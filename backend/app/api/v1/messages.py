"""
Messages route — SSE-streaming tutor turn endpoint.

POST /v1/sessions/{session_id}/messages
Accept: text/event-stream
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.sse_turn import stream_tutor_turn
from app.dependencies import CurrentUser, build_orchestrator, get_session_repo, get_session_service
from app.services.llm_factory import get_llm_service
from app.models.message import Message, MessageResponse, SendMessageRequest
from app.repositories import MessageRepository, SessionRepository
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["messages"])


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    user: CurrentUser,
    limit: int = 100,
    sessions: SessionRepository = Depends(get_session_repo),
):
    """Return chat history for a session (chronological)."""
    session_doc = await sessions.get_for_client(session_id)
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session_doc.get("student_id", "")) != user.sub:
        raise HTTPException(status_code=403, detail="Not your session")

    from app.db.client import get_database

    msg_repo = MessageRepository(get_database().messages)
    docs = await msg_repo.get_session_history(session_id, limit=limit)
    return [_doc_to_message_response(d) for d in docs]


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    user: CurrentUser,
    request: Request,
    sessions: SessionRepository = Depends(get_session_repo),
    session_svc: SessionService = Depends(get_session_service),
):
    """Process a student message and stream the tutor response via SSE."""
    session_doc = await sessions.get_for_client(session_id)
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session_doc.get("student_id", "")) != user.sub:
        raise HTTPException(status_code=403, detail="Not your session")
    if session_doc.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Session already completed")

    from app.db.client import get_database

    msg_repo = MessageRepository(get_database().messages)
    if body.client_message_id:
        if await msg_repo.is_duplicate(session_id, body.client_message_id):
            raise HTTPException(status_code=409, detail="Duplicate message")

    try:
        ctx = await session_svc.load_context(session_id, user.sub)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    ctx.is_new_problem = ctx.analysis is None
    ctx.stuck_requested = False

    llm = get_llm_service(ctx.llm_provider)
    orchestrator = build_orchestrator(llm)

    return await stream_tutor_turn(
        request,
        session_id,
        ctx,
        body.content,
        orchestrator,
        session_svc,
        client_message_id=body.client_message_id,
    )


def _doc_to_message_response(doc: dict) -> MessageResponse:
    d = dict(doc)
    d["_id"] = str(d.get("_id", ""))
    d["session_id"] = str(d.get("session_id", ""))
    d["student_id"] = str(d.get("student_id", ""))
    return MessageResponse.from_message(Message(**d))
