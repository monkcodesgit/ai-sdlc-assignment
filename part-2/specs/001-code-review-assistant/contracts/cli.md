# Contract: Command-line interface

```text
python -m reviewer review PATH [--diff]
```

Run with `PYTHONPATH=src` (or an installed package).

| Element | Meaning |
|---|---|
| `PATH` | file to review, read as UTF-8 |
| `--diff` | treat the file as a unified diff (`kind="diff"`); default `kind="snippet"` |

**stdout**: the result object as JSON (indent 2), conforming to
[review-result.schema.json](./review-result.schema.json).
**stderr**: one-line error messages; never credentials.

| Exit code | Meaning |
|---|---|
| 0 | a result was printed (any `status`) |
| 1 | other `ReviewerError` (provider rejected the request with a non-service status, e.g. 400/404) |
| 2 | usage error, unreadable file, `ValueError`, or `ConfigurationError` |
| 3 | `LLMServiceError` (provider/service failure) |
| 4 | `ModelOutputError` (no JSON object after one retry) |
