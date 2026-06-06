"""
Orchestrator Agent — routes turns, enforces phase transitions, answer embargo.
"""
from __future__ import annotations

import asyncio
import time

import structlog
from pydantic import BaseModel, field_validator

from app.utils.coerce import as_float, as_int

from app.models.agent import (
    AnalyzerOutput,
    OrchestratorDecision,
    PracticeOutput,
    SessionContext,
    TeachingOutput,
)
from app.services.vertex_prompts import ORCHESTRATOR_SYSTEM
from app.config import get_settings
from app.services.llm_protocol import LLMService
from app.services.vertex_exceptions import VertexError
from app.utils.llm_error import emit_llm_error
from app.utils.locale import refresh_session_locale
from app.utils.tracing import trace_span

logger = structlog.get_logger(__name__)

# Number of consecutive failures before circuit breaker trips
CIRCUIT_BREAKER_LIMIT = 3


class _RoutingDecision(BaseModel):
    message_type: str
    route: str
    phase_transition: str | None = None
    hint_level: int = 0
    milestone_index: int = 0
    reason: str = ""

    @field_validator("hint_level", "milestone_index", mode="before")
    @classmethod
    def _coerce_int_fields(cls, v: object) -> int:
        return as_int(v, 0, 0)


VALID_ROUTES = {"analyzer", "teaching", "practice", "noop"}
VALID_MESSAGE_TYPES = {
    "new_problem", "step_submission", "stuck_signal",
    "clarification", "off_topic",
}

STUCK_PHRASES = (
    "stuck", "help", "hint", "don't know", "confused",
    "卡住了", "提示", "帮助", "不会", "不懂",
)


