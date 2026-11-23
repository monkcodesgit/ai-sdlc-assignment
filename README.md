# ai-sdlc-assignment
# Assignment 1: Spec-Driven Development and Harness Engineering

Course: AI-Augmented SDLC (SEZG534), BITS Pilani. Student: Vishal Rathee.

| Part | Application | Folder |
|---|---|---|
| 1A | Tiered Rate Limiter Microservice (deterministic) | `part-1/` |
| 1B | Semantic Code Review & Refactoring Assistant (non-deterministic, LLM-backed) | `part-2/` |

- Demo video: <link>
- Python: 3.11+

## Part 1A
```bash
cd part-1 && python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python .harness/run_harness.py
```

## Part 1B
```bash
cd part-2 && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements.txt
python .harness/run_harness.py --skip-eval      # preflight gates, no API calls
# set credentials in your SHELL (never in a file), e.g.:
export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...   # see part-2/.env.example for names
python .harness/run_harness.py                   # full evaluation; writes evidence/eval-results.json
```
No API keys or secrets are included in this repository.

## Evidence map
Each part: Spec Kit artifacts in `.specify/` and `specs/`; prompts used in `speckit-prompts/`; first generation in `evidence/initial-generation/`; final in `evidence/final-generation/`; harness results in `evidence/harness-results/`; narrative in `evidence/harness-log.md`. Part 1B also has `evals/dataset.json` and `evidence/eval-results.json`.
