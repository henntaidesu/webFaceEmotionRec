"""集中配置。支持通过环境变量覆盖关键项。"""
import os


def _env_flag(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ── 服务监听 ──────────────────────────────────────────────────────
HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
PORT = int(os.getenv("BACKEND_PORT", "9501"))

# ── CUDA 设备 ─────────────────────────────────────────────────────
# 默认强制使用 CUDA：无可用 GPU 时直接报错退出。
# 设置环境变量 REQUIRE_CUDA=0 可关闭，改为在无 GPU 时回退到 CPU。
REQUIRE_CUDA = _env_flag("REQUIRE_CUDA", True)
# 指定使用的 GPU 序号
CUDA_DEVICE_INDEX = int(os.getenv("CUDA_DEVICE_INDEX", "0"))

# ── 模型 ──────────────────────────────────────────────────────────
# enet_b2_7：EfficientNet-B2，7 类情感（不含 contempt，与 DeepFace 标签一致）
EMOTION_MODEL = os.getenv("EMOTION_MODEL", "enet_b2_7")

# ── MTCNN 检测参数 ────────────────────────────────────────────────
MIN_FACE_SIZE = 20
MTCNN_THRESHOLDS = [0.6, 0.7, 0.7]
# 单脸置信度门槛：低于此值的人脸在情感分类前丢弃
FACE_CONFIDENCE_THRESHOLD = 0.75

# ── 检测后端（当前仅校验，实际始终使用 MTCNN）─────────────────────
ALLOWED_DETECTOR_BACKENDS = frozenset({
    "opencv", "ssd", "dlib", "mtcnn", "retinaface",
    "mediapipe", "yolov8", "yunet", "fastmtcnn",
})
DEFAULT_DETECTOR_BACKEND = "mtcnn"

# ── 推理线程池大小 ────────────────────────────────────────────────
WORKER_THREADS = int(os.getenv("WORKER_THREADS", "2"))
