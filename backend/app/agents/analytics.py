"""
Learning Analytics Agent — infers strengths, weaknesses, mastery, and next step.

Architecture (two-layer):
  Layer 1 — Deterministic Python
    Pure computation from numeric mastery scores and aggregated error tags.
    Always succeeds; never touches the LLM.

  Layer 2 — LLM Enrichment (Gemini Flash)
    Generates recommended_subtopic and learning_tip.
    Falls back gracefully when the call fails (deterministic_only=True).

The agent is stateless: call run() once per analytics request.
"""
from __future__ import annotations

from collections import Counter

import structlog
from pydantic import BaseModel, Field

from app.models.agent import ErrorFrequency, LearningAnalyticsOutput
from app.models.student import ErrorPattern, MasterySnapshot, StudentStats
from app.services.mastery import mastery_label, mastery_pct
from app.services.vertex_prompts import LEARNING_ANALYTICS_SYSTEM
from app.services.llm_protocol import LLMService
from app.utils.locale import default_learning_tip, locale_instruction, normalize_locale

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────

MASTERY_STRENGTH_THRESHOLD = 0.70
MASTERY_WEAKNESS_THRESHOLD = 0.40
ERROR_WEAKNESS_COUNT = 3          # ≥ N occurrences → weakness
SEVERITY_HIGH = 5
SEVERITY_MEDIUM = 2

# Topic learning order used to break mastery ties
TOPIC_PREREQUISITES = ["limits", "derivatives", "integrals"]


# ── LLM output schemas ────────────────────────────────────────────

class _EnrichmentOutput(BaseModel):
    """Flash response schema — enriches deterministic base with LLM insights."""
    strengths: list[str] = []
    weaknesses: list[str] = []
    mastery_scores: dict[str, float] = Field(default_factory=dict)
    recommended_next_topic: str = ""
    recommended_subtopic: str = ""
    learning_tip: str = ""
    confidence: float = 0.8


# ── Agent ─────────────────────────────────────────────────────────

