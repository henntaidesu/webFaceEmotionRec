"""FastAPI 应用：HTTP 健康检查 + WebSocket 实时情感识别。"""
import asyncio
import base64
import binascii
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import torch
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..use_model import model_registry
from ..use_model.emotion import analyze_frame
from ..use_model.fea_emotion import classify_fea
from ..use_model.models import get_models
from ..use_eval import eval_store, evaluation
from ..use_train import train_store, training
from .image_utils import decode_base64_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="人脸情感识别 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=config.WORKER_THREADS)

# 启动即加载模型（含 CUDA 设备选择，无 GPU 且强制 CUDA 时此处即报错）
models = get_models()


@app.get("/health")
async def health_check():
    on_cuda = models.device.type == "cuda"
    return {
        "status": "ok",
        "message": "人脸情感识别服务运行中",
        "device": str(models.device),
        "gpu": torch.cuda.get_device_name(config.CUDA_DEVICE_INDEX) if on_cuda else None,
    }


# ── 模型训练（图像 FER）API ───────────────────────────────────────
@app.get("/api/train/datasets")
async def train_datasets():
    return training.list_datasets()


@app.get("/api/train/status")
async def train_status():
    return training.get_status()


@app.post("/api/train/start")
async def train_start(params: dict = Body(default=None)):
    try:
        return training.start_training(params or {})
    except RuntimeError as e:        # 已有任务在跑
        return JSONResponse(status_code=409, content={"ok": False, "error": str(e)})
    except ValueError as e:          # 参数非法
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.post("/api/train/stop")
async def train_stop():
    return training.stop_training()


@app.get("/api/train/runs")
async def train_runs():
    """全部历史训练运行（供右侧面板下拉切换）。"""
    return train_store.list_runs()


@app.get("/api/train/runs/{run_id}")
async def train_run_detail(run_id: str):
    """某次训练的元数据与逐轮指标。"""
    run = train_store.get_run(run_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "训练记录不存在"})
    return run


# ── 模型评测（测试/验证集）API ────────────────────────────────────
@app.get("/api/eval/targets")
async def eval_targets():
    """可评测的模型与数据集（含 val/test 计数）。"""
    return evaluation.list_targets()


@app.get("/api/eval/status")
async def eval_status():
    return evaluation.get_status()


@app.post("/api/eval/start")
async def eval_start(params: dict = Body(default=None)):
    try:
        return evaluation.start_eval(params or {})
    except RuntimeError as e:        # 已有任务在跑
        return JSONResponse(status_code=409, content={"ok": False, "error": str(e)})
    except ValueError as e:          # 参数非法
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.post("/api/eval/stop")
async def eval_stop():
    return evaluation.stop_eval()


@app.get("/api/eval/runs")
async def eval_runs():
    """全部历史评测记录（供下拉切换）。"""
    return eval_store.list_evals()


@app.get("/api/eval/runs/{eval_id}")
async def eval_run_detail(eval_id: str):
    """某次评测的完整结果（含混淆矩阵与逐类指标）。"""
    run = eval_store.get_eval(eval_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "评测记录不存在"})
    return run


@app.delete("/api/eval/runs/{eval_id}")
async def eval_run_delete(eval_id: str):
    if eval_store.delete_eval(eval_id):
        return {"ok": True}
    return JSONResponse(status_code=404, content={"ok": False, "error": "评测记录不存在"})


# ── 推理模型注册表（列出 / 切换 / 删除）─────────────────────────────
@app.get("/api/models")
async def models_list():
    return model_registry.list_models()


@app.post("/api/models/active")
async def models_set_active(body: dict = Body(default=None)):
    model_id = (body or {}).get("id")
    if not model_id:
        return JSONResponse(status_code=400, content={"ok": False, "error": "缺少模型 id"})
    try:
        return model_registry.set_active(model_id, models)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "error": "模型不存在"})
    except RuntimeError as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.delete("/api/models/{model_id}")
async def models_delete(model_id: str):
    try:
        return model_registry.delete_model(model_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "error": "模型不存在"})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


# ── 网页生成的刺激图落盘（image/<emotion>/<时间戳>.png）────────────
@app.post("/api/stimulus/save")
async def stimulus_save(body: dict = Body(default=None)):
    """接收前端生成的刺激图，按情感分目录存入 image/，文件名用时间戳（精确到秒）。

    请求体：{"emotion": str, "image": data-url/base64, "ext"?: str, "folder"?: str}
    """
    body = body or {}
    emotion = str(body.get("emotion") or "").strip().lower()
    if emotion not in config.TRAIN_CLASSES:
        return JSONResponse(status_code=400, content={"ok": False, "error": "非法情感类别"})

    data_url = body.get("image")
    b64 = data_url.split(",", 1)[-1] if isinstance(data_url, str) else ""
    if not b64:
        return JSONResponse(status_code=400, content={"ok": False, "error": "缺少图像数据"})
    try:
        raw = base64.b64decode(b64)
    except (ValueError, binascii.Error):
        return JSONResponse(status_code=400, content={"ok": False, "error": "图像解码失败"})

    ext = re.sub(r"[^a-z0-9]", "", str(body.get("ext") or "png").lower()) or "png"
    folder = re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("folder") or ""))
    dest_dir = config.IMAGE_DIR / folder / emotion if folder else config.IMAGE_DIR / emotion
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 精确到秒命名；同一秒内重复时追加序号避免覆盖
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = dest_dir / f"{stamp}.{ext}"
    n = 1
    while path.exists():
        path = dest_dir / f"{stamp}_{n}.{ext}"
        n += 1
    path.write_bytes(raw)

    return {"ok": True, "path": str(path.relative_to(config.ROOT)), "filename": path.name}


