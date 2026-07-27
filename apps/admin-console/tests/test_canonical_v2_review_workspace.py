from __future__ import annotations

from dataclasses import dataclass, replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Event
import time
from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError
import pytest

from backend.services import canonical_v2_review as review_module
from backend.services.canonical_v2_review import (
    AbandonInFlightJudgeRun,
    DraftData,
    ExportMode,
    ExportReview,
    JudgeAuthorization,
    JudgeAuthorizationProvider,
    OpenAICompatibleEvidenceBoundedJudge,
    OpenWorkspace,
    ReviewErrorCode,
    ReviewWorkspaceError,
    ReadExport,
    SaveDraft,
    SealCalibration,
    SubmitDecision,
    TaskKind,
    create_review_workspace,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
REVIEW_SOURCE = (
    REPO_ROOT
    / ".agents"
    / "runs"
    / "rebuild-canonical-v2-knowledge-platform"
    / "s2c"
    / "review"
)
ARTIFACT_NAMES = (
    "human-review-packet-v1.json",
    "human-review-workload-v2.json",
    "calibration-policy-v2.json",
    "calibration-observation-bank-v2.jsonl",
    "calibration-observation-bank-v2-provenance.json",
)
S2C_CONTEXT_PATHS = tuple(
    Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c") / name
    for name in (
        "claim-level-corpus-v1.jsonl",
        "case-accounting-v1.jsonl",
        "source-snapshots-v1.jsonl",
        "claim-level-corpus-manifest-v1.json",
    )
)
RENDERER_FILES = (
    "review.html",
    "review.css",
    "review.js",
    "review_mutation_coordinator.js",
    "review_presentation.js",
)
_STIMULUS_SCHEMA = "canonical-v2-human-calibration-stimulus-v1"
_STIMULUS_SET_SCHEMA = "canonical-v2-human-calibration-stimulus-set-v1"


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _calibration_stimulus(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": _STIMULUS_SCHEMA,
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


def _stimulus_set_sha256(probes: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        {
            "schema_version": _STIMULUS_SET_SCHEMA,
            "stimuli": [_calibration_stimulus(probe) for probe in probes],
        }
    )


@dataclass(frozen=True)
class ReviewFixture:
    packet_path: Path
    workload_path: Path
    source_root: Path
    state_dir: Path
    export_dir: Path


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _fixture(tmp_path: Path) -> ReviewFixture:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    for name in ARTIFACT_NAMES:
        shutil.copyfile(REVIEW_SOURCE / name, review_dir / name)

    workload = json.loads(
        (review_dir / "human-review-workload-v2.json").read_text(encoding="utf-8")
    )
    source_root = tmp_path / "source-root"
    for relative in {
        probe["source_identity"]["path"] for probe in workload["calibration_probes"]
    }:
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    for relative in S2C_CONTEXT_PATHS:
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    return ReviewFixture(
        packet_path=review_dir / "human-review-packet-v1.json",
        workload_path=review_dir / "human-review-workload-v2.json",
        source_root=source_root,
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
    )


def _workspace(fixture: ReviewFixture):
    return create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
    )


class RecordedJudge:
    model_id = "review-judge-v1"
    provider_profile = "approved-review-profile"

    def __init__(self, decisions: dict[str, str] | None = None) -> None:
        supplied = decisions or {}
        probes = json.loads(
            (REVIEW_SOURCE / "human-review-workload-v2.json").read_text(
                encoding="utf-8"
            )
        )["calibration_probes"]
        translated = dict(supplied)
        for probe in probes:
            legacy_request_sha256 = probe["request_sha256"]
            if legacy_request_sha256 in supplied:
                translated[_canonical_sha256(_calibration_stimulus(probe))] = supplied[
                    legacy_request_sha256
                ]
        self.decisions = translated
        self.requests: list[dict[str, Any]] = []

    def judge(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        request_sha256 = _canonical_sha256(request)
        return {
            "schema_version": "canonical-v2-human-calibration-judge-decision-v2",
            "model_id": self.model_id,
            "policy_id": "evidence-bounded-judge-v1",
            "request_sha256": request_sha256,
            "decision": self.decisions.get(request_sha256, "supported"),
            "evidence_scope": "supplied_request_only",
            "used_external_memory": False,
        }


class V2RecordedJudge(RecordedJudge):
    def judge(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        request_sha256 = _canonical_sha256(request)
        return {
            "schema_version": "canonical-v2-human-calibration-judge-decision-v2",
            "model_id": self.model_id,
            "policy_id": "evidence-bounded-judge-v1",
            "request_sha256": request_sha256,
            "decision": self.decisions.get(request_sha256, "supported"),
            "evidence_scope": "supplied_request_only",
            "used_external_memory": False,
        }


def _authorization(
    *,
    round_id: str,
    model_id: str = "review-judge-v1",
    provider_profile: str = "approved-review-profile",
    evidence_class: str = "implementation_test",
    workload_content_sha256: str = (
        "89b027058e8f66864edfd6c3a2ccc0be3f006a51432e17eaa0a6e504d7baa456"
    ),
    calibration_policy_id: str = "single-human-global-stratified-v2",
    judge_policy_id: str = "evidence-bounded-judge-v1",
) -> JudgeAuthorization:
    content = {
        "schema_version": "judge-authorization-v2",
        "evidence_class": evidence_class,
        "round_id": round_id,
        "authorizer_id": "human:owner-1",
        "provider_profile": provider_profile,
        "model_id": model_id,
        "calibration_policy_id": calibration_policy_id,
        "judge_policy_id": judge_policy_id,
        "workload_content_sha256": workload_content_sha256,
        "authorized_at": "2026-07-24T12:00:00Z",
        "evidence_scope": "supplied_request_only",
    }
    content_sha256 = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return JudgeAuthorization.model_validate(
        {**content, "content_sha256": content_sha256}
    )


class RecordedAuthorizationProvider:
    def __init__(
        self,
        *,
        model_id: str = "review-judge-v1",
        provider_profile: str = "approved-review-profile",
        fault: str | None = None,
        real_authorization_provider: bool = False,
    ) -> None:
        self.model_id = model_id
        self.provider_profile = provider_profile
        self.fault = fault
        self._real_authorization_provider = real_authorization_provider
        self.round_ids: list[str] = []
        self.authorization_requests: list[dict[str, str]] = []

    @property
    def is_real_authorization_provider(self) -> bool:
        return self._real_authorization_provider

    def authorize(
        self,
        *,
        round_id: str,
        workload_content_sha256: str,
        evidence_class: str,
    ) -> JudgeAuthorization:
        self.round_ids.append(round_id)
        self.authorization_requests.append(
            {
                "round_id": round_id,
                "workload_content_sha256": workload_content_sha256,
                "evidence_class": evidence_class,
            }
        )
        authorization = _authorization(
            round_id=round_id,
            model_id=self.model_id,
            provider_profile=self.provider_profile,
            evidence_class=evidence_class,
            workload_content_sha256=workload_content_sha256,
        )
        if self.fault == "wrong_round":
            authorization = _authorization(
                round_id="round:not-this-round",
                model_id=self.model_id,
                provider_profile=self.provider_profile,
                evidence_class=evidence_class,
                workload_content_sha256=workload_content_sha256,
            )
        elif self.fault == "content_hash":
            authorization = authorization.model_copy(
                update={"content_sha256": "0" * 64}
            )
        elif self.fault == "secret":
            content = authorization.model_dump(exclude={"content_sha256"})
            content["provider_profile"] = "api_key=must-not-persist"
            return JudgeAuthorization.model_construct(
                **content,
                content_sha256=authorization.content_sha256,
            )
        elif self.fault == "judge_policy":
            authorization = _authorization(
                round_id=round_id,
                model_id=self.model_id,
                provider_profile=self.provider_profile,
                evidence_class=evidence_class,
                workload_content_sha256=workload_content_sha256,
                judge_policy_id="wrong-judge-policy-v2",
            )
        elif self.fault == "calibration_policy":
            authorization = _authorization(
                round_id=round_id,
                model_id=self.model_id,
                provider_profile=self.provider_profile,
                evidence_class=evidence_class,
                workload_content_sha256=workload_content_sha256,
                calibration_policy_id="wrong-calibration-policy-v2",
            )
        elif self.fault == "evidence_class":
            authorization = _authorization(
                round_id=round_id,
                model_id=self.model_id,
                provider_profile=self.provider_profile,
                evidence_class=(
                    "real_human_round"
                    if evidence_class == "implementation_test"
                    else "implementation_test"
                ),
                workload_content_sha256=workload_content_sha256,
            )
        elif self.fault == "workload":
            authorization = _authorization(
                round_id=round_id,
                model_id=self.model_id,
                provider_profile=self.provider_profile,
                evidence_class=evidence_class,
                workload_content_sha256="0" * 64,
            )
        elif self.fault == "provider_profile":
            authorization = _authorization(
                round_id=round_id,
                model_id=self.model_id,
                provider_profile="wrong-review-profile",
                evidence_class=evidence_class,
                workload_content_sha256=workload_content_sha256,
            )
        return authorization


def _workspace_with_judge(
    fixture: ReviewFixture,
    judge: RecordedJudge,
    authorization_provider: JudgeAuthorizationProvider | None = None,
):
    return create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=judge,
        judge_authorization_provider=(
            authorization_provider
            or RecordedAuthorizationProvider(model_id=judge.model_id)
        ),
    )


def _submit_calibration_labels(
    workspace: Any,
    token: str,
    *,
    labels: dict[str, str] | None = None,
    idempotency_prefix: str = "calibration-label",
) -> list[dict[str, Any]]:
    workload = json.loads(
        (REVIEW_SOURCE / "human-review-workload-v2.json").read_text(encoding="utf-8")
    )
    probes = workload["calibration_probes"]
    for position, probe in enumerate(probes, start=1):
        task_id = f"calibration:{probe['sample_id']}"
        decision = (labels or {}).get(
            probe["request_sha256"],
            "unsupported" if position <= 12 else "supported",
        )
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CALIBRATION,
                decision=decision,
                expected_revision=0,
                idempotency_key=f"{idempotency_prefix}-{position}",
            )
        )
    return probes


def _register(workspace):
    view = workspace.open(OpenWorkspace(display_name="Reviewer Li", staff_id="R-1042"))
    assert view.session_token
    return view, view.session_token


def _real_judge() -> OpenAICompatibleEvidenceBoundedJudge:
    return OpenAICompatibleEvidenceBoundedJudge(
        client=object(),
        model_id="review-judge-v1",
        provider_profile="approved-review-profile",
    )


def test_default_evidence_class_is_immutable_and_runtime_id_is_not_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runtime_instance_id = "runtime-instance:test-process-1"
    workspace = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        runtime_instance_id=runtime_instance_id,
    )
    view, _ = _register(workspace)

    assert view.evidence_class is review_module.EvidenceClass.IMPLEMENTATION_TEST
    with pytest.raises(ValidationError):
        view.evidence_class = review_module.EvidenceClass.REAL_HUMAN_ROUND  # type: ignore[misc]
    serialized = json.dumps(view.model_dump(mode="json"), sort_keys=True)
    assert runtime_instance_id not in serialized
    assert (
        runtime_instance_id.encode()
        not in (fixture.state_dir / "review-workbench.sqlite3").read_bytes()
    )
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        metadata = dict(connection.execute("SELECT key, value FROM workspace_meta"))
    assert metadata["schema_version"] == "canonical-v2-review-workspace-sqlite-v10"
    assert metadata["evidence_class"] == "implementation_test"


