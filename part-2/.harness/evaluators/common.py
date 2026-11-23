"""Shared constants and the Check record."""
from __future__ import annotations

from dataclasses import asdict, dataclass

CATEGORIES = ("security", "bug", "performance", "maintainability", "error-handling")
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
STATUSES = ("ok", "needs_clarification", "refused")


@dataclass
class Check:
    layer: str          # "structural" | "property" | "semantic"
    name: str
    requirement: str    # spec id, e.g. INV-003
    passed: bool
    expected: str
    observed: str

    def to_dict(self) -> dict:
        return asdict(self)


def norm_ws(text: str) -> str:
    """Collapse all whitespace runs so formatting differences do not matter."""
    return " ".join(str(text).split())


def split_lines(code: str) -> list[str]:
    """Spec line model: lines separated by LF after CRLF normalisation; a trailing
    newline does not create an extra empty line; empty input has zero lines."""
    lines = code.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines
