#!/usr/bin/env python3
"""Generate source-build-manifest-p4.json (s12f manifest + six P4 batches)."""

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
    "company_full": "p4-company-full-v1",
    "patent_full": "p4-patent-full-v1",
    "paper_salvage": "p4-paper-salvage-v1",
    "professor_full": "p4-professor-full-v1",
    "professor_paper_links": "p4-professor-paper-links-v1",
    "applicant_binding_full": "p4-applicant-binding-full-v1",
}
RATIONALES = {
    "company_full": (
        "P4 full-column rebuild admits the complete company workbook "
        "(6,514 deduplicated rows x 16 columns) as released company objects."
    ),
    "patent_full": (
        "P4 full-column rebuild admits the full 11,408-patent admin release "
        "with deterministic type inference as released patent objects."
    ),
    "paper_salvage": (
        "P4 full-column rebuild admits the salvage ready-paper set (24,101 "
        "quality-gated rows) as released paper objects."
    ),
    "professor_full": (
        "P4 full-column rebuild admits the legacy professor JSONL union "
        "(v2 3,274 + v3-merged 825, 3,735 distinct name+institution) as "
        "released professor objects."
    ),
    "professor_paper_links": (
        "P4 full-column rebuild admits the salvage verified professor-paper "
        "links (18,655 name-anchored rows) as attribution evidence."
    ),
    "applicant_binding_full": (
        "P4 full-column rebuild admits the full applicant-pool resolution "
        "(2,373 applicants; s12f audited resolutions reused verbatim, "
        "full-column name-normalization joins, typed-gap unmatched)."
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
    )

    base = json.loads(S12F_MANIFEST.read_text())
    entries = {entry["source_id"]: entry for entry in base["inventory_entries"]}
    added = 0
    for purpose, batch_id in sorted(BATCH_IDS.items(), key=lambda kv: kv[1]):
        meta = INVENTORY[purpose]
        authority = next(
            value
            for value in _SUPPLEMENTAL_SOURCE_AUTHORITIES.values()
            if value.source_batch_id == batch_id
        )
        source_id = next(
            key
            for key, value in _SUPPLEMENTAL_SOURCE_AUTHORITIES.items()
            if value.source_batch_id == batch_id
        )
        member_path = f"workspace/docs/source_backfills/{meta['filename']}"
        entry = {
            "source_id": source_id,
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
                    "observed_at": "2026-08-19T00:00:00Z",
                    "parent_source_id": source_id,
                }
            ],
            "approval_reference": "approved-p4-full-column-rebuild",
            "gap_id": None,
            "rationale": RATIONALES[purpose],
        }
        if source_id in entries:
            raise SystemExit(f"duplicate source id {source_id}")
        entries[source_id] = entry
        added += 1
    base["inventory_entries"] = sorted(
        entries.values(), key=lambda item: item["source_id"]
    )
    base.pop("content_sha256", None)
    base["content_sha256"] = _canonical_sha256(base)

    from src.data_agents.canonical_v2.knowledge_build_isolated import (
        SourceBuildManifest,
    )

    SourceBuildManifest.model_validate_json(
        json.dumps(base, ensure_ascii=False),
        context={"external_content_addressed": True},
    )
    out = RUN_ROOT / "source-build-manifest-p4.json"
    out.write_text(
        json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"entries added: {added}; total: {len(base['inventory_entries'])}")
    print(f"manifest content_sha256: {base['content_sha256']}")
    print(f"file sha256: {__import__('hashlib').sha256(out.read_bytes()).hexdigest()}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
