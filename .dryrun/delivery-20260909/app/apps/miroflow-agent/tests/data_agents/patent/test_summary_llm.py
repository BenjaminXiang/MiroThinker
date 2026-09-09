from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.data_agents.contracts import Evidence, PatentRecord
from src.data_agents.patent.summary_llm import generate_patent_summary_text


def _record() -> PatentRecord:
    return PatentRecord(
        id="PAT-SUMMARY",
        title="一种高可靠传感器校准方法",
        patent_number="CN999999999A",
        applicants=["深圳市测试科技有限公司"],
        patent_type="发明",
        filing_date="2026-05-01",
        abstract="该方法通过多源信号融合修正传感器漂移，提高长期运行稳定性。",
        technology_effect="降低校准误差并提升设备稳定性",
        summary_text="fallback seed",
        evidence=[
            Evidence(
                source_type="xlsx_import",
                source_file="patent.xlsx",
                fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                confidence=1.0,
            )
        ],
        last_updated=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _llm_returning(text: str) -> MagicMock:
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=text))]
    )
    return llm


def test_generate_patent_summary_text_accepts_valid_llm_output():
    text = "  " + ("专" * 200) + "  "
    llm = _llm_returning(text)

    summary, method = generate_patent_summary_text(_record(), llm_client=llm)

    assert method == "llm"
    assert summary == "专" * 200


def test_generate_patent_summary_text_truncates_long_llm_output():
    llm = _llm_returning("长" * 350)

    summary, method = generate_patent_summary_text(_record(), llm_client=llm)

    assert method == "llm"
    assert summary == ("长" * 300) + "…"


def test_generate_patent_summary_text_falls_back_for_short_output():
    llm = _llm_returning("短" * 30)

    summary, method = generate_patent_summary_text(_record(), llm_client=llm)

    assert method == "fallback_template"
    assert "高可靠传感器校准方法" in summary


def test_generate_patent_summary_text_falls_back_when_llm_raises():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("llm down")

    summary, method = generate_patent_summary_text(_record(), llm_client=llm)

    assert method == "fallback_template"
    assert "高可靠传感器校准方法" in summary


def test_generate_patent_summary_text_prompt_contains_core_fields():
    llm = _llm_returning("专" * 200)

    generate_patent_summary_text(_record(), llm_client=llm)

    kwargs = llm.chat.completions.create.call_args.kwargs
    prompt = kwargs["messages"][1]["content"]
    assert "一种高可靠传感器校准方法" in prompt
    assert "多源信号融合修正传感器漂移" in prompt
    assert "降低校准误差并提升设备稳定性" in prompt
