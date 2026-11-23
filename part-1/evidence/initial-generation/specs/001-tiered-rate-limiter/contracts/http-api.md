# HTTP API Contract

Base: service root. All bodies are `application/json`. Headers values are decimal integer strings.

## POST /v1/check

Request body (JSON object, no extra keys):

```json
{"client_id": "alice", "tier": "free", "cost": 1}
```

| Field | Type | Required | Constraint |
|-------|------|----------|-----------|
| `client_id` | string | yes | 1–128 chars of `A–Z a–z 0–9 . _ : @ -` |
| `tier` | string | yes | non-empty; must be a configured tier |
| `cost` | integer | no (default 1) | ≥ 1, not boolean, ≤ tier capacity |

### Responses

| Status | When | Body | Headers |
|--------|------|------|---------|
| 200 | allowed | `{"allowed": true, "limit": L, "remaining": R, "retry_after": 0, "reset": S}` | `X-RateLimit-Limit: L`, `X-RateLimit-Remaining: R`, `X-RateLimit-Reset: S`; **no** `Retry-After` |
| 429 | denied | `{"allowed": false, "error": "rate_limited", "limit": L, "remaining": R, "retry_after": T, "reset": S}` | the three `X-RateLimit-*` headers + `Retry-After: T` |
| 400 | tier not configured | `{"error": "unknown_tier"}` | — |
| 400 | cost > capacity | `{"error": "cost_exceeds_capacity"}` | — |
| 422 | schema-invalid (missing/invalid field, wrong type, extra field, malformed JSON, non-object body) | `{"detail": [{"type": str, "loc": [..], "msg": str}, ...]}` (no `input`, `ctx`, `url`) | — |
| 405 | method other than POST | framework default | `Allow: POST` |
| 500 | unexpected error | `{"error": "internal_error"}` | — |

Examples (default tiers, fresh state):

- `POST {"client_id":"alice","tier":"free"}` → 200, `remaining 4`, `reset 1`.
- 6th immediate request → 429, `remaining 0`, `retry_after 1`, `reset 5`, `Retry-After: 1`.
- `{"client_id":"alice","tier":"gold"}` → 400 `unknown_tier`.
- `{"client_id":"alice","tier":"free","cost":6}` → 400 `cost_exceeds_capacity`.
- `{"client_id":"alice","tier":""}` → 422.

## GET /health

200 `{"status": "ok"}`.

## Guarantees

- No response contains a stack trace or a source-file path (`.py`).
- Rate-limit timing uses the service's injected clock (monotonic by default).
- Precedence of errors: 422 (shape/client_id/cost) → 400 `unknown_tier` → 400
  `cost_exceeds_capacity` → 200/429.
