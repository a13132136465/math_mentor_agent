"""
Shared SSE streaming for tutor turns (/messages and /stuck).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncIterator

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import OrchestratorAgent
from app.services.session_service import SessionService

logger = structlog.get_logger(__name__)


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def persist_turn_result(
    session_svc: SessionService,
    ctx,
    student_message: str,
    turn_result: dict,
    client_message_id: str | None = None,
) -> None:
    """Persist turn state; finalize session when practice exercises are produced."""
    try:
        await session_svc.persist_turn(
            ctx=ctx,
            student_message=student_message,
            assistant_message=turn_result.get("response_text", ""),
            verdict=turn_result.get("verdict"),
            error_tag=turn_result.get("error_tag"),
            critic_output=turn_result.get("critic_output"),
            agent_trace={
                "route": turn_result.get("route", ""),
                "models": turn_result.get("models_used", []),
                "turn": ctx.turn_count + 1,
                "milestone": (
                    f"{ctx.current_milestone}/{len(ctx.plan.milestones)}"
                    if ctx.plan
                    else None
                ),
                "hint_level": ctx.hint_level,
                "verdict": turn_result.get("verdict"),
                "error_tag": turn_result.get("error_tag"),
                "mastery_delta": turn_result.get("mastery_delta"),
                "latency_ms": turn_result.get("latency_ms", 0),
                "leak_risk": turn_result.get("leak_risk", 0.0),
                "assessment": turn_result.get("assessment"),
                "analysis": turn_result.get("analysis"),
            },
            plan_payload=turn_result.get("plan"),
            milestone_advanced=turn_result.get("milestone_advanced", False),
            client_message_id=client_message_id,
        )

        exercises = turn_result.get("exercises")
        if exercises:
            await session_svc.finalize_session(
                ctx,
                exercises=exercises,
                rationale=turn_result.get("rationale", ""),
                source=turn_result.get("source", "generated"),
            )
    except Exception as exc:
        logger.error("persist_turn_failed", session_id=ctx.session_id, error=str(exc))


async def stream_tutor_turn(
    request: Request,
    session_id: str,
    ctx,
    student_message: str,
    orchestrator: OrchestratorAgent,
    session_svc: SessionService,
    *,
    client_message_id: str | None = None,
) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()

    async def _generator() -> AsyncIterator[str]:
        task = asyncio.create_task(
            orchestrator.handle_turn(ctx, student_message, queue)
        )
        turn_failed = False

        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield sse_format("heartbeat", {"ts": "ping"})
                    continue

                etype = event.get("type")

                if etype == "token":
                    yield sse_format("token", {"text": event["text"]})

                elif etype == "retract":
                    yield sse_format("retract", {})

                elif etype == "analysis":
                    yield sse_format("analysis", {
                        "topic": event.get("topic"),
                        "subtopic": event.get("subtopic"),
                        "difficulty": event.get("difficulty"),
                        "methods": event.get("methods", []),
                        "degraded": event.get("degraded", False),
                    })

                elif etype == "analysis_start":
                    yield sse_format("analysis_start", {})

                elif etype == "practice_start":
                    yield sse_format("practice_start", {})

                elif etype == "error":
                    turn_failed = True
                    yield sse_format("error", {
                        "code": event.get("code"),
                        "detail": event.get("detail"),
                    })
                    if not task.done():
                        task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                    break

                elif etype == "done":
                    if turn_failed:
                        break

                    try:
                        turn_result = await asyncio.wait_for(task, timeout=5.0)
                    except Exception:
                        turn_result = {}

                    if not turn_result.get("llm_failed"):
                        await persist_turn_result(
                            session_svc,
                            ctx,
                            student_message,
                            turn_result,
                            client_message_id=client_message_id,
                        )

                    yield sse_format("done", {
                        "session_id": session_id,
                        "phase": ctx.phase,
                        "milestone": ctx.current_milestone,
                        "hint_level": ctx.hint_level,
                        "solution_ready": ctx.solution_ready,
                        "verdict": turn_result.get("verdict"),
                        "error_tag": turn_result.get("error_tag"),
                        "milestone_advanced": turn_result.get("milestone_advanced", False),
                        "exercises": turn_result.get("exercises"),
                        "rationale": turn_result.get("rationale"),
                    })

                    assessment = turn_result.get("assessment") or {}
                    yield sse_format("agent_trace", {
                        "route": turn_result.get("route", "unknown"),
                        "llm_provider": ctx.llm_provider,
                        "models": turn_result.get("models_used", []),
                        "milestone": (
                            f"{ctx.current_milestone}/{len(ctx.plan.milestones) if ctx.plan else '?'}"
                        ),
                        "hint_level": ctx.hint_level,
                        "latency_ms": turn_result.get("latency_ms", 0),
                        "leak_risk": turn_result.get("leak_risk", 0.0),
                        "verdict": turn_result.get("verdict"),
                        "error_tag": turn_result.get("error_tag"),
                        "mastery_delta": turn_result.get("mastery_delta"),
                        "student_understanding": assessment.get("student_understanding", ""),
                        "next_question": assessment.get("next_question", ""),
                        "hint": assessment.get("hint", ""),
                        "confidence": assessment.get("confidence", 0),
                        "milestone_complete": assessment.get("milestone_complete", False),
                    })
                    break

        except asyncio.CancelledError:
            task.cancel()
        except Exception as exc:
            logger.error("sse_generator_error", error=str(exc))
            yield sse_format("error", {"code": "internal", "detail": str(exc)})

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def new_client_message_id() -> str:
    return str(uuid.uuid4())
