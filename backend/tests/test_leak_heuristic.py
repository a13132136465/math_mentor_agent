"""Unit tests for deterministic leak heuristics."""
from app.utils.leak_heuristic import heuristic_leak_risk


def test_detects_affirmation_leak():
    draft = "You've nailed the derivative — it's correct!"
    assert heuristic_leak_risk(draft) >= 0.55


def test_detects_completeness_confirmation():
    student = "Is that the full derivative?"
    draft = "Yes, that's the full derivative: f'(x) = cos(x^2+1)*2x."
    assert heuristic_leak_risk(draft, student) >= 0.75


def test_safe_socratic_reply_low_risk():
    draft = "What rule connects the outer and inner functions here?"
    assert heuristic_leak_risk(draft) < 0.55


def test_detects_exactly_the_derivative_on_completeness_question():
    student = "Is that the full derivative?"
    draft = "That's exactly the derivative of sin(x^2+1)."
    assert heuristic_leak_risk(draft, student) >= 0.75
