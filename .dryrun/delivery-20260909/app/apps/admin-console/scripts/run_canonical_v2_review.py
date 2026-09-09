"""Run the isolated Canonical V2 single-human review workbench."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import uvicorn

from backend.main import create_canonical_v2_review_app
from backend.services.canonical_v2_review import (
    AbandonInFlightJudgeRun,
    EvidenceClass,
    JudgeAuthorization,
    OpenAICompatibleEvidenceBoundedJudge,
    create_review_workspace,
)


CALIBRATION_POLICY_ID = "single-human-global-stratified-v2"
JUDGE_POLICY_ID = "evidence-bounded-judge-v1"
REAL_JUDGE_ENV = (
    "OPENAI_API_KEY",
    "CANONICAL_V2_REVIEW_JUDGE_MODEL",
    "CANONICAL_V2_REVIEW_PROVIDER_PROFILE",
    "CANONICAL_V2_REVIEW_AUTHORIZER_ID",
)


class LauncherConfigurationError(RuntimeError):
    """The explicit isolated-review launch configuration is incomplete."""


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class EnvironmentJudgeAuthorizationProvider:
    """Issue a round-bound authorization from explicit operator configuration."""

    def __init__(
        self,
        *,
        authorizer_id: str,
        provider_profile: str,
        model_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._authorizer_id = authorizer_id
        self._provider_profile = provider_profile
        self._model_id = model_id
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def is_real_authorization_provider(self) -> bool:
        return True

    def authorize(
        self,
        *,
        round_id: str,
        workload_content_sha256: str,
        evidence_class: EvidenceClass,
    ) -> JudgeAuthorization:
        if evidence_class is not EvidenceClass.REAL_HUMAN_ROUND:
            raise LauncherConfigurationError("real judge authorization requires real evidence")
        payload: dict[str, Any] = {
            "schema_version": "judge-authorization-v2",
            "evidence_class": evidence_class.value,
            "round_id": round_id,
            "authorizer_id": self._authorizer_id,
            "provider_profile": self._provider_profile,
            "model_id": self._model_id,
            "calibration_policy_id": CALIBRATION_POLICY_ID,
            "judge_policy_id": JUDGE_POLICY_ID,
            "workload_content_sha256": workload_content_sha256,
            "authorized_at": self._clock().isoformat(),
            "evidence_scope": "supplied_request_only",
        }
        authorization = JudgeAuthorization.model_validate(
            {**payload, "content_sha256": "0" * 64}
        )
        canonical_payload = authorization.model_dump(
            mode="json", exclude={"content_sha256"}
        )
        return authorization.model_copy(
            update={"content_sha256": _canonical_sha256(canonical_payload)}
        )


def _required_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in REAL_JUDGE_ENV}
    configured = tuple(bool(value) for value in values.values())
    if not any(configured):
        return {}
    if not all(configured):
        raise LauncherConfigurationError("real judge environment is incomplete")
    return values


def _judge_dependencies(
    *, real_human_round: bool
) -> tuple[
    OpenAICompatibleEvidenceBoundedJudge | None,
    EnvironmentJudgeAuthorizationProvider | None,
    EvidenceClass,
]:
    if not real_human_round:
        return None, None, EvidenceClass.IMPLEMENTATION_TEST

    values = _required_environment()
    if not values:
        return None, None, EvidenceClass.REAL_HUMAN_ROUND
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=values["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
            max_retries=0,
            timeout=120.0,
        )
    except Exception as exc:
        raise LauncherConfigurationError("real judge client is unavailable") from exc

    model_id = values["CANONICAL_V2_REVIEW_JUDGE_MODEL"]
    provider_profile = values["CANONICAL_V2_REVIEW_PROVIDER_PROFILE"]
    judge = OpenAICompatibleEvidenceBoundedJudge(
        client=client,
        model_id=model_id,
        provider_profile=provider_profile,
    )
    authorization = EnvironmentJudgeAuthorizationProvider(
        authorizer_id=values["CANONICAL_V2_REVIEW_AUTHORIZER_ID"],
        provider_profile=provider_profile,
        model_id=model_id,
    )
    return judge, authorization, EvidenceClass.REAL_HUMAN_ROUND


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the isolated Canonical V2 human-review workbench."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18189)
    parser.add_argument(
        "--real-human-round",
        action="store_true",
        help=(
            "admit attributable human evidence; explicit real judge configuration is "
            "required when sealing"
        ),
    )
    parser.add_argument("--recover-run-id")
    parser.add_argument("--recover-round-id")
    parser.add_argument("--recover-command-sha256")
    parser.add_argument("--recover-human-snapshot-sha256")
    parser.add_argument("--recover-authorization-sha256")
    parser.add_argument("--recover-operator-staff-id")
    return parser


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    args = _parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise LauncherConfigurationError("port is outside the valid range")
    recovery_identity = (
        args.recover_run_id,
        args.recover_round_id,
        args.recover_command_sha256,
        args.recover_human_snapshot_sha256,
        args.recover_authorization_sha256,
        args.recover_operator_staff_id,
    )
    if any(recovery_identity) and not all(recovery_identity):
        raise LauncherConfigurationError("complete recovery identity is required")
    return args


def _create_app(args: argparse.Namespace):
    judge, authorization, evidence_class = _judge_dependencies(
        real_human_round=bool(args.real_human_round)
    )
    workspace = create_review_workspace(
        packet_path=args.packet,
        workload_path=args.workload,
        source_root=args.source_root,
        state_dir=args.state_dir,
        export_dir=args.export_dir,
        judge=judge,
        judge_authorization_provider=authorization,
        evidence_class=evidence_class,
    )
    return create_canonical_v2_review_app(
        review_workspace=workspace,
        public_origin=args.public_origin,
    )


def _recover(args: argparse.Namespace) -> int:
    evidence_class = (
        EvidenceClass.REAL_HUMAN_ROUND
        if args.real_human_round
        else EvidenceClass.IMPLEMENTATION_TEST
    )
    workspace = create_review_workspace(
        packet_path=args.packet,
        workload_path=args.workload,
        source_root=args.source_root,
        state_dir=args.state_dir,
        export_dir=args.export_dir,
        evidence_class=evidence_class,
        recovery_only=True,
    )
    receipt = workspace.abandon_in_flight_judge_run(
        AbandonInFlightJudgeRun(
            run_id=args.recover_run_id,
            round_id=args.recover_round_id,
            command_sha256=args.recover_command_sha256,
            human_snapshot_sha256=args.recover_human_snapshot_sha256,
            authorization_sha256=args.recover_authorization_sha256,
            operator_staff_id=args.recover_operator_staff_id,
        )
    )
    print(receipt.model_dump_json())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.recover_run_id:
        return _recover(args)
    app = _create_app(args)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,
        reload=False,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
