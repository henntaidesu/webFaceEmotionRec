<template>
  <div class="eval-wrap">
    <div class="eval-card">
      <div class="card-header">
        <span class="panel-title">{{ t.title }}</span>
        <span class="status-badge" :class="statusClass">
          <span class="status-dot"></span>{{ statusLabel }}
        </span>
      </div>

      <div class="card-body two-col">
        <!-- ── 左列：评测配置 ── -->
        <div class="col col-left">
          <!-- 模型选择 -->
          <div class="field">
            <label class="field-label">{{ t.model }}</label>
            <select v-model="form.model_id" class="ctrl-select" :disabled="isRunning || models.length === 0">
              <option v-for="m in models" :key="m.id" :value="m.id">
                {{ m.name }}{{ m.type === 'trained' && m.macro_f1 != null ? ` · F1 ${fmt(m.macro_f1)}` : '' }}
              </option>
            </select>
            <p v-if="models.length === 0" class="hint">{{ t.noModels }}</p>
          </div>

          <!-- 数据集选择 -->
          <div class="field">
            <label class="field-label">{{ t.datasets }}</label>
            <div class="ds-list">
              <label
                v-for="d in datasets"
                :key="d.name"
                class="ds-item"
                :class="{ disabled: !dsAvailable(d), checked: selected.includes(d.name) }"
              >
                <input
                  type="checkbox"
                  :value="d.name"
                  :disabled="!dsAvailable(d) || isRunning"
                  v-model="selected"
                />
                <span class="ds-name">{{ d.name }}</span>
                <span v-if="dsAvailable(d)" class="ds-count">
                  val {{ d.val.toLocaleString() }} · test {{ d.test.toLocaleString() }}
                </span>
                <span v-else class="ds-count ds-na">{{ t.unavailable }}</span>
              </label>
              <p v-if="datasets.length === 0" class="hint">{{ t.noDatasets }}</p>
            </div>
          </div>

          <!-- 划分 + 遮挡条件 -->
          <div class="field">
            <label class="field-label">{{ t.split }}</label>
            <div class="seg">
              <button
                v-for="s in splits" :key="s"
                class="seg-btn" :class="{ on: form.split === s }"
                :disabled="isRunning" @click="form.split = s"
              >{{ t[`split_${s}`] || s }}</button>
            </div>
          </div>

          <div class="field">
            <label class="field-label">{{ t.occlusion }}</label>
            <div class="seg">
              <button
                v-for="o in occlusions" :key="o"
                class="seg-btn" :class="{ on: form.occlusion === o }"
                :disabled="isRunning" @click="form.occlusion = o"
              >{{ t[`occl_${o}`] || o }}</button>
            </div>
            <p class="hint">{{ form.occlusion === 'vr' ? t.occlVrHint : t.occlNoneHint }}</p>
          </div>

          <!-- 操作 -->
          <div class="actions">
            <button
              v-if="!isRunning"
              class="btn-primary"
              :disabled="selected.length === 0 || !form.model_id || starting"
              @click="onStart"
            >
              {{ starting ? t.starting : t.start }}
            </button>
            <button v-else class="btn-stop" @click="onStop">{{ t.stop }}</button>
          </div>

          <p v-if="errorMsg" class="status-msg msg-error">{{ errorMsg }}</p>

          <!-- 进度 -->
          <div v-if="isRunning && status.total_steps > 0" class="progress-section">
            <div class="progress-row">
              <span class="progress-label">{{ t.progress }} {{ status.step }}/{{ status.total_steps }}</span>
              <span class="progress-label">{{ stepPct }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill step" :style="{ width: stepPct + '%' }"></div>
            </div>
          </div>

          <!-- 日志 -->
          <div v-if="status.log && status.log.length" class="field">
            <label class="field-label">{{ t.log }}</label>
            <pre class="log-box" ref="logBox">{{ status.log.join('\n') }}</pre>
          </div>
        </div>

        <!-- ── 右列：评测结果 ── -->
        <div class="col col-right">
          <div class="field">
            <label class="field-label">{{ t.runLabel }}</label>
            <div class="run-row">
              <select v-model="selectedRunId" class="ctrl-select" :disabled="runs.length === 0">
                <option v-for="r in runs" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
              <button
                v-if="selectedRunId" class="btn-icon" :title="t.delete"
                :disabled="isRunning" @click="onDelete"
              >🗑</button>
            </div>
          </div>

          <p v-if="!result" class="hint">{{ t.noResult }}</p>

          <template v-else>
            <!-- 总体指标 -->
            <div class="metric-grid">
              <div class="metric"><span class="m-k">{{ t.accuracy }}</span><span class="m-v hot">{{ fmt(result.accuracy) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.macroF1 }}</span><span class="m-v hot">{{ fmt(result.macro_f1) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.weightedF1 }}</span><span class="m-v">{{ fmt(result.weighted_f1) }}</span></div>
              <div class="metric"><span class="m-k">{{ t.samples }}</span><span class="m-v">{{ (result.total || 0).toLocaleString() }}</span></div>
            </div>

            <div class="result-meta">
              <span>{{ result.model_name }}</span>
              <span>{{ (result.datasets || []).join('/') }} · {{ t[`split_${result.split}`] || result.split }} · {{ t[`occl_${result.occlusion}`] || result.occlusion }}</span>
            </div>

            <!-- 逐类指标 -->
            <div class="field">
              <div class="sub-head">
                <label class="field-label">{{ t.perClass }}</label>
                <button class="btn-link" @click="downloadPerClassCsv">{{ t.exportCsv }}</button>
              </div>
              <div class="rounds">
                <table class="rounds-table">
                  <thead>
                    <tr>
                      <th>{{ t.class }}</th>
                      <th>{{ t.precision }}</th>
                      <th>{{ t.recall }}</th>
                      <th>{{ t.f1 }}</th>
                      <th>{{ t.support }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="c in result.per_class" :key="c.class">
                      <td>{{ c.class }}</td>
                      <td>{{ fmt(c.precision) }}</td>
                      <td>{{ fmt(c.recall) }}</td>
                      <td class="hot">{{ fmt(c.f1) }}</td>
                      <td>{{ c.support }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- 混淆矩阵热力图 -->
            <div class="field">
              <div class="sub-head">
                <label class="field-label">{{ t.confusion }}</label>
                <button class="btn-link" @click="downloadConfusionCsv">{{ t.exportCsv }}</button>
              </div>
              <p class="hint">{{ t.confusionHint }}</p>
              <div class="cm-scroll">
                <table class="cm-table">
                  <thead>
                    <tr>
                      <th class="cm-corner">{{ t.cmAxis }}</th>
                      <th v-for="c in result.classes" :key="c" class="cm-pred">{{ c }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, i) in result.confusion_matrix" :key="i">
                      <th class="cm-true">{{ result.classes[i] }}</th>
                      <td
                        v-for="(v, j) in row" :key="j"
                        class="cm-cell" :class="{ diag: i === j }"
                        :style="cellStyle(row, v, i === j)"
                      >{{ v }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import {
  fetchTargets, fetchStatus, startEval, stopEval, fetchRuns, fetchRun, deleteRun,
} from '../api/evalApi.js'

const props = defineProps({ locale: { type: Object, required: true } })
const t = computed(() => props.locale.evaluate)

const models = ref([])
const datasets = ref([])
const splits = ref(['val', 'test'])
const occlusions = ref(['none', 'vr'])
const selected = ref([])
const starting = ref(false)
const errorMsg = ref('')
const logBox = ref(null)

const runs = ref([])
const selectedRunId = ref(null)
const fetchedResult = ref(null)   // 选中历史记录（非当前会话）时拉取的完整结果

const form = reactive({ model_id: '', split: 'val', occlusion: 'none' })

const status = reactive({
  status: 'idle', eval_id: null, model_id: null, model_name: null,
  datasets: [], split: null, occlusion: null,
  step: 0, total_steps: 0, result: null, log: [],
})

const isRunning = computed(() => status.status === 'running')
const stepPct = computed(() =>
  status.total_steps > 0 ? Math.round((status.step / status.total_steps) * 100) : 0,
)

const statusLabel = computed(() => t.value[`st_${status.status}`] || status.status)
const statusClass = computed(() => ({
  running: 'st-run', done: 'st-ok', stopped: 'st-warn', error: 'st-err', idle: 'st-idle',
}[status.status] || 'st-idle'))

// 选中的是本次会话刚完成的评测 → 用 status.result；否则用拉取的历史结果
const isLiveSelected = computed(
  () => !!selectedRunId.value && selectedRunId.value === status.eval_id && !!status.result,
)
const result = computed(() => (isLiveSelected.value ? status.result : fetchedResult.value))

function dsAvailable(d) {
  return form.split === 'test' ? d.has_test : d.has_val
}

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toFixed(3)
}

// 混淆矩阵单元格按「该行（真实类）最大值」着色；对角线用绿色，其余用红色
function cellStyle(row, v, isDiag) {
  const max = Math.max(...row, 1)
  const a = v === 0 ? 0 : 0.12 + 0.6 * (v / max)
  const rgb = isDiag ? '46, 204, 113' : '214, 69, 69'
  return { background: `rgba(${rgb}, ${a.toFixed(3)})` }
}

function applyStatus(data) {
  Object.assign(status, data)
}

async function loadRuns() {
  try {
    const data = await fetchRuns()
    runs.value = data.evals || []
    if (!selectedRunId.value || !runs.value.some((r) => r.id === selectedRunId.value)) {
      selectedRunId.value = status.eval_id || (runs.value[0] && runs.value[0].id) || null
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
      if (wasRunning) {           // 刚结束 → 选中本次结果并刷新历史
        selectedRunId.value = status.eval_id
        loadRuns()
      }
    }
  } catch { /* 后端暂不可达 */ }
}

async function onStart() {
  errorMsg.value = ''
  starting.value = true
  try {
    await startEval({ model_id: form.model_id, datasets: selected.value, split: form.split, occlusion: form.occlusion })
    await refresh()
    selectedRunId.value = status.eval_id
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
    await stopEval()
    await refresh()
  } catch (e) {
    errorMsg.value = e.message
  }
}

async function onDelete() {
  const id = selectedRunId.value
  if (!id) return
  try {
    await deleteRun(id)
    selectedRunId.value = null
    fetchedResult.value = null
    await loadRuns()
  } catch (e) {
    errorMsg.value = e.message
  }
}

// 选中历史记录（非本次会话结果）时拉取完整结果
watch(selectedRunId, async (id) => {
  if (!id || (id === status.eval_id && status.result)) {
    fetchedResult.value = null
    return
  }
  try {
    fetchedResult.value = await fetchRun(id)
  } catch {
    fetchedResult.value = null
  }
})

watch(() => status.log && status.log.length, async () => {
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
})

// 数据集可用性随划分变化：切到 test 时剔除无 test 的已选项
watch(() => form.split, () => {
  selected.value = selected.value.filter((name) => {
    const d = datasets.value.find((x) => x.name === name)
    return d && dsAvailable(d)
  })
})

// ── CSV 导出（供论文使用）──────────────────────────────────────
function download(filename, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function downloadPerClassCsv() {
  if (!result.value) return
  const rows = ['class,precision,recall,f1,support']
  for (const c of result.value.per_class) {
    rows.push(`${c.class},${c.precision},${c.recall},${c.f1},${c.support}`)
  }
  download(`${result.value.id}_per_class.csv`, rows.join('\n'))
}

function downloadConfusionCsv() {
  if (!result.value) return
  const cls = result.value.classes
  const rows = ['true\\pred,' + cls.join(',')]
  result.value.confusion_matrix.forEach((row, i) => {
    rows.push(`${cls[i]},${row.join(',')}`)
  })
  download(`${result.value.id}_confusion_matrix.csv`, rows.join('\n'))
}

onMounted(async () => {
  try {
    const data = await fetchTargets()
    models.value = data.models || []
    datasets.value = data.datasets || []
    splits.value = data.splits || ['val', 'test']
    occlusions.value = data.occlusions || ['none', 'vr']
    if (models.value.length && !form.model_id) form.model_id = models.value[0].id
    selected.value = datasets.value.filter((d) => dsAvailable(d)).map((d) => d.name)
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
.eval-wrap { display: flex; }
.eval-card {
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
.panel-title { font-size: 0.95rem; font-weight: 700; color: var(--color-text); }

.status-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 11px; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
}
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.st-run  { background: rgba(255, 193, 7, 0.14);  color: #ffc107; }
.st-ok   { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
.st-warn { background: rgba(255, 159, 64, 0.15); color: #ff9f40; }
.st-err  { background: rgba(255, 107, 107, 0.14); color: #ff6b6b; }
.st-idle { background: rgba(150, 150, 150, 0.14); color: var(--color-text-muted); }

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
  font-size: 0.75rem; font-weight: 600; color: var(--color-text-muted); letter-spacing: 0.04em;
}
.sub-head { display: flex; align-items: center; justify-content: space-between; }

.ds-list { display: flex; flex-direction: column; gap: 6px; }
.ds-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border: 1px solid var(--color-border); border-radius: 9px;
  cursor: pointer; transition: all 0.15s; background: var(--color-surface-2);
}
.ds-item.checked { border-color: var(--color-primary); background: rgba(91, 100, 112, 0.18); }
.ds-item.disabled { opacity: 0.5; cursor: not-allowed; }
.ds-name { font-weight: 600; color: var(--color-text); font-size: 0.85rem; }
.ds-count { margin-left: auto; font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.ds-na { color: #ff6b6b; }

.ctrl-select {
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: 8px; color: var(--color-text); font-size: 0.82rem;
  padding: 7px 10px; outline: none; transition: border-color 0.2s; width: 100%;
}
.ctrl-select:focus { border-color: var(--color-primary); }
.ctrl-select:disabled { opacity: 0.6; }

.run-row { display: flex; gap: 8px; align-items: center; }
.btn-icon {
  flex-shrink: 0; width: 34px; height: 34px; border-radius: 8px;
  border: 1px solid var(--color-border); background: var(--color-surface-2);
  color: var(--color-text-muted); cursor: pointer; font-size: 0.85rem;
}
.btn-icon:hover:not(:disabled) { color: #ff6b6b; border-color: #ff6b6b; }
.btn-icon:disabled { opacity: 0.5; cursor: not-allowed; }

/* 分段开关（划分 / 遮挡） */
.seg { display: flex; gap: 6px; }
.seg-btn {
  flex: 1; padding: 8px 0; border-radius: 8px;
  border: 1px solid var(--color-border); background: var(--color-surface-2);
  color: var(--color-text-muted); font-size: 0.8rem; font-weight: 600; cursor: pointer;
  transition: all 0.15s;
}
.seg-btn.on { border-color: var(--color-primary); background: rgba(37, 99, 235, 0.16); color: var(--color-text); }
.seg-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.actions { display: flex; gap: 10px; }
.btn-primary, .btn-stop {
  flex: 1; padding: 11px 0; border: none; border-radius: 10px;
  font-size: 0.9rem; font-weight: 700; cursor: pointer; letter-spacing: 0.04em;
  transition: opacity 0.2s, transform 0.1s; color: #fff;
}
.btn-primary { background: #2563eb; }
.btn-primary:hover:not(:disabled) { opacity: 0.92; transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-stop { background: #d64545; }
.btn-stop:hover { opacity: 0.92; transform: translateY(-1px); }

.btn-link {
  background: none; border: none; color: var(--color-accent);
  font-size: 0.72rem; cursor: pointer; padding: 0;
}
.btn-link:hover { text-decoration: underline; }

.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; margin: 0; }
.msg-error { background: rgba(255, 107, 107, 0.12); color: #ff6b6b; }

.progress-section { display: flex; flex-direction: column; gap: 10px; }
.progress-row { display: flex; justify-content: space-between; }
.progress-label { font-size: 0.74rem; color: var(--color-text-muted); font-weight: 600; }
.progress-bar { height: 6px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; background: var(--color-primary); transition: width 0.3s ease; }
.progress-fill.step { background: #2563eb; }

.metric-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
.metric {
  display: flex; flex-direction: column; gap: 3px; padding: 8px 10px;
  border-radius: 8px; background: var(--color-surface-2); border: 1px solid var(--color-border);
}
.m-k { font-size: 0.68rem; color: var(--color-text-muted); }
.m-v { font-size: 0.95rem; font-weight: 700; color: var(--color-text); font-family: ui-monospace, monospace; }
.m-v.hot { color: var(--color-accent); }

.result-meta {
  display: flex; flex-direction: column; gap: 2px;
  font-size: 0.74rem; color: var(--color-text-muted);
}

.log-box {
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 10px 12px; font-size: 0.72rem; line-height: 1.5;
  color: var(--color-text-muted); font-family: ui-monospace, monospace;
  max-height: 200px; overflow-y: auto; margin: 0; white-space: pre-wrap; word-break: break-all;
}
.hint { font-size: 0.78rem; color: var(--color-text-muted); margin: 0; }

/* 逐类指标表 */
.rounds { max-height: 320px; overflow-y: auto; border: 1px solid var(--color-border); border-radius: 8px; }
.rounds-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; font-family: ui-monospace, monospace; }
.rounds-table th, .rounds-table td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
.rounds-table th:first-child, .rounds-table td:first-child { text-align: left; }
.rounds-table thead th { position: sticky; top: 0; background: var(--color-surface-2); color: var(--color-text-muted); font-weight: 600; font-size: 0.7rem; z-index: 1; }
.rounds-table tbody td { color: var(--color-text); }
.rounds-table tbody td.hot { color: var(--color-accent); }

/* 混淆矩阵热力图 */
.cm-scroll { overflow-x: auto; border: 1px solid var(--color-border); border-radius: 8px; }
.cm-table { border-collapse: collapse; font-size: 0.72rem; font-family: ui-monospace, monospace; width: 100%; }
.cm-table th, .cm-table td { padding: 7px 9px; text-align: center; white-space: nowrap; }
.cm-corner { color: var(--color-text-muted); font-size: 0.62rem; text-align: left; }
.cm-pred { color: var(--color-text-muted); font-weight: 600; border-bottom: 1px solid var(--color-border); }
.cm-true { color: var(--color-text-muted); font-weight: 600; text-align: right; border-right: 1px solid var(--color-border); }
.cm-cell { color: var(--color-text); font-weight: 600; }
.cm-cell.diag { font-weight: 800; }
</style>
