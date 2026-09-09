"""Artifact-bound, SQLite-only workspace for attributable human review."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Any, Annotated, Literal, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
)


__all__ = (
    "DraftData",
    "CalibrationGateStatus",
    "CalibrationJudgment",
    "CalibrationSummary",
    "EvidenceClass",
    "ExportMode",
    "ExportDownload",
    "ExportReceipt",
    "ExportReview",
    "ReadExport",
    "AbandonInFlightJudgeRun",
    "JudgeRunRecoveryReceipt",
    "EvidenceBoundedJudge",
    "ExclusionReviewContext",
    "JudgeAuthorization",
    "JudgeAuthorizationProvider",
    "OpenAICompatibleEvidenceBoundedJudge",
    "OpenWorkspace",
    "ReviewerView",
    "ReviewCounts",
    "ReviewCoverage",
    "ReviewDecisionView",
    "ReviewErrorCode",
    "ReviewProgress",
    "ReviewGateSummary",
    "ReviewTaskSummary",
    "ReviewTaskView",
    "ReviewCommand",
    "ReviewWorkspace",
    "ReviewWorkspaceError",
    "SaveDraft",
    "SealCalibration",
    "SubmitDecision",
    "TaskKind",
    "SealedWorkspaceView",
    "WorkspaceView",
    "WorkspaceArtifactIdentity",
    "create_review_workspace",
)


_SCHEMA_VERSION = "canonical-v2-review-workspace-sqlite-v10"
_DATABASE_NAME = "review-workbench.sqlite3"
_PACKET_SCHEMA = "canonical-v2-human-review-packet-v1"
_WORKLOAD_SCHEMA = "canonical-v2-human-review-workload-v2"
_POLICY_SCHEMA = "canonical-v2-human-calibration-policy-v2"
_PROVENANCE_SCHEMA = "canonical-v2-calibration-provenance-v1"
_REQUEST_SCHEMA = "canonical-v2-human-calibration-request-v2"
_STIMULUS_SCHEMA = "canonical-v2-human-calibration-stimulus-v1"
_STIMULUS_SET_SCHEMA = "canonical-v2-human-calibration-stimulus-set-v1"
_JUDGE_RESPONSE_SCHEMA = "canonical-v2-human-calibration-judge-decision-v2"
_RENDERER_SCHEMA = "canonical-v2-human-review-renderer-v2"
_RENDERER_DIR = Path(__file__).resolve().parent.parent / "static"
_RENDERER_FILES = (
    "review.html",
    "review.css",
    "review.js",
    "review_mutation_coordinator.js",
    "review_presentation.js",
)
_CALIBRATION_POLICY_ID = "single-human-global-stratified-v2"
_JUDGE_POLICY_ID = "evidence-bounded-judge-v1"
_JUDGE_RUN_WAIT_SECONDS = 10.0
_JUDGE_RUN_POLL_SECONDS = 0.01
_S2C_CONTEXT_ROOT = Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c")
_S2C_CONTEXT_FILES = {
    "contracts": _S2C_CONTEXT_ROOT / "claim-level-corpus-v1.jsonl",
    "accounting": _S2C_CONTEXT_ROOT / "case-accounting-v1.jsonl",
    "snapshots": _S2C_CONTEXT_ROOT / "source-snapshots-v1.jsonl",
    "manifest": _S2C_CONTEXT_ROOT / "claim-level-corpus-manifest-v1.json",
}
_S2C_MANIFEST_SCHEMA = "canonical-v2-s2c-corpus-manifest-v1"
_STAFF_ID = re.compile(r"^[a-z0-9._-]{2,64}$", flags=re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_RUNTIME_INSTANCE_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", flags=re.ASCII
)
_FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "expected_label",
        "gold_label",
        "ground_truth",
        "human_label",
        "judge_decision",
        "model_judgment",
        "oracle_label",
    }
)
_EXPECTED_COUNTS = {
    "contract_reviews": 29,
    "exclusion_reviews": 23,
    "calibration_probes": 60,
    "human_actions": 112,
}
_EXPECTED_STRATA = {
    "claim_evidence": 20,
    "context_relationship": 10,
    "identity_entity": 10,
    "insufficiency_assessment": 10,
    "safety_web": 10,
}
_EXPECTED_REQUIREMENT_KINDS = {
    "claim_evidence": "claim_entailment",
    "context_relationship": "relationship_or_context",
    "identity_entity": "identity_consistency",
    "insufficiency_assessment": "evidence_sufficiency",
    "safety_web": "safety_or_web_policy",
}
_EXPECTED_ARTIFACT_IDENTITIES = {
    "packet": (
        "222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e",
        "d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb",
    ),
    "workload": (
        "0e0e5bbc1a101d4a21fc99c523b59ad81a344420d13fc57d5f11000570e8f494",
        "89b027058e8f66864edfd6c3a2ccc0be3f006a51432e17eaa0a6e504d7baa456",
    ),
    "policy": (
        "9900ea9a6cb20c928fb07f9c38f43b4bc0d6f42efad0978aab6a341cfa3b92c5",
        "cb569bc6f2b094a4b541d80f6e0b76c3143ff8b0fad007bf18dee633f61d1f75",
    ),
    "bank": (
        "3a0fdc42202b052d79cb04853ed7fc8ae98b701b685ed30f920c5f2b7b4257cd",
        "ff97cae3f0df349567d74585e22750d8f8f80d87069787f5e383bbc0fdd41eaf",
    ),
    "provenance": (
        "1a806bc6e99d1fcf219338f1007feb5963ef35e60de200fa3246a8e2baa0fa80",
        "3fea1e29ca388c0eab17d30844a034c1db3a7fd97d1faea0501acabb995f5f6b",
    ),
}
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:\bapi[_ -]?key\b|\bcredential\b|\bpassword\b|"
    r"\bauthorization\b|\bbearer\s+|\bsk-[a-z0-9_-]{6,}|"
    r"(?:postgres(?:ql)?|mysql)://[^\s]+@)"
)
_EXPECTED_STORAGE_ERRORS = (
    json.JSONDecodeError,
    sqlite3.Error,
    UnicodeDecodeError,
    ValidationError,
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskKind(StrEnum):
    CONTRACT = "contract"
    EXCLUSION = "exclusion"
    CALIBRATION = "calibration"


class EvidenceClass(StrEnum):
    IMPLEMENTATION_TEST = "implementation_test"
    REAL_HUMAN_ROUND = "real_human_round"


_ACCEPTING_DECISIONS: dict[TaskKind, frozenset[str]] = {
    TaskKind.CONTRACT: frozenset({"approved"}),
    TaskKind.EXCLUSION: frozenset({"accept_exclusion"}),
    TaskKind.CALIBRATION: frozenset({"supported", "unsupported"}),
}


class ExportMode(StrEnum):
    REVIEW_EVIDENCE = "review_evidence"
    ACCEPTANCE_CANDIDATE = "acceptance_candidate"


class ReviewErrorCode(StrEnum):
    ARTIFACT_MISMATCH = "artifact_mismatch"
    INVALID_REVIEWER = "invalid_reviewer"
    INVALID_SESSION = "invalid_session"
    UNKNOWN_TASK = "unknown_task"
    STALE_REVISION = "stale_revision"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_DECISION = "invalid_decision"
    INVALID_COMMAND = "invalid_command"
    JUDGE_UNAVAILABLE = "judge_unavailable"
    JUDGE_RECOVERY_REQUIRED = "judge_recovery_required"
    CALIBRATION_NOT_SEALED = "calibration_not_sealed"
    EXPORT_BLOCKED = "export_blocked"
    STORAGE_FAILURE = "storage_failure"


_ERROR_MESSAGES = {
    ReviewErrorCode.ARTIFACT_MISMATCH: "review artifacts failed admission",
    ReviewErrorCode.INVALID_REVIEWER: "reviewer identity is invalid",
    ReviewErrorCode.INVALID_SESSION: "review session is invalid",
    ReviewErrorCode.UNKNOWN_TASK: "review task is unknown",
    ReviewErrorCode.STALE_REVISION: "review task revision is stale",
    ReviewErrorCode.IDEMPOTENCY_CONFLICT: "idempotency key conflicts",
    ReviewErrorCode.INVALID_DECISION: "review decision is invalid",
    ReviewErrorCode.INVALID_COMMAND: "review command is invalid",
    ReviewErrorCode.JUDGE_UNAVAILABLE: "review judge is unavailable",
    ReviewErrorCode.JUDGE_RECOVERY_REQUIRED: "a prior judge run requires recovery",
    ReviewErrorCode.CALIBRATION_NOT_SEALED: "calibration is not sealed",
    ReviewErrorCode.EXPORT_BLOCKED: "review export is blocked",
    ReviewErrorCode.STORAGE_FAILURE: "review storage operation failed",
}


class ReviewWorkspaceError(Exception):
    """Stable public failure without filesystem or storage implementation details."""

    def __init__(
        self,
        code: ReviewErrorCode,
        *,
        reason: str | None = None,
        current_revision: int | None = None,
    ) -> None:
        self.code = code
        self.reason = reason
        self.current_revision = current_revision
        super().__init__(f"{code.value}: {_ERROR_MESSAGES[code]}")


class OpenWorkspace(_FrozenModel):
    display_name: str | None = None
    staff_id: str | None = None
    session_token: str | None = None
    task_id: str | None = None


class DraftData(_FrozenModel):
    decision: str | None = Field(default=None, max_length=64)
    rationale: str = Field(default="", max_length=10_000)


class SaveDraft(_FrozenModel):
    action: Literal["draft"] = "draft"
    session_token: str
    task_id: str
    draft: DraftData


class SubmitDecision(_FrozenModel):
    action: Literal["decision"] = "decision"
    session_token: str
    task_id: str
    task_kind: TaskKind
    decision: str = Field(min_length=1, max_length=64)
    rationale: str | None = Field(default=None, max_length=10_000)
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class SealCalibration(_FrozenModel):
    action: Literal["seal_calibration"] = "seal_calibration"
    session_token: str
    expected_revision: Literal[60]
    idempotency_key: str = Field(min_length=1, max_length=128)


ReviewCommand: TypeAlias = Annotated[
    SaveDraft | SubmitDecision | SealCalibration, Field(discriminator="action")
]


class EvidenceBoundedJudge(Protocol):
    model_id: str
    provider_profile: str

    def judge(self, request: dict[str, Any]) -> dict[str, Any]: ...


class JudgeAuthorization(_FrozenModel):
    schema_version: Literal["judge-authorization-v2"]
    evidence_class: EvidenceClass
    round_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    authorizer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    provider_profile: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
    calibration_policy_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    judge_policy_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    workload_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_at: datetime
    evidence_scope: Literal["supplied_request_only"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("model_id")
    @classmethod
    def _model_id_is_opaque(cls, value: str) -> str:
        if "://" in value or _SENSITIVE_TEXT.search(value):
            raise ValueError("model_id must be an opaque identifier")
        return value


class JudgeAuthorizationProvider(Protocol):
    @property
    def is_real_authorization_provider(self) -> bool: ...

    def authorize(
        self,
        *,
        round_id: str,
        workload_content_sha256: str,
        evidence_class: EvidenceClass,
    ) -> JudgeAuthorization: ...


class OpenAICompatibleEvidenceBoundedJudge:
    """OpenAI-compatible evidence-bounded judge with an injected client."""

    def __init__(self, *, client: Any, model_id: str, provider_profile: str) -> None:
        self._client = client
        self.model_id = model_id
        self.provider_profile = provider_profile

    def judge(self, request: dict[str, Any]) -> dict[str, Any]:
        canonical_request = _canonical_bytes(request).decode("utf-8")
        response = self._client.chat.completions.create(
            model=self.model_id,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Judge only the supplied request and evidence. Return one JSON "
                        "object with exactly: schema_version, model_id, policy_id, "
                        "request_sha256, decision, evidence_scope, used_external_memory. "
                        f"schema_version must be {_JUDGE_RESPONSE_SCHEMA}. "
                        "decision must be supported or unsupported; evidence_scope must "
                        "be supplied_request_only; used_external_memory must be false; "
                        f"policy_id must be {_JUDGE_POLICY_ID}."
                    ),
                },
                {"role": "user", "content": canonical_request},
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("judge response content must be JSON text")
        value = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(value, dict):
            raise ValueError("judge response must be an object")
        return _JudgeResponse.model_validate(value).model_dump(mode="json")


class ExportReview(_FrozenModel):
    session_token: str
    mode: ExportMode
    idempotency_key: str = Field(default="legacy-export", min_length=1, max_length=128)


class ReadExport(_FrozenModel):
    session_token: str
    export_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ExportDownload(_FrozenModel):
    receipt: "ExportReceipt"
    content: bytes


class AbandonInFlightJudgeRun(_FrozenModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    round_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    command_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_staff_id: str = Field(pattern=r"^[a-z0-9._-]{2,64}$")
    reason: Literal["process_crash_confirmed"] = "process_crash_confirmed"


class JudgeRunRecoveryReceipt(_FrozenModel):
    recovery_id: str
    run_id: str
    round_id: str
    command_sha256: str
    human_snapshot_sha256: str
    authorization_sha256: str
    operator_staff_id: str
    reason: Literal["process_crash_confirmed"]
    recovered_at: datetime


class ExportReceipt(_FrozenModel):
    export_id: str
    round_id: str
    mode: ExportMode
    evidence_class: EvidenceClass
    acceptance_eligible: bool
    task_2_8_eligible: bool
    basename: str
    raw_sha256: str
    content_sha256: str
    content_length: int
    created_at: datetime


class ReviewCounts(_FrozenModel):
    contract_reviews: int
    exclusion_reviews: int
    calibration_probes: int
    human_actions: int


class ReviewerView(_FrozenModel):
    reviewer_id: str
    display_name: str
    staff_id: str


class ReviewDecisionView(_FrozenModel):
    event_id: str
    reviewer_id: str
    staff_id: str
    decision: str
    rationale: str | None
    revision: int
    supersedes_event_id: str | None
    submitted_at: datetime
    payload_sha256: str


class WorkspaceArtifactIdentity(_FrozenModel):
    packet_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    packet_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workload_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workload_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bank_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bank_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    s2c_manifest_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    s2c_manifest_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    s2c_corpus_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    s2c_accounting_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    s2c_snapshots_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_stimulus_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_schema_version: Literal["canonical-v2-human-review-renderer-v2"]
    review_html_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_css_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_js_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_mutation_coordinator_js_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_presentation_js_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewOnlyMarker(_FrozenModel):
    role: Literal["review_only"] = "review_only"
    normative: Literal[False] = False


class ReviewOnlyReferenceProse(ReviewOnlyMarker):
    content: str
    key_points: str | None


class ExclusionReviewContext(_FrozenModel):
    query: str
    as_of: str
    contract: dict[str, JsonValue]
    accounting: dict[str, JsonValue]
    requirement_snapshots: tuple[dict[str, JsonValue], ...]
    reference_prose: ReviewOnlyReferenceProse
    requirement_snapshot_use: ReviewOnlyMarker


class ReviewTaskView(_FrozenModel):
    task_id: str
    kind: TaskKind
    payload: dict[str, JsonValue]
    draft: DraftData | None
    current_decision: ReviewDecisionView | None
    revision: int
    review_context: ExclusionReviewContext | None = None
    mutable: bool
    read_only_reason: (
        Literal[
            "round_locked",
            "calibration_labels_sealed",
            "round_not_mutable",
        ]
        | None
    )


class RevealedReviewTaskView(ReviewTaskView):
    model_judgment: Literal["supported", "unsupported"]
    judge_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewTaskSummary(_FrozenModel):
    task_id: str
    kind: TaskKind
    position: int
    status: Literal["pending", "submitted"]
    revision: int
    current_decision: str | None


class ReviewProgress(_FrozenModel):
    total: int
    submitted: int
    remaining: int
    contract_submitted: int
    exclusion_submitted: int
    calibration_submitted: int
    current_position: int | None


class ReviewCoverage(_FrozenModel):
    total: int = Field(ge=0)
    submitted: int = Field(ge=0)
    accepting: int = Field(ge=0)
    blocking: int = Field(ge=0)
    missing: int = Field(ge=0)


AcceptanceBlocker: TypeAlias = Literal[
    "human_decisions_missing",
    "human_decisions_blocking",
    "calibration_not_sealed",
    "calibration_failed",
    "round_locked",
]


class ReviewGateSummary(_FrozenModel):
    missing_task_ids: tuple[str, ...]
    blocking_task_ids: tuple[str, ...]
    blocking_reasons: dict[str, str]
    family_coverage: dict[str, ReviewCoverage]
    stratum_coverage: dict[str, ReviewCoverage]
    calibration_labels_valid: bool
    calibration_ready_to_seal: bool
    acceptance_ready: bool
    acceptance_blockers: tuple[AcceptanceBlocker, ...]


class WorkspaceView(_FrozenModel):
    round_id: str
    evidence_class: EvidenceClass
    reviewer: ReviewerView
    session_token: str | None = None
    counts: ReviewCounts
    progress: ReviewProgress
    queue: tuple[ReviewTaskSummary, ...]
    task: ReviewTaskView | None
    lifecycle: Literal[
        "in_progress",
        "calibration_failed_sealed",
        "human_labels_sealed",
        "review_complete_blocked",
        "acceptance_ready",
        "locked",
    ]
    artifact_identity: WorkspaceArtifactIdentity
    judge_configured: bool
    gate_summary: ReviewGateSummary


class CalibrationJudgment(_FrozenModel):
    task_id: str
    sample_id: str
    stratum: str
    critical_probe: bool
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_decision: Literal["supported", "unsupported"]
    model_decision: Literal["supported", "unsupported"]


class CalibrationGateStatus(_FrozenModel):
    exact_pair_count: bool
    exact_stratum_quotas: bool
    minimum_agreement: bool
    minimum_supported_labels: bool
    minimum_unsupported_labels: bool
    minimum_unsupported_critical_probes: bool
    maximum_critical_false_accepts: bool


class CalibrationSummary(_FrozenModel):
    evidence_class: EvidenceClass
    pair_count: int
    stratum_counts: dict[str, int]
    human_supported: int
    human_unsupported: int
    agreement: float
    confusion_matrix: dict[str, int]
    unsupported_critical_probes: int
    critical_false_accepts: int
    gates: CalibrationGateStatus
    passed: bool
    model_id: str
    calibration_policy_id: str
    judge_policy_id: str
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judgments: tuple[CalibrationJudgment, ...]


class SealedWorkspaceView(WorkspaceView):
    calibration: CalibrationSummary
    task: ReviewTaskView | RevealedReviewTaskView | None


class _JudgeResponse(_FrozenModel):
    schema_version: Literal["canonical-v2-human-calibration-judge-decision-v2"]
    model_id: str
    policy_id: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["supported", "unsupported"]
    evidence_scope: Literal["supplied_request_only"]
    used_external_memory: Literal[False]


@dataclass(frozen=True, slots=True)
class _Task:
    task_id: str
    kind: TaskKind
    payload: dict[str, JsonValue]
    review_context: ExclusionReviewContext | None = None
    audit_payload: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class _Artifacts:
    tasks: tuple[_Task, ...]
    counts: ReviewCounts
    identity: dict[str, JsonValue]
    header_identity: WorkspaceArtifactIdentity
    watched_sha256s: tuple[tuple[Path, str], ...]


@dataclass(frozen=True, slots=True)
class _JudgedTask:
    task: _Task
    human_decision: Literal["supported", "unsupported"]
    response: _JudgeResponse
    response_json: str
    response_sha256: str
    judged_at: str


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


def _validated_judge_response(
    response_json: str, response_sha256: str
) -> _JudgeResponse:
    if not isinstance(response_json, str) or not isinstance(response_sha256, str):
        raise ValueError("judge response encoding")
    if hashlib.sha256(response_json.encode("utf-8")).hexdigest() != response_sha256:
        raise ValueError("judge response identity")
    value = json.loads(response_json, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError("judge response object")
    if _canonical_bytes(value).decode("utf-8") != response_json:
        raise ValueError("judge response is not canonical")
    response = _JudgeResponse.model_validate(value)
    if (
        _canonical_bytes(response.model_dump(mode="json")).decode("utf-8")
        != response_json
    ):
        raise ValueError("judge response schema projection")
    return response


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


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict) or raw != _pretty_bytes(value):
        raise ValueError("non-canonical JSON artifact")
    return value


def _load_canonical_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            raise ValueError("empty JSONL row")
        value = json.loads(
            line.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
        if not isinstance(value, dict):
            raise ValueError("JSONL row is not an object")
        rows.append(value)
    expected = b"".join(_canonical_bytes(row) + b"\n" for row in rows)
    if raw != expected:
        raise ValueError("non-canonical JSONL artifact")
    return rows


def _without_content_sha256(value: dict[str, Any]) -> dict[str, Any]:
    return {key: child for key, child in value.items() if key != "content_sha256"}


def _require_self_hash(value: dict[str, Any]) -> str:
    claimed = value.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
        raise ValueError("missing content identity")
    if claimed != _canonical_sha256(_without_content_sha256(value)):
        raise ValueError("content identity mismatch")
    return claimed


def _walk_forbidden_labels(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_LABEL_KEYS:
                raise ValueError("prefilled review label")
            _walk_forbidden_labels(child)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden_labels(child)


def _safe_source_path(source_root: Path, relative: str) -> Path:
    root = source_root.resolve(strict=True)
    candidate = (root / relative).resolve(strict=True)
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        raise ValueError("source identity escapes root")
    return candidate


def _audit_projection(row: dict[str, Any]) -> dict[str, Any]:
    requirement = row.get("requirement")
    if not isinstance(requirement, dict):
        raise ValueError("invalid requirement")
    return {
        "as_of": row.get("as_of"),
        "candidate_observation": row.get("candidate_observation"),
        "critical_probe": row.get("critical_probe"),
        "evidence_snapshots": row.get("evidence_snapshots"),
        "policy_id": row.get("policy_id"),
        "requirement": {
            key: value for key, value in requirement.items() if key != "fixture_locator"
        },
        "requirement_kind": row.get("requirement_kind"),
        "stratum": row.get("stratum"),
    }


def _calibration_stimulus(row: dict[str, Any]) -> dict[str, JsonValue]:
    requirement = row.get("requirement")
    if not isinstance(requirement, dict):
        raise ValueError("invalid requirement")
    stimulus = {
        "schema_version": _STIMULUS_SCHEMA,
        "sample_id": row.get("sample_id"),
        "as_of": row.get("as_of"),
        "requirement": {
            key: value for key, value in requirement.items() if key != "fixture_locator"
        },
        "candidate_observation": row.get("candidate_observation"),
        "evidence_snapshots": row.get("evidence_snapshots"),
    }
    return json.loads(_canonical_bytes(stimulus))


def _task_audit_payload(task: _Task) -> dict[str, JsonValue]:
    return task.payload if task.audit_payload is None else task.audit_payload


def _load_exclusion_review_contexts(
    *,
    packet: dict[str, Any],
    source_root: Path,
) -> tuple[dict[str, ExclusionReviewContext], tuple[Path, ...]]:
    paths = {
        name: _safe_source_path(source_root, str(relative))
        for name, relative in _S2C_CONTEXT_FILES.items()
    }
    contracts = _load_canonical_jsonl(paths["contracts"])
    accounting_rows = _load_canonical_jsonl(paths["accounting"])
    snapshots = _load_canonical_jsonl(paths["snapshots"])
    manifest = _load_canonical_json(paths["manifest"])
    source_identity = packet.get("source_identity")
    if not isinstance(source_identity, dict):
        raise ValueError("packet source identity")
    expected_raw = {
        "contracts": source_identity.get("corpus_file_sha256"),
        "accounting": source_identity.get("accounting_file_sha256"),
        "snapshots": source_identity.get("snapshot_file_sha256"),
        "manifest": source_identity.get("manifest_file_sha256"),
    }
    for name, expected in expected_raw.items():
        if not isinstance(expected, str) or _raw_sha256(paths[name]) != expected:
            raise ValueError("S2C source identity")

    manifest_content = _require_self_hash(manifest)
    if (
        manifest.get("schema_version") != _S2C_MANIFEST_SCHEMA
        or manifest_content != source_identity.get("manifest_content_sha256")
        or manifest.get("corpus_id") != source_identity.get("corpus_id")
        or manifest.get("contract_version") != source_identity.get("contract_version")
        or manifest.get("case_contract_schema_version")
        != source_identity.get("case_contract_schema_version")
        or manifest.get("contract_case_count") != 52
        or manifest.get("snapshot_count") != 53
    ):
        raise ValueError("S2C manifest identity")
    outputs = manifest.get("outputs")
    expected_outputs = {
        "claim-level-corpus-v1.jsonl": expected_raw["contracts"],
        "case-accounting-v1.jsonl": expected_raw["accounting"],
        "source-snapshots-v1.jsonl": expected_raw["snapshots"],
    }
    if not isinstance(outputs, dict) or any(
        outputs.get(name) != {"sha256": expected}
        for name, expected in expected_outputs.items()
    ):
        raise ValueError("S2C manifest outputs")
    if len(contracts) != 52 or len(accounting_rows) != 52 or len(snapshots) != 53:
        raise ValueError("S2C source counts")

    contracts_by_id: dict[str, dict[str, Any]] = {}
    for row in contracts:
        case_id = row.get("case_id")
        if (
            not isinstance(case_id, str)
            or case_id in contracts_by_id
            or _require_self_hash(row) != row.get("content_sha256")
        ):
            raise ValueError("S2C contract identity")
        contracts_by_id[case_id] = row

    accounting_by_id: dict[str, dict[str, Any]] = {}
    for row in accounting_rows:
        case_id = row.get("contract_case_id")
        if (
            not isinstance(case_id, str)
            or case_id in accounting_by_id
            or _require_self_hash(row) != row.get("content_sha256")
        ):
            raise ValueError("S2C accounting identity")
        accounting_by_id[case_id] = row

    snapshots_by_id: dict[str, dict[str, Any]] = {}
    for row in snapshots:
        snapshot_id = row.get("snapshot_id")
        payload = row.get("payload")
        payload_kind = row.get("payload_kind")
        record_sha256 = row.get("record_sha256")
        if payload_kind == "canonical_json" and isinstance(payload, dict):
            payload_sha256 = _canonical_sha256(payload)
        elif payload_kind == "utf8_text" and isinstance(payload, str):
            payload_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        else:
            raise ValueError("S2C snapshot payload")
        if (
            not isinstance(snapshot_id, str)
            or snapshot_id in snapshots_by_id
            or row.get("content_sha256") != payload_sha256
            or not isinstance(record_sha256, str)
            or record_sha256
            != _canonical_sha256(
                {key: value for key, value in row.items() if key != "record_sha256"}
            )
        ):
            raise ValueError("S2C snapshot identity")
        snapshots_by_id[snapshot_id] = row

    exclusions = packet.get("exclusion_candidates")
    if not isinstance(exclusions, list) or len(exclusions) != 23:
        raise ValueError("S2C exclusions")
    exclusion_ids = {row.get("case_id") for row in exclusions if isinstance(row, dict)}
    blocked_contract_ids = {
        case_id
        for case_id, row in contracts_by_id.items()
        if row.get("review_state") == "blocked_missing_evidence"
    }
    blocked_accounting_ids = {
        case_id
        for case_id, row in accounting_by_id.items()
        if row.get("conversion_outcome") == "blocked_missing_evidence"
    }
    if (
        len(exclusion_ids) != 23
        or exclusion_ids != blocked_contract_ids
        or exclusion_ids != blocked_accounting_ids
    ):
        raise ValueError("S2C exclusion set")

    contexts: dict[str, ExclusionReviewContext] = {}
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("S2C exclusion row")
        case_id = exclusion.get("case_id")
        source_case_id = exclusion.get("source_case_id")
        snapshot_ids = exclusion.get("snapshot_ids")
        if (
            not isinstance(case_id, str)
            or not isinstance(source_case_id, str)
            or not isinstance(snapshot_ids, list)
            or not snapshot_ids
            or not all(isinstance(value, str) for value in snapshot_ids)
        ):
            raise ValueError("S2C exclusion identity")
        contract = contracts_by_id[case_id]
        accounting = accounting_by_id[case_id]
        contract_snapshots = contract.get("source_snapshots")
        reference = contract.get("reference_context")
        outcome = contract.get("outcome_policy")
        if (
            exclusion.get("contract_content_sha256") != contract.get("content_sha256")
            or exclusion.get("source_case_id") != contract.get("source_case_id")
            or exclusion.get("family") != accounting.get("family")
            or accounting.get("contract_content_sha256")
            != contract.get("content_sha256")
            or accounting.get("source_case_id") != source_case_id
            or accounting.get("requirement_snapshot_ids") != snapshot_ids
            or accounting.get("evidence_snapshot_ids") != []
            or accounting.get("review_state") != exclusion.get("review_state")
            or contract.get("review_state") != exclusion.get("review_state")
            or contract.get("acceptance_eligible") is not False
            or contract.get("evidence_availability") != "unavailable"
            or contract.get("unavailable_evidence_reason")
            != exclusion.get("evidence_gap_reason")
            or not isinstance(contract_snapshots, list)
            or [row.get("snapshot_id") for row in contract_snapshots] != snapshot_ids
            or not isinstance(reference, dict)
            or reference.get("answer_role") != "review_only"
            or not isinstance(reference.get("reference_prose"), str)
            or reference.get("reference_key_points") is not None
            and not isinstance(reference.get("reference_key_points"), str)
            or not isinstance(outcome, dict)
            or outcome.get("reference_prose_normative") is not False
        ):
            raise ValueError("S2C exclusion join")
        joined_snapshots: list[dict[str, Any]] = []
        for expected, snapshot_id in zip(contract_snapshots, snapshot_ids, strict=True):
            if not isinstance(expected, dict):
                raise ValueError("S2C contract snapshot")
            snapshot = snapshots_by_id.get(snapshot_id)
            if snapshot is None:
                raise ValueError("S2C missing snapshot")
            for key in (
                "snapshot_id",
                "captured_at",
                "content_sha256",
                "review_state",
                "snapshot_role",
                "source_locator",
                "source_nature",
            ):
                if expected.get(key) != snapshot.get(key):
                    raise ValueError("S2C snapshot join")
            payload = snapshot.get("payload")
            if (
                snapshot.get("source_case_id") != source_case_id
                or snapshot.get("snapshot_role") != "requirement_context"
                or not isinstance(payload, dict)
                or payload.get("case_id") != source_case_id
                or payload.get("query") != contract.get("query")
                or accounting.get("source_case_sha256")
                != snapshot.get("content_sha256")
            ):
                raise ValueError("S2C requirement snapshot")
            joined_snapshots.append(snapshot)
        query = contract.get("query")
        as_of = contract.get("as_of")
        if not isinstance(query, str) or not isinstance(as_of, str):
            raise ValueError("S2C review context")
        contexts[case_id] = ExclusionReviewContext(
            query=query,
            as_of=as_of,
            contract=contract,
            accounting=accounting,
            requirement_snapshots=tuple(joined_snapshots),
            reference_prose=ReviewOnlyReferenceProse(
                content=reference["reference_prose"],
                key_points=reference.get("reference_key_points"),
            ),
            requirement_snapshot_use=ReviewOnlyMarker(),
        )
    return contexts, tuple(paths.values())


def _load_bound_artifacts(
    *, packet_path: Path, workload_path: Path, source_root: Path
) -> _Artifacts:
    workload_source = workload_path.resolve(strict=True)
    review_dir = workload_source.parent
    packet_source = packet_path.resolve(strict=True)
    policy_path = review_dir / "calibration-policy-v2.json"
    bank_path = review_dir / "calibration-observation-bank-v2.jsonl"
    provenance_path = review_dir / "calibration-observation-bank-v2-provenance.json"
    for peer in (policy_path, bank_path, provenance_path):
        if peer.is_symlink() or peer.resolve(strict=True).parent != review_dir:
            raise ValueError("review artifact is not a same-directory file")
    if _RENDERER_DIR.is_symlink():
        raise ValueError("renderer directory is not a regular directory")
    renderer_root = _RENDERER_DIR.resolve(strict=True)
    if not renderer_root.is_dir():
        raise ValueError("renderer directory is not a regular directory")
    renderer_paths: dict[str, Path] = {}
    for name in _RENDERER_FILES:
        path = _RENDERER_DIR / name
        if (
            path.is_symlink()
            or path.resolve(strict=True).parent != renderer_root
            or not path.is_file()
        ):
            raise ValueError("renderer asset is not a same-directory file")
        renderer_paths[name] = path
    packet = _load_canonical_json(packet_source)
    workload = _load_canonical_json(workload_source)
    policy = _load_canonical_json(policy_path)
    bank = _load_canonical_jsonl(bank_path)
    provenance = _load_canonical_json(provenance_path)

    if packet.get("schema_version") != _PACKET_SCHEMA:
        raise ValueError("packet schema")
    packet_content = _require_self_hash(packet)
    if (_raw_sha256(packet_source), packet_content) != _EXPECTED_ARTIFACT_IDENTITIES[
        "packet"
    ]:
        raise ValueError("packet identity")
    exclusion_contexts, context_paths = _load_exclusion_review_contexts(
        packet=packet,
        source_root=source_root,
    )
    if workload.get("schema_version") != _WORKLOAD_SCHEMA:
        raise ValueError("workload schema")
    workload_content = _require_self_hash(workload)
    if (
        _raw_sha256(workload_source),
        workload_content,
    ) != _EXPECTED_ARTIFACT_IDENTITIES["workload"]:
        raise ValueError("workload identity")
    if set(workload) != {
        "bank_identity",
        "calibration_probes",
        "content_sha256",
        "contract_reviews",
        "counts",
        "exclusion_reviews",
        "packet_identity",
        "policy",
        "policy_identity",
        "provenance_identity",
        "schema_version",
        "workload_id",
    }:
        raise ValueError("workload fields")

    packet_identity = workload.get("packet_identity")
    if packet_identity != {
        "schema_version": _PACKET_SCHEMA,
        "raw_sha256": _raw_sha256(packet_source),
        "content_sha256": packet_content,
    }:
        raise ValueError("packet binding")
    if workload.get("contract_reviews") != packet.get("review_candidates"):
        raise ValueError("contract binding")
    if workload.get("exclusion_reviews") != packet.get("exclusion_candidates"):
        raise ValueError("exclusion binding")

    if (
        policy.get("schema_version") != _POLICY_SCHEMA
        or policy.get("policy_id") != _CALIBRATION_POLICY_ID
    ):
        raise ValueError("policy schema")
    if policy != workload.get("policy"):
        raise ValueError("policy binding")
    if workload.get("policy_identity") != {
        "raw_sha256": _raw_sha256(policy_path),
        "content_sha256": _canonical_sha256(policy),
    }:
        raise ValueError("policy identity")
    if (
        _raw_sha256(policy_path),
        _canonical_sha256(policy),
    ) != _EXPECTED_ARTIFACT_IDENTITIES["policy"]:
        raise ValueError("policy frozen identity")
    if policy.get("reviewer_count") != 1 or policy.get("sample_count") != 60:
        raise ValueError("policy counts")
    if policy.get("strata") != _EXPECTED_STRATA:
        raise ValueError("policy strata")

    if bank != workload.get("calibration_probes"):
        raise ValueError("bank/workload binding")
    if workload.get("bank_identity") != {
        "raw_sha256": _raw_sha256(bank_path),
        "content_sha256": _canonical_sha256(bank),
        "row_count": 60,
    }:
        raise ValueError("bank identity")
    if (
        _raw_sha256(bank_path),
        _canonical_sha256(bank),
    ) != _EXPECTED_ARTIFACT_IDENTITIES["bank"]:
        raise ValueError("bank frozen identity")
    if provenance.get("schema_version") != _PROVENANCE_SCHEMA:
        raise ValueError("provenance schema")
    provenance_content = _require_self_hash(provenance)
    if workload.get("provenance_identity") != {
        "schema_version": _PROVENANCE_SCHEMA,
        "raw_sha256": _raw_sha256(provenance_path),
        "content_sha256": provenance_content,
    }:
        raise ValueError("provenance identity")
    if (
        _raw_sha256(provenance_path),
        provenance_content,
    ) != _EXPECTED_ARTIFACT_IDENTITIES["provenance"]:
        raise ValueError("provenance frozen identity")

    counts = workload.get("counts")
    contract_rows = workload.get("contract_reviews")
    exclusion_rows = workload.get("exclusion_reviews")
    calibration_rows = workload.get("calibration_probes")
    if counts != _EXPECTED_COUNTS:
        raise ValueError("workload counts")
    if not isinstance(contract_rows, list) or len(contract_rows) != 29:
        raise ValueError("contract count")
    if not isinstance(exclusion_rows, list) or len(exclusion_rows) != 23:
        raise ValueError("exclusion count")
    if not isinstance(calibration_rows, list) or len(calibration_rows) != 60:
        raise ValueError("calibration count")
    _walk_forbidden_labels(workload)

    sample_ids: list[str] = []
    request_hashes: list[str] = []
    strata: Counter[str] = Counter()
    source_identities: dict[str, str] = {}
    provenance_bindings: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    source_groups = provenance.get("source_groups")
    if not isinstance(source_groups, list):
        raise ValueError("provenance groups")
    for group in source_groups:
        if not isinstance(group, dict) or set(group) != {
            "path",
            "samples",
            "source_sha256",
            "test_name",
        }:
            raise ValueError("provenance group")
        samples = group.get("samples")
        if not isinstance(samples, list):
            raise ValueError("provenance samples")
        for sample in samples:
            if not isinstance(sample, dict) or set(sample) != {
                "sample_id",
                "selectors",
            }:
                raise ValueError("provenance sample")
            sample_id = sample.get("sample_id")
            selectors = sample.get("selectors")
            if (
                not isinstance(sample_id, str)
                or sample_id in provenance_bindings
                or not isinstance(selectors, list)
                or not selectors
                or not all(isinstance(item, str) for item in selectors)
            ):
                raise ValueError("provenance binding")
            provenance_bindings[sample_id] = (
                str(group.get("path")),
                str(group.get("source_sha256")),
                str(group.get("test_name")),
                tuple(selectors),
            )

    projections = provenance.get("projection_sha256s")
    for row in calibration_rows:
        if not isinstance(row, dict) or row.get("schema_version") != _REQUEST_SCHEMA:
            raise ValueError("calibration schema")
        sample_id = row.get("sample_id")
        request_hash = row.get("request_sha256")
        stratum = row.get("stratum")
        source = row.get("source_identity")
        requirement = row.get("requirement")
        if (
            not isinstance(sample_id, str)
            or not isinstance(request_hash, str)
            or not isinstance(stratum, str)
            or not isinstance(source, dict)
            or not isinstance(requirement, dict)
        ):
            raise ValueError("calibration fields")
        request_without_hash = {
            key: value for key, value in row.items() if key != "request_sha256"
        }
        if request_hash != _canonical_sha256(request_without_hash):
            raise ValueError("request identity")
        if row.get("policy_id") != _CALIBRATION_POLICY_ID:
            raise ValueError("request policy")
        if row.get("requirement_kind") != _EXPECTED_REQUIREMENT_KINDS.get(stratum):
            raise ValueError("request kind")
        path_value = source.get("path")
        sha_value = source.get("source_sha256")
        test_name = source.get("test_name")
        locator = requirement.get("fixture_locator")
        if (
            not isinstance(path_value, str)
            or not isinstance(sha_value, str)
            or not isinstance(test_name, str)
            or not isinstance(locator, dict)
            or locator.get("function") != test_name
            or not isinstance(locator.get("selectors"), list)
        ):
            raise ValueError("source identity")
        source_path = _safe_source_path(source_root, path_value)
        actual_source_sha = _raw_sha256(source_path)
        if actual_source_sha != sha_value:
            raise ValueError("source identity")
        prior_sha = source_identities.setdefault(path_value, sha_value)
        if prior_sha != sha_value:
            raise ValueError("source identity conflict")
        binding = (path_value, sha_value, test_name, tuple(locator["selectors"]))
        if provenance_bindings.get(sample_id) != binding:
            raise ValueError("provenance binding")
        if not isinstance(projections, dict) or projections.get(
            sample_id
        ) != _canonical_sha256(_audit_projection(row)):
            raise ValueError("provenance projection")
        sample_ids.append(sample_id)
        request_hashes.append(request_hash)
        strata[stratum] += 1
    if len(source_identities) != 7:
        raise ValueError("source identity count")
    if len(sample_ids) != len(set(sample_ids)) or len(request_hashes) != len(
        set(request_hashes)
    ):
        raise ValueError("calibration uniqueness")
    if (
        provenance.get("sample_ids") != sample_ids
        or list(provenance_bindings) != sample_ids
    ):
        raise ValueError("provenance order")
    if set(projections or {}) != set(sample_ids):
        raise ValueError("provenance projections")
    if strata != Counter(_EXPECTED_STRATA):
        raise ValueError("calibration strata")

    tasks: list[_Task] = []
    for row in contract_rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ValueError("contract task")
        tasks.append(
            _Task(
                task_id=f"contract:{row['case_id']}",
                kind=TaskKind.CONTRACT,
                payload=row,
            )
        )
    for row in exclusion_rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ValueError("exclusion task")
        tasks.append(
            _Task(
                task_id=f"exclusion:{row['case_id']}",
                kind=TaskKind.EXCLUSION,
                payload=row,
                review_context=exclusion_contexts[row["case_id"]],
            )
        )
    for row in calibration_rows:
        stimulus = _calibration_stimulus(row)
        tasks.append(
            _Task(
                task_id=f"calibration:{row['sample_id']}",
                kind=TaskKind.CALIBRATION,
                payload=stimulus,
                audit_payload=row,
            )
        )
    task_ids = [task.task_id for task in tasks]
    if len(tasks) != 112 or len(task_ids) != len(set(task_ids)):
        raise ValueError("task identity")

    context_paths_by_name = dict(zip(_S2C_CONTEXT_FILES, context_paths, strict=True))
    packet_source_identity = packet.get("source_identity")
    if not isinstance(packet_source_identity, dict):
        raise ValueError("packet source identity")

    watched = [
        packet_source,
        workload_source,
        policy_path,
        bank_path,
        provenance_path,
        *context_paths,
        *(_safe_source_path(source_root, relative) for relative in source_identities),
        *renderer_paths.values(),
    ]
    stimuli = [_calibration_stimulus(row) for row in calibration_rows]
    renderer_hashes = {
        name: _raw_sha256(renderer_paths[name]) for name in _RENDERER_FILES
    }
    identity: dict[str, JsonValue] = {
        "packet_raw_sha256": _raw_sha256(packet_source),
        "packet_content_sha256": packet_content,
        "workload_raw_sha256": _raw_sha256(workload_source),
        "workload_content_sha256": workload_content,
        "policy_raw_sha256": _raw_sha256(policy_path),
        "policy_content_sha256": _canonical_sha256(policy),
        "bank_raw_sha256": _raw_sha256(bank_path),
        "bank_content_sha256": _canonical_sha256(bank),
        "provenance_raw_sha256": _raw_sha256(provenance_path),
        "provenance_content_sha256": provenance_content,
        "s2c_manifest_raw_sha256": _raw_sha256(context_paths_by_name["manifest"]),
        "s2c_manifest_content_sha256": packet_source_identity[
            "manifest_content_sha256"
        ],
        "s2c_corpus_raw_sha256": _raw_sha256(context_paths_by_name["contracts"]),
        "s2c_accounting_raw_sha256": _raw_sha256(context_paths_by_name["accounting"]),
        "s2c_snapshots_raw_sha256": _raw_sha256(context_paths_by_name["snapshots"]),
        "calibration_stimulus_set_sha256": _canonical_sha256(
            {
                "schema_version": _STIMULUS_SET_SCHEMA,
                "stimuli": stimuli,
            }
        ),
        "renderer_schema_version": _RENDERER_SCHEMA,
        "review_html_raw_sha256": renderer_hashes["review.html"],
        "review_css_raw_sha256": renderer_hashes["review.css"],
        "review_js_raw_sha256": renderer_hashes["review.js"],
        "review_mutation_coordinator_js_raw_sha256": renderer_hashes[
            "review_mutation_coordinator.js"
        ],
        "review_presentation_js_raw_sha256": renderer_hashes["review_presentation.js"],
        "renderer_content_sha256": _canonical_sha256(
            {
                "schema_version": _RENDERER_SCHEMA,
                "assets": renderer_hashes,
            }
        ),
        "source_sha256s": dict(sorted(source_identities.items())),
    }
    return _Artifacts(
        tasks=tuple(tasks),
        counts=ReviewCounts(**_EXPECTED_COUNTS),
        identity=identity,
        header_identity=WorkspaceArtifactIdentity.model_validate(
            {field: identity[field] for field in WorkspaceArtifactIdentity.model_fields}
        ),
        watched_sha256s=tuple((path, _raw_sha256(path)) for path in watched),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return secrets.token_hex(16)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_runtime_instance_id() -> str:
    return f"runtime:{secrets.token_hex(16)}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _reject_sensitive_text(*values: str | None) -> None:
    if any(value is not None and _SENSITIVE_TEXT.search(value) for value in values):
        raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)


def _lexical_absolute(path: Path) -> Path:
    if ".." in path.parts:
        raise OSError("parent traversal is not allowed")
    return Path(os.path.abspath(os.fspath(path)))


def _require_no_symlink_components(path: Path, *, final_kind: str | None) -> None:
    current = Path(path.anchor)
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(metadata.st_mode):
            raise OSError("symlink path component")
        is_final = index == len(parts) - 1
        if not is_final and not stat.S_ISDIR(metadata.st_mode):
            raise OSError("non-directory path component")
        if (
            is_final
            and final_kind == "directory"
            and not stat.S_ISDIR(metadata.st_mode)
        ):
            raise OSError("workspace path is not a directory")
        if is_final and final_kind == "file" and not stat.S_ISREG(metadata.st_mode):
            raise OSError("workspace path is not a regular file")


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _require_private_regular_file(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise OSError("workspace file is not private and regular")


def _prepare_workspace_paths(
    *, state_dir: Path, export_dir: Path
) -> tuple[Path, Path, tuple[int, int]]:
    state = _lexical_absolute(state_dir)
    export = _lexical_absolute(export_dir)
    _require_no_symlink_components(state, final_kind="directory")
    _require_no_symlink_components(export, final_kind="directory")
    if _paths_overlap(state, export):
        raise OSError("workspace paths overlap")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_no_symlink_components(state, final_kind="directory")
    if state.resolve(strict=True) != state:
        raise OSError("workspace path alias")
    os.chmod(state, 0o700, follow_symlinks=False)

    database = state / _DATABASE_NAME
    try:
        metadata = os.lstat(database)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(database, flags, 0o600)
        os.close(descriptor)
        metadata = os.lstat(database)
    _require_private_regular_file(metadata)
    os.chmod(database, 0o600, follow_symlinks=False)
    return state, export, (metadata.st_dev, metadata.st_ino)


def _rollback_after_failure(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.Error:
        pass


class ReviewWorkspace:
    """Own artifact admission, attribution, task state, and the immutable ledger."""

    def __init__(
        self,
        *,
        artifacts: _Artifacts,
        state_dir: Path,
        export_dir: Path,
        clock: Callable[[], datetime],
        id_factory: Callable[[], str],
        token_factory: Callable[[], str],
        judge: EvidenceBoundedJudge | None,
        judge_authorization_provider: JudgeAuthorizationProvider | None,
        evidence_class: EvidenceClass,
        runtime_instance_id: str,
        recovery_only: bool,
    ) -> None:
        self._artifacts = artifacts
        self._tasks = {task.task_id: task for task in artifacts.tasks}
        self._task_order = tuple(task.task_id for task in artifacts.tasks)
        self._evidence_class = evidence_class
        self._runtime_instance_id = runtime_instance_id
        self._recovery_only = recovery_only
        try:
            safe_state, safe_export, database_identity = _prepare_workspace_paths(
                state_dir=state_dir,
                export_dir=export_dir,
            )
        except OSError as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        self._state_dir = safe_state
        self._database_path = safe_state / _DATABASE_NAME
        self._database_identity = database_identity
        self._export_dir = safe_export
        self._clock = clock
        self._id_factory = id_factory
        self._token_factory = token_factory
        self._judge = judge
        self._judge_authorization_provider = judge_authorization_provider
        self._initialize_database()

    def open(self, request: OpenWorkspace) -> WorkspaceView | SealedWorkspaceView:
        self._require_interactive_mode()
        self._assert_artifacts_current()
        if request.session_token is not None:
            if request.display_name is not None or request.staff_id is not None:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_REVIEWER)
            connection: sqlite3.Connection | None = None
            try:
                connection = self._connection()
                round_row = self._round_for_token(connection, request.session_token)
                return self._workspace_view(
                    connection,
                    round_row=round_row,
                    requested_task_id=request.task_id,
                )
            except ReviewWorkspaceError:
                raise
            except _EXPECTED_STORAGE_ERRORS as exc:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
            finally:
                if connection is not None:
                    connection.close()
        if request.task_id is not None:
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
        display_name, staff_id = self._normalize_reviewer(
            request.display_name, request.staff_id
        )
        return self._register(display_name=display_name, staff_id=staff_id)

    def record(self, command: ReviewCommand) -> WorkspaceView | SealedWorkspaceView:
        self._require_interactive_mode()
        self._assert_artifacts_current()
        if isinstance(command, SaveDraft):
            return self._save_draft(command)
        if isinstance(command, SubmitDecision):
            return self._submit_decision(command)
        if isinstance(command, SealCalibration):
            return self._seal_calibration(command)
        raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)

    def export(self, command: ExportReview) -> ExportReceipt:
        self._require_interactive_mode()
        self._assert_artifacts_current()
        _reject_sensitive_text(command.idempotency_key)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connection()
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            round_id = str(round_row["round_id"])
            command_sha256 = _canonical_sha256(
                {"action": "export", "mode": command.mode.value, "round_id": round_id}
            )
            existing = connection.execute(
                "SELECT * FROM export_records WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["round_id"] != round_id
                    or existing["command_sha256"] != command_sha256
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
                receipt = self._export_receipt(existing)
                content = bytes(existing["content_bytes"])
                connection.commit()
            else:
                latest = self._latest_decision_rows(connection, round_id=round_id)
                calibration = self._sealed_calibration(connection, round_id=round_id)
                gates = self._review_gate_summary(
                    latest=latest,
                    lifecycle=str(round_row["lifecycle"]),
                    calibration_passed=(
                        None if calibration is None else calibration.passed
                    ),
                )
                acceptance_eligible = (
                    command.mode is ExportMode.ACCEPTANCE_CANDIDATE
                    and str(round_row["lifecycle"]) == "acceptance_ready"
                    and gates.acceptance_ready
                )
                if (
                    command.mode is ExportMode.ACCEPTANCE_CANDIDATE
                    and not acceptance_eligible
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.EXPORT_BLOCKED)
                created_at = _timestamp(self._clock())
                export_id = f"export:{self._id_factory()}"
                basename = self._export_basename(export_id)
                payload = self._export_payload(
                    connection,
                    round_row=round_row,
                    export_id=export_id,
                    mode=command.mode,
                    created_at=created_at,
                    latest=latest,
                    calibration=calibration,
                    gates=gates,
                    acceptance_eligible=acceptance_eligible,
                )
                content = _canonical_bytes(payload)
                raw_sha256 = hashlib.sha256(content).hexdigest()
                content_sha256 = str(payload["content_sha256"])
                connection.execute(
                    "INSERT INTO export_records(export_id, round_id, idempotency_key, "
                    "command_sha256, mode, evidence_class, acceptance_eligible, "
                    "task_2_8_eligible, basename, raw_sha256, content_sha256, "
                    "content_length, content_bytes, state, created_at, verified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, NULL)",
                    (
                        export_id,
                        round_id,
                        command.idempotency_key,
                        command_sha256,
                        command.mode.value,
                        self._evidence_class.value,
                        int(acceptance_eligible),
                        int(
                            acceptance_eligible
                            and self._evidence_class is EvidenceClass.REAL_HUMAN_ROUND
                        ),
                        basename,
                        raw_sha256,
                        content_sha256,
                        len(content),
                        content,
                        created_at,
                    ),
                )
                if acceptance_eligible:
                    locked = connection.execute(
                        "UPDATE rounds SET lifecycle = 'locked', updated_at = ? "
                        "WHERE round_id = ? AND lifecycle = 'acceptance_ready'",
                        (created_at, round_id),
                    )
                    if locked.rowcount != 1:
                        raise ReviewWorkspaceError(ReviewErrorCode.EXPORT_BLOCKED)
                row = connection.execute(
                    "SELECT * FROM export_records WHERE export_id = ?", (export_id,)
                ).fetchone()
                if row is None:
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
                receipt = self._export_receipt(row)
                connection.commit()
            self._write_export_bytes(receipt=receipt, content=content)
            connection = self._connection()
            connection.execute("BEGIN IMMEDIATE")
            record = connection.execute(
                "SELECT * FROM export_records WHERE export_id = ?", (receipt.export_id,)
            ).fetchone()
            if record is None or bytes(record["content_bytes"]) != content:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            verified_at = _timestamp(self._clock())
            connection.execute(
                "UPDATE export_records SET state = 'verified', verified_at = ? "
                "WHERE export_id = ? AND state = 'prepared'",
                (verified_at, receipt.export_id),
            )
            connection.commit()
            return receipt
        except ReviewWorkspaceError:
            if connection is not None:
                _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            if connection is not None:
                _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            if connection is not None:
                connection.close()

    def read_export(self, command: ReadExport) -> ExportDownload:
        self._require_interactive_mode()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connection()
            round_row = self._round_for_token(connection, command.session_token)
            row = connection.execute(
                "SELECT * FROM export_records WHERE export_id = ?", (command.export_id,)
            ).fetchone()
            if row is None or row["round_id"] != round_row["round_id"]:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
            if row["state"] != "verified":
                raise ReviewWorkspaceError(ReviewErrorCode.EXPORT_BLOCKED)
            content = bytes(row["content_bytes"])
            receipt = self._export_receipt(row)
            self._verify_export_bytes(receipt=receipt, content=content)
            return ExportDownload(receipt=receipt, content=content)
        except ReviewWorkspaceError:
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            if connection is not None:
                connection.close()

    def abandon_in_flight_judge_run(
        self, command: AbandonInFlightJudgeRun
    ) -> JudgeRunRecoveryReceipt:
        if not self._recovery_only:
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connection()
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT j.*, r.staff_id FROM judge_runs j JOIN rounds r "
                "ON r.round_id = j.round_id WHERE j.run_id = ?",
                (command.run_id,),
            ).fetchone()
            if (
                run is None
                or run["state"] != "in_flight"
                or run["round_id"] != command.round_id
                or run["command_sha256"] != command.command_sha256
                or run["human_snapshot_sha256"] != command.human_snapshot_sha256
                or run["authorization_sha256"] != command.authorization_sha256
                or run["staff_id"] != command.operator_staff_id
            ):
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
            if run["runtime_instance_id"] == self._runtime_instance_id:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            recovery_time = self._clock()
            recovered_at = _timestamp(recovery_time)
            recovery_id = f"judge-recovery:{self._id_factory()}"
            changed = connection.execute(
                "UPDATE judge_runs SET state = 'failed', "
                "failure_code = 'operator_abandoned_after_crash', finished_at = ? "
                "WHERE run_id = ? AND state = 'in_flight'",
                (recovered_at, command.run_id),
            )
            if changed.rowcount != 1:
                raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_RECOVERY_REQUIRED)
            connection.execute(
                "INSERT INTO judge_run_recoveries(recovery_id, run_id, round_id, "
                "command_sha256, human_snapshot_sha256, authorization_sha256, "
                "operator_staff_id, reason, recovered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    recovery_id,
                    command.run_id,
                    command.round_id,
                    command.command_sha256,
                    command.human_snapshot_sha256,
                    command.authorization_sha256,
                    command.operator_staff_id,
                    command.reason,
                    recovered_at,
                ),
            )
            connection.commit()
            return JudgeRunRecoveryReceipt(
                recovery_id=recovery_id,
                run_id=command.run_id,
                round_id=command.round_id,
                command_sha256=command.command_sha256,
                human_snapshot_sha256=command.human_snapshot_sha256,
                authorization_sha256=command.authorization_sha256,
                operator_staff_id=command.operator_staff_id,
                reason=command.reason,
                recovered_at=recovery_time,
            )
        except ReviewWorkspaceError:
            if connection is not None:
                _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            if connection is not None:
                _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _export_basename(export_id: str) -> str:
        safe = export_id.replace(":", "-")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", safe):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        return f"{safe}.json"

    @staticmethod
    def _export_receipt(row: sqlite3.Row) -> ExportReceipt:
        try:
            return ExportReceipt(
                export_id=row["export_id"],
                round_id=row["round_id"],
                mode=row["mode"],
                evidence_class=row["evidence_class"],
                acceptance_eligible=bool(row["acceptance_eligible"]),
                task_2_8_eligible=bool(row["task_2_8_eligible"]),
                basename=row["basename"],
                raw_sha256=row["raw_sha256"],
                content_sha256=row["content_sha256"],
                content_length=row["content_length"],
                created_at=row["created_at"],
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc

    def _latest_decision_rows(
        self, connection: sqlite3.Connection, *, round_id: str
    ) -> dict[str, sqlite3.Row]:
        return {
            str(row["task_id"]): row
            for row in connection.execute(
                "SELECT e.* FROM decision_events e JOIN ("
                "SELECT task_id, max(revision) AS revision FROM decision_events "
                "WHERE round_id = ? GROUP BY task_id"
                ") current ON current.task_id = e.task_id "
                "AND current.revision = e.revision WHERE e.round_id = ?",
                (round_id, round_id),
            )
        }

    @staticmethod
    def _sealed_calibration(
        connection: sqlite3.Connection, *, round_id: str
    ) -> CalibrationSummary | None:
        row = connection.execute(
            "SELECT summary_json, summary_sha256 FROM calibration_seals WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        if row is None:
            return None
        serialized = row["summary_json"]
        if (
            not isinstance(serialized, str)
            or hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            != row["summary_sha256"]
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        return CalibrationSummary.model_validate(json.loads(serialized))

    def _export_payload(
        self,
        connection: sqlite3.Connection,
        *,
        round_row: sqlite3.Row,
        export_id: str,
        mode: ExportMode,
        created_at: str,
        latest: dict[str, sqlite3.Row],
        calibration: CalibrationSummary | None,
        gates: ReviewGateSummary,
        acceptance_eligible: bool,
    ) -> dict[str, Any]:
        round_id = str(round_row["round_id"])
        events = tuple(
            connection.execute(
                "SELECT * FROM decision_events WHERE round_id = ? "
                "ORDER BY task_id, revision, event_id",
                (round_id,),
            )
        )
        event_payloads = [
            {
                "event_id": row["event_id"],
                "task_id": row["task_id"],
                "task_kind": row["task_kind"],
                "revision": row["revision"],
                "supersedes_event_id": row["supersedes_event_id"],
                "decision": row["decision"],
                "rationale": row["rationale"],
                "canonical_payload": json.loads(row["canonical_payload_json"]),
                "payload_sha256": row["payload_sha256"],
                "idempotency_sha256": hashlib.sha256(
                    row["idempotency_key"].encode("utf-8")
                ).hexdigest(),
                "record_sha256": _canonical_sha256(
                    {
                        "event_id": row["event_id"],
                        "payload_sha256": row["payload_sha256"],
                        "revision": row["revision"],
                        "supersedes_event_id": row["supersedes_event_id"],
                    }
                ),
                "submitted_at": row["submitted_at"],
            }
            for row in events
        ]
        decisions = {
            kind.value: [
                {
                    "task_id": task_id,
                    "decision": row["decision"],
                    "revision": row["revision"],
                    "event_id": row["event_id"],
                    "payload_sha256": row["payload_sha256"],
                }
                for task_id, row in sorted(latest.items())
                if self._tasks[task_id].kind is kind
            ]
            for kind in (TaskKind.CONTRACT, TaskKind.EXCLUSION, TaskKind.CALIBRATION)
        }
        judge: dict[str, Any] = {
            "visibility": "hidden_until_sealed",
            "status": "hidden_until_sealed",
        }
        if calibration is not None:
            authorizations = [
                json.loads(row["authorization_json"])
                for row in connection.execute(
                    "SELECT authorization_json FROM judge_authorizations WHERE round_id = ?",
                    (round_id,),
                )
            ]
            runs = [
                {
                    **{
                        key: row[key]
                        for key in (
                            "run_id",
                            "round_id",
                            "command_sha256",
                            "human_snapshot_sha256",
                            "authorization_sha256",
                            "started_at",
                            "state",
                            "failure_code",
                            "finished_at",
                        )
                    },
                    "idempotency_sha256": hashlib.sha256(
                        row["idempotency_key"].encode("utf-8")
                    ).hexdigest(),
                }
                for row in connection.execute(
                    "SELECT * FROM judge_runs WHERE round_id = ? ORDER BY started_at, run_id",
                    (round_id,),
                )
            ]
            recoveries = [
                dict(row)
                for row in connection.execute(
                    "SELECT recovery_id, run_id, round_id, command_sha256, human_snapshot_sha256, "
                    "authorization_sha256, operator_staff_id, reason, recovered_at "
                    "FROM judge_run_recoveries WHERE round_id = ? ORDER BY recovered_at, recovery_id",
                    (round_id,),
                )
            ]
            responses = [
                {
                    "task_id": row["task_id"],
                    "request_sha256": row["request_sha256"],
                    "response": json.loads(row["response_json"]),
                    "response_sha256": row["response_sha256"],
                    "judged_at": row["judged_at"],
                }
                for row in connection.execute(
                    "SELECT * FROM judge_results WHERE round_id = ? ORDER BY task_id",
                    (round_id,),
                )
            ]
            judge = {
                "visibility": "sealed",
                "authorizations": authorizations,
                "attempts": runs,
                "recoveries": recoveries,
                "completed_run": next(
                    (run for run in runs if run["state"] == "completed"), None
                ),
                "responses": responses,
                "summary": calibration.model_dump(mode="json"),
            }
        result: dict[str, Any] = {
            "schema_version": "canonical-v2-human-review-export-v2",
            "export_id": export_id,
            "mode": mode.value,
            "acceptance_eligible": acceptance_eligible,
            "evidence_class": self._evidence_class.value,
            "task_2_8_eligible": acceptance_eligible
            and self._evidence_class is EvidenceClass.REAL_HUMAN_ROUND,
            "created_at": created_at,
            "artifact_identity": self._artifacts.identity,
            "round": {
                "round_id": round_id,
                "reviewer_id": round_row["reviewer_id"],
                "staff_id": round_row["staff_id"],
                "lifecycle": "locked"
                if acceptance_eligible
                else round_row["lifecycle"],
            },
            "accounting": {
                "counts": self._artifacts.counts.model_dump(mode="json"),
                "missing": list(gates.missing_task_ids),
                "blocking": list(gates.blocking_task_ids),
            },
            "decision_events": event_payloads,
            "contract_decisions": decisions[TaskKind.CONTRACT.value],
            "exclusion_decisions": decisions[TaskKind.EXCLUSION.value],
            "calibration_labels": decisions[TaskKind.CALIBRATION.value],
            "judge": judge,
            "gates": gates.model_dump(mode="json"),
        }
        result["content_sha256"] = _canonical_sha256(result)
        return result

    def _write_export_bytes(self, *, receipt: ExportReceipt, content: bytes) -> None:
        try:
            _require_no_symlink_components(self._export_dir, final_kind="directory")
            self._export_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            _require_no_symlink_components(self._export_dir, final_kind="directory")
            os.chmod(self._export_dir, 0o700, follow_symlinks=False)
        except OSError as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        self._verify_export_bytes(receipt=receipt, content=content, allow_missing=True)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory = os.open(self._export_dir, flags)
        temporary = f".{receipt.basename}.{secrets.token_hex(16)}.tmp"
        try:
            output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                output_flags |= os.O_NOFOLLOW
            descriptor = os.open(temporary, output_flags, 0o600, dir_fd=directory)
            try:
                os.write(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.link(
                    temporary,
                    receipt.basename,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
            except FileExistsError:
                pass
            finally:
                os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(directory)
        self._verify_export_bytes(receipt=receipt, content=content)

    def _verify_export_bytes(
        self, *, receipt: ExportReceipt, content: bytes, allow_missing: bool = False
    ) -> None:
        if (
            len(content) != receipt.content_length
            or hashlib.sha256(content).hexdigest() != receipt.raw_sha256
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        try:
            _require_no_symlink_components(self._export_dir, final_kind="directory")
            if self._export_dir.resolve(strict=True) != self._export_dir:
                raise OSError("export path alias")
            payload = json.loads(content)
            expected_content_hash = payload.pop("content_sha256")
            if (
                expected_content_hash != receipt.content_sha256
                or _canonical_sha256(payload) != expected_content_hash
            ):
                raise ValueError("export content identity")
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                directory_flags |= os.O_NOFOLLOW
            directory = os.open(self._export_dir, directory_flags)
            try:
                directory_metadata = os.fstat(directory)
                if not stat.S_ISDIR(directory_metadata.st_mode):
                    raise OSError("export directory identity")
                descriptor = os.open(receipt.basename, flags, dir_fd=directory)
            finally:
                os.close(directory)
            try:
                metadata = os.fstat(descriptor)
                _require_private_regular_file(metadata)
                if os.read(descriptor, receipt.content_length + 1) != content:
                    raise ValueError("export bytes differ")
            finally:
                os.close(descriptor)
        except FileNotFoundError:
            if allow_missing:
                return
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from None
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc

    def _require_interactive_mode(self) -> None:
        if self._recovery_only:
            raise ReviewWorkspaceError(
                ReviewErrorCode.INVALID_COMMAND,
                reason="recovery_only_workspace",
            )

    def _assert_artifacts_current(self) -> None:
        try:
            for path, expected in self._artifacts.watched_sha256s:
                if _raw_sha256(path) != expected:
                    raise ReviewWorkspaceError(ReviewErrorCode.ARTIFACT_MISMATCH)
        except ReviewWorkspaceError:
            raise
        except (OSError, ValueError) as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.ARTIFACT_MISMATCH) from exc

    def _connection(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self._verify_database_file()
            connection = sqlite3.connect(
                f"{self._database_path.as_uri()}?mode=rw",
                timeout=10,
                isolation_level=None,
                uri=True,
            )
            self._verify_database_file()
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc

    def _verify_database_file(self) -> None:
        _require_no_symlink_components(self._state_dir, final_kind="directory")
        if self._state_dir.resolve(strict=True) != self._state_dir:
            raise OSError("workspace path alias")
        metadata = os.lstat(self._database_path)
        _require_private_regular_file(metadata)
        if (metadata.st_dev, metadata.st_ino) != self._database_identity:
            raise OSError("workspace database identity changed")
        for suffix in ("-journal", "-shm", "-wal"):
            sidecar = Path(f"{self._database_path}{suffix}")
            try:
                sidecar_metadata = os.lstat(sidecar)
            except FileNotFoundError:
                continue
            _require_private_regular_file(sidecar_metadata)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._database_path, flags)
        try:
            opened = os.fstat(descriptor)
            _require_private_regular_file(opened)
            if (opened.st_dev, opened.st_ino) != self._database_identity:
                raise OSError("workspace database descriptor mismatch")
        finally:
            os.close(descriptor)

    def _initialize_database(self) -> None:
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connection()
            metadata = {
                "schema_version": _SCHEMA_VERSION,
                "artifact_identity": _canonical_bytes(self._artifacts.identity).decode(
                    "utf-8"
                ),
                "evidence_class": self._evidence_class.value,
            }
            has_metadata_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'workspace_meta'"
            ).fetchone()
            if has_metadata_table is not None:
                existing = {
                    row["key"]: row["value"]
                    for row in connection.execute(
                        "SELECT key, value FROM workspace_meta"
                    )
                }
                if existing != metadata:
                    raise ReviewWorkspaceError(ReviewErrorCode.ARTIFACT_MISMATCH)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("BEGIN IMMEDIATE")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            existing = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM workspace_meta")
            }
            if existing and existing != metadata:
                raise ReviewWorkspaceError(ReviewErrorCode.ARTIFACT_MISMATCH)
            if not existing:
                connection.executemany(
                    "INSERT INTO workspace_meta(key, value) VALUES (?, ?)",
                    tuple(metadata.items()),
                )
            connection.commit()
        except ReviewWorkspaceError:
            if connection is not None:
                _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            if connection is not None:
                _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _normalize_reviewer(
        display_name: str | None, staff_id: str | None
    ) -> tuple[str, str]:
        normalized_name = "" if display_name is None else display_name.strip()
        normalized_staff = "" if staff_id is None else staff_id.strip().lower()
        if (
            not normalized_name
            or len(normalized_name) > 128
            or not _STAFF_ID.fullmatch(normalized_staff)
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_REVIEWER)
        if _SENSITIVE_TEXT.search(normalized_name) or _SENSITIVE_TEXT.search(
            normalized_staff
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_REVIEWER)
        return normalized_name, normalized_staff

    def _register(self, *, display_name: str, staff_id: str) -> WorkspaceView:
        token = self._token_factory()
        if len(token) < 32:
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
        now = _timestamp(self._clock())
        reviewer_id = f"human:{staff_id}"
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = connection.execute(
                "SELECT * FROM rounds WHERE reviewer_id = ? AND lifecycle != 'locked' "
                "ORDER BY created_at DESC, round_id DESC LIMIT 1",
                (reviewer_id,),
            ).fetchone()
            if round_row is not None and round_row["display_name"] != display_name:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_REVIEWER)
            if round_row is None:
                round_id = f"round:{self._id_factory()}"
                connection.execute(
                    "INSERT INTO rounds(round_id, reviewer_id, display_name, staff_id, "
                    "lifecycle, created_at, updated_at) VALUES (?, ?, ?, ?, 'in_progress', ?, ?)",
                    (round_id, reviewer_id, display_name, staff_id, now, now),
                )
                round_row = connection.execute(
                    "SELECT * FROM rounds WHERE round_id = ?", (round_id,)
                ).fetchone()
            session_id = f"session:{self._id_factory()}"
            connection.execute(
                "INSERT INTO sessions(session_id, round_id, token_hash, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, round_row["round_id"], _token_hash(token), now),
            )
            view = self._workspace_view(
                connection,
                round_row=round_row,
                requested_task_id=None,
                issued_token=token,
            )
            connection.commit()
            return view
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

    def _round_for_token(
        self, connection: sqlite3.Connection, token: str
    ) -> sqlite3.Row:
        if not token or len(token) > 512:
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
        row = connection.execute(
            "SELECT r.* FROM sessions s JOIN rounds r ON r.round_id = s.round_id "
            "WHERE s.token_hash = ?",
            (_token_hash(token),),
        ).fetchone()
        if row is None:
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
        return row

    def _save_draft(self, command: SaveDraft) -> WorkspaceView:
        task = self._require_task(command.task_id)
        _reject_sensitive_text(command.draft.decision, command.draft.rationale)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            if not self._task_is_mutable(task=task, lifecycle=round_row["lifecycle"]):
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            payload = command.draft.model_dump(mode="json")
            now = _timestamp(self._clock())
            connection.execute(
                "INSERT INTO drafts(round_id, task_id, task_kind, payload_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(round_id, task_id) DO UPDATE SET "
                "task_kind = excluded.task_kind, payload_json = excluded.payload_json, "
                "updated_at = excluded.updated_at",
                (
                    round_row["round_id"],
                    task.task_id,
                    task.kind.value,
                    _canonical_bytes(payload).decode("utf-8"),
                    now,
                ),
            )
            connection.execute(
                "UPDATE rounds SET updated_at = ? WHERE round_id = ?",
                (now, round_row["round_id"]),
            )
            view = self._workspace_view(
                connection,
                round_row=round_row,
                requested_task_id=task.task_id,
            )
            connection.commit()
            return view
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

    def _submit_decision(self, command: SubmitDecision) -> WorkspaceView:
        task = self._require_task(command.task_id)
        rationale = None if command.rationale is None else command.rationale.strip()
        _reject_sensitive_text(command.decision, rationale, command.idempotency_key)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            round_id = round_row["round_id"]
            canonical_payload = {
                "action": command.action,
                "decision": command.decision,
                "display_name": round_row["display_name"],
                "expected_revision": command.expected_revision,
                "rationale": rationale,
                "reviewer_id": round_row["reviewer_id"],
                "staff_id": round_row["staff_id"],
                "task_id": task.task_id,
                "task_kind": command.task_kind.value,
            }
            payload_json = _canonical_bytes(canonical_payload).decode("utf-8")
            payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            prior_key = connection.execute(
                "SELECT e.round_id, e.event_id, e.payload_sha256, "
                "r.workspace_view_json, r.view_sha256 "
                "FROM decision_events e LEFT JOIN idempotency_receipts r "
                "ON r.idempotency_key = e.idempotency_key "
                "AND r.event_id = e.event_id AND r.round_id = e.round_id "
                "WHERE e.idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if prior_key is not None:
                if (
                    prior_key["round_id"] != round_id
                    or prior_key["payload_sha256"] != payload_sha256
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
                view = self._validated_receipt(prior_key)
                connection.commit()
                return view
            current = connection.execute(
                "SELECT event_id, revision FROM decision_events "
                "WHERE round_id = ? AND task_id = ? ORDER BY revision DESC LIMIT 1",
                (round_id, task.task_id),
            ).fetchone()
            current_revision = 0 if current is None else int(current["revision"])
            if command.expected_revision != current_revision:
                raise ReviewWorkspaceError(
                    ReviewErrorCode.STALE_REVISION,
                    current_revision=current_revision,
                )
            self._validate_decision(
                task=task,
                command=command,
                rationale=rationale,
                superseding=current is not None,
            )
            if not self._task_is_mutable(task=task, lifecycle=round_row["lifecycle"]):
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            event_id = f"event:{self._id_factory()}"
            submitted_at = _timestamp(self._clock())
            connection.execute(
                "INSERT INTO decision_events(event_id, round_id, task_id, task_kind, "
                "reviewer_id, staff_id, display_name, decision, rationale, revision, "
                "supersedes_event_id, idempotency_key, canonical_payload_json, "
                "payload_sha256, submitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    round_id,
                    task.task_id,
                    task.kind.value,
                    round_row["reviewer_id"],
                    round_row["staff_id"],
                    round_row["display_name"],
                    command.decision,
                    rationale,
                    current_revision + 1,
                    None if current is None else current["event_id"],
                    command.idempotency_key,
                    payload_json,
                    payload_sha256,
                    submitted_at,
                ),
            )
            connection.execute(
                "DELETE FROM drafts WHERE round_id = ? AND task_id = ?",
                (round_id, task.task_id),
            )
            connection.execute(
                "UPDATE rounds SET updated_at = ? WHERE round_id = ?",
                (submitted_at, round_id),
            )
            lifecycle = self._recompute_round_lifecycle(
                connection,
                round_id=round_id,
                current_lifecycle=round_row["lifecycle"],
            )
            connection.execute(
                "UPDATE rounds SET lifecycle = ? WHERE round_id = ?",
                (lifecycle, round_id),
            )
            round_row = connection.execute(
                "SELECT * FROM rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            view = self._workspace_view(
                connection,
                round_row=round_row,
                requested_task_id=None,
            )
            serialized_view = _canonical_bytes(view.model_dump(mode="json")).decode(
                "utf-8"
            )
            connection.execute(
                "INSERT INTO idempotency_receipts(idempotency_key, event_id, round_id, "
                "workspace_view_json, view_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    command.idempotency_key,
                    event_id,
                    round_id,
                    serialized_view,
                    hashlib.sha256(serialized_view.encode("utf-8")).hexdigest(),
                    submitted_at,
                ),
            )
            connection.commit()
            return view
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

    def _seal_calibration(self, command: SealCalibration) -> SealedWorkspaceView:
        _reject_sensitive_text(command.idempotency_key)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            round_id = str(round_row["round_id"])
            command_sha256 = _canonical_sha256(
                {
                    "action": command.action,
                    "expected_revision": command.expected_revision,
                    "round_id": round_id,
                }
            )
            replay = self._seal_replay(
                connection,
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
            )
            if replay is not None:
                connection.commit()
                return replay
            if round_row["lifecycle"] != "in_progress":
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            human_rows, human_snapshot_sha256 = self._calibration_snapshot(
                connection, round_id=round_id
            )
            disposition = self._judge_run_disposition(
                connection,
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
                human_snapshot_sha256=human_snapshot_sha256,
                authorization_sha256=None,
            )
            connection.commit()
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

        if isinstance(disposition, SealedWorkspaceView):
            return disposition
        if disposition == "wait":
            return self._wait_for_judge_run(
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
                human_snapshot_sha256=human_snapshot_sha256,
            )

        authorization, authorization_sha256 = self._bound_authorization(
            round_id=round_id
        )
        run_id = f"judge-run:{self._id_factory()}"
        started_at = _timestamp(self._clock())

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            if str(round_row["round_id"]) != round_id:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
            replay = self._seal_replay(
                connection,
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
            )
            if replay is not None:
                connection.commit()
                return replay
            current_rows, current_snapshot_sha256 = self._calibration_snapshot(
                connection, round_id=round_id
            )
            if current_snapshot_sha256 != human_snapshot_sha256:
                raise ReviewWorkspaceError(
                    ReviewErrorCode.STALE_REVISION,
                    current_revision=sum(int(row["revision"]) for row in current_rows),
                )
            if round_row["lifecycle"] != "in_progress":
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            disposition = self._judge_run_disposition(
                connection,
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
                human_snapshot_sha256=human_snapshot_sha256,
                authorization_sha256=authorization_sha256,
            )
            if isinstance(disposition, SealedWorkspaceView):
                connection.commit()
                return disposition
            if disposition == "wait":
                connection.commit()
            else:
                authorization_json = _canonical_bytes(authorization).decode("utf-8")
                existing_authorization = connection.execute(
                    "SELECT authorization_json, authorization_sha256 "
                    "FROM judge_authorizations WHERE round_id = ?",
                    (round_id,),
                ).fetchone()
                if existing_authorization is None:
                    connection.execute(
                        "INSERT INTO judge_authorizations(round_id, authorization_json, "
                        "authorization_sha256, created_at) VALUES (?, ?, ?, ?)",
                        (
                            round_id,
                            authorization_json,
                            authorization_sha256,
                            started_at,
                        ),
                    )
                elif (
                    existing_authorization["authorization_json"] != authorization_json
                    or existing_authorization["authorization_sha256"]
                    != authorization_sha256
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
                connection.execute(
                    "INSERT INTO judge_runs(run_id, round_id, idempotency_key, "
                    "command_sha256, human_snapshot_sha256, authorization_sha256, "
                    "evidence_class, runtime_instance_id, started_at, state, failure_code, finished_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_flight', NULL, NULL)",
                    (
                        run_id,
                        round_id,
                        command.idempotency_key,
                        command_sha256,
                        human_snapshot_sha256,
                        authorization_sha256,
                        self._evidence_class.value,
                        self._runtime_instance_id,
                        started_at,
                    ),
                )
                connection.commit()
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

        if disposition == "wait":
            return self._wait_for_judge_run(
                round_id=round_id,
                idempotency_key=command.idempotency_key,
                command_sha256=command_sha256,
                human_snapshot_sha256=human_snapshot_sha256,
            )

        try:
            judged = self._run_judge(human_rows)
            self._assert_artifacts_current()
            return self._complete_judge_run(
                command=command,
                round_id=round_id,
                run_id=run_id,
                command_sha256=command_sha256,
                human_snapshot_sha256=human_snapshot_sha256,
                authorization_sha256=authorization_sha256,
                judged=judged,
            )
        except ReviewWorkspaceError as exc:
            self._fail_judge_run(run_id=run_id, failure_code=exc.code.value)
            raise

    def _complete_judge_run(
        self,
        *,
        command: SealCalibration,
        round_id: str,
        run_id: str,
        command_sha256: str,
        human_snapshot_sha256: str,
        authorization_sha256: str,
        judged: tuple[_JudgedTask, ...],
    ) -> SealedWorkspaceView:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            round_row = self._round_for_token(connection, command.session_token)
            if str(round_row["round_id"]) != round_id:
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_SESSION)
            run_row = connection.execute(
                "SELECT * FROM judge_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if (
                run_row is None
                or run_row["state"] != "in_flight"
                or run_row["round_id"] != round_id
                or run_row["idempotency_key"] != command.idempotency_key
                or run_row["command_sha256"] != command_sha256
                or run_row["human_snapshot_sha256"] != human_snapshot_sha256
                or run_row["authorization_sha256"] != authorization_sha256
            ):
                raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
            current_rows, current_snapshot_sha256 = self._calibration_snapshot(
                connection, round_id=round_id
            )
            if current_snapshot_sha256 != human_snapshot_sha256:
                raise ReviewWorkspaceError(
                    ReviewErrorCode.STALE_REVISION,
                    current_revision=sum(int(row["revision"]) for row in current_rows),
                )
            if round_row["lifecycle"] != "in_progress":
                raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
            summary = self._calibration_summary(
                judged=judged,
                human_snapshot_sha256=human_snapshot_sha256,
                authorization_sha256=authorization_sha256,
                evidence_class=self._evidence_class,
            )
            for result in judged:
                persisted_response = _validated_judge_response(
                    result.response_json, result.response_sha256
                )
                if (
                    persisted_response != result.response
                    or persisted_response.request_sha256
                    != _canonical_sha256(result.task.payload)
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            sealed_at = _timestamp(self._clock())
            connection.executemany(
                "INSERT INTO judge_results(result_id, run_id, round_id, task_id, "
                "request_sha256, response_json, response_sha256, decision, model_id, "
                "judge_policy_id, authorization_sha256, judged_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(
                    (
                        f"judge-result:{self._id_factory()}",
                        run_id,
                        round_id,
                        result.task.task_id,
                        result.response.request_sha256,
                        result.response_json,
                        result.response_sha256,
                        result.response.decision,
                        result.response.model_id,
                        result.response.policy_id,
                        authorization_sha256,
                        result.judged_at,
                    )
                    for result in judged
                ),
            )
            lifecycle = self._derive_lifecycle(
                connection, round_id=round_id, calibration_passed=summary.passed
            )
            connection.execute(
                "UPDATE rounds SET lifecycle = ?, updated_at = ? WHERE round_id = ?",
                (lifecycle, sealed_at, round_id),
            )
            current_round = connection.execute(
                "SELECT * FROM rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            view = self._workspace_view(
                connection,
                round_row=current_round,
                requested_task_id=None,
                calibration_override=summary,
            )
            if not isinstance(view, SealedWorkspaceView):
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            summary_json = _canonical_bytes(summary.model_dump(mode="json")).decode(
                "utf-8"
            )
            serialized_view = _canonical_bytes(view.model_dump(mode="json")).decode(
                "utf-8"
            )
            connection.execute(
                "INSERT INTO calibration_seals(seal_id, round_id, idempotency_key, "
                "run_id, command_sha256, human_snapshot_sha256, authorization_sha256, "
                "summary_json, summary_sha256, workspace_view_json, view_sha256, "
                "passed, sealed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"calibration-seal:{self._id_factory()}",
                    round_id,
                    command.idempotency_key,
                    run_id,
                    command_sha256,
                    human_snapshot_sha256,
                    authorization_sha256,
                    summary_json,
                    hashlib.sha256(summary_json.encode("utf-8")).hexdigest(),
                    serialized_view,
                    hashlib.sha256(serialized_view.encode("utf-8")).hexdigest(),
                    int(summary.passed),
                    sealed_at,
                ),
            )
            completed = connection.execute(
                "UPDATE judge_runs SET state = 'completed', failure_code = NULL, "
                "finished_at = ? WHERE run_id = ? AND state = 'in_flight'",
                (sealed_at, run_id),
            )
            if completed.rowcount != 1:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            connection.commit()
            return view
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

    def _judge_run_disposition(
        self,
        connection: sqlite3.Connection,
        *,
        round_id: str,
        idempotency_key: str,
        command_sha256: str,
        human_snapshot_sha256: str,
        authorization_sha256: str | None,
    ) -> SealedWorkspaceView | Literal["wait"] | None:
        run = connection.execute(
            "SELECT * FROM judge_runs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if run is not None:
            mismatched = (
                run["round_id"] != round_id
                or run["command_sha256"] != command_sha256
                or run["human_snapshot_sha256"] != human_snapshot_sha256
                or (
                    authorization_sha256 is not None
                    and run["authorization_sha256"] != authorization_sha256
                )
            )
            if mismatched:
                raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
            if run["state"] == "failed":
                raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
            if run["state"] == "in_flight":
                if run["runtime_instance_id"] != self._runtime_instance_id:
                    raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_RECOVERY_REQUIRED)
                return "wait"
            replay = self._seal_replay(
                connection,
                round_id=round_id,
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
            )
            if replay is None:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            return replay
        in_flight = connection.execute(
            "SELECT idempotency_key, runtime_instance_id FROM judge_runs "
            "WHERE round_id = ? AND state = 'in_flight'",
            (round_id,),
        ).fetchone()
        if in_flight is not None:
            if in_flight["runtime_instance_id"] != self._runtime_instance_id:
                raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_RECOVERY_REQUIRED)
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
        return None

    def _wait_for_judge_run(
        self,
        *,
        round_id: str,
        idempotency_key: str,
        command_sha256: str,
        human_snapshot_sha256: str,
    ) -> SealedWorkspaceView:
        deadline = time.monotonic() + _JUDGE_RUN_WAIT_SECONDS
        while time.monotonic() < deadline:
            connection = self._connection()
            try:
                run = connection.execute(
                    "SELECT * FROM judge_runs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if run is None:
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
                if (
                    run["round_id"] != round_id
                    or run["command_sha256"] != command_sha256
                    or run["human_snapshot_sha256"] != human_snapshot_sha256
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
                if run["state"] == "failed":
                    raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
                if (
                    run["state"] == "in_flight"
                    and run["runtime_instance_id"] != self._runtime_instance_id
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_RECOVERY_REQUIRED)
                if run["state"] == "completed":
                    replay = self._seal_replay(
                        connection,
                        round_id=round_id,
                        idempotency_key=idempotency_key,
                        command_sha256=command_sha256,
                    )
                    if replay is None:
                        raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
                    return replay
            except ReviewWorkspaceError:
                raise
            except _EXPECTED_STORAGE_ERRORS as exc:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
            finally:
                connection.close()
            time.sleep(_JUDGE_RUN_POLL_SECONDS)
        raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)

    def _fail_judge_run(self, *, run_id: str, failure_code: str) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT state FROM judge_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            if run["state"] == "in_flight":
                connection.execute(
                    "UPDATE judge_runs SET state = 'failed', failure_code = ?, "
                    "finished_at = ? WHERE run_id = ? AND state = 'in_flight'",
                    (failure_code, _timestamp(self._clock()), run_id),
                )
            connection.commit()
        except ReviewWorkspaceError:
            _rollback_after_failure(connection)
            raise
        except _EXPECTED_STORAGE_ERRORS as exc:
            _rollback_after_failure(connection)
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        finally:
            connection.close()

    def _seal_replay(
        self,
        connection: sqlite3.Connection,
        *,
        round_id: str,
        idempotency_key: str,
        command_sha256: str,
    ) -> SealedWorkspaceView | None:
        by_key = connection.execute(
            "SELECT * FROM calibration_seals WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if by_key is not None:
            if (
                by_key["round_id"] != round_id
                or by_key["command_sha256"] != command_sha256
            ):
                raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
            return self._validated_seal_receipt(by_key)
        by_round = connection.execute(
            "SELECT idempotency_key FROM calibration_seals WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        if by_round is not None:
            raise ReviewWorkspaceError(ReviewErrorCode.IDEMPOTENCY_CONFLICT)
        return None

    def _calibration_snapshot(
        self, connection: sqlite3.Connection, *, round_id: str
    ) -> tuple[tuple[sqlite3.Row, ...], str]:
        latest = {
            row["task_id"]: row
            for row in connection.execute(
                "SELECT e.* FROM decision_events e JOIN ("
                "SELECT task_id, max(revision) AS revision FROM decision_events "
                "WHERE round_id = ? AND task_kind = 'calibration' GROUP BY task_id"
                ") current ON current.task_id = e.task_id "
                "AND current.revision = e.revision WHERE e.round_id = ?",
                (round_id, round_id),
            )
        }
        calibration_tasks = tuple(
            self._tasks[task_id]
            for task_id in self._task_order
            if self._tasks[task_id].kind is TaskKind.CALIBRATION
        )
        if len(latest) != 60 or len(calibration_tasks) != 60:
            raise ReviewWorkspaceError(ReviewErrorCode.CALIBRATION_NOT_SEALED)
        ordered: list[sqlite3.Row] = []
        snapshot: list[dict[str, JsonValue]] = []
        for task in calibration_tasks:
            row = latest.get(task.task_id)
            if row is None or row["decision"] not in {"supported", "unsupported"}:
                raise ReviewWorkspaceError(ReviewErrorCode.CALIBRATION_NOT_SEALED)
            ordered.append(row)
            snapshot.append(
                {
                    "decision": row["decision"],
                    "event_id": row["event_id"],
                    "payload_sha256": row["payload_sha256"],
                    "revision": row["revision"],
                    "task_id": row["task_id"],
                }
            )
        return tuple(ordered), _canonical_sha256(snapshot)

    def _bound_authorization(
        self, *, round_id: str
    ) -> tuple[dict[str, JsonValue], str]:
        judge = self._judge
        provider = self._judge_authorization_provider
        if judge is None or provider is None:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
        workload_content_sha256 = str(
            self._artifacts.identity["workload_content_sha256"]
        )
        try:
            supplied = provider.authorize(
                round_id=round_id,
                workload_content_sha256=workload_content_sha256,
                evidence_class=self._evidence_class,
            )
            authorization = JudgeAuthorization.model_validate(
                supplied.model_dump(mode="json")
            )
        except Exception:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE) from None
        content = authorization.model_dump(mode="json", exclude={"content_sha256"})
        serialized_content = _canonical_bytes(content).decode("utf-8")
        if (
            authorization.content_sha256
            != hashlib.sha256(serialized_content.encode("utf-8")).hexdigest()
            or authorization.evidence_class is not self._evidence_class
            or authorization.round_id != round_id
            or authorization.model_id != judge.model_id
            or authorization.provider_profile != judge.provider_profile
            or authorization.calibration_policy_id != _CALIBRATION_POLICY_ID
            or authorization.judge_policy_id != _JUDGE_POLICY_ID
            or authorization.workload_content_sha256 != workload_content_sha256
            or authorization.authorized_at.tzinfo is None
            or "://" in authorization.model_id
            or any(
                _SENSITIVE_TEXT.search(value)
                for value in (
                    authorization.authorizer_id,
                    authorization.provider_profile,
                    authorization.model_id,
                )
            )
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
        bound = authorization.model_dump(mode="json")
        return bound, authorization.content_sha256

    def _run_judge(
        self, human_rows: tuple[sqlite3.Row, ...]
    ) -> tuple[_JudgedTask, ...]:
        judge = self._judge
        if judge is None:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
        rows_by_task = {str(row["task_id"]): row for row in human_rows}
        results: list[_JudgedTask] = []
        try:
            for task_id in self._task_order:
                task = self._tasks[task_id]
                if task.kind is not TaskKind.CALIBRATION:
                    continue
                request = json.loads(_canonical_bytes(task.payload))
                _walk_forbidden_labels(request)
                raw_response = judge.judge(request)
                response = _JudgeResponse.model_validate(raw_response)
                request_sha256 = _canonical_sha256(request)
                if (
                    response.model_id != judge.model_id
                    or response.policy_id != _JUDGE_POLICY_ID
                    or response.request_sha256 != request_sha256
                ):
                    raise ValueError("cross-wired judge response")
                response_json = _canonical_bytes(
                    response.model_dump(mode="json")
                ).decode("utf-8")
                response_sha256 = hashlib.sha256(
                    response_json.encode("utf-8")
                ).hexdigest()
                if (
                    _validated_judge_response(response_json, response_sha256)
                    != response
                ):
                    raise ValueError("judge response validation")
                human_row = rows_by_task[task.task_id]
                results.append(
                    _JudgedTask(
                        task=task,
                        human_decision=human_row["decision"],
                        response=response,
                        response_json=response_json,
                        response_sha256=response_sha256,
                        judged_at=_timestamp(self._clock()),
                    )
                )
        except Exception:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE) from None
        if len(results) != 60:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
        return tuple(results)

    @staticmethod
    def _calibration_summary(
        *,
        judged: tuple[_JudgedTask, ...],
        human_snapshot_sha256: str,
        authorization_sha256: str,
        evidence_class: EvidenceClass,
    ) -> CalibrationSummary:
        strata = Counter(
            str(_task_audit_payload(result.task)["stratum"]) for result in judged
        )
        human_supported = sum(result.human_decision == "supported" for result in judged)
        human_unsupported = len(judged) - human_supported
        matches = sum(
            result.human_decision == result.response.decision for result in judged
        )
        confusion = {
            "human_supported_model_supported": 0,
            "human_supported_model_unsupported": 0,
            "human_unsupported_model_supported": 0,
            "human_unsupported_model_unsupported": 0,
        }
        for result in judged:
            key = f"human_{result.human_decision}_model_{result.response.decision}"
            confusion[key] += 1
        unsupported_critical = sum(
            result.human_decision == "unsupported"
            and _task_audit_payload(result.task).get("critical_probe") is True
            for result in judged
        )
        critical_false_accepts = sum(
            result.human_decision == "unsupported"
            and result.response.decision == "supported"
            and _task_audit_payload(result.task).get("critical_probe") is True
            for result in judged
        )
        agreement = matches / len(judged) if judged else 0.0
        gates = CalibrationGateStatus(
            exact_pair_count=len(judged) == 60,
            exact_stratum_quotas=dict(strata) == _EXPECTED_STRATA,
            minimum_agreement=agreement >= 0.80,
            minimum_supported_labels=human_supported >= 10,
            minimum_unsupported_labels=human_unsupported >= 10,
            minimum_unsupported_critical_probes=unsupported_critical >= 5,
            maximum_critical_false_accepts=critical_false_accepts == 0,
        )
        passed = all(gates.model_dump().values())
        first = judged[0]
        return CalibrationSummary(
            evidence_class=evidence_class,
            pair_count=len(judged),
            stratum_counts=dict(sorted(strata.items())),
            human_supported=human_supported,
            human_unsupported=human_unsupported,
            agreement=agreement,
            confusion_matrix=confusion,
            unsupported_critical_probes=unsupported_critical,
            critical_false_accepts=critical_false_accepts,
            gates=gates,
            passed=passed,
            model_id=first.response.model_id,
            calibration_policy_id=_CALIBRATION_POLICY_ID,
            judge_policy_id=first.response.policy_id,
            authorization_sha256=authorization_sha256,
            human_snapshot_sha256=human_snapshot_sha256,
            judgments=tuple(
                CalibrationJudgment(
                    task_id=result.task.task_id,
                    sample_id=str(result.task.payload["sample_id"]),
                    stratum=str(_task_audit_payload(result.task)["stratum"]),
                    critical_probe=(
                        _task_audit_payload(result.task).get("critical_probe") is True
                    ),
                    request_sha256=result.response.request_sha256,
                    response_sha256=result.response_sha256,
                    human_decision=result.human_decision,
                    model_decision=result.response.decision,
                )
                for result in judged
            ),
        )

    def _derive_lifecycle(
        self,
        connection: sqlite3.Connection,
        *,
        round_id: str,
        calibration_passed: bool,
    ) -> str:
        if not calibration_passed:
            return "calibration_failed_sealed"
        current = {
            row["task_id"]: row["decision"]
            for row in connection.execute(
                "SELECT e.task_id, e.decision FROM decision_events e JOIN ("
                "SELECT task_id, max(revision) AS revision FROM decision_events "
                "WHERE round_id = ? AND task_kind != 'calibration' GROUP BY task_id"
                ") latest ON latest.task_id = e.task_id AND latest.revision = e.revision "
                "WHERE e.round_id = ?",
                (round_id, round_id),
            )
        }
        required = tuple(
            self._tasks[task_id]
            for task_id in self._task_order
            if self._tasks[task_id].kind is not TaskKind.CALIBRATION
        )
        if len(current) != 52:
            return "human_labels_sealed"
        accepting = all(
            current.get(task.task_id) in _ACCEPTING_DECISIONS[task.kind]
            for task in required
        )
        return "acceptance_ready" if accepting else "review_complete_blocked"

    @staticmethod
    def _task_read_only_reason(*, task: _Task, lifecycle: str) -> str | None:
        if lifecycle == "locked":
            return "round_locked"
        if task.kind is TaskKind.CALIBRATION and lifecycle != "in_progress":
            return "calibration_labels_sealed"
        if task.kind is not TaskKind.CALIBRATION and lifecycle not in {
            "in_progress",
            "calibration_failed_sealed",
            "human_labels_sealed",
            "review_complete_blocked",
            "acceptance_ready",
        }:
            return "round_not_mutable"
        return None

    @classmethod
    def _task_is_mutable(cls, *, task: _Task, lifecycle: str) -> bool:
        return cls._task_read_only_reason(task=task, lifecycle=lifecycle) is None

    def _review_gate_summary(
        self,
        *,
        latest: dict[str, sqlite3.Row],
        lifecycle: str,
        calibration_passed: bool | None,
    ) -> ReviewGateSummary:
        current = {task_id: str(row["decision"]) for task_id, row in latest.items()}
        missing_task_ids = tuple(
            task_id for task_id in self._task_order if task_id not in current
        )
        blocking_task_ids = tuple(
            task_id
            for task_id in self._task_order
            if task_id in current
            and current[task_id] not in _ACCEPTING_DECISIONS[self._tasks[task_id].kind]
        )
        blocking_reasons = {task_id: current[task_id] for task_id in blocking_task_ids}

        def coverage(*, field: str, kind: TaskKind | None) -> dict[str, ReviewCoverage]:
            counters: dict[str, Counter[str]] = {}
            for task_id in self._task_order:
                task = self._tasks[task_id]
                if kind is None:
                    if task.kind is TaskKind.CALIBRATION:
                        continue
                elif task.kind is not kind:
                    continue
                group = str(_task_audit_payload(task)[field])
                counts = counters.setdefault(group, Counter())
                counts["total"] += 1
                decision = current.get(task_id)
                if decision is None:
                    counts["missing"] += 1
                else:
                    counts["submitted"] += 1
                    if decision in _ACCEPTING_DECISIONS[task.kind]:
                        counts["accepting"] += 1
                    else:
                        counts["blocking"] += 1
            return {
                group: ReviewCoverage(
                    total=counts["total"],
                    submitted=counts["submitted"],
                    accepting=counts["accepting"],
                    blocking=counts["blocking"],
                    missing=counts["missing"],
                )
                for group, counts in sorted(counters.items())
            }

        calibration_task_ids = tuple(
            task_id
            for task_id in self._task_order
            if self._tasks[task_id].kind is TaskKind.CALIBRATION
        )
        calibration_labels_valid = (
            all(
                current.get(task_id) in _ACCEPTING_DECISIONS[TaskKind.CALIBRATION]
                for task_id in calibration_task_ids
            )
            and len(calibration_task_ids) == self._artifacts.counts.calibration_probes
        )

        blockers: list[AcceptanceBlocker] = []
        if missing_task_ids:
            blockers.append("human_decisions_missing")
        if blocking_task_ids:
            blockers.append("human_decisions_blocking")
        if calibration_passed is None:
            blockers.append("calibration_not_sealed")
        elif not calibration_passed:
            blockers.append("calibration_failed")
        if lifecycle == "locked":
            blockers.append("round_locked")

        return ReviewGateSummary(
            missing_task_ids=missing_task_ids,
            blocking_task_ids=blocking_task_ids,
            blocking_reasons=blocking_reasons,
            family_coverage=coverage(field="family", kind=None),
            stratum_coverage=coverage(field="stratum", kind=TaskKind.CALIBRATION),
            calibration_labels_valid=calibration_labels_valid,
            calibration_ready_to_seal=(
                lifecycle == "in_progress" and calibration_labels_valid
            ),
            acceptance_ready=lifecycle == "acceptance_ready",
            acceptance_blockers=tuple(blockers),
        )

    def _recompute_round_lifecycle(
        self,
        connection: sqlite3.Connection,
        *,
        round_id: str,
        current_lifecycle: str,
    ) -> str:
        if current_lifecycle == "locked":
            return "locked"
        seal = connection.execute(
            "SELECT passed FROM calibration_seals WHERE round_id = ?", (round_id,)
        ).fetchone()
        if seal is None:
            return "in_progress"
        return self._derive_lifecycle(
            connection,
            round_id=round_id,
            calibration_passed=bool(seal["passed"]),
        )

    @staticmethod
    def _validated_receipt(row: sqlite3.Row) -> WorkspaceView | SealedWorkspaceView:
        serialized = row["workspace_view_json"]
        claimed_sha256 = row["view_sha256"]
        if not isinstance(serialized, str) or not isinstance(claimed_sha256, str):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != claimed_sha256:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        payload = json.loads(serialized)
        if _canonical_bytes(payload).decode("utf-8") != serialized:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        view: WorkspaceView | SealedWorkspaceView
        if "calibration" in payload:
            view = SealedWorkspaceView.model_validate(payload)
        else:
            view = WorkspaceView.model_validate(payload)
        if _canonical_bytes(view.model_dump(mode="json")).decode("utf-8") != serialized:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        if view.round_id != row["round_id"]:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        return view

    @staticmethod
    def _validated_seal_receipt(row: sqlite3.Row) -> SealedWorkspaceView:
        view = ReviewWorkspace._validated_receipt(row)
        if not isinstance(view, SealedWorkspaceView):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        return view

    @staticmethod
    def _validate_decision(
        *,
        task: _Task,
        command: SubmitDecision,
        rationale: str | None,
        superseding: bool,
    ) -> None:
        allowed = {
            TaskKind.CONTRACT: {
                "approved",
                "needs_change",
                "unable_to_determine",
            },
            TaskKind.EXCLUSION: {
                "accept_exclusion",
                "require_evidence",
                "unable_to_determine",
            },
            TaskKind.CALIBRATION: {
                "supported",
                "unsupported",
                "unable_to_determine",
            },
        }
        rationale_required = (
            superseding
            or task.kind is TaskKind.EXCLUSION
            or (
                task.kind is TaskKind.CONTRACT
                and command.decision in {"needs_change", "unable_to_determine"}
            )
        )
        if (
            command.task_kind is not task.kind
            or command.decision not in allowed[task.kind]
            or (rationale_required and not rationale)
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.INVALID_DECISION)

    def _require_task(self, task_id: str) -> _Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise ReviewWorkspaceError(ReviewErrorCode.UNKNOWN_TASK)
        return task

    def _validated_judge_results(
        self, connection: sqlite3.Connection, *, round_id: str
    ) -> dict[str, sqlite3.Row]:
        rows = tuple(
            connection.execute(
                "SELECT * FROM judge_results WHERE round_id = ? ORDER BY task_id",
                (round_id,),
            )
        )
        expected_task_ids = {
            task.task_id
            for task in self._artifacts.tasks
            if task.kind is TaskKind.CALIBRATION
        }
        if (
            len(rows) != 60
            or {str(row["task_id"]) for row in rows} != expected_task_ids
        ):
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
        try:
            for row in rows:
                task = self._tasks[str(row["task_id"])]
                response = _validated_judge_response(
                    row["response_json"], row["response_sha256"]
                )
                if (
                    response.request_sha256 != _canonical_sha256(task.payload)
                    or response.request_sha256 != row["request_sha256"]
                    or response.decision != row["decision"]
                    or response.model_id != row["model_id"]
                    or response.policy_id != row["judge_policy_id"]
                ):
                    raise ValueError("judge response projection mismatch")
        except (KeyError, TypeError, ValueError, sqlite3.Error, ValidationError) as exc:
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE) from exc
        return {str(row["task_id"]): row for row in rows}

    def _workspace_view(
        self,
        connection: sqlite3.Connection,
        *,
        round_row: sqlite3.Row,
        requested_task_id: str | None,
        issued_token: str | None = None,
        calibration_override: CalibrationSummary | None = None,
    ) -> WorkspaceView | SealedWorkspaceView:
        round_id = str(round_row["round_id"])
        lifecycle = str(round_row["lifecycle"])
        calibration = calibration_override
        if calibration is None:
            seal_row = connection.execute(
                "SELECT summary_json, summary_sha256 FROM calibration_seals "
                "WHERE round_id = ?",
                (round_id,),
            ).fetchone()
            if seal_row is not None:
                summary_json = seal_row["summary_json"]
                if (
                    hashlib.sha256(summary_json.encode("utf-8")).hexdigest()
                    != seal_row["summary_sha256"]
                ):
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
                summary_payload = json.loads(summary_json)
                if _canonical_bytes(summary_payload).decode("utf-8") != summary_json:
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
                calibration = CalibrationSummary.model_validate(summary_payload)
        judgment_rows = (
            {}
            if calibration is None
            else self._validated_judge_results(connection, round_id=round_id)
        )
        latest = {
            row["task_id"]: row
            for row in connection.execute(
                "SELECT e.* FROM decision_events e JOIN ("
                "SELECT task_id, max(revision) AS revision FROM decision_events "
                "WHERE round_id = ? GROUP BY task_id"
                ") current ON current.task_id = e.task_id "
                "AND current.revision = e.revision WHERE e.round_id = ?",
                (round_id, round_id),
            )
        }
        gate_summary = self._review_gate_summary(
            latest=latest,
            lifecycle=lifecycle,
            calibration_passed=(None if calibration is None else calibration.passed),
        )
        if requested_task_id is not None:
            task = self._require_task(requested_task_id)
        else:
            task = next(
                (
                    self._tasks[task_id]
                    for task_id in self._task_order
                    if task_id not in latest
                ),
                None,
            )
        task_view: ReviewTaskView | RevealedReviewTaskView | None = None
        current_position: int | None = None
        if task is not None:
            current_position = self._task_order.index(task.task_id) + 1
            draft_row = connection.execute(
                "SELECT payload_json FROM drafts WHERE round_id = ? AND task_id = ?",
                (round_id, task.task_id),
            ).fetchone()
            decision_row = latest.get(task.task_id)
            read_only_reason = self._task_read_only_reason(
                task=task,
                lifecycle=lifecycle,
            )
            task_fields = {
                "task_id": task.task_id,
                "kind": task.kind,
                "payload": json.loads(_canonical_bytes(task.payload)),
                "draft": (
                    None
                    if draft_row is None
                    else DraftData.model_validate(json.loads(draft_row["payload_json"]))
                ),
                "current_decision": (
                    None
                    if decision_row is None
                    else ReviewDecisionView(
                        event_id=decision_row["event_id"],
                        reviewer_id=decision_row["reviewer_id"],
                        staff_id=decision_row["staff_id"],
                        decision=decision_row["decision"],
                        rationale=decision_row["rationale"],
                        revision=decision_row["revision"],
                        supersedes_event_id=decision_row["supersedes_event_id"],
                        submitted_at=decision_row["submitted_at"],
                        payload_sha256=decision_row["payload_sha256"],
                    )
                ),
                "revision": 0 if decision_row is None else decision_row["revision"],
                "review_context": task.review_context,
                "mutable": read_only_reason is None,
                "read_only_reason": read_only_reason,
            }
            judgment_row = None
            if calibration is not None and task.kind is TaskKind.CALIBRATION:
                judgment_row = judgment_rows.get(task.task_id)
                if judgment_row is None:
                    raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
            if judgment_row is not None:
                task_view = RevealedReviewTaskView(
                    **task_fields,
                    model_judgment=judgment_row["decision"],
                    judge_request_sha256=judgment_row["request_sha256"],
                    judge_response_sha256=judgment_row["response_sha256"],
                )
            else:
                task_view = ReviewTaskView(**task_fields)
        kind_counts = Counter(self._tasks[task_id].kind for task_id in latest)
        submitted = len(latest)
        queue = tuple(
            ReviewTaskSummary(
                task_id=task_id,
                kind=self._tasks[task_id].kind,
                position=position,
                status="submitted" if task_id in latest else "pending",
                revision=(0 if task_id not in latest else latest[task_id]["revision"]),
                current_decision=(
                    None if task_id not in latest else latest[task_id]["decision"]
                ),
            )
            for position, task_id in enumerate(self._task_order, start=1)
        )
        common = {
            "round_id": round_id,
            "evidence_class": self._evidence_class,
            "reviewer": ReviewerView(
                reviewer_id=round_row["reviewer_id"],
                display_name=round_row["display_name"],
                staff_id=round_row["staff_id"],
            ),
            "session_token": issued_token,
            "counts": self._artifacts.counts,
            "progress": ReviewProgress(
                total=112,
                submitted=submitted,
                remaining=112 - submitted,
                contract_submitted=kind_counts[TaskKind.CONTRACT],
                exclusion_submitted=kind_counts[TaskKind.EXCLUSION],
                calibration_submitted=kind_counts[TaskKind.CALIBRATION],
                current_position=current_position,
            ),
            "queue": queue,
            "task": task_view,
            "lifecycle": lifecycle,
            "artifact_identity": self._artifacts.header_identity,
            "judge_configured": (
                self._judge is not None
                and self._judge_authorization_provider is not None
            ),
            "gate_summary": gate_summary,
        }
        if calibration is not None:
            return SealedWorkspaceView(**common, calibration=calibration)
        return WorkspaceView(**common)


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS workspace_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS rounds (
        round_id TEXT PRIMARY KEY,
        reviewer_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        staff_id TEXT NOT NULL,
        lifecycle TEXT NOT NULL CHECK (
            lifecycle IN (
                'in_progress', 'calibration_failed_sealed',
                'human_labels_sealed', 'review_complete_blocked',
                'acceptance_ready', 'locked'
            )
        ),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS drafts (
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        task_id TEXT NOT NULL,
        task_kind TEXT NOT NULL CHECK (
            task_kind IN ('contract', 'exclusion', 'calibration')
        ),
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (round_id, task_id)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_events (
        event_id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        task_id TEXT NOT NULL,
        task_kind TEXT NOT NULL CHECK (
            task_kind IN ('contract', 'exclusion', 'calibration')
        ),
        reviewer_id TEXT NOT NULL,
        staff_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        decision TEXT NOT NULL,
        rationale TEXT,
        revision INTEGER NOT NULL CHECK (revision > 0),
        supersedes_event_id TEXT REFERENCES decision_events(event_id),
        idempotency_key TEXT NOT NULL UNIQUE,
        canonical_payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        submitted_at TEXT NOT NULL,
        UNIQUE (round_id, task_id, revision),
        UNIQUE (idempotency_key, event_id, round_id)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS idempotency_receipts (
        idempotency_key TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        round_id TEXT NOT NULL,
        workspace_view_json TEXT NOT NULL,
        view_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (idempotency_key, event_id, round_id)
            REFERENCES decision_events(idempotency_key, event_id, round_id)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_authorizations (
        round_id TEXT PRIMARY KEY REFERENCES rounds(round_id),
        authorization_json TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_runs (
        run_id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        idempotency_key TEXT NOT NULL UNIQUE,
        command_sha256 TEXT NOT NULL,
        human_snapshot_sha256 TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL REFERENCES judge_authorizations(authorization_sha256),
        evidence_class TEXT NOT NULL CHECK (evidence_class IN ('implementation_test', 'real_human_round')),
        runtime_instance_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('in_flight', 'failed', 'completed')),
        failure_code TEXT,
        finished_at TEXT,
        UNIQUE (round_id, run_id)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_run_recoveries (
        recovery_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES judge_runs(run_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        command_sha256 TEXT NOT NULL,
        human_snapshot_sha256 TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL REFERENCES judge_authorizations(authorization_sha256),
        operator_staff_id TEXT NOT NULL,
        reason TEXT NOT NULL CHECK (reason = 'process_crash_confirmed'),
        recovered_at TEXT NOT NULL,
        UNIQUE(run_id)
    ) STRICT
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS judge_runs_one_in_flight_per_round
    ON judge_runs(round_id) WHERE state = 'in_flight'
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_results (
        result_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES judge_runs(run_id),
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        task_id TEXT NOT NULL,
        request_sha256 TEXT NOT NULL,
        response_json TEXT NOT NULL,
        response_sha256 TEXT NOT NULL,
        decision TEXT NOT NULL CHECK (decision IN ('supported', 'unsupported')),
        model_id TEXT NOT NULL,
        judge_policy_id TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL REFERENCES judge_authorizations(authorization_sha256),
        judged_at TEXT NOT NULL,
        UNIQUE (round_id, task_id),
        UNIQUE (round_id, request_sha256)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS calibration_seals (
        seal_id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL UNIQUE REFERENCES rounds(round_id),
        idempotency_key TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL UNIQUE REFERENCES judge_runs(run_id),
        command_sha256 TEXT NOT NULL,
        human_snapshot_sha256 TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL REFERENCES judge_authorizations(authorization_sha256),
        summary_json TEXT NOT NULL,
        summary_sha256 TEXT NOT NULL,
        workspace_view_json TEXT NOT NULL,
        view_sha256 TEXT NOT NULL,
        passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
        sealed_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS export_records (
        export_id TEXT PRIMARY KEY,
        round_id TEXT NOT NULL REFERENCES rounds(round_id),
        idempotency_key TEXT NOT NULL UNIQUE,
        command_sha256 TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('review_evidence', 'acceptance_candidate')),
        evidence_class TEXT NOT NULL CHECK (evidence_class IN ('implementation_test', 'real_human_round')),
        acceptance_eligible INTEGER NOT NULL CHECK (acceptance_eligible IN (0, 1)),
        task_2_8_eligible INTEGER NOT NULL CHECK (task_2_8_eligible IN (0, 1)),
        basename TEXT NOT NULL UNIQUE,
        raw_sha256 TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        content_length INTEGER NOT NULL CHECK (content_length >= 0),
        content_bytes BLOB NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('prepared', 'verified')),
        created_at TEXT NOT NULL,
        verified_at TEXT
    ) STRICT
    """,
    """
    CREATE TRIGGER IF NOT EXISTS rounds_attribution_immutable
    BEFORE UPDATE OF round_id, reviewer_id, display_name, staff_id, created_at ON rounds
    BEGIN
        SELECT RAISE(ABORT, 'round attribution is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS decision_events_no_update
    BEFORE UPDATE ON decision_events
    BEGIN
        SELECT RAISE(ABORT, 'decision events are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS decision_events_no_delete
    BEFORE DELETE ON decision_events
    BEGIN
        SELECT RAISE(ABORT, 'decision events are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS idempotency_receipts_no_update
    BEFORE UPDATE ON idempotency_receipts
    BEGIN
        SELECT RAISE(ABORT, 'idempotency receipts are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS idempotency_receipts_no_delete
    BEFORE DELETE ON idempotency_receipts
    BEGIN
        SELECT RAISE(ABORT, 'idempotency receipts are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_authorizations_no_update
    BEFORE UPDATE ON judge_authorizations
    BEGIN
        SELECT RAISE(ABORT, 'judge authorizations are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_authorizations_no_delete
    BEFORE DELETE ON judge_authorizations
    BEGIN
        SELECT RAISE(ABORT, 'judge authorizations are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_results_no_update
    BEFORE UPDATE ON judge_results
    BEGIN
        SELECT RAISE(ABORT, 'judge results are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_runs_transition_only
    BEFORE UPDATE ON judge_runs
    WHEN NOT (
        OLD.state = 'in_flight'
        AND NEW.state IN ('failed', 'completed')
        AND NEW.run_id = OLD.run_id
        AND NEW.round_id = OLD.round_id
        AND NEW.idempotency_key = OLD.idempotency_key
        AND NEW.command_sha256 = OLD.command_sha256
        AND NEW.human_snapshot_sha256 = OLD.human_snapshot_sha256
        AND NEW.authorization_sha256 = OLD.authorization_sha256
        AND NEW.evidence_class = OLD.evidence_class
        AND NEW.runtime_instance_id = OLD.runtime_instance_id
        AND NEW.started_at = OLD.started_at
        AND NEW.finished_at IS NOT NULL
        AND (
            (NEW.state = 'failed' AND NEW.failure_code IS NOT NULL)
            OR (NEW.state = 'completed' AND NEW.failure_code IS NULL)
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'judge run transition is invalid');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_runs_no_delete
    BEFORE DELETE ON judge_runs
    BEGIN
        SELECT RAISE(ABORT, 'judge runs are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_run_recoveries_no_update
    BEFORE UPDATE ON judge_run_recoveries
    BEGIN
        SELECT RAISE(ABORT, 'judge run recoveries are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_run_recoveries_no_delete
    BEFORE DELETE ON judge_run_recoveries
    BEGIN
        SELECT RAISE(ABORT, 'judge run recoveries are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS judge_results_no_delete
    BEFORE DELETE ON judge_results
    BEGIN
        SELECT RAISE(ABORT, 'judge results are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS calibration_seals_no_update
    BEFORE UPDATE ON calibration_seals
    BEGIN
        SELECT RAISE(ABORT, 'calibration seals are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS calibration_seals_no_delete
    BEFORE DELETE ON calibration_seals
    BEGIN
        SELECT RAISE(ABORT, 'calibration seals are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS export_records_no_delete
    BEFORE DELETE ON export_records
    BEGIN
        SELECT RAISE(ABORT, 'export records are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS export_records_transition_only
    BEFORE UPDATE ON export_records
    WHEN NOT (OLD.state = 'prepared' AND NEW.state = 'verified'
              AND NEW.export_id = OLD.export_id AND NEW.round_id = OLD.round_id
              AND NEW.idempotency_key = OLD.idempotency_key
              AND NEW.command_sha256 = OLD.command_sha256 AND NEW.mode = OLD.mode
              AND NEW.evidence_class = OLD.evidence_class
              AND NEW.acceptance_eligible = OLD.acceptance_eligible
              AND NEW.task_2_8_eligible = OLD.task_2_8_eligible
              AND NEW.basename = OLD.basename AND NEW.raw_sha256 = OLD.raw_sha256
              AND NEW.content_sha256 = OLD.content_sha256
              AND NEW.content_length = OLD.content_length AND NEW.content_bytes = OLD.content_bytes
              AND NEW.created_at = OLD.created_at AND NEW.verified_at IS NOT NULL)
    BEGIN
        SELECT RAISE(ABORT, 'export record transition is invalid');
    END
    """,
)


