"""刺激生成的**共享控制状态**：网页与 VR 头显两侧都能读改同一份参数。

为什么放后端：原先闭环的全部参数（目标情绪、场景四要素、调制模式、目标强度…）只存在
VRStimulusPanel.vue 的局部 ref 里，头显无从知晓也无法修改。要做到「在 VR 中与在外面都
可以调整」，就必须有一份两边共用的真源，这个模块即是。

  GET  /api/stimulus/options   选项表（情绪 / 场景四要素 / 调制模式），带 zh/ja/en 三语
  GET  /api/stimulus/control   当前控制状态（含 version，便于两侧只在变化时刷新 UI）
  POST /api/stimulus/control   局部更新（只传要改的字段），version 自增

**谁在执行生成**：DeepSeek 提示词与 ComfyUI 出图都跑在浏览器里（VRStimulusPanel.vue），
本模块只持有「要不要跑」的意图。头显按下开始 → running=True → 网页轮询到后启动闭环。
因此**网页必须保持打开**，头显才能真正驱动生成；网页关掉时 running 只是个待执行的意图。

语言取舍：网页是 zh/ja，头显是 en/ja（受试者面向国际），所以选项表同时给三语，
各端自取所需，避免两边各写一份预设导致漂移。
"""
import threading
import time

from .. import config

# ── 选项表（单一真源；VRStimulusPanel.vue 与 Unity 都从这里取）──────────
# 情绪 key 必须是 config.TRAIN_CLASSES 里的值
EMOTIONS = [
    {"key": "angry",    "zh": "愤怒", "ja": "怒り",     "en": "Angry"},
    {"key": "disgust",  "zh": "厌恶", "ja": "嫌悪",     "en": "Disgust"},
    {"key": "fear",     "zh": "恐惧", "ja": "恐怖",     "en": "Fear"},
    {"key": "happy",    "zh": "开心", "ja": "喜び",     "en": "Happy"},
    {"key": "neutral",  "zh": "平静", "ja": "中立",     "en": "Neutral"},
    {"key": "sad",      "zh": "悲伤", "ja": "悲しみ",   "en": "Sad"},
    {"key": "surprise", "zh": "惊讶", "ja": "驚き",     "en": "Surprise"},
]

MODES = [
    {"key": "amplify", "zh": "递进强化",   "ja": "段階的強化", "en": "Amplify"},
    {"key": "titrate", "zh": "目标带调节", "ja": "目標帯調節", "en": "Titrate"},
    {"key": "dose",    "zh": "剂量阶梯",   "ja": "用量段階",   "en": "Dose ladder"},
    {"key": "random",  "zh": "随机",       "ja": "ランダム",   "en": "Random"},
]

# 场景四要素（「刺激种子」）：组合后喂给 DeepSeek 生成提示词
SCENE_DIMS = [
    {"key": "time", "zh": "时间", "ja": "時間", "en": "Time", "items": [
        {"zh": "清晨",     "ja": "早朝",     "en": "Early morning"},
        {"zh": "正午",     "ja": "正午",     "en": "Noon"},
        {"zh": "黄昏",     "ja": "夕暮れ",   "en": "Dusk"},
        {"zh": "深夜",     "ja": "深夜",     "en": "Late night"},
        {"zh": "雨天",     "ja": "雨の日",   "en": "Rainy day"},
        {"zh": "雪天",     "ja": "雪の日",   "en": "Snowy day"},
        {"zh": "春日",     "ja": "春の日",   "en": "Spring day"},
        {"zh": "盛夏",     "ja": "真夏",     "en": "Midsummer"},
        {"zh": "秋日",     "ja": "秋の日",   "en": "Autumn day"},
        {"zh": "暴风雨夜", "ja": "嵐の夜",   "en": "Stormy night"},
    ]},
    {"key": "place", "zh": "地点", "ja": "場所", "en": "Place", "items": [
        {"zh": "海滩",     "ja": "ビーチ",   "en": "Beach"},
        {"zh": "森林",     "ja": "森",       "en": "Forest"},
        {"zh": "城市街道", "ja": "街の通り", "en": "City street"},
        {"zh": "山顶",     "ja": "山頂",     "en": "Mountain summit"},
        {"zh": "室内房间", "ja": "室内",     "en": "Indoor room"},
        {"zh": "湖畔",     "ja": "湖畔",     "en": "Lakeside"},
        {"zh": "沙漠",     "ja": "砂漠",     "en": "Desert"},
        {"zh": "花园",     "ja": "庭園",     "en": "Garden"},
        {"zh": "地铁站",   "ja": "駅",       "en": "Subway station"},
        {"zh": "废墟",     "ja": "廃墟",     "en": "Ruins"},
    ]},
    {"key": "task", "zh": "任务", "ja": "タスク", "en": "Activity", "items": [
        {"zh": "散步",     "ja": "散歩",             "en": "Walking"},
        {"zh": "休息",     "ja": "休憩",             "en": "Resting"},
        {"zh": "探索",     "ja": "探索",             "en": "Exploring"},
        {"zh": "庆祝",     "ja": "お祝い",           "en": "Celebrating"},
        {"zh": "独处",     "ja": "一人で過ごす",     "en": "Being alone"},
        {"zh": "奔跑",     "ja": "走る",             "en": "Running"},
        {"zh": "眺望远方", "ja": "遠くを眺める",     "en": "Gazing into the distance"},
        {"zh": "等待",     "ja": "待つ",             "en": "Waiting"},
        {"zh": "逃离",     "ja": "逃げる",           "en": "Fleeing"},
        {"zh": "沉思",     "ja": "物思いにふける",   "en": "Contemplating"},
    ]},
    {"key": "event", "zh": "事情", "ja": "出来事", "en": "Event", "items": [
        {"zh": "烟花绽放", "ja": "花火が上がる",     "en": "Fireworks bursting"},
        {"zh": "日出",     "ja": "日の出",           "en": "Sunrise"},
        {"zh": "暴风来临", "ja": "嵐が来る",         "en": "Storm approaching"},
        {"zh": "花朵盛开", "ja": "花が咲く",         "en": "Flowers blooming"},
        {"zh": "极光出现", "ja": "オーロラが現れる", "en": "Aurora appearing"},
        {"zh": "大雨倾盆", "ja": "土砂降り",         "en": "Downpour"},
        {"zh": "落叶纷飞", "ja": "落ち葉が舞う",     "en": "Leaves swirling"},
        {"zh": "火焰蔓延", "ja": "炎が広がる",       "en": "Flames spreading"},
        {"zh": "雾气弥漫", "ja": "霧が立ち込める",   "en": "Fog rolling in"},
        {"zh": "万物寂静", "ja": "静寂に包まれる",   "en": "Everything falls silent"},
    ]},
]

