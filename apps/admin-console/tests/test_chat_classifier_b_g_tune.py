from __future__ import annotations

import json
import os
from types import SimpleNamespace

from fastapi import Response
import pytest

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "classifier-test-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


@pytest.fixture(autouse=True)
def _session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", _FakeSessionStore())


B_CASES = {
    "深圳哪些公司做激光雷达": {
        "type": "B",
        "topic": "激光雷达",
        "name": "",
        "target_domain": "company",
    },
    "深圳做合成数据平台的企业": {
        "type": "B",
        "topic": "合成数据平台",
        "name": "",
        "target_domain": "company",
    },
    "做脑机接口的深圳团队": {
        "type": "B",
        "topic": "脑机接口",
        "name": "",
        "target_domain": "company",
    },
    "有没有做工业视觉检测的深圳企业": {
        "type": "B",
        "topic": "工业视觉检测",
        "name": "",
        "target_domain": "company",
    },
    "研究力控的深圳高校教授有哪些": {
        "type": "B",
        "topic": "力控",
        "name": "",
        "target_domain": "professor",
    },
}
G_CASES = {
    "介绍无界智航": {
        "type": "G",
        "topic": "",
        "name": "无界智航",
        "target_domain": "company",
    },
    "介绍无界智航的相关信息": {
        "type": "G",
        "topic": "",
        "name": "无界智航",
        "target_domain": "company",
    },
    "介绍王伟": {
        "type": "G",
        "topic": "",
        "name": "王伟",
        "target_domain": "professor",
    },
    "王伟是谁": {
        "type": "G",
        "topic": "",
        "name": "王伟",
        "target_domain": "professor",
    },
    "李雪芳是谁": {
        "type": "G",
        "topic": "",
        "name": "李雪芳",
        "target_domain": "professor",
    },
}


def _classify_with_mock_llm(monkeypatch: pytest.MonkeyPatch, query: str):
    cases = {**B_CASES, **G_CASES}

    def _fake_settings(profile_name: str | None, *, include_profile: bool = False):
        assert profile_name is None
        assert include_profile is True
        return {
            "local_llm_base_url": "http://127.0.0.1:8000/v1",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-v4-pro",
        }

    class _FakeOpenAI:
        def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
            assert base_url == "http://127.0.0.1:8000/v1"
            assert api_key == "test-key"
            assert timeout == chat_module._CLASSIFIER_TIMEOUT
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs):
            assert kwargs["model"] == "deepseek-v4-pro"
            assert kwargs["temperature"] == 0.0
            assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
            messages = kwargs["messages"]
            system_prompt = messages[0]["content"]
            user_query = messages[1]["content"]
            assert user_query == query
            assert "深圳哪些公司做激光雷达" in system_prompt
            assert "深圳做合成数据平台的企业" in system_prompt
            assert "做脑机接口的深圳团队" in system_prompt
            assert "介绍无界智航" in system_prompt
            assert "介绍王伟" in system_prompt
            assert "X 是谁" in system_prompt
            assert "不是单纯'地域 + 产业/技术'组合" in system_prompt
            payload = {**cases[user_query], "reason": "w13-7 mock"}
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(payload, ensure_ascii=False),
                        )
                    )
                ]
            )

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "resolve_professor_llm_settings", _fake_settings)
    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)

    return chat_module._classify_query_with_llm(query)


