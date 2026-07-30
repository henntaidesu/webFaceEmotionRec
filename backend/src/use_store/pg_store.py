"""「情感偏好生成」的存储服务层（构建在对象模式 db_manager 之上）。

app.py 的 /api/affect/* 端点调用这里；真正的建库/建表/改表与 CRUD 由
backend/src/db_manager（对象模式，参考 CsWeaponManager 的 db_manager）完成。
Postgres 连接参数取自 settings_store（conf.ini [postgres]），系统设置页改完即时生效。

is_configured / 连接失败 / 未配置 一律抛 RuntimeError，由路由层转 HTTP 错误。
"""
import logging
import threading
import time

from .. import config
from ..db_manager import (
    AffectFeaModel,
    AffectImageModel,
    AffectSelfReportModel,
    AffectSessionModel,
    DatabaseManager,
    get_db_manager,
)

FEA_DIM = config.FEA_DIM
EMOTION_ORDER = config.TRAIN_CLASSES  # angry disgust fear happy neutral sad surprise（7）

logger = logging.getLogger(__name__)
_initialized = False
_init_lock = threading.Lock()   # 防并发首请求同时跑建库/建表 DDL


def is_configured() -> bool:
    return DatabaseManager().is_configured()


def _ensure_init() -> None:
    """首次使用时自动建库 + 建表（幂等）。"""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        if not get_db_manager().initialize_database():
            raise RuntimeError("数据库初始化失败（建库/建表未全部成功）")
        _initialized = True


def test_connection() -> dict:
    """连通性 + 建库/建表：返回 {server_version}。失败抛 RuntimeError。"""
    if not is_configured():
        raise RuntimeError("Postgres host 未配置")
    global _initialized
    if not get_db_manager().initialize_database():
        raise RuntimeError("数据库初始化失败")
    _initialized = True
    return {"server_version": DatabaseManager().server_version()}


def _context_from_emotions(emotions) -> list | None:
    if emotions is None:
        return None
    if isinstance(emotions, dict):
        return [float(emotions.get(k, 0.0)) for k in EMOTION_ORDER]
    if isinstance(emotions, (list, tuple)) and len(emotions) == len(EMOTION_ORDER):
        return [float(x) for x in emotions]
    return None


# ── 会话生命周期 ──────────────────────────────────────────────────────
def start_session(subject_id: str, meta: dict | None = None) -> dict:
    _ensure_init()
    session_id = "s" + time.strftime("%Y%m%d_%H%M%S")
    base, n = session_id, 1
    while AffectSessionModel.count('"session_id" = %s', (session_id,)) > 0:
        session_id = f"{base}_{n}"
        n += 1
    started = int(time.time() * 1000)
    AffectSessionModel(
        session_id=session_id, subject_id=subject_id or "anon",
        started_ms=started, meta=meta or {},
    ).save()
    return {"ok": True, "session_id": session_id, "started_ms": started}


def stop_session(session_id: str) -> dict:
    _ensure_init()
    sess = AffectSessionModel.find_all('"session_id" = %s', (session_id,), limit=1)
    if sess:
        s = sess[0]
        s.stopped_ms = int(time.time() * 1000)
        s.save()
    fea_n = AffectFeaModel.count('"session_id" = %s', (session_id,))
    img_n = AffectImageModel.count('"session_id" = %s', (session_id,))
    return {"ok": True, "session_id": session_id, "fea_count": fea_n, "image_count": img_n}


# ── 写入 ──────────────────────────────────────────────────────────────
def insert_fea(session_id: str, rows: list) -> int:
    """批量写 FEA 时间轴。rows: [{ts_ms, blendshapes?[63], emotions?, dominant?, source?}]。"""
    _ensure_init()
    now = int(time.time() * 1000)
    prepared = []
    skipped = 0
    for r in rows or []:
        bs = r.get("blendshapes")
        if bs is not None and len(bs) != FEA_DIM:
            skipped += 1        # 错维 FEA：跳过而非静默写 NULL 损坏时间轴
            continue
        prepared.append({
            "session_id": session_id,
            "ts_ms": int(r.get("ts_ms") or now),
            "fea": bs,          # None（本行无 FEA）或已校验为 FEA_DIM 维
            "emotions": r.get("emotions"),
            "dominant": r.get("dominant"),
            "source": r.get("source"),
        })
    if skipped:
        logger.warning("insert_fea: 跳过 %d 行错误维度 FEA（期望 %d 维）", skipped, FEA_DIM)
    if not prepared:
        return 0
    return AffectFeaModel.insert_many(prepared)


def insert_selfreport(session_id: str, rows: list) -> int:
    """批量写受试者自评。rows: [{ts_ms, image_id?, label7, valence?, arousal?, source?}]。

    自评是**唯一独立于 FEA 的真值来源**：规则式 classify_fea 与 FEA 同源，不能既当输入
    又当标签。没有这张表，PG 链路采到的时间轴就只能配循环标签，无法用于正式训练。
    label7 非法的行拒绝写入，避免污染标签空间。
    """
    _ensure_init()
    now = int(time.time() * 1000)
    prepared, bad = [], 0
    for r in rows or []:
        label = str(r.get("label7") or "").strip().lower()
        if label and label not in EMOTION_ORDER:
            bad += 1
            continue

        def _clamp(v):
            """SAM 取 1–9；越界或非数字一律记 None，不硬塞。"""
            if v is None or v == "":
                return None
            try:
                iv = int(v)
            except (TypeError, ValueError):
                return None
            return iv if 1 <= iv <= 9 else None

        prepared.append({
            "session_id": session_id,
            "ts_ms": int(r.get("ts_ms") or now),
            "image_id": (str(r["image_id"]) if r.get("image_id") is not None else None),
            "label7": label or None,
            "valence": _clamp(r.get("valence")),
            "arousal": _clamp(r.get("arousal")),
            "source": r.get("source"),
        })
    if bad:
        logger.warning("insert_selfreport: 跳过 %d 行非法 label7（须为 %s 之一）",
                       bad, "/".join(EMOTION_ORDER))
    if not prepared:
        return 0
    return AffectSelfReportModel.insert_many(prepared)


