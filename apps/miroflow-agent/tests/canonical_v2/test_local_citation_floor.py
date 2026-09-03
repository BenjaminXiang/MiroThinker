"""Stage0-G1 selector floor: a query that names a canonical entity must keep
at least one local claim for it, even when the local item carries no field
claim_binding. RED evidence for openspec/changes/local-citation-floor.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def _read_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read")


def _serving_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_serving_isolated")


def _answer_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_answer")


def _bundle(serving: Any) -> Any:
    # select() reads only the claim-window fields; the full recorded bundle
    # is hash-bound to a release and irrelevant to this unit seam.
    return serving.RecordedServingBundle.model_construct(
        max_candidates=8,
        max_web_results=8,
        answer_model_id="canonical-v2-deterministic-answer-v1",
    )


def _local_item(read: Any, *, binding: Any = None, lane: str = "lexical") -> Any:
    return read.EvidenceItem(
        evidence_id="evidence:g1:company-local",
        object_id="company:g1-feixiang",
        domain="company",
        lane=lane,
        source_nature="local",
        source_locator="artifact:company-g1#profile",
        snippet=(
            '{"name": "深圳市飞象工业科技有限公司", "business": "工业科技产品研发", '
            '"industry": "工业自动化"}'
        ),
        score=0.9,
        claim_binding=binding,
    )


def _web_item(read: Any) -> Any:
    return read.EvidenceItem(
        evidence_id="evidence:g1:company-web",
        object_id="company:g1-feixiang",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.com/feixiang",
        snippet="深圳市飞象工业科技有限公司是一家工业科技公司；来源：https://example.com/feixiang",
        score=0.7,
        claim_binding=read.EvidenceClaimBinding(
            subject_id="company:g1-feixiang",
            predicate="profile",
            value="深圳市飞象工业科技有限公司",
        ),
    )


def _handle(read: Any) -> Any:
    return read.CanonicalEntityHandle(
        canonical_id="company:g1-feixiang",
        domain="company",
        display_name="深圳市飞象工业科技有限公司",
        evidence_ids=("evidence:g1:company-local",),
    )


def _turn(answer: Any, *, query: str, evidence_set: Any) -> Any:
    return answer.TurnRequest(
        session_id="session:g1:floor",
        turn_id="turn:g1:floor:1",
        query=query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
    )


def _evidence_set(read: Any, *, query: str, items: tuple, handles: tuple) -> Any:
    return read.EvidenceSet(
        release_id="candidate-g1-r1",
        original_query=query,
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        entity_handles=handles,
    )


def _named_query() -> str:
    return "深圳市飞象工业科技有限公司"


def test_named_query_keeps_local_claim_without_binding() -> None:
    serving = _serving_module()
    read = _read_module()
    answer = _answer_module()
    item = _local_item(read, binding=None)
    evidence_set = _evidence_set(
        read,
        query=_named_query(),
        items=(item, _web_item(read)),
        handles=(_handle(read),),
    )
    proposal = serving._answer_selector(bundle=_bundle(serving))(
        _turn(answer, query=_named_query(), evidence_set=evidence_set)
    )
    local_ids = {item.evidence_id}
    local_claims = [
        claim for claim in proposal.claims if local_ids & set(claim.evidence_ids)
    ]
    assert local_claims, (
        "a query naming a canonical entity with a retained local item must "
        "keep at least one local claim even without a field claim_binding"
    )


def test_floor_does_not_duplicate_when_binding_exists() -> None:
    serving = _serving_module()
    read = _read_module()
    answer = _answer_module()
    bound = read.EvidenceClaimBinding(
        subject_id="company:g1-feixiang",
        predicate="business",
        value="工业科技产品研发",
    )
    item = _local_item(read, binding=bound)
    evidence_set = _evidence_set(
        read,
        query=_named_query(),
        items=(item,),
        handles=(_handle(read),),
    )
    proposal = serving._answer_selector(bundle=_bundle(serving))(
        _turn(answer, query=_named_query(), evidence_set=evidence_set)
    )
    local_claims = [
        claim
        for claim in proposal.claims
        if "evidence:g1:company-local" in claim.evidence_ids
    ]
    assert len(local_claims) == 1


def test_floor_silent_for_unnamed_topic_query() -> None:
    serving = _serving_module()
    read = _read_module()
    answer = _answer_module()
    item = _local_item(read, binding=None)
    query = "深圳做工业自动化的公司有哪些"
    evidence_set = _evidence_set(
        read,
        query=query,
        items=(item,),
        handles=(_handle(read),),
    )
    proposal = serving._answer_selector(bundle=_bundle(serving))(
        _turn(answer, query=query, evidence_set=evidence_set)
    )
    local_claims = [
        claim
        for claim in proposal.claims
        if "evidence:g1:company-local" in claim.evidence_ids
    ]
    assert not local_claims
