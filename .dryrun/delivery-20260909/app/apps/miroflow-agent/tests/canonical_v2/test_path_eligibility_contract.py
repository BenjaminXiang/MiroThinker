from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import DecisionMethod
from src.data_agents.canonical_v2.contracts import IdentityAction
from src.data_agents.canonical_v2.contracts import IdentityDecision
from src.data_agents.canonical_v2.contracts import PolicyDecision
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import PolicyOutcome
from src.data_agents.canonical_v2.contracts import PolicyReference
from src.data_agents.canonical_v2.contracts import RelationshipDecision
from src.data_agents.canonical_v2.contracts import RelationshipDecisionState


TARGET_MODULE = "src.data_agents.canonical_v2.path_eligibility"
NOW = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s6-path-r1"
PUBLISHED_USER_PATHS = (
    "exact_lookup",
    "structured_filter",
    "verified_relationship_traversal",
    "semantic_recall",
    "recommendation",
    "ranking",
)


def _module() -> Any:
    module = import_module(TARGET_MODULE)
    assert module.PolicyDecision is PolicyDecision
    assert module.PolicyReference is PolicyReference
    return module


def _policy(kind: PolicyKind, version: str) -> PolicyReference:
    return PolicyReference(
        policy_id=f"canonical-v2-{kind.value}",
        policy_version=version,
        policy_kind=kind,
        content_sha256="6" * 64,
        effective_at=NOW - timedelta(days=1),
    )


def _inclusion(identity_id: str) -> PolicyDecision:
    return PolicyDecision(
        decision_id=f"inclusion:{identity_id}",
        policy=_policy(PolicyKind.inclusion, "domain-inclusion-v1"),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.admitted,
        score=None,
        limitations=(),
        hard_exclusion_codes=(),
        supporting_assertion_ids=(f"assertion:{identity_id}:identity",),
        evaluated_at=NOW,
    )


def _excluded_inclusion(identity_id: str, code: str) -> PolicyDecision:
    return PolicyDecision(
        decision_id=f"inclusion:{identity_id}",
        policy=_policy(PolicyKind.inclusion, "domain-inclusion-v1"),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.excluded,
        score=None,
        limitations=(),
        hard_exclusion_codes=(code,),
        supporting_assertion_ids=(f"assertion:{identity_id}:{code}",),
        evaluated_at=NOW,
    )


def _projection(
    module: Any,
    *,
    domain: str,
    identity_id: str,
    fields: tuple[str, ...],
    quality_signals: tuple[Any, ...] = (),
    paper_identity_status: str | None = None,
    diagnostic_metadata: dict[str, str] | None = None,
) -> Any:
    return module.TypedProjectionInput(
        projection_id=f"projection:{identity_id}",
        canonical_identity_id=identity_id,
        domain=domain,
        release_id=RELEASE_ID,
        canonical_identity_state="active",
        domain_identity_status=(paper_identity_status if domain == "paper" else None),
        usable_field_paths=fields,
        field_assertion_ids={
            field: (f"assertion:{identity_id}:{field}",) for field in fields
        },
        quality_signals=quality_signals,
        diagnostic_metadata=diagnostic_metadata or {},
    )


def _relationship_decision(
    *,
    decision_id: str,
    relationship_type_id: str,
    source_identity_id: str,
    target_identity_id: str,
    state: RelationshipDecisionState,
    role_bindings: dict[str, str] | None = None,
) -> RelationshipDecision:
    assertion_id = f"relationship-assertion:{decision_id}"
    return RelationshipDecision(
        decision_id=decision_id,
        canonical_relationship_id=f"canonical-relationship:{decision_id}",
        relationship_type_id=relationship_type_id,
        relationship_type_version="canonical-v2-relationship-v1",
        source_canonical_identity_id=source_identity_id,
        target_canonical_identity_id=target_identity_id,
        state=state,
        candidate_assertion_ids=(assertion_id,),
        selected_assertion_ids=(
            (assertion_id,) if state is RelationshipDecisionState.accepted else ()
        ),
        conflicting_assertion_ids=(),
        role_bindings=role_bindings or {},
        policy=_policy(PolicyKind.relationship, "relationship-decision-v1"),
        method=DecisionMethod.deterministic,
        method_version="relationship-decision-v1",
        decision_run_id="relationship-build-run-1",
        confidence=0.95,
        rationale=f"{state.value} evidence-backed relationship fixture.",
        release_id=RELEASE_ID,
        decided_at=NOW,
    )


