from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.dependencies import CurrentUser, get_mastery_event_repo, get_student_repo
from app.models.student import (
    MasteryHistoryPoint,
    MasteryHistoryResponse,
    StudentProfileResponse,
    UpdatePreferencesRequest,
)
from app.repositories import MasteryEventRepository, StudentRepository
from app.services.llm_factory import SUPPORTED_LLM_PROVIDERS

_TOPICS = ("limits", "derivatives", "integrals")

router = APIRouter(prefix="/me", tags=["profile"])


@router.get("", response_model=StudentProfileResponse)
async def get_profile(
    user: CurrentUser,
    students: StudentRepository = Depends(get_student_repo),
):
    doc = await students.get_by_id(user.sub)
    if not doc:
        raise HTTPException(status_code=404, detail="Student profile not found")
    from app.models.student import Student
    doc = dict(doc)
    doc["_id"] = str(doc.get("_id", ""))
    student = Student(**doc)
    return StudentProfileResponse.from_student(student)


@router.patch("/preferences", response_model=StudentProfileResponse)
async def update_preferences(
    body: UpdatePreferencesRequest,
    user: CurrentUser,
    students: StudentRepository = Depends(get_student_repo),
):
    updates = body.model_dump(exclude_none=True)
    if updates:
        await students.update_preferences(user.sub, updates)

    doc = await students.get_by_id(user.sub)
    doc = dict(doc)
    doc["_id"] = str(doc.get("_id", ""))
    from app.models.student import Student
    return StudentProfileResponse.from_student(Student(**doc))


@router.get("/mastery/history", response_model=MasteryHistoryResponse)
async def get_mastery_history(
    user: CurrentUser,
    mastery_events: MasteryEventRepository = Depends(get_mastery_event_repo),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return per-topic mastery score timeline for dashboard charts."""
    result: dict[str, list[MasteryHistoryPoint]] = {}
    for topic in _TOPICS:
        events = await mastery_events.get_topic_history(user.sub, topic, limit=limit)
        points = [
            MasteryHistoryPoint(
                score_after=ev.get("score_after", 0.5),
                delta=ev.get("delta", 0.0),
                event_type=ev.get("event_type", "unknown"),
                subtopic=ev.get("subtopic"),
                created_at=ev.get("created_at"),
            )
            for ev in reversed(events)
        ]
        result[topic] = points
    return MasteryHistoryResponse(**result)


@router.get("/llm-providers")
async def list_llm_providers():
    settings = get_settings()
    labels = {"gemini": "Google Gemini", "deepseek": "DeepSeek"}
    return {
        "providers": [
            {
                "id": provider,
                "label": labels.get(provider, provider),
                "available": provider != "deepseek" or bool(settings.deepseek_api_key),
            }
            for provider in SUPPORTED_LLM_PROVIDERS
        ]
    }
