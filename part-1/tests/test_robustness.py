"""AC-018..AC-022: clock behaviour, concurrency, input validation, store adapter."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ratelimiter.config import DEFAULT_TIERS
from ratelimiter.errors import InvalidRequestError
from ratelimiter.limiter import RateLimiter
from ratelimiter.store import BucketState, InMemoryStore


def test_ac_018_backwards_clock_neither_refills_nor_double_credits(limiter, clock):
    for _ in range(5):
        limiter.check("alice", "free")
    clock.set(900.0)
    assert limiter.check("alice", "free").allowed is False
    clock.set(1001.0)
    d = limiter.check("alice", "free")
    assert (d.allowed, d.remaining) == (True, 0), f"expected: allowed, remaining=0 | observed: {d}"


def test_ac_019_concurrent_requests_never_exceed_capacity(limiter):
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: limiter.check("alice", "free"), range(50)))
    allowed = sum(1 for d in results if d.allowed)
    assert allowed == 5, f"expected: exactly 5 allowed | observed: {allowed} allowed of 50"
    assert all(d.remaining >= 0 for d in results)


INVALID_CLIENT_IDS = ["", "a b", "a/b", "x" * 129, "line\nbreak", "tab\t", "ünï", None, 123]


@pytest.mark.parametrize("client_id", INVALID_CLIENT_IDS)
def test_ac_020_invalid_client_id_is_rejected(limiter, client_id):
    with pytest.raises(InvalidRequestError):
        limiter.check(client_id, "free")


def test_ac_020_valid_client_id_boundaries_are_accepted(limiter):
    assert limiter.check("x" * 128, "free").allowed is True
    assert limiter.check("a.b_c:d@e-f", "free").allowed is True


def test_ac_020_request_validation_happens_before_tier_lookup(limiter):
    with pytest.raises(InvalidRequestError):
        limiter.check("", "no-such-tier")


@pytest.mark.parametrize("cost", [0, -1, 1.5, "2", None, True])
def test_ac_021_invalid_cost_is_rejected(limiter, cost):
    with pytest.raises(InvalidRequestError):
        limiter.check("alice", "free", cost=cost)


class RecordingStore:
    """A custom storage adapter that proves the limiter depends only on get/put/len."""

    def __init__(self):
        self.data = {}
        self.puts = 0

    def get(self, key):
        return self.data.get(key)

    def put(self, key, state):
        self.puts += 1
        self.data[key] = state

    def __len__(self):
        return len(self.data)


def test_ac_022_limiter_uses_the_injected_store_adapter(clock):
    store = RecordingStore()
    limiter = RateLimiter(DEFAULT_TIERS, clock=clock, store=store)
    limiter.check("alice", "free")
    assert store.puts >= 1 and len(store) == 1
    state = next(iter(store.data.values()))
    assert state.tokens == pytest.approx(4.0)
    assert state.last_refill == clock.now
    limiter.check("alice", "pro")
    assert len(store) == 2


def test_ac_022_in_memory_store_contract():
    store = InMemoryStore()
    assert store.get("missing") is None
    assert len(store) == 0
    state = BucketState(tokens=1.5, last_refill=2.0)
    store.put("k", state)
    assert store.get("k") is state
    assert len(store) == 1
