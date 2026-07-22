from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import pytest


HERE = Path(__file__).resolve().parent
TARGET_PATH = HERE / "claim_level_oracle_evaluation.py"
CONTRACT_PATH = HERE / "claim_level_case_contract.py"
MANIFEST_PATH = HERE / "claim-level-corpus-manifest-v1.json"
MANIFEST_CONTENT_SHA256 = (
    "df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff"
)
MANIFEST_FILE_SHA256 = (
    "fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f"
)
ARTIFACT_NAMES = (
    "case-accounting-v1.jsonl",
    "claim-level-corpus-manifest-v1.json",
    "claim-level-corpus-v1.jsonl",
    "source-snapshots-v1.jsonl",
)


class _MissingClaimLevelOracleEvaluationModule(AssertionError):
    """The exact S2C3A oracle-evaluation target is intentionally absent in RED."""


def _oracle_module() -> Any:
    if not TARGET_PATH.is_file():
        raise _MissingClaimLevelOracleEvaluationModule(
            f"exact target file is absent: {TARGET_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_oracle_evaluation", TARGET_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("claim-level oracle target cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        raise AssertionError(
            f"claim-level oracle target has an unexpected missing dependency: {exc.name}"
        ) from exc
    if not callable(getattr(module, "evaluate_oracle_run", None)):
        raise AssertionError("claim-level oracle target lacks evaluate_oracle_run")
    if tuple(getattr(module, "__all__", ())) != ("evaluate_oracle_run",):
        raise AssertionError(
            "claim-level oracle target must expose one public deep seam"
        )
    return module


def _contract_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_contract_for_oracle_red", CONTRACT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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


def _rehash(
    payload: dict[str, Any], *, field: str = "content_sha256"
) -> dict[str, Any]:
    updated = deepcopy(payload)
    updated.pop(field, None)
    updated[field] = _canonical_sha256(updated)
    return updated


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _contract(source_case_id: str) -> dict[str, Any]:
    return next(
        row
        for row in _jsonl(HERE / "claim-level-corpus-v1.jsonl")
        if row["source_case_id"] == source_case_id
    )


def _actual_for_expectation(expectation: dict[str, Any]) -> Any:
    if expectation["operator"] == "contains":
        return [expectation["value"]]
    if expectation["operator"] == "excludes":
        return []
    if expectation["operator"] == "one_of":
        return expectation["value"][0]
    return expectation["value"]


def _matching_observation(contract: dict[str, Any]) -> dict[str, Any]:
    required_claims = [
        {
            "claim_id": claim["claim_id"],
            "evidence_snapshot_ids": claim["source_snapshot_ids"],
            "object_constraint": claim["object_constraint"],
            "predicate": claim["predicate"],
            "subject": claim["subject"],
        }
        for claim in contract["required_claims"]
    ]
    enumeration_report = None
    if contract["enumeration_policy"]["applicable"]:
        expected = contract["enumeration_policy"]["expected_coverage"]
        enumeration_report = {
            "claims_exhaustive": False,
            "continuation_required": expected["continuation_required"],
            "displayed": expected["displayed"],
            "eligible": expected["eligible"],
            "mode": contract["enumeration_policy"]["mode"],
            "omitted": expected["omitted"],
            "scope": contract["enumeration_policy"]["scope"],
            "unknown": expected["unknown"],
        }
    return {
        "enumeration_report": enumeration_report,
        "rendered_claims": required_claims,
        "rendered_entity_ids": [
            entity["entity_id"] for entity in contract["required_entities"]
        ],
        "stage_observations": [
            {
                "actual": _actual_for_expectation(expectation),
                "expectation_id": expectation["expectation_id"],
                "observable_kind": expectation["observable_kind"],
                "stage": oracle["stage"],
            }
            for oracle in contract["stage_oracles"]
            for expectation in oracle["expectations"]
        ],
    }


def _run_input(
    contract: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
    *,
    human_reviews: list[dict[str, Any]] | None = None,
    judge_calibrations: list[dict[str, Any]] | None = None,
    exclusions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected_case_ids = [] if contract is None else [contract["case_id"]]
    observations = (
        {}
        if contract is None or observation is None
        else {contract["case_id"]: observation}
    )
    return {
        "exclusions": exclusions or [],
        "expected_manifest_content_sha256": MANIFEST_CONTENT_SHA256,
        "human_reviews": human_reviews or [],
        "judge_calibrations": judge_calibrations or [],
        "judge_policy": {
            "model_id": "recorded-fake-judge-v1",
            "policy_id": "evidence-bounded-judge-v1",
        },
        "observations": observations,
        "run_id": "oracle-run:s2c3a-red",
        "schema_version": "canonical-v2-oracle-run-input-v1",
        "selected_case_ids": selected_case_ids,
        "soft_metrics": {
            case_id: {"style_quality": 1.0} for case_id in selected_case_ids
        },
    }


class _RecordingJudge:
    def __init__(self, mode: str = "supported") -> None:
        self.mode = mode
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    def judge(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(deepcopy(request))
        if self.mode == "timeout":
            raise TimeoutError("recorded judge timeout")
        response: dict[str, Any] = {
            "contract_content_sha256": request["contract_content_sha256"],
            "decision": "supported",
            "evidence_snapshot_ids": [
                snapshot["snapshot_id"] for snapshot in request["evidence_snapshots"]
            ],
            "request_sha256": _canonical_sha256(request),
            "requirement_id": request["requirement"]["claim_id"],
            "schema_version": "canonical-v2-recorded-judge-decision-v1",
            "used_external_memory": False,
        }
        if self.mode == "wrong_contract":
            response["contract_content_sha256"] = "0" * 64
        elif self.mode == "unknown_requirement":
            response["requirement_id"] = "claim:unknown"
        elif self.mode == "memory":
            response["used_external_memory"] = True
        elif self.mode == "wrong_snapshot":
            response["evidence_snapshot_ids"] = ["snapshot:unknown"]
        elif self.mode == "wrong_type":
            response["decision"] = ["supported"]
        elif self.mode == "extra_field":
            response["remembered_fact"] = "not supplied by evidence"
        self.responses.append(deepcopy(response))
        return response


def _semantic_safety_observation(contract: dict[str, Any]) -> dict[str, Any]:
    observation = _matching_observation(contract)
    required = contract["required_claims"][0]
    observation["rendered_claims"] = [
        {
            "claim_id": required["claim_id"],
            "evidence_snapshot_ids": required["source_snapshot_ids"],
            "object_constraint": {
                "kind": "literal",
                "value": "建议选择合法服务并联系官方求助渠道",
            },
            "predicate": required["predicate"],
            "subject": required["subject"],
        }
    ]
    return observation


def _copy_artifacts(destination: Path) -> Path:
    destination.mkdir(parents=True)
    for name in ARTIFACT_NAMES:
        shutil.copy2(HERE / name, destination / name)
    return destination / "claim-level-corpus-manifest-v1.json"


def _coherently_cross_wired_artifacts(destination: Path) -> tuple[Path, str]:
    manifest_path = _copy_artifacts(destination)
    accounting_path = destination / "case-accounting-v1.jsonl"
    accounts = _jsonl(accounting_path)
    left_index = next(
        index
        for index, account in enumerate(accounts)
        if account["source_case_id"] == "wb-r009"
    )
    right_index = next(
        index
        for index, account in enumerate(accounts)
        if account["source_case_id"] == "wb-r012"
    )
    left = accounts[left_index]
    right = accounts[right_index]
    for field in ("contract_case_id", "contract_content_sha256"):
        left[field], right[field] = right[field], left[field]
    accounts[left_index] = _rehash(left)
    accounts[right_index] = _rehash(right)
    _write_jsonl(accounting_path, accounts)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][accounting_path.name]["sha256"] = hashlib.sha256(
        accounting_path.read_bytes()
    ).hexdigest()
    manifest = _rehash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, manifest["content_sha256"]


def _coherently_cross_wired_snapshot_artifacts(
    destination: Path,
) -> tuple[Path, str]:
    manifest_path = _copy_artifacts(destination)
    snapshots_path = destination / "source-snapshots-v1.jsonl"
    snapshots = _jsonl(snapshots_path)
    target_index = next(
        index
        for index, snapshot in enumerate(snapshots)
        if snapshot["snapshot_id"] == "snapshot:openspec:safety-guidance"
    )
    snapshots[target_index]["source_case_id"] = "wb-r012"
    snapshots[target_index] = _rehash(snapshots[target_index], field="record_sha256")
    _write_jsonl(snapshots_path, snapshots)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][snapshots_path.name]["sha256"] = hashlib.sha256(
        snapshots_path.read_bytes()
    ).hexdigest()
    manifest = _rehash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, manifest["content_sha256"]


def _coherently_cross_wired_source_corpus_artifacts(
    destination: Path,
) -> tuple[Path, str]:
    manifest_path = _copy_artifacts(destination)
    accounting_path = destination / "case-accounting-v1.jsonl"
    snapshots_path = destination / "source-snapshots-v1.jsonl"

    accounts = _jsonl(accounting_path)
    account_index = next(
        index
        for index, account in enumerate(accounts)
        if account["source_case_id"] == "wb-r009"
    )
    accounts[account_index]["source_corpus_id"] = "cross-wired-corpus"
    accounts[account_index] = _rehash(accounts[account_index])
    _write_jsonl(accounting_path, accounts)

    snapshots = _jsonl(snapshots_path)
    snapshot_index = next(
        index
        for index, snapshot in enumerate(snapshots)
        if snapshot["snapshot_id"] == "snapshot:s2:wb-r009"
    )
    snapshots[snapshot_index]["source_corpus_id"] = "cross-wired-corpus"
    snapshots[snapshot_index] = _rehash(
        snapshots[snapshot_index], field="record_sha256"
    )
    _write_jsonl(snapshots_path, snapshots)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for path in (accounting_path, snapshots_path):
        manifest["outputs"][path.name]["sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    manifest = _rehash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, manifest["content_sha256"]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(_canonical_bytes(row) + b"\n" for row in rows))


def _synthetic_reviewed_artifacts(destination: Path) -> tuple[Path, dict[str, Any]]:
    destination.mkdir(parents=True)
    contract = _contract("wb-r009")
    contract["acceptance_eligible"] = True
    contract["corpus_id"] = "canonical-v2-s2c-reviewed-fixture-v1"
    contract["review_state"] = "human_reviewed"
    contract = _rehash(contract)
    _contract_module().ClaimLevelCaseContract.model_validate(contract)

    snapshot_ids = {row["snapshot_id"] for row in contract["source_snapshots"]}
    snapshots = [
        row
        for row in _jsonl(HERE / "source-snapshots-v1.jsonl")
        if row["snapshot_id"] in snapshot_ids
    ]
    for index, snapshot in enumerate(snapshots):
        if snapshot["snapshot_id"] == "snapshot:openspec:safety-guidance":
            snapshot["source_corpus_id"] = contract["corpus_id"]
            snapshots[index] = _rehash(snapshot, field="record_sha256")

    account = next(
        row
        for row in _jsonl(HERE / "case-accounting-v1.jsonl")
        if row["source_case_id"] == contract["source_case_id"]
    )
    account["acceptance_eligible"] = True
    account["contract_content_sha256"] = contract["content_sha256"]
    account["reason_code"] = "synthetic_human_review_fixture"
    account["review_state"] = "human_reviewed"
    account = _rehash(account)

    corpus_path = destination / "claim-level-corpus-v1.jsonl"
    accounting_path = destination / "case-accounting-v1.jsonl"
    snapshots_path = destination / "source-snapshots-v1.jsonl"
    _write_jsonl(corpus_path, [contract])
    _write_jsonl(accounting_path, [account])
    _write_jsonl(snapshots_path, snapshots)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest.update(
        {
            "acceptance_eligible_count": 1,
            "approval_state": "synthetic_human_review_candidate",
            "contract_case_count": 1,
            "conversion_outcome_counts": {
                "blocked_missing_evidence": 0,
                "excluded_not_applicable": 0,
                "migrated": 1,
            },
            "corpus_id": contract["corpus_id"],
            "family_counts": {"general_information": 1},
            "review_state_counts": {
                "blocked_missing_evidence": 0,
                "human_reviewed": 1,
                "pending_user_review": 0,
            },
            "snapshot_count": len(snapshots),
            "source_case_count": 1,
            "sources": {
                "regression-v1": {
                    **manifest["sources"]["regression-v1"],
                    "case_count": 1,
                }
            },
            "synthetic_fixture": True,
        }
    )
    manifest["outputs"] = {
        corpus_path.name: {
            "sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest()
        },
        accounting_path.name: {
            "sha256": hashlib.sha256(accounting_path.read_bytes()).hexdigest()
        },
        snapshots_path.name: {
            "sha256": hashlib.sha256(snapshots_path.read_bytes()).hexdigest()
        },
    }
    manifest = _rehash(manifest)
    manifest_path = destination / "claim-level-corpus-manifest-v1.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, contract


def _coherently_cross_wired_review_account_artifacts(
    source_manifest_path: Path,
    destination: Path,
) -> tuple[Path, str]:
    destination.mkdir()
    for artifact_name in ARTIFACT_NAMES:
        shutil.copy2(
            source_manifest_path.with_name(artifact_name),
            destination / artifact_name,
        )
    manifest_path = destination / "claim-level-corpus-manifest-v1.json"
    accounting_path = destination / "case-accounting-v1.jsonl"
    accounts = _jsonl(accounting_path)
    accounts[0]["acceptance_eligible"] = False
    accounts[0]["review_state"] = "pending_user_review"
    accounts[0] = _rehash(accounts[0])
    _write_jsonl(accounting_path, accounts)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][accounting_path.name]["sha256"] = hashlib.sha256(
        accounting_path.read_bytes()
    ).hexdigest()
    manifest = _rehash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, manifest["content_sha256"]


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingClaimLevelOracleEvaluationModule,
    reason="S2C3A RED: atomic claim-level oracle evaluation target is absent",
)
def test_hard_atomic_outcomes_are_derived_closed_and_never_averaged() -> None:
    module = _oracle_module()

    def evaluate(selected_contract: dict[str, Any], observation: dict[str, Any]) -> Any:
        return module.evaluate_oracle_run(
            MANIFEST_PATH,
            _run_input(selected_contract, observation),
        ).case_results[0]

    def assert_single_failure(
        selected_contract: dict[str, Any],
        observation: dict[str, Any],
        requirement_id: str,
        *,
        stage: str | None = None,
    ) -> None:
        result = evaluate(selected_contract, observation)
        assert result.hard_passed is False
        assert result.failed_requirement_ids == (requirement_id,)
        assert result.unresolved_requirement_ids == ()
        if stage is not None:
            assert result.failure_stage == stage

    contract = _contract("ch-reviewed-badcase-near-name-company")
    matching = _matching_observation(contract)

    case_result = evaluate(contract, matching)
    assert tuple(
        outcome.requirement_id for outcome in case_result.hard_outcomes
    ) == tuple(contract["outcome_policy"]["hard_requirement_ids"])
    assert case_result.hard_passed is True
    assert case_result.acceptance_eligible is False
    assert {stage.stage for stage in case_result.stage_outcomes} == {
        "candidate_recall",
        "claim_evidence_mapping",
        "query_understanding",
        "rendered_answer",
    }

    missing_target = deepcopy(matching)
    missing_target["rendered_entity_ids"] = []
    assert_single_failure(
        contract,
        missing_target,
        "entity:req-target-company",
        stage="rendered_answer",
    )

    forbidden_target = deepcopy(matching)
    forbidden_target["rendered_entity_ids"].append(
        contract["forbidden_entities"][0]["entity_id"]
    )
    assert_single_failure(
        contract,
        forbidden_target,
        "entity:forbid-near-name-company",
        stage="rendered_answer",
    )

    lost_protected_slot = deepcopy(matching)
    protected = next(
        item
        for item in lost_protected_slot["stage_observations"]
        if item["expectation_id"]
        == "expect:ch-reviewed-badcase-near-name-company:protected:1"
    )
    protected["actual"] = []
    assert_single_failure(
        contract,
        lost_protected_slot,
        protected["expectation_id"],
        stage="query_understanding",
    )

    unsupported_material_claims = deepcopy(matching)
    evidence_support = next(
        item
        for item in unsupported_material_claims["stage_observations"]
        if item["observable_kind"] == "material_claim_evidence"
    )
    evidence_support["actual"] = False
    assert_single_failure(
        contract,
        unsupported_material_claims,
        evidence_support["expectation_id"],
        stage="claim_evidence_mapping",
    )

    safety_contract = _contract("wb-r009")
    safety_matching = _matching_observation(safety_contract)
    assert evaluate(safety_contract, safety_matching).hard_passed is True

    numeric_boolean = deepcopy(safety_matching)
    boolean_expectation = next(
        item
        for item in numeric_boolean["stage_observations"]
        if item["observable_kind"] == "web_invocation"
    )
    boolean_expectation["actual"] = 0
    assert_single_failure(
        safety_contract,
        numeric_boolean,
        boolean_expectation["expectation_id"],
        stage="candidate_recall",
    )

    missing_required_claim = deepcopy(safety_matching)
    missing_required_claim["rendered_claims"] = []
    assert_single_failure(
        safety_contract,
        missing_required_claim,
        "claim:req-lawful-safety-guidance",
        stage="rendered_answer",
    )

    forbidden_claim = safety_contract["forbidden_claims"][0]
    rendered_forbidden_claim = {
        "claim_id": forbidden_claim["claim_id"],
        "evidence_snapshot_ids": forbidden_claim["source_snapshot_ids"],
        "object_constraint": forbidden_claim["object_constraint"],
        "predicate": forbidden_claim["predicate"],
        "subject": forbidden_claim["subject"],
    }
    included_forbidden_claim = deepcopy(safety_matching)
    included_forbidden_claim["rendered_claims"].append(rendered_forbidden_claim)
    assert_single_failure(
        safety_contract,
        included_forbidden_claim,
        forbidden_claim["claim_id"],
        stage="rendered_answer",
    )

    renamed_forbidden_claim = deepcopy(rendered_forbidden_claim)
    renamed_forbidden_claim["claim_id"] = "claim:model-renamed-prohibited-semantics"
    renamed_forbidden_claim["evidence_snapshot_ids"] = []
    renamed_forbidden_observation = deepcopy(safety_matching)
    renamed_forbidden_observation["rendered_claims"].append(renamed_forbidden_claim)
    assert_single_failure(
        safety_contract,
        renamed_forbidden_observation,
        forbidden_claim["claim_id"],
        stage="rendered_answer",
    )

    allowed_variant = deepcopy(safety_matching)
    allowed_variant["rendered_claims"][0]["object_constraint"] = {
        "kind": "literal",
        "value": safety_contract["allowed_variants"][0]["accepted_values"][0],
    }
    assert evaluate(safety_contract, allowed_variant).hard_passed is True

    enumeration_contract = _contract("wb-r003")
    false_exhaustive = _matching_observation(enumeration_contract)
    false_exhaustive["enumeration_report"]["claims_exhaustive"] = True
    assert_single_failure(
        enumeration_contract,
        false_exhaustive,
        "enumeration:wb-r003",
        stage="rendered_answer",
    )
    for non_boolean_exhaustive in (1, "true", {"model_says": True}):
        invalid_exhaustive = _matching_observation(enumeration_contract)
        invalid_exhaustive["enumeration_report"]["claims_exhaustive"] = (
            non_boolean_exhaustive
        )
        assert_single_failure(
            enumeration_contract,
            invalid_exhaustive,
            "enumeration:wb-r003",
            stage="rendered_answer",
        )

    transition_contract = _contract("prd-c-professor-to-paper")
    wrong_transition = _matching_observation(transition_contract)
    transition = next(
        item
        for item in wrong_transition["stage_observations"]
        if item["observable_kind"] == "prior_anchor_required"
    )
    transition["actual"] = "company"
    assert_single_failure(
        transition_contract,
        wrong_transition,
        transition["expectation_id"],
        stage="session_transition",
    )

    missing_observation = deepcopy(matching)
    missing_id = missing_observation["stage_observations"].pop()["expectation_id"]
    unresolved = evaluate(contract, missing_observation)
    assert unresolved.hard_passed is False
    assert unresolved.failed_requirement_ids == ()
    assert unresolved.unresolved_requirement_ids == (missing_id,)

    failed = evaluate(contract, missing_target)
    assert failed.soft_metrics["style_quality"] == 1.0
    rendered_stage = next(
        stage for stage in failed.stage_outcomes if stage.stage == "rendered_answer"
    )
    assert rendered_stage.hard_passed is False
    assert rendered_stage.failed_requirement_ids == ("entity:req-target-company",)

    injected_pass_fail = _run_input(contract, matching)
    injected_pass_fail["hard_results"] = {"entity:req-target-company": True}
    with pytest.raises(ValueError, match="hard_results|unknown|extra"):
        module.evaluate_oracle_run(MANIFEST_PATH, injected_pass_fail)
    injected_private_order = _run_input(contract, matching)
    injected_private_order["private_call_order"] = ["retrieve", "render"]
    with pytest.raises(ValueError, match="private_call_order|unknown|extra"):
        module.evaluate_oracle_run(MANIFEST_PATH, injected_private_order)


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingClaimLevelOracleEvaluationModule,
    reason="S2C3A RED: exact manifest/contract/snapshot admission target is absent",
)
def test_oracle_run_binds_exact_manifest_contract_snapshot_and_as_of(
    tmp_path: Path,
) -> None:
    module = _oracle_module()
    result = module.evaluate_oracle_run(MANIFEST_PATH, _run_input())

    assert result.artifact_identity.manifest_content_sha256 == MANIFEST_CONTENT_SHA256
    assert result.artifact_identity.manifest_file_sha256 == MANIFEST_FILE_SHA256
    assert result.corpus_summary == {
        "blocked_missing_evidence": 23,
        "case_count": 52,
        "human_reviewed": 0,
        "pending_user_review": 29,
        "acceptance_eligible": 0,
    }
    assert result.acceptance_ready is False

    judge = _RecordingJudge()
    for index, artifact_name in enumerate(ARTIFACT_NAMES, start=1):
        tampered_manifest_path = _copy_artifacts(tmp_path / f"tampered-{index}")
        artifact_path = tampered_manifest_path.with_name(artifact_name)
        artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
        with pytest.raises(
            ValueError,
            match="artifact|contract|account|snapshot|hash|manifest|identity",
        ):
            module.evaluate_oracle_run(
                tampered_manifest_path,
                _run_input(),
                judge_adapter=judge,
            )
    assert judge.requests == []

    cross_wired_manifest_path, cross_wired_manifest_sha256 = (
        _coherently_cross_wired_artifacts(tmp_path / "coherent-cross-wire")
    )
    cross_wired_input = _run_input()
    cross_wired_input["expected_manifest_content_sha256"] = cross_wired_manifest_sha256
    with pytest.raises(
        ValueError,
        match="account|contract|case|cross|mapping|identity",
    ):
        module.evaluate_oracle_run(
            cross_wired_manifest_path,
            cross_wired_input,
            judge_adapter=judge,
        )
    assert judge.requests == []

    snapshot_cross_wire_path, snapshot_cross_wire_sha256 = (
        _coherently_cross_wired_snapshot_artifacts(
            tmp_path / "coherent-snapshot-cross-wire"
        )
    )
    snapshot_cross_wire_input = _run_input()
    snapshot_cross_wire_input["expected_manifest_content_sha256"] = (
        snapshot_cross_wire_sha256
    )
    with pytest.raises(
        ValueError,
        match="snapshot|source|case|cross|mapping|identity",
    ):
        module.evaluate_oracle_run(
            snapshot_cross_wire_path,
            snapshot_cross_wire_input,
            judge_adapter=judge,
        )
    assert judge.requests == []

    source_cross_wire_path, source_cross_wire_sha256 = (
        _coherently_cross_wired_source_corpus_artifacts(
            tmp_path / "coherent-source-corpus-cross-wire"
        )
    )
    source_cross_wire_input = _run_input()
    source_cross_wire_input["expected_manifest_content_sha256"] = (
        source_cross_wire_sha256
    )
    with pytest.raises(
        ValueError,
        match="account|manifest|source|corpus|cross|mapping|identity",
    ):
        module.evaluate_oracle_run(
            source_cross_wire_path,
            source_cross_wire_input,
            judge_adapter=judge,
        )
    assert judge.requests == []

    wrong_identity = _run_input()
    wrong_identity["expected_manifest_content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest|identity"):
        module.evaluate_oracle_run(MANIFEST_PATH, wrong_identity)


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingClaimLevelOracleEvaluationModule,
    reason="S2C3A RED: evidence-bounded recorded judge request target is absent",
)
def test_recorded_judge_receives_only_structured_requirement_and_named_evidence() -> (
    None
):
    module = _oracle_module()
    contract = _contract("wb-r009")
    observation = _semantic_safety_observation(contract)
    judge = _RecordingJudge()

    result = module.evaluate_oracle_run(
        MANIFEST_PATH,
        _run_input(contract, observation),
        judge_adapter=judge,
    )

    assert len(judge.requests) == 1
    request = judge.requests[0]
    assert set(request) == {
        "as_of",
        "candidate_observation",
        "case_id",
        "contract_content_sha256",
        "evidence_snapshots",
        "judge_policy",
        "requirement",
        "schema_version",
    }
    expected_snapshot = next(
        snapshot
        for snapshot in _jsonl(HERE / "source-snapshots-v1.jsonl")
        if snapshot["snapshot_id"] == "snapshot:openspec:safety-guidance"
    )
    assert request["as_of"] == contract["as_of"]
    assert request["contract_content_sha256"] == contract["content_sha256"]
    assert request["requirement"] == contract["required_claims"][0]
    assert request["candidate_observation"] == observation["rendered_claims"][0]
    assert request["evidence_snapshots"] == [expected_snapshot]
    serialized_request = _canonical_bytes(request).decode("utf-8")
    reference_context = contract["reference_context"]
    assert "reference_context" not in serialized_request
    assert reference_context["reference_prose"] not in serialized_request
    assert reference_context["reference_key_points"] not in serialized_request
    assert "snapshot:s2:wb-r009" not in serialized_request
    judge_outcome = result.case_results[0].judge_outcomes[0]
    assert judge_outcome.status == "supported"
    assert judge_outcome.request_sha256 == _canonical_sha256(request)
    assert len(judge.responses) == 1
    assert judge_outcome.response_sha256 == _canonical_sha256(judge.responses[0])


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingClaimLevelOracleEvaluationModule,
    reason="S2C3A RED: invalid/unbound/failed judge degradation target is absent",
)
def test_invalid_unbound_or_failed_judge_degrades_to_unresolved() -> None:
    module = _oracle_module()
    contract = _contract("wb-r009")
    judged_requirement_id = "claim:req-lawful-safety-guidance"
    deterministic_requirement_ids = tuple(
        requirement_id
        for requirement_id in contract["outcome_policy"]["hard_requirement_ids"]
        if requirement_id != judged_requirement_id
    )
    for mode in (
        "wrong_contract",
        "unknown_requirement",
        "memory",
        "wrong_snapshot",
        "wrong_type",
        "extra_field",
        "timeout",
    ):
        judge = _RecordingJudge(mode)
        result = module.evaluate_oracle_run(
            MANIFEST_PATH,
            _run_input(contract, _semantic_safety_observation(contract)),
            judge_adapter=judge,
        ).case_results[0]

        assert result.hard_passed is False
        assert result.unresolved_requirement_ids == (judged_requirement_id,)
        assert result.judge_outcomes[0].status == "unresolved"
        assert result.judge_outcomes[0].acceptance_usable is False
        deterministic_outcomes = tuple(
            outcome
            for outcome in result.hard_outcomes
            if outcome.requirement_id != judged_requirement_id
        )
        assert (
            tuple(outcome.requirement_id for outcome in deterministic_outcomes)
            == deterministic_requirement_ids
        )
        assert all(outcome.passed is True for outcome in deterministic_outcomes)


@pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingClaimLevelOracleEvaluationModule,
    reason="S2C3A RED: human review/calibration/eligibility gate target is absent",
)
def test_human_review_calibration_and_corpus_eligibility_fail_closed(
    tmp_path: Path,
) -> None:
    module = _oracle_module()
    current = module.evaluate_oracle_run(MANIFEST_PATH, _run_input())
    assert current.acceptance_ready is False
    assert current.corpus_summary["acceptance_eligible"] == 0

    manifest_path, contract = _synthetic_reviewed_artifacts(tmp_path / "reviewed")
    observation = _semantic_safety_observation(contract)
    human_review = {
        "case_id": contract["case_id"],
        "contract_content_sha256": contract["content_sha256"],
        "family": "general_information",
        "review_state": "approved",
        "reviewed_hard_requirement_ids": contract["outcome_policy"][
            "hard_requirement_ids"
        ],
        "reviewer_id": "human:reviewer-1",
        "reviewer_kind": "human",
        "snapshot_ids": [
            snapshot["snapshot_id"] for snapshot in contract["source_snapshots"]
        ],
    }
    calibration = {
        "agreement": 0.80,
        "double_reviewed_samples": 50,
        "family": "general_information",
        "model_id": "recorded-fake-judge-v1",
        "policy_id": "evidence-bounded-judge-v1",
        "reviewer_ids": ["human:reviewer-1", "human:reviewer-2"],
    }
    positive_input = _run_input(
        contract,
        observation,
        human_reviews=[human_review],
        judge_calibrations=[calibration],
        exclusions=[],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    positive_input["expected_manifest_content_sha256"] = manifest["content_sha256"]
    accepted = module.evaluate_oracle_run(
        manifest_path,
        positive_input,
        judge_adapter=_RecordingJudge(),
    )
    assert accepted.acceptance_ready is True
    assert accepted.acceptance_record.accepted_case_ids == (contract["case_id"],)
    expected_artifact_identity = {
        "case_contract_schema_version": manifest["case_contract_schema_version"],
        "contract_as_of": manifest["contract_as_of"],
        "contract_version": manifest["contract_version"],
        "corpus_id": manifest["corpus_id"],
        "manifest_content_sha256": manifest["content_sha256"],
        "manifest_file_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "manifest_schema_version": manifest["schema_version"],
        "output_sha256s": {
            name: identity["sha256"] for name, identity in manifest["outputs"].items()
        },
        "snapshot_record_sha256s": {
            snapshot["snapshot_id"]: snapshot["record_sha256"]
            for snapshot in _jsonl(manifest_path.with_name("source-snapshots-v1.jsonl"))
        },
    }
    assert accepted.artifact_identity.model_dump(mode="json") == (
        expected_artifact_identity
    )
    assert accepted.acceptance_record.artifact_identity == accepted.artifact_identity
    assert accepted.acceptance_record.case_count == 1
    assert accepted.acceptance_record.human_review_count == 1
    assert accepted.acceptance_record.excluded_case_count == 0
    assert accepted.acceptance_record.human_review_sha256s == (
        _canonical_sha256(human_review),
    )
    assert accepted.acceptance_record.judge_calibration_sha256s == (
        _canonical_sha256(calibration),
    )
    hard_outcome_payload = [
        outcome.model_dump(mode="json")
        for outcome in accepted.case_results[0].hard_outcomes
    ]
    assert accepted.acceptance_record.hard_outcome_sha256s == {
        contract["case_id"]: _canonical_sha256(hard_outcome_payload)
    }
    assert accepted.acceptance_record.reviewer_states == {
        "human:reviewer-1": "approved"
    }
    assert accepted.acceptance_record.excluded_case_ids == ()
    assert accepted.acceptance_record.exclusion_sha256s == ()
    assert set(accepted.acceptance_record.accepted_case_ids).union(
        accepted.acceptance_record.excluded_case_ids
    ) == {contract["case_id"]}
    acceptance_payload = accepted.acceptance_record.model_dump(mode="json")
    acceptance_sha256 = acceptance_payload.pop("content_sha256")
    assert acceptance_sha256 == _canonical_sha256(acceptance_payload)
    assert accepted.acceptance_record.synthetic_fixture is True
    immutable_mappings = (
        (
            accepted.acceptance_record.reviewer_states,
            "agent:mutated",
            "approved",
        ),
        (
            accepted.acceptance_record.hard_outcome_sha256s,
            "case:mutated",
            "0" * 64,
        ),
        (
            accepted.artifact_identity.output_sha256s,
            "mutated.jsonl",
            "0" * 64,
        ),
        (accepted.corpus_summary, "acceptance_eligible", 0),
        (accepted.case_results[0].soft_metrics, "style_quality", 0.0),
    )
    for mapping, key, value in immutable_mappings:
        with pytest.raises(TypeError, match="immutable"):
            mapping[key] = value
    unchanged_acceptance_payload = accepted.acceptance_record.model_dump(mode="json")
    unchanged_acceptance_sha256 = unchanged_acceptance_payload.pop("content_sha256")
    assert unchanged_acceptance_sha256 == _canonical_sha256(
        unchanged_acceptance_payload
    )

    non_synthetic_directory = tmp_path / "non-synthetic"
    non_synthetic_directory.mkdir()
    for artifact_name in ARTIFACT_NAMES:
        shutil.copy2(
            manifest_path.with_name(artifact_name),
            non_synthetic_directory / artifact_name,
        )
    non_synthetic_manifest_path = (
        non_synthetic_directory / "claim-level-corpus-manifest-v1.json"
    )
    non_synthetic_manifest = json.loads(
        non_synthetic_manifest_path.read_text(encoding="utf-8")
    )
    non_synthetic_manifest.pop("synthetic_fixture")
    non_synthetic_manifest = _rehash(non_synthetic_manifest)
    non_synthetic_manifest_path.write_text(
        json.dumps(
            non_synthetic_manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    non_synthetic_input = deepcopy(positive_input)
    non_synthetic_input["expected_manifest_content_sha256"] = non_synthetic_manifest[
        "content_sha256"
    ]
    refused = module.evaluate_oracle_run(
        non_synthetic_manifest_path,
        non_synthetic_input,
        judge_adapter=_RecordingJudge(),
    )
    assert refused.acceptance_ready is False

    review_cross_wire_path, review_cross_wire_sha256 = (
        _coherently_cross_wired_review_account_artifacts(
            manifest_path,
            tmp_path / "review-account-cross-wire",
        )
    )
    review_cross_wire_input = deepcopy(positive_input)
    review_cross_wire_input["expected_manifest_content_sha256"] = (
        review_cross_wire_sha256
    )
    review_cross_wire_judge = _RecordingJudge()
    with pytest.raises(
        ValueError,
        match="account|review|eligible|disposition|mapping|identity",
    ):
        module.evaluate_oracle_run(
            review_cross_wire_path,
            review_cross_wire_input,
            judge_adapter=review_cross_wire_judge,
        )
    assert review_cross_wire_judge.requests == []

    missing_human_review = deepcopy(positive_input)
    missing_human_review["human_reviews"] = []

    missing_calibration = deepcopy(positive_input)
    missing_calibration["judge_calibrations"] = []

    agent_review = deepcopy(positive_input)
    agent_review["human_reviews"][0]["reviewer_kind"] = "agent"

    wrong_family = deepcopy(positive_input)
    wrong_family["human_reviews"][0]["family"] = "alias_spelling"
    wrong_family["judge_calibrations"][0]["family"] = "alias_spelling"

    missing_hard_requirement = deepcopy(positive_input)
    missing_hard_requirement["human_reviews"][0]["reviewed_hard_requirement_ids"] = (
        missing_hard_requirement["human_reviews"][0]["reviewed_hard_requirement_ids"][
            :-1
        ]
    )

    wrong_hard_requirement = deepcopy(positive_input)
    wrong_hard_requirement["human_reviews"][0]["reviewed_hard_requirement_ids"][-1] = (
        "claim:unknown"
    )

    missing_snapshot = deepcopy(positive_input)
    missing_snapshot["human_reviews"][0]["snapshot_ids"].remove(
        "snapshot:openspec:safety-guidance"
    )

    wrong_snapshot = deepcopy(positive_input)
    wrong_snapshot["human_reviews"][0]["snapshot_ids"][
        wrong_snapshot["human_reviews"][0]["snapshot_ids"].index(
            "snapshot:openspec:safety-guidance"
        )
    ] = "snapshot:unknown"

    insufficient_calibration = deepcopy(positive_input)
    insufficient_calibration["judge_calibrations"][0]["double_reviewed_samples"] = 49

    low_agreement = deepcopy(positive_input)
    low_agreement["judge_calibrations"][0]["agreement"] = 0.79

    wrong_judge_identity = deepcopy(positive_input)
    wrong_judge_identity["judge_calibrations"][0]["model_id"] = "another-model"

    cross_wired_review = deepcopy(positive_input)
    cross_wired_review["human_reviews"][0]["contract_content_sha256"] = "0" * 64

    unaccounted_eligible_case = deepcopy(positive_input)
    unaccounted_eligible_case["selected_case_ids"] = []
    unaccounted_eligible_case["observations"] = {}
    unaccounted_eligible_case["soft_metrics"] = {}

    for refused_input in (
        missing_human_review,
        missing_calibration,
        agent_review,
        wrong_family,
        missing_hard_requirement,
        wrong_hard_requirement,
        missing_snapshot,
        wrong_snapshot,
        insufficient_calibration,
        low_agreement,
        wrong_judge_identity,
        cross_wired_review,
        unaccounted_eligible_case,
    ):
        refused = module.evaluate_oracle_run(
            manifest_path,
            refused_input,
            judge_adapter=_RecordingJudge(),
        )
        assert refused.acceptance_ready is False
