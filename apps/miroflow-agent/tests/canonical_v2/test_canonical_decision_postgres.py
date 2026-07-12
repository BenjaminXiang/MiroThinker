from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import inspect
import json
import os
from pathlib import Path
from threading import Event
import time
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import URL, make_url

from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0005"
RELEASE_ID = "decision-postgres-release-r1"
RUN_ID = "decision-postgres-run-1"
NOW = datetime(2026, 7, 11, 23, 30, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
    target_kind: str
    backup_gate_root: Path
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
            "Canonical V2 decision persistence requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _migration_config(target: _Target) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, target.database_url)
    config.set_main_option("miroflow.expected_database", target.expected_database)
    config.set_main_option("miroflow.target_kind", target.target_kind)
    config.set_main_option("miroflow.backup_gate_root", str(target.backup_gate_root))
    return config


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _connect(target: _Target, *, autocommit: bool = False) -> Any:
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def _verify_target(target: _Target) -> None:
    with _connect(target, autocommit=True) as connection:
        actual_database, marker = connection.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        assert actual_database == target.expected_database
        assert marker == (
            "miroflow:destructive-target:v1:"
            f"{target.target_kind}:{target.expected_database}"
        )
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)


def _sibling_database_url(database_url: str, database_name: str) -> str:
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def test_migration_config_accepts_rendered_sibling_socket_url_without_a_database() -> (
    None
):
    sibling_url = _sibling_database_url(
        URL.create(
            "postgresql+psycopg",
            username="probe",
            password="synthetic",
            database="base",
            query={"host": "/tmp/canonical-v2"},
        ).render_as_string(hide_password=False),
        "sibling",
    )
    target = _Target(
        database_url=sibling_url,
        expected_database="sibling",
        target_kind="disposable",
        backup_gate_root=Path("/synthetic"),
        config=Config(),
    )

    configured = _migration_config(target)

    configured_url = configured.get_main_option("sqlalchemy.url")
    assert configured_url is not None
    assert configured_url == sibling_url
    parsed = make_url(configured_url)
    assert parsed.database == "sibling"
    assert dict(parsed.query) == {"host": "/tmp/canonical-v2"}


def _drop_owned_sibling(
    connection: psycopg.Connection[Any],
    *,
    database_name: str,
    expected_marker: str,
) -> None:
    existing = connection.execute(
        "SELECT shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = %s",
        (database_name,),
    ).fetchone()
    if existing is None:
        return
    assert existing == (expected_marker,)
    connection.execute(
        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
    )


@pytest.fixture
def target(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert target_kind == "disposable"
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
    base_marker = f"miroflow:destructive-target:v1:{target_kind}:{expected_database}"
    sibling_name = (
        f"{expected_database[:42]}_s5b_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    sibling_marker = f"miroflow:destructive-target:v1:disposable:{sibling_name}"
    with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
        assert admin.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone() == (expected_database, base_marker)
        _drop_owned_sibling(
            admin,
            database_name=sibling_name,
            expected_marker=sibling_marker,
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(sibling_name))
        )
        admin.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(sibling_name),
                sql.Literal(sibling_marker),
            )
        )
    try:
        provisional = _Target(
            database_url=_sibling_database_url(database_url, sibling_name),
            expected_database=sibling_name,
            target_kind="disposable",
            backup_gate_root=Path(backup_gate_root),
            config=Config(),
        )
        configured = _Target(
            database_url=provisional.database_url,
            expected_database=provisional.expected_database,
            target_kind=provisional.target_kind,
            backup_gate_root=provisional.backup_gate_root,
            config=_migration_config(provisional),
        )
        command.upgrade(configured.config, EXPECTED_REVISION)
        _verify_target(configured)
        yield configured
    finally:
        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
            _drop_owned_sibling(
                admin,
                database_name=sibling_name,
                expected_marker=sibling_marker,
            )


def _engine_module() -> Any:
    return import_module("src.data_agents.canonical_v2.canonical_decision_engine")


def _postgres_module() -> Any:
    return import_module("src.data_agents.canonical_v2.canonical_decision_postgres")


def _store(target: _Target) -> Any:
    return _postgres_module().create_postgres_canonical_decision_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )


def _set_database_marker(target: _Target, marker: str) -> None:
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(target.expected_database),
                sql.Literal(marker),
            )
        )


def _policy(module: Any, kind: str, *, version: str = "v1") -> Any:
    return module.PolicyReference(
        policy_id=f"{kind}-policy",
        policy_version=version,
        policy_kind=kind,
        content_sha256=hashlib.sha256(f"policy:{kind}".encode()).hexdigest(),
        effective_at=NOW - timedelta(days=1),
    )


