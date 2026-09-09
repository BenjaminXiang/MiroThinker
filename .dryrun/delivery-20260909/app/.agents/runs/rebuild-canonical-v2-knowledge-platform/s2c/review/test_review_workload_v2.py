from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
TARGET_PATH = HERE / "build_review_workload_v2.py"
PACKET_PATH = HERE / "human-review-packet-v1.json"
POLICY_PATH = HERE / "calibration-policy-v2.json"
BANK_PATH = HERE / "calibration-observation-bank-v2.jsonl"
PROVENANCE_PATH = HERE / "calibration-observation-bank-v2-provenance.json"
WORKLOAD_PATH = HERE / "human-review-workload-v2.json"

PACKET_RAW_SHA256 = (
    "222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e"
)
PACKET_CONTENT_SHA256 = (
    "d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb"
)
STRATA = {
    "claim_evidence": 20,
    "identity_entity": 10,
    "context_relationship": 10,
    "safety_web": 10,
    "insufficiency_assessment": 10,
}
SOURCE_PATHS = (
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_grounding_contract.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_atomic_green_contract.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py",
    "apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py",
)
FORBIDDEN_LABEL_KEYS = {
    "expected_label",
    "gold_label",
    "ground_truth",
    "human_label",
    "judge_decision",
    "oracle_label",
}


class _MissingReviewWorkloadBuilder(AssertionError):
    """The workload builder is intentionally absent in RED."""


