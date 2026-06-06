"""Sanitized pedagogical hints — never expose ReasoningPlan milestone goals to Teaching LLM."""
from __future__ import annotations


def milestone_focus_for_teaching(
    *,
    topic: str,
    subtopic: str,
    skills: list[str],
) -> str:
    """Internal focus string for Teaching assessment — no solution steps."""
    skill_text = ", ".join(skills) if skills else subtopic
    return (
        f"Help the student discover the next step using skills: {skill_text} "
        f"({topic}). Do not state the target expression or final answer."
    )


def pitfall_label(pitfall: str | None) -> str:
    if not pitfall:
        return "common algebraic errors"
    if len(pitfall) > 80:
        return "a common mistake in this problem type"
    return pitfall
