"""Explicit-target PostgreSQL storage for immutable canonical decisions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import JsonValue, ValidationError
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import (
    DatabaseTargetSafetyError,
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

from . import canonical_decision_engine as _engine
from .canonical_revision import (
    CanonicalRevisionError,
    load_canonical_v2_script_directory,
    require_minimum_canonical_revision,
)
from .contracts import (
    CanonicalDecision,
    DecisionState,
    IdentityReference,
    IdentitySpace,
    PolicyReference,
    RelationshipAssertion,
    RelationshipDecision,
    RelationshipDecisionState,
    SourceAssertion,
    TemporalComparisonContext,
    TemporalInstantValue,
)
from .rebuild_write_gate import require_accepted_backup_gate


MINIMUM_REVISION = "C2_0008"
VERSION_TABLE = "public.canonical_v2_alembic_version"


class CanonicalDecisionPersistenceError(RuntimeError):
    """A durable canonical-decision operation failed closed."""


class CanonicalDecisionNotFoundError(CanonicalDecisionPersistenceError):
    """The requested immutable decision batch does not exist."""


class CanonicalDecisionStore(ABC):
    """Deep storage seam for complete immutable decision batches."""

    @abstractmethod
    def persist(
        self, result: _engine.DecisionBatchResult
    ) -> _engine.DecisionBatchResult:
        """Atomically retain a complete decision batch or replay it exactly."""
        raise NotImplementedError

    @abstractmethod
    def load(
        self,
        release_id: str,
        decision_run_id: str,
    ) -> _engine.DecisionBatchResult:
        """Reconstruct one complete batch from immutable durable history."""
        raise NotImplementedError

    @abstractmethod
    def load_history(
        self,
        release_id: str,
        *,
        as_of: datetime,
        temporal_comparison_context: TemporalComparisonContext | None = None,
    ) -> _engine.DecisionHistoryProjection:
        """Reconstruct one release ancestry and its unique current/history heads."""
        raise NotImplementedError


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


def _assertion_fingerprint(
    assertion: SourceAssertion | RelationshipAssertion,
) -> str:
    return _engine._content_sha256(cast(JsonValue, assertion.model_dump(mode="json")))


def _temporal_json(value: object | None) -> Jsonb | None:
    if value is None:
        return None
    return Jsonb(cast(Any, value).model_dump(mode="json"))


def _legacy_instant(value: object | None) -> datetime | None:
    return value.value if isinstance(value, TemporalInstantValue) else None


def _decision_identity_context_payload(
    result: _engine.DecisionBatchResult,
    decision: CanonicalDecision | RelationshipDecision,
) -> dict[str, JsonValue]:
    manifest = next(
        manifest
        for manifest in result.decision_group_manifests
        if manifest.decision_id == decision.decision_id
    )
    if isinstance(decision, CanonicalDecision):
        assertions_by_id = {
            assertion.assertion_id: assertion for assertion in result.field_assertions
        }
        canonical_identity_ids = {decision.canonical_identity_id}
        source_identity_ids = {
            assertions_by_id[assertion_id].source_identity_id
            for assertion_id in manifest.assertion_ids
        }
    else:
        relationship_assertions_by_id = {
            assertion.assertion_id: assertion
            for assertion in result.relationship_assertions
        }
        canonical_identity_ids = {
            decision.source_canonical_identity_id,
            decision.target_canonical_identity_id,
        }
        source_identity_ids = {
            source_identity_id
            for assertion_id in manifest.assertion_ids
            for source_identity_id in (
                relationship_assertions_by_id[assertion_id].source_endpoint.identity_id,
                relationship_assertions_by_id[assertion_id].target_endpoint.identity_id,
            )
        }
    return cast(
        dict[str, JsonValue],
        {
            "canonical_identity_contexts": [
                context.model_dump(mode="json")
                for context in result.canonical_identity_contexts
                if context.canonical_identity_id in canonical_identity_ids
            ],
            "source_identity_contexts": [
                context.model_dump(mode="json")
                for context in result.source_identity_contexts
                if context.source_identity_id in source_identity_ids
            ],
        },
    )


class _PostgresCanonicalDecisionStore(CanonicalDecisionStore):
    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        backup_gate_root: Path,
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._dsn = _psycopg_dsn(target.url)

    def verify_ready(self) -> None:
        with self._connection(write=False) as connection:
            connection.rollback()

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
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision target identity cannot be read"
            )
        try:
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
        except DatabaseTargetSafetyError as exc:
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision target identity is invalid"
            ) from exc

        revision_rows = connection.execute(
            f"SELECT version_num FROM {VERSION_TABLE}"
        ).fetchall()
        if len(revision_rows) != 1:
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision target requires exactly one "
                "Alembic revision row"
            )
        current_revision = revision_rows[0]["version_num"]
        try:
            require_minimum_canonical_revision(
                scripts=load_canonical_v2_script_directory(),
                current_revision=current_revision,
                minimum_revision=MINIMUM_REVISION,
            )
        except CanonicalRevisionError as exc:
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision target does not satisfy the "
                f"required minimum revision {MINIMUM_REVISION!r}"
            ) from exc

    @contextmanager
    def _connection(
        self,
        *,
        write: bool,
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        # The accepted evidence bytes are checked before every connection. In
        # particular, no later write may rely only on the factory-time receipt.
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
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision target cannot be connected"
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
            raise CanonicalDecisionPersistenceError(
                "PostgreSQL canonical-decision verification or transaction failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _validated_result(
        result: _engine.DecisionBatchResult,
    ) -> _engine.DecisionBatchResult:
        if not isinstance(result, _engine.DecisionBatchResult):
            raise CanonicalDecisionPersistenceError(
                "persist requires a validated DecisionBatchResult"
            )
        try:
            validated = _engine.DecisionBatchResult.model_validate(
                result.model_dump(mode="python")
            )
        except (UnicodeError, ValueError, ValidationError) as exc:
            raise CanonicalDecisionPersistenceError(
                "canonical-decision result failed typed integrity validation"
            ) from exc
        if not validated.canonical_decisions and not validated.relationship_decisions:
            raise CanonicalDecisionPersistenceError(
                "an empty decision batch has no durable identity in the approved schema"
            )
        return validated

    @staticmethod
    def _lock_release_boundary(
        connection: psycopg.Connection[dict[str, Any]],
    ) -> None:
        # C2 migrations acquire release before the reviewed decision tables.
        # Establish the same order before replay lookup so neither side can
        # hold one boundary while queueing a conflicting lock on the other.
        connection.execute("LOCK TABLE knowledge.release IN ROW SHARE MODE")

    @staticmethod
    def _batch_decision_count(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> int:
        row = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.canonical_decision "
            " WHERE release_id = %s AND decision_run_id = %s) + "
            "(SELECT count(*) FROM knowledge.relationship_decision "
            " WHERE release_id = %s AND decision_run_id = %s) AS decision_count",
            (release_id, decision_run_id, release_id, decision_run_id),
        ).fetchone()
        if row is None:
            raise CanonicalDecisionPersistenceError(
                "canonical-decision batch presence cannot be read"
            )
        return cast(int, row["decision_count"])

    @staticmethod
    def _require_exact_supersession_heads(
        connection: psycopg.Connection[dict[str, Any]],
        result: _engine.DecisionBatchResult,
    ) -> None:
        families = (
            (
                "canonical_decision",
                result.canonical_decisions,
                ("canonical_identity_id", "field_path"),
            ),
            (
                "relationship_decision",
                result.relationship_decisions,
                (
                    "canonical_relationship_id",
                    "relationship_type_id",
                    "relationship_type_version",
                    "source_canonical_identity_id",
                    "target_canonical_identity_id",
                ),
            ),
        )
        for table, decisions, subject_columns in families:
            for decision in decisions:
                predecessor_id = decision.supersedes_decision_id
                subject_predicate = " AND ".join(
                    f"predecessor.{column} = %s" for column in subject_columns
                )
                subject_values = tuple(
                    cast(str, getattr(decision, column)) for column in subject_columns
                )
                lineage_sql = (
                    "WITH RECURSIVE release_lineage AS ("
                    "SELECT release_id, previous_release_id FROM knowledge.release "
                    "WHERE release_id = %s UNION "
                    "SELECT parent.release_id, parent.previous_release_id "
                    "FROM knowledge.release AS parent JOIN release_lineage AS child "
                    "ON parent.release_id = child.previous_release_id) "
                )
                if predecessor_id is None:
                    existing = connection.execute(
                        cast(
                            LiteralString,
                            lineage_sql
                            + f"SELECT predecessor.decision_id FROM knowledge.{table} "
                            "AS predecessor JOIN release_lineage AS lineage "
                            "ON lineage.release_id = predecessor.release_id "
                            f"WHERE {subject_predicate} LIMIT 1",
                        ),
                        (result.release_id, *subject_values),
                    ).fetchone()
                    if existing is not None:
                        raise CanonicalDecisionPersistenceError(
                            "a later release cannot create a new root for an existing "
                            "decision lineage head"
                        )
                    continue
                row = connection.execute(
                    cast(
                        LiteralString,
                        lineage_sql
                        + f"SELECT predecessor.decision_id, EXISTS (SELECT 1 FROM knowledge.{table} "
                        "AS child WHERE child.supersedes_decision_id = "
                        "predecessor.decision_id) AS already_superseded "
                        f"FROM knowledge.{table} AS predecessor JOIN release_lineage AS lineage "
                        "ON lineage.release_id = predecessor.release_id "
                        "WHERE predecessor.decision_id = %s "
                        f"AND predecessor.release_id <> %s AND {subject_predicate}",
                    ),
                    (
                        result.release_id,
                        predecessor_id,
                        result.release_id,
                        *subject_values,
                    ),
                ).fetchone()
                if row is None or row["already_superseded"]:
                    raise CanonicalDecisionPersistenceError(
                        "decision supersession must target the exact unsuperseded head "
                        "in the target release ancestry"
                    )

    @staticmethod
    def _insert_field_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        assertions: tuple[SourceAssertion, ...],
    ) -> None:
        for assertion in assertions:
            connection.execute(
                "INSERT INTO knowledge.source_assertion "
                "(assertion_id, source_record_id, source_identity_id, "
                "subject_entity_type, field_path, value, "
                "assertion_fingerprint_sha256, observed_at, source_event_time, "
                "valid_from, valid_to, valid_from_temporal, valid_to_temporal, "
                "assertion_run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    assertion.assertion_id,
                    assertion.source_record_id,
                    assertion.source_identity_id,
                    assertion.subject_entity_type,
                    assertion.field_path,
                    Jsonb(assertion.value),
                    _assertion_fingerprint(assertion),
                    assertion.observed_at,
                    assertion.source_event_time,
                    _legacy_instant(assertion.valid_from),
                    _legacy_instant(assertion.valid_to),
                    _temporal_json(assertion.valid_from),
                    _temporal_json(assertion.valid_to),
                    assertion.assertion_run_id,
                ),
            )

    @staticmethod
    def _insert_relationship_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        assertions: tuple[RelationshipAssertion, ...],
    ) -> None:
        for assertion in assertions:
            connection.execute(
                "INSERT INTO knowledge.relationship_assertion "
                "(assertion_id, relationship_type_id, relationship_type_version, "
                "source_record_id, source_identity_id, target_identity_id, "
                "attributes, assertion_fingerprint_sha256, observed_at, "
                "source_event_time, valid_from, valid_to, valid_from_temporal, "
                "valid_to_temporal, assertion_run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    assertion.assertion_id,
                    assertion.relationship_type_id,
                    assertion.relationship_type_version,
                    assertion.source_record_id,
                    assertion.source_endpoint.identity_id,
                    assertion.target_endpoint.identity_id,
                    Jsonb(assertion.attributes),
                    _assertion_fingerprint(assertion),
                    assertion.observed_at,
                    assertion.source_event_time,
                    _legacy_instant(assertion.valid_from),
                    _legacy_instant(assertion.valid_to),
                    _temporal_json(assertion.valid_from),
                    _temporal_json(assertion.valid_to),
                    assertion.assertion_run_id,
                ),
            )

    @staticmethod
    def _trace_json(
        decision: CanonicalDecision | RelationshipDecision,
    ) -> Jsonb | None:
        if decision.llm_trace is None:
            return None
        return Jsonb(decision.llm_trace.model_dump(mode="json"))

    @staticmethod
    def _review_json(
        decision: CanonicalDecision | RelationshipDecision,
    ) -> Jsonb | None:
        if decision.human_review_resolution is None:
            return None
        return Jsonb(decision.human_review_resolution.model_dump(mode="json"))

    @classmethod
    def _insert_field_decisions(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        decisions: tuple[CanonicalDecision, ...],
    ) -> None:
        for decision in decisions:
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at, supersedes_decision_id, llm_trace, "
                "human_review_resolution) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s)",
                (
                    decision.release_id,
                    decision.decision_id,
                    decision.canonical_identity_id,
                    decision.field_path,
                    decision.state.value,
                    decision.policy.policy_id,
                    decision.policy.policy_version,
                    decision.method.value,
                    decision.method_version,
                    decision.decision_run_id,
                    decision.confidence,
                    decision.rationale,
                    decision.decided_at,
                    decision.supersedes_decision_id,
                    cls._trace_json(decision),
                    cls._review_json(decision),
                ),
            )

    @classmethod
    def _insert_relationship_decisions(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        decisions: tuple[RelationshipDecision, ...],
    ) -> None:
        for decision in decisions:
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, valid_from, valid_to, "
                "valid_from_temporal, valid_to_temporal, decided_at, "
                "supersedes_decision_id, llm_trace, "
                "human_review_resolution) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    decision.release_id,
                    decision.decision_id,
                    decision.canonical_relationship_id,
                    decision.relationship_type_id,
                    decision.relationship_type_version,
                    decision.source_canonical_identity_id,
                    decision.target_canonical_identity_id,
                    decision.state.value,
                    Jsonb(decision.role_bindings),
                    decision.policy.policy_id,
                    decision.policy.policy_version,
                    decision.method.value,
                    decision.method_version,
                    decision.decision_run_id,
                    decision.confidence,
                    decision.rationale,
                    _legacy_instant(decision.valid_from),
                    _legacy_instant(decision.valid_to),
                    _temporal_json(decision.valid_from),
                    _temporal_json(decision.valid_to),
                    decision.decided_at,
                    decision.supersedes_decision_id,
                    cls._trace_json(decision),
                    cls._review_json(decision),
                ),
            )

    @staticmethod
    def _insert_temporal_context(
        connection: psycopg.Connection[dict[str, Any]],
        result: _engine.DecisionBatchResult,
    ) -> None:
        context = result.temporal_comparison_context
        if context is None:
            return
        payload = cast(JsonValue, context.model_dump(mode="json"))
        connection.execute(
            "INSERT INTO knowledge.decision_batch_temporal_context "
            "(release_id, decision_run_id, comparison_context, content_sha256) "
            "VALUES (%s, %s, %s, %s)",
            (
                result.release_id,
                result.decision_run_id,
                Jsonb(payload),
                _engine._content_sha256(payload),
            ),
        )

    @staticmethod
    def _insert_roles(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        table: str,
        decision: CanonicalDecision | RelationshipDecision,
    ) -> None:
        role_ids = (
            ("candidate", decision.candidate_assertion_ids),
            ("selected", decision.selected_assertion_ids),
            ("conflicting", decision.conflicting_assertion_ids),
        )
        for role, assertion_ids in role_ids:
            for assertion_id in assertion_ids:
                connection.execute(
                    sql.SQL(
                        "INSERT INTO knowledge.{} "
                        "(release_id, decision_id, assertion_id, assertion_role) "
                        "VALUES (%s, %s, %s, %s)"
                    ).format(sql.Identifier(table)),
                    (
                        decision.release_id,
                        decision.decision_id,
                        assertion_id,
                        role,
                    ),
                )

    @staticmethod
    def _insert_outcomes(
        connection: psycopg.Connection[dict[str, Any]],
        result: _engine.DecisionBatchResult,
    ) -> None:
        field_assertion_ids = {
            assertion.assertion_id for assertion in result.field_assertions
        }
        for outcome in result.constraint_outcomes:
            table = (
                "canonical_decision_constraint_outcome"
                if outcome.assertion_id in field_assertion_ids
                else "relationship_decision_constraint_outcome"
            )
            connection.execute(
                f"INSERT INTO knowledge.{table} "
                "(release_id, decision_id, assertion_id, admitted, reason_codes) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    outcome.release_id,
                    outcome.decision_id,
                    outcome.assertion_id,
                    outcome.admitted,
                    Jsonb(list(outcome.reason_codes)),
                ),
            )

    @staticmethod
    def _insert_identity_context_snapshots(
        connection: psycopg.Connection[dict[str, Any]],
        result: _engine.DecisionBatchResult,
    ) -> None:
        for decision in (*result.canonical_decisions, *result.relationship_decisions):
            table = (
                "canonical_decision_identity_context"
                if isinstance(decision, CanonicalDecision)
                else "relationship_decision_identity_context"
            )
            payload = _decision_identity_context_payload(result, decision)
            connection.execute(
                f"INSERT INTO knowledge.{table} "
                "(release_id, decision_id, canonical_identity_contexts, "
                "source_identity_contexts, content_sha256) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    decision.release_id,
                    decision.decision_id,
                    Jsonb(payload["canonical_identity_contexts"]),
                    Jsonb(payload["source_identity_contexts"]),
                    _engine._content_sha256(cast(JsonValue, payload)),
                ),
            )

    def persist(
        self, result: _engine.DecisionBatchResult
    ) -> _engine.DecisionBatchResult:
        validated = self._validated_result(result)
        try:
            with self._connection(write=True) as connection:
                try:
                    lock_identity = _engine._content_sha256(
                        cast(
                            JsonValue,
                            [validated.release_id, validated.decision_run_id],
                        )
                    )
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (lock_identity,),
                    )
                    self._lock_release_boundary(connection)
                    if self._batch_decision_count(
                        connection,
                        release_id=validated.release_id,
                        decision_run_id=validated.decision_run_id,
                    ):
                        existing = self._load_result(
                            connection,
                            release_id=validated.release_id,
                            decision_run_id=validated.decision_run_id,
                        )
                        if existing != validated:
                            raise CanonicalDecisionPersistenceError(
                                "one release/decision_run_id cannot identify changed "
                                "decision content; replay conflict"
                            )
                        connection.rollback()
                        return existing

                    self._require_durable_identity_contexts(connection, validated)
                    self._require_exact_supersession_heads(connection, validated)
                    # Re-check the accepted evidence bytes and the connected target
                    # after every read/advisory prerequisite, immediately before the
                    # first durable mutation in this transaction.
                    require_accepted_backup_gate(self._backup_gate_root)
                    self._verify_connected_target(connection)
                    self._insert_field_assertions(
                        connection, validated.field_assertions
                    )
                    self._insert_relationship_assertions(
                        connection, validated.relationship_assertions
                    )
                    self._insert_field_decisions(
                        connection, validated.canonical_decisions
                    )
                    self._insert_relationship_decisions(
                        connection, validated.relationship_decisions
                    )
                    self._insert_temporal_context(connection, validated)
                    self._insert_identity_context_snapshots(connection, validated)
                    for decision in validated.canonical_decisions:
                        self._insert_roles(
                            connection,
                            table="canonical_decision_assertion",
                            decision=decision,
                        )
                    for decision in validated.relationship_decisions:
                        self._insert_roles(
                            connection,
                            table="relationship_decision_assertion",
                            decision=decision,
                        )
                    self._insert_outcomes(connection, validated)

                    durable = self._load_result(
                        connection,
                        release_id=validated.release_id,
                        decision_run_id=validated.decision_run_id,
                    )
                    if durable != validated:
                        raise CanonicalDecisionPersistenceError(
                            "durable decision content does not exactly match its "
                            "validated input"
                        )
                    connection.commit()
                    return durable
                except Exception:
                    connection.rollback()
                    raise
        except CanonicalDecisionPersistenceError:
            raise
        except (KeyError, TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise CanonicalDecisionPersistenceError(
                "canonical-decision batch could not be persisted exactly"
            ) from exc

    def load(
        self,
        release_id: str,
        decision_run_id: str,
    ) -> _engine.DecisionBatchResult:
        try:
            with self._connection(write=False) as connection:
                result = self._load_result(
                    connection,
                    release_id=release_id,
                    decision_run_id=decision_run_id,
                )
                connection.rollback()
                return result
        except (CanonicalDecisionNotFoundError, CanonicalDecisionPersistenceError):
            raise
        except (KeyError, TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise CanonicalDecisionPersistenceError(
                "durable canonical-decision batch is incomplete or corrupt"
            ) from exc

    @staticmethod
    def _release_lineage(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
    ) -> tuple[str, ...]:
        lineage: list[str] = []
        seen: set[str] = set()
        current_release_id: str | None = release_id
        while current_release_id is not None:
            if current_release_id in seen:
                raise CanonicalDecisionPersistenceError(
                    "durable release lineage contains a cycle"
                )
            row = connection.execute(
                "SELECT release_id, previous_release_id FROM knowledge.release "
                "WHERE release_id = %s",
                (current_release_id,),
            ).fetchone()
            if row is None:
                raise CanonicalDecisionPersistenceError(
                    "durable release lineage references a missing release"
                )
            seen.add(current_release_id)
            lineage.append(current_release_id)
            current_release_id = row["previous_release_id"]
        return tuple(reversed(lineage))

    @staticmethod
    def _release_decision_runs(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
    ) -> tuple[str, ...]:
        rows = connection.execute(
            "SELECT decision_run_id, min(decided_at) AS first_decided_at FROM ("
            "SELECT decision_run_id, decided_at FROM knowledge.canonical_decision "
            "WHERE release_id = %s UNION ALL "
            "SELECT decision_run_id, decided_at FROM knowledge.relationship_decision "
            "WHERE release_id = %s) AS decisions "
            "GROUP BY decision_run_id ORDER BY first_decided_at, decision_run_id",
            (release_id, release_id),
        ).fetchall()
        return tuple(row["decision_run_id"] for row in rows)

    def load_history(
        self,
        release_id: str,
        *,
        as_of: datetime,
        temporal_comparison_context: TemporalComparisonContext | None = None,
    ) -> _engine.DecisionHistoryProjection:
        try:
            with self._connection(write=False) as connection:
                lineage = self._release_lineage(
                    connection,
                    release_id=release_id,
                )
                batches = tuple(
                    self._load_result(
                        connection,
                        release_id=lineage_release_id,
                        decision_run_id=decision_run_id,
                    )
                    for lineage_release_id in lineage
                    for decision_run_id in self._release_decision_runs(
                        connection,
                        release_id=lineage_release_id,
                    )
                )
                if not batches:
                    raise CanonicalDecisionNotFoundError(
                        "canonical-decision release lineage has no decision batches"
                    )
                projection = _engine.project_decision_history(
                    batches,
                    as_of=as_of,
                    temporal_comparison_context=temporal_comparison_context,
                )
                if projection.release_lineage != tuple(
                    batch_release_id
                    for position, batch_release_id in enumerate(
                        batch.release_id for batch in batches
                    )
                    if position == 0
                    or batch_release_id != batches[position - 1].release_id
                ):
                    raise CanonicalDecisionPersistenceError(
                        "durable decision history release ordering is corrupt"
                    )
                connection.rollback()
                return projection
        except (
            CanonicalDecisionNotFoundError,
            CanonicalDecisionPersistenceError,
        ):
            raise
        except (
            KeyError,
            TypeError,
            UnicodeError,
            ValueError,
            ValidationError,
            _engine.DecisionHistoryIntegrityError,
        ) as exc:
            raise CanonicalDecisionPersistenceError(
                "durable canonical-decision history is incomplete or corrupt"
            ) from exc

    @staticmethod
    def _role_rows(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        table: str,
        decision_table: str,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            connection.execute(
                sql.SQL(
                    "SELECT link.decision_id, link.assertion_id, "
                    "link.assertion_role FROM knowledge.{} AS link "
                    "JOIN knowledge.{} AS decision "
                    "ON decision.release_id = link.release_id "
                    "AND decision.decision_id = link.decision_id "
                    "WHERE decision.release_id = %s "
                    "AND decision.decision_run_id = %s "
                    "ORDER BY link.decision_id, link.assertion_role, "
                    "link.assertion_id"
                ).format(sql.Identifier(table), sql.Identifier(decision_table)),
                (release_id, decision_run_id),
            ).fetchall()
        )

    @staticmethod
    def _roles_by_decision(
        rows: tuple[dict[str, Any], ...],
    ) -> dict[str, dict[str, tuple[str, ...]]]:
        mutable: dict[str, dict[str, list[str]]] = {}
        for row in rows:
            roles = mutable.setdefault(
                row["decision_id"],
                {"candidate": [], "selected": [], "conflicting": []},
            )
            role = row["assertion_role"]
            if role not in roles:
                raise ValueError("durable decision contains an unknown assertion role")
            roles[role].append(row["assertion_id"])
        return {
            decision_id: {
                role: tuple(sorted(assertion_ids))
                for role, assertion_ids in roles.items()
            }
            for decision_id, roles in mutable.items()
        }

    @staticmethod
    def _policy_from_row(row: Mapping[str, Any]) -> PolicyReference:
        return PolicyReference(
            policy_id=row["policy_id"],
            policy_version=row["policy_version"],
            policy_kind=row["policy_kind"],
            content_sha256=row["policy_content_sha256"],
            effective_at=row["policy_effective_at"],
        )

    @classmethod
    def _load_field_decisions(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[CanonicalDecision, ...]:
        rows = connection.execute(
            "SELECT decision.release_id, decision.decision_id, "
            "decision.canonical_identity_id, decision.field_path, decision.state, "
            "decision.policy_id, decision.policy_version, policy.policy_kind, "
            "policy.content_sha256 AS policy_content_sha256, "
            "policy.effective_at AS policy_effective_at, decision.method, "
            "decision.method_version, decision.decision_run_id, decision.confidence, "
            "decision.rationale, decision.decided_at, "
            "decision.supersedes_decision_id, decision.llm_trace, "
            "decision.human_review_resolution "
            "FROM knowledge.canonical_decision AS decision "
            "JOIN knowledge.policy AS policy ON policy.policy_id = decision.policy_id "
            "AND policy.policy_version = decision.policy_version "
            "WHERE decision.release_id = %s AND decision.decision_run_id = %s "
            "ORDER BY decision.canonical_identity_id, decision.field_path, "
            "decision.decision_id",
            (release_id, decision_run_id),
        ).fetchall()
        roles = cls._roles_by_decision(
            cls._role_rows(
                connection,
                table="canonical_decision_assertion",
                decision_table="canonical_decision",
                release_id=release_id,
                decision_run_id=decision_run_id,
            )
        )
        decisions = []
        for row in rows:
            decision_roles = roles.get(
                row["decision_id"],
                {"candidate": (), "selected": (), "conflicting": ()},
            )
            decisions.append(
                CanonicalDecision(
                    decision_id=row["decision_id"],
                    canonical_identity_id=row["canonical_identity_id"],
                    field_path=row["field_path"],
                    state=row["state"],
                    candidate_assertion_ids=decision_roles["candidate"],
                    selected_assertion_ids=decision_roles["selected"],
                    conflicting_assertion_ids=decision_roles["conflicting"],
                    policy=cls._policy_from_row(row),
                    method=row["method"],
                    method_version=row["method_version"],
                    decision_run_id=row["decision_run_id"],
                    confidence=row["confidence"],
                    rationale=row["rationale"],
                    llm_trace=row["llm_trace"],
                    release_id=row["release_id"],
                    decided_at=row["decided_at"],
                    supersedes_decision_id=row["supersedes_decision_id"],
                    human_review_resolution=row["human_review_resolution"],
                )
            )
        return tuple(
            sorted(
                decisions,
                key=lambda decision: (
                    decision.canonical_identity_id,
                    decision.field_path,
                    decision.decision_id,
                ),
            )
        )

    @classmethod
    def _load_relationship_decisions(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[RelationshipDecision, ...]:
        rows = connection.execute(
            "SELECT decision.release_id, decision.decision_id, "
            "decision.canonical_relationship_id, decision.relationship_type_id, "
            "decision.relationship_type_version, "
            "decision.source_canonical_identity_id, "
            "decision.target_canonical_identity_id, decision.state, "
            "decision.role_bindings, decision.policy_id, decision.policy_version, "
            "policy.policy_kind, policy.content_sha256 AS policy_content_sha256, "
            "policy.effective_at AS policy_effective_at, decision.method, "
            "decision.method_version, decision.decision_run_id, decision.confidence, "
            "decision.rationale, decision.valid_from, decision.valid_to, "
            "decision.valid_from_temporal, decision.valid_to_temporal, "
            "decision.decided_at, decision.supersedes_decision_id, decision.llm_trace, "
            "decision.human_review_resolution "
            "FROM knowledge.relationship_decision AS decision "
            "JOIN knowledge.policy AS policy ON policy.policy_id = decision.policy_id "
            "AND policy.policy_version = decision.policy_version "
            "WHERE decision.release_id = %s AND decision.decision_run_id = %s "
            "ORDER BY decision.canonical_relationship_id, decision.decision_id",
            (release_id, decision_run_id),
        ).fetchall()
        roles = cls._roles_by_decision(
            cls._role_rows(
                connection,
                table="relationship_decision_assertion",
                decision_table="relationship_decision",
                release_id=release_id,
                decision_run_id=decision_run_id,
            )
        )
        decisions = []
        for row in rows:
            decision_roles = roles.get(
                row["decision_id"],
                {"candidate": (), "selected": (), "conflicting": ()},
            )
            decisions.append(
                RelationshipDecision(
                    decision_id=row["decision_id"],
                    canonical_relationship_id=row["canonical_relationship_id"],
                    relationship_type_id=row["relationship_type_id"],
                    relationship_type_version=row["relationship_type_version"],
                    source_canonical_identity_id=row["source_canonical_identity_id"],
                    target_canonical_identity_id=row["target_canonical_identity_id"],
                    state=row["state"],
                    candidate_assertion_ids=decision_roles["candidate"],
                    selected_assertion_ids=decision_roles["selected"],
                    conflicting_assertion_ids=decision_roles["conflicting"],
                    role_bindings=row["role_bindings"],
                    policy=cls._policy_from_row(row),
                    method=row["method"],
                    method_version=row["method_version"],
                    decision_run_id=row["decision_run_id"],
                    confidence=row["confidence"],
                    rationale=row["rationale"],
                    valid_from=row["valid_from_temporal"],
                    valid_to=row["valid_to_temporal"],
                    release_id=row["release_id"],
                    decided_at=row["decided_at"],
                    supersedes_decision_id=row["supersedes_decision_id"],
                    llm_trace=row["llm_trace"],
                    human_review_resolution=row["human_review_resolution"],
                )
            )
        return tuple(
            sorted(
                decisions,
                key=lambda decision: (
                    decision.canonical_relationship_id,
                    decision.decision_id,
                ),
            )
        )

    @staticmethod
    def _load_outcome_rows(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            connection.execute(
                "SELECT 'field' AS family, outcome.release_id, "
                "outcome.decision_id, outcome.assertion_id, outcome.admitted, "
                "outcome.reason_codes "
                "FROM knowledge.canonical_decision_constraint_outcome AS outcome "
                "JOIN knowledge.canonical_decision AS decision "
                "ON decision.release_id = outcome.release_id "
                "AND decision.decision_id = outcome.decision_id "
                "WHERE decision.release_id = %s AND decision.decision_run_id = %s "
                "UNION ALL "
                "SELECT 'relationship' AS family, outcome.release_id, "
                "outcome.decision_id, outcome.assertion_id, outcome.admitted, "
                "outcome.reason_codes "
                "FROM knowledge.relationship_decision_constraint_outcome AS outcome "
                "JOIN knowledge.relationship_decision AS decision "
                "ON decision.release_id = outcome.release_id "
                "AND decision.decision_id = outcome.decision_id "
                "WHERE decision.release_id = %s AND decision.decision_run_id = %s "
                "ORDER BY family, assertion_id, decision_id",
                (release_id, decision_run_id, release_id, decision_run_id),
            ).fetchall()
        )

    @staticmethod
    def _load_field_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        assertion_ids: tuple[str, ...],
    ) -> tuple[SourceAssertion, ...]:
        if not assertion_ids:
            return ()
        rows = connection.execute(
            "SELECT assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, assertion_fingerprint_sha256, "
            "observed_at, source_event_time, valid_from_temporal, valid_to_temporal, "
            "assertion_run_id "
            "FROM knowledge.source_assertion WHERE assertion_id = ANY(%s) "
            "ORDER BY assertion_id",
            (list(assertion_ids),),
        ).fetchall()
        rows = sorted(rows, key=lambda row: row["assertion_id"])
        assertions = tuple(
            SourceAssertion(
                assertion_id=row["assertion_id"],
                source_record_id=row["source_record_id"],
                source_identity_id=row["source_identity_id"],
                subject_entity_type=row["subject_entity_type"],
                field_path=row["field_path"],
                value=row["value"],
                observed_at=row["observed_at"],
                source_event_time=row["source_event_time"],
                valid_from=row["valid_from_temporal"],
                valid_to=row["valid_to_temporal"],
                assertion_run_id=row["assertion_run_id"],
            )
            for row in rows
        )
        if tuple(assertion.assertion_id for assertion in assertions) != tuple(
            sorted(assertion_ids)
        ):
            raise ValueError("durable field assertion set is incomplete")
        for assertion, row in zip(assertions, rows, strict=True):
            if row["assertion_fingerprint_sha256"] != _assertion_fingerprint(assertion):
                raise ValueError("durable field assertion fingerprint is invalid")
        return assertions

    @staticmethod
    def _load_relationship_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        assertion_ids: tuple[str, ...],
    ) -> tuple[RelationshipAssertion, ...]:
        if not assertion_ids:
            return ()
        rows = connection.execute(
            "SELECT assertion.assertion_id, assertion.relationship_type_id, "
            "assertion.relationship_type_version, assertion.source_record_id, "
            "assertion.source_identity_id, source_identity.entity_type "
            "AS source_entity_type, assertion.target_identity_id, "
            "target_identity.entity_type AS target_entity_type, "
            "assertion.attributes, assertion.assertion_fingerprint_sha256, "
            "assertion.observed_at, assertion.source_event_time, "
            "assertion.valid_from_temporal, assertion.valid_to_temporal, "
            "assertion.assertion_run_id "
            "FROM knowledge.relationship_assertion AS assertion "
            "JOIN knowledge.source_identity AS source_identity "
            "ON source_identity.source_identity_id = assertion.source_identity_id "
            "JOIN knowledge.source_identity AS target_identity "
            "ON target_identity.source_identity_id = assertion.target_identity_id "
            "WHERE assertion.assertion_id = ANY(%s) ORDER BY assertion.assertion_id",
            (list(assertion_ids),),
        ).fetchall()
        rows = sorted(rows, key=lambda row: row["assertion_id"])
        assertions = tuple(
            RelationshipAssertion(
                assertion_id=row["assertion_id"],
                relationship_type_id=row["relationship_type_id"],
                relationship_type_version=row["relationship_type_version"],
                source_record_id=row["source_record_id"],
                source_endpoint=IdentityReference(
                    identity_id=row["source_identity_id"],
                    identity_space=IdentitySpace.source,
                    entity_type=row["source_entity_type"],
                ),
                target_endpoint=IdentityReference(
                    identity_id=row["target_identity_id"],
                    identity_space=IdentitySpace.source,
                    entity_type=row["target_entity_type"],
                ),
                attributes=row["attributes"],
                observed_at=row["observed_at"],
                source_event_time=row["source_event_time"],
                valid_from=row["valid_from_temporal"],
                valid_to=row["valid_to_temporal"],
                assertion_run_id=row["assertion_run_id"],
            )
            for row in rows
        )
        observed_ids = tuple(assertion.assertion_id for assertion in assertions)
        expected_ids = tuple(sorted(assertion_ids))
        if observed_ids != expected_ids:
            duplicate_requested_ids = sorted(
                {
                    assertion_id
                    for assertion_id in expected_ids
                    if expected_ids.count(assertion_id) > 1
                }
            )
            raise ValueError(
                "durable relationship assertion set is incomplete: "
                f"requested={len(expected_ids)}, observed={len(observed_ids)}, "
                f"missing={sorted(set(expected_ids) - set(observed_ids))}, "
                f"extra={sorted(set(observed_ids) - set(expected_ids))}, "
                f"duplicate_requested={duplicate_requested_ids}"
            )
        for assertion, row in zip(assertions, rows, strict=True):
            if row["assertion_fingerprint_sha256"] != _assertion_fingerprint(assertion):
                raise ValueError(
                    "durable relationship assertion fingerprint is invalid"
                )
        return assertions

    @staticmethod
    def _load_canonical_identity_contexts(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        canonical_identity_ids: tuple[str, ...],
    ) -> tuple[_engine.CanonicalIdentityConstraintContext, ...]:
        if not canonical_identity_ids:
            return ()
        has_explicit_membership = connection.execute(
            "SELECT to_regclass('knowledge.canonical_identity_source_membership') "
            "IS NOT NULL AS available"
        ).fetchone()
        if has_explicit_membership is not None and has_explicit_membership["available"]:
            rows = connection.execute(
                "SELECT identity.canonical_identity_id, identity.entity_type, "
                "identity.state, membership.source_identity_id "
                "FROM knowledge.canonical_identity AS identity "
                "JOIN knowledge.canonical_identity_source_membership AS membership "
                "ON membership.release_id = identity.release_id "
                "AND membership.canonical_identity_id = "
                "identity.canonical_identity_id "
                "WHERE identity.release_id = %s "
                "AND identity.canonical_identity_id = ANY(%s) "
                "ORDER BY identity.canonical_identity_id, "
                "membership.source_identity_id",
                (release_id, list(canonical_identity_ids)),
            ).fetchall()
        else:
            ambiguous_legacy_decisions = connection.execute(
                "SELECT identity.identity_decision_id "
                "FROM knowledge.canonical_identity AS identity "
                "LEFT JOIN knowledge.identity_decision_output AS decision_output "
                "ON decision_output.release_id = identity.release_id "
                "AND decision_output.decision_id = identity.identity_decision_id "
                "WHERE identity.release_id = %s "
                "AND identity.canonical_identity_id = ANY(%s) "
                "GROUP BY identity.identity_decision_id "
                "HAVING count(DISTINCT decision_output.canonical_identity_id) <> 1",
                (release_id, list(canonical_identity_ids)),
            ).fetchall()
            if ambiguous_legacy_decisions:
                raise ValueError(
                    "legacy decision-wide identity membership requires exactly "
                    "one output per producing decision"
                )
            rows = connection.execute(
                "SELECT identity.canonical_identity_id, identity.entity_type, "
                "identity.state, membership.source_identity_id "
                "FROM knowledge.canonical_identity AS identity "
                "JOIN knowledge.identity_decision_output AS decision_output "
                "ON decision_output.release_id = identity.release_id "
                "AND decision_output.decision_id = identity.identity_decision_id "
                "AND decision_output.canonical_identity_id = "
                "identity.canonical_identity_id "
                "JOIN knowledge.identity_decision_source_identity AS membership "
                "ON membership.release_id = identity.release_id "
                "AND membership.decision_id = identity.identity_decision_id "
                "WHERE identity.release_id = %s "
                "AND identity.canonical_identity_id = ANY(%s) "
                "ORDER BY identity.canonical_identity_id, "
                "membership.source_identity_id",
                (release_id, list(canonical_identity_ids)),
            ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            context = grouped.setdefault(
                row["canonical_identity_id"],
                {
                    "canonical_identity_id": row["canonical_identity_id"],
                    "entity_type": row["entity_type"],
                    "state": row["state"],
                    "source_identity_ids": [],
                },
            )
            context["source_identity_ids"].append(row["source_identity_id"])
        if set(grouped) != set(canonical_identity_ids):
            raise ValueError(
                "durable canonical identity context or authoritative membership "
                "is incomplete"
            )
        return tuple(
            _engine.CanonicalIdentityConstraintContext.model_validate(context)
            for context in grouped.values()
        )

    @staticmethod
    def _load_source_identity_contexts(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        source_identity_ids: tuple[str, ...],
    ) -> tuple[_engine.SourceIdentity, ...]:
        if not source_identity_ids:
            return ()
        rows = connection.execute(
            "SELECT identity.source_identity_id, identity.source_system, "
            "identity.source_key, identity.entity_type, identity.normalized_keys, "
            "identity.first_observed_at, identity.last_observed_at, identity.state, "
            "record.record_id FROM knowledge.source_identity AS identity "
            "JOIN knowledge.source_identity_record AS record "
            "ON record.source_identity_id = identity.source_identity_id "
            "WHERE identity.source_identity_id = ANY(%s) "
            "ORDER BY identity.source_identity_id, record.record_id",
            (list(source_identity_ids),),
        ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            context = grouped.setdefault(
                row["source_identity_id"],
                {
                    "source_identity_id": row["source_identity_id"],
                    "source_system": row["source_system"],
                    "source_key": row["source_key"],
                    "entity_type": row["entity_type"],
                    "source_record_ids": [],
                    "normalized_keys": row["normalized_keys"],
                    "first_observed_at": row["first_observed_at"],
                    "last_observed_at": row["last_observed_at"],
                    "state": row["state"],
                },
            )
            context["source_record_ids"].append(row["record_id"])
        if set(grouped) != set(source_identity_ids):
            raise ValueError(
                "durable source identity context or source-record membership is "
                "incomplete"
            )
        return tuple(
            _engine.SourceIdentity.model_validate(context)
            for context in grouped.values()
        )

    @classmethod
    def _current_identity_contexts(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        field_assertions: tuple[SourceAssertion, ...],
        relationship_assertions: tuple[RelationshipAssertion, ...],
        field_decisions: tuple[CanonicalDecision, ...],
        relationship_decisions: tuple[RelationshipDecision, ...],
    ) -> tuple[
        tuple[_engine.CanonicalIdentityConstraintContext, ...],
        tuple[_engine.SourceIdentity, ...],
    ]:
        canonical_identity_ids = tuple(
            sorted(
                {decision.canonical_identity_id for decision in field_decisions}
                | {
                    canonical_identity_id
                    for decision in relationship_decisions
                    for canonical_identity_id in (
                        decision.source_canonical_identity_id,
                        decision.target_canonical_identity_id,
                    )
                }
            )
        )
        source_identity_ids = tuple(
            sorted(
                {assertion.source_identity_id for assertion in field_assertions}
                | {
                    source_identity_id
                    for assertion in relationship_assertions
                    for source_identity_id in (
                        assertion.source_endpoint.identity_id,
                        assertion.target_endpoint.identity_id,
                    )
                }
            )
        )
        # The loaded contexts are re-sorted in Python with the same keys the
        # decision engine's result normalization uses: the database en_US.utf8
        # collation does not order text the way Python's codepoint sort does
        # (released "COMP-..." vs backfilled "company-backfill:..." source ids
        # interleave differently), so the durable-context comparison must be
        # collation-independent.
        return (
            tuple(
                sorted(
                    cls._load_canonical_identity_contexts(
                        connection,
                        release_id=release_id,
                        canonical_identity_ids=canonical_identity_ids,
                    ),
                    key=lambda context: context.canonical_identity_id,
                )
            ),
            tuple(
                sorted(
                    cls._load_source_identity_contexts(
                        connection,
                        source_identity_ids=source_identity_ids,
                    ),
                    key=lambda context: context.source_identity_id,
                )
            ),
        )

    @staticmethod
    def _identity_context_snapshot_rows(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        table: str,
        decision_table: str,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            connection.execute(
                sql.SQL(
                    "SELECT snapshot.decision_id, "
                    "snapshot.canonical_identity_contexts, "
                    "snapshot.source_identity_contexts, snapshot.content_sha256 "
                    "FROM knowledge.{} AS snapshot "
                    "JOIN knowledge.{} AS decision "
                    "ON decision.release_id = snapshot.release_id "
                    "AND decision.decision_id = snapshot.decision_id "
                    "WHERE decision.release_id = %s "
                    "AND decision.decision_run_id = %s "
                    "ORDER BY snapshot.decision_id"
                ).format(sql.Identifier(table), sql.Identifier(decision_table)),
                (release_id, decision_run_id),
            ).fetchall()
        )

    @classmethod
    def _snapshot_identity_contexts(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
        field_decisions: tuple[CanonicalDecision, ...],
        relationship_decisions: tuple[RelationshipDecision, ...],
    ) -> tuple[
        tuple[_engine.CanonicalIdentityConstraintContext, ...],
        tuple[_engine.SourceIdentity, ...],
    ]:
        family_rows = (
            (
                field_decisions,
                cls._identity_context_snapshot_rows(
                    connection,
                    table="canonical_decision_identity_context",
                    decision_table="canonical_decision",
                    release_id=release_id,
                    decision_run_id=decision_run_id,
                ),
            ),
            (
                relationship_decisions,
                cls._identity_context_snapshot_rows(
                    connection,
                    table="relationship_decision_identity_context",
                    decision_table="relationship_decision",
                    release_id=release_id,
                    decision_run_id=decision_run_id,
                ),
            ),
        )
        canonical_by_id: dict[str, _engine.CanonicalIdentityConstraintContext] = {}
        source_by_id: dict[str, _engine.SourceIdentity] = {}
        for decisions, rows in family_rows:
            if {row["decision_id"] for row in rows} != {
                decision.decision_id for decision in decisions
            }:
                raise ValueError(
                    "every durable decision requires exactly one identity-context "
                    "snapshot"
                )
            for row in rows:
                payload = cast(
                    JsonValue,
                    {
                        "canonical_identity_contexts": row[
                            "canonical_identity_contexts"
                        ],
                        "source_identity_contexts": row["source_identity_contexts"],
                    },
                )
                if row["content_sha256"] != _engine._content_sha256(payload):
                    raise ValueError(
                        "durable identity-context snapshot hash is invalid"
                    )
                for raw_context in row["canonical_identity_contexts"]:
                    context = _engine.CanonicalIdentityConstraintContext.model_validate(
                        raw_context
                    )
                    prior = canonical_by_id.setdefault(
                        context.canonical_identity_id, context
                    )
                    if prior != context:
                        raise ValueError(
                            "durable canonical identity snapshots disagree"
                        )
                for raw_context in row["source_identity_contexts"]:
                    context = _engine.SourceIdentity.model_validate(raw_context)
                    prior = source_by_id.setdefault(context.source_identity_id, context)
                    if prior != context:
                        raise ValueError("durable source identity snapshots disagree")
        return (
            tuple(
                sorted(
                    canonical_by_id.values(),
                    key=lambda context: context.canonical_identity_id,
                )
            ),
            tuple(
                sorted(
                    source_by_id.values(),
                    key=lambda context: context.source_identity_id,
                )
            ),
        )

    @classmethod
    def _require_durable_identity_contexts(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        result: _engine.DecisionBatchResult,
    ) -> None:
        try:
            canonical_contexts, source_contexts = cls._current_identity_contexts(
                connection,
                release_id=result.release_id,
                field_assertions=result.field_assertions,
                relationship_assertions=result.relationship_assertions,
                field_decisions=result.canonical_decisions,
                relationship_decisions=result.relationship_decisions,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise CanonicalDecisionPersistenceError(
                "durable identity ownership or constraint context is incomplete"
            ) from exc
        if (
            canonical_contexts != result.canonical_identity_contexts
            or source_contexts != result.source_identity_contexts
        ):
            raise CanonicalDecisionPersistenceError(
                "durable identity ownership and constraint context must exactly "
                "match the decision result"
            )

    @staticmethod
    def _decision_manifests(
        *,
        field_assertions: tuple[SourceAssertion, ...],
        relationship_assertions: tuple[RelationshipAssertion, ...],
        field_decisions: tuple[CanonicalDecision, ...],
        relationship_decisions: tuple[RelationshipDecision, ...],
        outcome_rows: tuple[dict[str, Any], ...],
    ) -> tuple[_engine.DecisionGroupManifest, ...]:
        field_by_id = {
            assertion.assertion_id: assertion for assertion in field_assertions
        }
        relationship_by_id = {
            assertion.assertion_id: assertion for assertion in relationship_assertions
        }
        assertion_ids_by_decision: dict[str, list[str]] = {}
        for row in outcome_rows:
            assertion_ids_by_decision.setdefault(row["decision_id"], []).append(
                row["assertion_id"]
            )
        manifests = []
        for decision in (*field_decisions, *relationship_decisions):
            assertion_ids = tuple(
                sorted(assertion_ids_by_decision.get(decision.decision_id, ()))
            )
            if isinstance(decision, CanonicalDecision):
                assertions: tuple[SourceAssertion | RelationshipAssertion, ...] = tuple(
                    field_by_id[assertion_id] for assertion_id in assertion_ids
                )
            else:
                assertions = tuple(
                    relationship_by_id[assertion_id] for assertion_id in assertion_ids
                )
            group_key = _engine._decision_group_key(decision)
            manifests.append(
                _engine.DecisionGroupManifest(
                    decision_id=decision.decision_id,
                    group_key=group_key,
                    assertion_ids=assertion_ids,
                    content_sha256=_engine._decision_group_manifest_content_sha256(
                        group_key=group_key,
                        assertions=assertions,
                    ),
                )
            )
        return tuple(sorted(manifests, key=lambda manifest: manifest.decision_id))

    @staticmethod
    def _derive_projections(
        *,
        release_id: str,
        as_of: datetime,
        temporal_comparison_context: TemporalComparisonContext | None,
        field_assertions: tuple[SourceAssertion, ...],
        field_decisions: tuple[CanonicalDecision, ...],
        relationship_decisions: tuple[RelationshipDecision, ...],
    ) -> tuple[
        tuple[_engine.CurrentFieldSelection, ...],
        tuple[_engine.CurrentRelationshipSelection, ...],
        tuple[_engine.UnresolvedConflict, ...],
    ]:
        fields_by_id = {
            assertion.assertion_id: assertion for assertion in field_assertions
        }
        field_validity_by_decision = {
            decision.decision_id: _engine._selected_validity(
                field_assertions,
                decision.selected_assertion_ids,
            )
            for decision in field_decisions
            if decision.state is DecisionState.selected
        }
        current_fields = tuple(
            sorted(
                (
                    _engine.CurrentFieldSelection(
                        release_id=release_id,
                        canonical_identity_id=decision.canonical_identity_id,
                        field_path=decision.field_path,
                        value=fields_by_id[decision.selected_assertion_ids[0]].value,
                        decision_id=decision.decision_id,
                        supporting_assertion_ids=decision.selected_assertion_ids,
                        conflicting_assertion_ids=decision.conflicting_assertion_ids,
                        valid_from=field_validity_by_decision[decision.decision_id][0],
                        valid_to=field_validity_by_decision[decision.decision_id][1],
                    )
                    for decision in field_decisions
                    if decision.state is DecisionState.selected
                    and _engine._interval_contains(
                        as_of=as_of,
                        valid_from=field_validity_by_decision[decision.decision_id][0],
                        valid_to=field_validity_by_decision[decision.decision_id][1],
                        context=temporal_comparison_context,
                    )
                ),
                key=lambda current: (
                    current.canonical_identity_id,
                    current.field_path,
                    current.decision_id,
                ),
            )
        )
        current_relationships = tuple(
            sorted(
                (
                    _engine.CurrentRelationshipSelection(
                        release_id=release_id,
                        canonical_relationship_id=decision.canonical_relationship_id,
                        relationship_type_id=decision.relationship_type_id,
                        relationship_type_version=decision.relationship_type_version,
                        source_canonical_identity_id=(
                            decision.source_canonical_identity_id
                        ),
                        target_canonical_identity_id=(
                            decision.target_canonical_identity_id
                        ),
                        role_bindings=decision.role_bindings,
                        decision_id=decision.decision_id,
                        supporting_assertion_ids=decision.selected_assertion_ids,
                        conflicting_assertion_ids=decision.conflicting_assertion_ids,
                        valid_from=decision.valid_from,
                        valid_to=decision.valid_to,
                    )
                    for decision in relationship_decisions
                    if decision.state is RelationshipDecisionState.accepted
                    and _engine._interval_contains(
                        as_of=as_of,
                        valid_from=decision.valid_from,
                        valid_to=decision.valid_to,
                        context=temporal_comparison_context,
                    )
                ),
                key=lambda current: (
                    current.canonical_relationship_id,
                    current.decision_id,
                ),
            )
        )
        conflicts = tuple(
            sorted(
                (
                    *(
                        _engine.UnresolvedConflict(
                            release_id=release_id,
                            decision_id=decision.decision_id,
                            subject_id=decision.canonical_identity_id,
                            path=decision.field_path,
                            assertion_ids=decision.conflicting_assertion_ids,
                        )
                        for decision in field_decisions
                        if decision.state is DecisionState.unresolved
                    ),
                    *(
                        _engine.UnresolvedConflict(
                            release_id=release_id,
                            decision_id=decision.decision_id,
                            subject_id=decision.canonical_relationship_id,
                            path=decision.relationship_type_id,
                            assertion_ids=decision.conflicting_assertion_ids,
                        )
                        for decision in relationship_decisions
                        if decision.state is RelationshipDecisionState.unresolved
                    ),
                ),
                key=lambda conflict: (
                    conflict.subject_id,
                    conflict.path,
                    conflict.decision_id,
                ),
            )
        )
        return current_fields, current_relationships, conflicts

    @staticmethod
    def _load_temporal_context(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> TemporalComparisonContext | None:
        row = connection.execute(
            "SELECT comparison_context, content_sha256 FROM "
            "knowledge.decision_batch_temporal_context "
            "WHERE release_id = %s AND decision_run_id = %s",
            (release_id, decision_run_id),
        ).fetchone()
        if row is None:
            return None
        payload = cast(JsonValue, row["comparison_context"])
        if row["content_sha256"] != _engine._content_sha256(payload):
            raise ValueError("durable temporal comparison context hash is invalid")
        return TemporalComparisonContext.model_validate(payload)

    @classmethod
    def _load_result(
        cls,
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> _engine.DecisionBatchResult:
        field_decisions = cls._load_field_decisions(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
        )
        relationship_decisions = cls._load_relationship_decisions(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
        )
        if not field_decisions and not relationship_decisions:
            raise CanonicalDecisionNotFoundError(
                "canonical-decision batch was not found"
            )

        outcome_rows = cls._load_outcome_rows(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
        )
        field_assertion_ids = tuple(
            sorted(
                row["assertion_id"] for row in outcome_rows if row["family"] == "field"
            )
        )
        relationship_assertion_ids = tuple(
            sorted(
                row["assertion_id"]
                for row in outcome_rows
                if row["family"] == "relationship"
            )
        )
        field_assertions = cls._load_field_assertions(connection, field_assertion_ids)
        relationship_assertions = cls._load_relationship_assertions(
            connection, relationship_assertion_ids
        )
        manifests = cls._decision_manifests(
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            outcome_rows=outcome_rows,
        )
        manifests_by_decision = {
            manifest.decision_id: manifest for manifest in manifests
        }
        decisions_by_id: dict[str, CanonicalDecision | RelationshipDecision] = {
            decision.decision_id: decision
            for decision in (*field_decisions, *relationship_decisions)
        }
        outcomes = tuple(
            sorted(
                (
                    _engine.ConstraintOutcome(
                        release_id=row["release_id"],
                        decision_id=row["decision_id"],
                        assertion_id=row["assertion_id"],
                        group_key=manifests_by_decision[row["decision_id"]].group_key,
                        admitted=row["admitted"],
                        reason_codes=tuple(row["reason_codes"]),
                        policy_version=decisions_by_id[
                            row["decision_id"]
                        ].policy.policy_version,
                    )
                    for row in outcome_rows
                ),
                key=lambda outcome: (outcome.assertion_id, outcome.decision_id),
            )
        )
        all_decisions = (*field_decisions, *relationship_decisions)
        as_of = all_decisions[0].decided_at
        temporal_comparison_context = cls._load_temporal_context(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
        )
        current_fields, current_relationships, conflicts = cls._derive_projections(
            release_id=release_id,
            as_of=as_of,
            temporal_comparison_context=temporal_comparison_context,
            field_assertions=field_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
        )
        canonical_contexts, source_contexts = cls._snapshot_identity_contexts(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
        )
        content = _engine._DecisionBatchContent(
            release_id=release_id,
            decision_run_id=decision_run_id,
            as_of=as_of,
            temporal_comparison_context=temporal_comparison_context,
            canonical_identity_contexts=canonical_contexts,
            source_identity_contexts=source_contexts,
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            canonical_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            decision_group_manifests=manifests,
            constraint_outcomes=outcomes,
            current_fields=current_fields,
            current_relationships=current_relationships,
            unresolved_conflicts=conflicts,
            review_cases=_engine._review_cases_for_decisions(
                field_decisions=field_decisions,
                relationship_decisions=relationship_decisions,
                manifests=manifests,
            ),
        )
        payload = cast(JsonValue, content.model_dump(mode="json"))
        return _engine.DecisionBatchResult(
            **content.model_dump(mode="python"),
            content_sha256=_engine._content_sha256(payload),
        )


def create_postgres_canonical_decision_store(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
) -> CanonicalDecisionStore:
    """Create an explicit, gate-checked store for disposable PostgreSQL only."""
    require_accepted_backup_gate(backup_gate_root)
    accepted_root = backup_gate_root.resolve(strict=False)
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
        raise CanonicalDecisionPersistenceError(
            "canonical-decision target selection failed explicit safety checks"
        ) from exc
    if target.target_kind != "disposable":
        raise CanonicalDecisionPersistenceError(
            "canonical-decision persistence is restricted to a disposable target"
        )
    store = _PostgresCanonicalDecisionStore(
        target=target,
        backup_gate_root=accepted_root,
    )
    store.verify_ready()
    return store


__all__ = [
    "CanonicalDecisionNotFoundError",
    "CanonicalDecisionPersistenceError",
    "CanonicalDecisionStore",
    "create_postgres_canonical_decision_store",
]
