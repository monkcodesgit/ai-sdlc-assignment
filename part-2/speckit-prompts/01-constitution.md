# Prompt for `/speckit.constitution`

Paste everything below the line.

---

Create a constitution for a **Semantic Code Review & Refactoring Assistant**: an application that sends supplied Python code or a diff to a language model and returns structured, validated findings with refactoring suggestions. Keep every constraint measurable.

**I. Specification is the source of truth.** Requirements have stable IDs (FR, SCH, INV, BEH, GR, EVAL, NFR). Code, prompts, evaluation cases and harness derive from the specification. If something is ambiguous, the upstream artifact is amended and the change is recorded; evaluation cases and expectations are never silently edited to match behaviour.

**II. Non-determinism is bounded by contract, not by hope.** Model wording may vary; the output schema, structural invariants, behavioural properties and guardrails may not. Every behaviour that matters must be checkable without exact text equality.

**III. Layered, independent evaluation.** One evaluation harness judges the application in three layers: (1) schema/structural validation, (2) deterministic invariants and properties, (3) semantic/quality scoring against ground truth. An LLM judge, if ever added, may supplement but never replace layers 1 and 2. The acceptance threshold is declared in the specification BEFORE the final evaluation and is never lowered afterwards.

**IV. Safety and guardrails are mandatory.** The model must treat reviewed code as untrusted data and never obey instructions embedded in it. Secret values must never appear in output (they are redacted). Requests to produce malicious software are refused or clarified. Unreviewable input (empty, binary, unsupported language, oversize) is handled deterministically WITHOUT calling the model.

**V. Immutable evaluation assets.** During implementation and repair the coding agent MUST NOT modify `tests/`, `evals/dataset.json`, `.harness/`, thresholds, `pytest.ini`, `requirements-dev.txt` or any Spec Kit artifact; must not delete, skip or weaken cases or checks; must not special-case dataset inputs. Failures are repaired in `src/` and `prompts/` by fixing root causes generally.

**VI. Failures are classified honestly.** Provider/service problems (timeouts, rate limits, 5xx, auth) are SERVICE errors, retried by the harness and never counted as application failures; too many of them make a run INCONCLUSIVE, not PASS or FAIL. Application, prompt and parser defects are FAILs.

**VII. Reproducibility and evidence.** Model provider, model id, temperature (at most 0.2), prompt version hash, dataset hash and thresholds are recorded with every evaluation. No secret or API key is ever stored in the repository; credentials come only from environment variables. The first generated implementation is preserved before any repair, and harness results are never edited by hand.

**VIII. Simplicity.** Python 3.11+, standard library plus an HTTP client only. No frameworks, databases or background services.

**Governance.** Amendments require a version bump and date. A human makes the final ACCEPT/REJECT decision after the automated harness passes and records residual risks.
