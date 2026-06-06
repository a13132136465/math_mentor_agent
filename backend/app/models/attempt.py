from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import MongoBase, utcnow

ERROR_TAGS = Literal[
    "wrong_derivative_rule",
    "missing_chain_rule_factor",
    "arithmetic_error",
    "wrong_integral_bounds",
    "forgot_constant_of_integration",
    "limit_form_error",
    "incorrect_factoring",
    "sign_error",
    "wrong_trig_identity",
    "conceptual_gap",
    "notation_error",
]

VerdictType = Literal["correct", "partially_correct", "incorrect", "unclear"]


class CriticOutput(BaseModel):
    correct_parts: str | None = None
    reasoning: str = ""
    model_used: str = ""
    latency_ms: int = 0


class MasteryImpact(BaseModel):
    topic: str
    score_before: float
    score_after: float
    delta: float
    hint_penalty: float = 1.0


class Attempt(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    session_id: str
    student_id: str
    message_id: str | None = None

    content: str
    turn_index: int
    milestone_id: int

    verdict: VerdictType
    error_tag: str | None = None

    critic_output: CriticOutput = Field(default_factory=CriticOutput)
    mastery_impact: MasteryImpact | None = None
    hint_level_at_attempt: int = 0

    created_at: datetime = Field(default_factory=utcnow)
