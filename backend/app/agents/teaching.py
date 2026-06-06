"""
Teaching Agent — Socratic tutor voice.

Two-phase architecture:
  Phase 1 (Flash JSON)     → SocraticAssessment
  Phase 2 (Flash, streaming) → Natural-language reply

LLM failures fall back to safe canned scaffolds; high leak risk triggers override text.
"""
from __future__ import annotations

import asyncio

import structlog

from app.models.agent import (
    CriticVerdict,
    SessionContext,
    SocraticAssessment,
    TeachingOutput,
)
from app.services.mastery import mastery_label
from app.utils.coerce import as_float, as_int
from app.services.vertex_prompts import (
    CRITIC_SECTION_CORRECT,
    CRITIC_SECTION_INCORRECT,
    CRITIC_SECTION_NONE,
    CRITIC_SECTION_PARTIAL,
    TEACHING_ASSESSMENT_SYSTEM,
    TEACHING_REPLY_SYSTEM,
)
from app.services.vertex_exceptions import VertexError
from app.services.llm_protocol import LLMService
from app.services.vertex_types import PromptMessage
from app.utils.leak_heuristic import heuristic_leak_risk
from app.utils.llm_error import emit_llm_error
from app.utils.locale import locale_instruction
from app.utils.pedagogy import milestone_focus_for_teaching, pitfall_label

logger = structlog.get_logger(__name__)

LEAK_RISK_REWRITE = 0.30
LEAK_RISK_OVERRIDE = 0.70
MAX_REWRITES = 2
_LEAK_CHECK_TIMEOUT = 8.0


