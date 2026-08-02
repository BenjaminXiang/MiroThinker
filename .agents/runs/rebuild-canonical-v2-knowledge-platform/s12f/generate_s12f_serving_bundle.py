"""Generate the content-addressed s12f serving bundle after pack creation.

Only release-bound identities change from the accepted r8 serving bundle.
Runtime policy fields remain identical.  The script refuses to run before the
exact s12f envelope and dogfood-built serving pack exist, recomputes the bundle
self-hash through ``RecordedServingBundle.model_validate``, and validates the
written file in external content-addressed mode.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
AGENT_APP = ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    RecordedServingBundle,
)


GATE = ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
SOURCE = GATE / "s12c/serving-bundle-r8.json"
OUTPUT = Path(__file__).with_name("serving-bundle-s12f.json")
RELEASE_ID = "candidate-s12f-20260801-v1"
DATABASE_NAME = "miroflow_candidate_s12f_20260801_v1"
INDEX_ROOT = Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1")
ENVELOPE = GATE / "s12a/complete-candidate-build-envelope.json"
PACK_DIR = Path("/var/tmp/mirothinker-canonical-v2-s12f/serving-pack")
INDEX_MARKER_SHA256 = "e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51"
PACK_GENERATOR_RUN_ID = "s12f-pack-20260801-v1"
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


def _require_pack() -> None:
    if not PACK_DIR.is_dir() or PACK_DIR.is_symlink():
        raise RuntimeError(f"s12f serving pack is missing: {PACK_DIR}")
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
            "s12f serving pack manifest identity differs: "
            f"expected={expected!r} actual={actual!r}"
        )


def main() -> None:
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise RuntimeError(f"refusing to overwrite existing bundle: {OUTPUT}")
    _require_regular_file(ENVELOPE, owner="s12f complete-candidate envelope")
    _require_pack()

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
        raise RuntimeError("s12f serving bundle readback differs")
    print(f"{OUTPUT} {bundle.content_sha256}")


if __name__ == "__main__":
    main()
