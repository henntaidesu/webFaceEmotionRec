"""校验自采 Quest Pro 数据并导出为 ImageFolder（供图像式训练器使用）。

输入格式见 DataSet/quest_pro_capture_spec.md：
    <capture_root>/<split>/<sample_id>.json + <sample_id>_central.jpg
每个 JSON：{"sample_id", "label", "image_central", "blendshapes":[63], "blendshape_names"?, ...}

本脚本做两件事（均为纯 Python，无需重造 notebook 的 build_manifest）：
  1. QC 校验：63 维、值域 0~1、顺序核对、图像存在且 224×224、标签合法、
     按受试者划分无身份泄漏、类别均衡统计。
  2. 可选导出：把 <sample_id>_central.jpg 摊平成 <out>/<split>/<emotion>/ 的
     torchvision ImageFolder 结构（7 类字母序），供 backend/src/use_train 直接训练。

用法：
    python DataSet/prepare_quest_pro.py --root <capture_root>            # 只校验
    python DataSet/prepare_quest_pro.py --root <capture_root> --out DataSet/quest_pro_imagefolder
"""
import argparse
import glob
import json
import os
import shutil
from collections import defaultdict

# 与 backend/src/config.py 的 TRAIN_CLASSES、notebook 的 CLASS_NAMES 一致（7 类，字母序）
CLASS_NAMES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

# EmoHeVRDB 原始情感名 → 本项目 7 类 key（与 notebook 的 EMOHEVR_LABEL_MAP 一致）
LABEL_MAP = {
    "anger": "angry", "disgust": "disgust", "fear": "fear", "happiness": "happy",
    "neutral": "neutral", "sadness": "sad", "surprise": "surprise",
    # 已是本项目 key 的直接透传
    **{c: c for c in CLASS_NAMES},
}

FEA_DIM = 63

# 63 维 OVRFaceExpressions 顺序（与 quest_pro_capture_spec.md §5 一致，用于核对 blendshape_names）
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

DEFAULT_SPLITS = ["train", "val", "test"]


def _subject_of(sample_id):
    """从 sample_id 解析受试者，如 p07_e0123 → p07。解析不出则用整个 id。"""
    return sample_id.split("_", 1)[0] if "_" in sample_id else sample_id


