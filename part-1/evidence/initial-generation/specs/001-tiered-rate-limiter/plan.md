# Implementation Plan: Tiered Rate Limiter Microservice

**Branch**: `001-tiered-rate-limiter` (spec directory; work happens on `main`) | **Date**: 2026-11-23 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-tiered-rate-limiter/spec.md`
(technical direction from `speckit-prompts/04-plan.md`)

## Summary

An in-memory, token-bucket rate limiter keyed by (tier, client_id), exposed as a small HTTP
service. A standard-library-only core (`errors`, `config`, `store`, `limiter`) makes every
decision under a single lock with an injected clock; a thin FastAPI layer (`app`, `main`) maps
decisions and errors onto the HTTP contract (200 / 429 / 400 / 422 / 405) and rate-limit headers.
The design is fixed by the locked tests in `tests/`, which import exact module paths and names.

## Technical Context

**Language/Version**: Python 3.11+ (tests use `sys.stdlib_module_names`, which needs ≥ 3.10; see
research R-001: the current `.venv` is 3.9.6 and must be recreated)

**Primary Dependencies**: Core: standard library only. HTTP layer: FastAPI + Pydantic v2; uvicorn
to run. Runtime deps in `requirements.txt`; dev deps in `requirements-dev.txt` (locked).

**Storage**: In-memory dict behind a `get`/`put`/`__len__` store adapter. No persistence.

**Testing**: pytest + pytest-cov (`pytest.ini`: `pythonpath = src`, `testpaths = tests`), FastAPI
`TestClient` (httpx) for HTTP tests; a `FakeClock` fixture in `tests/conftest.py`.

**Target Platform**: Any OS running CPython 3.11+; served by uvicorn on localhost by default.

**Project Type**: Web service (single project, library core + HTTP adapter).

**Performance Goals**: 10,000 limiter checks < 2 s in-process (NFR-004); O(1) work per check.

**Constraints**: Core imports stdlib only (NFR-005); one process; no background threads; no
suppression comments (NFR-007); coverage ≥ 90% (NFR-003); ruff/bandit clean (NFR-001/002).

**Scale/Scope**: Single-process; buckets grow with distinct (tier, client_id) pairs and are never
evicted (documented limitation). 3 default tiers; up to 64 KiB tier config file.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-design | Post-design |
|-----------|------|------------|-------------|
| I. Spec is source of truth | All behaviour traces to FR/AC/NFR IDs; no un-specced behaviour | PASS | PASS — every module maps to FRs (see Project Structure) |
| II. Deterministic & testable | Clock injected as `() -> float`; no sleeps/wall clock in tests | PASS | PASS — `RateLimiter(clock=…)`, `create_app(clock=…)`, default `time.monotonic` |
| III. Quality gates | ruff, bandit, coverage ≥ 90%, `test_ac_*` per AC, no suppressions | PASS | PASS — design needs no suppressions (no `assert`, no `subprocess`, no `0.0.0.0` bind) |
| IV. Security by default | Boundary validation, no secrets, no internals in errors, no eval/exec/pickle/shell/dynamic import | PASS | PASS — Pydantic + core validation; generic 500 handler; 422 body sanitised (R-004) |
| V. Immutable validation assets | No edits to `tests/`, `.harness/`, `pytest.ini`, `requirements-dev.txt`, spec artifacts during implement/repair | PASS | PASS — only `src/` and `requirements.txt` are created |
| VI. Simplicity | Stdlib core; FastAPI only in `app.py`/`main.py`; in-memory store; no threads/persistence/auth | PASS | PASS — one lock, one dict, 6 modules |
| VII. Traceability & evidence | Tasks cite IDs; initial snapshot preserved; harness output never hand-edited | PASS | PASS — enforced in `/speckit-tasks` and workflow |

No violations; Complexity Tracking is empty.

**Environment risks (not principle violations, must be resolved before `/speckit-implement`)**:
resolved 2026-11-23: `.venv` rebuilt on Python 3.11.12 (R-001); `.harness/` copied from the
assignment kit (R-007). Remaining human step: `python .harness/run_harness.py --lock`.

## Project Structure

### Documentation (this feature)

```text
specs/001-tiered-rate-limiter/
├── plan.md              # This file
├── research.md          # Phase 0 decisions
├── data-model.md        # Entities, validation, state transitions
├── quickstart.md        # Run & validation guide
├── contracts/
│   ├── http-api.md      # HTTP contract (endpoints, bodies, headers, status codes)
│   └── python-api.md    # Public Python API imported by tests
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root = `part-1/`)

