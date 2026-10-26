"""Unit tests for the validated answer cache (fresh local-only turns)."""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.canonical_v2_answer_cache import (
    AnswerCache,
    eligible_query,
    query_key,
    validate_candidate,
)


def _citation(citation_type: str = "company", citation_id: str = "local-source-abc"):
    return SimpleNamespace(type=citation_type, id=citation_id, label="示例公司")


def _response(citations, *, citation_map=None, answer_text="示例回答"):
    return SimpleNamespace(
        answer_text=answer_text,
        citations=list(citations),
        citation_map=(
            {citation.id: citation.label for citation in citations}
            if citation_map is None
            else citation_map
        ),
    )


def _turn_result(citations, *, answer_text="示例回答", **overrides):
    values = {
        "response_mode": "answer",
        "render_mode": "prose_renderer",
        "fallback_sha256": None,
        "citations": tuple(citations),
        "conflicts": (),
        "answer_text": answer_text,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_eligible_query_rejects_referents_and_time_sensitivity() -> None:
    assert eligible_query("优必选有哪些专利") == (True, "ok")
    assert eligible_query("他有哪些专利") == (False, "referent")
    assert eligible_query("最新的机器人公司") == (False, "time_sensitive")


def test_validate_candidate_accepts_local_grounded_answer() -> None:
    citations = [_citation()]
    answer = "优必选拥有多项专利。" * 5
    ok, checks = validate_candidate(
        query="优必选有哪些专利",
        response=_response(citations, answer_text=answer),
        turn_result=_turn_result(citations, answer_text=answer),
    )
    assert ok, checks
    assert all(checks.values())


def test_validate_candidate_rejects_web_citation() -> None:
    citations = [_citation("web", "web-source-1")]
    ok, checks = validate_candidate(
        query="优必选有哪些专利",
        response=_response(citations),
        turn_result=_turn_result(citations, answer_text="网页来源。" * 10),
    )
    assert not ok
    assert checks["local_grounding"] is False


def test_validate_candidate_accepts_mixed_local_and_web_citations() -> None:
    """The gate that wrote zero rows: real answers mix local and web evidence.

    Adopted from the 2026-10-26 hot patch. Before it, `local_only` demanded every
    citation be local, so a grounded answer that also cited the current web page
    could never cache, and the 1200-character ceiling rejected the 1–3k prose
    answers that actually ship.
    """

    citations = [
        _citation("professor", "local-source-abc"),
        _citation("web", "web-source-1"),
    ]
    answer = "丁文伯的主要研究方向包括信号处理、机器人与机器学习。" * 60

    ok, checks = validate_candidate(
        query="丁文伯的研究方向有哪些",
        response=_response(citations, answer_text=answer),
        turn_result=_turn_result(citations, answer_text=answer),
    )

    assert ok, checks
    assert checks["local_grounding"] is True
    assert checks["length"] is True
    assert len(answer) > 1200


def test_validate_candidate_rejects_marker_and_allows_coverage_tail() -> None:
    """Protocol markers are refused; an enumeration coverage tail is not.

    The deployed gate validates the HTTP envelope, so the checks read
    `response.answer_text`. The old local-only gate also rejected answers that
    listed several companies ("member wall"); enumeration answers legitimately
    end with a bounded coverage tail, and rejecting them kept the cache empty.
    """

    citations = [_citation()]
    marker_text = "</|canonical_v2_answer_v1|> 这是一段足够长的回答内容。" * 2
    marker = _turn_result(citations, answer_text=marker_text)
    ok, checks = validate_candidate(
        query="优必选有哪些专利",
        response=_response(citations, answer_text=marker_text),
        turn_result=marker,
    )
    assert not ok and checks["no_marker"] is False

    tail_text = (
        "这是一段足够长的回答内容，满足长度要求。"
        "此外，本次检索还召回以下相关本地企业：甲公司、乙公司。"
    )
    wall = _turn_result(citations, answer_text=tail_text)
    ok, checks = validate_candidate(
        query="深圳有哪些机器人公司",
        response=_response(citations, answer_text=tail_text),
        turn_result=wall,
    )
    assert ok, checks
    assert "no_member_wall" not in checks


def test_validate_candidate_accepts_index_keyed_citation_map() -> None:
    citations = [_citation()]
    answer = "这是一段足够长的回答内容。" * 5
    ok, checks = validate_candidate(
        query="优必选有哪些专利",
        response=_response(
            citations, citation_map={"1": citations[0].id}, answer_text=answer
        ),
        turn_result=_turn_result(citations, answer_text=answer),
    )
    assert ok, checks


def test_validate_candidate_requires_resolvable_citation_map() -> None:
    citations = [_citation()]
    ok, checks = validate_candidate(
        query="优必选有哪些专利",
        response=_response(citations, citation_map={}),
        turn_result=_turn_result(citations, answer_text="这是一段足够长的回答内容。" * 3),
    )
    assert not ok and checks["citation_map"] is False


def test_cache_round_trip_hits_until_release_or_epoch_changes(tmp_path) -> None:
    cache = AnswerCache(tmp_path / "cache.sqlite3")
    payload = {"response": {"answer_text": "ok"}, "turn_result": {}}
    cache.put(
        "优必选有哪些专利",
        payload,
        release_id="candidate-r1",
        epoch="epoch-1",
        validation={"ok": True},
    )

    assert cache.get(
        "优必选有哪些专利", release_id="candidate-r1", epoch="epoch-1"
    ) == payload
    assert (
        cache.get("优必选有哪些专利", release_id="candidate-r2", epoch="epoch-1")
        is None
    )
    assert (
        cache.get("优必选有哪些专利", release_id="candidate-r1", epoch="epoch-2")
        is None
    )


def test_cache_expired_entry_misses_and_purges(tmp_path) -> None:
    cache = AnswerCache(tmp_path / "cache.sqlite3", ttl_seconds=-1)
    cache.put(
        "优必选有哪些专利",
        {"response": {}},
        release_id="candidate-r1",
        epoch="epoch-1",
        validation={},
    )
    assert (
        cache.get("优必选有哪些专利", release_id="candidate-r1", epoch="epoch-1")
        is None
    )
    assert cache.purge_expired() == 1


def test_query_key_is_stable_for_surrounding_whitespace() -> None:
    assert query_key("  优必选有哪些专利 ") == query_key("优必选有哪些专利")
