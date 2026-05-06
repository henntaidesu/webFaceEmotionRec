<template>
  <div class="app-layout">
    <header class="app-header">
      <h1 class="app-title">{{ currentLocale.pageTitle }}</h1>
      <RouterLink :to="currentLocale.langSwitchPath" class="lang-switch">
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
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px 0;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
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

.app-main {
  max-width: 960px;
  margin: 0 auto;
  padding: 20px 24px 28px;
  width: 100%;
}

@media (max-width: 768px) {
  .app-header,
  .app-main {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
