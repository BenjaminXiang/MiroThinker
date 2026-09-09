from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
from importlib import import_module
import json
import os
from pathlib import Path
import sys
from typing import Any, LiteralString, cast

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2.contracts import (
    CandidateRelease,
    ReleaseState,
    ReleaseVerification,
)
from src.data_agents.canonical_v2.knowledge_gap_feedback import (
    GapEffectVerification,
    GapRemediationRequest,
    GapSignal,
    GapTrigger,
    OfflineRemediationReceipt,
    create_ephemeral_knowledge_gap_feedback,
)
from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0011"
SOURCE_RELEASE_ID = "release:s10o:source"
CANDIDATE_RELEASE_ID = "release:s10o:candidate"
BUILD_RUN_ID = "build:s10o:candidate"
SOURCE_BATCH_IDS = ("batch:s10o:candidate",)
MANIFEST_SHA256 = "a" * 64
NOW = datetime(2026, 7, 20, 12, 30, tzinfo=UTC)


class _MissingS10ODurableOperations(RuntimeError):
    """Exact S10O RED sentinel; setup and predecessor failures remain visible."""


def _postgres_module() -> Any:
    try:
        module = import_module("src.data_agents.canonical_v2.knowledge_gap_postgres")
    except ModuleNotFoundError as exc:
        if exc.name == "src.data_agents.canonical_v2.knowledge_gap_postgres":
            raise _MissingS10ODurableOperations(
                "exact S10O durable knowledge-gap operations module is absent"
            ) from exc
        raise
    required = (
        "GapAdminQuery",
        "GapAdminPage",
        "GapAdminDetail",
        "KnowledgeGapPersistenceError",
        "PostgresKnowledgeGapOperations",
        "create_postgres_knowledge_gap_operations",
    )
    missing = tuple(name for name in required if not hasattr(module, name))
    revision = _scripts().get_revision(EXPECTED_REVISION)
    if missing or revision is None:
        details = (*missing, *(("C2_0011",) if revision is None else ()))
        raise _MissingS10ODurableOperations(
            "exact S10O durable target surface is absent: " + ", ".join(details)
        )
    return module


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
    target_kind: str
    backup_gate_root: Path
    config: Config


def _scripts() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return ScriptDirectory.from_config(config)


def _explicit_environment() -> tuple[str, str, str, str]:
    names = (
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not all(values):
        pytest.skip("S10O PostgreSQL checks require all four explicit target settings")
    return values  # type: ignore[return-value]


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _sibling_url(database_url: str, database_name: str) -> str:
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _migration_config(target: _Target) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, target.database_url)
    config.set_main_option("miroflow.expected_database", target.expected_database)
    config.set_main_option("miroflow.target_kind", target.target_kind)
    config.set_main_option("miroflow.backup_gate_root", str(target.backup_gate_root))
    return config


def _drop_sibling(
    connection: psycopg.Connection[Any], database_name: str, marker: str
) -> None:
    row = connection.execute(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s",
        (database_name,),
    ).fetchone()
    if row is None:
        return
    assert row == (marker,)
    connection.execute(
        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
    )