def _source_identity(
    module: Any,
    source_identity_id: str,
    *,
    source_system: str,
    entity_type: str,
    record_ids: tuple[str, ...],
    state: str = "active",
) -> Any:
    return module.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=source_system,
        source_key=f"key:{source_identity_id}",
        entity_type=entity_type,
        source_record_ids=record_ids,
        normalized_keys={"source_key": source_identity_id},
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW,
        state=state,
    )


def _canonical_identity(
    module: Any,
    canonical_identity_id: str,
    *,
    entity_type: str,
    source_identity_ids: tuple[str, ...],
) -> Any:
    return module.CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state="active",
        display_name=f"Display {canonical_identity_id}",
        source_identity_ids=source_identity_ids,
        identity_decision_id=f"identity-decision:{canonical_identity_id}",
        release_id=RELEASE_ID,
    )


def _recorded_response(
    module: Any,
    *,
    decision_kind: str,
    subject_id: str,
    path: str,
    assertions: tuple[Any, ...],
    state: str,
    selected_assertion_ids: tuple[str, ...],
    conflicting_assertion_ids: tuple[str, ...],
    rationale: str,
    role_bindings: dict[str, str] | None = None,
) -> Any:
    validated_output: dict[str, Any] = {
        "state": state,
        "selected_assertion_ids": list(selected_assertion_ids),
        "conflicting_assertion_ids": list(conflicting_assertion_ids),
        "confidence": 0.9,
        "rationale": rationale,
        "uncertainty": "The competing assertion remains retained for audit.",
    }
    if role_bindings is not None:
        validated_output["role_bindings"] = role_bindings
    raw_output = json.dumps(
        validated_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    ordered_assertions = tuple(
        sorted(assertions, key=lambda assertion: assertion.assertion_id)
    )
    return module.RecordedAdjudication(
        input_evidence_ids=tuple(
            assertion.assertion_id for assertion in ordered_assertions
        ),
        input_evidence_sha256=module.canonical_adjudication_input_sha256(
            decision_kind=decision_kind,
            subject_id=subject_id,
            path=path,
            assertions=ordered_assertions,
        ),
        raw_output=raw_output,
        expected_output_sha256=hashlib.sha256(raw_output).hexdigest(),
    )


def _decision_result(
    *,
    changed: bool = False,
    temporal_history: bool = False,
    non_utc_temporal: bool = False,
) -> Any:
    module = _engine_module()
    input_zone = timezone(timedelta(hours=8)) if non_utc_temporal else timezone.utc

    def input_time(value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(input_zone)

    changed_field_id = "field-b-changed" if changed else "field-b"
    sources = (
        _source_identity(
            module,
            "prof-source-a",
            source_system="official_profile_a",
            entity_type="professor",
            record_ids=("record:prof-source-a", "record:relationship"),
        ),
        _source_identity(
            module,
            "prof-source-b",
            source_system="official_profile_b",
            entity_type="professor",
            record_ids=("record:prof-source-b",),
        ),
        _source_identity(
            module,
            "company-source",
            source_system="company_registry",
            entity_type="company",
            record_ids=("record:company-source", "record:relationship"),
        ),
        _source_identity(
            module,
            "rejected-source",
            source_system="rejected_source",
            entity_type="professor",
            record_ids=("record:rejected-source",),
            state="rejected",
        ),
    )
    professor = _canonical_identity(
        module,
        "professor-c1",
        entity_type="professor",
        source_identity_ids=("prof-source-a", "prof-source-b", "rejected-source"),
    )
    company = _canonical_identity(
        module,
        "company-c1",
        entity_type="company",
        source_identity_ids=("company-source",),
    )
    field_assertions = (
        module.SourceAssertion(
            assertion_id="field-a",
            source_record_id="record:prof-source-a",
            source_identity_id="prof-source-a",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Professor",
            observed_at=NOW - timedelta(hours=2),
            assertion_run_id="field-assertion-run-1",
        ),
        module.SourceAssertion(
            assertion_id=changed_field_id,
            source_record_id="record:prof-source-b",
            source_identity_id="prof-source-b",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Distinguished Professor" if changed else "Chair Professor",
            observed_at=NOW - timedelta(hours=1),
            assertion_run_id="field-assertion-run-1",
        ),
        module.SourceAssertion(
            assertion_id="field-rejected",
            source_record_id="record:rejected-source",
            source_identity_id="rejected-source",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Dean",
            observed_at=NOW - timedelta(minutes=30),
            assertion_run_id="field-assertion-run-1",
        ),
    )
    endpoints = {
        "source_endpoint": module.IdentityReference(
            identity_id="prof-source-a",
            identity_space="source",
            entity_type="professor",
        ),
        "target_endpoint": module.IdentityReference(
            identity_id="company-source",
            identity_space="source",
            entity_type="company",
        ),
    }
    relationship_rows = (
        (
            (
                "relation-role-old",
                "founder",
                60 * 24 * 400,
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                NOW,
            ),
            (
                "relation-role-current",
                "founder",
                60 * 24,
                NOW,
                NOW,
                None,
            ),
        )
        if temporal_history
        else (
            (
                "relation-founder",
                "founder",
                50,
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                None,
            ),
            ("relation-advisor", "advisor", 40, None, None, None),
        )
    )
    relationship_assertions = tuple(
        module.RelationshipAssertion(
            assertion_id=assertion_id,
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_record_id="record:relationship",
            attributes={"role": role},
            observed_at=(NOW - timedelta(minutes=minutes)).astimezone(input_zone),
            source_event_time=input_time(source_event_time),
            valid_from=input_time(valid_from),
            valid_to=input_time(valid_to),
            assertion_run_id="relationship-assertion-run-1",
            **endpoints,
        )
        for (
            assertion_id,
            role,
            minutes,
            source_event_time,
            valid_from,
            valid_to,
        ) in relationship_rows
    )
    field_response = _recorded_response(
        module,
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
        assertions=field_assertions[:2],
        state="selected",
        selected_assertion_ids=(changed_field_id,),
        conflicting_assertion_ids=("field-a",),
        rationale=(
            "Changed replay content must conflict."
            if changed
            else "The newer official profile supports the chair title."
        ),
    )
    relationship_groups = (
        tuple(
            module.RelationshipAssertionGroup(
                canonical_relationship_id=canonical_relationship_id,
                relationship_type_id="professor_company_role",
                relationship_type_version="v1",
                source_canonical_identity_id="professor-c1",
                target_canonical_identity_id="company-c1",
                assertions=(assertion,),
                policy=_policy(module, "relationship", version="v2"),
            )
            for canonical_relationship_id, assertion in (
                ("canonical-relationship-old", relationship_assertions[0]),
                ("canonical-relationship-current", relationship_assertions[1]),
            )
        )
        if temporal_history
        else (
            module.RelationshipAssertionGroup(
                canonical_relationship_id="canonical-relationship-1",
                relationship_type_id="professor_company_role",
                relationship_type_version="v1",
                source_canonical_identity_id="professor-c1",
                target_canonical_identity_id="company-c1",
                assertions=relationship_assertions,
                policy=_policy(module, "relationship", version="v2"),
            ),
        )
    )
    recorded_responses = [field_response]
    if not temporal_history:
        recorded_responses.append(
            _recorded_response(
                module,
                decision_kind="relationship",
                subject_id="canonical-relationship-1",
                path="professor_company_role",
                assertions=relationship_assertions,
                state="selected",
                selected_assertion_ids=("relation-founder",),
                conflicting_assertion_ids=("relation-advisor",),
                rationale="The official evidence supports the founder role.",
                role_bindings={"source": "founder"},
            )
        )
    request = module.DecisionBatchRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW.astimezone(input_zone),
        source_identities=sources,
        canonical_identities=(professor, company),
        field_groups=(
            module.FieldAssertionGroup(
                canonical_identity_id="professor-c1",
                field_path="employment.current_title",
                assertions=field_assertions,
                policy=_policy(module, "field_selection"),
            ),
        ),
        relationship_groups=relationship_groups,
    )
    adjudicator = module.create_recorded_structured_adjudicator(
        provider="recorded",
        model="canonical-judge-fixture-v1",
        prompt_version="canonical-adjudication-v1",
        schema_version="canonical-adjudication-output-v1",
        responses=tuple(recorded_responses),
    )
    return module.create_ephemeral_canonical_decision_engine(
        adjudicator=adjudicator
    ).decide(request)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _insert_prerequisites(
    target: _Target,
    *,
    omitted_membership: str | None = None,
) -> None:
    record_ids = (
        "record:prof-source-a",
        "record:prof-source-b",
        "record:company-source",
        "record:relationship",
        "record:rejected-source",
    )
    with _connect(target) as connection:
        has_explicit_membership = connection.execute(
            "SELECT to_regclass('knowledge.canonical_identity_source_membership') "
            "IS NOT NULL"
        ).fetchone() == (True,)
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES "
            "('decision-artifact-1', 'recorded_fixture', 'fixture://decision', %s, "
            "1, %s, 'decision-prerequisite-run')",
            (_fingerprint("decision-artifact"), NOW),
        )
        connection.execute(
            "INSERT INTO landing.parser_run "
            "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
            "run_status, started_at, finished_at) VALUES "
            "('decision-parse-run', 'decision-artifact-1', 'recorded_fixture', 'v1', "
            "'decision-source-v1', 'succeeded', %s, %s)",
            (NOW, NOW),
        )
        for ordinal, record_id in enumerate(record_ids):
            connection.execute(
                "INSERT INTO landing.source_record "
                "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
                "record_ordinal, parse_status, payload, parsed_at) VALUES "
                "(%s, 'decision-artifact-1', 'decision-source-batch', %s, "
                "'decision-parse-run', %s, 'parsed', %s, %s)",
                (record_id, f"row:{ordinal}", ordinal, Jsonb({"id": record_id}), NOW),
            )
        for source_identity_id, source_system, entity_type, linked_records, state in (
            (
                "prof-source-a",
                "official_profile_a",
                "professor",
                ("record:prof-source-a", "record:relationship"),
                "active",
            ),
            (
                "prof-source-b",
                "official_profile_b",
                "professor",
                ("record:prof-source-b",),
                "active",
            ),
            (
                "company-source",
                "company_registry",
                "company",
                ("record:company-source", "record:relationship"),
                "active",
            ),
            (
                "rejected-source",
                "rejected_source",
                "professor",
                ("record:rejected-source",),
                "rejected",
            ),
        ):
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    source_identity_id,
                    source_system,
                    f"key:{source_identity_id}",
                    entity_type,
                    Jsonb({"source_key": source_identity_id}),
                    NOW - timedelta(days=30),
                    NOW,
                    state,
                ),
            )
            for record_id in linked_records:
                connection.execute(
                    "INSERT INTO knowledge.source_identity_record "
                    "(source_identity_id, record_id) VALUES (%s, %s)",
                    (source_identity_id, record_id),
                )
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, %s, 'candidate', %s, %s)",
            (RELEASE_ID, RUN_ID, _fingerprint("decision-manifest"), NOW),
        )
        for kind, version in (
            ("identity", "v1"),
            ("field_selection", "v1"),
            ("relationship", "v2"),
        ):
            connection.execute(
                "INSERT INTO knowledge.policy "
                "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    f"{kind}-policy",
                    version,
                    kind,
                    _fingerprint(f"policy:{kind}"),
                    NOW - timedelta(days=1),
                ),
            )
        for canonical_identity_id, entity_type, source_identity_ids in (
            (
                "professor-c1",
                "professor",
                ("prof-source-a", "prof-source-b", "rejected-source"),
            ),
            ("company-c1", "company", ("company-source",)),
        ):
            decision_id = f"identity-decision:{canonical_identity_id}"
            connection.execute(
                "INSERT INTO knowledge.identity_decision "
                "(release_id, decision_id, action, policy_id, policy_version, method, "
                "method_version, decision_run_id, confidence, rationale, decided_at) "
                "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
                "'identity-v1', %s, 1.0, 'fixture identity', %s)",
                (RELEASE_ID, decision_id, RUN_ID, NOW),
            )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity "
                "(release_id, canonical_identity_id, entity_type, state, display_name, "
                "identity_decision_id) VALUES (%s, %s, %s, 'active', %s, %s)",
                (
                    RELEASE_ID,
                    canonical_identity_id,
                    entity_type,
                    f"Display {canonical_identity_id}",
                    decision_id,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output "
                "(release_id, decision_id, canonical_identity_id) "
                "VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, canonical_identity_id),
            )
            for source_identity_id in source_identity_ids:
                if source_identity_id == omitted_membership:
                    continue
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_source_identity "
                    "(release_id, decision_id, source_identity_id) "
                    "VALUES (%s, %s, %s)",
                    (RELEASE_ID, decision_id, source_identity_id),
                )
                if has_explicit_membership:
                    connection.execute(
                        "INSERT INTO knowledge.canonical_identity_source_membership "
                        "(release_id, canonical_identity_id, source_identity_id) "
                        "VALUES (%s, %s, %s)",
                        (RELEASE_ID, canonical_identity_id, source_identity_id),
                    )
        connection.execute(
            "INSERT INTO knowledge.relationship_type "
            "(relationship_type_id, version, layer, source_entity_types, "
            "target_entity_types, direction, roles, required_evidence_kinds, "
            "time_semantics, allowed_states, eligible_paths) VALUES "
            "('professor_company_role', 'v1', 'canonical', %s, %s, 'directed', %s, "
            "%s, 'validity_interval', %s, %s)",
            (
                Jsonb(["professor"]),
                Jsonb(["company"]),
                Jsonb([{"role_id": "founder", "applies_to": "source"}]),
                Jsonb(["official_profile"]),
                Jsonb(["accepted", "unresolved", "rejected"]),
                Jsonb(["relationship_traversal"]),
            ),
        )
        connection.commit()


