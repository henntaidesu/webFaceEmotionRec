<template>
  <div class="comfy-panel">
    <div class="comfy-header">
      <div class="header-left">
        <span class="panel-title">{{ locale.affective.title }}</span>
        <span class="server-addr">{{ COMFYUI_HOST }}</span>
      </div>
      <div class="header-right">
        <span class="conn-badge" :class="online ? 'conn-ok' : 'conn-off'">
          <span class="conn-dot"></span>{{ online ? locale.comfyConnected : locale.comfyDisconnected }}
        </span>
        <button class="icon-btn" :title="locale.comfyRetry" @click="retryConn">↻</button>
      </div>
    </div>

    <div class="comfy-body">
      <p class="panel-desc">{{ locale.affective.desc }}</p>

      <!-- 摄像头 + 实时情感 -->
      <div class="cam-row">
        <div class="cam-wrap">
          <video v-show="source === 'webcam'" ref="videoEl" class="cam-video" autoplay playsinline muted></video>
          <div v-if="source === 'quest'" class="cam-ph">🥽</div>
          <div v-else-if="!cameraActive" class="cam-ph">{{ locale.cameraPlaceholderIcon }}</div>
        </div>
        <div class="emo-live">
          <div class="emo-dom" v-if="cur.dominant_en">
            {{ emoEmoji(cur.dominant_en) }} <strong>{{ cur.dominant_zh }}</strong>
          </div>
          <div v-else class="emo-dom muted">{{ locale.affective.noEmotion }}</div>
          <div v-for="e in EN_CLASSES" :key="e" class="bar-row">
            <span class="bar-label">{{ locale.emotionMap[EN2ZH[e]] }}</span>
            <div class="bar"><div class="bar-fill" :style="{ width: (cur.probs[e] || 0) + '%' }"></div></div>
            <span class="bar-val">{{ Math.round(cur.probs[e] || 0) }}</span>
          </div>
        </div>
      </div>

      <!-- 控制 -->
      <div class="row-group">
        <select v-model="source" class="ctrl-select src-select" :disabled="active">
          <option value="webcam">{{ locale.affective.srcWebcam }}</option>
          <option value="quest">{{ locale.affective.srcQuest }}</option>
        </select>
        <button class="btn-mini" @click="toggleSource">
          {{ active ? locale.affective.stop : locale.affective.start }}
        </button>
        <label class="inline"><input type="checkbox" v-model="autoMode" /> {{ locale.affective.auto }}</label>
        <label class="inline">{{ locale.affective.cooldown }}
          <input type="number" v-model.number="cooldownSec" class="num-mini" min="3" max="120" />s</label>
      </div>
      <p v-if="source === 'quest'" class="batch-hint">{{ locale.affective.questHint }}</p>

      <div class="field">
        <label class="field-label">{{ locale.affective.genMode }}</label>
        <select v-model="genMode" class="ctrl-select">
          <option value="builtin">{{ locale.affective.genBuiltin }}</option>
          <option value="workflow">{{ locale.affective.genWorkflow }}</option>
        </select>
      </div>

      <div v-if="genMode === 'builtin'" class="field">
        <label class="field-label">{{ locale.comfyModel }}</label>
        <select v-model="checkpoint" class="ctrl-select">
          <option v-if="checkpoints.length === 0" value="">{{ locale.affective.noCkpt }}</option>
          <option v-for="c in checkpoints" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <div v-else class="field">
        <label class="field-label">{{ locale.comfyWorkflow }}</label>
        <select v-model="selectedWorkflow" class="ctrl-select">
          <option v-if="workflows.length === 0" value="">{{ locale.affective.noWorkflow }}</option>
          <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf.replace(/\.json$/, '') }}</option>
        </select>
      </div>

      <button class="btn-generate" :disabled="generating || !cur.dominant_en || !canGenerate" @click="() => generate('manual')">
        <span v-if="generating">{{ locale.affective.generating }}<span v-if="progress.max"> · {{ progress.current }}/{{ progress.max }}</span></span>
        <span v-else>⚡ {{ locale.affective.generateNow }}</span>
      </button>
      <p v-if="statusMsg" class="status-msg" :class="statusCls">{{ statusMsg }}</p>

      <!-- 情感→风格映射（可编辑） -->
      <details class="art-box">
        <summary>{{ locale.affective.artTitle }}</summary>
        <textarea v-model="artText" class="art-text" rows="8" spellcheck="false"></textarea>
        <div class="row-group">
          <button class="btn-mini" @click="applyArt">{{ locale.affective.artApply }}</button>
          <button class="btn-mini" @click="resetArt">{{ locale.affective.artResetBtn }}</button>
          <span v-if="artMsg" class="art-msg">{{ artMsg }}</span>
        </div>
      </details>

      <!-- 采集会话 -->
      <div class="batch-box">
        <div class="batch-title">🎞 {{ locale.affective.session }}（{{ sessionLog.length }}）</div>
        <div class="row-group">
          <button class="btn-mini" :disabled="sessionLog.length === 0" @click="exportCsv">⬇ {{ locale.affective.exportCsv }}</button>
          <button class="btn-mini" @click="syncBeacon">✦ {{ locale.affective.syncBeacon }}</button>
          <button class="btn-mini" :disabled="sessionLog.length === 0" @click="sessionLog = []">✕ {{ locale.stimulus.clear }}</button>
        </div>
        <p class="batch-hint" v-if="lastSyncTs">{{ locale.affective.lastSync }}: {{ lastSyncTs }}</p>
      </div>

      <!-- 结果 -->
      <div v-if="results.length" class="result-grid">
        <div v-for="(r, i) in results" :key="i" class="result-item">
          <img :src="r.url" class="result-img" @click="lightbox = r.url" />
          <span class="emo-tag">{{ r.label }}</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="flash" class="sync-flash"></div>
      <div v-if="lightbox" class="lightbox" @click="lightbox = null">
        <img :src="lightbox" class="lightbox-img" @click.stop />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import {
  checkOnline, fetchCheckpoints, buildTxt2ImgWorkflow, queuePrompt,
  getHistory, imageUrl, makeClientId, openProgressWS, COMFYUI_HOST,
  fetchWorkflows, fetchWorkflow, fetchObjectInfo, uiToApiFormat, applyPromptOverrides,
} from '../api/comfyuiApi.js'

