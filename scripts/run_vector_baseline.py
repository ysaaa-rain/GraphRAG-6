"""Run a simple vector-only RAG baseline on the fixed Enron S0 questions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pandas as pd
from openai import OpenAI


SYSTEM_PROMPT = """你是一个严谨的邮件档案问答系统。
只能依据用户提供的邮件证据回答，不得补充证据中没有的合同、金额、日期或因果关系。
如果证据不足，必须明确回答“证据不足”，并说明缺少什么信息。
回答使用中文，先给出结论，再用 [S1]、[S2] 标记对应证据。
不要把邮件中“正在考虑”“提议”“预计”改写成“已经签署”“已经实施”或“已经确定”。
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def config_hash(values: dict[str, str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def embed_queries(client: OpenAI, model: str, queries: list[str], batch_size: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(queries), batch_size):
        response = client.embeddings.create(model=model, input=queries[start : start + batch_size])
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)
    return vectors


def build_context(records: list[dict[str, Any]], top_k: int) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    context_parts: list[str] = []
    for index, record in enumerate(records[:top_k], 1):
        source = record["source_path"]
        evidence.append(
            {
                "citation": f"S{index}",
                "source_path": source,
                "text_unit_id": record["id"],
                "similarity": record["similarity"],
            }
        )
        context_parts.append(f"[S{index}] source_path={source}\n{record['text']}")
    return "\n\n".join(context_parts), evidence


def retrieve(
    query_vector: np.ndarray,
    text_units: pd.DataFrame,
    vectors: np.ndarray,
    top_k: int,
) -> list[dict[str, Any]]:
    query_norm = np.linalg.norm(query_vector)
    vector_norms = np.linalg.norm(vectors, axis=1)
    similarities = (vectors @ query_vector) / np.maximum(vector_norms * query_norm, 1e-12)
    indices = np.argsort(-similarities)[:top_k]
    results: list[dict[str, Any]] = []
    for index in indices:
        row = text_units.iloc[int(index)]
        results.append(
            {
                "id": str(row["id"]),
                "text": str(row["text"]),
                "source_path": str(row["source_path"]),
                "similarity": float(similarities[index]),
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("experiments/enron_s0/evaluation/questions.jsonl"))
    parser.add_argument("--text-units", type=Path, default=Path("experiments/outputs/enron_s0/output/text_units.parquet"))
    parser.add_argument("--documents", type=Path, default=Path("experiments/outputs/enron_s0/output/documents.parquet"))
    parser.add_argument("--vector-store", type=Path, default=Path("experiments/outputs/enron_s0/lancedb"))
    parser.add_argument("--output", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/vector_results.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--retrieval-only", action="store_true", help="只执行向量召回，不调用 DeepSeek")
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    text_units = pd.read_parquet(args.text_units)
    documents = pd.read_parquet(args.documents)
    document_sources = {
        str(row["id"]): str(row["raw_data"]["source_path"])
        for _, row in documents.iterrows()
    }
    text_units = text_units.copy()
    text_units["source_path"] = text_units["document_id"].map(document_sources)
    if text_units["source_path"].isna().any():
        raise ValueError("存在无法映射到 source_path 的 text unit")

    db = lancedb.connect(str(args.vector_store))
    stored = db.open_table("text_unit_text").to_pandas()
    stored = stored.set_index("id").loc[text_units["id"]].reset_index()
    vectors = np.asarray(stored["vector"].tolist(), dtype=np.float32)
    if vectors.shape[1] != int(os.getenv("GRAPHRAG_EMBEDDING_DIMENSION", vectors.shape[1])):
        raise ValueError(f"向量维度不符合配置: {vectors.shape}")

    embedding_endpoint = os.environ["GRAPHRAG_EMBEDDING_ENDPOINT"]
    embedding_model = os.environ["GRAPHRAG_EMBEDDING_MODEL"]
    embedding_client = OpenAI(api_key="local-embedding", base_url=embedding_endpoint)
    query_vectors = embed_queries(
        embedding_client,
        embedding_model,
        [question["question"] for question in questions],
        args.embedding_batch_size,
    )
    if len(query_vectors) != len(questions):
        raise ValueError("查询向量数量与问题数量不一致")

    completion_client: OpenAI | None = None
    completion_model = os.getenv("GRAPHRAG_COMPLETION_MODEL", "deepseek-v4-flash")
    if not args.retrieval_only:
        completion_client = OpenAI(
            api_key=os.environ["GRAPHRAG_API_KEY"],
            base_url=os.environ["GRAPHRAG_API_BASE"],
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("vector-s0-%Y%m%dT%H%M%SZ")
    metadata = {
        "run_id": run_id,
        "retrieval_mode": "vector",
        "dataset": "Enron S0",
        "question_set": str(args.questions),
        "embedding_model": embedding_model,
        "embedding_endpoint": embedding_endpoint,
        "embedding_dimension": int(vectors.shape[1]),
        "top_k": args.top_k,
        "max_tokens": args.max_tokens,
        "completion_model": None if args.retrieval_only else completion_model,
        "thinking_mode": None if args.retrieval_only else "enabled",
        "config_hash": config_hash(
            {
                "embedding_model": embedding_model,
                "embedding_endpoint": embedding_endpoint,
                "embedding_dimension": str(vectors.shape[1]),
                "top_k": str(args.top_k),
                "max_tokens": str(args.max_tokens),
                "completion_model": completion_model,
                "thinking_mode": "enabled",
            }
        ),
    }

    with args.output.open("w", encoding="utf-8") as output_file:
        for question, query_vector in zip(questions, query_vectors, strict=True):
            started = time.perf_counter()
            retrieved = retrieve(np.asarray(query_vector, dtype=np.float32), text_units, vectors, args.top_k)
            context, evidence = build_context(retrieved, args.top_k)
            result: dict[str, Any] = {
                **metadata,
                "question_id": question["question_id"],
                "question": question["question"],
                "reference_answer": question["reference_answer"],
                "evidence": evidence,
                "answer": None,
                "answer_status": "retrieval_only" if completion_client is None else "pending",
                "finish_reason": None,
                "usage": None,
                "error": None,
            }
            if completion_client is not None:
                try:
                    response = completion_client.chat.completions.create(
                        model=completion_model,
                        max_tokens=args.max_tokens,
                        extra_body={"thinking": {"type": "enabled"}},
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": f"问题：{question['question']}\n\n邮件证据：\n{context}",
                            },
                        ],
                    )
                    result["answer"] = response.choices[0].message.content
                    result["finish_reason"] = response.choices[0].finish_reason
                    if not result["answer"]:
                        result["answer_status"] = "empty_output"
                    elif result["finish_reason"] == "length":
                        result["answer_status"] = "truncated"
                    else:
                        result["answer_status"] = "success"
                    if response.usage is not None:
                        result["usage"] = response.usage.model_dump()
                except Exception as error:  # noqa: BLE001 - preserve per-question failure records
                    result["error"] = f"{type(error).__name__}: {error}"
                    result["answer_status"] = "api_error"
            result["latency_seconds"] = round(time.perf_counter() - started, 3)
            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            output_file.flush()
            print(
                f"{question['question_id']}: retrieved={len(evidence)} "
                f"answer={'yes' if result['answer'] else 'no'} "
                f"error={'yes' if result['error'] else 'no'}"
            )

    print(f"结果已写入: {args.output}")
    print(f"run_id: {run_id}")


if __name__ == "__main__":
    main()
