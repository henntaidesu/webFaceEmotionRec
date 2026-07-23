<template>
  <div class="comfy-panel">
    <!-- 顶部工具栏 -->
    <div class="comfy-header">
      <div class="header-left">
        <span class="panel-title">{{ locale.affect.title }}</span>
        <span class="server-addr">{{ COMFYUI_HOST }}</span>
      </div>
      <div class="header-right">
        <span class="conn-badge" :class="online ? 'conn-ok' : 'conn-off'">
          <span class="conn-dot"></span>{{ online ? locale.comfyConnected : locale.comfyDisconnected }}
        </span>
        <button class="icon-btn" :title="locale.comfyRetry" @click="retryConn">↻</button>
      </div>
    </div>

    <!-- 主体：左配置 / 右实时情绪 + 当前图 -->
    <div class="comfy-body">
      <!-- ── 左：配置 ── -->
      <div class="config-col">
        <p class="panel-desc">{{ locale.affect.desc }}</p>

        <!-- 功能可用性 -->
        <div class="cap-row">
          <span class="cap" :class="caps.pg ? 'cap-ok' : 'cap-bad'">PG {{ caps.pg ? '✓' : '✕' }}</span>
          <span class="cap" :class="caps.deepseek ? 'cap-ok' : 'cap-bad'">DeepSeek {{ caps.deepseek ? '✓' : '✕' }}</span>
        </div>
        <p v-if="!caps.pg" class="warn">{{ locale.affect.pgMissing }}</p>

        <!-- 受试者 + 来源 -->
        <div class="field">
          <label class="field-label">{{ locale.affect.subject }}</label>
          <input v-model.trim="subjectId" class="ctrl-input" :disabled="running" placeholder="subject-01" />
        </div>
        <div class="field">
          <label class="field-label">{{ locale.affect.source }}</label>
          <select v-model="source" class="ctrl-select" :disabled="running">
            <option value="quest">{{ locale.affect.srcQuest }}</option>
            <option value="webcam">{{ locale.affect.srcWebcam }}</option>
          </select>
        </div>

        <!-- 开始/停止：点开始即建会话 + 开始采集面部信息 -->
        <button class="btn-generate" :class="{ 'btn-stop': running }" :disabled="!caps.pg && !running" @click="toggleRun">
          {{ running ? ('■ ' + locale.affect.stop) : ('▶ ' + locale.affect.start) }}
        </button>
        <p v-if="running" class="run-stat">
          {{ locale.affect.collecting }} · {{ feaCount }} {{ locale.affect.frames }}
          <span v-if="sessionId" class="sid">· {{ sessionId }}</span>
        </p>

        <!-- 闭环参数 -->
        <details class="cfg-box" open>
          <summary>{{ locale.affect.loopCfg }}</summary>
          <label class="inline"><input type="checkbox" v-model="autoMode" /> {{ locale.affect.auto }}</label>
          <div class="grid2">
            <div class="field">
              <label class="field-label">{{ locale.affect.cooldown }} (s)</label>
              <input type="number" v-model.number="cooldownSec" class="ctrl-input" min="3" max="120" />
            </div>
            <div class="field">
              <label class="field-label">{{ locale.affect.reactionWindow }} (s)</label>
              <input type="number" v-model.number="reactionWindowSec" class="ctrl-input" min="2" max="60" />
            </div>
          </div>
          <div class="field">
            <label class="field-label">{{ locale.affect.likeThreshold }}</label>
            <input type="number" v-model.number="likeThreshold" class="ctrl-input" min="-1" max="1" step="0.05" />
          </div>
          <label class="inline"><input type="checkbox" v-model="usePreference" /> {{ locale.affect.usePreference }}</label>
        </details>

        <!-- 提示词来源 -->
        <div class="field">
          <label class="field-label">{{ locale.affect.promptSource }}</label>
          <select v-model="promptSource" class="ctrl-select">
            <option value="deepseek" :disabled="!caps.deepseek">{{ locale.affect.psDeepseek }}</option>
            <option value="art">{{ locale.affect.psArt }}</option>
          </select>
        </div>

        <!-- 生成方式（复用 ComfyUI 内置 txt2img / 服务器工作流）-->
        <div class="field">
          <label class="field-label">{{ locale.affect.genMode }}</label>
          <select v-model="genMode" class="ctrl-select">
            <option value="builtin">{{ locale.affect.genBuiltin }}</option>
            <option value="workflow">{{ locale.affect.genWorkflow }}</option>
          </select>
        </div>
        <div v-if="genMode === 'builtin'" class="field">
          <label class="field-label">{{ locale.comfyModel }}</label>
          <select v-model="checkpoint" class="ctrl-select">
            <option v-if="checkpoints.length === 0" value="">{{ locale.affect.noCkpt }}</option>
            <option v-for="c in checkpoints" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div v-else class="field">
          <label class="field-label">{{ locale.comfyWorkflow }}</label>
          <select v-model="selectedWorkflow" class="ctrl-select">
            <option v-if="workflows.length === 0" value="">{{ locale.affect.noWorkflow }}</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf.replace(/\.json$/, '') }}</option>
          </select>
        </div>

        <button class="btn-generate" :disabled="generating || !cur.dominant_en || !canGenerate" @click="() => generate('manual')">
          <span v-if="generating">{{ locale.affect.generating }}<span v-if="progress.max"> · {{ progress.current }}/{{ progress.max }}</span></span>
          <span v-else>⚡ {{ locale.affect.generateNow }}</span>
        </button>
        <p v-if="statusMsg" class="status-msg" :class="statusCls">{{ statusMsg }}</p>

        <!-- 用户喜欢过的相似图（pgvector 检索）-->
        <div v-if="recommendations.length" class="rec-box">
          <div class="rec-title">💜 {{ locale.affect.liked }}（{{ recommendations.length }}）</div>
          <div class="rec-grid">
            <div v-for="r in recommendations" :key="r.id" class="rec-item" :title="r.scene || r.prompt">
              <img v-if="r.image_url" :src="r.image_url" class="rec-img" @click="lightbox = r.image_url" />
              <span v-else class="rec-noimg">{{ r.scene || '—' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 右：实时情绪 + 当前生成图 ── -->
      <div class="view-col">
        <!-- 2D 摄像头预览（仅 webcam 来源）-->
        <video v-show="source === 'webcam' && running" ref="videoEl" class="cam-video" autoplay playsinline muted></video>

        <!-- 实时情绪 -->
        <div class="emo-live">
          <div class="emo-dom" v-if="cur.dominant_en">{{ emoEmoji(cur.dominant_en) }} <strong>{{ cur.dominant_zh }}</strong></div>
          <div v-else class="emo-dom muted">{{ locale.affect.noEmotion }}</div>
          <div v-for="e in EN_CLASSES" :key="e" class="bar-row">
            <span class="bar-label">{{ locale.emotionMap[EN2ZH[e]] }}</span>
            <div class="bar"><div class="bar-fill" :style="{ width: (cur.probs[e] || 0) + '%' }"></div></div>
            <span class="bar-val">{{ Math.round(cur.probs[e] || 0) }}</span>
          </div>
        </div>

        <!-- 当前生成图 + 反应判定 -->
        <div class="cur-title">{{ locale.affect.currentImage }}</div>
        <div class="cur-box">
          <img v-if="currentImage.url" :src="currentImage.url" class="cur-img" @click="lightbox = currentImage.url" />
          <span v-else class="cur-ph">{{ locale.affect.noImage }}</span>
        </div>
        <div v-if="currentImage.scene" class="cur-scene">🎬 {{ currentImage.scene }}</div>
        <div v-if="currentImage.reasoning" class="cur-reason">{{ currentImage.reasoning }}</div>
        <div v-if="reaction.state" class="reaction" :class="'rx-' + reaction.state">
          <span v-if="reaction.state === 'measuring'">⏱ {{ locale.affect.measuring }}</span>
          <span v-else-if="reaction.state === 'liked'">💜 {{ locale.affect.judgedLiked }}（{{ reaction.score.toFixed(2) }}）</span>
          <span v-else>🤍 {{ locale.affect.judgedMeh }}（{{ reaction.score.toFixed(2) }}）</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="lightbox" class="lightbox" @click="lightbox = null">
        <img :src="lightbox" class="lightbox-img" @click.stop />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import {
  checkOnline, fetchCheckpoints, fetchWorkflows, fetchWorkflow, fetchObjectInfo,
  uiToApiFormat, applyPromptOverrides, buildTxt2ImgWorkflow, queuePrompt,
  getHistory, imageUrl, makeClientId, openProgressWS, COMFYUI_HOST,
} from '../api/comfyuiApi.js'
import {
  affectStatus, fetchFeaLatest, generatePrompt, startSession, stopSession,
  pushSamples, recordImage, recommend,
} from '../api/affect.js'
import { saveStimulusImage } from '../api/vrStimulus.js'

const props = defineProps({ locale: { type: Object, required: true } })

const EN_CLASSES = ['happy', 'surprise', 'neutral', 'sad', 'angry', 'fear', 'disgust']
const EN2ZH = { happy: '开心', sad: '悲伤', angry: '愤怒', surprise: '惊讶', fear: '恐惧', disgust: '厌恶', neutral: '平静' }
const ZH2EN = Object.fromEntries(Object.entries(EN2ZH).map(([en, zh]) => [zh, en]))
const emoEmoji = (en) => ({ happy: '😄', sad: '😢', angry: '😠', surprise: '😲', fear: '😨', disgust: '🤢', neutral: '😐' }[en] || '🙂')

// 提示词回退（DeepSeek 不可用时按情感取一段风格）
const DEFAULT_ART = {
  happy: 'joyful vibrant art, warm bright colors, uplifting energy, dynamic swirls',
  sad: 'melancholic art, cool blue tones, soft rain, gentle comforting mood',
  angry: 'calming art, cool soothing tones, slow flowing shapes, relief from tension',
  surprise: 'delightful surreal art, bursting light, playful vivid colors',
  fear: 'safe warm art, soft glow, reassuring cozy atmosphere',
  disgust: 'clean fresh art, crisp clear tones, pleasant tidy composition',
  neutral: 'calm minimalist art, balanced neutral tones, serene composition',
}
const NEG = 'lowres, worst quality, blurry, text, watermark, deformed'

// ── ComfyUI 连接 ──
const online = ref(false)
const checkpoints = ref([])
const checkpoint = ref('')
const genMode = ref('builtin')
const workflows = ref([])
const selectedWorkflow = ref('')
const canGenerate = computed(() => genMode.value === 'workflow' ? !!selectedWorkflow.value : !!checkpoint.value)

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
  if (checkpoints.value.length === 0 && workflows.value.length > 0 && genMode.value === 'builtin') {
    genMode.value = 'workflow'
    if (!selectedWorkflow.value) selectedWorkflow.value = workflows.value[0]
  }
}

// ── 功能可用性 + 闭环参数（默认取自后端）──
const caps = reactive({ pg: false, deepseek: false })
const autoMode = ref(true)
const cooldownSec = ref(10)
const reactionWindowSec = ref(6)
const likeThreshold = ref(0.15)
const usePreference = ref(true)
const promptSource = ref('deepseek')

async function loadStatus() {
  try {
    const s = await affectStatus()
    caps.pg = !!s.pg_configured
    caps.deepseek = !!s.deepseek_configured
    if (s.cooldown_s) cooldownSec.value = s.cooldown_s
    if (s.reaction_window_s) reactionWindowSec.value = s.reaction_window_s
    if (typeof s.like_threshold === 'number') likeThreshold.value = s.like_threshold
    if (!caps.deepseek) promptSource.value = 'art'
  } catch { /* 后端未在线 */ }
}

// ── 情绪来源与采集 ──
const source = ref('quest')
const subjectId = ref('subject-01')
const running = ref(false)
const sessionId = ref('')
const feaCount = ref(0)
const videoEl = ref(null)
const cur = reactive({ dominant_en: '', dominant_zh: '', probs: {} })

// 情绪轨迹缓冲（喂 DeepSeek）与 webcam 模式的待推样本
const trajectory = []               // [{ t, dom, probs(en→0..100) }]
let webcamPending = []              // webcam 模式待批量写 PG 的样本
let feaTimer = null, sampleTimer = null
let stream = null, emoWs = null, capTimer = null
const FEA_POLL_MS = 300
const EMO_FPS = 4

function positiveScore(probs) {
  const g = (k) => probs[k] || 0
  return (g('happy') + g('surprise') - g('angry') - g('disgust') - g('fear') - g('sad')) / 100
}

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

  const now = Date.now()
  trajectory.push({ t: now, dom: cur.dominant_en, probs: { ...probs } })
  while (trajectory.length > 40) trajectory.shift()

  // 反应测量：收集生成后窗口内的正向情绪
  if (reaction.state === 'measuring') reaction.samples.push(positiveScore(probs))
  // webcam 模式自采样本待推 PG（头显模式由后端 /api/fea 自动写）
  if (source.value === 'webcam' && running.value) {
    webcamPending.push({ ts_ms: now, emotions: probs, dominant: cur.dominant_en, source: 'webcam' })
  }
  maybeAutoGenerate(prevDom)
}

