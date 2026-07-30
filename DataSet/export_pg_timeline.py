"""把 Postgres 里的 FEA 时间轴导出成 Capture/ 目录结构，接回既有切窗流水线。

背景：项目里有两条采集链路，数据互不相通——
  链路 A（刺激页 / 情感偏好页）：头显 POST /api/fea → affect_fea 表（Postgres）
  链路 B（Unity SessionUploader）：POST /api/session/ingest → Capture/*/*/fea.csv
而 DataSet/prepare_timeline_dataset.py 只读链路 B 的 CSV，于是链路 A 已经采到的数据
无法进入训练。本脚本把 A 导成 B 的格式，让两条链路汇合。

导出结构（与 use_capture/session_store.py 落盘格式一致）：
    <out>/<subject_id>/<session_id>/
        meta.json      会话元信息（标注 source=postgres）
        fea.csv        timestamp_ms, f0..f62      ← affect_fea（仅 fea 非空的行）
        stimulus.csv   onset_ms, image_id, target_emotion, offset_ms, dwell_ms
                                                  ← affect_image（供 block-level 分组）
        selfreport.csv 表头占位（PG 链路没有逐张自评，见下方警告）

用法：
    python DataSet/export_pg_timeline.py --out Capture
    python DataSet/export_pg_timeline.py --out Capture --subject p01 --dry-run

注意：PG 链路没有采集自评（selfreport），导出的 selfreport.csv 只有表头。
因此这批数据**只能**配合 --label-source fea 使用，而那是与 X 同源的循环标签，
不能作为研究结论。要用于正式训练，需在采集端补上自评。脚本会显式警告。
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.src import config                                    # noqa: E402
from backend.src.db_manager import DatabaseManager                # noqa: E402

FEA_DIM = config.FEA_DIM
_FEA_HEADER = ["timestamp_ms"] + [f"f{i}" for i in range(FEA_DIM)]
_STIMULUS_HEADER = ["onset_ms", "image_id", "target_emotion", "offset_ms", "dwell_ms"]
_SELFREPORT_HEADER = ["timestamp_ms", "image_id", "label7", "valence", "arousal"]


def _safe(s, fallback):
    import re
    s = re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))
    return s or fallback


def fetch_sessions(db, subject=None):
    sql = ('SELECT s.session_id, s.subject_id, s.started_ms, s.stopped_ms '
           'FROM affect_session s')
    params = ()
    if subject:
        sql += ' WHERE s.subject_id = %s'
        params = (subject,)
    sql += ' ORDER BY s.started_ms'
    cols = ["session_id", "subject_id", "started_ms", "stopped_ms"]
    return [dict(zip(cols, r)) for r in db.execute_query(sql, params)]


def parse_vector(v):
    """pgvector 列 → float list。

    本项目没有 register_vector，psycopg 把 vector 原样当字符串返回（形如 '[0.1,0.2,…]'），
    直接 list() 会把它拆成单个字符。这里同时兼容字符串与已注册成序列的两种情况。
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lstrip("[").rstrip("]")
        if not s:
            return None
        try:
            return [float(x) for x in s.split(",")]
        except ValueError:
            return None
    try:
        return [float(x) for x in v]
    except (TypeError, ValueError):
        return None


def fetch_fea(db, session_id):
    """affect_fea 中该会话的逐帧 FEA（跳过 fea 为 NULL 的行——那些只有情绪没有原始信号）。"""
    rows = db.execute_query(
        'SELECT ts_ms, fea FROM affect_fea '
        'WHERE session_id = %s AND fea IS NOT NULL ORDER BY ts_ms', (session_id,))
    out, bad = [], 0
    for ts, fea in rows:
        vec = parse_vector(fea)
        if not vec or len(vec) != FEA_DIM:
            bad += 1
            continue
        out.append((int(ts), vec))
    if bad:
        print(f"  [警告] {session_id}: 跳过 {bad} 行维度异常/无法解析的 FEA")
    return out


def fetch_images(db, session_id):
    rows = db.execute_query(
        'SELECT id, ts_ms, dominant FROM affect_image '
        'WHERE session_id = %s ORDER BY ts_ms', (session_id,))
    return [{"id": r[0], "ts_ms": int(r[1]), "dominant": r[2]} for r in rows]


