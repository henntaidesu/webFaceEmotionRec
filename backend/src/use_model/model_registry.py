"""推理用情感模型注册表：列出 / 切换 / 删除可用模型。

可用模型 = 内置 HSEmotion（enet_b2_7） + 每次网页训练保存的自训模型。
自训模型以 `<id>.pt`（权重）+ `<id>.json`（元数据 sidecar）存于 config.CHECKPOINT_DIR。
推理时 emotion.py 通过 get_active_recognizer() 取当前激活模型。

TrainedEmotionRecognizer 与 hsemotion 的 HSEmotionRecognizer 接口兼容：
  - 属性 idx_to_class: {idx: 类名}
  - 方法 predict_emotions(rgb_ndarray, logits=False) -> (类名, scores)
"""
import json
import logging
import os
import threading

import numpy as np

from . import config

logger = logging.getLogger(__name__)

BUILTIN_ID = "hsemotion"
BUILTIN_NAME = "HSEmotion（内置 enet_b2_7）"

_LOCK = threading.Lock()
_active_id = BUILTIN_ID
_cache: dict = {}  # id -> TrainedEmotionRecognizer


# ── 自训模型识别器（接口对齐 HSEmotionRecognizer）─────────────────
class TrainedEmotionRecognizer:
    def __init__(self, ckpt_path: str, device):
        import timm
        import torch
        from torchvision import transforms

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.classes = ckpt["classes"]
        self.idx_to_class = {i: c for i, c in enumerate(self.classes)}
        img_size = int(ckpt.get("params", {}).get("img_size", 224))
        backbone = ckpt.get("backbone", config.TRAIN_BACKBONE)

        self._device = device
        self._torch = torch
        self.model = timm.create_model(backbone, pretrained=False,
                                       num_classes=len(self.classes))
        self.model.load_state_dict(ckpt["model"])
        self.model.eval().to(device)

        self._tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def predict_emotions(self, face_rgb: np.ndarray, logits: bool = False):
        """face_rgb: RGB uint8 ndarray（emotion.py 传入的人脸裁剪）。"""
        from PIL import Image
        torch = self._torch
        x = self._tf(Image.fromarray(face_rgb)).unsqueeze(0).to(self._device)
        with torch.no_grad():
            out = self.model(x)[0]
            scores = out if logits else torch.softmax(out, dim=0)
        scores = scores.cpu().numpy()
        return self.classes[int(scores.argmax())], scores


# ── sidecar 读写 ──────────────────────────────────────────────────
def _sidecar_path(model_id: str) -> str:
    return str(config.CHECKPOINT_DIR / f"{model_id}.json")


def register_trained(meta: dict) -> None:
    """训练保存最佳权重后写入元数据 sidecar（供列表展示与加载）。"""
    with open(_sidecar_path(meta["id"]), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def _load_sidecars() -> list:
    out = []
    if not config.CHECKPOINT_DIR.is_dir():
        return out
    for entry in os.scandir(config.CHECKPOINT_DIR):
        if entry.name.endswith(".json"):
            try:
                with open(entry.path, encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception as e:  # noqa: BLE001
                logger.warning("读取模型元数据失败 %s: %s", entry.name, e)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


# ── 列表 / 切换 / 删除 ────────────────────────────────────────────
def list_models() -> dict:
    models = [{
        "id": BUILTIN_ID, "name": BUILTIN_NAME, "type": "builtin",
        "datasets": [], "val_acc": None, "macro_f1": None, "created_at": None,
        "active": _active_id == BUILTIN_ID,
    }]
    for m in _load_sidecars():
        models.append({
            "id": m["id"], "name": m.get("name", m["id"]), "type": "trained",
            "datasets": m.get("datasets", []),
            "val_acc": m.get("val_acc"), "macro_f1": m.get("macro_f1"),
            "created_at": m.get("created_at"),
            "active": _active_id == m["id"],
        })
    return {"active": _active_id, "models": models}


def set_active(model_id: str, models) -> dict:
    """切换激活模型。未知 id 抛 KeyError；加载失败抛 RuntimeError。"""
    global _active_id
    if model_id == BUILTIN_ID:
        with _LOCK:
            _active_id = BUILTIN_ID
        return {"ok": True, "active": _active_id}

    sidecar = _sidecar_path(model_id)
    ckpt = config.CHECKPOINT_DIR / f"{model_id}.pt"
    if not (os.path.exists(sidecar) and ckpt.exists()):
        raise KeyError(model_id)

    if model_id not in _cache:
        try:
            _cache[model_id] = TrainedEmotionRecognizer(str(ckpt), models.device)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"加载模型失败: {e}") from e
    with _LOCK:
        _active_id = model_id
    logger.info("已切换推理模型 → %s", model_id)
    return {"ok": True, "active": _active_id}


def delete_model(model_id: str) -> dict:
    """删除自训模型（不可删内置）。若删的是当前激活，则回退到内置。"""
    global _active_id
    if model_id == BUILTIN_ID:
        raise ValueError("内置模型不可删除")
    sidecar = _sidecar_path(model_id)
    ckpt = config.CHECKPOINT_DIR / f"{model_id}.pt"
    if not os.path.exists(sidecar):
        raise KeyError(model_id)
    for p in (sidecar, str(ckpt)):
        if os.path.exists(p):
            os.remove(p)
    _cache.pop(model_id, None)
    with _LOCK:
        if _active_id == model_id:
            _active_id = BUILTIN_ID
    return {"ok": True, "active": _active_id}


def get_active_recognizer(models):
    """返回当前激活的情感识别器（内置 → models.emotion；自训 → 缓存实例）。"""
    aid = _active_id
    if aid == BUILTIN_ID:
        return models.emotion
    rec = _cache.get(aid)
    if rec is None:                      # 进程重启后缓存为空，惰性重载
        try:
            set_active(aid, models)
            rec = _cache.get(aid)
        except Exception:                # noqa: BLE001
            return models.emotion
    return rec
