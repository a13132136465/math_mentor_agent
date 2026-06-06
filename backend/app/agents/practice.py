"""
Practice Agent — two generation modes.

  run()             Generate 3 targeted post-session exercises.
  generate_single() Generate ONE focused exercise on demand.

Both modes use numeric difficulty (1–5) and store a full worked
answer server-side for later reveal.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from app.models.agent import PracticeOutput, SessionContext
from app.models.exercise import SingleExerciseResponse
from app.models.student import ErrorPattern, MasterySnapshot
from app.services.mastery import mastery_pct
from app.services.vertex_prompts import PRACTICE_SYSTEM, SINGLE_EXERCISE_SYSTEM
from app.services.llm_protocol import LLMService
from app.utils.locale import locale_instruction

logger = structlog.get_logger(__name__)

VALID_TOPICS = {"limits", "derivatives", "integrals"}
TOPIC_PREREQUISITES = ["limits", "derivatives", "integrals"]


# ── Difficulty helpers ────────────────────────────────────────────

def _difficulty_from_score(score: float) -> int:
    """Map mastery score [0, 1] → numeric difficulty 1-5."""
    if score < 0.40:
        return 2   # easy
    if score < 0.70:
        return 3   # medium
    return 4       # hard


def _clamp_difficulty(d: int | str) -> int:
    """Accept either int or legacy string, always return int 1-5."""
    if isinstance(d, str):
        mapping = {"easy": 2, "medium": 3, "hard": 4}
        return mapping.get(d.lower(), 3)
    return max(1, min(5, d))


# ── LLM output schemas ────────────────────────────────────────────

class _ExerciseItem(BaseModel):
    id: str = "ex-1"
    prompt: str
    topic: str
    subtopic: str = ""
    difficulty: int = Field(default=3, ge=1, le=5)
    target_skill: str = ""
    learning_intention: str = ""
    answer: str = ""


class _BatchOutput(BaseModel):
    exercises: list[_ExerciseItem]
    rationale: str = ""


class _SingleOutput(BaseModel):
    """Mirror of SINGLE_EXERCISE_SYSTEM output schema."""
    problem: str
    difficulty: int = Field(default=3, ge=1, le=5)
    topic: str
    subtopic: str = ""
    target_skill: str = ""
    learning_intention: str = ""
    answer: str = ""


# ── Agent ─────────────────────────────────────────────────────────

class PracticeAgent:
    def __init__(self, gemini: LLMService, problem_library=None) -> None:
        self._gemini = gemini
        self._library = problem_library

    # ── Batch (session-end) ───────────────────────────────────────

    async def run(
        self,
        ctx: SessionContext,
        error_tags: list[str],
        recent_prompts: list[str],
    ) -> PracticeOutput:
        """
        Generate 3 personalised exercises targeting session errors.
        Falls back to template exercises if generation fails.
        """
        topic   = ctx.analysis.topic    if ctx.analysis else "derivatives"
        subtopic = ctx.analysis.subtopic if ctx.analysis else "power_rule"
        score   = ctx.mastery.get_score(topic)

        plan = ctx.plan
        milestones_done  = sum(1 for m in plan.milestones if m.completed) if plan else 0
        milestones_total = len(plan.milestones) if plan else 3

        system = PRACTICE_SYSTEM.format_map({
            "topic":           topic,
            "subtopic":        subtopic,
            "milestones_done": milestones_done,
            "milestones_total":milestones_total,
            "error_tags":      ", ".join(set(error_tags)) or "none",
            "hint_level":      ctx.hint_level,
            "mastery_pct":     score,
            "error_patterns":  ", ".join(ctx.error_patterns[-5:]) or "none",
            "locale_instruction": locale_instruction(ctx.response_locale),
        })

        avoid_note = ""
        if recent_prompts:
            avoid_note = (
                "\n\n## Previously seen problems (DO NOT reuse or create near-duplicates)\n"
                + "\n".join(f"- {p[:100]}" for p in recent_prompts[:5])
            )

        for attempt in range(3):
            try:
                raw: _BatchOutput = await self._gemini.classify(
                    system_prompt=system,
                    user_message=f"Generate exercises.{avoid_note}",
                    schema=_BatchOutput,
                )
                exercises = self._validate_batch(raw.exercises, topic)
                if len(exercises) >= 2:
                    logger.info(
                        "practice_batch_ok",
                        count=len(exercises),
                        topic=topic,
                        attempt=attempt + 1,
                    )
                    return PracticeOutput(
                        exercises=[e.model_dump() for e in exercises[:3]],
                        rationale=raw.rationale,
                        source="generated",
                    )
                avoid_note += "\n(Previous attempt produced insufficient exercises.)"
            except Exception as exc:
                logger.warning("practice_batch_failed", attempt=attempt + 1, error=str(exc))

        library_exercises = await self._library_fallback(topic, subtopic, score)
        if library_exercises:
            return PracticeOutput(
                exercises=library_exercises,
                rationale="Curated problems from problem_library (generation unavailable).",
                source="problem_library",
            )

        logger.warning("practice_using_fallback", topic=topic)
        return PracticeOutput(
            exercises=self._fallback_exercises(topic, score),
            rationale="Generated using fallback templates due to service error.",
            source="fallback",
        )

    # ── Single (on-demand) ────────────────────────────────────────

    async def generate_single(
        self,
        mastery: MasterySnapshot,
        error_patterns: list[ErrorPattern],
        topic: str | None = None,
        avoid_topics: list[str] | None = None,
        response_locale: str = "en",
    ) -> SingleExerciseResponse:
        """
        Generate ONE focused exercise targeting the student's weakest area.
        Returns SingleExerciseResponse including the worked answer.
        """
        # Auto-select topic if not provided
        if not topic or topic not in VALID_TOPICS:
            topic = self._pick_weak_topic(mastery)

        score = mastery.get_score(topic)
        suggested_diff = _difficulty_from_score(score)
        subtopic = self._pick_subtopic(topic, error_patterns)

        top_errors = ", ".join(
            ep.tag for ep in sorted(error_patterns, key=lambda e: e.count, reverse=True)[:3]
        ) or "none"

        system = SINGLE_EXERCISE_SYSTEM.format_map({
            "topic":               topic,
            "subtopic":            subtopic,
            "mastery_pct":         mastery.get_score(topic),
            "suggested_difficulty": suggested_diff,
            "error_patterns":      top_errors,
            "avoid_topics":        ", ".join(avoid_topics or []) or "none",
            "locale_instruction":  locale_instruction(response_locale),
        })

        for attempt in range(3):
            try:
                raw: _SingleOutput = await self._gemini.classify(
                    system_prompt=system,
                    user_message="Generate one exercise.",
                    schema=_SingleOutput,
                )
                if not raw.problem.strip():
                    raise ValueError("Empty problem text returned")

                result = SingleExerciseResponse(
                    problem=raw.problem,
                    difficulty=_clamp_difficulty(raw.difficulty),
                    topic=raw.topic if raw.topic in VALID_TOPICS else topic,
                    subtopic=raw.subtopic or subtopic,
                    target_skill=raw.target_skill,
                    learning_intention=raw.learning_intention,
                    answer=raw.answer,
                )
                logger.info(
                    "practice_single_ok",
                    topic=result.topic,
                    difficulty=result.difficulty,
                    has_answer=bool(result.answer),
                    attempt=attempt + 1,
                )
                return result

            except Exception as exc:
                logger.warning(
                    "practice_single_failed", attempt=attempt + 1, error=str(exc)
                )

        # Fallback: pick first template exercise for topic
        logger.warning("practice_single_using_fallback", topic=topic)
        fallback = self._fallback_exercises(topic, score)[0]
        return SingleExerciseResponse(
            problem=fallback["prompt"],
            difficulty=fallback["difficulty"],
            topic=fallback["topic"],
            subtopic=fallback["subtopic"],
            target_skill=fallback.get("target_skill", ""),
            learning_intention=fallback.get("learning_intention", ""),
            answer=fallback.get("answer", ""),
        )

    # ── Validation ────────────────────────────────────────────────

    @staticmethod
    def _validate_batch(
        items: list[_ExerciseItem], expected_topic: str
    ) -> list[_ExerciseItem]:
        valid: list[_ExerciseItem] = []
        seen_subtopics: set[str] = set()
        for item in items:
            if item.topic not in VALID_TOPICS:
                item.topic = expected_topic
            item.difficulty = _clamp_difficulty(item.difficulty)
            if item.subtopic in seen_subtopics:
                continue  # enforce variety
            seen_subtopics.add(item.subtopic)
            valid.append(item)
        return valid

    # ── Topic / subtopic selection ────────────────────────────────

    @staticmethod
    def _pick_weak_topic(mastery: MasterySnapshot) -> str:
        scores = {
            "limits":      mastery.limits.score,
            "derivatives": mastery.derivatives.score,
            "integrals":   mastery.integrals.score,
        }
        return min(TOPIC_PREREQUISITES, key=lambda t: (scores[t], TOPIC_PREREQUISITES.index(t)))

    @staticmethod
    def _pick_subtopic(topic: str, error_patterns: list[ErrorPattern]) -> str:
        """Map persistent error tags to a concrete subtopic, fallback to first in taxonomy."""
        _error_to_subtopic: dict[str, str] = {
            "missing_chain_rule_factor":      "chain_rule",
            "wrong_derivative_rule":          "power_rule",
            "forgot_constant_of_integration": "ftc_part2",
            "wrong_integral_bounds":          "ftc_part2",
            "limit_form_error":               "indeterminate_forms",
            "wrong_trig_identity":            "trig",
            "incorrect_factoring":            "indeterminate_forms",
        }
        _topic_defaults: dict[str, str] = {
            "limits":      "indeterminate_forms",
            "derivatives": "chain_rule",
            "integrals":   "u_substitution",
        }
        if error_patterns:
            top_tag = max(error_patterns, key=lambda e: e.count).tag
            if top_tag in _error_to_subtopic:
                return _error_to_subtopic[top_tag]
        return _topic_defaults.get(topic, "power_rule")

    async def _library_fallback(
        self, topic: str, subtopic: str, score: float
    ) -> list[dict]:
        if not self._library:
            return []
        d = _difficulty_from_score(score)
        docs = await self._library.find_by_topic(
            topic, subtopic=subtopic, difficulty=d, limit=3
        )
        if len(docs) < 2:
            docs = await self._library.find_by_topic(topic, limit=3)
        if not docs:
            return []
        exercises: list[dict] = []
        for i, doc in enumerate(docs[:3], start=1):
            exercises.append({
                "id": f"lib-{i}",
                "prompt": doc.get("prompt", ""),
                "topic": doc.get("topic", topic),
                "subtopic": doc.get("subtopic", subtopic),
                "difficulty": doc.get("difficulty", d),
                "target_skill": doc.get("target_skill", ""),
                "learning_intention": doc.get("learning_intention", ""),
                "answer": doc.get("answer", ""),
            })
        return exercises

    # ── Fallback templates ────────────────────────────────────────

    @staticmethod
    def _fallback_exercises(topic: str, score: float) -> list[dict]:
        d = _difficulty_from_score(score)
        templates: dict[str, list[dict]] = {
            "derivatives": [
                {
                    "id": "ex-1",
                    "prompt": r"Find \( \frac{d}{dx}[x^3 - 2x + 1] \)",
                    "topic": "derivatives", "subtopic": "power_rule",
                    "difficulty": d, "target_skill": "power_rule",
                    "learning_intention": "Practise the power rule on a polynomial.",
                    "answer": r"\( 3x^2 - 2 \)",
                },
                {
                    "id": "ex-2",
                    "prompt": r"Differentiate \( f(x) = \sin(2x) \)",
                    "topic": "derivatives", "subtopic": "chain_rule",
                    "difficulty": min(d + 1, 5), "target_skill": "chain_rule",
                    "learning_intention": "Apply the chain rule to a trig function.",
                    "answer": r"\( f'(x) = 2\cos(2x) \)",
                },
                {
                    "id": "ex-3",
                    "prompt": r"Find \( \frac{d}{dx}[\ln(x^2 + 1)] \)",
                    "topic": "derivatives", "subtopic": "chain_rule",
                    "difficulty": min(d + 1, 5), "target_skill": "chain_rule",
                    "learning_intention": "Chain rule with a logarithmic outer function.",
                    "answer": r"\( \frac{2x}{x^2 + 1} \)",
                },
            ],
            "limits": [
                {
                    "id": "ex-1",
                    "prompt": r"Evaluate \( \lim_{x \to 2} \frac{x^2 - 4}{x - 2} \)",
                    "topic": "limits", "subtopic": "indeterminate_forms",
                    "difficulty": d, "target_skill": "factoring",
                    "learning_intention": "Resolve a 0/0 indeterminate form by factoring.",
                    "answer": r"Factor numerator: \( \frac{(x-2)(x+2)}{x-2} = x+2 \). Limit \( = 4 \).",
                },
                {
                    "id": "ex-2",
                    "prompt": r"Find \( \lim_{x \to \infty} \frac{3x^2}{x^2 + 1} \)",
                    "topic": "limits", "subtopic": "infinity_limits",
                    "difficulty": d, "target_skill": "infinity_limits",
                    "learning_intention": "Divide numerator and denominator by the highest power.",
                    "answer": r"Divide by \( x^2 \): \( \frac{3}{1 + 1/x^2} \to 3 \) as \( x\to\infty \).",
                },
                {
                    "id": "ex-3",
                    "prompt": r"Evaluate \( \lim_{x \to 0} \frac{\sin(3x)}{x} \)",
                    "topic": "limits", "subtopic": "lhopital",
                    "difficulty": d, "target_skill": "standard_limit",
                    "learning_intention": r"Use the standard limit \( \lim_{u\to0}\sin(u)/u = 1 \).",
                    "answer": r"Rewrite as \( 3 \cdot \frac{\sin(3x)}{3x} \to 3 \cdot 1 = 3 \).",
                },
            ],
            "integrals": [
                {
                    "id": "ex-1",
                    "prompt": r"Compute \( \int (3x^2 - 4x + 2)\,dx \)",
                    "topic": "integrals", "subtopic": "ftc_part2",
                    "difficulty": d, "target_skill": "power_rule_integration",
                    "learning_intention": "Apply the power rule for integration term by term.",
                    "answer": r"\( x^3 - 2x^2 + 2x + C \)",
                },
                {
                    "id": "ex-2",
                    "prompt": r"Evaluate \( \int_0^1 x^2\,dx \)",
                    "topic": "integrals", "subtopic": "ftc_part2",
                    "difficulty": d, "target_skill": "definite_integral",
                    "learning_intention": "Compute a definite integral using FTC Part 2.",
                    "answer": r"\( \left[\frac{x^3}{3}\right]_0^1 = \frac{1}{3} \)",
                },
                {
                    "id": "ex-3",
                    "prompt": r"Find \( \int \cos(x)\,e^{\sin x}\,dx \)",
                    "topic": "integrals", "subtopic": "u_substitution",
                    "difficulty": min(d + 1, 5), "target_skill": "u_substitution",
                    "learning_intention": "Identify the inner function and apply u-substitution.",
                    "answer": r"Let \( u = \sin x \), \( du = \cos x\,dx \). Integral \( = e^u + C = e^{\sin x} + C \).",
                },
            ],
        }
        return templates.get(topic, templates["derivatives"])
