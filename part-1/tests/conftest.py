"""Shared fixtures. FakeClock makes every time-dependent test deterministic."""
from __future__ import annotations

import pytest

from ratelimiter.config import DEFAULT_TIERS
from ratelimiter.limiter import RateLimiter


class FakeClock:
    """A manually advanced clock; callable like time.monotonic()."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def set(self, value: float) -> None:
        self.now = value


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> RateLimiter:
    return RateLimiter(DEFAULT_TIERS, clock=clock)


@pytest.fixture
def client(clock: FakeClock):
    from fastapi.testclient import TestClient

    from ratelimiter.app import create_app

    return TestClient(create_app(clock=clock))