def _persisted_counts(target: _Target) -> tuple[int, ...]:
    with _connect(target) as connection:
        return connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.source_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_assertion), "
            "(SELECT count(*) FROM knowledge.canonical_decision), "
            "(SELECT count(*) FROM knowledge.canonical_decision_assertion), "
            "(SELECT count(*) FROM knowledge.canonical_decision_constraint_outcome), "
            "(SELECT count(*) FROM knowledge.canonical_decision_identity_context), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "(SELECT count(*) FROM knowledge.relationship_decision_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_decision_constraint_outcome), "
            "(SELECT count(*) FROM knowledge.relationship_decision_identity_context)"
        ).fetchone()


def test_complete_field_and_relationship_result_round_trips_and_replays_exactly(
    target: _Target,
) -> None:
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0005",)
        assert connection.execute(
            "SELECT to_regclass('knowledge.canonical_identity_source_membership')"
        ).fetchone() == (None,)
    result = _decision_result()
    _insert_prerequisites(target)
    module = _postgres_module()
    store = _store(target)
    assert isinstance(store, module.CanonicalDecisionStore)

    first = store.persist(result)
    counts = _persisted_counts(target)
    replayed = _store(target).persist(result)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert first == replayed == loaded == result
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")
    assert loaded.content_sha256 == result.content_sha256
    assert len(loaded.field_assertions) == 3
    assert len(loaded.relationship_assertions) == 2
    assert len(loaded.canonical_decisions) == 1
    assert len(loaded.relationship_decisions) == 1
    assert len(loaded.current_fields) == 1
    assert len(loaded.current_relationships) == 1
    field_outcomes = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id.startswith("field-")
    )
    relationship_outcomes = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id.startswith("relation-")
    )
    assert len(field_outcomes) == 3
    assert len(relationship_outcomes) == 2
    assert {outcome.policy_version for outcome in field_outcomes} == {"v1"}
    assert {outcome.policy_version for outcome in relationship_outcomes} == {"v2"}
    rejected = next(
        outcome
        for outcome in field_outcomes
        if outcome.assertion_id == "field-rejected"
    )
    assert rejected.admitted is False
    assert rejected.reason_codes == ("source_identity_rejected",)
    assert rejected.policy_version == "v1"
    admitted = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id != "field-rejected"
    )
    assert all(outcome.admitted for outcome in admitted)
    assert all(outcome.reason_codes == () for outcome in admitted)
    field_decision = loaded.canonical_decisions[0]
    assert "field-rejected" not in field_decision.candidate_assertion_ids
    assert "field-rejected" not in field_decision.llm_trace.input_evidence_ids
    assert _persisted_counts(target) == counts

    with pytest.raises(
        sa_exc.DBAPIError,
        match="non-empty|not empty|constraint outcome|outcome|identity-context",
    ):
        command.downgrade(target.config, "C2_0004")
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0005",)
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_temporal_relationship_history_restarts_with_only_as_of_current(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    changed = _decision_result(changed=True, temporal_history=True)
    _insert_prerequisites(target)

    persisted = _store(target).persist(result)
    counts = _persisted_counts(target)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert persisted == loaded == result
    assert len(loaded.relationship_assertions) == 2
    assert len(loaded.relationship_decisions) == 2
    assert tuple(
        current.canonical_relationship_id for current in loaded.current_relationships
    ) == ("canonical-relationship-current",)
    assert {
        decision.canonical_relationship_id: (
            decision.valid_from,
            decision.valid_to,
        )
        for decision in loaded.relationship_decisions
    } == {
        "canonical-relationship-current": (NOW, None),
        "canonical-relationship-old": (NOW - timedelta(days=365), NOW),
    }
    assert {
        assertion.assertion_id: (
            assertion.observed_at,
            assertion.source_event_time,
            assertion.valid_from,
            assertion.valid_to,
        )
        for assertion in loaded.relationship_assertions
    } == {
        "relation-role-current": (
            NOW - timedelta(days=1),
            NOW,
            NOW,
            None,
        ),
        "relation-role-old": (
            NOW - timedelta(days=400),
            NOW - timedelta(days=365),
            NOW - timedelta(days=365),
            NOW,
        ),
    }

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT assertion_id, observed_at, source_event_time, valid_from, valid_to "
            "FROM knowledge.relationship_assertion ORDER BY assertion_id"
        ).fetchall() == [
            (
                "relation-role-current",
                NOW - timedelta(days=1),
                NOW,
                NOW,
                None,
            ),
            (
                "relation-role-old",
                NOW - timedelta(days=400),
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                NOW,
            ),
        ]
        assert connection.execute(
            "SELECT canonical_relationship_id, valid_from, valid_to "
            "FROM knowledge.relationship_decision "
            "ORDER BY canonical_relationship_id"
        ).fetchall() == [
            ("canonical-relationship-current", NOW, None),
            (
                "canonical-relationship-old",
                NOW - timedelta(days=365),
                NOW,
            ),
        ]

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="content|conflict|replay|decision_run_id|run",
    ):
        _store(target).persist(changed)

    assert _store(target).load(RELEASE_ID, RUN_ID) == result
    assert _persisted_counts(target) == counts
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.source_assertion "
            "WHERE assertion_id = 'field-b-changed'"
        ).fetchone() == (0,)


