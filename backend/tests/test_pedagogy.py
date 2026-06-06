"""Pedagogy helpers — no raw plan goals in teaching prompts."""
from app.utils.pedagogy import milestone_focus_for_teaching, pitfall_label


def test_milestone_focus_uses_skills_not_solution():
    focus = milestone_focus_for_teaching(
        topic="derivatives",
        subtopic="chain_rule",
        skills=["chain_rule", "derivative_of_trig"],
    )
    assert "chain_rule" in focus
    assert "final answer" in focus.lower()


def test_pitfall_label_truncates_long_text():
    long_pitfall = "x" * 120
    assert pitfall_label(long_pitfall) == "a common mistake in this problem type"
