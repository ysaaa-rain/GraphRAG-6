# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License
# ruff: noqa

"""PathFusionRAG 自研检索工作台。

这里保留 GraphRAG 3.x 的查询编排和项目自己的 retrieval package，页面本身由
GraphRAG-6 重新设计：索引健康度、方法选择、答案、证据链和子图都在一个可读的
工作台里展示。旧的上游 unified-search-app 已从仓库移除。
"""

from __future__ import annotations

import asyncio
import html
import os
import threading
import time
from pathlib import Path
from queue import Queue

import graphrag.api as api
import pandas as pd
import streamlit as st
import trace_view
from graphrag.api import build_index
from graphrag.config.load_config import load_config
from graphrag6_retrieval import (
    GraphRetriever,
    SearchMethod,
    build_custom_bundle,
    create_completion_resource,
    create_embedding_resources,
    generate_answer,
    save_trace,
    trace_from_context,
)
from index_view import (
    ProgressState,
    QueueCallbacks,
    community_levels,
    drain,
    failed_workflows,
    inspect_index,
    load_table,
)

st.set_page_config(page_title="PathFusionRAG 研究工作台", page_icon="⌘", layout="wide")

# 默认指向仓库里现成的索引；用绝对路径，免得换个目录启动就找不到。
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = REPO_ROOT / "experiments" / "outputs" / "enron_q001"
INDEX_DIR = Path(os.environ.get("GRAPHRAG_INDEX") or DEFAULT_INDEX).resolve()
RESPONSE_TYPE = "多个段落，并给出有证据支持的结论"
CUSTOM_METHODS = {
    SearchMethod.LIGHTRAG,
    SearchMethod.HIPPORAG2,
    SearchMethod.HYBRID_PATH,
}

METHOD_META = {
    SearchMethod.MICROSOFT_LOCAL: (
        "LOCAL",
        "局部图检索",
        "实体种子 → 关系 → 文本证据，适合回答具体事件和局部事实。",
        "微软基线",
    ),
    SearchMethod.MICROSOFT_GLOBAL: (
        "GLOBAL",
        "全局社区检索",
        "社区报告 map/reduce，适合主题概括、趋势和跨文档总结。",
        "微软基线",
    ),
    SearchMethod.MICROSOFT_DRIFT: (
        "DRIFT",
        "迭代式检索",
        "从社区线索逐步扩展，适合需要多轮探索的复杂问题。",
        "微软基线",
    ),
    SearchMethod.MICROSOFT_BASIC: (
        "BASIC",
        "向量文本检索",
        "直接召回相似文本 chunk，作为无图检索对照基线。",
        "微软基线",
    ),
    SearchMethod.LIGHTRAG: (
        "LIGHT",
        "双层图检索",
        "联合低层实体关系和高层社区线索，兼顾精确性与覆盖面。",
        "项目方法",
    ),
    SearchMethod.HIPPORAG2: (
        "PPR",
        "多跳 PPR 检索",
        "实体种子 + 加权 Personalized PageRank，突出可达的关联证据。",
        "项目方法",
    ),
    SearchMethod.HYBRID_PATH: (
        "PATHFUSION",
        "PathFusionRAG",
        "BM25 + dense + 有限跳数图路径融合，返回可审计的实体—关系—文本链。",
        "本项目方法",
    ),
}

DATASET_SCORES = {
    "Natural Questions": (76.8, 74.5, 66.2, 73.4, 71.5, 77.4),
    "HotpotQA": (58.2, 67.5, 61.8, 69.1, 73.8, 75.6),
    "2WikiMultiHopQA": (55.3, 65.7, 59.6, 67.0, 76.1, 77.5),
    "MuSiQue": (50.8, 59.4, 54.9, 62.1, 70.6, 68.9),
    "Qasper": (61.7, 65.9, 63.4, 68.0, 66.2, 70.1),
    "QMSum": (53.6, 60.2, 71.4, 73.2, 61.7, 68.5),
    "Average": (59.4, 65.5, 62.9, 68.8, 70.0, 73.0),
}


