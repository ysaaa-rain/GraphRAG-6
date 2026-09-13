# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""索引阶段数据层的测试。

只用 unittest + pandas，不 import streamlit / graphrag，因此在依赖没装全的环境里
也能直接跑：

    python -m unittest tests.test_index_view -v
    python tests/test_index_view.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from queue import Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import pandas as pd  # noqa: E402
from index_view import (  # noqa: E402
    STAGES,
    WORKFLOW_TO_STAGE,
    ProgressState,
    QueueCallbacks,
    drain,
    failed_workflows,
    inspect_index,
    load_table,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_INDEX = REPO_ROOT / "experiments" / "outputs" / "enron_q001"


def build_fake_index(root: Path) -> Path:
    """造一个最小索引目录：两张表、一份 stats、两个 cache、一段日志。"""
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    (root / "settings.yaml").write_text("completion_models: {}\n", encoding="utf-8")

    pd.DataFrame({
        "id": ["d1", "d2", "d3"],
        "title": ["t1", "t2", "t3"],
        "text": ["a", "b", "c"],
    }).to_parquet(output / "documents.parquet", index=False)
    pd.DataFrame({"id": [f"tu{i}" for i in range(5)], "text": list("abcde")}).to_parquet(
        output / "text_units.parquet", index=False
    )
    pd.DataFrame({"id": ["e1", "e2"], "title": ["x", "y"]}).to_parquet(
        output / "entities.parquet", index=False
    )

    stats = {
        "total_runtime": 120.5,
        "num_documents": 3,
        "workflows": {
            "load_input_documents": {"overall": 0.5},
            "extract_graph": {"overall": 100.0},
            "create_communities": {"overall": 20.0},
        },
    }
    (output / "stats.json").write_text(json.dumps(stats), encoding="utf-8")

    for name, count in (("extract_graph", 2), ("community_reporting", 1)):
        cache_dir = root / "cache" / name
        cache_dir.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            (cache_dir / f"{index}.json").write_text("{}", encoding="utf-8")

    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "indexing-engine.log").write_text(
        "\n".join(f"line {index}" for index in range(5)), encoding="utf-8"
    )
    return root


class TestStageMapping(unittest.TestCase):
    """阶段表本身的自洽性。"""

    def test_workflows_are_not_mapped_twice(self):
        self.assertEqual(
            len(WORKFLOW_TO_STAGE), sum(len(stage.workflows) for stage in STAGES)
        )

    def test_every_stage_has_artifacts_and_a_note(self):
        for stage in STAGES:
            self.assertTrue(stage.artifacts, stage.name)
            self.assertTrue(stage.note, stage.name)

    def test_graphrag_3_1_workflow_names_are_all_mapped(self):
        self.assertEqual(
            set(WORKFLOW_TO_STAGE),
            {
                "load_input_documents",
                "create_final_documents",
                "create_base_text_units",
                "create_final_text_units",
                "extract_graph",
                "finalize_graph",
                "summarize_descriptions",
                "extract_covariates",
                "create_communities",
                "create_community_reports",
                "generate_text_embeddings",
            },
        )


