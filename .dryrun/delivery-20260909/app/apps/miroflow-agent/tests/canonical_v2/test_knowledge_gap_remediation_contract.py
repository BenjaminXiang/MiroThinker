from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module
import json
from typing import Any

import pytest
from pydantic import ValidationError


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_gap_feedback"
CONTRACTS_MODULE = "src.data_agents.canonical_v2.contracts"
GAP_CREATED_AT = datetime(2026, 7, 15, 1, 0, tzinfo=UTC)
REMEDIATION_STARTED_AT = GAP_CREATED_AT + timedelta(hours=1)
REMEDIATION_COMPLETED_AT = REMEDIATION_STARTED_AT + timedelta(minutes=20)
RELEASE_VERIFIED_AT = REMEDIATION_COMPLETED_AT + timedelta(minutes=20)
EFFECT_VERIFIED_AT = RELEASE_VERIFIED_AT + timedelta(minutes=10)
REQUESTED_AT = EFFECT_VERIFIED_AT + timedelta(minutes=5)
TRANSITIONED_AT = REQUESTED_AT + timedelta(minutes=5)
SOURCE_RELEASE_ID = "release-r1"
RESOLVING_RELEASE_ID = "release-r2"
BUILD_RUN_ID = "build-run:gap-remediation"
MANIFEST_SHA256 = "a" * 64


class _MissingKnowledgeGapRemediationContract(RuntimeError):
    """Exact Task 10.3 RED sentinel; nested implementation failures stay real."""


def _remediation_module() -> Any:
    module = import_module(TARGET_MODULE)
    required_symbols = (
        "GapEffectVerification",
        "GapRemediationRequest",
        "GapRemediationResult",
        "OfflineRemediationReceipt",
    )
    missing = tuple(
        symbol for symbol in required_symbols if not hasattr(module, symbol)
    )
    if not hasattr(module.KnowledgeGapFeedback, "apply_remediation"):
        missing += ("KnowledgeGapFeedback.apply_remediation",)
    if missing:
        raise _MissingKnowledgeGapRemediationContract(
            "exact Task 10.3 remediation contract is absent: " + ", ".join(missing)
        )
    return module


def _contracts() -> Any:
    return import_module(CONTRACTS_MODULE)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _content_bound(module: Any, model_name: str, payload: dict[str, Any]) -> Any:
    model = getattr(module, model_name)
    normalized = model.model_construct(
        **payload,
        content_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"content_sha256"})
    return model(
        **payload,
        content_sha256=_canonical_sha256(normalized),
    )


def _open_gap(module: Any) -> Any:
    signal = module.GapSignal(
        signal_id="signal:missing-relationship",
        trigger="missing_relationship",
        release_id=SOURCE_RELEASE_ID,
        affected_domains=("professor", "paper"),
        affected_paths=("professor_attributed_to_paper",),
        query_trace_id="query-trace:missing-relationship",
        answer_trace_id="answer-trace:missing-relationship",
        benchmark_case_id="case:missing-relationship",
        telemetry_key=None,
        observed_symptom="The source-grounded Professor-Paper path is missing.",
        evidence_ids=("evidence:professor", "evidence:paper"),
        demand_observation_ids=("demand:1",),
        observed_at=GAP_CREATED_AT,
    )
    return module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: GAP_CREATED_AT
    ).record(signal)


def _candidate(
    contracts: Any,
    *,
    state: str,
    release_id: str = RESOLVING_RELEASE_ID,
    run_id: str = BUILD_RUN_ID,
    source_batch_ids: tuple[str, ...] = ("source-batch:gap-remediation",),
    manifest_sha256: str = MANIFEST_SHA256,
) -> Any:
    return contracts.CandidateRelease(
        release_id=release_id,
        run_id=run_id,
        state=state,
        source_batch_ids=source_batch_ids,
        parser_versions={"offline-remediation": "parser-v1"},
        policy_versions={"gap-remediation": "gap-remediation-v1"},
        model_versions={},
        manifest_sha256=manifest_sha256,
        object_counts={"professor": 1, "paper": 1},
        relationship_count=1,
        active_release_changed=False,
    )


def _release_verification(
    contracts: Any,
    *,
    accepted: bool,
    release_id: str = RESOLVING_RELEASE_ID,
    manifest_sha256: str = MANIFEST_SHA256,
    verified_at: datetime = RELEASE_VERIFIED_AT,
) -> Any:
    return contracts.ReleaseVerification(
        candidate_release_id=release_id,
        manifest_sha256=manifest_sha256,
        accepted=accepted,
        canonical_index_parity=accepted,
        missing_points=0 if accepted else 1,
        extra_points=0,
        stale_points=0,
        cross_release_points=0,
        evidence_ids=("verification:release-parity",),
        verified_at=verified_at,
    )


