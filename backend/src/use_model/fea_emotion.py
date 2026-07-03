"""由 Meta Quest Pro 的 63 维 FACS 面部混合形状（Face Tracking）判定 7 类情绪。

Quest Pro 不开放机内摄像头原始图像，只提供抽象的 63 维 blendshape 权重（0~1，
OVRFaceExpressions 顺序）。本模块把这些权重按 FACS 动作单元（Ekman）映射到 7 类情绪。

这是**规则式基线**（无需训练即可用）；将来可换成 train_multimodal_fer_vr.ipynb
训练出的 FEA 分支模型（接口保持 classify_fea(list[63]) -> dict 即可）。
"""
from . import labels

# 63 维 OVRFaceExpressions 顺序（与 DataSet/quest_pro_capture_spec.md / prepare_quest_pro.py 一致）
OVR_FACE_EXPRESSIONS = [
    "BrowLowererL", "BrowLowererR", "CheekPuffL", "CheekPuffR", "CheekRaiserL", "CheekRaiserR",
    "CheekSuckL", "CheekSuckR", "ChinRaiserB", "ChinRaiserT", "DimplerL", "DimplerR",
    "EyesClosedL", "EyesClosedR", "EyesLookDownL", "EyesLookDownR", "EyesLookLeftL", "EyesLookLeftR",
    "EyesLookRightL", "EyesLookRightR", "EyesLookUpL", "EyesLookUpR", "InnerBrowRaiserL", "InnerBrowRaiserR",
    "JawDrop", "JawSidewaysLeft", "JawSidewaysRight", "JawThrust", "LidTightenerL", "LidTightenerR",
    "LipCornerDepressorL", "LipCornerDepressorR", "LipCornerPullerL", "LipCornerPullerR",
    "LipFunnelerLB", "LipFunnelerLT", "LipFunnelerRB", "LipFunnelerRT", "LipPressorL", "LipPressorR",
    "LipPuckerL", "LipPuckerR", "LipStretcherL", "LipStretcherR", "LipSuckLB", "LipSuckLT",
    "LipSuckRB", "LipSuckRT", "LipTightenerL", "LipTightenerR", "LipsToward", "LowerLipDepressorL",
    "LowerLipDepressorR", "MouthLeft", "MouthRight", "NoseWrinklerL", "NoseWrinklerR",
    "OuterBrowRaiserL", "OuterBrowRaiserR", "UpperLidRaiserL", "UpperLidRaiserR",
    "UpperLipRaiserL", "UpperLipRaiserR",
]
_IDX = {name: i for i, name in enumerate(OVR_FACE_EXPRESSIONS)}
FEA_DIM = len(OVR_FACE_EXPRESSIONS)  # 63

# FACS 动作单元组合 → 情绪（Ekman）。用组内 blendshape 均值作为该情绪激活强度。
_AU_GROUPS = {
    "happy":    ["CheekRaiserL", "CheekRaiserR", "LipCornerPullerL", "LipCornerPullerR", "DimplerL", "DimplerR"],
    "sad":      ["InnerBrowRaiserL", "InnerBrowRaiserR", "LipCornerDepressorL", "LipCornerDepressorR", "LowerLipDepressorL", "LowerLipDepressorR"],
    "surprise": ["InnerBrowRaiserL", "InnerBrowRaiserR", "OuterBrowRaiserL", "OuterBrowRaiserR", "UpperLidRaiserL", "UpperLidRaiserR", "JawDrop"],
    "fear":     ["InnerBrowRaiserL", "InnerBrowRaiserR", "OuterBrowRaiserL", "OuterBrowRaiserR", "BrowLowererL", "BrowLowererR", "UpperLidRaiserL", "UpperLidRaiserR", "LipStretcherL", "LipStretcherR"],
    "angry":    ["BrowLowererL", "BrowLowererR", "LidTightenerL", "LidTightenerR", "LipTightenerL", "LipTightenerR", "LipPressorL", "LipPressorR"],
    "disgust":  ["NoseWrinklerL", "NoseWrinklerR", "UpperLipRaiserL", "UpperLipRaiserR", "LipCornerDepressorL", "LipCornerDepressorR"],
}

_EN_ORDER = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]


def _group_score(bs, names):
    vals = [bs[_IDX[n]] for n in names if n in _IDX]
    return sum(vals) / len(vals) if vals else 0.0


def classify_fea(blendshapes) -> dict:
    """blendshapes: 长度 63 的 0~1 浮点列表（OVRFaceExpressions 顺序）。

    返回与图像识别路径同构的 face 结构：
        {"dominant_en", "dominant"(中文), "emotions": {中文标签: 百分比}}
    """
    if not isinstance(blendshapes, (list, tuple)) or len(blendshapes) != FEA_DIM:
        raise ValueError(f"blendshapes 维度应为 {FEA_DIM}，实际 {len(blendshapes) if hasattr(blendshapes, '__len__') else '?'}")
    bs = [float(x) for x in blendshapes]

    scores = {emo: _group_score(bs, names) for emo, names in _AU_GROUPS.items()}
    # 中性：整体表情越弱越中性
    max_other = max(scores.values()) if scores else 0.0
    scores["neutral"] = max(0.0, 1.0 - 1.6 * max_other)

    total = sum(scores.values()) or 1.0
    emotions_zh = {}
    for en in _EN_ORDER:
        pct = round(scores.get(en, 0.0) / total * 100, 2)
        emotions_zh[labels.to_zh(en)] = pct

    dominant_en = max(_EN_ORDER, key=lambda e: scores.get(e, 0.0))
    return {
        "dominant_en": dominant_en,
        "dominant": labels.to_zh(dominant_en),
        "emotions": emotions_zh,
    }
