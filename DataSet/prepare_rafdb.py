"""下载并准备 RAF-DB（7 类，真人脸表情）为 torchvision ImageFolder。

来源：HuggingFace `deanngkl/raf-db-7emotions`（非官方镜像，~2GB）。
> 注意：RAF-DB 官方需申请许可；此为公开镜像，仅供个人研究，许可灰色地带。

标签（已与官方核对，字母序，直接对应本项目 7 类 key）：
    0 angry  1 disgust  2 fear  3 happy  4 neutral  5 sad  6 surprise

镜像仅含一个 train 划分（20,471 张），本脚本按受试无关的随机种子做 90/10 train/val 切分。
输出：DataSet/rafdb/{train,val}/<emotion>/*.png

运行：python DataSet/prepare_rafdb.py
"""
import io
import os
import random

import pandas as pd
from huggingface_hub import hf_hub_download
from PIL import Image
from tqdm import tqdm

REPO = "deanngkl/raf-db-7emotions"
SHARDS = [f"data/train-0000{i}-of-00005.parquet" for i in range(5)]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rafdb")
RAW = os.path.join(OUT, "_raw")

LABELS = {0: "angry", 1: "disgust", 2: "fear", 3: "happy",
          4: "neutral", 5: "sad", 6: "surprise"}
VAL_FRAC = 0.1
SEED = 42


def main():
    os.makedirs(RAW, exist_ok=True)
    samples = []  # (png_bytes, emotion)
    for s in SHARDS:
        print(f"下载 {s} ...")
        path = hf_hub_download(REPO, s, repo_type="dataset", local_dir=RAW)
        df = pd.read_parquet(path, columns=["image", "label"])
        for row in df.itertuples(index=False):
            samples.append((row.image["bytes"], LABELS[int(row.label)]))
        print(f"  累计 {len(samples)} 张")

    random.Random(SEED).shuffle(samples)
    n_val = int(len(samples) * VAL_FRAC)
    splits = {"val": samples[:n_val], "train": samples[n_val:]}

    for split, items in splits.items():
        for e in LABELS.values():
            os.makedirs(os.path.join(OUT, split, e), exist_ok=True)
        for i, (raw_bytes, emotion) in enumerate(tqdm(items, desc=split)):
            img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            img.save(os.path.join(OUT, split, emotion, f"{split}_{i:05d}.png"))

    print("\n完成：")
    for split in ("train", "val"):
        counts = {e: len(os.listdir(os.path.join(OUT, split, e))) for e in LABELS.values()}
        print(f"  {split}: {sum(counts.values())}  {counts}")


if __name__ == "__main__":
    main()
