<template>
  <div class="app-layout">
    <header class="app-header">
      <h1 class="app-title">{{ currentLocale.pageTitle }}</h1>

      <nav class="app-nav">
        <RouterLink :to="detectPath" class="nav-link">{{ currentLocale.nav.detect }}</RouterLink>
        <RouterLink :to="trainPath" class="nav-link">{{ currentLocale.nav.train }}</RouterLink>
      </nav>

      <RouterLink :to="langSwitchPath" class="lang-switch">
        {{ currentLocale.langSwitchLabel }}
      </RouterLink>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed, watchEffect } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const route = useRoute()

const isJp = computed(() => route.path.startsWith('/jp'))
const isTrain = computed(() => route.path.endsWith('/train'))
const prefix = computed(() => (isJp.value ? '/jp' : '/cn'))

const currentLocale = computed(() => (isJp.value ? ja : zh))
const detectPath = computed(() => prefix.value)
const trainPath = computed(() => `${prefix.value}/train`)
// 切换语言时保留当前子页（识别 / 训练）
const langSwitchPath = computed(
  () => (isJp.value ? '/cn' : '/jp') + (isTrain.value ? '/train' : ''),
)

watchEffect(() => {
  document.title = currentLocale.value.pageTitle
})
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
}

/* ── 顶部导航 ── */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 32px 0;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  flex-shrink: 0;
}

.app-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: 0.02em;
}

.lang-switch {
  padding: 6px 18px;
  border-radius: 20px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 0.82rem;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s;
  letter-spacing: 0.04em;
}

.lang-switch:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: rgba(108, 99, 255, 0.08);
}

/* ── 顶部导航（识别 / 训练） ── */
.app-nav {
  display: flex;
  gap: 8px;
  margin-right: auto;
  margin-left: 28px;
}

.nav-link {
  padding: 6px 16px;
  border-radius: 18px;
  color: var(--color-text-muted);
  font-size: 0.85rem;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s;
}

.nav-link:hover {
  color: var(--color-primary);
  background: rgba(108, 99, 255, 0.08);
}

.nav-link.router-link-exact-active {
  color: var(--color-primary);
  background: rgba(108, 99, 255, 0.14);
}

/* ── 主体容器 ── */
.app-main {
  padding: 20px 32px 32px;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  flex: 1;
  min-height: 0;
}

@media (max-width: 1080px) {
  .app-header,
  .app-main {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
