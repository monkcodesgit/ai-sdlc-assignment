# Prompt for `/speckit.specify`

Paste everything below the line. Keep the IDs EXACTLY as written: the harness traces them to tests.

---

Build a **Tiered Rate Limiter Microservice**. A client identified by a `client_id` belongs to a named **tier**. Each (tier, client) pair owns a **token bucket**. A request asks the service whether one unit of work (optionally weighted by a `cost`) may proceed right now. The service answers allowed or denied and tells the caller how many tokens remain and when to retry. State is in-memory only.

## Token-bucket rules
- A bucket has `capacity` (max tokens, integer ≥ 1) and `refill_rate` (tokens added per second, number > 0).
- A bucket is created lazily on first use and starts **full**.
- Tokens refill continuously, proportionally to elapsed time, and never exceed capacity.
- A request with cost `c` is **allowed** if tokens ≥ c, and then consumes exactly `c` tokens. Otherwise it is **denied** and consumes nothing.
- Buckets are keyed by the pair (tier, client_id): the same client in two tiers has two independent buckets; two clients in one tier are independent.
- `remaining` = floor(tokens after the decision). `retry_after` = 0 when allowed, otherwise ceil((c − tokens) / refill_rate) seconds with a minimum of 1. `reset` = ceil((capacity − tokens) / refill_rate) seconds until the bucket is full (0 if full).
- If the clock moves backwards, no tokens are added or removed and the bucket's last-refill time never moves backwards.
- Concurrent requests must never allow more than the available tokens.

## Default tiers
| tier | capacity | refill_rate (tokens/s) |
|---|---|---|
| free | 5 | 1.0 |
| pro | 20 | 4.0 |
| enterprise | 100 | 20.0 |
Tier names match `^[a-z][a-z0-9_-]{0,31}$` and are case-sensitive. Tiers are configurable (from a mapping or a JSON file of at most 64 KiB).

## Input rules
- `client_id`: 1–128 characters from `A–Z a–z 0–9 . _ : @ -`.
- `cost`: integer ≥ 1 (booleans are not integers), default 1, and at most the tier's capacity.
- Validation order: request shape and client_id/cost first, then tier lookup, then cost vs capacity.

## HTTP interface
- `POST /v1/check` with JSON body `{"client_id": str, "tier": str, "cost": int (optional, default 1)}`; extra fields are rejected.
- **200** when allowed. Body: `{"allowed": true, "limit": <capacity>, "remaining": n, "retry_after": 0, "reset": n}`. Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. No `Retry-After` header.
- **429** when denied. Body: `{"allowed": false, "error": "rate_limited", "limit": n, "remaining": n, "retry_after": n, "reset": n}`. Same three headers plus `Retry-After` (integer seconds).
- **400** `{"error": "unknown_tier"}` for an unknown tier; **400** `{"error": "cost_exceeds_capacity"}` when cost > capacity.
- **422** for any schema-invalid request (missing/invalid fields, wrong types, extra fields, malformed JSON, non-object body).
- `GET /health` → 200 `{"status": "ok"}`. Wrong method on `/v1/check` → 405.
- No response ever contains a stack trace or source-file path.

## User stories
1. As an API owner I want per-tier limits so paying tiers get higher throughput.
2. As a client developer I want standard rate-limit headers and a `Retry-After` so I can back off correctly.
3. As an operator I want tier limits configurable without code changes.

