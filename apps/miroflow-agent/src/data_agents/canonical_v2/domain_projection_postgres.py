"""Guarded PostgreSQL adapter for immutable Canonical V2 domain projections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
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
from .contracts import (
    PolicyDecision,
    PolicyReference,
    TemporalDateValue,
    TemporalInstantValue,
)
from .domain_catalog import PACKAGED_CATALOG
from .domain_inclusion import Domain, DomainInclusionResult
from .domain_projection import (
    DomainProjectionManifestEntry,
    DomainProjectionResult,
    RejectedProjection,
)
from .domain_projection_models import (
    DOMAIN_SUBOBJECT_ATTRIBUTES,
    DOMAIN_SUBOBJECT_MODELS,
    CompanyProjection,
    FieldProjectionLineage,
    PaperProjection,
    PatentProjection,
    ProfessorProjection,
    TypedSubobject,
)
from .rebuild_write_gate import require_accepted_backup_gate


MINIMUM_REVISION = "C2_0009"
VERSION_TABLE = "public.canonical_v2_alembic_version"
DOMAINS: tuple[Domain, ...] = ("company", "paper", "patent", "professor")
ROOT_TABLES = {domain: (domain, "current_projection") for domain in DOMAINS}
SUBOBJECT_TABLES = {
    domain: {subobject_type: (domain, subobject_type) for subobject_type in subobjects}
    for domain, subobjects in DOMAIN_SUBOBJECT_MODELS.items()
}
MANIFEST_TABLE = ("knowledge", "domain_projection_manifest")
INCLUSION_DECISION_TABLE = ("knowledge", "domain_inclusion_decision")
INCLUSION_ASSERTION_TABLE = (
    "knowledge",
    "domain_inclusion_decision_assertion",
)
LINEAGE_TABLE = ("knowledge", "domain_projection_lineage")
PROJECTION_TABLES = tuple(
    sorted(
        (
            MANIFEST_TABLE,
            INCLUSION_DECISION_TABLE,
            INCLUSION_ASSERTION_TABLE,
            *ROOT_TABLES.values(),
            *(
                table
                for tables in SUBOBJECT_TABLES.values()
                for table in tables.values()
            ),
            LINEAGE_TABLE,
        )
    )
)
ROOT_MODELS = {
    "company": CompanyProjection,
    "paper": PaperProjection,
    "patent": PatentProjection,
    "professor": ProfessorProjection,
}
CATALOG_DOMAINS = {domain.domain: domain for domain in PACKAGED_CATALOG.domains}
SUBOBJECT_MEMBER_COLUMN_OVERRIDES: dict[tuple[str, str, str], str] = {
    ("paper", "full_text", "content_sha256"): "source_content_sha256",
}
_SUBOBJECT_BASE_FIELDS = frozenset(TypedSubobject.model_fields)


def _canonical_json(value: Any) -> JsonValue:
    if isinstance(value, BaseModel):
        return cast(JsonValue, value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return cast(JsonValue, value.value)
    if isinstance(value, Decimal):
        return cast(JsonValue, str(value))
    if isinstance(value, (date, datetime)):
        return cast(JsonValue, value.isoformat())
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


def _is_json_shape(shape: str) -> bool:
    if shape == "content_storage_reference":
        return False
    if shape in {
        "money",
        "field_override_map",
        "evidence_reference",
        "evidence_reference_list",
        "relationship_projection_list",
    }:
        return True
    return shape.endswith("_reference") or shape.endswith("_reference_list")


def _database_value(value: Any, *, shape: str) -> Any:
    if value is None:
        return None
    if _is_json_shape(shape):
        return Jsonb(_canonical_json(value))
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _projection_id(canonical_identity_id: str) -> str:
    return f"projection:{canonical_identity_id}"


def _display_name(projection: Any) -> str:
    for attribute in ("name", "title", "canonical_name_zh"):
        value = getattr(projection, attribute, None)
        if value:
            return cast(str, value)
    return cast(str, projection.canonical_identity_id)


def _subobject_counts(result: DomainProjectionResult) -> dict[str, int]:
    counts = {
        f"{domain}.{subobject_type}": 0
        for domain, subobjects in DOMAIN_SUBOBJECT_MODELS.items()
        for subobject_type in subobjects
    }
    for projection in result.projections:
        for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
            projection.entity_type
        ].items():
            counts[f"{projection.entity_type}.{subobject_type}"] += len(
                getattr(projection, attribute)
            )
    return dict(sorted(counts.items()))


def _projection_hashes(result: DomainProjectionResult) -> dict[str, str]:
    return {
        f"{projection.entity_type}:{projection.canonical_identity_id}": (
            projection.content_sha256
        )
        for projection in result.projections
    }


def _lineage_targets(
    projection: Any,
    lineage: FieldProjectionLineage,
) -> tuple[tuple[str | None, TypedSubobject | None], ...]:
    matches: list[tuple[str | None, TypedSubobject | None]] = []
    for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
        projection.entity_type
    ].items():
        for child in cast(tuple[TypedSubobject, ...], getattr(projection, attribute)):
            if lineage.decision_id in child.decision_ids and set(
                lineage.supporting_assertion_ids
            ) <= set(child.supporting_assertion_ids):
                matches.append((subobject_type, child))
    return tuple(matches) or ((None, None),)


class DomainProjectionPersistenceError(RuntimeError):
    """Durable domain-projection state is unavailable or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class DomainProjectionPersistenceReceipt:
    """Immutable summary of one first-write or idempotent replay."""

    release_id: str
    build_run_id: str
    manifest_content_sha256: str
    root_counts: Mapping[str, int]
    idempotent_replay: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "root_counts", MappingProxyType(dict(self.root_counts))
        )