def test_evidence_class_mismatch_restart_fails_before_mutation_or_provider_call(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    first, _ = _register(workspace)
    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        before_meta = connection.execute(
            "SELECT key, value FROM workspace_meta ORDER BY key"
        ).fetchall()
        before_rounds = connection.execute("SELECT * FROM rounds").fetchall()

    provider = RecordedAuthorizationProvider(real_authorization_provider=True)
    with pytest.raises(ReviewWorkspaceError) as mismatch:
        create_review_workspace(
            packet_path=fixture.packet_path,
            workload_path=fixture.workload_path,
            source_root=fixture.source_root,
            state_dir=fixture.state_dir,
            export_dir=fixture.export_dir,
            judge=_real_judge(),
            judge_authorization_provider=provider,
            evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
            runtime_instance_id="runtime-instance:other-process",
        )
    assert mismatch.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    assert provider.authorization_requests == []
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT key, value FROM workspace_meta ORDER BY key"
            ).fetchall()
            == before_meta
        )
        assert connection.execute("SELECT * FROM rounds").fetchall() == before_rounds
    assert first.evidence_class is review_module.EvidenceClass.IMPLEMENTATION_TEST


def test_v8_workspace_is_rejected_without_migration(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _workspace(fixture)
    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE workspace_meta SET value = ? WHERE key = 'schema_version'",
            ("canonical-v2-review-workspace-sqlite-v8",),
        )

    with pytest.raises(ReviewWorkspaceError) as old_schema:
        _workspace(fixture)
    assert old_schema.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("canonical-v2-review-workspace-sqlite-v8",)


@pytest.mark.parametrize(
    "scenario",
    ["missing_judge", "missing_provider", "fake_judge", "fake_provider"],
)
def test_real_evidence_configuration_rejects_incomplete_or_fake_before_state_creation(
    tmp_path: Path,
    scenario: str,
) -> None:
    fixture = _fixture(tmp_path)
    judge: Any = _real_judge()
    provider: Any = RecordedAuthorizationProvider(real_authorization_provider=True)
    if scenario == "missing_judge":
        judge = None
    elif scenario == "missing_provider":
        provider = None
    elif scenario == "fake_judge":
        judge = RecordedJudge()
    elif scenario == "fake_provider":
        provider = RecordedAuthorizationProvider()

    with pytest.raises(ReviewWorkspaceError) as rejected:
        create_review_workspace(
            packet_path=fixture.packet_path,
            workload_path=fixture.workload_path,
            source_root=fixture.source_root,
            state_dir=fixture.state_dir,
            export_dir=fixture.export_dir,
            judge=judge,
            judge_authorization_provider=provider,
            evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
        )
    assert rejected.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    assert not fixture.state_dir.exists()


def test_real_evidence_round_can_start_without_judge_and_resume_with_one(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    initial = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
        runtime_instance_id="runtime-instance:human-labeling",
    )
    opened, token = _register(initial)

    assert opened.evidence_class is review_module.EvidenceClass.REAL_HUMAN_ROUND
    assert opened.judge_configured is False

    resumed = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=_real_judge(),
        judge_authorization_provider=RecordedAuthorizationProvider(
            real_authorization_provider=True
        ),
        evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
        runtime_instance_id="runtime-instance:judge-sealing",
    )
    reopened = resumed.open(OpenWorkspace(session_token=token))

    assert reopened.round_id == opened.round_id
    assert reopened.progress.submitted == 0
    assert reopened.judge_configured is True


def test_implementation_evidence_may_use_real_marked_provider_but_never_upgrades(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=RecordedJudge(),
        judge_authorization_provider=RecordedAuthorizationProvider(
            real_authorization_provider=True
        ),
    )

    view, _ = _register(workspace)
    assert view.evidence_class is review_module.EvidenceClass.IMPLEMENTATION_TEST


def test_recovery_only_real_workspace_needs_no_provider_and_disables_other_methods(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    provider = RecordedAuthorizationProvider(real_authorization_provider=True)
    create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=_real_judge(),
        judge_authorization_provider=provider,
        evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
        runtime_instance_id="runtime-instance:interactive-process",
    )

    recovery = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        evidence_class=review_module.EvidenceClass.REAL_HUMAN_ROUND,
        runtime_instance_id="runtime-instance:recovery-process",
        recovery_only=True,
    )
    assert provider.authorization_requests == []

    with pytest.raises(ReviewWorkspaceError) as open_blocked:
        recovery.open(OpenWorkspace(display_name="Operator", staff_id="ops-1"))
    assert open_blocked.value.code is ReviewErrorCode.INVALID_COMMAND
    with pytest.raises(ReviewWorkspaceError) as record_blocked:
        recovery.record(
            SaveDraft(
                session_token="unused-session",
                task_id="contract:unused",
                draft=DraftData(),
            )
        )
    assert record_blocked.value.code is ReviewErrorCode.INVALID_COMMAND
    with pytest.raises(ReviewWorkspaceError) as export_blocked:
        recovery.export(
            ExportReview(
                session_token="unused-session",
                mode=ExportMode.REVIEW_EVIDENCE,
            )
        )
    assert export_blocked.value.code is ReviewErrorCode.INVALID_COMMAND


@pytest.mark.parametrize(
    "target",
    [
        "human-review-packet-v1.json",
        "human-review-workload-v2.json",
        "calibration-policy-v2.json",
        "calibration-observation-bank-v2.jsonl",
        "calibration-observation-bank-v2-provenance.json",
        "source",
    ],
)
def test_artifact_admission_fails_before_first_sqlite_write(
    tmp_path: Path, target: str
) -> None:
    fixture = _fixture(tmp_path)
    if target == "source":
        source = next(path for path in fixture.source_root.rglob("*.py"))
        source.write_bytes(source.read_bytes() + b"\n# drift\n")
    else:
        path = fixture.workload_path.parent / target
        path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(ReviewWorkspaceError) as caught:
        _workspace(fixture)

    assert caught.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    assert not (fixture.state_dir / "review-workbench.sqlite3").exists()
    assert str(tmp_path) not in str(caught.value)


