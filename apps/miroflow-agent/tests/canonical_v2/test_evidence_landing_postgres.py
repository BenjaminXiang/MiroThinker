from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import errors
from psycopg import sql
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import make_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0004"
EXPECTED_DATABASE = "miroflow_canonical_v2_s4c_disposable"
EXPECTED_MARKER = (
    "miroflow:destructive-target:v1:disposable:miroflow_canonical_v2_s4c_disposable"
)
NOW = datetime(2026, 7, 11, 19, 15, tzinfo=timezone.utc)


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
            "Canonical V2 landing persistence requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _migration_config(target: _Target) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", target.database_url)
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


def _verify_target(database_url: str) -> None:
    with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as connection:
        actual_database, marker = connection.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()  # type: ignore[misc]
        assert actual_database == EXPECTED_DATABASE
        assert marker == EXPECTED_MARKER


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert expected_database == EXPECTED_DATABASE
    assert target_kind == "disposable"
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    provisional = _Target(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
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
    command.upgrade(configured.config, "head")
    _verify_target(database_url)
    try:
        yield configured
    finally:
        command.downgrade(configured.config, "C2_0001")
        command.upgrade(configured.config, "head")


def _module() -> Any:
    return import_module("src.data_agents.canonical_v2.evidence_landing_postgres")


def _core() -> Any:
    return import_module("src.data_agents.canonical_v2.evidence_landing")


def _landing(target: _Target) -> Any:
    return _module().create_postgres_evidence_landing(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )


def _request(
    *,
    run_id: str,
    batch: str,
    source_kind: str,
    source_locator: str,
    content: bytes,
    parser_version: str = "v1",
    parser_options: dict[str, Any] | None = None,
    parent_artifact_id: str | None = None,
    parent_content_sha256: str | None = None,
) -> Any:
    core = _core()
    return core.IngestEvidenceRequest(
        run_id=run_id,
        source_batch_id=batch,
        source_kind=source_kind,
        source_locator=source_locator,
        content=content,
        observed_at=NOW,
        expected_content_sha256=hashlib.sha256(content).hexdigest(),
        parser=core.ParserReference(
            parser_name="historical_jsonl",
            parser_version=parser_version,
            schema_version="historical-record-v1",
            options=parser_options or {},
        ),
        parent_artifact_id=parent_artifact_id,
        parent_content_sha256=parent_content_sha256,
    )


def _connect(target: _Target, *, autocommit: bool = False) -> Any:
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def test_c2_0004_declares_durable_landing_run_order_and_parser_configuration() -> None:
    scripts = ScriptDirectory.from_config(
        Config(str(ALEMBIC_INI), config_args={"script_location": str(SCRIPT_LOCATION)})
    )

    revision = scripts.get_revision(EXPECTED_REVISION)

    assert revision is not None
    assert revision.down_revision == "C2_0003"


def test_c2_0004_refuses_unaccounted_existing_c2_0003_landing_rows(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0003")
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES (%s, 'historical_jsonl', %s, %s, 2, %s, %s)",
            (
                "pre-c2-0004-artifact",
                "verified/pre-c2-0004.jsonl",
                hashlib.sha256(b"{}").hexdigest(),
                NOW,
                "pre-c2-0004-run",
            ),
        )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError, match="empty C2_0003 landing"):
        command.upgrade(target.config, "head")

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0003",)
        assert connection.execute(
            "SELECT artifact_id FROM landing.evidence_artifact"
        ).fetchone() == ("pre-c2-0004-artifact",)


def test_postgres_landing_survives_restart_with_exact_order_errors_and_options(
    target: _Target,
) -> None:
    content = (
        b'{"source_id":"paper-1","title":"First"}\n'
        b'{"source_id":"paper-2","abstract":{"$unreadable_external":"toast:2"}}\n'
        b'{"source_id":"paper-nan","score":NaN}\n'
    )
    request = _request(
        run_id="postgres-restart-run",
        batch="postgres-restart-batch",
        source_kind="historical_jsonl",
        source_locator="verified/history/restart.jsonl",
        content=content,
        parser_options={"mode": "audit"},
    )

    receipt = _landing(target).ingest(request)
    restarted = _landing(target)
    assert restarted.ingest(request) == receipt
    records = restarted.stream(request.source_batch_id)

    assert [record.record_locator for record in records] == [
        "line:1",
        "line:2",
        "line:3",
    ]
    assert [record.parse_status.value for record in records] == [
        "parsed",
        "partial",
        "corrupt",
    ]
    assert records[1].errors[0].field_path == "abstract"
    assert records[2].errors[0].error_kind.value == "corrupt_content"

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT parser_options FROM landing.parser_run WHERE parse_run_id = %s",
            (receipt.parse_run_id,),
        ).fetchone() == ({"mode": "audit"},)
        assert connection.execute(
            "SELECT record_ordinal FROM landing.source_record "
            "WHERE parse_run_id = %s ORDER BY record_ordinal",
            (receipt.parse_run_id,),
        ).fetchall() == [(0,), (1,), (2,)]
        assert connection.execute(
            "SELECT (SELECT count(*) FROM landing.evidence_artifact), "
            "(SELECT count(*) FROM landing.ingest_run), "
            "(SELECT count(*) FROM landing.parser_run), "
            "(SELECT count(*) FROM landing.source_record), "
            "(SELECT count(*) FROM landing.source_error)"
        ).fetchone() == (1, 1, 1, 3, 2)
        with pytest.raises(errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE landing.parser_run SET parser_options = '{}'::jsonb "
                "WHERE parse_run_id = %s",
                (receipt.parse_run_id,),
            )
        connection.rollback()
    for statement in (
        "UPDATE landing.ingest_run SET record_count = 99",
        "DELETE FROM landing.ingest_run",
        "TRUNCATE landing.ingest_run",
    ):
        with _connect(target) as connection:
            with pytest.raises(errors.ObjectNotInPrerequisiteState):
                connection.execute(statement)
            connection.rollback()


