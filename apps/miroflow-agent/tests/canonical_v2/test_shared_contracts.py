from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json
from typing import Any

from pydantic import ValidationError
import pytest


NOW = datetime(2026, 7, 11, 17, 0, tzinfo=timezone.utc)


def _contracts() -> Any:
    return importlib.import_module("src.data_agents.canonical_v2.contracts")


def _policy(module: Any, kind: str = "field_selection") -> Any:
    return module.PolicyReference(
        policy_id=f"{kind}-policy",
        policy_version="v1",
        policy_kind=kind,
        content_sha256="1" * 64,
        effective_at=NOW,
    )


def _section(module: Any, section_id: str, release_id: str = "release-r1") -> Any:
    return module.ManifestSection(
        section_id=section_id,
        release_id=release_id,
        version="v1",
        record_count=2,
        content_sha256="2" * 64,
    )


def test_artifact_and_source_record_preserve_byte_and_parser_chain_of_custody() -> None:
    module = _contracts()
    artifact = module.EvidenceArtifact(
        artifact_id="artifact-copy-1",
        source_kind="historical_jsonl",
        source_locator="verified-restore/papers.jsonl",
        content_sha256="a" * 64,
        byte_size=123,
        acquired_at=NOW,
        run_id="copy-run-1",
        parent_artifact_id="artifact-source-1",
        parent_content_sha256="a" * 64,
    )
    record = module.SourceRecord(
        record_id="record-1",
        artifact_id=artifact.artifact_id,
        source_batch_id="batch-1",
        record_locator="line:1",
        parser_name="historical-jsonl",
        parser_version="parser-v1",
        schema_version="source-paper-v1",
        parse_run_id="parse-run-1",
        parse_status="parsed",
        payload={"title": "Evidence first", "year": 2026},
        errors=(),
        parsed_at=NOW,
    )

    assert artifact.parent_artifact_id == "artifact-source-1"
    assert artifact.content_sha256 == artifact.parent_content_sha256
    assert record.artifact_id == artifact.artifact_id
    assert record.record_locator == "line:1"
    assert record.parse_status.value == "parsed"
    assert json.loads(record.model_dump_json())["parser_version"] == "parser-v1"
    with pytest.raises(ValidationError, match="frozen"):
        artifact.byte_size = 1


def test_artifact_rejects_bad_hash_naive_time_and_half_parent_lineage() -> None:
    module = _contracts()
    base = {
        "artifact_id": "artifact-1",
        "source_kind": "sqlite",
        "source_locator": "restore/source.db",
        "content_sha256": "a" * 64,
        "byte_size": 10,
        "acquired_at": NOW,
        "run_id": "copy-run-1",
    }

    with pytest.raises(ValidationError, match="content_sha256"):
        module.EvidenceArtifact(**{**base, "content_sha256": "not-a-hash"})
    with pytest.raises(ValidationError, match="timezone"):
        module.EvidenceArtifact(
            **{**base, "acquired_at": datetime(2026, 7, 11, 17, 0)}
        )
    with pytest.raises(ValidationError, match="parent"):
        module.EvidenceArtifact(
            **{**base, "parent_artifact_id": "artifact-parent"}
        )


def test_nonparsed_source_record_requires_typed_errors_and_keeps_partial_payload() -> None:
    module = _contracts()
    error = module.SourceError(
        error_code="missing_toast",
        error_kind="missing_external_content",
        message="external value is unavailable",
        field_path="abstract",
        recoverable=False,
    )
    partial = module.SourceRecord(
        record_id="record-partial-1",
        artifact_id="artifact-1",
        source_batch_id="batch-1",
        record_locator="block:8/row:2",
        parser_name="fpi-salvage",
        parser_version="v1",
        schema_version="salvage-paper-v1",
        parse_run_id="parse-run-1",
        parse_status="partial",
        payload={"paper_id": "paper-1", "title": "Readable title"},
        errors=(error,),
        parsed_at=NOW,
    )

    assert partial.payload["title"] == "Readable title"
    assert partial.errors[0].field_path == "abstract"
    with pytest.raises(ValidationError, match="typed error"):
        module.SourceRecord(
            **{
                **partial.model_dump(),
                "record_id": "record-corrupt-1",
                "parse_status": "corrupt",
                "errors": (),
            }
        )