def test_artifact_admission_rejects_hidden_labels_and_unknown_tasks(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workload = json.loads(fixture.workload_path.read_text(encoding="utf-8"))
    workload["calibration_probes"][0]["expected_label"] = "supported"
    content = {key: value for key, value in workload.items() if key != "content_sha256"}
    workload["content_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    fixture.workload_path.write_text(
        json.dumps(workload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ReviewWorkspaceError) as caught:
        _workspace(fixture)
    assert caught.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    assert not (fixture.state_dir / "review-workbench.sqlite3").exists()


def test_register_resume_and_restart_keep_token_out_of_sqlite(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    first, token = _register(workspace)

    assert first.reviewer.reviewer_id == "human:r-1042"
    assert first.counts.contract_reviews == 29
    assert first.counts.exclusion_reviews == 23
    assert first.counts.calibration_probes == 60
    assert first.progress.total == 112
    assert first.task is not None
    assert first.task.task_id.startswith("contract:")
    assert first.task.mutable is True
    assert first.task.read_only_reason is None
    assert len(first.queue) == 112
    assert [item.position for item in first.queue] == list(range(1, 113))
    assert [item.kind for item in first.queue[:29]] == [TaskKind.CONTRACT] * 29
    assert [item.kind for item in first.queue[29:52]] == [TaskKind.EXCLUSION] * 23
    assert [item.kind for item in first.queue[52:]] == [TaskKind.CALIBRATION] * 60
    assert all(item.status == "pending" for item in first.queue)
    assert all(
        item.revision == 0 and item.current_decision is None for item in first.queue
    )
    serialized_queue = json.dumps(
        [item.model_dump(mode="json") for item in first.queue]
    )
    assert "payload" not in serialized_queue
    assert "judge" not in serialized_queue

    resumed = workspace.open(OpenWorkspace(session_token=token))
    assert resumed.round_id == first.round_id
    assert resumed.session_token is None

    restarted = _workspace(fixture)
    after_restart = restarted.open(OpenWorkspace(session_token=token))
    assert after_restart.round_id == first.round_id
    assert after_restart.session_token is None
    assert after_restart.queue == first.queue

    new_session = restarted.open(
        OpenWorkspace(display_name="Reviewer Li", staff_id="r-1042")
    )
    assert new_session.round_id == first.round_id
    assert new_session.session_token not in {None, token}
    assert new_session.session_token is not None
    new_token = new_session.session_token

    database_bytes = (fixture.state_dir / "review-workbench.sqlite3").read_bytes()
    assert token.encode() not in database_bytes
    assert new_token.encode() not in database_bytes


def test_workspace_header_exposes_frozen_artifact_identity_and_safe_judge_status(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    without_judge, _ = _register(workspace)
    s2c_root = (
        fixture.source_root / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c"
    )
    manifest = json.loads(
        (s2c_root / "claim-level-corpus-manifest-v1.json").read_text(encoding="utf-8")
    )
    renderer_dir = REPO_ROOT / "apps/admin-console/backend/static"
    renderer_hashes = {
        name: hashlib.sha256((renderer_dir / name).read_bytes()).hexdigest()
        for name in RENDERER_FILES
    }
    workload = json.loads(fixture.workload_path.read_text(encoding="utf-8"))
    assert without_judge.artifact_identity.model_dump(mode="json") == {
        "packet_raw_sha256": (
            "222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e"
        ),
        "packet_content_sha256": (
            "d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb"
        ),
        "workload_raw_sha256": (
            "0e0e5bbc1a101d4a21fc99c523b59ad81a344420d13fc57d5f11000570e8f494"
        ),
        "workload_content_sha256": (
            "89b027058e8f66864edfd6c3a2ccc0be3f006a51432e17eaa0a6e504d7baa456"
        ),
        "policy_raw_sha256": (
            "9900ea9a6cb20c928fb07f9c38f43b4bc0d6f42efad0978aab6a341cfa3b92c5"
        ),
        "policy_content_sha256": (
            "cb569bc6f2b094a4b541d80f6e0b76c3143ff8b0fad007bf18dee633f61d1f75"
        ),
        "bank_raw_sha256": (
            "3a0fdc42202b052d79cb04853ed7fc8ae98b701b685ed30f920c5f2b7b4257cd"
        ),
        "bank_content_sha256": (
            "ff97cae3f0df349567d74585e22750d8f8f80d87069787f5e383bbc0fdd41eaf"
        ),
        "provenance_raw_sha256": (
            "1a806bc6e99d1fcf219338f1007feb5963ef35e60de200fa3246a8e2baa0fa80"
        ),
        "provenance_content_sha256": (
            "3fea1e29ca388c0eab17d30844a034c1db3a7fd97d1faea0501acabb995f5f6b"
        ),
        "s2c_manifest_raw_sha256": hashlib.sha256(
            (s2c_root / "claim-level-corpus-manifest-v1.json").read_bytes()
        ).hexdigest(),
        "s2c_manifest_content_sha256": manifest["content_sha256"],
        "s2c_corpus_raw_sha256": hashlib.sha256(
            (s2c_root / "claim-level-corpus-v1.jsonl").read_bytes()
        ).hexdigest(),
        "s2c_accounting_raw_sha256": hashlib.sha256(
            (s2c_root / "case-accounting-v1.jsonl").read_bytes()
        ).hexdigest(),
        "s2c_snapshots_raw_sha256": hashlib.sha256(
            (s2c_root / "source-snapshots-v1.jsonl").read_bytes()
        ).hexdigest(),
        "calibration_stimulus_set_sha256": _stimulus_set_sha256(
            workload["calibration_probes"]
        ),
        "renderer_schema_version": "canonical-v2-human-review-renderer-v2",
        "review_html_raw_sha256": renderer_hashes["review.html"],
        "review_css_raw_sha256": renderer_hashes["review.css"],
        "review_js_raw_sha256": renderer_hashes["review.js"],
        "review_mutation_coordinator_js_raw_sha256": renderer_hashes[
            "review_mutation_coordinator.js"
        ],
        "review_presentation_js_raw_sha256": renderer_hashes["review_presentation.js"],
        "renderer_content_sha256": _canonical_sha256(
            {
                "schema_version": "canonical-v2-human-review-renderer-v2",
                "assets": renderer_hashes,
            }
        ),
    }
    assert without_judge.judge_configured is False
    serialized = json.dumps(without_judge.model_dump(mode="json"))
    assert "model_id" not in serialized
    assert "provider_profile" not in serialized

    judge_root = tmp_path / "with-judge"
    judge_root.mkdir()
    configured_fixture = _fixture(judge_root)
    configured = _workspace_with_judge(configured_fixture, RecordedJudge())
    configured_view, _ = _register(configured)
    assert configured_view.judge_configured is True
    assert configured_view.artifact_identity == without_judge.artifact_identity


def test_renderer_assets_are_content_bound_and_runtime_watched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    renderer_dir = tmp_path / "renderer"
    renderer_dir.mkdir()
    source = REPO_ROOT / "apps/admin-console/backend/static"
    for name in RENDERER_FILES:
        shutil.copyfile(source / name, renderer_dir / name)
    monkeypatch.setattr(review_module, "_RENDERER_DIR", renderer_dir, raising=False)

    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    serialized_identity = json.dumps(opened.artifact_identity.model_dump(mode="json"))
    assert str(renderer_dir) not in serialized_identity
    assert (
        opened.artifact_identity.review_html_raw_sha256
        == hashlib.sha256((renderer_dir / "review.html").read_bytes()).hexdigest()
    )

    (renderer_dir / "review.css").write_bytes(
        (renderer_dir / "review.css").read_bytes() + b"\n/* drift */\n"
    )
    with pytest.raises(ReviewWorkspaceError) as drift:
        workspace.open(OpenWorkspace(session_token=token))
    assert drift.value.code is ReviewErrorCode.ARTIFACT_MISMATCH


def test_server_gate_summary_owns_missing_blocking_and_coverage_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)

    summary = opened.gate_summary
    assert len(summary.missing_task_ids) == 112
    assert summary.missing_task_ids == tuple(item.task_id for item in opened.queue)
    assert summary.blocking_task_ids == ()
    assert summary.blocking_reasons == {}
    assert sum(item.total for item in summary.family_coverage.values()) == 52
    assert sum(item.total for item in summary.stratum_coverage.values()) == 60
    assert {name: item.total for name, item in summary.stratum_coverage.items()} == {
        "claim_evidence": 20,
        "context_relationship": 10,
        "identity_entity": 10,
        "insufficiency_assessment": 10,
        "safety_web": 10,
    }
    assert all(item.submitted == 0 for item in summary.family_coverage.values())
    assert all(item.submitted == 0 for item in summary.stratum_coverage.values())
    assert summary.calibration_labels_valid is False
    assert summary.calibration_ready_to_seal is False
    assert summary.acceptance_ready is False
    assert "human_decisions_missing" in summary.acceptance_blockers
    serialized = json.dumps(opened.model_dump(mode="json"), sort_keys=True)
    for hidden in (
        "model_id",
        "judge_policy_id",
        "model_judgment",
        "agreement",
        "authorization_sha256",
    ):
        assert hidden not in serialized

    contract_id = next(
        item.task_id for item in opened.queue if item.kind is TaskKind.CONTRACT
    )
    exclusion_id = next(
        item.task_id for item in opened.queue if item.kind is TaskKind.EXCLUSION
    )
    calibration_id = next(
        item.task_id for item in opened.queue if item.kind is TaskKind.CALIBRATION
    )
    workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=contract_id,
            task_kind=TaskKind.CONTRACT,
            decision="needs_change",
            rationale="Contract needs a bounded correction.",
            expected_revision=0,
            idempotency_key="gate-contract-blocking",
        )
    )
    workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=exclusion_id,
            task_kind=TaskKind.EXCLUSION,
            decision="require_evidence",
            rationale="The exclusion still needs admissible evidence.",
            expected_revision=0,
            idempotency_key="gate-exclusion-blocking",
        )
    )
    updated = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=calibration_id,
            task_kind=TaskKind.CALIBRATION,
            decision="unable_to_determine",
            expected_revision=0,
            idempotency_key="gate-calibration-blocking",
        )
    )

    assert updated.gate_summary.blocking_task_ids == (
        contract_id,
        exclusion_id,
        calibration_id,
    )
    assert updated.gate_summary.blocking_reasons == {
        contract_id: "needs_change",
        exclusion_id: "require_evidence",
        calibration_id: "unable_to_determine",
    }
    assert len(updated.gate_summary.missing_task_ids) == 109
    assert updated.gate_summary.calibration_labels_valid is False
    assert "human_decisions_blocking" in updated.gate_summary.acceptance_blockers


def test_exclusion_task_exposes_exact_non_normative_review_context(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)
    workload = json.loads(fixture.workload_path.read_text(encoding="utf-8"))
    exclusion = workload["exclusion_reviews"][0]
    task_id = f"exclusion:{exclusion['case_id']}"

    view = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
    assert view.task is not None
    context = view.task.review_context
    assert context is not None
    assert context.query == "介绍清华的丁文伯"
    assert context.as_of == "2026-07-13T17:44:15Z"

    source_dir = (
        fixture.source_root / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c"
    )
    contract = next(
        row
        for row in _jsonl_rows(source_dir / "claim-level-corpus-v1.jsonl")
        if row["case_id"] == exclusion["case_id"]
    )
    accounting = next(
        row
        for row in _jsonl_rows(source_dir / "case-accounting-v1.jsonl")
        if row["contract_case_id"] == exclusion["case_id"]
    )
    snapshots = {
        row["snapshot_id"]: row
        for row in _jsonl_rows(source_dir / "source-snapshots-v1.jsonl")
    }
    assert context.contract == contract
    assert context.accounting == accounting
    assert [row["snapshot_id"] for row in context.requirement_snapshots] == exclusion[
        "snapshot_ids"
    ]
    assert context.requirement_snapshots == tuple(
        snapshots[snapshot_id] for snapshot_id in exclusion["snapshot_ids"]
    )
    assert context.reference_prose.role == "review_only"
    assert context.reference_prose.normative is False
    assert (
        context.reference_prose.content
        == contract["reference_context"]["reference_prose"]
    )
    assert context.requirement_snapshot_use.role == "review_only"
    assert context.requirement_snapshot_use.normative is False
    assert context.contract["outcome_policy"]["reference_prose_normative"] is False
    assert context.contract["evidence_availability"] == "unavailable"
    assert context.accounting["evidence_snapshot_ids"] == []
    assert all(
        row["snapshot_role"] == "requirement_context"
        for row in context.requirement_snapshots
    )


@pytest.mark.parametrize("relative", S2C_CONTEXT_PATHS)
def test_source_context_tamper_fails_before_database_and_after_start(
    tmp_path: Path, relative: Path
) -> None:
    before_root = tmp_path / "before"
    before_root.mkdir()
    before = _fixture(before_root)
    before_path = before.source_root / relative
    before_path.write_bytes(before_path.read_bytes() + b" ")
    with pytest.raises(ReviewWorkspaceError) as admission:
        _workspace(before)
    assert admission.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    assert not (before.state_dir / "review-workbench.sqlite3").exists()

    after_root = tmp_path / "after"
    after_root.mkdir()
    after = _fixture(after_root)
    workspace = _workspace(after)
    opened, token = _register(workspace)
    after_path = after.source_root / relative
    after_path.write_bytes(after_path.read_bytes() + b" ")
    with pytest.raises(ReviewWorkspaceError) as runtime:
        workspace.open(OpenWorkspace(session_token=token))
    assert runtime.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    database = after.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM rounds").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM decision_events"
        ).fetchone() == (0,)
    assert opened.round_id


@pytest.mark.parametrize(
    ("display_name", "staff_id"),
    [
        ("", "r-1042"),
        ("Reviewer", "R 1042"),
        ("Reviewer", "人事-1042"),
        ("Reviewer", "x"),
    ],
)
def test_invalid_reviewer_and_session_are_stable(
    tmp_path: Path, display_name: str, staff_id: str
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    with pytest.raises(ReviewWorkspaceError) as caught:
        workspace.open(OpenWorkspace(display_name=display_name, staff_id=staff_id))
    assert caught.value.code is ReviewErrorCode.INVALID_REVIEWER

    with pytest.raises(ReviewWorkspaceError) as invalid_token:
        workspace.open(OpenWorkspace(session_token="not-a-real-session-token"))
    assert invalid_token.value.code is ReviewErrorCode.INVALID_SESSION


def test_drafts_are_mutable_non_evidentiary_and_secret_fields_are_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    assert opened.task is not None
    task_id = opened.task.task_id

    drafted = workspace.record(
        SaveDraft(
            session_token=token,
            task_id=task_id,
            draft=DraftData(decision="needs_change", rationale="first note"),
        )
    )
    assert drafted.task is not None
    assert drafted.task.draft is not None
    assert drafted.task.draft.rationale == "first note"
    redrafted = workspace.record(
        SaveDraft(
            session_token=token,
            task_id=task_id,
            draft=DraftData(decision="approved", rationale="second note"),
        )
    )
    assert redrafted.task is not None
    assert redrafted.task.draft is not None
    assert redrafted.task.draft.rationale == "second note"
    assert redrafted.task.revision == 0

    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM drafts").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM decision_events"
        ).fetchone() == (0,)

    with pytest.raises(ValidationError):
        DraftData.model_validate(
            {"decision": "approved", "rationale": "ok", "api_key": "sk-secret"}
        )
    assert (
        b"sk-secret"
        not in (fixture.state_dir / "review-workbench.sqlite3").read_bytes()
    )


