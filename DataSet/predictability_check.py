"""可预测性预检：未来的情绪，真的能从过去的 FEA 里预测出来吗？

对应 docs/研究逻辑修复方案_情绪预测线_2026-07-20.md §0——**在写任何模型之前先做**，
因为它能在投入训练前就否掉一个 horizon，避免「训了个打不过 persistence 的 GRU」。

算两个量（标签必须用自评，不能用规则式 fea 标签，否则 y=f(X) 循环）：
  I(y_now ; y_future)                  光靠「现在」能解释多少「未来」= persistence 的信息上限
  I(FEA_past ; y_future | y_now)       在「现在」之外，过去那段 FEA **额外**贡献了多少

判据：条件互信息 ≈ 0 → 该 horizon 上没有可学信号，应缩短 horizon 或更换构念；
      显著 > 0 才值得继续训模型。

FEA_past 是连续高维（seq_len×63），互信息无法直接估。这里把它压成低维离散代理：
对窗口做时间平均 + 末尾差分（趋势），取前若干主成分后等频分箱。这是有偏的下界估计——
**估出来的条件互信息偏小**，所以「条件互信息 ≈ 0」只能说明这套代理没抓到信号，
不能证明信号绝对不存在；反之若它已经 > 0，则信号确实存在。结论按此方向解读。

用法（先跑 prepare_timeline_dataset.py 产出 all.npz）：
    python DataSet/predictability_check.py --dataset DataSet/timeline_sliced
    python DataSet/predictability_check.py --dataset DataSet/timeline_sliced --bins 6 --pcs 3
"""
import argparse
import json
import os

import numpy as np


def entropy(counts):
    """离散分布的香农熵（bit）。"""
    c = np.asarray(counts, dtype="float64")
    c = c[c > 0]
    if c.size == 0:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def mutual_info(a, b):
    """两个离散变量的互信息 I(a;b) = H(a) + H(b) − H(a,b)（bit）。"""
    a = np.asarray(a)
    b = np.asarray(b)
    _ua, ia = np.unique(a, return_inverse=True)
    _ub, ib = np.unique(b, return_inverse=True)
    joint = np.zeros((ia.max() + 1, ib.max() + 1), dtype="int64")
    np.add.at(joint, (ia, ib), 1)
    h_a = entropy(joint.sum(axis=1))
    h_b = entropy(joint.sum(axis=0))
    h_ab = entropy(joint.ravel())
    return max(0.0, h_a + h_b - h_ab)      # 估计噪声可能给出极小负值，夹到 0


def cond_mutual_info(x, y, z):
    """I(x;y|z) = Σ_z p(z) I(x;y | Z=z)（bit），全部离散。"""
    z = np.asarray(z)
    total = len(z)
    out = 0.0
    for zv in np.unique(z):
        m = z == zv
        if m.sum() < 2:
            continue
        out += (m.sum() / total) * mutual_info(np.asarray(x)[m], np.asarray(y)[m])
    return float(out)


def permutation_null(fn, x, y, z=None, n=200, seed=0):
    """打乱 y 重算，给出零假设分布 → 均值/95 分位/经验 p 值。"""
    rng = np.random.default_rng(seed)
    obs = fn(x, y) if z is None else fn(x, y, z)
    null = np.empty(n)
    y = np.asarray(y)
    for i in range(n):
        yp = rng.permutation(y)
        null[i] = fn(x, yp) if z is None else fn(x, yp, z)
    p = float((null >= obs).sum() + 1) / (n + 1)
    return obs, float(null.mean()), float(np.percentile(null, 95)), p


