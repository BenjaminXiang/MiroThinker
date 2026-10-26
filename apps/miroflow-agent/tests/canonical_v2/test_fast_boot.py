"""Hermetic fast-boot tests for the manifest-verified isolated snapshot open.

The full physical audit re-embeds every stored point at serving-composition
time. The fast boot path must instead verify only the marker, the self-hashed
build receipt, and the lookup/vector manifests and inventories, then open the
snapshot directly and still bind it to the accepted release bundle. These
tests build a tiny synthetic isolated target (3 vector points, 2 lookup
documents) with the real on-disk writers, so no network, database, or real
embedding model is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from src.data_agents.canonical_v2 import (
    index_projection_isolated as isolated_index,
)
from src.data_agents.canonical_v2 import (
    knowledge_read_isolated as isolated_read,
)
from src.data_agents.canonical_v2.contracts import (
    BuildManifest,
    IndexProjectionManifest,
    ManifestSection,
    ProjectionManifest,
    ProjectionScope,
    PublishedRelease,
    ReleaseState,
)
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
)
from src.data_agents.canonical_v2.domain_projection_models import (
    CompanyProjection,
    FieldProjectionLineage,
    ProjectionEvidenceReference,
)
from src.data_agents.canonical_v2.index_projection import (
    IndexProjectionIntegrityError,
    IndexProjectionMaterializationReceipt,
    IndexProjectionPoint,
    IndexProjectionPolicySnapshot,
    IndexProjectionRebuildDecision,
    IndexProjectionResult,
    LookupProjectionDocument,
    LookupProjectionManifest,
    ProjectionView,
)
from src.data_agents.canonical_v2.index_projection_isolated import (
    IsolatedIndexTarget,
    IsolatedIndexTargetSafetyError,
    RecordedEmbeddingAdapter,
)
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceSet,
    FusedCandidate,
    LaneQuery,
    LaneRequest,
    RetrievalLaneResult,
    RetrievalPlan,
    StructuredConstraints,
    WebSearchPolicy,
    WebSnapshotPolicy,
)
from src.data_agents.canonical_v2.release_publication_isolated import (
    IsolatedReleaseBundle,
)


NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-fastboot-test"
TARGET_ID = f"index:{RELEASE_ID}"
EMBEDDING_MODEL = "recorded-embedding-v1"
PATH_POLICY_VERSION = "path-eligibility-v1"
COLLECTION_NAME = "canonical_v2_0123456789abcdef0123456789abcdef"


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bound_hash(model_type: Any, values: dict[str, Any], hash_field: str) -> str:
    provisional = model_type.model_construct(**values, **{hash_field: "0" * 64})
    payload = provisional.model_dump(mode="json", exclude={hash_field})
    return _canonical_sha256(payload)


class _SpyEmbeddingAdapter:
    """Recorded deterministic embeddings with a composition-time call counter."""

    def __init__(self) -> None:
        self._delegate = RecordedEmbeddingAdapter(
            model_id=EMBEDDING_MODEL,
            dimension=32,
        )
        self.model_id = self._delegate.model_id
        self.dimension = self._delegate.dimension
        self.batch_calls = 0
        self.embedded_texts = 0

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.batch_calls += 1
        self.embedded_texts += len(texts)
        return self._delegate.embed_batch(texts)


def _company_projection(
    *,
    canonical_id: str,
    name: str,
    summary: str,
) -> CompanyProjection:
    decision_id = f"decision:{canonical_id}"
    assertion_id = f"assertion:{canonical_id}:name"
    values: dict[str, Any] = {
        "release_id": RELEASE_ID,
        "canonical_identity_id": canonical_id,
        "identity_decision_id": decision_id,
        "inclusion_decision_id": decision_id,
        "projection_version": "canonical-v2-domain-projection-v1",
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": CATALOG_VERSION,
        "catalog_content_sha256": CATALOG_CONTENT_SHA256,
        "as_of": NOW,
        "field_lineage": (
            FieldProjectionLineage(
                field_path="name",
                decision_id=decision_id,
                supporting_assertion_ids=(assertion_id,),
            ),
        ),
        "id": canonical_id,
        "name": name,
        "normalized_name": name.casefold(),
        "profile_summary": summary,
        "quality_status": "complete",
        "run_id": "run-fastboot-test",
        "last_updated": NOW,
        "technology_route_summary": summary,
        "evidence": (
            ProjectionEvidenceReference(
                assertion_id=assertion_id,
                decision_id=decision_id,
                field_path="name",
            ),
        ),
    }
    return CompanyProjection(
        **values,
        content_sha256=_bound_hash(CompanyProjection, values, "content_sha256"),
    )


def _vector_point(
    *,
    point_id: str,
    canonical_id: str,
    projection_id: str,
    view: ProjectionView,
    embedded_content: str,
    source_projection_sha256: str,
) -> IndexProjectionPoint:
    return IndexProjectionPoint(
        point_id=point_id,
        canonical_object_id=canonical_id,
        release_id=RELEASE_ID,
        projection_id=projection_id,
        projection_scope=ProjectionScope.public_domain,
        domain="company",
        reference_type=None,
        projection_view=view,
        projection_version="canonical-v2-index-projection-v1",
        schema_version="canonical-v2-vector-schema-v1",
        embedding_model=EMBEDDING_MODEL,
        eligibility_policy_version=PATH_POLICY_VERSION,
        eligibility_decision_id=f"eligibility:{canonical_id}",
        eligibility_outcome="admitted",
        source_projection_content_sha256=source_projection_sha256,
        embedded_content=embedded_content,
        embedded_content_sha256=_text_sha256(embedded_content),
        source_evidence_ids=(f"evidence:{canonical_id}",),
    )


def _lookup_document(
    *,
    canonical_id: str,
    projection: CompanyProjection,
) -> LookupProjectionDocument:
    lookup_content = projection.model_dump_json()
    return LookupProjectionDocument(
        document_id=f"doc:{canonical_id}:default",
        canonical_object_id=canonical_id,
        release_id=RELEASE_ID,
        projection_id="lookup:company",
        projection_scope=ProjectionScope.public_domain,
        domain="company",
        reference_type=None,
        projection_view=ProjectionView.default,
        eligibility_policy_version=PATH_POLICY_VERSION,
        eligibility_decision_id=f"eligibility:{canonical_id}",
        eligibility_outcome="admitted",
        source_projection_content_sha256=projection.content_sha256,
        lookup_content=lookup_content,
        lookup_content_sha256=_text_sha256(lookup_content),
        source_evidence_ids=(f"evidence:{canonical_id}",),
    )


def _index_manifests(points: tuple[IndexProjectionPoint, ...]) -> tuple[Any, ...]:
    manifests: list[IndexProjectionManifest] = []
    for domain in ("company", "paper", "patent", "professor"):
        for view in ("default", "identity"):
            projection_id = f"index:{domain}:{view}"
            bound_points = tuple(
                point
                for point in points
                if point.projection_id == projection_id
            )
            manifests.append(
                IndexProjectionManifest(
                    projection_id=projection_id,
                    release_id=RELEASE_ID,
                    projection_scope=ProjectionScope.public_domain,
                    domain=domain,
                    reference_type=None,
                    path="semantic_recall",
                    projection_version="canonical-v2-index-projection-v1",
                    schema_version="canonical-v2-vector-schema-v1",
                    embedding_model=EMBEDDING_MODEL,
                    eligibility_policy_version=PATH_POLICY_VERSION,
                    point_count=len(bound_points),
                    entity_ids_sha256=_text_sha256(
                        "|".join(
                            sorted(
                                point.canonical_object_id for point in bound_points
                            )
                        )
                    ),
                    content_sha256=_text_sha256(f"index-manifest:{projection_id}"),
                    full_rebuild=True,
                )
            )
    return tuple(manifests)


def _lookup_manifests(
    documents: tuple[LookupProjectionDocument, ...],
) -> tuple[Any, ...]:
    manifests: list[LookupProjectionManifest] = []
    for domain in ("company", "paper", "patent", "professor"):
        projection_id = f"lookup:{domain}"
        bound_documents = tuple(
            document for document in documents if document.projection_id == projection_id
        )
        manifests.append(
            LookupProjectionManifest(
                projection_id=projection_id,
                release_id=RELEASE_ID,
                projection_scope=ProjectionScope.public_domain,
                domain=domain,
                reference_type=None,
                eligibility_policy_version=PATH_POLICY_VERSION,
                document_count=len(bound_documents),
                entity_ids_sha256=_text_sha256(
                    "|".join(
                        sorted(
                            document.canonical_object_id
                            for document in bound_documents
                        )
                    )
                ),
                content_sha256=_text_sha256(f"lookup-manifest:{projection_id}"),
                full_rebuild=True,
            )
        )
    for reference_type in ("person", "technology_concept", "technology_route"):
        projection_id = f"lookup:internal:{reference_type}"
        manifests.append(
            LookupProjectionManifest(
                projection_id=projection_id,
                release_id=RELEASE_ID,
                projection_scope=ProjectionScope.internal_auxiliary,
                domain=None,
                reference_type=reference_type,
                eligibility_policy_version=PATH_POLICY_VERSION,
                document_count=0,
                entity_ids_sha256=_text_sha256(""),
                content_sha256=_text_sha256(f"lookup-manifest:{projection_id}"),
                full_rebuild=True,
            )
        )
    return tuple(manifests)


def _receipt(
    *,
    points: tuple[IndexProjectionPoint, ...],
    documents: tuple[LookupProjectionDocument, ...],
    index_manifests: tuple[Any, ...],
    lookup_manifests: tuple[Any, ...],
) -> Any:
    values: dict[str, Any] = {
        "release_id": RELEASE_ID,
        "target_id": TARGET_ID,
        "target_kind": "isolated-candidate",
        "vector_backend": "milvus-lite",
        "lookup_backend": "sqlite",
        "point_ids": tuple(sorted(point.point_id for point in points)),
        "lookup_document_ids": tuple(
            sorted(document.document_id for document in documents)
        ),
        "index_projections": index_manifests,
        "lookup_projections": lookup_manifests,
        "source_inventory_sha256": "1" * 64,
        "backup_manifest_sha256": "2" * 64,
        "restore_verification_sha256": "3" * 64,
        "acceptance_record_sha256": "4" * 64,
        "built_at": NOW,
    }
    return IndexProjectionMaterializationReceipt(
        **values,
        content_sha256=_bound_hash(
            IndexProjectionMaterializationReceipt, values, "content_sha256"
        ),
    )


def _index_result(
    *,
    points: tuple[IndexProjectionPoint, ...],
    documents: tuple[LookupProjectionDocument, ...],
    index_manifests: tuple[Any, ...],
    lookup_manifests: tuple[Any, ...],
) -> IndexProjectionResult:
    values: dict[str, Any] = {
        "release_id": RELEASE_ID,
        "points": points,
        "lookup_documents": documents,
        "expected_index_projections": index_manifests,
        "actual_index_projections": index_manifests,
        "expected_lookup_projections": lookup_manifests,
        "actual_lookup_projections": lookup_manifests,
        "rebuild_decisions": (
            IndexProjectionRebuildDecision(
                decision_id="rebuild:fastboot-test",
                release_id=RELEASE_ID,
                reason_codes=("initial_release",),
                affected_projection_ids=tuple(
                    sorted(
                        manifest.projection_id
                        for manifest in (*index_manifests, *lookup_manifests)
                    )
                ),
            ),
        ),
        "policy_snapshot": IndexProjectionPolicySnapshot(
            release_id=RELEASE_ID,
            index_projection_version="canonical-v2-index-projection-v1",
            vector_schema_version="canonical-v2-vector-schema-v1",
            embedding_model=EMBEDDING_MODEL,
            public_path_policy_versions=(PATH_POLICY_VERSION,),
            internal_auxiliary_policy_version="internal-evidence-anchor-v1",
        ),
    }
    return IndexProjectionResult(
        **values,
        content_sha256=_bound_hash(IndexProjectionResult, values, "content_sha256"),
    )


def _build_manifest(
    index_manifests: tuple[Any, ...],
) -> BuildManifest:
    values: dict[str, Any] = {
        "manifest_version": "canonical-v2-build-manifest-v2",
        "release_id": RELEASE_ID,
        "build_run_id": "run-fastboot-test",
        "source_batch_ids": ("accepted-s2b-source-batch",),
        "source_batches_sha256": "5" * 64,
        "parser_versions": {"historical": "parser-v1"},
        "policy_versions": {"eligibility": PATH_POLICY_VERSION},
        "model_versions": {"embedding": EMBEDDING_MODEL},
        "decision_set": ManifestSection(
            section_id="decisions",
            release_id=RELEASE_ID,
            version="canonical-v2-decision-v1",
            record_count=1,
            content_sha256=_text_sha256("decisions"),
        ),
        "object_sets": (
            ManifestSection(
                section_id="objects:projection-bundle",
                release_id=RELEASE_ID,
                version="canonical-v2-objects-v1",
                record_count=2,
                content_sha256=_text_sha256("objects"),
            ),
        ),
        "relationship_set": ManifestSection(
            section_id="relationships",
            release_id=RELEASE_ID,
            version="canonical-v2-relationships-v1",
            record_count=0,
            content_sha256=_text_sha256("relationships"),
        ),
        "eligibility_sets": (
            ManifestSection(
                section_id="eligibility:semantic_recall",
                release_id=RELEASE_ID,
                version=PATH_POLICY_VERSION,
                record_count=3,
                content_sha256=_text_sha256("eligibility"),
            ),
        ),
        "published_projections": (
            ProjectionManifest(
                projection_id="published:company",
                release_id=RELEASE_ID,
                projection_scope=ProjectionScope.public_domain,
                projection_kind="domain_projection",
                domain="company",
                reference_type=None,
                projection_version="canonical-v2-domain-projection-v1",
                record_count=2,
                content_sha256=_text_sha256("published:company"),
            ),
        ),
        "expected_index_projections": index_manifests,
        "created_at": NOW,
    }
    return BuildManifest(
        **values,
        manifest_sha256=_bound_hash(BuildManifest, values, "manifest_sha256"),
    )


@dataclass(frozen=True)
class _FastBootFixture:
    target: IsolatedIndexTarget
    bundle: IsolatedReleaseBundle
    published: PublishedRelease
    points: tuple[IndexProjectionPoint, ...]
    documents: tuple[LookupProjectionDocument, ...]


def _build_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _FastBootFixture:
    monkeypatch.setattr(
        isolated_index,
        "require_accepted_backup_gate",
        lambda _root: None,
    )
    target = isolated_index.prepare_isolated_index_target(
        root=tmp_path / "index-target",
        target_id=TARGET_ID,
        release_id=RELEASE_ID,
        backup_gate_root=tmp_path / "gate",
        forbidden_milvus_paths=((tmp_path / "original-milvus.db").resolve(),),
    )
    adapter = RecordedEmbeddingAdapter(model_id=EMBEDDING_MODEL, dimension=32)
    robotics = _company_projection(
        canonical_id="company-robotics",
        name="Robotics Co",
        summary="Robotics company in Shenzhen",
    )
    other = _company_projection(
        canonical_id="company-other",
        name="Other Co",
        summary="Unrelated wholesale business",
    )
    points = (
        _vector_point(
            point_id="point:company-other:default",
            canonical_id="company-other",
            projection_id="index:company:default",
            view=ProjectionView.default,
            embedded_content=json.dumps(
                {"name": "Other Co", "summary": "Unrelated wholesale business"},
                ensure_ascii=False,
            ),
            source_projection_sha256=other.content_sha256,
        ),
        _vector_point(
            point_id="point:company-robotics:default",
            canonical_id="company-robotics",
            projection_id="index:company:default",
            view=ProjectionView.default,
            embedded_content=json.dumps(
                {"name": "Robotics Co", "summary": "Robotics company in Shenzhen"},
                ensure_ascii=False,
            ),
            source_projection_sha256=robotics.content_sha256,
        ),
        _vector_point(
            point_id="point:company-robotics:identity",
            canonical_id="company-robotics",
            projection_id="index:company:identity",
            view=ProjectionView.identity,
            embedded_content=json.dumps(
                {"name": "Robotics Co"},
                ensure_ascii=False,
            ),
            source_projection_sha256=robotics.content_sha256,
        ),
    )
    documents = (
        _lookup_document(canonical_id="company-other", projection=other),
        _lookup_document(canonical_id="company-robotics", projection=robotics),
    )
    index_manifests = _index_manifests(points)
    lookup_manifests = _lookup_manifests(documents)
    lookup_path = target.root / "lookup.sqlite3"
    isolated_index._write_lookup_projection(
        lookup_path,
        release_id=RELEASE_ID,
        documents=documents,
        manifests=lookup_manifests,
    )
    client = isolated_index._open_milvus_client(target.root / "milvus.db")
    try:
        isolated_index._write_milvus_projection(
            client,
            collection_name=COLLECTION_NAME,
            points=points,
            embedding_adapter=adapter,
        )
    finally:
        client.close()
    isolated_index._write_build_metadata(lookup_path, collection_name=COLLECTION_NAME)
    isolated_index._write_receipt(
        lookup_path,
        _receipt(
            points=points,
            documents=documents,
            index_manifests=index_manifests,
            lookup_manifests=lookup_manifests,
        ),
    )
    result = _index_result(
        points=points,
        documents=documents,
        index_manifests=index_manifests,
        lookup_manifests=lookup_manifests,
    )
    bundle = IsolatedReleaseBundle(
        manifest=_build_manifest(index_manifests),
        index_result=result,
        index_target=target,
    )
    published = PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id="accepted-before-fastboot",
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state=ReleaseState.active,
        changed_at=NOW,
        verification_evidence_ids=("release-verification:fastboot",),
    )
    return _FastBootFixture(
        target=target,
        bundle=bundle,
        published=published,
        points=points,
        documents=documents,
    )


def _lane_request(*, lane: str, query_text: str) -> LaneRequest:
    return LaneRequest(
        lane=lane,
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=query_text,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="disabled"),
        query_text=query_text,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=8,
    )


def test_fast_boot_opens_valid_snapshot_and_lanes_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    audited = isolated_index.audit_isolated_index_snapshot(
        fixture.target,
        embedding_adapter=RecordedEmbeddingAdapter(
            model_id=EMBEDDING_MODEL,
            dimension=32,
        ),
    )
    opened = isolated_index.open_manifest_verified_index_snapshot(
        fixture.target,
        expected_embedding_model_id=EMBEDDING_MODEL,
    )
    assert opened == audited

    spy = _SpyEmbeddingAdapter()
    vector_adapter = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=spy,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=True,
    )
    assert spy.batch_calls == 0

    vector_result = vector_adapter(
        _lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    )
    assert len(vector_result.candidates) == 3
    assert {
        candidate.canonical_id for candidate in vector_result.candidates
    } == {"company-robotics", "company-other"}
    assert vector_result.candidates[0].canonical_id == "company-robotics"
    assert all(
        candidate.evidence[0].lane == "vector"
        for candidate in vector_result.candidates
    )
    assert spy.batch_calls > 0

    exact_adapter = isolated_read.create_isolated_exact_lookup_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
    )
    exact_result = exact_adapter(
        _lane_request(lane="exact", query_text="Robotics Co")
    )
    assert len(exact_result.candidates) == 1
    assert exact_result.candidates[0].canonical_id == "company-robotics"


def test_fast_boot_fails_closed_on_tampered_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    marker_path = fixture.target.root / ".canonical-v2-isolated-index-target.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["release_id"] = "candidate-tampered-release"
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(IsolatedIndexTargetSafetyError, match="marker"):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=True,
            vectorized_scoring=True,
            fast_boot=True,
        )


def test_fast_boot_fails_closed_on_tampered_point_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    extra = _vector_point(
        point_id="point:company-extra:default",
        canonical_id="company-extra",
        projection_id="index:company:default",
        view=ProjectionView.default,
        embedded_content=json.dumps(
            {"name": "Extra Co"},
            ensure_ascii=False,
        ),
        source_projection_sha256="6" * 64,
    )
    adapter = RecordedEmbeddingAdapter(model_id=EMBEDDING_MODEL, dimension=32)
    client = isolated_index._open_milvus_client(fixture.target.root / "milvus.db")
    try:
        client.upsert(
            collection_name=COLLECTION_NAME,
            data=[
                {
                    "point_id": extra.point_id,
                    "vector": list(adapter.embed_batch((extra.embedded_content,))[0]),
                    "release_id": extra.release_id,
                    "projection_id": extra.projection_id,
                    "canonical_object_id": extra.canonical_object_id,
                    "embedded_content_sha256": extra.embedded_content_sha256,
                    "point_json": extra.model_dump_json(),
                }
            ],
        )
        client.flush(collection_name=COLLECTION_NAME)
    finally:
        client.close()

    with pytest.raises(
        isolated_read.IsolatedKnowledgeReadIntegrityError,
        match="point inventory|vector points differ",
    ):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=True,
            vectorized_scoring=True,
            fast_boot=True,
        )


def test_fast_boot_fails_closed_on_tampered_lookup_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    lookup_path = fixture.target.root / "lookup.sqlite3"
    with sqlite3.connect(lookup_path) as connection:
        connection.execute(
            "DELETE FROM lookup_document WHERE document_id = ?",
            ("doc:company-other:default",),
        )

    with pytest.raises(
        IndexProjectionIntegrityError,
        match="lookup content differs",
    ):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=True,
            vectorized_scoring=True,
            fast_boot=True,
        )


def test_full_audit_remains_the_default_without_fast_boot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)

    default_spy = _SpyEmbeddingAdapter()
    default_adapter = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=default_spy,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
    )
    assert default_spy.batch_calls > 0
    default_result = default_adapter(
        _lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    )
    assert len(default_result.candidates) == 3

    explicit_spy = _SpyEmbeddingAdapter()
    isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=explicit_spy,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=False,
    )
    assert explicit_spy.batch_calls > 0

    with pytest.raises(ValueError, match="fast_boot requires"):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=False,
            fast_boot=True,
        )
    with pytest.raises(TypeError, match="fast_boot must be a Boolean"):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=True,
            fast_boot="yes",  # type: ignore[arg-type]
        )


def test_release_knowledge_read_composition_supports_fast_boot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    web_policy = WebSearchPolicy(
        mode="universal",
        max_provider_calls=2,
        timeout_ms=1_000,
        max_results=5,
    )
    snapshot_policy = WebSnapshotPolicy(
        policy_id="web-snapshot:fastboot",
        policy_version="web-snapshot-v1",
        max_bytes=4096,
    )

    fast_spy = _SpyEmbeddingAdapter()
    fast_read = isolated_read.create_isolated_release_knowledge_read(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        universal_web_policy=web_policy,
        web_search=lambda _request: RetrievalLaneResult(),
        web_snapshot_policy=snapshot_policy,
        embedding_adapter=fast_spy,
        reuse_audited_vector_snapshot=True,
        vectorized_recall=True,
        fast_boot=True,
        clock=lambda: NOW,
    )
    assert fast_read is not None
    assert fast_spy.batch_calls == 0

    default_spy = _SpyEmbeddingAdapter()
    default_read = isolated_read.create_isolated_release_knowledge_read(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        universal_web_policy=web_policy,
        web_search=lambda _request: RetrievalLaneResult(),
        web_snapshot_policy=snapshot_policy,
        embedding_adapter=default_spy,
        reuse_audited_vector_snapshot=True,
        vectorized_recall=True,
        clock=lambda: NOW,
    )
    assert default_read is not None
    assert default_spy.batch_calls > 0


def _load_runner_module() -> Any:
    runner_path = (
        Path(__file__).resolve().parents[4]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py"
    )
    spec = importlib.util.spec_from_file_location(
        "complete_candidate_runner",
        runner_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _runner_config(runner: Any, tmp_path: Path) -> Any:
    return runner.RunnerConfig(
        database_url="postgresql+psycopg://example.invalid:5432/miroflow_fastboot",
        expected_database="miroflow_fastboot_test",
        database_target_kind="disposable",
        accepted_backup_gate_root=tmp_path / "gate",
        source_manifest_path=tmp_path / "source-manifest.json",
        source_manifest_sha256="0" * 64,
        candidate_staging_root=tmp_path / "staging",
        index_root=tmp_path / "index",
        index_marker_sha256="1" * 64,
        candidate_release_id=RELEASE_ID,
        run_id="run-fastboot-test",
        source_batch_ids=("accepted-s2b-source-batch",),
        parser_versions={"historical": "parser-v1"},
        policy_versions={"eligibility": PATH_POLICY_VERSION},
        model_versions={"embedding": EMBEDDING_MODEL},
        recorded_decision_bundle=tmp_path / "decisions.json",
        recorded_embedding_bundle=tmp_path / "embeddings.json",
        recorded_serving_bundle=tmp_path / "serving.json",
        recorded_serving_bundle_sha256="2" * 64,
        envelope_output=tmp_path / "envelope.json",
        accepted_original_milvus_path=tmp_path / "original-milvus.db",
        accepted_original_milvus_sha256="3" * 64,
        accepted_original_milvus_record_sha256="4" * 64,
        serve=True,
        serve_existing=True,
        host="0.0.0.0",
        port=18188,
    )


def _runner_recorded_inputs() -> Any:
    return SimpleNamespace(
        planning_policy=object(),
        proposal_provider=object(),
        ambiguity_policy=object(),
        universal_web_policy=object(),
        web_search=object(),
        web_snapshot_policy=object(),
        embedding_adapter=object(),
        identity_fuser=None,
        reranker=None,
        sufficiency_decider=None,
        supplemental_search=None,
        web_handle_resolver=None,
        accepted_identity_lookup=None,
        answer_factory=object(),
        answer_session_fork=object(),
        gap_operations=object(),
        supplemental_budget=object(),
        idle_keepwarm_cycle=object(),
    )


@pytest.mark.parametrize("env_value", [None, "1", "0"])
def test_runner_serve_wires_fast_boot_env_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
) -> None:
    runner = _load_runner_module()
    if env_value is None:
        monkeypatch.delenv("CANONICAL_V2_FAST_BOOT", raising=False)
    else:
        monkeypatch.setenv("CANONICAL_V2_FAST_BOOT", env_value)
    create_read_calls: list[dict[str, Any]] = []
    uvicorn_calls: list[dict[str, Any]] = []
    recorded = _runner_recorded_inputs()

    def _create_knowledge_read(**kwargs: Any) -> Any:
        create_read_calls.append(kwargs)
        return object()

    dependencies = runner.RunnerDependencies(
        create_builder=lambda _config: object(),
        read_envelope=lambda _path: object(),
        validate_envelope=lambda value: value,
        load_recorded_serving_inputs=lambda _config: recorded,
        create_published_release=lambda **kwargs: SimpleNamespace(**kwargs),
        create_query_planner=lambda **kwargs: object(),
        create_knowledge_read=_create_knowledge_read,
        compose_consumer_runtime=lambda **kwargs: object(),
        create_candidate_app=lambda **kwargs: object(),
        uvicorn_run=lambda _app, **kwargs: uvicorn_calls.append(kwargs),
    )
    handoff = SimpleNamespace(
        release_verification=SimpleNamespace(
            evidence_ids=("release-verification:fastboot",)
        ),
        release_bundle=object(),
        index_projection_request=object(),
        institution_catalog=object(),
    )

    runner._serve(
        config=_runner_config(runner, tmp_path),
        handoff=handoff,
        dependencies=dependencies,
    )

    assert len(create_read_calls) == 1
    assert len(uvicorn_calls) == 1
    call = create_read_calls[0]
    assert call["reuse_audited_vector_snapshot"] is True
    assert call["vectorized_recall"] is True
    assert call["fast_boot"] is (env_value == "1")


def test_persisted_vector_matrix_boots_without_reembedding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The persisted npz matrix must load at adapter creation: the first
    vector request then scores from the file with zero re-embeds."""
    fixture = _build_fixture(tmp_path, monkeypatch)
    snapshot = isolated_index.open_manifest_verified_index_snapshot(
        fixture.target,
        expected_embedding_model_id=EMBEDDING_MODEL,
    )
    adapter = RecordedEmbeddingAdapter(model_id=EMBEDDING_MODEL, dimension=32)
    vectors = tuple(
        adapter.embed_batch((point.embedded_content,))[0]
        for point in snapshot.points
    )
    isolated_index.write_persisted_vector_matrix(
        fixture.target.root,
        points=snapshot.points,
        vectors=vectors,
        embedding_model_id=EMBEDDING_MODEL,
    )

    spy = _SpyEmbeddingAdapter()
    vector_adapter = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=spy,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=True,
    )
    assert spy.batch_calls == 0  # matrix loaded from file, not embedded

    result = vector_adapter(
        _lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    )
    assert len(result.candidates) == 3
    assert spy.batch_calls == 1  # only the query vector is embedded