def test_final_decisions_are_append_only_superseded_and_optimistic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    assert opened.task is not None
    task_id = opened.task.task_id

    first = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            rationale=None,
            expected_revision=0,
            idempotency_key="decision-first",
        )
    )
    assert first.queue[0].status == "submitted"
    assert first.queue[0].revision == 1
    assert first.queue[0].current_decision == "approved"
    original = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
    assert original.task is not None
    assert original.task.revision == 1
    assert original.task.current_decision is not None
    assert original.task.current_decision.decision == "approved"
    assert original.task.current_decision.reviewer_id == "human:r-1042"
    assert original.task.current_decision.staff_id == "r-1042"

    replay = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            rationale=None,
            expected_revision=0,
            idempotency_key="decision-first",
        )
    )
    assert replay.progress.submitted == first.progress.submitted == 1

    with pytest.raises(ReviewWorkspaceError) as conflict:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CONTRACT,
                decision="needs_change",
                rationale="different payload",
                expected_revision=1,
                idempotency_key="decision-first",
            )
        )
    assert conflict.value.code is ReviewErrorCode.IDEMPOTENCY_CONFLICT

    with pytest.raises(ReviewWorkspaceError) as stale:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CONTRACT,
                decision="approved",
                rationale="stale edit",
                expected_revision=0,
                idempotency_key="decision-stale",
            )
        )
    assert stale.value.code is ReviewErrorCode.STALE_REVISION
    assert stale.value.current_revision == 1

    with pytest.raises(ReviewWorkspaceError) as rationale_required:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CONTRACT,
                decision="approved",
                rationale=None,
                expected_revision=1,
                idempotency_key="decision-no-rationale",
            )
        )
    assert rationale_required.value.code is ReviewErrorCode.INVALID_DECISION

    workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="needs_change",
            rationale="The requirement is too broad.",
            expected_revision=1,
            idempotency_key="decision-second",
        )
    )

    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT revision, supersedes_event_id, decision, reviewer_id, staff_id, "
            "display_name, canonical_payload_json, payload_sha256 "
            "FROM decision_events "
            "WHERE task_id = ? ORDER BY revision",
            (task_id,),
        ).fetchall()
        assert rows[0][:6] == (
            1,
            None,
            "approved",
            "human:r-1042",
            "r-1042",
            "Reviewer Li",
        )
        first_payload = json.loads(rows[0][6])
        assert first_payload["reviewer_id"] == "human:r-1042"
        assert first_payload["staff_id"] == "r-1042"
        assert first_payload["display_name"] == "Reviewer Li"
        assert rows[0][7] == hashlib.sha256(rows[0][6].encode()).hexdigest()
        assert rows[1][0] == 2
        assert rows[1][1] is not None
        assert rows[1][2] == "needs_change"
        assert rows[1][3:6] == rows[0][3:6]
        assert len(rows) == 2
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE decision_events SET decision = 'approved' WHERE task_id = ?",
                (task_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM decision_events WHERE task_id = ?", (task_id,)
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE rounds SET reviewer_id = 'human:other' WHERE round_id = ?",
                (opened.round_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE rounds SET staff_id = 'other' WHERE round_id = ?",
                (opened.round_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE rounds SET display_name = 'Other' WHERE round_id = ?",
                (opened.round_id,),
            )

    restarted = _workspace(fixture).open(OpenWorkspace(session_token=token))
    assert restarted.queue[0].status == "submitted"
    assert restarted.queue[0].revision == 2
    assert restarted.queue[0].current_decision == "needs_change"


def test_idempotency_replay_returns_the_durable_original_workspace_view(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    first_task_id = opened.queue[0].task_id
    second_task_id = opened.queue[1].task_id
    first_command = SubmitDecision(
        session_token=token,
        task_id=first_task_id,
        task_kind=TaskKind.CONTRACT,
        decision="approved",
        expected_revision=0,
        idempotency_key="durable-receipt-first",
    )

    original_receipt = workspace.record(first_command)
    workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=second_task_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            expected_revision=0,
            idempotency_key="durable-receipt-second",
        )
    )
    replayed_receipt = workspace.record(first_command)

    original = original_receipt.model_dump(mode="json")
    replayed = replayed_receipt.model_dump(mode="json")
    assert replayed == original
    assert json.dumps(replayed, sort_keys=True, separators=(",", ":")) == json.dumps(
        original, sort_keys=True, separators=(",", ":")
    )

    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        receipts = connection.execute(
            "SELECT idempotency_key, event_id, round_id, workspace_view_json, "
            "view_sha256 FROM idempotency_receipts ORDER BY idempotency_key"
        ).fetchall()
        assert len(receipts) == 2
        first = next(row for row in receipts if row[0] == "durable-receipt-first")
        assert first[2] == opened.round_id
        assert first[4] == hashlib.sha256(first[3].encode()).hexdigest()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE idempotency_receipts SET view_sha256 = ? "
                "WHERE idempotency_key = ?",
                ("0" * 64, "durable-receipt-first"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM idempotency_receipts WHERE idempotency_key = ?",
                ("durable-receipt-first",),
            )


def test_all_contract_and_exclusion_tasks_enforce_kind_and_decision_semantics(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    contract_ids = [
        item.task_id for item in opened.queue if item.kind is TaskKind.CONTRACT
    ]
    exclusion_ids = [
        item.task_id for item in opened.queue if item.kind is TaskKind.EXCLUSION
    ]
    assert len(set(contract_ids + exclusion_ids)) == 52

    with pytest.raises(ReviewWorkspaceError) as wrong_kind:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=contract_ids[0],
                task_kind=TaskKind.EXCLUSION,
                decision="accept_exclusion",
                rationale="wrong kind",
                expected_revision=0,
                idempotency_key="wrong-kind",
            )
        )
    assert wrong_kind.value.code is ReviewErrorCode.INVALID_DECISION

    with pytest.raises(ReviewWorkspaceError) as missing_rationale:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=contract_ids[0],
                task_kind=TaskKind.CONTRACT,
                decision="needs_change",
                rationale="",
                expected_revision=0,
                idempotency_key="missing-rationale",
            )
        )
    assert missing_rationale.value.code is ReviewErrorCode.INVALID_DECISION

    for index, task_id in enumerate(contract_ids):
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CONTRACT,
                decision="approved",
                expected_revision=0,
                idempotency_key=f"contract-{index:02d}",
            )
        )
    for index, task_id in enumerate(exclusion_ids):
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.EXCLUSION,
                decision="accept_exclusion",
                rationale="Reviewed evidence remains unavailable.",
                expected_revision=0,
                idempotency_key=f"exclusion-{index:02d}",
            )
        )
    view = workspace.open(OpenWorkspace(session_token=token))
    assert view.progress.contract_submitted == 29
    assert view.progress.exclusion_submitted == 23
    assert view.progress.submitted == 52
    assert view.task is not None
    assert view.task.task_id.startswith("calibration:")
    assert [item.status for item in view.queue[:52]] == ["submitted"] * 52
    assert [item.status for item in view.queue[52:]] == ["pending"] * 60


def test_secret_smuggling_is_rejected_before_any_user_state_write(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    database = fixture.state_dir / "review-workbench.sqlite3"

    for display_name, staff_id in (
        ("Reviewer Li", "sk-abcdef123456"),
        ("api_key=do-not-store", "r-1042"),
    ):
        with pytest.raises(ReviewWorkspaceError) as invalid_reviewer:
            workspace.open(OpenWorkspace(display_name=display_name, staff_id=staff_id))
        assert invalid_reviewer.value.code is ReviewErrorCode.INVALID_REVIEWER
        assert "sk-" not in str(invalid_reviewer.value)
        assert "api_key" not in str(invalid_reviewer.value)

    opened, token = _register(workspace)
    assert opened.task is not None
    task_id = opened.task.task_id
    secret_commands = (
        SaveDraft(
            session_token=token,
            task_id=task_id,
            draft=DraftData(decision="sk-draft123456", rationale="normal"),
        ),
        SaveDraft(
            session_token=token,
            task_id=task_id,
            draft=DraftData(decision="approved", rationale="password=hunter2"),
        ),
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="sk-decision123456",
            expected_revision=0,
            idempotency_key="normal-decision-key",
        ),
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            rationale="Bearer secret-credential",
            expected_revision=0,
            idempotency_key="normal-rationale-key",
        ),
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            expected_revision=0,
            idempotency_key="sk-fedcba654321",
        ),
    )
    for command in secret_commands:
        with pytest.raises(ReviewWorkspaceError) as invalid_command:
            workspace.record(command)
        assert invalid_command.value.code is ReviewErrorCode.INVALID_COMMAND
        assert "secret" not in str(invalid_command.value)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM rounds").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM drafts").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM decision_events"
        ).fetchone() == (0,)
    database_bytes = database.read_bytes()
    for secret in (
        b"sk-abcdef123456",
        b"api_key=do-not-store",
        b"sk-fedcba654321",
        b"password=hunter2",
    ):
        assert secret not in database_bytes


def test_calibration_payload_is_blind_and_unknown_task_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)
    workload = json.loads(fixture.workload_path.read_text(encoding="utf-8"))
    task_id = f"calibration:{workload['calibration_probes'][0]['sample_id']}"

    before = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
    assert before.task is not None
    probe = workload["calibration_probes"][0]
    assert before.task.payload == _calibration_stimulus(probe)
    assert set(before.task.payload) == {
        "schema_version",
        "sample_id",
        "as_of",
        "requirement",
        "candidate_observation",
        "evidence_snapshots",
    }
    serialized_payload = json.dumps(before.task.payload, ensure_ascii=False)
    for forbidden in (
        "source_identity",
        "fixture_locator",
        "critical_probe",
        "stratum",
        "test_name",
        "selectors",
        "apps/miroflow-agent/tests",
    ):
        assert forbidden not in serialized_payload
    assert "model_judgment" not in before.task.model_dump(mode="json")
    assert "judge_decision" not in json.dumps(before.model_dump(mode="json"))

    submitted = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CALIBRATION,
            decision="unsupported",
            expected_revision=0,
            idempotency_key="calibration-first",
        )
    )
    after = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
    assert after.task is not None
    assert after.task.revision == 1
    assert "model_judgment" not in after.task.model_dump(mode="json")
    assert submitted.lifecycle == "in_progress"

    workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=task_id,
            task_kind=TaskKind.CALIBRATION,
            decision="supported",
            rationale="Correcting the pre-seal human label.",
            expected_revision=1,
            idempotency_key="calibration-second",
        )
    )

    with pytest.raises(ReviewWorkspaceError) as unknown:
        workspace.open(OpenWorkspace(session_token=token, task_id="contract:unknown"))
    assert unknown.value.code is ReviewErrorCode.UNKNOWN_TASK


def test_human_and_judge_receive_the_same_sanitized_calibration_stimuli(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    judge = V2RecordedJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)

    human_payloads = []
    for probe in probes:
        task_id = f"calibration:{probe['sample_id']}"
        view = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
        assert view.task is not None
        human_payloads.append(view.task.payload)
    assert human_payloads == [_calibration_stimulus(probe) for probe in probes]

    _submit_calibration_labels(workspace, token)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="seal-sanitized-stimuli",
        )
    )

    assert judge.requests == human_payloads
    assert [item.request_sha256 for item in sealed.calibration.judgments] == [
        _canonical_sha256(payload) for payload in human_payloads
    ]


