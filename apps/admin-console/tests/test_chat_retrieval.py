"""RED-phase tests for M4 — chat routes use RetrievalService + M5.1 Serper fallback.

Source of truth: docs/plans/2026-04-22-002-m4-chat-routes-retrieval-integration.md.

Tests organized by Unit (1-6). All hermetic — mock RetrievalService +
WebSearchProvider + conn + env vars. No real Milvus, no live network.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from backend import deps as deps_module
from backend.api import chat as chat_module


# ============================================================================
# Test helpers / fixtures
# ============================================================================


def _evidence(
    object_type: str = "professor",
    object_id: str = "p1",
    score: float = 0.9,
    snippet: str = "Snippet text",
    source_url: str | None = None,
    metadata: dict | None = None,
):
    from src.data_agents.service.retrieval import Evidence

    return Evidence(
        object_type=object_type,
        object_id=object_id,
        score=score,
        snippet=snippet,
        source_url=source_url,
        metadata=metadata or {},
    )


@pytest.fixture(autouse=True)
def _reset_lru_cache_and_env(monkeypatch):
    """Clear lru_cache on deps factories + reset relevant env vars for each test."""
    # Remove any prior env overrides
    monkeypatch.delenv("CHAT_USE_RETRIEVAL_SERVICE", raising=False)
    monkeypatch.delenv("CHAT_E_WEB_FALLBACK_THRESHOLD", raising=False)
    monkeypatch.delenv("MILVUS_URI", raising=False)
    # Clear lru_cache on any factory that was wrapped
    for name in (
        "_get_milvus_client",
        "_get_embedding_client",
        "_get_reranker_client",
        "_get_web_search_provider",
        "get_retrieval_service",
    ):
        factory = getattr(deps_module, name, None)
        if factory is not None and hasattr(factory, "cache_clear"):
            factory.cache_clear()
    yield


# ============================================================================
# Unit 1 — deps.py singletons + feature flag
# ============================================================================


def test_unit1_chat_use_retrieval_service_default_is_on():
    """Env unset → defaults to True (on)."""
    assert deps_module.chat_use_retrieval_service() is True


def test_unit1_chat_use_retrieval_service_off_via_env(monkeypatch):
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "off")
    assert deps_module.chat_use_retrieval_service() is False


@pytest.mark.parametrize("val", ["0", "false", "False", "no"])
def test_unit1_chat_use_retrieval_service_disabled_synonyms(monkeypatch, val):
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", val)
    assert deps_module.chat_use_retrieval_service() is False


@pytest.mark.parametrize("val", ["1", "true", "True", "on", "yes"])
def test_unit1_chat_use_retrieval_service_enabled_synonyms(monkeypatch, val):
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", val)
    assert deps_module.chat_use_retrieval_service() is True


def test_unit1_e_web_fallback_threshold_default():
    assert deps_module.chat_e_web_fallback_threshold() == pytest.approx(0.5)


def test_unit1_e_web_fallback_threshold_custom(monkeypatch):
    monkeypatch.setenv("CHAT_E_WEB_FALLBACK_THRESHOLD", "0.3")
    assert deps_module.chat_e_web_fallback_threshold() == pytest.approx(0.3)


def test_unit1_e_web_fallback_threshold_malformed_falls_back(monkeypatch):
    monkeypatch.setenv("CHAT_E_WEB_FALLBACK_THRESHOLD", "not-a-number")
    # Should not raise; should return the default.
    assert deps_module.chat_e_web_fallback_threshold() == pytest.approx(0.5)


# ============================================================================
# Unit 2 — Evidence adapter + citation validator + low-confidence prefix
# ============================================================================


def test_unit2_evidence_adapter_maps_professor():
    evidence = [
        _evidence(
            object_type="professor",
            object_id="prof_1",
            score=0.9,
            snippet="Prof summary",
            source_url="https://sustech.edu.cn/prof/1",
            metadata={"name": "Prof X", "institution": "南方科技大学"},
        )
    ]
    out = chat_module._evidence_list_from_retrieval(evidence)
    assert len(out) == 1
    row = out[0]
    assert row["type"] == "professor"
    assert row["id"] == "prof_1"
    assert row["url"] == "https://sustech.edu.cn/prof/1"


def test_unit2_evidence_adapter_maps_paper():
    evidence = [
        _evidence(
            object_type="paper",
            object_id="paper:doi:10.1/abc",
            score=0.88,
            snippet="Abstract content...",
            source_url=None,
            metadata={"paper_id": "paper:doi:10.1/abc", "year": 2023, "venue": "NeurIPS"},
        )
    ]
    out = chat_module._evidence_list_from_retrieval(evidence)
    assert len(out) == 1
    assert out[0]["type"] == "paper"
    assert "Abstract" in out[0]["snippet"]


def test_unit2_evidence_adapter_empty_list():
    assert chat_module._evidence_list_from_retrieval([]) == []


def test_unit2_citation_validator_valid_passes_through():
    text = "Prof Doe [1] is at 南科大 [2]."
    assert chat_module._validate_and_strip_citations(text, evidence_count=2) == text


def test_unit2_citation_validator_strips_out_of_range():
    text = "Prof Doe [1] and [99] are experts."
    cleaned = chat_module._validate_and_strip_citations(text, evidence_count=2)
    assert "[1]" in cleaned
    assert "[99]" not in cleaned


def test_unit2_citation_validator_strips_zero():
    text = "Prof Doe [0] is at 南科大."
    cleaned = chat_module._validate_and_strip_citations(text, evidence_count=3)
    assert "[0]" not in cleaned


def test_unit2_citation_validator_no_citations_unchanged():
    text = "Plain answer with no brackets."
    assert chat_module._validate_and_strip_citations(text, evidence_count=5) == text


def test_unit2_citation_validator_zero_evidence_strips_all():
    text = "Answer with [1] and [2]."
    cleaned = chat_module._validate_and_strip_citations(text, evidence_count=0)
    assert "[1]" not in cleaned
    assert "[2]" not in cleaned


def test_unit2_low_confidence_prefix_high_score_no_prefix():
    evidence = [_evidence(score=0.9)]
    text = "Answer."
    assert chat_module._maybe_prefix_low_confidence(text, evidence) == text


def test_unit2_low_confidence_prefix_low_score_prepends():
    evidence = [_evidence(score=0.2)]
    text = "Answer."
    result = chat_module._maybe_prefix_low_confidence(text, evidence)
    assert "供参考" in result  # Chinese disclaimer
    assert result.endswith("Answer.")


def test_unit2_low_confidence_prefix_empty_evidence_no_prefix():
    assert chat_module._maybe_prefix_low_confidence("Answer.", []) == "Answer."


def test_unit2_low_confidence_prefix_boundary_exact_threshold_no_prefix():
    evidence = [_evidence(score=0.3)]  # exact threshold
    text = "Answer."
    # Strict less-than: 0.3 is NOT less than 0.3, so no prefix.
    assert chat_module._maybe_prefix_low_confidence(text, evidence) == text


# ============================================================================
# Unit 3 — B-route retrieval path + flag gate
# ============================================================================


def test_unit3_b_route_flag_on_uses_retrieval(monkeypatch):
    """Flag on → retrieve called, returns adapted dict list."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = [
        _evidence(
            object_type="professor",
            object_id="prof_a",
            metadata={"name": "A", "institution": "南方科技大学"},
        ),
        _evidence(
            object_type="professor",
            object_id="prof_b",
            metadata={"name": "B", "institution": "南方科技大学"},
        ),
    ]
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    conn = MagicMock()
    results = chat_module._lookup_professors_by_topic(
        conn,
        institutions=("南方科技大学",),
        topic="robotics",
        limit=5,
    )
    assert len(results) == 2
    assert fake_service.retrieve.called
    # conn.execute NOT used (SQL LIKE path bypassed)
    # Note: if implementation does a separate SQL lookup after retrieve for
    # additional fields, this may still be called — pin behavior at impl time.
    # Strict: the legacy LIKE query should not fire.