def _merge_decision(
    *,
    merged_identity_id: str,
    merge_peer_identity_id: str,
    survivor_identity_id: str,
) -> IdentityDecision:
    return IdentityDecision(
        decision_id="identity-decision:paper-merge",
        action=IdentityAction.merge,
        source_identity_ids=("source-paper:merged", "source-paper:merge-peer"),
        input_canonical_identity_ids=(
            merged_identity_id,
            merge_peer_identity_id,
        ),
        output_canonical_identity_ids=(survivor_identity_id,),
        supporting_record_ids=("record:paper-merge",),
        policy=_policy(PolicyKind.identity, "identity-resolution-v1"),
        method=DecisionMethod.deterministic,
        method_version="identity-merge-v1",
        decision_run_id="identity-build-run-1",
        confidence=1.0,
        rationale="Accepted merge redirects both predecessors to one survivor.",
        decided_at=NOW,
    )


def _decisions_by_path(result: Any) -> dict[str, PolicyDecision]:
    assert all(isinstance(decision, PolicyDecision) for decision in result.decisions)
    assert all(
        isinstance(decision.policy, PolicyReference) for decision in result.decisions
    )
    paths = tuple(decision.path for decision in result.decisions)
    assert None not in paths
    assert len(paths) == len(set(paths)), "path decisions must not contain duplicates"
    decisions = {decision.path: decision for decision in result.decisions}
    assert set(decisions) == set(PUBLISHED_USER_PATHS)
    return decisions


def test_partial_four_domain_projections_remain_exactly_reachable() -> None:
    module = _module()
    cases = (
        (
            "professor",
            "professor-c1",
            None,
            ("name", "institution"),
            ("profile_summary_incomplete",),
        ),
        (
            "company",
            "company-c1",
            None,
            ("name", "normalized_name"),
            ("technology_route_summary_incomplete",),
        ),
        (
            "paper",
            "paper-c1",
            "unverified",
            ("title", "year"),
            ("identity_unverified", "summary_incomplete"),
        ),
        (
            "patent",
            "patent-c1",
            None,
            ("patent_number", "title"),
            ("ipc_incomplete",),
        ),
    )

    for domain, identity_id, paper_status, fields, limitations in cases:
        quality_signals = tuple(
            module.QualitySignal(
                code=code,
                affected_paths=PUBLISHED_USER_PATHS,
                supporting_assertion_ids=(f"assertion:{identity_id}:{fields[0]}",),
            )
            for code in limitations
        )
        projection = _projection(
            module,
            domain=domain,
            identity_id=identity_id,
            fields=fields,
            quality_signals=quality_signals,
            paper_identity_status=paper_status,
        )
        inclusion = _inclusion(identity_id)
        request = module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
            projection=projection,
            inclusion_decision=inclusion,
            relationship_decisions=(),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )

        result = module.PathEligibilityEngine().evaluate(request)
        exact = _decisions_by_path(result)["exact_lookup"]

        assert result.projection_id == projection.projection_id
        assert projection.canonical_identity_state == "active"
        assert projection.domain_identity_status == paper_status
        assert result.inclusion_decision_id == inclusion.decision_id
        assert result.relationship_decision_ids == ()
        assert exact.outcome.value == "admitted"
        assert set(limitations) <= set(exact.limitations)
        assert exact.hard_exclusion_codes == ()
        assert exact.supporting_assertion_ids
        assert exact.policy.policy_version == "path-eligibility-v1"


