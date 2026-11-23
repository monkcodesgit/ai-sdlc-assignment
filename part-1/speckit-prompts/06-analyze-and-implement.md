# Prompts for `/speckit.analyze` and `/speckit.implement`

## `/speckit.analyze`
Run it and ask additionally: confirm that every AC-001..AC-031 and NFR-001..NFR-008 maps to a task or a harness gate; that the module paths and class names in the plan match what the files in `tests/` import; and list any inconsistency between spec, plan and tasks. Do not change tests.

## `/speckit.implement`  (paste as the extra instruction)

Implement all tasks from `tasks.md` exactly as specified in `spec.md` and `plan.md`. Hard rules:
- Write only under `src/` and `requirements.txt`.
- Do NOT modify `tests/`, `.harness/`, `pytest.ini`, `requirements-dev.txt`, `specs/`, `.specify/` or the constitution.
- Do NOT add `# noqa`, `# nosec`, `# type: ignore` or any suppression; do not disable lint or security rules.
- Do NOT write secrets, tokens or `.env` files.
- Do NOT run the test suite or the harness and do not iterate on test results. Implement the tasks, then STOP. A human will snapshot this first generation and run the harness.
- When finished, list the files you created and the task IDs completed.
