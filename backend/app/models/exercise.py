from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import MongoBase, utcnow


class ExerciseProblem(BaseModel):
    """Full exercise problem record — stored in MongoDB, includes answer."""
    id: str
    prompt: str
    topic: Literal["limits", "derivatives", "integrals"]
    subtopic: str
    difficulty: int = Field(default=3, ge=1, le=5, description="1=trivial … 5=very hard")
    target_skill: str = ""
    learning_intention: str = ""
    source_problem_id: str | None = None

    # ── Answer — INTERNAL only, never returned to the student in ──
    # ── the normal exercise flow. Revealed after completion only. ──
    answer: str = Field(
        default="",
        description=(
            "Full worked answer. Stored server-side. "
            "NOT included in student-facing GET responses. "
            "Available via GET /exercises/{id}/problems/{pid}/answer "
            "after the problem is marked completed or skipped."
        ),
    )

    status: Literal["pending", "attempted", "completed", "skipped"] = "pending"
    student_answer: str | None = None
    completed_at: datetime | None = None

    @property
    def difficulty_label(self) -> Literal["easy", "medium", "hard"]:
        """Human label — for prompts and display."""
        if self.difficulty <= 2:
            return "easy"
        if self.difficulty <= 3:
            return "medium"
        return "hard"


class ExerciseProblemPublic(BaseModel):
    """
    Student-facing view of an exercise problem.
    `answer` is deliberately excluded to prevent spoilers.
    """
    id: str
    prompt: str
    topic: str
    subtopic: str
    difficulty: int
    target_skill: str
    learning_intention: str
    status: str
    student_answer: str | None
    completed_at: datetime | None

    @classmethod
    def from_problem(cls, p: ExerciseProblem) -> "ExerciseProblemPublic":
        return cls(
            id=p.id,
            prompt=p.prompt,
            topic=p.topic,
            subtopic=p.subtopic,
            difficulty=p.difficulty,
            target_skill=p.target_skill,
            learning_intention=p.learning_intention,
            status=p.status,
            student_answer=p.student_answer,
            completed_at=p.completed_at,
        )


class GenerationMeta(BaseModel):
    model_used: str = ""
    rationale: str = ""
    weak_subtopics: list[str] = Field(default_factory=list)
    source: Literal["generated", "problem_library", "fallback"] = "generated"
    latency_ms: int = 0


class SpacedRepetition(BaseModel):
    due_at: datetime = Field(default_factory=utcnow)
    interval_hours: int = 24
    repetition_number: int = 1


class Exercise(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    student_id: str
    session_id: str
    status: Literal["pending", "in_progress", "completed", "expired"] = "pending"

    generation_meta: GenerationMeta = Field(default_factory=GenerationMeta)
    problems: list[ExerciseProblem] = Field(default_factory=list)
    spaced_repetition: SpacedRepetition = Field(default_factory=SpacedRepetition)

    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    expires_at: datetime = Field(
        default_factory=lambda: utcnow() + timedelta(days=180)
    )


# ── API request / response shapes ─────────────────────────────────


class SingleExerciseRequest(BaseModel):
    """Optional body for POST /exercises/single."""
    topic: Literal["limits", "derivatives", "integrals"] | None = Field(
        default=None,
        description="Override the auto-selected topic.",
    )
    focus_weakness: bool = Field(
        default=True,
        description="When True, use mastery scores to target the weakest area.",
    )


class SingleExerciseResponse(BaseModel):
    """
    Response for POST /exercises/single.

    `answer` is included here because the student explicitly requested
    a single practice problem and will self-check after solving.
    The front-end must hide it behind a 'Show answer' toggle.
    """
    problem: str = Field(description="The exercise prompt (LaTeX-formatted).")
    difficulty: int = Field(ge=1, le=5)
    topic: str
    subtopic: str
    target_skill: str
    learning_intention: str
    answer: str = Field(description="Full worked answer — show only after student attempts.")


class UpdateProblemRequest(BaseModel):
    status: Literal["completed", "skipped"]
    student_answer: str | None = None


class ExerciseResponse(BaseModel):
    """Student-facing exercise set. Problems have answers stripped."""
    id: str
    status: str
    problems: list[ExerciseProblemPublic]   # answer excluded
    generation_meta: GenerationMeta
    spaced_repetition: SpacedRepetition
    created_at: datetime

    @classmethod
    def from_exercise(cls, e: Exercise) -> "ExerciseResponse":
        return cls(
            id=e.id or "",
            status=e.status,
            problems=[ExerciseProblemPublic.from_problem(p) for p in e.problems],
            generation_meta=e.generation_meta,
            spaced_repetition=e.spaced_repetition,
            created_at=e.created_at,
        )