def _receipt(
    module: Any,
    gap: Any,
    *,
    remediation_kind: str = "relationship_repair",
    execution_mode: str = "offline",
    gap_id: str | None = None,
    source_release_id: str = SOURCE_RELEASE_ID,
    candidate_release_id: str = RESOLVING_RELEASE_ID,
    build_run_id: str = BUILD_RUN_ID,
    affected_domains: tuple[str, ...] | None = None,
    affected_paths: tuple[str, ...] | None = None,
    offline_run_id: str | None = None,
    source_batch_ids: tuple[str, ...] = ("source-batch:gap-remediation",),
    landing_artifact_ids: tuple[str, ...] = ("artifact:gap-remediation",),
    review_state: str = "accepted",
    review_evidence_ids: tuple[str, ...] = ("review:offline-remediation",),
    started_at: datetime = REMEDIATION_STARTED_AT,
    completed_at: datetime = REMEDIATION_COMPLETED_AT,
) -> Any:
    payload = {
        "receipt_id": f"remediation:{remediation_kind}",
        "gap_id": gap_id or gap.gap_id,
        "remediation_kind": remediation_kind,
        "execution_mode": execution_mode,
        "source_release_id": source_release_id,
        "candidate_release_id": candidate_release_id,
        "affected_domains": affected_domains or gap.affected_domains,
        "affected_paths": affected_paths or gap.affected_paths,
        "offline_run_id": offline_run_id or f"offline-run:{remediation_kind}",
        "source_batch_ids": source_batch_ids,
        "landing_artifact_ids": landing_artifact_ids,
        "build_run_id": build_run_id,
        "review_state": review_state,
        "review_evidence_ids": review_evidence_ids,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    return _content_bound(module, "OfflineRemediationReceipt", payload)


def _effect_verification(
    module: Any,
    gap: Any,
    *,
    accepted: bool,
    gap_id: str | None = None,
    release_id: str = RESOLVING_RELEASE_ID,
    affected_domains: tuple[str, ...] | None = None,
    affected_paths: tuple[str, ...] | None = None,
    scenario_ids: tuple[str, ...] | None = None,
    query_trace_id: str | None = None,
    answer_trace_id: str | None = None,
    benchmark_case_id: str | None = None,
    evidence_ids: tuple[str, ...] = ("verification:intended-effect",),
    verified_at: datetime = EFFECT_VERIFIED_AT,
) -> Any:
    payload = {
        "verification_id": "effect-verification:missing-relationship",
        "gap_id": gap_id or gap.gap_id,
        "release_id": release_id,
        "affected_domains": affected_domains or gap.affected_domains,
        "affected_paths": affected_paths or gap.affected_paths,
        "query_trace_id": query_trace_id or gap.query_trace_id,
        "answer_trace_id": answer_trace_id or gap.answer_trace_id,
        "benchmark_case_id": benchmark_case_id or gap.benchmark_case_id,
        "scenario_ids": scenario_ids or (gap.benchmark_case_id,),
        "accepted": accepted,
        "evidence_ids": evidence_ids,
        "verified_at": verified_at,
    }
    return _content_bound(module, "GapEffectVerification", payload)


def _request(
    module: Any,
    *,
    gap: Any,
    remediation_receipt: Any,
    candidate_release: Any,
    release_verification: Any | None,
    effect_verification: Any | None,
    requested_at: datetime = REQUESTED_AT,
) -> Any:
    payload = {
        "request_id": f"gap-transition:{gap.gap_id}:{candidate_release.release_id}",
        "gap": gap,
        "remediation_receipt": remediation_receipt,
        "candidate_release": candidate_release,
        "release_verification": release_verification,
        "effect_verification": effect_verification,
        "requested_at": requested_at,
    }
    return _content_bound(module, "GapRemediationRequest", payload)


def _unsafe_copy(model: Any, **updates: Any) -> Any:
    payload = {field: getattr(model, field) for field in type(model).model_fields}
    payload.update(updates)
    return type(model).model_construct(**payload)


def _unsafe_content_bound_copy(model: Any, **updates: Any) -> Any:
    payload = {
        field: getattr(model, field)
        for field in type(model).model_fields
        if field != "content_sha256"
    }
    payload.update(updates)
    normalized = (
        type(model)
        .model_construct(
            **payload,
            content_sha256="0" * 64,
        )
        .model_dump(mode="json", exclude={"content_sha256"})
    )
    return type(model).model_construct(
        **payload,
        content_sha256=_canonical_sha256(normalized),
    )


def _preserved_gap_fields(gap: Any) -> dict[str, Any]:
    return gap.model_dump(
        mode="python",
        exclude={
            "status",
            "review_state",
            "updated_at",
            "resolved_release_id",
            "resolved_release_state",
            "resolution_verification_ids",
        },
    )


def _assert_transition_identity(result: Any, request: Any) -> None:
    normalized = result.model_dump(
        mode="json",
        exclude={"content_sha256", "transition_id"},
    )
    expected_sha256 = _canonical_sha256(normalized)
    assert result.remediation_input_sha256 == request.content_sha256
    assert result.content_sha256 == expected_sha256
    assert result.transition_id
    assert type(result).model_validate(result.model_dump(mode="python")) == result


def test_reviewed_offline_relationship_repair_links_without_premature_closure() -> None:
    module = _remediation_module()
    contracts = _contracts()
    feedback = module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: TRANSITIONED_AT
    )
    gap = _open_gap(module)
    receipt = _receipt(module, gap, remediation_kind="relationship_repair")
    candidate = _candidate(contracts, state="candidate")
    request = _request(
        module,
        gap=gap,
        remediation_receipt=receipt,
        candidate_release=candidate,
        release_verification=None,
        effect_verification=None,
    )

    result = feedback.apply_remediation(request)

    assert isinstance(result, module.GapRemediationResult)
    assert result.transition_state == "linked"
    assert result.remediation_receipt == receipt
    assert result.release_verification is None
    assert result.effect_verification is None
    assert result.gap.gap_id == gap.gap_id
    assert _preserved_gap_fields(result.gap) == _preserved_gap_fields(gap)
    assert result.gap.status in {"open", "in_review", "planned"}
    assert result.gap.review_state in {"unreviewed", "in_review"}
    assert result.gap.resolved_release_id is None
    assert result.gap.resolved_release_state is None
    assert result.gap.resolution_verification_ids == ()
    assert result.gap.created_at == gap.created_at
    assert result.gap.updated_at == TRANSITIONED_AT
    _assert_transition_identity(result, request)

    repeated = feedback.apply_remediation(request)
    assert repeated == result

    ticks = iter((TRANSITIONED_AT, TRANSITIONED_AT + timedelta(seconds=1)))
    advancing_feedback = module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: next(ticks)
    )
    first_replay = advancing_feedback.apply_remediation(request)
    assert advancing_feedback.apply_remediation(request) == first_replay

    alternate_receipt = _receipt(
        module,
        gap,
        remediation_kind="relationship_repair",
        offline_run_id="offline-run:relationship-repair:alternate",
    )
    alternate_request = _request(
        module,
        gap=gap,
        remediation_receipt=alternate_receipt,
        candidate_release=candidate,
        release_verification=None,
        effect_verification=None,
    )
    alternate = feedback.apply_remediation(alternate_request)
    _assert_transition_identity(alternate, alternate_request)
    assert alternate.transition_id != result.transition_id
    assert alternate.content_sha256 != result.content_sha256


