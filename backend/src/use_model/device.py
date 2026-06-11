"""CUDA 设备选择与诊断。"""
import logging

import torch

from .. import config

logger = logging.getLogger(__name__)


def select_device() -> torch.device:
    """选择运算设备。

    默认强制 CUDA：检测不到可用 GPU 时抛出 RuntimeError。
    若 config.REQUIRE_CUDA 为 False，则在无 GPU 时回退到 CPU。
    """
    if torch.cuda.is_available():
        index = config.CUDA_DEVICE_INDEX
        device = torch.device(f"cuda:{index}")
        gpu_name = torch.cuda.get_device_name(index)
        cuda_ver = torch.version.cuda
        logger.info(
            "✅ GPU 已启用: %s  |  CUDA %s  |  PyTorch %s",
            gpu_name, cuda_ver, torch.__version__,
        )
        return device

    if config.REQUIRE_CUDA:
        raise RuntimeError(
            "未检测到可用的 CUDA 设备，而 REQUIRE_CUDA 已开启。\n"
            "请确认已安装支持 CUDA 的 PyTorch 与显卡驱动："
            "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128\n"
            "如需在 CPU 上运行，请设置环境变量 REQUIRE_CUDA=0。"
        )

    logger.warning("⚠️  未检测到 GPU，将使用 CPU 运算（性能较低）")
    return torch.device("cpu")