@pytest.mark.parametrize("query", B_CASES)
def test_b_regional_single_domain_queries_stay_b(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    result = _classify_with_mock_llm(monkeypatch, query)

    assert result is not None
    ctype = result["type"]
    assert ctype == "B"
    assert result.get("target_domain") == B_CASES[query]["target_domain"]


def test_deterministic_b_query_bypasses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic B query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm("深圳哪些公司做激光雷达")

    assert result is not None
    assert result["type"] == "B"
    assert result["topic"] == "激光雷达"
    assert result["target_domain"] == "company"


@pytest.mark.parametrize("query", ["夏树涛是谁？", "夏树涛是谁?"])
def test_deterministic_professor_who_query_strips_question_punctuation(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic professor who query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(query)

    assert result is not None
    assert result["type"] == "G"
    assert result["name"] == "夏树涛"
    assert result["target_domain"] == "professor"


def test_deterministic_b_query_strips_explicit_topic_switch_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic B query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm("对了，深圳哪些公司做激光雷达")

    assert result is not None
    assert result["type"] == "B"
    assert result["topic"] == "激光雷达"
    assert result["target_domain"] == "company"


def test_classifier_clears_proxy_env_before_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("http_proxy", "socks5://127.0.0.1:7890")
    monkeypatch.setenv("https_proxy", "socks5://127.0.0.1:7890")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:7890")

    monkeypatch.setattr(
        chat_module,
        "resolve_professor_llm_settings",
        lambda profile_name, *, include_profile: {
            "local_llm_base_url": "http://127.0.0.1:8000/v1",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-v4-pro",
        },
    )

    class _FakeOpenAI:
        def __init__(self, **_kwargs) -> None:
            assert "http_proxy" not in os.environ
            assert "https_proxy" not in os.environ
            assert "all_proxy" not in os.environ
            self.chat = SimpleNamespace(completions=self)

        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "type": "UNKNOWN",
                                    "topic": "",
                                    "name": "",
                                    "target_domain": "",
                                    "reason": "test",
                                }
                            )
                        )
                    )
                ]
            )

    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)

    result = chat_module._classify_query_with_llm("其中做大模型的")

    assert result is not None
    assert result["type"] == "UNKNOWN"


def test_deterministic_b_paper_topic_strips_query_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic B query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm("近两年具身智能方向的论文有哪些")

    assert result is not None
    assert result["type"] == "B"
    assert result["topic"] == "具身智能"
    assert result["target_domain"] == "paper"


def test_deterministic_english_paper_topic_query_routes_to_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic B query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm("查找 medical image analysis 方向的论文")

    assert result is not None
    assert result["type"] == "B"
    assert result["topic"] == "medical image analysis"
    assert result["target_domain"] == "paper"


def test_deterministic_english_paper_title_is_not_patent_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(
        "论文 Image Super-Resolution Using Deep Convolutional Networks"
    )

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == "Image Super-Resolution Using Deep Convolutional Networks"


def test_deterministic_paper_title_query_strips_wrappers_and_summary_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(
        "查找论文《Communication Efficient Federated Learning with Adaptive Quantization》的摘要和作者。"
    )

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == "Communication Efficient Federated Learning with Adaptive Quantization"


def test_deterministic_unicode_paper_title_query_strips_this_paper_summary_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(
        "High-speed silicon photonic Mach–Zehnder modulator at 2 μm 这篇论文的摘要是什么？"
    )

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == "High-speed silicon photonic Mach–Zehnder modulator at 2 μm"


def test_deterministic_paper_title_query_strips_this_paper_main_point_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    title = (
        "Global Fire Forecasts Using Both Large-Scale Climate Indices "
        "and Local Meteorological Parameters"
    )
    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(f"{title} 这篇论文主要讲什么？")

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == title


def test_deterministic_paper_title_query_strips_problem_statement_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    title = (
        "MLFA Towards Realistic Test Time Adaptive Object Detection "
        "by Multi-level Feature Alignment"
    )
    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(f"{title} 这篇论文主要解决什么问题？")

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == title


def test_deterministic_paper_title_query_strips_short_what_about_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    title = "Greedy Algorithms for the Profit-Aware Social Team Formation Problem"
    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(f"{title} 这篇论文讲什么？")

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == title


def test_deterministic_paper_title_query_strips_this_paper_what_is_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    title = (
        "Designing Mediated Social Touch for Mobile Communication: "
        "From Hand Gestures to Touch Signals"
    )
    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(f"{title} 这篇论文是什么")

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == title


def test_deterministic_long_paper_title_query_is_not_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic A paper query should not call LLM")

    title = (
        "Mendelian randomization analyses reveal causal relationships between "
        "the human microbiome and longevity"
    )
    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(f"{title} 这篇论文的摘要是什么？")

    assert result is not None
    assert result["type"] == "A"
    assert result["target_domain"] == "paper"
    assert result["name"] == title


