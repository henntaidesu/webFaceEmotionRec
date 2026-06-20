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
        <!-- 工作流（服务器端工作区） -->
        <div class="field">
          <div class="field-label-row">
            <label class="field-label">{{ locale.comfyWorkflow }}</label>
            <button class="icon-btn wf-refresh" :title="locale.comfyRetry" @click="loadWorkflows">↻</button>
          </div>
          <select v-model="selectedWorkflow" class="ctrl-select">
            <option value="">{{ locale.comfyWorkflowBuiltin }}</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf.replace(/\.json$/, '') }}</option>
          </select>
        </div>

        <!-- 模型（仅内置工作流） -->
        <div v-if="!selectedWorkflow" class="field">
          <label class="field-label">{{ locale.comfyModel }}</label>
          <select v-model="form.checkpoint" class="ctrl-select">
            <option v-if="checkpoints.length === 0" value="">{{ locale.comfyLoadingModels }}</option>
            <option v-for="ck in checkpoints" :key="ck" :value="ck">{{ ck }}</option>
          </select>
        </div>

        <!-- 尺寸 -->
        <div v-if="!selectedWorkflow" class="field">
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

        <!-- VR 情感预设 -->
        <div class="field">
          <div class="field-label-row">
            <label class="field-label">{{ locale.comfyVrPreset }}</label>
            <button class="use-emotion-btn" @click="useRandomPrompt">🎲 {{ locale.comfyRandomPrompt }}</button>
          </div>
          <div class="preset-btns">
            <button
              v-for="p in vrPresets"
              :key="p.key"
              class="preset-btn"
              :class="{ active: activeVrPreset === p.key }"
              @click="applyVrPreset(p)"
            >{{ p.label }}</button>
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
        <div v-if="!selectedWorkflow" class="two-col">
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
        <div v-if="!selectedWorkflow" class="two-col">
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
        <button class="btn-generate" :disabled="generating || (!selectedWorkflow && !form.checkpoint)" @click="generate">
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

        <!-- ── 批量生成数据集 ── -->
        <div class="batch-box">
          <div class="batch-title">🗂 {{ locale.comfyBatchTitle }}</div>
          <p class="batch-desc">{{ locale.comfyBatchDesc }}</p>

          <div class="field">
            <label class="field-label">{{ locale.comfyBatchEmotions }}</label>
            <div class="preset-btns">
              <button
                v-for="p in vrPresets"
                :key="p.key"
                class="preset-btn"
                :class="{ active: batch.emotions.includes(p.key) }"
                :disabled="batch.running"
                @click="toggleBatchEmotion(p.key)"
              >{{ p.label }}</button>
            </div>
          </div>

          <div class="two-col">
            <div class="field">
              <label class="field-label">{{ locale.comfyBatchPerEmotion }}</label>
              <input
                type="number"
                v-model.number="batch.perEmotion"
                class="ctrl-num"
                min="1"
                max="5000"
                :disabled="batch.running"
              />
            </div>
            <div class="field">
              <label class="field-label">{{ locale.comfyBatchFolder }}</label>
              <input
                type="text"
                v-model.trim="batch.folder"
                class="ctrl-select"
                :disabled="batch.running"
              />
            </div>
          </div>

          <p class="batch-hint">
            {{ locale.comfyBatchSaveHint }}
            <code>output/{{ batch.folder || 'vr_dataset' }}/&lt;emotion&gt;/</code>
          </p>

          <button
            v-if="!batch.running"
            class="btn-generate"
            :disabled="!form.checkpoint || batch.emotions.length === 0 || batch.perEmotion < 1"
            @click="startBatch"
          >
            {{ locale.comfyBatchStart }} ({{ batch.emotions.length * batch.perEmotion }})
          </button>
          <button v-else class="btn-stop" @click="stopBatch">
            ■ {{ locale.comfyBatchStop }}
          </button>

          <div v-if="batch.running || batch.done > 0" class="batch-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: batchPct + '%' }"></div>
            </div>
            <div class="batch-stat">
              <span>{{ batch.done }} / {{ batch.total }}</span>
              <span v-if="batch.currentEmotion" class="cur">· {{ emoLabel(batch.currentEmotion) }}</span>
              <span class="ok">✓ {{ batch.ok }}</span>
              <span v-if="batch.fail > 0" class="fail">✗ {{ batch.fail }}</span>
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
  fetchWorkflows,
  fetchWorkflow,
  fetchObjectInfo,
  uiToApiFormat,
  applyPromptOverrides,
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
import { randomVrPrompt } from '../api/vrPrompts.js'

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
  if (online.value && workflows.value.length === 0) {
    loadWorkflows()
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

// ── 服务器端工作流（工作区） ───────────────────────────
const workflows = ref([])
const selectedWorkflow = ref('')

async function loadWorkflows() {
  try {
    workflows.value = await fetchWorkflows()
  } catch { workflows.value = [] }
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

// ── VR 情感提示词预设（眼部被 VR 头显遮挡，情绪靠口部/姿态表达） ──
const VR_BASE_PROMPT =
  'masterpiece, best quality, ultra detailed, photorealistic portrait photograph of one person ' +
  'wearing a modern white VR headset, head-mounted display covering both eyes, ' +
  'upper half of face occluded by VR goggles, mouth and chin clearly visible, ' +
  'front view, studio lighting, clean neutral background, sharp focus, detailed skin texture'

const VR_NEGATIVE_PROMPT =
  'lowres, worst quality, blurry, bad anatomy, deformed face, extra fingers, extra limbs, ' +
  'cartoon, anime, painting, sketch, text, watermark, logo, visible eyes, no headset, multiple people'

const VR_EMOTIONS = [
  { key: 'happy',    zh: '开心', prompt: 'joyful expression, wide open-mouth smile, grinning, raised cheeks, cheerful mood' },
  { key: 'sad',      zh: '悲伤', prompt: 'sad expression, downturned mouth corners, frowning lips, sorrowful mood, slightly lowered head' },
  { key: 'angry',    zh: '愤怒', prompt: 'angry expression, clenched jaw, gritted teeth, tense mouth, aggressive mood' },
  { key: 'surprise', zh: '惊讶', prompt: 'surprised expression, wide open mouth, dropped jaw, astonished mood, hands raised near face' },
  { key: 'fear',     zh: '恐惧', prompt: 'fearful expression, trembling open mouth, tense grimace, frightened mood, defensive posture' },
  { key: 'disgust',  zh: '厌恶', prompt: 'disgusted expression, wrinkled nose, raised upper lip, sneering mouth, repulsed mood' },
  { key: 'neutral',  zh: '平静', prompt: 'neutral expression, relaxed closed mouth, calm composed mood' },
]

const activeVrPreset = ref('')
const vrPresets = computed(() =>
  VR_EMOTIONS.map((e) => ({ ...e, label: props.locale.emotionMap[e.zh] ?? e.zh })),
)

function applyVrPreset(p) {
  activeVrPreset.value = p.key
  form.positive = `${VR_BASE_PROMPT}, ${p.prompt}`
  form.negative = VR_NEGATIVE_PROMPT
}

/** 从 7000 条提示词库中随机抽取一条（已选情感预设则在该情感内抽取） */
async function useRandomPrompt() {
  try {
    const { emotion, prompt } = await randomVrPrompt(activeVrPreset.value)
    activeVrPreset.value = emotion
    form.positive = prompt
    form.negative = VR_NEGATIVE_PROMPT
  } catch (err) {
    statusMsg.value = `${props.locale.comfyError}：${err.message}`
    statusMsgClass.value = 'msg-error'
  }
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

/** 组装最终提交的工作流：服务器端工作区 或 内置 txt2img */
async function buildWorkflow() {
  if (!selectedWorkflow.value) {
    return buildTxt2ImgWorkflow({
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
    })
  }
  const [raw, objectInfo] = await Promise.all([
    fetchWorkflow(selectedWorkflow.value),
    fetchObjectInfo(),
  ])
  // userdata 中保存的工作区通常是 UI 格式（含 nodes 数组），需转换；API 格式直接使用
  const apiWorkflow = Array.isArray(raw?.nodes) ? uiToApiFormat(raw, objectInfo) : raw
  return applyPromptOverrides(apiWorkflow, {
    positive: form.positive,
    negative: form.negative,
    seed:     form.seed,
  })
}

async function generate() {
  if (generating.value || (!selectedWorkflow.value && !form.checkpoint)) return

  generating.value = true
  resultImages.value = []
  statusMsg.value    = ''
  progress.current   = 0
  progress.max       = 0
  progress.node      = ''

  const clientId = makeClientId()

  try {
    const workflow = await buildWorkflow()

    // 建立 WebSocket 连接（用于进度推送）
    ws = openProgressWS(clientId)

    const { prompt_id } = await queuePrompt(clientId, workflow)

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

// ── 批量数据集生成 ────────────────────────────────────
const batch = reactive({
  emotions:   VR_EMOTIONS.map((e) => e.key), // 默认全选 7 类
  perEmotion: 50,
  folder:     'vr_dataset',
  running:    false,
  done:       0,
  total:      0,
  ok:         0,
  fail:       0,
  currentEmotion: '',
})

const batchPct = computed(() =>
  batch.total > 0 ? Math.round((batch.done / batch.total) * 100) : 0,
)

const emoLabel = (key) => vrPresets.value.find((p) => p.key === key)?.label ?? key

function toggleBatchEmotion(key) {
  if (batch.running) return
  const i = batch.emotions.indexOf(key)
  if (i >= 0) batch.emotions.splice(i, 1)
  else batch.emotions.push(key)
}

let batchStop = false
let batchWs   = null

async function startBatch() {
  if (batch.running) return
  if (!form.checkpoint) {
    statusMsg.value      = props.locale.comfyBatchNoCheckpoint
    statusMsgClass.value = 'msg-error'
    return
  }
  if (batch.emotions.length === 0 || batch.perEmotion < 1) return

  batchStop      = false
  batch.running  = true
  batch.done     = 0
  batch.ok       = 0
  batch.fail     = 0
  batch.total    = batch.emotions.length * batch.perEmotion
  batch.currentEmotion = ''
  statusMsg.value = ''
  progress.current = 0
  progress.max     = 0

  const clientId = makeClientId()
  batchWs = openProgressWS(clientId)
  const folder = batch.folder || 'vr_dataset'

  try {
    for (const emo of batch.emotions) {
      if (batchStop) break
      batch.currentEmotion = emo
      const prefix = `${folder}/${emo}/${emo}`
      for (let i = 0; i < batch.perEmotion; i++) {
        if (batchStop) break
        try {
          const { prompt } = await randomVrPrompt(emo)
          const workflow = buildTxt2ImgWorkflow({
            positive:        prompt,
            negative:        VR_NEGATIVE_PROMPT,
            checkpoint:      form.checkpoint,
            steps:           form.steps,
            cfg:             form.cfg,
            width:           form.width,
            height:          form.height,
            sampler:         form.sampler,
            scheduler:       form.scheduler,
            seed:            -1,
            filename_prefix: prefix,
          })
          const { prompt_id } = await queuePrompt(clientId, workflow)
          await waitForPrompt(batchWs, prompt_id)
          batch.ok++
        } catch {
          batch.fail++
        } finally {
          batch.done++
        }
      }
    }
    statusMsg.value      = batchStop ? props.locale.comfyBatchStopped : props.locale.comfyBatchDone
    statusMsgClass.value = batchStop ? 'msg-error' : 'msg-ok'
  } finally {
    batch.running        = false
    batch.currentEmotion = ''
    if (batchWs) { batchWs.close(); batchWs = null }
  }
}

function stopBatch() {
  batchStop = true
}

/** 等待单个 prompt 执行完成；WS 漏消息时靠 history 轮询兜底 */
function waitForPrompt(socket, promptId) {
  return new Promise((resolve, reject) => {
    let settled = false
    let poll    = null

    function cleanup() {
      socket.removeEventListener('message', onMsg)
      if (poll) clearInterval(poll)
    }
    function done() {
      if (settled) return
      settled = true
      cleanup()
      resolve()
    }
    function onMsg(e) {
      let msg
      try { msg = JSON.parse(e.data) } catch { return }
      const { type, data } = msg
      if (type === 'progress' && data?.prompt_id === promptId) {
        progress.current = data.value
        progress.max     = data.max
      }
      if (
        (type === 'execution_success' && data?.prompt_id === promptId) ||
        (type === 'executing' && data?.node === null && data?.prompt_id === promptId)
      ) {
        done()
      }
      if (type === 'execution_error' && data?.prompt_id === promptId) {
        if (settled) return
        settled = true
        cleanup()
        reject(new Error(data?.exception_message ?? 'execution error'))
      }
    }

    socket.addEventListener('message', onMsg)
    // 兜底：每 3s 查一次 history，命中输出即判定完成
    poll = setInterval(async () => {
      try {
        const h = await getHistory(promptId)
        if (h[promptId]?.outputs) done()
      } catch { /* 继续轮询 */ }
    }, 3000)
  })
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
  batchStop = true
  if (batchWs) { batchWs.close(); batchWs = null }
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

/* ── 工作流刷新按钮 ── */
.wf-refresh {
  width: 22px;
  height: 22px;
  font-size: 0.78rem;
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

/* ── 批量数据集生成 ── */
.batch-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 6px;
  padding: 14px;
  border: 1px dashed var(--color-border);
  border-radius: 10px;
  background: var(--color-surface-2);
}

.batch-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-text);
}

.batch-desc {
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--color-text-muted);
}

.batch-hint {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.batch-hint code {
  font-family: ui-monospace, monospace;
  color: var(--color-accent);
}

.btn-stop {
  width: 100%;
  padding: 11px 0;
  border: none;
  border-radius: 10px;
  background: rgba(255, 107, 107, 0.16);
  color: #ff6b6b;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s;
}
.btn-stop:hover { opacity: 0.85; }

.batch-progress {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.batch-stat {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.72rem;
  color: var(--color-text-muted);
}
.batch-stat .cur  { color: var(--color-primary); }
.batch-stat .ok   { color: #2ecc71; margin-left: auto; }
.batch-stat .fail { color: #ff6b6b; }

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