```text
src/ratelimiter/
├── __init__.py   # package marker; re-exports nothing heavy (keeps core import stdlib-only)
├── errors.py     # RateLimiterError + ConfigError, UnknownTierError, InvalidRequestError,
│                 #   CostExceedsCapacityError                          (FR-013/14/15/16/17, FR-022)
├── config.py     # TierConfig, DEFAULT_TIERS, load_tiers, load_tiers_from_json
│                 #                                                     (FR-001, FR-010–FR-014)
├── store.py      # BucketState, InMemoryStore (get/put/__len__)       (FR-018)
├── limiter.py    # Decision, RateLimiter.check                         (FR-002–FR-009, FR-015–FR-017)
├── app.py        # create_app(tiers=None, clock=None) -> FastAPI      (FR-019–FR-026)
└── main.py       # app for uvicorn; RATELIMITER_TIERS_FILE; start-up log (FR-014a, FR-027)

requirements.txt  # fastapi, pydantic>=2, uvicorn (runtime)

tests/            # LOCKED — pre-written, not modified
├── conftest.py            # FakeClock, limiter, client fixtures
├── test_core_limiter.py   # AC-001–AC-010
├── test_tiers_config.py   # AC-011–AC-017
├── test_robustness.py     # AC-018–AC-022
├── test_http_api.py       # AC-023–AC-031
└── test_nfr.py            # NFR-004, NFR-005
```

**Structure Decision**: Single project with a `src/` layout. Module paths and public names are
fixed by test imports (`ratelimiter.config`, `.errors`, `.limiter`, `.store`, `.app`). The core
four modules never import `app`/`main` or any third-party package.

### Core algorithm (limiter.py — all steps under one `threading.Lock`)

1. Validate `client_id` (str, 1–128, `^[A-Za-z0-9._:@-]+$`, ASCII only) and `cost` (int, not
   bool, ≥ 1) → `InvalidRequestError`.
2. Look up `tier` in the tier mapping (exact, case-sensitive) → `UnknownTierError`.
3. `cost > capacity` → `CostExceedsCapacityError` (no state touched).
4. `key = f"{tier}:{client_id}"` (unambiguous: tier names cannot contain `:`); `now = clock()`.
5. Missing state → `BucketState(tokens=capacity, last_refill=now)`. Existing →
   `elapsed = max(0, now − last_refill)`; `tokens = min(capacity, tokens + elapsed × rate)`;
   `last_refill = max(last_refill, now)`.
6. `allowed = tokens ≥ cost`; if allowed, `tokens −= cost`, `retry_after = 0`; else
   `retry_after = max(1, ceil((cost − tokens) / rate))`.
7. `store.put(key, state)`; `remaining = floor(tokens)`;
   `reset = 0 if tokens ≥ capacity else ceil((capacity − tokens) / rate)`; return `Decision`.

Floating-point guard: `ceil` is applied to values computed from exact binary fractions in the
tests; a tiny epsilon is **not** introduced (it would change AC-007/AC-008 results). See R-003.

### HTTP layer (app.py)

- Request model: `extra="forbid"`; `client_id: StrictStr` (1–128, pattern); `tier: StrictStr`
  (1–32); `cost: StrictInt ≥ 1 = 1`. Non-object / malformed JSON → 422 by the framework.
- Exception mapping: `UnknownTierError` → 400 `unknown_tier`; `CostExceedsCapacityError` → 400
  `cost_exceeds_capacity`; `InvalidRequestError` → 422; any other exception → 500
  `{"error": "internal_error"}` (no trace, no path).
- 422 handler: keeps the standard `{"detail": [{type, loc, msg}]}` shape but drops `input`, `ctx`
  and `url` so user input and library internals are never echoed (R-004).
- Headers on 200/429: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (strings
  of ints); 429 adds `Retry-After`.
- `GET /health` → `{"status": "ok"}`. Unsupported method on `/v1/check` → framework 405.
- `create_app(tiers=None, clock=None)`: `tiers` default `DEFAULT_TIERS`; `clock` default
  `time.monotonic`. `main.py` resolves `RATELIMITER_TIERS_FILE` (explicit tiers win, FR-014a);
  invalid file raises `ConfigError` at import → uvicorn fails to start. No host binding in code.

## Complexity Tracking

No constitution violations to justify.