@pytest.fixture
def target(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert target_kind == "disposable"
    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "DATABASE_URL",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    sibling_name = (
        f"{expected_database[:38]}_s10o_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    marker = f"miroflow:destructive-target:v1:disposable:{sibling_name}"
    base_marker = f"miroflow:destructive-target:v1:disposable:{expected_database}"
    with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
        assert admin.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone() == (expected_database, base_marker)
        _drop_sibling(admin, sibling_name, marker)
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(sibling_name))
        )
        admin.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(sibling_name), sql.Literal(marker)
            )
        )
    provisional = _Target(
        database_url=_sibling_url(database_url, sibling_name),
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
    try:
        command.upgrade(configured.config, EXPECTED_REVISION)
        yield configured
    finally:
        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
            _drop_sibling(admin, sibling_name, marker)


def _operations(module: Any, target: _Target, *, clock: Any):
    return module.create_postgres_knowledge_gap_operations(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        clock=clock,
    )


def _seed_release(
    target: _Target,
    *,
    release_id: str,
    state: str,
    build_run_id: str = "build:s10o:source",
    manifest_sha256: str = "b" * 64,
    source_batch_ids: tuple[str, ...] = ("batch:s10o:source",),
) -> None:
    source_batches_hash = _canonical_sha256(
        {"source_batch_ids": list(source_batch_ids)}
    )
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (release_id, build_run_id, state, manifest_sha256, NOW),
        )
        connection.execute(
            "INSERT INTO publish.build_manifest "
            "(release_id, manifest_version, build_run_id, source_batch_ids, "
            "source_batches_sha256, parser_versions, policy_versions, model_versions, "
            "manifest_sha256, created_at) VALUES "
            "(%s, 'canonical-v2-build-manifest-v2', %s, %s::jsonb, %s, "
            "%s::jsonb, %s::jsonb, %s::jsonb, %s, %s)",
            (
                release_id,
                build_run_id,
                json.dumps(source_batch_ids),
                source_batches_hash,
                json.dumps({"offline-remediation": "parser-v1"}),
                json.dumps({"gap-remediation": "gap-remediation-v1"}),
                json.dumps({}),
                manifest_sha256,
                NOW,
            ),
        )
        for section_id, section_kind, record_count in (
            ("objects:professor", "object_set", 1),
            ("objects:paper", "object_set", 1),
            ("relationships", "relationship_set", 1),
        ):
            connection.execute(
                "INSERT INTO publish.manifest_section "
                "(release_id, section_id, section_kind, version, record_count, "
                "content_sha256) VALUES (%s, %s, %s, 's10o-v1', %s, %s)",
                (
                    release_id,
                    section_id,
                    section_kind,
                    record_count,
                    _canonical_sha256(
                        {"release_id": release_id, "section_id": section_id}
                    ),
                ),
            )
        connection.commit()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _content_bound(model: type[Any], payload: dict[str, Any]) -> Any:
    normalized = model.model_construct(**payload, content_sha256="0" * 64).model_dump(
        mode="json", exclude={"content_sha256"}
    )
    return model(**payload, content_sha256=_canonical_sha256(normalized))


def _signal(
    *,
    signal_id: str = "signal:s10o:missing-relationship",
    symptom: str = "A material Professor-Paper path is missing.",
    evidence_ids: tuple[str, ...] = (
        "field-assertion:s10o",
        "web:s10o:unmatched",
    ),
    trigger: GapTrigger = GapTrigger.missing_relationship,
    release_id: str = SOURCE_RELEASE_ID,
    affected_domains: tuple[str, ...] = ("professor", "paper"),
    affected_paths: tuple[str, ...] = ("professor_attributed_to_paper",),
    demand_observation_ids: tuple[str, ...] = ("demand:s10o:1",),
) -> GapSignal:
    return GapSignal(
        signal_id=signal_id,
        trigger=trigger,
        release_id=release_id,
        affected_domains=affected_domains,
        affected_paths=affected_paths,
        query_trace_id="query-trace:s10o",
        answer_trace_id="answer-trace:s10o",
        benchmark_case_id="case:s10o",
        telemetry_key=None,
        observed_symptom=symptom,
        evidence_ids=evidence_ids,
        demand_observation_ids=demand_observation_ids,
        observed_at=NOW,
    )


def _candidate(*, state: str) -> CandidateRelease:
    return CandidateRelease(
        release_id=CANDIDATE_RELEASE_ID,
        run_id=BUILD_RUN_ID,
        state=ReleaseState(state),
        source_batch_ids=SOURCE_BATCH_IDS,
        parser_versions={"offline-remediation": "parser-v1"},
        policy_versions={"gap-remediation": "gap-remediation-v1"},
        model_versions={},
        manifest_sha256=MANIFEST_SHA256,
        object_counts={"professor": 1, "paper": 1},
        relationship_count=1,
        active_release_changed=False,
    )


