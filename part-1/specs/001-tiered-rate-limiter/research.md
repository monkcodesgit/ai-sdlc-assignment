# Research: Tiered Rate Limiter Microservice

All Technical Context unknowns are resolved below. Format: Decision / Rationale / Alternatives.

## R-001 Python version and virtual environment

- **Decision**: Target Python 3.11+. Recreate `.venv` with Python 3.11 (or newer; 3.11, 3.12 and
  3.13 are installed under `/opt/homebrew/bin`) before implementation, then
  `pip install -r requirements.txt -r requirements-dev.txt`.
- **Rationale**: The current `.venv` is Python 3.9.6. `tests/test_nfr.py` (NFR-005) uses
  `sys.stdlib_module_names`, which exists only in 3.10+, so that locked test cannot pass on 3.9.
  3.11 also brings faster CPython for NFR-004.
- **Alternatives**: Stay on 3.9 (rejected: locked test fails, tests cannot change under Principle
  V); 3.10 (works, but 3.11 was requested in the plan input).

## R-002 Concurrency control

- **Decision**: One `threading.Lock` per `RateLimiter`, held for the whole check (validation →
  state load → refill → decide → store put).
- **Rationale**: Simplest correct option for AC-019 (50 threads, exactly 5 allowed). The critical
  section is a few arithmetic ops, so contention is negligible for NFR-004.
- **Alternatives**: Per-key locks (more complex, needs a lock map that also grows unbounded);
  lock-free CAS (not available for Python objects; unnecessary).

## R-003 Arithmetic and rounding

- **Decision**: Store tokens as `float`; `remaining = math.floor(tokens)`,
  `retry_after = max(1, math.ceil((cost − tokens) / rate))` when denied, `reset = 0` if
  `tokens >= capacity` else `math.ceil((capacity − tokens) / rate)`. No epsilon.
- **Rationale**: Matches FR-006 exactly. Test inputs (rates 0.5, 1, 4, 20; steps 0.25, 0.5, 1, 2)
  are exact binary fractions, so float results are exact. An epsilon would make e.g. a 0.25-token
  deficit at 1/s round differently near integer boundaries.
- **Alternatives**: `fractions.Fraction` (exact but ~10× slower, threatens NFR-004); `Decimal`
  (same concern); integer micro-tokens (adds conversion complexity with no test benefit).

## R-004 422 response body

- **Decision**: Custom `RequestValidationError` handler returning
  `{"detail": [{"type", "loc", "msg"}]}` — the framework's standard shape (clarification Q3) with
  `input`, `ctx` and `url` removed.
- **Rationale**: FastAPI 0.128 already omits `url`, but echoes `input`; a client sending
  `"a.py"` would see `.py` in the response, and arbitrary reflected input is a needless risk
  (Principle IV, AC-030). Dropping `input`/`ctx` keeps "which field and why" (FR-023).
- **Alternatives**: Default handler unchanged (reflects input); fixed `{"error":
  "invalid_request"}` (rejected in clarification Q3).

## R-005 Request validation split (Pydantic vs core)

- **Decision**: Validate shape and types in Pydantic (`StrictStr`, `StrictInt`, lengths, client
  id pattern, `extra="forbid"`, `tier` min length 1); the core re-validates `client_id` and `cost`
  independently (it is also used without HTTP). `InvalidRequestError` from the core maps to 422.
- **Rationale**: AC-020/AC-021 test the core directly; AC-027 tests HTTP. Empty `tier` must be
  422 over HTTP (clarification Q2) but `UnknownTierError` in the core (AC-014).
- **Alternatives**: Tier pattern in Pydantic (rejected: would turn `Free` into 422, but AC-014 /
  FR-022 require 400 `unknown_tier`).

## R-006 Tier configuration loading

- **Decision**: `load_tiers(raw)` validates a `Mapping[str, Mapping]`: non-empty; names match
  `^[a-z][a-z0-9_-]{0,31}$`; each value a mapping with exactly `capacity` and `refill_rate`;
  `capacity` is `int` (not bool) in 1..1,000,000; `refill_rate` is `int|float` (not bool),
  finite, in (0, 1,000,000]; returns `dict[str, TierConfig]` with `refill_rate` cast to `float`.
  `load_tiers_from_json(path)` checks `os.stat` size ≤ 65,536 bytes before reading, reads at most
  65,537 bytes, decodes UTF-8, `json.loads`, requires a top-level object, then calls `load_tiers`.
  All failures (incl. `OSError`, `UnicodeDecodeError`, `JSONDecodeError`) → `ConfigError` with a
  message that does not include the file contents.
- **Rationale**: Covers every case in AC-016/AC-017; bounded read prevents memory abuse.
- **Alternatives**: Pydantic for config (rejected: core must be stdlib-only, NFR-005).

## R-007 Harness availability

- **Decision**: Treat `.harness/` (ruff config `.harness/ruff.toml`, `run_harness.py`,
  `snapshot.py`) as an external, locked asset that must be added to the repository before
  `/speckit-implement`. Until then, gates are run directly:
  `ruff check src tests`, `bandit -r src -ll`, `pytest --cov=ratelimiter --cov-fail-under=90`.
- **Rationale**: The constitution and the evidence README reference `.harness/`, but it is not
  present in `part-1/` (only `evidence/` placeholders are committed). The plan must not create
  it (Principle V).
- **Alternatives**: Author a harness ourselves (rejected: harness is a validation asset).

## R-008 Default clock and start-up configuration

- **Decision**: Default clock `time.monotonic` (clarification Q4). `main.py` builds the app at
  import: if `RATELIMITER_TIERS_FILE` is set, `load_tiers_from_json` (errors propagate →
  start-up fails); else `DEFAULT_TIERS`. Logs one INFO line naming the tier source (not file
  contents) via `logging` (clarification Q5).
- **Rationale**: Matches FR-009, FR-014a, FR-027. Failing loudly prevents a misconfigured service
  silently enforcing default limits.
- **Alternatives**: Fallback to defaults on error (rejected in clarification Q1).

## R-009 Error leakage

- **Decision**: Register a catch-all `Exception` handler returning 500
  `{"error": "internal_error"}`; never set `debug=True`; 404 for unknown routes uses the
  framework's `{"detail": "Not Found"}`.
- **Rationale**: AC-030 / FR-025: no traceback or `.py` path in any response.
- **Alternatives**: Rely on Starlette defaults (plain-text 500 without trace when debug is off —
  acceptable, but an explicit JSON handler is clearer and testable).
