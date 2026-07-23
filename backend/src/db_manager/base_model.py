# -*- coding: utf-8 -*-
"""数据库模型基础类（对象模式，Postgres）。

子类只需声明 get_table_name() 与 get_fields()（可选 get_indexes()），即可获得
建表/改表/增删改查能力。字段定义示例：

    @classmethod
    def get_fields(cls):
        return {
            "id":       {"type": "INTEGER", "primary_key": True, "autoincrement": True},
            "ts_ms":    {"type": "INTEGER", "not_null": True},
            "fea":      {"type": "VECTOR", "dim": 63},   # pgvector 列
            "emotions": {"type": "JSONB"},
            "name":     {"type": "TEXT"},
        }

VECTOR 值可传 list（自动格式化为 '[...]'::vector）；JSONB 值可传 dict/list（自动 json）。
"""
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .database import DatabaseManager


class BaseModel(ABC):
    def __init__(self, **kwargs):
        self.db = DatabaseManager()
        self._data = {}
        self._original_data = {}
        for field_name, field_def in self.get_fields().items():
            value = kwargs.get(field_name, field_def.get("default"))
            if isinstance(value, str) and value.strip() == "":
                value = None
            self._data[field_name] = value
            self._original_data[field_name] = value

    # ── 子类声明 ───────────────────────────────────────────────────────
    @classmethod
    @abstractmethod
    def get_table_name(cls) -> str: ...

    @classmethod
    @abstractmethod
    def get_fields(cls) -> Dict[str, Dict[str, Any]]: ...

    @classmethod
    def get_indexes(cls) -> List[Dict[str, Any]]:
        return []

    # ── 字段访问 ───────────────────────────────────────────────────────
    def __getattr__(self, name: str):
        data = self.__dict__.get("_data", {})
        if name in data:
            return data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        if name.startswith("_") or name == "db":
            super().__setattr__(name, value)
        elif hasattr(self, "_data") and name in self.get_fields():
            if isinstance(value, str) and value.strip() == "":
                value = None
            self._data[name] = value
        else:
            super().__setattr__(name, value)

    def to_dict(self) -> Dict[str, Any]:
        return self._data.copy()

    # ── 值适配（VECTOR / JSONB）────────────────────────────────────────
    @classmethod
    def _cast(cls, field_def: Dict[str, Any]) -> str:
        base = (field_def.get("type") or "TEXT").upper()
        if base == "VECTOR":
            return "::vector"
        if base == "JSONB":
            return "::jsonb"
        return ""

    @staticmethod
    def _adapt(field_def: Dict[str, Any], value):
        if value is None:
            return None
        base = (field_def.get("type") or "TEXT").upper()
        if base == "VECTOR":
            if isinstance(value, str):
                return value
            return "[" + ",".join(f"{float(x):.6g}" for x in value) + "]"
        if base == "JSONB":
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return value

    def _get_primary_keys(self) -> List[str]:
        return [n for n, d in self.get_fields().items() if d.get("primary_key")]

    # ── 增删改 ─────────────────────────────────────────────────────────
    def save(self) -> bool:
        return self._insert() if self._is_new_record() else self._update()

    def _is_new_record(self) -> bool:
        pks = self._get_primary_keys()
        if not pks:
            return True
        for key in pks:
            if not self._data.get(key):
                return True
        where = " AND ".join(f'"{k}" = %s' for k in pks)
        params = tuple(self._data[k] for k in pks)
        try:
            rows = self.db.execute_query(
                f'SELECT 1 FROM "{self.get_table_name()}" WHERE {where} LIMIT 1', params)
            return len(rows) == 0
        except Exception:
            return True

    def _insert(self) -> bool:
        fields, placeholders, params = [], [], []
        fdefs = self.get_fields()
        for name, value in self._data.items():
            fdef = fdefs[name]
            # 自增主键留空由数据库填充；空值跳过（存 NULL/默认）
            if fdef.get("autoincrement") and value is None:
                continue
            if value is None:
                continue
            fields.append(f'"{name}"')
            placeholders.append("%s" + self._cast(fdef))
            params.append(self._adapt(fdef, value))

        table = self.get_table_name()
        sql = f'INSERT INTO "{table}" ({", ".join(fields)}) VALUES ({", ".join(placeholders)})'

        # 单一自增主键时用 RETURNING 取回自增 id
        auto_pk = next((n for n, d in fdefs.items()
                        if d.get("primary_key") and d.get("autoincrement")), None)
        try:
            if auto_pk and self._data.get(auto_pk) is None:
                sql += f' RETURNING "{auto_pk}"'
                new_id = self.db.execute_insert(sql, tuple(params))
                if new_id is not None:
                    self._data[auto_pk] = new_id
            else:
                self.db.execute_update(sql, tuple(params))
            self._original_data = self._data.copy()
            return True
        except Exception as e:
            print(f"[错误] 插入记录失败 - 表: {table}, 错误: {e}")
            return False

    def _update(self) -> bool:
        pks = self._get_primary_keys()
        if not pks:
            return False
        fdefs = self.get_fields()
        set_parts, params = [], []
        for name, value in self._data.items():
            if name in pks or value == self._original_data.get(name):
                continue
            fdef = fdefs[name]
            set_parts.append(f'"{name}" = %s' + self._cast(fdef))
            params.append(self._adapt(fdef, value))
        if not set_parts:
            return True
        where = " AND ".join(f'"{k}" = %s' for k in pks)
        params.extend(self._original_data[k] for k in pks)
        sql = f'UPDATE "{self.get_table_name()}" SET {", ".join(set_parts)} WHERE {where}'
        try:
            if self.db.execute_update(sql, tuple(params)) > 0:
                self._original_data = self._data.copy()
            return True
        except Exception as e:
            print(f"更新记录失败: {e}")
            return False

    def delete(self) -> bool:
        pks = self._get_primary_keys()
        if not pks:
            return False
        where = " AND ".join(f'"{k}" = %s' for k in pks)
        params = tuple(self._data[k] for k in pks)
        try:
            return self.db.execute_update(
                f'DELETE FROM "{self.get_table_name()}" WHERE {where}', params) > 0
        except Exception as e:
            print(f"删除记录失败: {e}")
            return False

    @classmethod
    def insert_many(cls, rows: List[Dict[str, Any]]) -> int:
        """批量插入（同一组列）。rows 内各 dict 的键须一致，缺省列走默认/NULL。"""
        if not rows:
            return 0
        fdefs = cls.get_fields()
        cols = [c for c in rows[0].keys() if c in fdefs]
        placeholders = ", ".join("%s" + cls._cast(fdefs[c]) for c in cols)
        col_sql = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{cls.get_table_name()}" ({col_sql}) VALUES ({placeholders})'
        params_list = [tuple(cls._adapt(fdefs[c], r.get(c)) for c in cols) for r in rows]
        return DatabaseManager().execute_many(sql, params_list)

    @classmethod
    def delete_all(cls, where: str = "", params: tuple = ()) -> int:
        sql = f'DELETE FROM "{cls.get_table_name()}"'
        if where:
            sql += f" WHERE {where}"
        try:
            return DatabaseManager().execute_update(sql, params)
        except Exception as e:
            print(f"删除 {cls.get_table_name()} 失败: {e}")
            return 0

    # ── 查询 ───────────────────────────────────────────────────────────
    @classmethod
    def find_all(cls, where: str = "", params: tuple = (), limit: int = None,
                 offset: int = None, order_by: str = None) -> list:
        sql = f'SELECT * FROM "{cls.get_table_name()}"'
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {int(limit)}"
            if offset:
                sql += f" OFFSET {int(offset)}"
        try:
            rows = DatabaseManager().execute_query(sql, params)
            return [cls._create_from_row(r) for r in rows]
        except Exception as e:
            print(f"查找记录失败: {e}")
            return []

    @classmethod
    def count(cls, where: str = "", params: tuple = ()) -> int:
        sql = f'SELECT COUNT(*) FROM "{cls.get_table_name()}"'
        if where:
            sql += f" WHERE {where}"
        try:
            rows = DatabaseManager().execute_query(sql, params)
            return rows[0][0] if rows else 0
        except Exception as e:
            print(f"统计记录失败: {e}")
            return 0

    @classmethod
    def _get_table_column_names(cls) -> List[str]:
        cache = "_cached_cols"
        if not hasattr(cls, cache):
            cols = DatabaseManager().get_table_columns(cls.get_table_name())
            setattr(cls, cache, [c["name"] for c in cols])
        return getattr(cls, cache)

    @classmethod
    def _create_from_row(cls, row: tuple):
        names = cls._get_table_column_names()
        fdefs = cls.get_fields()
        kwargs = {}
        for idx, col in enumerate(names):
            if idx >= len(row) or col not in fdefs:
                continue
            kwargs[col] = row[idx]
        inst = cls(**kwargs)
        inst._original_data = inst._data.copy()
        return inst

    # ── 建表 / 改表 ────────────────────────────────────────────────────
    @classmethod
    def ensure_table_exists(cls) -> bool:
        db = DatabaseManager()
        if db.table_exists(cls.get_table_name()):
            return cls._check_and_update_table_structure()
        return cls._create_table()

    @classmethod
    def _create_table(cls) -> bool:
        db = DatabaseManager()
        columns = []
        for name, fdef in cls.get_fields().items():
            columns.append({
                "name": name,
                "type": fdef.get("type"),
                "primary_key": fdef.get("primary_key", False),
                "not_null": fdef.get("not_null", False),
                "default": fdef.get("default"),
                "autoincrement": fdef.get("autoincrement", False),
                "pg_type": fdef.get("pg_type"),
                "dim": fdef.get("dim"),
                "length": fdef.get("length"),
            })
        ok = db.create_table(cls.get_table_name(), columns, cls.get_indexes())
        if hasattr(cls, "_cached_cols"):
            delattr(cls, "_cached_cols")
        return ok

    @classmethod
    def _check_and_update_table_structure(cls) -> bool:
        db = DatabaseManager()
        table = cls.get_table_name()
        existing = {c["name"]: c for c in db.get_table_columns(table)}
        defined = cls.get_fields()

        # 增补缺失列
        for name, fdef in defined.items():
            if name not in existing:
                print(f"表 {table} 缺少字段 {name}，正在添加…")
                if not db.add_column(table, {
                    "name": name, "type": fdef.get("type"), "not_null": False,
                    "default": fdef.get("default"), "pg_type": fdef.get("pg_type"),
                    "dim": fdef.get("dim"), "length": fdef.get("length"),
                }):
                    return False

        # 删除多余列（主键除外）——默认【不删】，避免改字段名/schema 漂移时静默毁数据。
        # 确需自动删列时设环境变量 DB_ALLOW_DROP_COLUMN=1。
        allow_drop = os.getenv("DB_ALLOW_DROP_COLUMN", "").strip().lower() in {"1", "true", "yes", "on"}
        for name, info in existing.items():
            if name in defined:
                continue
            if info.get("pk"):
                print(f"表 {table} 字段 {name} 是主键，跳过删除")
                continue
            if not allow_drop:
                print(f"表 {table} 存在多余字段 {name}（保留；如确需删除设 DB_ALLOW_DROP_COLUMN=1）")
                continue
            print(f"表 {table} 存在多余字段 {name}，正在删除…")
            if not db.drop_column(table, name):
                return False

        if hasattr(cls, "_cached_cols"):
            delattr(cls, "_cached_cols")
        return True
