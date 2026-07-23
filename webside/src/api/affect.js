// 「情感偏好生成」页的后端接口封装。
// 情绪来源：Quest Pro FEA（/api/fea/latest，头显推 /api/fea）；
// 提示词：DeepSeek（/api/prompt/generate）；存储：Postgres/pgvector（/api/affect/*）。

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${res.status}`)
  }
  return data
}

// 功能可用性 + 闭环默认参数（reaction_window_s / like_threshold / cooldown_s）
export async function affectStatus() {
  const res = await fetch('/api/affect/status')
  return res.json()
}

// 取最近一帧 Quest Pro FEA 情绪：{success, timestamp_ms, faces:[{dominant_en,dominant,emotions}]}
export async function fetchFeaLatest() {
  const res = await fetch('/api/fea/latest')
  return res.json()
}

// DeepSeek：情感变化轨迹 → {positive, negative, scene, reasoning}
export async function generatePrompt(trajectory, current, locale = 'zh') {
  return postJson('/api/prompt/generate', { trajectory, current, locale })
}

// DeepSeek（场景驱动，刺激页闭环用）：目标情绪 + 基础场景 + 强度指令 → {positive,negative,scene,reasoning}
export async function generateScenePrompt(emotion, scene, directive, locale = 'zh') {
  return postJson('/api/prompt/scene', { emotion, scene, directive, locale })
}

// 采集会话生命周期
export function startSession(subjectId, meta) {
  return postJson('/api/affect/session/start', { subject_id: subjectId, meta })
}
export function stopSession(sessionId) {
  return postJson('/api/affect/session/stop', { session_id: sessionId })
}

// 2D 摄像头模式下推送情绪时间轴样本（头显模式由 /api/fea 自动写盘，无需调用）
export function pushSamples(sessionId, rows) {
  return postJson('/api/affect/sample', { session_id: sessionId, rows })
}

// 记录一条生成图偏好（含情绪情境向量、提示词、反应、是否喜欢）
export function recordImage(rec) {
  return postJson('/api/affect/image', rec)
}

// 按当前情绪情境检索用户喜欢过的相似图（pgvector 最近邻）
export function recommend(emotions, k = 5, subjectId) {
  return postJson('/api/affect/recommend', { emotions, k, subject_id: subjectId })
}