def test_concurrent_exact_run_commits_once_and_conflict_leaves_no_artifact(
    target: _Target,
) -> None:
    request = _request(
        run_id="postgres-concurrent-run",
        batch="postgres-concurrent-batch",
        source_kind="historical_jsonl",
        source_locator="verified/history/concurrent.jsonl",
        content=b'{"source_id":"paper-concurrent"}\n',
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = tuple(
            executor.map(lambda _: _landing(target).ingest(request), range(2))
        )

    assert receipts[0] == receipts[1]
    conflict = _request(
        run_id=request.run_id,
        batch=request.source_batch_id,
        source_kind=request.source_kind,
        source_locator=request.source_locator,
        content=b'{"source_id":"paper-conflict"}\n',
    )
    with pytest.raises(_core().EvidenceIntegrityError, match="run_id"):
        _landing(target).ingest(conflict)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT (SELECT count(*) FROM landing.ingest_run), "
            "(SELECT count(*) FROM landing.evidence_artifact), "
            "(SELECT count(*) FROM landing.parser_run), "
            "(SELECT count(*) FROM landing.source_record)"
        ).fetchone() == (1, 1, 1, 1)


def test_concurrent_distinct_runs_share_one_artifact_without_lost_replay(
    target: _Target,
) -> None:
    content = b'{"source_id":"paper-shared-artifact"}\n'
    requests = tuple(
        _request(
            run_id=f"shared-artifact-run-{suffix}",
            batch=f"shared-artifact-batch-{suffix}",
            source_kind="historical_jsonl",
            source_locator="verified/history/shared-artifact.jsonl",
            content=content,
        )
        for suffix in ("one", "two")
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = tuple(
            executor.map(
                lambda request: _landing(target).ingest(request),
                requests,
            )
        )

    assert receipts[0].artifact_id == receipts[1].artifact_id
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT (SELECT count(*) FROM landing.evidence_artifact), "
            "(SELECT count(*) FROM landing.ingest_run), "
            "(SELECT count(*) FROM landing.parser_run), "
            "(SELECT count(*) FROM landing.source_record)"
        ).fetchone() == (1, 2, 2, 2)


def test_parent_copy_and_new_parser_run_coexist_without_rewriting_prior_records(
    target: _Target,
) -> None:
    content = b'{"source_id":"paper-lineage","title":"Retained"}\n'
    source = _landing(target).ingest(
        _request(
            run_id="postgres-parent-run",
            batch="postgres-parent-batch",
            source_kind="forensic_source",
            source_locator="verified/source/lineage.jsonl",
            content=content,
        )
    )
    copied_request = _request(
        run_id="postgres-copy-v1-run",
        batch="postgres-copy-batch",
        source_kind="verified_copy",
        source_locator="verified/copy/lineage.jsonl",
        content=content,
        parent_artifact_id=source.artifact_id,
        parent_content_sha256=source.content_sha256,
    )
    copied = _landing(target).ingest(copied_request)
    replayed = _landing(target).ingest(
        copied_request.model_copy(
            update={
                "run_id": "postgres-copy-v2-run",
                "parser": copied_request.parser.model_copy(
                    update={"parser_version": "v2"}
                ),
            }
        )
    )

    records = _landing(target).stream("postgres-copy-batch")
    assert [record.parser_version for record in records] == ["v1", "v2"]
    assert (
        records[0].payload
        == records[1].payload
        == {
            "source_id": "paper-lineage",
            "title": "Retained",
        }
    )
    assert copied.parse_run_id != replayed.parse_run_id
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT parent_artifact_id, parent_content_sha256 "
            "FROM landing.evidence_artifact WHERE artifact_id = %s",
            (copied.artifact_id,),
        ).fetchone() == (source.artifact_id, source.content_sha256)
        assert connection.execute(
            "SELECT count(*) FROM landing.evidence_artifact"
        ).fetchone() == (2,)


