"""Guarded Task 7.7 adapter for one isolated release publication rehearsal."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, MutableSequence
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import psycopg
from pydantic import JsonValue, ValidationError, model_validator
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import (
    DatabaseTargetSafetyError,
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

from .contracts import (
    BuildManifest,
    ContractModel,
    PublishedRelease,
    ReleaseVerification,
)
from .candidate_projection import (
    CandidateProjectionRequest,
    CandidateProjectionIntegrityError,
    compose_candidate_projections,
)
from .index_projection import (
    IndexProjectionIntegrityError,
    IndexProjectionResult,
)
from .index_projection_isolated import (
    EmbeddingAdapter,
    IsolatedIndexSnapshot,
    IsolatedIndexTarget,
    _validate_target_marker,
    audit_isolated_index_snapshot,
)
from .rebuild_write_gate import require_accepted_backup_gate
from .relationship_projection import (
    INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION,
    RelationshipProjectionIntegrityError,
    RelationshipProjectionRequest,
    RelationshipProjectionResult,
    create_ephemeral_relationship_projection,
)
from .release_publication import (
    IndexPointDiscrepancy,
    ReleasePublication,
    create_ephemeral_release_publication,
)


_ACTIVE_RELEASE_KEYS = (
    "canonical_release_id",
    "published_projection_release_id",
    "index_release_id",
)


class IsolatedReleaseTargetSafetyError(RuntimeError):
    """The rehearsal target is not explicitly disposable and identity checked."""


def _canonical_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class IsolatedReleaseBundle(ContractModel):
    """One immutable logical release bound to its marked physical index target."""

    manifest: BuildManifest
    index_result: IndexProjectionResult
    index_target: IsolatedIndexTarget
    relationship_projection_request: RelationshipProjectionRequest | None = None
    relationship_projection_result: RelationshipProjectionResult | None = None

    @property
    def release_id(self) -> str:
        return self.manifest.release_id

    @model_validator(mode="after")
    def validate_release_continuity(self) -> IsolatedReleaseBundle:
        release_ids = {
            self.manifest.release_id,
            self.index_result.release_id,
            self.index_target.release_id,
        }
        if len(release_ids) != 1:
            raise ValueError("isolated bundle release identities must match")
        if (
            not _same_index_manifests(
                self.manifest.expected_index_projections,
                self.index_result.expected_index_projections,
            )
            or self.index_result.expected_index_projections
            != self.index_result.actual_index_projections
        ):
            raise ValueError(
                "isolated bundle manifest and index projections must match"
            )
        relationship_request = self.relationship_projection_request
        relationship_result = self.relationship_projection_result
        if (relationship_request is None) != (relationship_result is None):
            raise ValueError(
                "relationship projection request/result must be supplied together"
            )
        relationship_section = self.manifest.relationship_set
        if relationship_section.section_id != "relationships":
            raise ValueError(
                "relationship manifest must use section_id 'relationships'"
            )
        if relationship_request is None or relationship_result is None:
            if relationship_section.record_count != 0:
                raise ValueError(
                    "a non-zero relationship manifest requires publication authority"
                )
            return self

        internal_request = relationship_request.internal_reference_projection_request
        internal_result = relationship_request.internal_reference_projection_result
        if internal_request is None or internal_result is None:
            raise ValueError(
                "relationship publication authority requires an internal reference pair"
            )
        if relationship_request.relationship_registry_version != (
            INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
        ):
            raise ValueError(
                "relationship publication authority requires the combined registry"
            )
        try:
            replayed_relationships = create_ephemeral_relationship_projection().project(
                relationship_request
            )
            candidate_request = CandidateProjectionRequest(
                release_id=self.release_id,
                build_run_id=internal_request.build_run_id,
                as_of=internal_request.as_of,
                internal_reference_projection_request=internal_request,
                internal_reference_projection_result=internal_result,
            )
            replayed_candidate = compose_candidate_projections(candidate_request)
        except (
            CandidateProjectionIntegrityError,
            RelationshipProjectionIntegrityError,
            TypeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise ValueError(
                "relationship publication authority cannot be replayed exactly"
            ) from exc
        if replayed_relationships != relationship_result:
            raise ValueError(
                "relationship publication result differs from exact replay"
            )
        replayed_manifests = {
            item.projection_id: item
            for item in replayed_candidate.published_projections
        }
        published_manifests = {
            item.projection_id: item for item in self.manifest.published_projections
        }
        if (
            len(replayed_manifests) != len(replayed_candidate.published_projections)
            or len(published_manifests) != len(self.manifest.published_projections)
            or replayed_manifests != published_manifests
        ):
            raise ValueError(
                "relationship graph differs from published projection manifests"
            )
        if (
            relationship_section.release_id != self.release_id
            or relationship_request.release_id != self.release_id
            or relationship_result.release_id != self.release_id
            or relationship_section.version
            != relationship_result.projection_schema_version
            or relationship_section.record_count
            != len(relationship_result.current_relationships)
            or relationship_section.content_sha256 != relationship_result.content_sha256
        ):
            raise ValueError("relationship manifest differs from publication authority")
        return self


class _NoAlembicOptions:
    def get_main_option(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        del name
        return default


def prepare_isolated_release_database_target(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
) -> DestructiveDatabaseTarget:
    """Resolve and connect-check one explicit disposable rehearsal database."""

    if not database_url.strip() or not expected_database.strip():
        raise IsolatedReleaseTargetSafetyError(
            "an explicit isolated release database URL and identity are required"
        )
    if target_kind.casefold() != "disposable":
        raise IsolatedReleaseTargetSafetyError(
            "isolated release rehearsal requires a disposable database target"
        )
    target = _resolve_explicit_target(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
    )
    require_accepted_backup_gate(backup_gate_root)
    with _connect_postgres(target.url) as connection:
        _verify_database_identity(target, connection)
    return target


def read_isolated_active_release(
    database_target: DestructiveDatabaseTarget,
) -> dict[str, str]:
    """Read the one internally consistent active release from an isolated database."""

    target = _validate_database_target(database_target)
    with _connect_postgres(target.url) as connection:
        _verify_database_identity(target, connection)
        release_id, state = _read_active_release_row(connection)
    if release_id not in set(state.values()):
        raise IsolatedReleaseTargetSafetyError(
            "isolated active release primary identity differs from its projections"
        )
    return state


def create_isolated_release_publication(
    *,
    database_target: DestructiveDatabaseTarget,
    prior_release: IsolatedReleaseBundle,
    candidate_release: IsolatedReleaseBundle,
    backup_gate_root: Path,
    embedding_adapter: EmbeddingAdapter,
    verification_store: MutableMapping[str, ReleaseVerification],
    discrepancy_store: MutableMapping[
        str,
        tuple[IndexPointDiscrepancy, ...],
    ],
    publication_history: MutableSequence[PublishedRelease],
    clock: Callable[[], datetime],
) -> ReleasePublication:
    """Compose S7F over complete physical audits and one atomic DB pointer."""

    prior_release, candidate_release = _validate_bundle_pair(
        prior_release,
        candidate_release,
    )
    require_accepted_backup_gate(backup_gate_root)
    _validate_target_marker(prior_release.index_target)
    _validate_target_marker(candidate_release.index_target)
    target = _validate_database_target(database_target)
    state = _PostgresActiveReleaseState(
        target=target,
        expected_prior_release_id=prior_release.release_id,
        clock=clock,
    )
    _validate_database_release_registry(
        target,
        prior_release=prior_release,
        candidate_release=candidate_release,
    )
    return _IsolatedReleasePublication(
        database_target=target,
        prior_release=prior_release,
        candidate_release=candidate_release,
        backup_gate_root=backup_gate_root.resolve(strict=False),
        embedding_adapter=embedding_adapter,
        active_release_state=state,
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=publication_history,
        clock=clock,
    )


class _IsolatedReleasePublication(ReleasePublication):
    def __init__(
        self,
        *,
        database_target: DestructiveDatabaseTarget,
        prior_release: IsolatedReleaseBundle,
        candidate_release: IsolatedReleaseBundle,
        backup_gate_root: Path,
        embedding_adapter: EmbeddingAdapter,
        active_release_state: MutableMapping[str, str],
        verification_store: MutableMapping[str, ReleaseVerification],
        discrepancy_store: MutableMapping[
            str,
            tuple[IndexPointDiscrepancy, ...],
        ],
        publication_history: MutableSequence[PublishedRelease],
        clock: Callable[[], datetime],
    ) -> None:
        self._database_target = database_target
        self._prior_release = prior_release
        self._candidate_release = candidate_release
        self._backup_gate_root = backup_gate_root
        self._embedding_adapter = embedding_adapter
        self._active_release_state = active_release_state
        self._verification_store = verification_store
        self._discrepancy_store = discrepancy_store
        self._publication_history = publication_history
        self._clock = clock
        self._delegate: ReleasePublication | None = None
        self._verified_snapshot: IsolatedIndexSnapshot | None = None

    def verify(self, candidate_release_id: str) -> ReleaseVerification:
        if candidate_release_id != self._candidate_release.release_id:
            raise ValueError("unknown isolated candidate release")
        self._preflight()
        snapshot = self._audit_bundle(
            self._candidate_release,
            require_exact_points=False,
        )
        delegate = self._compose(snapshot)
        verification = delegate.verify(candidate_release_id)
        self._delegate = delegate
        self._verified_snapshot = snapshot
        return verification

    def promote(self, accepted_release_id: str) -> PublishedRelease:
        if accepted_release_id != self._candidate_release.release_id:
            raise ValueError("unknown isolated candidate release")
        verification = self._verification_store.get(accepted_release_id)
        if (
            verification is None
            or not verification.accepted
            or self._verified_snapshot is None
        ):
            raise ValueError("release is not accepted")
        self._preflight()
        snapshot = self._audit_bundle(
            self._candidate_release,
            require_exact_points=False,
        )
        if snapshot != self._verified_snapshot:
            raise ValueError("release physical snapshot changed after verification")
        delegate = self._compose(snapshot)
        published = delegate.promote(accepted_release_id)
        self._delegate = delegate
        return published

    def rollback(self, published_release_id: str) -> PublishedRelease:
        if published_release_id != self._candidate_release.release_id:
            raise ValueError("unknown isolated published release")
        if self._delegate is None:
            raise ValueError("published release has no isolated promotion checkpoint")
        self._preflight()
        self._audit_bundle(self._prior_release, require_exact_points=True)
        return self._delegate.rollback(published_release_id)

    def _preflight(self) -> None:
        require_accepted_backup_gate(self._backup_gate_root)
        _validate_database_target(self._database_target)
        _validate_database_release_registry(
            self._database_target,
            prior_release=self._prior_release,
            candidate_release=self._candidate_release,
        )

    def _audit_bundle(
        self,
        bundle: IsolatedReleaseBundle,
        *,
        require_exact_points: bool,
    ) -> IsolatedIndexSnapshot:
        snapshot = audit_isolated_index_snapshot(
            bundle.index_target,
            embedding_adapter=self._embedding_adapter,
        )
        if (
            snapshot.receipt.index_projections
            != bundle.index_result.actual_index_projections
            or snapshot.receipt.lookup_projections
            != bundle.index_result.actual_lookup_projections
            or snapshot.lookup_documents != bundle.index_result.lookup_documents
        ):
            raise IndexProjectionIntegrityError(
                "isolated physical receipt/lookup differs from the release bundle"
            )
        if require_exact_points and snapshot.points != bundle.index_result.points:
            raise IndexProjectionIntegrityError(
                "isolated rollback target points differ from the prior release"
            )
        return snapshot

    def _compose(self, snapshot: IsolatedIndexSnapshot) -> ReleasePublication:
        release_id = self._candidate_release.release_id
        return create_ephemeral_release_publication(
            candidate_manifests={release_id: self._candidate_release.manifest},
            actual_index_projections={
                release_id: snapshot.receipt.index_projections,
            },
            expected_index_points={
                release_id: self._candidate_release.index_result.points,
            },
            actual_index_points={release_id: snapshot.points},
            active_release_state=self._active_release_state,
            verification_store=self._verification_store,
            discrepancy_store=self._discrepancy_store,
            publication_history=self._publication_history,
            clock=self._clock,
        )


class _PostgresActiveReleaseState(dict[str, str]):
    """Cached three-key state whose only mutation is one guarded SQL update."""

    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        expected_prior_release_id: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._target = target
        self._clock = clock
        with _connect_postgres(target.url) as connection:
            _verify_database_identity(target, connection)
            release_id, state = _read_active_release_row(connection)
        if release_id != expected_prior_release_id or set(state.values()) != {
            expected_prior_release_id
        }:
            raise IsolatedReleaseTargetSafetyError(
                "isolated database does not point to the expected prior release"
            )
        super().__init__(state)

    def __setitem__(self, key: str, value: str) -> None:
        del key, value
        raise TypeError("isolated pointer state permits only one atomic update")

    def __delitem__(self, key: str) -> None:
        del key
        raise TypeError("isolated pointer state cannot delete release keys")

    def update(self, other: Any = (), /, **kwargs: str) -> None:
        requested = dict(other, **kwargs)
        if set(requested) != set(_ACTIVE_RELEASE_KEYS):
            raise IsolatedReleaseTargetSafetyError(
                "isolated pointer update requires exactly three release keys"
            )
        target_release_ids = set(requested.values())
        if len(target_release_ids) != 1 or "" in target_release_ids:
            raise IsolatedReleaseTargetSafetyError(
                "isolated pointer update requires one release identity"
            )
        previous_release_ids = set(self.values())
        if len(previous_release_ids) != 1:
            raise IsolatedReleaseTargetSafetyError(
                "cached isolated pointer contains mixed release identities"
            )
        target_release_id = next(iter(target_release_ids))
        previous_release_id = next(iter(previous_release_ids))
        with _connect_postgres(self._target.url) as connection:
            _verify_database_identity(self._target, connection)
            result = connection.execute(
                "UPDATE publish.active_release SET release_id = %s, "
                "canonical_release_id = %s, published_projection_release_id = %s, "
                "index_release_id = %s, previous_release_id = %s, changed_at = %s "
                "WHERE singleton = TRUE AND release_id = %s "
                "AND canonical_release_id = %s "
                "AND published_projection_release_id = %s "
                "AND index_release_id = %s",
                (
                    target_release_id,
                    target_release_id,
                    target_release_id,
                    target_release_id,
                    previous_release_id,
                    self._clock(),
                    previous_release_id,
                    previous_release_id,
                    previous_release_id,
                    previous_release_id,
                ),
            )
            if result.rowcount != 1:
                raise IsolatedReleaseTargetSafetyError(
                    "isolated active release changed before atomic pointer update"
                )
        super().clear()
        super().update(cast(Mapping[str, str], requested))


def _validate_bundle_pair(
    prior_release: IsolatedReleaseBundle,
    candidate_release: IsolatedReleaseBundle,
) -> tuple[IsolatedReleaseBundle, IsolatedReleaseBundle]:
    validated_bundles: list[IsolatedReleaseBundle] = []
    for label, bundle in (
        ("prior", prior_release),
        ("candidate", candidate_release),
    ):
        if type(bundle) is not IsolatedReleaseBundle:
            raise IsolatedReleaseTargetSafetyError(
                f"{label} release must be an exact IsolatedReleaseBundle"
            )
        try:
            validated = IsolatedReleaseBundle.model_validate(
                bundle.model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            raise IsolatedReleaseTargetSafetyError(
                f"{label} release bundle failed exact validation"
            ) from exc
        manifest_payload = cast(
            JsonValue,
            validated.manifest.model_dump(
                mode="json",
                exclude={"manifest_sha256"},
            ),
        )
        if validated.manifest.manifest_sha256 != _canonical_sha256(manifest_payload):
            raise IsolatedReleaseTargetSafetyError(
                f"{label} release manifest hash does not bind the complete manifest"
            )
        validated_bundles.append(validated)

    validated_prior, validated_candidate = validated_bundles
    if validated_prior.release_id == validated_candidate.release_id:
        raise IsolatedReleaseTargetSafetyError(
            "prior and candidate releases must have distinct identities"
        )
    if validated_prior.index_target.root == validated_candidate.index_target.root:
        raise IsolatedReleaseTargetSafetyError(
            "prior and candidate releases require distinct index targets"
        )
    return validated_prior, validated_candidate


def _resolve_explicit_target(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
) -> DestructiveDatabaseTarget:
    try:
        return resolve_destructive_database_target(
            _NoAlembicOptions(),
            {
                "ALEMBIC_DATABASE_URL": database_url,
                "ALEMBIC_EXPECTED_DATABASE": expected_database,
                "ALEMBIC_TARGET_KIND": target_kind,
            },
        )
    except DatabaseTargetSafetyError as exc:
        raise IsolatedReleaseTargetSafetyError(str(exc)) from exc


def _same_index_manifests(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    left_by_id = {manifest.projection_id: manifest for manifest in left}
    right_by_id = {manifest.projection_id: manifest for manifest in right}
    return (
        len(left_by_id) == len(left)
        and len(right_by_id) == len(right)
        and left_by_id == right_by_id
    )


def _validate_database_target(
    target: DestructiveDatabaseTarget,
) -> DestructiveDatabaseTarget:
    if target.target_kind != "disposable":
        raise IsolatedReleaseTargetSafetyError(
            "isolated release rehearsal requires a disposable database target"
        )
    resolved = _resolve_explicit_target(
        database_url=target.url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
    )
    if resolved != target:
        raise IsolatedReleaseTargetSafetyError(
            "isolated release database target identity differs"
        )
    return target


def _connect_postgres(database_url: str) -> psycopg.Connection[Any]:
    parsed = make_url(database_url).set(drivername="postgresql")
    dsn = parsed.render_as_string(hide_password=False)
    return psycopg.connect(dsn, autocommit=False)


def _verify_database_identity(
    target: DestructiveDatabaseTarget,
    connection: psycopg.Connection[Any],
) -> None:
    row = connection.execute(
        "SELECT current_database(), shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = current_database()"
    ).fetchone()
    if row is None:
        raise IsolatedReleaseTargetSafetyError(
            "isolated database identity row is missing"
        )
    try:
        target.verify_database_identity(
            actual_database=row[0],
            database_marker=row[1],
        )
    except DatabaseTargetSafetyError as exc:
        raise IsolatedReleaseTargetSafetyError(str(exc)) from exc


def _read_active_release_row(
    connection: psycopg.Connection[Any],
) -> tuple[str, dict[str, str]]:
    rows = connection.execute(
        "SELECT release_id, canonical_release_id, "
        "published_projection_release_id, index_release_id "
        "FROM publish.active_release WHERE singleton = TRUE"
    ).fetchall()
    if len(rows) != 1 or any(
        not isinstance(value, str) or not value for value in rows[0]
    ):
        raise IsolatedReleaseTargetSafetyError(
            "isolated database requires one complete active release row"
        )
    release_id, canonical_release_id, published_release_id, index_release_id = rows[0]
    state = {
        "canonical_release_id": canonical_release_id,
        "published_projection_release_id": published_release_id,
        "index_release_id": index_release_id,
    }
    if {release_id, *state.values()} != {release_id}:
        raise IsolatedReleaseTargetSafetyError(
            "isolated active release contains mixed release identities"
        )
    return release_id, state


def _validate_database_release_registry(
    target: DestructiveDatabaseTarget,
    *,
    prior_release: IsolatedReleaseBundle,
    candidate_release: IsolatedReleaseBundle,
) -> None:
    expected = {
        prior_release.release_id: prior_release.manifest.manifest_sha256,
        candidate_release.release_id: candidate_release.manifest.manifest_sha256,
    }
    with _connect_postgres(target.url) as connection:
        _verify_database_identity(target, connection)
        rows = connection.execute(
            "SELECT release.release_id, release.state, release.manifest_sha256, "
            "manifest.manifest_sha256 "
            "FROM knowledge.release AS release "
            "JOIN publish.build_manifest AS manifest USING (release_id) "
            "WHERE release.release_id = ANY(%s) ORDER BY release.release_id",
            (list(sorted(expected)),),
        ).fetchall()
    if len(rows) != 2:
        raise IsolatedReleaseTargetSafetyError(
            "isolated database release registry is incomplete"
        )
    for release_id, state, release_hash, manifest_hash in rows:
        if (
            release_id not in expected
            or str(state) != "accepted"
            or release_hash != expected[release_id]
            or manifest_hash != expected[release_id]
        ):
            raise IsolatedReleaseTargetSafetyError(
                "isolated database release registry differs from the bundles"
            )


__all__ = [
    "IsolatedReleaseBundle",
    "IsolatedReleaseTargetSafetyError",
    "create_isolated_release_publication",
    "prepare_isolated_release_database_target",
    "read_isolated_active_release",
]