def test_partial_relationships_remain_reachable_in_all_eight_directions() -> None:
    module = _module()
    cases = (
        (
            "company_to_patent",
            "company",
            "patent",
            "patent_has_applicant",
            "patent",
            "company",
            "applicant",
            "target",
        ),
        (
            "company_to_professor",
            "company",
            "professor",
            "professor_company_role",
            "professor",
            "company",
            "founder",
            "source",
        ),
        (
            "paper_to_professor",
            "paper",
            "professor",
            "professor_attributed_to_paper",
            "professor",
            "paper",
            None,
            None,
        ),
        (
            "patent_to_company",
            "patent",
            "company",
            "patent_has_applicant",
            "patent",
            "company",
            "applicant",
            "target",
        ),
        (
            "patent_to_professor",
            "patent",
            "professor",
            "patent_has_inventor",
            "patent",
            "professor",
            "inventor",
            "target",
        ),
        (
            "professor_to_company",
            "professor",
            "company",
            "professor_company_role",
            "professor",
            "company",
            "founder",
            "source",
        ),
        (
            "professor_to_paper",
            "professor",
            "paper",
            "professor_attributed_to_paper",
            "professor",
            "paper",
            None,
            None,
        ),
        (
            "professor_to_patent",
            "professor",
            "patent",
            "professor_page_lists_patent",
            "professor",
            "patent",
            None,
            None,
        ),
    )

    for (
        direction,
        requested_source_domain,
        requested_target_domain,
        relationship_type_id,
        canonical_source_domain,
        canonical_target_domain,
        role_id,
        role_endpoint,
    ) in cases:
        canonical_source_id = f"{canonical_source_domain}:{direction}:edge-source"
        canonical_target_id = f"{canonical_target_domain}:{direction}:edge-target"
        endpoint_ids = {
            canonical_source_domain: canonical_source_id,
            canonical_target_domain: canonical_target_id,
        }
        requested_source_id = endpoint_ids[requested_source_domain]
        requested_target_id = endpoint_ids[requested_target_domain]
        requested_source_projection = _projection(
            module,
            domain=requested_source_domain,
            identity_id=requested_source_id,
            fields=("id", "display_name"),
            paper_identity_status=(
                "unverified" if requested_source_domain == "paper" else None
            ),
        )
        target_signal = module.QualitySignal(
            code="target_enrichment_incomplete",
            affected_paths=("verified_relationship_traversal",),
            supporting_assertion_ids=(f"assertion:{requested_target_id}:id",),
        )
        requested_target_projection = _projection(
            module,
            domain=requested_target_domain,
            identity_id=requested_target_id,
            fields=("id", "display_name"),
            quality_signals=(target_signal,),
            paper_identity_status=(
                "unverified" if requested_target_domain == "paper" else None
            ),
        )
        role_bindings = (
            {
                role_id: (
                    canonical_source_id
                    if role_endpoint == "source"
                    else canonical_target_id
                )
            }
            if role_id is not None
            else {}
        )
        relationship = _relationship_decision(
            decision_id=f"relationship-decision:{direction}",
            relationship_type_id=relationship_type_id,
            source_identity_id=canonical_source_id,
            target_identity_id=canonical_target_id,
            state=RelationshipDecisionState.accepted,
            role_bindings=role_bindings,
        )
        inclusion = _inclusion(requested_source_id)
        request = module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
            projection=requested_source_projection,
            related_projections=(requested_target_projection,),
            inclusion_decision=inclusion,
            relationship_decisions=(relationship,),
            requested_traversal_direction=direction,
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )

        result = module.PathEligibilityEngine().evaluate(request)
        traversal = _decisions_by_path(result)["verified_relationship_traversal"]

        assert result.projection_id == requested_source_projection.projection_id
        assert result.inclusion_decision_id == inclusion.decision_id
        assert result.relationship_decision_ids == (relationship.decision_id,)
        assert result.traversal_directions == (direction,)
        assert relationship.source_canonical_identity_id == canonical_source_id
        assert relationship.target_canonical_identity_id == canonical_target_id
        assert traversal.outcome.value == "admitted"
        assert "target_enrichment_incomplete" in traversal.limitations
        assert traversal.hard_exclusion_codes == ()
        assert set(relationship.selected_assertion_ids) <= set(
            traversal.supporting_assertion_ids
        )
        assert {
            assertion_id
            for assertion_ids in requested_target_projection.field_assertion_ids.values()
            for assertion_id in assertion_ids
        } <= set(traversal.supporting_assertion_ids)

    paper_id = "paper:valid-with-rejected-attribution"
    professor_id = "professor:rejected-attribution"
    rejected_attribution = _relationship_decision(
        decision_id="relationship-decision:rejected-professor-paper",
        relationship_type_id="professor_attributed_to_paper",
        source_identity_id=professor_id,
        target_identity_id=paper_id,
        state=RelationshipDecisionState.rejected,
    )
    paper_projection = _projection(
        module,
        domain="paper",
        identity_id=paper_id,
        fields=("title", "year"),
        paper_identity_status="confirmed",
    )
    professor_projection = _projection(
        module,
        domain="professor",
        identity_id=professor_id,
        fields=("name",),
    )
    rejected_request = module.PathEligibilityRequest(
        release_id=RELEASE_ID,
        policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        projection=paper_projection,
        related_projections=(professor_projection,),
        inclusion_decision=_inclusion(paper_id),
        relationship_decisions=(rejected_attribution,),
        requested_traversal_direction="paper_to_professor",
        published_paths=PUBLISHED_USER_PATHS,
        evaluated_at=NOW,
    )

    rejected_result = module.PathEligibilityEngine().evaluate(rejected_request)
    rejected_paths = _decisions_by_path(rejected_result)

    assert rejected_paths["verified_relationship_traversal"].outcome.value == "excluded"
    assert rejected_paths["verified_relationship_traversal"].hard_exclusion_codes == (
        "relationship_not_accepted",
    )
    assert rejected_paths["exact_lookup"].outcome.value == "admitted"
    assert rejected_paths["exact_lookup"].hard_exclusion_codes == ()
    assert rejected_result.relationship_decision_ids == (
        rejected_attribution.decision_id,
    )


