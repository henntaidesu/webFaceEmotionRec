"""评测结果的磁盘存储：每次评测一个文件夹，记录完整结果。

目录结构（config.EVAL_DIR 下，每个评测一个子目录）：
    Eval/<eval_id>/
        result.json      评测元数据 + 总体指标 + 逐类指标 + 7×7 混淆矩阵

供评测页左侧「评测记录」下拉读取历史，右侧表格/热力图渲染混淆矩阵。
重启后端后历史结果不丢失。
"""
import json
import logging
import os
import shutil

from .. import config

logger = logging.getLogger(__name__)

_RESULT = "result.json"


def _eval_dir(eval_id: str):
    return config.EVAL_DIR / eval_id


def save(eval_id: str, result: dict) -> None:
    """写入一次评测的完整结果。"""
    d = _eval_dir(eval_id)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / _RESULT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


def _read(eval_id: str) -> dict | None:
    path = _eval_dir(eval_id) / _RESULT
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def list_evals() -> dict:
    """列出全部评测记录（按创建时间倒序），仅含摘要字段供下拉显示。"""
    evals = []
    if config.EVAL_DIR.is_dir():
        for entry in os.scandir(config.EVAL_DIR):
            if not entry.is_dir():
                continue
            r = _read(entry.name)
            if r:
                evals.append({
                    "id": r.get("id", entry.name),
                    "name": r.get("name", entry.name),
                    "model_name": r.get("model_name"),
                    "datasets": r.get("datasets", []),
                    "split": r.get("split"),
                    "occlusion": r.get("occlusion"),
                    "accuracy": r.get("accuracy"),
                    "macro_f1": r.get("macro_f1"),
                    "total": r.get("total"),
                    "created_at": r.get("created_at", ""),
                })
    evals.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return {"evals": evals}


def get_eval(eval_id: str) -> dict | None:
    """返回某次评测的完整结果（含混淆矩阵与逐类指标）。不存在返回 None。"""
    return _read(eval_id)


def delete_eval(eval_id: str) -> bool:
    """删除一次评测记录目录。不存在返回 False。"""
    d = _eval_dir(eval_id)
    if not d.is_dir():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True
