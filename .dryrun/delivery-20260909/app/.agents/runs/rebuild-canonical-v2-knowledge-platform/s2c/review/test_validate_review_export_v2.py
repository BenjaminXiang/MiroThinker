from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType
from typing import Any, Callable

import pytest


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
TARGET_PATH = HERE / "validate_review_export_v2.py"
PACKET_NAME = "human-review-packet-v1.json"
WORKLOAD_NAME = "human-review-workload-v2.json"
POLICY_NAME = "calibration-policy-v2.json"
BANK_NAME = "calibration-observation-bank-v2.jsonl"
PROVENANCE_NAME = "calibration-observation-bank-v2-provenance.json"
S2C_FILES = (
    "claim-level-corpus-v1.jsonl",
    "case-accounting-v1.jsonl",
    "source-snapshots-v1.jsonl",
    "claim-level-corpus-manifest-v1.json",
)
RENDERER_FILES = (
    "review.html",
    "review.css",
    "review.js",
    "review_mutation_coordinator.js",
)
COUNTS = {
    "contract_reviews": 29,
    "exclusion_reviews": 23,
    "calibration_probes": 60,
    "human_actions": 112,
}
STRATA = {
    "claim_evidence": 20,
    "context_relationship": 10,
    "identity_entity": 10,
    "insufficiency_assessment": 10,
    "safety_web": 10,
}


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_validate_review_export_v2", TARGET_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert tuple(module.__all__) == (
        "ReviewExportValidationError",
        "ValidatedReviewCounts",
        "ValidatedReviewExportV2",
        "validate_review_export_v2",
    )
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


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stimulus(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "canonical-v2-human-calibration-stimulus-v1",
        "sample_id": probe["sample_id"],
        "as_of": probe["as_of"],
        "requirement": {
            key: value
            for key, value in probe["requirement"].items()
            if key != "fixture_locator"
        },
        "candidate_observation": probe["candidate_observation"],
        "evidence_snapshots": probe["evidence_snapshots"],
    }


class ArtifactFixture:
    def __init__(self, root: Path) -> None:
        self.source_root = root / "source-root"
        self.review_dir = self.source_root / HERE.relative_to(REPO_ROOT)
        self.review_dir.mkdir(parents=True)
        for name in (
            PACKET_NAME,
            WORKLOAD_NAME,
            POLICY_NAME,
            BANK_NAME,
            PROVENANCE_NAME,
        ):
            shutil.copyfile(HERE / name, self.review_dir / name)

        workload = _json(self.review_dir / WORKLOAD_NAME)
        relatives = {
            Path(probe["source_identity"]["path"])
            for probe in workload["calibration_probes"]
        }
        relatives.update(
            Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c") / name
            for name in S2C_FILES
        )
        relatives.update(
            Path("apps/admin-console/backend/static") / name for name in RENDERER_FILES
        )
        for relative in relatives:
            destination = self.source_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, destination)

        self.packet_path = self.review_dir / PACKET_NAME
        self.workload_path = self.review_dir / WORKLOAD_NAME
        self.export_path = root / "review-export.json"


@pytest.fixture
def artifacts(tmp_path: Path) -> ArtifactFixture:
    return ArtifactFixture(tmp_path)


