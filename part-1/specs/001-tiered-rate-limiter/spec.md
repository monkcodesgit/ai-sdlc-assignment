# Feature Specification: Tiered Rate Limiter Microservice

**Feature Branch**: `001-tiered-rate-limiter` (spec directory; work happens on `main`)

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Build a Tiered Rate Limiter Microservice. A client identified by a
`client_id` belongs to a named tier. Each (tier, client) pair owns a token bucket. A request asks
the service whether one unit of work (optionally weighted by a `cost`) may proceed right now. The
service answers allowed or denied and tells the caller how many tokens remain and when to retry.
State is in-memory only." (full description: `speckit-prompts/02-specify.md`)

> **ID stability**: The AC-nnn and NFR-nnn IDs below are fixed by the input and are traced by the
> harness to tests named `test_ac_<nnn>_*` / `test_nfr_<nnn>_*`. They MUST NOT be renumbered.

## Clarifications

### Session 2026-11-23

- Q: When the service starts, how should it find a custom tier configuration file? → A: Optional
  environment variable `RATELIMITER_TIERS_FILE` names the JSON file; unset → default tiers; set
  but invalid → the service refuses to start.
- Q: Over HTTP, how should a missing/empty `tier` be handled versus a well-formed but unconfigured
  tier name? → A: `tier` must be a non-empty string as part of the request shape (missing, empty
  or non-string → 422); any non-empty name not configured (e.g. `gold`, `Free`, ` free `) → 400
  `unknown_tier`.
- Q: What should the body of a 422 "invalid request" response contain? → A: The framework's
  standard validation body (a `detail` list naming each invalid field and reason); it must never
  contain stack traces or source-file paths.
- Q: When the service runs for real, what clock should it use by default? → A: A monotonic clock
  (seconds, never affected by wall-clock adjustments), overridable by injecting any time source.
- Q: What should the service log while it runs? → A: Minimal: start-up info (tier source loaded)
  and configuration/internal errors only; no per-request logs; never log secrets; not part of the
  acceptance tests.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-tier limits (Priority: P1)

As an API owner, I want each client's requests limited according to its tier, so that paying
tiers get higher throughput and no client can exceed its allowance.

**Why this priority**: This is the core decision (allow/deny) the service exists to make; every
other story builds on it.

**Independent Test**: Call the limiter directly with a controllable clock and check allow/deny
decisions, remaining tokens, retry and reset values for the default tiers. Delivers a usable
in-process rate limiter even with no HTTP interface.

**Acceptance Scenarios**:

1. **Given** a new free-tier client, **When** it makes its first request, **Then** the request is
   allowed with limit 5, remaining 4, retry_after 0 (AC-001).
2. **Given** a fresh free bucket, **When** 6 requests arrive at the same instant, **Then** the
   first 5 are allowed (remaining 4, 3, 2, 1, 0) and the 6th is denied (AC-002, AC-003).
3. **Given** an empty free bucket, **When** exactly 1.0 s passes, **Then** one request is allowed
   and the next is denied (AC-004).
4. **Given** the same client in two tiers, or two clients in one tier, **When** one bucket is
   drained, **Then** the other bucket is unaffected (AC-012, AC-013).

---

### User Story 2 - Standard rate-limit signalling over HTTP (Priority: P2)

As a client developer, I want standard rate-limit headers and a `Retry-After` value, so that I can
back off correctly.

**Why this priority**: Makes the limiter usable as a network service by any client.

**Independent Test**: Send HTTP requests to the service with a controllable clock and check status
codes, bodies and headers.

**Acceptance Scenarios**:

1. **Given** a client with tokens available, **When** it posts a check, **Then** it receives 200
   with the allowed body and `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
   headers and no `Retry-After` (AC-023).
2. **Given** a client with an empty bucket, **When** it posts a check, **Then** it receives 429
   with the denied body, the three headers and `Retry-After` (AC-024).
3. **Given** a denied client, **When** it waits `Retry-After` seconds and retries, **Then** it is
   allowed (AC-029).
4. **Given** a malformed or invalid request, **When** it is posted, **Then** it receives 422 (schema
   errors) or 400 (unknown tier / cost above capacity), never a stack trace (AC-026, AC-027, AC-030).

---

### User Story 3 - Configurable tiers (Priority: P3)

As an operator, I want tier limits configurable without code changes, so that I can tune
capacity and refill rates per deployment.

**Why this priority**: Defaults cover the initial need; configurability is needed for operations.

**Independent Test**: Load a custom tier mapping or JSON file and check that its limits are
applied and invalid configurations are rejected.

**Acceptance Scenarios**:

1. **Given** a custom tier configuration, **When** the limiter is built from it, **Then** its
   parameters apply and tiers not in it are unknown (AC-015).
2. **Given** an invalid configuration or file, **When** it is loaded, **Then** it is rejected with
   a configuration error (AC-016, AC-017).
3. **Given** `RATELIMITER_TIERS_FILE` names a valid tier file, **When** the service starts,
   **Then** it enforces those tiers; if the variable is unset, it enforces the default tiers
   (FR-014a).

---

### Edge Cases

- Long idle time: tokens are capped at capacity (AC-006).
- Fractional refill: partial tokens accumulate; a denied request consumes nothing (AC-005).
- Clock moves backwards: no tokens added or removed; later time is not double-credited (AC-018).
- Concurrent requests against a frozen clock never allow more than the available tokens (AC-019).
- Cost greater than tier capacity: rejected with no state change (AC-010).
- Tier name with different case, empty, or surrounding spaces: unknown tier (AC-014).
- Client id at exactly 128 characters, or using every allowed punctuation character: accepted
  (AC-020).
- Request is both invalid (bad client id) and for an unknown tier: reported as an invalid request,
  because request validation precedes tier lookup (AC-020).
- Wrong HTTP method on the check endpoint: 405 (AC-031).
- Empty, missing or longer-than-32-character `tier` over HTTP: 422 (malformed request), whereas a non-empty unconfigured
  tier such as `Free` or `gold`: 400 `unknown_tier`. Called directly, the limiter rejects an empty
  tier as unknown (AC-014).
- `RATELIMITER_TIERS_FILE` set to a missing, oversized or invalid file: the service refuses to
  start; it never silently falls back to the default tiers (FR-014a).

## Requirements *(mandatory)*

### Functional Requirements

**Token bucket**

- **FR-001**: Each tier MUST define `capacity` (integer ≥ 1) and `refill_rate` (tokens per second,
  number > 0).
- **FR-002**: Buckets MUST be keyed by the pair (tier, client_id) and be independent of each other.
- **FR-003**: A bucket MUST be created on first use and start full.
- **FR-004**: Tokens MUST refill continuously in proportion to elapsed time and never exceed
  capacity.
- **FR-005**: A request of cost `c` MUST be allowed if tokens ≥ c, consuming exactly `c` tokens;
  otherwise it MUST be denied and consume nothing.
- **FR-006**: Every decision MUST report `limit` = capacity, `remaining` = floor(tokens after the
  decision), `retry_after` = 0 if allowed else max(1, ceil((c − tokens) / refill_rate)), and
  `reset` = ceil((capacity − tokens) / refill_rate), or 0 if full.
- **FR-007**: If the clock moves backwards, no tokens MUST be added or removed and the bucket's
  last-refill time MUST NOT move backwards.
- **FR-008**: Concurrent requests MUST never be allowed beyond the tokens available.
- **FR-009**: The current time MUST be supplied to the limiter as a replaceable time source so that
  behaviour is reproducible. When none is supplied, the default MUST be a monotonic clock in
  seconds (unaffected by wall-clock adjustments).

**Tiers and configuration**

- **FR-010**: The default tiers MUST be: free (capacity 5, refill 1.0/s), pro (20, 4.0/s),
  enterprise (100, 20.0/s).
- **FR-011**: Tier names MUST match `^[a-z][a-z0-9_-]{0,31}$` and are case-sensitive; any other
  name is an unknown tier.
- **FR-012**: Tiers MUST be configurable from a mapping of name → {capacity, refill_rate}; integer
  refill rates are normalised to floating point.
- **FR-013**: A configuration MUST be rejected if it is not a mapping, is empty, has a bad tier
  name, has missing or extra keys, has booleans or wrong-type values, has non-positive values, or
  has capacity or refill_rate above 1,000,000.
- **FR-014**: Tiers MUST be loadable from a JSON file of at most 64 KiB; a missing file, invalid
  JSON, non-object content or an oversized file MUST be rejected.
- **FR-014a**: At service start-up, if the environment variable `RATELIMITER_TIERS_FILE` is set,
  tiers MUST be loaded from the file it names (per FR-014); if it is unset, the default tiers
  (FR-010) MUST be used. If the file is set but invalid, the service MUST fail to start with a
  configuration error rather than fall back to defaults. Tiers passed explicitly when the service
  is constructed take precedence over the environment variable.

**Input validation**

- **FR-015**: `client_id` MUST be a string of 1–128 characters from `A–Z a–z 0–9 . _ : @ -`.
- **FR-016**: `cost` MUST be an integer ≥ 1 (booleans are not integers), default 1.
- **FR-017**: Validation MUST occur in this order: request shape and client_id/cost, then tier
  lookup, then cost versus tier capacity. Cost above capacity MUST be rejected without changing
  state.

**Storage**

- **FR-018**: Bucket state MUST be stored behind a replaceable store interface offering get, put
  and length operations; an in-memory store MUST be provided and is the only store in scope.

**HTTP interface**

- **FR-019**: `POST /v1/check` MUST accept a JSON object `{"client_id": str, "tier": str,
  "cost": int (optional, default 1)}` and reject extra fields. `tier` MUST be a string of 1–32
  characters at the request-shape level (no valid tier name is longer than 32, FR-011); tier-name
  pattern and existence are checked afterwards (FR-022).
- **FR-020**: An allowed check MUST return 200 with body `{"allowed": true, "limit", "remaining",
  "retry_after": 0, "reset"}` and headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset`, and no `Retry-After` header.
