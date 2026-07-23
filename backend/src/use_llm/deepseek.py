"""DeepSeek 对接：把用户表情/情感的「变化轨迹」转成图像生成提示词。

核心逻辑用 Python（见项目语言约定）。前端只把最近的情感轨迹 POST 到
后端 /api/prompt/generate，真正的 LLM 调用在这里完成——这样密钥不落前端，
提示词工程也集中在一处。

连接参数（密钥/base_url/模型/超时/温度）实时取自 settings_store（根目录
conf.ini），系统设置页改完即时生效，无需重启后端。

DeepSeek 提供 OpenAI 兼容的 Chat Completions 接口：
    POST {BASE_URL}/chat/completions   Authorization: Bearer <key>
用标准库 urllib 直连，避免为一次 HTTP 调用引入第三方依赖。
"""
import json
import urllib.error
import urllib.request

from .. import settings_store

# 7 类情感英文 → 中文，仅用于给 LLM 的可读描述
_EMO_ZH = {
    "angry": "愤怒", "disgust": "厌恶", "fear": "恐惧", "happy": "开心",
    "neutral": "平静", "sad": "悲伤", "surprise": "惊讶",
}

# 提示词必须含 "json" 字样，DeepSeek 的 JSON 模式才会启用
_SYSTEM_PROMPT = (
    "You are an art director that turns a viewer's facial-emotion trajectory into a "
    "single text-to-image prompt. The viewer's dominant emotion CHANGES over time; "
    "make the mood, palette, lighting and subject reflect that emotional CHANGE "
    "(the transition), not merely the latest emotion. "
    "Reply with STRICT JSON only, keys: "
    '"positive" (a detailed English image prompt, comma-separated tags/phrases), '
    '"negative" (English things to avoid, comma-separated), '
    '"scene" (a short English title of the scene), '
    '"reasoning" (ONE short sentence in Chinese explaining how the emotion change shaped the image). '
    "No text outside the JSON object."
)


def _settings() -> dict:
    return settings_store.get_section("deepseek")


def is_configured() -> bool:
    """是否已配置 API Key（未配置时视为该功能未启用）。"""
    return bool(_settings().get("api_key"))


def _chat(messages, temperature, max_tokens=None) -> dict:
    """调用 DeepSeek Chat Completions（JSON 模式），返回解析后的 content dict。

    失败（未配置 / 网络 / 返回异常）时抛 RuntimeError。
    """
    s = _settings()
    if not s.get("api_key"):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    payload = {
        "model": s["model"],
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    req = urllib.request.Request(
        f"{s['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {s['api_key']}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=s["timeout"]) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"DeepSeek 请求失败 [{e.code}]: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"DeepSeek 连接失败: {e.reason}")

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        # strict=False：容忍模型在字符串值里放入的原始换行等控制字符（否则严格模式会解析失败）
        return json.loads(content, strict=False)
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"DeepSeek 返回无法解析: {e}")


def _format_trajectory(trajectory, current) -> str:
    """把前端传来的情感轨迹压成简短、省 token 的文本喂给 LLM。"""
    lines = []
    for s in trajectory or []:
        dom = s.get("dom") or s.get("dominant_en") or ""
        zh = _EMO_ZH.get(dom, dom)
        ago = s.get("ago_s")
        probs = s.get("probs") or {}
        # 只保留最高的三项概率，压缩上下文
        top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_s = ", ".join(f"{k} {round(float(v))}%" for k, v in top if isinstance(v, (int, float)))
        when = f"{ago}s ago" if ago is not None else "earlier"
        lines.append(f"- {when}: {dom}({zh})" + (f" [{top_s}]" if top_s else ""))
    cur_dom = (current or {}).get("dominant_en") or ""
    if cur_dom:
        lines.append(f"- now: {cur_dom}({_EMO_ZH.get(cur_dom, cur_dom)}) (current dominant)")
    return "\n".join(lines) if lines else "- (no samples)"