class OrchestratorAgent:
    def __init__(
        self,
        gemini: LLMService,
        analyzer,
        teaching,
        student_model,
        practice,
        exercises=None,
    ) -> None:
        self._gemini = gemini
        self._analyzer = analyzer
        self._teaching = teaching
        self._student_model = student_model
        self._practice = practice
        self._exercises = exercises
        self._consecutive_failures = 0

    # ── Main entry point ──────────────────────────────────────────

    async def handle_turn(
        self,
        ctx: SessionContext,
        student_message: str,
        queue: asyncio.Queue,
    ) -> dict:
        """
        Process one student turn end-to-end.
        Returns a dict of turn metadata consumed by the API route.
        """
        t0 = time.monotonic()

        async with trace_span(
            "orchestrator",
            "handle_turn",
            session_id=ctx.session_id,
            turn=ctx.turn_count + 1,
        ):
            refresh_session_locale(ctx, student_message)

            if self._message_signals_stuck(student_message):
                ctx.stuck_requested = True

            if self._consecutive_failures >= CIRCUIT_BREAKER_LIMIT:
                await emit_llm_error(
                    queue,
                    VertexError(
                        "MathMentor is temporarily unavailable after repeated model errors.",
                        retryable=False,
                    ),
                )
                return {"route": "noop", "circuit_breaker": True, "llm_failed": True}

            route = self._fast_route(ctx, student_message)
            decision: OrchestratorDecision | None = None

            if not route:
                decision = await self._llm_route(ctx, student_message)
                route = decision.route

            try:
                result = await self._dispatch(
                    route, ctx, student_message, decision, queue
                )
                if (
                    not result.get("llm_failed")
                    and route == "teaching"
                    and self._should_auto_practice(ctx, result)
                ):
                    ctx.phase = "wrap_up"
                    ctx.solution_ready = True
                    practice_result = await self._run_practice(ctx, queue)
                    result.update(practice_result)
                    result["trace_route"] = "practice"
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                logger.exception("orchestrator_dispatch_failed", route=route)
                if not isinstance(exc, VertexError):
                    await emit_llm_error(queue, exc)
                result = {"route": route, "error": str(exc), "llm_failed": True}

            if not result.get("llm_failed"):
                await queue.put({"type": "done"})

        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        trace_route = result.pop("trace_route", route)
        result["route"] = trace_route
        result["models_used"] = result.get(
            "models_used",
            self._default_models_used(route, trace_route),
        )
        return result

    def _default_models_used(self, route: str, trace_route: str) -> list[str]:
        settings = get_settings()
        if self._gemini.provider_name == "deepseek":
            flash = settings.deepseek_model_flash
            pro = settings.deepseek_model_pro
        else:
            flash = settings.gemini_model_flash
            pro = settings.gemini_model_pro
        if route == "analyzer":
            return [pro, flash]
        if trace_route == "critic->teaching":
            return [flash, flash]
        if route == "practice":
            return [pro]
        return [flash]

    # ── Deterministic pre-LLM routing ────────────────────────────

    @staticmethod
    def _fast_route(ctx: SessionContext, message: str) -> str | None:
        if ctx.session_ended:
            return "noop"
        if ctx.analysis is None:
            return "analyzer"
        if ctx.phase == "wrap_up":
            return "practice"
        if OrchestratorAgent._message_signals_stuck(message):
            return "teaching"
        return None

    @staticmethod
    def _message_signals_stuck(message: str) -> bool:
        lower = message.lower()
        return any(w in lower for w in STUCK_PHRASES)

    # ── LLM routing ───────────────────────────────────────────────

    async def _llm_route(
        self, ctx: SessionContext, message: str
    ) -> OrchestratorDecision:
        plan = ctx.plan
        total = len(plan.milestones) if plan else 3
        system = ORCHESTRATOR_SYSTEM.format_map({
            "phase": ctx.phase,
            "current_milestone": ctx.current_milestone,
            "total_milestones": total,
            "hint_level": ctx.hint_level,
            "solution_ready": ctx.solution_ready,
            "turn_count": ctx.turn_count,
        })
        try:
            raw: _RoutingDecision = await self._gemini.classify(
                system_prompt=system,
                user_message=message,
                schema=_RoutingDecision,
            )
            route = raw.route if raw.route in VALID_ROUTES else "teaching"
            msg_type = raw.message_type if raw.message_type in VALID_MESSAGE_TYPES else "clarification"
            return OrchestratorDecision(
                route=route,  # type: ignore[arg-type]
                message_type=msg_type,  # type: ignore[arg-type]
                reason=raw.reason,
                updated_phase=raw.phase_transition or ctx.phase,
                updated_hint_level=as_int(raw.hint_level, ctx.hint_level, 0, 3),
                updated_milestone=raw.milestone_index,
            )
        except Exception as exc:
            logger.warning("orchestrator_llm_route_failed", error=str(exc))
            return OrchestratorDecision(
                route="teaching",
                message_type="clarification",
                reason="LLM routing failed; defaulting to teaching",
                updated_phase=ctx.phase,
                updated_hint_level=as_int(ctx.hint_level, 0, 0, 3),
                updated_milestone=ctx.current_milestone,
            )

    # ── Dispatch ──────────────────────────────────────────────────

    async def _dispatch(
        self,
        route: str,
        ctx: SessionContext,
        student_message: str,
        decision: OrchestratorDecision | None,
        queue: asyncio.Queue,
    ) -> dict:
        if route == "analyzer":
            return await self._run_analyzer(ctx, queue)

        if route == "teaching":
            return await self._run_teaching(ctx, student_message, decision, queue)

        if route == "practice":
            return await self._run_practice(ctx, queue)

        return {}

    # ── Analyzer dispatch ─────────────────────────────────────────

    async def _run_analyzer(self, ctx: SessionContext, queue: asyncio.Queue) -> dict:
        await queue.put({"type": "analysis_start"})

        score = ctx.mastery
        output: AnalyzerOutput = await self._analyzer.run(
            problem_text=ctx.problem_text,
            limits_score=as_float(score.limits.score, 0.5),
            deriv_score=as_float(score.derivatives.score, 0.5),
            integ_score=as_float(score.integrals.score, 0.5),
            error_patterns=ctx.error_patterns,
            ui_locale=ctx.ui_locale,
        )

        # Store on context so teaching can use it this turn
        ctx.analysis = output.analysis
        ctx.plan = output.plan
        ctx.current_milestone_obj = output.plan.milestones[0] if output.plan.milestones else None

        await queue.put({
            "type": "analysis",
            "topic": output.analysis.topic,
            "subtopic": output.analysis.subtopic,
            "difficulty": output.analysis.difficulty,
            "methods": output.analysis.suggested_methods,
            "degraded": output.degraded,
        })

        # Immediately follow with opening question from Teaching Agent
        teaching_out = await self._teaching.run(
            ctx=ctx,
            student_message=output.opening_question_seed,
            critic_verdict=None,
            queue=queue,
        )

        ctx.phase = "tutoring"

        return {
            "trace_route": "analyzer->teaching",
            "analysis": output.analysis.model_dump(),
            "plan": output.plan.model_dump(),
            "plan_milestones": len(output.plan.milestones),
            "degraded": output.degraded,
            "response_text": teaching_out.response_text,
            "assessment": teaching_out.assessment.model_dump(),
            "leak_risk": teaching_out.answer_leak_risk,
            "milestone_advanced": teaching_out.milestone_advanced,
        }

    # ── Teaching dispatch ─────────────────────────────────────────

    async def _run_teaching(
        self,
        ctx: SessionContext,
        student_message: str,
        decision: OrchestratorDecision | None,
        queue: asyncio.Queue,
    ) -> dict:
        verdict_data = None
        critic_verdict = None
        critic_output = {}
        mastery_delta: dict[str, float] | None = None

        # Apply hint escalation if stuck
        if ctx.stuck_requested:
            ctx.hint_level = min(as_int(ctx.hint_level, 0, 0, 3) + 1, 3)

        # Run Critic if this looks like a step submission
        is_step = self._looks_like_step(student_message)
        if is_step and ctx.current_milestone_obj:
            critic_verdict = await self._student_model.evaluate_step(
                student_step=student_message,
                milestone_goal=ctx.current_milestone_obj.goal,
                skills_required=ctx.current_milestone_obj.skills_required,
            )
            critic_output = {
                "verdict": critic_verdict.verdict,
                "error_tag": critic_verdict.error_tag,
                "correct_parts": critic_verdict.correct_parts,
                "reasoning": critic_verdict.reasoning,
            }

            # Update mastery in context (DB write happens in SessionService)
            if ctx.analysis:
                sm_out = self._student_model.apply_mastery_update(
                    mastery=ctx.mastery,
                    topic=ctx.analysis.topic,
                    verdict=critic_verdict.verdict,
                    hint_level=ctx.hint_level,
                    error_tag=critic_verdict.error_tag,
                    error_patterns=ctx.error_patterns,
                )
                ctx.mastery = sm_out.updated_mastery
                ctx.error_patterns = sm_out.updated_error_patterns
                mastery_delta = sm_out.mastery_deltas or None

        teaching_out: TeachingOutput = await self._teaching.run(
            ctx=ctx,
            student_message=student_message,
            critic_verdict=critic_verdict,
            queue=queue,
        )

        trace_route = "critic->teaching" if critic_verdict else "teaching"

        return {
            "trace_route": trace_route,
            "verdict": critic_verdict.verdict if critic_verdict else None,
            "error_tag": critic_verdict.error_tag if critic_verdict else None,
            "mastery_delta": mastery_delta,
            "milestone_advanced": teaching_out.milestone_advanced,
            "hint_level": ctx.hint_level,
            "leak_risk": teaching_out.answer_leak_risk,
            "critic_output": critic_output if critic_output else None,
            "response_text": teaching_out.response_text,
            "assessment": teaching_out.assessment.model_dump(),
        }

    # ── Practice dispatch ─────────────────────────────────────────

    async def _run_practice(
        self, ctx: SessionContext, queue: asyncio.Queue
    ) -> dict:
        await queue.put({"type": "practice_start"})

        # Gather error tags from session steps
        error_tags = [
            s["error_tag"]
            for s in ctx.student_steps
            if s.get("error_tag")
        ]

        recent_prompts: list[str] = []
        if self._exercises:
            recent_prompts = await self._exercises.get_recent_problem_prompts(
                ctx.student_id
            )

        practice_out: PracticeOutput = await self._practice.run(
            ctx=ctx,
            error_tags=error_tags,
            recent_prompts=recent_prompts,
        )

        return {
            "exercises": practice_out.exercises,
            "rationale": practice_out.rationale,
            "source": practice_out.source,
        }

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _should_auto_practice(ctx: SessionContext, result: dict) -> bool:
        """Trigger Practice Agent when the final milestone is satisfied."""
        if not result.get("milestone_advanced"):
            return False
        plan = ctx.plan
        if not plan or not plan.milestones:
            return False
        return ctx.current_milestone + 1 >= len(plan.milestones)

    @staticmethod
    def _looks_like_step(message: str) -> bool:
        """Heuristic: message likely contains math work."""
        step_indicators = ["=", "+", "-", "*", "/", "\\", "^", "let ", "so ", "thus "]
        lower = message.lower()
        return any(ind in lower for ind in step_indicators) or len(message) > 30

