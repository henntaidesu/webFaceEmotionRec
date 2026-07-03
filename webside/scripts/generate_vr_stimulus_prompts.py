"""生成 VR 情绪刺激图提示词库 → webside/public/vr_stimulus_prompts.csv

每条是一个「能诱导某种情绪」的 360° 全景场景（等距圆柱投影），
用于「VR 刺激图」面板：戴 Quest Pro 的受试者看到该沉浸场景后自然做出对应表情。

与项目其余数据脚本保持一致，用 Python 编写（无第三方依赖）。
运行：python webside/scripts/generate_vr_stimulus_prompts.py
"""
import os

PREFIX = (
    "360 panorama, equirectangular projection, full spherical seamless panorama, photograph, "
)

# 每类情绪：核心场景 × 氛围修饰 → 组合出多样的诱导场景
EMOTIONS = {
    "happy": {
        "scenes": [
            "sunny tropical beach paradise, turquoise water, white sand, palm trees",
            "vast blooming flower field under a clear blue sky, butterflies drifting",
            "colorful amusement park with a carousel and floating balloons",
            "cozy sunlit green meadow with playful golden retriever puppies",
            "vibrant summer festival with fireworks and confetti at dusk",
            "rainbow over a lush waterfall valley, birds flying",
            "warm spring cherry blossom park in full bloom, petals in the air",
            "joyful lantern festival with glowing paper lanterns floating up",
        ],
        "moods": ["bright cheerful daylight", "warm golden hour glow", "festive joyful atmosphere", "uplifting radiant mood"],
    },
    "sad": {
        "scenes": [
            "lonely rainy city street at dusk, wet empty pavement",
            "abandoned empty room with dim light and floating dust",
            "foggy grey cemetery under bare leafless trees",
            "desolate autumn forest with falling withered leaves",
            "empty quiet hospital corridor at night",
            "deserted rainy train platform, a single flickering lamp",
            "grey overcast seashore with cold crashing waves, no one around",
            "faded old house interior with covered furniture and cobwebs",
        ],
        "moods": ["grey melancholic mood", "somber sorrowful atmosphere", "cold blue lonely light", "overcast heavy gloom"],
    },
    "angry": {
        "scenes": [
            "chaotic gridlock traffic jam, glaring red brake lights",
            "stormy red sky over a burning industrial wasteland",
            "ruined war-torn city street with rubble and thick smoke",
            "raging wildfire consuming a dark forest, fierce flames surrounding",
            "crowded overwhelming subway platform crushed at rush hour",
            "violent thunderstorm over jagged black volcanic rocks",
            "polluted factory zone with belching smokestacks and grime",
            "turbulent crimson lava field cracking and erupting",
        ],
        "moods": ["intense oppressive atmosphere", "tense hostile mood", "aggressive fiery red tone", "suffocating heat and noise"],
    },
    "surprise": {
        "scenes": [
            "sudden glowing magical portal opening in a mystical forest",
            "surreal floating islands in the sky with cascading waterfalls",
            "spectacular cosmic aurora and an exploding galaxy overhead",
            "giant whimsical creature emerging unexpectedly from the clouds",
            "fantastical crystal cave suddenly revealed, glittering everywhere",
            "a whale gliding impossibly through a sky full of stars",
            "an enormous unexpected fireworks finale bursting all around",
            "a hidden bioluminescent forest lighting up all at once",
        ],
        "moods": ["dazzling light burst", "breathtaking unexpected vista", "awe-inspiring astonishing scene", "wondrous sudden reveal"],
    },
    "fear": {
        "scenes": [
            "dark haunted forest at midnight, twisted trees, menacing shadows",
            "abandoned decaying asylum hallway with flickering lights",
            "standing at the edge of a dizzying tall cliff over a deep abyss",
            "deep pitch-black cave with an unknown lurking presence",
            "creepy foggy graveyard at night with looming tombstones",
            "narrow flooded tunnel in total darkness, distant echoing",
            "derelict horror mansion staircase under a blood moon",
            "endless dark corridor with doors slowly creaking open",
        ],
        "moods": ["eerie chilling terror", "claustrophobic dread", "ominous horror atmosphere", "cold creeping fear"],
    },
    "disgust": {
        "scenes": [
            "overflowing garbage dump with rotting waste and swarming flies",
            "dirty clogged sewer tunnel with grimy dripping sludge",
            "moldy abandoned kitchen with rotten spoiled food",
            "swarm of insects crawling over decaying matter",
            "polluted toxic swamp with murky slime and floating refuse",
            "filthy neglected public restroom, stained and grimy",
            "pile of spoiled meat covered in mold in a dim cellar",
            "stagnant green pond thick with scum and dead fish",
        ],
        "moods": ["revolting filthy scene", "nauseating foul atmosphere", "repulsive decay", "sickening grime"],
    },
    "neutral": {
        "scenes": [
            "plain minimalist empty white studio",
            "quiet serene zen garden with raked sand and stones",
            "calm empty library reading room",
            "gentle misty lake at dawn with flat calm water",
            "simple tidy modern living room",
            "empty softly lit art gallery with blank walls",
            "quiet office space with neutral grey furniture",
            "plain overcast open field, flat horizon",
        ],
        "moods": ["soft even light, calm neutral space", "tranquil balanced stillness", "peaceful quiet mood", "relaxed plain atmosphere"],
    },
}

QUALITY = [
    "ultra detailed, sharp focus, high resolution",
    "cinematic, highly detailed, realistic",
    "photorealistic, rich detail, immersive",
    "crisp detail, natural lighting, lifelike",
]


def main():
    lines = ["emotion,prompt"]
    for emotion, cfg in EMOTIONS.items():
        seen = set()
        for scene in cfg["scenes"]:
            for mood in cfg["moods"]:
                for q in QUALITY:
                    prompt = f"{PREFIX}{scene}, {mood}, {q}"
                    if prompt in seen:
                        continue
                    seen.add(prompt)
                    escaped = prompt.replace('"', '""')
                    lines.append(f'{emotion},"{escaped}"')

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "public", "vr_stimulus_prompts.csv"
    )
    out_path = os.path.normpath(out_path)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {len(lines) - 1} stimulus prompts -> {out_path}")


if __name__ == "__main__":
    main()