def test_judge_is_blind_until_sixty_labels_then_exact_threshold_seals(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workload = json.loads(fixture.workload_path.read_text(encoding="utf-8"))
    probes = workload["calibration_probes"]
    judge_decisions = {
        probe["request_sha256"]: ("unsupported" if position <= 24 else "supported")
        for position, probe in enumerate(probes, start=1)
    }
    judge = RecordedJudge(judge_decisions)
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)

    for probe in probes:
        task_id = f"calibration:{probe['sample_id']}"
        view = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
        assert view.task is not None
        serialized = json.dumps(view.model_dump(mode="json"), sort_keys=True)
        assert "model_judgment" not in serialized
        assert "judge_decision" not in serialized
        assert "agreement" not in serialized
    assert judge.requests == []

    _submit_calibration_labels(workspace, token)
    assert judge.requests == []
    ready = workspace.open(OpenWorkspace(session_token=token))
    assert ready.gate_summary.calibration_labels_valid is True
    assert ready.gate_summary.calibration_ready_to_seal is True
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="seal-threshold-pass",
        )
    )

    assert len(judge.requests) == 60
    assert all("human_label" not in request for request in judge.requests)
    assert sealed.task is not None
    assert sealed.task.kind is TaskKind.CONTRACT
    assert sealed.lifecycle == "human_labels_sealed"
    assert sealed.calibration.passed is True
    assert sealed.evidence_class is review_module.EvidenceClass.IMPLEMENTATION_TEST
    assert (
        sealed.calibration.evidence_class
        is review_module.EvidenceClass.IMPLEMENTATION_TEST
    )
    assert sealed.calibration.agreement == pytest.approx(0.80)
    assert sealed.calibration.pair_count == 60
    assert sealed.calibration.human_supported == 48
    assert sealed.calibration.human_unsupported == 12
    assert sealed.calibration.unsupported_critical_probes >= 5
    assert sealed.calibration.critical_false_accepts == 0
    assert sealed.gate_summary.calibration_labels_valid is True
    assert sealed.gate_summary.calibration_ready_to_seal is False
    assert (
        sealed.calibration.calibration_policy_id == "single-human-global-stratified-v2"
    )
    assert sealed.calibration.judge_policy_id == "evidence-bounded-judge-v1"
    assert len(sealed.calibration.judgments) == 60

    first_task_id = f"calibration:{probes[0]['sample_id']}"
    revealed = workspace.open(OpenWorkspace(session_token=token, task_id=first_task_id))
    assert revealed.task is not None
    assert revealed.task.model_judgment == "unsupported"


def test_missing_or_malformed_judge_fails_closed_without_persistence(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing_fixture = _fixture(missing_root)
    missing_workspace = _workspace(missing_fixture)
    _, missing_token = _register(missing_workspace)
    _submit_calibration_labels(missing_workspace, missing_token)

    with pytest.raises(ReviewWorkspaceError) as unavailable:
        missing_workspace.record(
            SealCalibration(
                session_token=missing_token,
                expected_revision=60,
                idempotency_key="seal-missing-judge",
            )
        )
    assert unavailable.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE

    class MalformedJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            response = super().judge(request)
            response["rationale"] = "must not be accepted or stored"
            return response

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    malformed_fixture = _fixture(malformed_root)
    judge = MalformedJudge()
    malformed_workspace = _workspace_with_judge(malformed_fixture, judge)
    _, malformed_token = _register(malformed_workspace)
    _submit_calibration_labels(malformed_workspace, malformed_token)

    with pytest.raises(ReviewWorkspaceError) as malformed:
        malformed_workspace.record(
            SealCalibration(
                session_token=malformed_token,
                expected_revision=60,
                idempotency_key="seal-malformed-judge",
            )
        )
    assert malformed.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    with sqlite3.connect(
        malformed_fixture.state_dir / "review-workbench.sqlite3"
    ) as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("failed", "judge_unavailable")


@pytest.mark.parametrize(
    ("scenario", "failed_gate"),
    [
        ("agreement_079", "minimum_agreement"),
        ("only_nine_unsupported", "minimum_unsupported_labels"),
        ("only_nine_supported", "minimum_supported_labels"),
        ("only_four_critical_unsupported", "minimum_unsupported_critical_probes"),
        ("critical_false_accept", "maximum_critical_false_accepts"),
    ],
)
def test_calibration_gates_fail_closed_at_each_policy_boundary(
    tmp_path: Path, scenario: str, failed_gate: str
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    critical = [index for index, probe in enumerate(probes) if probe["critical_probe"]]
    noncritical = [
        index for index, probe in enumerate(probes) if not probe["critical_probe"]
    ]
    unsupported_indexes: set[int]
    if scenario == "only_nine_unsupported":
        unsupported_indexes = set(range(9))
    elif scenario == "only_nine_supported":
        unsupported_indexes = set(range(51))
    elif scenario == "only_four_critical_unsupported":
        unsupported_indexes = set(critical[:4] + noncritical[:6])
    else:
        unsupported_indexes = set(range(12))
    human_labels = {
        probe["request_sha256"]: (
            "unsupported" if index in unsupported_indexes else "supported"
        )
        for index, probe in enumerate(probes)
    }
    judge_decisions = dict(human_labels)
    if scenario == "agreement_079":
        for index in sorted(set(range(60)) - unsupported_indexes)[:13]:
            judge_decisions[probes[index]["request_sha256"]] = "unsupported"
    elif scenario == "critical_false_accept":
        target = next(index for index in critical if index in unsupported_indexes)
        judge_decisions[probes[target]["request_sha256"]] = "supported"

    judge = RecordedJudge(judge_decisions)
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=human_labels)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key=f"seal-{scenario}",
        )
    )

    assert sealed.lifecycle == "calibration_failed_sealed"
    assert sealed.calibration.passed is False
    assert getattr(sealed.calibration.gates, failed_gate) is False
    if scenario == "agreement_079":
        assert sealed.calibration.agreement == pytest.approx(47 / 60)
    if scenario == "critical_false_accept":
        assert sealed.calibration.critical_false_accepts == 1


def test_incomplete_or_unable_calibration_never_calls_judge(tmp_path: Path) -> None:
    for suffix, unable in (("incomplete", False), ("unable", True)):
        root = tmp_path / suffix
        root.mkdir()
        fixture = _fixture(root)
        judge = RecordedJudge()
        workspace = _workspace_with_judge(fixture, judge)
        _, token = _register(workspace)
        probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
            "calibration_probes"
        ]
        limit = 60 if unable else 59
        for position, probe in enumerate(probes[:limit], start=1):
            workspace.record(
                SubmitDecision(
                    session_token=token,
                    task_id=f"calibration:{probe['sample_id']}",
                    task_kind=TaskKind.CALIBRATION,
                    decision=(
                        "unable_to_determine"
                        if unable and position == 60
                        else "supported"
                    ),
                    expected_revision=0,
                    idempotency_key=f"{suffix}-{position}",
                )
            )
        with pytest.raises(ReviewWorkspaceError) as blocked:
            workspace.record(
                SealCalibration(
                    session_token=token,
                    expected_revision=60,
                    idempotency_key=f"seal-{suffix}",
                )
            )
        assert blocked.value.code is ReviewErrorCode.CALIBRATION_NOT_SEALED
        assert judge.requests == []


@pytest.mark.parametrize(
    "mode",
    ["timeout", "wrong_request", "wrong_model", "wrong_policy", "external_memory"],
)
def test_judge_failures_and_cross_wiring_persist_nothing(
    tmp_path: Path, mode: str
) -> None:
    class FaultJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            response = super().judge(request)
            if mode == "timeout":
                raise TimeoutError
            if mode == "wrong_request":
                response["request_sha256"] = "0" * 64
            elif mode == "wrong_model":
                response["model_id"] = "other-model"
            elif mode == "wrong_policy":
                response["policy_id"] = "single-human-global-stratified-v2"
            elif mode == "external_memory":
                response["used_external_memory"] = True
            return response

    fixture = _fixture(tmp_path)
    judge = FaultJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(ReviewWorkspaceError) as blocked:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key=f"seal-{mode}",
            )
        )
    assert blocked.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("failed", "judge_unavailable")


@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "wrong_round",
        "content_hash",
        "secret",
        "judge_policy",
        "calibration_policy",
        "evidence_class",
        "workload",
        "provider_profile",
    ],
)
def test_invalid_judge_authorization_never_calls_judge(
    tmp_path: Path, fault: str
) -> None:
    fixture = _fixture(tmp_path)
    judge = RecordedJudge()
    provider = RecordedAuthorizationProvider(
        model_id="other-model" if fault == "model" else judge.model_id,
        fault=None if fault == "model" else fault,
    )
    workspace = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=judge,
        judge_authorization_provider=provider,
    )
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(ReviewWorkspaceError) as blocked:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key=f"seal-auth-{fault}",
            )
        )
    assert blocked.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    assert judge.requests == []
    assert len(provider.authorization_requests) == 1
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM judge_authorizations"
        ).fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM judge_runs").fetchone() == (0,)
    assert (
        b"must-not-persist"
        not in (fixture.state_dir / "review-workbench.sqlite3").read_bytes()
    )


