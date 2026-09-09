from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pytest


HERE = Path(__file__).resolve().parent
S2C = HERE.parent
TARGET = HERE / "apply_review_export_v2.py"
VALIDATOR_TEST_SUPPORT = HERE / "test_validate_review_export_v2.py"
EVALUATOR = S2C / "claim_level_oracle_evaluation.py"
PREDECESSOR = S2C / "claim-level-corpus-manifest-v1.json"
WORKLOAD = HERE / "human-review-workload-v2.json"
OUTPUT_NAMES = {
    "claim-level-corpus-v2.jsonl",
    "case-accounting-v2.jsonl",
    "source-snapshots-v2.jsonl",
    "human-review-bindings-v2.jsonl",
    "exclusion-review-bindings-v2.jsonl",
    "judge-calibration-v2.json",
    "claim-level-corpus-manifest-v2.json",
}


def _module() -> Any:
    assert TARGET.exists(), "reviewed-v2 application target is missing"
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_apply_review_export_v2", TARGET
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator_test_support() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_validator_test_support_for_application",
        VALIDATOR_TEST_SUPPORT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evaluator_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_oracle_evaluator_for_review_application",
        EVALUATOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@dataclass(frozen=True, slots=True)
class _Counts:
    contract_reviews: int = 29
    exclusion_reviews: int = 23
    calibration_probes: int = 60
    human_actions: int = 112


@dataclass(frozen=True, slots=True)
class _Validated:
    schema_version: str
    export_id: str
    round_id: str
    mode: str
    evidence_class: str
    acceptance_eligible: bool
    task_2_8_eligible: bool
    policy_id: str
    workload_counts: _Counts
    artifact_identity: Mapping[str, Any]
    canonical_export_bytes: bytes
    raw_sha256: str
    content_sha256: str


def _event(
    *,
    sequence: int,
    task_id: str,
    task_kind: str,
    decision: str,
    reviewer_id: str,
    staff_id: str,
) -> dict[str, Any]:
    canonical_payload = {
        "action": "decision",
        "decision": decision,
        "display_name": "Reviewer Li",
        "expected_revision": 0,
        "rationale": "reviewed against the supplied contract and evidence",
        "reviewer_id": reviewer_id,
        "staff_id": staff_id,
        "task_id": task_id,
        "task_kind": task_kind,
    }
    payload_sha256 = _canonical_sha256(canonical_payload)
    event_id = f"event:test-{sequence:03d}"
    return {
        "canonical_payload": canonical_payload,
        "event_id": event_id,
        "idempotency_sha256": hashlib.sha256(
            f"idempotency-{sequence}".encode()
        ).hexdigest(),
        "payload_sha256": payload_sha256,
        "record_sha256": _canonical_sha256(
            {
                "event_id": event_id,
                "payload_sha256": payload_sha256,
                "revision": 1,
                "supersedes_event_id": None,
            }
        ),
        "revision": 1,
        "submitted_at": "2026-07-24T12:00:00Z",
        "supersedes_event_id": None,
        "task_id": task_id,
        "task_kind": task_kind,
        "decision": decision,
        "rationale": canonical_payload["rationale"],
    }


