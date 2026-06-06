"""
Locale detection and prompt instructions for bilingual (en/zh) student-facing LLM output.
"""
from __future__ import annotations

import re
from typing import Literal

SupportedLocale = Literal["en", "zh"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[a-zA-Z]")

_STUCK_MESSAGES: dict[SupportedLocale, str] = {
    "en": "I'm stuck — can I get a hint?",
    "zh": "我卡住了，能给我一点提示吗？",
}

_DEFAULT_TIPS: dict[SupportedLocale, str] = {
    "en": "Start with limits — they are the foundation of all calculus.",
    "zh": "从极限开始 — 它们是所有微积分的基础。",
}

LOCALE_INSTRUCTIONS: dict[SupportedLocale, str] = {
    "en": (
        "Respond in English. All student-facing text (questions, hints, explanations, "
        "learning tips) must be in English. Keep mathematical notation in standard LaTeX."
    ),
    "zh": (
        "请使用简体中文回复。所有面向学生的文字（提问、提示、说明、学习建议）必须使用中文。"
        "数学公式仍使用标准 LaTeX 格式。"
    ),
}


def normalize_locale(value: str | None, default: SupportedLocale = "en") -> SupportedLocale:
    if not value:
        return default
    lowered = value.lower().strip()
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("en"):
        return "en"
    return default


def detect_locale(text: str) -> SupportedLocale | None:
    """Infer locale from a single text snippet. Returns None when ambiguous."""
    if not text or not text.strip():
        return None

    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))

    if cjk >= 2 or (cjk >= 1 and cjk >= latin):
        return "zh"
    if latin >= 3:
        return "en"
    if cjk >= 1:
        return "zh"
    return None


def resolve_locale(
    *texts: str,
    ui_locale: str = "en",
    session_locale: str | None = None,
) -> SupportedLocale:
    """
    Pick response locale for LLM output.

    Priority: latest detectable user text → UI preference → session locale → English.
    """
    for text in reversed([t for t in texts if t]):
        detected = detect_locale(text)
        if detected:
            return detected

    if ui_locale:
        return normalize_locale(ui_locale)
    if session_locale:
        return normalize_locale(session_locale)
    return "en"


def locale_instruction(locale: str) -> str:
    return LOCALE_INSTRUCTIONS.get(normalize_locale(locale), LOCALE_INSTRUCTIONS["en"])


def stuck_message(locale: str) -> str:
    return _STUCK_MESSAGES.get(normalize_locale(locale), _STUCK_MESSAGES["en"])


def default_learning_tip(locale: str) -> str:
    return _DEFAULT_TIPS.get(normalize_locale(locale), _DEFAULT_TIPS["en"])


def refresh_session_locale(ctx, student_message: str) -> None:
    """Update ctx.response_locale from the latest user text and preferences."""
    student_msgs = [
        m.get("content", "")
        for m in getattr(ctx, "recent_messages", [])
        if m.get("role") == "student"
    ]
    ctx.response_locale = resolve_locale(
        student_message,
        *reversed(student_msgs),
        getattr(ctx, "problem_text", ""),
        ui_locale=getattr(ctx, "ui_locale", "en"),
        session_locale=getattr(ctx, "response_locale", None),
    )
