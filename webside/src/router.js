import { createRouter, createWebHistory } from 'vue-router'
import EmotionDetector from './components/EmotionDetector.vue'
import TrainingPanel from './components/TrainingPanel.vue'
import ComfyUIPanel from './components/ComfyUIPanel.vue'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const routes = [
  { path: '/',            redirect: '/cn' },
  { path: '/cn',          component: EmotionDetector, props: { locale: zh } },
  { path: '/jp',          component: EmotionDetector, props: { locale: ja } },
  { path: '/cn/train',    component: TrainingPanel,    props: { locale: zh } },
  { path: '/jp/train',    component: TrainingPanel,    props: { locale: ja } },
  { path: '/cn/comfyui',  component: ComfyUIPanel,     props: { locale: zh } },
  { path: '/jp/comfyui',  component: ComfyUIPanel,     props: { locale: ja } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