def _validated_export() -> _Validated:
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    manifest = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    reviewer_id = "human:r-1042"
    staff_id = "r-1042"
    task_rows: list[tuple[str, str, str]] = []
    task_rows.extend(
        (f"contract:{row['case_id']}", "contract", "approved")
        for row in workload["contract_reviews"]
    )
    task_rows.extend(
        (f"exclusion:{row['case_id']}", "exclusion", "accept_exclusion")
        for row in workload["exclusion_reviews"]
    )
    task_rows.extend(
        (
            f"calibration:{row['sample_id']}",
            "calibration",
            "supported" if index < 30 else "unsupported",
        )
        for index, row in enumerate(workload["calibration_probes"])
    )
    events = [
        _event(
            sequence=index,
            task_id=task_id,
            task_kind=kind,
            decision=decision,
            reviewer_id=reviewer_id,
            staff_id=staff_id,
        )
        for index, (task_id, kind, decision) in enumerate(task_rows, start=1)
    ]

    def decision_projection(kind: str) -> list[dict[str, Any]]:
        return [
            {
                "decision": event["decision"],
                "event_id": event["event_id"],
                "payload_sha256": event["payload_sha256"],
                "revision": event["revision"],
                "task_id": event["task_id"],
            }
            for event in events
            if event["task_kind"] == kind
        ]

    s2c_paths = {
        "s2c_manifest_raw_sha256": PREDECESSOR,
        "s2c_corpus_raw_sha256": S2C / "claim-level-corpus-v1.jsonl",
        "s2c_accounting_raw_sha256": S2C / "case-accounting-v1.jsonl",
        "s2c_snapshots_raw_sha256": S2C / "source-snapshots-v1.jsonl",
    }
    artifact_identity: dict[str, Any] = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in s2c_paths.items()
    }
    artifact_identity.update(
        {
            "packet_raw_sha256": workload["packet_identity"]["raw_sha256"],
            "packet_content_sha256": workload["packet_identity"]["content_sha256"],
            "workload_raw_sha256": hashlib.sha256(WORKLOAD.read_bytes()).hexdigest(),
            "workload_content_sha256": workload["content_sha256"],
            "policy_raw_sha256": workload["policy_identity"]["raw_sha256"],
            "policy_content_sha256": workload["policy_identity"]["content_sha256"],
            "bank_raw_sha256": workload["bank_identity"]["raw_sha256"],
            "bank_content_sha256": workload["bank_identity"]["content_sha256"],
            "provenance_raw_sha256": workload["provenance_identity"]["raw_sha256"],
            "provenance_content_sha256": workload["provenance_identity"][
                "content_sha256"
            ],
            "s2c_manifest_content_sha256": manifest["content_sha256"],
            "source_sha256s": {"fixture:source": "c" * 64},
        }
    )
    export: dict[str, Any] = {
        "schema_version": "canonical-v2-human-review-export-v2",
        "export_id": "export:accepted-test",
        "mode": "acceptance_candidate",
        "acceptance_eligible": True,
        "evidence_class": "real_human_round",
        "task_2_8_eligible": True,
        "created_at": "2026-07-24T13:00:00Z",
        "artifact_identity": artifact_identity,
        "round": {
            "round_id": "round:accepted-test",
            "reviewer_id": reviewer_id,
            "staff_id": staff_id,
            "lifecycle": "locked",
        },
        "accounting": {"counts": workload["counts"], "missing": [], "blocking": []},
        "decision_events": events,
        "contract_decisions": decision_projection("contract"),
        "exclusion_decisions": decision_projection("exclusion"),
        "calibration_labels": decision_projection("calibration"),
        "judge": {
            "visibility": "sealed",
            "authorizations": [
                {
                    "schema_version": "judge-authorization-v2",
                    "model_id": "approved-judge-v2",
                    "policy_id": "evidence-bounded-judge-v1",
                }
            ],
            "attempts": [
                {
                    "run_id": "judge-run:test",
                    "state": "completed",
                    "idempotency_sha256": "b" * 64,
                }
            ],
            "recoveries": [],
            "completed_run": {"run_id": "judge-run:test", "state": "completed"},
            "responses": [{"task_id": row[0], "response_sha256": "a" * 64} for row in task_rows[52:]],
            "summary": {
                "agreement": 0.85,
                "critical_false_accepts": 0,
                "passed": True,
                "valid_pairs": 60,
            },
        },
        "gates": {
            "acceptance_ready": True,
            "calibration_labels_valid": True,
            "missing_task_ids": [],
            "blocking_task_ids": [],
            "acceptance_blockers": [],
        },
    }
    export["content_sha256"] = _canonical_sha256(export)
    canonical = _canonical_bytes(export)
    return _Validated(
        schema_version="canonical-v2-validated-review-export-v2",
        export_id=export["export_id"],
        round_id=export["round"]["round_id"],
        mode=export["mode"],
        evidence_class=export["evidence_class"],
        acceptance_eligible=True,
        task_2_8_eligible=True,
        policy_id="single-human-global-stratified-v2",
        workload_counts=_Counts(),
        artifact_identity=MappingProxyType(
            {
                **artifact_identity,
                "source_sha256s": MappingProxyType(
                    artifact_identity["source_sha256s"]
                ),
            }
        ),
        canonical_export_bytes=canonical,
        raw_sha256=hashlib.sha256(canonical).hexdigest(),
        content_sha256=export["content_sha256"],
    )


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _real_application_fixture(
    root: Path,
) -> tuple[Any, Any, dict[str, Any], dict[str, Path]]:
    support = _validator_test_support()
    fixture = support.ArtifactFixture(root)
    export = support._acceptance_export(fixture)
    support._write_export(fixture.export_path, export)
    predecessor = (
        fixture.source_root
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/claim-level-corpus-manifest-v1.json"
    )
    return support, fixture, export, {
        "export_path": fixture.export_path,
        "packet_path": fixture.packet_path,
        "workload_path": fixture.workload_path,
        "source_root": fixture.source_root,
        "predecessor_manifest_path": predecessor,
    }


