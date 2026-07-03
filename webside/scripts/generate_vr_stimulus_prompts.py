"""生成 VR 情绪刺激图提示词库 → webside/public/vr_stimulus_prompts.csv

每条是一个「能诱导某种情绪」的 360° 全景场景（等距圆柱投影），
用于「VR 刺激图」面板：戴 Quest Pro 的受试者看到该沉浸场景后自然做出对应表情。

提示词素材（场景 / 氛围 / 画质）不写在代码里，统一存放在
`vr_stimulus_sources.csv`（列：emotion,kind,text；kind ∈ scene/mood/quality，
quality 行 emotion 填 `all`，为所有情绪共用）。本脚本读取该表，
对每类情绪做 scene × mood × quality 组合，去重后写出成品 CSV。

与项目其余数据脚本保持一致，用 Python 编写（无第三方依赖）。
运行：python webside/scripts/generate_vr_stimulus_prompts.py
"""
import csv
import os

# 全景触发前缀（与前端 PANO_PREFIX 保持一致，喂给全景 LoRA）
PREFIX = (
    "360 panorama, equirectangular projection, full spherical seamless panorama, photograph, "
)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(HERE, "vr_stimulus_sources.csv")
OUT_PATH = os.path.normpath(os.path.join(HERE, "..", "public", "vr_stimulus_prompts.csv"))


def load_sources(path):
    """读素材表 → (scenes_by_emotion, moods_by_emotion, qualities)。保持文件内出现顺序。"""
    scenes, moods, qualities = {}, {}, []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            emotion = (row["emotion"] or "").strip()
            kind = (row["kind"] or "").strip()
            text = (row["text"] or "").strip()
            if not text:
                continue
            if kind == "quality":
                qualities.append(text)
            elif kind == "scene":
                scenes.setdefault(emotion, []).append(text)
            elif kind == "mood":
                moods.setdefault(emotion, []).append(text)
    return scenes, moods, qualities


def main():
    scenes, moods, qualities = load_sources(SRC_PATH)

    lines = ["emotion,prompt"]
    per_emotion = {}
    for emotion in scenes:
        seen = set()
        for scene in scenes[emotion]:
            for mood in moods.get(emotion, []):
                for q in qualities:
                    prompt = f"{PREFIX}{scene}, {mood}, {q}"
                    if prompt in seen:
                        continue
                    seen.add(prompt)
                    escaped = prompt.replace('"', '""')
                    lines.append(f'{emotion},"{escaped}"')
        per_emotion[emotion] = len(seen)

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")

    summary = ", ".join(f"{e}={n}" for e, n in per_emotion.items())
    print(f"wrote {len(lines) - 1} stimulus prompts -> {OUT_PATH}")
    print(f"per emotion: {summary}")


if __name__ == "__main__":
    main()
