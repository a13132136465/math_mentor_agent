"""Message API models — client-safe agent trace."""
from datetime import datetime, timezone

from app.models.message import AgentTrace, Message, MessageResponse


def test_message_response_strips_plan_from_trace():
    msg = Message(
        _id="m1",
        session_id="s1",
        student_id="st1",
        role="assistant",
        content="What do you notice?",
        turn_index=1,
        agent_trace=AgentTrace(
            route="analyzer->teaching",
            plan={"milestones": [{"id": 1, "goal": "secret goal"}]},
            analysis={"topic": "derivatives"},
        ),
        created_at=datetime.now(timezone.utc),
    )
    resp = MessageResponse.from_message(msg)
    assert resp.agent_trace is not None
    dumped = resp.agent_trace.model_dump()
    assert "plan" not in dumped
