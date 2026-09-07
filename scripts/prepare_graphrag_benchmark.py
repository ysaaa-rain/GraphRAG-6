"""Prepare official GraphRAG-Bench Novel/Medical data as GraphRAG JSONL input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_source(path: Path, subset: str) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if subset == "medical":
        raw = [raw]
    return [
        {
            "id": f"graphrag-bench:{subset}:{index:04d}",
            "title": str(item["corpus_name"]),
            "text": str(item["context"]),
            "source_corpus": str(item["corpus_name"]),
        }
        for index, item in enumerate(raw)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", choices=["novel", "medical"], required=True)
    parser.add_argument(
        "--source",
        type=Path,
        help="Official corpus JSON; defaults to the cloned GraphRAG-Benchmark repository.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory; defaults to data/processed/benchmark/<subset>.",
    )
    args = parser.parse_args()

    source = args.source or Path(
        f"data/raw/benchmarks/GraphRAG-Benchmark/Datasets/Corpus/{args.subset}.json"
    )
    output_dir = args.output_dir or Path(f"data/processed/benchmark/{args.subset}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_source(source, args.subset)
    output = output_dir / "documents.jsonl"
    output.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "subset": args.subset,
        "source": str(source),
        "document_count": len(records),
        "output": str(output),
        "character_count": sum(len(record["text"]) for record in records),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
