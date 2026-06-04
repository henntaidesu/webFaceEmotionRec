# DataSet

人脸情感识别训练数据。**图片数据不入库**（见根目录 `.gitignore`），仅保留准备脚本。
克隆仓库后运行脚本重新生成。

## FER2013

与本项目模型（`enet_b2_7`，7 类）标签完全一致的公开数据集。

- 来源：HuggingFace `Aaryan333/fer2013_train_publicTest_privateTest`（原始 FER2013 三路划分）
- 许可：FER2013 为公开研究数据集（Kaggle ICML 2013 挑战赛）
- 规模：35,887 张 48×48 灰度人脸，约 266 MB（解码为 PNG 后）

### 生成

```powershell
python DataSet/prepare_fer2013.py
```

### 目录结构（torchvision ImageFolder）

```
DataSet/fer2013/
    train/<emotion>/*.png   28,709
    val/<emotion>/*.png      3,589   （原 PublicTest）
    test/<emotion>/*.png     3,589   （原 PrivateTest）
    _raw/                    原始 parquet 缓存
```

7 类目录：`angry  disgust  fear  happy  neutral  sad  surprise`

> 注意：FER2013 类别不均衡（disgust 仅 436 张，happy 7215 张），训练时建议加权采样或类别权重。

### 加载示例

```python
from torchvision import datasets, transforms

tf = transforms.Compose([
    transforms.Grayscale(num_output_channels=3),  # enet_b2 需 3 通道
    transforms.Resize((260, 260)),                # EfficientNet-B2 输入
    transforms.ToTensor(),
])
train = datasets.ImageFolder("DataSet/fer2013/train", transform=tf)
```

## 需手动申请的数据集（无法自动下载）

如需更大/更高质量数据，以下需注册并同意许可后手动下载：

- **AffectNet** — http://mohammadmahoor.com/affectnet/ （学术申请）
- **RAF-DB** — http://www.whdeng.cn/raf/model1.html （申请表）
- **CK+** — https://www.jeffcohn.net/Resources/ （注册）
- **FER+**（FER2013 的改进标注，8 类含 contempt）— https://github.com/microsoft/FERPlus
