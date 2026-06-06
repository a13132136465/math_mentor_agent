"""
POST /v1/analyze — standalone problem analysis (demo endpoint).

Returns AnalysisResult only; ReasoningPlan is never exposed to the client.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.analyzer import AnalyzerAgent
from app.dependencies import CurrentUser, get_llm_for_current_user, get_student_repo
from app.models.session import AnalysisResult
from app.repositories import StudentRepository
from app.services.llm_protocol import LLMService

router = APIRouter(prefix="/analyze", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    problem_text: str = Field(min_length=3, max_length=4000)


class AnalyzeResponse(BaseModel):
    analysis: AnalysisResult
    opening_question_seed: str
    degraded: bool = False


@router.post("", response_model=AnalyzeResponse)
async def analyze_problem(
    body: AnalyzeRequest,
    user: CurrentUser,
    llm: LLMService = Depends(get_llm_for_current_user),
    students: StudentRepository = Depends(get_student_repo),
):
    """Run the Analyzer Agent once without creating a session."""
    student_doc = await students.get_by_id(user.sub)
    mastery = (student_doc or {}).get("mastery", {})
    error_patterns = [
        ep["tag"] for ep in (student_doc or {}).get("error_patterns", [])
    ]

    agent = AnalyzerAgent(llm)
    output = await agent.run(
        problem_text=body.problem_text,
        limits_score=mastery.get("limits", {}).get("score", 0.5),
        deriv_score=mastery.get("derivatives", {}).get("score", 0.5),
        integ_score=mastery.get("integrals", {}).get("score", 0.5),
        error_patterns=error_patterns,
    )

    return AnalyzeResponse(
        analysis=output.analysis,
        opening_question_seed=output.opening_question_seed,
        degraded=output.degraded,
    )