class DomainProjectionStore(ABC):
    """Persist and reconstruct one immutable release-scoped projection result."""

    @abstractmethod
    def persist(
        self,
        result: DomainProjectionResult,
    ) -> DomainProjectionPersistenceReceipt:
        """Atomically persist a result or return an idempotent replay receipt."""

    @abstractmethod
    def load(self, release_id: str) -> DomainProjectionResult:
        """Load and validate the exact durable result for one release."""


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


class _PostgresDomainProjectionStore(DomainProjectionStore):
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
            raise DomainProjectionPersistenceError(
                "PostgreSQL domain-projection target identity cannot be read"
            )
        try:
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
        except DatabaseTargetSafetyError as exc:
            raise DomainProjectionPersistenceError(
                "PostgreSQL domain-projection target identity is invalid"
            ) from exc
        revisions = connection.execute(
            f"SELECT version_num FROM {VERSION_TABLE}"
        ).fetchall()
        if len(revisions) != 1:
            raise DomainProjectionPersistenceError(
                "domain-projection target requires exactly one Alembic revision row"
            )
        try:
            require_minimum_canonical_revision(
                scripts=load_canonical_v2_script_directory(),
                current_revision=revisions[0]["version_num"],
                minimum_revision=MINIMUM_REVISION,
            )
        except CanonicalRevisionError as exc:
            raise DomainProjectionPersistenceError(
                f"domain-projection target does not satisfy {MINIMUM_REVISION}"
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
            raise DomainProjectionPersistenceError(
                "PostgreSQL domain-projection target cannot be connected"
            ) from exc
        try:
            if not write:
                connection.execute("SET TRANSACTION READ ONLY")
            self._verify_connected_target(connection)
            yield connection
        except psycopg.Error as exc:
            connection.rollback()
            raise DomainProjectionPersistenceError(
                "domain-projection PostgreSQL transaction failed"
            ) from exc
        finally:
            connection.close()

    def verify_ready(self) -> None:
        with self._connection(write=False) as connection:
            connection.rollback()

    @staticmethod
    def _lock_write_boundary(
        connection: psycopg.Connection[dict[str, Any]],
    ) -> None:
        connection.execute("LOCK TABLE knowledge.release IN ROW SHARE MODE")
        connection.execute(
            sql.SQL("LOCK TABLE {} IN ROW EXCLUSIVE MODE").format(
                sql.SQL(", ").join(
                    sql.Identifier(*table) for table in PROJECTION_TABLES
                )
            )
        )

    @staticmethod
    def _validated_result(result: DomainProjectionResult) -> DomainProjectionResult:
        if not isinstance(result, DomainProjectionResult):
            raise DomainProjectionPersistenceError(
                "persist requires a typed DomainProjectionResult"
            )
        try:
            return DomainProjectionResult.model_validate(
                result.model_dump(mode="python")
            )
        except (AttributeError, ValueError, ValidationError) as exc:
            raise DomainProjectionPersistenceError(
                "domain projection result failed typed integrity validation"
            ) from exc

    @staticmethod
    def _insert_row(
        connection: psycopg.Connection[dict[str, Any]],
        table: tuple[str, str],
        values: Mapping[str, Any],
    ) -> None:
        columns = tuple(values)
        connection.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(*table),
                sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            ),
            tuple(values[column] for column in columns),
        )

    @staticmethod
    def _require_candidate_release(
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        release = connection.execute(
            "SELECT build_run_id, state FROM knowledge.release "
            "WHERE release_id = %s FOR SHARE",
            (result.release_id,),
        ).fetchone()
        if release is None or release["build_run_id"] != result.build_run_id:
            raise DomainProjectionPersistenceError(
                "domain projection requires its exact pre-existing release/build"
            )
        if release["state"] != "candidate":
            raise DomainProjectionPersistenceError(
                "domain projection persistence is restricted to a candidate release"
            )

    @staticmethod
    def _ensure_inclusion_policies(
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        policies = {
            (decision.policy.policy_id, decision.policy.policy_version): decision.policy
            for decision in result.inclusion_decisions
        }
        for policy in policies.values():
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
            durable = connection.execute(
                "SELECT policy_kind, content_sha256, effective_at "
                "FROM knowledge.policy WHERE policy_id = %s AND policy_version = %s",
                (policy.policy_id, policy.policy_version),
            ).fetchone()
            if durable is None or (
                durable["policy_kind"],
                durable["content_sha256"],
                durable["effective_at"],
            ) != (
                policy.policy_kind.value,
                policy.content_sha256,
                policy.effective_at,
            ):
                raise DomainProjectionPersistenceError(
                    "inclusion policy identity conflicts with durable policy content"
                )

    @classmethod
    def _insert_manifest(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        cls._insert_row(
            connection,
            MANIFEST_TABLE,
            {
                "release_id": result.release_id,
                "build_run_id": result.build_run_id,
                "projection_version": result.projection_version,
                "catalog_schema_version": result.catalog_schema_version,
                "catalog_version": result.catalog_version,
                "catalog_content_sha256": result.catalog_content_sha256,
                "inclusion_result_content_sha256": (
                    result.inclusion_result_content_sha256
                ),
                "approved_source_scope_manifest_sha256": (
                    result.approved_source_scope_manifest_sha256
                ),
                "inclusion_decision_run_id": result.inclusion_result.decision_run_id,
                "inclusion_evaluated_at": result.inclusion_result.evaluated_at,
                "manifest_content_sha256": result.content_sha256,
                "as_of": result.as_of,
                "root_counts": Jsonb(dict(result.counts_by_domain)),
                "subobject_counts": Jsonb(_subobject_counts(result)),
                "projection_hashes": Jsonb(_projection_hashes(result)),
                "rejected_projections": Jsonb(
                    [
                        item.model_dump(mode="json")
                        for item in result.rejected_projections
                    ]
                ),
                "created_at": result.as_of,
            },
        )

    @classmethod
    def _insert_inclusion_decisions(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        entity_by_identity = {
            projection.canonical_identity_id: projection.entity_type
            for projection in result.projections
        }
        entity_by_identity.update(
            {
                rejected.canonical_identity_id: rejected.entity_type
                for rejected in result.rejected_projections
            }
        )
        for decision in result.inclusion_decisions:
            cls._insert_row(
                connection,
                INCLUSION_DECISION_TABLE,
                {
                    "release_id": result.release_id,
                    "build_run_id": result.build_run_id,
                    "decision_id": decision.decision_id,
                    "canonical_identity_id": decision.subject_identity_id,
                    "entity_type": entity_by_identity[decision.subject_identity_id],
                    "policy_id": decision.policy.policy_id,
                    "policy_version": decision.policy.policy_version,
                    "policy_kind": decision.policy.policy_kind.value,
                    "outcome": decision.outcome.value,
                    "score": decision.score,
                    "limitations": list(decision.limitations),
                    "hard_exclusion_codes": list(decision.hard_exclusion_codes),
                    "evaluated_at": decision.evaluated_at,
                    "inclusion_decision_run_id": (
                        result.inclusion_result.decision_run_id
                    ),
                    "inclusion_result_content_sha256": (
                        result.inclusion_result_content_sha256
                    ),
                    "manifest_content_sha256": result.content_sha256,
                    "content_sha256": _canonical_sha256(decision),
                },
            )
            for assertion_id in decision.supporting_assertion_ids:
                cls._insert_row(
                    connection,
                    INCLUSION_ASSERTION_TABLE,
                    {
                        "release_id": result.release_id,
                        "decision_id": decision.decision_id,
                        "assertion_id": assertion_id,
                    },
                )

    @classmethod
    def _insert_roots(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        inclusion_by_identity = {
            decision.subject_identity_id: decision
            for decision in result.inclusion_decisions
        }
        for projection in result.projections:
            domain = projection.entity_type
            inclusion = inclusion_by_identity[projection.canonical_identity_id]
            attribute_to_subobject = {
                attribute: subobject_type
                for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
                    domain
                ].items()
            }
            values: dict[str, Any] = {
                "release_id": result.release_id,
                "build_run_id": result.build_run_id,
                "projection_id": _projection_id(projection.canonical_identity_id),
                "canonical_identity_id": projection.canonical_identity_id,
                "entity_type": domain,
                "identity_decision_id": projection.identity_decision_id,
                "display_name": _display_name(projection),
                "inclusion_decision_id": projection.inclusion_decision_id,
                "inclusion_outcome": inclusion.outcome.value,
                "as_of": projection.as_of,
                "quality_signals": [projection.quality_status],
                "projection_version": projection.projection_version,
                "catalog_schema_version": projection.catalog_schema_version,
                "catalog_version": projection.catalog_version,
                "catalog_content_sha256": projection.catalog_content_sha256,
                "manifest_content_sha256": result.content_sha256,
                "content_sha256": projection.content_sha256,
            }
            for field in CATALOG_DOMAINS[domain].fields:
                field_value = getattr(projection, field.field_path)
                if field.field_path in attribute_to_subobject:
                    field_value = [item.subobject_id for item in field_value]
                    values[field.field_path] = field_value
                else:
                    values[field.field_path] = _database_value(
                        field_value,
                        shape=field.value_shape,
                    )
            cls._insert_row(connection, ROOT_TABLES[domain], values)

    @staticmethod
    def _validity_columns(subobject: TypedSubobject) -> dict[str, str | None]:
        non_null = subobject.valid_from or subobject.valid_to
        if non_null is None:
            return {"valid_from": None, "valid_to": None, "validity_kind": None}

        def encoded_value(
            value: TemporalDateValue | TemporalInstantValue | None,
        ) -> str | None:
            if value is None:
                return None
            payload = value.model_dump(mode="json")
            return cast(str, payload["value"])

        return {
            "valid_from": encoded_value(subobject.valid_from),
            "valid_to": encoded_value(subobject.valid_to),
            "validity_kind": non_null.precision,
        }

    @classmethod
    def _insert_subobjects(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        for projection in result.projections:
            domain = projection.entity_type
            catalog_subobjects = {
                item.subobject_type: item for item in CATALOG_DOMAINS[domain].subobjects
            }
            for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
                domain
            ].items():
                member_shapes = {
                    member.member_name: member.value_shape
                    for member in catalog_subobjects[subobject_type].members
                }
                for ordinal, subobject in enumerate(getattr(projection, attribute)):
                    values: dict[str, Any] = {
                        "release_id": result.release_id,
                        "build_run_id": result.build_run_id,
                        "subobject_id": subobject.subobject_id,
                        "parent_projection_id": _projection_id(
                            projection.canonical_identity_id
                        ),
                        "canonical_identity_id": projection.canonical_identity_id,
                        "parent_canonical_identity_id": (
                            subobject.parent_canonical_identity_id
                        ),
                        "entity_type": domain,
                        "subobject_type": subobject_type,
                        "ordinal": ordinal,
                        "supporting_assertion_ids": list(
                            subobject.supporting_assertion_ids
                        ),
                        "decision_ids": list(subobject.decision_ids),
                        "observed_at": subobject.observed_at,
                        **cls._validity_columns(subobject),
                        "projection_version": projection.projection_version,
                        "catalog_schema_version": projection.catalog_schema_version,
                        "catalog_version": projection.catalog_version,
                        "catalog_content_sha256": projection.catalog_content_sha256,
                        "manifest_content_sha256": result.content_sha256,
                        "projection_content_sha256": (
                            subobject.projection_content_sha256
                        ),
                        "content_sha256": subobject.projection_content_sha256,
                    }
                    for member in (
                        set(type(subobject).model_fields) - _SUBOBJECT_BASE_FIELDS
                    ):
                        member = cast(str, member)
                        column = (
                            SUBOBJECT_MEMBER_COLUMN_OVERRIDES.get(
                                (domain, subobject_type, member)
                            )
                            or member
                        )
                        values[column] = _database_value(
                            getattr(subobject, member),
                            shape=member_shapes[member],
                        )
                    cls._insert_row(
                        connection,
                        SUBOBJECT_TABLES[domain][subobject_type],
                        values,
                    )

    @classmethod
    def _insert_lineage(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        assertion_ids = sorted(
            {
                assertion_id
                for projection in result.projections
                for lineage in projection.field_lineage
                for assertion_id in lineage.supporting_assertion_ids
            }
        )
        assertion_times = {
            row["assertion_id"]: row["observed_at"]
            for row in connection.execute(
                "SELECT assertion_id, observed_at FROM knowledge.source_assertion "
                "WHERE assertion_id = ANY(%s)",
                (assertion_ids,),
            ).fetchall()
        }
        if set(assertion_times) != set(assertion_ids):
            raise DomainProjectionPersistenceError(
                "projection lineage references missing source assertions"
            )
        for projection in result.projections:
            domain = projection.entity_type
            for lineage in projection.field_lineage:
                for target_type, child in _lineage_targets(projection, lineage):
                    for assertion_id in lineage.supporting_assertion_ids:
                        identity = {
                            "release_id": result.release_id,
                            "build_run_id": result.build_run_id,
                            "projection_id": _projection_id(
                                projection.canonical_identity_id
                            ),
                            "subobject_type": target_type,
                            "subobject_id": (
                                child.subobject_id if child is not None else None
                            ),
                            "canonical_identity_id": (projection.canonical_identity_id),
                            "entity_type": domain,
                            "field_path": lineage.field_path,
                            "decision_id": lineage.decision_id,
                            "assertion_id": assertion_id,
                            "assertion_role": "selected",
                            "observed_at": assertion_times[assertion_id],
                            "manifest_content_sha256": result.content_sha256,
                        }
                        identity["lineage_id"] = (
                            f"domain-lineage:sha256:{_canonical_sha256(identity)}"
                        )
                        identity["content_sha256"] = _canonical_sha256(identity)
                        cls._insert_row(connection, LINEAGE_TABLE, identity)

    @classmethod
    def _insert_projection_graph(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: DomainProjectionResult,
    ) -> None:
        cls._ensure_inclusion_policies(connection, result)
        cls._insert_manifest(connection, result)
        cls._insert_inclusion_decisions(connection, result)
        cls._insert_roots(connection, result)
        cls._insert_subobjects(connection, result)
        cls._insert_lineage(connection, result)

    @staticmethod
    def _receipt(
        result: DomainProjectionResult,
        *,
        idempotent_replay: bool,
    ) -> DomainProjectionPersistenceReceipt:
        return DomainProjectionPersistenceReceipt(
            release_id=result.release_id,
            build_run_id=result.build_run_id,
            manifest_content_sha256=result.content_sha256,
            root_counts=result.counts_by_domain,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _load_manifest(
        connection: psycopg.Connection[dict[str, Any]],
        release_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM knowledge.domain_projection_manifest WHERE release_id = %s",
            (release_id,),
        ).fetchone()
        if row is None:
            raise DomainProjectionPersistenceError(
                f"domain projection release is not persisted: {release_id}"
            )
        for column, expected_type in (
            ("root_counts", dict),
            ("subobject_counts", dict),
            ("projection_hashes", dict),
            ("rejected_projections", list),
        ):
            if not isinstance(row[column], expected_type):
                raise DomainProjectionPersistenceError(
                    f"durable projection manifest has invalid JSONB {column}"
                )
        return row

    @staticmethod
    def _load_inclusion_result(
        connection: psycopg.Connection[dict[str, Any]],
        manifest: Mapping[str, Any],
    ) -> tuple[
        DomainInclusionResult,
        tuple[PolicyDecision, ...],
        dict[str, Domain],
    ]:
        release_id = cast(str, manifest["release_id"])
        assertion_rows = connection.execute(
            "SELECT decision_id, assertion_id FROM "
            "knowledge.domain_inclusion_decision_assertion "
            "WHERE release_id = %s ORDER BY decision_id, assertion_id",
            (release_id,),
        ).fetchall()
        assertions_by_decision: dict[str, list[str]] = {}
        for row in assertion_rows:
            assertions_by_decision.setdefault(row["decision_id"], []).append(
                row["assertion_id"]
            )
        rows = connection.execute(
            "SELECT decision.*, policy.content_sha256 AS policy_content_sha256, "
            "policy.effective_at AS policy_effective_at "
            "FROM knowledge.domain_inclusion_decision AS decision "
            "JOIN knowledge.policy AS policy "
            "ON policy.policy_id = decision.policy_id "
            "AND policy.policy_version = decision.policy_version "
            "WHERE decision.release_id = %s "
            "ORDER BY decision.canonical_identity_id, decision.decision_id",
            (release_id,),
        ).fetchall()
        decisions: list[PolicyDecision] = []
        entity_by_identity: dict[str, Domain] = {}
        for row in rows:
            policy = PolicyReference(
                policy_id=row["policy_id"],
                policy_version=row["policy_version"],
                policy_kind=row["policy_kind"],
                content_sha256=row["policy_content_sha256"],
                effective_at=row["policy_effective_at"],
            )
            decision = PolicyDecision(
                decision_id=row["decision_id"],
                policy=policy,
                subject_identity_id=row["canonical_identity_id"],
                release_id=row["release_id"],
                outcome=row["outcome"],
                score=row["score"],
                limitations=tuple(row["limitations"]),
                hard_exclusion_codes=tuple(row["hard_exclusion_codes"]),
                supporting_assertion_ids=tuple(
                    assertions_by_decision.pop(row["decision_id"], [])
                ),
                evaluated_at=row["evaluated_at"],
            )
            if (
                row["build_run_id"] != manifest["build_run_id"]
                or row["inclusion_decision_run_id"]
                != manifest["inclusion_decision_run_id"]
                or row["manifest_content_sha256"] != manifest["manifest_content_sha256"]
                or row["inclusion_result_content_sha256"]
                != manifest["inclusion_result_content_sha256"]
                or row["content_sha256"] != _canonical_sha256(decision)
            ):
                raise DomainProjectionPersistenceError(
                    "durable inclusion decision envelope/hash is inconsistent"
                )
            if row["entity_type"] not in DOMAINS:
                raise DomainProjectionPersistenceError(
                    "durable inclusion decision has an invalid domain"
                )
            entity_type = cast(Domain, row["entity_type"])
            existing_entity = entity_by_identity.setdefault(
                decision.subject_identity_id, entity_type
            )
            if existing_entity != row["entity_type"]:
                raise DomainProjectionPersistenceError(
                    "durable inclusion decision identity has multiple domains"
                )
            decisions.append(decision)
        if assertions_by_decision:
            raise DomainProjectionPersistenceError(
                "durable inclusion assertion links have no decision"
            )
        decision_values = tuple(decisions)
        outcome_maps: dict[str, dict[Domain, tuple[str, ...]]] = {
            outcome: {domain: () for domain in DOMAINS}
            for outcome in ("admitted", "review", "excluded")
        }
        mutable_maps: dict[str, dict[Domain, list[str]]] = {
            outcome: {domain: [] for domain in DOMAINS} for outcome in outcome_maps
        }
        for decision in decision_values:
            if decision.outcome.value not in mutable_maps:
                raise DomainProjectionPersistenceError(
                    "durable inclusion result contains an unsupported outcome"
                )
            mutable_maps[decision.outcome.value][
                entity_by_identity[decision.subject_identity_id]
            ].append(decision.subject_identity_id)
        for outcome, domain_values in mutable_maps.items():
            outcome_maps[outcome] = {
                domain: tuple(sorted(identity_ids))
                for domain, identity_ids in domain_values.items()
            }
        try:
            inclusion_result = DomainInclusionResult(
                release_id=release_id,
                decision_run_id=manifest["inclusion_decision_run_id"],
                evaluated_at=manifest["inclusion_evaluated_at"],
                approved_source_scope_manifest_sha256=manifest[
                    "approved_source_scope_manifest_sha256"
                ],
                policy_decisions=decision_values,
                admitted_identity_ids_by_domain=outcome_maps["admitted"],
                review_identity_ids_by_domain=outcome_maps["review"],
                excluded_identity_ids_by_domain=outcome_maps["excluded"],
                content_sha256=manifest["inclusion_result_content_sha256"],
            )
        except (ValueError, ValidationError) as exc:
            raise DomainProjectionPersistenceError(
                "durable inclusion result failed typed/hash validation"
            ) from exc
        return inclusion_result, decision_values, entity_by_identity

    @staticmethod
    def _decode_validity(value: str | None, validity_kind: str | None) -> Any:
        if value is None:
            return None
        if validity_kind == "date":
            return TemporalDateValue(value=date.fromisoformat(value))
        if validity_kind == "instant":
            return TemporalInstantValue(value=datetime.fromisoformat(value))
        raise DomainProjectionPersistenceError(
            "typed sub-object validity has an invalid durable shape"
        )

    @classmethod
    def _load_subobjects(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        manifest: Mapping[str, Any],
    ) -> tuple[
        dict[tuple[str, str, str], tuple[TypedSubobject, ...]],
        dict[str, int],
    ]:
        grouped: dict[tuple[str, str, str], list[TypedSubobject]] = {}
        counts: dict[str, int] = {}
        seen_ids: set[tuple[str, str]] = set()
        for domain in DOMAINS:
            catalog_subobjects = {
                item.subobject_type: item for item in CATALOG_DOMAINS[domain].subobjects
            }
            for subobject_type, model in DOMAIN_SUBOBJECT_MODELS[domain].items():
                rows = connection.execute(
                    sql.SQL("SELECT * FROM {} WHERE release_id = %s ").format(
                        sql.Identifier(*SUBOBJECT_TABLES[domain][subobject_type])
                    )
                    + sql.SQL("ORDER BY parent_projection_id, ordinal, subobject_id"),
                    (manifest["release_id"],),
                ).fetchall()
                counts[f"{domain}.{subobject_type}"] = len(rows)
                member_shapes = {
                    member.member_name: member.value_shape
                    for member in catalog_subobjects[subobject_type].members
                }
                for row in rows:
                    durable_id = (domain, row["subobject_id"])
                    if durable_id in seen_ids:
                        raise DomainProjectionPersistenceError(
                            "durable typed sub-object ID is duplicated"
                        )
                    seen_ids.add(durable_id)
                    if (
                        row["build_run_id"] != manifest["build_run_id"]
                        or row["entity_type"] != domain
                        or row["subobject_type"] != subobject_type
                        or row["parent_canonical_identity_id"]
                        != row["canonical_identity_id"]
                        or row["projection_version"] != manifest["projection_version"]
                        or row["catalog_schema_version"]
                        != manifest["catalog_schema_version"]
                        or row["catalog_version"] != manifest["catalog_version"]
                        or row["catalog_content_sha256"]
                        != manifest["catalog_content_sha256"]
                        or row["manifest_content_sha256"]
                        != manifest["manifest_content_sha256"]
                        or row["content_sha256"] != row["projection_content_sha256"]
                    ):
                        raise DomainProjectionPersistenceError(
                            "durable typed sub-object envelope is inconsistent"
                        )
                    payload: dict[str, Any] = {
                        "subobject_id": row["subobject_id"],
                        "parent_canonical_identity_id": row[
                            "parent_canonical_identity_id"
                        ],
                        "supporting_assertion_ids": tuple(
                            row["supporting_assertion_ids"]
                        ),
                        "decision_ids": tuple(row["decision_ids"]),
                        "observed_at": row["observed_at"],
                        "valid_from": cls._decode_validity(
                            row["valid_from"], row["validity_kind"]
                        ),
                        "valid_to": cls._decode_validity(
                            row["valid_to"], row["validity_kind"]
                        ),
                        "projection_content_sha256": row["projection_content_sha256"],
                    }
                    for member in sorted(
                        set(model.model_fields) - _SUBOBJECT_BASE_FIELDS
                    ):
                        member = cast(str, member)
                        column = (
                            SUBOBJECT_MEMBER_COLUMN_OVERRIDES.get(
                                (domain, subobject_type, member)
                            )
                            or member
                        )
                        value = row[column]
                        if (
                            value is not None
                            and _is_json_shape(member_shapes[member])
                            and not isinstance(value, (dict, list))
                        ):
                            raise DomainProjectionPersistenceError(
                                "typed sub-object JSONB member did not decode natively"
                            )
                        payload[member] = value
                    try:
                        child = cast(
                            TypedSubobject,
                            model.model_validate(payload),
                        )
                    except (ValueError, ValidationError) as exc:
                        raise DomainProjectionPersistenceError(
                            "durable typed sub-object failed model/hash validation"
                        ) from exc
                    grouped.setdefault(
                        (domain, row["canonical_identity_id"], subobject_type), []
                    ).append(child)
        return (
            {key: tuple(values) for key, values in grouped.items()},
            dict(sorted(counts.items())),
        )

    @staticmethod
    def _load_lineage(
        connection: psycopg.Connection[dict[str, Any]],
        manifest: Mapping[str, Any],
    ) -> tuple[
        tuple[dict[str, Any], ...],
        dict[tuple[str, str], tuple[FieldProjectionLineage, ...]],
    ]:
        rows = connection.execute(
            "SELECT * FROM knowledge.domain_projection_lineage "
            "WHERE release_id = %s "
            "ORDER BY entity_type, canonical_identity_id, field_path, "
            "decision_id, subobject_id NULLS FIRST, assertion_id",
            (manifest["release_id"],),
        ).fetchall()
        grouped: dict[
            tuple[str, str, str, str],
            set[str],
        ] = {}
        content_columns = (
            "release_id",
            "build_run_id",
            "projection_id",
            "subobject_type",
            "subobject_id",
            "canonical_identity_id",
            "entity_type",
            "field_path",
            "decision_id",
            "assertion_id",
            "assertion_role",
            "observed_at",
            "manifest_content_sha256",
            "lineage_id",
        )
        for row in rows:
            if (
                row["build_run_id"] != manifest["build_run_id"]
                or row["manifest_content_sha256"] != manifest["manifest_content_sha256"]
                or row["assertion_role"] != "selected"
                or row["content_sha256"]
                != _canonical_sha256(
                    {column: row[column] for column in content_columns}
                )
            ):
                raise DomainProjectionPersistenceError(
                    "durable projection lineage envelope/hash is inconsistent"
                )
            grouped.setdefault(
                (
                    row["entity_type"],
                    row["canonical_identity_id"],
                    row["field_path"],
                    row["decision_id"],
                ),
                set(),
            ).add(row["assertion_id"])
        by_root: dict[tuple[str, str], list[FieldProjectionLineage]] = {}
        paths_by_root: dict[tuple[str, str], set[str]] = {}
        for (
            domain,
            canonical_identity_id,
            field_path,
            decision_id,
        ), assertion_ids in sorted(grouped.items()):
            root_key = (domain, canonical_identity_id)
            if field_path in paths_by_root.setdefault(root_key, set()):
                raise DomainProjectionPersistenceError(
                    "durable field lineage binds one path to multiple decisions"
                )
            paths_by_root[root_key].add(field_path)
            by_root.setdefault(root_key, []).append(
                FieldProjectionLineage(
                    field_path=field_path,
                    decision_id=decision_id,
                    supporting_assertion_ids=tuple(sorted(assertion_ids)),
                )
            )
        return tuple(rows), {key: tuple(values) for key, values in by_root.items()}

    @staticmethod
    def _verify_lineage_targets(
        projections: tuple[Any, ...],
        rows: tuple[dict[str, Any], ...],
    ) -> None:
        expected: set[tuple[Any, ...]] = set()
        for projection in projections:
            for lineage in projection.field_lineage:
                for subobject_type, child in _lineage_targets(projection, lineage):
                    for assertion_id in lineage.supporting_assertion_ids:
                        expected.add(
                            (
                                projection.entity_type,
                                projection.canonical_identity_id,
                                _projection_id(projection.canonical_identity_id),
                                subobject_type,
                                child.subobject_id if child is not None else None,
                                lineage.field_path,
                                lineage.decision_id,
                                assertion_id,
                            )
                        )
        durable = {
            (
                row["entity_type"],
                row["canonical_identity_id"],
                row["projection_id"],
                row["subobject_type"],
                row["subobject_id"],
                row["field_path"],
                row["decision_id"],
                row["assertion_id"],
            )
            for row in rows
        }
        if durable != expected or len(rows) != len(expected):
            raise DomainProjectionPersistenceError(
                "durable root/sub-object field lineage is incomplete or cross-wired"
            )

    @classmethod
    def _load_roots(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        manifest: Mapping[str, Any],
        inclusion_decisions: tuple[PolicyDecision, ...],
        subobjects: Mapping[tuple[str, str, str], tuple[TypedSubobject, ...]],
        lineage_by_root: Mapping[tuple[str, str], tuple[FieldProjectionLineage, ...]],
    ) -> tuple[Any, ...]:
        inclusion_by_identity = {
            decision.subject_identity_id: decision for decision in inclusion_decisions
        }
        projections: list[Any] = []
        consumed_children: set[tuple[str, str, str]] = set()
        consumed_lineage: set[tuple[str, str]] = set()
        for domain in DOMAINS:
            rows = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE release_id = %s ").format(
                    sql.Identifier(*ROOT_TABLES[domain])
                )
                + sql.SQL("ORDER BY canonical_identity_id"),
                (manifest["release_id"],),
            ).fetchall()
            attribute_to_subobject = {
                attribute: subobject_type
                for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
                    domain
                ].items()
            }
            for row in rows:
                root_key = (domain, row["canonical_identity_id"])
                inclusion = inclusion_by_identity.get(row["canonical_identity_id"])
                if (
                    inclusion is None
                    or row["build_run_id"] != manifest["build_run_id"]
                    or row["projection_id"]
                    != _projection_id(row["canonical_identity_id"])
                    or row["entity_type"] != domain
                    or row["inclusion_decision_id"] != inclusion.decision_id
                    or row["inclusion_outcome"] != inclusion.outcome.value
                    or row["as_of"] != manifest["as_of"]
                    or row["projection_version"] != manifest["projection_version"]
                    or row["catalog_schema_version"]
                    != manifest["catalog_schema_version"]
                    or row["catalog_version"] != manifest["catalog_version"]
                    or row["catalog_content_sha256"]
                    != manifest["catalog_content_sha256"]
                    or row["manifest_content_sha256"]
                    != manifest["manifest_content_sha256"]
                ):
                    raise DomainProjectionPersistenceError(
                        "durable domain root envelope is inconsistent"
                    )
                payload: dict[str, Any] = {
                    "release_id": row["release_id"],
                    "canonical_identity_id": row["canonical_identity_id"],
                    "identity_decision_id": row["identity_decision_id"],
                    "inclusion_decision_id": row["inclusion_decision_id"],
                    "projection_version": row["projection_version"],
                    "catalog_schema_version": row["catalog_schema_version"],
                    "catalog_version": row["catalog_version"],
                    "catalog_content_sha256": row["catalog_content_sha256"],
                    "as_of": row["as_of"],
                    "field_lineage": lineage_by_root.get(root_key, ()),
                    "content_sha256": row["content_sha256"],
                }
                consumed_lineage.add(root_key)
                for field in CATALOG_DOMAINS[domain].fields:
                    value = row[field.field_path]
                    subobject_type = attribute_to_subobject.get(field.field_path)
                    if subobject_type is not None:
                        child_key = (
                            domain,
                            row["canonical_identity_id"],
                            subobject_type,
                        )
                        children = subobjects.get(child_key, ())
                        if list(value) != [child.subobject_id for child in children]:
                            raise DomainProjectionPersistenceError(
                                "durable root typed-child IDs are incomplete or reordered"
                            )
                        payload[field.field_path] = children
                        if children:
                            consumed_children.add(child_key)
                    else:
                        if (
                            value is not None
                            and _is_json_shape(field.value_shape)
                            and not isinstance(value, (dict, list))
                        ):
                            raise DomainProjectionPersistenceError(
                                "domain root JSONB field did not decode natively"
                            )
                        payload[field.field_path] = value
                for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
                    domain
                ].items():
                    if attribute in payload:
                        continue
                    child_key = (
                        domain,
                        row["canonical_identity_id"],
                        subobject_type,
                    )
                    children = subobjects.get(child_key, ())
                    payload[attribute] = children
                    if children:
                        consumed_children.add(child_key)
                try:
                    projection = ROOT_MODELS[domain].model_validate(payload)
                except (ValueError, ValidationError) as exc:
                    raise DomainProjectionPersistenceError(
                        "durable domain root failed model/hash validation"
                    ) from exc
                if row["display_name"] != _display_name(projection) or list(
                    row["quality_signals"]
                ) != [projection.quality_status]:
                    raise DomainProjectionPersistenceError(
                        "durable domain root derived columns are inconsistent"
                    )
                projections.append(projection)
        populated_children = {key for key, values in subobjects.items() if values}
        if consumed_children != populated_children or consumed_lineage != set(
            lineage_by_root
        ):
            raise DomainProjectionPersistenceError(
                "durable domain root graph has orphan children or lineage"
            )
        return tuple(
            sorted(
                projections,
                key=lambda item: (item.entity_type, item.canonical_identity_id),
            )
        )

    @classmethod
    def _load_snapshot(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        release_id: str,
    ) -> DomainProjectionResult:
        manifest = cls._load_manifest(connection, release_id)
        inclusion_result, inclusion_decisions, entity_by_identity = (
            cls._load_inclusion_result(connection, manifest)
        )
        subobjects, subobject_counts = cls._load_subobjects(connection, manifest)
        lineage_rows, lineage_by_root = cls._load_lineage(connection, manifest)
        projections = cls._load_roots(
            connection,
            manifest,
            inclusion_decisions,
            subobjects,
            lineage_by_root,
        )
        cls._verify_lineage_targets(projections, lineage_rows)
        try:
            rejected = tuple(
                RejectedProjection.model_validate(item)
                for item in manifest["rejected_projections"]
            )
        except (ValueError, ValidationError) as exc:
            raise DomainProjectionPersistenceError(
                "durable rejected projection manifest is invalid"
            ) from exc
        expected_rejected = tuple(
            sorted(
                (
                    RejectedProjection(
                        canonical_identity_id=decision.subject_identity_id,
                        entity_type=entity_by_identity[decision.subject_identity_id],
                        reason_codes=(
                            f"inclusion_{decision.outcome.value}",
                            *decision.hard_exclusion_codes,
                        ),
                    )
                    for decision in inclusion_decisions
                    if decision.outcome.value != "admitted"
                ),
                key=lambda item: (
                    item.entity_type,
                    item.canonical_identity_id,
                ),
            )
        )
        if rejected != expected_rejected:
            raise DomainProjectionPersistenceError(
                "durable rejected projections conflict with inclusion decisions"
            )
        root_counts = {
            domain: sum(item.entity_type == domain for item in projections)
            for domain in DOMAINS
        }
        projection_hashes = {
            f"{item.entity_type}:{item.canonical_identity_id}": item.content_sha256
            for item in projections
        }
        if (
            manifest["root_counts"] != root_counts
            or manifest["subobject_counts"] != subobject_counts
            or manifest["projection_hashes"] != projection_hashes
        ):
            raise DomainProjectionPersistenceError(
                "durable projection manifest counts/hashes do not match typed rows"
            )
        projection_manifest = tuple(
            DomainProjectionManifestEntry(
                canonical_identity_id=item.canonical_identity_id,
                entity_type=item.entity_type,
                projection_content_sha256=item.content_sha256,
            )
            for item in projections
        )
        try:
            return DomainProjectionResult(
                release_id=manifest["release_id"],
                build_run_id=manifest["build_run_id"],
                as_of=manifest["as_of"],
                projection_version=manifest["projection_version"],
                catalog_schema_version=manifest["catalog_schema_version"],
                catalog_version=manifest["catalog_version"],
                catalog_content_sha256=manifest["catalog_content_sha256"],
                inclusion_result=inclusion_result,
                inclusion_result_content_sha256=manifest[
                    "inclusion_result_content_sha256"
                ],
                approved_source_scope_manifest_sha256=manifest[
                    "approved_source_scope_manifest_sha256"
                ],
                projections=projections,
                rejected_projections=rejected,
                inclusion_decisions=inclusion_decisions,
                manifest=projection_manifest,
                counts_by_domain=root_counts,
                content_sha256=manifest["manifest_content_sha256"],
            )
        except (ValueError, ValidationError) as exc:
            raise DomainProjectionPersistenceError(
                "durable domain projection failed complete result validation"
            ) from exc

    def persist(
        self,
        result: DomainProjectionResult,
    ) -> DomainProjectionPersistenceReceipt:
        validated = self._validated_result(result)
        with self._connection(write=True) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (validated.release_id,),
            )
            self._lock_write_boundary(connection)
            existing = connection.execute(
                "SELECT manifest_content_sha256 FROM "
                "knowledge.domain_projection_manifest WHERE release_id = %s FOR UPDATE",
                (validated.release_id,),
            ).fetchone()
            if existing is not None:
                if existing["manifest_content_sha256"] != validated.content_sha256:
                    raise DomainProjectionPersistenceError(
                        "immutable same-release projection content conflict"
                    )
                durable = self._load_snapshot(connection, validated.release_id)
                if durable != validated:
                    raise DomainProjectionPersistenceError(
                        "idempotent replay does not match exact durable content"
                    )
                connection.rollback()
                return self._receipt(validated, idempotent_replay=True)

            self._require_candidate_release(connection, validated)
            require_accepted_backup_gate(self._backup_gate_root)
            self._verify_connected_target(connection)
            self._insert_projection_graph(connection, validated)
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            durable = self._load_snapshot(connection, validated.release_id)
            if durable != validated:
                raise DomainProjectionPersistenceError(
                    "persisted projection failed exact durable round-trip validation"
                )
            connection.commit()
            return self._receipt(validated, idempotent_replay=False)

    def load(self, release_id: str) -> DomainProjectionResult:
        if not isinstance(release_id, str) or not release_id.strip():
            raise DomainProjectionPersistenceError(
                "load requires a non-empty release_id"
            )
        with self._connection(write=False) as connection:
            result = self._load_snapshot(connection, release_id)
            connection.rollback()
            return result


def create_postgres_domain_projection_store(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
) -> DomainProjectionStore:
    """Create an explicit, backup-gated adapter for a disposable target only."""
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
        raise DomainProjectionPersistenceError(
            "domain-projection target selection failed explicit safety checks"
        ) from exc
    if target.target_kind != "disposable":
        raise DomainProjectionPersistenceError(
            "domain-projection persistence is restricted to a disposable target"
        )
    store = _PostgresDomainProjectionStore(
        target=target,
        backup_gate_root=backup_gate_root.resolve(strict=False),
    )
    store.verify_ready()
    return store


__all__ = [
    "DomainProjectionPersistenceError",
    "DomainProjectionPersistenceReceipt",
    "DomainProjectionStore",
    "MINIMUM_REVISION",
    "create_postgres_domain_projection_store",
]
