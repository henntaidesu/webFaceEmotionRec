"""会话记录器（SessionRecorder）：接收头显推来的四路时序，落盘为时间轴数据集。

头显 Unity App 经 LAN 把四路信号 POST 到后端：
  - fea        高频 63 维 blendshape 流   → fea.csv        (timestamp_ms, f0..f62)
  - gaze       眼动/注视流                → gaze.csv       (timestamp_ms, gx, gy, gz)
  - stimulus   刺激呈现事件                → stimulus.csv   (onset_ms, image_id, target_emotion, offset_ms, dwell_ms)
  - selfreport 每张图后自评(7类+SAM)      → selfreport.csv (timestamp_ms, image_id, label7, valence, arousal)

落盘目录（时间轴新格式，见任务书 §5）：
  <CAPTURE_DIR>/<subject_id>/<session_id>/{meta.json, fea.csv, gaze.csv, stimulus.csv, selfreport.csv}

设计取舍：ingest 每批「打开→追加→关闭」，不常驻文件句柄，进程崩溃也不丢已写数据；
批量推送下（头显攒若干帧再发）开销可忽略。线程安全由 _LOCK 保护会话表与写盘。
"""
import csv
import json
import re
import threading
import time
from collections import defaultdict

from .. import config
from ..use_model.fea_emotion import OVR_FACE_EXPRESSIONS

FEA_DIM = config.FEA_DIM  # 63
EMOTION_ORDER = config.TRAIN_CLASSES  # angry disgust fear happy neutral sad surprise

# 各路 CSV 的表头
_FEA_HEADER = ["timestamp_ms"] + [f"f{i}" for i in range(FEA_DIM)]
_GAZE_HEADER = ["timestamp_ms", "gaze_x", "gaze_y", "gaze_z"]
_STIMULUS_HEADER = ["onset_ms", "image_id", "target_emotion", "offset_ms", "dwell_ms"]
_SELFREPORT_HEADER = ["timestamp_ms", "image_id", "label7", "valence", "arousal"]

_STREAMS = {
    "fea": ("fea.csv", _FEA_HEADER),
    "gaze": ("gaze.csv", _GAZE_HEADER),
    "stimulus": ("stimulus.csv", _STIMULUS_HEADER),
    "selfreport": ("selfreport.csv", _SELFREPORT_HEADER),
}

_LOCK = threading.Lock()
# session_id -> {"dir": Path, "subject": str, "counts": {stream: int}, "started_ms": int, "meta": dict}
_active: dict = {}


def _safe(s: str, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))
    return s or fallback


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rel(path) -> str:
    """相对仓库根展示；CAPTURE_DIR 若被改到根外则退回绝对路径。"""
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def _ensure_header(path, header):
    """文件不存在则写表头。"""
    if not path.exists():
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)


# ── 会话生命周期 ──────────────────────────────────────────────────
def start_session(body: dict) -> dict:
    """建立一个采集会话。

    body: {"subject_id": str, "session_id"?: str, "fea_rate_hz"?, "gaze_rate_hz"?,
           "sync_offset_ms"?: int, "note"?: str}
    返回 {"ok", "session_id", "dir"}。
    """
    body = body or {}
    subject = _safe(body.get("subject_id"), "anon")
    session_id = body.get("session_id")
    if session_id:
        session_id = _safe(session_id, "")
    if not session_id:
        session_id = "s" + time.strftime("%Y%m%d_%H%M%S")

    with _LOCK:
        sess_dir = config.CAPTURE_DIR / subject / session_id
        # 同秒重开会话时避免撞名
        n = 1
        while sess_dir.exists() and session_id not in _active:
            session_id = f"{session_id}_{n}"
            sess_dir = config.CAPTURE_DIR / subject / session_id
            n += 1
        sess_dir.mkdir(parents=True, exist_ok=True)

        for _stream, (fname, header) in _STREAMS.items():
            _ensure_header(sess_dir / fname, header)

        started = _now_ms()
        _active[session_id] = {
            "dir": sess_dir,
            "subject": subject,
            "counts": defaultdict(int),
            "started_ms": started,
            "meta": {
                "subject_id": subject,
                "session_id": session_id,
                "created_ms": started,
                "sync_offset_ms": int(body.get("sync_offset_ms") or 0),
                "fea_rate_hz": body.get("fea_rate_hz"),
                "gaze_rate_hz": body.get("gaze_rate_hz"),
                "emotion_order": EMOTION_ORDER,
                "fea_dim": FEA_DIM,
                "fea_names": OVR_FACE_EXPRESSIONS,
                "device": body.get("device", "Meta Quest Pro"),
                "app_build": body.get("app_build"),
                "note": body.get("note"),
            },
        }
    return {"ok": True, "session_id": session_id, "dir": _rel(sess_dir)}