def insert_image(rec: dict) -> dict:
    """写一条生成图偏好记录。"""
    _ensure_init()
    context = _context_from_emotions(rec.get("context") or rec.get("emotions"))
    liked = rec.get("liked")
    model = AffectImageModel(
        session_id=rec.get("session_id"),
        ts_ms=int(rec.get("ts_ms") or time.time() * 1000),
        dominant=rec.get("dominant"),
        context=context,
        prompt=rec.get("prompt"),
        negative=rec.get("negative"),
        scene=rec.get("scene"),
        reasoning=rec.get("reasoning"),
        image_url=rec.get("image_url"),
        image_path=rec.get("image_path"),
        liked=bool(liked) if liked is not None else None,
        reaction=rec.get("reaction"),
    )
    model.save()
    return {"ok": True, "id": model.id}


# ── 检索（偏好闭环）───────────────────────────────────────────────────
_REC_COLS = ["id", "dominant", "prompt", "negative", "scene", "image_url", "dist"]


def recommend(emotions, k: int = 5, subject_id: str | None = None,
              epsilon: float | None = None) -> dict:
    """按当前情绪情境检索相似的生成图。

    两处偏离原实现，都是为了让「偏好模型比随机好」这件事可被检验：
    - **距离用 cosine（`<=>`）而非 L2**：context 是 7 类情绪概率，位于单纯形上，
      L2 会把「强度」当成差异，cosine 才对应「情绪构成相似」。
    - **保留 ε-探索**：默认 20% 的名额从全库随机取（不限于 liked），否则检索只在
      「喜欢过」的集合里打转，探索崩溃，且无法与随机基线做 A/B。
      liked 池为空时（例如刺激页从不写 liked），退化为纯随机而不是返回空列表。

    每项带 `source`: exploit=最近邻 / explore=随机，便于下游做 A/B 与日志归因。
    """
    _ensure_init()
    context = _context_from_emotions(emotions)
    if context is None:
        return {"items": []}
    eps = config.AFFECT_EPSILON if epsilon is None else float(epsilon)
    eps = min(max(eps, 0.0), 1.0)
    k = max(0, int(k))
    n_explore = int(round(k * eps))
    n_exploit = k - n_explore

    qv = "[" + ",".join(f"{float(x):.6g}" for x in context) + "]"
    db = DatabaseManager()
    join = " JOIN affect_session s ON i.session_id = s.session_id" if subject_id else ""
    subj_cond = " AND s.subject_id = %s" if subject_id else ""

    def _query(where, order, limit, extra_params=()):
        sql = (f'SELECT i.id, i.dominant, i.prompt, i.negative, i.scene, i.image_url, '
               f'i.context <=> %s::vector AS dist '
               f'FROM affect_image i{join} '
               f'WHERE i.context IS NOT NULL{subj_cond} {where} {order} LIMIT %s')
        params = [qv] + ([subject_id] if subject_id else []) + list(extra_params) + [limit]
        return db.execute_query(sql, tuple(params))

    items, seen = [], set()
    if n_exploit:
        for r in _query("AND i.liked = true", "ORDER BY i.context <=> %s::vector",
                        n_exploit, (qv,)):
            d = dict(zip(_REC_COLS, r))
            d["source"] = "exploit"
            items.append(d)
            seen.add(d["id"])

    # 探索名额（含 exploit 未取满时的补位）从全库随机取，保证不与已选重复
    want = k - len(items)
    if want > 0:
        for r in _query("", "ORDER BY random()", want + len(seen)):
            d = dict(zip(_REC_COLS, r))
            if d["id"] in seen:
                continue
            d["source"] = "explore"
            items.append(d)
            seen.add(d["id"])
            if len(items) >= k:
                break
    return {"items": items, "epsilon": eps, "metric": "cosine"}


def list_sessions(limit: int = 100) -> dict:
    _ensure_init()
    db = DatabaseManager()
    rows = db.execute_query(
        'SELECT s.session_id, s.subject_id, s.started_ms, s.stopped_ms, '
        '  (SELECT count(*) FROM affect_fea f WHERE f.session_id = s.session_id), '
        '  (SELECT count(*) FROM affect_image i WHERE i.session_id = s.session_id), '
        '  (SELECT count(*) FROM affect_selfreport r WHERE r.session_id = s.session_id) '
        'FROM affect_session s ORDER BY s.started_ms DESC LIMIT %s',
        (limit,))
    cols = ["session_id", "subject_id", "started_ms", "stopped_ms",
            "fea_count", "image_count", "selfreport_count"]
    sessions = [dict(zip(cols, r)) for r in rows]
    # 没有自评的会话只能配循环标签，不能用于正式训练——显式标出来，别让人以为能用
    for s in sessions:
        s["trainable"] = bool(s["selfreport_count"])
    return {"sessions": sessions}
