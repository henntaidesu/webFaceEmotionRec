<template>
  <div class="train-wrap">
    <div class="train-card">
      <div class="card-header">
        <span class="panel-title">{{ t.title }}</span>
        <span class="status-badge" :class="statusClass">
          <span class="status-dot"></span>{{ statusLabel }}
        </span>
      </div>

      <div class="card-body two-col">
        <!-- ── 左列：训练选择与基础 ── -->
        <div class="col col-left">
          <!-- 数据集选择 -->
          <div class="field">
            <label class="field-label">{{ t.datasets }}</label>
            <div class="ds-list">
              <label
                v-for="d in datasets"
                :key="d.name"
                class="ds-item"
                :class="{ disabled: !d.available, checked: selected.includes(d.name) }"
              >
                <input
                  type="checkbox"
                  :value="d.name"
                  :disabled="!d.available || isRunning"
                  v-model="selected"
                />
                <span class="ds-name">{{ d.name }}</span>
                <span v-if="d.available" class="ds-count">
                  train {{ d.train.toLocaleString() }} · val {{ d.val.toLocaleString() }}
                </span>
                <span v-else class="ds-count ds-na">{{ t.unavailable }}</span>
              </label>
              <p v-if="datasets.length === 0" class="hint">{{ t.noDatasets }}</p>
            </div>
          </div>

          <!-- 超参数 -->
          <div class="field">
            <label class="field-label">{{ t.params }}</label>
            <div class="param-grid">
              <label class="param">
                <span>{{ t.epochs }}</span>
                <input type="number" v-model.number="form.epochs" min="1" max="200" :disabled="isRunning" class="ctrl-num" />
              </label>
              <label class="param">
                <span>{{ t.batchSize }}</span>
                <input type="number" v-model.number="form.batch_size" min="1" max="512" step="8" :disabled="isRunning" class="ctrl-num" />
              </label>
              <label class="param">
                <span>{{ t.lr }}</span>
                <input type="number" v-model.number="form.lr" min="0.000001" step="0.00005" :disabled="isRunning" class="ctrl-num wide" />
              </label>
              <label class="param">
                <span>{{ t.freezeEpochs }}</span>
                <input type="number" v-model.number="form.freeze_epochs" min="0" max="50" :disabled="isRunning" class="ctrl-num" />
              </label>
              <label class="param">
                <span>{{ t.imgSize }}</span>
                <input type="number" v-model.number="form.img_size" min="96" max="384" step="32" :disabled="isRunning" class="ctrl-num" />
              </label>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="actions">
            <button
              v-if="!isRunning"
              class="btn-primary"
              :disabled="selected.length === 0 || starting"
              @click="onStart"
            >
              {{ starting ? t.starting : t.start }}
            </button>
            <button v-else class="btn-stop" @click="onStop">{{ t.stop }}</button>
          </div>

          <p v-if="errorMsg" class="status-msg msg-error">{{ errorMsg }}</p>
          <p class="note">{{ t.note }}</p>

          <!-- 实时进度 -->
          <div v-if="status.total_epochs > 0" class="progress-section">
            <div class="progress-row">
              <span class="progress-label">{{ t.epoch }} {{ status.epoch }}/{{ status.total_epochs }}</span>
              <span class="progress-label">{{ progressPct }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
            </div>

            <template v-if="isRunning && status.total_steps > 0">
              <div class="progress-row">
                <span class="progress-label">{{ phaseLabel }} {{ status.step }}/{{ status.total_steps }}</span>
                <span class="progress-label">
                  {{ stepPct }}%<template v-if="status.running_loss != null"> · {{ t.curLoss }} {{ fmt(status.running_loss) }}</template>
                </span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill step" :style="{ width: stepPct + '%' }"></div>
              </div>
            </template>

            <div class="metric-grid">
              <div class="metric"><span class="m-k">{{ t.trainAcc }}</span><span class="m-v">{{ fmt(status.train_acc) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.valAcc }}</span><span class="m-v hot">{{ fmt(status.val_acc) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.macroF1 }}</span><span class="m-v hot">{{ fmt(status.macro_f1) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.bestF1 }}</span><span class="m-v">{{ fmt(status.best_f1) }}</span></div>
            </div>
          </div>

          <!-- 日志 -->
          <div v-if="status.log && status.log.length" class="field">
            <label class="field-label">{{ t.log }}</label>
            <pre class="log-box" ref="logBox">{{ status.log.join('\n') }}</pre>
          </div>
        </div>

        <!-- ── 右列：训练轮次 ── -->
        <div class="col col-right">
          <div class="field">
            <label class="field-label">{{ t.runLabel }}</label>
            <select v-model="selectedRunId" class="ctrl-select" :disabled="runs.length === 0">
              <option v-for="r in runs" :key="r.id" :value="r.id">
                {{ r.name }} · {{ runStatusLabel(r.status) }}
              </option>
            </select>
          </div>

          <p v-if="runs.length === 0" class="hint">{{ t.noRuns }}</p>

          <div v-else class="rounds">
            <table class="rounds-table">
              <thead>
                <tr>
                  <th>{{ t.epoch }}</th>
                  <th>{{ t.trainLoss }}</th>
                  <th>{{ t.valLoss }}</th>
                  <th>{{ t.trainAcc }}</th>
                  <th>{{ t.valAcc }}</th>
                  <th>{{ t.macroF1 }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in displayRows" :key="r.epoch" :class="{ best: r.is_best }">
                  <td>{{ r.epoch }}<span v-if="r.is_best" class="best-star" :title="t.bestF1">★</span></td>
                  <td>{{ fmt(r.train_loss) }}</td>
                  <td>{{ fmt(r.val_loss) }}</td>
                  <td>{{ fmt(r.train_acc) }}</td>
                  <td class="hot">{{ fmt(r.val_acc) }}</td>
                  <td class="hot">{{ fmt(r.macro_f1) }}</td>
                </tr>
                <tr v-if="displayRows.length === 0">
                  <td colspan="6" class="empty">{{ t.noEpochYet }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import {
  fetchDatasets, fetchStatus, startTraining, stopTraining, fetchRuns, fetchRun,
} from '../api/trainApi.js'

const props = defineProps({ locale: { type: Object, required: true } })
const t = computed(() => props.locale.train)

const datasets = ref([])
const selected = ref([])
const starting = ref(false)
const errorMsg = ref('')
const logBox = ref(null)

const runs = ref([])               // 历史训练运行列表
const selectedRunId = ref(null)    // 右侧下拉选中的 run
const runRows = ref([])            // 选中「非当前运行」时从后端拉取的逐轮数据

const form = reactive({
  epochs: 15,
  batch_size: 64,
  lr: 0.0001,
  freeze_epochs: 2,
  img_size: 224,
})

const status = reactive({
  status: 'idle', model_id: null, epoch: 0, total_epochs: 0,
  step: 0, total_steps: 0, phase: null, running_loss: null,
  train_loss: null, train_acc: null, val_loss: null, val_acc: null,
  macro_f1: null, best_f1: null, epochs: [], log: [], ckpt_path: null,
})

const isRunning = computed(() => ['running', 'stopping'].includes(status.status))
const progressPct = computed(() =>
  status.total_epochs > 0 ? Math.round((status.epoch / status.total_epochs) * 100) : 0,
)
const stepPct = computed(() =>
  status.total_steps > 0 ? Math.round((status.step / status.total_steps) * 100) : 0,
)
const phaseLabel = computed(() =>
  status.phase === 'val' ? t.value.phaseVal : t.value.phaseTrain,
)

// 选中的是「当前会话内的运行」→ 直接用实时 status.epochs；否则用拉取的 CSV 数据
const isLiveSelected = computed(
  () => !!selectedRunId.value && selectedRunId.value === status.model_id,
)
const displayRows = computed(() => (isLiveSelected.value ? status.epochs : runRows.value))

const statusLabel = computed(() => t.value[`st_${status.status}`] || status.status)
const statusClass = computed(() => ({
  running: 'st-run', stopping: 'st-run', done: 'st-ok',
  stopped: 'st-warn', error: 'st-err', idle: 'st-idle',
}[status.status] || 'st-idle'))

function runStatusLabel(s) {
  return t.value[`st_${s}`] || s
}

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toFixed(3)
}

function applyStatus(data) {
  Object.assign(status, data)
}

async function loadRuns() {
  try {
    const data = await fetchRuns()
    runs.value = data.runs || []
    // 默认选中：当前运行 > 最近一次
    if (!selectedRunId.value || !runs.value.some((r) => r.id === selectedRunId.value)) {
      selectedRunId.value = status.model_id
        || (runs.value[0] && runs.value[0].id) || null
    }
  } catch { /* 后端暂不可达 */ }
}

let timer = null
function startPolling() {
  if (timer) return
  timer = setInterval(refresh, 1000)
}
function stopPolling() {
  clearInterval(timer)
  timer = null
}

async function refresh() {
  try {
    const wasRunning = isRunning.value
    const data = await fetchStatus()
    applyStatus(data)
    if (!isRunning.value) {
      stopPolling()
      if (wasRunning) loadRuns()   // 刚结束 → 刷新历史列表状态
    }
  } catch { /* 后端暂不可达，下次再试 */ }
}

async function onStart() {
  errorMsg.value = ''
  starting.value = true
  try {
    await startTraining({ datasets: selected.value, ...form })
    await refresh()
    selectedRunId.value = status.model_id
    await loadRuns()
    startPolling()
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    starting.value = false
  }
}

async function onStop() {
  try {
    await stopTraining()
    await refresh()
  } catch (e) {
    errorMsg.value = e.message
  }
}

// 选中历史运行（非当前）时拉取其逐轮数据
watch(selectedRunId, async (id) => {
  if (!id || id === status.model_id) {
    runRows.value = []
    return
  }
  try {
    const data = await fetchRun(id)
    runRows.value = data.epochs || []
  } catch {
    runRows.value = []
  }
})

// 日志自动滚到底
watch(() => status.log && status.log.length, async () => {
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
})

onMounted(async () => {
  try {
    const data = await fetchDatasets()
    datasets.value = data.datasets
    const firstAvail = data.datasets.find((d) => d.available)
    if (firstAvail) selected.value = [firstAvail.name]
  } catch (e) {
    errorMsg.value = e.message
  }
  await refresh()
  await loadRuns()
  if (isRunning.value) startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.train-wrap {
  display: flex;
}

.train-card {
  width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2);
}

.panel-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 11px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 600;
}
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.st-run  { background: rgba(255, 193, 7, 0.14);  color: #ffc107; }
.st-ok   { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
.st-warn { background: rgba(255, 159, 64, 0.15); color: #ff9f40; }
.st-err  { background: rgba(255, 107, 107, 0.14); color: #ff6b6b; }
.st-idle { background: rgba(150, 150, 150, 0.14); color: var(--color-text-muted); }

/* 两栏布局 */
.card-body.two-col {
  padding: 16px 18px 22px;
  display: grid;
  grid-template-columns: minmax(300px, 380px) 1fr;
  gap: 20px;
  align-items: start;
}
.col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }

@media (max-width: 1080px) {
  .card-body.two-col { grid-template-columns: 1fr; }
}

.field { display: flex; flex-direction: column; gap: 8px; }

.field-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}

/* 数据集列表 */
.ds-list { display: flex; flex-direction: column; gap: 6px; }

.ds-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--color-surface-2);
}
.ds-item.checked { border-color: var(--color-primary); background: rgba(91, 100, 112, 0.18); }
.ds-item.disabled { opacity: 0.5; cursor: not-allowed; }
.ds-name { font-weight: 600; color: var(--color-text); font-size: 0.85rem; }
.ds-count { margin-left: auto; font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.ds-na { color: #ff6b6b; }

/* 参数 */
.param-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}
.param { display: flex; flex-direction: column; gap: 4px; }
.param > span { font-size: 0.72rem; color: var(--color-text-muted); }

.ctrl-num, .ctrl-select {
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
.ctrl-num:focus, .ctrl-select:focus { border-color: var(--color-primary); }
.ctrl-num:disabled, .ctrl-select:disabled { opacity: 0.6; }

/* 按钮 */
.actions { display: flex; gap: 10px; }

.btn-primary, .btn-stop {
  flex: 1;
  padding: 11px 0;
  border: none;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: opacity 0.2s, transform 0.1s;
  color: #fff;
}
.btn-primary { background: #2563eb; }
.btn-primary:hover:not(:disabled) { opacity: 0.92; transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-stop { background: #d64545; }
.btn-stop:hover { opacity: 0.92; transform: translateY(-1px); }

.note { font-size: 0.72rem; color: var(--color-text-muted); line-height: 1.5; margin: 0; }

.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; margin: 0; }
.msg-error { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }

/* 进度 */
.progress-section { display: flex; flex-direction: column; gap: 10px; }
.progress-row { display: flex; justify-content: space-between; }
.progress-label { font-size: 0.74rem; color: var(--color-text-muted); font-weight: 600; }

.progress-bar { height: 6px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.progress-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--color-primary);
  transition: width 0.3s ease;
}
.progress-fill.step { background: #2563eb; }

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
}
.m-k { font-size: 0.68rem; color: var(--color-text-muted); }
.m-v { font-size: 0.95rem; font-weight: 700; color: var(--color-text); font-family: ui-monospace, monospace; }
.m-v.hot { color: var(--color-accent); }

.log-box {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--color-text-muted);
  font-family: ui-monospace, monospace;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.hint { font-size: 0.78rem; color: var(--color-text-muted); }

/* 训练轮次表格 */
.rounds { max-height: 560px; overflow-y: auto; border: 1px solid var(--color-border); border-radius: 8px; }
.rounds-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
  font-family: ui-monospace, monospace;
}
.rounds-table th, .rounds-table td {
  padding: 8px 10px;
  text-align: right;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}
.rounds-table th:first-child, .rounds-table td:first-child { text-align: left; }
.rounds-table thead th {
  position: sticky;
  top: 0;
  background: var(--color-surface-2);
  color: var(--color-text-muted);
  font-weight: 600;
  font-size: 0.7rem;
  z-index: 1;
}
.rounds-table tbody td { color: var(--color-text); }
.rounds-table tbody td.hot { color: var(--color-accent); }
.rounds-table tbody tr:hover { background: rgba(255, 255, 255, 0.03); }
.rounds-table tbody tr.best { background: rgba(37, 99, 235, 0.12); }
.best-star { color: #2563eb; margin-left: 4px; }
.empty { text-align: center !important; color: var(--color-text-muted); padding: 18px 0; }
</style>
