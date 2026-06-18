// 生成 VR 情感提示词库：7 类情感 × 每类 1000 条，输出 public/vr_emotion_prompts.csv
// 用法：node scripts/generate_vr_prompts.mjs
// 组合式生成（前缀 × 人物 × 头显 × 遮挡描述 × 表情 × 构图 × 光照 × 背景 × 画质），
// 固定随机种子，结果可复现。
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const PER_EMOTION = 1000

// ── 可复现的伪随机数（mulberry32） ──────────────────────
function mulberry32(seed) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const rand = mulberry32(20260611)
const pick = (arr) => arr[Math.floor(rand() * arr.length)]

// ── 素材池 ──────────────────────────────────────────────
const PREFIXES = [
  'masterpiece, best quality, ultra detailed, photorealistic portrait photograph of',
  'masterpiece, best quality, realistic photo of',
  'best quality, highly detailed, professional portrait photo of',
  'masterpiece, photorealistic, studio portrait of',
]

const AGES = ['young', 'teenage', 'middle-aged', 'elderly', 'adult']
const GENDERS = ['man', 'woman']
const APPEARANCES = ['', 'asian ', 'east asian ', 'european ', 'african ', 'hispanic ', 'middle eastern ', 'indian ']

const HEADSETS = [
  'modern white VR headset',
  'sleek black VR headset',
  'futuristic silver VR headset',
  'compact gray VR headset',
  'glossy white VR goggles',
  'matte black VR goggles',
  'high-tech VR head-mounted display',
  'wireless VR headset with head strap',
]

const OCCLUSIONS = [
  'head-mounted display covering both eyes, mouth and chin clearly visible',
  'eyes fully occluded by the VR visor, expressive lower face visible',
  'upper half of face hidden behind the VR headset, jaw and lips clearly visible',
  'VR goggles covering the eyes, visible mouth and chin',
]

const FRAMINGS = [
  'front view, head and shoulders portrait',
  'close-up portrait, front view',
  'slight three-quarter view portrait',
  'medium close-up, centered composition',
  'head-and-shoulders shot, eye-level camera',
  'tight portrait framing, frontal angle',
  'upper body portrait, facing camera',
  'close-up face shot, symmetrical composition',
]

const LIGHTINGS = [
  'studio lighting',
  'soft diffused lighting',
  'dramatic side lighting',
  'neon ambient lighting',
  'cinematic lighting',
  'natural window light',
  'rim lighting',
  'softbox lighting',
  'moody low-key lighting',
  'bright high-key lighting',
  'warm golden lighting',
  'cool blue tech lighting',
]

const BACKGROUNDS = [
  'clean neutral background',
  'plain white background',
  'dark gray studio background',
  'blurred tech lab background',
  'futuristic interior background',
  'soft gradient background',
  'dimly lit room background',
  'minimalist office background',
  'blurred living room background',
  'black seamless background',
  'cyberpunk neon background with bokeh',
  'white seamless backdrop',
]

const QUALITIES = [
  'sharp focus, detailed skin texture',
  'sharp focus, high detail, 8k',
  'ultra detailed, realistic skin pores',
  'crisp details, professional photography',
  'high resolution, fine skin detail',
  'detailed texture, dslr photo',
]

