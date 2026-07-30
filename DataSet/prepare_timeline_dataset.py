"""把 FEA 时序会话（SessionRecorder 落盘）切成滑窗训练样本，按受试者划分。

输入（时间轴新格式，见 docs/任务书_VR微情感时序采集与情绪预测.md §5）：
    <capture_root>/<subject_id>/<session_id>/{meta.json, fea.csv, selfreport.csv, ...}
    fea.csv: timestamp_ms, f0..f62（OVRFaceExpressions 顺序，0~1）

处理：把每个 session 的 fea 按时间戳重采样到固定帧率（**遇到采集空洞即断段，不跨洞插值**）
→ 逐帧取标签 → 滑窗切片：
    X = 过去 window_s 秒序列 (seq_len, 63)
    y = 未来 horizon_s 秒时刻的 7 类索引（即「预测接下来会产生什么表情」）

**标签源默认 selfreport（自评）**。规则式 `fea` 标签由 classify_fea 从同一份 63 维 FEA 算出，
与 X 同源——用它训练等于让模型去拟合一个确定性函数 f(X)，「预测准不准」无法被证伪。
故 `--label-source fea` 仅供调试，需显式加 `--allow-circular-labels` 才放行。

输出（供 backend/src/use_predict/train_predict.py 训练）：
    <out>/{meta.json, train.npz, val.npz, test.npz, all.npz}
    *.npz: X(N,seq_len,63) f32, y(N,) i64, y_now(N,) i64, subj(N,) <U, block(N,) <U
      y_now = 窗末当前标签，供 persistence 基线；subj/block 供 LOSO 与 block-level 指标。

划分按受试者（禁止同人跨 split）；受试者 <3 人时不做三分，全部落 train 并要求走 LOSO。
用法：
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


def resample_segments(ts, feats, rate_hz, max_gap_s):
    """按时间戳重采样到固定帧率，**相邻帧间隔超过 max_gap_s 即断段**。

    返回 [(grid_ts, grid_feats), ...]。掉帧、摘头显、会话暂停都会在时间轴上留下空洞，
    若像原先那样对整段直接 np.interp，空洞会被线性插值填成平滑假数据（而且滑窗还会
    横跨它）——那是凭空捏造的观测，必须断开。
    """
    step = 1000.0 / rate_hz
    gap_ms = max_gap_s * 1000.0
    # ts[i] 与 ts[i+1] 间隔过大 → 段在 i 处结束
    cut = np.where(np.diff(ts) > gap_ms)[0]
    segs = []
    start = 0
    for end in list(cut) + [len(ts) - 1]:
        if end > start:                       # 至少 2 帧才能插值
            s_ts, s_f = ts[start:end + 1], feats[start:end + 1]
            grid = np.arange(s_ts[0], s_ts[-1] + 1e-6, step)
            if len(grid) >= 2:
                out = np.empty((len(grid), s_f.shape[1]), dtype="float32")
                for k in range(s_f.shape[1]):
                    out[:, k] = np.interp(grid, s_ts, s_f[:, k])
                segs.append((grid.astype("int64"), out))
        start = end + 1
    return segs


def observed_rate_hz(ts):
    """实际采集帧率（用中位间隔估计），用于核对 --rate-hz 是否离谱。"""
    if len(ts) < 2:
        return None
    med = float(np.median(np.diff(ts)))
    return 1000.0 / med if med > 0 else None


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


def load_blocks(path):
    """stimulus.csv → 按 onset 升序 [(onset_ms, image_id), ...]，用于 block-level 评测分组。"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            try:
                out.append((int(float(row[0])), str(row[1]).strip()))
            except ValueError:
                continue
    out.sort(key=lambda r: r[0])
    return out


def block_at(blocks, t_ms, fallback):
    """t_ms 落在哪个刺激块内（取最近一次已开始的刺激）；无 stimulus.csv 时回落到会话名。"""
    if not blocks:
        return fallback
    lo, hi = 0, len(blocks) - 1
    if t_ms < blocks[0][0]:
        return fallback
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if blocks[mid][0] <= t_ms:
            lo = mid
        else:
            hi = mid - 1
    return blocks[lo][1] or fallback


