from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, LiteralString

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy.engine import make_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0002"
EXPECTED_DATABASE = "miroflow_canonical_v2_s3d_disposable"
EXPECTED_MARKER = (
    "miroflow:destructive-target:v1:disposable:miroflow_canonical_v2_s3d_disposable"
)
NOW = datetime(2026, 7, 11, 17, 30, tzinfo=timezone.utc)
BUSINESS_SCHEMAS = {
    "landing",
    "knowledge",
    "professor",
    "company",
    "paper",
    "patent",
    "publish",
    "ops",
}
EXPECTED_SHARED_TABLES = {
    ("landing", "evidence_artifact"),
    ("landing", "parser_run"),
    ("landing", "source_record"),
    ("landing", "source_error"),
    ("knowledge", "release"),
    ("knowledge", "policy"),
    ("knowledge", "source_identity"),
    ("knowledge", "source_identity_record"),
    ("knowledge", "source_assertion"),
    ("knowledge", "canonical_identity"),
    ("knowledge", "identity_decision"),
    ("knowledge", "identity_decision_source_identity"),
    ("knowledge", "identity_decision_input"),
    ("knowledge", "identity_decision_output"),
    ("knowledge", "identity_decision_record"),
    ("knowledge", "canonical_decision"),
    ("knowledge", "canonical_decision_assertion"),
    ("knowledge", "relationship_type"),
    ("knowledge", "relationship_assertion"),
    ("knowledge", "relationship_decision"),
    ("knowledge", "relationship_decision_assertion"),
    ("publish", "build_manifest"),
    ("publish", "manifest_section"),
    ("publish", "active_release"),
}


@dataclass(frozen=True)
class _Target:
    connection: psycopg.Connection[Any]
    config: Config


def _explicit_environment() -> tuple[str, str, str, str]:
    names = (
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not all(values):
        pytest.skip(
            "Canonical V2 integrity integration requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _migration_config(
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: str,
) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("miroflow.expected_database", expected_database)
    config.set_main_option("miroflow.target_kind", target_kind)
    config.set_main_option("miroflow.backup_gate_root", backup_gate_root)
    return config


def _prepare_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _verify_target(connection: psycopg.Connection[Any]) -> None:
    actual_database, marker = connection.execute(
        "SELECT current_database(), "
        "shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = current_database()"
    ).fetchone()  # type: ignore[misc]
    assert actual_database == EXPECTED_DATABASE
    assert marker == EXPECTED_MARKER
    connection.rollback()


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert expected_database == EXPECTED_DATABASE
    assert target_kind == "disposable"
    _prepare_environment(monkeypatch)
    config = _migration_config(
        database_url,
        expected_database,
        target_kind,
        backup_gate_root,
    )
    command.upgrade(config, "head")
    connection = psycopg.connect(_psycopg_dsn(database_url), autocommit=False)
    _verify_target(connection)
    try:
        yield _Target(connection=connection, config=config)
    finally:
        connection.rollback()
        connection.close()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _assert_database_error(
    connection: psycopg.Connection[Any],
    error_type: type[BaseException],
    statement: LiteralString,
    parameters: tuple[Any, ...] | dict[str, Any] | None = None,
) -> None:
    connection.execute("SAVEPOINT expected_database_error")
    try:
        with pytest.raises(error_type):
            connection.execute(statement, parameters)
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT expected_database_error")
        connection.execute("RELEASE SAVEPOINT expected_database_error")


def _insert_release(
    connection: psycopg.Connection[Any],
    release_id: str,
    *,
    state: str = "accepted",
    previous_release_id: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO knowledge.release "
        "(release_id, build_run_id, state, manifest_sha256, previous_release_id, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            release_id,
            f"build-{release_id}",
            state,
            _fingerprint(f"manifest:{release_id}"),
            previous_release_id,
            NOW,
        ),
    )