def _request(gap: Any, *, state: str) -> GapRemediationRequest:
    completed = NOW + timedelta(hours=1)
    receipt = _content_bound(
        OfflineRemediationReceipt,
        {
            "receipt_id": "receipt:s10o",
            "gap_id": gap.gap_id,
            "remediation_kind": "relationship_repair",
            "execution_mode": "offline",
            "source_release_id": SOURCE_RELEASE_ID,
            "candidate_release_id": CANDIDATE_RELEASE_ID,
            "affected_domains": gap.affected_domains,
            "affected_paths": gap.affected_paths,
            "offline_run_id": "offline:s10o",
            "source_batch_ids": SOURCE_BATCH_IDS,
            "landing_artifact_ids": ("artifact:s10o",),
            "build_run_id": BUILD_RUN_ID,
            "review_state": "accepted",
            "review_evidence_ids": ("review:s10o",),
            "started_at": NOW + timedelta(minutes=30),
            "completed_at": completed,
        },
    )
    release_verification = None
    effect_verification = None
    if state == "accepted":
        release_verification = ReleaseVerification(
            candidate_release_id=CANDIDATE_RELEASE_ID,
            manifest_sha256=MANIFEST_SHA256,
            accepted=True,
            canonical_index_parity=True,
            missing_points=0,
            extra_points=0,
            stale_points=0,
            cross_release_points=0,
            evidence_ids=("verification:release:s10o",),
            verified_at=completed + timedelta(minutes=10),
        )
        effect_verification = _content_bound(
            GapEffectVerification,
            {
                "verification_id": "verification:effect:s10o",
                "gap_id": gap.gap_id,
                "release_id": CANDIDATE_RELEASE_ID,
                "affected_domains": gap.affected_domains,
                "affected_paths": gap.affected_paths,
                "query_trace_id": gap.query_trace_id,
                "answer_trace_id": gap.answer_trace_id,
                "benchmark_case_id": gap.benchmark_case_id,
                "scenario_ids": (gap.benchmark_case_id,),
                "accepted": True,
                "evidence_ids": ("verification:effect:s10o",),
                "verified_at": completed + timedelta(minutes=20),
            },
        )
    payload = {
        "request_id": f"request:s10o:{state}",
        "gap": gap,
        "remediation_receipt": receipt,
        "candidate_release": _candidate(state=state),
        "release_verification": release_verification,
        "effect_verification": effect_verification,
        "requested_at": completed + timedelta(minutes=30),
    }
    return _content_bound(GapRemediationRequest, payload)


def test_c2_0011_is_append_only_reversible_and_refuses_nonempty_downgrade(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    revision = _scripts().get_revision(EXPECTED_REVISION)
    assert revision is not None and revision.down_revision == "C2_0010"
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT to_regclass('ops.knowledge_gap'), "
            "to_regclass('ops.gap_remediation_transition'), "
            "to_regclass('ops.current_knowledge_gap')"
        ).fetchone() == (
            "ops.knowledge_gap",
            "ops.gap_remediation_transition",
            "ops.current_knowledge_gap",
        )
    command.downgrade(target.config, "C2_0010")
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT to_regclass('ops.knowledge_gap'), "
            "to_regclass('ops.gap_remediation_transition'), "
            "to_regclass('ops.current_knowledge_gap')"
        ).fetchone() == (None, None, None)
    command.upgrade(target.config, EXPECTED_REVISION)
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    _seed_release(
        target,
        release_id=CANDIDATE_RELEASE_ID,
        state="candidate",
        build_run_id=BUILD_RUN_ID,
        manifest_sha256=MANIFEST_SHA256,
        source_batch_ids=SOURCE_BATCH_IDS,
    )
    gap = _operations(module, target, clock=lambda: NOW).record(_signal())
    _operations(
        module, target, clock=lambda: NOW + timedelta(hours=2)
    ).apply_remediation(_request(gap, state="candidate"))
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert set(
            connection.execute(
                "SELECT class.relname, trigger.tgname FROM pg_trigger AS trigger "
                "JOIN pg_class AS class ON class.oid=trigger.tgrelid "
                "JOIN pg_namespace AS namespace ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='ops' AND NOT trigger.tgisinternal "
                "AND class.relname=ANY(%s)",
                (["knowledge_gap", "gap_remediation_transition"],),
            ).fetchall()
        ) == {
            ("knowledge_gap", "trg_reject_mutation"),
            ("knowledge_gap", "trg_reject_truncate"),
            ("gap_remediation_transition", "trg_reject_mutation"),
            ("gap_remediation_transition", "trg_reject_truncate"),
        }
    for statement, parameters in (
        (
            "UPDATE ops.knowledge_gap SET status='planned' WHERE gap_id=%s",
            (gap.gap_id,),
        ),
        ("DELETE FROM ops.knowledge_gap WHERE gap_id=%s", (gap.gap_id,)),
        ("TRUNCATE ops.knowledge_gap, ops.gap_remediation_transition", ()),
        (
            "UPDATE ops.gap_remediation_transition SET transition_state='resolved' "
            "WHERE gap_id=%s",
            (gap.gap_id,),
        ),
        ("DELETE FROM ops.gap_remediation_transition WHERE gap_id=%s", (gap.gap_id,)),
        ("TRUNCATE ops.gap_remediation_transition", ()),
    ):
        with psycopg.connect(
            _psycopg_dsn(target.database_url), autocommit=True
        ) as connection:
            with pytest.raises(psycopg.Error, match="append-only"):
                connection.execute(sql.SQL(cast(LiteralString, statement)), parameters)
    with pytest.raises(Exception, match="nonempty|operational history"):
        command.downgrade(target.config, "C2_0010")
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)


