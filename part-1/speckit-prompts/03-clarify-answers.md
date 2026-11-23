# Prepared answers for `/speckit.clarify`

Spec Kit will ask its own questions. Answer from this sheet when it asks about these topics, so the answers stay consistent with the locked tests. If it asks something that would CHANGE behaviour the tests assert, do not just agree: stop, decide as a human, amend the spec AND (if needed) the tests, run `python .harness/run_harness.py --lock`, and record the change in `evidence/harness-log.md`.

| Topic | Answer |
|---|---|
| Bucket key | The pair (tier, client_id). Same client in two tiers = two buckets. |
| Does a denied request consume tokens? | No. Denied requests consume nothing (refill still applies). |
| Initial bucket state | Full (tokens = capacity at first sight). |
| Refill model | Lazy and continuous: computed from elapsed time at each request; no timers or threads. |
| Rounding | remaining = floor; retry_after = ceil with minimum 1; reset = ceil seconds to full. |
| Clock going backwards | Treat elapsed as 0; last-refill time never decreases. |
| Time source | Injected callable returning float seconds; default is a monotonic clock. |
| Weighted cost | Supported; integer ≥ 1; > capacity is an error (HTTP 400). |
| Unknown tier case sensitivity | Case-sensitive; no trimming. |
| client_id rules | 1–128 chars of `A-Za-z0-9._:@-`. |
| Validation order | shape + client_id/cost → tier → cost vs capacity. |
| Error format | 400 `{"error": "<code>"}`; 422 framework validation body; 429 body as specified. |
| Header names | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`. |
| Config source | Mapping in code, or JSON file ≤ 64 KiB, optionally path from env var `RATELIMITER_TIERS_FILE`. |
| Idle bucket eviction | Out of scope; recorded as a known limitation. |
| Logging | Minimal; never log secrets; not tested. |
