from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import MongoBase, utcnow

EventType = Literal[
    "step_correct",
    "step_partially_correct",
    "step_incorrect",
    "step_unclear",
    "milestone_complete",
    "session_complete",
    "exercise_complete",
    "exercise_skipped",
]


class MasteryEventContext(BaseModel):
    milestone_id: int | None = None
    hint_level: int | None = None
    hint_penalty_applied: float | None = None
    error_tag: str | None = None


class MasteryEvent(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    student_id: str
    session_id: str
    attempt_id: str | None = None

    topic: Literal["limits", "derivatives", "integrals"]
    subtopic: str | None = None

    event_type: EventType
    delta: float
    score_after: float = Field(ge=0.0, le=1.0)

    context: MasteryEventContext = Field(default_factory=MasteryEventContext)

    created_at: datetime = Field(default_factory=utcnow)