def write_session(out_root, sess, fea_rows, images, dry_run=False):
    subject = _safe(sess["subject_id"], "anon")
    session_id = _safe(sess["session_id"], "s0")
    sess_dir = os.path.join(out_root, subject, session_id)
    if dry_run:
        return sess_dir, len(fea_rows), len(images)

    os.makedirs(sess_dir, exist_ok=True)
    with open(os.path.join(sess_dir, "fea.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(_FEA_HEADER)
        for ts, vec in fea_rows:
            w.writerow([ts] + [round(float(x), 5) for x in vec])

    # 刺激块：一张图的展示区间 = 本条 ts → 下一条 ts
    with open(os.path.join(sess_dir, "stimulus.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(_STIMULUS_HEADER)
        for i, im in enumerate(images):
            nxt = images[i + 1]["ts_ms"] if i + 1 < len(images) else None
            w.writerow([im["ts_ms"], f"img{im['id']}", im["dominant"] or "",
                        nxt if nxt is not None else "",
                        (nxt - im["ts_ms"]) if nxt is not None else ""])

    # PG 链路没有自评，只写表头占位（prepare 脚本会因无标签而跳过 selfreport 模式）
    with open(os.path.join(sess_dir, "selfreport.csv"), "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(_SELFREPORT_HEADER)

    meta = {
        "subject_id": subject,
        "session_id": session_id,
        "created_ms": sess.get("started_ms"),
        "ended_ms": sess.get("stopped_ms"),
        "source": "postgres",       # 标明这批来自 PG 链路，不是头显直采的 CSV
        "fea_dim": FEA_DIM,
        "emotion_order": config.TRAIN_CLASSES,
        "counts": {"fea": len(fea_rows), "stimulus": len(images), "selfreport": 0},
        "note": "由 DataSet/export_pg_timeline.py 从 affect_fea/affect_image 导出；无自评标签",
    }
    with open(os.path.join(sess_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return sess_dir, len(fea_rows), len(images)


def main():
    ap = argparse.ArgumentParser(description="Postgres FEA 时间轴 → Capture/ 目录结构")
    ap.add_argument("--out", default=str(config.CAPTURE_DIR),
                    help="导出根目录（默认 config.CAPTURE_DIR，即 Capture/）")
    ap.add_argument("--subject", default=None, help="只导出该受试者")
    ap.add_argument("--min-frames", type=int, default=100,
                    help="FEA 帧数少于该值的会话跳过（默认 100）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    args = ap.parse_args()

    db = DatabaseManager()
    if not db.is_configured():
        print("[错误] Postgres 未配置（系统设置页填 host，或设 POSTGRES_HOST）。")
        raise SystemExit(2)

    sessions = fetch_sessions(db, args.subject)
    if not sessions:
        print("[错误] affect_session 里没有会话" + (f"（subject={args.subject}）" if args.subject else ""))
        raise SystemExit(2)

    total_f = total_i = written = skipped = 0
    for sess in sessions:
        fea_rows = fetch_fea(db, sess["session_id"])
        if len(fea_rows) < args.min_frames:
            print(f"[跳过] {sess['subject_id']}/{sess['session_id']}：仅 {len(fea_rows)} 帧 FEA")
            skipped += 1
            continue
        images = fetch_images(db, sess["session_id"])
        d, nf, ni = write_session(args.out, sess, fea_rows, images, args.dry_run)
        span = (fea_rows[-1][0] - fea_rows[0][0]) / 1000.0
        rate = (len(fea_rows) - 1) / span if span > 0 else 0
        print(f"[{'预览' if args.dry_run else '导出'}] {d}：{nf} 帧 FEA "
              f"（{span:.0f}s，约 {rate:.1f}Hz）, {ni} 张刺激图")
        total_f += nf
        total_i += ni
        written += 1

    print(f"\n[完成] {written} 个会话，{total_f} 帧 FEA，{total_i} 张刺激图"
          + ("（dry-run，未写盘）" if args.dry_run else f" → {args.out}"))
    if skipped:
        print(f"[提示] 跳过 {skipped} 个帧数不足的会话（--min-frames {args.min_frames}）")
    if written:
        print("\n[警告] PG 链路没有采集自评（selfreport.csv 为空），这批数据只能配合")
        print("       --label-source fea 使用，而那是与 X 同源的循环标签，不能作为研究结论。")
        print("       正式训练前请在采集端补上自评。")
        print(f"\n下一步：python DataSet/prepare_timeline_dataset.py --root {args.out} \\")
        print("            --out DataSet/timeline_sliced --label-source selfreport")
    raise SystemExit(0 if written else 1)


if __name__ == "__main__":
    main()
