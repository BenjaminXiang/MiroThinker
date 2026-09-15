"""Seal one scratch serving pack (v1 or v2) against a scratch index root.

The production packs bind their own absolute index root, so an isolated scratch
instance needs a pack whose ``manifest.json`` names the scratch root. This
script rewrites exactly those loader-bound fields (index root, marker hash,
per-file hashes, pack schema version) from real pack artifacts, copies the
index files, and dogfoods the result through the real loader before it is used.

Read-only against ``--source-pack`` and ``--index-root``; writes only into
``--pack-dir``. Usage (from ``apps/miroflow-agent``)::

    uv run python ../../.agents/runs/drop-milvus-from-serving-pack/seal_scratch_pack.py \
        --source-pack /var/tmp/mirothinker-data-v2/serving-pack-run15-sealed \
        --index-root /var/tmp/slimpack-296/v1/index \
        --pack-dir /var/tmp/slimpack-296/v1/pack \
        --generator-run-id scratch-v1-20260915

    # v2 (index root already converted by convert_index_to_v2.py)
    uv run python ../../.agents/runs/drop-milvus-from-serving-pack/seal_scratch_pack.py \
        --source-pack /var/tmp/mirothinker-data-v2/serving-pack-run15-sealed \
        --index-root /var/tmp/slimpack-296/v2/index \
        --pack-dir /var/tmp/slimpack-296/v2/pack \
        --pack-schema-version canonical-v2-serving-pack-v2 \
        --generator-run-id scratch-v2-20260915
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any


def _bootstrap_src() -> None:
    try:
        import_module("src.data_agents.canonical_v2.serving_pack_loader")
    except ModuleNotFoundError:
        agent_root = Path(__file__).resolve().parents[3] / "apps/miroflow-agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))


_bootstrap_src()

from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    _canonical_json_bytes,
    _marker_document,
    has_lookup_index_points,
)


class ScratchPackError(RuntimeError):
    """The scratch pack cannot be sealed from these inputs."""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("an explicit absolute path is required")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seal one scratch serving pack")
    parser.add_argument("--source-pack", required=True, type=_absolute)
    parser.add_argument("--index-root", required=True, type=_absolute)
    parser.add_argument("--pack-dir", required=True, type=_absolute)
    parser.add_argument("--generator-run-id", required=True)
    parser.add_argument(
        "--pack-schema-version",
        choices=(pack_loader.PACK_SCHEMA_VERSION, pack_loader.PACK_SCHEMA_VERSION_V2),
        default=pack_loader.PACK_SCHEMA_VERSION,
    )
    return parser


def main(args: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(args)
    try:
        summary = seal_scratch_pack(
            source_pack=namespace.source_pack,
            index_root=namespace.index_root,
            pack_dir=namespace.pack_dir,
            generator_run_id=namespace.generator_run_id,
            pack_schema_version=namespace.pack_schema_version,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"scratch pack seal failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("scratch_pack_summary=" + repr(summary), flush=True)
    return 0


def seal_scratch_pack(
    *,
    source_pack: Path,
    index_root: Path,
    pack_dir: Path,
    generator_run_id: str,
    pack_schema_version: str,
) -> dict[str, Any]:
    index_filenames = pack_loader.pack_index_filenames(pack_schema_version)
    point_store = pack_loader.pack_point_store(pack_schema_version)
    if not source_pack.is_dir() or source_pack.is_symlink():
        raise ScratchPackError("source pack directory is missing or unsafe")
    if not index_root.is_dir() or index_root.is_symlink():
        raise ScratchPackError("index root is missing or unsafe")
    index_root = Path(os.path.abspath(index_root))
    for ancestor in (index_root, *index_root.parents):
        if ancestor.is_symlink():
            raise ScratchPackError("index root ancestry contains a symlink")

    manifest_path = source_pack / pack_loader.PACK_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_bytes())
    release_id = manifest["release_id"]
    forbidden = [str(value) for value in manifest["index_forbidden_milvus_paths"]]

    marker_bytes = (
        _canonical_json_bytes(
            _marker_document(
                root=index_root,
                target_id=manifest["index_target_id"],
                release_id=release_id,
                forbidden_milvus_paths=tuple(Path(value) for value in forbidden),
            )
        )
        + b"\n"
    )
    (index_root / pack_loader.PACK_MARKER_FILENAME).write_bytes(marker_bytes)

    if pack_schema_version == pack_loader.PACK_SCHEMA_VERSION_V2:
        if not has_lookup_index_points(index_root / "lookup.sqlite3"):
            raise ScratchPackError("v2 index root lacks the index_point store")
        if (index_root / "milvus.db").exists():
            raise ScratchPackError("v2 index root must not carry milvus.db")

    if pack_dir.exists():
        raise ScratchPackError("scratch pack directory must not exist yet")
    pack_dir.parent.mkdir(parents=True, exist_ok=True)
    pack_dir.mkdir()
    file_hashes: dict[str, str] = {}
    file_sizes: dict[str, int] = {}
    for name in (
        *index_filenames,
        *(
            pack_loader.PACK_RELATIONSHIPS_FILENAME,
            pack_loader.PACK_INSTITUTION_CATALOG_FILENAME,
        ),
    ):
        source = (
            index_root / name
            if name in index_filenames
            else source_pack / name
        )
        if not source.is_file() or source.is_symlink():
            raise ScratchPackError(f"input artifact is missing: {name}")
        target = pack_dir / name
        shutil.copyfile(source, target)
        file_hashes[name] = pack_loader._sha256_file(target)
        file_sizes[name] = target.stat().st_size
    marker_target = pack_dir / pack_loader.PACK_MARKER_FILENAME
    marker_target.write_bytes(marker_bytes)
    file_hashes[pack_loader.PACK_MARKER_FILENAME] = _sha256_bytes(marker_bytes)
    file_sizes[pack_loader.PACK_MARKER_FILENAME] = len(marker_bytes)

    manifest.update(
        {
            "schema_version": pack_schema_version,
            "index_root": str(index_root),
            "index_marker_sha256": _sha256_bytes(marker_bytes),
            "generator_run_id": generator_run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": file_hashes,
        }
    )
    pack_loader.ServingPackManifest.model_validate(manifest)
    (pack_dir / pack_loader.PACK_MANIFEST_FILENAME).write_bytes(
        (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )

    authority = pack_loader.open_serving_pack_authority(
        pack_dir=pack_dir,
        expected_release_id=release_id,
        expected_index_marker_sha256=manifest["index_marker_sha256"],
        expected_forbidden_milvus_path=Path(forbidden[0]),
    )
    snapshot = authority.index_snapshot
    return {
        "pack_dir": str(pack_dir),
        "index_root": str(index_root),
        "pack_schema_version": pack_schema_version,
        "point_store": point_store,
        "points": len(snapshot.points),
        "lookup_documents": len(snapshot.lookup_documents),
        "index_result_content_sha256": authority.release_bundle.index_result.content_sha256,
        "file_sizes": file_sizes,
    }


if __name__ == "__main__":
    raise SystemExit(main())