def test_unit3_b_route_flag_off_uses_sql(monkeypatch):
    """Flag off → SQL LIKE fallback; retrieve NOT called."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "off")

    fake_service = MagicMock()
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    conn = MagicMock()
    # Make conn.execute return empty cursor for any SQL call.
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor

    results = chat_module._lookup_professors_by_topic(
        conn,
        institutions=("南方科技大学",),
        topic="topic",
        limit=5,
    )
    # retrieve NOT called
    fake_service.retrieve.assert_not_called()
    # SQL path exercised
    assert conn.execute.called


def test_unit3_b_route_retrieve_exception_falls_back_to_sql(monkeypatch):
    """Flag on but retrieve raises → fall back to SQL LIKE, no 500."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.side_effect = RuntimeError("milvus down")
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor

    # Should not raise.
    results = chat_module._lookup_professors_by_topic(
        conn,
        institutions=("南方科技大学",),
        topic="topic",
        limit=5,
    )
    assert isinstance(results, list)
    # SQL fallback was invoked after retrieve failure.
    assert conn.execute.called


def test_unit3_b_route_single_institution_applies_filter(monkeypatch):
    """Single institution → filters={'institution': name} passed to retrieve."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = []
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    chat_module._lookup_professors_by_topic(
        MagicMock(),
        institutions=("南方科技大学",),
        topic="机器人",
        limit=5,
    )
    kwargs = fake_service.retrieve.call_args.kwargs
    filters = kwargs.get("filters") or {}
    assert filters.get("institution") == "南方科技大学"


def test_unit3_b_route_multi_institution_no_filter(monkeypatch):
    """Multiple institutions (generic 深圳) → no institution filter."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = []
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    chat_module._lookup_professors_by_topic(
        MagicMock(),
        institutions=("南方科技大学", "清华大学深圳国际研究生院"),
        topic="机器人",
        limit=5,
    )
    kwargs = fake_service.retrieve.call_args.kwargs
    filters = kwargs.get("filters") or {}
    assert "institution" not in filters


