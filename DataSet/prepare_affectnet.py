"""把已下载的 AffectNet（no-contempt，7 类）parquet 解码为 torchvision ImageFolder。

来源：HuggingFace `deanngkl/affectnet_no_contempt`（非官方镜像，~8GB，27,823 张）。
> 注意：AffectNet 官方需学术申请；此为公开镜像，许可灰色地带，仅供个人研究。

标签（ClassLabel 元数据，字母序）：
    0 angry  1 disgust  2 fear  3 happy  4 neutral  5 sad  6 surprise

镜像仅一个 train 划分；本脚本按类内顺序做 stratified 90/10 train/val（每 10 张取 1 张作 val），
单遍流式解码、低内存。图像统一 resize 到 224×224（节省磁盘与训练 IO）。

输出：DataSet/affectnet/{train,val}/<emotion>/*.jpg

前置：先用 snapshot_download 下好 parquet 到 DataSet/affectnet/_raw/data/。
运行：python DataSet/prepare_affectnet.py
"""
import glob
import io
import os

import pandas as pd
from PIL import Image
from tqdm import tqdm

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "affectnet")
RAW = os.path.join(OUT, "_raw", "data")

LABELS = {0: "angry", 1: "disgust", 2: "fear", 3: "happy",
          4: "neutral", 5: "sad", 6: "surprise"}
IMG_SIZE = 224
VAL_EVERY = 10  # 每类每 10 张取 1 张作 val


def main():
    shards = sorted(glob.glob(os.path.join(RAW, "*.parquet")))
    if not shards:
        raise FileNotFoundError(f"未找到 parquet：{RAW}（先下载 AffectNet 镜像）")
    print(f"shards: {len(shards)}")

    for split in ("train", "val"):
        for e in LABELS.values():
            os.makedirs(os.path.join(OUT, split, e), exist_ok=True)

    per_class = {e: 0 for e in LABELS.values()}  # 类内计数，用于命名与切分
    counts = {"train": 0, "val": 0}
    for s in shards:
        df = pd.read_parquet(s, columns=["image", "label"])
        for row in tqdm(df.itertuples(index=False), total=len(df), desc=os.path.basename(s)):
            emo = LABELS[int(row.label)]
            i = per_class[emo]
            per_class[emo] += 1
            split = "val" if i % VAL_EVERY == 0 else "train"
            img = Image.open(io.BytesIO(row.image["bytes"])).convert("RGB")
            img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
            img.save(os.path.join(OUT, split, emo, f"{emo}_{i:06d}.jpg"), quality=92)
            counts[split] += 1

    print("\n完成：")
    for split in ("train", "val"):
        c = {e: len(os.listdir(os.path.join(OUT, split, e))) for e in LABELS.values()}
        print(f"  {split}: {counts[split]}  {c}")


if __name__ == "__main__":
    main()
