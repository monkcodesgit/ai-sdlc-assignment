# .harness/  (Part 1B: ONE evaluation harness)

`python .harness/run_harness.py` is the single entry point.

| Stage | What it checks | Needs API? |
|---|---|---|
| integrity (NFR-003) | dataset, evaluators, thresholds, tests, harness unchanged since `--lock` | no |
| dataset (FR-002) | >= 15 cases, all six categories, ground-truth lines contain their anchors, ids exist in the spec | no |
| threshold-declared (EVAL-001..004) | the spec declares the same thresholds the harness enforces | no |
| traceability | every spec id is covered by a test, dataset case, evaluator check or gate | no |
| secrets (NFR-002) | no keys / .env / key files | no |
| lint (NFR-001) | Ruff on src/ and tests/ | no |
| unit-tests | application contract tests (fake model) + evaluator self-tests | no |
| **evaluation** | dataset -> application -> Layer 1 schema -> Layer 2 invariants/properties -> Layer 3 semantic -> aggregate vs threshold | **yes** |

Layers live in `evaluators/`: `schema.py` (structural), `invariants.py` (deterministic properties), `quality.py` (ground-truth semantic scoring).
Decisions: PASS (exit 0), FAIL (exit 1), INCONCLUSIVE (exit 2: service problems or not configured).
Service errors are retried 3 times and reported as SERVICE_ERROR; they are never counted as application failures.
`--stub ideal|sloppy` runs the pipeline offline to self-test the harness; stub runs are never written to `evidence/eval-results.json`.
`snapshot.py` freezes `src/`, `prompts/`, `specs/` as evidence.
