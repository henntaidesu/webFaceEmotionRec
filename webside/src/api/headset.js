/**
 * 头显 USB 连接（后端用 adb 反向隧道，网页驱动）。
 * 连上后，头显里 Unity 应用把后端地址设为 http://127.0.0.1:9501 即经数据线直达后端。
 */

/** 查询头显 USB 连接状态。 */
export async function getHeadsetStatus() {
  const r = await fetch('/api/headset/status')
  if (!r.ok) throw new Error(`headset status failed [${r.status}]`)
  return r.json()
}

/**
 * 连接头显：建立 adb 反向隧道（+可选启动应用）。
 * @param {boolean} launch 连上后是否自动启动头显里的应用
 */
export async function connectHeadset(launch = true) {
  const r = await fetch('/api/headset/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ launch }),
  })
  if (!r.ok) throw new Error(`headset connect failed [${r.status}]`)
  return r.json()
}
