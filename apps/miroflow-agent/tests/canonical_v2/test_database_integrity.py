from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, LiteralString

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import errors, sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0006"
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
    ("landing", "ingest_run"),
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
    ("knowledge", "canonical_decision_constraint_outcome"),
    ("knowledge", "canonical_decision_identity_context"),
    ("knowledge", "relationship_type"),
    ("knowledge", "relationship_assertion"),
    ("knowledge", "relationship_decision"),
    ("knowledge", "relationship_decision_assertion"),
    ("knowledge", "relationship_decision_constraint_outcome"),
    ("knowledge", "relationship_decision_identity_context"),
    ("knowledge", "identity_resolution_run"),
    ("knowledge", "identity_candidate_verdict"),
    ("knowledge", "identity_decision_context"),
    ("knowledge", "identity_decision_assertion"),
    ("knowledge", "canonical_identity_source_membership"),
    ("knowledge", "identity_decision_output_source"),
    ("knowledge", "canonical_identity_lineage"),
    ("knowledge", "current_source_identity_assignment"),
    ("publish", "build_manifest"),
    ("publish", "manifest_section"),
    ("publish", "active_release"),
}
EXPECTED_TASK_5_2_COLUMNS = {
    "identity_resolution_run": {
        "release_id",
        "decision_run_id",
        "identity_method_version",
        "as_of",
        "policy_id",
        "policy_version",
        "build_authority",
        "request_content",
        "request_content_sha256",
        "result_content",
        "result_content_sha256",
        "created_at",
    },
    "identity_candidate_verdict": {
        "release_id",
        "decision_run_id",
        "verdict_id",
        "verdict",
        "method",
        "confidence",
        "verdict_content",
        "content_sha256",
    },
    "identity_decision_context": {
        "release_id",
        "decision_id",
        "decision_run_id",
        "candidate_verdict_id",
        "context_content",
        "content_sha256",
        "supporting_assertion_ids",
    },
    "identity_decision_assertion": {
        "release_id",
        "decision_id",
        "assertion_id",
        "source_identity_id",
        "source_record_id",
    },
    "canonical_identity_source_membership": {
        "release_id",
        "canonical_identity_id",
        "source_identity_id",
    },
    "identity_decision_output_source": {
        "release_id",
        "decision_id",
        "canonical_identity_id",
        "source_identity_id",
    },
    "canonical_identity_lineage": {
        "release_id",
        "decision_id",
        "predecessor_identity_id",
        "successor_identity_id",
        "transition",
    },
    "current_source_identity_assignment": {
        "release_id",
        "source_identity_id",
        "canonical_identity_id",
        "identity_decision_id",
    },
    "source_assertion": {
        "assertion_id",
        "source_record_id",
        "source_identity_id",
        "subject_entity_type",
        "field_path",
        "value",
        "assertion_fingerprint_sha256",
        "observed_at",
        "source_event_time",
        "valid_from",
        "valid_to",
        "assertion_run_id",
    },
    "identity_decision": {
        "release_id",
        "decision_id",
        "action",
        "policy_id",
        "policy_version",
        "method",
        "method_version",
        "decision_run_id",
        "confidence",
        "rationale",
        "decided_at",
        "reversal_of_decision_id",
        "llm_trace",
    },
    "canonical_decision": {
        "release_id",
        "decision_id",
        "canonical_identity_id",
        "field_path",
        "state",
        "policy_id",
        "policy_version",
        "method",
        "method_version",
        "decision_run_id",
        "confidence",
        "rationale",
        "decided_at",
        "supersedes_decision_id",
        "llm_trace",
    },
    "canonical_decision_assertion": {
        "release_id",
        "decision_id",
        "assertion_id",
        "assertion_role",
    },
    "canonical_decision_constraint_outcome": {
        "release_id",
        "decision_id",
        "assertion_id",
        "admitted",
        "reason_codes",
    },
    "canonical_decision_identity_context": {
        "release_id",
        "decision_id",
        "canonical_identity_contexts",
        "source_identity_contexts",
        "content_sha256",
    },
    "relationship_assertion": {
        "assertion_id",
        "relationship_type_id",
        "relationship_type_version",
        "source_record_id",
        "source_identity_id",
        "target_identity_id",
        "attributes",
        "assertion_fingerprint_sha256",
        "observed_at",
        "source_event_time",
        "valid_from",
        "valid_to",
        "assertion_run_id",
    },
    "relationship_decision": {
        "release_id",
        "decision_id",
        "canonical_relationship_id",
        "relationship_type_id",
        "relationship_type_version",
        "source_canonical_identity_id",
        "target_canonical_identity_id",
        "state",
        "role_bindings",
        "policy_id",
        "policy_version",
        "method",
        "method_version",
        "decision_run_id",
        "confidence",
        "rationale",
        "valid_from",
        "valid_to",
        "decided_at",
        "supersedes_decision_id",
        "llm_trace",
    },
    "relationship_decision_assertion": {
        "release_id",
        "decision_id",
        "assertion_id",
        "assertion_role",
    },
    "relationship_decision_constraint_outcome": {
        "release_id",
        "decision_id",
        "assertion_id",
        "admitted",
        "reason_codes",
    },
    "relationship_decision_identity_context": {
        "release_id",
        "decision_id",
        "canonical_identity_contexts",
        "source_identity_contexts",
        "content_sha256",
    },
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
    set_alembic_database_url(config, database_url)
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
    expected_database = os.environ["CANONICAL_V2_TEST_EXPECTED_DATABASE"]
    target_kind = os.environ["CANONICAL_V2_TEST_TARGET_KIND"]
    assert actual_database == expected_database
    assert marker == (
        f"miroflow:destructive-target:v1:{target_kind}:{expected_database}"
    )
    connection.rollback()


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
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
    statement: LiteralString | sql.SQL | sql.Composed,
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
        "record_ordinal, parse_status, payload, parsed_at) "
        "VALUES (%s, %s, 'batch-1', 'line:1', %s, 0, 'parsed', %s, %s)",
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


def _insert_relationship_type(connection: psycopg.Connection[Any]) -> None:
    connection.execute(
        "INSERT INTO knowledge.relationship_type "
        "(relationship_type_id, version, layer, source_entity_types, target_entity_types, "
        "direction, roles, required_evidence_kinds, time_semantics, allowed_states, "
        "eligible_paths) VALUES ('professor_founded_company', 'v1', 'canonical', "
        "%s, %s, 'directed', '[]'::jsonb, %s, 'validity_interval', %s, %s) "
        "ON CONFLICT DO NOTHING",
        (
            Jsonb(["professor"]),
            Jsonb(["company"]),
            Jsonb(["official_site"]),
            Jsonb(["accepted", "rejected"]),
            Jsonb(["relationship_traversal"]),
        ),
    )


def _llm_trace(raw_output: bytes | None = None) -> dict[str, Any]:
    raw = raw_output or b'{"selected_assertion_ids":["assertion-1"],"state":"selected"}'
    return {
        "provider": "recorded-fake",
        "model": "canonical-judge-v1",
        "prompt_version": "prompt-v1",
        "schema_version": "decision-v1",
        "input_evidence_ids": ["assertion-1"],
        "raw_output_base64": base64.b64encode(raw).decode("ascii"),
        "output_sha256": hashlib.sha256(raw).hexdigest(),
        "validated_output": json.loads(raw),
    }


def _insert_decision_test_graph(
    connection: psycopg.Connection[Any],
) -> dict[str, str]:
    release_id = "decision-release-r1"
    _insert_release(connection, release_id, state="candidate")
    values = _insert_artifact_graph(connection)
    connection.execute(
        "INSERT INTO knowledge.source_identity "
        "(source_identity_id, source_system, source_key, entity_type, normalized_keys, "
        "first_observed_at, last_observed_at, state) VALUES "
        "('source-professor-1', 'official_profile', 'professor:1', 'professor', "
        "%s, %s, %s, 'active')",
        (Jsonb({"name": "professor one"}), NOW, NOW),
    )
    connection.execute(
        "INSERT INTO knowledge.source_identity_record (source_identity_id, record_id) "
        "VALUES ('source-professor-1', %s)",
        (values["record_id"],),
    )
    connection.execute(
        "INSERT INTO knowledge.source_assertion "
        "(assertion_id, source_record_id, source_identity_id, subject_entity_type, "
        "field_path, value, assertion_fingerprint_sha256, observed_at, assertion_run_id) "
        "VALUES ('assertion-2', %s, %s, 'company', 'name', %s, %s, %s, "
        "'assert-run-1')",
        (
            values["record_id"],
            values["source_identity_id"],
            Jsonb("Example Technology"),
            _fingerprint("assertion-2"),
            NOW,
        ),
    )
    _insert_identity(connection, release_id, "professor-c1", "professor")
    _insert_identity(connection, release_id, "company-c1", "company")
    _insert_policy(connection, "field-policy", "field_selection")
    _insert_policy(connection, "relationship-policy", "relationship")
    _insert_relationship_type(connection)
    for assertion_id, role in (
        ("relation-assertion-1", "founder"),
        ("relation-assertion-2", "advisor"),
    ):
        connection.execute(
            "INSERT INTO knowledge.relationship_assertion "
            "(assertion_id, relationship_type_id, relationship_type_version, "
            "source_record_id, source_identity_id, target_identity_id, attributes, "
            "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
            "VALUES (%s, 'professor_founded_company', 'v1', %s, "
            "'source-professor-1', %s, %s, %s, %s, 'assert-run-1')",
            (
                assertion_id,
                values["record_id"],
                values["source_identity_id"],
                Jsonb({"role": role}),
                _fingerprint(assertion_id),
                NOW,
            ),
        )
    return {
        **values,
        "release_id": release_id,
        "field_decision_id": "field-decision-1",
        "relationship_decision_id": "relationship-decision-1",
    }


def _insert_field_and_relationship_decisions(
    connection: psycopg.Connection[Any],
    values: dict[str, str],
) -> None:
    connection.execute(
        "INSERT INTO knowledge.canonical_decision "
        "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
        "policy_version, method, method_version, decision_run_id, confidence, rationale, "
        "decided_at) VALUES (%s, %s, 'company-c1', 'name', 'selected', "
        "'field-policy', 'v1', 'deterministic', 'field-v1', 'decision-run-1', 1.0, "
        "'deterministic field selection', %s)",
        (values["release_id"], values["field_decision_id"], NOW),
    )
    connection.execute(
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, role_bindings, policy_id, policy_version, "
        "method, method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES (%s, %s, 'canonical-relationship-1', 'professor_founded_company', "
        "'v1', 'professor-c1', 'company-c1', 'accepted', %s, "
        "'relationship-policy', 'v1', 'deterministic', 'relationship-v1', "
        "'decision-run-1', 1.0, 'deterministic relationship selection', %s)",
        (
            values["release_id"],
            values["relationship_decision_id"],
            Jsonb({"source": "founder"}),
            NOW,
        ),
    )


def _insert_structured_llm_decision(
    connection: psycopg.Connection[Any],
    *,
    decision_kind: str,
    decision_id: str,
    trace: dict[str, Any],
    release_id: str,
) -> None:
    if decision_kind == "identity":
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "llm_trace) VALUES (%s, %s, 'reject', 'identity-policy', 'v1', "
            "'structured_llm', 'identity-v1', 'decision-run-1', 0.8, "
            "'structured identity decision', %s, %s)",
            (release_id, decision_id, NOW, Jsonb(trace)),
        )
        return
    if decision_kind == "field":
        connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at, llm_trace) VALUES "
            "(%s, %s, 'company-c1', %s, 'selected', 'field-policy', 'v1', "
            "'structured_llm', 'field-v1', 'decision-run-1', 0.8, "
            "'structured field decision', %s, %s)",
            (release_id, decision_id, f"field.{decision_id}", NOW, Jsonb(trace)),
        )
        return
    if decision_kind == "relationship":
        connection.execute(
            "INSERT INTO knowledge.relationship_decision "
            "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
            "relationship_type_version, source_canonical_identity_id, "
            "target_canonical_identity_id, state, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "llm_trace) VALUES (%s, %s, %s, 'professor_founded_company', 'v1', "
            "'professor-c1', 'company-c1', 'accepted', 'relationship-policy', 'v1', "
            "'structured_llm', 'relationship-v1', 'decision-run-1', 0.8, "
            "'structured relationship decision', %s, %s)",
            (release_id, decision_id, f"relationship-{decision_id}", NOW, Jsonb(trace)),
        )
        return
    raise AssertionError(f"unsupported decision kind: {decision_kind}")


