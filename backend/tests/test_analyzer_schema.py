"""Schema validation tests for Analyzer output models."""
from app.models.session import AnalysisResult, Milestone, ReasoningPlan


def test_analysis_result_valid():
    result = AnalysisResult(
        topic="derivatives",
        subtopic="chain_rule",
        difficulty=3,
        recommended_method="chain_rule",
        key_observation="Composition of ln and sin",
        suggested_methods=["chain_rule"],
        prerequisites=["derivative_of_ln"],
        confidence=0.95,
    )
    assert result.topic == "derivatives"
    assert result.difficulty == 3


def test_analysis_difficulty_coerced_to_valid_range():
    result = AnalysisResult(
        topic="derivatives",
        subtopic="chain_rule",
        difficulty=6,
        recommended_method="chain_rule",
        key_observation="x",
        suggested_methods=[],
        prerequisites=[],
        confidence=0.5,
    )
    assert 1 <= result.difficulty <= 5


def test_reasoning_plan_milestones():
    plan = ReasoningPlan(
        milestones=[
            Milestone(id=1, goal="Identify outer function", skills_required=["decomposition"]),
            Milestone(id=2, goal="Apply chain rule", skills_required=["chain_rule"]),
        ],
        common_pitfalls=["Forgetting inner derivative"],
        estimated_turns=6,
    )
    assert len(plan.milestones) == 2
    assert plan.estimated_turns == 6
