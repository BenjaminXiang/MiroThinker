from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest

from src.data_agents.professor.candidate_llm_provider import (
    InvalidLLMOutputContract,
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
                            "candidate_profile_summary": _valid_profile_summary(),
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
    prompt = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "profile_summary must be a 200-300 character Chinese" in prompt
    assert "超过 300 字视为失败" in prompt
    assert client.chat.completions.calls[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_candidate_llm_provider_retries_profile_summary_contract_violation() -> None:
    too_long = _valid_profile_summary() + _valid_profile_summary()
    completions = _FakeCompletions(
        [
            json.dumps(
                {
                    "candidate_profile_summary": too_long,
                    "llm_self_check": {"source_grounded": True},
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "candidate_profile_summary": _valid_profile_summary(),
                    "llm_self_check": {"source_grounded": True},
                },
                ensure_ascii=False,
            ),
        ]
    )
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        settings=_settings(task_type="profile_summary_synthesis"),
    )

    result = provider.generate_profile_summary(_profile_input())

    assert result.text == _valid_profile_summary()
    assert result.provider_metadata["attempt_count"] == 2
    retry_prompt = completions.calls[1]["messages"][1]["content"]
    assert "profile_summary_too_long" in retry_prompt
    assert "不要超过 300 字" in retry_prompt


def test_candidate_llm_provider_raises_typed_failure_after_profile_contract_retry() -> (
    None
):
    too_long = _valid_profile_summary() + _valid_profile_summary()
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=_FakeCompletions(
                    [
                        json.dumps(
                            {
                                "candidate_profile_summary": too_long,
                                "llm_self_check": {"source_grounded": True},
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "candidate_profile_summary": too_long,
                                "llm_self_check": {"source_grounded": True},
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            )
        ),
        settings=_settings(task_type="profile_summary_synthesis"),
    )

    with pytest.raises(InvalidLLMOutputContract) as exc_info:
        provider.generate_profile_summary(_profile_input())

    assert exc_info.value.retryable is True
    assert exc_info.value.provider_metadata["task_type"] == "profile_summary_synthesis"
    assert exc_info.value.provider_metadata["validation_errors"] == [
        "profile_summary_too_long"
    ]


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
    assert "只输出一个 JSON 对象" in completions.calls[1]["messages"][1]["content"]
    assert '"candidate_research_overview_zh": "..."' in completions.calls[1][
        "messages"
    ][1]["content"]


def test_candidate_llm_provider_accepts_empty_research_overview_absence() -> None:
    completions = _FakeCompletions(
        [
            json.dumps(
                {
                    "candidate_research_overview_zh": "",
                    "llm_self_check": {
                        "source_grounded": True,
                        "quality_flags": ["missing_research_overview_source=true"],
                        "review_required": True,
                    },
                },
                ensure_ascii=False,
            )
        ]
    )
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        settings=_settings(task_type="research_overview_translation"),
    )

    result = provider.translate_research_overview(
        "研究领域：主页地址 复制地址 联系方式 招生信息。"
    )

    assert result.text == ""
    assert result.llm_self_check["quality_flags"] == [
        "missing_research_overview_source=true"
    ]
    assert len(completions.calls) == 1


def test_candidate_llm_provider_cleans_noisy_chinese_research_overview() -> None:
    completions = _FakeCompletions(
        [
            json.dumps(
                {
                    "candidate_research_overview_zh": "研究方向包括群体智能、网络科学、图神经网络和复杂系统控制。",
                    "llm_self_check": {
                        "source_grounded": True,
                        "removed_page_noise": [
                            "课程",
                            "招生",
                            "联系方式",
                            "链接",
                        ],
                    },
                },
                ensure_ascii=False,
            )
        ]
    )
    provider = ProfessorCandidateLLMProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        settings=_settings(task_type="research_overview_translation"),
    )

    result = provider.translate_research_overview(
        "研究方向：群体智能、网络科学、图神经网络。教授课程：数字信号处理。"
        "欢迎研究生发送简历，主页：https://example.edu。"
    )

    assert result.text == "研究方向包括群体智能、网络科学、图神经网络和复杂系统控制。"
    assert result.llm_self_check["removed_page_noise"] == [
        "课程",
        "招生",
        "联系方式",
        "链接",
    ]
    prompt = completions.calls[0]["messages"][1]["content"]
    assert "剔除课程、招生、联系方式、链接" in prompt
    assert "如果来源没有研究方向信息" in prompt
    assert "不要输出 Markdown" in prompt
    assert '"candidate_research_overview_zh": "..."' in prompt
    assert '"llm_self_check"' in prompt


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


def test_candidate_llm_provider_wraps_openai_client_with_deepseek_limiter(
    monkeypatch,
) -> None:
    from src.data_agents.company import provider_rate_limit

    wrapped_calls: list[tuple[object, str]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    class FakeHttpxClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setitem(
        sys.modules, "httpx", types.SimpleNamespace(Client=FakeHttpxClient)
    )
    monkeypatch.setattr(
        provider_rate_limit,
        "wrap_openai_client",
        lambda client, provider_key: (
            wrapped_calls.append((client, provider_key)) or client
        ),
    )

    provider = ProfessorCandidateLLMProvider(
        settings=_settings(task_type="profile_summary_synthesis"),
    )

    assert isinstance(provider.client, FakeOpenAI)
    assert wrapped_calls == [(provider.client, "deepseek")]


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


def _valid_profile_summary() -> str:
    return (
        "Ahmed Elazab现任清华大学深圳国际研究生院助理教授，研究聚焦可信人工智能、医学影像分析与脑疾病诊断预后。"
        "他围绕多模态神经影像融合、可解释机器学习和计算机辅助诊断开展研究，强调模型稳健性、临床可解释性与真实医疗场景中的应用价值。"
        "其工作结合深度学习、模式识别和神经信息学方法，服务于阿尔茨海默病、脑肿瘤等疾病的早筛、分型和预后评估，并参与医学影像智能分析相关项目。"
        "相关成果支撑跨模态影像特征提取、疾病风险预测和医生决策辅助。"
    )