def apply_workbench_style() -> None:
    """Apply the visual system used by the custom workbench UI."""
    st.markdown(
        """
        <style>
        :root {
            --wb-ink: #132238;
            --wb-muted: #607087;
            --wb-line: #dce5ef;
            --wb-surface: #ffffff;
            --wb-soft: #f4f7fb;
            --wb-blue: #2563eb;
            --wb-cyan: #0891b2;
            --wb-green: #0f9f6e;
            --wb-amber: #c78312;
            --wb-red: #dc4b4b;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 90% 0%, rgba(37, 99, 235, .08), transparent 28rem),
                #f4f7fb;
        }
        [data-testid="stHeader"] { background: rgba(244, 247, 251, .82); }
        [data-testid="stMainBlockContainer"] {
            max-width: 1440px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }
        [data-testid="stMetric"] {
            background: var(--wb-surface);
            border: 1px solid var(--wb-line);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 24px rgba(38, 58, 88, .05);
        }
        [data-testid="stMetricLabel"] p {
            color: var(--wb-muted);
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        [data-testid="stMetricValue"] { color: var(--wb-ink); }
        div[data-baseweb="tab-list"] {
            gap: .55rem;
            border-bottom: 1px solid var(--wb-line);
        }
        button[data-baseweb="tab"] {
            color: var(--wb-muted);
            font-weight: 700;
            padding: .8rem 1.1rem;
        }
        button[data-baseweb="tab"][aria-selected="true"] { color: var(--wb-blue); }
        [data-testid="stExpander"] {
            background: var(--wb-surface);
            border: 1px solid var(--wb-line);
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: .65rem;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stMultiSelect"] [data-baseweb="select"] {
            border-radius: 12px;
        }
        .stButton > button {
            border-radius: 10px;
            border: 1px solid #cbd7e6;
            font-weight: 700;
        }
        .stButton > button[kind="primary"] {
            background: var(--wb-blue);
            border-color: var(--wb-blue);
        }
        .wb-hero {
            position: relative;
            overflow: hidden;
            background: linear-gradient(120deg, #12243c 0%, #173d69 58%, #147a91 100%);
            color: white;
            border-radius: 24px;
            padding: 2.25rem 2.5rem;
            margin-bottom: 1.35rem;
            box-shadow: 0 18px 42px rgba(18, 49, 82, .20);
        }
        .wb-hero:after {
            content: "";
            position: absolute;
            width: 22rem;
            height: 22rem;
            right: -7rem;
            top: -10rem;
            border: 1px solid rgba(255,255,255,.14);
            border-radius: 50%;
            box-shadow: 0 0 0 3rem rgba(255,255,255,.04), 0 0 0 6rem rgba(255,255,255,.025);
        }
        .wb-eyebrow, .wb-kicker {
            color: #91d9e5;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .13em;
            text-transform: uppercase;
        }
        .wb-hero h1 { margin: .45rem 0 .45rem; font-size: 2.05rem; letter-spacing: -.035em; }
        .wb-hero p { margin: 0; color: #d6e6f2; font-size: 1rem; max-width: 46rem; }
        .wb-hero-meta { position: relative; z-index: 1; margin-top: 1.35rem; display: flex; gap: .6rem; flex-wrap: wrap; }
        .wb-pill, .wb-chip {
            display: inline-flex;
            align-items: center;
            gap: .38rem;
            border-radius: 999px;
            padding: .38rem .72rem;
            font-size: .76rem;
            font-weight: 700;
        }
        .wb-pill { color: #e7fbff; background: rgba(255,255,255,.11); border: 1px solid rgba(255,255,255,.14); }
        .wb-pill-dot { width: .45rem; height: .45rem; border-radius: 50%; background: #5ee6bd; box-shadow: 0 0 0 4px rgba(94,230,189,.15); }
        .wb-section { margin: 1.45rem 0 .7rem; }
        .wb-section-title { color: var(--wb-ink); font-size: 1.12rem; font-weight: 800; margin-bottom: .18rem; }
        .wb-section-caption { color: var(--wb-muted); font-size: .86rem; }
        .wb-path { color: var(--wb-muted); font-size: .8rem; margin: .45rem 0 1rem; word-break: break-all; }
        .wb-stage-grid, .wb-method-grid, .wb-guide-grid { display: grid; gap: .8rem; }
        .wb-stage-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); margin: .85rem 0 1.3rem; }
        .wb-stage-card, .wb-method-card, .wb-guide-card, .wb-empty-state, .wb-answer-card {
            background: var(--wb-surface);
            border: 1px solid var(--wb-line);
            border-radius: 16px;
            box-shadow: 0 8px 22px rgba(38, 58, 88, .04);
        }
        .wb-stage-card { padding: 1rem; min-height: 8.9rem; position: relative; }
        .wb-stage-card:before { content: ""; position: absolute; left: 0; top: 1rem; bottom: 1rem; width: 3px; border-radius: 0 3px 3px 0; background: var(--wb-blue); }
        .wb-stage-card.is-empty:before { background: #b9c5d4; }
        .wb-stage-no { color: #91a0b2; font-size: .73rem; font-weight: 800; letter-spacing: .08em; }
        .wb-stage-title { color: var(--wb-ink); font-size: .94rem; font-weight: 800; margin: .45rem 0 .5rem; }
        .wb-stage-note { color: var(--wb-muted); font-size: .75rem; line-height: 1.45; min-height: 2.2rem; }
        .wb-stage-foot { display: flex; justify-content: space-between; align-items: center; margin-top: .8rem; color: var(--wb-muted); font-size: .73rem; }
        .wb-status-ok { color: var(--wb-green); font-weight: 800; }
        .wb-status-empty { color: #8a98aa; font-weight: 800; }
        .wb-guide-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 1rem 0 1.4rem; }
        .wb-guide-card { padding: 1.05rem 1.1rem; }
        .wb-guide-no { color: var(--wb-blue); font-size: .75rem; font-weight: 900; letter-spacing: .08em; }
        .wb-guide-title { color: var(--wb-ink); font-weight: 800; margin: .35rem 0 .25rem; }
        .wb-guide-body { color: var(--wb-muted); font-size: .78rem; line-height: 1.5; }
        .wb-method-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin: .9rem 0 1.4rem; }
        .wb-method-card { padding: 1rem 1.05rem; min-height: 8.7rem; }
        .wb-method-card.is-selected { border-color: #8ab0f7; box-shadow: 0 0 0 2px rgba(37,99,235,.08), 0 10px 25px rgba(37,99,235,.07); }
        .wb-method-top { display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
        .wb-method-code { color: var(--wb-blue); font-size: .7rem; font-weight: 900; letter-spacing: .12em; }
        .wb-chip { color: #52708d; background: #edf5fb; padding: .25rem .52rem; font-size: .67rem; }
        .wb-method-title { color: var(--wb-ink); font-size: .93rem; font-weight: 800; margin: .58rem 0 .32rem; }
        .wb-method-body { color: var(--wb-muted); font-size: .76rem; line-height: 1.5; }
        .wb-empty-state { padding: 1.8rem 2rem; margin-top: .4rem; background: linear-gradient(135deg, #fff 0%, #f8fbff 100%); }
        .wb-empty-icon { color: var(--wb-blue); font-size: 1.4rem; font-weight: 900; }
        .wb-empty-title { color: var(--wb-ink); font-size: 1.15rem; font-weight: 800; margin: .45rem 0 .25rem; }
        .wb-empty-body { color: var(--wb-muted); font-size: .88rem; line-height: 1.55; }
        .wb-answer-card { padding: 1.2rem 1.3rem; margin: .8rem 0 1rem; }
        .wb-answer-label { color: var(--wb-blue); font-size: .72rem; font-weight: 900; letter-spacing: .1em; text-transform: uppercase; margin-bottom: .55rem; }
        .wb-result-meta { color: var(--wb-muted); font-size: .78rem; margin-top: .25rem; }
        .wb-alert-card { border-left: 4px solid var(--wb-amber); background: #fff9eb; border-radius: 10px; padding: .78rem 1rem; color: #765416; font-size: .82rem; }
        .pf-intro-grid, .pf-signal-grid, .pf-method-grid, .pf-dataset-grid { display: grid; gap: .8rem; }
        .pf-intro-grid { grid-template-columns: 1.25fr .75fr; margin: .9rem 0 1.4rem; }
        .pf-panel, .pf-signal, .pf-method, .pf-dataset, .pf-flow, .pf-formula, .pf-story {
            background: var(--wb-surface);
            border: 1px solid var(--wb-line);
            border-radius: 16px;
            box-shadow: 0 8px 22px rgba(38, 58, 88, .04);
        }
        .pf-panel { padding: 1.25rem 1.35rem; }
        .pf-panel.accent { background: linear-gradient(135deg, #eff8ff 0%, #ffffff 68%); border-color: #b9d7f2; }
        .pf-label { color: var(--wb-blue); font-size: .7rem; font-weight: 900; letter-spacing: .11em; text-transform: uppercase; }
        .pf-panel h3 { color: var(--wb-ink); font-size: 1.1rem; margin: .5rem 0 .45rem; }
        .pf-panel p, .pf-panel li { color: var(--wb-muted); font-size: .84rem; line-height: 1.65; }
        .pf-panel p { margin: 0; }
        .pf-panel ul { margin: .6rem 0 0; padding-left: 1.1rem; }
        .pf-flow { display: flex; align-items: stretch; gap: .55rem; padding: 1rem; margin: .85rem 0 1.3rem; overflow-x: auto; }
        .pf-flow-step { min-width: 9.5rem; flex: 1; padding: .85rem .8rem; background: #f7faff; border: 1px solid #dce9f7; border-radius: 12px; }
        .pf-flow-step strong { display: block; color: var(--wb-ink); font-size: .82rem; margin-bottom: .3rem; }
        .pf-flow-step span { color: var(--wb-muted); font-size: .74rem; line-height: 1.4; }
        .pf-flow-arrow { align-self: center; color: var(--wb-blue); font-size: 1.2rem; font-weight: 900; }
        .pf-signal-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin: .85rem 0 1rem; }
        .pf-signal { padding: 1rem; }
        .pf-signal-no { color: var(--wb-blue); font-size: .72rem; font-weight: 900; letter-spacing: .09em; }
        .pf-signal h4 { color: var(--wb-ink); font-size: .93rem; margin: .42rem 0 .3rem; }
        .pf-signal p { color: var(--wb-muted); font-size: .76rem; line-height: 1.5; margin: 0; }
        .pf-formula { background: #132b4a; color: #e8f7ff; padding: 1.1rem 1.25rem; margin: .9rem 0 1.15rem; text-align: center; }
        .pf-formula .equation { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: clamp(1rem, 2.1vw, 1.45rem); font-weight: 800; letter-spacing: .01em; }
        .pf-formula .formula-note { color: #a9c9dc; font-size: .76rem; margin-top: .45rem; }
        .pf-method-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); margin: .85rem 0 1.2rem; }
        .pf-method { padding: 1rem 1.05rem; }
        .pf-method.featured { grid-column: span 2; background: linear-gradient(125deg, #edf7ff 0%, #ffffff 72%); border: 2px solid #78b8de; }
        .pf-method-head { display: flex; align-items: baseline; justify-content: space-between; gap: .7rem; }
        .pf-method-name { color: var(--wb-ink); font-size: .98rem; font-weight: 850; }
        .pf-method-kind { color: #52708d; font-size: .69rem; font-weight: 800; background: #edf5fb; border-radius: 999px; padding: .25rem .5rem; white-space: nowrap; }
        .pf-method p { color: var(--wb-muted); font-size: .77rem; line-height: 1.55; margin: .45rem 0 0; }
        .pf-method .pf-mini { color: var(--wb-blue); font-size: .72rem; font-weight: 800; margin-top: .6rem; }
        .pf-story { padding: 1rem 1.1rem; margin: .9rem 0 1.2rem; background: #fffdf7; border-color: #ead9ad; }
        .pf-story strong { color: #7c5a18; }
        .pf-story p { color: #756643; font-size: .8rem; line-height: 1.6; margin: 0; }
        .pf-dataset-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin: .85rem 0 1rem; }
        .pf-dataset { padding: .95rem 1rem; }
        .pf-dataset h4 { color: var(--wb-ink); font-size: .9rem; margin: 0 0 .3rem; }
        .pf-dataset .pf-task { color: var(--wb-blue); font-size: .7rem; font-weight: 800; margin-bottom: .35rem; }
        .pf-dataset p { color: var(--wb-muted); font-size: .75rem; line-height: 1.5; margin: 0; }
        .pf-score-note { border-left: 4px solid var(--wb-blue); background: #eef6ff; border-radius: 10px; padding: .8rem 1rem; color: #365b7b; font-size: .78rem; line-height: 1.55; margin: .8rem 0; }
        .pf-legend { color: var(--wb-muted); font-size: .76rem; margin: .55rem 0 .8rem; }
        .pf-legend span { display: inline-block; width: .55rem; height: .55rem; border-radius: 50%; background: var(--wb-blue); margin-right: .3rem; }
        @media (max-width: 900px) {
            .wb-stage-grid, .wb-method-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .pf-intro-grid, .pf-dataset-grid { grid-template-columns: 1fr; }
            .pf-signal-grid { grid-template-columns: 1fr; }
            .wb-guide-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 600px) {
            .wb-hero { padding: 1.5rem; border-radius: 18px; }
            .wb-hero h1 { font-size: 1.55rem; }
            .wb-stage-grid, .wb-method-grid { grid-template-columns: 1fr; }
            .pf-method-grid { grid-template-columns: 1fr; }
            .pf-method.featured { grid-column: span 1; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe(value: object) -> str:
    """Escape values inserted into the small HTML presentation layer."""
    return html.escape(str(value))


def _format_seconds(seconds: float | None) -> str:
    if not seconds:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


@st.cache_resource(show_spinner="加载索引配置…")
def cached_config(index_dir: str) -> object:
    """读配置。GraphRAG 的配置对象放到资源缓存里复用。"""
    return load_config(Path(index_dir))


@st.cache_data(ttl=30, show_spinner=False)
def cached_table(index_dir: str, name: str) -> pd.DataFrame:
    """读一个产出表，短 TTL，避免建索引后一直看到旧数据。"""
    return load_table(index_dir, name)


@st.cache_data(ttl=30, show_spinner=False)
def community_level(index_dir: str) -> int:
    """Global 用的社区层级：环境变量优先，否则取索引最高层。"""
    override = os.environ.get("GRAPHRAG_COMMUNITY_LEVEL")
    if override:
        return int(override)
    levels = community_levels(index_dir)
    return max(levels) if levels else 0


def graph_tables(index_dir: str) -> dict[str, pd.DataFrame]:
    """检索需要的全部产物表。"""
    names = (
        "entities",
        "relationships",
        "text_units",
        "communities",
        "community_reports",
        "documents",
        "covariates",
    )
    return {name: cached_table(index_dir, name) for name in names}


def index_retriever(index_dir: str) -> GraphRetriever:
    """建一个可复用的检索器：自定义方法和 native trace 共用它。"""
    tables = graph_tables(index_dir)
    return GraphRetriever(
        entities=tables["entities"],
        relationships=tables["relationships"],
        text_units=tables["text_units"],
        community_reports=tables["community_reports"],
        communities=tables["communities"],
        documents=tables["documents"],
    )


def finish_native(
    query: str,
    method: SearchMethod,
    answer: object,
    context: object,
    retriever: GraphRetriever | None,
) -> tuple[object, dict[str, pd.DataFrame], object]:
    """原生方法：用同一套 trace schema 补出证据链，并追加到 parquet。"""
    data = context if isinstance(context, dict) else {}
    trace = None
    if retriever is not None:
        try:
            trace = trace_from_context(
                query=query, method=method, context=data, retriever=retriever
            )
            save_trace(INDEX_DIR, trace)
        except Exception as error:  # noqa: BLE001 - 证据链失败不挡住答案
            st.warning(f"证据链生成/落盘失败：{type(error).__name__}: {error}")
    return answer, data, trace


async def run_search(
    method: SearchMethod,
    query: str,
    index_dir: str,
    retriever: GraphRetriever | None = None,
):
    """跑一种检索方法，返回 (答案, 检索上下文, 证据链)。"""
    config = cached_config(index_dir)
    tables = graph_tables(index_dir)
    if method is SearchMethod.MICROSOFT_GLOBAL:
        answer, context = await api.global_search(
            config=config,
            entities=tables["entities"],
            communities=tables["communities"],
            community_reports=tables["community_reports"],
            community_level=community_level(index_dir),
            dynamic_community_selection=False,
            response_type=RESPONSE_TYPE,
            query=query,
        )
        return finish_native(query, method, answer, context, retriever)
    if method is SearchMethod.MICROSOFT_LOCAL:
        answer, context = await api.local_search(
            config=config,
            entities=tables["entities"],
            communities=tables["communities"],
            community_reports=tables["community_reports"],
            text_units=tables["text_units"],
            relationships=tables["relationships"],
            covariates=None if tables["covariates"].empty else tables["covariates"],
            community_level=community_level(index_dir),
            response_type=RESPONSE_TYPE,
            query=query,
        )
        return finish_native(query, method, answer, context, retriever)
    if method is SearchMethod.MICROSOFT_DRIFT:
        answer, context = await api.drift_search(
            config=config,
            entities=tables["entities"],
            communities=tables["communities"],
            community_reports=tables["community_reports"],
            text_units=tables["text_units"],
            relationships=tables["relationships"],
            community_level=community_level(index_dir),
            response_type=RESPONSE_TYPE,
            query=query,
        )
        return finish_native(query, method, answer, context, retriever)
    if method is SearchMethod.MICROSOFT_BASIC:
        answer, context = await api.basic_search(
            config=config,
            text_units=tables["text_units"],
            response_type=RESPONSE_TYPE,
            query=query,
        )
        return finish_native(query, method, answer, context, retriever)

    # 三个项目方法：复用 graphrag6-retrieval 的检索和生成实现。
    text_store, entity_store, embedding_model = create_embedding_resources(config)
    model, model_params = create_completion_resource(config)
    bundle = build_custom_bundle(
        query=query,
        method=method,
        retriever=retriever or index_retriever(index_dir),
        text_store=text_store,
        entity_store=entity_store,
        embedding_model=embedding_model,
    )
    answer, _ = await generate_answer(
        query=query,
        method=method,
        bundle=bundle,
        model=model,
        model_params=model_params,
    )
    try:
        save_trace(INDEX_DIR, bundle.trace)
    except Exception as error:  # noqa: BLE001 - trace 落盘失败不挡住答案
        st.warning(f"检索 trace 落盘失败：{type(error).__name__}: {error}")
    return answer, bundle.context, bundle.trace


def start_build(index_dir: Path, method: str) -> Queue:
    """后台线程跑建索引；进度通过回调队列返回，避免阻塞页面。"""
    queue: Queue = Queue()
    callbacks = QueueCallbacks(queue)

    def worker() -> None:
        try:
            config = load_config(index_dir)
            results = asyncio.run(
                build_index(config=config, method=method, callbacks=[callbacks])
            )
            broken = failed_workflows(results)
            if broken:
                queue.put({
                    "type": "error",
                    "message": "这些阶段失败了：" + "、".join(broken),
                })
        except BaseException as error:  # noqa: BLE001 - 错误要显示在界面上
            queue.put({"type": "error", "message": f"{type(error).__name__}: {error}"})
        finally:
            queue.put({"type": "end"})

    threading.Thread(target=worker, daemon=True).start()
    return queue


def render_hero() -> None:
    """Render the page-level identity instead of the default blank header."""
    state = "已连接" if INDEX_DIR.exists() else "等待索引目录"
    st.markdown(
        f"""
        <section class="wb-hero">
            <div class="wb-eyebrow">PATHFUSIONRAG · RESEARCH WORKBENCH</div>
            <h1>把检索结果变成可追溯的证据链</h1>
            <p>PathFusionRAG 将 BM25、Dense Retrieval 与有限跳数图路径融合，并统一展示实体、关系、文本证据、子图和路径召回字段。</p>
            <div class="wb-hero-meta">
                <span class="wb-pill"><span class="wb-pill-dot"></span>{_safe(state)}</span>
                <span class="wb-pill">索引 · {_safe(INDEX_DIR.name)}</span>
                <span class="wb-pill">7 种可选检索策略</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, caption: str) -> None:
    st.markdown(
        f"""
        <div class="wb-section">
            <div class="wb-section-title">{_safe(title)}</div>
            <div class="wb-section-caption">{_safe(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stage_overview(snapshot: object) -> None:
    """Show a dense visual overview before the detailed expanders."""
    cards: list[str] = []
    for number, facts in enumerate(snapshot.stages, start=1):
        produced = facts.produced
        status = "已产出" if produced else "待补齐"
        status_class = "wb-status-ok" if produced else "wb-status-empty"
        card_class = "wb-stage-card" if produced else "wb-stage-card is-empty"
        cards.append(
            f'<article class="{card_class}"><div class="wb-stage-no">PHASE {number:02d}</div>'
            f'<div class="wb-stage-title">{_safe(facts.stage.name)}</div>'
            f'<div class="wb-stage-note">{_safe(facts.stage.note)}</div>'
            f'<div class="wb-stage-foot"><span class="{status_class}">{status}</span>'
            f"<span>{facts.rows:,} 行 · {_format_seconds(facts.seconds)}</span></div></article>"
        )
    st.html(f'<div class="wb-stage-grid">{"".join(cards)}</div>')


def render_guide() -> None:
    cards = (
        ("01", "先看健康度", "确认 settings、文档、实体关系、社区和向量库是否齐全。"),
        (
            "02",
            "再做方法对照",
            "在“检索对照”中同时选择基线和项目方法，输入同一个问题。",
        ),
        (
            "03",
            "最后审证据链",
            "展开结果中的证据链，查看路径高亮、子图和可持久化的 trace 字段。",
        ),
    )
    st.html(
        '<div class="wb-guide-grid">'
        + "".join(
            f'<article class="wb-guide-card"><div class="wb-guide-no">{number}</div>'
            f'<div class="wb-guide-title">{_safe(title)}</div>'
            f'<div class="wb-guide-body">{_safe(body)}</div></article>'
            for number, title, body in cards
        )
        + "</div>"
    )


def render_home_tab() -> None:
    """Render the method-oriented landing page for the PathFusionRAG system."""
    st.html(
        """
        <div class="pf-intro-grid">
            <article class="pf-panel accent">
                <div class="pf-label">SYSTEM THESIS</div>
                <h3>为什么从 Vector RAG 走到 GraphRAG？</h3>
                <p>Vector RAG 擅长回答“某个具体事实在哪里”，但它只检索相似文本，不知道实体之间为什么能连起来。GraphRAG 把文本进一步组织为实体、关系、社区和报告，让检索从相似片段升级为可解释的结构化证据。</p>
                <ul>
                    <li>直接事实：词项和语义相似度通常已经足够。</li>
                    <li>跨文档问题：需要实体关系把分散片段连成链。</li>
                    <li>全局总结：需要社区报告覆盖整个语料主题。</li>
                </ul>
            </article>
            <article class="pf-panel">
                <div class="pf-label">PROJECT METHOD</div>
                <h3>PathFusionRAG</h3>
                <p>基于约束图路径融合的多通道检索增强生成方法。它把精确词项、语义匹配和有限跳数图路径放在同一个 scoring framework 中，目标是在单事实、跨文档和多跳问题之间取得更稳定的综合性能。</p>
                <div class="pf-mini">Lexical + Dense + Constrained Graph Path</div>
            </article>
        </div>
        <div class="pf-flow">
            <div class="pf-flow-step"><strong>Vector RAG</strong><span>chunk → embedding → top-k 相似文本</span></div>
            <div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>GraphRAG Index</strong><span>实体 / 关系 / 社区报告</span></div>
            <div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>PathFusionRAG</strong><span>候选证据 + 有限路径 + trace</span></div>
            <div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>可审计答案</strong><span>实体—关系—文本证据链</span></div>
        </div>
        """
    )

    render_section(
        "七种方法怎么分工",
        "它们解决的是不同的检索瓶颈；没有脱离任务、数据和模型条件的唯一最优方法。",
    )
    method_cards = (
        (
            "Basic / Vector RAG",
            "文本相似度",
            "chunk embedding 后取 top-k 文本",
            "单事实、明确答案位置",
            "不理解实体关系，多跳容易漏证据",
        ),
        (
            "Microsoft GraphRAG · Local",
            "实体种子 + 局部图",
            "从 query 相关实体向关系、文本和社区扩张",
            "某人、某事件附近的局部关系",
            "第一跳 seed 错了会漏掉后续实体",
        ),
        (
            "Microsoft GraphRAG · Global",
            "社区报告 + map/reduce",
            "多个 community report 分别回答后汇总",
            "整个数据集的主题、趋势和总结",
            "调用成本高，摘要可能损失细节",
        ),
        (
            "Microsoft GraphRAG · DRIFT",
            "社区引导的迭代探索",
            "从社区线索不断深入局部证据",
            "复杂、开放式、需要探索的问题",
            "延迟和编排复杂度更高",
        ),
        (
            "LightRAG 风格",
            "低层 + 高层双路",
            "具体实体/属性与整体主题并行检索，再回链文本",
            "多主题、多人物、跨文档聚合",
            "community expansion 可能带来噪声",
        ),
        (
            "HippoRAG 2 风格",
            "seed + PPR 传播",
            "让相关性沿图边传播，找隐式多跳实体",
            "第二跳实体不在 query 中的关联问题",
            "错误边、超级节点也会放大噪声",
        ),
        (
            "PathFusionRAG",
            "词项 + Dense + 约束路径",
            "候选文本先经 lexical/dense 召回，再用最大 2-hop BFS 做结构约束",
            "既要精确，又要跨实体和可解释路径",
            "权重、top-k、hop 仍需固定验证集校准",
        ),
    )
    method_html = []
    for name, kind, mechanism, best_for, risk in method_cards:
        featured = " featured" if name == "PathFusionRAG" else ""
        method_html.append(
            f'<article class="pf-method{featured}"><div class="pf-method-head">'
            f'<div class="pf-method-name">{_safe(name)}</div><div class="pf-method-kind">{_safe(kind)}</div></div>'
            f"<p><strong>机制：</strong>{_safe(mechanism)}</p>"
            f"<p><strong>最佳场景：</strong>{_safe(best_for)}</p>"
            f"<p><strong>主要风险：</strong>{_safe(risk)}</p></article>"
        )
    st.html(f'<div class="pf-method-grid">{"".join(method_html)}</div>')

    render_section(
        "重点方法：PathFusionRAG",
        "把 Basic RAG 的精确性、Dense 的语义泛化和 HippoRAG 2 的图多跳能力组合起来，但不让相关性无限扩散。",
    )
    st.html(
        """
        <div class="pf-formula">
            <div class="equation">Score(text) = 0.35 · S<sub>BM25</sub> + 0.35 · S<sub>Dense</sub> + 0.30 · S<sub>Path</sub></div>
            <div class="formula-note">当前实现的可解释默认权重；正式结论仍需在固定验证集上完成消融和校准。</div>
        </div>
        <div class="pf-signal-grid">
            <article class="pf-signal"><div class="pf-signal-no">01 / LEXICAL</div><h4>BM25 精确匹配</h4><p>保留人名、机构名、事件名等直接词项证据，避免图扩张掩盖原文中的关键事实。</p></article>
            <article class="pf-signal"><div class="pf-signal-no">02 / SEMANTIC</div><h4>Dense 语义召回</h4><p>补回没有共享关键词、但语义表达一致的文本；复用已有 GraphRAG 向量资源。</p></article>
            <article class="pf-signal"><div class="pf-signal-no">03 / STRUCTURE</div><h4>Constrained Graph Path</h4><p>对 seed 到候选文本实体运行最大 2-hop BFS；路径既是多跳信号，也是证据可信度的门控。</p></article>
        </div>
        <div class="pf-flow">
            <div class="pf-flow-step"><strong>Query</strong><span>问题输入</span></div><div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>BM25 + Dense</strong><span>实体 / 关系 / 文本候选</span></div><div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>Seed entities</strong><span>选取高分实体种子</span></div><div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>≤ 2-hop BFS</strong><span>seed ↔ evidence entity</span></div><div class="pf-flow-arrow">→</div>
            <div class="pf-flow-step"><strong>Fusion + Trace</strong><span>证据、路径、子图交给 LLM</span></div>
        </div>
        <div class="pf-story"><p><strong>和 HippoRAG 2 的关键区别：</strong>HippoRAG 把图当作 propagation，让相关性在全图继续传播；PathFusionRAG 把图当作 constrained evidence path，文本首先要有 lexical / semantic 候选资格，再检查是否能通过有限长度路径连接到 query seed。因此它保留多跳能力，同时降低 PPR 无限扩散图噪声的风险。</p></div>
        """
    )

    render_section(
        "六个公开数据集：机制对应什么场景",
        "这组数据集把直接事实、跨文档多跳、长文档证据和全局总结区分开，适合验证方法的适用边界。",
    )
    dataset_cards = (
        (
            "Natural Questions",
            "开放域 QA · 直接事实",
            "真实 Google 搜索查询 + Wikipedia，适合检验图结构对传统事实检索是否必要。",
        ),
        (
            "HotpotQA",
            "Multi-hop QA · supporting facts",
            "明确要求多个 supporting documents 和 supporting facts，是经典的可解释跨文档多跳基准。",
        ),
        (
            "2WikiMultiHopQA",
            "Multi-hop QA · 显式路径",
            "结合 Wikipedia 与 Wikidata，并提供 evidence reasoning path，适合直接测实体、关系和路径召回。",
        ),
        (
            "MuSiQue",
            "2–4 hop QA · anti-shortcut",
            "由 single-hop 问题组合而成，刻意减少 shortcut，最能检验连续图传播能力。",
        ),
        (
            "Qasper",
            "科研论文 QA · 长文档",
            "研究人员针对完整论文提问，答案往往分散在 Introduction、Method、Experiments 等不同部分。",
        ),
        (
            "QMSum",
            "长会议 · query-focused summary",
            "同一场会议包含多人和多个主题，天然偏向 Global / 高层主题聚合与完整覆盖。",
        ),
    )
    dataset_html = []
    for name, task, description in dataset_cards:
        dataset_html.append(
            f'<article class="pf-dataset"><h4>{_safe(name)}</h4><div class="pf-task">{_safe(task)}</div>'
            f"<p>{_safe(description)}</p></article>"
        )
    st.html(f'<div class="pf-dataset-grid">{"".join(dataset_html)}</div>')

    render_section(
        "汇报版方法对照分数",
        "这张表按你提供的实验故事呈现：PathFusionRAG 强调整体鲁棒性，但在真正 4-hop 或全局总结场景不必然第一。",
    )
    st.html(
        '<div class="pf-score-note"><strong>数据状态：</strong>以下是你提供的汇报版对照数据，当前仓库尚未完成这六个公开 benchmark 的统一重跑。正式报告前必须固定数据、问题、embedding、LLM、context budget、answer protocol 和评测脚本后复核；这里不把它们标记为本仓库已验证实验结果。</div>'
    )
    score_frame = pd.DataFrame(
        [[dataset, *scores] for dataset, scores in DATASET_SCORES.items()],
        columns=[
            "Dataset",
            "Basic RAG",
            "GraphRAG Local",
            "GraphRAG Global",
            "LightRAG",
            "HippoRAG 2",
            "PathFusionRAG",
        ],
    )
    st.dataframe(score_frame, hide_index=True, use_container_width=True)
    st.html(
        """
        <div class="pf-story"><p><strong>如何解读：</strong>Natural Questions 偏直接事实，Basic 与 PathFusionRAG 更合适；HotpotQA 和 2WikiMultiHopQA 需要跨文档与显式路径，HippoRAG 2 / PathFusionRAG 应上升；MuSiQue 的 2–4 hop 超出当前 PathFusionRAG 最大 2-hop 设置，因此 HippoRAG 2 可能更高；QMSum 需要覆盖整场会议，LightRAG / Global 更有优势。这个分布比“所有数据集都第一”更能说明机制与场景的对应关系。</p></div>
        """
    )


def render_build_tab() -> None:
    """Render index health, stage overview, controls and detailed artifacts."""
    render_section(
        "索引健康度", "先确认当前索引目录，再展开任意阶段查看 parquet 产物与 cache。"
    )
    st.markdown(
        f'<div class="wb-path">当前目录 · {_safe(INDEX_DIR)}</div>',
        unsafe_allow_html=True,
    )
    if not INDEX_DIR.exists():
        st.markdown(
            '<div class="wb-empty-state"><div class="wb-empty-icon">◎</div>'
            '<div class="wb-empty-title">还没有接入索引目录</div>'
            '<div class="wb-empty-body">请设置 GRAPHRAG_INDEX 环境变量，指向包含 output/、lancedb/ 和 settings.yaml 的索引目录，然后刷新页面。</div></div>',
            unsafe_allow_html=True,
        )
        return

    snapshot = inspect_index(INDEX_DIR)
    top = st.columns(4)
    top[0].metric("配置文件", "已连接" if snapshot.settings_exists else "缺失")
    top[1].metric("文档数", f"{snapshot.document_count or 0:,}")
    top[2].metric("索引耗时", _format_seconds(snapshot.total_seconds))
    top[3].metric(
        "社区层级",
        "/".join(str(level) for level in snapshot.community_levels) or "—",
        help="Global 检索默认用最高一层，可用 GRAPHRAG_COMMUNITY_LEVEL 覆盖。",
    )

    produced = sum(facts.produced for facts in snapshot.stages)
    total = len(snapshot.stages)
    st.markdown(
        f'<div class="wb-result-meta">阶段完成度 · {produced}/{total} · 日志 {snapshot.log_lines:,} 行</div>',
        unsafe_allow_html=True,
    )
    st.progress(produced / total if total else 0.0)

    if not snapshot.settings_exists:
        st.markdown(
            '<div class="wb-alert-card">当前目录没有 settings.yaml：阶段产物仍可浏览，但 native GraphRAG 和项目方法的在线问答需要完整配置与模型服务。</div>',
            unsafe_allow_html=True,
        )
    if snapshot.run_completed is False:
        st.warning(
            "最近一次索引运行没有正常结束（stats.json 里没有总耗时）。产物可能不完整，请展开阶段和日志定位失败 workflow。"
        )
    if snapshot.unmapped_workflows:
        st.warning(
            f"这些 workflow 还没有归入任何阶段：{', '.join(snapshot.unmapped_workflows)}"
        )

    render_section(
        "七阶段总览", "颜色条表示阶段是否已经产出，下面的展开面板保留原始产物检查能力。"
    )
    render_stage_overview(snapshot)
    render_guide()

    render_section("阶段详情", "按需打开；表格默认只展示前 30 行，避免页面被大表拖慢。")
    for facts in snapshot.stages:
        state = "已产出" if facts.produced else "待补齐"
        head = f"{facts.stage.name} · {state} · {facts.rows:,} 行"
        if facts.seconds:
            head += f" · {facts.seconds:.0f}s"
        with st.expander(head, expanded=False):
            st.caption(facts.stage.note)
            st.caption(f"workflow：{', '.join(facts.stage.workflows)}")
            for artifact in facts.artifacts:
                mark = "存在" if artifact.exists else "缺失"
                st.write(f"`{artifact.path}` — {mark}，{artifact.rows or 0:,} 行")
                if artifact.is_table and artifact.exists:
                    frame = cached_table(str(INDEX_DIR), Path(artifact.path).stem)
                    st.dataframe(frame.head(30), height=220, hide_index=True)
            if facts.cache_files:
                st.caption(
                    "cache："
                    + "，".join(
                        f"{key} {value} 文件"
                        for key, value in facts.cache_files.items()
                    )
                )

    render_section(
        "索引操作",
        "重建索引会写入当前目录，请确认 settings.yaml 和模型服务已经准备好。",
    )
    left, right = st.columns([1, 2])
    method = left.selectbox("索引方法", ("standard", "fast"), index=0)
    if left.button("开始建索引", type="primary", use_container_width=True):
        if st.session_state.get("build_running"):
            st.warning("已经有一个建索引任务在运行。")
        else:
            st.session_state["build_queue"] = start_build(INDEX_DIR, method)
            st.session_state["build_running"] = True
            st.rerun()
    right.markdown(
        '<div class="wb-guide-card"><div class="wb-guide-title">建议操作顺序</div>'
        '<div class="wb-guide-body">先用 fast 验证链路，再用 standard 生成质量更高的实体、关系与社区报告。查询前请确认向量服务和 completion model 可用。</div></div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("build_running"):
        queue: Queue = st.session_state["build_queue"]
        state = ProgressState()
        bar = st.progress(0.0)
        line = st.empty()
        while True:
            for event in drain(queue):
                if event.get("type") == "end":
                    st.session_state["build_running"] = False
                state.apply(event)
            bar.progress(min(state.percent / 100.0, 1.0))
            line.write(
                f"当前：{state.running or '—'}　完成 {len(state.finished)}/{len(state.planned)}"
                f"　{state.completed_items}/{state.total_items}"
            )
            if not st.session_state["build_running"]:
                break
            time.sleep(0.5)
        if state.error:
            st.error(state.error)
        else:
            st.success("建索引完成，产物已刷新。")
            st.cache_data.clear()
            st.rerun()

    if st.button("清缓存并刷新", use_container_width=False):
        st.cache_data.clear()
        st.rerun()
    if snapshot.log_tail:
        with st.expander("查看最近日志", expanded=False):
            st.code(snapshot.log_tail, language="text")


def render_method_cards(methods: list[SearchMethod]) -> None:
    """Render a visible method legend when the user has not submitted a query."""
    cards: list[str] = []
    for method in SearchMethod:
        code, title, body, family = METHOD_META[method]
        selected_class = " is-selected" if method in methods else ""
        cards.append(
            f'<article class="wb-method-card{selected_class}"><div class="wb-method-top">'
            f'<span class="wb-method-code">{_safe(code)}</span><span class="wb-chip">{_safe(family)}</span></div>'
            f'<div class="wb-method-title">{_safe(title)}</div>'
            f'<div class="wb-method-body">{_safe(body)}</div></article>'
        )
    st.html(f'<div class="wb-method-grid">{"".join(cards)}</div>')


def render_search_landing(methods: list[SearchMethod]) -> None:
    selected = "、".join(method.label for method in methods) if methods else "尚未选择"
    st.markdown(
        f"""
        <div class="wb-empty-state">
            <div class="wb-empty-icon">⌁</div>
            <div class="wb-empty-title">从一个问题开始</div>
            <div class="wb-empty-body">当前选择：<strong>{_safe(selected)}</strong>。输入同一个问题即可并排比较答案质量、证据覆盖和图路径；没有 query 时这里也会保留方法说明，避免页面出现大片空白。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_section(
        "方法地图",
        "蓝色边框代表当前已勾选的方法；推荐先比较 Microsoft Local、Global 和 PathFusionRAG。",
    )
    render_method_cards(methods)


def render_result(method: SearchMethod, result: object) -> None:
    """Render one method result as a readable answer + evidence workspace."""
    code, title, body, family = METHOD_META[method]
    st.markdown(
        f'<div class="wb-method-top"><span class="wb-method-code">{_safe(code)} · {_safe(family)}</span><span class="wb-chip">{_safe(title)}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(body)
    if isinstance(result, BaseException):
        st.markdown(
            f'<div class="wb-alert-card">该方法暂时无法运行：{_safe(type(result).__name__)} · {_safe(result)}</div>',
            unsafe_allow_html=True,
        )
        return
    answer, context, trace = result
    safe_answer = _safe(answer).replace("\n", "<br>")
    st.markdown(
        f'<div class="wb-answer-card"><div class="wb-answer-label">ANSWER · {_safe(method.value)}</div>{safe_answer}</div>',
        unsafe_allow_html=True,
    )
    if trace is not None:
        stats = trace_view.summary(trace)
        stat_columns = st.columns(min(max(len(stats), 1), 6))
        for column, (key, value) in zip(stat_columns, stats.items(), strict=False):
            column.metric(key, value)
        with st.expander("证据链与子图", expanded=True):
            render_evidence(trace)
    with st.expander("检索上下文 / 引用", expanded=False):
        if not context:
            st.info("该方法没有返回可展示的上下文表。")
        for name, frame in (context or {}).items():
            st.caption(name)
            if isinstance(frame, pd.DataFrame):
                st.dataframe(frame, height=240, hide_index=True)
            else:
                st.write(frame)


def render_search_tab() -> None:
    """Render method selection, query entry, answer tabs and evidence chain."""
    render_section(
        "检索对照",
        "多选方法共享同一个问题；每个结果都可以继续展开实体、关系、路径和文本证据。",
    )
    controls = st.columns([1.05, 1.65])
    methods = controls[0].multiselect(
        "选择检索方法",
        list(SearchMethod),
        default=[SearchMethod.MICROSOFT_LOCAL, SearchMethod.MICROSOFT_GLOBAL],
        format_func=lambda item: item.label,
    )
    query = controls[1].text_input(
        "输入问题",
        placeholder="例如：这次危机中哪些事件彼此相关？",
        help="可以一次选择多个方法，对同一个问题做可解释的对照。",
    )
    if not (query.strip() and methods):
        render_search_landing(methods)
        return
    if not INDEX_DIR.exists():
        st.error("当前索引目录不存在，请先在 GRAPHRAG_INDEX 中指定可用索引。")
        return

    st.markdown(
        f'<div class="wb-path">正在比较 · {_safe(" / ".join(method.label for method in methods))} · 问题：{_safe(query)}</div>',
        unsafe_allow_html=True,
    )
    try:
        retriever = index_retriever(str(INDEX_DIR))
    except Exception as error:  # noqa: BLE001 - 页面给出可操作错误
        st.error(f"读取索引产物失败：{type(error).__name__}: {error}")
        return
    with st.spinner("正在运行所选方法并整理证据链…"):
        results = asyncio.run(
            asyncio.gather(
                *(
                    run_search(method, query, str(INDEX_DIR), retriever)
                    for method in methods
                ),
                return_exceptions=True,
            )
        )
    result_tabs = st.tabs([
        f"{index + 1:02d} · {method.label}" for index, method in enumerate(methods)
    ])
    for pane, method, result in zip(result_tabs, methods, results, strict=True):
        with pane:
            render_result(method, result)


def render_evidence(trace: object) -> None:
    """Render trace fields, recall status, source evidence and highlighted subgraph."""
    stats = trace_view.summary(trace)
    stat_columns = st.columns(min(max(len(stats), 1), 6))
    for column, (key, value) in zip(stat_columns, stats.items(), strict=False):
        column.metric(key, value)

    hint = trace_view.evidence_hint(trace)
    if hint:
        st.info(hint)

    paths = trace_view.path_rows(trace)
    if not paths.empty:
        st.markdown("**图路径**")
        st.dataframe(paths, height=180, hide_index=True)

    for name, frame in trace_view.frames(trace).items():
        if frame.empty:
            continue
        st.markdown(f"**{name}**")
        st.dataframe(frame.head(30), height=200, hide_index=True)

    scores = trace_view.channel_frame(trace)
    if not scores.empty:
        st.markdown("**检索信号分数**")
        st.dataframe(scores, height=160, hide_index=True)

    st.markdown("**召回指标**")
    st.dataframe(trace_view.recall_rows(trace), hide_index=True)

    if trace.retrieved_source_paths:
        st.markdown("**来源路径**")
        for path in trace.retrieved_source_paths:
            st.caption(f"`{path}`")

    dot = trace_view.subgraph_dot(trace)
    if dot:
        st.markdown("**可视化子图**（红色为路径经过的节点与边，浅红为 seed）")
        st.graphviz_chart(dot, width="stretch")


st.session_state.setdefault("build_running", False)
apply_workbench_style()
render_hero()
home_tab, build_tab, search_tab = st.tabs(["首页 · 方法原理", "索引中心", "检索对照"])
with home_tab:
    render_home_tab()
with build_tab:
    render_build_tab()
with search_tab:
    render_search_tab()
