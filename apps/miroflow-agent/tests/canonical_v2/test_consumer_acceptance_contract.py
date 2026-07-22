"""Atomic RED owner for aggregate Canonical V2 consumer acceptance evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import shlex
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from _pytest.junitxml import bin_xml_escape, mangle_test_address


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_ROOT = (
    _REPOSITORY_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c"
)
_MISSING_SENTINEL = "_MissingS11CAcceptanceEvidence"
_SIGNATURE_SCHEMA = "canonical-v2-s11b-baseline-signature-v3"
_GUARDED_RUN_IDS = frozenset({"admin-no-external", "canonical-v2-predecessors"})
_GUARDED_PROVENANCE_DERIVATION = "pytest-junit-testsuite-timestamp-plus-duration-v1"
_S11C_EVIDENCE_RELATIVE = ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c"
_PREDECESSOR_COMMAND_POINTERS = {
    "s11b-focused-agent-owners": "/verification/focused_agent_owners/command",
    "s11b-focused-admin-owners": ("/verification/focused_admin_s11b_owners/command"),
    "s11a-predecessor-owner": "/verification/s11a_predecessor_owner/command",
    "s10o-predecessor-owner": "/verification/s10o_predecessor_owner/command",
}
_S10O_RECEIPT_SHA256 = (
    "e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246"
)
_DISPOSABLE_ENV_NAMES = frozenset(
    {
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
    }
)
_ACCEPTED_S11B_RECEIPT = (
    _REPOSITORY_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/verification-receipt.json"
)
_INVENTORY = (
    _REPOSITORY_ROOT
    / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/legacy-consumer-inventory-v1.json"
)
_INVENTORY_SHA256_POINTER = "/legacy_consumer_inventory/sha256"
_REQUIRED_EVIDENCE_FAMILY_LABELS = frozenset(
    {
        "s11a_http_session",
        "s11b_admin_quarantine",
        "s2c_task_2_7_structural",
        "interface_scenario_trace",
        "disposable_postgres",
        "release_index_adapter",
    }
)
_ACCEPTED_S11B_COLLECTED = {
    "admin-no-external": (
        _REPOSITORY_ROOT
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/collected/admin-no-external.txt"
    ),
    "canonical-v2-no-external": (
        _REPOSITORY_ROOT
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/collected/canonical-v2-no-external.txt"
    ),
}
_OWNER_FILES_BY_FAMILY = {
    "s11a_http_session": {
        "admin-no-external": ("tests/test_canonical_v2_chat_http_adapter.py",),
    },
    "interface_scenario_trace": {
        "canonical-v2-no-external": (
            "tests/canonical_v2/test_evidence_landing_replay_contract.py",
            "tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py",
            "tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py",
            "tests/canonical_v2/test_knowledge_answer_grounding_contract.py",
            "tests/canonical_v2/test_knowledge_answer_multiturn_contract.py",
        ),
    },
    "disposable_postgres": {
        "canonical-v2-no-external": (
            "tests/canonical_v2/test_evidence_landing_postgres.py",
            "tests/canonical_v2/test_canonical_decision_postgres.py",
            "tests/canonical_v2/test_canonical_identity_postgres.py",
            "tests/canonical_v2/test_domain_projection_postgres.py",
            "tests/canonical_v2/test_relationship_projection_postgres.py",
        ),
    },
    "release_index_adapter": {
        "canonical-v2-no-external": (
            "tests/canonical_v2/test_release_publication_interface.py",
            "tests/canonical_v2/test_internal_reference_projection_contract.py",
        ),
    },
}
_S2C_ROOT = ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c"
_S2C_OWNER_NODEIDS = (
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_claim_level_contract_binds_strict_schema_version_hash_and_unique_ids",
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_claim_constraints_require_subject_object_materiality_and_evidence",
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_entity_constraints_and_variants_use_reviewed_identity_references",
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_dynamic_evidence_and_enumeration_require_replayable_coverage_context",
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_stage_oracles_allow_observable_outcomes_not_private_call_order",
    f"{_S2C_ROOT}/test_claim_level_case_contract.py::test_hard_outcomes_remain_per_case_and_reference_prose_is_review_only",
    f"{_S2C_ROOT}/test_claim_level_corpus_migration.py::test_migration_accounts_for_all_frozen_cases_without_premature_acceptance",
    f"{_S2C_ROOT}/test_claim_level_corpus_migration.py::test_reference_material_stays_review_only_and_known_bad_cases_stay_negative",
    f"{_S2C_ROOT}/test_claim_level_corpus_migration.py::test_multi_turn_context_is_bound_or_explicitly_blocked",
    f"{_S2C_ROOT}/test_claim_level_corpus_migration.py::test_rebuild_is_byte_deterministic_and_tamper_is_rejected",
    f"{_S2C_ROOT}/test_claim_level_corpus_migration.py::test_checked_repository_artifacts_match_deterministic_rebuild",
)
_S11B_ADMIN_QUARANTINE_OWNER_NODEIDS = (
    "tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers",
    "tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers",
    "tests/test_canonical_v2_operations_api.py::test_canonical_v2_operations_api_is_bounded_read_only_and_quarantined",
    "tests/test_smoke_canonical_v2_candidate.py::test_smoke_requires_explicit_release_and_reuses_one_cookie_session",
)
_PRODUCTION_AUTHORITY = {
    "accepted_s11b_receipt_path": _ACCEPTED_S11B_RECEIPT.relative_to(
        _REPOSITORY_ROOT
    ).as_posix(),
    "accepted_s11b_receipt_sha256": (
        "cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945"
    ),
    "guarded_capture_accepted_s11b": {
        "owner_path": (
            "apps/miroflow-agent/tests/scripts/"
            "test_capture_canonical_v2_s11b_baseline.py"
        ),
        "owner_sha256": (
            "47c060bb589bac6ae5c593eea2dfebf3272dd23b12e690662cd3e7322f95e1b3"
        ),
        "producer_path": (
            "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py"
        ),
        "producer_sha256": (
            "75fd8ea49cf6cab552c0eec1d196c9a41430543e10beb361bde14dd5e4638efa"
        ),
        "receipt_path": (
            ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
            "s11b/verification-receipt.json"
        ),
        "receipt_sha256": (
            "cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945"
        ),
    },
    "accepted_s11b_collected": {
        "admin-no-external": {
            "path": _ACCEPTED_S11B_COLLECTED["admin-no-external"]
            .relative_to(_REPOSITORY_ROOT)
            .as_posix(),
            "sha256": "b54da3fa9ce707775848ab00cd071b8678017395ec97a527fb264fc33c025457",
        },
        "canonical-v2-no-external": {
            "path": _ACCEPTED_S11B_COLLECTED["canonical-v2-no-external"]
            .relative_to(_REPOSITORY_ROOT)
            .as_posix(),
            "sha256": "2d70c10e585eca77836d15912fc70c6bd0a51dcc5dcbc6cb7a402894148611bd",
        },
    },
    "evidence_root": str(_EVIDENCE_ROOT),
    "inventory_path": _INVENTORY.relative_to(_REPOSITORY_ROOT).as_posix(),
    "inventory_sha256": (
        "c5a151b82cf308ec8504c31c10f6e6d997a3286ef18613d530088314a7f8f940"
    ),
    "inventory_sha256_pointer": _INVENTORY_SHA256_POINTER,
    # Historical S11C execution provenance, never the current checkout locator.
    "frozen_execution_repository_root": (
        "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s2"
    ),
    "retired_failure_ledger_sha256": (
        "271f4f9808a206e06cd616c95a778178f453fb67cf9284e9b93c33623fb75e7d"
    ),
    "hardcoded_owner_nodeids_by_family": {
        "s11b_admin_quarantine": _S11B_ADMIN_QUARANTINE_OWNER_NODEIDS,
        "s2c_task_2_7_structural": _S2C_OWNER_NODEIDS,
    },
    "owner_files_by_family": _OWNER_FILES_BY_FAMILY,
    "repository_root": str(_REPOSITORY_ROOT),
    "s11c_disposition_count": 0,
}


class _MissingS11CAcceptanceEvidence(RuntimeError):
    """The exact S11C aggregate evidence set has not been captured yet."""


def _sha256_raw_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _normalize_failure_text(
    value: str, *, basetemp_root: str, repository_root: str
) -> str:
    normalized = value.replace("\r\n", "\n")
    normalized = normalized.replace(f"{basetemp_root.rstrip('/')}/", "<pytest-tmp>/")
    return normalized.replace(f"{repository_root.rstrip('/')}/", "<repo>/")


def _normalized_failure_signature(
    *,
    outcome: str,
    message: str,
    body: str,
    basetemp_root: str,
    repository_root: str,
) -> str:
    if outcome not in {"failure", "error"}:
        raise ValueError("failure signature outcome must be failure or error")
    if not basetemp_root or not repository_root:
        raise ValueError("failure signature roots must be non-empty")
    normalized_message = _normalize_failure_text(
        message,
        basetemp_root=basetemp_root,
        repository_root=repository_root,
    )
    normalized_body = _normalize_failure_text(
        body,
        basetemp_root=basetemp_root,
        repository_root=repository_root,
    )
    payload = f"{outcome}\n{normalized_message}\n{normalized_body}".encode()
    return _sha256_raw_bytes(payload)


def _parse_collected_nodeids(raw: bytes) -> tuple[str, ...]:
    try:
        text = raw.decode()
    except UnicodeDecodeError as exc:
        raise ValueError("collected-nodeids must be UTF-8") from exc
    if not text.endswith("\n") or "\r" in text:
        raise ValueError("collected-nodeids must use canonical LF-terminated bytes")
    nodeids = tuple(text[:-1].split("\n"))
    if (
        not nodeids
        or any(not _is_exact_nodeid(nodeid) for nodeid in nodeids)
        or nodeids != tuple(sorted(set(nodeids)))
    ):
        raise ValueError(
            "collected-nodeids must be exact canonical sorted unique newline bytes"
        )
    return nodeids


def _junit_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _nodeid_matches_testcase(
    nodeid: str, *, file_name: str, classname: str, test_name: str
) -> bool:
    address = mangle_test_address(nodeid)
    if not address or bin_xml_escape(address[-1]) != test_name:
        return False
    nodeid_file = nodeid.split("::", 1)[0]
    if file_name and nodeid_file != file_name:
        return False
    return not classname or classname == ".".join(address[:-1])


def _parse_junit_testcases(
    raw: bytes, collected_nodeids: tuple[str, ...]
) -> tuple[dict[str, str], ...]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("JUnit must be valid XML") from exc
    cases: list[dict[str, str]] = []
    mapped_nodeids: set[str] = set()
    for testcase in (item for item in root.iter() if _junit_tag(item) == "testcase"):
        name = testcase.attrib.get("name", "")
        file_name = testcase.attrib.get("file", "")
        classname = testcase.attrib.get("classname", "")
        if not name:
            raise ValueError("JUnit testcase requires canonical name attribute")
        candidates = [
            nodeid
            for nodeid in collected_nodeids
            if _nodeid_matches_testcase(
                nodeid,
                file_name=file_name,
                classname=classname,
                test_name=name,
            )
        ]
        if len(candidates) != 1:
            raise ValueError(
                "JUnit testcase must uniquely map to matching collected-nodeids"
            )
        nodeid = candidates[0]
        if nodeid in mapped_nodeids:
            raise ValueError("JUnit testcase maps a collected nodeid more than once")
        mapped_nodeids.add(nodeid)
        outcome_elements = [
            child
            for child in testcase
            if _junit_tag(child) in {"failure", "error", "skipped"}
        ]
        if len(outcome_elements) > 1:
            raise ValueError("JUnit testcase has multiple outcomes")
        if not outcome_elements:
            outcome = "pass"
            message = ""
            body = ""
            phase = "call"
        else:
            outcome_element = outcome_elements[0]
            outcome = _junit_tag(outcome_element)
            message = outcome_element.attrib.get("message", "")
            body = "".join(outcome_element.itertext())
            phase = "call"
            if outcome == "error" and "failed on setup" in message:
                phase = "setup"
            elif outcome == "error" and "failed on teardown" in message:
                phase = "teardown"
        cases.append(
            {
                "body": body,
                "message": message,
                "nodeid": nodeid,
                "outcome": outcome,
                "phase": phase,
            }
        )
    if mapped_nodeids != set(collected_nodeids):
        raise ValueError("JUnit testcase set must equal collected-nodeids set")
    return tuple(cases)


def _inventory_entry_key(category: Any, entry: Any, *, label: str) -> tuple[str, str]:
    if not isinstance(category, str) or not category:
        raise ValueError(f"{label} category must be non-empty")
    if not isinstance(entry, dict):
        raise ValueError(f"{label} entry must be an object")
    identities: list[tuple[str, str]] = []
    for field in ("path", "module"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            identities.append((field, value))
    if len(identities) != 1:
        raise ValueError(f"{label} requires exactly one path/module key")
    _field, value = identities[0]
    return category, value


def _overlay_entry_key(entry: Any, *, label: str) -> tuple[str, str]:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} entry must be an object")
    category = entry.get("inventory_category")
    path = entry.get("inventory_path")
    if not isinstance(category, str) or not category:
        raise ValueError(f"{label} inventory_category must be non-empty")
    if not isinstance(path, str) or not path:
        raise ValueError(f"{label} inventory_path must be non-empty")
    return category, path


def _is_exact_nodeid(value: Any) -> bool:
    return isinstance(value, str) and value == value.strip() and "::" in value


def _is_forbidden_unrelated_owner(nodeid: str) -> bool:
    normalized = nodeid.casefold().replace("-", "_")
    if "s11" in normalized:
        return True
    if "candidate" in normalized and any(
        marker in normalized for marker in ("import", "route")
    ):
        return True
    return any(
        marker in normalized
        for marker in (
            "contract",
            "release",
            "index",
            "trace",
            "write_safety",
            "no_online_write",
            "target_safety",
        )
    )


def _required_owner_nodeids_by_family(
    evidence: dict[str, Any],
    receipt: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, frozenset[str]]:
    direct = authority.get("required_owner_nodeids_by_family")
    if isinstance(direct, dict):
        required = {
            label: frozenset(nodeids)
            for label, nodeids in direct.items()
            if isinstance(nodeids, (list, tuple))
        }
    else:
        snapshot_authority = authority.get("accepted_s11b_collected")
        snapshot_raw = evidence.get("accepted_s11b_collected_raw_by_run")
        owner_files = authority.get("owner_files_by_family")
        if (
            not isinstance(snapshot_authority, dict)
            or not isinstance(snapshot_raw, dict)
            or not isinstance(owner_files, dict)
        ):
            raise ValueError("Accepted S11B collected owner authority is missing")
        baseline = receipt.get("broad_test_baseline")
        if not isinstance(baseline, dict):
            raise ValueError("Accepted S11B broad baseline is missing")
        baseline_runs = {
            run.get("run_id"): run
            for run in baseline.get("runs", [])
            if isinstance(run, dict) and isinstance(run.get("run_id"), str)
        }
        snapshot_nodeids: dict[str, tuple[str, ...]] = {}
        if set(snapshot_raw) != set(snapshot_authority):
            raise ValueError("Accepted S11B collected snapshot set mismatch")
        for run_id, binding in snapshot_authority.items():
            raw = snapshot_raw.get(run_id)
            baseline_run = baseline_runs.get(run_id)
            if (
                not isinstance(binding, dict)
                or not isinstance(raw, bytes)
                or not isinstance(baseline_run, dict)
                or baseline_run.get("collected_nodeids_path") != binding.get("path")
                or baseline_run.get("collected_nodeids_sha256") != binding.get("sha256")
                or _sha256_raw_bytes(raw) != binding.get("sha256")
            ):
                raise ValueError("Accepted S11B collected snapshot authority mismatch")
            snapshot_nodeids[run_id] = _parse_collected_nodeids(raw)
        required = {}
        for label, by_snapshot in owner_files.items():
            owners: set[str] = set()
            for run_id, files in by_snapshot.items():
                available = snapshot_nodeids.get(run_id, ())
                for file_name in files:
                    file_owners = {
                        nodeid
                        for nodeid in available
                        if nodeid.split("::", 1)[0] == file_name
                    }
                    if not file_owners:
                        raise ValueError(
                            "Accepted S11B collected snapshot lacks required owner file"
                        )
                    owners.update(file_owners)
            required[label] = frozenset(owners)
        for label, nodeids in authority.get(
            "hardcoded_owner_nodeids_by_family", {}
        ).items():
            required[label] = frozenset(nodeids)
    if set(required) != _REQUIRED_EVIDENCE_FAMILY_LABELS or any(
        not nodeids or not all(_is_exact_nodeid(nodeid) for nodeid in nodeids)
        for nodeids in required.values()
    ):
        raise ValueError("required owner nodeids authority is incomplete")
    return required


def _lexical_posix_join(root: PurePosixPath, value: str) -> PurePosixPath:
    return PurePosixPath(posixpath.normpath(posixpath.join(root.as_posix(), value)))


def _frozen_capture_repository_root(
    ledger_runs: Any, *, authority: dict[str, Any]
) -> PurePosixPath:
    if not isinstance(ledger_runs, list) or not ledger_runs:
        raise ValueError("ledger runs must freeze one repository root")
    frozen_root = authority.get("frozen_execution_repository_root")
    repository_roots = [
        run.get("repository_root") if isinstance(run, dict) else None
        for run in ledger_runs
    ]
    if not isinstance(frozen_root, str) or any(
        root != frozen_root for root in repository_roots
    ):
        raise ValueError("ledger run repository_root must equal frozen repo root")
    frozen_path = PurePosixPath(frozen_root)
    if not frozen_path.is_absolute() or posixpath.normpath(frozen_root) != frozen_root:
        raise ValueError("ledger run repository_root must equal frozen repo root")
    return frozen_path


def _guarded_signature_temp_roots(
    guarded_receipt: dict[str, Any],
    *,
    ledger_runs: Any,
    capture_repository_root: PurePosixPath,
    authority: dict[str, Any],
) -> dict[str, str]:
    if (
        guarded_receipt.get("schema_version")
        != "canonical-v2-s11c-guarded-partitions-receipt-v1"
        or guarded_receipt.get("signature_schema_version") != _SIGNATURE_SCHEMA
        or guarded_receipt.get("capture_mode") != "real_subprocess"
        or not isinstance(ledger_runs, list)
    ):
        raise ValueError("guarded partitions receipt schema/content mismatch")
    expected_accepted_s11b = authority.get("guarded_capture_accepted_s11b")
    if (
        not isinstance(expected_accepted_s11b, dict)
        or guarded_receipt.get("accepted_s11b") != expected_accepted_s11b
    ):
        raise ValueError("guarded partitions Accepted S11B authority mismatch")
    ledger_by_run = {
        run.get("run_id"): run
        for run in ledger_runs
        if isinstance(run, dict) and isinstance(run.get("run_id"), str)
    }
    guarded_runs = guarded_receipt.get("runs")
    if not isinstance(guarded_runs, list):
        raise ValueError("guarded partitions receipt run set mismatch")
    guarded_by_run = {
        run.get("run_id"): run
        for run in guarded_runs
        if isinstance(run, dict) and isinstance(run.get("run_id"), str)
    }
    if (
        len(ledger_by_run) != len(ledger_runs)
        or len(guarded_by_run) != len(guarded_runs)
        or set(guarded_by_run) != _GUARDED_RUN_IDS
        or not _GUARDED_RUN_IDS.issubset(ledger_by_run)
    ):
        raise ValueError("guarded partitions receipt run set mismatch")
    bound_fields = (
        ("argv", "command"),
        ("exit_code", "exit_code"),
        ("collected_nodeids_path", "collected_nodeids_path"),
        ("collected_nodeids_sha256", "collected_nodeids_sha256"),
        ("junit_xml_path", "junit_xml_path"),
        ("junit_xml_sha256", "junit_xml_sha256"),
    )
    for run_id, guarded_run in guarded_by_run.items():
        ledger_run = ledger_by_run[run_id]
        if any(
            guarded_run.get(guarded_field) != ledger_run.get(ledger_field)
            for guarded_field, ledger_field in bound_fields
        ):
            raise ValueError("guarded partitions receipt run content mismatch")
        guarded_cwd = guarded_run.get("cwd")
        ledger_cwd = ledger_run.get("cwd")
        guarded_cwd_path = (
            PurePosixPath(guarded_cwd) if isinstance(guarded_cwd, str) else None
        )
        ledger_cwd_path = (
            PurePosixPath(ledger_cwd) if isinstance(ledger_cwd, str) else None
        )
        if (
            guarded_cwd_path is None
            or guarded_cwd_path.is_absolute()
            or ".." in guarded_cwd_path.parts
            or ledger_cwd_path is None
            or not ledger_cwd_path.is_absolute()
            or posixpath.normpath(ledger_cwd) != ledger_cwd
            or _lexical_posix_join(capture_repository_root, guarded_cwd)
            != ledger_cwd_path
        ):
            raise ValueError("guarded partitions receipt run cwd mismatch")

    guard = guarded_receipt.get("guard_preflight")
    if not isinstance(guard, dict):
        raise ValueError("guarded partitions receipt guard_preflight is missing")
    if guard.get("cleanup") is not True:
        raise ValueError("guard cleanup must be true")
    if (
        guard.get("terminal_receipts_captured_after_process_exit") is not True
        or guard.get("wrapper_stage_cleanup") is not True
        or guard.get("admin_marker_expression") != "not requires_classifier_llm"
        or guard.get("admin_deselected_nodeids")
        != ["tests/test_classifier_benchmark.py::test_classifier_benchmark"]
    ):
        raise ValueError("guarded partitions real-capture preflight mismatch")
    owned_temp_root_value = guard.get("owned_temp_root")
    if not isinstance(owned_temp_root_value, str):
        raise ValueError("guard owned_temp_root must be exact")
    owned_temp_root = PurePosixPath(owned_temp_root_value)
    if (
        not owned_temp_root.is_absolute()
        or posixpath.normpath(owned_temp_root_value) != owned_temp_root_value
    ):
        raise ValueError("guard owned_temp_root must be an exact absolute path")

    pytest_temp_roots = guard.get("pytest_temp_roots")
    if (
        not isinstance(pytest_temp_roots, dict)
        or set(pytest_temp_roots) != _GUARDED_RUN_IDS
    ):
        raise ValueError("guard run set must equal ledger run set")
    signature_roots: dict[str, str] = {}
    for run_id, mode_roots in pytest_temp_roots.items():
        run_root_value = mode_roots.get("run") if isinstance(mode_roots, dict) else None
        if not isinstance(run_root_value, str):
            raise ValueError("guard run root must be exact")
        run_root = PurePosixPath(run_root_value)
        if (
            not run_root.is_absolute()
            or posixpath.normpath(run_root_value) != run_root_value
            or run_root == owned_temp_root
            or not run_root.is_relative_to(owned_temp_root)
        ):
            raise ValueError("guard run root must be inside owned_temp_root")
        signature_roots[run_id] = run_root_value

    child_receipts = guard.get("child_receipts")
    if not isinstance(child_receipts, list):
        raise ValueError("guard terminal child receipts are missing")
    run_children = [
        child
        for child in child_receipts
        if isinstance(child, dict) and child.get("mode") == "run"
    ]
    child_by_root = {
        child.get("pytest_temp_root"): child
        for child in run_children
        if isinstance(child.get("pytest_temp_root"), str)
    }
    if (
        len(run_children) != len(signature_roots)
        or len(child_by_root) != len(run_children)
        or set(child_by_root) != set(signature_roots.values())
        or any(
            child.get("owned_temp_root") != owned_temp_root_value
            or child.get("session_finished") is not True
            or child.get("unconfigured") is not True
            for child in run_children
        )
    ):
        raise ValueError("guard terminal child receipt does not match run root")
    return signature_roots


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value).issubset(set("0123456789abcdef"))
    )


def _parse_exact_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be exact UTC")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be exact UTC") from exc
    if (
        parsed.utcoffset() != timedelta(0)
        or parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
        != value
    ):
        raise ValueError(f"{label} must be exact UTC")
    return parsed


def _junit_execution_window(raw: bytes) -> dict[str, str]:
    root = ET.fromstring(raw)
    suites = [element for element in root.iter() if _junit_tag(element) == "testsuite"]
    if len(suites) != 1:
        raise ValueError("guarded JUnit must contain exactly one testsuite")
    timestamp = suites[0].attrib.get("timestamp")
    duration_text = suites[0].attrib.get("time")
    if not timestamp or duration_text is None:
        raise ValueError("guarded JUnit lacks timestamp or duration")
    try:
        started = datetime.fromisoformat(timestamp)
        duration = Decimal(duration_text)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("guarded JUnit timestamp or duration is invalid") from exc
    if (
        started.tzinfo is None
        or started.utcoffset() != timedelta(0)
        or not duration.is_finite()
        or duration < 0
    ):
        raise ValueError("guarded JUnit execution window is not finite UTC")
    microseconds = duration * Decimal(1_000_000)
    if microseconds != microseconds.to_integral_value():
        raise ValueError("guarded JUnit duration exceeds microsecond precision")
    finished = started + timedelta(microseconds=int(microseconds))
    return {
        "junit_testsuite_duration_seconds": duration_text,
        "junit_testsuite_timestamp": timestamp,
        "derived_started_at_utc": (
            started.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        ),
        "derived_finished_at_utc": (
            finished.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        ),
    }


def _json_pointer_value(document: dict[str, Any], pointer: str) -> Any:
    current: Any = document
    for raw_token in pointer.removeprefix("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError("Accepted command JSON pointer is missing")
        current = current[token]
    return current


def _required_predecessor_nodeids(
    evidence: dict[str, Any],
    *,
    accepted_receipt: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, frozenset[str]]:
    direct = authority.get("predecessor_required_nodeids_by_run")
    if isinstance(direct, dict):
        required = {
            run_id: frozenset(nodeids)
            for run_id, nodeids in direct.items()
            if isinstance(run_id, str) and isinstance(nodeids, (list, tuple))
        }
    else:
        snapshot_raw = evidence.get("accepted_s11b_collected_raw_by_run")
        if not isinstance(snapshot_raw, dict):
            raise ValueError("predecessor rerun collected authority is missing")
        accepted_nodeids = {
            nodeid
            for raw in snapshot_raw.values()
            if isinstance(raw, bytes)
            for nodeid in _parse_collected_nodeids(raw)
        }
        required = {}
        for run_id, pointer in _PREDECESSOR_COMMAND_POINTERS.items():
            command = _json_pointer_value(accepted_receipt, pointer)
            if not isinstance(command, str):
                raise ValueError("Accepted predecessor command must be a string")
            targets = set(shlex.split(command))
            required[run_id] = frozenset(
                nodeid
                for nodeid in accepted_nodeids
                if nodeid in targets or nodeid.split("::", 1)[0] in targets
            )
    if set(required) != set(_PREDECESSOR_COMMAND_POINTERS) or any(
        not nodeids or not all(_is_exact_nodeid(nodeid) for nodeid in nodeids)
        for nodeids in required.values()
    ):
        raise ValueError("predecessor rerun required nodeids are incomplete")
    return required


def _validate_predecessor_reruns(
    predecessor_receipt: dict[str, Any],
    *,
    predecessor_v1_raw: bytes,
    evidence: dict[str, Any],
    accepted_receipt: dict[str, Any],
    authority: dict[str, Any],
    capture_repository_root: PurePosixPath,
    run_records: dict[str, dict[str, Any]],
    all_cases: dict[tuple[str, str], dict[str, str]],
) -> None:
    if (
        predecessor_receipt.get("schema_version")
        != "canonical-v2-s11c-predecessor-reruns-v2"
        or predecessor_receipt.get("accepted_s11b_receipt_path")
        != authority["accepted_s11b_receipt_path"]
        or predecessor_receipt.get("accepted_s11b_receipt_sha256")
        != authority["accepted_s11b_receipt_sha256"]
    ):
        raise ValueError("predecessor rerun Accepted S11B authority mismatch")
    if predecessor_receipt.get("supersedes") != {
        "path": f"{_S11C_EVIDENCE_RELATIVE}/predecessor-reruns-v1.json",
        "sha256": _sha256_raw_bytes(predecessor_v1_raw),
    }:
        raise ValueError("predecessor rerun v1 supersession binding mismatch")
    runs = predecessor_receipt.get("runs")
    if not isinstance(runs, list):
        raise ValueError("predecessor rerun set is missing")
    by_id = {
        row.get("run_id"): row
        for row in runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    if len(by_id) != len(runs) or set(by_id) != set(_PREDECESSOR_COMMAND_POINTERS):
        raise ValueError("predecessor rerun set must contain exact four runs")
    required = _required_predecessor_nodeids(
        evidence,
        accepted_receipt=accepted_receipt,
        authority=authority,
    )
    for run_id, pointer in _PREDECESSOR_COMMAND_POINTERS.items():
        row = by_id[run_id]
        command = _json_pointer_value(accepted_receipt, pointer)
        if row.get("cwd") != str(capture_repository_root):
            raise ValueError("predecessor rerun repository cwd mismatch")
        if set(row) != {
            "accepted_command",
            "accepted_command_json_pointer",
            "accepted_command_sha256",
            "cross_links",
            "cwd",
            "exit_code",
            "finished_at",
            "launcher_argv",
            "run_id",
            "sanitized_env_unset",
            "started_at",
            "stderr_sha256",
            "stdout_sha256",
        }:
            raise ValueError("predecessor rerun record exact keys mismatch")
        try:
            started_at = _parse_exact_utc(
                row.get("started_at"), label="predecessor rerun UTC window"
            )
            finished_at = _parse_exact_utc(
                row.get("finished_at"), label="predecessor rerun UTC window"
            )
        except ValueError as exc:
            raise ValueError("predecessor rerun UTC window mismatch") from exc
        if (
            not isinstance(command, str)
            or row.get("accepted_command_json_pointer") != pointer
            or row.get("accepted_command") != command
            or row.get("accepted_command_sha256") != _sha256_raw_bytes(command.encode())
            or row.get("cwd") != str(capture_repository_root)
            or row.get("launcher_argv") != ["/bin/bash", "-lc", command]
            or row.get("sanitized_env_unset") != ["HF_TOKEN"]
            or finished_at < started_at
            or row.get("exit_code") != 0
            or not _is_sha256(row.get("stdout_sha256"))
            or not _is_sha256(row.get("stderr_sha256"))
        ):
            raise ValueError("predecessor rerun command/result binding mismatch")
        cross_links = row.get("cross_links")
        if not isinstance(cross_links, list):
            raise ValueError("predecessor rerun cross-links are missing")
        linked_nodeids: set[str] = set()
        for link in cross_links:
            if not isinstance(link, dict):
                raise ValueError("predecessor rerun cross-link must be an object")
            nodeid = link.get("nodeid")
            ledger_run_id = link.get("ledger_run_id")
            if not isinstance(nodeid, str) or not isinstance(ledger_run_id, str):
                raise ValueError("predecessor rerun cross-link identity is invalid")
            ledger_run = run_records.get(ledger_run_id)
            case = all_cases.get((ledger_run_id, nodeid))
            if (
                ledger_run is None
                or case is None
                or case.get("outcome") != "pass"
                or link.get("junit_xml_sha256") != ledger_run.get("junit_xml_sha256")
            ):
                raise ValueError("predecessor rerun cross-link lacks a JUnit pass")
            linked_nodeids.add(nodeid)
        if linked_nodeids != set(required[run_id]) or len(linked_nodeids) != len(
            cross_links
        ):
            raise ValueError(
                "predecessor rerun cross-links are incomplete or duplicate"
            )


def _validate_guarded_execution_provenance(
    provenance: dict[str, Any],
    *,
    ledger_raw: bytes,
    guarded_partitions_receipt_raw: bytes,
    guarded_partitions_receipt: dict[str, Any],
    run_records: dict[str, dict[str, Any]],
    junit_by_run: dict[str, Any],
) -> None:
    if (
        provenance.get("schema_version")
        != "canonical-v2-s11c-guarded-execution-provenance-v1"
    ):
        raise ValueError("guarded execution provenance schema mismatch")
    expected_sources = {
        "guarded_partitions_receipt": {
            "path": f"{_S11C_EVIDENCE_RELATIVE}/guarded-partitions-receipt.json",
            "sha256": _sha256_raw_bytes(guarded_partitions_receipt_raw),
        },
        "retired_failure_ledger": {
            "path": f"{_S11C_EVIDENCE_RELATIVE}/retired-failure-ledger-v1.json",
            "sha256": _sha256_raw_bytes(ledger_raw),
        },
    }
    if provenance.get("source_artifacts") != expected_sources:
        raise ValueError("guarded execution source hash mismatch")
    runs = provenance.get("runs")
    if not isinstance(runs, list):
        raise ValueError("guarded execution provenance run set is missing")
    by_id = {
        row.get("run_id"): row
        for row in runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    guard_runs = guarded_partitions_receipt.get("runs")
    if not isinstance(guard_runs, list):
        raise ValueError("guarded execution source run set is missing")
    guard_by_id = {
        row.get("run_id"): row
        for row in guard_runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    if (
        len(by_id) != len(runs)
        or set(by_id) != _GUARDED_RUN_IDS
        or set(guard_by_id) != _GUARDED_RUN_IDS
    ):
        raise ValueError("guarded execution provenance run set mismatch")
    expected_keys = {
        "argv",
        "cwd",
        "derivation",
        "derived_finished_at_utc",
        "derived_started_at_utc",
        "junit_testsuite_duration_seconds",
        "junit_testsuite_timestamp",
        "junit_xml_path",
        "junit_xml_sha256",
        "run_id",
    }
    for run_id in sorted(_GUARDED_RUN_IDS):
        row = by_id[run_id]
        ledger_run = run_records.get(run_id)
        guard_run = guard_by_id[run_id]
        junit_raw = junit_by_run.get(run_id)
        if not isinstance(ledger_run, dict) or not isinstance(junit_raw, bytes):
            raise ValueError("guarded execution source run is missing")
        if row.get("junit_xml_sha256") != _sha256_raw_bytes(junit_raw):
            raise ValueError("guarded execution source hash mismatch")
        expected_window = _junit_execution_window(junit_raw)
        if any(row.get(key) != value for key, value in expected_window.items()):
            raise ValueError("guarded execution UTC window mismatch")
        if (
            set(row) != expected_keys
            or row.get("argv") != ledger_run.get("command")
            or row.get("argv") != guard_run.get("argv")
            or row.get("cwd") != ledger_run.get("cwd")
            or row.get("junit_xml_path") != ledger_run.get("junit_xml_path")
            or row.get("junit_xml_path") != guard_run.get("junit_xml_path")
            or row.get("junit_xml_sha256") != ledger_run.get("junit_xml_sha256")
            or row.get("junit_xml_sha256") != guard_run.get("junit_xml_sha256")
            or row.get("derivation") != _GUARDED_PROVENANCE_DERIVATION
        ):
            raise ValueError("guarded execution source binding mismatch")


def _validate_disposable_postgres_receipt(
    disposable_receipt: dict[str, Any],
    *,
    run_records: dict[str, dict[str, Any]],
    all_cases: dict[tuple[str, str], dict[str, str]],
) -> None:
    container = disposable_receipt.get("container")
    backup_gate = disposable_receipt.get("backup_gate")
    base = disposable_receipt.get("base")
    target = disposable_receipt.get("target")
    owner = disposable_receipt.get("owner_matrix")
    cleanup = disposable_receipt.get("cleanup")
    if (
        disposable_receipt.get("schema_version")
        != "canonical-v2-s11c-disposable-postgres-target-receipt-v1"
        or disposable_receipt.get("status") != "passed_cleanup_complete"
        or disposable_receipt.get("s10o_receipt_sha256") != _S10O_RECEIPT_SHA256
        or not all(
            isinstance(value, dict)
            for value in (container, backup_gate, base, target, owner, cleanup)
        )
    ):
        raise ValueError("disposable PostgreSQL receipt authority/status mismatch")
    assert isinstance(container, dict)
    assert isinstance(backup_gate, dict)
    assert isinstance(base, dict)
    assert isinstance(target, dict)
    assert isinstance(owner, dict)
    assert isinstance(cleanup, dict)
    if (
        container.get("name") != "canonical-v2-s6c-pg-20260712"
        or not _is_sha256(container.get("id"))
        or container.get("network_mode") != "none"
        or container.get("published_ports") != []
        or container.get("postflight_unchanged") is not True
        or backup_gate != {"source_count": 50, "status": "accepted"}
        or base
        != {
            "database": "canonical_v2_s6c_base",
            "marker": (
                "miroflow:destructive-target:v1:disposable:canonical_v2_s6c_base"
            ),
        }
        or target
        != {
            "created": True,
            "credentials_stored": False,
            "database": "miroflow_canonical_v2_s4c_disposable",
            "dsn_stored": False,
            "marker": (
                "miroflow:destructive-target:v1:disposable:"
                "miroflow_canonical_v2_s4c_disposable"
            ),
            "preexisting": False,
        }
        or disposable_receipt.get("provided_env_names") != sorted(_DISPOSABLE_ENV_NAMES)
        or cleanup
        != {
            "base_unchanged": True,
            "container_unchanged": True,
            "original_pgtest_unchanged": True,
            "target_database_absent": True,
        }
    ):
        raise ValueError("disposable PostgreSQL receipt target/cleanup mismatch")
    ledger_run = run_records.get("disposable-postgres")
    cases = [
        case
        for (run_id, _nodeid), case in all_cases.items()
        if run_id == "disposable-postgres"
    ]
    if (
        ledger_run is None
        or owner.get("run_id") != "disposable-postgres"
        or owner.get("exit_code") != 0
        or owner.get("passed") != 122
        or any(owner.get(key) != 0 for key in ("failed", "errors", "skipped"))
        or owner.get("junit_xml_sha256") != ledger_run.get("junit_xml_sha256")
        or ledger_run.get("exit_code") != 0
        or len(cases) != 122
        or any(case.get("outcome") != "pass" for case in cases)
    ):
        raise ValueError("disposable PostgreSQL receipt owner matrix mismatch")


def _validate_evidence_bundle(
    evidence: dict[str, Any], *, authority: dict[str, Any]
) -> None:
    receipt_raw = evidence.get("accepted_s11b_receipt_raw")
    inventory_raw = evidence.get("inventory_raw")
    overlay_raw = evidence.get("overlay_raw")
    ledger_raw = evidence.get("ledger_raw")
    guarded_partitions_receipt_raw = evidence.get("guarded_partitions_receipt_raw")
    guarded_execution_provenance_raw = evidence.get("guarded_execution_provenance_raw")
    predecessor_reruns_v1_raw = evidence.get("predecessor_reruns_raw")
    predecessor_reruns_v2_raw = evidence.get("predecessor_reruns_v2_raw")
    disposable_postgres_receipt_raw = evidence.get("disposable_postgres_receipt_raw")
    if not all(
        isinstance(raw, bytes)
        for raw in (
            receipt_raw,
            inventory_raw,
            overlay_raw,
            ledger_raw,
            guarded_partitions_receipt_raw,
            guarded_execution_provenance_raw,
            predecessor_reruns_v1_raw,
            predecessor_reruns_v2_raw,
            disposable_postgres_receipt_raw,
        )
    ):
        raise ValueError("acceptance evidence JSON inputs must be raw bytes")
    assert isinstance(receipt_raw, bytes)
    assert isinstance(inventory_raw, bytes)
    assert isinstance(overlay_raw, bytes)
    assert isinstance(ledger_raw, bytes)
    assert isinstance(guarded_partitions_receipt_raw, bytes)
    assert isinstance(guarded_execution_provenance_raw, bytes)
    assert isinstance(predecessor_reruns_v1_raw, bytes)
    assert isinstance(predecessor_reruns_v2_raw, bytes)
    assert isinstance(disposable_postgres_receipt_raw, bytes)
    frozen_ledger_sha256 = authority.get("retired_failure_ledger_sha256")
    if frozen_ledger_sha256 is not None and (
        not _is_sha256(frozen_ledger_sha256)
        or _sha256_raw_bytes(ledger_raw) != frozen_ledger_sha256
    ):
        raise ValueError("frozen ledger raw-byte SHA-256 mismatch")
    if _sha256_raw_bytes(receipt_raw) != authority["accepted_s11b_receipt_sha256"]:
        raise ValueError("Accepted S11B receipt raw-byte SHA-256 mismatch")
    if _sha256_raw_bytes(inventory_raw) != authority["inventory_sha256"]:
        raise ValueError("inventory raw-byte SHA-256 mismatch")

    receipt = _load_json_object(receipt_raw, label="Accepted S11B receipt")
    inventory = _load_json_object(inventory_raw, label="inventory")
    overlay = _load_json_object(overlay_raw, label="overlay")
    ledger = _load_json_object(ledger_raw, label="ledger")
    guarded_partitions_receipt = _load_json_object(
        guarded_partitions_receipt_raw,
        label="guarded partitions receipt",
    )
    guarded_execution_provenance = _load_json_object(
        guarded_execution_provenance_raw,
        label="guarded execution provenance",
    )
    predecessor_reruns = _load_json_object(
        predecessor_reruns_v2_raw,
        label="predecessor reruns",
    )
    disposable_postgres_receipt = _load_json_object(
        disposable_postgres_receipt_raw,
        label="disposable PostgreSQL receipt",
    )
    if _sha256_raw_bytes(guarded_partitions_receipt_raw) != ledger.get(
        "guarded_partitions_receipt_sha256"
    ):
        raise ValueError("guarded partitions receipt SHA-256 mismatch")
    if receipt.get("status") != "Accepted":
        raise ValueError("Accepted S11B receipt status mismatch")

    receipt_inventory = receipt.get("legacy_consumer_inventory")
    if not isinstance(receipt_inventory, dict):
        raise ValueError("Accepted S11B receipt inventory authority is missing")
    if receipt_inventory.get("path") != authority["inventory_path"]:
        raise ValueError("Accepted S11B inventory path mismatch")
    if receipt_inventory.get("sha256") != authority["inventory_sha256"]:
        raise ValueError("Accepted S11B inventory SHA-256 pointer value mismatch")
    if (
        receipt_inventory.get("s11c_disposition_count")
        != authority["s11c_disposition_count"]
    ):
        raise ValueError("Accepted S11B s11c_disposition_count mismatch")

    if set(overlay) != {
        "schema_version",
        "accepted_s11b_receipt_sha256",
        "base_inventory_receipt_json_pointer",
        "base_inventory_sha256",
        "entries",
    }:
        raise ValueError("overlay exact keys mismatch")
    if overlay.get("schema_version") != ("canonical-v2-s11c-disposition-overlay-v1"):
        raise ValueError("overlay schema_version mismatch")
    if (
        overlay.get("accepted_s11b_receipt_sha256")
        != authority["accepted_s11b_receipt_sha256"]
    ):
        raise ValueError("overlay Accepted S11B receipt binding mismatch")
    if (
        overlay.get("base_inventory_receipt_json_pointer")
        != authority["inventory_sha256_pointer"]
        or overlay.get("base_inventory_sha256") != authority["inventory_sha256"]
    ):
        raise ValueError("overlay inventory hash/pointer binding mismatch")

    inventory_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    s11c_entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for category, entries in inventory.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            key = _inventory_entry_key(category, entry, label="inventory")
            if key in inventory_by_key:
                raise ValueError("inventory has a duplicate category/path key")
            inventory_by_key[key] = entry
            if entry.get("disposition") == "s11c_disposition":
                s11c_entries_by_key[key] = entry
    if len(s11c_entries_by_key) != authority["s11c_disposition_count"]:
        raise ValueError("inventory s11c_disposition count mismatch")
    receipt_entries = receipt_inventory.get("s11c_disposition_entries")
    if not isinstance(receipt_entries, list):
        raise ValueError("Accepted S11B disposition entries are missing")
    receipt_keys = {
        _inventory_entry_key(
            entry.get("category") if isinstance(entry, dict) else None,
            entry,
            label="Accepted S11B disposition",
        )
        for entry in receipt_entries
    }
    if receipt_keys != set(s11c_entries_by_key):
        raise ValueError("Accepted S11B disposition entries mismatch inventory")

    overlay_entries = overlay.get("entries")
    if not isinstance(overlay_entries, list):
        raise ValueError("overlay entries must be a list")
    overlay_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in overlay_entries:
        if isinstance(entry, dict) and set(entry) == {
            "inventory_category",
            "inventory_path",
            "disposition",
            "replacement_owner_nodeids",
        }:
            raise ValueError("overlay reason must be non-empty")
        if not isinstance(entry, dict) or set(entry) != {
            "inventory_category",
            "inventory_path",
            "disposition",
            "replacement_owner_nodeids",
            "reason",
        }:
            raise ValueError("overlay entry exact keys mismatch")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError("overlay reason must be non-empty")
        key = _overlay_entry_key(entry, label="overlay")
        if key in overlay_by_key:
            raise ValueError("overlay key coverage contains a duplicate")
        if entry.get("disposition") not in {
            "replaced_owner_passed",
            "reference_only_quarantined",
        }:
            raise ValueError("overlay disposition is not allowed")
        owner_nodeids = entry.get("replacement_owner_nodeids")
        if (
            not isinstance(owner_nodeids, list)
            or not owner_nodeids
            or not all(_is_exact_nodeid(nodeid) for nodeid in owner_nodeids)
            or len(owner_nodeids) != len(set(owner_nodeids))
        ):
            raise ValueError(
                "overlay replacement_owner_nodeids must be non-empty exact nodeids"
            )
        overlay_by_key[key] = entry
    if set(overlay_by_key) != set(s11c_entries_by_key):
        raise ValueError("overlay key coverage must exactly match inventory")

    if ledger.get("schema_version") != ("canonical-v2-s11c-retired-failure-ledger-v1"):
        raise ValueError("ledger schema_version mismatch")
    if ledger.get("base_inventory_sha256") != authority["inventory_sha256"]:
        raise ValueError("ledger base_inventory_sha256 mismatch")
    if ledger.get("signature_schema_version") != _SIGNATURE_SCHEMA:
        raise ValueError("ledger signature schema mismatch")
    baseline = receipt.get("broad_test_baseline")
    if (
        not isinstance(baseline, dict)
        or baseline.get("signature_schema_version") != _SIGNATURE_SCHEMA
    ):
        raise ValueError("Accepted S11B baseline signature schema mismatch")
    required_owner_nodeids = _required_owner_nodeids_by_family(
        evidence, receipt, authority
    )
    labels = ledger.get("evidence_family_labels")
    if (
        not isinstance(labels, dict)
        or not _REQUIRED_EVIDENCE_FAMILY_LABELS.issubset(labels)
        or not all(
            isinstance(run_ids, list)
            and run_ids
            and len(run_ids) == len(set(run_ids))
            and all(isinstance(run_id, str) and run_id for run_id in run_ids)
            for run_ids in labels.values()
        )
    ):
        raise ValueError("required evidence-family labels are incomplete")

    collected_by_run = evidence.get("collected_raw_by_run")
    junit_by_run = evidence.get("junit_raw_by_run")
    if not isinstance(collected_by_run, dict) or not isinstance(junit_by_run, dict):
        raise ValueError("recorded collected/JUnit maps are missing")
    runs = ledger.get("runs")
    if not isinstance(runs, list):
        raise ValueError("ledger runs must be a list")
    capture_repository_root = _frozen_capture_repository_root(runs, authority=authority)
    signature_basetemp_roots = _guarded_signature_temp_roots(
        guarded_partitions_receipt,
        ledger_runs=runs,
        capture_repository_root=capture_repository_root,
        authority=authority,
    )
    run_records: dict[str, dict[str, Any]] = {}
    all_cases: dict[tuple[str, str], dict[str, str]] = {}
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
            raise ValueError("ledger run_id must be exact")
        run_id = run["run_id"]
        if not run_id or run_id in run_records:
            raise ValueError("ledger run_id must be unique")
        if set((run_id,)) - set(collected_by_run) or set((run_id,)) - set(junit_by_run):
            raise ValueError("ledger run lacks matching collected/JUnit bytes")
        collected_raw = collected_by_run[run_id]
        junit_raw = junit_by_run[run_id]
        if not isinstance(collected_raw, bytes) or not isinstance(junit_raw, bytes):
            raise ValueError("recorded collected/JUnit inputs must be raw bytes")
        command = run.get("command")
        exit_code = run.get("exit_code")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(token, str) and token for token in command)
            or not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
        ):
            raise ValueError("ledger run command/exit_code must be exact")
        if _sha256_raw_bytes(collected_raw) != run.get("collected_nodeids_sha256"):
            raise ValueError("collected-nodeids SHA-256 mismatch")
        if _sha256_raw_bytes(junit_raw) != run.get("junit_xml_sha256"):
            raise ValueError("JUnit raw-byte SHA-256 mismatch")
        if not str(run.get("collected_nodeids_path", "")).endswith(
            f"collected/{run_id}.txt"
        ) or not str(run.get("junit_xml_path", "")).endswith(f"junit/{run_id}.xml"):
            raise ValueError("ledger run artifact paths do not match run_id")
        repository_root = run.get("repository_root")
        basetemp_tokens = [
            token for token in command if token.startswith("--basetemp=")
        ]
        if len(basetemp_tokens) != 1:
            raise ValueError("ledger command must bind one exact --basetemp root")
        if repository_root != str(capture_repository_root):
            raise ValueError("ledger run repository_root must equal frozen repo root")
        cwd = run.get("cwd")
        cwd_path = PurePosixPath(cwd) if isinstance(cwd, str) else None
        if (
            cwd_path is None
            or not cwd_path.is_absolute()
            or posixpath.normpath(cwd) != cwd
        ):
            raise ValueError("ledger run cwd must be an exact absolute path")
        command_basetemp_value = basetemp_tokens[0].split("=", 1)[1]
        command_basetemp = PurePosixPath(command_basetemp_value)
        resolved_basetemp = (
            PurePosixPath(posixpath.normpath(command_basetemp_value))
            if command_basetemp.is_absolute()
            else _lexical_posix_join(cwd_path, command_basetemp_value)
        )
        try:
            evidence_relative = Path(authority["evidence_root"]).relative_to(
                Path(authority["repository_root"])
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("evidence root must be repository-relative") from None
        expected_basetemp = _lexical_posix_join(
            capture_repository_root,
            (evidence_relative / "tmp" / run_id / "pytest").as_posix(),
        )
        if resolved_basetemp != expected_basetemp:
            raise ValueError("ledger command --basetemp root mismatch")
        nodeids = _parse_collected_nodeids(collected_raw)
        cases = _parse_junit_testcases(junit_raw, nodeids)
        has_junit_failure = any(
            case["outcome"] in {"failure", "error"} for case in cases
        )
        if exit_code != (1 if has_junit_failure else 0):
            raise ValueError("ledger run exit_code/JUnit outcome mismatch")
        for case in cases:
            case_key = (run_id, case["nodeid"])
            if case_key in all_cases:
                raise ValueError("JUnit testcase identity is duplicated")
            all_cases[case_key] = case
        run_records[run_id] = run
    if set(run_records) != set(collected_by_run) or set(run_records) != set(
        junit_by_run
    ):
        raise ValueError("ledger runs must exactly cover collected/JUnit artifacts")
    for run_id in set(run_records) - _GUARDED_RUN_IDS:
        if run_records[run_id]["exit_code"] != 0 or any(
            case["outcome"] != "pass"
            for (case_run_id, _nodeid), case in all_cases.items()
            if case_run_id == run_id
        ):
            raise ValueError(
                "non-guarded Task 11.2 run must be exit-zero and fully passing"
            )
    if any(
        run_id not in run_records for run_ids in labels.values() for run_id in run_ids
    ):
        raise ValueError("evidence-family labels reference an unknown run")
    actual_failures: dict[tuple[str, str], tuple[str, str, str]] = {}
    outcomes_by_nodeid: dict[str, set[str]] = {}
    for (run_id, nodeid), case in all_cases.items():
        outcomes_by_nodeid.setdefault(nodeid, set()).add(case["outcome"])
        if case["outcome"] in {"failure", "error"}:
            run = run_records[run_id]
            signature = _normalized_failure_signature(
                outcome=case["outcome"],
                message=case["message"],
                body=case["body"],
                basetemp_root=signature_basetemp_roots[run_id],
                repository_root=run["repository_root"],
            )
            actual_failures[(run_id, nodeid)] = (
                case["outcome"],
                signature,
                case["phase"],
            )

    ledger_failures = ledger.get("failures")
    if not isinstance(ledger_failures, list):
        raise ValueError("ledger failures must be a list")
    ledger_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in ledger_failures:
        if not isinstance(row, dict):
            raise ValueError("ledger failure row must be an object")
        run_id = row.get("run_id")
        nodeid = row.get("nodeid")
        if (
            not isinstance(run_id, str)
            or not run_id
            or not isinstance(nodeid, str)
            or not nodeid
        ):
            raise ValueError("ledger failure identity must be exact")
        key = (run_id, nodeid)
        if _is_forbidden_unrelated_owner(nodeid):
            raise ValueError("ledger contains a protected failure")
        if key in ledger_by_key:
            raise ValueError("duplicate ledger failure identity")
        ledger_by_key[key] = row
        actual = actual_failures.get(key)
        if (
            actual is not None
            and row.get("outcome") == actual[0]
            and row.get("normalized_failure_signature_sha256") != actual[1]
        ):
            raise ValueError("ledger failure signature mismatch")
    if set(ledger_by_key) != set(actual_failures) or any(
        (
            row.get("outcome"),
            row.get("normalized_failure_signature_sha256"),
            row.get("phase"),
        )
        != actual_failures[key]
        for key, row in ledger_by_key.items()
        if key in actual_failures
    ):
        raise ValueError("JUnit failure/ledger bijection mismatch")

    def owner_passes(nodeid: str) -> bool:
        return outcomes_by_nodeid.get(nodeid) == {"pass"}

    for run_ids in labels.values():
        for run_id in run_ids:
            if run_records[run_id]["exit_code"] != 0 or any(
                case["outcome"] != "pass"
                for (case_run_id, _nodeid), case in all_cases.items()
                if case_run_id == run_id
            ):
                raise ValueError("evidence-family labels must reference passing runs")
    for label, required_nodeids in required_owner_nodeids.items():
        mapped_run_ids = set(labels[label])
        mapped_outcomes: dict[str, set[str]] = {}
        for (run_id, nodeid), case in all_cases.items():
            if run_id in mapped_run_ids:
                mapped_outcomes.setdefault(nodeid, set()).add(case["outcome"])
        if any(mapped_outcomes.get(nodeid) != {"pass"} for nodeid in required_nodeids):
            raise ValueError(
                "evidence-family mapping lacks required owner nodeids passing in JUnit"
            )

    for entry in overlay_by_key.values():
        if not all(
            owner_passes(nodeid) for nodeid in entry["replacement_owner_nodeids"]
        ):
            raise ValueError("every replacement owner must pass in recorded JUnit")

    accepted_baseline_failures = {
        (
            failure.get("nodeid"),
            failure.get("outcome"),
            failure.get("normalized_failure_signature_sha256"),
        )
        for run in baseline.get("runs", [])
        if isinstance(run, dict)
        for failure in run.get("failures", [])
        if isinstance(failure, dict)
    }
    retired_dispositions = {
        "retired_replaced": ("replaced", "replaced_owner_passed"),
        "retired_reference_only": (
            "reference_only",
            "reference_only_quarantined",
        ),
    }
    for row in ledger_failures:
        disposition = row.get("disposition")
        if disposition in retired_dispositions:
            key = _overlay_entry_key(row, label="retired ledger")
            inventory_entry = inventory_by_key.get(key)
            overlay_entry = overlay_by_key.get(key)
            replacement_owner_nodeids = row.get("replacement_owner_nodeids")
            if (
                not isinstance(replacement_owner_nodeids, list)
                or not replacement_owner_nodeids
                or not all(
                    _is_exact_nodeid(nodeid) for nodeid in replacement_owner_nodeids
                )
                or len(replacement_owner_nodeids) != len(set(replacement_owner_nodeids))
            ):
                raise ValueError(
                    "retired replacement_owner_nodeids must be non-empty exact unique nodeids"
                )
            if not all(owner_passes(nodeid) for nodeid in replacement_owner_nodeids):
                raise ValueError(
                    "every retired replacement owner must pass in recorded JUnit"
                )
            if inventory_entry is None:
                raise ValueError("retired ledger key must map to frozen inventory")
            base_disposition, overlay_disposition = retired_dispositions[disposition]
            if inventory_entry.get("disposition") == "s11c_disposition":
                if (
                    overlay_entry is None
                    or overlay_entry.get("disposition") != overlay_disposition
                ):
                    raise ValueError(
                        "retired ledger disposition mismatches frozen inventory/overlay"
                    )
                if replacement_owner_nodeids != overlay_entry.get(
                    "replacement_owner_nodeids"
                ):
                    raise ValueError("retired replacement owner set mismatches overlay")
            elif inventory_entry.get("disposition") != base_disposition:
                raise ValueError(
                    "retired ledger disposition mismatches frozen inventory/overlay"
                )
            if row.get("baseline_signature_sha256") is not None:
                raise ValueError("retired baseline_signature_sha256 must be null")
        elif disposition == "unrelated_preexisting":
            if (
                row.get("inventory_category") is not None
                or row.get("inventory_path") is not None
            ):
                raise ValueError("unrelated_preexisting inventory link must be null")
            baseline_identity = (
                row.get("nodeid"),
                row.get("outcome"),
                row.get("baseline_signature_sha256"),
            )
            if baseline_identity not in accepted_baseline_failures:
                raise ValueError(
                    "unrelated_preexisting must match Accepted S11B baseline"
                )
            if row.get("baseline_signature_sha256") != row.get(
                "normalized_failure_signature_sha256"
            ):
                raise ValueError(
                    "unrelated_preexisting must match Accepted S11B baseline signature"
                )
            if row.get("replacement_owner_nodeids") != []:
                raise ValueError(
                    "unrelated_preexisting replacement_owner_nodeids must be empty"
                )
            scope_owner = row.get("scope_owner_nodeid")
            if not _is_exact_nodeid(scope_owner) or not owner_passes(scope_owner):
                raise ValueError("scope_owner_nodeid must pass in recorded JUnit")
            if _is_forbidden_unrelated_owner(row["nodeid"]) or (
                _is_forbidden_unrelated_owner(scope_owner)
            ):
                raise ValueError("unrelated_preexisting forbidden owner")
        else:
            raise ValueError("ledger failure disposition is not allowed")

    _validate_guarded_execution_provenance(
        guarded_execution_provenance,
        ledger_raw=ledger_raw,
        guarded_partitions_receipt_raw=guarded_partitions_receipt_raw,
        guarded_partitions_receipt=guarded_partitions_receipt,
        run_records=run_records,
        junit_by_run=junit_by_run,
    )
    _validate_predecessor_reruns(
        predecessor_reruns,
        predecessor_v1_raw=predecessor_reruns_v1_raw,
        evidence=evidence,
        accepted_receipt=receipt,
        authority=authority,
        capture_repository_root=capture_repository_root,
        run_records=run_records,
        all_cases=all_cases,
    )
    _validate_disposable_postgres_receipt(
        disposable_postgres_receipt,
        run_records=run_records,
        all_cases=all_cases,
    )


def _read_required_acceptance_artifact(path: Path) -> bytes:
    if not path.is_file():
        pytest.xfail(_MISSING_SENTINEL)
        raise _MissingS11CAcceptanceEvidence(_MISSING_SENTINEL)
    return path.read_bytes()


def _declared_run_artifact_path(
    run: dict[str, Any],
    *,
    field: str,
    directory: str,
    suffix: str,
) -> Path:
    run_id = run["run_id"]
    expected = _EVIDENCE_ROOT / directory / f"{run_id}{suffix}"
    try:
        expected_declaration = expected.relative_to(_REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(
            "S11C evidence root must be inside the frozen repository"
        ) from exc
    if run.get(field) != expected_declaration:
        raise ValueError("ledger run artifact path must be the exact S11C run path")
    return expected


def load_s11c_acceptance_evidence() -> dict[str, Any]:
    """Fail before importing candidate/runtime code when evidence is incomplete."""

    ledger_raw = _read_required_acceptance_artifact(
        _EVIDENCE_ROOT / "retired-failure-ledger-v1.json"
    )
    ledger = _load_json_object(ledger_raw, label="ledger")
    runs = ledger.get("runs")
    if not isinstance(runs, list):
        raise ValueError("ledger runs must be a list")
    collected_raw_by_run: dict[str, bytes] = {}
    junit_raw_by_run: dict[str, bytes] = {}
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
            raise ValueError("ledger run_id must be exact")
        run_id = run["run_id"]
        if not run_id or Path(run_id).name != run_id or run_id in collected_raw_by_run:
            raise ValueError("ledger run_id must be a unique path segment")
        collected_path = _declared_run_artifact_path(
            run,
            field="collected_nodeids_path",
            directory="collected",
            suffix=".txt",
        )
        junit_path = _declared_run_artifact_path(
            run,
            field="junit_xml_path",
            directory="junit",
            suffix=".xml",
        )
        collected_raw_by_run[run_id] = _read_required_acceptance_artifact(
            collected_path
        )
        junit_raw_by_run[run_id] = _read_required_acceptance_artifact(junit_path)
    return {
        "accepted_s11b_receipt_raw": _ACCEPTED_S11B_RECEIPT.read_bytes(),
        "accepted_s11b_collected_raw_by_run": {
            run_id: path.read_bytes()
            for run_id, path in _ACCEPTED_S11B_COLLECTED.items()
        },
        "collected_raw_by_run": collected_raw_by_run,
        "disposable_postgres_receipt_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "disposable-postgres-target-receipt.json"
        ),
        "guarded_partitions_receipt_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "guarded-partitions-receipt.json"
        ),
        "guarded_execution_provenance_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "guarded-execution-provenance-v1.json"
        ),
        "inventory_raw": _INVENTORY.read_bytes(),
        "junit_raw_by_run": junit_raw_by_run,
        "ledger_raw": ledger_raw,
        "overlay_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "disposition-overlay-v1.json"
        ),
        "predecessor_reruns_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "predecessor-reruns-v1.json"
        ),
        "predecessor_reruns_v2_raw": _read_required_acceptance_artifact(
            _EVIDENCE_ROOT / "predecessor-reruns-v2.json"
        ),
    }


def validate_s11c_acceptance_evidence(evidence: dict[str, Any]) -> None:
    """Validate only persisted S11C evidence and Accepted predecessor receipts."""

    _validate_evidence_bundle(evidence, authority=_PRODUCTION_AUTHORITY)


def test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency() -> None:
    evidence = load_s11c_acceptance_evidence()
    validate_s11c_acceptance_evidence(evidence)


_SYNTHETIC_RETIRED_NODEID = "tests/test_retired.py::test_retired_consumer"
_SYNTHETIC_REPLACEMENT_NODEID = "tests/test_owner.py::test_replacement_owner"
_SYNTHETIC_UNRELATED_NODEID = "tests/test_old.py::test_unrelated_failure"
_SYNTHETIC_SCOPE_NODEID = "tests/test_scope.py::test_scope_owner"
_SYNTHETIC_CONTRACT_NODEID = "tests/test_contract.py::test_contract_owner"
_SYNTHETIC_FAMILY_NODEID = "tests/test_family.py::test_required_evidence_families"
_SYNTHETIC_UNRELATED_PASS_NODEID = "tests/test_unrelated_pass.py::test_unrelated_pass"
_SYNTHETIC_PROTECTED_FAILURE_NODEID = (
    "tests/test_release_index_contract.py::test_release_index_contract"
)
_SYNTHETIC_ADMIN_RUN = "admin-no-external"
_SYNTHETIC_PREDECESSOR_RUN = "canonical-v2-predecessors"
_SYNTHETIC_TASK11_2_RUN = "disposable-postgres"
_SYNTHETIC_REQUIRED_FAMILIES = (
    "s11a_http_session",
    "s11b_admin_quarantine",
    "s2c_task_2_7_structural",
    "interface_scenario_trace",
    "disposable_postgres",
    "release_index_adapter",
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _synthetic_acceptance_evidence(
    *,
    base_disposition: str = "s11c_disposition",
    retired_disposition: str = "retired_replaced",
) -> tuple[dict[str, Any], dict[str, Any]]:
    guard_owned_root = "/guard-owned"
    effective_basetemp_by_run = {
        run_id: f"{guard_owned_root}/{run_id}/run/pytest"
        for run_id in (_SYNTHETIC_ADMIN_RUN, _SYNTHETIC_PREDECESSOR_RUN)
    }
    inventory = {
        "retired_http_routers": [
            {
                "disposition": base_disposition,
                "module": "backend.api.retired",
            }
        ],
        "schema_version": "synthetic-inventory-v1",
    }
    inventory_raw = _json_bytes(inventory)
    inventory_sha256 = hashlib.sha256(inventory_raw).hexdigest()
    retired_signature = hashlib.sha256(
        (
            "failure\nretired boom at <pytest-tmp>/case.py\n"
            "retired body at <pytest-tmp>/body.py"
        ).encode()
    ).hexdigest()
    unrelated_signature = hashlib.sha256(
        b"failure\nunrelated boom\nunrelated body"
    ).hexdigest()
    synthetic_commands = {
        "focused_agent_owners": (
            f"pytest {_SYNTHETIC_REPLACEMENT_NODEID} tests/scripts/test_cli.py"
        ),
        "focused_admin_s11b_owners": f"pytest {_SYNTHETIC_SCOPE_NODEID}",
        "s11a_predecessor_owner": f"pytest {_SYNTHETIC_FAMILY_NODEID}",
        "s10o_predecessor_owner": f"pytest {_SYNTHETIC_CONTRACT_NODEID}",
    }
    receipt = {
        "broad_test_baseline": {
            "runs": [
                {
                    "failures": [
                        {
                            "nodeid": _SYNTHETIC_UNRELATED_NODEID,
                            "normalized_failure_signature_sha256": (
                                unrelated_signature
                            ),
                            "outcome": "failure",
                        }
                    ],
                    "run_id": "accepted-admin-baseline",
                }
            ],
            "signature_schema_version": "canonical-v2-s11b-baseline-signature-v3",
        },
        "legacy_consumer_inventory": {
            "path": "inventory.json",
            "s11c_disposition_count": int(base_disposition == "s11c_disposition"),
            "s11c_disposition_entries": (
                [
                    {
                        "category": "retired_http_routers",
                        "module": "backend.api.retired",
                    }
                ]
                if base_disposition == "s11c_disposition"
                else []
            ),
            "sha256": inventory_sha256,
        },
        "status": "Accepted",
        "verification": {
            key: {"command": command} for key, command in synthetic_commands.items()
        },
    }
    receipt_raw = _json_bytes(receipt)
    receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    overlay = {
        "accepted_s11b_receipt_sha256": receipt_sha256,
        "base_inventory_receipt_json_pointer": ("/legacy_consumer_inventory/sha256"),
        "base_inventory_sha256": inventory_sha256,
        "entries": (
            [
                {
                    "disposition": "replaced_owner_passed",
                    "inventory_category": "retired_http_routers",
                    "inventory_path": "backend.api.retired",
                    "reason": "synthetic retired consumer replacement",
                    "replacement_owner_nodeids": [_SYNTHETIC_REPLACEMENT_NODEID],
                }
            ]
            if base_disposition == "s11c_disposition"
            else []
        ),
        "schema_version": "canonical-v2-s11c-disposition-overlay-v1",
    }
    nodeids = tuple(
        sorted(
            (
                _SYNTHETIC_RETIRED_NODEID,
                _SYNTHETIC_REPLACEMENT_NODEID,
                _SYNTHETIC_UNRELATED_NODEID,
                _SYNTHETIC_SCOPE_NODEID,
                _SYNTHETIC_CONTRACT_NODEID,
            )
        )
    )
    collected_raw = ("\n".join(nodeids) + "\n").encode()
    junit_raw = f"""\