def test_only_exact_accepted_release_and_intended_effect_resolve_the_gap() -> None:
    module = _remediation_module()
    contracts = _contracts()
    feedback = module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: TRANSITIONED_AT
    )
    gap = _open_gap(module)
    receipt = _receipt(module, gap)
    accepted_candidate = _candidate(contracts, state="accepted")
    accepted_release = _release_verification(contracts, accepted=True)
    accepted_effect = _effect_verification(module, gap, accepted=True)
    request = _request(
        module,
        gap=gap,
        remediation_receipt=receipt,
        candidate_release=accepted_candidate,
        release_verification=accepted_release,
        effect_verification=accepted_effect,
    )

    result = feedback.apply_remediation(request)

    assert result.transition_state == "resolved"
    assert result.remediation_receipt == receipt
    assert result.release_verification == accepted_release
    assert result.effect_verification == accepted_effect
    assert result.gap.gap_id == gap.gap_id
    assert _preserved_gap_fields(result.gap) == _preserved_gap_fields(gap)
    assert result.gap.status == "resolved"
    assert result.gap.review_state == "accepted"
    assert result.gap.resolved_release_id == RESOLVING_RELEASE_ID
    assert result.gap.resolved_release_state == "accepted"
    assert result.gap.resolution_verification_ids == (
        "verification:release-parity",
        "verification:intended-effect",
    )
    assert result.gap.updated_at == TRANSITIONED_AT
    assert result.gap.created_at == gap.created_at
    _assert_transition_identity(result, request)
    repeated = feedback.apply_remediation(request)
    assert repeated == result

    alternate_effect = _effect_verification(
        module,
        gap,
        accepted=True,
        evidence_ids=("verification:intended-effect:alternate",),
    )
    alternate_request = _request(
        module,
        gap=gap,
        remediation_receipt=receipt,
        candidate_release=accepted_candidate,
        release_verification=accepted_release,
        effect_verification=alternate_effect,
    )
    alternate = feedback.apply_remediation(alternate_request)
    _assert_transition_identity(alternate, alternate_request)
    assert alternate.transition_id != result.transition_id
    assert alternate.content_sha256 != result.content_sha256

    original_gap = gap.model_dump(mode="python")
    for release_state in ("candidate", "verified", "rejected"):
        invalid_request = _request(
            module,
            gap=gap,
            remediation_receipt=receipt,
            candidate_release=_candidate(contracts, state=release_state),
            release_verification=accepted_release,
            effect_verification=accepted_effect,
        )
        with pytest.raises(ValueError):
            feedback.apply_remediation(invalid_request)
        assert gap.model_dump(mode="python") == original_gap

    for release_verification, effect_verification in (
        (None, accepted_effect),
        (accepted_release, None),
        (_release_verification(contracts, accepted=False), accepted_effect),
        (accepted_release, _effect_verification(module, gap, accepted=False)),
    ):
        invalid_request = _request(
            module,
            gap=gap,
            remediation_receipt=receipt,
            candidate_release=accepted_candidate,
            release_verification=release_verification,
            effect_verification=effect_verification,
        )
        with pytest.raises(ValueError):
            feedback.apply_remediation(invalid_request)
        assert gap.model_dump(mode="python") == original_gap

    for execution_mode in ("current_web", "model_output"):
        online_receipt = _unsafe_content_bound_copy(
            receipt,
            execution_mode=execution_mode,
        )
        online_request = _unsafe_content_bound_copy(
            request,
            remediation_receipt=online_receipt,
        )
        with pytest.raises(ValueError):
            feedback.apply_remediation(online_request)
        assert gap.model_dump(mode="python") == original_gap


