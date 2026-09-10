"""Reseal one half-sealed Serving Pack from its own artifacts (C2.1r).

The run14 pack at ``--source-pack`` carries the 2026-09-08 run14 index
materialization but still binds the p4 (2026-08-26) index-side manifest
fields, so the fail-closed loader refuses it. This script seals a fresh pack
from the artifacts themselves: it copies the five pack files into a fresh
``--pack-dir`` and recomputes **every loader-bound manifest field** exactly
the way ``serving_pack_loader.open_serving_pack_authority`` verifies them,
then dogfoods the new pack through the real loader and refuses to ship unless
the full authority opens clean.

Read-only against ``--source-pack`` and ``--index-root``. Usage (from
``apps/miroflow-agent``)::

    uv run python ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/reseal_serving_pack.py \
        --source-pack /var/tmp/mirothinker-data-v2/serving-pack-run14 \
        --index-root /var/tmp/mirothinker-data-v2/index-v1 \
        --pack-dir /var/tmp/mirothinker-data-v2/serving-pack-run14-resealed \
        --generator-run-id c2-reseal-20260910-v1
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any


def _bootstrap_src() -> None:
    try:
        import_module("src.data_agents.canonical_v2.serving_pack_loader")
    except ModuleNotFoundError:
        agent_root = Path(__file__).resolve().parents[4] / "apps/miroflow-agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))


_bootstrap_src()

from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2.candidate_projection import (  # noqa: E402
    CandidateProjectionRequest,
    CandidateProjectionResult,
)
from src.data_agents.canonical_v2.contracts import (  # noqa: E402
    BuildManifest,
    ReleaseVerification,
)
from src.data_agents.canonical_v2.index_projection import (  # noqa: E402
    IndexProjectionMaterializationReceipt,
    IndexProjectionPolicySnapshot,
    IndexProjectionRebuildDecision,
    IndexProjectionRequest,
    IndexProjectionResult,
)
from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    IsolatedIndexTarget,
    open_manifest_verified_index_snapshot,
)
from src.data_agents.canonical_v2.internal_reference_projection import (  # noqa: E402
    InternalReferenceProjectionResult,
)
from src.data_agents.canonical_v2.knowledge_read import InstitutionCatalog  # noqa: E402
from src.data_agents.canonical_v2.path_eligibility import (  # noqa: E402
    PathEligibilityResult,
)
from src.data_agents.canonical_v2.relationship_projection import (  # noqa: E402
    RelationshipProjectionResult,
)


class ServingPackResealError(RuntimeError):
    """The source pack/index inputs cannot produce an exact resealed pack."""


@dataclass(frozen=True, slots=True)
class ResealSummary:
    pack_dir: Path
    release_id: str
    generator_run_id: str
    manifest: dict[str, Any]
    file_sizes: dict[str, int]
    phase_seconds: dict[str, float] = field(default_factory=dict)


class _ManifestEmbeddingStub:
    """Identity-only embedding port for the dogfood open; it never embeds."""

    def __init__(self, *, model_id: str) -> None:
        self.model_id = model_id
        self.dimension = 1

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        raise ServingPackResealError("serving pack reseal must not embed")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_json(path: Path, value: Any) -> int:
    content = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    path.write_bytes(content)
    return len(content)


def _required_absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("an explicit absolute path is required")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reseal one half-sealed Canonical V2 serving pack"
    )
    parser.add_argument("--source-pack", required=True, type=_required_absolute_path)
    parser.add_argument("--index-root", required=True, type=_required_absolute_path)
    parser.add_argument("--pack-dir", required=True, type=_required_absolute_path)
    parser.add_argument("--generator-run-id", required=True)
    return parser


def _prepare_fresh_pack_dir(pack_dir: Path) -> Path:
    normalized = Path(os.path.abspath(os.fspath(pack_dir)))
    for ancestor in (normalized, *normalized.parents):
        if ancestor.is_symlink():
            raise ServingPackResealError(
                "serving pack directory ancestry contains a symlink"
            )
    if normalized.exists():
        raise ServingPackResealError("resealed pack directory must not exist yet")
    if not normalized.parent.is_dir():
        raise ServingPackResealError(
            "resealed pack parent directory must already exist"
        )
    normalized.mkdir()
    return normalized


def _read_live_receipt(index_root: Path) -> IndexProjectionMaterializationReceipt:
    lookup_path = index_root / "lookup.sqlite3"
    if not lookup_path.is_file() or lookup_path.is_symlink():
        raise ServingPackResealError("live index lookup store is missing or unsafe")
    uri = f"file:{lookup_path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT release_id, receipt_json FROM build_receipt"
        ).fetchall()
    if len(rows) != 1:
        raise ServingPackResealError("live index receipt store must hold one receipt")
    try:
        return IndexProjectionMaterializationReceipt.model_validate(
            json.loads(rows[0][1])
        )
    except ValueError as exc:
        raise ServingPackResealError(
            "live index receipt failed typed validation"
        ) from exc


def reseal_serving_pack(
    *,
    source_pack: Path,
    index_root: Path,
    pack_dir: Path,
    generator_run_id: str,
) -> ResealSummary:
    """Materialize and self-verify one resealed pack; fail closed on drift."""

    phases: dict[str, float] = {}
    started = monotonic()

    def mark(phase: str) -> None:
        nonlocal started
        now = monotonic()
        phases[phase] = round(now - started, 3)
        started = now
        print(f"phase={phase} seconds={phases[phase]}", flush=True)

    if not source_pack.is_dir() or source_pack.is_symlink():
        raise ServingPackResealError("source pack directory is missing or unsafe")
    if not index_root.is_dir() or index_root.is_symlink():
        raise ServingPackResealError("index root directory is missing or unsafe")
    index_root = Path(os.path.abspath(os.fspath(index_root)))

    source_manifest = pack_loader.ServingPackManifest.model_validate_json(
        (source_pack / pack_loader.PACK_MANIFEST_FILENAME).read_bytes()
    )
    if source_manifest.schema_version != pack_loader.PACK_SCHEMA_VERSION:
        raise ServingPackResealError("source pack schema version differs")
    release_id = source_manifest.release_id

    marker_bytes = (index_root / pack_loader.PACK_MARKER_FILENAME).read_bytes()
    marker = json.loads(marker_bytes)
    if marker.get("schema_version") != "canonical-v2-isolated-index-target-v1":
        raise ServingPackResealError("live index marker schema differs")
    if marker.get("release_id") != release_id:
        raise ServingPackResealError("live index marker release differs")
    if marker.get("target_id") != f"index:{release_id}":
        raise ServingPackResealError("live index marker target differs")
    if marker.get("root") != str(index_root):
        raise ServingPackResealError("live index marker root differs")
    forbidden_paths = tuple(
        Path(value) for value in marker.get("forbidden_milvus_paths") or ()
    )
    if len(forbidden_paths) != 1 or not forbidden_paths[0].is_absolute():
        raise ServingPackResealError("live index marker forbidden paths differ")
    marker_sha256 = _sha256_bytes(marker_bytes)
    if (source_pack / pack_loader.PACK_MARKER_FILENAME).read_bytes() != marker_bytes:
        raise ServingPackResealError("source pack marker copy differs from live marker")
    mark("inputs_verified")

    receipt = _read_live_receipt(index_root)
    if receipt.release_id != release_id or receipt.target_id != f"index:{release_id}":
        raise ServingPackResealError("live index receipt identity differs")
    embedding_models = {
        projection.embedding_model for projection in receipt.index_projections
    }
    if len(embedding_models) != 1:
        raise ServingPackResealError(
            "live index receipt embedding model is not uniform"
        )
    embedding_model_id = embedding_models.pop()

    policy_snapshot = pack_loader._parse_model(
        IndexProjectionPolicySnapshot,
        source_manifest.index_policy_snapshot,
        owner="source manifest.index_policy_snapshot",
    )
    if policy_snapshot.embedding_model != embedding_model_id:
        raise ServingPackResealError(
            "carried index policy snapshot embedding model differs from the receipt"
        )
    rebuild_decisions = pack_loader._parse_models(
        IndexProjectionRebuildDecision,
        list(source_manifest.index_rebuild_decisions),
        owner="source manifest.index_rebuild_decisions",
    )
    mark("carried_fields_verified")

    destination = _prepare_fresh_pack_dir(pack_dir)
    file_sizes: dict[str, int] = {}
    file_hashes: dict[str, str] = {}
    for name in (
        *pack_loader.PACK_INDEX_FILENAMES,
        pack_loader.PACK_MARKER_FILENAME,
        pack_loader.PACK_RELATIONSHIPS_FILENAME,
        pack_loader.PACK_INSTITUTION_CATALOG_FILENAME,
    ):
        source = source_pack / name
        if not source.is_file() or source.is_symlink():
            raise ServingPackResealError(f"source pack file is missing: {name}")
        target_path = destination / name
        shutil.copyfile(source, target_path)
        file_hashes[name] = pack_loader._sha256_file(target_path)
        file_sizes[name] = target_path.stat().st_size
    mark("pack_files_copied")

    relationships = json.loads(
        (destination / pack_loader.PACK_RELATIONSHIPS_FILENAME).read_bytes()
    )
    internal_result = pack_loader._parse_model(
        InternalReferenceProjectionResult,
        relationships.get("internal_reference_projection_result"),
        owner="relationships.internal_reference_projection_result",
    )
    relationship_result = pack_loader._parse_model(
        RelationshipProjectionResult,
        relationships.get("relationship_projection_result"),
        owner="relationships.relationship_projection_result",
    )
    candidate_result = pack_loader._parse_model(
        CandidateProjectionResult,
        relationships.get("candidate_projection_result"),
        owner="relationships.candidate_projection_result",
    )
    if (
        relationship_result.release_id != release_id
        or candidate_result.release_id != release_id
    ):
        raise ServingPackResealError("relationship authority release differs")
    eligibility_results = pack_loader._parse_models(
        PathEligibilityResult,
        relationships.get("public_path_eligibility_results"),
        owner="relationships.public_path_eligibility_results",
    )
    relationship_request_raw = pack_loader._require_mapping(
        relationships.get("relationship_projection_request"),
        owner="relationships.relationship_projection_request",
    )
    internal_request = pack_loader._build_internal_reference_request(
        pack_loader._require_mapping(
            relationship_request_raw.get("internal_reference_projection_request"),
            owner="relationship request.internal_reference_projection_request",
        )
    )
    relationship_request = pack_loader._build_relationship_request(
        relationship_request_raw,
        internal_request=internal_request,
        internal_result=internal_result,
    )
    relationship_request_sha256 = pack_loader._canonical_sha256(
        relationship_request.model_dump(mode="json")
    )
    mark("relationship_request_rebuilt")

    candidate_request_scalars = pack_loader._require_mapping(
        relationships.get("candidate_projection_request_scalars"),
        owner="relationships.candidate_projection_request_scalars",
    )
    candidate_request = CandidateProjectionRequest.model_construct(
        release_id=pack_loader._require_str(
            candidate_request_scalars.get("release_id"),
            owner="candidate request release_id",
        ),
        build_run_id=pack_loader._require_str(
            candidate_request_scalars.get("build_run_id"),
            owner="candidate request build_run_id",
        ),
        as_of=pack_loader._parse_datetime(
            candidate_request_scalars.get("as_of"),
            owner="candidate request as_of",
        ),
        projection_schema_version=pack_loader._require_str(
            candidate_request_scalars.get("projection_schema_version"),
            owner="candidate request projection_schema_version",
        ),
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
    )
    index_scalars = pack_loader._require_mapping(
        relationships.get("index_projection_scalars"),
        owner="relationships.index_projection_scalars",
    )
    index_request = IndexProjectionRequest.model_construct(
        candidate_projection_request=candidate_request,
        candidate_projection_result=candidate_result,
        public_path_eligibility_requests=tuple(
            pack_loader._require_list(
                relationships.get("public_path_eligibility_requests"),
                owner="relationships.public_path_eligibility_requests",
            )
        ),
        public_path_eligibility_results=eligibility_results,
        index_projection_version=pack_loader._require_str(
            index_scalars.get("index_projection_version"),
            owner="index projection version",
        ),
        vector_schema_version=pack_loader._require_str(
            index_scalars.get("vector_schema_version"),
            owner="index vector schema version",
        ),
        embedding_model=pack_loader._require_str(
            index_scalars.get("embedding_model"), owner="index embedding model"
        ),
        internal_auxiliary_policy_version=pack_loader._require_str(
            index_scalars.get("internal_auxiliary_policy_version"),
            owner="index internal auxiliary policy version",
        ),
        build_mode=pack_loader._require_str(
            index_scalars.get("build_mode"), owner="index build mode"
        ),
        prior_accepted_snapshot=index_scalars.get("prior_accepted_snapshot"),
    )
    index_request_sha256 = pack_loader._canonical_sha256(
        index_request.model_dump(mode="json")
    )
    del relationship_request, candidate_request, index_request
    mark("index_request_rebuilt")

    index_target = IsolatedIndexTarget(
        root=index_root,
        target_id=f"index:{release_id}",
        release_id=release_id,
        forbidden_milvus_paths=forbidden_paths,
        marker_sha256=marker_sha256,
    )
    snapshot = open_manifest_verified_index_snapshot(
        index_target,
        expected_embedding_model_id=embedding_model_id,
    )
    mark("index_snapshot_opened")

    index_result = IndexProjectionResult.model_construct(
        release_id=release_id,
        points=snapshot.points,
        lookup_documents=snapshot.lookup_documents,
        expected_index_projections=snapshot.receipt.index_projections,
        actual_index_projections=snapshot.receipt.index_projections,
        expected_lookup_projections=snapshot.receipt.lookup_projections,
        actual_lookup_projections=snapshot.receipt.lookup_projections,
        rebuild_decisions=rebuild_decisions,
        policy_snapshot=policy_snapshot,
        content_sha256="0" * 64,
    )
    index_result_content_sha256 = pack_loader._canonical_sha256(
        index_result.model_dump(mode="json", exclude={"content_sha256"})
    )
    del index_result, snapshot
    mark("index_result_rebuilt")

    old_build_manifest = pack_loader._parse_model(
        BuildManifest,
        source_manifest.build_manifest,
        owner="source manifest.build_manifest",
    )
    build_manifest_payload = old_build_manifest.model_dump(
        mode="json",
        exclude={"manifest_sha256"},
    )
    build_manifest_payload["published_projections"] = [
        projection.model_dump(mode="json")
        for projection in candidate_result.published_projections
    ]
    build_manifest_sha256 = pack_loader._canonical_sha256(build_manifest_payload)
    build_manifest = BuildManifest.model_validate(
        {**build_manifest_payload, "manifest_sha256": build_manifest_sha256}
    )
    old_release_verification = pack_loader._parse_model(
        ReleaseVerification,
        source_manifest.release_verification,
        owner="source manifest.release_verification",
    )
    release_verification = ReleaseVerification.model_validate(
        {
            **old_release_verification.model_dump(mode="json"),
            "candidate_release_id": release_id,
            "manifest_sha256": build_manifest.manifest_sha256,
        }
    )
    mark("release_bindings_resealed")

    catalog_envelope = json.loads(
        (destination / pack_loader.PACK_INSTITUTION_CATALOG_FILENAME).read_bytes()
    )
    institution_catalog = pack_loader._parse_model(
        InstitutionCatalog,
        pack_loader._require_mapping(catalog_envelope, owner="catalog").get(
            "institution_catalog"
        ),
        owner="institution_catalog",
    )
    if institution_catalog.release_id != release_id:
        raise ServingPackResealError("institution catalog release differs")

    manifest: dict[str, Any] = {
        "schema_version": pack_loader.PACK_SCHEMA_VERSION,
        "pack_id": source_manifest.pack_id,
        "release_id": release_id,
        "index_root": str(index_root),
        "index_target_id": f"index:{release_id}",
        "index_marker_sha256": marker_sha256,
        "index_forbidden_milvus_paths": [str(path) for path in forbidden_paths],
        "embedding_model_id": embedding_model_id,
        "generator_run_id": generator_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build_manifest": build_manifest.model_dump(mode="json"),
        "index_policy_snapshot": policy_snapshot.model_dump(mode="json"),
        "index_rebuild_decisions": [
            decision.model_dump(mode="json") for decision in rebuild_decisions
        ],
        "index_result_content_sha256": index_result_content_sha256,
        "release_verification": release_verification.model_dump(mode="json"),
        "relationship_request_sha256": relationship_request_sha256,
        "relationship_result_content_sha256": relationship_result.content_sha256,
        "index_projection_request_sha256": index_request_sha256,
        "candidate_projection_result_content_sha256": candidate_result.content_sha256,
        "internal_reference_projection_result_content_sha256": (
            internal_result.content_sha256
        ),
        "institution_catalog_content_sha256": institution_catalog.content_sha256,
        "files": file_hashes,
    }
    pack_loader.ServingPackManifest.model_validate(manifest)
    file_sizes[pack_loader.PACK_MANIFEST_FILENAME] = _write_json(
        destination / pack_loader.PACK_MANIFEST_FILENAME,
        manifest,
    )
    mark("manifest_written")

    del (
        relationships,
        relationship_request_raw,
        internal_request,
        internal_result,
        relationship_result,
        candidate_result,
        eligibility_results,
    )
    gc.collect()

    authority = pack_loader.open_serving_pack_authority(
        pack_dir=destination,
        expected_release_id=release_id,
        expected_index_marker_sha256=marker_sha256,
        expected_forbidden_milvus_path=forbidden_paths[0],
        embedding_adapter=_ManifestEmbeddingStub(model_id=embedding_model_id),
    )
    mark("dogfood_open")

    domain_counts = Counter(
        str(document.domain)
        for document in authority.index_snapshot.lookup_documents
    )
    summary = {
        "pack_dir": str(destination),
        "release_id": release_id,
        "generator_run_id": generator_run_id,
        "lookup_documents": len(authority.index_snapshot.lookup_documents),
        "points": len(authority.index_snapshot.points),
        "domain_counts": dict(sorted(domain_counts.items())),
        "file_sizes": file_sizes,
        "phase_seconds": phases,
    }
    print("reseal_summary=" + repr(summary), flush=True)
    return ResealSummary(
        pack_dir=destination,
        release_id=release_id,
        generator_run_id=generator_run_id,
        manifest=manifest,
        file_sizes=file_sizes,
        phase_seconds=phases,
    )


def main(args: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(args)
    try:
        reseal_serving_pack(
            source_pack=namespace.source_pack,
            index_root=namespace.index_root,
            pack_dir=namespace.pack_dir,
            generator_run_id=namespace.generator_run_id,
        )
    except ServingPackResealError as exc:
        print(f"serving pack reseal failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"serving pack reseal failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
