"""Focused owner for verified restore-member EvidenceLanding ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_ingest_uses_one_verified_restore_member_after_factory_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import run_canonical_v2_evidence_ingest as cli
    from src.data_agents.canonical_v2.evidence_landing import (
        LandingReceipt,
        LandingStatus,
    )

    evidence_root = tmp_path / "evidence"
    backup_root = tmp_path / "backup"
    restore_root = tmp_path / "restore"
    original = tmp_path / "original.jsonl"
    content = b'{"record":"accepted"}\n'
    original.write_bytes(content)
    object_path = backup_root / "objects/sha256/member"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(content)
    restored = restore_root / "workspace/data/member.jsonl"
    restored.parent.mkdir(parents=True)
    restored.write_bytes(content)
    manifest_path = backup_root / "manifests/member.jsonl"
    manifest_path.parent.mkdir(parents=True)
    member_hash = hashlib.sha256(content).hexdigest()
    member = {
        "namespace": "workspace",
        "relative_path": "data/member.jsonl",
        "source_path": str(original),
        "source_bytes": len(content),
        "source_sha256": member_hash,
        "backup_bytes": len(content),
        "backup_sha256": member_hash,
        "object_path": "objects/sha256/member",
        "copy_independent": True,
    }
    manifest_path.write_text(json.dumps(member) + "\n", encoding="utf-8")
    backup = {
        "run_id": "accepted-s2b",
        "backup_root": str(backup_root),
        "restore_root": str(restore_root),
        "sources": [
            {
                "source_id": "source:one",
                "copy_independent": True,
                "hash_verified": True,
                "backup_member_manifest_path": "manifests/member.jsonl",
                "backup_member_manifest_sha256": _sha256(manifest_path),
            }
        ],
    }
    backup_path = evidence_root / "s2b/backup-manifest.json"
    _write_json(backup_path, backup)
    restore = {
        "run_id": "accepted-s2b",
        "backup_root": str(backup_root),
        "restore_root": str(restore_root),
        "backup_manifest_sha256": _sha256(backup_path),
        "sources": [
            {
                "source_id": "source:one",
                "status": "passed",
                "hash_verified": True,
                "copy_independent": True,
            }
        ],
    }
    restore_path = evidence_root / "s2b/restore-verification.json"
    _write_json(restore_path, restore)
    acceptance = {
        "state": "accepted",
        "backup_manifest_sha256": _sha256(backup_path),
        "restore_verification_sha256": _sha256(restore_path),
    }
    acceptance_path = evidence_root / "s2b/acceptance-record.json"
    _write_json(acceptance_path, acceptance)

    request_path = tmp_path / "request.json"
    _write_json(
        request_path,
        {
            "run_id": "landing:one",
            "source_batch_id": "batch:one",
            "source_kind": "restored_jsonl",
            "source_locator": (
                "s2b-restore://accepted-s2b/workspace/data/member.jsonl"
            ),
            "observed_at": datetime(2026, 7, 21, tzinfo=UTC).isoformat(),
            "expected_content_sha256": member_hash,
        },
    )

    events: list[str] = []
    captured: list[object] = []

    class Landing:
        def ingest(self, request: object) -> LandingReceipt:
            events.append("ingest")
            captured.append(request)
            return LandingReceipt(
                run_id="landing:one",
                source_batch_id="batch:one",
                artifact_id="artifact:one",
                content_sha256=member_hash,
                bytes_written=len(content),
                status=LandingStatus.accepted,
                parse_run_id="parse:one",
                record_count=1,
            )

    def factory(**kwargs: object) -> Landing:
        events.append("factory")
        assert kwargs["target_kind"] in {"disposable", "isolated-candidate"}
        return Landing()

    def gate(path: Path) -> SimpleNamespace:
        events.append("gate")
        assert path == evidence_root
        return SimpleNamespace(
            backup_manifest_sha256=_sha256(backup_path),
            restore_verification_sha256=_sha256(restore_path),
            acceptance_record_sha256=_sha256(acceptance_path),
        )

    real_read = cli._read_member_once

    def observed_read(path: Path) -> bytes:
        events.append("read")
        return real_read(path)

    monkeypatch.setattr(cli, "create_postgres_evidence_landing", factory)
    monkeypatch.setattr(cli, "require_accepted_backup_gate", gate)
    monkeypatch.setattr(cli, "_read_member_once", observed_read)

    receipt = cli.run_ingest(
        database_url="postgresql://explicit.invalid/candidate",
        expected_database="candidate",
        target_kind="disposable",
        backup_gate_root=evidence_root,
        request_json=request_path,
        source_id="source:one",
        member_namespace="workspace",
        member_relative_path="data/member.jsonl",
    )

    assert receipt.status is LandingStatus.accepted
    assert events == ["factory", "gate", "read", "ingest"]
    assert len(captured) == 1
    assert captured[0].content == content

    events.clear()
    replay = cli.run_ingest(
        database_url="postgresql://explicit.invalid/candidate",
        expected_database="candidate",
        target_kind="isolated-candidate",
        backup_gate_root=evidence_root,
        request_json=request_path,
        source_id="source:one",
        member_namespace="workspace",
        member_relative_path="data/member.jsonl",
    )
    assert replay == receipt
    assert events == ["factory", "gate", "read", "ingest"]

    missing_hash = tmp_path / "missing-hash.json"
    missing_hash_payload = json.loads(request_path.read_text())
    missing_hash_payload.pop("expected_content_sha256")
    _write_json(missing_hash, missing_hash_payload)
    events.clear()
    with pytest.raises(cli.EvidenceIngestContractError):
        cli.run_ingest(
            database_url="postgresql://explicit.invalid/candidate",
            expected_database="candidate",
            target_kind="disposable",
            backup_gate_root=evidence_root,
            request_json=missing_hash,
            source_id="source:one",
            member_namespace="workspace",
            member_relative_path="data/member.jsonl",
        )
    assert events == []

    stale_locator = tmp_path / "stale-locator.json"
    stale_payload = json.loads(request_path.read_text())
    stale_payload["source_locator"] = "s2b-restore://wrong/workspace/data/member.jsonl"
    _write_json(stale_locator, stale_payload)
    events.clear()
    with pytest.raises(cli.EvidenceIngestContractError):
        cli.run_ingest(
            database_url="postgresql://explicit.invalid/candidate",
            expected_database="candidate",
            target_kind="disposable",
            backup_gate_root=evidence_root,
            request_json=stale_locator,
            source_id="source:one",
            member_namespace="workspace",
            member_relative_path="data/member.jsonl",
        )
    assert events == ["factory", "gate"]

    events.clear()
    restored.unlink()
    restored.symlink_to(original)
    with pytest.raises(cli.EvidenceIngestContractError):
        cli.run_ingest(
            database_url="postgresql://explicit.invalid/candidate",
            expected_database="candidate",
            target_kind="disposable",
            backup_gate_root=evidence_root,
            request_json=request_path,
            source_id="source:one",
            member_namespace="workspace",
            member_relative_path="data/member.jsonl",
        )
    assert events == ["factory", "gate"]
    restored.unlink()
    restored.write_bytes(b'{"record":"rejected"}\n')
    events.clear()
    with pytest.raises(cli.EvidenceIngestContractError):
        cli.run_ingest(
            database_url="postgresql://explicit.invalid/candidate",
            expected_database="candidate",
            target_kind="disposable",
            backup_gate_root=evidence_root,
            request_json=request_path,
            source_id="source:one",
            member_namespace="workspace",
            member_relative_path="data/member.jsonl",
        )
    assert events == ["factory", "gate", "read"]
    restored.write_bytes(content)

    bad_request = tmp_path / "bad-request.json"
    payload = json.loads(request_path.read_text())
    payload["content"] = "caller-authored"
    _write_json(bad_request, payload)
    events.clear()
    with pytest.raises(cli.EvidenceIngestContractError):
        cli.run_ingest(
            database_url="postgresql://explicit.invalid/candidate",
            expected_database="candidate",
            target_kind="disposable",
            backup_gate_root=evidence_root,
            request_json=bad_request,
            source_id="source:one",
            member_namespace="workspace",
            member_relative_path="data/member.jsonl",
        )
    assert events == []
