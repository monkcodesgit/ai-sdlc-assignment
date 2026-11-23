# evidence/
- `initial-generation/`: immutable snapshot of the first generated `src/` + `specs/` (created by `.harness/snapshot.py initial`).
- `final-generation/`: snapshot after the harness is green.
- `harness-results/`: machine-written run results, feedback files, traceability matrix. Never edit by hand.
- `harness-log.md`: the human-written narrative (see `harness-log.TEMPLATE.md`).
