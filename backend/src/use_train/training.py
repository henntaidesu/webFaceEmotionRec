"""图像 FER 模型训练任务管理（供网页「模型训练」页面调用）。

单进程内单任务：后台 daemon 线程跑训练，主线程通过状态快照轮询进度。
训练目标是纯图像情感分类（EfficientNet-B2，7 类），数据用已下载的 ImageFolder 数据集。
重型依赖（torch/torchvision/timm）在训练时才导入，避免拖慢后端启动。
"""
import logging
import os
import threading
import time
from copy import deepcopy

from .. import config
from ..use_model import model_registry
from . import train_store

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOG_MAX = 60

_JOB: dict = {
    "status": "idle",          # idle | running | stopping | done | error | stopped
    "params": None,
    "model_id": None,
    "model_name": None,
    "epoch": 0,
    "total_epochs": 0,
    "step": 0,                 # 当前 epoch 内已处理批次
    "total_steps": 0,          # 当前 epoch 总批次
    "phase": None,             # train | val
    "running_loss": None,      # 当前 epoch 实时平均损失
    "train_loss": None,
    "train_acc": None,
    "val_loss": None,
    "val_acc": None,
    "macro_f1": None,
    "best_f1": None,
    "epochs": [],              # 已完成各轮指标行（供右侧「训练轮次」实时显示）
    "log": [],
    "error": None,
    "ckpt_path": None,
    "started_at": None,
    "updated_at": None,
}


# ── 状态读写 ──────────────────────────────────────────────────────
def _update(**kw) -> None:
    with _LOCK:
        _JOB.update(kw)
        _JOB["updated_at"] = time.time()


def _log(msg: str) -> None:
    logger.info("[train] %s", msg)
    with _LOCK:
        _JOB["log"].append(msg)
        if len(_JOB["log"]) > _LOG_MAX:
            _JOB["log"] = _JOB["log"][-_LOG_MAX:]
        _JOB["updated_at"] = time.time()


def get_status() -> dict:
    with _LOCK:
        return deepcopy(_JOB)


# ── 数据集枚举 ────────────────────────────────────────────────────
def _count_images(split_dir: str) -> int:
    total = 0
    if not os.path.isdir(split_dir):
        return 0
    for cls in os.scandir(split_dir):
        if cls.is_dir():
            total += sum(1 for f in os.scandir(cls.path) if f.is_file())
    return total


def list_datasets() -> dict:
    """返回可训练数据集及其 train/val 计数（不存在的标记 available=False）。"""
    out = []
    for name in config.TRAIN_DATASETS:
        root = config.DATASET_DIR / name
        train_n = _count_images(str(root / "train"))
        val_n = _count_images(str(root / "val"))
        out.append({
            "name": name,
            "train": train_n,
            "val": val_n,
            "available": train_n > 0 and val_n > 0,
        })
    return {"datasets": out, "classes": config.TRAIN_CLASSES}


# ── 任务控制 ──────────────────────────────────────────────────────
def _parse_params(raw: dict) -> dict:
    d = dict(config.TRAIN_DEFAULTS)
    raw = raw or {}
    datasets = raw.get("datasets") or []
    datasets = [x for x in datasets if x in config.TRAIN_DATASETS]
    if not datasets:
        raise ValueError("未选择有效数据集")
    backbone = str(raw.get("backbone", d["backbone"]))
    if backbone not in config.TRAIN_BACKBONE_CHOICES:
        raise ValueError(f"未知主干网络: {backbone}")
    p = {
        "datasets": datasets,
        "backbone": backbone,
        "vr_occlusion": bool(raw.get("vr_occlusion", d["vr_occlusion"])),
        "epochs": int(raw.get("epochs", d["epochs"])),
        "batch_size": int(raw.get("batch_size", d["batch_size"])),
        "lr": float(raw.get("lr", d["lr"])),
        "weight_decay": float(raw.get("weight_decay", d["weight_decay"])),
        "freeze_epochs": int(raw.get("freeze_epochs", d["freeze_epochs"])),
        "img_size": int(raw.get("img_size", d["img_size"])),
        "num_workers": int(raw.get("num_workers", d["num_workers"])),
    }
    if p["epochs"] < 1 or p["batch_size"] < 1:
        raise ValueError("epochs 与 batch_size 必须 ≥ 1")
    return p