def test_application_rejects_duck_typed_validated_receipt(tmp_path: Path) -> None:
    module = _module()
    destination = tmp_path / "forged-receipt"

    with pytest.raises(TypeError):
        module.apply_review_export_v2(
            _validated_export(),
            predecessor_manifest_path=PREDECESSOR,
            output_dir=destination,
        )

    assert not destination.exists()


def test_application_derives_deterministic_reviewed_v2_without_mutating_v1(
    tmp_path: Path,
) -> None:
    module = _module()
    _, _, export, inputs = _real_application_fixture(tmp_path / "validator")
    predecessor_manifest = inputs["predecessor_manifest_path"]
    source_s2c = predecessor_manifest.parent
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            predecessor_manifest,
            source_s2c / "claim-level-corpus-v1.jsonl",
            source_s2c / "case-accounting-v1.jsonl",
            source_s2c / "source-snapshots-v1.jsonl",
        )
    }
    first = tmp_path / "first"
    second = tmp_path / "second"

    receipt = module.apply_review_export_v2(
        **inputs,
        output_dir=first,
    )
    module.apply_review_export_v2(
        **inputs,
        output_dir=second,
    )

    assert {path.name for path in first.iterdir()} == OUTPUT_NAMES
    assert _tree_bytes(first) == _tree_bytes(second)
    assert receipt.manifest_path == first / "claim-level-corpus-manifest-v2.json"
    assert receipt.contract_review_count == 29
    assert receipt.exclusion_review_count == 23
    assert receipt.calibration_probe_count == 60
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            predecessor_manifest,
            source_s2c / "claim-level-corpus-v1.jsonl",
            source_s2c / "case-accounting-v1.jsonl",
            source_s2c / "source-snapshots-v1.jsonl",
        )
    }

    v1_contracts = {
        row["case_id"]: row
        for row in _jsonl(source_s2c / "claim-level-corpus-v1.jsonl")
    }
    v2_contracts = _jsonl(first / "claim-level-corpus-v2.jsonl")
    assert sum(row["review_state"] == "human_reviewed" for row in v2_contracts) == 29
    assert sum(row["acceptance_eligible"] is True for row in v2_contracts) == 29
    assert sum(row["review_state"] == "blocked_missing_evidence" for row in v2_contracts) == 23
    assert sum(row["acceptance_eligible"] is False for row in v2_contracts) == 23
    for derived in v2_contracts:
        original = v1_contracts[derived["case_id"]]
        ignored = {"acceptance_eligible", "content_sha256", "corpus_id", "review_state"}
        assert {key: value for key, value in derived.items() if key not in ignored} == {
            key: value for key, value in original.items() if key not in ignored
        }

    human_bindings = _jsonl(first / "human-review-bindings-v2.jsonl")
    exclusion_bindings = _jsonl(first / "exclusion-review-bindings-v2.jsonl")
    assert len(human_bindings) == 29
    assert len(exclusion_bindings) == 23
    assert all(row["decision"] == "approved" for row in human_bindings)
    assert all(row["decision"] == "accept_exclusion" for row in exclusion_bindings)
    assert all(row["reviewer_id"] == "human:r-1042" for row in human_bindings + exclusion_bindings)
    assert all(
        row["predecessor_contract_content_sha256"]
        == v1_contracts[row["case_id"]]["content_sha256"]
        for row in human_bindings + exclusion_bindings
    )

    manifest = json.loads(
        (first / "claim-level-corpus-manifest-v2.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "canonical-v2-s2c-corpus-manifest-v2"
    assert manifest["approval_state"] == "human_reviewed"
    assert manifest["acceptance_eligible_count"] == 29
    assert manifest["review_state_counts"] == {
        "blocked_missing_evidence": 23,
        "human_reviewed": 29,
        "pending_user_review": 0,
    }
    assert manifest["predecessor"]["manifest_content_sha256"] == json.loads(
        predecessor_manifest.read_text(encoding="utf-8")
    )["content_sha256"]
    assert manifest["review_application"]["export_id"] == export["export_id"]
    assert manifest["review_application"]["policy_id"] == "single-human-global-stratified-v2"
    assert manifest["review_application"]["counts"] == {
        "calibration_probes": 60,
        "contract_reviews": 29,
        "exclusion_reviews": 23,
        "human_actions": 112,
    }
    assert manifest["content_sha256"] == _canonical_sha256(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )


def test_real_validator_result_feeds_application_without_schema_translation(
    tmp_path: Path,
) -> None:
    module = _module()
    support, fixture, _, inputs = _real_application_fixture(tmp_path / "validator")
    validator = support._module()
    validated = support._validate(validator, fixture)
    destination = tmp_path / "reviewed-v2"

    receipt = module.apply_review_export_v2(
        **inputs,
        output_dir=destination,
    )

    assert receipt.manifest_path.is_file()
    manifest = json.loads(receipt.manifest_path.read_text(encoding="utf-8"))
    assert manifest["review_application"]["export_id"] == validated.export_id
    assert manifest["review_application"]["export_content_sha256"] == (
        validated.content_sha256
    )
    assert manifest["acceptance_eligible_count"] == 29

    admitted = _evaluator_module()._admit_artifacts(
        receipt.manifest_path,
        receipt.manifest_content_sha256,
    )
    assert admitted[-1]["review"]["export_id"] == validated.export_id
    assert admitted[-1]["review"]["counts"] == {
        "calibration_probes": 60,
        "contract_reviews": 29,
        "exclusion_reviews": 23,
        "human_actions": 112,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "review_evidence"),
        ("evidence_class", "implementation_test"),
        ("acceptance_eligible", False),
        ("task_2_8_eligible", False),
    ],
)
def test_application_rejects_nonaccepting_validated_result_before_output(
    tmp_path: Path, field: str, value: object
) -> None:
    module = _module()
    support, _, export, inputs = _real_application_fixture(tmp_path / "validator")
    export[field] = value
    support._write_export(inputs["export_path"], export)
    destination = tmp_path / "blocked"

    with pytest.raises(module.ReviewApplicationError, match="validation"):
        module.apply_review_export_v2(
            **inputs,
            output_dir=destination,
        )

    assert not destination.exists()