def test_ordinary_quality_gaps_are_visible_soft_signals_on_every_path() -> None:
    module = _module()
    identity_id = "professor:soft-quality"
    signals = (
        module.QualitySignal(
            code="missing_optional_enrichment",
            affected_paths=("semantic_recall", "recommendation", "ranking"),
            supporting_assertion_ids=(f"assertion:{identity_id}:name",),
        ),
        module.QualitySignal(
            code="partial_summary",
            affected_paths=("exact_lookup", "semantic_recall"),
            supporting_assertion_ids=(f"assertion:{identity_id}:name",),
        ),
        module.QualitySignal(
            code="ordinary_uncertainty",
            affected_paths=(
                "structured_filter",
                "verified_relationship_traversal",
            ),
            supporting_assertion_ids=(f"assertion:{identity_id}:institution",),
        ),
        module.QualitySignal(
            code="stale_non_material_field",
            affected_paths=PUBLISHED_USER_PATHS,
            supporting_assertion_ids=(f"assertion:{identity_id}:institution",),
        ),
    )
    projection = _projection(
        module,
        domain="professor",
        identity_id=identity_id,
        fields=("name", "institution", "research_directions"),
        quality_signals=signals,
    )
    inclusion = _inclusion(identity_id)
    request = module.PathEligibilityRequest(
        release_id=RELEASE_ID,
        policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        projection=projection,
        inclusion_decision=inclusion,
        relationship_decisions=(),
        published_paths=PUBLISHED_USER_PATHS,
        evaluated_at=NOW,
    )

    result = module.PathEligibilityEngine().evaluate(request)
    decisions = _decisions_by_path(result)
    visible_codes = {
        code for decision in decisions.values() for code in decision.limitations
    } | {gap.code for gap in result.gaps}

    assert result.inclusion_decision_id == inclusion.decision_id
    assert all(
        decision.outcome.value in {"admitted", "limited", "review"}
        for decision in decisions.values()
    )
    assert all(not decision.hard_exclusion_codes for decision in decisions.values())
    assert {signal.code for signal in signals} <= visible_codes


