<template>
  <div class="home-main">
    <!-- 左侧：情感识别 -->
    <section class="panel-left">
      <EmotionDetector :locale="locale" />
    </section>

    <!-- 右侧：ComfyUI -->
    <section class="panel-right">
      <ComfyUIPanel :locale="locale" />
    </section>
  </div>
</template>

<script setup>
import EmotionDetector from './EmotionDetector.vue'
import ComfyUIPanel from './ComfyUIPanel.vue'

defineProps({
  locale: { type: Object, required: true },
})
</script>

<style scoped>
.home-main {
  display: grid;
  grid-template-columns: 680px 1fr;
  gap: 24px;
  width: 100%;
  min-height: 0;
}

.panel-left {
  min-width: 0;
}

.panel-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 100px);
}

@media (max-width: 1080px) {
  .home-main {
    grid-template-columns: 1fr;
  }
}
</style>
