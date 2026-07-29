import { createRouter, createWebHistory } from 'vue-router'
import AboutPanel from './components/AboutPanel.vue'
import EmotionDetector from './components/EmotionDetector.vue'
import TrainingPanel from './components/TrainingPanel.vue'
import EvaluationPanel from './components/EvaluationPanel.vue'
import VRStimulusPanel from './components/VRStimulusPanel.vue'
import AffectPreferencePanel from './components/AffectPreferencePanel.vue'
import ResearchLogPanel from './components/ResearchLogPanel.vue'
import SystemSettingsPanel from './components/SystemSettingsPanel.vue'
import zh from './locales/zh.js'
import ja from './locales/ja.js'

const routes = [
  { path: '/',            redirect: '/cn' },
  { path: '/cn/about',    component: AboutPanel,       props: { locale: zh } },
  { path: '/jp/about',    component: AboutPanel,       props: { locale: ja } },
  { path: '/cn',          component: EmotionDetector, props: { locale: zh } },
  { path: '/jp',          component: EmotionDetector, props: { locale: ja } },
  { path: '/cn/train',    component: TrainingPanel,    props: { locale: zh } },
  { path: '/jp/train',    component: TrainingPanel,    props: { locale: ja } },
  { path: '/cn/eval',     component: EvaluationPanel,  props: { locale: zh } },
  { path: '/jp/eval',     component: EvaluationPanel,  props: { locale: ja } },
  { path: '/cn/comfyui/stimulus', component: VRStimulusPanel, props: { locale: zh } },
  { path: '/jp/comfyui/stimulus', component: VRStimulusPanel, props: { locale: ja } },
  { path: '/cn/comfyui/affect', component: AffectPreferencePanel, props: { locale: zh } },
  { path: '/jp/comfyui/affect', component: AffectPreferencePanel, props: { locale: ja } },
  { path: '/cn/log',      component: ResearchLogPanel, props: { locale: zh } },
  { path: '/jp/log',      component: ResearchLogPanel, props: { locale: ja } },
  { path: '/cn/settings',  component: SystemSettingsPanel, props: { locale: zh } },
  { path: '/jp/settings',  component: SystemSettingsPanel, props: { locale: ja } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
