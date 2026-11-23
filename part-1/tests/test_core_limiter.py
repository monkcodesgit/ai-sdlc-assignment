"""AC-001..AC-010: token-bucket behaviour of the core limiter (no HTTP)."""
from __future__ import annotations

import pytest

from ratelimiter.errors import CostExceedsCapacityError


def _msg(expected, observed):
    return f"expected: {expected} | observed: {observed}"


def _drain(limiter, client_id="alice", tier="free", count=5):
    return [limiter.check(client_id, tier) for _ in range(count)]


def test_ac_001_first_request_allowed_with_remaining(limiter):
    d = limiter.check("alice", "free")
    assert d.allowed is True, _msg("allowed=True", d)
    assert (d.limit, d.remaining, d.retry_after) == (5, 4, 0), _msg(
        "limit=5 remaining=4 retry_after=0", d
    )


def test_ac_002_burst_equals_capacity_then_denied(limiter):
    first_five = _drain(limiter)
    assert all(d.allowed for d in first_five), _msg("5 allowed", first_five)
    assert [d.remaining for d in first_five] == [4, 3, 2, 1, 0]
    sixth = limiter.check("alice", "free")
    assert sixth.allowed is False, _msg("6th request denied", sixth)


def test_ac_003_denied_decision_shape(limiter):
    _drain(limiter)
    d = limiter.check("alice", "free")
    observed = (d.allowed, d.limit, d.remaining, d.retry_after, d.reset)
    assert observed == (False, 5, 0, 1, 5), _msg("(False, 5, 0, 1, 5)", observed)


def test_ac_004_refill_one_token_per_second(limiter, clock):
    _drain(limiter)
    clock.advance(1.0)
    assert limiter.check("alice", "free").allowed is True
    assert limiter.check("alice", "free").allowed is False


def test_ac_005_fractional_refill_accumulates_and_denial_consumes_nothing(limiter, clock):
    _drain(limiter)
    clock.advance(0.5)
    half = limiter.check("alice", "free")
    assert half.allowed is False, _msg("denied at 0.5 tokens", half)
    assert half.retry_after == 1
    clock.advance(0.5)
    again = limiter.check("alice", "free")
    assert again.allowed is True, _msg("allowed at 1.0 token (denial consumed nothing)", again)


def test_ac_006_idle_time_never_exceeds_capacity(limiter, clock):
    _drain(limiter)
    clock.advance(1000.0)
    results = _drain(limiter, count=6)
    assert [d.allowed for d in results] == [True] * 5 + [False], _msg(
        "5 allowed then 1 denied", [d.allowed for d in results]
    )
    assert results[0].remaining == 4


def test_ac_007_retry_after_uses_ceiling_free_tier(limiter):
    assert limiter.check("alice", "free", cost=4).remaining == 1
    d = limiter.check("alice", "free", cost=3)
    assert (d.allowed, d.retry_after) == (False, 2), _msg("denied, retry_after=2", d)


def test_ac_007_retry_after_uses_ceiling_pro_tier(limiter):
    assert limiter.check("bob", "pro", cost=20).remaining == 0
    assert limiter.check("bob", "pro", cost=1).retry_after == 1
    assert limiter.check("bob", "pro", cost=8).retry_after == 2


def test_ac_007_retry_after_is_at_least_one_for_fractional_wait(limiter, clock):
    _drain(limiter)
    clock.advance(0.25)
    d = limiter.check("alice", "free")
    assert (d.allowed, d.retry_after) == (False, 1), _msg("denied, retry_after=1", d)


def test_ac_008_reset_is_seconds_until_bucket_full(limiter, clock):
    assert limiter.check("a", "free").reset == 1
    three = [limiter.check("b", "free") for _ in range(3)]
    assert three[-1].reset == 3
    assert limiter.check("c", "pro", cost=20).reset == 5
    assert limiter.check("d", "enterprise", cost=100).reset == 5
    _drain(limiter, "e")
    clock.advance(2.0)
    d = limiter.check("e", "free")
    assert (d.remaining, d.reset) == (1, 4), _msg("remaining=1 reset=4", d)


def test_ac_009_cost_consumes_that_many_tokens(limiter):
    d = limiter.check("alice", "free", cost=3)
    assert (d.allowed, d.remaining) == (True, 2)
    denied = limiter.check("alice", "free", cost=3)
    assert (denied.allowed, denied.retry_after) == (False, 1)
    assert limiter.check("alice", "free", cost=2).remaining == 0


def test_ac_010_cost_above_capacity_is_rejected_without_side_effects(limiter):
    with pytest.raises(CostExceedsCapacityError):
        limiter.check("alice", "free", cost=6)
    with pytest.raises(CostExceedsCapacityError):
        limiter.check("bob", "pro", cost=21)
    assert limiter.check("alice", "free").remaining == 4
    assert limiter.check("bob", "pro", cost=20).allowed is True