<testsuites><testsuite name="synthetic" timestamp="2026-07-21T00:00:00.000000+00:00" time="2.500">
  <testcase file="tests/test_retired.py" classname="tests.test_retired" name="test_retired_consumer"><failure message="retired boom at {effective_basetemp_by_run[_SYNTHETIC_ADMIN_RUN]}/case.py">retired body at {effective_basetemp_by_run[_SYNTHETIC_ADMIN_RUN]}/body.py</failure></testcase>
  <testcase file="tests/test_owner.py" classname="tests.test_owner" name="test_replacement_owner" />
  <testcase file="tests/test_old.py" classname="tests.test_old" name="test_unrelated_failure"><failure message="unrelated boom">unrelated body</failure></testcase>
  <testcase file="tests/test_scope.py" classname="tests.test_scope" name="test_scope_owner" />
  <testcase file="tests/test_contract.py" classname="tests.test_contract" name="test_contract_owner" />
</testsuite></testsuites>
""".encode()
    family_collected_raw = f"{_SYNTHETIC_FAMILY_NODEID}\n".encode()
    family_junit_raw = b"""\
<testsuite timestamp="2026-07-21T00:01:00.000000+00:00" time="1.250">
  <testcase file="tests/test_family.py" classname="tests.test_family" name="test_required_evidence_families" />
