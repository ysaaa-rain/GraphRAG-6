# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""把 RetrievalTrace 变成界面能画的东西。

这一层只做"数据 → 表格 / Graphviz DOT 字符串"的转换，不 import streamlit，
所以可以单独测试。子图用 DOT 字符串而不是 graphviz 对象，这样不需要额外的
Python 依赖（Streamlit 前端自带 viz.js）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from graphrag6_retrieval import RetrievalTrace

MAX_LABEL = 28

# 子图配色：seed 浅红、路径节点红、普通节点浅蓝、路径边红色加粗
SEED_FILL = "#ffe3e3"
PATH_FILL = "#ffb3b3"
PLAIN_FILL = "#dbeafe"
EDGE_COLOR = "#8a93a5"
PATH_EDGE_COLOR = "#e5484d"
NODE_BORDER = "#b8c0cf"


def _text(value: Any) -> str:
    """把任意字段转成适合展示的单行文本。"""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _shorten(text: str, limit: int = MAX_LABEL) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _dot_escape(text: str) -> str:
    """DOT 标签里不能出现双引号和换行。"""
    return text.replace("\\", "/").replace('"', "'").replace("\n", " ")


def title_map(trace: RetrievalTrace) -> dict[str, str]:
    """实体 id -> 可读标题，方便把路径 id 序列展示成人看得懂的名字。"""
    titles: dict[str, str] = {}
    for node in trace.subgraph_nodes or []:
        node_id = _text(node.get("id"))
        if node_id:
            titles[node_id] = _text(node.get("title")) or node_id
    for entity in trace.matched_entities or []:
        entity_id = _text(entity.get("id") or entity.get("human_readable_id"))
        if entity_id and entity_id not in titles:
            titles[entity_id] = _text(entity.get("title")) or entity_id
    return titles


def frames(trace: RetrievalTrace) -> dict[str, pd.DataFrame]:
    """命中实体、命中关系、文本证据、子图边，各转成一张表。"""
    return {
        "命中实体": pd.DataFrame(trace.matched_entities or []),
        "命中关系": pd.DataFrame(trace.matched_relationships or []),
        "文本证据": pd.DataFrame(trace.text_evidence or []),
        "子图边": pd.DataFrame(trace.subgraph_edges or []),
    }


def path_rows(trace: RetrievalTrace) -> pd.DataFrame:
    """图路径转成人可读的一行：A → B → C，附跳数和分数。"""
    titles = title_map(trace)
    rows: list[dict[str, Any]] = []
    for path in trace.graph_paths or []:
        entity_ids = [_text(item) for item in path.get("entity_ids", [])]
        relationship_ids = [_text(item) for item in path.get("relationship_ids", [])]
        rows.append({
            "path_id": _text(path.get("path_id")),
            "hops": path.get("hops", len(relationship_ids)),
            "score": path.get("score", 0.0),
            "路径": " → ".join(titles.get(item, item) for item in entity_ids),
            "relationship_ids": ", ".join(relationship_ids),
        })
    return pd.DataFrame(rows)


def channel_frame(trace: RetrievalTrace) -> pd.DataFrame:
    """各路信号的分数（BM25 / 向量 / 图），扁平化成两列表。"""
    rows: list[dict[str, Any]] = []
    for key, value in (trace.channel_scores or {}).items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                rows.append({"信号": f"{key}.{sub_key}", "值": sub_value})
        elif isinstance(value, list):
            rows.append({"信号": key, "值": f"{len(value)} 项"})
        else:
            rows.append({"信号": key, "值": value})
    return pd.DataFrame(rows)