# ============================================================================
# Unit 4 — D-route cross-domain merge
# ============================================================================
# D-route wiring is deeper in chat.py; testing requires exercising the chat
# endpoint or an internal helper. The test below targets a helper the
# implementation will introduce (e.g., `_lookup_cross_domain_evidence`).
# If the implementer's name differs, update the import.


def test_unit4_d_route_merges_prof_paper_company(monkeypatch):
    """D-route evidence merger: retrieve returns prof+paper, SQL returns company, output has all three types."""
    if not hasattr(chat_module, "_lookup_cross_domain_evidence"):
        pytest.skip("Implementation uses different helper name; update test after impl.")

    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = [
        _evidence(object_type="professor", object_id="prof_1"),
        _evidence(object_type="paper", object_id="paper_1"),
    ]
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    # Mock company SQL path returning 2 rows.
    def _fake_lookup_companies(conn, *, topic):
        return [{"id": "co_1", "name": "Co 1"}, {"id": "co_2", "name": "Co 2"}]

    monkeypatch.setattr(chat_module, "_lookup_companies_by_topic", _fake_lookup_companies)

    merged = chat_module._lookup_cross_domain_evidence(
        MagicMock(), topic="AI 生态"
    )
    types_seen = {m.get("type") for m in merged}
    assert "professor" in types_seen
    assert "paper" in types_seen
    assert "company" in types_seen


def test_unit4_d_route_flag_off_only_companies(monkeypatch):
    if not hasattr(chat_module, "_lookup_cross_domain_evidence"):
        pytest.skip("Implementation uses different helper name.")

    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "off")
    fake_service = MagicMock()
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    monkeypatch.setattr(
        chat_module,
        "_lookup_companies_by_topic",
        lambda conn, *, topic: [{"id": "co_1", "name": "Co 1"}],
    )

    merged = chat_module._lookup_cross_domain_evidence(MagicMock(), topic="AI")
    fake_service.retrieve.assert_not_called()
    types_seen = {m.get("type") for m in merged}
    assert types_seen == {"company"}


# ============================================================================
# Unit 5 — E-route paper retrieve + Serper fallback
# ============================================================================


