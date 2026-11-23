# Prompts for `/speckit.analyze` and `/speckit.implement`

## `/speckit.analyze`
Run it and ask additionally: confirm every FR, INV, BEH, GR, EVAL and NFR ID maps to a task or to a harness gate; that module paths and signatures in the plan match what the files in `tests/` and `.harness/` import (`reviewer.service.review_code`, `reviewer.errors`, `reviewer.llm.build_client_from_env`, the client protocol with `complete` and `describe`); that the thresholds in the spec match `.harness/eval_config.json`; and list any inconsistency between spec, plan and tasks. Do not change tests or the dataset.

## `/speckit.implement`  (paste as the extra instruction)

Implement all tasks from `tasks.md` exactly as specified in `spec.md` and `plan.md`. Hard rules:
- Write only under `src/`, `prompts/` and `requirements.txt`.
- Do NOT modify `tests/`, `evals/`, `.harness/`, `pytest.ini`, `requirements-dev.txt`, `specs/`, `.specify/` or the constitution.
- Do NOT add `# noqa`, `# nosec`, `# type: ignore` or any suppression.
- Do NOT write API keys, tokens or `.env` files, and do not hard-code credentials. Read them only from environment variables.
- Do NOT run the tests, the harness, or any live model call, and do not iterate on results. Implement the tasks, then STOP. A human will snapshot this first generation and run the harness.
- Do not tailor the system prompt or code to the text of `evals/dataset.json`; write general behaviour from the specification.
- When finished, list the files you created and the task IDs completed.
