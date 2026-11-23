# evals/dataset.json

20 cases (minimum required: 15). Locked by the harness integrity gate.
Categories: normal 5, boundary 4, ambiguous 2, missing 3, malformed 3, adversarial 3. 13 labelled issues.

Each case: `id`, `category`, `requirements` (spec ids), `kind`, `language`, `input`, `tags` (`guardrail`), and `expected`:
- `status_any`: acceptable statuses; `status_requirement`: which spec id that check enforces.
- `issues[]`: ground truth: `categories_any`, `lines` (+ `line_tolerance`), `anchor` (text that must sit on those lines),
  `min_severity`, `rationale_keywords_any`, `refactor_regex` / `refactor_forbidden_regex`, and a `reference_finding`
  (an answer key, also used to self-test the harness).
- `max_findings`, `max_severity` (clean-code rubric), `forbidden_substrings` (leak / harmful-content check), `llm_calls` (exact model-call count).

Seeded secret strings in this file are FAKE and exist only to test redaction.
