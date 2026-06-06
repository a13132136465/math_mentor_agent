from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.coerce import as_float, as_int

from app.models.common import MongoBase, utcnow


# ── Embedded sub-models ───────────────────────────────────────────


class AnalysisResult(BaseModel):
    # ── Required core fields (match user-facing JSON schema) ──────
    topic: Literal["limits", "derivatives", "integrals"]
    subtopic: str
    difficulty: int = Field(ge=1, le=5, description="1=trivial … 5=very hard")
    recommended_method: str = Field(
        default="",
        description="Primary solution strategy the student should discover.",
    )
    key_observation: str = Field(
        default="",
        description=(
            "The one insight that unlocks the problem. "
            "Never revealed verbatim to the student — used to prime the Planner."
        ),
    )

    # ── Extended fields used by Planner / Teaching agents ─────────
    suggested_methods: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    ambiguity_note: str | None = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _coerce_difficulty(cls, v: object) -> int:
        return as_int(v, 3, 1, 5)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: object) -> float:
        f = as_float(v, 0.8)
        return max(0.0, min(1.0, f))

    # ── Derived helpers ───────────────────────────────────────────
    @property
    def difficulty_label(self) -> Literal["easy", "medium", "hard"]:
        """Map numeric 1-5 score to human label used in prompts."""
        d = as_int(self.difficulty, 3, 1, 5)
        if d <= 2:
            return "easy"
        if d <= 3:
            return "medium"
        return "hard"


class Milestone(BaseModel):
    id: int
    goal: str
    skills_required: list[str] = Field(default_factory=list)
    completed: bool = False
    completed_at: datetime | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> int:
        return as_int(v, 1, 1)


class ReasoningPlan(BaseModel):
    milestones: list[Milestone] = Field(default_factory=list)
    common_pitfalls: list[str] = Field(default_factory=list)
    estimated_turns: int = 6

    @field_validator("milestones", mode="before")
    @classmethod
    def _coerce_milestones(cls, v: object) -> list:
        if not isinstance(v, list):
            return []
        return [
            Milestone.model_validate(item)
            if isinstance(item, dict)
            else item
            for item in v
        ]

    @field_validator("estimated_turns", mode="before")
    @classmethod
    def _coerce_estimated_turns(cls, v: object) -> int:
        return as_int(v, 6, 1)


class SessionProgress(BaseModel):
    current_milestone: int = 0
    hint_level: int = Field(default=0, ge=0, le=3)

    @field_validator("current_milestone", "hint_level", mode="before")
    @classmethod
    def _coerce_progress_ints(cls, v: object) -> int:
        return as_int(v, 0, 0)
    solution_ready: bool = False
    turn_count: int = 0
    message_count: int = 0
    stuck_count: int = 0
    response_locale: str = "en"


class SessionSummary(BaseModel):
    milestones_completed: int = 0
    milestones_total: int = 0
    error_tags_this_session: list[str] = Field(default_factory=list)
    mastery_deltas: dict[str, float] = Field(default_factory=dict)
    peak_hint_level: int = 0
    duration_seconds: int = 0


class SessionFlags(BaseModel):
    degraded_mode: bool = False
    circuit_breaker: bool = False
    integrity_flagged: bool = False


# ── Main document model ───────────────────────────────────────────


class Session(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    student_id: str
    status: Literal["active", "completed", "abandoned", "paused"] = "active"
    phase: Literal[
        "intake", "analyzing", "tutoring", "validating", "wrap_up", "completed"
    ] = "intake"

    problem_text: str = Field(max_length=4000)

    # Analyzer output — safe for client
    analysis: AnalysisResult | None = None

    # INTERNAL — never exposed in client responses
    plan: ReasoningPlan | None = None

    progress: SessionProgress = Field(default_factory=SessionProgress)
    session_summary: SessionSummary | None = None
    flags: SessionFlags = Field(default_factory=SessionFlags)

    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow)


# ── API shapes ────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    problem_text: str = Field(min_length=5, max_length=4000)


class SessionResponse(BaseModel):
    """Client-safe session response — plan is excluded."""

    id: str
    status: str
    phase: str
    problem_text: str
    analysis: AnalysisResult | None
    progress: SessionProgress
    session_summary: SessionSummary | None
    flags: SessionFlags
    started_at: datetime
    ended_at: datetime | None

    @classmethod
    def from_session(cls, s: Session) -> "SessionResponse":
        return cls(
            id=s.id or "",
            status=s.status,
            phase=s.phase,
            problem_text=s.problem_text,
            analysis=s.analysis,
            progress=s.progress,
            session_summary=s.session_summary,
            flags=s.flags,
            started_at=s.started_at,
            ended_at=s.ended_at,
        )


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
