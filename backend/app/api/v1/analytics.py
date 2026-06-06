"""
GET /v1/me/analytics — Learning Analytics Agent endpoint.

Returns a full learning profile for the authenticated student:
  strengths, weaknesses, mastery_scores, recommended_next_topic,
  recommended_subtopic, error_summary, learning_tip, confidence.

The response is NOT cached — it is computed fresh on each request
so it always reflects the latest mastery and error data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.analytics import AnalyticsAgent
from app.dependencies import (
    CurrentUser,
    get_attempt_repo,
    get_llm_for_current_user,
    get_student_repo,
)
from app.services.llm_protocol import LLMService
from app.models.agent import LearningAnalyticsOutput
from app.repositories.attempts import AttemptRepository
from app.repositories.students import StudentRepository
from app.models.student import (
    ErrorPattern,
    MasterySnapshot,
    StudentStats,
)
from app.utils.locale import default_learning_tip, normalize_locale, resolve_locale

router = APIRouter(prefix="/me", tags=["analytics"])


@router.get(
    "/analytics",
    response_model=LearningAnalyticsOutput,
    summary="Get personalised learning analytics",
    description=(
        "Runs the Learning Analytics Agent against the current student's "
        "mastery snapshot, error history, and recent attempts. "
        "Returns strengths, weaknesses, recommended next topic, and a "
        "personalised learning tip."
    ),
)
async def get_analytics(
    user: CurrentUser,
    students: StudentRepository = Depends(get_student_repo),
    attempts: AttemptRepository = Depends(get_attempt_repo),
    llm: LLMService = Depends(get_llm_for_current_user),
) -> LearningAnalyticsOutput:
    # ── Load student profile ──────────────────────────────────────
    student_doc = await students.get_by_id(user.sub)
    if not student_doc:
        return LearningAnalyticsOutput(
            strengths=[],
            weaknesses=[],
            mastery_scores={"limits": 0.5, "derivatives": 0.5, "integrals": 0.5},
            recommended_next_topic="limits",
            recommended_subtopic="one_sided",
            learning_tip=default_learning_tip("en"),
            confidence=0.5,
            deterministic_only=True,
        )

    locale = normalize_locale(student_doc.get("preferences", {}).get("locale"))

    mastery = MasterySnapshot(**student_doc.get("mastery", {}))
    stats = StudentStats(**student_doc.get("stats", {}))
    error_patterns = [
        ErrorPattern(**ep) for ep in student_doc.get("error_patterns", [])
    ]

    # ── Load recent attempts (cross-session) ──────────────────────
    student_id = str(student_doc["_id"])
    recent_attempts = await attempts.get_recent_for_student(student_id, limit=50)

    recent_msgs = [
        a.get("content", "")
        for a in recent_attempts
        if a.get("content")
    ]
    response_locale = resolve_locale(*recent_msgs[-5:], ui_locale=locale)

    # ── Run agent ─────────────────────────────────────────────────
    agent = AnalyticsAgent(llm)
    return await agent.run(
        mastery=mastery,
        error_patterns=error_patterns,
        stats=stats,
        recent_attempts=recent_attempts,
        response_locale=response_locale,
    )
