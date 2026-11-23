# Guidance for `/speckit.tasks`

Use this as the extra instruction text after `/speckit.tasks`.

---

Generate tasks from the plan and spec with these rules:
1. Every task cites the FR/AC/NFR IDs it satisfies (e.g. "T005 [AC-001..AC-010] implement RateLimiter.check in src/ratelimiter/limiter.py").
2. **Do not create tasks that write or edit tests, harness files or configs**: they already exist and are locked. A task may only create or edit files under `src/` and `requirements.txt`.
3. Order: errors → config (+JSON loader) → store → limiter → HTTP app → main/requirements. Mark independent tasks parallelizable.
4. Do not add a task that runs the harness or iterates on failures; a human runs the harness after implementation.
5. Every AC must appear in at least one task.
