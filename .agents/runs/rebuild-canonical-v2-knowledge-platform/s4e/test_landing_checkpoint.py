from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest


MODULE_PATH = Path(__file__).with_name("landing_checkpoint.py")


def _module() -> Any:
    name = "canonical_v2_s4e_landing_checkpoint"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _landing_metrics() -> dict[str, Any]:
    return {
        "artifact_kind_counts": {
            "historical_jsonl": 1,
            "historical_sqlite": 1,
            "historical_xlsx": 1,
            "milvus_verified_copy_records": 1,
            "recorded_collected_response": 1,
            "verified_backup_copy": 6,
            "verified_restore_copy": 3,
            "wal_fpi_salvage_records": 1,
        },
        "error_kind_counts": {
            "missing_external_content": 3,
            "schema_mismatch": 3,
        },
        "integrity_violation_counts": {
            "artifact_cycle": 0,
            "artifact_invalid_identity": 0,
            "artifact_orphan_parent": 0,
            "artifact_self_parent": 0,
            "error_orphan_record": 0,
            "ingest_orphan_artifact_or_parser": 0,
            "parser_incomplete_identity": 0,
            "parser_orphan_artifact": 0,
            "partial_record_without_error": 0,
            "record_incomplete_identity": 0,
            "record_orphan_artifact_or_parser": 0,
        },
        "lineage_counts": {
            "matching_parent_edges": 9,
            "orphan_parent_edges": 0,
            "parent_edges": 9,
            "roots": 6,
        },
        "record_status_counts": {"parsed": 17, "partial": 4},
        "run_status_counts": {"accepted": 4, "partial": 2},
    }


