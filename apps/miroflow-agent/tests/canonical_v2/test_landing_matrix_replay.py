from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    REPO_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s4d"
    / "replay_landing_matrix.py"
)
MATRIX_PATH = MODULE_PATH.with_name("landing-matrix.json")
NOW = datetime(2026, 7, 11, 20, 15, tzinfo=timezone.utc)


def _module() -> Any:
    name = "canonical_v2_s4d_replay_landing_matrix"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_verified_pair(
    tmp_path: Path,
    *,
    relative_path: str,
    content: bytes,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    backup_root = tmp_path / "backup"
    restore_root = tmp_path / "restore"
    digest = _sha256(content)
    object_path = f"objects/sha256/{digest[:2]}/{digest}"
    backup_path = backup_root / object_path
    restore_path = restore_root / relative_path
    backup_path.parent.mkdir(parents=True)
    restore_path.parent.mkdir(parents=True)
    backup_path.write_bytes(content)
    restore_path.write_bytes(content)
    manifest = backup_root / "manifests/member-manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "backup_bytes": len(content),
                "backup_sha256": digest,
                "copy_independent": True,
                "namespace": "workspace",
                "object_path": object_path,
                "relative_path": relative_path.removeprefix("workspace/"),
                "source_bytes": len(content),
                "source_path": f"/frozen/source/{relative_path}",
                "source_sha256": digest,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    restore_source = {
        "copy_independent": True,
        "hash_verified": True,
        "source_id": "inventory:accepted-source",
        "status": "passed",
        "probes": [
            {
                "probe": "jsonl_parse",
                "restore_path": relative_path,
                "status": "passed",
            }
        ],
    }
    return backup_root, restore_root, manifest, restore_source


def test_verified_member_requires_exact_manifest_hash_paths_and_independent_inode(
    tmp_path: Path,
) -> None:
    module = _module()
    content = b'{"source_id":"one"}\n'
    relative_path = "workspace/history/one.jsonl"
    backup_root, restore_root, manifest, restore_source = _write_verified_pair(
        tmp_path,
        relative_path=relative_path,
        content=content,
    )

    member = module.verify_member(
        source_id="inventory:accepted-source",
        member_relative_path="history/one.jsonl",
        restore_relative_path=relative_path,
        backup_root=backup_root,
        restore_root=restore_root,
        member_manifest_path=manifest,
        restore_source=restore_source,
        expected_sha256=_sha256(content),
        expected_byte_size=len(content),
    )

    assert member.backup_path.read_bytes() == content
    assert member.restore_path.read_bytes() == content
    assert member.backup_path.stat().st_ino != member.restore_path.stat().st_ino

    restore_source["probes"][0]["restore_path"] = "../outside.jsonl"
    with pytest.raises(module.MatrixReplayError, match="restore probe"):
        module.verify_member(
            source_id="inventory:accepted-source",
            member_relative_path="history/one.jsonl",
            restore_relative_path="../outside.jsonl",
            backup_root=backup_root,
            restore_root=restore_root,
            member_manifest_path=manifest,
            restore_source=restore_source,
            expected_sha256=_sha256(content),
            expected_byte_size=len(content),
        )

    restore_source["probes"][0]["restore_path"] = relative_path
    (restore_root / relative_path).write_bytes(content + b"changed")
    with pytest.raises(module.MatrixReplayError, match="hash|size"):
        module.verify_member(
            source_id="inventory:accepted-source",
            member_relative_path="history/one.jsonl",
            restore_relative_path=relative_path,
            backup_root=backup_root,
            restore_root=restore_root,
            member_manifest_path=manifest,
            restore_source=restore_source,
            expected_sha256=_sha256(content),
            expected_byte_size=len(content),
        )


def test_pg_copy_parser_and_wal_materializer_retain_fields_and_exact_errors() -> None:
    module = _module()
    paper_copy = (
        "COPY salvage.paper (paper_id, title_clean, year, abstract_clean) FROM stdin;\n"
        "PAPER-2\\tTabbed\tTitle two\t2024\t\\N\n"
        "PAPER-1\t\\N\t2023\tReadable abstract\n"
        "\\.\n"
    )
    error_copy = (
        "COPY salvage.field_errors (table_name, record_key, source_ctid, "
        "column_name, sqlstate, error_message) FROM stdin;\n"
        "paper\tPAPER-1\t(1,1)\ttitle_clean\tXX000\tcould not open relation\n"
        "\\.\n"
    )
    papers = module.parse_pg_copy_rows(
        paper_copy.splitlines(keepends=True), expected_table="salvage.paper"
    )
    selected_papers = module.parse_pg_copy_rows(
        paper_copy.splitlines(keepends=True),
        expected_table="salvage.paper",
        selected_field="paper_id",
        selected_values=frozenset({"PAPER-1"}),
    )
    errors = module.parse_pg_copy_rows(
        error_copy.splitlines(keepends=True), expected_table="salvage.field_errors"
    )
    assert selected_papers == (papers[1],)
    content = module.materialize_wal_fpi(
        papers,
        errors,
        record_keys=("PAPER-1", "PAPER-2\tTabbed"),
    )
    envelopes = [json.loads(line) for line in content.splitlines()]

    assert envelopes[0]["record_locator"] == "salvage.paper:PAPER-1"
    assert envelopes[0]["readable_fields"] == {
        "abstract_clean": "Readable abstract",
        "paper_id": "PAPER-1",
        "year": 2023,
    }
    assert envelopes[0]["field_errors"] == [
        {
            "error_code": "salvage_XX000",
            "error_kind": "missing_external_content",
            "field_path": "title_clean",
            "message": "could not open relation",
            "recoverable": False,
        }
    ]
    assert envelopes[1]["readable_fields"]["paper_id"] == "PAPER-2\tTabbed"
    assert envelopes[1]["field_errors"] == []
    assert b"placeholder" not in content.lower()

    with pytest.raises(module.MatrixReplayError, match="missing WAL/FPI"):
        module.materialize_wal_fpi(
            papers,
            errors,
            record_keys=("PAPER-NOT-RECOVERED",),
        )


def test_milvus_materializer_requires_exact_fixed_keys_and_drops_no_fields() -> None:
    module = _module()
    rows = [
        {"id": "COMP-2", "name": "Two", "industry": "AI"},
        {"id": "COMP-1", "name": "One", "industry": "Bio"},
    ]
    content = module.materialize_milvus(
        rows,
        collection="company_profiles",
        primary_key_field="id",
        primary_keys=("COMP-1", "COMP-2"),
        copy_sha256="2" * 64,
    )
    records = [json.loads(line) for line in content.splitlines()]

    assert [record["primary_key"] for record in records] == ["COMP-1", "COMP-2"]
    assert records[0]["payload"] == {
        "id": "COMP-1",
        "industry": "Bio",
        "name": "One",
    }
    assert records[0]["projection"] == {"source_copy_sha256": "2" * 64}

    with pytest.raises(module.MatrixReplayError, match="primary keys"):
        module.materialize_milvus(
            rows[:1],
            collection="company_profiles",
            primary_key_field="id",
            primary_keys=("COMP-1", "COMP-2"),
            copy_sha256="2" * 64,
        )


def test_recorded_response_materializer_does_not_invent_unknown_http_metadata() -> None:
    module = _module()
    cache = json.dumps(
        {"url": "https://example.test/professor/one", "content": "<html>One</html>"}
    ).encode()

    content = module.materialize_recorded_response(
        cache,
        source_sha256=_sha256(cache),
        relative_path="logs/debug/professor_fetch_cache/one.json",
    )
    envelope = json.loads(content)

    assert envelope == {
        "body": "<html>One</html>",
        "source_cache": {
            "content_sha256": _sha256(cache),
            "relative_path": "logs/debug/professor_fetch_cache/one.json",
        },
        "source_url": "https://example.test/professor/one",
    }
    assert "retrieved_at" not in envelope
    assert "status_code" not in envelope
    assert "content_type" not in envelope


def test_replay_prepared_entry_builds_direct_and_derived_parent_chains(
    tmp_path: Path,
) -> None:
    module = _module()
    landing_module = __import__(
        "src.data_agents.canonical_v2.evidence_landing",
        fromlist=["create_ephemeral_evidence_landing"],
    )
    landing = landing_module.create_ephemeral_evidence_landing()
    direct = b'{"source_id":"direct"}\n'
    backup_root, restore_root, manifest, restore_source = _write_verified_pair(
        tmp_path / "direct",
        relative_path="workspace/direct.jsonl",
        content=direct,
    )
    direct_source = module.verify_member(
        source_id="inventory:accepted-source",
        member_relative_path="direct.jsonl",
        restore_relative_path="workspace/direct.jsonl",
        backup_root=backup_root,
        restore_root=restore_root,
        member_manifest_path=manifest,
        restore_source=restore_source,
        expected_sha256=_sha256(direct),
        expected_byte_size=len(direct),
    )
    direct_entry = module.PreparedEntry(
        entry_id="direct-jsonl",
        source_batch_id="direct-jsonl",
        source_kind="historical_jsonl",
        source_locator="s2b-restore://run/direct.jsonl",
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-record-v1",
        parser_options={},
        content=direct,
        source=direct_source,
        derived=False,
    )
    direct_summary = module.replay_prepared_entry(
        landing, direct_entry, observed_at=NOW
    )

    derived_content = (
        b'{"collection":"company_profiles","primary_key":"COMP-1",'
        b'"payload":{"name":"One"}}\n'
    )
    derived_entry = module.PreparedEntry(
        entry_id="derived-milvus",
        source_batch_id="derived-milvus",
        source_kind="milvus_verified_copy_records",
        source_locator="s2b-derived://run/milvus.jsonl",
        parser_name="milvus_copy_records",
        parser_version="v1",
        schema_version="milvus-copy-record-v1",
        parser_options={},
        content=derived_content,
        source=direct_source,
        derived=True,
    )
    derived_summary = module.replay_prepared_entry(
        landing, derived_entry, observed_at=NOW
    )

    assert direct_summary["record_count"] == 1
    assert direct_summary["parent_kind"] == "verified_backup_copy"
    assert derived_summary["record_count"] == 1
    assert derived_summary["parent_kind"] == "verified_restore_copy"
    assert (
        derived_summary["record_set_sha256"]
        == hashlib.sha256(
            json.dumps(
                [
                    {
                        "errors": [],
                        "parse_status": "parsed",
                        "payload": {
                            "collection": "company_profiles",
                            "payload": {"name": "One"},
                            "primary_key": "COMP-1",
                        },
                        "record_locator": (
                            "collection:company_profiles:primary_key:COMP-1:line:1"
                        ),
                    }
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )

    exact = dict(derived_summary)
    module.require_expected_summary(derived_summary, exact)
    exact["record_count"] = 2
    with pytest.raises(module.MatrixReplayError, match="summary mismatch"):
        module.require_expected_summary(derived_summary, exact)


def test_matrix_preflight_blocks_destination_factory_until_every_summary_matches(
    tmp_path: Path,
) -> None:
    module = _module()
    landing_module = __import__(
        "src.data_agents.canonical_v2.evidence_landing",
        fromlist=["create_ephemeral_evidence_landing"],
    )
    content = b'{"source_id":"preflight"}\n'
    backup_root, restore_root, manifest, restore_source = _write_verified_pair(
        tmp_path,
        relative_path="workspace/preflight.jsonl",
        content=content,
    )
    source = module.verify_member(
        source_id="inventory:accepted-source",
        member_relative_path="preflight.jsonl",
        restore_relative_path="workspace/preflight.jsonl",
        backup_root=backup_root,
        restore_root=restore_root,
        member_manifest_path=manifest,
        restore_source=restore_source,
        expected_sha256=_sha256(content),
        expected_byte_size=len(content),
    )
    entry = module.PreparedEntry(
        entry_id="preflight-jsonl",
        source_batch_id="preflight-jsonl",
        source_kind="historical_jsonl",
        source_locator="s2b-restore://run/preflight.jsonl",
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-record-v1",
        parser_options={},
        content=content,
        source=source,
        derived=False,
    )
    destination_calls: list[bool] = []

    def _destination() -> Any:
        destination_calls.append(True)
        return landing_module.create_ephemeral_evidence_landing()

    with pytest.raises(module.MatrixReplayError, match="summary mismatch"):
        module.execute_prepared_matrix(
            (entry,),
            observed_at=NOW,
            expected_by_entry={"preflight-jsonl": {"record_count": 2}},
            landing_factory=_destination,
        )
    assert destination_calls == []

    observed = module.execute_prepared_matrix(
        (entry,),
        observed_at=NOW,
        expected_by_entry={},
        landing_factory=None,
    )
    accepted = module.execute_prepared_matrix(
        (entry,),
        observed_at=NOW,
        expected_by_entry={"preflight-jsonl": observed["entries"][0]},
        landing_factory=_destination,
    )

    assert destination_calls == [True]
    assert accepted == observed


def test_frozen_matrix_loader_requires_exact_six_families_and_aware_time(
    tmp_path: Path,
) -> None:
    module = _module()

    matrix = module.load_matrix(MATRIX_PATH)

    assert matrix.matrix_id == "canonical-v2-s4d-bounded-representative-v1"
    assert matrix.observed_at == NOW
    assert [entry["family"] for entry in matrix.entries] == [
        "wal_fpi_partial",
        "sqlite",
        "jsonl",
        "xlsx",
        "milvus_copy",
        "recorded_response",
    ]
    assert set(matrix.expected_by_entry) == {
        entry["entry_id"] for entry in matrix.entries
    }
    assert all(matrix.expected_by_entry.values())

    invalid = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    invalid["entries"] = invalid["entries"][:-1]
    invalid["observed_at"] = "2026-07-11T20:15:00"
    invalid_path = tmp_path / "invalid-matrix.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(module.MatrixReplayError, match="families|timezone"):
        module.load_matrix(invalid_path)


@pytest.mark.parametrize("case", ["duplicate_key", "nonstandard_number"])
def test_matrix_loader_rejects_ambiguous_json_before_using_source_paths(
    tmp_path: Path,
    case: str,
) -> None:
    module = _module()
    content = MATRIX_PATH.read_text(encoding="utf-8")
    if case == "duplicate_key":
        content = content.replace(
            '  "matrix_id": "canonical-v2-s4d-bounded-representative-v1",',
            '  "matrix_id": "shadowed-value",\n'
            '  "matrix_id": "canonical-v2-s4d-bounded-representative-v1",',
            1,
        )
    else:
        content = content.replace("{\n", '{\n  "ambiguous": NaN,\n', 1)
    path = tmp_path / f"ambiguous-{case}.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(module.MatrixReplayError, match="duplicate|non-standard"):
        module.load_matrix(path)
