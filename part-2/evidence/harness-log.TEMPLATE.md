# harness-log.md  (WRITE THIS YOURSELF; AI-generated log entries are not allowed by the assignment)

Copy to `harness-log.md` and replace every prompt with your own words and your own evidence.

## 1. Model and configuration (no secrets)
(Provider, model id, temperature, max_tokens, prompt hash, dataset hash, date. Copy from `evidence/eval-results.json`.)

## 2. Threshold and scoring method (as declared in the spec BEFORE the final evaluation)
(The four thresholds, the layer weights, how the per-sample score and each metric are computed, which commit declared them.)

## 3. Initial generation
(Commit/tag of the first unrepaired generation, snapshot location, which spec/plan/tasks context the agent received.)

## 4. Harness results, run by run
(For EACH run in `history.jsonl`: run id, commit, preflight gates, structural / property / semantic outcomes, metrics, decision. Include INCONCLUSIVE or service-error runs and say how you handled them.)

## 5. Meaningful failures and the evidence fed back
(Only genuine failures: case ids, the failed requirement/property, the feedback you gave the agent.)

## 6. Repair and re-evaluation
(What changed in prompt/parser/guardrail/code, why that fixes the ROOT CAUSE generally, and the re-evaluation outcome. Confirm no case, expectation, guardrail or threshold was weakened.)

## 7. Final human decision
ACCEPT / REJECT:
Justification:
Known limitations and residual risks:
