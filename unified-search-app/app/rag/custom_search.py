# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License
# ruff: noqa: RUF001

"""LLM and vector-store adapters for the custom GraphRAG policies."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from graphrag.config.embeddings import (
    entity_description_embedding,
    text_unit_text_embedding,
)
from graphrag.utils.api import get_embedding_store
from graphrag_llm.completion import create_completion
from graphrag_llm.embedding import create_embedding
from graphrag_llm.utils import CompletionMessagesBuilder

if TYPE_CHECKING:
    from rag.retrieval import GraphRetriever, RetrievalBundle
    from rag.typing import SearchMethod


CUSTOM_SYSTEM_PROMPT = """你是一个严格基于检索证据回答问题的知识图谱问答助手。
只使用下面提供的 Entities、Relationships、Sources、Community reports 和 Graph paths。
如果证据不足，明确说明证据不足，不要凭空补充。回答要直接、结构清晰，并在相关句末用
[实体: ID]、[关系: ID]、[来源: ID] 标出证据。Graph paths 是检索阶段生成的候选路径，
不能把路径本身当成事实；事实必须能回溯到 Sources 或 Community reports。

检索方法：{method}
问题：{query}

检索上下文：
{context}

请输出 {response_type}。
"""


def vector_scores(
    query: str,
    vector_store: Any | None,
    embedding_model: Any | None,
    k: int = 32,
) -> dict[str, float]:
    """Query an existing Microsoft GraphRAG vector index when available."""
    if vector_store is None or embedding_model is None:
        return {}
    try:
        results = vector_store.similarity_search_by_text(
            text=query,
            text_embedder=lambda text: (
                embedding_model.embedding(input=[text]).first_embedding
            ),
            k=k,
            include_vectors=False,
        )
    except Exception:  # noqa: BLE001 - custom mode must remain usable without a vector index
        return {}
    return {
        str(result.document.id): float(result.score)
        for result in results
        if result.document.id is not None
    }


def create_embedding_resources(
    config: Any,
) -> tuple[Any | None, Any | None, Any | None]:
    """Create text/entity vector stores and a shared embedding model lazily."""
    text_store = None
    entity_store = None
    embedding_model = None
    with suppress(Exception):
        text_store = get_embedding_store(
            config=config.vector_store,
            embedding_name=text_unit_text_embedding,
        )
    with suppress(Exception):
        entity_store = get_embedding_store(
            config=config.vector_store,
            embedding_name=entity_description_embedding,
        )
    with suppress(Exception):
        embedding_settings = config.get_embedding_model_config(
            config.basic_search.embedding_model_id
        )
        embedding_model = create_embedding(embedding_settings)
    return text_store, entity_store, embedding_model


def create_completion_resource(config: Any) -> tuple[Any, dict[str, Any]]:
    """Create the completion model used by all custom methods."""
    settings = config.get_completion_model_config(
        config.local_search.completion_model_id
    )
    return create_completion(settings), settings.call_args


async def generate_answer(
    query: str,
    method: SearchMethod,
    bundle: RetrievalBundle,
    model: Any,
    model_params: dict[str, Any] | None = None,
    response_type: str = "多个段落，并给出有证据支持的结论",
) -> tuple[str, dict[str, int]]:
    """Generate a grounded answer and return basic token/call statistics."""
    if model is None:
        error_message = "自定义 GraphRAG 方法需要可用的 completion model，请检查 settings.yaml 和 API 配置。"
        raise RuntimeError(error_message)
    tokenizer = model.tokenizer
    prompt = CUSTOM_SYSTEM_PROMPT.format(
        method=method.label,
        query=query,
        context=bundle.context_text,
        response_type=response_type,
    )
    messages = (
        CompletionMessagesBuilder()
        .add_system_message(prompt)
        .add_user_message(query)
        .build()
    )
    stream = await model.completion_async(
        messages=messages,
        stream=True,
        **(model_params or {}),
    )
    answer = ""
    async for chunk in stream:
        answer += chunk.choices[0].delta.content or ""
    return answer, {
        "llm_calls": 1,
        "prompt_tokens": len(tokenizer.encode(prompt)),
        "output_tokens": len(tokenizer.encode(answer)),
    }


def build_custom_bundle(
    query: str,
    method: SearchMethod,
    retriever: GraphRetriever,
    text_store: Any | None = None,
    entity_store: Any | None = None,
    embedding_model: Any | None = None,
) -> RetrievalBundle:
    """Retrieve candidates using dense scores when configured, then graph logic."""
    text_scores = retriever.normalize_external_scores(
        vector_scores(query, text_store, embedding_model), "text"
    )
    entity_scores = retriever.normalize_external_scores(
        vector_scores(query, entity_store, embedding_model), "entity"
    )
    return retriever.retrieve(
        query=query,
        method=method,
        vector_scores=text_scores,
        entity_vector_scores=entity_scores,
    )
