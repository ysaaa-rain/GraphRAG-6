"""Verify the generated Enron S0 GraphRAG artifacts without calling any API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import lancedb
import pandas as pd


EXPECTED_TABLES = {
    "entity_description": 480,
    "community_full_content": 29,
    "text_unit_text": 33,
}
EXPECTED_PARQUET_ROWS = {
    "documents": 30,
    "text_units": 33,
    "entities": 480,
    "relationships": 1295,
    "communities": 29,
    "community_reports": 29,
}


def verify(root: Path, expected_dimension: int) -> dict[str, object]:
    output = root / "output"
    result: dict[str, object] = {
        "root": str(root),
        "parquet_rows": {},
        "vector_tables": {},
        "passed": True,
    }

    parquet_rows: dict[str, int] = {}
    for name, expected in EXPECTED_PARQUET_ROWS.items():
        path = output / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        rows = len(pd.read_parquet(path))
        parquet_rows[name] = rows
        if rows != expected:
            result["passed"] = False
    result["parquet_rows"] = parquet_rows

    db = lancedb.connect(str(root / "lancedb"))
    table_names = set(db.list_tables().tables or [])
    vector_tables: dict[str, dict[str, object]] = {}
    for name, expected_rows in EXPECTED_TABLES.items():
        if name not in table_names:
            result["passed"] = False
            continue
        table = db.open_table(name)
        schema = table.schema
        vector_field = schema.field("vector")
        dimension = vector_field.type.list_size
        rows = table.count_rows()
        vector_tables[name] = {
            "rows": rows,
            "dimension": dimension,
        }
        if rows != expected_rows or dimension != expected_dimension:
            result["passed"] = False
    result["vector_tables"] = vector_tables
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("experiments/outputs/enron_s0"),
        help="GraphRAG output directory",
    )
    parser.add_argument("--expected-dimension", type=int, default=1024)
    args = parser.parse_args()

    result = verify(args.root, args.expected_dimension)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
