# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Shared types for the selectable GraphRAG query modes."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class SearchType(Enum):
    """SearchType class definition."""

    Basic = "basic"
    Local = "local"
    Global = "global"
    Drift = "drift"
    LightRAG = "lightrag"
    HippoRAG2 = "hipporag2"
    HybridPath = "hybrid_path"


class SearchMethod(str, Enum):
    """User-selectable query engines.

    The first four entries are the existing Microsoft GraphRAG engines.  The
    other entries are local, schema-compatible implementations inspired by
    LightRAG and HippoRAG 2, plus this project's hybrid path method.
    """

    MICROSOFT_LOCAL = "microsoft_local"
    MICROSOFT_GLOBAL = "microsoft_global"
    MICROSOFT_DRIFT = "microsoft_drift"
    MICROSOFT_BASIC = "microsoft_basic"
    LIGHTRAG = "lightrag"
    HIPPORAG2 = "hipporag2"
    HYBRID_PATH = "hybrid_path"

    @property
    def label(self) -> str:
        """Chinese UI label for the method."""
        return {
            SearchMethod.MICROSOFT_LOCAL: "Microsoft GraphRAG · Local",
            SearchMethod.MICROSOFT_GLOBAL: "Microsoft GraphRAG · Global",
            SearchMethod.MICROSOFT_DRIFT: "Microsoft GraphRAG · DRIFT",
            SearchMethod.MICROSOFT_BASIC: "Microsoft Basic / Vector RAG",
            SearchMethod.LIGHTRAG: "LightRAG 风格 · 双层检索",
            SearchMethod.HIPPORAG2: "HippoRAG 2 风格 · PPR 多跳",
            SearchMethod.HYBRID_PATH: "本项目 · Hybrid Path GraphRAG",
        }[self]

    @property
    def search_type(self) -> SearchType:
        """Map a selectable method to the UI/result category."""
        return {
            SearchMethod.MICROSOFT_LOCAL: SearchType.Local,
            SearchMethod.MICROSOFT_GLOBAL: SearchType.Global,
            SearchMethod.MICROSOFT_DRIFT: SearchType.Drift,
            SearchMethod.MICROSOFT_BASIC: SearchType.Basic,
            SearchMethod.LIGHTRAG: SearchType.LightRAG,
            SearchMethod.HIPPORAG2: SearchType.HippoRAG2,
            SearchMethod.HYBRID_PATH: SearchType.HybridPath,
        }[self]


@dataclass
class RetrievalTrace:
    """Auditable retrieval output shared by all engines.

    ``path_recall`` is intentionally nullable for interactive queries.  It is
    populated by the evaluation adapter when a gold path/evidence set is
    supplied; an online retriever cannot know the gold answer by itself.
    """

    query: str
    method: str
    matched_entity_ids: list[str] = field(default_factory=list)
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    matched_relationship_ids: list[str] = field(default_factory=list)
    matched_relationships: list[dict[str, Any]] = field(default_factory=list)
    graph_paths: list[dict[str, Any]] = field(default_factory=list)
    subgraph_nodes: list[dict[str, Any]] = field(default_factory=list)
    subgraph_edges: list[dict[str, Any]] = field(default_factory=list)
    text_evidence: list[dict[str, Any]] = field(default_factory=list)
    retrieved_source_paths: list[str] = field(default_factory=list)
    path_recall: float | None = None
    path_recall_numerator: int = 0
    path_recall_denominator: int = 0
    evidence_recall: float | None = None
    evidence_recall_numerator: int = 0
    evidence_recall_denominator: int = 0
    channel_scores: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def as_record(self) -> dict[str, Any]:
        """Return a JSON-serializable record for trace persistence."""
        return {
            "query": self.query,
            "method": self.method,
            "matched_entity_ids": self.matched_entity_ids,
            "matched_entities": self.matched_entities,
            "matched_relationship_ids": self.matched_relationship_ids,
            "matched_relationships": self.matched_relationships,
            "graph_paths": self.graph_paths,
            "subgraph_nodes": self.subgraph_nodes,
            "subgraph_edges": self.subgraph_edges,
            "text_evidence": self.text_evidence,
            "retrieved_source_paths": self.retrieved_source_paths,
            "path_recall": self.path_recall,
            "path_recall_numerator": self.path_recall_numerator,
            "path_recall_denominator": self.path_recall_denominator,
            "evidence_recall": self.evidence_recall,
            "evidence_recall_numerator": self.evidence_recall_numerator,
            "evidence_recall_denominator": self.evidence_recall_denominator,
            "channel_scores": self.channel_scores,
            "created_at": self.created_at,
        }


@dataclass
class SearchResult:
    """SearchResult class definition."""

    # create a dataclass to store the search result of each algorithm
    search_type: SearchType
    response: str
    context: dict[str, pd.DataFrame]
    method: SearchMethod | None = None
    trace: RetrievalTrace | None = None
