"""Run the same Enron questions through GraphRAG local search and basic vector RAG."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graphrag.config.embeddings import entity_description_embedding, text_unit_text_embedding
from graphrag.config.load_config import load_config
from graphrag.data_model.data_reader import DataReader
from graphrag.query.factory import get_basic_search_engine, get_local_search_engine
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


SOURCE_PATH_RE = re.compile(r"(?:^|[\n|])Source path:\s*([^\n|]+)")


def load_questions(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"问题文件不能为空: {path}")
    for row in rows:
        if not row.get("question_id") or not row.get("question"):
            raise ValueError(f"问题缺少 question_id/question: {row}")
    return rows


def as_context_strings(context_text: str | list[str] | dict[str, str]) -> list[str]:
    if isinstance(context_text, str):
        return [context_text]
    if isinstance(context_text, list):
        return [str(item) for item in context_text if str(item).strip()]
    if isinstance(context_text, dict):
        return [str(value) for value in context_text.values() if str(value).strip()]
    return [str(context_text)]


def source_paths(contexts: list[str]) -> list[str]:
    paths: set[str] = set()
    for context in contexts:
        paths.update(match.group(1).strip() for match in SOURCE_PATH_RE.finditer(context))
    return sorted(paths)


def unique_required_paths(question: dict[str, Any]) -> list[str]:
    return sorted({item["source_path"] for item in question.get("required_evidence", [])})


def retrieval_summary(question: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    required = unique_required_paths(question)
    adjacent = sorted(set(question.get("acceptable_adjacent_evidence", [])))
    retrieved = set(paths)
    hit = sorted(retrieved.intersection(required))
    adjacent_hit = sorted(retrieved.intersection(adjacent))
    return {
        "required_evidence_email_count": len(required),
        "retrieved_required_evidence_email_count": len(hit),
        "required_evidence_recall": round(len(hit) / len(required), 4) if required else None,
        "retrieved_required_evidence_paths": hit,
        "missed_required_evidence_paths": sorted(set(required).difference(retrieved)),
        "retrieved_acceptable_adjacent_paths": adjacent_hit,
    }


async def load_engines(root: Path, community_level: int, response_type: str):
    config = load_config(root_dir=root)
    storage = create_storage(config.output_storage)
    provider = create_table_provider(config.table_provider, storage=storage)
    reader = DataReader(provider)

    async def read(name: str):
        return await getattr(reader, name)()

    communities, reports, text_units, relationships, entities = await asyncio.gather(
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
    text_unit_store = get_embedding_store(
        config=config.vector_store,
        embedding_name=text_unit_text_embedding,
    )

    graph_engine = get_local_search_engine(
        config=config,
        reports=read_indexer_reports(reports, communities, community_level),
        text_units=read_indexer_text_units(text_units),
        entities=read_indexer_entities(entities, communities, community_level),
        relationships=read_indexer_relationships(relationships),
        covariates={"claims": read_indexer_covariates(covariates) if covariates is not None else []},
        description_embedding_store=description_store,
        response_type=response_type,
        system_prompt=load_search_prompt(config.local_search.prompt),
    )
    vector_engine = get_basic_search_engine(
        config=config,
        text_units=read_indexer_text_units(text_units),
        text_unit_embeddings=text_unit_store,
        response_type=response_type,
        system_prompt=load_search_prompt(config.basic_search.prompt),
    )
    return graph_engine, vector_engine


async def run_one_engine(engine: Any, question: dict[str, Any], retrieval_mode: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await engine.search(query=question["question"])
        contexts = as_context_strings(result.context_text)
        paths = source_paths(contexts)
        return {
            "answer": str(result.response),
            "contexts": contexts,
            "retrieved_source_paths": paths,
            "retrieval_mode": retrieval_mode,
            "llm_calls": result.llm_calls,
            "prompt_tokens": result.prompt_tokens,
            "output_tokens": result.output_tokens,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "answer_status": "success" if str(result.response).strip() else "empty_output",
            "error": None,
            **retrieval_summary(question, paths),
        }
    except Exception as exc:  # noqa: BLE001 - preserve per-method failures for comparison
        return {
            "answer": "",
            "contexts": [],
            "retrieved_source_paths": [],
            "retrieval_mode": retrieval_mode,
            "llm_calls": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "answer_status": "api_error",
            "error": f"{type(exc).__name__}: {exc}",
            **retrieval_summary(question, []),
        }


async def main_async(args: argparse.Namespace) -> None:
    questions = load_questions(args.questions)
    graph_engine, vector_engine = await load_engines(args.root, args.community_level, args.response_type)
    existing: dict[str, dict[str, Any]] = {}
    if args.resume and args.output.exists():
        try:
            previous = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(previous, list):
                existing = {row["question_id"]: row for row in previous if row.get("question_id")}
        except (OSError, json.JSONDecodeError):
            existing = {}

    results: list[dict[str, Any] | None] = [existing.get(row["question_id"]) for row in questions]
    run_id = datetime.now(UTC).strftime("enron-comparison-%Y%m%dT%H%M%SZ")

    def save_checkpoint() -> None:
        completed = [row for row in results if row is not None]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(completed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    for index, question in enumerate(questions):
        if results[index] is not None:
            print(f"{index + 1}/{len(questions)} {question['question_id']} status=resume_skip", flush=True)
            continue
        graph_result = await run_one_engine(graph_engine, question, "graph_local")
        vector_result = await run_one_engine(vector_engine, question, "vector_basic")
        results[index] = {
            "question_id": question["question_id"],
            "question": question["question"],
            "question_zh": question.get("question_zh"),
            "question_type": question.get("question_type"),
            "reference_answer": question.get("reference_answer"),
            "evidence_email_count": question.get("evidence_email_count"),
            "expected_graph_help": question.get("expected_graph_help"),
            "run_id": run_id,
            "graph_local": graph_result,
            "vector_basic": vector_result,
        }
        save_checkpoint()
        print(
            f"{index + 1}/{len(questions)} {question['question_id']} "
            f"graph={graph_result['answer_status']} vector={vector_result['answer_status']} "
            f"graph_recall={graph_result['required_evidence_recall']} "
            f"vector_recall={vector_result['required_evidence_recall']}",
            flush=True,
        )

    save_checkpoint()
    print(f"结果已写入: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--community-level", type=int, default=2)
    parser.add_argument(
        "--response-type",
        default="Answer the question with concise evidence-grounded reasoning.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="不读取已有输出；默认按 question_id 断点续跑。",
    )
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.questions = args.questions.resolve()
    args.output = args.output.resolve()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