def test_non_utc_temporal_inputs_restart_as_one_canonical_instant(
    target: _Target,
) -> None:
    result = _decision_result(
        temporal_history=True,
        non_utc_temporal=True,
    )
    _insert_prerequisites(target)
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("ALTER DATABASE {} SET timezone TO 'Asia/Shanghai'").format(
                sql.Identifier(target.expected_database)
            )
        )
    with _connect(target) as connection:
        assert connection.execute("SHOW timezone").fetchone() == ("Asia/Shanghai",)

    persisted = _store(target).persist(result)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert persisted == loaded == result
    for assertion in loaded.relationship_assertions:
        assert assertion.observed_at.utcoffset() == timedelta(0)
        if assertion.source_event_time is not None:
            assert assertion.source_event_time.utcoffset() == timedelta(0)
        if assertion.valid_from is not None:
            assert assertion.valid_from.utcoffset() == timedelta(0)
        if assertion.valid_to is not None:
            assert assertion.valid_to.utcoffset() == timedelta(0)
    assert all(
        decision.valid_from is None or decision.valid_from.utcoffset() == timedelta(0)
        for decision in loaded.relationship_decisions
    )
    assert loaded.content_sha256 == result.content_sha256


def test_corrupt_temporal_restart_is_wrapped_by_store_abstraction(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "ALTER TABLE knowledge.relationship_assertion DISABLE TRIGGER USER"
        )
        try:
            connection.execute(
                "UPDATE knowledge.relationship_assertion "
                "SET valid_from = valid_from - interval '1 day' "
                "WHERE assertion_id = 'relation-role-current'"
            )
        finally:
            connection.execute(
                "ALTER TABLE knowledge.relationship_assertion ENABLE TRIGGER USER"
            )

    module = _postgres_module()
    with pytest.raises(
        module.CanonicalDecisionPersistenceError,
        match="incomplete|corrupt",
    ) as caught:
        _store(target).load(RELEASE_ID, RUN_ID)
    assert isinstance(caught.value.__cause__, ValueError)
    assert not isinstance(
        caught.value.__cause__,
        _engine_module().DecisionBatchIntegrityError,
    )


