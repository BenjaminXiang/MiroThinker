"""Pre-classification routes meta questions away from the retrieval pipeline."""

from __future__ import annotations

from backend.services.canonical_v2_chat import _pre_route, _self_response


def test_identity_questions_route_to_identity() -> None:
    for query in ("你是谁", "你是谁？", "你叫什么"):
        assert _pre_route(query) == "identity"


def test_capability_questions_route_to_capabilities() -> None:
    for query in ("你能做什么", "你有什么功能", "怎么用", "使用说明"):
        assert _pre_route(query) == "capabilities"


def test_domain_questions_are_not_intercepted() -> None:
    for query in ("丁文伯是谁", "优必选有哪些专利", "今天几号", "深圳有哪些机器人公司"):
        assert _pre_route(query) is None


def test_self_response_shape() -> None:
    response = _self_response("你能做什么", "capabilities")

    assert "查教授" in response.answer_text
    assert response.query_type == "canonical_v2:A:direct_capabilities"
    assert response.citations == []


def test_core_name_strips_prefix_and_suffix() -> None:
    from backend.services.canonical_v2_chat import _core_name

    assert _core_name("深圳市优必选科技股份有限公司") == "优必选"
    assert _core_name("深圳鹏行智能研究有限公司") == "鹏行智能研究"


def test_entity_query_patterns() -> None:
    from backend.services.canonical_v2_chat import _ENTITY_INTRO_QUERY, _ENTITY_QUERY

    for query in ("丁文伯是谁", "优必选是做什么的"):
        assert _ENTITY_QUERY.match(query) is not None
    assert _ENTITY_INTRO_QUERY.match("介绍一下丁文伯") is not None
    for query in ("优必选有哪些专利", "今天几号"):
        assert _ENTITY_QUERY.match(query) is None
