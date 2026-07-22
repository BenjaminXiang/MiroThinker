"""Build isolated Canonical V2 candidates from already-materialized release sections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, MutableMapping
from datetime import datetime
import hashlib
import json
from typing import Any, NoReturn, cast

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import (
    BuildManifest,
    CandidateRelease,
    ContractModel,
    IndexProjectionManifest,
    ManifestSection,
    NonEmptyStr,
    ProjectionManifest,
    ReleaseState,
)


class BuildCandidateRequest(ContractModel):
    """Named, versioned inputs for one isolated candidate release."""

    run_id: NonEmptyStr
    candidate_release_id: NonEmptyStr
    source_batch_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    parser_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    policy_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    model_versions: dict[NonEmptyStr, NonEmptyStr]

    @field_validator("source_batch_ids")
    @classmethod
    def canonicalize_source_batch_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(values))

    @field_validator("parser_versions", "policy_versions", "model_versions")
    @classmethod
    def freeze_version_maps(cls, values: dict[str, str]) -> dict[str, str]:
        return _immutable_sorted(values)

    @model_validator(mode="after")
    def validate_unique_source_batches(self) -> BuildCandidateRequest:
        if len(set(self.source_batch_ids)) != len(self.source_batch_ids):
            raise ValueError("source_batch_ids must contain unique values")
        return self


class KnowledgeBuild(ABC):
    """Construct one candidate without exposing internal build stages."""

    @abstractmethod
    def build(self, request: BuildCandidateRequest) -> CandidateRelease:
        """Build and retain one isolated candidate release."""


class _CandidateMaterialization(ContractModel):
    decision_set: ManifestSection
    object_sets: tuple[ManifestSection, ...] = Field(min_length=1)
    relationship_set: ManifestSection
    eligibility_sets: tuple[ManifestSection, ...] = Field(min_length=1)
    published_projections: tuple[ProjectionManifest, ...] = Field(min_length=1)
    expected_index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_section_roles(self) -> _CandidateMaterialization:
        if self.decision_set.section_id != "decisions":
            raise ValueError("decision_set must use section_id 'decisions'")
        if self.relationship_set.section_id != "relationships":
            raise ValueError("relationship_set must use section_id 'relationships'")

        object_ids = tuple(section.section_id for section in self.object_sets)
        if any(
            not section_id.startswith("objects:") or len(section_id) == len("objects:")
            for section_id in object_ids
        ):
            raise ValueError(
                "object_sets must use non-empty objects:<type> section IDs"
            )
        if len(set(object_ids)) != len(object_ids):
            raise ValueError("object_sets must use unique section IDs")

        eligibility_ids = tuple(section.section_id for section in self.eligibility_sets)
        if any(
            not section_id.startswith("eligibility:")
            or len(section_id) == len("eligibility:")
            for section_id in eligibility_ids
        ):
            raise ValueError(
                "eligibility_sets must use non-empty eligibility:<path> section IDs"
            )
        if len(set(eligibility_ids)) != len(eligibility_ids):
            raise ValueError("eligibility_sets must use unique section IDs")
        return self


class _ImmutableDict[K, V](dict[K, V]):
    """A JSON-serializable dict copy that rejects in-place mutation."""

    @staticmethod
    def _reject_mutation() -> NoReturn:
        raise TypeError("Canonical V2 build mappings are immutable")

    def __setitem__(self, key: K, value: V) -> None:
        self._reject_mutation()

    def __delitem__(self, key: K) -> None:
        self._reject_mutation()

    def __ior__(self, value: Any) -> NoReturn:
        self._reject_mutation()

    def __copy__(self) -> _ImmutableDict[K, V]:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _ImmutableDict[K, V]:
        return self

    def clear(self) -> None:
        self._reject_mutation()

    def pop(self, key: K, default: Any = None) -> NoReturn:
        self._reject_mutation()

    def popitem(self) -> NoReturn:
        self._reject_mutation()

    def setdefault(self, key: K, default: V | None = None) -> NoReturn:
        self._reject_mutation()

    def update(self, *args: Any, **kwargs: V) -> None:
        self._reject_mutation()


def _immutable_sorted[K, V](values: Mapping[K, V]) -> dict[K, V]:
    return _ImmutableDict(sorted(values.items(), key=lambda item: str(item[0])))


def _canonical_sha256(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_batches_sha256(source_batch_ids: tuple[str, ...]) -> str:
    return _canonical_sha256({"source_batch_ids": list(source_batch_ids)})


def _freeze_manifest(manifest: BuildManifest) -> BuildManifest:
    return manifest.model_copy(
        update={
            "parser_versions": _immutable_sorted(manifest.parser_versions),
            "policy_versions": _immutable_sorted(manifest.policy_versions),
            "model_versions": _immutable_sorted(manifest.model_versions),
        }
    )


def _freeze_candidate(candidate: CandidateRelease) -> CandidateRelease:
    return candidate.model_copy(
        update={
            "parser_versions": _immutable_sorted(candidate.parser_versions),
            "policy_versions": _immutable_sorted(candidate.policy_versions),
            "model_versions": _immutable_sorted(candidate.model_versions),
            "object_counts": _immutable_sorted(candidate.object_counts),
        }
    )


class _EphemeralKnowledgeBuild(KnowledgeBuild):
    def __init__(
        self,
        *,
        materialize: Callable[[BuildCandidateRequest], object],
        candidate_store: MutableMapping[str, CandidateRelease],
        manifest_store: MutableMapping[str, BuildManifest],
        failure_store: MutableMapping[str, Any],
        active_release_state: Mapping[str, str],
        clock: Callable[[], datetime],
    ) -> None:
        self._materialize = materialize
        self._candidate_store = candidate_store
        self._manifest_store = manifest_store
        self._failure_store = failure_store
        self._active_release_state = active_release_state
        self._clock = clock

    def _active_snapshot(self) -> dict[str, str]:
        return dict(self._active_release_state)

    def _assert_active_unchanged(self, snapshot: Mapping[str, str]) -> None:
        if self._active_snapshot() != dict(snapshot):
            raise RuntimeError(
                "candidate construction cannot change the active release"
            )

    def _record_materialize_failure(
        self,
        request: BuildCandidateRequest,
        error: Exception,
    ) -> None:
        self._failure_store.setdefault(
            request.candidate_release_id,
            {
                "candidate_release_id": request.candidate_release_id,
                "run_id": request.run_id,
                "stage": "materialize",
                "retryable": True,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )

    def _construct_manifest(
        self,
        request: BuildCandidateRequest,
        materialization: _CandidateMaterialization,
    ) -> BuildManifest:
        source_batch_ids = tuple(request.source_batch_ids)
        content: dict[str, Any] = {
            "manifest_version": "canonical-v2-build-manifest-v2",
            "release_id": request.candidate_release_id,
            "build_run_id": request.run_id,
            "source_batch_ids": source_batch_ids,
            "source_batches_sha256": _source_batches_sha256(source_batch_ids),
            "parser_versions": dict(sorted(request.parser_versions.items())),
            "policy_versions": dict(sorted(request.policy_versions.items())),
            "model_versions": dict(sorted(request.model_versions.items())),
            "decision_set": materialization.decision_set,
            "object_sets": tuple(
                sorted(materialization.object_sets, key=lambda item: item.section_id)
            ),
            "relationship_set": materialization.relationship_set,
            "eligibility_sets": tuple(
                sorted(
                    materialization.eligibility_sets,
                    key=lambda item: item.section_id,
                )
            ),
            "published_projections": tuple(
                sorted(
                    materialization.published_projections,
                    key=lambda item: item.projection_id,
                )
            ),
            "expected_index_projections": tuple(
                sorted(
                    materialization.expected_index_projections,
                    key=lambda item: item.projection_id,
                )
            ),
            "created_at": self._clock(),
        }
        provisional = BuildManifest(**content, manifest_sha256="0" * 64)
        hash_payload = cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"manifest_sha256"}),
        )
        return _freeze_manifest(
            BuildManifest(
                **content,
                manifest_sha256=_canonical_sha256(hash_payload),
            )
        )

    @staticmethod
    def _construct_candidate(
        request: BuildCandidateRequest,
        materialization: _CandidateMaterialization,
        manifest: BuildManifest,
    ) -> CandidateRelease:
        object_counts = {
            section.section_id.removeprefix("objects:"): section.record_count
            for section in materialization.object_sets
        }
        return _freeze_candidate(
            CandidateRelease(
                release_id=request.candidate_release_id,
                run_id=request.run_id,
                state=ReleaseState.candidate,
                source_batch_ids=request.source_batch_ids,
                parser_versions=dict(sorted(request.parser_versions.items())),
                policy_versions=dict(sorted(request.policy_versions.items())),
                model_versions=dict(sorted(request.model_versions.items())),
                manifest_sha256=manifest.manifest_sha256,
                object_counts=object_counts,
                relationship_count=materialization.relationship_set.record_count,
                active_release_changed=False,
            )
        )

    def _retain_candidate(
        self,
        candidate: CandidateRelease,
        manifest: BuildManifest,
    ) -> CandidateRelease:
        release_id = candidate.release_id
        existing_candidate = self._candidate_store.get(release_id)
        existing_manifest = self._manifest_store.get(release_id)
        if existing_candidate is not None or existing_manifest is not None:
            if (
                existing_candidate is not None
                and existing_manifest is not None
                and existing_candidate == candidate
                and existing_manifest == manifest
            ):
                return existing_candidate
            raise ValueError(
                f"immutable candidate release collision for release_id {release_id!r}"
            )

        self._manifest_store[release_id] = manifest
        try:
            self._candidate_store[release_id] = candidate
        except Exception:
            del self._manifest_store[release_id]
            raise
        return candidate

    def build(self, request: BuildCandidateRequest) -> CandidateRelease:
        active_snapshot = self._active_snapshot()
        try:
            raw_materialization = self._materialize(request)
        except Exception as error:
            self._record_materialize_failure(request, error)
            self._assert_active_unchanged(active_snapshot)
            raise

        self._assert_active_unchanged(active_snapshot)
        materialization = _CandidateMaterialization.model_validate(raw_materialization)
        manifest = self._construct_manifest(request, materialization)
        candidate = self._construct_candidate(request, materialization, manifest)
        self._assert_active_unchanged(active_snapshot)
        retained = self._retain_candidate(candidate, manifest)
        self._assert_active_unchanged(active_snapshot)
        return retained


def create_ephemeral_knowledge_build(
    *,
    materialize: Callable[[BuildCandidateRequest], object],
    candidate_store: MutableMapping[str, CandidateRelease],
    manifest_store: MutableMapping[str, BuildManifest],
    failure_store: MutableMapping[str, Any],
    active_release_state: Mapping[str, str],
    clock: Callable[[], datetime],
) -> KnowledgeBuild:
    """Compose the pure Task 7.2 implementation with in-process stores."""

    return _EphemeralKnowledgeBuild(
        materialize=materialize,
        candidate_store=candidate_store,
        manifest_store=manifest_store,
        failure_store=failure_store,
        active_release_state=active_release_state,
        clock=clock,
    )


__all__ = [
    "BuildCandidateRequest",
    "BuildManifest",
    "CandidateRelease",
    "KnowledgeBuild",
    "create_ephemeral_knowledge_build",
]