def test_current_head_and_exact_storage_inventory_exist(target: _Target) -> None:
    scripts = ScriptDirectory.from_config(target.config)
    assert scripts.get_revision(EXPECTED_REVISION) is not None
    assert target.connection.execute(
        "SELECT version_num FROM public.canonical_v2_alembic_version"
    ).fetchone() == (scripts.get_current_head(),)
    rows = target.connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema = ANY(%s)",
        (sorted(BUSINESS_SCHEMAS),),
    ).fetchall()
    assert {(row[0], row[1]) for row in rows} == EXPECTED_SHARED_TABLES
    public_tables = target.connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert {row[0] for row in public_tables} == {"canonical_v2_alembic_version"}

    column_rows = target.connection.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'knowledge' AND table_name = ANY(%s)",
        (sorted(EXPECTED_TASK_5_2_COLUMNS),),
    ).fetchall()
    actual_columns = {
        table_name: {
            column_name
            for row_table_name, column_name in column_rows
            if row_table_name == table_name
        }
        for table_name in EXPECTED_TASK_5_2_COLUMNS
    }
    assert actual_columns == EXPECTED_TASK_5_2_COLUMNS


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
        "record_ordinal, parse_status, payload, parsed_at) "
        "VALUES ('orphan-record', 'missing-artifact', 'batch-1', 'line:2', "
        "'missing-run', 1, 'parsed', '{}'::jsonb, %s)",
        (NOW,),
    )
    _assert_database_error(
        connection,
        errors.UniqueViolation,
        "INSERT INTO landing.source_record "
        "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
        "record_ordinal, parse_status, payload, parsed_at) "
        "VALUES ('record-replay', %s, 'batch-1', 'line:1', %s, 1, 'parsed', "
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


def test_operational_metadata_cannot_rewrite_or_delete_history(target: _Target) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)
    connection.execute(
        "INSERT INTO landing.parser_run "
        "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
        "run_status, started_at) VALUES ('parse-run-unused', %s, 'jsonl', "
        "'parser-v1', 'company-v1', 'running', %s)",
        (values["artifact_id"], NOW),
    )
    connection.execute(
        "INSERT INTO knowledge.source_identity "
        "(source_identity_id, source_system, source_key, entity_type, normalized_keys, "
        "first_observed_at, last_observed_at, state) VALUES ('source-unused', "
        "'historical_jsonl', 'line:unused', 'company', '{}'::jsonb, %s, %s, 'active')",
        (NOW, NOW),
    )

    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "UPDATE landing.parser_run SET parser_version = 'rewritten' "
        "WHERE parse_run_id = 'parse-run-unused'",
    )
    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "UPDATE knowledge.source_identity SET source_key = 'rewritten' "
        "WHERE source_identity_id = 'source-unused'",
    )
    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "DELETE FROM landing.parser_run WHERE parse_run_id = 'parse-run-unused'",
    )
    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "DELETE FROM knowledge.source_identity WHERE source_identity_id = 'source-unused'",
    )


