# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""GraphRAG-6 自己的检索算法库。

和微软的 GraphRAG 引擎（仓库根的 ``packages/``）分开：这里只放本项目实现的部分——
三种可切换的自定义检索（LightRAG 风格、HippoRAG 2 风格、PathFusionRAG）、检索轨迹
的数据结构，以及 trace 落盘。前端 ``graphrag-workbench`` 只消费这个包，不重复实现。

文件来源：

- ``retrieval.py`` / ``custom_search.py`` / ``trace_store.py``：本项目在 commit
  0b8665c（2026-09-11）新增，后于 2026-09-13 抽成独立包；
- ``typing.py``：在兼容 GraphRAG-6 数据契约的基础上扩展出 SearchMethod 与 RetrievalTrace。
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
