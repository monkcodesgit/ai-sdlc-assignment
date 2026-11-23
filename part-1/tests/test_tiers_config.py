"""AC-011..AC-017: tiers, isolation and configuration."""
from __future__ import annotations

import json

import pytest

from ratelimiter.config import DEFAULT_TIERS, TierConfig, load_tiers, load_tiers_from_json
from ratelimiter.errors import ConfigError, UnknownTierError
from ratelimiter.limiter import RateLimiter

EXPECTED_DEFAULTS = {"free": (5, 1.0), "pro": (20, 4.0), "enterprise": (100, 20.0)}


def test_ac_011_default_tiers_match_specification():
    assert set(DEFAULT_TIERS) == set(EXPECTED_DEFAULTS)
    for name, (capacity, rate) in EXPECTED_DEFAULTS.items():
        tier = DEFAULT_TIERS[name]
        assert isinstance(tier, TierConfig)
        observed = (tier.name, tier.capacity, tier.refill_rate)
        expected = (name, capacity, rate)
        assert observed == expected, f"expected: {expected} | observed: {observed}"


def test_ac_012_tiers_are_independent_buckets_for_the_same_client(limiter):
    for _ in range(5):
        limiter.check("alice", "free")
    assert limiter.check("alice", "free").allowed is False
    pro = limiter.check("alice", "pro")
    assert (pro.allowed, pro.remaining) == (True, 19)


def test_ac_013_clients_are_isolated(limiter):
    for _ in range(5):
        limiter.check("alice", "free")
    assert limiter.check("alice", "free").allowed is False
    bob = limiter.check("bob", "free")
    assert (bob.allowed, bob.remaining) == (True, 4)


@pytest.mark.parametrize("tier", ["gold", "FREE", "Free", "", " free", "free "])
def test_ac_014_unknown_tier_is_rejected(limiter, tier):
    with pytest.raises(UnknownTierError):
        limiter.check("alice", tier)


def test_ac_015_custom_tiers_are_applied(clock):
    tiers = load_tiers({"basic": {"capacity": 3, "refill_rate": 0.5}})
    limiter = RateLimiter(tiers, clock=clock)
    assert [limiter.check("a", "basic").allowed for _ in range(3)] == [True, True, True]
    denied = limiter.check("a", "basic")
    assert (denied.allowed, denied.limit, denied.retry_after) == (False, 3, 2)
    clock.advance(2.0)
    assert limiter.check("a", "basic").allowed is True
    with pytest.raises(UnknownTierError):
        limiter.check("a", "free")


def test_ac_015_integer_refill_rate_is_normalised_to_float():
    tier = load_tiers({"t": {"capacity": 1, "refill_rate": 2}})["t"]
    assert tier.refill_rate == 2.0
    assert isinstance(tier.refill_rate, float)


VALID = {"capacity": 1, "refill_rate": 1}
INVALID_CONFIGS = [
    None,
    "not a mapping",
    [],
    {},
    {"Bad Name": VALID},
    {"1abc": VALID},
    {"a" * 33: VALID},
    {"free": [1, 1]},
    {"free": {"capacity": 0, "refill_rate": 1}},
    {"free": {"capacity": -1, "refill_rate": 1}},
    {"free": {"capacity": 1.5, "refill_rate": 1}},
    {"free": {"capacity": True, "refill_rate": 1}},
    {"free": {"capacity": "5", "refill_rate": 1}},
    {"free": {"capacity": 1_000_001, "refill_rate": 1}},
    {"free": {"capacity": 1, "refill_rate": 0}},
    {"free": {"capacity": 1, "refill_rate": -1.0}},
    {"free": {"capacity": 1, "refill_rate": "1"}},
    {"free": {"capacity": 1, "refill_rate": True}},
    {"free": {"capacity": 1, "refill_rate": 1_000_001}},
    {"free": {"capacity": 1}},
    {"free": {"refill_rate": 1}},
    {"free": {"capacity": 1, "refill_rate": 1, "burst": 9}},
]


@pytest.mark.parametrize("raw", INVALID_CONFIGS)
def test_ac_016_invalid_tier_configuration_is_rejected(raw):
    with pytest.raises(ConfigError):
        load_tiers(raw)


def test_ac_017_load_tiers_from_json_file(tmp_path):
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps({"gold": {"capacity": 7, "refill_rate": 2}}), encoding="utf-8")
    tiers = load_tiers_from_json(path)
    assert (tiers["gold"].capacity, tiers["gold"].refill_rate) == (7, 2.0)


def test_ac_017_bad_json_files_are_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_tiers_from_json(tmp_path / "does-not-exist.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_tiers_from_json(broken)
    top_level_list = tmp_path / "list.json"
    top_level_list.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_tiers_from_json(top_level_list)
    oversized = tmp_path / "big.json"
    oversized.write_text(" " * 70_000 + "{}", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_tiers_from_json(oversized)
