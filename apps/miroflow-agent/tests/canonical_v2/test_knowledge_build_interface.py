from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from pydantic import ValidationError
import pytest

from src.data_agents.canonical_v2.contracts import (
    BuildManifest as SharedBuildManifest,
    CandidateRelease as SharedCandidateRelease,
    IndexProjectionManifest,
    ManifestSection,
    ProjectionManifest,
    ProjectionScope,
)


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_build"
NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


class _MissingTargetModule(RuntimeError):
    """Exact Task 7.1 RED sentinel; nested missing dependencies fail normally."""


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


def _request(
    module: Any,
    *,
    release_id: str = "candidate-r1",
    run_id: str = "build-run-1",
) -> Any:
    return module.BuildCandidateRequest(
        run_id=run_id,
        candidate_release_id=release_id,
        source_batch_ids=("batch-1", "batch-2"),
        parser_versions={"historical_jsonl": "parser-v1"},
        policy_versions={"identity": "identity-v1", "eligibility": "eligibility-v1"},
        model_versions={"identity_judge": "recorded-fake-v1"},
    )


def _materialization(
    release_id: str,
    *,
    auxiliary_index_content_sha256: str = "b" * 64,
) -> dict[str, Any]:
    return {
        "decision_set": ManifestSection(
            section_id="decisions",
            release_id=release_id,
            version="decision-v1",
            record_count=2,
            content_sha256="2" * 64,
        ),
        "object_sets": (
            ManifestSection(
                section_id="objects:company",
                release_id=release_id,
                version="company-v1",
                record_count=1,
                content_sha256="3" * 64,
            ),
            ManifestSection(
                section_id="objects:person",
                release_id=release_id,
                version="person-v1",
                record_count=1,
                content_sha256="4" * 64,
            ),
        ),
        "relationship_set": ManifestSection(
            section_id="relationships",
            release_id=release_id,
            version="relationship-v2",
            record_count=1,
            content_sha256="5" * 64,
        ),
        "eligibility_sets": (
            ManifestSection(
                section_id="eligibility:semantic_recall",
                release_id=release_id,
                version="eligibility-v1",
                record_count=2,
                content_sha256="6" * 64,
            ),
        ),
        "published_projections": (
            ProjectionManifest(
                projection_id="published:company",
                release_id=release_id,
                projection_scope=ProjectionScope.public_domain,
                projection_kind="lookup",
                domain="company",
                reference_type=None,
                projection_version="published-v1",
                record_count=1,
                content_sha256="7" * 64,
            ),
            ProjectionManifest(
                projection_id="published:person",
                release_id=release_id,
                projection_scope=ProjectionScope.internal_auxiliary,
                projection_kind="lookup",
                domain=None,
                reference_type="person",
                projection_version="published-v1",
                record_count=1,
                content_sha256="8" * 64,
            ),
        ),
        "expected_index_projections": (
            IndexProjectionManifest(
                projection_id="index:company",
                release_id=release_id,
                projection_scope=ProjectionScope.public_domain,
                domain="company",
                reference_type=None,
                path="semantic_recall",
                projection_version="index-v1",
                schema_version="schema-v1",
                embedding_model="embedding-v1",
                eligibility_policy_version="eligibility-v1",
                point_count=1,
                entity_ids_sha256="9" * 64,
                content_sha256="a" * 64,
                full_rebuild=True,
            ),
            IndexProjectionManifest(
                projection_id="index:person",
                release_id=release_id,
                projection_scope=ProjectionScope.internal_auxiliary,
                domain=None,
                reference_type="person",
                path="semantic_recall",
                projection_version="index-v1",
                schema_version="schema-v1",
                embedding_model="embedding-v1",
                eligibility_policy_version="eligibility-v1",
                point_count=1,
                entity_ids_sha256="c" * 64,
                content_sha256=auxiliary_index_content_sha256,
                full_rebuild=True,
            ),
        ),
    }


def _composition(
    module: Any,
    *,
    materialize: Any,
) -> tuple[
    Any, dict[str, Any], dict[str, SharedBuildManifest], dict[str, Any], dict[str, str]
]:
    candidate_store: dict[str, Any] = {}
    manifest_store: dict[str, SharedBuildManifest] = {}
    failure_store: dict[str, Any] = {}
    active_release_state = {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }
    builder = module.create_ephemeral_knowledge_build(
        materialize=materialize,
        candidate_store=candidate_store,
        manifest_store=manifest_store,
        failure_store=failure_store,
        active_release_state=active_release_state,
        clock=lambda: NOW,
    )
    return (
        builder,
        candidate_store,
        manifest_store,
        failure_store,
        active_release_state,
    )


