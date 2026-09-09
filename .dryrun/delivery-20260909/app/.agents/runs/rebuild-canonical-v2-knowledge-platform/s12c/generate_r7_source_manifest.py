"""Generate the content-bound r7 source manifest from the accepted v1 inventory."""

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
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12b/source-build-manifest-v2.json"
)
OUTPUT = Path(__file__).with_name("source-build-manifest-r7.json")
OBSERVED_AT = "2026-07-11T15:44:30Z"


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing manifest: {OUTPUT}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload.pop("content_sha256", None)
    payload["schema_version"] = "canonical-v2-source-build-manifest-v2"
    restore_root = Path(payload["restore_root"])
    entries = {entry["source_id"]: entry for entry in payload["inventory_entries"]}
    for source_id, authority in build._SUPPLEMENTAL_SOURCE_AUTHORITIES.items():
        entry = entries[source_id]
        entry.update(
            {
                "disposition": "evidence_input",
                "approval_reference": "approved-s12c-r7-fixed-source-promotion",
                "rationale": (
                    "S12C r7 restore-verified fixed source admitted through immutable "
                    "landing; production serving never reads the customer workbook."
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
                        "backup_member_manifest_path": str(
                            authority.backup_member_manifest_path
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
                            "schema_version": (
                                "historical-jsonl-record-v1"
                                if authority.parser_name == "historical_jsonl"
                                else "historical-xlsx-record-v1"
                            ),
                            "options": authority.parser_options,
                        },
                        "observed_at": OBSERVED_AT,
                        "parent_source_id": source_id,
                    }
                ],
            }
        )
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
        raise RuntimeError("r7 source manifest readback differs")
    print(f"{OUTPUT} {manifest.content_sha256}")


if __name__ == "__main__":
    main()
