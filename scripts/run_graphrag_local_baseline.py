"""Run GraphRAG Local Search on the fixed Enron S0 question set."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_PATTERN = re.compile(r"Data: Sources \(([^)]*)\)")
ENTITY_PATTERN = re.compile(r"Data: Entities \(([^)]*)\)")
RELATIONSHIP_PATTERN = re.compile(r"Data: Relationships \(([^)]*)\)")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_ids(answer: str, pattern: re.Pattern[str]) -> list[str]:
    values: list[str] = []
    for match in pattern.findall(answer):
        values.extend(item.strip() for item in match.split(",") if item.strip())
    return sorted(set(values))


def run_query(root: Path, question: str, response_type: str, timeout: int) -> tuple[str, str, int, float]:
    command = [
        sys.executable,
        "-m",
        "graphrag",
        "query",
        "--root",
        str(root),
        "--method",
        "local",
        "--response-type",
        response_type,
        question,
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
        timeout=timeout,
        check=False,
    )
    return completed.stdout, completed.stderr, completed.returncode, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("experiments/enron_s0"))
    parser.add_argument("--questions", type=Path, default=Path("experiments/enron_s0/evaluation/questions.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/graphrag_local_results.jsonl"))
    parser.add_argument("--raw-dir", type=Path, default=Path("experiments/outputs/enron_s0/evaluation/graphrag_local_raw"))
    parser.add_argument("--response-type", default="回答中列出结论、关键实体、关系和证据来源；证据不足时明确说明")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    questions = load_jsonl(args.questions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("graph-local-s0-%Y%m%dT%H%M%SZ")

    with args.output.open("w", encoding="utf-8") as output_file:
        for question in questions:
            question_id = question["question_id"]
            try:
                stdout, stderr, returncode, elapsed = run_query(
                    args.root,
                    question["question"],
                    args.response_type,
                    args.timeout,
                )
                raw_path = args.raw_dir / f"{question_id}.txt"
                raw_path.write_text(
                    f"[stdout]\n{stdout}\n[stderr]\n{stderr}",
                    encoding="utf-8",
                )
                answer = stdout.strip()
                result: dict[str, Any] = {
                    "run_id": run_id,
                    "retrieval_mode": "graph_local",
                    "dataset": "Enron S0",
                    "question_set": str(args.questions),
                    "root": str(args.root),
                    "response_type": args.response_type,
                    "question_id": question_id,
                    "question": question["question"],
                    "reference_answer": question["reference_answer"],
                    "answer": answer,
                    "answer_status": "success" if returncode == 0 and answer else "empty_output",
                    "returncode": returncode,
                    "source_ids": extract_ids(answer, SOURCE_PATTERN),
                    "entity_ids": extract_ids(answer, ENTITY_PATTERN),
                    "relationship_ids": extract_ids(answer, RELATIONSHIP_PATTERN),
                    "raw_output_path": str(raw_path),
                    "latency_seconds": round(elapsed, 3),
                    "stderr": stderr[-4000:] if stderr else None,
                    "error": None if returncode == 0 else f"graphrag query exited with {returncode}",
                }
            except subprocess.TimeoutExpired as error:
                result = {
                    "run_id": run_id,
                    "retrieval_mode": "graph_local",
                    "dataset": "Enron S0",
                    "question_set": str(args.questions),
                    "root": str(args.root),
                    "response_type": args.response_type,
                    "question_id": question_id,
                    "question": question["question"],
                    "reference_answer": question["reference_answer"],
                    "answer": "",
                    "answer_status": "timeout",
                    "returncode": None,
                    "source_ids": [],
                    "entity_ids": [],
                    "relationship_ids": [],
                    "raw_output_path": None,
                    "latency_seconds": args.timeout,
                    "stderr": str(error),
                    "error": "query timeout",
                }
            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            output_file.flush()
            print(
                f"{question_id}: status={result['answer_status']} "
                f"sources={len(result['source_ids'])} "
                f"entities={len(result['entity_ids'])} "
                f"relationships={len(result['relationship_ids'])} "
                f"latency={result['latency_seconds']}s"
            )

    print(f"结果已写入: {args.output}")
    print(f"run_id: {run_id}")


if __name__ == "__main__":
    main()
