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

      <!-- 右侧：自定义内容区 -->
      <section class="panel-right">
        <slot name="right">
          <div class="right-placeholder">
            <span class="placeholder-icon">🖥️</span>
            <p class="placeholder-text">右侧内容区域</p>
          </div>
        </slot>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, watchEffect } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
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

/* ── 右侧（自定义内容） ── */
.panel-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 默认占位 */
.right-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius);
  color: var(--color-text-muted);
  min-height: 300px;
}

.placeholder-icon {
  font-size: 2.5rem;
}

.placeholder-text {
  font-size: 0.9rem;
  letter-spacing: 0.04em;
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
