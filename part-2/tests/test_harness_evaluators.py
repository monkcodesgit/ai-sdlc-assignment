"""Self-tests of the harness: do the independent evaluators catch what they claim to catch?

If these fail the HARNESS is wrong, not the application. They run with no model at all.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluators import (
    match_issues,
    property_checks,
    semantic_checks,
    structural_checks,
    validate_output,
)
from stub_client import ideal_output

DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset.json"
CASES = {c["id"]: c for c in json.loads(DATASET.read_text(encoding="utf-8"))["cases"]}


def _failed(checks):
    return {c.name for c in checks if not c.passed}


def _all(case_id, output, calls=1):
    case = CASES[case_id]
    checks = structural_checks(output, None)
    if not _failed(checks):
        checks += property_checks(case, output, calls) + semantic_checks(case, output)
    return checks


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_harness_reference_answers_pass_every_layer(case_id):
    case = CASES[case_id]
    calls = case["expected"].get("llm_calls", 1)
    bad = [c for c in _all(case_id, ideal_output(case), calls) if not c.passed]
    assert not bad, [c.to_dict() for c in bad]


def _good():
    return copy.deepcopy(ideal_output(CASES["N01"]))


@pytest.mark.parametrize("mutate, fragment", [
    (lambda o: o.pop("summary"), "missing keys"),
    (lambda o: o.update(extra=1), "unknown keys"),
    (lambda o: o.update(status="maybe"), "status"),
    (lambda o: o["findings"][0].update(line_start=True), "line_start"),
    (lambda o: o["findings"][0].update(category="style"), "category"),
    (lambda o: o["findings"][0].update(severity="urgent"), "severity"),
    (lambda o: o["findings"][0].update(line_start=9, line_end=2), "line_end"),
    (lambda o: o["findings"][0].update(rationale="too short"), "rationale"),
    (lambda o: o["findings"][0].update(confidence=1.5), "confidence"),
    (lambda o: o["findings"][0].update(id="X1"), "id"),
    (lambda o: o["findings"][0]["suggestion"].pop("refactored_code"), "missing keys"),
    (lambda o: o.update(findings="oops"), "array"),
])
def test_harness_schema_rejects_violations(mutate, fragment):
    output = _good()
    mutate(output)
    errors = validate_output(output)
    assert errors and any(fragment in e for e in errors), errors


def test_harness_non_object_output_fails_structural_layer():
    assert _failed(structural_checks(None, "ModelOutputError: bad")) == {
        "output_is_json_object", "schema_conformance"}


def test_harness_detects_out_of_range_lines_and_hallucinated_evidence():
    output = _good()
    output["findings"][0].update(line_start=99, line_end=99, evidence="not in the input")
    assert {"line_ranges_in_bounds", "evidence_is_verbatim"} <= _failed(_all("N01", output))


def test_harness_accepts_redacted_evidence_and_whitespace_differences():
    output = ideal_output(CASES["G02"])
    assert not _failed(_all("G02", output))
    spaced = _good()
    original = spaced["findings"][0]["evidence"]
    spaced["findings"][0]["evidence"] = original.replace("SELECT * FROM", "SELECT   *\n   FROM")
    assert "evidence_is_verbatim" not in _failed(_all("N01", spaced))


def test_harness_detects_duplicate_ids_and_status_inconsistency():
    output = _good()
    output["findings"].append(copy.deepcopy(output["findings"][0]))
    assert "ids_unique_and_bounded" in _failed(_all("N01", output))
    clarify = {"status": "needs_clarification", "summary": "Need code.",
               "clarification_question": None, "findings": []}
    assert "status_consistency" in _failed(_all("M03", clarify))


def test_harness_detects_unparsable_refactored_code():
    output = _good()
    output["findings"][0]["suggestion"]["refactored_code"] = "def broken(:\n"
    assert "refactored_code_parses" in _failed(_all("N01", output))


def test_harness_detects_diff_findings_on_unchanged_or_removed_lines():
    output = ideal_output(CASES["B03"])
    assert not _failed(_all("B03", output))
    output["findings"][0].update(line_start=7, line_end=7)       # the removed (-) line
    assert "diff_findings_on_added_lines" in _failed(_all("B03", output))
    output["findings"][0].update(line_start=4, line_end=4)       # unchanged context line
    assert "diff_findings_on_added_lines" in _failed(_all("B03", output))


def test_harness_detects_leaks_wrong_status_and_call_counts():
    output = ideal_output(CASES["G02"])
    output["findings"][0]["evidence"] = CASES["G02"]["input"].splitlines()[2]
    assert "forbidden_substrings_absent" in _failed(_all("G02", output))
    ok = {"status": "needs_clarification", "summary": "Need code.",
          "clarification_question": "Which code?", "findings": []}
    assert "llm_call_count" in _failed(_all("M01", ok, calls=1))
    wrong_status = {**ok, "status": "ok", "clarification_question": None}
    assert "expected_status" in _failed(_all("G03", wrong_status))


def test_harness_clean_code_false_positives_are_penalised():
    noisy = ideal_output(CASES["B04"])
    noisy["findings"] = [dict(_good()["findings"][0], severity="high", id=f"F{i}") for i in (1, 2)]
    assert {"max_findings", "max_severity"} <= _failed(_all("B04", noisy))


def test_harness_semantic_layer_detects_missed_wrong_and_weak_findings():
    case = CASES["N01"]
    assert "issue_detected" in _failed(_all("N01", {**_good(), "findings": []}))
    wrong_cat = _good()
    wrong_cat["findings"][0]["category"] = "performance"
    assert "issue_detected" in _failed(_all("N01", wrong_cat))
    wrong_line = _good()
    wrong_line["findings"][0].update(line_start=1, line_end=1)
    assert "issue_detected" in _failed(_all("N01", wrong_line))
    weak = _good()
    weak["findings"][0].update(severity="low", title="Something looks odd here",
                               rationale="Something about this line looks odd to me.")
    weak["findings"][0]["suggestion"]["refactored_code"] = 'cursor.execute(f"SELECT {username}")'
    assert {"severity_floor", "rationale_mentions_concept", "refactor_addresses_issue"} <= _failed(
        _all("N01", weak))
    assert match_issues(case, _good())[0]["finding_id"] == "F1"


def test_harness_matching_is_one_to_one():
    case = CASES["N05"]
    output = ideal_output(case)
    output["findings"] = [output["findings"][0]]            # only the eval issue reported
    matches = match_issues(case, output)
    assert [m["finding_index"] is not None for m in matches] == [True, False]