const props = defineProps({ locale: { type: Object, required: true } })

const EN_CLASSES = ['happy', 'sad', 'angry', 'surprise', 'fear', 'disgust', 'neutral']
const EN2ZH = { happy: '开心', sad: '悲伤', angry: '愤怒', surprise: '惊讶', fear: '恐惧', disgust: '厌恶', neutral: '平静' }
const ZH2EN = Object.fromEntries(Object.entries(EN2ZH).map(([en, zh]) => [zh, en]))

// 情感 → 生成风格提示词（默认；可在页面编辑）
const DEFAULT_ART = {
  happy: 'joyful vibrant abstract art, warm bright colors, uplifting energy, dynamic swirls',
  sad: 'melancholic abstract art, cool blue tones, rain, somber soft mood',
  angry: 'intense abstract art, fiery red and black, sharp aggressive strokes, chaotic energy',
  surprise: 'surreal art, bursting light, unexpected shapes, electric vivid colors',
  fear: 'eerie dark abstract art, shadowy tones, tense unsettling atmosphere',
  disgust: 'murky abstract art, sickly green tones, distorted textures',
  neutral: 'calm minimalist abstract art, balanced neutral tones, serene composition',
}
const NEG = 'lowres, worst quality, blurry, text, watermark'

// 可编辑的情感→风格映射：artMap 为生效值，artText 为编辑框文本
const artMap = reactive({ ...DEFAULT_ART })
const artText = ref(JSON.stringify(DEFAULT_ART, null, 2))
const artMsg = ref('')
function applyArt() {
  try {
    const obj = JSON.parse(artText.value)
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) throw new Error('need object')
    for (const [k, v] of Object.entries(obj)) {
      if (typeof v !== 'string') throw new Error(`"${k}" 的值必须是字符串`)
    }
    // 仅接受 7 类 key，缺失的用默认补齐
    const next = { ...DEFAULT_ART }
    for (const k of EN_CLASSES) if (typeof obj[k] === 'string') next[k] = obj[k]
    Object.assign(artMap, next)
    artMsg.value = props.locale.affective.artApplied
  } catch (e) {
    artMsg.value = `${props.locale.affective.artError}: ${e.message}`
  }
}
function resetArt() {
  Object.assign(artMap, DEFAULT_ART)
  artText.value = JSON.stringify(DEFAULT_ART, null, 2)
  artMsg.value = props.locale.affective.artReset
}

