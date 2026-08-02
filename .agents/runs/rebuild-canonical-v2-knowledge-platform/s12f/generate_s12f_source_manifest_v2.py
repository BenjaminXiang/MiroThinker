"""Generate the s12f v2 source-build manifest: 50 S2B sources + 3 backfill batches.

The s12e manifest binds the 50-source Accepted S2B inventory plus the five r7
supplemental authorities.  S12F promotes the registered-but-unprojected
professor-metrics inventory slot to ``evidence_input`` for the
``s12e-professor-backfill-v1`` batch, and additionally admits two brand-new
inventory entries for the s12f company backfill (``s12f-company-backfill-v1``)
and the applicant-binding batch (``s12f-applicant-binding-v1``).  All three
batches were produced after the Accepted S2B checkpoint, so their members
carry no historical backup lineage (null backup fields) and the build verifies
them by pinned content hash and byte size at staging time.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
AGENT_APP = ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2 import knowledge_build_isolated as build  # noqa: E402

SOURCE = (
    ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/source-build-manifest-s12e.json"
)
OUTPUT = Path(__file__).with_name("source-build-manifest-s12f.json")
OBSERVED_AT = "2026-08-01T13:35:30Z"


def _member_for(authority: build._SupplementalSourceAuthority, source_id: str) -> dict:
    restore_root = Path(
        json.loads(SOURCE.read_text(encoding="utf-8"))["restore_root"]
    )
    return {
        "member_id": authority.member_id,
        "source_batch_id": authority.source_batch_id,
        "source_kind": authority.source_kind,
        "content_path": str(restore_root / authority.restore_member_path),
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
            "schema_version": "historical-jsonl-record-v1",
            "options": authority.parser_options,
        },
        "observed_at": OBSERVED_AT,
        "parent_source_id": source_id,
    }


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing manifest: {OUTPUT}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    if payload["schema_version"] != "canonical-v2-source-build-manifest-v2":
        raise RuntimeError("s12f authority requires the v2 s12e manifest")
    entries = {entry["source_id"]: entry for entry in payload["inventory_entries"]}

    # 1. Promote the registered-but-unprojected professor-metrics slot.
    professor_source_id = build._PROFESSOR_BACKFILL_SOURCE_ID
    professor_authority = build._SUPPLEMENTAL_SOURCE_AUTHORITIES[professor_source_id]
    entry = entries.get(professor_source_id)
    if entry is None:
        raise RuntimeError("professor backfill inventory slot is absent")
    if entry["disposition"] != "registered_unprojected" or entry["members"]:
        raise RuntimeError("professor backfill inventory slot is not unprojected")
    entry.update(
        {
            "disposition": "evidence_input",
            "approval_reference": "approved-s12f-professor-backfill-promotion",
            "rationale": (
                "S12F admits the s12e-professor-backfill-v1 field backfill "
                "(16 audited professors; department/email/title from official "
                "institution pages) through the registered-but-unprojected "
                "professor-metrics inventory slot."
            ),
            "members": [_member_for(professor_authority, professor_source_id)],
        }
    )

    # 2. Add the two brand-new s12f inventory entries.
    new_entries = []
    for source_id in (
        build._COMPANY_BACKFILL_SOURCE_ID,
        build._APPLICANT_BINDING_SOURCE_ID,
    ):
        if source_id in entries:
            raise RuntimeError(f"new s12f source already present: {source_id}")
        authority = build._SUPPLEMENTAL_SOURCE_AUTHORITIES[source_id]
        new_entries.append(
            {
                "source_id": source_id,
                "source_family": "accepted-s2b-source",
                "disposition": "evidence_input",
                "approval_reference": "approved-s12f-applicant-resolution-backfill",
                "gap_id": None,
                "rationale": (
                    "S12F admits the company backfill and applicant-binding "
                    "batches produced by the s12f applicant-resolution "
                    "pipeline (700 audited companies; every released patent "
                    "applicant mapped to a canonical company).  Both payloads "
                    "postdate the Accepted S2B checkpoint, so they carry no "
                    "historical backup lineage and are verified by pinned "
                    "content hash at staging."
                ),
                "members": [_member_for(authority, source_id)],
            }
        )
    payload["inventory_entries"] = sorted(
        [*payload["inventory_entries"], *new_entries],
        key=lambda entry: entry["source_id"],
    )
    payload.pop("content_sha256", None)
    payload["content_sha256"] = "0" * 64
    manifest = build.SourceBuildManifest.model_validate(payload)
    rendered = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
        allow_nan=False,
    ) + "\n"
    OUTPUT.write_text(rendered, encoding="utf-8")
    readback = build.SourceBuildManifest.model_validate_json(
        OUTPUT.read_text(encoding="utf-8"),
        context={"external_content_addressed": True},
    )
    if readback != manifest:
        raise RuntimeError("s12f source manifest readback differs")
    batch_ids = sorted(
        member.source_batch_id
        for item in manifest.inventory_entries
        if item.disposition is build.SourceDisposition.evidence_input
        for member in item.members
    )
    print(f"{OUTPUT} {manifest.content_sha256}")
    print(f"evidence batches: {batch_ids}")


if __name__ == "__main__":
    main()
