<template>
  <div class="app-layout">
    <header class="app-header">
      <h1 class="app-title">{{ currentLocale.pageTitle }}</h1>
      <RouterLink :to="currentLocale.langSwitchPath" class="lang-switch">
        {{ currentLocale.langSwitchLabel }}
      </RouterLink>
    </header>

    <main class="app-main">
      <!-- 左侧：情感识别 -->
      <section class="panel-left">
        <RouterView />
      </section>

      <!-- 右侧：ComfyUI -->
      <section class="panel-right">
        <ComfyUIPanel :locale="currentLocale" />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, watchEffect } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import ComfyUIPanel from './components/ComfyUIPanel.vue'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const localeMap = { '/cn': zh, '/jp': ja }
const route = useRoute()
const currentLocale = computed(() => localeMap[route.path] ?? zh)

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

/* ── 主体两栏 ── */
.app-main {
  display: grid;
  grid-template-columns: 680px 1fr;
  gap: 24px;
  padding: 20px 32px 32px;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  flex: 1;
  min-height: 0;
}

/* ── 左侧（情感识别） ── */
.panel-left {
  min-width: 0;
}

/* ── 右侧（ComfyUI） ── */
.panel-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 100px);
}

/* ── 响应式：窄屏改为单列 ── */
@media (max-width: 1080px) {
  .app-main {
    grid-template-columns: 1fr;
  }

  .app-header,
  .app-main {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
