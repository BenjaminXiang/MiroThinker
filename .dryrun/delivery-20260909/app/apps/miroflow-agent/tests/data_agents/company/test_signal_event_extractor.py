from __future__ import annotations

import json
from datetime import date, datetime, timezone
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


def test_build_signal_event_prompt_mentions_source_profile_context():
    prompt = build_signal_event_prompt(
        company_name="深圳旭宏医疗科技有限公司",
        title="旭宏医疗 - PitchHub",
        summary=None,
        raw_text="项目简介：专注心电AI。融资历史：2024-01-01 完成天使轮融资。",
        published_at=None,
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
    )

    assert "pitchhub_36kr" in prompt
    assert "source profile" in prompt
    assert "融资历史" in prompt


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


def test_extract_signal_events_normalizes_source_backed_funding_fields():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-03-15",
                "event_summary": "旭宏医疗完成3000万元A+轮融资，投资方为力合科创、松禾资本。",
                "confidence": 0.91,
                "subject": {
                    "round": "A+轮",
                    "amount": "3000万元人民币",
                    "investors": ["力合科创", "松禾资本"],
                },
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        news_id="11111111-1111-1111-1111-111111111111",
        title="旭宏医疗 - PitchHub 项目页",
        summary="融资历史 | A+轮 | 2026-03-15 | 3000万元人民币 | 力合科创、松禾资本",
        raw_text="融资历史 | A+轮 | 2026-03-15 | 3000万元人民币 | 力合科创、松禾资本",
        published_at=None,
        llm_client=llm,
        llm_model="gemma",
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
        baseline_latest_funding_round="天使轮",
        baseline_latest_funding_date=date(2024, 1, 1),
    )

    assert result.error is None
    assert len(result.events) == 1
    event = result.events[0]
    normalized = event.event_subject_normalized
    assert event.status == "active"
    assert normalized["financing_round"] == "A+轮"
    assert normalized["amount_raw"] == "3000万元人民币"
    assert normalized["amount_cny_wan"] == "3000"
    assert normalized["investors"] == ["力合科创", "松禾资本"]
    assert normalized["financing_summary"] == "旭宏医疗完成3000万元A+轮融资，投资方为力合科创、松禾资本。"
    assert normalized["funding_freshness"] == "newer_than_xlsx_baseline"
    assert normalized["xlsx_baseline"]["round"] == "天使轮"
    assert normalized["xlsx_baseline"]["date"] == "2024-01-01"
    assert normalized["source_url"] == "https://pitchhub.36kr.com/project/1678475362006017"
    assert normalized["source_adapter"] == "pitchhub_36kr"


def test_extract_signal_events_review_gates_conflicting_funding_baseline():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-01-01",
                "event_summary": "示例科技完成A轮融资。",
                "confidence": 0.82,
                "subject": {"round": "A轮", "amount": "未披露"},
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技有限公司",
        news_id="11111111-1111-1111-1111-111111111111",
        title="示例科技 - PitchHub 项目页",
        summary="融资历史 | A轮 | 2026-01-01 | 未披露",
        raw_text="融资历史 | A轮 | 2026-01-01 | 未披露",
        published_at=None,
        llm_client=llm,
        llm_model="gemma",
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/example",
        baseline_latest_funding_round="天使轮",
        baseline_latest_funding_date=date(2026, 1, 1),
    )

    assert result.error is None
    assert len(result.events) == 1
    event = result.events[0]
    assert event.status == "needs_review"
    assert event.event_subject_normalized["review_reason"] == (
        "conflicts_with_xlsx_baseline"
    )
    assert event.event_subject_normalized["source_url"] == (
        "https://pitchhub.36kr.com/project/example"
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


def test_extract_signal_events_requires_source_profile_date_evidence():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-05-28",
                "event_summary": "示例公司完成A轮融资。",
                "confidence": 0.9,
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id="11111111-1111-1111-1111-111111111111",
        title="示例科技 - PitchHub 项目页",
        summary="项目简介：示例科技提供AI检测服务。融资历史：A轮 未披露。",
        raw_text="项目简介：示例科技提供AI检测服务。融资历史：A轮 未披露。",
        published_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        llm_client=llm,
        llm_model="gemma",
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/example",
    )

    assert result.error is None
    assert result.events == ()


def test_extract_signal_events_allows_dated_yiou_news_published_date():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-05-01",
                "event_summary": "示例科技完成A轮融资。",
                "confidence": 0.9,
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id="11111111-1111-1111-1111-111111111111",
        title="示例科技完成A轮融资",
        summary="示例科技完成A轮融资。",
        raw_text="示例科技完成A轮融资。",
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        llm_client=llm,
        llm_model="gemma",
        source_adapter="iyiou",
        source_url="https://data.iyiou.com/news/123456",
    )

    assert result.error is None
    assert len(result.events) == 1
    assert result.events[0].event_date.isoformat() == "2026-05-01"


def test_extract_signal_events_keeps_source_profile_dated_history():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-01-01",
                "event_summary": "示例科技完成A+轮融资，金额过亿人民币。",
                "confidence": 0.95,
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id="11111111-1111-1111-1111-111111111111",
        title="示例科技 - PitchHub 项目页",
        summary="融资历史 | A+轮 | 2026-01 | 过亿人民币 |",
        raw_text="融资历史 | A+轮 | 2026-01 | 过亿人民币 |",
        published_at=None,
        llm_client=llm,
        llm_model="gemma",
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/example",
    )

    assert result.error is None
    assert len(result.events) == 1
    assert result.events[0].event_date.isoformat() == "2026-01-01"


def test_extract_signal_events_rejects_source_profile_invented_day_for_month_only():
    payload = {
        "events": [
            {
                "event_type": "funding",
                "event_date": "2026-05-28",
                "event_summary": "示例科技完成C轮融资。",
                "confidence": 0.95,
            }
        ]
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = extract_signal_events_from_news(
        company_id="COMP-1",
        company_name="深圳示例科技",
        news_id="11111111-1111-1111-1111-111111111111",
        title="示例科技 - PitchHub 项目页",
        summary="融资历史 | C轮 | 2026-05 | 未透露 |",
        raw_text="融资历史 | C轮 | 2026-05 | 未透露 |",
        published_at=None,
        llm_client=llm,
        llm_model="gemma",
        source_adapter="pitchhub_36kr",
        source_url="https://pitchhub.36kr.com/project/example",
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
