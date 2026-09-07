"""Validate the tracked Enron question registry against the local S0 input."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REQUIRED_FIELDS = {
    "question_id",
    "category",
    "question",
    "reference_answer",
    "evidence_source_paths",
    "gold_entities",
    "gold_relations",
    "expected_graph_help",
    "answerability",
}
EXPECTED_CATEGORIES = {
    "single_fact",
    "multi_entity",
    "multi_hop",
    "global_summary",
    "graph_limited",
    "hallucination_risk",
}


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number} 不是合法 JSON: {error}") from error
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} 顶层必须是对象")
        records.append(record)
    return records


def validate(question_path: Path, messages_path: Path) -> None:
    questions = load_jsonl(question_path)
    messages = load_jsonl(messages_path)
    source_paths = {record.get("source_path") for record in messages}

    if not questions:
        raise ValueError("问题集为空")

    question_ids = [record.get("question_id") for record in questions]
    if None in question_ids or len(set(question_ids)) != len(question_ids):
        raise ValueError("question_id 必须存在且唯一")

    for record in questions:
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"{record['question_id']} 缺少字段: {sorted(missing)}")
        if record["category"] not in EXPECTED_CATEGORIES:
            raise ValueError(f"{record['question_id']} 使用了未知类别: {record['category']}")
        if record["expected_graph_help"] not in {"high", "medium", "low"}:
            raise ValueError(f"{record['question_id']} 的 expected_graph_help 不合法")
        if record["answerability"] not in {"answerable", "insufficient_evidence"}:
            raise ValueError(f"{record['question_id']} 的 answerability 不合法")
        missing_sources = set(record["evidence_source_paths"]) - source_paths
        if missing_sources:
            raise ValueError(f"{record['question_id']} 的证据邮件不存在: {sorted(missing_sources)}")

    category_counts = Counter(record["category"] for record in questions)
    absent_categories = EXPECTED_CATEGORIES - category_counts.keys()
    if absent_categories:
        raise ValueError(f"问题集缺少类别: {sorted(absent_categories)}")

    print(f"问题集校验通过: {len(questions)} 题")
    print("类别统计:", dict(sorted(category_counts.items())))
    print(f"证据邮件覆盖: {len({path for q in questions for path in q['evidence_source_paths']})} 封")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("experiments/enron_s0/evaluation/questions.jsonl"),
    )
    parser.add_argument(
        "--messages",
        type=Path,
        default=Path("data/processed/enron/s0/messages.jsonl"),
    )
    args = parser.parse_args()
    validate(args.questions, args.messages)


if __name__ == "__main__":
    main()
