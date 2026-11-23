---

description: "Task list for the Tiered Rate Limiter Microservice"
---

# Tasks: Tiered Rate Limiter Microservice

**Input**: Design documents from `specs/001-tiered-rate-limiter/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: No test tasks. The acceptance and NFR tests already exist in `tests/` and are locked
(Constitution Principle V). Every task below may only create or edit files under `src/` and
`requirements.txt`. No task runs the harness or iterates on failures; a human runs the harness
after implementation.

**Organization**: Tasks are grouped by user story. Each task cites the FR/AC/NFR IDs it
satisfies (Constitution Principle VII). Order follows errors → config → store → limiter → HTTP app
→ main/requirements.

## Format: `[ID] [P?] [Story] [IDs] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: User story from spec.md (US1, US2, US3)
- Paths are relative to `part-1/`

## Environment prerequisites (human, before `/speckit-implement`; not tasks)

- [x] `.venv` recreated with Python 3.11.12 (research R-001).
- [x] Locked `.harness/` copied from the assignment kit (research R-007).
- [ ] Human runs `python .harness/run_harness.py --lock` to baseline integrity hashes.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and runtime dependency manifest

- [ ] T001 [NFR-005] Create package `src/ratelimiter/__init__.py` with a module docstring and
  `__all__ = []`; it MUST NOT import `app`, `main` or any third-party package, so importing any
  core module stays stdlib-only (plan.md › Project Structure)
- [ ] T002 [P] [FR-019, FR-024] Create `requirements.txt` listing runtime dependencies only:
  `fastapi>=0.110`, `pydantic>=2`, `uvicorn>=0.29` (plan.md › Technical Context)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error types, tier model with defaults, and storage — required by every story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 [P] [FR-013, FR-014, FR-015, FR-016, FR-017, FR-022, AC-010, AC-014, AC-016, AC-020,
  AC-021] Implement `src/ratelimiter/errors.py`: `RateLimiterError(Exception)` and subclasses
  `ConfigError`, `UnknownTierError`, `InvalidRequestError`, `CostExceedsCapacityError`, each with
  a one-line docstring (data-model.md › Errors; contracts/python-api.md › ratelimiter.errors)
- [ ] T004 [P] [FR-001, FR-010, FR-011, AC-011] Implement in `src/ratelimiter/config.py` the
  frozen dataclass `TierConfig` with fields per data-model.md `TierConfig.name`,
  `TierConfig.capacity`, `TierConfig.refill_rate`, the compiled tier-name regex
  `^[a-z][a-z0-9_-]{0,31}$` as a module constant (data-model.md `TierConfig.name`), the bound
  constant `MAX_BOUND = 1_000_000`, and `DEFAULT_TIERS: dict[str, TierConfig]` = free (5, 1.0),
  pro (20, 4.0), enterprise (100, 20.0) (data-model.md › TierConfig defaults). Stdlib imports only
- [ ] T005 [P] [FR-018, AC-022] Implement `src/ratelimiter/store.py`: mutable dataclass
  `BucketState` (data-model.md `BucketState.tokens`, `BucketState.last_refill`), a `Store`
  `typing.Protocol` with `get`/`put`/`__len__`, and dict-backed `InMemoryStore` where `get`
  returns the exact stored object or `None` (data-model.md › Store; contracts/python-api.md ›
  ratelimiter.store). Stdlib imports only

**Checkpoint**: Foundation ready — `errors`, `config` (model + defaults), `store` importable

---

## Phase 3: User Story 1 — Per-tier limits (Priority: P1) 🎯 MVP

**Goal**: An in-process limiter that allows/denies per (tier, client_id) with correct remaining,
retry_after and reset values, thread-safe and clock-injected.

**Independent Test**: `pytest tests/test_core_limiter.py tests/test_robustness.py
tests/test_nfr.py` plus AC-011–AC-014 in `tests/test_tiers_config.py` pass with only Phase 1–3
code present.

- [ ] T006 [US1] [FR-006, AC-001, AC-003] Add the frozen dataclass `Decision` to
  `src/ratelimiter/limiter.py` with fields per data-model.md `Decision.allowed`, `Decision.limit`,
  `Decision.remaining`, `Decision.retry_after`, `Decision.reset`
- [ ] T007 [US1] [FR-015, FR-016, FR-017, AC-020, AC-021] Add private validators to
  `src/ratelimiter/limiter.py` that raise `InvalidRequestError`: `client_id` per data-model.md
  `CheckRequest.client_id` (must be `str`; use `re.fullmatch` with an ASCII-only class so
  `\n`, `\t` and non-ASCII are rejected) and `cost` per data-model.md `CheckRequest.cost`
  (`type(cost) is int`, so `bool` is rejected)
