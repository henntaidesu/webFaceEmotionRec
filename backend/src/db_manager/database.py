# -*- coding: utf-8 -*-
"""数据库管理核心类（Postgres + pgvector）。

对象模式的底座：BaseModel 定义字段 → DatabaseManager 负责连接、建库、建表、改表。
参考 CsWeaponManager 的 db_manager 结构，但本项目单后端（Postgres），故不做方言翻译，
直接用 Postgres 原生占位符 %s 与标识符 "name"。

连接参数实时取自 settings_store（conf.ini [postgres]），系统设置页改完即时生效。
特性：
- 自动建库：目标库不存在时连维护库（postgres）执行 CREATE DATABASE。
- pgvector：建库后 CREATE EXTENSION IF NOT EXISTS vector。
- 自动改表：BaseModel.ensure_table_exists 增补缺失列、删除多余列。
- 向量/JSONB：字段类型 VECTOR(dim)/JSONB，写入时以 %s::vector / %s::jsonb 转换。

psycopg 未安装 / host 未配置 / 连接失败 一律抛 RuntimeError，由上层转 HTTP 错误。
"""
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .. import settings_store


def _psycopg():
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError('未安装 psycopg：pip install "psycopg[binary]"') from e
    return psycopg


# ── 字段类型映射（模型定义 → Postgres 类型）───────────────────────────────
def pg_column_type(field: Dict[str, Any]) -> str:
    """把模型字段定义映射为 Postgres 字段类型。

    可选类型提示：
    - 'pg_type'：直接指定（最高优先级）
    - 'dim'：VECTOR 维度
    - 'length'：VARCHAR 长度
    autoincrement + primary_key → BIGSERIAL。
    """
    if field.get("pg_type"):
        return field["pg_type"]
    if field.get("autoincrement") and field.get("primary_key"):
        return "BIGSERIAL"

    base = (field.get("type") or "TEXT").upper()
    if base == "VECTOR":
        return f"vector({int(field.get('dim') or 0)})"
    if base == "JSONB":
        return "JSONB"
    if "INT" in base:
        return "BIGINT"
    if base in ("REAL", "FLOAT", "DOUBLE"):
        return "DOUBLE PRECISION"
    if base in ("NUMERIC", "DECIMAL"):
        return "NUMERIC(20,6)"
    if base in ("BOOL", "BOOLEAN"):
        return "BOOLEAN"
    if base in ("BLOB", "BYTEA"):
        return "BYTEA"
    length = field.get("length")
    if length:
        return f"VARCHAR({int(length)})"
    return "TEXT"