_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@app.get("/api/stimulus/images")
async def stimulus_images(emotion: str = "", limit: int = 1000):
    """列出 image/ 下已保存的历史刺激图（按修改时间倒序，最新在前）。

    每项：{"emotion", "filename", "path", "url", "mtime"}。
    url 指向 /api/stimulus/files/<相对路径> 静态服务。
    """
    emo_filter = emotion.strip().lower()
    items = []
    for p in config.IMAGE_DIR.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_EXT:
            continue
        emo = p.parent.name.lower()
        if emo not in config.TRAIN_CLASSES:
            continue
        if emo_filter and emo != emo_filter:
            continue
        rel = p.relative_to(config.IMAGE_DIR).as_posix()
        items.append({
            "emotion": emo,
            "filename": p.name,
            "path": rel,
            "url": f"/api/stimulus/files/{rel}",
            "mtime": p.stat().st_mtime,
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"images": items[:max(1, limit)], "total": len(items)}


@app.delete("/api/stimulus/images")
async def stimulus_images_delete(path: str = "", emotion: str = ""):
    """删除历史刺激图：传 path 删单张；传 emotion 删该情感下全部。"""
    root = config.IMAGE_DIR.resolve()
    if path:
        target = (config.IMAGE_DIR / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return JSONResponse(status_code=400, content={"ok": False, "error": "非法路径"})
        target.unlink()
        return {"ok": True, "deleted": 1}

    emo = emotion.strip().lower()
    if emo and emo in config.TRAIN_CLASSES:
        deleted = 0
        for p in config.IMAGE_DIR.rglob("*"):
            if p.is_file() and p.parent.name.lower() == emo and p.suffix.lower() in _IMAGE_EXT:
                p.unlink()
                deleted += 1
        return {"ok": True, "deleted": deleted}

    return JSONResponse(status_code=400, content={"ok": False, "error": "缺少 path 或 emotion"})


# 静态服务已保存的刺激图（历史查看用）
app.mount(
    "/api/stimulus/files",
    StaticFiles(directory=str(config.IMAGE_DIR)),
    name="stimulus_files",
)


# ── Quest Pro 头显 FEA（63 维混合形状）→ 情绪 ─────────────────────
# 机内摄像头不开放原始图像，头显侧（Unity/Meta XR Movement SDK）把 63 维 FEA
# 推到这里；后端分类后，前端「微情感生成」页轮询 /api/fea/latest 取用。
_latest_fea: dict = {"data": None}


@app.post("/api/fea")
async def fea_ingest(body: dict = Body(default=None)):
    """接收 Quest Pro 的一帧 FEA：{"blendshapes":[63], "timestamp_ms"?:int}。"""
    bs = (body or {}).get("blendshapes")
    try:
        result = classify_fea(bs)
    except (ValueError, TypeError) as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    result["success"] = True
    result["timestamp_ms"] = int((body or {}).get("timestamp_ms") or time.time() * 1000)
    _latest_fea["data"] = result
    return result


@app.get("/api/fea/latest")
async def fea_latest():
    """前端取最近一帧 FEA 情绪；无数据时 success=False。"""
    data = _latest_fea["data"]
    if not data:
        return {"success": False, "faces": []}
    # 结构对齐图像识别路径：faces:[{dominant_en,dominant,emotions}]
    return {"success": True, "timestamp_ms": data["timestamp_ms"], "faces": [
        {"dominant_en": data["dominant_en"], "dominant": data["dominant"], "emotions": data["emotions"]}
    ]}


@app.websocket("/ws/emotion")
async def emotion_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket 连接建立")

    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await websocket.receive_text()

            detector_backend = config.DEFAULT_DETECTOR_BACKEND
            frame_payload = data

            if data.strip().startswith("{"):
                try:
                    payload = json.loads(data)
                    frame_payload = payload.get("frame") or payload.get("data") or ""
                    raw_backend = payload.get("detector_backend")
                    if isinstance(raw_backend, str):
                        b = raw_backend.lower().strip()
                        if b in config.ALLOWED_DETECTOR_BACKENDS:
                            detector_backend = b
                except json.JSONDecodeError:
                    frame_payload = data

            img = decode_base64_image(frame_payload)
            if img is None:
                await websocket.send_text(
                    json.dumps({"success": False, "error": "图像解码失败", "faces": []})
                )
                continue

            result = await loop.run_in_executor(
                executor,
                lambda: analyze_frame(img, models, detector_backend),
            )
            await websocket.send_text(json.dumps(result, ensure_ascii=False))

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
