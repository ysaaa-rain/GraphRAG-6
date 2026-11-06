# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Query trace persistence tests using isolated temporary index directories."""

from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor

from graphrag6_retrieval.trace_store import load_trace_table, save_trace
from graphrag6_retrieval.typing import RetrievalTrace


def test_append_keeps_all_queries_and_graph_evidence() -> None:
    with tempfile.TemporaryDirectory() as directory:
        first = RetrievalTrace(
            query="Who connected Alpha and Beta?",
            method="hybrid_path",
            graph_paths=[{"entity_ids": ["alpha", "beta"], "relationship_ids": ["rel-1"]}],
        )
        second = RetrievalTrace(query="What happened next?", method="lightrag")
        save_trace(directory, first)
        save_trace(directory, second)
        rows = load_trace_table(directory)
        assert rows["query"].tolist() == [first.query, second.query]
        assert json.loads(rows.iloc[0]["graph_paths"])[0]["relationship_ids"] == ["rel-1"]


def test_parallel_trace_saves_do_not_overwrite_other_queries() -> None:
    with tempfile.TemporaryDirectory() as directory:
        def write(number: int) -> None:
            save_trace(directory, RetrievalTrace(query=f"query-{number}", method="hybrid_path"))

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(8)))

        rows = load_trace_table(directory)
        assert len(rows) == 8
        assert set(rows["query"].tolist()) == {f"query-{number}" for number in range(8)}
