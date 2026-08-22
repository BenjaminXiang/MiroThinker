#!/usr/bin/env python3
"""Generate source-build-manifest-p4-mini.json (s12f manifest + professor_full only).

Mini rehearsal scope: the known-good s12f base plus exactly one P4 batch so
the whole pipeline (p4 merge code included) runs end-to-end at a fraction of
the full-column size.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUN_ROOT = Path(__file__).resolve().parent
APP_ROOT = RUN_ROOT.parents[2] / "apps/miroflow-agent"
S12F_MANIFEST = (
    RUN_ROOT.parents[0]
    / "rebuild-canonical-v2-knowledge-platform/s12f/source-build-manifest-s12f.json"
)
RESTORE_ROOT = Path(
    "/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z"
)
INVENTORY = json.loads((RUN_ROOT / "batch-inventory.json").read_text())

BATCH_IDS = {
    "professor_full": "p4-professor-full-v1",
}
RATIONALES = {
    "professor_full": (
        "Mini rehearsal admits the legacy professor JSONL union so the p4 "
        "merge path runs end-to-end at reduced scale."
    ),
}


def _canonical_sha256(value: object) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    sys.path.insert(0, str(APP_ROOT))
    from src.data_agents.canonical_v2.knowledge_build_isolated import (
        _SUPPLEMENTAL_SOURCE_AUTHORITIES,
        SourceBuildManifest,
    )

    base = json.loads(S12F_MANIFEST.read_text())
    entries = {entry["source_id"]: entry for entry in base["inventory_entries"]}
    added = 0
    for purpose, batch_id in sorted(BATCH_IDS.items(), key=lambda kv: kv[1]):
        meta = INVENTORY[purpose]
        authority_key = next(
            key
            for key, value in _SUPPLEMENTAL_SOURCE_AUTHORITIES.items()
            if value.source_batch_id == batch_id
        )
        member_path = f"workspace/docs/source_backfills/{meta['filename']}"
        entry = {
            "source_id": authority_key,
            "disposition": "evidence_input",
            "source_family": "accepted-s2b-source",
            "members": [
                {
                    "member_id": f"accepted-restore:{member_path}",
                    "source_batch_id": batch_id,
                    "source_kind": "historical_jsonl",
                    "content_path": str(RESTORE_ROOT / member_path),
                    "restore_member_path": member_path,
                    "backup_member_manifest_path": None,
                    "backup_member_manifest_sha256": None,
                    "source_member_manifest_sha256": None,
                    "byte_size": meta["byte_size"],
                    "content_sha256": meta["content_sha256"],
                    "parser": {
                        "parser_name": "historical_jsonl",
                        "parser_version": "v1",
                        "schema_version": "historical-jsonl-record-v1",
                        "options": {},
                    },
                    "observed_at": "2026-08-21T00:00:00Z",
                    "parent_source_id": authority_key,
                }
            ],
            "approval_reference": "approved-p4-full-column-rebuild",
            "gap_id": None,
            "rationale": RATIONALES[purpose],
        }
        if authority_key in entries:
            raise SystemExit(f"duplicate source id {authority_key}")
        entries[authority_key] = entry
        added += 1
    base["inventory_entries"] = sorted(
        entries.values(), key=lambda item: item["source_id"]
    )
    base.pop("content_sha256", None)
    base["content_sha256"] = _canonical_sha256(base)

    SourceBuildManifest.model_validate_json(
        json.dumps(base, ensure_ascii=False),
        context={"external_content_addressed": True},
    )
    out = RUN_ROOT / "source-build-manifest-p4-mini.json"
    out.write_text(
        json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"entries added: {added}; total: {len(base['inventory_entries'])}")
    print(f"manifest content_sha256: {base['content_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
