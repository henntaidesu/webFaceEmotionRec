"""FastAPI 应用：HTTP 健康检查 + WebSocket 实时情感识别。"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .emotion import analyze_frame
from .image_utils import decode_base64_image
from .models import get_models

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