def create_review_workspace(
    *,
    packet_path: str | Path,
    workload_path: str | Path,
    source_root: str | Path,
    state_dir: str | Path,
    export_dir: str | Path,
    judge: EvidenceBoundedJudge | None = None,
    judge_authorization_provider: JudgeAuthorizationProvider | None = None,
    evidence_class: EvidenceClass = EvidenceClass.IMPLEMENTATION_TEST,
    runtime_instance_id: str | None = None,
    recovery_only: bool = False,
) -> ReviewWorkspace:
    """Admit frozen artifacts before creating the dedicated SQLite workspace."""

    try:
        evidence_class = EvidenceClass(evidence_class)
    except ValueError as exc:
        raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND) from exc
    runtime_id = runtime_instance_id or _new_runtime_instance_id()
    if not _RUNTIME_INSTANCE_ID.fullmatch(runtime_id) or _SENSITIVE_TEXT.search(
        runtime_id
    ):
        raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
    if recovery_only and (
        judge is not None or judge_authorization_provider is not None
    ):
        raise ReviewWorkspaceError(ReviewErrorCode.INVALID_COMMAND)
    if not recovery_only and (
        (judge is None) is not (judge_authorization_provider is None)
    ):
        raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
    if (
        evidence_class is EvidenceClass.REAL_HUMAN_ROUND
        and not recovery_only
        and judge is not None
    ):
        try:
            real_provider = (
                judge_authorization_provider is not None
                and judge_authorization_provider.is_real_authorization_provider is True
            )
        except Exception:
            real_provider = False
        if type(judge) is not OpenAICompatibleEvidenceBoundedJudge or not real_provider:
            raise ReviewWorkspaceError(ReviewErrorCode.JUDGE_UNAVAILABLE)
    try:
        artifacts = _load_bound_artifacts(
            packet_path=Path(packet_path),
            workload_path=Path(workload_path),
            source_root=Path(source_root),
        )
    except ReviewWorkspaceError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ReviewWorkspaceError(ReviewErrorCode.ARTIFACT_MISMATCH) from exc
    return ReviewWorkspace(
        artifacts=artifacts,
        state_dir=Path(state_dir),
        export_dir=Path(export_dir),
        clock=_now,
        id_factory=_new_id,
        token_factory=_new_token,
        judge=judge,
        judge_authorization_provider=judge_authorization_provider,
        evidence_class=evidence_class,
        runtime_instance_id=runtime_id,
        recovery_only=recovery_only,
    )