- [ ] T008 [US1] [FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-017,
  AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-012, AC-013,
  AC-014, AC-018, AC-019, AC-022, NFR-004, NFR-005] Implement `RateLimiter.__init__(tiers, clock=time.monotonic,
  store=None)` and `RateLimiter.check(client_id, tier, cost=1)` in `src/ratelimiter/limiter.py`
  following plan.md › Core algorithm steps 1–7 exactly: one `threading.Lock` around the whole
  check; validation order client_id/cost → tier lookup (`UnknownTierError`, exact case-sensitive
  key, data-model.md `CheckRequest.tier`) → `cost > capacity` (`CostExceedsCapacityError`, before
  any store access); key `f"{tier}:{client_id}"`; new bucket full with `last_refill = now`;
  refill with `elapsed = max(0, now - last_refill)` and `last_refill = max(last_refill, now)`
  (data-model.md › BucketState transitions); `math.floor`/`math.ceil` rounding per research R-003
  with no epsilon; default store `InMemoryStore()`; accept any store with `get`/`put`/`__len__`.
  Stdlib imports only; no `assert` statements

**Checkpoint**: MVP — core limiter complete and usable in-process

---

## Phase 4: User Story 2 — Standard rate-limit signalling over HTTP (Priority: P2)

**Goal**: HTTP service exposing `POST /v1/check` and `GET /health` per contracts/http-api.md.

**Independent Test**: `pytest tests/test_http_api.py` passes (AC-023–AC-031).

- [ ] T009 [US2] [FR-019, FR-023, AC-025, AC-027] In `src/ratelimiter/app.py` define the Pydantic
  v2 request model `CheckRequest` with `model_config = ConfigDict(extra="forbid")`:
  `client_id: StrictStr` (data-model.md `CheckRequest.client_id`), `tier: StrictStr` with
  `min_length=1, max_length=32` (data-model.md `CheckRequest.tier`; pattern deliberately
  NOT checked here so `Free` yields 400, research R-005), `cost: StrictInt` (data-model.md
  `CheckRequest.cost`, default 1, `ge=1`)
- [ ] T010 [US2] [FR-009, FR-020, FR-021, FR-024, FR-026, AC-023, AC-024, AC-025, AC-028, AC-029,
  AC-031] Implement `create_app(tiers=None, clock=None) -> FastAPI` in `src/ratelimiter/app.py`:
  defaults `DEFAULT_TIERS` and `time.monotonic`; one `RateLimiter` per app sharing that clock;
  `POST /v1/check` returns 200 or 429 `JSONResponse` with bodies and headers exactly per
  contracts/http-api.md (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
  always; `Retry-After` only on 429; `"error": "rate_limited"` only on 429); `GET /health` returns
  `{"status": "ok"}`; only POST registered on `/v1/check` so other methods get 405
- [ ] T011 [US2] [FR-022, FR-023, FR-025, AC-026, AC-027, AC-030] Register exception handlers
  inside `create_app` in `src/ratelimiter/app.py`: `UnknownTierError` → 400
  `{"error": "unknown_tier"}`; `CostExceedsCapacityError` → 400 `{"error": "cost_exceeds_capacity"}`;
  `InvalidRequestError` → 422; `RequestValidationError` → 422 `{"detail": [{"type", "loc",
  "msg"}]}` dropping `input`, `ctx`, `url` (research R-004); catch-all `Exception` → 500
  `{"error": "internal_error"}` (research R-009). Never enable debug; never include exception text
  or paths in bodies

**Checkpoint**: US1 + US2 work; service usable over HTTP with default tiers

---

## Phase 5: User Story 3 — Configurable tiers (Priority: P3)

**Goal**: Operators load tiers from a mapping, a JSON file, or `RATELIMITER_TIERS_FILE`.

**Independent Test**: `pytest tests/test_tiers_config.py` passes (AC-015–AC-017); quickstart.md
§5 start-up scenarios behave as described.

- [ ] T012 [US3] [FR-012, FR-013, AC-015, AC-016] Implement `load_tiers(raw)` in
  `src/ratelimiter/config.py` per research R-006: `raw` must be a non-empty `Mapping`; each name
  per data-model.md `TierConfig.name`; each value a `Mapping` with exactly the keys `capacity`
  and `refill_rate`; `capacity` per data-model.md `TierConfig.capacity` (`type(v) is int`);
  `refill_rate` per data-model.md `TierConfig.refill_rate` (int or float, not bool, finite,
  normalised with `float()`); return a new `dict[str, TierConfig]`; raise `ConfigError` on every
  violation
- [ ] T013 [US3] [FR-014, AC-017] Implement `load_tiers_from_json(path)` in
  `src/ratelimiter/config.py` per research R-006: reject files whose size exceeds 65,536 bytes
  (check `os.stat` and read at most 65,537 bytes), decode UTF-8, `json.loads`, require a top-level
  `dict`, delegate to `load_tiers`; convert `OSError`, `UnicodeDecodeError`, `ValueError` into
  `ConfigError` with a message that never contains file contents
