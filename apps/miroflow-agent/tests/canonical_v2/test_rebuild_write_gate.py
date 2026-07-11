from __future__ import annotations

from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import runpy
import shutil
from typing import Any

from alembic import context as alembic_context
from alembic.config import Config
import pytest
import sqlalchemy


APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parents[1]
EVIDENCE_ROOT = (
    REPO_ROOT / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
)
ALEMBIC_ENV = APP_ROOT / "canonical_v2_alembic" / "env.py"
EXPECTED_DATABASE = "miroflow_canonical_v2_candidate_s3b"
EXPLICIT_URL = (
    "postgresql+psycopg://miroflow:local-test@isolated-lab:5432/"
    f"{EXPECTED_DATABASE}"
)


def _gate_module() -> Any:
    return importlib.import_module(
        "src.data_agents.canonical_v2.rebuild_write_gate"
    )


def _copy_gate_evidence(destination: Path) -> Path:
    shutil.copytree(EVIDENCE_ROOT / "s2", destination / "s2")
    shutil.copytree(EVIDENCE_ROOT / "s2b", destination / "s2b")
    return destination


def test_exact_accepted_s2b_evidence_returns_typed_admission_receipt() -> None:
    module = _gate_module()

    receipt = module.require_accepted_backup_gate(EVIDENCE_ROOT)

    assert isinstance(receipt, module.BackupGateReceipt)
    assert receipt.state == "accepted"
    assert receipt.source_count == 50
    assert (
        receipt.source_inventory_sha256
        == "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
    )
    assert (
        receipt.backup_manifest_sha256
        == "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
    )
    assert (
        receipt.restore_verification_sha256
        == "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
    )
    assert (
        receipt.acceptance_record_sha256
        == "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
    )


@pytest.mark.parametrize("case", ["missing", "tampered", "not_accepted"])
def test_missing_changed_or_unaccepted_gate_evidence_fails_closed(
    tmp_path: Path,
    case: str,
) -> None:
    module = _gate_module()
    evidence_root = _copy_gate_evidence(tmp_path / "evidence")
    acceptance_path = evidence_root / "s2b" / "acceptance-record.json"

    if case == "missing":
        acceptance_path.unlink()
    else:
        acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
        if case == "tampered":
            acceptance["statement"] = "changed after acceptance"
        else:
            acceptance["state"] = "candidate"
        acceptance_path.write_text(
            json.dumps(acceptance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(module.RebuildWriteGateError, match="missing|hash|accepted"):
        module.require_accepted_backup_gate(evidence_root)


def test_rejected_backup_gate_stops_alembic_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _gate_module()
    config = Config()
    config.set_main_option("sqlalchemy.url", EXPLICIT_URL)
    config.set_main_option("miroflow.expected_database", EXPECTED_DATABASE)
    config.set_main_option("miroflow.target_kind", "isolated-candidate")
    config.set_main_option("miroflow.backup_gate_root", "/missing/accepted-gate")
    engine_calls: list[dict[str, Any]] = []

    def _reject_gate(_evidence_root: Path) -> Any:
        raise module.RebuildWriteGateError("accepted backup evidence is missing")

    def _record_engine(*args: Any, **kwargs: Any) -> None:
        engine_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("engine creation must not occur after gate rejection")

    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "DATABASE_URL",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "require_accepted_backup_gate", _reject_gate)
    monkeypatch.setattr(alembic_context, "config", config, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(alembic_context, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)
    monkeypatch.setattr(alembic_context, "run_migrations", lambda: None)
    monkeypatch.setattr(sqlalchemy, "engine_from_config", _record_engine)

    with pytest.raises(module.RebuildWriteGateError, match="accepted backup"):
        runpy.run_path(str(ALEMBIC_ENV), run_name="__canonical_v2_gate_order__")

    assert engine_calls == []