def test_deterministic_ambiguous_paper_title_question_routes_to_g(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic G paper query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm(
        "Image Super-Resolution 是哪篇论文"
    )

    assert result is not None
    assert result["type"] == "G"
    assert result["target_domain"] == "paper"
    assert result["name"] == "Image Super-Resolution"


def test_deterministic_ambiguous_patent_title_question_routes_to_g(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedOpenAI:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("deterministic G patent query should not call LLM")

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "OpenAI", _UnexpectedOpenAI)

    result = chat_module._classify_query_with_llm("机器人控制是哪件专利")

    assert result is not None
    assert result["type"] == "G"
    assert result["target_domain"] == "patent"
    assert result["name"] == "机器人控制"


def test_paper_profile_selector_accepts_long_partial_title_match() -> None:
    query_title = "OctGLP-Net Learning Octree-Structured Context Entropy Model"
    selected = chat_module._select_exact_paper_profile_match(
        query_title,
        [
            {
                "paper_id": "PAPER-SPARSE",
                "title_clean": (
                    "OctGLP-Net: Learning Octree-Structured Context Entropy Model "
                    "for a Related Task"
                ),
                "summary_zh": None,
                "abstract_clean": None,
                "authors_display": "",
                "citation_count": 99,
                "year": 2025,
            },
            {
                "paper_id": "PAPER-RICH",
                "title_clean": (
                    "OctGLP-Net: Learning Octree-Structured Context Entropy Model "
                    "With Global-Local Perception for Point Cloud Geometry Compression"
                ),
                "summary_zh": "中文摘要。",
                "abstract_clean": "English abstract.",
                "authors_display": "A. Author",
                "citation_count": 1,
                "year": 2026,
            },
        ],
    )

    assert selected is not None
    assert selected["paper_id"] == "PAPER-RICH"


@pytest.mark.parametrize("query", G_CASES)
def test_g_intro_and_who_queries_stay_g(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    result = _classify_with_mock_llm(monkeypatch, query)

    assert result is not None
    ctype = result["type"]
    assert ctype == "G"
    assert result.get("target_domain") == G_CASES[query]["target_domain"]


def test_b_company_target_routes_to_company_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "激光雷达",
            "name": "",
            "target_domain": "company",
            "reason": "company semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: False)
    monkeypatch.setattr(
        chat_module,
        "_lookup_companies_by_topic",
        lambda _conn, *, topic: [
            {
                "company_id": "COMP-1",
                "canonical_name": "速腾聚创",
                "industry": "激光雷达",
                "business": "车载激光雷达供应商",
                "total_count": 1,
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="深圳哪些公司做激光雷达"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "B_company_topic_search"
    assert response.citations[0].type == "company"
    assert response.structured_payload["classifier_target_domain"] == "company"
    assert response.structured_payload["matched_objects"][0]["company_id"] == "COMP-1"


def test_g_company_query_routes_to_company_profile_when_single_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "G",
            "topic": "",
            "name": "无界智航",
            "target_domain": "company",
            "reason": "near-name company",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_company",
        lambda _conn, *, name: [
            {
                "company_id": "COMP-WJZH",
                "canonical_name": "深圳无界智航科技有限公司",
                "industry": "低空经济",
                "business": "无人机系统与自动驾驶飞控",
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍无界智航的相关信息"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_company_profile"
    assert response.citations[0].type == "company"
    assert response.structured_payload["company_id"] == "COMP-WJZH"
    assert "深圳无界智航科技有限公司" in response.answer_text


def test_g_company_query_returns_company_clarification_for_multiple_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "G",
            "topic": "",
            "name": "无界智航",
            "target_domain": "company",
            "reason": "near-name company",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_company",
        lambda _conn, *, name: [
            {
                "company_id": "COMP-SZ",
                "canonical_name": "深圳无界智航科技有限公司",
                "industry": "低空经济",
                "business": "无人机系统",
            },
            {
                "company_id": "COMP-YN",
                "canonical_name": "广南县无界智航科技有限公司",
                "industry": "科技服务",
                "business": "",
            },
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍无界智航"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "G_ambiguous_clarification"
    assert response.clarification is not None
    assert response.clarification.default_id == "COMP-SZ"
    assert [option.domain for option in response.clarification.options] == [
        "company",
        "company",
    ]
    assert "深圳无界智航科技有限公司" in response.answer_text


def test_company_entity_id_hint_bypasses_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"classifier": False}

    def classify(_query: str) -> dict[str, str]:
        called["classifier"] = True
        return {
            "type": "G",
            "topic": "",
            "name": "无界智航",
            "target_domain": "company",
            "reason": "near-name company",
        }

    monkeypatch.setattr(chat_module, "_classify_query_with_llm", classify)
    monkeypatch.setattr(
        chat_module,
        "_lookup_company_by_id",
        lambda _conn, *, company_id: {
            "company_id": company_id,
            "canonical_name": "深圳无界智航科技有限公司",
            "industry": "低空经济",
            "business": "无人机系统",
        },
    )

    response = chat_module.chat(
        chat_module.ChatRequest(
            query="介绍无界智航",
            entity_id_hint="COMP-SZ",
        ),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_company_profile"
    assert response.structured_payload["company_id"] == "COMP-SZ"
    assert called["classifier"] is False


def test_b_paper_topic_search_allows_non_ready_candidates_with_caveat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetrievalService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("filter_by_quality_status") is True:
                return []
            return [
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-1",
                    score=0.8,
                    snippet="Embodied intelligence for robot control",
                    source_url=None,
                    metadata={
                        "paper_id": "PAPER-1",
                        "year": 2025,
                        "venue": "ICRA",
                        "quality_status": "needs_review",
                    },
                )
            ]

    class _FakeRows:
        def fetchall(self):
            return [
                {
                    "paper_id": "PAPER-1",
                    "title_clean": "Embodied Intelligence for Robots",
                    "year": 2025,
                    "venue": "ICRA",
                    "quality_status": "needs_review",
                }
            ]

    class _FakeConn:
        def execute(self, _sql, _params):
            return _FakeRows()

    service = _FakeRetrievalService()
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "具身智能",
            "name": "",
            "target_domain": "paper",
            "reason": "paper semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="近两年具身智能方向的论文有哪些"),
        response=Response(),
        conn=_FakeConn(),
    )

    assert response.query_type == "B_paper_topic_search"
    assert response.citations[0].type == "paper"
    assert response.citations[0].label == "Embodied Intelligence for Robots"
    assert "质量门尚未完全完成" in response.answer_text
    assert response.structured_payload["matched_objects"][0]["quality_status"] == "needs_review"
    assert [call["filter_by_quality_status"] for call in service.calls] == [
        True,
        False,
    ]


def test_b_paper_topic_search_prefers_ready_candidates_without_caveat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetrievalService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return [
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-READY",
                    score=0.82,
                    snippet="Ready abstract chunk",
                    source_url=None,
                    metadata={"paper_id": "PAPER-READY", "quality_status": "ready"},
                ),
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-REVIEW",
                    score=0.81,
                    snippet="Non-ready abstract chunk",
                    source_url=None,
                    metadata={
                        "paper_id": "PAPER-REVIEW",
                        "quality_status": "needs_review",
                    },
                ),
            ]

    class _FakeRows:
        def fetchall(self):
            return [
                {
                    "paper_id": "PAPER-READY",
                    "title_clean": "Ready Paper",
                    "year": 2025,
                    "venue": "ICRA",
                    "identity_status": "confirmed",
                    "quality_status": "ready",
                },
                {
                    "paper_id": "PAPER-REVIEW",
                    "title_clean": "Needs Review Paper",
                    "year": 2025,
                    "venue": "ICRA",
                    "identity_status": "unverified",
                    "quality_status": "needs_review",
                },
            ]

    class _FakeConn:
        def execute(self, _sql, _params):
            return _FakeRows()

    service = _FakeRetrievalService()
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "机器人控制",
            "name": "",
            "target_domain": "paper",
            "reason": "paper semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)
    monkeypatch.setattr(chat_module, "_augment_rows_with_web", lambda query, rows, **_k: rows)

    response = chat_module.chat(
        chat_module.ChatRequest(query="机器人控制相关论文有哪些？"),
        response=Response(),
        conn=_FakeConn(),
    )

    matched = response.structured_payload["matched_objects"]
    assert [row["paper_id"] for row in matched] == ["PAPER-READY"]
    assert "质量门尚未完全完成" not in response.answer_text
    assert [call["filter_by_quality_status"] for call in service.calls] == [True]


def test_b_paper_topic_search_excludes_rejected_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetrievalService:
        def retrieve(self, **_kwargs):
            return [
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-READY",
                    score=0.82,
                    snippet="Ready abstract chunk",
                    source_url=None,
                    metadata={"paper_id": "PAPER-READY", "quality_status": "ready"},
                ),
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-REJECTED",
                    score=0.81,
                    snippet="Rejected stale duplicate chunk",
                    source_url=None,
                    metadata={
                        "paper_id": "PAPER-REJECTED",
                        "quality_status": "rejected",
                    },
                ),
            ]

    class _FakeRows:
        def fetchall(self):
            return [
                {
                    "paper_id": "PAPER-READY",
                    "title_clean": "Fast dynamic nonparametric distribution tracking in electron microscopic data",
                    "year": 2019,
                    "venue": "The Annals of Applied Statistics",
                    "quality_status": "ready",
                },
                {
                    "paper_id": "PAPER-REJECTED",
                    "title_clean": "Fast dynamic nonparametric distribution tracking in electron microscopic data. Annals of Applied Statistics",
                    "year": 2019,
                    "venue": None,
                    "quality_status": "rejected",
                },
            ]

    class _FakeConn:
        def execute(self, _sql, _params):
            return _FakeRows()

    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "纳米颗粒 TEM 动态非参数分布追踪",
            "name": "",
            "target_domain": "paper",
            "reason": "paper semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(
        chat_module, "get_retrieval_service", lambda: _FakeRetrievalService()
    )
    monkeypatch.setattr(chat_module, "_augment_rows_with_web", lambda query, rows, **_k: rows)

    response = chat_module.chat(
        chat_module.ChatRequest(query="纳米颗粒 TEM 动态非参数分布追踪相关论文有哪些？"),
        response=Response(),
        conn=_FakeConn(),
    )

    matched = response.structured_payload["matched_objects"]
    assert [row["paper_id"] for row in matched] == ["PAPER-READY"]
    assert [citation.id for citation in response.citations] == ["PAPER-READY"]
    assert "Rejected stale duplicate chunk" not in response.answer_text


def test_b_paper_topic_search_deduplicates_chunk_hits_by_paper_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetrievalService:
        def retrieve(self, **_kwargs):
            return [
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-1",
                    score=0.62,
                    snippet="Short duplicate chunk",
                    source_url=None,
                    metadata={"paper_id": "PAPER-1", "quality_status": "ready"},
                ),
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-2",
                    score=0.58,
                    snippet="Another paper chunk",
                    source_url=None,
                    metadata={"paper_id": "PAPER-2", "quality_status": "ready"},
                ),
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-1",
                    score=0.91,
                    snippet="Fuller duplicate chunk with better score and summary",
                    source_url=None,
                    metadata={"paper_id": "PAPER-1", "quality_status": "ready"},
                ),
            ]

    class _FakeRows:
        def fetchall(self):
            return [
                {
                    "paper_id": "PAPER-1",
                    "title_clean": "Hybrid Model Predictive Control",
                    "year": 2021,
                    "venue": "IEEE",
                    "quality_status": "ready",
                },
                {
                    "paper_id": "PAPER-2",
                    "title_clean": "Grid Inverter Control",
                    "year": 2022,
                    "venue": "ACM",
                    "quality_status": "ready",
                },
            ]

    class _FakeConn:
        def execute(self, _sql, _params):
            return _FakeRows()

    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "模型预测控制",
            "name": "",
            "target_domain": "paper",
            "reason": "paper semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(
        chat_module, "get_retrieval_service", lambda: _FakeRetrievalService()
    )
    monkeypatch.setattr(chat_module, "_augment_rows_with_web", lambda query, rows, **_k: rows)

    response = chat_module.chat(
        chat_module.ChatRequest(query="找模型预测控制相关论文"),
        response=Response(),
        conn=_FakeConn(),
    )

    citation_ids = [citation.id for citation in response.citations]
    object_ids = [
        row["paper_id"] for row in response.structured_payload["matched_objects"]
    ]

    assert citation_ids == ["PAPER-1", "PAPER-2"]
    assert object_ids == ["PAPER-1", "PAPER-2"]
    assert response.structured_payload["match_count"] == 2
    assert response.structured_payload["matched_objects"][0]["score"] == 0.91
    assert "Fuller duplicate chunk" in response.answer_text


