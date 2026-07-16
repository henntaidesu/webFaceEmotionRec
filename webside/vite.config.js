import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const comfyTarget = env.VITE_COMFYUI_PROXY_TARGET || 'http://127.0.0.1:8188'

  // 公网访问（路由器端口映射到公网 IP/DDNS 时 Host 不固定）：默认放行任意 Host。
  // 如需收紧，设环境变量 VITE_ALLOWED_HOSTS（逗号分隔的域名/IP），例：
  //   VITE_ALLOWED_HOSTS=nas.makurochan.com,1.2.3.4
  const allowedHosts = env.VITE_ALLOWED_HOSTS
    ? env.VITE_ALLOWED_HOSTS.split(',').map((s) => s.trim()).filter(Boolean)
    : true

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 9500,
      strictPort: true,
      allowedHosts,
      proxy: {
        '/ws': {
          target: 'ws://localhost:9501',
          ws: true,
        },
        '/health': {
          target: 'http://localhost:9501',
        },
        '/api': {
          target: 'http://localhost:9501',
        },
        '/comfyui': {
          target: comfyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/comfyui/, ''),
          ws: true,
          // ComfyUI 的 origin_only_middleware 会拒绝 Host≠Origin 的写请求（POST /prompt 返回 403）。
          // changeOrigin 只改了 Host，这里把 Origin 也改成目标地址，两者一致即可通过校验。
          configure: (proxy) => {
            const setOrigin = (proxyReq) => proxyReq.setHeader('origin', comfyTarget)
            proxy.on('proxyReq', setOrigin)
            proxy.on('proxyReqWs', setOrigin)
          },
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 9500,
      strictPort: true,
      allowedHosts,
    },
  }
})