// —— Quest Pro FEA 轮询 ——
async function pollFea() {
  try {
    const data = await fetchFeaLatest()
    if (data.success && data.faces?.length) { applyFace(data.faces[0]); feaCount.value++ }
  } catch { /* 忽略 */ }
}

// —— 2D 摄像头（/ws/emotion）——
async function startWebcam() {
  stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false,
  })
  videoEl.value.srcObject = stream
  await videoEl.value.play()
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  emoWs = new WebSocket(`${proto}://${location.host}/ws/emotion`)
  emoWs.onopen = () => { capTimer = setInterval(sendFrame, Math.round(1000 / EMO_FPS)) }
  emoWs.onmessage = (evt) => {
    let data; try { data = JSON.parse(evt.data) } catch { return }
    if (data.success && data.faces?.length) { applyFace(data.faces[0]); feaCount.value++ }
  }
}
function sendFrame() {
  if (!emoWs || emoWs.readyState !== WebSocket.OPEN) return
  if (!videoEl.value || videoEl.value.readyState < 2) return
  const c = document.createElement('canvas')
  c.width = videoEl.value.videoWidth; c.height = videoEl.value.videoHeight
  c.getContext('2d').drawImage(videoEl.value, 0, 0)
  emoWs.send(JSON.stringify({ frame: c.toDataURL('image/jpeg', 0.7) }))
}