def test_b_paper_topic_search_deduplicates_different_ids_by_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetrievalService:
        def retrieve(self, **_kwargs):
            return [
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-A",
                    score=0.40,
                    snippet="Lower score duplicate",
                    source_url=None,
                    metadata={"paper_id": "PAPER-A", "quality_status": "ready"},
                ),
                chat_module.Evidence(
                    object_type="paper",
                    object_id="PAPER-B",
                    score=0.82,
                    snippet="Higher score duplicate",
                    source_url=None,
                    metadata={"paper_id": "PAPER-B", "quality_status": "ready"},
                ),
            ]

    class _FakeRows:
        def fetchall(self):
            return [
                {
                    "paper_id": "PAPER-A",
                    "title_clean": "Adversarial Decoupling for Face Recognition",
                    "year": 2021,
                    "venue": "IEEE",
                    "quality_status": "ready",
                },
                {
                    "paper_id": "PAPER-B",
                    "title_clean": "Adversarial Decoupling for Face Recognition",
                    "year": 2021,
                    "venue": "IEEE",
                    "quality_status": "ready",
                },
            ]

    class _FakeConn:
        def execute(self, _sql, _params):
            return _FakeRows()

    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "人脸识别",
            "name": "",
            "target_domain": "paper",
            "reason": "paper semantic search",
        },
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(
        chat_module, "get_retrieval_service", lambda: _FakeRetrievalService()
    )
    monkeypatch.setattr(chat_module, "_augment_rows_with_web", lambda query, rows, **_k: rows)

    response = chat_module.chat(
        chat_module.ChatRequest(query="找人脸识别相关论文"),
        response=Response(),
        conn=_FakeConn(),
    )

    matched = response.structured_payload["matched_objects"]
    assert [row["paper_id"] for row in matched] == ["PAPER-B"]
    assert matched[0]["score"] == 0.82
    assert "Higher score duplicate" in response.answer_text
    assert "Lower score duplicate" not in response.answer_text