def test_authorization_provider_binds_distinct_exact_round_records(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    provider = RecordedAuthorizationProvider()
    judge = RecordedJudge()
    workspace = _workspace_with_judge(fixture, judge, authorization_provider=provider)

    first, first_token = _register(workspace)
    _submit_calibration_labels(
        workspace, first_token, idempotency_prefix="first-round-label"
    )
    first_seal = workspace.record(
        SealCalibration(
            session_token=first_token,
            expected_revision=60,
            idempotency_key="first-round-seal",
        )
    )
    second = workspace.open(
        OpenWorkspace(display_name="Reviewer Chen", staff_id="r-2048")
    )
    assert second.session_token is not None
    _submit_calibration_labels(
        workspace,
        second.session_token,
        idempotency_prefix="second-round-label",
    )
    second_seal = workspace.record(
        SealCalibration(
            session_token=second.session_token,
            expected_revision=60,
            idempotency_key="second-round-seal",
        )
    )

    expected_workload_sha256 = (
        "89b027058e8f66864edfd6c3a2ccc0be3f006a51432e17eaa0a6e504d7baa456"
    )
    assert provider.authorization_requests == [
        {
            "round_id": first.round_id,
            "workload_content_sha256": expected_workload_sha256,
            "evidence_class": "implementation_test",
        },
        {
            "round_id": second.round_id,
            "workload_content_sha256": expected_workload_sha256,
            "evidence_class": "implementation_test",
        },
    ]
    assert first_seal.calibration.authorization_sha256 != (
        second_seal.calibration.authorization_sha256
    )
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        authorizations = connection.execute(
            "SELECT round_id, authorization_json, authorization_sha256 "
            "FROM judge_authorizations ORDER BY round_id"
        ).fetchall()
    assert len(authorizations) == 2
    for round_id, raw, authorization_sha256 in authorizations:
        record = json.loads(raw)
        assert record["schema_version"] == "judge-authorization-v2"
        assert record["evidence_class"] == "implementation_test"
        assert record["round_id"] == round_id
        assert record["workload_content_sha256"] == expected_workload_sha256
        assert record["model_id"] == judge.model_id
        assert record["provider_profile"] == judge.provider_profile
        assert record["calibration_policy_id"] == "single-human-global-stratified-v2"
        assert record["judge_policy_id"] == "evidence-bounded-judge-v1"
        assert record["content_sha256"] == authorization_sha256


@pytest.mark.parametrize(
    "provider_profile", ["https://provider.example/profile", "token=secret"]
)
def test_judge_authorization_rejects_non_opaque_provider_profile(
    provider_profile: str,
) -> None:
    valid = _authorization(round_id="round:opaque-id")
    content = valid.model_dump(mode="json")
    content["provider_profile"] = provider_profile
    with pytest.raises(ValidationError):
        JudgeAuthorization.model_validate(content)


@pytest.mark.parametrize("model_id", ["https://model.example/v1", "sk-secret-model"])
def test_judge_authorization_rejects_url_or_secret_like_model_id(model_id: str) -> None:
    valid = _authorization(round_id="round:opaque-model")
    content = valid.model_dump(mode="json")
    content["model_id"] = model_id
    with pytest.raises(ValidationError):
        JudgeAuthorization.model_validate(content)


def test_sealed_calibration_is_immutable_but_other_decisions_recompute_lifecycle(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    human_labels = {
        probe["request_sha256"]: ("unsupported" if position <= 12 else "supported")
        for position, probe in enumerate(probes, start=1)
    }
    judge = RecordedJudge(human_labels)
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=human_labels)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="seal-before-contracts",
        )
    )
    assert sealed.lifecycle == "human_labels_sealed"
    assert sealed.task is not None
    assert sealed.task.mutable is True
    assert sealed.task.read_only_reason is None
    calibration_task_id = f"calibration:{probes[0]['sample_id']}"
    read_only_calibration = workspace.open(
        OpenWorkspace(session_token=token, task_id=calibration_task_id)
    )
    assert read_only_calibration.task is not None
    assert read_only_calibration.task.mutable is False
    assert read_only_calibration.task.read_only_reason == "calibration_labels_sealed"
    with pytest.raises(ReviewWorkspaceError) as draft_blocked:
        workspace.record(
            SaveDraft(
                session_token=token,
                task_id=calibration_task_id,
                draft=DraftData(decision="supported", rationale="late"),
            )
        )
    assert draft_blocked.value.code is ReviewErrorCode.INVALID_COMMAND
    with pytest.raises(ReviewWorkspaceError) as label_blocked:
        workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=calibration_task_id,
                task_kind=TaskKind.CALIBRATION,
                decision="supported",
                rationale="late",
                expected_revision=1,
                idempotency_key="late-calibration-label",
            )
        )
    assert label_blocked.value.code is ReviewErrorCode.INVALID_COMMAND

    contract_ids = [
        item.task_id for item in sealed.queue if item.kind is TaskKind.CONTRACT
    ]
    exclusion_ids = [
        item.task_id for item in sealed.queue if item.kind is TaskKind.EXCLUSION
    ]
    current = sealed
    for position, task_id in enumerate(contract_ids, start=1):
        current = workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.CONTRACT,
                decision="approved",
                expected_revision=0,
                idempotency_key=f"postseal-contract-{position}",
            )
        )
    for position, task_id in enumerate(exclusion_ids, start=1):
        current = workspace.record(
            SubmitDecision(
                session_token=token,
                task_id=task_id,
                task_kind=TaskKind.EXCLUSION,
                decision="accept_exclusion",
                rationale="The exclusion record is complete.",
                expected_revision=0,
                idempotency_key=f"postseal-exclusion-{position}",
            )
        )
    assert current.lifecycle == "acceptance_ready"
    assert current.task is None
    assert current.gate_summary.acceptance_ready is True
    assert current.gate_summary.acceptance_blockers == ()

    blocked = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=contract_ids[0],
            task_kind=TaskKind.CONTRACT,
            decision="needs_change",
            rationale="A material field needs correction.",
            expected_revision=1,
            idempotency_key="postseal-contract-revision",
        )
    )
    assert blocked.lifecycle == "review_complete_blocked"
    assert blocked.calibration.passed is True
    assert blocked.gate_summary.acceptance_ready is False
    assert blocked.gate_summary.blocking_task_ids == (contract_ids[0],)

    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        connection.execute(
            "UPDATE rounds SET lifecycle = 'locked' WHERE round_id = ?",
            (blocked.round_id,),
        )
    locked = workspace.open(OpenWorkspace(session_token=token, task_id=contract_ids[0]))
    assert locked.task is not None
    assert locked.task.mutable is False
    assert locked.task.read_only_reason == "round_locked"


def test_snapshot_change_during_external_judge_is_stale_and_persists_nothing(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]

    class MutatingJudge(RecordedJudge):
        workspace: Any = None
        token: str = ""

        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if not self.requests:
                first = probes[0]
                self.workspace.record(
                    SubmitDecision(
                        session_token=self.token,
                        task_id=f"calibration:{first['sample_id']}",
                        task_kind=TaskKind.CALIBRATION,
                        decision="supported",
                        rationale="Changed in another tab while the judge was running.",
                        expected_revision=1,
                        idempotency_key="concurrent-label-change",
                    )
                )
            return super().judge(request)

    judge = MutatingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    judge.workspace = workspace
    judge.token = token
    _submit_calibration_labels(workspace, token)
    with pytest.raises(ReviewWorkspaceError) as stale:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="seal-stale-snapshot",
            )
        )
    assert stale.value.code is ReviewErrorCode.STALE_REVISION
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("failed", "stale_revision")


def test_artifact_change_during_external_judge_aborts_before_seal(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    class ArtifactMutatingJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if not self.requests:
                source = next(fixture.source_root.rglob("*.py"))
                source.write_bytes(source.read_bytes() + b"\n# changed-during-judge\n")
            return super().judge(request)

    judge = ArtifactMutatingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(ReviewWorkspaceError) as mismatch:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="seal-artifact-race",
            )
        )
    assert mismatch.value.code is ReviewErrorCode.ARTIFACT_MISMATCH
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("failed", "artifact_mismatch")


def test_seal_receipt_restarts_exactly_and_storage_is_append_only(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    labels = {
        probe["request_sha256"]: ("unsupported" if position <= 12 else "supported")
        for position, probe in enumerate(probes, start=1)
    }
    judge = RecordedJudge(labels)
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=labels)
    command = SealCalibration(
        session_token=token,
        expected_revision=60,
        idempotency_key="durable-seal-receipt",
    )
    first = workspace.record(command)
    replayed = workspace.record(command)
    assert replayed == first
    assert len(judge.requests) == 60

    restarted = _workspace_with_judge(fixture, judge)
    after_restart = restarted.open(
        OpenWorkspace(
            session_token=token,
            task_id=f"calibration:{probes[0]['sample_id']}",
        )
    )
    assert after_restart.calibration == first.calibration
    assert after_restart.task is not None
    assert after_restart.task.model_judgment == labels[probes[0]["request_sha256"]]
    resumed_identity = restarted.open(
        OpenWorkspace(display_name="Reviewer Li", staff_id="r-1042")
    )
    assert resumed_identity.round_id == first.round_id
    assert resumed_identity.session_token not in {None, token}
    assert resumed_identity.calibration == first.calibration
    with pytest.raises(ReviewWorkspaceError) as reseal:
        restarted.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="different-seal-command",
            )
        )
    assert reseal.value.code is ReviewErrorCode.IDEMPOTENCY_CONFLICT
    assert len(judge.requests) == 60

    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        judge_result_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(judge_results)")
        }
        assert "response_json" in judge_result_columns
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            60,
        )
        response_rows = connection.execute(
            "SELECT response_json, response_sha256, request_sha256, decision, "
            "model_id, judge_policy_id FROM judge_results ORDER BY task_id"
        ).fetchall()
        assert len(response_rows) == 60
        for (
            response_json,
            response_sha256,
            request_sha256,
            decision,
            model_id,
            policy_id,
        ) in response_rows:
            response = json.loads(response_json)
            assert response_json == json.dumps(
                response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            assert hashlib.sha256(response_json.encode("utf-8")).hexdigest() == (
                response_sha256
            )
            assert response == {
                "schema_version": ("canonical-v2-human-calibration-judge-decision-v2"),
                "model_id": model_id,
                "policy_id": policy_id,
                "request_sha256": request_sha256,
                "decision": decision,
                "evidence_scope": "supplied_request_only",
                "used_external_memory": False,
            }
        assert connection.execute(
            "SELECT count(*) FROM judge_authorizations"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM judge_runs WHERE state = 'completed'"
        ).fetchone() == (1,)
        run_ids = {
            row[0]
            for row in connection.execute(
                "SELECT run_id FROM judge_results UNION SELECT run_id FROM calibration_seals"
            )
        }
        assert len(run_ids) == 1
        authorization_json, authorization_sha256 = connection.execute(
            "SELECT authorization_json, authorization_sha256 FROM judge_authorizations"
        ).fetchone()
        authorization = json.loads(authorization_json)
        assert authorization["round_id"] == first.round_id
        claimed = authorization.pop("content_sha256")
        assert claimed == authorization_sha256
        assert (
            claimed
            == hashlib.sha256(
                json.dumps(
                    authorization,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        )

        for statement in (
            "UPDATE judge_results SET decision = 'supported'",
            "DELETE FROM judge_results",
            "UPDATE calibration_seals SET passed = 0",
            "DELETE FROM calibration_seals",
            "UPDATE judge_runs SET command_sha256 = 'tampered'",
            "DELETE FROM judge_runs",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()
    database_bytes = database.read_bytes()
    for forbidden in (
        b"api_key",
        b"credential",
        b"evidence_snapshots",
        b"must not be accepted or stored",
    ):
        assert forbidden not in database_bytes


@pytest.mark.parametrize("fault", ["hash", "schema"])
def test_judge_response_readback_revalidates_canonical_hash_and_schema(
    tmp_path: Path,
    fault: str,
) -> None:
    fixture = _fixture(tmp_path)
    judge = RecordedJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key=f"seal-response-readback-{fault}",
        )
    )
    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(judge_results)")
        }
        assert "response_json" in columns
        result_id, response_json, response_sha256 = connection.execute(
            "SELECT result_id, response_json, response_sha256 FROM judge_results "
            "ORDER BY task_id LIMIT 1"
        ).fetchone()
        response = json.loads(response_json)
        if fault == "hash":
            response["decision"] = (
                "unsupported" if response["decision"] == "supported" else "supported"
            )
            tampered_json = json.dumps(
                response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            tampered_sha256 = response_sha256
        else:
            response["schema_version"] = "canonical-v2-recorded-judge-decision-v1"
            tampered_json = json.dumps(
                response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            tampered_sha256 = hashlib.sha256(tampered_json.encode("utf-8")).hexdigest()
        connection.execute("DROP TRIGGER judge_results_no_update")
        connection.execute(
            "UPDATE judge_results SET response_json = ?, response_sha256 = ? "
            "WHERE result_id = ?",
            (tampered_json, tampered_sha256, result_id),
        )

    with pytest.raises(ReviewWorkspaceError) as invalid:
        workspace.open(OpenWorkspace(session_token=token))
    assert invalid.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert sealed.calibration.pair_count == 60


def test_concurrent_same_seal_has_one_durable_result_set(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    labels = {
        probe["request_sha256"]: ("unsupported" if position <= 12 else "supported")
        for position, probe in enumerate(probes, start=1)
    }

    class BlockingJudge(RecordedJudge):
        def __init__(self) -> None:
            super().__init__(labels)
            self.started = Event()
            self.release = Event()

        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if not self.started.is_set():
                self.started.set()
                assert self.release.wait(timeout=5)
            return super().judge(request)

    judge = BlockingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=labels)
    command = SealCalibration(
        session_token=token,
        expected_revision=60,
        idempotency_key="concurrent-seal",
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(workspace.record, command)
        assert judge.started.wait(timeout=5)
        second = executor.submit(workspace.record, command)
        time.sleep(0.1)
        judge.release.set()
        views = (first.result(timeout=10), second.result(timeout=10))
    assert views[0] == views[1]
    assert len(judge.requests) == 60
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            60,
        )
        assert connection.execute(
            "SELECT count(*) FROM calibration_seals"
        ).fetchone() == (1,)


def test_judge_callback_observes_durable_in_flight_run_claim(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    class ClaimCheckingJudge(RecordedJudge):
        observed: tuple[str, str, str] | None = None

        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if self.observed is None:
                with sqlite3.connect(
                    fixture.state_dir / "review-workbench.sqlite3"
                ) as connection:
                    self.observed = connection.execute(
                        "SELECT state, human_snapshot_sha256, authorization_sha256 "
                        "FROM judge_runs"
                    ).fetchone()
            return super().judge(request)

    judge = ClaimCheckingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="durable-run-claim",
        )
    )
    assert judge.observed is not None
    assert judge.observed[0] == "in_flight"
    assert len(judge.observed[1]) == 64
    assert judge.observed[2] == sealed.calibration.authorization_sha256


def test_failed_run_same_key_is_not_retried_but_new_key_can_retry(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    class OnceFailingJudge(RecordedJudge):
        failed = False

        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if not self.failed:
                self.failed = True
                self.requests.append(request)
                raise TimeoutError
            return super().judge(request)

    judge = OnceFailingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    failed_command = SealCalibration(
        session_token=token,
        expected_revision=60,
        idempotency_key="failed-run-key",
    )
    with pytest.raises(ReviewWorkspaceError) as first_failure:
        workspace.record(failed_command)
    assert first_failure.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    assert len(judge.requests) == 1

    with pytest.raises(ReviewWorkspaceError) as replay_failure:
        workspace.record(failed_command)
    assert replay_failure.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    assert len(judge.requests) == 1

    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="retry-with-new-key",
        )
    )
    assert sealed.calibration.pair_count == 60
    assert len(judge.requests) == 61
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        runs = connection.execute(
            "SELECT state, failure_code FROM judge_runs ORDER BY started_at, run_id"
        ).fetchall()
        assert runs == [("failed", "judge_unavailable"), ("completed", None)]
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            60,
        )


