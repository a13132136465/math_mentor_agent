"""Deterministic answer-leak heuristics — complements LLM leak_check."""
from __future__ import annotations

import re

# Affirmations that confirm a complete student solution (high leak signal)
_AFFIRMATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bnailed\b",
        r"\bthat'?s\s+(right|correct)\b",
        r"\byou(?:'ve|\s+have)\s+(got\s+it|nailed|solved)\b",
        r"\bthe\s+(full\s+)?derivative\s+is\b",
        r"\bthe\s+answer\s+is\b",
        r"\bit'?s\s+correct\b",
        r"\byou(?:'re|\s+are)\s+correct\b",
        r"\bperfect!?\b",
        r"\bexactly\s+right\b",
        r"\bthat'?s\s+exactly\b",
        r"\bexactly\s+the\s+derivative\b",
        r"\bcorrect\s+derivative\b",
        r"\bthe\s+correct\s+derivative\b",
    )
)

_DERIV_NOTATION = re.compile(
    r"(?:f|g|y)\s*['′]\s*\(|\\frac\s*\{\\s*d\s*\}",
    re.IGNORECASE,
)

_COMPLETENESS_QUESTION = re.compile(
    r"\b(is\s+that|is\s+this|are\s+we)\b.{0,40}\b(complete|full|done|correct|the\s+derivative)\b",
    re.IGNORECASE,
)


def heuristic_leak_risk(draft_response: str, student_message: str = "") -> float:
    """
    Return 0.0–1.0 leak risk from pattern matching.
    Used as max() with LLM leak_check so confirmations are caught reliably.
    """
    if not draft_response.strip():
        return 0.0

    text = draft_response.lower()
    risk = 0.0

    for pat in _AFFIRMATION_PATTERNS:
        if pat.search(text):
            risk = max(risk, 0.55)

    student = (student_message or "").lower()
    if student and _COMPLETENESS_QUESTION.search(student):
        if risk >= 0.55 or re.search(
            r"\b(yes|correct|right|full|complete|nailed|exactly)\b", text
        ):
            risk = max(risk, 0.75)
        elif re.search(r"\bderivative\b", text) and re.search(r"\bexactly\b", text):
            risk = max(risk, 0.75)

    if student and _DERIV_NOTATION.search(student) and _DERIV_NOTATION.search(text):
        if risk >= 0.55:
            risk = max(risk, 0.70)

    return min(1.0, risk)
