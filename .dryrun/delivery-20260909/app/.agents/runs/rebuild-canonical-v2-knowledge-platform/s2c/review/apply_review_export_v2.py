"""Apply one independently validated human-review export to reviewed S2C v2."""

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from typing import Any


__all__ = (
    "AppliedReviewV2",
    "ReviewApplicationError",
    "apply_review_export_v2",
)


_VALIDATED_SCHEMA = "canonical-v2-validated-review-export-v2"
_EXPORT_SCHEMA = "canonical-v2-human-review-export-v2"
_MANIFEST_V1_SCHEMA = "canonical-v2-s2c-corpus-manifest-v1"
_MANIFEST_V2_SCHEMA = "canonical-v2-s2c-corpus-manifest-v2"
_CORPUS_V2_ID = "canonical-v2-s2c-reviewed-v2"
_POLICY_ID = "single-human-global-stratified-v2"
_EXPECTED_COUNTS = {
    "calibration_probes": 60,
    "contract_reviews": 29,
    "exclusion_reviews": 23,
    "human_actions": 112,
}
_V1_OUTPUTS = {
    "case-accounting-v1.jsonl",
    "claim-level-corpus-v1.jsonl",
    "source-snapshots-v1.jsonl",
}
_V2_DATA_OUTPUTS = (
    "claim-level-corpus-v2.jsonl",
    "case-accounting-v2.jsonl",
    "source-snapshots-v2.jsonl",
    "human-review-bindings-v2.jsonl",
    "exclusion-review-bindings-v2.jsonl",
    "judge-calibration-v2.json",
)
_SHA256_KEYS = {
    "s2c_manifest_raw_sha256",
    "s2c_manifest_content_sha256",
    "s2c_corpus_raw_sha256",
    "s2c_accounting_raw_sha256",
    "s2c_snapshots_raw_sha256",
}


class ReviewApplicationError(ValueError):
    """Stable fail-closed error for reviewed-v2 application."""


@dataclass(frozen=True, slots=True)
class AppliedReviewV2:
    manifest_path: Path
    manifest_content_sha256: str
    output_sha256s: Mapping[str, str]
    contract_review_count: int
    exclusion_review_count: int
    calibration_probe_count: int