def test_source_assertion_retains_source_identity_time_and_conflicting_values() -> None:
    module = _contracts()
    first = module.SourceAssertion(
        assertion_id="assertion-title-official",
        source_record_id="record-official",
        source_identity_id="source-professor-official",
        subject_entity_type="professor",
        field_path="employment.current_title",
        value="Professor",
        observed_at=NOW,
        source_event_time=NOW - timedelta(days=5),
        valid_from=NOW - timedelta(days=30),
        valid_to=None,
        assertion_run_id="assert-run-1",
    )
    competing = module.SourceAssertion(
        **{
            **first.model_dump(),
            "assertion_id": "assertion-title-historical",
            "source_record_id": "record-historical",
            "source_identity_id": "source-professor-history",
            "value": "Associate Professor",
            "observed_at": NOW - timedelta(days=60),
        }
    )

    assert first.value != competing.value
    assert first.source_record_id != competing.source_record_id
    with pytest.raises(ValidationError, match="valid_from"):
        module.SourceAssertion(
            **{
                **first.model_dump(),
                "valid_from": NOW,
                "valid_to": NOW - timedelta(days=1),
            }
        )


def test_canonical_decision_can_select_evidence_or_preserve_unresolved_conflict() -> None:
    module = _contracts()
    trace = module.LLMDecisionTrace(
        provider="recorded-fake",
        model="identity-judge-v1",
        prompt_version="prompt-v2",
        schema_version="decision-v1",
        input_evidence_ids=("assertion-a", "assertion-b"),
        output_sha256="3" * 64,
    )
    selected = module.CanonicalDecision(
        decision_id="decision-title-1",
        canonical_identity_id="professor-c1",
        field_path="employment.current_title",
        state="selected",
        candidate_assertion_ids=("assertion-a", "assertion-b"),
        selected_assertion_ids=("assertion-a",),
        conflicting_assertion_ids=("assertion-b",),
        policy=_policy(module),
        method="structured_llm",
        method_version="selector-v1",
        decision_run_id="build-run-1",
        confidence=0.83,
        rationale="Official current page is newer than the historical row.",
        llm_trace=trace,
        decided_at=NOW,
    )
    unresolved = module.CanonicalDecision(
        **{
            **selected.model_dump(),
            "decision_id": "decision-title-2",
            "state": "unresolved",
            "selected_assertion_ids": (),
            "conflicting_assertion_ids": ("assertion-a", "assertion-b"),
            "confidence": 0.42,
            "rationale": "Neither source establishes a current title.",
        }
    )

    assert selected.selected_assertion_ids == ("assertion-a",)
    assert unresolved.conflicting_assertion_ids == ("assertion-a", "assertion-b")
    with pytest.raises(ValidationError, match="selected assertion"):
        module.CanonicalDecision(
            **{
                **selected.model_dump(),
                "selected_assertion_ids": ("assertion-not-a-candidate",),
            }
        )


