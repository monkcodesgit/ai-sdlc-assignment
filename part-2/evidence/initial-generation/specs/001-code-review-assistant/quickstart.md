# Quickstart: validating the Code Review Assistant

Run from `part-2/`. A human runs these steps after implementation (the coding agent does not;
see `speckit-prompts/06-analyze-and-implement.md`).

## Prerequisites

- Python 3.11+
- `.harness/` present and locked (currently missing — see plan.md, "Blocking dependency")
- Credentials exported in the shell (never written to a file):

```bash
export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...        # REVIEW_MODEL optional
# or: export LLM_PROVIDER=openai_compatible LLM_BASE_URL=... LLM_API_KEY=... REVIEW_MODEL=...
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## 1. Snapshot the first generation (Constitution VII)

```bash
python .harness/snapshot.py initial
```

## 2. Deterministic checks (no model)

```bash
pytest                                   # locked contract + evaluator tests
ruff check --config .harness/ruff.toml src tests   # NFR-001
```

Expected: all tests pass, zero lint violations.

## 3. Manual smoke test (live model)

```bash
printf 'import sqlite3\ndef q(c, n):\n    return c.execute("SELECT * FROM u WHERE n=\x27" + n + "\x27")\n' > /tmp/s.py
PYTHONPATH=src python -m reviewer review /tmp/s.py
```

Expected: exit 0; `status` `ok`; a `security` finding on line 3 about SQL injection with
parameterised `refactored_code`. Output matches
[contracts/review-result.schema.json](./contracts/review-result.schema.json).

```bash
printf '' > /tmp/empty.py && PYTHONPATH=src python -m reviewer review /tmp/empty.py
```

Expected: `needs_clarification`, a question, no findings, and it works even with no
credentials set (no model call, GR-004).

## 4. Full evaluation

```bash
python .harness/run_harness.py
```

Expected: all preflight gates pass, and decision **PASS** with EVAL-001..004 met
(`aggregate_score >= 0.85`, `issue_recall >= 0.80`, `schema_validity_rate >= 0.95`,
`guardrail_pass_rate == 1.0`). If more than 20% of samples are SERVICE_ERROR the decision is
INCONCLUSIVE: re-run later; do not change code for it.

## 5. Record evidence

Results land in `evidence/harness-results/` (never edit by hand). Record the narrative in
`evidence/harness-log.md` and the human ACCEPT/REJECT decision with residual risks.
