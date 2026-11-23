"""Deterministic pre-checks and secret redaction.

Pre-checks run before any model call (FR-001, FR-005, FR-006, GR-004); redaction runs on
every string of the model's result (GR-002, INV-004).
"""

from __future__ import annotations

import re
from typing import Any

MAX_CODE_CHARS = 20_000
VALID_KINDS = frozenset({"snippet", "diff"})
SUPPORTED_LANGUAGE = "python"
REDACTED = "[REDACTED]"

# Compiled patterns live in neutrally named constants (ruff S105/S106; research.md R4).
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\n]*"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
)
# A quoted value of 8+ characters assigned to a name that looks like a credential.
_ASSIGNMENT_PATTERN = re.compile(
    r"""(?i)(\b\w*(?:api_?key|secret|password|passwd|token)\w*["']?\s*[:=]\s*)"""
    r"""(["'])([^"'\n]{8,})\2"""
)


def _result(status: str, summary: str, question: str | None = None) -> dict[str, Any]:
    """Build a complete SCH-001 result with no findings (data-model.md ReviewResult)."""
    return {
        "status": status,
        "summary": summary,
        "clarification_question": question,
        "findings": [],
    }


def precheck(code: str, kind: str, language: str) -> dict[str, Any] | None:
    """Return a final result for unreviewable input, or ``None`` to continue to the model.

    Order (spec Inputs): invalid kind -> ValueError; unsupported language, empty or
    whitespace-only code, or a NUL character -> ``needs_clarification``; more than 20,000
    characters -> ``refused``. No model is called for any of these.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be 'snippet' or 'diff', got {kind!r}")
    if str(language).strip().lower() != SUPPORTED_LANGUAGE:
        return _result(
            "needs_clarification",
            f"The language {str(language)[:40]!r} is not supported; only Python can be reviewed.",
            "Only Python is supported. Could you provide the Python code you want reviewed?",
        )
    if not code.strip():
        return _result(
            "needs_clarification",
            "No code was provided, so there is nothing to review.",
            "Please paste the Python code or unified diff you would like reviewed.",
        )
    if "\x00" in code:
        return _result(
            "needs_clarification",
            "The input contains NUL characters and looks like binary data, not source code.",
            "Could you provide the Python source as plain text?",
        )
    if len(code) > MAX_CODE_CHARS:
        return _result(
            "refused",
            f"The input has {len(code):,} characters; the maximum is {MAX_CODE_CHARS:,}. "
            "Please submit a smaller snippet or diff.",
        )
    return None


def _redact_assignment(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{REDACTED}{match.group(2)}"


def redact_text(text: str) -> str:
    """Replace secret-looking values in ``text`` with ``[REDACTED]`` (GR-002)."""
    for pattern in _REDACTION_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return _ASSIGNMENT_PATTERN.sub(_redact_assignment, text)


def redact_value(value: Any) -> Any:
    """Apply :func:`redact_text` to every string inside dicts and lists; keep other values."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value
