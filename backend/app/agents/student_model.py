"""
Student Model Agent — Critic sub-task + mastery bookkeeping.
LLM used only for step verdict. Mastery math is deterministic Python.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel

from app.models.agent import CriticVerdict, StudentModelOutput
from app.models.student import MasterySnapshot, TopicMastery
from app.services.mastery import compute_ema
from app.services.vertex_prompts import CRITIC_SYSTEM
from app.services.llm_protocol import LLMService
from app.services.vertex_types import GeminiModel, GenerationConfig

logger = structlog.get_logger(__name__)


class _CriticLLMOutput(BaseModel):
    verdict: str
    error_tag: str | None = None
    correct_parts: str | None = None
    reasoning: str = ""


VALID_VERDICTS = {"correct", "partially_correct", "incorrect", "unclear"}
VALID_ERROR_TAGS = {
    "wrong_derivative_rule", "missing_chain_rule_factor", "arithmetic_error",
    "wrong_integral_bounds", "forgot_constant_of_integration", "limit_form_error",
    "incorrect_factoring", "sign_error", "wrong_trig_identity", "conceptual_gap",
    "notation_error",
}


class StudentModelAgent:
    def __init__(self, gemini: LLMService) -> None:
        self._gemini = gemini

    # ── Critic ────────────────────────────────────────────────────

    async def evaluate_step(
        self,
        student_step: str,
        milestone_goal: str,
        skills_required: list[str],
    ) -> CriticVerdict:
        """
        Evaluate a student's step against the current milestone.
        Returns a structured CriticVerdict.
        """
        system = CRITIC_SYSTEM.format_map({
            "milestone_goal": milestone_goal,
            "skills": ", ".join(skills_required),
        })

        try:
            raw: _CriticLLMOutput = await self._gemini.classify(
                system_prompt=system,
                user_message=f'Student step:\n"{student_step}"',
                schema=_CriticLLMOutput,
            )
        except Exception as exc:
            logger.warning("critic_evaluate_failed", error=str(exc))
            return CriticVerdict(
                verdict="unclear",
                error_tag=None,
                correct_parts=None,
                reasoning="Critic unavailable",
            )

        verdict = raw.verdict if raw.verdict in VALID_VERDICTS else "unclear"
        error_tag = raw.error_tag if raw.error_tag in VALID_ERROR_TAGS else None

        logger.info(
            "critic_verdict",
            verdict=verdict,
            error_tag=error_tag,
            milestone=milestone_goal[:50],
        )
        return CriticVerdict(
            verdict=verdict,  # type: ignore[arg-type]
            error_tag=error_tag,
            correct_parts=raw.correct_parts,
            reasoning=raw.reasoning,
        )

    # ── Mastery update ────────────────────────────────────────────

    def apply_mastery_update(
        self,
        mastery: MasterySnapshot,
        topic: str,
        verdict: str,
        hint_level: int,
        error_tag: str | None,
        error_patterns: list[str],
    ) -> StudentModelOutput:
        """
        Compute updated mastery via EMA and return the full output.
        Pure function — no side effects (DB writes happen in SessionService).
        """
        current = mastery.get_score(topic)
        new_score, delta = compute_ema(current, verdict, hint_level)

        # Clone mastery and update target topic
        new_mastery = mastery.model_copy(deep=True)
        new_mastery.set_score(topic, new_score)

        # Update error pattern list
        updated_patterns = list(error_patterns)
        if error_tag:
            updated_patterns.append(error_tag)
            if len(updated_patterns) > 50:
                updated_patterns = updated_patterns[-50:]

        recommended_hint = hint_level
        # If same error_tag seen 3+ times in patterns, suggest bumping hint
        if error_tag and updated_patterns.count(error_tag) >= 3:
            recommended_hint = min(hint_level + 1, 3)

        return StudentModelOutput(
            updated_mastery=new_mastery,
            updated_error_patterns=updated_patterns,
            mastery_deltas={topic: delta},
            recommended_hint_level=recommended_hint,
            critic_verdict=None,  # set by caller after evaluate_step
        )
