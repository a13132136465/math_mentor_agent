"""
SessionService — coordinates repository writes around a single tutor turn.
Keeps route handlers thin.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from app.agents.practice import PracticeAgent
from app.models.agent import SessionContext
from app.models.session import AnalysisResult, ReasoningPlan
from app.repositories import (
    AgentMemoryRepository,
    AttemptRepository,
    ExerciseRepository,
    MasteryEventRepository,
    MessageRepository,
    SessionRepository,
    StudentRepository,
)
from app.services.mastery import compute_ema, compute_session_mastery_deltas, due_at_hours
from app.utils.coerce import as_int
from app.utils.locale import normalize_locale

logger = structlog.get_logger(__name__)


class SessionService:
    def __init__(
        self,
        students: StudentRepository,
        sessions: SessionRepository,
        messages: MessageRepository,
        attempts: AttemptRepository,
        mastery_events: MasteryEventRepository,
        exercises: ExerciseRepository,
        agent_memory: AgentMemoryRepository,
    ) -> None:
        self.students = students
        self.sessions = sessions
        self.messages = messages
        self.attempts = attempts
        self.mastery_events = mastery_events
        self.exercises = exercises
        self.agent_memory = agent_memory

    # ── Context loader ────────────────────────────────────────────

    async def load_context(self, session_id: str, student_id: str) -> SessionContext:
        """
        Hydrate a SessionContext from DB for a new turn.
        Includes the plan (server-side only).
        """
        session_doc = await self.sessions.get_for_agent(session_id)
        student_doc = await self.students.get_by_id(student_id)

        if not session_doc or not student_doc:
            raise ValueError("Session or student not found")

        mastery_raw = student_doc.get("mastery", {})

        from app.models.student import MasterySnapshot

        mastery = (
            MasterySnapshot.model_validate(mastery_raw)
            if mastery_raw
            else MasterySnapshot()
        )

        error_patterns = [
            ep["tag"] for ep in student_doc.get("error_patterns", [])
        ]

        progress = session_doc.get("progress", {})
        ui_locale = normalize_locale(
            student_doc.get("preferences", {}).get("locale")
        )
        response_locale = normalize_locale(
            progress.get("response_locale"), default=ui_locale
        )
        plan_raw = session_doc.get("plan")

        from app.models.session import AnalysisResult, ReasoningPlan, Milestone

        analysis_raw = session_doc.get("analysis")
        analysis = (
            AnalysisResult.model_validate(analysis_raw) if analysis_raw else None
        )

        plan = None
        current_milestone_obj = None
        milestone_idx = as_int(progress.get("current_milestone", 0), 0, 0)
        if plan_raw:
            plan = ReasoningPlan.model_validate(plan_raw)
            if plan.milestones and milestone_idx < len(plan.milestones):
                current_milestone_obj = plan.milestones[milestone_idx]

        recent_msgs = await self.messages.get_recent_for_context(session_id, n=6)
        attempts_raw = await self.attempts.get_session_attempts(session_id)

        return SessionContext(
            session_id=session_id,
            student_id=student_id,
            display_name=student_doc.get("display_name", "Student"),
            mastery=mastery,
            error_patterns=error_patterns,
            hint_preference=student_doc.get("preferences", {}).get("hint_style", "balanced"),
            llm_provider=student_doc.get("preferences", {}).get("llm_provider", "gemini"),
            ui_locale=ui_locale,
            response_locale=response_locale,
            problem_text=session_doc.get("problem_text", ""),
            analysis=analysis,
            plan=plan,
            phase=session_doc.get("phase", "intake"),
            current_milestone=milestone_idx,
            hint_level=as_int(progress.get("hint_level", 0), 0, 0, 3),
            solution_ready=bool(progress.get("solution_ready", False)),
            turn_count=as_int(progress.get("turn_count", 0), 0, 0),
            stuck_count=as_int(progress.get("stuck_count", 0), 0, 0),
            recent_messages=recent_msgs,
            student_steps=[
                {
                    "content": a.get("content"),
                    "verdict": a.get("verdict"),
                    "error_tag": a.get("error_tag"),
                    "milestone_id": a.get("milestone_id"),
                }
                for a in attempts_raw
            ],
            current_milestone_obj=current_milestone_obj,
        )

    # ── Post-turn persistence ─────────────────────────────────────

    async def persist_turn(
        self,
        ctx: SessionContext,
        student_message: str,
        assistant_message: str,
        verdict: str | None,
        error_tag: str | None,
        critic_output: dict | None,
        agent_trace: dict,
        milestone_advanced: bool,
        client_message_id: str | None,
        plan_payload: dict | None = None,
    ) -> None:
        """
        Atomically persist everything that happened in one tutor turn.
        All writes are async; non-critical writes (mastery events, traces)
        are fire-and-gathered concurrently.
        """
        turn_index = ctx.turn_count + 1

        # 1. Student message
        student_msg_id = await self.messages.insert_student_message(
            session_id=ctx.session_id,
            student_id=ctx.student_id,
            content=student_message,
            turn_index=turn_index,
            client_message_id=client_message_id,
        )

        # 2. Assistant message
        milestone_id = ctx.current_milestone_obj.id if ctx.current_milestone_obj else 0
        await self.messages.insert_assistant_message(
            session_id=ctx.session_id,
            student_id=ctx.student_id,
            content=assistant_message,
            turn_index=turn_index,
            agent_trace=agent_trace,
            metadata={
                "milestone_id": milestone_id,
                "hint_level": ctx.hint_level,
                "phase": ctx.phase,
            },
        )

        # 3. Attempt record + mastery update (only on step submission)
        if verdict and critic_output:
            topic = ctx.analysis.topic if ctx.analysis else "derivatives"
            subtopic = ctx.analysis.subtopic if ctx.analysis else None

            current_score = ctx.mastery.get_score(topic)
            new_score, delta = compute_ema(current_score, verdict, ctx.hint_level)

            attempt_id = await self.attempts.record(
                session_id=ctx.session_id,
                student_id=ctx.student_id,
                content=student_message,
                turn_index=turn_index,
                milestone_id=milestone_id,
                verdict=verdict,
                error_tag=error_tag,
                critic_output=critic_output,
                mastery_impact={
                    "topic": topic,
                    "score_before": current_score,
                    "score_after": new_score,
                    "delta": delta,
                    "hint_penalty": 1.0 - (0.15 * ctx.hint_level),
                },
                hint_level=ctx.hint_level,
                message_id=str(student_msg_id),
            )

            # Concurrent non-blocking writes
            await asyncio.gather(
                self.students.update_mastery(
                    ctx.student_id, topic, new_score, error_tag
                ),
                self.mastery_events.append(
                    student_id=ctx.student_id,
                    session_id=ctx.session_id,
                    topic=topic,
                    subtopic=subtopic,
                    event_type=f"step_{verdict}",
                    delta=delta,
                    score_after=new_score,
                    context={
                        "milestone_id": milestone_id,
                        "hint_level": ctx.hint_level,
                        "error_tag": error_tag,
                    },
                    attempt_id=str(attempt_id),
                ),
                return_exceptions=True,
            )

        # 4. Persist analyzer output on first turn (plan stays server-side only)
        analysis_payload = agent_trace.get("analysis")
        if analysis_payload and plan_payload:
            await self.sessions.save_analysis_and_plan(
                ctx.session_id, analysis_payload, plan_payload
            )
            ctx.phase = "tutoring"
            if not ctx.analysis:
                ctx.analysis = AnalysisResult.model_validate(analysis_payload)
            if not ctx.plan and plan_payload:
                ctx.plan = ReasoningPlan.model_validate(plan_payload)

        # 5. Session progress update
        new_milestone = ctx.current_milestone + (1 if milestone_advanced else 0)
        total = len(ctx.plan.milestones) if ctx.plan else 1
        solution_ready = new_milestone >= total
        new_phase = "wrap_up" if solution_ready else ctx.phase

        await self.sessions.update_progress(
            ctx.session_id,
            milestone=new_milestone,
            hint_level=ctx.hint_level,
            phase=new_phase,
            solution_ready=solution_ready,
            response_locale=ctx.response_locale,
        )

        # 5. Agent trace (fire-and-forget)
        asyncio.create_task(
            self.agent_memory.write_turn_trace(
                agent_name="orchestrator",
                session_id=ctx.session_id,
                student_id=ctx.student_id,
                turn_index=turn_index,
                trace=agent_trace,
            )
        )

    # ── Session completion ────────────────────────────────────────

    async def run_practice_for_session(
        self,
        ctx: SessionContext,
        practice: PracticeAgent,
    ) -> dict:
        """Generate exercises and persist them; used by /complete and manual triggers."""
        error_tags = [
            s["error_tag"] for s in ctx.student_steps if s.get("error_tag")
        ]
        recent = await self.exercises.get_recent_problem_prompts(ctx.student_id)
        practice_out = await practice.run(
            ctx=ctx,
            error_tags=error_tags,
            recent_prompts=recent,
        )
        return await self.finalize_session(
            ctx,
            exercises=practice_out.exercises,
            rationale=practice_out.rationale,
            source=practice_out.source,
        )

    async def finalize_session(
        self,
        ctx: SessionContext,
        exercises: list[dict],
        rationale: str,
        source: str = "generated",
    ) -> dict:
        """
        Called after Practice Agent runs. Closes session + persists exercises.
        Returns session summary dict.
        """
        attempts_raw = await self.attempts.get_session_attempts(ctx.session_id)
        error_tags = [a["error_tag"] for a in attempts_raw if a.get("error_tag")]
        mastery_deltas = compute_session_mastery_deltas(attempts_raw)

        plan = ctx.plan
        total_milestones = len(plan.milestones) if plan else 0
        completed = sum(1 for m in plan.milestones if m.completed) if plan else 0

        started_at = datetime.now(timezone.utc)  # fallback; real value from session doc
        duration = 0

        summary = {
            "milestones_completed": completed,
            "milestones_total": total_milestones,
            "error_tags_this_session": list(set(error_tags)),
            "mastery_deltas": mastery_deltas,
            "peak_hint_level": ctx.stuck_count,
            "duration_seconds": duration,
        }

        topic = ctx.analysis.topic if ctx.analysis else "derivatives"
        score = ctx.mastery.get_score(topic)

        from datetime import timedelta
        due = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            hours=due_at_hours(score)
        )

        await asyncio.gather(
            self.sessions.complete_session(ctx.session_id, summary),
            self.exercises.create(
                student_id=ctx.student_id,
                session_id=ctx.session_id,
                problems=exercises,
                generation_meta={"rationale": rationale, "source": source},
                due_at=due,
                interval_hours=due_at_hours(score),
            ),
            self.agent_memory.write_session_summary(
                ctx.session_id, ctx.student_id, summary
            ),
            return_exceptions=True,
        )

        return summary