async function flushWebcamSamples() {
  if (!webcamPending.length || !sessionId.value) return
  const batch = webcamPending; webcamPending = []
  try { await pushSamples(sessionId.value, batch) } catch { webcamPending = batch.concat(webcamPending) }
}

// ── 开始 / 停止 ──
let starting = false          // 防 startSession await 期间重复点击起两个会话/摄像头
let reactionTimer = null      // measureReaction 的 setTimeout id，停止/卸载时清
let activeGenWs = null        // 生成进行中的进度 WS，卸载时关

async function toggleRun() {
  if (running.value) { await stopRun(); return }
  await startRun()
}

async function startRun() {
  if (starting || running.value) return
  starting = true
  try {
    statusMsg.value = ''
    let r
    try {
      r = await startSession(subjectId.value || 'anon', { source: source.value })
    } catch (e) {
      setStatus(`${props.locale.affect.error}: ${e.message}`, 'msg-error'); return
    }
    sessionId.value = r.session_id
    running.value = true
    feaCount.value = 0
    trajectory.length = 0
    if (source.value === 'webcam') {
      try { await startWebcam() } catch (e) { setStatus(`${props.locale.cameraErrorPrefix || ''}${e.message}`, 'msg-error') }
      sampleTimer = setInterval(flushWebcamSamples, 2000)
    } else {
      feaTimer = setInterval(pollFea, FEA_POLL_MS)
    }
    setStatus(props.locale.affect.started, 'msg-ok')
  } finally {
    starting = false
  }
}

