from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import BuildManifest
from src.data_agents.canonical_v2.contracts import IndexProjectionManifest
from src.data_agents.canonical_v2.contracts import ManifestSection
from src.data_agents.canonical_v2.contracts import ProjectionManifest
from src.data_agents.canonical_v2.contracts import ProjectionScope
from src.data_agents.canonical_v2.contracts import (
    PublishedRelease as SharedPublishedRelease,
)
from src.data_agents.canonical_v2.contracts import (
    ReleaseVerification as SharedReleaseVerification,
)


TARGET_MODULE = "src.data_agents.canonical_v2.release_publication"
INDEX_PROJECTION_TARGET_MODULE = "src.data_agents.canonical_v2.index_projection"
NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)
DEFAULT_RELEASE_ID = "candidate-r1"
DEFAULT_POINT_ID = "point:paper:paper-1:default"
DEFAULT_OBJECT_ID = "paper-1"
DEFAULT_EMBEDDED_CONTENT = "Evidence-bound robotics paper."


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


DEFAULT_EMBEDDED_CONTENT_SHA256 = _sha256_text(DEFAULT_EMBEDDED_CONTENT)
DEFAULT_ENTITY_IDS_SHA256 = _sha256_text(DEFAULT_OBJECT_ID)


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


def _candidate_manifest() -> BuildManifest:
    release_id = DEFAULT_RELEASE_ID
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    expected_point = _index_point(index_module)
    expected_index = IndexProjectionManifest(
        projection_id="index:paper",
        release_id=release_id,
        projection_scope=ProjectionScope.public_domain,
        domain="paper",
        reference_type=None,
        path="semantic_recall",
        projection_version="index-v1",
        schema_version="schema-v1",
        embedding_model="embedding-v1",
        eligibility_policy_version="eligibility-v1",
        point_count=1,
        entity_ids_sha256=DEFAULT_ENTITY_IDS_SHA256,
        content_sha256=index_module.index_point_content_sha256((expected_point,)),
        full_rebuild=True,
    )
    return BuildManifest(
        manifest_version="canonical-v2-build-manifest-v2",
        release_id=release_id,
        build_run_id="build-run-1",
        source_batch_ids=("batch-1",),
        source_batches_sha256="1" * 64,
        parser_versions={"historical_jsonl": "parser-v1"},
        policy_versions={"eligibility": "eligibility-v1"},
        model_versions={},
        decision_set=ManifestSection(
            section_id="decisions",
            release_id=release_id,
            version="decision-v1",
            record_count=1,
            content_sha256="2" * 64,
        ),
        object_sets=(
            ManifestSection(
                section_id="objects:paper",
                release_id=release_id,
                version="paper-v1",
                record_count=1,
                content_sha256="3" * 64,
            ),
        ),
        relationship_set=ManifestSection(
            section_id="relationships",
            release_id=release_id,
            version="relationship-v2",
            record_count=0,
            content_sha256="4" * 64,
        ),
        eligibility_sets=(
            ManifestSection(
                section_id="eligibility:semantic_recall",
                release_id=release_id,
                version="eligibility-v1",
                record_count=1,
                content_sha256="5" * 64,
            ),
        ),
        published_projections=(
            ProjectionManifest(
                projection_id="published:paper",
                release_id=release_id,
                projection_scope=ProjectionScope.public_domain,
                projection_kind="lookup",
                domain="paper",
                reference_type=None,
                projection_version="published-v1",
                record_count=1,
                content_sha256="6" * 64,
            ),
        ),
        expected_index_projections=(expected_index,),
        created_at=NOW,
        manifest_sha256="7" * 64,
    )


def _index_point(
    module: Any,
    *,
    point_id: str = DEFAULT_POINT_ID,
    canonical_object_id: str = DEFAULT_OBJECT_ID,
    release_id: str = DEFAULT_RELEASE_ID,
    embedded_content: str = DEFAULT_EMBEDDED_CONTENT,
) -> Any:
    return module.IndexProjectionPoint(
        point_id=point_id,
        canonical_object_id=canonical_object_id,
        release_id=release_id,
        projection_id="index:paper",
        projection_scope=ProjectionScope.public_domain,
        domain="paper",
        reference_type=None,
        path="semantic_recall",
        projection_view="default",
        projection_version="index-v1",
        schema_version="schema-v1",
        embedding_model="embedding-v1",
        eligibility_policy_version="eligibility-v1",
        eligibility_decision_id=f"path-decision:{canonical_object_id}",
        eligibility_outcome="admitted",
        eligibility_limitations=(),
        source_projection_content_sha256="d" * 64,
        embedded_content=embedded_content,
        embedded_content_sha256=hashlib.sha256(
            embedded_content.encode("utf-8")
        ).hexdigest(),
        source_evidence_ids=(f"evidence:{canonical_object_id}",),
    )


