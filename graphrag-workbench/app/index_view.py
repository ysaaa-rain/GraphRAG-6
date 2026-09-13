# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""索引阶段的数据层。

这一层刻意不 import streamlit 和 graphrag，只依赖 pandas，因此可以在没有安装
GraphRAG 的环境里直接跑单元测试。界面只负责把这里的数据画出来。

它回答三个问题：

1. GraphRAG 的 workflow 名对应哪个"阶段"，产物落在哪个文件；
2. 一个索引目录里，每个阶段实际产出了多少数据、命中多少 cache、花了多少时间；
3. 建索引过程中，回调事件折算出进度条需要哪些状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import pandas as pd

TABLE_DIR = "output"
CACHE_DIR = "cache"
LOG_FILE = "logs/indexing-engine.log"
STATS_FILE = "output/stats.json"


@dataclass(frozen=True)
class Stage:
    """一个索引阶段：workflow 名、产物文件、cache 子目录。"""

    name: str
    workflows: tuple[str, ...]
    artifacts: tuple[str, ...]
    caches: tuple[str, ...] = ()
    note: str = ""


STAGES: tuple[Stage, ...] = (
    Stage(
        "文档载入",
        ("load_input_documents", "create_final_documents"),
        ("output/documents.parquet",),
        note="原始文档转成带 id/title/text 的表",
    ),
    Stage(
        "文本切分",
        ("create_base_text_units", "create_final_text_units"),
        ("output/text_units.parquet",),
        ("create_base_text_units",),
        note="按 token 窗口切 chunk，得到检索的最小文本单元",
    ),
    Stage(
        "实体关系抽取",
        ("extract_graph", "finalize_graph", "summarize_descriptions"),
        ("output/entities.parquet", "output/relationships.parquet"),
        ("extract_graph", "summarize_descriptions"),
        note="LLM 抽实体和关系，再合并同义描述",
    ),
    Stage(
        "属性抽取（可选）",
        ("extract_covariates",),
        ("output/covariates.parquet",),
        note="claims 开关关闭时这一阶段为空",
    ),
    Stage(
        "社区聚类",
        ("create_communities",),
        ("output/communities.parquet",),
        ("create_communities",),
        note="Leiden 层次聚类，得到社区层级",
    ),
    Stage(
        "社区报告",
        ("create_community_reports",),
        ("output/community_reports.parquet",),
        ("community_reporting",),
        note="每个社区生成摘要报告，Global 检索直接吃这层",
    ),
    Stage(
        "向量化",
        ("generate_text_embeddings",),
        ("lancedb",),
        ("text_embedding", "entity_embedding"),
        note="文本单元和实体描述写入 LanceDB",
    ),
)

WORKFLOW_TO_STAGE: dict[str, str] = {
    workflow: stage.name for stage in STAGES for workflow in stage.workflows
}


@dataclass
class Artifact:
    """一个产物文件的存在性与规模。"""

    path: str
    exists: bool
    rows: int | None = None
    columns: tuple[str, ...] = ()

    @property
    def is_table(self) -> bool:
        return self.path.endswith(".parquet")


@dataclass
class StageFacts:
    """某个阶段在这份索引里的实际情况。"""

    stage: Stage
    artifacts: list[Artifact]
    cache_files: dict[str, int] = field(default_factory=dict)
    seconds: float | None = None

    @property
    def produced(self) -> bool:
        """是否已经产出内容（有行数或有 cache 文件）。"""
        has_rows = any((artifact.rows or 0) > 0 for artifact in self.artifacts)
        return has_rows or any(count > 0 for count in self.cache_files.values())

    @property
    def rows(self) -> int:
        """该阶段产物表的最大行数，用作规模指标。"""
        return max((artifact.rows or 0 for artifact in self.artifacts), default=0)


