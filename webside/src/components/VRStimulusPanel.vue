<template>
  <div class="comfy-panel">
    <!-- ── 顶部工具栏 ── -->
    <div class="comfy-header">
      <div class="header-left">
        <span class="panel-title">{{ locale.stimulus.title }}</span>
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
        <p class="offline-hint">{{ locale.stimulus.offlineHint }}</p>
        <button class="btn-retry" @click="retryConn">{{ locale.comfyRetry }}</button>
      </div>

      <template v-else>
        <p class="panel-desc">{{ locale.stimulus.desc }}</p>

        <!-- 目标情绪 -->
        <div class="field">
          <label class="field-label">{{ locale.stimulus.emotion }}</label>
          <div class="preset-btns">
            <button
              v-for="e in emotions"
              :key="e.key"
              class="preset-btn"
              :class="{ active: selectedEmotion === e.key }"
              @click="selectEmotion(e.key)"
            >{{ e.label }}</button>
          </div>
        </div>

        <!-- 场景提示词 -->
        <div class="field">
          <div class="field-label-row">
            <label class="field-label">{{ locale.stimulus.scene }}</label>
            <button class="use-emotion-btn" @click="pickPrompt">{{ locale.stimulus.pick }}</button>
          </div>
          <textarea v-model="currentPrompt" class="ctrl-textarea" rows="3" />
        </div>

        <!-- 负向提示词 -->
        <div class="field">
          <label class="field-label">{{ locale.stimulus.negative }}</label>
          <textarea v-model="negative" class="ctrl-textarea" rows="2" />
        </div>

        <!-- 种子 -->
        <div class="field">
          <label class="field-label">{{ locale.stimulus.seed }}</label>
          <div class="row-group">
            <input type="number" v-model.number="seed" class="ctrl-num seed-input" min="-1" />
            <button class="icon-btn" :title="locale.stimulus.randomSeed" @click="seed = -1">🎲</button>
            <span class="seed-hint">{{ seed < 0 ? locale.stimulus.randomSeedHint : '' }}</span>
          </div>
        </div>

        <!-- 生成按钮 -->
        <button class="btn-generate" :disabled="generating || !currentPrompt" @click="generate">
          <span v-if="generating">
            {{ locale.stimulus.generating }}
            <span v-if="progress.max > 0"> · {{ progress.current }}/{{ progress.max }}</span>
          </span>
          <span v-else>{{ locale.stimulus.generate }}</span>
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

        <!-- 结果图 -->
        <div v-if="results.length > 0" class="result-area">
          <div class="result-header">
            <span class="result-label">{{ locale.stimulus.result }}（{{ results.length }}）</span>
            <div class="result-actions">
              <label class="dwell-label">
                {{ locale.stimulus.dwell }}
                <input type="number" v-model.number="session.dwell" class="dwell-input" min="2" max="60" />
              </label>
              <button class="use-emotion-btn" @click="startSession">{{ locale.stimulus.sessionStart }}</button>
              <button class="clear-btn" @click="results = []">✕</button>
            </div>
          </div>
          <div class="result-grid">
            <div v-for="(img, i) in results" :key="i" class="result-item">
              <img :src="img.url" class="result-img" :title="locale.stimulus.fullscreen" @click="panoSrc = img.url" />
              <span class="emo-tag">{{ img.label }}</span>
              <a :href="img.url" download class="dl-btn" :title="locale.stimulus.download">↓</a>
            </div>
          </div>
        </div>

        <!-- ── 批量生成刺激图集 ── -->
        <div class="batch-box">
          <div class="batch-title">🗂 {{ locale.stimulus.batchTitle }}</div>
          <p class="batch-desc">{{ locale.stimulus.batchDesc }}</p>

          <div class="field">
            <label class="field-label">{{ locale.stimulus.batchEmotions }}</label>
            <div class="preset-btns">
              <button
                v-for="e in emotions"
                :key="e.key"
                class="preset-btn"
                :class="{ active: batch.emotions.includes(e.key) }"
                :disabled="batch.running"
                @click="toggleBatchEmotion(e.key)"
              >{{ e.label }}</button>
            </div>
          </div>

          <div class="two-col">
            <div class="field">
              <label class="field-label">{{ locale.stimulus.batchPerEmotion }}</label>
              <input type="number" v-model.number="batch.perEmotion" class="ctrl-num" min="1" max="500" :disabled="batch.running" />
            </div>
            <div class="field">
              <label class="field-label">{{ locale.stimulus.batchFolder }}</label>
              <input type="text" v-model.trim="batch.folder" class="ctrl-textarea batch-folder" :disabled="batch.running" />
            </div>
          </div>

          <p class="batch-hint">
            {{ locale.stimulus.batchSaveHint }}
            <code>output/{{ batch.folder || 'vr_stimulus' }}/&lt;emotion&gt;/</code>
          </p>

          <button
            v-if="!batch.running"
            class="btn-generate"
            :disabled="batch.emotions.length === 0 || batch.perEmotion < 1"
            @click="startBatch"
          >
            {{ locale.stimulus.batchStart }} ({{ batch.emotions.length * batch.perEmotion }})
          </button>
          <button v-else class="btn-stop" @click="stopBatch">■ {{ locale.stimulus.batchStop }}</button>

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

    <!-- 沉浸式 360° 全景查看器（可在 Quest 浏览器点击进入 VR） -->
    <PanoramaViewer
      v-if="panoSrc"
      :src="panoSrc"
      :caption="sessionCaption"
      :enter-vr-label="locale.stimulus.fullscreen"
      :download-label="locale.stimulus.download"
      @close="closeViewer"
    />
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import {
  checkOnline,
  fetchWorkflow,
  fetchObjectInfo,
  uiToApiFormat,
  applyPromptOverrides,
  queuePrompt,
  getHistory,
  imageUrl,
  makeClientId,
  openProgressWS,
  COMFYUI_HOST,
} from '../api/comfyuiApi.js'
import { randomVrStimulus } from '../api/vrStimulus.js'
// 懒加载：three.js 仅在打开 360 查看器时才按需加载，保持首屏包体积
const PanoramaViewer = defineAsyncComponent(() => import('./PanoramaViewer.vue'))

