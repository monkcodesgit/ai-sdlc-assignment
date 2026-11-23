# Prompt for `/speckit.plan`

Paste everything below the line.

---

Technical plan for the Tiered Rate Limiter.

**Stack:** Python 3.11+, FastAPI + Pydantic v2 for the HTTP layer only, uvicorn to run it. The core limiter uses only the standard library (NFR-005). Dev tools: pytest, pytest-cov, ruff, bandit (see `requirements-dev.txt`). Runtime dependencies go in `requirements.txt`.

**Layout (exact module paths, because the pre-written tests import them):**
```
src/ratelimiter/
  __init__.py
  errors.py    # RateLimiterError(Exception) and subclasses: ConfigError, UnknownTierError,
               #   InvalidRequestError, CostExceedsCapacityError
  config.py    # TierConfig (frozen dataclass: name:str, capacity:int, refill_rate:float),
               #   DEFAULT_TIERS: dict[str, TierConfig], load_tiers(raw) -> dict[str, TierConfig],
               #   load_tiers_from_json(path) -> dict[str, TierConfig]   (raise ConfigError)
  store.py     # BucketState (mutable dataclass: tokens: float, last_refill: float),
               #   InMemoryStore with get(key)->BucketState|None, put(key, state), __len__
  limiter.py   # Decision (frozen dataclass: allowed, limit, remaining, retry_after, reset),
               #   RateLimiter(tiers, clock=time.monotonic, store=None).check(client_id, tier, cost=1)
  app.py       # create_app(tiers=None, clock=None) -> FastAPI ; routes /v1/check and /health
  main.py      # app = create_app(...) for uvicorn; reads RATELIMITER_TIERS_FILE if set
```
**Core algorithm** (inside one `threading.Lock`, one lock for the whole limiter):
1. Validate client_id and cost (raise InvalidRequestError), then look up the tier (UnknownTierError), then cost > capacity (CostExceedsCapacityError).
2. key = f"{tier}:{client_id}"; now = clock(); load state or create BucketState(tokens=capacity, last_refill=now).
3. If existing: elapsed = max(0, now − last_refill); tokens = min(capacity, tokens + elapsed × refill_rate); last_refill = max(last_refill, now).
4. allowed = tokens ≥ cost. If allowed, tokens −= cost and retry_after = 0; else retry_after = max(1, ceil((cost − tokens)/refill_rate)).
5. put state; remaining = floor(tokens); reset = ceil((capacity − tokens)/refill_rate) (0 if full). Return Decision.

**HTTP layer:** Pydantic request model with `extra="forbid"`; `client_id`: StrictStr, length 1–128, pattern `^[A-Za-z0-9._:@-]+$`; `tier`: StrictStr, length 1–32; `cost`: StrictInt ≥ 1, default 1. Map UnknownTierError → 400 `{"error":"unknown_tier"}`, CostExceedsCapacityError → 400 `{"error":"cost_exceeds_capacity"}`, InvalidRequestError → 422, denied → 429 with Retry-After. A generic exception handler must return a body with no trace or paths. Never bind a server to 0.0.0.0 in code.

**Quality gates and test strategy:** tests under `tests/` already exist, were derived from the acceptance criteria, and are locked; the implementation must satisfy them without modification. The harness (`.harness/run_harness.py`) runs integrity, lint, SAST, secrets, suppressions, tests+coverage and traceability gates. Constitution principles III and V apply.
