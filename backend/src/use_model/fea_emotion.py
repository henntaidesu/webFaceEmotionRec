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


def normalize_blendshapes(blendshapes) -> list[float]:
    """校验并裁到 FEA_DIM 维。

    **为什么允许多于 63 维**：Meta XR SDK 从 `FaceExpression` 换到 `FaceExpression2` 后，
    `OVRFaceExpressions.FaceExpression.Max` 由 63 变成 **70**——末尾追加了 7 个舌头
    blendshape（Tongue_Tip_Interdental=63 … Tongue_Retreat=69）。头显因此发 70 维，
    而这里原先严格要求 63，导致 `POST /api/fea` 全部 400、一帧都存不下来。
    前 63 维的顺序和含义没变，取前 63 维即可，与既有 63 维训练管线保持一致。
    （代价：舌头那 7 维被丢弃。本课题是面部情绪，暂不需要；要用得同步改
    OVR_FACE_EXPRESSIONS、config.FEA_DIM 与切窗脚本。）
    """
    if not isinstance(blendshapes, (list, tuple)) or len(blendshapes) < FEA_DIM:
        n = len(blendshapes) if hasattr(blendshapes, "__len__") else "?"
        raise ValueError(f"blendshapes 维度应 ≥ {FEA_DIM}，实际 {n}")
    return [float(x) for x in blendshapes[:FEA_DIM]]


def classify_fea(blendshapes) -> dict:
    """blendshapes: 至少 63 维的 0~1 浮点列表（OVRFaceExpressions 顺序，多余维度忽略）。

    返回与图像识别路径同构的 face 结构：
        {"dominant_en", "dominant"(中文), "emotions": {中文标签: 百分比}}
    """
    bs = normalize_blendshapes(blendshapes)

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
