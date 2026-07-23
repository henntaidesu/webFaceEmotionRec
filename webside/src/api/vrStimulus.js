// VR 情绪刺激图的存盘 / 推送接口。提示词已全部改由 DeepSeek 动态生成，
// 旧的静态 CSV 场景库（randomVrStimulus）已删除。

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
 * 上报「下一张图」的生成进度，供 VR 头显里的进度条显示（失败静默，不影响闭环）。
 * @param {{running: boolean, current?: number, max?: number, step?: number, note?: string}} p
 */
export function reportStimulusProgress(p) {
  return fetch('/api/stimulus/progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(p),
  }).catch(() => {})
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