def test_source_and_canonical_identities_keep_merge_split_and_reversal_lineage() -> None:
    module = _contracts()
    source_identity = module.SourceIdentity(
        source_identity_id="source-company-1",
        source_system="historical-company-xlsx",
        source_key="row:8",
        entity_type="company",
        source_record_ids=("record-company-8",),
        normalized_keys={"name": "example technology shenzhen"},
        first_observed_at=NOW - timedelta(days=90),
        last_observed_at=NOW,
        state="active",
    )
    canonical = module.CanonicalIdentity(
        canonical_identity_id="company-c1",
        entity_type="company",
        state="active",
        display_name="Example Technology (Shenzhen)",
        source_identity_ids=(source_identity.source_identity_id,),
        identity_decision_id="identity-create-1",
        predecessor_identity_ids=(),
        successor_identity_ids=(),
        release_id="release-r1",
    )
    merge = module.IdentityDecision(
        decision_id="identity-merge-1",
        action="merge",
        source_identity_ids=("source-company-1", "source-company-2"),
        input_canonical_identity_ids=("company-c1", "company-c2"),
        output_canonical_identity_ids=("company-c3",),
        supporting_record_ids=("record-company-8", "record-company-9"),
        policy=_policy(module, "identity"),
        method="composite",
        method_version="identity-v1",
        decision_run_id="build-run-1",
        confidence=0.99,
        rationale="Credit code and official name match.",
        decided_at=NOW,
    )
    split = module.IdentityDecision(
        **{
            **merge.model_dump(),
            "decision_id": "identity-split-1",
            "action": "split",
            "source_identity_ids": ("source-company-1", "source-company-2"),
            "input_canonical_identity_ids": ("company-c3",),
            "output_canonical_identity_ids": ("company-c1", "company-c2"),
            "rationale": "Reviewed evidence proves two legal persons.",
        }
    )
    reversal = module.IdentityDecision(
        **{
            **split.model_dump(),
            "decision_id": "identity-reverse-1",
            "action": "reverse",
            "reversal_of_decision_id": merge.decision_id,
        }
    )

    assert canonical.source_identity_ids == ("source-company-1",)
    assert merge.output_canonical_identity_ids == ("company-c3",)
    assert len(split.output_canonical_identity_ids) == 2
    assert reversal.reversal_of_decision_id == merge.decision_id
    with pytest.raises(ValidationError, match="merge"):
        module.IdentityDecision(
            **{
                **merge.model_dump(),
                "input_canonical_identity_ids": ("company-c1",),
            }
        )


def test_relationship_catalog_expresses_canonical_derived_and_session_layers() -> None:
    module = _contracts()
    role = module.RelationshipRole(
        role_id="founder",
        applies_to="source",
        description="Professor founded the Company",
        required=True,
    )
    canonical = module.RelationshipType(
        relationship_type_id="professor_founded_company",
        version="v1",
        layer="canonical",
        source_entity_types=("professor",),
        target_entity_types=("company",),
        direction="directed",
        roles=(role,),
        required_evidence_kinds=("official_site", "corporate_registry"),
        time_semantics="validity_interval",
        allowed_states=("accepted", "unresolved", "rejected"),
        eligible_paths=("relationship_traversal", "structured_filter"),
    )
    derived = module.RelationshipType(
        relationship_type_id="paper_similarity",
        version="embedding-v2",
        layer="derived",
        source_entity_types=("paper",),
        target_entity_types=("paper",),
        direction="directed",
        roles=(),
        required_evidence_kinds=(),
        time_semantics="computed_at",
        allowed_states=("computed",),
        eligible_paths=("recommendation", "ranking"),
    )
    session = module.RelationshipType(
        relationship_type_id="displayed_result_referent",
        version="session-v1",
        layer="session",
        source_entity_types=("session",),
        target_entity_types=("canonical_identity",),
        direction="directed",
        roles=(),
        required_evidence_kinds=(),
        time_semantics="session_lifetime",
        allowed_states=("active", "expired"),
        eligible_paths=("context_resolution",),
    )

    assert {item.layer.value for item in (canonical, derived, session)} == {
        "canonical",
        "derived",
        "session",
    }
    with pytest.raises(ValidationError, match="source evidence"):
        module.RelationshipType(
            **{**canonical.model_dump(), "required_evidence_kinds": ()}
        )
    with pytest.raises(ValidationError, match="cannot require source evidence"):
        module.RelationshipType(
            **{**derived.model_dump(), "required_evidence_kinds": ("official_site",)}
        )


