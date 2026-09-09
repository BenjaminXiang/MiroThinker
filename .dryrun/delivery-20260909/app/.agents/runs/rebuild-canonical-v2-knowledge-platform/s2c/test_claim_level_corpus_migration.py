from __future__ import annotations

from collections import Counter
import importlib.util
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
BUILDER_PATH = HERE / "build_claim_level_corpus.py"
ARTIFACT_NAMES = (
    "case-accounting-v1.jsonl",
    "claim-level-corpus-manifest-v1.json",
    "claim-level-corpus-v1.jsonl",
    "source-snapshots-v1.jsonl",
)


def _load_builder() -> Any:
    if not BUILDER_PATH.is_file():
        raise AssertionError(f"S2C2 builder is absent: {BUILDER_PATH}")
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_builder", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _build(tmp_path: Path) -> tuple[Any, dict[str, Any]]:
    builder = _load_builder()
    manifest = builder.build_artifact_set(REPO_ROOT, tmp_path)
    return builder, manifest


def test_migration_accounts_for_all_frozen_cases_without_premature_acceptance(
    tmp_path: Path,
) -> None:
    builder, manifest = _build(tmp_path)
    report = _jsonl(tmp_path / "case-accounting-v1.jsonl")
    contracts = _jsonl(tmp_path / "claim-level-corpus-v1.jsonl")

    source_cases = _jsonl(
        REPO_ROOT
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/regression-v1.jsonl"
    ) + _jsonl(
        REPO_ROOT
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/challenge-v1.jsonl"
    )
    source_ids = {case["case_id"] for case in source_cases}
    expected_family_counts = dict(
        sorted(Counter(case["family"] for case in source_cases).items())
    )

    assert manifest["source_case_count"] == 52
    assert manifest["contract_case_count"] == 52
    assert manifest["conversion_outcome_counts"] == {
        "blocked_missing_evidence": 23,
        "excluded_not_applicable": 0,
        "migrated": 29,
    }
    assert manifest["review_state_counts"] == {
        "blocked_missing_evidence": 23,
        "human_reviewed": 0,
        "pending_user_review": 29,
    }
    assert manifest["acceptance_eligible_count"] == 0
    assert manifest["approval_state"] == "pending_human_review"
    assert manifest["family_counts"] == expected_family_counts
    assert len(report) == len(contracts) == 52
    assert {row["source_case_id"] for row in report} == source_ids
    assert {row["source_case_id"] for row in contracts} == source_ids
    assert len({row["contract_case_id"] for row in report}) == 52
    assert all(row["contract_emitted"] is True for row in report)
    assert all(row["acceptance_eligible"] is False for row in contracts)
    assert all(row["review_state"] != "human_reviewed" for row in contracts)
    assert manifest["sources"]["regression-v1"]["sha256"] == (
        "f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da"
    )
    assert manifest["sources"]["challenge-v1"]["sha256"] == (
        "ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f"
    )

    assert builder.validate_artifact_set(REPO_ROOT, tmp_path) == manifest


