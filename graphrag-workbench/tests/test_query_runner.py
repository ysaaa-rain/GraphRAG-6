# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Tests for the multi-method query entrypoint without network or Streamlit."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from query_runner import run_parallel  # noqa: E402


class QueryRunnerTests(unittest.TestCase):
    def test_results_follow_selection_order_and_preserve_errors(self) -> None:
        async def evaluate(method: int) -> str:
            await asyncio.sleep(0)
            if method == 2:
                raise ValueError("method unavailable")
            return f"result-{method}"

        results = asyncio.run(run_parallel([1, 2, 3], evaluate))
        self.assertEqual(results[0], "result-1")
        self.assertIsInstance(results[1], ValueError)
        self.assertEqual(results[2], "result-3")

    def test_no_selected_methods(self) -> None:
        async def evaluate(method: str) -> str:
            return method

        self.assertEqual(asyncio.run(run_parallel([], evaluate)), [])


if __name__ == "__main__":
    unittest.main()
