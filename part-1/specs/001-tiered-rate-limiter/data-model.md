# Data Model: Tiered Rate Limiter Microservice

## TierConfig (immutable)

| Field | Type | Rules |
|-------|------|-------|
| `name` | `str` | `^[a-z][a-z0-9_-]{0,31}$`; case-sensitive; unique key in the tier mapping |
| `capacity` | `int` | 1 ≤ capacity ≤ 1,000,000; `bool` rejected |
| `refill_rate` | `float` | 0 < rate ≤ 1,000,000; `int` input normalised to `float`; `bool`/`str` rejected |

- Tier mapping: `dict[str, TierConfig]`, non-empty, key == `TierConfig.name`.
- Defaults (`DEFAULT_TIERS`): `free` (5, 1.0), `pro` (20, 4.0), `enterprise` (100, 20.0).
- Raw config shape: `{"<name>": {"capacity": int, "refill_rate": number}}`, exactly those two keys.
- Sources: in-code mapping, or JSON file ≤ 64 KiB (FR-014), or `RATELIMITER_TIERS_FILE` (FR-014a).
- Errors: any violation → `ConfigError`.

## BucketState (mutable)

| Field | Type | Rules |
|-------|------|-------|
| `tokens` | `float` | 0 ≤ tokens ≤ capacity at all times |
| `last_refill` | `float` | clock seconds of the last refill; never decreases |

- Identity: key `f"{tier}:{client_id}"` (one bucket per (tier, client_id) pair, FR-002).
- Lifecycle / state transitions:

```text
(absent) --first check--> FULL (tokens = capacity, last_refill = now)
any      --check at now--> REFILLED: elapsed = max(0, now - last_refill)
                                     tokens = min(capacity, tokens + elapsed * rate)
                                     last_refill = max(last_refill, now)
REFILLED --tokens >= cost--> CONSUMED (tokens -= cost)          → allowed
REFILLED --tokens <  cost--> UNCHANGED (consumes nothing)        → denied
```

- Never evicted (known limitation).

## Store (adapter interface)

| Operation | Signature | Contract |
|-----------|-----------|----------|
| get | `get(key: str) -> BucketState \| None` | `None` when absent; returns the stored object |
| put | `put(key: str, state: BucketState) -> None` | insert or replace |
| length | `__len__() -> int` | number of stored buckets |

- `InMemoryStore`: dict-backed implementation. Any object with these three operations is accepted
  (structural typing, AC-022). The limiter's lock serialises access.

## CheckRequest

| Field | Type | Rules | Error |
|-------|------|-------|-------|
| `client_id` | `str` | 1–128 chars, `^[A-Za-z0-9._:@-]+$` (ASCII only) | `InvalidRequestError` / 422 |
| `tier` | `str` | HTTP: non-empty string; then must exist in the tier mapping | 422 (shape) / `UnknownTierError` / 400 |
| `cost` | `int` | ≥ 1, not `bool`, default 1; ≤ tier capacity | `InvalidRequestError` / 422; `CostExceedsCapacityError` / 400 |

- HTTP body must be a JSON object with no extra keys.
- Validation order: shape + client_id + cost → tier → cost vs capacity (FR-017).

## Decision (immutable)

| Field | Type | Definition |
|-------|------|-----------|
| `allowed` | `bool` | tokens ≥ cost (after refill) |
| `limit` | `int` | tier capacity |
| `remaining` | `int` | `floor(tokens after decision)` |
| `retry_after` | `int` | 0 if allowed, else `max(1, ceil((cost − tokens) / rate))` |
| `reset` | `int` | 0 if full, else `ceil((capacity − tokens) / rate)` |

## Errors

| Class | Parent | Raised when | HTTP |
|-------|--------|-------------|------|
| `RateLimiterError` | `Exception` | base class | — |
| `ConfigError` | `RateLimiterError` | invalid tier mapping or file | start-up failure |
| `InvalidRequestError` | `RateLimiterError` | bad client_id or cost | 422 |
| `UnknownTierError` | `RateLimiterError` | tier not configured | 400 `unknown_tier` |
| `CostExceedsCapacityError` | `RateLimiterError` | cost > capacity | 400 `cost_exceeds_capacity` |
