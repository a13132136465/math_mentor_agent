"""
FastAPI dependency injection — DB collections, repositories, services, agents.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agents import (
    AnalyticsAgent,
    AnalyzerAgent,
    OrchestratorAgent,
    PracticeAgent,
    StudentModelAgent,
    TeachingAgent,
)
from app.db.client import get_database
from app.repositories import (
    AgentMemoryRepository,
    AttemptRepository,
    ExerciseRepository,
    MasteryEventRepository,
    MessageRepository,
    ProblemLibraryRepository,
    SessionRepository,
    StudentRepository,
)
from app.services.auth import AuthService, TokenPayload, get_auth_service
from app.services.llm_factory import get_llm_service, resolve_llm_provider
from app.services.llm_protocol import LLMService
from app.services.session_service import SessionService
from app.services.vertex_service import GeminiService, get_gemini_service

_bearer = HTTPBearer()

# ── Repository dependencies ───────────────────────────────────────


def get_student_repo() -> StudentRepository:
    return StudentRepository(get_database().students)


def get_session_repo() -> SessionRepository:
    return SessionRepository(get_database().sessions)


def get_message_repo() -> MessageRepository:
    return MessageRepository(get_database().messages)


def get_attempt_repo() -> AttemptRepository:
    return AttemptRepository(get_database().attempts)


def get_mastery_event_repo() -> MasteryEventRepository:
    return MasteryEventRepository(get_database().mastery_events)


def get_exercise_repo() -> ExerciseRepository:
    return ExerciseRepository(get_database().exercises)


def get_problem_library_repo() -> ProblemLibraryRepository:
    return ProblemLibraryRepository(get_database().problem_library)


def get_agent_memory_repo() -> AgentMemoryRepository:
    return AgentMemoryRepository(get_database().agent_memory)


# ── Service dependencies ──────────────────────────────────────────


def get_session_service(
    students: StudentRepository = Depends(get_student_repo),
    sessions: SessionRepository = Depends(get_session_repo),
    messages: MessageRepository = Depends(get_message_repo),
    attempts: AttemptRepository = Depends(get_attempt_repo),
    mastery_events: MasteryEventRepository = Depends(get_mastery_event_repo),
    exercises: ExerciseRepository = Depends(get_exercise_repo),
    agent_memory: AgentMemoryRepository = Depends(get_agent_memory_repo),
) -> SessionService:
    return SessionService(
        students=students,
        sessions=sessions,
        messages=messages,
        attempts=attempts,
        mastery_events=mastery_events,
        exercises=exercises,
        agent_memory=agent_memory,
    )


# ── Agent dependencies ────────────────────────────────────────────


def build_orchestrator(
    llm: LLMService,
    exercises: ExerciseRepository | None = None,
    problem_library: ProblemLibraryRepository | None = None,
) -> OrchestratorAgent:
    if exercises is None:
        exercises = get_exercise_repo()
    if problem_library is None:
        problem_library = get_problem_library_repo()
    analyzer = AnalyzerAgent(llm)
    student_model = StudentModelAgent(llm)
    teaching = TeachingAgent(llm)
    practice = PracticeAgent(llm, problem_library=problem_library)
    return OrchestratorAgent(
        gemini=llm,
        analyzer=analyzer,
        teaching=teaching,
        student_model=student_model,
        practice=practice,
        exercises=exercises,
    )


def get_orchestrator(
    gemini: GeminiService = Depends(get_gemini_service),
) -> OrchestratorAgent:
    return build_orchestrator(gemini)


# ── Auth dependency ───────────────────────────────────────────────


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPayload:
    try:
        return auth_service.decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Type aliases for route signatures ────────────────────────────

CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


async def get_llm_for_current_user(
    user: CurrentUser,
    students: StudentRepository = Depends(get_student_repo),
) -> LLMService:
    doc = await students.get_by_id(user.sub)
    provider = resolve_llm_provider(doc.get("preferences") if doc else None)
    return get_llm_service(provider)