async function stopRun() {
  if (feaTimer) { clearInterval(feaTimer); feaTimer = null }
  if (sampleTimer) { clearInterval(sampleTimer); sampleTimer = null }
  if (reactionTimer) { clearTimeout(reactionTimer); reactionTimer = null }
  if (reaction.state === 'measuring') reaction.state = ''
  await flushWebcamSamples()
  stopWebcam()
  running.value = false
  const sid = sessionId.value
  sessionId.value = ''
  try {
    if (sid) { const r = await stopSession(sid); setStatus(`${props.locale.affect.stopped}（FEA ${r.fea_count} · IMG ${r.image_count}）`, 'msg-ok') }
  } catch (e) { setStatus(`${props.locale.affect.error}: ${e.message}`, 'msg-error') }
}

function stopWebcam() {
  if (capTimer) { clearInterval(capTimer); capTimer = null }
  if (emoWs) { emoWs.close(); emoWs = null }
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null }
}

// ── 自动随情感变化生成 ──
let lastGenAt = 0
function maybeAutoGenerate(prevDom) {
  if (!autoMode.value || !running.value || generating.value || !canGenerate.value) return
  if (!cur.dominant_en || cur.dominant_en === prevDom) return
  if (Date.now() - lastGenAt < cooldownSec.value * 1000) return
  generate('auto')
}