@pytest.mark.parametrize("omitted_membership", ("prof-source-b", "company-source"))
def test_missing_authoritative_identity_membership_fails_before_decision_writes(
    target: _Target,
    omitted_membership: str,
) -> None:
    result = _decision_result()
    _insert_prerequisites(target, omitted_membership=omitted_membership)

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="identity|ownership|context|membership",
    ):
        _store(target).persist(result)

    assert _persisted_counts(target) == (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_c2_0005_legacy_membership_rejects_multi_output_identity_decision(
    target: _Target,
) -> None:
    result = _decision_result()
    _insert_prerequisites(target)
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, display_name, "
            "identity_decision_id) VALUES (%s, 'professor-c2', 'professor', "
            "'active', 'Ambiguous second output', "
            "'identity-decision:professor-c1')",
            (RELEASE_ID,),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) VALUES "
            "(%s, 'identity-decision:professor-c1', 'professor-c2')",
            (RELEASE_ID,),
        )
        connection.commit()

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="identity ownership|constraint context|single output",
    ):
        _store(target).persist(result)

    assert _persisted_counts(target) == (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_historical_load_uses_immutable_decision_time_identity_context(
    target: _Target,
) -> None:
    result = _decision_result()
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.source_record "
            "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
            "record_ordinal, parse_status, payload, parsed_at) VALUES "
            "('record:prof-source-a:later', 'decision-artifact-1', "
            "'later-source-batch', 'row:later', 'decision-parse-run', 99, "
            "'parsed', %s, %s)",
            (Jsonb({"id": "later"}), NOW + timedelta(days=1)),
        )
        connection.execute(
            "INSERT INTO knowledge.source_identity_record "
            "(source_identity_id, record_id) "
            "VALUES ('prof-source-a', 'record:prof-source-a:later')"
        )
        connection.execute(
            "UPDATE knowledge.source_identity SET last_observed_at = %s, "
            "state = 'superseded' WHERE source_identity_id = 'prof-source-a'",
            (NOW + timedelta(days=1),),
        )
        connection.commit()

    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_factory_interface_and_explicit_target_safety_are_enforced(
    target: _Target,
    tmp_path: Path,
) -> None:
    module = _postgres_module()
    factory = module.create_postgres_canonical_decision_store
    parameters = inspect.signature(factory).parameters
    assert tuple(parameters) == (
        "database_url",
        "expected_database",
        "target_kind",
        "backup_gate_root",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in parameters.values()
    )
    with pytest.raises(TypeError):
        factory()
    assert isinstance(_store(target), module.CanonicalDecisionStore)

    gate_module = import_module("src.data_agents.canonical_v2.rebuild_write_gate")
    with pytest.raises(gate_module.RebuildWriteGateError):
        factory(
            database_url=(
                "postgresql+psycopg://miroflow@unresolvable.invalid/"
                "canonical_decision_must_not_connect"
            ),
            expected_database="canonical_decision_must_not_connect",
            target_kind="disposable",
            backup_gate_root=tmp_path / "unaccepted-gate",
        )

    disposable_marker = (
        f"miroflow:destructive-target:v1:disposable:{target.expected_database}"
    )
    try:
        _set_database_marker(target, "miroflow:destructive-target:v1:disposable:wrong")
        with pytest.raises(
            module.CanonicalDecisionPersistenceError,
            match="marker|identity|target|database",
        ):
            _store(target)

        _set_database_marker(
            target,
            "miroflow:destructive-target:v1:isolated-candidate:"
            f"{target.expected_database}",
        )
        with pytest.raises(
            module.CanonicalDecisionPersistenceError,
            match="disposable|target",
        ):
            factory(
                database_url=target.database_url,
                expected_database=target.expected_database,
                target_kind="isolated-candidate",
                backup_gate_root=target.backup_gate_root,
            )
    finally:
        _set_database_marker(target, disposable_marker)


