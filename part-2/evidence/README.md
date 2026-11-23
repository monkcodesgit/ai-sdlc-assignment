# evidence/
- `initial-generation/`: immutable snapshot of the first generated `src/`, `prompts/`, `specs/` (`.harness/snapshot.py initial`).
- `final-generation/`: snapshot after the evaluation passes.
- `eval-results.json`: the latest OFFICIAL evaluation (written only by a full run whose preflight gates passed).
- `harness-results/`: every run (`history.jsonl`, `run-*-eval.json`, `run-*-preflight.json`, `*-feedback.md`, traceability matrix). Never edit by hand.
- `harness-log.md`: your own narrative (see `harness-log.TEMPLATE.md`).
