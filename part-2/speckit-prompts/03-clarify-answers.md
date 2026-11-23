# Prepared answers for `/speckit.clarify`

Answer from this sheet where Spec Kit asks about these topics, so the answers stay consistent with the locked dataset and tests. If it asks something that would CHANGE behaviour the dataset or tests assert, stop: decide as a human, amend the spec, update the dataset/tests only if the spec change demands it, run `python .harness/run_harness.py --lock`, and record it in `evidence/harness-log.md`.

| Topic | Answer |
|---|---|
| Diff line numbering | Index the diff text itself (1-based), headers included. |
| Findings on removed or context lines of a diff | Not allowed; only added (`+`) lines. |
| Evidence format | Verbatim excerpt; whitespace differences ignored; `[REDACTED]` allowed. |
| Secret handling | Redact secret-looking values in ALL output strings after the model replies; the model still sees the code. |
| Unsupported language | `needs_clarification` with a question, no model call. |
| Prose / "please review my code" with no code | `needs_clarification` (decided by the model, BEH-006). |
| Harmful request | `refused` or `needs_clarification`, no findings, no harmful content. |
| Syntax-error code | Still reviewed; a `bug` finding describing the syntax error is expected. |
| Finding limit | Maximum 10; extras are truncated; ids are renumbered F1..Fn. |
| Invalid model JSON | One retry; then an error (ModelOutputError) that the harness counts as a structural failure. |
| Service failures | Raised as LLMServiceError, not retried by the app; the harness retries (3 attempts). |
| Temperature | 0 by default; must be at most 0.2. |
| Default model | Configurable by environment variable; recorded in results. |
| Semantic scoring | Ground-truth and heuristic only (no LLM judge). |
| Repeats | Default 1 run per case; `--repeats N` is available. |
| Confidence | Informational only, not scored. |
