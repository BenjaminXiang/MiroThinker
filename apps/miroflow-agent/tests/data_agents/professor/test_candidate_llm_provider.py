from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.data_agents.professor.candidate_llm_provider import (
    MalformedLLMJSON,
    MissingLLMCredentials,
    ProfessorCandidateLLMProvider,
    ProfessorCandidateLLMTaskSettings,
)
from src.data_agents.professor.dataset_candidate_generation import (
    CandidateLLMOutput,
    ProfileSummaryFact,
    build_profile_summary_input,
)


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=content),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=17),
        )


def test_candidate_llm_provider_generates_profile_summary_with_audit_metadata() -> None:
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=_FakeCompletions(
                [
                    json.dumps(
                        {
                            "candidate_profile_summary": "Ahmed Elazab现任清华大学深圳国际研究生院助理教授，研究聚焦可信人工智能、医学影像分析和脑疾病诊断预后。",
                            "llm_self_check": {
                                "source_grounded": True,
                                "unsupported_claims": [],
                                "needs_review": True,
                            },
                        },
                        ensure_ascii=False,
                    )
                ]
            )
        )
    )
    provider = ProfessorCandidateLLMProvider(
        client=client,
        settings=_settings(task_type="profile_summary_synthesis"),
    )

    result = provider.generate_profile_summary(_profile_input())

    assert isinstance(result, CandidateLLMOutput)
    assert result.text.startswith("Ahmed Elazab现任清华大学深圳国际研究生院")
    assert result.llm_self_check["source_grounded"] is True
    assert result.provider_metadata["task_type"] == "profile_summary_synthesis"
    assert result.provider_metadata["llm_profile"] == "deepseekv4pro"
    assert result.provider_metadata["model"] == "deepseek-v4-pro"
    assert len(result.provider_metadata["prompt_hash"]) == 64
    assert len(result.provider_metadata["raw_response_hash"]) == 64
    assert result.provider_metadata["finish_reason"] == "stop"
    assert result.provider_metadata["prompt_tokens"] == 11
    assert result.provider_metadata["completion_tokens"] == 17
    assert client.chat.completions.calls[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_candidate_llm_provider_retries_malformed_json_once() -> None:
    completions = _FakeCompletions(
        [
            "not json",
            json.dumps(
                {
                    "candidate_research_overview_zh": "研究方向包括可信人工智能、医学影像分析和脑疾病诊断预后。",
                    "llm_self_check": {"source_preserved": True},
                },
                ensure_ascii=False,
            ),
        ]
    )
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        settings=_settings(task_type="research_overview_translation"),
    )

    result = provider.translate_research_overview(
        "My research focuses on trustworthy artificial intelligence."
    )

    assert result.text.startswith("研究方向包括可信人工智能")
    assert result.provider_metadata["attempt_count"] == 2
    assert "上次输出无法解析" in completions.calls[1]["messages"][1]["content"]


def test_candidate_llm_provider_raises_typed_failure_after_bad_json() -> None:
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions(["not json", "[]"]))
        ),
        settings=_settings(task_type="paper_summary_synthesis"),
    )

    with pytest.raises(MalformedLLMJSON) as exc_info:
        provider.generate_paper_summary(
            SimpleNamespace(
                professor_id="PROF-1",
                professor_name="Ahmed Elazab",
                eligible_papers=(),
                excluded_paper_ids=(),
                exclusion_reasons={},
                duplicate_status="deduplicated",
                source_page_ids=("PAGE-1",),
            )
        )

    assert exc_info.value.retryable is True
    assert exc_info.value.provider_metadata["task_type"] == "paper_summary_synthesis"
    assert exc_info.value.provider_metadata["model"] == "deepseek-v4-pro"


def test_candidate_llm_provider_missing_credentials_is_typed_failure() -> None:
    provider = ProfessorCandidateLLMProvider(
        client=None,
        settings=_settings(task_type="profile_summary_synthesis", api_key=""),
    )

    with pytest.raises(MissingLLMCredentials) as exc_info:
        provider.generate_profile_summary(_profile_input())

    assert exc_info.value.retryable is True
    assert exc_info.value.provider_metadata["llm_profile"] == "deepseekv4pro"
    assert exc_info.value.provider_metadata["model"] == "deepseek-v4-pro"


def _settings(
    *,
    task_type: str,
    api_key: str = "test-key",
) -> ProfessorCandidateLLMTaskSettings:
    return ProfessorCandidateLLMTaskSettings(
        task_type=task_type,
        llm_profile="deepseekv4pro",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        api_key=api_key,
        extra_body={"thinking": {"type": "disabled"}},
        timeout_seconds=60.0,
        retry_budget=1,
    )


def _profile_input():
    return build_profile_summary_input(
        professor_id="PROF-1",
        canonical_name="Ahmed Elazab",
        institution="清华大学",
        department="深圳国际研究生院",
        title="助理教授",
        source_page_id="PAGE-1",
        source_url="https://example.edu/prof/ahmed",
        profile_raw_text=(
            "My research focuses on developing trustworthy artificial intelligence "
            "for medical image analysis."
        ),
        facts=(
            ProfileSummaryFact(
                fact_type="research_topic",
                value="可信人工智能、医学影像分析、脑疾病诊断预后",
                evidence_span="medical image analysis",
                source_page_id="PAGE-1",
            ),
        ),
        paper_summary="论文围绕多模态神经影像融合和脑疾病诊断展开。",
        linked_output_titles=("Improved Alzheimer's disease diagnosis",),
    )
