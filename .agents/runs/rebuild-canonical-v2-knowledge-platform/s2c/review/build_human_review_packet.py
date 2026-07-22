"""Build the deterministic, deliberately unapproved S2C human-review packet."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


__all__ = ("build_review_packet",)

_HERE = Path(__file__).resolve().parent
_S2C = _HERE.parent
_EVALUATOR_PATH = _S2C / "claim_level_oracle_evaluation.py"
_DEFAULT_MANIFEST_PATH = _S2C / "claim-level-corpus-manifest-v1.json"
_DEFAULT_OUTPUT_PATH = _HERE / "human-review-packet-v1.json"
_EXPECTED_MANIFEST_CONTENT_SHA256 = (
    "df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff"
)
_EXPECTED_MANIFEST_FILE_SHA256 = (
    "fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f"
)
_ADMISSION_JUDGE_IDENTITY = {
    "model_id": "s2c3c1-no-judge-admission",
    "policy_id": "evidence-bounded-judge-v1",
}
_JUDGE_POLICY_ID = "evidence-bounded-judge-v1"


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
        raise ValueError("review packet is not canonical JSON") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jsonl_bytes(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"review packet input is invalid JSONL: {label}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"review packet input rows must be objects: {label}")
    return rows


def _evaluator_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_evaluator_for_review_packet", _EVALUATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise ValueError("accepted claim-level evaluator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if tuple(getattr(module, "__all__", ())) != ("evaluate_oracle_run",):
        raise ValueError("accepted claim-level evaluator interface mismatch")
    return module


def _admit(
    manifest_path: Path,
) -> tuple[dict[str, Any], Any, list[dict[str, Any]], list[dict[str, Any]]]:
    run_input = {
        "exclusions": [],
        "expected_manifest_content_sha256": _EXPECTED_MANIFEST_CONTENT_SHA256,
        "human_reviews": [],
        "judge_calibrations": [],
        "judge_policy": dict(_ADMISSION_JUDGE_IDENTITY),
        "observations": {},
        "run_id": "oracle-run:s2c3c1-review-packet",
        "schema_version": "canonical-v2-oracle-run-input-v1",
        "selected_case_ids": [],
        "soft_metrics": {},
    }
    result = _evaluator_module().evaluate_oracle_run(manifest_path, run_input)
    identity = result.artifact_identity
    if (
        identity.manifest_content_sha256 != _EXPECTED_MANIFEST_CONTENT_SHA256
        or identity.manifest_file_sha256 != _EXPECTED_MANIFEST_FILE_SHA256
    ):
        raise ValueError("manifest identity is not the Accepted S2C2 version")
    if result.corpus_summary != {
        "blocked_missing_evidence": 23,
        "case_count": 52,
        "human_reviewed": 0,
        "pending_user_review": 29,
        "acceptance_eligible": 0,
    }:
        raise ValueError("manifest review-state accounting is not the Accepted draft")
    if result.acceptance_ready is not False:
        raise ValueError("unreviewed source corpus cannot be acceptance ready")

    artifact_paths = {
        "case-accounting-v1.jsonl": manifest_path.with_name("case-accounting-v1.jsonl"),
        "claim-level-corpus-v1.jsonl": manifest_path.with_name(
            "claim-level-corpus-v1.jsonl"
        ),
        "source-snapshots-v1.jsonl": manifest_path.with_name(
            "source-snapshots-v1.jsonl"
        ),
    }
    try:
        manifest_bytes = manifest_path.read_bytes()
        artifact_bytes = {
            name: path.read_bytes() for name, path in artifact_paths.items()
        }
    except OSError as exc:
        raise ValueError("accepted review-packet input cannot be captured") from exc
    if hashlib.sha256(manifest_bytes).hexdigest() != identity.manifest_file_sha256:
        raise ValueError("manifest identity changed after admission")
    for name, payload in artifact_bytes.items():
        if hashlib.sha256(payload).hexdigest() != identity.output_sha256s[name]:
            raise ValueError(f"{name} identity changed after admission")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("captured manifest identity is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("content_sha256") != (
        _EXPECTED_MANIFEST_CONTENT_SHA256
    ):
        raise ValueError("captured manifest content identity mismatch")
    contracts = _jsonl_bytes(
        artifact_bytes["claim-level-corpus-v1.jsonl"],
        label="claim-level-corpus-v1.jsonl",
    )
    accounts = _jsonl_bytes(
        artifact_bytes["case-accounting-v1.jsonl"],
        label="case-accounting-v1.jsonl",
    )
    _jsonl_bytes(
        artifact_bytes["source-snapshots-v1.jsonl"],
        label="source-snapshots-v1.jsonl",
    )
    return manifest, identity, contracts, accounts


def _reference_context_identity(contract: dict[str, Any]) -> dict[str, Any]:
    reference = contract["reference_context"]
    return {
        "answer_role": "review_only",
        "legacy_source_locator": reference["legacy_source_locator"],
        "reference_key_points_sha256": _text_sha256(reference["reference_key_points"]),
        "reference_prose_sha256": _text_sha256(reference["reference_prose"]),
    }


def _review_candidate(
    contract: dict[str, Any], account: dict[str, Any]
) -> dict[str, Any]:
    hard_ids = contract["outcome_policy"]["hard_requirement_ids"]
    snapshot_ids = [
        snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]
    ]
    family = account["family"]
    return {
        "as_of": contract["as_of"],
        "case_id": contract["case_id"],
        "contract_content_sha256": contract["content_sha256"],
        "family": family,
        "hard_requirement_ids": hard_ids,
        "query": contract["query"],
        "reference_context_identity": _reference_context_identity(contract),
        "review_template": {
            "case_id": contract["case_id"],
            "contract_content_sha256": contract["content_sha256"],
            "family": family,
            "review_state": None,
            "reviewed_hard_requirement_ids": hard_ids,
            "reviewer_id": None,
            "reviewer_kind": "human",
            "snapshot_ids": snapshot_ids,
        },
        "snapshot_ids": snapshot_ids,
        "source_case_id": contract["source_case_id"],
        "structured_requirements": {
            "allowed_variants": contract["allowed_variants"],
            "enumeration_policy": contract["enumeration_policy"],
            "forbidden_claims": contract["forbidden_claims"],
            "forbidden_entities": contract["forbidden_entities"],
            "required_claims": contract["required_claims"],
            "required_entities": contract["required_entities"],
            "stage_oracles": contract["stage_oracles"],
        },
    }


def _exclusion_candidate(
    contract: dict[str, Any], account: dict[str, Any]
) -> dict[str, Any]:
    return {
        "case_id": contract["case_id"],
        "contract_content_sha256": contract["content_sha256"],
        "evidence_gap_reason": contract["unavailable_evidence_reason"],
        "exclusion_state": "proposed_pending_evidence",
        "family": account["family"],
        "review_state": "blocked_missing_evidence",
        "snapshot_ids": [
            snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]
        ],
        "source_case_id": contract["source_case_id"],
    }


def _calibration_requirements(
    review_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    family_counts = Counter(candidate["family"] for candidate in review_candidates)
    return [
        {
            "calibration_template": {
                "agreement": None,
                "double_reviewed_samples": None,
                "family": family,
                "model_id": None,
                "policy_id": _JUDGE_POLICY_ID,
                "reviewer_ids": [],
            },
            "candidate_case_count": family_counts[family],
            "family": family,
            "judge_identity": {
                "model_id": None,
                "policy_id": _JUDGE_POLICY_ID,
                "selection_state": "pending_external_authorization",
            },
            "minimum_agreement": 0.80,
            "minimum_double_reviewed_samples": 50,
        }
        for family in sorted(family_counts)
    ]


def build_review_packet(
    manifest_path: str | Path = _DEFAULT_MANIFEST_PATH,
    *,
    output_path: str | Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    """Build or check the exact no-approval review packet."""

    source_manifest = Path(manifest_path).resolve()
    manifest, identity, contracts, account_rows = _admit(source_manifest)
    accounts = {row["contract_case_id"]: row for row in account_rows}
    if len(accounts) != len(contracts):
        raise ValueError("review packet case/account identity is incomplete")
    review_candidates = [
        _review_candidate(contract, accounts[contract["case_id"]])
        for contract in contracts
        if contract["review_state"] == "pending_user_review"
    ]
    exclusion_candidates = [
        _exclusion_candidate(contract, accounts[contract["case_id"]])
        for contract in contracts
        if contract["review_state"] == "blocked_missing_evidence"
    ]
    calibrations = _calibration_requirements(review_candidates)
    payload = {
        "approval_state": "awaiting_external_human_review",
        "as_of": manifest["contract_as_of"],
        "calibration_requirements": calibrations,
        "counts": {
            "blocked_exclusion_candidates": len(exclusion_candidates),
            "calibration_families": len(calibrations),
            "human_reviewed": 0,
            "pending_review_candidates": len(review_candidates),
            "source_cases": len(contracts),
        },
        "exclusion_candidates": exclusion_candidates,
        "packet_version": "s2c-human-review-packet-v1",
        "review_candidates": review_candidates,
        "schema_version": "canonical-v2-human-review-packet-v1",
        "source_identity": {
            "accounting_file_sha256": identity.output_sha256s[
                "case-accounting-v1.jsonl"
            ],
            "case_contract_schema_version": (identity.case_contract_schema_version),
            "contract_version": identity.contract_version,
            "corpus_file_sha256": identity.output_sha256s[
                "claim-level-corpus-v1.jsonl"
            ],
            "corpus_id": identity.corpus_id,
            "manifest_content_sha256": identity.manifest_content_sha256,
            "manifest_file_sha256": identity.manifest_file_sha256,
            "snapshot_file_sha256": identity.output_sha256s[
                "source-snapshots-v1.jsonl"
            ],
        },
    }
    packet = {**payload, "content_sha256": _canonical_sha256(payload)}
    serialized = _canonical_bytes(packet).decode("utf-8")
    if (
        '"approved"' in serialized
        or '"reference_prose"' in serialized
        or '"reference_key_points"' in serialized
        or '"reviewer_kind":"agent"' in serialized
        or '"reviewer_kind":"model"' in serialized
    ):
        raise ValueError("review packet contains a prefilled or prose-normative value")

    destination = None if output_path is None else Path(output_path).resolve()
    if destination is not None:
        expected_bytes = (
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if check:
            if not destination.is_file() or destination.read_bytes() != expected_bytes:
                raise ValueError("human review packet deterministic check failed")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(expected_bytes)
    elif check:
        raise ValueError("human review packet check requires an output path")
    return packet


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    packet = build_review_packet(
        args.manifest,
        output_path=args.output,
        check=args.check,
    )
    print(
        json.dumps(
            {
                "approval_state": packet["approval_state"],
                "content_sha256": packet["content_sha256"],
                "counts": packet["counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
