from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import MongoBase, utcnow


class AgentTrace(BaseModel):
    """Persisted agent trace — superset of fields needed to rebuild the debug panel."""

    model_config = {"extra": "allow"}

    route: str = ""
    models: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    turn: int = 0
    milestone: str | None = None
    hint_level: int = 0
    verdict: str | None = None
    error_tag: str | None = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    leak_risk: float | None = None
    mastery_delta: dict[str, float] | None = None
    assessment: dict | None = None
    analysis: dict | None = None


class MessageMetadata(BaseModel):
    milestone_id: int | None = None
    hint_level: int | None = None
    phase: str | None = None


class Message(MongoBase):
    id: str | None = Field(default=None, alias="_id")
    schema_version: int = 1

    session_id: str
    student_id: str
    client_message_id: str | None = None

    role: Literal["student", "assistant", "system"]
    content: str = Field(max_length=8000)
    turn_index: int = 0

    agent_trace: AgentTrace | None = None
    metadata: MessageMetadata | None = None

    created_at: datetime = Field(default_factory=utcnow)


# ── API shapes ────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    turn_index: int
    agent_trace: AgentTrace | None
    metadata: MessageMetadata | None
    created_at: datetime

    @classmethod
    def from_message(cls, m: Message) -> "MessageResponse":
        trace = m.agent_trace
        if trace is not None:
            trace_data = trace.model_dump()
            trace_data.pop("plan", None)
            trace = AgentTrace.model_validate(trace_data)
        return cls(
            id=m.id or "",
            role=m.role,
            content=m.content,
            turn_index=m.turn_index,
            agent_trace=trace,
            metadata=m.metadata,
            created_at=m.created_at,
        )
