"""
Exercise routes.

GET    /exercises                         — pending exercise sets
GET    /exercises/all                     — all sets (dashboard)
POST   /exercises/single                  — generate one targeted problem on-demand
GET    /exercises/{id}                    — single exercise set (answers stripped)
PATCH  /exercises/{id}/problems/{pid}     — mark problem completed / skipped
GET    /exercises/{id}/problems/{pid}/answer — reveal answer after completion
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.practice import PracticeAgent
from app.dependencies import (
    CurrentUser,
    get_exercise_repo,
    get_llm_for_current_user,
    get_problem_library_repo,
    get_student_repo,
)
from app.services.llm_protocol import LLMService
from app.models.exercise import (
    ExerciseResponse,
    SingleExerciseRequest,
    SingleExerciseResponse,
    UpdateProblemRequest,
)
from app.models.student import ErrorPattern, MasterySnapshot
from app.repositories import ExerciseRepository, StudentRepository
from app.utils.locale import normalize_locale, resolve_locale

router = APIRouter(prefix="/exercises", tags=["exercises"])


# ── List exercise sets ────────────────────────────────────────────

@router.get("", response_model=list[ExerciseResponse])
async def list_exercises(
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    """Return all pending / in-progress exercise sets due now."""
    docs = await exercises.get_pending_for_student(user.sub)
    return [ExerciseResponse.from_exercise(_doc_to_exercise(d)) for d in docs]


@router.get("/due", response_model=list[ExerciseResponse])
async def list_due_exercises(
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    """Spaced-repetition queue: exercises where due_at <= now."""
    docs = await exercises.get_pending_for_student(user.sub)
    return [ExerciseResponse.from_exercise(_doc_to_exercise(d)) for d in docs]


@router.get("/all", response_model=list[ExerciseResponse])
async def list_all_exercises(
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    """Return all exercise sets (pending + completed) for the dashboard."""
    docs = await exercises.get_all_for_student(user.sub)
    return [ExerciseResponse.from_exercise(_doc_to_exercise(d)) for d in docs]


# ── Single on-demand exercise ─────────────────────────────────────

@router.post(
    "/single",
    response_model=SingleExerciseResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate one targeted exercise",
    description=(
        "Runs the Practice Agent to produce a single problem matched to the "
        "student's current level and weakest area. "
        "The `answer` field is included — the front-end MUST hide it behind a "
        "'Show answer' toggle until the student has attempted the problem."
    ),
)
async def generate_single_exercise(
    user: CurrentUser,
    body: SingleExerciseRequest = Depends(),
    students: StudentRepository = Depends(get_student_repo),
    llm: LLMService = Depends(get_llm_for_current_user),
    problem_library=Depends(get_problem_library_repo),
):
    student_doc = await students.get_by_id(user.sub)

    mastery = MasterySnapshot(**(student_doc or {}).get("mastery", {}))
    error_patterns = [
        ErrorPattern(**ep)
        for ep in (student_doc or {}).get("error_patterns", [])
    ]

    ui_locale = normalize_locale((student_doc or {}).get("preferences", {}).get("locale"))
    response_locale = resolve_locale(ui_locale=ui_locale)

    agent = PracticeAgent(llm, problem_library=problem_library)
    return await agent.generate_single(
        mastery=mastery,
        error_patterns=error_patterns,
        topic=body.topic,
        response_locale=response_locale,
    )


# ── Single exercise set ───────────────────────────────────────────

@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(
    exercise_id: str,
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    doc = await exercises.find_by_id(exercise_id)
    _assert_owned(doc, user.sub, exercise_id)
    return ExerciseResponse.from_exercise(_doc_to_exercise(doc))


# ── Update problem status ─────────────────────────────────────────

@router.patch("/{exercise_id}/problems/{problem_id}", status_code=status.HTTP_200_OK)
async def update_problem(
    exercise_id: str,
    problem_id: str,
    body: UpdateProblemRequest,
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
    students: StudentRepository = Depends(get_student_repo),
):
    """Mark a single exercise problem as completed or skipped."""
    doc = await exercises.find_by_id(exercise_id)
    _assert_owned(doc, user.sub, exercise_id)

    updated = await exercises.update_problem_status(
        exercise_id=exercise_id,
        problem_id=problem_id,
        status=body.status,
        student_answer=body.student_answer,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Problem not found in exercise set")

    # Auto-complete the set when every problem is done
    doc_fresh = await exercises.find_by_id(exercise_id)
    problems = doc_fresh.get("problems", [])
    all_done = all(p.get("status") in ("completed", "skipped") for p in problems)
    if all_done:
        await exercises.mark_completed(exercise_id)
        if body.status == "completed":
            await students.increment_exercise_count(user.sub)

    return {"updated": updated, "set_completed": all_done}


# ── Reveal answer (after attempt) ────────────────────────────────

@router.get(
    "/{exercise_id}/problems/{problem_id}/answer",
    summary="Reveal the worked answer for a completed problem",
    description=(
        "Returns the full worked answer. Only available after the problem "
        "has been marked 'completed' or 'skipped' — enforces the Socratic flow."
    ),
)
async def get_problem_answer(
    exercise_id: str,
    problem_id: str,
    user: CurrentUser,
    exercises: ExerciseRepository = Depends(get_exercise_repo),
):
    doc = await exercises.find_by_id(exercise_id)
    _assert_owned(doc, user.sub, exercise_id)

    for prob in doc.get("problems", []):
        if prob.get("id") == problem_id:
            if prob.get("status") not in ("completed", "skipped"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Answer not available yet. "
                        "Submit your attempt first, then the answer will be revealed."
                    ),
                )
            answer = prob.get("answer", "")
            if not answer:
                raise HTTPException(
                    status_code=404,
                    detail="No answer recorded for this problem.",
                )
            return {"problem_id": problem_id, "answer": answer}

    raise HTTPException(status_code=404, detail="Problem not found in exercise set")


# ── Helpers ───────────────────────────────────────────────────────

def _assert_owned(doc: dict | None, student_id: str, resource_id: str) -> None:
    if not doc:
        raise HTTPException(status_code=404, detail="Exercise not found")
    if str(doc.get("student_id", "")) != student_id:
        raise HTTPException(status_code=403, detail="Not your exercise")


def _doc_to_exercise(doc: dict):
    from app.models.common import utcnow
    from app.models.exercise import Exercise
    doc = dict(doc)
    doc["_id"]        = str(doc.get("_id", ""))
    doc["student_id"] = str(doc.get("student_id", ""))
    doc["session_id"] = str(doc.get("session_id", ""))
    doc.setdefault("created_at", utcnow())
    return Exercise(**doc)
