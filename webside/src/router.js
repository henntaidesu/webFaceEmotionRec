import { createRouter, createWebHistory } from 'vue-router'
import EmotionDetector from './components/EmotionDetector.vue'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const routes = [
  { path: '/',    redirect: '/cn' },
  { path: '/cn',  component: EmotionDetector, props: { locale: zh } },
  { path: '/jp',  component: EmotionDetector, props: { locale: ja } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
