<!--
Sync Impact Report
- Version change: (template, unversioned) → 1.0.0
- Modified principles: all template placeholders replaced with:
  I. Specification Is the Source of Truth
  II. Deterministic and Testable by Construction
  III. Measurable Quality Gates (NON-NEGOTIABLE)
  IV. Security by Default
  V. Immutable Validation Assets (NON-NEGOTIABLE)
  VI. Simplicity
  VII. Traceability and Evidence
- Added sections: Technology & Scope Constraints; Development Workflow & Quality Gates; Governance
- Removed sections: none
- Source of principles: speckit-prompts/01-constitution.md
- Follow-up TODOs: none
-->

# Tiered Rate Limiter Microservice Constitution

A token-bucket, tiered rate limiter with in-memory storage exposed over an HTTP API.

## Core Principles

### I. Specification Is the Source of Truth

- Code, tests and harness configuration MUST derive from the Spec Kit artifacts
  (`spec.md`, `plan.md`, `tasks.md` and supporting design documents).
- Every requirement MUST carry a stable ID: `FR-nnn` (functional), `AC-nnn`
  (acceptance criterion) or `NFR-nnn` (non-functional). IDs are never reused or renumbered.
- When an ambiguity or defect is discovered later, the upstream artifact MUST be amended and
  the change recorded in that artifact's changelog. Code or tests MUST NOT be silently changed
  to match an unrecorded interpretation.

Rationale: a single authoritative specification makes generated code auditable and keeps
repairs honest.

### II. Deterministic and Testable by Construction

- Time MUST be an injected dependency: a zero-argument callable returning seconds as a `float`.
- No test may call `time.sleep`, `asyncio.sleep` or read the wall clock; tests advance an
  injected fake clock instead.
- Given the same configuration, clock values and request sequence, the limiter MUST produce
  identical decisions and remaining-token values on every run.

Rationale: rate limiting is time-driven; only an injectable clock makes behaviour exactly
reproducible and tests fast and non-flaky.

### III. Measurable Quality Gates (NON-NEGOTIABLE)

All gates are mandatory, and all MUST pass before any task counts as done:

- Ruff reports zero violations using `.harness/ruff.toml`.
- Bandit reports zero MEDIUM or HIGH severity findings on `src/`.
- Line coverage of the `ratelimiter` package is at least 90%.
- Every `AC-nnn` has at least one test named `test_ac_<nnn>_*`.
- `src/` contains no `# noqa`, `# nosec`, `# type: ignore` or other lint-disable comments.

Rationale: objective, machine-checkable gates replace subjective "looks done" judgements.

### IV. Security by Default

- All external input MUST be validated at the boundary, including client-id character set and
  length, request cost range, and configuration file size.
- The repository MUST NOT contain secrets, keys, tokens or `.env` files.
- Error responses MUST NOT expose stack traces, file paths or internal details.
- `src/` MUST NOT use `eval`, `exec`, `pickle`, shell invocation (`subprocess`, `os.system`)
  or dynamic imports.

Rationale: a rate limiter sits on the request path; it must fail safely and leak nothing.

### V. Immutable Validation Assets (NON-NEGOTIABLE)

During implementation and repair, the coding agent MUST NOT:

- modify `tests/`, `.harness/`, `pytest.ini`, `requirements-dev.txt` or any Spec Kit artifact;
- delete, skip, xfail or otherwise weaken tests;
- lower thresholds or disable checks.

Failures MUST be fixed in `src/`. Specification changes happen only through the Spec Kit
artifacts, each with a changelog entry.

Rationale: the validation assets define "correct"; editing them to pass defeats the harness.

### VI. Simplicity

- The core limiter MUST use only the Python standard library.
- FastAPI is confined to the HTTP layer; the core MUST NOT import it.
- Storage is in-memory only, behind a small storage adapter interface.
- Out of scope: persistence, authentication, distributed coordination and background threads.

Rationale: a small, dependency-free core is easier to reason about, test and verify.

### VII. Traceability and Evidence

- Every task in `tasks.md` MUST cite the `FR`/`AC`/`NFR` IDs it satisfies.
- The first generated implementation MUST be preserved (`evidence/initial-generation/`)
  before any repair begins.
- Harness results in `evidence/harness-results/` MUST be produced by the harness runner and
  are never edited by hand.

Rationale: evidence of the generate → validate → repair loop is a deliverable in itself.

## Technology & Scope Constraints

- Language: Python 3; package name `ratelimiter` under `src/` (`pythonpath = src`).
- Algorithm: token bucket per client, with capacity and refill rate defined per tier.
- HTTP layer: FastAPI (served with uvicorn); tests use `httpx`/FastAPI test client.
- Tooling: pytest, pytest-cov, ruff and bandit as pinned in `requirements-dev.txt`.
- No new runtime dependencies may be added without a constitution-compliant plan entry that
  justifies them.

## Development Workflow & Quality Gates

1. `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` →
   `/speckit-analyze` → `/speckit-implement`, in that order.
2. The plan's Constitution Check MUST pass (or record a justified exception) before tasks are
   generated.
3. After initial generation, snapshot to `evidence/initial-generation/`.
4. Run the harness; on failure, repair `src/` only (Principle V) and re-run until all gates in
   Principle III pass.
5. Snapshot the green state to `evidence/final-generation/` and record the narrative in
   `evidence/harness-log.md`.

## Governance

- This constitution supersedes all other practices and guidance in the project.
- Amendments MUST be made via `/speckit-constitution`, with a semantic version bump and an
  updated Last Amended date:
  - MAJOR: removal or backward-incompatible redefinition of a principle or gate.
  - MINOR: a new principle or section, or materially expanded guidance.
  - PATCH: clarifications and wording fixes with no change in meaning.
- Every plan and review MUST verify compliance with these principles; complexity beyond
  Principle VI MUST be justified in the plan's Complexity Tracking.
- A human makes the final ACCEPT/REJECT decision, only after the automated harness passes.

**Version**: 1.0.0 | **Ratified**: 2026-11-23 | **Last Amended**: 2026-11-23