def test_changed_content_conflicts_and_rolls_back_every_new_row(
    target: _Target,
) -> None:
    original = _decision_result()
    changed = _decision_result(changed=True)
    _insert_prerequisites(target)
    store = _store(target)
    assert store.persist(original) == original
    counts = _persisted_counts(target)

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="content|conflict|replay|decision_run_id|run",
    ):
        _store(target).persist(changed)

    assert _store(target).load(RELEASE_ID, RUN_ID) == original
    assert _persisted_counts(target) == counts
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.source_assertion "
            "WHERE assertion_id = 'field-b-changed'"
        ).fetchone() == (0,)


def test_empty_c2_0005_round_trips_through_c2_0004_on_owned_sibling(
    target: _Target,
) -> None:
    revision = ScriptDirectory.from_config(target.config).get_revision("C2_0005")
    assert revision is not None
    assert revision.down_revision == "C2_0004"

    try:
        command.downgrade(target.config, "C2_0004")
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0004",)
            assert connection.execute(
                "SELECT "
                "to_regclass('knowledge.canonical_decision_constraint_outcome'), "
                "to_regclass('knowledge.relationship_decision_constraint_outcome'), "
                "to_regclass('knowledge.canonical_decision_identity_context'), "
                "to_regclass('knowledge.relationship_decision_identity_context')"
            ).fetchone() == (None, None, None, None)

        command.upgrade(target.config, "C2_0005")
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0005",)
            assert connection.execute(
                "SELECT "
                "to_regclass('knowledge.canonical_decision_constraint_outcome'), "
                "to_regclass('knowledge.relationship_decision_constraint_outcome'), "
                "to_regclass('knowledge.canonical_decision_identity_context'), "
                "to_regclass('knowledge.relationship_decision_identity_context')"
            ).fetchone() == (
                "knowledge.canonical_decision_constraint_outcome",
                "knowledge.relationship_decision_constraint_outcome",
                "knowledge.canonical_decision_identity_context",
                "knowledge.relationship_decision_identity_context",
            )
    finally:
        command.upgrade(target.config, "head")


