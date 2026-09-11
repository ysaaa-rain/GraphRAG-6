# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

# ruff: noqa: RUF001

"""Streamlit home page for comparable GraphRAG methods."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import streamlit as st
from app_logic import dataset_name, initialize, run_all_searches, run_generate_questions
from rag.typing import SearchMethod
from st_tabs import TabBar
from ui.questions_list import create_questions_list_ui
from ui.report_details import create_report_details_ui
from ui.report_list import create_report_list_ui
from ui.search import (
    display_citations,
    display_retrieval_trace,
    format_suggested_questions,
    init_search_ui,
)
from ui.sidebar import create_side_bar

if TYPE_CHECKING:
    from state.session_variables import SessionVariables


METHOD_CAPTIONS = {
    SearchMethod.MICROSOFT_BASIC: "文本 chunk 向量检索（无图）",
    SearchMethod.MICROSOFT_LOCAL: "实体—关系—文本的局部 GraphRAG 检索",
    SearchMethod.MICROSOFT_GLOBAL: "社区报告 map/reduce 的全局 GraphRAG",
    SearchMethod.MICROSOFT_DRIFT: "基于社区信息的迭代式 GraphRAG 检索",
    SearchMethod.LIGHTRAG: "低层实体/关系 + 高层社区的双层检索",
    SearchMethod.HIPPORAG2: "实体种子 + 加权 Personalized PageRank 多跳",
    SearchMethod.HYBRID_PATH: "BM25 + dense vector + 路径约束的可解释融合",
}


async def main():
    """Render the query comparison and community explorer tabs."""
    sv = initialize()
    create_side_bar(sv)

    st.markdown("#### GraphRAG 方法对照实验：实体、关系、路径与文本证据")
    st.markdown("##### 当前数据集：" + dataset_name(sv.dataset.value, sv))
    st.markdown(sv.dataset_config.value.description)

    def on_click_reset(sv: SessionVariables):
        sv.generated_questions.value = []
        sv.selected_question.value = ""
        sv.show_text_input.value = True

    def on_change(sv: SessionVariables):
        sv.question.value = st.session_state[question_input]

    question_input = "question_input"
    generate_questions = st.button("生成示例问题")
    question = sv.question.value if len(sv.question.value.strip()) > 0 else ""

    if generate_questions:
        with st.spinner("正在生成示例问题…"):
            try:
                result = await run_generate_questions(
                    query=(
                        "Generate numbered list only with the top "
                        f"{sv.suggested_questions.value} most important questions of this dataset "
                        "(numbered list only without titles or anything extra)"
                    ),
                    sv=sv,
                )
                for result_item in result:
                    sv.generated_questions.value = format_suggested_questions(
                        result_item.response
                    )
                    sv.show_text_input.value = False
            except Exception as exc:  # noqa: BLE001
                st.error(f"示例问题生成失败：{exc}")

    if sv.show_text_input.value:
        st.text_input(
            "输入问题（可同时勾选多个方法进行对照）",
            key=question_input,
            on_change=on_change,
            value=question,
            kwargs={"sv": sv},
        )

    if sv.generated_questions.value:
        create_questions_list_ui(sv)
    if not sv.show_text_input.value:
        st.button(label="重置问题", on_click=on_click_reset, kwargs={"sv": sv})

    tab_id = TabBar(
        tabs=["方法对照与证据链", "Community Explorer"],
        color="#fc9e9e",
        activeColor="#ff4b4b",
        default=0,
    )

    if tab_id == 0:
        if sv.selected_question.value:
            question = sv.selected_question.value
            sv.question.value = question
        if question:
            st.write(f"##### 问题：*{question}*")

        methods = [
            SearchMethod(value)
            for value in sv.selected_methods.value
            if value in {method.value for method in SearchMethod}
        ]
        if not methods:
            st.warning("请在左侧至少选择一个检索方法。")
        else:
            answer_columns = st.columns(len(methods))
            citation_columns = st.columns(len(methods))
            citation_containers = {}
            for index, method in enumerate(methods):
                citation_containers[method] = citation_columns[index]
                with answer_columns[index]:
                    init_search_ui(
                        container=answer_columns[index],
                        search_type=method.search_type,
                        title=f"##### {method.label}",
                        caption=f"###### {METHOD_CAPTIONS[method]}",
                    )

            if question and question != sv.question_in_progress.value:
                sv.question_in_progress.value = question
                st.session_state.response_lengths = []
                try:
                    results = await run_all_searches(query=question, sv=sv)
                    result_by_method = {
                        result.method: result for result in results if result.method
                    }
                    for method in methods:
                        result = result_by_method.get(method)
                        if result is None:
                            continue
                        display_citations(
                            container=citation_containers[method], result=result
                        )
                        display_retrieval_trace(
                            container=citation_containers[method], result=result
                        )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"检索失败：{exc}")

    if tab_id == 1:
        report_list, report_content = st.columns([0.33, 0.67])
        with report_list:
            st.markdown("##### Community Reports")
            create_report_list_ui(sv)
        with report_content:
            st.markdown("##### Selected Report")
            create_report_details_ui(sv)


if __name__ == "__main__":
    asyncio.run(main())
