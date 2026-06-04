"""情感标签三套词表的映射（HSEmotion 输出 → 英文 key → 中文显示）。

模型为 enet_b2_7，共 7 类，不含 contempt。
如更换模型，需同步更新这两张表。
"""

# HSEmotion 原始输出（小写后）→ DeepFace 兼容英文 key
HSEMOTION_TO_EN = {
    "anger":     "angry",
    "disgust":   "disgust",
    "fear":      "fear",
    "happiness": "happy",
    "neutral":   "neutral",
    "sadness":   "sad",
    "surprise":  "surprise",
}

# 英文 key → 中文显示
EMOTION_ZH = {
    "angry":    "愤怒",
    "fear":     "恐惧",
    "happy":    "开心",
    "sad":      "悲伤",
    "surprise": "惊讶",
    "neutral":  "平静",
}


def to_en(hsemotion_label: str) -> str:
    """HSEmotion 标签（任意大小写）转英文 key。"""
    key = hsemotion_label.lower()
    return HSEMOTION_TO_EN.get(key, key)


def to_zh(en_label: str) -> str:
    """英文 key 转中文显示。"""
    return EMOTION_ZH.get(en_label, en_label)
