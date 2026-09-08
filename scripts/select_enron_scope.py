"""Freeze an Enron experiment scope from the normalized full corpus."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_PREFIXES = [
    "maildir/dasovich-j/california_crisis/",
    "maildir/dasovich-j/california_crisis__press/",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=Path("data/processed/enron/full/messages.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/enron/california_crisis_66"),
    )
    parser.add_argument(
        "--prefix",
        dest="prefixes",
        action="append",
        default=None,
        help="Folder prefix to include; repeat for multiple folders.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def in_scope(source_path: str, prefixes: list[str]) -> bool:
    return any(source_path.startswith(prefix) for prefix in prefixes)


def iso_min(values: list[str]) -> str | None:
    return min(values) if values else None


def iso_max(values: list[str]) -> str | None:
    return max(values) if values else None


def main() -> int:
    args = parse_args()
    input_path = args.input_jsonl.resolve()
    output_dir = args.output_dir.resolve()
    prefixes = args.prefixes or DEFAULT_PREFIXES
    if not input_path.is_file():
        raise SystemExit(f"Input JSONL does not exist: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "documents.jsonl"
    manifest_path = output_dir / "scope_manifest.json"
    if not args.overwrite and (output_path.exists() or manifest_path.exists()):
        raise SystemExit(f"Scope output already exists under {output_dir}; use --overwrite to replace it.")

    records: list[dict[str, Any]] = []
    folder_counts: Counter[str] = Counter()
    thread_ids: set[str] = set()
    dates: list[str] = []
    with input_path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            source_path = record["source_path"]
            if not in_scope(source_path, prefixes):
                continue
            selected = {
                "id": record["record_id"],
                "title": record["subject"] or record["record_id"],
                "text": record["text"],
                "source_path": source_path,
                "folder": record["folder"],
                "mailbox_user": record["mailbox_user"],
                "message_id": record["message_id"],
                "date_raw": record["date_raw"],
                "date": record["date"],
                "thread_id": record["thread_id"],
                "from": record["from"],
                "to": record["to"],
                "cc": record["cc"],
                "body": record["body"],
            }
            records.append(selected)
            folder_counts[f"maildir/{record['mailbox_user']}/{record['folder']}"] += 1
            thread_ids.add(record["thread_id"])
            if record["date"]:
                dates.append(record["date"])

    records.sort(key=lambda item: (item["date"] or "", item["source_path"]))
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    manifest = {
        "schema_version": "enron-scope-v1",
        "scope_name": "california_crisis_66",
        "status": "approved_candidate_scope",
        "selection_rule": "include every normalized message whose source_path starts with one of the declared original folder prefixes",
        "input_jsonl": str(input_path),
        "output_jsonl": str(output_path),
        "source_prefixes": prefixes,
        "record_count": len(records),
        "unique_thread_id_count": len(thread_ids),
        "date_min": iso_min(dates),
        "date_max": iso_max(dates),
        "folder_counts": dict(sorted(folder_counts.items())),
        "source_paths": [record["source_path"] for record in records],
        "notes": [
            "This scope preserves the original mailbox folders and does not assign new topic labels.",
            "The 66 messages are the declared build denominator; question-level required evidence must be annotated separately.",
            "Do not add adjacent folders without updating this manifest and rerunning both baselines.",
        ],
        "created_at": datetime.now().astimezone().isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"selected_records={len(records)}")
    print(f"unique_threads={len(thread_ids)}")
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
