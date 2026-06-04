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

## FER+（FER2013 的改进标注）

微软对 FER2013 的多人投票重标注（`microsoft/FERPlus`）。本脚本取投票多数类、
丢弃 contempt/unknown/NF，生成更干净的 **7 类** 版本。已验证与本地 FER2013 行序对齐
（一致率 ~63%，符合 FER+ 论文）。

- 生成：`python DataSet/apply_ferplus.py`（需先有 `fer2013/`）
- 输出：`DataSet/fer2013_plus/{train,val,test}/<emotion>/*.png`（约 28.2k/3.5k/3.5k）
- 特点：neutral 占比显著上升（FER+ 把大量歧义脸归为 neutral），噪声更低。

## RAF-DB（真人脸表情，7 类）

- 来源：HuggingFace `deanngkl/raf-db-7emotions`（**非官方镜像**，~2GB，20,471 张）
- 标签（已核对，字母序）：`0 angry 1 disgust 2 fear 3 happy 4 neutral 5 sad 6 surprise`
- 生成：`python DataSet/prepare_rafdb.py` → `DataSet/rafdb/{train,val}/<emotion>/*.png`（90/10 切分）
- 质量远高于 FER2013，适合增强图像分支。

## AffectNet（no-contempt，7 类）

- 来源：HuggingFace `deanngkl/affectnet_no_contempt`（**非官方镜像**，~8GB，27,823 张）
- 标签（ClassLabel 元数据）：`0 angry 1 disgust 2 fear 3 happy 4 neutral 5 sad 6 surprise`
- 生成：`python DataSet/prepare_affectnet.py`（先 `snapshot_download` 下 parquet 到 `affectnet/_raw/`）
  → `DataSet/affectnet/{train,val}/<emotion>/*.jpg`（统一 resize 224×224，90/10 切分）

> ⚠️ **许可提示**：RAF-DB / AffectNet 官方均要求注册并签许可。上面两个 HuggingFace 镜像绕过了
> 授权，属许可灰色地带——仅供个人研究。如需合规，请走官方申请：
> AffectNet http://mohammadmahoor.com/affectnet/ ；RAF-DB http://www.whdeng.cn/raf/model1.html

## VR 头戴遮挡数据集（需学术申请）

戴 VR 头显的真实人脸情感数据集**无法自动下载**，见 `VR_datasets_access_guide.md`：
- **EmoHeVRDB**（Meta Quest Pro，7 类 + 63 维 FEA）— 学术邮件 + 签 EULA
- **HEADSET**（多模态 3D）— 许可同意

自采 Quest Pro 数据见 `quest_pro_capture_spec.md` + `QuestProFaceCapture.cs`。

## 其他需手动申请

- **CK+** — https://www.jeffcohn.net/Resources/ （注册）
- **JAFFE** — https://zenodo.org/record/3451524 （注册）