def start_training(raw_params: dict) -> dict:
    """启动训练。已有任务在跑则抛 RuntimeError。"""
    global _THREAD
    with _LOCK:
        if _JOB["status"] in ("running", "stopping"):
            raise RuntimeError("已有训练任务正在运行")
    params = _parse_params(raw_params)

    # 每次训练 = 一个独立保存的模型，生成唯一 id 与显示名
    ts = time.strftime("%Y%m%d_%H%M%S")
    params["model_id"] = f"fer_{ts}_{'-'.join(params['datasets'])}"
    raw_name = (raw_params or {}).get("name")
    params["name"] = (raw_name.strip() if isinstance(raw_name, str) and raw_name.strip()
                      else f"FER {'/'.join(params['datasets'])} {time.strftime('%m-%d %H:%M')}")

    _STOP.clear()
    with _LOCK:
        _JOB.update({
            "status": "running", "params": params,
            "model_id": params["model_id"], "model_name": params["name"],
            "epoch": 0, "total_epochs": params["epochs"],
            "step": 0, "total_steps": 0, "phase": None, "running_loss": None,
            "train_loss": None, "train_acc": None, "val_loss": None,
            "val_acc": None, "macro_f1": None, "best_f1": None, "epochs": [],
            "log": [], "error": None, "ckpt_path": None,
            "started_at": time.time(), "updated_at": time.time(),
        })

    # 每次训练 = Model/<run_id>/ 一个独立目录（meta.json + metrics.csv + 滚动权重）
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    train_store.create_run(params["model_id"], {
        "id": params["model_id"], "name": params["name"], "status": "running",
        "created_at": created_at, "datasets": params["datasets"],
        "params": {k: params[k] for k in (
            "backbone", "vr_occlusion", "epochs", "batch_size", "lr",
            "weight_decay", "freeze_epochs", "img_size", "num_workers")},
        "total_epochs": params["epochs"], "best_f1": None, "best_epoch": None,
    })

    _THREAD = threading.Thread(target=_train_loop, args=(params,), daemon=True)
    _THREAD.start()
    return {"ok": True, "params": params}


def stop_training() -> dict:
    with _LOCK:
        running = _JOB["status"] in ("running", "stopping")
        if running:
            _JOB["status"] = "stopping"
    if running:
        _STOP.set()
        _log("收到停止请求，将在当前批次后停止…")
    return {"ok": True, "stopping": running}


# ── 训练循环 ──────────────────────────────────────────────────────
def _build_loaders(params):
    import torch
    from torch.utils.data import ConcatDataset, DataLoader
    from torchvision import datasets, transforms

    from .cnn_model import VRMask

    sz = params["img_size"]
    vr = params["vr_occlusion"]
    mean, std = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
    # VR 遮挡增强：训练随机遮挡上半脸；验证固定遮挡，使指标反映佩戴 VR 时的精度
    train_tf = transforms.Compose([
        transforms.Resize((sz, sz)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2),
        transforms.ToTensor(),
        *([VRMask(train=True)] if vr else []),
        transforms.Normalize(mean, std),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((sz, sz)),
        transforms.ToTensor(),
        *([VRMask(train=False)] if vr else []),
        transforms.Normalize(mean, std),
    ])

    def load(split, tf):
        parts = []
        for name in params["datasets"]:
            d = config.DATASET_DIR / name / split
            if os.path.isdir(d):
                ds = datasets.ImageFolder(str(d), transform=tf)
                # 强制类别顺序与 config.TRAIN_CLASSES 一致（各数据集已是字母序，故天然一致）
                assert ds.classes == config.TRAIN_CLASSES, (
                    f"{name}/{split} 类别顺序异常: {ds.classes}")
                parts.append(ds)
        if not parts:
            raise RuntimeError(f"所选数据集缺少 {split} 划分")
        return parts[0] if len(parts) == 1 else ConcatDataset(parts)

    train_ds, val_ds = load("train", train_tf), load("val", eval_tf)
    nw = params["num_workers"]
    persistent = nw > 0
    train_loader = DataLoader(train_ds, batch_size=params["batch_size"], shuffle=True,
                              num_workers=nw, drop_last=True,
                              pin_memory=True, persistent_workers=persistent)
    val_loader = DataLoader(val_ds, batch_size=params["batch_size"], shuffle=False,
                            num_workers=nw,
                            pin_memory=True, persistent_workers=persistent)
    return train_ds, train_loader, val_loader