def _insert_policy(
    connection: psycopg.Connection[Any],
    policy_id: str,
    policy_kind: str,
) -> None:
    connection.execute(
        "INSERT INTO knowledge.policy "
        "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
        "VALUES (%s, 'v1', %s, %s, %s) ON CONFLICT DO NOTHING",
        (policy_id, policy_kind, _fingerprint(f"policy:{policy_id}"), NOW),
    )


def _insert_artifact_graph(connection: psycopg.Connection[Any]) -> dict[str, str]:
    values = {
        "artifact_id": "artifact-1",
        "parse_run_id": "parse-run-1",
        "record_id": "record-1",
        "source_identity_id": "source-company-1",
        "assertion_id": "assertion-1",
        "assertion_fingerprint": _fingerprint("assertion-1"),
    }
    connection.execute(
        "INSERT INTO landing.evidence_artifact "
        "(artifact_id, source_kind, source_locator, content_sha256, byte_size, acquired_at, run_id) "
        "VALUES (%s, 'historical_jsonl', 'restore/company.jsonl', %s, 12, %s, 'copy-run-1')",
        (values["artifact_id"], _fingerprint("artifact-1"), NOW),
    )
    connection.execute(
        "INSERT INTO landing.parser_run "
        "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
        "run_status, started_at, finished_at) "
        "VALUES (%s, %s, 'jsonl', 'parser-v1', 'company-v1', 'succeeded', %s, %s)",
        (values["parse_run_id"], values["artifact_id"], NOW, NOW),
    )
    connection.execute(
        "INSERT INTO landing.source_record "
        "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
        "parse_status, payload, parsed_at) "
        "VALUES (%s, %s, 'batch-1', 'line:1', %s, 'parsed', %s, %s)",
        (
            values["record_id"],
            values["artifact_id"],
            values["parse_run_id"],
            Jsonb({"company_name": "Example"}),
            NOW,
        ),
    )
    connection.execute(
        "INSERT INTO knowledge.source_identity "
        "(source_identity_id, source_system, source_key, entity_type, normalized_keys, "
        "first_observed_at, last_observed_at, state) "
        "VALUES (%s, 'historical_jsonl', 'line:1', 'company', %s, %s, %s, 'active')",
        (
            values["source_identity_id"],
            Jsonb({"name": "example"}),
            NOW,
            NOW,
        ),
    )
    connection.execute(
        "INSERT INTO knowledge.source_identity_record (source_identity_id, record_id) "
        "VALUES (%s, %s)",
        (values["source_identity_id"], values["record_id"]),
    )
    connection.execute(
        "INSERT INTO knowledge.source_assertion "
        "(assertion_id, source_record_id, source_identity_id, subject_entity_type, "
        "field_path, value, assertion_fingerprint_sha256, observed_at, assertion_run_id) "
        "VALUES (%s, %s, %s, 'company', 'name', %s, %s, %s, 'assert-run-1')",
        (
            values["assertion_id"],
            values["record_id"],
            values["source_identity_id"],
            Jsonb("Example"),
            values["assertion_fingerprint"],
            NOW,
        ),
    )
    return values


def _insert_identity(
    connection: psycopg.Connection[Any],
    release_id: str,
    identity_id: str,
    entity_type: str,
) -> None:
    _insert_policy(connection, "identity-policy", "identity")
    decision_id = f"create-{release_id}-{identity_id}"
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
        "'identity-v1', %s, 1.0, 'fixture identity', %s)",
        (release_id, decision_id, f"build-{release_id}", NOW),
    )
    connection.execute(
        "INSERT INTO knowledge.canonical_identity "
        "(release_id, canonical_identity_id, entity_type, state, display_name, "
        "identity_decision_id) VALUES (%s, %s, %s, 'active', %s, %s)",
        (release_id, identity_id, entity_type, identity_id, decision_id),
    )


def test_c2_0002_is_current_and_shared_tables_exist(target: _Target) -> None:
    scripts = ScriptDirectory.from_config(target.config)
    assert scripts.get_revision(EXPECTED_REVISION) is not None
    assert target.connection.execute(
        "SELECT version_num FROM public.canonical_v2_alembic_version"
    ).fetchone() == (scripts.get_current_head(),)
    rows = target.connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('landing', 'knowledge', 'publish')"
    ).fetchall()
    assert EXPECTED_SHARED_TABLES <= {(row[0], row[1]) for row in rows}


