"""后端入口：启动 FastAPI 服务（MTCNN + HSEmotion，CUDA 加速）。

实际逻辑已拆分到 src/ 包：
  src/config.py      配置
  src/torch_patch.py PyTorch 2.6 兼容补丁
  src/device.py      CUDA 设备选择
  src/labels.py      情感标签映射
  src/models.py      模型加载
  src/image_utils.py 图像解码
  src/emotion.py     情感识别核心
  src/app.py         FastAPI 路由
"""
import uvicorn

from src import config
from src.app import app

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, reload=False)
