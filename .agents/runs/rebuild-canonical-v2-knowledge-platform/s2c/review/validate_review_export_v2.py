"""Independent, fail-closed validation for Canonical V2 human-review exports."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any


__all__ = (
    "ReviewExportValidationError",
    "ValidatedReviewCounts",
    "ValidatedReviewExportV2",
    "validate_review_export_v2",
)


_EXPORT_SCHEMA = "canonical-v2-human-review-export-v2"
_VALIDATED_SCHEMA = "canonical-v2-validated-review-export-v2"
_PACKET_SCHEMA = "canonical-v2-human-review-packet-v1"
_WORKLOAD_SCHEMA = "canonical-v2-human-review-workload-v2"
_POLICY_SCHEMA = "canonical-v2-human-calibration-policy-v2"
_PROVENANCE_SCHEMA = "canonical-v2-calibration-provenance-v1"
_REQUEST_SCHEMA = "canonical-v2-human-calibration-request-v2"
_STIMULUS_SCHEMA = "canonical-v2-human-calibration-stimulus-v1"
_STIMULUS_SET_SCHEMA = "canonical-v2-human-calibration-stimulus-set-v1"
_RESPONSE_SCHEMA = "canonical-v2-human-calibration-judge-decision-v2"
_AUTHORIZATION_SCHEMA = "judge-authorization-v2"
_RENDERER_SCHEMA = "canonical-v2-human-review-renderer-v1"
_S2C_MANIFEST_SCHEMA = "canonical-v2-s2c-corpus-manifest-v1"
_CALIBRATION_POLICY_ID = "single-human-global-stratified-v2"
_JUDGE_POLICY_ID = "evidence-bounded-judge-v1"

_POLICY_NAME = "calibration-policy-v2.json"
_BANK_NAME = "calibration-observation-bank-v2.jsonl"
_PROVENANCE_NAME = "calibration-observation-bank-v2-provenance.json"
_S2C_ROOT = Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c")
_S2C_FILES = {
    "contracts": _S2C_ROOT / "claim-level-corpus-v1.jsonl",
    "accounting": _S2C_ROOT / "case-accounting-v1.jsonl",
    "snapshots": _S2C_ROOT / "source-snapshots-v1.jsonl",
    "manifest": _S2C_ROOT / "claim-level-corpus-manifest-v1.json",
}
_RENDERER_ROOT = Path("apps/admin-console/backend/static")
_RENDERER_FILES = (
    "review.html",
    "review.css",
    "review.js",
    "review_mutation_coordinator.js",
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
_EXPECTED_POLICY = {
    "schema_version": _POLICY_SCHEMA,
    "policy_id": _CALIBRATION_POLICY_ID,
    "reviewer_count": 1,
    "sample_count": 60,
    "strata": _EXPECTED_STRATA,
    "minimum_agreement": 0.8,
    "minimum_supported_labels": 10,
    "minimum_unsupported_labels": 10,
    "minimum_unsupported_critical_probes": 5,
    "maximum_critical_false_accepts": 0,
}
_FROZEN_ARTIFACT_IDENTITIES = {
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
_ALLOWED_DECISIONS = {
    "contract": {"approved", "needs_change", "unable_to_determine"},
    "exclusion": {
        "accept_exclusion",
        "require_evidence",
        "unable_to_determine",
    },
    "calibration": {"supported", "unsupported", "unable_to_determine"},
}
_ACCEPTING_DECISIONS = {
    "contract": {"approved"},
    "exclusion": {"accept_exclusion"},
    "calibration": {"supported", "unsupported"},
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_STAFF_ID = re.compile(r"^[a-z0-9._-]{2,64}$", flags=re.ASCII)
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", flags=re.ASCII)
_PROVIDER_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", flags=re.ASCII)
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$", flags=re.ASCII)
_FORBIDDEN_LABEL_KEYS = {
    "expected_label",
    "gold_label",
    "ground_truth",
    "human_label",
    "judge_decision",
    "model_judgment",
    "oracle_label",
}
_TOP_KEYS = {
    "schema_version",
    "export_id",
    "mode",
    "acceptance_eligible",
    "evidence_class",
    "task_2_8_eligible",
    "created_at",
    "artifact_identity",
    "round",
    "accounting",
    "decision_events",
    "contract_decisions",
    "exclusion_decisions",
    "calibration_labels",
    "judge",
    "gates",
    "content_sha256",
}
_EVENT_KEYS = {
    "event_id",
    "task_id",
    "task_kind",
    "revision",
    "supersedes_event_id",
    "decision",
    "rationale",
    "canonical_payload",
    "payload_sha256",
    "idempotency_sha256",
    "record_sha256",
    "submitted_at",
}
_PROJECTION_KEYS = {
    "task_id",
    "decision",
    "revision",
    "event_id",
    "payload_sha256",
}


class ReviewExportValidationError(Exception):
    """Stable validation failure that never includes input paths or payloads."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedReviewCounts:
    contract_reviews: int
    exclusion_reviews: int
    calibration_probes: int
    human_actions: int


@dataclass(frozen=True, slots=True)
class ValidatedReviewExportV2:
    schema_version: str
    export_id: str
    round_id: str
    mode: str
    evidence_class: str
    acceptance_eligible: bool
    task_2_8_eligible: bool
    policy_id: str
    workload_counts: ValidatedReviewCounts
    artifact_identity: Mapping[str, object]
    canonical_export_bytes: bytes
    raw_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class _Artifacts:
    workload: dict[str, Any]
    policy: dict[str, Any]
    artifact_identity: dict[str, Any]
    task_order: tuple[str, ...]
    tasks: Mapping[str, tuple[str, dict[str, Any]]]


def _fail(code: str) -> None:
    raise ReviewExportValidationError(code)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = child
    return value


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
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("artifact_mismatch")
    return hashlib.sha256(raw).hexdigest()


