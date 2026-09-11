# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""App logic module."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import graphrag.api as api
import streamlit as st
from knowledge_loader.data_sources.loader import (
    create_datasource,
    load_dataset_listing,
)
from knowledge_loader.model import load_model
from rag.custom_search import (
    build_custom_bundle,
    create_completion_resource,
    create_embedding_resources,
    generate_answer,
)
from rag.retrieval import GraphRetriever, trace_from_context
from rag.trace_store import save_trace
from rag.typing import SearchMethod, SearchResult, SearchType
from state.session_variables import SessionVariables
from ui.search import display_search_result

if TYPE_CHECKING:
    import pandas as pd

logging.basicConfig(level=logging.INFO)
logging.getLogger("azure").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def initialize() -> SessionVariables:
    """Initialize app logic."""
    if "session_variables" not in st.session_state:
        st.set_page_config(
            layout="wide",
            initial_sidebar_state="collapsed",
            page_title="GraphRAG",
        )
        sv = SessionVariables()
        datasets = load_dataset_listing()
        sv.datasets.value = datasets
        sv.dataset.value = (
            st.query_params["dataset"].lower()
            if "dataset" in st.query_params
            else datasets[0].key
        )
        load_dataset(sv.dataset.value, sv)
        st.session_state["session_variables"] = sv
    return st.session_state["session_variables"]


def load_dataset(dataset: str, sv: SessionVariables):
    """Load dataset from the dropdown."""
    sv.dataset.value = dataset
    sv.dataset_config.value = next(
        (d for d in sv.datasets.value if d.key == dataset), None
    )
    if sv.dataset_config.value is not None:
        sv.datasource.value = create_datasource(f"{sv.dataset_config.value.path}")  # type: ignore
        sv.graphrag_config.value = sv.datasource.value.read_settings("settings.yaml")
        load_knowledge_model(sv)


def dataset_name(key: str, sv: SessionVariables) -> str:
    """Get dataset name."""
    return next((d for d in sv.datasets.value if d.key == key), None).name  # type: ignore


async def run_all_searches(query: str, sv: SessionVariables) -> list[SearchResult]:
    """Run the methods selected in the sidebar and return comparable results."""
    selected_values = sv.selected_methods.value
    if isinstance(selected_values, str):
        selected_values = [selected_values]
    selected = [
        SearchMethod(value)
        for value in selected_values
        if value in {method.value for method in SearchMethod}
    ]
    runners = {
        SearchMethod.MICROSOFT_DRIFT: run_drift_search,
        SearchMethod.MICROSOFT_BASIC: run_basic_search,
        SearchMethod.MICROSOFT_LOCAL: run_local_search,
        SearchMethod.MICROSOFT_GLOBAL: run_global_search,
        SearchMethod.LIGHTRAG: run_lightrag_search,
        SearchMethod.HIPPORAG2: run_hipporag_search,
        SearchMethod.HYBRID_PATH: run_hybrid_path_search,
    }
    tasks = [runners[method](query=query, sv=sv) for method in selected]

    return await asyncio.gather(*tasks)


def _record_result(sv: SessionVariables, result: SearchResult) -> SearchResult:
    """Render, persist, and retain a result for the current question."""
    container = st.session_state.get(f"{result.search_type.value.lower()}_container")
    if container is not None:
        display_search_result(container=container, result=result, stats=None)
    if result.trace is not None:
        try:
            save_trace(sv.datasource.value, result.trace)
        except Exception as exc:  # noqa: BLE001 - UI must still show the answer
            logger.warning("retrieval trace persistence failed: %s", exc)
    if "response_lengths" not in st.session_state:
        st.session_state.response_lengths = []
    st.session_state.response_lengths.append({
        "result": result,
        "search": result.search_type.value.lower(),
        "method": result.method.value if result.method else result.search_type.value,
    })
    return result


def _graph_retriever(sv: SessionVariables) -> GraphRetriever:
    """Build a schema-compatible retriever for the loaded dataset."""
    return GraphRetriever(
        entities=sv.entities.value,
        relationships=sv.relationships.value,
        text_units=sv.text_units.value,
        community_reports=sv.community_reports.value,
        communities=sv.communities.value,
        documents=sv.documents.value,
    )


def _custom_resources(
    sv: SessionVariables,
) -> tuple[object | None, object | None, object | None, object | None, dict]:
    """Lazily load vector stores, embedding model, and completion model."""
    if not sv.embedding_model.value:
        text_store, entity_store, embedding_model = create_embedding_resources(
            sv.graphrag_config.value
        )
        sv.text_vector_store.value = text_store
        sv.entity_vector_store.value = entity_store
        sv.embedding_model.value = embedding_model
    if not sv.completion_model.value:
        model, model_params = create_completion_resource(sv.graphrag_config.value)
        sv.completion_model.value = model
        sv.completion_model_params.value = model_params
    return (
        sv.text_vector_store.value,
        sv.entity_vector_store.value,
        sv.embedding_model.value,
        sv.completion_model.value,
        sv.completion_model_params.value,
    )


