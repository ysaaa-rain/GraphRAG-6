"""使用 GraphRAG-Bench 官方指标评测已生成的 GraphRAG 结果。

说明：
1. 指标实现直接从固定的官方 benchmark commit 导入，避免重新实现评分逻辑。
2. 生成模型使用项目统一的 DeepSeek API；语义相似度使用项目统一的本地 Qwen3-Embedding-0.6B。
3. 输出按题目 ID 断点保存，支持完整数据集长时间运行和中断后续跑。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import SecretStr


QUESTION_METRICS: dict[str, list[str]] = {
    "Fact Retrieval": ["rouge_l", "answer_correctness"],
    "Complex Reasoning": ["rouge_l", "answer_correctness"],
    "Contextual Summarize": ["answer_correctness", "coverage"],
    "Creative Generation": ["answer_correctness", "coverage", "faithfulness"],
}


class LocalQwenEmbeddings(Embeddings):
    """LangChain 适配器：调用本地 OpenAI-compatible Qwen embedding 服务。"""

    def __init__(self, endpoint: str, model: str) -> None:
        self.client = OpenAI(api_key="local-embedding", base_url=endpoint)
        self.model = model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


def load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"输入文件必须是 JSON 数组: {path}")
    return data


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def api_base_url() -> str:
    base = os.environ.get("GRAPHRAG_API_BASE", "https://api.deepseek.com").rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def build_llm() -> ChatOpenAI:
    api_key = os.environ.get("GRAPHRAG_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 GRAPHRAG_API_KEY；请在 .env 中配置后再运行。")
    return ChatOpenAI(
        model=os.environ.get("GRAPHRAG_COMPLETION_MODEL", "deepseek-v4-flash"),
        base_url=api_base_url(),
        api_key=SecretStr(api_key),
        temperature=0.0,
        max_tokens=4000,
        max_retries=3,
        timeout=120,
        extra_body={"thinking": {"type": "disabled"}},
    )


def build_embeddings() -> LocalQwenEmbeddings:
    endpoint = os.environ.get("GRAPHRAG_EMBEDDING_ENDPOINT", "http://127.0.0.1:8000/v1")
    model = os.environ.get("GRAPHRAG_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    return LocalQwenEmbeddings(endpoint=endpoint, model=model)


def metric_configuration(kind: str, question_type: str) -> list[str]:
    if kind == "generation":
        return QUESTION_METRICS.get(question_type, [])
    if kind == "retrieval":
        return ["context_relevancy", "evidence_recall"]
    raise ValueError(f"未知评测类型: {kind}")


async def calculate_metrics(
    item: dict[str, Any],
    kind: str,
    llm: ChatOpenAI,
    embeddings: LocalQwenEmbeddings,
) -> dict[str, float]:
    # 只有这里导入官方仓库，避免把 benchmark 代码复制进主项目。
    from Evaluation.metrics import (
        compute_answer_correctness,
        compute_context_relevance,
        compute_coverage_score,
        compute_evidence_recall,
        compute_faithfulness_score,
        compute_rouge_score,
    )

    question = str(item.get("question", ""))
    answer = str(item.get("generated_answer", ""))
    ground_truth = str(item.get("ground_truth", ""))
    contexts = item.get("contexts", item.get("context", []))
    if isinstance(contexts, str):
        contexts = [contexts]
    if not isinstance(contexts, list):
        contexts = [str(contexts)]
    contexts = [str(value) for value in contexts]
    evidence = item.get("evidence", "")
    question_type = str(item.get("question_type", ""))
    metric_names = metric_configuration(kind, question_type)
    result: dict[str, float] = {}

    if "rouge_l" in metric_names:
        result["rouge_l"] = float(await compute_rouge_score(answer, ground_truth))
    if "answer_correctness" in metric_names:
        result["answer_correctness"] = float(
            await compute_answer_correctness(question, answer, ground_truth, llm, embeddings)
        )
    if "coverage" in metric_names:
        result["coverage"] = float(
            await compute_coverage_score(question, ground_truth, answer, llm)
        )
    if "faithfulness" in metric_names:
        result["faithfulness"] = float(
            await compute_faithfulness_score(question, answer, contexts, llm)
        )
    if "context_relevancy" in metric_names:
        result["context_relevancy"] = float(
            await compute_context_relevance(question, contexts, llm)
        )
    if "evidence_recall" in metric_names:
        result["evidence_recall"] = float(
            await compute_evidence_recall(question, contexts, evidence, llm)
        )
    return result


def finite_mean(values: list[float]) -> float | None:
    valid = [value for value in values if math.isfinite(value)]
    return round(statistics.fmean(valid), 6) if valid else None


def summarize(records: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_type.setdefault(str(record.get("question_type", "")), []).append(record)

    def one_group(group: list[dict[str, Any]]) -> dict[str, Any]:
        metric_names = sorted({name for row in group for name in row.get("metrics", {})})
        summary: dict[str, Any] = {
            "question_count": len(group),
            "completed_count": sum(row.get("status") == "success" for row in group),
            "failed_count": sum(row.get("status") == "error" for row in group),
            "nonempty_answer_rate": round(
                sum(bool(row.get("generated_answer", "").strip()) for row in group) / len(group),
                6,
            )
            if group
            else 0.0,
        }
        for metric in metric_names:
            summary[metric] = finite_mean(
                [float(row["metrics"][metric]) for row in group if metric in row.get("metrics", {})]
            )
        return summary

    return {
        "kind": kind,
        "question_types": {question_type: one_group(group) for question_type, group in sorted(by_type.items())},
        "all": one_group(records),
    }


async def run(args: argparse.Namespace) -> None:
    items = load_json_list(args.input)
    previous: dict[str, dict[str, Any]] = {}
    if args.resume and args.output.exists():
        try:
            data = load_json_list(args.output)
            previous = {
                str(row["id"]): row
                for row in data
                if row.get("id") and row.get("status") == "success"
            }
        except (OSError, json.JSONDecodeError, ValueError):
            previous = {}

    llm = build_llm()
    embeddings = build_embeddings()
    semaphore = asyncio.Semaphore(args.concurrency)
    records: dict[str, dict[str, Any]] = dict(previous)
    pending = [item for item in items if str(item.get("id")) not in previous]
    print(f"评测类型: {args.kind}; 总题数: {len(items)}; 待评测: {len(pending)}", flush=True)

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        base = {
            "id": item.get("id"),
            "question": item.get("question", ""),
            "question_type": item.get("question_type", ""),
            "generated_answer": item.get("generated_answer", ""),
            "status": "success",
            "metrics": {},
            "latency_seconds": 0.0,
            "error": None,
        }
        try:
            async with semaphore:
                base["metrics"] = await calculate_metrics(item, args.kind, llm, embeddings)
        except Exception as exc:  # noqa: BLE001 - 每题保留错误并继续全量任务
            base["status"] = "error"
            base["error"] = f"{type(exc).__name__}: {exc}"
        base["latency_seconds"] = round(time.perf_counter() - started, 3)
        return base

    completed = 0
    for future in asyncio.as_completed([one(item) for item in pending]):
        record = await future
        records[str(record["id"])] = record
        completed += 1
        ordered = [records.get(str(item.get("id"))) for item in items]
        save_json(args.output, [row for row in ordered if row is not None])
        if completed % args.progress_every == 0 or completed == len(pending):
            print(
                f"{completed}/{len(pending)} 完成; 当前输出: {args.output}",
                flush=True,
            )

    ordered_records = [records[str(item.get("id"))] for item in items if str(item.get("id")) in records]
    save_json(args.output, ordered_records)
    summary = summarize(ordered_records, args.kind)
    save_json(args.summary, summary)
    print(f"明细已写入: {args.output}")
    print(f"汇总已写入: {args.summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["generation", "retrieval"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