def slice_session(sess_dir, window_s, horizon_s, rate_hz, stride, label_source, max_gap_s):
    """返回 (X, y, y_now, block)：y_now 为窗末当前标签（persistence 基线用）。"""
    empty = ([], [], [], [])
    fea_path = os.path.join(sess_dir, "fea.csv")
    if not os.path.exists(fea_path):
        return empty
    ts, feats = load_fea_csv(fea_path)
    if ts is None or len(ts) < 4:
        return empty

    reports = load_selfreport(os.path.join(sess_dir, "selfreport.csv"))
    blocks = load_blocks(os.path.join(sess_dir, "stimulus.csv"))
    sess_name = os.path.basename(sess_dir.rstrip("/\\"))

    seq_len = int(round(window_s * rate_hz))
    horizon = int(round(horizon_s * rate_hz))
    X, y, y_now, blk = [], [], [], []

    # 逐段处理：滑窗只在段内取，绝不跨采集空洞
    for grid_ts, grid in resample_segments(ts, feats, rate_hz, max_gap_s):
        lab = selfreport_labels(grid_ts, reports) if label_source == "selfreport" else fea_labels(grid)
        last_start = len(grid) - seq_len - horizon
        for s in range(0, last_start + 1, stride):
            i_now = s + seq_len - 1
            target = lab[i_now + horizon]
            cur = lab[i_now]
            if target < 0 or cur < 0:      # selfreport 尚无标签
                continue
            X.append(grid[s:s + seq_len])
            y.append(int(target))
            y_now.append(int(cur))
            blk.append(block_at(blocks, int(grid_ts[i_now + horizon]), sess_name))
    return X, y, y_now, blk


