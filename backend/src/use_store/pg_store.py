"""「情感偏好生成」的存储服务层（构建在对象模式 db_manager 之上）。

app.py 的 /api/affect/* 端点调用这里；真正的建库/建表/改表与 CRUD 由
backend/src/db_manager（对象模式，参考 CsWeaponManager 的 db_manager）完成。
Postgres 连接参数取自 settings_store（conf.ini [postgres]），系统设置页改完即时生效。

is_configured / 连接失败 / 未配置 一律抛 RuntimeError，由路由层转 HTTP 错误。
"""
import time

from .. import config
from ..db_manager import (
    AffectFeaModel,
    AffectImageModel,
    AffectSessionModel,
    DatabaseManager,
    get_db_manager,
)

FEA_DIM = config.FEA_DIM
EMOTION_ORDER = config.TRAIN_CLASSES  # angry disgust fear happy neutral sad surprise（7）

_initialized = False


def is_configured() -> bool:
    return DatabaseManager().is_configured()


def _ensure_init() -> None:
    """首次使用时自动建库 + 建表（幂等）。"""
    global _initialized
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
    for r in rows or []:
        bs = r.get("blendshapes")
        fea = bs if (bs is not None and len(bs) == FEA_DIM) else None
        prepared.append({
            "session_id": session_id,
            "ts_ms": int(r.get("ts_ms") or now),
            "fea": fea,
            "emotions": r.get("emotions"),
            "dominant": r.get("dominant"),
            "source": r.get("source"),
        })
    if not prepared:
        return 0
    return AffectFeaModel.insert_many(prepared)


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
        liked=bool(liked) if liked is not None else None,
        reaction=rec.get("reaction"),
    )
    model.save()
    return {"ok": True, "id": model.id}


# ── 检索（偏好闭环）───────────────────────────────────────────────────
def recommend(emotions, k: int = 5, subject_id: str | None = None) -> dict:
    """按当前情绪情境，检索最相似的「用户喜欢过」的生成图（pgvector L2 最近邻）。"""
    _ensure_init()
    context = _context_from_emotions(emotions)
    if context is None:
        return {"items": []}
    qv = "[" + ",".join(f"{float(x):.6g}" for x in context) + "]"
    db = DatabaseManager()
    if subject_id:
        rows = db.execute_query(
            'SELECT i.id, i.dominant, i.prompt, i.negative, i.scene, i.image_url, '
            'i.context <-> %s::vector AS dist '
            'FROM affect_image i JOIN affect_session s ON i.session_id = s.session_id '
            'WHERE i.liked = true AND i.context IS NOT NULL AND s.subject_id = %s '
            'ORDER BY i.context <-> %s::vector LIMIT %s',
            (qv, subject_id, qv, k))
    else:
        rows = db.execute_query(
            'SELECT id, dominant, prompt, negative, scene, image_url, '
            'context <-> %s::vector AS dist '
            'FROM affect_image WHERE liked = true AND context IS NOT NULL '
            'ORDER BY context <-> %s::vector LIMIT %s',
            (qv, qv, k))
    cols = ["id", "dominant", "prompt", "negative", "scene", "image_url", "dist"]
    return {"items": [dict(zip(cols, r)) for r in rows]}


def list_sessions(limit: int = 100) -> dict:
    _ensure_init()
    db = DatabaseManager()
    rows = db.execute_query(
        'SELECT s.session_id, s.subject_id, s.started_ms, s.stopped_ms, '
        '  (SELECT count(*) FROM affect_fea f WHERE f.session_id = s.session_id), '
        '  (SELECT count(*) FROM affect_image i WHERE i.session_id = s.session_id) '
        'FROM affect_session s ORDER BY s.started_ms DESC LIMIT %s',
        (limit,))
    cols = ["session_id", "subject_id", "started_ms", "stopped_ms", "fea_count", "image_count"]
    return {"sessions": [dict(zip(cols, r)) for r in rows]}