def test_crashed_in_flight_run_blocks_unclaimed_retry(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    class CrashingJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            self.requests.append(request)
            raise SystemExit("simulated process crash")

    judge = CrashingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(SystemExit):
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="crashed-run",
            )
        )
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("in_flight", None)
        assert connection.execute("SELECT count(*) FROM judge_results").fetchone() == (
            0,
        )

    judge.failed = True
    with pytest.raises(ReviewWorkspaceError) as blocked:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="retry-after-crash",
            )
        )
    assert blocked.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE
    assert len(judge.requests) == 1


def test_recovery_abandons_exact_crashed_run_and_unblocks_new_key(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    class CrashingJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            self.requests.append(request)
            raise SystemExit("simulated process crash")

    judge = CrashingJudge()
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(SystemExit):
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="crash-for-recovery",
            )
        )
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        run = connection.execute("SELECT * FROM judge_runs").fetchone()
    assert run is not None

    recovery = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        runtime_instance_id="runtime-instance:recovery-process",
        recovery_only=True,
    )
    receipt = recovery.abandon_in_flight_judge_run(
        AbandonInFlightJudgeRun(
            run_id=run[0],
            round_id=run[1],
            command_sha256=run[3],
            human_snapshot_sha256=run[4],
            authorization_sha256=run[5],
            operator_staff_id="r-1042",
        )
    )
    assert receipt.reason == "process_crash_confirmed"
    with sqlite3.connect(fixture.state_dir / "review-workbench.sqlite3") as connection:
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == (
            "failed",
            "operator_abandoned_after_crash",
        )
        assert connection.execute(
            "SELECT count(*) FROM judge_run_recoveries"
        ).fetchone() == (1,)

    with pytest.raises(ReviewWorkspaceError) as old_key:
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="crash-for-recovery",
            )
        )
    assert old_key.value.code is ReviewErrorCode.JUDGE_UNAVAILABLE


def test_recovery_rejects_same_runtime_without_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    class CrashingJudge(RecordedJudge):
        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            self.requests.append(request)
            raise SystemExit("simulated process crash")

    runtime_instance_id = "runtime-instance:same-process"
    judge = CrashingJudge()
    workspace = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        judge=judge,
        judge_authorization_provider=RecordedAuthorizationProvider(
            model_id=judge.model_id
        ),
        runtime_instance_id=runtime_instance_id,
    )
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    with pytest.raises(SystemExit):
        workspace.record(
            SealCalibration(
                session_token=token,
                expected_revision=60,
                idempotency_key="same-runtime-crash",
            )
        )
    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        run = connection.execute("SELECT * FROM judge_runs").fetchone()
    assert run is not None

    recovery = create_review_workspace(
        packet_path=fixture.packet_path,
        workload_path=fixture.workload_path,
        source_root=fixture.source_root,
        state_dir=fixture.state_dir,
        export_dir=fixture.export_dir,
        runtime_instance_id=runtime_instance_id,
        recovery_only=True,
    )
    with pytest.raises(ReviewWorkspaceError) as rejected:
        recovery.abandon_in_flight_judge_run(
            AbandonInFlightJudgeRun(
                run_id=run[0],
                round_id=run[1],
                command_sha256=run[3],
                human_snapshot_sha256=run[4],
                authorization_sha256=run[5],
                operator_staff_id="r-1042",
            )
        )
    assert rejected.value.code is ReviewErrorCode.INVALID_COMMAND
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state, failure_code FROM judge_runs"
        ).fetchone() == ("in_flight", None)
        assert connection.execute(
            "SELECT count(*) FROM judge_run_recoveries"
        ).fetchone() == (0,)


def test_review_evidence_export_is_idempotent_and_read_authorizes_round(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)
    receipt = workspace.export(
        ExportReview(
            session_token=token,
            mode=ExportMode.REVIEW_EVIDENCE,
            idempotency_key="export-review-evidence",
        )
    )
    replay = workspace.export(
        ExportReview(
            session_token=token,
            mode=ExportMode.REVIEW_EVIDENCE,
            idempotency_key="export-review-evidence",
        )
    )
    assert replay == receipt
    download = workspace.read_export(
        ReadExport(session_token=token, export_id=receipt.export_id)
    )
    payload = json.loads(download.content)
    assert tuple(payload) == (
        "acceptance_eligible",
        "accounting",
        "artifact_identity",
        "calibration_labels",
        "content_sha256",
        "contract_decisions",
        "created_at",
        "decision_events",
        "evidence_class",
        "exclusion_decisions",
        "export_id",
        "gates",
        "judge",
        "mode",
        "round",
        "schema_version",
        "task_2_8_eligible",
    )
    assert payload["schema_version"] == "canonical-v2-human-review-export-v2"
    assert payload["judge"] == {
        "status": "hidden_until_sealed",
        "visibility": "hidden_until_sealed",
    }


def test_prepared_export_is_not_downloadable_until_idempotent_retry_verifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)
    command = ExportReview(
        session_token=token,
        mode=ExportMode.REVIEW_EVIDENCE,
        idempotency_key="prepared-export-retry",
    )

    with monkeypatch.context() as context:

        def fail_write(*, receipt: Any, content: bytes) -> None:
            del receipt, content
            raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)

        context.setattr(workspace, "_write_export_bytes", fail_write)
        with pytest.raises(ReviewWorkspaceError) as interrupted:
            workspace.export(command)
        assert interrupted.value.code is ReviewErrorCode.STORAGE_FAILURE

    database = fixture.state_dir / "review-workbench.sqlite3"
    with sqlite3.connect(database) as connection:
        export_id, state = connection.execute(
            "SELECT export_id, state FROM export_records"
        ).fetchone()
    assert state == "prepared"
    with pytest.raises(ReviewWorkspaceError) as unavailable:
        workspace.read_export(ReadExport(session_token=token, export_id=export_id))
    assert unavailable.value.code is ReviewErrorCode.EXPORT_BLOCKED

    receipt = workspace.export(command)
    assert receipt.export_id == export_id
    assert workspace.read_export(
        ReadExport(session_token=token, export_id=export_id)
    ).content
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state FROM export_records WHERE export_id = ?", (export_id,)
        ).fetchone() == ("verified",)


def test_export_download_rejects_replaced_symlink_directory(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)
    receipt = workspace.export(
        ExportReview(
            session_token=token,
            mode=ExportMode.REVIEW_EVIDENCE,
            idempotency_key="export-directory-symlink",
        )
    )
    replacement = tmp_path / "replacement-exports"
    replacement.mkdir()
    shutil.copyfile(
        fixture.export_dir / receipt.basename,
        replacement / receipt.basename,
    )
    original = tmp_path / "original-exports"
    fixture.export_dir.rename(original)
    fixture.export_dir.symlink_to(replacement, target_is_directory=True)

    with pytest.raises(ReviewWorkspaceError) as replaced:
        workspace.read_export(
            ReadExport(session_token=token, export_id=receipt.export_id)
        )
    assert replaced.value.code is ReviewErrorCode.STORAGE_FAILURE


def test_sealed_export_hashes_judge_attempt_idempotency_key(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace_with_judge(fixture, RecordedJudge())
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token)
    seal_key = "sealed-attempt-secret-key"
    workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key=seal_key,
        )
    )
    receipt = workspace.export(
        ExportReview(
            session_token=token,
            mode=ExportMode.REVIEW_EVIDENCE,
            idempotency_key="sealed-export",
        )
    )
    payload = json.loads(
        workspace.read_export(
            ReadExport(session_token=token, export_id=receipt.export_id)
        ).content
    )
    attempts = payload["judge"]["attempts"]
    assert attempts
    assert all("idempotency_key" not in attempt for attempt in attempts)
    assert (
        attempts[0]["idempotency_sha256"]
        == hashlib.sha256(seal_key.encode("utf-8")).hexdigest()
    )
    assert seal_key not in json.dumps(payload, sort_keys=True)


