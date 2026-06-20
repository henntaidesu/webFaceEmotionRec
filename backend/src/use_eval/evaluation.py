"""模型评测任务管理（供网页「模型评测」页面调用）。

在指定数据集划分上评测任意一个模型（内置 HSEmotion 或某个自训模型），
逐图推理累计 7×7 混淆矩阵，产出总体准确率、宏 F1、加权 F1 与逐类
precision / recall / F1 / support。

支持「遮挡条件」开关：
  - none：原图评测（不戴 VR 头显的基线表现）
  - vr  ：施加与训练端 VRMask 一致的固定眼带遮挡（佩戴 VR 时的表现）
二者对比即可量化「遮挡掉多少分」「VRMask 训练救回多少」。

与训练子系统一致：单进程内单任务，后台 daemon 线程执行，前端轮询
/api/eval/status 获取进度快照；评测不修改当前推理激活模型，互不干扰。
重型依赖（torch/torchvision/PIL）在评测时才导入。
"""
import logging
import os
import threading
import time
from copy import deepcopy

from .. import config
from ..use_model import labels
from . import eval_store

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOG_MAX = 60

# 评测划分与遮挡条件白名单
SPLIT_CHOICES = ["val", "test"]
OCCLUSION_CHOICES = ["none", "vr"]
# 固定遮挡参数（与 cnn_model.VRMask(train=False) 一致）：黑色眼带，高度 12%~55%
_VR_TOP, _VR_BOTTOM = 0.12, 0.55

_JOB: dict = {
    "status": "idle",        # idle | running | done | error | stopped
    "eval_id": None,
    "name": None,
    "model_id": None,
    "model_name": None,
    "datasets": [],
    "split": None,
    "occlusion": None,
    "step": 0,               # 已处理样本数
    "total_steps": 0,        # 样本总数
    "result": None,          # 完成后填入完整结果
    "log": [],
    "error": None,
    "started_at": None,
    "updated_at": None,
}


# ── 状态读写 ──────────────────────────────────────────────────────
def _update(**kw) -> None:
    with _LOCK:
        _JOB.update(kw)
        _JOB["updated_at"] = time.time()


def _log(msg: str) -> None:
    logger.info("[eval] %s", msg)
    with _LOCK:
        _JOB["log"].append(msg)
        if len(_JOB["log"]) > _LOG_MAX:
            _JOB["log"] = _JOB["log"][-_LOG_MAX:]
        _JOB["updated_at"] = time.time()


def get_status() -> dict:
    with _LOCK:
        return deepcopy(_JOB)


# ── 评测对象枚举 ──────────────────────────────────────────────────
def _count_images(split_dir: str) -> int:
    total = 0
    if not os.path.isdir(split_dir):
        return 0
    for cls in os.scandir(split_dir):
        if cls.is_dir():
            total += sum(1 for f in os.scandir(cls.path) if f.is_file())
    return total


def list_targets() -> dict:
    """返回可评测的模型列表与数据集（含 val/test 计数）。"""
    from ..use_model import model_registry
    models = model_registry.list_models()["models"]
    datasets = []
    for name in config.TRAIN_DATASETS:
        root = config.DATASET_DIR / name
        val_n = _count_images(str(root / "val"))
        test_n = _count_images(str(root / "test"))
        datasets.append({
            "name": name,
            "val": val_n,
            "test": test_n,
            "has_val": val_n > 0,
            "has_test": test_n > 0,
        })
    return {
        "models": models,
        "datasets": datasets,
        "classes": config.TRAIN_CLASSES,
        "splits": SPLIT_CHOICES,
        "occlusions": OCCLUSION_CHOICES,
    }


