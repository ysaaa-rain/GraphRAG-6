# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License
# ruff: noqa: S101

"""Unit tests for the dependency-free custom GraphRAG retrieval policies."""

import json

import pandas as pd
from rag.retrieval import GraphRetriever, path_recall, source_recall
from rag.trace_store import trace_record
from rag.typing import SearchMethod


def make_retriever() -> GraphRetriever:
    """Build a three-node graph for deterministic unit tests."""
    entities = pd.DataFrame([
        {
            "id": "e-a",
            "human_readable_id": 0,
            "title": "Alpha",
            "description": "project alpha",
        },
        {
            "id": "e-b",
            "human_readable_id": 1,
            "title": "Beta",
            "description": "project beta",
        },
        {
            "id": "e-c",
            "human_readable_id": 2,
            "title": "Gamma",
            "description": "project gamma",
        },
    ])
    relationships = pd.DataFrame([
        {
            "id": "r-ab",
            "human_readable_id": 0,
            "source": "Alpha",
            "target": "Beta",
            "weight": 2.0,
            "description": "alpha owns beta",
        },
        {
            "id": "r-bc",
            "human_readable_id": 1,
            "source": "Beta",
            "target": "Gamma",
            "weight": 1.0,
            "description": "beta reports gamma",
        },
    ])
    text_units = pd.DataFrame([
        {
            "id": "t-a",
            "human_readable_id": 0,
            "entity_ids": ["e-a"],
            "relationship_ids": [],
            "text": "Alpha evidence",
            "source_path": "mail/a",
        },
        {
            "id": "t-c",
            "human_readable_id": 1,
            "entity_ids": ["e-c"],
            "relationship_ids": ["r-bc"],
            "text": "Gamma evidence",
            "source_path": "mail/c",
        },
    ])
    return GraphRetriever(entities, relationships, text_units)


def test_lightrag_style_returns_low_and_high_level_context():
    """LightRAG style retrieval returns entity-linked text evidence."""
    bundle = make_retriever().retrieve("Alpha", SearchMethod.LIGHTRAG)

    assert "e-a" in bundle.trace.matched_entity_ids
    assert bundle.trace.text_evidence
    assert bundle.trace.method == SearchMethod.LIGHTRAG.value


def test_hipporag_style_exposes_graph_path():
    """HippoRAG style retrieval exposes graph paths."""
    bundle = make_retriever().retrieve("Alpha", SearchMethod.HIPPORAG2)

    assert bundle.trace.graph_paths
    assert all("relationship_ids" in path for path in bundle.trace.graph_paths)


def test_hybrid_path_fuses_dense_candidate_and_path():
    """Hybrid Path combines a dense candidate with a graph path."""
    bundle = make_retriever().retrieve(
        "Alpha",
        SearchMethod.HYBRID_PATH,
        vector_scores={"t-c": 1.0},
    )

    assert "t-c" in bundle.trace.matched_entity_ids or any(
        row.get("id") == "t-c" for row in bundle.trace.text_evidence
    )
    assert any(path["target_text_id"] == "t-c" for path in bundle.trace.graph_paths)


def test_path_and_source_recall_are_explicit_metrics():
    """Path and source recall expose numerator and denominator."""
    paths = [{"entity_ids": ["e-a", "e-b"], "relationship_ids": ["r-ab"]}]
    assert path_recall(paths, paths) == (1.0, 1, 1)
    assert source_recall(["mail/a"], ["mail/a", "mail/b"]) == (0.5, 1, 2)


def test_trace_record_preserves_nested_graph_fields_and_id_aliases():
    """Trace persistence keeps nested fields and resolves short IDs."""
    retriever = make_retriever()
    assert retriever.normalize_external_scores({"1": 0.8}, "text") == {"t-c": 0.8}

    trace = retriever.retrieve("Alpha", SearchMethod.HIPPORAG2).trace
    record = trace_record(trace)

    assert json.loads(record["matched_entity_ids"])
    assert json.loads(record["subgraph_edges"])
    assert json.loads(record["graph_paths"])
