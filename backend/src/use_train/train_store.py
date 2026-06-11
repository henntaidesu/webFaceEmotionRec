"""训练运行的磁盘存储：每次训练一个文件夹，记录逐轮指标与滚动权重。

目录结构（config.MODEL_DIR 下，每个 run 一个子目录）：
    Model/<run_id>/
        meta.json        运行元数据（名称/状态/超参/数据集/最佳指标）
        metrics.csv      逐 epoch 一行（loss/acc/F1），刷新或重启后端均不丢失
        epoch_03.pt …    每轮权重，仅保留最近 config.KEEP_CHECKPOINTS 个

供训练页右侧「训练轮次」面板读取（下拉切换不同 run）。
"""
import csv
import json
import logging
import os
import re

from . import config

logger = logging.getLogger(__name__)

_META = "meta.json"
_CSV = "metrics.csv"
_CSV_FIELDS = ["epoch", "train_loss", "train_acc", "val_loss", "val_acc",
               "macro_f1", "best_f1", "is_best", "time"]


def _run_dir(run_id: str):
    return config.MODEL_DIR / run_id


# ── 写入（训练过程调用）──────────────────────────────────────────
def create_run(run_id: str, meta: dict) -> None:
    """开始训练时创建运行目录、写 meta.json、初始化 metrics.csv 表头。"""
    d = _run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    write_meta(run_id, meta)
    csv_path = d / _CSV
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()


def write_meta(run_id: str, meta: dict) -> None:
    with open(_run_dir(run_id) / _META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def update_meta(run_id: str, **kw) -> None:
    """合并更新 meta.json（运行目录已存在时）。"""
    path = _run_dir(run_id) / _META
    meta = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:  # noqa: BLE001
            meta = {}
    meta.update(kw)
    write_meta(run_id, meta)


def append_epoch(run_id: str, row: dict) -> None:
    """逐轮追加一行指标到 metrics.csv。"""
    with open(_run_dir(run_id) / _CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_CSV_FIELDS).writerow(
            {k: row.get(k, "") for k in _CSV_FIELDS})


def save_checkpoint(run_id: str, epoch: int, state: dict) -> str:
    """保存本轮权重为 epoch_NN.pt，并仅保留最近 KEEP_CHECKPOINTS 个。"""
    import torch
    d = _run_dir(run_id)
    path = d / f"epoch_{epoch:02d}.pt"
    torch.save(state, path)
    _prune_checkpoints(run_id)
    return str(path)


def _prune_checkpoints(run_id: str) -> None:
    d = _run_dir(run_id)
    ckpts = []
    for entry in os.scandir(d):
        m = re.fullmatch(r"epoch_(\d+)\.pt", entry.name)
        if m:
            ckpts.append((int(m.group(1)), entry.path))
    ckpts.sort()  # 按 epoch 升序
    for _, path in ckpts[:-config.KEEP_CHECKPOINTS]:
        try:
            os.remove(path)
        except OSError as e:
            logger.warning("删除旧权重失败 %s: %s", path, e)


# ── 读取（API 调用）────────────────────────────────────────────
def _read_meta(run_id: str) -> dict | None:
    path = _run_dir(run_id) / _META
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def list_runs() -> dict:
    """列出全部训练运行（按创建时间倒序），供下拉切换。"""
    runs = []
    if config.MODEL_DIR.is_dir():
        for entry in os.scandir(config.MODEL_DIR):
            if not entry.is_dir():
                continue
            meta = _read_meta(entry.name)
            if meta:
                runs.append({
                    "id": meta.get("id", entry.name),
                    "name": meta.get("name", entry.name),
                    "status": meta.get("status", "unknown"),
                    "created_at": meta.get("created_at", ""),
                    "datasets": meta.get("datasets", []),
                    "total_epochs": meta.get("total_epochs", 0),
                    "best_f1": meta.get("best_f1"),
                    "best_epoch": meta.get("best_epoch"),
                })
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"runs": runs}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def get_run(run_id: str) -> dict | None:
    """返回某次运行的元数据与逐轮指标行。不存在返回 None。"""
    meta = _read_meta(run_id)
    if meta is None:
        return None
    epochs = []
    csv_path = _run_dir(run_id) / _CSV
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                epochs.append({
                    "epoch": int(float(r["epoch"])) if r.get("epoch") else None,
                    "train_loss": _num(r.get("train_loss")),
                    "train_acc": _num(r.get("train_acc")),
                    "val_loss": _num(r.get("val_loss")),
                    "val_acc": _num(r.get("val_acc")),
                    "macro_f1": _num(r.get("macro_f1")),
                    "best_f1": _num(r.get("best_f1")),
                    "is_best": str(r.get("is_best")).lower() in ("1", "true"),
                })
    return {"meta": meta, "epochs": epochs}
