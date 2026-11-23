# Guidance for `/speckit.tasks`

Use this as the extra instruction text after `/speckit.tasks`.

---

Generate tasks from the plan and spec with these rules:
1. Every task cites the FR/SCH/INV/BEH/GR/EVAL/NFR IDs it satisfies (e.g. "T004 [FR-005, FR-006, GR-004] implement precheck in src/reviewer/guards.py").
2. **Do not create tasks that write or edit tests, `evals/`, harness files or configs**: they already exist and are locked. Tasks may only create or edit files under `src/`, `prompts/` and `requirements.txt`.
3. Order: errors -> guards (precheck, redaction) -> parser -> llm client(s) -> system prompt -> service -> CLI -> requirements. Mark independent tasks parallelizable.
4. Include an explicit task for authoring `prompts/review_system_prompt.md` that references INV, BEH and GR IDs.
5. Do not add tasks that run the tests, the harness or any live model call; a human does that after implementation.
6. Every FR, INV, BEH and GR ID must appear in at least one task.
