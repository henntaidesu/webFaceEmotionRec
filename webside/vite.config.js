import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const comfyTarget = env.VITE_COMFYUI_PROXY_TARGET || 'http://192.168.123.45:8188'

  return {
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
        '/comfyui': {
          target: comfyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/comfyui/, ''),
          ws: true,
        },
      },
    },
  }
})