def test_foreign_keys_and_logical_uniqueness_reject_orphans_and_replay(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)

    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO landing.source_record "
        "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
        "parse_status, payload, parsed_at) "
        "VALUES ('orphan-record', 'missing-artifact', 'batch-1', 'line:2', "
        "'missing-run', 'parsed', '{}'::jsonb, %s)",
        (NOW,),
    )
    _assert_database_error(
        connection,
        errors.UniqueViolation,
        "INSERT INTO landing.source_record "
        "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
        "parse_status, payload, parsed_at) "
        "VALUES ('record-replay', %s, 'batch-1', 'line:1', %s, 'parsed', "
        "'{}'::jsonb, %s)",
        (values["artifact_id"], values["parse_run_id"], NOW),
    )
    _assert_database_error(
        connection,
        errors.UniqueViolation,
        "INSERT INTO knowledge.source_assertion "
        "(assertion_id, source_record_id, source_identity_id, subject_entity_type, "
        "field_path, value, assertion_fingerprint_sha256, observed_at, assertion_run_id) "
        "VALUES ('assertion-replay', %s, %s, 'company', 'name', %s, "
        "%s, %s, 'assert-run-2')",
        (
            values["record_id"],
            values["source_identity_id"],
            Jsonb("Example"),
            values["assertion_fingerprint"],
            NOW,
        ),
    )


def test_identical_bytes_can_keep_distinct_source_and_copy_lineage(
    target: _Target,
) -> None:
    connection = target.connection
    content_sha256 = _fingerprint("same-source-bytes")
    connection.execute(
        "INSERT INTO landing.evidence_artifact "
        "(artifact_id, source_kind, source_locator, content_sha256, byte_size, acquired_at, run_id) "
        "VALUES ('source-artifact', 'forensic_source', 'source/volume', %s, 12, %s, 'copy-run-1')",
        (content_sha256, NOW),
    )
    connection.execute(
        "INSERT INTO landing.evidence_artifact "
        "(artifact_id, source_kind, source_locator, content_sha256, byte_size, acquired_at, run_id, "
        "parent_artifact_id, parent_content_sha256) "
        "VALUES ('copy-artifact', 'verified_copy', 'backup/volume', %s, 12, %s, 'copy-run-1', "
        "'source-artifact', %s)",
        (content_sha256, NOW, content_sha256),
    )

    assert connection.execute(
        "SELECT artifact_id, source_locator FROM landing.evidence_artifact "
        "ORDER BY artifact_id"
    ).fetchall() == [
        ("copy-artifact", "backup/volume"),
        ("source-artifact", "source/volume"),
    ]


def test_evidence_and_assertion_history_is_append_only(target: _Target) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)

    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "UPDATE landing.evidence_artifact SET byte_size = 99 WHERE artifact_id = %s",
        (values["artifact_id"],),
    )
    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "DELETE FROM knowledge.source_assertion WHERE assertion_id = %s",
        (values["assertion_id"],),
    )
    assert connection.execute(
        "SELECT byte_size FROM landing.evidence_artifact WHERE artifact_id = %s",
        (values["artifact_id"],),
    ).fetchone() == (12,)


def test_operational_run_and_source_identity_metadata_can_progress(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)
    later = NOW.replace(hour=18)

    connection.execute(
        "UPDATE landing.parser_run SET finished_at = %s WHERE parse_run_id = %s",
        (later, values["parse_run_id"]),
    )
    connection.execute(
        "UPDATE knowledge.source_identity SET last_observed_at = %s "
        "WHERE source_identity_id = %s",
        (later, values["source_identity_id"]),
    )

    assert connection.execute(
        "SELECT finished_at FROM landing.parser_run WHERE parse_run_id = %s",
        (values["parse_run_id"],),
    ).fetchone() == (later,)
    assert connection.execute(
        "SELECT last_observed_at FROM knowledge.source_identity "
        "WHERE source_identity_id = %s",
        (values["source_identity_id"],),
    ).fetchone() == (later,)