class AnalyticsAgent:
    """
    Usage:
        output = await agent.run(mastery, error_patterns, stats, recent_attempts)
        # output is a LearningAnalyticsOutput (serialisable to JSON)
    """

    def __init__(self, gemini: LLMService) -> None:
        self._gemini = gemini

    async def run(
        self,
        mastery: MasterySnapshot,
        error_patterns: list[ErrorPattern],
        stats: StudentStats,
        recent_attempts: list[dict],
        response_locale: str = "en",
    ) -> LearningAnalyticsOutput:
        """
        Full analytics pipeline.
        Layer 1 always runs; Layer 2 (LLM) is best-effort.
        """
        locale = normalize_locale(response_locale)
        base = self._deterministic(mastery, error_patterns, stats, recent_attempts)
        return await self._enrich(
            base, mastery, error_patterns, stats, recent_attempts, locale
        )

    # ── Layer 1: Deterministic ────────────────────────────────────

    def _deterministic(
        self,
        mastery: MasterySnapshot,
        error_patterns: list[ErrorPattern],
        stats: StudentStats,
        recent_attempts: list[dict],
    ) -> LearningAnalyticsOutput:
        scores = {
            "limits":      round(mastery.limits.score, 4),
            "derivatives": round(mastery.derivatives.score, 4),
            "integrals":   round(mastery.integrals.score, 4),
        }

        # Strengths: topics with high mastery
        strengths = [t for t, s in scores.items() if s >= MASTERY_STRENGTH_THRESHOLD]

        # Weaknesses: low mastery topics …
        weak_topics = {t for t, s in scores.items() if s < MASTERY_WEAKNESS_THRESHOLD}

        # … plus error tags seen ≥ ERROR_WEAKNESS_COUNT times
        for ep in error_patterns:
            if ep.count >= ERROR_WEAKNESS_COUNT:
                weak_topics.add(ep.tag)

        weaknesses = sorted(weak_topics)

        # Error summary — sorted by count desc, assign severity
        error_summary = sorted(
            [
                ErrorFrequency(
                    tag=ep.tag,
                    count=ep.count,
                    severity=(
                        "high"   if ep.count >= SEVERITY_HIGH   else
                        "medium" if ep.count >= SEVERITY_MEDIUM else
                        "low"
                    ),
                )
                for ep in error_patterns
            ],
            key=lambda e: e.count,
            reverse=True,
        )

        # Recommended next topic: lowest-mastery, prioritised by prerequisite order
        recommended = self._pick_next_topic(scores, recent_attempts)

        # Confidence: driven by evidence volume
        total = stats.total_steps_submitted
        confidence = 0.9 if total >= 10 else (0.7 if total >= 5 else 0.5)

        logger.info(
            "analytics_deterministic",
            strengths=strengths,
            weaknesses=list(weak_topics),
            recommended=recommended,
            attempts=total,
        )

        return LearningAnalyticsOutput(
            strengths=strengths,
            weaknesses=weaknesses,
            mastery_scores=scores,
            recommended_next_topic=recommended,
            recommended_subtopic="",          # filled by LLM enrichment
            error_summary=error_summary,
            learning_tip="",                   # filled by LLM enrichment
            confidence=confidence,
            deterministic_only=True,           # set False after enrichment
        )

    # ── Layer 2: LLM enrichment ───────────────────────────────────

    async def _enrich(
        self,
        base: LearningAnalyticsOutput,
        mastery: MasterySnapshot,
        error_patterns: list[ErrorPattern],
        stats: StudentStats,
        recent_attempts: list[dict],
        response_locale: str,
    ) -> LearningAnalyticsOutput:
        """
        Gemini Flash call: fills recommended_subtopic and learning_tip.
        Falls back to base on any failure.
        """
        # Summarise recent verdicts for the prompt
        verdict_counts: Counter[str] = Counter(
            a.get("verdict", "unclear") for a in recent_attempts
        )
        verdict_lines = ", ".join(
            f"{v}:{c}" for v, c in verdict_counts.most_common()
        ) or "no recent attempts"

        top_errors = ", ".join(
            ep.tag for ep in sorted(error_patterns, key=lambda e: e.count, reverse=True)[:5]
        ) or "none"

        system = LEARNING_ANALYTICS_SYSTEM.format_map({
            "limits_pct":      mastery_pct(mastery.limits.score),
            "deriv_pct":       mastery_pct(mastery.derivatives.score),
            "integ_pct":       mastery_pct(mastery.integrals.score),
            "total_attempts":  stats.total_steps_submitted,
            "sessions_done":   stats.total_sessions,
            "exercises_done":  stats.total_exercises_done,
            "top_errors":      top_errors,
            "recent_window":   min(len(recent_attempts), 20),
            "verdict_summary": verdict_lines,
            "locale_instruction": locale_instruction(response_locale),
        })

        user_msg = (
            f"Student mastery snapshot:\n"
            f"  limits      = {mastery_pct(mastery.limits.score)}% "
            f"({mastery_label(mastery.limits.score)})\n"
            f"  derivatives = {mastery_pct(mastery.derivatives.score)}% "
            f"({mastery_label(mastery.derivatives.score)})\n"
            f"  integrals   = {mastery_pct(mastery.integrals.score)}% "
            f"({mastery_label(mastery.integrals.score)})\n\n"
            f"Error patterns (tag: count):\n"
            + "\n".join(f"  {ep.tag}: {ep.count}" for ep in error_patterns[:10])
            + f"\n\nRecommended next topic (deterministic): {base.recommended_next_topic}"
        )

        try:
            raw: _EnrichmentOutput = await self._gemini.classify(
                system_prompt=system,
                user_message=user_msg,
                schema=_EnrichmentOutput,
            )

            # Trust LLM subtopic and tip; keep deterministic mastery/strengths/weaknesses
            # (LLM must not alter the numeric scores — they come from verified DB data)
            enriched = base.model_copy(update={
                "recommended_subtopic": raw.recommended_subtopic or base.recommended_subtopic,
                "learning_tip":         raw.learning_tip or base.learning_tip,
                "confidence":           raw.confidence if raw.confidence else base.confidence,
                "deterministic_only":   False,
            })

            logger.info(
                "analytics_enriched",
                recommended_subtopic=enriched.recommended_subtopic,
                confidence=enriched.confidence,
            )
            return enriched

        except Exception as exc:
            logger.warning("analytics_enrichment_failed", error=str(exc))
            fallback = base.model_copy(update={
                "learning_tip": base.learning_tip or default_learning_tip(response_locale),
            })
            return fallback  # deterministic_only remains True

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _pick_next_topic(
        scores: dict[str, float],
        recent_attempts: list[dict],
    ) -> str:
        """
        Choose the most leveraged topic.
        Priority order:
          1. Weakest topic that has at least one recent attempt
             (evidence the student is actively working there).
          2. If no recent attempts for any topic, pick the globally weakest.
          3. Break ties using TOPIC_PREREQUISITES order.
        """
        recent_topics: set[str] = set()
        for a in recent_attempts:
            topic = (a.get("mastery_impact") or {}).get("topic", "")
            if topic:
                recent_topics.add(topic)

        # Sort by score asc, then by prerequisite order (index asc)
        def sort_key(t: str) -> tuple[float, int]:
            return (scores.get(t, 0.5), TOPIC_PREREQUISITES.index(t))

        candidates = sorted(TOPIC_PREREQUISITES, key=sort_key)

        # Prefer topics with recent activity
        active_candidates = [t for t in candidates if t in recent_topics]
        if active_candidates:
            return active_candidates[0]

        return candidates[0]
