# Meta Quest Pro 面部数据采集格式规范

用于自采人脸情感数据，**与 EmoHeVRDB 对齐**，可直接被
[train_multimodal_fer_vr.ipynb](train_multimodal_fer_vr.ipynb) 的 `build_manifest()` 读取，
并能与 EmoHeVRDB 合并训练。

> **设备前提**：仅 **Meta Quest Pro** 有内向红外摄像头 + Face Tracking API（Quest 3/3S 没有）。
> 头显**看不到自己的脸**，所以图像必须用**外接相机**拍下半脸/侧脸，与 FEA 用 `sample_id` 同步。

---

## 1. 目录结构

```
<capture_root>/
    train/                      # 划分：train | val | test
        p07_e0123.json          # 标签 + 63 维 blendshape + 图像文件名 + 元数据
        p07_e0123_central.jpg   # 外接相机：正面下半脸，224×224
        p07_e0123_side.jpg      # 可选：45° 侧视，224×224
        ...
    val/
    test/
```

- `sample_id` 命名建议 `p<受试者>_e<样本序号>`，例 `p07_e0123`，保证全局唯一。
- 一个受试者的所有样本只进同一个 split（避免身份泄漏到验证/测试集）。

## 2. 每样本 JSON

```json
{
  "sample_id": "p07_e0123",
  "label": "happiness",
  "image_central": "p07_e0123_central.jpg",
  "image_side": "p07_e0123_side.jpg",
  "blendshapes": [0.0, 0.12, 0.03, "... 共 63 个 0~1 浮点 ..."],
  "blendshape_names": ["BrowLowererL", "BrowLowererR", "..."],
  "device": "Meta Quest Pro",
  "sdk": "Meta XR Movement SDK - Face Tracking (63)",
  "timestamp_ms": 1717400000000
}
```

### 字段约定
- **`label`**：用 EmoHeVRDB 情感名 `anger / disgust / fear / happiness / neutral / sadness / surprise`
  或本项目 7 类 key（`angry / disgust / fear / happy / neutral / sad / surprise`）。
  notebook 的 `EMOHEVR_LABEL_MAP` 会统一映射。
- **`blendshapes`**：**必须按 `OVRFaceExpressions.FaceExpression` 枚举顺序（索引 0~62）**，
  与 EmoHeVRDB 一致——这是两数据集能合并的前提。值域 0~1。
- **`blendshape_names`**：可选，但强烈建议写入，便于核对顺序与 SDK 版本一致。

## 3. 图像规格
- 格式 jpg，分辨率 **224×224**（与 EmoHeVRDB-SI 一致）。
- `central` 正面下半脸为主；`side` 45° 侧视可选（多视角能提点）。
- 外接相机与 FEA 采集**时间对齐**：同一 `sample_id` 的图像与 blendshape 应为同一时刻。

## 4. 动态序列（可选，对应 EmoHeVRDB-DI）
若要做动态 FER：每个 `sample_id` 存连续 30 帧
（`p07_e0123_central_00.jpg ... _29.jpg` + 每帧一个 blendshape，存为 `blendshapes` 的二维数组
 `[30][63]`）。静态模型用不到，先做静态即可。

---

## 5. 63 维 blendshape 顺序参考（OVRFaceExpressions.FaceExpression）

> 以 **Meta XR Movement SDK 的 v1 Face Tracking（63 个表情）** 为准。
> 不同 SDK 版本可能有差异——请以你工程里 `OVRFaceExpressions.FaceExpression.Max` 实际枚举为准，
> 并与 EmoHeVRDB 仓库文档中的顺序逐一核对后再合并数据。

```
 0 BrowLowererL          21 EyesLookUpR           42 LipStretcherL
 1 BrowLowererR          22 InnerBrowRaiserL       43 LipStretcherR
 2 CheekPuffL            23 InnerBrowRaiserR       44 LipSuckLB
 3 CheekPuffR            24 JawDrop                45 LipSuckLT
 4 CheekRaiserL          25 JawSidewaysLeft        46 LipSuckRB
 5 CheekRaiserR          26 JawSidewaysRight       47 LipSuckRT
 6 CheekSuckL            27 JawThrust              48 LipTightenerL
 7 CheekSuckR            28 LidTightenerL          49 LipTightenerR
 8 ChinRaiserB           29 LidTightenerR          50 LipsToward
 9 ChinRaiserT           30 LipCornerDepressorL    51 LowerLipDepressorL
10 DimplerL              31 LipCornerDepressorR    52 LowerLipDepressorR
11 DimplerR              32 LipCornerPullerL       53 MouthLeft
12 EyesClosedL           33 LipCornerPullerR       54 MouthRight
13 EyesClosedR           34 LipFunnelerLB          55 NoseWrinklerL
14 EyesLookDownL         35 LipFunnelerLT          56 NoseWrinklerR
15 EyesLookDownR         36 LipFunnelerRB          57 OuterBrowRaiserL
16 EyesLookLeftL         37 LipFunnelerRT          58 OuterBrowRaiserR
17 EyesLookLeftR         38 LipPressorL            59 UpperLidRaiserL
18 EyesLookRightL        39 LipPressorR            60 UpperLidRaiserR
19 EyesLookRightR        40 LipPuckerL             61 UpperLipRaiserL
20 EyesLookUpL           41 LipPuckerR             62 UpperLipRaiserR
```

## 6. 采集流程建议
1. 受试者戴 Quest Pro，运行采集场景（见 `QuestProFaceCapture.cs`）。
2. 屏幕提示一个目标情感（label），受试者重演该表情。
3. 触发采集：Unity 侧记录 63 维 blendshape + 元数据写 JSON；外接相机同步拍 224×224 图。
4. 每类情感采集足量样本，注意类别均衡（disgust 通常最难、最少，可多采）。
5. 按受试者划分 train/val/test，避免身份泄漏。

采集完成后，在 notebook 中设 `USE_DUMMY_DATA = False`、`EMOHEVRDB_ROOT = <capture_root>`，
`build_manifest()` 已实现为读取本规范格式，直接重跑即可训练。
