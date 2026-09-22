#!/usr/bin/env python3
"""Independent check of the re-sealed pack: does a v1.1 boot take the fast path?

Two runs of the same code against the same pack, differing in one flag:

  --verify-reconstruction yes   replay the reconstruction (what the seal does;
                                this is the ~137 s a boot pays when the recorded
                                reader is not this reader)
  --verify-reconstruction no    the boot's normal path; with the pack's mount
                                receipt present and the recorded reader equal to
                                this reader, the loader skips the replay

Read-only against the pack (the receipt is written only when
``CANONICAL_V2_SERVING_RECEIPT_PATH`` is overridden to a scratch path).

Usage: python3 fastpath-check.py --pack DIR --verify-reconstruction {yes,no}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import monotonic

AGENT_ROOT = Path(__file__).resolve().parents[3] / "apps" / "miroflow-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402


class _StubEmbeddingAdapter:
    """Identity-only embedding port: this check never embeds."""

    def __init__(self, *, model_id: str) -> None:
        self.model_id = model_id
        self.dimension = 1

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        raise RuntimeError("fastpath check must not embed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--verify-reconstruction", choices=("yes", "no"), required=True)
    args = parser.parse_args()

    manifest_bytes = (args.pack / pack_loader.PACK_MANIFEST_FILENAME).read_bytes()
    manifest = pack_loader.ServingPackManifest.model_validate_json(manifest_bytes)
    digest = pack_loader.reader_contract_digest()
    print(f"pack                      = {args.pack}")
    print(f"pack manifest sha256      = {hashlib.sha256(manifest_bytes).hexdigest()}")
    print(f"pack schema_version       = {manifest.schema_version}")
    print(f"pack generator_run_id     = {manifest.generator_run_id}")
    print(f"recorded reader_contract  = {manifest.reader_contract_sha256}")
    print(f"this reader contract      = {digest}")
    print(f"recorded == this reader   = {manifest.reader_contract_sha256 == digest}")
    print(f"receipt path              = {pack_loader._mount_receipt_path(args.pack)}")
    print(f"receipt exists            = {pack_loader._mount_receipt_path(args.pack).is_file()}")
    print(f"verify_reconstruction     = {args.verify_reconstruction}")

    started = monotonic()
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=args.pack,
        expected_release_id=manifest.release_id,
        expected_index_marker_sha256=manifest.index_marker_sha256,
        expected_forbidden_milvus_path=Path(manifest.index_forbidden_milvus_paths[0]),
        embedding_adapter=_StubEmbeddingAdapter(model_id=manifest.embedding_model_id),
        verify_reconstruction=args.verify_reconstruction == "yes",
    )
    elapsed = monotonic() - started
    counts: dict[str, int] = {}
    for document in authority.index_snapshot.lookup_documents:
        counts[str(document.domain)] = counts.get(str(document.domain), 0) + 1
    print(f"open wall seconds         = {elapsed:.3f}")
    print(f"lookup documents          = {len(authority.index_snapshot.lookup_documents)}")
    print(f"points                    = {len(authority.index_snapshot.points)}")
    print(f"domain counts             = {json.dumps(dict(sorted(counts.items())))}")
    print(f"relationship_result_sha   = {authority.release_bundle.relationship_projection_result.content_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
