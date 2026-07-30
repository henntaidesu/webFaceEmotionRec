"""训练情绪预测（时序）模型：读 D1 切好的滑窗数据集 → 训 GRU → 存权重+sidecar。

数据集由 DataSet/prepare_timeline_dataset.py 产出：
    <dataset_dir>/{meta.json, train.npz, val.npz[, test.npz], all.npz}
    *.npz: X (N, seq_len, F) f32, y (N,) i64（未来 horizon 时刻的 7 类索引），
           y_now (N,) i64（窗末当前标签）, subj (N,) 受试者, block (N,) 刺激块

**评测协议**（docs/研究逻辑修复方案_情绪预测线_2026-07-20.md §3）：
任何准确率都必须与三条基线同表呈现，否则没有意义——
  chance      分层随机
  majority    恒预测训练集多数类
  persistence 直接拿窗末当前标签当预测
模型打不过 persistence 就没有价值。指标同时给 window-level 与 **block-level**
（每个刺激块聚合成一个预测），因为相邻滑窗重叠可达 96%，window-level 会被灌水。

受试者 <3 人时用 train_predict_loso() 做留一受试者交叉验证，而不是伪造一个 val。

用法（脚本或后端调用）：
    from ..use_predict.train_predict import train_predict, train_predict_loso
    train_predict("DataSet/timeline_sliced", {"epochs": 15})
    train_predict_loso("DataSet/timeline_sliced", {"epochs": 15})

torch 惰性导入。产物落 config.PREDICT_CHECKPOINT_DIR，供 predictor.SequencePredictor 加载。
"""
import json
import logging
import time
from collections import Counter, defaultdict
from pathlib import Path

from .. import config

logger = logging.getLogger(__name__)

EN = config.TRAIN_CLASSES


def _macro_f1(cm):
    """cm[t][p] 混淆矩阵 → macro-F1（纯 Python，避免引 sklearn）。"""
    c = len(cm)
    f1s = []
    for k in range(c):
        tp = cm[k][k]
        fp = sum(cm[t][k] for t in range(c)) - tp
        fn = sum(cm[k][p] for p in range(c)) - tp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return sum(f1s) / c


def _score(y_true, y_pred):
    """(acc, macro_f1)。"""
    cm = [[0] * len(EN) for _ in range(len(EN))]
    for t, p in zip(y_true, y_pred):
        cm[int(t)][int(p)] += 1
    total = sum(sum(r) for r in cm)
    acc = sum(cm[k][k] for k in range(len(EN))) / total if total else 0.0
    return acc, _macro_f1(cm)


def _block_score(y_true, y_pred, blocks):
    """block-level：每个刺激块内多数投票聚合成一个预测，再算指标。

    相邻滑窗重叠极高，window-level 指标等于把同一段观测重复计数。块级才是独立单元。
    """
    if blocks is None:
        return None
    agg = defaultdict(lambda: ([], []))
    for t, p, b in zip(y_true, y_pred, blocks):
        agg[b][0].append(int(t))
        agg[b][1].append(int(p))
    bt, bp = [], []
    for t_list, p_list in agg.values():
        bt.append(Counter(t_list).most_common(1)[0][0])
        bp.append(Counter(p_list).most_common(1)[0][0])
    acc, f1 = _score(bt, bp)
    return {"acc": round(acc, 4), "macro_f1": round(f1, 4), "n_blocks": len(bt)}


