"""Verify and rehearse one atomic Canonical V2 release snapshot transition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, MutableMapping, MutableSequence
from datetime import datetime
from enum import Enum
import hashlib
import json

from pydantic import model_validator

from .contracts import (
    BuildManifest,
    ContractModel,
    IndexProjectionManifest,
    NonEmptyStr,
    PublishedRelease,
    ReleaseState,
    ReleaseVerification,
    Sha256,
)
from .index_projection import IndexProjectionPoint, index_point_content_sha256


_ACTIVE_RELEASE_KEYS = (
    "canonical_release_id",
    "published_projection_release_id",
    "index_release_id",
)


class PointDiscrepancyKind(str, Enum):
    """One mutually exclusive point-level reconciliation outcome."""

    missing = "missing"
    extra = "extra"
    stale = "stale"
    cross_release = "cross_release"


class IndexPointDiscrepancy(ContractModel):
    """Repairable evidence for one point that prevents exact release parity."""

    discrepancy_id: NonEmptyStr
    kind: PointDiscrepancyKind
    point_id: NonEmptyStr
    projection_id: NonEmptyStr
    canonical_object_id: NonEmptyStr
    expected_release_id: NonEmptyStr | None
    actual_release_id: NonEmptyStr | None
    expected_projection_version: NonEmptyStr | None
    actual_projection_version: NonEmptyStr | None
    expected_embedded_content_sha256: Sha256 | None
    actual_embedded_content_sha256: Sha256 | None
    expected_point: IndexProjectionPoint | None
    actual_point: IndexProjectionPoint | None

    @model_validator(mode="after")
    def validate_discrepancy_sides(self) -> IndexPointDiscrepancy:
        expected_present = self.expected_release_id is not None
        actual_present = self.actual_release_id is not None
        if self.kind is PointDiscrepancyKind.missing and not (
            expected_present and not actual_present
        ):
            raise ValueError("missing discrepancy requires only the expected point")
        if self.kind is PointDiscrepancyKind.extra and not (
            actual_present and not expected_present
        ):
            raise ValueError("extra discrepancy requires only the actual point")
        if self.kind in {
            PointDiscrepancyKind.stale,
            PointDiscrepancyKind.cross_release,
        } and not (expected_present and actual_present):
            raise ValueError("stale/cross-release discrepancy requires both points")
        return self


class ReleasePublication(ABC):
    """The only Canonical V2 module allowed to change a release snapshot."""

    @abstractmethod
    def verify(self, candidate_release_id: str) -> ReleaseVerification:
        """Persist deterministic manifest and point reconciliation evidence."""

    @abstractmethod
    def promote(self, accepted_release_id: str) -> PublishedRelease:
        """Explicitly switch one accepted in-process release snapshot."""

    @abstractmethod
    def rollback(self, published_release_id: str) -> PublishedRelease:
        """Restore the prior snapshot recorded by the matching promotion."""


class _EphemeralReleasePublication(ReleasePublication):
    def __init__(
        self,
        *,
        candidate_manifests: Mapping[str, BuildManifest],
        actual_index_projections: Mapping[str, tuple[IndexProjectionManifest, ...]],
        expected_index_points: Mapping[str, tuple[IndexProjectionPoint, ...]],
        actual_index_points: Mapping[str, tuple[IndexProjectionPoint, ...]],
        active_release_state: MutableMapping[str, str],
        verification_store: MutableMapping[str, ReleaseVerification],
        discrepancy_store: MutableMapping[str, tuple[IndexPointDiscrepancy, ...]],
        publication_history: MutableSequence[PublishedRelease],
        clock: Callable[[], datetime],
    ) -> None:
        self._candidate_manifests = dict(candidate_manifests)
        self._actual_index_projections = {
            release_id: tuple(manifests)
            for release_id, manifests in actual_index_projections.items()
        }
        self._expected_index_points = {
            release_id: tuple(points)
            for release_id, points in expected_index_points.items()
        }
        self._actual_index_points = {
            release_id: tuple(points)
            for release_id, points in actual_index_points.items()
        }
        self._active_release_state = active_release_state
        self._verification_store = verification_store
        self._discrepancy_store = discrepancy_store
        self._publication_history = publication_history
        self._clock = clock

        for release_id, manifest in self._candidate_manifests.items():
            if release_id != manifest.release_id:
                raise ValueError("candidate manifest key must match its release_id")
        _active_release_id(self._active_release_state)

    def verify(self, candidate_release_id: str) -> ReleaseVerification:
        manifest = self._candidate_manifests.get(candidate_release_id)
        if manifest is None:
            raise ValueError("unknown candidate release")
        if candidate_release_id not in self._expected_index_points:
            raise ValueError("expected point inventory is required")
        if candidate_release_id not in self._actual_index_points:
            raise ValueError("actual point inventory is required")

        expected_manifests = manifest.expected_index_projections
        actual_manifests = self._actual_index_projections.get(candidate_release_id, ())
        expected_points = self._expected_index_points[candidate_release_id]
        actual_points = self._actual_index_points[candidate_release_id]

        expected_by_projection = _manifests_by_projection(
            expected_manifests,
            label="expected index manifests",
        )
        actual_by_projection = _manifests_by_projection(
            actual_manifests,
            label="actual index manifests",
        )
        manifest_parity, manifest_evidence = _reconcile_manifests(
            expected_by_projection,
            actual_by_projection,
        )
        expected_inventory_evidence = _inventory_binding_evidence(
            side="expected",
            manifests=expected_by_projection,
            points=expected_points,
        )
        actual_inventory_evidence = _inventory_binding_evidence(
            side="actual",
            manifests=actual_by_projection,
            points=actual_points,
        )
        discrepancies = _reconcile_points(expected_points, actual_points)
        counts = {
            kind: sum(detail.kind is kind for detail in discrepancies)
            for kind in PointDiscrepancyKind
        }
        point_parity = not discrepancies
        inventory_parity = not (
            expected_inventory_evidence or actual_inventory_evidence
        )
        accepted = manifest_parity and inventory_parity and point_parity

        evidence_ids = set(manifest_evidence)
        evidence_ids.update(expected_inventory_evidence)
        evidence_ids.update(actual_inventory_evidence)
        evidence_ids.update(detail.discrepancy_id for detail in discrepancies)
        if accepted:
            evidence_ids.add(
                "release-parity:sha256:"
                + _canonical_sha256(
                    {
                        "candidate_release_id": candidate_release_id,
                        "manifest_sha256": manifest.manifest_sha256,
                        "projection_ids": sorted(expected_by_projection),
                        "point_ids": sorted(
                            point.point_id for point in expected_points
                        ),
                    }
                )
            )

        verification = ReleaseVerification(
            candidate_release_id=candidate_release_id,
            manifest_sha256=manifest.manifest_sha256,
            accepted=accepted,
            canonical_index_parity=accepted,
            missing_points=counts[PointDiscrepancyKind.missing],
            extra_points=counts[PointDiscrepancyKind.extra],
            stale_points=counts[PointDiscrepancyKind.stale],
            cross_release_points=counts[PointDiscrepancyKind.cross_release],
            evidence_ids=tuple(sorted(evidence_ids)),
            verified_at=self._clock(),
        )
        self._discrepancy_store[candidate_release_id] = discrepancies
        self._verification_store[candidate_release_id] = verification
        return verification

    def promote(self, accepted_release_id: str) -> PublishedRelease:
        manifest = self._candidate_manifests.get(accepted_release_id)
        verification = self._verification_store.get(accepted_release_id)
        if (
            manifest is None
            or verification is None
            or not verification.accepted
            or verification.candidate_release_id != accepted_release_id
            or verification.manifest_sha256 != manifest.manifest_sha256
        ):
            raise ValueError("release is not accepted")

        previous_release_id = _active_release_id(self._active_release_state)
        if previous_release_id == accepted_release_id:
            raise ValueError("accepted release is already active")
        published = PublishedRelease(
            release_id=accepted_release_id,
            previous_release_id=previous_release_id,
            canonical_release_id=accepted_release_id,
            published_projection_release_id=accepted_release_id,
            index_release_id=accepted_release_id,
            state=ReleaseState.active,
            changed_at=self._clock(),
            verification_evidence_ids=verification.evidence_ids,
        )
        self._active_release_state.update(
            {key: accepted_release_id for key in _ACTIVE_RELEASE_KEYS}
        )
        self._publication_history.append(published)
        return published

    def rollback(self, published_release_id: str) -> PublishedRelease:
        if _active_release_id(self._active_release_state) != published_release_id:
            raise ValueError("published release is not the active release")
        promotion = next(
            (
                event
                for event in reversed(tuple(self._publication_history))
                if event.release_id == published_release_id
                and event.state is ReleaseState.active
            ),
            None,
        )
        if promotion is None or promotion.previous_release_id is None:
            raise ValueError("published release has no rollback checkpoint")

        restored_release_id = promotion.previous_release_id
        rolled_back = PublishedRelease(
            release_id=restored_release_id,
            previous_release_id=published_release_id,
            canonical_release_id=restored_release_id,
            published_projection_release_id=restored_release_id,
            index_release_id=restored_release_id,
            state=ReleaseState.rolled_back,
            changed_at=self._clock(),
            verification_evidence_ids=promotion.verification_evidence_ids,
        )
        self._active_release_state.update(
            {key: restored_release_id for key in _ACTIVE_RELEASE_KEYS}
        )
        self._publication_history.append(rolled_back)
        return rolled_back


def create_ephemeral_release_publication(
    *,
    candidate_manifests: Mapping[str, BuildManifest],
    actual_index_projections: Mapping[str, tuple[IndexProjectionManifest, ...]],
    expected_index_points: Mapping[str, tuple[IndexProjectionPoint, ...]],
    actual_index_points: Mapping[str, tuple[IndexProjectionPoint, ...]],
    active_release_state: MutableMapping[str, str],
    verification_store: MutableMapping[str, ReleaseVerification],
    discrepancy_store: MutableMapping[str, tuple[IndexPointDiscrepancy, ...]],
    publication_history: MutableSequence[PublishedRelease],
    clock: Callable[[], datetime],
) -> ReleasePublication:
    """Compose the explicit in-process Task 7.6 reconciliation boundary."""

    return _EphemeralReleasePublication(
        candidate_manifests=candidate_manifests,
        actual_index_projections=actual_index_projections,
        expected_index_points=expected_index_points,
        actual_index_points=actual_index_points,
        active_release_state=active_release_state,
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=publication_history,
        clock=clock,
    )


def _active_release_id(active_release_state: Mapping[str, str]) -> str:
    if set(active_release_state) != set(_ACTIVE_RELEASE_KEYS):
        raise ValueError("active release state must contain exactly three release keys")
    release_ids = {active_release_state[key] for key in _ACTIVE_RELEASE_KEYS}
    if len(release_ids) != 1 or "" in release_ids:
        raise ValueError("active canonical/published/index releases must match")
    return next(iter(release_ids))


def _manifests_by_projection(
    manifests: tuple[IndexProjectionManifest, ...],
    *,
    label: str,
) -> dict[str, IndexProjectionManifest]:
    by_projection = {manifest.projection_id: manifest for manifest in manifests}
    if len(by_projection) != len(manifests):
        raise ValueError(f"{label} must use unique projection IDs")
    return by_projection


def _points_by_id(
    points: tuple[IndexProjectionPoint, ...],
    *,
    label: str,
) -> dict[str, IndexProjectionPoint]:
    by_id = {point.point_id: point for point in points}
    if len(by_id) != len(points):
        raise ValueError(f"{label} must use unique point IDs")
    return by_id


def _inventory_binding_evidence(
    *,
    side: str,
    manifests: Mapping[str, IndexProjectionManifest],
    points: tuple[IndexProjectionPoint, ...],
) -> tuple[str, ...]:
    owned_points: dict[str, list[IndexProjectionPoint]] = {
        projection_id: [] for projection_id in manifests
    }
    for point in points:
        owned_points.setdefault(point.projection_id, []).append(point)

    evidence: list[str] = []
    for projection_id in sorted(owned_points):
        manifest = manifests.get(projection_id)
        owned = tuple(owned_points[projection_id])
        computed_entity_ids_sha256 = _entity_ids_sha256(
            point.canonical_object_id for point in owned
        )
        computed_content_sha256 = index_point_content_sha256(owned)
        if manifest is None:
            payload = {
                "side": side,
                "projection_id": projection_id,
                "manifest": None,
                "computed_point_count": len(owned),
                "computed_entity_ids_sha256": computed_entity_ids_sha256,
                "computed_content_sha256": computed_content_sha256,
                "point_ids": sorted(point.point_id for point in owned),
            }
            evidence.append(
                f"index-inventory:{side}:{projection_id}:no-manifest:"
                f"count-none-{len(owned)}:entities-none-{computed_entity_ids_sha256}:"
                f"content-none-{computed_content_sha256}:sha256:{_canonical_sha256(payload)}"
            )
            continue

        metadata_mismatch_point_ids = tuple(
            sorted(
                point.point_id
                for point in owned
                if not _point_matches_manifest(point, manifest)
            )
        )
        if (
            manifest.point_count == len(owned)
            and manifest.entity_ids_sha256 == computed_entity_ids_sha256
            and manifest.content_sha256 == computed_content_sha256
            and not metadata_mismatch_point_ids
        ):
            continue
        payload = {
            "side": side,
            "projection_id": projection_id,
            "projection_version": manifest.projection_version,
            "declared_point_count": manifest.point_count,
            "computed_point_count": len(owned),
            "declared_entity_ids_sha256": manifest.entity_ids_sha256,
            "computed_entity_ids_sha256": computed_entity_ids_sha256,
            "declared_content_sha256": manifest.content_sha256,
            "computed_content_sha256": computed_content_sha256,
            "metadata_mismatch_point_ids": metadata_mismatch_point_ids,
        }
        evidence.append(
            f"index-inventory:{side}:{projection_id}:{manifest.projection_version}:"
            f"count-{manifest.point_count}-{len(owned)}:"
            f"entities-{manifest.entity_ids_sha256}-{computed_entity_ids_sha256}:"
            f"content-{manifest.content_sha256}-{computed_content_sha256}:"
            f"metadata-{len(metadata_mismatch_point_ids)}:"
            f"sha256:{_canonical_sha256(payload)}"
        )
    return tuple(evidence)


def _point_matches_manifest(
    point: IndexProjectionPoint,
    manifest: IndexProjectionManifest,
) -> bool:
    return (
        point.release_id == manifest.release_id
        and point.projection_id == manifest.projection_id
        and point.projection_scope is manifest.projection_scope
        and point.domain == manifest.domain
        and point.reference_type == manifest.reference_type
        and point.path == manifest.path
        and point.projection_version == manifest.projection_version
        and point.schema_version == manifest.schema_version
        and point.embedding_model == manifest.embedding_model
        and point.eligibility_policy_version == manifest.eligibility_policy_version
    )


def _reconcile_manifests(
    expected: Mapping[str, IndexProjectionManifest],
    actual: Mapping[str, IndexProjectionManifest],
) -> tuple[bool, tuple[str, ...]]:
    evidence: list[str] = []
    for projection_id in sorted(set(expected) | set(actual)):
        expected_manifest = expected.get(projection_id)
        actual_manifest = actual.get(projection_id)
        if expected_manifest == actual_manifest:
            continue
        if expected_manifest is None:
            kind = "extra"
            version = (
                actual_manifest.projection_version if actual_manifest else "unknown"
            )
        elif actual_manifest is None:
            kind = "missing"
            version = expected_manifest.projection_version
        else:
            kind = "stale"
            version = expected_manifest.projection_version
        evidence.append(
            f"index-manifest:{kind}:{projection_id}:{version}:sha256:"
            + _canonical_sha256(
                {
                    "expected": (
                        expected_manifest.model_dump(mode="json")
                        if expected_manifest is not None
                        else None
                    ),
                    "actual": (
                        actual_manifest.model_dump(mode="json")
                        if actual_manifest is not None
                        else None
                    ),
                }
            )
        )
    return not evidence, tuple(evidence)


def _reconcile_points(
    expected: tuple[IndexProjectionPoint, ...],
    actual: tuple[IndexProjectionPoint, ...],
) -> tuple[IndexPointDiscrepancy, ...]:
    expected_by_id = _points_by_id(expected, label="expected point inventory")
    actual_by_id = _points_by_id(actual, label="actual point inventory")
    discrepancies: list[IndexPointDiscrepancy] = []
    for point_id in sorted(set(expected_by_id) | set(actual_by_id)):
        expected_point = expected_by_id.get(point_id)
        actual_point = actual_by_id.get(point_id)
        if expected_point is None:
            kind = PointDiscrepancyKind.extra
        elif actual_point is None:
            kind = PointDiscrepancyKind.missing
        elif expected_point.release_id != actual_point.release_id:
            kind = PointDiscrepancyKind.cross_release
        elif expected_point != actual_point:
            kind = PointDiscrepancyKind.stale
        else:
            continue
        discrepancies.append(_discrepancy(kind, expected_point, actual_point))
    return tuple(discrepancies)


def _discrepancy(
    kind: PointDiscrepancyKind,
    expected: IndexProjectionPoint | None,
    actual: IndexProjectionPoint | None,
) -> IndexPointDiscrepancy:
    point = expected if expected is not None else actual
    if point is None:  # pragma: no cover - protected by reconciliation construction
        raise AssertionError("point discrepancy requires one point")
    details = {
        "kind": kind.value,
        "point_id": point.point_id,
        "projection_id": point.projection_id,
        "canonical_object_id": point.canonical_object_id,
        "expected_release_id": expected.release_id if expected else None,
        "actual_release_id": actual.release_id if actual else None,
        "expected_projection_version": (
            expected.projection_version if expected else None
        ),
        "actual_projection_version": actual.projection_version if actual else None,
        "expected_embedded_content_sha256": (
            expected.embedded_content_sha256 if expected else None
        ),
        "actual_embedded_content_sha256": (
            actual.embedded_content_sha256 if actual else None
        ),
    }
    hash_payload = {
        **details,
        "expected_point": (
            expected.model_dump(mode="json") if expected is not None else None
        ),
        "actual_point": actual.model_dump(mode="json") if actual is not None else None,
    }
    return IndexPointDiscrepancy(
        discrepancy_id=(
            f"index-point-discrepancy:{kind.value}:{point.projection_id}:"
            f"{point.projection_version}:sha256:{_canonical_sha256(hash_payload)}"
        ),
        expected_point=expected,
        actual_point=actual,
        **details,
    )


def _entity_ids_sha256(ids: Iterable[str]) -> str:
    return _sha256_text("|".join(sorted(ids)))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