def fea_proxy(X, n_pcs, bins, seed=0):
    """(N, seq_len, 63) → (N,) 离散代理码。

    特征 = 各维时间均值 ⊕ (后 1/3 均值 − 前 1/3 均值)（趋势）→ PCA 降维 → 等频分箱 → 组合成码。
    """
    n, seq, dim = X.shape
    k = max(1, seq // 3)
    mean = X.mean(axis=1)
    trend = X[:, -k:, :].mean(axis=1) - X[:, :k, :].mean(axis=1)
    F = np.concatenate([mean, trend], axis=1)
    F = F - F.mean(axis=0, keepdims=True)
    # SVD 取主成分（样本数可能小于特征数，用 economy SVD）
    U, S, _Vt = np.linalg.svd(F, full_matrices=False)
    pcs = U[:, :n_pcs] * S[:n_pcs]
    codes = np.zeros(n, dtype="int64")
    for j in range(pcs.shape[1]):
        col = pcs[:, j]
        # 等频分箱：分位数边界，避免长尾把样本挤进一个桶
        edges = np.quantile(col, np.linspace(0, 1, bins + 1)[1:-1])
        codes = codes * bins + np.searchsorted(edges, col)
    return codes


def main():
    ap = argparse.ArgumentParser(description="FEA→未来情绪 的可预测性预检（互信息）")
    ap.add_argument("--dataset", required=True, help="prepare_timeline_dataset.py 的输出目录")
    ap.add_argument("--split", default="all", help="用哪个 npz（默认 all）")
    ap.add_argument("--bins", type=int, default=5, help="每个主成分的等频分箱数")
    ap.add_argument("--pcs", type=int, default=2, help="取几个主成分做代理")
    ap.add_argument("--perms", type=int, default=200, help="置换检验次数")
    ap.add_argument("--out", default=None, help="结果写入该 JSON")
    args = ap.parse_args()

    ddir = args.dataset
    npz = os.path.join(ddir, f"{args.split}.npz")
    if not os.path.exists(npz):
        print(f"[错误] 找不到 {npz}（先跑 DataSet/prepare_timeline_dataset.py）")
        raise SystemExit(2)
    meta = {}
    mp = os.path.join(ddir, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)

    if meta.get("label_source") == "fea":
        print("[拒绝] 该数据集用的是规则式 fea 标签，与 X 同源（y=f(X)），")
        print("       互信息必然虚高，预检没有意义。请用 --label-source selfreport 重切。")
        raise SystemExit(2)

    z = np.load(npz, allow_pickle=False)
    X, y = z["X"].astype("float32"), z["y"].astype("int64")
    if "y_now" not in z.files:
        print("[错误] npz 缺 y_now（窗末当前标签），无法算条件互信息。请用新版切窗脚本重切。")
        raise SystemExit(2)
    y_now = z["y_now"].astype("int64")

    print(f"数据集：{npz}")
    print(f"样本 {len(y)} | window_s={meta.get('window_s')} horizon_s={meta.get('horizon_s')} "
          f"rate_hz={meta.get('rate_hz')} 标签源={meta.get('label_source')}")
    if len(y) < 200:
        print(f"[警告] 仅 {len(y)} 个样本，互信息估计会严重偏高且不稳，结论仅供参考。")

    h_future = entropy(np.bincount(y))
    print(f"\nH(y_future) = {h_future:.4f} bit（上限：7 类均匀时 log2(7)={np.log2(7):.4f}）")

    # 1) persistence 的信息上限
    mi_now, nm, n95, p_now = permutation_null(mutual_info, y_now, y, n=args.perms)
    print(f"\n[1] I(y_now ; y_future) = {mi_now:.4f} bit  "
          f"（占 H 的 {mi_now / h_future * 100 if h_future else 0:.1f}%）")
    print(f"    置换零假设 均值={nm:.4f} 95%分位={n95:.4f} p={p_now:.4f}")

    # 2) 过去 FEA 的额外贡献
    codes = fea_proxy(X, args.pcs, args.bins)
    n_states = len(np.unique(codes))
    print(f"\n[2] FEA 代理：{args.pcs} 主成分 × {args.bins} 分箱 → {n_states} 个状态")
    cmi, cnm, cn95, p_cmi = permutation_null(cond_mutual_info, codes, y, y_now, n=args.perms)
    print(f"    I(FEA_past ; y_future | y_now) = {cmi:.4f} bit")
    print(f"    置换零假设 均值={cnm:.4f} 95%分位={cn95:.4f} p={p_cmi:.4f}")

    # 结论
    print("\n=== 判据 ===")
    sig = cmi > cn95 and p_cmi < 0.05
    if sig:
        print(f"条件互信息 {cmi:.4f} bit 超过置换 95% 分位 {cn95:.4f}（p={p_cmi:.4f}）：")
        print("→ 在「当前标签」之外，过去的 FEA 确实还携带关于未来的信息。值得训模型。")
        print("  但注意：有信号 ≠ 模型能超过 persistence，仍须与三基线同表对比。")
    else:
        print(f"条件互信息 {cmi:.4f} bit 未超过置换 95% 分位 {cn95:.4f}（p={p_cmi:.4f}）：")
        print(f"→ 这套代理没能在 horizon={meta.get('horizon_s')}s 上找到「现在」之外的额外信号。")
        print("  建议先缩短 horizon 再试，或按旧报告 §1 更换构念（如改预测『块级转变』）。")
        print("  注意本估计是下界，不能据此断言信号绝对不存在；但也别急着训模型。")
    print(f"\n参考：persistence 能拿到的信息占 H(y_future) 的 "
          f"{mi_now / h_future * 100 if h_future else 0:.1f}%，这就是模型要超越的起点。")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"n": int(len(y)), "h_future": h_future,
                       "mi_now": mi_now, "mi_now_p": p_now,
                       "cmi": cmi, "cmi_null_p95": cn95, "cmi_p": p_cmi,
                       "significant": bool(sig), "bins": args.bins, "pcs": args.pcs,
                       "window_s": meta.get("window_s"), "horizon_s": meta.get("horizon_s"),
                       "label_source": meta.get("label_source")}, f, ensure_ascii=False, indent=1)
        print(f"[已写出] {args.out}")


if __name__ == "__main__":
    main()
