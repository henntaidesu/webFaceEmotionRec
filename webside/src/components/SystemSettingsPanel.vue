<template>
  <div class="settings-panel">
    <div class="settings-header">
      <span class="panel-title">{{ locale.settings.title }}</span>
      <span class="conf-path">conf.ini</span>
    </div>

    <div class="settings-body">
      <p class="panel-desc">{{ locale.settings.desc }}</p>

      <!-- DeepSeek -->
      <section class="card">
        <div class="card-title">🧠 {{ locale.settings.deepseekTitle }}</div>
        <p class="card-hint">{{ locale.settings.deepseekHint }}</p>

        <div class="field">
          <label class="field-label">{{ locale.settings.apiKey }}</label>
          <div class="key-row">
            <input
              :type="showKey ? 'text' : 'password'"
              v-model="ds.api_key"
              class="ctrl-input"
              placeholder="sk-..."
              autocomplete="off"
              spellcheck="false"
            />
            <button class="btn-mini" type="button" @click="showKey = !showKey">
              {{ showKey ? locale.settings.hide : locale.settings.show }}
            </button>
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ locale.settings.baseUrl }}</label>
          <input v-model="ds.base_url" class="ctrl-input" spellcheck="false" />
        </div>

        <div class="field">
          <label class="field-label">{{ locale.settings.model }}</label>
          <input v-model="ds.model" class="ctrl-input" spellcheck="false" />
        </div>

        <div class="grid2">
          <div class="field">
            <label class="field-label">{{ locale.settings.timeout }}</label>
            <input v-model.number="ds.timeout" type="number" min="1" step="1" class="ctrl-input" />
          </div>
          <div class="field">
            <label class="field-label">{{ locale.settings.temperature }}</label>
            <input v-model.number="ds.temperature" type="number" min="0" max="2" step="0.1" class="ctrl-input" />
          </div>
        </div>

        <div class="row-group">
          <button class="btn-save" :disabled="saving" @click="save">
            {{ saving ? locale.settings.saving : locale.settings.save }}
          </button>
          <button class="btn-mini" :disabled="testing || !ds.api_key" @click="testConn">
            {{ testing ? locale.settings.testing : locale.settings.test }}
          </button>
          <button class="btn-mini" :disabled="loading" @click="load">↻ {{ locale.settings.reload }}</button>
        </div>

        <p v-if="msg" class="status-msg" :class="msgCls">{{ msg }}</p>
      </section>

      <!-- Postgres + pgvector -->
      <section class="card">
        <div class="card-title">🗄 {{ locale.settings.pgTitle }}</div>
        <p class="card-hint">{{ locale.settings.pgHint }}</p>

        <div class="grid2">
          <div class="field">
            <label class="field-label">{{ locale.settings.pgHost }}</label>
            <input v-model.trim="pg.host" class="ctrl-input" placeholder="10.0.10.20" spellcheck="false" />
          </div>
          <div class="field">
            <label class="field-label">{{ locale.settings.pgPort }}</label>
            <input v-model.number="pg.port" type="number" min="1" max="65535" class="ctrl-input" />
          </div>
        </div>

        <div class="grid2">
          <div class="field">
            <label class="field-label">{{ locale.settings.pgUser }}</label>
            <input v-model.trim="pg.user" class="ctrl-input" placeholder="postgres" spellcheck="false" />
          </div>
          <div class="field">
            <label class="field-label">{{ locale.settings.pgDatabase }}</label>
            <input v-model.trim="pg.database" class="ctrl-input" placeholder="webfaceemotionrec" spellcheck="false" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ locale.settings.pgPassword }}</label>
          <div class="key-row">
            <input
              :type="showDsn ? 'text' : 'password'"
              v-model="pg.password"
              class="ctrl-input"
              autocomplete="off"
              spellcheck="false"
            />
            <button class="btn-mini" type="button" @click="showDsn = !showDsn">
              {{ showDsn ? locale.settings.hide : locale.settings.show }}
            </button>
          </div>
        </div>

        <div class="row-group">
          <button class="btn-save" :disabled="pgSaving" @click="savePg">
            {{ pgSaving ? locale.settings.saving : locale.settings.save }}
          </button>
          <button class="btn-mini" :disabled="pgTesting || !pg.host" @click="testPg">
            {{ pgTesting ? locale.settings.testing : locale.settings.test }}
          </button>
        </div>

        <p v-if="pgMsg" class="status-msg" :class="pgMsgCls">{{ pgMsg }}</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'