class TeachingAgent:
    def __init__(self, gemini: LLMService) -> None:
        self._gemini = gemini

    async def run(
        self,
        ctx: SessionContext,
        student_message: str,
        critic_verdict: CriticVerdict | None,
        queue: asyncio.Queue,
    ) -> TeachingOutput:
        failed_attempts = self._count_failed_attempts(ctx)
        critic_section = self._build_critic_section(ctx, critic_verdict)
        history_text = self._format_history(ctx.recent_messages)
        history_msgs = self._build_history(ctx)

        assessment = await self._assess(
            ctx, student_message, critic_section, history_text, failed_attempts
        )

        logger.info(
            "teaching_assessment",
            confidence=assessment.confidence,
            milestone_complete=assessment.milestone_complete,
            hint_level=ctx.hint_level,
            failed_attempts=failed_attempts,
            understanding=assessment.student_understanding[:60],
        )

        full_text, leak_risk = await self._compose_and_stream(
            ctx=ctx,
            assessment=assessment,
            critic_section=critic_section,
            history=history_msgs,
            student_message=student_message,
            queue=queue,
        )

        milestone_advanced = assessment.milestone_complete or (
            critic_verdict is not None and critic_verdict.verdict == "correct"
        )

        return TeachingOutput(
            assessment=assessment,
            response_text=full_text,
            milestone_advanced=milestone_advanced,
            answer_leak_risk=leak_risk,
        )

    async def _assess(
        self,
        ctx: SessionContext,
        student_message: str,
        critic_section: str,
        history_text: str,
        failed_attempts: int,
    ) -> SocraticAssessment:
        milestone = ctx.current_milestone_obj
        topic = ctx.analysis.topic if ctx.analysis else "calculus"
        subtopic = ctx.analysis.subtopic if ctx.analysis else "general"
        pitfall = pitfall_label(
            ctx.plan.common_pitfalls[0]
            if ctx.plan and ctx.plan.common_pitfalls
            else None
        )
        score = (
            as_float(ctx.mastery.get_score(topic), 0.5)
            if ctx.analysis
            else 0.5
        )

        system = TEACHING_ASSESSMENT_SYSTEM.format_map({
            "topic": topic,
            "subtopic": subtopic,
            "milestone_goal": milestone_focus_for_teaching(
                topic=topic,
                subtopic=subtopic,
                skills=list(milestone.skills_required) if milestone else [],
            ),
            "skills": ", ".join(milestone.skills_required) if milestone else "calculus",
            "pitfall": pitfall,
            "hint_level": ctx.hint_level,
            "failed_attempts": failed_attempts,
            "mastery_label": mastery_label(score),
            "mastery_pct": score,
            "error_patterns": ", ".join(ctx.error_patterns[-3:]) or "none",
            "critic_section": critic_section,
            "history": history_text,
            "student_message": student_message,
            "locale_instruction": locale_instruction(ctx.response_locale),
        })

        try:
            result: SocraticAssessment = await self._gemini.classify(
                system_prompt=system,
                user_message=student_message,
                schema=SocraticAssessment,
            )
        except Exception as exc:
            logger.warning("teaching_assessment_failed", error=str(exc))
            return self._fallback_assessment(ctx)

        hint_lvl = as_int(ctx.hint_level, 0, 0, 3)
        attempts = as_int(failed_attempts, 0, 0)
        if result.should_reveal_solution:
            if not (hint_lvl >= 3 and attempts >= 3):
                result = result.model_copy(update={"should_reveal_solution": False})
        return result

    async def _compose_and_stream(
        self,
        ctx: SessionContext,
        assessment: SocraticAssessment,
        critic_section: str,
        history: list[PromptMessage],
        student_message: str,
        queue: asyncio.Queue,
    ) -> tuple[str, float]:
        hint_lvl_ctx = as_int(ctx.hint_level, 0, 0, 3)
        hint_text = assessment.hint if hint_lvl_ctx >= 2 else ""
        near_example_mode = str(assessment.should_reveal_solution).lower()

        system = TEACHING_REPLY_SYSTEM.format_map({
            "student_understanding": assessment.student_understanding,
            "confidence": assessment.confidence,
            "milestone_complete": assessment.milestone_complete,
            "next_question": assessment.next_question,
            "hint_text": hint_text or "(none — open Socratic questioning mode)",
            "near_example_mode": near_example_mode,
            "critic_section": critic_section,
            "locale_instruction": locale_instruction(ctx.response_locale),
        })

        full_text = ""
        leak_risk = 0.0
        strict_prefix = ""
        first_attempt = True

        for attempt in range(1, MAX_REWRITES + 2):
            if not first_attempt:
                await queue.put({"type": "retract"})
            first_attempt = False

            try:
                full_text = await self._gemini.teach(
                    system_prompt=strict_prefix + system,
                    user_message=student_message,
                    history=history,
                    queue=queue,
                    emit_done=False,
                )
            except Exception as exc:
                logger.warning("teaching_stream_failed", attempt=attempt, error=str(exc))
                await queue.put({"type": "retract"})
                if not isinstance(exc, VertexError):
                    await emit_llm_error(queue, exc)
                raise

            try:
                llm_risk = await self._check_leak_timed(full_text, student_message)
            except Exception as exc:
                logger.warning("leak_check_failed", error=str(exc))
                await queue.put({"type": "retract"})
                await emit_llm_error(queue, exc)
                raise

            heuristic_risk = heuristic_leak_risk(full_text, student_message)
            leak_risk = max(llm_risk, heuristic_risk)
            if heuristic_risk >= LEAK_RISK_REWRITE and llm_risk < LEAK_RISK_REWRITE:
                logger.info(
                    "leak_heuristic_triggered",
                    heuristic=heuristic_risk,
                    llm=llm_risk,
                )

            if leak_risk >= LEAK_RISK_REWRITE and attempt <= MAX_REWRITES:
                logger.warning("teaching_rewrite", risk=leak_risk, attempt=attempt)
                strict_prefix = (
                    "[STRICT MODE — do NOT reveal the answer or full solution path]\n"
                )
                if leak_risk >= LEAK_RISK_OVERRIDE:
                    strict_prefix = (
                        "[STRICT MODE — previous draft leaked the answer; "
                        "ask only a guiding question]\n"
                    )
                continue

            break

        if leak_risk >= LEAK_RISK_OVERRIDE:
            logger.warning("teaching_leak_override", risk=leak_risk)
            await queue.put({"type": "retract"})
            full_text = self._canned_response(ctx, assessment)
            leak_risk = 0.05
            await queue.put({"type": "token", "text": full_text})
        elif self._response_needs_question_suffix(full_text, assessment.next_question):
            q_suffix = "\n\n" + assessment.next_question
            full_text = full_text.rstrip() + q_suffix
            await queue.put({"type": "token", "text": q_suffix})

        normalized = self._dedupe_trailing_question(
            full_text, assessment.next_question
        )
        stripped = full_text.rstrip()
        if normalized != stripped:
            await queue.put({"type": "retract"})
            await queue.put({"type": "token", "text": normalized})
            full_text = normalized

        return full_text, leak_risk

    @staticmethod
    def _response_needs_question_suffix(full_text: str, next_question: str) -> bool:
        """True when the reply lacks a closing question and next_question is not already present."""
        stripped = full_text.rstrip()
        question = next_question.strip()
        if not question:
            return False
        if stripped.endswith("?") or stripped.endswith("？"):
            return False
        if stripped.endswith(question):
            return False
        tail = stripped[-max(len(question) + 80, len(question) * 2) :]
        if question in tail:
            return False
        return True

    @staticmethod
    def _dedupe_trailing_question(full_text: str, next_question: str) -> str:
        """Collapse repeated trailing copies of next_question to a single occurrence."""
        q = next_question.strip()
        if not q:
            return full_text.rstrip()

        text = full_text.rstrip()
        removed = 0
        while True:
            if text.endswith("\n\n" + q):
                text = text[: -(len(q) + 2)].rstrip()
                removed += 1
            elif text.endswith(q):
                text = text[: -len(q)].rstrip()
                removed += 1
            else:
                break

        if removed <= 1:
            return full_text.rstrip()
        return f"{text}\n\n{q}" if text else q

    @staticmethod
    def _fallback_assessment(ctx: SessionContext) -> SocraticAssessment:
        """Safe defaults when Phase 1 assessment LLM call fails."""
        question = (
            "What do you notice about the structure of this problem?"
            if as_int(ctx.hint_level, 0, 0, 3) == 0
            else "Which rule might apply to the next step — without computing the result?"
        )
        return SocraticAssessment(
            student_understanding="Assessment unavailable; continuing with open questioning.",
            next_question=question,
            hint="",
            confidence=50,
            milestone_complete=False,
            should_reveal_solution=False,
        )

    @staticmethod
    def _canned_response(ctx: SessionContext, assessment: SocraticAssessment) -> str:
        """Template scaffold when leak risk exceeds override threshold."""
        question = assessment.next_question.strip() or "What is your next step?"
        hint_lvl = as_int(ctx.hint_level, 0, 0, 3)
        if hint_lvl >= 2 and assessment.hint.strip():
            return (
                "Let's slow down and focus on one idea at a time. "
                f"{assessment.hint.strip()}\n\n{question}"
            )
        if hint_lvl >= 1:
            return f"Think about which calculus rule fits here — then try one step.\n\n{question}"
        return question

    async def _check_leak_timed(
        self, full_text: str, student_message: str = ""
    ) -> float:
        try:
            return as_float(
                await asyncio.wait_for(
                    self._gemini.leak_check(full_text),
                    timeout=_LEAK_CHECK_TIMEOUT,
                ),
                0.0,
            )
        except Exception as exc:
            logger.warning(
                "leak_check_degraded",
                error=str(exc),
                fallback="heuristic",
            )
            return heuristic_leak_risk(full_text, student_message)

    def _build_critic_section(
        self, ctx: SessionContext, verdict: CriticVerdict | None
    ) -> str:
        if not verdict:
            return CRITIC_SECTION_NONE

        if verdict.verdict == "correct":
            return CRITIC_SECTION_CORRECT.format_map({
                "correct_parts": verdict.correct_parts or "the reasoning step",
            })

        if verdict.verdict == "partially_correct":
            return CRITIC_SECTION_PARTIAL.format_map({
                "correct_parts": verdict.correct_parts or "part of the step",
                "error_tag": verdict.error_tag or "an error",
            })

        return CRITIC_SECTION_INCORRECT.format_map({
            "error_tag": verdict.error_tag or "a reasoning error",
        })

    @staticmethod
    def _build_history(ctx: SessionContext) -> list[PromptMessage]:
        role_map = {"student": "user", "assistant": "model"}
        return [
            PromptMessage(
                role=role_map.get(m.get("role", "user"), "user"),
                content=m.get("content", ""),
            )
            for m in ctx.recent_messages
        ]

    @staticmethod
    def _format_history(msgs: list[dict]) -> str:
        if not msgs:
            return "(no prior conversation)"
        lines = []
        for m in msgs:
            label = "Student" if m.get("role") == "student" else "MathMentor"
            lines.append(f"{label}: {m.get('content', '')}")
        return "\n".join(lines)

    @staticmethod
    def _count_failed_attempts(ctx: SessionContext) -> int:
        current_id = (
            as_int(ctx.current_milestone_obj.id, 0, 0)
            if ctx.current_milestone_obj
            else 0
        )
        return sum(
            1
            for s in ctx.student_steps
            if s.get("milestone_id") == current_id
            and s.get("verdict") in ("incorrect", "unclear")
        )
