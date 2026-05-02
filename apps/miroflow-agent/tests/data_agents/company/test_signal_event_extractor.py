from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from src.data_agents.company.entity_dedup import build_signal_event_dedup_key
from src.data_agents.company.signal_event_extractor import (
    SignalExtractionResult,
    build_signal_event_prompt,
    extract_signal_events_from_news,
)


def _make_llm_returning(*texts: str):
    llm = MagicMock()

    def _create(**_kwargs):
        text = texts[_create.index]
        _create.index += 1
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    _create.index = 0
    llm.chat.completions.create.side_effect = _create
    return llm


def test_build_signal_event_prompt_includes_news_context():
    prompt = build_signal_event_prompt(
        company_name="深圳示例科技",
        title="完成A轮融资",
        summary="数千万元融资。",
        raw_text=None,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )

    assert "深圳示例科技" in prompt
    assert "完成A轮融资" in prompt
    assert "2026-05-01" in prompt


def test_extract_signal_events_parses_mock_llm_json():
    payload = {
        "events": [
            {
                "event_type": "融资",
                "event_date": "2026-05-01",
                "event_summary": "深圳示例科技完成数千万元A轮融资。",
                "confidence": 0.86,
                "subject": {"amount": "数千万元", "round": "A轮"},
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技有限公司",
        news_id="11111111-1111-1111-1111-111111111111",
        title="深圳示例科技完成A轮融资",
        summary="深圳示例科技完成数千万元A轮融资。",
        raw_text=None,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        llm_client=llm,
        llm_model="gemma",
    )

    assert isinstance(result, SignalExtractionResult)
    assert result.error is None
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type == "funding"
    assert event.event_date.isoformat() == "2026-05-01"
    assert event.confidence == Decimal("0.86")
    assert event.event_subject_normalized["amount"] == "数千万元"
    assert event.dedup_key == build_signal_event_dedup_key(
        company_id="COMP-1",
        event_type="funding",
        event_date="2026-05-01",
    )


def test_extract_signal_events_retries_json_parse_failure():
    llm = _make_llm_returning(
        "不是 JSON",
        json.dumps({"events": []}, ensure_ascii=False),
    )

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id=None,
        title="普通报道",
        summary="没有明确事件。",
        raw_text=None,
        published_at="2026-05-01",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert result.events == ()
    assert llm.chat.completions.create.call_count == 2


def test_extract_signal_events_skips_unsupported_event_type():
    payload = {
        "events": [
            {
                "event_type": "rumor",
                "event_date": "2026-05-01",
                "event_summary": "传闻。",
                "confidence": 0.5,
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id=None,
        title="传闻报道",
        summary="传闻。",
        raw_text=None,
        published_at="2026-05-01",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert result.events == ()


def test_extract_signal_events_llm_exception_returns_error():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("llm down")

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id=None,
        title="融资新闻",
        summary="深圳示例科技完成融资。",
        raw_text=None,
        published_at="2026-05-01",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.events == ()
    assert "llm down" in result.error