async def _run_custom_search(
    query: str,
    sv: SessionVariables,
    method: SearchMethod,
) -> SearchResult:
    """Run a custom retrieval policy followed by the shared grounded prompt."""
    text_store, entity_store, embedding_model, completion_model, model_params = (
        _custom_resources(sv)
    )
    retriever = _graph_retriever(sv)
    bundle = build_custom_bundle(
        query=query,
        method=method,
        retriever=retriever,
        text_store=text_store,
        entity_store=entity_store,
        embedding_model=embedding_model,
    )
    response, _stats = await generate_answer(
        query=query,
        method=method,
        bundle=bundle,
        model=completion_model,
        model_params=model_params,
    )
    return _record_result(
        sv,
        SearchResult(
            search_type=method.search_type,
            method=method,
            response=response,
            context=bundle.context,
            trace=bundle.trace,
        ),
    )


async def run_lightrag_search(query: str, sv: SessionVariables) -> SearchResult:
    """Run the LightRAG-style dual-level method."""
    return await _run_custom_search(query, sv, SearchMethod.LIGHTRAG)


async def run_hipporag_search(query: str, sv: SessionVariables) -> SearchResult:
    """Run the HippoRAG 2-style PPR method."""
    return await _run_custom_search(query, sv, SearchMethod.HIPPORAG2)


async def run_hybrid_path_search(query: str, sv: SessionVariables) -> SearchResult:
    """Run the project's constrained hybrid path method."""
    return await _run_custom_search(query, sv, SearchMethod.HYBRID_PATH)


async def run_generate_questions(query: str, sv: SessionVariables):
    """Run global search to generate questions for the dataset."""
    tasks = []

    tasks.append(
        run_global_search_question_generation(
            query=query,
            sv=sv,
        )
    )

    return await asyncio.gather(*tasks)


async def run_global_search_question_generation(
    query: str,
    sv: SessionVariables,
) -> SearchResult:
    """Run global search question generation process."""
    empty_context_data: dict[str, pd.DataFrame] = {}

    response, context_data = await api.global_search(
        config=sv.graphrag_config.value,
        entities=sv.entities.value,
        communities=sv.communities.value,
        community_reports=sv.community_reports.value,
        dynamic_community_selection=True,
        response_type="Single paragraph",
        community_level=sv.dataset_config.value.community_level,
        query=query,
    )

    # display response and reference context to UI
    return SearchResult(
        search_type=SearchType.Global,
        method=SearchMethod.MICROSOFT_GLOBAL,
        response=str(response),
        context=context_data if isinstance(context_data, dict) else empty_context_data,
        trace=trace_from_context(
            query=query,
            method=SearchMethod.MICROSOFT_GLOBAL,
            context=context_data
            if isinstance(context_data, dict)
            else empty_context_data,
            retriever=_graph_retriever(sv),
        ),
    )


async def run_local_search(
    query: str,
    sv: SessionVariables,
) -> SearchResult:
    """Run local search."""
    print(f"Local search query: {query}")  # noqa T201

    # build local search engine
    response_placeholder = st.session_state[
        f"{SearchType.Local.value.lower()}_response_placeholder"
    ]
    with response_placeholder, st.spinner("Generating answer using local search..."):
        empty_context_data: dict[str, pd.DataFrame] = {}

        response, context_data = await api.local_search(
            config=sv.graphrag_config.value,
            communities=sv.communities.value,
            entities=sv.entities.value,
            community_reports=sv.community_reports.value,
            text_units=sv.text_units.value,
            relationships=sv.relationships.value,
            covariates=sv.covariates.value,
            community_level=sv.dataset_config.value.community_level,
            response_type="Multiple Paragraphs",
            query=query,
        )

        print(f"Local Response: {response}")  # noqa T201
        print(f"Context data: {context_data}")  # noqa T201

    context = context_data if isinstance(context_data, dict) else empty_context_data
    search_result = SearchResult(
        search_type=SearchType.Local,
        method=SearchMethod.MICROSOFT_LOCAL,
        response=str(response),
        context=context,
        trace=trace_from_context(
            query=query,
            method=SearchMethod.MICROSOFT_LOCAL,
            context=context,
            retriever=_graph_retriever(sv),
        ),
    )
    return _record_result(sv, search_result)


