/** ComfyUI 服务地址（开发环境经 Vite 代理为 /comfyui） */
export const COMFYUI_HOST =
  import.meta.env.VITE_COMFYUI_HOST || '127.0.0.1:8188'

/** API / 页面基路径：开发默认走代理，避免跨域 */
export const COMFYUI_BASE =
  import.meta.env.VITE_COMFYUI_BASE || '/comfyui'

export const COMFYUI_DIRECT_URL = `http://${COMFYUI_HOST}/`
