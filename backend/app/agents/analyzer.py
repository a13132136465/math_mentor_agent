"""
Problem Analyzer Agent — classifies topic, builds internal reasoning plan.

Phase 1  (Gemini Pro)   → AnalysisResult with the required schema:
                            { topic, subtopic, difficulty (1-5),
                              recommended_method, key_observation,
                              suggested_methods, prerequisites,
                              confidence, ambiguity_note }

Phase 2  (Gemini Pro)   → ReasoningPlan (milestones), seeded with
                            key_observation so milestones target the unlock.

Phase 2.5 (Gemini Flash) → Opening Socratic seed question.

Runs once per new problem. LLM failures propagate (no degraded fallback).
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field, field_validator

from app.utils.coerce import as_float, as_int

from app.models.agent import AnalyzerOutput
from app.models.session import AnalysisResult, Milestone, ReasoningPlan
from app.services.vertex_prompts import ANALYZER_SYSTEM, OPENING_SEED_SYSTEM, PLANNER_SYSTEM
from app.services.llm_protocol import LLMService
from app.services.vertex_types import GeminiModel, GenerationConfig
from app.utils.locale import locale_instruction, resolve_locale

logger = structlog.get_logger(__name__)

VALID_TOPICS = {"limits", "derivatives", "integrals"}
VALID_SUBTOPICS = {
    "limits": {
        "one_sided", "lhopital", "continuity", "squeeze_theorem",
        "infinity_limits", "indeterminate_forms",
    },
    "derivatives": {
        "power_rule", "chain_rule", "product_rule", "quotient_rule",
        "implicit", "logarithmic", "trig", "inverse_trig",
        "higher_order", "related_rates",
    },
    "integrals": {
        "riemann_sum", "ftc_part1", "ftc_part2", "u_substitution",
        "integration_by_parts", "trig_integrals", "partial_fractions",
        "improper", "area_between_curves",
    },
}


# ── LLM output schemas ────────────────────────────────────────────

class _AnalysisLLMOutput(BaseModel):
    """Exact mirror of the user-facing JSON schema returned by the LLM."""
    topic: str
    subtopic: str
    difficulty: int = Field(default=3, ge=1, le=5)
    recommended_method: str = ""
    key_observation: str = ""
    suggested_methods: list[str] = []
    prerequisites: list[str] = []
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    ambiguity_note: str | None = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _coerce_difficulty(cls, v: object) -> int:
        return as_int(v, 3, 1, 5)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: object) -> float:
        f = as_float(v, 0.8)
        return max(0.0, min(1.0, f))


class _MilestoneItem(BaseModel):
    id: int
    goal: str
    skills_required: list[str] = []
    completed: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> int:
        return as_int(v, 1, 1)


class _PlanLLMOutput(BaseModel):
    milestones: list[_MilestoneItem]
    common_pitfalls: list[str] = []
    estimated_turns: int = 6

    @field_validator("estimated_turns", mode="before")
    @classmethod
    def _coerce_estimated_turns(cls, v: object) -> int:
        return as_int(v, 6, 1)


class _SeedOutput(BaseModel):
    seed: str


# ── Agent ─────────────────────────────────────────────────────────

class AnalyzerAgent:
    def __init__(self, gemini: LLMService) -> None:
        self._gemini = gemini

    async def run(
        self,
        problem_text: str,
        limits_score: float,
        deriv_score: float,
        integ_score: float,
        error_patterns: list[str],
        ui_locale: str = "en",
    ) -> AnalyzerOutput:
        """
        Full analysis pipeline for a new problem.
        Falls back to degraded generic output when any phase fails.
        """
        degraded = False

        try:
            analysis = await self._classify(
                problem_text, limits_score, deriv_score, integ_score, error_patterns
            )
        except Exception as exc:
            logger.warning("analyzer_phase1_failed", error=str(exc))
            degraded = True
            analysis = self._fallback_analysis(problem_text)

        try:
            plan = await self._plan(problem_text, analysis)
        except Exception as exc:
            logger.warning("analyzer_phase2_failed", error=str(exc))
            degraded = True
            plan = ReasoningPlan(
                milestones=self._generic_milestones(analysis.topic),
                common_pitfalls=["Check each algebraic step carefully"],
                estimated_turns=6,
            )

        response_locale = resolve_locale(problem_text, ui_locale=ui_locale)
        try:
            seed = await self._opening_seed(
                problem_text, analysis.subtopic, response_locale
            )
        except Exception as exc:
            logger.warning("analyzer_seed_failed", error=str(exc))
            degraded = True
            seed = "What do you notice about the structure of this problem?"

        return AnalyzerOutput(
            analysis=analysis,
            plan=plan,
            opening_question_seed=seed,
            degraded=degraded,
        )

    # ── Phase 1 ───────────────────────────────────────────────────

    async def _classify(
        self,
        problem_text: str,
        limits_score: float,
        deriv_score: float,
        integ_score: float,
        error_patterns: list[str],
    ) -> AnalysisResult:
        system = ANALYZER_SYSTEM.format_map({
            "limits_score": as_float(limits_score, 0.5),
            "deriv_score": as_float(deriv_score, 0.5),
            "integ_score": as_float(integ_score, 0.5),
            "error_patterns": ", ".join(error_patterns) or "none",
        })

        raw, resp = await self._gemini.analyze(
            system_prompt=system,
            user_message=f"Problem:\n{problem_text}",
            schema=_AnalysisLLMOutput,
        )
        raw: _AnalysisLLMOutput

        # ── Sanitise & validate ───────────────────────────────────
        topic = raw.topic if raw.topic in VALID_TOPICS else "derivatives"
        subtopic = (
            raw.subtopic
            if raw.subtopic in VALID_SUBTOPICS.get(topic, set())
            else list(VALID_SUBTOPICS[topic])[0]
        )
        difficulty = as_int(raw.difficulty, 3, 1, 5)

        analysis = AnalysisResult(
            topic=topic,                                    # type: ignore[arg-type]
            subtopic=subtopic,
            difficulty=difficulty,
            recommended_method=raw.recommended_method,
            key_observation=raw.key_observation,
            suggested_methods=raw.suggested_methods or [raw.recommended_method],
            prerequisites=raw.prerequisites,
            confidence=raw.confidence,
            ambiguity_note=raw.ambiguity_note,
        )

        logger.info(
            "analyzer_phase1_ok",
            topic=topic,
            subtopic=subtopic,
            difficulty=difficulty,
            recommended_method=raw.recommended_method,
            confidence=raw.confidence,
            tokens=resp.total_tokens,
        )
        return analysis

    # ── Phase 2 ───────────────────────────────────────────────────

    async def _plan(
        self, problem_text: str, analysis: AnalysisResult
    ) -> ReasoningPlan:
        """
        Build a milestone graph. Injects key_observation so the planner
        knows which insight the student must discover — without spelling it out.
        """
        plan_prompt = (
            f"Problem:\n{problem_text}\n\n"
            f"Analysis summary:\n"
            f"  topic            = {analysis.topic}\n"
            f"  subtopic         = {analysis.subtopic}\n"
            f"  difficulty       = {analysis.difficulty}/5 ({analysis.difficulty_label})\n"
            f"  recommended_method = {analysis.recommended_method}\n"
            f"  key_observation  = {analysis.key_observation}\n"
            f"  prerequisites    = {', '.join(analysis.prerequisites)}\n\n"
            "Design exactly 3 milestones the student must discover themselves. "
            "The final milestone should reflect the key_observation without stating it."
        )

        raw, _ = await self._gemini.analyze(
            system_prompt=PLANNER_SYSTEM,
            user_message=plan_prompt,
            schema=_PlanLLMOutput,
        )
        raw: _PlanLLMOutput
        milestones = [
            Milestone(id=as_int(m.id, i + 1, 1), goal=m.goal, skills_required=m.skills_required)
            for i, m in enumerate(raw.milestones[:3])
        ]
        if not milestones:
            raise ValueError("Planner returned no milestones")

        logger.info(
            "analyzer_phase2_ok",
            milestones=len(milestones),
            estimated_turns=raw.estimated_turns,
        )
        return ReasoningPlan(
            milestones=milestones,
            common_pitfalls=raw.common_pitfalls,
            estimated_turns=as_int(raw.estimated_turns, 6, 1),
        )

    # ── Phase 2.5 ─────────────────────────────────────────────────

    async def _opening_seed(
        self, problem_text: str, subtopic: str, response_locale: str
    ) -> str:
        """
        Flash call: one short question that makes the student think about
        the structure WITHOUT hinting at the method.
        """
        system = OPENING_SEED_SYSTEM.format_map({
            "locale_instruction": locale_instruction(response_locale),
        })
        result = await self._gemini.classify(
            system_prompt=system,
            user_message=f"Problem: {problem_text}\nKey concept: {subtopic}",
            schema=_SeedOutput,
        )
        seed = result.seed.strip()  # type: ignore[union-attr]
        if not seed.endswith("?"):
            seed += "?"
        return seed

    # ── Static helpers ────────────────────────────────────────────

    @staticmethod
    def _fallback_analysis(problem_text: str) -> AnalysisResult:
        """Generic classification when Phase 1 LLM call fails."""
        lower = problem_text.lower()
        if any(w in lower for w in ("limit", "lim", "极限")):
            topic = "limits"
            subtopic = "one_sided"
        elif any(w in lower for w in ("integral", "∫", "积分")):
            topic = "integrals"
            subtopic = "u_substitution"
        else:
            topic = "derivatives"
            subtopic = "chain_rule"
        return AnalysisResult(
            topic=topic,  # type: ignore[arg-type]
            subtopic=subtopic,
            difficulty=3,
            recommended_method=subtopic,
            key_observation="Identify the main structure before applying a rule.",
            suggested_methods=[subtopic],
            prerequisites=[],
            confidence=0.3,
            ambiguity_note="Degraded analysis — LLM classification unavailable",
        )

    @staticmethod
    def _generic_milestones(topic: str) -> list[Milestone]:
        templates: dict[str, list[Milestone]] = {
            "limits": [
                Milestone(id=1, goal="Identify the limit form (determinate or indeterminate)",         skills_required=["limit_recognition"]),
                Milestone(id=2, goal="Select and apply the correct limit technique",                   skills_required=["limit_evaluation"]),
                Milestone(id=3, goal="Simplify the expression and state the limit value",              skills_required=["algebraic_simplification"]),
            ],
            "derivatives": [
                Milestone(id=1, goal="Identify the function structure and the applicable rule",        skills_required=["function_analysis"]),
                Milestone(id=2, goal="Apply the differentiation rule correctly",                       skills_required=["differentiation"]),
                Milestone(id=3, goal="Simplify the derivative expression",                             skills_required=["algebraic_simplification"]),
            ],
            "integrals": [
                Milestone(id=1, goal="Identify the appropriate integration technique",                 skills_required=["integral_recognition"]),
                Milestone(id=2, goal="Set up and execute the technique",                               skills_required=["integration"]),
                Milestone(id=3, goal="Evaluate, simplify, and include the constant of integration",   skills_required=["evaluation"]),
            ],
        }
        return templates.get(topic, templates["derivatives"])
