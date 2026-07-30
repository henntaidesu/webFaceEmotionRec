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

    <!-- ── 主体：左配置 / 右头显视角 ── -->
    <div class="comfy-body">
      <!-- 左侧：配置区（滚动） -->
      <div class="config-col">
      <!-- 离线提示：只是一条横幅，不再顶掉整个配置区。
           头显连接 / 刺激种子 / 闭环参数 / 出图参数都不依赖 ComfyUI，离线也要能看能改；
           真正需要 ComfyUI 在线的只有「开始生成图片」，那一颗单独禁用。 -->
      <div v-if="!online" class="offline-bar">
        <span class="offline-icon">⚡</span>
        <div class="offline-text">
          <p class="offline-title">{{ locale.comfyDisconnected }}</p>
          <p class="offline-hint">{{ locale.stimulus.offlineHint }}</p>
        </div>
        <button class="btn-retry" @click="retryConn">{{ locale.comfyRetry }}</button>
      </div>

      <!-- ① 头显连接：外网下服务器连不进头显的 NAT，只能等头显应用自己来报到 -->
      <section class="sec">
        <div class="sec-title">① 头显连接</div>
        <div class="headset-bar">
          <span class="hs-title">🥽 {{ locale.stimulus.hsTitle }}</span>
          <span class="hs-status" :class="headset.online ? 'hs-ok' : 'hs-bad'">{{ headsetText }}</span>
          <button class="hs-btn hs-ghost" :disabled="headset.busy" @click="refreshHeadset">
            {{ locale.stimulus.hsRefresh }}
          </button>
        </div>
      </section>

      <!-- ② 刺激种子：目标情绪 + 场景四要素（组合喂 DeepSeek 动态生成提示词）-->
      <section class="sec">
        <div class="sec-title">② 刺激种子</div>
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
        <div class="field">
          <div class="field-label-row">
            <label class="field-label">{{ locale.stimulus.scene }}</label>
            <button class="use-emotion-btn" @click="randomScene">{{ locale.stimulus.pick }}</button>
          </div>
          <div class="two-col scene-dims">
            <div class="dim-field" v-for="dim in sceneDims" :key="dim.key">
              <label class="dim-label">{{ dimLabel(dim) }}</label>
              <select v-model.number="sel[dim.key]" class="ctrl-select">
                <option v-for="(o, i) in dim.items" :key="i" :value="i">{{ optLabel(o) }}</option>
              </select>
            </div>
          </div>
        </div>
      </section>

      <!-- ③ 闭环参数：DeepSeek 动态提示词 + Quest Pro 目标情绪强度反馈 -->
      <section class="sec">
        <div class="sec-title">③ 闭环参数</div>
        <p class="hs-hint">情绪+场景为种子 → DeepSeek 按实时强度动态生成提示词 → 出图推头显 → 采集情绪变化写库</p>
        <div class="two-col">
          <div class="field">
            <label class="field-label">调制模式</label>
            <select v-model="loopMode" class="ctrl-select">
              <option v-for="m in LOOP_MODES" :key="m.key" :value="m.key">{{ m.zh }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">目标强度（0–1，仅目标带调节用）</label>
            <input type="number" v-model.number="targetIntensity" class="ctrl-num" min="0" max="1" step="0.05" />
          </div>
          <div class="field">
            <label class="field-label">受试者 ID</label>
            <input type="text" v-model="subjectId" class="ctrl-num" />
          </div>
          <div class="field">
            <label class="field-label">观看/测量窗（秒）</label>
            <input type="number" v-model.number="measureWindowSec" class="ctrl-num" min="2" max="60" />
          </div>
        </div>
      </section>

      <!-- ④ 出图参数：设一次即可，默认折叠省空间 -->
      <details class="sec sec-fold">
        <summary class="sec-title">④ 出图参数（{{ gen.width }}×{{ genHeight }} · {{ gen.steps }} steps · CFG {{ gen.cfg }}）</summary>
        <div class="sec-fold-body">
          <div class="field">
            <label class="field-label">{{ locale.stimulus.resolution }}（2:1）</label>
            <div class="preset-btns">
              <button
                v-for="p in RES_PRESETS"
                :key="p"
                class="preset-btn"
                :class="{ active: gen.width === p }"
                @click="gen.width = p"
              >{{ p }}×{{ p / 2 }}</button>
            </div>
            <div class="row-group">
              <input type="number" v-model.number="gen.width" class="ctrl-num seed-input" min="512" max="4096" step="64" @change="normalizeRes" />
              <span class="seed-hint">× {{ genHeight }} {{ locale.stimulus.resHint }}</span>
            </div>
          </div>
          <div class="two-col">
            <div class="field">
              <label class="field-label">{{ locale.stimulus.steps }}</label>
              <input type="number" v-model.number="gen.steps" class="ctrl-num" min="1" max="100" />
            </div>
            <div class="field">
              <label class="field-label">CFG</label>
              <input type="number" v-model.number="gen.cfg" class="ctrl-num" min="0" max="30" step="0.1" />
            </div>
            <div class="field">
              <label class="field-label">{{ locale.stimulus.sampler }}</label>
              <select v-model="gen.sampler" class="ctrl-select">
                <option v-for="s in SAMPLERS" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">{{ locale.stimulus.scheduler }}</label>
              <select v-model="gen.scheduler" class="ctrl-select">
                <option v-for="s in SCHEDULERS" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label class="field-label">{{ locale.stimulus.seed }}</label>
            <div class="row-group">
              <input type="number" v-model.number="seed" class="ctrl-num seed-input" min="-1" />
              <button class="icon-btn" :title="locale.stimulus.randomSeed" @click="seed = -1">🎲</button>
              <span class="seed-hint">{{ seed < 0 ? locale.stimulus.randomSeedHint : '' }}</span>
            </div>
          </div>
          <div class="field">
            <label class="field-label">{{ locale.stimulus.negative }}</label>
            <textarea v-model="negative" class="ctrl-textarea" rows="2" />
          </div>
        </div>
      </details>

      <!-- 开始闭环 + 查看历史图片（同一行）-->
      <div class="action-row">
        <button
          class="btn-generate"
          :class="{ 'btn-stop': loopRunning }"
          :disabled="!loopRunning && !online"
          :title="online ? '' : locale.stimulus.offlineHint"
          @click="toggleLoop"
        >{{ loopRunning ? '■ 停止生成' : '▶ 开始生成图片' }}</button>
        <button
          class="btn-random"
          :disabled="loopRunning || !online"
          :title="online ? '随机情绪 + 随机场景四要素，然后开始生成' : locale.stimulus.offlineHint"
          @click="randomGenerate"
        >🎲 随机生成图片</button>
        <button class="btn-history" @click="openHistory">🕑 {{ locale.stimulus.historyBtn }}</button>
      </div>

      <!-- ⑤ 闭环运行状态：指标 / 强度曲线 / 当前提示词 / 最新一张 -->
      <section class="sec">
        <div class="sec-title">⑤ 运行状态</div>
        <div class="loop-meta">
          <span>目标：{{ curEmotionObj?.zh }}</span>
          <span>实时强度：{{ (latestIntensity * 100).toFixed(0) }}%</span>
          <span>已生成：{{ loopStep }} 张</span>
          <span>同步：{{ syncText }}</span>
          <span :class="{ 'meta-bad': loopRunning && capture.rows === 0 }">采集：{{ capture.rows }} 帧</span>
        </div>
        <p v-if="loopRunning && capture.rows === 0" class="status-msg msg-error">
          正在生成，但**一帧 FEA 都没入库** —— 头显没在推数据。检查：头显里应用是否打开、Quest Pro 面部追踪权限是否开启。这样采下去只会得到空会话。
        </p>
        <svg class="intensity-curve" viewBox="0 0 280 60" preserveAspectRatio="none">
          <line x1="0" :y1="60 - targetIntensity * 60" x2="280" :y2="60 - targetIntensity * 60" class="target-line" />
          <polyline v-if="curvePath" :points="curvePath" class="curve-line" />
        </svg>
        <div v-if="loopRunning && progress.max > 0" class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
          </div>
          <span class="progress-node">{{ progress.current }}/{{ progress.max }}</span>
        </div>
        <p v-if="loopStatus" class="hs-hint loop-status">{{ loopStatus }}</p>
        <p v-if="pushWarn" class="status-msg msg-error">{{ pushWarn }}</p>
        <p v-if="dbWarn" class="status-msg msg-error">{{ dbWarn }}</p>
        <p v-if="statusMsg" class="status-msg" :class="statusMsgClass">{{ statusMsg }}</p>
        <textarea v-model="currentPrompt" class="ctrl-textarea" rows="3" readonly
                  :placeholder="'当前提示词由 DeepSeek 按情绪+场景动态生成（开始闭环后显示）'" />
        <div v-if="results.length > 0" class="result-area">
          <div class="result-header">
            <span class="result-label">{{ locale.stimulus.result }}（{{ results.length }}）</span>
            <div class="result-actions">
              <label class="dwell-label">
                {{ locale.stimulus.dwell }}
                <input type="number" v-model.number="session.dwell" class="dwell-input" min="2" max="60" />
              </label>
              <button class="use-emotion-btn" @click="startSession()">{{ locale.stimulus.sessionStart }}</button>
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
      </section>
      </div>

      <!-- 右侧：头显视角（一直显示，不折叠） -->
      <div class="view-col">
        <div class="view-col-title">{{ locale.stimulus.hsViewTitle }}</div>
        <div class="hs-view-box">
          <!-- 画面由头显 WebRTC 直推到本浏览器，不经过后端 -->
          <video
            v-show="headsetViewLive"
            ref="headsetVideo"
            class="hs-view-img"
            autoplay
            muted
            playsinline
          ></video>
          <span v-if="!headsetViewLive" class="hs-view-waiting">{{ headsetViewHint }}</span>
        </div>
      </div>
    </div>

    <!-- 历史图片弹窗（从磁盘 image/ 按需读取）-->
    <div v-if="history.open" class="history-overlay" @click.self="closeHistory">
      <div class="history-modal">
        <div class="history-head">
          <span class="history-title">{{ locale.stimulus.historyTitle }}（{{ history.images.length }}）</span>
          <div class="history-actions">
            <button class="icon-btn" :title="locale.comfyRetry" @click="loadHistory">↻</button>
            <button class="icon-btn" title="✕" @click="closeHistory">✕</button>
          </div>
        </div>

        <div class="history-filters">
          <button
            class="preset-btn"
            :class="{ active: history.filter === '' }"
            @click="setHistoryFilter('')"
          >{{ locale.stimulus.historyAll }}</button>
          <button
            v-for="e in emotions"
            :key="e.key"
            class="preset-btn"
            :class="{ active: history.filter === e.key }"
            @click="setHistoryFilter(e.key)"
          >{{ e.label }}</button>
        </div>

        <div class="history-body">
          <p v-if="history.loading" class="history-empty">…</p>
          <p v-else-if="history.images.length === 0" class="history-empty">{{ locale.stimulus.historyEmpty }}</p>
          <div v-else class="result-grid">
            <div v-for="img in history.images" :key="img.path" class="result-item">
              <img :src="img.url" class="result-img" :title="locale.stimulus.fullscreen" @click="panoSrc = img.url" />
              <span class="emo-tag">{{ emoLabel(img.emotion) }}</span>
              <a :href="img.url" :download="img.filename" class="dl-btn" :title="locale.stimulus.download">↓</a>
              <button class="del-btn" :title="locale.stimulus.historyDelete" @click="deleteHistoryImage(img.path)">🗑</button>
            </div>
          </div>
        </div>

        <div v-if="history.images.length > 0" class="history-foot">
          <button
            v-if="history.filter"
            class="clear-emo-btn"
            @click="clearHistoryEmotion"
          >🗑 {{ locale.stimulus.historyClear }}</button>
          <label class="dwell-label">
            {{ locale.stimulus.dwell }}
            <input type="number" v-model.number="session.dwell" class="dwell-input" min="2" max="60" />
          </label>
          <button class="use-emotion-btn" @click="playHistory">▶ {{ locale.stimulus.sessionStart }}</button>
        </div>
      </div>
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
import { ref, computed, reactive, watch, nextTick, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import {
  checkOnline,
  fetchWorkflow,
  fetchObjectInfo,
  uiToApiFormat,
  applyPromptOverrides,
  applyGenParams,
  queuePrompt,
  getHistory,
  imageUrl,
  makeClientId,
  openProgressWS,
  SAMPLERS,
  SCHEDULERS,
  COMFYUI_HOST,
} from '../api/comfyuiApi.js'
import { saveStimulusImage, reportStimulusProgress } from '../api/vrStimulus.js'
import { getHeadsetPresence } from '../api/headset.js'
import { createHeadsetViewLink } from '../api/headsetRtc.js'
import { fetchFeaLatest, startSession as startAffectSession, stopSession as stopAffectSession, recordImage, generateScenePrompt } from '../api/affect.js'
// 懒加载：three.js 仅在打开 360 查看器时才按需加载，保持首屏包体积
const PanoramaViewer = defineAsyncComponent(() => import('./PanoramaViewer.vue'))

const props = defineProps({
  locale: { type: Object, required: true },
})

// 复用已放入 ComfyUI 工作流目录的 360 全景工作流
const STIMULUS_WORKFLOW = 'qwen360_pano.json'
// 提示词由 DeepSeek 生成（其 system prompt 已要求以 "equirectangular 360 panorama," 开头）
const DEFAULT_NEG =
  'lowres, worst quality, blurry, distorted, polar distortion, poles warping, watermark, text, people, person, human'

// 7 类情绪（诱导目标）——具体场景改由下方「时间/地点/任务/事情」四要素组合，不再逐情绪预置
const EMOTIONS = [
  { key: 'happy', zh: '开心' },
  { key: 'sad', zh: '悲伤' },
  { key: 'angry', zh: '愤怒' },
  { key: 'surprise', zh: '惊讶' },
  { key: 'fear', zh: '恐惧' },
  { key: 'disgust', zh: '厌恶' },
  { key: 'neutral', zh: '平静' },
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

// ── 生成参数（默认取自 qwen360_pano 工作流）──
const gen = reactive({
  width: 2048,        // 高度恒为 width/2（强制 2:1 等距全景）
  steps: 15,
  cfg: 3.5,
  sampler: 'euler',
  scheduler: 'simple',
})
// 2:1 分辨率预设（宽度）
const RES_PRESETS = [1024, 1536, 2048, 2560, 3072]
const genHeight = computed(() => Math.round(gen.width / 2))
// 宽度归一化：钳制到 [512,4096] 并取 16 的倍数，保证 height=width/2 为 8 的倍数
function normalizeRes() {
  let w = Number(gen.width) || 2048
  w = Math.min(4096, Math.max(512, Math.round(w / 16) * 16))
  gen.width = w
}

const emotions = computed(() =>
  EMOTIONS.map((e) => ({ ...e, label: props.locale.emotionMap[e.zh] ?? e.zh })),
)
const curEmotionObj = computed(() => EMOTIONS.find((e) => e.key === selectedEmotion.value))

// 当前页语言：zh.js 的 langSwitchPath=/jp、ja.js 的=/cn
const lang = computed(() => (props.locale.langSwitchPath === '/cn' ? 'ja' : 'zh'))
const optLabel = (s) => (s ? (s[lang.value] || s.zh) : '')

// ── 场景四要素（「刺激种子」：时间/地点/任务/事情）──
// 预设表由后端 /api/stimulus/options 提供（backend/src/use_web/stimulus_control.py），
// 头显里的 VR 控制台读的是同一份，避免网页与 VR 各存一份导致选项漂移。
const sceneDims = ref([])          // [{ key, zh, ja, en, items: [{zh,ja,en}] }]
const dimLabel = (dim) => (lang.value === 'ja' ? dim.ja : dim.zh)
const sel = reactive({ time: 0, place: 0, task: 0, event: 0 })

const dimByKey = (key) => sceneDims.value.find((d) => d.key === key)
// 四要素组合成基础场景文本（当前语言），喂给 DeepSeek 生成提示词
const composedScene = () =>
  ['time', 'place', 'task', 'event']
    .map((k) => {
      const d = dimByKey(k)
      return d ? optLabel(d.items[sel[k]]) : ''
    })
    .filter(Boolean).join('，')

function selectEmotion(key) { selectedEmotion.value = key }
function randomScene() {
  for (const k of ['time', 'place', 'task', 'event']) {
    const d = dimByKey(k)
    if (d && d.items.length) sel[k] = Math.floor(Math.random() * d.items.length)
  }
}
// 整套刺激种子随机：目标情绪 + 场景四要素。
// 情绪从 emotions（后端选项表）里抽，不写死列表，加类别时不用改这里。
function randomizeSeed() {
  const list = emotions.value
  if (list.length) selectedEmotion.value = list[Math.floor(Math.random() * list.length)].key
  randomScene()
}

// ── 动态情绪闭环采集（DeepSeek 动态提示词 + Quest Pro 目标情绪强度反馈）──
const LOOP_MODES = [
  { key: 'amplify', zh: '递进强化' },
  { key: 'titrate', zh: '目标带调节' },
  { key: 'dose', zh: '剂量阶梯' },
  { key: 'random', zh: '随机' },
]
const loopMode = ref('amplify')
const targetIntensity = ref(0.6)
const subjectId = ref('anon')
const measureWindowSec = ref(6)
const loopRunning = ref(false)
const loopStep = ref(0)
const loopStatus = ref('')
const dbWarn = ref('')                 // 入库失败提示（闭环照跑，但要提示）
// 推送头显失败提示。这一步（/api/stimulus/save show=true）是头显能看到新图的**唯一**途径：
// 它失败后端就不会把图标记为「当前」，version 不涨，头显永远停在上一张。
// 以前这里是 catch {} 静默吞掉的，表现成「网页有图、头显不动」且毫无线索——必须让人看见。
const pushWarn = ref('')
const loopSessionId = ref('')
const latestIntensity = ref(0)
// 本次采集真正入库的 FEA 帧数（后端随 /api/fea/latest 一起返回）。
// 之前 37 个会话一帧没采到却毫无提示，一周后查库才发现——这个计数就是防这个的。
const capture = reactive({ rows: 0, lastMs: null })
const intensitySeries = reactive([])   // 目标情绪强度随时间的曲线点 [{ v }]
let latestFeaData = null
let feaTimer = null
let loopAbort = false

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── 与头显共享的控制状态（后端 /api/stimulus/control）────────────────
// 网页与 VR 控制台读改同一份参数：这边改了头显能看到，头显改了这边也会跟着变。
// 出图始终跑在本页（DeepSeek + ComfyUI 都在浏览器里），头显只是把 running 置真/假，
// 所以本页必须开着，头显按开始才会真的出图。
const ctlVersion = ref(-1)
const ctlSource = ref('')
let applyingRemote = false     // 正在把远端状态写进本地 ref，期间不要回推，避免来回打架
let ctlTimer = null

async function pushControl(patch) {
  try {
    const res = await fetch('/api/stimulus/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...patch, source: 'web' }),
    })
    const data = await res.json()
    if (typeof data?.version === 'number') ctlVersion.value = data.version
  } catch { /* 后端不通时本地照常操作，下次轮询再对齐 */ }
}

// 本地控件改动 → 推给后端（applyingRemote 期间跳过）
function watchAndPush(getter, key) {
  watch(getter, (v) => { if (!applyingRemote) pushControl({ [key]: v }) })
}
// 头显跟随网页的语言：/cn 页面 → 头显中文，/jp 页面 → 头显日语。
// 受试者面对的是同一套实验，两端语言不一致会让指导语和选项对不上。
watch(lang, (v) => pushControl({ lang: v }), { immediate: true })
watchAndPush(() => selectedEmotion.value, 'emotion')
watchAndPush(() => loopMode.value, 'mode')
watchAndPush(() => Number(targetIntensity.value), 'target_intensity')
watchAndPush(() => Number(measureWindowSec.value), 'measure_window_s')
watchAndPush(() => subjectId.value, 'subject_id')
watchAndPush(() => Number(seed.value), 'seed')   // 漏过：seed 在共享状态里，两边都要跟
watch(() => ({ ...sel }), (v) => { if (!applyingRemote) pushControl({ scene: v }) }, { deep: true })

// 远端状态 → 本地控件
function applyControl(c) {
  applyingRemote = true
  if (c.emotion) selectedEmotion.value = c.emotion
  if (c.mode) loopMode.value = c.mode
  if (typeof c.target_intensity === 'number') targetIntensity.value = c.target_intensity
  if (typeof c.measure_window_s === 'number') measureWindowSec.value = c.measure_window_s
  if (c.subject_id) subjectId.value = c.subject_id
  if (typeof c.seed === 'number') seed.value = c.seed
  if (c.scene) for (const k of ['time', 'place', 'task', 'event']) {
    if (typeof c.scene[k] === 'number') sel[k] = c.scene[k]
  }
  ctlSource.value = c.source || ''
  // 放到微任务之后再解锁，确保上面这些赋值触发的 watch 都已跳过
  nextTick(() => { applyingRemote = false })
}

// 同步指示：最后一次改动来自哪一边 + 版本号。没有它就算两边真同步了也看不出来，
// 「头显改了网页没反应」和「同步了但我没注意」分不开。
const syncText = computed(() => {
  if (ctlVersion.value < 0) return '—'
  const who = ctlSource.value === 'vr' ? '头显' : ctlSource.value === 'web' ? '网页' : '初始'
  return `${who} · v${ctlVersion.value}`
})

async function pollControl() {
  try {
    const res = await fetch('/api/stimulus/control')
    const c = await res.json()
    if (typeof c?.version !== 'number') return
    if (c.version !== ctlVersion.value) {
      ctlVersion.value = c.version
      applyControl(c)
    }
    // 头显按了开始/结束 → 这边跟着启停真正的生成闭环
    if (c.running && !loopRunning.value) startLoop({ fromRemote: true })
    else if (!c.running && loopRunning.value) stopLoop({ fromRemote: true })
  } catch { /* 忽略单次失败 */ }
}

// 从最近一帧 FEA 取「当前所选目标情绪」的分数（归一化到 0–1）
function targetScore(data) {
  if (!data?.success || !data.faces?.length) return null
  const em = data.faces[0].emotions || {}
  const raw = em[curEmotionObj.value?.zh]
  if (typeof raw !== 'number') return null
  return raw > 1 ? raw / 100 : raw
}
// 7 类情绪情境向量（英文键，供 pgvector context 存储）
function emotionsEnFromLatest() {
  const em = latestFeaData?.faces?.[0]?.emotions || {}
  const out = {}
  for (const e of EMOTIONS) {
    const raw = em[e.zh]
    out[e.key] = typeof raw === 'number' ? (raw > 1 ? raw / 100 : raw) : 0
  }
  return out
}

// 按调制模式 + 实时强度算出给 DeepSeek 的「强度指令」
function computeDirective(step, measured) {
  const emo = selectedEmotion.value
  const T = Number(targetIntensity.value) || 0.6
  let level, directive
  if (loopMode.value === 'amplify') {
    level = Math.min(5, 1 + step)
    directive = `intensify strongly toward peak ${emo}; render at intensity level ${level}/5, stronger and more extreme than the previous image`
  } else if (loopMode.value === 'titrate') {
    const m = measured ?? 0
    let dir
    if (m < T - 0.1) { level = Math.min(5, Math.round(T * 5) + 1); dir = 'increase' }
    else if (m > T + 0.1) { level = Math.max(1, Math.round(T * 5) - 1); dir = 'reduce' }
    else { level = Math.max(1, Math.round(T * 5)); dir = 'hold' }
    directive = `the viewer's current ${emo} intensity is ${m.toFixed(2)}, target is ${T.toFixed(2)}; ${dir} the emotional intensity toward the target, render at level ${level}/5`
  } else if (loopMode.value === 'dose') {
    level = 1 + (step % 5)
    directive = `dose-response ladder: render ${emo} at a fixed dose level ${level}/5`
  } else {
    level = 1 + Math.floor(Math.random() * 5)
    randomScene()   // 随机模式：随机换四要素组合
    directive = `render ${emo} at a random intensity level ${level}/5`
  }
  return { directive, level, sceneText: composedScene() }
}

// 把「下一张」的生成进度同步给后端，头显 UI 轮询后显示进度条
function pushProgress(running, note) {
  reportStimulusProgress({
    running,
    current: running ? progress.current : 0,
    max: running ? progress.max : 0,
    step: loopStep.value + 1,
    note,
  })
}

// 精简版单张生成：返回图片 URL（复用工作流/WS/history 兜底），不改动单张生成状态
function genImageUrl(positive, negativeText) {
  return new Promise((resolve, reject) => {
    let settled = false, sock = null, pollId = null
    const done = async (pid) => {
      if (settled) return; settled = true
      if (pollId) clearInterval(pollId)
      try { const urls = await collectImages(pid); resolve(urls[0] || '') }
      catch (e) { reject(e) }
      finally { if (sock) sock.close() }
    }
    ;(async () => {
      try {
        const clientId = makeClientId()
        const workflow = await buildWorkflow({ positive, negativeText, seedVal: -1 })
        sock = openProgressWS(clientId)
        const { prompt_id } = await queuePrompt(clientId, workflow)
        sock.addEventListener('message', (e) => {
          let m; try { m = JSON.parse(e.data) } catch { return }
          const { type, data } = m
          if (type === 'progress' && data?.prompt_id === prompt_id) {
            progress.current = data.value; progress.max = data.max
            pushProgress(true, 'sampling')     // 同步给头显里的进度条
          }
          if ((type === 'execution_success' && data?.prompt_id === prompt_id) ||
              (type === 'executing' && data?.node === null && data?.prompt_id === prompt_id)) done(prompt_id)
          if (type === 'execution_error' && data?.prompt_id === prompt_id && !settled) {
            settled = true; if (sock) sock.close(); reject(new Error(data?.exception_message || 'execution error'))
          }
        })
        sock.addEventListener('close', () => {
          if (settled) return
          let n = 0
          pollId = setInterval(async () => {
            if (settled) return
            if (++n > 200) { settled = true; clearInterval(pollId); reject(new Error('轮询超时：ComfyUI 未返回结果')); return }
            try { const h = await getHistory(prompt_id); if (h[prompt_id]?.outputs) done(prompt_id) } catch { /* 继续 */ }
          }, 3000)
        })
      } catch (e) { if (!settled) { settled = true; reject(e) } }
    })()
  })
}

async function pollFeaOnce() {
  try {
    const data = await fetchFeaLatest()
    latestFeaData = data
    if (data?.capture) {
      capture.rows = data.capture.rows || 0
      capture.lastMs = data.capture.last_ms || null
    }
    const v = targetScore(data)
    if (v != null) {
      latestIntensity.value = v
      intensitySeries.push({ v })
      if (intensitySeries.length > 120) intensitySeries.shift()
    }
  } catch { /* 忽略单次失败 */ }
}

async function runLoop() {
  let fails = 0                       // 连续失败计数：偶发抖动跳过重试，连续 3 次才停
  while (!loopAbort) {
    const measured = latestIntensity.value
    const { directive, level, sceneText } = computeDirective(loopStep.value, measured)
    loopStatus.value = `生成中…（第 ${loopStep.value + 1} 张 · level ${level}/5）`
    progress.current = 0
    progress.max = 0
    pushProgress(true, 'prompt')          // 提示词阶段：头显显示「准备中」
    let prompt, url
    try {
      prompt = await generateScenePrompt(selectedEmotion.value, sceneText, directive)
      if (loopAbort) break
      url = await genImageUrl(prompt.positive, prompt.negative || DEFAULT_NEG)
    } catch (e) {
      if (++fails >= 3) { loopStatus.value = `连续失败 ${fails} 次，已停止：${e.message}`; break }
      loopStatus.value = `第 ${fails} 次失败（${e.message}），2s 后重试…`
      await sleep(2000)
      continue
    }
    if (loopAbort || !url) break
    fails = 0
    currentPrompt.value = prompt.positive
    results.value = [{ url, emotion: selectedEmotion.value, label: curEmotionObj.value?.zh }]
    // 存盘 + 推头显天空盒
    let savedUrl = url
    let savedPath = ''                      // 磁盘相对路径 image/<emotion>/<时间戳>.png，入库用
    try {
      const s = await saveStimulusImage(url, selectedEmotion.value, 'stimulus', { show: true })
      if (s.path) {
        savedPath = s.path.replace(/\\/g, '/')
        savedUrl = `/api/stimulus/files/${savedPath.replace(/^image\//, '')}`
      }
      pushWarn.value = ''
    } catch (e) {
      pushWarn.value = `第 ${loopStep.value + 1} 张推送头显失败：${e.message}（头显会停在上一张）`
    }
    // 记录刺激事件（含调制元数据，供后期预测分析）
    try {
      await recordImage({
        session_id: loopSessionId.value,
        ts_ms: Date.now(),
        dominant: selectedEmotion.value,
        emotions: emotionsEnFromLatest(),
        prompt: prompt.positive, negative: prompt.negative, scene: prompt.scene, reasoning: prompt.reasoning,
        image_url: savedUrl,
        image_path: savedPath,
        reaction: {
          mode: loopMode.value, level,
          target_intensity: Number(targetIntensity.value) || 0.6,
          measured_intensity: measured, step: loopStep.value, page: 'stimulus',
        },
      })
      dbWarn.value = ''
    } catch (e) {
      dbWarn.value = `第 ${loopStep.value + 1} 张入库失败：${e.message}`   // 不中断闭环，但要让人看见
    }
    loopStep.value++
    loopStatus.value = `已展示第 ${loopStep.value} 张（level ${level}/5）· 采集情绪反应中…`
    pushProgress(false, 'watching')       // 观看窗内头显不显示进度条
    // 观看/测量窗：让 FEA 在当前图上累积后再生成下一张
    await sleep(Math.max(2, Number(measureWindowSec.value) || 6) * 1000)
  }
  loopRunning.value = false
  pushProgress(false, 'idle')             // 循环退出（含出错退出）也要清掉头显进度条
  // 必须同步清掉共享状态里的 running：否则连续失败自行退出后，后端仍是 running=true，
  // 下一次轮询会判定「该跑但没跑」而反复重启，变成死循环。
  pushControl({ running: false })
}

// fromRemote=true 表示由头显按下开始触发，此时不要再把 running 推回后端（避免回环）
async function startLoop({ fromRemote = false } = {}) {
  if (loopRunning.value) return
  if (!online.value) {
    loopStatus.value = 'ComfyUI 未连接'
    if (fromRemote) pushControl({ running: false })   // 头显那边要能看到没起来
    return
  }
  loopStatus.value = ''
  dbWarn.value = ''
  pushWarn.value = ''
  try {
    const r = await startAffectSession(subjectId.value || 'anon', {
      page: 'stimulus', mode: loopMode.value,
      target_emotion: selectedEmotion.value,
      target_intensity: Number(targetIntensity.value) || 0.6,
    })
    loopSessionId.value = r.session_id
  } catch (e) {
    loopStatus.value = `会话建立失败：${e.message}`
    if (fromRemote) pushControl({ running: false })
    return
  }
  loopRunning.value = true
  loopAbort = false
  loopStep.value = 0
  intensitySeries.length = 0
  feaTimer = setInterval(pollFeaOnce, 1000)
  if (!fromRemote) pushControl({ running: true })
  runLoop()
}

function toggleLoop() {
  if (loopRunning.value) stopLoop()
  else startLoop()
}

// 随机生成：整套种子换掉再走正常生成流程。
// 先 await nextTick，让 selectedEmotion / sel 的 watch 把新种子推给后端（头显跟着变），
// 再开始生成——否则头显那边可能还停在上一组参数上。
async function randomGenerate() {
  if (loopRunning.value) return
  randomizeSeed()
  await nextTick()
  startLoop()
}

function stopLoop({ fromRemote = false } = {}) {
  loopAbort = true
  loopRunning.value = false
  if (feaTimer) { clearInterval(feaTimer); feaTimer = null }
  if (loopSessionId.value) { stopAffectSession(loopSessionId.value).catch(() => {}); loopSessionId.value = '' }
  loopStatus.value = (loopStatus.value || '') + (fromRemote ? ' — 已由头显停止' : ' — 已停止')
  pushProgress(false, 'stopped')
  if (!fromRemote) pushControl({ running: false })
}

// 情绪强度曲线（内联 SVG polyline，0–1 → 60px 高）
const curvePath = computed(() => {
  const s = intensitySeries
  if (s.length < 2) return ''
  const W = 280, H = 60
  return s.map((p, i) => {
    const x = (i / (s.length - 1)) * W
    const y = H - Math.max(0, Math.min(1, p.v)) * H
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

onUnmounted(() => {
  loopAbort = true
  if (feaTimer) { clearInterval(feaTimer); feaTimer = null }
  if (loopSessionId.value) stopAffectSession(loopSessionId.value).catch(() => {})
})

// ── 生成流程（仅闭环使用）──
const progress   = reactive({ current: 0, max: 0 })
const statusMsg  = ref('')
const statusMsgClass = ref('')
const results    = ref([]) // { url, emotion, label }
const panoSrc    = ref(null)

// ── 头显在线状态（心跳）──
// 外网下头显连的是笔记本的 WiFi，和笔记本一起在别人家的 NAT 后面，服务器主动连不进来，
// 所以没有「连接头显」这个动作可做——只能等头显应用自己来报到。它每秒 GET 一次
// /api/stimulus/control?client=vr，后端记时间戳，这里轮询读回来。
const headset = reactive({ busy: false, online: false, ageS: null, msg: '' })
let headsetTimer = null

const headsetText = computed(() => {
  const L = props.locale.stimulus
  if (headset.msg) return headset.msg
  if (!headset.online) return L.hsOffline
  return L.hsOnline + (headset.ageS != null ? ` · ${headset.ageS}s` : '')
})

async function refreshHeadset() {
  headset.busy = true
  try {
    const p = await getHeadsetPresence()
    headset.online = !!p.online
    headset.ageS = p.age_s
    headset.msg = ''
  } catch (e) {
    headset.msg = e.message
    headset.online = false
  } finally {
    headset.busy = false
  }
}

// ── 头显用户视角预览（WebRTC 点对点，画面不经后端）─────────────────
// 不依赖 headset.ok：那是 USB/adb 的状态，而外网场景下头显本来就不走数据线。
const headsetVideo = ref(null)
const headsetViewState = ref('idle')      // idle|waiting|connecting|live|failed
const headsetViewLive = computed(() => headsetViewState.value === 'live')
const headsetViewHint = computed(() =>
  headsetViewState.value === 'connecting' ? props.locale.stimulus.hsViewConnecting
    : headsetViewState.value === 'failed' ? props.locale.stimulus.hsViewFailed
      : props.locale.stimulus.hsViewWaiting,
)

const headsetLink = createHeadsetViewLink({
  onStream(stream) {
    if (headsetVideo.value) headsetVideo.value.srcObject = stream
  },
  onState(s) { headsetViewState.value = s },
})

onUnmounted(() => {
  headsetLink.stop()
})

const progressPct = computed(() =>
  progress.max > 0 ? Math.round((progress.current / progress.max) * 100) : 0,
)

async function buildWorkflow({ positive, seedVal, negativeText } = {}) {
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
    negative: negativeText ?? negative.value,
    seed: seedVal ?? seed.value,
  })
  api = applyGenParams(api, {
    width: gen.width,
    height: genHeight.value,
    steps: gen.steps,
    cfg: gen.cfg,
    sampler: gen.sampler,
    scheduler: gen.scheduler,
  })
  return api
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

const emoLabel = (key) => emotions.value.find((e) => e.key === key)?.label ?? key

// ── 呈现序列（诱导 session 播放器）──
// 按情绪分组轮播已生成的刺激图，每张停留 dwell 秒，用于真实采集时诱导受试者表情
const session = reactive({ playing: false, dwell: 10, index: 0, list: [] })
const sessionCaption = ref('')
let sessionTimer = null

function startSession(list) {
  const src = Array.isArray(list) && list.length ? list : results.value
  if (src.length === 0) {
    statusMsg.value = props.locale.stimulus.sessionEmpty
    statusMsgClass.value = 'msg-error'
    return
  }
  // 按 7 类顺序分组排序，形成情绪块序列
  const order = EMOTIONS.map((e) => e.key)
  session.list = [...src].sort(
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
  sessionCaption.value = `${emoLabel(item.emotion)}  ·  ${session.index + 1}/${session.list.length}`
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

// ── 历史图片（从磁盘 image/ 读取，按需查看，不常驻页面）──
const history = reactive({ open: false, loading: false, filter: '', images: [] })

async function loadHistory() {
  history.loading = true
  try {
    const qs = history.filter ? `?emotion=${encodeURIComponent(history.filter)}` : ''
    const res = await fetch(`/api/stimulus/images${qs}`)
    const data = await res.json()
    history.images = Array.isArray(data.images) ? data.images : []
  } catch {
    history.images = []
  } finally {
    history.loading = false
  }
}
function openHistory() { history.open = true; loadHistory() }
function closeHistory() { history.open = false }
function setHistoryFilter(key) { history.filter = key; loadHistory() }
function playHistory() {
  if (history.images.length === 0) return
  closeHistory()
  startSession(history.images)
}
async function deleteHistoryImage(path) {
  try {
    await fetch(`/api/stimulus/images?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
    history.images = history.images.filter((i) => i.path !== path)
  } catch { /* 忽略：下次刷新即一致 */ }
}
async function clearHistoryEmotion() {
  if (!history.filter) return
  if (!window.confirm(props.locale.stimulus.historyClearConfirm)) return
  try {
    await fetch(`/api/stimulus/images?emotion=${encodeURIComponent(history.filter)}`, { method: 'DELETE' })
    await loadHistory()
  } catch { /* 忽略 */ }
}


// 场景四要素预设：与 VR 控制台共用后端那一份
async function loadStimulusOptions() {
  try {
    const res = await fetch('/api/stimulus/options')
    const data = await res.json()
    if (Array.isArray(data?.scene_dims) && data.scene_dims.length) {
      sceneDims.value = data.scene_dims
      return true
    }
  } catch { /* 后端还没起来 */ }
  return false
}

// ── 生命周期 ──
let connTimer = null
let optionsTimer = null
onMounted(async () => {
  retryConn()
  connTimer = setInterval(retryConn, 20_000)
  refreshHeadset()
  // 心跳超时 5s，3s 一轮足够及时反映头显掉线
  headsetTimer = setInterval(refreshHeadset, 3000)
  headsetLink.start()
  // 后端还没起来时选项拉不到。以前拉不到就空着且永不重试，「场景四要素」会一直缺
  // 到手动刷新页面——后端重启是常事，这里必须自愈（头显那侧早就是重试的）。
  if (!await loadStimulusOptions()) {
    optionsTimer = setInterval(async () => {
      if (await loadStimulusOptions()) { clearInterval(optionsTimer); optionsTimer = null }
    }, 3000)
  }
  await pollControl()                          // 先对齐一次，再开始定期同步
  ctlTimer = setInterval(pollControl, 1500)
})
onUnmounted(() => {
  clearInterval(connTimer)
  clearTimeout(sessionTimer)
  if (ctlTimer) { clearInterval(ctlTimer); ctlTimer = null }
  if (headsetTimer) { clearInterval(headsetTimer); headsetTimer = null }
  if (optionsTimer) { clearInterval(optionsTimer); optionsTimer = null }
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
.icon-btn:hover { border-color: #2563eb; color: #2563eb; }

.comfy-body {
  flex: 1; min-height: 0; overflow: hidden;
  display: flex; align-items: stretch;
}

/* 左侧配置区：独立滚动 */
.config-col {
  flex: 1 1 0; min-width: 0;
  overflow-y: auto;
  padding: 14px 16px 20px;
  display: flex; flex-direction: column; gap: 10px;
}

/* 右侧头显视角：常驻，一直显示 */
.view-col {
  flex: 1 1 0; min-width: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface-2);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto;
}
.view-col-title { font-size: 0.82rem; font-weight: 700; color: var(--color-text); letter-spacing: 0.04em; }

/* ── 左栏分区：每步一个卡片，标题带序号 ── */
.sec {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface-2);
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.sec-title {
  font-size: 0.78rem; font-weight: 700;
  color: var(--color-text); letter-spacing: 0.04em;
}
.sec-fold { gap: 0; }
.sec-fold > summary { cursor: pointer; list-style: none; }
.sec-fold > summary::-webkit-details-marker { display: none; }
.sec-fold > summary::before { content: '▸ '; color: var(--color-text-muted); }
.sec-fold[open] > summary::before { content: '▾ '; }
.sec-fold-body { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }

.offline-bar {
  flex: none; display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-radius: 8px;
  border: 1px solid rgba(240, 160, 160, 0.35);
  background: rgba(240, 160, 160, 0.08);
  color: var(--color-text-muted);
}
.offline-icon  { font-size: 1.3rem; }
.offline-text  { flex: 1; min-width: 0; }
.offline-title { font-size: 0.85rem; font-weight: 600; color: var(--color-text); }
.offline-hint  { font-size: 0.75rem; line-height: 1.5; }
.btn-retry {
  flex: none; padding: 7px 16px; border-radius: 20px; border: none;
  background: #2563eb; color: #fff;
  font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
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

.ctrl-select {
  width: 100%;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 8px; color: var(--color-text);
  font-size: 0.82rem; padding: 7px 10px; outline: none;
  cursor: pointer; transition: border-color 0.2s;
}
.ctrl-select:focus { border-color: var(--color-primary); }

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
  border-color: #2563eb; color: #2563eb;
  background: rgba(37, 99, 235, 0.1);
}

.use-emotion-btn {
  padding: 3px 9px; border-radius: 6px;
  border: 1px solid #2563eb;
  background: rgba(37, 99, 235, 0.08); color: #2563eb;
  font-size: 0.7rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.use-emotion-btn:hover { background: rgba(37, 99, 235, 0.18); }

.btn-generate {
  width: 100%; padding: 11px 0; border: none; border-radius: 10px;
  background: #2563eb;
  color: #fff; font-size: 0.9rem; font-weight: 700; cursor: pointer;
  transition: opacity 0.2s, transform 0.1s; letter-spacing: 0.04em; margin-top: 4px;
}
.btn-generate:hover:not(:disabled) { opacity: 0.92; transform: translateY(-1px); }
.btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

.progress-wrap { display: flex; flex-direction: column; gap: 5px; }
.progress-bar { height: 5px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.progress-fill {
  height: 100%; border-radius: 3px;
  background: #2563eb;
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

/* ── 生成 + 查看历史 一行 ── */
.action-row { display: flex; gap: 8px; align-items: stretch; margin-top: 4px; }
.action-row .btn-generate { flex: 1 1 0; margin-top: 0; }
.btn-history {
  flex: 1 1 0; white-space: nowrap;
  padding: 0 16px; border-radius: 10px;
  border: 1px solid var(--color-border); background: var(--color-surface-2);
  color: var(--color-text-muted); font-size: 0.82rem; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.btn-history:hover { border-color: #2563eb; color: #2563eb; }
.btn-random {
  flex: 1 1 0; white-space: nowrap;
  padding: 0 16px; border-radius: 10px;
  border: 1px solid rgba(37, 99, 235, 0.5); background: rgba(37, 99, 235, 0.12);
  color: #93b4fd; font-size: 0.82rem; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.btn-random:hover:not(:disabled) { border-color: #2563eb; color: #fff; background: rgba(37, 99, 235, 0.28); }
.btn-random:disabled { opacity: 0.45; cursor: not-allowed; }

/* ── 历史图片弹窗 ── */
.history-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.history-modal {
  display: flex; flex-direction: column;
  width: 80vw; height: 80vh;
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: 12px; overflow: hidden;
}
.history-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2); flex-shrink: 0;
}
.history-title { font-size: 0.9rem; font-weight: 700; color: var(--color-text); }
.history-actions { display: flex; gap: 8px; }
.history-filters {
  display: flex; gap: 5px; flex-wrap: wrap;
  padding: 10px 16px; border-bottom: 1px solid var(--color-border); flex-shrink: 0;
}
.history-body { flex: 1; overflow-y: auto; padding: 14px 16px; }
.history-empty { text-align: center; color: var(--color-text-muted); font-size: 0.82rem; padding: 40px 0; }
.history-foot {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px;
  padding: 10px 16px; border-top: 1px solid var(--color-border);
  background: var(--color-surface-2); flex-shrink: 0;
}
.clear-emo-btn {
  margin-right: auto;
  padding: 5px 12px; border-radius: 8px;
  border: 1px solid rgba(255, 107, 107, 0.4);
  background: rgba(255, 107, 107, 0.1); color: #ff6b6b;
  font-size: 0.72rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.clear-emo-btn:hover { background: rgba(255, 107, 107, 0.2); }
.del-btn {
  position: absolute; top: 5px; right: 5px;
  width: 24px; height: 24px; border-radius: 6px; border: none;
  background: rgba(0, 0, 0, 0.6); color: #fff; font-size: 0.8rem;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.2s;
}
.result-item:hover .del-btn { opacity: 1; }
.del-btn:hover { background: rgba(255, 107, 107, 0.85); }

/* ── 头显 USB 连接栏 ── */
.headset-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px; margin: 4px 0 6px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
}
.hs-title { font-weight: 600; font-size: 0.9rem; }
.hs-status {
  font-size: 0.85rem; padding: 2px 10px; border-radius: 999px;
  border: 1px solid transparent;
}
.hs-status.hs-ok { color: #4ade80; border-color: rgba(74, 222, 128, 0.4); background: rgba(74, 222, 128, 0.1); }
.hs-status.hs-bad { color: #f0a0a0; border-color: rgba(240, 160, 160, 0.35); background: rgba(240, 160, 160, 0.08); }
.hs-btn {
  margin-left: auto; padding: 6px 16px; border-radius: 8px; border: none;
  background: #3b82f6; color: #fff; font-size: 0.85rem; cursor: pointer;
}
.hs-btn:disabled { opacity: 0.5; cursor: default; }
.hs-btn.hs-ghost { margin-left: 0; background: rgba(255, 255, 255, 0.1); }
.hs-hint { font-size: 0.78rem; color: rgba(255, 255, 255, 0.45); margin: 0 0 10px; }
.hs-view-box {
  margin-top: 8px;
  min-height: 180px;                 /* 等帧时占位；来帧后跟随图片原始比例（头显单眼近方形）*/
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.hs-view-img { width: 100%; height: auto; display: block; }
.hs-view-waiting { font-size: 0.82rem; color: rgba(255, 255, 255, 0.4); }

/* ── 动态情绪闭环采集 ── */
.scene-select { margin-bottom: 6px; }
.scene-dims { gap: 8px; margin-bottom: 8px; }
.dim-field { display: flex; flex-direction: column; gap: 4px; }
.dim-label { font-size: 0.75rem; color: var(--color-text-muted, rgba(255, 255, 255, 0.55)); }
.btn-stop { background: #dc2626; }
.meta-bad { color: #f0a0a0; font-weight: 600; }
.loop-meta {
  display: flex; flex-wrap: wrap; gap: 12px;
  margin: 8px 0 4px; font-size: 0.82rem;
  color: var(--color-text-secondary, rgba(255, 255, 255, 0.6));
}
.intensity-curve {
  width: 100%; height: 60px; display: block;
  background: rgba(0, 0, 0, 0.15); border-radius: 6px;
}
.curve-line { fill: none; stroke: #4ade80; stroke-width: 1.5; }
.target-line { stroke: rgba(255, 255, 255, 0.35); stroke-width: 1; stroke-dasharray: 4 3; }
.loop-status { margin-top: 6px; }
</style>
