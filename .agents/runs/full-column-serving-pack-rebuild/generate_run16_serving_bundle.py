"""Generate the content-addressed run16 serving bundle after the pack is sealed.

Mirrors generate_run15_serving_bundle.py: the previously accepted run15 bundle
is the SOURCE and only release-bound identities change —

    release / database / index target+root / envelope path / bundle id

while every runtime-policy field (embedding model, planner/answer model ids,
web provider + limits, key env names) stays byte-identical to the bundle the
live 18188 currently serves. The self-hash is recomputed through
RecordedServingBundle.model_validate and the written file is re-validated in
external content-addressed mode.

Differences from the run15 generator:
  - the required pack file set is derived from the pack manifest's schema
    version through the serving loader's own helpers, and the schema must be
    v2 (run16 ships the v2 contract: index_point in lookup.sqlite3, no Milvus);
  - EXPECTED_MARKER_SHA256 must be exported (value printed by build-run16.sh);
    the index marker is re-hashed here, never trusted from the command line.

Refuses to run before the run16 pack exists and its manifest identity matches
this release (release_id / index_root / marker sha / generator_run_id) — that
manifest block is produced by the official sealer, not by this script.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


SERVING_ROOT = Path(
    os.environ.get(
        "SERVING_WORKTREE",
        "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation",
    )
)
AGENT_APP = SERVING_ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    RecordedServingBundle,
)
from src.data_agents.canonical_v2.serving_pack_loader import (  # noqa: E402
    PACK_INSTITUTION_CATALOG_FILENAME,
    PACK_MANIFEST_FILENAME,
    PACK_MARKER_FILENAME,
    PACK_RELATIONSHIPS_FILENAME,
    PACK_SCHEMA_VERSION_V2,
    pack_index_filenames,
)


S12G = SERVING_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12g"
SOURCE = S12G / "serving-bundle-run15.json"
OUTPUT = S12G / "serving-bundle-run16.json"
RELEASE_ID = "candidate-v2-20260916-r1"
DATABASE_NAME = "miroflow_candidate_v2_20260916_r1"
INDEX_ROOT = Path("/var/tmp/mirothinker-data-v2/index-v3")
ENVELOPE = Path(
    "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform"
    "/s12a/complete-candidate-build-envelope.json"
)
PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run16-sealed")
PACK_GENERATOR_RUN_ID = "p4-pack-20260916-v1"
INDEX_MARKER_SHA256 = os.environ.get("EXPECTED_MARKER_SHA256", "")


def _require_regular_file(path: Path, *, owner: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{owner} must be an explicit regular file: {path}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_pack_files(schema_version: str) -> frozenset[str]:
    if schema_version != PACK_SCHEMA_VERSION_V2:
        raise RuntimeError(
            f"run16 seal must be the v2 pack contract, got {schema_version!r}"
        )
    return frozenset(
        {
            PACK_MANIFEST_FILENAME,
            PACK_RELATIONSHIPS_FILENAME,
            PACK_INSTITUTION_CATALOG_FILENAME,
            PACK_MARKER_FILENAME,
            *pack_index_filenames(schema_version),
        }
    )


def main() -> None:
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise RuntimeError(f"refusing to overwrite existing bundle: {OUTPUT}")
    if not INDEX_MARKER_SHA256:
        raise RuntimeError(
            "EXPECTED_MARKER_SHA256 must be exported (printed by build-run16.sh)"
        )
    _require_regular_file(SOURCE, owner="accepted run15 serving bundle")
    _require_regular_file(ENVELOPE, owner="run16 complete-candidate envelope")
    if not PACK_DIR.is_dir() or PACK_DIR.is_symlink():
        raise RuntimeError(f"run16 serving pack is missing: {PACK_DIR}")
    manifest = json.loads((PACK_DIR / PACK_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    for filename in sorted(_required_pack_files(str(manifest.get("schema_version")))):
        _require_regular_file(PACK_DIR / filename, owner=f"serving pack {filename}")
    marker_actual = _sha256_file(PACK_DIR / PACK_MARKER_FILENAME)
    if marker_actual != INDEX_MARKER_SHA256:
        raise RuntimeError(
            f"pack marker sha differs: {marker_actual} != {INDEX_MARKER_SHA256}"
        )
    expected = {
        "release_id": RELEASE_ID,
        "index_root": str(INDEX_ROOT),
        "index_marker_sha256": INDEX_MARKER_SHA256,
        "generator_run_id": PACK_GENERATOR_RUN_ID,
    }
    actual = {key: manifest.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"run16 serving pack manifest identity differs: {actual!r} != {expected!r}"
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
        raise RuntimeError("run16 serving bundle readback differs")
    print(f"{OUTPUT} {bundle.content_sha256}")


if __name__ == "__main__":
    main()
