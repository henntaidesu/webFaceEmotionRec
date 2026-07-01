<template>
  <Teleport to="body">
    <div class="pano-overlay">
      <div ref="mount" class="pano-mount"></div>
      <div v-if="caption" class="pano-caption">{{ caption }}</div>
      <div class="pano-toolbar">
        <button v-if="xrSupported" class="pano-btn" @click="enterVR">🥽 {{ enterVrLabel }}</button>
        <a :href="src" download class="pano-btn" :title="downloadLabel">↓</a>
        <button class="pano-btn close" @click="$emit('close')">✕</button>
      </div>
      <p class="pano-hint">{{ hint }}</p>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'

const props = defineProps({
  src: { type: String, required: true },
  enterVrLabel: { type: String, default: '进入 VR' },
  downloadLabel: { type: String, default: '下载' },
  hint: { type: String, default: '拖动查看 · 滚轮缩放' },
  caption: { type: String, default: '' },
})
defineEmits(['close'])

const mount = ref(null)
const xrSupported = ref(false)

let renderer, scene, camera, sphere, texture, raf
let lon = 0, lat = 0, isDown = false, downX = 0, downY = 0, downLon = 0, downLat = 0
let fov = 75

function onResize() {
  if (!renderer || !camera) return
  const w = mount.value.clientWidth
  const h = mount.value.clientHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}
function onDown(e) {
  isDown = true
  const p = e.touches ? e.touches[0] : e
  downX = p.clientX; downY = p.clientY; downLon = lon; downLat = lat
}
function onMove(e) {
  if (!isDown) return
  const p = e.touches ? e.touches[0] : e
  lon = downLon - (p.clientX - downX) * 0.15
  lat = downLat + (p.clientY - downY) * 0.15
  lat = Math.max(-85, Math.min(85, lat))
}
function onUp() { isDown = false }
function onWheel(e) {
  fov = Math.max(30, Math.min(100, fov + e.deltaY * 0.05))
  camera.fov = fov
  camera.updateProjectionMatrix()
}

function animate() {
  raf = renderer.setAnimationLoop(render)
}
function render() {
  // WebXR 会话中由头显姿态控制相机；非 VR 时用鼠标经纬度
  if (!renderer.xr.isPresenting) {
    const phi = THREE.MathUtils.degToRad(90 - lat)
    const theta = THREE.MathUtils.degToRad(lon)
    camera.lookAt(
      500 * Math.sin(phi) * Math.cos(theta),
      500 * Math.cos(phi),
      500 * Math.sin(phi) * Math.sin(theta),
    )
  }
  renderer.render(scene, camera)
}

async function enterVR() {
  try {
    const session = await navigator.xr.requestSession('immersive-vr', {
      optionalFeatures: ['local-floor', 'bounded-floor'],
    })
    await renderer.xr.setSession(session)
  } catch (err) {
    console.warn('enter VR failed:', err)
  }
}

onMounted(async () => {
  const w = mount.value.clientWidth
  const h = mount.value.clientHeight

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(fov, w / h, 0.1, 1100)
  camera.position.set(0, 0, 0.01)

  // 内翻的球体：把等距全景贴到球内壁
  const geo = new THREE.SphereGeometry(500, 60, 40)
  geo.scale(-1, 1, 1)
  texture = new THREE.TextureLoader().load(props.src)
  texture.colorSpace = THREE.SRGBColorSpace
  sphere = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: texture }))
  scene.add(sphere)

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setSize(w, h)
  renderer.xr.enabled = true
  mount.value.appendChild(renderer.domElement)

  const el = renderer.domElement
  el.addEventListener('mousedown', onDown)
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  el.addEventListener('touchstart', onDown, { passive: true })
  window.addEventListener('touchmove', onMove, { passive: true })
  window.addEventListener('touchend', onUp)
  el.addEventListener('wheel', onWheel, { passive: true })
  window.addEventListener('resize', onResize)

  animate()

  // 检测是否支持沉浸式 VR（Quest 浏览器 / 支持 WebXR 的环境）
  if (navigator.xr?.isSessionSupported) {
    try { xrSupported.value = await navigator.xr.isSessionSupported('immersive-vr') } catch { /* 忽略 */ }
  }
})

// 序列呈现时父组件会切换 src → 重新加载球体贴图
watch(() => props.src, (url) => {
  if (!sphere || !url) return
  const next = new THREE.TextureLoader().load(url)
  next.colorSpace = THREE.SRGBColorSpace
  const old = sphere.material.map
  sphere.material.map = next
  sphere.material.needsUpdate = true
  if (old) old.dispose()
  texture = next
})

onUnmounted(() => {
  if (renderer) renderer.setAnimationLoop(null)
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
  window.removeEventListener('touchmove', onMove)
  window.removeEventListener('touchend', onUp)
  window.removeEventListener('resize', onResize)
  if (renderer) {
    const el = renderer.domElement
    el.removeEventListener('mousedown', onDown)
    el.removeEventListener('touchstart', onDown)
    el.removeEventListener('wheel', onWheel)
    renderer.dispose()
  }
  if (texture) texture.dispose()
  if (sphere) sphere.geometry.dispose()
})
</script>

<style scoped>
.pano-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: #000;
}
.pano-mount { width: 100%; height: 100%; }
.pano-mount :deep(canvas) { display: block; cursor: grab; }
.pano-mount :deep(canvas):active { cursor: grabbing; }

.pano-toolbar {
  position: absolute; top: 18px; right: 18px;
  display: flex; gap: 8px;
}
.pano-btn {
  min-width: 40px; height: 40px; padding: 0 12px;
  border-radius: 8px; border: 1px solid rgba(255,255,255,0.25);
  background: rgba(0,0,0,0.5); color: #fff;
  font-size: 0.9rem; font-weight: 600; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none; transition: background 0.2s;
}
.pano-btn:hover { background: rgba(255,255,255,0.18); }
.pano-btn.close { font-size: 1rem; }

.pano-hint {
  position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
  color: rgba(255,255,255,0.7); font-size: 0.78rem;
  background: rgba(0,0,0,0.4); padding: 6px 14px; border-radius: 16px;
}

.pano-caption {
  position: absolute; top: 18px; left: 18px;
  color: #fff; font-size: 1.1rem; font-weight: 700;
  background: rgba(0,0,0,0.5); padding: 8px 18px; border-radius: 10px;
  letter-spacing: 0.05em;
}
</style>