const emoEmoji = (en) => ({ happy: '😄', sad: '😢', angry: '😠', surprise: '😲', fear: '😨', disgust: '🤢', neutral: '😐' }[en] || '🙂')

// ── ComfyUI 连接 ──
const online = ref(false)
const checkpoints = ref([])
const checkpoint = ref('')
const genMode = ref('builtin')        // 'builtin'(内置 txt2img + checkpoint) | 'workflow'(服务器工作流)
const workflows = ref([])
const selectedWorkflow = ref('')
// 是否可生成：内置需 checkpoint；工作流需选中一个
const canGenerate = computed(() =>
  genMode.value === 'workflow' ? !!selectedWorkflow.value : !!checkpoint.value)

async function retryConn() {
  online.value = await checkOnline()
  if (!online.value) return
  if (checkpoints.value.length === 0) {
    try {
      checkpoints.value = await fetchCheckpoints()
      if (checkpoints.value.length && !checkpoint.value) checkpoint.value = checkpoints.value[0]
    } catch { /* 忽略 */ }
  }
  if (workflows.value.length === 0) {
    try { workflows.value = await fetchWorkflows() } catch { /* 忽略 */ }
  }
  // 无 SD checkpoint 但有服务器工作流时，自动切到工作流模式（兼容 Qwen-only 环境）
  if (checkpoints.value.length === 0 && workflows.value.length > 0 && genMode.value === 'builtin') {
    genMode.value = 'workflow'
    if (!selectedWorkflow.value) selectedWorkflow.value = workflows.value[0]
  }
}

// 把 SaveImage 的 filename_prefix 改到 affective/<emotion>/
function setSavePrefix(api, prefix) {
  for (const node of Object.values(api)) {
    if (node.class_type === 'SaveImage' && node.inputs) node.inputs.filename_prefix = prefix
  }
  return api
}

// 按当前生成方式构建工作流：内置 txt2img 或 服务器端工作流（注入情感提示词）
async function buildWorkflowFor(dom, positive) {
  const prefix = `affective/${dom}/${dom}`
  if (genMode.value === 'workflow') {
    const [raw, objectInfo] = await Promise.all([fetchWorkflow(selectedWorkflow.value), fetchObjectInfo()])
    let api = Array.isArray(raw?.nodes) ? uiToApiFormat(raw, objectInfo) : raw
    api = applyPromptOverrides(api, { positive, negative: NEG, seed: -1 })
    return setSavePrefix(api, prefix)
  }
  return buildTxt2ImgWorkflow({
    positive, negative: NEG, checkpoint: checkpoint.value,
    steps: 20, cfg: 7, width: 512, height: 512,
    sampler: 'euler', scheduler: 'normal', seed: -1, filename_prefix: prefix,
  })
}

// ── 情绪来源：2D 摄像头 或 Quest Pro 头显 FEA ──
const source = ref('webcam')          // 'webcam' | 'quest'
const videoEl = ref(null)
const cameraActive = ref(false)       // webcam 运行中
const questActive = ref(false)        // Quest FEA 轮询中
const active = computed(() => cameraActive.value || questActive.value)
const cur = reactive({ dominant_en: '', dominant_zh: '', probs: {} })
let stream = null, emoWs = null, capTimer = null, feaTimer = null
const EMO_FPS = 4
const FEA_POLL_MS = 300

