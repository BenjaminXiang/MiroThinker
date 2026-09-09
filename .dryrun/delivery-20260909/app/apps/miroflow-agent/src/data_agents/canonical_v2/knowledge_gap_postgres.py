"""Explicit-target PostgreSQL operations for durable Canonical V2 gaps."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, JsonValue, ValidationError
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import (
    DestructiveDatabaseTarget,
    DatabaseTargetSafetyError,
    resolve_destructive_database_target,
)

from .canonical_revision import (
    CanonicalRevisionError,
    load_canonical_v2_script_directory,
    require_minimum_canonical_revision,
)
from .contracts import (
    ContractModel,
    GapClass,
    GapSeverity,
    GapStatus,
    KnowledgeGap,
)
from .knowledge_gap_feedback import (
    GapClassifier,
    GapRemediationRequest,
    GapRemediationResult,
    GapSignal,
    KnowledgeGapFeedback,
    create_ephemeral_knowledge_gap_feedback,
)
from .rebuild_write_gate import RebuildWriteGateError, require_accepted_backup_gate


MINIMUM_REVISION = "C2_0011"
VERSION_TABLE = "public.canonical_v2_alembic_version"


class KnowledgeGapConfigurationError(RuntimeError):
    """The dedicated V2 operations target is absent, ambiguous, or unsafe."""


class KnowledgeGapPersistenceError(RuntimeError):
    """A sanitized durable operations failure."""


class KnowledgeGapIntegrityError(KnowledgeGapPersistenceError):
    """Durable payload identity or lifecycle lineage is inconsistent."""


class GapAdminQuery(ContractModel):
    statuses: tuple[GapStatus, ...] = ()
    gap_classes: tuple[GapClass, ...] = ()
    severities: tuple[GapSeverity, ...] = ()
    domain: str | None = None
    path: str | None = None
    release_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GapAdminPage(ContractModel):
    items: tuple[KnowledgeGap, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class GapAdminDetail(ContractModel):
    gap: KnowledgeGap
    transitions: tuple[GapRemediationResult, ...]
    field_assertions: tuple[dict[str, JsonValue], ...]
    relationship_assertions: tuple[dict[str, JsonValue], ...]
    canonical_decisions: tuple[dict[str, JsonValue], ...]
    relationship_decisions: tuple[dict[str, JsonValue], ...]
    releases: tuple[dict[str, JsonValue], ...]
    provenance: tuple[dict[str, JsonValue], ...]
    unresolved_evidence_ids: tuple[str, ...]


class _ExplicitTargetConfig:
    def __init__(self, *, database_url: str, expected_database: str, target_kind: str):
        self._options = {
            "sqlalchemy.url": database_url,
            "miroflow.expected_database": expected_database,
            "miroflow.target_kind": target_kind,
        }

    def get_main_option(self, name: str, default: str | None = None) -> str | None:
        return self._options.get(name, default)


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


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


def _model_hash(value: ContractModel) -> str:
    return _canonical_sha256(value.model_dump(mode="json"))


def _enum_values(values: tuple[Any, ...]) -> list[str]:
    return [value.value if hasattr(value, "value") else str(value) for value in values]


class PostgresKnowledgeGapOperations(KnowledgeGapFeedback):
    """Append-only durable composition around the accepted pure lifecycle."""

    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        backup_gate_root: Path,
        classifier: GapClassifier | None,
        clock: Callable[[], datetime],
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._classifier = classifier
        self._clock = clock
        self._dsn = _psycopg_dsn(target.url)

    @contextmanager
    def _connection(
        self, *, write: bool
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        try:
            require_accepted_backup_gate(self._backup_gate_root)
        except RebuildWriteGateError as exc:
            raise KnowledgeGapConfigurationError(
                "Canonical V2 operations backup gate is not accepted"
            ) from exc
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
            raise KnowledgeGapPersistenceError(
                "Canonical V2 operations database is unavailable"
            ) from exc
        try:
            identity = connection.execute(
                "SELECT current_database() AS database_name, "
                "shobj_description(oid, 'pg_database') AS database_marker "
                "FROM pg_database WHERE datname=current_database()"
            ).fetchone()
            if identity is None:
                raise KnowledgeGapConfigurationError(
                    "Canonical V2 operations target identity is unavailable"
                )
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
            revisions = connection.execute(
                f"SELECT version_num FROM {VERSION_TABLE}"
            ).fetchall()
            if len(revisions) != 1:
                raise KnowledgeGapConfigurationError(
                    "Canonical V2 operations target has no single live revision"
                )
            require_minimum_canonical_revision(
                scripts=load_canonical_v2_script_directory(),
                current_revision=revisions[0]["version_num"],
                minimum_revision=MINIMUM_REVISION,
            )
            connection.rollback()
            yield connection
        except (DatabaseTargetSafetyError, CanonicalRevisionError) as exc:
            connection.rollback()
            raise KnowledgeGapConfigurationError(
                "Canonical V2 operations target failed identity or revision validation"
            ) from exc
        except psycopg.Error as exc:
            connection.rollback()
            raise KnowledgeGapPersistenceError(
                "Canonical V2 operations transaction failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _load_gap(payload: Any, content_sha256: str | None = None) -> KnowledgeGap:
        try:
            gap = KnowledgeGap.model_validate(payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise KnowledgeGapIntegrityError(
                "Stored knowledge-gap payload is invalid"
            ) from exc
        if content_sha256 is not None and _model_hash(gap) != content_sha256:
            raise KnowledgeGapIntegrityError(
                "Stored knowledge-gap content identity does not match"
            )
        return gap

    @classmethod
    def _load_gap_row(cls, row: dict[str, Any]) -> KnowledgeGap:
        gap = cls._load_gap(row["gap_payload"], row["content_sha256"])
        stored = (
            row["gap_id"],
            row["release_id"],
            row["gap_class"],
            row["status"],
            row["review_state"],
            row["severity"],
            tuple(row["affected_domains"]),
            tuple(row["affected_paths"]),
            row["demand_count"],
            row["created_at"],
            row["updated_at"],
        )
        expected = (
            gap.gap_id,
            gap.release_id,
            gap.gap_class.value,
            gap.status.value,
            gap.review_state.value,
            gap.severity.value,
            gap.affected_domains,
            gap.affected_paths,
            gap.demand_count,
            gap.created_at,
            gap.updated_at,
        )
        if stored != expected:
            raise KnowledgeGapIntegrityError(
                "Stored knowledge-gap searchable columns do not match its typed payload"
            )
        return gap

    @staticmethod
    def _load_transition(row: dict[str, Any]) -> GapRemediationResult:
        try:
            request = GapRemediationRequest.model_validate(row["request_payload"])
            result = GapRemediationResult.model_validate(row["result_payload"])
        except (TypeError, ValueError, ValidationError) as exc:
            raise KnowledgeGapIntegrityError(
                "Stored remediation transition payload is invalid"
            ) from exc
        if (
            request.content_sha256 != row["remediation_input_sha256"]
            or result.remediation_input_sha256 != request.content_sha256
            or result.content_sha256 != row["result_content_sha256"]
            or result.transition_id != row["transition_id"]
            or result.transition_state != row["transition_state"]
            or result.gap.gap_id != row["gap_id"]
            or request.gap.gap_id != row["gap_id"]
            or request.gap.release_id != row["source_release_id"]
            or request.candidate_release.release_id != row["candidate_release_id"]
            or result.remediation_receipt.source_release_id != row["source_release_id"]
            or result.remediation_receipt.candidate_release_id
            != row["candidate_release_id"]
            or result.gap.updated_at != row["transitioned_at"]
        ):
            raise KnowledgeGapIntegrityError(
                "Stored remediation transition identity does not match"
            )
        return result

    @staticmethod
    def _base_row(connection: Any, gap_id: str, *, lock: bool) -> Any:
        return connection.execute(
            "SELECT gap_id, release_id, gap_class, status, review_state, severity, "
            "affected_domains, affected_paths, demand_count, created_at, updated_at, "
            "gap_payload, content_sha256 FROM ops.knowledge_gap "
            "WHERE gap_id=%s" + (" FOR UPDATE" if lock else ""),
            (gap_id,),
        ).fetchone()

    @classmethod
    def _current_gap(cls, connection: Any, gap_id: str, *, lock: bool) -> KnowledgeGap:
        base = cls._base_row(connection, gap_id, lock=lock)
        if base is None:
            raise KnowledgeGapIntegrityError("Knowledge gap is not durably recorded")
        gap = cls._load_gap_row(base)
        latest = connection.execute(
            "SELECT transition_id, gap_id, source_release_id, candidate_release_id, "
            "transition_state, transitioned_at, "
            "remediation_input_sha256, result_content_sha256, request_payload, "
            "result_payload FROM ops.gap_remediation_transition WHERE gap_id=%s "
            "ORDER BY transitioned_at DESC, transition_id DESC LIMIT 1"
            + (" FOR UPDATE" if lock else ""),
            (gap_id,),
        ).fetchone()
        return gap if latest is None else cls._load_transition(latest).gap

    def record(self, signal: GapSignal) -> KnowledgeGap:
        try:
            validated_signal = GapSignal.model_validate(signal.model_dump(mode="json"))
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ValueError("gap signal must be a validated GapSignal") from exc
        gap = create_ephemeral_knowledge_gap_feedback(
            classifier=self._classifier, clock=self._clock
        ).record(validated_signal)
        content_sha256 = _model_hash(gap)
        with self._connection(write=True) as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (gap.gap_id,),
                )
                existing = self._base_row(connection, gap.gap_id, lock=True)
                if existing is not None:
                    durable = self._load_gap_row(existing)
                    durable_identity = durable.model_dump(
                        mode="json", exclude={"created_at", "updated_at"}
                    )
                    replay_identity = gap.model_dump(
                        mode="json", exclude={"created_at", "updated_at"}
                    )
                    if durable_identity != replay_identity:
                        raise KnowledgeGapIntegrityError(
                            "One gap identity cannot identify different content"
                        )
                    return durable
                connection.execute(
                    "INSERT INTO ops.knowledge_gap "
                    "(gap_id, release_id, gap_class, status, review_state, severity, "
                    "affected_domains, affected_paths, demand_count, created_at, "
                    "updated_at, gap_payload, content_sha256) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        gap.gap_id,
                        gap.release_id,
                        gap.gap_class.value,
                        gap.status.value,
                        gap.review_state.value,
                        gap.severity.value,
                        list(gap.affected_domains),
                        list(gap.affected_paths),
                        gap.demand_count,
                        gap.created_at,
                        gap.updated_at,
                        Jsonb(gap.model_dump(mode="json")),
                        content_sha256,
                    ),
                )
        return gap

    @staticmethod
    def _verify_candidate(connection: Any, request: GapRemediationRequest) -> None:
        row = connection.execute(
            "SELECT release.release_id, release.build_run_id, release.state, "
            "release.manifest_sha256, manifest.manifest_version, "
            "manifest.source_batch_ids, manifest.source_batches_sha256, "
            "manifest.parser_versions, manifest.policy_versions, "
            "manifest.model_versions, manifest.build_run_id AS manifest_build_run_id, "
            "manifest.manifest_sha256 AS manifest_identity "
            "FROM knowledge.release AS release "
            "JOIN publish.build_manifest AS manifest USING (release_id) "
            "WHERE release.release_id=%s",
            (request.candidate_release.release_id,),
        ).fetchone()
        candidate = request.candidate_release
        canonical_source_hash = _canonical_sha256(
            {"source_batch_ids": list(candidate.source_batch_ids)}
        )
        expected = (
            candidate.release_id,
            candidate.run_id,
            candidate.state.value,
            candidate.manifest_sha256,
            "canonical-v2-build-manifest-v2",
            list(candidate.source_batch_ids),
            canonical_source_hash,
            candidate.parser_versions,
            candidate.policy_versions,
            candidate.model_versions,
            candidate.run_id,
            candidate.manifest_sha256,
        )
        actual = None if row is None else tuple(row.values())
        if actual != expected:
            raise KnowledgeGapIntegrityError(
                "Remediation candidate does not match durable release and manifest truth"
            )
        sections = connection.execute(
            "SELECT section_id, section_kind, record_count "
            "FROM publish.manifest_section WHERE release_id=%s ORDER BY section_id",
            (candidate.release_id,),
        ).fetchall()
        object_counts = {
            row["section_id"].removeprefix("objects:"): row["record_count"]
            for row in sections
            if row["section_kind"] == "object_set"
            and row["section_id"].startswith("objects:")
        }
        relationship_counts = [
            row["record_count"]
            for row in sections
            if row["section_kind"] == "relationship_set"
            and row["section_id"] == "relationships"
        ]
        if object_counts != dict(candidate.object_counts) or relationship_counts != [
            candidate.relationship_count
        ]:
            raise KnowledgeGapIntegrityError(
                "Remediation candidate counts do not match durable manifest sections"
            )

    def apply_remediation(self, request: GapRemediationRequest) -> GapRemediationResult:
        try:
            validated = GapRemediationRequest.model_validate(
                request.model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ValueError("remediation must be a validated request") from exc
        with self._connection(write=True) as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (validated.gap.gap_id,),
                )
                replay = connection.execute(
                    "SELECT transition_id, gap_id, source_release_id, "
                    "candidate_release_id, transition_state, transitioned_at, "
                    "remediation_input_sha256, result_content_sha256, "
                    "request_payload, result_payload "
                    "FROM ops.gap_remediation_transition "
                    "WHERE gap_id=%s AND remediation_input_sha256=%s FOR UPDATE",
                    (validated.gap.gap_id, validated.content_sha256),
                ).fetchone()
                if replay is not None:
                    result = self._load_transition(replay)
                    stored_request = GapRemediationRequest.model_validate(
                        replay["request_payload"]
                    )
                    if stored_request != validated:
                        raise KnowledgeGapIntegrityError(
                            "One remediation input identity cannot identify different content"
                        )
                    return result
                current = self._current_gap(connection, validated.gap.gap_id, lock=True)
                if current != validated.gap:
                    raise KnowledgeGapIntegrityError(
                        "Remediation request is stale or branches durable current state"
                    )
                self._verify_candidate(connection, validated)
                result = create_ephemeral_knowledge_gap_feedback(
                    clock=self._clock
                ).apply_remediation(validated)
                connection.execute(
                    "INSERT INTO ops.gap_remediation_transition "
                    "(transition_id, gap_id, source_release_id, candidate_release_id, "
                    "transition_state, remediation_input_sha256, result_content_sha256, "
                    "request_payload, result_payload, transitioned_at) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        result.transition_id,
                        result.gap.gap_id,
                        validated.gap.release_id,
                        validated.candidate_release.release_id,
                        result.transition_state,
                        validated.content_sha256,
                        result.content_sha256,
                        Jsonb(validated.model_dump(mode="json")),
                        Jsonb(result.model_dump(mode="json")),
                        result.gap.updated_at,
                    ),
                )
                return result

    @classmethod
    def _current_from_row(cls, row: dict[str, Any]) -> KnowledgeGap:
        base = cls._load_gap_row(
            {
                "gap_id": row["gap_id"],
                "release_id": row["base_release_id"],
                "gap_class": row["base_gap_class"],
                "status": row["base_status"],
                "review_state": row["base_review_state"],
                "severity": row["base_severity"],
                "affected_domains": row["base_affected_domains"],
                "affected_paths": row["base_affected_paths"],
                "demand_count": row["base_demand_count"],
                "created_at": row["base_created_at"],
                "updated_at": row["base_updated_at"],
                "gap_payload": row["base_payload"],
                "content_sha256": row["base_content_sha256"],
            }
        )
        if row["transition_id"] is None:
            return base
        return cls._load_transition(row).gap

    def list_for_admin(self, query: GapAdminQuery) -> GapAdminPage:
        validated = GapAdminQuery.model_validate(query.model_dump(mode="json"))
        predicates: list[str] = []
        parameters: list[Any] = []
        if validated.statuses:
            predicates.append("current.gap_payload ->> 'status' = ANY(%s)")
            parameters.append(_enum_values(validated.statuses))
        if validated.gap_classes:
            predicates.append("current.gap_payload ->> 'gap_class' = ANY(%s)")
            parameters.append(_enum_values(validated.gap_classes))
        if validated.severities:
            predicates.append("current.gap_payload ->> 'severity' = ANY(%s)")
            parameters.append(_enum_values(validated.severities))
        if validated.domain is not None:
            predicates.append("(current.gap_payload -> 'affected_domains') ? %s")
            parameters.append(validated.domain)
        if validated.path is not None:
            predicates.append("(current.gap_payload -> 'affected_paths') ? %s")
            parameters.append(validated.path)
        if validated.release_id is not None:
            predicates.append(
                "(current.source_release_id=%s OR current.candidate_release_id=%s OR "
                "EXISTS (SELECT 1 FROM ops.gap_remediation_transition AS linked "
                "WHERE linked.gap_id=current.gap_id AND linked.candidate_release_id=%s))"
            )
            parameters.extend([validated.release_id] * 3)
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        base_query = (
            " FROM ops.current_knowledge_gap AS current "
            "JOIN ops.knowledge_gap AS base USING (gap_id) "
            "LEFT JOIN ops.gap_remediation_transition AS latest "
            "ON latest.transition_id=current.transition_id" + where
        )
        select = (
            "SELECT current.gap_id, current.gap_payload, "
            "base.release_id AS base_release_id, base.gap_class AS base_gap_class, "
            "base.status AS base_status, base.review_state AS base_review_state, "
            "base.severity AS base_severity, "
            "base.affected_domains AS base_affected_domains, "
            "base.affected_paths AS base_affected_paths, "
            "base.demand_count AS base_demand_count, "
            "base.created_at AS base_created_at, base.updated_at AS base_updated_at, "
            "base.gap_payload AS base_payload, "
            "base.content_sha256 AS base_content_sha256, latest.transition_id, "
            "latest.source_release_id, latest.candidate_release_id, "
            "latest.transition_state, latest.transitioned_at, "
            "latest.remediation_input_sha256, latest.result_content_sha256, "
            "latest.request_payload, latest.result_payload"
        )
        order = (
            " ORDER BY CASE current.gap_payload ->> 'severity' "
            "WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, "
            "(current.gap_payload ->> 'demand_count')::bigint DESC, "
            "current.current_updated_at DESC, current.gap_id ASC LIMIT %s OFFSET %s"
        )
        with self._connection(write=False) as connection:
            total_row = connection.execute(
                sql.SQL(cast(LiteralString, "SELECT count(*) AS total" + base_query)),
                tuple(parameters),
            ).fetchone()
            rows = connection.execute(
                sql.SQL(cast(LiteralString, select + base_query + order)),
                (*parameters, validated.limit, validated.offset),
            ).fetchall()
        return GapAdminPage(
            items=tuple(self._current_from_row(row) for row in rows),
            total=0 if total_row is None else total_row["total"],
            limit=validated.limit,
            offset=validated.offset,
        )

    @staticmethod
    def _json_rows(connection: Any, statement: str, parameters: tuple[Any, ...]):
        return tuple(
            row["payload"] for row in connection.execute(statement, parameters)
        )

    def get_for_admin(self, gap_id: str) -> GapAdminDetail | None:
        with self._connection(write=False) as connection:
            base = self._base_row(connection, gap_id, lock=False)
            if base is None:
                return None
            initial = self._load_gap_row(base)
            transition_rows = connection.execute(
                "SELECT transition_id, gap_id, source_release_id, "
                "candidate_release_id, transition_state, transitioned_at, "
                "remediation_input_sha256, result_content_sha256, request_payload, "
                "result_payload FROM ops.gap_remediation_transition WHERE gap_id=%s "
                "ORDER BY transitioned_at, transition_id",
                (gap_id,),
            ).fetchall()
            transitions = tuple(self._load_transition(row) for row in transition_rows)
            current = initial if not transitions else transitions[-1].gap
            evidence_ids = list(current.evidence_ids)
            field_assertions = self._json_rows(
                connection,
                "SELECT to_jsonb(assertion) AS payload FROM knowledge.source_assertion "
                "AS assertion WHERE assertion.assertion_id=ANY(%s) "
                "ORDER BY assertion.assertion_id",
                (evidence_ids,),
            )
            relationship_assertions = self._json_rows(
                connection,
                "SELECT to_jsonb(assertion) AS payload "
                "FROM knowledge.relationship_assertion AS assertion "
                "WHERE assertion.assertion_id=ANY(%s) ORDER BY assertion.assertion_id",
                (evidence_ids,),
            )
            matched_assertion_ids = {
                cast(str, row["assertion_id"])
                for row in (*field_assertions, *relationship_assertions)
            }
            canonical_decisions = self._json_rows(
                connection,
                "SELECT to_jsonb(decision) AS payload "
                "FROM knowledge.canonical_decision AS decision "
                "WHERE EXISTS (SELECT 1 FROM knowledge.canonical_decision_assertion "
                "AS member WHERE member.release_id=decision.release_id "
                "AND member.decision_id=decision.decision_id "
                "AND member.assertion_id=ANY(%s)) "
                "ORDER BY decision.release_id, decision.decision_id",
                (list(matched_assertion_ids),),
            )
            relationship_decisions = self._json_rows(
                connection,
                "SELECT to_jsonb(decision) AS payload "
                "FROM knowledge.relationship_decision AS decision "
                "WHERE EXISTS (SELECT 1 FROM knowledge.relationship_decision_assertion "
                "AS member WHERE member.release_id=decision.release_id "
                "AND member.decision_id=decision.decision_id "
                "AND member.assertion_id=ANY(%s)) "
                "ORDER BY decision.release_id, decision.decision_id",
                (list(matched_assertion_ids),),
            )
            release_ids = {
                initial.release_id,
                *(
                    transition.remediation_receipt.candidate_release_id
                    for transition in transitions
                ),
                *(
                    (current.resolved_release_id,)
                    if current.resolved_release_id
                    else ()
                ),
            }
            releases = self._json_rows(
                connection,
                "SELECT to_jsonb(release) || jsonb_build_object("
                "'build_manifest', to_jsonb(manifest)) AS payload "
                "FROM knowledge.release AS release LEFT JOIN publish.build_manifest AS manifest "
                "USING (release_id) WHERE release.release_id=ANY(%s) "
                "ORDER BY release.release_id",
                (list(release_ids),),
            )
            source_record_ids = [
                cast(str, row["source_record_id"])
                for row in (*field_assertions, *relationship_assertions)
            ]
            provenance = self._json_rows(
                connection,
                "SELECT jsonb_build_object('source_record', to_jsonb(record), "
                "'artifact', to_jsonb(artifact)) AS payload "
                "FROM landing.source_record AS record "
                "JOIN landing.evidence_artifact AS artifact USING (artifact_id) "
                "WHERE record.record_id=ANY(%s) ORDER BY record.record_id",
                (source_record_ids,),
            )
        unresolved = tuple(sorted(set(current.evidence_ids) - matched_assertion_ids))
        return GapAdminDetail(
            gap=current,
            transitions=transitions,
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            canonical_decisions=canonical_decisions,
            relationship_decisions=relationship_decisions,
            releases=releases,
            provenance=provenance,
            unresolved_evidence_ids=unresolved,
        )


def create_postgres_knowledge_gap_operations(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
    classifier: GapClassifier | None = None,
    clock: Callable[[], datetime] | None = None,
) -> PostgresKnowledgeGapOperations:
    """Compose the only durable gap writer from an explicit, isolated target."""

    try:
        target = resolve_destructive_database_target(
            _ExplicitTargetConfig(
                database_url=database_url,
                expected_database=expected_database,
                target_kind=target_kind,
            ),
            {},
        )
        require_accepted_backup_gate(backup_gate_root)
    except (DatabaseTargetSafetyError, RebuildWriteGateError) as exc:
        raise KnowledgeGapConfigurationError(
            "Canonical V2 operations configuration is not accepted"
        ) from exc
    return PostgresKnowledgeGapOperations(
        target=target,
        backup_gate_root=backup_gate_root,
        classifier=classifier,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


__all__ = [
    "GapAdminDetail",
    "GapAdminPage",
    "GapAdminQuery",
    "KnowledgeGapConfigurationError",
    "KnowledgeGapIntegrityError",
    "KnowledgeGapPersistenceError",
    "PostgresKnowledgeGapOperations",
    "create_postgres_knowledge_gap_operations",
]
