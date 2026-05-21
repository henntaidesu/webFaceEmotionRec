import { COMFYUI_BASE, COMFYUI_HOST } from '../config/comfyui.js'

function base() {
  return COMFYUI_BASE.replace(/\/$/, '')
}

/** 检测 ComfyUI 是否在线 */
export async function checkOnline() {
  try {
    const res = await fetch(`${base()}/system_stats`, {
      signal: AbortSignal.timeout(5000),
    })
    return res.ok
  } catch {
    return false
  }
}

/** 获取可用的 Checkpoint 模型列表 */
export async function fetchCheckpoints() {
  const res = await fetch(`${base()}/object_info/CheckpointLoaderSimple`)
  if (!res.ok) throw new Error('fetch checkpoints failed')
  const data = await res.json()
  return data?.CheckpointLoaderSimple?.input?.required?.ckpt_name?.[0] ?? []
}

/** 提交生成任务，返回 { prompt_id } */
export async function queuePrompt(clientId, workflow) {
  const res = await fetch(`${base()}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: clientId, prompt: workflow }),
  })
  if (!res.ok) {
    const txt = await res.text().catch(() => '')
    throw new Error(`queue failed [${res.status}]: ${txt}`)
  }
  return res.json()
}

/** 查询历史记录，获取生成结果 */
export async function getHistory(promptId) {
  const res = await fetch(`${base()}/history/${promptId}`)
  if (!res.ok) throw new Error('history failed')
  return res.json()
}

/** 拼接图像查看 URL */
export function imageUrl(filename, subfolder = '', type = 'output') {
  const p = new URLSearchParams({ filename, subfolder, type, rand: Date.now() })
  return `${base()}/view?${p}`
}

/** 生成随机 clientId */
export function makeClientId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

/** 建立进度 WebSocket */
export function openProgressWS(clientId) {
  const b = base()
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = b.startsWith('http')
    ? b.replace(/^http/, 'ws') + `/ws?clientId=${clientId}`
    : `${wsProto}//${location.host}${b}/ws?clientId=${clientId}`
  return new WebSocket(wsUrl)
}

/**
 * 构建标准 txt2img 工作流 JSON
 * 对应节点：CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage
 *           → KSampler → VAEDecode → SaveImage
 */
export function buildTxt2ImgWorkflow({
  positive,
  negative,
  checkpoint,
  steps,
  cfg,
  width,
  height,
  sampler,
  scheduler,
  seed,
}) {
  const resolvedSeed =
    seed < 0 ? Math.floor(Math.random() * 999_999_999_999) : seed

  return {
    '4': {
      class_type: 'CheckpointLoaderSimple',
      inputs: { ckpt_name: checkpoint },
    },
    '6': {
      class_type: 'CLIPTextEncode',
      inputs: { text: positive, clip: ['4', 1] },
    },
    '7': {
      class_type: 'CLIPTextEncode',
      inputs: { text: negative, clip: ['4', 1] },
    },
    '5': {
      class_type: 'EmptyLatentImage',
      inputs: { width, height, batch_size: 1 },
    },
    '3': {
      class_type: 'KSampler',
      inputs: {
        seed: resolvedSeed,
        steps,
        cfg,
        sampler_name: sampler,
        scheduler,
        denoise: 1.0,
        model: ['4', 0],
        positive: ['6', 0],
        negative: ['7', 0],
        latent_image: ['5', 0],
      },
    },
    '8': {
      class_type: 'VAEDecode',
      inputs: { samples: ['3', 0], vae: ['4', 2] },
    },
    '9': {
      class_type: 'SaveImage',
      inputs: { filename_prefix: 'FaceEmotion', images: ['8', 0] },
    },
  }
}

export const SAMPLERS = [
  'euler',
  'euler_ancestral',
  'heun',
  'dpm_2',
  'dpm_2_ancestral',
  'dpmpp_2s_ancestral',
  'dpmpp_sde',
  'dpmpp_2m',
  'dpmpp_2m_sde',
  'dpmpp_3m_sde',
  'lcm',
  'ddim',
  'uni_pc',
]

export const SCHEDULERS = [
  'normal',
  'karras',
  'exponential',
  'sgm_uniform',
  'simple',
  'ddim_uniform',
]

export { COMFYUI_HOST }