def _builder_module() -> Any:
    if not TARGET_PATH.is_file():
        raise _MissingReviewWorkloadBuilder(
            f"exact target file is absent: {TARGET_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_review_workload_v2", TARGET_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("review-workload target cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert tuple(getattr(module, "__all__", ())) == ("build_workload",)
    assert callable(getattr(module, "build_workload", None))
    return module


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


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_bank(path: Path = BANK_PATH) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _write_bank(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(_canonical_bytes(row) + b"\n" for row in rows))


def _rehash_request(row: dict[str, Any]) -> None:
    request = {key: value for key, value in row.items() if key != "request_sha256"}
    row["request_sha256"] = _canonical_sha256(request)


def _copy_sources(destination: Path) -> None:
    for relative in SOURCE_PATHS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)


def _build(
    module: Any,
    *,
    output_path: Path,
    packet_path: Path = PACKET_PATH,
    policy_path: Path = POLICY_PATH,
    bank_path: Path = BANK_PATH,
    provenance_path: Path = PROVENANCE_PATH,
    source_root: Path = REPO_ROOT,
    check: bool = False,
) -> dict[str, Any]:
    return module.build_workload(
        packet_path=packet_path,
        policy_path=policy_path,
        bank_path=bank_path,
        provenance_path=provenance_path,
        source_root=source_root,
        output_path=output_path,
        check=check,
    )


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def test_review_workload_v2_is_deterministic_complete_and_unlabeled(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _build(module, output_path=first_path)
    second = _build(module, output_path=second_path)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_path.read_bytes() == WORKLOAD_PATH.read_bytes()
    assert first == second
    assert set(first) == {
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
    }
    content_sha256 = first.pop("content_sha256")
    assert content_sha256 == _canonical_sha256(first)
    first["content_sha256"] = content_sha256
    assert first["schema_version"] == "canonical-v2-human-review-workload-v2"
    assert first["workload_id"] == "canonical-v2-s2c-single-human-review-v2"
    assert first["counts"] == {
        "calibration_probes": 60,
        "contract_reviews": 29,
        "exclusion_reviews": 23,
        "human_actions": 112,
    }
    assert len(first["contract_reviews"]) == 29
    assert len(first["exclusion_reviews"]) == 23
    assert first["packet_identity"] == {
        "content_sha256": PACKET_CONTENT_SHA256,
        "raw_sha256": PACKET_RAW_SHA256,
        "schema_version": "canonical-v2-human-review-packet-v1",
    }
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    assert first["contract_reviews"] == packet["review_candidates"]
    assert first["exclusion_reviews"] == packet["exclusion_candidates"]
    assert Counter(row["stratum"] for row in first["calibration_probes"]) == STRATA
    assert len({row["sample_id"] for row in first["calibration_probes"]}) == 60
    assert len({row["request_sha256"] for row in first["calibration_probes"]}) == 60
    assert not (_walk_keys(first) & FORBIDDEN_LABEL_KEYS)
    assert _build(module, output_path=WORKLOAD_PATH, check=True) == first


def test_policy_and_bank_identities_are_exact_and_content_addressed(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    workload = _build(module, output_path=tmp_path / "workload.json")
    exact_policy = {
        "maximum_critical_false_accepts": 0,
        "minimum_agreement": 0.8,
        "minimum_supported_labels": 10,
        "minimum_unsupported_critical_probes": 5,
        "minimum_unsupported_labels": 10,
        "policy_id": "single-human-global-stratified-v2",
        "reviewer_count": 1,
        "sample_count": 60,
        "schema_version": "canonical-v2-human-calibration-policy-v2",
        "strata": STRATA,
    }
    assert workload["policy"] == exact_policy
    assert workload["policy_identity"] == {
        "content_sha256": _canonical_sha256(exact_policy),
        "raw_sha256": _raw_sha256(POLICY_PATH),
    }
    bank = _read_bank()
    assert workload["bank_identity"] == {
        "content_sha256": _canonical_sha256(bank),
        "raw_sha256": _raw_sha256(BANK_PATH),
        "row_count": 60,
    }
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    provenance_content = provenance.pop("content_sha256")
    assert provenance_content == _canonical_sha256(provenance)
    assert workload["provenance_identity"] == {
        "content_sha256": provenance_content,
        "raw_sha256": _raw_sha256(PROVENANCE_PATH),
        "schema_version": "canonical-v2-calibration-provenance-v1",
    }


def test_provenance_anchor_rejects_tamper_and_matching_blueprint_bank_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _builder_module()
    tampered_provenance = tmp_path / "tampered-provenance.json"
    tampered_provenance.write_bytes(PROVENANCE_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="provenance"):
        _build(
            module,
            output_path=tmp_path / "tampered-provenance-workload.json",
            provenance_path=tampered_provenance,
        )

    rows = _read_bank()
    rows[0]["candidate_observation"]["value"] = "drifted-in-both-authorities"
    _rehash_request(rows[0])
    matching_drift_bank = tmp_path / "matching-drift.jsonl"
    _write_bank(matching_drift_bank, rows)
    monkeypatch.setattr(module, "_blueprints", lambda: copy.deepcopy(rows))
    with pytest.raises(ValueError, match="provenance.*projection|projection.*provenance"):
        _build(
            module,
            output_path=tmp_path / "matching-drift-workload.json",
            bank_path=matching_drift_bank,
        )


def test_cli_write_validation_failure_preserves_all_formal_outputs(
    tmp_path: Path,
) -> None:
    invalid_packet = tmp_path / "invalid-packet.json"
    invalid_packet.write_bytes(PACKET_PATH.read_bytes() + b" ")
    policy = tmp_path / "policy.json"
    bank = tmp_path / "bank.jsonl"
    workload = tmp_path / "workload.json"
    sentinels = {
        policy: b"sentinel-policy\n",
        bank: b"sentinel-bank\n",
        workload: b"sentinel-workload\n",
    }
    for path, payload in sentinels.items():
        path.write_bytes(payload)

    completed = subprocess.run(
        [
            sys.executable,
            str(TARGET_PATH),
            "--write",
            "--packet",
            str(invalid_packet),
            "--policy",
            str(policy),
            "--bank",
            str(bank),
            "--provenance",
            str(PROVENANCE_PATH),
            "--output",
            str(workload),
            "--source-root",
            str(REPO_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "review packet raw identity mismatch" in completed.stderr
    assert {path: path.read_bytes() for path in sentinels} == sentinels


def test_single_workload_write_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _builder_module()
    destination = tmp_path / "workload.json"
    destination.write_bytes(b"old-workload-commit-marker\n")

    def fail_replace(_: object, __: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        _build(module, output_path=destination)
    assert destination.read_bytes() == b"old-workload-commit-marker\n"
    assert not list(tmp_path.glob(".*.tmp"))


def _run_cli_write(
    *,
    packet: Path,
    policy: Path,
    bank: Path,
    provenance: Path,
    workload: Path,
    source_root: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TARGET_PATH),
            "--write",
            "--packet",
            str(packet),
            "--policy",
            str(policy),
            "--bank",
            str(bank),
            "--provenance",
            str(provenance),
            "--output",
            str(workload),
            "--source-root",
            str(source_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("formal_name", ["policy", "bank", "workload"])
@pytest.mark.parametrize("protected_name", ["packet", "provenance"])
def test_cli_output_collision_preserves_packet_and_provenance(
    tmp_path: Path,
    formal_name: str,
    protected_name: str,
) -> None:
    packet = tmp_path / "packet.json"
    provenance = tmp_path / "provenance.json"
    shutil.copyfile(PACKET_PATH, packet)
    shutil.copyfile(PROVENANCE_PATH, provenance)
    formal = {
        "policy": tmp_path / "policy.json",
        "bank": tmp_path / "bank.jsonl",
        "workload": tmp_path / "workload.json",
    }
    protected = packet if protected_name == "packet" else provenance
    formal[formal_name] = protected
    before = protected.read_bytes()

    completed = _run_cli_write(
        packet=packet,
        policy=formal["policy"],
        bank=formal["bank"],
        provenance=provenance,
        workload=formal["workload"],
        source_root=REPO_ROOT,
    )

    assert completed.returncode != 0
    assert "output collision" in completed.stderr or "protected input" in completed.stderr
    assert protected.read_bytes() == before


@pytest.mark.parametrize("formal_name", ["policy", "bank", "workload"])
def test_cli_output_collision_preserves_authorized_source_fixture(
    tmp_path: Path,
    formal_name: str,
) -> None:
    source_root = tmp_path / "source-root"
    _copy_sources(source_root)
    protected = source_root / SOURCE_PATHS[0]
    before = protected.read_bytes()
    formal = {
        "policy": tmp_path / "policy.json",
        "bank": tmp_path / "bank.jsonl",
        "workload": tmp_path / "workload.json",
    }
    formal[formal_name] = protected

    completed = _run_cli_write(
        packet=PACKET_PATH,
        policy=formal["policy"],
        bank=formal["bank"],
        provenance=PROVENANCE_PATH,
        workload=formal["workload"],
        source_root=source_root,
    )

    assert completed.returncode != 0
    assert "output collision" in completed.stderr or "protected input" in completed.stderr
    assert protected.read_bytes() == before


@pytest.mark.parametrize("protected_name", ["packet", "provenance", "source"])
def test_cli_output_collision_resolves_symlink_and_parent_aliases(
    tmp_path: Path,
    protected_name: str,
) -> None:
    protected_dir = tmp_path / "protected"
    protected_dir.mkdir()
    packet = protected_dir / "packet.json"
    provenance = protected_dir / "provenance.json"
    shutil.copyfile(PACKET_PATH, packet)
    shutil.copyfile(PROVENANCE_PATH, provenance)
    source_root = tmp_path / "source-root"
    _copy_sources(source_root)
    source = source_root / SOURCE_PATHS[0]
    protected = {"packet": packet, "provenance": provenance, "source": source}[
        protected_name
    ]
    before = protected.read_bytes()
    if protected_name == "packet":
        output_alias = tmp_path / "output-link.json"
        output_alias.symlink_to(protected)
    else:
        alias_parent = tmp_path / "alias-parent"
        alias_parent.symlink_to(protected.parent, target_is_directory=True)
        output_alias = alias_parent / protected.name

    completed = _run_cli_write(
        packet=packet,
        policy=tmp_path / "policy.json",
        bank=tmp_path / "bank.jsonl",
        provenance=provenance,
        workload=output_alias,
        source_root=source_root,
    )

    assert completed.returncode != 0
    assert "output collision" in completed.stderr or "protected input" in completed.stderr
    assert protected.read_bytes() == before


@pytest.mark.parametrize(
    "protected_name",
    ["packet", "policy", "bank", "provenance", *SOURCE_PATHS],
)
def test_build_workload_output_collision_preserves_every_protected_input(
    tmp_path: Path,
    protected_name: str,
) -> None:
    module = _builder_module()
    packet = tmp_path / "packet.json"
    policy = tmp_path / "policy.json"
    bank = tmp_path / "bank.jsonl"
    provenance = tmp_path / "provenance.json"
    shutil.copyfile(PACKET_PATH, packet)
    shutil.copyfile(POLICY_PATH, policy)
    shutil.copyfile(BANK_PATH, bank)
    shutil.copyfile(PROVENANCE_PATH, provenance)
    source_root = tmp_path / "source-root"
    _copy_sources(source_root)
    protected = {
        "packet": packet,
        "policy": policy,
        "bank": bank,
        "provenance": provenance,
        **{relative: source_root / relative for relative in SOURCE_PATHS},
    }[protected_name]
    before = protected.read_bytes()

    with pytest.raises(ValueError, match="output collision|protected input"):
        module.build_workload(
            packet_path=packet,
            policy_path=policy,
            bank_path=bank,
            provenance_path=provenance,
            source_root=source_root,
            output_path=protected,
        )
    assert protected.read_bytes() == before


def test_calibration_requests_have_strict_schema_hashes_and_exact_ids(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    workload = _build(module, output_path=tmp_path / "workload.json")
    rows = workload["calibration_probes"]
    assert [row["sample_id"] for row in rows] == [
        *(f"cal-v2-ce-{index:03d}" for index in range(1, 21)),
        *(f"cal-v2-ie-{index:03d}" for index in range(1, 11)),
        *(f"cal-v2-ct-{index:03d}" for index in range(1, 11)),
        *(f"cal-v2-sw-{index:03d}" for index in range(1, 11)),
        *(f"cal-v2-is-{index:03d}" for index in range(1, 11)),
    ]
    expected_keys = {
        "as_of",
        "candidate_observation",
        "critical_probe",
        "evidence_snapshots",
        "policy_id",
        "request_sha256",
        "requirement",
        "requirement_kind",
        "sample_id",
        "schema_version",
        "source_identity",
        "stratum",
    }
    for row in rows:
        assert set(row) == expected_keys
        assert set(row["source_identity"]) == {
            "path",
            "source_sha256",
            "test_name",
        }
        assert row["schema_version"] == "canonical-v2-human-calibration-request-v2"
        assert row["policy_id"] == "single-human-global-stratified-v2"
        request = {key: value for key, value in row.items() if key != "request_sha256"}
        assert row["request_sha256"] == _canonical_sha256(request)
        locator = row["requirement"]["fixture_locator"]
        assert locator["function"] == row["source_identity"]["test_name"]
        assert locator["selectors"]
        assert all(
            selector.startswith(("binding:", "literal:", "helper:"))
            for selector in locator["selectors"]
        )
        assert row["source_identity"]["path"] in SOURCE_PATHS
        assert (
            row["source_identity"]["source_sha256"]
            == _raw_sha256(REPO_ROOT / row["source_identity"]["path"])
        )
    assert rows[8]["evidence_snapshots"] == []  # CE09 model memory
    assert rows[9]["evidence_snapshots"] == []  # CE10 model memory
    assert rows[40]["evidence_snapshots"] == []  # SW01 server-owned static
    assert rows[48]["evidence_snapshots"][0]["provided_payload"] is False  # SW09
    assert "payload_bytes" not in rows[48]["evidence_snapshots"][0]
    assert rows[56]["evidence_snapshots"] == []  # IS07 model memory
    assert len(rows[20]["requirement"]["fixture_locator"]["selectors"]) >= 2
    assert len(rows[28]["requirement"]["fixture_locator"]["selectors"]) >= 2


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("sample_count", 59),
        ("reviewer_count", 2),
        ("minimum_agreement", 0.79),
        ("maximum_critical_false_accepts", 1),
    ],
)
def test_workload_rejects_policy_drift(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    module = _builder_module()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy[field] = replacement
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="policy"):
        _build(module, output_path=tmp_path / "out.json", policy_path=path)


def test_workload_rejects_packet_raw_or_content_tamper(tmp_path: Path) -> None:
    module = _builder_module()
    raw_tamper = tmp_path / "raw-tamper.json"
    raw_tamper.write_bytes(PACKET_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="packet.*raw|raw.*packet"):
        _build(module, output_path=tmp_path / "raw.json", packet_path=raw_tamper)

    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet["review_candidates"][0]["query"] += " tampered"
    content_tamper = tmp_path / "content-tamper.json"
    content_tamper.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(ValueError, match="packet.*(raw|content)|(raw|content).*packet"):
        _build(module, output_path=tmp_path / "content.json", packet_path=content_tamper)


def test_workload_rejects_changed_order_and_unknown_fields(tmp_path: Path) -> None:
    module = _builder_module()
    rows = _read_bank()
    rows[0], rows[1] = rows[1], rows[0]
    changed_order = tmp_path / "changed-order.jsonl"
    _write_bank(changed_order, rows)
    with pytest.raises(ValueError, match="order"):
        _build(module, output_path=tmp_path / "order.json", bank_path=changed_order)

    rows = _read_bank()
    rows[0]["unknown"] = True
    strict = tmp_path / "strict.jsonl"
    _write_bank(strict, rows)
    with pytest.raises(ValueError, match="schema|field|extra|request"):
        _build(module, output_path=tmp_path / "strict.json", bank_path=strict)


def test_workload_rejects_rehashed_frozen_observation_tamper(tmp_path: Path) -> None:
    module = _builder_module()
    rows = _read_bank()
    rows[0]["candidate_observation"]["value"] = "tampered-founder"
    _rehash_request(rows[0])
    path = tmp_path / "tampered-observation.jsonl"
    _write_bank(path, rows)
    with pytest.raises(ValueError, match="frozen|content"):
        _build(module, output_path=tmp_path / "out.json", bank_path=path)


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_LABEL_KEYS))
def test_workload_recursively_rejects_prefilled_labels(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    module = _builder_module()
    rows = _read_bank()
    rows[0]["candidate_observation"]["nested"] = {forbidden_key: "supported"}
    _rehash_request(rows[0])
    path = tmp_path / f"{forbidden_key}.jsonl"
    _write_bank(path, rows)
    with pytest.raises(ValueError, match="label|decision|truth|forbidden"):
        _build(module, output_path=tmp_path / "out.json", bank_path=path)


def test_workload_rejects_missing_and_nonunique_ast_locators(tmp_path: Path) -> None:
    module = _builder_module()
    rows = _read_bank()
    rows[0]["requirement"]["fixture_locator"]["selectors"] = [
        "binding:not_present_in_source"
    ]
    _rehash_request(rows[0])
    missing = tmp_path / "missing.jsonl"
    _write_bank(missing, rows)
    with pytest.raises(ValueError, match="locator|selector"):
        _build(module, output_path=tmp_path / "missing-out.json", bank_path=missing)

    rows = _read_bank()
    rows[0]["requirement"]["fixture_locator"]["selectors"] = ["binding:claim"]
    _rehash_request(rows[0])
    nonunique = tmp_path / "nonunique.jsonl"
    _write_bank(nonunique, rows)
    with pytest.raises(ValueError, match="function|locator|unique"):
        _build(
            module,
            output_path=tmp_path / "nonunique-out.json",
            bank_path=nonunique,
        )


def test_workload_rejects_source_hash_drift(tmp_path: Path) -> None:
    module = _builder_module()
    source_root = tmp_path / "source-root"
    _copy_sources(source_root)
    source_path = source_root / SOURCE_PATHS[0]
    source_path.write_bytes(source_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source.*hash|hash.*source"):
        _build(
            module,
            output_path=tmp_path / "out.json",
            source_root=source_root,
        )


def test_workload_rejects_duplicate_request_and_semantic_reskin(tmp_path: Path) -> None:
    module = _builder_module()
    rows = _read_bank()
    rows[1] = copy.deepcopy(rows[0])
    duplicate = tmp_path / "duplicate.jsonl"
    _write_bank(duplicate, rows)
    with pytest.raises(ValueError, match="duplicate.*request|request.*duplicate"):
        _build(module, output_path=tmp_path / "duplicate-out.json", bank_path=duplicate)

    rows = _read_bank()
    rows[1] = copy.deepcopy(rows[0])
    rows[1]["sample_id"] = "cal-v2-ce-002"
    rows[1]["source_identity"] = {
        "path": SOURCE_PATHS[1],
        "source_sha256": _raw_sha256(REPO_ROOT / SOURCE_PATHS[1]),
        "test_name": (
            "test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded"
        ),
    }
    rows[1]["requirement"]["fixture_locator"] = {
        "function": rows[1]["source_identity"]["test_name"],
        "selectors": ["binding:static_request"],
    }
    _rehash_request(rows[1])
    semantic = tmp_path / "semantic.jsonl"
    _write_bank(semantic, rows)
    with pytest.raises(ValueError, match="semantic.*duplicate|duplicate.*semantic"):
        _build(module, output_path=tmp_path / "semantic-out.json", bank_path=semantic)


def test_workload_rejects_insufficient_critical_probe_capacity(tmp_path: Path) -> None:
    module = _builder_module()
    rows = _read_bank()
    critical = [row for row in rows if row["critical_probe"]]
    assert len(critical) == 36
    for row in critical[4:]:
        row["critical_probe"] = False
        _rehash_request(row)
    path = tmp_path / "critical.jsonl"
    _write_bank(path, rows)
    with pytest.raises(ValueError, match="critical"):
        _build(module, output_path=tmp_path / "out.json", bank_path=path)