async def run_global_search(query: str, sv: SessionVariables) -> SearchResult:
    """Run global search."""
    print(f"Global search query: {query}")  # noqa T201

    # build global search engine
    response_placeholder = st.session_state[
        f"{SearchType.Global.value.lower()}_response_placeholder"
    ]
    response_placeholder.empty()
    with response_placeholder, st.spinner("Generating answer using global search..."):
        empty_context_data: dict[str, pd.DataFrame] = {}

        response, context_data = await api.global_search(
            config=sv.graphrag_config.value,
            entities=sv.entities.value,
            communities=sv.communities.value,
            community_reports=sv.community_reports.value,
            dynamic_community_selection=False,
            response_type="Multiple Paragraphs",
            community_level=sv.dataset_config.value.community_level,
            query=query,
        )

        print(f"Context data: {context_data}")  # noqa T201
        print(f"Global Response: {response}")  # noqa T201

    context = context_data if isinstance(context_data, dict) else empty_context_data
    search_result = SearchResult(
        search_type=SearchType.Global,
        method=SearchMethod.MICROSOFT_GLOBAL,
        response=str(response),
        context=context,
        trace=trace_from_context(
            query=query,
            method=SearchMethod.MICROSOFT_GLOBAL,
            context=context,
            retriever=_graph_retriever(sv),
        ),
    )
    return _record_result(sv, search_result)


async def run_drift_search(
    query: str,
    sv: SessionVariables,
) -> SearchResult:
    """Run drift search."""
    print(f"Drift search query: {query}")  # noqa T201

    # build drift search engine
    response_placeholder = st.session_state[
        f"{SearchType.Drift.value.lower()}_response_placeholder"
    ]
    with response_placeholder, st.spinner("Generating answer using drift search..."):
        empty_context_data: dict[str, pd.DataFrame] = {}

        response, context_data = await api.drift_search(
            config=sv.graphrag_config.value,
            entities=sv.entities.value,
            communities=sv.communities.value,
            community_reports=sv.community_reports.value,
            text_units=sv.text_units.value,
            relationships=sv.relationships.value,
            community_level=sv.dataset_config.value.community_level,
            response_type="Multiple Paragraphs",
            query=query,
        )

        print(f"Drift Response: {response}")  # noqa T201
        print(f"Context data: {context_data}")  # noqa T201

    context = context_data if isinstance(context_data, dict) else empty_context_data
    search_result = SearchResult(
        search_type=SearchType.Drift,
        method=SearchMethod.MICROSOFT_DRIFT,
        response=str(response),
        context=context,
        trace=trace_from_context(
            query=query,
            method=SearchMethod.MICROSOFT_DRIFT,
            context=context,
            retriever=_graph_retriever(sv),
        ),
    )
    return _record_result(sv, search_result)


async def run_basic_search(
    query: str,
    sv: SessionVariables,
) -> SearchResult:
    """Run basic search."""
    print(f"Basic search query: {query}")  # noqa T201

    # build local search engine
    response_placeholder = st.session_state[
        f"{SearchType.Basic.value.lower()}_response_placeholder"
    ]
    with response_placeholder, st.spinner("Generating answer using basic RAG..."):
        empty_context_data: dict[str, pd.DataFrame] = {}

        response, context_data = await api.basic_search(
            config=sv.graphrag_config.value,
            text_units=sv.text_units.value,
            query=query,
        )

        print(f"Basic Response: {response}")  # noqa T201
        print(f"Context data: {context_data}")  # noqa T201

    context = context_data if isinstance(context_data, dict) else empty_context_data
    search_result = SearchResult(
        search_type=SearchType.Basic,
        method=SearchMethod.MICROSOFT_BASIC,
        response=str(response),
        context=context,
        trace=trace_from_context(
            query=query,
            method=SearchMethod.MICROSOFT_BASIC,
            context=context,
            retriever=_graph_retriever(sv),
        ),
    )
    return _record_result(sv, search_result)


def load_knowledge_model(sv: SessionVariables):
    """Load knowledge model from the datasource."""
    print("Loading knowledge model...", sv.dataset.value, sv.dataset_config.value)  # noqa T201
    model = load_model(sv.dataset.value, sv.datasource.value)

    sv.generated_questions.value = []
    sv.selected_question.value = ""
    sv.entities.value = model.entities
    sv.relationships.value = model.relationships
    sv.covariates.value = model.covariates
    sv.community_reports.value = model.community_reports
    sv.communities.value = model.communities
    sv.text_units.value = model.text_units
    sv.documents.value = model.documents
    sv.text_vector_store.value = None
    sv.entity_vector_store.value = None
    sv.embedding_model.value = None
    sv.completion_model.value = None
    sv.completion_model_params.value = {}

    return sv