def test_gap_record_persists_restarts_and_rejects_same_id_different_content(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    first = _operations(module, target, clock=lambda: NOW).record(_signal())
    restarted = _operations(module, target, clock=lambda: NOW + timedelta(days=1))
    assert restarted.record(_signal()) == first
    assert restarted.get_for_admin(first.gap_id).gap == first
    malformed_gap = create_ephemeral_knowledge_gap_feedback(clock=lambda: NOW).record(
        _signal(signal_id="signal:s10o:malformed-search-columns")
    )
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        connection.execute(
            "INSERT INTO ops.knowledge_gap "
            "(gap_id, release_id, gap_class, status, review_state, severity, "
            "affected_domains, affected_paths, demand_count, created_at, updated_at, "
            "gap_payload, content_sha256) VALUES "
            "(%s, %s, %s, 'planned', %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            (
                malformed_gap.gap_id,
                malformed_gap.release_id,
                malformed_gap.gap_class.value,
                malformed_gap.review_state.value,
                malformed_gap.severity.value,
                list(malformed_gap.affected_domains),
                list(malformed_gap.affected_paths),
                malformed_gap.demand_count,
                malformed_gap.created_at,
                malformed_gap.updated_at,
                malformed_gap.model_dump_json(),
                _canonical_sha256(malformed_gap.model_dump(mode="json")),
            ),
        )
        connection.commit()
    with pytest.raises(module.KnowledgeGapIntegrityError):
        restarted.get_for_admin(malformed_gap.gap_id)
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM ops.knowledge_gap"
        ).fetchone() == (2,)