def _snapshot(module: Any) -> dict[str, Any]:
    expected_tables = {
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
    table_rows: dict[str, list[str]] = {name: [] for name in expected_tables}
    table_rows.update(
        {
            "landing.evidence_artifact": [
                f'{{"id":"a-{index}"}}' for index in range(15)
            ],
            "landing.ingest_run": [f'{{"id":"i-{index}"}}' for index in range(6)],
            "landing.parser_run": [f'{{"id":"p-{index}"}}' for index in range(6)],
            "landing.source_error": [f'{{"id":"e-{index}"}}' for index in range(6)],
            "landing.source_record": [f'{{"id":"r-{index}"}}' for index in range(21)],
            "public.canonical_v2_alembic_version": ['{"version_num":"C2_0004"}'],
        }
    )
    return module.build_logical_snapshot(
        revision="C2_0004",
        schema_fingerprint={
            "normalized_bytes": 64000,
            "normalized_sha256": "1" * 64,
            "removed_control_lines": 2,
        },
        table_rows=table_rows,
        landing_metrics=_landing_metrics(),
    )


def _gate() -> dict[str, Any]:
    return {
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


def _fresh_execution() -> dict[str, Any]:
    return {
        "schema_version": "canonical-v2-s4d-replay-execution-v1",
        "run_id": "canonical-v2-s4-landing-20260711T220000Z-cef42a1",
        "executed_at": "2026-07-11T22:00:00+00:00",
        "git_commit": "cef42a1e075d30c5a0e179f34ab543b4878edabd",
        "worktree_state": "task-worktree-dirty",
        "worktree_status_sha256": "b" * 64,
        "openspec_tree_sha256": "2" * 64,
        "replay_tool_sha256": "6" * 64,
        "matrix_sha256": (
            "eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923"
        ),
        "gate": _gate(),
        "replay_summary_sha256": (
            "a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5"
        ),
        "target_before": _target(),
        "target_after": _target(),
        "source_revalidation_before_destination": "passed",
        "source_revalidation_after_destination": "passed",
        "command": {
            "sanitized_argv": ["tool", "--database-url", "<explicit-dsn>"],
            "exit_code": 0,
        },
        "provider_calls": 0,
    }


def _inputs() -> dict[str, Any]:
    execution = _fresh_execution()
    execution_bytes = (
        json.dumps(
            execution,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    return {
        "landing_matrix_sha256": (
            "eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923"
        ),
        "landing_replay_summary_sha256": (
            "a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5"
        ),
        "matrix_entries_sha256": (
            "5b77b4a4f3ea9f0a0fd4667dfccff6afefa968b5fb43124de816e652d1c58293"
        ),
        "fresh_guarded_replay_summary": {
            "relative_path": "fresh-guarded-replay-summary.json",
            "sha256": (
                "a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5"
            ),
        },
        "fresh_guarded_replay_execution": {
            "relative_path": "fresh-guarded-replay-execution.json",
            "sha256": hashlib.sha256(execution_bytes).hexdigest(),
            "document": execution,
        },
    }


def _target() -> dict[str, Any]:
    return {
        "container_name": "canonical-v2-s3b-pg-20260711",
        "container_running": True,
        "database": "miroflow_canonical_v2_candidate_s3b",
        "database_marker": (
            "miroflow:destructive-target:v1:isolated-candidate:"
            "miroflow_canonical_v2_candidate_s3b"
        ),
        "kind": "isolated-candidate",
        "error_kind_counts": {
            "missing_external_content": 3,
            "schema_mismatch": 3,
        },
        "landing_counts": {
            "evidence_artifact": 15,
            "ingest_run": 6,
            "parser_run": 6,
            "source_error": 6,
            "source_record": 21,
        },
        "lineage_counts": {
            "matching_parent_edges": 9,
            "orphan_parent_edges": 0,
            "parent_edges": 9,
            "roots": 6,
        },
        "network_mode": "none",
        "non_landing_row_count": 0,
        "pgdata_volume": "canonical-v2-s3b-pgdata-20260711",
        "published_ports": [],
        "restart_policy": "no",
        "revision": "C2_0004",
        "record_status_counts": {"parsed": 17, "partial": 4},
        "run_status_counts": {"accepted": 4, "partial": 2},
        "system_identifier": "7661313446684311592",
        "validated_prestate": "bounded-replay",
    }


def _implementation_artifacts() -> dict[str, str]:
    return {
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4d/"
        "replay_landing_matrix.py": "6" * 64,
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/"
        "landing_checkpoint.py": "7" * 64,
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/"
        "test_landing_checkpoint.py": "8" * 64,
        "apps/miroflow-agent/tests/canonical_v2/test_landing_matrix_replay.py": "9"
        * 64,
    }


def _manifest(module: Any) -> dict[str, Any]:
    snapshot = _snapshot(module)
    return module.build_checkpoint_manifest(
        checkpoint_id="canonical-v2-s4-landing-20260711T220000Z-cef42a1",
        created_at="2026-07-11T22:00:00+00:00",
        git_commit="cef42a1e075d30c5a0e179f34ab543b4878edabd",
        worktree_state="clean",
        git_status_sha256="b" * 64,
        git_diff_sha256="c" * 64,
        implementation_artifacts=_implementation_artifacts(),
        openspec_tree_sha256="2" * 64,
        threshold_registry_sha256=(
            "bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc"
        ),
        corpus_manifest_sha256=(
            "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088"
        ),
        gate=_gate(),
        inputs=_inputs(),
        source_revalidation={
            "after_dump": "passed",
            "before_dump": "passed",
            "source_count": 6,
        },
        candidate_target_before=_target(),
        candidate_target_after=_target(),
        snapshot_before=snapshot,
        snapshot_after=snapshot,
        dump={
            "byte_size": 1234,
            "format": "postgresql-custom",
            "relative_path": "candidate-landing.dump",
            "sha256": "5" * 64,
            "archive_list_exit_code": 0,
            "archive_list_sha256": "a" * 64,
            "archive_toc_line_count": 42,
        },
        tool_versions={
            "docker": "Docker version 28.3.2",
            "pg_dump": "pg_dump (PostgreSQL) 16.9",
            "pg_restore": "pg_restore (PostgreSQL) 16.9",
            "python": "3.12.11",
        },
        command_evidence=[
            {
                "command_id": "candidate-pg-dump",
                "exit_code": 0,
                "sanitized_argv": ["docker", "exec", "<candidate>", "pg_dump"],
            }
        ],
    )


def test_table_hash_is_order_independent_but_duplicate_sensitive() -> None:
    module = _module()

    ordered = module.summarize_table_rows(['{"id":2}', '{"id":1}'])
    reversed_rows = module.summarize_table_rows(['{"id":1}', '{"id":2}'])
    duplicate = module.summarize_table_rows(['{"id":1}', '{"id":2}', '{"id":2}'])

    assert ordered == reversed_rows
    assert ordered["row_count"] == 2
    assert duplicate["row_count"] == 3
    assert duplicate["rows_sha256"] != ordered["rows_sha256"]


def test_integrity_probe_matches_c2_0004_schema_and_counts_all_violations() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "OR started_at IS NULL OR finished_at IS NULL" in source
    assert "OR started_at IS NULL OR completed_at IS NULL" not in source
    assert (
        '"(SELECT count(*)::int FROM ("\n'
        '        "SELECT record.record_id FROM landing.source_record record "'
    ) in source
    assert '"HAVING count(error.record_id) = 0"' in source
    assert '") AS partial_without_error) AS partial_record_without_error"' in source


def test_logical_snapshot_binds_every_table_and_rejects_landing_drift() -> None:
    module = _module()
    snapshot = _snapshot(module)

    module.require_landing_checkpoint_snapshot(snapshot)
    assert snapshot["tables"]["landing.evidence_artifact"]["row_count"] == 15
    assert snapshot["non_landing_row_count"] == 0
    assert len(snapshot["logical_sha256"]) == 64

    changed = deepcopy(snapshot)
    changed["tables"]["landing.source_record"]["row_count"] = 20
    with pytest.raises(module.CheckpointError, match="landing table counts"):
        module.require_landing_checkpoint_snapshot(changed)

    changed = deepcopy(snapshot)
    changed["landing_metrics"]["integrity_violation_counts"]["artifact_cycle"] = 1
    with pytest.raises(module.CheckpointError, match="integrity"):
        module.require_landing_checkpoint_snapshot(changed)

    changed = deepcopy(snapshot)
    del changed["tables"]["knowledge.policy"]
    changed["table_count"] -= 1
    changed["logical_sha256"] = module.sha256_bytes(
        module.canonical_json_bytes(
            {key: value for key, value in changed.items() if key != "logical_sha256"}
        )
    )
    with pytest.raises(module.CheckpointError, match="table inventory"):
        module.require_landing_checkpoint_snapshot(changed)

    changed = deepcopy(snapshot)
    changed["tables"]["knowledge.policy"]["rows_sha256"] = "invalid"
    changed["logical_sha256"] = module.sha256_bytes(
        module.canonical_json_bytes(
            {key: value for key, value in changed.items() if key != "logical_sha256"}
        )
    )
    with pytest.raises(module.CheckpointError, match="table summary"):
        module.require_landing_checkpoint_snapshot(changed)

    changed = deepcopy(snapshot)
    del changed["landing_metrics"]["integrity_violation_counts"]["artifact_cycle"]
    changed["logical_sha256"] = module.sha256_bytes(
        module.canonical_json_bytes(
            {key: value for key, value in changed.items() if key != "logical_sha256"}
        )
    )
    with pytest.raises(module.CheckpointError, match="integrity key"):
        module.require_landing_checkpoint_snapshot(changed)


def test_checkpoint_manifest_requires_exact_inputs_and_stable_candidate() -> None:
    module = _module()
    manifest = _manifest(module)

    assert manifest["state"] == "candidate"
    assert manifest["provider_usage"] == "not_used"
    assert manifest["snapshot"]["logical_sha256"] == _snapshot(module)["logical_sha256"]

    snapshot = _snapshot(module)
    changed = deepcopy(snapshot)
    changed["logical_sha256"] = "0" * 64
    with pytest.raises(module.CheckpointError, match="changed during dump"):
        module.build_checkpoint_manifest(
            checkpoint_id="canonical-v2-s4-landing-20260711T220000Z-cef42a1",
            created_at="2026-07-11T22:00:00+00:00",
            git_commit="cef42a1e075d30c5a0e179f34ab543b4878edabd",
            worktree_state="clean",
            git_status_sha256="b" * 64,
            git_diff_sha256="c" * 64,
            implementation_artifacts=_implementation_artifacts(),
            openspec_tree_sha256="2" * 64,
            threshold_registry_sha256=(
                "bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc"
            ),
            corpus_manifest_sha256=(
                "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088"
            ),
            gate=_gate(),
            inputs=_inputs(),
            source_revalidation={
                "after_dump": "passed",
                "before_dump": "passed",
                "source_count": 6,
            },
            candidate_target_before=_target(),
            candidate_target_after=_target(),
            snapshot_before=snapshot,
            snapshot_after=changed,
            dump={
                "byte_size": 1234,
                "format": "postgresql-custom",
                "relative_path": "candidate-landing.dump",
                "sha256": "5" * 64,
                "archive_list_exit_code": 0,
                "archive_list_sha256": "a" * 64,
                "archive_toc_line_count": 42,
            },
            tool_versions={
                "docker": "Docker version 28.3.2",
                "pg_dump": "pg_dump (PostgreSQL) 16.9",
                "pg_restore": "pg_restore (PostgreSQL) 16.9",
                "python": "3.12.11",
            },
            command_evidence=[],
        )

    bad_inputs = _inputs()
    bad_inputs["landing_matrix_sha256"] = "0" * 64
    with pytest.raises(module.CheckpointError, match="landing matrix"):
        module.require_exact_checkpoint_inputs(bad_inputs)

    wrong_target = _target()
    wrong_target["system_identifier"] = "9000000000000000000"
    with pytest.raises(module.CheckpointError, match="candidate target"):
        module.require_exact_candidate_target(wrong_target)

    with pytest.raises(module.CheckpointError, match="Task 4.4 commit"):
        module.require_task4_4_commit("0" * 40)

    missing_tool = _implementation_artifacts()
    del missing_tool[
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/"
        "test_landing_checkpoint.py"
    ]
    with pytest.raises(module.CheckpointError, match="implementation artifact"):
        module.require_implementation_artifacts(missing_tool)


def test_fresh_replay_binds_byte_stable_summary_and_separate_target_execution(
    tmp_path: Path,
) -> None:
    module = _module()
    run_root = MODULE_PATH.parents[1]
    committed_summary = run_root / "s4d/landing-replay-summary.json"
    fresh_summary = tmp_path / "fresh-summary.json"
    fresh_execution = tmp_path / "fresh-execution.json"
    fresh_summary.write_bytes(committed_summary.read_bytes())
    execution = _fresh_execution()
    fresh_execution.write_bytes(module.document_bytes(execution))

    inputs = module._checkpoint_inputs(
        evidence_root=run_root,
        fresh_replay_summary=fresh_summary,
        fresh_replay_execution=fresh_execution,
    )

    assert (
        inputs["fresh_guarded_replay_summary"]["sha256"]
        == (inputs["landing_replay_summary_sha256"])
    )
    assert inputs["fresh_guarded_replay_execution"]["document"] == execution

    unsafe_execution = deepcopy(execution)
    unsafe_execution["target_after"]["network_mode"] = "bridge"
    fresh_execution.write_bytes(module.document_bytes(unsafe_execution))
    with pytest.raises(module.CheckpointError, match="fresh replay execution"):
        module._checkpoint_inputs(
            evidence_root=run_root,
            fresh_replay_summary=fresh_summary,
            fresh_replay_execution=fresh_execution,
        )


def _restore_inspect(tmp_path: Path) -> dict[str, Any]:
    checkpoint_root = tmp_path / "checkpoint"
    socket_root = tmp_path / "socket" / "postgresql"
    return {
        "Id": "a" * 64,
        "Image": "sha256:" + "b" * 64,
        "Name": "/canonical-v2-s4e-restore-20260711",
        "State": {"Running": True},
        "HostConfig": {
            "NetworkMode": "none",
            "PortBindings": {},
            "ReadonlyRootfs": True,
            "RestartPolicy": {"Name": "no"},
            "Tmpfs": {"/var/lib/postgresql/data": "rw,noexec,nosuid,size=1073741824"},
        },
        "NetworkSettings": {"Networks": {"none": {"Gateway": "", "IPAddress": ""}}},
        "Mounts": [
            {
                "Destination": "/checkpoint",
                "RW": False,
                "Source": str(checkpoint_root),
                "Type": "bind",
            },
            {
                "Destination": "/var/run/postgresql",
                "RW": True,
                "Source": str(socket_root),
                "Type": "bind",
            },
        ],
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["HostConfig"].update(NetworkMode="bridge"),
            "network",
        ),
        (
            lambda value: value["HostConfig"]["PortBindings"].update(
                {"5432/tcp": [{"HostPort": "15432"}]}
            ),
            "ports",
        ),
        (
            lambda value: value["HostConfig"]["Tmpfs"].clear(),
            "tmpfs",
        ),
        (
            lambda value: value["Mounts"].append(
                {
                    "Destination": "/var/lib/postgresql/data",
                    "Name": "anonymous-volume",
                    "RW": True,
                    "Type": "volume",
                }
            ),
            "persistent",
        ),
        (
            lambda value: value["HostConfig"].update(ReadonlyRootfs=False),
            "read-only",
        ),
        (
            lambda value: value["NetworkSettings"].update(
                Networks={"bridge": {"Gateway": "172.17.0.1", "IPAddress": "1"}}
            ),
            "attached network",
        ),
    ],
)
def test_restore_container_policy_rejects_every_isolation_drift(
    tmp_path: Path,
    mutate: Any,
    message: str,
) -> None:
    module = _module()
    (tmp_path / "checkpoint").mkdir()
    (tmp_path / "socket").mkdir(mode=0o770)
    (tmp_path / "socket").chmod(0o770)
    (tmp_path / "socket" / "postgresql").mkdir(mode=0o777)
    (tmp_path / "socket" / "postgresql").chmod(0o770)
    inspect = _restore_inspect(tmp_path)
    accepted = module.require_restore_container_policy(
        inspect,
        expected_container="canonical-v2-s4e-restore-20260711",
        expected_container_id="a" * 64,
        expected_image_id="sha256:" + "b" * 64,
        checkpoint_root=tmp_path / "checkpoint",
        socket_parent=tmp_path / "socket",
        socket_mount_root=tmp_path / "socket" / "postgresql",
    )
    assert accepted["network_mode"] == "none"
    assert accepted["pgdata_storage"] == "tmpfs"

    changed = deepcopy(inspect)
    mutate(changed)
    with pytest.raises(module.CheckpointError, match=message):
        module.require_restore_container_policy(
            changed,
            expected_container="canonical-v2-s4e-restore-20260711",
            expected_container_id="a" * 64,
            expected_image_id="sha256:" + "b" * 64,
            checkpoint_root=tmp_path / "checkpoint",
            socket_parent=tmp_path / "socket",
            socket_mount_root=tmp_path / "socket" / "postgresql",
        )


@pytest.mark.parametrize("entrypoint_mode", [0o770, 0o3775, 0o777])
def test_bounded_socket_parent_accepts_postgres_entrypoint_mode_drift(
    tmp_path: Path,
    entrypoint_mode: int,
) -> None:
    module = _module()
    (tmp_path / "checkpoint").mkdir()
    (tmp_path / "socket").mkdir(mode=0o770)
    (tmp_path / "socket").chmod(0o770)
    socket_mount = tmp_path / "socket" / "postgresql"
    socket_mount.mkdir(mode=0o777)
    socket_mount.chmod(entrypoint_mode)

    receipt = module.require_restore_container_policy(
        _restore_inspect(tmp_path),
        expected_container="canonical-v2-s4e-restore-20260711",
        expected_container_id="a" * 64,
        expected_image_id="sha256:" + "b" * 64,
        checkpoint_root=tmp_path / "checkpoint",
        socket_parent=tmp_path / "socket",
        socket_mount_root=socket_mount,
    )

    assert receipt["socket_parent_mode"] == "0770"
    assert int(receipt["socket_mount_mode"], 8) & 0o070 == 0o070


def test_restore_verification_requires_independent_system_and_exact_parity() -> None:
    module = _module()
    manifest = _manifest(module)
    snapshot = manifest["snapshot"]
    restore_target = {
        "container_name": "canonical-v2-s4e-restore-20260711",
        "container_id": "a" * 64,
        "container_read_only": True,
        "database": "miroflow_canonical_v2_s4e_restore_20260711",
        "database_marker": (
            "miroflow:destructive-target:v1:disposable:"
            "miroflow_canonical_v2_s4e_restore_20260711"
        ),
        "image_id": "sha256:" + "b" * 64,
        "network_mode": "none",
        "checkpoint_mount_read_only": True,
        "pgdata_storage": "tmpfs",
        "persistent_volume_count": 0,
        "published_ports": [],
        "restart_policy": "no",
        "socket_mount_gid": os.getgid(),
        "socket_mount_mode": "0770",
        "socket_parent_mode": "0770",
        "system_identifier": "9000000000000000000",
    }
    verification = module.build_restore_verification(
        checkpoint_manifest=manifest,
        restore_target=restore_target,
        restore_snapshot=snapshot,
        dump_sha256_after="5" * 64,
        archive_list_exit_code=0,
        pg_restore_exit_code=0,
        docker_volume_set_before="6" * 64,
        docker_volume_set_after="6" * 64,
        cleanup={
            "container_absent": True,
            "owned_container_id": "a" * 64,
            "socket_root_absent": True,
        },
    )
    assert verification["state"] == "passed"
    assert verification["logical_parity"] is True

    same_system = deepcopy(restore_target)
    same_system["system_identifier"] = _target()["system_identifier"]
    with pytest.raises(module.CheckpointError, match="independent system"):
        module.build_restore_verification(
            checkpoint_manifest=manifest,
            restore_target=same_system,
            restore_snapshot=snapshot,
            dump_sha256_after="5" * 64,
            archive_list_exit_code=0,
            pg_restore_exit_code=0,
            docker_volume_set_before="6" * 64,
            docker_volume_set_after="6" * 64,
            cleanup={
                "container_absent": True,
                "owned_container_id": "a" * 64,
                "socket_root_absent": True,
            },
        )

    changed_snapshot = deepcopy(snapshot)
    changed_snapshot["logical_sha256"] = "0" * 64
    with pytest.raises(module.CheckpointError, match="logical parity"):
        module.build_restore_verification(
            checkpoint_manifest=manifest,
            restore_target=restore_target,
            restore_snapshot=changed_snapshot,
            dump_sha256_after="5" * 64,
            archive_list_exit_code=0,
            pg_restore_exit_code=0,
            docker_volume_set_before="6" * 64,
            docker_volume_set_after="6" * 64,
            cleanup={
                "container_absent": True,
                "owned_container_id": "a" * 64,
                "socket_root_absent": True,
            },
        )

    unsafe_target = deepcopy(restore_target)
    unsafe_target["network_mode"] = "bridge"
    with pytest.raises(module.CheckpointError, match="restore target policy"):
        module.build_restore_verification(
            checkpoint_manifest=manifest,
            restore_target=unsafe_target,
            restore_snapshot=snapshot,
            dump_sha256_after="5" * 64,
            archive_list_exit_code=0,
            pg_restore_exit_code=0,
            docker_volume_set_before="6" * 64,
            docker_volume_set_after="6" * 64,
            cleanup={
                "container_absent": True,
                "owned_container_id": "a" * 64,
                "socket_root_absent": True,
            },
        )


def test_restore_name_and_cleanup_are_bound_to_owned_container_id() -> None:
    module = _module()
    owned_id = "a" * 64

    assert module.parse_exact_container_lookup("") is None
    assert module.parse_exact_container_lookup(f"{owned_id}\n") == owned_id
    with pytest.raises(module.CheckpointError, match="ambiguous"):
        module.parse_exact_container_lookup(f"{owned_id}\n{'b' * 64}\n")
    with pytest.raises(module.CheckpointError, match="identity"):
        module.parse_exact_container_lookup("not-a-container-id\n")

    module.require_restore_name_absent(None)
    with pytest.raises(module.CheckpointError, match="already exists"):
        module.require_restore_name_absent(owned_id)

    module.require_owned_restore_container(
        observed_container_id=owned_id,
        expected_container_id=owned_id,
    )
    with pytest.raises(module.CheckpointError, match="ownership"):
        module.require_owned_restore_container(
            observed_container_id="b" * 64,
            expected_container_id=owned_id,
        )

    receipt = module.require_restore_cleanup(
        removed_container_id=owned_id,
        expected_container_id=owned_id,
        observed_container_id_after=None,
        socket_root_absent=True,
    )
    assert receipt == {
        "container_absent": True,
        "owned_container_id": owned_id,
        "socket_root_absent": True,
    }
    with pytest.raises(module.CheckpointError, match="cleanup"):
        module.require_restore_cleanup(
            removed_container_id="b" * 64,
            expected_container_id=owned_id,
            observed_container_id_after=None,
            socket_root_absent=True,
        )


def test_restore_readiness_requires_final_pid1_and_stable_database() -> None:
    module = _module()

    assert (
        module.advance_final_postgres_readiness(
            pid1_command="docker-entrypoint.sh",
            pg_isready_exit_code=0,
            consecutive_successes=2,
        )
        == 0
    )
    assert (
        module.advance_final_postgres_readiness(
            pid1_command="postgres",
            pg_isready_exit_code=1,
            consecutive_successes=2,
        )
        == 0
    )
    assert (
        module.advance_final_postgres_readiness(
            pid1_command="postgres",
            pg_isready_exit_code=0,
            consecutive_successes=2,
        )
        == 3
    )


def test_owned_restore_cleanup_stops_gracefully_before_id_only_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    owned_id = "a" * 64
    observed = iter([owned_id, owned_id, None])
    argv_seen: list[list[str]] = []

    monkeypatch.setattr(
        module,
        "_lookup_exact_container_id",
        lambda _name: next(observed),
    )

    def fake_run(argv: list[str], **kwargs: Any) -> tuple[Any, dict[str, Any]]:
        argv_seen.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr=""), {
            "command_id": kwargs["command_id"],
            "exit_code": 0,
            "sanitized_argv": argv,
        }

    monkeypatch.setattr(module, "_run_text_command", fake_run)
    socket_root = tmp_path / "socket-root"
    (socket_root / "postgresql").mkdir(parents=True)

    receipt, commands = module._remove_owned_restore_target(
        container_name="canonical-v2-s4e-restore-20260711",
        container_id=owned_id,
        socket_root=socket_root,
    )

    assert argv_seen == [
        ["docker", "stop", "--time", "30", owned_id],
        ["docker", "rm", "--volumes", owned_id],
    ]
    assert all("--force" not in argv for argv in argv_seen)
    assert len(commands) == 2
    assert receipt["owned_container_id"] == owned_id


def test_evidence_copy_is_exclusive_and_never_deletes_existing_file(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "source.json"
    source.write_bytes(b'{"state":"passed"}\n')
    expected_sha256 = module.sha256_file(source)
    destination = tmp_path / "new" / "evidence.json"

    module._copy_file_exclusive_verified(
        source,
        destination,
        expected_sha256=expected_sha256,
    )
    assert destination.read_bytes() == source.read_bytes()

    existing = tmp_path / "existing.json"
    existing.write_bytes(b"do-not-delete")
    with pytest.raises(module.CheckpointError, match="not new"):
        module._copy_file_exclusive_verified(
            source,
            existing,
            expected_sha256=expected_sha256,
        )
    assert existing.read_bytes() == b"do-not-delete"


@pytest.mark.parametrize(
    "argv",
    [
        ["tool", "--database-url", "postgresql://secret@host/db"],
        ["tool", "--database-url=postgresql://secret@host/db"],
    ],
)
def test_checkpoint_command_evidence_redacts_every_dsn_form(argv: list[str]) -> None:
    module = _module()

    sanitized = module._sanitized_argv(argv)

    assert "secret" not in " ".join(sanitized)
    assert "postgresql://" not in " ".join(sanitized)


@pytest.mark.parametrize("case", ["duplicate", "nan"])
def test_checkpoint_json_loader_rejects_ambiguous_documents(
    tmp_path: Path,
    case: str,
) -> None:
    module = _module()
    payload = '{"state":"candidate","state":"shadow"}'
    if case == "nan":
        payload = '{"state":"candidate","value":NaN}'
    path = tmp_path / f"{case}.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(module.CheckpointError, match="duplicate|non-standard"):
        module.load_json_object(path, label="checkpoint fixture")
