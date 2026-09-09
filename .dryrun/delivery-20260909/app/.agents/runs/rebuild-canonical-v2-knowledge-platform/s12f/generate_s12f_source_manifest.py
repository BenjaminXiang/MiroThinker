"""Generate the s12f source-build manifest: s12e authority plus the professor backfill.

The s12e manifest binds the 50-source Accepted S2B inventory plus the five r7
supplemental authorities.  S12F promotes one more registered-but-unprojected
inventory slot (the professor-metrics backfill slot
``inventory:8c3084c6...``) to ``evidence_input`` for the
``s12e-professor-backfill-v1`` batch, pinning the exact
``professor_backfill_batch.jsonl`` content hash from the fixed
``_SUPPLEMENTAL_SOURCE_AUTHORITIES`` constant.  The batch was produced after
the Accepted S2B checkpoint, so the member carries no historical backup
lineage (null backup-member fields) and the build verifies it by content hash
and byte size at staging time.

Every other manifest field (accepted-gate hashes, inventory, the six existing
evidence members, mapper policy, expected row counts) is unchanged; this
script re-binds only the new member and the content-addressed
``content_sha256``.
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


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing manifest: {OUTPUT}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    if payload["schema_version"] != "canonical-v2-source-build-manifest-v2":
        raise RuntimeError("s12f authority requires the v2 s12e manifest")
    source_id = build._PROFESSOR_BACKFILL_SOURCE_ID
    authority = build._SUPPLEMENTAL_SOURCE_AUTHORITIES[source_id]
    restore_root = Path(payload["restore_root"])
    entries = {entry["source_id"]: entry for entry in payload["inventory_entries"]}
    entry = entries.get(source_id)
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
                "professor-metrics inventory slot.  The payload postdates the "
                "Accepted S2B checkpoint, so it carries no historical backup "
                "lineage and is verified by pinned content hash at staging."
            ),
            "members": [
                {
                    "member_id": authority.member_id,
                    "source_batch_id": authority.source_batch_id,
                    "source_kind": authority.source_kind,
                    "content_path": str(
                        restore_root / authority.restore_member_path
                    ),
                    "restore_member_path": str(authority.restore_member_path),
                    "backup_member_manifest_path": (
                        str(authority.backup_member_manifest_path)
                        if authority.backup_member_manifest_path is not None
                        else None
                    ),
                    "backup_member_manifest_sha256": (
                        authority.backup_manifest_sha256
                    ),
                    "source_member_manifest_sha256": (
                        authority.source_member_manifest_sha256
                    ),
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
            ],
        }
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