_SCENE_SYSTEM_PROMPT = (
    "You are an art director generating a single 360-degree EQUIRECTANGULAR PANORAMA "
    "text-to-image prompt used as a VR emotional stimulus. You are given a TARGET emotion, "
    "a BASE scene chosen by the operator, and an INTENSITY DIRECTIVE describing how strongly "
    "the scene should evoke that emotion RIGHT NOW (relative to the viewer's measured state). "
    "Rewrite the base scene into a vivid prompt whose mood, palette, lighting and composition "
    "match BOTH the target emotion AND the requested intensity level: a stronger directive means "
    "a more extreme, saturated, unambiguous version of that emotion; a weaker/softening directive "
    "means a milder, gentler version. The scene elements may include a TIME, a PLACE, an ACTIVITY, "
    "and an EVENT; treat the ACTIVITY as what the VIEWER themselves is doing in first person, so render "
    "the scene from the viewer's immersive first-person point of view and do NOT depict any people or "
    "human figures in the image. Keep it a coherent seamless 360 panorama. "
    "Reply with STRICT JSON only, keys: "
    '"positive" (detailed English image prompt, comma-separated tags/phrases, MUST start with '
    "\"equirectangular 360 panorama, \"), "
    '"negative" (English things to avoid, comma-separated), '
    '"scene" (short English scene title), '
    '"reasoning" (ONE short Chinese sentence: how the target emotion + intensity shaped the image). '
    "No text outside the JSON object."
)


def generate_scene_prompt(emotion, scene, directive, locale="zh") -> dict:
    """场景驱动的动态提示词：给定目标情绪 + 基础场景 + 强度指令 → {positive,negative,scene,reasoning}。

    调制策略（递进/目标带/剂量阶梯/随机）由前端计算成 `directive` 文本传入，这里只负责
    让 DeepSeek 按目标情绪与强度把基础场景改写成全景提示词。失败抛 RuntimeError。
    """
    emo = str(emotion or "").strip()
    zh = _EMO_ZH.get(emo, emo)
    user_msg = (
        f"TARGET emotion: {emo} ({zh})\n"
        f"BASE scene: {str(scene or '').strip() or '(operator gave no scene; invent a fitting one)'}\n"
        f"INTENSITY DIRECTIVE: {str(directive or 'render at a natural, moderate intensity').strip()}\n\n"
        "Return ONE 360 panorama prompt (as JSON) at the requested emotion and intensity."
    )
    messages = [
        {"role": "system", "content": _SCENE_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    # JSON 模式偶尔返回空 positive 或解析抖动（temperature 偏高时）；重试一次，避免闭环因单次抖动中断。
    last_err = "DeepSeek 返回缺少 positive 提示词"
    for _attempt in range(2):
        try:
            parsed = _chat(messages, temperature=_settings()["temperature"])
        except RuntimeError as e:
            last_err = str(e)
            continue
        positive = str(parsed.get("positive") or "").strip()
        if positive:
            return {
                "positive": positive,
                "negative": str(parsed.get("negative") or "").strip(),
                "scene": str(parsed.get("scene") or "").strip(),
                "reasoning": str(parsed.get("reasoning") or "").strip(),
            }
    raise RuntimeError(last_err)


def generate_image_prompt(trajectory, current, locale="zh") -> dict:
    """调用 DeepSeek，返回 {positive, negative, scene, reasoning}。"""
    traj_text = _format_trajectory(trajectory, current)
    user_msg = (
        "Viewer facial-emotion trajectory (oldest first):\n"
        f"{traj_text}\n\n"
        "Return ONE text-to-image prompt (as JSON) reflecting this emotional change."
    )
    parsed = _chat(
        [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
        temperature=_settings()["temperature"],
    )
    positive = str(parsed.get("positive") or "").strip()
    if not positive:
        raise RuntimeError("DeepSeek 返回缺少 positive 提示词")
    return {
        "positive": positive,
        "negative": str(parsed.get("negative") or "").strip(),
        "scene": str(parsed.get("scene") or "").strip(),
        "reasoning": str(parsed.get("reasoning") or "").strip(),
    }


def test_connection() -> dict:
    """用当前设置做一次最小调用，验证密钥/地址/模型是否可用。

    成功返回 {model}；失败抛 RuntimeError（由路由层转成 HTTP 错误）。
    """
    parsed = _chat(
        [{"role": "user", "content": 'Reply strictly as JSON: {"ok": true}.'}],
        temperature=0,
        max_tokens=20,
    )
    return {"model": _settings()["model"], "reply": parsed}
