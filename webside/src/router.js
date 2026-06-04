import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './components/HomeView.vue'
import TrainingPanel from './components/TrainingPanel.vue'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const routes = [
  { path: '/',          redirect: '/cn' },
  { path: '/cn',        component: HomeView,      props: { locale: zh } },
  { path: '/jp',        component: HomeView,      props: { locale: ja } },
  { path: '/cn/train',  component: TrainingPanel, props: { locale: zh } },
  { path: '/jp/train',  component: TrainingPanel, props: { locale: ja } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
