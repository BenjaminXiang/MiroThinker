from __future__ import annotations

from backend.services.canonical_v2_chat import _standalone_anchor


def test_standalone_anchor_resolves_professor_company_relation() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(query: str, domain: str) -> tuple[str, str] | None:
        calls.append((query, domain))
        if domain == "professor":
            return ("professor-c-ding", "丁文伯")
        return None

    assert _standalone_anchor("丁文伯创办的公司是哪家", resolver) == (
        "professor-c-ding",
        "丁文伯",
    )
    assert calls == [("丁文伯创办的公司是哪家", "professor")]


def test_standalone_anchor_resolves_company_founder_relation() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(query: str, domain: str) -> tuple[str, str] | None:
        calls.append((query, domain))
        if domain == "company":
            return ("company-c-xspark", "深圳无界智航科技有限公司")
        return None

    assert _standalone_anchor("无界智航的创始人是谁", resolver) == (
        "company-c-xspark",
        "深圳无界智航科技有限公司",
    )
    assert calls == [("无界智航的创始人是谁", "company")]


def test_standalone_anchor_declines_unrelated_or_ambiguous() -> None:
    def ambiguous(query: str, domain: str) -> tuple[str, str] | None:
        return None

    assert _standalone_anchor("今天天气怎么样", ambiguous) is None
    assert _standalone_anchor("丁文伯创办的公司", ambiguous) is None


def test_topic_professor_query_does_not_anchor_a_company() -> None:
    """`有哪些做 X 的教授` is topic discovery, not a named-company relation.

    Adopted from the 2026-10-26 hot patch: without this guard the query reached
    the exact-name resolver, whose name forms derive `灵巧` from the alias
    `灵巧智能`, matched 浙江灵巧智能科技有限公司 inside `灵巧手`, and turned the
    turn into a company→professor traversal with zero evidence.
    """

    calls: list[tuple[str, str]] = []

    def resolver(query: str, domain: str) -> tuple[str, str] | None:
        calls.append((query, domain))
        if domain == "company":
            return ("company-c-lingqiao", "浙江灵巧智能科技有限公司")
        return None

    assert _standalone_anchor("有哪些做具身智能和灵巧手的教授", resolver) is None
    assert calls == []


def test_topic_guard_does_not_swallow_named_relations() -> None:
    """A query that names a company keeps its anchor (the guard is narrow)."""

    calls: list[tuple[str, str]] = []

    def resolver(query: str, domain: str) -> tuple[str, str] | None:
        calls.append((query, domain))
        if domain == "professor":
            return ("professor-c-ding", "丁文伯")
        return None

    assert _standalone_anchor("丁文伯教授创办了哪些公司", resolver) == (
        "professor-c-ding",
        "丁文伯",
    )
    assert calls == [("丁文伯教授创办了哪些公司", "professor")]


def test_local_patent_count_response_answers_named_company() -> None:
    from backend.services.canonical_v2_chat import _local_patent_count_response

    def resolver(query: str, domain: str) -> tuple[str, str] | None:
        if domain == "company":
            return ("company-c-ubtech", "深圳市优必选科技股份有限公司")
        return None

    response = _local_patent_count_response(
        query="本地知识库收录了优必选多少专利",
        resolver=resolver,
        counter=lambda company_id: 450,
    )

    assert response is not None
    assert "450 件专利" in response.answer_text
    assert response.citations[0].label == "深圳市优必选科技股份有限公司"
    assert response.structured_payload["local_patent_count"] == 450


def test_local_patent_count_response_skips_listing_query() -> None:
    from backend.services.canonical_v2_chat import _local_patent_count_response

    response = _local_patent_count_response(
        query="优必选有哪些专利",
        resolver=lambda query, domain: ("company-c-ubtech", "优必选"),
        counter=lambda company_id: 450,
    )

    assert response is None