def test_named_hard_exclusions_cover_every_path_and_merge_redirects() -> None:
    module = _module()
    object_level_hard_exclusions = (
        ("wrong_identity", False),
        ("terminal_rejection", False),
        ("unsafe_exposure", True),
        ("no_usable_source_grounded_facts", True),
    )

    for code, has_current_projection in object_level_hard_exclusions:
        identity_id = f"paper:{code}"
        evidence_id = f"assertion:{identity_id}:hard-invariant"
        fields = () if code == "no_usable_source_grounded_facts" else ("title",)
        current_projection = (
            _projection(
                module,
                domain="paper",
                identity_id=identity_id,
                fields=fields,
                paper_identity_status="confirmed",
            )
            if has_current_projection
            else None
        )
        invariant = module.HardInvariantDecisionInput(
            decision_id=f"hard-invariant:{identity_id}",
            code=code,
            affected_paths=PUBLISHED_USER_PATHS,
            supporting_assertion_ids=(evidence_id,),
            release_id=RELEASE_ID,
        )
        request = module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
            referenced_identity_id=identity_id,
            projection=current_projection,
            inclusion_decision=(
                _inclusion(identity_id)
                if has_current_projection
                else _excluded_inclusion(identity_id, code)
            ),
            relationship_decisions=(),
            hard_invariant_decisions=(invariant,),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )

        result = module.PathEligibilityEngine().evaluate(request)
        decisions = _decisions_by_path(result)

        assert all(
            decision.outcome.value == "excluded" for decision in decisions.values()
        )
        assert all(
            decision.hard_exclusion_codes == (code,) for decision in decisions.values()
        )
        assert all(not decision.limitations for decision in decisions.values())
        assert all(
            evidence_id in decision.supporting_assertion_ids
            for decision in decisions.values()
        )

    broken_identity_id = "paper:broken-reference"
    broken_evidence_id = f"assertion:{broken_identity_id}:broken-reference"
    broken_projection = _projection(
        module,
        domain="paper",
        identity_id=broken_identity_id,
        fields=("title",),
        paper_identity_status="confirmed",
    )
    broken_invariant = module.HardInvariantDecisionInput(
        decision_id=f"hard-invariant:{broken_identity_id}",
        code="broken_reference",
        affected_paths=("verified_relationship_traversal",),
        supporting_assertion_ids=(broken_evidence_id,),
        release_id=RELEASE_ID,
    )
    broken_request = module.PathEligibilityRequest(
        release_id=RELEASE_ID,
        policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        referenced_identity_id=broken_identity_id,
        projection=broken_projection,
        inclusion_decision=_inclusion(broken_identity_id),
        relationship_decisions=(),
        hard_invariant_decisions=(broken_invariant,),
        published_paths=PUBLISHED_USER_PATHS,
        evaluated_at=NOW,
    )

    broken_result = module.PathEligibilityEngine().evaluate(broken_request)
    broken_paths = _decisions_by_path(broken_result)
    broken_traversal = broken_paths.pop("verified_relationship_traversal")

    assert broken_traversal.outcome.value == "excluded"
    assert broken_traversal.hard_exclusion_codes == ("broken_reference",)
    assert broken_evidence_id in broken_traversal.supporting_assertion_ids
    assert all(
        decision.outcome.value != "excluded" for decision in broken_paths.values()
    )
    assert all(not decision.hard_exclusion_codes for decision in broken_paths.values())

    merged_id = "paper:merged"
    survivor_id = "paper:survivor"
    merge_peer_id = "paper:merge-peer"
    merge_decision = _merge_decision(
        merged_identity_id=merged_id,
        merge_peer_identity_id=merge_peer_id,
        survivor_identity_id=survivor_id,
    )
    survivor = _projection(
        module,
        domain="paper",
        identity_id=survivor_id,
        fields=("title",),
        paper_identity_status="confirmed",
    )
    survivor_inclusion = _inclusion(survivor_id)
    merge_request = module.PathEligibilityRequest(
        release_id=RELEASE_ID,
        policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        referenced_identity_id=merged_id,
        projection=survivor,
        inclusion_decision=survivor_inclusion,
        identity_redirect_decision=merge_decision,
        relationship_decisions=(),
        published_paths=PUBLISHED_USER_PATHS,
        evaluated_at=NOW,
    )

    merge_result = module.PathEligibilityEngine().evaluate(merge_request)
    merge_decisions = _decisions_by_path(merge_result)

    assert merge_result.redirect.source_identity_id == merged_id
    assert merge_result.redirect.survivor_identity_id == survivor_id
    assert merge_result.redirect.identity_decision_id == merge_decision.decision_id
    assert merge_result.resolved_projection_id == survivor.projection_id
    assert merge_result.inclusion_decision_id == survivor_inclusion.decision_id
    assert all(
        decision.subject_identity_id == survivor_id
        for decision in merge_decisions.values()
    )
    assert all(
        "terminal_merge" not in decision.hard_exclusion_codes
        for decision in merge_decisions.values()
    )
    assert merge_result.result_identity_ids == (survivor_id,)


