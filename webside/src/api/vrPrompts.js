/**
 * VR 情感提示词库（/vr_emotion_prompts.csv，由 scripts/generate_vr_prompts.mjs 生成）。
 * 首次抽取时加载并按情感分组缓存。
 */
let promptsByEmotion = null

async function loadPrompts() {
  const res = await fetch('/vr_emotion_prompts.csv')
  if (!res.ok) throw new Error(`load prompts failed [${res.status}]`)
  const text = await res.text()
  const grouped = {}
  for (const line of text.split('\n').slice(1)) {
    // 生成格式固定为：emotion,"prompt"（prompt 内的引号转义为 ""）
    const m = line.match(/^(\w+),"((?:[^"]|"")*)"\s*$/)
    if (!m) continue
    const list = (grouped[m[1]] ??= [])
    list.push(m[2].replace(/""/g, '"'))
  }
  promptsByEmotion = grouped
}

/**
 * 随机抽取一条提示词。
 * @param {string} emotionKey 情感 key（happy/sad/...）；为空则随机选一种情感
 * @returns {Promise<{emotion: string, prompt: string}>}
 */
export async function randomVrPrompt(emotionKey = '') {
  if (!promptsByEmotion) await loadPrompts()
  const keys = Object.keys(promptsByEmotion)
  if (keys.length === 0) throw new Error('prompt library is empty')
  const emotion =
    emotionKey && promptsByEmotion[emotionKey]
      ? emotionKey
      : keys[Math.floor(Math.random() * keys.length)]
  const list = promptsByEmotion[emotion]
  return { emotion, prompt: list[Math.floor(Math.random() * list.length)] }
}
