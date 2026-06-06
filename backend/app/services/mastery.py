"""
Mastery scoring service — deterministic EMA updates, no LLM.
"""
from __future__ import annotations

from app.utils.coerce import as_float, as_int

EMA_ALPHA = 0.15  # smoothing factor

_VERDICT_SCORE: dict[str, float] = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "incorrect": 0.0,
    "unclear": 0.3,
}

_HINT_PENALTY: dict[int, float] = {
    0: 1.0,
    1: 0.85,
    2: 0.65,
    3: 0.40,
}


def compute_ema(current: float, verdict: str, hint_level: int) -> tuple[float, float]:
    """
    Apply one EMA step.

    Returns (new_score, delta):
      new_score ∈ [0.0, 1.0], rounded to 4dp
      delta     = new_score - current
    """
    cur = as_float(current, 0.5)
    lvl = as_int(hint_level, 0, 0, 3)
    raw = _VERDICT_SCORE.get(verdict, 0.3)
    penalty = _HINT_PENALTY.get(lvl, 1.0)
    observation = raw * penalty
    new_score = cur + EMA_ALPHA * (observation - cur)
    new_score = round(max(0.0, min(1.0, new_score)), 4)
    delta = round(new_score - cur, 6)
    return new_score, delta


def mastery_label(score: float) -> str:
    s = as_float(score, 0.5)
    if s < 0.4:
        return "beginner"
    if s < 0.7:
        return "developing"
    return "proficient"


def mastery_pct(score: float) -> float:
    return round(as_float(score, 0.5) * 100, 1)


def due_at_hours(score: float) -> int:
    """Spaced repetition interval based on mastery score."""
    s = as_float(score, 0.5)
    if s < 0.4:
        return 4
    if s < 0.6:
        return 24
    if s < 0.8:
        return 72
    return 168  # 1 week


def compute_session_mastery_deltas(
    attempts: list[dict],
) -> dict[str, float]:
    """
    Given a list of attempt dicts with `mastery_impact` embedded,
    sum up per-topic deltas for the session summary.
    """
    deltas: dict[str, float] = {}
    for a in attempts:
        impact = a.get("mastery_impact")
        if not impact:
            continue
        topic = impact.get("topic", "")
        delta = as_float(impact.get("delta", 0.0), 0.0)
        deltas[topic] = round(deltas.get(topic, 0.0) + delta, 6)
    return deltas
