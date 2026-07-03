"""把 Quest Pro 原始采集流对齐、打包成 quest_pro_capture_spec.md 规定的样本格式。

采集时通常分两路独立落盘（时间戳不完全对齐）：
  1. 头显侧 63 维 blendshape 流（JSONL：每行 {"timestamp_ms":int,"blendshapes":[63]}
     或 CSV：timestamp_ms,bs0,...,bs62）。
  2. 外接相机帧（图像文件 + 帧索引 CSV：timestamp_ms,filename）。

本工具按时间戳做最近邻配对（可加固定偏移 offset、容差 tol），给每对生成一个样本：
  <out>/<split>/<sample_id>.json  +  <sample_id>_central.jpg
标签来自 --label（整批同一情绪）或 --events（按时间段给标签）。

产物可直接被 DataSet/prepare_quest_pro.py 校验、被 notebook 的 build_manifest 读取。

用法示例：
  python DataSet/sync_quest_pro_capture.py \
      --blendshapes fea.jsonl --frames-index frames.csv --frames-root ./frames \
      --label happy --subject p07 --split train --out DataSet/quest_pro_vr \
      --offset-ms 0 --tol-ms 50
"""
import argparse
import bisect
import csv
import json
import os
import shutil

FEA_DIM = 63

# 与 quest_pro_capture_spec.md §5 / prepare_quest_pro.py 一致
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


def load_blendshapes(path):
    """返回按时间戳升序的 [(ts_ms:int, [63]float), ...]。支持 JSONL 或 CSV。"""
    records = []
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jsonl", ".ndjson"):
        with open(path, "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                ts = int(d["timestamp_ms"])
                bs = [float(x) for x in d["blendshapes"]]
                if len(bs) != FEA_DIM:
                    raise ValueError(f"{path}:{ln} blendshapes 维度 {len(bs)}≠{FEA_DIM}")
                records.append((ts, bs))
    else:  # CSV: timestamp_ms,bs0..bs62
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for ln, row in enumerate(reader, 2):
                if not row:
                    continue
                ts = int(float(row[0]))
                bs = [float(x) for x in row[1:1 + FEA_DIM]]
                if len(bs) != FEA_DIM:
                    raise ValueError(f"{path}:{ln} blendshapes 列数 {len(bs)}≠{FEA_DIM}")
                records.append((ts, bs))
    records.sort(key=lambda r: r[0])
    return records


def load_frames(index_path):
    """帧索引 CSV：timestamp_ms,filename。返回按时间戳升序 [(ts_ms, filename), ...]。"""
    frames = []
    with open(index_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or len(row) < 2:
                continue
            frames.append((int(float(row[0])), row[1].strip()))
    frames.sort(key=lambda r: r[0])
    return frames


def load_events(path):
    """事件 CSV：start_ms,end_ms,label。返回 [(start,end,label), ...]。"""
    events = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or len(row) < 3:
                continue
            events.append((int(float(row[0])), int(float(row[1])), row[2].strip()))
    return events


def label_for(ts, events, single_label):
    if single_label:
        return single_label
    for start, end, lab in events:
        if start <= ts <= end:
            return lab
    return None


def nearest(sorted_ts, keys, target):
    """在升序 sorted_ts 中找与 target 最近的索引；keys 为对应键列表。"""
    i = bisect.bisect_left(keys, target)
    best, best_d = None, None
    for j in (i - 1, i):
        if 0 <= j < len(keys):
            d = abs(keys[j] - target)
            if best_d is None or d < best_d:
                best, best_d = j, d
    return best, best_d


def main():
    ap = argparse.ArgumentParser(description="Quest Pro 原始流时间对齐 → 采集样本")
    ap.add_argument("--blendshapes", required=True, help="63 维 FEA 流（.jsonl 或 .csv）")
    ap.add_argument("--frames-index", required=True, help="帧索引 CSV：timestamp_ms,filename")
    ap.add_argument("--frames-root", required=True, help="帧图像所在目录")
    ap.add_argument("--out", required=True, help="输出采集根目录")
    ap.add_argument("--split", default="train")
    ap.add_argument("--subject", required=True, help="受试者 id，如 p07")
    ap.add_argument("--label", default=None, help="整批同一情绪（与 --events 二选一）")
    ap.add_argument("--events", default=None, help="事件 CSV：start_ms,end_ms,label")
    ap.add_argument("--offset-ms", type=int, default=0, help="相机时钟相对头显的偏移（camera_ts += offset）")
    ap.add_argument("--tol-ms", type=int, default=50, help="最近邻配对容差，超出则丢弃该帧")
    ap.add_argument("--copy", action="store_true", help="复制图像（默认硬链接）")
    args = ap.parse_args()

    if not args.label and not args.events:
        print("[错误] 需提供 --label 或 --events 之一。")
        raise SystemExit(2)

    fea = load_blendshapes(args.blendshapes)
    frames = load_frames(args.frames_index)
    events = load_events(args.events) if args.events else []
    if not fea or not frames:
        print("[错误] blendshape 或帧索引为空。")
        raise SystemExit(2)

    fea_ts = [t for t, _ in fea]
    out_split = os.path.join(args.out, args.split)
    os.makedirs(out_split, exist_ok=True)

    matched, dropped_tol, dropped_label, dropped_img = 0, 0, 0, 0
    seq = 0
    for cam_ts, fname in frames:
        aligned = cam_ts + args.offset_ms
        j, d = nearest(fea, fea_ts, aligned)
        if j is None or d > args.tol_ms:
            dropped_tol += 1
            continue
        lab = label_for(aligned, events, args.label)
        if lab is None:
            dropped_label += 1
            continue
        src_img = os.path.join(args.frames_root, fname)
        if not os.path.exists(src_img):
            dropped_img += 1
            continue

        sample_id = f"{args.subject}_e{seq:04d}"
        seq += 1
        dst_img = os.path.join(out_split, f"{sample_id}_central.jpg")
        if os.path.exists(dst_img):
            os.remove(dst_img)
        if args.copy:
            shutil.copy2(src_img, dst_img)
        else:
            try:
                os.link(src_img, dst_img)
            except OSError:
                shutil.copy2(src_img, dst_img)

        meta = {
            "sample_id": sample_id,
            "label": lab,
            "image_central": os.path.basename(dst_img),
            "blendshapes": fea[j][1],
            "blendshape_names": OVR_FACE_EXPRESSIONS,
            "device": "Meta Quest Pro",
            "sdk": "Meta XR Movement SDK - Face Tracking (63)",
            "timestamp_ms": fea[j][0],
            "sync": {"camera_ts_ms": cam_ts, "offset_ms": args.offset_ms, "match_delta_ms": d},
        }
        with open(os.path.join(out_split, f"{sample_id}.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        matched += 1

    print(f"配对成功 {matched} | 超容差丢弃 {dropped_tol} | 无标签丢弃 {dropped_label} | 缺图丢弃 {dropped_img}")
    print(f"输出 → {out_split}")
    print("下一步：python DataSet/prepare_quest_pro.py --root", args.out, "校验并导出 ImageFolder。")


if __name__ == "__main__":
    main()
