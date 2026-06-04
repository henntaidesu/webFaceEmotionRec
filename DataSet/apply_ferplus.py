"""用 FER+ 的改进标注重组已有的 FER2013，生成更干净的 7 类 ImageFolder。

FER+（microsoft/FERPlus 的 fer2013new.csv）按原始 FER2013 行序为每张图提供多人投票标注。
已验证本地 DataSet/fer2013 的行序与之对齐（一致率 ~63%，符合 FER+ 论文报告值）。

做法：对每张图取投票多数类；丢弃多数为 contempt / unknown / NF（非人脸）的样本，
保留 7 类，把已有图像复制到新的标签目录。

输出：DataSet/fer2013_plus/{train,val,test}/<emotion>/*.png

前置：已运行 prepare_fer2013.py；fer2013new.csv 可从
  https://raw.githubusercontent.com/microsoft/FERPlus/master/fer2013new.csv 获取。

运行：python DataSet/apply_ferplus.py
"""
import csv
import glob
import os
import shutil
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FER = os.path.join(HERE, "fer2013")
OUT = os.path.join(HERE, "fer2013_plus")
CSV = os.path.join(OUT, "_raw", "fer2013new.csv")
CSV_URL = "https://raw.githubusercontent.com/microsoft/FERPlus/master/fer2013new.csv"

USAGE2SPLIT = {"Training": "train", "PublicTest": "val", "PrivateTest": "test"}
# fer2013new.csv 全部投票列（顺序固定）
VOTE_COLS = ["neutral", "happiness", "surprise", "sadness", "anger",
             "disgust", "fear", "contempt", "unknown", "NF"]
# FER+ 情感名 → 本项目 7 类 key（contempt/unknown/NF 不在其中 → 丢弃）
TO_KEY = {"neutral": "neutral", "happiness": "happy", "surprise": "surprise",
          "sadness": "sad", "anger": "angry", "disgust": "disgust", "fear": "fear"}


def index_map(split):
    """{行号: 该图在本地的 png 路径}（行号来自文件名 {split}_{idx}.png）。"""
    m = {}
    for path in glob.glob(os.path.join(FER, split, "*", f"{split}_*.png")):
        idx = int(os.path.basename(path).split("_")[1].split(".")[0])
        m[idx] = path
    return m


def main():
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    if not os.path.exists(CSV):
        print("下载 fer2013new.csv ...")
        urllib.request.urlretrieve(CSV_URL, CSV)

    # 按 split 收集 FER+ 行（保持原序）
    rows = {"train": [], "val": [], "test": []}
    with open(CSV, newline="") as f:
        for r in csv.DictReader(f):
            sp = USAGE2SPLIT.get(r["Usage"])
            if sp:
                rows[sp].append(r)

    stats = {}
    dropped = 0
    for split in ("train", "val", "test"):
        imgs = index_map(split)
        for e in TO_KEY.values():
            os.makedirs(os.path.join(OUT, split, e), exist_ok=True)
        kept = 0
        for j, r in enumerate(rows[split]):
            if j not in imgs:
                continue
            votes = [int(r[c]) for c in VOTE_COLS]
            top = VOTE_COLS[votes.index(max(votes))]
            key = TO_KEY.get(top)
            if key is None:          # contempt / unknown / NF → 丢弃
                dropped += 1
                continue
            shutil.copy(imgs[j], os.path.join(OUT, split, key, f"{split}_{j:05d}.png"))
            kept += 1
        stats[split] = kept

    print("\n完成（FER+ 7 类）：")
    for split in ("train", "val", "test"):
        counts = {e: len(os.listdir(os.path.join(OUT, split, e))) for e in TO_KEY.values()}
        print(f"  {split}: {stats[split]}  {counts}")
    print(f"  丢弃（contempt/unknown/NF 多数）：{dropped}")


if __name__ == "__main__":
    main()