// ── 生成方式 ──
function setSavePrefix(api, prefix) {
  for (const node of Object.values(api)) {
    if (node.class_type === 'SaveImage' && node.inputs) node.inputs.filename_prefix = prefix
  }
  return api
}
async function buildWorkflowFor(dom, positive, negative) {
  const prefix = `affect/${dom}/${dom}`
  if (genMode.value === 'workflow') {
    const [raw, objectInfo] = await Promise.all([fetchWorkflow(selectedWorkflow.value), fetchObjectInfo()])
    let api = Array.isArray(raw?.nodes) ? uiToApiFormat(raw, objectInfo) : raw
    api = applyPromptOverrides(api, { positive, negative, seed: -1 })
    return setSavePrefix(api, prefix)
  }
  return buildTxt2ImgWorkflow({
    positive, negative, checkpoint: checkpoint.value,
    steps: 22, cfg: 7, width: 512, height: 512,
    sampler: 'euler', scheduler: 'normal', seed: -1, filename_prefix: prefix,
  })
}

// ── 生成 + 反应测量 + 存储（闭环核心）──
const generating = ref(false)
const progress = reactive({ current: 0, max: 0 })
const statusMsg = ref(''), statusCls = ref('')
const currentImage = reactive({ url: '', label: '', scene: '', reasoning: '' })
const reaction = reactive({ state: '', samples: [], score: 0 })
const recommendations = ref([])
const lightbox = ref(null)

function setStatus(t, cls) { statusMsg.value = t; statusCls.value = cls }

// 组装喂 DeepSeek 的轨迹（最近若干帧，ago_s + probs）
function buildTrajectoryPayload() {
  const now = Date.now()
  const recent = trajectory.slice(-8)
  const traj = recent.map((s) => ({ dom: s.dom, ago_s: Math.round((now - s.t) / 1000), probs: s.probs }))
  return { trajectory: traj, current: { dominant_en: cur.dominant_en, probs: { ...cur.probs } } }
}

async function resolvePrompt(dom) {
  // 1) 提示词：DeepSeek（据情感变化轨迹）或静态风格回退
  let positive, negative = NEG, scene = '', reasoning = ''
  if (promptSource.value === 'deepseek' && caps.deepseek) {
    const { trajectory: traj, current } = buildTrajectoryPayload()
    const r = await generatePrompt(traj, current, 'zh')
    positive = r.positive; negative = r.negative || NEG; scene = r.scene || ''; reasoning = r.reasoning || ''
  } else {
    positive = `masterpiece, expressive art, ${DEFAULT_ART[dom] || dom}`
  }
  // 2) 偏好闭环：检索用户在相似情绪下喜欢过的图，用其场景强化提示词
  if (usePreference.value && caps.pg) {
    try {
      const { items } = await recommend(cur.probs, 3, subjectId.value)
      recommendations.value = items || []
      const liked = (items || []).find((it) => it.scene || it.prompt)
      if (liked) { positive += `, ${liked.scene || ''}`.replace(/, $/, ''); reasoning = (reasoning ? reasoning + ' ' : '') + props.locale.affect.reinforced }
    } catch { /* 检索失败不阻断生成 */ }
  }
  return { positive, negative, scene, reasoning }
}