const props = defineProps({
  locale: { type: Object, required: true },
})

// 复用已放入 ComfyUI 工作流目录的 360 全景工作流
const STIMULUS_WORKFLOW = 'qwen360_pano.json'
// 全景触发词前缀（LoRA 需要 equirectangular 类关键词）
const PANO_PREFIX =
  '360 panorama, equirectangular projection, full spherical seamless panorama, photograph, '
const DEFAULT_NEG =
  'lowres, worst quality, blurry, distorted, polar distortion, poles warping, watermark, text, people, person, human'

// 7 类情绪 → 诱导该情绪的 360° 场景库（英文喂模型）
const EMOTIONS = [
  { key: 'happy', zh: '开心', scenes: [
    'sunny tropical beach paradise, turquoise water, palm trees, bright cheerful daylight',
    'vast blooming flower field under a clear blue sky, butterflies, warm sunshine',
    'colorful amusement park with a carousel and floating balloons, festive joyful atmosphere',
    'cozy sunlit green meadow with playful puppies, golden warm light',
    'vibrant festival at night with fireworks and confetti, celebration, joyful glowing lights',
  ] },
  { key: 'sad', zh: '悲伤', scenes: [
    'lonely rainy city street at dusk, wet empty pavement, grey melancholic mood',
    'abandoned empty room with dim light and floating dust, nostalgic loneliness',
    'foggy grey cemetery under bare trees, somber sorrowful atmosphere',
    'desolate autumn forest with falling withered leaves, overcast heavy sky',
    'empty quiet hospital corridor at night, cold blue melancholic light',
  ] },
  { key: 'angry', zh: '愤怒', scenes: [
    'chaotic gridlock traffic jam, glaring red brake lights, frustrating congestion',
    'stormy red sky over a burning industrial wasteland, intense oppressive atmosphere',
    'ruined war-torn city street, rubble and thick smoke, tense hostile mood',
    'raging wildfire consuming a dark forest, fierce red flames surrounding, oppressive heat',
    'crowded overwhelming subway platform at rush hour, claustrophobic irritating crush',
  ] },
  { key: 'surprise', zh: '惊讶', scenes: [
    'sudden glowing magical portal opening in a mystical forest, dazzling light burst',
    'surreal floating islands in the sky with cascading waterfalls, breathtaking unexpected vista',
    'spectacular cosmic aurora and an exploding galaxy overhead, awe-inspiring space',
    'giant whimsical creature emerging unexpectedly from the clouds, astonishing scene',
    'fantastical crystal cave suddenly revealed, sparkling with unexpected wonder',
  ] },
  { key: 'fear', zh: '恐惧', scenes: [
    'dark haunted forest at midnight, twisted trees, eerie fog, menacing shadows',
    'abandoned decaying asylum hallway, flickering lights, horror atmosphere',
    'standing at the edge of a dizzying tall cliff, vertigo, deep dark abyss below',
    'deep pitch-black cave with an unknown lurking presence, claustrophobic dread',
    'creepy foggy graveyard at night with looming tombstones, chilling terror',
  ] },
  { key: 'disgust', zh: '厌恶', scenes: [
    'overflowing garbage dump with rotting waste, swarming flies, foul filthy scene',
    'dirty clogged sewer tunnel with grimy sludge, repulsive decay',
    'moldy abandoned kitchen with rotten spoiled food, revolting filth',
    'swarm of insects crawling over decaying matter, nauseating scene',
    'polluted toxic swamp with murky slime and floating refuse, disgusting atmosphere',
  ] },
  { key: 'neutral', zh: '平静', scenes: [
    'plain minimalist empty white studio, soft even light, calm neutral space',
    'quiet serene zen garden with raked sand and stones, tranquil balance',
    'calm empty library reading room, soft daylight, peaceful stillness',
    'gentle misty lake at dawn, flat calm water, serene neutral mood',
    'simple tidy modern living room, soft neutral daylight, relaxed calm',
  ] },
]

