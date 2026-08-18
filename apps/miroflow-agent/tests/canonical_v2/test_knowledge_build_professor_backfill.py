"""S12F professor backfill: manifest authority and projection merge wiring.

The s12e professor audit produced a 16-record field backfill batch
(``s12e-professor-backfill-v1``) for professors whose department/email/title
were demoted to explicit placeholders by the historical-source gate.  These
tests pin two behaviors:

1. the supplemental source authority that admits the batch through the
   source-build manifest and the ``_preflight`` batch-consistency check; and
2. the conservative merge that fills only missing/placeholder professor
   projection fields with source-grounded values, never overwriting real
   historical values, carrying source_url/observed_at/evidence_quote
   provenance through the merged field assertions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
RUN_ROOT = (
    Path(__file__).resolve().parents[4]
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
)
BACKFILL_PAYLOAD_PATH = RUN_ROOT / "s12e/professor_backfill_batch.jsonl"
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
RUN_ID = "s12f-test-build-run"
RELEASE_ID = "candidate-s12a-test"
SOURCE_BATCH_ID = "s12a-released-objects-full-v1"
BACKFILL_BATCH_ID = "s12e-professor-backfill-v1"
BACKFILL_OBSERVED_AT = "2026-08-01T13:35:30+00:00"

SOURCE_INVENTORY_SHA256 = (
    "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
)
BACKUP_MANIFEST_SHA256 = (
    "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
)
RESTORE_VERIFICATION_SHA256 = (
    "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
)
ACCEPTANCE_RECORD_SHA256 = (
    "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
)
RELEASED_OBJECTS_SOURCE_ID = (
    "inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0"
)
RELEASED_OBJECTS_SHA256 = (
    "7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce"
)
RELEASED_OBJECTS_RESTORE_MEMBER_PATH = "workspace/logs/data_agents/released_objects.db"
RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH = (
    "manifests/inventory/"
    "027-ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0.jsonl"
)
RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256 = (
    "6820786a2e055def2828c82de60f3b90cad9ac5dcc8f1477943a9f46a02777ae"
)
RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256 = (
    "4c91d1d7dce88e5c9d9924b2c21d6f3111292eb3e5c30a60e688fd40ccf8b594"
)
ORIGINAL_MILVUS_SHA256 = (
    "43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc"
)


def _module() -> Any:
    return import_module(TARGET_MODULE)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _released_member() -> dict[str, Any]:
    return {
        "member_id": "accepted-restore:workspace/logs/data_agents/released_objects.db",
        "source_batch_id": SOURCE_BATCH_ID,
        "source_kind": "released_objects_sqlite",
        "content_path": "/accepted/restore/workspace/logs/data_agents/released_objects.db",
        "restore_member_path": RELEASED_OBJECTS_RESTORE_MEMBER_PATH,
        "backup_member_manifest_path": (RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH),
        "backup_member_manifest_sha256": (
            RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
        ),
        "source_member_manifest_sha256": (
            RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
        ),
        "byte_size": 20_267_008,
        "content_sha256": RELEASED_OBJECTS_SHA256,
        "parser": {
            "parser_name": "released_objects_sqlite",
            "parser_version": "canonical-v2-s12a-full-table-v1",
            "schema_version": "released-objects-v1",
            "options": {
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        },
        "observed_at": "2026-07-22T12:00:00Z",
        "parent_source_id": RELEASED_OBJECTS_SOURCE_ID,
    }


def _supplemental_member(source_id: str, authority: Any) -> dict[str, Any]:
    return {
        "member_id": authority.member_id,
        "source_batch_id": authority.source_batch_id,
        "source_kind": authority.source_kind,
        "content_path": str(Path("/accepted/restore") / authority.restore_member_path),
        "restore_member_path": str(authority.restore_member_path),
        "backup_member_manifest_path": (
            str(authority.backup_member_manifest_path)
            if authority.backup_member_manifest_path is not None
            else None
        ),
        "backup_member_manifest_sha256": authority.backup_manifest_sha256,
        "source_member_manifest_sha256": authority.source_member_manifest_sha256,
        "byte_size": authority.byte_size,
        "content_sha256": authority.content_sha256,
        "parser": {
            "parser_name": authority.parser_name,
            "parser_version": "v1",
            "schema_version": (
                "historical-jsonl-record-v1"
                if authority.parser_name == "historical_jsonl"
                else "historical-xlsx-record-v1"
            ),
            "options": authority.parser_options,
        },
        "observed_at": "2026-07-11T15:44:30Z",
        "parent_source_id": source_id,
    }


def _v2_manifest_payload(module: Any, *, with_backfill: bool) -> dict[str, Any]:
    supplemental_ids = set(module._SUPPLEMENTAL_SOURCE_IDS)
    if not with_backfill:
        supplemental_ids -= {
            module._PROFESSOR_BACKFILL_SOURCE_ID,
        }
    entries: list[dict[str, Any]] = []
    for disposition, source_ids in module._SOURCE_IDS_BY_DISPOSITION.items():
        for source_id in source_ids:
            members: list[dict[str, Any]] = []
            selected_disposition = disposition.value
            if source_id == RELEASED_OBJECTS_SOURCE_ID:
                members = [_released_member()]
            elif source_id in supplemental_ids:
                selected_disposition = "evidence_input"
                members = [
                    _supplemental_member(
                        source_id,
                        module._SUPPLEMENTAL_SOURCE_AUTHORITIES[source_id],
                    )
                ]
            entries.append(
                {
                    "source_id": source_id,
                    "disposition": selected_disposition,
                    "source_family": "accepted-s2b-source",
                    "members": members,
                    "approval_reference": (
                        "approved-s12f-professor-backfill-promotion"
                        if source_id in supplemental_ids
                        and source_id == module._PROFESSOR_BACKFILL_SOURCE_ID
                        else None
                    ),
                    "gap_id": None,
                    "rationale": f"S12F exact {selected_disposition} disposition.",
                }
            )
    payload: dict[str, Any] = {
        "schema_version": "canonical-v2-source-build-manifest-v2",
        "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
        "backup_manifest_sha256": BACKUP_MANIFEST_SHA256,
        "restore_verification_sha256": RESTORE_VERIFICATION_SHA256,
        "acceptance_record_sha256": ACCEPTANCE_RECORD_SHA256,
        "released_objects_mapper_policy_version": (
            "canonical-v2-released-objects-mapper-v2"
        ),
        "released_objects_mapper_policy_sha256": (
            module._RELEASED_OBJECTS_MAPPER_POLICY_SHA256
        ),
        "released_objects_expected_row_counts": dict(module._EXPECTED_OBJECT_COUNTS),
        "restore_root": "/accepted/restore",
        "approved_recollection_root": None,
        "inventory_entries": sorted(entries, key=lambda item: item["source_id"]),
        "targeted_recollection_entries": [],
    }
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def _v1_manifest_payload(module: Any) -> dict[str, Any]:
    """A valid v1-era manifest: no supplemental sources are admitted.

    Mirrors ``_v2_manifest_payload`` but keeps every source in the module's
    baseline disposition map, so a v1 manifest is a downgrade that would
    silently drop the supplemental (backfill) authority.
    """
    entries: list[dict[str, Any]] = []
    for disposition, source_ids in module._SOURCE_IDS_BY_DISPOSITION.items():
        for source_id in source_ids:
            members: list[dict[str, Any]] = []
            if source_id == RELEASED_OBJECTS_SOURCE_ID:
                members = [_released_member()]
            entries.append(
                {
                    "source_id": source_id,
                    "disposition": disposition.value,
                    "source_family": "accepted-s2b-source",
                    "members": members,
                    "approval_reference": None,
                    "gap_id": None,
                    "rationale": f"S12A exact {disposition.value} disposition.",
                }
            )
    payload: dict[str, Any] = {
        "schema_version": "canonical-v2-source-build-manifest-v1",
        "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
        "backup_manifest_sha256": BACKUP_MANIFEST_SHA256,
        "restore_verification_sha256": RESTORE_VERIFICATION_SHA256,
        "acceptance_record_sha256": ACCEPTANCE_RECORD_SHA256,
        "released_objects_mapper_policy_version": (
            "canonical-v2-released-objects-mapper-v2"
        ),
        "released_objects_mapper_policy_sha256": (
            module._RELEASED_OBJECTS_MAPPER_POLICY_SHA256
        ),
        "released_objects_expected_row_counts": dict(module._EXPECTED_OBJECT_COUNTS),
        "restore_root": "/accepted/restore",
        "approved_recollection_root": None,
        "inventory_entries": sorted(entries, key=lambda item: item["source_id"]),
        "targeted_recollection_entries": [],
    }
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def _request(
    module: Any,
    *,
    source_batch_ids: tuple[str, ...],
) -> Any:
    return module.BuildCandidateRequest(
        run_id=RUN_ID,
        candidate_release_id=RELEASE_ID,
        source_batch_ids=source_batch_ids,
        parser_versions={
            "historical_jsonl": "v1",
            "historical_xlsx": "v1",
            "released_objects_sqlite": "canonical-v2-s12a-full-table-v1",
        },
        policy_versions={
            "path_eligibility": "path-eligibility-v1",
            "released_objects_mapper": "canonical-v2-released-objects-mapper-v2",
        },
        model_versions={"embedding": "recorded-embedding-v1"},
    )


class _BoundaryFailure(RuntimeError):
    """Controlled failure at a boundary primitive."""


@dataclass
class _RecordingDecisionAdapter:
    authority_sha256: str = (
        "6d7fa297838812bf6e3692bb32ff1133239be692d675ad8be749aeca9c7487b4"
    )
    calls: list[Any] = field(default_factory=list)

    def adjudicate(self, request: Any, /) -> Any:
        self.calls.append(request)
        recorded = getattr(request, "recorded_default", None)
        if recorded is None:
            raise _BoundaryFailure("no recorded decision for ambiguous fixture input")
        return recorded


@dataclass
class _RecordingEmbeddingAdapter:
    model_id: str = "recorded-embedding-v1"
    dimension: int = 32
    authority_sha256: str = (
        "a5b57005eb48a0692ae946d83c02ce54df0280a8274527f94c29d79d81266200"
    )


class _PreflightBoundary:
    """Preflight-only recording boundary; staging/landing are never reached."""

    def __init__(self, module: Any) -> None:
        self.module = module

    def verify_accepted_control_files_safe(self, *, gate_root: Path) -> None:
        assert gate_root == Path("/accepted/gate")

    def resolve_accepted_immutable_paths(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Any:
        assert gate_root == Path("/accepted/gate")
        assert expected_sha256 == ORIGINAL_MILVUS_SHA256
        return self.module._AcceptedImmutablePaths(
            backup_root=Path("/accepted/backup"),
            restore_root=Path("/accepted/restore"),
            evidence_root=Path("/protected/evidence"),
            original_milvus_path=Path("/protected/original/milvus.db"),
        )

    def resolve_accepted_original_milvus_path(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Path:
        assert gate_root == Path("/accepted/gate")
        assert expected_sha256 == ORIGINAL_MILVUS_SHA256
        return Path("/protected/original/milvus.db")

    def verify_accepted_gate(self, *, gate_root: Path) -> Any:
        assert gate_root == Path("/accepted/gate")
        return SimpleNamespace(
            source_inventory_sha256=SOURCE_INVENTORY_SHA256,
            backup_manifest_sha256=BACKUP_MANIFEST_SHA256,
            restore_verification_sha256=RESTORE_VERIFICATION_SHA256,
            acceptance_record_sha256=ACCEPTANCE_RECORD_SHA256,
            accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        )

    def validate_fresh_targets(self, *, target_config: Any) -> None:
        if not self.module._prepared_index_root_is_fresh(target_config.index):
            raise _BoundaryFailure("index target is not fresh marker-only state")
        staging = target_config.staging.root
        if staging.is_symlink() or staging.exists():
            raise _BoundaryFailure("staging target is not fresh and non-symlink")

    def prepare_fresh_targets(self, *, target_config: Any) -> None:
        self.validate_fresh_targets(target_config=target_config)


@dataclass
class _EnvelopeSink:
    module: Any
    destination: Path

    def validate_fresh(
        self,
        *,
        required_destination: Path,
        protected_paths: tuple[Path, ...],
    ) -> None:
        assert required_destination == Path(
            "/accepted/gate/s12a/complete-candidate-build-envelope.json"
        )
        if self.destination.exists() or self.destination.is_symlink():
            raise _BoundaryFailure("test envelope destination is not fresh")
        if any(
            self.module._paths_overlap(self.destination, path)
            for path in protected_paths
        ):
            raise _BoundaryFailure("test envelope destination overlaps protected path")


def _preflight_builder(
    module: Any,
    *,
    tmp_path: Path,
    manifest_payload: dict[str, Any],
) -> Any:
    manifest_path = tmp_path / "source-build-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_target = module.prepare_isolated_index_target(
        root=tmp_path / "index",
        target_id=f"index:{RELEASE_ID}",
        release_id=RELEASE_ID,
        backup_gate_root=RUN_ROOT,
        forbidden_milvus_paths=(Path("/protected/original/milvus.db"),),
    )
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    targets = module.CompleteCandidateTargetConfig(
        database=module.DestructiveDatabaseTarget(
            url=f"postgresql+psycopg://miroflow@127.0.0.1:5432/{database_name}",
            expected_database=database_name,
            target_kind="disposable",
        ),
        index=index_target,
        staging=module.CandidateStagingTarget(
            root=tmp_path / "staging",
            marker=module.CandidateStagingMarker(
                schema_version="canonical-v2-candidate-staging-marker-v1",
                run_id=RUN_ID,
                candidate_release_id=RELEASE_ID,
                source_manifest_sha256=manifest_payload["content_sha256"],
            ),
        ),
    )
    return module.create_isolated_knowledge_build(
        target_config=targets,
        accepted_backup_gate_root=Path("/accepted/gate"),
        source_manifest_path=manifest_path,
        accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        accepted_original_milvus_record_sha256=_canonical_hash(
            {
                "record_kind": "accepted-original-milvus-identity",
                "content_sha256": ORIGINAL_MILVUS_SHA256,
            }
        ),
        decision_adapter=_RecordingDecisionAdapter(),
        embedding_adapter=_RecordingEmbeddingAdapter(),
        boundary=_PreflightBoundary(module),
        envelope_sink=_EnvelopeSink(module, tmp_path / "envelope.json"),
        clock=lambda: NOW,
    )


def _demoted_professor_payload(
    *,
    object_id: str = "professor:00070",
    name: str = "王学谦",
) -> dict[str, Any]:
    """Professor released_objects row as the gate demoted it: no typed facts
    for the degradable fields, so the mapper projects explicit placeholders."""
    return {
        "id": object_id,
        "object_type": "professor",
        "display_name": name,
        "core_facts": {
            "name": name,
            "company_roles": [],
            "institution": "清华大学深圳国际研究生院",
            "patent_ids": [],
            "research_directions": [],
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/professor/70",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }


def _backfill_field(
    value: Any,
    *,
    source_url: str | None = "https://www.sigs.tsinghua.edu.cn/lx/wxq.htm",
    observed_at: str | None = BACKFILL_OBSERVED_AT,
    evidence_quote: str | None = "数据与信息研究院 王学谦",
    method: str | None = "official_page",
) -> dict[str, Any]:
    field_payload: dict[str, Any] = {"value": value}
    if source_url is not None:
        field_payload["source_url"] = source_url
    if observed_at is not None:
        field_payload["observed_at"] = observed_at
    if evidence_quote is not None:
        field_payload["evidence_quote"] = evidence_quote
    if method is not None:
        field_payload["method"] = method
    return field_payload


def _backfill_payload(
    *,
    professor_id: str = "professor:00070",
    professor_name: str = "王学谦",
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "backfill_batch": BACKFILL_BATCH_ID,
        "professor_id": professor_id,
        "professor_name": professor_name,
        "institution": "清华大学深圳国际研究生院",
        "fields": fields,
    }


def _parsed_rows(
    module: Any,
    payloads: tuple[dict[str, Any], ...],
) -> tuple[Any, ...]:
    member = module.SourceBuildMember.model_validate(_released_member())
    parsed: list[Any] = []
    for payload in payloads:
        row = {
            "id": payload["id"],
            "object_type": payload["object_type"],
            "display_name": payload["display_name"],
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        }
        record = module._source_record(
            row=row,
            source_batch_id=SOURCE_BATCH_ID,
            member=member,
            parsed_at=NOW,
        )
        parsed.append(
            module._ParsedReleasedObject(
                source_id=RELEASED_OBJECTS_SOURCE_ID,
                source_batch_id=SOURCE_BATCH_ID,
                record=record,
                artifact=module.EvidenceArtifact(
                    artifact_id=record.artifact_id,
                    source_kind=member.source_kind,
                    source_locator=str(member.content_path),
                    content_sha256=member.content_sha256,
                    byte_size=member.byte_size,
                    acquired_at=NOW,
                    run_id=RUN_ID,
                ),
                payload=payload,
            )
        )
    return tuple(parsed)


def _backfill_row(
    module: Any,
    basis: Any,
    payload: dict[str, Any],
    *,
    index: int = 0,
) -> Any:
    artifact_id = f"artifact:professor-backfill:{index}"
    record = basis.record.model_copy(
        update={
            "record_id": f"professor-backfill-record:{index}",
            "artifact_id": artifact_id,
            "source_batch_id": BACKFILL_BATCH_ID,
            "record_locator": f"professor-backfill:{index}",
            "payload": payload,
        },
        deep=True,
    )
    artifact = basis.artifact.model_copy(
        update={
            "artifact_id": artifact_id,
            "source_kind": "historical_jsonl",
            "source_locator": f"professor-backfill:{index}",
            "content_sha256": f"{index + 1:064x}",
            "run_id": f"professor-backfill-run:{index}",
        }
    )
    return module._ParsedReleasedObject(
        source_id=module._PROFESSOR_BACKFILL_SOURCE_ID,
        source_batch_id=BACKFILL_BATCH_ID,
        record=record,
        artifact=artifact,
        payload=payload,
    )


def _field_assertion(
    decision_result: Any, *, object_id: str, field_path: str
) -> Any:
    matches = [
        assertion
        for assertion in decision_result.field_assertions
        if assertion.source_identity_id == f"source-released-object:{object_id}"
        and assertion.field_path == field_path
    ]
    assert len(matches) == 1
    return matches[0]


def test_backfill_authority_pins_the_committed_batch_file() -> None:
    module = _module()
    source_id = module._PROFESSOR_BACKFILL_SOURCE_ID
    authority = module._SUPPLEMENTAL_SOURCE_AUTHORITIES[source_id]

    content = BACKFILL_PAYLOAD_PATH.read_bytes()
    assert authority.source_batch_id == BACKFILL_BATCH_ID
    assert authority.byte_size == len(content)
    assert authority.content_sha256 == hashlib.sha256(content).hexdigest()
    assert authority.source_kind == "historical_jsonl"
    assert authority.parser_name == "historical_jsonl"
    assert (
        authority.restore_member_path
        == Path("workspace/docs/source_backfills/professor_backfill_batch.jsonl")
    )
    assert source_id in module._SUPPLEMENTAL_SOURCE_IDS
    assert module._SUPPLEMENTAL_SOURCE_PURPOSES[source_id] == "professor_backfill"
    assert (
        source_id
        not in module._SOURCE_IDS_BY_DISPOSITION[
            module.SourceDisposition.evidence_input
        ]
    )
    assert (
        source_id
        in module._SOURCE_IDS_BY_DISPOSITION[
            module.SourceDisposition.registered_unprojected
        ]
    )


def test_preflight_admits_manifest_with_backfill_authority(tmp_path: Path) -> None:
    module = _module()
    payload = _v2_manifest_payload(module, with_backfill=True)
    builder = _preflight_builder(module, tmp_path=tmp_path, manifest_payload=payload)
    batches = tuple(
        sorted(
            (
                SOURCE_BATCH_ID,
                "s12c-r7-company-knowledge-v1",
                "s12c-r7-company-workbook-supplement-v1",
                "s12c-r7-paper-identifiers-v1",
                "s12c-r7-patent-identifiers-v1",
                "s12c-r7-professor-company-roles-v1",
                BACKFILL_BATCH_ID,
                "s12f-company-backfill-v1",
                "s12f-applicant-binding-v1",
                "p4-company-full-v1",
                "p4-patent-full-v1",
                "p4-paper-salvage-v1",
                "p4-professor-full-v1",
                "p4-professor-paper-links-v1",
                "p4-applicant-binding-full-v1",
            )
        )
    )

    manifest, _ = builder._preflight(_request(module, source_batch_ids=batches))

    assert manifest.content_sha256 == payload["content_sha256"]
    admitted_batches = tuple(
        sorted(
            member.source_batch_id
            for entry in manifest.inventory_entries
            if entry.disposition is module.SourceDisposition.evidence_input
            for member in entry.members
        )
    )
    assert admitted_batches == batches


def test_preflight_rejects_request_missing_the_backfill_batch(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _v2_manifest_payload(module, with_backfill=True)
    builder = _preflight_builder(module, tmp_path=tmp_path, manifest_payload=payload)
    stale_batches = tuple(
        sorted(
            (
                SOURCE_BATCH_ID,
                "s12c-r7-company-knowledge-v1",
                "s12c-r7-company-workbook-supplement-v1",
                "s12c-r7-paper-identifiers-v1",
                "s12c-r7-patent-identifiers-v1",
                "s12c-r7-professor-company-roles-v1",
                "s12f-company-backfill-v1",
                "s12f-applicant-binding-v1",
            )
        )
    )

    with pytest.raises(
        module.SourceBuildManifestError,
        match="request source batches differ from the source-build manifest",
    ):
        builder._preflight(_request(module, source_batch_ids=stale_batches))


def test_legacy_manifest_without_backfill_authority_is_rejected(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _v2_manifest_payload(module, with_backfill=False)
    builder = _preflight_builder(module, tmp_path=tmp_path, manifest_payload=payload)
    batches = tuple(
        sorted(
            (
                SOURCE_BATCH_ID,
                "s12c-r7-company-knowledge-v1",
                "s12c-r7-company-workbook-supplement-v1",
                "s12c-r7-paper-identifiers-v1",
                "s12c-r7-patent-identifiers-v1",
                "s12c-r7-professor-company-roles-v1",
                BACKFILL_BATCH_ID,
                "s12f-company-backfill-v1",
                "s12f-applicant-binding-v1",
                "p4-company-full-v1",
                "p4-patent-full-v1",
                "p4-paper-salvage-v1",
                "p4-professor-full-v1",
                "p4-professor-paper-links-v1",
                "p4-applicant-binding-full-v1",
            )
        )
    )

    with pytest.raises(module.SourceBuildManifestError):
        builder._preflight(_request(module, source_batch_ids=batches))


def test_v1_manifest_is_rejected_at_build_entry(tmp_path: Path) -> None:
    """The build entry must refuse a v1 downgrade of the source manifest.

    A v1 manifest validates as a legal accepted-gate build without the
    supplemental (professor backfill) authority, so a caller could otherwise
    downgrade the manifest and silently drop every supplemental source.
    """
    module = _module()
    payload = _v1_manifest_payload(module)
    builder = _preflight_builder(module, tmp_path=tmp_path, manifest_payload=payload)
    batches = tuple(
        sorted(
            member["source_batch_id"]
            for entry in payload["inventory_entries"]
            for member in entry["members"]
        )
    )

    with pytest.raises(
        module.SourceBuildManifestError,
        match="canonical-v2-source-build-manifest-v2",
    ):
        builder._preflight(_request(module, source_batch_ids=batches))


def test_backfill_fills_demoted_fields_with_provenance() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {
        "department": _backfill_field("数据与信息研究院"),
        "email": _backfill_field("wang.xueqian@sz.tsinghua.edu.cn"),
        "title": _backfill_field("副教授"),
    }
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(fields=fields),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    projections = public[4].projections
    assert len(projections) == 1
    projection = projections[0]
    assert projection.entity_type == "professor"
    assert projection.department.name == "数据与信息研究院"
    assert projection.email == "wang.xueqian@sz.tsinghua.edu.cn"
    assert projection.title == "副教授"

    expected_observed_at = datetime(2026, 8, 1, 13, 35, 30, tzinfo=timezone.utc)
    for field_path in ("department", "email", "title"):
        assertion = _field_assertion(
            public[2], object_id=professor["id"], field_path=field_path
        )
        assert assertion.source_record_id == backfill.record.record_id
        assert assertion.observed_at == expected_observed_at
    department = _field_assertion(
        public[2], object_id=professor["id"], field_path="department"
    )
    assert department.value["name"] == "数据与信息研究院"

    source = next(
        item
        for item in public[1].source_identities
        if item.source_key == professor["id"]
    )
    assert backfill.record.record_id in source.source_record_ids


def test_backfill_never_overwrites_real_values() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    professor["core_facts"].update(
        {
            "department": "机器人研究院",
            "email": "real.wang@sz.tsinghua.edu.cn",
        }
    )
    released_rows = _parsed_rows(module, (professor,))
    fields = {
        "department": _backfill_field("数据与信息研究院"),
        "email": _backfill_field("wang.xueqian@sz.tsinghua.edu.cn"),
        "title": _backfill_field("副教授"),
    }
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(fields=fields),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    projection = public[4].projections[0]
    assert projection.department.name == "机器人研究院"
    assert projection.email == "real.wang@sz.tsinghua.edu.cn"
    assert projection.title == "副教授"

    kept_department = _field_assertion(
        public[2], object_id=professor["id"], field_path="department"
    )
    assert kept_department.source_record_id == released_rows[0].record.record_id
    merged_title = _field_assertion(
        public[2], object_id=professor["id"], field_path="title"
    )
    assert merged_title.source_record_id == backfill.record.record_id


def test_backfill_skips_unknown_professor_and_counts() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {"department": _backfill_field("数据与信息研究院")}
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(
            professor_id="professor:does-not-exist",
            fields=fields,
        ),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    projection = public[4].projections[0]
    assert projection.department.name == module._PROFESSOR_MISSING_FIELD_FALLBACK
    unmatched = [
        gap
        for gap in public[6]
        if gap.result.evidence_ids == (backfill.record.record_id,)
        and "no exact retained object match" in gap.signal.observed_symptom
    ]
    assert len(unmatched) == 1


def test_backfill_skips_crosswired_professor_name() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {"department": _backfill_field("数据与信息研究院")}
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(
            professor_name="完全不同姓名",
            fields=fields,
        ),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    projection = public[4].projections[0]
    assert projection.department.name == module._PROFESSOR_MISSING_FIELD_FALLBACK
    crosswired = [
        gap
        for gap in public[6]
        if gap.result.evidence_ids == (backfill.record.record_id,)
        and "does not match" in gap.signal.observed_symptom
    ]
    assert len(crosswired) == 1


def test_backfill_rejected_record_stays_out_of_identity_lineage() -> None:
    """A professor_id hit alone must not admit lineage for the professor.

    The record is rejected by the merge-stage name check, so it must not
    enter the professor's ``source_record_ids``, must produce no field
    assertion, and must be counted as unmatched.
    """
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {"department": _backfill_field("数据与信息研究院")}
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(
            professor_name="完全不同姓名",
            fields=fields,
        ),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    source = next(
        item
        for item in public[1].source_identities
        if item.source_key == professor["id"]
    )
    assert backfill.record.record_id not in source.source_record_ids
    assert not [
        assertion
        for assertion in public[2].field_assertions
        if assertion.source_record_id == backfill.record.record_id
    ]
    crosswired = [
        gap
        for gap in public[6]
        if gap.result.evidence_ids == (backfill.record.record_id,)
        and "does not match" in gap.signal.observed_symptom
    ]
    assert len(crosswired) == 1

    _, stats, adopted = module._merge_professor_backfill_rows(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(backfill,),
        selected_by_object={
            professor["id"]: {"name": professor["core_facts"]["name"]}
        },
        domain_by_object={professor["id"]: "professor"},
        field_assertions=[],
        gaps=[],
        now=NOW,
    )
    assert stats.records_seen == 1
    assert stats.records_unmatched == 1
    assert stats.records_merged == 0
    assert adopted == ()


def test_backfill_all_invalid_fields_record_stays_out_of_identity_lineage() -> None:
    """A matched record with no admissible field must not admit lineage either.

    The name matches, but every field fails provenance/admissibility, so the
    record contributes nothing; it must not enter the professor's
    ``source_record_ids`` and must produce no field assertion.
    """
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {
        "department": _backfill_field("数据与信息研究院", source_url=None),
        "title": _backfill_field("副教授", observed_at=None),
    }
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(fields=fields),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    source = next(
        item
        for item in public[1].source_identities
        if item.source_key == professor["id"]
    )
    assert backfill.record.record_id not in source.source_record_ids
    assert not [
        assertion
        for assertion in public[2].field_assertions
        if assertion.source_record_id == backfill.record.record_id
    ]
    skipped = [
        gap
        for gap in public[6]
        if gap.result.evidence_ids == (backfill.record.record_id,)
        and "cannot admit" in gap.signal.observed_symptom
    ]
    assert len(skipped) == 1

    _, stats, adopted = module._merge_professor_backfill_rows(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(backfill,),
        selected_by_object={
            professor["id"]: {
                "name": professor["core_facts"]["name"],
                "department": module._PROFESSOR_MISSING_FIELD_FALLBACK,
                "title": module._PROFESSOR_MISSING_FIELD_FALLBACK,
            }
        },
        domain_by_object={professor["id"]: "professor"},
        field_assertions=[],
        gaps=[],
        now=NOW,
    )
    assert stats.records_seen == 1
    assert stats.records_merged == 0
    assert stats.records_unmatched == 0
    assert stats.fields_invalid == 2
    assert adopted == ()


def test_backfill_skips_unsupported_and_unprovenanced_fields() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {
        "aliases": _backfill_field(["Wang Xueqian"], method="pinyin"),
        "canonical_name_en": _backfill_field("Xueqian Wang", method="pinyin"),
        "department": _backfill_field("数据与信息研究院", source_url=None),
        "title": _backfill_field("副教授"),
    }
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(fields=fields),
    )

    public = module._map_public_authority(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(*released_rows, backfill),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    projection = public[4].projections[0]
    # aliases/canonical_name_en are outside the professor projection contract;
    # the unprovenanced department value stays out; only title merges.
    assert projection.title == "副教授"
    assert projection.department.name == module._PROFESSOR_MISSING_FIELD_FALLBACK
    skipped = [
        gap
        for gap in public[6]
        if gap.result.evidence_ids == (backfill.record.record_id,)
        and "cannot admit" in gap.signal.observed_symptom
    ]
    assert len(skipped) == 1
    assert {
        "fields.aliases",
        "fields.canonical_name_en",
        "fields.department",
    } <= set(skipped[0].signal.affected_paths)


def test_backfill_merge_helper_reports_exact_counts() -> None:
    module = _module()
    professor = _demoted_professor_payload()
    released_rows = _parsed_rows(module, (professor,))
    fields = {
        "aliases": _backfill_field(["Wang Xueqian"]),
        "department": _backfill_field("数据与信息研究院"),
        "email": _backfill_field("wang.xueqian@sz.tsinghua.edu.cn"),
        "homepage": _backfill_field("", evidence_quote=""),
        "title": _backfill_field("副教授"),
    }
    backfill = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(fields=fields),
    )
    unknown = _backfill_row(
        module,
        released_rows[0],
        _backfill_payload(
            professor_id="professor:does-not-exist",
            fields={"department": _backfill_field("数据与信息研究院")},
        ),
        index=1,
    )
    selected = {
        professor["id"]: {
            "name": professor["core_facts"]["name"],
            "department": module._PROFESSOR_MISSING_FIELD_FALLBACK,
            "email": module._PROFESSOR_MISSING_FIELD_FALLBACK,
            "homepage": module._PROFESSOR_MISSING_FIELD_FALLBACK,
            "title": module._PROFESSOR_MISSING_FIELD_FALLBACK,
        }
    }
    assertions: list[Any] = []
    gaps: list[Any] = []

    merged_assertions, stats, adopted = module._merge_professor_backfill_rows(
        request=_request(module, source_batch_ids=(SOURCE_BATCH_ID,)),
        rows=(backfill, unknown),
        selected_by_object=selected,
        domain_by_object={professor["id"]: "professor"},
        field_assertions=assertions,
        gaps=gaps,
        now=NOW,
    )

    assert stats.records_seen == 2
    assert stats.records_merged == 1
    assert stats.records_unmatched == 1
    assert stats.fields_merged == 3
    assert stats.fields_kept_existing == 0
    assert stats.fields_unsupported == 1
    assert stats.fields_invalid == 1
    assert adopted == ((professor["id"], backfill.record.record_id),)
    assert len(merged_assertions) == 3
    assert selected[professor["id"]]["department"]["name"] == "数据与信息研究院"
    assert selected[professor["id"]]["email"] == (
        "wang.xueqian@sz.tsinghua.edu.cn"
    )
    assert selected[professor["id"]]["title"] == "副教授"
    assert selected[professor["id"]]["homepage"] == (
        module._PROFESSOR_MISSING_FIELD_FALLBACK
    )