def test_identity_reversal_adds_history_and_requires_an_existing_parent(
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
    _insert_relationship_type(connection)

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


def test_artifact_parent_hash_must_match_the_referenced_parent(target: _Target) -> None:
    connection = target.connection
    connection.execute(
        "INSERT INTO landing.evidence_artifact "
        "(artifact_id, source_kind, source_locator, content_sha256, byte_size, acquired_at, run_id) "
        "VALUES ('parent-artifact', 'forensic_source', 'source/parent', %s, 12, %s, 'copy-run-1')",
        (_fingerprint("parent-bytes"), NOW),
    )

    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO landing.evidence_artifact "
        "(artifact_id, source_kind, source_locator, content_sha256, byte_size, acquired_at, run_id, "
        "parent_artifact_id, parent_content_sha256) "
        "VALUES ('child-artifact', 'verified_copy', 'backup/child', %s, 12, %s, 'copy-run-1', "
        "'parent-artifact', %s)",
        (_fingerprint("child-bytes"), NOW, _fingerprint("not-the-parent-bytes")),
    )


def test_assertion_identity_must_be_linked_to_its_source_record(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)
    connection.execute(
        "INSERT INTO knowledge.source_identity "
        "(source_identity_id, source_system, source_key, entity_type, normalized_keys, "
        "first_observed_at, last_observed_at, state) "
        "VALUES ('source-company-unlinked', 'other-source', 'row:99', 'company', "
        "'{}'::jsonb, %s, %s, 'active')",
        (NOW, NOW),
    )

    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO knowledge.source_assertion "
        "(assertion_id, source_record_id, source_identity_id, subject_entity_type, "
        "field_path, value, assertion_fingerprint_sha256, observed_at, assertion_run_id) "
        "VALUES ('assertion-unlinked', %s, 'source-company-unlinked', 'company', "
        "'name', %s, %s, %s, 'assert-run-review')",
        (
            values["record_id"],
            Jsonb("Other"),
            _fingerprint("assertion-unlinked"),
            NOW,
        ),
    )


