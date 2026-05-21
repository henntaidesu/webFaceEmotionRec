<template>
  <div class="comfy-panel">
    <!-- ── 顶部工具栏 ── -->
    <div class="comfy-header">
      <div class="header-left">
        <span class="panel-title">ComfyUI</span>
        <span class="server-addr">{{ COMFYUI_HOST }}</span>
      </div>
      <div class="header-right">
        <span class="conn-badge" :class="connClass">
          <span class="conn-dot"></span>
          {{ connLabel }}
        </span>
        <button class="icon-btn" :title="locale.comfyRetry" @click="retryConn">↻</button>
      </div>
    </div>

    <!-- ── 主体滚动区 ── -->
    <div class="comfy-body">
      <!-- 离线提示 -->
      <div v-if="!online" class="offline-box">
        <span class="offline-icon">⚡</span>
        <p class="offline-title">{{ locale.comfyDisconnected }}</p>
        <p class="offline-hint">{{ locale.comfyOfflineHint }}</p>
        <button class="btn-retry" @click="retryConn">{{ locale.comfyRetry }}</button>
      </div>

      <!-- 在线操作面板 -->
      <template v-else>
        <!-- 模型 -->
        <div class="field">
          <label class="field-label">{{ locale.comfyModel }}</label>
          <select v-model="form.checkpoint" class="ctrl-select">
            <option v-if="checkpoints.length === 0" value="">{{ locale.comfyLoadingModels }}</option>
            <option v-for="ck in checkpoints" :key="ck" :value="ck">{{ ck }}</option>
          </select>
        </div>

        <!-- 尺寸 -->
        <div class="field">
          <label class="field-label">{{ locale.comfySize }}</label>
          <div class="row-group">
            <input type="number" v-model.number="form.width"  class="ctrl-num" min="64" max="2048" step="64" />
            <span class="separator">×</span>
            <input type="number" v-model.number="form.height" class="ctrl-num" min="64" max="2048" step="64" />
            <div class="preset-btns">
              <button
                v-for="p in sizePresets"
                :key="p.label"
                class="preset-btn"
                :class="{ active: form.width === p.w && form.height === p.h }"
                @click="form.width = p.w; form.height = p.h"
              >{{ p.label }}</button>
            </div>
          </div>
        </div>

        <!-- 正向提示词 -->
        <div class="field">
          <div class="field-label-row">
            <label class="field-label">{{ locale.comfyPositive }}</label>
            <button
              v-if="emotionPrompt"
              class="use-emotion-btn"
              :title="locale.comfyUseEmotion"
              @click="appendEmotionPrompt"
            >{{ locale.comfyUseEmotion }}</button>
          </div>
          <textarea
            v-model="form.positive"
            class="ctrl-textarea"
            rows="3"
            :placeholder="locale.comfyPositivePH"
          />
        </div>

        <!-- 负向提示词 -->
        <div class="field">
          <label class="field-label">{{ locale.comfyNegative }}</label>
          <textarea
            v-model="form.negative"
            class="ctrl-textarea"
            rows="2"
            :placeholder="locale.comfyNegativePH"
          />
        </div>

        <!-- 步数 / CFG -->
        <div class="two-col">
          <div class="field">
            <label class="field-label">{{ locale.comfySteps }} <strong class="val">{{ form.steps }}</strong></label>
            <input type="range" v-model.number="form.steps" min="1" max="100" class="slider" />
          </div>
          <div class="field">
            <label class="field-label">{{ locale.comfyCfg }} <strong class="val">{{ form.cfg }}</strong></label>
            <input type="range" v-model.number="form.cfg" min="1" max="20" step="0.5" class="slider" />
          </div>
        </div>

        <!-- 采样器 / 调度器 -->
        <div class="two-col">
          <div class="field">
            <label class="field-label">{{ locale.comfySampler }}</label>
            <select v-model="form.sampler" class="ctrl-select">
              <option v-for="s in SAMPLERS" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">{{ locale.comfyScheduler }}</label>
            <select v-model="form.scheduler" class="ctrl-select">
              <option v-for="s in SCHEDULERS" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
        </div>

        <!-- 种子 -->
        <div class="field">
          <label class="field-label">{{ locale.comfySeed }}</label>
          <div class="row-group">
            <input type="number" v-model.number="form.seed" class="ctrl-num seed-input" min="-1" />
            <button class="icon-btn" :title="locale.comfyRandomSeed" @click="form.seed = -1">🎲</button>
            <span class="seed-hint">{{ form.seed < 0 ? locale.comfyRandomSeedHint : '' }}</span>
          </div>
        </div>

        <!-- 生成按钮 -->
        <button class="btn-generate" :disabled="generating || !form.checkpoint" @click="generate">
          <span v-if="generating">
            {{ locale.comfyGenerating }}
            <span v-if="progress.max > 0"> · {{ progress.current }}/{{ progress.max }}</span>
          </span>
          <span v-else>⚡ {{ locale.comfyGenerate }}</span>
        </button>

        <!-- 进度条 -->
        <div v-if="generating" class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
          </div>
          <span class="progress-node">{{ progress.node }}</span>
        </div>

        <!-- 状态消息 -->
        <p v-if="statusMsg" class="status-msg" :class="statusMsgClass">{{ statusMsg }}</p>

        <!-- 生成结果图 -->
        <div v-if="resultImages.length > 0" class="result-area">
          <div class="result-header">
            <span class="result-label">{{ locale.comfyResult }}</span>
            <button class="clear-btn" @click="resultImages = []">✕</button>
          </div>
          <div class="result-grid">
            <div v-for="(img, i) in resultImages" :key="i" class="result-item">
              <img :src="img" class="result-img" @click="lightboxSrc = img" />
              <a :href="img" download class="dl-btn" :title="locale.comfyDownload">↓</a>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 灯箱预览 -->
    <Teleport to="body">
      <div v-if="lightboxSrc" class="lightbox" @click="lightboxSrc = null">
        <img :src="lightboxSrc" class="lightbox-img" @click.stop />
        <button class="lightbox-close" @click="lightboxSrc = null">✕</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import {
  checkOnline,
  fetchCheckpoints,
  queuePrompt,
  getHistory,
  imageUrl,
  makeClientId,
  openProgressWS,
  buildTxt2ImgWorkflow,
  SAMPLERS,
  SCHEDULERS,
  COMFYUI_HOST,
} from '../api/comfyuiApi.js'

