# .harness/
`run_harness.py` runs seven independent gates; the coding agent can neither see nor change their logic during repair.

| Gate | Enforces | Tool |
|---|---|---|
| integrity | NFR-008 tests/harness/config unchanged since `--lock` | SHA-256 manifest |
| lint | NFR-001 | Ruff (`ruff.toml`) |
| sast | NFR-002 | Bandit, medium+ |
| secrets | NFR-006 | regex scan + forbidden file names |
| suppressions | NFR-007 | no noqa/nosec/type-ignore in `src/` |
| tests | AC-001..031, NFR-003/004/005 | pytest + pytest-cov (>= 90%) |
| traceability | every spec ID enforced | spec.md vs test names |

Status values: `PASS`, `FAIL` (your code or process), `ERROR` (tool missing or cannot start: environment problem).
`snapshot.py` freezes `src/` and `specs/` as evidence.