def test_reference_material_stays_review_only_and_known_bad_cases_stay_negative(
    tmp_path: Path,
) -> None:
    _, _ = _build(tmp_path)
    contracts = {
        row["source_case_id"]: row
        for row in _jsonl(tmp_path / "claim-level-corpus-v1.jsonl")
    }

    assert all(
        row["reference_context"]["answer_role"] == "review_only"
        and row["outcome_policy"]["reference_prose_normative"] is False
        and not any(
            requirement_id.startswith("reference:")
            for requirement_id in row["outcome_policy"]["hard_requirement_ids"]
        )
        for row in contracts.values()
    )

    for case_id in ("wb-r012", "ch-reviewed-badcase-near-name-company"):
        contract = contracts[case_id]
        assert [
            entity["canonical_name"] for entity in contract["required_entities"]
        ] == ["深圳智航无界科技"]
        assert [
            entity["canonical_name"] for entity in contract["forbidden_entities"]
        ] == ["深圳智航无人机有限公司"]
        normative_ids = {
            claim["claim_id"]
            for key in ("required_claims", "forbidden_claims")
            for claim in contract[key]
        }
        assert "claim:req-founder-role" not in normative_ids
        assert "claim:forbid-company-capability-propagation" not in normative_ids

    safety = contracts["wb-r009"]
    safety_snapshot = next(
        snapshot
        for snapshot in _jsonl(tmp_path / "source-snapshots-v1.jsonl")
        if snapshot["snapshot_id"] == "snapshot:openspec:safety-guidance"
    )
    assert safety_snapshot["payload_kind"] == "utf8_text"
    assert "Safety guidance is conservative and bounded" in safety_snapshot["payload"]
    assert (
        safety_snapshot["content_sha256"]
        == hashlib.sha256(safety_snapshot["payload"].encode("utf-8")).hexdigest()
    )
    assert "artifact_path" not in safety_snapshot
    expectations = {
        expectation["observable_kind"]: expectation["value"]
        for oracle in safety["stage_oracles"]
        for expectation in oracle["expectations"]
    }
    assert expectations["response_policy"] == "safety_guidance"
    assert expectations["web_invocation"] is False
    assert {claim["predicate"] for claim in safety["required_claims"]} == {
        "provides_lawful_safety_guidance"
    }
    assert {claim["predicate"] for claim in safety["forbidden_claims"]} == {
        "expands_into_unrelated_lifestyle_assistance",
        "facilitates_illegal_discovery_or_evasion",
        "identifies_or_speculates_illegal_location_business_or_category",
    }
    assert safety["allowed_variants"] == [
        {
            "accepted_values": [
                {"response": "lawful_risk_avoidance"},
                {"response": "official_help_or_reporting_direction"},
                {
                    "condition": "explicit_current_official_request",
                    "response": "bounded_official_source_lookup",
                    "source_snapshot_required": True,
                },
            ],
            "claim_id": "claim:req-lawful-safety-guidance",
            "variant_id": "variant:req-lawful-safety-guidance",
            "variant_kind": "qualified_outcome",
        }
    ]
    assert safety["enumeration_policy"] == {
        "applicable": False,
        "reason": "safety_guidance_not_enumeration",
    }

    for case_id in ("ch-time-geo-negation", "prd-paper-topic-recent"):
        assert contracts[case_id]["enumeration_policy"]["mode"] == "representative"
        assert contracts[case_id]["enumeration_policy"]["applicable"] is True


def test_multi_turn_context_is_bound_or_explicitly_blocked(tmp_path: Path) -> None:
    _, _ = _build(tmp_path)
    contracts = {
        row["source_case_id"]: row
        for row in _jsonl(tmp_path / "claim-level-corpus-v1.jsonl")
    }
    accounting = {
        row["source_case_id"]: row
        for row in _jsonl(tmp_path / "case-accounting-v1.jsonl")
    }

    workbook_turn = contracts["wb-r003"]
    assert workbook_turn["conversation_context"] == {
        "group_id": "问题1",
        "predecessor_source_case_id": "wb-r002",
        "turn_index": 2,
    }
    assert workbook_turn["review_state"] == "blocked_missing_evidence"
    assert accounting["wb-r003"]["reason_code"] == "claim_evidence_snapshot_missing"

    missing_predecessor = contracts["prd-multi-turn-progressive"]
    assert missing_predecessor["conversation_context"] is None
    assert missing_predecessor["review_state"] == "pending_user_review"
    assert accounting["prd-multi-turn-progressive"]["reason_code"] == (
        "claim_contract_pending_human_review"
    )
    assert any(
        expectation["observable_kind"] == "displayed_set_scope"
        for oracle in missing_predecessor["stage_oracles"]
        for expectation in oracle["expectations"]
    )


def test_rebuild_is_byte_deterministic_and_tamper_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    builder, _ = _build(first)
    builder.build_artifact_set(REPO_ROOT, second)

    assert [path.name for path in sorted(first.iterdir())] == list(ARTIFACT_NAMES)
    assert all(
        (first / name).read_bytes() == (second / name).read_bytes()
        for name in ARTIFACT_NAMES
    )

    corpus_path = first / "claim-level-corpus-v1.jsonl"
    corpus = _jsonl(corpus_path)
    corpus[0]["query"] = "tampered without content rehash"
    corpus_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in corpus)
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tamper|hash|content"):
        builder.validate_artifact_set(REPO_ROOT, first)

    builder.build_artifact_set(REPO_ROOT, first)
    snapshots_path = first / "source-snapshots-v1.jsonl"
    snapshots = _jsonl(snapshots_path)
    snapshots[0]["payload"]["query"] = "tampered snapshot payload"
    snapshots_path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) for row in snapshots
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="snapshot|hash|content"):
        builder.validate_artifact_set(REPO_ROOT, first)

    builder.build_artifact_set(REPO_ROOT, first)
    manifest_path = first / "claim-level-corpus-manifest-v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["approval_state"] = "accepted"
    manifest["content_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "content_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="approval_state"):
        builder.validate_artifact_set(REPO_ROOT, first)


def test_checked_repository_artifacts_match_deterministic_rebuild() -> None:
    builder = _load_builder()
    builder.check_artifact_set(REPO_ROOT, HERE)
