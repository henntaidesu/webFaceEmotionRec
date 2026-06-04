<template>
  <div class="detector">
    <!-- 摄像头 + Canvas 叠加层 -->
    <div class="camera-wrap">
      <video ref="videoEl" class="camera-video" autoplay playsinline muted></video>
      <canvas ref="overlayEl" class="camera-overlay"></canvas>

      <!-- 状态浮层 -->
      <div class="camera-status" :class="statusClass">
        <span class="status-dot"></span>
        {{ statusText }}
      </div>

      <!-- 无摄像头提示 -->
      <div v-if="cameraError" class="camera-placeholder">
        <div class="placeholder-icon">{{ locale.cameraPlaceholderIcon }}</div>
        <p>{{ cameraError }}</p>
      </div>
    </div>

    <!-- 控制按钮 -->
    <div class="controls">
      <button class="btn btn-primary" @click="toggleCamera" :disabled="connecting">
        {{ cameraActive ? locale.closeCamera : locale.openCamera }}
      </button>
      <button
        class="btn btn-accent"
        @click="toggleDetection"
        :disabled="!cameraActive || connecting"
      >
        {{ detecting ? locale.stopDetection : locale.startDetection }}
      </button>

      <label class="model-select-wrap">
        <span class="model-label">{{ locale.modelLabel }}</span>
        <select v-model="detectorBackend" class="model-select">
          <option v-for="opt in locale.detectorOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>

      <div class="fps-display">
        <span>{{ locale.fps }}</span>
        <strong>{{ fps }} FPS</strong>
      </div>
    </div>

    <!-- 情感结果面板 -->
    <transition name="fade">
      <div v-if="faces.length > 0" class="results-panel">
        <div v-for="(face, idx) in faces" :key="idx" class="face-card">
          <div class="face-header">
            <span class="face-index">{{ locale.facePrefix }}{{ idx + 1 }}</span>
            <span class="dominant-badge" :style="{ background: emotionColor(face.dominant_en) }">
              {{ emotionEmoji(face.dominant_en) }} {{ translateEmotion(face.dominant) }}
            </span>
          </div>
          <div class="emotion-bars">
            <div
              v-for="(val, name) in face.emotions"
              :key="name"
              class="emotion-row"
            >
              <span class="emotion-name">{{ translateEmotion(name) }}</span>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{
                    width: val + '%',
                    background: emotionColor(emotionEnKey(name)),
                  }"
                ></div>
              </div>
              <span class="emotion-val">{{ val.toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 无人脸提示 -->
    <transition name="fade">
      <div v-if="detecting && faces.length === 0 && !cameraError" class="no-face-tip">
        {{ locale.noFaceTip }}
      </div>
    </transition>

    <!-- 连接错误提示 -->
    <transition name="fade">
      <div v-if="wsError" class="error-banner">
        ⚠️ {{ wsError }}
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'

const props = defineProps({
  locale: { type: Object, required: true },
})

// ─── 响应式状态 ───────────────────────────────────────────────
const videoEl = ref(null)
const overlayEl = ref(null)
const cameraActive = ref(false)
const cameraError = ref('')
const detecting = ref(false)
const connecting = ref(false)
const faces = ref([])
const wsError = ref('')
const fps = ref(0)

const detectorBackend = ref(props.locale.detectorOptions[0].value)

let stream = null
let ws = null
let captureTimer = null
let fpsTimer = null
let frameCount = 0

const TARGET_FPS = 5
const FRAME_INTERVAL = Math.round(1000 / TARGET_FPS)

// ─── 状态文字 / 样式 ──────────────────────────────────────────
const statusText = computed(() => {
  if (cameraError.value) return props.locale.statusError
  if (connecting.value)  return props.locale.statusConnecting
  if (detecting.value)   return props.locale.statusDetecting
  if (cameraActive.value) return props.locale.statusReady
  return props.locale.statusIdle
})

const statusClass = computed(() => ({
  'status-error':  !!cameraError.value,
  'status-active': detecting.value,
  'status-ready':  cameraActive.value && !detecting.value,
}))

// ─── 情感颜色 / Emoji / 翻译 ──────────────────────────────────
const EMOTION_META = {
  angry:    { color: '#ff4d4d', emoji: '😠' },
  disgust:  { color: '#a855f7', emoji: '🤢' },
  fear:     { color: '#f59e0b', emoji: '😨' },
  happy:    { color: '#22c55e', emoji: '😄' },
  sad:      { color: '#3b82f6', emoji: '😢' },
  surprise: { color: '#f97316', emoji: '😲' },
  neutral:  { color: '#6b7280', emoji: '😐' },
}

const ZH_TO_EN = {
  愤怒: 'angry', 厌恶: 'disgust', 恐惧: 'fear',
  开心: 'happy', 悲伤: 'sad', 惊讶: 'surprise', 平静: 'neutral',
}

function emotionColor(enKey) {
  return EMOTION_META[enKey]?.color ?? '#6c63ff'
}

function emotionEmoji(enKey) {
  return EMOTION_META[enKey]?.emoji ?? '🙂'
}

function emotionEnKey(zhName) {
  return ZH_TO_EN[zhName] ?? 'neutral'
}

function translateEmotion(zhName) {
  return props.locale.emotionMap[zhName] ?? zhName
}

// ─── 摄像头控制 ───────────────────────────────────────────────
async function toggleCamera() {
  if (cameraActive.value) {
    stopAll()
  } else {
    await startCamera()
  }
}

async function startCamera() {
  cameraError.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false,
    })
    videoEl.value.srcObject = stream
    await videoEl.value.play()
    videoEl.value.addEventListener('loadedmetadata', syncOverlaySize)
    syncOverlaySize()
    cameraActive.value = true
  } catch (e) {
    cameraError.value = `${props.locale.cameraErrorPrefix}${e.message}`
  }
}

