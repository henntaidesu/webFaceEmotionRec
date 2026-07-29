"""研究记录日志：每日一条，全部条目存于单个 JSON 文件（config.RESEARCH_LOG_FILE）。

文件格式：
    {"entries": [{"date": "2026-07-30", "progress": "", "issues": "",
                  "plan": "", "tags": [], "updated_ms": 1753...}, ...]}

设计取舍：**每次请求都从磁盘重读**，不做内存缓存——这份文件也会被人/Claude 直接
用编辑器改，缓存会让页面看到过期内容。写入走「临时文件 + 原子替换」，避免中途崩溃
损坏整个日志。条目按日期倒序（最新在前）持久化，前端拿到即可直接渲染。
"""
import json
import os
import re
import threading
import time

from . import config

# 分区模板的正文字段（前端四栏；tags 单独处理）
TEXT_FIELDS = ("progress", "issues", "plan")

_LOCK = threading.Lock()   # 读改写非原子，并发保存需串行
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load() -> list:
    """读全部条目；文件不存在/损坏时返回空表（不抛错，页面照常可用）。"""
    path = config.RESEARCH_LOG_FILE
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else data
    return [e for e in entries if isinstance(e, dict) and _DATE_RE.match(str(e.get("date", "")))] \
        if isinstance(entries, list) else []


def _save(entries: list) -> None:
    """原子写盘：先写 .tmp 再 os.replace，避免半截文件。"""
    path = config.RESEARCH_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = sorted(entries, key=lambda e: e["date"], reverse=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _clean(entry: dict) -> dict:
    """规整一条：只保留已知字段，标签去空去重且保序。"""
    tags, seen = [], set()
    for t in entry.get("tags") or []:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
    return {
        "date": entry["date"],
        **{k: str(entry.get(k) or "") for k in TEXT_FIELDS},
        "tags": tags,
        "updated_ms": int(entry.get("updated_ms") or time.time() * 1000),
    }


def list_entries() -> dict:
    """全部条目（日期倒序）+ 出现过的标签集合，供前端筛选。"""
    entries = sorted(_load(), key=lambda e: e["date"], reverse=True)
    tags = sorted({t for e in entries for t in (e.get("tags") or [])})
    return {"entries": [_clean(e) for e in entries], "tags": tags,
            "file": str(config.RESEARCH_LOG_FILE)}


def upsert_entry(body: dict) -> dict:
    """按日期新增或覆盖一条。body: {date, progress?, issues?, plan?, tags?}。"""
    body = body or {}
    date = str(body.get("date") or "").strip()
    if not _DATE_RE.match(date):
        raise ValueError("date 需为 YYYY-MM-DD")
    entry = _clean({**body, "date": date, "updated_ms": int(time.time() * 1000)})
    with _LOCK:
        entries = [e for e in _load() if e["date"] != date]
        entries.append(entry)
        _save(entries)
    return {"ok": True, "entry": entry}


def delete_entry(date: str) -> dict:
    """删除指定日期的条目；不存在时返回 deleted=False。"""
    date = str(date or "").strip()
    with _LOCK:
        entries = _load()
        kept = [e for e in entries if e["date"] != date]
        if len(kept) == len(entries):
            return {"ok": True, "deleted": False}
        _save(kept)
    return {"ok": True, "deleted": True}
