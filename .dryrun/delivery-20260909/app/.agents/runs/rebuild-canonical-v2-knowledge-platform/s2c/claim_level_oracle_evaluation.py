"""Run-local evaluator for the Canonical V2 claim-level acceptance corpus."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


__all__ = ("evaluate_oracle_run",)

_HERE = Path(__file__).resolve().parent
_CONTRACT_PATH = _HERE / "claim_level_case_contract.py"
_OUTPUT_NAMES_V1 = (
    "case-accounting-v1.jsonl",
    "claim-level-corpus-v1.jsonl",
    "source-snapshots-v1.jsonl",
)
_OUTPUT_NAMES_V2 = (
    "case-accounting-v2.jsonl",
    "claim-level-corpus-v2.jsonl",
    "source-snapshots-v2.jsonl",
    "human-review-bindings-v2.jsonl",
    "exclusion-review-bindings-v2.jsonl",
    "judge-calibration-v2.json",
)
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_RUN_INPUT_V1_KEYS = {
    "exclusions",
    "expected_manifest_content_sha256",
    "human_reviews",
    "judge_calibrations",
    "judge_policy",
    "observations",
    "run_id",
    "schema_version",
    "selected_case_ids",
    "soft_metrics",
}
_RUN_INPUT_V2_KEYS = {
    "expected_manifest_content_sha256",
    "judge_policy",
    "observations",
    "review_binding",
    "run_id",
    "schema_version",
    "selected_case_ids",
    "soft_metrics",
}
_REVIEW_BINDING_KEYS = {
    "counts",
    "exclusion_review_bindings_sha256",
    "export_content_sha256",
    "export_id",
    "human_review_bindings_sha256",
    "judge_calibration_sha256",
    "policy_id",
}
_GLOBAL_REVIEW_COUNTS = {
    "calibration_probes": 60,
    "contract_reviews": 29,
    "exclusion_reviews": 23,
    "human_actions": 112,
}
_GLOBAL_REVIEW_POLICY_ID = "single-human-global-stratified-v2"
_GLOBAL_REVIEW_STRATA = {
    "claim_evidence": 20,
    "context_relationship": 10,
    "identity_entity": 10,
    "insufficiency_assessment": 10,
    "safety_web": 10,
}
_OBSERVATION_KEYS = {
    "enumeration_report",
    "rendered_claims",
    "rendered_entity_ids",
    "stage_observations",
}
_RENDERED_CLAIM_KEYS = {
    "claim_id",
    "evidence_snapshot_ids",
    "object_constraint",
    "predicate",
    "subject",
}
_STAGE_OBSERVATION_KEYS = {
    "actual",
    "expectation_id",
    "observable_kind",
    "stage",
}
_JUDGE_RESPONSE_KEYS = {
    "contract_content_sha256",
    "decision",
    "evidence_snapshot_ids",
    "request_sha256",
    "requirement_id",
    "schema_version",
    "used_external_memory",
}


class _FrozenDict(dict[str, Any]):
    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("oracle result mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _deep_freeze(self) -> _StrictModel:
        for field_name in type(self).model_fields:
            object.__setattr__(
                self, field_name, _freeze_json(getattr(self, field_name))
            )
        return self


class _ArtifactIdentity(_StrictModel):
    case_contract_schema_version: str
    contract_as_of: str
    contract_version: str
    corpus_id: str
    manifest_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_file_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_schema_version: str
    output_sha256s: dict[str, str]
    snapshot_record_sha256s: dict[str, str]


class _HardOutcome(_StrictModel):
    requirement_id: str
    passed: bool | None
    stage: str


class _StageOutcome(_StrictModel):
    stage: str
    hard_passed: bool
    failed_requirement_ids: tuple[str, ...]
    unresolved_requirement_ids: tuple[str, ...]


class _JudgeOutcome(_StrictModel):
    requirement_id: str
    status: Literal["supported", "unsupported", "unresolved"]
    acceptance_usable: bool
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    response_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)


class _CaseResult(_StrictModel):
    case_id: str
    contract_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    hard_outcomes: tuple[_HardOutcome, ...]
    stage_outcomes: tuple[_StageOutcome, ...]
    judge_outcomes: tuple[_JudgeOutcome, ...]
    failed_requirement_ids: tuple[str, ...]
    unresolved_requirement_ids: tuple[str, ...]
    hard_passed: bool
    failure_stage: str | None
    acceptance_eligible: bool
    soft_metrics: dict[str, float]


class _AcceptanceRecord(_StrictModel):
    artifact_identity: _ArtifactIdentity
    accepted_case_ids: tuple[str, ...]
    excluded_case_ids: tuple[str, ...]
    case_count: int
    human_review_count: int
    excluded_case_count: int
    human_review_sha256s: tuple[str, ...]
    judge_calibration_sha256s: tuple[str, ...]
    exclusion_sha256s: tuple[str, ...]
    hard_outcome_sha256s: dict[str, str]
    reviewer_states: dict[str, str]
    synthetic_fixture: bool
    content_sha256: str = Field(pattern=_SHA256_PATTERN)


class _ReviewedAcceptanceRecord(_StrictModel):
    artifact_identity: _ArtifactIdentity
    accepted_case_ids: tuple[str, ...]
    excluded_case_ids: tuple[str, ...]
    case_count: int
    human_review_count: int
    excluded_case_count: int
    calibration_probe_count: int
    human_review_bindings_sha256: str = Field(pattern=_SHA256_PATTERN)
    exclusion_review_bindings_sha256: str = Field(pattern=_SHA256_PATTERN)
    judge_calibration_sha256: str = Field(pattern=_SHA256_PATTERN)
    hard_outcome_sha256s: dict[str, str]
    reviewer_states: dict[str, str]
    review_export_id: str
    review_export_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    review_policy_id: str
    synthetic_fixture: Literal[False] = False
    content_sha256: str = Field(pattern=_SHA256_PATTERN)


class _EvaluationResult(_StrictModel):
    artifact_identity: _ArtifactIdentity
    corpus_summary: dict[str, int]
    case_results: tuple[_CaseResult, ...]
    acceptance_ready: bool
    acceptance_record: _AcceptanceRecord | _ReviewedAcceptanceRecord | None = None


for _model in (
    _ArtifactIdentity,
    _HardOutcome,
    _StageOutcome,
    _JudgeOutcome,
    _CaseResult,
    _AcceptanceRecord,
    _ReviewedAcceptanceRecord,
    _EvaluationResult,
):
    _model.model_rebuild(_types_namespace=globals())


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("oracle value is not canonical JSON") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _json_equal(left: Any, right: Any) -> bool:
    return _canonical_bytes(left) == _canonical_bytes(right)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    content = dict(payload)
    content.pop(field, None)
    return content


def _verify_self_hash(payload: Mapping[str, Any], *, field: str, label: str) -> None:
    supplied = payload.get(field)
    if not isinstance(supplied, str) or supplied != _canonical_sha256(
        _without(payload, field)
    ):
        raise ValueError(f"{label} content hash mismatch")


def _require_exact_keys(
    payload: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{label} has unknown/extra or missing fields: {missing=}, {extra=}"
        )


def _require_unique(values: Sequence[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} artifact is invalid JSONL") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{label} artifact rows must be objects")
    canonical = b"".join(_canonical_bytes(row) + b"\n" for row in rows)
    if path.read_bytes() != canonical:
        raise ValueError(f"{label} artifact is not canonical JSONL")
    return rows


@lru_cache(maxsize=1)
def _contract_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_contract_for_oracle_green", _CONTRACT_PATH
    )
    if spec is None or spec.loader is None:
        raise ValueError("case contract schema cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest artifact is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest artifact must be an object")
    deterministic_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if manifest_path.read_bytes() != deterministic_bytes:
        raise ValueError("manifest file identity is not deterministic")
    _verify_self_hash(manifest, field="content_sha256", label="manifest")
    if (
        manifest.get("schema_version")
        not in {
            "canonical-v2-s2c-corpus-manifest-v1",
            "canonical-v2-s2c-corpus-manifest-v2",
        }
        or manifest.get("case_contract_schema_version")
        != "canonical-v2-claim-level-case-contract-v1"
        or manifest.get("contract_version") != "claim-level-contract-v1"
    ):
        raise ValueError("manifest schema/contract version identity mismatch")
    for field in (
        "acceptance_eligible_count",
        "contract_case_count",
        "snapshot_count",
        "source_case_count",
    ):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"manifest {field} must be a non-negative integer")
    for field in (
        "conversion_outcome_counts",
        "family_counts",
        "review_state_counts",
    ):
        counts = manifest.get(field)
        if not isinstance(counts, dict) or any(
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in counts.items()
        ):
            raise ValueError(f"manifest {field} is invalid")
    if "synthetic_fixture" in manifest and manifest["synthetic_fixture"] is not True:
        raise ValueError("manifest synthetic fixture flag is invalid")
    if manifest.get("schema_version") == "canonical-v2-s2c-corpus-manifest-v2" and (
        manifest.get("approval_state") != "human_reviewed"
        or manifest.get("acceptance_eligible_count") != 29
        or manifest.get("review_state_counts")
        != {
            "blocked_missing_evidence": 23,
            "human_reviewed": 29,
            "pending_user_review": 0,
        }
        or "synthetic_fixture" in manifest
    ):
        raise ValueError("reviewed-v2 manifest review accounting mismatch")
    return manifest


def _validate_snapshot_record(snapshot: Mapping[str, Any]) -> None:
    _verify_self_hash(snapshot, field="record_sha256", label="snapshot record")
    payload_kind = snapshot.get("payload_kind")
    payload = snapshot.get("payload")
    if payload_kind == "canonical_json":
        content_sha256 = _canonical_sha256(payload)
    elif payload_kind == "utf8_text" and isinstance(payload, str):
        content_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    else:
        raise ValueError("snapshot payload kind is invalid")
    if snapshot.get("content_sha256") != content_sha256:
        raise ValueError("snapshot payload content hash mismatch")


def _load_pretty_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} artifact is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} artifact must be an object")
    expected = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.read_bytes() != expected:
        raise ValueError(f"{label} artifact is not deterministic")
    return value


def _validate_recomputed_calibration(
    calibration: Mapping[str, Any], review: Mapping[str, Any]
) -> None:
    labels = calibration.get("calibration_labels")
    judge = calibration.get("judge")
    if (
        calibration.get("schema_version") != "canonical-v2-judge-calibration-v2"
        or calibration.get("export_id") != review["export_id"]
        or calibration.get("export_content_sha256")
        != review["export_content_sha256"]
        or calibration.get("round_id") != review["round_id"]
        or calibration.get("reviewer_id") != review["reviewer_id"]
        or calibration.get("staff_id") != review["staff_id"]
        or calibration.get("policy_id") != review["policy_id"]
        or calibration.get("workload_counts") != _GLOBAL_REVIEW_COUNTS
        or not isinstance(labels, list)
        or len(labels) != 60
        or not isinstance(judge, dict)
    ):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")

    label_keys = {"decision", "event_id", "payload_sha256", "revision", "task_id"}
    labels_by_task: dict[str, dict[str, Any]] = {}
    for label in labels:
        if not isinstance(label, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(label, label_keys, label="calibration label")
        task_id = label.get("task_id")
        revision = label.get("revision")
        if (
            not isinstance(task_id, str)
            or not task_id.startswith("calibration:")
            or task_id in labels_by_task
            or label.get("decision") not in {"supported", "unsupported"}
            or not isinstance(label.get("event_id"), str)
            or not label["event_id"]
            or not isinstance(label.get("payload_sha256"), str)
            or len(label["payload_sha256"]) != 64
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
        ):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        labels_by_task[task_id] = label
    _require_exact_keys(
        judge,
        {
            "authorizations",
            "attempts",
            "completed_run",
            "recoveries",
            "responses",
            "summary",
            "visibility",
        },
        label="sealed calibration judge",
    )
    authorizations = judge.get("authorizations")
    attempts = judge.get("attempts")
    recoveries = judge.get("recoveries")
    responses = judge.get("responses")
    summary = judge.get("summary")
    if (
        judge.get("visibility") != "sealed"
        or not isinstance(authorizations, list)
        or len(authorizations) != 1
        or not isinstance(authorizations[0], dict)
        or not isinstance(attempts, list)
        or not attempts
        or not isinstance(recoveries, list)
        or not isinstance(responses, list)
        or len(responses) != 60
        or not isinstance(summary, dict)
    ):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")
    judgment_order = summary.get("judgments")
    if not isinstance(judgment_order, list) or len(judgment_order) != 60:
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")
    ordered_label_tasks = [
        judgment.get("task_id") if isinstance(judgment, dict) else None
        for judgment in judgment_order
    ]
    if (
        any(not isinstance(task_id, str) for task_id in ordered_label_tasks)
        or len(set(ordered_label_tasks)) != 60
        or set(ordered_label_tasks) != set(labels_by_task)
    ):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")
    human_snapshot_sha256 = _canonical_sha256(
        [labels_by_task[str(task_id)] for task_id in ordered_label_tasks]
    )

    authorization = authorizations[0]
    _require_exact_keys(
        authorization,
        {
            "authorized_at",
            "authorizer_id",
            "calibration_policy_id",
            "content_sha256",
            "evidence_class",
            "evidence_scope",
            "judge_policy_id",
            "model_id",
            "provider_profile",
            "round_id",
            "schema_version",
            "workload_content_sha256",
        },
        label="calibration authorization",
    )
    _verify_self_hash(
        authorization,
        field="content_sha256",
        label="calibration authorization",
    )
    model_id = authorization.get("model_id")
    artifact_identity = review.get("artifact_identity")
    if (
        authorization.get("schema_version") != "judge-authorization-v2"
        or authorization.get("evidence_class") != "real_human_round"
        or authorization.get("round_id") != review["round_id"]
        or authorization.get("calibration_policy_id") != _GLOBAL_REVIEW_POLICY_ID
        or authorization.get("judge_policy_id") != "evidence-bounded-judge-v1"
        or authorization.get("evidence_scope") != "supplied_request_only"
        or not isinstance(artifact_identity, dict)
        or authorization.get("workload_content_sha256")
        != artifact_identity.get("workload_content_sha256")
        or not isinstance(model_id, str)
        or not model_id
    ):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")

    expected_command_sha256 = _canonical_sha256(
        {
            "action": "seal_calibration",
            "expected_revision": 60,
            "round_id": review["round_id"],
        }
    )
    attempt_keys = {
        "authorization_sha256",
        "command_sha256",
        "failure_code",
        "finished_at",
        "human_snapshot_sha256",
        "idempotency_sha256",
        "round_id",
        "run_id",
        "started_at",
        "state",
    }
    attempts_by_run: dict[str, dict[str, Any]] = {}
    completed_attempts: list[dict[str, Any]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(attempt, attempt_keys, label="calibration judge attempt")
        run_id = attempt.get("run_id")
        state = attempt.get("state")
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id in attempts_by_run
            or attempt.get("round_id") != review["round_id"]
            or not isinstance(attempt.get("idempotency_sha256"), str)
            or len(attempt["idempotency_sha256"]) != 64
            or attempt.get("command_sha256") != expected_command_sha256
            or attempt.get("human_snapshot_sha256") != human_snapshot_sha256
            or attempt.get("authorization_sha256")
            != authorization["content_sha256"]
            or state not in {"completed", "failed"}
            or (state == "completed" and attempt.get("failure_code") is not None)
            or (state == "failed" and not isinstance(attempt.get("failure_code"), str))
        ):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        attempts_by_run[run_id] = attempt
        if state == "completed":
            completed_attempts.append(attempt)
    if len(completed_attempts) != 1 or judge.get("completed_run") != completed_attempts[0]:
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")

    recovery_keys = {
        "authorization_sha256",
        "command_sha256",
        "human_snapshot_sha256",
        "operator_staff_id",
        "reason",
        "recovered_at",
        "recovery_id",
        "round_id",
        "run_id",
    }
    recovered_runs: set[str] = set()
    for recovery in recoveries:
        if not isinstance(recovery, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(recovery, recovery_keys, label="calibration recovery")
        run_id = recovery.get("run_id")
        attempt = attempts_by_run.get(str(run_id))
        operator = recovery.get("operator_staff_id")
        if (
            attempt is None
            or not isinstance(run_id, str)
            or run_id in recovered_runs
            or attempt.get("state") != "failed"
            or attempt.get("failure_code") != "operator_abandoned_after_crash"
            or recovery.get("round_id") != review["round_id"]
            or recovery.get("command_sha256") != expected_command_sha256
            or recovery.get("human_snapshot_sha256") != human_snapshot_sha256
            or recovery.get("authorization_sha256")
            != authorization["content_sha256"]
            or not isinstance(operator, str)
            or not operator
            or recovery.get("reason") != "process_crash_confirmed"
        ):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        recovered_runs.add(run_id)

    response_keys = {
        "judged_at",
        "request_sha256",
        "response",
        "response_sha256",
        "task_id",
    }
    response_body_keys = {
        "decision",
        "evidence_scope",
        "model_id",
        "policy_id",
        "request_sha256",
        "schema_version",
        "used_external_memory",
    }
    responses_by_task: dict[str, dict[str, Any]] = {}
    for row in responses:
        if not isinstance(row, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(row, response_keys, label="calibration response")
        task_id = row.get("task_id")
        response = row.get("response")
        if not isinstance(response, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(
            response,
            response_body_keys,
            label="calibration response body",
        )
        if (
            not isinstance(task_id, str)
            or task_id in responses_by_task
            or task_id not in labels_by_task
            or response.get("schema_version")
            != "canonical-v2-human-calibration-judge-decision-v2"
            or response.get("model_id") != model_id
            or response.get("policy_id") != "evidence-bounded-judge-v1"
            or response.get("request_sha256") != row.get("request_sha256")
            or response.get("decision") not in {"supported", "unsupported"}
            or response.get("evidence_scope") != "supplied_request_only"
            or response.get("used_external_memory") is not False
            or row.get("response_sha256") != _canonical_sha256(response)
        ):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        responses_by_task[task_id] = row

    summary_keys = {
        "agreement",
        "authorization_sha256",
        "calibration_policy_id",
        "confusion_matrix",
        "critical_false_accepts",
        "evidence_class",
        "gates",
        "human_snapshot_sha256",
        "human_supported",
        "human_unsupported",
        "judge_policy_id",
        "judgments",
        "model_id",
        "pair_count",
        "passed",
        "stratum_counts",
        "unsupported_critical_probes",
    }
    _require_exact_keys(summary, summary_keys, label="calibration summary")
    judgments = summary.get("judgments")
    if (
        summary.get("evidence_class") != "real_human_round"
        or summary.get("model_id") != model_id
        or summary.get("calibration_policy_id") != _GLOBAL_REVIEW_POLICY_ID
        or summary.get("judge_policy_id") != "evidence-bounded-judge-v1"
        or summary.get("authorization_sha256")
        != authorization["content_sha256"]
        or summary.get("human_snapshot_sha256") != human_snapshot_sha256
        or not isinstance(judgments, list)
        or len(judgments) != 60
    ):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")

    judgment_keys = {
        "critical_probe",
        "human_decision",
        "model_decision",
        "request_sha256",
        "response_sha256",
        "sample_id",
        "stratum",
        "task_id",
    }
    judgments_by_task: dict[str, dict[str, Any]] = {}
    strata: Counter[str] = Counter()
    confusion: Counter[str] = Counter()
    human_supported = 0
    matches = 0
    unsupported_critical = 0
    critical_false_accepts = 0
    for judgment in judgments:
        if not isinstance(judgment, dict):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        _require_exact_keys(judgment, judgment_keys, label="calibration judgment")
        task_id = judgment.get("task_id")
        response_row = responses_by_task.get(str(task_id))
        label = labels_by_task.get(str(task_id))
        human_decision = judgment.get("human_decision")
        model_decision = judgment.get("model_decision")
        stratum = judgment.get("stratum")
        critical_probe = judgment.get("critical_probe")
        if (
            not isinstance(task_id, str)
            or task_id in judgments_by_task
            or label is None
            or response_row is None
            or judgment.get("sample_id") != task_id.removeprefix("calibration:")
            or stratum not in _GLOBAL_REVIEW_STRATA
            or not isinstance(critical_probe, bool)
            or human_decision != label["decision"]
            or model_decision != response_row["response"]["decision"]
            or judgment.get("request_sha256") != response_row["request_sha256"]
            or judgment.get("response_sha256") != response_row["response_sha256"]
        ):
            raise ValueError("reviewed-v2 global60 judge calibration is invalid")
        judgments_by_task[task_id] = judgment
        strata[str(stratum)] += 1
        human_supported += human_decision == "supported"
        matches += human_decision == model_decision
        confusion[f"human_{human_decision}_model_{model_decision}"] += 1
        is_unsupported_critical = (
            human_decision == "unsupported" and critical_probe is True
        )
        unsupported_critical += is_unsupported_critical
        critical_false_accepts += (
            is_unsupported_critical and model_decision == "supported"
        )
    if set(judgments_by_task) != set(labels_by_task):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")

    human_unsupported = 60 - human_supported
    agreement = matches / 60
    gates = {
        "exact_pair_count": True,
        "exact_stratum_quotas": dict(strata) == _GLOBAL_REVIEW_STRATA,
        "minimum_agreement": agreement >= 0.80,
        "minimum_supported_labels": human_supported >= 10,
        "minimum_unsupported_labels": human_unsupported >= 10,
        "minimum_unsupported_critical_probes": unsupported_critical >= 5,
        "maximum_critical_false_accepts": critical_false_accepts <= 0,
    }
    expected_aggregate = {
        "agreement": agreement,
        "confusion_matrix": {
            "human_supported_model_supported": confusion[
                "human_supported_model_supported"
            ],
            "human_supported_model_unsupported": confusion[
                "human_supported_model_unsupported"
            ],
            "human_unsupported_model_supported": confusion[
                "human_unsupported_model_supported"
            ],
            "human_unsupported_model_unsupported": confusion[
                "human_unsupported_model_unsupported"
            ],
        },
        "critical_false_accepts": critical_false_accepts,
        "gates": gates,
        "human_supported": human_supported,
        "human_unsupported": human_unsupported,
        "pair_count": 60,
        "passed": all(gates.values()),
        "stratum_counts": dict(sorted(strata.items())),
        "unsupported_critical_probes": unsupported_critical,
    }
    if any(summary.get(field) != value for field, value in expected_aggregate.items()):
        raise ValueError("reviewed-v2 global60 judge calibration is invalid")


def _admit_reviewed_v2(
    *,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    contracts_by_case: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    predecessor = manifest.get("predecessor")
    review = manifest.get("review_application")
    if not isinstance(predecessor, dict) or set(predecessor) != {
        "corpus_id",
        "manifest_content_sha256",
        "manifest_raw_sha256",
        "output_sha256s",
        "schema_version",
    }:
        raise ValueError("reviewed-v2 predecessor binding is invalid")
    if (
        predecessor.get("schema_version") != "canonical-v2-s2c-corpus-manifest-v1"
        or predecessor.get("corpus_id") != "canonical-v2-s2c-v1"
        or not all(
            isinstance(predecessor.get(field), str)
            and len(predecessor[field]) == 64
            for field in ("manifest_content_sha256", "manifest_raw_sha256")
        )
        or not isinstance(predecessor.get("output_sha256s"), dict)
        or set(predecessor["output_sha256s"]) != set(_OUTPUT_NAMES_V1)
    ):
        raise ValueError("reviewed-v2 predecessor identity is invalid")
    review_keys = {
        "artifact_identity",
        "counts",
        "evidence_class",
        "exclusion_review_bindings_sha256",
        "export_content_sha256",
        "export_id",
        "export_raw_sha256",
        "human_review_bindings_sha256",
        "judge_calibration_sha256",
        "policy_id",
        "reviewer_id",
        "round_id",
        "schema_version",
        "staff_id",
    }
    if not isinstance(review, dict) or set(review) != review_keys:
        raise ValueError("reviewed-v2 review application binding is invalid")
    if (
        review.get("schema_version")
        != "canonical-v2-reviewed-application-binding-v2"
        or review.get("evidence_class") != "real_human_round"
        or review.get("policy_id") != _GLOBAL_REVIEW_POLICY_ID
        or review.get("counts") != _GLOBAL_REVIEW_COUNTS
        or not isinstance(review.get("export_id"), str)
        or not review["export_id"]
        or not isinstance(review.get("round_id"), str)
        or not review["round_id"]
        or not isinstance(review.get("reviewer_id"), str)
        or not review["reviewer_id"].startswith("human:")
        or not isinstance(review.get("staff_id"), str)
        or not review["staff_id"]
        or any(
            not isinstance(review.get(field), str) or len(review[field]) != 64
            for field in (
                "export_content_sha256",
                "export_raw_sha256",
                "human_review_bindings_sha256",
                "exclusion_review_bindings_sha256",
                "judge_calibration_sha256",
            )
        )
    ):
        raise ValueError("reviewed-v2 export/policy/count identity is invalid")
    artifact_identity = review.get("artifact_identity")
    predecessor_outputs = predecessor["output_sha256s"]
    if not isinstance(artifact_identity, dict) or any(
        artifact_identity.get(field) != expected
        for field, expected in {
            "s2c_manifest_raw_sha256": predecessor["manifest_raw_sha256"],
            "s2c_manifest_content_sha256": predecessor[
                "manifest_content_sha256"
            ],
            "s2c_corpus_raw_sha256": predecessor_outputs[
                "claim-level-corpus-v1.jsonl"
            ],
            "s2c_accounting_raw_sha256": predecessor_outputs[
                "case-accounting-v1.jsonl"
            ],
            "s2c_snapshots_raw_sha256": predecessor_outputs[
                "source-snapshots-v1.jsonl"
            ],
        }.items()
    ):
        raise ValueError("reviewed-v2 predecessor/export identity is cross-wired")

    human_path = manifest_path.with_name("human-review-bindings-v2.jsonl")
    exclusion_path = manifest_path.with_name("exclusion-review-bindings-v2.jsonl")
    calibration_path = manifest_path.with_name("judge-calibration-v2.json")
    human = _load_jsonl(human_path, label="human review bindings")
    exclusions = _load_jsonl(exclusion_path, label="exclusion review bindings")
    calibration = _load_pretty_json(calibration_path, label="judge calibration")
    if (
        hashlib.sha256(human_path.read_bytes()).hexdigest()
        != review["human_review_bindings_sha256"]
        or hashlib.sha256(exclusion_path.read_bytes()).hexdigest()
        != review["exclusion_review_bindings_sha256"]
    ):
        raise ValueError("reviewed-v2 review binding hash mismatch")
    _verify_self_hash(calibration, field="content_sha256", label="judge calibration")
    if calibration["content_sha256"] != review["judge_calibration_sha256"]:
        raise ValueError("reviewed-v2 judge calibration binding mismatch")

    binding_keys = {
        "case_id",
        "content_sha256",
        "decision",
        "derived_contract_content_sha256",
        "event_id",
        "event_payload_sha256",
        "event_revision",
        "export_content_sha256",
        "export_id",
        "hard_requirement_ids",
        "policy_id",
        "predecessor_contract_content_sha256",
        "rationale",
        "reviewer_id",
        "round_id",
        "schema_version",
        "snapshot_ids",
        "source_case_id",
        "staff_id",
        "submitted_at",
    }

    def validate_bindings(
        rows: list[dict[str, Any]],
        *,
        schema_version: str,
        decision: str,
        accepting: bool,
    ) -> None:
        for row in rows:
            _require_exact_keys(row, binding_keys, label="review binding")
            _verify_self_hash(row, field="content_sha256", label="review binding")
            contract = contracts_by_case.get(row.get("case_id"))
            if (
                row.get("schema_version") != schema_version
                or row.get("decision") != decision
                or contract is None
                or bool(contract["acceptance_eligible"]) is not accepting
                or (
                    not accepting
                    and contract["review_state"] != "blocked_missing_evidence"
                )
                or row.get("source_case_id") != contract["source_case_id"]
                or row.get("derived_contract_content_sha256")
                != contract["content_sha256"]
                or row.get("hard_requirement_ids")
                != contract["outcome_policy"]["hard_requirement_ids"]
                or row.get("snapshot_ids")
                != [item["snapshot_id"] for item in contract["source_snapshots"]]
                or row.get("export_id") != review["export_id"]
                or row.get("export_content_sha256")
                != review["export_content_sha256"]
                or row.get("policy_id") != review["policy_id"]
                or row.get("round_id") != review["round_id"]
                or row.get("reviewer_id") != review["reviewer_id"]
                or row.get("staff_id") != review["staff_id"]
            ):
                raise ValueError("reviewed-v2 review binding identity mismatch")

    if len(human) != 29 or len(exclusions) != 23:
        raise ValueError("reviewed-v2 contract/exclusion review count mismatch")
    validate_bindings(
        human,
        schema_version="canonical-v2-human-review-binding-v2",
        decision="approved",
        accepting=True,
    )
    validate_bindings(
        exclusions,
        schema_version="canonical-v2-exclusion-review-binding-v2",
        decision="accept_exclusion",
        accepting=False,
    )
    human_ids = [row["case_id"] for row in human]
    exclusion_ids = [row["case_id"] for row in exclusions]
    _require_unique(human_ids, label="human-reviewed case IDs")
    _require_unique(exclusion_ids, label="excluded case IDs")
    if (
        set(human_ids)
        != {
            case_id
            for case_id, contract in contracts_by_case.items()
            if contract["acceptance_eligible"]
        }
        or set(exclusion_ids)
        != {
            case_id
            for case_id, contract in contracts_by_case.items()
            if contract["review_state"] == "blocked_missing_evidence"
        }
    ):
        raise ValueError("reviewed-v2 case disposition binding is incomplete")

    _validate_recomputed_calibration(calibration, review)
    return {
        "human": tuple(human),
        "exclusions": tuple(exclusions),
        "calibration": calibration,
        "review": dict(review),
    }


def _admit_artifacts(
    manifest_path: Path, expected_manifest_content_sha256: str
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    _ArtifactIdentity,
    dict[str, int],
    dict[str, Any] | None,
]:
    manifest = _load_manifest(manifest_path)
    if manifest.get("content_sha256") != expected_manifest_content_sha256:
        raise ValueError("manifest identity mismatch")
    v2 = manifest["schema_version"] == "canonical-v2-s2c-corpus-manifest-v2"
    output_names = _OUTPUT_NAMES_V2 if v2 else _OUTPUT_NAMES_V1
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(output_names):
        raise ValueError("manifest output artifact identity is incomplete")
    for name in output_names:
        path = manifest_path.with_name(name)
        identity = outputs[name]
        if not isinstance(identity, dict) or set(identity) != {"sha256"}:
            raise ValueError("manifest output identity is invalid")
        if identity["sha256"] != _file_sha256(path):
            raise ValueError(f"artifact hash mismatch: {name}")

    suffix = "v2" if v2 else "v1"
    contract_rows = _load_jsonl(
        manifest_path.with_name(f"claim-level-corpus-{suffix}.jsonl"),
        label="contract corpus",
    )
    account_rows = _load_jsonl(
        manifest_path.with_name(f"case-accounting-{suffix}.jsonl"),
        label="case accounting",
    )
    snapshot_rows = _load_jsonl(
        manifest_path.with_name(f"source-snapshots-{suffix}.jsonl"),
        label="source snapshots",
    )
    validated_contracts = _contract_module().validate_case_contracts(
        tuple(contract_rows)
    )
    validated_rows = tuple(
        contract.model_dump(mode="json") for contract in validated_contracts
    )
    if len(validated_rows) != len(contract_rows) or any(
        not _json_equal(validated, raw)
        for validated, raw in zip(validated_rows, contract_rows, strict=True)
    ):
        raise ValueError("contract validation changed artifact identity")

    contracts_by_case = {row["case_id"]: row for row in contract_rows}
    contracts_by_source = {row["source_case_id"]: row for row in contract_rows}
    accounts_by_source = {row["source_case_id"]: row for row in account_rows}
    snapshots_by_id = {row["snapshot_id"]: row for row in snapshot_rows}
    if len(contracts_by_case) != len(contract_rows) or len(contracts_by_source) != len(
        contract_rows
    ):
        raise ValueError("contract case/source identity is not unique")
    if len(accounts_by_source) != len(account_rows):
        raise ValueError("account source-case identity is not unique")
    if len(snapshots_by_id) != len(snapshot_rows):
        raise ValueError("snapshot identity is not unique")

    for account in account_rows:
        _verify_self_hash(account, field="content_sha256", label="account")
        contract = contracts_by_source.get(account["source_case_id"])
        if (
            contract is None
            or account.get("contract_case_id") != contract["case_id"]
            or account.get("contract_content_sha256") != contract["content_sha256"]
        ):
            raise ValueError("account-to-contract case mapping identity mismatch")
        evidence_ids = [
            snapshot["snapshot_id"]
            for snapshot in contract["source_snapshots"]
            if snapshot["snapshot_role"] == "claim_evidence"
        ]
        requirement_ids = [
            snapshot["snapshot_id"]
            for snapshot in contract["source_snapshots"]
            if snapshot["snapshot_role"] == "requirement_context"
        ]
        if (
            account.get("evidence_snapshot_ids") != evidence_ids
            or account.get("requirement_snapshot_ids") != requirement_ids
        ):
            raise ValueError("account snapshot mapping identity mismatch")
        expected_conversion = (
            "blocked_missing_evidence"
            if contract["review_state"] == "blocked_missing_evidence"
            else "migrated"
        )
        if (
            account.get("contract_emitted") is not True
            or account.get("review_state") != contract["review_state"]
            or account.get("acceptance_eligible") is not contract["acceptance_eligible"]
            or account.get("conversion_outcome") != expected_conversion
        ):
            raise ValueError("account contract review/disposition mapping mismatch")
        if len(requirement_ids) != 1:
            raise ValueError("account requires one source-case snapshot identity")
        source_snapshot = snapshots_by_id.get(requirement_ids[0])
        source_payload = (
            source_snapshot.get("payload")
            if isinstance(source_snapshot, dict)
            else None
        )
        if (
            not isinstance(source_payload, dict)
            or source_payload.get("case_id") != contract["source_case_id"]
            or source_payload.get("family") != account.get("family")
            or source_snapshot.get("content_sha256")
            != account.get("source_case_sha256")
            or source_snapshot.get("source_corpus_id")
            != account.get("source_corpus_id")
        ):
            raise ValueError("account family/source-case snapshot mapping mismatch")

    for snapshot in snapshot_rows:
        _validate_snapshot_record(snapshot)
    snapshot_owners: dict[str, tuple[str, str]] = {}
    for contract in contract_rows:
        for embedded in contract["source_snapshots"]:
            snapshot_id = embedded["snapshot_id"]
            if snapshot_id in snapshot_owners:
                raise ValueError("snapshot-to-contract ownership is not unique")
            expected_source_corpus_id = (
                accounts_by_source[contract["source_case_id"]]["source_corpus_id"]
                if embedded["snapshot_role"] == "requirement_context"
                else contract["corpus_id"]
            )
            snapshot_owners[snapshot_id] = (
                contract["source_case_id"],
                expected_source_corpus_id,
            )
            snapshot = snapshots_by_id.get(embedded["snapshot_id"])
            if snapshot is None or any(
                snapshot.get(field) != value for field, value in embedded.items()
            ):
                raise ValueError("contract snapshot identity mismatch")
    if set(snapshot_owners) != set(snapshots_by_id):
        raise ValueError("snapshot-to-contract ownership mapping is incomplete")
    for snapshot_id, (source_case_id, source_corpus_id) in snapshot_owners.items():
        snapshot = snapshots_by_id[snapshot_id]
        if (
            snapshot.get("source_case_id") != source_case_id
            or snapshot.get("source_corpus_id") != source_corpus_id
        ):
            raise ValueError("snapshot source-case/corpus mapping identity mismatch")

    contract_count = len(contract_rows)
    if (
        manifest.get("contract_case_count") != contract_count
        or manifest.get("source_case_count") != len(account_rows)
        or manifest.get("snapshot_count") != len(snapshot_rows)
        or set(accounts_by_source) != set(contracts_by_source)
    ):
        raise ValueError("manifest artifact count identity mismatch")
    sources = manifest.get("sources")
    if (
        not isinstance(sources, dict)
        or any(
            not isinstance(source, dict)
            or isinstance(source.get("case_count"), bool)
            or not isinstance(source.get("case_count"), int)
            or source["case_count"] < 0
            for source in sources.values()
        )
        or sum(source["case_count"] for source in sources.values())
        != manifest.get("source_case_count")
    ):
        raise ValueError("manifest source accounting count mismatch")
    source_account_counts = Counter(
        account.get("source_corpus_id") for account in account_rows
    )
    if set(source_account_counts) != set(sources) or any(
        source_account_counts[source_id] != source["case_count"]
        or any(
            account.get("source_corpus_sha256") != source.get("sha256")
            for account in account_rows
            if account.get("source_corpus_id") == source_id
        )
        for source_id, source in sources.items()
    ):
        raise ValueError("account-to-manifest source corpus mapping identity mismatch")
    if any(
        contract["schema_version"] != manifest.get("case_contract_schema_version")
        or contract["contract_version"] != manifest.get("contract_version")
        or contract["corpus_id"] != manifest.get("corpus_id")
        or contract["as_of"] != manifest.get("contract_as_of")
        for contract in contract_rows
    ):
        raise ValueError("manifest contract schema/version/as-of identity mismatch")

    review_counts = Counter(row["review_state"] for row in contract_rows)
    family_counts = Counter(row["family"] for row in account_rows)
    conversion_counts = Counter(row["conversion_outcome"] for row in account_rows)
    eligible_count = sum(bool(row["acceptance_eligible"]) for row in contract_rows)
    if (
        dict(review_counts)
        != {
            key: value
            for key, value in manifest.get("review_state_counts", {}).items()
            if value
        }
        or dict(family_counts) != manifest.get("family_counts")
        or dict(conversion_counts)
        != {
            key: value
            for key, value in manifest.get("conversion_outcome_counts", {}).items()
            if value
        }
        or eligible_count != manifest.get("acceptance_eligible_count")
    ):
        raise ValueError("manifest review/family/conversion accounting mismatch")

    artifact_identity = _ArtifactIdentity(
        case_contract_schema_version=manifest["case_contract_schema_version"],
        contract_as_of=manifest["contract_as_of"],
        contract_version=manifest["contract_version"],
        corpus_id=manifest["corpus_id"],
        manifest_content_sha256=manifest["content_sha256"],
        manifest_file_sha256=_file_sha256(manifest_path),
        manifest_schema_version=manifest["schema_version"],
        output_sha256s={name: identity["sha256"] for name, identity in outputs.items()},
        snapshot_record_sha256s={
            row["snapshot_id"]: row["record_sha256"] for row in snapshot_rows
        },
    )
    corpus_summary = {
        "blocked_missing_evidence": review_counts["blocked_missing_evidence"],
        "case_count": contract_count,
        "human_reviewed": review_counts["human_reviewed"],
        "pending_user_review": review_counts["pending_user_review"],
        "acceptance_eligible": eligible_count,
    }
    review_evidence = (
        _admit_reviewed_v2(
            manifest_path=manifest_path,
            manifest=manifest,
            contracts_by_case=contracts_by_case,
        )
        if v2
        else None
    )
    return (
        manifest,
        contracts_by_case,
        accounts_by_source,
        snapshots_by_id,
        artifact_identity,
        corpus_summary,
        review_evidence,
    )


def _validate_run_input(run_input: Mapping[str, Any]) -> None:
    schema_version = run_input.get("schema_version")
    if schema_version == "canonical-v2-oracle-run-input-v1":
        expected_keys = _RUN_INPUT_V1_KEYS
    elif schema_version == "canonical-v2-oracle-run-input-v2":
        expected_keys = _RUN_INPUT_V2_KEYS
    else:
        raise ValueError("oracle run input schema version mismatch")
    _require_exact_keys(run_input, expected_keys, label="oracle run input")
    _canonical_bytes(run_input)
    if not isinstance(run_input.get("run_id"), str) or not run_input["run_id"]:
        raise ValueError("oracle run ID is required")
    expected_sha = run_input.get("expected_manifest_content_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("expected manifest identity is invalid")
    list_fields = ["selected_case_ids"]
    if schema_version == "canonical-v2-oracle-run-input-v1":
        list_fields.extend(("exclusions", "human_reviews", "judge_calibrations"))
    for field in list_fields:
        if not isinstance(run_input.get(field), list):
            raise ValueError(f"oracle run input {field} must be a list")
    for field in ("judge_policy", "observations", "soft_metrics"):
        if not isinstance(run_input.get(field), dict):
            raise ValueError(f"oracle run input {field} must be an object")
    if set(run_input["judge_policy"]) != {"model_id", "policy_id"} or not all(
        isinstance(value, str) and value for value in run_input["judge_policy"].values()
    ):
        raise ValueError("judge policy identity is invalid")
    _require_unique(run_input["selected_case_ids"], label="selected case IDs")
    if schema_version == "canonical-v2-oracle-run-input-v2":
        binding = run_input.get("review_binding")
        if not isinstance(binding, dict):
            raise ValueError("review binding must be an object")
        _require_exact_keys(binding, _REVIEW_BINDING_KEYS, label="review binding")
        if (
            binding.get("policy_id") != _GLOBAL_REVIEW_POLICY_ID
            or binding.get("counts") != _GLOBAL_REVIEW_COUNTS
            or not isinstance(binding.get("export_id"), str)
            or not binding["export_id"]
            or any(
                not isinstance(binding.get(field), str)
                or len(binding[field]) != 64
                for field in (
                    "export_content_sha256",
                    "human_review_bindings_sha256",
                    "exclusion_review_bindings_sha256",
                    "judge_calibration_sha256",
                )
            )
        ):
            raise ValueError("review binding policy/count/identity is invalid")


def _validate_observation(observation: Mapping[str, Any]) -> None:
    _require_exact_keys(observation, _OBSERVATION_KEYS, label="case observation")
    rendered_claims = observation.get("rendered_claims")
    rendered_entities = observation.get("rendered_entity_ids")
    stage_observations = observation.get("stage_observations")
    if not isinstance(rendered_claims, list) or not all(
        isinstance(claim, dict) for claim in rendered_claims
    ):
        raise ValueError("rendered claims must be objects")
    for claim in rendered_claims:
        _require_exact_keys(claim, _RENDERED_CLAIM_KEYS, label="rendered claim")
    _require_unique(
        [str(claim["claim_id"]) for claim in rendered_claims],
        label="rendered claim IDs",
    )
    if not isinstance(rendered_entities, list) or not all(
        isinstance(entity_id, str) for entity_id in rendered_entities
    ):
        raise ValueError("rendered entity IDs must be strings")
    _require_unique(rendered_entities, label="rendered entity IDs")
    if not isinstance(stage_observations, list) or not all(
        isinstance(item, dict) for item in stage_observations
    ):
        raise ValueError("stage observations must be objects")
    for item in stage_observations:
        _require_exact_keys(item, _STAGE_OBSERVATION_KEYS, label="stage observation")
    _require_unique(
        [str(item["expectation_id"]) for item in stage_observations],
        label="stage observation IDs",
    )
    enumeration = observation.get("enumeration_report")
    if enumeration is not None and not isinstance(enumeration, dict):
        raise ValueError("enumeration report must be an object or null")


def _rendered_claim_projection(claim: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": claim["claim_id"],
        "evidence_snapshot_ids": claim["source_snapshot_ids"],
        "object_constraint": claim["object_constraint"],
        "predicate": claim["predicate"],
        "subject": claim["subject"],
    }


def _matches_allowed_variant(
    contract: Mapping[str, Any],
    requirement_id: str,
    candidate: Mapping[str, Any],
) -> bool:
    object_constraint = candidate.get("object_constraint")
    if not isinstance(object_constraint, dict) or set(object_constraint) != {
        "kind",
        "value",
    }:
        return False
    if object_constraint["kind"] != "literal":
        return False
    candidate_value = object_constraint["value"]
    return any(
        variant["claim_id"] == requirement_id
        and any(
            _json_equal(candidate_value, accepted_value)
            for accepted_value in variant["accepted_values"]
        )
        for variant in contract["allowed_variants"]
    )


def _matches_forbidden_semantics(
    candidate: Mapping[str, Any], requirement: Mapping[str, Any]
) -> bool:
    expected = _rendered_claim_projection(requirement)
    return all(
        _json_equal(candidate[field], expected[field])
        for field in (
            "object_constraint",
            "predicate",
            "subject",
        )
    )


def _stage_operator_passes(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "equals":
        return _json_equal(actual, expected)
    if operator == "contains":
        return isinstance(actual, (list, tuple)) and any(
            _json_equal(item, expected) for item in actual
        )
    if operator == "excludes":
        return isinstance(actual, (list, tuple)) and not any(
            _json_equal(item, expected) for item in actual
        )
    if operator == "one_of":
        return isinstance(expected, (list, tuple)) and any(
            _json_equal(actual, item) for item in expected
        )
    if operator == "at_least":
        return (
            not isinstance(actual, bool)
            and isinstance(actual, (int, float))
            and actual >= expected
        )
    if operator == "at_most":
        return (
            not isinstance(actual, bool)
            and isinstance(actual, (int, float))
            and actual <= expected
        )
    if operator == "exists":
        return (actual is not None) is bool(expected)
    raise ValueError(f"unknown stage operator: {operator}")


def _judge_required_claim(
    *,
    contract: Mapping[str, Any],
    requirement: Mapping[str, Any],
    candidate: Mapping[str, Any],
    snapshots_by_id: Mapping[str, Mapping[str, Any]],
    judge_policy: Mapping[str, Any],
    judge_adapter: Any,
) -> tuple[bool | None, _JudgeOutcome]:
    evidence_snapshots = [
        dict(snapshots_by_id[snapshot_id])
        for snapshot_id in requirement["source_snapshot_ids"]
    ]
    request = {
        "as_of": contract["as_of"],
        "candidate_observation": dict(candidate),
        "case_id": contract["case_id"],
        "contract_content_sha256": contract["content_sha256"],
        "evidence_snapshots": evidence_snapshots,
        "judge_policy": dict(judge_policy),
        "requirement": dict(requirement),
        "schema_version": "canonical-v2-recorded-judge-request-v1",
    }
    request_sha256 = _canonical_sha256(request)
    if judge_adapter is None or not callable(getattr(judge_adapter, "judge", None)):
        return None, _JudgeOutcome(
            requirement_id=requirement["claim_id"],
            status="unresolved",
            acceptance_usable=False,
            request_sha256=request_sha256,
        )
    submitted_request = deepcopy(request)
    try:
        response = judge_adapter.judge(submitted_request)
    except Exception:
        return None, _JudgeOutcome(
            requirement_id=requirement["claim_id"],
            status="unresolved",
            acceptance_usable=False,
            request_sha256=request_sha256,
        )
    try:
        response_sha256 = (
            _canonical_sha256(response) if isinstance(response, dict) else None
        )
    except ValueError:
        response_sha256 = None
    valid = isinstance(response, dict) and set(response) == _JUDGE_RESPONSE_KEYS
    valid = valid and _json_equal(submitted_request, request)
    valid = valid and response.get("schema_version") == (
        "canonical-v2-recorded-judge-decision-v1"
    )
    valid = valid and response.get("contract_content_sha256") == contract.get(
        "content_sha256"
    )
    valid = valid and response.get("requirement_id") == requirement.get("claim_id")
    valid = valid and response.get("request_sha256") == request_sha256
    valid = valid and response.get("evidence_snapshot_ids") == requirement.get(
        "source_snapshot_ids"
    )
    valid = valid and response.get("used_external_memory") is False
    decision = response.get("decision") if isinstance(response, dict) else None
    valid = (
        valid
        and isinstance(decision, str)
        and decision
        in (
            "supported",
            "unsupported",
        )
    )
    if not valid:
        return None, _JudgeOutcome(
            requirement_id=requirement["claim_id"],
            status="unresolved",
            acceptance_usable=False,
            request_sha256=request_sha256,
            response_sha256=response_sha256,
        )
    supported = response["decision"] == "supported"
    return supported, _JudgeOutcome(
        requirement_id=requirement["claim_id"],
        status="supported" if supported else "unsupported",
        acceptance_usable=True,
        request_sha256=request_sha256,
        response_sha256=response_sha256,
    )


def _enumeration_passes(
    policy: Mapping[str, Any], report: Mapping[str, Any] | None
) -> bool | None:
    if not policy["applicable"]:
        return True
    if report is None:
        return None
    expected_keys = {
        "claims_exhaustive",
        "continuation_required",
        "displayed",
        "eligible",
        "mode",
        "omitted",
        "scope",
        "unknown",
    }
    if set(report) != expected_keys:
        return False
    if not isinstance(report["claims_exhaustive"], bool):
        return False
    if not isinstance(report["mode"], str) or not isinstance(report["scope"], str):
        return False
    for field in ("eligible", "displayed", "omitted", "unknown"):
        value = report[field]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            return False
    if report["continuation_required"] is not None and not isinstance(
        report["continuation_required"], bool
    ):
        return False
    if report["mode"] != policy["mode"] or report["scope"] != policy["scope"]:
        return False
    if report["claims_exhaustive"] is True and policy["mode"] != "exhaustive_bounded":
        return False
    expected_coverage = policy["expected_coverage"]
    for field in (
        "eligible",
        "displayed",
        "omitted",
        "unknown",
        "continuation_required",
    ):
        expected = expected_coverage[field]
        if expected is not None and report[field] != expected:
            return False
    return True


def _evaluate_case(
    *,
    contract: Mapping[str, Any],
    observation: Mapping[str, Any],
    snapshots_by_id: Mapping[str, Mapping[str, Any]],
    judge_policy: Mapping[str, Any],
    judge_adapter: Any,
    soft_metrics: Mapping[str, Any],
) -> _CaseResult:
    _validate_observation(observation)
    rendered_claims = {
        claim["claim_id"]: claim for claim in observation["rendered_claims"]
    }
    rendered_entities = set(observation["rendered_entity_ids"])
    stage_observations = {
        item["expectation_id"]: item for item in observation["stage_observations"]
    }
    passed_by_id: dict[str, bool | None] = {}
    stage_by_id: dict[str, str] = {}
    judge_outcomes: list[_JudgeOutcome] = []

    for requirement in contract["required_claims"]:
        requirement_id = requirement["claim_id"]
        stage_by_id[requirement_id] = "rendered_answer"
        candidate = rendered_claims.get(requirement_id)
        if candidate is None:
            passed_by_id[requirement_id] = False
            continue
        expected = _rendered_claim_projection(requirement)
        if _json_equal(candidate, expected):
            passed_by_id[requirement_id] = True
            continue
        structural_fields = (
            "claim_id",
            "evidence_snapshot_ids",
            "predicate",
            "subject",
        )
        if any(
            not _json_equal(candidate[field], expected[field])
            for field in structural_fields
        ):
            passed_by_id[requirement_id] = False
            continue
        if _matches_allowed_variant(contract, requirement_id, candidate):
            passed_by_id[requirement_id] = True
            continue
        passed, judge_outcome = _judge_required_claim(
            contract=contract,
            requirement=requirement,
            candidate=candidate,
            snapshots_by_id=snapshots_by_id,
            judge_policy=judge_policy,
            judge_adapter=judge_adapter,
        )
        passed_by_id[requirement_id] = passed
        judge_outcomes.append(judge_outcome)

    for requirement in contract["forbidden_claims"]:
        requirement_id = requirement["claim_id"]
        stage_by_id[requirement_id] = "rendered_answer"
        passed_by_id[requirement_id] = not any(
            candidate["claim_id"] == requirement_id
            or _matches_forbidden_semantics(candidate, requirement)
            for candidate in rendered_claims.values()
        )
    for requirement in contract["required_entities"]:
        requirement_id = requirement["constraint_id"]
        stage_by_id[requirement_id] = "rendered_answer"
        passed_by_id[requirement_id] = requirement["entity_id"] in rendered_entities
    for requirement in contract["forbidden_entities"]:
        requirement_id = requirement["constraint_id"]
        stage_by_id[requirement_id] = "rendered_answer"
        passed_by_id[requirement_id] = requirement["entity_id"] not in rendered_entities

    declared_stage_order: list[str] = []
    stage_requirement_ids: dict[str, list[str]] = {}
    for oracle in contract["stage_oracles"]:
        stage = oracle["stage"]
        if stage not in declared_stage_order:
            declared_stage_order.append(stage)
        stage_requirement_ids.setdefault(stage, [])
        for expectation in oracle["expectations"]:
            if not expectation["hard"]:
                continue
            requirement_id = expectation["expectation_id"]
            stage_by_id[requirement_id] = stage
            stage_requirement_ids[stage].append(requirement_id)
            actual = stage_observations.get(requirement_id)
            if actual is None:
                passed_by_id[requirement_id] = None
            elif (
                actual["stage"] != stage
                or actual["observable_kind"] != expectation["observable_kind"]
            ):
                passed_by_id[requirement_id] = False
            else:
                passed_by_id[requirement_id] = _stage_operator_passes(
                    expectation["operator"],
                    actual["actual"],
                    expectation["value"],
                )

    policy = contract["enumeration_policy"]
    if policy["applicable"]:
        requirement_id = policy["obligation_id"]
        stage_by_id[requirement_id] = "rendered_answer"
        passed_by_id[requirement_id] = _enumeration_passes(
            policy, observation["enumeration_report"]
        )

    declared_ids = tuple(contract["outcome_policy"]["hard_requirement_ids"])
    if set(passed_by_id) != set(declared_ids):
        raise ValueError("evaluator hard outcome closure does not match contract")
    hard_outcomes = tuple(
        _HardOutcome(
            requirement_id=requirement_id,
            passed=passed_by_id[requirement_id],
            stage=stage_by_id[requirement_id],
        )
        for requirement_id in declared_ids
    )
    failed_ids = tuple(
        outcome.requirement_id for outcome in hard_outcomes if outcome.passed is False
    )
    unresolved_ids = tuple(
        outcome.requirement_id for outcome in hard_outcomes if outcome.passed is None
    )
    hard_passed = all(outcome.passed is True for outcome in hard_outcomes)
    first_not_passed = next(
        (outcome for outcome in hard_outcomes if outcome.passed is not True), None
    )
    localized_stage_order = list(declared_stage_order)
    for requirement_id in declared_ids:
        stage = stage_by_id[requirement_id]
        if stage not in localized_stage_order:
            localized_stage_order.append(stage)
    localized_requirement_ids = {
        stage: [
            requirement_id
            for requirement_id in declared_ids
            if stage_by_id[requirement_id] == stage
        ]
        for stage in localized_stage_order
    }
    stage_outcomes = tuple(
        _StageOutcome(
            stage=stage,
            hard_passed=all(
                passed_by_id[requirement_id] is True
                for requirement_id in localized_requirement_ids[stage]
            ),
            failed_requirement_ids=tuple(
                requirement_id
                for requirement_id in localized_requirement_ids[stage]
                if passed_by_id[requirement_id] is False
            ),
            unresolved_requirement_ids=tuple(
                requirement_id
                for requirement_id in localized_requirement_ids[stage]
                if passed_by_id[requirement_id] is None
            ),
        )
        for stage in localized_stage_order
    )
    normalized_soft_metrics: dict[str, float] = {}
    for key, value in soft_metrics.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("soft metrics must be finite numbers")
        normalized_soft_metrics[str(key)] = float(value)
    return _CaseResult(
        case_id=contract["case_id"],
        contract_content_sha256=contract["content_sha256"],
        hard_outcomes=hard_outcomes,
        stage_outcomes=stage_outcomes,
        judge_outcomes=tuple(judge_outcomes),
        failed_requirement_ids=failed_ids,
        unresolved_requirement_ids=unresolved_ids,
        hard_passed=hard_passed,
        failure_stage=None if first_not_passed is None else first_not_passed.stage,
        acceptance_eligible=bool(contract["acceptance_eligible"]),
        soft_metrics=normalized_soft_metrics,
    )


def _review_is_valid(
    review: Any,
    *,
    contract: Mapping[str, Any],
    account: Mapping[str, Any],
) -> bool:
    expected_keys = {
        "case_id",
        "contract_content_sha256",
        "family",
        "review_state",
        "reviewed_hard_requirement_ids",
        "reviewer_id",
        "reviewer_kind",
        "snapshot_ids",
    }
    return (
        isinstance(review, dict)
        and set(review) == expected_keys
        and review["case_id"] == contract["case_id"]
        and review["contract_content_sha256"] == contract["content_sha256"]
        and review["family"] == account["family"]
        and review["review_state"] == "approved"
        and review["reviewer_kind"] == "human"
        and isinstance(review["reviewer_id"], str)
        and review["reviewer_id"].startswith("human:")
        and review["reviewed_hard_requirement_ids"]
        == contract["outcome_policy"]["hard_requirement_ids"]
        and review["snapshot_ids"]
        == [snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]]
    )


def _calibration_is_valid(
    calibration: Any,
    *,
    family: str,
    judge_policy: Mapping[str, Any],
    case_reviewer_id: str,
) -> bool:
    expected_keys = {
        "agreement",
        "double_reviewed_samples",
        "family",
        "model_id",
        "policy_id",
        "reviewer_ids",
    }
    if not isinstance(calibration, dict) or set(calibration) != expected_keys:
        return False
    reviewer_ids = calibration["reviewer_ids"]
    return (
        calibration["family"] == family
        and calibration["model_id"] == judge_policy.get("model_id")
        and calibration["policy_id"] == judge_policy.get("policy_id")
        and isinstance(calibration["double_reviewed_samples"], int)
        and not isinstance(calibration["double_reviewed_samples"], bool)
        and calibration["double_reviewed_samples"] >= 50
        and isinstance(calibration["agreement"], (int, float))
        and not isinstance(calibration["agreement"], bool)
        and math.isfinite(float(calibration["agreement"]))
        and calibration["agreement"] >= 0.80
        and isinstance(reviewer_ids, list)
        and len(reviewer_ids) >= 2
        and all(
            isinstance(reviewer_id, str) and reviewer_id.startswith("human:")
            for reviewer_id in reviewer_ids
        )
        and len(reviewer_ids) == len(set(reviewer_ids))
        and case_reviewer_id in reviewer_ids
    )


def _acceptance_record(
    *,
    manifest: Mapping[str, Any],
    artifact_identity: _ArtifactIdentity,
    case_results: tuple[_CaseResult, ...],
    human_reviews: list[dict[str, Any]],
    calibrations: list[dict[str, Any]],
) -> _AcceptanceRecord:
    accepted_case_ids = tuple(result.case_id for result in case_results)
    hard_outcome_sha256s = {
        result.case_id: _canonical_sha256(
            [outcome.model_dump(mode="json") for outcome in result.hard_outcomes]
        )
        for result in case_results
    }
    draft = _AcceptanceRecord(
        artifact_identity=artifact_identity,
        accepted_case_ids=accepted_case_ids,
        excluded_case_ids=(),
        case_count=len(accepted_case_ids),
        human_review_count=len(human_reviews),
        excluded_case_count=0,
        human_review_sha256s=tuple(
            _canonical_sha256(review) for review in human_reviews
        ),
        judge_calibration_sha256s=tuple(
            _canonical_sha256(calibration) for calibration in calibrations
        ),
        exclusion_sha256s=(),
        hard_outcome_sha256s=hard_outcome_sha256s,
        reviewer_states={
            review["reviewer_id"]: review["review_state"] for review in human_reviews
        },
        synthetic_fixture=manifest.get("synthetic_fixture") is True,
        content_sha256="0" * 64,
    )
    payload = draft.model_dump(mode="json", exclude={"content_sha256"})
    return draft.model_copy(update={"content_sha256": _canonical_sha256(payload)})


def _try_accept(
    *,
    manifest: Mapping[str, Any],
    contracts_by_case: Mapping[str, Mapping[str, Any]],
    accounts_by_source: Mapping[str, Mapping[str, Any]],
    artifact_identity: _ArtifactIdentity,
    case_results: tuple[_CaseResult, ...],
    run_input: Mapping[str, Any],
) -> _AcceptanceRecord | None:
    if manifest.get("synthetic_fixture") is not True or len(contracts_by_case) != 1:
        return None
    eligible_contracts = tuple(
        contract
        for contract in contracts_by_case.values()
        if contract["acceptance_eligible"]
    )
    if not eligible_contracts or run_input["exclusions"]:
        return None
    eligible_ids = tuple(contract["case_id"] for contract in eligible_contracts)
    if tuple(run_input["selected_case_ids"]) != eligible_ids:
        return None
    results_by_case = {result.case_id: result for result in case_results}
    if set(results_by_case) != set(eligible_ids) or any(
        not results_by_case[case_id].hard_passed for case_id in eligible_ids
    ):
        return None

    raw_reviews = run_input["human_reviews"]
    if len(raw_reviews) != len(eligible_contracts) or not all(
        isinstance(review, dict) for review in raw_reviews
    ):
        return None
    if any(not isinstance(review.get("case_id"), str) for review in raw_reviews):
        return None
    reviews_by_case = {review.get("case_id"): review for review in raw_reviews}
    if set(reviews_by_case) != set(eligible_ids):
        return None
    for contract in eligible_contracts:
        account = accounts_by_source[contract["source_case_id"]]
        if not _review_is_valid(
            reviews_by_case[contract["case_id"]],
            contract=contract,
            account=account,
        ):
            return None

    families = tuple(
        dict.fromkeys(
            accounts_by_source[contract["source_case_id"]]["family"]
            for contract in eligible_contracts
        )
    )
    raw_calibrations = run_input["judge_calibrations"]
    if len(raw_calibrations) != len(families) or not all(
        isinstance(calibration, dict) for calibration in raw_calibrations
    ):
        return None
    if any(
        not isinstance(calibration.get("family"), str)
        for calibration in raw_calibrations
    ):
        return None
    calibrations_by_family = {
        calibration.get("family"): calibration for calibration in raw_calibrations
    }
    if set(calibrations_by_family) != set(families):
        return None
    for family in families:
        family_contract = next(
            contract
            for contract in eligible_contracts
            if accounts_by_source[contract["source_case_id"]]["family"] == family
        )
        review = reviews_by_case[family_contract["case_id"]]
        if not _calibration_is_valid(
            calibrations_by_family[family],
            family=family,
            judge_policy=run_input["judge_policy"],
            case_reviewer_id=review["reviewer_id"],
        ):
            return None
    if any(
        not outcome.acceptance_usable
        for result in case_results
        for outcome in result.judge_outcomes
    ):
        return None
    return _acceptance_record(
        manifest=manifest,
        artifact_identity=artifact_identity,
        case_results=case_results,
        human_reviews=raw_reviews,
        calibrations=raw_calibrations,
    )


def _bind_reviewed_v2_run(
    *,
    manifest: Mapping[str, Any],
    contracts_by_case: Mapping[str, Mapping[str, Any]],
    run_input: Mapping[str, Any],
    review_evidence: Mapping[str, Any] | None,
) -> None:
    manifest_is_v2 = (
        manifest.get("schema_version") == "canonical-v2-s2c-corpus-manifest-v2"
    )
    input_is_v2 = run_input.get("schema_version") == "canonical-v2-oracle-run-input-v2"
    if manifest_is_v2 != input_is_v2:
        raise ValueError("manifest/run-input version binding mismatch")
    if not manifest_is_v2:
        return
    if review_evidence is None:
        raise ValueError("reviewed-v2 evidence binding is unavailable")
    review = review_evidence["review"]
    expected_binding = {
        "export_id": review["export_id"],
        "export_content_sha256": review["export_content_sha256"],
        "policy_id": review["policy_id"],
        "counts": review["counts"],
        "human_review_bindings_sha256": review[
            "human_review_bindings_sha256"
        ],
        "exclusion_review_bindings_sha256": review[
            "exclusion_review_bindings_sha256"
        ],
        "judge_calibration_sha256": review["judge_calibration_sha256"],
    }
    if run_input.get("review_binding") != expected_binding:
        raise ValueError("reviewed-v2 run-input review binding identity mismatch")
    calibration = review_evidence["calibration"]
    calibration_summary = calibration["judge"]["summary"]
    calibrated_judge = {
        "model_id": calibration_summary["model_id"],
        "policy_id": calibration_summary["judge_policy_id"],
    }
    if run_input.get("judge_policy") != calibrated_judge:
        raise ValueError("reviewed-v2 calibrated judge identity mismatch")
    eligible_ids = tuple(
        case_id
        for case_id, contract in contracts_by_case.items()
        if contract["acceptance_eligible"]
    )
    if tuple(run_input["selected_case_ids"]) != eligible_ids:
        raise ValueError("reviewed-v2 run must select exactly all reviewed contracts")


def _try_accept_reviewed_v2(
    *,
    contracts_by_case: Mapping[str, Mapping[str, Any]],
    artifact_identity: _ArtifactIdentity,
    case_results: tuple[_CaseResult, ...],
    review_evidence: Mapping[str, Any],
) -> _ReviewedAcceptanceRecord | None:
    eligible_ids = tuple(
        case_id
        for case_id, contract in contracts_by_case.items()
        if contract["acceptance_eligible"]
    )
    results_by_case = {result.case_id: result for result in case_results}
    if (
        tuple(result.case_id for result in case_results) != eligible_ids
        or any(not results_by_case[case_id].hard_passed for case_id in eligible_ids)
        or any(
            not outcome.acceptance_usable
            for result in case_results
            for outcome in result.judge_outcomes
        )
    ):
        return None
    human = review_evidence["human"]
    exclusions = review_evidence["exclusions"]
    calibration = review_evidence["calibration"]
    review = review_evidence["review"]
    excluded_ids = tuple(row["case_id"] for row in exclusions)
    hard_outcome_sha256s = {
        result.case_id: _canonical_sha256(
            [outcome.model_dump(mode="json") for outcome in result.hard_outcomes]
        )
        for result in case_results
    }
    draft = _ReviewedAcceptanceRecord(
        artifact_identity=artifact_identity,
        accepted_case_ids=eligible_ids,
        excluded_case_ids=excluded_ids,
        case_count=len(eligible_ids),
        human_review_count=len(human),
        excluded_case_count=len(exclusions),
        calibration_probe_count=len(calibration["calibration_labels"]),
        human_review_bindings_sha256=review[
            "human_review_bindings_sha256"
        ],
        exclusion_review_bindings_sha256=review[
            "exclusion_review_bindings_sha256"
        ],
        judge_calibration_sha256=review["judge_calibration_sha256"],
        hard_outcome_sha256s=hard_outcome_sha256s,
        reviewer_states={review["reviewer_id"]: "approved"},
        review_export_id=review["export_id"],
        review_export_content_sha256=review["export_content_sha256"],
        review_policy_id=review["policy_id"],
        synthetic_fixture=False,
        content_sha256="0" * 64,
    )
    return draft.model_copy(
        update={
            "content_sha256": _canonical_sha256(
                draft.model_dump(mode="json", exclude={"content_sha256"})
            )
        }
    )


def evaluate_oracle_run(
    manifest_path: str | Path,
    run_input: Mapping[str, Any],
    *,
    judge_adapter: Any = None,
) -> _EvaluationResult:
    """Evaluate one content-bound run without mutating corpus or external state."""

    if not isinstance(run_input, Mapping):
        raise ValueError("oracle run input must be an object")
    _validate_run_input(run_input)
    path = Path(manifest_path).resolve()
    (
        manifest,
        contracts_by_case,
        accounts_by_source,
        snapshots_by_id,
        artifact_identity,
        corpus_summary,
        review_evidence,
    ) = _admit_artifacts(path, run_input["expected_manifest_content_sha256"])

    _bind_reviewed_v2_run(
        manifest=manifest,
        contracts_by_case=contracts_by_case,
        run_input=run_input,
        review_evidence=review_evidence,
    )

    selected_ids = tuple(run_input["selected_case_ids"])
    if any(case_id not in contracts_by_case for case_id in selected_ids):
        raise ValueError("selected case identity is unknown")
    if set(run_input["observations"]) != set(selected_ids):
        raise ValueError("selected case observation identity mismatch")
    if set(run_input["soft_metrics"]) != set(selected_ids):
        raise ValueError("selected case soft-metric identity mismatch")
    case_results = tuple(
        _evaluate_case(
            contract=contracts_by_case[case_id],
            observation=run_input["observations"][case_id],
            snapshots_by_id=snapshots_by_id,
            judge_policy=run_input["judge_policy"],
            judge_adapter=judge_adapter,
            soft_metrics=run_input["soft_metrics"][case_id],
        )
        for case_id in selected_ids
    )
    if review_evidence is None:
        record = _try_accept(
            manifest=manifest,
            contracts_by_case=contracts_by_case,
            accounts_by_source=accounts_by_source,
            artifact_identity=artifact_identity,
            case_results=case_results,
            run_input=run_input,
        )
    else:
        record = _try_accept_reviewed_v2(
            contracts_by_case=contracts_by_case,
            artifact_identity=artifact_identity,
            case_results=case_results,
            review_evidence=review_evidence,
        )
    return _EvaluationResult(
        artifact_identity=artifact_identity,
        corpus_summary=corpus_summary,
        case_results=case_results,
        acceptance_ready=record is not None,
        acceptance_record=record,
    )