function syncOverlaySize() {
  if (!videoEl.value || !overlayEl.value) return
  overlayEl.value.width  = videoEl.value.videoWidth  || 640
  overlayEl.value.height = videoEl.value.videoHeight || 480
}

// ─── 识别控制 ─────────────────────────────────────────────────
function toggleDetection() {
  detecting.value ? stopDetection() : startDetection()
}

function startDetection() {
  wsError.value  = ''
  connecting.value = true

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${protocol}://${location.host}/ws/emotion`)

  ws.onopen = () => {
    connecting.value = false
    detecting.value  = true
    startCapture()
    startFpsCounter()
  }

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data)
      if (data.success) {
        faces.value = data.faces
        drawOverlay(data.faces)
      } else {
        faces.value = []
        clearOverlay()
      }
    } catch { /* 忽略解析错误 */ }
  }

  ws.onerror = () => {
    wsError.value = props.locale.wsErrorMsg
    stopDetection()
  }

  ws.onclose = () => {
    if (detecting.value) stopDetection()
  }
}

function stopDetection() {
  detecting.value  = false
  connecting.value = false
  stopCapture()
  stopFpsCounter()
  faces.value = []
  clearOverlay()
  if (ws) { ws.close(); ws = null }
}

// ─── 帧捕获 & 发送 ────────────────────────────────────────────
function startCapture() {
  captureTimer = setInterval(sendFrame, FRAME_INTERVAL)
}

function stopCapture() {
  if (captureTimer) { clearInterval(captureTimer); captureTimer = null }
}

function sendFrame() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  if (!videoEl.value || videoEl.value.readyState < 2) return

  const canvas = document.createElement('canvas')
  canvas.width  = videoEl.value.videoWidth
  canvas.height = videoEl.value.videoHeight
  const ctx = canvas.getContext('2d')
  ctx.translate(canvas.width, 0)
  ctx.scale(-1, 1)
  ctx.drawImage(videoEl.value, 0, 0)

  ws.send(JSON.stringify({
    frame: canvas.toDataURL('image/jpeg', 0.75),
    detector_backend: detectorBackend.value,
  }))
  frameCount++
}

// ─── FPS 计数 ─────────────────────────────────────────────────
function startFpsCounter() {
  fpsTimer = setInterval(() => { fps.value = frameCount; frameCount = 0 }, 1000)
}

function stopFpsCounter() {
  if (fpsTimer) { clearInterval(fpsTimer); fpsTimer = null }
  fps.value = 0
}