def test_relationship_assertion_and_decision_keep_endpoint_evidence_and_conflict() -> None:
    module = _contracts()
    assertion = module.RelationshipAssertion(
        assertion_id="relation-assertion-1",
        relationship_type_id="professor_founded_company",
        source_record_id="record-official-bio",
        source_endpoint=module.IdentityReference(
            identity_id="source-professor-1",
            identity_space="source",
            entity_type="professor",
        ),
        target_endpoint=module.IdentityReference(
            identity_id="source-company-1",
            identity_space="source",
            entity_type="company",
        ),
        attributes={"role": "founder"},
        observed_at=NOW,
        source_event_time=None,
        valid_from=None,
        valid_to=None,
        assertion_run_id="assert-run-1",
    )
    decision = module.RelationshipDecision(
        decision_id="relation-decision-1",
        canonical_relationship_id="canonical-relation-1",
        relationship_type_id=assertion.relationship_type_id,
        source_canonical_identity_id="professor-c1",
        target_canonical_identity_id="company-c1",
        state="accepted",
        candidate_assertion_ids=(assertion.assertion_id, "relation-assertion-2"),
        selected_assertion_ids=(assertion.assertion_id,),
        conflicting_assertion_ids=("relation-assertion-2",),
        role_bindings={"source": "founder"},
        policy=_policy(module, "relationship"),
        method="human_review",
        method_version="relation-v1",
        decision_run_id="build-run-1",
        confidence=0.95,
        rationale="Official biography supports founder role.",
        valid_from=None,
        valid_to=None,
        release_id="release-r1",
        decided_at=NOW,
    )

    assert decision.selected_assertion_ids == (assertion.assertion_id,)
    assert decision.conflicting_assertion_ids == ("relation-assertion-2",)
    with pytest.raises(ValidationError, match="accepted relationship"):
        module.RelationshipDecision(
            **{**decision.model_dump(), "selected_assertion_ids": ()}
        )


