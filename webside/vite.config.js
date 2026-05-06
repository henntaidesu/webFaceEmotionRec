import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 9500,
    proxy: {
      '/ws': {
        target: 'ws://localhost:9501',
        ws: true,
      },
      '/health': {
        target: 'http://localhost:9501',
      },
    },
  },
})