- **FR-021**: A denied check MUST return 429 with body `{"allowed": false, "error": "rate_limited",
  "limit", "remaining", "retry_after", "reset"}`, the same three headers, and `Retry-After`
  (integer seconds).
- **FR-022**: An unknown tier (any 1–32 character tier string that is not configured, including
  names differing only in case or whitespace) MUST return 400 `{"error": "unknown_tier"}`; cost above capacity MUST
  return 400 `{"error": "cost_exceeds_capacity"}`.
- **FR-023**: Any schema-invalid request (missing or invalid fields, wrong types, extra fields,
  malformed JSON, non-object body) MUST return 422 with the standard validation body: a `detail`
  list in which each entry identifies the invalid field (location) and a human-readable reason.
- **FR-024**: `GET /health` MUST return 200 `{"status": "ok"}`; a wrong method on `/v1/check` MUST
  return 405.
- **FR-025**: No response MUST ever contain a stack trace or source-file path.
- **FR-026**: The HTTP layer MUST use the same injected time source as the limiter.

**Logging**

- **FR-027**: The service MUST log only start-up information (which tier source was loaded) and
  configuration or internal errors. It MUST NOT log per-request decisions or any secrets. Logging
  is not covered by acceptance tests.

### Acceptance Criteria

| ID | Criterion | FRs |
|----|-----------|-----|
| **AC-001** | First request for a new free-tier client is allowed with limit 5, remaining 4, retry_after 0. | FR-003, FR-005, FR-006 |
| **AC-002** | A fresh free bucket allows exactly 5 immediate requests (remaining 4,3,2,1,0) and denies the 6th at the same instant. | FR-005, FR-006 |
| **AC-003** | A denied free-tier decision at an empty bucket has allowed=false, limit 5, remaining 0, retry_after 1, reset 5. | FR-006 |
| **AC-004** | With the free bucket empty, after exactly 1.0 s one request is allowed and the next is denied. | FR-004 |
| **AC-005** | Fractional refill accumulates: at 0.5 s the request is denied (retry_after 1) and consumes nothing; at 1.0 s total it is allowed. | FR-004, FR-005 |
| **AC-006** | After long idle time (1000 s) a bucket never holds more than capacity: 5 allowed, then denied; first remaining is 4. | FR-004 |
| **AC-007** | retry_after uses ceiling with a minimum of 1 (free, 1 token left, cost 3 → 2; pro empty, cost 1 → 1, cost 8 → 2; free at 0.25 tokens, cost 1 → 1). | FR-006 |
| **AC-008** | reset is the ceiling of seconds until full (free after 1 request → 1; after 3 → 3; pro cost 20 → 5; enterprise cost 100 → 5; free drained, 2 s refill, 1 request → remaining 1, reset 4). | FR-006 |
| **AC-009** | Cost 3 consumes 3 tokens; a second cost-3 request on a free bucket with 2 tokens left is denied with retry_after 1; cost 2 is then allowed with remaining 0. | FR-005, FR-016 |
| **AC-010** | Cost greater than capacity is rejected (CostExceedsCapacity) with no state change. | FR-017 |
| **AC-011** | Default tiers have exactly the parameters in FR-010. | FR-010 |
| **AC-012** | Tiers are independent buckets for the same client. | FR-002 |
| **AC-013** | Clients are isolated from each other. | FR-002 |
| **AC-014** | Unknown tiers (including different case, empty, or surrounding spaces) are rejected. | FR-011 |
| **AC-015** | Custom tier configuration is applied; integer refill rates are normalised to float; tiers absent from the configuration are unknown. | FR-012 |
| **AC-016** | Invalid tier configuration is rejected (non-mapping, empty, bad names, capacity/refill not positive numbers of the right type, bounds above 1,000,000, missing or extra keys, booleans). | FR-013 |
| **AC-017** | Tier configuration can be loaded from a JSON file; missing file, invalid JSON, non-object content and files over 64 KiB are rejected. | FR-014 |
| **AC-018** | A backwards clock adds and removes no tokens and does not double-credit later time. | FR-007 |
| **AC-019** | 50 concurrent requests against a frozen clock on a free bucket allow exactly 5. | FR-008 |
| **AC-020** | Invalid client ids (empty, spaces, slashes, over 128 chars, newlines, tabs, non-ASCII, non-strings) are rejected; 128-char and `a.b_c:d@e-f` ids are accepted; request validation precedes tier lookup. | FR-015, FR-017 |
| **AC-021** | Invalid costs (0, negative, fractional, string, null, boolean) are rejected. | FR-016 |
| **AC-022** | Bucket storage sits behind a replaceable adapter exposing get/put/length; the limiter works with any conforming store; an in-memory store is provided. | FR-018 |
| **AC-023** | HTTP allowed response: 200, JSON body and the three rate-limit headers exactly as specified; no Retry-After. | FR-020 |
| **AC-024** | HTTP denied response: 429, exact body, and Retry-After plus the three headers. | FR-021 |
| **AC-025** | Cost defaults to 1 over HTTP and an explicit cost is honoured. | FR-016, FR-019 |
| **AC-026** | Unknown tier and cost above capacity return the specified 400 bodies. | FR-022 |
| **AC-027** | All schema-invalid HTTP requests return 422. | FR-019, FR-023 |
| **AC-028** | `GET /health` returns 200 `{"status": "ok"}`. | FR-024 |
| **AC-029** | The HTTP layer uses the injected clock (after Retry-After seconds a denied client is allowed again). | FR-009, FR-026 |
| **AC-030** | No error response contains a stack trace or a `.py` path. | FR-025 |
| **AC-031** | Wrong HTTP method on `/v1/check` returns 405. | FR-024 |

