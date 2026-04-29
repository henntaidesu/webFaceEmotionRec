# 人脸情感识别 Web 应用

基于 Vue 3 + FastAPI + DeepFace 的实时人脸情感识别系统。

## 项目结构

```
webFaceEmotionRec/
├── backend/
│   ├── main.py           # FastAPI 后端服务
│   └── requirements.txt  # Python 依赖
├── webside/
│   ├── src/
│   │   ├── App.vue                         # 主布局
│   │   ├── components/EmotionDetector.vue  # 核心识别组件
│   │   ├── main.js
│   │   └── style.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 快速启动

### 1. 启动后端

```powershell
cd backend

# 创建虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安装依赖（首次约需几分钟，会下载 DeepFace 模型）
pip install -r requirements.txt

# 启动服务
python main.py
```

后端运行在 `http://localhost:8000`，首次调用时 DeepFace 会自动下载模型文件（约 100MB）。

### 2. 启动前端

```powershell
cd webside

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:5173`，打开浏览器访问即可。

### 3. 使用方法

1. 打开 `http://localhost:5173`
2. 点击「开启摄像头」，浏览器会请求摄像头权限，点击允许
3. 点击「开始识别」，系统自动连接后端并开始实时分析
4. 将脸部对准摄像头，右侧面板实时显示情感概率

## 可识别的情感

| 情感 | 英文 | Emoji |
|------|------|-------|
| 开心 | happy | 😄 |
| 悲伤 | sad | 😢 |
| 愤怒 | angry | 😠 |
| 惊讶 | surprise | 😲 |
| 恐惧 | fear | 😨 |
| 厌恶 | disgust | 🤢 |
| 平静 | neutral | 😐 |

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Vite |
| 前后端通信 | WebSocket（Base64 JPEG 帧流） |
| 后端框架 | FastAPI + uvicorn |
| 情感识别模型 | DeepFace（opencv 检测器） |
| 图像处理 | OpenCV + NumPy |

## 注意事项

- 首次运行后端时，DeepFace 会自动从网络下载模型文件，请确保网络畅通
- 识别帧率默认限制为 5 FPS，可在 `EmotionDetector.vue` 中修改 `TARGET_FPS`
- 光线充足、正面对摄像头时识别效果最佳
- 如遇 WebSocket 连接失败，请确认后端已成功启动在 8000 端口
