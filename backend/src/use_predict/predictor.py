"""情绪预测服务：规则式基线 + 训练模型注册表 + /api/predict 分发。

- RulePredictor      无需训练：对窗口内 FEA 逐帧规则式分类，取近端均值 + 线性趋势外推到未来。
- SequencePredictor  加载 train_predict 训出的 GRU（<id>.pt + <id>.json 于 PREDICT_CHECKPOINT_DIR）。
- 两者 predict(window, horizon_s) 返回结构与图像识别路径同构（见任务书 §6）。

响应字段：dominant_en / dominant(中文) / emotions{中文:pct} / horizon_s / pred_time_ms
          / trajectory(可选) / suggest_next_emotion(闭环反馈用)。
"""
import json
import logging
import os
import threading
import time

from .. import config
from ..use_model import labels
from ..use_model.fea_emotion import classify_fea

logger = logging.getLogger(__name__)

EN = config.TRAIN_CLASSES                       # angry disgust fear happy neutral sad surprise
FEA_DIM = config.FEA_DIM
_ZH2EN = {labels.to_zh(en): en for en in EN}
_NEUTRAL_IDX = EN.index("neutral")

RULE_ID = "rule"
RULE_NAME = "规则式基线（无需训练）"

_LOCK = threading.Lock()
_active_id = RULE_ID
_cache: dict = {}   # id -> SequencePredictor