// ─── Canvas 叠加层绘制 ────────────────────────────────────────
function drawOverlay(facesData) {
  if (!overlayEl.value) return
  const ctx = overlayEl.value.getContext('2d')
  const w = overlayEl.value.width
  const h = overlayEl.value.height
  ctx.clearRect(0, 0, w, h)

  facesData.forEach((face) => {
    const { x, y, w: fw, h: fh } = face.region
    if (!fw || !fh) return

    const mirroredX = w - x - fw
    const color = emotionColor(face.dominant_en)

    ctx.strokeStyle = color
    ctx.lineWidth = 2.5
    ctx.shadowColor = color
    ctx.shadowBlur = 8
    ctx.strokeRect(mirroredX, y, fw, fh)
    ctx.shadowBlur = 0

    const label = `${emotionEmoji(face.dominant_en)} ${translateEmotion(face.dominant)}`
    ctx.font = 'bold 15px "Segoe UI", sans-serif'
    const textW = ctx.measureText(label).width + 16
    const labelY = y > 28 ? y - 8 : y + fh + 24

    ctx.fillStyle = color
    ctx.globalAlpha = 0.85
    roundRect(ctx, mirroredX, labelY - 20, textW, 24, 6)
    ctx.fill()
    ctx.globalAlpha = 1

    ctx.fillStyle = '#fff'
    ctx.fillText(label, mirroredX + 8, labelY - 3)
  })
}

function clearOverlay() {
  if (!overlayEl.value) return
  overlayEl.value.getContext('2d').clearRect(0, 0, overlayEl.value.width, overlayEl.value.height)
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

// ─── 全部停止 ─────────────────────────────────────────────────
function stopAll() {
  stopDetection()
  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }
  if (videoEl.value) videoEl.value.srcObject = null
  cameraActive.value = false
}

onUnmounted(stopAll)
</script>

<style scoped>
.detector {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
}

/* ── 摄像头区域 ── */
.camera-wrap {
  position: relative;
  width: 100%;
  max-width: 640px;
  aspect-ratio: 4/3;
  background: #0d0d1a;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--color-border);
  box-shadow: 0 0 40px rgba(108, 99, 255, 0.1);
}

.camera-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
  display: block;
}

.camera-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.camera-status {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(6px);
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
}

.status-active .status-dot {
  background: #22c55e;
  box-shadow: 0 0 6px #22c55e;
  animation: pulse 1.4s infinite;
}
.status-active { color: #22c55e; }

.status-ready .status-dot { background: var(--color-primary); }
.status-ready { color: var(--color-primary); }

.status-error .status-dot { background: #ef4444; }
.status-error { color: #ef4444; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

.camera-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(13, 13, 26, 0.92);
  color: var(--color-text-muted);
  font-size: 0.9rem;
  text-align: center;
  padding: 20px;
}

.placeholder-icon { font-size: 3rem; }

/* ── 控制按钮 ── */
.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  padding: 10px 22px;
  border: none;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 4px 15px var(--color-primary-glow);
}
.btn-primary:not(:disabled):hover {
  filter: brightness(1.15);
  transform: translateY(-1px);
}

.btn-accent {
  background: linear-gradient(135deg, #00d4ff, #0099cc);
  color: #fff;
  box-shadow: 0 4px 15px rgba(0, 212, 255, 0.3);
}
.btn-accent:not(:disabled):hover {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.model-select-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 200px;
}

.model-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}

.model-select {
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  max-width: 280px;
}

.model-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-glow);
}

.fps-display {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  line-height: 1.3;
}
.fps-display strong {
  font-size: 1.05rem;
  color: var(--color-accent);
}

/* ── 结果面板 ── */
.results-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.face-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 18px 20px;
}

.face-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.face-index {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.dominant-badge {
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 0.88rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.03em;
}

/* ── 情绪条 ── */
.emotion-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.emotion-row {
  display: grid;
  grid-template-columns: 56px 1fr 46px;
  align-items: center;
  gap: 10px;
}

.emotion-name {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  text-align: right;
  white-space: nowrap;
}

.bar-track {
  height: 8px;
  background: var(--color-border);
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.35s ease;
  min-width: 2px;
}

.emotion-val {
  font-size: 0.78rem;
  color: var(--color-text);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ── 提示 / 错误 ── */
.no-face-tip {
  text-align: center;
  color: var(--color-text-muted);
  font-size: 0.88rem;
  padding: 14px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius);
}

.error-banner {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #fca5a5;
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 0.88rem;
}

/* ── 过渡动画 ── */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