</testsuite>
"""
    task11_2_nodeids = tuple(
        sorted(
            (_SYNTHETIC_UNRELATED_PASS_NODEID,)
            + tuple(
                f"tests/test_task11_2.py::test_owner_{index:03d}"
                for index in range(121)
            )
        )
    )
    unrelated_pass_collected_raw = ("\n".join(task11_2_nodeids) + "\n").encode()
    unrelated_pass_junit_raw = (
        "<testsuite>\n"
        '  <testcase file="tests/test_unrelated_pass.py" '
        'classname="tests.test_unrelated_pass" name="test_unrelated_pass" />\n'
        + "".join(
            '  <testcase file="tests/test_task11_2.py" '
            f'classname="tests.test_task11_2" name="test_owner_{index:03d}" />\n'
            for index in range(121)
        )
        + "</testsuite>\n"
    ).encode()
    ledger = {
        "base_inventory_sha256": inventory_sha256,
        "evidence_family_labels": {
            label: [_SYNTHETIC_PREDECESSOR_RUN]
            for label in _SYNTHETIC_REQUIRED_FAMILIES
        },
        "failures": [
            {
                "baseline_signature_sha256": None,
                "disposition": retired_disposition,
                "inventory_category": "retired_http_routers",
                "inventory_path": "backend.api.retired",
                "nodeid": _SYNTHETIC_RETIRED_NODEID,
                "normalized_failure_signature_sha256": retired_signature,
                "outcome": "failure",
                "phase": "call",
                "reason": "synthetic retired consumer failure",
                "replacement_owner_nodeids": [_SYNTHETIC_REPLACEMENT_NODEID],
                "run_id": _SYNTHETIC_ADMIN_RUN,
                "scope_owner_nodeid": None,
            },
            {
                "baseline_signature_sha256": unrelated_signature,
                "disposition": "unrelated_preexisting",
                "inventory_category": None,
                "inventory_path": None,
                "nodeid": _SYNTHETIC_UNRELATED_NODEID,
                "normalized_failure_signature_sha256": unrelated_signature,
                "outcome": "failure",
                "phase": "call",
                "reason": "synthetic unchanged pre-existing failure",
                "replacement_owner_nodeids": [],
                "run_id": _SYNTHETIC_ADMIN_RUN,
                "scope_owner_nodeid": _SYNTHETIC_SCOPE_NODEID,
            },
        ],
        "runs": [
            {
                "collected_nodeids_path": f"collected/{_SYNTHETIC_ADMIN_RUN}.txt",
                "collected_nodeids_sha256": hashlib.sha256(collected_raw).hexdigest(),
                "command": [
                    "pytest",
                    f"--basetemp=evidence/tmp/{_SYNTHETIC_ADMIN_RUN}/pytest",
                ],
                "cwd": "/repo",
                "exit_code": 1,
                "junit_xml_path": f"junit/{_SYNTHETIC_ADMIN_RUN}.xml",
                "junit_xml_sha256": hashlib.sha256(junit_raw).hexdigest(),
                "repository_root": "/repo",
                "run_id": _SYNTHETIC_ADMIN_RUN,
            },
            {
                "collected_nodeids_path": f"collected/{_SYNTHETIC_PREDECESSOR_RUN}.txt",
                "collected_nodeids_sha256": hashlib.sha256(
                    family_collected_raw
                ).hexdigest(),
                "command": [
                    "pytest",
                    f"--basetemp=evidence/tmp/{_SYNTHETIC_PREDECESSOR_RUN}/pytest",
                ],
                "cwd": "/repo",
                "exit_code": 0,
                "junit_xml_path": f"junit/{_SYNTHETIC_PREDECESSOR_RUN}.xml",
                "junit_xml_sha256": hashlib.sha256(family_junit_raw).hexdigest(),
                "repository_root": "/repo",
                "run_id": _SYNTHETIC_PREDECESSOR_RUN,
            },
            {
                "collected_nodeids_path": f"collected/{_SYNTHETIC_TASK11_2_RUN}.txt",
                "collected_nodeids_sha256": hashlib.sha256(
                    unrelated_pass_collected_raw
                ).hexdigest(),
                "command": [
                    "pytest",
                    f"--basetemp=evidence/tmp/{_SYNTHETIC_TASK11_2_RUN}/pytest",
                ],
                "cwd": "/repo",
                "exit_code": 0,
                "junit_xml_path": f"junit/{_SYNTHETIC_TASK11_2_RUN}.xml",
                "junit_xml_sha256": hashlib.sha256(
                    unrelated_pass_junit_raw
                ).hexdigest(),
                "repository_root": "/repo",
                "run_id": _SYNTHETIC_TASK11_2_RUN,
            },
        ],
        "schema_version": "canonical-v2-s11c-retired-failure-ledger-v1",
        "signature_schema_version": "canonical-v2-s11b-baseline-signature-v3",
    }
    synthetic_guard_authority = {
        "owner_path": "tests/scripts/accepted-owner.py",
        "owner_sha256": "1" * 64,
        "producer_path": "scripts/accepted-producer.py",
        "producer_sha256": "2" * 64,
        "receipt_path": "receipt.json",
        "receipt_sha256": receipt_sha256,
    }
    guarded_partitions_receipt = {
        "accepted_s11b": synthetic_guard_authority,
        "capture_mode": "real_subprocess",
        "guard_preflight": {
            "admin_deselected_nodeids": [
                "tests/test_classifier_benchmark.py::test_classifier_benchmark"
            ],
            "admin_marker_expression": "not requires_classifier_llm",
            "child_receipts": [
                {
                    "mode": "run",
                    "owned_temp_root": guard_owned_root,
                    "pytest_temp_root": effective_basetemp_by_run[run_id],
                    "session_finished": True,
                    "unconfigured": True,
                }
                for run_id in effective_basetemp_by_run
            ],
            "cleanup": True,
            "owned_temp_root": guard_owned_root,
            "pytest_temp_roots": {
                run_id: {
                    "collect": f"{guard_owned_root}/{run_id}/collect/pytest",
                    "run": run_root,
                }
                for run_id, run_root in effective_basetemp_by_run.items()
            },
            "terminal_receipts_captured_after_process_exit": True,
            "wrapper_stage_cleanup": True,
        },
        "runs": [
            {
                "argv": row["command"],
                "collected_nodeids_path": row["collected_nodeids_path"],
                "collected_nodeids_sha256": row["collected_nodeids_sha256"],
                "cwd": ".",
                "exit_code": row["exit_code"],
                "junit_xml_path": row["junit_xml_path"],
                "junit_xml_sha256": row["junit_xml_sha256"],
                "run_id": row["run_id"],
            }
            for row in ledger["runs"]
            if row["run_id"] in {_SYNTHETIC_ADMIN_RUN, _SYNTHETIC_PREDECESSOR_RUN}
        ],
        "schema_version": "canonical-v2-s11c-guarded-partitions-receipt-v1",
        "signature_schema_version": "canonical-v2-s11b-baseline-signature-v3",
    }
    guarded_partitions_receipt_raw = _json_bytes(guarded_partitions_receipt)
    ledger_runs_by_id = {row["run_id"]: row for row in ledger["runs"]}
    predecessor_cross_link_targets = {
        "s11b-focused-agent-owners": (
            _SYNTHETIC_REPLACEMENT_NODEID,
            _SYNTHETIC_ADMIN_RUN,
        ),
        "s11b-focused-admin-owners": (
            _SYNTHETIC_SCOPE_NODEID,
            _SYNTHETIC_ADMIN_RUN,
        ),
        "s11a-predecessor-owner": (
            _SYNTHETIC_FAMILY_NODEID,
            _SYNTHETIC_PREDECESSOR_RUN,
        ),
        "s10o-predecessor-owner": (
            _SYNTHETIC_CONTRACT_NODEID,
            _SYNTHETIC_ADMIN_RUN,
        ),
    }
    predecessor_runs = []
    for run_id, pointer in _PREDECESSOR_COMMAND_POINTERS.items():
        verification_key = pointer.split("/")[2]
        command = synthetic_commands[verification_key]
        nodeid, ledger_run_id = predecessor_cross_link_targets[run_id]
        predecessor_runs.append(
            {
                "accepted_command": command,
                "accepted_command_json_pointer": pointer,
                "accepted_command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                "cross_links": [
                    {
                        "junit_xml_sha256": ledger_runs_by_id[ledger_run_id][
                            "junit_xml_sha256"
                        ],
                        "ledger_run_id": ledger_run_id,
                        "nodeid": nodeid,
                    }
                ],
                "exit_code": 0,
                "run_id": run_id,
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                "stdout_sha256": hashlib.sha256(run_id.encode()).hexdigest(),
            }
        )
    predecessor_reruns = {
        "accepted_s11b_receipt_sha256": receipt_sha256,
        "runs": predecessor_runs,
        "schema_version": "canonical-v2-s11c-predecessor-reruns-v1",
    }
    predecessor_reruns_raw = _json_bytes(predecessor_reruns)
    predecessor_reruns_v2 = {
        "accepted_s11b_receipt_path": "receipt.json",
        "accepted_s11b_receipt_sha256": receipt_sha256,
        "runs": [
            {
                **row,
                "cwd": "/repo",
                "finished_at": "2026-07-21T00:02:01.000000Z",
                "launcher_argv": ["/bin/bash", "-lc", row["accepted_command"]],
                "sanitized_env_unset": ["HF_TOKEN"],
                "started_at": "2026-07-21T00:02:00.000000Z",
            }
            for row in predecessor_runs
        ],
        "schema_version": "canonical-v2-s11c-predecessor-reruns-v2",
        "supersedes": {
            "path": (
                ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
                "s11c/predecessor-reruns-v1.json"
            ),
            "sha256": hashlib.sha256(predecessor_reruns_raw).hexdigest(),
        },
    }
    disposable_run = ledger_runs_by_id[_SYNTHETIC_TASK11_2_RUN]
    disposable_postgres_receipt = {
        "backup_gate": {"source_count": 50, "status": "accepted"},
        "base": {
            "database": "canonical_v2_s6c_base",
            "marker": (
                "miroflow:destructive-target:v1:disposable:canonical_v2_s6c_base"
            ),
        },
        "cleanup": {
            "base_unchanged": True,
            "container_unchanged": True,
            "original_pgtest_unchanged": True,
            "target_database_absent": True,
        },
        "container": {
            "id": "a" * 64,
            "name": "canonical-v2-s6c-pg-20260712",
            "network_mode": "none",
            "postflight_unchanged": True,
            "published_ports": [],
        },
        "owner_matrix": {
            "errors": 0,
            "exit_code": 0,
            "failed": 0,
            "junit_xml_sha256": disposable_run["junit_xml_sha256"],
            "passed": 122,
            "run_id": _SYNTHETIC_TASK11_2_RUN,
            "skipped": 0,
        },
        "provided_env_names": sorted(_DISPOSABLE_ENV_NAMES),
        "s10o_receipt_sha256": _S10O_RECEIPT_SHA256,
        "schema_version": ("canonical-v2-s11c-disposable-postgres-target-receipt-v1"),
        "status": "passed_cleanup_complete",
        "target": {
            "created": True,
            "credentials_stored": False,
            "database": "miroflow_canonical_v2_s4c_disposable",
            "dsn_stored": False,
            "marker": (
                "miroflow:destructive-target:v1:disposable:"
                "miroflow_canonical_v2_s4c_disposable"
            ),
            "preexisting": False,
        },
    }
    ledger["guarded_partitions_receipt_sha256"] = hashlib.sha256(
        guarded_partitions_receipt_raw
    ).hexdigest()
    ledger_raw = _json_bytes(ledger)
    guarded_execution_provenance = {
        "runs": [
            {
                "argv": ledger["runs"][0]["command"],
                "cwd": "/repo",
                "derivation": "pytest-junit-testsuite-timestamp-plus-duration-v1",
                "derived_finished_at_utc": "2026-07-21T00:00:02.500000Z",
                "derived_started_at_utc": "2026-07-21T00:00:00.000000Z",
                "junit_testsuite_duration_seconds": "2.500",
                "junit_testsuite_timestamp": ("2026-07-21T00:00:00.000000+00:00"),
                "junit_xml_path": ledger["runs"][0]["junit_xml_path"],
                "junit_xml_sha256": ledger["runs"][0]["junit_xml_sha256"],
                "run_id": _SYNTHETIC_ADMIN_RUN,
            },
            {
                "argv": ledger["runs"][1]["command"],
                "cwd": "/repo",
                "derivation": "pytest-junit-testsuite-timestamp-plus-duration-v1",
                "derived_finished_at_utc": "2026-07-21T00:01:01.250000Z",
                "derived_started_at_utc": "2026-07-21T00:01:00.000000Z",
                "junit_testsuite_duration_seconds": "1.250",
                "junit_testsuite_timestamp": ("2026-07-21T00:01:00.000000+00:00"),
                "junit_xml_path": ledger["runs"][1]["junit_xml_path"],
                "junit_xml_sha256": ledger["runs"][1]["junit_xml_sha256"],
                "run_id": _SYNTHETIC_PREDECESSOR_RUN,
            },
        ],
        "schema_version": "canonical-v2-s11c-guarded-execution-provenance-v1",
        "source_artifacts": {
            "guarded_partitions_receipt": {
                "path": (
                    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
                    "s11c/guarded-partitions-receipt.json"
                ),
                "sha256": hashlib.sha256(guarded_partitions_receipt_raw).hexdigest(),
            },
            "retired_failure_ledger": {
                "path": (
                    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
                    "s11c/retired-failure-ledger-v1.json"
                ),
                "sha256": hashlib.sha256(ledger_raw).hexdigest(),
            },
        },
    }
    evidence = {
        "accepted_s11b_receipt_raw": receipt_raw,
        "collected_raw_by_run": {
            _SYNTHETIC_ADMIN_RUN: collected_raw,
            _SYNTHETIC_PREDECESSOR_RUN: family_collected_raw,
            _SYNTHETIC_TASK11_2_RUN: unrelated_pass_collected_raw,
        },
        "guarded_partitions_receipt_raw": guarded_partitions_receipt_raw,
        "inventory_raw": inventory_raw,
        "junit_raw_by_run": {
            _SYNTHETIC_ADMIN_RUN: junit_raw,
            _SYNTHETIC_PREDECESSOR_RUN: family_junit_raw,
            _SYNTHETIC_TASK11_2_RUN: unrelated_pass_junit_raw,
        },
        "guarded_execution_provenance_raw": _json_bytes(guarded_execution_provenance),
        "ledger_raw": ledger_raw,
        "overlay_raw": _json_bytes(overlay),
        "predecessor_reruns_raw": predecessor_reruns_raw,
        "predecessor_reruns_v2_raw": _json_bytes(predecessor_reruns_v2),
        "disposable_postgres_receipt_raw": _json_bytes(disposable_postgres_receipt),
    }
    authority = {
        "accepted_s11b_receipt_path": "receipt.json",
        "accepted_s11b_receipt_sha256": receipt_sha256,
        "evidence_root": "/repo/evidence",
        "inventory_path": "inventory.json",
        "inventory_sha256": inventory_sha256,
        "inventory_sha256_pointer": "/legacy_consumer_inventory/sha256",
        "frozen_execution_repository_root": "/repo",
        "repository_root": "/repo",
        "guarded_capture_accepted_s11b": synthetic_guard_authority,
        "predecessor_required_nodeids_by_run": {
            run_id: [nodeid]
            for run_id, (nodeid, _ledger_run_id) in (
                predecessor_cross_link_targets.items()
            )
        },
        "required_owner_nodeids_by_family": {
            label: [_SYNTHETIC_FAMILY_NODEID] for label in _SYNTHETIC_REQUIRED_FAMILIES
        },
        "s11c_disposition_count": int(base_disposition == "s11c_disposition"),
    }
    return evidence, authority


def _mutate_json(evidence: dict[str, Any], key: str, mutation: Any) -> None:
    value = json.loads(evidence[key])
    mutation(value)
    evidence[key] = _json_bytes(value)


def _tamper_receipt_raw(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    evidence["accepted_s11b_receipt_raw"] += b" "


def _tamper_inventory_raw(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    evidence["inventory_raw"] += b" "


def _drop_overlay_entry(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    _mutate_json(evidence, "overlay_raw", lambda value: value["entries"].clear())


def _use_invalid_overlay_disposition(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "overlay_raw",
        lambda value: value["entries"][0].update({"disposition": "waived"}),
    )


def _empty_replacement_owner(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "overlay_raw",
        lambda value: value["entries"][0].update({"replacement_owner_nodeids": []}),
    )


def _drop_collected_nodeid(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    evidence["collected_raw_by_run"][_SYNTHETIC_ADMIN_RUN] = evidence[
        "collected_raw_by_run"
    ][_SYNTHETIC_ADMIN_RUN].replace(f"{_SYNTHETIC_UNRELATED_NODEID}\n".encode(), b"")


def _drop_ledger_row(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    _mutate_json(evidence, "ledger_raw", lambda value: value["failures"].pop())


def _duplicate_ledger_row(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["failures"].append(copy.deepcopy(value["failures"][0])),
    )


def _change_ledger_signature(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["failures"][0].update(
            {"normalized_failure_signature_sha256": "0" * 64}
        ),
    )


def _make_replacement_owner_nonpassing(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN] = evidence["junit_raw_by_run"][
        _SYNTHETIC_ADMIN_RUN
    ].replace(
        b'<testcase file="tests/test_owner.py" classname="tests.test_owner" name="test_replacement_owner" />',
        b'<testcase file="tests/test_owner.py" classname="tests.test_owner" name="test_replacement_owner"><skipped /></testcase>',
    )
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["runs"][0].update(
            {
                "junit_xml_sha256": hashlib.sha256(
                    evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN]
                ).hexdigest()
            }
        ),
    )
    _sync_guard_receipt_runs_to_ledger(evidence)


def _change_unrelated_signature_from_baseline(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN] = evidence["junit_raw_by_run"][
        _SYNTHETIC_ADMIN_RUN
    ].replace(b"unrelated body", b"changed unrelated body")
    changed_signature = hashlib.sha256(
        b"failure\nunrelated boom\nchanged unrelated body"
    ).hexdigest()
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: (
            value["failures"][1].update(
                {"normalized_failure_signature_sha256": changed_signature}
            ),
            value["runs"][0].update(
                {
                    "junit_xml_sha256": hashlib.sha256(
                        evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN]
                    ).hexdigest()
                }
            ),
        ),
    )
    _sync_guard_receipt_runs_to_ledger(evidence)


def _use_forbidden_scope_owner(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["failures"][1].update(
            {"scope_owner_nodeid": _SYNTHETIC_CONTRACT_NODEID}
        ),
    )
    _sync_guard_receipt_runs_to_ledger(evidence)


def _use_missing_scope_owner(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["failures"][1].update(
            {"scope_owner_nodeid": "tests/test_scope.py::test_missing_owner"}
        ),
    )


def _drop_evidence_family(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["evidence_family_labels"].pop("release_index_adapter"),
    )


def _claim_all_families_with_unrelated_pass(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value.update(
            {
                "evidence_family_labels": {
                    label: [_SYNTHETIC_TASK11_2_RUN]
                    for label in _SYNTHETIC_REQUIRED_FAMILIES
                }
            }
        ),
    )


def _mismatch_command_basetemp_root(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["runs"][0].update(
            {"command": ["pytest", "--basetemp=evidence/tmp/wrong/pytest"]}
        ),
    )
    _sync_guard_receipt_runs_to_ledger(evidence)


def _mismatch_repository_root(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["runs"][0].update({"repository_root": "/wrong"}),
    )


def _disguise_protected_failure_as_retired(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    collected = (
        evidence["collected_raw_by_run"][_SYNTHETIC_ADMIN_RUN].decode().splitlines()
    )
    collected[collected.index(_SYNTHETIC_RETIRED_NODEID)] = (
        _SYNTHETIC_PROTECTED_FAILURE_NODEID
    )
    evidence["collected_raw_by_run"][_SYNTHETIC_ADMIN_RUN] = (
        "\n".join(sorted(collected)) + "\n"
    ).encode()
    evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN] = evidence["junit_raw_by_run"][
        _SYNTHETIC_ADMIN_RUN
    ].replace(
        b'file="tests/test_retired.py" classname="tests.test_retired" name="test_retired_consumer"',
        b'file="tests/test_release_index_contract.py" classname="tests.test_release_index_contract" name="test_release_index_contract"',
    )

    def update_ledger(value: dict[str, Any]) -> None:
        value["failures"][0]["nodeid"] = _SYNTHETIC_PROTECTED_FAILURE_NODEID
        value["runs"][0]["collected_nodeids_sha256"] = hashlib.sha256(
            evidence["collected_raw_by_run"][_SYNTHETIC_ADMIN_RUN]
        ).hexdigest()
        value["runs"][0]["junit_xml_sha256"] = hashlib.sha256(
            evidence["junit_raw_by_run"][_SYNTHETIC_ADMIN_RUN]
        ).hexdigest()

    _mutate_json(evidence, "ledger_raw", update_ledger)
    _sync_guard_receipt_runs_to_ledger(evidence)


def _add_overlay_root_nesting(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "overlay_raw",
        lambda value: value.update({"legacy_consumer_inventory": {}}),
    )


def _add_overlay_inventory_id(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "overlay_raw",
        lambda value: value["entries"][0].update({"inventory_id": "invented"}),
    )


def _drop_overlay_reason(evidence: dict[str, Any], _authority: dict[str, Any]) -> None:
    _mutate_json(
        evidence,
        "overlay_raw",
        lambda value: value["entries"][0].pop("reason"),
    )


def _swallow_failure_exit_code(
    evidence: dict[str, Any], _authority: dict[str, Any]
) -> None:
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["runs"][0].update({"exit_code": 0}),
    )
    _sync_guard_receipt_runs_to_ledger(evidence)


def _rewrite_guard_receipt(
    evidence: dict[str, Any], mutation: Any, *, rebind_sha256: bool
) -> None:
    receipt = json.loads(evidence["guarded_partitions_receipt_raw"])
    mutation(receipt)
    raw = _json_bytes(receipt)
    evidence["guarded_partitions_receipt_raw"] = raw
    if rebind_sha256:
        _mutate_json(
            evidence,
            "ledger_raw",
            lambda ledger: ledger.update(
                {"guarded_partitions_receipt_sha256": hashlib.sha256(raw).hexdigest()}
            ),
        )


def _sync_guard_receipt_runs_to_ledger(evidence: dict[str, Any]) -> None:
    ledger = json.loads(evidence["ledger_raw"])
    guarded_receipt = json.loads(evidence["guarded_partitions_receipt_raw"])
    ledger_by_run = {row["run_id"]: row for row in ledger["runs"]}
    for guarded_run in guarded_receipt["runs"]:
        ledger_run = ledger_by_run[guarded_run["run_id"]]
        guarded_run.update(
            {
                "argv": ledger_run["command"],
                "collected_nodeids_path": ledger_run["collected_nodeids_path"],
                "collected_nodeids_sha256": ledger_run["collected_nodeids_sha256"],
                "exit_code": ledger_run["exit_code"],
                "junit_xml_path": ledger_run["junit_xml_path"],
                "junit_xml_sha256": ledger_run["junit_xml_sha256"],
            }
        )
    guarded_raw = _json_bytes(guarded_receipt)
    evidence["guarded_partitions_receipt_raw"] = guarded_raw
    ledger["guarded_partitions_receipt_sha256"] = hashlib.sha256(
        guarded_raw
    ).hexdigest()
    evidence["ledger_raw"] = _json_bytes(ledger)


def _put_guard_root_outside_owned_root(receipt: dict[str, Any]) -> None:
    guard = receipt["guard_preflight"]
    original = guard["pytest_temp_roots"][_SYNTHETIC_ADMIN_RUN]["run"]
    replacement = "/outside-owned-root/admin/run/pytest"
    guard["pytest_temp_roots"][_SYNTHETIC_ADMIN_RUN]["run"] = replacement
    child = next(
        row
        for row in guard["child_receipts"]
        if row["mode"] == "run" and row["pytest_temp_root"] == original
    )
    child["pytest_temp_root"] = replacement


def _drop_guard_run_root(receipt: dict[str, Any]) -> None:
    receipt["guard_preflight"]["pytest_temp_roots"].pop(_SYNTHETIC_PREDECESSOR_RUN)


def _make_guard_child_nonterminal(receipt: dict[str, Any]) -> None:
    receipt["guard_preflight"]["child_receipts"][0]["session_finished"] = False


def _make_guard_child_configured(receipt: dict[str, Any]) -> None:
    receipt["guard_preflight"]["child_receipts"][0]["unconfigured"] = False


def _make_guard_cleanup_false(receipt: dict[str, Any]) -> None:
    receipt["guard_preflight"]["cleanup"] = False


def _make_non_guarded_task11_2_run_skipped(evidence: dict[str, Any]) -> None:
    raw = evidence["junit_raw_by_run"][_SYNTHETIC_TASK11_2_RUN].replace(
        b'name="test_unrelated_pass" />',
        b'name="test_unrelated_pass"><skipped /></testcase>',
    )
    evidence["junit_raw_by_run"][_SYNTHETIC_TASK11_2_RUN] = raw
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda ledger: next(
            row for row in ledger["runs"] if row["run_id"] == _SYNTHETIC_TASK11_2_RUN
        ).update({"junit_xml_sha256": hashlib.sha256(raw).hexdigest()}),
    )


def test_helper_raw_bytes_and_failure_signature_contract() -> None:
    raw = b"raw\r\nbytes"
    assert _sha256_raw_bytes(raw) == hashlib.sha256(raw).hexdigest()

    message = "at /repo/evidence/tmp/run/pytest/case.py\r\nand /repo/src.py\rkept"
    body = "/repo/evidence/tmp/run/pytest/body.py\r\n/repo/body.py"
    normalized_payload = (
        "failure\n"
        "at <pytest-tmp>/case.py\nand <repo>/src.py\rkept\n"
        "<pytest-tmp>/body.py\n<repo>/body.py"
    ).encode()
    assert (
        _normalized_failure_signature(
            outcome="failure",
            message=message,
            body=body,
            basetemp_root="/repo/evidence/tmp/run/pytest",
            repository_root="/repo",
        )
        == hashlib.sha256(normalized_payload).hexdigest()
    )


def test_helper_junit_mapping_is_unique_and_parses_outcomes() -> None:
    collected = (
        "tests/test_sample.py::test_pass[value]",
        "tests/test_sample.py::TestCase::test_failure",
        "tests/test_sample.py::test_error",
    )
    junit_raw = b"""\
