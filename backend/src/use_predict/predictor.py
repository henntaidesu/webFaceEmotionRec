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
from ..safe_path import is_safe_id
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
        # 模型只会预测其训练时的固定 horizon；响应按此标注，勿回显请求值（否则闭环时序错标）。
        self.horizon_s = float(meta.get("horizon_s", config.PREDICT_HORIZON_S))
        self._torch = torch
        self._device = device

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.model = build_gru(ckpt.get("input_dim", FEA_DIM), len(EN),
                               hidden=ckpt.get("hidden", 128), layers=ckpt.get("layers", 1))
        self.model.load_state_dict(ckpt["model"])
        self.model.eval().to(device)

    # 允许的窗口时长偏差：模型学到的是固定时间尺度，偏差过大就不该硬塞
    _SPAN_TOL = (0.7, 1.4)

    def _resample(self, fea):
        """按**时间戳**把窗口重采样到 seq_len 帧，覆盖最后 window_s 秒。

        原实现用 np.linspace(0, n-1, seq_len) 按下标插值，完全不看时间戳：同为 60 帧、
        一个跨 2 秒一个跨 10 秒的窗口会得到完全相同的张量，模型训练时学到的时间尺度
        在推理端被抹掉。这里改为按真实时间轴插值，并校验窗口时长。
        """
        import numpy as np

        ts = np.array([t for t, _bs in fea], dtype="float64")
        arr = np.array([bs for _ts, bs in fea], dtype="float32")
        if len(arr) < 2:
            raise ValueError("窗口至少需要 2 帧 FEA")
        span_s = (ts[-1] - ts[0]) / 1000.0
        lo, hi = self._SPAN_TOL
        if span_s <= 0:
            raise ValueError("窗口时间戳非法（时长为 0）")
        if not (self.window_s * lo <= span_s <= self.window_s * hi):
            raise ValueError(
                f"窗口时长 {span_s:.2f}s 与模型训练窗口 {self.window_s:g}s 不匹配"
                f"（允许 {self.window_s * lo:.2f}~{self.window_s * hi:.2f}s）")

        # 以窗末为基准回溯 window_s 秒，落在采集起点之前的部分夹到起点
        grid = np.linspace(ts[-1] - self.window_s * 1000.0, ts[-1], self.seq_len)
        grid = np.clip(grid, ts[0], ts[-1])
        out = np.empty((self.seq_len, arr.shape[1]), dtype="float32")
        for k in range(arr.shape[1]):
            out[:, k] = np.interp(grid, ts, arr[:, k])
        return out

    def predict(self, window: dict, horizon_s: float):
        # horizon_s（请求值）被忽略：模型输出对应其训练 horizon（self.horizon_s）。
        fea = _parse_fea((window or {}).get("fea"))
        if not fea:
            return _neutral_response(self.horizon_s)
        try:
            x_np = self._resample(fea)
        except ValueError as e:
            # 窗口不合规时退回规则式基线，并如实标注——绝不把拉伸过的窗喂给模型
            logger.warning("窗口不合规，回退规则式基线：%s", e)
            r = _RULE.predict(window, self.horizon_s)
            r["fallback"] = "rule"
            r["fallback_reason"] = str(e)
            return r
        torch = self._torch
        x = torch.from_numpy(x_np).unsqueeze(0).to(self._device)
        with torch.no_grad():
            probs = torch.softmax(self.model(x)[0], dim=0).cpu().numpy()
        scores = {en: float(probs[i]) for i, en in enumerate(EN)}
        return _response(scores, fea[-1][0], self.horizon_s)


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
                    m = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取预测模型元数据失败 %s: %s", entry.name, e)
                continue
            # 目录里可能有非模型 JSON（如 LOSO 评测报告），没有 id 就不是模型 sidecar
            if isinstance(m, dict) and m.get("id"):
                out.append(m)
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
    if not is_safe_id(model_id):     # 阻断路径穿越（../ 等）→ 视为不存在
        raise KeyError(model_id)
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