def test_relationship_endpoints_must_be_linked_to_the_evidence_record(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_artifact_graph(connection)
    connection.execute(
        "INSERT INTO knowledge.source_identity "
        "(source_identity_id, source_system, source_key, entity_type, normalized_keys, "
        "first_observed_at, last_observed_at, state) "
        "VALUES ('source-company-unlinked', 'other-source', 'row:99', 'company', "
        "'{}'::jsonb, %s, %s, 'active')",
        (NOW, NOW),
    )
    _insert_relationship_type(connection)

    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO knowledge.relationship_assertion "
        "(assertion_id, relationship_type_id, relationship_type_version, source_record_id, "
        "source_identity_id, target_identity_id, attributes, assertion_fingerprint_sha256, "
        "observed_at, assertion_run_id) VALUES ('relation-assertion-unlinked', "
        "'professor_founded_company', 'v1', %s, %s, 'source-company-unlinked', "
        "'{}'::jsonb, %s, %s, 'assert-run-review')",
        (
            values["record_id"],
            values["source_identity_id"],
            _fingerprint("relation-assertion-unlinked"),
            NOW,
        ),
    )


def test_append_only_history_rejects_bulk_truncate(target: _Target) -> None:
    connection = target.connection
    _insert_artifact_graph(connection)

    _assert_database_error(
        connection,
        errors.ObjectNotInPrerequisiteState,
        "TRUNCATE landing.evidence_artifact CASCADE",
    )


def test_identity_reversal_can_reference_a_previous_release_decision(
    target: _Target,
) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_release(connection, "release-r2", previous_release_id="release-r1")
    _insert_policy(connection, "identity-policy", "identity")
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES ('release-r1', 'merge-r1', 'merge', 'identity-policy', 'v1', "
        "'human_review', 'identity-v1', 'build-r1', 0.98, 'merge evidence', %s)",
        (NOW,),
    )
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "reversal_of_decision_id) VALUES ('release-r2', 'reverse-r2', 'reverse', "
        "'identity-policy', 'v1', 'human_review', 'identity-v1', 'build-r2', 1.0, "
        "'reviewed reversal', %s, 'merge-r1')",
        (NOW,),
    )

    assert connection.execute(
        "SELECT reversal_of_decision_id FROM knowledge.identity_decision "
        "WHERE release_id = 'release-r2' AND decision_id = 'reverse-r2'"
    ).fetchone() == ("merge-r1",)


def test_identity_reversal_cannot_reference_itself(target: _Target) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_policy(connection, "identity-policy", "identity")
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "reversal_of_decision_id) VALUES ('release-r1', 'reverse-self', 'reverse', "
        "'identity-policy', 'v1', 'human_review', 'identity-v1', 'build-r1', 1.0, "
        "'invalid self reversal', %s, 'reverse-self')",
        (NOW,),
    )


def test_field_decision_can_supersede_a_previous_release_decision(
    target: _Target,
) -> None:
    connection = target.connection
    for release_id in ("release-r1", "release-r2"):
        _insert_release(
            connection,
            release_id,
            previous_release_id="release-r1" if release_id == "release-r2" else None,
        )
        _insert_identity(connection, release_id, "company-c1", "company")
    _insert_policy(connection, "field-policy", "field_selection")
    connection.execute(
        "INSERT INTO knowledge.canonical_decision "
        "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
        "policy_version, method, method_version, decision_run_id, confidence, rationale, "
        "decided_at) VALUES ('release-r1', 'field-r1', 'company-c1', 'name', 'selected', "
        "'field-policy', 'v1', 'deterministic', 'field-v1', 'build-r1', 1.0, "
        "'first selection', %s)",
        (NOW,),
    )
    connection.execute(
        "INSERT INTO knowledge.canonical_decision "
        "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
        "policy_version, method, method_version, decision_run_id, confidence, rationale, "
        "decided_at, supersedes_decision_id) VALUES ('release-r2', 'field-r2', "
        "'company-c1', 'name', 'selected', 'field-policy', 'v1', 'human_review', "
        "'field-v1', 'build-r2', 0.99, 'updated selection', %s, 'field-r1')",
        (NOW,),
    )

    assert connection.execute(
        "SELECT supersedes_decision_id FROM knowledge.canonical_decision "
        "WHERE release_id = 'release-r2' AND decision_id = 'field-r2'"
    ).fetchone() == ("field-r1",)


