from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module
import math
from typing import Any

import pytest

TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
RELEASE_ID = "candidate-r1"
NOW = datetime(2026, 7, 15, 7, 45, tzinfo=UTC)


class _MissingKnowledgeReadModule(RuntimeError):
    """Exact S8RG target sentinel; nested missing dependencies remain real."""


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


def _web_policy(module: Any, mode: str) -> Any:
    if mode == "disabled":
        return module.WebSearchPolicy(mode=mode)
    return module.WebSearchPolicy(
        mode=mode,
        max_provider_calls=1,
        timeout_ms=1_500,
        max_results=5,
        allowed_domains=(),
    )


def _item(
    module: Any,
    *,
    evidence_id: str,
    object_id: str,
    lane: str,
    value: str,
    domain: str = "company",
    predicate: str = "display_name",
    source_nature: str = "local",
    source_authority: str = "other",
    source_locator: str | None = None,
    snapshot: Any | None = None,
) -> Any:
    return module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=object_id,
        domain=domain,
        lane=lane,
        source_nature=source_nature,
        source_authority=source_authority,
        source_locator=source_locator or f"artifact:s8rg#{evidence_id}",
        snippet=f"Recorded evidence for {value}.",
        score=0.8,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=object_id,
            predicate=predicate,
            value=value,
        ),
        web_snapshot=snapshot,
    )


def _candidate(
    module: Any,
    *,
    token: str,
    canonical_id: str | None,
    display_name: str,
    lane: str,
    evidence: tuple[Any, ...],
    domain: str = "company",
    identity_kind: str = "canonical",
) -> Any:
    return module.RecallCandidate(
        raw_candidate_id=f"raw-candidate:{token}",
        display_name=display_name,
        domain=domain,
        identity_kind=identity_kind,
        canonical_id=canonical_id,
        resolution_state=("resolved" if canonical_id else "unresolved"),
        query_view="view:original",
        lane=lane,
        attempt=1,
        release_id=RELEASE_ID,
        adapter_version=f"recorded-{lane}-adapter-v1",
        provider_version=("recorded-web-v1" if lane == "web" else None),
        raw_score=0.8,
        evidence=evidence,
    )


def _ambiguity_decision(module: Any, *, mode: str) -> Any:
    policy = module.AmbiguityPolicy(
        policy_id="ambiguity-policy:synthetic-handoff",
        policy_version="fixture-only-not-calibrated:handoff-v1",
        entity_type="company",
        minimum_evidence_count=1,
        confidence_threshold=0.5,
        minimum_lead_margin=(0.2 if mode == "blocking" else 0.1),
    )
    selected_trace = module.AmbiguityCandidateTrace(
        candidate_id="candidate:alpha",
        canonical_id="company:alpha",
        display_name="Alpha Robotics",
        candidate_sha256="a" * 64,
        evidence_ids=("evidence:alpha",),
        evidence_count=1,
        evidence_confidence=0.9,
        model_confidence=0.99,
        protected_constraint_conflicts=(),
        eligible=True,
        rejection_reason=None,
        discriminators=(),
    )
    alternative_trace = module.AmbiguityCandidateTrace(
        candidate_id="candidate:beta",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        candidate_sha256="b" * 64,
        evidence_ids=("evidence:beta",),
        evidence_count=1,
        evidence_confidence=0.75,
        model_confidence=0.999,
        protected_constraint_conflicts=(),
        eligible=True,
        rejection_reason=None,
        discriminators=(),
    )
    return module.AmbiguityDecision(
        mode=mode,
        selected_canonical_id=("company:alpha" if mode == "non_blocking" else None),
        reason_code=(
            "dominant_candidate" if mode == "non_blocking" else "multiple_candidates"
        ),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_sha256=policy.content_sha256,
        request_sha256="c" * 64,
        candidate_manifest_sha256="d" * 64,
        candidate_traces=(selected_trace, alternative_trace),
        qualifying_candidate_ids=(
            ("candidate:alpha",)
            if mode == "non_blocking"
            else ("candidate:alpha", "candidate:beta")
        ),
        viable_alternative_ids=(("candidate:beta",) if mode == "non_blocking" else ()),
        observed_lead_margin=0.15,
    )


def _plan(
    module: Any,
    *,
    token: str,
    interaction_mode: str,
    lanes: tuple[str, ...],
    decision: Any | None = None,
    session_id: str | None = None,
) -> Any:
    return module.RetrievalPlan(
        plan_id=f"retrieval-plan:{token}",
        plan_version="retrieval-plan-v1",
        original_query=f"synthetic query:{token}",
        behavior_class="G",
        interaction_mode=interaction_mode,
        release_id=RELEASE_ID,
        domains=("company",) if lanes else (),
        protected_slots=(),
        lanes=lanes,
        max_candidates=10,
        web_required="web" in lanes,
        web_policy=_web_policy(
            module,
            "universal" if "web" in lanes else "disabled",
        ),
        freshness_material="web" in lanes,
        ambiguity_decision=decision,
        session_id=session_id,
    )