def test_published_paths_are_independent_and_ignore_global_ready_poison() -> None:
    module = _module()
    internal_only_paths = {"audit_lineage", "identity_resolution"}

    assert tuple(module.PUBLISHED_USER_PATHS) == PUBLISHED_USER_PATHS
    assert internal_only_paths.isdisjoint(module.PUBLISHED_USER_PATHS)

    identity_id = "professor:path-independence"
    inclusion = _inclusion(identity_id)

    def projection(poison: str) -> Any:
        return _projection(
            module,
            domain="professor",
            identity_id=identity_id,
            fields=(
                "name",
                "institution",
                "research_directions",
                "profile_summary",
            ),
            diagnostic_metadata={"legacy_global_ready_poison": poison},
        )

    def evaluate(value: Any) -> Any:
        request = module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
            projection=value,
            inclusion_decision=inclusion,
            relationship_decisions=(),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )
        return module.PathEligibilityEngine().evaluate(request)

    ready_result = evaluate(projection("ready"))
    rejected_result = evaluate(projection("rejected"))
    decisions = _decisions_by_path(ready_result)

    assert ready_result.inclusion_decision_id == inclusion.decision_id
    assert inclusion.policy.policy_kind.value == "inclusion"
    assert inclusion.path is None
    assert len({decision.decision_id for decision in decisions.values()}) == len(
        PUBLISHED_USER_PATHS
    )
    assert all(
        decision.policy.policy_kind.value == "path_eligibility"
        for decision in decisions.values()
    )
    assert all(
        decision.policy.policy_version == "path-eligibility-v1"
        for decision in decisions.values()
    )
    assert all(decision.path == path for path, decision in decisions.items())
    assert all(decision.release_id == RELEASE_ID for decision in decisions.values())
    assert all(
        decision.subject_identity_id == identity_id for decision in decisions.values()
    )
    assert ready_result.decisions == rejected_result.decisions
    assert ready_result.gaps == rejected_result.gaps


def test_request_rejects_policy_release_subject_path_and_evidence_cross_wires() -> None:
    module = _module()
    identity_id = "professor:integrity"
    projection = _projection(
        module,
        domain="professor",
        identity_id=identity_id,
        fields=("name",),
    )
    inclusion = _inclusion(identity_id)
    values = {
        "release_id": RELEASE_ID,
        "policy": _policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        "projection": projection,
        "inclusion_decision": inclusion,
        "relationship_decisions": (),
        "published_paths": PUBLISHED_USER_PATHS,
        "evaluated_at": NOW,
    }
    bad_signal = module.QualitySignal(
        code="cross-wired-quality",
        affected_paths=("exact_lookup",),
        supporting_assertion_ids=("assertion:other:name",),
    )
    invalid_cases = (
        (
            {"policy": _policy(PolicyKind.inclusion, "path-eligibility-v1")},
            "path-eligibility policy",
        ),
        (
            {
                "projection": projection.model_copy(
                    update={"release_id": "other-release"}
                )
            },
            "projection release",
        ),
        (
            {
                "inclusion_decision": inclusion.model_copy(
                    update={"subject_identity_id": "professor:other"}
                )
            },
            "resolved identity",
        ),
        (
            {"published_paths": PUBLISHED_USER_PATHS[:-1]},
            "published paths",
        ),
        (
            {
                "inclusion_decision": inclusion.model_copy(
                    update={"supporting_assertion_ids": ()}
                )
            },
            "inclusion decision requires evidence",
        ),
        (
            {
                "projection": projection.model_copy(
                    update={"quality_signals": (bad_signal,)}
                )
            },
            "quality signals require projection assertion lineage",
        ),
    )
    for update, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            module.PathEligibilityRequest.model_validate({**values, **update})