def test_field_decision_cannot_supersede_itself(target: _Target) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_identity(connection, "release-r1", "company-c1", "company")
    _insert_policy(connection, "field-policy", "field_selection")
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.canonical_decision "
        "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
        "policy_version, method, method_version, decision_run_id, confidence, rationale, "
        "decided_at, supersedes_decision_id) VALUES ('release-r1', 'field-self', "
        "'company-c1', 'name', 'selected', 'field-policy', 'v1', 'human_review', "
        "'field-v1', 'build-r1', 0.99, 'invalid self supersession', %s, 'field-self')",
        (NOW,),
    )


def test_field_supersession_cannot_cross_identity_or_field(target: _Target) -> None:
    connection = target.connection
    for release_id in ("release-r1", "release-r2"):
        _insert_release(
            connection,
            release_id,
            previous_release_id="release-r1" if release_id == "release-r2" else None,
        )
        _insert_identity(connection, release_id, "company-c1", "company")
        _insert_identity(connection, release_id, "company-c2", "company")
    _insert_policy(connection, "field-policy", "field_selection")
    connection.execute(
        "INSERT INTO knowledge.canonical_decision "
        "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
        "policy_version, method, method_version, decision_run_id, confidence, rationale, "
        "decided_at) VALUES ('release-r1', 'field-r1', 'company-c1', 'name', 'selected', "
        "'field-policy', 'v1', 'deterministic', 'field-v1', 'build-r1', 1.0, "
        "'first selection', %s)",
        (NOW,),
    )
    for decision_id, identity_id, field_path in (
        ("field-wrong-identity", "company-c2", "name"),
        ("field-wrong-path", "company-c1", "address"),
    ):
        _assert_database_error(
            connection,
            errors.ForeignKeyViolation,
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, policy_id, "
            "policy_version, method, method_version, decision_run_id, confidence, rationale, "
            "decided_at, supersedes_decision_id) VALUES ('release-r2', %s, %s, %s, "
            "'selected', 'field-policy', 'v1', 'human_review', 'field-v1', 'build-r2', "
            "0.99, 'invalid lineage subject', %s, 'field-r1')",
            (decision_id, identity_id, field_path, NOW),
        )


def test_relationship_decision_can_supersede_a_previous_release_decision(
    target: _Target,
) -> None:
    connection = target.connection
    for release_id in ("release-r1", "release-r2"):
        _insert_release(
            connection,
            release_id,
            previous_release_id="release-r1" if release_id == "release-r2" else None,
        )
        _insert_identity(connection, release_id, "professor-c1", "professor")
        _insert_identity(connection, release_id, "company-c1", "company")
    _insert_policy(connection, "relationship-policy", "relationship")
    _insert_relationship_type(connection)
    for release_id, decision_id, supersedes in (
        ("release-r1", "relation-r1", None),
        ("release-r2", "relation-r2", "relation-r1"),
    ):
        connection.execute(
            "INSERT INTO knowledge.relationship_decision "
            "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
            "relationship_type_version, source_canonical_identity_id, "
            "target_canonical_identity_id, state, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "supersedes_decision_id) VALUES (%s, %s, 'canonical-relation-1', "
            "'professor_founded_company', 'v1', 'professor-c1', 'company-c1', "
            "'accepted', 'relationship-policy', 'v1', 'human_review', 'relation-v1', "
            "%s, 0.95, 'reviewed relationship', %s, %s)",
            (
                release_id,
                decision_id,
                f"build-{release_id}",
                NOW,
                supersedes,
            ),
        )

    assert connection.execute(
        "SELECT supersedes_decision_id FROM knowledge.relationship_decision "
        "WHERE release_id = 'release-r2' AND decision_id = 'relation-r2'"
    ).fetchone() == ("relation-r1",)


def test_relationship_decision_cannot_supersede_itself(target: _Target) -> None:
    connection = target.connection
    _insert_release(connection, "release-r1")
    _insert_identity(connection, "release-r1", "professor-c1", "professor")
    _insert_identity(connection, "release-r1", "company-c1", "company")
    _insert_policy(connection, "relationship-policy", "relationship")
    _insert_relationship_type(connection)
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "supersedes_decision_id) VALUES ('release-r1', 'relation-self', "
        "'canonical-relation-1', 'professor_founded_company', 'v1', 'professor-c1', "
        "'company-c1', 'accepted', 'relationship-policy', 'v1', 'human_review', "
        "'relation-v1', 'build-r1', 0.95, 'invalid self supersession', %s, "
        "'relation-self')",
        (NOW,),
    )


def test_relationship_supersession_cannot_cross_logical_relationship(
    target: _Target,
) -> None:
    connection = target.connection
    for release_id in ("release-r1", "release-r2"):
        _insert_release(
            connection,
            release_id,
            previous_release_id="release-r1" if release_id == "release-r2" else None,
        )
        _insert_identity(connection, release_id, "professor-c1", "professor")
        _insert_identity(connection, release_id, "company-c1", "company")
    _insert_policy(connection, "relationship-policy", "relationship")
    _insert_relationship_type(connection)
    connection.execute(
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) VALUES "
        "('release-r1', 'relation-r1', 'canonical-relation-1', "
        "'professor_founded_company', 'v1', 'professor-c1', 'company-c1', 'accepted', "
        "'relationship-policy', 'v1', 'human_review', 'relation-v1', 'build-r1', "
        "0.95, 'first relationship decision', %s)",
        (NOW,),
    )
    _assert_database_error(
        connection,
        errors.ForeignKeyViolation,
        "INSERT INTO knowledge.relationship_decision "
        "(release_id, decision_id, canonical_relationship_id, relationship_type_id, "
        "relationship_type_version, source_canonical_identity_id, "
        "target_canonical_identity_id, state, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "supersedes_decision_id) VALUES ('release-r2', 'relation-wrong-subject', "
        "'canonical-relation-2', 'professor_founded_company', 'v1', 'professor-c1', "
        "'company-c1', 'accepted', 'relationship-policy', 'v1', 'human_review', "
        "'relation-v1', 'build-r2', 0.95, 'invalid lineage subject', %s, 'relation-r1')",
        (NOW,),
    )


