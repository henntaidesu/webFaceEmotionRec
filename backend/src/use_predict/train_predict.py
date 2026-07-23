"""训练情绪预测（时序）模型：读 D1 切好的滑窗数据集 → 训 GRU → 存权重+sidecar。

数据集由 DataSet/prepare_timeline_dataset.py 产出：
    <dataset_dir>/{meta.json, train.npz, val.npz[, test.npz]}
    *.npz: X (N, seq_len, F) float32, y (N,) int64（未来 horizon 时刻的 7 类索引）

用法（脚本或后端调用）：
    from ..use_predict.train_predict import train_predict
    train_predict("DataSet/timeline_sliced", {"epochs": 15})

torch 惰性导入。产物落 config.PREDICT_CHECKPOINT_DIR，供 predictor.SequencePredictor 加载。
"""
import json
import logging
import time
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


def train_predict(dataset_dir: str, params: dict = None) -> dict:
    """训练并保存一个序列预测模型，返回 {"id", "val_acc", "macro_f1", ...}。"""
    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    from .seq_model import build_gru

    params = params or {}
    ddir = Path(dataset_dir)
    meta_path = ddir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"找不到数据集 meta：{meta_path}（先跑 DataSet/prepare_timeline_dataset.py）")
    with open(meta_path, encoding="utf-8") as f:
        dmeta = json.load(f)

    def load(split):
        p = ddir / f"{split}.npz"
        if not p.exists():
            return None
        z = np.load(p)
        return z["X"].astype("float32"), z["y"].astype("int64")

    tr = load("train")
    va = load("val") or tr
    if tr is None:
        raise FileNotFoundError(f"缺 train.npz：{ddir}")

    input_dim = tr[0].shape[2]
    epochs = max(1, int(params.get("epochs", 15)))     # 防 epochs<1 使 best_state 保持 None 存出空 checkpoint
    batch = int(params.get("batch_size", 64))
    lr = float(params.get("lr", 1e-3))
    hidden = int(params.get("hidden", 128))
    layers = int(params.get("layers", 1))
    # 有 GPU 就用；REQUIRE_CUDA 只用于"要求但不可用时报错"，不该反过来禁用 GPU。
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def loader(data, shuffle):
        X, y = data
        ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
        return DataLoader(ds, batch_size=batch, shuffle=shuffle)

    tl, vl = loader(tr, True), loader(va, False)

    # 类别权重（缓解不均衡）
    counts = np.bincount(tr[1], minlength=len(EN)).astype("float32")
    weights = torch.tensor((counts.sum() / (counts + 1e-6)), dtype=torch.float32).to(device)

    model = build_gru(input_dim, len(EN), hidden=hidden, layers=layers).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    crit = nn.CrossEntropyLoss(weight=weights)

    best_f1, best_state, best_acc = -1.0, None, 0.0
    for ep in range(1, epochs + 1):
        model.train()
        for xb, yb in tl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            opt.step()

        # 验证
        model.eval()
        cm = [[0] * len(EN) for _ in range(len(EN))]
        correct = total = 0
        with torch.no_grad():
            for xb, yb in vl:
                pred = model(xb.to(device)).argmax(1).cpu().numpy()
                for t, p in zip(yb.numpy(), pred):
                    cm[int(t)][int(p)] += 1
                    correct += int(t == p)
                    total += 1
        acc = correct / total if total else 0.0
        f1 = _macro_f1(cm)
        logger.info("[predict-train] epoch %d/%d val_acc=%.3f macro_f1=%.3f", ep, epochs, acc, f1)
        if f1 > best_f1:
            best_f1, best_acc = f1, acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model_id = "pred_" + time.strftime("%Y%m%d_%H%M%S")
    ckpt = {
        "model": best_state, "input_dim": input_dim, "hidden": hidden, "layers": layers,
        "classes": EN,
    }
    torch.save(ckpt, config.PREDICT_CHECKPOINT_DIR / f"{model_id}.pt")
    sidecar = {
        "id": model_id,
        "name": params.get("name", model_id),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window_s": dmeta.get("window_s"),
        "horizon_s": dmeta.get("horizon_s"),
        "rate_hz": dmeta.get("rate_hz"),
        "seq_len": dmeta.get("seq_len"),
        "input_dim": input_dim,
        "val_acc": round(best_acc, 4),
        "macro_f1": round(best_f1, 4),
        "dataset": str(ddir),
    }
    with open(config.PREDICT_CHECKPOINT_DIR / f"{model_id}.json", "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=1)
    logger.info("[predict-train] 保存 → %s（val_acc=%.3f macro_f1=%.3f）", model_id, best_acc, best_f1)
    return sidecar
