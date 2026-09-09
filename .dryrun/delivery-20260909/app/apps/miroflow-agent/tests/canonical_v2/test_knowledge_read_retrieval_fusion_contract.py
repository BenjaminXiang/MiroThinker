from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module
from threading import Barrier
from typing import Any

TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
RELEASE_ID = "candidate-r1"
NOW = datetime(2026, 7, 15, 7, 0, tzinfo=UTC)
PUBLIC_DOMAINS = ("professor", "company", "paper", "patent")


class _MissingKnowledgeReadModule(RuntimeError):
    """Exact S8RF target sentinel; nested missing dependencies remain real."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingKnowledgeReadModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _web_policy(module: Any, mode: str = "universal") -> Any:
    if mode == "disabled":
        return module.WebSearchPolicy(mode=mode)
    return module.WebSearchPolicy(
        mode=mode,
        max_provider_calls=1,
        timeout_ms=1_500,
        max_results=8,
        allowed_domains=(),
    )


def _slot(module: Any, *, kind: str, value: str) -> Any:
    return module.ProtectedSlot(kind=kind, value=value)


def _plan(
    module: Any,
    *,
    token: str,
    query: str,
    lanes: tuple[str, ...],
    protected_slots: tuple[Any, ...] = (),
    interaction_mode: str = "information_retrieval",
    retained_web_handles: tuple[Any, ...] = (),
    web_handle_replays: tuple[Any, ...] = (),
    handle_operation: str | None = None,
    session_id: str | None = None,
) -> Any:
    return module.RetrievalPlan(
        plan_id=f"retrieval-plan:{token}",
        plan_version="retrieval-plan-v1",
        original_query=query,
        behavior_class="E",
        interaction_mode=interaction_mode,
        release_id=RELEASE_ID,
        domains=PUBLIC_DOMAINS,
        protected_slots=protected_slots,
        lanes=lanes,
        max_candidates=24,
        web_required="web" in lanes,
        web_policy=_web_policy(
            module,
            "universal" if "web" in lanes else "disabled",
        ),
        freshness_material="web" in lanes,
        retained_web_handles=retained_web_handles,
        web_handle_replays=web_handle_replays,
        handle_operation=handle_operation,
        session_id=session_id,
    )


def _snapshot(module: Any, *, token: str, payload: bytes) -> Any:
    content_sha256 = hashlib.sha256(payload).hexdigest()
    return module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:{token}:sha256:{content_sha256}",
        content_sha256=content_sha256,
        retrieved_at=NOW,
        byte_length=len(payload),
    )


def _item(
    module: Any,
    *,
    evidence_id: str,
    object_id: str,
    domain: str,
    lane: str,
    predicate: str,
    value: str,
    source_nature: str = "local",
    source_locator: str | None = None,
    score: float = 0.8,
    web_snapshot: Any | None = None,
) -> Any:
    return module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=object_id,
        domain=domain,
        lane=lane,
        source_nature=source_nature,
        source_locator=source_locator or f"artifact:s8rf#{evidence_id}",
        snippet=f"Recorded fixture evidence for {predicate}={value}.",
        score=score,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=object_id,
            predicate=predicate,
            value=value,
        ),
        web_snapshot=web_snapshot,
    )


def _candidate(
    module: Any,
    *,
    token: str,
    display_name: str,
    domain: str,
    lane: str,
    evidence: tuple[Any, ...],
    canonical_id: str | None = None,
    identity_kind: str = "canonical",
    reference_type: str | None = None,
    resolution_state: str = "resolved",
    relationship_state: str | None = None,
    origin_public_evidence_ids: tuple[str, ...] = (),
    raw_score: float = 0.8,
    quality_flags: tuple[str, ...] = (),
) -> Any:
    return module.RecallCandidate(
        raw_candidate_id=f"raw-candidate:{token}",
        display_name=display_name,
        domain=domain,
        identity_kind=identity_kind,
        canonical_id=canonical_id,
        reference_type=reference_type,
        resolution_state=resolution_state,
        relationship_state=relationship_state,
        origin_public_evidence_ids=origin_public_evidence_ids,
        query_view="view:original",
        lane=lane,
        attempt=1,
        release_id=RELEASE_ID,
        adapter_version=f"recorded-{lane}-adapter-v1",
        provider_version=("recorded-web-v1" if lane == "web" else None),
        raw_score=raw_score,
        quality_flags=quality_flags,
        evidence=evidence,
    )


def _lane_result(module: Any, candidates: tuple[Any, ...]) -> Any:
    return module.RetrievalLaneResult(candidates=candidates)


def _handle_id(handle: Any) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def test_independent_seven_lane_recall_overlaps_and_retains_full_candidate_trace() -> (
    None
):
    module = _module()
    lanes = (
        "exact",
        "structured",
        "lexical",
        "vector",
        "relationship",
        "internal_reference",
        "web",
    )
    overlap = Barrier(2)
    seen: list[str] = []
    person_origin = (
        "evidence:professor-profile",
        "evidence:company-personnel",
        "evidence:paper-author",
    )
    person_origin_objects = {
        "evidence:professor-profile": ("professor:chen", "professor"),
        "evidence:company-personnel": ("company:star-sea", "company"),
        "evidence:paper-author": ("paper:person-origin", "paper"),
    }
    candidates_by_lane = {
        "exact": (
            _candidate(
                module,
                token="exact-company",
                display_name="星海机器人",
                domain="company",
                lane="exact",
                canonical_id="company:star-sea",
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:exact-company",
                        object_id="company:star-sea",
                        domain="company",
                        lane="exact",
                        predicate="display_name",
                        value="星海机器人",
                        score=1.0,
                    ),
                ),
                raw_score=1.0,
            ),
        ),
        "structured": (
            _candidate(
                module,
                token="structured-patent",
                display_name="CN117873146A",
                domain="patent",
                lane="structured",
                canonical_id="patent:CN117873146A",
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:structured-patent",
                        object_id="patent:CN117873146A",
                        domain="patent",
                        lane="structured",
                        predicate="patent_number",
                        value="CN117873146A",
                    ),
                ),
            ),
        ),
        "lexical": (
            _candidate(
                module,
                token="lexical-paper",
                display_name="Rare Visual Servoing Phrase",
                domain="paper",
                lane="lexical",
                canonical_id="paper:rare-phrase",
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:lexical-paper",
                        object_id="paper:rare-phrase",
                        domain="paper",
                        lane="lexical",
                        predicate="title",
                        value="Rare Visual Servoing Phrase",
                    ),
                ),
            ),
        ),
        "vector": (
            _candidate(
                module,
                token="vector-paper",
                display_name="Broad Robot Control Study",
                domain="paper",
                lane="vector",
                canonical_id="paper:broad-control",
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:vector-paper",
                        object_id="paper:broad-control",
                        domain="paper",
                        lane="vector",
                        predicate="topic",
                        value="robot control",
                    ),
                ),
            ),
        ),
        "relationship": (
            _candidate(
                module,
                token="technology-discussion",
                display_name="Route discussion at 星海机器人",
                domain="company",
                lane="relationship",
                canonical_id="company:star-sea",
                reference_type="technology_route",
                relationship_state="discussion_or_mention",
                origin_public_evidence_ids=("evidence:company-route-discussion",),
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:company-route-discussion",
                        object_id="company:star-sea",
                        domain="company",
                        lane="relationship",
                        predicate="technology_relationship_state",
                        value="discussion_or_mention",
                    ),
                ),
            ),
            _candidate(
                module,
                token="technology-demonstrated",
                display_name="Route demonstrated by Example Patent",
                domain="patent",
                lane="relationship",
                canonical_id="patent:route-demonstration",
                reference_type="technology_route",
                relationship_state="demonstrated_use",
                origin_public_evidence_ids=("evidence:patent-route-demonstrated",),
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:patent-route-demonstrated",
                        object_id="patent:route-demonstration",
                        domain="patent",
                        lane="relationship",
                        predicate="technology_relationship_state",
                        value="demonstrated_use",
                    ),
                ),
            ),
        ),
        "internal_reference": (
            _candidate(
                module,
                token="person-resolved-founder",
                display_name="陈教授",
                domain="professor",
                lane="internal_reference",
                canonical_id="professor:chen",
                reference_type="person",
                origin_public_evidence_ids=person_origin,
                evidence=tuple(
                    _item(
                        module,
                        evidence_id=evidence_id,
                        object_id=person_origin_objects[evidence_id][0],
                        domain=person_origin_objects[evidence_id][1],
                        lane="internal_reference",
                        predicate="person_origin",
                        value=evidence_id,
                    )
                    for evidence_id in person_origin
                ),
            ),
            _candidate(
                module,
                token="person-unresolved-same-name",
                display_name="陈教授",
                domain="paper",
                lane="internal_reference",
                identity_kind="internal_reference",
                reference_type="person",
                resolution_state="unresolved",
                origin_public_evidence_ids=("evidence:paper-author-unresolved",),
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:paper-author-unresolved",
                        object_id="paper:unresolved-author",
                        domain="paper",
                        lane="internal_reference",
                        predicate="author_display_name",
                        value="陈教授",
                    ),
                ),
            ),
        ),
        "web": (
            _candidate(
                module,
                token="web-company",
                display_name="Star Sea Robotics",
                domain="company",
                lane="web",
                canonical_id="company:star-sea",
                identity_kind="web_candidate",
                evidence=(
                    _item(
                        module,
                        evidence_id="evidence:web-company",
                        object_id="web-object:star-sea",
                        domain="company",
                        lane="web",
                        predicate="display_name",
                        value="Star Sea Robotics",
                        source_nature="current_web",
                        source_locator="https://current.example/star-sea",
                        web_snapshot=_snapshot(
                            module,
                            token="star-sea",
                            payload=b"Recorded Star Sea Robotics Web profile.",
                        ),
                    ),
                ),
            ),
        ),
    }

    def adapter_for(lane: str) -> Any:
        def adapter(request: Any) -> Any:
            assert request.lane == lane
            assert request.release_id == RELEASE_ID
            assert request.query_view == "view:original"
            seen.append(lane)
            if lane in {"exact", "web"}:
                overlap.wait(timeout=5)
            return _lane_result(module, candidates_by_lane[lane])

        return adapter

    read = module.create_ephemeral_knowledge_read(
        lane_adapters={lane: adapter_for(lane) for lane in lanes},
        universal_web_policy=_web_policy(module),
    )
    plan = _plan(
        module,
        token="all-lanes",
        query="查找深圳机器人路线的公司、教授、论文和专利，并补充当前 Web 证据",
        lanes=lanes,
    )

    result = read.execute(plan)

    assert isinstance(result, module.EvidenceSet)
    assert set(seen) == set(lanes)
    expected_candidates = tuple(
        candidate for lane in lanes for candidate in candidates_by_lane[lane]
    )
    traces = {trace.raw_candidate_id: trace for trace in result.candidate_traces}
    assert set(traces) == {
        candidate.raw_candidate_id for candidate in expected_candidates
    }
    for candidate in expected_candidates:
        trace = traces[candidate.raw_candidate_id]
        assert trace.query_view == candidate.query_view
        assert trace.lane == candidate.lane
        assert trace.attempt == candidate.attempt
        assert trace.release_id == candidate.release_id
        assert trace.adapter_version == candidate.adapter_version
        assert trace.provider_version == candidate.provider_version
        assert trace.raw_score == candidate.raw_score
        assert trace.evidence_ids == tuple(
            item.evidence_id for item in candidate.evidence
        )
        assert trace.disposition

    unresolved = traces["raw-candidate:person-unresolved-same-name"]
    assert unresolved.disposition == "unresolved_reference"
    assert unresolved.selected_result_id is None
    auxiliary = {item.raw_candidate_id: item for item in result.auxiliary_traces}
    assert auxiliary["raw-candidate:person-resolved-founder"].reference_type == (
        "person"
    )
    assert (
        auxiliary["raw-candidate:person-resolved-founder"].origin_public_evidence_ids
        == person_origin
    )
    assert auxiliary["raw-candidate:person-resolved-founder"].public_population is False
    assert auxiliary["raw-candidate:person-unresolved-same-name"].eligible is False
    assert tuple(
        auxiliary[token].relationship_state
        for token in (
            "raw-candidate:technology-discussion",
            "raw-candidate:technology-demonstrated",
        )
    ) == ("discussion_or_mention", "demonstrated_use")
    assert tuple(
        auxiliary[token].origin_public_evidence_ids
        for token in (
            "raw-candidate:technology-discussion",
            "raw-candidate:technology-demonstrated",
        )
    ) == (
        ("evidence:company-route-discussion",),
        ("evidence:patent-route-demonstrated",),
    )
    assert all(
        auxiliary[token].public_population is False
        for token in (
            "raw-candidate:technology-discussion",
            "raw-candidate:technology-demonstrated",
        )
    )
    assert all(item.domain in PUBLIC_DOMAINS for item in result.items)
    serialized = repr(result.model_dump(mode="json"))
    assert "product_has_capability" not in serialized
    assert "public_person_population" not in serialized


def _fusion_candidates(module: Any) -> dict[str, tuple[Any, ...]]:
    local_alpha = _candidate(
        module,
        token="alpha-local",
        display_name="星海机器人",
        domain="company",
        lane="exact",
        canonical_id="company:alpha",
        evidence=(
            _item(
                module,
                evidence_id="evidence:alpha-local-name",
                object_id="company:alpha",
                domain="company",
                lane="exact",
                predicate="display_name",
                value="星海机器人",
                score=1.0,
            ),
        ),
        raw_score=1.0,
    )
    web_alpha = _candidate(
        module,
        token="alpha-web-alias",
        display_name="Star Sea Robotics Ltd.",
        domain="company",
        lane="web",
        canonical_id="company:alpha",
        identity_kind="web_candidate",
        evidence=(
            _item(
                module,
                evidence_id="evidence:alpha-web-geography",
                object_id="web-object:alpha",
                domain="company",
                lane="web",
                predicate="geography",
                value="深圳",
                source_nature="current_web",
                source_locator="https://current.example/alpha",
                web_snapshot=_snapshot(
                    module,
                    token="alpha-geography",
                    payload=b"Star Sea Robotics Ltd. is located in Shenzhen.",
                ),
            ),
        ),
        raw_score=0.7,
    )
    beta = _candidate(
        module,
        token="beta-incomplete",
        display_name="Beta Robotics",
        domain="company",
        lane="vector",
        canonical_id="company:beta",
        quality_flags=("missing_optional_summary",),
        evidence=(
            _item(
                module,
                evidence_id="evidence:beta-geography",
                object_id="company:beta",
                domain="company",
                lane="vector",
                predicate="geography",
                value="深圳",
                score=0.65,
            ),
        ),
        raw_score=0.65,
    )
    same_name_other = _candidate(
        module,
        token="same-name-other-id",
        display_name="星海机器人",
        domain="company",
        lane="vector",
        canonical_id="company:alpha-other",
        evidence=(
            _item(
                module,
                evidence_id="evidence:same-name-other-id",
                object_id="company:alpha-other",
                domain="company",
                lane="vector",
                predicate="geography",
                value="深圳",
                score=0.6,
            ),
        ),
        raw_score=0.6,
    )
    outside = _candidate(
        module,
        token="outside-high-score",
        display_name="Outside Robotics",
        domain="company",
        lane="relationship",
        canonical_id="company:outside",
        evidence=(
            _item(
                module,
                evidence_id="evidence:outside-geography",
                object_id="company:outside",
                domain="company",
                lane="relationship",
                predicate="geography",
                value="广州",
                score=0.99,
            ),
        ),
        raw_score=0.99,
    )
    return {
        "exact": (local_alpha,),
        "vector": (beta, same_name_other),
        "relationship": (outside,),
        "web": (web_alpha,),
    }


def test_identity_fusion_aggregates_before_constraints_and_validates_late_rerank() -> (
    None
):
    module = _module()
    candidates = _fusion_candidates(module)
    plan = _plan(
        module,
        token="late-fusion",
        query="列出深圳的机器人公司",
        lanes=tuple(candidates),
        protected_slots=(_slot(module, kind="geography", value="深圳"),),
    )

    def lane_adapter(request: Any) -> Any:
        return _lane_result(module, candidates[request.lane])

    def identity_fuser(request: Any) -> Any:
        assert set(request.raw_candidate_ids) == {
            candidate.raw_candidate_id
            for lane_candidates in candidates.values()
            for candidate in lane_candidates
        }
        return module.IdentityFusionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="identity-fusion-v1",
            model_id="recorded-identity-fuser",
            prompt_version="identity-fusion-prompt-v1",
            groups=(
                module.IdentityFusionGroup(
                    canonical_id="company:alpha",
                    raw_candidate_ids=(
                        "raw-candidate:alpha-local",
                        "raw-candidate:alpha-web-alias",
                    ),
                    evidence_ids=(
                        "evidence:alpha-local-name",
                        "evidence:alpha-web-geography",
                    ),
                    confidence=0.95,
                    rationale="The accepted alias evidence binds one Company identity.",
                ),
                module.IdentityFusionGroup(
                    canonical_id="company:beta",
                    raw_candidate_ids=("raw-candidate:beta-incomplete",),
                    evidence_ids=("evidence:beta-geography",),
                    confidence=1.0,
                    rationale="The local candidate already has an accepted Canonical ID.",
                ),
                module.IdentityFusionGroup(
                    canonical_id="company:alpha-other",
                    raw_candidate_ids=("raw-candidate:same-name-other-id",),
                    evidence_ids=("evidence:same-name-other-id",),
                    confidence=1.0,
                    rationale=(
                        "A different accepted Canonical ID stays separate despite the "
                        "same display name."
                    ),
                ),
                module.IdentityFusionGroup(
                    canonical_id="company:outside",
                    raw_candidate_ids=("raw-candidate:outside-high-score",),
                    evidence_ids=("evidence:outside-geography",),
                    confidence=1.0,
                    rationale="The local candidate already has an accepted Canonical ID.",
                ),
            ),
        )

    valid_rerank_input_sha256: list[str] = []

    def valid_reranker(request: Any) -> Any:
        valid_rerank_input_sha256.append(request.content_sha256)
        result_ids = {
            candidate.canonical_id: candidate.result_id
            for candidate in request.eligible_candidates
        }
        assert set(result_ids) == {
            "company:alpha",
            "company:alpha-other",
            "company:beta",
        }
        eligible = {
            candidate.canonical_id: candidate
            for candidate in request.eligible_candidates
        }
        assert set(eligible["company:alpha"].evidence_ids) == {
            "evidence:alpha-local-name",
            "evidence:alpha-web-geography",
        }
        assert eligible["company:beta"].quality_flags == ("missing_optional_summary",)
        return module.RerankProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=(
                result_ids["company:beta"],
                result_ids["company:alpha"],
                result_ids["company:alpha-other"],
            ),
            rationale="Both eligible Companies answer the protected Shenzhen query.",
        )

    def execute(reranker: Any, *, fuser: Any = identity_fuser) -> Any:
        return module.create_ephemeral_knowledge_read(
            lane_adapters={lane: lane_adapter for lane in candidates},
            identity_fuser=fuser,
            reranker=reranker,
            universal_web_policy=_web_policy(module),
        ).execute(plan)

    ranked = execute(valid_reranker)

    assert tuple(_handle_id(handle) for handle in ranked.entity_handles) == (
        "company:beta",
        "company:alpha",
        "company:alpha-other",
    )
    alpha_handle = next(
        handle
        for handle in ranked.entity_handles
        if _handle_id(handle) == "company:alpha"
    )
    assert set(alpha_handle.evidence_ids) == {
        "evidence:alpha-local-name",
        "evidence:alpha-web-geography",
    }
    assert (
        len(
            [
                handle
                for handle in ranked.entity_handles
                if _handle_id(handle) == "company:alpha"
            ]
        )
        == 1
    )
    assert {
        _handle_id(handle)
        for handle in ranked.entity_handles
        if handle.display_name == "星海机器人"
    } == {"company:alpha", "company:alpha-other"}
    assert ranked.rerank_receipt.mode == "recorded_structured"
    assert ranked.rerank_receipt.decision_input_sha256 == (valid_rerank_input_sha256[0])
    traces = {trace.raw_candidate_id: trace for trace in ranked.candidate_traces}
    assert traces["raw-candidate:alpha-local"].selected_result_id == (
        traces["raw-candidate:alpha-web-alias"].selected_result_id
    )
    assert traces["raw-candidate:outside-high-score"].disposition == (
        "hard_constraint_rejected"
    )
    assert traces["raw-candidate:outside-high-score"].selected_result_id is None
    constraint_receipt = next(
        receipt
        for receipt in ranked.constraint_receipts
        if receipt.raw_candidate_ids == ("raw-candidate:outside-high-score",)
    )
    assert constraint_receipt.outcome == "rejected"
    assert tuple(
        (failure.slot_kind, failure.required_value, failure.observed_values)
        for failure in constraint_receipt.failed_slots
    ) == (("geography", "深圳", ("广州",)),)
    assert constraint_receipt.aggregated_evidence_ids == ("evidence:outside-geography",)
    assert traces["raw-candidate:beta-incomplete"].disposition == "selected"
    assert "missing_optional_summary" in next(
        item.quality_flags
        for item in ranked.fused_candidates
        if item.canonical_id == "company:beta"
    )

    def wrong_bound_reranker(request: Any) -> Any:
        return module.RerankProposal(
            decision_input_sha256="f" * 64,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=tuple(
                candidate.result_id for candidate in request.eligible_candidates
            ),
            rationale="This proposal is bound to the wrong input.",
        )

    def unknown_candidate_reranker(request: Any) -> Any:
        return module.RerankProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=(
                "fused-result:unknown",
                request.eligible_candidates[0].result_id,
            ),
            rationale="This proposal attempts to add an unknown candidate.",
        )

    def duplicate_candidate_reranker(request: Any) -> Any:
        first = request.eligible_candidates[0].result_id
        return module.RerankProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=(first, first),
            rationale="This proposal repeats one candidate and drops the others.",
        )

    def timed_out_reranker(_: Any) -> Any:
        raise TimeoutError("recorded reranker timeout")

    degraded = tuple(
        execute(provider)
        for provider in (
            wrong_bound_reranker,
            unknown_candidate_reranker,
            duplicate_candidate_reranker,
            timed_out_reranker,
        )
    )
    degraded_orders = tuple(
        tuple(_handle_id(handle) for handle in result.entity_handles)
        for result in degraded
    )
    assert len(set(degraded_orders)) == 1
    assert set(degraded_orders[0]) == {
        "company:alpha",
        "company:alpha-other",
        "company:beta",
    }
    assert all(
        result.rerank_receipt.mode == "deterministic_fallback" for result in degraded
    )
    assert tuple(result.rerank_receipt.degradation_reason for result in degraded) == (
        "input_binding_mismatch",
        "unknown_candidate",
        "duplicate_candidate",
        "timeout",
    )
    assert all(
        "company:outside"
        not in {_handle_id(handle) for handle in result.entity_handles}
        for result in degraded
    )
    assert all(
        {
            item.evidence_id
            for item in result.items
            if item.object_id in {"company:alpha", "web-object:alpha"}
        }
        == {"evidence:alpha-local-name", "evidence:alpha-web-geography"}
        for result in degraded
    )

    def hostile_name_merge_fuser(request: Any) -> Any:
        return module.IdentityFusionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="identity-fusion-v1",
            model_id="recorded-identity-fuser",
            prompt_version="identity-fusion-prompt-v1",
            groups=(
                module.IdentityFusionGroup(
                    canonical_id="company:alpha",
                    raw_candidate_ids=(
                        "raw-candidate:alpha-local",
                        "raw-candidate:alpha-web-alias",
                        "raw-candidate:same-name-other-id",
                    ),
                    evidence_ids=(
                        "evidence:alpha-local-name",
                        "evidence:alpha-web-geography",
                        "evidence:same-name-other-id",
                    ),
                    confidence=0.99,
                    rationale="The hostile proposal merges on display name alone.",
                ),
                module.IdentityFusionGroup(
                    canonical_id="company:beta",
                    raw_candidate_ids=("raw-candidate:beta-incomplete",),
                    evidence_ids=("evidence:beta-geography",),
                    confidence=1.0,
                    rationale="The local candidate has an accepted Canonical ID.",
                ),
                module.IdentityFusionGroup(
                    canonical_id="company:outside",
                    raw_candidate_ids=("raw-candidate:outside-high-score",),
                    evidence_ids=("evidence:outside-geography",),
                    confidence=1.0,
                    rationale="The local candidate has an accepted Canonical ID.",
                ),
            ),
        )

    hostile_merge = execute(
        timed_out_reranker,
        fuser=hostile_name_merge_fuser,
    )
    assert {_handle_id(handle) for handle in hostile_merge.entity_handles} == {
        "company:alpha",
        "company:alpha-other",
        "company:beta",
    }
    assert (
        next(
            trace
            for trace in hostile_merge.candidate_traces
            if trace.raw_candidate_id == "raw-candidate:alpha-local"
        ).selected_result_id
        != next(
            trace
            for trace in hostile_merge.candidate_traces
            if trace.raw_candidate_id == "raw-candidate:same-name-other-id"
        ).selected_result_id
    )
    assert hostile_merge.fusion_receipt.mode == "deterministic_fallback"
    assert hostile_merge.fusion_receipt.degradation_reason == (
        "conflicting_accepted_canonical_ids"
    )


def test_web_handles_bind_snapshot_collision_expiry_and_read_only_resolution() -> None:
    module = _module()
    shared_url = "https://current.example/directory/robotics"
    alpha_payload = b"Recorded profile for Web-only Alpha Robotics."
    beta_payload = b"Recorded profile for Web-only Beta Robotics."
    alpha_snapshot = _snapshot(module, token="web-alpha", payload=alpha_payload)
    beta_snapshot = _snapshot(module, token="web-beta", payload=beta_payload)
    web_candidates = (
        _candidate(
            module,
            token="web-only-alpha",
            display_name="Alpha Robotics",
            domain="company",
            lane="web",
            identity_kind="web_only",
            resolution_state="unresolved",
            evidence=(
                _item(
                    module,
                    evidence_id="evidence:web-only-alpha",
                    object_id="web-object:alpha",
                    domain="company",
                    lane="web",
                    predicate="display_identity",
                    value="Alpha Robotics",
                    source_nature="current_web",
                    source_locator=shared_url,
                    web_snapshot=alpha_snapshot,
                ),
            ),
        ),
        _candidate(
            module,
            token="web-only-beta",
            display_name="Beta Robotics",
            domain="company",
            lane="web",
            identity_kind="web_only",
            resolution_state="unresolved",
            evidence=(
                _item(
                    module,
                    evidence_id="evidence:web-only-beta",
                    object_id="web-object:beta",
                    domain="company",
                    lane="web",
                    predicate="display_identity",
                    value="Beta Robotics",
                    source_nature="current_web",
                    source_locator=shared_url,
                    web_snapshot=beta_snapshot,
                ),
            ),
        ),
    )

    def web_adapter(_: Any) -> Any:
        return _lane_result(module, web_candidates)

    read = module.create_ephemeral_knowledge_read(
        lane_adapters={"web": web_adapter},
        universal_web_policy=_web_policy(module),
        clock=lambda: NOW,
        web_handle_ttl=timedelta(hours=1),
    )
    initial_plan = _plan(
        module,
        token="web-handles",
        query="列出当前 Web 中的 Alpha Robotics 和 Beta Robotics",
        lanes=("web",),
        session_id="session:s8rf:web-handles",
    )

    initial = read.execute(initial_plan)

    handles = initial.entity_handles
    assert len(handles) == 2
    assert tuple(handle.kind for handle in handles) == ("web", "web")
    assert tuple(handle.domain for handle in handles) == ("company", "company")
    assert len({handle.handle_id for handle in handles}) == 2
    assert all(handle.handle_id != shared_url for handle in handles)
    assert tuple(handle.display_name for handle in handles) == (
        "Alpha Robotics",
        "Beta Robotics",
    )
    assert tuple(handle.evidence_snapshot_ids for handle in handles) == (
        (alpha_snapshot.snapshot_id,),
        (beta_snapshot.snapshot_id,),
    )
    assert all(handle.resolution_state == "unresolved" for handle in handles)
    assert all(
        handle.originating_query == initial_plan.original_query for handle in handles
    )
    assert all(handle.origin_lane == "web" for handle in handles)
    assert all(handle.origin_attempt == 1 for handle in handles)
    assert all(handle.session_id == "session:s8rf:web-handles" for handle in handles)
    assert all(handle.expires_at == NOW + timedelta(hours=1) for handle in handles)
    assert {item.source_locator for item in initial.items} == {shared_url}
    assert alpha_snapshot.content_sha256 == hashlib.sha256(alpha_payload).hexdigest()
    assert alpha_snapshot.byte_length == len(alpha_payload)
    assert beta_snapshot.content_sha256 == hashlib.sha256(beta_payload).hexdigest()
    assert beta_snapshot.byte_length == len(beta_payload)
    candidate_traces = {
        trace.raw_candidate_id: trace for trace in initial.candidate_traces
    }
    for candidate, handle in zip(web_candidates, handles, strict=True):
        trace = candidate_traces[candidate.raw_candidate_id]
        assert handle.evidence_ids == trace.evidence_ids
        assert trace.provider_version == "recorded-web-v1"
        assert trace.selected_result_id == handle.handle_id

    alpha_handle = handles[0]
    original_handle = alpha_handle.model_dump(mode="json")
    original_snapshots = (
        alpha_snapshot.model_dump(mode="json"),
        beta_snapshot.model_dump(mode="json"),
    )
    changed_payload = b"Changed live content for a different entity."
    tampered_replay = module.WebHandleReplay(
        handle=alpha_handle,
        snapshot_payloads=(
            module.WebSnapshotPayload(
                snapshot_id=alpha_snapshot.snapshot_id,
                content=changed_payload,
            ),
        ),
        observed_live_content_sha256=alpha_snapshot.content_sha256,
        replayed_at=NOW + timedelta(minutes=10),
    )
    tamper_plan = _plan(
        module,
        token="web-handle-tamper",
        query="继续查看 Alpha Robotics",
        lanes=(),
        interaction_mode="handle_replay",
        retained_web_handles=(alpha_handle,),
        web_handle_replays=(tampered_replay,),
        handle_operation="coreference",
        session_id="session:s8rf:web-handles",
    )
    tampered = read.execute(tamper_plan)
    assert tampered.entity_handles == (alpha_handle,)
    assert tampered.handle_replay_receipts[0].status == "snapshot_mismatch"
    assert tampered.handle_replay_receipts[0].accepted_snapshot_sha256 == (
        alpha_snapshot.content_sha256
    )
    assert tampered.handle_replay_receipts[0].observed_live_content_sha256 == (
        alpha_snapshot.content_sha256
    )
    assert tampered.handle_replay_receipts[0].continuity_established is False
    assert any(
        limitation.code == "web_snapshot_mismatch"
        for limitation in tampered.limitations
    )
    assert tampered.items == ()

    provider_changed_replay = module.WebHandleReplay(
        handle=alpha_handle,
        snapshot_payloads=(
            module.WebSnapshotPayload(
                snapshot_id=alpha_snapshot.snapshot_id,
                content=alpha_payload,
            ),
        ),
        observed_live_content_sha256=hashlib.sha256(changed_payload).hexdigest(),
        replayed_at=NOW + timedelta(minutes=11),
    )
    provider_changed_plan = _plan(
        module,
        token="web-provider-content-changed",
        query="继续查看 Alpha Robotics",
        lanes=(),
        interaction_mode="handle_replay",
        retained_web_handles=(alpha_handle,),
        web_handle_replays=(provider_changed_replay,),
        handle_operation="coreference",
        session_id="session:s8rf:web-handles",
    )
    provider_changed = read.execute(provider_changed_plan)
    assert provider_changed.entity_handles == (alpha_handle,)
    provider_receipt = provider_changed.handle_replay_receipts[0]
    assert provider_receipt.status == "provider_content_changed"
    assert provider_receipt.accepted_snapshot_sha256 == (alpha_snapshot.content_sha256)
    assert (
        provider_receipt.observed_live_content_sha256
        == hashlib.sha256(changed_payload).hexdigest()
    )
    assert provider_receipt.continuity_established is False
    assert any(
        limitation.code == "web_provider_content_changed"
        for limitation in provider_changed.limitations
    )
    assert provider_changed.items == ()

    valid_replay = module.WebHandleReplay(
        handle=alpha_handle,
        snapshot_payloads=(
            module.WebSnapshotPayload(
                snapshot_id=alpha_snapshot.snapshot_id,
                content=alpha_payload,
            ),
        ),
        observed_live_content_sha256=alpha_snapshot.content_sha256,
        replayed_at=NOW + timedelta(hours=2),
    )
    expired_read = module.create_ephemeral_knowledge_read(
        lane_adapters={},
        universal_web_policy=_web_policy(module),
        clock=lambda: NOW + timedelta(hours=2),
    )
    expired_plan = _plan(
        module,
        token="web-handle-expired",
        query="继续查看 Alpha Robotics",
        lanes=(),
        interaction_mode="handle_replay",
        retained_web_handles=(alpha_handle,),
        web_handle_replays=(valid_replay,),
        handle_operation="coreference",
        session_id="session:s8rf:web-handles",
    )
    expired = expired_read.execute(expired_plan)
    assert expired.handle_replay_receipts[0].status == "expired"
    assert expired.live_referent_handle_ids == ()
    assert any(
        limitation.code == "web_handle_expired" for limitation in expired.limitations
    )

    accepted_identity_mapping = {
        RELEASE_ID: {
            "company:alpha": ("evidence:canonical-alpha",),
        }
    }
    original_identity_mapping = {
        release_id: dict(candidates)
        for release_id, candidates in accepted_identity_mapping.items()
    }

    def accepted_identity_lookup(request: Any) -> Any:
        evidence_ids = accepted_identity_mapping.get(
            request.release_id,
            {},
        ).get(request.canonical_id)
        return module.AcceptedIdentityLookupResult(
            release_id=request.release_id,
            canonical_id=request.canonical_id,
            accepted=evidence_ids is not None,
            evidence_ids=evidence_ids or (),
        )

    def resolver(request: Any) -> Any:
        assert request.handle.handle_id == alpha_handle.handle_id
        assert request.accepted_release_id == RELEASE_ID
        assert request.evidence_snapshot_ids == (alpha_snapshot.snapshot_id,)
        assert accepted_identity_mapping[RELEASE_ID]["company:alpha"] == (
            "evidence:canonical-alpha",
        )
        return module.WebHandleResolutionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=alpha_handle.handle_id,
            accepted_release_id=RELEASE_ID,
            canonical_id="company:alpha",
            canonical_evidence_ids=("evidence:canonical-alpha",),
            retained_snapshot_ids=(alpha_snapshot.snapshot_id,),
            resolution_state="resolved",
            rationale="Accepted release evidence resolves the retained display identity.",
        )

    resolving_read = module.create_ephemeral_knowledge_read(
        lane_adapters={},
        universal_web_policy=_web_policy(module),
        web_handle_resolver=resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        clock=lambda: NOW + timedelta(minutes=20),
    )
    resolution_replay = module.WebHandleReplay(
        handle=alpha_handle,
        snapshot_payloads=(
            module.WebSnapshotPayload(
                snapshot_id=alpha_snapshot.snapshot_id,
                content=alpha_payload,
            ),
        ),
        observed_live_content_sha256=alpha_snapshot.content_sha256,
        replayed_at=NOW + timedelta(minutes=20),
    )
    resolution_plan = _plan(
        module,
        token="web-handle-resolution",
        query="尝试将 Alpha Robotics 只读解析到当前 release",
        lanes=(),
        interaction_mode="handle_replay",
        retained_web_handles=(alpha_handle,),
        web_handle_replays=(resolution_replay,),
        handle_operation="resolve_read_only",
        session_id="session:s8rf:web-handles",
    )
    resolved = resolving_read.execute(resolution_plan)
    resolved_handle = resolved.entity_handles[0]
    assert resolved_handle.handle_id == alpha_handle.handle_id
    assert resolved_handle.evidence_snapshot_ids == (alpha_snapshot.snapshot_id,)
    assert resolved_handle.resolution_state == "resolved"
    assert resolved_handle.candidate_canonical_ids == ("company:alpha",)
    receipt = resolved.handle_resolution_receipts[0]
    assert receipt.handle_id == alpha_handle.handle_id
    assert receipt.accepted_release_id == RELEASE_ID
    assert receipt.canonical_id == "company:alpha"
    assert receipt.retained_snapshot_ids == (alpha_snapshot.snapshot_id,)
    assert receipt.read_only is True
    assert receipt.canonical_mutation_count == 0
    assert receipt.index_mutation_count == 0
    assert receipt.source_mapping_mutation_count == 0
    assert alpha_handle.model_dump(mode="json") == original_handle
    assert (
        alpha_snapshot.model_dump(mode="json"),
        beta_snapshot.model_dump(mode="json"),
    ) == original_snapshots
    assert accepted_identity_mapping == original_identity_mapping

    def wrong_release_resolver(request: Any) -> Any:
        return module.WebHandleResolutionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=request.handle.handle_id,
            accepted_release_id="candidate-r2",
            canonical_id="company:alpha",
            canonical_evidence_ids=("evidence:canonical-alpha",),
            retained_snapshot_ids=request.evidence_snapshot_ids,
            resolution_state="resolved",
            rationale="This proposal is cross-wired to another release.",
        )

    cross_wired = module.create_ephemeral_knowledge_read(
        lane_adapters={},
        universal_web_policy=_web_policy(module),
        web_handle_resolver=wrong_release_resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        clock=lambda: NOW + timedelta(minutes=20),
    ).execute(resolution_plan)
    assert cross_wired.entity_handles == (alpha_handle,)
    assert cross_wired.handle_resolution_receipts[0].status == "rejected"
    assert cross_wired.handle_resolution_receipts[0].canonical_mutation_count == 0
    assert accepted_identity_mapping == original_identity_mapping
    assert alpha_handle.model_dump(mode="json") == original_handle
    assert any(
        limitation.code == "web_handle_resolution_cross_wired"
        for limitation in cross_wired.limitations
    )

    def invented_identity_resolver(request: Any) -> Any:
        return module.WebHandleResolutionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=request.handle.handle_id,
            accepted_release_id=RELEASE_ID,
            canonical_id="company:invented",
            canonical_evidence_ids=("evidence:invented",),
            retained_snapshot_ids=request.evidence_snapshot_ids,
            resolution_state="resolved",
            rationale="This same-release proposal invents an unaccepted identity.",
        )

    def wrong_evidence_resolver(request: Any) -> Any:
        return module.WebHandleResolutionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=request.handle.handle_id,
            accepted_release_id=RELEASE_ID,
            canonical_id="company:alpha",
            canonical_evidence_ids=("evidence:wrong",),
            retained_snapshot_ids=request.evidence_snapshot_ids,
            resolution_state="resolved",
            rationale="This proposal cross-wires evidence for an accepted identity.",
        )

    for hostile_resolver, reason_code in (
        (invented_identity_resolver, "unaccepted_canonical_identity"),
        (wrong_evidence_resolver, "canonical_evidence_mismatch"),
    ):
        rejected = module.create_ephemeral_knowledge_read(
            lane_adapters={},
            universal_web_policy=_web_policy(module),
            web_handle_resolver=hostile_resolver,
            accepted_identity_lookup=accepted_identity_lookup,
            clock=lambda: NOW + timedelta(minutes=20),
        ).execute(resolution_plan)
        assert rejected.entity_handles == (alpha_handle,)
        hostile_receipt = rejected.handle_resolution_receipts[0]
        assert hostile_receipt.status == "rejected"
        assert hostile_receipt.reason_code == reason_code
        assert hostile_receipt.canonical_mutation_count == 0
        assert hostile_receipt.index_mutation_count == 0
        assert hostile_receipt.source_mapping_mutation_count == 0
        assert accepted_identity_mapping == original_identity_mapping
        assert alpha_handle.model_dump(mode="json") == original_handle
