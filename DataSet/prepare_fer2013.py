"""下载并准备 FER2013 数据集（与本项目模型一致的 7 类情感）。

来源：HuggingFace 数据集 `Aaryan333/fer2013_train_publicTest_privateTest`
      （原始 FER2013 的三路划分：train / PublicTest / PrivateTest，parquet 格式）。

输出 torchvision ImageFolder 结构，便于直接训练：
    DataSet/fer2013/
        train/<emotion>/*.png   28709 张
        val/<emotion>/*.png      3589 张（原 PublicTest，作验证集）
        test/<emotion>/*.png     3589 张（原 PrivateTest，作测试集）

标签映射（FER2013 原始整数 → 英文 key，与 backend/src/labels.py 对应）：
    0 angry  1 disgust  2 fear  3 happy  4 sad  5 surprise  6 neutral

运行：python DataSet/prepare_fer2013.py
"""
import io
import os

import pandas as pd
from huggingface_hub import hf_hub_download
from PIL import Image
from tqdm import tqdm

REPO = "Aaryan333/fer2013_train_publicTest_privateTest"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fer2013")
RAW = os.path.join(OUT, "_raw")

# parquet 文件名 → 输出子目录名
SPLITS = {
    "data/train-00000-of-00001-5eab84e1c6a2fc27.parquet": "train",
    "data/publicTest-00000-of-00001-f41bb7384b8aad6e.parquet": "val",
    "data/privateTest-00000-of-00001-4b8a0715cf1b7560.parquet": "test",
}

LABELS = {
    0: "angry", 1: "disgust", 2: "fear", 3: "happy",
    4: "sad", 5: "surprise", 6: "neutral",
}


def main():
    os.makedirs(RAW, exist_ok=True)
    for fname, split in SPLITS.items():
        print(f"[1/2] 下载 {split} parquet ...")
        path = hf_hub_download(REPO, fname, repo_type="dataset", local_dir=RAW)
        df = pd.read_parquet(path)
        print(f"[2/2] 解码 {split}: {len(df)} 张图片")
        for name in LABELS.values():
            os.makedirs(os.path.join(OUT, split, name), exist_ok=True)
        for i, row in enumerate(tqdm(df.itertuples(index=False), total=len(df), desc=split)):
            label_name = LABELS[int(row.label)]
            img = Image.open(io.BytesIO(row.image["bytes"]))
            img.save(os.path.join(OUT, split, label_name, f"{split}_{i:05d}.png"))

    print("\n完成。结构如下：")
    for split in SPLITS.values():
        total = sum(
            len(os.listdir(os.path.join(OUT, split, n))) for n in LABELS.values()
        )
        print(f"  {split}: {total} 张")
    print(f"\n输出目录: {OUT}")
    print("提示：可用 torchvision.datasets.ImageFolder 直接加载。")


if __name__ == "__main__":
    main()