def test_structured_llm_decisions_require_a_persisted_trace(target: _Target) -> None:
    connection = target.connection
    trace_columns = connection.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'knowledge' AND column_name = 'llm_trace' "
        "AND table_name = ANY(%s) ORDER BY table_name",
        (["identity_decision", "canonical_decision", "relationship_decision"],),
    ).fetchall()
    assert trace_columns == [
        ("canonical_decision",),
        ("identity_decision",),
        ("relationship_decision",),
    ]

    _insert_release(connection, "release-r1")
    _insert_policy(connection, "identity-policy", "identity")
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at) "
        "VALUES ('release-r1', 'llm-without-trace', 'create', 'identity-policy', 'v1', "
        "'structured_llm', 'identity-v1', 'build-r1', 0.8, 'model judgment', %s)",
        (NOW,),
    )
    connection.execute(
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, llm_trace) "
        "VALUES ('release-r1', 'llm-with-trace', 'create', 'identity-policy', 'v1', "
        "'structured_llm', 'identity-v1', 'build-r1', 0.8, 'model judgment', %s, %s)",
        (
            NOW,
            Jsonb(_llm_trace()),
        ),
    )


def test_hardened_llm_trace_is_content_bound_for_every_decision_family(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_decision_test_graph(connection)
    valid_raw = b'{"selected_assertion_ids":["assertion-1"],"state":"selected"}'
    valid_trace = _llm_trace(valid_raw)
    for decision_kind in ("identity", "field", "relationship"):
        _insert_structured_llm_decision(
            connection,
            decision_kind=decision_kind,
            decision_id=f"valid-trace-{decision_kind}",
            trace=valid_trace,
            release_id=values["release_id"],
        )

    invalid_utf8 = b"\xff"
    malformed_json = b"{not-json"
    non_object_json = b"[]"
    different_object = b'{"answer":1}'
    valid_encoded = base64.b64encode(valid_raw).decode("ascii")
    whitespace_encoded = valid_encoded[:12] + "\n" + valid_encoded[12:]
    padded_raw = b'{"answer":1}'
    noncanonical_padding = base64.b64encode(padded_raw).decode("ascii") + "="
    invalid_traces: tuple[dict[str, Any], ...] = (
        {
            key: value
            for key, value in valid_trace.items()
            if key != "raw_output_base64"
        },
        {key: value for key, value in valid_trace.items() if key != "validated_output"},
        {**valid_trace, "raw_output_base64": whitespace_encoded},
        {
            **valid_trace,
            "raw_output_base64": noncanonical_padding,
            "output_sha256": hashlib.sha256(padded_raw).hexdigest(),
            "validated_output": {"answer": 1},
        },
        {**valid_trace, "output_sha256": "0" * 64},
        {
            **valid_trace,
            "raw_output_base64": base64.b64encode(invalid_utf8).decode("ascii"),
            "output_sha256": hashlib.sha256(invalid_utf8).hexdigest(),
            "validated_output": {},
        },
        {
            **valid_trace,
            "raw_output_base64": base64.b64encode(malformed_json).decode("ascii"),
            "output_sha256": hashlib.sha256(malformed_json).hexdigest(),
            "validated_output": {},
        },
        {
            **valid_trace,
            "raw_output_base64": base64.b64encode(non_object_json).decode("ascii"),
            "output_sha256": hashlib.sha256(non_object_json).hexdigest(),
            "validated_output": {},
        },
        {
            **valid_trace,
            "raw_output_base64": base64.b64encode(different_object).decode("ascii"),
            "output_sha256": hashlib.sha256(different_object).hexdigest(),
            "validated_output": {"answer": 2},
        },
        *(
            {**valid_trace, field: " \t\n"}
            for field in (
                "provider",
                "model",
                "prompt_version",
                "schema_version",
            )
        ),
        *(
            {**valid_trace, field: f" {valid_trace[field]} "}
            for field in (
                "provider",
                "model",
                "prompt_version",
                "schema_version",
            )
        ),
        *(
            {**valid_trace, field: f"\v{valid_trace[field]}"}
            for field in (
                "provider",
                "model",
                "prompt_version",
                "schema_version",
            )
        ),
        *(
            {**valid_trace, field: f"{valid_trace[field]}\v"}
            for field in (
                "provider",
                "model",
                "prompt_version",
                "schema_version",
            )
        ),
        {
            **valid_trace,
            "input_evidence_ids": ["assertion-1", "assertion-1"],
        },
        {**valid_trace, "input_evidence_ids": [" x "]},
        {**valid_trace, "input_evidence_ids": ["x", " x "]},
        {**valid_trace, "input_evidence_ids": ["\vx"]},
        {**valid_trace, "input_evidence_ids": ["x\v"]},
        *(
            {
                **valid_trace,
                "raw_output_base64": base64.b64encode(
                    b'{"answer":' + literal + b"}"
                ).decode("ascii"),
                "output_sha256": hashlib.sha256(
                    b'{"answer":' + literal + b"}"
                ).hexdigest(),
                "validated_output": {},
            }
            for literal in (b"NaN", b"Infinity", b"-Infinity")
        ),
    )
    # JSONB collapses duplicate keys and rejects non-finite validated values before
    # a CHECK can compare them. The lossless typed trace seam owns duplicate-key
    # rejection; these raw non-finite forms still prove intrinsic DB rejection.
    for decision_kind in ("identity", "field", "relationship"):
        for index, invalid_trace in enumerate(invalid_traces):
            savepoint = f"invalid_trace_{decision_kind}_{index}"
            savepoint_identifier = sql.Identifier(savepoint)
            connection.execute(sql.SQL("SAVEPOINT {}").format(savepoint_identifier))
            try:
                with pytest.raises(psycopg.Error):
                    _insert_structured_llm_decision(
                        connection,
                        decision_kind=decision_kind,
                        decision_id=f"invalid-trace-{decision_kind}-{index}",
                        trace=invalid_trace,
                        release_id=values["release_id"],
                    )
            finally:
                connection.execute(
                    sql.SQL("ROLLBACK TO SAVEPOINT {}").format(savepoint_identifier)
                )
                connection.execute(
                    sql.SQL("RELEASE SAVEPOINT {}").format(savepoint_identifier)
                )

    assert connection.execute(
        "SELECT "
        "(SELECT count(*) FROM knowledge.identity_decision "
        " WHERE decision_id LIKE 'invalid-trace-%'), "
        "(SELECT count(*) FROM knowledge.canonical_decision "
        " WHERE decision_id LIKE 'invalid-trace-%'), "
        "(SELECT count(*) FROM knowledge.relationship_decision "
        " WHERE decision_id LIKE 'invalid-trace-%')"
    ).fetchone() == (0, 0, 0)


def test_selected_and_conflicting_roles_cannot_overlap_for_one_assertion(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_decision_test_graph(connection)
    _insert_field_and_relationship_decisions(connection, values)
    role_tables = (
        (
            "canonical_decision_assertion",
            values["field_decision_id"],
            values["assertion_id"],
            "assertion-2",
        ),
        (
            "relationship_decision_assertion",
            values["relationship_decision_id"],
            "relation-assertion-1",
            "relation-assertion-2",
        ),
    )
    for table, decision_id, selected_id, conflicting_id in role_tables:
        table_identifier = sql.Identifier("knowledge", table)
        connection.execute(
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, %s, %s, 'candidate'), (%s, %s, %s, 'selected')"
            ).format(table_identifier),
            (
                values["release_id"],
                decision_id,
                selected_id,
                values["release_id"],
                decision_id,
                selected_id,
            ),
        )
        _assert_database_error(
            connection,
            errors.UniqueViolation,
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, %s, %s, 'conflicting')"
            ).format(table_identifier),
            (values["release_id"], decision_id, selected_id),
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, %s, %s, 'candidate'), (%s, %s, %s, 'conflicting')"
            ).format(table_identifier),
            (
                values["release_id"],
                decision_id,
                conflicting_id,
                values["release_id"],
                decision_id,
                conflicting_id,
            ),
        )
        _assert_database_error(
            connection,
            errors.UniqueViolation,
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, %s, %s, 'selected')"
            ).format(table_identifier),
            (values["release_id"], decision_id, conflicting_id),
        )


