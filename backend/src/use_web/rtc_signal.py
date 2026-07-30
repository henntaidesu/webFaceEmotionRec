"""头显视角回传的 **WebRTC 信令中转**（后端只转交 SDP，不经手任何像素）。

原先的做法是头显把每帧渲成 JPEG POST 到后端、网页再轮询取回，画面在服务器上
过一遍。单眼原生分辨率下这是几十 Mbps 的上下行，外网场景根本跑不动。改成
WebRTC 后画面由头显直接推给浏览器，后端在这里只做一件事：让两端交换到彼此的
SDP（几 KB 的一次性文本）。

**谁发起**：头显是 offerer（媒体在它那边），但只在「确实有人在看」时才建连接、
才开编码 —— 省电，也避免没人看时白白占带宽。所以多了一个 watch 探针：

    网页 GET /offer   ← 这个调用本身就登记「有人在看」（VIEWER_TTL_S 内有效）
    头显 GET /watch   → {watching: true} 时建 pc、造 offer、POST /offer
    网页 GET /offer   → 拿到 {session, sdp}，造 answer，POST /answer
    头显 GET /answer  → 拿到 answer，连接建立，之后画面不再经过后端
    网页 POST /bye    → 离开页面时立刻通知，头显不必等 TTL 超时才停编码

**vanilla ICE（非 trickle）**：两端都等 ICE 收集完再发 SDP，候选地址直接内嵌在
SDP 里。代价是建连慢 1～3 秒，换来的是信令面少一半接口、且没有「候选先于会话
ID 到达」这类竞态要处理。一次会话只握手一次，这个取舍是划算的。
"""
from __future__ import annotations

import threading
import time

from .. import settings_store

# 网页多久没来取 offer 就认为它走了（网页轮询间隔 1s，留 5s 容忍抖动）
VIEWER_TTL_S = 5.0

_LOCK = threading.Lock()
_state: dict = {
    "session": 0,        # 会话号，头显每发一次 offer 自增；网页据此判断「换了新连接」
    "offer": None,       # 头显的 SDP offer
    "answer": None,      # 网页的 SDP answer
    "viewer_ts": 0.0,    # 网页最后一次来取 offer 的时刻（单调时钟）
}


def ice_servers() -> list[dict]:
    """两端共用的 ICE 服务器表（实时读 conf.ini，改完不用重启）。"""
    cfg = settings_store.get_section("webrtc")
    servers: list[dict] = []
    stun = [u.strip() for u in (cfg.get("stun_urls") or "").split(",") if u.strip()]
    if stun:
        servers.append({"urls": stun})
    turn = (cfg.get("turn_url") or "").strip()
    if turn:
        servers.append({
            "urls": [turn],
            "username": cfg.get("turn_username") or "",
            "credential": cfg.get("turn_credential") or "",
        })
    return servers


def _watching_locked() -> bool:
    return (time.monotonic() - _state["viewer_ts"]) < VIEWER_TTL_S


def watching() -> dict:
    """头显轮询：现在有没有人在网页上看？没人看就别建连接、别编码。"""
    with _LOCK:
        return {"watching": _watching_locked(), "session": _state["session"]}


def put_offer(sdp: str) -> dict:
    """头显发布 offer，开启新会话（旧 answer 作废）。"""
    with _LOCK:
        _state["session"] += 1
        _state["offer"] = sdp
        _state["answer"] = None
        return {"ok": True, "session": _state["session"]}


def take_offer() -> dict | None:
    """网页取 offer；顺带登记「有人在看」。没有 offer 时返回 None。"""
    with _LOCK:
        _state["viewer_ts"] = time.monotonic()
        if not _state["offer"]:
            return None
        return {"session": _state["session"], "sdp": _state["offer"]}


def put_answer(session: int, sdp: str) -> dict:
    """网页回 answer。session 对不上说明这是上一次会话的迟到应答，丢弃。"""
    with _LOCK:
        if session != _state["session"]:
            return {"ok": False, "error": "会话已过期"}
        _state["answer"] = sdp
        return {"ok": True}


def take_answer(session: int) -> str | None:
    with _LOCK:
        if session != _state["session"]:
            return None
        return _state["answer"]


def bye() -> dict:
    """网页离开：立刻清空会话，头显下次 watch 就会拆连接停编码。"""
    with _LOCK:
        _state["viewer_ts"] = 0.0
        _state["offer"] = None
        _state["answer"] = None
        return {"ok": True}