_EMOTION_KEYS = {e["key"] for e in EMOTIONS}
_MODE_KEYS = {m["key"] for m in MODES}
_DIM_LEN = {d["key"]: len(d["items"]) for d in SCENE_DIMS}

LANGS = ("zh", "ja", "en")

_LOCK = threading.Lock()
_state = {
    "running": False,          # 是否要跑生成闭环（网页据此启停）
    # 界面语言：由网页当前所在的 /cn 或 /jp 决定，头显跟随它。
    # 受试者面对的是同一套实验，两端语言不一致会造成指导语与选项对不上。
    "lang": "zh",
    "emotion": "happy",
    "mode": "amplify",
    "target_intensity": 0.6,
    "measure_window_s": 6.0,
    "scene": {"time": 0, "place": 0, "task": 0, "event": 0},
    "seed": -1,                # -1 = 每张随机
    "subject_id": "anon",
    "version": 0,
    "updated_ms": 0,
    "source": "init",          # 最后一次修改来自 web / vr / init
}


def _clamp(v, lo, hi, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def options() -> dict:
    """选项表。三语一起返回，各端按自己的语言取。"""
    return {"emotions": EMOTIONS, "modes": MODES, "scene_dims": SCENE_DIMS,
            "classes": list(config.TRAIN_CLASSES)}


def get_control() -> dict:
    with _LOCK:
        return dict(_state, scene=dict(_state["scene"]))


def update_control(patch: dict) -> dict:
    """局部更新：只认已知字段，非法值忽略而不是写坏状态。

    返回更新后的完整状态。version 只在确实发生变化时自增，方便两侧靠 version 判断
    「要不要重建 UI」而不是每次轮询都重绘。
    """
    patch = patch or {}
    with _LOCK:
        changed = False

        if "running" in patch:
            val = bool(patch["running"])
            if val != _state["running"]:
                _state["running"] = val
                changed = True

        if "lang" in patch:
            val = str(patch["lang"] or "").strip().lower()
            if val in LANGS and val != _state["lang"]:
                _state["lang"] = val
                changed = True

        if "emotion" in patch:
            val = str(patch["emotion"] or "").strip().lower()
            if val in _EMOTION_KEYS and val != _state["emotion"]:
                _state["emotion"] = val
                changed = True

        if "mode" in patch:
            val = str(patch["mode"] or "").strip().lower()
            if val in _MODE_KEYS and val != _state["mode"]:
                _state["mode"] = val
                changed = True

        if "target_intensity" in patch:
            val = round(_clamp(patch["target_intensity"], 0.0, 1.0, _state["target_intensity"]), 3)
            if val != _state["target_intensity"]:
                _state["target_intensity"] = val
                changed = True

        if "measure_window_s" in patch:
            val = round(_clamp(patch["measure_window_s"], 2.0, 120.0, _state["measure_window_s"]), 1)
            if val != _state["measure_window_s"]:
                _state["measure_window_s"] = val
                changed = True

        if "seed" in patch:
            try:
                val = int(patch["seed"])
            except (TypeError, ValueError):
                val = _state["seed"]
            if val != _state["seed"]:
                _state["seed"] = val
                changed = True

        if "subject_id" in patch:
            val = str(patch["subject_id"] or "").strip() or "anon"
            if val != _state["subject_id"]:
                _state["subject_id"] = val
                changed = True

        scene = patch.get("scene")
        if isinstance(scene, dict):
            for k, n in _DIM_LEN.items():
                if k not in scene:
                    continue
                try:
                    idx = int(scene[k])
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < n and idx != _state["scene"][k]:
                    _state["scene"][k] = idx
                    changed = True

        if changed:
            _state["version"] += 1
            _state["updated_ms"] = int(time.time() * 1000)
            src = str(patch.get("source") or "").strip().lower()
            _state["source"] = src if src in {"web", "vr"} else "unknown"
        return dict(_state, scene=dict(_state["scene"]))


def scene_text(lang: str = "en") -> str:
    """当前四要素组合成一句场景文本（喂 DeepSeek 用）。"""
    with _LOCK:
        sel = dict(_state["scene"])
    key = lang if lang in ("zh", "ja", "en") else "en"
    parts = []
    for d in SCENE_DIMS:
        items = d["items"]
        i = sel.get(d["key"], 0)
        if 0 <= i < len(items):
            parts.append(items[i][key])
    return ", ".join(parts) if key == "en" else "，".join(parts)