def recall_rows(trace: RetrievalTrace) -> pd.DataFrame:
    """召回指标；交互查询没有 gold 标注时为 null，正好说明这一点。"""
    def show(value: float | None) -> str:
        return "（无 gold 标注）" if value is None else f"{value:.3f}"

    return pd.DataFrame([
        {
            "指标": "path_recall",
            "值": show(trace.path_recall),
            "分子/分母": f"{trace.path_recall_numerator}/{trace.path_recall_denominator}",
        },
        {
            "指标": "evidence_recall",
            "值": show(trace.evidence_recall),
            "分子/分母": (
                f"{trace.evidence_recall_numerator}/{trace.evidence_recall_denominator}"
            ),
        },
    ])


def summary(trace: RetrievalTrace) -> dict[str, Any]:
    """顶部那几个数字。"""
    stats: dict[str, Any] = {
        "命中实体": len(trace.matched_entity_ids or []),
        "命中关系": len(trace.matched_relationship_ids or []),
        "文本证据": len(trace.text_evidence or []),
        "来源路径": len(trace.retrieved_source_paths or []),
        "图路径": len(trace.graph_paths or []),
        "子图节点": len(trace.subgraph_nodes or []),
    }
    report_count = (trace.channel_scores or {}).get("report_count")
    if isinstance(report_count, int):
        stats["社区报告"] = report_count
    return stats


def evidence_hint(trace: RetrievalTrace) -> str | None:
    """没有子图时给出人话解释，而不是让人对着一排 0 猜。"""
    if trace.subgraph_nodes:
        return None
    method = (trace.method or "").lower()
    if "global" in method:
        return (
            "Global 以社区报告为检索单元，不涉及实体和关系，所以没有子图；"
            "它的证据在下面『检索上下文 / 引用』的 reports 里。"
        )
    if "basic" in method:
        return "Basic / Vector 直接用原文片段作为证据，没有图，所以没有子图。"
    return "这次检索没有命中实体或关系，因此没有子图可画。"


def subgraph_dot(trace: RetrievalTrace, max_nodes: int = 40) -> str:
    """子图 DOT 字符串：路径经过的节点/边用红色加粗，seed 节点浅红。"""
    nodes = list(trace.subgraph_nodes or [])[:max_nodes]
    if not nodes:
        return ""
    node_ids = {_text(node.get("id")) for node in nodes if _text(node.get("id"))}
    path_nodes = {
        _text(item)
        for path in trace.graph_paths or []
        for item in path.get("entity_ids", [])
    }
    path_edges = {
        _text(item)
        for path in trace.graph_paths or []
        for item in path.get("relationship_ids", [])
    }

    lines = [
        "digraph subgraph {",
        '  graph [rankdir=LR, bgcolor="transparent"];',
        '  node [shape=box, style="rounded,filled", fontsize=10, fontname="Helvetica"];',
        f'  edge [fontsize=9, color="{EDGE_COLOR}"];',
    ]
    for index, node in enumerate(nodes, start=1):
        node_id = _text(node.get("id")) or f"node-{index}"
        label = _dot_escape(_shorten(_text(node.get("title")) or node_id))
        if node.get("seed"):
            fill, penwidth = SEED_FILL, "2"
        elif node_id in path_nodes:
            fill, penwidth = PATH_FILL, "2"
        else:
            fill, penwidth = PLAIN_FILL, "1"
        lines.append(
            f'  "{node_id}" [label="{label}", fillcolor="{fill}", '
            f'color="{NODE_BORDER}", penwidth={penwidth}];'
        )
    for edge in trace.subgraph_edges or []:
        source = _text(edge.get("source"))
        target = _text(edge.get("target"))
        if not source or not target or source not in node_ids or target not in node_ids:
            continue
        highlighted = _text(edge.get("id")) in path_edges
        color = PATH_EDGE_COLOR if highlighted else EDGE_COLOR
        penwidth = "2.2" if highlighted else "1"
        description = _dot_escape(_shorten(_text(edge.get("description")), 22))
        lines.append(
            f'  "{source}" -> "{target}" [color="{color}", penwidth={penwidth}, '
            f'label="{description}"];'
        )
    lines.append("}")
    return "\n".join(lines)