@dataclass(frozen=True, slots=True)
class _Predecessor:
    manifest: dict[str, Any]
    manifest_raw_sha256: str
    contracts: tuple[dict[str, Any], ...]
    accounts: tuple[dict[str, Any], ...]
    snapshots: tuple[dict[str, Any], ...]


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewApplicationError("value is not canonical JSON") from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _without(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result.pop(field, None)
    return result


def _self_hash(payload: Mapping[str, Any], field: str, label: str) -> None:
    supplied = payload.get(field)
    if not isinstance(supplied, str) or supplied != _canonical_sha256(
        _without(payload, field)
    ):
        raise ReviewApplicationError(f"{label} content hash mismatch")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewApplicationError("export contains duplicate JSON keys")
        result[key] = value
    return result


def _parse_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewApplicationError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ReviewApplicationError(f"{label} must be an object")
    return value


def _read_jsonl(path: Path, label: str) -> tuple[dict[str, Any], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = tuple(json.loads(line, object_pairs_hook=_reject_duplicate_keys) for line in lines)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewApplicationError(f"predecessor {label} is invalid") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ReviewApplicationError(f"predecessor {label} is invalid")
    if path.read_bytes() != _jsonl_bytes(rows):
        raise ReviewApplicationError(f"predecessor {label} is not deterministic")
    return rows


def _contract_module(manifest_path: Path) -> Any:
    path = manifest_path.parent / "claim_level_case_contract.py"
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / "claim_level_case_contract.py"
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_review_application_contract", path
    )
    if spec is None or spec.loader is None:
        raise ReviewApplicationError("predecessor contract schema is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, TypeError, ValueError) as exc:
        raise ReviewApplicationError("predecessor contract schema is unavailable") from exc
    return module


def _load_predecessor(path: Path, artifact_identity: Mapping[str, Any]) -> _Predecessor:
    try:
        raw = path.read_bytes()
        manifest = _parse_json_bytes(raw, "predecessor manifest")
    except OSError as exc:
        raise ReviewApplicationError("predecessor manifest is unavailable") from exc
    if raw != _pretty_bytes(manifest):
        raise ReviewApplicationError("predecessor manifest is not deterministic")
    _self_hash(manifest, "content_sha256", "predecessor manifest")
    if (
        manifest.get("schema_version") != _MANIFEST_V1_SCHEMA
        or set(manifest.get("outputs", {})) != _V1_OUTPUTS
    ):
        raise ReviewApplicationError("predecessor manifest schema identity mismatch")

    manifest_raw_sha256 = hashlib.sha256(raw).hexdigest()
    paths = {
        "s2c_manifest_raw_sha256": path,
        "s2c_corpus_raw_sha256": path.with_name("claim-level-corpus-v1.jsonl"),
        "s2c_accounting_raw_sha256": path.with_name("case-accounting-v1.jsonl"),
        "s2c_snapshots_raw_sha256": path.with_name("source-snapshots-v1.jsonl"),
    }
    try:
        expected = {
            key: hashlib.sha256(candidate.read_bytes()).hexdigest()
            for key, candidate in paths.items()
        }
    except OSError as exc:
        raise ReviewApplicationError("predecessor artifact is unavailable") from exc
    expected["s2c_manifest_content_sha256"] = manifest["content_sha256"]
    if any(artifact_identity.get(key) != expected[key] for key in _SHA256_KEYS):
        raise ReviewApplicationError("predecessor artifact identity mismatch")
    for name, identity in manifest["outputs"].items():
        try:
            actual_sha256 = hashlib.sha256(path.with_name(name).read_bytes()).hexdigest()
        except OSError as exc:
            raise ReviewApplicationError("predecessor output is unavailable") from exc
        if (
            not isinstance(identity, dict)
            or set(identity) != {"sha256"}
            or identity["sha256"] != actual_sha256
        ):
            raise ReviewApplicationError("predecessor output hash mismatch")

    contracts = _read_jsonl(path.with_name("claim-level-corpus-v1.jsonl"), "contracts")
    accounts = _read_jsonl(path.with_name("case-accounting-v1.jsonl"), "accounting")
    snapshots = _read_jsonl(path.with_name("source-snapshots-v1.jsonl"), "snapshots")
    try:
        validated = _contract_module(path).validate_case_contracts(contracts)
        validated_rows = tuple(item.model_dump(mode="json") for item in validated)
    except (TypeError, ValueError) as exc:
        raise ReviewApplicationError("predecessor contract validation failed") from exc
    if len(validated_rows) != len(contracts) or any(
        _canonical_bytes(left) != _canonical_bytes(right)
        for left, right in zip(validated_rows, contracts, strict=True)
    ):
        raise ReviewApplicationError("predecessor contract identity changed during validation")

    contracts_by_source = {row.get("source_case_id"): row for row in contracts}
    accounts_by_source = {row.get("source_case_id"): row for row in accounts}
    if (
        len(contracts_by_source) != 52
        or len(accounts_by_source) != 52
        or set(contracts_by_source) != set(accounts_by_source)
        or len({row.get("snapshot_id") for row in snapshots}) != len(snapshots)
    ):
        raise ReviewApplicationError("predecessor case accounting identity mismatch")
    for account in accounts:
        _self_hash(account, "content_sha256", "predecessor account")
        contract = contracts_by_source.get(account.get("source_case_id"))
        if (
            contract is None
            or account.get("contract_case_id") != contract.get("case_id")
            or account.get("contract_content_sha256") != contract.get("content_sha256")
        ):
            raise ReviewApplicationError("predecessor account/contract identity mismatch")
    for snapshot in snapshots:
        _self_hash(snapshot, "record_sha256", "predecessor snapshot")

    states = Counter(row.get("review_state") for row in contracts)
    if states != Counter({"pending_user_review": 29, "blocked_missing_evidence": 23}):
        raise ReviewApplicationError("predecessor review-state accounting mismatch")
    if any(row.get("acceptance_eligible") is not False for row in contracts):
        raise ReviewApplicationError("predecessor acceptance state mismatch")
    return _Predecessor(
        manifest=manifest,
        manifest_raw_sha256=manifest_raw_sha256,
        contracts=contracts,
        accounts=accounts,
        snapshots=snapshots,
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(child) for child in value]
    return value


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        thawed = _thaw_json(value)
        if isinstance(thawed, dict):
            return thawed
    fields = getattr(value, "__dataclass_fields__", None)
    if isinstance(fields, dict):
        return {name: _thaw_json(getattr(value, name)) for name in fields}
    raise ReviewApplicationError(f"validated {label} is invalid")


def _validated_payload(validated: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    required_fields = (
        "schema_version",
        "export_id",
        "round_id",
        "mode",
        "evidence_class",
        "acceptance_eligible",
        "task_2_8_eligible",
        "policy_id",
        "workload_counts",
        "artifact_identity",
        "canonical_export_bytes",
        "raw_sha256",
        "content_sha256",
    )
    if any(not hasattr(validated, field) for field in required_fields):
        raise ReviewApplicationError("validated review result is incomplete")
    if (
        validated.schema_version != _VALIDATED_SCHEMA
        or validated.mode != "acceptance_candidate"
        or validated.evidence_class != "real_human_round"
        or validated.acceptance_eligible is not True
        or validated.task_2_8_eligible is not True
        or validated.policy_id != _POLICY_ID
    ):
        raise ReviewApplicationError("validated acceptance result or policy is invalid")
    counts = _mapping(validated.workload_counts, "workload counts")
    if counts != _EXPECTED_COUNTS:
        raise ReviewApplicationError("validated workload counts are invalid")
    artifact_identity = _mapping(validated.artifact_identity, "artifact identity")
    content = validated.canonical_export_bytes
    if not isinstance(content, bytes):
        raise ReviewApplicationError("validated export bytes are invalid")
    if hashlib.sha256(content).hexdigest() != validated.raw_sha256:
        raise ReviewApplicationError("validated export raw hash mismatch")
    payload = _parse_json_bytes(content, "validated export")
    if content != _canonical_bytes(payload):
        raise ReviewApplicationError("validated export bytes are not canonical")
    _self_hash(payload, "content_sha256", "validated export")
    round_payload = payload.get("round")
    if (
        payload.get("schema_version") != _EXPORT_SCHEMA
        or payload.get("export_id") != validated.export_id
        or payload.get("mode") != validated.mode
        or payload.get("evidence_class") != validated.evidence_class
        or payload.get("acceptance_eligible") is not True
        or payload.get("task_2_8_eligible") is not True
        or payload.get("content_sha256") != validated.content_sha256
        or payload.get("artifact_identity") != artifact_identity
        or not isinstance(round_payload, dict)
        or round_payload.get("round_id") != validated.round_id
        or round_payload.get("lifecycle") != "locked"
    ):
        raise ReviewApplicationError("validated export identity mismatch")
    accounting = payload.get("accounting")
    if (
        not isinstance(accounting, dict)
        or accounting.get("counts") != _EXPECTED_COUNTS
        or accounting.get("missing") != []
        or accounting.get("blocking") != []
    ):
        raise ReviewApplicationError("validated export accounting is incomplete")
    gates = payload.get("gates")
    if (
        not isinstance(gates, dict)
        or gates.get("acceptance_ready") is not True
        or gates.get("calibration_labels_valid") is not True
        or gates.get("missing_task_ids") != []
        or gates.get("blocking_task_ids") != []
        or gates.get("acceptance_blockers") != []
    ):
        raise ReviewApplicationError("validated export acceptance gates failed")
    judge = payload.get("judge")
    attempts = judge.get("attempts") if isinstance(judge, dict) else None
    if (
        not isinstance(judge, dict)
        or judge.get("visibility") != "sealed"
        or not isinstance(judge.get("summary"), dict)
        or judge["summary"].get("passed") is not True
        or not isinstance(attempts, list)
        or any(
            not isinstance(attempt, dict)
            or "idempotency_key" in attempt
            or not isinstance(attempt.get("idempotency_sha256"), str)
            or len(attempt["idempotency_sha256"]) != 64
            for attempt in attempts
        )
    ):
        raise ReviewApplicationError("validated judge evidence is invalid")
    return payload, artifact_identity


def _current_decisions(
    payload: Mapping[str, Any],
    *,
    field: str,
    kind: str,
    expected_decision: str | None,
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    decisions = payload.get(field)
    events = payload.get("decision_events")
    if not isinstance(decisions, list) or not isinstance(events, list):
        raise ReviewApplicationError("validated decision evidence is incomplete")
    events_by_id = {
        event.get("event_id"): event
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
    }
    if len(events_by_id) != len(events):
        raise ReviewApplicationError("validated decision event identity is invalid")
    result: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ReviewApplicationError("validated decision projection is invalid")
        event = events_by_id.get(decision.get("event_id"))
        canonical = event.get("canonical_payload") if isinstance(event, dict) else None
        task_id = decision.get("task_id")
        if (
            not isinstance(task_id, str)
            or task_id in result
            or not isinstance(event, dict)
            or not isinstance(canonical, dict)
            or event.get("task_id") != task_id
            or event.get("task_kind") != kind
            or event.get("decision") != decision.get("decision")
            or event.get("revision") != decision.get("revision")
            or event.get("payload_sha256") != decision.get("payload_sha256")
            or canonical.get("task_id") != task_id
            or canonical.get("task_kind") != kind
            or canonical.get("decision") != decision.get("decision")
            or _canonical_sha256(canonical) != event.get("payload_sha256")
            or (
                expected_decision is not None
                and decision.get("decision") != expected_decision
            )
        ):
            raise ReviewApplicationError("validated current decision identity is invalid")
        result[task_id] = (decision, event)
    return result


def _binding(
    *,
    schema_version: str,
    contract: Mapping[str, Any],
    derived: Mapping[str, Any],
    decision: Mapping[str, Any],
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    policy_id: str,
) -> dict[str, Any]:
    canonical = event["canonical_payload"]
    binding: dict[str, Any] = {
        "schema_version": schema_version,
        "case_id": contract["case_id"],
        "source_case_id": contract["source_case_id"],
        "decision": decision["decision"],
        "rationale": event.get("rationale"),
        "reviewer_id": canonical["reviewer_id"],
        "staff_id": canonical["staff_id"],
        "round_id": payload["round"]["round_id"],
        "export_id": payload["export_id"],
        "export_content_sha256": payload["content_sha256"],
        "policy_id": policy_id,
        "event_id": event["event_id"],
        "event_revision": event["revision"],
        "event_payload_sha256": event["payload_sha256"],
        "submitted_at": event["submitted_at"],
        "predecessor_contract_content_sha256": contract["content_sha256"],
        "derived_contract_content_sha256": derived["content_sha256"],
        "hard_requirement_ids": contract["outcome_policy"]["hard_requirement_ids"],
        "snapshot_ids": [item["snapshot_id"] for item in contract["source_snapshots"]],
    }
    binding["content_sha256"] = _canonical_sha256(binding)
    return binding


def _derive_artifacts(
    predecessor: _Predecessor,
    payload: dict[str, Any],
    artifact_identity: dict[str, Any],
    policy_id: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    contract_decisions = _current_decisions(
        payload,
        field="contract_decisions",
        kind="contract",
        expected_decision="approved",
    )
    exclusion_decisions = _current_decisions(
        payload,
        field="exclusion_decisions",
        kind="exclusion",
        expected_decision="accept_exclusion",
    )
    calibration_decisions = _current_decisions(
        payload,
        field="calibration_labels",
        kind="calibration",
        expected_decision=None,
    )
    pending_ids = {
        f"contract:{row['case_id']}"
        for row in predecessor.contracts
        if row["review_state"] == "pending_user_review"
    }
    blocked_ids = {
        f"exclusion:{row['case_id']}"
        for row in predecessor.contracts
        if row["review_state"] == "blocked_missing_evidence"
    }
    if (
        set(contract_decisions) != pending_ids
        or set(exclusion_decisions) != blocked_ids
        or len(calibration_decisions) != 60
        or any(
            decision[0].get("decision") not in {"supported", "unsupported"}
            for decision in calibration_decisions.values()
        )
    ):
        raise ReviewApplicationError("validated review decision set is incomplete")

    reviewer_id = payload["round"].get("reviewer_id")
    staff_id = payload["round"].get("staff_id")
    for _, event in (
        *contract_decisions.values(),
        *exclusion_decisions.values(),
        *calibration_decisions.values(),
    ):
        canonical = event["canonical_payload"]
        if (
            canonical.get("reviewer_id") != reviewer_id
            or canonical.get("staff_id") != staff_id
        ):
            raise ReviewApplicationError("validated reviewer attribution is cross-wired")

    derived_contracts: list[dict[str, Any]] = []
    derived_by_case: dict[str, dict[str, Any]] = {}
    for original in predecessor.contracts:
        derived = dict(original)
        derived["corpus_id"] = _CORPUS_V2_ID
        if original["review_state"] == "pending_user_review":
            derived["review_state"] = "human_reviewed"
            derived["acceptance_eligible"] = True
        derived["content_sha256"] = _canonical_sha256(
            _without(derived, "content_sha256")
        )
        derived_contracts.append(derived)
        derived_by_case[derived["case_id"]] = derived

    try:
        validated = _contract_module(
            Path(__file__).resolve().parent.parent / "claim-level-corpus-manifest-v1.json"
        ).validate_case_contracts(tuple(derived_contracts))
    except (TypeError, ValueError) as exc:
        raise ReviewApplicationError("derived reviewed contracts are invalid") from exc
    if any(
        _canonical_bytes(model.model_dump(mode="json")) != _canonical_bytes(raw)
        for model, raw in zip(validated, derived_contracts, strict=True)
    ):
        raise ReviewApplicationError("derived reviewed contract identity changed")

    derived_accounts: list[dict[str, Any]] = []
    for original in predecessor.accounts:
        derived = dict(original)
        contract = derived_by_case[derived["contract_case_id"]]
        derived["contract_content_sha256"] = contract["content_sha256"]
        derived["review_state"] = contract["review_state"]
        derived["acceptance_eligible"] = contract["acceptance_eligible"]
        if contract["review_state"] == "human_reviewed":
            derived["reason_code"] = "claim_contract_human_reviewed"
        derived["content_sha256"] = _canonical_sha256(
            _without(derived, "content_sha256")
        )
        derived_accounts.append(derived)

    derived_snapshots: list[dict[str, Any]] = []
    for original in predecessor.snapshots:
        derived = dict(original)
        if derived.get("snapshot_role") == "claim_evidence":
            derived["source_corpus_id"] = _CORPUS_V2_ID
        derived["record_sha256"] = _canonical_sha256(
            _without(derived, "record_sha256")
        )
        derived_snapshots.append(derived)

    original_by_case = {row["case_id"]: row for row in predecessor.contracts}
    human_bindings: list[dict[str, Any]] = []
    for task_id in sorted(contract_decisions):
        decision, event = contract_decisions[task_id]
        case_id = task_id.removeprefix("contract:")
        human_bindings.append(
            _binding(
                schema_version="canonical-v2-human-review-binding-v2",
                contract=original_by_case[case_id],
                derived=derived_by_case[case_id],
                decision=decision,
                event=event,
                payload=payload,
                policy_id=policy_id,
            )
        )
    exclusion_bindings: list[dict[str, Any]] = []
    for task_id in sorted(exclusion_decisions):
        decision, event = exclusion_decisions[task_id]
        case_id = task_id.removeprefix("exclusion:")
        exclusion_bindings.append(
            _binding(
                schema_version="canonical-v2-exclusion-review-binding-v2",
                contract=original_by_case[case_id],
                derived=derived_by_case[case_id],
                decision=decision,
                event=event,
                payload=payload,
                policy_id=policy_id,
            )
        )

    calibration: dict[str, Any] = {
        "schema_version": "canonical-v2-judge-calibration-v2",
        "export_id": payload["export_id"],
        "export_content_sha256": payload["content_sha256"],
        "round_id": payload["round"]["round_id"],
        "reviewer_id": reviewer_id,
        "staff_id": staff_id,
        "policy_id": policy_id,
        "workload_counts": _EXPECTED_COUNTS,
        "calibration_labels": payload["calibration_labels"],
        "judge": payload["judge"],
    }
    calibration["content_sha256"] = _canonical_sha256(calibration)

    output_bytes = {
        "claim-level-corpus-v2.jsonl": _jsonl_bytes(derived_contracts),
        "case-accounting-v2.jsonl": _jsonl_bytes(derived_accounts),
        "source-snapshots-v2.jsonl": _jsonl_bytes(derived_snapshots),
        "human-review-bindings-v2.jsonl": _jsonl_bytes(human_bindings),
        "exclusion-review-bindings-v2.jsonl": _jsonl_bytes(exclusion_bindings),
        "judge-calibration-v2.json": _pretty_bytes(calibration),
    }
    output_sha256s = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in output_bytes.items()
    }
    review_application = {
        "schema_version": "canonical-v2-reviewed-application-binding-v2",
        "export_id": payload["export_id"],
        "export_raw_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
        "export_content_sha256": payload["content_sha256"],
        "round_id": payload["round"]["round_id"],
        "reviewer_id": reviewer_id,
        "staff_id": staff_id,
        "evidence_class": payload["evidence_class"],
        "policy_id": policy_id,
        "counts": dict(_EXPECTED_COUNTS),
        "artifact_identity": artifact_identity,
        "human_review_bindings_sha256": output_sha256s[
            "human-review-bindings-v2.jsonl"
        ],
        "exclusion_review_bindings_sha256": output_sha256s[
            "exclusion-review-bindings-v2.jsonl"
        ],
        "judge_calibration_sha256": calibration["content_sha256"],
    }
    manifest: dict[str, Any] = {
        "schema_version": _MANIFEST_V2_SCHEMA,
        "corpus_id": _CORPUS_V2_ID,
        "contract_version": predecessor.manifest["contract_version"],
        "case_contract_schema_version": predecessor.manifest[
            "case_contract_schema_version"
        ],
        "contract_as_of": predecessor.manifest["contract_as_of"],
        "source_case_count": len(derived_accounts),
        "contract_case_count": len(derived_contracts),
        "snapshot_count": len(derived_snapshots),
        "acceptance_eligible_count": 29,
        "approval_state": "human_reviewed",
        "review_state_counts": {
            "blocked_missing_evidence": 23,
            "human_reviewed": 29,
            "pending_user_review": 0,
        },
        "conversion_outcome_counts": predecessor.manifest[
            "conversion_outcome_counts"
        ],
        "family_counts": predecessor.manifest["family_counts"],
        "sources": predecessor.manifest["sources"],
        "frozen_inputs": predecessor.manifest["frozen_inputs"],
        "predecessor": {
            "schema_version": predecessor.manifest["schema_version"],
            "corpus_id": predecessor.manifest["corpus_id"],
            "manifest_raw_sha256": predecessor.manifest_raw_sha256,
            "manifest_content_sha256": predecessor.manifest["content_sha256"],
            "output_sha256s": {
                name: identity["sha256"]
                for name, identity in predecessor.manifest["outputs"].items()
            },
        },
        "review_application": review_application,
        "outputs": {
            name: {"sha256": output_sha256s[name]}
            for name in _V2_DATA_OUTPUTS
        },
    }
    manifest["content_sha256"] = _canonical_sha256(manifest)
    output_bytes["claim-level-corpus-manifest-v2.json"] = _pretty_bytes(manifest)
    return output_bytes, manifest


def _safe_destination(path: Path) -> Path:
    if ".." in path.parts:
        raise ReviewApplicationError("output destination is unsafe")
    destination = Path(os.path.abspath(os.fspath(path)))
    if destination.exists() or destination.is_symlink():
        raise ReviewApplicationError("output destination already exists")
    return destination


def _publish(output_dir: Path, output_bytes: Mapping[str, bytes]) -> None:
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=parent))
    try:
        for name, content in output_bytes.items():
            if Path(name).name != name:
                raise ReviewApplicationError("output artifact name is unsafe")
            target = stage / name
            descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
        directory_descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        if output_dir.exists() or output_dir.is_symlink():
            raise ReviewApplicationError("output destination already exists")
        os.rename(stage, output_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def apply_review_export_v2(
    *,
    export_path: str | Path,
    packet_path: str | Path,
    workload_path: str | Path,
    source_root: str | Path,
    predecessor_manifest_path: str | Path,
    output_dir: str | Path,
) -> AppliedReviewV2:
    """Validate one export and derive immutable reviewed-v2 artifacts."""

    destination = _safe_destination(Path(output_dir))
    validator = _validator_module()
    try:
        validated_export = validator.validate_review_export_v2(
            export_path=Path(export_path),
            packet_path=Path(packet_path),
            workload_path=Path(workload_path),
            source_root=Path(source_root),
        )
    except validator.ReviewExportValidationError as exc:
        raise ReviewApplicationError("review export validation failed") from exc
    payload, artifact_identity = _validated_payload(validated_export)
    predecessor = _load_predecessor(
        Path(predecessor_manifest_path).resolve(), artifact_identity
    )
    output_bytes, manifest = _derive_artifacts(
        predecessor,
        payload,
        artifact_identity,
        validated_export.policy_id,
    )
    _publish(destination, output_bytes)
    output_sha256s = MappingProxyType(
        {
            name: hashlib.sha256(content).hexdigest()
            for name, content in output_bytes.items()
        }
    )
    return AppliedReviewV2(
        manifest_path=destination / "claim-level-corpus-manifest-v2.json",
        manifest_content_sha256=manifest["content_sha256"],
        output_sha256s=output_sha256s,
        contract_review_count=29,
        exclusion_review_count=23,
        calibration_probe_count=60,
    )


def _validator_module() -> Any:
    path = Path(__file__).with_name("validate_review_export_v2.py")
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_review_export_validator_for_application", path
    )
    if spec is None or spec.loader is None:
        raise ReviewApplicationError("independent review export validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--predecessor-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = apply_review_export_v2(
        export_path=args.export,
        packet_path=args.packet,
        workload_path=args.workload,
        source_root=args.source_root,
        predecessor_manifest_path=args.predecessor_manifest,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "manifest_content_sha256": receipt.manifest_content_sha256,
                "manifest_path": str(receipt.manifest_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
