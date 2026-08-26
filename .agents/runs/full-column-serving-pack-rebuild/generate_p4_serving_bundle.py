"""Generate the content-addressed P4 serving bundle after pack creation.

Mirrors generate_s12f_serving_bundle.py, rebound to the run-9 release:
candidate-v2-20260819-r1, database miroflow_candidate_v2_20260819_r1,
index root /var/tmp/mirothinker-data-v2/index-v1, envelope from THIS
worktree's gate root. Runtime policy fields stay identical to the
accepted r8/s12f bundle.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

S11_ROOT = Path(
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
)
AGENT_APP = S11_ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    RecordedServingBundle,
)

SOURCE = (
    S11_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/serving-bundle-r8.json"
)
OUTPUT = Path(__file__).with_name("serving-bundle-p4.json")
GATE = (
    Path("/home/longxiang/MiroThinker/.worktrees/data-rebuild")
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
)
RELEASE_ID = "candidate-v2-20260819-r1"
DATABASE_NAME = "miroflow_candidate_v2_20260819_r1"
INDEX_ROOT = Path("/var/tmp/mirothinker-data-v2/index-v1")
ENVELOPE = GATE / "s12a/complete-candidate-build-envelope.json"
PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack")
INDEX_MARKER_SHA256 = "8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
PACK_GENERATOR_RUN_ID = "p4-pack-20260826-v1"
REQUIRED_PACK_FILES = frozenset(
    {
        "manifest.json",
        "relationships.json",
        "institution_catalog.json",
        "lookup.sqlite3",
        "milvus.db",
        ".canonical-v2-isolated-index-target.json",
    }
)


def _require_regular_file(path: Path, *, owner: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{owner} must be an explicit regular file: {path}")


def main() -> None:
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise RuntimeError(f"refusing to overwrite existing bundle: {OUTPUT}")
    _require_regular_file(ENVELOPE, owner="p4 complete-candidate envelope")
    if not PACK_DIR.is_dir() or PACK_DIR.is_symlink():
        raise RuntimeError(f"p4 serving pack is missing: {PACK_DIR}")
    for filename in sorted(REQUIRED_PACK_FILES):
        _require_regular_file(PACK_DIR / filename, owner=f"serving pack {filename}")
    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    expected = {
        "release_id": RELEASE_ID,
        "index_root": str(INDEX_ROOT),
        "index_marker_sha256": INDEX_MARKER_SHA256,
        "generator_run_id": PACK_GENERATOR_RUN_ID,
    }
    actual = {key: manifest.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"p4 serving pack manifest identity differs: {actual!r} != {expected!r}"
        )

    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload.pop("content_sha256", None)
    payload.update(
        {
            "bundle_id": f"serving-bundle:{RELEASE_ID}",
            "release_id": RELEASE_ID,
            "database_name": DATABASE_NAME,
            "index_target_id": f"index:{RELEASE_ID}",
            "index_root": str(INDEX_ROOT),
            "envelope_path": str(ENVELOPE),
        }
    )
    bundle = RecordedServingBundle.model_validate(payload)
    rendered = (
        json.dumps(
            bundle.model_dump(mode="json"),
            ensure_ascii=False,
            indent=1,
            sort_keys=False,
            allow_nan=False,
        )
        + "\n"
    )
    OUTPUT.write_text(rendered, encoding="utf-8")
    readback = RecordedServingBundle.model_validate_json(
        OUTPUT.read_bytes(),
        context={"external_content_addressed": True},
    )
    if readback != bundle:
        raise RuntimeError("p4 serving bundle readback differs")
    print(f"{OUTPUT} {bundle.content_sha256}")


if __name__ == "__main__":
    main()
