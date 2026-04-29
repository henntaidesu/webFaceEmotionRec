<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="header-inner">
        <div class="logo">
          <span class="logo-icon">🧠</span>
          <div>
            <h1 class="logo-title">人脸情感识别</h1>
            <p class="logo-sub">Face Emotion Recognition</p>
          </div>
        </div>
        <div class="header-badges">
          <span class="badge">Vue 3</span>
          <span class="badge">FastAPI</span>
          <span class="badge">DeepFace</span>
        </div>
      </div>
    </header>

    <main class="app-main">
      <div class="sidebar">
        <div class="info-card">
          <h3 class="info-title">使用说明</h3>
          <ol class="info-steps">
            <li>点击 <strong>开启摄像头</strong> 获取摄像头权限</li>
            <li>点击 <strong>开始识别</strong> 连接后端服务</li>
            <li>将脸部对准摄像头，系统自动识别情感</li>
            <li>右侧面板显示各情感概率分布</li>
          </ol>
        </div>

        <div class="info-card">
          <h3 class="info-title">可识别情感</h3>
          <div class="emotion-legend">
            <div v-for="item in emotions" :key="item.en" class="legend-item">
              <span class="legend-dot" :style="{ background: item.color }"></span>
              <span class="legend-emoji">{{ item.emoji }}</span>
              <span>{{ item.zh }}</span>
            </div>
          </div>
        </div>

        <div class="info-card tech-card">
          <h3 class="info-title">技术栈</h3>
          <ul class="tech-list">
            <li><span class="tech-label">前端</span>Vue 3 + Vite + WebSocket</li>
            <li><span class="tech-label">后端</span>Python + FastAPI</li>
            <li><span class="tech-label">模型</span>DeepFace（可切换人脸检测后端）</li>
            <li><span class="tech-label">传输</span>Base64 JPEG 帧流</li>
          </ul>
        </div>
      </div>

      <section class="detector-section">
        <EmotionDetector />
      </section>
    </main>
  </div>
</template>

<script setup>
import EmotionDetector from './components/EmotionDetector.vue'

const emotions = [
  { en: 'happy',    zh: '开心', emoji: '😄', color: '#22c55e' },
  { en: 'sad',      zh: '悲伤', emoji: '😢', color: '#3b82f6' },
  { en: 'angry',    zh: '愤怒', emoji: '😠', color: '#ff4d4d' },
  { en: 'surprise', zh: '惊讶', emoji: '😲', color: '#f97316' },
  { en: 'fear',     zh: '恐惧', emoji: '😨', color: '#f59e0b' },
  { en: 'disgust',  zh: '厌恶', emoji: '🤢', color: '#a855f7' },
  { en: 'neutral',  zh: '平静', emoji: '😐', color: '#6b7280' },
]
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

/* ── Header ── */
.app-header {
  border-bottom: 1px solid var(--color-border);
  background: rgba(26, 26, 46, 0.8);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo-icon {
  font-size: 2.2rem;
  filter: drop-shadow(0 0 8px rgba(108,99,255,0.6));
}

.logo-title {
  font-size: 1.25rem;
  font-weight: 700;
  background: linear-gradient(135deg, #6c63ff, #00d4ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.logo-sub {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  letter-spacing: 0.05em;
}

.header-badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 600;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

/* ── Main ── */
.app-main {
  flex: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 24px;
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 28px;
  width: 100%;
}

/* ── Sidebar ── */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 18px 20px;
}

.info-title {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-primary);
  margin-bottom: 14px;
}

.info-steps {
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  line-height: 1.5;
}
.info-steps li strong { color: var(--color-text); }

.emotion-legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-emoji { font-size: 1rem; }

.tech-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.83rem;
  color: var(--color-text-muted);
}

.tech-label {
  display: inline-block;
  width: 38px;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--color-accent);
  margin-right: 8px;
  letter-spacing: 0.04em;
}

/* ── Detector section ── */
.detector-section {
  min-width: 0;
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .app-main {
    grid-template-columns: 1fr;
  }
  .sidebar {
    order: 2;
  }
  .detector-section {
    order: 1;
  }
  .header-badges { display: none; }
}
</style>
