# -*- coding: utf-8 -*-
"""集中式路径安全校验。

多处端点用用户可控的 id 拼接文件路径（模型注册表、预测模型、评测记录等）。
若不校验，`../` / `..\\` 可逃逸目标目录，配合全局 `torch.load(weights_only=False)`
造成 RCE，或经 `shutil.rmtree` 造成任意目录删除。所有 id→路径拼接处统一用此模块。
"""
import re

# 仅允许字母、数字、下划线、连字符（与 use_capture/session_store._safe 同约定）。
# 不含 . / \\ 空格等，天然排除 ".."、路径分隔符与盘符。
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_id(value) -> bool:
    """value 是否可安全用于拼接文件名/单级目录名。"""
    return isinstance(value, str) and _ID_RE.match(value) is not None
