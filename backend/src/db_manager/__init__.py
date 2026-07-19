# -*- coding: utf-8 -*-
"""数据库管理模块（对象模式 + 自动表结构管理，Postgres + pgvector）。"""
from .database import DatabaseManager
from .base_model import BaseModel
from .manager import DBManager, init_database, get_db_manager
from .models import AffectSessionModel, AffectFeaModel, AffectImageModel

__all__ = [
    "DatabaseManager",
    "BaseModel",
    "DBManager",
    "init_database",
    "get_db_manager",
    "AffectSessionModel",
    "AffectFeaModel",
    "AffectImageModel",
]
