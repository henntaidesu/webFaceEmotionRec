/**
 * VR 情绪刺激场景库（/vr_stimulus_prompts.csv，由 scripts/generate_vr_stimulus_prompts.py 生成）。
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

/**
 * 把已生成的刺激图回传后端，存入 image/<emotion>/<时间戳>.png。
 * 先按可访问 URL（ComfyUI /view，经 Vite 代理）拉取图像字节，再 base64 回传。
 * @param {string} url     图片可访问地址
 * @param {string} emotion 情感 key（happy/sad/...）
 * @param {string} [folder] 可选：image/ 下的分组子目录
 * @returns {Promise<{ok: boolean, path?: string, filename?: string}>}
 */
export async function saveStimulusImage(url, emotion, folder = '', { show = false } = {}) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch image failed [${res.status}]`)
  const blob = await res.blob()
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('read image failed'))
    reader.readAsDataURL(blob)
  })
  const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg')
  // show=true 时后端同时把这张图标记为「当前」，Quest Pro 上的 Unity 会轮询并贴到全景天空盒。
  const saveRes = await fetch('/api/stimulus/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ emotion, folder, ext, image: dataUrl, show }),
  })
  if (!saveRes.ok) throw new Error(`save failed [${saveRes.status}]`)
  return saveRes.json()
}

/**
 * 把一张已保存的历史刺激图推送到 VR 头显显示（用于「查看历史图片」里手动推送）。
 * @param {string} path 后端返回的相对路径（image/<emotion>/xxx.png 或 <emotion>/xxx.png）
 * @returns {Promise<{ok: boolean, version?: number, url?: string}>}
 */
export async function showStimulusInHeadset(path) {
  const res = await fetch('/api/stimulus/show', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) throw new Error(`show failed [${res.status}]`)
  return res.json()
}
