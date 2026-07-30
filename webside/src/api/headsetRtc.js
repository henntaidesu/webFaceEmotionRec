/**
 * 头显视角的 WebRTC 接收端：画面由头显直接推给本浏览器，**不经过后端**。
 * 后端只在建连时转交一次 SDP（见 backend/src/use_web/rtc_signal.py）。
 *
 * 本模块只做「收」：浏览器是 answerer，头显是 offerer。轮询 /rtc/offer 这个动作
 * 本身就在告诉后端「有人在看」，头显据此才开编码——所以 stop() 后必须真的停轮询。
 */

/** ICE 服务器表（后端从 conf.ini [webrtc] 实时读，两端共用同一份）。 */
async function fetchIceServers() {
  const r = await fetch('/api/headset/rtc/config')
  if (!r.ok) throw new Error(`rtc config failed [${r.status}]`)
  const data = await r.json()
  return data.iceServers || []
}

/** 取头显的 offer；顺带向后端登记「有人在看」。暂无 offer 时返回 null。 */
async function fetchOffer() {
  const r = await fetch('/api/headset/rtc/offer')
  if (r.status !== 200) return null
  return r.json()
}

async function postAnswer(session, sdp) {
  await fetch('/api/headset/rtc/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session, sdp }),
  })
}

/** 离开页面：让后端立刻作废会话，头显下次轮询即停止编码。 */
function postBye() {
  // 关页面场景下 fetch 会被取消，用 sendBeacon 才送得出去
  const blob = new Blob(['{}'], { type: 'application/json' })
  if (navigator.sendBeacon) navigator.sendBeacon('/api/headset/rtc/bye', blob)
  else fetch('/api/headset/rtc/bye', { method: 'POST', keepalive: true }).catch(() => {})
}

/**
 * 建立并维持「头显视角」链路。
 * @param {(stream: MediaStream|null) => void} onStream 收到/断开视频流时回调
 * @param {(state: string) => void} onState 连接状态：idle|waiting|connecting|live|failed
 * @returns {{start: () => void, stop: () => void}}
 */
export function createHeadsetViewLink({ onStream, onState }) {
  let alive = false
  let pc = null
  let session = -1
  let timer = null
  let iceServers = null

  const setState = (s) => onState && onState(s)

  function teardown() {
    if (pc) {
      pc.onicecandidate = null
      pc.ontrack = null
      pc.onconnectionstatechange = null
      pc.close()
      pc = null
    }
    session = -1
    onStream && onStream(null)
  }

  /** vanilla ICE：等候选收集完再回 answer，候选直接内嵌在 SDP 里，信令只需一来一回。
   *  若 TURN 不可达，gathering 会卡到超时，所以最多等 3 秒就用已收集到的发出去。 */
  function waitIceGathering(peer) {
    if (peer.iceGatheringState === 'complete') return Promise.resolve()
    return new Promise((resolve) => {
      const done = () => {
        peer.removeEventListener('icegatheringstatechange', check)
        clearTimeout(t)
        resolve()
      }
      const check = () => { if (peer.iceGatheringState === 'complete') done() }
      const t = setTimeout(done, 3000)
      peer.addEventListener('icegatheringstatechange', check)
    })
  }

  async function accept(offer) {
    teardown()
    session = offer.session
    setState('connecting')

    pc = new RTCPeerConnection({ iceServers })
    pc.ontrack = (e) => {
      if (e.streams && e.streams[0]) onStream && onStream(e.streams[0])
    }
    pc.onconnectionstatechange = () => {
      if (!pc) return
      // disconnected 是 WebRTC 的暂态，多半自己会恢复，不处理；只有真断了才重来
      if (pc.connectionState === 'connected') setState('live')
      else if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
        setState('failed')
        teardown()
        // 通知后端作废本次会话：头显下一拍 watch 会拆连接，
        // 再下一拍看到我们仍在轮询就重发 offer —— 约 3 秒自动重连。
        postBye()
      }
    }

    await pc.setRemoteDescription({ type: 'offer', sdp: offer.sdp })
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await waitIceGathering(pc)
    await postAnswer(session, pc.localDescription.sdp)
  }

  async function loop() {
    if (!alive) return
    try {
      if (!iceServers) iceServers = await fetchIceServers()
      const offer = await fetchOffer()
      if (offer && offer.session !== session) await accept(offer)
      else if (!offer && !pc) setState('waiting')
    } catch (e) {
      if (pc) { teardown(); setState('failed') }
    }
    if (alive) timer = setTimeout(loop, 1000)
  }

  return {
    start() {
      if (alive) return
      alive = true
      setState('waiting')
      loop()
    },
    stop() {
      if (!alive) return
      alive = false
      if (timer) { clearTimeout(timer); timer = null }
      teardown()
      postBye()
      setState('idle')
    },
  }
}
