"""Explicit-disposable PostgreSQL storage for offline canonical identity builds."""

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
from pydantic import JsonValue, ValidationError
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import (
    DatabaseTargetSafetyError,
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

from . import canonical_identity_resolution as _identity
from .canonical_revision import (
    CanonicalRevisionError,
    load_canonical_v2_script_directory,
    require_minimum_canonical_revision,
)
from .contracts import (
    IdentityAction,
    IdentityDecision,
    SourceAssertion,
    TemporalInstantValue,
)
from .rebuild_write_gate import require_accepted_backup_gate


MINIMUM_REVISION = "C2_0008"
VERSION_TABLE = "public.canonical_v2_alembic_version"
OFFLINE_BUILD_AUTHORITY = "offline_canonical_build"
IDENTITY_LOCK_ORDER = (
    "identity_resolution_run",
    "identity_candidate_verdict",
    "identity_decision",
    "identity_decision_context",
    "canonical_identity",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_record",
    "identity_decision_assertion",
    "canonical_identity_source_membership",
    "identity_decision_output_source",
    "canonical_identity_lineage",
    "current_source_identity_assignment",
)


class CanonicalIdentityPersistenceError(RuntimeError):
    """A canonical identity persistence operation failed closed."""


class CanonicalIdentityNotFoundError(CanonicalIdentityPersistenceError):
    """The requested immutable identity resolution does not exist."""


class CanonicalIdentityStore(ABC):
    """Deep storage seam for one immutable identity projection per release."""

    @abstractmethod
    def persist(
        self,
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> _identity.IdentityResolutionResult:
        """Persist an exact request/result pair or replay it byte-for-byte."""
        raise NotImplementedError

    @abstractmethod
    def load(
        self,
        release_id: str,
        decision_run_id: str,
    ) -> _identity.IdentityResolutionResult:
        """Load and revalidate one immutable identity resolution."""
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


def _canonical_json_sha256(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assertion_fingerprint(assertion: SourceAssertion) -> str:
    return _canonical_json_sha256(cast(JsonValue, assertion.model_dump(mode="json")))


def _temporal_json(value: object | None) -> Jsonb | None:
    if value is None:
        return None
    return Jsonb(cast(Any, value).model_dump(mode="json"))


def _legacy_instant(value: object | None) -> Any | None:
    return value.value if isinstance(value, TemporalInstantValue) else None


def _trace_json(decision: IdentityDecision) -> Jsonb | None:
    if decision.llm_trace is None:
        return None
    return Jsonb(decision.llm_trace.model_dump(mode="json"))


def _all_decisions(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[IdentityDecision, ...]:
    decisions: dict[str, IdentityDecision] = {}
    for decision in (*request.prior_identity_decisions, *result.identity_decisions):
        existing = decisions.setdefault(decision.decision_id, decision)
        if existing != decision:
            raise CanonicalIdentityPersistenceError(
                "one decision ID cannot identify different immutable decisions"
            )
    return tuple(decisions.values())


def _all_contexts(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[_identity.IdentityDecisionContext, ...]:
    contexts: dict[str, _identity.IdentityDecisionContext] = {}
    for context in (*request.prior_decision_contexts, *result.decision_contexts):
        existing = contexts.setdefault(context.decision_id, context)
        if existing != context:
            raise CanonicalIdentityPersistenceError(
                "one decision ID cannot identify different immutable contexts"
            )
    if set(contexts) != {
        decision.decision_id for decision in _all_decisions(request, result)
    }:
        raise CanonicalIdentityPersistenceError(
            "every persisted identity decision requires its exact context"
        )
    return tuple(contexts[key] for key in sorted(contexts))


def _all_candidate_verdicts(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[_identity.IdentityCandidateVerdict, ...]:
    verdicts: dict[str, _identity.IdentityCandidateVerdict] = {}
    candidates = [*result.candidate_verdicts]
    candidates.extend(
        context.candidate_verdict
        for context in request.prior_decision_contexts
        if context.candidate_verdict is not None
    )
    for verdict in candidates:
        existing = verdicts.setdefault(verdict.verdict_id, verdict)
        if existing != verdict:
            raise CanonicalIdentityPersistenceError(
                "one verdict ID cannot identify different immutable verdicts"
            )
    return tuple(verdicts[key] for key in sorted(verdicts))


def _all_sources(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[_identity.SourceIdentity, ...]:
    sources: dict[str, _identity.SourceIdentity] = {}
    candidates = [*request.source_identities]
    for context in _all_contexts(request, result):
        candidates.extend(context.source_identities)
    for source in candidates:
        existing = sources.setdefault(source.source_identity_id, source)
        if existing != source:
            raise CanonicalIdentityPersistenceError(
                "one source identity ID cannot identify different immutable content"
            )
    return tuple(sources[key] for key in sorted(sources))


def _all_assertions(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[SourceAssertion, ...]:
    assertions: dict[str, SourceAssertion] = {}
    candidates = [*request.identity_assertions]
    for context in _all_contexts(request, result):
        candidates.extend(context.identity_assertions)
    for assertion in candidates:
        existing = assertions.setdefault(assertion.assertion_id, assertion)
        if existing != assertion:
            raise CanonicalIdentityPersistenceError(
                "one assertion ID cannot identify different immutable content"
            )
    return tuple(assertions[key] for key in sorted(assertions))


def _all_identities(
    result: _identity.IdentityResolutionResult,
) -> tuple[_identity.CanonicalIdentity, ...]:
    return (*result.current_canonical_identities, *result.canonical_identity_history)


def _output_allocations(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[tuple[str, str, str], ...]:
    identities_by_id = {
        identity.canonical_identity_id: identity for identity in _all_identities(result)
    }
    result_decision_ids = {
        decision.decision_id for decision in result.identity_decisions
    }
    allocations: set[tuple[str, str, str]] = set()
    request_identities = (
        *request.current_canonical_identities,
        *request.canonical_identity_history,
    )
    for decision in _all_decisions(request, result):
        decision_allocations: set[tuple[str, str]] = set()
        if decision.decision_id in result_decision_ids:
            candidate_identities = tuple(
                identity
                for identity in identities_by_id.values()
                if identity.identity_decision_id == decision.decision_id
                and identity.canonical_identity_id
                in decision.output_canonical_identity_ids
            )
            for identity in candidate_identities:
                decision_allocations.update(
                    (identity.canonical_identity_id, source_id)
                    for source_id in identity.source_identity_ids
                )
        else:
            for assignment in request.current_source_identity_assignments:
                if assignment.identity_decision_id == decision.decision_id:
                    decision_allocations.add(
                        (
                            assignment.canonical_identity_id,
                            assignment.source_identity_id,
                        )
                    )
            for identity in request_identities:
                if identity.identity_decision_id == decision.decision_id:
                    decision_allocations.update(
                        (identity.canonical_identity_id, source_id)
                        for source_id in identity.source_identity_ids
                    )
        if decision.output_canonical_identity_ids:
            if {source_id for _, source_id in decision_allocations} != set(
                decision.source_identity_ids
            ):
                raise CanonicalIdentityPersistenceError(
                    "identity decision output allocation is incomplete or ambiguous"
                )
            if not {canonical_id for canonical_id, _ in decision_allocations} <= set(
                decision.output_canonical_identity_ids
            ):
                raise CanonicalIdentityPersistenceError(
                    "identity decision output allocation is cross-wired"
                )
        allocations.update(
            (decision.decision_id, canonical_id, source_id)
            for canonical_id, source_id in decision_allocations
        )
    return tuple(sorted(allocations))


def _lineage_edges(
    request: _identity.IdentityResolutionRequest,
    result: _identity.IdentityResolutionResult,
) -> tuple[tuple[str, str, str, str], ...]:
    edges: set[tuple[str, str, str, str]] = set()
    for decision in _all_decisions(request, result):
        if decision.action not in {
            IdentityAction.merge,
            IdentityAction.split_identity,
            IdentityAction.reverse,
        }:
            continue
        for predecessor_id in decision.input_canonical_identity_ids:
            for successor_id in decision.output_canonical_identity_ids:
                if predecessor_id == successor_id:
                    continue
                edges.add(
                    (
                        decision.decision_id,
                        predecessor_id,
                        successor_id,
                        decision.action.value,
                    )
                )
    return tuple(sorted(edges))


class _PostgresCanonicalIdentityStore(CanonicalIdentityStore):
    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        backup_gate_root: Path,
        build_authority: str,
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._build_authority = build_authority
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
            raise CanonicalIdentityPersistenceError(
                "PostgreSQL canonical-identity target identity cannot be read"
            )
        try:
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
        except DatabaseTargetSafetyError as exc:
            raise CanonicalIdentityPersistenceError(
                "PostgreSQL canonical-identity target identity is invalid"
            ) from exc
        revisions = connection.execute(
            f"SELECT version_num FROM {VERSION_TABLE}"
        ).fetchall()
        if len(revisions) != 1:
            raise CanonicalIdentityPersistenceError(
                "canonical-identity target requires exactly one Alembic revision row"
            )
        try:
            require_minimum_canonical_revision(
                scripts=load_canonical_v2_script_directory(),
                current_revision=revisions[0]["version_num"],
                minimum_revision=MINIMUM_REVISION,
            )
        except CanonicalRevisionError as exc:
            raise CanonicalIdentityPersistenceError(
                "canonical-identity target does not satisfy minimum revision "
                f"{MINIMUM_REVISION}"
            ) from exc

    @staticmethod
    def _lock_identity_tables(
        connection: psycopg.Connection[dict[str, Any]],
    ) -> None:
        tables = sql.SQL(", ").join(
            sql.Identifier("knowledge", table) for table in IDENTITY_LOCK_ORDER
        )
        connection.execute(
            sql.SQL("LOCK TABLE {} IN ROW EXCLUSIVE MODE").format(tables)
        )

    @staticmethod
    def _lock_release_boundary(
        connection: psycopg.Connection[dict[str, Any]],
    ) -> None:
        # C2 migrations acquire release before every identity table. Establish
        # that same ordering before even the replay lookup, so a migration can
        # never hold release while this writer holds an identity-table lock.
        connection.execute("LOCK TABLE knowledge.release IN ROW SHARE MODE")

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
            raise CanonicalIdentityPersistenceError(
                "PostgreSQL canonical-identity target cannot be connected"
            ) from exc
        try:
            if not write:
                connection.execute("SET TRANSACTION READ ONLY")
            self._verify_connected_target(connection)
            yield connection
        except psycopg.Error as exc:
            connection.rollback()
            raise CanonicalIdentityPersistenceError(
                "canonical-identity PostgreSQL transaction failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _validated_pair(
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> tuple[
        _identity.IdentityResolutionRequest,
        _identity.IdentityResolutionResult,
    ]:
        if not isinstance(
            request, _identity.IdentityResolutionRequest
        ) or not isinstance(result, _identity.IdentityResolutionResult):
            raise CanonicalIdentityPersistenceError(
                "persist requires typed identity request and result values"
            )
        try:
            validated_request = _identity.IdentityResolutionRequest.model_validate(
                request.model_dump(mode="python")
            )
            validated_result = _identity.validate_identity_resolution_result(
                validated_request,
                _identity.IdentityResolutionResult.model_validate(
                    result.model_dump(mode="python")
                ),
            )
        except (AttributeError, ValueError, ValidationError) as exc:
            raise CanonicalIdentityPersistenceError(
                "identity request/result failed typed integrity validation"
            ) from exc
        _all_decisions(validated_request, validated_result)
        _output_allocations(validated_request, validated_result)
        return validated_request, validated_result

    @staticmethod
    def _require_prerequisites(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        release = connection.execute(
            "SELECT build_run_id, state FROM knowledge.release WHERE release_id = %s",
            (request.release_id,),
        ).fetchone()
        if release is None or release["build_run_id"] != request.decision_run_id:
            raise CanonicalIdentityPersistenceError(
                "identity persistence requires its exact pre-existing candidate release"
            )
        if release["state"] != "candidate":
            raise CanonicalIdentityPersistenceError(
                "identity persistence is restricted to a candidate release"
            )
        policy = connection.execute(
            "SELECT policy_kind, content_sha256, effective_at FROM knowledge.policy "
            "WHERE policy_id = %s AND policy_version = %s",
            (request.policy.policy_id, request.policy.policy_version),
        ).fetchone()
        if policy is None or (
            policy["policy_kind"],
            policy["content_sha256"],
            policy["effective_at"],
        ) != (
            request.policy.policy_kind.value,
            request.policy.content_sha256,
            request.policy.effective_at,
        ):
            raise CanonicalIdentityPersistenceError(
                "identity persistence requires its exact pre-existing policy"
            )
        record_ids = {
            record_id
            for source in _all_sources(request, result)
            for record_id in source.source_record_ids
        }
        existing_record_ids = {
            row["record_id"]
            for row in connection.execute(
                "SELECT record_id FROM landing.source_record WHERE record_id = ANY(%s)",
                (list(record_ids),),
            ).fetchall()
        }
        if existing_record_ids != record_ids:
            raise CanonicalIdentityPersistenceError(
                "identity persistence will not invent missing landing source records"
            )
        partial = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.identity_decision WHERE release_id = %s) + "
            "(SELECT count(*) FROM knowledge.canonical_identity WHERE release_id = %s) "
            "AS row_count",
            (request.release_id, request.release_id),
        ).fetchone()
        if partial is None or partial["row_count"] != 0:
            raise CanonicalIdentityPersistenceError(
                "identity release contains partial history without an immutable run"
            )

    @staticmethod
    def _insert_sources_and_assertions(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        for source in _all_sources(request, result):
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (source_identity_id) DO NOTHING",
                (
                    source.source_identity_id,
                    source.source_system,
                    source.source_key,
                    source.entity_type,
                    Jsonb(source.normalized_keys),
                    source.first_observed_at,
                    source.last_observed_at,
                    source.state.value,
                ),
            )
            for record_id in source.source_record_ids:
                connection.execute(
                    "INSERT INTO knowledge.source_identity_record "
                    "(source_identity_id, record_id) VALUES (%s, %s) "
                    "ON CONFLICT (source_identity_id, record_id) DO NOTHING",
                    (source.source_identity_id, record_id),
                )
        for assertion in _all_assertions(request, result):
            connection.execute(
                "INSERT INTO knowledge.source_assertion "
                "(assertion_id, source_record_id, source_identity_id, "
                "subject_entity_type, field_path, value, "
                "assertion_fingerprint_sha256, observed_at, source_event_time, "
                "valid_from, valid_to, valid_from_temporal, valid_to_temporal, "
                "assertion_run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s) "
                "ON CONFLICT (assertion_id) DO NOTHING",
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
    def _verify_base_projection(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        sources = _all_sources(request, result)
        source_ids = [source.source_identity_id for source in sources]
        source_rows = connection.execute(
            "SELECT source_identity_id, source_system, source_key, entity_type, "
            "normalized_keys, first_observed_at, last_observed_at, state "
            "FROM knowledge.source_identity WHERE source_identity_id = ANY(%s) "
            "ORDER BY source_identity_id",
            (source_ids,),
        ).fetchall()
        durable_sources = {
            row["source_identity_id"]: (
                row["source_system"],
                row["source_key"],
                row["entity_type"],
                row["normalized_keys"],
                row["first_observed_at"],
                row["last_observed_at"],
                row["state"],
            )
            for row in source_rows
        }
        expected_sources = {
            source.source_identity_id: (
                source.source_system,
                source.source_key,
                source.entity_type,
                dict(source.normalized_keys),
                source.first_observed_at,
                source.last_observed_at,
                source.state.value,
            )
            for source in sources
        }
        if durable_sources != expected_sources:
            raise CanonicalIdentityPersistenceError(
                "immutable source identity base projection conflicts"
            )

        durable_records = {
            (row["source_identity_id"], row["record_id"])
            for row in connection.execute(
                "SELECT source_identity_id, record_id "
                "FROM knowledge.source_identity_record "
                "WHERE source_identity_id = ANY(%s)",
                (source_ids,),
            ).fetchall()
        }
        expected_records = {
            (source.source_identity_id, record_id)
            for source in sources
            for record_id in source.source_record_ids
        }
        if durable_records != expected_records:
            raise CanonicalIdentityPersistenceError(
                "immutable source identity record set conflicts"
            )

        assertions = _all_assertions(request, result)
        assertion_ids = [assertion.assertion_id for assertion in assertions]
        durable_assertions = {
            row["assertion_id"]: (
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
                ),
                row["assertion_fingerprint_sha256"],
            )
            for row in connection.execute(
                "SELECT assertion_id, source_record_id, source_identity_id, "
                "subject_entity_type, field_path, value, "
                "assertion_fingerprint_sha256, observed_at, source_event_time, "
                "valid_from_temporal, valid_to_temporal, assertion_run_id "
                "FROM knowledge.source_assertion WHERE assertion_id = ANY(%s) "
                "ORDER BY assertion_id",
                (assertion_ids,),
            ).fetchall()
        }
        expected_assertions = {
            assertion.assertion_id: (
                assertion,
                _assertion_fingerprint(assertion),
            )
            for assertion in assertions
        }
        if durable_assertions != expected_assertions:
            raise CanonicalIdentityPersistenceError(
                "immutable assertion base projection conflicts"
            )

    @staticmethod
    def _insert_run(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
        *,
        build_authority: str,
    ) -> None:
        connection.execute(
            "INSERT INTO knowledge.identity_resolution_run "
            "(release_id, decision_run_id, identity_method_version, as_of, "
            "policy_id, policy_version, build_authority, request_content, "
            "request_content_sha256, result_content, result_content_sha256) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                request.release_id,
                request.decision_run_id,
                request.identity_method_version,
                request.as_of,
                request.policy.policy_id,
                request.policy.policy_version,
                build_authority,
                Jsonb(request.model_dump(mode="json")),
                _identity.canonical_identity_resolution_request_sha256(request),
                Jsonb(result.model_dump(mode="json")),
                result.content_sha256,
            ),
        )

    @staticmethod
    def _insert_decisions(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        decisions = list(_all_decisions(request, result))
        inserted: set[str] = set()
        while decisions:
            ready = [
                decision
                for decision in decisions
                if decision.reversal_of_decision_id is None
                or decision.reversal_of_decision_id in inserted
            ]
            if not ready:
                raise CanonicalIdentityPersistenceError(
                    "identity reversal lineage is missing or cyclic"
                )
            for decision in ready:
                connection.execute(
                    "INSERT INTO knowledge.identity_decision "
                    "(release_id, decision_id, action, policy_id, policy_version, "
                    "method, method_version, decision_run_id, confidence, rationale, "
                    "decided_at, reversal_of_decision_id, llm_trace, "
                    "human_review_resolution) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s)",
                    (
                        request.release_id,
                        decision.decision_id,
                        decision.action.value,
                        decision.policy.policy_id,
                        decision.policy.policy_version,
                        decision.method.value,
                        decision.method_version,
                        decision.decision_run_id,
                        decision.confidence,
                        decision.rationale,
                        decision.decided_at,
                        decision.reversal_of_decision_id,
                        _trace_json(decision),
                        (
                            Jsonb(
                                decision.human_review_resolution.model_dump(mode="json")
                            )
                            if decision.human_review_resolution is not None
                            else None
                        ),
                    ),
                )
                inserted.add(decision.decision_id)
                decisions.remove(decision)

    @staticmethod
    def _insert_identities_and_topology(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        identities = _all_identities(result)
        for identity in identities:
            connection.execute(
                "INSERT INTO knowledge.canonical_identity "
                "(release_id, canonical_identity_id, entity_type, state, "
                "display_name, identity_decision_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    identity.canonical_identity_id,
                    identity.entity_type,
                    identity.state.value,
                    identity.display_name,
                    identity.identity_decision_id,
                ),
            )
        source_by_id = {
            source.source_identity_id: source
            for source in _all_sources(request, result)
        }
        for decision in _all_decisions(request, result):
            for source_id in decision.source_identity_ids:
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_source_identity "
                    "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                    (result.release_id, decision.decision_id, source_id),
                )
            for canonical_id in decision.input_canonical_identity_ids:
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_input "
                    "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
                    (result.release_id, decision.decision_id, canonical_id),
                )
            for canonical_id in decision.output_canonical_identity_ids:
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_output "
                    "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
                    (result.release_id, decision.decision_id, canonical_id),
                )
            for record_id in decision.supporting_record_ids:
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_record "
                    "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
                    (result.release_id, decision.decision_id, record_id),
                )
            if not set(decision.source_identity_ids) <= set(source_by_id):
                raise CanonicalIdentityPersistenceError(
                    "identity decision references a source outside the exact request"
                )
        for identity in identities:
            for source_id in identity.source_identity_ids:
                connection.execute(
                    "INSERT INTO knowledge.canonical_identity_source_membership "
                    "(release_id, canonical_identity_id, source_identity_id) "
                    "VALUES (%s, %s, %s)",
                    (result.release_id, identity.canonical_identity_id, source_id),
                )
        for decision_id, canonical_id, source_id in _output_allocations(
            request, result
        ):
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, %s, %s, %s)",
                (result.release_id, decision_id, canonical_id, source_id),
            )
        for decision_id, predecessor, successor, transition in _lineage_edges(
            request, result
        ):
            connection.execute(
                "INSERT INTO knowledge.canonical_identity_lineage "
                "(release_id, decision_id, predecessor_identity_id, "
                "successor_identity_id, transition) VALUES (%s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    decision_id,
                    predecessor,
                    successor,
                    transition,
                ),
            )

    @staticmethod
    def _insert_result_projection(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        for verdict in _all_candidate_verdicts(request, result):
            payload = cast(JsonValue, verdict.model_dump(mode="json"))
            connection.execute(
                "INSERT INTO knowledge.identity_candidate_verdict "
                "(release_id, decision_run_id, verdict_id, verdict, method, "
                "confidence, verdict_content, content_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    result.decision_run_id,
                    verdict.verdict_id,
                    verdict.verdict.value,
                    verdict.method.value,
                    verdict.confidence,
                    Jsonb(payload),
                    _canonical_json_sha256(payload),
                ),
            )
        assertions = {
            assertion.assertion_id: assertion
            for assertion in _all_assertions(request, result)
        }
        for context in _all_contexts(request, result):
            candidate_verdict_id = (
                context.candidate_verdict.verdict_id
                if context.candidate_verdict is not None
                else None
            )
            supporting_assertion_ids = tuple(
                assertion.assertion_id for assertion in context.identity_assertions
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_context "
                "(release_id, decision_id, decision_run_id, candidate_verdict_id, "
                "context_content, content_sha256, supporting_assertion_ids) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    result.release_id,
                    context.decision_id,
                    result.decision_run_id,
                    candidate_verdict_id,
                    Jsonb(context.model_dump(mode="json")),
                    context.content_sha256,
                    Jsonb(list(supporting_assertion_ids)),
                ),
            )
            for assertion_id in supporting_assertion_ids:
                assertion = assertions[assertion_id]
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_assertion "
                    "(release_id, decision_id, assertion_id, source_identity_id, "
                    "source_record_id) VALUES (%s, %s, %s, %s, %s)",
                    (
                        result.release_id,
                        context.decision_id,
                        assertion_id,
                        assertion.source_identity_id,
                        assertion.source_record_id,
                    ),
                )
        for assignment in result.source_identity_assignments:
            connection.execute(
                "INSERT INTO knowledge.current_source_identity_assignment "
                "(release_id, source_identity_id, canonical_identity_id, "
                "identity_decision_id) VALUES (%s, %s, %s, %s)",
                (
                    result.release_id,
                    assignment.source_identity_id,
                    assignment.canonical_identity_id,
                    assignment.identity_decision_id,
                ),
            )

    @staticmethod
    def _load_snapshot(
        connection: psycopg.Connection[dict[str, Any]],
        *,
        release_id: str,
        decision_run_id: str,
    ) -> tuple[
        _identity.IdentityResolutionRequest,
        _identity.IdentityResolutionResult,
    ]:
        row = connection.execute(
            "SELECT release_id, decision_run_id, identity_method_version, as_of, "
            "policy_id, policy_version, build_authority, request_content, request_content_sha256, "
            "result_content, result_content_sha256 "
            "FROM knowledge.identity_resolution_run "
            "WHERE release_id = %s AND decision_run_id = %s",
            (release_id, decision_run_id),
        ).fetchone()
        if row is None:
            raise CanonicalIdentityNotFoundError(
                "canonical identity resolution was not found"
            )
        try:
            request = _identity.IdentityResolutionRequest.model_validate(
                row["request_content"]
            )
            result = _identity.IdentityResolutionResult.model_validate(
                row["result_content"]
            )
            validated = _identity.validate_identity_resolution_result(request, result)
        except (ValueError, ValidationError) as exc:
            raise CanonicalIdentityPersistenceError(
                "durable identity snapshot failed typed validation"
            ) from exc
        expected_key = (release_id, decision_run_id)
        if (
            (row["release_id"], row["decision_run_id"]) != expected_key
            or (request.release_id, request.decision_run_id) != expected_key
            or (result.release_id, result.decision_run_id) != expected_key
        ):
            raise CanonicalIdentityPersistenceError(
                "durable identity snapshot row key is cross-wired"
            )
        if row[
            "request_content_sha256"
        ] != _identity.canonical_identity_resolution_request_sha256(request):
            raise CanonicalIdentityPersistenceError(
                "durable identity request hash mismatch"
            )
        if row["result_content_sha256"] != validated.content_sha256:
            raise CanonicalIdentityPersistenceError(
                "durable identity result hash mismatch"
            )
        if (
            row["identity_method_version"] != request.identity_method_version
            or row["as_of"] != request.as_of
            or row["policy_id"] != request.policy.policy_id
            or row["policy_version"] != request.policy.policy_version
            or row["build_authority"] != OFFLINE_BUILD_AUTHORITY
        ):
            raise CanonicalIdentityPersistenceError(
                "durable identity run context is incomplete or corrupt"
            )
        return request, validated

    @staticmethod
    def _verify_projection(
        connection: psycopg.Connection[dict[str, Any]],
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> None:
        _PostgresCanonicalIdentityStore._verify_base_projection(
            connection, request, result
        )
        decisions = _all_decisions(request, result)
        decision_rows = connection.execute(
            "SELECT decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "reversal_of_decision_id, llm_trace, human_review_resolution "
            "FROM knowledge.identity_decision "
            "WHERE release_id = %s ORDER BY decision_id",
            (result.release_id,),
        ).fetchall()
        durable_decisions = {
            row["decision_id"]: (
                row["action"],
                row["policy_id"],
                row["policy_version"],
                row["method"],
                row["method_version"],
                row["decision_run_id"],
                row["confidence"],
                row["rationale"],
                row["decided_at"],
                row["reversal_of_decision_id"],
                row["llm_trace"],
                row["human_review_resolution"],
            )
            for row in decision_rows
        }
        expected_decisions = {
            decision.decision_id: (
                decision.action.value,
                decision.policy.policy_id,
                decision.policy.policy_version,
                decision.method.value,
                decision.method_version,
                decision.decision_run_id,
                decision.confidence,
                decision.rationale,
                decision.decided_at,
                decision.reversal_of_decision_id,
                (
                    decision.llm_trace.model_dump(mode="json")
                    if decision.llm_trace is not None
                    else None
                ),
                (
                    decision.human_review_resolution.model_dump(mode="json")
                    if decision.human_review_resolution is not None
                    else None
                ),
            )
            for decision in decisions
        }
        if durable_decisions != expected_decisions:
            raise CanonicalIdentityPersistenceError(
                "durable identity decisions are incomplete or corrupt"
            )
        relation_specs = (
            (
                "identity_decision_source_identity",
                "source_identity_id",
                {
                    (decision.decision_id, source_id)
                    for decision in decisions
                    for source_id in decision.source_identity_ids
                },
            ),
            (
                "identity_decision_input",
                "canonical_identity_id",
                {
                    (decision.decision_id, canonical_id)
                    for decision in decisions
                    for canonical_id in decision.input_canonical_identity_ids
                },
            ),
            (
                "identity_decision_output",
                "canonical_identity_id",
                {
                    (decision.decision_id, canonical_id)
                    for decision in decisions
                    for canonical_id in decision.output_canonical_identity_ids
                },
            ),
            (
                "identity_decision_record",
                "record_id",
                {
                    (decision.decision_id, record_id)
                    for decision in decisions
                    for record_id in decision.supporting_record_ids
                },
            ),
        )
        for table, value_column, expected_rows in relation_specs:
            projection_query = sql.SQL(
                "SELECT decision_id, {} FROM knowledge.{} WHERE release_id = %s"
            ).format(sql.Identifier(value_column), sql.Identifier(table))
            durable_rows = {
                (row["decision_id"], row[value_column])
                for row in connection.execute(
                    projection_query,
                    (result.release_id,),
                ).fetchall()
            }
            if durable_rows != expected_rows:
                raise CanonicalIdentityPersistenceError(
                    f"durable {table} projection is incomplete or corrupt"
                )
        identity_rows = connection.execute(
            "SELECT canonical_identity_id, entity_type, state, display_name, "
            "identity_decision_id FROM knowledge.canonical_identity "
            "WHERE release_id = %s",
            (result.release_id,),
        ).fetchall()
        durable_identities = {
            row["canonical_identity_id"]: (
                row["entity_type"],
                row["state"],
                row["display_name"],
                row["identity_decision_id"],
            )
            for row in identity_rows
        }
        expected_identities = {
            identity.canonical_identity_id: (
                identity.entity_type,
                identity.state.value,
                identity.display_name,
                identity.identity_decision_id,
            )
            for identity in _all_identities(result)
        }
        if durable_identities != expected_identities:
            raise CanonicalIdentityPersistenceError(
                "durable canonical identities are incomplete or corrupt"
            )
        membership_rows = connection.execute(
            "SELECT canonical_identity_id, source_identity_id "
            "FROM knowledge.canonical_identity_source_membership "
            "WHERE release_id = %s",
            (result.release_id,),
        ).fetchall()
        durable_membership = {
            (row["canonical_identity_id"], row["source_identity_id"])
            for row in membership_rows
        }
        expected_membership = {
            (identity.canonical_identity_id, source_id)
            for identity in _all_identities(result)
            for source_id in identity.source_identity_ids
        }
        if durable_membership != expected_membership:
            raise CanonicalIdentityPersistenceError(
                "durable canonical identity membership is incomplete or corrupt"
            )
        allocation_rows = connection.execute(
            "SELECT decision_id, canonical_identity_id, source_identity_id "
            "FROM knowledge.identity_decision_output_source WHERE release_id = %s",
            (result.release_id,),
        ).fetchall()
        durable_allocations = {
            (
                row["decision_id"],
                row["canonical_identity_id"],
                row["source_identity_id"],
            )
            for row in allocation_rows
        }
        if durable_allocations != set(_output_allocations(request, result)):
            raise CanonicalIdentityPersistenceError(
                "durable identity output allocation is incomplete or corrupt"
            )
        assignment_rows = connection.execute(
            "SELECT release_id, source_identity_id, canonical_identity_id, "
            "identity_decision_id FROM knowledge.current_source_identity_assignment "
            "WHERE release_id = %s ORDER BY source_identity_id",
            (result.release_id,),
        ).fetchall()
        durable_assignments = tuple(
            _identity.SourceIdentityAssignment.model_validate(row)
            for row in assignment_rows
        )
        if durable_assignments != result.source_identity_assignments:
            raise CanonicalIdentityPersistenceError(
                "durable current source assignments are incomplete or corrupt"
            )
        context_rows = connection.execute(
            "SELECT decision_id, decision_run_id, candidate_verdict_id, "
            "context_content, content_sha256, supporting_assertion_ids "
            "FROM knowledge.identity_decision_context WHERE release_id = %s "
            "ORDER BY decision_id",
            (result.release_id,),
        ).fetchall()
        durable_contexts = {
            row["decision_id"]: (
                row["decision_run_id"],
                row["candidate_verdict_id"],
                _identity.IdentityDecisionContext.model_validate(
                    row["context_content"]
                ),
                row["content_sha256"],
                tuple(row["supporting_assertion_ids"]),
            )
            for row in context_rows
        }
        expected_contexts = {
            context.decision_id: (
                result.decision_run_id,
                (
                    context.candidate_verdict.verdict_id
                    if context.candidate_verdict is not None
                    else None
                ),
                context,
                context.content_sha256,
                tuple(
                    assertion.assertion_id for assertion in context.identity_assertions
                ),
            )
            for context in _all_contexts(request, result)
        }
        if durable_contexts != expected_contexts:
            raise CanonicalIdentityPersistenceError(
                "durable identity decision contexts are incomplete or corrupt"
            )
        durable_decision_assertions = {
            (
                row["decision_id"],
                row["assertion_id"],
                row["source_identity_id"],
                row["source_record_id"],
            )
            for row in connection.execute(
                "SELECT decision_id, assertion_id, source_identity_id, "
                "source_record_id FROM "
                "knowledge.identity_decision_assertion WHERE release_id = %s",
                (result.release_id,),
            ).fetchall()
        }
        expected_decision_assertions = {
            (
                context.decision_id,
                assertion.assertion_id,
                assertion.source_identity_id,
                assertion.source_record_id,
            )
            for context in _all_contexts(request, result)
            for assertion in context.identity_assertions
        }
        if durable_decision_assertions != expected_decision_assertions:
            raise CanonicalIdentityPersistenceError(
                "durable identity decision evidence is incomplete or corrupt"
            )
        verdict_rows = connection.execute(
            "SELECT verdict_content, content_sha256 FROM "
            "knowledge.identity_candidate_verdict WHERE release_id = %s "
            "ORDER BY verdict_id",
            (result.release_id,),
        ).fetchall()
        durable_verdicts = tuple(
            _identity.IdentityCandidateVerdict.model_validate(row["verdict_content"])
            for row in verdict_rows
        )
        if durable_verdicts != _all_candidate_verdicts(request, result) or any(
            row["content_sha256"]
            != _canonical_json_sha256(cast(JsonValue, row["verdict_content"]))
            for row in verdict_rows
        ):
            raise CanonicalIdentityPersistenceError(
                "durable identity candidate verdicts are incomplete or corrupt"
            )
        lineage_rows = connection.execute(
            "SELECT decision_id, predecessor_identity_id, successor_identity_id, "
            "transition FROM knowledge.canonical_identity_lineage "
            "WHERE release_id = %s",
            (result.release_id,),
        ).fetchall()
        durable_lineage = {
            (
                row["decision_id"],
                row["predecessor_identity_id"],
                row["successor_identity_id"],
                row["transition"],
            )
            for row in lineage_rows
        }
        if durable_lineage != set(_lineage_edges(request, result)):
            raise CanonicalIdentityPersistenceError(
                "durable canonical identity lineage is incomplete or corrupt"
            )

    def persist(
        self,
        request: _identity.IdentityResolutionRequest,
        result: _identity.IdentityResolutionResult,
    ) -> _identity.IdentityResolutionResult:
        validated_request, validated_result = self._validated_pair(request, result)
        try:
            with self._connection(write=True) as connection:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (validated_request.release_id,),
                )
                self._lock_release_boundary(connection)
                existing = connection.execute(
                    "SELECT decision_run_id FROM knowledge.identity_resolution_run "
                    "WHERE release_id = %s",
                    (validated_request.release_id,),
                ).fetchone()
                if existing is not None:
                    durable_request, durable_result = self._load_snapshot(
                        connection,
                        release_id=validated_request.release_id,
                        decision_run_id=existing["decision_run_id"],
                    )
                    self._verify_projection(connection, durable_request, durable_result)
                    if (
                        durable_request != validated_request
                        or durable_result != validated_result
                    ):
                        raise CanonicalIdentityPersistenceError(
                            "one release cannot identify changed identity content"
                        )
                    connection.rollback()
                    return durable_result

                require_accepted_backup_gate(self._backup_gate_root)
                self._verify_connected_target(connection)
                self._lock_identity_tables(connection)
                self._require_prerequisites(
                    connection, validated_request, validated_result
                )
                # Locks and prerequisite reads can wait. Re-validate the accepted
                # evidence bytes and exact connected target only after they finish,
                # immediately before the transaction's first durable mutation.
                require_accepted_backup_gate(self._backup_gate_root)
                self._verify_connected_target(connection)
                self._insert_sources_and_assertions(
                    connection, validated_request, validated_result
                )
                self._verify_base_projection(
                    connection, validated_request, validated_result
                )
                self._insert_run(
                    connection,
                    validated_request,
                    validated_result,
                    build_authority=self._build_authority,
                )
                self._insert_decisions(connection, validated_request, validated_result)
                self._insert_identities_and_topology(
                    connection, validated_request, validated_result
                )
                self._insert_result_projection(
                    connection, validated_request, validated_result
                )
                connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
                durable_request, durable_result = self._load_snapshot(
                    connection,
                    release_id=validated_request.release_id,
                    decision_run_id=validated_request.decision_run_id,
                )
                self._verify_projection(connection, durable_request, durable_result)
                if (
                    durable_request != validated_request
                    or durable_result != validated_result
                ):
                    raise CanonicalIdentityPersistenceError(
                        "durable identity content does not exactly match its input"
                    )
                connection.commit()
                return durable_result
        except CanonicalIdentityPersistenceError:
            raise
        except (KeyError, TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise CanonicalIdentityPersistenceError(
                "identity resolution could not be persisted exactly"
            ) from exc

    def load(
        self,
        release_id: str,
        decision_run_id: str,
    ) -> _identity.IdentityResolutionResult:
        try:
            with self._connection(write=False) as connection:
                request, result = self._load_snapshot(
                    connection,
                    release_id=release_id,
                    decision_run_id=decision_run_id,
                )
                self._verify_projection(connection, request, result)
                connection.rollback()
                return result
        except (CanonicalIdentityNotFoundError, CanonicalIdentityPersistenceError):
            raise
        except (KeyError, TypeError, UnicodeError, ValueError, ValidationError) as exc:
            raise CanonicalIdentityPersistenceError(
                "durable identity resolution is incomplete or corrupt"
            ) from exc


def create_postgres_canonical_identity_store(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
    build_authority: str,
) -> CanonicalIdentityStore:
    """Create a gate-checked offline writer for one explicit disposable target."""

    if build_authority != OFFLINE_BUILD_AUTHORITY:
        raise CanonicalIdentityPersistenceError(
            "canonical identity persistence requires explicit offline build authority"
        )
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
        raise CanonicalIdentityPersistenceError(
            "canonical identity target selection failed explicit safety checks"
        ) from exc
    if target.target_kind != "disposable":
        raise CanonicalIdentityPersistenceError(
            "canonical identity persistence is restricted to a disposable target"
        )
    store = _PostgresCanonicalIdentityStore(
        target=target,
        backup_gate_root=accepted_root,
        build_authority=build_authority,
    )
    store.verify_ready()
    return store


__all__ = [
    "CanonicalIdentityNotFoundError",
    "CanonicalIdentityPersistenceError",
    "CanonicalIdentityStore",
    "create_postgres_canonical_identity_store",
]
