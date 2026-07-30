"""回归检查：离线 fea_labels 必须与线上 classify_fea 判出同一个主情绪。

prepare_timeline_dataset.py 出于「脚本自包含、不 import 后端」的考虑，复制了一份
OVR_FACE_EXPRESSIONS / _AU_GROUPS / neutral 系数。两份规则一旦漂移，离线训练标签
与线上实时显示就会不一致，而且不会报任何错——只会让训练与推理悄悄对不上。

本脚本对拍两者。改动任一侧的规则表后都应重跑；不一致时退出码非 0。

用法：
    python DataSet/check_rule_parity.py
    python DataSet/check_rule_parity.py --n 20000 --seed 7
"""
import argparse
import os
import sys

import numpy as np

os.environ.setdefault("REQUIRE_CUDA", "0")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import prepare_timeline_dataset as P                                        # noqa: E402
from backend.src.use_model.fea_emotion import (                             # noqa: E402
    OVR_FACE_EXPRESSIONS as BE_NAMES,
    _AU_GROUPS as BE_GROUPS,
    classify_fea,
)


def main():
    ap = argparse.ArgumentParser(description="离线/线上 FEA 规则对拍")
    ap.add_argument("--n", type=int, default=5000, help="随机对拍帧数")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    fails = []

    if list(BE_NAMES) != list(P.OVR_FACE_EXPRESSIONS):
        fails.append("OVR_FACE_EXPRESSIONS 两侧不一致")
    if {k: sorted(v) for k, v in BE_GROUPS.items()} != {k: sorted(v) for k, v in P._AU_GROUPS.items()}:
        fails.append("_AU_GROUPS 两侧不一致")

    rng = np.random.default_rng(args.seed)
    # 混合不同激活强度，覆盖 neutral 判定边界
    X = rng.random((args.n, len(P.OVR_FACE_EXPRESSIONS))).astype("float32")
    X *= rng.choice([0.1, 0.3, 0.6, 1.0], size=(args.n, 1))

    offline = P.fea_labels(X)
    mismatch = []
    for i in range(args.n):
        online = classify_fea(X[i].tolist())["dominant_en"]
        if P.CLASS_NAMES[offline[i]] != online:
            mismatch.append((i, P.CLASS_NAMES[offline[i]], online))

    print(f"对拍 {args.n} 帧：不一致 {len(mismatch)} 帧")
    for i, off, on in mismatch[:10]:
        print(f"  帧 {i}: 离线={off} 线上={on}")
    if mismatch:
        fails.append(f"{len(mismatch)}/{args.n} 帧主情绪判定不一致")

    if fails:
        print("\n[失败] " + "；".join(fails))
        print("请同步 backend/src/use_model/fea_emotion.py 与 "
              "DataSet/prepare_timeline_dataset.py 两处的规则表。")
        raise SystemExit(1)
    print("[通过] 两侧规则一致")


if __name__ == "__main__":
    main()
