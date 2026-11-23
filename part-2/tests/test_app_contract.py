"""Deterministic application contract tests (no real model). Names carry spec requirement ids."""
from __future__ import annotations

import json

import pytest
from conftest import finding, reply

from evaluators import validate_output
from reviewer.errors import LLMServiceError, ModelOutputError
from reviewer.service import review_code

SECRET = "sk-FAKE-0000-1111-2222-3333"


@pytest.mark.parametrize("code", ["", "   \n\t  \n", "x = 1\x00"])
def test_gr_004_empty_whitespace_and_nul_input_never_call_the_model(make_llm, code):
    llm = make_llm([])
    result = review_code(code, client=llm)
    assert llm.calls == [], "the model must not be called for unreviewable input"
    assert result["status"] == "needs_clarification"
    assert result["findings"] == []
    assert validate_output(result) == []


def test_fr_006_oversize_input_is_refused_without_a_model_call(make_llm):
    llm = make_llm([])
    result = review_code("x = 1\n" * 3334, client=llm)
    assert llm.calls == []
    assert result["status"] == "refused"
    assert result["findings"] == [] and result["clarification_question"] is None
    assert validate_output(result) == []


def test_fr_006_input_exactly_at_the_limit_is_sent_to_the_model(make_llm):
    llm = make_llm([reply()])
    result = review_code(("x = 1\n" * 3334)[:20000], client=llm)
    assert len(llm.calls) == 1
    assert result["status"] == "ok"


def test_fr_001_invalid_kind_is_rejected(make_llm):
    with pytest.raises(ValueError):
        review_code("x = 1", kind="patch", client=make_llm([]))


def test_fr_005_non_python_language_needs_clarification_without_a_model_call(make_llm):
    llm = make_llm([])
    result = review_code("console.log(1)", language="javascript", client=llm)
    assert llm.calls == []
    assert result["status"] == "needs_clarification"
    assert validate_output(result) == []


def test_fr_004_prompt_numbers_lines_and_marks_diffs(make_llm):
    llm = make_llm([reply(), reply()])
    review_code("import os\nx = 1\n", client=llm)
    user_prompt = llm.calls[0][1]
    assert "1: import os" in user_prompt and "2: x = 1" in user_prompt
    review_code("+x = 1\n", kind="diff", client=llm)
    assert "diff" in (llm.calls[1][0] + llm.calls[1][1]).lower()


def test_inv_001_json_inside_a_code_fence_is_extracted(make_llm):
    llm = make_llm(["```json\n" + reply([finding()]) + "\n```"])
    assert review_code("x = 1", client=llm)["findings"][0]["id"] == "F1"


def test_inv_001_json_surrounded_by_prose_is_extracted(make_llm):
    llm = make_llm(["Here is my review:\n" + reply([finding()]) + "\nHope that helps!"])
    assert review_code("x = 1", client=llm)["status"] == "ok"


def test_inv_001_invalid_json_is_retried_once_then_succeeds(make_llm):
    llm = make_llm(["not json at all", reply()])
    assert review_code("x = 1", client=llm)["status"] == "ok"
    assert len(llm.calls) == 2


def test_inv_001_persistently_invalid_json_raises_model_output_error(make_llm):
    llm = make_llm(["not json", "[1, 2]"])
    with pytest.raises(ModelOutputError):
        review_code("x = 1", client=llm)
    assert len(llm.calls) == 2


def test_inv_002_malformed_model_json_is_returned_as_is_without_crashing(make_llm):
    llm = make_llm(['{"status": "ok", "findings": "oops"}'])
    assert review_code("x = 1", client=llm) == {"status": "ok", "findings": "oops"}


def test_sch_001_valid_model_output_passes_through_unchanged(make_llm):
    expected = json.loads(reply([finding("F1", 1), finding("F2", 1)]))
    assert review_code("x = 1", client=make_llm([json.dumps(expected)])) == expected


def test_inv_005_duplicate_ids_are_renumbered_and_extra_findings_truncated(make_llm):
    llm = make_llm([reply([finding("F1") for _ in range(12)])])
    result = review_code("x = 1", client=llm)
    assert [f["id"] for f in result["findings"]] == [f"F{i}" for i in range(1, 11)]


def test_gr_002_secrets_are_redacted_from_every_string_in_the_output(make_llm):
    leaky = finding(
        title=f"Key {SECRET} exposed", evidence=f'API_KEY = "{SECRET}"',
        rationale="The AWS key AKIAABCDEFGHIJKLMNOP is committed to source control.",
        suggestion={"summary": f"Remove {SECRET} from the repository.",
                    "refactored_code": 'password = "hunter2hunter2"'},
    )
    result = review_code("x = 1", client=make_llm([reply([leaky], summary=f"Found {SECRET}")]))
    blob = json.dumps(result)
    for secret in (SECRET, "AKIAABCDEFGHIJKLMNOP", "hunter2hunter2"):
        assert secret not in blob
    assert "[REDACTED]" in blob


def test_eval_005_service_errors_propagate_without_a_retry(make_llm):
    llm = make_llm([LLMServiceError("provider unavailable")])
    with pytest.raises(LLMServiceError):
        review_code("x = 1", client=llm)
    assert len(llm.calls) == 1