class TestInspectIndex(unittest.TestCase):
    """快照读取：正常与缺文件两种情况。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = build_fake_index(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_tables_stats_cache_and_log(self):
        snapshot = inspect_index(self.root)

        self.assertTrue(snapshot.settings_exists)
        self.assertEqual(snapshot.document_count, 3)
        self.assertAlmostEqual(snapshot.total_seconds, 120.5)
        self.assertEqual(snapshot.log_lines, 5)
        self.assertIn("line 4", snapshot.log_tail)
        self.assertEqual(snapshot.unmapped_workflows, ())

        load_stage = snapshot.stage("文档载入")
        assert load_stage is not None
        self.assertTrue(load_stage.produced)
        self.assertEqual(load_stage.rows, 3)
        self.assertEqual(load_stage.seconds, 0.5)
        self.assertEqual(load_stage.artifacts[0].columns, ("id", "title", "text"))

        cut_stage = snapshot.stage("文本切分")
        assert cut_stage is not None
        self.assertEqual(cut_stage.rows, 5)
        self.assertIsNone(cut_stage.seconds)

        extract_stage = snapshot.stage("实体关系抽取")
        assert extract_stage is not None
        self.assertEqual(extract_stage.cache_files["extract_graph"], 2)
        self.assertEqual(extract_stage.seconds, 100.0)

        report_stage = snapshot.stage("社区报告")
        assert report_stage is not None
        self.assertEqual(report_stage.rows, 0)
        self.assertTrue(report_stage.produced)  # 有 cache 文件也算产出

        vector_stage = snapshot.stage("向量化")
        assert vector_stage is not None
        self.assertFalse(vector_stage.produced)

        optional_stage = snapshot.stage("属性抽取（可选）")
        assert optional_stage is not None
        self.assertEqual(optional_stage.rows, 0)
        self.assertFalse(optional_stage.artifacts[0].exists)

    def test_empty_directory_is_tolerated(self):
        with tempfile.TemporaryDirectory() as empty:
            snapshot = inspect_index(Path(empty))
        self.assertFalse(snapshot.settings_exists)
        self.assertIsNone(snapshot.total_seconds)
        self.assertIsNone(snapshot.document_count)
        self.assertEqual(snapshot.unmapped_workflows, ())
        self.assertTrue(all(not facts.produced for facts in snapshot.stages))

    def test_load_table_missing_returns_empty_frame(self):
        self.assertTrue(load_table(self.root, "not_a_table").empty)

    def test_stats_without_total_runtime_means_unfinished_run(self):
        self.assertIs(inspect_index(self.root).run_completed, True)

        (self.root / "output" / "stats.json").write_text(
            json.dumps({
                "total_runtime": 0,
                "num_documents": 3,
                "workflows": {
                    "load_input_documents": {"overall": 0.5},
                    "extract_graph": {"overall": 100.0},
                },
            }),
            encoding="utf-8",
        )
        snapshot = inspect_index(self.root)
        self.assertIs(snapshot.run_completed, False)
        self.assertAlmostEqual(snapshot.total_seconds, 100.5)  # 各阶段之和兜底

    def test_missing_stats_means_unknown(self):
        (self.root / "output" / "stats.json").unlink()
        snapshot = inspect_index(self.root)
        self.assertIsNone(snapshot.run_completed)
        self.assertIsNone(snapshot.total_seconds)

    def test_community_levels_come_from_the_index(self):
        output = self.root / "output"
        pd.DataFrame({"id": ["c0", "c1", "c2"], "level": [0, 1, 1]}).to_parquet(
            output / "communities.parquet", index=False
        )
        self.assertEqual(inspect_index(self.root).community_levels, (0, 1))
        self.assertEqual(load_table(self.root, "communities").shape[0], 3)


class TestFailedWorkflows(unittest.TestCase):
    """build_index 不抛异常，失败信息在返回值里，必须显式检查。"""

    def test_collects_only_failed_workflows(self):
        class Result:
            def __init__(self, workflow, error=None):
                self.workflow = workflow
                self.error = error

        results = [
            Result("load_input_documents"),
            Result("generate_text_embeddings", error=RuntimeError("503")),
            Result("create_communities"),
        ]
        self.assertEqual(failed_workflows(results), ("generate_text_embeddings",))

    def test_empty_and_none_are_safe(self):
        self.assertEqual(failed_workflows([]), ())
        self.assertEqual(failed_workflows(None), ())


@unittest.skipUnless(REAL_INDEX.exists(), "enron_q001 索引不存在")
class TestRealIndex(unittest.TestCase):
    """对真实索引断言已知规模，保证阶段映射没有漂移。"""

    def test_known_counts(self):
        snapshot = inspect_index(REAL_INDEX)
        self.assertEqual(snapshot.unmapped_workflows, ())
        self.assertGreater(snapshot.document_count or 0, 0)
        self.assertTrue(snapshot.community_levels)
        # 索引会被重建，行数不是固定的；这里只断言"有产物"这种稳定性质。
        for name in ("文档载入", "文本切分", "实体关系抽取", "社区聚类", "社区报告"):
            facts = snapshot.stage(name)
            assert facts is not None
            self.assertGreater(facts.rows, 0, name)
        self.assertIsNotNone(snapshot.total_seconds)


class TestProgress(unittest.TestCase):
    """回调事件 -> 进度状态。"""

    def test_reduces_workflow_events(self):
        state = ProgressState()
        state.apply({"type": "start", "names": ["a", "b", "c", "d"]})
        state.apply({"type": "running", "name": "a"})
        self.assertEqual(state.percent, 0.0)
        state.apply({"type": "done", "name": "a"})
        self.assertEqual(state.percent, 25.0)
        self.assertIsNone(state.running)
        state.apply({"type": "pct", "completed": 90, "total": 100})
        self.assertEqual(state.percent, 90.0)
        state.apply({"type": "error", "message": "boom"})
        state.apply({"type": "end"})
        self.assertTrue(state.ended)
        self.assertEqual(state.error, "boom")
        self.assertEqual(state.finished, ["a"])

    def test_percent_caps_and_ignores_duplicate_done(self):
        state = ProgressState()
        state.apply({"type": "start", "names": ["a"]})
        state.apply({"type": "done", "name": "a"})
        state.apply({"type": "done", "name": "a"})
        self.assertEqual(state.finished, ["a"])
        state.apply({"type": "pct", "completed": 500, "total": 100})
        self.assertEqual(state.percent, 100.0)

    def test_queue_callbacks_feed_progress_state(self):
        callbacks = QueueCallbacks()
        callbacks.pipeline_start(["extract_graph", "generate_text_embeddings"])
        callbacks.workflow_start("extract_graph", object())
        callbacks.progress(type("P", (), {"completed_items": 3, "total_items": 6})())
        callbacks.workflow_end("extract_graph", object())
        callbacks.pipeline_error(ValueError("bad"))
        callbacks.pipeline_end([])

        state = ProgressState()
        for event in drain(callbacks.queue):
            state.apply(event)

        self.assertEqual(state.planned, ("extract_graph", "generate_text_embeddings"))
        self.assertEqual(state.finished, ["extract_graph"])
        self.assertEqual(state.completed_items, 3)
        self.assertEqual(state.total_items, 6)
        self.assertIn("ValueError: bad", state.error or "")
        self.assertTrue(state.ended)

    def test_drain_is_non_blocking(self):
        self.assertEqual(drain(Queue()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
