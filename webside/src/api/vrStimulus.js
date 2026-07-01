/**
 * VR 情绪刺激场景库（/vr_stimulus_prompts.csv，由 scripts/generate_vr_stimulus_prompts.mjs 生成）。
 * 每条是一个能诱导某种情绪的 360° 全景场景。首次抽取时加载并按情感分组缓存。
 */
let scenesByEmotion = null

async function loadScenes() {
  const res = await fetch('/vr_stimulus_prompts.csv')
  if (!res.ok) throw new Error(`load stimulus prompts failed [${res.status}]`)
  const text = await res.text()
  const grouped = {}
  for (const line of text.split('\n').slice(1)) {
    const m = line.match(/^(\w+),"((?:[^"]|"")*)"\s*$/)
    if (!m) continue
    const list = (grouped[m[1]] ??= [])
    list.push(m[2].replace(/""/g, '"'))
  }
  scenesByEmotion = grouped
}

/**
 * 随机抽取一条刺激场景提示词。
 * @param {string} emotionKey 情感 key（happy/sad/...）；为空则随机选一种情感
 * @returns {Promise<{emotion: string, prompt: string}>}
 */
export async function randomVrStimulus(emotionKey = '') {
  if (!scenesByEmotion) await loadScenes()
  const keys = Object.keys(scenesByEmotion)
  if (keys.length === 0) throw new Error('stimulus library is empty')
  const emotion =
    emotionKey && scenesByEmotion[emotionKey]
      ? emotionKey
      : keys[Math.floor(Math.random() * keys.length)]
  const list = scenesByEmotion[emotion]
  return { emotion, prompt: list[Math.floor(Math.random() * list.length)] }
}
