"""FastAPI 应用：HTTP 健康检查 + WebSocket 实时情感识别。"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import torch
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import config
from ..use_model import model_registry
from ..use_model.emotion import analyze_frame
from ..use_model.models import get_models
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