const props = defineProps({ locale: { type: Object, required: true } })

const ds = reactive({ api_key: '', base_url: '', model: '', timeout: 30, temperature: 1.3 })
const showKey = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const msg = ref('')
const msgCls = ref('')

const pg = reactive({ host: '', port: 5432, user: 'postgres', password: '', database: 'webfaceemotionrec' })
const showDsn = ref(false)
const pgSaving = ref(false)
const pgTesting = ref(false)
const pgMsg = ref('')
const pgMsgCls = ref('')

function setMsg(text, cls) { msg.value = text; msgCls.value = cls }
function setPgMsg(text, cls) { pgMsg.value = text; pgMsgCls.value = cls }

async function load() {
  loading.value = true
  try {
    const res = await fetch('/api/settings')
    const data = await res.json()
    if (data.deepseek) Object.assign(ds, data.deepseek)
    if (data.postgres) Object.assign(pg, data.postgres)
    setMsg('', '')
  } catch (e) {
    setMsg(`${props.locale.settings.loadError}: ${e.message}`, 'msg-error')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deepseek: { ...ds } }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`)
    if (data.settings?.deepseek) Object.assign(ds, data.settings.deepseek)
    setMsg(props.locale.settings.saved, 'msg-ok')
  } catch (e) {
    setMsg(`${props.locale.settings.saveError}: ${e.message}`, 'msg-error')
  } finally {
    saving.value = false
  }
}

async function testConn() {
  testing.value = true
  setMsg(props.locale.settings.testing, '')
  try {
    // 先保存，确保测的是当前表单值
    await save()
    const res = await fetch('/api/settings/deepseek/test', { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`)
    setMsg(`${props.locale.settings.testOk}（${data.model}）`, 'msg-ok')
  } catch (e) {
    setMsg(`${props.locale.settings.testFail}: ${e.message}`, 'msg-error')
  } finally {
    testing.value = false
  }
}

async function savePg() {
  pgSaving.value = true
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ postgres: { ...pg } }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`)
    if (data.settings?.postgres) Object.assign(pg, data.settings.postgres)
    setPgMsg(props.locale.settings.saved, 'msg-ok')
  } catch (e) {
    setPgMsg(`${props.locale.settings.saveError}: ${e.message}`, 'msg-error')
  } finally {
    pgSaving.value = false
  }
}

async function testPg() {
  pgTesting.value = true
  setPgMsg(props.locale.settings.testing, '')
  try {
    await savePg()
    const res = await fetch('/api/settings/postgres/test', { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`)
    setPgMsg(`${props.locale.settings.testOk}（PostgreSQL ${data.server_version || ''}）`, 'msg-ok')
  } catch (e) {
    setPgMsg(`${props.locale.settings.testFail}: ${e.message}`, 'msg-error')
  } finally {
    pgTesting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.settings-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius); overflow: hidden; }
.settings-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface-2); }
.panel-title { font-size: 0.92rem; font-weight: 700; color: var(--color-text); }
.conf-path { font-size: 0.72rem; color: var(--color-text-muted); font-family: ui-monospace, monospace; }
.settings-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; max-width: 620px; }
.panel-desc { font-size: 0.78rem; line-height: 1.5; color: var(--color-text-muted); }

.card { display: flex; flex-direction: column; gap: 10px; padding: 16px; border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-surface-2); }
.card-title { font-size: 0.88rem; font-weight: 700; color: var(--color-text); }
.card-hint { font-size: 0.74rem; line-height: 1.5; color: var(--color-text-muted); }

.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 0.76rem; font-weight: 600; color: var(--color-text-muted); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ctrl-input { width: 100%; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; color: var(--color-text); font-size: 0.82rem; padding: 8px 10px; font-family: ui-monospace, monospace; }
.key-row { display: flex; gap: 8px; }
.key-row .ctrl-input { flex: 1; }

.row-group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 4px; }
.btn-save { padding: 9px 18px; border: none; border-radius: 8px; background: #2563eb; color: #fff; font-size: 0.84rem; font-weight: 700; cursor: pointer; }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-mini { padding: 8px 14px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text); font-size: 0.8rem; cursor: pointer; }
.btn-mini:disabled { opacity: 0.5; cursor: not-allowed; }
.status-msg { font-size: 0.78rem; border-radius: 6px; padding: 7px 10px; margin-top: 2px; }
.msg-ok { background: rgba(46,204,113,0.12); color: #2ecc71; }
.msg-error { background: rgba(255,107,107,0.12); color: #ff6b6b; }
</style>
