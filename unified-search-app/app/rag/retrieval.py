# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Schema-compatible graph retrieval algorithms.

The module deliberately works on the Parquet tables produced by Microsoft
GraphRAG instead of introducing a second indexing format.  It provides three
retrieval policies:

* ``lightrag``: low-level entity matching plus high-level community matching;
* ``hipporag2``: entity seeds followed by weighted personalized PageRank;
* ``hybrid_path``: BM25-style lexical, optional dense-vector, and constrained
  graph-path fusion.

These are faithful engineering adaptations of the published ideas, not claims
to be the original projects' reference implementations.  Keeping the
algorithms pure makes them testable without an LLM or vector database.
"""

from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
from rag.typing import RetrievalTrace, SearchMethod

if TYPE_CHECKING:
    from collections.abc import Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]")


def tokenize(text: Any) -> list[str]:
    """Tokenize English terms and individual CJK characters."""
    if text is None:
        return []
    return [token.lower() for token in TOKEN_RE.findall(str(text))]


def _as_list(value: Any) -> list[str]:
    """Normalize a Parquet list column that may have been stringified."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(raw)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            if isinstance(parsed, (list, tuple, set)):
                return [str(item) for item in parsed if item is not None]
        return [raw]
    try:
        if bool(pd.isna(value)):
            return []
    except (TypeError, ValueError):
        pass
    return [str(value)]