def assign_splits(subjects, ratios):
    """按受试者稳定划分 train/val/test。

    受试者 <3 人时无法三分，全部落 train（不再伪造空 val/test）——此时唯一诚实的评测
    是 LOSO，见 train_predict.train_predict_loso。
    """
    subs = sorted(subjects)
    n = len(subs)
    if n == 0:
        return {}
    if n < 3:
        return {s: "train" for s in subs}
    # 先保证 val/test 各至少 1 人，余下全给 train（原实现把 train 压到 n-2，
    # 导致 3 人时只有 1 人参与训练）
    n_va = max(1, int(round(n * ratios[1])))
    n_te = max(1, int(round(n * ratios[2])))
    if n_va + n_te > n - 1:
        n_va = n_te = 1
    n_tr = n - n_va - n_te
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
    ap.add_argument("--label-source", choices=["fea", "selfreport"], default="selfreport",
                    help="标签来源：selfreport=最近自评(默认) / fea=规则式表情(与 X 同源，仅调试)")
    ap.add_argument("--allow-circular-labels", action="store_true",
                    help="放行 --label-source fea。该标签由 classify_fea 从同一份 FEA 算出，"
                         "与 X 同源，训出的模型只是在拟合确定性函数，不能作为研究结论。")
    ap.add_argument("--max-gap-s", type=float, default=1.0,
                    help="相邻 FEA 帧间隔超过该秒数即断段，不跨空洞插值（默认 1s）")
    ap.add_argument("--ratios", type=float, nargs=3, default=[0.7, 0.15, 0.15],
                    help="按受试者划分 train val test 比例")
    args = ap.parse_args()

    if args.label_source == "fea" and not args.allow_circular_labels:
        print("[拒绝] --label-source fea 的标签由 classify_fea 从与 X 完全相同的 63 维 FEA 算出，")
        print("       y = f(X) 是确定性函数，真值里没有任何独立于输入的情绪信息，")
        print("       「预测准不准」这一命题无法被证伪。请改用 --label-source selfreport；")
        print("       确需调试再加 --allow-circular-labels。")
        raise SystemExit(2)

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

    # 核对实际采集帧率：与 --rate-hz 差太多说明重采样在硬造/丢弃信息
    rates = []
    for _subject, sess_dir in sessions:
        t, _f = load_fea_csv(os.path.join(sess_dir, "fea.csv"))
        if t is not None:
            r = observed_rate_hz(t)
            if r:
                rates.append(r)
    obs_rate = float(np.median(rates)) if rates else None
    if obs_rate and (obs_rate < args.rate_hz * 0.8 or obs_rate > args.rate_hz * 1.25):
        print(f"[警告] 实测采集帧率约 {obs_rate:.1f}Hz，与 --rate-hz {args.rate_hz:g} 相差较大。"
              f"上采样不会凭空增加信息，下采样会丢弃细节——请对齐采集端与切窗率。")

    cols = ("X", "y", "y_now", "subj", "block")
    buckets = {sp: {c: [] for c in cols} for sp in ("train", "val", "test")}
    per_subject = defaultdict(int)
    for subject, sess_dir in sessions:
        X, y, y_now, blk = slice_session(sess_dir, args.window_s, args.horizon_s, args.rate_hz,
                                         args.stride, args.label_source, args.max_gap_s)
        b = buckets[split_of[subject]]
        b["X"].extend(X); b["y"].extend(y); b["y_now"].extend(y_now)
        b["subj"].extend([subject] * len(X))
        b["block"].extend(f"{subject}/{x}" for x in blk)   # 块 id 全局唯一，避免跨受试者撞名
        per_subject[subject] += len(X)

    os.makedirs(args.out, exist_ok=True)
    seq_len = int(round(args.window_s * args.rate_hz))
    total = 0

    def pack(d):
        return {
            "X": np.asarray(d["X"], dtype="float32"),
            "y": np.asarray(d["y"], dtype="int64"),
            "y_now": np.asarray(d["y_now"], dtype="int64"),
            "subj": np.asarray(d["subj"]),
            "block": np.asarray(d["block"]),
        }

    for sp, d in buckets.items():
        if not d["X"]:
            continue
        np.savez_compressed(os.path.join(args.out, f"{sp}.npz"), **pack(d))
        total += len(d["X"])
        dist = np.bincount(np.asarray(d["y"], dtype="int64"), minlength=len(CLASS_NAMES))
        print(f"[{sp}] {len(d['X'])} 样本 | 类别分布 " +
              ", ".join(f"{c}={int(dist[i])}" for i, c in enumerate(CLASS_NAMES)))

    # all.npz：LOSO 需要跨 split 的全量数据（按受试者分折，不用上面的三分）
    merged = {c: [v for d in buckets.values() for v in d[c]] for c in cols}
    if merged["X"]:
        np.savez_compressed(os.path.join(args.out, "all.npz"), **pack(merged))

    meta = {
        "classes": CLASS_NAMES,
        "window_s": args.window_s,
        "horizon_s": args.horizon_s,
        "rate_hz": args.rate_hz,
        "observed_rate_hz": round(obs_rate, 2) if obs_rate else None,
        "max_gap_s": args.max_gap_s,
        "stride": args.stride,
        "window_overlap": round(1 - args.stride / seq_len, 4) if seq_len else None,
        "seq_len": seq_len,
        "input_dim": FEA_DIM,
        "feature": "fea",
        "label_source": args.label_source,
        "n_subjects": len(subjects),
        "splits": {sp: sorted([s for s, v in split_of.items() if v == sp]) for sp in buckets},
    }
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print(f"\n[完成] 共 {total} 样本 → {args.out}")
    print("受试者划分：" + ", ".join(f"{s}:{split_of[s]}" for s in sorted(subjects)))
    if seq_len and args.stride:
        print(f"[提醒] 相邻滑窗重叠 {(1 - args.stride / seq_len):.1%}，"
              f"window-level 指标会被重复样本灌水——评测请看 block-level 那一行。")
    if len(subjects) < 3:
        print(f"[提醒] 只有 {len(subjects)} 名受试者，无法三分，已全部落 train。"
              "唯一诚实的评测是 LOSO：train_predict_loso('%s')" % args.out)
    else:
        print("下一步：from backend.src.use_predict.train_predict import train_predict; "
              f"train_predict('{args.out}')")
    raise SystemExit(0 if total else 1)


if __name__ == "__main__":
    main()