def test_derived_and_session_relationships_are_not_source_grounded_canonical_facts() -> None:
    module = _contracts()
    derived = module.DerivedRelationship(
        derived_relationship_id="derived-paper-sim-1",
        relationship_type_id="paper_similarity",
        release_id="release-r1",
        source_canonical_identity_id="paper-c1",
        target_canonical_identity_id="paper-c2",
        computation_version="embedding-v2",
        input_content_sha256=("4" * 64, "5" * 64),
        score=0.91,
        computed_at=NOW,
    )
    session = module.SessionRelationship(
        session_relationship_id="session-rel-1",
        relationship_type_id="displayed_result_referent",
        session_id="session-1",
        turn_id="turn-2",
        release_id="release-r1",
        source_reference="result-set-1",
        target_reference="paper-c1",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    assert not hasattr(derived, "source_assertion_ids")
    assert not hasattr(session, "source_assertion_ids")
    with pytest.raises(ValidationError, match="extra"):
        module.DerivedRelationship(
            **{**derived.model_dump(), "source_assertion_ids": ("assertion-1",)}
        )


def test_policy_decisions_separate_soft_limitations_from_named_hard_exclusions() -> None:
    module = _contracts()
    limited = module.PolicyDecision(
        decision_id="eligibility-paper-1",
        policy=_policy(module, "path_eligibility"),
        subject_identity_id="paper-c1",
        release_id="release-r1",
        path="semantic_recall",
        outcome="limited",
        score=0.62,
        limitations=("missing_abstract_enrichment",),
        hard_exclusion_codes=(),
        supporting_assertion_ids=("assertion-title-1",),
        evaluated_at=NOW,
    )
    exact = module.PolicyDecision(
        **{
            **limited.model_dump(),
            "decision_id": "eligibility-paper-exact-1",
            "path": "exact_lookup",
            "outcome": "admitted",
            "score": 0.95,
            "limitations": ("summary_incomplete",),
        }
    )
    excluded = module.PolicyDecision(
        **{
            **limited.model_dump(),
            "decision_id": "eligibility-paper-wrong-id",
            "outcome": "excluded",
            "score": 0.0,
            "limitations": (),
            "hard_exclusion_codes": ("wrong_identity",),
        }
    )

    assert limited.outcome.value == "limited"
    assert exact.outcome.value == "admitted"
    assert excluded.hard_exclusion_codes == ("wrong_identity",)
    with pytest.raises(ValidationError, match="named hard exclusion"):
        module.PolicyDecision(
            **{
                **excluded.model_dump(),
                "hard_exclusion_codes": (),
            }
        )
    with pytest.raises(ValidationError, match="limitation"):
        module.PolicyDecision(
            **{**limited.model_dump(), "limitations": ()}
        )


def test_inclusion_policy_is_not_a_path_eligibility_decision() -> None:
    module = _contracts()
    inclusion = module.PolicyDecision(
        decision_id="include-company-1",
        policy=_policy(module, "inclusion"),
        subject_identity_id="company-c1",
        release_id="release-r1",
        path=None,
        outcome="admitted",
        score=None,
        limitations=("profile_enrichment_pending",),
        hard_exclusion_codes=(),
        supporting_assertion_ids=("assertion-company-name",),
        evaluated_at=NOW,
    )

    assert inclusion.path is None
    with pytest.raises(ValidationError, match="path"):
        module.PolicyDecision(
            **{**inclusion.model_dump(), "path": "semantic_recall"}
        )


def test_knowledge_gap_covers_required_classes_and_requires_proven_resolution() -> None:
    module = _contracts()
    required_classes = {
        "knowledge_coverage",
        "identity",
        "source_conflict_freshness",
        "relationship",
        "path_reach",
        "retrieval_precision",
        "context",
        "synthesis",
        "index_parity",
        "provider_availability",
    }
    assert {value.value for value in module.GapClass} >= required_classes
    gap = module.KnowledgeGap(
        gap_id="gap-paper-web-dependence",
        gap_class="knowledge_coverage",
        status="open",
        release_id="release-r1",
        affected_domains=("paper",),
        affected_paths=("exact_lookup", "semantic_recall"),
        query_trace_id="query-trace-1",
        answer_trace_id="answer-trace-1",
        benchmark_case_id=None,
        telemetry_key="paper-current-status",
        observed_symptom="Repeated local miss requires current Web evidence.",
        evidence_ids=("web-evidence-1",),
        classification_confidence=0.9,
        review_state="unreviewed",
        proposed_owner="recollection",
        proposed_remediation="Collect and land the missing official source.",
        demand_count=12,
        scenario_families=("paper_exact", "universal_web"),
        severity="high",
        created_at=NOW,
        updated_at=NOW,
        resolved_release_id=None,
        resolved_release_state=None,
        resolution_verification_ids=(),
    )

    assert gap.status.value == "open"
    assert gap.demand_count == 12
    with pytest.raises(ValidationError, match="accepted release"):
        module.KnowledgeGap(
            **{**gap.model_dump(), "status": "resolved"}
        )
    resolved = module.KnowledgeGap(
        **{
            **gap.model_dump(),
            "status": "resolved",
            "review_state": "accepted",
            "resolved_release_id": "release-r2",
            "resolved_release_state": "accepted",
            "resolution_verification_ids": ("benchmark-proof-1",),
            "updated_at": NOW + timedelta(days=1),
        }
    )
    assert resolved.resolved_release_id == "release-r2"


def test_build_manifest_accounts_for_every_versioned_projection_on_one_release() -> None:
    module = _contracts()
    published = module.ProjectionManifest(
        projection_id="published-paper",
        release_id="release-r1",
        projection_kind="published_domain",
        domain="paper",
        path=None,
        projection_version="published-paper-v1",
        record_count=3,
        content_sha256="6" * 64,
    )
    expected_index = module.IndexProjectionManifest(
        projection_id="paper-semantic",
        release_id="release-r1",
        domain="paper",
        path="semantic_recall",
        projection_version="paper-semantic-v1",
        schema_version="vector-schema-v2",
        embedding_model="recorded-embedding-v1",
        eligibility_policy_version="paper-semantic-policy-v1",
        point_count=7,
        entity_ids_sha256="7" * 64,
        content_sha256="8" * 64,
        full_rebuild=True,
    )
    manifest = module.BuildManifest(
        manifest_version="canonical-v2-build-manifest-v1",
        release_id="release-r1",
        build_run_id="build-run-1",
        source_batch_ids=("batch-1", "batch-2"),
        source_batches_sha256="9" * 64,
        parser_versions={"historical_jsonl": "parser-v1"},
        policy_versions={
            "identity": "identity-v1",
            "inclusion": "inclusion-v1",
            "path_eligibility": "eligibility-v1",
        },
        model_versions={"identity_judge": "recorded-fake-v1"},
        decision_set=_section(module, "canonical-decisions"),
        object_sets=(
            _section(module, "professor-objects"),
            _section(module, "company-objects"),
            _section(module, "paper-objects"),
            _section(module, "patent-objects"),
        ),
        relationship_set=_section(module, "canonical-relationships"),
        eligibility_sets=(_section(module, "path-eligibility"),),
        published_projections=(published,),
        expected_index_projections=(expected_index,),
        created_at=NOW,
        manifest_sha256="a" * 64,
    )

    assert manifest.release_id == "release-r1"
    assert len(manifest.object_sets) == 4
    assert manifest.expected_index_projections[0].full_rebuild is True
    assert "table_name" not in module.BuildManifest.model_fields
    assert "collection_name" not in module.IndexProjectionManifest.model_fields
    json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False)
    with pytest.raises(ValidationError, match="one release"):
        module.BuildManifest(
            **{
                **manifest.model_dump(),
                "published_projections": (
                    module.ProjectionManifest(
                        **{**published.model_dump(), "release_id": "release-r2"}
                    ),
                ),
            }
        )