def _text(value: Any) -> str:
    """Convert nullable/scalar/list values into searchable text."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set, dict)):
        return " ".join(_text(item) for item in value)
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _record_id(row: pd.Series) -> str:
    """Read either the stable UUID or the human-readable GraphRAG ID."""
    for column in ("id", "human_readable_id", "short_id"):
        if column in row and _text(row[column]):
            return _text(row[column])
    return ""


def _jsonable(value: Any) -> Any:
    """Make a pandas row safe for JSON and Markdown rendering."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        value = value.item()
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def row_record(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """Convert a dataframe row to a JSON-safe dictionary."""
    source = row.to_dict() if isinstance(row, pd.Series) else row
    return {str(key): _jsonable(value) for key, value in source.items()}


def _frame(value: Any) -> pd.DataFrame:
    """Normalize native GraphRAG context values to dataframes."""
    if isinstance(value, pd.DataFrame):
        return value
    if value is None:
        return pd.DataFrame()
    if isinstance(value, dict):
        return pd.DataFrame([value])
    try:
        return pd.DataFrame(value)
    except (TypeError, ValueError):
        return pd.DataFrame()


class BM25:
    """Small dependency-free BM25 scorer for the in-memory query path."""

    def __init__(self, documents: dict[str, str], k1: float = 1.2, b: float = 0.75):
        """Build an index from stable record IDs to searchable text."""
        self.k1 = k1
        self.b = b
        self.ids = list(documents)
        self.tokens = {key: tokenize(value) for key, value in documents.items()}
        self.lengths = {key: len(value) for key, value in self.tokens.items()}
        self.avgdl = sum(self.lengths.values()) / max(len(self.ids), 1)
        self.doc_frequency: Counter[str] = Counter()
        for values in self.tokens.values():
            self.doc_frequency.update(set(values))

    def score(self, query: str) -> dict[str, float]:
        """Return BM25 scores for every indexed document."""
        query_terms = set(tokenize(query))
        scores: dict[str, float] = {}
        count = len(self.ids)
        for doc_id in self.ids:
            frequencies = Counter(self.tokens[doc_id])
            length = self.lengths[doc_id]
            total = 0.0
            for term in query_terms:
                df = self.doc_frequency.get(term, 0)
                if not df:
                    continue
                idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
                tf = frequencies.get(term, 0)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * length / max(self.avgdl, 1e-9)
                )
                total += idf * (tf * (self.k1 + 1) / max(denominator, 1e-9))
            scores[doc_id] = total
        return scores


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Scale a score channel to [0, 1] while preserving zeros."""
    if not scores:
        return {}
    positive = [value for value in scores.values() if value > 0]
    if not positive:
        return dict.fromkeys(scores, 0.0)
    minimum = min(positive)
    maximum = max(positive)
    if math.isclose(minimum, maximum):
        return {key: 1.0 if value > 0 else 0.0 for key, value in scores.items()}
    return {
        key: max(0.0, (value - minimum) / (maximum - minimum))
        for key, value in scores.items()
    }


@dataclass
class RetrievalConfig:
    """Controls shared retrieval budgets across custom methods."""

    top_k_entities: int = 12
    top_k_relationships: int = 18
    top_k_sources: int = 12
    top_k_reports: int = 6
    max_hops: int = 2
    pagerank_alpha: float = 0.15
    pagerank_iterations: int = 30
    lexical_weight: float = 0.35
    vector_weight: float = 0.35
    graph_weight: float = 0.30


@dataclass
class RetrievalBundle:
    """Candidate context plus the full trace used to produce it."""

    context: dict[str, pd.DataFrame]
    context_text: str
    trace: RetrievalTrace


class GraphRetriever:
    """Retrieve from Microsoft GraphRAG output tables with explicit paths."""

    def __init__(
        self,
        entities: pd.DataFrame,
        relationships: pd.DataFrame,
        text_units: pd.DataFrame,
        community_reports: pd.DataFrame | None = None,
        communities: pd.DataFrame | None = None,
        documents: pd.DataFrame | None = None,
        config: RetrievalConfig | None = None,
    ):
        self.entities_df = entities.copy() if entities is not None else pd.DataFrame()
        self.relationships_df = (
            relationships.copy() if relationships is not None else pd.DataFrame()
        )
        self.text_units_df = (
            text_units.copy() if text_units is not None else pd.DataFrame()
        )
        self.community_reports_df = (
            community_reports.copy()
            if community_reports is not None
            else pd.DataFrame()
        )
        self.communities_df = (
            communities.copy() if communities is not None else pd.DataFrame()
        )
        self.documents_df = (
            documents.copy() if documents is not None else pd.DataFrame()
        )
        self.config = config or RetrievalConfig()

        self.entity_rows = {
            _record_id(row): row
            for _, row in self.entities_df.iterrows()
            if _record_id(row)
        }
        self.entity_title_to_id = {
            _text(row.get("title")).strip().lower(): entity_id
            for entity_id, row in self.entity_rows.items()
            if _text(row.get("title")).strip()
        }
        self.entity_short_to_id = {
            _text(row.get("human_readable_id")).strip(): entity_id
            for entity_id, row in self.entity_rows.items()
            if _text(row.get("human_readable_id")).strip()
        }
        self.relationship_rows = {
            _record_id(row): row
            for _, row in self.relationships_df.iterrows()
            if _record_id(row)
        }
        self.relationship_short_to_id = {
            _text(row.get("human_readable_id")).strip(): relationship_id
            for relationship_id, row in self.relationship_rows.items()
            if _text(row.get("human_readable_id")).strip()
        }
        self.text_rows = {
            _record_id(row): row
            for _, row in self.text_units_df.iterrows()
            if _record_id(row)
        }
        self.text_short_to_id = {
            _text(row.get("human_readable_id")).strip(): text_id
            for text_id, row in self.text_rows.items()
            if _text(row.get("human_readable_id")).strip()
        }
        self.adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for relationship_id, row in self.relationship_rows.items():
            source = self._entity_ref(_text(row.get("source")))
            target = self._entity_ref(_text(row.get("target")))
            if source and target:
                self.adjacency[source].append((target, relationship_id))
                self.adjacency[target].append((source, relationship_id))

        self.entity_bm25 = BM25({
            entity_id: self._entity_search_text(row)
            for entity_id, row in self.entity_rows.items()
        })
        self.text_bm25 = BM25({
            text_id: self._text_search_text(row)
            for text_id, row in self.text_rows.items()
        })
        self.relationship_bm25 = BM25({
            relationship_id: self._relationship_search_text(row)
            for relationship_id, row in self.relationship_rows.items()
        })
        self.report_bm25 = BM25({
            _record_id(row): self._report_search_text(row)
            for _, row in self.community_reports_df.iterrows()
            if _record_id(row)
        })

    def _entity_ref(self, value: str) -> str:
        """Resolve an endpoint stored as UUID, short ID, or title."""
        if value in self.entity_rows:
            return value
        if value in self.entity_short_to_id:
            return self.entity_short_to_id[value]
        return self.entity_title_to_id.get(value.strip().lower(), "")

    def _relationship_ref(self, value: str) -> str:
        if value in self.relationship_rows:
            return value
        return self.relationship_short_to_id.get(value.strip(), "")

    def _text_ref(self, value: str) -> str:
        if value in self.text_rows:
            return value
        return self.text_short_to_id.get(value.strip(), "")

    def normalize_external_scores(
        self, scores: dict[str, float] | None, kind: str
    ) -> dict[str, float]:
        """Map vector-store IDs from stable/short IDs to stable graph IDs."""
        scores = scores or {}
        resolver = {
            "entity": self._entity_ref,
            "text": self._text_ref,
        }.get(kind)
        if resolver is None:
            error_message = f"Unsupported score kind: {kind}"
            raise ValueError(error_message)
        normalized: dict[str, float] = {}
        for raw_id, score in scores.items():
            resolved_id = resolver(str(raw_id))
            if resolved_id:
                normalized[resolved_id] = max(
                    normalized.get(resolved_id, 0.0), float(score)
                )
        return normalized

    @staticmethod
    def _entity_search_text(row: pd.Series) -> str:
        return " ".join(
            _text(row.get(column)) for column in ("title", "type", "description")
        )

    @staticmethod
    def _relationship_search_text(row: pd.Series) -> str:
        return " ".join(
            _text(row.get(column)) for column in ("source", "target", "description")
        )

    @staticmethod
    def _text_search_text(row: pd.Series) -> str:
        return " ".join(
            _text(row.get(column))
            for column in ("text", "title", "source_path", "document_id")
        )

    @staticmethod
    def _report_search_text(row: pd.Series) -> str:
        return " ".join(
            _text(row.get(column))
            for column in ("title", "summary", "full_content", "full_content_json")
        )

    def _community_entity_ids(self, report_ids: Iterable[str]) -> set[str]:
        """Return entities belonging to selected reports/communities."""
        report_communities = {
            _record_id(row): _text(row.get("community"))
            for _, row in self.community_reports_df.iterrows()
            if _record_id(row) and _text(row.get("community"))
        }
        communities = {
            report_communities.get(str(report_id), "")
            for report_id in report_ids
            if str(report_id) in report_communities
        }
        entity_ids: set[str] = set()
        if self.communities_df.empty:
            return entity_ids
        for _, row in self.communities_df.iterrows():
            if _text(row.get("community")) in communities:
                entity_ids.update(
                    entity_id
                    for value in _as_list(row.get("entity_ids"))
                    if (entity_id := self._entity_ref(value))
                )
        return entity_ids

    def _selected_relationship_ids(self, entity_ids: set[str]) -> set[str]:
        selected: set[str] = set()
        for relationship_id, row in self.relationship_rows.items():
            source = self._entity_ref(_text(row.get("source")))
            target = self._entity_ref(_text(row.get("target")))
            if source in entity_ids and target in entity_ids:
                selected.add(relationship_id)
        return selected

    def _relationship_weight(self, relationship_id: str) -> float:
        """Return a positive edge weight, tolerating nullable/non-numeric data."""
        value = _text(self.relationship_rows[relationship_id].get("weight"))
        try:
            return max(float(value), 0.01) if value else 1.0
        except (TypeError, ValueError):
            return 1.0

    def _shortest_path(self, start: str, target: str) -> tuple[list[str], list[str]]:
        """Return the shortest entity and relationship path, if one exists."""
        if start == target:
            return [start], []
        queue: deque[str] = deque([start])
        parents: dict[str, tuple[str, str] | None] = {start: None}
        while queue:
            current = queue.popleft()
            for neighbor, relationship_id in self.adjacency.get(current, []):
                if neighbor in parents:
                    continue
                parents[neighbor] = (current, relationship_id)
                if neighbor == target:
                    queue.clear()
                    break
                queue.append(neighbor)
        if target not in parents:
            return [], []
        entities = [target]
        relationships: list[str] = []
        current = target
        while parents[current] is not None:
            parent, relationship_id = parents[current]  # type: ignore[misc]
            entities.append(parent)
            relationships.append(relationship_id)
            current = parent
        entities.reverse()
        relationships.reverse()
        if len(relationships) > self.config.max_hops:
            return [], []
        return entities, relationships

    def _make_paths(
        self,
        seeds: Iterable[str],
        targets: Iterable[str],
        entity_scores: dict[str, float],
    ) -> list[dict[str, Any]]:
        paths: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for target in targets:
            best: tuple[list[str], list[str]] = ([], [])
            for seed in seeds:
                candidate = self._shortest_path(seed, target)
                if candidate[0] and (not best[0] or len(candidate[1]) < len(best[1])):
                    best = candidate
            if not best[0]:
                continue
            key = tuple(best[0])
            if key in seen:
                continue
            seen.add(key)
            paths.append({
                "path_id": f"path-{len(paths) + 1}",
                "entity_ids": best[0],
                "relationship_ids": best[1],
                "hops": len(best[1]),
                "score": round(
                    max(entity_scores.get(item, 0.0) for item in best[0]), 6
                ),
            })
        paths.sort(key=lambda item: (-item["score"], item["hops"], item["path_id"]))
        return paths

    def _pagerank(self, seeds: dict[str, float]) -> dict[str, float]:
        """Run weighted personalized PageRank over the entity graph."""
        nodes = set(self.entity_rows)
        if not nodes:
            return {}
        personalization = normalize_scores({
            node: seeds.get(node, 0.0) for node in nodes
        })
        total = sum(personalization.values())
        if total <= 0:
            personalization = {node: 1 / len(nodes) for node in nodes}
        else:
            personalization = {
                node: value / total for node, value in personalization.items()
            }
        ranks = personalization.copy()
        alpha = self.config.pagerank_alpha
        for _ in range(self.config.pagerank_iterations):
            next_ranks = {node: alpha * personalization[node] for node in nodes}
            for node, rank in ranks.items():
                neighbors = self.adjacency.get(node, [])
                if not neighbors:
                    for target in nodes:
                        next_ranks[target] += (
                            (1 - alpha) * rank * personalization[target]
                        )
                    continue
                weight_sum = sum(
                    self._relationship_weight(relationship_id)
                    for _, relationship_id in neighbors
                )
                for target, relationship_id in neighbors:
                    next_ranks[target] += (
                        (1 - alpha)
                        * rank
                        * self._relationship_weight(relationship_id)
                        / max(weight_sum, 1e-9)
                    )
            ranks = next_ranks
        return ranks

    def _source_path(self, row: pd.Series) -> str:
        """Resolve source path from text-unit attributes or document table."""
        for column in ("source_path", "document_path", "path", "title"):
            value = _text(row.get(column))
            if value:
                return value
        attributes = row.get("attributes")
        if isinstance(attributes, str):
            try:
                attributes = json.loads(attributes)
            except json.JSONDecodeError:
                attributes = {}
        if isinstance(attributes, dict):
            for key in ("source_path", "document_path", "path", "title"):
                if _text(attributes.get(key)):
                    return _text(attributes[key])
        document_id = _text(row.get("document_id"))
        if document_id and not self.documents_df.empty and "id" in self.documents_df:
            matches = self.documents_df[
                self.documents_df["id"].astype(str) == document_id
            ]
            if not matches.empty:
                document = matches.iloc[0]
                for column in ("source_path", "path", "title"):
                    value = _text(document.get(column))
                    if value:
                        return value
                raw_content = _text(document.get("raw_content"))
                source_match = re.search(
                    r"^\s*Source path:\s*(\S+)", raw_content, flags=re.MULTILINE
                )
                if source_match:
                    return source_match.group(1)
        return document_id

    def _selected_frames(
        self,
        entity_scores: dict[str, float],
        relationship_scores: dict[str, float],
        text_scores: dict[str, float],
        report_scores: dict[str, float] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Attach retrieval scores to context frames for UI and evaluation."""
        report_scores = report_scores or {}

        def frame(rows: dict[str, pd.Series], scores: dict[str, float], limit: int):
            selected = sorted(
                (
                    (key, value)
                    for key, value in scores.items()
                    if key in rows and value > 0
                ),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
            records = []
            for key, score in selected:
                record = row_record(rows[key])
                record["retrieval_score"] = round(score, 6)
                records.append(record)
            return pd.DataFrame(records)

        sources = frame(self.text_rows, text_scores, self.config.top_k_sources)
        if not sources.empty:
            sources["source_path"] = sources.apply(self._source_path, axis=1)
        reports = frame(
            {
                _record_id(row): row
                for _, row in self.community_reports_df.iterrows()
                if _record_id(row)
            },
            report_scores,
            self.config.top_k_reports,
        )
        return {
            "entities": frame(
                self.entity_rows, entity_scores, self.config.top_k_entities
            ),
            "relationships": frame(
                self.relationship_rows,
                relationship_scores,
                self.config.top_k_relationships,
            ),
            "sources": sources,
            "reports": reports,
        }

    def _context_text(
        self,
        context: dict[str, pd.DataFrame],
        paths: list[dict[str, Any]],
    ) -> str:
        """Serialize the selected evidence into a stable LLM prompt context."""
        parts: list[str] = []
        labels = {
            "entities": "Entities",
            "relationships": "Relationships",
            "sources": "Sources",
            "reports": "Community reports",
        }
        for key in ("entities", "relationships", "sources", "reports"):
            frame = context.get(key)
            if frame is not None and not frame.empty:
                parts.append(f"[{labels[key]}]\n{frame.to_csv(index=False, sep='|')}")
        if paths:
            parts.append(f"[Graph paths]\n{json.dumps(paths, ensure_ascii=False)}")
        return "\n\n".join(parts)

    def _trace(
        self,
        query: str,
        method: SearchMethod,
        context: dict[str, pd.DataFrame],
        paths: list[dict[str, Any]],
        channel_scores: dict[str, Any],
    ) -> RetrievalTrace:
        entities = _frame(context.get("entities"))
        relationships = _frame(context.get("relationships"))
        sources = _frame(context.get("sources"))
        entity_ids = [
            _record_id(row) for _, row in entities.iterrows() if _record_id(row)
        ]
        relationship_ids = [
            _record_id(row) for _, row in relationships.iterrows() if _record_id(row)
        ]
        source_paths = sorted({
            _text(value)
            for value in sources.get("source_path", pd.Series(dtype=str)).tolist()
            if _text(value)
        })
        subgraph_nodes = []
        for _, row in entities.iterrows():
            subgraph_nodes.append({
                "id": _record_id(row),
                "title": _text(row.get("title")),
                "type": _text(row.get("type")),
                "seed": _record_id(row) in channel_scores.get("seed_entity_ids", []),
            })
        subgraph_edges = []
        for _, row in relationships.iterrows():
            subgraph_edges.append({
                "id": _record_id(row),
                "source": self._entity_ref(_text(row.get("source")))
                or _text(row.get("source")),
                "target": self._entity_ref(_text(row.get("target")))
                or _text(row.get("target")),
                "description": _text(row.get("description")),
                "weight": _jsonable(row.get("weight")),
            })
        return RetrievalTrace(
            query=query,
            method=method.value,
            matched_entity_ids=entity_ids,
            matched_entities=[row_record(row) for _, row in entities.iterrows()],
            matched_relationship_ids=relationship_ids,
            matched_relationships=[
                row_record(row) for _, row in relationships.iterrows()
            ],
            graph_paths=paths,
            subgraph_nodes=subgraph_nodes,
            subgraph_edges=subgraph_edges,
            text_evidence=[row_record(row) for _, row in sources.iterrows()],
            retrieved_source_paths=source_paths,
            channel_scores=channel_scores,
            created_at=datetime.now(UTC).isoformat(),
        )

    def retrieve(
        self,
        query: str,
        method: SearchMethod,
        vector_scores: dict[str, float] | None = None,
        entity_vector_scores: dict[str, float] | None = None,
    ) -> RetrievalBundle:
        """Run one of the custom retrieval policies."""
        vector_scores = normalize_scores(vector_scores or {})
        entity_vector_scores = normalize_scores(entity_vector_scores or {})
        lexical_entities = normalize_scores(self.entity_bm25.score(query))
        lexical_text = normalize_scores(self.text_bm25.score(query))
        lexical_relationships = normalize_scores(self.relationship_bm25.score(query))
        lexical_reports = normalize_scores(self.report_bm25.score(query))

        if method is SearchMethod.LIGHTRAG:
            report_ids = {
                report_id for report_id, score in lexical_reports.items() if score > 0
            }
            high_level_entities = self._community_entity_ids(report_ids)
            entity_scores = {
                entity_id: max(score, 0.8 if entity_id in high_level_entities else 0.0)
                for entity_id, score in lexical_entities.items()
            }
            selected_entity_ids = {
                entity_id
                for entity_id, score in sorted(
                    entity_scores.items(), key=lambda item: (-item[1], item[0])
                )[: self.config.top_k_entities]
                if score > 0
            }
            relationship_scores = {
                relationship_id: max(
                    lexical_relationships.get(relationship_id, 0.0),
                    0.75
                    if relationship_id
                    in self._selected_relationship_ids(selected_entity_ids)
                    else 0.0,
                )
                for relationship_id in self.relationship_rows
            }
            text_scores = {
                text_id: max(
                    lexical_text.get(text_id, 0.0),
                    vector_scores.get(text_id, 0.0),
                    max(
                        [
                            entity_scores.get(self._entity_ref(value), 0.0)
                            for value in _as_list(row.get("entity_ids"))
                        ]
                        + [0.0]
                    )
                    * 0.8,
                )
                for text_id, row in self.text_rows.items()
            }
            paths = self._make_paths(
                [key for key, value in lexical_entities.items() if value > 0],
                selected_entity_ids,
                entity_scores,
            )
            selected_reports = lexical_reports
            channels = {
                "low_level_entity": lexical_entities,
                "high_level_community": lexical_reports,
                "dense_vector": vector_scores,
                "seed_entity_ids": list(lexical_entities),
            }
        elif method is SearchMethod.HIPPORAG2:
            seed_scores = {
                entity_id: max(
                    lexical_entities.get(entity_id, 0.0),
                    entity_vector_scores.get(entity_id, 0.0),
                )
                for entity_id in self.entity_rows
            }
            pagerank_scores = self._pagerank(seed_scores)
            entity_scores = {
                entity_id: 0.65 * pagerank_scores.get(entity_id, 0.0)
                + 0.35
                * max(
                    lexical_entities.get(entity_id, 0.0),
                    entity_vector_scores.get(entity_id, 0.0),
                )
                for entity_id in self.entity_rows
            }
            selected_entity_ids = {
                entity_id
                for entity_id, score in sorted(
                    entity_scores.items(), key=lambda item: (-item[1], item[0])
                )[: self.config.top_k_entities]
                if score > 0
            }
            induced_relationships = self._selected_relationship_ids(selected_entity_ids)
            relationship_scores = {
                relationship_id: max(
                    lexical_relationships.get(relationship_id, 0.0),
                    0.7 if relationship_id in induced_relationships else 0.0,
                )
                for relationship_id in self.relationship_rows
            }
            text_scores = {
                text_id: max(
                    lexical_text.get(text_id, 0.0),
                    vector_scores.get(text_id, 0.0),
                    max(
                        [
                            entity_scores.get(self._entity_ref(value), 0.0)
                            for value in _as_list(row.get("entity_ids"))
                        ]
                        + [0.0]
                    ),
                )
                for text_id, row in self.text_rows.items()
            }
            paths = self._make_paths(
                [key for key, value in lexical_entities.items() if value > 0],
                selected_entity_ids,
                entity_scores,
            )
            selected_reports = lexical_reports
            channels = {
                "seed_entity": seed_scores,
                "personalized_pagerank": pagerank_scores,
                "dense_vector": entity_vector_scores,
                "seed_entity_ids": list(lexical_entities),
            }
        else:
            # The project's method is a score-level fusion with path constraints:
            # vector/lexical text candidates are only graph-expanded when a seed
            # entity can reach their entities within max_hops.
            entity_scores = {
                entity_id: 0.65 * lexical_entities.get(entity_id, 0.0)
                + 0.35 * entity_vector_scores.get(entity_id, 0.0)
                for entity_id in self.entity_rows
            }
            seed_ids = [
                entity_id
                for entity_id, score in sorted(
                    entity_scores.items(), key=lambda item: (-item[1], item[0])
                )[: self.config.top_k_entities]
                if score > 0
            ]
            graph_scores: dict[str, float] = {}
            paths = []
            text_scores = {}
            for text_id, row in self.text_rows.items():
                text_entity_ids = [
                    self._entity_ref(value) for value in _as_list(row.get("entity_ids"))
                ]
                best_path_score = 0.0
                for target in text_entity_ids:
                    for seed in seed_ids:
                        entity_path, relationship_path = self._shortest_path(
                            seed, target
                        )
                        if not entity_path:
                            continue
                        score = entity_scores.get(seed, 0.0) / (
                            1 + len(relationship_path)
                        )
                        best_path_score = max(best_path_score, score)
                        paths.append({
                            "path_id": f"path-{len(paths) + 1}",
                            "entity_ids": entity_path,
                            "relationship_ids": relationship_path,
                            "hops": len(relationship_path),
                            "score": round(score, 6),
                            "target_text_id": text_id,
                        })
                graph_scores[text_id] = best_path_score
                text_scores[text_id] = (
                    self.config.lexical_weight * lexical_text.get(text_id, 0.0)
                    + self.config.vector_weight * vector_scores.get(text_id, 0.0)
                    + self.config.graph_weight * best_path_score
                )
            paths = sorted(
                {json.dumps(path, sort_keys=True): path for path in paths}.values(),
                key=lambda item: (-item["score"], item["hops"], item["path_id"]),
            )[: self.config.top_k_sources]
            selected_entity_ids = set(seed_ids)
            for path in paths:
                selected_entity_ids.update(path["entity_ids"])
            entity_scores = {
                entity_id: score
                for entity_id, score in entity_scores.items()
                if entity_id in selected_entity_ids
            }
            relationship_ids = self._selected_relationship_ids(selected_entity_ids)
            relationship_scores = {
                relationship_id: max(
                    lexical_relationships.get(relationship_id, 0.0),
                    0.8 if relationship_id in relationship_ids else 0.0,
                )
                for relationship_id in self.relationship_rows
            }
            selected_reports = lexical_reports
            channels = {
                "lexical_bm25": lexical_text,
                "dense_vector": vector_scores,
                "graph_path_proximity": graph_scores,
                "seed_entity_ids": seed_ids,
                "weights": {
                    "lexical": self.config.lexical_weight,
                    "vector": self.config.vector_weight,
                    "graph": self.config.graph_weight,
                },
            }

        context = self._selected_frames(
            entity_scores=entity_scores,
            relationship_scores=relationship_scores,
            text_scores=text_scores,
            report_scores=selected_reports,
        )
        trace = self._trace(query, method, context, paths, channels)
        return RetrievalBundle(
            context=context,
            context_text=self._context_text(context, paths),
            trace=trace,
        )


def path_recall(
    retrieved_paths: Iterable[dict[str, Any]],
    gold_paths: Iterable[dict[str, Any]],
) -> tuple[float | None, int, int]:
    """Compute exact entity-edge path recall for an evaluation record."""
    gold = {
        (
            tuple(str(item) for item in path.get("entity_ids", [])),
            tuple(str(item) for item in path.get("relationship_ids", [])),
        )
        for path in gold_paths
    }
    if not gold:
        return None, 0, 0
    retrieved = {
        (
            tuple(str(item) for item in path.get("entity_ids", [])),
            tuple(str(item) for item in path.get("relationship_ids", [])),
        )
        for path in retrieved_paths
    }
    numerator = len(gold.intersection(retrieved))
    return numerator / len(gold), numerator, len(gold)


def source_recall(
    retrieved: Iterable[str], gold: Iterable[str]
) -> tuple[float | None, int, int]:
    """Compute source/evidence recall for datasets with gold source paths."""
    gold_set = {str(item) for item in gold if str(item)}
    if not gold_set:
        return None, 0, 0
    numerator = len(gold_set.intersection(str(item) for item in retrieved))
    return numerator / len(gold_set), numerator, len(gold_set)


def annotate_trace_metrics(
    trace: RetrievalTrace,
    gold_paths: Iterable[dict[str, Any]] | None = None,
    gold_source_paths: Iterable[str] | None = None,
) -> RetrievalTrace:
    """Attach gold-path and gold-source recall to an existing trace."""
    if gold_paths is not None:
        recall, numerator, denominator = path_recall(trace.graph_paths, gold_paths)
        trace.path_recall = recall
        trace.path_recall_numerator = numerator
        trace.path_recall_denominator = denominator
    if gold_source_paths is not None:
        recall, numerator, denominator = source_recall(
            trace.retrieved_source_paths, gold_source_paths
        )
        trace.evidence_recall = recall
        trace.evidence_recall_numerator = numerator
        trace.evidence_recall_denominator = denominator
    return trace


def trace_from_context(
    query: str,
    method: SearchMethod,
    context: dict[str, pd.DataFrame],
    retriever: GraphRetriever | None = None,
) -> RetrievalTrace:
    """Create the same trace schema for native Microsoft search outputs."""
    entities = _frame(context.get("entities"))
    relationships = _frame(context.get("relationships"))
    sources = _frame(context.get("sources"))
    reports = _frame(context.get("reports"))
    entity_records = [row_record(row) for _, row in entities.iterrows()]
    relationship_records = [row_record(row) for _, row in relationships.iterrows()]
    source_records = [row_record(row) for _, row in sources.iterrows()]
    if retriever is not None:
        for record in source_records:
            text_id = retriever._text_ref(  # noqa: SLF001
                _record_id(pd.Series(record))
            )
            if text_id in retriever.text_rows and not _text(record.get("source_path")):
                record["source_path"] = retriever._source_path(  # noqa: SLF001
                    retriever.text_rows[text_id]
                )
    entity_ids = [_record_id(row) for _, row in entities.iterrows() if _record_id(row)]
    relationship_ids = [
        _record_id(row) for _, row in relationships.iterrows() if _record_id(row)
    ]
    paths: list[dict[str, Any]] = []
    if retriever is not None and entity_ids:
        paths = retriever._make_paths(  # noqa: SLF001
            entity_ids[:1], entity_ids[1:], dict.fromkeys(entity_ids, 1.0)
        )
    subgraph_nodes = [
        {
            "id": _record_id(row),
            "title": _text(row.get("title")),
            "type": _text(row.get("type")),
            "seed": index == 0,
        }
        for index, (_, row) in enumerate(entities.iterrows())
    ]

    def endpoint(row: pd.Series, column: str) -> str:
        raw_value = _text(row.get(column))
        if retriever is None:
            return raw_value
        return retriever._entity_ref(raw_value) or raw_value  # noqa: SLF001

    subgraph_edges = [
        {
            "id": _record_id(row),
            "source": endpoint(row, "source"),
            "target": endpoint(row, "target"),
            "description": _text(row.get("description")),
            "weight": _jsonable(row.get("weight")),
        }
        for _, row in relationships.iterrows()
    ]
    source_paths = sorted({
        _text(record.get("source_path"))
        for record in source_records
        if _text(record.get("source_path"))
    })
    return RetrievalTrace(
        query=query,
        method=method.value,
        matched_entity_ids=entity_ids,
        matched_entities=entity_records,
        matched_relationship_ids=relationship_ids,
        matched_relationships=relationship_records,
        graph_paths=paths,
        subgraph_nodes=subgraph_nodes,
        subgraph_edges=subgraph_edges,
        text_evidence=source_records,
        retrieved_source_paths=source_paths,
        channel_scores={
            "native_microsoft_context": True,
            "report_count": len(reports),
        },
        created_at=datetime.now(UTC).isoformat(),
    )
