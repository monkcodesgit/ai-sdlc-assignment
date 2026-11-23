# Research: Semantic Code Review & Refactoring Assistant

No `NEEDS CLARIFICATION` items remained in Technical Context; the stack and layout were given
in `speckit-prompts/04-plan.md`. This file records the decisions that shape implementation
and the alternatives rejected.

## R1. HTTP access to providers

- **Decision**: call provider REST APIs directly with `httpx` (sync client, 60 s timeout).
- **Rationale**: Constitution VIII allows stdlib + one HTTP client. Two small clients cover
  Anthropic and every OpenAI-compatible endpoint (OpenAI, Gemini's compatible endpoint, Groq,
  Ollama).
- **Alternatives**: vendor SDKs (extra dependencies, one per provider); `urllib` (verbose
  timeout and error handling).

## R2. Error classification

- **Decision**: map `httpx.TimeoutException`, `httpx.TransportError`, HTTP 401, 403, 408,
  409, 429, 5xx and 529 to `LLMServiceError`; the application never retries it. Every other
  non-2xx status (400, 404, 413, 422, …) raises plain `ReviewerError`, because it signals an
  application or configuration defect that must count as a FAIL. Unparsable replies →
  `ModelOutputError` after exactly one retry.
- **Rationale**: Constitution VI and clarification Q2: only the harness retries (3 attempts)
  so service errors are counted honestly and retries don't multiply.
  `test_eval_005_service_errors_propagate_without_a_retry` asserts exactly one call.
- **Alternatives**: app-level backoff (hides outages from the harness; rejected in clarify);
  treating every non-2xx as a service error (would hide request-building bugs or a wrong
  model id as SERVICE_ERROR / INCONCLUSIVE instead of FAIL; rejected in analyze, finding D2).

## R3. JSON extraction

- **Decision**: try `json.loads(text)`; then content of the first ``` fence; then
  `JSONDecoder.raw_decode` starting at each `{` until a `dict` decodes. Non-dict (e.g. a
  list) counts as failure.
- **Rationale**: handles fences and surrounding prose (locked tests) without regex-matching
  braces, which breaks on braces inside strings.
- **Alternatives**: provider "JSON mode" / tool use (provider-specific; not available on all
  OpenAI-compatible endpoints).

## R4. Secret redaction

- **Decision**: after the model replies, replace matches in every output string with
  `[REDACTED]`:
  - `sk-[A-Za-z0-9_\-]{20,}` (hyphen included: the locked test secret is
    `sk-FAKE-0000-1111-2222-3333`)
  - `AKIA[0-9A-Z]{16}`
  - `gh[pousr]_[A-Za-z0-9]{36,}`
  - `-----BEGIN [A-Z ]*PRIVATE KEY-----` … `-----END [A-Z ]*PRIVATE KEY-----` (DOTALL)
  - quoted values of ≥ 8 chars assigned to names containing `api_key|secret|password|passwd|token`
    (case-insensitive; `=` or `:`), replacing only the quoted value.
- **Rationale**: GR-002 / clarify sheet: the model still sees the code; redaction is a
  deterministic post-step that doesn't rely on the model. The assignment pattern covers
  `password = "hunter2hunter2"` in the locked test.
- **Alternatives**: redacting input before the model (would stop the model citing the
  hardcoded-secret issue with correct evidence); entropy detection (false positives).

## R5. Line numbering in the prompt

- **Decision**: normalise CRLF→LF, split on `\n` dropping one trailing empty element, prefix
  each line `N: ` (1-based). Diffs are numbered over the whole diff text, headers included
  (clarification Q3).
- **Rationale**: the model can copy correct `line_start`/`line_end` (INV-003, INV-008) and
  verbatim evidence (INV-004); the locked test checks `1: import os` and `2: x = 1`.

## R6. Post-processing scope

- **Decision**: only redact, truncate to 10 and renumber `F1..Fn`. No schema repair.
- **Rationale**: Constitution III: layer 1 must see real schema defects. The locked test
  `test_inv_002_malformed_model_json_is_returned_as_is_without_crashing` requires
  `{"status":"ok","findings":"oops"}` to pass through unchanged.
- **Alternatives**: validating and repairing the output (would mask prompt defects).

## R7. Model and sampling

- **Decision**: `temperature=0.0`, `max_tokens=8192`; model from `REVIEW_MODEL`, defaulting to
  `claude-haiku-4-5` for Anthropic; required for `openai_compatible`.
- **Rationale**: NFR-004 / Constitution VII (≤ 0.2, recorded via `describe()`); a fast small
  model keeps evaluation cost low; configurable for comparison runs.
- **Amendment 2026-11-23 (human decision at `/speckit-implement`)**: the default was
  `claude-haiku-5-5` with `max_tokens=2048` (from `speckit-prompts/04-plan.md`). The Claude API
  reference shows Haiku 5.5 rejects any non-default `temperature` with HTTP 400, so it cannot
  meet NFR-004 honestly (sending 0.0 fails; omitting it runs at 1.0). The default is now
  `claude-haiku-4-5`, which accepts `temperature=0.0` with `anthropic-version: 2023-06-01`.
  `max_tokens` is raised to 8192 so a reply with 10 findings and refactored code is not
  truncated (truncation would be a structural FAIL). `REVIEW_MODEL` still overrides the model.
- **Alternatives**: keep Haiku 5.5 and omit temperature (fails the harness's NFR-004 check);
  make `openai_compatible` the default (quality depends on an unspecified model).

## R8. Prompt versioning

- **Decision**: system prompt in `prompts/review_system_prompt.md` with a version line at the
  top; the harness hashes the file.
- **Rationale**: NFR-004: prompt changes are traceable across evaluation runs without code
  changes.

## R9. Harness availability (risk)

- **Finding**: `part-2/.harness/` is absent from the working tree and git history, although
  `pytest.ini` and `tests/` import `evaluators` and `stub_client` from it.
- **Decision**: proceed with design; the harness is a locked human-owned asset and MUST NOT
  be created by implementation. A human must add and lock it (`run_harness.py --lock`)
  before tests or evaluation can run.
