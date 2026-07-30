/**
 * 头显在线状态。
 *
 * 头显和笔记本都会被带到外网，服务器留在家里——两边都在别人家的 NAT 后面，服务器
 * **主动连不进去**，所以 adb（无论 USB 还是 adb connect）在真实场景下都用不上。
 * 唯一可靠的在线信号是头显应用自己往外发的请求：它每秒 GET 一次
 * /api/stimulus/control?client=vr，后端记下时间戳，这里读回来判断在不在线。
 *
 * 同理，「远程拉起头显里的应用」做不到——没有 adb 就没有远程启动的手段，
 * 必须有人在头显里点开应用。
 */

/** 头显应用是否在线 + 它该连的服务器地址。 */
export async function getHeadsetPresence() {
  const r = await fetch('/api/headset/presence')
  if (!r.ok) throw new Error(`headset presence failed [${r.status}]`)
  return r.json()
}
