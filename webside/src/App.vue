<template>
  <div class="app-layout">
    <!-- ── 左侧一级导航 ── -->
    <aside class="sidebar">
      <div class="brand">{{ currentLocale.pageTitle }}</div>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
        >
          {{ item.label }}
        </RouterLink>

        <!-- 图像生成（含二级菜单） -->
        <div class="nav-group">
          <button
            class="nav-group-header"
            :class="{ open: comfyOpen }"
            @click="comfyOpen = !comfyOpen"
          >
            <span>{{ comfyGroup.label }}</span>
            <span class="caret">{{ comfyOpen ? '▾' : '▸' }}</span>
          </button>
          <div v-show="comfyOpen" class="nav-children">
            <RouterLink
              v-for="c in comfyGroup.children"
              :key="c.to"
              :to="c.to"
              class="nav-link nav-sublink"
            >
              {{ c.label }}
            </RouterLink>
          </div>
        </div>
      </nav>

      <RouterLink :to="langSwitchPath" class="lang-switch">
        {{ currentLocale.langSwitchLabel }}
      </RouterLink>
    </aside>

    <!-- ── 主体内容 ── -->
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watchEffect } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const route = useRoute()

const isJp = computed(() => route.path.startsWith('/jp'))
const prefix = computed(() => (isJp.value ? '/jp' : '/cn'))
const currentLocale = computed(() => (isJp.value ? ja : zh))

// 当前子页后缀（'' / '/train' / '/comfyui'），用于切换语言时保留页面
const suffix = computed(() => route.path.replace(/^\/(cn|jp)/, ''))
const langSwitchPath = computed(() => (isJp.value ? '/cn' : '/jp') + suffix.value)

const navItems = computed(() => [
  { to: prefix.value, label: currentLocale.value.nav.detect },
  { to: `${prefix.value}/train`, label: currentLocale.value.nav.train },
  { to: `${prefix.value}/eval`, label: currentLocale.value.nav.evaluate },
])

// 图像生成一级项及其二级菜单
const comfyGroup = computed(() => ({
  label: currentLocale.value.nav.comfyui,
  children: [
    { to: `${prefix.value}/comfyui`, label: currentLocale.value.nav.comfyExpression },
    { to: `${prefix.value}/comfyui/stimulus`, label: currentLocale.value.nav.comfyStimulus },
  ],
}))

const comfyOpen = ref(true)

watchEffect(() => {
  document.title = currentLocale.value.pageTitle
})
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
  background: #000;
}

/* ── 侧边栏 ── */
.sidebar {
  display: flex;
  flex-direction: column;
  width: 200px;
  flex-shrink: 0;
  padding: 20px 12px;
  background: #000;
  border-right: 1px solid var(--color-border);
}

.brand {
  padding: 8px 12px 20px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-link {
  padding: 10px 12px;
  border-radius: 6px;
  color: var(--color-text-muted);
  font-size: 0.9rem;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.04);
}

.nav-link.router-link-exact-active {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.08);
}

/* ── 二级菜单 ── */
.nav-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--color-text-muted);
  font-size: 0.9rem;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, color 0.15s;
}

.nav-group-header:hover {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.04);
}

.nav-group-header .caret {
  font-size: 0.7rem;
  opacity: 0.7;
}

.nav-children {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-sublink {
  padding-left: 24px;
  font-size: 0.85rem;
}

/* ── 语言切换（侧边栏底部） ── */
.lang-switch {
  margin-top: auto;
  padding: 10px 12px;
  border-radius: 6px;
  color: var(--color-text-muted);
  font-size: 0.85rem;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.lang-switch:hover {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.04);
}

/* ── 主体内容 ── */
.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  padding: 24px;
}
</style>