def test_ambiguity_decision_handoff_blocks_or_preserves_selected_identity() -> None:
    module = _module()
    planning_policy = module.QueryPlanningPolicy(
        policy_id="query-planning-policy:s8rg-boundaries",
        policy_version="fixture-only-v1",
        public_domains=("professor", "company", "paper", "patent"),
        supported_lanes=("exact", "internal_reference", "web"),
        supported_relationship_paths=(),
        max_candidates=10,
        max_provider_calls=1,
        max_planning_attempts=1,
    )
    institution_catalog = module.InstitutionCatalog(
        catalog_id="institution-catalog:s8rg-empty",
        catalog_version="fixture-only-v1",
        release_id=RELEASE_ID,
        entries=(),
    )

    def planning_request(
        token: str,
        query: str,
        *,
        ambiguity_candidates: tuple[Any, ...] = (),
        enumeration_context: Any | None = None,
    ) -> Any:
        return module.QueryPlanningRequest(
            request_id=f"query-request:{token}",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
            ambiguity_candidates=ambiguity_candidates,
            enumeration_context=enumeration_context,
        )

    def proposal(
        request: Any,
        token: str,
        *,
        lanes: tuple[str, ...] = ("exact", "web"),
        enumeration_mode: str | None = None,
        internal_reference_targets: tuple[str, ...] = (),
    ) -> Any:
        return module.RecordedPlanningProposal(
            proposal_id=f"planning-proposal:{token}",
            request_sha256=request.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-s8rg-planner",
            prompt_version="query-plan-prompt-v1",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=lanes,
            max_candidates=10,
            max_provider_calls=1,
            enumeration_mode=enumeration_mode,
            internal_reference_targets=internal_reference_targets,
        )

    threshold_lead = module.AmbiguityCandidate(
        candidate_id="candidate:threshold-lead",
        entity_type="company",
        canonical_id="company:threshold-lead",
        display_name="Threshold Robotics",
        evidence_ids=("evidence:threshold-lead",),
        evidence_confidence=0.76,
        model_confidence=0.99,
    )
    threshold_runner = module.AmbiguityCandidate(
        candidate_id="candidate:threshold-runner",
        entity_type="company",
        canonical_id="company:threshold-runner",
        display_name="Threshold Robotics",
        evidence_ids=("evidence:threshold-runner",),
        evidence_confidence=0.74,
        model_confidence=0.99,
    )
    threshold_request = planning_request(
        "ambiguity-threshold-straddle",
        "介绍 Threshold Robotics",
        ambiguity_candidates=(threshold_lead, threshold_runner),
    )
    threshold_plan = module.create_ephemeral_query_planner(
        planning_policy=planning_policy,
        institution_catalog=institution_catalog,
        proposal_provider=lambda value: proposal(
            value,
            "ambiguity-threshold-straddle",
        ),
        ambiguity_policy=module.AmbiguityPolicy(
            policy_id="ambiguity-policy:threshold-straddle",
            policy_version="fixture-only-v1",
            entity_type="company",
            minimum_evidence_count=1,
            confidence_threshold=0.75,
            minimum_lead_margin=0.15,
        ),
    ).plan(threshold_request)
    assert threshold_plan.ambiguity_decision.mode == "blocking"
    assert threshold_plan.ambiguity_decision.reason_code == "multiple_candidates"
    assert threshold_plan.ambiguity_decision.observed_lead_margin == pytest.approx(0.02)

    wrong_release_universe = module.FiniteEnumerationUniverse(
        universe_id="universe:wrong-release",
        release_id="candidate-r2",
        scope="wrong-release finite Company universe",
        member_ids=("company:alpha",),
        source_evidence_ids=("projection:wrong-release",),
        as_of=NOW,
    )
    enumeration_request = planning_request(
        "wrong-release-universe",
        "列出当前 release 的全部公司",
        enumeration_context=module.EnumerationPlanningContext(
            requested=True,
            scope=wrong_release_universe.scope,
            as_of=NOW,
            finite_universe=wrong_release_universe,
            required_member_ids=(),
        ),
    )
    with pytest.raises(module.InvalidRetrievalPlanError) as universe_error:
        module.create_ephemeral_query_planner(
            planning_policy=planning_policy,
            institution_catalog=institution_catalog,
            proposal_provider=lambda value: proposal(
                value,
                "wrong-release-universe",
                enumeration_mode="exhaustive_bounded",
            ),
        ).plan(enumeration_request)
    assert universe_error.value.reason_code == "enumeration_universe_release_mismatch"

    technology_request = planning_request(
        "wrong-release-technology",
        "比较仿真合成数据路线",
    )
    with pytest.raises(module.InvalidRetrievalPlanError) as technology_error:
        module.create_ephemeral_query_planner(
            planning_policy=planning_policy,
            institution_catalog=institution_catalog,
            proposal_provider=lambda value: proposal(
                value,
                "wrong-release-technology",
                lanes=("internal_reference", "web"),
                internal_reference_targets=("technology_route",),
            ),
            technology_routes=(
                module.TechnologyRouteRecord(
                    reference_id="technology-route:wrong-release",
                    release_id="candidate-r2",
                    canonical_route_id="technology-route:wrong-release",
                    canonical_name="仿真合成数据路线",
                    aliases=("仿真合成数据",),
                    definition_evidence_ids=("evidence:wrong-release",),
                ),
            ),
        ).plan(technology_request)
    assert technology_error.value.reason_code == "technology_route_release_mismatch"
    hostile_constructed_policy = module.AmbiguityPolicy.model_construct(
        policy_id="ambiguity-policy:hostile-construct",
        policy_version="fixture-only-v1",
        entity_type="company",
        minimum_evidence_count=-1,
        confidence_threshold=-1.0,
        minimum_lead_margin=-1.0,
        content_sha256="0" * 64,
    )
    with pytest.raises(ValueError):
        module.create_ephemeral_query_planner(
            planning_policy=planning_policy,
            institution_catalog=institution_catalog,
            proposal_provider=lambda value: proposal(
                value,
                "hostile-constructed-policy",
            ),
            ambiguity_policy=hostile_constructed_policy,
        )

    blocking_decision = _ambiguity_decision(module, mode="blocking")
    blocking_plan = _plan(
        module,
        token="blocking-ambiguity",
        interaction_mode="blocking_clarification",
        lanes=(),
        decision=blocking_decision,
    )

    def fail_on_lane(_: Any) -> Any:
        raise AssertionError("blocking ambiguity executed a retrieval lane")

    blocking_read = module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": fail_on_lane, "web": fail_on_lane},
        universal_web_policy=_web_policy(module, "universal"),
    )
    blocked = blocking_read.execute(blocking_plan)
    assert blocked.items == ()
    assert blocked.entity_handles == ()
    assert blocked.traces == ()
    assert blocked.candidate_traces == ()
    assert blocked.ambiguity_decision == blocking_decision
    assert blocked.ambiguity_decision.content_sha256 == (
        blocking_decision.content_sha256
    )

    selected_decision = _ambiguity_decision(module, mode="non_blocking")
    alpha = _candidate(
        module,
        token="alpha",
        canonical_id="company:alpha",
        display_name="Alpha Robotics",
        lane="exact",
        evidence=(
            _item(
                module,
                evidence_id="evidence:alpha",
                object_id="company:alpha",
                lane="exact",
                value="Alpha Robotics",
            ),
        ),
    )
    beta = _candidate(
        module,
        token="beta",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        lane="exact",
        evidence=(
            _item(
                module,
                evidence_id="evidence:beta",
                object_id="company:beta",
                lane="exact",
                value="Beta Robotics",
            ),
        ),
    )

    def exact_adapter(_: Any) -> Any:
        return module.RetrievalLaneResult(candidates=(beta, alpha))

    def empty_web(_: Any) -> Any:
        return module.RetrievalLaneResult(candidates=())

    selected_plan = _plan(
        module,
        token="selected-ambiguity",
        interaction_mode="information_retrieval",
        lanes=("exact", "web"),
        decision=selected_decision,
    )
    selected = module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": exact_adapter, "web": empty_web},
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(selected_plan)
    assert tuple(handle.canonical_id for handle in selected.entity_handles) == (
        "company:alpha",
    )
    assert tuple(item.object_id for item in selected.items) == ("company:alpha",)
    assert selected.ambiguity_decision == selected_decision
    assert selected.ambiguity_decision.selected_canonical_id == "company:alpha"
    assert selected.ambiguity_decision.viable_alternative_ids == ("candidate:beta",)
    traces = {trace.raw_candidate_id: trace for trace in selected.candidate_traces}
    assert traces["raw-candidate:alpha"].disposition == "selected"
    assert traces["raw-candidate:beta"].disposition == "ambiguity_alternative"
    assert traces["raw-candidate:beta"].selected_result_id is None

    canonical_handle = module.CanonicalEntityHandle(
        kind="canonical",
        canonical_id="company:alpha",
        domain="company",
        display_name="Alpha Robotics",
        evidence_ids=("evidence:alpha",),
    )
    successor_web_bytes = b"Recorded S9-shape Web handle evidence."
    successor_web_sha256 = hashlib.sha256(successor_web_bytes).hexdigest()
    successor_web_snapshot = module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:sha256:{successor_web_sha256}",
        content_sha256=successor_web_sha256,
        retrieved_at=NOW,
        byte_length=len(successor_web_bytes),
    )
    successor_web_handle = module.WebEntityHandle(
        kind="web",
        handle_id="web-handle:company-alpha",
        domain="company",
        display_name="Alpha Robotics (Web)",
        evidence_snapshot_ids=(successor_web_snapshot.snapshot_id,),
        evidence_ids=("evidence:alpha-web",),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query="successor result-shape smoke",
        origin_lane="web",
        origin_attempt=1,
    )
    successor_ambiguity_candidate = module.AmbiguityCandidate(
        handle_id="company:alpha",
        evidence_ids=("evidence:alpha",),
        discriminator="accepted Company identity",
        viable=True,
        protected_constraint_conflict=False,
    )
    successor_ambiguity = module.AmbiguityDecision(
        decision_id="ambiguity:successor-shape",
        policy_version="ambiguity-policy-v1",
        outcome="selected",
        candidates=(successor_ambiguity_candidate,),
        selected_handle_id="company:alpha",
        viable_alternative_handle_ids=(),
        decision_trace_id="trace:ambiguity:successor-shape",
    )
    coverage = module.EnumerationCoverage(
        mode="representative",
        scope="representative Shenzhen robotics Companies",
        as_of=NOW,
        checked_ids=("company:alpha",),
        eligible_ids=("company:alpha",),
        retrieved_ids=("company:alpha",),
        displayed_ids=("company:alpha",),
        omitted_ids=(),
        unknown_ids=(),
        unknown_scope=True,
        checked_count=1,
        eligible_count=1,
        retrieved_count=1,
        displayed_count=1,
        omitted_count=0,
        unknown_count=None,
        exhaustive=False,
        accounting_complete=True,
        required_member_outcomes=(),
        continuation_state="open_world",
        continuation_required=True,
    )
    traversal = module.TypedTraversalRequest(
        path_id="company_to_patent",
        source_domain="company",
        target_domain="patent",
        relationship_type="company_has_patent",
        direction="forward",
    )
    continuation = module.ContinuationCandidate(
        candidate_id="continuation:company-patents",
        reason="eligible_next_hop",
        label="查看该公司的专利",
        operation="traverse_relationship",
        target_kind="current_handle",
        target_handle_ids=("company:alpha",),
        constraint_pairs=(("geography", "深圳"),),
        relation_type="company_has_patent",
        coverage_state="open_world",
        evidence_ids=("evidence:alpha",),
        available=True,
    )
    continuation_without_coverage = module.ContinuationCandidate(
        candidate_id="continuation:company-details",
        reason="eligible_next_hop",
        label="查看该公司的详情",
        operation="inspect_current_handle",
        target_kind="current_handle",
        target_handle_ids=("company:alpha",),
        constraint_pairs=(("geography", "深圳"),),
        relation_type=None,
        coverage_state=None,
        evidence_ids=("evidence:alpha",),
        available=True,
    )
    assert continuation_without_coverage.coverage_state is None
    successor_web_item = _item(
        module,
        evidence_id="evidence:alpha-web",
        object_id="company:alpha",
        lane="web",
        value="Alpha Robotics",
        source_nature="current_web",
        source_locator="https://current.example/alpha",
        snapshot=successor_web_snapshot,
    )
    conflict = module.EvidenceConflict(
        conflict_id="conflict:alpha-current-role",
        subject_id="company:alpha",
        predicate="current_role",
        evidence_ids=("evidence:alpha", "evidence:alpha-web"),
        material=True,
        fusion_decision_id=None,
    )
    brief_intent = module.IndustryBriefIntent(
        release_id=RELEASE_ID,
        scope="Shenzhen robotics route landscape",
        as_of=NOW,
        route_ids=("technology-route:visual-servoing",),
        enumeration_mode="representative",
    )
    successor_material_part = module.MaterialQuestionPart(
        part_id="part:successor-company-identity",
        text="Confirm the selected Company identity.",
        subject_id="company:alpha",
        predicate="display_name",
        requested_value="Alpha Robotics",
        material=True,
    )
    successor_shape = module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query="successor result-shape smoke",
        protected_slots=(),
        items=(alpha.evidence[0], successor_web_item),
        traces=(),
        limitations=(),
        entity_handles=(canonical_handle, successor_web_handle),
        enumeration_coverage=coverage,
        requested_traversal=traversal,
        ambiguity_decision=successor_ambiguity,
        continuation_candidates=(continuation, continuation_without_coverage),
        material_conflicts=(conflict,),
        material_parts=(successor_material_part,),
        industry_brief_intent=brief_intent,
    )
    round_tripped_successor = module.EvidenceSet.model_validate(
        successor_shape.model_dump(mode="json")
    )
    assert round_tripped_successor == successor_shape
    assert round_tripped_successor.continuation_candidates[1].coverage_state is None
    with pytest.raises(ValueError):
        module.AmbiguityCandidate()
    with pytest.raises(ValueError):
        module.AmbiguityCandidate(
            candidate_id="candidate:mixed",
            entity_type="company",
            canonical_id="company:mixed",
            display_name="Mixed Robotics",
            evidence_ids=("evidence:mixed",),
            evidence_confidence=0.9,
            model_confidence=0.9,
            viable=True,
        )
    with pytest.raises(ValueError):
        module.AmbiguityDecision(policy_version="ambiguity-policy-v1")
    with pytest.raises(ValueError):
        module.AmbiguityDecision(
            decision_id="ambiguity:mixed",
            policy_version="ambiguity-policy-v1",
            outcome="selected",
            candidates=(successor_ambiguity_candidate,),
            selected_handle_id="company:alpha",
            decision_trace_id="trace:ambiguity:mixed",
            policy_sha256="e" * 64,
        )