## Acceptance criteria (each must be testable as pass/fail)
- **AC-001** First request for a new free-tier client is allowed with limit 5, remaining 4, retry_after 0.
- **AC-002** A fresh free bucket allows exactly 5 immediate requests (remaining 4,3,2,1,0) and denies the 6th at the same instant.
- **AC-003** A denied free-tier decision at an empty bucket has allowed=false, limit 5, remaining 0, retry_after 1, reset 5.
- **AC-004** With the free bucket empty, after exactly 1.0 s one request is allowed and the next is denied.
- **AC-005** Fractional refill accumulates: at 0.5 s the request is denied (retry_after 1) and consumes nothing; at 1.0 s total it is allowed.
- **AC-006** After long idle time (1000 s) a bucket never holds more than capacity: 5 allowed, then denied; first remaining is 4.
- **AC-007** retry_after uses ceiling with a minimum of 1 (e.g. free, 1 token left, cost 3 → 2; pro empty, cost 1 → 1, cost 8 → 2; free at 0.25 tokens, cost 1 → 1).
- **AC-008** reset is the ceiling of seconds until full (free after 1 request → 1; after 3 → 3; pro cost 20 → 5; enterprise cost 100 → 5; free drained then 2 s refill then 1 request → remaining 1, reset 4).
- **AC-009** A request with cost 3 consumes 3 tokens; a second cost-3 request on a free bucket with 2 tokens left is denied with retry_after 1; cost 2 is then allowed with remaining 0.
- **AC-010** Cost greater than capacity is rejected (CostExceedsCapacity) with no state change.
- **AC-011** Default tiers have exactly the parameters in the table above.
- **AC-012** Tiers are independent buckets for the same client.
- **AC-013** Clients are isolated from each other.
- **AC-014** Unknown tiers (including different case, empty, or surrounding spaces) are rejected.
- **AC-015** Custom tier configuration is applied; integer refill rates are normalised to float; tiers absent from the configuration are unknown.
- **AC-016** Invalid tier configuration is rejected (non-mapping, empty, bad names, capacity/refill not positive numbers of the right type, bounds above 1,000,000, missing or extra keys, booleans).
- **AC-017** Tier configuration can be loaded from a JSON file; missing file, invalid JSON, non-object content and files over 64 KiB are rejected.
- **AC-018** A backwards clock adds and removes no tokens and does not double-credit later time.
- **AC-019** 50 concurrent requests against a frozen clock on a free bucket allow exactly 5.
- **AC-020** Invalid client ids (empty, spaces, slashes, over 128 chars, newlines, tabs, non-ASCII, non-strings) are rejected; 128-char and `a.b_c:d@e-f` ids are accepted; request validation precedes tier lookup.
- **AC-021** Invalid costs (0, negative, fractional, string, null, boolean) are rejected.
- **AC-022** Bucket storage sits behind a replaceable adapter exposing get/put/length; the limiter works with any conforming store; an in-memory store is provided.
- **AC-023** HTTP allowed response: 200, JSON body and the three rate-limit headers exactly as specified; no Retry-After.
- **AC-024** HTTP denied response: 429, exact body, and Retry-After plus the three headers.
- **AC-025** Cost defaults to 1 over HTTP and an explicit cost is honoured.
- **AC-026** Unknown tier and cost above capacity return the specified 400 bodies.
- **AC-027** All schema-invalid HTTP requests return 422.
- **AC-028** `GET /health` returns 200 `{"status": "ok"}`.
- **AC-029** The HTTP layer uses the injected clock (after Retry-After seconds a denied client is allowed again).
- **AC-030** No error response contains a stack trace or a `.py` path.
- **AC-031** Wrong HTTP method on `/v1/check` returns 405.

## Non-functional requirements
- **NFR-001** Ruff: zero violations. **NFR-002** Bandit: zero medium/high findings.
- **NFR-003** Coverage of the package ≥ 90%.
- **NFR-004** 10,000 limiter checks complete in under 2 seconds.
- **NFR-005** The core modules (errors, config, limiter, store) import only the standard library.
- **NFR-006** No secrets or secret-bearing files in the repository.
- **NFR-007** No lint/security suppression comments in `src/`.
- **NFR-008** Tests, harness and their configuration are unchanged since human approval.

## Out of scope
Persistence, distributed or multi-process coordination, authentication, per-endpoint rules, metrics, background threads, memory eviction of idle buckets (documented as a known limitation).