def _baselines(tr_y, va_y, va_y_now, va_blocks, seed=0):
    """chance / majority / persistence 三条基线，与模型同表对比。"""
    import numpy as np

    out = {}
    rng = np.random.default_rng(seed)

    # chance：按训练集类别先验分层随机
    prior = np.bincount(tr_y, minlength=len(EN)).astype("float64")
    prior = prior / prior.sum() if prior.sum() else np.full(len(EN), 1 / len(EN))
    pred = rng.choice(len(EN), size=len(va_y), p=prior)
    acc, f1 = _score(va_y, pred)
    out["chance"] = {"acc": round(acc, 4), "macro_f1": round(f1, 4),
                     "block": _block_score(va_y, pred, va_blocks)}

    # majority：恒预测训练集多数类
    maj = int(np.bincount(tr_y, minlength=len(EN)).argmax())
    pred = np.full(len(va_y), maj)
    acc, f1 = _score(va_y, pred)
    out["majority"] = {"acc": round(acc, 4), "macro_f1": round(f1, 4), "class": EN[maj],
                       "block": _block_score(va_y, pred, va_blocks)}

    # persistence：直接拿窗末当前标签当预测（最强的朴素基线）
    if va_y_now is not None:
        acc, f1 = _score(va_y, va_y_now)
        out["persistence"] = {"acc": round(acc, 4), "macro_f1": round(f1, 4),
                              "block": _block_score(va_y, va_y_now, va_blocks)}
    else:
        out["persistence"] = None
    return out


def _load_npz(path):
    """→ dict(X, y, y_now?, subj?, block?)；缺 y_now/subj/block 的旧数据集也能读。"""
    import numpy as np

    if not path.exists():
        return None
    z = np.load(path, allow_pickle=False)
    d = {"X": z["X"].astype("float32"), "y": z["y"].astype("int64")}
    for k in ("y_now", "subj", "block"):
        if k in z.files:
            d[k] = z[k].astype("int64") if k == "y_now" else z[k]
    return d


def _fit(tr, va, params, dmeta, device_str=None):
    """训一个 GRU，返回 (best_state, best_metrics, val_pred)。纯训练，不落盘。"""
    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    from .seq_model import build_gru

    epochs = max(1, int(params.get("epochs", 15)))   # 防 epochs<1 使 best_state 为 None
    batch = int(params.get("batch_size", 64))
    lr = float(params.get("lr", 1e-3))
    hidden = int(params.get("hidden", 128))
    layers = int(params.get("layers", 1))
    # 有 GPU 就用；REQUIRE_CUDA 只用于"要求但不可用时报错"，不该反过来禁用 GPU。
    device = torch.device(device_str or ("cuda" if torch.cuda.is_available() else "cpu"))
    input_dim = tr["X"].shape[2]

    def loader(d, shuffle):
        ds = TensorDataset(torch.from_numpy(d["X"]), torch.from_numpy(d["y"]))
        return DataLoader(ds, batch_size=batch, shuffle=shuffle)

    tl, vl = loader(tr, True), loader(va, False)

    counts = np.bincount(tr["y"], minlength=len(EN)).astype("float32")
    weights = torch.tensor(counts.sum() / (counts + 1e-6), dtype=torch.float32).to(device)

    model = build_gru(input_dim, len(EN), hidden=hidden, layers=layers).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    crit = nn.CrossEntropyLoss(weight=weights)

    best_f1, best_state, best_pred = -1.0, None, None
    for ep in range(1, epochs + 1):
        model.train()
        for xb, yb in tl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            crit(model(xb), yb).backward()
            opt.step()

        model.eval()
        preds = []
        with torch.no_grad():
            for xb, _yb in vl:
                preds.append(model(xb.to(device)).argmax(1).cpu().numpy())
        pred = np.concatenate(preds) if preds else np.zeros(0, dtype="int64")
        acc, f1 = _score(va["y"], pred)
        logger.info("[predict-train] epoch %d/%d val_acc=%.3f macro_f1=%.3f", ep, epochs, acc, f1)
        if f1 > best_f1:
            best_f1, best_pred = f1, pred
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    acc, f1 = _score(va["y"], best_pred)
    return best_state, {"acc": round(acc, 4), "macro_f1": round(f1, 4),
                        "block": _block_score(va["y"], best_pred, va.get("block"))}, best_pred


