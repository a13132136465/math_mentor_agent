"""Teaching Agent fallbacks and leak override."""
from app.agents.teaching import LEAK_RISK_OVERRIDE, TeachingAgent
from app.models.agent import SessionContext, SocraticAssessment
from app.models.student import MasterySnapshot


def make_session_context(**kwargs) -> SessionContext:
    base = dict(
        session_id="s1",
        student_id="st1",
        display_name="Test",
        mastery=MasterySnapshot(),
        problem_text="x",
    )
    base.update(kwargs)
    return SessionContext(**base)


def test_fallback_assessment_returns_question():
    ctx = make_session_context()
    assessment = TeachingAgent._fallback_assessment(ctx)
    assert assessment.next_question.endswith("?")
    assert assessment.confidence == 50


def test_canned_response_uses_next_question():
    ctx = make_session_context(hint_level=0)
    assessment = SocraticAssessment(
        student_understanding="partial",
        next_question="What is the outer function?",
        hint="Recall the chain rule.",
        confidence=60,
    )
    text = TeachingAgent._canned_response(ctx, assessment)
    assert "What is the outer function?" in text


def test_response_needs_question_suffix_english_question_mark():
    q = "Which grows faster, ln(x) or x?"
    assert not TeachingAgent._response_needs_question_suffix(f"Good start. {q}", q)
    assert not TeachingAgent._response_needs_question_suffix(f"Good start. {q}?", q)
    assert TeachingAgent._response_needs_question_suffix("Good start.", q)


def test_response_needs_question_suffix_chinese_fullwidth_mark():
    q = "当 x → ∞ 时，分子 ln(x) 和分母 x 的增长速度哪个更快？这对极限值有什么影响？"
    assert not TeachingAgent._response_needs_question_suffix(
        f"你观察得很对。{q}", q
    )
    assert not TeachingAgent._response_needs_question_suffix(
        f"你观察得很对。{q}？", q
    )
    assert TeachingAgent._response_needs_question_suffix("你观察得很对。", q)


def test_dedupe_trailing_question_collapses_triple_repeat():
    q = "当 x → ∞ 时，分子 ln(x) 和分母 x 的增长速度哪个更快？这对极限值有什么影响？"
    intro = "你观察得很对——想一想，哪个增长得更快？"
    bloated = f"{intro}\n\n{q}\n\n{q}\n\n{q}"
    result = TeachingAgent._dedupe_trailing_question(bloated, q)
    assert result.count(q) == 1
    assert result.endswith(q)
    assert intro in result


def test_dedupe_trailing_question_keeps_single_copy():
    q = "What is the next step?"
    text = f"Good thinking.\n\n{q}"
    assert TeachingAgent._dedupe_trailing_question(text, q) == text


def test_response_needs_question_suffix_skips_when_in_tail():
    q = "当 x → ∞ 时，分子 ln(x) 和分母 x 的增长速度哪个更快？这对极限值有什么影响？"
    text = f"你观察得很对。\n\n{q}"
    assert not TeachingAgent._response_needs_question_suffix(text, q)


def test_canned_response_includes_hint_at_level_2():
    ctx = make_session_context(hint_level=2)
    assessment = SocraticAssessment(
        student_understanding="partial",
        next_question="What comes next?",
        hint="Multiply by the inner derivative.",
        confidence=40,
    )
    text = TeachingAgent._canned_response(ctx, assessment)
    assert "inner derivative" in text
    assert LEAK_RISK_OVERRIDE == 0.70
