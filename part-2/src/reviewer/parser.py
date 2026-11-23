"""Extract one JSON object from a model reply (INV-001; research.md R3)."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```[A-Za-z]*[ \t]*\n?(.*?)```", re.DOTALL)


def _load_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _scan_for_object(text: str) -> dict[str, Any] | None:
    """Decode from each ``{`` in turn and return the first complete JSON object."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    return None


def extract_json(text: str) -> dict[str, Any]:
    """Return the JSON object in ``text``, tolerating code fences and surrounding prose.

    Raises ``ValueError`` when no JSON object is present (a JSON list does not count).
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("the model reply is empty")
    candidates = [text.strip(), *(m.group(1).strip() for m in _FENCE.finditer(text))]
    for candidate in candidates:
        value = _load_object(candidate)
        if value is not None:
            return value
    for candidate in candidates:
        value = _scan_for_object(candidate)
        if value is not None:
            return value
    raise ValueError("no JSON object found in the model reply")
