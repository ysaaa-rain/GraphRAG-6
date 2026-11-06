# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""GraphRAG-6 的独立检索模块。

在 Microsoft GraphRAG 输出的实体、关系与文本索引上，提供 LightRAG 风格、
HippoRAG 2 风格和 PathFusionRAG 三种检索策略，统一证据轨迹和结果持久化。
"""

from .custom_search import (
    build_custom_bundle,
    create_completion_resource,
    create_embedding_resources,
    generate_answer,
    vector_scores,
)
from .retrieval import (
    BM25,
    GraphRetriever,
    RetrievalBundle,
    RetrievalConfig,
    annotate_trace_metrics,
    normalize_scores,
    path_recall,
    row_record,
    source_recall,
    trace_from_context,
)
from .trace_store import load_trace_table, save_trace, trace_path, trace_record
from .typing import RetrievalTrace, SearchMethod, SearchResult, SearchType

__all__ = [  # noqa: RUF022 - 按"数据结构 → 检索 → 生成 → trace"分组，不按字母序
    "SearchMethod",
    "SearchType",
    "SearchResult",
    "RetrievalTrace",
    "GraphRetriever",
    "RetrievalConfig",
    "RetrievalBundle",
    "BM25",
    "normalize_scores",
    "row_record",
    "trace_from_context",
    "path_recall",
    "source_recall",
    "annotate_trace_metrics",
    "build_custom_bundle",
    "create_completion_resource",
    "create_embedding_resources",
    "generate_answer",
    "vector_scores",
    "save_trace",
    "load_trace_table",
    "trace_record",
    "trace_path",
]
