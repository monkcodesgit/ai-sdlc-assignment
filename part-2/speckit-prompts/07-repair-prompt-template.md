# Repair prompt template (use only after a REAL harness failure)

Paste this, followed by the full contents of `evidence/harness-results/feedback-latest.md`.

---

The harness failed on your implementation. The evidence below was produced by the harness and is authoritative. It lists the failing case, the application's output, the failed requirement/property and the evaluation result.

Rules: you may change `src/` (application code, parser, validators, guardrails) and `prompts/` only. Do not modify `tests/`, `evals/dataset.json`, `.harness/`, thresholds, `pytest.ini`, `requirements-dev.txt`, any Spec Kit artifact, or add suppression comments. Do not special-case the text of any evaluation case: fix the general root cause (for example a missing prompt rule, a parsing gap, or a missing guardrail). If you believe the specification itself is wrong, stop and say so instead of working around it.

First explain the ROOT CAUSE of each failure in one or two sentences, then fix it, then list exactly which files, functions or prompt sections you changed. Do not run the harness or call any model; a human will re-run it.

<paste feedback-latest.md here>