def _artifact_identity(fixture: ArtifactFixture) -> dict[str, Any]:
    packet = _json(fixture.packet_path)
    workload = _json(fixture.workload_path)
    policy_path = fixture.review_dir / POLICY_NAME
    bank_path = fixture.review_dir / BANK_NAME
    provenance_path = fixture.review_dir / PROVENANCE_NAME
    policy = _json(policy_path)
    bank = _jsonl(bank_path)
    provenance = _json(provenance_path)
    s2c_root = (
        fixture.source_root / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c"
    )
    renderer_root = fixture.source_root / "apps/admin-console/backend/static"
    renderer_hashes = {
        name: _raw_sha256(renderer_root / name) for name in RENDERER_FILES
    }
    source_sha256s = {
        probe["source_identity"]["path"]: probe["source_identity"]["source_sha256"]
        for probe in workload["calibration_probes"]
    }
    return {
        "packet_raw_sha256": _raw_sha256(fixture.packet_path),
        "packet_content_sha256": packet["content_sha256"],
        "workload_raw_sha256": _raw_sha256(fixture.workload_path),
        "workload_content_sha256": workload["content_sha256"],
        "policy_raw_sha256": _raw_sha256(policy_path),
        "policy_content_sha256": _canonical_sha256(policy),
        "bank_raw_sha256": _raw_sha256(bank_path),
        "bank_content_sha256": _canonical_sha256(bank),
        "provenance_raw_sha256": _raw_sha256(provenance_path),
        "provenance_content_sha256": provenance["content_sha256"],
        "s2c_manifest_raw_sha256": _raw_sha256(
            s2c_root / "claim-level-corpus-manifest-v1.json"
        ),
        "s2c_manifest_content_sha256": packet["source_identity"][
            "manifest_content_sha256"
        ],
        "s2c_corpus_raw_sha256": _raw_sha256(s2c_root / "claim-level-corpus-v1.jsonl"),
        "s2c_accounting_raw_sha256": _raw_sha256(s2c_root / "case-accounting-v1.jsonl"),
        "s2c_snapshots_raw_sha256": _raw_sha256(s2c_root / "source-snapshots-v1.jsonl"),
        "calibration_stimulus_set_sha256": _canonical_sha256(
            {
                "schema_version": "canonical-v2-human-calibration-stimulus-set-v1",
                "stimuli": [
                    _stimulus(probe) for probe in workload["calibration_probes"]
                ],
            }
        ),
        "renderer_schema_version": "canonical-v2-human-review-renderer-v1",
        "review_html_raw_sha256": renderer_hashes["review.html"],
        "review_css_raw_sha256": renderer_hashes["review.css"],
        "review_js_raw_sha256": renderer_hashes["review.js"],
        "review_mutation_coordinator_js_raw_sha256": renderer_hashes[
            "review_mutation_coordinator.js"
        ],
        "renderer_content_sha256": _canonical_sha256(
            {
                "schema_version": "canonical-v2-human-review-renderer-v1",
                "assets": renderer_hashes,
            }
        ),
        "source_sha256s": dict(sorted(source_sha256s.items())),
    }


def _coverage(
    rows: list[dict[str, Any]], field: str, *, submitted: bool
) -> dict[str, dict[str, int]]:
    counts = Counter(str(row[field]) for row in rows)
    return {
        name: {
            "total": total,
            "submitted": total if submitted else 0,
            "accepting": total if submitted else 0,
            "blocking": 0,
            "missing": 0 if submitted else total,
        }
        for name, total in sorted(counts.items())
    }


def _decision_event(
    *, task_id: str, task_kind: str, decision: str, position: int
) -> dict[str, Any]:
    rationale = (
        "Reviewed evidence remains unavailable." if task_kind == "exclusion" else None
    )
    payload = {
        "action": "decision",
        "decision": decision,
        "display_name": "Reviewer Li",
        "expected_revision": 0,
        "rationale": rationale,
        "reviewer_id": "human:r-1042",
        "staff_id": "r-1042",
        "task_id": task_id,
        "task_kind": task_kind,
    }
    event_id = f"event:{position:03d}"
    payload_sha256 = _canonical_sha256(payload)
    supersedes_event_id = None
    return {
        "event_id": event_id,
        "task_id": task_id,
        "task_kind": task_kind,
        "revision": 1,
        "supersedes_event_id": supersedes_event_id,
        "decision": decision,
        "rationale": rationale,
        "canonical_payload": payload,
        "payload_sha256": payload_sha256,
        "idempotency_sha256": hashlib.sha256(
            f"decision-{position:03d}".encode()
        ).hexdigest(),
        "record_sha256": _canonical_sha256(
            {
                "event_id": event_id,
                "payload_sha256": payload_sha256,
                "revision": 1,
                "supersedes_event_id": supersedes_event_id,
            }
        ),
        "submitted_at": "2026-07-24T12:00:00Z",
    }


