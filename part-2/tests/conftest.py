"""Shared fixtures: a scripted fake model so application behaviour is tested deterministically."""
from __future__ import annotations

import json

import pytest


class FakeLLM:
    """Returns scripted replies in order; an Exception instance in the script is raised."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def describe(self) -> dict:
        return {"provider": "fake", "model": "fake-1", "temperature": 0.0}


@pytest.fixture
def make_llm():
    return FakeLLM


def finding(fid="F1", line=1, **overrides):
    item = {
        "id": fid, "category": "bug", "severity": "medium", "line_start": line, "line_end": line,
        "title": "Example finding", "evidence": "x = 1",
        "rationale": "This is an example rationale for the finding.",
        "suggestion": {"summary": "Do the example refactoring instead.", "refactored_code": None},
        "confidence": 0.8,
    }
    item.update(overrides)
    return item


def reply(findings=None, status="ok", question=None, summary="Reviewed the code."):
    return json.dumps({"status": status, "summary": summary, "clarification_question": question,
                       "findings": findings or []})