function toggleSource() {
  if (active.value) { stopSource(); return }
  if (source.value === 'webcam') startWebcam()
  else startQuest()
}
function stopSource() { stopCamera(); stopQuest() }

// 两条来源共用：把一帧 face 结构（emotions 为中文 key→百分比）应用到 cur 并触发自动生成
function applyFace(f) {
  if (!f) return
  const probs = {}
  for (const [zh, pct] of Object.entries(f.emotions || {})) {
    const en = ZH2EN[zh]; if (en) probs[en] = pct
  }
  const prevDom = cur.dominant_en
  cur.dominant_en = f.dominant_en || ''
  cur.dominant_zh = f.dominant || ''
  cur.probs = probs
  maybeAutoGenerate(prevDom)
}

// —— 2D 摄像头（图像识别，经 /ws/emotion）——
async function startWebcam() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false })
    videoEl.value.srcObject = stream
    await videoEl.value.play()
    cameraActive.value = true
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    emoWs = new WebSocket(`${proto}://${location.host}/ws/emotion`)
    emoWs.onopen = () => { capTimer = setInterval(sendFrame, Math.round(1000 / EMO_FPS)) }
    emoWs.onmessage = (evt) => {
      let data
      try { data = JSON.parse(evt.data) } catch { return }
      if (!data.success || !data.faces || !data.faces.length) return
      applyFace(data.faces[0])
    }
  } catch (e) {
    statusMsg.value = `${props.locale.cameraErrorPrefix}${e.message}`; statusCls.value = 'msg-error'
  }
}
function stopCamera() {
  if (capTimer) { clearInterval(capTimer); capTimer = null }
  if (emoWs) { emoWs.close(); emoWs = null }
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null }
  cameraActive.value = false
}

// —— Quest Pro 头显 FEA（63 维，头显侧推到后端 /api/fea，此处轮询最新情绪）——
function startQuest() {
  questActive.value = true
  feaTimer = setInterval(pollFea, FEA_POLL_MS)
}
function stopQuest() {
  if (feaTimer) { clearInterval(feaTimer); feaTimer = null }
  questActive.value = false
}
async function pollFea() {
  try {
    const res = await fetch('/api/fea/latest')
    if (!res.ok) return
    const data = await res.json()
    if (data.success && data.faces && data.faces.length) applyFace(data.faces[0])
  } catch { /* 后端未在线或无数据，忽略 */ }
}

function sendFrame() {
  if (!emoWs || emoWs.readyState !== WebSocket.OPEN) return
  if (!videoEl.value || videoEl.value.readyState < 2) return
  const c = document.createElement('canvas')
  c.width = videoEl.value.videoWidth; c.height = videoEl.value.videoHeight
  c.getContext('2d').drawImage(videoEl.value, 0, 0)
  emoWs.send(JSON.stringify({ frame: c.toDataURL('image/jpeg', 0.7) }))
}

// ── 自动随情感变化生成 ──
const autoMode = ref(false)
const cooldownSec = ref(8)
let lastGenAt = 0
function maybeAutoGenerate(prevDom) {
  if (!autoMode.value || generating.value || !canGenerate.value) return
  if (!cur.dominant_en || cur.dominant_en === prevDom) return
  if (Date.now() - lastGenAt < cooldownSec.value * 1000) return
  generate('auto')
}

// ── 生成 ──
const generating = ref(false)
const progress = reactive({ current: 0, max: 0 })
const statusMsg = ref(''); const statusCls = ref('')
const results = ref([])
const lightbox = ref(null)