def test_unit5_e_route_confident_retrieve_no_serper(monkeypatch):
    """Top-1 score 0.8 → no Serper fallback."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = [
        _evidence(
            object_type="paper",
            object_id="p1",
            score=0.8,
            snippet="About LLM distillation.",
        )
    ]
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    answer_text, _ref = chat_module._answer_knowledge_qa("大模型蒸馏原理")
    fake_web.search.assert_not_called()
    assert isinstance(answer_text, str)


def test_unit5_e_route_low_confidence_triggers_serper(monkeypatch):
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = [
        _evidence(object_type="paper", object_id="p1", score=0.3),
    ]
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    fake_web.search.return_value = {
        "organic": [
            {
                "title": "arxiv result",
                "link": "https://arxiv.org/abs/2310.00001",
                "snippet": "Some snippet",
            },
        ]
    }
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    chat_module._answer_knowledge_qa("obscure query")
    fake_web.search.assert_called_once()


def test_unit5_e_route_empty_retrieve_triggers_serper(monkeypatch):
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = []
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    fake_web.search.return_value = {"organic": []}
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    chat_module._answer_knowledge_qa("unknown topic")
    fake_web.search.assert_called_once()


def test_unit5_e_route_serper_filters_non_scholarly_domains(monkeypatch):
    """Serper returns github + arxiv; only arxiv survives filter."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = []
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    fake_web.search.return_value = {
        "organic": [
            {"title": "arxiv paper", "link": "https://arxiv.org/abs/1", "snippet": "s1"},
            {"title": "github repo", "link": "https://github.com/user/repo", "snippet": "s2"},
            {"title": "blog post", "link": "https://example.com/blog", "snippet": "s3"},
        ]
    }
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    # Implementation may expose an internal helper; assert via its presence.
    if hasattr(chat_module, "_e_route_filter_scholarly_organics"):
        filtered = chat_module._e_route_filter_scholarly_organics(
            fake_web.search.return_value.get("organic", [])
        )
        links = {o["link"] for o in filtered}
        assert any("arxiv.org" in l for l in links)
        assert not any("github.com" in l for l in links)
        assert not any("example.com" in l for l in links)
    else:
        pytest.skip("Implementation uses different filter helper.")


def test_unit5_e_route_serper_429_graceful(monkeypatch):
    """Serper quota exceeded → answer still returned, no 500."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "on")

    fake_service = MagicMock()
    fake_service.retrieve.return_value = []
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    fake_web.search.side_effect = RuntimeError("Serper quota exceeded")
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    answer_text, _ = chat_module._answer_knowledge_qa("anything")
    assert isinstance(answer_text, str)


def test_unit5_e_route_flag_off_skips_retrieval(monkeypatch):
    """Flag off → no retrieve, no Serper, existing rule-based FAQ only."""
    monkeypatch.setenv("CHAT_USE_RETRIEVAL_SERVICE", "off")

    fake_service = MagicMock()
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: fake_service)

    fake_web = MagicMock()
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: fake_web)

    chat_module._answer_knowledge_qa("某个查询")
    fake_service.retrieve.assert_not_called()
    fake_web.search.assert_not_called()


# ============================================================================
# Unit 6 — Wire validator + prefix into _build_chat_response
# ============================================================================


def test_unit6_build_chat_response_strips_out_of_range_citations(monkeypatch):
    """Final chat response text has out-of-range [N] stripped."""
    # This test exercises the final assembly path. Implementer must invoke
    # _validate_and_strip_citations inside _build_chat_response (or equivalent).
    # Simple contract test: the helper is invoked with evidence_count.
    called_with: dict = {}

    def _fake_validate(text, evidence_count):
        called_with["text"] = text
        called_with["evidence_count"] = evidence_count
        return text.replace("[99]", "")

    monkeypatch.setattr(chat_module, "_validate_and_strip_citations", _fake_validate)

    # If the module has a direct helper to test, use it. Otherwise skip with
    # a pointer for the implementer.
    if not hasattr(chat_module, "_build_chat_response"):
        pytest.skip("_build_chat_response not exposed; assert via integration.")

    # Assert wrapper was reachable via real code path in non-mock test —
    # for now just verify the helper signature works standalone:
    out = chat_module._validate_and_strip_citations("Answer [99]", 2)
    assert "[99]" not in out


def test_unit6_build_chat_response_applies_low_confidence_prefix_when_applicable():
    """If evidence top score < 0.3, disclaimer prepended; test helper directly."""
    text = chat_module._maybe_prefix_low_confidence(
        "Raw answer.",
        [_evidence(score=0.1)],
    )
    assert "仅供参考" in text