# ── 任务控制 ──────────────────────────────────────────────────────
def _parse_params(raw: dict) -> dict:
    raw = raw or {}
    model_id = str(raw.get("model_id") or "").strip()
    if not model_id:
        raise ValueError("未选择模型")
    datasets = [x for x in (raw.get("datasets") or []) if x in config.TRAIN_DATASETS]
    if not datasets:
        raise ValueError("未选择有效数据集")
    split = str(raw.get("split", "val"))
    if split not in SPLIT_CHOICES:
        raise ValueError(f"未知数据划分: {split}")
    occlusion = str(raw.get("occlusion", "none"))
    if occlusion not in OCCLUSION_CHOICES:
        raise ValueError(f"未知遮挡条件: {occlusion}")
    return {"model_id": model_id, "datasets": datasets,
            "split": split, "occlusion": occlusion}


def start_eval(raw_params: dict) -> dict:
    """启动评测。已有任务在跑则抛 RuntimeError。"""
    global _THREAD
    with _LOCK:
        if _JOB["status"] == "running":
            raise RuntimeError("已有评测任务正在运行")
    params = _parse_params(raw_params)

    # 解析模型显示名（用于记录与展示）
    from ..use_model import model_registry
    model_name = params["model_id"]
    for m in model_registry.list_models()["models"]:
        if m["id"] == params["model_id"]:
            model_name = m["name"]
            break
    params["model_name"] = model_name

    ts = time.strftime("%Y%m%d_%H%M%S")
    params["eval_id"] = f"eval_{ts}_{params['model_id']}_{params['split']}_{params['occlusion']}"
    params["name"] = (f"{model_name} · {'/'.join(params['datasets'])} "
                      f"· {params['split']} · {params['occlusion']}")
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    params["created_at"] = created_at

    _STOP.clear()
    with _LOCK:
        _JOB.update({
            "status": "running", "eval_id": params["eval_id"], "name": params["name"],
            "model_id": params["model_id"], "model_name": model_name,
            "datasets": params["datasets"], "split": params["split"],
            "occlusion": params["occlusion"], "step": 0, "total_steps": 0,
            "result": None, "log": [], "error": None,
            "started_at": time.time(), "updated_at": time.time(),
        })

    _THREAD = threading.Thread(target=_eval_loop, args=(params,), daemon=True)
    _THREAD.start()
    return {"ok": True, "params": params}


def stop_eval() -> dict:
    with _LOCK:
        running = _JOB["status"] == "running"
    if running:
        _STOP.set()
        _log("收到停止请求，将在当前样本后停止…")
    return {"ok": True, "stopping": running}


# ── 评测核心 ──────────────────────────────────────────────────────
def _apply_vr_occlusion(img_rgb):
    """对 RGB uint8 ndarray 施加固定黑色眼带遮挡（与 VRMask 验证设置一致）。"""
    h = img_rgb.shape[0]
    y1, y2 = int(_VR_TOP * h), int(_VR_BOTTOM * h)
    img_rgb[y1:y2, :, :] = 0
    return img_rgb


def _build_recognizer(model_id: str):
    """为指定模型构建独立识别器（不改动当前推理激活模型）。"""
    from ..use_model import model_registry
    from ..use_model.models import get_models
    models = get_models()
    if model_id == model_registry.BUILTIN_ID:
        return models.emotion, models.device
    ckpt = config.CHECKPOINT_DIR / f"{model_id}.pt"
    if not ckpt.exists():
        raise FileNotFoundError(f"模型权重不存在: {model_id}")
    rec = model_registry.TrainedEmotionRecognizer(str(ckpt), models.device)
    return rec, models.device


def _collect_samples(datasets, split):
    """汇总所选数据集某划分的全部 (路径, 真实类别索引)。类别顺序对齐 TRAIN_CLASSES。"""
    from torchvision import datasets as tvd
    classes = config.TRAIN_CLASSES
    samples = []
    for name in datasets:
        root = config.DATASET_DIR / name / split
        if not os.path.isdir(root):
            continue
        ds = tvd.ImageFolder(str(root))
        assert ds.classes == classes, f"{name}/{split} 类别顺序异常: {ds.classes}"
        samples.extend(ds.samples)  # [(path, target), ...]
    return samples


