# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

# ruff: noqa: RUF001

"""Sidebar module."""

import streamlit as st
from app_logic import dataset_name, load_dataset
from rag.typing import SearchMethod
from state.session_variables import SessionVariables


def reset_app():
    """Reset app to its original state."""
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()


def update_dataset(sv: SessionVariables):
    """Update dataset from the dropdown."""
    value = st.session_state[sv.dataset.key]
    st.cache_data.clear()
    if "response_lengths" not in st.session_state:
        st.session_state.response_lengths = []
    st.session_state.response_lengths = []
    load_dataset(value, sv)


def update_basic_rag(sv: SessionVariables):
    """Update basic rag state."""
    sv.include_basic_rag.value = st.session_state[sv.include_basic_rag.key]


def update_drift_search(sv: SessionVariables):
    """Update drift rag state."""
    sv.include_drift_search.value = st.session_state[sv.include_drift_search.key]


def update_local_search(sv: SessionVariables):
    """Update local rag state."""
    sv.include_local_search.value = st.session_state[sv.include_local_search.key]


def update_global_search(sv: SessionVariables):
    """Update global rag state."""
    sv.include_global_search.value = st.session_state[sv.include_global_search.key]


def create_side_bar(sv: SessionVariables):
    """Create a side bar panel.."""
    with st.sidebar:
        st.subheader("Options")

        options = [d.key for d in sv.datasets.value]

        def lookup_label(key: str):
            return dataset_name(key, sv)

        st.selectbox(
            "Dataset",
            key=sv.dataset.key,
            on_change=update_dataset,
            kwargs={"sv": sv},
            options=options,
            format_func=lookup_label,
        )
        st.number_input(
            "Number of suggested questions",
            key=sv.suggested_questions.key,
            min_value=1,
            max_value=100,
            step=1,
        )
        st.subheader("检索方法（可多选对照）")
        method_values = [method.value for method in SearchMethod]
        method_labels = {method.value: method.label for method in SearchMethod}
        st.multiselect(
            "选择 GraphRAG 方法",
            options=method_values,
            key=sv.selected_methods.key,
            format_func=lambda value: method_labels.get(value, value),
            help="Microsoft 方法保留原始实现；其他三项在同一 Parquet 图索引上复现对应检索思想。",
        )
        st.caption(
            "自定义方法会额外保存实体、关系、图路径、子图边和文本证据；没有 gold path 时路径召回率显示为 N/A。"
        )
