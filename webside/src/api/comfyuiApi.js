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

/** 列出服务器端保存的工作流（userdata API，新版 ComfyUI 前端的"工作区"） */
export async function fetchWorkflows() {
  const res = await fetch(`${base()}/userdata?dir=workflows&recurse=true&split=false`)
  if (!res.ok) return []
  const data = await res.json()
  return (Array.isArray(data) ? data : []).filter((f) => typeof f === 'string' && f.endsWith('.json'))
}

/** 读取某个服务器端工作流文件（可能是 UI 格式或 API 格式） */
export async function fetchWorkflow(name) {
  const res = await fetch(`${base()}/userdata/${encodeURIComponent(`workflows/${name}`)}`)
  if (!res.ok) throw new Error(`load workflow failed [${res.status}]`)
  return res.json()
}

/** 获取全部节点定义（UI → API 格式转换需要），结果缓存 */
let objectInfoCache = null
export async function fetchObjectInfo() {
  if (objectInfoCache) return objectInfoCache
  const res = await fetch(`${base()}/object_info`)
  if (!res.ok) throw new Error('object_info failed')
  objectInfoCache = await res.json()
  return objectInfoCache
}

function isWidgetInput(spec) {
  const type = spec?.[0]
  const cfg = spec?.[1] ?? {}
  if (cfg.forceInput) return false
  if (Array.isArray(type)) return true // 下拉枚举
  return ['INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO'].includes(type)
}

const CONTROL_AFTER_GENERATE = ['fixed', 'increment', 'decrement', 'randomize']

/**
 * 将 ComfyUI 的 UI 格式工作流（含 nodes/links）转换为 /prompt 可执行的 API 格式。
 * 覆盖常见节点；遇到未知节点类型时抛错并提示改用 API 格式导出。
 */
export function uiToApiFormat(ui, objectInfo) {
  const nodes = ui.nodes ?? []
  const linkMap = new Map() // link_id → [fromNodeId, fromSlot]
  for (const l of ui.links ?? []) linkMap.set(l[0], [String(l[1]), l[2]])
  const nodeById = new Map(nodes.map((n) => [String(n.id), n]))

  // 穿透 Reroute 节点找到真实数据源
  function resolveSource(nodeId, slot) {
    const node = nodeById.get(nodeId)
    if (node && node.type === 'Reroute') {
      const inLink = node.inputs?.[0]?.link
      if (inLink == null || !linkMap.has(inLink)) return null
      const [fn, fs] = linkMap.get(inLink)
      return resolveSource(fn, fs)
    }
    return [nodeId, slot]
  }

  const SKIP_TYPES = new Set(['Reroute', 'Note', 'MarkdownNote', 'PrimitiveNode'])
  const api = {}

  for (const node of nodes) {
    if (node.mode === 2 || node.mode === 4) continue // 静音 / 旁路节点
    if (SKIP_TYPES.has(node.type)) continue
    const def = objectInfo[node.type]
    if (!def) {
      throw new Error(`未知节点类型 "${node.type}"，请在 ComfyUI 中用「导出（API 格式）」保存该工作流`)
    }

    const inputs = {}
    const linkedNames = new Set()
    for (const inp of node.inputs ?? []) {
      if (inp.link == null) continue
      const src = linkMap.get(inp.link)
      if (!src) continue
      const resolved = resolveSource(src[0], src[1])
      if (resolved) {
        inputs[inp.name] = resolved
        linkedNames.add(inp.name)
      }
    }

    const order = [
      ...Object.entries(def.input?.required ?? {}),
      ...Object.entries(def.input?.optional ?? {}),
    ]
    const wv = node.widgets_values
    if (Array.isArray(wv)) {
      let i = 0
      for (const [name, spec] of order) {
        if (!isWidgetInput(spec)) continue
        if (i >= wv.length) break
        const value = wv[i++]
        if (!linkedNames.has(name)) inputs[name] = value
        // seed 类控件在 widgets_values 中带一个额外的 control_after_generate 值
        if (CONTROL_AFTER_GENERATE.includes(wv[i])) i++
      }
    } else if (wv && typeof wv === 'object') {
      for (const [k, v] of Object.entries(wv)) {
        if (!linkedNames.has(k)) inputs[k] = v
      }
    }

    api[String(node.id)] = { class_type: node.type, inputs }
  }
  return api
}

/**
 * 把页面上的提示词 / 种子注入到 API 格式工作流：
 * - 沿采样器的 positive / negative 连接找到文本编码节点，替换其 text
 * - 重写所有 seed / noise_seed（-1 表示随机）
 */
export function applyPromptOverrides(apiWorkflow, { positive, negative, seed }) {
  for (const node of Object.values(apiWorkflow)) {
    const inp = node.inputs ?? {}
    for (const key of ['seed', 'noise_seed']) {
      if (typeof inp[key] === 'number') {
        inp[key] = seed < 0 ? Math.floor(Math.random() * 999_999_999_999) : seed
      }
    }
    for (const [key, text] of [['positive', positive], ['negative', negative]]) {
      if (!text || !Array.isArray(inp[key])) continue
      const target = apiWorkflow[inp[key][0]]
      if (target && typeof target.inputs?.text === 'string') {
        target.inputs.text = text
      }
    }
  }
  return apiWorkflow
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
  filename_prefix = 'FaceEmotion',
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
      inputs: { filename_prefix, images: ['8', 0] },
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