def _verdict(model_m, base):
    """一句话结论：模型有没有打过 persistence。块级优先，退回窗级。"""
    p = base.get("persistence")
    if not p:
        return "无 persistence 基线（数据集缺 y_now），无法判断模型是否有价值"
    mk = model_m.get("block") or model_m
    pk = p.get("block") or p
    d = mk["macro_f1"] - pk["macro_f1"]
    if d > 0:
        return f"模型 macro-F1 高于 persistence {d:+.4f}（{'block' if model_m.get('block') else 'window'}-level）"
    return (f"模型 macro-F1 未超过 persistence（{d:+.4f}）——按研究逻辑修复方案 §3，"
            "此模型没有价值，应缩短 horizon 或更换构念，不要对外称『实现了情绪预测』")


def train_predict(dataset_dir: str, params: dict = None) -> dict:
    """训练并保存一个序列预测模型，返回 sidecar（含三条基线与 block-level 指标）。"""
    params = params or {}
    ddir = Path(dataset_dir)
    meta_path = ddir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"找不到数据集 meta：{meta_path}（先跑 DataSet/prepare_timeline_dataset.py）")
    with open(meta_path, encoding="utf-8") as f:
        dmeta = json.load(f)

    tr = _load_npz(ddir / "train.npz")
    if tr is None:
        raise FileNotFoundError(f"缺 train.npz：{ddir}")
    va = _load_npz(ddir / "val.npz")
    if va is None:
        # 绝不静默拿训练集当验证集——那样报出的 val_acc 是训练集指标，模型选择也在训练集上做
        raise FileNotFoundError(
            f"缺 val.npz：{ddir}。受试者不足 3 人时 prepare_timeline_dataset.py 不会划出验证集，"
            "请改用 train_predict_loso() 做留一受试者交叉验证，而不是拿训练集当验证集。")

    if dmeta.get("label_source") == "fea":
        logger.warning("[predict-train] 数据集标签源为 fea（与 X 同源的规则标签），"
                       "训出的指标不能作为研究结论，仅供调试。")

    best_state, model_m, _pred = _fit(tr, va, params, dmeta)
    base = _baselines(tr["y"], va["y"], va.get("y_now"), va.get("block"))
    verdict = _verdict(model_m, base)
    logger.info("[predict-train] %s", verdict)

    return _save(best_state, tr["X"].shape[2], params, dmeta, ddir, model_m, base, verdict,
                 protocol="holdout")


