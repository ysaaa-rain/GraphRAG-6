# Copyright (c) 2026 GraphRAG-6 project contributors.
# Licensed under the MIT License

"""Concurrent query orchestration independent of the Streamlit presentation layer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def run_parallel(
    items: Iterable[T],
    query: Callable[[T], Awaitable[R]],
) -> list[R | BaseException]:
    """Evaluate selected methods concurrently and keep per-method failures visible."""
    return await asyncio.gather(
        *(query(item) for item in items),
        return_exceptions=True,
    )