def _parse_json_bytes(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return value


def _load_json(path: Path, code: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail(code)
    return _parse_json_bytes(raw, code), raw


def _load_jsonl(path: Path, code: str) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        _fail(code)
    rows: list[dict[str, Any]] = []
    try:
        lines = raw.splitlines(keepends=True)
        if not lines or any(not line.endswith(b"\n") for line in lines):
            raise ValueError("line endings")
        for line in lines:
            row = _parse_json_bytes(line[:-1], code)
            if line != _canonical_bytes(row) + b"\n":
                raise ValueError("noncanonical row")
            rows.append(row)
    except ReviewExportValidationError:
        raise
    except (TypeError, ValueError):
        _fail(code)
    return rows, raw


def _exact_dict(value: object, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _boolean(value: object, code: str) -> bool:
    if type(value) is not bool:
        _fail(code)
    return value


def _integer(value: object, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(code)
    return value


def _timestamp(value: object, code: str) -> str:
    text = _string(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None:
        _fail(code)
    return text


def _require_self_hash(value: dict[str, Any], code: str) -> str:
    claimed = _sha(value.get("content_sha256"), code)
    content = {key: child for key, child in value.items() if key != "content_sha256"}
    if claimed != _canonical_sha256(content):
        _fail(code)
    return claimed


def _safe_source_path(source_root: Path, relative: str) -> Path:
    try:
        root = source_root.resolve(strict=True)
        candidate = (root / relative).resolve(strict=True)
    except OSError:
        _fail("artifact_mismatch")
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        _fail("artifact_mismatch")
    return candidate


def _walk_forbidden_labels(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_LABEL_KEYS:
                _fail("workload_mismatch")
            _walk_forbidden_labels(child)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden_labels(child)


def _audit_projection(row: dict[str, Any]) -> dict[str, Any]:
    requirement = row.get("requirement")
    if not isinstance(requirement, dict):
        _fail("workload_mismatch")
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


def _stimulus(row: dict[str, Any]) -> dict[str, Any]:
    requirement = row.get("requirement")
    if not isinstance(requirement, dict):
        _fail("workload_mismatch")
    return {
        "schema_version": _STIMULUS_SCHEMA,
        "sample_id": row.get("sample_id"),
        "as_of": row.get("as_of"),
        "requirement": {
            key: value for key, value in requirement.items() if key != "fixture_locator"
        },
        "candidate_observation": row.get("candidate_observation"),
        "evidence_snapshots": row.get("evidence_snapshots"),
    }


def _validate_s2c_sources(
    *, packet: dict[str, Any], source_root: Path
) -> dict[str, Path]:
    paths = {
        name: _safe_source_path(source_root, str(relative))
        for name, relative in _S2C_FILES.items()
    }
    manifest, _ = _load_json(paths["manifest"], "artifact_mismatch")
    contracts, _ = _load_jsonl(paths["contracts"], "artifact_mismatch")
    accounting, _ = _load_jsonl(paths["accounting"], "artifact_mismatch")
    snapshots, _ = _load_jsonl(paths["snapshots"], "artifact_mismatch")
    source_identity = packet.get("source_identity")
    if not isinstance(source_identity, dict):
        _fail("artifact_mismatch")
    expected_raw = {
        "contracts": source_identity.get("corpus_file_sha256"),
        "accounting": source_identity.get("accounting_file_sha256"),
        "snapshots": source_identity.get("snapshot_file_sha256"),
        "manifest": source_identity.get("manifest_file_sha256"),
    }
    if any(
        _raw_sha256(paths[name]) != expected for name, expected in expected_raw.items()
    ):
        _fail("artifact_mismatch")
    if (
        manifest.get("schema_version") != _S2C_MANIFEST_SCHEMA
        or _require_self_hash(manifest, "artifact_mismatch")
        != source_identity.get("manifest_content_sha256")
        or manifest.get("corpus_id") != source_identity.get("corpus_id")
        or manifest.get("contract_version") != source_identity.get("contract_version")
        or manifest.get("case_contract_schema_version")
        != source_identity.get("case_contract_schema_version")
        or manifest.get("contract_case_count") != 52
        or manifest.get("snapshot_count") != 53
    ):
        _fail("artifact_mismatch")
    outputs = manifest.get("outputs")
    expected_outputs = {
        "claim-level-corpus-v1.jsonl": {"sha256": expected_raw["contracts"]},
        "case-accounting-v1.jsonl": {"sha256": expected_raw["accounting"]},
        "source-snapshots-v1.jsonl": {"sha256": expected_raw["snapshots"]},
    }
    if outputs != expected_outputs:
        _fail("artifact_mismatch")
    if len(contracts) != 52 or len(accounting) != 52 or len(snapshots) != 53:
        _fail("artifact_mismatch")

    contracts_by_id: dict[str, dict[str, Any]] = {}
    for row in contracts:
        case_id = row.get("case_id")
        if (
            not isinstance(case_id, str)
            or case_id in contracts_by_id
            or _require_self_hash(row, "artifact_mismatch") != row.get("content_sha256")
        ):
            _fail("artifact_mismatch")
        contracts_by_id[case_id] = row
    accounting_by_id: dict[str, dict[str, Any]] = {}
    for row in accounting:
        case_id = row.get("contract_case_id")
        if (
            not isinstance(case_id, str)
            or case_id in accounting_by_id
            or _require_self_hash(row, "artifact_mismatch") != row.get("content_sha256")
        ):
            _fail("artifact_mismatch")
        accounting_by_id[case_id] = row
    snapshots_by_id: dict[str, dict[str, Any]] = {}
    for row in snapshots:
        snapshot_id = row.get("snapshot_id")
        payload = row.get("payload")
        if row.get("payload_kind") == "canonical_json" and isinstance(payload, dict):
            payload_sha256 = _canonical_sha256(payload)
        elif row.get("payload_kind") == "utf8_text" and isinstance(payload, str):
            payload_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        else:
            _fail("artifact_mismatch")
        record = {key: value for key, value in row.items() if key != "record_sha256"}
        if (
            not isinstance(snapshot_id, str)
            or snapshot_id in snapshots_by_id
            or row.get("content_sha256") != payload_sha256
            or row.get("record_sha256") != _canonical_sha256(record)
        ):
            _fail("artifact_mismatch")
        snapshots_by_id[snapshot_id] = row

    reviews = packet.get("review_candidates")
    exclusions = packet.get("exclusion_candidates")
    if not isinstance(reviews, list) or not isinstance(exclusions, list):
        _fail("artifact_mismatch")
    packet_ids: set[str] = set()
    for row, state in [
        *((item, "pending_user_review") for item in reviews),
        *((item, "blocked_missing_evidence") for item in exclusions),
    ]:
        if not isinstance(row, dict):
            _fail("artifact_mismatch")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id in packet_ids:
            _fail("artifact_mismatch")
        packet_ids.add(case_id)
        contract = contracts_by_id.get(case_id)
        account = accounting_by_id.get(case_id)
        snapshot_ids = row.get("snapshot_ids")
        if (
            contract is None
            or account is None
            or not isinstance(snapshot_ids, list)
            or any(snapshot_id not in snapshots_by_id for snapshot_id in snapshot_ids)
            or contract.get("review_state") != state
            or account.get("review_state") != state
            or row.get("contract_content_sha256") != contract.get("content_sha256")
            or row.get("source_case_id") != contract.get("source_case_id")
            or row.get("source_case_id") != account.get("source_case_id")
            or row.get("family") != account.get("family")
            or account.get("contract_content_sha256") != contract.get("content_sha256")
        ):
            _fail("artifact_mismatch")
    if packet_ids != set(contracts_by_id) or packet_ids != set(accounting_by_id):
        _fail("artifact_mismatch")
    return paths


def _load_artifacts(
    *, packet_path: Path, workload_path: Path, source_root: Path
) -> _Artifacts:
    packet, packet_raw = _load_json(packet_path, "artifact_mismatch")
    workload, workload_raw = _load_json(workload_path, "artifact_mismatch")
    policy_path = workload_path.parent / _POLICY_NAME
    bank_path = workload_path.parent / _BANK_NAME
    provenance_path = workload_path.parent / _PROVENANCE_NAME
    policy, policy_raw = _load_json(policy_path, "artifact_mismatch")
    bank, bank_raw = _load_jsonl(bank_path, "artifact_mismatch")
    provenance, provenance_raw = _load_json(provenance_path, "artifact_mismatch")

    if packet.get("schema_version") != _PACKET_SCHEMA:
        _fail("artifact_mismatch")
    packet_content = _require_self_hash(packet, "artifact_mismatch")
    if workload.get("schema_version") != _WORKLOAD_SCHEMA:
        _fail("workload_mismatch")
    workload_content = _require_self_hash(workload, "workload_mismatch")
    if policy != _EXPECTED_POLICY or workload.get("policy") != _EXPECTED_POLICY:
        _fail("workload_mismatch")
    if provenance.get("schema_version") != _PROVENANCE_SCHEMA:
        _fail("artifact_mismatch")
    provenance_content = _require_self_hash(provenance, "artifact_mismatch")
    actual_frozen_identities = {
        "packet": (hashlib.sha256(packet_raw).hexdigest(), packet_content),
        "workload": (hashlib.sha256(workload_raw).hexdigest(), workload_content),
        "policy": (hashlib.sha256(policy_raw).hexdigest(), _canonical_sha256(policy)),
        "bank": (hashlib.sha256(bank_raw).hexdigest(), _canonical_sha256(bank)),
        "provenance": (
            hashlib.sha256(provenance_raw).hexdigest(),
            provenance_content,
        ),
    }
    if actual_frozen_identities != _FROZEN_ARTIFACT_IDENTITIES:
        _fail("artifact_mismatch")

    if workload.get("packet_identity") != {
        "schema_version": _PACKET_SCHEMA,
        "raw_sha256": hashlib.sha256(packet_raw).hexdigest(),
        "content_sha256": packet_content,
    }:
        _fail("artifact_mismatch")
    if workload.get("policy_identity") != {
        "raw_sha256": hashlib.sha256(policy_raw).hexdigest(),
        "content_sha256": _canonical_sha256(policy),
    }:
        _fail("artifact_mismatch")
    if workload.get("bank_identity") != {
        "raw_sha256": hashlib.sha256(bank_raw).hexdigest(),
        "content_sha256": _canonical_sha256(bank),
        "row_count": 60,
    }:
        _fail("artifact_mismatch")
    if workload.get("provenance_identity") != {
        "schema_version": _PROVENANCE_SCHEMA,
        "raw_sha256": hashlib.sha256(provenance_raw).hexdigest(),
        "content_sha256": provenance_content,
    }:
        _fail("artifact_mismatch")

    counts = workload.get("counts")
    contract_rows = workload.get("contract_reviews")
    exclusion_rows = workload.get("exclusion_reviews")
    calibration_rows = workload.get("calibration_probes")
    if counts != _EXPECTED_COUNTS:
        _fail("accounting_mismatch")
    if (
        not isinstance(contract_rows, list)
        or len(contract_rows) != 29
        or not isinstance(exclusion_rows, list)
        or len(exclusion_rows) != 23
        or not isinstance(calibration_rows, list)
        or len(calibration_rows) != 60
        or contract_rows != packet.get("review_candidates")
        or exclusion_rows != packet.get("exclusion_candidates")
        or calibration_rows != bank
    ):
        _fail("workload_mismatch")
    _walk_forbidden_labels(workload)

    provenance_groups = provenance.get("source_groups")
    projections = provenance.get("projection_sha256s")
    sample_order = provenance.get("sample_ids")
    if (
        not isinstance(provenance_groups, list)
        or not isinstance(projections, dict)
        or not isinstance(sample_order, list)
    ):
        _fail("workload_mismatch")
    bindings: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    for group in provenance_groups:
        if not isinstance(group, dict) or set(group) != {
            "path",
            "samples",
            "source_sha256",
            "test_name",
        }:
            _fail("workload_mismatch")
        samples = group.get("samples")
        if not isinstance(samples, list):
            _fail("workload_mismatch")
        for sample in samples:
            if not isinstance(sample, dict) or set(sample) != {
                "sample_id",
                "selectors",
            }:
                _fail("workload_mismatch")
            sample_id = sample.get("sample_id")
            selectors = sample.get("selectors")
            if (
                not isinstance(sample_id, str)
                or sample_id in bindings
                or not isinstance(selectors, list)
                or not selectors
                or not all(isinstance(item, str) for item in selectors)
            ):
                _fail("workload_mismatch")
            bindings[sample_id] = (
                str(group.get("path")),
                str(group.get("source_sha256")),
                str(group.get("test_name")),
                tuple(selectors),
            )

    sample_ids: list[str] = []
    request_hashes: list[str] = []
    strata: Counter[str] = Counter()
    source_sha256s: dict[str, str] = {}
    for row in calibration_rows:
        if not isinstance(row, dict) or row.get("schema_version") != _REQUEST_SCHEMA:
            _fail("workload_mismatch")
        sample_id = row.get("sample_id")
        request_sha256 = row.get("request_sha256")
        stratum = row.get("stratum")
        source = row.get("source_identity")
        requirement = row.get("requirement")
        if (
            not isinstance(sample_id, str)
            or not isinstance(request_sha256, str)
            or not isinstance(stratum, str)
            or not isinstance(source, dict)
            or not isinstance(requirement, dict)
            or row.get("policy_id") != _CALIBRATION_POLICY_ID
            or row.get("requirement_kind") != _EXPECTED_REQUIREMENT_KINDS.get(stratum)
            or request_sha256
            != _canonical_sha256(
                {key: value for key, value in row.items() if key != "request_sha256"}
            )
        ):
            _fail("workload_mismatch")
        path_value = source.get("path")
        source_sha = source.get("source_sha256")
        test_name = source.get("test_name")
        locator = requirement.get("fixture_locator")
        if (
            not isinstance(path_value, str)
            or not isinstance(source_sha, str)
            or not isinstance(test_name, str)
            or not isinstance(locator, dict)
            or locator.get("function") != test_name
            or not isinstance(locator.get("selectors"), list)
        ):
            _fail("workload_mismatch")
        source_path = _safe_source_path(source_root, path_value)
        if _raw_sha256(source_path) != source_sha:
            _fail("artifact_mismatch")
        prior = source_sha256s.setdefault(path_value, source_sha)
        if prior != source_sha:
            _fail("workload_mismatch")
        binding = (path_value, source_sha, test_name, tuple(locator["selectors"]))
        if bindings.get(sample_id) != binding:
            _fail("workload_mismatch")
        if projections.get(sample_id) != _canonical_sha256(_audit_projection(row)):
            _fail("workload_mismatch")
        sample_ids.append(sample_id)
        request_hashes.append(request_sha256)
        strata[stratum] += 1
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(request_hashes) != len(set(request_hashes))
        or sample_order != sample_ids
        or list(bindings) != sample_ids
        or set(projections) != set(sample_ids)
        or dict(strata) != _EXPECTED_STRATA
    ):
        _fail("workload_mismatch")

    s2c_paths = _validate_s2c_sources(packet=packet, source_root=source_root)
    renderer_paths = {
        name: _safe_source_path(source_root, str(_RENDERER_ROOT / name))
        for name in _RENDERER_FILES
    }
    renderer_hashes = {name: _raw_sha256(path) for name, path in renderer_paths.items()}
    artifact_identity = {
        "packet_raw_sha256": hashlib.sha256(packet_raw).hexdigest(),
        "packet_content_sha256": packet_content,
        "workload_raw_sha256": hashlib.sha256(workload_raw).hexdigest(),
        "workload_content_sha256": workload_content,
        "policy_raw_sha256": hashlib.sha256(policy_raw).hexdigest(),
        "policy_content_sha256": _canonical_sha256(policy),
        "bank_raw_sha256": hashlib.sha256(bank_raw).hexdigest(),
        "bank_content_sha256": _canonical_sha256(bank),
        "provenance_raw_sha256": hashlib.sha256(provenance_raw).hexdigest(),
        "provenance_content_sha256": provenance_content,
        "s2c_manifest_raw_sha256": _raw_sha256(s2c_paths["manifest"]),
        "s2c_manifest_content_sha256": packet["source_identity"][
            "manifest_content_sha256"
        ],
        "s2c_corpus_raw_sha256": _raw_sha256(s2c_paths["contracts"]),
        "s2c_accounting_raw_sha256": _raw_sha256(s2c_paths["accounting"]),
        "s2c_snapshots_raw_sha256": _raw_sha256(s2c_paths["snapshots"]),
        "calibration_stimulus_set_sha256": _canonical_sha256(
            {
                "schema_version": _STIMULUS_SET_SCHEMA,
                "stimuli": [_stimulus(row) for row in calibration_rows],
            }
        ),
        "renderer_schema_version": _RENDERER_SCHEMA,
        "review_html_raw_sha256": renderer_hashes["review.html"],
        "review_css_raw_sha256": renderer_hashes["review.css"],
        "review_js_raw_sha256": renderer_hashes["review.js"],
        "review_mutation_coordinator_js_raw_sha256": renderer_hashes[
            "review_mutation_coordinator.js"
        ],
        "renderer_content_sha256": _canonical_sha256(
            {"schema_version": _RENDERER_SCHEMA, "assets": renderer_hashes}
        ),
        "source_sha256s": dict(sorted(source_sha256s.items())),
    }

    tasks: dict[str, tuple[str, dict[str, Any]]] = {}
    task_order: list[str] = []
    for kind, rows, id_field in (
        ("contract", contract_rows, "case_id"),
        ("exclusion", exclusion_rows, "case_id"),
        ("calibration", calibration_rows, "sample_id"),
    ):
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get(id_field), str):
                _fail("workload_mismatch")
            task_id = f"{kind}:{row[id_field]}"
            if task_id in tasks:
                _fail("workload_mismatch")
            tasks[task_id] = (kind, row)
            task_order.append(task_id)
    if len(tasks) != 112:
        _fail("accounting_mismatch")
    return _Artifacts(
        workload=workload,
        policy=policy,
        artifact_identity=artifact_identity,
        task_order=tuple(task_order),
        tasks=MappingProxyType(tasks),
    )


def _validate_events(
    *, export: dict[str, Any], artifacts: _Artifacts, round_row: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    events = _list(export.get("decision_events"), "decision_chain_mismatch")
    if events != sorted(
        events,
        key=lambda item: (
            item.get("task_id", "") if isinstance(item, dict) else "",
            item.get("revision", -1) if isinstance(item, dict) else -1,
            item.get("event_id", "") if isinstance(item, dict) else "",
        ),
    ):
        _fail("decision_chain_mismatch")
    by_task: dict[str, list[dict[str, Any]]] = {}
    event_ids: set[str] = set()
    for value in events:
        event = _exact_dict(value, _EVENT_KEYS, "decision_chain_mismatch")
        event_id = _string(event.get("event_id"), "decision_chain_mismatch")
        task_id = _string(event.get("task_id"), "decision_chain_mismatch")
        task = artifacts.tasks.get(task_id)
        kind = event.get("task_kind")
        decision = event.get("decision")
        revision = _integer(event.get("revision"), "decision_chain_mismatch", minimum=1)
        if (
            event_id in event_ids
            or task is None
            or kind != task[0]
            or not isinstance(decision, str)
            or decision not in _ALLOWED_DECISIONS[task[0]]
        ):
            _fail("decision_chain_mismatch")
        event_ids.add(event_id)
        rationale = event.get("rationale")
        if rationale is not None and (not isinstance(rationale, str) or not rationale):
            _fail("decision_chain_mismatch")
        if (
            revision > 1
            or kind == "exclusion"
            or (
                kind == "contract"
                and decision in {"needs_change", "unable_to_determine"}
            )
        ) and not rationale:
            _fail("decision_chain_mismatch")
        payload = _exact_dict(
            event.get("canonical_payload"),
            {
                "action",
                "decision",
                "display_name",
                "expected_revision",
                "rationale",
                "reviewer_id",
                "staff_id",
                "task_id",
                "task_kind",
            },
            "decision_chain_mismatch",
        )
        expected_payload = {
            "action": "decision",
            "decision": decision,
            "display_name": payload.get("display_name"),
            "expected_revision": revision - 1,
            "rationale": rationale,
            "reviewer_id": round_row["reviewer_id"],
            "staff_id": round_row["staff_id"],
            "task_id": task_id,
            "task_kind": kind,
        }
        if (
            payload != expected_payload
            or not isinstance(payload.get("display_name"), str)
            or not payload["display_name"].strip()
            or event.get("payload_sha256") != _canonical_sha256(payload)
            or _SHA256.fullmatch(str(event.get("idempotency_sha256"))) is None
            or event.get("record_sha256")
            != _canonical_sha256(
                {
                    "event_id": event_id,
                    "payload_sha256": event.get("payload_sha256"),
                    "revision": revision,
                    "supersedes_event_id": event.get("supersedes_event_id"),
                }
            )
        ):
            _fail("decision_chain_mismatch")
        _timestamp(event.get("submitted_at"), "decision_chain_mismatch")
        by_task.setdefault(task_id, []).append(event)
    latest: dict[str, dict[str, Any]] = {}
    for task_id, chain in by_task.items():
        for index, event in enumerate(chain, start=1):
            if event["revision"] != index:
                _fail("decision_chain_mismatch")
            expected_supersedes = None if index == 1 else chain[index - 2]["event_id"]
            if event["supersedes_event_id"] != expected_supersedes:
                _fail("decision_chain_mismatch")
        latest[task_id] = chain[-1]

    for kind, key in (
        ("contract", "contract_decisions"),
        ("exclusion", "exclusion_decisions"),
        ("calibration", "calibration_labels"),
    ):
        actual = _list(export.get(key), "decision_chain_mismatch")
        expected = [
            {
                "task_id": task_id,
                "decision": event["decision"],
                "revision": event["revision"],
                "event_id": event["event_id"],
                "payload_sha256": event["payload_sha256"],
            }
            for task_id, event in sorted(latest.items())
            if artifacts.tasks[task_id][0] == kind
        ]
        if actual != expected or any(
            not isinstance(item, dict) or set(item) != _PROJECTION_KEYS
            for item in actual
        ):
            _fail("decision_chain_mismatch")
    return latest


def _coverage(
    *,
    artifacts: _Artifacts,
    latest: dict[str, dict[str, Any]],
    kind: str | None,
    field: str,
) -> dict[str, dict[str, int]]:
    counters: dict[str, Counter[str]] = {}
    for task_id in artifacts.task_order:
        task_kind, row = artifacts.tasks[task_id]
        if kind is None:
            if task_kind == "calibration":
                continue
        elif task_kind != kind:
            continue
        group = str(row[field])
        counts = counters.setdefault(group, Counter())
        counts["total"] += 1
        event = latest.get(task_id)
        if event is None:
            counts["missing"] += 1
        else:
            counts["submitted"] += 1
            if event["decision"] in _ACCEPTING_DECISIONS[task_kind]:
                counts["accepting"] += 1
            else:
                counts["blocking"] += 1
    return {
        group: {
            "total": counts["total"],
            "submitted": counts["submitted"],
            "accepting": counts["accepting"],
            "blocking": counts["blocking"],
            "missing": counts["missing"],
        }
        for group, counts in sorted(counters.items())
    }


def _validate_hidden_judge(judge: object) -> None:
    if judge != {
        "visibility": "hidden_until_sealed",
        "status": "hidden_until_sealed",
    }:
        _fail("preseal_judge_disclosure")


def _calibration_snapshot_sha256(
    artifacts: _Artifacts, latest: dict[str, dict[str, Any]]
) -> str:
    snapshot: list[dict[str, Any]] = []
    for task_id in artifacts.task_order:
        if artifacts.tasks[task_id][0] != "calibration":
            continue
        event = latest.get(task_id)
        if event is None or event["decision"] not in {"supported", "unsupported"}:
            _fail("judge_evidence_mismatch")
        snapshot.append(
            {
                "decision": event["decision"],
                "event_id": event["event_id"],
                "payload_sha256": event["payload_sha256"],
                "revision": event["revision"],
                "task_id": task_id,
            }
        )
    if len(snapshot) != 60:
        _fail("judge_evidence_mismatch")
    return _canonical_sha256(snapshot)


def _validate_sealed_judge(
    *,
    judge_value: object,
    export: dict[str, Any],
    artifacts: _Artifacts,
    latest: dict[str, dict[str, Any]],
    round_row: dict[str, Any],
) -> bool:
    judge = _exact_dict(
        judge_value,
        {
            "visibility",
            "authorizations",
            "attempts",
            "recoveries",
            "completed_run",
            "responses",
            "summary",
        },
        "judge_evidence_mismatch",
    )
    if judge.get("visibility") != "sealed":
        _fail("judge_evidence_mismatch")
    authorizations = _list(judge.get("authorizations"), "judge_evidence_mismatch")
    if len(authorizations) != 1:
        _fail("judge_evidence_mismatch")
    authorization = _exact_dict(
        authorizations[0],
        {
            "schema_version",
            "evidence_class",
            "round_id",
            "authorizer_id",
            "provider_profile",
            "model_id",
            "calibration_policy_id",
            "judge_policy_id",
            "workload_content_sha256",
            "authorized_at",
            "evidence_scope",
            "content_sha256",
        },
        "judge_evidence_mismatch",
    )
    authorization_sha256 = _require_self_hash(authorization, "judge_evidence_mismatch")
    authorizer_id = authorization.get("authorizer_id")
    provider_profile = authorization.get("provider_profile")
    model_id_value = authorization.get("model_id")
    if (
        authorization.get("schema_version") != _AUTHORIZATION_SCHEMA
        or authorization.get("evidence_class") != export["evidence_class"]
        or authorization.get("round_id") != round_row["round_id"]
        or authorization.get("calibration_policy_id") != _CALIBRATION_POLICY_ID
        or authorization.get("judge_policy_id") != _JUDGE_POLICY_ID
        or authorization.get("workload_content_sha256")
        != artifacts.artifact_identity["workload_content_sha256"]
        or authorization.get("evidence_scope") != "supplied_request_only"
        or not isinstance(authorizer_id, str)
        or _OPAQUE_ID.fullmatch(authorizer_id) is None
        or not isinstance(provider_profile, str)
        or _PROVIDER_PROFILE.fullmatch(provider_profile) is None
        or not isinstance(model_id_value, str)
        or _MODEL_ID.fullmatch(model_id_value) is None
        or "://" in model_id_value
    ):
        _fail("judge_evidence_mismatch")
    _timestamp(authorization.get("authorized_at"), "judge_evidence_mismatch")
    model_id = _string(model_id_value, "judge_evidence_mismatch")

    human_snapshot_sha256 = _calibration_snapshot_sha256(artifacts, latest)
    expected_command_sha256 = _canonical_sha256(
        {
            "action": "seal_calibration",
            "expected_revision": 60,
            "round_id": round_row["round_id"],
        }
    )
    attempts = _list(judge.get("attempts"), "judge_evidence_mismatch")
    if not attempts:
        _fail("judge_evidence_mismatch")
    attempt_keys = {
        "run_id",
        "round_id",
        "idempotency_sha256",
        "command_sha256",
        "human_snapshot_sha256",
        "authorization_sha256",
        "started_at",
        "state",
        "failure_code",
        "finished_at",
    }
    attempts_by_id: dict[str, dict[str, Any]] = {}
    completed: list[dict[str, Any]] = []
    for value in attempts:
        attempt = _exact_dict(value, attempt_keys, "judge_evidence_mismatch")
        run_id = _string(attempt.get("run_id"), "judge_evidence_mismatch")
        state = attempt.get("state")
        if (
            run_id in attempts_by_id
            or attempt.get("round_id") != round_row["round_id"]
            or _SHA256.fullmatch(str(attempt.get("idempotency_sha256"))) is None
            or attempt.get("command_sha256") != expected_command_sha256
            or attempt.get("human_snapshot_sha256") != human_snapshot_sha256
            or attempt.get("authorization_sha256") != authorization_sha256
            or state not in {"failed", "completed"}
            or (state == "completed" and attempt.get("failure_code") is not None)
            or (state == "failed" and not isinstance(attempt.get("failure_code"), str))
        ):
            _fail("judge_evidence_mismatch")
        _timestamp(attempt.get("started_at"), "judge_evidence_mismatch")
        _timestamp(attempt.get("finished_at"), "judge_evidence_mismatch")
        attempts_by_id[run_id] = attempt
        if state == "completed":
            completed.append(attempt)
    if len(completed) != 1 or judge.get("completed_run") != completed[0]:
        _fail("judge_evidence_mismatch")

    recoveries = _list(judge.get("recoveries"), "judge_evidence_mismatch")
    recovery_keys = {
        "recovery_id",
        "run_id",
        "round_id",
        "command_sha256",
        "human_snapshot_sha256",
        "authorization_sha256",
        "operator_staff_id",
        "reason",
        "recovered_at",
    }
    recovered_runs: set[str] = set()
    for value in recoveries:
        recovery = _exact_dict(value, recovery_keys, "judge_evidence_mismatch")
        run_id = recovery.get("run_id")
        attempt = attempts_by_id.get(str(run_id))
        operator = recovery.get("operator_staff_id")
        if (
            attempt is None
            or run_id in recovered_runs
            or attempt.get("state") != "failed"
            or attempt.get("failure_code") != "operator_abandoned_after_crash"
            or recovery.get("round_id") != round_row["round_id"]
            or recovery.get("command_sha256") != expected_command_sha256
            or recovery.get("human_snapshot_sha256") != human_snapshot_sha256
            or recovery.get("authorization_sha256") != authorization_sha256
            or not isinstance(operator, str)
            or _STAFF_ID.fullmatch(operator) is None
            or recovery.get("reason") != "process_crash_confirmed"
        ):
            _fail("judge_evidence_mismatch")
        _timestamp(recovery.get("recovered_at"), "judge_evidence_mismatch")
        recovered_runs.add(str(run_id))

    probes = artifacts.workload["calibration_probes"]
    probe_by_task = {f"calibration:{probe['sample_id']}": probe for probe in probes}
    responses = _list(judge.get("responses"), "judge_evidence_mismatch")
    if len(responses) != 60 or responses != sorted(
        responses,
        key=lambda item: item.get("task_id", "") if isinstance(item, dict) else "",
    ):
        _fail("judge_evidence_mismatch")
    responses_by_task: dict[str, dict[str, Any]] = {}
    response_keys = {
        "task_id",
        "request_sha256",
        "response",
        "response_sha256",
        "judged_at",
    }
    response_body_keys = {
        "schema_version",
        "model_id",
        "policy_id",
        "request_sha256",
        "decision",
        "evidence_scope",
        "used_external_memory",
    }
    for value in responses:
        row = _exact_dict(value, response_keys, "judge_evidence_mismatch")
        task_id = row.get("task_id")
        probe = probe_by_task.get(str(task_id))
        response = _exact_dict(
            row.get("response"), response_body_keys, "judge_evidence_mismatch"
        )
        expected_request = (
            None if probe is None else _canonical_sha256(_stimulus(probe))
        )
        if (
            probe is None
            or task_id in responses_by_task
            or row.get("request_sha256") != expected_request
            or response.get("schema_version") != _RESPONSE_SCHEMA
            or response.get("model_id") != model_id
            or response.get("policy_id") != _JUDGE_POLICY_ID
            or response.get("request_sha256") != expected_request
            or response.get("decision") not in {"supported", "unsupported"}
            or response.get("evidence_scope") != "supplied_request_only"
            or response.get("used_external_memory") is not False
            or row.get("response_sha256") != _canonical_sha256(response)
        ):
            _fail("judge_evidence_mismatch")
        _timestamp(row.get("judged_at"), "judge_evidence_mismatch")
        responses_by_task[str(task_id)] = row
    if set(responses_by_task) != set(probe_by_task):
        _fail("judge_evidence_mismatch")

    strata = Counter(str(probe["stratum"]) for probe in probes)
    human_supported = 0
    matches = 0
    confusion = {
        "human_supported_model_supported": 0,
        "human_supported_model_unsupported": 0,
        "human_unsupported_model_supported": 0,
        "human_unsupported_model_unsupported": 0,
    }
    unsupported_critical = 0
    critical_false_accepts = 0
    judgments: list[dict[str, Any]] = []
    for probe in probes:
        task_id = f"calibration:{probe['sample_id']}"
        human_decision = latest[task_id]["decision"]
        response_row = responses_by_task[task_id]
        model_decision = response_row["response"]["decision"]
        human_supported += human_decision == "supported"
        matches += human_decision == model_decision
        confusion[f"human_{human_decision}_model_{model_decision}"] += 1
        is_unsupported_critical = (
            human_decision == "unsupported" and probe.get("critical_probe") is True
        )
        unsupported_critical += is_unsupported_critical
        critical_false_accepts += (
            is_unsupported_critical and model_decision == "supported"
        )
        judgments.append(
            {
                "task_id": task_id,
                "sample_id": probe["sample_id"],
                "stratum": probe["stratum"],
                "critical_probe": probe["critical_probe"],
                "request_sha256": response_row["request_sha256"],
                "response_sha256": response_row["response_sha256"],
                "human_decision": human_decision,
                "model_decision": model_decision,
            }
        )
    human_unsupported = 60 - human_supported
    agreement = matches / 60
    gate_values = {
        "exact_pair_count": True,
        "exact_stratum_quotas": dict(strata) == _EXPECTED_STRATA,
        "minimum_agreement": agreement >= artifacts.policy["minimum_agreement"],
        "minimum_supported_labels": human_supported
        >= artifacts.policy["minimum_supported_labels"],
        "minimum_unsupported_labels": human_unsupported
        >= artifacts.policy["minimum_unsupported_labels"],
        "minimum_unsupported_critical_probes": unsupported_critical
        >= artifacts.policy["minimum_unsupported_critical_probes"],
        "maximum_critical_false_accepts": critical_false_accepts
        <= artifacts.policy["maximum_critical_false_accepts"],
    }
    expected_summary = {
        "evidence_class": export["evidence_class"],
        "pair_count": 60,
        "stratum_counts": dict(sorted(strata.items())),
        "human_supported": human_supported,
        "human_unsupported": human_unsupported,
        "agreement": agreement,
        "confusion_matrix": confusion,
        "unsupported_critical_probes": unsupported_critical,
        "critical_false_accepts": critical_false_accepts,
        "gates": gate_values,
        "passed": all(gate_values.values()),
        "model_id": model_id,
        "calibration_policy_id": _CALIBRATION_POLICY_ID,
        "judge_policy_id": _JUDGE_POLICY_ID,
        "authorization_sha256": authorization_sha256,
        "human_snapshot_sha256": human_snapshot_sha256,
        "judgments": judgments,
    }
    if judge.get("summary") != expected_summary:
        _fail("gate_mismatch")
    return bool(expected_summary["passed"])


def _validated_gate_lifecycle(
    *,
    mode: object,
    acceptance_eligible: bool,
    reported_lifecycle: str,
    artifacts: _Artifacts,
    latest: dict[str, dict[str, Any]],
    calibration_passed: bool | None,
) -> str:
    if calibration_passed is None:
        if reported_lifecycle != "in_progress":
            _fail("preseal_judge_disclosure")
        return reported_lifecycle

    if not calibration_passed:
        derived_lifecycle = "calibration_failed_sealed"
    else:
        review_task_ids = [
            task_id
            for task_id in artifacts.task_order
            if artifacts.tasks[task_id][0] != "calibration"
        ]
        if any(task_id not in latest for task_id in review_task_ids):
            derived_lifecycle = "human_labels_sealed"
        elif all(
            latest[task_id]["decision"]
            in _ACCEPTING_DECISIONS[artifacts.tasks[task_id][0]]
            for task_id in review_task_ids
        ):
            derived_lifecycle = "acceptance_ready"
        else:
            derived_lifecycle = "review_complete_blocked"

    if reported_lifecycle == "locked":
        if derived_lifecycle != "acceptance_ready":
            _fail("gate_mismatch")
        if mode == "acceptance_candidate" and acceptance_eligible:
            return derived_lifecycle
        return reported_lifecycle
    if reported_lifecycle != derived_lifecycle:
        _fail("gate_mismatch")
    return reported_lifecycle


def _validate_accounting_and_gates(
    *,
    export: dict[str, Any],
    artifacts: _Artifacts,
    latest: dict[str, dict[str, Any]],
    round_lifecycle: str,
    calibration_passed: bool | None,
) -> bool:
    missing = [task_id for task_id in artifacts.task_order if task_id not in latest]
    blocking = [
        task_id
        for task_id in artifacts.task_order
        if task_id in latest
        and latest[task_id]["decision"]
        not in _ACCEPTING_DECISIONS[artifacts.tasks[task_id][0]]
    ]
    accounting = _exact_dict(
        export.get("accounting"),
        {"counts", "missing", "blocking"},
        "accounting_mismatch",
    )
    if accounting != {
        "counts": _EXPECTED_COUNTS,
        "missing": missing,
        "blocking": blocking,
    }:
        _fail("accounting_mismatch")

    calibration_task_ids = [
        task_id
        for task_id in artifacts.task_order
        if artifacts.tasks[task_id][0] == "calibration"
    ]
    labels_valid = len(calibration_task_ids) == 60 and all(
        latest.get(task_id, {}).get("decision") in {"supported", "unsupported"}
        for task_id in calibration_task_ids
    )
    blockers: list[str] = []
    if missing:
        blockers.append("human_decisions_missing")
    if blocking:
        blockers.append("human_decisions_blocking")
    if calibration_passed is None:
        blockers.append("calibration_not_sealed")
    elif not calibration_passed:
        blockers.append("calibration_failed")
    if round_lifecycle == "locked":
        blockers.append("round_locked")
    expected_gates = {
        "missing_task_ids": missing,
        "blocking_task_ids": blocking,
        "blocking_reasons": {
            task_id: latest[task_id]["decision"] for task_id in blocking
        },
        "family_coverage": _coverage(
            artifacts=artifacts,
            latest=latest,
            kind=None,
            field="family",
        ),
        "stratum_coverage": _coverage(
            artifacts=artifacts,
            latest=latest,
            kind="calibration",
            field="stratum",
        ),
        "calibration_labels_valid": labels_valid,
        "calibration_ready_to_seal": round_lifecycle == "in_progress" and labels_valid,
        "acceptance_ready": round_lifecycle == "acceptance_ready",
        "acceptance_blockers": blockers,
    }
    if export.get("gates") != expected_gates:
        _fail("gate_mismatch")
    return bool(expected_gates["acceptance_ready"])


def _deep_freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(child) for key, child in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(child) for child in value)
    return value


def _validate_review_export_v2(
    *,
    export_path: Path,
    packet_path: Path,
    workload_path: Path,
    source_root: Path,
) -> ValidatedReviewExportV2:
    """Validate an export and return its immutable, canonical application input."""

    try:
        raw = export_path.read_bytes()
    except OSError:
        _fail("invalid_json")
    export = _parse_json_bytes(raw, "invalid_json")
    try:
        canonical_export = _canonical_bytes(export)
    except (TypeError, ValueError, UnicodeError):
        _fail("invalid_json")
    if canonical_export != raw:
        _fail("non_canonical_export")
    _exact_dict(export, _TOP_KEYS, "invalid_export_schema")
    if export.get("schema_version") != _EXPORT_SCHEMA:
        _fail("invalid_export_schema")
    content_sha256 = _sha(export.get("content_sha256"), "export_hash_mismatch")
    if content_sha256 != _canonical_sha256(
        {key: value for key, value in export.items() if key != "content_sha256"}
    ):
        _fail("export_hash_mismatch")

    artifacts = _load_artifacts(
        packet_path=packet_path,
        workload_path=workload_path,
        source_root=source_root,
    )
    if export.get("artifact_identity") != artifacts.artifact_identity:
        _fail("artifact_mismatch")

    mode = export.get("mode")
    evidence_class = export.get("evidence_class")
    acceptance_eligible = _boolean(
        export.get("acceptance_eligible"), "invalid_export_schema"
    )
    task_2_8_eligible = _boolean(
        export.get("task_2_8_eligible"), "invalid_export_schema"
    )
    if mode not in {
        "review_evidence",
        "acceptance_candidate",
    } or evidence_class not in {
        "implementation_test",
        "real_human_round",
    }:
        _fail("invalid_export_schema")
    export_id = _string(export.get("export_id"), "invalid_export_schema")
    if _OPAQUE_ID.fullmatch(export_id) is None:
        _fail("invalid_export_schema")
    _timestamp(export.get("created_at"), "invalid_export_schema")
    round_row = _exact_dict(
        export.get("round"),
        {"round_id", "reviewer_id", "staff_id", "lifecycle"},
        "invalid_export_schema",
    )
    round_id = _string(round_row.get("round_id"), "invalid_export_schema")
    staff_id = round_row.get("staff_id")
    if (
        _OPAQUE_ID.fullmatch(round_id) is None
        or not isinstance(staff_id, str)
        or _STAFF_ID.fullmatch(staff_id) is None
        or round_row.get("reviewer_id") != f"human:{staff_id}"
        or round_row.get("lifecycle")
        not in {
            "in_progress",
            "calibration_failed_sealed",
            "human_labels_sealed",
            "review_complete_blocked",
            "acceptance_ready",
            "locked",
        }
    ):
        _fail("invalid_export_schema")

    latest = _validate_events(export=export, artifacts=artifacts, round_row=round_row)
    judge = export.get("judge")
    sealed = isinstance(judge, dict) and judge.get("visibility") == "sealed"
    if sealed:
        calibration_passed: bool | None = _validate_sealed_judge(
            judge_value=judge,
            export=export,
            artifacts=artifacts,
            latest=latest,
            round_row=round_row,
        )
    else:
        _validate_hidden_judge(judge)
        calibration_passed = None

    gate_lifecycle = _validated_gate_lifecycle(
        mode=mode,
        acceptance_eligible=acceptance_eligible,
        reported_lifecycle=str(round_row["lifecycle"]),
        artifacts=artifacts,
        latest=latest,
        calibration_passed=calibration_passed,
    )
    acceptance_ready = _validate_accounting_and_gates(
        export=export,
        artifacts=artifacts,
        latest=latest,
        round_lifecycle=gate_lifecycle,
        calibration_passed=calibration_passed,
    )
    expected_acceptance = mode == "acceptance_candidate" and acceptance_ready
    expected_task_2_8 = expected_acceptance and evidence_class == "real_human_round"
    if (
        acceptance_eligible != expected_acceptance
        or task_2_8_eligible != expected_task_2_8
        or (mode == "acceptance_candidate" and not expected_acceptance)
        or (expected_acceptance and round_row["lifecycle"] != "locked")
        or (mode == "review_evidence" and (acceptance_eligible or task_2_8_eligible))
    ):
        _fail("ineligible_export")

    frozen_identity = _deep_freeze(artifacts.artifact_identity)
    if not isinstance(frozen_identity, Mapping):
        _fail("artifact_mismatch")
    return ValidatedReviewExportV2(
        schema_version=_VALIDATED_SCHEMA,
        export_id=export_id,
        round_id=round_id,
        mode=str(mode),
        evidence_class=str(evidence_class),
        acceptance_eligible=acceptance_eligible,
        task_2_8_eligible=task_2_8_eligible,
        policy_id=_CALIBRATION_POLICY_ID,
        workload_counts=ValidatedReviewCounts(**_EXPECTED_COUNTS),
        artifact_identity=frozen_identity,
        canonical_export_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        content_sha256=content_sha256,
    )


def validate_review_export_v2(
    *,
    export_path: Path,
    packet_path: Path,
    workload_path: Path,
    source_root: Path,
) -> ValidatedReviewExportV2:
    """Validate an export and return its immutable, canonical application input."""

    try:
        return _validate_review_export_v2(
            export_path=export_path,
            packet_path=packet_path,
            workload_path=workload_path,
            source_root=source_root,
        )
    except ReviewExportValidationError:
        raise
    except (
        AttributeError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ):
        raise ReviewExportValidationError("invalid_input") from None
