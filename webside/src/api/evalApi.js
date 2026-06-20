// 模型评测后端接口（经 Vite 代理转发到 :9501 的 /api/eval/*）

/** 获取可评测的模型与数据集（含 val/test 计数） */
export async function fetchTargets() {
  const res = await fetch('/api/eval/targets')
  if (!res.ok) throw new Error('fetch targets failed')
  return res.json()
}

/** 查询评测状态快照 */
export async function fetchStatus() {
  const res = await fetch('/api/eval/status')
  if (!res.ok) throw new Error('fetch status failed')
  return res.json()
}

/** 启动评测。冲突(409)/参数错(400) 时抛出含后端消息的 Error */
export async function startEval(params) {
  const res = await fetch('/api/eval/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `start failed [${res.status}]`)
  return data
}

/** 停止当前评测 */
export async function stopEval() {
  const res = await fetch('/api/eval/stop', { method: 'POST' })
  if (!res.ok) throw new Error('stop failed')
  return res.json()
}

/** 列出全部历史评测记录 */
export async function fetchRuns() {
  const res = await fetch('/api/eval/runs')
  if (!res.ok) throw new Error('fetch runs failed')
  return res.json()
}

/** 获取某次评测的完整结果（含混淆矩阵与逐类指标） */
export async function fetchRun(evalId) {
  const res = await fetch(`/api/eval/runs/${encodeURIComponent(evalId)}`)
  if (!res.ok) throw new Error('fetch run failed')
  return res.json()
}

/** 删除一次评测记录 */
export async function deleteRun(evalId) {
  const res = await fetch(`/api/eval/runs/${encodeURIComponent(evalId)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('delete failed')
  return res.json()
}