def test_initial_web_snapshot_policy_recomputes_bytes_and_rejects_missing_oversize_or_tamper() -> (
    None
):
    module = _module()
    snapshot_policy = module.WebSnapshotPolicy(
        policy_id="web-snapshot-policy:synthetic-bounds",
        policy_version="fixture-only-v1",
        max_bytes=64,
    )
    valid_bytes = b"Bounded recorded Web profile for Alpha Robotics."
    oversize_bytes = b"x" * 65
    tampered_bytes = b"Different bytes under retained metadata."

    def snapshot(
        token: str,
        payload: bytes,
        *,
        digest: str | None = None,
        claimed_byte_length: int | None = None,
    ) -> Any:
        content_sha256 = digest or hashlib.sha256(payload).hexdigest()
        return module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:{token}:sha256:{content_sha256}",
            content_sha256=content_sha256,
            retrieved_at=NOW,
            byte_length=(
                len(payload) if claimed_byte_length is None else claimed_byte_length
            ),
        )

    valid_snapshot = snapshot("valid", valid_bytes)
    oversize_snapshot = snapshot(
        "oversize",
        oversize_bytes,
        claimed_byte_length=32,
    )
    tampered_snapshot = snapshot("tampered", tampered_bytes, digest="f" * 64)
    missing_payload_bytes = (
        b"Metadata exists but the actual recorded bytes are missing."
    )
    missing_payload_snapshot = snapshot("missing-payload", missing_payload_bytes)
    direct_oversize_snapshot = snapshot(
        "direct-oversize",
        oversize_bytes,
        claimed_byte_length=1,
    )
    direct_oversize_item = _item(
        module,
        evidence_id="evidence:direct-oversize",
        object_id="web-object:direct-oversize",
        lane="web",
        value="Direct Oversize Robotics",
        source_nature="current_web",
        source_locator="https://current.example/direct-oversize",
        snapshot=direct_oversize_snapshot,
    )
    web_inputs = (
        (
            "valid",
            valid_bytes,
            valid_snapshot,
            "Alpha Robotics",
            True,
        ),
        (
            "oversize",
            oversize_bytes,
            oversize_snapshot,
            "Oversize Robotics",
            True,
        ),
        (
            "tampered",
            tampered_bytes,
            tampered_snapshot,
            "Tampered Robotics",
            True,
        ),
        (
            "missing-payload",
            missing_payload_bytes,
            missing_payload_snapshot,
            "Metadata-only Robotics",
            False,
        ),
    )
    candidates = tuple(
        _candidate(
            module,
            token=token,
            canonical_id=None,
            display_name=display_name,
            lane="web",
            identity_kind="web_only",
            evidence=(
                _item(
                    module,
                    evidence_id=f"evidence:{token}",
                    object_id=f"web-object:{token}",
                    lane="web",
                    value=display_name,
                    source_nature="current_web",
                    source_locator=f"https://current.example/{token}",
                    snapshot=current_snapshot,
                ),
            ),
        )
        for token, _, current_snapshot, display_name, _ in web_inputs
    )
    payloads = (
        *tuple(
            module.WebSnapshotPayload(
                snapshot_id=current_snapshot.snapshot_id,
                content=payload,
            )
            for _, payload, current_snapshot, _, include_payload in web_inputs
            if include_payload
        ),
        module.WebSnapshotPayload(
            snapshot_id=direct_oversize_snapshot.snapshot_id,
            content=oversize_bytes,
        ),
    )

    def web_adapter(_: Any) -> Any:
        return module.RetrievalLaneResult(
            items=(direct_oversize_item,),
            candidates=candidates,
            web_snapshot_payloads=payloads,
        )

    plan = _plan(
        module,
        token="bounded-initial-snapshots",
        interaction_mode="information_retrieval",
        lanes=("web",),
        session_id="session:s8rg:snapshots",
    )
    result = module.create_ephemeral_knowledge_read(
        lane_adapters={"web": web_adapter},
        universal_web_policy=_web_policy(module, "universal"),
        web_snapshot_policy=snapshot_policy,
        web_handle_ttl=timedelta(hours=1),
        clock=lambda: NOW,
    ).execute(plan)

    assert tuple(item.evidence_id for item in result.items) == ("evidence:valid",)
    assert tuple(handle.display_name for handle in result.entity_handles) == (
        "Alpha Robotics",
    )
    retained = result.items[0].web_snapshot
    assert retained.content_sha256 == hashlib.sha256(valid_bytes).hexdigest()
    assert retained.byte_length == len(valid_bytes)
    assert retained.snapshot_id == valid_snapshot.snapshot_id
    traces = {trace.raw_candidate_id: trace for trace in result.candidate_traces}
    assert traces["raw-candidate:oversize"].disposition == "snapshot_oversize"
    assert traces["raw-candidate:tampered"].disposition == "snapshot_hash_mismatch"
    assert (
        traces["raw-candidate:missing-payload"].disposition
        == "snapshot_payload_missing"
    )
    assert traces["raw-candidate:oversize"].selected_result_id is None
    assert traces["raw-candidate:tampered"].selected_result_id is None
    assert traces["raw-candidate:missing-payload"].selected_result_id is None
    receipts = {receipt.snapshot_id: receipt for receipt in result.snapshot_receipts}
    assert receipts[oversize_snapshot.snapshot_id].status == "rejected"
    assert receipts[oversize_snapshot.snapshot_id].reason_code == "max_bytes_exceeded"
    assert receipts[oversize_snapshot.snapshot_id].observed_byte_length == 65
    assert receipts[tampered_snapshot.snapshot_id].status == "rejected"
    assert (
        receipts[tampered_snapshot.snapshot_id].reason_code == "content_hash_mismatch"
    )
    assert receipts[missing_payload_snapshot.snapshot_id].status == "rejected"
    assert (
        receipts[missing_payload_snapshot.snapshot_id].reason_code == "payload_missing"
    )
    assert receipts[direct_oversize_snapshot.snapshot_id].status == "rejected"
    assert (
        receipts[direct_oversize_snapshot.snapshot_id].reason_code
        == "max_bytes_exceeded"
    )
    assert receipts[direct_oversize_snapshot.snapshot_id].observed_byte_length == 65
    assert any(
        limitation.code == "web_snapshot_rejected" for limitation in result.limitations
    )

    crosswired_candidate = _candidate(
        module,
        token="crosswired-lane",
        canonical_id="company:crosswired",
        display_name="Crosswired Robotics",
        lane="vector",
        evidence=(
            _item(
                module,
                evidence_id="evidence:crosswired-lane",
                object_id="company:crosswired",
                lane="vector",
                value="Crosswired Robotics",
            ),
        ),
    ).model_copy(update={"release_id": "candidate-r2", "attempt": 9})
    crosswire_plan = _plan(
        module,
        token="crosswired-lane",
        interaction_mode="information_retrieval",
        lanes=("exact", "web"),
    )
    crosswire_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(crosswired_candidate,)
            ),
            "web": lambda _: module.RetrievalLaneResult(),
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(crosswire_plan)
    exact_trace = next(
        trace for trace in crosswire_result.traces if trace.lane == "exact"
    )
    assert exact_trace.status == "unavailable"
    assert exact_trace.failure_kind == "invalid_output"
    assert crosswire_result.entity_handles == ()
    assert crosswire_result.candidate_traces == ()

    missing_web_result = module.create_ephemeral_knowledge_read(
        lane_adapters={},
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(
        _plan(
            module,
            token="missing-required-web-adapter",
            interaction_mode="information_retrieval",
            lanes=("web",),
        )
    )
    missing_web_trace = next(
        trace for trace in missing_web_result.traces if trace.lane == "web"
    )
    assert missing_web_trace.status == "unavailable"
    assert missing_web_trace.failure_kind == "invalid_output"
    assert any(
        limitation.code == "current_web_unavailable"
        for limitation in missing_web_result.limitations
    )

    def revised_plan(base: Any, **updates: Any) -> Any:
        return module.RetrievalPlan.model_validate(
            {
                **base.model_dump(mode="json", exclude={"content_sha256"}),
                **updates,
            }
        )

    direct_constraint_plan = revised_plan(
        _plan(
            module,
            token="direct-constraint-and-max",
            interaction_mode="information_retrieval",
            lanes=("exact", "web"),
        ),
        protected_slots=(module.ProtectedSlot(kind="geography", value="深圳"),),
        max_candidates=1,
    )
    direct_outside = _item(
        module,
        evidence_id="evidence:direct-outside",
        object_id="company:outside",
        lane="exact",
        predicate="geography",
        value="广州",
    )
    direct_alpha = _item(
        module,
        evidence_id="evidence:direct-alpha",
        object_id="company:alpha",
        lane="exact",
        predicate="geography",
        value="深圳",
    )
    direct_beta = _item(
        module,
        evidence_id="evidence:direct-beta",
        object_id="company:beta",
        lane="exact",
        predicate="geography",
        value="深圳",
    )
    direct_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(direct_outside, direct_alpha, direct_beta)
            ),
            "web": lambda _: module.RetrievalLaneResult(),
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(direct_constraint_plan)
    assert tuple(item.evidence_id for item in direct_result.items) == (
        direct_alpha.evidence_id,
    )
    direct_outside_receipt = next(
        receipt
        for receipt in direct_result.constraint_receipts
        if receipt.aggregated_evidence_ids == (direct_outside.evidence_id,)
    )
    assert direct_outside_receipt.outcome == "rejected"

    missing_geography_item = _item(
        module,
        evidence_id="evidence:missing-geography",
        object_id="company:missing-geography",
        lane="exact",
        value="Missing Geography Robotics",
    )
    wrong_subject_geography_item = _item(
        module,
        evidence_id="evidence:wrong-subject-geography",
        object_id="company:beta",
        lane="exact",
        predicate="geography",
        value="深圳",
    ).model_copy(
        update={
            "claim_binding": module.EvidenceClaimBinding(
                subject_id="company:alpha",
                predicate="geography",
                value="深圳",
            )
        }
    )
    for hostile_geography_item in (
        missing_geography_item,
        wrong_subject_geography_item,
    ):
        hostile_geography_direct = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "exact": lambda _, item=hostile_geography_item: (
                    module.RetrievalLaneResult(items=(item,))
                ),
                "web": lambda _: module.RetrievalLaneResult(),
            },
            universal_web_policy=_web_policy(module, "universal"),
        ).execute(direct_constraint_plan)
        assert hostile_geography_direct.items == ()
        assert hostile_geography_direct.constraint_receipts[0].outcome == "rejected"

        hostile_geography_candidate = _candidate(
            module,
            token=hostile_geography_item.evidence_id,
            canonical_id=hostile_geography_item.object_id,
            display_name="Hostile Geography Robotics",
            lane="exact",
            evidence=(hostile_geography_item,),
        )
        hostile_geography_candidate_result = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "exact": lambda _, candidate=hostile_geography_candidate: (
                    module.RetrievalLaneResult(candidates=(candidate,))
                ),
                "web": lambda _: module.RetrievalLaneResult(),
            },
            universal_web_policy=_web_policy(module, "universal"),
        ).execute(direct_constraint_plan)
        assert hostile_geography_candidate_result.entity_handles == ()
        assert (
            hostile_geography_candidate_result.constraint_receipts[0].outcome
            == "rejected"
        )

    unresolved_web_geography_item = _item(
        module,
        evidence_id="evidence:unresolved-web-geography",
        object_id="web-object:unresolved-shenzhen",
        lane="web",
        predicate="geography",
        value="深圳",
        source_nature="current_web",
        source_locator="https://current.example/unresolved-shenzhen",
        snapshot=valid_snapshot,
    )
    unresolved_web_geography_candidate = _candidate(
        module,
        token="unresolved-web-geography",
        canonical_id=None,
        display_name="Unresolved Shenzhen Robotics",
        lane="web",
        identity_kind="web_only",
        evidence=(unresolved_web_geography_item,),
    )
    unresolved_web_geography_plan = revised_plan(
        direct_constraint_plan,
        plan_id="retrieval-plan:unresolved-web-geography",
        max_candidates=10,
        session_id="session:s8rg:unresolved-web-geography",
    )
    unresolved_web_geography_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(),
            "web": lambda _: module.RetrievalLaneResult(
                candidates=(unresolved_web_geography_candidate,)
            ),
        },
        universal_web_policy=_web_policy(module, "universal"),
        clock=lambda: NOW,
    ).execute(unresolved_web_geography_plan)
    assert tuple(
        handle.kind for handle in unresolved_web_geography_result.entity_handles
    ) == ("web",)
    assert unresolved_web_geography_result.constraint_receipts[0].outcome == (
        "accepted"
    )

    direct_ambiguity_plan = revised_plan(
        _plan(
            module,
            token="direct-ambiguity",
            interaction_mode="information_retrieval",
            lanes=("exact", "web"),
            decision=_ambiguity_decision(module, mode="non_blocking"),
        ),
        max_candidates=10,
    )
    direct_ambiguity = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(direct_alpha, direct_beta)
            ),
            "web": lambda _: module.RetrievalLaneResult(),
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(direct_ambiguity_plan)
    assert tuple(item.object_id for item in direct_ambiguity.items) == (
        "company:alpha",
    )

    local_alpha = _candidate(
        module,
        token="local-alpha",
        canonical_id="company:alpha",
        display_name="Alpha Robotics",
        lane="exact",
        evidence=(direct_alpha,),
    )
    local_beta = _candidate(
        module,
        token="local-beta",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        lane="exact",
        evidence=(direct_beta,),
    )
    two_candidate_plan = _plan(
        module,
        token="fuser-timeout-and-rerank-subset",
        interaction_mode="information_retrieval",
        lanes=("exact", "web"),
    )

    def exact_candidates(_: Any) -> Any:
        return module.RetrievalLaneResult(candidates=(local_alpha, local_beta))

    def empty_web_lane(_: Any) -> Any:
        return module.RetrievalLaneResult()

    def fuser_timeout(_: Any) -> Any:
        raise TimeoutError("recorded fusion timeout")

    timed_out_fusion = module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": exact_candidates, "web": empty_web_lane},
        identity_fuser=fuser_timeout,
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(two_candidate_plan)
    assert {handle.canonical_id for handle in timed_out_fusion.entity_handles} == {
        "company:alpha",
        "company:beta",
    }
    assert timed_out_fusion.fusion_receipt.mode == "deterministic_fallback"
    assert timed_out_fusion.fusion_receipt.degradation_reason == "timeout"

    def select_alpha(request: Any) -> Any:
        alpha_result_id = next(
            candidate.result_id
            for candidate in request.eligible_candidates
            if candidate.canonical_id == "company:alpha"
        )
        return module.RerankProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=(alpha_result_id,),
            rationale="Select the one requested eligible Company.",
        )

    rerank_subset = module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": exact_candidates, "web": empty_web_lane},
        reranker=select_alpha,
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(two_candidate_plan)
    assert tuple(handle.canonical_id for handle in rerank_subset.entity_handles) == (
        "company:alpha",
    )
    assert rerank_subset.rerank_receipt.mode == "recorded_structured"

    forged_web_item = _item(
        module,
        evidence_id="evidence:forged-web-canonical",
        object_id="web-object:forged-canonical",
        lane="web",
        value="Forged Canonical Robotics",
        source_nature="current_web",
        source_locator="https://current.example/forged-canonical",
        snapshot=valid_snapshot,
    )
    forged_web_candidate = _candidate(
        module,
        token="forged-web-canonical",
        canonical_id="company:provider-forged",
        display_name="Forged Canonical Robotics",
        lane="web",
        identity_kind="web_candidate",
        evidence=(forged_web_item,),
    )

    def invent_canonical(request: Any) -> Any:
        return module.IdentityFusionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="identity-fusion-v1",
            model_id="recorded-identity-fuser",
            prompt_version="identity-fusion-prompt-v1",
            groups=(
                module.IdentityFusionGroup(
                    canonical_id="company:model-invented",
                    raw_candidate_ids=(forged_web_candidate.raw_candidate_id,),
                    evidence_ids=(forged_web_item.evidence_id,),
                    confidence=0.99,
                    rationale="A hostile proposal invents accepted identity state.",
                ),
            ),
        )

    forged_web_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "web": lambda _: module.RetrievalLaneResult(
                candidates=(forged_web_candidate,)
            )
        },
        identity_fuser=invent_canonical,
        universal_web_policy=_web_policy(module, "universal"),
        clock=lambda: NOW,
    ).execute(
        _plan(
            module,
            token="forged-web-canonical",
            interaction_mode="information_retrieval",
            lanes=("web",),
            session_id="session:s8rg:forged-canonical",
        )
    )
    assert tuple(handle.kind for handle in forged_web_result.entity_handles) == ("web",)
    assert forged_web_result.fusion_receipt.mode == "deterministic_fallback"
    assert (
        forged_web_result.fusion_receipt.degradation_reason
        == "conflicting_accepted_canonical_ids"
    )
    retained_forged_handle = forged_web_result.entity_handles[0]
    resolution_replay = module.WebHandleReplay(
        handle=retained_forged_handle,
        snapshot_payloads=(
            module.WebSnapshotPayload(
                snapshot_id=valid_snapshot.snapshot_id,
                content=valid_bytes,
            ),
        ),
        observed_live_content_sha256=valid_snapshot.content_sha256,
        replayed_at=NOW,
    )
    resolution_plan = revised_plan(
        _plan(
            module,
            token="crosswired-accepted-lookup",
            interaction_mode="handle_replay",
            lanes=(),
            decision=None,
            session_id="session:s8rg:forged-canonical",
        ),
        retained_web_handles=(retained_forged_handle,),
        web_handle_replays=(resolution_replay,),
        handle_operation="resolve_read_only",
    )

    def resolution_proposal(request: Any) -> Any:
        return module.WebHandleResolutionProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=request.handle.handle_id,
            accepted_release_id=RELEASE_ID,
            canonical_id="company:alpha",
            canonical_evidence_ids=("evidence:canonical-alpha",),
            retained_snapshot_ids=request.evidence_snapshot_ids,
            resolution_state="resolved",
            rationale="Recorded proposal for a hostile lookup-boundary check.",
        )

    crosswired_lookup_result = module.create_ephemeral_knowledge_read(
        lane_adapters={},
        universal_web_policy=_web_policy(module, "universal"),
        web_handle_resolver=resolution_proposal,
        accepted_identity_lookup=lambda _: module.AcceptedIdentityLookupResult(
            release_id="candidate-r2",
            canonical_id="company:wrong",
            accepted=True,
            evidence_ids=("evidence:canonical-alpha",),
        ),
        clock=lambda: NOW,
    ).execute(resolution_plan)
    assert crosswired_lookup_result.entity_handles == (retained_forged_handle,)
    assert crosswired_lookup_result.handle_resolution_receipts[0].status == "rejected"
    assert (
        crosswired_lookup_result.handle_resolution_receipts[0].reason_code
        == "unaccepted_canonical_identity"
    )

    incomplete_handle_updates = (
        {
            "handle_id": "web-handle:missing-snapshot",
            "evidence_snapshot_ids": (),
        },
        {
            "handle_id": "web-handle:missing-session",
            "session_id": None,
        },
        {
            "handle_id": "web-handle:missing-expiry",
            "expires_at": None,
        },
    )
    for handle_updates in incomplete_handle_updates:
        incomplete_handle = retained_forged_handle.model_copy(update=handle_updates)
        incomplete_replay = module.WebHandleReplay(
            handle=incomplete_handle,
            snapshot_payloads=(
                ()
                if not incomplete_handle.evidence_snapshot_ids
                else resolution_replay.snapshot_payloads
            ),
            observed_live_content_sha256=valid_snapshot.content_sha256,
            replayed_at=NOW,
        )
        incomplete_plan = revised_plan(
            resolution_plan,
            retained_web_handles=(incomplete_handle,),
            web_handle_replays=(incomplete_replay,),
            handle_operation="coreference",
        )
        incomplete_result = module.create_ephemeral_knowledge_read(
            lane_adapters={},
            universal_web_policy=_web_policy(module, "universal"),
            clock=lambda: NOW,
        ).execute(incomplete_plan)
        assert incomplete_result.live_referent_handle_ids == ()
        assert (
            incomplete_result.handle_replay_receipts[0].continuity_established is False
        )
        assert incomplete_result.handle_replay_receipts[0].status != "accepted"

    for limit_mode in ("universal", "official_only"):
        limited_candidates = tuple(
            _candidate(
                module,
                token=f"{limit_mode}-limit-{index}",
                canonical_id=None,
                display_name=f"Limited Candidate {index}",
                lane="web",
                identity_kind="web_only",
                evidence=(
                    _item(
                        module,
                        evidence_id=f"evidence:{limit_mode}-limit-{index}",
                        object_id=f"web-object:{limit_mode}-limit-{index}",
                        lane="web",
                        value=f"Limited Candidate {index}",
                        source_nature="current_web",
                        source_authority=(
                            "official" if limit_mode == "official_only" else "other"
                        ),
                        source_locator=(
                            f"https://www.sz.gov.cn/limit-{index}"
                            if limit_mode == "official_only"
                            else f"https://current.example/limit-{index}"
                        ),
                        snapshot=valid_snapshot,
                    ),
                ),
            )
            for index in (1, 2)
        )
        limit_policy = module.WebSearchPolicy(
            mode=limit_mode,
            max_provider_calls=1,
            timeout_ms=1_500,
            max_results=1,
            allowed_domains=(("sz.gov.cn",) if limit_mode == "official_only" else ()),
        )
        limited_plan = module.RetrievalPlan(
            plan_id=f"retrieval-plan:{limit_mode}-result-limit",
            plan_version="retrieval-plan-v1",
            original_query=f"查询 {limit_mode} 有界结果",
            behavior_class=("F" if limit_mode == "official_only" else "G"),
            interaction_mode=(
                "safety_guidance"
                if limit_mode == "official_only"
                else "information_retrieval"
            ),
            release_id=RELEASE_ID,
            domains=(() if limit_mode == "official_only" else ("company",)),
            protected_slots=(),
            lanes=("web",),
            max_candidates=5,
            web_required=True,
            web_policy=limit_policy,
            freshness_material=True,
            session_id=f"session:s8rg:{limit_mode}-result-limit",
        )
        limited_result = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "web": lambda _, values=limited_candidates: module.RetrievalLaneResult(
                    candidates=values
                )
            },
            universal_web_policy=limit_policy,
            clock=lambda: NOW,
        ).execute(limited_plan)
        limited_traces = {
            trace.raw_candidate_id: trace for trace in limited_result.candidate_traces
        }
        assert set(limited_traces) == {
            candidate.raw_candidate_id for candidate in limited_candidates
        }
        assert (
            limited_traces[limited_candidates[1].raw_candidate_id].disposition
            == "result_limit_rejected"
        )
        assert limited_traces[limited_candidates[1].raw_candidate_id].evidence_ids == (
            limited_candidates[1].evidence[0].evidence_id,
        )
        limited_web_trace = next(
            trace for trace in limited_result.traces if trace.lane == "web"
        )
        assert limited_web_trace.candidate_count == 2

    official_item = _item(
        module,
        evidence_id="evidence:official-candidate",
        object_id="web-object:official-candidate",
        lane="web",
        value="Official Candidate Robotics",
        source_nature="current_web",
        source_authority="official",
        source_locator="https://www.sz.gov.cn/official-candidate",
        snapshot=valid_snapshot,
    )
    unverified_item = _item(
        module,
        evidence_id="evidence:unverified-candidate",
        object_id="web-object:unverified-candidate",
        lane="web",
        value="Unverified Candidate Robotics",
        source_nature="current_web",
        source_locator="https://unverified.example/candidate",
        snapshot=valid_snapshot,
    )
    official_candidate = _candidate(
        module,
        token="official-candidate",
        canonical_id="company:official-provider-claim",
        display_name="Official Candidate Robotics",
        lane="web",
        identity_kind="web_candidate",
        evidence=(official_item,),
    )
    unverified_candidate = _candidate(
        module,
        token="unverified-candidate",
        canonical_id="company:unverified-provider-claim",
        display_name="Unverified Candidate Robotics",
        lane="web",
        identity_kind="web_candidate",
        evidence=(unverified_item,),
    )
    official_plan = module.RetrievalPlan(
        plan_id="retrieval-plan:official-candidate-boundary",
        plan_version="retrieval-plan-v1",
        original_query="查询当前官方候选",
        behavior_class="F",
        interaction_mode="safety_guidance",
        release_id=RELEASE_ID,
        domains=(),
        protected_slots=(),
        lanes=("web",),
        max_candidates=5,
        web_required=True,
        web_policy=module.WebSearchPolicy(
            mode="official_only",
            max_provider_calls=1,
            timeout_ms=1_500,
            max_results=5,
            allowed_domains=("sz.gov.cn",),
        ),
        freshness_material=True,
        session_id="session:s8rg:official",
    )
    official_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "web": lambda _: module.RetrievalLaneResult(
                candidates=(official_candidate, unverified_candidate)
            )
        },
        universal_web_policy=_web_policy(module, "universal"),
        clock=lambda: NOW,
    ).execute(official_plan)
    assert tuple(item.evidence_id for item in official_result.items) == (
        official_item.evidence_id,
    )
    assert tuple(handle.kind for handle in official_result.entity_handles) == ("web",)
    official_traces = {
        trace.raw_candidate_id: trace for trace in official_result.candidate_traces
    }
    assert (
        official_traces[unverified_candidate.raw_candidate_id].disposition
        == "official_policy_rejected"
    )
    assert official_traces[unverified_candidate.raw_candidate_id].evidence_ids == (
        unverified_item.evidence_id,
    )

    role_part = module.MaterialQuestionPart(
        part_id="part:target-role",
        text="确认 Alpha Robotics 的当前负责人",
        subject_id="company:alpha",
        predicate="current_role",
        requested_value="chief executive",
        material=True,
    )
    wrong_subject_role = _item(
        module,
        evidence_id="evidence:wrong-subject-role",
        object_id="company:beta",
        lane="exact",
        predicate="current_role",
        value="chief executive",
    )

    def hostile_role_decider(request: Any) -> Any:
        return module.SufficiencyProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="sufficiency-v1",
            decision_id="sufficiency:wrong-subject",
            parts=(
                module.MaterialPartProposal(
                    part_id=role_part.part_id,
                    outcome="supported",
                    evidence_ids=(wrong_subject_role.evidence_id,),
                    rationale="A hostile proposal cross-wires another Company.",
                    uncertainty="low",
                    confidence=0.99,
                ),
            ),
        )

    hostile_role_plan = revised_plan(
        _plan(
            module,
            token="wrong-subject-sufficiency",
            interaction_mode="information_retrieval",
            lanes=("exact", "web"),
        ),
        material_parts=(role_part,),
    )
    hostile_role_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(items=(wrong_subject_role,)),
            "web": empty_web_lane,
        },
        sufficiency_decider=hostile_role_decider,
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(hostile_role_plan)
    assert hostile_role_result.sufficiency_report.parts[0].outcome == "missing"
    assert hostile_role_result.sufficiency_report.complete is False

    def missing_role_decider(request: Any) -> Any:
        return module.SufficiencyProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="sufficiency-v1",
            decision_id="sufficiency:missing-role",
            parts=(
                module.MaterialPartProposal(
                    part_id=role_part.part_id,
                    outcome="missing",
                    evidence_ids=(),
                    rationale="No direct retained role evidence exists.",
                    uncertainty="high",
                    confidence=0.2,
                ),
            ),
        )

    zero_budget_calls: list[Any] = []

    def forbidden_zero_budget_search(request: Any) -> Any:
        zero_budget_calls.append(request)
        return module.SupplementalLaneResult(
            items=(), elapsed_ms=0, cost_units=0.0, retryable=False
        )

    zero_budget_plan = revised_plan(
        hostile_role_plan,
        plan_id="retrieval-plan:zero-supplemental-budget",
        supplemental_budget=module.SupplementalBudget(
            max_wall_time_ms=1_000,
            max_provider_calls=0,
            max_retries=1,
            max_cost_units=10.0,
        ),
    )
    zero_budget_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(),
            "web": empty_web_lane,
        },
        sufficiency_decider=missing_role_decider,
        supplemental_search=forbidden_zero_budget_search,
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(zero_budget_plan)
    assert zero_budget_calls == []
    assert zero_budget_result.supplemental_budget_receipt.provider_calls == 0
    assert zero_budget_result.supplemental_budget_receipt.exhaustion_reason == (
        "provider_calls"
    )

    within_budget_plan = revised_plan(
        hostile_role_plan,
        plan_id="retrieval-plan:within-supplemental-budget",
        supplemental_budget=module.SupplementalBudget(
            max_wall_time_ms=1_000,
            max_provider_calls=2,
            max_retries=1,
            max_cost_units=10.0,
        ),
    )
    within_budget_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(),
            "web": empty_web_lane,
        },
        sufficiency_decider=missing_role_decider,
        supplemental_search=lambda _: module.SupplementalLaneResult(
            items=(), elapsed_ms=1, cost_units=0.1, retryable=False
        ),
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(within_budget_plan)
    assert within_budget_result.supplemental_budget_receipt.exhausted is False
    assert within_budget_result.supplemental_budget_receipt.exhaustion_reason is None
    assert all(
        limitation.code != "supplemental_budget_exhausted"
        for limitation in within_budget_result.limitations
    )
    assert within_budget_result.continuation_reasons == ("evidence_gap",)

    supplemental_outside = _item(
        module,
        evidence_id="evidence:supplemental-outside",
        object_id="company:supplemental-outside",
        lane="supplemental",
        predicate="geography",
        value="广州",
    )
    supplemental_alpha = _item(
        module,
        evidence_id="evidence:supplemental-alpha",
        object_id="company:supplemental-alpha",
        lane="supplemental",
        predicate="geography",
        value="深圳",
    )
    supplemental_beta = _item(
        module,
        evidence_id="evidence:supplemental-beta",
        object_id="company:supplemental-beta",
        lane="supplemental",
        predicate="geography",
        value="深圳",
    )
    constrained_supplemental_plan = revised_plan(
        within_budget_plan,
        plan_id="retrieval-plan:constrained-supplemental-results",
        protected_slots=(module.ProtectedSlot(kind="geography", value="深圳"),),
        max_candidates=1,
    )
    constrained_supplemental_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(),
            "web": empty_web_lane,
        },
        sufficiency_decider=missing_role_decider,
        supplemental_search=lambda _: module.SupplementalLaneResult(
            items=(supplemental_outside, supplemental_alpha, supplemental_beta),
            elapsed_ms=1,
            cost_units=0.1,
            retryable=False,
        ),
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(constrained_supplemental_plan)
    assert tuple(item.object_id for item in constrained_supplemental_result.items) == (
        supplemental_alpha.object_id,
    )
    outside_supplemental_receipt = next(
        receipt
        for receipt in constrained_supplemental_result.constraint_receipts
        if receipt.aggregated_evidence_ids == (supplemental_outside.evidence_id,)
    )
    assert outside_supplemental_receipt.outcome == "rejected"

    invalid_supplemental_results = (
        module.SupplementalLaneResult.model_construct(
            items=(supplemental_alpha,),
            elapsed_ms=1,
            cost_units=-1.0,
            retryable=False,
        ),
        module.SupplementalLaneResult.model_construct(
            items=(supplemental_alpha,),
            elapsed_ms=1,
            cost_units=float("nan"),
            retryable=False,
        ),
        module.SupplementalLaneResult.model_construct(
            items=(supplemental_alpha,),
            elapsed_ms=1,
            cost_units=float("inf"),
            retryable=False,
        ),
        module.SupplementalLaneResult.model_construct(
            items=(supplemental_alpha,),
            elapsed_ms=-1,
            cost_units=0.1,
            retryable=False,
        ),
        module.SupplementalLaneResult(
            items=(direct_alpha,),
            elapsed_ms=1,
            cost_units=0.1,
            retryable=False,
        ),
    )
    for invalid_supplemental_result in invalid_supplemental_results:
        rejected_supplemental_result = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "exact": lambda _: module.RetrievalLaneResult(),
                "web": empty_web_lane,
            },
            sufficiency_decider=missing_role_decider,
            supplemental_search=lambda _, result=invalid_supplemental_result: result,
            universal_web_policy=_web_policy(module, "universal"),
        ).execute(within_budget_plan)
        assert rejected_supplemental_result.items == ()
        rejected_supplemental_trace = next(
            trace
            for trace in rejected_supplemental_result.traces
            if trace.phase == "supplemental"
        )
        assert rejected_supplemental_trace.status == "unavailable"
        assert rejected_supplemental_trace.failure_kind == "invalid_output"
        rejected_cost = (
            rejected_supplemental_result.supplemental_budget_receipt.cost_units
        )
        assert rejected_cost >= 0.0
        assert math.isfinite(rejected_cost)
        assert any(
            limitation.code == "supplemental_unavailable"
            and limitation.reason == "invalid_output"
            for limitation in rejected_supplemental_result.limitations
        )

    vector_beta_item = _item(
        module,
        evidence_id="evidence:vector-beta",
        object_id="company:beta",
        lane="vector",
        value="Beta Robotics",
    )
    duplicate_raw_beta = _candidate(
        module,
        token="vector-beta",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        lane="vector",
        evidence=(vector_beta_item,),
    ).model_copy(update={"raw_candidate_id": local_alpha.raw_candidate_id})
    duplicate_raw_plan = _plan(
        module,
        token="duplicate-raw-candidate-id",
        interaction_mode="information_retrieval",
        lanes=("exact", "vector", "web"),
    )
    duplicate_raw_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(candidates=(local_alpha,)),
            "vector": lambda _: module.RetrievalLaneResult(
                candidates=(duplicate_raw_beta,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(duplicate_raw_plan)
    assert duplicate_raw_result.entity_handles == ()
    assert any(
        limitation.code == "duplicate_raw_candidate_id"
        for limitation in duplicate_raw_result.limitations
    )

    conflicting_evidence_beta = vector_beta_item.model_copy(
        update={"evidence_id": direct_alpha.evidence_id}
    )
    evidence_collision_beta = _candidate(
        module,
        token="evidence-collision-beta",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        lane="vector",
        evidence=(conflicting_evidence_beta,),
    )
    evidence_collision_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(candidates=(local_alpha,)),
            "vector": lambda _: module.RetrievalLaneResult(
                candidates=(evidence_collision_beta,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(duplicate_raw_plan)
    assert evidence_collision_result.entity_handles == ()
    assert any(
        limitation.code == "conflicting_evidence_id"
        for limitation in evidence_collision_result.limitations
    )

    displayed_slot = module.ProtectedSlot(
        kind="displayed_entity_set",
        value="displayed_entity_set",
        entity_ids=("company:alpha",),
    )
    displayed_plan = revised_plan(
        two_candidate_plan,
        protected_slots=(displayed_slot,),
    )
    displayed_direct_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(direct_beta, direct_alpha)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(displayed_plan)
    assert tuple(item.object_id for item in displayed_direct_result.items) == (
        "company:alpha",
    )
    displayed_candidate_result = module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": exact_candidates, "web": empty_web_lane},
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(displayed_plan)
    assert tuple(
        handle.canonical_id for handle in displayed_candidate_result.entity_handles
    ) == ("company:alpha",)

    crosswired_displayed_item = _item(
        module,
        evidence_id="evidence:displayed-crosswire",
        object_id="company:alpha",
        lane="exact",
        predicate="related_company",
        value="Alpha Robotics",
    )
    crosswired_displayed_candidate = _candidate(
        module,
        token="displayed-crosswire",
        canonical_id="company:beta",
        display_name="Beta Robotics",
        lane="exact",
        evidence=(crosswired_displayed_item,),
    )
    crosswired_displayed_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(crosswired_displayed_candidate,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(displayed_plan)
    assert crosswired_displayed_result.entity_handles == ()
    assert crosswired_displayed_result.constraint_receipts[0].outcome == "rejected"
    unresolved_displayed_candidate = _candidate(
        module,
        token="displayed-unresolved",
        canonical_id=None,
        display_name="Unresolved Alpha-shaped candidate",
        lane="exact",
        identity_kind="web_only",
        evidence=(crosswired_displayed_item,),
    )
    unresolved_displayed_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(unresolved_displayed_candidate,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(displayed_plan)
    assert unresolved_displayed_result.constraint_receipts[0].outcome == "rejected"

    negated_identity = "company:negated"
    negated_item = _item(
        module,
        evidence_id="evidence:negated-identity",
        object_id=negated_identity,
        lane="exact",
        predicate="display_name",
        value="Safe Display Name",
    )
    negation_plan = revised_plan(
        two_candidate_plan,
        protected_slots=(
            module.ProtectedSlot(kind="negation", value=negated_identity),
        ),
    )
    negation_direct_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(negated_item, direct_alpha)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(negation_plan)
    assert tuple(item.object_id for item in negation_direct_result.items) == (
        direct_alpha.object_id,
    )
    negated_candidate = _candidate(
        module,
        token="negated-identity",
        canonical_id=negated_identity,
        display_name="Safe Display Name",
        lane="exact",
        evidence=(negated_item,),
    )
    negation_candidate_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(negated_candidate, local_alpha)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(negation_plan)
    assert tuple(
        handle.canonical_id for handle in negation_candidate_result.entity_handles
    ) == (local_alpha.canonical_id,)

    target_identifier = "CN117873146A"
    wrong_patent_item = _item(
        module,
        evidence_id="evidence:patent-wrong",
        object_id="patent:CN000000000B",
        lane="exact",
        domain="patent",
        predicate="patent_number",
        value="CN000000000B",
    )
    correct_patent_item = _item(
        module,
        evidence_id="evidence:patent-correct",
        object_id=f"patent:{target_identifier}",
        lane="exact",
        domain="patent",
        predicate="patent_number",
        value=target_identifier,
    )
    exact_identifier_plan = revised_plan(
        two_candidate_plan,
        domains=("patent",),
        protected_slots=(
            module.ProtectedSlot(kind="exact_identifier", value=target_identifier),
        ),
    )
    exact_identifier_direct_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(wrong_patent_item, correct_patent_item)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(exact_identifier_plan)
    assert tuple(item.object_id for item in exact_identifier_direct_result.items) == (
        f"patent:{target_identifier}",
    )

    wrong_patent_candidate = _candidate(
        module,
        token="patent-wrong",
        canonical_id="patent:CN000000000B",
        display_name="Wrong patent",
        lane="exact",
        domain="patent",
        evidence=(wrong_patent_item,),
    )
    correct_patent_candidate = _candidate(
        module,
        token="patent-correct",
        canonical_id=f"patent:{target_identifier}",
        display_name="Target patent",
        lane="exact",
        domain="patent",
        evidence=(correct_patent_item,),
    )
    exact_identifier_candidate_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(wrong_patent_candidate, correct_patent_candidate)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(exact_identifier_plan)
    assert tuple(
        handle.canonical_id
        for handle in exact_identifier_candidate_result.entity_handles
    ) == (f"patent:{target_identifier}",)

    company_relationship_item = _item(
        module,
        evidence_id="evidence:company-applicant-relationship",
        object_id="company:alpha",
        lane="exact",
        predicate="applicant_of",
        value=f"patent:{target_identifier}",
    )
    company_relationship_candidate = _candidate(
        module,
        token="company-applicant-relationship",
        canonical_id="company:alpha",
        display_name="Alpha Robotics",
        lane="exact",
        evidence=(company_relationship_item,),
    )
    mixed_domain_exact_plan = revised_plan(
        exact_identifier_plan,
        domains=("company", "patent"),
    )
    mixed_domain_direct_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                items=(company_relationship_item,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(mixed_domain_exact_plan)
    assert mixed_domain_direct_result.items == (company_relationship_item,)
    mixed_domain_candidate_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(company_relationship_candidate,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(mixed_domain_exact_plan)
    assert tuple(
        handle.canonical_id for handle in mixed_domain_candidate_result.entity_handles
    ) == (company_relationship_candidate.canonical_id,)

    provider_claim_override_item = _item(
        module,
        evidence_id="evidence:patent-provider-claim-override",
        object_id="patent:CN000000000B",
        lane="exact",
        domain="patent",
        predicate="patent_number",
        value=target_identifier,
    )
    display_name_override_item = _item(
        module,
        evidence_id="evidence:patent-display-name-override",
        object_id="patent:CN000000000B",
        lane="exact",
        domain="patent",
        predicate="display_name",
        value=target_identifier,
    )
    for hostile_identifier_item in (
        provider_claim_override_item,
        display_name_override_item,
    ):
        hostile_identifier_direct = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "exact": lambda _, item=hostile_identifier_item: (
                    module.RetrievalLaneResult(items=(item,))
                ),
                "web": empty_web_lane,
            },
            universal_web_policy=_web_policy(module, "universal"),
        ).execute(exact_identifier_plan)
        assert hostile_identifier_direct.items == ()
        hostile_identifier_candidate = _candidate(
            module,
            token=hostile_identifier_item.evidence_id,
            canonical_id="patent:CN000000000B",
            display_name=target_identifier,
            lane="exact",
            domain="patent",
            evidence=(hostile_identifier_item,),
        )
        hostile_identifier_candidate_result = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "exact": lambda _, candidate=hostile_identifier_candidate: (
                    module.RetrievalLaneResult(candidates=(candidate,))
                ),
                "web": empty_web_lane,
            },
            universal_web_policy=_web_policy(module, "universal"),
        ).execute(exact_identifier_plan)
        assert hostile_identifier_candidate_result.entity_handles == ()

    crosswired_patent_reference = _item(
        module,
        evidence_id="evidence:patent-reference-crosswire",
        object_id=f"patent:{target_identifier}",
        lane="exact",
        domain="patent",
        predicate="cites_patent",
        value="Referenced by the wrong patent candidate",
    )
    crosswired_patent_candidate = _candidate(
        module,
        token="patent-reference-crosswire",
        canonical_id="patent:CN000000000B",
        display_name="Wrong patent with a target reference",
        lane="exact",
        domain="patent",
        evidence=(wrong_patent_item, crosswired_patent_reference),
    )
    crosswired_patent_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(crosswired_patent_candidate,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(exact_identifier_plan)
    assert crosswired_patent_result.entity_handles == ()
    assert crosswired_patent_result.constraint_receipts[0].outcome == "rejected"

    crosswired_patent_claim_candidate = _candidate(
        module,
        token="patent-claim-crosswire",
        canonical_id="patent:CN000000000B",
        display_name="Wrong patent with a target identifier claim",
        lane="exact",
        domain="patent",
        evidence=(wrong_patent_item, correct_patent_item),
    )
    crosswired_patent_claim_result = module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(
                candidates=(crosswired_patent_claim_candidate,)
            ),
            "web": empty_web_lane,
        },
        universal_web_policy=_web_policy(module, "universal"),
    ).execute(exact_identifier_plan)
    assert crosswired_patent_claim_result.entity_handles == ()
    assert crosswired_patent_claim_result.constraint_receipts[0].outcome == "rejected"

    with pytest.raises(ValueError):
        revised_plan(
            two_candidate_plan,
            lanes=("web", "web"),
        )
    with pytest.raises(ValueError):
        revised_plan(
            two_candidate_plan,
            lanes=("filesystem_scan",),
        )
    with pytest.raises(ValueError):
        revised_plan(
            two_candidate_plan,
            ambiguity_decision=_ambiguity_decision(module, mode="blocking"),
        )
