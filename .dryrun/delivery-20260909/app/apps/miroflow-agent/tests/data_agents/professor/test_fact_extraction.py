from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.fact_backfill import (
    TARGET_FACT_TYPES,
    ExtractedProfessorFact,
    ProfessorFactExtractionResult,
    extract_professor_facts,
    persist_extracted_professor_facts,
)


def _make_llm_returning(text: str) -> MagicMock:
    llm = MagicMock()
    llm.chat.completions.create.return_value = _response(text)
    return llm


def _make_llm_returning_sequence(texts: list[str]) -> MagicMock:
    llm = MagicMock()
    llm.chat.completions.create.side_effect = [_response(text) for text in texts]
    return llm


def _response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_extract_professor_facts_parses_all_target_fact_types() -> None:
    llm = _make_llm_returning(
        """
        ```json
        {
          "facts": [
            {
              "fact_type": "education",
              "value_raw": "2005年至2010年在清华大学获得博士学位",
              "value_normalized": "清华大学博士",
              "evidence_span": "2005年至2010年在清华大学获得博士学位",
              "confidence": 0.96
            },
            {
              "fact_type": "work_experience",
              "value_raw": "曾任香港科技大学助理教授",
              "value_normalized": "香港科技大学助理教授",
              "evidence_span": "曾任香港科技大学助理教授",
              "confidence": 0.91
            },
            {
              "fact_type": "award",
              "value_raw": "国家杰出青年科学基金获得者",
              "value_normalized": "国家杰出青年科学基金",
              "evidence_span": "国家杰出青年科学基金获得者",
              "confidence": 0.88
            },
            {
              "fact_type": "academic_position",
              "value_raw": "IEEE Fellow (IEEE会士)",
              "value_normalized": "IEEE Fellow (IEEE会士)",
              "evidence_span": "IEEE Fellow",
              "confidence": 0.86
            }
          ]
        }
        ```
        """
    )

    result = extract_professor_facts(
        professor_id="PROF-1",
        professor_name="王教授",
        institution="南方科技大学",
        profile_raw_text="王教授，2005年至2010年在清华大学获得博士学位，曾任香港科技大学助理教授，国家杰出青年科学基金获得者，IEEE Fellow。",
        llm_client=llm,
        llm_model="gemma",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert isinstance(result, ProfessorFactExtractionResult)
    assert result.error is None
    assert {fact.fact_type for fact in result.facts} == set(TARGET_FACT_TYPES)
    assert all(isinstance(fact, ExtractedProfessorFact) for fact in result.facts)
    assert result.facts[0].professor_id == "PROF-1"
    assert result.facts[0].source_profile_raw_text_len > 0
    kwargs = llm.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gemma"
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    prompt_text = "\n".join(message["content"] for message in kwargs["messages"])
    for fact_type in TARGET_FACT_TYPES:
        assert fact_type in prompt_text
    assert "王教授" in prompt_text
    assert "清华大学获得博士学位" in prompt_text
    assert "English original (中文翻译)" in prompt_text
    assert "evidence_span 必须来自原文" in prompt_text


def test_extract_professor_facts_deduplicates_repeated_profile_text_before_prompt() -> (
    None
):
    llm = _make_llm_returning('{"facts": []}')
    repeated_line = "Education: Ph.D., Stanford University."
    raw_text = "\n".join(
        [
            repeated_line,
            "Research: Trustworthy AI for medical imaging.",
            repeated_line,
            repeated_line,
        ]
    )

    result = extract_professor_facts(
        professor_id="PROF-DUP",
        professor_name="Dup Prof",
        institution="Test University",
        profile_raw_text=raw_text,
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    prompt_text = "\n".join(
        message["content"]
        for message in llm.chat.completions.create.call_args.kwargs["messages"]
    )
    assert prompt_text.count(repeated_line) == 1


def test_extract_professor_facts_retries_english_fact_until_bilingual() -> None:
    first = """
    {
      "facts": [
        {
          "fact_type": "academic_position",
          "value_raw": "Assistant Professor",
          "value_normalized": "Assistant Professor",
          "evidence_span": "Assistant Professor",
          "confidence": 0.92
        }
      ]
    }
    """
    second = """
    {
      "facts": [
        {
          "fact_type": "academic_position",
          "value_raw": "Assistant Professor (助理教授)",
          "value_normalized": "Assistant Professor (助理教授)",
          "evidence_span": "Assistant Professor",
          "confidence": 0.92
        }
      ]
    }
    """
    llm = _make_llm_returning_sequence([first, second])

    result = extract_professor_facts(
        professor_id="PROF-EN",
        professor_name="English Prof",
        institution="Test University",
        profile_raw_text="Biography: Assistant Professor at Test University.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert result.facts[0].value_raw == "Assistant Professor (助理教授)"
    assert result.facts[0].evidence_span == "Assistant Professor"
    assert llm.chat.completions.create.call_count == 2
    retry_prompt = llm.chat.completions.create.call_args_list[1].kwargs["messages"][1][
        "content"
    ]
    assert "上次输出违反事实抽取合同" in retry_prompt
    assert "missing bilingual translation" in retry_prompt


@pytest.mark.parametrize("fact_type", TARGET_FACT_TYPES)
def test_extract_professor_facts_preserves_low_confidence_values(
    fact_type: str,
) -> None:
    llm = _make_llm_returning(
        f"""
        {{
          "facts": [
            {{
              "fact_type": "{fact_type}",
              "value_raw": "低置信度事实",
              "value_normalized": "低置信度事实",
              "evidence_span": "低置信度事实",
              "confidence": 0.31
            }}
          ]
        }}
        """
    )

    result = extract_professor_facts(
        professor_id="PROF-LOW",
        professor_name="低置信教授",
        institution="深圳大学",
        profile_raw_text="低置信度事实",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert len(result.facts) == 1
    assert result.facts[0].fact_type == fact_type
    assert result.facts[0].confidence == pytest.approx(0.31)


def test_extract_professor_facts_skips_malformed_output_without_raising() -> None:
    llm = _make_llm_returning("not json")

    result = extract_professor_facts(
        professor_id="PROF-BAD",
        professor_name="坏输出教授",
        institution="深圳大学",
        profile_raw_text="教育经历：某大学博士。",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.facts == ()
    assert result.error is not None
    assert "malformed" in result.error


def test_extract_professor_facts_llm_failure_returns_error_without_raising() -> None:
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("LLM down")

    result = extract_professor_facts(
        professor_id="PROF-ERR",
        professor_name="异常教授",
        institution="深圳大学",
        profile_raw_text="工作经历：曾任教授。",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.facts == ()
    assert result.error is not None
    assert "LLM down" in result.error


def test_persist_extracted_professor_facts_delegates_dedup_to_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dedup now lives inside the keep-richest writer; persist must not run its
    own retire SQL — it just forwards each fact to _upsert_fact."""
    import src.data_agents.professor.canonical_writer as canonical_writer

    calls: list[dict] = []

    def _fake_upsert(_conn, **kwargs):
        calls.append(kwargs)
        return "inserted"

    monkeypatch.setattr(canonical_writer, "_upsert_fact", _fake_upsert)
    conn = MagicMock()
    fact = ExtractedProfessorFact(
        professor_id="PROF-EN",
        fact_type="academic_position",
        value_raw="Assistant Professor (助理教授)",
        value_normalized="Assistant Professor (助理教授)",
        evidence_span="Assistant Professor",
        confidence=0.93,
        source_profile_raw_text_len=128,
    )

    report = persist_extracted_professor_facts(
        conn,
        facts=(fact,),
        source_page_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    assert report.facts_written == 1
    assert report.facts_retired == 0  # retired count is now internal to the writer
    assert len(calls) == 1  # exactly one writer call per fact
    # persist must not issue its own retire/row_number SQL anymore
    executed_sql = "\n".join(call.args[0] for call in conn.execute.call_args_list)
    assert "row_number()" not in executed_sql
    assert "superseded" not in executed_sql
