<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-title">{{ locale.pageTitle }}</div>
      <p class="login-desc">{{ locale.login.desc }}</p>

      <div class="field">
        <label class="field-label">{{ locale.login.username }}</label>
        <input
          v-model="username"
          class="ctrl-input"
          autocomplete="username"
          spellcheck="false"
          autofocus
        />
      </div>

      <div class="field">
        <label class="field-label">{{ locale.login.password }}</label>
        <input
          v-model="password"
          type="password"
          class="ctrl-input"
          autocomplete="current-password"
        />
      </div>

      <button class="btn-login" type="submit" :disabled="busy || !password">
        {{ busy ? locale.login.submitting : locale.login.submit }}
      </button>

      <p v-if="error" class="login-error">{{ error }}</p>
    </form>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getAuthStatus, login } from '../api/auth.js'

const props = defineProps({ locale: { type: Object, required: true } })

const route = useRoute()
const router = useRouter()
const prefix = route.path.startsWith('/jp') ? '/jp' : '/cn'

const username = ref('admin')
const password = ref('')
const busy = ref(false)
const error = ref('')

function goBack() {
  const target = route.query.redirect
  router.replace(typeof target === 'string' && target.startsWith('/') ? target : prefix)
}

// 后端没配口令时登录页没有意义，直接进去
onMounted(async () => {
  try {
    const s = await getAuthStatus()
    if (!s.required) goBack()
  } catch { /* 后端没起来：留在登录页，提交时会报错 */ }
})

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await login(username.value, password.value)
    goBack()
  } catch {
    error.value = props.locale.login.error
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 320px;
  padding: 28px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}

.login-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--color-text);
}

.login-desc {
  margin: 6px 0 20px;
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--color-text-muted);
}

.field {
  margin-bottom: 14px;
}

.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.ctrl-input {
  width: 100%;
  padding: 9px 10px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font-family: inherit;
  font-size: 0.85rem;
}

.ctrl-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.btn-login {
  width: 100%;
  margin-top: 6px;
  padding: 10px;
  background: var(--color-primary);
  border: none;
  border-radius: 6px;
  color: var(--color-text);
  font-family: inherit;
  font-size: 0.88rem;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-login:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-login:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.login-error {
  margin-top: 12px;
  font-size: 0.8rem;
  color: #d98080;
  text-align: center;
}
</style>
