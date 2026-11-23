"""Layer 2: deterministic invariants and per-case properties.

Requirement ids: INV-003..INV-008, BEH-003, BEH-006, FR-006, GR-002, GR-003, GR-004.
These checks never use a model and never use exact text equality.
"""
from __future__ import annotations

import ast
import json
import re
import textwrap

from .common import SEVERITY_ORDER, Check, norm_ws, split_lines

REDACTED = "[REDACTED]"


def _added_line(line: str) -> bool:
    return line.startswith("+") and not line.startswith("+++")


def _strip_diff_markers(code: str) -> str:
    return "\n".join(line[1:] if line[:1] in "+- " else line for line in code.splitlines())


def _evidence_ok(evidence: str, case: dict) -> bool:
    if REDACTED in evidence:
        return True
    wanted = norm_ws(evidence)
    haystacks = [norm_ws(case["input"])]
    if case["kind"] == "diff":
        haystacks.append(norm_ws(_strip_diff_markers(case["input"])))
    return any(wanted in hay for hay in haystacks)


def _parses(code: str) -> bool:
    try:
        ast.parse(textwrap.dedent(code))
    except (SyntaxError, ValueError):
        return False
    return True


def _check(name: str, req: str, passed: bool, expected: str, observed: str) -> Check:
    return Check("property", name, req, passed, expected, observed)


def property_checks(case: dict, output: dict, llm_calls: int) -> list[Check]:
    expected = case["expected"]
    findings = output.get("findings", [])
    lines = split_lines(case["input"])
    checks: list[Check] = []

    if findings:
        bad = [f["id"] for f in findings if not 1 <= f["line_start"] <= f["line_end"] <= len(lines)]
        checks.append(_check("line_ranges_in_bounds", "INV-003", not bad,
                             f"every finding lies within lines 1..{len(lines)}",
                             "ok" if not bad else f"out of range: {bad}"))
        bad = [f["id"] for f in findings if not _evidence_ok(f["evidence"], case)]
        checks.append(_check("evidence_is_verbatim", "INV-004", not bad,
                             "evidence is a verbatim excerpt of the input (or redacted)",
                             "ok" if not bad else f"evidence not found in input for: {bad}"))
        with_code = [f for f in findings if f["suggestion"]["refactored_code"]]
        if with_code:
            bad = [f["id"] for f in with_code if not _parses(f["suggestion"]["refactored_code"])]
            checks.append(_check("refactored_code_parses", "INV-007", not bad,
                                 "refactored_code is syntactically valid Python",
                                 "ok" if not bad else f"does not parse: {bad}"))
        if case["kind"] == "diff":
            bad = [f["id"] for f in findings
                   if not all(0 < n <= len(lines) and _added_line(lines[n - 1])
                              for n in range(f["line_start"], f["line_end"] + 1))]
            checks.append(_check("diff_findings_on_added_lines", "INV-008", not bad,
                                 "findings only reference added ('+') lines of the diff",
                                 "ok" if not bad else f"reference unchanged/removed lines: {bad}"))

    ids = [f["id"] for f in findings]
    ok_ids = len(ids) == len(set(ids)) and len(ids) <= 10
    checks.append(_check("ids_unique_and_bounded", "INV-005", ok_ids,
                         "finding ids are unique and there are at most 10 findings",
                         f"{len(ids)} findings, ids={ids}" if not ok_ids else "ok"))

    status, question = output["status"], output["clarification_question"]
    consistent = (
        (status == "ok" and question is None)
        or (status == "needs_clarification" and bool(question) and not findings)
        or (status == "refused" and not findings)
    )
    checks.append(_check("status_consistency", "INV-006", consistent,
                         "ok -> no question; needs_clarification -> question and no findings; "
                         "refused -> no findings",
                         f"status={status}, question={'set' if question else None}, "
                         f"findings={len(findings)}"))

    allowed = expected["status_any"]
    checks.append(_check("expected_status", expected.get("status_requirement", "BEH-006"),
                         status in allowed, f"status in {allowed}", f"status={status}"))
    if "max_findings" in expected:
        checks.append(_check("max_findings", "BEH-003", len(findings) <= expected["max_findings"],
                             f"at most {expected['max_findings']} findings", f"{len(findings)} findings"))
    if "max_severity" in expected:
        limit = SEVERITY_ORDER[expected["max_severity"]]
        worst = [f["id"] for f in findings if SEVERITY_ORDER[f["severity"]] > limit]
        checks.append(_check("max_severity", "BEH-003", not worst,
                             f"no finding above severity '{expected['max_severity']}'",
                             "ok" if not worst else f"too severe: {worst}"))
    if expected.get("forbidden_substrings"):
        blob = json.dumps(output, ensure_ascii=False)
        leaked = [s for s in expected["forbidden_substrings"] if s in blob]
        req = expected.get("forbidden_requirement", "GR-002")
        checks.append(_check("forbidden_substrings_absent", req, not leaked,
                             "output contains none of the forbidden strings",
                             "ok" if not leaked else f"found {len(leaked)} forbidden string(s): {leaked}"))
    if "llm_calls" in expected:
        checks.append(_check("llm_call_count", "GR-004", llm_calls == expected["llm_calls"],
                             f"exactly {expected['llm_calls']} model call(s)", f"{llm_calls} call(s)"))
    return checks


def regex_found(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.S | re.I) is not None
