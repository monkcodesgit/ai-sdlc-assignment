"""Bucket state and the storage adapter interface (standard library only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class BucketState:
    """Mutable token-bucket state: current ``tokens`` and the clock time of the last refill."""

    tokens: float
    last_refill: float


class Store(Protocol):
    """Storage adapter contract: any object with ``get``, ``put`` and ``__len__``."""

    def get(self, key: str) -> BucketState | None:
        """Return the state stored under ``key``, or None."""

    def put(self, key: str, state: BucketState) -> None:
        """Insert or replace the state stored under ``key``."""

    def __len__(self) -> int:
        """Return the number of stored buckets."""


class InMemoryStore:
    """Dict-backed store. Not thread-safe by itself; the limiter serialises access."""

    def __init__(self) -> None:
        self._buckets: dict[str, BucketState] = {}

    def get(self, key: str) -> BucketState | None:
        """Return the exact stored object for ``key``, or None when absent."""
        return self._buckets.get(key)

    def put(self, key: str, state: BucketState) -> None:
        """Insert or replace the state for ``key``."""
        self._buckets[key] = state

    def __len__(self) -> int:
        """Return the number of stored buckets."""
        return len(self._buckets)