def train_predict_loso(dataset_dir: str, params: dict = None) -> dict:
    """留一受试者交叉验证：每折留一名受试者做验证，其余训练。

    小样本（<3 人无法三分、或固定 3 人 test 功效过低）时这是唯一诚实的评测方式。
    返回汇总 sidecar；不保存单折权重（折模型只用于评测，不用于上线）。
    """
    import numpy as np

    params = params or {}
    ddir = Path(dataset_dir)
    with open(ddir / "meta.json", encoding="utf-8") as f:
        dmeta = json.load(f)

    alld = _load_npz(ddir / "all.npz")
    if alld is None:
        raise FileNotFoundError(f"缺 all.npz：{ddir}（请用新版 prepare_timeline_dataset.py 重新切窗）")
    if "subj" not in alld:
        raise ValueError("all.npz 缺 subj 字段，无法按受试者分折（请用新版 prepare_timeline_dataset.py 重新切窗）")

    subjects = sorted(set(alld["subj"].tolist()))
    if len(subjects) < 2:
        raise ValueError(f"LOSO 至少需要 2 名受试者，当前 {len(subjects)} 名")

    folds = []
    for held in subjects:
        m = alld["subj"] == held
        sub = lambda d, mask: {k: v[mask] for k, v in d.items()}      # noqa: E731
        tr, va = sub(alld, ~m), sub(alld, m)
        if len(tr["y"]) == 0 or len(va["y"]) == 0:
            continue
        _state, model_m, _pred = _fit(tr, va, params, dmeta)
        base = _baselines(tr["y"], va["y"], va.get("y_now"), va.get("block"))
        folds.append({"held_out": str(held), "n_val": int(len(va["y"])),
                      "model": model_m, "baselines": base})
        logger.info("[predict-loso] 留 %s：model_f1=%.3f persistence_f1=%s",
                    held, model_m["macro_f1"],
                    base["persistence"]["macro_f1"] if base["persistence"] else "n/a")

    if not folds:
        raise ValueError("LOSO 没有产出任何有效折")

    def mean(path):
        vals = []
        for fd in folds:
            cur = fd
            for k in path:
                cur = (cur or {}).get(k) if isinstance(cur, dict) else None
            if isinstance(cur, (int, float)):
                vals.append(float(cur))
        return round(sum(vals) / len(vals), 4) if vals else None

    summary = {
        "protocol": "loso",
        "n_folds": len(folds),
        "subjects": [str(s) for s in subjects],
        "model": {"acc": mean(["model", "acc"]), "macro_f1": mean(["model", "macro_f1"]),
                  "block_macro_f1": mean(["model", "block", "macro_f1"])},
        "baselines": {
            b: {"acc": mean(["baselines", b, "acc"]),
                "macro_f1": mean(["baselines", b, "macro_f1"]),
                "block_macro_f1": mean(["baselines", b, "block", "macro_f1"])}
            for b in ("chance", "majority", "persistence")
        },
        "folds": folds,
    }
    m_f1 = summary["model"]["block_macro_f1"] or summary["model"]["macro_f1"] or 0.0
    p_f1 = (summary["baselines"]["persistence"]["block_macro_f1"]
            or summary["baselines"]["persistence"]["macro_f1"])
    summary["verdict"] = (
        f"LOSO 均值 macro-F1 {m_f1:.4f} vs persistence {p_f1:.4f}："
        + ("模型有增益" if p_f1 is not None and m_f1 > p_f1 else "模型未超过 persistence，无价值"))
    logger.info("[predict-loso] %s", summary["verdict"])

    # 报告写到 reports/ 子目录：PREDICT_CHECKPOINT_DIR 根下的 *.json 会被
    # predictor._load_sidecars 当成模型 sidecar 扫描，评测报告不是模型。
    rep_dir = config.PREDICT_CHECKPOINT_DIR / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    out = rep_dir / ("loso_" + time.strftime("%Y%m%d_%H%M%S") + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    logger.info("[predict-loso] 报告 → %s", out)
    return summary


def _save(best_state, input_dim, params, dmeta, ddir, model_m, base, verdict, protocol):
    import torch

    model_id = "pred_" + time.strftime("%Y%m%d_%H%M%S")
    ckpt = {"model": best_state, "input_dim": input_dim,
            "hidden": int(params.get("hidden", 128)), "layers": int(params.get("layers", 1)),
            "classes": EN}
    torch.save(ckpt, config.PREDICT_CHECKPOINT_DIR / f"{model_id}.pt")
    sidecar = {
        "id": model_id,
        "name": params.get("name", model_id),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "protocol": protocol,
        "window_s": dmeta.get("window_s"),
        "horizon_s": dmeta.get("horizon_s"),
        "rate_hz": dmeta.get("rate_hz"),
        "seq_len": dmeta.get("seq_len"),
        "input_dim": input_dim,
        "label_source": dmeta.get("label_source"),
        "val_acc": model_m["acc"],
        "macro_f1": model_m["macro_f1"],
        "block_level": model_m.get("block"),
        "baselines": base,
        "verdict": verdict,
        "dataset": str(ddir),
    }
    with open(config.PREDICT_CHECKPOINT_DIR / f"{model_id}.json", "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=1)
    logger.info("[predict-train] 保存 → %s（val_acc=%.3f macro_f1=%.3f）",
                model_id, model_m["acc"], model_m["macro_f1"])
    return sidecar
