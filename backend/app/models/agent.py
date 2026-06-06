"""Shared agent contract models — inter-agent data transfer objects."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.coerce import as_int

from app.models.common import utcnow
from app.models.session import AnalysisResult, Milestone, ReasoningPlan
from app.models.student import MasterySnapshot


# ── Orchestrator ──────────────────────────────────────────────────


class OrchestratorDecision(BaseModel):
    route: Literal["analyzer", "teaching", "practice", "noop"]
    message_type: Literal[
        "new_problem", "step_submission", "stuck_signal", "clarification", "off_topic"
    ]
    reason: str = ""
    updated_phase: str
    updated_hint_level: int
    updated_milestone: int


# ── Analyzer ──────────────────────────────────────────────────────


class AnalyzerOutput(BaseModel):
    analysis: AnalysisResult
    plan: ReasoningPlan
    opening_question_seed: str = ""
    degraded: bool = False  # True when Flash fallback was used


# ── Teaching ──────────────────────────────────────────────────────


class SocraticAssessment(BaseModel):
    """
    Structured inner reasoning the Teaching Agent produces before composing
    its reply. Mirrors the user-requested output contract:
      { student_understanding, next_question, hint, confidence }

    This is INTERNAL — never sent raw to the student.
    The agent uses it to compose a natural-language response.
    """
    student_understanding: str = Field(
        description="One-sentence assessment of what the student currently grasps."
    )
    next_question: str = Field(
        description="The single Socratic guiding question for this turn."
    )
    hint: str = Field(
        description=(
            "A concrete hint scaled to hint_level. "
            "Empty string when hint_level=0 (open questioning mode)."
        )
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Tutor confidence (0–100) that the student is on the right track."
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: object) -> int:
        from app.utils.coerce import as_float

        if isinstance(v, int) and not isinstance(v, bool):
            return as_int(v, 50, 0, 100)
        f = as_float(v, 0.5)
        if isinstance(v, float) and 0.0 < f <= 1.0:
            return int(round(f * 100))
        if isinstance(v, str) and f <= 1.0 and "." in v:
            return int(round(f * 100))
        return as_int(v, 50, 0, 100)

    should_reveal_solution: bool = Field(
        default=False,
        description=(
            "True ONLY when: hint_level==3 AND the student has made 3+ incorrect "
            "attempts on the same milestone. Triggers near-example scaffold, NOT the answer."
        )
    )
    milestone_complete: bool = Field(
        default=False,
        description="True when the student's step correctly satisfies the milestone goal."
    )


class TeachingOutput(BaseModel):
    """Full output returned from TeachingAgent.run()."""
    # The structured inner reasoning (logged + sent to SSE agent_trace)
    assessment: SocraticAssessment

    # Natural-language text streamed to the student
    response_text: str

    # Convenience fields consumed by Orchestrator
    milestone_advanced: bool = False
    answer_leak_risk: float = Field(default=0.0, ge=0.0, le=1.0)


# ── Student Model (Critic) ────────────────────────────────────────


class CriticVerdict(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect", "unclear"]
    error_tag: str | None = None
    correct_parts: str | None = None
    reasoning: str = ""


class StudentModelOutput(BaseModel):
    updated_mastery: MasterySnapshot
    updated_error_patterns: list[str]
    mastery_deltas: dict[str, float] = Field(default_factory=dict)
    recommended_hint_level: int = 0
    critic_verdict: CriticVerdict | None = None


# ── Practice ──────────────────────────────────────────────────────


class PracticeOutput(BaseModel):
    exercises: list[dict] = Field(default_factory=list)
    rationale: str = ""
    source: Literal["generated", "problem_library", "fallback"] = "generated"


# ── Learning Analytics ────────────────────────────────────────────


class ErrorFrequency(BaseModel):
    """Aggregated error tag with count and computed severity."""
    tag: str
    count: int
    severity: Literal["low", "medium", "high"] = "low"


class LearningAnalyticsOutput(BaseModel):
    """
    Full output of the Learning Analytics Agent.

    Matches the user-facing JSON contract:
        strengths, weaknesses, mastery_scores,
        recommended_next_topic, recommended_subtopic,
        error_summary, learning_tip, confidence

    deterministic_only=True when the LLM enrichment call failed
    (mastery scores and error analysis are always computed deterministically).
    """
    # ── Core output ────────────────────────────────────────────────
    strengths: list[str] = Field(
        default_factory=list,
        description="Topics/subtopics where mastery >= 0.70.",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Topics where mastery < 0.40 or persistent error tags.",
    )
    mastery_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-topic mastery in [0.0, 1.0]. Keys: limits, derivatives, integrals.",
    )
    recommended_next_topic: str = Field(
        description="The one topic the student should focus on next.",
    )
    recommended_subtopic: str = Field(
        default="",
        description="Granular subtopic within recommended_next_topic.",
    )

    # ── Diagnostic detail ──────────────────────────────────────────
    error_summary: list[ErrorFrequency] = Field(
        default_factory=list,
        description="Top error tags ranked by frequency.",
    )
    learning_tip: str = Field(
        default="",
        description="Personalised, actionable advice generated by the LLM.",
    )

    # ── Metadata ───────────────────────────────────────────────────
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="How confident the system is in the recommendation (0–1).",
    )
    deterministic_only: bool = Field(
        default=False,
        description="True when the LLM enrichment step was skipped/failed.",
    )
    computed_at: datetime = Field(default_factory=utcnow)


# ── Session Context (shared across all agents per request) ────────


class SessionContext(BaseModel):
    session_id: str
    student_id: str

    # Student profile snapshot
    display_name: str
    mastery: MasterySnapshot
    error_patterns: list[str] = Field(default_factory=list)
    hint_preference: str = "balanced"
    llm_provider: str = "gemini"
    ui_locale: str = "en"
    response_locale: str = "en"

    # Problem state
    problem_text: str
    analysis: AnalysisResult | None = None
    plan: ReasoningPlan | None = None  # NEVER serialized to client

    # Progress
    phase: str = "intake"
    current_milestone: int = 0
    hint_level: int = 0
    solution_ready: bool = False
    turn_count: int = 0
    stuck_count: int = 0

    # History (bounded — last N messages only for LLM context)
    recent_messages: list[dict] = Field(default_factory=list)
    student_steps: list[dict] = Field(default_factory=list)

    # Flags
    is_new_problem: bool = False
    stuck_requested: bool = False
    session_ended: bool = False
    current_milestone_obj: Milestone | None = None
