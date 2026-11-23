# Repair prompt template (use only after a REAL harness failure)

Paste this, followed by the full contents of `evidence/harness-results/feedback-latest.md`.

---

The deterministic harness failed on your implementation. The evidence below was produced by the harness; it is authoritative.

Rules: fix the implementation under `src/` only. Do not modify `tests/`, `.harness/`, `pytest.ini`, `requirements-dev.txt`, any Spec Kit artifact, or add suppression comments, skips or relaxed thresholds. If you believe the specification itself is wrong, stop and say so instead of working around it.

First explain the ROOT CAUSE of each failure in one or two sentences, then fix it, then list exactly which files and functions you changed. Do not run the harness; a human will re-run it.

<paste feedback-latest.md here>