const props = defineProps({
  locale: { type: Object, required: true },
  /** 来自左侧情感识别的 emotion 关键词，可选 */
  emotionPrompt: { type: String, default: '' },
})

// ── 连接状态 ─────────────────────────────────────────
const online    = ref(false)
const checking  = ref(false)
const checkpoints = ref([])

const connClass = computed(() => {
  if (checking.value) return 'conn-checking'
  return online.value ? 'conn-ok' : 'conn-off'
})
const connLabel = computed(() => {
  if (checking.value) return props.locale.comfyConnecting
  return online.value ? props.locale.comfyConnected : props.locale.comfyDisconnected
})

async function retryConn() {
  checking.value = true
  online.value = await checkOnline()
  checking.value = false
  if (online.value && checkpoints.value.length === 0) {
    loadCheckpoints()
  }
}

async function loadCheckpoints() {
  try {
    const list = await fetchCheckpoints()
    checkpoints.value = list
    if (list.length > 0 && !form.checkpoint) {
      form.checkpoint = list[0]
    }
  } catch { /* 忽略，不阻断流程 */ }
}

// ── 表单状态 ─────────────────────────────────────────
const form = reactive({
  checkpoint: '',
  width:     512,
  height:    512,
  positive:  'masterpiece, best quality',
  negative:  'lowres, bad anatomy, bad hands, worst quality, blurry',
  steps:     20,
  cfg:       7,
  sampler:   'euler',
  scheduler: 'normal',
  seed:      -1,
})

const sizePresets = [
  { label: '512²', w: 512,  h: 512  },
  { label: '768²', w: 768,  h: 768  },
  { label: '512×768', w: 512, h: 768 },
  { label: '1024²', w: 1024, h: 1024 },
]

function appendEmotionPrompt() {
  const kw = props.emotionPrompt
  if (!kw) return
  form.positive = form.positive
    ? `${form.positive}, ${kw}`
    : kw
}