def test_candidate_remediation_links_without_closing_and_replays_across_restart(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    _seed_release(
        target,
        release_id=CANDIDATE_RELEASE_ID,
        state="candidate",
        build_run_id=BUILD_RUN_ID,
        manifest_sha256=MANIFEST_SHA256,
        source_batch_ids=SOURCE_BATCH_IDS,
    )
    operations = _operations(module, target, clock=lambda: NOW + timedelta(hours=2))
    gap = _operations(module, target, clock=lambda: NOW).record(_signal())
    transition = operations.apply_remediation(_request(gap, state="candidate"))
    assert transition.transition_state == "linked"
    assert transition.gap.status.value == "planned"
    replayed = _operations(
        module, target, clock=lambda: NOW + timedelta(hours=3)
    ).apply_remediation(_request(gap, state="candidate"))
    assert replayed == transition
    detail = operations.get_for_admin(gap.gap_id)
    assert detail is not None and detail.transitions == (transition,)


def test_only_durable_exact_accepted_release_and_later_effect_can_close(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    _seed_release(
        target,
        release_id=CANDIDATE_RELEASE_ID,
        state="accepted",
        build_run_id=BUILD_RUN_ID,
        manifest_sha256=MANIFEST_SHA256,
        source_batch_ids=SOURCE_BATCH_IDS,
    )
    gap = _operations(module, target, clock=lambda: NOW).record(_signal())
    request_value = _request(gap, state="accepted")
    operations = _operations(module, target, clock=lambda: NOW + timedelta(hours=2))
    for table, bad_statement, bad_parameters, restore_statement, restore_parameters in (
        (
            "publish.build_manifest",
            "UPDATE publish.build_manifest SET manifest_version=%s WHERE release_id=%s",
            ("canonical-v2-build-manifest-v1", CANDIDATE_RELEASE_ID),
            "UPDATE publish.build_manifest SET manifest_version=%s WHERE release_id=%s",
            ("canonical-v2-build-manifest-v2", CANDIDATE_RELEASE_ID),
        ),
        (
            "publish.build_manifest",
            "UPDATE publish.build_manifest SET source_batches_sha256=%s WHERE release_id=%s",
            ("e" * 64, CANDIDATE_RELEASE_ID),
            "UPDATE publish.build_manifest SET source_batches_sha256=%s WHERE release_id=%s",
            (
                _canonical_sha256({"source_batch_ids": list(SOURCE_BATCH_IDS)}),
                CANDIDATE_RELEASE_ID,
            ),
        ),
        (
            "publish.manifest_section",
            "UPDATE publish.manifest_section SET record_count=2 "
            "WHERE release_id=%s AND section_id='objects:professor'",
            (CANDIDATE_RELEASE_ID,),
            "UPDATE publish.manifest_section SET record_count=1 "
            "WHERE release_id=%s AND section_id='objects:professor'",
            (CANDIDATE_RELEASE_ID,),
        ),
        (
            "publish.manifest_section",
            "UPDATE publish.manifest_section SET record_count=2 "
            "WHERE release_id=%s AND section_id='relationships'",
            (CANDIDATE_RELEASE_ID,),
            "UPDATE publish.manifest_section SET record_count=1 "
            "WHERE release_id=%s AND section_id='relationships'",
            (CANDIDATE_RELEASE_ID,),
        ),
    ):
        table_identifier = sql.Identifier(*table.split("."))
        with psycopg.connect(
            _psycopg_dsn(target.database_url), autocommit=True
        ) as connection:
            connection.execute(
                sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(table_identifier)
            )
            connection.execute(
                sql.SQL(cast(LiteralString, bad_statement)), bad_parameters
            )
            connection.execute(
                sql.SQL("ALTER TABLE {} ENABLE TRIGGER USER").format(table_identifier)
            )
        try:
            with pytest.raises(module.KnowledgeGapIntegrityError):
                operations.apply_remediation(request_value)
        finally:
            with psycopg.connect(
                _psycopg_dsn(target.database_url), autocommit=True
            ) as connection:
                connection.execute(
                    sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(
                        table_identifier
                    )
                )
                connection.execute(
                    sql.SQL(cast(LiteralString, restore_statement)),
                    restore_parameters,
                )
                connection.execute(
                    sql.SQL("ALTER TABLE {} ENABLE TRIGGER USER").format(
                        table_identifier
                    )
                )
        with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
            assert connection.execute(
                "SELECT count(*) FROM ops.gap_remediation_transition"
            ).fetchone() == (0,)
    wrong_candidate = _candidate(state="accepted").model_copy(
        update={"manifest_sha256": "d" * 64}
    )
    wrong_payload = {
        field: getattr(request_value, field)
        for field in type(request_value).model_fields
        if field != "content_sha256"
    }
    wrong_payload["candidate_release"] = wrong_candidate
    with pytest.raises(module.KnowledgeGapIntegrityError):
        operations.apply_remediation(
            _content_bound(GapRemediationRequest, wrong_payload)
        )
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM ops.gap_remediation_transition"
        ).fetchone() == (0,)
    result = operations.apply_remediation(request_value)
    assert result.transition_state == "resolved"
    assert result.gap.resolved_release_id == CANDIDATE_RELEASE_ID
    assert operations.get_for_admin(gap.gap_id).gap == result.gap


def test_concurrent_stale_crosswired_or_tampered_transitions_fail_atomically(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    _seed_release(
        target,
        release_id=CANDIDATE_RELEASE_ID,
        state="candidate",
        build_run_id=BUILD_RUN_ID,
        manifest_sha256=MANIFEST_SHA256,
        source_batch_ids=SOURCE_BATCH_IDS,
    )
    gap = _operations(module, target, clock=lambda: NOW).record(_signal())
    value = _request(gap, state="candidate")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda _: _operations(
                    module, target, clock=lambda: NOW + timedelta(hours=2)
                ).apply_remediation(value),
                range(2),
            )
        )
    assert results[0] == results[1]
    stale_payload = {
        field: getattr(value, field)
        for field in type(value).model_fields
        if field != "content_sha256"
    }
    stale_payload["request_id"] = "request:s10o:stale-branch"
    stale = _content_bound(GapRemediationRequest, stale_payload)
    with pytest.raises(module.KnowledgeGapIntegrityError):
        _operations(
            module, target, clock=lambda: NOW + timedelta(hours=3)
        ).apply_remediation(stale)
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM ops.gap_remediation_transition"
        ).fetchone() == (1,)
    crosswired_gap = _operations(module, target, clock=lambda: NOW).record(
        _signal(signal_id="signal:s10o:crosswired-stored-transition")
    )
    crosswired_request = _request(crosswired_gap, state="candidate")
    crosswired_result = create_ephemeral_knowledge_gap_feedback(
        clock=lambda: NOW + timedelta(hours=2)
    ).apply_remediation(crosswired_request)
    with psycopg.connect(_psycopg_dsn(target.database_url)) as connection:
        connection.execute(
            "INSERT INTO ops.gap_remediation_transition "
            "(transition_id, gap_id, source_release_id, candidate_release_id, "
            "transition_state, remediation_input_sha256, result_content_sha256, "
            "request_payload, result_payload, transitioned_at) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)",
            (
                crosswired_result.transition_id,
                crosswired_gap.gap_id,
                CANDIDATE_RELEASE_ID,
                SOURCE_RELEASE_ID,
                crosswired_result.transition_state,
                crosswired_request.content_sha256,
                crosswired_result.content_sha256,
                crosswired_request.model_dump_json(),
                crosswired_result.model_dump_json(),
                crosswired_result.gap.updated_at,
            ),
        )
        connection.commit()
    with pytest.raises(module.KnowledgeGapIntegrityError):
        _operations(module, target, clock=lambda: NOW).get_for_admin(
            crosswired_gap.gap_id
        )


