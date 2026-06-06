"""Golden evaluation: heuristic leak detector on curated cases."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.leak_heuristic import heuristic_leak_risk

CASES_PATH = Path(__file__).parent / "leak_cases.json"
LEAK_THRESHOLD = 0.55


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", json.loads(CASES_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_leaky_drafts_flagged(case: dict):
    risk = heuristic_leak_risk(case["leaky_draft"], case["student_message"])
    assert risk >= LEAK_THRESHOLD, f"Expected leak for {case['id']}, got {risk}"


@pytest.mark.parametrize("case", json.loads(CASES_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_safe_drafts_pass(case: dict):
    risk = heuristic_leak_risk(case["safe_draft"], case["student_message"])
    assert risk < LEAK_THRESHOLD, f"False positive for {case['id']}, got {risk}"
