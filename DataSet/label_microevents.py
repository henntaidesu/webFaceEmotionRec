"""从 FEA 时序自动标注微表情事件（onset / apex / offset），写 microevents.csv。

取消外接相机后，微表情只能靠 Quest Pro 高帧率 FEA 捕捉（见任务书 §2、M-D）。
本脚本对每个会话的 fea.csv：
  1. 逐帧算「表情强度」= 各情绪 FACS 组激活的最大值（排除 neutral）。
  2. 用带迟滞的阈值检测强度「爆发段」：升过 onset 阈 → 峰值(apex) → 跌破 offset 阈。
  3. 每段记 onset/apex/offset 时间、时长、峰值情绪；时长 ≤ micro_max_s 标记为微表情。

输出：<session_dir>/microevents.csv
    onset_ms, apex_ms, offset_ms, duration_ms, emotion, peak_intensity, is_micro, verified
（verified 留 0 供人工校验。）

用法：
    python DataSet/label_microevents.py --root Capture              # 处理全部会话
    python DataSet/label_microevents.py --session Capture/p07/s01   # 处理单个会话
"""
import argparse
import csv
import glob
import os

import numpy as np

CLASS_NAMES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
FEA_DIM = 63

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
_NON_NEUTRAL = [c for c in CLASS_NAMES if c != "neutral"]


def load_fea_csv(path):
    ts, feats = [], []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
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


def group_scores(feats):
    """(n,63) → (n, len(_NON_NEUTRAL)) 各情绪组激活。"""
    out = np.zeros((len(feats), len(_NON_NEUTRAL)), dtype="float32")
    for ci, c in enumerate(_NON_NEUTRAL):
        cols = [_IDX[name] for name in _AU_GROUPS[c]]
        out[:, ci] = feats[:, cols].mean(axis=1)
    return out


def detect_events(ts, feats, onset_thr, offset_thr, micro_max_s, min_dur_s):
    scores = group_scores(feats)
    intensity = scores.max(axis=1)
    dom = scores.argmax(axis=1)

    events = []
    i, n = 0, len(ts)
    while i < n:
        if intensity[i] < onset_thr:
            i += 1
            continue
        # 爆发段起点：回溯到升过 offset 阈的地方作为 onset
        onset = i
        while onset > 0 and intensity[onset - 1] >= offset_thr:
            onset -= 1
        # 前推到跌破 offset 阈作为 offset
        j = i
        while j + 1 < n and intensity[j + 1] >= offset_thr:
            j += 1
        offset = j
        seg = slice(onset, offset + 1)
        apex = onset + int(np.argmax(intensity[seg]))
        dur_ms = int(ts[offset] - ts[onset])
        if dur_ms >= min_dur_s * 1000:
            events.append({
                "onset_ms": int(ts[onset]),
                "apex_ms": int(ts[apex]),
                "offset_ms": int(ts[offset]),
                "duration_ms": dur_ms,
                "emotion": _NON_NEUTRAL[int(dom[apex])],
                "peak_intensity": round(float(intensity[apex]), 4),
                "is_micro": 1 if dur_ms <= micro_max_s * 1000 else 0,
                "verified": 0,
            })
        i = offset + 1
    return events


def process_session(sess_dir, args):
    fea_path = os.path.join(sess_dir, "fea.csv")
    if not os.path.exists(fea_path):
        return None
    ts, feats = load_fea_csv(fea_path)
    if ts is None or len(ts) < 3:
        return None
    events = detect_events(ts, feats, args.onset_thr, args.offset_thr,
                           args.micro_max_s, args.min_dur_s)
    out_path = os.path.join(sess_dir, "microevents.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["onset_ms", "apex_ms", "offset_ms", "duration_ms",
                    "emotion", "peak_intensity", "is_micro", "verified"])
        for e in events:
            w.writerow([e["onset_ms"], e["apex_ms"], e["offset_ms"], e["duration_ms"],
                        e["emotion"], e["peak_intensity"], e["is_micro"], e["verified"]])
    micro = sum(e["is_micro"] for e in events)
    print(f"{sess_dir}: {len(events)} 事件（微表情 {micro}）→ {os.path.basename(out_path)}")
    return len(events)


def main():
    ap = argparse.ArgumentParser(description="FEA 时序 → 微表情 onset/apex/offset 标注")
    ap.add_argument("--root", default=None, help="采集根目录（处理全部 <subject>/<session>）")
    ap.add_argument("--session", default=None, help="单个会话目录")
    ap.add_argument("--onset-thr", type=float, default=0.15, help="爆发起始强度阈（升过判为表情起）")
    ap.add_argument("--offset-thr", type=float, default=0.08, help="回落阈（迟滞，< onset-thr）")
    ap.add_argument("--micro-max-s", type=float, default=0.5, help="≤此时长标记为微表情")
    ap.add_argument("--min-dur-s", type=float, default=0.04, help="小于此时长的抖动丢弃")
    args = ap.parse_args()

    if not args.root and not args.session:
        print("[错误] 需提供 --root 或 --session 之一。")
        raise SystemExit(2)
    if args.offset_thr >= args.onset_thr:
        print("[错误] --offset-thr 必须小于 --onset-thr（迟滞）。")
        raise SystemExit(2)

    sess_dirs = []
    if args.session:
        sess_dirs = [args.session]
    else:
        for fea_path in sorted(glob.glob(os.path.join(args.root, "*", "*", "fea.csv"))):
            sess_dirs.append(os.path.dirname(fea_path))

    if not sess_dirs:
        print("[错误] 没找到任何 fea.csv。")
        raise SystemExit(2)

    total = 0
    done = 0
    for d in sess_dirs:
        r = process_session(d, args)
        if r is not None:
            total += r
            done += 1
    print(f"\n[完成] {done} 个会话，共 {total} 个表情事件。")
    raise SystemExit(0 if done else 1)


if __name__ == "__main__":
    main()