// ── 连接状态 ──
const online   = ref(false)
const checking = ref(false)

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
}

// ── 情绪 / 提示词 ──
const selectedEmotion = ref('happy')
const currentPrompt   = ref('')
const negative        = ref(DEFAULT_NEG)
const seed            = ref(-1)

const emotions = computed(() =>
  EMOTIONS.map((e) => ({ ...e, label: props.locale.emotionMap[e.zh] ?? e.zh })),
)
const curEmotionObj = computed(() => EMOTIONS.find((e) => e.key === selectedEmotion.value))

// 优先从 CSV 场景库随机抽（128/情绪）；离线或加载失败时退回内置场景
async function pickPrompt() {
  try {
    const { prompt } = await randomVrStimulus(selectedEmotion.value)
    currentPrompt.value = prompt
  } catch {
    const list = curEmotionObj.value?.scenes ?? []
    if (list.length === 0) return
    currentPrompt.value = PANO_PREFIX + list[Math.floor(Math.random() * list.length)]
  }
}
function selectEmotion(key) {
  selectedEmotion.value = key
  pickPrompt()
}
pickPrompt() // 初始填一条

// ── 生成流程 ──
const generating = ref(false)
const progress   = reactive({ current: 0, max: 0, node: '' })
const statusMsg  = ref('')
const statusMsgClass = ref('')
const results    = ref([]) // { url, emotion, label }
const panoSrc    = ref(null)

const progressPct = computed(() =>
  progress.max > 0 ? Math.round((progress.current / progress.max) * 100) : 0,
)

let ws = null
let pollTimer = null

// 在 API 格式工作流中把 SaveImage 的 filename_prefix 改为指定路径（批量分目录保存用）
function setSavePrefix(api, prefix) {
  for (const node of Object.values(api)) {
    if (node.class_type === 'SaveImage' && node.inputs) node.inputs.filename_prefix = prefix
  }
  return api
}

async function buildWorkflow({ positive, seedVal, filenamePrefix } = {}) {
  let raw
  try {
    raw = await fetchWorkflow(STIMULUS_WORKFLOW)
  } catch {
    throw new Error(props.locale.stimulus.workflowMissing)
  }
  const objectInfo = await fetchObjectInfo()
  let api = Array.isArray(raw?.nodes) ? uiToApiFormat(raw, objectInfo) : raw
  // positive 已包含 360 全景前缀（CSV 库与内置回退均已带上）
  api = applyPromptOverrides(api, {
    positive: positive ?? currentPrompt.value,
    negative: negative.value,
    seed: seedVal ?? seed.value,
  })
  if (filenamePrefix) setSavePrefix(api, filenamePrefix)
  return api
}

async function generate() {
  if (generating.value || !currentPrompt.value) return

  generating.value = true
  statusMsg.value  = ''
  progress.current = 0
  progress.max     = 0
  progress.node    = ''

  const clientId = makeClientId()
  const emo   = selectedEmotion.value
  const label = props.locale.emotionMap[curEmotionObj.value?.zh] ?? emo

  try {
    const workflow = await buildWorkflow()
    ws = openProgressWS(clientId)
    const { prompt_id } = await queuePrompt(clientId, workflow)
    await waitForCompletion(ws, prompt_id, emo, label)
  } catch (err) {
    statusMsg.value      = `${props.locale.stimulus.error}：${err.message}`
    statusMsgClass.value = 'msg-error'
    generating.value     = false
    closeWS()
  }
}

