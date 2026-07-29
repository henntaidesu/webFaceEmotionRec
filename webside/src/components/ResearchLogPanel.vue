<template>
  <div class="log-panel">
    <div class="log-header">
      <div class="header-left">
        <span class="panel-title">{{ L.title }}</span>
        <span class="file-path">{{ filePath }}</span>
      </div>
      <div class="header-right">
        <span v-if="dirty" class="dirty-badge">● {{ L.unsaved }}</span>
        <button class="btn-mini" :disabled="loading" @click="reload">↻ {{ L.reload }}</button>
      </div>
    </div>

    <div class="log-body">
      <!-- 左：日期列表 -->
      <aside class="list-col">
        <button class="btn-new" @click="newEntry(todayStr())">＋ {{ L.newToday }}</button>

        <input v-model="query" class="ctrl-input search" :placeholder="L.search" spellcheck="false" />

        <div v-if="allTags.length" class="tag-filter">
          <button
            v-for="t in allTags"
            :key="t"
            class="tag-chip"
            :class="{ on: tagFilter === t }"
            @click="tagFilter = tagFilter === t ? '' : t"
          >{{ t }}</button>
        </div>

        <p v-if="loading" class="list-hint">{{ L.loading }}</p>
        <p v-else-if="visible.length === 0" class="list-hint">{{ entries.length ? L.noMatch : L.noEntries }}</p>

        <ul v-else class="entry-list">
          <li
            v-for="e in visible"
            :key="e.date"
            class="entry-item"
            :class="{ on: e.date === draft.date && !isNew }"
            @click="openEntry(e)"
          >
            <div class="entry-date">{{ e.date }}</div>
            <div class="entry-preview">{{ preview(e) || L.emptyEntry }}</div>
            <div v-if="e.tags.length" class="entry-tags">
              <span v-for="t in e.tags" :key="t" class="tag-mini">{{ t }}</span>
            </div>
          </li>
        </ul>
      </aside>

      <!-- 右：编辑区（分区模板） -->
      <section class="edit-col">
        <div class="edit-toolbar">
          <input v-model="draft.date" type="date" class="ctrl-input date-input" />
          <span v-if="draft.updated_ms && !isNew" class="updated-at">{{ L.updatedAt }} {{ fmtTime(draft.updated_ms) }}</span>
          <div class="spacer"></div>
          <button class="btn-save" :disabled="saving || !draft.date" @click="save">
            {{ saving ? L.saving : L.save }}
          </button>
          <button v-if="!isNew" class="btn-del" :disabled="saving" @click="remove">{{ L.del }}</button>
        </div>

        <div class="field">
          <label class="field-label">📈 {{ L.progress }}</label>
          <textarea v-model="draft.progress" class="ctrl-area tall" :placeholder="L.phProgress" spellcheck="false"></textarea>
        </div>

        <div class="field">
          <label class="field-label">⚠ {{ L.issues }}</label>
          <textarea v-model="draft.issues" class="ctrl-area" :placeholder="L.phIssues" spellcheck="false"></textarea>
        </div>

        <div class="field">
          <label class="field-label">📌 {{ L.plan }}</label>
          <textarea v-model="draft.plan" class="ctrl-area" :placeholder="L.phPlan" spellcheck="false"></textarea>
        </div>

        <div class="field">
          <label class="field-label">🏷 {{ L.tags }}</label>
          <input v-model="tagsText" class="ctrl-input" :placeholder="L.phTags" spellcheck="false" />
          <p class="field-hint">{{ L.tagsHint }}</p>
        </div>

        <p v-if="msg" class="status-msg" :class="msgCls">{{ msg }}</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

const props = defineProps({ locale: { type: Object, required: true } })
const L = computed(() => props.locale.log)

const entries = ref([])
const allTags = ref([])
const filePath = ref('')
const loading = ref(false)
const saving = ref(false)
const query = ref('')
const tagFilter = ref('')
const msg = ref('')
const msgCls = ref('')