def test_request_rejects_duplicate_quality_codes_and_cross_wired_topology() -> None:
    module = _module()
    professor_id = "professor:topology"
    company_id = "company:topology"
    professor_signal = module.QualitySignal(
        code="duplicate-quality",
        affected_paths=("verified_relationship_traversal",),
        supporting_assertion_ids=(f"assertion:{professor_id}:name",),
    )
    company_signal = module.QualitySignal(
        code="duplicate-quality",
        affected_paths=("verified_relationship_traversal",),
        supporting_assertion_ids=(f"assertion:{company_id}:name",),
    )
    professor = _projection(
        module,
        domain="professor",
        identity_id=professor_id,
        fields=("name",),
        quality_signals=(professor_signal,),
    )
    company = _projection(
        module,
        domain="company",
        identity_id=company_id,
        fields=("name",),
        quality_signals=(company_signal,),
    )
    relationship = _relationship_decision(
        decision_id="relationship-decision:topology",
        relationship_type_id="professor_company_role",
        source_identity_id=professor_id,
        target_identity_id=company_id,
        state=RelationshipDecisionState.accepted,
        role_bindings={"founder": professor_id},
    )
    values = {
        "release_id": RELEASE_ID,
        "policy": _policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
        "projection": professor,
        "related_projections": (company,),
        "inclusion_decision": _inclusion(professor_id),
        "relationship_decisions": (relationship,),
        "requested_traversal_direction": "professor_to_company",
        "published_paths": PUBLISHED_USER_PATHS,
        "evaluated_at": NOW,
    }
    with pytest.raises(ValueError, match="quality signal codes"):
        module.PathEligibilityRequest.model_validate(values)

    clean_values = {
        **values,
        "projection": professor.model_copy(update={"quality_signals": ()}),
        "related_projections": (company.model_copy(update={"quality_signals": ()}),),
    }
    cross_wired_relationship = relationship.model_copy(
        update={
            "source_canonical_identity_id": company_id,
            "target_canonical_identity_id": professor_id,
        }
    )
    with pytest.raises(ValueError, match="catalog orientation"):
        module.PathEligibilityRequest.model_validate(
            {
                **clean_values,
                "relationship_decisions": (cross_wired_relationship,),
            }
        )

    with pytest.raises(ValueError, match="require a requested traversal"):
        module.PathEligibilityRequest.model_validate(
            {
                **clean_values,
                "requested_traversal_direction": None,
            }
        )

    survivor_id = "paper:topology-survivor"
    survivor = _projection(
        module,
        domain="paper",
        identity_id=survivor_id,
        fields=("title",),
        paper_identity_status="confirmed",
    )
    redirect = _merge_decision(
        merged_identity_id="paper:topology-merged",
        merge_peer_identity_id="paper:topology-peer",
        survivor_identity_id=survivor_id,
    ).model_copy(update={"output_canonical_identity_ids": ("paper:wrong",)})
    with pytest.raises(ValueError, match="one exact merge survivor"):
        module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=values["policy"],
            referenced_identity_id="paper:topology-merged",
            projection=survivor,
            inclusion_decision=_inclusion(survivor_id),
            identity_redirect_decision=redirect,
            relationship_decisions=(),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )


def test_path_decision_identity_binds_complete_policy_content() -> None:
    module = _module()
    identity_id = "professor:policy-identity"
    projection = _projection(
        module,
        domain="professor",
        identity_id=identity_id,
        fields=("name",),
    )
    inclusion = _inclusion(identity_id)
    policy = _policy(PolicyKind.path_eligibility, "path-eligibility-v1")

    def evaluate(value: PolicyReference) -> Any:
        return module.PathEligibilityEngine().evaluate(
            module.PathEligibilityRequest(
                release_id=RELEASE_ID,
                policy=value,
                projection=projection,
                inclusion_decision=inclusion,
                relationship_decisions=(),
                published_paths=PUBLISHED_USER_PATHS,
                evaluated_at=NOW,
            )
        )

    baseline = evaluate(policy)
    changed = evaluate(
        policy.model_copy(
            update={
                "policy_id": "canonical-v2-path-eligibility-alternate",
                "content_sha256": "7" * 64,
            }
        )
    )

    assert {decision.decision_id for decision in baseline.decisions}.isdisjoint(
        decision.decision_id for decision in changed.decisions
    )
    tampered = baseline.model_copy(update={"content_sha256": "0" * 64})
    with pytest.raises(ValueError, match="content_sha256"):
        module.PathEligibilityResult.model_validate(tampered.model_dump(mode="python"))


def test_inclusion_review_never_promotes_an_identity_without_current_projection() -> (
    None
):
    module = _module()
    identity_id = "company:inclusion-review"
    inclusion = PolicyDecision(
        decision_id=f"inclusion:{identity_id}",
        policy=_policy(PolicyKind.inclusion, "domain-inclusion-v1"),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.review,
        score=None,
        limitations=("company_scope_requires_review",),
        hard_exclusion_codes=(),
        supporting_assertion_ids=(f"assertion:{identity_id}:scope",),
        evaluated_at=NOW,
    )
    result = module.PathEligibilityEngine().evaluate(
        module.PathEligibilityRequest(
            release_id=RELEASE_ID,
            policy=_policy(PolicyKind.path_eligibility, "path-eligibility-v1"),
            referenced_identity_id=identity_id,
            projection=None,
            inclusion_decision=inclusion,
            relationship_decisions=(),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )
    )

    assert result.projection_id is None
    assert result.result_identity_ids == ()
    assert all(
        decision.outcome is PolicyOutcome.review for decision in result.decisions
    )
    assert all(
        "company_scope_requires_review" in decision.limitations
        for decision in result.decisions
    )
