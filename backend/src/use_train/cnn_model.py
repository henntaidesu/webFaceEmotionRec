"""自定义 CNN 情感识别网络（面向 VR 头显遮挡场景）。

VRFaceCNN：从零搭建的残差 CNN（SE 通道注意力 + 空间注意力）。
配合 VRMask 遮挡增强 —— 训练时随机遮住人脸裁剪图的眼部横带，
模拟佩戴 VR 头显后上半脸不可见的情况，迫使网络从嘴部、下颌等
可见区域学习情感特征；验证集使用固定遮挡评估，因此训练页展示的
val_acc / macro_F1 直接反映佩戴 VR 设备时的正面情感识别精度。

本模块顶层 import torch，调用方（training.py / model_registry.py）
均在使用时才导入本模块，不影响后端启动速度。
"""
import random

import torch
import torch.nn as nn

# 训练/推理两端共用的自定义主干标识（config.TRAIN_BACKBONE_CHOICES 之一）
VR_CNN_ID = "vr_cnn"


class SEBlock(nn.Module):
    """通道注意力（Squeeze-and-Excitation）：按信息量重新加权各通道。"""

    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        hidden = max(channels // reduction, 8)
        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1), nn.Flatten(),
            nn.Linear(channels, hidden), nn.ReLU(inplace=True),
            nn.Linear(hidden, channels), nn.Sigmoid(),
        )

    def forward(self, x):
        return x * self.fc(x).unsqueeze(-1).unsqueeze(-1)


class SpatialAttention(nn.Module):
    """空间注意力：抑制被遮挡区域、突出可见区域（嘴部/下半脸）的响应。"""

    def __init__(self, kernel_size: int = 7):
        super().__init__()
        self.conv = nn.Conv2d(2, 1, kernel_size, padding=kernel_size // 2, bias=False)

    def forward(self, x):
        avg = x.mean(dim=1, keepdim=True)
        mx, _ = x.max(dim=1, keepdim=True)
        return x * torch.sigmoid(self.conv(torch.cat([avg, mx], dim=1)))


class ResidualBlock(nn.Module):
    """两层 3×3 卷积 + SE 的残差块；stride=2 时同时下采样。"""

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            SEBlock(out_ch),
        )
        self.skip = nn.Identity() if stride == 1 and in_ch == out_ch else nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 1, stride=stride, bias=False),
            nn.BatchNorm2d(out_ch),
        )
        self.act = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.act(self.body(x) + self.skip(x))


class VRFaceCNN(nn.Module):
    """残差 CNN：stem(7×7/2 + maxpool) → 4 个 stage(64/128/256/512) → GAP → 分类头。

    后两个 stage 末尾接空间注意力，使深层特征聚焦未被头显遮挡的区域。
    分类头命名为 classifier，与 timm 模型保持一致。
    约 11.3M 参数（ResNet18 量级），从零训练。
    """

    def __init__(self, num_classes: int = 7, dropout: float = 0.3):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False),
            nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.MaxPool2d(3, stride=2, padding=1),
        )
        self.stages = nn.Sequential(
            self._stage(64, 64, stride=1),
            self._stage(64, 128, stride=2),
            self._stage(128, 256, stride=2, attn=True),
            self._stage(256, 512, stride=2, attn=True),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(512, num_classes)

    @staticmethod
    def _stage(in_ch: int, out_ch: int, stride: int, attn: bool = False) -> nn.Sequential:
        layers: list[nn.Module] = [
            ResidualBlock(in_ch, out_ch, stride=stride),
            ResidualBlock(out_ch, out_ch),
        ]
        if attn:
            layers.append(SpatialAttention())
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.stages(self.stem(x))
        x = self.pool(x).flatten(1)
        return self.classifier(self.dropout(x))


class VRMask:
    """模拟 VR 头显遮挡：遮住人脸裁剪图的眼部横带。

    作用于 ToTensor 之后、Normalize 之前的 [C,H,W] 张量（值域 0~1）。
    train=True：以概率 p 随机遮挡，位置/高度/填充（黑/灰/噪声）随机抖动，
        保留部分未遮挡样本，使模型同时适配戴与不戴头显两种场景。
    train=False：固定遮挡（高度 12%~55%，黑色），用于验证集 ——
        使 val 指标直接反映佩戴 VR 时的识别精度。
    """

    def __init__(self, train: bool, p: float = 0.8):
        self.train = train
        self.p = p

    def __call__(self, x):
        _, h, _ = x.shape
        if self.train:
            if random.random() > self.p:
                return x
            top = random.uniform(0.05, 0.20)
            bottom = random.uniform(0.45, 0.62)
            fill = random.choice(("black", "gray", "noise"))
        else:
            top, bottom, fill = 0.12, 0.55, "black"
        y1, y2 = int(top * h), int(bottom * h)
        if fill == "noise":
            x[:, y1:y2, :] = torch.rand_like(x[:, y1:y2, :])
        elif fill == "gray":
            x[:, y1:y2, :] = random.uniform(0.05, 0.35)
        else:
            x[:, y1:y2, :] = 0.0
        return x


def create_model(backbone: str, num_classes: int, pretrained: bool = False) -> nn.Module:
    """统一建模入口：vr_cnn → 自定义网络（从零训练）；其余 → timm。"""
    if backbone == VR_CNN_ID:
        return VRFaceCNN(num_classes=num_classes)
    import timm
    return timm.create_model(backbone, pretrained=pretrained, num_classes=num_classes)