class DatabaseManager:
    """Postgres 数据库管理器 - 单例，线程本地连接，autocommit。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_ready"):
            self._local = threading.local()
            self._ready = True

    # ── 配置 / 连接 ────────────────────────────────────────────────────
    def _cfg(self) -> dict:
        return settings_store.get_section("postgres")

    def is_configured(self) -> bool:
        c = self._cfg()
        return bool((c.get("host") or "").strip() and (c.get("database") or "").strip())

    def _sig(self, c: dict) -> tuple:
        return (c.get("host"), c.get("port"), c.get("user"), c.get("password"), c.get("database"))

    def _connect(self, dbname: str):
        c = self._cfg()
        if not (c.get("host") or "").strip():
            raise RuntimeError("Postgres host 未配置")
        psycopg = _psycopg()
        try:
            return psycopg.connect(
                host=c["host"], port=int(c.get("port") or 5432),
                user=c.get("user") or "postgres", password=c.get("password") or "",
                dbname=dbname, autocommit=True, connect_timeout=10,
            )
        except psycopg.Error as e:
            raise RuntimeError(f"Postgres 连接失败: {e}")

    def _get_conn(self):
        """线程本地连接到目标库；配置变化或连接失效则重连。"""
        c = self._cfg()
        sig = self._sig(c)
        conn = getattr(self._local, "conn", None)
        if conn is not None and (getattr(self._local, "sig", None) != sig or conn.closed):
            try:
                conn.close()
            except Exception:
                pass
            conn = None
        if conn is None:
            conn = self._connect(c["database"])
            self._local.conn = conn
            self._local.sig = sig
        return conn

    def reconfigure(self):
        """配置切换后重置线程本地连接。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None

    @contextmanager
    def get_connection(self):
        yield self._get_conn()

    # ── 建库 + 扩展 ────────────────────────────────────────────────────
    def ensure_database(self) -> None:
        """目标库不存在则创建；并确保 pgvector 扩展存在。"""
        c = self._cfg()
        dbname = c["database"]
        psycopg = _psycopg()
        # 连维护库检查/建库（CREATE DATABASE 不能在事务内，autocommit 已开）
        admin = self._connect("postgres")
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{dbname}"')
        except psycopg.Error as e:
            raise RuntimeError(f"创建数据库 {dbname} 失败: {e}")
        finally:
            admin.close()
        # 目标库启用 pgvector
        with self._get_conn().cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def server_version(self) -> str:
        with self._get_conn().cursor() as cur:
            cur.execute("SHOW server_version")
            return cur.fetchone()[0]

    # ── 基础执行 ───────────────────────────────────────────────────────
    def execute_query(self, sql: str, params: tuple = ()) -> List[tuple]:
        with self._get_conn().cursor() as cur:
            cur.execute(sql, params or None)
            return cur.fetchall()

    def execute_update(self, sql: str, params: tuple = ()) -> int:
        with self._get_conn().cursor() as cur:
            cur.execute(sql, params or None)
            return cur.rowcount

    def execute_insert(self, sql: str, params: tuple = ()) -> Optional[int]:
        """执行 INSERT ... RETURNING，返回首列（通常自增主键）。"""
        with self._get_conn().cursor() as cur:
            cur.execute(sql, params or None)
            row = cur.fetchone() if cur.description else None
            return row[0] if row else None

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        if not params_list:
            return 0
        with self._get_conn().cursor() as cur:
            cur.executemany(sql, params_list)
            return cur.rowcount

    # ── 内省 ───────────────────────────────────────────────────────────
    def table_exists(self, table_name: str) -> bool:
        rows = self.execute_query(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s", (table_name,))
        return len(rows) > 0

    def _primary_key_cols(self, table_name: str) -> set:
        rows = self.execute_query(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = %s::regclass AND i.indisprimary",
            (f'public."{table_name}"',))
        return {r[0] for r in rows}

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        if not self.table_exists(table_name):
            return []
        pk = self._primary_key_cols(table_name)
        rows = self.execute_query(
            "SELECT column_name, data_type, is_nullable, column_default, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table_name,))
        cols = []
        for r in rows:
            cols.append({
                "cid": r[4], "name": r[0], "type": r[1],
                "notnull": (str(r[2]).upper() == "NO"),
                "default_value": r[3], "pk": r[0] in pk,
            })
        return cols

    def get_all_tables(self) -> List[str]:
        rows = self.execute_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
        return [r[0] for r in rows]

    # ── 建表 / 改列 ────────────────────────────────────────────────────
    def create_table(self, table_name: str, columns: List[Dict[str, Any]],
                     indexes: List[Dict[str, Any]] = None) -> bool:
        try:
            pk_cols = [c["name"] for c in columns if c.get("primary_key")]
            defs = []
            for col in columns:
                col_def = f'"{col["name"]}" {pg_column_type(col)}'
                if col.get("primary_key") and len(pk_cols) == 1:
                    col_def += " PRIMARY KEY"
                elif col.get("not_null"):
                    col_def += " NOT NULL"
                if col.get("default") is not None and not col.get("autoincrement"):
                    col_def += f" DEFAULT {self._default_literal(col['default'])}"
                defs.append(col_def)
            if len(pk_cols) > 1:
                defs.append(f'PRIMARY KEY ({", ".join(chr(34)+c+chr(34) for c in pk_cols)})')
            self.execute_update(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(defs)})')
            for idx in (indexes or []):
                self._create_index(table_name, idx)
            return True
        except Exception as e:
            print(f"创建表 {table_name} 失败: {e}")
            return False

    def _create_index(self, table_name: str, idx: Dict[str, Any]) -> None:
        cols = idx["columns"]
        idx_name = idx.get("name", f"idx_{table_name}_{cols[0]}")
        col_list = ", ".join(f'"{c}"' for c in cols)
        using = idx.get("using")  # 例如 'hnsw'（pgvector）
        if using:
            opclass = idx.get("opclass", "vector_l2_ops")
            sql = (f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" '
                   f'USING {using} ("{cols[0]}" {opclass})')
        else:
            sql = f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" ({col_list})'
        try:
            self.execute_update(sql)
        except Exception as e:
            print(f"创建索引 {idx_name} 失败: {e}")

    @staticmethod
    def _default_literal(default) -> str:
        if isinstance(default, (int, float)):
            return str(default)
        s = str(default).replace("'", "''")
        return f"'{s}'"

    def add_column(self, table_name: str, column_def: Dict[str, Any]) -> bool:
        try:
            col_sql = f'"{column_def["name"]}" {pg_column_type(column_def)}'
            if column_def.get("not_null"):
                col_sql += " NOT NULL"
            if column_def.get("default") is not None:
                col_sql += f" DEFAULT {self._default_literal(column_def['default'])}"
            self.execute_update(f'ALTER TABLE "{table_name}" ADD COLUMN {col_sql}')
            return True
        except Exception as e:
            print(f"添加列到表 {table_name} 失败: {e}")
            return False

    def drop_column(self, table_name: str, column_name: str) -> bool:
        try:
            self.execute_update(f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"')
            return True
        except Exception as e:
            print(f"删除列 {column_name} 从表 {table_name} 失败: {e}")
            return False

    def drop_table(self, table_name: str) -> bool:
        try:
            self.execute_update(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            return True
        except Exception as e:
            print(f"删除表 {table_name} 失败: {e}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        c = self._cfg()
        info = {"host": c.get("host"), "database": c.get("database"), "tables": []}
        for t in self.get_all_tables():
            info["tables"].append({"name": t, "columns": self.get_table_columns(t)})
        return info