def test_knowledge_build_returns_isolated_candidate_with_versioned_manifest() -> None:
    module = _module()
    assert module.CandidateRelease is SharedCandidateRelease
    request = _request(module)
    builder, candidate_store, manifest_store, _, active_release_state = _composition(
        module,
        materialize=lambda value: _materialization(value.candidate_release_id),
    )

    assert isinstance(builder, module.KnowledgeBuild)
    candidate = builder.build(request)
    manifest = manifest_store[candidate.release_id]

    assert isinstance(candidate, module.CandidateRelease)
    assert candidate.release_id == "candidate-r1"
    assert candidate.state.value == "candidate"
    assert candidate.source_batch_ids == request.source_batch_ids
    assert candidate.parser_versions == request.parser_versions
    assert candidate.policy_versions == request.policy_versions
    assert candidate.model_versions == request.model_versions
    assert candidate.manifest_sha256 == manifest.manifest_sha256
    assert candidate.object_counts == {"company": 1, "person": 1}
    assert candidate.relationship_count == 1
    assert candidate.active_release_changed is False
    assert candidate_store[candidate.release_id] == candidate
    assert active_release_state == {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }


def test_failed_candidate_remains_isolated_inspectable_and_retryable() -> None:
    module = _module()
    attempts = 0

    def fail_once(value: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated index build failure")
        return _materialization(value.candidate_release_id)

    builder, candidate_store, manifest_store, failure_store, active_release_state = (
        _composition(
            module,
            materialize=fail_once,
        )
    )

    with pytest.raises(RuntimeError, match="simulated index build failure"):
        builder.build(_request(module))

    failure = failure_store["candidate-r1"]
    assert failure["candidate_release_id"] == "candidate-r1"
    assert failure["stage"] == "materialize"
    assert failure["retryable"] is True
    assert "candidate-r1" not in candidate_store
    assert "candidate-r1" not in manifest_store
    assert active_release_state == {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }

    retried = builder.build(
        _request(module, release_id="candidate-r2", run_id="build-run-2")
    )
    assert retried.release_id == "candidate-r2"
    assert retried.state.value == "candidate"
    assert candidate_store[retried.release_id] == retried
    assert failure_store["candidate-r1"] == failure


def test_repeated_build_binds_immutable_deterministic_public_and_auxiliary_hashes() -> (
    None
):
    module = _module()
    request = _request(module)

    def run_once(auxiliary_hash: str) -> tuple[Any, SharedBuildManifest]:
        builder, _, manifest_store, _, _ = _composition(
            module,
            materialize=lambda value: _materialization(
                value.candidate_release_id,
                auxiliary_index_content_sha256=auxiliary_hash,
            ),
        )
        candidate = builder.build(request)
        return candidate, manifest_store[candidate.release_id]

    first_candidate, first_manifest = run_once("b" * 64)
    repeated_candidate, repeated_manifest = run_once("b" * 64)
    changed_candidate, changed_manifest = run_once("d" * 64)

    assert first_candidate == repeated_candidate
    assert first_manifest == repeated_manifest
    assert first_manifest.model_dump_json() == repeated_manifest.model_dump_json()
    assert first_candidate.manifest_sha256 == first_manifest.manifest_sha256
    assert changed_candidate.manifest_sha256 == changed_manifest.manifest_sha256
    assert changed_manifest.manifest_sha256 != first_manifest.manifest_sha256
    assert {
        (projection.projection_scope, projection.domain, projection.reference_type)
        for projection in first_manifest.published_projections
    } == {
        (ProjectionScope.public_domain, "company", None),
        (ProjectionScope.internal_auxiliary, None, "person"),
    }
    assert {
        projection.projection_id: projection.content_sha256
        for projection in first_manifest.expected_index_projections
    } == {"index:company": "a" * 64, "index:person": "b" * 64}
    with pytest.raises(ValidationError, match="frozen"):
        setattr(first_manifest, "manifest_sha256", "e" * 64)
    for immutable_values in (
        first_manifest.parser_versions,
        first_manifest.policy_versions,
        first_manifest.model_versions,
        first_candidate.parser_versions,
        first_candidate.policy_versions,
        first_candidate.model_versions,
        first_candidate.object_counts,
        request.parser_versions,
        request.policy_versions,
        request.model_versions,
    ):
        with pytest.raises(TypeError, match="immutable"):
            immutable_values["unexpected"] = "changed"

    auxiliary_hash = "b" * 64
    builder, candidate_store, manifest_store, _, _ = _composition(
        module,
        materialize=lambda value: _materialization(
            value.candidate_release_id,
            auxiliary_index_content_sha256=auxiliary_hash,
        ),
    )
    stored_candidate = builder.build(request)
    stored_manifest = manifest_store[request.candidate_release_id]
    auxiliary_hash = "d" * 64
    with pytest.raises(ValueError, match="immutable candidate release collision"):
        builder.build(request)
    assert candidate_store[request.candidate_release_id] == stored_candidate
    assert manifest_store[request.candidate_release_id] == stored_manifest