def _acceptance_export(fixture: ArtifactFixture) -> dict[str, Any]:
    workload = _json(fixture.workload_path)
    round_id = "round:review-1"
    probes = workload["calibration_probes"]
    unsupported = {
        probe["sample_id"]
        for probe in [item for item in probes if item["critical_probe"]][:12]
    }
    task_specs: list[tuple[str, str, str]] = [
        (f"contract:{row['case_id']}", "contract", "approved")
        for row in workload["contract_reviews"]
    ]
    task_specs.extend(
        (f"exclusion:{row['case_id']}", "exclusion", "accept_exclusion")
        for row in workload["exclusion_reviews"]
    )
    task_specs.extend(
        (
            f"calibration:{row['sample_id']}",
            "calibration",
            "unsupported" if row["sample_id"] in unsupported else "supported",
        )
        for row in probes
    )
    events = [
        _decision_event(
            task_id=task_id,
            task_kind=kind,
            decision=decision,
            position=position,
        )
        for position, (task_id, kind, decision) in enumerate(task_specs, start=1)
    ]
    current = {event["task_id"]: event for event in events}
    calibration_events = [
        current[f"calibration:{probe['sample_id']}"] for probe in probes
    ]
    human_snapshot_sha256 = _canonical_sha256(
        [
            {
                "decision": event["decision"],
                "event_id": event["event_id"],
                "payload_sha256": event["payload_sha256"],
                "revision": event["revision"],
                "task_id": event["task_id"],
            }
            for event in calibration_events
        ]
    )
    authorization = {
        "schema_version": "judge-authorization-v2",
        "evidence_class": "real_human_round",
        "round_id": round_id,
        "authorizer_id": "human:owner-1",
        "provider_profile": "approved-review-profile",
        "model_id": "review-judge-v1",
        "calibration_policy_id": "single-human-global-stratified-v2",
        "judge_policy_id": "evidence-bounded-judge-v1",
        "workload_content_sha256": workload["content_sha256"],
        "authorized_at": "2026-07-24T12:00:00Z",
        "evidence_scope": "supplied_request_only",
    }
    authorization["content_sha256"] = _canonical_sha256(authorization)
    run = {
        "run_id": "judge-run:001",
        "round_id": round_id,
        "idempotency_sha256": hashlib.sha256(b"seal-review-1").hexdigest(),
        "command_sha256": _canonical_sha256(
            {
                "action": "seal_calibration",
                "expected_revision": 60,
                "round_id": round_id,
            }
        ),
        "human_snapshot_sha256": human_snapshot_sha256,
        "authorization_sha256": authorization["content_sha256"],
        "started_at": "2026-07-24T12:01:00Z",
        "state": "completed",
        "failure_code": None,
        "finished_at": "2026-07-24T12:02:00Z",
    }
    responses: list[dict[str, Any]] = []
    judgments: list[dict[str, Any]] = []
    confusion = {
        "human_supported_model_supported": 0,
        "human_supported_model_unsupported": 0,
        "human_unsupported_model_supported": 0,
        "human_unsupported_model_unsupported": 0,
    }
    for probe, event in zip(probes, calibration_events, strict=True):
        stimulus = _stimulus(probe)
        request_sha256 = _canonical_sha256(stimulus)
        response = {
            "schema_version": "canonical-v2-human-calibration-judge-decision-v2",
            "model_id": "review-judge-v1",
            "policy_id": "evidence-bounded-judge-v1",
            "request_sha256": request_sha256,
            "decision": event["decision"],
            "evidence_scope": "supplied_request_only",
            "used_external_memory": False,
        }
        response_sha256 = _canonical_sha256(response)
        task_id = event["task_id"]
        responses.append(
            {
                "task_id": task_id,
                "request_sha256": request_sha256,
                "response": response,
                "response_sha256": response_sha256,
                "judged_at": "2026-07-24T12:01:30Z",
            }
        )
        judgments.append(
            {
                "task_id": task_id,
                "sample_id": probe["sample_id"],
                "stratum": probe["stratum"],
                "critical_probe": probe["critical_probe"],
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
                "human_decision": event["decision"],
                "model_decision": event["decision"],
            }
        )
        confusion[f"human_{event['decision']}_model_{event['decision']}"] += 1

    human_unsupported = len(unsupported)
    human_supported = len(probes) - human_unsupported
    unsupported_critical = sum(
        probe["sample_id"] in unsupported and probe["critical_probe"]
        for probe in probes
    )
    summary = {
        "evidence_class": "real_human_round",
        "pair_count": 60,
        "stratum_counts": dict(
            sorted(Counter(probe["stratum"] for probe in probes).items())
        ),
        "human_supported": human_supported,
        "human_unsupported": human_unsupported,
        "agreement": 1.0,
        "confusion_matrix": confusion,
        "unsupported_critical_probes": unsupported_critical,
        "critical_false_accepts": 0,
        "gates": {
            "exact_pair_count": True,
            "exact_stratum_quotas": True,
            "minimum_agreement": True,
            "minimum_supported_labels": True,
            "minimum_unsupported_labels": True,
            "minimum_unsupported_critical_probes": True,
            "maximum_critical_false_accepts": True,
        },
        "passed": True,
        "model_id": "review-judge-v1",
        "calibration_policy_id": "single-human-global-stratified-v2",
        "judge_policy_id": "evidence-bounded-judge-v1",
        "authorization_sha256": authorization["content_sha256"],
        "human_snapshot_sha256": human_snapshot_sha256,
        "judgments": judgments,
    }

    def projection(kind: str) -> list[dict[str, Any]]:
        return [
            {
                "task_id": event["task_id"],
                "decision": event["decision"],
                "revision": event["revision"],
                "event_id": event["event_id"],
                "payload_sha256": event["payload_sha256"],
            }
            for event in sorted(events, key=lambda item: item["task_id"])
            if event["task_kind"] == kind
        ]

    result = {
        "schema_version": "canonical-v2-human-review-export-v2",
        "export_id": "export:review-1",
        "mode": "acceptance_candidate",
        "acceptance_eligible": True,
        "evidence_class": "real_human_round",
        "task_2_8_eligible": True,
        "created_at": "2026-07-24T12:03:00Z",
        "artifact_identity": _artifact_identity(fixture),
        "round": {
            "round_id": round_id,
            "reviewer_id": "human:r-1042",
            "staff_id": "r-1042",
            "lifecycle": "locked",
        },
        "accounting": {"counts": dict(COUNTS), "missing": [], "blocking": []},
        "decision_events": sorted(
            events,
            key=lambda item: (item["task_id"], item["revision"], item["event_id"]),
        ),
        "contract_decisions": projection("contract"),
        "exclusion_decisions": projection("exclusion"),
        "calibration_labels": projection("calibration"),
        "judge": {
            "visibility": "sealed",
            "authorizations": [authorization],
            "attempts": [run],
            "recoveries": [],
            "completed_run": run,
            "responses": sorted(responses, key=lambda item: item["task_id"]),
            "summary": summary,
        },
        "gates": {
            "missing_task_ids": [],
            "blocking_task_ids": [],
            "blocking_reasons": {},
            "family_coverage": _coverage(
                workload["contract_reviews"] + workload["exclusion_reviews"],
                "family",
                submitted=True,
            ),
            "stratum_coverage": _coverage(
                workload["calibration_probes"], "stratum", submitted=True
            ),
            "calibration_labels_valid": True,
            "calibration_ready_to_seal": False,
            "acceptance_ready": True,
            "acceptance_blockers": [],
        },
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _review_evidence_export(fixture: ArtifactFixture) -> dict[str, Any]:
    workload = _json(fixture.workload_path)
    task_ids = [
        *(f"contract:{row['case_id']}" for row in workload["contract_reviews"]),
        *(f"exclusion:{row['case_id']}" for row in workload["exclusion_reviews"]),
        *(f"calibration:{row['sample_id']}" for row in workload["calibration_probes"]),
    ]
    result = {
        "schema_version": "canonical-v2-human-review-export-v2",
        "export_id": "export:review-evidence-1",
        "mode": "review_evidence",
        "acceptance_eligible": False,
        "evidence_class": "real_human_round",
        "task_2_8_eligible": False,
        "created_at": "2026-07-24T12:03:00Z",
        "artifact_identity": _artifact_identity(fixture),
        "round": {
            "round_id": "round:review-1",
            "reviewer_id": "human:r-1042",
            "staff_id": "r-1042",
            "lifecycle": "in_progress",
        },
        "accounting": {"counts": dict(COUNTS), "missing": task_ids, "blocking": []},
        "decision_events": [],
        "contract_decisions": [],
        "exclusion_decisions": [],
        "calibration_labels": [],
        "judge": {
            "visibility": "hidden_until_sealed",
            "status": "hidden_until_sealed",
        },
        "gates": {
            "missing_task_ids": task_ids,
            "blocking_task_ids": [],
            "blocking_reasons": {},
            "family_coverage": _coverage(
                workload["contract_reviews"] + workload["exclusion_reviews"],
                "family",
                submitted=False,
            ),
            "stratum_coverage": _coverage(
                workload["calibration_probes"], "stratum", submitted=False
            ),
            "calibration_labels_valid": False,
            "calibration_ready_to_seal": False,
            "acceptance_ready": False,
            "acceptance_blockers": [
                "human_decisions_missing",
                "calibration_not_sealed",
            ],
        },
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _write_export(path: Path, value: dict[str, Any], *, rehash: bool = True) -> None:
    if rehash:
        value.pop("content_sha256", None)
        value["content_sha256"] = _canonical_sha256(value)
    path.write_bytes(_canonical_bytes(value))


def _rebind_authorization(export: dict[str, Any]) -> None:
    judge = export["judge"]
    authorization = judge["authorizations"][0]
    authorization.pop("content_sha256", None)
    authorization_sha256 = _canonical_sha256(authorization)
    authorization["content_sha256"] = authorization_sha256
    for attempt in judge["attempts"]:
        attempt["authorization_sha256"] = authorization_sha256
    judge["completed_run"]["authorization_sha256"] = authorization_sha256
    for recovery in judge["recoveries"]:
        recovery["authorization_sha256"] = authorization_sha256
    judge["summary"]["authorization_sha256"] = authorization_sha256


def _validate(module: ModuleType, fixture: ArtifactFixture) -> Any:
    return module.validate_review_export_v2(
        export_path=fixture.export_path,
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
    )


def test_acceptance_candidate_is_independently_validated_and_frozen(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _acceptance_export(artifacts)
    _write_export(artifacts.export_path, export)

    validated = _validate(module, artifacts)

    assert validated.schema_version == "canonical-v2-validated-review-export-v2"
    assert validated.export_id == "export:review-1"
    assert validated.round_id == "round:review-1"
    assert validated.mode == "acceptance_candidate"
    assert validated.evidence_class == "real_human_round"
    assert validated.acceptance_eligible is True
    assert validated.task_2_8_eligible is True
    assert validated.policy_id == "single-human-global-stratified-v2"
    assert validated.workload_counts.contract_reviews == 29
    assert validated.workload_counts.exclusion_reviews == 23
    assert validated.workload_counts.calibration_probes == 60
    assert validated.workload_counts.human_actions == 112
    assert validated.canonical_export_bytes == artifacts.export_path.read_bytes()
    assert (
        validated.raw_sha256
        == hashlib.sha256(artifacts.export_path.read_bytes()).hexdigest()
    )
    assert validated.content_sha256 == export["content_sha256"]
    assert validated.artifact_identity["workload_content_sha256"] == (
        "89b027058e8f66864edfd6c3a2ccc0be3f006a51432e17eaa0a6e504d7baa456"
    )
    with pytest.raises(TypeError):
        validated.artifact_identity["workload_content_sha256"] = "0" * 64


def test_preseal_review_evidence_is_valid_but_permanently_nonaccepting(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _review_evidence_export(artifacts)
    _write_export(artifacts.export_path, export)

    validated = _validate(module, artifacts)

    assert validated.mode == "review_evidence"
    assert validated.acceptance_eligible is False
    assert validated.task_2_8_eligible is False


def test_acceptance_candidate_mode_cannot_represent_a_blocked_round(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _review_evidence_export(artifacts)
    export["mode"] = "acceptance_candidate"
    _write_export(artifacts.export_path, export)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "ineligible_export"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("authorizer_id", None),
        ("authorizer_id", "not an opaque identity"),
        ("provider_profile", []),
        ("provider_profile", "provider/profile"),
    ],
)
def test_judge_authorization_identity_fields_are_independently_validated(
    artifacts: ArtifactFixture,
    field: str,
    invalid_value: object,
) -> None:
    module = _module()
    export = _acceptance_export(artifacts)
    export["judge"]["authorizations"][0][field] = invalid_value
    _rebind_authorization(export)
    _write_export(artifacts.export_path, export)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "judge_evidence_mismatch"


def test_hidden_judge_requires_the_derived_preseal_lifecycle(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _review_evidence_export(artifacts)
    export["round"]["lifecycle"] = "calibration_failed_sealed"
    _write_export(artifacts.export_path, export)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "preseal_judge_disclosure"


def _mutate_export(
    fixture: ArtifactFixture,
    mutator: Callable[[dict[str, Any]], None],
    *,
    rehash: bool = True,
) -> None:
    export = _acceptance_export(fixture)
    mutator(export)
    _write_export(fixture.export_path, export, rehash=rehash)


@pytest.mark.parametrize(
    ("expected_code", "mutator", "rehash"),
    [
        (
            "export_hash_mismatch",
            lambda value: value.update(export_id="changed"),
            False,
        ),
        (
            "artifact_mismatch",
            lambda value: value["artifact_identity"].update(packet_raw_sha256="0" * 64),
            True,
        ),
        (
            "decision_chain_mismatch",
            lambda value: value["decision_events"][0]["canonical_payload"].update(
                decision="needs_change"
            ),
            True,
        ),
        (
            "decision_chain_mismatch",
            lambda value: value["contract_decisions"][0].update(revision=2),
            True,
        ),
        (
            "accounting_mismatch",
            lambda value: value["accounting"]["counts"].update(human_actions=111),
            True,
        ),
        (
            "judge_evidence_mismatch",
            lambda value: value["judge"]["authorizations"][0].update(
                model_id="other-model"
            ),
            True,
        ),
        (
            "judge_evidence_mismatch",
            lambda value: value["judge"]["responses"][0]["response"].update(
                decision="unsupported"
            ),
            True,
        ),
        (
            "gate_mismatch",
            lambda value: value["judge"]["summary"].update(agreement=0.5),
            True,
        ),
        (
            "ineligible_export",
            lambda value: value.update(task_2_8_eligible=False),
            True,
        ),
    ],
)
def test_tampering_fails_closed_with_stable_codes(
    artifacts: ArtifactFixture,
    expected_code: str,
    mutator: Callable[[dict[str, Any]], None],
    rehash: bool,
) -> None:
    module = _module()
    _mutate_export(artifacts, mutator, rehash=rehash)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == expected_code
    assert str(caught.value) == expected_code
    assert str(artifacts.export_path) not in str(caught.value)


def test_preseal_export_rejects_every_judge_or_derived_model_signal(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _review_evidence_export(artifacts)
    export["judge"] = {
        "visibility": "hidden_until_sealed",
        "status": "hidden_until_sealed",
        "agreement": 1.0,
    }
    _write_export(artifacts.export_path, export)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)
    assert caught.value.code == "preseal_judge_disclosure"


def test_peer_artifact_or_source_drift_fails_without_leaking_paths(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    export = _acceptance_export(artifacts)
    _write_export(artifacts.export_path, export)
    policy_path = artifacts.review_dir / POLICY_NAME
    policy_path.write_bytes(policy_path.read_bytes() + b" ")

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "artifact_mismatch"
    assert str(caught.value) == "artifact_mismatch"
    assert str(artifacts.source_root) not in str(caught.value)


def test_self_consistent_rebinding_cannot_replace_frozen_artifact_bytes(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    policy_path = artifacts.review_dir / POLICY_NAME
    policy_path.write_bytes(policy_path.read_bytes() + b" ")
    workload = _json(artifacts.workload_path)
    workload["policy_identity"]["raw_sha256"] = _raw_sha256(policy_path)
    workload.pop("content_sha256")
    workload["content_sha256"] = _canonical_sha256(workload)
    artifacts.workload_path.write_text(
        json.dumps(workload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    export = _review_evidence_export(artifacts)
    _write_export(artifacts.export_path, export)

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "artifact_mismatch"


def test_invalid_json_and_duplicate_keys_have_one_nonleaking_error(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    artifacts.export_path.write_text(
        '{"mode":"review_evidence","mode":"x"}', encoding="utf-8"
    )

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "invalid_json"
    assert str(caught.value) == "invalid_json"
    assert "mode" not in str(caught.value)


def test_lone_surrogate_json_maps_to_stable_nonleaking_error(
    artifacts: ArtifactFixture,
) -> None:
    module = _module()
    artifacts.export_path.write_bytes(b'{"value":"\\ud800"}')

    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "invalid_json"
    assert str(caught.value) == "invalid_json"


def test_unreadable_artifact_maps_to_stable_nonleaking_error(
    artifacts: ArtifactFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    export = _review_evidence_export(artifacts)
    _write_export(artifacts.export_path, export)
    denied_path = artifacts.source_root / "apps/admin-console/backend/static/review.js"
    original_read_bytes = Path.read_bytes

    def denied_read_bytes(path: Path) -> bytes:
        if path == denied_path:
            raise PermissionError(f"denied: {denied_path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", denied_read_bytes)
    with pytest.raises(module.ReviewExportValidationError) as caught:
        _validate(module, artifacts)

    assert caught.value.code == "artifact_mismatch"
    assert str(caught.value) == "artifact_mismatch"
    assert str(denied_path) not in str(caught.value)
