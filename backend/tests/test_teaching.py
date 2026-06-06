"""Unit tests for Teaching Agent leak-guard thresholds."""
from app.agents.teaching import LEAK_RISK_OVERRIDE, LEAK_RISK_REWRITE, MAX_REWRITES
from app.utils.leak_heuristic import heuristic_leak_risk


def test_leak_threshold_constants():
    assert LEAK_RISK_REWRITE < LEAK_RISK_OVERRIDE
    assert MAX_REWRITES >= 1


def test_heuristic_catches_answer_confirmation():
    draft = "Yes, that's exactly the derivative you need!"
    student = "Is my answer f'(x) = cos(x)/sin(x) complete?"
    assert heuristic_leak_risk(draft, student) >= 0.55


def test_heuristic_safe_socratic_question():
    draft = "What do you notice about the structure of the outer function?"
    assert heuristic_leak_risk(draft) < 0.55
