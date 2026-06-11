"""模型加载：MTCNN 人脸检测 + HSEmotion 情感分类（单例）。"""
import logging

# 必须在导入 facenet_pytorch / hsemotion 之前打补丁
from .torch_patch import patch_torch_load

patch_torch_load()

from facenet_pytorch import MTCNN  # noqa: E402
from hsemotion.facial_emotions import HSEmotionRecognizer  # noqa: E402

from .. import config  # noqa: E402
from .device import select_device  # noqa: E402

logger = logging.getLogger(__name__)


class ModelBundle:
    """持有运算设备与两个模型实例。"""

    def __init__(self) -> None:
        self.device = select_device()

        # MTCNN：多任务级联卷积网络，GPU 加速人脸检测
        self.mtcnn = MTCNN(
            keep_all=True,
            device=self.device,
            min_face_size=config.MIN_FACE_SIZE,
            thresholds=config.MTCNN_THRESHOLDS,
            post_process=False,
        )

        # HSEmotion：EfficientNet-B2，7 类情感
        self.emotion = HSEmotionRecognizer(
            model_name=config.EMOTION_MODEL,
            device=str(self.device),
        )

        logger.info("模型加载完成（设备：%s，情感模型：%s）", self.device, config.EMOTION_MODEL)


_bundle: ModelBundle | None = None


def get_models() -> ModelBundle:
    """获取（首次惰性加载）模型单例。"""
    global _bundle
    if _bundle is None:
        _bundle = ModelBundle()
    return _bundle