def test_cross_wired_stale_tampered_and_caller_resolved_inputs_fail_closed() -> None:
    module = _remediation_module()
    contracts = _contracts()
    feedback = module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: TRANSITIONED_AT
    )
    gap = _open_gap(module)
    receipt = _receipt(module, gap)
    accepted_candidate = _candidate(contracts, state="accepted")
    accepted_release = _release_verification(contracts, accepted=True)
    accepted_effect = _effect_verification(module, gap, accepted=True)
    request = _request(
        module,
        gap=gap,
        remediation_receipt=receipt,
        candidate_release=accepted_candidate,
        release_verification=accepted_release,
        effect_verification=accepted_effect,
    )
    wrong_domains = ("company",)
    wrong_path = ("company_has_product",)
    cross_wired_receipts = (
        _receipt(module, gap, gap_id="gap:other"),
        _receipt(module, gap, source_release_id="release:other"),
        _receipt(module, gap, candidate_release_id="release:other"),
        _receipt(module, gap, affected_domains=wrong_domains),
        _receipt(module, gap, build_run_id="build-run:other"),
        _receipt(module, gap, affected_paths=wrong_path),
        _receipt(
            module,
            gap,
            source_batch_ids=("source-batch:other",),
        ),
        _unsafe_content_bound_copy(receipt, offline_run_id=""),
        _unsafe_content_bound_copy(receipt, landing_artifact_ids=()),
        _unsafe_content_bound_copy(receipt, review_state="rejected"),
        _unsafe_content_bound_copy(receipt, review_evidence_ids=()),
        _unsafe_content_bound_copy(
            receipt,
            started_at=REMEDIATION_COMPLETED_AT + timedelta(seconds=1),
        ),
        _receipt(
            module,
            gap,
            started_at=GAP_CREATED_AT - timedelta(seconds=1),
        ),
        _unsafe_copy(receipt, content_sha256="f" * 64),
    )
    cross_wired_effects = (
        _effect_verification(module, gap, accepted=True, gap_id="gap:other"),
        _effect_verification(module, gap, accepted=True, release_id="release:other"),
        _effect_verification(
            module,
            gap,
            accepted=True,
            affected_domains=wrong_domains,
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            affected_paths=wrong_path,
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            scenario_ids=("case:other",),
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            query_trace_id="query-trace:other",
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            answer_trace_id="answer-trace:other",
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            benchmark_case_id="case:other",
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            verified_at=RELEASE_VERIFIED_AT,
        ),
        _effect_verification(
            module,
            gap,
            accepted=True,
            verified_at=RELEASE_VERIFIED_AT - timedelta(seconds=1),
        ),
        _unsafe_copy(accepted_effect, content_sha256="e" * 64),
        _unsafe_content_bound_copy(
            accepted_effect,
            evidence_ids=(
                "verification:intended-effect",
                "verification:intended-effect",
            ),
        ),
    )
    cross_wired_candidates = (
        _candidate(contracts, state="accepted", release_id="release:other"),
        _candidate(contracts, state="accepted", run_id="build-run:other"),
        _candidate(
            contracts,
            state="accepted",
            source_batch_ids=("source-batch:other",),
        ),
        _candidate(
            contracts,
            state="accepted",
            manifest_sha256="b" * 64,
        ),
    )
    cross_wired_release_verifications = (
        _release_verification(
            contracts,
            accepted=True,
            release_id="release:other",
        ),
        _release_verification(
            contracts,
            accepted=True,
            manifest_sha256="b" * 64,
        ),
        _release_verification(
            contracts,
            accepted=True,
            verified_at=REMEDIATION_COMPLETED_AT - timedelta(seconds=1),
        ),
    )
    same_release_candidate = _candidate(
        contracts,
        state="accepted",
        release_id=SOURCE_RELEASE_ID,
    )
    same_release_request = _request(
        module,
        gap=gap,
        remediation_receipt=_receipt(
            module,
            gap,
            candidate_release_id=SOURCE_RELEASE_ID,
        ),
        candidate_release=same_release_candidate,
        release_verification=_release_verification(
            contracts,
            accepted=True,
            release_id=SOURCE_RELEASE_ID,
        ),
        effect_verification=_effect_verification(
            module,
            gap,
            accepted=True,
            release_id=SOURCE_RELEASE_ID,
        ),
    )
    stale_gap = type(gap).model_validate(
        {
            **gap.model_dump(mode="python"),
            "status": "planned",
            "review_state": "in_review",
            "updated_at": TRANSITIONED_AT + timedelta(seconds=1),
        }
    )
    stale_request = _request(
        module,
        gap=stale_gap,
        remediation_receipt=_receipt(module, stale_gap),
        candidate_release=accepted_candidate,
        release_verification=accepted_release,
        effect_verification=_effect_verification(
            module,
            stale_gap,
            accepted=True,
        ),
    )

    original_gap = gap.model_dump(mode="python")
    invalid_requests = [
        _unsafe_content_bound_copy(
            request,
            remediation_receipt=invalid_receipt,
        )
        for invalid_receipt in cross_wired_receipts
    ]
    invalid_requests.extend(
        _unsafe_content_bound_copy(
            request,
            effect_verification=invalid_effect,
        )
        for invalid_effect in cross_wired_effects
    )
    invalid_requests.extend(
        _unsafe_content_bound_copy(
            request,
            candidate_release=invalid_candidate,
        )
        for invalid_candidate in cross_wired_candidates
    )
    invalid_requests.extend(
        _unsafe_content_bound_copy(
            request,
            release_verification=invalid_verification,
        )
        for invalid_verification in cross_wired_release_verifications
    )
    invalid_requests.extend(
        (
            same_release_request,
            stale_request,
            _unsafe_content_bound_copy(
                request,
                requested_at=EFFECT_VERIFIED_AT - timedelta(seconds=1),
            ),
            _unsafe_copy(request, content_sha256="d" * 64),
        )
    )

    for invalid_request in invalid_requests:
        with pytest.raises(ValueError):
            feedback.apply_remediation(invalid_request)
        assert gap.model_dump(mode="python") == original_gap

    early_feedback = module.create_ephemeral_knowledge_gap_feedback(
        clock=lambda: REQUESTED_AT - timedelta(seconds=1)
    )
    with pytest.raises(ValueError):
        early_feedback.apply_remediation(request)
    assert gap.model_dump(mode="python") == original_gap

    with pytest.raises(ValidationError):
        module.GapRemediationRequest(
            **{
                **request.model_dump(mode="python"),
                "resolved_gap": gap.model_copy(
                    update={
                        "status": "resolved",
                        "review_state": "accepted",
                        "resolved_release_id": RESOLVING_RELEASE_ID,
                        "resolved_release_state": "accepted",
                        "resolution_verification_ids": ("caller:invented-resolution",),
                    }
                ),
            }
        )