// 眼部被遮挡，表情全部通过口部 / 下颌 / 姿态表达
const EXPRESSIONS = {
  happy: [
    'joyful expression, wide open-mouth smile, raised cheeks',
    'cheerful grin, bright smile, lifted cheeks',
    'laughing happily, open mouth laugh, joyful mood',
    'delighted expression, beaming smile, dimpled cheeks',
    'broad smile showing teeth, happy mood',
    'gentle happy smile, relaxed joyful face',
    'excited happy expression, grinning widely',
    'warm smile, slightly parted lips, content mood',
    'euphoric expression, big laughing smile',
    'playful grin, upturned mouth corners',
    'radiant smile, cheerful energy',
    'amused smile, soft laughter',
  ],
  sad: [
    'sad expression, downturned mouth corners, frowning lips',
    'sorrowful look, trembling lower lip, slightly lowered head',
    'grieving expression, tight downturned mouth',
    'melancholic mood, drooping mouth, slumped shoulders',
    'crying expression, tears on cheeks below the headset, quivering lips',
    'deep sadness, pressed downturned lips, sunken cheeks',
    'dejected expression, slack downturned mouth',
    'mournful face, tight lips pulled downward',
    'heartbroken expression, trembling chin',
    'gloomy mood, faint frown, lowered chin',
    'sobbing expression, open downturned mouth',
    'despairing look, drawn-down mouth corners, head tilted down',
  ],
  angry: [
    'angry expression, clenched jaw, gritted teeth',
    'furious look, snarling mouth, tense lips',
    'rage expression, bared teeth, tight jaw muscles',
    'irritated scowl, pressed thin lips',
    'enraged expression, open shouting mouth',
    'aggressive grimace, flared nostrils, clenched teeth',
    'seething anger, tightly compressed lips, tense neck',
    'hostile expression, curled lip, rigid jaw',
    'yelling angrily, wide open tense mouth',
    'frustrated anger, jaw thrust forward, tight mouth',
    'wrathful expression, twisted snarl',
    'fuming mood, hard set mouth, tensed chin',
  ],
  surprise: [
    'surprised expression, wide open mouth, dropped jaw',
    'astonished look, gasping open mouth, hands raised near face',
    'shocked expression, jaw dropped wide',
    'amazed reaction, rounded open lips',
    'startled expression, sudden open-mouth gasp',
    'stunned look, parted lips frozen open',
    'speechless surprise, hand covering open mouth',
    'overwhelmed astonishment, mouth agape',
    'sudden shock, sharply inhaling open mouth',
    'wide-mouthed disbelief, tilted head',
    'jaw-dropping amazement, leaning back slightly',
    'gasping in wonder, round open mouth',
  ],
  fear: [
    'fearful expression, trembling open mouth, tense grimace',
    'terrified look, quivering lips, defensive posture',
    'frightened expression, drawn-back lips, rigid jaw',
    'panicked mood, gasping mouth, hunched shoulders',
    'horrified expression, frozen open mouth',
    'anxious fear, tightly pressed trembling lips',
    'scared expression, grimacing mouth pulled wide',
    'dread-filled look, pale face, shaking chin',
    'alarmed expression, half-open quivering mouth',
    'cowering in fear, lips stretched tight, raised shoulders',
    'petrified look, stiff open mouth',
    'nervous terror, biting lower lip, tensed neck',
  ],
  disgust: [
    'disgusted expression, wrinkled nose, raised upper lip',
    'repulsed look, sneering mouth, curled lip',
    'revolted expression, grimacing twisted mouth',
    'nauseated look, scrunched nose, tongue slightly out',
    'scornful sneer, one-sided raised lip',
    'strong aversion, recoiling head, wrinkled nose',
    'grossed-out expression, gagging open mouth',
    'displeased grimace, tight puckered lips',
    'repelled look, upper lip pulled upward',
    'queasy expression, downturned grimace, scrunched nose',
    'averse reaction, head turned slightly away, sneer',
    'disgusted scowl, nose wrinkled, lips parted in distaste',
  ],
  neutral: [
    'neutral expression, relaxed closed mouth, calm face',
    'calm composed look, resting face',
    'expressionless face, softly closed lips',
    'serene mood, relaxed jaw, still posture',
    'blank neutral look, natural relaxed lips',
    'peaceful expression, gently closed mouth',
    'composed face, level chin, relaxed muscles',
    'placid expression, neutral resting mouth',
    'tranquil look, loose relaxed lips',
    'emotionless face, straight closed mouth',
    'at-ease expression, natural soft lips',
    'quiet calm face, relaxed lower face',
  ],
}

// ── 生成 ────────────────────────────────────────────────
function buildPrompt(emotion) {
  const subject = `${pick(AGES)} ${pick(APPEARANCES)}${pick(GENDERS)}`
  return [
    `${pick(PREFIXES)} one ${subject} wearing a ${pick(HEADSETS)}`,
    pick(OCCLUSIONS),
    pick(EXPRESSIONS[emotion]),
    pick(FRAMINGS),
    pick(LIGHTINGS),
    pick(BACKGROUNDS),
    pick(QUALITIES),
  ].join(', ')
}

const csvField = (s) => `"${s.replace(/"/g, '""')}"`

const rows = ['emotion,prompt']
for (const emotion of Object.keys(EXPRESSIONS)) {
  const seen = new Set()
  while (seen.size < PER_EMOTION) {
    seen.add(buildPrompt(emotion))
  }
  for (const p of seen) rows.push(`${emotion},${csvField(p)}`)
}

const outDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public')
fs.mkdirSync(outDir, { recursive: true })
const outFile = path.join(outDir, 'vr_emotion_prompts.csv')
fs.writeFileSync(outFile, rows.join('\n') + '\n', 'utf8')
console.log(`written ${rows.length - 1} prompts -> ${outFile}`)
