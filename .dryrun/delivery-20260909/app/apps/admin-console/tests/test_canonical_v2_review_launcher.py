from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

import pytest

from backend.services.canonical_v2_review import EvidenceClass
from scripts import run_canonical_v2_review as launcher


REQUIRED = [
    "--packet",
    "/tmp/packet.json",
    "--workload",
    "/tmp/workload.json",
    "--source-root",
    "/tmp/source",
    "--state-dir",
    "/tmp/state",
    "--export-dir",
    "/tmp/exports",
    "--public-origin",
    "http://127.0.0.1:18189",
]


def test_serve_defaults_to_requested_external_bind_without_storage_options() -> None:
    args = launcher._parse_args(REQUIRED)

    assert args.host == "0.0.0.0"
    assert args.port == 18189
    assert args.real_human_round is False
    help_text = launcher._parser().format_help().lower()
    assert "database" not in help_text
    assert "milvus" not in help_text
    assert "api-key" not in help_text
    assert "required when sealing" in help_text


def test_real_human_round_can_start_before_judge_environment_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in launcher.REAL_JUDGE_ENV:
        monkeypatch.delenv(name, raising=False)

    judge, authorization, evidence_class = launcher._judge_dependencies(
        real_human_round=True
    )

    assert judge is None
    assert authorization is None
    assert evidence_class is EvidenceClass.REAL_HUMAN_ROUND


def test_real_human_round_rejects_partial_judge_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in launcher.REAL_JUDGE_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CANONICAL_V2_REVIEW_JUDGE_MODEL", "review-judge-v1")

    with pytest.raises(launcher.LauncherConfigurationError, match="real judge"):
        launcher._judge_dependencies(real_human_round=True)


def test_real_authorization_is_exact_and_content_addressed() -> None:
    provider = launcher.EnvironmentJudgeAuthorizationProvider(
        authorizer_id="review-owner-1",
        provider_profile="approved-review-profile",
        model_id="review-judge-v1",
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    authorization = provider.authorize(
        round_id="round:one",
        workload_content_sha256="a" * 64,
        evidence_class=EvidenceClass.REAL_HUMAN_ROUND,
    )
    payload = authorization.model_dump(mode="json", exclude={"content_sha256"})
    expected_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    assert provider.is_real_authorization_provider is True
    assert authorization.schema_version == "judge-authorization-v2"
    assert authorization.evidence_scope == "supplied_request_only"
    assert authorization.content_sha256 == expected_hash


def test_real_authorization_rejects_non_real_evidence_class() -> None:
    provider = launcher.EnvironmentJudgeAuthorizationProvider(
        authorizer_id="review-owner-1",
        provider_profile="approved-review-profile",
        model_id="review-judge-v1",
    )

    with pytest.raises(launcher.LauncherConfigurationError):
        provider.authorize(
            round_id="round:one",
            workload_content_sha256="a" * 64,
            evidence_class=EvidenceClass.IMPLEMENTATION_TEST,
        )


def test_main_runs_one_non_reloading_worker_without_access_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_app = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_create_app", lambda args: sentinel_app)
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda app, **kwargs: observed.update(app=app, **kwargs),
    )

    assert launcher.main(REQUIRED) == 0
    assert observed == {
        "app": sentinel_app,
        "host": "0.0.0.0",
        "port": 18189,
        "workers": 1,
        "reload": False,
        "access_log": False,
    }


def test_recovery_requires_the_complete_exact_run_identity() -> None:
    with pytest.raises(launcher.LauncherConfigurationError, match="recovery identity"):
        launcher._parse_args([*REQUIRED, "--recover-run-id", "judge-run:one"])


def test_recovery_uses_the_offline_path_and_does_not_start_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recovery_args = [
        *REQUIRED,
        "--real-human-round",
        "--recover-run-id",
        "judge-run:one",
        "--recover-round-id",
        "round:one",
        "--recover-command-sha256",
        "a" * 64,
        "--recover-human-snapshot-sha256",
        "b" * 64,
        "--recover-authorization-sha256",
        "c" * 64,
        "--recover-operator-staff-id",
        "ops-1",
    ]
    observed: list[object] = []
    monkeypatch.setattr(launcher, "_recover", lambda args: observed.append(args) or 0)
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda *args, **kwargs: pytest.fail("recovery must not start HTTP"),
    )

    assert launcher.main(recovery_args) == 0
    assert len(observed) == 1