async function generate(trigger) {
  if (generating.value || !cur.dominant_en || !canGenerate.value) return
  generating.value = true; lastGenAt = Date.now()
  progress.current = 0; progress.max = 0
  const dom = cur.dominant_en
  const contextProbs = { ...cur.probs }
  const clientId = makeClientId()
  let ws = null
  try {
    const { positive, negative, scene, reasoning } = await resolvePrompt(dom)
    const workflow = await buildWorkflowFor(dom, positive, negative)
    ws = openProgressWS(clientId); activeGenWs = ws
    const { prompt_id } = await queuePrompt(clientId, workflow)
    const urls = await waitForImages(ws, prompt_id)
    const url = urls[0] || ''
    currentImage.url = url
    currentImage.label = `${emoEmoji(dom)} ${EN2ZH[dom]}`
    currentImage.scene = scene
    currentImage.reasoning = reasoning
    setStatus(props.locale.affect.done, 'msg-ok')

    // 推到 VR 头显天空盒让用户看到（并落盘 image/affect/<emotion>/）
    let savedUrl = url
    if (url) { try { const s = await saveStimulusImage(url, dom, 'affect', { show: true }); if (s.path) savedUrl = `/api/stimulus/files/${s.path.replace(/^image\//, '')}` } catch { /* 忽略存盘失败 */ } }

    // 反应测量 → 判定「喜欢」→ 写 PG
    measureReaction({ dom, contextProbs, positive, negative, scene, reasoning, url: savedUrl })
  } catch (e) {
    setStatus(`${props.locale.affect.error}: ${e.message}`, 'msg-error')
  } finally {
    generating.value = false
    if (ws) ws.close()
    activeGenWs = null
  }
}

// 生成后测量随后窗口内的正向情绪，均值≥阈值判为「喜欢」，连同情绪情境向量写 PG
function measureReaction({ dom, contextProbs, positive, negative, scene, reasoning, url }) {
  const onset = Date.now()
  reaction.state = 'measuring'; reaction.samples = []; reaction.score = 0
  if (reactionTimer) clearTimeout(reactionTimer)
  reactionTimer = setTimeout(async () => {
    reactionTimer = null
    const arr = reaction.samples
    const score = arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : positiveScore(contextProbs)
    const liked = score >= likeThreshold.value
    reaction.score = score
    reaction.state = liked ? 'liked' : 'meh'
    if (caps.pg) {
      try {
        await recordImage({
          ts_ms: onset, dominant: dom, emotions: contextProbs,
          prompt: positive, negative, scene, reasoning, image_url: url,
          liked, reaction: { mean_positive: Number(score.toFixed(4)), samples: arr.length, window_s: reactionWindowSec.value },
        })
      } catch (e) { setStatus(`${props.locale.affect.error}: ${e.message}`, 'msg-error') }
    }
  }, Math.max(2, reactionWindowSec.value) * 1000)
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
      if (m.type === 'execution_error' && m.data?.prompt_id === promptId) {
        if (!settled) { settled = true; socket.removeEventListener('message', onMsg); if (poll) clearInterval(poll); reject(new Error(m.data?.exception_message || 'execution error')) }
      }
    }
    socket.addEventListener('message', onMsg)
    let pollN = 0
    poll = setInterval(async () => {
      if (++pollN > 200) {          // ~10min 上限：Comfy 崩/节点错时不再无限轮询
        if (settled) return
        settled = true
        socket.removeEventListener('message', onMsg); if (poll) clearInterval(poll)
        reject(new Error('轮询超时：ComfyUI 未返回结果')); return
      }
      try { const h = await getHistory(promptId); if (h[promptId]?.outputs) done() } catch { /* 继续 */ }
    }, 3000)
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

// ── 生命周期 ──
let connTimer = null
onMounted(() => { retryConn(); loadStatus(); connTimer = setInterval(retryConn, 20000) })
onUnmounted(() => {
  clearInterval(connTimer)
  if (feaTimer) clearInterval(feaTimer)
  if (sampleTimer) clearInterval(sampleTimer)
  if (reactionTimer) { clearTimeout(reactionTimer); reactionTimer = null }
  if (activeGenWs) { activeGenWs.close(); activeGenWs = null }
  stopWebcam()
})
</script>