// 当前编辑中的条目；isNew 表示这一天在磁盘上还没有记录
const draft = reactive({ date: '', progress: '', issues: '', plan: '', updated_ms: 0 })
const tagsText = ref('')
const isNew = ref(true)
let saved = ''            // 上次保存时的快照，用于 dirty 判定

const todayStr = () => {
  const d = new Date()          // 用本地日期，避免 toISOString 的 UTC 偏移把日期算到前一天
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const snapshot = () => JSON.stringify([draft.date, draft.progress, draft.issues, draft.plan, tagsText.value])
const dirty = computed(() => snapshot() !== saved)

const parseTags = () => tagsText.value.split(/[,，\s]+/).map((t) => t.trim()).filter(Boolean)

function preview(e) {
  return [e.progress, e.issues, e.plan].filter(Boolean).join(' / ').replace(/\s+/g, ' ').slice(0, 60)
}

function fmtTime(ms) {
  const d = new Date(ms)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ` +
         `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return entries.value.filter((e) => {
    if (tagFilter.value && !e.tags.includes(tagFilter.value)) return false
    if (!q) return true
    return [e.date, e.progress, e.issues, e.plan, ...e.tags].join(' ').toLowerCase().includes(q)
  })
})

function setDraft(e, asNew) {
  draft.date = e.date
  draft.progress = e.progress || ''
  draft.issues = e.issues || ''
  draft.plan = e.plan || ''
  draft.updated_ms = e.updated_ms || 0
  tagsText.value = (e.tags || []).join(', ')
  isNew.value = asNew
  saved = snapshot()
  msg.value = ''
}

// 切换条目前若有未保存改动，先让用户确认，避免直接丢弃
function confirmLeave() {
  return !dirty.value || window.confirm(L.value.unsavedConfirm)
}

function openEntry(e) {
  if (draft.date === e.date && !isNew.value) return
  if (!confirmLeave()) return
  setDraft(e, false)
}

function newEntry(date) {
  if (!confirmLeave()) return
  const exist = entries.value.find((e) => e.date === date)
  if (exist) { setDraft(exist, false); return }   // 今天已有记录：直接打开续写，不覆盖
  setDraft({ date, progress: '', issues: '', plan: '', tags: [] }, true)
}

async function load(keepDate) {
  loading.value = true
  try {
    const res = await fetch('/api/log/entries')
    const data = await res.json()
    entries.value = Array.isArray(data.entries) ? data.entries : []
    allTags.value = Array.isArray(data.tags) ? data.tags : []
    filePath.value = data.file || ''
    const target = keepDate || draft.date
    const hit = entries.value.find((e) => e.date === target)
    if (hit) setDraft(hit, false)
    else if (!draft.date) newEntry(todayStr())
  } catch (e) {
    msg.value = `${L.value.loadFailed}${e.message}`
    msgCls.value = 'msg-error'
  } finally {
    loading.value = false
  }
}

// 手动刷新：磁盘上的 JSON 可能被我/编辑器直接改过，重读以看到最新内容
function reload() {
  if (!confirmLeave()) return
  load()
}

