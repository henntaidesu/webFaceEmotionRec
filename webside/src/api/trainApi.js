// 模型训练后端接口（经 Vite 代理转发到 :9501 的 /api/train/*）

/** 获取可训练数据集及计数 */
export async function fetchDatasets() {
  const res = await fetch('/api/train/datasets')
  if (!res.ok) throw new Error('fetch datasets failed')
  return res.json()
}

/** 查询训练状态快照 */
export async function fetchStatus() {
  const res = await fetch('/api/train/status')
  if (!res.ok) throw new Error('fetch status failed')
  return res.json()
}

/** 启动训练。冲突(409)/参数错(400) 时抛出含后端消息的 Error */
export async function startTraining(params) {
  const res = await fetch('/api/train/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `start failed [${res.status}]`)
  return data
}

/** 停止当前训练 */
export async function stopTraining() {
  const res = await fetch('/api/train/stop', { method: 'POST' })
  if (!res.ok) throw new Error('stop failed')
  return res.json()
}
