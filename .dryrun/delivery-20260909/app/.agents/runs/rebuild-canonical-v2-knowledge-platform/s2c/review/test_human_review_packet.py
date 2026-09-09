from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


HERE = Path(__file__).resolve().parent
S2C = HERE.parent
TARGET_PATH = HERE / "build_human_review_packet.py"
MANIFEST_PATH = S2C / "claim-level-corpus-manifest-v1.json"
PACKET_PATH = HERE / "human-review-packet-v1.json"
MANIFEST_CONTENT_SHA256 = (
    "df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff"
)
MANIFEST_FILE_SHA256 = (
    "fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f"
)


class _MissingHumanReviewPacketBuilder(AssertionError):
    """The exact S2C3C1 review-packet builder is intentionally absent in RED."""


def _builder_module() -> Any:
    if not TARGET_PATH.is_file():
        raise _MissingHumanReviewPacketBuilder(
            f"exact target file is absent: {TARGET_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_human_review_packet", TARGET_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("human-review packet target cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if tuple(getattr(module, "__all__", ())) != ("build_review_packet",):
        raise AssertionError("review packet builder must expose one public seam")
    if not callable(getattr(module, "build_review_packet", None)):
        raise AssertionError("review packet builder lacks build_review_packet")
    return module


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingHumanReviewPacketBuilder,
    reason="S2C3C1 RED: deterministic unapproved review-packet builder is absent",
)
def test_human_review_packet_is_complete_deterministic_and_unapproved(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    packet = module.build_review_packet(MANIFEST_PATH)

    assert set(packet) == {
        "approval_state",
        "as_of",
        "calibration_requirements",
        "content_sha256",
        "counts",
        "exclusion_candidates",
        "packet_version",
        "review_candidates",
        "schema_version",
        "source_identity",
    }
    content_sha256 = packet.pop("content_sha256")
    assert content_sha256 == _canonical_sha256(packet)
    packet["content_sha256"] = content_sha256
    assert packet["schema_version"] == "canonical-v2-human-review-packet-v1"
    assert packet["packet_version"] == "s2c-human-review-packet-v1"
    assert packet["approval_state"] == "awaiting_external_human_review"
    assert packet["counts"] == {
        "blocked_exclusion_candidates": 23,
        "calibration_families": len(packet["calibration_requirements"]),
        "human_reviewed": 0,
        "pending_review_candidates": 29,
        "source_cases": 52,
    }
    assert packet["source_identity"] == {
        "accounting_file_sha256": (
            "e953c2fcf64daf66614e26831f0d1263f087263bcdb9771fc20b6123e34fbc48"
        ),
        "case_contract_schema_version": ("canonical-v2-claim-level-case-contract-v1"),
        "contract_version": "claim-level-contract-v1",
        "corpus_file_sha256": (
            "75ff02e0610b93274eba530994a3b04c2bc2a427df9db2ae6d07aaee690a6668"
        ),
        "corpus_id": "canonical-v2-s2c-v1",
        "manifest_content_sha256": MANIFEST_CONTENT_SHA256,
        "manifest_file_sha256": MANIFEST_FILE_SHA256,
        "snapshot_file_sha256": (
            "85c1e4c1660e151526d54f9b1416917782f961b318091550bb3ef8042d16e253"
        ),
    }

    accounts = {
        row["contract_case_id"]: row for row in _jsonl(S2C / "case-accounting-v1.jsonl")
    }
    contracts = {
        row["case_id"]: row for row in _jsonl(S2C / "claim-level-corpus-v1.jsonl")
    }
    review_candidates = packet["review_candidates"]
    exclusion_candidates = packet["exclusion_candidates"]
    assert len(review_candidates) == 29
    assert len(exclusion_candidates) == 23
    all_packet_case_ids = [row["case_id"] for row in review_candidates] + [
        row["case_id"] for row in exclusion_candidates
    ]
    assert len(all_packet_case_ids) == len(set(all_packet_case_ids)) == 52
    assert set(all_packet_case_ids) == set(contracts)

    review_candidate_keys = {
        "as_of",
        "case_id",
        "contract_content_sha256",
        "family",
        "hard_requirement_ids",
        "query",
        "reference_context_identity",
        "review_template",
        "snapshot_ids",
        "source_case_id",
        "structured_requirements",
    }
    review_template_keys = {
        "case_id",
        "contract_content_sha256",
        "family",
        "review_state",
        "reviewed_hard_requirement_ids",
        "reviewer_id",
        "reviewer_kind",
        "snapshot_ids",
    }
    for candidate in review_candidates:
        assert set(candidate) == review_candidate_keys
        contract = contracts[candidate["case_id"]]
        account = accounts[candidate["case_id"]]
        assert contract["review_state"] == "pending_user_review"
        assert candidate["as_of"] == contract["as_of"]
        assert candidate["query"] == contract["query"]
        assert candidate["source_case_id"] == contract["source_case_id"]
        assert candidate["contract_content_sha256"] == contract["content_sha256"]
        assert candidate["family"] == account["family"]
        assert (
            candidate["hard_requirement_ids"]
            == contract["outcome_policy"]["hard_requirement_ids"]
        )
        assert candidate["snapshot_ids"] == [
            snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]
        ]
        assert candidate["structured_requirements"] == {
            "allowed_variants": contract["allowed_variants"],
            "enumeration_policy": contract["enumeration_policy"],
            "forbidden_claims": contract["forbidden_claims"],
            "forbidden_entities": contract["forbidden_entities"],
            "required_claims": contract["required_claims"],
            "required_entities": contract["required_entities"],
            "stage_oracles": contract["stage_oracles"],
        }
        reference = contract["reference_context"]
        assert candidate["reference_context_identity"] == {
            "answer_role": "review_only",
            "legacy_source_locator": reference["legacy_source_locator"],
            "reference_key_points_sha256": (
                None
                if reference["reference_key_points"] is None
                else hashlib.sha256(
                    reference["reference_key_points"].encode("utf-8")
                ).hexdigest()
            ),
            "reference_prose_sha256": (
                None
                if reference["reference_prose"] is None
                else hashlib.sha256(
                    reference["reference_prose"].encode("utf-8")
                ).hexdigest()
            ),
        }
        template = candidate["review_template"]
        assert set(template) == review_template_keys
        assert template == {
            "case_id": contract["case_id"],
            "contract_content_sha256": contract["content_sha256"],
            "family": account["family"],
            "review_state": None,
            "reviewed_hard_requirement_ids": contract["outcome_policy"][
                "hard_requirement_ids"
            ],
            "reviewer_id": None,
            "reviewer_kind": "human",
            "snapshot_ids": [
                snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]
            ],
        }

    exclusion_candidate_keys = {
        "case_id",
        "contract_content_sha256",
        "evidence_gap_reason",
        "exclusion_state",
        "family",
        "review_state",
        "snapshot_ids",
        "source_case_id",
    }
    for candidate in exclusion_candidates:
        assert set(candidate) == exclusion_candidate_keys
        contract = contracts[candidate["case_id"]]
        account = accounts[candidate["case_id"]]
        assert contract["review_state"] == "blocked_missing_evidence"
        assert candidate == {
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

    expected_family_counts = Counter(
        accounts[candidate["case_id"]]["family"] for candidate in review_candidates
    )
    assert len(packet["calibration_requirements"]) == len(expected_family_counts)
    assert [row["family"] for row in packet["calibration_requirements"]] == sorted(
        expected_family_counts
    )
    for requirement in packet["calibration_requirements"]:
        assert set(requirement) == {
            "calibration_template",
            "candidate_case_count",
            "family",
            "judge_identity",
            "minimum_agreement",
            "minimum_double_reviewed_samples",
        }
        family = requirement["family"]
        assert requirement["candidate_case_count"] == expected_family_counts[family]
        assert requirement["minimum_agreement"] == 0.80
        assert requirement["minimum_double_reviewed_samples"] == 50
        assert requirement["judge_identity"] == {
            "model_id": None,
            "policy_id": "evidence-bounded-judge-v1",
            "selection_state": "pending_external_authorization",
        }
        assert requirement["calibration_template"] == {
            "agreement": None,
            "double_reviewed_samples": None,
            "family": family,
            "model_id": None,
            "policy_id": "evidence-bounded-judge-v1",
            "reviewer_ids": [],
        }

    serialized_packet = _canonical_bytes(packet).decode("utf-8")
    assert '"approved"' not in serialized_packet
    assert '"reference_prose"' not in serialized_packet
    assert '"reference_key_points"' not in serialized_packet
    assert '"reviewer_kind":"agent"' not in serialized_packet
    assert '"reviewer_kind":"model"' not in serialized_packet
    assert "recorded-fake-judge" not in serialized_packet

    output_path = tmp_path / "human-review-packet-v1.json"
    written = module.build_review_packet(MANIFEST_PATH, output_path=output_path)
    assert written == packet
    expected_bytes = (
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert output_path.read_bytes() == expected_bytes
    assert PACKET_PATH.read_bytes() == expected_bytes
    assert (
        module.build_review_packet(
            MANIFEST_PATH,
            output_path=PACKET_PATH,
            check=True,
        )
        == packet
    )

    tampered_manifest = tmp_path / "tampered-manifest.json"
    tampered_manifest.write_bytes(MANIFEST_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest|identity|deterministic"):
        module.build_review_packet(tampered_manifest)
