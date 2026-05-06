import asyncio
import base64
import functools
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import torch
from PIL import Image
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# PyTorch 2.6+ 将 weights_only 默认值改为 True，hsemotion 尚未适配，此处打补丁兼容
_original_torch_load = torch.load
@functools.wraps(_original_torch_load)
def _patched_torch_load(f, *args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_torch_load(f, *args, **kwargs)
torch.load = _patched_torch_load

from facenet_pytorch import MTCNN
from hsemotion.facial_emotions import HSEmotionRecognizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── 设备初始化 ────────────────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if torch.cuda.is_available():
    gpu_name = torch.cuda.get_device_name(0)
    cuda_ver = torch.version.cuda
    logger.info(f"✅ GPU 已启用: {gpu_name}  |  CUDA {cuda_ver}  |  PyTorch {torch.__version__}")
else:
    logger.warning("⚠️  未检测到 GPU，将使用 CPU 运算（请检查 CUDA/cuDNN 安装）")

# ── 模型初始化 ────────────────────────────────────────────────────
# MTCNN：多任务级联卷积神经网络，GPU 加速人脸检测
mtcnn = MTCNN(
    keep_all=True,
    device=device,
    min_face_size=20,
    thresholds=[0.6, 0.7, 0.7],
    post_process=False,
)

# HSEmotion：EfficientNet-B2，7 类情感（不含 Contempt，与 DeepFace 标签一致）
emotion_recognizer = HSEmotionRecognizer(model_name="enet_b2_7", device=str(device))

# ── 情感标签映射（英文 → 中文）────────────────────────────────────
# hsemotion enet_b0_7 输出首字母大写，需统一小写后映射
HSEMOTION_TO_EN = {
    "anger":     "angry",
    "disgust":   "disgust",
    "fear":      "fear",
    "happiness": "happy",
    "neutral":   "neutral",
    "sadness":   "sad",
    "surprise":  "surprise",
}
EMOTION_ZH = {
    "angry":    "愤怒",
    "disgust":  "厌恶",
    "fear":     "恐惧",
    "happy":    "开心",
    "sad":      "悲伤",
    "surprise": "惊讶",
    "neutral":  "平静",
}

ALLOWED_DETECTOR_BACKENDS = frozenset({
    "opencv", "ssd", "dlib", "mtcnn", "retinaface",
    "mediapipe", "yolov8", "yunet", "fastmtcnn",
})
DEFAULT_DETECTOR_BACKEND = "mtcnn"

app = FastAPI(title="人脸情感识别 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)


def analyze_frame(img: np.ndarray, detector_backend: str = DEFAULT_DETECTOR_BACKEND) -> dict:
    """使用 MTCNN + HSEmotion (PyTorch) 检测人脸并识别情感。"""
    try:
        h, w = img.shape[:2]

        # OpenCV BGR → PIL RGB（MTCNN 要求 RGB）
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # MTCNN 人脸检测，返回 boxes=[N,4] (x1,y1,x2,y2)，probs=[N]
        boxes, probs = mtcnn.detect(pil_img)

        if boxes is None:
            return {"success": True, "faces": []}

        faces = []
        # 获取情感标签顺序
        idx_to_label = emotion_recognizer.idx_to_class  # {0: 'Anger', 1: 'Disgust', ...}

        for box, prob in zip(boxes, probs):
            if prob is None or float(prob) < 0.75:
                continue

            x1, y1, x2, y2 = (int(c) for c in box)
            # 边界裁剪，防止越界
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            # 裁剪人脸区域（RGB 格式传入 HSEmotion）
            face_crop = rgb[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            # 情感识别：返回 (emotion_str, scores_ndarray)
            emotion_raw, scores = emotion_recognizer.predict_emotions(face_crop, logits=False)

            # 将 hsemotion 标签统一转小写，再映射为 DeepFace 兼容的英文 key
            dominant_hs = emotion_raw.lower()
            dominant_en = HSEMOTION_TO_EN.get(dominant_hs, dominant_hs)
            dominant_zh = EMOTION_ZH.get(dominant_en, dominant_en)

            # 构建各情感概率字典（中文 key，百分比）
            emotions_zh: dict[str, float] = {}
            for idx, score in enumerate(scores):
                label_hs = idx_to_label.get(idx, "").lower()
                label_en = HSEMOTION_TO_EN.get(label_hs, label_hs)
                label_zh = EMOTION_ZH.get(label_en, label_en)
                emotions_zh[label_zh] = round(float(score) * 100, 2)

            faces.append({
                "region": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                "emotions": emotions_zh,
                "dominant": dominant_zh,
                "dominant_en": dominant_en,
            })

        return {"success": True, "faces": faces}

    except Exception as e:
        logger.error(f"分析错误: {e}", exc_info=True)
        return {"success": False, "error": str(e), "faces": []}


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """将 base64 数据 URL 解码为 OpenCV 图像数组。"""
    try:
        encoded = data_url.split(",", 1)[1] if "," in data_url else data_url
        img_bytes = base64.b64decode(encoded)
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.error(f"图像解码错误: {e}")
        return None


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "人脸情感识别服务运行中",
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


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

            if data.strip().startswith("{"):
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
    uvicorn.run(app, host="0.0.0.0", port=9501, reload=False)