def _composition(
    module: Any,
    *,
    actual_index_projection: IndexProjectionManifest,
    expected_index_points: tuple[Any, ...],
    actual_index_points: tuple[Any, ...],
    candidate_manifest: BuildManifest | None = None,
) -> tuple[
    Any,
    dict[str, str],
    dict[str, Any],
    dict[str, tuple[Any, ...]],
    list[Any],
    dict[str, BuildManifest],
]:
    candidate_manifest = candidate_manifest or _candidate_manifest()
    candidate_manifests = {candidate_manifest.release_id: candidate_manifest}
    active_release_state = {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }
    verification_store: dict[str, Any] = {}
    discrepancy_store: dict[str, tuple[Any, ...]] = {}
    publication_history: list[Any] = []
    publication = module.create_ephemeral_release_publication(
        candidate_manifests=candidate_manifests,
        actual_index_projections={
            candidate_manifest.release_id: (actual_index_projection,)
        },
        expected_index_points={candidate_manifest.release_id: expected_index_points},
        actual_index_points={candidate_manifest.release_id: actual_index_points},
        active_release_state=active_release_state,
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=publication_history,
        clock=lambda: NOW,
    )
    return (
        publication,
        active_release_state,
        verification_store,
        discrepancy_store,
        publication_history,
        candidate_manifests,
    )


