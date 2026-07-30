# -*- coding: utf-8 -*-
"""「情感偏好生成」的表模型（对象模式）。

三张表：
  affect_session  采集会话（subject / 起止 / 元数据）
  affect_fea      FEA 时间轴：每帧 63 维 blendshape(vector) + 7 类情绪概率 + 时间戳
                  —— 供后续训练情绪预测模型
  affect_image    生成图偏好：生成时 7 维情绪情境(vector) + 提示词 + 反应 + 是否喜欢
                  —— context 向量供「相似情绪情境下用户喜欢的图」相似度检索
"""
from .. import config
from .base_model import BaseModel

_FEA_DIM = config.FEA_DIM                 # 63
_EMO_DIM = len(config.TRAIN_CLASSES)      # 7


class AffectSessionModel(BaseModel):
    @classmethod
    def get_table_name(cls) -> str:
        return "affect_session"

    @classmethod
    def get_fields(cls):
        return {
            "session_id": {"type": "TEXT", "primary_key": True, "not_null": True},
            "subject_id": {"type": "TEXT", "not_null": True},
            "started_ms": {"type": "INTEGER", "not_null": True},
            "stopped_ms": {"type": "INTEGER"},
            "meta":       {"type": "JSONB"},
        }


class AffectFeaModel(BaseModel):
    @classmethod
    def get_table_name(cls) -> str:
        return "affect_fea"

    @classmethod
    def get_fields(cls):
        return {
            "id":         {"type": "INTEGER", "primary_key": True, "autoincrement": True},
            "session_id": {"type": "TEXT", "not_null": True},
            "ts_ms":      {"type": "INTEGER", "not_null": True},
            "fea":        {"type": "VECTOR", "dim": _FEA_DIM},
            "emotions":   {"type": "JSONB"},
            "dominant":   {"type": "TEXT"},
            "source":     {"type": "TEXT"},
        }

    @classmethod
    def get_indexes(cls):
        return [{"name": "idx_affect_fea_session_ts", "columns": ["session_id", "ts_ms"]}]


class AffectImageModel(BaseModel):
    @classmethod
    def get_table_name(cls) -> str:
        return "affect_image"

    @classmethod
    def get_fields(cls):
        return {
            "id":         {"type": "INTEGER", "primary_key": True, "autoincrement": True},
            "session_id": {"type": "TEXT"},
            "ts_ms":      {"type": "INTEGER", "not_null": True},
            "dominant":   {"type": "TEXT"},
            "context":    {"type": "VECTOR", "dim": _EMO_DIM},
            "prompt":     {"type": "TEXT"},
            "negative":   {"type": "TEXT"},
            "scene":      {"type": "TEXT"},
            "reasoning":  {"type": "TEXT"},
            "image_url":  {"type": "TEXT"},
            # 磁盘相对路径（相对仓库根，如 image/happy/20260723_181500.png）——
            # image_url 只是它的 HTTP 映射，换端口/换机器后仍能凭 path 找回文件
            "image_path": {"type": "TEXT"},
            "liked":      {"type": "BOOLEAN"},
            "reaction":   {"type": "JSONB"},
        }

    @classmethod
    def get_indexes(cls):
        return [
            {"name": "idx_affect_image_liked", "columns": ["liked"]},
            # pgvector 近邻检索索引：与 pg_store.recommend 的 <=> 保持一致用 cosine。
            # context 是 7 类情绪概率（单纯形上），L2 会把强度差当成情绪差，
            # 且 opclass 与查询算子不一致时索引根本不会被用上。
            {"name": "idx_affect_image_context_cos", "columns": ["context"],
             "using": "hnsw", "opclass": "vector_cosine_ops"},
        ]
