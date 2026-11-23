# Contract: Python API

These names and signatures are imported by the locked `tests/` and `.harness/`; they MUST NOT
change.

## `reviewer.service.review_code`

```python
def review_code(code: str, kind: str = "snippet", language: str = "python", *,
                client: LLMClient | None = None) -> dict
```

- Returns a `dict` (normally a SCH-001 object; see [review-result.schema.json](./review-result.schema.json)).
- Raises `ValueError` for an invalid `kind` (FR-001), before any model call.
- Pre-check results (`needs_clarification` / `refused`) make zero `client.complete` calls and
  do not construct a client.
- Otherwise exactly 1 call, or 2 if the first reply has no JSON object (INV-001).
- Raises `ModelOutputError` after the second unparsable reply.
- `LLMServiceError` from the client propagates unchanged after the first call (no retry).
- Post-processing: secrets → `[REDACTED]` in every string; `findings` (if a list) truncated to
  10 and `id`s renumbered `F1..Fn` (if items are dicts). A malformed object is returned as is.
- If `client` is `None`, `reviewer.llm.build_client_from_env()` is used.

## `reviewer.errors`

```python
class ReviewerError(Exception): ...
class LLMServiceError(ReviewerError): ...    # provider/transport failure (SERVICE)
class ModelOutputError(ReviewerError): ...   # no JSON object after one retry (FAIL)
class ConfigurationError(ReviewerError): ... # missing credentials/settings
```

## `reviewer.llm`

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...
    def describe(self) -> dict: ...  # {"provider", "model", "temperature", "max_tokens"}

def build_client_from_env() -> LLMClient
```

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `anthropic` (default) or `openai_compatible` |
| `ANTHROPIC_API_KEY` | required for `anthropic` |
| `REVIEW_MODEL` | model id; default `claude-haiku-5-5` for anthropic; required for `openai_compatible` |
| `LLM_BASE_URL` | required for `openai_compatible` (e.g. `http://localhost:11434/v1`) |
| `LLM_API_KEY` | bearer token for `openai_compatible` (optional for local servers) |

Missing required values → `ConfigurationError`. Credentials are never logged or printed.

## `reviewer.guards`

```python
def precheck(code: str, kind: str, language: str) -> dict | None
def redact_text(text: str) -> str
def redact_value(value: object) -> object   # recursive over dict/list/str
```

## `reviewer.parser`

```python
def extract_json(text: str) -> dict   # raises ValueError if no JSON object is found
```