def _rows_fea(items, errors):
    """items: [[ts, f0..f62], ...] 或 [{"timestamp_ms":..,"blendshapes":[63]}, ...]。"""
    for it in items:
        if isinstance(it, dict):
            ts = it.get("timestamp_ms")
            bs = it.get("blendshapes")
        elif isinstance(it, (list, tuple)) and len(it) == FEA_DIM + 1:
            ts, bs = it[0], it[1:]
        else:
            errors.append("fea 行格式非法")
            continue
        if bs is None or len(bs) != FEA_DIM:
            errors.append("fea 维度应为 63")
            continue
        yield [int(ts) if ts is not None else _now_ms()] + [round(float(x), 5) for x in bs]


def _rows_gaze(items, errors):
    for it in items:
        if isinstance(it, dict):
            row = [it.get("timestamp_ms"), it.get("gaze_x"), it.get("gaze_y"), it.get("gaze_z")]
        elif isinstance(it, (list, tuple)) and len(it) >= 4:
            row = list(it[:4])
        else:
            errors.append("gaze 行格式非法")
            continue
        yield [int(row[0]) if row[0] is not None else _now_ms()] + [float(x) for x in row[1:4]]


def _rows_stimulus(items, errors):
    for it in items:
        if not isinstance(it, dict):
            errors.append("stimulus 需为对象")
            continue
        yield [
            int(it.get("onset_ms") or _now_ms()),
            str(it.get("image_id") or ""),
            str(it.get("target_emotion") or ""),
            it.get("offset_ms"),
            it.get("dwell_ms"),
        ]


def _rows_selfreport(items, errors):
    for it in items:
        if not isinstance(it, dict):
            errors.append("selfreport 需为对象")
            continue
        label = str(it.get("label7") or "")
        if label and label not in EMOTION_ORDER:
            errors.append(f"selfreport 非法标签 {label}")
        yield [
            int(it.get("timestamp_ms") or _now_ms()),
            str(it.get("image_id") or ""),
            label,
            it.get("valence"),
            it.get("arousal"),
        ]


_ROW_BUILDERS = {
    "fea": _rows_fea,
    "gaze": _rows_gaze,
    "stimulus": _rows_stimulus,
    "selfreport": _rows_selfreport,
}


def ingest(body: dict) -> dict:
    """追加一批四路事件。

    body: {"session_id": str, "fea": [...], "gaze": [...], "stimulus": [...], "selfreport": [...]}
    每路可缺省。返回本批各路写入条数与错误。
    """
    body = body or {}
    session_id = _safe(body.get("session_id"), "")
    with _LOCK:
        sess = _active.get(session_id)
        if sess is None:
            raise KeyError(session_id)
        sess_dir = sess["dir"]
        written, errors = {}, []
        for stream, (fname, _header) in _STREAMS.items():
            items = body.get(stream)
            if not items:
                continue
            rows = list(_ROW_BUILDERS[stream](items, errors))
            if rows:
                with open(sess_dir / fname, "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerows(rows)
                sess["counts"][stream] += len(rows)
                written[stream] = len(rows)
    return {"ok": True, "written": written, "errors": errors, "counts": dict(sess["counts"])}


def stop_session(body: dict) -> dict:
    """收尾：写 meta.json（含各路计数、时长、sync_offset）。"""
    body = body or {}
    session_id = _safe(body.get("session_id"), "")
    with _LOCK:
        sess = _active.pop(session_id, None)
        if sess is None:
            raise KeyError(session_id)
        meta = sess["meta"]
        meta["counts"] = dict(sess["counts"])
        meta["ended_ms"] = _now_ms()
        meta["duration_s"] = round((meta["ended_ms"] - sess["started_ms"]) / 1000, 2)
        if body.get("sync_offset_ms") is not None:
            meta["sync_offset_ms"] = int(body["sync_offset_ms"])
        with open(sess["dir"] / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    return {"ok": True, "session_id": session_id, "meta": meta}


def list_sessions() -> dict:
    """列出已落盘的会话（扫 CAPTURE_DIR，含进行中的活动会话）。"""
    out = []
    root = config.CAPTURE_DIR
    if root.is_dir():
        for meta_path in sorted(root.glob("*/*/meta.json")):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    m = json.load(f)
                out.append({
                    "subject_id": m.get("subject_id"),
                    "session_id": m.get("session_id"),
                    "counts": m.get("counts", {}),
                    "duration_s": m.get("duration_s"),
                    "dir": _rel(meta_path.parent),
                })
            except (OSError, json.JSONDecodeError):
                continue
    with _LOCK:
        active_ids = [
            {"subject_id": s["subject"], "session_id": sid, "counts": dict(s["counts"]), "active": True}
            for sid, s in _active.items()
        ]
    return {"sessions": out, "active": active_ids}
