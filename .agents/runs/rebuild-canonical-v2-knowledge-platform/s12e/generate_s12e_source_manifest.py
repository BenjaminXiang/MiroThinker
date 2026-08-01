"""Generate the s12e source-build manifest from the accepted r7 authority.

The s12e field-whitelist widenings (company industry/website/key_personnel/
aliases, paper doi/arxiv_id/pdf_path, patent filing/publication dates) changed
``_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE`` and therefore the derived
``_RELEASED_OBJECTS_MAPPER_POLICY_SHA256`` (5c281568... -> 4c6265ce...).  The
committed r7 manifest pins the old mapper hash, so exact accepted-authority
validation rejects it.  Every other manifest field (accepted-gate hashes,
50-source inventory, member identities/hashes, expected row counts) is
unchanged; this script re-binds only the mapper policy hash and the
content-addressed ``content_sha256``.
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
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/source-build-manifest-r7.json"
)
OUTPUT = Path(__file__).with_name("source-build-manifest-s12e.json")


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing manifest: {OUTPUT}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    old_mapper = payload["released_objects_mapper_policy_sha256"]
    new_mapper = build._RELEASED_OBJECTS_MAPPER_POLICY_SHA256
    if old_mapper == new_mapper:
        raise RuntimeError("r7 manifest already binds the current mapper policy")
    payload.pop("content_sha256", None)
    payload["released_objects_mapper_policy_sha256"] = new_mapper
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
        raise RuntimeError("s12e source manifest readback differs")
    print(f"old_mapper={old_mapper}")
    print(f"new_mapper={new_mapper}")
    print(f"{OUTPUT} {manifest.content_sha256}")


if __name__ == "__main__":
    main()
