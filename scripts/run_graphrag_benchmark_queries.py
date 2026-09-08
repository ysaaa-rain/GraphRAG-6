"""Batch-query official GraphRAG-Bench questions with one loaded GraphRAG engine."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graphrag.config.load_config import load_config
from graphrag.config.embeddings import entity_description_embedding
from graphrag.data_model.data_reader import DataReader
from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.factory import get_local_search_engine
from graphrag.query.indexer_adapters import (
    read_indexer_communities,
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.utils.api import get_embedding_store, load_search_prompt
from graphrag_storage import create_storage
from graphrag_storage.tables.table_provider_factory import create_table_provider


def load_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"题目文件必须是数组: {path}")
    return raw


def make_context_list(context_text: str | list[str] | dict[str, str]) -> list[str]:
    if isinstance(context_text, str):
        return [context_text]
    if isinstance(context_text, list):
        return [str(item) for item in context_text if str(item).strip()]
    if isinstance(context_text, dict):
        return [str(value) for value in context_text.values() if str(value).strip()]
    return [str(context_text)]


async def load_engine(root: Path, community_level: int, response_type: str):
    config = load_config(root_dir=root)
    storage = create_storage(config.output_storage)
    provider = create_table_provider(config.table_provider, storage=storage)
    reader = DataReader(provider)

    async def read(name: str):
        return await getattr(reader, name)()

    communities, community_reports, text_units, relationships, entities = await asyncio.gather(
        read("communities"),
        read("community_reports"),
        read("text_units"),
        read("relationships"),
        read("entities"),
    )
    covariates = await reader.covariates() if await provider.has("covariates") else None
    description_store = get_embedding_store(
        config=config.vector_store,
        embedding_name=entity_description_embedding,
    )
    engine = get_local_search_engine(
        config=config,
        reports=read_indexer_reports(community_reports, communities, community_level),
        text_units=read_indexer_text_units(text_units),
        entities=read_indexer_entities(entities, communities, community_level),
        relationships=read_indexer_relationships(relationships),
        covariates={"claims": read_indexer_covariates(covariates) if covariates is not None else []},
        description_embedding_store=description_store,
        response_type=response_type,
        system_prompt=load_search_prompt(config.local_search.prompt),
    )
    return engine


async def main_async(args: argparse.Namespace) -> None:
    questions = load_json(args.questions)
    engine = await load_engine(args.root, args.community_level, args.response_type)
    semaphore = asyncio.Semaphore(args.concurrency)
    existing: dict[str, dict[str, Any]] = {}
    if args.resume and args.output.exists():
        try:
            previous = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(previous, list):
                existing = {
                    item["id"]: item
                    for item in previous
                    if isinstance(item, dict) and item.get("id")
                }
        except (OSError, json.JSONDecodeError):
            existing = {}
    results: list[dict[str, Any] | None] = [existing.get(item["id"]) for item in questions]
    run_id = datetime.now(UTC).strftime(f"{args.subset}-local-%Y%m%dT%H%M%SZ")

    def save_checkpoint() -> None:
        completed = [result for result in results if result is not None]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(completed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.output)

    async def run_one(index: int, question: dict[str, Any]) -> None:
        if results[index] is not None:
            print(
                f"{index + 1}/{len(questions)} {question['id']} "
                "status=resume_skip",
                flush=True,
            )
            return
        async with semaphore:
            started = time.perf_counter()
            error: str | None = None
            try:
                search_result = await engine.search(query=question["question"])
                answer = str(search_result.response)
                contexts = make_context_list(search_result.context_text)
                result = {
                    "id": question["id"],
                    "question": question["question"],
                    "question_type": question["question_type"],
                    "ground_truth": question["answer"],
                    "evidence": question.get("evidence", ""),
                    "generated_answer": answer,
                    "contexts": contexts,
                    "context": contexts,
                    "answer_status": "success" if answer.strip() else "empty_output",
                    "retrieval_mode": "graph_local",
                    "subset": args.subset,
                    "run_id": run_id,
                    "llm_calls": search_result.llm_calls,
                    "prompt_tokens": search_result.prompt_tokens,
                    "output_tokens": search_result.output_tokens,
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - preserve per-question failures
                error = f"{type(exc).__name__}: {exc}"
                result = {
                    "id": question["id"],
                    "question": question["question"],
                    "question_type": question["question_type"],
                    "ground_truth": question["answer"],
                    "evidence": question.get("evidence", ""),
                    "generated_answer": "",
                    "contexts": [],
                    "context": [],
                    "answer_status": "api_error",
                    "retrieval_mode": "graph_local",
                    "subset": args.subset,
                    "run_id": run_id,
                    "llm_calls": None,
                    "prompt_tokens": None,
                    "output_tokens": None,
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "error": error,
                }
            results[index] = result
            save_checkpoint()
            print(
                f"{index + 1}/{len(questions)} {question['id']} "
                f"status={result['answer_status']} "
                f"latency={result['latency_seconds']}s",
                flush=True,
            )

    await asyncio.gather(*(run_one(index, question) for index, question in enumerate(questions)))
    save_checkpoint()
    print(f"结果已写入: {args.output}")
    print(f"run_id: {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", choices=["novel", "medical"], required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--community-level", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="不读取已有输出；默认按题目 ID 断点续跑。",
    )
    parser.add_argument(
        "--response-type",
        default="Answer the question with concise evidence-grounded reasoning.",
    )
    args = parser.parse_args()
    # load_config may change the working directory to the experiment root;
    # resolve all user-facing paths first so checkpoints stay in the project
    # output directory rather than being nested under the experiment root.
    args.root = args.root.resolve()
    args.questions = args.questions.resolve()
    args.output = args.output.resolve()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