def test_lookup_paper_selects_summary_and_authors_for_profile() -> None:
    class _FakeRows:
        def fetchall(self):
            return []

    class _FakeConn:
        def __init__(self) -> None:
            self.sql = ""

        def execute(self, sql, _params):
            self.sql = sql
            return _FakeRows()

    conn = _FakeConn()

    chat_module._lookup_paper(
        conn,
        title="Communication Efficient Federated Learning with Adaptive Quantization",
    )

    assert "summary_zh" in conn.sql
    assert "authors_display" in conn.sql
    assert "identity_status, 'unverified') != 'rejected'" in conn.sql
    assert "quality_status, 'needs_enrichment') != 'rejected'" in conn.sql


def test_a_paper_profile_answer_surfaces_summary_and_authors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "A",
            "topic": "",
            "name": "Communication Efficient Federated Learning with Adaptive Quantization",
            "target_domain": "paper",
            "reason": "test",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_paper",
        lambda _conn, *, title: [
            {
                "paper_id": "PAPER-35204DCCD66B",
                "title_clean": title,
                "year": 2022,
                "venue": "ACM Transactions on Intelligent Systems and Technology",
                "authors_display": "Yuzhu Mao, Wenbo Ding",
                "summary_zh": "本文研究自适应量化下的通信高效联邦学习。",
                "abstract_clean": "This paper studies communication efficient federated learning.",
                "citation_count": None,
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(
            query="查找论文《Communication Efficient Federated Learning with Adaptive Quantization》的摘要和作者。"
        ),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_paper_profile"
    assert "作者：Yuzhu Mao, Wenbo Ding" in response.answer_text
    assert "摘要：本文研究自适应量化下的通信高效联邦学习。" in response.answer_text


def test_paper_id_related_professors_query_returns_linked_professors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_lookup_paper_related_professors",
        lambda _conn, *, paper_id: [
            {
                "professor_id": "PROF-YUESHENG",
                "canonical_name": "岳晟",
                "institution": "南方科技大学",
                "title": "副教授",
            }
        ],
        raising=False,
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="PAPER-C0CB4902CF93 的关联教授是谁？"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert response.citations[0].type == "professor"
    assert response.citations[0].id == "PROF-YUESHENG"
    assert "岳晟" in response.answer_text


def test_a_paper_profile_selects_rich_exact_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    title = (
        "Mendelian randomization analyses reveal causal relationships between "
        "the human microbiome and longevity"
    )
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "A",
            "topic": "",
            "name": title,
            "target_domain": "paper",
            "reason": "test",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_paper",
        lambda _conn, *, title: [
            {
                "paper_id": "PAPER-SPARSE",
                "title_clean": title,
                "year": 2023,
                "venue": "Nature Aging",
                "authors_display": "",
                "summary_zh": None,
                "abstract_clean": None,
                "citation_count": 999,
            },
            {
                "paper_id": "PAPER-RICH",
                "title_clean": title,
                "year": 2023,
                "venue": "Nature Aging",
                "authors_display": "A. Author",
                "summary_zh": "中文摘要。",
                "abstract_clean": "English abstract.",
                "citation_count": 1,
            },
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query=f"{title} 这篇论文的摘要是什么？"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_paper_profile"
    assert response.structured_payload["paper_id"] == "PAPER-RICH"
    assert "摘要：中文摘要。" in response.answer_text