@dataclass
class IndexSnapshot:
    """一个索引目录的只读快照，界面和测试都用它。"""

    index_dir: Path
    settings_exists: bool
    stages: list[StageFacts]
    total_seconds: float | None = None
    document_count: int | None = None
    community_levels: tuple[int, ...] = ()
    # None = 没有 stats.json，无法判断；False = 最近一次运行没跑完（有阶段失败）
    run_completed: bool | None = None
    log_lines: int = 0
    log_tail: str = ""
    unmapped_workflows: tuple[str, ...] = ()

    def stage(self, name: str) -> StageFacts | None:
        """按阶段名取 StageFacts。"""
        return next((item for item in self.stages if item.stage.name == name), None)


def _count_files(path: Path) -> int:
    """递归数文件；目录不存在时返回 0。"""
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _artifact(index_dir: Path, relative: str) -> Artifact:
    """检查一个产物：parquet 读行列，其他类型只看存在性。"""
    path = index_dir / relative
    artifact = Artifact(path=relative, exists=path.exists())
    if artifact.is_table and path.is_file():
        try:
            frame = pd.read_parquet(path)
        except Exception:  # noqa: BLE001 - 坏文件不应该让整个页面崩掉
            return artifact
        artifact.rows = len(frame)
        artifact.columns = tuple(str(column) for column in frame.columns)
    return artifact


def _read_stats(
    stats_path: Path,
) -> tuple[dict[str, float], float | None, int | None, bool | None]:
    """读 output/stats.json，返回 (workflow 秒数, 总秒数, 文档数, 是否正常结束)。

    graphrag 只在流水线跑完时写入 total_runtime；某个 workflow 抛错时它会被跳过，
    所以 total_runtime 为 0 就是"上次没跑完"的信号。这种情况下用各阶段耗时之和
    兜底，免得界面显示 0 分钟。
    """
    if not stats_path.is_file():
        return {}, None, None, None
    try:
        payload = json.loads(stats_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}, None, None, None
    timings = {
        name: float(body.get("overall", 0.0))
        for name, body in (payload.get("workflows") or {}).items()
        if isinstance(body, dict)
    }
    total = payload.get("total_runtime")
    documents = payload.get("num_documents")
    completed = bool(total)
    return (
        timings,
        float(total) if completed else (sum(timings.values()) or None),
        int(documents) if documents is not None else None,
        completed,
    )


def failed_workflows(results: object) -> tuple[str, ...]:
    """从 build_index 的返回值里挑出失败的 workflow 名。

    graphrag 的 build_index 不会因为单个 workflow 失败就抛异常，它把错误放在
    PipelineRunResult.error 里，所以必须显式检查，否则界面会误报"完成"。
    """
    failed: list[str] = []
    for item in results or []:
        if getattr(item, "error", None) is not None:
            failed.append(str(getattr(item, "workflow", "?")))
    return tuple(failed)


def load_table(index_dir: Path | str, name: str) -> pd.DataFrame:
    """读一个产出的表，例如 name="entities" -> output/entities.parquet。"""
    path = Path(index_dir) / TABLE_DIR / f"{name}.parquet"
    return pd.read_parquet(path) if path.is_file() else pd.DataFrame()


def community_levels(index_dir: Path | str) -> tuple[int, ...]:
    """索引里实际存在的社区层级，用来推断 Global 检索默认用哪一层。

    少量文档往往只聚出 level 0；语料一大就会出现 0/1/2…，这时如果还沿用 0，
    Global 检索就只看最细的社区，所以默认值应该按索引实际情况推断。
    """
    frame = load_table(index_dir, "communities")
    if frame.empty or "level" not in frame.columns:
        return ()
    return tuple(sorted({int(value) for value in frame["level"].dropna()}))


