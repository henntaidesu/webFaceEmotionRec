# 人脸情感识别 Web 应用（VR 遮挡场景）

面向 **VR 遮挡场景**的实时人脸情绪识别系统：Vue 3 单页应用把摄像头帧经 WebSocket 推给 FastAPI 后端，后端在 GPU 上做 **MTCNN 人脸检测 + 情绪分类**，返回每张脸的 7 类情绪概率。分类器**可插拔**——默认内置 HSEmotion（EfficientNet-B2），也支持**在浏览器里训练自定义模型**并热切换用于推理。

> 研究背景与数据采集计划见 [docs/研究路线图.md](docs/研究路线图.md) 与 [docs/任务书_QuestPro_VR表情数据集采集.md](docs/任务书_QuestPro_VR表情数据集采集.md)。

## 端口与环境

- 后端：**9501**（`0.0.0.0:9501`）
- 前端：**9500**（Vite，strictPort）
- 建议使用 conda 环境 `webFaceEmotionRec`。
- 默认要求 CUDA（`select_device` 无 GPU 会报错）；设 `REQUIRE_CUDA=0` 可退回 CPU。

## 快速启动

```powershell
# 整栈（前后端一起），仓库根目录：
.\start_sys.bat      # Windows，开两个 cmd 窗口
./start.sh           # bash/conda，Ctrl+C 同时停止

# 仅后端
cd backend
python main.py       # 0.0.0.0:9501（薄入口 → src/use_web/app.py）

# 仅前端
cd webside
npm install
npm run dev          # 0.0.0.0:9500
```

### Python 依赖
PyTorch(CUDA) 需**先单独**安装，再装 `backend/requirements.txt`：
```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```
HSEmotion 权重首次运行时联网下载。

## 页面（Vue Router，`/cn/*` 中文、`/jp/*` 日文）

- **情感识别** `/cn` — 摄像头实时识别。
- **模型训练** `/cn/train` — 浏览器内训练自定义 FER 模型（含 VR 遮挡增强）。
- **模型评测** `/cn/eval` — 混淆矩阵 + 逐类指标。
- **图像生成** `/cn/comfyui`（二级菜单）：
  - **生成表情** — ComfyUI 生成「戴 VR 的人做表情」的合成训练图。
  - **VR 刺激图** `/cn/comfyui/stimulus` — 生成 360° 全景情绪刺激图，用于诱导受试者表情；内置场景库 + WebXR 沉浸查看器。

## 可识别的情感（7 类，字母序对齐 `config.TRAIN_CLASSES`）

| 中文 | 英文 | Emoji |
|------|------|-------|
| 愤怒 | angry | 😠 |
| 厌恶 | disgust | 🤢 |
| 恐惧 | fear | 😨 |
| 开心 | happy | 😄 |
| 平静 | neutral | 😐 |
| 悲伤 | sad | 😢 |
| 惊讶 | surprise | 😲 |

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | Vue 3 + Vue Router + Vite；three.js（360 查看器，懒加载） |
| 通信 | WebSocket（Base64 JPEG 帧流，`TARGET_FPS=5`） |
| 后端 | FastAPI + uvicorn，推理跑在 ThreadPoolExecutor |
| 检测 | MTCNN（facenet-pytorch） |
| 分类 | HSEmotion `enet_b2_7`（默认）/ 自训练模型 |
| 训练 | timm efficientnet_b2 或自定义 VRFaceCNN；AMP + AdamW |

## 架构要点

- 前端**不硬编码后端地址**，走 Vite 代理（`/ws`、`/health`、`/api` → 9501；`/comfyui` → 8188）。
- 三套标签空间（模型输出 → 英文键 → 中文显示），映射表在 `backend/src/use_model/labels.py`。
- 两个独立模型存储：`Model/<run_id>/`（训练历史）与 `backend/checkpoints/`（推理注册表）。
- ComfyUI 面板对接**本地** `127.0.0.1:8188`（根目录 `comfyui/` 绘世启动器，`--listen`）。
- 训练数据不入库（见 `.gitignore`），用 `DataSet/` 下脚本本地生成 `ImageFolder` 树。

## 注意事项

- 帧率默认 5 FPS，可在 `EmotionDetector.vue` 改 `TARGET_FPS`。
- WebSocket 连不上时确认后端已在 **9501** 启动。
- ComfyUI 经代理提交任务若报 403，见 `webside/vite.config.js` 中 `/comfyui` 代理对 Origin 头的改写说明。