// ── 生成流程 ─────────────────────────────────────────
const generating = ref(false)
const progress = reactive({ current: 0, max: 0, node: '' })
const statusMsg  = ref('')
const statusMsgClass = ref('')
const resultImages = ref([])
const lightboxSrc  = ref(null)

const progressPct = computed(() => {
  if (progress.max <= 0) return 0
  return Math.round((progress.current / progress.max) * 100)
})

let ws  = null
let pollTimer = null

async function generate() {
  if (generating.value || !form.checkpoint) return

  generating.value = true
  resultImages.value = []
  statusMsg.value    = ''
  progress.current   = 0
  progress.max       = 0
  progress.node      = ''

  const clientId = makeClientId()

  try {
    // 建立 WebSocket 连接（用于进度推送）
    ws = openProgressWS(clientId)

    const { prompt_id } = await queuePrompt(
      clientId,
      buildTxt2ImgWorkflow({
        positive:   form.positive,
        negative:   form.negative,
        checkpoint: form.checkpoint,
        steps:      form.steps,
        cfg:        form.cfg,
        width:      form.width,
        height:     form.height,
        sampler:    form.sampler,
        scheduler:  form.scheduler,
        seed:       form.seed,
      }),
    )

    await waitForCompletion(ws, prompt_id)
  } catch (err) {
    statusMsg.value     = `${props.locale.comfyError}：${err.message}`
    statusMsgClass.value = 'msg-error'
    generating.value    = false
    closeWS()
  }
}

function waitForCompletion(socket, promptId) {
  return new Promise((resolve, reject) => {
    socket.addEventListener('message', async (e) => {
      let msg
      try { msg = JSON.parse(e.data) } catch { return }

      const { type, data } = msg

      if (type === 'progress' && data?.prompt_id === promptId) {
        progress.current = data.value
        progress.max     = data.max
        progress.node    = data.node ?? ''
      }

      if (type === 'executing' && data?.prompt_id === promptId) {
        progress.node = data.node ?? ''
      }

      if (
        (type === 'execution_success' && data?.prompt_id === promptId) ||
        (type === 'executing' && data?.node === null && data?.prompt_id === promptId)
      ) {
        try {
          const images = await collectImages(promptId)
          resultImages.value = images
          statusMsg.value      = props.locale.comfySuccess
          statusMsgClass.value = 'msg-ok'
        } catch (err) {
          statusMsg.value      = `${props.locale.comfyError}：${err.message}`
          statusMsgClass.value = 'msg-error'
        } finally {
          generating.value = false
          closeWS()
          resolve()
        }
      }

      if (type === 'execution_error' && data?.prompt_id === promptId) {
        reject(new Error(data?.exception_message ?? 'execution error'))
      }
    })

    socket.addEventListener('error', () => {
      reject(new Error('WebSocket error'))
    })

    socket.addEventListener('close', () => {
      if (generating.value) {
        // WS 断开但仍在生成，降级轮询历史
        pollHistory(promptId, resolve, reject)
      }
    })
  })
}

async function collectImages(promptId) {
  const history = await getHistory(promptId)
  const entry = history[promptId]
  if (!entry) throw new Error('history not found')

  const urls = []
  for (const nodeOutputs of Object.values(entry.outputs ?? {})) {
    for (const img of nodeOutputs.images ?? []) {
      urls.push(imageUrl(img.filename, img.subfolder, img.type))
    }
  }
  return urls
}

function pollHistory(promptId, resolve, reject) {
  let attempts = 0
  pollTimer = setInterval(async () => {
    attempts++
    try {
      const images = await collectImages(promptId)
      if (images.length > 0) {
        clearInterval(pollTimer)
        resultImages.value   = images
        statusMsg.value      = props.locale.comfySuccess
        statusMsgClass.value = 'msg-ok'
        generating.value     = false
        resolve()
      }
    } catch { /* 继续轮询 */ }
    if (attempts >= 60) {
      clearInterval(pollTimer)
      reject(new Error('timeout waiting for result'))
    }
  }, 2000)
}

function closeWS() {
  if (ws) {
    ws.close()
    ws = null
  }
}

// ── 生命周期 ─────────────────────────────────────────
let connTimer = null

onMounted(() => {
  retryConn()
  connTimer = setInterval(retryConn, 20_000)
})