def inspect_index(index_dir: Path | str, log_tail_lines: int = 15) -> IndexSnapshot:
    """把一个索引目录读成快照：阶段产物、cache、耗时、日志尾巴。"""
    index_dir = Path(index_dir)
    timings, total, documents, completed = _read_stats(index_dir / STATS_FILE)

    stages: list[StageFacts] = []
    for stage in STAGES:
        seconds = sum(timings.get(name, 0.0) for name in stage.workflows)
        stages.append(
            StageFacts(
                stage=stage,
                artifacts=[_artifact(index_dir, item) for item in stage.artifacts],
                cache_files={
                    name: _count_files(index_dir / CACHE_DIR / name)
                    for name in stage.caches
                },
                seconds=seconds or None,
            )
        )

    log_path = index_dir / LOG_FILE
    log_lines, log_tail = 0, ""
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        log_lines = len(text)
        log_tail = "\n".join(text[-log_tail_lines:])

    return IndexSnapshot(
        index_dir=index_dir,
        settings_exists=(index_dir / "settings.yaml").is_file(),
        stages=stages,
        total_seconds=total,
        document_count=documents,
        community_levels=community_levels(index_dir),
        run_completed=completed,
        log_lines=log_lines,
        log_tail=log_tail,
        unmapped_workflows=tuple(sorted(set(timings) - set(WORKFLOW_TO_STAGE))),
    )


@dataclass
class ProgressState:
    """把建索引的回调事件折算成进度条需要的状态。"""

    planned: tuple[str, ...] = ()
    running: str | None = None
    finished: list[str] = field(default_factory=list)
    completed_items: int = 0
    total_items: int = 0
    error: str | None = None
    ended: bool = False

    @property
    def percent(self) -> float:
        """优先用条目级进度，没有就退回"已完成阶段/计划阶段"。"""
        if self.total_items:
            return min(100.0, self.completed_items / self.total_items * 100.0)
        if self.planned:
            return len(self.finished) / len(self.planned) * 100.0
        return 0.0

    def apply(self, event: dict[str, Any]) -> None:
        """消费一条回调事件。"""
        kind = event.get("type")
        if kind == "start":
            self.planned = tuple(event.get("names") or ())
        elif kind == "running":
            self.running = event.get("name")
        elif kind == "done":
            name = event.get("name")
            if name and name not in self.finished:
                self.finished.append(name)
            self.running = None
        elif kind == "pct":
            self.completed_items = int(event.get("completed") or 0)
            self.total_items = int(event.get("total") or 0)
        elif kind == "error":
            self.error = str(event.get("message"))
        elif kind == "end":
            self.ended = True
            self.running = None


class QueueCallbacks:
    """GraphRAG 的 WorkflowCallbacks 实现：把事件丢进队列给界面消费。

    只用到回调对象上的公开方法名，所以不需要 import graphrag 就能被测试。
    """

    def __init__(self, queue: Queue | None = None):
        self.queue: Queue = queue or Queue()

    def _put(self, **event: Any) -> None:
        self.queue.put(event)

    def pipeline_start(self, names: list[str]) -> None:
        """整个流水线开始。"""
        self._put(type="start", names=list(names))

    def pipeline_end(self, results: object = None) -> None:
        """整个流水线结束。"""
        self._put(type="end")

    def workflow_start(self, name: str, instance: object = None) -> None:
        """某个阶段开始。"""
        self._put(type="running", name=name)

    def workflow_end(self, name: str, instance: object = None) -> None:
        """某个阶段结束。"""
        self._put(type="done", name=name)

    def progress(self, progress: object) -> None:
        """条目级进度。"""
        self._put(
            type="pct",
            completed=getattr(progress, "completed_items", 0) or 0,
            total=getattr(progress, "total_items", 0) or 0,
        )

    def pipeline_error(self, error: BaseException) -> None:
        """流水线出错。"""
        self._put(type="error", message=f"{type(error).__name__}: {error}")


def drain(queue: Queue, limit: int = 200) -> list[dict[str, Any]]:
    """非阻塞地取队列里的所有事件。"""
    events: list[dict[str, Any]] = []
    for _ in range(limit):
        try:
            events.append(queue.get_nowait())
        except Empty:
            break
    return events
