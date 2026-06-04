"""核心情感识别逻辑。"""
import logging

import cv2
import numpy as np
from PIL import Image

from . import config, labels
from .models import ModelBundle

logger = logging.getLogger(__name__)


def analyze_frame(
    img: np.ndarray,
    models: ModelBundle,
    detector_backend: str = config.DEFAULT_DETECTOR_BACKEND,
) -> dict:
    """使用 MTCNN + HSEmotion 检测人脸并识别情感。

    返回 {"success": bool, "faces": [...]}。
    faces 每项含 region、emotions（中文 key→百分比）、dominant（中文）、dominant_en。
    """
    try:
        h, w = img.shape[:2]

        # OpenCV BGR → PIL RGB（MTCNN 要求 RGB）
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # MTCNN 人脸检测：boxes=[N,4] (x1,y1,x2,y2)，probs=[N]
        boxes, probs = models.mtcnn.detect(pil_img)
        if boxes is None:
            return {"success": True, "faces": []}

        idx_to_label = models.emotion.idx_to_class  # {0: 'Anger', ...}
        faces = []

        for box, prob in zip(boxes, probs):
            if prob is None or float(prob) < config.FACE_CONFIDENCE_THRESHOLD:
                continue

            x1, y1, x2, y2 = (int(c) for c in box)
            # 边界裁剪，防止越界
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            face_crop = rgb[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            # 情感识别：返回 (emotion_str, scores_ndarray)
            emotion_raw, scores = models.emotion.predict_emotions(face_crop, logits=False)

            dominant_en = labels.to_en(emotion_raw)
            dominant_zh = labels.to_zh(dominant_en)

            # 各情感概率（中文 key，百分比）
            emotions_zh: dict[str, float] = {}
            for idx, score in enumerate(scores):
                label_en = labels.to_en(idx_to_label.get(idx, ""))
                emotions_zh[labels.to_zh(label_en)] = round(float(score) * 100, 2)

            faces.append({
                "region": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                "emotions": emotions_zh,
                "dominant": dominant_zh,
                "dominant_en": dominant_en,
            })

        return {"success": True, "faces": faces}

    except Exception as e:
        logger.error("分析错误: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "faces": []}