def test_release_parity_mismatch_blocks_promotion_and_retains_discrepancy_evidence() -> (
    None
):
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    expected = _candidate_manifest().expected_index_projections[0]
    mismatched = IndexProjectionManifest.model_validate(
        {
            **expected.model_dump(mode="python"),
            "point_count": 2,
            "entity_ids_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
    )
    expected_point = _index_point(index_module)
    extra_point = _index_point(
        index_module,
        point_id="point:paper:paper-extra:default",
        canonical_object_id="paper-extra",
        embedded_content="Unexpected extra paper.",
    )
    publication, active_release_state, verification_store, _, _, _ = _composition(
        module,
        actual_index_projection=mismatched,
        expected_index_points=(expected_point,),
        actual_index_points=(expected_point, extra_point),
    )

    verification = publication.verify("candidate-r1")

    assert isinstance(verification, SharedReleaseVerification)
    assert verification.accepted is False
    assert verification.canonical_index_parity is False
    assert verification.extra_points == 1
    assert verification.missing_points == 0
    assert any(
        "index:paper" in evidence_id for evidence_id in verification.evidence_ids
    )
    assert any("index-v1" in evidence_id for evidence_id in verification.evidence_ids)
    assert verification_store["candidate-r1"] == verification
    with pytest.raises(ValueError, match="not accepted"):
        publication.promote("candidate-r1")
    assert active_release_state == {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }


def test_release_rejects_matching_forged_manifest_hashes_and_retains_inventory_evidence() -> (
    None
):
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    candidate = _candidate_manifest()
    expected_point = _index_point(index_module)
    forged_manifest = IndexProjectionManifest.model_validate(
        {
            **candidate.expected_index_projections[0].model_dump(mode="python"),
            "entity_ids_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
    )
    forged_candidate = BuildManifest.model_validate(
        {
            **candidate.model_dump(mode="python"),
            "expected_index_projections": (forged_manifest,),
        }
    )
    (
        publication,
        active_release_state,
        verification_store,
        discrepancy_store,
        _,
        _,
    ) = _composition(
        module,
        actual_index_projection=forged_manifest,
        expected_index_points=(expected_point,),
        actual_index_points=(expected_point,),
        candidate_manifest=forged_candidate,
    )

    verification = publication.verify(DEFAULT_RELEASE_ID)

    assert verification.accepted is False
    assert verification.canonical_index_parity is False
    assert (
        verification.missing_points,
        verification.extra_points,
        verification.stale_points,
        verification.cross_release_points,
    ) == (0, 0, 0, 0)
    assert any(
        evidence_id.startswith("index-inventory:expected:index:paper:index-v1")
        for evidence_id in verification.evidence_ids
    )
    assert any(
        evidence_id.startswith("index-inventory:actual:index:paper:index-v1")
        for evidence_id in verification.evidence_ids
    )
    assert verification_store[DEFAULT_RELEASE_ID] == verification
    assert discrepancy_store[DEFAULT_RELEASE_ID] == ()
    with pytest.raises(ValueError, match="not accepted"):
        publication.promote(DEFAULT_RELEASE_ID)
    assert set(active_release_state.values()) == {"release-r0"}


def test_release_persists_actual_manifest_inventory_count_mismatch() -> None:
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    expected_manifest = _candidate_manifest().expected_index_projections[0]
    expected_point = _index_point(index_module)
    extra_point = _index_point(
        index_module,
        point_id="point:paper:paper-extra:default",
        canonical_object_id="paper-extra",
        embedded_content="Unexpected extra paper.",
    )
    (
        publication,
        active_release_state,
        verification_store,
        discrepancy_store,
        _,
        _,
    ) = _composition(
        module,
        actual_index_projection=expected_manifest,
        expected_index_points=(expected_point,),
        actual_index_points=(expected_point, extra_point),
    )

    verification = publication.verify(DEFAULT_RELEASE_ID)

    assert verification.accepted is False
    assert verification.extra_points == 1
    assert any(
        evidence_id.startswith("index-inventory:actual:index:paper:index-v1")
        for evidence_id in verification.evidence_ids
    )
    assert verification_store[DEFAULT_RELEASE_ID] == verification
    details = discrepancy_store[DEFAULT_RELEASE_ID]
    assert len(details) == 1
    assert details[0].kind.value == "extra"
    assert details[0].actual_point == extra_point
    with pytest.raises(ValueError, match="not accepted"):
        publication.promote(DEFAULT_RELEASE_ID)
    assert set(active_release_state.values()) == {"release-r0"}


def test_release_stale_evidence_retains_complete_expected_and_actual_points() -> None:
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    expected_manifest = _candidate_manifest().expected_index_projections[0]
    expected_point = _index_point(index_module)
    stale_point = expected_point.model_copy(update={"embedding_model": "embedding-v2"})
    actual_manifest = IndexProjectionManifest.model_validate(
        {
            **expected_manifest.model_dump(mode="python"),
            "embedding_model": "embedding-v2",
        }
    )
    publication, _, _, discrepancy_store, _, _ = _composition(
        module,
        actual_index_projection=actual_manifest,
        expected_index_points=(expected_point,),
        actual_index_points=(stale_point,),
    )

    verification = publication.verify(DEFAULT_RELEASE_ID)

    assert verification.accepted is False
    assert verification.stale_points == 1
    detail = discrepancy_store[DEFAULT_RELEASE_ID][0]
    assert detail.expected_point == expected_point
    assert detail.actual_point == stale_point
    assert detail.expected_point.embedding_model == "embedding-v1"
    assert detail.actual_point.embedding_model == "embedding-v2"
    assert detail.discrepancy_id in verification.evidence_ids


def test_release_publication_verifies_exact_parity_then_promotes_and_rolls_back_one_release() -> (
    None
):
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    assert module.ReleaseVerification is SharedReleaseVerification
    assert module.PublishedRelease is SharedPublishedRelease
    expected = _candidate_manifest().expected_index_projections[0]
    expected_point = _index_point(index_module)
    (
        publication,
        active_release_state,
        verification_store,
        _,
        publication_history,
        candidate_manifests,
    ) = _composition(
        module,
        actual_index_projection=expected,
        expected_index_points=(expected_point,),
        actual_index_points=(expected_point,),
    )

    with pytest.raises(ValueError, match="not accepted"):
        publication.promote("candidate-r1")

    verification = publication.verify("candidate-r1")
    promoted = publication.promote("candidate-r1")

    assert verification.accepted is True
    assert verification.canonical_index_parity is True
    assert (
        verification.missing_points,
        verification.extra_points,
        verification.stale_points,
        verification.cross_release_points,
    ) == (0, 0, 0, 0)
    assert promoted.previous_release_id == "release-r0"
    assert {
        promoted.canonical_release_id,
        promoted.published_projection_release_id,
        promoted.index_release_id,
    } == {promoted.release_id}
    assert active_release_state == {
        "canonical_release_id": "candidate-r1",
        "published_projection_release_id": "candidate-r1",
        "index_release_id": "candidate-r1",
    }

    rolled_back = publication.rollback(promoted.release_id)

    assert rolled_back.release_id == "release-r0"
    assert rolled_back.previous_release_id == "candidate-r1"
    assert active_release_state == {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }
    assert verification_store["candidate-r1"] == verification
    assert candidate_manifests["candidate-r1"].manifest_sha256 == "7" * 64
    assert [event.release_id for event in publication_history] == [
        "candidate-r1",
        "release-r0",
    ]


def test_release_point_parity_classifies_missing_extra_stale_and_cross_release() -> (
    None
):
    module = _module()
    index_module = import_module(INDEX_PROJECTION_TARGET_MODULE)
    expected_manifest = _candidate_manifest().expected_index_projections[0]
    expected_point = _index_point(index_module)
    extra_point = _index_point(
        index_module,
        point_id="point:paper:paper-extra:default",
        canonical_object_id="paper-extra",
        embedded_content="Unexpected extra paper.",
    )
    stale_content = "Stale paper content."
    stale_point = expected_point.model_copy(
        update={
            "embedded_content": stale_content,
            "embedded_content_sha256": hashlib.sha256(
                stale_content.encode("utf-8")
            ).hexdigest(),
        }
    )
    cross_release_point = expected_point.model_copy(update={"release_id": "release-r0"})

    cases = (
        (
            "missing",
            (),
            (1, 0, 0, 0),
            expected_point.point_id,
            "candidate-r1",
            None,
            expected_point.embedded_content_sha256,
            None,
        ),
        (
            "extra",
            (expected_point, extra_point),
            (0, 1, 0, 0),
            extra_point.point_id,
            None,
            "candidate-r1",
            None,
            extra_point.embedded_content_sha256,
        ),
        (
            "stale",
            (stale_point,),
            (0, 0, 1, 0),
            expected_point.point_id,
            "candidate-r1",
            "candidate-r1",
            expected_point.embedded_content_sha256,
            stale_point.embedded_content_sha256,
        ),
        (
            "cross_release",
            (cross_release_point,),
            (0, 0, 0, 1),
            expected_point.point_id,
            "candidate-r1",
            "release-r0",
            expected_point.embedded_content_sha256,
            cross_release_point.embedded_content_sha256,
        ),
    )
    prior_active = {
        "canonical_release_id": "release-r0",
        "published_projection_release_id": "release-r0",
        "index_release_id": "release-r0",
    }

    for (
        kind,
        actual_points,
        expected_counts,
        detail_point_id,
        expected_release_id,
        actual_release_id,
        expected_content_sha256,
        actual_content_sha256,
    ) in cases:
        entity_ids_sha256 = hashlib.sha256(
            "|".join(
                sorted(point.canonical_object_id for point in actual_points)
            ).encode("utf-8")
        ).hexdigest()
        content_sha256 = hashlib.sha256(
            "|".join(
                sorted(
                    f"{point.point_id}:{point.release_id}:"
                    f"{point.embedded_content_sha256}"
                    for point in actual_points
                )
            ).encode("utf-8")
        ).hexdigest()
        actual_manifest = IndexProjectionManifest.model_validate(
            {
                **expected_manifest.model_dump(mode="python"),
                "point_count": len(actual_points),
                "entity_ids_sha256": entity_ids_sha256,
                "content_sha256": content_sha256,
            }
        )
        (
            publication,
            active_release_state,
            _,
            discrepancy_store,
            _,
            _,
        ) = _composition(
            module,
            actual_index_projection=actual_manifest,
            expected_index_points=(expected_point,),
            actual_index_points=actual_points,
        )

        verification = publication.verify("candidate-r1")

        assert isinstance(verification, SharedReleaseVerification)
        assert verification.accepted is False
        assert verification.canonical_index_parity is False
        assert (
            verification.missing_points,
            verification.extra_points,
            verification.stale_points,
            verification.cross_release_points,
        ) == expected_counts
        details = discrepancy_store["candidate-r1"]
        assert len(details) == 1
        detail = details[0]
        assert detail.kind.value == kind
        assert detail.point_id == detail_point_id
        assert detail.projection_id == "index:paper"
        assert detail.canonical_object_id == (
            "paper-extra" if kind == "extra" else "paper-1"
        )
        assert detail.expected_release_id == expected_release_id
        assert detail.actual_release_id == actual_release_id
        assert detail.expected_projection_version == (
            None if kind == "extra" else "index-v1"
        )
        assert detail.actual_projection_version == (
            None if kind == "missing" else "index-v1"
        )
        assert detail.expected_embedded_content_sha256 == expected_content_sha256
        assert detail.actual_embedded_content_sha256 == actual_content_sha256
        assert detail.discrepancy_id in verification.evidence_ids
        with pytest.raises(ValueError, match="not accepted"):
            publication.promote("candidate-r1")
        assert active_release_state == prior_active
