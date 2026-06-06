"""Unit tests for StudentModelAgent mastery updates."""
from app.agents.student_model import StudentModelAgent
from app.models.student import MasterySnapshot


def test_mastery_increases_on_correct():
    agent = StudentModelAgent(gemini=None)  # type: ignore[arg-type]
    mastery = MasterySnapshot()
    out = agent.apply_mastery_update(
        mastery=mastery,
        topic="derivatives",
        verdict="correct",
        hint_level=0,
        error_tag=None,
        error_patterns=[],
    )
    assert out.updated_mastery.derivatives.score > 0.5
    assert out.mastery_deltas["derivatives"] > 0


def test_hint_penalty_reduces_credit():
    agent = StudentModelAgent(gemini=None)  # type: ignore[arg-type]
    mastery = MasterySnapshot()
    no_hint = agent.apply_mastery_update(
        mastery=mastery,
        topic="derivatives",
        verdict="correct",
        hint_level=0,
        error_tag=None,
        error_patterns=[],
    )
    with_hint = agent.apply_mastery_update(
        mastery=mastery,
        topic="derivatives",
        verdict="correct",
        hint_level=3,
        error_tag=None,
        error_patterns=[],
    )
    assert with_hint.mastery_deltas["derivatives"] < no_hint.mastery_deltas["derivatives"]


def test_error_pattern_accumulation():
    agent = StudentModelAgent(gemini=None)  # type: ignore[arg-type]
    mastery = MasterySnapshot()
    out = agent.apply_mastery_update(
        mastery=mastery,
        topic="derivatives",
        verdict="incorrect",
        hint_level=1,
        error_tag="missing_chain_rule_factor",
        error_patterns=["missing_chain_rule_factor", "missing_chain_rule_factor"],
    )
    assert out.updated_error_patterns.count("missing_chain_rule_factor") == 3
    assert out.recommended_hint_level >= 2
