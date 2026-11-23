# Prompt for `/speckit.constitution`

Paste everything below the line.

---

Create a constitution for a **Tiered Rate Limiter Microservice** (token-bucket algorithm, in-memory storage, HTTP API). Use these principles, keeping every constraint measurable:

**I. Specification is the source of truth.** Code, tests and harness derive from the Spec Kit artifacts. Requirements have stable IDs (FR-nnn, AC-nnn, NFR-nnn). If an ambiguity is found later, the upstream artifact is amended and the change recorded; code or tests are never silently changed to match.

**II. Deterministic and testable by construction.** Time is an injected dependency (a zero-argument callable returning seconds as a float). No test may sleep or read the wall clock. Behaviour must be exactly reproducible.

**III. Measurable quality gates (all mandatory, all must pass before any task counts as done).**
- Ruff reports zero violations using `.harness/ruff.toml`.
- Bandit reports zero MEDIUM or HIGH findings on `src/`.
- Line coverage of the `ratelimiter` package is at least 90%.
- Every AC has at least one test named `test_ac_<nnn>_*`.
- `src/` contains no `# noqa`, `# nosec`, `# type: ignore` or lint-disable comments.

**IV. Security by default.** All external input is validated at the boundary (client id charset and length, cost range, config file size). No secrets, keys, tokens or `.env` files in the repository. Error responses never expose stack traces, file paths or internals. No `eval`, `exec`, `pickle`, shell invocation or dynamic imports.

**V. Immutable validation assets.** During implementation and repair the coding agent MUST NOT modify `tests/`, `.harness/`, `pytest.ini`, `requirements-dev.txt` or any Spec Kit artifact; must not delete, skip, xfail or weaken tests; must not lower thresholds or disable checks. Failures are fixed in `src/`. Specification changes happen only through the Spec Kit artifacts with a changelog entry.

**VI. Simplicity.** The core limiter uses only the Python standard library. FastAPI is confined to the HTTP layer. Storage is in-memory only behind a small adapter interface. No persistence, authentication, distributed coordination or background threads in scope.

**VII. Traceability and evidence.** Every task cites the FR/AC/NFR IDs it satisfies. The first generated implementation is preserved before any repair. Harness results are produced by the harness runner and never edited by hand.

**Governance.** Amendments require a version bump and date. A human makes the final ACCEPT/REJECT decision after the automated harness passes.
