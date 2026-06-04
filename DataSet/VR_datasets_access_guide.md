# VR 头戴遮挡人脸情感数据集 — 申请指引

戴 VR 头显时上半脸(眼睛、眉毛)被完全遮挡,常规 FER 数据集不适用。
以下是目前公开的、针对该场景的数据集。**两者均需学术身份 + 签署许可协议,无法直接下载。**

---

## 1. EmoHeVRDB(EmojiHeroVR Database)— 首选 ⭐

与本项目模型 `enet_b2_7` 的 **7 类情感完全一致**:
`anger, disgust, fear, happiness, sadness, surprise, neutral`

### 规格
- 采集设备:Meta Quest Pro VR 头显
- 参与者:37 人,1778 个重演情感
- **EmoHeVRDB-SI**(静态图):3,556 张已标注人脸,中央视角 + 45° 侧视,**224×224 jpg**
- **EmoHeVRDB-DI**(动态序列):3,556 段,每段 30 帧 jpg
- **EmoHeVRDB-SFEA**(表情激活):1,727 个 JSON,每个 63 维表情激活向量(多模态用)
- 论文基线:静态 FER 7 类准确率约 69.84%–73.02%

### 申请步骤
1. 阅读官方仓库的数据结构与许可说明:
   https://github.com/thorbenortmann/emoji-hero-vr-database
   （仓库只含代码和文档,**不含数据**）
2. 发邮件至 **thorben.ortmann@haw-hamburg.de**
   - 主题:`EmoHeVRDB Access Request`
   - 附上学术主页链接(机构页面或 Google Scholar)以证明研究者身份
   - 说明需要哪些子集(SI / DI / SFEA)
   - 申请人须隶属研究机构;学生可作为共同研究者列出
3. 收到并签署 EULA(禁止再分发)后,作者提供下载链接 + 解密密码

### 论文
- EmojiHeroVR (2024):https://arxiv.org/abs/2410.03331
- 多模态静态 FER (2025, AIxVR):https://arxiv.org/html/2412.11306v1
- 机构仓库:https://reposit.haw-hamburg.de/handle/20.500.12738/18314

---

## 2. HEADSET — 多模态 3D 备选

多模态(3D 网格/点云/光场/多视角 RGB-D),适合做表情重建、面部重演等 XR 算法评测。
注意:数据是 **3D 格式**,不是即用的 2D FER 图片,体积大、处理复杂。

### 规格
- 参与者:27 人(其中 11 人佩戴 HMD),含一定族裔多样性
- 表情:6 基本情感(happiness, surprise, anger, disgust, sadness, fear)+ neutral
- 模态:带纹理 3D 网格、彩色点云、多视角 RGB-D、Lytro Illum 光场图

### 申请步骤
- 官方页面:https://webpages.tuni.fi/headset
- "公开供研究使用",但需同意许可条款 + 通过伦理知情同意流程
- 论文:https://arxiv.org/html/2402.09107v1

---

## 拿到数据后

EmoHeVRDB-SI 是 224×224 jpg,可直接整理为 torchvision `ImageFolder` 结构
(参考本目录 `prepare_fer2013.py` 的转换逻辑),7 类目录名与现有 FER2013 一致,
可与本地 FER2013 合并或迁移学习。届时告诉我,我帮你写整理/训练脚本。
