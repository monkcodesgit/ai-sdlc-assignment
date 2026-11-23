"""Review orchestration: pre-check, prompt, model call, parsing and post-processing.

Implements ``review_code`` (FR-001..FR-006, INV-001, INV-005, GR-002, GR-004, EVAL-005) as
described in plan.md ``service.py`` and contracts/python-api.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reviewer.errors import ModelOutputError
from reviewer.guards import precheck, redact_value
from reviewer.llm import LLMClient, build_client_from_env
from reviewer.parser import extract_json

MAX_FINDINGS = 10
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "review_system_prompt.md"
RETRY_INSTRUCTION = (
    "Your previous reply could not be parsed. Reply with the JSON object only: no code "
    "fences, no prose."
)
DIFF_INSTRUCTION = (
    "This is a unified diff: review only added lines (starting with '+', not '+++') and "
    "cite the diff-text line numbers shown."
)


def load_system_prompt() -> str:
    """Return the versioned system prompt (NFR-004: hashed by the harness)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def number_lines(code: str) -> str:
    """Prefix each line with ``N: `` (1-based; CRLF normalised; no line for a final newline)."""
    lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return "\n".join(f"{number}: {line}" for number, line in enumerate(lines, start=1))


def build_user_message(code: str, kind: str) -> str:
    """Build the user turn: the kind, a diff reminder when needed, and the numbered code."""
    parts = [f"Kind: {kind}"]
    if kind == "diff":
        parts.append(DIFF_INSTRUCTION)
    parts.append(f"<code>\n{number_lines(code)}\n</code>")
    return "\n\n".join(parts)


def _ask_model(client: LLMClient, system: str, user: str) -> dict[str, Any]:
    """One call, plus exactly one retry if the reply has no JSON object (INV-001).

    ``LLMServiceError`` is never caught here: the harness owns service retries (EVAL-005).
    """
    reply = client.complete(system, user)
    try:
        return extract_json(reply)
    except ValueError:
        pass
    reply = client.complete(system, f"{user}\n\n{RETRY_INSTRUCTION}")
    try:
        return extract_json(reply)
    except ValueError as exc:
        raise ModelOutputError(f"no JSON object in the model reply after one retry: {exc}") from exc


def _postprocess(result: dict[str, Any]) -> dict[str, Any]:
    """Redact secrets everywhere, then cap and renumber findings (GR-002, INV-005).

    Nothing else is added, removed or validated, so schema defects stay visible to the
    harness (Constitution III; research.md R6).
    """
    result = redact_value(result)
    findings = result.get("findings")
    if isinstance(findings, list):
        findings = findings[:MAX_FINDINGS]
        for number, item in enumerate(findings, start=1):
            if isinstance(item, dict):
                item["id"] = f"F{number}"
        result["findings"] = findings
    return result


def review_code(
    code: str,
    kind: str = "snippet",
    language: str = "python",
    *,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Review Python ``code`` (a snippet or a unified diff) and return a SCH-001 result.

    Unreviewable input is answered by the deterministic pre-check without building or
    calling a client (GR-004). Raises ``ValueError`` for an invalid ``kind`` (FR-001),
    ``ModelOutputError`` when no JSON object can be parsed after one retry, and lets
    ``LLMServiceError`` propagate without retrying.
    """
    early = precheck(code, kind, language)
    if early is not None:
        return early
    user = build_user_message(code, kind)
    model = client if client is not None else build_client_from_env()
    result = _ask_model(model, load_system_prompt(), user)
    return _postprocess(result)
