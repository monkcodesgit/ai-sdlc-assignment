"""Token-bucket rate limiter core (standard library only)."""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .config import TierConfig
from .errors import CostExceedsCapacityError, InvalidRequestError, UnknownTierError
from .store import BucketState, InMemoryStore, Store

CLIENT_ID_RE = re.compile(r"[A-Za-z0-9._:@-]{1,128}")


@dataclass(frozen=True)
class Decision:
    """Outcome of one check: allow/deny plus rate-limit metadata (all whole numbers)."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset: int


def _validate_client_id(client_id: object) -> None:
    if not isinstance(client_id, str) or CLIENT_ID_RE.fullmatch(client_id) is None:
        raise InvalidRequestError("client_id must be 1-128 characters of A-Za-z0-9._:@-")


def _validate_cost(cost: object) -> None:
    if isinstance(cost, bool) or not isinstance(cost, int) or cost < 1:
        raise InvalidRequestError("cost must be an integer >= 1")


def _refill(state: BucketState, now: float, tier: TierConfig) -> None:
    """Add tokens for elapsed time; a backwards clock adds nothing and never rewinds."""
    elapsed = max(0.0, now - state.last_refill)
    state.tokens = min(float(tier.capacity), state.tokens + elapsed * tier.refill_rate)
    state.last_refill = max(state.last_refill, now)


def _seconds_until_full(tokens: float, tier: TierConfig) -> int:
    if tokens >= tier.capacity:
        return 0
    return math.ceil((tier.capacity - tokens) / tier.refill_rate)


class RateLimiter:
    """Thread-safe token-bucket limiter keyed by (tier, client_id)."""

    def __init__(
        self,
        tiers: Mapping[str, TierConfig],
        clock: Callable[[], float] = time.monotonic,
        store: Store | None = None,
    ) -> None:
        self._tiers: dict[str, TierConfig] = dict(tiers)
        self._clock = clock
        self._store: Store = store if store is not None else InMemoryStore()
        self._lock = threading.Lock()

    def check(self, client_id: str, tier: str, cost: int = 1) -> Decision:
        """Decide whether a request of ``cost`` tokens may proceed now.

        Raises, in this order: InvalidRequestError (client_id/cost), UnknownTierError,
        CostExceedsCapacityError. A denied request consumes nothing.
        """
        with self._lock:
            _validate_client_id(client_id)
            _validate_cost(cost)
            config = self._tiers.get(tier) if isinstance(tier, str) else None
            if config is None:
                raise UnknownTierError("unknown tier")
            if cost > config.capacity:
                raise CostExceedsCapacityError("cost exceeds tier capacity")

            key = f"{tier}:{client_id}"
            now = self._clock()
            state = self._store.get(key)
            if state is None:
                state = BucketState(tokens=float(config.capacity), last_refill=now)
            else:
                _refill(state, now, config)

            allowed = state.tokens >= cost
            if allowed:
                state.tokens -= cost
                retry_after = 0
            else:
                retry_after = max(1, math.ceil((cost - state.tokens) / config.refill_rate))
            self._store.put(key, state)

            return Decision(
                allowed=allowed,
                limit=config.capacity,
                remaining=math.floor(state.tokens),
                retry_after=retry_after,
                reset=_seconds_until_full(state.tokens, config),
            )
