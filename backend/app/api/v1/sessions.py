from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.agents.practice import PracticeAgent
from app.api.v1.sse_turn import new_client_message_id, stream_tutor_turn
from app.utils.locale import stuck_message
from app.dependencies import (
    CurrentUser,
    build_orchestrator,
    get_exercise_repo,
    get_problem_library_repo,
    get_session_repo,
    get_session_service,
    get_student_repo,
)
from app.services.llm_factory import get_llm_service
from app.models.session import CreateSessionRequest, SessionListResponse, SessionResponse
from app.repositories import ExerciseRepository, SessionRepository, StudentRepository
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    phase: str


class CompleteSessionResponse(BaseModel):
    status: str
    exercises: list[dict] | None = None
    rationale: str | None = None
    summary: dict | None = None


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    user: CurrentUser,
    sessions: SessionRepository = Depends(get_session_repo),
    students: StudentRepository = Depends(get_student_repo),
):
    session_id = await sessions.create(
        student_id=user.sub,
        problem_text=body.problem_text,
    )
    await students.increment_session_count(user.sub)
    return CreateSessionResponse(
        session_id=str(session_id),
        status="active",
        phase="intake",
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, le=50),
    skip: int = Query(default=0, ge=0),
    sessions: SessionRepository = Depends(get_session_repo),
):
    docs = await sessions.list_for_student(
        student_id=user.sub,
        status=status_filter,
        limit=limit,
        skip=skip,
    )
    total = await sessions.count({"student_id": sessions.to_oid(user.sub)})
    return SessionListResponse(
        sessions=[SessionResponse.from_session(_doc_to_session(d)) for d in docs],
        total=total,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: CurrentUser,
    sessions: SessionRepository = Depends(get_session_repo),
):
    doc = await sessions.get_for_client(session_id)
    _assert_session_owned(doc, user.sub, session_id)
    return SessionResponse.from_session(_doc_to_session(doc))


@router.post("/{session_id}/stuck")
async def escalate_hint(
    session_id: str,
    user: CurrentUser,
    request: Request,
    sessions: SessionRepository = Depends(get_session_repo),
    session_svc: SessionService = Depends(get_session_service),
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    """
    Escalate hint level and stream a scaffolded tutor response via SSE.
    Same event format as POST /messages.
    """
    doc = await sessions.get_for_client(session_id)
    _assert_session_owned(doc, user.sub, session_id)
    if doc.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Session already completed")

    from app.utils.coerce import as_int

    current_hint = as_int(doc.get("progress", {}).get("hint_level", 0), 0, 0, 3)
    new_hint = min(current_hint + 1, 3)
    await sessions.increment_stuck(session_id, new_hint)

    try:
        ctx = await session_svc.load_context(session_id, user.sub)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    ctx.hint_level = new_hint
    ctx.stuck_requested = True
    ctx.is_new_problem = False

    llm = get_llm_service(ctx.llm_provider)
    orchestrator = build_orchestrator(llm, exercises=exercises)

    return await stream_tutor_turn(
        request,
        session_id,
        ctx,
        stuck_message(ctx.response_locale),
        orchestrator,
        session_svc,
        client_message_id=new_client_message_id(),
    )


@router.post("/{session_id}/complete", response_model=CompleteSessionResponse)
async def complete_session(
    session_id: str,
    user: CurrentUser,
    sessions: SessionRepository = Depends(get_session_repo),
    session_svc: SessionService = Depends(get_session_service),
    exercises_repo: ExerciseRepository = Depends(get_exercise_repo),
    problem_library=Depends(get_problem_library_repo),
):
    """End session and trigger PracticeAgent to generate personalised exercises."""
    doc = await sessions.get_for_client(session_id)
    _assert_session_owned(doc, user.sub, session_id)

    if doc.get("status") == "completed":
        existing = await exercises_repo.find_many(
            {"session_id": exercises_repo.to_oid(session_id)},
            limit=1,
        )
        problems = existing[0].get("problems", []) if existing else []
        return CompleteSessionResponse(
            status="already_completed",
            exercises=problems or None,
        )

    try:
        ctx = await session_svc.load_context(session_id, user.sub)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    llm = get_llm_service(ctx.llm_provider)
    practice = PracticeAgent(llm, problem_library=problem_library)

    if doc.get("phase") != "wrap_up":
        await sessions.update_progress(
            session_id,
            milestone=ctx.current_milestone,
            hint_level=ctx.hint_level,
            phase="wrap_up",
            solution_ready=True,
        )
        ctx.phase = "wrap_up"
        ctx.solution_ready = True

    summary = await session_svc.run_practice_for_session(ctx, practice)
    practice_doc = await exercises_repo.find_many(
        {"session_id": exercises_repo.to_oid(session_id)},
        sort=[("created_at", -1)],
        limit=1,
    )
    problems = practice_doc[0].get("problems", []) if practice_doc else []
    rationale = (
        practice_doc[0].get("generation_meta", {}).get("rationale")
        if practice_doc
        else None
    )

    return CompleteSessionResponse(
        status="completed",
        exercises=problems,
        rationale=rationale,
        summary=summary,
    )


def _assert_session_owned(doc: dict | None, student_id: str, session_id: str) -> None:
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(doc.get("student_id", "")) != student_id:
        raise HTTPException(status_code=403, detail="Not your session")


def _doc_to_session(doc: dict):
    from app.models.session import Session
    from app.models.common import utcnow

    doc = dict(doc)
    doc["_id"] = str(doc.get("_id", ""))
    doc["student_id"] = str(doc.get("student_id", ""))
    doc.setdefault("started_at", utcnow())
    doc.setdefault("updated_at", utcnow())
    return Session(**doc)
