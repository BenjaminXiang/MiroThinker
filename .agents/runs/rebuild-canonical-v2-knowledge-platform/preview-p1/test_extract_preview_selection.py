from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "extract_preview_selection.py"
MANIFEST_PATH = HERE / "preview-selection-manifest-v1.json"

EVIDENCE_ROOT = Path("/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z")
SOURCE_RELATIVE_PATH = Path("workspace/logs/data_agents/released_objects.db")
SOURCE_PATH = EVIDENCE_ROOT / SOURCE_RELATIVE_PATH
SOURCE_ID = "inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0"

ROW_DESCRIPTORS = (
    {
        "id": "COMP-3B95F48EB687",
        "object_type": "company",
        "display_name": "深圳森合创新科技有限公司",
        "payload_json_sha256": (
            "9d946d96fdfd216b80425931acb5b572af82c1930df72f7986abd2c559f052de"
        ),
    },
    {
        "id": "PAT-009605B1E383",
        "object_type": "patent",
        "display_name": "底刀调节结构及割草机器人",
        "payload_json_sha256": (
            "90a9ed2538147778a70f2e112e9c40a0103114063308eee4e49c0f7707e9610c"
        ),
    },
    {
        "id": "PROF-8000C9F994C3",
        "object_type": "professor",
        "display_name": "丁文伯",
        "payload_json_sha256": (
            "8164448be7dcb5c82ccb5a19ea801f38be5aaa2d24bf421eb719824c3164ae4e"
        ),
    },
    {
        "id": "PAPER-1258119BC264",
        "object_type": "paper",
        "display_name": (
            "Keystroke dynamics enabled authentication and identification using "
            "triboelectric nanogenerator array"
        ),
        "payload_json_sha256": (
            "26abe842affe9cf940eb2af637ff53620287def9dc4978fae56bfb285934e7d0"
        ),
    },
    {
        "id": "PROF-PAPER-LINK-00A7B60465F2",
        "object_type": "professor_paper_link",
        "display_name": (
            "丁文伯 -> Keystroke dynamics enabled authentication and identification "
            "using triboelectric nanogenerator array"
        ),
        "payload_json_sha256": (
            "9b05dda6e0cc0911b588849c30e67398347aea3e7e35455d63e76cc3774b5225"
        ),
    },
)

EXPECTED_MANIFEST: dict[str, Any] = {
    "schema_version": "preview-selection-manifest-v1",
    "selection_id": "canonical-v2-real-data-preview-p1-v1",
    "accepted_checkpoint": {
        "source_inventory_sha256": (
            "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
        ),
        "backup_manifest_sha256": (
            "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
        ),
        "restore_verification_sha256": (
            "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
        ),
        "acceptance_record_sha256": (
            "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
        ),
    },
    "source": {
        "source_id": SOURCE_ID,
        "relative_path": SOURCE_RELATIVE_PATH.as_posix(),
        "bytes": 20_267_008,
        "sha256": ("7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce"),
    },
    "rows": list(ROW_DESCRIPTORS),
    "expected_public_domain_counts": {
        "company": 1,
        "paper": 1,
        "patent": 1,
        "professor": 1,
    },
    "expected_relationships": [
        {
            "kind": "company_patent",
            "source_id": "COMP-3B95F48EB687",
            "target_id": "PAT-009605B1E383",
        },
        {
            "kind": "professor_authored_paper",
            "source_id": "PROF-8000C9F994C3",
            "target_id": "PAPER-1258119BC264",
            "link_row_id": "PROF-PAPER-LINK-00A7B60465F2",
        },
    ],
    "expected_row_count": 5,
    "selected_row_set_sha256": (
        "0a806a93c66159b1a824b52131041aa6ff7877dc3d808d1d2c56ffc5efd76f06"
    ),
    "public_field_policy_version": "preview-public-fields-v1",
}

