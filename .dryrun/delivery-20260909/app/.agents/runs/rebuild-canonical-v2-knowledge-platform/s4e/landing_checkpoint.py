#!/usr/bin/env python3
"""Create and independently restore-verify the Canonical V2 S4 landing checkpoint."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


class CheckpointError(RuntimeError):
    """The landing checkpoint cannot be accepted without weakening its contract."""


_LANDING_TABLE_COUNTS = {
    "landing.evidence_artifact": 15,
    "landing.ingest_run": 6,
    "landing.parser_run": 6,
    "landing.source_error": 6,
    "landing.source_record": 21,
}
_ARTIFACT_KIND_COUNTS = {
    "historical_jsonl": 1,
    "historical_sqlite": 1,
    "historical_xlsx": 1,
    "milvus_verified_copy_records": 1,
    "recorded_collected_response": 1,
    "verified_backup_copy": 6,
    "verified_restore_copy": 3,
    "wal_fpi_salvage_records": 1,
}
_LINEAGE_COUNTS = {
    "matching_parent_edges": 9,
    "orphan_parent_edges": 0,
    "parent_edges": 9,
    "roots": 6,
}
_RUN_STATUS_COUNTS = {"accepted": 4, "partial": 2}
_RECORD_STATUS_COUNTS = {"parsed": 17, "partial": 4}
_ERROR_KIND_COUNTS = {
    "missing_external_content": 3,
    "schema_mismatch": 3,
}
_EXPECTED_TABLES = frozenset(
    {
        "knowledge.canonical_decision",
        "knowledge.canonical_decision_assertion",
        "knowledge.canonical_identity",
        "knowledge.identity_decision",
        "knowledge.identity_decision_input",
        "knowledge.identity_decision_output",
        "knowledge.identity_decision_record",
        "knowledge.identity_decision_source_identity",
        "knowledge.policy",
        "knowledge.relationship_assertion",
        "knowledge.relationship_decision",
        "knowledge.relationship_decision_assertion",
        "knowledge.relationship_type",
        "knowledge.release",
        "knowledge.source_assertion",
        "knowledge.source_identity",
        "knowledge.source_identity_record",
        "landing.evidence_artifact",
        "landing.ingest_run",
        "landing.parser_run",
        "landing.source_error",
        "landing.source_record",
        "public.canonical_v2_alembic_version",
        "publish.active_release",
        "publish.build_manifest",
        "publish.manifest_section",
    }
)
_EXPECTED_INTEGRITY_KEYS = frozenset(
    {
        "artifact_cycle",
        "artifact_invalid_identity",
        "artifact_orphan_parent",
        "artifact_self_parent",
        "error_orphan_record",
        "ingest_orphan_artifact_or_parser",
        "parser_incomplete_identity",
        "parser_orphan_artifact",
        "partial_record_without_error",
        "record_incomplete_identity",
        "record_orphan_artifact_or_parser",
    }
)
_EXPECTED_INPUTS = {
    "landing_matrix_sha256": (
        "eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923"
    ),
    "landing_replay_summary_sha256": (
        "a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5"
    ),
    "matrix_entries_sha256": (
        "5b77b4a4f3ea9f0a0fd4667dfccff6afefa968b5fb43124de816e652d1c58293"
    ),
}
_EXPECTED_GATE = {
    "acceptance_record_sha256": (
        "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
    ),
    "backup_manifest_sha256": (
        "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
    ),
    "restore_verification_sha256": (
        "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
    ),
    "source_count": 50,
    "source_inventory_sha256": (
        "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
    ),
    "state": "accepted",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_REPO_ROOT = Path(__file__).resolve().parents[4]
_APP_ROOT = _REPO_ROOT / "apps/miroflow-agent"
_RUN_ROOT = Path(__file__).resolve().parents[1]
_S4D_TOOL = _RUN_ROOT / "s4d/replay_landing_matrix.py"
_SCHEMA_FINGERPRINT_TOOL = _APP_ROOT / "scripts/canonical_v2_schema_fingerprint.py"
_ALLOWED_CHECKPOINT_PARENT = Path("/md1/mirothinker-backups")
_ALLOWED_SOCKET_PARENT = Path("/var/tmp/mirothinker-canonical-v2")
_CANDIDATE_CONTAINER = "canonical-v2-s3b-pg-20260711"
_CANDIDATE_DATABASE = "miroflow_canonical_v2_candidate_s3b"
_DATABASE_USER = "miroflow"
_TASK4_4_COMMIT = "cef42a1e075d30c5a0e179f34ab543b4878edabd"
_THRESHOLD_REGISTRY_SHA256 = (
    "bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc"
)
_CORPUS_MANIFEST_SHA256 = (
    "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088"
)
_EXPECTED_IMPLEMENTATION_PATHS = frozenset(
    {
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/"
        "replay_landing_matrix.py",
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/"
        "landing_checkpoint.py",
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/"
        "test_landing_checkpoint.py",
        "apps/miroflow-agent/tests/canonical_v2/test_landing_matrix_replay.py",
    }
)
_EXPECTED_CANDIDATE_TARGET: dict[str, Any] = {
    "container_name": _CANDIDATE_CONTAINER,
    "container_running": True,
    "database": _CANDIDATE_DATABASE,
    "database_marker": (
        f"miroflow:destructive-target:v1:isolated-candidate:{_CANDIDATE_DATABASE}"
    ),
    "error_kind_counts": _ERROR_KIND_COUNTS,
    "kind": "isolated-candidate",
    "landing_counts": {
        "evidence_artifact": 15,
        "ingest_run": 6,
        "parser_run": 6,
        "source_error": 6,
        "source_record": 21,
    },
    "lineage_counts": _LINEAGE_COUNTS,
    "network_mode": "none",
    "non_landing_row_count": 0,
    "pgdata_volume": "canonical-v2-s3b-pgdata-20260711",
    "published_ports": [],
    "record_status_counts": _RECORD_STATUS_COUNTS,
    "restart_policy": "no",
    "revision": "C2_0004",
    "run_status_counts": _RUN_STATUS_COUNTS,
    "system_identifier": "7661313446684311592",
    "validated_prestate": "bounded-replay",
}


class _StrictJsonError(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _StrictJsonError(f"non-standard JSON number {value!r}")


def _strict_json_loads(value: str | bytes) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = _strict_json_loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        raise CheckpointError(f"{label} is missing or invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise CheckpointError(f"{label} must be a JSON object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise CheckpointError("evidence contains a non-canonical JSON value") from exc


def document_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                dict(value),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError) as exc:
        raise CheckpointError("evidence contains a non-serializable value") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise CheckpointError(f"checkpoint artifact is unreadable: {path}") from exc
    return digest.hexdigest()


def document_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(document_bytes(value))


def _load_python_module(path: Path, *, name: str) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CheckpointError(f"cannot load required checkpoint helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_text_command(
    argv: list[str],
    *,
    command_id: str,
    sanitized_argv: list[str] | None = None,
    check: bool = True,
    cwd: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    evidence = {
        "command_id": command_id,
        "sanitized_argv": sanitized_argv or argv,
        "exit_code": completed.returncode,
        "stdout_sha256": sha256_bytes(completed.stdout.encode()),
        "stderr_sha256": sha256_bytes(completed.stderr.encode()),
    }
    if check and completed.returncode != 0:
        raise CheckpointError(
            f"{command_id} failed with exit {completed.returncode}: "
            f"{completed.stderr[-1000:]}"
        )
    return completed, evidence


def _docker_inspect(container_name: str) -> dict[str, Any]:
    completed, _ = _run_text_command(
        ["docker", "inspect", container_name],
        command_id=f"inspect-{container_name}",
    )
    try:
        value = _strict_json_loads(completed.stdout)
    except (json.JSONDecodeError, _StrictJsonError) as exc:
        raise CheckpointError("Docker inspection returned invalid JSON") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise CheckpointError("Docker inspection did not resolve one container")
    return value[0]


def parse_exact_container_lookup(stdout: str) -> str | None:
    identities = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(identities) > 1:
        raise CheckpointError("restore container lookup is ambiguous")
    if not identities:
        return None
    identity = identities[0]
    if re.fullmatch(r"[0-9a-f]{64}", identity) is None:
        raise CheckpointError("restore container lookup returned an invalid identity")
    return identity


def _lookup_exact_container_id(container_name: str) -> str | None:
    completed, _ = _run_text_command(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"name=^/{container_name}$",
        ],
        command_id=f"lookup-{container_name}",
    )
    return parse_exact_container_lookup(completed.stdout)


def require_restore_name_absent(observed_container_id: str | None) -> None:
    if observed_container_id is not None:
        raise CheckpointError(
            "restore container name already exists; refusing to claim or remove it"
        )


def require_owned_restore_container(
    *,
    observed_container_id: str | None,
    expected_container_id: str,
) -> None:
    if (
        re.fullmatch(r"[0-9a-f]{64}", expected_container_id) is None
        or observed_container_id != expected_container_id
    ):
        raise CheckpointError("restore container ownership does not match this run")


def require_restore_cleanup(
    *,
    removed_container_id: str,
    expected_container_id: str,
    observed_container_id_after: str | None,
    socket_root_absent: bool,
) -> dict[str, Any]:
    if (
        removed_container_id != expected_container_id
        or observed_container_id_after is not None
        or not socket_root_absent
    ):
        raise CheckpointError("restore cleanup could not prove owned-target removal")
    return {
        "container_absent": True,
        "owned_container_id": expected_container_id,
        "socket_root_absent": True,
    }


def _docker_volume_set_sha256() -> str:
    completed, _ = _run_text_command(
        ["docker", "volume", "ls", "-q"],
        command_id="docker-volume-set",
    )
    names = "\n".join(sorted(line for line in completed.stdout.splitlines() if line))
    return sha256_bytes(names.encode())


def _schema_fingerprint(
    *,
    container_name: str,
    database_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    argv = [
        "docker",
        "exec",
        container_name,
        "pg_dump",
        "-U",
        _DATABASE_USER,
        "-d",
        database_name,
        "--schema-only",
        "--no-owner",
        "--no-privileges",
    ]
    completed = subprocess.run(argv, capture_output=True, check=False)
    evidence = {
        "command_id": "schema-fingerprint-dump",
        "sanitized_argv": argv,
        "exit_code": completed.returncode,
        "stdout_sha256": sha256_bytes(completed.stdout),
        "stderr_sha256": sha256_bytes(completed.stderr),
    }
    if completed.returncode != 0:
        raise CheckpointError(
            "schema-only pg_dump failed: "
            + completed.stderr.decode(errors="replace")[-1000:]
        )
    module = _load_python_module(
        _SCHEMA_FINGERPRINT_TOOL,
        name="canonical_v2_s4e_schema_fingerprint",
    )
    return dict(module.fingerprint_schema_dump(completed.stdout)), evidence


def _psycopg_dsn(database_url: str) -> str:
    try:
        from sqlalchemy.engine import make_url

        return (
            make_url(database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
    except Exception as exc:
        raise CheckpointError("explicit checkpoint database URL is invalid") from exc


def _group_counts(connection: Any, *, table: str, column: str) -> dict[str, int]:
    from psycopg import sql

    rows = connection.execute(
        sql.SQL(
            "SELECT {column}::text AS key, count(*)::int AS value "
            "FROM {schema}.{table} GROUP BY {column} ORDER BY {column}"
        ).format(
            column=sql.Identifier(column),
            schema=sql.Identifier("landing"),
            table=sql.Identifier(table),
        )
    ).fetchall()
    return {str(row["key"]): int(row["value"]) for row in rows}


def _landing_metrics(connection: Any) -> dict[str, Any]:
    artifact_kinds = _group_counts(
        connection,
        table="evidence_artifact",
        column="source_kind",
    )
    run_statuses = _group_counts(
        connection,
        table="ingest_run",
        column="landing_status",
    )
    record_statuses = _group_counts(
        connection,
        table="source_record",
        column="parse_status",
    )
    error_kinds = _group_counts(
        connection,
        table="source_error",
        column="error_kind",
    )
    lineage = connection.execute(
        "SELECT "
        "count(*) FILTER (WHERE child.parent_artifact_id IS NULL)::int AS roots, "
        "count(*) FILTER (WHERE child.parent_artifact_id IS NOT NULL)::int "
        "AS parent_edges, "
        "count(parent.artifact_id)::int AS matching_parent_edges, "
        "count(*) FILTER (WHERE child.parent_artifact_id IS NOT NULL "
        "AND parent.artifact_id IS NULL)::int AS orphan_parent_edges "
        "FROM landing.evidence_artifact AS child "
        "LEFT JOIN landing.evidence_artifact AS parent "
        "ON parent.artifact_id = child.parent_artifact_id "
        "AND parent.content_sha256 = child.parent_content_sha256"
    ).fetchone()
    if lineage is None:
        raise CheckpointError("landing lineage metrics are unavailable")
    cycle_count = connection.execute(
        "WITH RECURSIVE walk AS ("
        "SELECT artifact_id AS start_id, parent_artifact_id AS next_id, "
        "ARRAY[artifact_id]::text[] AS path, false AS cycle "
        "FROM landing.evidence_artifact "
        "UNION ALL "
        "SELECT walk.start_id, parent.parent_artifact_id, "
        "walk.path || parent.artifact_id, parent.artifact_id = ANY(walk.path) "
        "FROM walk JOIN landing.evidence_artifact AS parent "
        "ON parent.artifact_id = walk.next_id "
        "WHERE walk.next_id IS NOT NULL AND NOT walk.cycle"
        ") SELECT count(*)::int AS count FROM walk WHERE cycle"
    ).fetchone()
    assert cycle_count is not None
    integrity = connection.execute(
        "SELECT "
        "(SELECT count(*)::int FROM landing.evidence_artifact "
        "WHERE source_kind = '' OR source_locator = '' OR run_id = '' "
        "OR content_sha256 !~ '^[0-9a-f]{64}$' OR byte_size < 0 "
        "OR acquired_at IS NULL) AS artifact_invalid_identity, "
        "(SELECT count(*)::int FROM landing.evidence_artifact "
        "WHERE parent_artifact_id = artifact_id) AS artifact_self_parent, "
        "(SELECT count(*)::int FROM landing.evidence_artifact child "
        "LEFT JOIN landing.evidence_artifact parent "
        "ON parent.artifact_id = child.parent_artifact_id "
        "AND parent.content_sha256 = child.parent_content_sha256 "
        "WHERE child.parent_artifact_id IS NOT NULL "
        "AND parent.artifact_id IS NULL) AS artifact_orphan_parent, "
        "(SELECT count(*)::int FROM landing.parser_run parser "
        "LEFT JOIN landing.evidence_artifact artifact "
        "ON artifact.artifact_id = parser.artifact_id "
        "WHERE artifact.artifact_id IS NULL) AS parser_orphan_artifact, "
        "(SELECT count(*)::int FROM landing.parser_run "
        "WHERE parser_name = '' OR parser_version = '' OR schema_version = '' "
        "OR started_at IS NULL OR finished_at IS NULL "
        "OR parser_options IS NULL) AS parser_incomplete_identity, "
        "(SELECT count(*)::int FROM landing.ingest_run run "
        "LEFT JOIN landing.evidence_artifact artifact "
        "ON artifact.artifact_id = run.artifact_id "
        "AND artifact.content_sha256 = run.content_sha256 "
        "LEFT JOIN landing.parser_run parser "
        "ON parser.parse_run_id = run.parse_run_id "
        "AND parser.artifact_id = run.artifact_id "
        "WHERE artifact.artifact_id IS NULL OR parser.parse_run_id IS NULL) "
        "AS ingest_orphan_artifact_or_parser, "
        "(SELECT count(*)::int FROM landing.source_record record "
        "LEFT JOIN landing.evidence_artifact artifact "
        "ON artifact.artifact_id = record.artifact_id "
        "LEFT JOIN landing.parser_run parser "
        "ON parser.parse_run_id = record.parse_run_id "
        "AND parser.artifact_id = record.artifact_id "
        "WHERE artifact.artifact_id IS NULL OR parser.parse_run_id IS NULL) "
        "AS record_orphan_artifact_or_parser, "
        "(SELECT count(*)::int FROM landing.source_record "
        "WHERE record_locator = '' OR source_batch_id = '' "
        "OR record_ordinal < 0 OR parsed_at IS NULL) "
        "AS record_incomplete_identity, "
        "(SELECT count(*)::int FROM landing.source_error error "
        "LEFT JOIN landing.source_record record "
        "ON record.record_id = error.record_id "
        "WHERE record.record_id IS NULL) AS error_orphan_record, "
        "(SELECT count(*)::int FROM ("
        "SELECT record.record_id FROM landing.source_record record "
        "LEFT JOIN landing.source_error error ON error.record_id = record.record_id "
        "WHERE record.parse_status = 'partial' GROUP BY record.record_id "
        "HAVING count(error.record_id) = 0"
        ") AS partial_without_error) AS partial_record_without_error"
    ).fetchone()
    if integrity is None:
        raise CheckpointError("landing integrity metrics are unavailable")
    integrity_counts = {key: int(value or 0) for key, value in dict(integrity).items()}
    integrity_counts["artifact_cycle"] = int(cycle_count["count"])
    return {
        "artifact_kind_counts": artifact_kinds,
        "lineage_counts": {key: int(value) for key, value in dict(lineage).items()},
        "run_status_counts": run_statuses,
        "record_status_counts": record_statuses,
        "error_kind_counts": error_kinds,
        "integrity_violation_counts": integrity_counts,
    }


def read_database_snapshot(
    *,
    database_url: str,
    container_name: str,
    database_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row

        connect: Any = psycopg.connect
        connection: Any = connect(
            _psycopg_dsn(database_url),
            row_factory=dict_row,
            options=("-c default_transaction_read_only=on -c timezone=UTC"),
        )
    except Exception as exc:
        raise CheckpointError("logical snapshot database connection failed") from exc
    try:
        connection.execute(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ ONLY, DEFERRABLE"
        )
        revisions = connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchall()
        if len(revisions) != 1:
            raise CheckpointError("logical snapshot has ambiguous Alembic revision")
        table_records = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            "AND table_schema NOT LIKE 'pg_toast%' "
            "ORDER BY table_schema, table_name"
        ).fetchall()
        table_rows: dict[str, list[str]] = {}
        for record in table_records:
            schema_name = str(record["table_schema"])
            table_name = str(record["table_name"])
            rows = connection.execute(
                sql.SQL(
                    "SELECT to_jsonb(row_value)::text AS row_json FROM {}.{} "
                    "AS row_value"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                )
            ).fetchall()
            table_rows[f"{schema_name}.{table_name}"] = [
                str(row["row_json"]) for row in rows
            ]
        metrics = _landing_metrics(connection)
        connection.rollback()
    except CheckpointError:
        raise
    except Exception as exc:
        raise CheckpointError("logical database snapshot failed") from exc
    finally:
        connection.close()
    fingerprint, command = _schema_fingerprint(
        container_name=container_name,
        database_name=database_name,
    )
    snapshot = build_logical_snapshot(
        revision=str(revisions[0]["version_num"]),
        schema_fingerprint=fingerprint,
        table_rows=table_rows,
        landing_metrics=metrics,
    )
    require_landing_checkpoint_snapshot(snapshot)
    return snapshot, command


def _require_new_child_root(
    path: Path,
    *,
    parent: Path,
    prefix: str,
    label: str,
) -> Path:
    if not path.is_absolute():
        raise CheckpointError(f"{label} must be an explicit absolute path")
    resolved_parent = parent.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if resolved.parent != resolved_parent or not resolved.name.startswith(prefix):
        raise CheckpointError(
            f"{label} must be one new direct child of {resolved_parent} with prefix {prefix}"
        )
    if os.path.lexists(resolved):
        raise CheckpointError(f"{label} already exists")
    return resolved


def _write_document_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if not path.is_absolute():
        raise CheckpointError("evidence document path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path):
        raise CheckpointError(f"evidence document already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise CheckpointError(f"evidence document already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _file_tree_sha256(root: Path) -> str:
    resolved = root.resolve(strict=True)
    rows: list[str] = []
    for path in sorted(path for path in resolved.rglob("*") if path.is_file()):
        relative = path.relative_to(resolved).as_posix()
        rows.append(f"{relative}|{path.stat().st_size}|{sha256_file(path)}\n")
    return sha256_bytes("".join(rows).encode())


def _git_evidence() -> dict[str, Any]:
    head, head_command = _run_text_command(
        ["git", "rev-parse", "HEAD"],
        command_id="git-head",
        cwd=_REPO_ROOT,
    )
    status, status_command = _run_text_command(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        command_id="git-status",
        cwd=_REPO_ROOT,
    )
    diff, diff_command = _run_text_command(
        ["git", "diff", "--binary", "HEAD", "--"],
        command_id="git-worktree-diff",
        cwd=_REPO_ROOT,
    )
    commit = head.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CheckpointError("git HEAD is not one full commit identity")
    state = "clean" if not status.stdout else "task4.5-dirty"
    return {
        "commit": commit,
        "state": state,
        "status_sha256": sha256_bytes(status.stdout.encode()),
        "diff_sha256": sha256_bytes(diff.stdout.encode()),
        "commands": [head_command, status_command, diff_command],
    }


def _implementation_artifacts() -> dict[str, str]:
    artifacts = {
        relative_path: sha256_file(_REPO_ROOT / relative_path)
        for relative_path in sorted(_EXPECTED_IMPLEMENTATION_PATHS)
    }
    require_implementation_artifacts(artifacts)
    return artifacts


def _candidate_target(
    *,
    database_url: str,
) -> tuple[Any, dict[str, Any]]:
    module = _load_python_module(
        _S4D_TOOL,
        name="canonical_v2_s4e_replay_guard",
    )
    observation = module.observe_replay_target(
        database_url=database_url,
        contract=module._CANDIDATE_TARGET_CONTRACT,
    )
    target = module.require_replay_target(
        observation,
        contract=module._CANDIDATE_TARGET_CONTRACT,
        expected_prestate="bounded-replay",
    )
    return module, target


def _accepted_gate(evidence_root: Path) -> dict[str, Any]:
    if str(_APP_ROOT) not in sys.path:
        sys.path.insert(0, str(_APP_ROOT))
    from src.data_agents.canonical_v2.rebuild_write_gate import (
        require_accepted_backup_gate,
    )

    receipt = require_accepted_backup_gate(evidence_root)
    document = {
        "acceptance_record_sha256": receipt.acceptance_record_sha256,
        "backup_manifest_sha256": receipt.backup_manifest_sha256,
        "restore_verification_sha256": receipt.restore_verification_sha256,
        "source_count": receipt.source_count,
        "source_inventory_sha256": receipt.source_inventory_sha256,
        "state": receipt.state,
    }
    _require_exact_gate(document)
    return document


def _checkpoint_inputs(
    *,
    evidence_root: Path,
    fresh_replay_summary: Path,
    fresh_replay_execution: Path,
) -> dict[str, Any]:
    matrix_path = evidence_root / "s4d/landing-matrix.json"
    replay_path = evidence_root / "s4d/landing-replay-summary.json"
    replay = load_json_object(replay_path, label="committed landing replay summary")
    fresh = load_json_object(
        fresh_replay_summary,
        label="fresh guarded replay summary",
    )
    execution = load_json_object(
        fresh_replay_execution,
        label="fresh guarded replay execution",
    )
    committed_summary_sha256 = sha256_file(replay_path)
    fresh_summary_sha256 = sha256_file(fresh_replay_summary)
    if fresh != replay or fresh_summary_sha256 != committed_summary_sha256:
        raise CheckpointError(
            "fresh guarded replay summary is not byte-identical to the committed summary"
        )
    require_fresh_replay_execution(execution)
    inputs: dict[str, Any] = {
        "landing_matrix_sha256": sha256_file(matrix_path),
        "landing_replay_summary_sha256": committed_summary_sha256,
        "matrix_entries_sha256": replay.get("matrix_entries_sha256"),
        "fresh_guarded_replay_summary": {
            "relative_path": "fresh-guarded-replay-summary.json",
            "sha256": fresh_summary_sha256,
        },
        "fresh_guarded_replay_execution": {
            "relative_path": "fresh-guarded-replay-execution.json",
            "sha256": sha256_file(fresh_replay_execution),
            "document": execution,
        },
    }
    require_exact_checkpoint_inputs(inputs)
    return inputs


def _capture_custom_dump(
    *,
    checkpoint_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dump_path = checkpoint_root / "candidate-landing.dump"
    temporary = checkpoint_root / ".candidate-landing.dump.tmp"
    argv = [
        "docker",
        "exec",
        _CANDIDATE_CONTAINER,
        "pg_dump",
        "-U",
        _DATABASE_USER,
        "-d",
        _CANDIDATE_DATABASE,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--serializable-deferrable",
    ]
    try:
        with temporary.open("xb") as stream:
            completed = subprocess.run(
                argv,
                stdout=stream,
                stderr=subprocess.PIPE,
                check=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        dump_command = {
            "command_id": "candidate-pg-dump",
            "sanitized_argv": argv,
            "exit_code": completed.returncode,
            "stderr_sha256": sha256_bytes(completed.stderr),
        }
        if completed.returncode != 0:
            raise CheckpointError(
                "candidate pg_dump failed: "
                + completed.stderr.decode(errors="replace")[-1000:]
            )
        with temporary.open("rb") as stream:
            archive_header = stream.read(5)
        if archive_header != b"PGDMP":
            raise CheckpointError("candidate dump is not a PostgreSQL custom archive")
        temporary.replace(dump_path)
        dump_path.chmod(0o440)
        with dump_path.open("rb") as stream:
            listed = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    _CANDIDATE_CONTAINER,
                    "pg_restore",
                    "--list",
                ],
                stdin=stream,
                capture_output=True,
                check=False,
            )
        list_command = {
            "command_id": "checkpoint-pg-restore-list",
            "sanitized_argv": [
                "docker",
                "exec",
                "-i",
                _CANDIDATE_CONTAINER,
                "pg_restore",
                "--list",
                "<candidate-landing.dump",
            ],
            "exit_code": listed.returncode,
            "stdout_sha256": sha256_bytes(listed.stdout),
            "stderr_sha256": sha256_bytes(listed.stderr),
            "toc_line_count": len(listed.stdout.splitlines()),
        }
        if listed.returncode != 0 or not listed.stdout.strip():
            raise CheckpointError("candidate dump failed pg_restore --list")
        return (
            {
                "absolute_path": str(dump_path),
                "relative_path": dump_path.name,
                "format": "postgresql-custom",
                "byte_size": dump_path.stat().st_size,
                "sha256": sha256_file(dump_path),
                "archive_list_sha256": sha256_bytes(listed.stdout),
                "archive_list_exit_code": listed.returncode,
                "archive_toc_line_count": len(listed.stdout.splitlines()),
            },
            [dump_command, list_command],
        )
    finally:
        temporary.unlink(missing_ok=True)


def _socket_database_url(*, socket_root: Path, database_name: str) -> str:
    from sqlalchemy.engine import URL

    return URL.create(
        drivername="postgresql+psycopg",
        username=_DATABASE_USER,
        database=database_name,
        query={"host": str(socket_root)},
    ).render_as_string(hide_password=False)


def _probe_database_identity(database_url: str) -> dict[str, str | None]:
    try:
        import psycopg
        from psycopg.rows import dict_row

        connect: Any = psycopg.connect
        connection: Any = connect(
            _psycopg_dsn(database_url),
            row_factory=dict_row,
            options="-c default_transaction_read_only=on -c timezone=UTC",
        )
    except Exception as exc:
        raise CheckpointError("restore database identity cannot be connected") from exc
    try:
        identity = connection.execute(
            "SELECT current_database() AS database_name, "
            "shobj_description(oid, 'pg_database') AS database_marker "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        system = connection.execute(
            "SELECT system_identifier::text AS system_identifier "
            "FROM pg_control_system()"
        ).fetchone()
        connection.rollback()
        if identity is None or system is None:
            raise CheckpointError("restore database identity probe is incomplete")
        return {
            "database_name": str(identity["database_name"]),
            "database_marker": identity["database_marker"],
            "system_identifier": str(system["system_identifier"]),
        }
    finally:
        connection.close()


def _set_database_marker(
    *,
    database_url: str,
    database_name: str,
    marker: str,
) -> None:
    try:
        import psycopg
        from psycopg import sql

        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as connection:
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(database_name),
                    sql.Literal(marker),
                )
            )
    except Exception as exc:
        raise CheckpointError("restore database marker write failed") from exc


def advance_final_postgres_readiness(
    *,
    pid1_command: str,
    pg_isready_exit_code: int,
    consecutive_successes: int,
) -> int:
    if pid1_command == "postgres" and pg_isready_exit_code == 0:
        return consecutive_successes + 1
    return 0


def _wait_for_postgres(
    *,
    container_name: str,
    database_name: str,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    started = time.monotonic()
    attempts = 0
    last_exit = -1
    consecutive_successes = 0
    while time.monotonic() - started < timeout_seconds:
        attempts += 1
        pid1 = subprocess.run(
            ["docker", "exec", container_name, "cat", "/proc/1/comm"],
            capture_output=True,
            text=True,
            check=False,
        )
        ready = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                _DATABASE_USER,
                "-d",
                database_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        last_exit = ready.returncode
        pid1_command = pid1.stdout.strip() if pid1.returncode == 0 else ""
        consecutive_successes = advance_final_postgres_readiness(
            pid1_command=pid1_command,
            pg_isready_exit_code=ready.returncode,
            consecutive_successes=consecutive_successes,
        )
        if consecutive_successes >= 3:
            return {
                "command_id": "restore-final-postgres-readiness",
                "sanitized_argv": [
                    "docker",
                    "exec",
                    container_name,
                    "<pid1-postgres-and-pg-isready-x3>",
                ],
                "exit_code": 0,
                "attempt_count": attempts,
                "consecutive_successes": consecutive_successes,
                "pid1_command": pid1_command,
            }
        time.sleep(0.25)
    raise CheckpointError(
        f"restore PostgreSQL did not become ready; last exit={last_exit}"
    )


def _remove_socket_root(socket_root: Path) -> None:
    if not os.path.lexists(socket_root):
        return
    if socket_root.is_symlink() or not socket_root.is_dir():
        raise CheckpointError("restore socket root changed type before cleanup")
    shutil.rmtree(socket_root)


def _remove_owned_restore_target(
    *,
    container_name: str,
    container_id: str,
    socket_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    observed = _lookup_exact_container_id(container_name)
    require_owned_restore_container(
        observed_container_id=observed,
        expected_container_id=container_id,
    )
    _, stop_command = _run_text_command(
        ["docker", "stop", "--time", "30", container_id],
        command_id="stop-owned-restore-container",
    )
    require_owned_restore_container(
        observed_container_id=_lookup_exact_container_id(container_name),
        expected_container_id=container_id,
    )
    _, remove_command = _run_text_command(
        ["docker", "rm", "--volumes", container_id],
        command_id="remove-owned-restore-container",
    )
    observed_after = _lookup_exact_container_id(container_name)
    _remove_socket_root(socket_root)
    receipt = require_restore_cleanup(
        removed_container_id=container_id,
        expected_container_id=container_id,
        observed_container_id_after=observed_after,
        socket_root_absent=not os.path.lexists(socket_root),
    )
    return receipt, [stop_command, remove_command]


def _restore_and_verify(
    *,
    checkpoint_root: Path,
    checkpoint_manifest: Mapping[str, Any],
    restore_container: str,
    restore_database: str,
    socket_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if re.fullmatch(r"canonical-v2-s4e-restore-[a-z0-9-]+", restore_container) is None:
        raise CheckpointError("restore container name is outside the S4E namespace")
    if (
        re.fullmatch(r"miroflow_canonical_v2_s4e_restore_[a-z0-9_]+", restore_database)
        is None
    ):
        raise CheckpointError("restore database name is outside the S4E namespace")
    socket_root = _require_new_child_root(
        socket_root,
        parent=_ALLOWED_SOCKET_PARENT,
        prefix="s4e-restore-",
        label="restore socket root",
    )
    checkpoint_root = checkpoint_root.resolve(strict=True)
    dump_receipt = checkpoint_manifest.get("dump")
    if not isinstance(dump_receipt, Mapping):
        raise CheckpointError("checkpoint manifest dump receipt is missing")
    dump_relative_path = str(dump_receipt.get("relative_path"))
    if dump_relative_path != "candidate-landing.dump":
        raise CheckpointError("checkpoint dump path is not the frozen S4 filename")
    dump_path = checkpoint_root / dump_relative_path
    if sha256_file(dump_path) != checkpoint_manifest["dump"]["sha256"]:
        raise CheckpointError("checkpoint dump changed before restore")
    require_restore_name_absent(_lookup_exact_container_id(restore_container))
    candidate_inspect = _docker_inspect(_CANDIDATE_CONTAINER)
    image_id = candidate_inspect.get("Image")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise CheckpointError("candidate PostgreSQL image identity is unavailable")
    volume_before = _docker_volume_set_sha256()
    socket_root.mkdir(mode=0o770, parents=True)
    socket_root.chmod(0o770)
    socket_mount_root = socket_root / "postgresql"
    socket_mount_root.mkdir(mode=0o777)
    socket_mount_root.chmod(0o777)
    restore_marker = f"miroflow:destructive-target:v1:disposable:{restore_database}"
    commands: list[dict[str, Any]] = []
    restore_snapshot: dict[str, Any] | None = None
    restore_target: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None
    archive_list_exit = dump_receipt.get("archive_list_exit_code")
    if archive_list_exit != 0:
        raise CheckpointError("checkpoint archive list receipt is not successful")
    pg_restore_exit = -1
    owned_container_id: str | None = None
    volume_after: str | None = None
    try:
        run_argv = [
            "docker",
            "run",
            "--detach",
            "--name",
            restore_container,
            "--network",
            "none",
            "--restart",
            "no",
            "--read-only",
            "--tmpfs",
            "/var/lib/postgresql/data:rw,noexec,nosuid,size=1073741824",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=67108864",
            "--volume",
            f"{checkpoint_root}:/checkpoint:ro",
            "--volume",
            f"{socket_mount_root}:/var/run/postgresql:rw",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_USER={_DATABASE_USER}",
            "--env",
            f"POSTGRES_DB={restore_database}",
            "--env",
            "PGDATA=/var/lib/postgresql/data/pgdata",
            image_id,
        ]
        started, start_command = _run_text_command(
            run_argv,
            command_id="start-isolated-restore",
        )
        commands.append(start_command)
        returned_container_id = started.stdout.strip()
        if re.fullmatch(r"[0-9a-f]{64}", returned_container_id) is None:
            raise CheckpointError("restore container did not return one full identity")
        owned_container_id = returned_container_id
        require_owned_restore_container(
            observed_container_id=_lookup_exact_container_id(restore_container),
            expected_container_id=owned_container_id,
        )
        commands.append(
            _wait_for_postgres(
                container_name=restore_container,
                database_name=restore_database,
            )
        )
        inspect = _docker_inspect(restore_container)
        policy = require_restore_container_policy(
            inspect,
            expected_container=restore_container,
            expected_container_id=owned_container_id,
            expected_image_id=image_id,
            checkpoint_root=checkpoint_root,
            socket_parent=socket_root,
            socket_mount_root=socket_mount_root,
        )
        restore_url = _socket_database_url(
            socket_root=socket_mount_root,
            database_name=restore_database,
        )
        identity_before = _probe_database_identity(restore_url)
        if (
            identity_before["database_name"] != restore_database
            or identity_before["database_marker"] is not None
            or identity_before["system_identifier"]
            == checkpoint_manifest["candidate_target_after"]["system_identifier"]
        ):
            raise CheckpointError("restore pre-write database identity is unsafe")
        _set_database_marker(
            database_url=restore_url,
            database_name=restore_database,
            marker=restore_marker,
        )
        require_owned_restore_container(
            observed_container_id=_lookup_exact_container_id(restore_container),
            expected_container_id=owned_container_id,
        )
        restore_argv = [
            "docker",
            "exec",
            restore_container,
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "-U",
            _DATABASE_USER,
            "-d",
            restore_database,
            f"/checkpoint/{dump_relative_path}",
        ]
        restored, restore_command = _run_text_command(
            restore_argv,
            command_id="restore-candidate-dump",
        )
        commands.append(restore_command)
        pg_restore_exit = restored.returncode
        identity_after = _probe_database_identity(restore_url)
        if (
            identity_after["database_name"] != restore_database
            or identity_after["database_marker"] != restore_marker
            or identity_after["system_identifier"]
            != identity_before["system_identifier"]
        ):
            raise CheckpointError("restore post-write database identity changed")
        restore_snapshot, schema_command = read_database_snapshot(
            database_url=restore_url,
            container_name=restore_container,
            database_name=restore_database,
        )
        commands.append(schema_command)
        restore_target = {
            **policy,
            "database": restore_database,
            "database_marker": restore_marker,
            "system_identifier": identity_after["system_identifier"],
        }
    finally:
        cleanup_error: Exception | None = None
        try:
            if owned_container_id is None:
                unexpected = _lookup_exact_container_id(restore_container)
                if unexpected is not None:
                    raise CheckpointError(
                        "restore command left an unowned container; refusing deletion"
                    )
                _remove_socket_root(socket_root)
            else:
                cleanup, cleanup_commands = _remove_owned_restore_target(
                    container_name=restore_container,
                    container_id=owned_container_id,
                    socket_root=socket_root,
                )
                commands.extend(cleanup_commands)
        except Exception as exc:
            cleanup_error = exc
        volume_after = _docker_volume_set_sha256()
        if volume_after != volume_before:
            raise CheckpointError(
                "restore drill changed the Docker volume set during cleanup"
            ) from cleanup_error
        if cleanup_error is not None:
            raise cleanup_error
    if restore_snapshot is None or restore_target is None:
        raise CheckpointError("restore completed without parity evidence")
    if cleanup is None or volume_after is None:
        raise CheckpointError("restore cleanup evidence is incomplete")
    verification = build_restore_verification(
        checkpoint_manifest=checkpoint_manifest,
        restore_target=restore_target,
        restore_snapshot=restore_snapshot,
        dump_sha256_after=sha256_file(dump_path),
        archive_list_exit_code=int(archive_list_exit),
        pg_restore_exit_code=pg_restore_exit,
        docker_volume_set_before=volume_before,
        docker_volume_set_after=volume_after,
        cleanup=cleanup,
    )
    verification["verified_at"] = datetime.now(timezone.utc).isoformat()
    verification["command_evidence"] = commands
    return verification, commands


def summarize_table_rows(rows: Iterable[str]) -> dict[str, Any]:
    normalized = sorted(rows)
    payload = "".join(f"{row}\n" for row in normalized).encode()
    return {
        "row_count": len(normalized),
        "rows_sha256": sha256_bytes(payload),
    }


def _non_landing_row_count(tables: Mapping[str, Mapping[str, Any]]) -> int:
    count = 0
    for table_name, summary in tables.items():
        if table_name.startswith("landing.") or table_name == (
            "public.canonical_v2_alembic_version"
        ):
            continue
        row_count = summary.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int):
            raise CheckpointError(f"table {table_name} has an invalid row count")
        count += row_count
    return count


def build_logical_snapshot(
    *,
    revision: str,
    schema_fingerprint: Mapping[str, Any],
    table_rows: Mapping[str, Iterable[str]],
    landing_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    tables = {
        table_name: summarize_table_rows(rows)
        for table_name, rows in sorted(table_rows.items())
    }
    snapshot: dict[str, Any] = {
        "schema_version": "canonical-v2-postgres-logical-snapshot-v1",
        "revision": revision,
        "schema_fingerprint": dict(schema_fingerprint),
        "table_count": len(tables),
        "tables": tables,
        "landing_metrics": deepcopy(dict(landing_metrics)),
        "non_landing_row_count": _non_landing_row_count(tables),
    }
    snapshot["logical_sha256"] = sha256_bytes(canonical_json_bytes(snapshot))
    return snapshot


def _require_exact_map(
    actual: Any,
    expected: Mapping[str, int],
    *,
    label: str,
) -> None:
    if actual != dict(expected):
        raise CheckpointError(
            f"landing {label} mismatch: expected={dict(expected)!r}, actual={actual!r}"
        )


def require_landing_checkpoint_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schema_version") != ("canonical-v2-postgres-logical-snapshot-v1"):
        raise CheckpointError("logical snapshot schema version is unsupported")
    if snapshot.get("revision") != "C2_0004":
        raise CheckpointError("logical snapshot revision is not C2_0004")
    tables = snapshot.get("tables")
    if not isinstance(tables, Mapping):
        raise CheckpointError("logical snapshot has no table map")
    if set(tables) != _EXPECTED_TABLES or snapshot.get("table_count") != len(
        _EXPECTED_TABLES
    ):
        raise CheckpointError(
            "logical snapshot table inventory mismatch: "
            f"missing={sorted(_EXPECTED_TABLES - set(tables))!r}, "
            f"unexpected={sorted(set(tables) - _EXPECTED_TABLES)!r}"
        )
    for table_name, summary in tables.items():
        if not isinstance(summary, Mapping) or set(summary) != {
            "row_count",
            "rows_sha256",
        }:
            raise CheckpointError(f"table summary is invalid for {table_name}")
        row_count = summary.get("row_count")
        if (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count < 0
            or not isinstance(summary.get("rows_sha256"), str)
            or _SHA256_RE.fullmatch(str(summary.get("rows_sha256"))) is None
        ):
            raise CheckpointError(f"table summary is invalid for {table_name}")
    revision_summary = tables["public.canonical_v2_alembic_version"]
    if revision_summary.get("row_count") != 1:
        raise CheckpointError("revision table summary must contain exactly one row")
    schema_fingerprint = snapshot.get("schema_fingerprint")
    if not isinstance(schema_fingerprint, Mapping) or set(schema_fingerprint) != {
        "normalized_bytes",
        "normalized_sha256",
        "removed_control_lines",
    }:
        raise CheckpointError("logical snapshot schema fingerprint is invalid")
    normalized_bytes = schema_fingerprint.get("normalized_bytes")
    removed_control_lines = schema_fingerprint.get("removed_control_lines")
    if (
        isinstance(normalized_bytes, bool)
        or not isinstance(normalized_bytes, int)
        or normalized_bytes <= 0
        or isinstance(removed_control_lines, bool)
        or not isinstance(removed_control_lines, int)
        or removed_control_lines < 0
        or not isinstance(schema_fingerprint.get("normalized_sha256"), str)
        or _SHA256_RE.fullmatch(str(schema_fingerprint.get("normalized_sha256")))
        is None
    ):
        raise CheckpointError("logical snapshot schema fingerprint is invalid")
    actual_landing_counts = {
        table_name: tables.get(table_name, {}).get("row_count")
        if isinstance(tables.get(table_name), Mapping)
        else None
        for table_name in _LANDING_TABLE_COUNTS
    }
    if actual_landing_counts != _LANDING_TABLE_COUNTS:
        raise CheckpointError(
            "landing table counts mismatch: "
            f"expected={_LANDING_TABLE_COUNTS!r}, actual={actual_landing_counts!r}"
        )
    if snapshot.get("non_landing_row_count") != 0:
        raise CheckpointError("logical snapshot contains non-landing business rows")
    metrics = snapshot.get("landing_metrics")
    if not isinstance(metrics, Mapping):
        raise CheckpointError("logical snapshot has no landing metrics")
    _require_exact_map(
        metrics.get("artifact_kind_counts"),
        _ARTIFACT_KIND_COUNTS,
        label="artifact kind counts",
    )
    _require_exact_map(
        metrics.get("lineage_counts"), _LINEAGE_COUNTS, label="lineage counts"
    )
    _require_exact_map(
        metrics.get("run_status_counts"),
        _RUN_STATUS_COUNTS,
        label="run status counts",
    )
    _require_exact_map(
        metrics.get("record_status_counts"),
        _RECORD_STATUS_COUNTS,
        label="record status counts",
    )
    _require_exact_map(
        metrics.get("error_kind_counts"),
        _ERROR_KIND_COUNTS,
        label="error kind counts",
    )
    integrity = metrics.get("integrity_violation_counts")
    if not isinstance(integrity, Mapping) or set(integrity) != _EXPECTED_INTEGRITY_KEYS:
        raise CheckpointError(
            "landing integrity key inventory mismatch: "
            f"actual={sorted(integrity) if isinstance(integrity, Mapping) else integrity!r}"
        )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value != 0
        for value in integrity.values()
    ):
        raise CheckpointError(
            f"landing integrity violations are nonzero or missing: {integrity!r}"
        )
    without_hash = dict(snapshot)
    actual_hash = without_hash.pop("logical_sha256", None)
    expected_hash = sha256_bytes(canonical_json_bytes(without_hash))
    if actual_hash != expected_hash:
        raise CheckpointError("logical snapshot hash does not match its content")


def require_fresh_replay_execution(execution: Mapping[str, Any]) -> None:
    expected_keys = {
        "command",
        "executed_at",
        "gate",
        "git_commit",
        "matrix_sha256",
        "openspec_tree_sha256",
        "provider_calls",
        "replay_summary_sha256",
        "replay_tool_sha256",
        "run_id",
        "schema_version",
        "source_revalidation_after_destination",
        "source_revalidation_before_destination",
        "target_after",
        "target_before",
        "worktree_state",
        "worktree_status_sha256",
    }
    if set(execution) != expected_keys or execution.get("schema_version") != (
        "canonical-v2-s4d-replay-execution-v1"
    ):
        raise CheckpointError("fresh replay execution schema is invalid")
    if not isinstance(execution.get("run_id"), str) or not execution.get("run_id"):
        raise CheckpointError("fresh replay execution run identity is invalid")
    executed_at = execution.get("executed_at")
    try:
        parsed_time = datetime.fromisoformat(str(executed_at))
    except ValueError as exc:
        raise CheckpointError("fresh replay execution timestamp is invalid") from exc
    if parsed_time.utcoffset() is None:
        raise CheckpointError("fresh replay execution timestamp lacks a timezone")
    require_task4_4_commit(str(execution.get("git_commit")))
    _require_sha256(execution.get("openspec_tree_sha256"), label="fresh OpenSpec tree")
    _require_sha256(execution.get("replay_tool_sha256"), label="fresh replay tool")
    if execution.get("matrix_sha256") != _EXPECTED_INPUTS["landing_matrix_sha256"]:
        raise CheckpointError("fresh replay execution matrix identity changed")
    worktree_status = execution.get("worktree_status_sha256")
    if worktree_status is not None:
        _require_sha256(worktree_status, label="fresh worktree status")
    if not isinstance(execution.get("worktree_state"), str):
        raise CheckpointError("fresh replay execution worktree state is invalid")
    _require_exact_gate(execution.get("gate", {}))
    if (
        execution.get("replay_summary_sha256")
        != _EXPECTED_INPUTS["landing_replay_summary_sha256"]
    ):
        raise CheckpointError("fresh replay execution summary identity changed")
    for field in ("target_before", "target_after"):
        target = execution.get(field)
        if not isinstance(target, Mapping):
            raise CheckpointError("fresh replay execution target evidence is missing")
        try:
            require_exact_candidate_target(target)
        except CheckpointError as exc:
            raise CheckpointError("fresh replay execution target is unsafe") from exc
    if (
        execution.get("source_revalidation_before_destination") != "passed"
        or execution.get("source_revalidation_after_destination") != "passed"
        or execution.get("provider_calls") != 0
    ):
        raise CheckpointError("fresh replay execution boundary evidence is incomplete")
    command = execution.get("command")
    if (
        not isinstance(command, Mapping)
        or set(command) != {"exit_code", "sanitized_argv"}
        or command.get("exit_code") != 0
        or not isinstance(command.get("sanitized_argv"), list)
        or not command.get("sanitized_argv")
        or any(not isinstance(value, str) for value in command["sanitized_argv"])
        or "postgresql://" in " ".join(command["sanitized_argv"])
        or "postgresql+psycopg://" in " ".join(command["sanitized_argv"])
    ):
        raise CheckpointError("fresh replay execution command evidence is unsafe")


def require_exact_checkpoint_inputs(inputs: Mapping[str, Any]) -> None:
    if set(inputs) != {
        *_EXPECTED_INPUTS,
        "fresh_guarded_replay_execution",
        "fresh_guarded_replay_summary",
    }:
        raise CheckpointError("checkpoint input inventory is incomplete or unexpected")
    for key, expected in _EXPECTED_INPUTS.items():
        if inputs.get(key) != expected:
            label = key.removesuffix("_sha256").replace("_", " ")
            raise CheckpointError(
                f"{label} identity changed: expected {expected}, got {inputs.get(key)}"
            )
    fresh_summary = inputs.get("fresh_guarded_replay_summary")
    if fresh_summary != {
        "relative_path": "fresh-guarded-replay-summary.json",
        "sha256": _EXPECTED_INPUTS["landing_replay_summary_sha256"],
    }:
        raise CheckpointError("fresh guarded replay summary identity changed")
    fresh_execution = inputs.get("fresh_guarded_replay_execution")
    if (
        not isinstance(fresh_execution, Mapping)
        or set(fresh_execution) != {"document", "relative_path", "sha256"}
        or fresh_execution.get("relative_path") != "fresh-guarded-replay-execution.json"
    ):
        raise CheckpointError("fresh guarded replay execution identity is invalid")
    execution_document = fresh_execution.get("document")
    if not isinstance(execution_document, Mapping):
        raise CheckpointError("fresh guarded replay execution document is missing")
    require_fresh_replay_execution(execution_document)
    execution_sha256 = _require_sha256(
        fresh_execution.get("sha256"),
        label="fresh guarded replay execution",
    )
    if execution_sha256 != document_sha256(execution_document):
        raise CheckpointError(
            "fresh guarded replay execution hash does not match content"
        )


def _require_exact_gate(gate: Mapping[str, Any]) -> None:
    if dict(gate) != _EXPECTED_GATE:
        raise CheckpointError("Accepted S2B gate identity changed")


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CheckpointError(f"{label} must be one lowercase SHA-256")
    return value


def require_task4_4_commit(git_commit: str) -> None:
    if git_commit != _TASK4_4_COMMIT:
        raise CheckpointError(
            f"Task 4.4 commit changed: expected {_TASK4_4_COMMIT}, got {git_commit}"
        )


def require_exact_candidate_target(target: Mapping[str, Any]) -> None:
    if dict(target) != _EXPECTED_CANDIDATE_TARGET:
        raise CheckpointError(
            "candidate target does not match the frozen Task 4.4 target"
        )


def require_implementation_artifacts(artifacts: Mapping[str, Any]) -> None:
    if set(artifacts) != _EXPECTED_IMPLEMENTATION_PATHS:
        raise CheckpointError(
            "implementation artifact inventory is incomplete or unexpected"
        )
    for relative_path, digest in artifacts.items():
        if (
            Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
        ):
            raise CheckpointError(
                f"implementation artifact identity is invalid: {relative_path}"
            )


def build_checkpoint_manifest(
    *,
    checkpoint_id: str,
    created_at: str,
    git_commit: str,
    worktree_state: str,
    git_status_sha256: str,
    git_diff_sha256: str,
    implementation_artifacts: Mapping[str, Any],
    openspec_tree_sha256: str,
    threshold_registry_sha256: str,
    corpus_manifest_sha256: str,
    gate: Mapping[str, Any],
    inputs: Mapping[str, Any],
    source_revalidation: Mapping[str, Any],
    candidate_target_before: Mapping[str, Any],
    candidate_target_after: Mapping[str, Any],
    snapshot_before: Mapping[str, Any],
    snapshot_after: Mapping[str, Any],
    dump: Mapping[str, Any],
    tool_versions: Mapping[str, Any],
    command_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    if not checkpoint_id or not created_at:
        raise CheckpointError("checkpoint identity and creation time are required")
    try:
        checkpoint_time = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise CheckpointError("checkpoint creation time is invalid") from exc
    if checkpoint_time.utcoffset() is None:
        raise CheckpointError("checkpoint creation time requires a timezone")
    require_task4_4_commit(git_commit)
    require_implementation_artifacts(implementation_artifacts)
    if worktree_state not in {"clean", "task4.5-dirty"}:
        raise CheckpointError("checkpoint worktree state is invalid")
    _require_sha256(git_status_sha256, label="git status")
    _require_sha256(git_diff_sha256, label="git diff")
    for label, value in (
        ("OpenSpec tree", openspec_tree_sha256),
        ("threshold registry", threshold_registry_sha256),
        ("corpus manifest", corpus_manifest_sha256),
    ):
        _require_sha256(value, label=label)
    if threshold_registry_sha256 != _THRESHOLD_REGISTRY_SHA256:
        raise CheckpointError("accepted threshold registry identity changed")
    if corpus_manifest_sha256 != _CORPUS_MANIFEST_SHA256:
        raise CheckpointError("accepted corpus manifest identity changed")
    _require_exact_gate(gate)
    require_exact_checkpoint_inputs(inputs)
    if dict(source_revalidation) != {
        "after_dump": "passed",
        "before_dump": "passed",
        "source_count": 6,
    }:
        raise CheckpointError("checkpoint source revalidation is incomplete")
    fresh_execution = inputs["fresh_guarded_replay_execution"]
    assert isinstance(fresh_execution, Mapping)
    execution_document = fresh_execution["document"]
    assert isinstance(execution_document, Mapping)
    execution_time = datetime.fromisoformat(str(execution_document["executed_at"]))
    execution_age = (checkpoint_time - execution_time).total_seconds()
    s4d_path = (
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/"
        "replay_landing_matrix.py"
    )
    if (
        execution_document.get("run_id") != checkpoint_id
        or execution_document.get("openspec_tree_sha256") != openspec_tree_sha256
        or execution_document.get("worktree_status_sha256") != git_status_sha256
        or execution_document.get("replay_tool_sha256")
        != implementation_artifacts[s4d_path]
        or execution_age < 0
        or execution_age > 1800
    ):
        raise CheckpointError(
            "fresh replay execution is not bound to this checkpoint implementation"
        )
    require_exact_candidate_target(candidate_target_before)
    require_exact_candidate_target(candidate_target_after)
    require_landing_checkpoint_snapshot(snapshot_before)
    if dict(snapshot_before) != dict(snapshot_after) or dict(
        candidate_target_before
    ) != dict(candidate_target_after):
        raise CheckpointError("candidate changed during dump capture")
    require_landing_checkpoint_snapshot(snapshot_after)
    if dump.get("format") != "postgresql-custom":
        raise CheckpointError("checkpoint dump format must be postgresql-custom")
    relative_path = dump.get("relative_path")
    byte_size = dump.get("byte_size")
    if (
        not isinstance(relative_path, str)
        or relative_path != "candidate-landing.dump"
        or Path(relative_path).is_absolute()
        or ".." in Path(relative_path).parts
    ):
        raise CheckpointError("checkpoint dump path must be safe and relative")
    if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size <= 0:
        raise CheckpointError("checkpoint dump byte size must be positive")
    _require_sha256(dump.get("sha256"), label="checkpoint dump")
    _require_sha256(dump.get("archive_list_sha256"), label="archive list")
    archive_exit = dump.get("archive_list_exit_code")
    archive_lines = dump.get("archive_toc_line_count")
    if (
        archive_exit != 0
        or isinstance(archive_lines, bool)
        or not isinstance(archive_lines, int)
        or archive_lines <= 0
    ):
        raise CheckpointError("checkpoint dump archive listing is invalid")
    if set(tool_versions) != {"docker", "pg_dump", "pg_restore", "python"} or any(
        not isinstance(value, str) or not value.strip()
        for value in tool_versions.values()
    ):
        raise CheckpointError("checkpoint tool version inventory is incomplete")
    if not command_evidence:
        raise CheckpointError("checkpoint command evidence is empty")
    for command in command_evidence:
        argv = command.get("sanitized_argv") if isinstance(command, Mapping) else None
        if (
            not isinstance(command, Mapping)
            or not isinstance(command.get("command_id"), str)
            or not command.get("command_id")
            or command.get("exit_code") != 0
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(value, str) for value in argv)
            or "postgresql://" in " ".join(argv)
            or "postgresql+psycopg://" in " ".join(argv)
        ):
            raise CheckpointError("checkpoint command evidence is invalid or unsafe")
    return {
        "schema_version": "canonical-v2-s4-landing-checkpoint-v1",
        "state": "candidate",
        "checkpoint_id": checkpoint_id,
        "created_at": created_at,
        "implementation": {
            "git_commit": git_commit,
            "worktree_state": worktree_state,
            "git_status_sha256": git_status_sha256,
            "git_diff_sha256": git_diff_sha256,
            "implementation_artifacts": deepcopy(dict(implementation_artifacts)),
            "openspec_tree_sha256": openspec_tree_sha256,
            "threshold_registry_sha256": threshold_registry_sha256,
            "corpus_manifest_sha256": corpus_manifest_sha256,
        },
        "gate": deepcopy(dict(gate)),
        "inputs": deepcopy(dict(inputs)),
        "source_revalidation": deepcopy(dict(source_revalidation)),
        "candidate_target_before": deepcopy(dict(candidate_target_before)),
        "candidate_target_after": deepcopy(dict(candidate_target_after)),
        "snapshot": deepcopy(dict(snapshot_after)),
        "dump": deepcopy(dict(dump)),
        "tool_versions": deepcopy(dict(tool_versions)),
        "command_evidence": deepcopy(command_evidence),
        "provider_usage": "not_used",
        "model_prompt_embedding_reranker_versions": "not_applicable",
        "provider_calls": 0,
        "publication_or_index_effect": "none",
    }


def require_restore_container_policy(
    container_inspect: Mapping[str, Any],
    *,
    expected_container: str,
    expected_container_id: str,
    expected_image_id: str,
    checkpoint_root: Path,
    socket_parent: Path,
    socket_mount_root: Path,
) -> dict[str, Any]:
    container_id = container_inspect.get("Id")
    image_id = container_inspect.get("Image")
    name = container_inspect.get("Name")
    state = container_inspect.get("State")
    host = container_inspect.get("HostConfig")
    mounts = container_inspect.get("Mounts")
    network_settings = container_inspect.get("NetworkSettings")
    if (
        container_id != expected_container_id
        or image_id != expected_image_id
        or name != f"/{expected_container}"
        or not isinstance(state, Mapping)
        or state.get("Running") is not True
        or not isinstance(host, Mapping)
        or not isinstance(mounts, list)
        or not isinstance(network_settings, Mapping)
    ):
        raise CheckpointError("restore container identity/running state is invalid")
    if host.get("NetworkMode") != "none":
        raise CheckpointError("restore container network must be none")
    networks = network_settings.get("Networks")
    none_network = networks.get("none") if isinstance(networks, Mapping) else None
    if (
        not isinstance(networks, Mapping)
        or set(networks) != {"none"}
        or not isinstance(none_network, Mapping)
        or none_network.get("IPAddress") not in {None, ""}
        or none_network.get("Gateway") not in {None, ""}
    ):
        raise CheckpointError("restore container has an attached network")
    ports = host.get("PortBindings") or {}
    if not isinstance(ports, Mapping) or ports:
        raise CheckpointError("restore container must have no published ports")
    restart = host.get("RestartPolicy")
    if not isinstance(restart, Mapping) or restart.get("Name") != "no":
        raise CheckpointError("restore container restart policy must be no")
    if host.get("ReadonlyRootfs") is not True:
        raise CheckpointError("restore container root filesystem must be read-only")
    tmpfs = host.get("Tmpfs")
    pgdata_tmpfs = (
        tmpfs.get("/var/lib/postgresql/data") if isinstance(tmpfs, Mapping) else None
    )
    if not isinstance(pgdata_tmpfs, str) or set(pgdata_tmpfs.split(",")) != {
        "rw",
        "noexec",
        "nosuid",
        "size=1073741824",
    }:
        raise CheckpointError("restore container PGDATA must use explicit tmpfs")
    if any(
        isinstance(mount, Mapping)
        and (
            mount.get("Destination") == "/var/lib/postgresql/data"
            or mount.get("Type") == "volume"
        )
        for mount in mounts
    ):
        raise CheckpointError("restore container has persistent or anonymous storage")
    by_destination = {
        mount.get("Destination"): mount
        for mount in mounts
        if isinstance(mount, Mapping)
    }
    if set(by_destination) != {"/checkpoint", "/var/run/postgresql"}:
        raise CheckpointError("restore container has an undeclared bind mount")
    checkpoint_mount = by_destination["/checkpoint"]
    socket_mount = by_destination["/var/run/postgresql"]
    if (
        checkpoint_mount.get("Type") != "bind"
        or checkpoint_mount.get("RW") is not False
        or Path(str(checkpoint_mount.get("Source"))).resolve(strict=False)
        != checkpoint_root.resolve(strict=False)
    ):
        raise CheckpointError(
            "restore checkpoint mount is not the exact read-only root"
        )
    if (
        socket_mount.get("Type") != "bind"
        or socket_mount.get("RW") is not True
        or Path(str(socket_mount.get("Source"))).resolve(strict=False)
        != socket_mount_root.resolve(strict=False)
    ):
        raise CheckpointError("restore socket mount is not the exact writable root")
    try:
        parent_mode = f"{socket_parent.stat().st_mode & 0o7777:04o}"
        mount_stat = socket_mount_root.stat()
        mount_mode = f"{mount_stat.st_mode & 0o7777:04o}"
        mount_gid = mount_stat.st_gid
    except OSError as exc:
        raise CheckpointError("restore socket root cannot be inspected") from exc
    if (
        parent_mode != "0770"
        or mount_gid != os.getgid()
        or (mount_stat.st_mode & 0o070) != 0o070
    ):
        raise CheckpointError(
            "restore socket outer/inner permissions are not the bounded host pattern"
        )
    return {
        "container_name": expected_container,
        "container_id": expected_container_id,
        "container_read_only": True,
        "image_id": expected_image_id,
        "network_mode": "none",
        "pgdata_storage": "tmpfs",
        "published_ports": [],
        "restart_policy": "no",
        "checkpoint_mount_read_only": True,
        "persistent_volume_count": 0,
        "socket_parent_mode": parent_mode,
        "socket_mount_mode": mount_mode,
        "socket_mount_gid": mount_gid,
    }


def require_restore_target_receipt(
    target: Mapping[str, Any],
    *,
    source_system_identifier: Any,
) -> None:
    expected_keys = {
        "checkpoint_mount_read_only",
        "container_id",
        "container_name",
        "container_read_only",
        "database",
        "database_marker",
        "image_id",
        "network_mode",
        "persistent_volume_count",
        "pgdata_storage",
        "published_ports",
        "restart_policy",
        "socket_mount_gid",
        "socket_mount_mode",
        "socket_parent_mode",
        "system_identifier",
    }
    if set(target) != expected_keys:
        raise CheckpointError("restore target policy receipt has an invalid field set")
    container_name = target.get("container_name")
    container_id = target.get("container_id")
    database = target.get("database")
    system_identifier = target.get("system_identifier")
    if system_identifier == source_system_identifier:
        raise CheckpointError("restore target is not an independent system")
    if (
        not isinstance(container_name, str)
        or re.fullmatch(r"canonical-v2-s4e-restore-[a-z0-9-]+", container_name) is None
        or not isinstance(container_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", container_id) is None
        or not isinstance(database, str)
        or re.fullmatch(r"miroflow_canonical_v2_s4e_restore_[a-z0-9_]+", database)
        is None
        or target.get("database_marker")
        != f"miroflow:destructive-target:v1:disposable:{database}"
        or not isinstance(system_identifier, str)
        or re.fullmatch(r"[0-9]+", system_identifier) is None
        or not isinstance(target.get("image_id"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(target.get("image_id"))) is None
    ):
        raise CheckpointError("restore target policy identity is invalid")
    expected_policy = {
        "checkpoint_mount_read_only": True,
        "container_read_only": True,
        "network_mode": "none",
        "persistent_volume_count": 0,
        "pgdata_storage": "tmpfs",
        "published_ports": [],
        "restart_policy": "no",
        "socket_parent_mode": "0770",
    }
    drift = {
        key: target.get(key)
        for key, expected in expected_policy.items()
        if target.get(key) != expected
    }
    if drift:
        raise CheckpointError(f"restore target policy drift: {drift!r}")
    mount_mode = target.get("socket_mount_mode")
    mount_gid = target.get("socket_mount_gid")
    if (
        not isinstance(mount_mode, str)
        or re.fullmatch(r"[0-7]{4}", mount_mode) is None
        or (int(mount_mode, 8) & 0o070) != 0o070
        or mount_gid != os.getgid()
    ):
        raise CheckpointError("restore target socket policy is unsafe")


def build_restore_verification(
    *,
    checkpoint_manifest: Mapping[str, Any],
    restore_target: Mapping[str, Any],
    restore_snapshot: Mapping[str, Any],
    dump_sha256_after: str,
    archive_list_exit_code: int,
    pg_restore_exit_code: int,
    docker_volume_set_before: str,
    docker_volume_set_after: str,
    cleanup: Mapping[str, Any],
) -> dict[str, Any]:
    source_target = checkpoint_manifest.get("candidate_target_after")
    source_snapshot = checkpoint_manifest.get("snapshot")
    dump = checkpoint_manifest.get("dump")
    if (
        not isinstance(source_target, Mapping)
        or not isinstance(source_snapshot, Mapping)
        or not isinstance(dump, Mapping)
    ):
        raise CheckpointError("checkpoint manifest is incomplete")
    require_landing_checkpoint_snapshot(source_snapshot)
    require_restore_target_receipt(
        restore_target,
        source_system_identifier=source_target.get("system_identifier"),
    )
    restore_system = restore_target.get("system_identifier")
    if not isinstance(restore_system, str) or restore_system == source_target.get(
        "system_identifier"
    ):
        raise CheckpointError("restore target is not an independent system")
    if dict(restore_snapshot) != dict(source_snapshot):
        raise CheckpointError("restore logical parity does not match the checkpoint")
    require_landing_checkpoint_snapshot(restore_snapshot)
    if dump_sha256_after != dump.get("sha256"):
        raise CheckpointError("checkpoint dump hash changed during restore")
    if archive_list_exit_code != 0 or pg_restore_exit_code != 0:
        raise CheckpointError("archive readability or pg_restore command failed")
    if docker_volume_set_before != docker_volume_set_after:
        raise CheckpointError("restore drill changed the Docker volume set")
    if cleanup != {
        "container_absent": True,
        "owned_container_id": restore_target.get("container_id"),
        "socket_root_absent": True,
    }:
        raise CheckpointError("restore target cleanup is incomplete")
    return {
        "schema_version": "canonical-v2-s4-landing-restore-verification-v1",
        "state": "passed",
        "checkpoint_id": checkpoint_manifest.get("checkpoint_id"),
        "checkpoint_manifest_sha256": document_sha256(checkpoint_manifest),
        "dump_sha256": dump_sha256_after,
        "restore_target": deepcopy(dict(restore_target)),
        "restore_snapshot": deepcopy(dict(restore_snapshot)),
        "logical_parity": True,
        "archive_list_exit_code": archive_list_exit_code,
        "pg_restore_exit_code": pg_restore_exit_code,
        "docker_volume_set_before": docker_volume_set_before,
        "docker_volume_set_after": docker_volume_set_after,
        "cleanup": deepcopy(dict(cleanup)),
        "provider_calls": 0,
    }


def _sanitized_argv(argv: list[str]) -> list[str]:
    result: list[str] = []
    redact_next = False
    for value in argv:
        if redact_next:
            result.append("<explicit-dsn>")
            redact_next = False
        elif value.startswith("--database-url="):
            result.append("--database-url=<explicit-dsn>")
        else:
            result.append(value)
            redact_next = value == "--database-url"
    return result


def _checkpoint_tool_versions() -> tuple[dict[str, str], list[dict[str, Any]]]:
    commands: list[dict[str, Any]] = []
    docker, command = _run_text_command(
        ["docker", "--version"],
        command_id="docker-version",
    )
    commands.append(command)
    pg_dump, command = _run_text_command(
        ["docker", "exec", _CANDIDATE_CONTAINER, "pg_dump", "--version"],
        command_id="pg-dump-version",
    )
    commands.append(command)
    pg_restore, command = _run_text_command(
        ["docker", "exec", _CANDIDATE_CONTAINER, "pg_restore", "--version"],
        command_id="pg-restore-version",
    )
    commands.append(command)
    versions = {
        "docker": docker.stdout.strip(),
        "pg_dump": pg_dump.stdout.strip(),
        "pg_restore": pg_restore.stdout.strip(),
        "python": sys.version.split()[0],
    }
    if any(not value for value in versions.values()):
        raise CheckpointError("checkpoint tool version probe is incomplete")
    return versions, commands


def _copy_file_exclusive_verified(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
) -> None:
    if sha256_file(source) != expected_sha256:
        raise CheckpointError(f"checkpoint copy source identity changed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            created = True
            digest = hashlib.sha256()
            while chunk := input_stream.read(1024 * 1024):
                digest.update(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except (FileExistsError, OSError) as exc:
        if created:
            destination.unlink(missing_ok=True)
        raise CheckpointError(
            f"checkpoint evidence destination is not new and writable: {destination}"
        ) from exc
    if digest.hexdigest() != expected_sha256 or sha256_file(source) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise CheckpointError(f"checkpoint evidence copy changed in transit: {source}")
    destination.chmod(0o440)


def _freeze_checkpoint_root(checkpoint_root: Path) -> dict[str, Any]:
    resolved = checkpoint_root.resolve(strict=True)
    for path in sorted(resolved.rglob("*"), reverse=True):
        if path.is_symlink():
            raise CheckpointError("checkpoint root contains a symbolic link")
        if path.is_file():
            path.chmod(0o440)
        elif path.is_dir():
            path.chmod(0o550)
    resolved.chmod(0o550)
    writable = [
        path.relative_to(resolved).as_posix()
        for path in [resolved, *resolved.rglob("*")]
        if path.stat().st_mode & 0o222
    ]
    if writable:
        raise CheckpointError(f"checkpoint root is not frozen: {writable!r}")
    return {
        "checkpoint_root": str(resolved),
        "directory_mode": "0550",
        "file_mode": "0440",
        "tree_sha256": _file_tree_sha256(resolved),
        "writable_paths": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--fresh-replay-summary", type=Path, required=True)
    parser.add_argument("--fresh-replay-execution", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--restore-container", required=True)
    parser.add_argument("--restore-database", required=True)
    parser.add_argument("--restore-socket-root", type=Path, required=True)
    args = parser.parse_args()

    evidence_root = args.evidence_root.resolve(strict=True)
    if evidence_root != _RUN_ROOT.resolve(strict=True):
        raise CheckpointError(
            "checkpoint evidence root is not the exact OpenSpec run root"
        )
    for label, path in (
        ("fresh replay summary", args.fresh_replay_summary),
        ("fresh replay execution", args.fresh_replay_execution),
        ("checkpoint root", args.checkpoint_root),
        ("restore socket root", args.restore_socket_root),
    ):
        if not path.is_absolute():
            raise CheckpointError(f"{label} must be an explicit absolute path")
    checkpoint_root = _require_new_child_root(
        args.checkpoint_root,
        parent=_ALLOWED_CHECKPOINT_PARENT,
        prefix="canonical-v2-s4-landing-",
        label="checkpoint root",
    )
    if checkpoint_root.name != args.checkpoint_id:
        raise CheckpointError("checkpoint ID must equal its external root name")
    repo_evidence = {
        "manifest": _RUN_ROOT / "s4e/checkpoint-manifest.json",
        "restore": _RUN_ROOT / "s4e/restore-verification.json",
        "fresh_summary": _RUN_ROOT / "s4e/fresh-guarded-replay-summary.json",
        "fresh_execution": _RUN_ROOT / "s4e/fresh-guarded-replay-execution.json",
        "freeze": _RUN_ROOT / "s4e/checkpoint-freeze-receipt.json",
    }
    existing_evidence = [
        str(path) for path in repo_evidence.values() if os.path.lexists(path)
    ]
    if existing_evidence:
        raise CheckpointError(
            f"Task 4.5 evidence paths already exist: {existing_evidence!r}"
        )

    created_at = datetime.now(timezone.utc).isoformat()
    gate = _accepted_gate(evidence_root)
    inputs = _checkpoint_inputs(
        evidence_root=evidence_root,
        fresh_replay_summary=args.fresh_replay_summary,
        fresh_replay_execution=args.fresh_replay_execution,
    )
    replay_module, candidate_before = _candidate_target(database_url=args.database_url)
    require_exact_candidate_target(candidate_before)
    source_validation_root = _require_new_child_root(
        _ALLOWED_SOCKET_PARENT / f"s4e-source-validation-{args.checkpoint_id}",
        parent=_ALLOWED_SOCKET_PARENT,
        prefix="s4e-source-validation-",
        label="checkpoint source-validation work root",
    )
    matrix_spec = replay_module.load_matrix(_RUN_ROOT / "s4d/landing-matrix.json")
    prepared_sources = replay_module.prepare_matrix(
        matrix_spec,
        evidence_root=evidence_root,
        work_root=source_validation_root,
    )
    replay_module.revalidate_prepared_sources(prepared_sources.entries)
    source_revalidation = {
        "before_dump": "passed",
        "source_count": len(prepared_sources.entries),
    }
    snapshot_before, schema_before_command = read_database_snapshot(
        database_url=args.database_url,
        container_name=_CANDIDATE_CONTAINER,
        database_name=_CANDIDATE_DATABASE,
    )
    git = _git_evidence()
    tool_versions, tool_commands = _checkpoint_tool_versions()
    implementation_artifacts = _implementation_artifacts()

    checkpoint_root.mkdir(mode=0o750)
    _copy_file_exclusive_verified(
        args.fresh_replay_summary,
        checkpoint_root / "fresh-guarded-replay-summary.json",
        expected_sha256=inputs["fresh_guarded_replay_summary"]["sha256"],
    )
    _copy_file_exclusive_verified(
        args.fresh_replay_execution,
        checkpoint_root / "fresh-guarded-replay-execution.json",
        expected_sha256=inputs["fresh_guarded_replay_execution"]["sha256"],
    )
    dump, dump_commands = _capture_custom_dump(checkpoint_root=checkpoint_root)
    replay_module.revalidate_prepared_sources(prepared_sources.entries)
    source_revalidation["after_dump"] = "passed"
    _accepted_gate(evidence_root)
    _, candidate_after = _candidate_target(database_url=args.database_url)
    require_exact_candidate_target(candidate_after)
    snapshot_after, schema_after_command = read_database_snapshot(
        database_url=args.database_url,
        container_name=_CANDIDATE_CONTAINER,
        database_name=_CANDIDATE_DATABASE,
    )
    command_evidence = [
        *git["commands"],
        *tool_commands,
        schema_before_command,
        *dump_commands,
        schema_after_command,
        {
            "command_id": "s4e-checkpoint-orchestration",
            "sanitized_argv": _sanitized_argv(sys.argv),
            "exit_code": 0,
        },
    ]
    manifest = build_checkpoint_manifest(
        checkpoint_id=args.checkpoint_id,
        created_at=created_at,
        git_commit=git["commit"],
        worktree_state=git["state"],
        git_status_sha256=git["status_sha256"],
        git_diff_sha256=git["diff_sha256"],
        implementation_artifacts=implementation_artifacts,
        openspec_tree_sha256=_file_tree_sha256(
            _REPO_ROOT / "openspec/changes/rebuild-canonical-v2-knowledge-platform"
        ),
        threshold_registry_sha256=sha256_file(
            _RUN_ROOT / "s2/acceptance-thresholds.json"
        ),
        corpus_manifest_sha256=sha256_file(_RUN_ROOT / "s2/corpus-manifest.json"),
        gate=gate,
        inputs=inputs,
        source_revalidation=source_revalidation,
        candidate_target_before=candidate_before,
        candidate_target_after=candidate_after,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        dump=dump,
        tool_versions=tool_versions,
        command_evidence=command_evidence,
    )
    verification, _ = _restore_and_verify(
        checkpoint_root=checkpoint_root,
        checkpoint_manifest=manifest,
        restore_container=args.restore_container,
        restore_database=args.restore_database,
        socket_root=args.restore_socket_root,
    )
    _accepted_gate(evidence_root)
    _, candidate_after_restore = _candidate_target(database_url=args.database_url)
    require_exact_candidate_target(candidate_after_restore)
    snapshot_after_restore, final_schema_command = read_database_snapshot(
        database_url=args.database_url,
        container_name=_CANDIDATE_CONTAINER,
        database_name=_CANDIDATE_DATABASE,
    )
    if snapshot_after_restore != snapshot_before:
        raise CheckpointError("candidate changed during independent restore drill")
    replay_module.revalidate_prepared_sources(prepared_sources.entries)
    _remove_socket_root(source_validation_root)
    verification["candidate_target_after_restore"] = candidate_after_restore
    verification["candidate_snapshot_after_restore"] = snapshot_after_restore
    verification["final_candidate_schema_command"] = final_schema_command
    verification["source_revalidation_after_restore"] = "passed"

    external_manifest = checkpoint_root / "checkpoint-manifest.json"
    external_restore = checkpoint_root / "restore-verification.json"
    _write_document_exclusive(external_manifest, manifest)
    _write_document_exclusive(external_restore, verification)
    freeze = _freeze_checkpoint_root(checkpoint_root)

    _copy_file_exclusive_verified(
        external_manifest,
        repo_evidence["manifest"],
        expected_sha256=document_sha256(manifest),
    )
    _copy_file_exclusive_verified(
        external_restore,
        repo_evidence["restore"],
        expected_sha256=document_sha256(verification),
    )
    _copy_file_exclusive_verified(
        checkpoint_root / "fresh-guarded-replay-summary.json",
        repo_evidence["fresh_summary"],
        expected_sha256=inputs["fresh_guarded_replay_summary"]["sha256"],
    )
    _copy_file_exclusive_verified(
        checkpoint_root / "fresh-guarded-replay-execution.json",
        repo_evidence["fresh_execution"],
        expected_sha256=inputs["fresh_guarded_replay_execution"]["sha256"],
    )
    freeze["checkpoint_manifest_sha256"] = document_sha256(manifest)
    freeze["restore_verification_sha256"] = document_sha256(verification)
    freeze["frozen_at"] = datetime.now(timezone.utc).isoformat()
    _write_document_exclusive(repo_evidence["freeze"], freeze)

    print(
        json.dumps(
            {
                "checkpoint_id": args.checkpoint_id,
                "checkpoint_manifest_sha256": document_sha256(manifest),
                "checkpoint_root": str(checkpoint_root),
                "checkpoint_tree_sha256": freeze["tree_sha256"],
                "restore_verification_sha256": document_sha256(verification),
                "state": "restore-verified-candidate",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
