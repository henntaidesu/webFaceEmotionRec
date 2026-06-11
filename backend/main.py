"""后端入口：启动 FastAPI 服务（MTCNN + HSEmotion，CUDA 加速）。

实际逻辑已拆分到 src/ 包，按职责分为三个子包：
  src/config.py                    配置（共用）
  src/use_web/                     前端对接
    app.py                         FastAPI 路由
    image_utils.py                 图像解码
  src/use_model/                   模型使用（推理）
    torch_patch.py                 PyTorch 2.6 兼容补丁
    device.py                      CUDA 设备选择
    labels.py                      情感标签映射
    models.py                      模型加载
    emotion.py                     情感识别核心
    model_registry.py              推理模型注册表
  src/use_train/                   模型训练
    training.py                    训练任务管理
    train_store.py                 训练运行磁盘存储
"""
import uvicorn

from src import config
from src.use_web.app import app

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, reload=False)
