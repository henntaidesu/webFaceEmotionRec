"""图像工具。"""
import base64
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """将 base64 数据 URL 解码为 OpenCV BGR 图像数组，失败返回 None。"""
    try:
        encoded = data_url.split(",", 1)[1] if "," in data_url else data_url
        img_bytes = base64.b64decode(encoded)
        arr = np.frombuffer(img_bytes, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error("图像解码错误: %s", e)
        return None
