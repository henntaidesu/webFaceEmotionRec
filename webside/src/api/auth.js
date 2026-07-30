/**
 * 网页登录。
 *
 * 会话放在后端种的 HttpOnly Cookie 里，同源 fetch / WebSocket 握手都会自动带上，
 * 所以其它 api/*.js 和 EmotionDetector 的 WebSocket 都不用改。
 */

/** 要不要登录（后端 conf.ini [auth] 配了口令没）、当前是否已登录。 */
export async function getAuthStatus() {
  const r = await fetch('/api/auth/status')
  if (!r.ok) throw new Error(`auth status failed [${r.status}]`)
  return r.json()
}

export async function login(username, password) {
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `login failed [${r.status}]`)
  return data
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' })
}
