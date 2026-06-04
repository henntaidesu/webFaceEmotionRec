// 推理模型注册表接口（经 Vite 代理转发到 :9501 的 /api/models*）

/** 列出可用模型（内置 + 自训），含 active 标记 */
export async function fetchModels() {
  const res = await fetch('/api/models')
  if (!res.ok) throw new Error('fetch models failed')
  return res.json()
}

/** 切换当前激活模型 */
export async function setActiveModel(id) {
  const res = await fetch('/api/models/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `switch failed [${res.status}]`)
  return data
}

/** 删除一个自训模型 */
export async function deleteModel(id) {
  const res = await fetch(`/api/models/${encodeURIComponent(id)}`, { method: 'DELETE' })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `delete failed [${res.status}]`)
  return data
}
