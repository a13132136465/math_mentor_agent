"""Orchestrator routing helpers — stuck detection and trace routes."""
from app.agents.orchestrator import OrchestratorAgent, STUCK_PHRASES
from app.models.agent import SessionContext
from app.models.session import AnalysisResult
from app.models.student import MasterySnapshot


def _ctx(**kwargs) -> SessionContext:
    base = dict(
        session_id="s1",
        student_id="st1",
        display_name="Test",
        mastery=MasterySnapshot(),
        problem_text="Find derivative",
    )
    base.update(kwargs)
    return SessionContext(**base)


def test_message_signals_stuck_english():
    assert OrchestratorAgent._message_signals_stuck("I'm stuck on this step")
    assert OrchestratorAgent._message_signals_stuck("Can I get a hint?")


def test_message_signals_stuck_chinese():
    assert OrchestratorAgent._message_signals_stuck("我卡住了")


def test_message_signals_stuck_negative():
    assert not OrchestratorAgent._message_signals_stuck("Let u = sin x")


def test_fast_route_stuck_returns_teaching():
    ctx = _ctx(
        phase="tutoring",
        analysis=AnalysisResult(
            topic="derivatives",
            subtopic="chain_rule",
            difficulty=3,
            recommended_method="chain_rule",
            key_observation="composition",
            suggested_methods=["chain_rule"],
            prerequisites=[],
            confidence=0.9,
        ),
    )
    route = OrchestratorAgent._fast_route(ctx, "I need a hint")
    assert route == "teaching"


def test_stuck_phrases_tuple_non_empty():
    assert "stuck" in STUCK_PHRASES


def test_should_auto_practice_on_final_milestone():
    from app.models.session import Milestone, ReasoningPlan

    ctx = _ctx(
        phase="tutoring",
        current_milestone=2,
        plan=ReasoningPlan(
            milestones=[
                Milestone(id=1, goal="a", skills_required=[]),
                Milestone(id=2, goal="b", skills_required=[]),
                Milestone(id=3, goal="c", skills_required=[]),
            ],
            common_pitfalls=[],
            estimated_turns=6,
        ),
    )
    assert OrchestratorAgent._should_auto_practice(ctx, {"milestone_advanced": True})
    assert not OrchestratorAgent._should_auto_practice(ctx, {"milestone_advanced": False})