<testsuite>
  <testcase file="tests/test_sample.py" classname="tests.test_sample" name="test_pass[value]" />
  <testcase file="tests/test_sample.py" classname="tests.test_sample.TestCase" name="test_failure"><failure message="boom">body</failure></testcase>
  <testcase file="tests/test_sample.py" classname="tests.test_sample" name="test_error"><error message="broken">trace</error></testcase>
</testsuite>
"""
    cases = _parse_junit_testcases(junit_raw, collected)
    assert {case["nodeid"]: case["outcome"] for case in cases} == {
        "tests/test_sample.py::test_pass[value]": "pass",
        "tests/test_sample.py::TestCase::test_failure": "failure",
        "tests/test_sample.py::test_error": "error",
    }

    with pytest.raises(ValueError, match="uniquely map"):
        _parse_junit_testcases(
            b'<testsuite><testcase file="tests/test_sample.py" name="test_same" /></testsuite>',
            (
                "tests/test_sample.py::TestOne::test_same",
                "tests/test_sample.py::TestTwo::test_same",
            ),
        )


def test_production_loader_includes_accepted_s11b_collected_snapshots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence_root = tmp_path / "s11c"
    evidence_root.mkdir()
    for file_name in (
        "retired-failure-ledger-v1.json",
        "disposition-overlay-v1.json",
        "guarded-partitions-receipt.json",
        "guarded-execution-provenance-v1.json",
        "predecessor-reruns-v1.json",
        "predecessor-reruns-v2.json",
        "disposable-postgres-target-receipt.json",
    ):
        payload = {"runs": []} if file_name.startswith("retired") else {}
        (evidence_root / file_name).write_bytes(_json_bytes(payload))
    accepted_paths = dict(_ACCEPTED_S11B_COLLECTED)
    monkeypatch.setitem(globals(), "_EVIDENCE_ROOT", evidence_root)
    monkeypatch.setitem(globals(), "_ACCEPTED_S11B_COLLECTED", accepted_paths)

    evidence = load_s11c_acceptance_evidence()

    snapshot_raw = evidence.get("accepted_s11b_collected_raw_by_run")
    assert snapshot_raw == {
        run_id: path.read_bytes() for run_id, path in accepted_paths.items()
    }
    assert isinstance(snapshot_raw, dict)
    assert len(snapshot_raw) == 2
    binding_authority = _PRODUCTION_AUTHORITY.get("accepted_s11b_collected")
    assert isinstance(binding_authority, dict)
    for run_id, path in accepted_paths.items():
        binding = binding_authority.get(run_id)
        raw = snapshot_raw.get(run_id)
        assert isinstance(binding, dict)
        assert isinstance(raw, bytes)
        assert binding["path"] == path.relative_to(_REPOSITORY_ROOT).as_posix()
        assert binding["sha256"] == _sha256_raw_bytes(raw)


def _prepare_production_loader_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    write_declared: bool,
) -> tuple[Path, bytes, bytes]:
    repository_root = tmp_path / "repo"
    evidence_root = (
        repository_root / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c"
    )
    collected_root = evidence_root / "collected"
    junit_root = evidence_root / "junit"
    focused_root = evidence_root / "focused"
    for root in (collected_root, junit_root, focused_root):
        root.mkdir(parents=True)

    declared_collected = b"tests/test_declared.py::test_declared\n"
    declared_junit = b"""\