def test_candidate_verification_publication_and_rollback_keep_exact_release_parity() -> None:
    module = _contracts()
    candidate = module.CandidateRelease(
        release_id="release-r1",
        run_id="build-run-1",
        state="candidate",
        source_batch_ids=("batch-1",),
        parser_versions={"jsonl": "parser-v1"},
        policy_versions={"identity": "identity-v1"},
        model_versions={"identity_judge": "recorded-fake-v1"},
        manifest_sha256="a" * 64,
        object_counts={"professor": 1, "company": 1, "paper": 2, "patent": 1},
        relationship_count=3,
        active_release_changed=False,
    )
    verification = module.ReleaseVerification(
        candidate_release_id=candidate.release_id,
        manifest_sha256=candidate.manifest_sha256,
        accepted=True,
        canonical_index_parity=True,
        missing_points=0,
        extra_points=0,
        stale_points=0,
        cross_release_points=0,
        evidence_ids=("parity-proof-1",),
        verified_at=NOW,
    )
    promoted = module.PublishedRelease(
        release_id="release-r1",
        previous_release_id="release-r0",
        canonical_release_id="release-r1",
        published_projection_release_id="release-r1",
        index_release_id="release-r1",
        state="active",
        changed_at=NOW,
        verification_evidence_ids=verification.evidence_ids,
    )
    rollback = module.PublishedRelease(
        release_id="release-r0",
        previous_release_id="release-r1",
        canonical_release_id="release-r0",
        published_projection_release_id="release-r0",
        index_release_id="release-r0",
        state="active",
        changed_at=NOW + timedelta(minutes=5),
        verification_evidence_ids=("rollback-proof-1",),
    )

    assert candidate.active_release_changed is False
    assert verification.accepted is True
    assert promoted.release_id == promoted.index_release_id
    assert rollback.previous_release_id == promoted.release_id
    with pytest.raises(ValidationError, match="zero deviations"):
        module.ReleaseVerification(
            **{**verification.model_dump(), "extra_points": 1}
        )
    with pytest.raises(ValidationError, match="same release"):
        module.PublishedRelease(
            **{**promoted.model_dump(), "index_release_id": "release-r2"}
        )


def test_contracts_reject_unknown_fields_and_keep_ids_in_json_mode() -> None:
    module = _contracts()
    candidate = module.CandidateRelease(
        release_id="release-r1",
        run_id="build-run-1",
        state="candidate",
        source_batch_ids=("batch-1",),
        parser_versions={"jsonl": "parser-v1"},
        policy_versions={"identity": "identity-v1"},
        model_versions={},
        manifest_sha256="a" * 64,
        object_counts={"paper": 1},
        relationship_count=0,
        active_release_changed=False,
    )
    dumped = candidate.model_dump(mode="json")

    assert dumped["release_id"] == "release-r1"
    assert dumped["source_batch_ids"] == ["batch-1"]
    with pytest.raises(ValidationError, match="extra"):
        module.CandidateRelease(
            **{**candidate.model_dump(), "legacy_table_name": "paper"}
        )
