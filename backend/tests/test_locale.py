from app.utils.locale import (
    detect_locale,
    locale_instruction,
    normalize_locale,
    resolve_locale,
    stuck_message,
)


def test_detect_chinese():
    assert detect_locale("我想一步一步地解决这个问题") == "zh"
    assert detect_locale("求极限 lim x→0") == "zh"


def test_detect_english():
    assert detect_locale("I'd like to work through this problem step by step.") == "en"


def test_resolve_prefers_latest_user_text():
    assert resolve_locale(
        "Evaluate the limit",
        "我卡住了",
        ui_locale="en",
        session_locale="en",
    ) == "zh"


def test_resolve_falls_back_to_ui_locale():
    assert resolve_locale("x^2 + 1", ui_locale="zh", session_locale="en") == "zh"


def test_locale_instruction_zh():
    assert "简体中文" in locale_instruction("zh")


def test_stuck_message_localized():
    assert "卡住" in stuck_message("zh")
    assert "stuck" in stuck_message("en").lower()


def test_normalize_locale():
    assert normalize_locale("zh-Hans") == "zh"
    assert normalize_locale("en-US") == "en"
