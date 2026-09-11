# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Persistence helpers for reproducible, query-level retrieval traces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pandas as pd
from data_config import retrieval_trace_table
from knowledge_loader.data_sources.typing import Datasource, WriteMode

if TYPE_CHECKING:
    from rag.typing import RetrievalTrace


def _encode(value: Any) -> str:
    """Encode nested trace fields as stable JSON strings in Parquet."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def trace_record(trace: RetrievalTrace) -> dict[str, Any]:
    """Flatten a trace without dropping any graph/path field."""
    record = trace.as_record()
    for key in (
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
    ):
        record[key] = _encode(record[key])
    return record


def save_trace(datasource: Datasource, trace: RetrievalTrace) -> None:
    """Append one trace to ``output/retrieval_traces.parquet``."""
    datasource.write(
        retrieval_trace_table,
        pd.DataFrame([trace_record(trace)]),
        mode=WriteMode.Append,
    )


def load_trace_table(datasource: Datasource) -> pd.DataFrame:
    """Load persisted traces, returning an empty frame if none exist."""
    return datasource.read(retrieval_trace_table)