async function generate(trigger) {
  if (generating.value || !cur.dominant_en || !canGenerate.value) return
  generating.value = true; lastGenAt = Date.now()
  progress.current = 0; progress.max = 0
  const dom = cur.dominant_en
  const probsSnapshot = { ...cur.probs }
  const positive = `masterpiece, expressive art, ${artMap[dom] || dom}`
  const clientId = makeClientId()
  let ws = null
  try {
    const workflow = await buildWorkflowFor(dom, positive)
    ws = openProgressWS(clientId)
    const { prompt_id } = await queuePrompt(clientId, workflow)
    const urls = await waitForImages(ws, prompt_id)
    const url = urls[0] || ''
    if (url) {
      results.value = [{ url, label: `${emoEmoji(dom)} ${EN2ZH[dom]}`, dom }, ...results.value].slice(0, 40)
    }
    sessionLog.push({ ts: Date.now(), dom, probs: probsSnapshot, image: url.split('/').pop() || '', prompt: positive, trigger })
    statusMsg.value = props.locale.affective.done; statusCls.value = 'msg-ok'
  } catch (e) {
    statusMsg.value = `${props.locale.affective.error}: ${e.message}`; statusCls.value = 'msg-error'
  } finally {
    generating.value = false
    if (ws) ws.close()
  }
}

function waitForImages(socket, promptId) {
  return new Promise((resolve, reject) => {
    let settled = false, poll = null
    const done = async () => {
      if (settled) return; settled = true
      socket.removeEventListener('message', onMsg); if (poll) clearInterval(poll)
      try { resolve(await collectImages(promptId)) } catch (e) { reject(e) }
    }
    function onMsg(e) {
      let m; try { m = JSON.parse(e.data) } catch { return }
      if (m.type === 'progress' && m.data?.prompt_id === promptId) { progress.current = m.data.value; progress.max = m.data.max }
      if ((m.type === 'execution_success' && m.data?.prompt_id === promptId) ||
          (m.type === 'executing' && m.data?.node === null && m.data?.prompt_id === promptId)) done()
      if (m.type === 'execution_error' && m.data?.prompt_id === promptId) { if (!settled) { settled = true; socket.removeEventListener('message', onMsg); if (poll) clearInterval(poll); reject(new Error(m.data?.exception_message || 'execution error')) } }
    }
    socket.addEventListener('message', onMsg)
    poll = setInterval(async () => { try { const h = await getHistory(promptId); if (h[promptId]?.outputs) done() } catch { /* 继续 */ } }, 3000)
  })
}

async function collectImages(promptId) {
  const h = await getHistory(promptId)
  const entry = h[promptId]; if (!entry) return []
  const urls = []
  for (const out of Object.values(entry.outputs || {}))
    for (const img of out.images || []) urls.push(imageUrl(img.filename, img.subfolder, img.type))
  return urls
}

// ── 采集会话日志 ──
const sessionLog = reactive([])
const flash = ref(false)
const lastSyncTs = ref(0)

function syncBeacon() {
  const ts = Date.now()
  lastSyncTs.value = ts
  sessionLog.push({ ts, dom: '__SYNC__', probs: {}, image: '', prompt: 'SYNC_BEACON', trigger: 'sync' })
  flash.value = true
  setTimeout(() => { flash.value = false }, 250)
}

