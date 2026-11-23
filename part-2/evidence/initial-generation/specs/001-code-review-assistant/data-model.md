# Data Model: Semantic Code Review & Refactoring Assistant

All entities are in-memory values; nothing is persisted. The authoritative wire format is
[contracts/review-result.schema.json](./contracts/review-result.schema.json) (SCH-001).

## ReviewRequest (input)

| Field | Type | Rules |
|---|---|---|
| `code` | str | Python source or unified diff. CRLF normalised to LF. Line count = lines after splitting on LF, a trailing newline adds none. |
| `kind` | str | `snippet` (default) or `diff`; anything else → `ValueError` (FR-001). |
| `language` | str | default `python`; any other value → `needs_clarification` without a model call (FR-005). |

Pre-check order (first match wins, no model call): invalid kind → error; language ≠ python →
`needs_clarification`; empty/whitespace-only → `needs_clarification`; contains NUL →
`needs_clarification`; `len(code) > 20000` → `refused` (FR-006, GR-004).

## ReviewResult (output, SCH-001)

| Field | Type | Rules |
|---|---|---|
| `status` | enum | `ok`, `needs_clarification`, `refused` |
| `summary` | str | 1–500 chars |
| `clarification_question` | str \| null | 1–300 chars when present |
| `findings` | Finding[] | ≤ 10 (INV-005) |

No other fields (INV-002).

### Status rules (INV-006)

| status | `clarification_question` | `findings` |
|---|---|---|
| `ok` | null | 0–10 |
| `needs_clarification` | non-empty string | empty |
| `refused` | null (pre-check) · null or 1–300-char string (model) | empty |

Status is decided once per request: by the pre-check, or by the model. There are no other
state transitions. A `refused` result produced by the pre-check (oversize input, FR-006)
always has `clarification_question: null`; a `refused` result produced by the model (GR-003)
MAY carry a question, since INV-006 constrains only `findings` for `refused`.

## Finding

| Field | Type | Rules |
|---|---|---|
| `id` | str | `F1`..`Fn`, unique, sequential (renumbered by the service) |
| `category` | enum | `security`, `bug`, `performance`, `maintainability`, `error-handling` |
| `severity` | enum | `low` < `medium` < `high` < `critical` |
| `line_start` | int | ≥ 1, ≤ input line count (INV-003) |
| `line_end` | int | ≥ `line_start`, ≤ input line count; for diffs every line in range is an added `+` line, not `+++` (INV-008) |
| `title` | str | 1–120 chars |
| `evidence` | str | 1–300 chars; verbatim excerpt of input ignoring whitespace, or contains `[REDACTED]` (INV-004) |
| `rationale` | str | 20–600 chars |
| `suggestion` | Suggestion | required (FR-003) |
| `confidence` | number | 0–1, informational, not scored |

## Suggestion

| Field | Type | Rules |
|---|---|---|
| `summary` | str | 15–400 chars |
| `refactored_code` | str \| null | ≤ 4000 chars; when present, parses as Python (INV-007) and is not a copy of the evidence (BEH-007) |

## Errors (raised, not returned)

| Error | When | Harness treatment |
|---|---|---|
| `ValueError` | invalid `kind` | test expectation |
| `ModelOutputError` | no JSON object after one retry | structural FAIL |
| `LLMServiceError` | timeout, connection, HTTP 401/403/408/409/429/5xx/529 | SERVICE_ERROR, retried by harness, excluded from scores |
| `ConfigurationError` | missing credentials/settings | setup error |
| `ReviewerError` (base, raised directly) | provider returned any other non-2xx (400, 404, 422, …) | application FAIL, not retried |

All derive from `ReviewerError` (except `ValueError`).

## ClientDescription (`LLMClient.describe()`)

`{provider, model, temperature, max_tokens}`; recorded with every evaluation (NFR-004).
