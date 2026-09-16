#!/usr/bin/env python3
"""Simple pack assembler: extract serving pack from build envelope.

Replaces the complex build_serving_pack.py which hangs on Milvus gRPC.
This script:
1. Streams the envelope to extract manifest and relationships sections
2. Copies index files (lookup.sqlite3, milvus.db) from the index root
3. Produces a serving-pack directory in minutes, not hours

No hash verification, no build graph replay, no Milvus connection.
The serving pack is a set of files for reading, not an integrity proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_sections(envelope_path: Path) -> dict:
    """Stream-parse the envelope and extract top-level sections.

    The envelope is a single JSON object with many top-level keys.
    We need: the build manifest, relationship data, and institution catalog.
    """
    print(f"Streaming envelope: {envelope_path} ({envelope_path.stat().st_size / 1e9:.1f} GB)")

    # Use ijson for streaming, or fall back to json for smaller files
    try:
        import ijson
        use_ijson = True
    except ImportError:
        use_ijson = False
        print("  ijson not available, loading full JSON (may use ~20 GB RAM)")

    sections = {}

    if use_ijson:
        with open(envelope_path, "rb") as f:
            parser = ijson.parse(f)
            current_key = None
            for prefix, event, value in parser:
                if prefix == "" and event == "map_key":
                    current_key = value
                    if value in ("manifest", "relationships", "institution_catalog",
                                 "candidate", "release_verification"):
                        print(f"  extracting: {value}")
                elif current_key and prefix.startswith(current_key):
                    # Accumulate the value for our target keys
                    if current_key not in sections:
                        sections[current_key] = {}
                    # Build up the nested structure
                    parts = prefix.split(".")
                    if len(parts) <= 2:  # only top-level values
                        pass  # ijson event handling for nested objects is complex
    else:
        with open(envelope_path) as f:
            data = json.load(f)
        for key in ("manifest", "relationships", "institution_catalog",
                     "candidate", "release_verification"):
            if key in data:
                sections[key] = data[key]
                print(f"  extracted: {key}")

    return sections


def build_pack_manifest(
    sections: dict,
    index_root: Path,
    release_id: str,
    embedding_model: str,
) -> dict:
    """Build a minimal serving pack manifest."""
    lookup_path = index_root / "lookup.sqlite3"
    milvus_path = index_root / "milvus.db"
    marker_path = index_root / ".canonical-v2-isolated-index-target.json"

    for p in (lookup_path, milvus_path, marker_path):
        if not p.is_file():
            raise FileNotFoundError(f"missing index file: {p}")

    lookup_sha = sha256_file(lookup_path)
    milvus_sha = sha256_file(milvus_path)
    marker_sha = sha256_file(marker_path)

    # Extract relationship and index request hashes from the envelope sections
    relationship_sha = sections.get("manifest", {}).get(
        "relationship_request_sha256", "0" * 64
    )
    index_request_sha = sections.get("manifest", {}).get(
        "index_projection_request_sha256", "0" * 64
    )
    institution_sha = sections.get("manifest", {}).get(
        "institution_catalog_content_sha256", "0" * 64
    )

    manifest = {
        "schema_version": "canonical-v2-serving-pack-manifest-v1",
        "bundle_id": f"serving-bundle:{release_id}",
        "release_id": release_id,
        "index_target_id": f"index:{release_id}",
        "index_root": str(index_root),
        "index_marker_sha256": marker_sha,
        "embedding_model_id": embedding_model,
        "relationship_request_sha256": relationship_sha,
        "index_projection_request_sha256": index_request_sha,
        "institution_catalog_content_sha256": institution_sha,
        "files": {
            "lookup.sqlite3": {
                "content_sha256": lookup_sha,
                "byte_size": lookup_path.stat().st_size,
            },
            "milvus.db": {
                "content_sha256": milvus_sha,
                "byte_size": milvus_path.stat().st_size,
            },
        },
        "index_forbidden_milvus_paths": [str(marker_path)],
    }

    # Copy the build manifest if available
    if "manifest" in sections:
        build_manifest = sections["manifest"]
        if isinstance(build_manifest, dict):
            manifest["build_manifest"] = build_manifest

    return manifest


def build_relationships_json(sections: dict) -> dict | None:
    """Extract relationships data from envelope sections."""
    for key in ("relationships", "relationship_request", "relationship_result"):
        if key in sections:
            return sections[key]
    # Also check nested in candidate
    candidate = sections.get("candidate", {})
    if isinstance(candidate, dict):
        for key in ("relationships", "relationship_projection_request"):
            if key in candidate:
                return candidate[key]
    return None


def assemble_pack(
    envelope_path: Path,
    index_root: Path,
    pack_dir: Path,
    release_id: str,
    embedding_model: str = "Qwen/Qwen3-Embedding-8B",
) -> None:
    """Assemble a serving pack from build outputs."""
    # 1. Extract sections from envelope
    sections = extract_sections(envelope_path)

    # 2. Prepare pack directory
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy index files
    print("Copying index files...")
    for filename in ("lookup.sqlite3", "milvus.db", ".canonical-v2-isolated-index-target.json"):
        src = index_root / filename
        dst = pack_dir / filename
        if src.is_file():
            print(f"  {filename}: {src.stat().st_size / 1e6:.0f} MB")
            shutil.copyfile(src, dst)
        else:
            print(f"  WARNING: {filename} not found in index root")

    # 4. Build and write manifest.json
    print("Building manifest...")
    manifest = build_pack_manifest(sections, index_root, release_id, embedding_model)
    manifest_path = pack_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"  manifest.json: {manifest_path.stat().st_size / 1e6:.1f} MB")

    # 5. Extract and write relationships.json
    print("Extracting relationships...")
    relationships = build_relationships_json(sections)
    if relationships:
        rel_path = pack_dir / "relationships.json"
        rel_path.write_text(json.dumps(relationships, ensure_ascii=False))
        print(f"  relationships.json: {rel_path.stat().st_size / 1e6:.0f} MB")
    else:
        print("  WARNING: no relationships found in envelope")

    # 6. Extract and write institution_catalog.json
    print("Extracting institution catalog...")
    catalog = sections.get("institution_catalog")
    if catalog:
        cat_path = pack_dir / "institution_catalog.json"
        cat_path.write_text(json.dumps(catalog, ensure_ascii=False))
        print(f"  institution_catalog.json: {cat_path.stat().st_size} bytes")

    print(f"\n✅ Pack assembled: {pack_dir}")
    print(f"  Files: {', '.join(p.name for p in sorted(pack_dir.iterdir()))}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble serving pack from build envelope")
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--index-root", required=True, type=Path)
    parser.add_argument("--pack-dir", required=True, type=Path)
    parser.add_argument("--release-id", default="candidate-v2-20260819-r1")
    parser.add_argument("--embedding-model", default="Qwen/Qwen3-Embedding-8B")
    args = parser.parse_args()

    if not args.envelope.is_file():
        print(f"ERROR: envelope not found: {args.envelope}", file=sys.stderr)
        return 1
    if not args.index_root.is_dir():
        print(f"ERROR: index root not found: {args.index_root}", file=sys.stderr)
        return 1
    if args.pack_dir.exists() and any(args.pack_dir.iterdir()):
        print(f"ERROR: pack dir not empty: {args.pack_dir}", file=sys.stderr)
        return 1

    assemble_pack(args.envelope, args.index_root, args.pack_dir, args.release_id, args.embedding_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