def test_application_rejects_export_or_predecessor_drift_before_output(
    tmp_path: Path,
) -> None:
    module = _module()
    support, _, export, inputs = _real_application_fixture(tmp_path / "validator")
    inputs["export_path"].write_bytes(inputs["export_path"].read_bytes() + b" ")
    export_destination = tmp_path / "bad-export"
    with pytest.raises(module.ReviewApplicationError, match="validation"):
        module.apply_review_export_v2(
            **inputs,
            output_dir=export_destination,
        )
    assert not export_destination.exists()
    support._write_export(inputs["export_path"], export)

    copied = tmp_path / "v1"
    copied.mkdir()
    for name in (
        "claim-level-corpus-manifest-v1.json",
        "claim-level-corpus-v1.jsonl",
        "case-accounting-v1.jsonl",
        "source-snapshots-v1.jsonl",
    ):
        (copied / name).write_bytes(
            (inputs["predecessor_manifest_path"].parent / name).read_bytes()
        )
    (copied / "claim-level-corpus-v1.jsonl").write_bytes(
        (copied / "claim-level-corpus-v1.jsonl").read_bytes() + b"\n"
    )
    predecessor_destination = tmp_path / "bad-predecessor"
    with pytest.raises(module.ReviewApplicationError, match="predecessor|hash|identity"):
        module.apply_review_export_v2(
            **{
                **inputs,
                "predecessor_manifest_path": copied
                / "claim-level-corpus-manifest-v1.json",
            },
            output_dir=predecessor_destination,
        )
    assert not predecessor_destination.exists()


def test_application_refuses_to_clobber_an_existing_destination(tmp_path: Path) -> None:
    module = _module()
    _, _, _, inputs = _real_application_fixture(tmp_path / "validator")
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(module.ReviewApplicationError, match="destination"):
        module.apply_review_export_v2(
            **inputs,
            output_dir=destination,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"
