"""情绪预测的时序模型定义（GRU 基线）。

输入：过去 window 的定频特征序列 (B, T, F)，F 默认 63（FEA）。
输出：未来 horizon 时刻的 7 类 logits (B, C)。

torch 惰性导入（与 use_train 一致），使后端启动与规则式基线不依赖训练栈。
"""


def build_gru(input_dim: int, num_classes: int, hidden: int = 128, layers: int = 1):
    """构造一个轻量 GRU 分类器。返回 nn.Module。"""
    import torch.nn as nn

    class GRUPredictor(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(input_dim, hidden, num_layers=layers, batch_first=True)
            self.head = nn.Sequential(
                nn.LayerNorm(hidden),
                nn.Linear(hidden, hidden),
                nn.ReLU(inplace=True),
                nn.Dropout(0.2),
                nn.Linear(hidden, num_classes),
            )

        def forward(self, x):                # x: (B, T, F)
            out, _ = self.gru(x)
            return self.head(out[:, -1])     # 取末时刻隐状态 → 未来分类

    return GRUPredictor()