def test_external_judge_runs_without_a_sqlite_write_transaction(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    labels = {
        probe["request_sha256"]: ("unsupported" if position <= 12 else "supported")
        for position, probe in enumerate(probes, start=1)
    }

    class LockProbeJudge(RecordedJudge):
        checked = False

        def judge(self, request: dict[str, Any]) -> dict[str, Any]:
            if not self.checked:
                with sqlite3.connect(
                    fixture.state_dir / "review-workbench.sqlite3", timeout=0.1
                ) as independent:
                    independent.execute("BEGIN IMMEDIATE")
                    independent.rollback()
                self.checked = True
            return super().judge(request)

    judge = LockProbeJudge(labels)
    workspace = _workspace_with_judge(fixture, judge)
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=labels)
    sealed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="transaction-free-judge",
        )
    )
    assert judge.checked is True
    assert sealed.calibration.passed is True


def test_failed_seal_stays_failed_while_contract_feedback_remains_editable(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    probes = json.loads(fixture.workload_path.read_text(encoding="utf-8"))[
        "calibration_probes"
    ]
    labels = {
        probe["request_sha256"]: ("unsupported" if position <= 12 else "supported")
        for position, probe in enumerate(probes, start=1)
    }
    decisions = dict(labels)
    critical = next(
        probe
        for position, probe in enumerate(probes, start=1)
        if position <= 12 and probe["critical_probe"]
    )
    decisions[critical["request_sha256"]] = "supported"
    workspace = _workspace_with_judge(fixture, RecordedJudge(decisions))
    _, token = _register(workspace)
    _submit_calibration_labels(workspace, token, labels=labels)
    failed = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=60,
            idempotency_key="failed-seal",
        )
    )
    assert failed.lifecycle == "calibration_failed_sealed"
    contract_id = next(
        item.task_id for item in failed.queue if item.kind is TaskKind.CONTRACT
    )
    updated = workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=contract_id,
            task_kind=TaskKind.CONTRACT,
            decision="approved",
            expected_revision=0,
            idempotency_key="feedback-after-failed-seal",
        )
    )
    assert updated.lifecycle == "calibration_failed_sealed"
    assert updated.calibration.passed is False


def test_openai_compatible_adapter_uses_canonical_bounded_request_and_strict_schema() -> (
    None
):
    request = {
        "schema_version": _STIMULUS_SCHEMA,
        "sample_id": "calibration:example",
        "as_of": "2026-07-15T00:00:00Z",
        "requirement": {"predicate": "supports"},
        "candidate_observation": {"claim_id": "claim:1"},
        "evidence_snapshots": [{"evidence_id": "evidence:1", "snippet": "bounded"}],
    }
    valid_response = {
        "schema_version": "canonical-v2-human-calibration-judge-decision-v2",
        "model_id": "review-judge-v1",
        "policy_id": "evidence-bounded-judge-v1",
        "request_sha256": _canonical_sha256(request),
        "decision": "supported",
        "evidence_scope": "supplied_request_only",
        "used_external_memory": False,
    }

    class Completions:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps(self.payload))
                    )
                ]
            )

    completions = Completions(valid_response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    adapter = OpenAICompatibleEvidenceBoundedJudge(
        client=client,
        model_id="review-judge-v1",
        provider_profile="approved-review-profile",
    )
    assert adapter.judge(request) == valid_response
    call = completions.calls[0]
    assert call["model"] == "review-judge-v1"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][1]["content"] == json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    assert "human_label" not in call["messages"][1]["content"]
    assert "exactly" in call["messages"][0]["content"]

    malformed = dict(valid_response, rationale="not allowed")
    malformed_client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions(malformed))
    )
    malformed_adapter = OpenAICompatibleEvidenceBoundedJudge(
        client=malformed_client,
        model_id="review-judge-v1",
        provider_profile="approved-review-profile",
    )
    with pytest.raises(ValidationError):
        malformed_adapter.judge(request)


def test_sqlite_schema_enforces_wal_foreign_keys_and_no_external_state(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _register(workspace)
    database = fixture.state_dir / "review-workbench.sqlite3"

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "workspace_meta",
            "rounds",
            "sessions",
            "drafts",
            "decision_events",
        }.issubset(tables)
        assert connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("canonical-v2-review-workspace-sqlite-v10",)
        assert connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'evidence_class'"
        ).fetchone() == ("implementation_test",)

    files = {path.name for path in fixture.state_dir.iterdir()}
    assert files <= {
        "review-workbench.sqlite3",
        "review-workbench.sqlite3-wal",
        "review-workbench.sqlite3-shm",
    }
    assert not fixture.export_dir.exists()

    source = (
        REPO_ROOT
        / "apps"
        / "admin-console"
        / "backend"
        / "services"
        / "canonical_v2_review.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "psycopg",
        "pymilvus",
        "milvus.db",
        "DATABASE_URL",
        "active_release",
    ):
        assert forbidden not in source


def test_state_and_export_paths_reject_symlinks_and_alias_conflicts(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.state_dir.mkdir()
    outside_database = tmp_path / "outside.sqlite3"
    outside_database.write_bytes(b"outside-must-stay-byte-identical")
    (fixture.state_dir / "review-workbench.sqlite3").symlink_to(outside_database)

    with pytest.raises(ReviewWorkspaceError) as database_symlink:
        _workspace(fixture)
    assert database_symlink.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert str(tmp_path) not in str(database_symlink.value)
    assert outside_database.read_bytes() == b"outside-must-stay-byte-identical"

    outside_state = tmp_path / "outside-state"
    outside_state.mkdir()
    state_alias = tmp_path / "state-alias"
    state_alias.symlink_to(outside_state, target_is_directory=True)
    aliased_fixture = replace(fixture, state_dir=state_alias)
    with pytest.raises(ReviewWorkspaceError) as directory_symlink:
        _workspace(aliased_fixture)
    assert directory_symlink.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert list(outside_state.iterdir()) == []

    clean_fixture = replace(
        fixture,
        state_dir=tmp_path / "clean-state",
        export_dir=tmp_path / "clean-state" / "exports",
    )
    with pytest.raises(ReviewWorkspaceError) as path_conflict:
        _workspace(clean_fixture)
    assert path_conflict.value.code is ReviewErrorCode.STORAGE_FAILURE

    export_target = tmp_path / "outside-exports"
    export_target.mkdir()
    export_alias = tmp_path / "export-alias"
    export_alias.symlink_to(export_target, target_is_directory=True)
    export_fixture = replace(
        fixture,
        state_dir=tmp_path / "another-clean-state",
        export_dir=export_alias,
    )
    with pytest.raises(ReviewWorkspaceError) as export_symlink:
        _workspace(export_fixture)
    assert export_symlink.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert list(export_target.iterdir()) == []


def test_preexisting_database_hardlink_is_rejected_before_chmod_or_ddl(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.state_dir.mkdir()
    outside_database = tmp_path / "outside-hardlink.sqlite3"
    sentinel = b"outside-hardlink-must-remain-unchanged"
    outside_database.write_bytes(sentinel)
    outside_database.chmod(0o640)
    original_mode = outside_database.stat().st_mode
    os.link(
        outside_database,
        fixture.state_dir / "review-workbench.sqlite3",
    )

    with pytest.raises(ReviewWorkspaceError) as hardlink_failure:
        _workspace(fixture)
    assert hardlink_failure.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert str(tmp_path) not in str(hardlink_failure.value)
    assert outside_database.read_bytes() == sentinel
    assert outside_database.stat().st_mode == original_mode
    assert {path.name for path in fixture.state_dir.iterdir()} == {
        "review-workbench.sqlite3"
    }


def test_runtime_database_hardlink_blocks_reads_and_writes_without_mutation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    assert opened.task is not None
    task_id = opened.task.task_id
    database = fixture.state_dir / "review-workbench.sqlite3"
    before_bytes = database.read_bytes()
    with sqlite3.connect(database) as connection:
        before_counts = (
            connection.execute("SELECT count(*) FROM decision_events").fetchone(),
            connection.execute("SELECT count(*) FROM drafts").fetchone(),
        )
    outside_link = tmp_path / "runtime-outside-link.sqlite3"
    os.link(database, outside_link)
    assert database.stat().st_nlink == 2

    operations = (
        lambda: workspace.open(OpenWorkspace(session_token=token)),
        lambda: workspace.record(
            SaveDraft(
                session_token=token,
                task_id=task_id,
                draft=DraftData(decision="approved", rationale="must not persist"),
            )
        ),
    )
    for operation in operations:
        with pytest.raises(ReviewWorkspaceError) as hardlink_failure:
            operation()
        assert hardlink_failure.value.code is ReviewErrorCode.STORAGE_FAILURE
        assert str(tmp_path) not in str(hardlink_failure.value)

    assert database.read_bytes() == before_bytes
    with sqlite3.connect(database) as connection:
        after_counts = (
            connection.execute("SELECT count(*) FROM decision_events").fetchone(),
            connection.execute("SELECT count(*) FROM drafts").fetchone(),
        )
    assert after_counts == before_counts == ((0,), (0,))


def test_corrupt_sqlite_and_projection_data_map_to_stable_storage_failure(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    opened, token = _register(workspace)
    database = fixture.state_dir / "review-workbench.sqlite3"
    database.write_bytes(b"not-a-sqlite-database")

    for operation in (
        lambda: workspace.open(OpenWorkspace(session_token=token)),
        lambda: workspace.export(
            ExportReview(session_token=token, mode=ExportMode.REVIEW_EVIDENCE)
        ),
    ):
        with pytest.raises(ReviewWorkspaceError) as storage_failure:
            operation()
        assert storage_failure.value.code is ReviewErrorCode.STORAGE_FAILURE
        assert "sqlite" not in str(storage_failure.value).lower()
        assert "database" not in str(storage_failure.value).lower()

    projection_root = tmp_path / "projection"
    projection_root.mkdir()
    projection_fixture = _fixture(projection_root)
    projection_workspace = _workspace(projection_fixture)
    projection_opened, projection_token = _register(projection_workspace)
    assert projection_opened.task is not None
    task_id = projection_opened.task.task_id
    projection_workspace.record(
        SaveDraft(
            session_token=projection_token,
            task_id=task_id,
            draft=DraftData(decision="approved", rationale="valid draft"),
        )
    )
    with sqlite3.connect(
        projection_fixture.state_dir / "review-workbench.sqlite3"
    ) as connection:
        connection.execute(
            "UPDATE drafts SET payload_json = '{broken-json' WHERE task_id = ?",
            (task_id,),
        )
    with pytest.raises(ReviewWorkspaceError) as projection_failure:
        projection_workspace.open(
            OpenWorkspace(session_token=projection_token, task_id=task_id)
        )
    assert projection_failure.value.code is ReviewErrorCode.STORAGE_FAILURE
    assert "json" not in str(projection_failure.value).lower()


def test_review_evidence_export_is_available_before_acceptance(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    workspace = _workspace(fixture)
    _, token = _register(workspace)

    receipt = workspace.export(
        ExportReview(session_token=token, mode=ExportMode.REVIEW_EVIDENCE)
    )
    assert receipt.acceptance_eligible is False
    assert (fixture.export_dir / receipt.basename).is_file()