### Non-Functional Requirements

- **NFR-001**: Ruff reports zero violations.
- **NFR-002**: Bandit reports zero medium or high findings.
- **NFR-003**: Line coverage of the package is at least 90%.
- **NFR-004**: 10,000 limiter checks complete in under 2 seconds.
- **NFR-005**: The core modules (errors, config, limiter, store) import only the standard library.
- **NFR-006**: The repository contains no secrets or secret-bearing files.
- **NFR-007**: `src/` contains no lint or security suppression comments.
- **NFR-008**: Tests, harness and their configuration are unchanged since human approval.

### Key Entities

- **Tier**: A named limit policy with `capacity` and `refill_rate`. Name follows FR-011.
- **Bucket state**: Per (tier, client_id): current token count (fractional) and last-refill time.
- **Decision**: Result of a check: allowed, limit, remaining, retry_after, reset.
- **Check request**: client_id, tier, optional cost.
- **Store**: Holds bucket states keyed by (tier, client_id); supports get, put, length.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of acceptance criteria AC-001 to AC-031 pass as automated pass/fail checks.
- **SC-002**: No client is ever allowed more units of work than its tier permits: 50 simultaneous
  requests on a 5-capacity tier yield exactly 5 allowed.
- **SC-003**: 10,000 allow/deny decisions complete in under 2 seconds on a developer laptop.
- **SC-004**: Every denied response tells the caller a wait time after which a retry succeeds
  (verified by retrying after exactly that wait).
- **SC-005**: Operators can change tier limits with a configuration file only, without code
  changes.
- **SC-006**: 0 error responses expose internal details (stack traces or source paths).
- **SC-007**: All quality gates NFR-001 to NFR-008 pass.

## Assumptions

- Out of scope: persistence, distributed or multi-process coordination, authentication,
  per-endpoint rules, metrics, background threads.
- Idle buckets are never evicted from memory; memory grows with the number of distinct
  (tier, client_id) pairs. This is a documented known limitation.
- The service runs as a single process; "concurrent" means concurrent requests within that
  process.
- Callers are trusted to report their own `client_id`; identity verification is out of scope.
- Time values are in seconds; `retry_after` and `reset` are whole seconds.

## Changelog

- 2026-11-23: Initial specification from `speckit-prompts/02-specify.md`.
- 2026-11-23: Clarification session (5 Q&A): added FR-014a (tier file via
  `RATELIMITER_TIERS_FILE`) and FR-027 (logging); clarified FR-009 (monotonic default clock),
  FR-019/FR-022 (empty tier → 422, unconfigured tier → 400), FR-023 (422 body). No AC/NFR changed.
- 2026-11-23: Analysis fix I1: FR-019/FR-022 and edge cases now bound HTTP `tier` to 1–32
  characters at request-shape level (longer → 422), matching the plan and data model. No AC/NFR
  changed; no locked test affected.