def test_constraint_outcome_ledgers_are_linked_checked_and_append_only(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_decision_test_graph(connection)
    _insert_field_and_relationship_decisions(connection, values)
    expected_columns = {
        "release_id",
        "decision_id",
        "assertion_id",
        "admitted",
        "reason_codes",
    }
    for table_name in (
        "canonical_decision_constraint_outcome",
        "relationship_decision_constraint_outcome",
    ):
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'knowledge' AND table_name = %s",
                (table_name,),
            ).fetchall()
        }
        assert columns == expected_columns

    connection.execute(
        "INSERT INTO knowledge.canonical_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, %s, TRUE, %s)",
        (
            values["release_id"],
            values["field_decision_id"],
            values["assertion_id"],
            Jsonb([]),
        ),
    )
    connection.execute(
        "INSERT INTO knowledge.relationship_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, 'relation-assertion-1', FALSE, %s)",
        (
            values["release_id"],
            values["relationship_decision_id"],
            Jsonb(["identity_mismatch"]),
        ),
    )
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.canonical_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, 'assertion-2', TRUE, %s)",
        (
            values["release_id"],
            values["field_decision_id"],
            Jsonb(["must_be_empty_when_admitted"]),
        ),
    )
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.canonical_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, 'assertion-2', FALSE, %s)",
        (
            values["release_id"],
            values["field_decision_id"],
            Jsonb([]),
        ),
    )
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.relationship_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, 'relation-assertion-2', FALSE, %s)",
        (
            values["release_id"],
            values["relationship_decision_id"],
            Jsonb([]),
        ),
    )
    _assert_database_error(
        connection,
        errors.CheckViolation,
        "INSERT INTO knowledge.relationship_decision_constraint_outcome "
        "(release_id, decision_id, assertion_id, admitted, reason_codes) "
        "VALUES (%s, %s, 'relation-assertion-2', TRUE, %s)",
        (
            values["release_id"],
            values["relationship_decision_id"],
            Jsonb(["must_be_empty_when_admitted"]),
        ),
    )
    for table, decision_id, assertion_id in (
        (
            "canonical_decision_constraint_outcome",
            values["field_decision_id"],
            "assertion-2",
        ),
        (
            "relationship_decision_constraint_outcome",
            values["relationship_decision_id"],
            "relation-assertion-2",
        ),
    ):
        table_identifier = sql.Identifier("knowledge", table)
        for reason_codes in (
            [""],
            [" \t\n"],
            ["duplicate_reason", "duplicate_reason"],
            [" padded_reason "],
            ["x", " x "],
            ["\vreason"],
            ["reason\v"],
        ):
            _assert_database_error(
                connection,
                errors.CheckViolation,
                sql.SQL(
                    "INSERT INTO {} "
                    "(release_id, decision_id, assertion_id, admitted, reason_codes) "
                    "VALUES (%s, %s, %s, FALSE, %s)"
                ).format(table_identifier),
                (
                    values["release_id"],
                    decision_id,
                    assertion_id,
                    Jsonb(reason_codes),
                ),
            )
    for table, decision_id, assertion_id in (
        (
            "canonical_decision_constraint_outcome",
            values["field_decision_id"],
            "assertion-2",
        ),
        (
            "relationship_decision_constraint_outcome",
            values["relationship_decision_id"],
            "relation-assertion-2",
        ),
    ):
        table_identifier = sql.Identifier("knowledge", table)
        _assert_database_error(
            connection,
            errors.ForeignKeyViolation,
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, admitted, reason_codes) "
                "VALUES (%s, 'missing-decision', %s, FALSE, %s)"
            ).format(table_identifier),
            (values["release_id"], assertion_id, Jsonb(["missing_decision"])),
        )
        _assert_database_error(
            connection,
            errors.ForeignKeyViolation,
            sql.SQL(
                "INSERT INTO {} "
                "(release_id, decision_id, assertion_id, admitted, reason_codes) "
                "VALUES (%s, %s, 'missing-assertion', FALSE, %s)"
            ).format(table_identifier),
            (values["release_id"], decision_id, Jsonb(["missing_assertion"])),
        )

    for table in (
        "canonical_decision_constraint_outcome",
        "relationship_decision_constraint_outcome",
    ):
        table_identifier = sql.Identifier("knowledge", table)
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL(
                "UPDATE {} SET admitted = NOT admitted, "
                "reason_codes = '[\"rewritten\"]'::jsonb"
            ).format(table_identifier),
        )
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL("DELETE FROM {}").format(table_identifier),
        )
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL("TRUNCATE {}").format(table_identifier),
        )

    assert connection.execute(
        "SELECT admitted, reason_codes "
        "FROM knowledge.canonical_decision_constraint_outcome"
    ).fetchall() == [(True, [])]
    assert connection.execute(
        "SELECT admitted, reason_codes "
        "FROM knowledge.relationship_decision_constraint_outcome"
    ).fetchall() == [(False, ["identity_mismatch"])]