async function save() {
  saving.value = true
  msg.value = ''
  try {
    const res = await fetch('/api/log/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: draft.date, progress: draft.progress, issues: draft.issues,
        plan: draft.plan, tags: parseTags(),
      }),
    })
    const data = await res.json()
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`)
    const d = draft.date
    await load(d)
    msg.value = L.value.saved
    msgCls.value = 'msg-ok'
  } catch (e) {
    msg.value = `${L.value.saveFailed}${e.message}`
    msgCls.value = 'msg-error'
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!window.confirm(`${L.value.delConfirm}${draft.date}`)) return
  saving.value = true
  try {
    await fetch(`/api/log/entries/${encodeURIComponent(draft.date)}`, { method: 'DELETE' })
    saved = snapshot()          // 已删除，不再提示未保存
    draft.date = ''
    await load()
    if (!draft.date) newEntry(todayStr())
  } catch (e) {
    msg.value = `${L.value.saveFailed}${e.message}`
    msgCls.value = 'msg-error'
  } finally {
    saving.value = false
  }
}

onMounted(() => load(todayStr()))
</script>

<style scoped>
.log-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
}

.log-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2);
  flex-shrink: 0;
}
.header-left  { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.panel-title { font-size: 0.92rem; font-weight: 700; color: var(--color-text); }
.file-path {
  font-size: 0.7rem; color: var(--color-text-muted);
  font-family: ui-monospace, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dirty-badge { font-size: 0.72rem; color: #ffc107; font-weight: 600; }

.log-body { flex: 1; min-height: 0; display: flex; align-items: stretch; }

/* 左栏：日期列表 */
.list-col {
  width: 260px; flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface-2);
  padding: 12px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 8px;
}
.btn-new {
  padding: 7px 10px; border-radius: 7px; cursor: pointer;
  border: 1px solid #2563eb; background: rgba(37, 99, 235, 0.12);
  color: #6ea8ff; font-size: 0.78rem; font-weight: 600;
}
.btn-new:hover { background: rgba(37, 99, 235, 0.2); }
.search { font-size: 0.76rem; }

.tag-filter { display: flex; flex-wrap: wrap; gap: 5px; }
.tag-chip {
  padding: 2px 8px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--color-border); background: var(--color-surface);
  color: var(--color-text-muted); font-size: 0.68rem;
}
.tag-chip.on { border-color: #2563eb; color: #6ea8ff; background: rgba(37, 99, 235, 0.12); }

.list-hint { font-size: 0.74rem; color: var(--color-text-muted); padding: 8px 2px; }

.entry-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.entry-item {
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--color-border); background: var(--color-surface);
  transition: border-color 0.15s;
}
.entry-item:hover { border-color: #3a3a3a; }
.entry-item.on { border-color: #2563eb; background: rgba(37, 99, 235, 0.08); }
.entry-date { font-size: 0.76rem; font-weight: 700; color: var(--color-text); font-family: ui-monospace, monospace; }
.entry-preview {
  font-size: 0.7rem; color: var(--color-text-muted); margin-top: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.entry-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.tag-mini {
  font-size: 0.62rem; padding: 1px 6px; border-radius: 10px;
  background: rgba(155, 89, 255, 0.14); color: #b07bff;
}

/* 右栏：编辑区 */
.edit-col {
  flex: 1; min-width: 0; overflow-y: auto;
  padding: 14px 16px 20px;
  display: flex; flex-direction: column; gap: 12px;
}
.edit-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.spacer { flex: 1; }
.date-input { width: auto; font-family: ui-monospace, monospace; }
.updated-at { font-size: 0.7rem; color: var(--color-text-muted); }

.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 0.78rem; font-weight: 600; color: var(--color-text); }
.field-hint { font-size: 0.68rem; color: var(--color-text-muted); margin: 0; }

.ctrl-input, .ctrl-area {
  width: 100%; padding: 7px 10px; border-radius: 7px;
  border: 1px solid var(--color-border); background: var(--color-surface);
  color: var(--color-text); font-size: 0.8rem; font-family: inherit;
}
.ctrl-input:focus, .ctrl-area:focus { outline: none; border-color: #2563eb; }
.ctrl-area { resize: vertical; min-height: 80px; line-height: 1.6; }
.ctrl-area.tall { min-height: 160px; }

.btn-save, .btn-del, .btn-mini {
  padding: 6px 14px; border-radius: 7px; cursor: pointer;
  font-size: 0.76rem; font-weight: 600;
  border: 1px solid var(--color-border);
  background: var(--color-surface); color: var(--color-text-muted);
}
.btn-save { border-color: #2563eb; background: rgba(37, 99, 235, 0.14); color: #6ea8ff; }
.btn-save:hover:not(:disabled) { background: rgba(37, 99, 235, 0.22); }
.btn-del:hover:not(:disabled) { border-color: #ff6b6b; color: #ff6b6b; }
.btn-mini:hover:not(:disabled) { border-color: #2563eb; color: #2563eb; }
.btn-save:disabled, .btn-del:disabled, .btn-mini:disabled { opacity: 0.5; cursor: not-allowed; }

.status-msg { font-size: 0.75rem; margin: 0; }
.msg-ok    { color: #2ecc71; }
.msg-error { color: #ff6b6b; }
</style>
