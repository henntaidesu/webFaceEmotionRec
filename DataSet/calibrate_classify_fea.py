"""校准规则式仪器 classify_fea：用自评做金标准，给出混淆矩阵 + macro-F1 + 标定魔法数。

为什么必须先做这件事（docs/研究逻辑修复方案_情绪预测线_2026-07-20.md §4）：
classify_fea 同时是标签源、微情感强度显示、predictor 规则基线、闭环调制依据，
却从未验证过。在它有一个已知混淆矩阵之前，所有下游「情绪」数字都没有可信度上界——
若它自身只有 ~0.4 macro-F1，那么任何「预测准确率 0.7」都要打问号。

顺带标定 `neutral = 1 - K * max_other` 里的魔法数 K（当前硬编码 1.6）：
在真数据上扫一遍 K，报告使 macro-F1 最大的取值。

输入：Capture/<subject>/<session>/{fea.csv, selfreport.csv}
      —— 需要**有自评**的会话；自评是唯一独立于 FEA 的真值来源。

用法：
    python DataSet/calibrate_classify_fea.py --root Capture
    python DataSet/calibrate_classify_fea.py --root Capture --tolerance-s 2.0
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prepare_timeline_dataset as P                              # noqa: E402

CLASS_NAMES = P.CLASS_NAMES


def rule_labels_with_k(feats, k):
    """复刻 fea_labels，但把 neutral 的魔法数 K 变成参数，用于扫描标定。"""
    n = len(feats)
    scores = np.zeros((n, len(CLASS_NAMES)), dtype="float32")
    for ci, c in enumerate(CLASS_NAMES):
        if c == "neutral":
            continue
        cols = [P._IDX[name] for name in P._AU_GROUPS[c]]
        scores[:, ci] = feats[:, cols].mean(axis=1)
    max_other = scores.max(axis=1)
    scores[:, CLASS_NAMES.index("neutral")] = np.maximum(0.0, 1.0 - k * max_other)
    return scores.argmax(axis=1)


def metrics(y_true, y_pred):
    c = len(CLASS_NAMES)
    cm = np.zeros((c, c), dtype="int64")
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    tp = cm.diagonal().astype("float64")
    acc = tp.sum() / cm.sum() if cm.sum() else 0.0
    prec = np.divide(tp, cm.sum(axis=0), out=np.zeros(c), where=cm.sum(axis=0) > 0)
    rec = np.divide(tp, cm.sum(axis=1), out=np.zeros(c), where=cm.sum(axis=1) > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(c), where=(prec + rec) > 0)
    return cm, float(acc), float(f1.mean()), prec, rec, f1


def collect(root, tolerance_s):
    """把每条自评与其时刻的 FEA 配对：(feats, 自评标签)。"""
    feats_all, y_all, subj_all = [], [], []
    n_sess = n_rep = 0
    for fea_path in sorted(glob.glob(os.path.join(root, "*", "*", "fea.csv"))):
        sess_dir = os.path.dirname(fea_path)
        subject = os.path.basename(os.path.dirname(sess_dir))
        reports = P.load_selfreport(os.path.join(sess_dir, "selfreport.csv"))
        if not reports:
            continue
        ts, feats = P.load_fea_csv(fea_path)
        if ts is None:
            continue
        n_sess += 1
        tol_ms = tolerance_s * 1000.0
        for r_ts, r_lab in reports:
            n_rep += 1
            i = int(np.argmin(np.abs(ts - r_ts)))
            if abs(int(ts[i]) - r_ts) > tol_ms:      # 自评时刻附近没有 FEA，丢弃
                continue
            feats_all.append(feats[i])
            y_all.append(r_lab)
            subj_all.append(subject)
    return (np.asarray(feats_all, dtype="float32"), np.asarray(y_all, dtype="int64"),
            np.asarray(subj_all), n_sess, n_rep)


def main():
    ap = argparse.ArgumentParser(description="用自评校准 classify_fea 规则")
    ap.add_argument("--root", default="Capture", help="采集根目录")
    ap.add_argument("--tolerance-s", type=float, default=1.0,
                    help="自评时刻与最近 FEA 帧的最大容差秒数")
    ap.add_argument("--out", default=None, help="把结果写入该 JSON 文件")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"[错误] 找不到采集根目录：{args.root}")
        raise SystemExit(2)

    feats, y, subj, n_sess, n_rep = collect(args.root, args.tolerance_s)
    if len(y) == 0:
        print(f"[错误] {args.root} 下没有可用于校准的样本。")
        print("       校准需要**带自评**的会话（selfreport.csv 非空）——自评是唯一")
        print("       独立于 FEA 的真值。当前采集里没有，先补自评再跑本脚本。")
        print(f"       （扫描到 {n_sess} 个含自评的会话、{n_rep} 条自评记录）")
        raise SystemExit(1)

    print(f"样本：{len(y)} 条自评（来自 {n_sess} 个会话、{len(set(subj.tolist()))} 名受试者）")
    dist = np.bincount(y, minlength=len(CLASS_NAMES))
    print("自评类别分布：" + ", ".join(f"{c}={int(dist[i])}" for i, c in enumerate(CLASS_NAMES)))

    pred = rule_labels_with_k(feats, 1.6)
    cm, acc, mf1, prec, rec, f1 = metrics(y, pred)
    print(f"\n=== 当前规则（K=1.6）vs 自评 ===")
    print(f"accuracy={acc:.4f}  macro-F1={mf1:.4f}")
    print(f"{'类别':<10}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>9}")
    for i, c in enumerate(CLASS_NAMES):
        print(f"{c:<10}{prec[i]:>10.3f}{rec[i]:>10.3f}{f1[i]:>10.3f}{int(dist[i]):>9}")
    print("\n混淆矩阵（行=自评真值，列=规则预测）：")
    print("          " + "".join(f"{c[:5]:>7}" for c in CLASS_NAMES))
    for i, c in enumerate(CLASS_NAMES):
        print(f"{c:<10}" + "".join(f"{int(cm[i][j]):>7}" for j in range(len(CLASS_NAMES))))

    # 标定魔法数 K
    print("\n=== 标定 neutral 系数 K（1 - K*max_other）===")
    best = (None, -1.0)
    sweep = []
    for k in np.arange(0.4, 4.01, 0.1):
        _cm, a, f, *_ = metrics(y, rule_labels_with_k(feats, float(k)))
        sweep.append({"k": round(float(k), 2), "acc": round(a, 4), "macro_f1": round(f, 4)})
        if f > best[1]:
            best = (float(k), f)
    print(f"当前 K=1.6 → macro-F1={mf1:.4f}")
    print(f"最优 K={best[0]:.1f} → macro-F1={best[1]:.4f}")
    if best[1] - mf1 > 0.01:
        print(f"[建议] 把 fea_emotion.py 与 prepare_timeline_dataset.py 里的 1.6 改为 {best[0]:.1f}")

    if mf1 < 0.5:
        print(f"\n[警告] 规则本身 macro-F1 仅 {mf1:.3f}。它是全线的标签源与闭环依据，")
        print("       任何基于它的下游『情绪』数字都不会比这个数更可信。")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"n": int(len(y)), "acc": acc, "macro_f1": mf1,
                       "confusion": cm.tolist(), "classes": CLASS_NAMES,
                       "best_k": best[0], "best_macro_f1": best[1], "sweep": sweep},
                      f, ensure_ascii=False, indent=1)
        print(f"\n[已写出] {args.out}")


if __name__ == "__main__":
    main()