def test_persisted_vector_matrix_fails_closed_on_model_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    snapshot = isolated_index.open_manifest_verified_index_snapshot(
        fixture.target,
        expected_embedding_model_id=EMBEDDING_MODEL,
    )
    adapter = RecordedEmbeddingAdapter(model_id=EMBEDDING_MODEL, dimension=32)
    vectors = tuple(
        adapter.embed_batch((point.embedded_content,))[0]
        for point in snapshot.points
    )
    isolated_index.write_persisted_vector_matrix(
        fixture.target.root,
        points=snapshot.points,
        vectors=vectors,
        embedding_model_id="different-model",
    )

    with pytest.raises(isolated_read.IsolatedKnowledgeReadIntegrityError):
        isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=_SpyEmbeddingAdapter(),
            reuse_audited_snapshot=True,
            vectorized_scoring=True,
            fast_boot=True,
        )


def test_persisted_matrix_evidence_check_uses_each_point_own_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the npz branch of the release-bound vector evidence check
    must pair each point with its OWN persisted vector.  The first attempt
    passed a plain parenthesized tuple to ``zip``, which iterated the tuple
    element-wise and turned ``point_vector`` into a numpy scalar, crashing
    with ``TypeError: object of type 'numpy.float64' has no len()``."""
    fixture = _build_fixture(tmp_path, monkeypatch)
    snapshot = isolated_index.open_manifest_verified_index_snapshot(
        fixture.target,
        expected_embedding_model_id=EMBEDDING_MODEL,
    )
    recorded = RecordedEmbeddingAdapter(model_id=EMBEDDING_MODEL, dimension=32)
    vectors = tuple(
        recorded.embed_batch((point.embedded_content,))[0]
        for point in snapshot.points
    )
    isolated_index.write_persisted_vector_matrix(
        fixture.target.root,
        points=snapshot.points,
        vectors=vectors,
        embedding_model_id=EMBEDDING_MODEL,
    )

    spy = _SpyEmbeddingAdapter()
    vector_adapter = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=spy,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=True,
    )
    recall = vector_adapter(
        _lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    )
    assert len(recall.candidates) == 3

    items = tuple(candidate.evidence[0] for candidate in recall.candidates)
    fused_candidates = tuple(
        FusedCandidate(
            result_id=f"fused:test:{candidate.canonical_id}",
            canonical_id=candidate.canonical_id,
            display_name=candidate.display_name,
            domain=candidate.domain,
            raw_candidate_ids=(candidate.raw_candidate_id,),
            evidence_ids=(candidate.evidence[0].evidence_id,),
            evidence=(candidate.evidence[0],),
            quality_flags=(),
            raw_score=candidate.raw_score,
            identity_kind=candidate.identity_kind,
            resolution_state=candidate.resolution_state,
            origin_lane=candidate.lane,
            origin_attempt=candidate.attempt,
            adapter_versions=(candidate.adapter_version,),
            provider_versions=(
                (candidate.provider_version,)
                if candidate.provider_version is not None
                else ()
            ),
        )
        for candidate in recall.candidates
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query="Robotics Co",
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        fused_candidates=fused_candidates,
    )
    plan = RetrievalPlan(
        plan_version="fastboot-test-v1",
        original_query="Robotics Co",
        behavior_class="A",
        release_id=RELEASE_ID,
        domains=("company",),
        protected_slots=(),
        lanes=("vector",),
        max_candidates=8,
        web_required=False,
        lane_queries=(
            LaneQuery(
                lane="vector",
                release_id=RELEASE_ID,
                catalog_sha256=CATALOG_CONTENT_SHA256,
                pure_topic_text="Robotics Co",
                query_text="Robotics Co [lane=vector]",
            ),
        ),
    )
    isolated_read._validate_release_bound_vector_evidence(
        plan=plan,
        evidence_set=evidence_set,
        bundle=fixture.bundle,
        publication=fixture.published,
        embedding_adapter=spy,
    )