- [ ] T014 [US3] [FR-009, FR-014a, FR-027] Implement `src/ratelimiter/main.py`: module-level
  `logger = logging.getLogger("ratelimiter")`; build `app = create_app(tiers=...)` where tiers come
  from `load_tiers_from_json(os.environ["RATELIMITER_TIERS_FILE"])` when that variable is set and
  non-empty, else `DEFAULT_TIERS`; let `ConfigError` propagate so start-up fails; log one INFO line
  naming the tier source (path or "defaults") and tier names only; no host/port binding in code,
  no `if __name__ == "__main__"` server start

**Checkpoint**: All user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T015 [P] [NFR-001, NFR-002, NFR-005, NFR-006, NFR-007, FR-025] Review every file in
  `src/ratelimiter/` and fix in place: type hints and docstrings on public names; no `# noqa`,
  `# nosec`, `# type: ignore` or lint-disable comments; no `eval`, `exec`, `pickle`,
  `subprocess`, `os.system`, dynamic imports, `assert`, hard-coded secrets or `0.0.0.0`; core
  modules (`errors`, `config`, `store`, `limiter`) import only the standard library
- [ ] T016 [NFR-003] Remove unreachable branches and dead code in `src/ratelimiter/` so every line
  is exercised by the existing tests (coverage target ≥ 90%; `main.py` is the only module not
  imported by tests, so keep it minimal)

---

## Traceability: AC → task

| AC | Task(s) | AC | Task(s) | AC | Task(s) |
|----|---------|----|---------|----|---------|
| AC-001 | T006, T008 | AC-012 | T008 | AC-023 | T010 |
| AC-002 | T008 | AC-013 | T008 | AC-024 | T010 |
| AC-003 | T006, T008 | AC-014 | T003, T008 | AC-025 | T009, T010 |
| AC-004 | T008 | AC-015 | T012 | AC-026 | T011 |
| AC-005 | T008 | AC-016 | T003, T012 | AC-027 | T009, T011 |
| AC-006 | T008 | AC-017 | T013 | AC-028 | T010 |
| AC-007 | T008 | AC-018 | T008 | AC-029 | T010 |
| AC-008 | T008 | AC-019 | T008 | AC-030 | T011 |
| AC-009 | T008 | AC-020 | T003, T007 | AC-031 | T010 |
| AC-010 | T003, T008 | AC-021 | T003, T007 | | |
| AC-011 | T004 | AC-022 | T005, T008 | | |

NFR-004 → T008; NFR-005 → T001, T004, T005, T008, T015; NFR-001/002/006/007 → T015;
NFR-003 → T016; NFR-008 → no task (enforced by not touching `tests/`, `.harness/` or configs).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → **US1 (Phase 3)** → **US2 (Phase 4)** →
  **US3 (Phase 5)** → **Polish (Phase 6)**
- US2 depends on US1 (`app.py` wraps `RateLimiter`). US3's `load_tiers*` (T012, T013) depend only
  on Phase 2 and could run alongside US1; T014 depends on T010 and T013.

### Task dependencies

- T003, T004, T005 depend on T001; T004 imports nothing from T003 until T012.
- T006 → T007 → T008 (same file, sequential); T008 needs T003, T004, T005.
- T009 → T010 → T011 (same file, sequential); all need T008.
- T012 → T013 (same file, sequential); both need T003, T004.
- T014 needs T010, T013. T015, T016 need all previous tasks.

### Parallel opportunities

- Phase 1: T001 ∥ T002.
- Phase 2: T003 ∥ T004 ∥ T005 (three different files).
- After Phase 2: the US1 chain (T006–T008 in `limiter.py`) ∥ the US3 loader chain (T012–T013 in
  `config.py`).

### Parallel example: Phase 2

```text
Task: "T003 Implement errors in src/ratelimiter/errors.py"
Task: "T004 Implement TierConfig + DEFAULT_TIERS in src/ratelimiter/config.py"
Task: "T005 Implement BucketState + InMemoryStore in src/ratelimiter/store.py"
```

### Parallel example: after Phase 2

```text
Task: "T006–T008 [US1] Decision, validators, RateLimiter in src/ratelimiter/limiter.py"
Task: "T012–T013 [US3] load_tiers, load_tiers_from_json in src/ratelimiter/config.py"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 → Phase 2 → Phase 3 (T001–T008).
2. Stop and validate: core limiter tests (AC-001–AC-014, AC-018–AC-022, NFR-004/005) pass.

### Incremental delivery

1. + US2 (T009–T011) → HTTP contract tests (AC-023–AC-031) pass.
2. + US3 (T012–T014) → configuration tests (AC-015–AC-017) pass; env-var start-up works.
3. Polish (T015–T016) → ready for the human-run harness (lint, SAST, secrets, suppressions,
   coverage, traceability).

### Notes

- Before implementation, snapshot nothing; after the first full generation, the human preserves
  `src/` + `specs/` in `evidence/initial-generation/` (Principle VII).
- If a locked test appears to contradict the spec, stop and escalate to a human; never edit
  `tests/` (Principle V).
