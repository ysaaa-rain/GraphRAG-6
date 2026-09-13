# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""证据链展示层的测试：只用 pandas，不需要 streamlit / graphrag。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import trace_view  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from graphrag6_retrieval.retrieval import row_record  # noqa: E402
from graphrag6_retrieval.typing import RetrievalTrace  # noqa: E402


def make_trace() -> RetrievalTrace:
    """一条包含路径、seed、悬挂边的 trace。"""
    return RetrievalTrace(
        query="谁参与了电力危机？",
        method="hybrid_path",
        matched_entity_ids=["e-a", "e-b"],
        matched_entities=[
            {"id": "e-a", "title": "Alpha", "type": "person"},
            {"id": "e-b", "title": "Beta", "type": "organization"},
        ],
        matched_relationship_ids=["r-ab"],
        matched_relationships=[
            {"id": "r-ab", "source": "e-a", "target": "e-b", "description": "link"}
        ],
        graph_paths=[
            {
                "path_id": "path-1",
                "entity_ids": ["e-a", "e-b"],
                "relationship_ids": ["r-ab"],
                "hops": 1,
                "score": 0.9,
            }
        ],
        subgraph_nodes=[
            {"id": "e-a", "title": "Alpha", "type": "person", "seed": True},
            {"id": "e-b", "title": "Beta", "type": "organization", "seed": False},
        ],
        subgraph_edges=[
            {"id": "r-ab", "source": "e-a", "target": "e-b", "description": "link"},
            {"id": "r-bc", "source": "e-b", "target": "e-c", "description": "dangling"},
        ],
        text_evidence=[{"id": "tu-1", "source_path": "mail/1"}],
        retrieved_source_paths=["mail/1"],
        channel_scores={
            "lexical": 0.4,
            "vector": {"e-a": 0.7},
            "seed_entity_ids": ["e-a"],
        },
    )


class TestTraceView(unittest.TestCase):
    """表格化与 DOT 生成。"""

    def setUp(self):
        self.trace = make_trace()

    def test_summary_counts(self):
        stats = trace_view.summary(self.trace)
        self.assertEqual(stats["命中实体"], 2)
        self.assertEqual(stats["命中关系"], 1)
        self.assertEqual(stats["图路径"], 1)
        self.assertEqual(stats["子图节点"], 2)
        self.assertEqual(stats["文本证据"], 1)
        self.assertEqual(stats["来源路径"], 1)
        self.assertNotIn("社区报告", stats)

    def test_summary_reports_report_count_when_present(self):
        self.trace.channel_scores = {"native_microsoft_context": True, "report_count": 5}
        self.assertEqual(trace_view.summary(self.trace)["社区报告"], 5)

    def test_evidence_hint_explains_missing_subgraph(self):
        self.assertIsNone(trace_view.evidence_hint(self.trace))

        empty = make_trace()
        empty.subgraph_nodes = []
        empty.method = "microsoft_global"
        self.assertIn("社区报告", trace_view.evidence_hint(empty) or "")

        empty.method = "microsoft_basic"
        self.assertIn("原文片段", trace_view.evidence_hint(empty) or "")

        empty.method = "hybrid_path"
        self.assertIn("没有命中实体", trace_view.evidence_hint(empty) or "")

    def test_path_rows_use_readable_titles(self):
        paths = trace_view.path_rows(self.trace)
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths.loc[0, "路径"], "Alpha → Beta")
        self.assertEqual(paths.loc[0, "hops"], 1)
        self.assertEqual(paths.loc[0, "relationship_ids"], "r-ab")

    def test_frames_cover_evidence_tables(self):
        frames = trace_view.frames(self.trace)
        self.assertEqual(
            set(frames), {"命中实体", "命中关系", "文本证据", "子图边"}
        )
        self.assertEqual(len(frames["命中实体"]), 2)
        self.assertEqual(len(frames["子图边"]), 2)

    def test_channel_frame_flattens_nested_scores(self):
        scores = trace_view.channel_frame(self.trace)
        keys = set(scores["信号"])
        self.assertIn("lexical", keys)
        self.assertIn("vector.e-a", keys)
        self.assertIn("seed_entity_ids", keys)

    def test_recall_rows_mark_missing_gold_labels(self):
        rows = trace_view.recall_rows(self.trace)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows["值"].str.contains("无 gold 标注").all())

    def test_subgraph_dot_highlights_path_and_seed(self):
        dot = trace_view.subgraph_dot(self.trace)
        self.assertTrue(dot.startswith("digraph subgraph {"))
        self.assertTrue(dot.rstrip().endswith("}"))
        self.assertIn('"e-a"', dot)
        self.assertIn("Alpha", dot)
        self.assertIn(trace_view.SEED_FILL, dot)          # seed 节点浅红
        self.assertIn(trace_view.PATH_EDGE_COLOR, dot)    # 路径边红色
        self.assertNotIn("dangling", dot)                 # 端点不在子图里的边被丢掉
        self.assertNotIn("e-c", dot)

    def test_dot_labels_drop_quotes_and_newlines(self):
        trace = make_trace()
        trace.subgraph_nodes[0]["title"] = 'He said "yes"\nnow'
        dot = trace_view.subgraph_dot(trace)
        self.assertNotIn('\\"', dot)
        self.assertIn("He said 'yes' now", dot)

    def test_empty_trace_is_safe(self):
        empty = RetrievalTrace(query="q", method="lightrag")
        self.assertEqual(trace_view.subgraph_dot(empty), "")
        self.assertTrue(trace_view.path_rows(empty).empty)
        self.assertTrue(trace_view.channel_frame(empty).empty)
        for frame in trace_view.frames(empty).values():
            self.assertTrue(frame.empty)
        self.assertEqual(trace_view.summary(empty)["命中实体"], 0)
        self.assertTrue(
            trace_view.recall_rows(empty)["值"].str.contains("无 gold 标注").all()
        )

    def test_node_cap_limits_subgraph_size(self):
        trace = make_trace()
        trace.subgraph_nodes = [
            {"id": f"e-{index}", "title": f"Node {index}"} for index in range(10)
        ]
        dot = trace_view.subgraph_dot(trace, max_nodes=3)
        self.assertIn('"e-2"', dot)
        self.assertNotIn('"e-3"', dot)


class TestRowRecord(unittest.TestCase):
    """回归：Arrow 列表列读出来是 numpy 数组，不能再因为 .item() 炸掉。"""

    def test_multi_element_array_becomes_list(self):
        row = pd.Series({
            "id": "tu-1",
            "entity_ids": np.array(["e-a", "e-b"]),
            "covariate_ids": np.array([], dtype=object),
        })
        record = row_record(row)
        self.assertEqual(record["entity_ids"], ["e-a", "e-b"])
        self.assertEqual(record["covariate_ids"], [])
        self.assertEqual(record["id"], "tu-1")

    def test_missing_values_become_none(self):
        record = row_record(pd.Series({"a": None, "b": np.float64(1.5)}))
        self.assertIsNone(record["a"])
        self.assertEqual(record["b"], 1.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