EXPECTED_CORE_FIELDS = {
    "company": {
        "industry",
        "key_personnel",
        "name",
        "normalized_name",
        "website",
    },
    "patent": {
        "abstract",
        "applicants",
        "company_ids",
        "filing_date",
        "grant_date",
        "inventors",
        "ipc_codes",
        "patent_number",
        "patent_type",
        "professor_ids",
        "publication_date",
        "technology_effect",
        "title",
        "title_en",
    },
    "professor": {
        "academic_positions",
        "awards",
        "citation_count",
        "company_roles",
        "department",
        "education_structured",
        "h_index",
        "homepage",
        "institution",
        "name",
        "paper_count",
        "patent_ids",
        "projects",
        "research_directions",
        "title",
        "top_papers",
        "work_experience",
    },
    "paper": {
        "abstract",
        "arxiv_id",
        "authors",
        "citation_count",
        "doi",
        "enrichment_sources",
        "fields_of_study",
        "funders",
        "keywords",
        "license",
        "oa_status",
        "professor_ids",
        "publication_date",
        "reference_count",
        "title",
        "title_zh",
        "tldr",
        "venue",
        "year",
    },
    "professor_paper_link": {
        "evidence_source",
        "evidence_url",
        "link_status",
        "paper_id",
        "paper_title",
        "professor_id",
        "professor_name",
    },
}

EXPECTED_SUMMARY_FIELDS = {
    "company": {
        "evaluation_summary",
        "profile_summary",
        "technology_route_summary",
    },
    "patent": {"summary_text"},
    "professor": {"evaluation_summary", "profile_summary"},
    "paper": {"summary_text", "summary_zh"},
    "professor_paper_link": {"match_reason"},
}