<testsuite><testcase file="tests/test_declared.py" classname="tests.test_declared" name="test_declared" /></testsuite>
"""
    if write_declared:
        (collected_root / "declared.txt").write_bytes(declared_collected)
        (junit_root / "declared.xml").write_bytes(declared_junit)
    (collected_root / "undeclared-sibling.txt").write_bytes(
        b"tests/test_sibling.py::test_sibling\n"
    )
    (junit_root / "undeclared-sibling.xml").write_bytes(
        b'<testsuite><testcase file="tests/test_sibling.py" name="test_sibling" /></testsuite>'
    )
    (focused_root / "collected.txt").write_bytes(
        b"tests/test_focused.py::test_focused\n"
    )
    (focused_root / "junit.xml").write_bytes(
        b'<testsuite><testcase file="tests/test_focused.py" name="test_focused" /></testsuite>'
    )

    ledger = {
        "runs": [
            {
                "collected_nodeids_path": (
                    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
                    "s11c/collected/declared.txt"
                ),
                "junit_xml_path": (
                    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
                    "s11c/junit/declared.xml"
                ),
                "run_id": "declared",
            }
        ]
    }
    ledger_path = evidence_root / "retired-failure-ledger-v1.json"
    overlay_path = evidence_root / "disposition-overlay-v1.json"
    guard_receipt_path = evidence_root / "guarded-partitions-receipt.json"
    guard_provenance_path = evidence_root / "guarded-execution-provenance-v1.json"
    predecessor_v1_path = evidence_root / "predecessor-reruns-v1.json"
    predecessor_v2_path = evidence_root / "predecessor-reruns-v2.json"
    disposable_receipt_path = evidence_root / "disposable-postgres-target-receipt.json"
    ledger_path.write_bytes(_json_bytes(ledger))
    overlay_path.write_bytes(b"{}")
    guard_receipt_path.write_bytes(b"{}")
    guard_provenance_path.write_bytes(b"{}")
    predecessor_v1_path.write_bytes(b"{}")
    predecessor_v2_path.write_bytes(b"{}")
    disposable_receipt_path.write_bytes(b"{}")

    receipt_path = repository_root / "accepted-receipt.json"
    inventory_path = repository_root / "inventory.json"
    receipt_path.write_bytes(b"{}")
    inventory_path.write_bytes(b"{}")
    accepted_collected_path = repository_root / "accepted-collected.txt"
    accepted_collected_path.write_bytes(b"tests/test_accepted.py::test_accepted\n")

    monkeypatch.setitem(globals(), "_REPOSITORY_ROOT", repository_root)
    monkeypatch.setitem(globals(), "_EVIDENCE_ROOT", evidence_root)
    monkeypatch.setitem(globals(), "_ACCEPTED_S11B_RECEIPT", receipt_path)
    monkeypatch.setitem(globals(), "_INVENTORY", inventory_path)
    monkeypatch.setitem(
        globals(), "_ACCEPTED_S11B_COLLECTED", {"accepted": accepted_collected_path}
    )
    return evidence_root, declared_collected, declared_junit


def test_production_loader_reads_only_ledger_declared_run_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _evidence_root, declared_collected, declared_junit = (
        _prepare_production_loader_fixture(
            monkeypatch,
            tmp_path,
            write_declared=True,
        )
    )

    evidence = load_s11c_acceptance_evidence()

    assert evidence["collected_raw_by_run"] == {"declared": declared_collected}
    assert evidence["junit_raw_by_run"] == {"declared": declared_junit}


def test_production_loader_missing_declared_artifact_uses_exact_sentinel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _prepare_production_loader_fixture(
        monkeypatch,
        tmp_path,
        write_declared=False,
    )
    monkeypatch.setattr(pytest, "xfail", lambda reason: None)

    with pytest.raises(_MissingS11CAcceptanceEvidence, match=f"^{_MISSING_SENTINEL}$"):
        load_s11c_acceptance_evidence()


@pytest.mark.parametrize(
    "missing_name",
    (
        "predecessor-reruns-v1.json",
        "predecessor-reruns-v2.json",
        "guarded-execution-provenance-v1.json",
        "disposable-postgres-target-receipt.json",
    ),
)
def test_production_loader_missing_fixed_receipt_uses_exact_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing_name: str,
) -> None:
    evidence_root, _collected, _junit = _prepare_production_loader_fixture(
        monkeypatch,
        tmp_path,
        write_declared=True,
    )
    (evidence_root / missing_name).unlink()
    monkeypatch.setattr(pytest, "xfail", lambda reason: None)

    with pytest.raises(_MissingS11CAcceptanceEvidence, match=f"^{_MISSING_SENTINEL}$"):
        load_s11c_acceptance_evidence()


def test_production_s11b_admin_quarantine_owner_set_is_exact() -> None:
    evidence = {
        "accepted_s11b_collected_raw_by_run": {
            run_id: path.read_bytes()
            for run_id, path in _ACCEPTED_S11B_COLLECTED.items()
        }
    }
    receipt = _load_json_object(
        _ACCEPTED_S11B_RECEIPT.read_bytes(), label="Accepted S11B receipt"
    )

    owners = _required_owner_nodeids_by_family(
        evidence,
        receipt,
        _PRODUCTION_AUTHORITY,
    )

    assert owners["s11b_admin_quarantine"] == frozenset(
        {
            "tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers",
            "tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers",
            "tests/test_canonical_v2_operations_api.py::test_canonical_v2_operations_api_is_bounded_read_only_and_quarantined",
            "tests/test_smoke_canonical_v2_candidate.py::test_smoke_requires_explicit_release_and_reuses_one_cookie_session",
        }
    )


def test_helper_validator_accepts_complete_synthetic_evidence() -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    ledger = json.loads(evidence["ledger_raw"])
    guard_receipt = json.loads(evidence["guarded_partitions_receipt_raw"])
    command_basetemp = next(
        token
        for token in ledger["runs"][0]["command"]
        if token.startswith("--basetemp=")
    ).split("=", 1)[1]
    effective_basetemp = guard_receipt["guard_preflight"]["pytest_temp_roots"][
        _SYNTHETIC_ADMIN_RUN
    ]["run"]
    assert command_basetemp != effective_basetemp

    _validate_evidence_bundle(evidence, authority=authority)


def test_helper_validator_accepts_frozen_evidence_after_checkout_relocation() -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    evidence_relative = Path(authority["evidence_root"]).relative_to(
        Path(authority["repository_root"])
    )
    relocated_root = Path("/relocated/canonical-v2-checkout")
    authority["repository_root"] = str(relocated_root)
    authority["evidence_root"] = str(relocated_root / evidence_relative)

    _validate_evidence_bundle(evidence, authority=authority)


def test_helper_validator_does_not_resolve_historical_paths_on_live_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, authority = _synthetic_acceptance_evidence()

    def reject_live_resolution(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("historical evidence paths must be compared lexically")

    monkeypatch.setattr(Path, "resolve", reject_live_resolution)

    _validate_evidence_bundle(evidence, authority=authority)


def test_helper_validator_rejects_nonpassing_non_guarded_task11_2_run() -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    _make_non_guarded_task11_2_run_skipped(evidence)

    with pytest.raises(ValueError, match="non-guarded Task 11.2 run"):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    ("raw_key", "mutation", "message"),
    (
        (
            "predecessor_reruns_v2_raw",
            lambda receipt: receipt.update({"accepted_s11b_receipt_sha256": "0" * 64}),
            "predecessor rerun Accepted S11B",
        ),
        (
            "disposable_postgres_receipt_raw",
            lambda receipt: receipt.update({"status": "incomplete"}),
            "disposable PostgreSQL receipt",
        ),
    ),
)
def test_helper_validator_rejects_required_receipt_tamper(
    raw_key: str, mutation: Any, message: str
) -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    _mutate_json(evidence, raw_key, mutation)

    with pytest.raises(ValueError, match=message):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    ("raw_key", "mutation", "message"),
    (
        (
            "predecessor_reruns_v2_raw",
            lambda receipt: receipt["runs"][0].pop("cwd"),
            "predecessor rerun repository cwd",
        ),
        (
            "predecessor_reruns_v2_raw",
            lambda receipt: receipt["runs"][0].update({"cwd": "/repo/apps"}),
            "predecessor rerun repository cwd",
        ),
        (
            "guarded_execution_provenance_raw",
            lambda receipt: receipt["runs"][0].pop("derived_started_at_utc"),
            "guarded execution UTC window",
        ),
        (
            "guarded_execution_provenance_raw",
            lambda receipt: receipt["runs"][0].update(
                {"derived_finished_at_utc": "2026-07-21T00:00:03.500000Z"}
            ),
            "guarded execution UTC window",
        ),
        (
            "guarded_execution_provenance_raw",
            lambda receipt: receipt["source_artifacts"][
                "retired_failure_ledger"
            ].update({"sha256": "0" * 64}),
            "guarded execution source hash",
        ),
        (
            "guarded_execution_provenance_raw",
            lambda receipt: receipt["runs"][0].update({"junit_xml_sha256": "0" * 64}),
            "guarded execution source hash",
        ),
    ),
)
def test_helper_validator_rejects_execution_trace_tampering(
    raw_key: str, mutation: Any, message: str
) -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    _mutate_json(evidence, raw_key, mutation)

    with pytest.raises(ValueError, match=message):
        _validate_evidence_bundle(evidence, authority=authority)


def test_helper_validator_rejects_guard_receipt_raw_byte_tamper() -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    evidence["guarded_partitions_receipt_raw"] += b" "

    with pytest.raises(ValueError, match="guarded partitions receipt SHA-256"):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (_put_guard_root_outside_owned_root, "owned_temp_root"),
        (_drop_guard_run_root, "guard run set"),
        (_make_guard_child_nonterminal, "terminal child receipt"),
        (_make_guard_child_configured, "terminal child receipt"),
        (_make_guard_cleanup_false, "guard cleanup"),
    ),
)
def test_helper_validator_rejects_guard_receipt_content_tamper(
    mutation: Any, message: str
) -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    _rewrite_guard_receipt(evidence, mutation, rebind_sha256=True)

    with pytest.raises(ValueError, match=message):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    ("base_disposition", "retired_disposition"),
    (
        ("replaced", "retired_replaced"),
        ("reference_only", "retired_reference_only"),
    ),
)
def test_helper_validator_accepts_direct_final_base_inventory_retirement(
    base_disposition: str, retired_disposition: str
) -> None:
    evidence, authority = _synthetic_acceptance_evidence(
        base_disposition=base_disposition,
        retired_disposition=retired_disposition,
    )

    _validate_evidence_bundle(evidence, authority=authority)


def test_helper_validator_rejects_direct_base_disposition_mismatch() -> None:
    evidence, authority = _synthetic_acceptance_evidence(
        base_disposition="replaced",
        retired_disposition="retired_reference_only",
    )

    with pytest.raises(ValueError, match="retired ledger disposition"):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    "owner_nodeids",
    (
        [],
        [_SYNTHETIC_REPLACEMENT_NODEID, _SYNTHETIC_REPLACEMENT_NODEID],
        [" not-an-exact-nodeid "],
    ),
)
def test_helper_validator_rejects_invalid_direct_base_retirement_owners(
    owner_nodeids: list[str],
) -> None:
    evidence, authority = _synthetic_acceptance_evidence(
        base_disposition="replaced",
        retired_disposition="retired_replaced",
    )
    _mutate_json(
        evidence,
        "ledger_raw",
        lambda value: value["failures"][0].update(
            {"replacement_owner_nodeids": owner_nodeids}
        ),
    )

    with pytest.raises(ValueError, match="replacement_owner_nodeids"):
        _validate_evidence_bundle(evidence, authority=authority)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (_tamper_receipt_raw, "receipt raw-byte SHA-256"),
        (_tamper_inventory_raw, "inventory raw-byte SHA-256"),
        (_drop_overlay_entry, "overlay key coverage"),
        (_use_invalid_overlay_disposition, "overlay disposition"),
        (_empty_replacement_owner, "replacement_owner_nodeids"),
        (_drop_collected_nodeid, "collected-nodeids SHA-256"),
        (_drop_ledger_row, "failure/ledger bijection"),
        (_duplicate_ledger_row, "duplicate ledger"),
        (_change_ledger_signature, "failure signature"),
        (_make_replacement_owner_nonpassing, "replacement owner must pass"),
        (_change_unrelated_signature_from_baseline, "Accepted S11B baseline"),
        (_use_forbidden_scope_owner, "unrelated_preexisting forbidden owner"),
        (_use_missing_scope_owner, "scope_owner_nodeid must pass"),
        (_drop_evidence_family, "evidence-family labels"),
        (_claim_all_families_with_unrelated_pass, "required owner nodeids"),
        (_mismatch_command_basetemp_root, "basetemp root"),
        (_mismatch_repository_root, "frozen repo root"),
        (_disguise_protected_failure_as_retired, "protected failure"),
        (_add_overlay_root_nesting, "overlay exact keys"),
        (_add_overlay_inventory_id, "overlay entry exact keys"),
        (_drop_overlay_reason, "overlay reason"),
        (_swallow_failure_exit_code, "exit_code/JUnit outcome"),
    ),
)
def test_helper_validator_rejects_integrity_tampering(
    mutation: Any, message: str
) -> None:
    evidence, authority = _synthetic_acceptance_evidence()
    mutation(evidence, authority)

    with pytest.raises(ValueError, match=message):
        _validate_evidence_bundle(evidence, authority=authority)
