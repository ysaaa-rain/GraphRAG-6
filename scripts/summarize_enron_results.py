"""Summarize source recall and engineering fields for Enron S0 pilot results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def recall(retrieved: set[str], gold: set[str]) -> float:
    return round(len(retrieved & gold) / len(gold), 4) if gold else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("experiments/enron_s0/evaluation/questions.jsonl"))
    parser.add_argument("--documents", type=Path, default=Path("experiments/outputs/enron_s0/output/documents.parquet"))
    parser.add_argument("--vector", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/vector_results.jsonl"))
    parser.add_argument("--graph", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/graphrag_local_results.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/source_recall_summary.json"))
    args = parser.parse_args()

    questions = {record["question_id"]: record for record in load_jsonl(args.questions)}
    vector_results = {record["question_id"]: record for record in load_jsonl(args.vector)}
    graph_results = {record["question_id"]: record for record in load_jsonl(args.graph)}
    documents = pd.read_parquet(args.documents)
    source_by_document_index = {
        str(int(row["human_readable_id"])): str(row["raw_data"]["source_path"])
        for _, row in documents.iterrows()
    }

    rows: list[dict[str, Any]] = []
    for question_id, question in questions.items():
        gold = set(question["evidence_source_paths"])
        vector = vector_results.get(question_id, {})
        graph = graph_results.get(question_id, {})
        vector_sources = {item["source_path"] for item in vector.get("evidence", [])}
        graph_sources = {
            source_by_document_index[source_id]
            for source_id in graph.get("source_ids", [])
            if source_id in source_by_document_index
        }
        rows.append(
            {
                "question_id": question_id,
                "category": question["category"],
                "gold_source_count": len(gold),
                "vector_status": vector.get("answer_status", "missing"),
                "graph_status": graph.get("answer_status", "missing"),
                "vector_source_recall": recall(vector_sources, gold),
                "graph_source_recall": recall(graph_sources, gold),
                "vector_exact_evidence": gold.issubset(vector_sources),
                "graph_exact_evidence": gold.issubset(graph_sources),
                "vector_latency_seconds": vector.get("latency_seconds"),
                "graph_latency_seconds": graph.get("latency_seconds"),
                "vector_sources": sorted(vector_sources),
                "graph_sources": sorted(graph_sources),
            }
        )

    status_counts = {
        "vector_success": sum(row["vector_status"] == "success" for row in rows),
        "graph_success": sum(row["graph_status"] == "success" for row in rows),
    }
    summary = {
        "dataset": "Enron S0",
        "question_count": len(rows),
        "status_counts": status_counts,
        "mean_vector_source_recall": round(sum(row["vector_source_recall"] for row in rows) / len(rows), 4),
        "mean_graph_source_recall": round(sum(row["graph_source_recall"] for row in rows) / len(rows), 4),
        "vector_exact_evidence_count": sum(row["vector_exact_evidence"] for row in rows),
        "graph_exact_evidence_count": sum(row["graph_exact_evidence"] for row in rows),
        "mean_vector_latency_seconds": round(
            sum(row["vector_latency_seconds"] or 0 for row in rows) / len(rows), 3
        ),
        "mean_graph_latency_seconds": round(
            sum(row["graph_latency_seconds"] or 0 for row in rows) / len(rows), 3
        ),
        "rows": rows,
        "limitations": [
            "source recall 只衡量证据邮件是否被召回，不代表答案正确性或忠实度",
            "graph source id 按 GraphRAG S0 documents.parquet 的 human_readable_id 映射回 source_path",
            "尚未计算 ROUGE-L、Coverage、Faithfulness、Multi-hop Success Rate 和 Path Recall",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, ensure_ascii=False, indent=2))
    print(f"结果已写入: {args.output}")


if __name__ == "__main__":
    main()