function exportCsv() {
  const cols = ['timestamp_ms', 'dominant', ...EN_CLASSES, 'image_file', 'prompt', 'trigger']
  const lines = [cols.join(',')]
  for (const r of sessionLog) {
    const row = [r.ts, r.dom, ...EN_CLASSES.map((e) => Math.round((r.probs[e] || 0) * 100) / 100),
      r.image, `"${(r.prompt || '').replace(/"/g, '""')}"`, r.trigger]
    lines.push(row.join(','))
  }
  const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `affective_session_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

// ── 生命周期 ──
let connTimer = null
onMounted(() => { retryConn(); connTimer = setInterval(retryConn, 20000) })
onUnmounted(() => { clearInterval(connTimer); stopSource() })
</script>

<style scoped>
.comfy-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius); overflow: hidden; }
.comfy-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface-2); }
.header-left { display: flex; align-items: center; gap: 10px; }
.panel-title { font-size: 0.92rem; font-weight: 700; color: var(--color-text); }
.server-addr { font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.header-right { display: flex; align-items: center; gap: 8px; }
.conn-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 600; }
.conn-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.conn-ok { background: rgba(46,204,113,0.15); color: #2ecc71; }
.conn-off { background: rgba(255,107,107,0.12); color: #ff6b6b; }
.icon-btn { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text-muted); cursor: pointer; }
.comfy-body { flex: 1; overflow-y: auto; padding: 14px 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.panel-desc { font-size: 0.75rem; line-height: 1.5; color: var(--color-text-muted); }

.cam-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.cam-wrap { position: relative; aspect-ratio: 4/3; background: #000; border-radius: 10px; overflow: hidden; border: 1px solid var(--color-border); }
.cam-video { width: 100%; height: 100%; object-fit: cover; transform: scaleX(-1); }
.cam-ph { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 2rem; }
.emo-live { display: flex; flex-direction: column; gap: 5px; justify-content: center; }
.emo-dom { font-size: 1.1rem; color: var(--color-text); }
.emo-dom.muted { color: var(--color-text-muted); font-size: 0.85rem; }
.bar-row { display: flex; align-items: center; gap: 6px; font-size: 0.7rem; color: var(--color-text-muted); }
.bar-label { width: 34px; flex-shrink: 0; }
.bar { flex: 1; height: 6px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.bar-fill { height: 100%; background: #2563eb; transition: width 0.3s; }
.bar-val { width: 22px; text-align: right; }

.row-group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.inline { display: inline-flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--color-text-muted); }
.num-mini { width: 48px; text-align: center; background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text); padding: 3px; }
.btn-mini { padding: 6px 12px; border-radius: 7px; border: 1px solid var(--color-border); background: var(--color-surface-2); color: var(--color-text); font-size: 0.78rem; cursor: pointer; }
.btn-mini:disabled { opacity: 0.5; cursor: not-allowed; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 0.75rem; font-weight: 600; color: var(--color-text-muted); }
.ctrl-select { background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: 8px; color: var(--color-text); font-size: 0.82rem; padding: 7px 10px; width: 100%; }
.src-select { width: auto; }
.btn-generate { width: 100%; padding: 11px 0; border: none; border-radius: 10px; background: #2563eb; color: #fff; font-size: 0.9rem; font-weight: 700; cursor: pointer; }
.btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }
.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; }
.msg-ok { background: rgba(46,204,113,0.12); color: #2ecc71; }
.msg-error { background: rgba(255,107,107,0.12); color: #ff6b6b; }

.batch-box { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px dashed var(--color-border); border-radius: 10px; background: var(--color-surface-2); }
.batch-title { font-size: 0.82rem; font-weight: 700; color: var(--color-text); }
.batch-hint { font-size: 0.7rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.art-box { border: 1px dashed var(--color-border); border-radius: 10px; padding: 10px 12px; background: var(--color-surface-2); }
.art-box summary { font-size: 0.8rem; font-weight: 700; color: var(--color-text); cursor: pointer; }
.art-text { width: 100%; margin: 8px 0; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; color: var(--color-text); font-family: ui-monospace, monospace; font-size: 0.72rem; padding: 8px; resize: vertical; }
.art-msg { font-size: 0.7rem; color: var(--color-text-muted); }

.result-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.result-item { position: relative; border-radius: 8px; overflow: hidden; border: 1px solid var(--color-border); }
.result-img { display: block; width: 100%; aspect-ratio: 1; object-fit: cover; cursor: zoom-in; }
.emo-tag { position: absolute; top: 4px; left: 4px; padding: 1px 7px; border-radius: 10px; background: rgba(0,0,0,0.6); color: #fff; font-size: 0.66rem; }

.sync-flash { position: fixed; inset: 0; background: #fff; z-index: 10000; pointer-events: none; }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.9); display: flex; align-items: center; justify-content: center; z-index: 9999; cursor: zoom-out; }
.lightbox-img { max-width: 94vw; max-height: 92vh; border-radius: 10px; }
</style>
