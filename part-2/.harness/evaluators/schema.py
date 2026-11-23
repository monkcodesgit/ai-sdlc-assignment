"""Layer 1: structural validation (INV-001, INV-002, SCH-001).

A small hand-written validator so the harness has no third-party dependency and
cannot be influenced by the application's own models.
"""
from __future__ import annotations

import re

from .common import CATEGORIES, SEVERITY_ORDER, STATUSES, Check

TOP_KEYS = {"status", "summary", "clarification_question", "findings"}
FINDING_KEYS = {
    "id", "category", "severity", "line_start", "line_end", "title",
    "evidence", "rationale", "suggestion", "confidence",
}
SUGGESTION_KEYS = {"summary", "refactored_code"}
ID_RE = re.compile(r"F[1-9][0-9]*")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_str(value, low: int, high: int) -> bool:
    return isinstance(value, str) and low <= len(value) <= high


def _check_keys(obj: dict, allowed: set, path: str, errors: list[str]) -> None:
    missing = sorted(allowed - set(obj))
    extra = sorted(set(obj) - allowed)
    if missing:
        errors.append(f"{path}: missing keys {missing}")
    if extra:
        errors.append(f"{path}: unknown keys {extra}")


def _validate_suggestion(sug, path: str) -> list[str]:
    if not isinstance(sug, dict):
        return [f"{path}: not an object"]
    errors: list[str] = []
    _check_keys(sug, SUGGESTION_KEYS, path, errors)
    if "summary" in sug and not _is_str(sug["summary"], 15, 400):
        errors.append(f"{path}.summary: must be a string of 15..400 chars")
    code = sug.get("refactored_code")
    if "refactored_code" in sug and code is not None and not _is_str(code, 0, 4000):
        errors.append(f"{path}.refactored_code: must be null or a string of at most 4000 chars")
    return errors


def _validate_finding(item, path: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{path}: not an object"]
    errors: list[str] = []
    _check_keys(item, FINDING_KEYS, path, errors)
    if "id" in item and not (isinstance(item["id"], str) and ID_RE.fullmatch(item["id"])):
        errors.append(f"{path}.id: must look like F1, F2, ...")
    if item.get("category") not in CATEGORIES:
        errors.append(f"{path}.category: must be one of {list(CATEGORIES)}")
    if item.get("severity") not in SEVERITY_ORDER:
        errors.append(f"{path}.severity: must be one of {list(SEVERITY_ORDER)}")
    start, end = item.get("line_start"), item.get("line_end")
    if not _is_int(start) or start < 1:
        errors.append(f"{path}.line_start: must be an integer >= 1")
    if not _is_int(end) or (_is_int(start) and end < start):
        errors.append(f"{path}.line_end: must be an integer >= line_start")
    for key, high, low in (("title", 120, 1), ("evidence", 300, 1), ("rationale", 600, 20)):
        if key in item and not _is_str(item[key], low, high):
            errors.append(f"{path}.{key}: must be a string of {low}..{high} chars")
    conf = item.get("confidence")
    if "confidence" in item and not (_is_number(conf) and 0 <= conf <= 1):
        errors.append(f"{path}.confidence: must be a number between 0 and 1")
    if "suggestion" in item:
        errors.extend(_validate_suggestion(item["suggestion"], f"{path}.suggestion"))
    return errors


def validate_output(obj) -> list[str]:
    """Return a list of schema violations (empty list means valid)."""
    if not isinstance(obj, dict):
        return ["$: output is not a JSON object"]
    errors: list[str] = []
    _check_keys(obj, TOP_KEYS, "$", errors)
    if obj.get("status") not in STATUSES:
        errors.append(f"$.status: must be one of {list(STATUSES)}")
    if "summary" in obj and not _is_str(obj["summary"], 1, 500):
        errors.append("$.summary: must be a string of 1..500 chars")
    question = obj.get("clarification_question")
    if "clarification_question" in obj and question is not None and not _is_str(question, 1, 300):
        errors.append("$.clarification_question: must be null or a string of 1..300 chars")
    if "findings" in obj:
        if not isinstance(obj["findings"], list):
            errors.append("$.findings: must be an array")
        else:
            for index, item in enumerate(obj["findings"]):
                errors.extend(_validate_finding(item, f"$.findings[{index}]"))
    return errors


def structural_checks(output, raised: str | None) -> list[Check]:
    is_object = isinstance(output, dict)
    observed = "ok" if is_object else (raised or f"got {type(output).__name__}")
    checks = [Check("structural", "output_is_json_object", "INV-001", is_object,
                    "the application returns one JSON object", observed)]
    errors = validate_output(output) if is_object else ["no object to validate"]
    checks.append(Check("structural", "schema_conformance", "INV-002", not errors,
                        "output matches the schema contract (SCH-001)",
                        "no violations" if not errors else "; ".join(errors[:5])))
    return checks
