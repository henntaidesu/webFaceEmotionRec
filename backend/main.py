import asyncio
import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"  # 屏蔽 TensorFlow 冗余日志

import cv2
import numpy as np
import tensorflow as tf
from deepface import DeepFace
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── GPU 初始化 ────────────────────────────────────────────────
gpus = tf.config.list_physical_devices("GPU")
if gpus:
    try:
        # 按需分配显存，避免一次性占满全部 GPU 内存
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        logger.info(f"✅ GPU 已启用，共检测到 {len(gpus)} 个设备: {[g.name for g in gpus]}")
    except RuntimeError as e:
        logger.error(f"GPU 配置失败: {e}")
else:
    logger.warning("⚠️  未检测到 GPU，将使用 CPU 运算（请检查 CUDA/cuDNN 安装）")

app = FastAPI(title="人脸情感识别 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

# DeepFace 人脸检测后端（与前端下拉选项一致，仅允许白名单内的值）
ALLOWED_DETECTOR_BACKENDS = frozenset(
    {
        "opencv",
        "ssd",
        "dlib",
        "mtcnn",
        "retinaface",
        "mediapipe",
        "yolov8",
        "yunet",
        "fastmtcnn",
    }
)
DEFAULT_DETECTOR_BACKEND = "retinaface"

EMOTION_ZH = {
    "angry": "愤怒",
    "disgust": "厌恶",
    "fear": "恐惧",
    "happy": "开心",
    "sad": "悲伤",
    "surprise": "惊讶",
    "neutral": "平静",
}


def analyze_frame(img: np.ndarray, detector_backend: str = DEFAULT_DETECTOR_BACKEND) -> dict:
    """在线程池中运行 DeepFace 分析，避免阻塞事件循环。"""
    try:
        results = DeepFace.analyze(
            img_path=img,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend=detector_backend,
            silent=True,
        )

        faces = []
        for face in results:
            region = face.get("region", {})
            emotions_raw = face.get("emotion", {})
            dominant = face.get("dominant_emotion", "neutral")

            emotions_zh = {
                EMOTION_ZH.get(k, k): round(v, 2)
                for k, v in emotions_raw.items()
            }
            dominant_zh = EMOTION_ZH.get(dominant, dominant)

            faces.append({
                "region": {
                    "x": region.get("x", 0),
                    "y": region.get("y", 0),
                    "w": region.get("w", 0),
                    "h": region.get("h", 0),
                },
                "emotions": emotions_zh,
                "dominant": dominant_zh,
                "dominant_en": dominant,
            })

        return {"success": True, "faces": faces}

    except Exception as e:
        logger.error(f"DeepFace 分析错误: {e}")
        return {"success": False, "error": str(e), "faces": []}


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """将 base64 数据 URL 解码为 OpenCV 图像数组。"""
    try:
        if "," in data_url:
            encoded = data_url.split(",", 1)[1]
        else:
            encoded = data_url
        img_bytes = base64.b64decode(encoded)
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.error(f"图像解码错误: {e}")
        return None


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "人脸情感识别服务运行中"}


@app.websocket("/ws/emotion")
async def emotion_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket 连接建立")

    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await websocket.receive_text()

            detector_backend = DEFAULT_DETECTOR_BACKEND
            frame_payload = data

            stripped = data.strip()
            if stripped.startswith("{"):
                try:
                    payload = json.loads(data)
                    frame_payload = payload.get("frame") or payload.get("data") or ""
                    raw_backend = payload.get("detector_backend")
                    if isinstance(raw_backend, str):
                        b = raw_backend.lower().strip()
                        if b in ALLOWED_DETECTOR_BACKENDS:
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
                lambda: analyze_frame(img, detector_backend),
            )
            await websocket.send_text(json.dumps(result, ensure_ascii=False))

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
