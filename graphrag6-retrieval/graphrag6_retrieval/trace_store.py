# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Persistence helpers for reproducible, query-level retrieval traces.

直接将检索结果写入 ``<index_dir>/output/retrieval_traces.parquet``，使用临时文件替换保证落盘时的文件完整性。
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from .typing import RetrievalTrace

TRACE_FILE = "output/retrieval_traces.parquet"
_TRACE_WRITE_LOCK = Lock()
NESTED_FIELDS = (
    "matched_entity_ids",
    "matched_entities",
    "matched_relationship_ids",
    "matched_relationships",
    "graph_paths",
    "subgraph_nodes",
    "subgraph_edges",
    "text_evidence",
    "retrieved_source_paths",
    "channel_scores",
)


def _encode(value: Any) -> str:
    """Encode nested trace fields as stable JSON strings in Parquet."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def trace_record(trace: RetrievalTrace) -> dict[str, Any]:
    """Flatten a trace without dropping any graph/path field."""
    record = trace.as_record()
    for key in NESTED_FIELDS:
        record[key] = _encode(record[key])
    return record


def trace_path(index_dir: str | Path) -> Path:
    """Return the trace table path for one index directory."""
    return Path(index_dir) / TRACE_FILE


def save_trace(index_dir: str | Path, trace: RetrievalTrace) -> Path:
    """Append a trace without exposing a partially written Parquet file."""
    path = trace_path(index_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _TRACE_WRITE_LOCK:
        batch = pd.DataFrame([trace_record(trace)])
        if path.is_file():
            batch = pd.concat([pd.read_parquet(path), batch], ignore_index=True)

        # A separate temporary file protects readers if writing is interrupted.
        with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
            temporary_path = Path(tmp.name)
        try:
            batch.to_parquet(temporary_path, index=False)
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return path


def load_trace_table(index_dir: str | Path) -> pd.DataFrame:
    """Load persisted traces, returning an empty frame if none exist."""
    path = trace_path(index_dir)
    return pd.read_parquet(path) if path.is_file() else pd.DataFrame()
