"""把 FEA 时序会话（SessionRecorder 落盘）切成滑窗训练样本，按受试者划分。

输入（时间轴新格式，见 docs/任务书_VR微情感时序采集与情绪预测.md §5）：
    <capture_root>/<subject_id>/<session_id>/{meta.json, fea.csv, selfreport.csv, ...}
    fea.csv: timestamp_ms, f0..f62（OVRFaceExpressions 顺序，0~1）

处理：把每个 session 的 fea 重采样到固定帧率 → 逐帧算 7 类「表情」标签（规则式 FACS，
或用 --label-source selfreport 取最近自评）→ 滑窗切片：
    X = 过去 window_s 秒序列 (seq_len, 63)
    y = 未来 horizon_s 秒时刻的 7 类索引（即「预测接下来会产生什么表情」）

输出（供 backend/src/use_predict/train_predict.py 训练）：
    <out>/{meta.json, train.npz, val.npz, test.npz}   *.npz: X(N,seq_len,63) float32, y(N,) int64

划分按受试者（禁止同人跨 split）。用法：
    python DataSet/prepare_timeline_dataset.py --root Capture --out DataSet/timeline_sliced \
        --window-s 5 --horizon-s 3 --rate-hz 30
"""
import argparse
import csv
import glob
import json
import os
from collections import defaultdict

import numpy as np

CLASS_NAMES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
FEA_DIM = 63

# 与 backend/src/use_model/fea_emotion.py 一致（脚本自包含，不 import 后端）
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
_IDX = {n: i for i, n in enumerate(OVR_FACE_EXPRESSIONS)}
_AU_GROUPS = {
    "happy":    ["CheekRaiserL", "CheekRaiserR", "LipCornerPullerL", "LipCornerPullerR", "DimplerL", "DimplerR"],
    "sad":      ["InnerBrowRaiserL", "InnerBrowRaiserR", "LipCornerDepressorL", "LipCornerDepressorR", "LowerLipDepressorL", "LowerLipDepressorR"],
    "surprise": ["InnerBrowRaiserL", "InnerBrowRaiserR", "OuterBrowRaiserL", "OuterBrowRaiserR", "UpperLidRaiserL", "UpperLidRaiserR", "JawDrop"],
    "fear":     ["InnerBrowRaiserL", "InnerBrowRaiserR", "OuterBrowRaiserL", "OuterBrowRaiserR", "BrowLowererL", "BrowLowererR", "UpperLidRaiserL", "UpperLidRaiserR", "LipStretcherL", "LipStretcherR"],
    "angry":    ["BrowLowererL", "BrowLowererR", "LidTightenerL", "LidTightenerR", "LipTightenerL", "LipTightenerR", "LipPressorL", "LipPressorR"],
    "disgust":  ["NoseWrinklerL", "NoseWrinklerR", "UpperLipRaiserL", "UpperLipRaiserR", "LipCornerDepressorL", "LipCornerDepressorR"],
}


def fea_labels(feats):
    """feats: (n, 63) → (n,) 每帧 7 类索引（规则式 FACS，与 classify_fea 同逻辑）。"""
    n = len(feats)
    scores = np.zeros((n, len(CLASS_NAMES)), dtype="float32")
    for ci, c in enumerate(CLASS_NAMES):
        if c == "neutral":
            continue
        cols = [_IDX[name] for name in _AU_GROUPS[c]]
        scores[:, ci] = feats[:, cols].mean(axis=1)
    max_other = scores.max(axis=1)
    scores[:, CLASS_NAMES.index("neutral")] = np.maximum(0.0, 1.0 - 1.6 * max_other)
    return scores.argmax(axis=1)


def load_fea_csv(path):
    """返回 (ts:(n,) int64, feats:(n,63) float32)，按时间戳升序。"""
    ts, feats = [], []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # 表头
        for row in reader:
            if len(row) < FEA_DIM + 1:
                continue
            ts.append(int(float(row[0])))
            feats.append([float(x) for x in row[1:1 + FEA_DIM]])
    if not ts:
        return None, None
    ts = np.array(ts, dtype="int64")
    feats = np.array(feats, dtype="float32")
    order = np.argsort(ts)
    return ts[order], feats[order]


def resample(ts, feats, rate_hz):
    """把不规则时间戳的 feats 线性重采样到固定帧率的均匀网格。返回 (grid_ts, grid_feats)。"""
    t0, t1 = ts[0], ts[-1]
    step = 1000.0 / rate_hz
    grid = np.arange(t0, t1 + 1e-6, step)
    if len(grid) < 2:
        return None, None
    out = np.empty((len(grid), feats.shape[1]), dtype="float32")
    for k in range(feats.shape[1]):
        out[:, k] = np.interp(grid, ts, feats[:, k])
    return grid.astype("int64"), out


