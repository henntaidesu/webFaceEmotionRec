"""PyTorch 2.6+ 兼容补丁。

PyTorch 2.6 将 torch.load 的 weights_only 默认值改为 True，
facenet_pytorch / hsemotion 附带的权重尚未适配，会加载失败。
必须在导入这两个库**之前**调用 patch_torch_load()。
"""
import functools

import torch

_patched = False


def patch_torch_load() -> None:
    """将 torch.load 的 weights_only 默认值强制为 False（幂等）。"""
    global _patched
    if _patched:
        return

    _original_torch_load = torch.load

    @functools.wraps(_original_torch_load)
    def _patched_torch_load(f, *args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_torch_load(f, *args, **kwargs)

    torch.load = _patched_torch_load
    _patched = True