@pytest.mark.parametrize("decision_family", ("field", "relationship"))
def test_c2_0005_refuses_existing_decisions_without_inventing_context_snapshots(
    target: _Target,
    decision_family: str,
) -> None:
    command.downgrade(target.config, "C2_0004")
    _insert_prerequisites(target)
    with _connect(target) as connection:
        if decision_family == "field":
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at) VALUES "
                "(%s, 'legacy-field-decision', 'professor-c1', "
                "'employment.current_title', 'unresolved', "
                "'field_selection-policy', 'v1', 'deterministic', "
                "'canonical-decision-v0', %s, 0.0, 'legacy field decision', %s)",
                (RELEASE_ID, RUN_ID, NOW),
            )
        else:
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, decided_at) VALUES "
                "(%s, 'legacy-relationship-decision', 'legacy-relationship', "
                "'professor_company_role', 'v1', 'professor-c1', 'company-c1', "
                "'unresolved', '{}'::jsonb, 'relationship-policy', 'v2', "
                "'deterministic', 'canonical-decision-v0', %s, 0.0, "
                "'legacy relationship decision', %s)",
                (RELEASE_ID, RUN_ID, NOW),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0004",)
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.canonical_decision), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "to_regclass('knowledge.canonical_decision_identity_context'), "
            "to_regclass('knowledge.relationship_decision_identity_context')"
        ).fetchone() == (
            1 if decision_family == "field" else 0,
            1 if decision_family == "relationship" else 0,
            None,
            None,
        )