def test_admin_read_model_joins_gap_assertion_decision_release_and_provenance_honestly(
    request: pytest.FixtureRequest,
) -> None:
    module = _postgres_module()
    target = request.getfixturevalue("target")
    fixture_path = Path(__file__).with_name("test_canonical_decision_postgres.py")
    spec = importlib.util.spec_from_file_location(
        "_s10o_accepted_decision_fixture", fixture_path
    )
    assert spec is not None and spec.loader is not None
    fixture_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixture_module
    spec.loader.exec_module(fixture_module)
    fixture_module._insert_prerequisites(target)
    accepted_result = fixture_module._decision_result()
    fixture_module._store(target).persist(accepted_result)
    _seed_release(target, release_id=SOURCE_RELEASE_ID, state="accepted")
    _seed_release(
        target,
        release_id=CANDIDATE_RELEASE_ID,
        state="candidate",
        build_run_id=BUILD_RUN_ID,
        manifest_sha256=MANIFEST_SHA256,
        source_batch_ids=SOURCE_BATCH_IDS,
    )
    gap = _operations(module, target, clock=lambda: NOW).record(
        _signal(evidence_ids=("field-b", "relation-founder", "web:s10o:unmatched"))
    )
    high = _operations(
        module, target, clock=lambda: NOW + timedelta(minutes=10)
    ).record(
        _signal(
            signal_id="signal:s10o:admin:high-web-demand",
            trigger=GapTrigger.repeated_web_dependence,
            affected_domains=("company",),
            affected_paths=("company:current_web",),
            demand_observation_ids=("demand:high:1", "demand:high:2"),
        )
    )
    demand = _operations(
        module, target, clock=lambda: NOW + timedelta(minutes=20)
    ).record(
        _signal(
            signal_id="signal:s10o:admin:medium-demand",
            trigger=GapTrigger.no_result,
            affected_domains=("paper",),
            affected_paths=("paper:title",),
            demand_observation_ids=(
                "demand:medium:1",
                "demand:medium:2",
                "demand:medium:3",
            ),
        )
    )
    tied = tuple(
        _operations(module, target, clock=lambda: NOW + timedelta(minutes=30)).record(
            _signal(
                signal_id=f"signal:s10o:admin:tie:{ordinal}",
                affected_domains=("professor", "patent"),
                affected_paths=(f"professor:patent:{ordinal}",),
            )
        )
        for ordinal in (1, 2)
    )
    link_gap = _operations(module, target, clock=lambda: NOW).record(
        _signal(
            signal_id="signal:s10o:admin:linked-history",
            affected_domains=("patent",),
            affected_paths=("patent:linked_history",),
        )
    )
    linked = _operations(
        module, target, clock=lambda: NOW + timedelta(hours=2)
    ).apply_remediation(_request(link_gap, state="candidate"))
    operations = _operations(module, target, clock=lambda: NOW)
    tied_order = tuple(sorted(tied, key=lambda item: item.gap_id))
    expected_order = (high, demand, linked.gap, *tied_order, gap)
    all_page = operations.list_for_admin(module.GapAdminQuery(limit=200))
    assert all_page.total == 6
    assert all_page.items == expected_order
    filter_matrix = (
        (module.GapAdminQuery(statuses=("open",)), (high, demand, *tied_order, gap)),
        (module.GapAdminQuery(statuses=("planned",)), (linked.gap,)),
        (module.GapAdminQuery(statuses=("resolved",)), ()),
        (
            module.GapAdminQuery(gap_classes=("relationship",)),
            (linked.gap, *tied_order, gap),
        ),
        (
            module.GapAdminQuery(gap_classes=("knowledge_coverage",)),
            (high, demand),
        ),
        (module.GapAdminQuery(gap_classes=("context",)), ()),
        (module.GapAdminQuery(severities=("high",)), (high,)),
        (
            module.GapAdminQuery(severities=("medium",)),
            (demand, linked.gap, *tied_order, gap),
        ),
        (module.GapAdminQuery(severities=("low",)), ()),
        (module.GapAdminQuery(domain="company"), (high,)),
        (module.GapAdminQuery(domain="unknown"), ()),
        (module.GapAdminQuery(path="paper:title"), (demand,)),
        (module.GapAdminQuery(path="unknown:path"), ()),
        (module.GapAdminQuery(release_id=SOURCE_RELEASE_ID), expected_order),
        (module.GapAdminQuery(release_id=CANDIDATE_RELEASE_ID), (linked.gap,)),
        (module.GapAdminQuery(release_id="release:missing"), ()),
    )
    for query, expected in filter_matrix:
        page = operations.list_for_admin(query)
        assert page.total == len(expected)
        assert page.items == expected
    bounded = operations.list_for_admin(module.GapAdminQuery(limit=2, offset=1))
    assert bounded.total == len(expected_order)
    assert bounded.items == expected_order[1:3]
    assert bounded.limit == 2 and bounded.offset == 1
    detail = operations.get_for_admin(gap.gap_id)
    assert detail is not None
    assert detail.gap == gap and detail.transitions == ()
    assert detail.releases[0]["release_id"] == SOURCE_RELEASE_ID
    assert tuple(row["assertion_id"] for row in detail.field_assertions) == ("field-b",)
    assert tuple(row["assertion_id"] for row in detail.relationship_assertions) == (
        "relation-founder",
    )
    expected_canonical_decision_id = next(
        decision.decision_id
        for decision in accepted_result.canonical_decisions
        if "field-b" in decision.selected_assertion_ids
    )
    expected_relationship_decision_id = next(
        decision.decision_id
        for decision in accepted_result.relationship_decisions
        if "relation-founder" in decision.selected_assertion_ids
    )
    assert tuple(row["decision_id"] for row in detail.canonical_decisions) == (
        expected_canonical_decision_id,
    )
    assert tuple(row["decision_id"] for row in detail.relationship_decisions) == (
        expected_relationship_decision_id,
    )
    assert tuple(row["source_record"]["record_id"] for row in detail.provenance) == (
        "record:prof-source-b",
        "record:relationship",
    )
    assert tuple(row["artifact"]["artifact_id"] for row in detail.provenance) == (
        "decision-artifact-1",
        "decision-artifact-1",
    )
    assert detail.unresolved_evidence_ids == ("web:s10o:unmatched",)
