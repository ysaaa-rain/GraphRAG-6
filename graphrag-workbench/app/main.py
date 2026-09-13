# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""GraphRAG 工作台：建索引、看阶段产物、做检索对照。

这是仓库里唯一的检索前端（原上游演示界面 unified-search-app 已删除）：

- ``app/index_view.py``：索引阶段的数据层，只依赖 pandas，可单独测试；
- ``app/trace_view.py``：证据链与子图渲染；
- 检索算法在独立包 ``graphrag6-retrieval`` 里，这里只做界面和编排；
- 索引目录用 GRAPHRAG_INDEX 指定，默认指到仓库里现成的 enron_q001 索引。

启动：``streamlit run app/main.py``（必须从项目根目录运行，让 app/ 进入 sys.path）。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from queue import Queue

import pandas as pd
import streamlit as st
import graphrag.api as api
from graphrag.api import build_index
from graphrag.config.load_config import load_config

from index_view import (
    ProgressState,
    QueueCallbacks,
    community_levels,
    drain,
    failed_workflows,
    inspect_index,
    load_table,
)
import trace_view
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


@st.cache_resource(show_spinner="加载 settings.yaml…")
def cached_config(index_dir: str) -> object:
    """读配置。注意 graphrag 的 load_config 会把进程工作目录切到索引目录。"""
    return load_config(Path(index_dir))


@st.cache_data(ttl=30, show_spinner=False)
def cached_table(index_dir: str, name: str) -> pd.DataFrame:
    """读一个产出表，短 TTL，避免建索引后一直看到旧数据。"""
    return load_table(index_dir, name)


@st.cache_data(ttl=30, show_spinner=False)
def community_level(index_dir: str) -> int:
    """Global 用的社区层级：GRAPHRAG_COMMUNITY_LEVEL 优先，否则取索引里最高一层。"""
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
    """建一个可复用的检索器：自定义方法用它检索，原生方法用它补全证据链。"""
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
        except Exception as error:  # noqa: BLE001 - 证据链失败不该挡住答案
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
            config=config, text_units=tables["text_units"], response_type=RESPONSE_TYPE, query=query
        )
        return finish_native(query, method, answer, context, retriever)

    # 三个自定义方法：复用 rag/ 里已有的检索和生成实现，不重写
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
        query=query, method=method, bundle=bundle, model=model, model_params=model_params
    )
    try:
        save_trace(INDEX_DIR, bundle.trace)
    except Exception as error:  # noqa: BLE001 - trace 落盘失败不应该挡住答案
        st.warning(f"检索 trace 落盘失败：{type(error).__name__}: {error}")
    return answer, bundle.context, bundle.trace


def start_build(index_dir: Path, method: str) -> Queue:
    """后台线程跑建索引；进度通过回调队列返回，避免阻塞界面。"""
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


def render_build_tab() -> None:
    """左侧：索引健康度 + 每个阶段的产物；下面是建索引按钮和进度。"""
    st.caption(f"索引目录：`{INDEX_DIR}`")
    if not INDEX_DIR.exists():
        st.error("索引目录不存在，请用 GRAPHRAG_INDEX 环境变量指定。")
        return

    snapshot = inspect_index(INDEX_DIR)
    top = st.columns(4)
    top[0].metric("settings.yaml", "有" if snapshot.settings_exists else "缺失")
    top[1].metric("文档数", snapshot.document_count or 0)
    top[2].metric("总耗时", f"{(snapshot.total_seconds or 0) / 60:.1f} 分钟")
    top[3].metric(
        "社区层级",
        "/".join(str(level) for level in snapshot.community_levels) or "—",
        help="Global 检索默认用最高一层，可用 GRAPHRAG_COMMUNITY_LEVEL 覆盖",
    )
    st.caption(f"日志 {snapshot.log_lines} 行")
    if snapshot.run_completed is False:
        st.warning(
            "最近一次索引运行没有正常结束（有阶段失败，stats.json 里没有总耗时）。"
            "产物可能不完整，例如向量库没更新；展开下面的阶段和日志能看到是哪一步。"
        )
    if snapshot.unmapped_workflows:
        st.warning(f"这些 workflow 还没有归入任何阶段：{', '.join(snapshot.unmapped_workflows)}")

    for facts in snapshot.stages:
        state = "已产出" if facts.produced else "空"
        head = f"{facts.stage.name} · {state} · {facts.rows} 行"
        if facts.seconds:
            head += f" · {facts.seconds:.0f}s"
        with st.expander(head, expanded=False):
            st.caption(facts.stage.note)
            st.caption(f"workflow：{', '.join(facts.stage.workflows)}")
            for artifact in facts.artifacts:
                mark = "存在" if artifact.exists else "缺失"
                st.write(f"`{artifact.path}` — {mark}，{artifact.rows or 0} 行")
                if artifact.is_table and artifact.exists:
                    frame = cached_table(str(INDEX_DIR), Path(artifact.path).stem)
                    st.dataframe(frame.head(30), height=220)
            if facts.cache_files:
                st.caption(
                    "cache：" + "，".join(f"{k} {v} 文件" for k, v in facts.cache_files.items())
                )

    left, right = st.columns([1, 3])
    method = left.selectbox("索引方法", ("standard", "fast"), index=0)
    if left.button("开始建索引"):
        if "build_queue" in st.session_state and st.session_state["build_running"]:
            st.warning("已经有一个建索引任务在跑。")
        else:
            st.session_state["build_queue"] = start_build(INDEX_DIR, method)
            st.session_state["build_running"] = True

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

    if st.button("清缓存并刷新"):
        st.cache_data.clear()
        st.rerun()
    if snapshot.log_tail:
        st.code(snapshot.log_tail, language="text")


def render_search_tab() -> None:
    """右侧：多种方法并排对照。"""
    methods = st.multiselect(
        "检索方法",
        list(SearchMethod),
        default=[SearchMethod.MICROSOFT_LOCAL, SearchMethod.MICROSOFT_GLOBAL],
        format_func=lambda item: item.label,
    )
    query = st.text_input("问题（可多选方法做对照）")
    if not (query and methods):
        return
    retriever = index_retriever(str(INDEX_DIR))
    with st.spinner("检索中…"):
        results = asyncio.run(
            asyncio.gather(
                *(
                    run_search(method, query, str(INDEX_DIR), retriever)
                    for method in methods
                ),
                return_exceptions=True,
            )
        )
    for column, method, result in zip(st.columns(len(methods)), methods, results, strict=True):
        with column:
            st.markdown(f"##### {method.label}")
            if isinstance(result, BaseException):
                st.error(f"{type(result).__name__}: {result}")
                continue
            answer, context, trace = result
            st.markdown(str(answer))
            if trace is not None:
                with st.expander("证据链与子图"):
                    render_evidence(trace)
            with st.expander("检索上下文 / 引用"):
                for name, frame in (context or {}).items():
                    st.caption(name)
                    st.dataframe(frame, height=240)


def render_evidence(trace: object) -> None:
    """证据链：命中实体/关系、图路径、文本证据、信号分数、召回指标、子图。"""
    stats = trace_view.summary(trace)
    st.caption(" · ".join(f"{key} {value}" for key, value in stats.items()))

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
        st.markdown("**子图**（红色为路径经过的节点与边，浅红为 seed）")
        st.graphviz_chart(dot, width="stretch")


st.set_page_config(page_title="GraphRAG 工作台", layout="wide")
st.session_state.setdefault("build_running", False)
build_tab, search_tab = st.tabs(["建索引与阶段", "检索对照"])
with build_tab:
    render_build_tab()
with search_tab:
    render_search_tab()
