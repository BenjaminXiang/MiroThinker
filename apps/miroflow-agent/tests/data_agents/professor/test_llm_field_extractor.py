from __future__ import annotations

import json
from uuid import UUID

import pytest

from src.data_agents.professor.llm_field_extractor import (
    ProfessorFieldExtractionInput,
    extract_llm_profile_fields,
)


RUN_ID = UUID("11111111-1111-4111-8111-111111111111")


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeUsage:
    prompt_tokens = 321
    completion_tokens = 123
    total_tokens = 444


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self.response_payload = response_payload
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(json.dumps(self.response_payload, ensure_ascii=False))


class _FakeChat:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self.completions = _FakeCompletions(response_payload)


class _FakeLLMClient:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self.chat = _FakeChat(response_payload)


def test_extract_llm_profile_fields_emits_bilingual_grounded_provenance_and_review_status() -> (
    None
):
    client = _FakeLLMClient(
        {
            "facts": [
                {
                    "field": "research_directions",
                    "fact_type": "research_topic",
                    "original_value": "machine learning",
                    "bilingual_value": "machine learning (机器学习)",
                    "evidence_span": "Research interests: machine learning and AI.",
                    "confidence": 0.91,
                },
                {
                    "field": "education",
                    "fact_type": "education",
                    "original_value": "Ph.D., Stanford University",
                    "bilingual_value": "Ph.D., Stanford University (斯坦福大学博士)",
                    "evidence_span": "Education: Ph.D., Stanford University.",
                    "confidence": 0.88,
                },
                {
                    "field": "academic_position",
                    "fact_type": "academic_position",
                    "original_value": "Associate Professor",
                    "bilingual_value": "Associate Professor (副教授)",
                    "evidence_span": "Title: Associate Professor.",
                    "confidence": 0.62,
                },
                {
                    "field": "contact",
                    "fact_type": "contact",
                    "original_value": "ada@example.edu",
                    "bilingual_value": "ada@example.edu",
                    "evidence_span": "Email: ada@example.edu",
                    "confidence": 0.95,
                },
            ]
        }
    )
    page_text = """
    Ada Chen
    Title: Associate Professor.
    Research interests: machine learning and AI.
    Education: Ph.D., Stanford University.
    Email: ada@example.edu
    """

    result = extract_llm_profile_fields(
        ProfessorFieldExtractionInput(
            professor_id="PROF-ADA",
            canonical_name="Ada Chen",
            institution="香港中文大学（深圳）",
            page_text=page_text,
            run_id=RUN_ID,
        ),
        llm_client=client,
        llm_model="fake-model",
    )

    assert result.error is None
    assert result.usage.prompt_tokens == 321
    assert result.usage.completion_tokens == 123
    assert result.usage.total_tokens == 444
    assert [fact.fact_type for fact in result.facts] == [
        "research_topic",
        "education",
        "academic_position",
        "contact",
    ]

    values = {fact.fact_type: fact.value_raw for fact in result.facts}
    assert values["research_topic"] == "machine learning (机器学习)"
    assert values["education"] == "Ph.D., Stanford University (斯坦福大学博士)"
    assert values["academic_position"] == "Associate Professor (副教授)"
    assert values["contact"] == "ada@example.edu"

    assert all(fact.source == "llm_extraction" for fact in result.facts)
    assert all(fact.run_id == RUN_ID for fact in result.facts)
    assert all(fact.professor_id == "PROF-ADA" for fact in result.facts)
    assert all(fact.evidence_span in page_text for fact in result.facts)
    assert all(
        fact.quality_status == "ready"
        for fact in result.facts
        if fact.confidence >= 0.75
    )
    assert (
        next(
            fact for fact in result.facts if fact.fact_type == "academic_position"
        ).quality_status
        == "needs_review"
    )

    request = client.chat.completions.calls[0]
    assert request["model"] == "fake-model"
    assert request["temperature"] == 0.0


def test_extract_llm_profile_fields_omits_absent_or_ungrounded_fields() -> None:
    client = _FakeLLMClient(
        {
            "facts": [
                {
                    "field": "award",
                    "fact_type": "award",
                    "original_value": "National Science Award",
                    "bilingual_value": "National Science Award (国家科学奖)",
                    "evidence_span": "National Science Award",
                    "confidence": 0.92,
                },
                {
                    "field": "work_experience",
                    "fact_type": "work_experience",
                    "original_value": "Professor at MIT",
                    "bilingual_value": "Professor at MIT (麻省理工学院教授)",
                    "evidence_span": "Professor at MIT",
                    "confidence": 0.86,
                },
            ]
        }
    )

    result = extract_llm_profile_fields(
        ProfessorFieldExtractionInput(
            professor_id="PROF-EMPTY",
            canonical_name="Empty Case",
            institution="香港中文大学（深圳）",
            page_text="Empty Case\nEmail: empty@example.edu",
            run_id=RUN_ID,
        ),
        llm_client=client,
        llm_model="fake-model",
    )

    assert result.error is None
    assert result.facts == ()


def test_extract_llm_profile_fields_omits_office_only_contact() -> None:
    client = _FakeLLMClient(
        {
            "facts": [
                {
                    "field": "contact",
                    "fact_type": "contact",
                    "original_value": "LEE Yin Yee (RA) 417",
                    "bilingual_value": "LEE Yin Yee (RA) 417 (办公室)",
                    "evidence_span": "Office: LEE Yin Yee (RA) 417",
                    "confidence": 0.93,
                }
            ]
        }
    )

    result = extract_llm_profile_fields(
        ProfessorFieldExtractionInput(
            professor_id="PROF-OFFICE",
            canonical_name="Office Only",
            institution="香港中文大学（深圳）",
            page_text="Office: LEE Yin Yee (RA) 417",
            run_id=RUN_ID,
        ),
        llm_client=client,
        llm_model="fake-model",
    )

    assert result.error is None
    assert result.facts == ()


def test_extract_llm_profile_fields_omits_english_without_bilingual_translation() -> (
    None
):
    client = _FakeLLMClient(
        {
            "facts": [
                {
                    "field": "research_directions",
                    "fact_type": "research_topic",
                    "original_value": "machine learning",
                    "bilingual_value": "machine learning",
                    "evidence_span": "Research interests: machine learning.",
                    "confidence": 0.96,
                }
            ]
        }
    )

    result = extract_llm_profile_fields(
        ProfessorFieldExtractionInput(
            professor_id="PROF-ENGLISH",
            canonical_name="English Only",
            institution="香港中文大学（深圳）",
            page_text="Research interests: machine learning.",
            run_id=RUN_ID,
        ),
        llm_client=client,
        llm_model="fake-model",
    )

    assert result.error is None
    assert result.facts == ()


def test_extract_llm_profile_fields_requires_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        ProfessorFieldExtractionInput(
            professor_id="PROF-NO-RUN",
            canonical_name="No Run",
            institution="香港中文大学（深圳）",
            page_text="Research interests: databases.",
            run_id=None,
        )
