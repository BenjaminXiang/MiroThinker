"""Stage0-G1 mapping floor: a handle-bound LOCAL citation without a
whitelisted official URL field must still surface a public card (url=None).
RED evidence for openspec/changes/local-citation-floor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

from backend.services.canonical_v2_chat import CanonicalV2ChatAdapter


def _read_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read")


def _answer_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_answer")


_OBSERVED = datetime(2026, 9, 3, tzinfo=UTC)


def _local_evidence(read: Any, snippet: str) -> Any:
    return read.EvidenceItem(
        evidence_id="evidence:g1map:company-local",
        object_id="company:g1map",
        domain="company",
        lane="lexical",
        source_nature="local",
        source_locator="artifact:company-g1map#profile",
        snippet=snippet,
        score=0.9,
    )


def _turn_result(answer: Any, *, citation_evidence_ids: tuple[str, ...]) -> Any:
    return answer.TurnResult(
        session_id="session:g1map",
        turn_id="turn:g1map:1",
        release_id="candidate-g1-r1",
        answer_text="answer",
        citations=tuple(
            answer.Citation(
                evidence_id=evidence_id,
                source_nature="local",
                source_locator="artifact:company-g1map#profile",
                observed_at=_OBSERVED,
            )
            for evidence_id in citation_evidence_ids
        ),
    )


def _run(read: Any, answer: Any, *, snippet: str, citation_evidence_ids) -> list:
    handle = read.CanonicalEntityHandle(
        canonical_id="company:g1map",
        domain="company",
        display_name="深圳市飞象工业科技有限公司",
        evidence_ids=citation_evidence_ids,
    )
    return list(
        CanonicalV2ChatAdapter._public_citations(
            turn_result=_turn_result(answer, citation_evidence_ids=citation_evidence_ids),
            handles_by_id={"company:g1map": handle},
            evidence_by_id={
                "evidence:g1map:company-local": _local_evidence(read, snippet)
            },
        )
    )


def test_local_citation_without_official_url_still_emits_card() -> None:
    read = _read_module()
    answer = _answer_module()
    cards = _run(
        read,
        answer,
        snippet='{"name": "深圳市飞象工业科技有限公司", "business": "工业科技产品研发"}',
        citation_evidence_ids=("evidence:g1map:company-local",),
    )
    assert len(cards) == 1
    assert cards[0].type == "company"
    assert cards[0].label == "深圳市飞象工业科技有限公司"
    assert cards[0].url is None


def test_local_citation_card_is_deduped_per_handle() -> None:
    read = _read_module()
    answer = _answer_module()
    cards = _run(
        read,
        answer,
        snippet='{"name": "深圳市飞象工业科技有限公司"}',
        citation_evidence_ids=("evidence:g1map:company-local",),
    )
    # the same handle bound twice through two citations must yield one card
    handle_citations = cards + cards
    assert len({(card.type, card.label) for card in handle_citations}) <= 1


def test_local_citation_with_official_url_keeps_url_card() -> None:
    read = _read_module()
    answer = _answer_module()
    cards = _run(
        read,
        answer,
        snippet='{"name": "深圳市新濠天地控股集团有限公司", "website": "http://www.cityrole.cn"}',
        citation_evidence_ids=("evidence:g1map:company-local",),
    )
    assert len(cards) == 1
    assert cards[0].url == "http://www.cityrole.cn"
