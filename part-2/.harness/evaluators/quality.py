"""Layer 3: semantic / quality evaluation against ground truth (BEH-001, 002, 004, 005, 007).

Heuristic, ground-truth based and fully deterministic: an issue is 'detected' when a
finding has an acceptable category and its line range overlaps the labelled range
(plus tolerance). No LLM judge is used, so these scores are reproducible.
"""
from __future__ import annotations

from .common import SEVERITY_ORDER, Check, norm_ws
from .invariants import regex_found


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def match_issues(case: dict, output: dict) -> list[dict]:
    """One-to-one greedy match of labelled issues to findings."""
    findings = output.get("findings", []) if isinstance(output, dict) else []
    used: set[int] = set()
    results = []
    for issue in case["expected"].get("issues", []):
        low, high = issue["lines"]
        tolerance = issue.get("line_tolerance", 1)
        hit = None
        for index, finding in enumerate(findings):
            if index in used:
                continue
            if finding["category"] in issue["categories_any"] and _overlap(
                finding["line_start"], finding["line_end"], low - tolerance, high + tolerance
            ):
                hit = index
                break
        if hit is not None:
            used.add(hit)
        results.append({"issue_id": issue["id"], "finding_index": hit,
                        "finding_id": findings[hit]["id"] if hit is not None else None})
    return results


def semantic_checks(case: dict, output: dict) -> list[Check]:
    checks: list[Check] = []
    findings = output.get("findings", [])
    for issue, match in zip(case["expected"].get("issues", []), match_issues(case, output)):
        finding = findings[match["finding_index"]] if match["finding_index"] is not None else None
        label = issue["id"]

        def add(name: str, req: str, passed: bool, expected: str, observed: str, label=label) -> None:
            checks.append(Check("semantic", name, req, passed, f"[{label}] {expected}", observed))

        lo, hi = issue["lines"]
        add("issue_detected", "BEH-001", finding is not None,
            f"a finding in {issue['categories_any']} overlapping lines {lo}-{hi} "
            f"(tolerance {issue.get('line_tolerance', 1)})",
            "detected" if finding else f"missed; findings were "
            f"{[(f['category'], f['line_start'], f['line_end']) for f in findings]}")
        missed = "issue not detected"

        if "min_severity" in issue:
            ok = finding is not None and SEVERITY_ORDER[finding["severity"]] >= SEVERITY_ORDER[issue["min_severity"]]
            add("severity_floor", "BEH-002", ok, f"severity >= {issue['min_severity']}",
                f"severity={finding['severity']}" if finding else missed)
        if issue.get("rationale_keywords_any"):
            text = (finding["rationale"] + " " + finding["title"]).lower() if finding else ""
            ok = any(k.lower() in text for k in issue["rationale_keywords_any"])
            add("rationale_mentions_concept", "BEH-005", ok,
                f"rationale/title mentions one of {issue['rationale_keywords_any']}",
                "ok" if ok else (missed if not finding else f"rationale was: {finding['rationale'][:160]!r}"))
        if issue.get("refactor_regex"):
            code = (finding["suggestion"]["refactored_code"] or "") if finding else ""
            good = bool(code) and regex_found(issue["refactor_regex"], code)
            bad = bool(code) and issue.get("refactor_forbidden_regex") and regex_found(
                issue["refactor_forbidden_regex"], code)
            add("refactor_addresses_issue", "BEH-004", good and not bad,
                f"refactored_code matches /{issue['refactor_regex']}/"
                + (f" and not /{issue['refactor_forbidden_regex']}/" if issue.get("refactor_forbidden_regex") else ""),
                missed if not finding else (f"refactored_code was: {code[:200]!r}" if code else "refactored_code is null/empty"))
        if finding is not None:
            code = finding["suggestion"]["refactored_code"]
            noop = bool(code) and norm_ws(code) == norm_ws(finding["evidence"])
            add("suggestion_is_substantive", "BEH-007", not noop,
                "suggestion exists and refactored_code is not a copy of the evidence",
                "ok" if not noop else "refactored_code equals the evidence")
        else:
            add("suggestion_is_substantive", "BEH-007", False, "a suggestion for the detected issue", missed)
    return checks
