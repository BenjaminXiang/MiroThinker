"""Clock questions are answered deterministically, without retrieval or the model."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.services.canonical_v2_chat import _clock_answer, _clock_response

NOW = datetime(2026, 10, 28, 3, 15, tzinfo=timezone.utc)  # 11:15 in Shanghai


def test_date_question_answers_from_the_server_clock() -> None:
    assert _clock_answer("今天是几号", NOW) == "今天是 2026年10月28日，星期三（北京时间）。"


def test_weekday_question_answers_the_same_way() -> None:
    assert "星期三" in (_clock_answer("今天星期几", NOW) or "")


def test_time_question_includes_the_hour() -> None:
    answer = _clock_answer("现在几点", NOW)

    assert answer is not None and "11:15" in answer


def test_non_clock_questions_are_not_intercepted() -> None:
    for query in ("丁文伯是谁", "今天天气怎么样", "优必选有哪些专利"):
        assert _clock_answer(query, NOW) is None


def test_clock_response_is_a_plain_answer_without_citations() -> None:
    response = _clock_response("今天是几号", "今天是 2026年10月28日，星期三（北京时间）。")

    assert response.answer_text.startswith("今天是")
    assert response.citations == []
    assert response.query_type == "canonical_v2:A:direct_clock"