def _load_module() -> ModuleType:
    if not MODULE_PATH.is_file():
        pytest.fail(f"missing extractor module: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("preview_p1_extractor", MODULE_PATH)
    if spec is None or spec.loader is None:
        pytest.fail(f"cannot load extractor module: {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_source_layout(tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / SOURCE_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE_PATH, target)
    return tmp_path, target


def _source_stat(path: Path) -> tuple[int, ...]:
    result = path.stat()
    return (
        result.st_dev,
        result.st_ino,
        result.st_mode,
        result.st_uid,
        result.st_gid,
        result.st_size,
        result.st_mtime_ns,
        result.st_ctime_ns,
    )


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_payload(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_payload(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_payload(child)


def test_manifest_freezes_the_exact_accepted_source_and_five_rows() -> None:
    module = _load_module()
    if not MANIFEST_PATH.is_file():
        pytest.fail(f"missing selection manifest: {MANIFEST_PATH}")

    raw_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert raw_manifest == EXPECTED_MANIFEST
    assert module.load_selection_manifest(MANIFEST_PATH) == EXPECTED_MANIFEST

    canonical_rows = sorted(raw_manifest["rows"], key=lambda row: row["id"])
    assert _canonical_sha256(canonical_rows) == raw_manifest["selected_row_set_sha256"]


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_top_level_field",
        "changed_checkpoint_hash",
        "changed_source_path",
        "missing_row",
        "extra_row",
        "changed_payload_hash",
        "changed_row_set_hash",
        "changed_public_policy",
    ),
)
def test_manifest_loader_rejects_any_change_to_the_frozen_contract(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = _load_module()
    manifest = copy.deepcopy(EXPECTED_MANIFEST)

    if mutation == "unknown_top_level_field":
        manifest["unexpected"] = True
    elif mutation == "changed_checkpoint_hash":
        manifest["accepted_checkpoint"]["acceptance_record_sha256"] = "0" * 64
    elif mutation == "changed_source_path":
        manifest["source"]["relative_path"] = "../released_objects.db"
    elif mutation == "missing_row":
        manifest["rows"].pop()
    elif mutation == "extra_row":
        manifest["rows"].append(copy.deepcopy(manifest["rows"][0]))
    elif mutation == "changed_payload_hash":
        manifest["rows"][0]["payload_json_sha256"] = "0" * 64
    elif mutation == "changed_row_set_hash":
        manifest["selected_row_set_sha256"] = "0" * 64
    elif mutation == "changed_public_policy":
        manifest["public_field_policy_version"] = "preview-public-fields-v2"
    else:  # pragma: no cover - keeps the mutation table exhaustive
        raise AssertionError(mutation)

    candidate = tmp_path / "manifest.json"
    _write_manifest(candidate, manifest)
    with pytest.raises(ValueError, match="manifest"):
        module.load_selection_manifest(candidate)


def test_extracts_exact_rows_and_validates_embedded_identities() -> None:
    module = _load_module()
    rows = module.extract_preview_selection(EVIDENCE_ROOT, MANIFEST_PATH)

    assert isinstance(rows, tuple)
    assert [row["id"] for row in rows] == [row["id"] for row in ROW_DESCRIPTORS]
    assert [row["object_type"] for row in rows] == [
        row["object_type"] for row in ROW_DESCRIPTORS
    ]
    assert len(rows) == EXPECTED_MANIFEST["expected_row_count"]

    expected_by_id = {row["id"]: row for row in ROW_DESCRIPTORS}
    for row in rows:
        expected = expected_by_id[row["id"]]
        assert row["display_name"] == expected["display_name"]
        assert row["payload_json_sha256"] == expected["payload_json_sha256"]
        artifact_material = {
            "payload_json_sha256": row["payload_json_sha256"],
            "source_id": SOURCE_ID,
        }
        assert row["source_artifact_id"] == (
            "preview-source-artifact:sha256:" + _canonical_sha256(artifact_material)
        )

    by_kind = {row["object_type"]: row for row in rows}
    assert (
        by_kind["company"]["core_facts"]["name"] == by_kind["company"]["display_name"]
    )
    assert by_kind["patent"]["core_facts"]["title"] == by_kind["patent"]["display_name"]
    assert (
        by_kind["professor"]["core_facts"]["name"]
        == by_kind["professor"]["display_name"]
    )
    assert by_kind["paper"]["core_facts"]["title"] == by_kind["paper"]["display_name"]


def test_relationship_endpoints_are_exact_and_bidirectionally_grounded() -> None:
    module = _load_module()
    rows = module.extract_preview_selection(EVIDENCE_ROOT, MANIFEST_PATH)
    by_kind = {row["object_type"]: row for row in rows}

    assert by_kind["patent"]["core_facts"]["company_ids"] == ["COMP-3B95F48EB687"]
    assert by_kind["paper"]["core_facts"]["professor_ids"] == ["PROF-8000C9F994C3"]

    link = by_kind["professor_paper_link"]
    assert link["core_facts"] == {
        "evidence_source": "openalex",
        "evidence_url": "https://doi.org/10.1016/j.mattod.2018.01.006",
        "link_status": "verified",
        "paper_id": "PAPER-1258119BC264",
        "paper_title": by_kind["paper"]["display_name"],
        "professor_id": "PROF-8000C9F994C3",
        "professor_name": by_kind["professor"]["display_name"],
    }


def test_public_projection_uses_only_the_fixed_allowlist() -> None:
    module = _load_module()
    rows = module.extract_preview_selection(EVIDENCE_ROOT, MANIFEST_PATH)
    expected_row_fields = {
        "id",
        "object_type",
        "display_name",
        "core_facts",
        "summary_fields",
        "evidence",
        "last_updated",
        "quality_status",
        "payload_json_sha256",
        "source_artifact_id",
    }
    forbidden_keys = {
        "email",
        "office",
        "pdf_path",
        "source_file",
        "file_path",
        "local_path",
        "verified_by",
    }

    for row in rows:
        kind = row["object_type"]
        assert set(row) == expected_row_fields
        assert set(row["core_facts"]) == EXPECTED_CORE_FIELDS[kind]
        assert set(row["summary_fields"]) == EXPECTED_SUMMARY_FIELDS[kind]
        assert row["quality_status"] == "ready"
        assert row["last_updated"].endswith("Z")

        for evidence in row["evidence"]:
            assert set(evidence) == {
                "confidence",
                "fetched_at",
                "snippet",
                "source_type",
                "source_url",
            }
            source_url = evidence["source_url"]
            assert source_url is None or source_url.startswith(("http://", "https://"))

        public_payload = {
            "core_facts": row["core_facts"],
            "summary_fields": row["summary_fields"],
            "evidence": row["evidence"],
        }
        for key, value in _walk_payload(public_payload):
            assert key not in forbidden_keys
            assert not key.endswith("_path")
            assert not key.endswith("_sha256")
            if isinstance(value, str):
                assert not value.startswith(("/", "file://", "\\\\"))
                assert ":\\" not in value


def test_sqlite_access_is_immutable_query_only_and_one_exact_query_per_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    real_connect = sqlite3.connect
    connect_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []
    execute_calls: list[tuple[str, tuple[object, ...]]] = []

    class RecordingConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def __enter__(self) -> RecordingConnection:
            return self

        def __exit__(self, *exc_info: object) -> None:
            self._connection.close()

        def execute(
            self,
            statement: str,
            parameters: tuple[object, ...] = (),
        ) -> sqlite3.Cursor:
            execute_calls.append((statement, parameters))
            return self._connection.execute(statement, parameters)

    def recording_connect(
        database: object,
        *args: object,
        **kwargs: object,
    ) -> RecordingConnection:
        connect_calls.append((database, args, kwargs))
        return RecordingConnection(real_connect(database, *args, **kwargs))

    monkeypatch.setattr(module.sqlite3, "connect", recording_connect)
    module.extract_preview_selection(EVIDENCE_ROOT, MANIFEST_PATH)

    assert len(connect_calls) == 1
    database, args, kwargs = connect_calls[0]
    assert not args
    assert kwargs == {"uri": True}
    assert isinstance(database, str)
    assert "mode=ro" in database
    assert "immutable=1" in database

    assert execute_calls[0] == ("PRAGMA query_only=ON", ())
    assert execute_calls[1] == ("PRAGMA query_only", ())
    select_calls = [
        (statement, parameters)
        for statement, parameters in execute_calls
        if "FROM released_objects" in statement
    ]
    assert len(select_calls) == len(ROW_DESCRIPTORS)
    assert [parameters for _, parameters in select_calls] == [
        (row["id"],) for row in ROW_DESCRIPTORS
    ]
    assert all("WHERE id = ?" in statement for statement, _ in select_calls)


def test_source_symlink_is_rejected_by_the_no_follow_gate(tmp_path: Path) -> None:
    module = _load_module()
    target = tmp_path / SOURCE_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(SOURCE_PATH)

    with pytest.raises(ValueError, match="source"):
        module.extract_preview_selection(tmp_path, MANIFEST_PATH)


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_any_sqlite_sidecar_is_rejected(tmp_path: Path, suffix: str) -> None:
    module = _load_module()
    evidence_root, target = _copy_source_layout(tmp_path)
    Path(f"{target}{suffix}").write_bytes(b"")

    with pytest.raises(ValueError, match="sidecar"):
        module.extract_preview_selection(evidence_root, MANIFEST_PATH)


def test_changed_source_bytes_are_rejected_before_sqlite_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    evidence_root, target = _copy_source_layout(tmp_path)
    with target.open("r+b") as changed:
        changed.seek(-1, os.SEEK_END)
        original = changed.read(1)
        changed.seek(-1, os.SEEK_END)
        changed.write(bytes([original[0] ^ 0x01]))

    def unexpected_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(module.sqlite3, "connect", unexpected_connect)
    with pytest.raises(ValueError, match="source sha256"):
        module.extract_preview_selection(evidence_root, MANIFEST_PATH)


def test_post_read_stat_change_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    evidence_root, target = _copy_source_layout(tmp_path)
    real_connect = sqlite3.connect

    def connect_then_touch(
        database: object,
        *args: object,
        **kwargs: object,
    ) -> sqlite3.Connection:
        connection = real_connect(database, *args, **kwargs)
        current = target.stat()
        os.utime(
            target,
            ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000_000),
        )
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", connect_then_touch)
    with pytest.raises(ValueError, match="source changed"):
        module.extract_preview_selection(evidence_root, MANIFEST_PATH)


def test_real_source_bytes_metadata_and_sidecars_are_unchanged() -> None:
    module = _load_module()
    before_stat = _source_stat(SOURCE_PATH)
    before_hash = _source_hash(SOURCE_PATH)
    sidecars = tuple(
        Path(f"{SOURCE_PATH}{suffix}") for suffix in ("-wal", "-shm", "-journal")
    )
    assert not any(os.path.lexists(path) for path in sidecars)

    module.extract_preview_selection(EVIDENCE_ROOT, MANIFEST_PATH)

    assert (
        _source_hash(SOURCE_PATH)
        == before_hash
        == EXPECTED_MANIFEST["source"]["sha256"]
    )
    assert _source_stat(SOURCE_PATH) == before_stat
    assert not any(os.path.lexists(path) for path in sidecars)