def test_decision_identity_context_snapshots_are_linked_and_append_only(
    target: _Target,
) -> None:
    connection = target.connection
    values = _insert_decision_test_graph(connection)
    _insert_field_and_relationship_decisions(connection, values)
    canonical_contexts = Jsonb([{"canonical_identity_id": "canonical-1"}])
    source_contexts = Jsonb([{"source_identity_id": "source-identity-1"}])
    snapshot_tables = (
        (
            "canonical_decision_identity_context",
            values["field_decision_id"],
        ),
        (
            "relationship_decision_identity_context",
            values["relationship_decision_id"],
        ),
    )
    for table, decision_id in snapshot_tables:
        table_identifier = sql.Identifier("knowledge", table)
        connection.execute(
            sql.SQL(
                "INSERT INTO {} (release_id, decision_id, "
                "canonical_identity_contexts, source_identity_contexts, "
                "content_sha256) VALUES (%s, %s, %s, %s, %s)"
            ).format(table_identifier),
            (
                values["release_id"],
                decision_id,
                canonical_contexts,
                source_contexts,
                _fingerprint(f"context:{decision_id}"),
            ),
        )
        _assert_database_error(
            connection,
            errors.ForeignKeyViolation,
            sql.SQL(
                "INSERT INTO {} (release_id, decision_id, "
                "canonical_identity_contexts, source_identity_contexts, "
                "content_sha256) VALUES (%s, 'missing-decision', %s, %s, %s)"
            ).format(table_identifier),
            (
                values["release_id"],
                canonical_contexts,
                source_contexts,
                _fingerprint("missing-context"),
            ),
        )
        for invalid_canonical, invalid_source, invalid_hash in (
            (Jsonb({}), source_contexts, _fingerprint("invalid-canonical")),
            (Jsonb([]), source_contexts, _fingerprint("empty-canonical")),
            (canonical_contexts, Jsonb({}), _fingerprint("invalid-source")),
            (canonical_contexts, Jsonb([]), _fingerprint("empty-source")),
            (canonical_contexts, source_contexts, "A" * 64),
        ):
            _assert_database_error(
                connection,
                errors.CheckViolation,
                sql.SQL(
                    "INSERT INTO {} (release_id, decision_id, "
                    "canonical_identity_contexts, source_identity_contexts, "
                    "content_sha256) VALUES (%s, %s, %s, %s, %s)"
                ).format(table_identifier),
                (
                    values["release_id"],
                    f"invalid-{table}-{invalid_hash[:8]}",
                    invalid_canonical,
                    invalid_source,
                    invalid_hash,
                ),
            )
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL("UPDATE {} SET content_sha256 = %s").format(table_identifier),
            (_fingerprint("rewrite"),),
        )
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL("DELETE FROM {}").format(table_identifier),
        )
        _assert_database_error(
            connection,
            errors.ObjectNotInPrerequisiteState,
            sql.SQL("TRUNCATE {}").format(table_identifier),
        )


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


def test_zz_shared_storage_downgrades_to_empty_baseline_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
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
