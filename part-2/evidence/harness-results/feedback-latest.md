# Harness feedback for the coding agent

## Repair rules (mandatory)
- You MAY change: `src/` (application code, parsers, validators, guardrails) and `prompts/`.
- You MUST NOT change: `tests/`, `evals/dataset.json`, `.harness/`, thresholds, `pytest.ini`,
  `requirements-dev.txt`, or any Spec Kit artifact. Do not delete or skip cases, do not lower
  the declared thresholds, do not disable guardrails, do not special-case dataset inputs.
- Fix the ROOT CAUSE in general terms (a prompt rule, a parser, a validator), not by matching
  the literal text of an evaluation case.
- If you believe the specification is wrong, STOP and report it; a human amends the spec.

## Preflight gate `secrets`: FAIL (NFR-002)
- Expected: No API keys, tokens, .env files or key files in the repository.
- Observed: 2 finding(s): specs/001-code-review-assistant/research.md: matches api-key-like; specs/001-code-review-assistant/research.md: matches hardcoded-credential
```
[
  "specs/001-code-review-assistant/research.md: matches api-key-like",
  "specs/001-code-review-assistant/research.md: matches hardcoded-credential"
]
```