def test_downgrade_serializes_with_an_uncommitted_outcome_insert(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0005")
    _insert_prerequisites(target)
    assertion_id = "downgrade-race-assertion"
    decision_id = "downgrade-race-decision"
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.source_assertion "
            "(assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, "
            "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
            "VALUES (%s, 'record:prof-source-a', 'prof-source-a', 'professor', "
            "'employment.current_title', %s, %s, %s, 'downgrade-race-run')",
            (
                assertion_id,
                Jsonb("Professor"),
                _fingerprint(assertion_id),
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at) VALUES "
            "(%s, %s, 'professor-c1', 'employment.current_title', 'selected', "
            "'field_selection-policy', 'v1', 'deterministic', 'field-v1', %s, "
            "1.0, 'downgrade race fixture', %s)",
            (RELEASE_ID, decision_id, RUN_ID, NOW),
        )
        connection.commit()

    application_name = "canonical_v2_c2_0005_downgrade_race"
    migration_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": application_name})
        .render_as_string(hide_password=False)
    )
    migration_target = _Target(
        database_url=migration_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        config=Config(),
    )
    migration_config = _migration_config(migration_target)
    writer = _connect(target)
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade = None
    writer_released = False
    try:
        writer.execute(
            "INSERT INTO knowledge.canonical_decision_constraint_outcome "
            "(release_id, decision_id, assertion_id, admitted, reason_codes) "
            "VALUES (%s, %s, %s, TRUE, '[]'::jsonb)",
            (RELEASE_ID, decision_id, assertion_id),
        )
        downgrade = executor.submit(command.downgrade, migration_config, "C2_0004")

        poll_interval = Event()
        deadline = time.monotonic() + 10.0
        lock_wait = None
        with _connect(target, autocommit=True) as observer:
            while time.monotonic() < deadline:
                lock_wait = observer.execute(
                    "SELECT wait_event_type, wait_event FROM pg_stat_activity "
                    "WHERE datname = current_database() AND application_name = %s",
                    (application_name,),
                ).fetchone()
                if lock_wait is not None and lock_wait[0] == "Lock":
                    break
                if downgrade.done():
                    break
                poll_interval.wait(0.01)
        assert lock_wait is not None
        assert lock_wait[0] == "Lock"
        assert not downgrade.done()

        writer.commit()
        writer_released = True
        with pytest.raises(sa_exc.DBAPIError) as caught:
            downgrade.result(timeout=10.0)
        assert getattr(caught.value.orig, "sqlstate", None) == "55000"

        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0005",)
            assert connection.execute(
                "SELECT admitted, reason_codes FROM "
                "knowledge.canonical_decision_constraint_outcome "
                "WHERE release_id = %s AND decision_id = %s AND assertion_id = %s",
                (RELEASE_ID, decision_id, assertion_id),
            ).fetchone() == (True, [])
    finally:
        if not writer_released:
            writer.rollback()
        writer.close()
        if downgrade is not None and not downgrade.done():
            downgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_missing_parents_are_not_created_and_no_current_projection_is_durable(
    target: _Target,
) -> None:
    result = _decision_result()
    module = _postgres_module()
    store = _store(target)

    with pytest.raises(module.CanonicalDecisionPersistenceError):
        store.persist(result)
    with pytest.raises(module.CanonicalDecisionNotFoundError):
        store.load(RELEASE_ID, RUN_ID)

    with _connect(target) as connection:
        assert (
            connection.execute(
                "SELECT "
                "(SELECT count(*) FROM landing.evidence_artifact), "
                "(SELECT count(*) FROM landing.parser_run), "
                "(SELECT count(*) FROM landing.source_record), "
                "(SELECT count(*) FROM landing.source_error), "
                "(SELECT count(*) FROM landing.ingest_run), "
                "(SELECT count(*) FROM knowledge.release), "
                "(SELECT count(*) FROM knowledge.policy), "
                "(SELECT count(*) FROM knowledge.source_identity), "
                "(SELECT count(*) FROM knowledge.source_identity_record), "
                "(SELECT count(*) FROM knowledge.identity_decision), "
                "(SELECT count(*) FROM knowledge.canonical_identity), "
                "(SELECT count(*) FROM knowledge.relationship_type), "
                "(SELECT count(*) FROM knowledge.source_assertion), "
                "(SELECT count(*) FROM knowledge.relationship_assertion), "
                "(SELECT count(*) FROM knowledge.canonical_decision), "
                "(SELECT count(*) FROM knowledge.canonical_decision_assertion), "
                "(SELECT count(*) FROM knowledge.canonical_decision_constraint_outcome), "
                "(SELECT count(*) FROM knowledge.relationship_decision), "
                "(SELECT count(*) FROM knowledge.relationship_decision_assertion), "
                "(SELECT count(*) FROM "
                " knowledge.relationship_decision_constraint_outcome)"
            ).fetchone()
            == (0,) * 20
        )
        current_tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_name ILIKE %s",
            (
                [
                    "landing",
                    "knowledge",
                    "publish",
                    "professor",
                    "company",
                    "paper",
                    "patent",
                    "ops",
                ],
                "%current%",
            ),
        ).fetchall()
        assert current_tables == []
