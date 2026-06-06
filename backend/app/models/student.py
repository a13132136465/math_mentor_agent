from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.coerce import as_float, as_int

from app.models.common import MongoBase, utcnow


# ── Sub-models ────────────────────────────────────────────────────


class TopicMastery(BaseModel):
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    attempts: int = 0
    last_practiced: datetime | None = None

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v: object) -> float:
        return max(0.0, min(1.0, as_float(v, 0.5)))

    @field_validator("attempts", mode="before")
    @classmethod
    def _coerce_attempts(cls, v: object) -> int:
        return as_int(v, 0, 0)


class MasterySnapshot(BaseModel):
    limits: TopicMastery = Field(default_factory=TopicMastery)
    derivatives: TopicMastery = Field(default_factory=TopicMastery)
    integrals: TopicMastery = Field(default_factory=TopicMastery)

    def get_score(self, topic: str) -> float:
        return as_float(getattr(self, topic).score, 0.5)

    def set_score(self, topic: str, score: float) -> None:
        getattr(self, topic).score = round(max(0.0, min(1.0, score)), 4)


class ErrorPattern(BaseModel):
    tag: str
    count: int = 1
    last_seen: datetime = Field(default_factory=utcnow)


class StudentPreferences(BaseModel):
    hint_style: Literal["gentle", "balanced", "challenging"] = "balanced"
    latex_enabled: bool = True
    notify_exercises: bool = True
    llm_provider: Literal["gemini", "deepseek"] = "gemini"
    locale: Literal["en", "zh"] = "en"


class StudentStats(BaseModel):
    total_sessions: int = 0
    total_steps_submitted: int = 0
    total_exercises_done: int = 0
    streak_days: int = 0
    last_active_at: datetime | None = None


# ── Main document model ───────────────────────────────────────────


class Student(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    auth_sub: str
    email: str
    display_name: str
    avatar_url: str | None = None

    preferences: StudentPreferences = Field(default_factory=StudentPreferences)
    mastery: MasterySnapshot = Field(default_factory=MasterySnapshot)
    error_patterns: list[ErrorPattern] = Field(default_factory=list)
    stats: StudentStats = Field(default_factory=StudentStats)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ── API Request / Response shapes ────────────────────────────────


class StudentProfileResponse(BaseModel):
    id: str
    display_name: str
    email: str
    avatar_url: str | None
    preferences: StudentPreferences
    mastery: MasterySnapshot
    error_patterns: list[ErrorPattern]
    stats: StudentStats

    @classmethod
    def from_student(cls, s: Student) -> "StudentProfileResponse":
        return cls(
            id=s.id or "",
            display_name=s.display_name,
            email=s.email,
            avatar_url=s.avatar_url,
            preferences=s.preferences,
            mastery=s.mastery,
            error_patterns=s.error_patterns,
            stats=s.stats,
        )


class UpdatePreferencesRequest(BaseModel):
    hint_style: Literal["gentle", "balanced", "challenging"] | None = None
    latex_enabled: bool | None = None
    notify_exercises: bool | None = None
    llm_provider: Literal["gemini", "deepseek"] | None = None
    locale: Literal["en", "zh"] | None = None


class MasteryHistoryPoint(BaseModel):
    score_after: float
    delta: float
    event_type: str
    subtopic: str | None = None
    created_at: datetime


class MasteryHistoryResponse(BaseModel):
    limits: list[MasteryHistoryPoint] = Field(default_factory=list)
    derivatives: list[MasteryHistoryPoint] = Field(default_factory=list)
    integrals: list[MasteryHistoryPoint] = Field(default_factory=list)