onUnmounted(() => {
  clearInterval(connTimer)
  clearInterval(pollTimer)
  closeWS()
})
</script>

<style scoped>
/* ── 面板容器 ── */
.comfy-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
}

/* ── 顶部工具栏 ── */
.comfy-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  background: var(--color-surface-2);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-title {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--color-text);
}

.server-addr {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  font-family: ui-monospace, monospace;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 连接状态标签 ── */
.conn-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 600;
}

.conn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.conn-ok       { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
.conn-off      { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }
.conn-checking { background: rgba(255, 193, 7, 0.12);  color: #ffc107; }

.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* ── 主体滚动区 ── */
.comfy-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 离线提示 ── */
.offline-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
  padding: 40px 24px;
  color: var(--color-text-muted);
}

.offline-icon  { font-size: 2rem; }
.offline-title { font-size: 1rem; font-weight: 600; color: var(--color-text); }
.offline-hint  { font-size: 0.8rem; line-height: 1.6; max-width: 300px; }

.btn-retry {
  margin-top: 6px;
  padding: 8px 22px;
  border-radius: 20px;
  border: none;
  background: var(--color-primary);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}
.btn-retry:hover { opacity: 0.9; }

/* ── 表单字段 ── */
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.val {
  color: var(--color-accent);
  font-size: 0.85rem;
  margin-left: 4px;
}

/* ── 控件通用 ── */
.ctrl-select,
.ctrl-num,
.ctrl-textarea {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  font-size: 0.82rem;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
}

.ctrl-select:focus,
.ctrl-num:focus,
.ctrl-textarea:focus {
  border-color: var(--color-primary);
}

.ctrl-textarea {
  resize: vertical;
  min-height: 56px;
  line-height: 1.5;
  font-family: inherit;
}

.ctrl-num {
  width: 72px;
  text-align: center;
  -moz-appearance: textfield;
}
.ctrl-num::-webkit-inner-spin-button,
.ctrl-num::-webkit-outer-spin-button { -webkit-appearance: none; }

/* ── 行布局 ── */
.row-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.separator {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.preset-btns {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.preset-btn {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.15s;
}

.preset-btn:hover,
.preset-btn.active {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: rgba(108, 99, 255, 0.1);
}

.seed-input { width: 120px; }

.seed-hint {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  font-style: italic;
}

/* ── 两列布局 ── */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

/* ── 滑块 ── */
.slider {
  -webkit-appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--color-border);
  outline: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--color-primary);
  border: 2px solid var(--color-bg);
  cursor: pointer;
}

/* ── 情感快填按钮 ── */
.use-emotion-btn {
  padding: 3px 9px;
  border-radius: 6px;
  border: 1px solid var(--color-accent);
  background: rgba(0, 212, 255, 0.08);
  color: var(--color-accent);
  font-size: 0.7rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.use-emotion-btn:hover {
  background: rgba(0, 212, 255, 0.18);
}

/* ── 生成按钮 ── */
.btn-generate {
  width: 100%;
  padding: 11px 0;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary), #a855f7);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
  letter-spacing: 0.04em;
  margin-top: 4px;
}

.btn-generate:hover:not(:disabled) { opacity: 0.92; transform: translateY(-1px); }
.btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── 进度条 ── */
.progress-wrap {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.progress-bar {
  height: 5px;
  border-radius: 3px;
  background: var(--color-border);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
  transition: width 0.3s ease;
}

.progress-node {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

/* ── 状态消息 ── */
.status-msg {
  font-size: 0.78rem;
  border-radius: 6px;
  padding: 7px 10px;
}

.msg-ok    { background: rgba(46, 204, 113, 0.12); color: #2ecc71; }
.msg-error { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }

/* ── 结果图区 ── */
.result-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}

.clear-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.result-item {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.result-img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  cursor: zoom-in;
  transition: transform 0.2s;
}

.result-img:hover { transform: scale(1.03); }

.dl-btn {
  position: absolute;
  bottom: 5px;
  right: 5px;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 0.85rem;
  text-decoration: none;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}

.result-item:hover .dl-btn { opacity: 1; }

/* ── 灯箱 ── */
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: zoom-out;
}

.lightbox-img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: 10px;
  cursor: default;
}

.lightbox-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.15);
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
}
</style>