def test_registered_large_copy_survives_restart_and_can_parent_a_derived_run(
    target: _Target,
    tmp_path: Path,
) -> None:
    core = _core()
    content_path = tmp_path / "verified-large-copy.bin"
    content_path.write_bytes((b"registered-parent\0" * 8192) + b"tail")
    parent_sha256 = hashlib.sha256(content_path.read_bytes()).hexdigest()
    registration = core.RegisterArtifactRequest(
        run_id="postgres-register-parent",
        source_kind="verified_restore_copy",
        source_locator="s2b-restore://run/verified-large-copy.bin",
        content_path=content_path,
        observed_at=NOW,
        expected_content_sha256=parent_sha256,
        expected_byte_size=content_path.stat().st_size,
    )

    parent = _landing(target).register_artifact(registration)
    assert _landing(target).register_artifact(registration) == parent
    derived_content = b'{"source_id":"derived-from-large-copy"}\n'
    derived = _landing(target).ingest(
        _request(
            run_id="postgres-derived-child",
            batch="postgres-derived-child",
            source_kind="verified_copy",
            source_locator="s2b-derived://run/child.jsonl",
            content=derived_content,
            parent_artifact_id=parent.artifact_id,
            parent_content_sha256=parent.content_sha256,
        )
    )

    assert derived.parent_artifact_id == parent.artifact_id
    assert _landing(target).stream(derived.source_batch_id)[0].payload == {
        "source_id": "derived-from-large-copy"
    }
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT (SELECT count(*) FROM landing.evidence_artifact), "
            "(SELECT count(*) FROM landing.ingest_run), "
            "(SELECT count(*) FROM landing.source_record)"
        ).fetchone() == (2, 1, 1)


def test_database_failure_rolls_back_artifact_parser_records_errors_and_run(
    target: _Target,
) -> None:
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "CREATE FUNCTION landing.reject_s4c_test_insert() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced insert failure'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER trg_reject_s4c_test_insert BEFORE INSERT "
            "ON landing.source_record FOR EACH ROW "
            "WHEN (NEW.source_batch_id = 'atomic-failure-batch') "
            "EXECUTE FUNCTION landing.reject_s4c_test_insert()"
        )
    try:
        with pytest.raises(_core().EvidenceLandingPersistenceError):
            _landing(target).ingest(
                _request(
                    run_id="atomic-failure-run",
                    batch="atomic-failure-batch",
                    source_kind="historical_jsonl",
                    source_locator="verified/history/atomic-failure.jsonl",
                    content=b'{"source_id":"paper-atomic"}\n',
                )
            )
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT (SELECT count(*) FROM landing.evidence_artifact), "
                "(SELECT count(*) FROM landing.ingest_run), "
                "(SELECT count(*) FROM landing.parser_run), "
                "(SELECT count(*) FROM landing.source_record), "
                "(SELECT count(*) FROM landing.source_error)"
            ).fetchone() == (0, 0, 0, 0, 0)
    finally:
        with _connect(target, autocommit=True) as connection:
            connection.execute(
                "DROP TRIGGER IF EXISTS trg_reject_s4c_test_insert "
                "ON landing.source_record"
            )
            connection.execute(
                "DROP FUNCTION IF EXISTS landing.reject_s4c_test_insert()"
            )


def test_postgres_factory_rejects_unaccepted_gate_before_connect(
    tmp_path: Path,
    target: _Target,
) -> None:
    gate_module = import_module("src.data_agents.canonical_v2.rebuild_write_gate")

    with pytest.raises(gate_module.RebuildWriteGateError):
        _module().create_postgres_evidence_landing(
            database_url=(
                "postgresql+psycopg://miroflow@unresolvable.invalid/"
                "miroflow_canonical_v2_s4c_disposable"
            ),
            expected_database=EXPECTED_DATABASE,
            target_kind="disposable",
            backup_gate_root=tmp_path,
        )

    relative_accepted_root = Path(os.path.relpath(target.backup_gate_root, Path.cwd()))
    assert not relative_accepted_root.is_absolute()
    with pytest.raises(gate_module.RebuildWriteGateError, match="absolute"):
        _module().create_postgres_evidence_landing(
            database_url=(
                "postgresql+psycopg://miroflow@unresolvable.invalid/"
                "miroflow_canonical_v2_s4c_disposable"
            ),
            expected_database=EXPECTED_DATABASE,
            target_kind="disposable",
            backup_gate_root=relative_accepted_root,
        )


def test_postgres_factory_refuses_read_only_candidate_behind_required_revision(
    target: _Target,
) -> None:
    isolated_marker = (
        f"miroflow:destructive-target:v1:isolated-candidate:{target.expected_database}"
    )
    command.downgrade(target.config, "C2_0003")
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(target.expected_database),
                sql.Literal(isolated_marker),
            )
        )
    try:
        with pytest.raises(
            _core().EvidenceLandingPersistenceError,
            match="C2_0004",
        ):
            _module().create_postgres_evidence_landing(
                database_url=target.database_url,
                expected_database=target.expected_database,
                target_kind="isolated-candidate",
                backup_gate_root=target.backup_gate_root,
            )
    finally:
        with _connect(target, autocommit=True) as connection:
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(target.expected_database),
                    sql.Literal(EXPECTED_MARKER),
                )
            )
        command.upgrade(target.config, "head")
