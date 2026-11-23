"""Tier configuration: model, defaults and validated loaders (standard library only)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

TIER_NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
MAX_BOUND = 1_000_000
MAX_CONFIG_BYTES = 64 * 1024
_TIER_KEYS = frozenset({"capacity", "refill_rate"})


@dataclass(frozen=True)
class TierConfig:
    """Limits of one tier: bucket ``capacity`` (tokens) and ``refill_rate`` (tokens/second)."""

    name: str
    capacity: int
    refill_rate: float


DEFAULT_TIERS: dict[str, TierConfig] = {
    "free": TierConfig(name="free", capacity=5, refill_rate=1.0),
    "pro": TierConfig(name="pro", capacity=20, refill_rate=4.0),
    "enterprise": TierConfig(name="enterprise", capacity=100, refill_rate=20.0),
}


def load_tiers(raw: object) -> dict[str, TierConfig]:
    """Validate a ``{name: {"capacity": int, "refill_rate": number}}`` mapping.

    Raises ConfigError on any violation; integer refill rates are normalised to float.
    """
    if not isinstance(raw, Mapping):
        raise ConfigError("tier configuration must be a mapping")
    if not raw:
        raise ConfigError("tier configuration must define at least one tier")
    return {name: _parse_tier(name, spec) for name, spec in raw.items()}


def _parse_tier(name: object, spec: object) -> TierConfig:
    if not isinstance(name, str) or TIER_NAME_RE.fullmatch(name) is None:
        raise ConfigError("tier names must match ^[a-z][a-z0-9_-]{0,31}$")
    if not isinstance(spec, Mapping):
        raise ConfigError(f"tier {name!r}: definition must be a mapping")
    if set(spec) != _TIER_KEYS:
        raise ConfigError(f"tier {name!r}: keys must be exactly 'capacity' and 'refill_rate'")
    capacity = spec["capacity"]
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise ConfigError(f"tier {name!r}: capacity must be an integer")
    if not 1 <= capacity <= MAX_BOUND:
        raise ConfigError(f"tier {name!r}: capacity must be between 1 and {MAX_BOUND}")
    rate = spec["refill_rate"]
    if isinstance(rate, bool) or not isinstance(rate, int | float):
        raise ConfigError(f"tier {name!r}: refill_rate must be a number")
    if not 0 < rate <= MAX_BOUND:
        raise ConfigError(f"tier {name!r}: refill_rate must be > 0 and <= {MAX_BOUND}")
    return TierConfig(name=name, capacity=capacity, refill_rate=float(rate))


def load_tiers_from_json(path: str | os.PathLike[str]) -> dict[str, TierConfig]:
    """Load and validate tiers from a JSON object file of at most 64 KiB.

    Raises ConfigError if the file is missing, unreadable, too large, not UTF-8 JSON, or not
    a JSON object. Error messages never include the file contents.
    """
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ConfigError("tier configuration file cannot be read") from exc
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError(f"tier configuration file exceeds {MAX_CONFIG_BYTES} bytes")
    try:
        raw = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise ConfigError("tier configuration file is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ConfigError("tier configuration file must contain a JSON object")
    return load_tiers(raw)
