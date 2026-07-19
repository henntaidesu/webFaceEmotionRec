# -*- coding: utf-8 -*-
"""数据库管理器 - 统一管理所有表模型（自动建库 + 建表 + 对齐表结构）。"""
from typing import List, Type

from .base_model import BaseModel
from .database import DatabaseManager
from .models import AffectSessionModel, AffectFeaModel, AffectImageModel


class DBManager:
    """统一管理所有表：初始化时自动建库、建表、增补/删除列。"""

    def __init__(self):
        self.db = DatabaseManager()
        self.models: List[Type[BaseModel]] = [
            AffectSessionModel,
            AffectFeaModel,
            AffectImageModel,
        ]

    def initialize_database(self) -> bool:
        """建库 + 启用 pgvector + 逐表建/对齐结构。"""
        self.db.ensure_database()

        ok, total, failed = 0, len(self.models), []
        for model_class in self.models:
            try:
                if model_class.ensure_table_exists():
                    ok += 1
                else:
                    failed.append(model_class.get_table_name())
            except Exception as e:
                failed.append(model_class.get_table_name())
                print(f"[FAIL] 表 {model_class.get_table_name()} 初始化异常: {e}")

        if ok == total:
            print(f"[OK] 数据库初始化成功: {ok}/{total} 个表")
            return True
        print(f"[WARN] 数据库初始化完成: {ok}/{total} 个表；失败: {', '.join(failed)}")
        return False

    def check_table_integrity(self) -> bool:
        for model_class in self.models:
            table = model_class.get_table_name()
            if not self.db.table_exists(table):
                return False
            existing = {c["name"] for c in self.db.get_table_columns(table)}
            if set(model_class.get_fields().keys()) - existing:
                return False
        return True

    def get_statistics(self) -> dict:
        stats = {"tables": {}, "total_records": 0}
        for model_class in self.models:
            table = model_class.get_table_name()
            try:
                n = model_class.count()
            except Exception:
                n = 0
            stats["tables"][table] = n
            stats["total_records"] += n
        return stats

    def get_database_info(self) -> dict:
        return self.db.get_database_info()


_db_manager = DBManager()


def init_database() -> bool:
    """初始化数据库（幂等：可重复调用以对齐表结构）。"""
    return _db_manager.initialize_database()


def get_db_manager() -> DBManager:
    return _db_manager