def test_identity_reversal_adds_history_and_requires_same_release_parent(
    target: _Target,
) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_policy(connection, "identity-policy", "identity")
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES ('release-r1', 'merge-1', 'merge', 'identity-policy', 'v1', "
        "'human_review', 'identity-v1', 'build-r1', 0.98, 'merge evidence', %s)",
        (NOW,),
    )
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "reversal_of_decision_id) "
        "VALUES ('release-r1', 'reverse-1', 'reverse', 'identity-policy', 'v1', "
        "'human_review', 'identity-v1', 'build-r1', 1.0, 'split reviewed', %s, 'merge-1')",
        (NOW,),
    )

    assert target.connection.execute(
        "SELECT decision_id, action, reversal_of_decision_id "
        "FROM knowledge.identity_decision WHERE release_id = 'release-r1' "
        "ORDER BY decision_id"
    ).fetchall() == [
        ("merge-1", "merge", None),
        ("reverse-1", "reverse", "merge-1"),
    ]
    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "reversal_of_decision_id) "
        "VALUES ('release-r1', 'reverse-missing', 'reverse', 'identity-policy', 'v1', "
        "'human_review', 'identity-v1', 'build-r1', 1.0, 'missing parent', %s, "
        "'merge-does-not-exist')",
        (NOW,),
    )
    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "UPDATE knowledge.identity_decision SET rationale = 'rewritten' "
        "WHERE release_id = 'release-r1' AND decision_id = 'merge-1'",
    )