def _class_weights(train_ds, device):
    import torch
    n = len(config.TRAIN_CLASSES)
    counts = torch.zeros(n)
    # ImageFolder 有 .targets；ConcatDataset 需遍历子集
    subsets = train_ds.datasets if hasattr(train_ds, "datasets") else [train_ds]
    for ds in subsets:
        for t in ds.targets:
            counts[t] += 1
    counts = counts.clamp(min=1)
    return (counts.sum() / (n * counts)).to(device), counts


def _metrics(cm):
    n = cm.shape[0]
    tp = cm.diagonal()
    acc = tp.sum() / max(cm.sum(), 1)
    f1s = []
    for c in range(n):
        fp = cm[:, c].sum() - tp[c]
        fn = cm[c, :].sum() - tp[c]
        prec = tp[c] / (tp[c] + fp) if (tp[c] + fp) else 0.0
        rec = tp[c] / (tp[c] + fn) if (tp[c] + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return float(acc), float(sum(f1s) / len(f1s))


def _run_epoch(model, loader, criterion, optimizer, device, train: bool, scaler):
    import numpy as np
    import torch
    model.train(train)
    n = len(config.TRAIN_CLASSES)
    cm = np.zeros((n, n), dtype=np.int64)
    total_loss, total = 0.0, 0
    use_amp = device.type == "cuda"
    phase = "train" if train else "val"
    steps = len(loader)
    _update(phase=phase, step=0, total_steps=steps)
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for i, (img, label) in enumerate(loader, 1):
            if _STOP.is_set():
                return None
            img = img.to(device, non_blocking=True)
            label = label.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits = model(img)
                loss = criterion(logits, label)
            if train:
                optimizer.zero_grad()
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total_loss += loss.item() * label.size(0)
            total += label.size(0)
            for t, p in zip(label.cpu().numpy(), logits.argmax(1).cpu().numpy()):
                cm[t, p] += 1
            # 每 10 批刷新一次实时进度（前端每秒轮询）
            if i % 10 == 0 or i == steps:
                if train:
                    _update(step=i, running_loss=round(total_loss / max(total, 1), 4))
                else:
                    _update(step=i)
    acc, f1 = _metrics(cm)
    return total_loss / max(total, 1), acc, f1


def _train_loop(params: dict) -> None:
    try:
        import torch
        import torch.nn as nn
        from ..use_model.device import select_device
        from .cnn_model import VR_CNN_ID, create_model

        device = select_device()
        backbone = params["backbone"]
        pretrained = backbone != VR_CNN_ID  # 自定义 CNN 无预训练权重，从零训练
        _log(f"加载数据集 {params['datasets']} …")
        train_ds, train_loader, val_loader = _build_loaders(params)
        if params["vr_occlusion"]:
            _log("已启用 VR 头显遮挡增强（验证集按固定遮挡评估）")
        _log(f"训练样本 {len(train_ds)}，开始构建模型 {backbone}")

        weights, counts = _class_weights(train_ds, device)
        model = create_model(backbone, len(config.TRAIN_CLASSES),
                             pretrained=pretrained).to(device)
        criterion = nn.CrossEntropyLoss(weight=weights)
        optimizer = torch.optim.AdamW(model.parameters(), lr=params["lr"],
                                      weight_decay=params["weight_decay"])
        use_cuda = device.type == "cuda"
        scaler = torch.amp.GradScaler("cuda", enabled=use_cuda)
        if use_cuda:
            torch.backends.cudnn.benchmark = True  # 固定尺寸输入，自动选最快卷积算法

        def set_frozen(frozen):
            # timm 分类头名为 classifier；冻结其余主干参数
            for name, p in model.named_parameters():
                if not name.startswith("classifier"):
                    p.requires_grad = not frozen

        best_f1 = 0.0
        best_epoch = 0
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        ckpt_path = str(config.CHECKPOINT_DIR / f"{params['model_id']}.pt")

        for epoch in range(1, params["epochs"] + 1):
            if _STOP.is_set():
                break
            # 仅预训练主干需要先冻结微调；从零训练的自定义 CNN 全程放开
            set_frozen(pretrained and epoch <= params["freeze_epochs"])

            tr = _run_epoch(model, train_loader, criterion, optimizer, device, True, scaler)
            if tr is None:
                break
            va = _run_epoch(model, val_loader, criterion, optimizer, device, False, scaler)
            if va is None:
                break
            tr_loss, tr_acc, _ = tr
            va_loss, va_acc, va_f1 = va
            is_best = va_f1 > best_f1
            if is_best:
                best_f1, best_epoch = va_f1, epoch

            row = {
                "epoch": epoch,
                "train_loss": round(tr_loss, 4), "train_acc": round(tr_acc, 4),
                "val_loss": round(va_loss, 4), "val_acc": round(va_acc, 4),
                "macro_f1": round(va_f1, 4), "best_f1": round(best_f1, 4),
                "is_best": is_best,
            }
            with _LOCK:
                _JOB["epochs"].append(row)
            _update(epoch=epoch, train_loss=row["train_loss"], train_acc=row["train_acc"],
                    val_loss=row["val_loss"], val_acc=row["val_acc"],
                    macro_f1=row["macro_f1"], best_f1=row["best_f1"])
            _log(f"[{epoch}/{params['epochs']}] "
                 f"train_acc={tr_acc:.3f} val_acc={va_acc:.3f} macroF1={va_f1:.3f}")

            # 持久化逐轮指标 + 本轮权重（滚动保留最近 N 个）到 Model/<run_id>/
            train_store.append_epoch(params["model_id"], {**row, "time": time.strftime("%H:%M:%S")})
            train_store.save_checkpoint(params["model_id"], epoch, {
                "model": model.state_dict(), "classes": config.TRAIN_CLASSES,
                "backbone": backbone, "params": params,
                "epoch": epoch, "val_f1": va_f1})
            train_store.update_meta(params["model_id"], best_f1=round(best_f1, 4),
                                    best_epoch=best_epoch)

            if is_best:
                torch.save({"model": model.state_dict(),
                            "classes": config.TRAIN_CLASSES,
                            "backbone": backbone,
                            "params": params, "epoch": epoch, "val_f1": va_f1},
                           ckpt_path)
                # 写元数据 sidecar，供推理端列表/切换
                model_registry.register_trained({
                    "id": params["model_id"], "name": params["name"], "type": "trained",
                    "backbone": backbone, "classes": config.TRAIN_CLASSES,
                    "img_size": params["img_size"], "datasets": params["datasets"],
                    "epochs": params["epochs"], "best_epoch": epoch,
                    "val_acc": round(va_acc, 4), "val_f1": round(va_f1, 4),
                    "macro_f1": round(va_f1, 4), "created_at": created_at,
                    "ckpt": f"{params['model_id']}.pt",
                })
                _update(best_f1=round(best_f1, 4), ckpt_path=ckpt_path)
                _log(f"  ✓ 保存最佳模型 macroF1={va_f1:.3f}")

        if _STOP.is_set():
            _update(status="stopped")
            train_store.update_meta(params["model_id"], status="stopped")
            _log("训练已停止")
        else:
            _update(status="done")
            train_store.update_meta(params["model_id"], status="done")
            _log(f"训练完成，最佳 macroF1={best_f1:.3f}")

    except Exception as e:  # noqa: BLE001
        logger.exception("训练失败")
        _update(status="error", error=str(e))
        try:
            train_store.update_meta(params["model_id"], status="error")
        except Exception:  # noqa: BLE001
            pass
        _log(f"训练出错: {e}")