function waitForCompletion(socket, promptId, emo, label) {
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
          const urls = await collectImages(promptId)
          results.value = [...urls.map((u) => ({ url: u, emotion: emo, label })), ...results.value]
          statusMsg.value      = props.locale.stimulus.success
          statusMsgClass.value = 'msg-ok'
        } catch (err) {
          statusMsg.value      = `${props.locale.stimulus.error}：${err.message}`
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

    socket.addEventListener('error', () => reject(new Error('WebSocket error')))
    socket.addEventListener('close', () => {
      if (generating.value) pollHistory(promptId, emo, label, resolve, reject)
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

function pollHistory(promptId, emo, label, resolve, reject) {
  let attempts = 0
  pollTimer = setInterval(async () => {
    attempts++
    try {
      const urls = await collectImages(promptId)
      if (urls.length > 0) {
        clearInterval(pollTimer)
        results.value = [...urls.map((u) => ({ url: u, emotion: emo, label })), ...results.value]
        statusMsg.value      = props.locale.stimulus.success
        statusMsgClass.value = 'msg-ok'
        generating.value     = false
        resolve()
      }
    } catch { /* 继续轮询 */ }
    if (attempts >= 90) {
      clearInterval(pollTimer)
      reject(new Error('timeout waiting for result'))
    }
  }, 2000)
}

function closeWS() {
  if (ws) { ws.close(); ws = null }
}

// ── 批量生成刺激图集 ──
const batch = reactive({
  emotions: EMOTIONS.map((e) => e.key),
  perEmotion: 20,
  folder: 'vr_stimulus',
  running: false,
  done: 0,
  total: 0,
  ok: 0,
  fail: 0,
  currentEmotion: '',
})

const batchPct = computed(() =>
  batch.total > 0 ? Math.round((batch.done / batch.total) * 100) : 0,
)
const emoLabel = (key) => emotions.value.find((e) => e.key === key)?.label ?? key

function toggleBatchEmotion(key) {
  if (batch.running) return
  const i = batch.emotions.indexOf(key)
  if (i >= 0) batch.emotions.splice(i, 1)
  else batch.emotions.push(key)
}

let batchStop = false
let batchWs = null

async function startBatch() {
  if (batch.running || batch.emotions.length === 0 || batch.perEmotion < 1) return
  batchStop = false
  batch.running = true
  batch.done = 0; batch.ok = 0; batch.fail = 0
  batch.total = batch.emotions.length * batch.perEmotion
  batch.currentEmotion = ''
  statusMsg.value = ''
  progress.current = 0; progress.max = 0

  const clientId = makeClientId()
  batchWs = openProgressWS(clientId)
  const folder = batch.folder || 'vr_stimulus'

  try {
    for (const emo of batch.emotions) {
      if (batchStop) break
      batch.currentEmotion = emo
      const prefix = `${folder}/${emo}/${emo}`
      for (let i = 0; i < batch.perEmotion; i++) {
        if (batchStop) break
        try {
          const { prompt } = await randomVrStimulus(emo)
          const workflow = await buildWorkflow({ positive: prompt, seedVal: -1, filenamePrefix: prefix })
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
    statusMsg.value      = batchStop ? props.locale.stimulus.batchStopped : props.locale.stimulus.batchDone
    statusMsgClass.value = batchStop ? 'msg-error' : 'msg-ok'
  } finally {
    batch.running = false
    batch.currentEmotion = ''
    if (batchWs) { batchWs.close(); batchWs = null }
  }
}

function stopBatch() { batchStop = true }

// ── 呈现序列（诱导 session 播放器）──
// 按情绪分组轮播已生成的刺激图，每张停留 dwell 秒，用于真实采集时诱导受试者表情
const session = reactive({ playing: false, dwell: 10, index: 0, list: [] })
const sessionCaption = ref('')
let sessionTimer = null

function startSession() {
  if (results.value.length === 0) {
    statusMsg.value = props.locale.stimulus.sessionEmpty
    statusMsgClass.value = 'msg-error'
    return
  }
  // 按 7 类顺序分组排序，形成情绪块序列
  const order = EMOTIONS.map((e) => e.key)
  session.list = [...results.value].sort(
    (a, b) => order.indexOf(a.emotion) - order.indexOf(b.emotion),
  )
  session.index = 0
  session.playing = true
  showSessionFrame()
}

function showSessionFrame() {
  const item = session.list[session.index]
  if (!item) { stopSession(); return }
  panoSrc.value = item.url
  sessionCaption.value = `${item.label}  ·  ${session.index + 1}/${session.list.length}`
  clearTimeout(sessionTimer)
  sessionTimer = setTimeout(() => {
    session.index++
    if (session.index >= session.list.length) stopSession()
    else showSessionFrame()
  }, Math.max(2, session.dwell) * 1000)
}

function stopSession() {
  session.playing = false
  clearTimeout(sessionTimer)
  sessionTimer = null
  sessionCaption.value = ''
  panoSrc.value = null
}

// 关闭查看器：如在序列播放中则一并停止
function closeViewer() {
  if (session.playing) stopSession()
  else panoSrc.value = null
}

// 等待单个 prompt 完成；WS 漏消息时靠 history 轮询兜底
function waitForPrompt(socket, promptId) {
  return new Promise((resolve, reject) => {
    let settled = false
    let poll = null
    function cleanup() {
      socket.removeEventListener('message', onMsg)
      if (poll) clearInterval(poll)
    }
    function finish() {
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
        finish()
      }
      if (type === 'execution_error' && data?.prompt_id === promptId) {
        if (settled) return
        settled = true
        cleanup()
        reject(new Error(data?.exception_message ?? 'execution error'))
      }
    }
    socket.addEventListener('message', onMsg)
    poll = setInterval(async () => {
      try {
        const h = await getHistory(promptId)
        if (h[promptId]?.outputs) finish()
      } catch { /* 继续轮询 */ }
    }, 3000)
  })
}

// ── 生命周期 ──
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
  clearTimeout(sessionTimer)
})
</script>

<style scoped>
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

.header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.panel-title { font-size: 0.92rem; font-weight: 700; color: var(--color-text); }
.server-addr { font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.conn-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 600;
}
.conn-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.conn-ok       { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
.conn-off      { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }
.conn-checking { background: rgba(255, 193, 7, 0.12);  color: #ffc107; }

.icon-btn {
  width: 30px; height: 30px; border-radius: 7px;
  border: 1px solid var(--color-border);
  background: var(--color-surface); color: var(--color-text-muted);
  cursor: pointer; font-size: 0.95rem; line-height: 1;
  transition: all 0.2s;
  display: flex; align-items: center; justify-content: center;
}
.icon-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }

.comfy-body {
  flex: 1; overflow-y: auto;
  padding: 14px 16px 20px;
  display: flex; flex-direction: column; gap: 10px;
}

.panel-desc {
  font-size: 0.75rem; line-height: 1.5;
  color: var(--color-text-muted);
}

.offline-box {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  gap: 10px; padding: 40px 24px; color: var(--color-text-muted);
}
.offline-icon  { font-size: 2rem; }
.offline-title { font-size: 1rem; font-weight: 600; color: var(--color-text); }
.offline-hint  { font-size: 0.8rem; line-height: 1.6; max-width: 300px; }
.btn-retry {
  margin-top: 6px; padding: 8px 22px; border-radius: 20px; border: none;
  background: var(--color-primary); color: #fff;
  font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
}
.btn-retry:hover { opacity: 0.9; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field-label {
  font-size: 0.75rem; font-weight: 600;
  color: var(--color-text-muted); letter-spacing: 0.04em;
}
.field-label-row { display: flex; align-items: center; justify-content: space-between; }

.ctrl-num, .ctrl-textarea {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 8px; color: var(--color-text);
  font-size: 0.82rem; padding: 7px 10px; outline: none;
  transition: border-color 0.2s; width: 100%;
}
.ctrl-textarea:focus, .ctrl-num:focus { border-color: var(--color-primary); }
.ctrl-textarea { resize: vertical; min-height: 56px; line-height: 1.5; font-family: inherit; }
.ctrl-num { width: 120px; text-align: center; -moz-appearance: textfield; }
.ctrl-num::-webkit-inner-spin-button, .ctrl-num::-webkit-outer-spin-button { -webkit-appearance: none; }

.row-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.seed-input { width: 120px; }
.seed-hint { font-size: 0.7rem; color: var(--color-text-muted); font-style: italic; }

.preset-btns { display: flex; gap: 5px; flex-wrap: wrap; }
.preset-btn {
  padding: 4px 10px; border-radius: 6px;
  border: 1px solid var(--color-border); background: transparent;
  color: var(--color-text-muted); font-size: 0.72rem; cursor: pointer;
  transition: all 0.15s;
}
.preset-btn:hover, .preset-btn.active {
  border-color: var(--color-primary); color: var(--color-primary);
  background: rgba(108, 99, 255, 0.1);
}

.use-emotion-btn {
  padding: 3px 9px; border-radius: 6px;
  border: 1px solid var(--color-accent);
  background: rgba(0, 212, 255, 0.08); color: var(--color-accent);
  font-size: 0.7rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.use-emotion-btn:hover { background: rgba(0, 212, 255, 0.18); }

.btn-generate {
  width: 100%; padding: 11px 0; border: none; border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary), #a855f7);
  color: #fff; font-size: 0.9rem; font-weight: 700; cursor: pointer;
  transition: opacity 0.2s, transform 0.1s; letter-spacing: 0.04em; margin-top: 4px;
}
.btn-generate:hover:not(:disabled) { opacity: 0.92; transform: translateY(-1px); }
.btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

.progress-wrap { display: flex; flex-direction: column; gap: 5px; }
.progress-bar { height: 5px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.progress-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
  transition: width 0.3s ease;
}
.progress-node { font-size: 0.7rem; color: var(--color-text-muted); }

.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; }
.msg-ok    { background: rgba(46, 204, 113, 0.12); color: #2ecc71; }
.msg-error { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }

.result-area { display: flex; flex-direction: column; gap: 8px; }
.result-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.result-label { font-size: 0.75rem; font-weight: 600; color: var(--color-text-muted); letter-spacing: 0.04em; }
.result-actions { display: flex; align-items: center; gap: 8px; }
.dwell-label { display: inline-flex; align-items: center; gap: 5px; font-size: 0.7rem; color: var(--color-text-muted); }
.dwell-input {
  width: 52px; text-align: center;
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: 6px; color: var(--color-text); font-size: 0.78rem; padding: 4px 6px;
  -moz-appearance: textfield;
}
.dwell-input::-webkit-inner-spin-button, .dwell-input::-webkit-outer-spin-button { -webkit-appearance: none; }
.clear-btn {
  width: 22px; height: 22px; border-radius: 4px;
  border: 1px solid var(--color-border); background: transparent;
  color: var(--color-text-muted); font-size: 0.7rem; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}
.result-item {
  position: relative; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--color-border);
}
.result-img {
  display: block; width: 100%; aspect-ratio: 2 / 1;
  object-fit: cover; cursor: zoom-in; transition: transform 0.2s;
}
.result-img:hover { transform: scale(1.03); }
.emo-tag {
  position: absolute; top: 5px; left: 5px;
  padding: 2px 8px; border-radius: 10px;
  background: rgba(0, 0, 0, 0.6); color: #fff;
  font-size: 0.68rem; font-weight: 600;
}
.dl-btn {
  position: absolute; bottom: 5px; right: 5px;
  width: 24px; height: 24px; border-radius: 6px;
  background: rgba(0,0,0,0.6); color: #fff; font-size: 0.85rem;
  text-decoration: none; display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.2s;
}
.result-item:hover .dl-btn { opacity: 1; }

/* ── 两列 & 批量 ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.batch-folder { min-height: 0; height: 34px; resize: none; }

.batch-box {
  display: flex; flex-direction: column; gap: 10px;
  margin-top: 6px; padding: 14px;
  border: 1px dashed var(--color-border); border-radius: 10px;
  background: var(--color-surface-2);
}
.batch-title { font-size: 0.85rem; font-weight: 700; color: var(--color-text); }
.batch-desc { font-size: 0.72rem; line-height: 1.5; color: var(--color-text-muted); }
.batch-hint { font-size: 0.7rem; color: var(--color-text-muted); }
.batch-hint code { font-family: ui-monospace, monospace; color: var(--color-accent); }

.btn-stop {
  width: 100%; padding: 11px 0; border: none; border-radius: 10px;
  background: rgba(255, 107, 107, 0.16); color: #ff6b6b;
  font-size: 0.9rem; font-weight: 700; cursor: pointer; transition: opacity 0.2s;
}
.btn-stop:hover { opacity: 0.85; }

.batch-progress { display: flex; flex-direction: column; gap: 5px; }
.batch-stat { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--color-text-muted); }
.batch-stat .cur  { color: var(--color-primary); }
.batch-stat .ok   { color: #2ecc71; margin-left: auto; }
.batch-stat .fail { color: #ff6b6b; }
</style>