def test_canonical_relationship_endpoints_cannot_cross_release_scope(
    target: _Target,
) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_release(connection, "release-r2")
    _insert_policy(connection, "relationship-policy", "relationship")
    _insert_identity(connection, "release-r1", "professor-c1", "professor")
    _insert_identity(connection, "release-r2", "company-c1", "company")
    connection.execute(
        "INSERT INTO knowledge.relationship_type "
        "(relationship_type_id, version, layer, source_entity_types, target_entity_types, "
        "direction, roles, required_evidence_kinds, time_semantics, allowed_states, "
        "eligible_paths) VALUES ('professor_founded_company', 'v1', 'canonical', "
        "%s, %s, 'directed', '[]'::jsonb, %s, 'validity_interval', %s, %s)",
        (
            Jsonb(["professor"]),
            Jsonb(["company"]),
            Jsonb(["official_site"]),
            Jsonb(["accepted", "rejected"]),
            Jsonb(["relationship_traversal"]),
        ),
    )

    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES ('release-r1', 'relation-cross-release', 'canonical-relation-1', "
        "'professor_founded_company', 'v1', 'professor-c1', 'company-c1', 'accepted', "
        "'relationship-policy', 'v1', 'human_review', 'relation-v1', 'build-r1', "
        "0.9, 'must fail cross release', %s)",
        (NOW,),
    )
    _insert_identity(connection, "release-r1", "company-c1", "company")
    connection.execute(
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES ('release-r1', 'relation-valid', 'canonical-relation-1', "
        "'professor_founded_company', 'v1', 'professor-c1', 'company-c1', 'accepted', "
        "'relationship-policy', 'v1', 'human_review', 'relation-v1', 'build-r1', "
        "0.9, 'same release', %s)",
        (NOW,),
    )
    assert connection.execute(
        "SELECT release_id FROM knowledge.relationship_decision "
        "WHERE decision_id = 'relation-valid'"
    ).fetchone() == ("release-r1",)


def test_active_release_pointer_cannot_mix_versions_and_transaction_rolls_back(
    target: _Target,
) -> None:
    connection = target.connection
    _insert_release(connection, "release-r0")
    _insert_release(connection, "release-r1", previous_release_id="release-r0")
    _insert_release(connection, "release-r2", previous_release_id="release-r1")
    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO publish.build_manifest "
        "(release_id, manifest_version, build_run_id, source_batch_ids, "
        "source_batches_sha256, parser_versions, policy_versions, model_versions, "
        "manifest_sha256, created_at) VALUES ('release-r2', 'v1', 'build-release-r2', "
        "'[]'::jsonb, %s, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, %s)",
        (
            _fingerprint("batches:release-r2"),
            _fingerprint("wrong-manifest:release-r2"),
            NOW,
        ),
    )
    for release_id in ("release-r0", "release-r1"):
        connection.execute(
            "INSERT INTO publish.build_manifest "
            "(release_id, manifest_version, build_run_id, source_batch_ids, "
            "source_batches_sha256, parser_versions, policy_versions, model_versions, "
            "manifest_sha256, created_at) VALUES (%s, 'v1', %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                release_id,
                f"build-{release_id}",
                Jsonb(["batch-1"]),
                _fingerprint(f"batches:{release_id}"),
                Jsonb({"jsonl": "v1"}),
                Jsonb({"identity": "v1"}),
                Jsonb({}),
                _fingerprint(f"manifest:{release_id}"),
                NOW,
            ),
        )
    connection.execute(
        "INSERT INTO publish.active_release "
        "(singleton, release_id, canonical_release_id, published_projection_release_id, "
        "index_release_id, previous_release_id, changed_at) "
        "VALUES (TRUE, 'release-r0', 'release-r0', 'release-r0', 'release-r0', NULL, %s)",
        (NOW,),
    )

    _assert_database_error(
        connection,
        errors.CheckViolation,
        "UPDATE publish.active_release SET index_release_id = 'release-r1' "
        "WHERE singleton = TRUE",
    )
    connection.execute("SAVEPOINT rollback_rehearsal")
    connection.execute(
        "UPDATE publish.active_release SET release_id = 'release-r1', "
        "canonical_release_id = 'release-r1', "
        "published_projection_release_id = 'release-r1', "
        "index_release_id = 'release-r1', previous_release_id = 'release-r0', "
        "changed_at = %s WHERE singleton = TRUE",
        (NOW,),
    )
    assert connection.execute(
        "SELECT release_id FROM publish.active_release WHERE singleton = TRUE"
    ).fetchone() == ("release-r1",)
    connection.execute("ROLLBACK TO SAVEPOINT rollback_rehearsal")
    connection.execute("RELEASE SAVEPOINT rollback_rehearsal")
    assert connection.execute(
        "SELECT release_id FROM publish.active_release WHERE singleton = TRUE"
    ).fetchone() == ("release-r0",)
    assert connection.execute(
        "SELECT count(*) FROM publish.build_manifest"
    ).fetchone() == (2,)


def test_zz_c2_0002_downgrades_to_empty_baseline_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert expected_database == EXPECTED_DATABASE
    assert target_kind == "disposable"
    _prepare_environment(monkeypatch)
    config = _migration_config(
        database_url,
        expected_database,
        target_kind,
        backup_gate_root,
    )
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_revision(EXPECTED_REVISION) is not None
    command.upgrade(config, "head")
    command.downgrade(config, "C2_0001")
    connection = psycopg.connect(_psycopg_dsn(database_url), autocommit=False)
    try:
        _verify_target(connection)
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0001",)
        schemas = {
            row[0]
            for row in connection.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = ANY(%s)",
                (list(BUSINESS_SCHEMAS),),
            ).fetchall()
        }
        assert schemas == BUSINESS_SCHEMAS
        shared_tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('landing', 'knowledge', 'publish')"
        ).fetchall()
        assert shared_tables == []
    finally:
        connection.rollback()
        connection.close()

    command.upgrade(config, "head")
    verify_connection = psycopg.connect(_psycopg_dsn(database_url), autocommit=False)
    try:
        _verify_target(verify_connection)
        assert verify_connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (scripts.get_current_head(),)
    finally:
        verify_connection.rollback()
        verify_connection.close()
