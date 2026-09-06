from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import CanonicalIdentity
from src.data_agents.canonical_v2.contracts import CanonicalIdentityState
from src.data_agents.canonical_v2.contracts import EvidenceArtifact
from src.data_agents.canonical_v2.contracts import ParseStatus
from src.data_agents.canonical_v2.contracts import (
    PolicyDecision as SharedPolicyDecision,
)
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import (
    PolicyReference as SharedPolicyReference,
)
from src.data_agents.canonical_v2.contracts import SourceAssertion
from src.data_agents.canonical_v2.contracts import SourceIdentity
from src.data_agents.canonical_v2.contracts import SourceIdentityState
from src.data_agents.canonical_v2.contracts import SourceRecord


TARGET_MODULE = "src.data_agents.canonical_v2.domain_inclusion"
NOW = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s6-domain-r1"
RUN_ID = "domain-inclusion-run-1"


class _MissingTargetModule(RuntimeError):
    """Exact Task 6.2 RED sentinel; nested missing dependencies fail normally."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingTargetModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _assert_shared_policy_reexports(module: Any) -> None:
    assert module.PolicyReference is SharedPolicyReference
    assert module.PolicyDecision is SharedPolicyDecision


def _policy(domain: str) -> SharedPolicyReference:
    policy_hashes = {
        "company": "1" * 64,
        "paper": "2" * 64,
        "patent": "3" * 64,
        "professor": "4" * 64,
    }
    return SharedPolicyReference(
        policy_id=f"canonical-v2-{domain}-inclusion",
        policy_version=f"{domain}-inclusion-v1",
        policy_kind=PolicyKind.inclusion,
        content_sha256=policy_hashes[domain],
        effective_at=NOW - timedelta(days=1),
    )


def _source_record(
    *,
    record_id: str,
    source_batch_id: str,
    artifact_id: str,
    payload: dict[str, Any],
) -> SourceRecord:
    return SourceRecord(
        record_id=record_id,
        artifact_id=artifact_id,
        source_batch_id=source_batch_id,
        record_locator=f"row:{record_id}",
        parser_name="recorded-domain-fixture",
        parser_version="v1",
        schema_version="domain-source-v1",
        parse_run_id="parse-domain-fixture-1",
        parse_status=ParseStatus.parsed,
        payload=payload,
        parsed_at=NOW - timedelta(hours=2),
    )


def _artifact(
    *,
    artifact_id: str,
    content_sha256: str,
    source_kind: str = "offline_fixture",
) -> EvidenceArtifact:
    return EvidenceArtifact(
        artifact_id=artifact_id,
        source_kind=source_kind,
        source_locator=f"fixture://{artifact_id}",
        content_sha256=content_sha256,
        byte_size=128,
        acquired_at=NOW - timedelta(hours=3),
        run_id="landing-domain-fixture-1",
    )


def _source_identity(
    *,
    source_identity_id: str,
    entity_type: str,
    record_id: str,
    source_key: str,
) -> SourceIdentity:
    return SourceIdentity(
        source_identity_id=source_identity_id,
        source_system="recorded-domain-fixture",
        source_key=source_key,
        entity_type=entity_type,
        source_record_ids=(record_id,),
        normalized_keys={"source_key": source_key},
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW - timedelta(hours=1),
        state=SourceIdentityState.active,
    )


def _canonical_identity(
    *,
    canonical_identity_id: str,
    entity_type: str,
    source_identity_id: str,
) -> CanonicalIdentity:
    return CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state=CanonicalIdentityState.active,
        display_name=f"Display {canonical_identity_id}",
        source_identity_ids=(source_identity_id,),
        identity_decision_id=f"identity-decision:{canonical_identity_id}",
        release_id=RELEASE_ID,
    )


def _assertion(
    *,
    assertion_id: str,
    source_identity: SourceIdentity,
    field_path: str,
    value: Any,
) -> SourceAssertion:
    return SourceAssertion(
        assertion_id=assertion_id,
        source_record_id=source_identity.source_record_ids[0],
        source_identity_id=source_identity.source_identity_id,
        subject_entity_type=source_identity.entity_type,
        field_path=field_path,
        value=value,
        observed_at=NOW - timedelta(hours=1),
        assertion_run_id="domain-assertion-run-1",
    )


def _approved_manifest(
    module: Any,
    *entries: tuple[str, str, str, str, str],
) -> Any:
    manifest = module.create_approved_source_scope_manifest(
        manifest_version="approved-domain-source-scope-v1",
        approved_batches=tuple(
            module.ApprovedSourceBatch(
                domain=domain,
                scope_kind=scope_kind,
                source_batch_id=source_batch_id,
                artifact_id=artifact_id,
                artifact_content_sha256=content_sha256,
            )
            for domain, scope_kind, source_batch_id, artifact_id, content_sha256 in entries
        ),
        created_at=NOW - timedelta(hours=3),
    )
    assert len(manifest.content_sha256) == 64
    assert set(manifest.content_sha256) <= set("0123456789abcdef")
    return manifest


def _candidate(
    module: Any,
    *,
    identity: CanonicalIdentity,
    source_identity: SourceIdentity,
    record: SourceRecord,
    assertions: tuple[SourceAssertion, ...],
    evidence_lane: str = "offline_landing",
    professor_anchor_identity_id: str | None = None,
    incremental_company_validation_decision_id: str | None = None,
) -> Any:
    return module.InclusionCandidate(
        canonical_identity_id=identity.canonical_identity_id,
        domain=identity.entity_type,
        source_identity_ids=(source_identity.source_identity_id,),
        source_record_ids=(record.record_id,),
        supporting_assertion_ids=tuple(
            assertion.assertion_id for assertion in assertions
        ),
        evidence_lane=evidence_lane,
        professor_anchor_identity_id=professor_anchor_identity_id,
        incremental_company_validation_decision_id=(
            incremental_company_validation_decision_id
        ),
    )


def _request(
    module: Any,
    *,
    manifest: Any,
    candidates: tuple[Any, ...],
    identities: tuple[CanonicalIdentity, ...],
    source_identities: tuple[SourceIdentity, ...],
    artifacts: tuple[EvidenceArtifact, ...],
    records: tuple[SourceRecord, ...],
    assertions: tuple[SourceAssertion, ...],
    included_professor_identity_ids: tuple[str, ...] = (),
    incremental_company_validation_decisions: tuple[Any, ...] = (),
) -> Any:
    return module.InclusionBatchRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        evaluated_at=NOW,
        policies=tuple(
            _policy(domain)
            for domain in sorted(("company", "paper", "patent", "professor"))
        ),
        approved_source_scope_manifest=manifest,
        canonical_identities=identities,
        source_identities=source_identities,
        evidence_artifacts=artifacts,
        source_records=records,
        source_assertions=assertions,
        candidates=candidates,
        included_professor_identity_ids=included_professor_identity_ids,
        incremental_company_validation_decisions=(
            incremental_company_validation_decisions
        ),
    )


def _evaluate(module: Any, request: Any) -> Any:
    engine = module.create_ephemeral_domain_inclusion_engine()
    assert isinstance(engine, module.DomainInclusionEngine)
    result = engine.evaluate(request)
    assert (
        result.approved_source_scope_manifest_sha256
        == request.approved_source_scope_manifest.content_sha256
    )
    return result


def _decision(result: Any, identity_id: str) -> SharedPolicyDecision:
    matches = tuple(
        decision
        for decision in result.policy_decisions
        if decision.subject_identity_id == identity_id
    )
    assert len(matches) == 1
    decision = matches[0]
    assert isinstance(decision, SharedPolicyDecision)
    return decision


def _incremental_company_validation(
    module: Any,
    *,
    company_identity_id: str,
    dimensions: dict[str, tuple[str, tuple[str, ...]]],
) -> Any:
    return module.create_incremental_company_validation_decision(
        company_identity_id=company_identity_id,
        policy=_policy("company"),
        decision_run_id="offline-company-validation-run-1",
        decision_origin="offline_build",
        dimensions=tuple(
            module.CompanyValidationDimension(
                dimension=dimension,
                outcome=outcome,
                supporting_assertion_ids=assertion_ids,
            )
            for dimension, (outcome, assertion_ids) in sorted(dimensions.items())
        ),
        decided_at=NOW - timedelta(minutes=30),
    )


def test_approved_seed_professor_is_admitted_without_runtime_whitelist_or_enrichment_gate() -> (
    None
):
    module = _module()
    _assert_shared_policy_reexports(module)
    batch_id = "batch:approved-professor-seed"
    artifact_id = "artifact:approved-professor-seed"
    artifact = _artifact(artifact_id=artifact_id, content_sha256="a" * 64)
    record = _source_record(
        record_id="record:professor-seed:1",
        source_batch_id=batch_id,
        artifact_id=artifact_id,
        payload={
            "name": "Ada Chen",
            "institution": "Operator-approved science institute",
        },
    )
    source_identity = _source_identity(
        source_identity_id="source-professor-1",
        entity_type="professor",
        record_id=record.record_id,
        source_key="ada-chen",
    )
    identity = _canonical_identity(
        canonical_identity_id="professor-c1",
        entity_type="professor",
        source_identity_id=source_identity.source_identity_id,
    )
    assertions = (
        _assertion(
            assertion_id="assertion:professor-name",
            source_identity=source_identity,
            field_path="name",
            value="Ada Chen",
        ),
        _assertion(
            assertion_id="assertion:professor-institution",
            source_identity=source_identity,
            field_path="institution",
            value="Operator-approved science institute",
        ),
    )
    candidate = _candidate(
        module,
        identity=identity,
        source_identity=source_identity,
        record=record,
        assertions=assertions,
    )
    unapproved_artifact = _artifact(
        artifact_id="artifact:web-only-professor",
        content_sha256="9" * 64,
        source_kind="query_time_web",
    )
    unapproved_record = _source_record(
        record_id="record:web-only-professor:1",
        source_batch_id="batch:web-only-professor",
        artifact_id=unapproved_artifact.artifact_id,
        payload={"name": "Web Only Professor"},
    )
    unapproved_source = _source_identity(
        source_identity_id="source-web-only-professor",
        entity_type="professor",
        record_id=unapproved_record.record_id,
        source_key="web-only-professor",
    )
    unapproved_identity = _canonical_identity(
        canonical_identity_id="professor-web-only-c1",
        entity_type="professor",
        source_identity_id=unapproved_source.source_identity_id,
    )
    unapproved_assertions = (
        _assertion(
            assertion_id="assertion:web-only-professor-name",
            source_identity=unapproved_source,
            field_path="name",
            value="Web Only Professor",
        ),
    )
    unapproved_candidate = _candidate(
        module,
        identity=unapproved_identity,
        source_identity=unapproved_source,
        record=unapproved_record,
        assertions=unapproved_assertions,
        evidence_lane="query_time_web",
    )
    manifest = _approved_manifest(
        module,
        (
            "professor",
            "professor_seed",
            batch_id,
            artifact_id,
            "a" * 64,
        ),
    )

    result = _evaluate(
        module,
        _request(
            module,
            manifest=manifest,
            candidates=(candidate, unapproved_candidate),
            identities=(identity, unapproved_identity),
            source_identities=(source_identity, unapproved_source),
            artifacts=(artifact, unapproved_artifact),
            records=(record, unapproved_record),
            assertions=(*assertions, *unapproved_assertions),
        ),
    )

    decision = _decision(result, identity.canonical_identity_id)
    assert decision.policy == _policy("professor")
    assert decision.path is None
    assert decision.outcome.value == "admitted"
    assert decision.hard_exclusion_codes == ()
    assert set(decision.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in assertions
    }
    assert result.admitted_identity_ids_by_domain == {
        "company": (),
        "paper": (),
        "patent": (),
        "professor": (identity.canonical_identity_id,),
    }
    unapproved_decision = _decision(result, unapproved_identity.canonical_identity_id)
    assert unapproved_decision.outcome.value == "excluded"
    assert unapproved_decision.hard_exclusion_codes == (
        "outside_professor_inclusion_scope",
    )
    assert unapproved_decision.supporting_assertion_ids == (
        unapproved_assertions[0].assertion_id,
    )
    assert result.excluded_identity_ids_by_domain["professor"] == (
        unapproved_identity.canonical_identity_id,
    )

    mismatched_manifest = _approved_manifest(
        module,
        (
            "professor",
            "professor_seed",
            batch_id,
            artifact_id,
            "0" * 64,
        ),
    )
    with pytest.raises(
        module.DomainInclusionIntegrityError,
        match="artifact.*content.*hash",
    ):
        _evaluate(
            module,
            _request(
                module,
                manifest=mismatched_manifest,
                candidates=(candidate,),
                identities=(identity,),
                source_identities=(source_identity,),
                artifacts=(artifact,),
                records=(record,),
                assertions=assertions,
            ),
        )


def test_roster_anchored_paper_is_admitted_without_enrichment_or_authorship_gate() -> (
    None
):
    module = _module()
    _assert_shared_policy_reexports(module)
    professor_batch_id = "batch:paper-anchor-professor-seed"
    professor_artifact_id = "artifact:paper-anchor-professor-seed"
    professor_artifact = _artifact(
        artifact_id=professor_artifact_id,
        content_sha256="b" * 64,
    )
    professor_record = _source_record(
        record_id="record:paper-anchor-professor",
        source_batch_id=professor_batch_id,
        artifact_id=professor_artifact_id,
        payload={"name": "Professor Lin"},
    )
    professor_source = _source_identity(
        source_identity_id="source-professor-paper-anchor",
        entity_type="professor",
        record_id=professor_record.record_id,
        source_key="professor-lin",
    )
    professor_identity = _canonical_identity(
        canonical_identity_id="professor-paper-anchor-c1",
        entity_type="professor",
        source_identity_id=professor_source.source_identity_id,
    )
    professor_assertions = (
        _assertion(
            assertion_id="assertion:paper-anchor-professor-name",
            source_identity=professor_source,
            field_path="name",
            value="Professor Lin",
        ),
    )
    professor_candidate = _candidate(
        module,
        identity=professor_identity,
        source_identity=professor_source,
        record=professor_record,
        assertions=professor_assertions,
    )

    paper_batch_id = "batch:approved-professor-page-papers"
    paper_artifact_id = "artifact:approved-professor-page-papers"
    paper_artifact = _artifact(
        artifact_id=paper_artifact_id,
        content_sha256="c" * 64,
    )
    paper_record = _source_record(
        record_id="record:professor-page-paper:1",
        source_batch_id=paper_batch_id,
        artifact_id=paper_artifact_id,
        payload={"title": "A roster-anchored preprint"},
    )
    paper_source = _source_identity(
        source_identity_id="source-paper-roster-1",
        entity_type="paper",
        record_id=paper_record.record_id,
        source_key="roster-anchored-preprint",
    )
    paper_identity = _canonical_identity(
        canonical_identity_id="paper-roster-c1",
        entity_type="paper",
        source_identity_id=paper_source.source_identity_id,
    )
    paper_assertions = (
        _assertion(
            assertion_id="assertion:roster-paper-title",
            source_identity=paper_source,
            field_path="title",
            value="A roster-anchored preprint",
        ),
        _assertion(
            assertion_id="assertion:roster-paper-discovery-anchor",
            source_identity=paper_source,
            field_path="discovery.professor_anchor_identity_id",
            value=professor_identity.canonical_identity_id,
        ),
    )
    paper_candidate = _candidate(
        module,
        identity=paper_identity,
        source_identity=paper_source,
        record=paper_record,
        assertions=paper_assertions,
        professor_anchor_identity_id=professor_identity.canonical_identity_id,
    )
    global_artifact = _artifact(
        artifact_id="artifact:global-paper-discovery",
        content_sha256="8" * 64,
        source_kind="academic_platform",
    )
    global_record = _source_record(
        record_id="record:global-paper-discovery:1",
        source_batch_id="batch:global-paper-discovery",
        artifact_id=global_artifact.artifact_id,
        payload={"title": "Globally discovered paper"},
    )
    global_source = _source_identity(
        source_identity_id="source-paper-global-1",
        entity_type="paper",
        record_id=global_record.record_id,
        source_key="globally-discovered-paper",
    )
    global_identity = _canonical_identity(
        canonical_identity_id="paper-global-c1",
        entity_type="paper",
        source_identity_id=global_source.source_identity_id,
    )
    global_assertions = (
        _assertion(
            assertion_id="assertion:global-paper-title",
            source_identity=global_source,
            field_path="title",
            value="Globally discovered paper",
        ),
    )
    global_candidate = _candidate(
        module,
        identity=global_identity,
        source_identity=global_source,
        record=global_record,
        assertions=global_assertions,
        evidence_lane="offline_enrichment",
    )
    manifest = _approved_manifest(
        module,
        (
            "professor",
            "professor_seed",
            professor_batch_id,
            professor_artifact_id,
            "b" * 64,
        ),
        (
            "paper",
            "paper_roster_discovery",
            paper_batch_id,
            paper_artifact_id,
            "c" * 64,
        ),
    )
    reversed_manifest = _approved_manifest(
        module,
        (
            "paper",
            "paper_roster_discovery",
            paper_batch_id,
            paper_artifact_id,
            "c" * 64,
        ),
        (
            "professor",
            "professor_seed",
            professor_batch_id,
            professor_artifact_id,
            "b" * 64,
        ),
    )
    assert manifest.content_sha256 == reversed_manifest.content_sha256

    result = _evaluate(
        module,
        _request(
            module,
            manifest=manifest,
            candidates=(global_candidate, paper_candidate, professor_candidate),
            identities=(global_identity, paper_identity, professor_identity),
            source_identities=(global_source, paper_source, professor_source),
            artifacts=(global_artifact, paper_artifact, professor_artifact),
            records=(global_record, paper_record, professor_record),
            assertions=(
                *global_assertions,
                *paper_assertions,
                *professor_assertions,
            ),
        ),
    )

    paper_decision = _decision(result, paper_identity.canonical_identity_id)
    assert paper_decision.policy == _policy("paper")
    assert paper_decision.path is None
    assert paper_decision.outcome.value == "admitted"
    assert paper_decision.hard_exclusion_codes == ()
    assert set(paper_decision.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in paper_assertions
    }
    assert result.admitted_identity_ids_by_domain["paper"] == (
        paper_identity.canonical_identity_id,
    )
    assert not any(
        assertion.field_path in {"abstract", "professor_ids", "summary_zh"}
        for assertion in paper_assertions
    )
    global_decision = _decision(result, global_identity.canonical_identity_id)
    assert global_decision.outcome.value == "excluded"
    assert global_decision.hard_exclusion_codes == ("outside_paper_discovery_scope",)
    assert global_decision.supporting_assertion_ids == (
        global_assertions[0].assertion_id,
    )
    assert result.excluded_identity_ids_by_domain["paper"] == (
        global_identity.canonical_identity_id,
    )


def test_approved_patent_export_is_admitted_as_a_set_without_topic_or_linkage_filters() -> (
    None
):
    module = _module()
    _assert_shared_policy_reexports(module)
    batch_id = "batch:approved-platform-patent-export"
    artifact_id = "artifact:approved-platform-patent-export"
    approved_artifact = _artifact(
        artifact_id=artifact_id,
        content_sha256="d" * 64,
    )
    patent_fixtures: list[
        tuple[
            SourceRecord,
            SourceIdentity,
            CanonicalIdentity,
            tuple[SourceAssertion, ...],
        ]
    ] = []
    for suffix, payload in (
        (
            "robotics",
            {
                "title": "Robotic navigation patent",
                "patent_number": "CN123456789A",
                "patent_type": "invention",
                "inventors": ["Inventor A"],
                "ipc_codes": ["B25J"],
            },
        ),
        (
            "unlinked",
            {
                "title": "Unlinked material patent",
                "patent_number": "CN987654321A",
            },
        ),
    ):
        record = _source_record(
            record_id=f"record:patent-export:{suffix}",
            source_batch_id=batch_id,
            artifact_id=artifact_id,
            payload=payload,
        )
        source_identity = _source_identity(
            source_identity_id=f"source-patent-{suffix}",
            entity_type="patent",
            record_id=record.record_id,
            source_key=str(payload["patent_number"]),
        )
        identity = _canonical_identity(
            canonical_identity_id=f"patent-{suffix}-c1",
            entity_type="patent",
            source_identity_id=source_identity.source_identity_id,
        )
        assertions = tuple(
            _assertion(
                assertion_id=f"assertion:patent-{suffix}:{field_path}",
                source_identity=source_identity,
                field_path=field_path,
                value=value,
            )
            for field_path, value in payload.items()
        )
        patent_fixtures.append((record, source_identity, identity, assertions))

    approved_candidates = tuple(
        _candidate(
            module,
            identity=identity,
            source_identity=source_identity,
            record=record,
            assertions=assertions,
        )
        for record, source_identity, identity, assertions in patent_fixtures
    )
    records = tuple(item[0] for item in patent_fixtures)
    source_identities = tuple(item[1] for item in patent_fixtures)
    identities = tuple(item[2] for item in patent_fixtures)
    assertions = tuple(
        assertion
        for _, _, _, fixture_assertions in patent_fixtures
        for assertion in fixture_assertions
    )
    unapproved_artifact = _artifact(
        artifact_id="artifact:unapproved-patent-export",
        content_sha256="7" * 64,
    )
    unapproved_record = _source_record(
        record_id="record:unapproved-patent-export:1",
        source_batch_id="batch:unapproved-patent-export",
        artifact_id=unapproved_artifact.artifact_id,
        payload={
            "title": "Patent outside the approved export",
            "patent_number": "CN111111111A",
        },
    )
    unapproved_source = _source_identity(
        source_identity_id="source-patent-unapproved",
        entity_type="patent",
        record_id=unapproved_record.record_id,
        source_key="CN111111111A",
    )
    unapproved_identity = _canonical_identity(
        canonical_identity_id="patent-unapproved-c1",
        entity_type="patent",
        source_identity_id=unapproved_source.source_identity_id,
    )
    unapproved_assertions = tuple(
        _assertion(
            assertion_id=f"assertion:patent-unapproved:{field_path}",
            source_identity=unapproved_source,
            field_path=field_path,
            value=value,
        )
        for field_path, value in unapproved_record.payload.items()
    )
    unapproved_candidate = _candidate(
        module,
        identity=unapproved_identity,
        source_identity=unapproved_source,
        record=unapproved_record,
        assertions=unapproved_assertions,
    )
    candidates = (*approved_candidates, unapproved_candidate)
    all_identities = (*identities, unapproved_identity)
    all_source_identities = (*source_identities, unapproved_source)
    all_records = (*records, unapproved_record)
    all_assertions = (*assertions, *unapproved_assertions)
    artifacts = (approved_artifact, unapproved_artifact)
    manifest = _approved_manifest(
        module,
        (
            "patent",
            "patent_export",
            batch_id,
            artifact_id,
            "d" * 64,
        ),
    )
    request = _request(
        module,
        manifest=manifest,
        candidates=candidates,
        identities=all_identities,
        source_identities=all_source_identities,
        artifacts=artifacts,
        records=all_records,
        assertions=all_assertions,
    )
    reversed_request = _request(
        module,
        manifest=manifest,
        candidates=tuple(reversed(candidates)),
        identities=tuple(reversed(all_identities)),
        source_identities=tuple(reversed(all_source_identities)),
        artifacts=tuple(reversed(artifacts)),
        records=tuple(reversed(all_records)),
        assertions=tuple(reversed(all_assertions)),
    )

    result = _evaluate(module, request)
    reversed_result = _evaluate(module, reversed_request)

    expected_ids = tuple(
        sorted(identity.canonical_identity_id for identity in identities)
    )
    assert result.admitted_identity_ids_by_domain["patent"] == expected_ids
    assert all(
        _decision(result, identity_id).outcome.value == "admitted"
        for identity_id in expected_ids
    )
    assert all(
        _decision(result, identity_id).hard_exclusion_codes == ()
        for identity_id in expected_ids
    )
    unapproved_decision = _decision(result, unapproved_identity.canonical_identity_id)
    assert unapproved_decision.outcome.value == "excluded"
    assert unapproved_decision.hard_exclusion_codes == ("outside_patent_export_scope",)
    assert set(unapproved_decision.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in unapproved_assertions
    }
    assert result.excluded_identity_ids_by_domain["patent"] == (
        unapproved_identity.canonical_identity_id,
    )
    assert result == reversed_result
    assert result.content_sha256 == reversed_result.content_sha256


def test_company_skeleton_and_four_dimension_incremental_validation_are_admitted() -> (
    None
):
    module = _module()
    _assert_shared_policy_reexports(module)
    skeleton_batch_id = "batch:approved-company-skeleton"
    skeleton_artifact_id = "artifact:approved-company-skeleton"
    skeleton_artifact = _artifact(
        artifact_id=skeleton_artifact_id,
        content_sha256="e" * 64,
    )
    skeleton_record = _source_record(
        record_id="record:company-skeleton:1",
        source_batch_id=skeleton_batch_id,
        artifact_id=skeleton_artifact_id,
        payload={"name": "Skeleton Robotics Ltd."},
    )
    skeleton_source = _source_identity(
        source_identity_id="source-company-skeleton-1",
        entity_type="company",
        record_id=skeleton_record.record_id,
        source_key="skeleton-robotics-ltd",
    )
    skeleton_identity = _canonical_identity(
        canonical_identity_id="company-skeleton-c1",
        entity_type="company",
        source_identity_id=skeleton_source.source_identity_id,
    )
    skeleton_assertions = (
        _assertion(
            assertion_id="assertion:company-skeleton-name",
            source_identity=skeleton_source,
            field_path="name",
            value="Skeleton Robotics Ltd.",
        ),
    )
    skeleton_candidate = _candidate(
        module,
        identity=skeleton_identity,
        source_identity=skeleton_source,
        record=skeleton_record,
        assertions=skeleton_assertions,
    )

    incremental_artifact = _artifact(
        artifact_id="artifact:offline-company-incremental-validation",
        content_sha256="6" * 64,
    )
    incremental_record = _source_record(
        record_id="record:company-incremental:1",
        source_batch_id="batch:offline-company-incremental-validation",
        artifact_id="artifact:offline-company-incremental-validation",
        payload={
            "name": "Shenzhen Precision Sensors Ltd.",
            "normalized_name": "shenzhen precision sensors",
            "geography": "Shenzhen",
            "product_description": "Industrial optical sensors",
            "evidence": {
                "source_type": "official_site",
                "source_url": "https://example.invalid/company",
            },
        },
    )
    incremental_source = _source_identity(
        source_identity_id="source-company-incremental-1",
        entity_type="company",
        record_id=incremental_record.record_id,
        source_key="shenzhen-precision-sensors",
    )
    incremental_identity = _canonical_identity(
        canonical_identity_id="company-incremental-c1",
        entity_type="company",
        source_identity_id=incremental_source.source_identity_id,
    )
    incremental_assertions = tuple(
        _assertion(
            assertion_id=f"assertion:company-incremental:{field_path}",
            source_identity=incremental_source,
            field_path=field_path,
            value=value,
        )
        for field_path, value in incremental_record.payload.items()
    )
    incremental_assertion_ids = {
        assertion.field_path: assertion.assertion_id
        for assertion in incremental_assertions
    }
    validation = _incremental_company_validation(
        module,
        company_identity_id=incremental_identity.canonical_identity_id,
        dimensions={
            "basic_identity": (
                "supported",
                (
                    incremental_assertion_ids["name"],
                    incremental_assertion_ids["normalized_name"],
                ),
            ),
            "innovation_business_relevance": (
                "supported",
                (incremental_assertion_ids["product_description"],),
            ),
            "shenzhen_geography": (
                "supported",
                (incremental_assertion_ids["geography"],),
            ),
            "source_validation": (
                "supported",
                (incremental_assertion_ids["evidence"],),
            ),
        },
    )
    incremental_candidate = _candidate(
        module,
        identity=incremental_identity,
        source_identity=incremental_source,
        record=incremental_record,
        assertions=incremental_assertions,
        incremental_company_validation_decision_id=validation.decision_id,
    )

    review_artifact = _artifact(
        artifact_id="artifact:offline-company-review-validation",
        content_sha256="5" * 64,
    )
    review_record = _source_record(
        record_id="record:company-incremental-review:1",
        source_batch_id="batch:offline-company-review-validation",
        artifact_id=review_artifact.artifact_id,
        payload={
            "name": "Shenzhen Ambiguous Automation Ltd.",
            "normalized_name": "shenzhen ambiguous automation",
            "geography": "Shenzhen",
            "product_description": "Automation equipment",
            "source_validation_status": "ambiguous",
        },
    )
    review_source = _source_identity(
        source_identity_id="source-company-incremental-review",
        entity_type="company",
        record_id=review_record.record_id,
        source_key="shenzhen-ambiguous-automation",
    )
    review_identity = _canonical_identity(
        canonical_identity_id="company-incremental-review-c1",
        entity_type="company",
        source_identity_id=review_source.source_identity_id,
    )
    review_assertions = tuple(
        _assertion(
            assertion_id=f"assertion:company-review:{field_path}",
            source_identity=review_source,
            field_path=field_path,
            value=value,
        )
        for field_path, value in review_record.payload.items()
    )
    review_assertion_ids = {
        assertion.field_path: assertion.assertion_id for assertion in review_assertions
    }
    review_validation = _incremental_company_validation(
        module,
        company_identity_id=review_identity.canonical_identity_id,
        dimensions={
            "basic_identity": (
                "supported",
                (
                    review_assertion_ids["name"],
                    review_assertion_ids["normalized_name"],
                ),
            ),
            "innovation_business_relevance": (
                "supported",
                (review_assertion_ids["product_description"],),
            ),
            "shenzhen_geography": (
                "supported",
                (review_assertion_ids["geography"],),
            ),
            "source_validation": (
                "insufficient_evidence",
                (review_assertion_ids["source_validation_status"],),
            ),
        },
    )
    review_candidate = _candidate(
        module,
        identity=review_identity,
        source_identity=review_source,
        record=review_record,
        assertions=review_assertions,
        incremental_company_validation_decision_id=review_validation.decision_id,
    )

    contrary_artifact = _artifact(
        artifact_id="artifact:offline-company-contrary-validation",
        content_sha256="4" * 64,
    )
    contrary_record = _source_record(
        record_id="record:company-incremental-contrary:1",
        source_batch_id="batch:offline-company-contrary-validation",
        artifact_id=contrary_artifact.artifact_id,
        payload={
            "name": "Beijing Confirmed Robotics Ltd.",
            "normalized_name": "beijing confirmed robotics",
            "geography": "Beijing",
            "product_description": "Industrial robots",
            "evidence": {
                "source_type": "official_site",
                "source_url": "https://example.invalid/beijing-company",
            },
        },
    )
    contrary_source = _source_identity(
        source_identity_id="source-company-incremental-contrary",
        entity_type="company",
        record_id=contrary_record.record_id,
        source_key="beijing-confirmed-robotics",
    )
    contrary_identity = _canonical_identity(
        canonical_identity_id="company-incremental-contrary-c1",
        entity_type="company",
        source_identity_id=contrary_source.source_identity_id,
    )
    contrary_assertions = tuple(
        _assertion(
            assertion_id=f"assertion:company-contrary:{field_path}",
            source_identity=contrary_source,
            field_path=field_path,
            value=value,
        )
        for field_path, value in contrary_record.payload.items()
    )
    contrary_assertion_ids = {
        assertion.field_path: assertion.assertion_id
        for assertion in contrary_assertions
    }
    contrary_validation = _incremental_company_validation(
        module,
        company_identity_id=contrary_identity.canonical_identity_id,
        dimensions={
            "basic_identity": (
                "supported",
                (
                    contrary_assertion_ids["name"],
                    contrary_assertion_ids["normalized_name"],
                ),
            ),
            "innovation_business_relevance": (
                "supported",
                (contrary_assertion_ids["product_description"],),
            ),
            "shenzhen_geography": (
                "contradicted",
                (contrary_assertion_ids["geography"],),
            ),
            "source_validation": (
                "supported",
                (contrary_assertion_ids["evidence"],),
            ),
        },
    )
    contrary_candidate = _candidate(
        module,
        identity=contrary_identity,
        source_identity=contrary_source,
        record=contrary_record,
        assertions=contrary_assertions,
        incremental_company_validation_decision_id=contrary_validation.decision_id,
    )
    manifest = _approved_manifest(
        module,
        (
            "company",
            "company_skeleton",
            skeleton_batch_id,
            skeleton_artifact_id,
            "e" * 64,
        ),
    )

    result = _evaluate(
        module,
        _request(
            module,
            manifest=manifest,
            candidates=(
                contrary_candidate,
                incremental_candidate,
                review_candidate,
                skeleton_candidate,
            ),
            identities=(
                contrary_identity,
                incremental_identity,
                review_identity,
                skeleton_identity,
            ),
            source_identities=(
                contrary_source,
                incremental_source,
                review_source,
                skeleton_source,
            ),
            artifacts=(
                contrary_artifact,
                incremental_artifact,
                review_artifact,
                skeleton_artifact,
            ),
            records=(
                contrary_record,
                incremental_record,
                review_record,
                skeleton_record,
            ),
            assertions=(
                *contrary_assertions,
                *incremental_assertions,
                *review_assertions,
                *skeleton_assertions,
            ),
            incremental_company_validation_decisions=(
                contrary_validation,
                validation,
                review_validation,
            ),
        ),
    )

    expected_ids = tuple(
        sorted(
            (
                incremental_identity.canonical_identity_id,
                skeleton_identity.canonical_identity_id,
            )
        )
    )
    assert result.admitted_identity_ids_by_domain["company"] == expected_ids
    assert (
        _decision(result, skeleton_identity.canonical_identity_id).outcome.value
        == "admitted"
    )
    incremental_decision = _decision(result, incremental_identity.canonical_identity_id)
    assert incremental_decision.outcome.value == "admitted"
    assert set(incremental_decision.supporting_assertion_ids) == set(
        incremental_assertion_ids.values()
    )
    assert all(
        assertion.field_path != "profile_summary" for assertion in skeleton_assertions
    )
    review_decision = _decision(result, review_identity.canonical_identity_id)
    assert review_decision.outcome.value == "review"
    assert review_decision.hard_exclusion_codes == ()
    assert review_decision.limitations == ("incremental_company_validation_incomplete",)
    assert set(review_decision.supporting_assertion_ids) == set(
        review_assertion_ids.values()
    )
    assert result.review_identity_ids_by_domain["company"] == (
        review_identity.canonical_identity_id,
    )
    contrary_decision = _decision(result, contrary_identity.canonical_identity_id)
    assert contrary_decision.outcome.value == "excluded"
    assert contrary_decision.hard_exclusion_codes == (
        "outside_company_inclusion_scope",
    )
    assert set(contrary_decision.supporting_assertion_ids) == set(
        contrary_assertion_ids.values()
    )
    assert result.excluded_identity_ids_by_domain["company"] == (
        contrary_identity.canonical_identity_id,
    )


def test_query_time_web_only_national_company_stays_outside_canonical_inclusion() -> (
    None
):
    module = _module()
    _assert_shared_policy_reexports(module)
    web_artifact = _artifact(
        artifact_id="artifact:query-time-web-company",
        content_sha256="3" * 64,
        source_kind="query_time_web",
    )
    web_record = _source_record(
        record_id="record:web-company-national:1",
        source_batch_id="batch:query-time-web-company",
        artifact_id="artifact:query-time-web-company",
        payload={
            "name": "Beijing National Robotics Ltd.",
            "geography": "Beijing",
            "product_description": "Industrial robots",
        },
    )
    web_source = _source_identity(
        source_identity_id="source-web-company-national-1",
        entity_type="company",
        record_id=web_record.record_id,
        source_key="beijing-national-robotics",
    )
    web_identity = _canonical_identity(
        canonical_identity_id="company-web-national-c1",
        entity_type="company",
        source_identity_id=web_source.source_identity_id,
    )
    web_assertions = tuple(
        _assertion(
            assertion_id=f"assertion:web-company:{field_path}",
            source_identity=web_source,
            field_path=field_path,
            value=value,
        )
        for field_path, value in web_record.payload.items()
    )
    web_candidate = _candidate(
        module,
        identity=web_identity,
        source_identity=web_source,
        record=web_record,
        assertions=web_assertions,
        evidence_lane="query_time_web",
    )
    manifest = _approved_manifest(
        module,
        (
            "company",
            "company_skeleton",
            "batch:some-other-approved-company-skeleton",
            "artifact:some-other-approved-company-skeleton",
            "f" * 64,
        ),
    )
    approved_placeholder_artifact = _artifact(
        artifact_id="artifact:some-other-approved-company-skeleton",
        content_sha256="f" * 64,
    )
    request = _request(
        module,
        manifest=manifest,
        candidates=(web_candidate,),
        identities=(web_identity,),
        source_identities=(web_source,),
        artifacts=(approved_placeholder_artifact, web_artifact),
        records=(web_record,),
        assertions=web_assertions,
    )
    request_before = request.model_dump(mode="json")

    result = _evaluate(module, request)

    decision = _decision(result, web_identity.canonical_identity_id)
    assert decision.policy == _policy("company")
    assert decision.path is None
    assert decision.outcome.value == "excluded"
    assert decision.hard_exclusion_codes == ("outside_company_inclusion_scope",)
    assert set(decision.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in web_assertions
    }
    assert web_identity.canonical_identity_id not in set(
        result.admitted_identity_ids_by_domain["company"]
    )
    assert result.excluded_identity_ids_by_domain["company"] == (
        web_identity.canonical_identity_id,
    )
    assert request.model_dump(mode="json") == request_before


def test_approved_scope_requires_a_cited_record_not_an_uncited_candidate_record() -> (
    None
):
    module = _module()
    approved_artifact = _artifact(
        artifact_id="artifact:approved-scope-record",
        content_sha256="7" * 64,
    )
    outside_artifact = _artifact(
        artifact_id="artifact:outside-scope-evidence",
        content_sha256="8" * 64,
    )
    approved_record = _source_record(
        record_id="record:approved-but-uncited",
        source_batch_id="batch:approved-but-uncited",
        artifact_id=approved_artifact.artifact_id,
        payload={"name": "Uncited approved row"},
    )
    outside_record = _source_record(
        record_id="record:outside-but-cited",
        source_batch_id="batch:outside-but-cited",
        artifact_id=outside_artifact.artifact_id,
        payload={"name": "Cited outside row"},
    )
    source_identity = SourceIdentity(
        source_identity_id="source-professor-mixed-scope",
        source_system="recorded-domain-fixture",
        source_key="mixed-scope-professor",
        entity_type="professor",
        source_record_ids=(approved_record.record_id, outside_record.record_id),
        normalized_keys={"source_key": "mixed-scope-professor"},
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW - timedelta(hours=1),
        state=SourceIdentityState.active,
    )
    identity = _canonical_identity(
        canonical_identity_id="professor-mixed-scope-c1",
        entity_type="professor",
        source_identity_id=source_identity.source_identity_id,
    )
    assertion = SourceAssertion(
        assertion_id="assertion:outside-scope-professor-name",
        source_record_id=outside_record.record_id,
        source_identity_id=source_identity.source_identity_id,
        subject_entity_type="professor",
        field_path="name",
        value="Cited Outside Professor",
        observed_at=NOW - timedelta(hours=1),
        assertion_run_id="domain-assertion-run-1",
    )
    candidate = module.InclusionCandidate(
        canonical_identity_id=identity.canonical_identity_id,
        domain="professor",
        source_identity_ids=(source_identity.source_identity_id,),
        source_record_ids=(approved_record.record_id, outside_record.record_id),
        supporting_assertion_ids=(assertion.assertion_id,),
        evidence_lane="offline_landing",
    )
    manifest = _approved_manifest(
        module,
        (
            "professor",
            "professor_seed",
            approved_record.source_batch_id,
            approved_artifact.artifact_id,
            approved_artifact.content_sha256,
        ),
    )

    result = _evaluate(
        module,
        _request(
            module,
            manifest=manifest,
            candidates=(candidate,),
            identities=(identity,),
            source_identities=(source_identity,),
            artifacts=(approved_artifact, outside_artifact),
            records=(approved_record, outside_record),
            assertions=(assertion,),
        ),
    )

    assert _decision(result, identity.canonical_identity_id).outcome.value == "excluded"


def test_incremental_company_validation_evidence_cannot_cross_wire_subjects() -> None:
    module = _module()
    candidate_artifact = _artifact(
        artifact_id="artifact:incremental-company",
        content_sha256="5" * 64,
    )
    candidate_record = _source_record(
        record_id="record:incremental-company",
        source_batch_id="batch:incremental-company",
        artifact_id=candidate_artifact.artifact_id,
        payload={"name": "Incremental Company"},
    )
    candidate_source = _source_identity(
        source_identity_id="source-incremental-company",
        entity_type="company",
        record_id=candidate_record.record_id,
        source_key="incremental-company",
    )
    candidate_identity = _canonical_identity(
        canonical_identity_id="company-incremental-c1",
        entity_type="company",
        source_identity_id=candidate_source.source_identity_id,
    )
    candidate_assertion = _assertion(
        assertion_id="assertion:incremental-company-name",
        source_identity=candidate_source,
        field_path="name",
        value="Incremental Company",
    )

    foreign_artifact = _artifact(
        artifact_id="artifact:foreign-company",
        content_sha256="6" * 64,
    )
    foreign_record = _source_record(
        record_id="record:foreign-company",
        source_batch_id="batch:foreign-company",
        artifact_id=foreign_artifact.artifact_id,
        payload={"name": "Foreign Company"},
    )
    foreign_source = _source_identity(
        source_identity_id="source-foreign-company",
        entity_type="company",
        record_id=foreign_record.record_id,
        source_key="foreign-company",
    )
    foreign_identity = _canonical_identity(
        canonical_identity_id="company-foreign-c1",
        entity_type="company",
        source_identity_id=foreign_source.source_identity_id,
    )
    foreign_assertion = _assertion(
        assertion_id="assertion:foreign-company-validation",
        source_identity=foreign_source,
        field_path="validation.source",
        value="foreign evidence",
    )
    validation = _incremental_company_validation(
        module,
        company_identity_id=candidate_identity.canonical_identity_id,
        dimensions={
            dimension: ("supported", (foreign_assertion.assertion_id,))
            for dimension in (
                "basic_identity",
                "innovation_business_relevance",
                "shenzhen_geography",
                "source_validation",
            )
        },
    )
    candidate = _candidate(
        module,
        identity=candidate_identity,
        source_identity=candidate_source,
        record=candidate_record,
        assertions=(candidate_assertion,),
        incremental_company_validation_decision_id=validation.decision_id,
    )
    approved_artifact = _artifact(
        artifact_id="artifact:unrelated-approved-company",
        content_sha256="4" * 64,
    )
    approved_record = _source_record(
        record_id="record:unrelated-approved-company",
        source_batch_id="batch:unrelated-approved-company",
        artifact_id=approved_artifact.artifact_id,
        payload={"name": "Approved unrelated row"},
    )
    manifest = _approved_manifest(
        module,
        (
            "company",
            "company_skeleton",
            approved_record.source_batch_id,
            approved_artifact.artifact_id,
            approved_artifact.content_sha256,
        ),
    )

    with pytest.raises(
        module.DomainInclusionIntegrityError,
        match="validation.*evidence|assertion.*candidate",
    ):
        _evaluate(
            module,
            _request(
                module,
                manifest=manifest,
                candidates=(candidate,),
                identities=(candidate_identity, foreign_identity),
                source_identities=(candidate_source, foreign_source),
                artifacts=(
                    candidate_artifact,
                    foreign_artifact,
                    approved_artifact,
                ),
                records=(candidate_record, foreign_record, approved_record),
                assertions=(candidate_assertion, foreign_assertion),
                incremental_company_validation_decisions=(validation,),
            ),
        )


def test_in_scope_unanchored_paper_is_admitted_with_paper_unanchored_limitation() -> (
    None
):
    # admit-unanchored-papers (G4/G6 admission matrix): an in-scope paper
    # WITHOUT a Professor anchor stays reachable, honestly tiered — was
    # hard-excluded (outside_paper_discovery_scope) before the change.
    module = _module()
    paper_batch_id = "batch:approved-paper-without-anchor"
    paper_artifact_id = "artifact:approved-paper-without-anchor"
    paper_artifact = _artifact(
        artifact_id=paper_artifact_id,
        content_sha256="d" * 64,
    )
    paper_record = _source_record(
        record_id="record:unanchored-paper:1",
        source_batch_id=paper_batch_id,
        artifact_id=paper_artifact_id,
        payload={"title": "An in-scope paper with no professor anchor"},
    )
    paper_source = _source_identity(
        source_identity_id="source-paper-unanchored-1",
        entity_type="paper",
        record_id=paper_record.record_id,
        source_key="in-scope-unanchored-paper",
    )
    paper_identity = _canonical_identity(
        canonical_identity_id="paper-unanchored-c1",
        entity_type="paper",
        source_identity_id=paper_source.source_identity_id,
    )
    paper_assertions = (
        _assertion(
            assertion_id="assertion:unanchored-paper-title",
            source_identity=paper_source,
            field_path="title",
            value="An in-scope paper with no professor anchor",
        ),
    )
    paper_candidate = _candidate(
        module,
        identity=paper_identity,
        source_identity=paper_source,
        record=paper_record,
        assertions=paper_assertions,
    )
    manifest = _approved_manifest(
        module,
        (
            "paper",
            "paper_roster_discovery",
            paper_batch_id,
            paper_artifact_id,
            "d" * 64,
        ),
    )
    result = _evaluate(
        module,
        _request(
            module,
            manifest=manifest,
            candidates=(paper_candidate,),
            identities=(paper_identity,),
            source_identities=(paper_source,),
            artifacts=(paper_artifact,),
            records=(paper_record,),
            assertions=paper_assertions,
        ),
    )
    paper_decision = _decision(result, paper_identity.canonical_identity_id)
    assert paper_decision.outcome.value == "admitted"
    assert paper_decision.limitations == ("paper_unanchored",)
    assert paper_decision.hard_exclusion_codes == ()
    assert result.admitted_identity_ids_by_domain["paper"] == (
        paper_identity.canonical_identity_id,
    )