def load_selfreport(path):
    """返回按时间戳升序 [(ts, label_idx), ...]；label 非法则跳过。"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            lab = row[2].strip()
            if lab in CLASS_NAMES:
                out.append((int(float(row[0])), CLASS_NAMES.index(lab)))
    out.sort(key=lambda r: r[0])
    return out


def selfreport_labels(grid_ts, reports):
    """对每个网格时刻取「最近一次已发生的自评」标签（前向填充）；无则 -1。"""
    labels = np.full(len(grid_ts), -1, dtype="int64")
    if not reports:
        return labels
    rts = [r[0] for r in reports]
    j = 0
    for i, t in enumerate(grid_ts):
        while j + 1 < len(rts) and rts[j + 1] <= t:
            j += 1
        if rts[j] <= t:
            labels[i] = reports[j][1]
    return labels


def slice_session(sess_dir, window_s, horizon_s, rate_hz, stride, label_source):
    fea_path = os.path.join(sess_dir, "fea.csv")
    if not os.path.exists(fea_path):
        return [], []
    ts, feats = load_fea_csv(fea_path)
    if ts is None or len(ts) < 4:
        return [], []
    grid_ts, grid = resample(ts, feats, rate_hz)
    if grid is None:
        return [], []

    if label_source == "selfreport":
        lab = selfreport_labels(grid_ts, load_selfreport(os.path.join(sess_dir, "selfreport.csv")))
    else:
        lab = fea_labels(grid)

    seq_len = int(round(window_s * rate_hz))
    horizon = int(round(horizon_s * rate_hz))
    X, y = [], []
    last_start = len(grid) - seq_len - horizon
    for s in range(0, last_start + 1, stride):
        target = lab[s + seq_len - 1 + horizon]
        if target < 0:            # selfreport 尚无标签
            continue
        X.append(grid[s:s + seq_len])
        y.append(int(target))
    return X, y


def assign_splits(subjects, ratios):
    """按受试者稳定划分 train/val/test。"""
    subs = sorted(subjects)
    n = len(subs)
    n_tr = max(1, int(round(n * ratios[0]))) if n else 0
    n_va = int(round(n * ratios[1]))
    # 至少各留一个（受试者足够时）
    if n >= 3:
        n_tr = min(n_tr, n - 2)
        n_va = max(1, min(n_va, n - n_tr - 1))
    split = {}
    for i, s in enumerate(subs):
        split[s] = "train" if i < n_tr else ("val" if i < n_tr + n_va else "test")
    return split


def main():
    ap = argparse.ArgumentParser(description="FEA 时序会话 → 滑窗训练样本（按受试者划分）")
    ap.add_argument("--root", required=True, help="采集根目录（含 <subject>/<session>/fea.csv）")
    ap.add_argument("--out", required=True, help="输出滑窗数据集目录")
    ap.add_argument("--window-s", type=float, default=5.0)
    ap.add_argument("--horizon-s", type=float, default=3.0)
    ap.add_argument("--rate-hz", type=float, default=30.0)
    ap.add_argument("--stride", type=int, default=5, help="滑窗步长（网格帧）")
    ap.add_argument("--label-source", choices=["fea", "selfreport"], default="fea",
                    help="标签来源：fea=规则式表情(默认) / selfreport=最近自评")
    ap.add_argument("--ratios", type=float, nargs=3, default=[0.7, 0.15, 0.15],
                    help="按受试者划分 train val test 比例")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"[错误] 找不到采集根目录：{args.root}（先经 SessionRecorder 采集落盘）")
        raise SystemExit(2)

    # 收集受试者
    sessions = []  # (subject, session_dir)
    for meta_path in sorted(glob.glob(os.path.join(args.root, "*", "*", "meta.json"))):
        sess_dir = os.path.dirname(meta_path)
        subject = os.path.basename(os.path.dirname(sess_dir))
        sessions.append((subject, sess_dir))
    # 兼容没有 meta.json、但有 fea.csv 的目录
    if not sessions:
        for fea_path in sorted(glob.glob(os.path.join(args.root, "*", "*", "fea.csv"))):
            sess_dir = os.path.dirname(fea_path)
            subject = os.path.basename(os.path.dirname(sess_dir))
            sessions.append((subject, sess_dir))

    if not sessions:
        print(f"[错误] {args.root} 下没有会话（缺 fea.csv）。")
        raise SystemExit(2)

    subjects = {s for s, _ in sessions}
    split_of = assign_splits(subjects, args.ratios)

    buckets = {"train": ([], []), "val": ([], []), "test": ([], [])}
    per_subject = defaultdict(int)
    for subject, sess_dir in sessions:
        X, y = slice_session(sess_dir, args.window_s, args.horizon_s, args.rate_hz,
                             args.stride, args.label_source)
        sp = split_of[subject]
        buckets[sp][0].extend(X)
        buckets[sp][1].extend(y)
        per_subject[subject] += len(X)

    os.makedirs(args.out, exist_ok=True)
    seq_len = int(round(args.window_s * args.rate_hz))
    total = 0
    for sp, (X, y) in buckets.items():
        if not X:
            continue
        Xa = np.asarray(X, dtype="float32")
        ya = np.asarray(y, dtype="int64")
        np.savez_compressed(os.path.join(args.out, f"{sp}.npz"), X=Xa, y=ya)
        total += len(X)
        dist = np.bincount(ya, minlength=len(CLASS_NAMES))
        print(f"[{sp}] {len(X)} 样本 | 类别分布 " +
              ", ".join(f"{c}={int(dist[i])}" for i, c in enumerate(CLASS_NAMES)))

    meta = {
        "classes": CLASS_NAMES,
        "window_s": args.window_s,
        "horizon_s": args.horizon_s,
        "rate_hz": args.rate_hz,
        "seq_len": seq_len,
        "input_dim": FEA_DIM,
        "feature": "fea",
        "label_source": args.label_source,
        "splits": {sp: sorted([s for s, v in split_of.items() if v == sp]) for sp in buckets},
    }
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print(f"\n[完成] 共 {total} 样本 → {args.out}")
    print("受试者划分：" + ", ".join(f"{s}:{split_of[s]}" for s in sorted(subjects)))
    print("下一步：from backend.src.use_predict.train_predict import train_predict; "
          f"train_predict('{args.out}')")
    raise SystemExit(0 if total else 1)


if __name__ == "__main__":
    main()