<style scoped>
.comfy-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius); overflow: hidden; }
.comfy-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface-2); }
.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.panel-title { font-size: 0.92rem; font-weight: 700; color: var(--color-text); }
.server-addr { font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.header-right { display: flex; align-items: center; gap: 8px; }
.conn-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 600; }
.conn-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.conn-ok { background: rgba(46,204,113,0.15); color: #2ecc71; }
.conn-off { background: rgba(255,107,107,0.12); color: #ff6b6b; }
.icon-btn { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text-muted); cursor: pointer; }

.comfy-body { flex: 1; min-height: 0; overflow: hidden; display: flex; align-items: stretch; }
.config-col { flex: 1 1 0; min-width: 0; overflow-y: auto; padding: 14px 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.view-col { flex: 1 1 0; min-width: 0; overflow-y: auto; border-left: 1px solid var(--color-border); background: var(--color-surface-2); padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }

.panel-desc { font-size: 0.75rem; line-height: 1.5; color: var(--color-text-muted); }
.cap-row { display: flex; gap: 8px; }
.cap { font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
.cap-ok { background: rgba(46,204,113,0.14); color: #2ecc71; }
.cap-bad { background: rgba(255,107,107,0.12); color: #ff6b6b; }
.warn { font-size: 0.72rem; color: #f0a05a; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 0.74rem; font-weight: 600; color: var(--color-text-muted); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ctrl-input, .ctrl-select { width: 100%; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; color: var(--color-text); font-size: 0.82rem; padding: 8px 10px; }
.ctrl-select { cursor: pointer; }
.inline { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--color-text-muted); }

.cfg-box { border: 1px solid var(--color-border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.cfg-box summary { font-size: 0.78rem; font-weight: 700; cursor: pointer; color: var(--color-text); }

.btn-generate { width: 100%; padding: 11px 0; border: none; border-radius: 10px; background: #2563eb; color: #fff; font-size: 0.9rem; font-weight: 700; cursor: pointer; transition: opacity 0.2s; }
.btn-generate:hover:not(:disabled) { opacity: 0.92; }
.btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-stop { background: rgba(255,107,107,0.16); color: #ff6b6b; }
.run-stat { font-size: 0.74rem; color: var(--color-text-muted); }
.run-stat .sid { font-family: ui-monospace, monospace; opacity: 0.7; }
.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; }
.msg-ok { background: rgba(46,204,113,0.12); color: #2ecc71; }
.msg-error { background: rgba(255,107,107,0.12); color: #ff6b6b; }

.rec-box { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.rec-title { font-size: 0.78rem; font-weight: 700; color: var(--color-text); }
.rec-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 6px; }
.rec-item { aspect-ratio: 1; border-radius: 6px; overflow: hidden; border: 1px solid var(--color-border); display: flex; align-items: center; justify-content: center; }
.rec-img { width: 100%; height: 100%; object-fit: cover; cursor: zoom-in; }
.rec-noimg { font-size: 0.6rem; color: var(--color-text-muted); padding: 4px; text-align: center; }

.cam-video { width: 100%; border-radius: 8px; background: #000; aspect-ratio: 4 / 3; object-fit: cover; }
.emo-live { display: flex; flex-direction: column; gap: 5px; }
.emo-dom { font-size: 1rem; color: var(--color-text); }
.emo-dom.muted { color: var(--color-text-muted); font-size: 0.85rem; }
.bar-row { display: grid; grid-template-columns: 44px 1fr 28px; align-items: center; gap: 6px; }
.bar-label { font-size: 0.68rem; color: var(--color-text-muted); }
.bar { height: 8px; background: var(--color-border); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: #2563eb; border-radius: 4px; transition: width 0.25s; }
.bar-val { font-size: 0.68rem; color: var(--color-text-muted); text-align: right; }

.cur-title { font-size: 0.8rem; font-weight: 700; color: var(--color-text); margin-top: 4px; }
.cur-box { width: 100%; aspect-ratio: 1; background: rgba(0,0,0,0.25); border: 1px solid var(--color-border); border-radius: 10px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.cur-img { width: 100%; height: 100%; object-fit: contain; cursor: zoom-in; }
.cur-ph { font-size: 0.82rem; color: var(--color-text-muted); }
.cur-scene { font-size: 0.76rem; color: var(--color-text); }
.cur-reason { font-size: 0.72rem; color: var(--color-text-muted); line-height: 1.5; }
.reaction { font-size: 0.8rem; font-weight: 600; padding: 6px 10px; border-radius: 8px; text-align: center; }
.rx-measuring { background: rgba(255,193,7,0.12); color: #ffc107; }
.rx-liked { background: rgba(155,89,255,0.14); color: #b07bff; }
.rx-meh { background: var(--color-surface); color: var(--color-text-muted); border: 1px solid var(--color-border); }

.lightbox { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; padding: 24px; }
.lightbox-img { max-width: 92vw; max-height: 92vh; border-radius: 8px; }
</style>