def validate_split(split_dir, warnings, errors, want_image_size=(224, 224)):
    """校验单个 split 目录，返回 [(sample_id, subject, emotion, image_path), ...]。"""
    try:
        from PIL import Image
        have_pil = True
    except ImportError:
        have_pil = False

    samples = []
    for jp in sorted(glob.glob(os.path.join(split_dir, "*.json"))):
        name = os.path.basename(jp)
        try:
            with open(jp, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{name}: JSON 读取失败 ({e})")
            continue

        sample_id = meta.get("sample_id") or os.path.splitext(name)[0]

        # label
        raw_label = meta.get("label")
        if raw_label is None:
            errors.append(f"{name}: 缺 label")
            continue
        emotion = LABEL_MAP.get(raw_label)
        if emotion is None:
            errors.append(f"{name}: 未知 label '{raw_label}'（应为 EmoHeVRDB 名或 7 类 key）")
            continue

        # blendshapes
        bs = meta.get("blendshapes")
        if not isinstance(bs, list):
            errors.append(f"{name}: 缺 blendshapes 或非数组")
            continue
        if len(bs) != FEA_DIM:
            errors.append(f"{name}: blendshapes 维度应为 {FEA_DIM}，实际 {len(bs)}")
            continue
        if any((not isinstance(v, (int, float))) or v < -0.01 or v > 1.01 for v in bs):
            warnings.append(f"{name}: blendshapes 存在超出 0~1 的值")

        # blendshape_names 顺序核对（可选但强烈建议）
        names = meta.get("blendshape_names")
        if names is not None and list(names) != OVR_FACE_EXPRESSIONS:
            warnings.append(f"{name}: blendshape_names 与 OVRFaceExpressions 标准顺序不一致（合并 EmoHeVRDB 前必须核对）")

        # 图像
        img_name = meta.get("image_central") or meta.get("image")
        if not img_name:
            errors.append(f"{name}: 缺 image_central")
            continue
        img_path = os.path.join(split_dir, img_name)
        if not os.path.exists(img_path):
            errors.append(f"{name}: 图像不存在 {img_name}")
            continue
        if have_pil:
            try:
                with Image.open(img_path) as im:
                    if im.size != want_image_size:
                        warnings.append(f"{name}: 图像尺寸 {im.size} ≠ {want_image_size}")
            except OSError as e:
                errors.append(f"{name}: 图像打不开 ({e})")
                continue

        samples.append((sample_id, _subject_of(sample_id), emotion, img_path))
    return samples


def main():
    ap = argparse.ArgumentParser(description="校验并导出 Quest Pro 自采数据")
    ap.add_argument("--root", required=True, help="采集根目录（含 train/val/test 子目录）")
    ap.add_argument("--out", default=None,
                    help="导出的 ImageFolder 根目录（省略则只校验）；"
                         "用 DataSet/quest_pro 可直接在训练/评测面板中作为 quest_pro 数据集出现")
    ap.add_argument("--splits", nargs="+", default=DEFAULT_SPLITS)
    ap.add_argument("--copy", action="store_true", help="导出时复制图像（默认硬链接，省空间）")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"[错误] 找不到采集根目录：{args.root}")
        print("       采集完成后（见 DataSet/quest_pro_capture_spec.md）再运行本脚本。")
        raise SystemExit(2)

    warnings, errors = [], []
    split_samples = {}
    subject_splits = defaultdict(set)

    for split in args.splits:
        split_dir = os.path.join(args.root, split)
        if not os.path.isdir(split_dir):
            warnings.append(f"跳过不存在的 split：{split}")
            split_samples[split] = []
            continue
        samples = validate_split(split_dir, warnings, errors)
        split_samples[split] = samples
        for _, subject, _, _ in samples:
            subject_splits[subject].add(split)

    # 身份泄漏检查：同一受试者不应出现在多个 split
    leaked = {s: sorted(sp) for s, sp in subject_splits.items() if len(sp) > 1}
    for s, sp in leaked.items():
        errors.append(f"身份泄漏：受试者 {s} 同时出现在 {sp}")

    # 报告
    print("=" * 60)
    print(f"采集根目录：{args.root}")
    for split in args.splits:
        samples = split_samples.get(split, [])
        per_class = defaultdict(int)
        for _, _, emotion, _ in samples:
            per_class[emotion] += 1
        subjects = sorted({sub for _, sub, _, _ in samples})
        print(f"\n[{split}] {len(samples)} 样本 | {len(subjects)} 受试者 {subjects}")
        print("   类别分布：" + ", ".join(f"{c}={per_class.get(c, 0)}" for c in CLASS_NAMES))

    print("\n" + "-" * 60)
    print(f"警告 {len(warnings)}、错误 {len(errors)}")
    for w in warnings[:50]:
        print(f"  [warn] {w}")
    for e in errors[:50]:
        print(f"  [ERR ] {e}")
    if len(warnings) > 50 or len(errors) > 50:
        print("  ...（更多略）")

    # 导出 ImageFolder
    if args.out:
        if errors:
            print("\n[跳过导出] 存在错误，请先修复后再导出。")
            raise SystemExit(1)
        total = 0
        for split, samples in split_samples.items():
            for sample_id, _, emotion, img_path in samples:
                dst_dir = os.path.join(args.out, split, emotion)
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, f"{sample_id}.jpg")
                if os.path.exists(dst):
                    os.remove(dst)
                if args.copy:
                    shutil.copy2(img_path, dst)
                else:
                    try:
                        os.link(img_path, dst)
                    except OSError:
                        shutil.copy2(img_path, dst)
                total += 1
        print(f"\n[导出完成] {total} 张 → {args.out}（ImageFolder：<split>/<emotion>/）")

    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
