from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from pathlib import Path

import pytest


NOW = datetime(2026, 7, 11, 20, 5, tzinfo=timezone.utc)


def _module():
    return import_module("src.data_agents.canonical_v2.evidence_landing")


def _registration(
    module,
    *,
    run_id: str,
    source_locator: str,
    content_path: Path,
    expected_sha256: str,
    expected_byte_size: int,
    parent_artifact_id: str | None = None,
    parent_content_sha256: str | None = None,
):
    return module.RegisterArtifactRequest(
        run_id=run_id,
        source_kind="verified_restore_copy",
        source_locator=source_locator,
        content_path=content_path,
        observed_at=NOW,
        expected_content_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
        parent_artifact_id=parent_artifact_id,
        parent_content_sha256=parent_content_sha256,
    )


def test_streaming_registration_retains_exact_file_manifest_without_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    content_path = tmp_path / "large-copy.bin"
    content_path.write_bytes((b"verified-copy-block\0" * 131_072) + b"tail")
    expected_sha256 = hashlib.sha256(content_path.read_bytes()).hexdigest()
    expected_byte_size = content_path.stat().st_size

    def _forbid_read_bytes(_path: Path) -> bytes:
        raise AssertionError("artifact registration must hash the file as a stream")

    monkeypatch.setattr(Path, "read_bytes", _forbid_read_bytes)
    artifact = landing.register_artifact(
        _registration(
            module,
            run_id="register-large-copy",
            source_locator="s2b-restore://run/large-copy.bin",
            content_path=content_path,
            expected_sha256=expected_sha256,
            expected_byte_size=expected_byte_size,
        )
    )

    assert artifact.content_sha256 == expected_sha256
    assert artifact.byte_size == expected_byte_size
    assert artifact.source_locator == "s2b-restore://run/large-copy.bin"
    assert landing.stream("register-large-copy") == ()


def test_registration_is_idempotent_and_derived_ingest_links_to_registered_parent(
    tmp_path: Path,
) -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    parent_path = tmp_path / "verified-milvus-copy.db"
    parent_path.write_bytes(b"SQLite format 3\0verified-copy")
    parent_sha256 = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    registration = _registration(
        module,
        run_id="register-milvus-restore",
        source_locator="s2b-restore://run/milvus-probe/milvus.db",
        content_path=parent_path,
        expected_sha256=parent_sha256,
        expected_byte_size=parent_path.stat().st_size,
    )

    parent = landing.register_artifact(registration)
    assert landing.register_artifact(registration) == parent
    content = (
        b'{"collection":"company_profiles","primary_key":"COMP-1",'
        b'"payload":{"name":"One"}}\n'
    )
    receipt = landing.ingest(
        module.IngestEvidenceRequest(
            run_id="derived-milvus-export",
            source_batch_id="derived-milvus-export",
            source_kind="milvus_verified_copy_records",
            source_locator="s2b-derived://run/milvus/company_profiles.jsonl",
            content=content,
            observed_at=NOW,
            expected_content_sha256=hashlib.sha256(content).hexdigest(),
            parser=module.ParserReference(
                parser_name="milvus_copy_records",
                parser_version="v1",
                schema_version="milvus-copy-record-v1",
            ),
            parent_artifact_id=parent.artifact_id,
            parent_content_sha256=parent.content_sha256,
        )
    )

    assert receipt.parent_artifact_id == parent.artifact_id
    assert receipt.parent_content_sha256 == parent.content_sha256
    assert landing.stream(receipt.source_batch_id)[0].payload["primary_key"] == (
        "COMP-1"
    )


@pytest.mark.parametrize("mismatch", ["hash", "size"])
def test_registration_mismatch_fails_before_artifact_becomes_a_valid_parent(
    tmp_path: Path,
    mismatch: str,
) -> None:
    module = _module()
    landing = module.create_ephemeral_evidence_landing()
    content_path = tmp_path / "copy.bin"
    content_path.write_bytes(b"exact-copy")
    digest = hashlib.sha256(content_path.read_bytes()).hexdigest()
    registration = _registration(
        module,
        run_id=f"register-mismatch-{mismatch}",
        source_locator=f"s2b-restore://run/mismatch-{mismatch}.bin",
        content_path=content_path,
        expected_sha256="0" * 64 if mismatch == "hash" else digest,
        expected_byte_size=(content_path.stat().st_size + 1)
        if mismatch == "size"
        else content_path.stat().st_size,
    )

    with pytest.raises(module.EvidenceIntegrityError, match=mismatch):
        landing.register_artifact(registration)

    child = b'{"source_id":"must-not-link"}\n'
    with pytest.raises(module.EvidenceIntegrityError, match="parent"):
        landing.ingest(
            module.IngestEvidenceRequest(
                run_id=f"child-after-{mismatch}",
                source_batch_id=f"child-after-{mismatch}",
                source_kind="verified_copy",
                source_locator=f"s2b-derived://run/after-{mismatch}.jsonl",
                content=child,
                observed_at=NOW,
                parser=module.ParserReference(
                    parser_name="historical_jsonl",
                    parser_version="v1",
                    schema_version="historical-record-v1",
                ),
                parent_artifact_id="artifact-not-registered",
                parent_content_sha256=digest,
            )
        )