# ── 窗口解析 ──────────────────────────────────────────────────────
def _parse_fea(items):
    """把 fea 列表统一成按时间戳升序的 [(ts_ms:int, [63]float), ...]。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            ts, bs = it.get("timestamp_ms"), it.get("blendshapes")
        elif isinstance(it, (list, tuple)) and len(it) == FEA_DIM + 1:
            ts, bs = it[0], it[1:]
        else:
            continue
        if bs is None or len(bs) != FEA_DIM:
            continue
        out.append((int(ts) if ts is not None else 0, [float(x) for x in bs]))
    out.sort(key=lambda r: r[0])
    return out


def _frame_dist(bs):
    """单帧 63 维 → 7 类概率 dict（en→0~1），复用规则式 classify_fea。"""
    r = classify_fea(bs)
    return {_ZH2EN[zh]: pct / 100.0 for zh, pct in r["emotions"].items()}


def _response(scores_en, last_ts, horizon_s, trajectory=None):
    """把 en→分数 dict 归一化为标准响应结构。"""
    total = sum(max(0.0, v) for v in scores_en.values()) or 1.0
    emotions_zh = {labels.to_zh(en): round(max(0.0, scores_en.get(en, 0.0)) / total * 100, 2) for en in EN}
    dominant_en = max(EN, key=lambda e: scores_en.get(e, 0.0))
    return {
        "success": True,
        "horizon_s": horizon_s,
        "pred_time_ms": int((last_ts or time.time() * 1000) + horizon_s * 1000),
        "dominant_en": dominant_en,
        "dominant": labels.to_zh(dominant_en),
        "emotions": emotions_zh,
        "suggest_next_emotion": dominant_en,   # 闭环：默认建议下一张刺激对应预测主情绪
        "trajectory": trajectory,
    }


def _neutral_response(horizon_s):
    scores = {en: (1.0 if en == "neutral" else 0.0) for en in EN}
    return _response(scores, None, horizon_s)


# ── 规则式基线：近端均值 + 线性趋势外推 ────────────────────────────
class RulePredictor:
    id = RULE_ID
    name = RULE_NAME

    def predict(self, window: dict, horizon_s: float):
        fea = _parse_fea((window or {}).get("fea"))
        if not fea:
            return _neutral_response(horizon_s)

        dists = [_frame_dist(bs) for _ts, bs in fea]
        n = len(dists)
        last_ts = fea[-1][0]

        # 近端均值：取后半段（至少 1 帧）
        recent = dists[max(0, n // 2):]
        cur = {en: sum(d[en] for d in recent) / len(recent) for en in EN}

        if n < 4:
            return _response(cur, last_ts, horizon_s)   # 太短，只给当前分布

        # 趋势：后 1/3 均值 - 前 1/3 均值
        k = max(1, n // 3)
        early = {en: sum(d[en] for d in dists[:k]) / k for en in EN}
        late = {en: sum(d[en] for d in dists[-k:]) / k for en in EN}
        span_s = max(0.5, (fea[-1][0] - fea[0][0]) / 1000.0)
        gain = min(2.0, horizon_s / span_s)            # 外推放大，封顶避免发散

        future = {en: cur[en] + (late[en] - early[en]) * gain for en in EN}
        # 轨迹：中间插几步（onset→未来）
        steps = 3
        traj = []
        for s in range(1, steps + 1):
            frac = s / steps
            pt = {en: cur[en] + (late[en] - early[en]) * gain * frac for en in EN}
            t = int(last_ts + horizon_s * 1000 * frac)
            tot = sum(max(0.0, v) for v in pt.values()) or 1.0
            traj.append({"t_ms": t, "emotions": {labels.to_zh(en): round(max(0.0, pt[en]) / tot * 100, 2) for en in EN}})
        return _response(future, last_ts, horizon_s, trajectory=traj)


# ── 训练模型（GRU）识别器 ─────────────────────────────────────────
class SequencePredictor:
    def __init__(self, ckpt_path: str, meta: dict, device):
        import torch

        from .seq_model import build_gru

        self.id = meta["id"]
        self.name = meta.get("name", meta["id"])
        self.window_s = float(meta.get("window_s", config.PREDICT_WINDOW_S))
        self.rate_hz = float(meta.get("rate_hz", 30))
        self.seq_len = int(meta.get("seq_len", round(self.window_s * self.rate_hz)))
        self._torch = torch
        self._device = device

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.model = build_gru(ckpt.get("input_dim", FEA_DIM), len(EN),
                               hidden=ckpt.get("hidden", 128), layers=ckpt.get("layers", 1))
        self.model.load_state_dict(ckpt["model"])
        self.model.eval().to(device)

    def _resample(self, fea):
        """把不定长 fea 窗口重采样/补齐到固定 seq_len 帧（每帧 63 维）。"""
        import numpy as np
        arr = np.array([bs for _ts, bs in fea], dtype="float32")  # (n, 63)
        n = len(arr)
        idx = np.linspace(0, n - 1, self.seq_len)
        lo = np.floor(idx).astype(int)
        hi = np.minimum(lo + 1, n - 1)
        frac = (idx - lo)[:, None]
        return arr[lo] * (1 - frac) + arr[hi] * frac              # (seq_len, 63)

    def predict(self, window: dict, horizon_s: float):
        fea = _parse_fea((window or {}).get("fea"))
        if not fea:
            return _neutral_response(horizon_s)
        torch = self._torch
        x = torch.from_numpy(self._resample(fea)).unsqueeze(0).to(self._device)
        with torch.no_grad():
            probs = torch.softmax(self.model(x)[0], dim=0).cpu().numpy()
        scores = {en: float(probs[i]) for i, en in enumerate(EN)}
        return _response(scores, fea[-1][0], horizon_s)


# ── sidecar / 注册表 ──────────────────────────────────────────────
def _sidecar_path(model_id: str):
    return config.PREDICT_CHECKPOINT_DIR / f"{model_id}.json"


def _load_sidecars():
    out = []
    d = config.PREDICT_CHECKPOINT_DIR
    if not d.is_dir():
        return out
    for entry in os.scandir(d):
        if entry.name.endswith(".json"):
            try:
                with open(entry.path, encoding="utf-8") as f:
                    out.append(json.load(f))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取预测模型元数据失败 %s: %s", entry.name, e)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def list_predictors() -> dict:
    items = [{"id": RULE_ID, "name": RULE_NAME, "type": "rule",
              "macro_f1": None, "created_at": None, "active": _active_id == RULE_ID}]
    for m in _load_sidecars():
        items.append({"id": m["id"], "name": m.get("name", m["id"]), "type": "trained",
                      "window_s": m.get("window_s"), "horizon_s": m.get("horizon_s"),
                      "macro_f1": m.get("macro_f1"), "created_at": m.get("created_at"),
                      "active": _active_id == m["id"]})
    return {"active": _active_id, "predictors": items}


_RULE = RulePredictor()


def _get(model_id, device):
    if model_id == RULE_ID:
        return _RULE
    if model_id in _cache:
        return _cache[model_id]
    sidecar = _sidecar_path(model_id)
    ckpt = config.PREDICT_CHECKPOINT_DIR / f"{model_id}.pt"
    if not (sidecar.exists() and ckpt.exists()):
        raise KeyError(model_id)
    with open(sidecar, encoding="utf-8") as f:
        meta = json.load(f)
    _cache[model_id] = SequencePredictor(str(ckpt), meta, device)
    return _cache[model_id]


def set_active(model_id: str, device) -> dict:
    global _active_id
    try:
        _get(model_id, device)     # rule 直接过；trained 触发加载校验
    except KeyError:
        raise
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"加载预测模型失败: {e}") from e
    with _LOCK:
        _active_id = model_id
    return {"ok": True, "active": _active_id}


def predict(body: dict, device=None) -> dict:
    """/api/predict 主入口。body 见任务书 §6。"""
    body = body or {}
    horizon_s = float(body.get("horizon_s") or config.PREDICT_HORIZON_S)
    window = body.get("window") or {}
    try:
        rec = _get(_active_id, device)
    except Exception as e:  # noqa: BLE001 —— 活动模型加载不了则退回规则式
        logger.warning("预测模型不可用，回退规则式：%s", e)
        rec = _RULE
    return rec.predict(window, horizon_s)
