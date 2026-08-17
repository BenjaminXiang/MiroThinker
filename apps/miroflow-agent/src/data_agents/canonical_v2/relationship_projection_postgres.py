"""Guarded PostgreSQL adapter for immutable Canonical V2 relationships."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, JsonValue, ValidationError
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import DatabaseTargetSafetyError
from src.data_agents.storage.database_target import DestructiveDatabaseTarget
from src.data_agents.storage.database_target import resolve_destructive_database_target

from .canonical_revision import CanonicalRevisionError
from .canonical_revision import load_canonical_v2_script_directory
from .canonical_revision import require_minimum_canonical_revision
from .contracts import RelationshipAssertion
from .contracts import RelationshipType
from .rebuild_write_gate import require_accepted_backup_gate
from .relationship_projection import (
    CURRENT_RELATIONSHIP_PROJECTION_SCHEMA_VERSION,
    LEGACY_RELATIONSHIP_PROJECTION_SCHEMA_VERSION,
    LEGACY_RELATIONSHIP_REGISTRY_VERSION,
    RelationshipProjectionRequest,
    RelationshipProjectionResult,
    create_ephemeral_relationship_projection,
)


MINIMUM_REVISION = "C2_0010"
VERSION_TABLE = "public.canonical_v2_alembic_version"


def _canonical_json(value: Any) -> JsonValue:
    if isinstance(value, BaseModel):
        return cast(JsonValue, value.model_dump(mode="json"))
    if isinstance(value, tuple):
        return cast(JsonValue, [_canonical_json(item) for item in value])
    if isinstance(value, list):
        return cast(JsonValue, [_canonical_json(item) for item in value])
    if isinstance(value, dict):
        return cast(
            JsonValue,
            {str(key): _canonical_json(item) for key, item in value.items()},
        )
    return cast(JsonValue, value)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _model_hash(value: BaseModel) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def _legacy_request_content_sha256(request: RelationshipProjectionRequest) -> str:
    payload = request.model_dump(mode="json")
    for field_name in (
        "relationship_registry_version",
        "relationship_registry_content_sha256",
        "internal_reference_projection_request",
        "internal_reference_projection_result",
    ):
        payload.pop(field_name, None)
    return _canonical_sha256(payload)


def _legacy_outcome_hash(value: BaseModel) -> str:
    payload = value.model_dump(mode="json")
    payload.pop("relationship_type_version", None)
    return _canonical_sha256(payload)


def _request_uses_internal_reference(
    request: RelationshipProjectionRequest,
) -> bool:
    internal_types = {"person", "technology_concept", "technology_route"}
    relationship_endpoints = (
        endpoint
        for candidate in request.candidates
        for endpoint in (candidate.source_endpoint, candidate.target_endpoint)
    )
    typed_assertion_endpoints = (
        endpoint
        for assertion in request.typed_relationship_assertions
        for endpoint in (assertion.source_endpoint, assertion.target_endpoint)
    )
    probe_endpoints = (
        endpoint
        for probe in request.direction_probes
        for endpoint in (probe.source_endpoint, probe.target_endpoint)
    )
    return (
        request.relationship_registry_version != LEGACY_RELATIONSHIP_REGISTRY_VERSION
        or request.internal_reference_projection_request is not None
        or request.internal_reference_projection_result is not None
        or any(
            endpoint.endpoint_type in internal_types
            for endpoint in (
                *relationship_endpoints,
                *typed_assertion_endpoints,
                *probe_endpoints,
            )
        )
        or any(
            endpoint.entity_type in internal_types
            for assertion in request.relationship_assertions
            for endpoint in (assertion.source_endpoint, assertion.target_endpoint)
        )
        or any(
            assignment.entity_type in internal_types
            for assignment in request.source_canonical_assignments
        )
    )


def _legacy_result_is_current_equivalent(
    request: RelationshipProjectionRequest,
    historical: RelationshipProjectionResult,
    current: RelationshipProjectionResult,
) -> bool:
    if (
        historical.projection_schema_version
        != LEGACY_RELATIONSHIP_PROJECTION_SCHEMA_VERSION
        or current.projection_schema_version
        != CURRENT_RELATIONSHIP_PROJECTION_SCHEMA_VERSION
    ):
        return False
    versions = {
        candidate.candidate_id: candidate.relationship_type_version
        for candidate in request.candidates
    }
    if any(
        outcome.candidate_id not in versions
        for outcome in historical.candidate_outcomes
    ):
        return False
    upgraded_outcomes = tuple(
        outcome.model_copy(
            update={
                "relationship_type_version": versions[outcome.candidate_id],
            }
        )
        for outcome in historical.candidate_outcomes
    )
    try:
        upgraded = RelationshipProjectionResult.model_validate(
            {
                **historical.model_dump(mode="python"),
                "projection_schema_version": (
                    CURRENT_RELATIONSHIP_PROJECTION_SCHEMA_VERSION
                ),
                "candidate_outcomes": upgraded_outcomes,
                "content_sha256": current.content_sha256,
            }
        )
    except (TypeError, ValueError, ValidationError):
        return False
    return upgraded == current


def _temporal_json(value: Any | None) -> Jsonb | None:
    return Jsonb(value.model_dump(mode="json")) if value is not None else None


class RelationshipProjectionPersistenceError(RuntimeError):
    """Durable relationship projection is unavailable or internally inconsistent."""


class RelationshipProjectionStore(ABC):
    """Persist and reconstruct one immutable relationship projection batch."""

    @abstractmethod
    def persist(
        self,
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> RelationshipProjectionResult:
        """Atomically persist an exact validated batch or replay it."""

    @abstractmethod
    def load(
        self,
        release_id: str,
        projection_run_id: str,
    ) -> RelationshipProjectionResult:
        """Load and validate one exact durable batch."""


class _ExplicitTargetConfig:
    def __init__(
        self,
        *,
        database_url: str,
        expected_database: str,
        target_kind: str,
    ) -> None:
        self._options = {
            "sqlalchemy.url": database_url,
            "miroflow.expected_database": expected_database,
            "miroflow.target_kind": target_kind,
        }

    def get_main_option(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        return self._options.get(name, default)


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


class _PostgresRelationshipProjectionStore(RelationshipProjectionStore):
    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        backup_gate_root: Path,
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._dsn = _psycopg_dsn(target.url)

    def _verify_connected_target(
        self,
        connection: psycopg.Connection[dict[str, Any]],
    ) -> None:
        identity = connection.execute(
            "SELECT current_database() AS database_name, "
            "shobj_description(oid, 'pg_database') AS database_marker "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        if identity is None:
            raise RelationshipProjectionPersistenceError(
                "PostgreSQL relationship target identity cannot be read"
            )
        try:
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
        except DatabaseTargetSafetyError as exc:
            raise RelationshipProjectionPersistenceError(
                "PostgreSQL relationship target identity is invalid"
            ) from exc
        revisions = connection.execute(
            f"SELECT version_num FROM {VERSION_TABLE}"
        ).fetchall()
        if len(revisions) != 1:
            raise RelationshipProjectionPersistenceError(
                "relationship target requires exactly one Alembic revision row"
            )
        try:
            require_minimum_canonical_revision(
                scripts=load_canonical_v2_script_directory(),
                current_revision=revisions[0]["version_num"],
                minimum_revision=MINIMUM_REVISION,
            )
        except CanonicalRevisionError as exc:
            raise RelationshipProjectionPersistenceError(
                f"relationship target does not satisfy {MINIMUM_REVISION}"
            ) from exc

    @contextmanager
    def _connection(
        self,
        *,
        write: bool,
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        require_accepted_backup_gate(self._backup_gate_root)
        try:
            connection = cast(
                psycopg.Connection[dict[str, Any]],
                psycopg.connect(
                    self._dsn,
                    autocommit=False,
                    row_factory=cast(Any, dict_row),
                ),
            )
        except psycopg.Error as exc:
            raise RelationshipProjectionPersistenceError(
                "PostgreSQL relationship target cannot be connected"
            ) from exc
        try:
            self._verify_connected_target(connection)
            connection.rollback()
            if not write:
                connection.execute(
                    "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
            yield connection
        except psycopg.Error as exc:
            connection.rollback()
            raise RelationshipProjectionPersistenceError(
                "PostgreSQL relationship verification or transaction failed"
            ) from exc
        finally:
            connection.close()

    def verify_ready(self) -> None:
        with self._connection(write=False) as connection:
            required_names = (
                "knowledge.relationship_projection_run",
                "knowledge.relationship_projection_shared_assertion",
                "knowledge.relationship_projection_shared_decision",
                "knowledge.typed_relationship_assertion",
                "knowledge.typed_relationship_decision",
                "knowledge.typed_relationship_decision_assertion",
                "knowledge.relationship_projection_outcome",
                "knowledge.current_relationship_projection",
            )
            required = connection.execute(
                "SELECT relation_name, to_regclass(relation_name) AS relation "
                "FROM unnest(%s::text[]) AS required(relation_name) "
                "ORDER BY relation_name",
                (list(required_names),),
            ).fetchall()
            if len(required) != len(required_names) or any(
                row["relation"] is None for row in required
            ):
                raise RelationshipProjectionPersistenceError(
                    "relationship projection schema is incomplete"
                )
            connection.rollback()

    @staticmethod
    def _validated_pair(
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> tuple[RelationshipProjectionRequest, RelationshipProjectionResult]:
        if not isinstance(request, RelationshipProjectionRequest) or not isinstance(
            result, RelationshipProjectionResult
        ):
            raise RelationshipProjectionPersistenceError(
                "persist requires typed relationship request and result"
            )
        try:
            validated_request = RelationshipProjectionRequest.model_validate(
                request.model_dump(mode="python")
            )
            validated_result = RelationshipProjectionResult.model_validate(
                result.model_dump(mode="python")
            )
            if _request_uses_internal_reference(validated_request):
                raise RelationshipProjectionPersistenceError(
                    "internal-reference relationship persistence is deferred until "
                    "its canonical projections are durable"
                )
            projected = create_ephemeral_relationship_projection().project(
                validated_request
            )
        except (TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise RelationshipProjectionPersistenceError(
                "relationship request/result failed typed validation"
            ) from exc
        if projected != validated_result and not _legacy_result_is_current_equivalent(
            validated_request,
            validated_result,
            projected,
        ):
            raise RelationshipProjectionPersistenceError(
                "relationship result is not the exact projection of its request"
            )
        return validated_request, validated_result

    @staticmethod
    def _require_candidate_release(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        release = connection.execute(
            "SELECT state FROM knowledge.release WHERE release_id = %s FOR SHARE",
            (result.release_id,),
        ).fetchone()
        if release is None or release["state"] != "candidate":
            raise RelationshipProjectionPersistenceError(
                "relationship persistence requires an existing candidate release"
            )

    @staticmethod
    def _insert_relationship_types(
        connection: psycopg.Connection[dict[str, Any]],
        relationship_types: tuple[RelationshipType, ...],
    ) -> None:
        ordered_types = tuple(
            sorted(
                relationship_types,
                key=lambda item: (item.relationship_type_id, item.version),
            )
        )
        keys = tuple(
            (item.relationship_type_id, item.version) for item in ordered_types
        )
        if len(keys) != len(set(keys)):
            raise RelationshipProjectionPersistenceError(
                "relationship catalog contains duplicate exact-version keys"
            )
        for relationship_type in ordered_types:
            connection.execute(
                "INSERT INTO knowledge.relationship_type "
                "(relationship_type_id, version, layer, source_entity_types, "
                "target_entity_types, direction, roles, required_evidence_kinds, "
                "time_semantics, allowed_states, eligible_paths) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    relationship_type.relationship_type_id,
                    relationship_type.version,
                    relationship_type.layer.value,
                    Jsonb(list(relationship_type.source_entity_types)),
                    Jsonb(list(relationship_type.target_entity_types)),
                    relationship_type.direction.value,
                    Jsonb(
                        [
                            role.model_dump(mode="json")
                            for role in relationship_type.roles
                        ]
                    ),
                    Jsonb(list(relationship_type.required_evidence_kinds)),
                    relationship_type.time_semantics.value,
                    Jsonb(list(relationship_type.allowed_states)),
                    Jsonb(list(relationship_type.eligible_paths)),
                ),
            )
        rows = connection.execute(
            "SELECT relationship_type_id, version, layer, source_entity_types, "
            "target_entity_types, direction, roles, required_evidence_kinds, "
            "time_semantics, allowed_states, eligible_paths "
            "FROM knowledge.relationship_type "
            "WHERE (relationship_type_id, version) IN ("
            "SELECT * FROM unnest(%s::text[], %s::text[])) "
            "ORDER BY relationship_type_id, version",
            (
                [item.relationship_type_id for item in ordered_types],
                [item.version for item in ordered_types],
            ),
        ).fetchall()
        durable = tuple(RelationshipType.model_validate(row) for row in rows)
        if durable != ordered_types:
            raise RelationshipProjectionPersistenceError(
                "installed relationship catalog conflicts with durable rows"
            )

    @staticmethod
    def _insert_policy(
        connection: psycopg.Connection[dict[str, Any]],
        request: RelationshipProjectionRequest,
    ) -> None:
        policy = request.decision_policy
        connection.execute(
            "INSERT INTO knowledge.policy "
            "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                policy.policy_id,
                policy.policy_version,
                policy.policy_kind.value,
                policy.content_sha256,
                policy.effective_at,
            ),
        )
        row = connection.execute(
            "SELECT policy_id, policy_version, policy_kind, content_sha256, "
            "effective_at FROM knowledge.policy WHERE policy_id = %s "
            "AND policy_version = %s",
            (policy.policy_id, policy.policy_version),
        ).fetchone()
        if row is None or row != policy.model_dump(mode="python"):
            raise RelationshipProjectionPersistenceError(
                "relationship policy conflicts with durable content"
            )

    @staticmethod
    def _require_shared_inputs(
        connection: psycopg.Connection[dict[str, Any]],
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> None:
        assignments = {
            assignment.source_identity_id: assignment
            for assignment in request.source_canonical_assignments
        }
        for assertion in result.retained_relationship_assertions:
            row = connection.execute(
                "SELECT assertion.assertion_id, assertion.relationship_type_id, "
                "assertion.relationship_type_version, assertion.source_record_id, "
                "assertion.source_identity_id, source_identity.entity_type "
                "AS source_entity_type, assertion.target_identity_id, "
                "target_identity.entity_type AS target_entity_type, "
                "assertion.attributes, assertion.assertion_fingerprint_sha256, "
                "assertion.observed_at, assertion.source_event_time, "
                "assertion.valid_from_temporal, assertion.valid_to_temporal, "
                "assertion.assertion_run_id FROM knowledge.relationship_assertion "
                "AS assertion JOIN knowledge.source_identity AS source_identity "
                "ON source_identity.source_identity_id = assertion.source_identity_id "
                "JOIN knowledge.source_identity AS target_identity "
                "ON target_identity.source_identity_id = assertion.target_identity_id "
                "WHERE assertion.assertion_id = %s",
                (assertion.assertion_id,),
            ).fetchone()
            durable_assertion = None
            if row is not None:
                try:
                    durable_assertion = RelationshipAssertion.model_validate(
                        {
                            "assertion_id": row["assertion_id"],
                            "relationship_type_id": row["relationship_type_id"],
                            "relationship_type_version": row[
                                "relationship_type_version"
                            ],
                            "source_record_id": row["source_record_id"],
                            "source_endpoint": {
                                "identity_id": row["source_identity_id"],
                                "identity_space": "source",
                                "entity_type": row["source_entity_type"],
                            },
                            "target_endpoint": {
                                "identity_id": row["target_identity_id"],
                                "identity_space": "source",
                                "entity_type": row["target_entity_type"],
                            },
                            "attributes": row["attributes"],
                            "observed_at": row["observed_at"],
                            "source_event_time": row["source_event_time"],
                            "valid_from": row["valid_from_temporal"],
                            "valid_to": row["valid_to_temporal"],
                            "assertion_run_id": row["assertion_run_id"],
                        }
                    )
                except ValidationError:
                    durable_assertion = None
            if (
                row is None
                or row["assertion_fingerprint_sha256"] != _model_hash(assertion)
                or durable_assertion != assertion
            ):
                raise RelationshipProjectionPersistenceError(
                    "shared relationship assertion is not already durable exactly"
                )
            for endpoint in (assertion.source_endpoint, assertion.target_endpoint):
                assignment = assignments.get(endpoint.identity_id)
                if assignment is None:
                    raise RelationshipProjectionPersistenceError(
                        "shared relationship source assignment is incomplete"
                    )
                durable_assignment = connection.execute(
                    "SELECT canonical_identity_id FROM "
                    "knowledge.current_source_identity_assignment "
                    "WHERE release_id = %s AND source_identity_id = %s",
                    (result.release_id, endpoint.identity_id),
                ).fetchone()
                if (
                    durable_assignment is None
                    or durable_assignment["canonical_identity_id"]
                    != assignment.canonical_identity_id
                ):
                    raise RelationshipProjectionPersistenceError(
                        "shared relationship assignment is not durable exactly"
                    )
                durable_records = connection.execute(
                    "SELECT record_id FROM knowledge.source_identity_record "
                    "WHERE source_identity_id = %s ORDER BY record_id",
                    (endpoint.identity_id,),
                ).fetchall()
                if not set(assignment.source_record_refs) <= {
                    row["record_id"] for row in durable_records
                }:
                    raise RelationshipProjectionPersistenceError(
                        "shared relationship source-record assignment is incomplete"
                    )
        for decision in result.relationship_decisions:
            row = connection.execute(
                "SELECT canonical_relationship_id, relationship_type_id, "
                "relationship_type_version, source_canonical_identity_id, "
                "target_canonical_identity_id, state, role_bindings, policy_id, "
                "policy_version, method, method_version, decision_run_id, confidence, "
                "rationale, valid_from_temporal, valid_to_temporal, decided_at, "
                "supersedes_decision_id FROM knowledge.relationship_decision "
                "WHERE release_id = %s AND decision_id = %s",
                (decision.release_id, decision.decision_id),
            ).fetchone()
            if row is None:
                raise RelationshipProjectionPersistenceError(
                    "shared relationship decision is not already durable"
                )
            expected = {
                "canonical_relationship_id": decision.canonical_relationship_id,
                "relationship_type_id": decision.relationship_type_id,
                "relationship_type_version": decision.relationship_type_version,
                "source_canonical_identity_id": decision.source_canonical_identity_id,
                "target_canonical_identity_id": decision.target_canonical_identity_id,
                "state": decision.state.value,
                "role_bindings": decision.role_bindings,
                "policy_id": decision.policy.policy_id,
                "policy_version": decision.policy.policy_version,
                "method": decision.method.value,
                "method_version": decision.method_version,
                "decision_run_id": decision.decision_run_id,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "valid_from_temporal": (
                    decision.valid_from.model_dump(mode="json")
                    if decision.valid_from is not None
                    else None
                ),
                "valid_to_temporal": (
                    decision.valid_to.model_dump(mode="json")
                    if decision.valid_to is not None
                    else None
                ),
                "decided_at": decision.decided_at,
                "supersedes_decision_id": decision.supersedes_decision_id,
            }
            if row != expected:
                raise RelationshipProjectionPersistenceError(
                    "shared relationship decision durable content conflicts"
                )
            role_rows = connection.execute(
                "SELECT assertion_id, assertion_role FROM "
                "knowledge.relationship_decision_assertion WHERE release_id = %s "
                "AND decision_id = %s ORDER BY assertion_role, assertion_id",
                (decision.release_id, decision.decision_id),
            ).fetchall()
            durable_roles = {
                "candidate": tuple(
                    item["assertion_id"]
                    for item in role_rows
                    if item["assertion_role"] == "candidate"
                ),
                "selected": tuple(
                    item["assertion_id"]
                    for item in role_rows
                    if item["assertion_role"] == "selected"
                ),
                "conflicting": tuple(
                    item["assertion_id"]
                    for item in role_rows
                    if item["assertion_role"] == "conflicting"
                ),
            }
            if durable_roles != {
                "candidate": decision.candidate_assertion_ids,
                "selected": decision.selected_assertion_ids,
                "conflicting": decision.conflicting_assertion_ids,
            }:
                raise RelationshipProjectionPersistenceError(
                    "shared relationship decision assertion roles conflict"
                )

    @staticmethod
    def _require_retained_evidence(
        connection: psycopg.Connection[dict[str, Any]],
        request: RelationshipProjectionRequest,
    ) -> None:
        artifacts = {
            artifact.reference_id: artifact for artifact in request.retained_artifacts
        }
        for artifact in artifacts.values():
            row = connection.execute(
                "SELECT content_sha256 FROM landing.evidence_artifact "
                "WHERE artifact_id = %s",
                (artifact.artifact_id,),
            ).fetchone()
            if row is None or row["content_sha256"] != artifact.content_sha256:
                raise RelationshipProjectionPersistenceError(
                    "retained artifact is not durable exactly"
                )
        for retained_assertion in request.retained_assertions:
            row = connection.execute(
                "SELECT artifact_id FROM landing.source_record WHERE record_id = %s",
                (retained_assertion.source_record_ref,),
            ).fetchone()
            if row is None:
                raise RelationshipProjectionPersistenceError(
                    "retained assertion source record is not durable"
                )
            referenced_artifact_ids = {
                artifacts[reference_id].artifact_id
                for reference_id in retained_assertion.artifact_refs
            }
            if (
                referenced_artifact_ids
                and row["artifact_id"] not in referenced_artifact_ids
            ):
                raise RelationshipProjectionPersistenceError(
                    "retained assertion source-record artifact is cross-wired"
                )

    @staticmethod
    def _insert_run(
        connection: psycopg.Connection[dict[str, Any]],
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> None:
        connection.execute(
            "INSERT INTO knowledge.relationship_projection_run "
            "(release_id, projection_run_id, catalog_schema_version, catalog_version, "
            "catalog_content_sha256, as_of, temporal_comparison_context, "
            "retained_assertion_refs, retained_artifact_refs, request_content_sha256, "
            "result_content_sha256, result_payload) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                result.release_id,
                result.projection_run_id,
                result.catalog.schema_version,
                result.catalog.catalog_version,
                result.catalog.content_sha256,
                result.as_of,
                (
                    Jsonb(request.temporal_comparison_context.model_dump(mode="json"))
                    if request.temporal_comparison_context is not None
                    else None
                ),
                Jsonb(list(result.retained_assertion_refs)),
                Jsonb(list(result.retained_artifact_refs)),
                _canonical_sha256(request.model_dump(mode="json")),
                result.content_sha256,
                Jsonb(result.model_dump(mode="json")),
            ),
        )

    @staticmethod
    def _insert_shared_memberships(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        for assertion in result.retained_relationship_assertions:
            connection.execute(
                "INSERT INTO knowledge.relationship_projection_shared_assertion "
                "(release_id, projection_run_id, assertion_id, content_sha256) "
                "VALUES (%s, %s, %s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    assertion.assertion_id,
                    _model_hash(assertion),
                ),
            )
        for decision in result.relationship_decisions:
            connection.execute(
                "INSERT INTO knowledge.relationship_projection_shared_decision "
                "(release_id, projection_run_id, decision_id, content_sha256) "
                "VALUES (%s, %s, %s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    decision.decision_id,
                    _model_hash(decision),
                ),
            )

    @staticmethod
    def _insert_typed_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        for assertion in result.typed_relationship_assertions:
            connection.execute(
                "INSERT INTO knowledge.typed_relationship_assertion "
                "(release_id, projection_run_id, assertion_id, relationship_type_id, "
                "relationship_type_version, source_record_id, source_endpoint, "
                "target_endpoint, attributes, evidence_bindings, observed_at, "
                "source_event_time, valid_from_temporal, valid_to_temporal, "
                "assertion_run_id, content_sha256) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    assertion.assertion_id,
                    assertion.relationship_type_id,
                    assertion.relationship_type_version,
                    assertion.source_record_ref,
                    Jsonb(assertion.source_endpoint.model_dump(mode="json")),
                    Jsonb(assertion.target_endpoint.model_dump(mode="json")),
                    Jsonb(assertion.attributes),
                    Jsonb(
                        [
                            binding.model_dump(mode="json")
                            for binding in assertion.evidence_bindings
                        ]
                    ),
                    assertion.observed_at,
                    assertion.source_event_time,
                    _temporal_json(assertion.valid_from),
                    _temporal_json(assertion.valid_to),
                    assertion.assertion_run_id,
                    _model_hash(assertion),
                ),
            )

    @staticmethod
    def _insert_typed_decisions(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        for decision in result.typed_relationship_decisions:
            connection.execute(
                "INSERT INTO knowledge.typed_relationship_decision "
                "(release_id, projection_run_id, decision_id, "
                "canonical_relationship_id, relationship_type_id, "
                "relationship_type_version, source_endpoint, target_endpoint, state, "
                "candidate_assertion_ids, selected_assertion_ids, "
                "conflicting_assertion_ids, role_bindings, selected_evidence_refs, "
                "policy_id, policy_version, method, method_version, confidence, "
                "rationale, valid_from_temporal, valid_to_temporal, decided_at, "
                "supersedes_decision_id, content_sha256) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    decision.decision_id,
                    decision.canonical_relationship_id,
                    decision.relationship_type_id,
                    decision.relationship_type_version,
                    Jsonb(decision.source_endpoint.model_dump(mode="json")),
                    Jsonb(decision.target_endpoint.model_dump(mode="json")),
                    decision.state,
                    Jsonb(list(decision.candidate_assertion_ids)),
                    Jsonb(list(decision.selected_assertion_ids)),
                    Jsonb(list(decision.conflicting_assertion_ids)),
                    Jsonb(decision.role_bindings),
                    Jsonb(list(decision.selected_evidence_refs)),
                    decision.policy.policy_id,
                    decision.policy.policy_version,
                    decision.method.value,
                    decision.method_version,
                    decision.confidence,
                    decision.rationale,
                    _temporal_json(decision.valid_from),
                    _temporal_json(decision.valid_to),
                    decision.decided_at,
                    decision.supersedes_decision_id,
                    _model_hash(decision),
                ),
            )
            for role, assertion_ids in (
                ("candidate", decision.candidate_assertion_ids),
                ("selected", decision.selected_assertion_ids),
                ("conflicting", decision.conflicting_assertion_ids),
            ):
                for assertion_id in assertion_ids:
                    connection.execute(
                        "INSERT INTO knowledge.typed_relationship_decision_assertion "
                        "(release_id, projection_run_id, decision_id, assertion_id, "
                        "assertion_role) VALUES (%s, %s, %s, %s, %s)",
                        (
                            result.release_id,
                            result.projection_run_id,
                            decision.decision_id,
                            assertion_id,
                            role,
                        ),
                    )

    @staticmethod
    def _insert_outcomes(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        for outcome in result.candidate_outcomes:
            connection.execute(
                "INSERT INTO knowledge.relationship_projection_outcome "
                "(release_id, projection_run_id, candidate_id, relationship_type_id, "
                "admitted, outcome_payload, content_sha256) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    outcome.candidate_id,
                    outcome.relationship_type_id,
                    outcome.admitted,
                    Jsonb(outcome.model_dump(mode="json")),
                    _model_hash(outcome),
                ),
            )

    @staticmethod
    def _insert_current(
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        typed_decision_ids = {
            decision.decision_id for decision in result.typed_relationship_decisions
        }
        for current in result.current_relationships:
            connection.execute(
                "INSERT INTO knowledge.current_relationship_projection "
                "(release_id, projection_run_id, canonical_relationship_id, "
                "decision_id, decision_kind, relationship_type_id, "
                "relationship_type_version, source_endpoint, target_endpoint, "
                "role_bindings, selected_evidence_refs, effective_time_semantics, "
                "valid_from_temporal, valid_to_temporal, projected_at, content_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s)",
                (
                    result.release_id,
                    result.projection_run_id,
                    current.canonical_relationship_id,
                    current.decision_id,
                    "typed" if current.decision_id in typed_decision_ids else "shared",
                    current.relationship_type_id,
                    current.relationship_type_version,
                    Jsonb(current.source_endpoint.model_dump(mode="json")),
                    Jsonb(current.target_endpoint.model_dump(mode="json")),
                    Jsonb(current.role_bindings),
                    Jsonb(list(current.selected_evidence_refs)),
                    current.effective_time_semantics,
                    _temporal_json(current.valid_from),
                    _temporal_json(current.valid_to),
                    current.projected_at,
                    _model_hash(current),
                ),
            )

    @staticmethod
    def _expected_hashes[T: BaseModel](
        values: tuple[T, ...],
        identity: str,
    ) -> dict[str, str]:
        return {
            cast(str, getattr(value, identity)): _model_hash(value) for value in values
        }

    @classmethod
    def _verify_normalized_rows(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: RelationshipProjectionResult,
    ) -> None:
        specifications = (
            (
                "relationship_projection_shared_assertion",
                "assertion_id",
                cls._expected_hashes(
                    result.retained_relationship_assertions, "assertion_id"
                ),
            ),
            (
                "relationship_projection_shared_decision",
                "decision_id",
                cls._expected_hashes(result.relationship_decisions, "decision_id"),
            ),
            (
                "typed_relationship_assertion",
                "assertion_id",
                cls._expected_hashes(
                    result.typed_relationship_assertions, "assertion_id"
                ),
            ),
            (
                "typed_relationship_decision",
                "decision_id",
                cls._expected_hashes(
                    result.typed_relationship_decisions, "decision_id"
                ),
            ),
            (
                "relationship_projection_outcome",
                "candidate_id",
                (
                    {
                        outcome.candidate_id: _legacy_outcome_hash(outcome)
                        for outcome in result.candidate_outcomes
                    }
                    if result.projection_schema_version
                    == LEGACY_RELATIONSHIP_PROJECTION_SCHEMA_VERSION
                    else cls._expected_hashes(result.candidate_outcomes, "candidate_id")
                ),
            ),
            (
                "current_relationship_projection",
                "canonical_relationship_id",
                cls._expected_hashes(
                    result.current_relationships, "canonical_relationship_id"
                ),
            ),
        )
        for table, identity, expected in specifications:
            rows = connection.execute(
                sql.SQL(
                    "SELECT {} AS identity, content_sha256 FROM knowledge.{} "
                    "WHERE release_id = %s AND projection_run_id = %s "
                    "ORDER BY identity"
                ).format(sql.Identifier(identity), sql.Identifier(table)),
                (result.release_id, result.projection_run_id),
            ).fetchall()
            durable = {row["identity"]: row["content_sha256"] for row in rows}
            if durable != expected:
                raise RelationshipProjectionPersistenceError(
                    f"durable normalized relationship rows conflict in {table}"
                )
        for decision in result.typed_relationship_decisions:
            rows = connection.execute(
                "SELECT assertion_id, assertion_role FROM "
                "knowledge.typed_relationship_decision_assertion "
                "WHERE release_id = %s AND projection_run_id = %s "
                "AND decision_id = %s ORDER BY assertion_role, assertion_id",
                (
                    result.release_id,
                    result.projection_run_id,
                    decision.decision_id,
                ),
            ).fetchall()
            durable_roles = {
                role: tuple(
                    row["assertion_id"] for row in rows if row["assertion_role"] == role
                )
                for role in ("candidate", "selected", "conflicting")
            }
            if durable_roles != {
                "candidate": decision.candidate_assertion_ids,
                "selected": decision.selected_assertion_ids,
                "conflicting": decision.conflicting_assertion_ids,
            }:
                raise RelationshipProjectionPersistenceError(
                    "durable typed relationship decision assertion roles conflict"
                )

    @classmethod
    def _load_snapshot(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        release_id: str,
        projection_run_id: str,
    ) -> RelationshipProjectionResult:
        row = connection.execute(
            "SELECT release_id, projection_run_id, catalog_schema_version, "
            "catalog_version, catalog_content_sha256, as_of, "
            "retained_assertion_refs, retained_artifact_refs, "
            "result_content_sha256, result_payload FROM "
            "knowledge.relationship_projection_run WHERE release_id = %s "
            "AND projection_run_id = %s",
            (release_id, projection_run_id),
        ).fetchone()
        if row is None:
            raise RelationshipProjectionPersistenceError(
                "relationship projection batch does not exist"
            )
        try:
            result = RelationshipProjectionResult.model_validate(row["result_payload"])
        except (TypeError, ValueError, ValidationError) as exc:
            raise RelationshipProjectionPersistenceError(
                "durable relationship result payload is invalid"
            ) from exc
        if result.content_sha256 != row["result_content_sha256"]:
            raise RelationshipProjectionPersistenceError(
                "durable relationship result hash conflicts with payload"
            )
        durable_envelope = {
            "release_id": row["release_id"],
            "projection_run_id": row["projection_run_id"],
            "catalog_schema_version": row["catalog_schema_version"],
            "catalog_version": row["catalog_version"],
            "catalog_content_sha256": row["catalog_content_sha256"],
            "as_of": row["as_of"],
            "retained_assertion_refs": row["retained_assertion_refs"],
            "retained_artifact_refs": row["retained_artifact_refs"],
        }
        expected_envelope = {
            "release_id": result.release_id,
            "projection_run_id": result.projection_run_id,
            "catalog_schema_version": result.catalog.schema_version,
            "catalog_version": result.catalog.catalog_version,
            "catalog_content_sha256": result.catalog.content_sha256,
            "as_of": result.as_of,
            "retained_assertion_refs": list(result.retained_assertion_refs),
            "retained_artifact_refs": list(result.retained_artifact_refs),
        }
        if durable_envelope != expected_envelope:
            raise RelationshipProjectionPersistenceError(
                "durable relationship run envelope conflicts with payload"
            )
        cls._verify_normalized_rows(connection, result)
        return result

    def persist(
        self,
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> RelationshipProjectionResult:
        validated_request, validated_result = self._validated_pair(request, result)
        request_content_sha256 = _canonical_sha256(
            validated_request.model_dump(mode="json")
        )
        acceptable_request_hashes = {request_content_sha256}
        if (
            validated_request.relationship_registry_version
            == LEGACY_RELATIONSHIP_REGISTRY_VERSION
        ):
            acceptable_request_hashes.add(
                _legacy_request_content_sha256(validated_request)
            )
        try:
            with self._connection(write=True) as connection:
                try:
                    lock_identity = _canonical_sha256(
                        [
                            validated_result.release_id,
                            validated_result.projection_run_id,
                        ]
                    )
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (lock_identity,),
                    )
                    existing = connection.execute(
                        "SELECT request_content_sha256, result_content_sha256 FROM "
                        "knowledge.relationship_projection_run WHERE release_id = %s "
                        "AND projection_run_id = %s FOR UPDATE",
                        (
                            validated_result.release_id,
                            validated_result.projection_run_id,
                        ),
                    ).fetchone()
                    if existing is not None:
                        if (
                            existing["request_content_sha256"]
                            not in acceptable_request_hashes
                        ):
                            raise RelationshipProjectionPersistenceError(
                                "one release/run cannot identify changed request content"
                            )
                        durable = self._load_snapshot(
                            connection,
                            validated_result.release_id,
                            validated_result.projection_run_id,
                        )
                        if durable != validated_result and not (
                            _legacy_result_is_current_equivalent(
                                validated_request,
                                durable,
                                validated_result,
                            )
                            or _legacy_result_is_current_equivalent(
                                validated_request,
                                validated_result,
                                durable,
                            )
                        ):
                            raise RelationshipProjectionPersistenceError(
                                "idempotent relationship replay is not exact"
                            )
                        connection.rollback()
                        return durable

                    if (
                        validated_result.projection_schema_version
                        == LEGACY_RELATIONSHIP_PROJECTION_SCHEMA_VERSION
                    ):
                        raise RelationshipProjectionPersistenceError(
                            "legacy relationship results may replay existing runs only"
                        )

                    self._require_candidate_release(connection, validated_result)
                    self._require_retained_evidence(connection, validated_request)
                    self._require_shared_inputs(
                        connection, validated_request, validated_result
                    )
                    require_accepted_backup_gate(self._backup_gate_root)
                    self._verify_connected_target(connection)
                    self._insert_relationship_types(
                        connection, validated_result.relationship_types
                    )
                    self._insert_policy(connection, validated_request)
                    self._insert_run(connection, validated_request, validated_result)
                    self._insert_shared_memberships(connection, validated_result)
                    self._insert_typed_assertions(connection, validated_result)
                    self._insert_typed_decisions(connection, validated_result)
                    self._insert_outcomes(connection, validated_result)
                    self._insert_current(connection, validated_result)
                    connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    durable = self._load_snapshot(
                        connection,
                        validated_result.release_id,
                        validated_result.projection_run_id,
                    )
                    if durable != validated_result:
                        raise RelationshipProjectionPersistenceError(
                            "persisted relationship batch failed exact round-trip"
                        )
                    connection.commit()
                    return durable
                except Exception:
                    connection.rollback()
                    raise
        except RelationshipProjectionPersistenceError:
            raise
        except (KeyError, TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise RelationshipProjectionPersistenceError(
                "relationship projection could not be persisted exactly"
            ) from exc

    def load(
        self,
        release_id: str,
        projection_run_id: str,
    ) -> RelationshipProjectionResult:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (release_id, projection_run_id)
        ):
            raise RelationshipProjectionPersistenceError(
                "load requires non-empty release and projection run IDs"
            )
        with self._connection(write=False) as connection:
            result = self._load_snapshot(connection, release_id, projection_run_id)
            connection.rollback()
            return result


def create_postgres_relationship_projection_store(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
) -> RelationshipProjectionStore:
    """Create one explicit, backup-gated disposable PostgreSQL adapter."""
    require_accepted_backup_gate(backup_gate_root)
    try:
        target = resolve_destructive_database_target(
            _ExplicitTargetConfig(
                database_url=database_url,
                expected_database=expected_database,
                target_kind=target_kind,
            ),
            {},
        )
    except DatabaseTargetSafetyError as exc:
        raise RelationshipProjectionPersistenceError(
            "relationship target selection failed explicit safety checks"
        ) from exc
    if target.target_kind != "disposable":
        raise RelationshipProjectionPersistenceError(
            "relationship persistence is restricted to a disposable target"
        )
    store = _PostgresRelationshipProjectionStore(
        target=target,
        backup_gate_root=backup_gate_root.resolve(strict=False),
    )
    store.verify_ready()
    return store


__all__ = [
    "MINIMUM_REVISION",
    "RelationshipProjectionPersistenceError",
    "RelationshipProjectionStore",
    "create_postgres_relationship_projection_store",
]