def _metrics(cm, classes):
    """由混淆矩阵 cm[true, pred] 计算总体与逐类指标。"""
    total = int(cm.sum())
    tp = cm.diagonal()
    acc = float(tp.sum() / total) if total else 0.0
    per_class, f1s, supports = [], [], []
    for i, c in enumerate(classes):
        fp = int(cm[:, i].sum() - tp[i])
        fn = int(cm[i, :].sum() - tp[i])
        sup = int(cm[i, :].sum())
        prec = float(tp[i] / (tp[i] + fp)) if (tp[i] + fp) else 0.0
        rec = float(tp[i] / (tp[i] + fn)) if (tp[i] + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class.append({"class": c, "precision": round(prec, 4),
                          "recall": round(rec, 4), "f1": round(f1, 4), "support": sup})
        f1s.append(f1)
        supports.append(sup)
    macro_f1 = float(sum(f1s) / len(f1s)) if f1s else 0.0
    tot_sup = sum(supports) or 1
    weighted_f1 = float(sum(f * s for f, s in zip(f1s, supports)) / tot_sup)
    return acc, macro_f1, weighted_f1, per_class


def _eval_loop(params: dict) -> None:
    try:
        import numpy as np
        from PIL import Image

        classes = config.TRAIN_CLASSES
        cls_to_idx = {c: i for i, c in enumerate(classes)}
        n = len(classes)

        _log(f"加载模型 {params['model_name']} …")
        recognizer, _ = _build_recognizer(params["model_id"])

        _log(f"汇总数据集 {params['datasets']} 的 {params['split']} 划分 …")
        samples = _collect_samples(params["datasets"], params["split"])
        total = len(samples)
        if total == 0:
            raise RuntimeError(f"所选数据集缺少 {params['split']} 划分或无样本")
        _update(total_steps=total)
        occl = params["occlusion"]
        _log(f"共 {total} 个样本，遮挡条件={occl}，开始逐图推理 …")

        cm = np.zeros((n, n), dtype=np.int64)
        unknown = 0
        for i, (path, target) in enumerate(samples, 1):
            if _STOP.is_set():
                break
            try:
                img = np.array(Image.open(path).convert("RGB"))
            except Exception:  # noqa: BLE001
                continue
            if occl == "vr":
                img = _apply_vr_occlusion(img)
            pred_label, _ = recognizer.predict_emotions(img, logits=False)
            pred_en = labels.to_en(pred_label)
            pred_idx = cls_to_idx.get(pred_en)
            if pred_idx is None:        # 模型输出了 7 类之外的标签（理论上不会发生）
                unknown += 1
                continue
            cm[target, pred_idx] += 1
            if i % 50 == 0 or i == total:
                _update(step=i)

        if _STOP.is_set():
            _update(status="stopped")
            _log("评测已停止")
            return

        acc, macro_f1, weighted_f1, per_class = _metrics(cm, classes)
        result = {
            "id": params["eval_id"], "name": params["name"],
            "model_id": params["model_id"], "model_name": params["model_name"],
            "datasets": params["datasets"], "split": params["split"],
            "occlusion": params["occlusion"], "created_at": params["created_at"],
            "classes": classes, "total": int(cm.sum()),
            "accuracy": round(acc, 4), "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(weighted_f1, 4),
            "per_class": per_class, "confusion_matrix": cm.tolist(),
        }
        if unknown:
            result["unknown_predictions"] = unknown
        eval_store.save(params["eval_id"], result)
        _update(status="done", result=result, step=total)
        _log(f"评测完成：accuracy={acc:.3f} macroF1={macro_f1:.3f}")

    except Exception as e:  # noqa: BLE001
        logger.exception("评测失败")
        _update(status="error", error=str(e))
        _log(f"评测出错: {e}")
