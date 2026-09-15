"""Build one Serving Pack from the committed r8 Candidate build envelope.

The pack is the seconds-level boot input for ``--serve --serve-existing``:
it carries exactly the serving authority the 426MB envelope carries, but in a
form the loader can verify and mount without re-running the deterministic
index/candidate/relationship replays (this script proves them once, at
generation time).

Usage (from ``apps/miroflow-agent``)::

    uv run python ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py \
        --envelope ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/complete-candidate-build-envelope.json \
        --index-root /var/tmp/mirothinker-canonical-v2-s12c/r8/index \
        --pack-dir /var/tmp/mirothinker-canonical-v2-s12c/r8/serving-pack \
        --expected-release-id candidate-s12c-20260726-r8 \
        --generator-run-id s12c-serving-pack-20260730-r1

The script is read-only against the index root: it copies (never modifies)
``lookup.sqlite3``, the index marker, and — for the v1 pack contract —
``milvus.db`` into the pack. It then dogfoods the pack through the real loader
and refuses to ship a pack whose reconstructed authority differs from the
envelope in any compared field. ``--pack-schema-version canonical-v2-serving-pack-v2``
seals the lookup-only contract (no Milvus file; the points come from the
``index_point`` table of an already-converted index root).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
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

from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_read_isolated as isolated_read,
)
from src.data_agents.canonical_v2 import (  # noqa: E402
    serving_pack_loader as pack_loader,
)
from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    IsolatedIndexTarget,
    has_lookup_index_points,
    open_manifest_verified_index_snapshot,
)
from src.data_agents.canonical_v2.knowledge_build_isolated import (  # noqa: E402
    CompleteCandidateBuildEnvelope,
)


class ServingPackBuildError(RuntimeError):
    """The envelope/index inputs cannot produce an exact serving pack."""


@dataclass(frozen=True, slots=True)
class ServingPackSummary:
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
        raise ServingPackBuildError("serving pack generation must not embed")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


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
        description="Build one verified Canonical V2 serving pack"
    )
    parser.add_argument("--envelope", required=True, type=_required_absolute_path)
    parser.add_argument("--index-root", required=True, type=_required_absolute_path)
    parser.add_argument("--pack-dir", required=True, type=_required_absolute_path)
    parser.add_argument("--expected-release-id", required=True)
    parser.add_argument("--generator-run-id", required=True)
    parser.add_argument(
        "--pack-schema-version",
        choices=(pack_loader.PACK_SCHEMA_VERSION, pack_loader.PACK_SCHEMA_VERSION_V2),
        default=pack_loader.PACK_SCHEMA_VERSION,
        help="pack contract to seal: v1 registers milvus.db, v2 does not",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="hard-link the index artifacts instead of copying them",
    )
    return parser


def _rebound_index_target(
    *,
    index_root: Path,
    expected_release_id: str,
    expected_target_id: str,
) -> Any:
    """Bind one v2 seal to the marker of the index root it copies.

    Reads the marker of ``index_root``, refuses any identity drift, and returns
    the ``IsolatedIndexTarget`` the pack manifest and the dogfood open use.
    """

    marker_path = index_root / pack_loader.PACK_MARKER_FILENAME
    if not marker_path.is_file() or marker_path.is_symlink():
        raise ServingPackBuildError("v2 index root marker is missing or unsafe")
    marker_bytes = marker_path.read_bytes()
    try:
        marker = json.loads(marker_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServingPackBuildError("v2 index root marker is invalid JSON") from exc
    if marker.get("schema_version") != "canonical-v2-isolated-index-target-v1":
        raise ServingPackBuildError("v2 index root marker schema differs")
    if marker.get("root") != str(index_root):
        raise ServingPackBuildError("v2 index root marker root differs")
    if marker.get("release_id") != expected_release_id:
        raise ServingPackBuildError("v2 index root marker release differs")
    if marker.get("target_id") != expected_target_id:
        raise ServingPackBuildError("v2 index root marker target differs")
    forbidden = tuple(Path(value) for value in marker.get("forbidden_milvus_paths") or ())
    if not forbidden or any(not path.is_absolute() for path in forbidden):
        raise ServingPackBuildError("v2 index root marker forbidden paths differ")
    return IsolatedIndexTarget(
        root=index_root,
        target_id=expected_target_id,
        release_id=expected_release_id,
        forbidden_milvus_paths=forbidden,
        marker_sha256=_sha256_bytes(marker_bytes),
    )


def _prepare_pack_dir(pack_dir: Path) -> Path:
    normalized = Path(os.path.abspath(os.fspath(pack_dir)))
    for ancestor in (normalized, *normalized.parents):
        if ancestor.is_symlink():
            raise ServingPackBuildError(
                "serving pack directory ancestry contains a symlink"
            )
    if normalized.exists():
        if not normalized.is_dir() or any(normalized.iterdir()):
            raise ServingPackBuildError("serving pack directory must be fresh or empty")
    else:
        if not normalized.parent.is_dir():
            raise ServingPackBuildError(
                "serving pack parent directory must already exist"
            )
        normalized.mkdir()
    return normalized


def build_serving_pack(
    *,
    envelope_path: Path,
    index_root: Path,
    pack_dir: Path,
    expected_release_id: str,
    generator_run_id: str,
    pack_schema_version: str = pack_loader.PACK_SCHEMA_VERSION,
    link: bool = False,
) -> ServingPackSummary:
    """Materialize and self-verify one serving pack; fail closed on any drift."""

    started = monotonic()
    if not envelope_path.is_file() or envelope_path.is_symlink():
        raise ServingPackBuildError("build envelope must be an explicit regular file")
    envelope = CompleteCandidateBuildEnvelope.model_validate_json(
        envelope_path.read_bytes(),
        context={"external_content_addressed": True},
    )
    print(f"phase=envelope_validate seconds={monotonic() - started:.3f}", flush=True)
    handoff = envelope.consumer_handoff
    return build_serving_pack_from_authority(
        release_bundle=handoff.release_bundle,
        index_projection_request=handoff.index_projection_request,
        institution_catalog=handoff.institution_catalog,
        release_verification=handoff.release_verification,
        index_root=index_root,
        pack_dir=pack_dir,
        expected_release_id=expected_release_id,
        generator_run_id=generator_run_id,
        pack_schema_version=pack_schema_version,
        link=link,
    )


def build_serving_pack_from_authority(
    *,
    release_bundle: Any,
    index_projection_request: Any,
    institution_catalog: Any,
    release_verification: Any,
    index_root: Path,
    pack_dir: Path,
    expected_release_id: str,
    generator_run_id: str,
    pack_schema_version: str = pack_loader.PACK_SCHEMA_VERSION,
    link: bool = False,
) -> ServingPackSummary:
    """Materialize one serving pack from an in-memory serving authority.

    ``pack_schema_version`` selects the pack contract: v1 (the default, the
    Milvus-registered shape) or v2 (lookup-only, no Milvus file, points read
    from the release lookup store). A v2 seal requires an index root that is
    already in v2 form; producing one from a v1 root is the migration step
    (``convert_isolated_index_to_v2``), not a silent conversion here.
    """

    index_filenames = pack_loader.pack_index_filenames(pack_schema_version)
    point_store = pack_loader.pack_point_store(pack_schema_version)
    phases: dict[str, float] = {}
    started = monotonic()

    def mark(phase: str) -> None:
        nonlocal started
        now = monotonic()
        phases[phase] = round(now - started, 3)
        started = now
        print(f"phase={phase} seconds={phases[phase]}", flush=True)

    bundle = release_bundle
    index_request = index_projection_request
    release_id = bundle.release_id
    if release_id != expected_release_id:
        raise ServingPackBuildError("release differs from the expected one")
    if (
        bundle.relationship_projection_request is None
        or bundle.relationship_projection_result is None
    ):
        raise ServingPackBuildError(
            "authority lacks relationship publication authority"
        )

    target = bundle.index_target
    expected_index_root = Path(os.path.abspath(os.fspath(index_root)))
    if pack_schema_version == pack_loader.PACK_SCHEMA_VERSION_V2:
        # A v2 seal binds the artifacts it actually copies: the envelope's
        # index target is the build-side (v1) root, while the converted v2 root
        # is a re-materialization of the same authority, carrying its own marker
        # whose bytes this seal registers and whose receipt the loader re-checks.
        target = _rebound_index_target(
            index_root=expected_index_root,
            expected_release_id=expected_release_id,
            expected_target_id=bundle.index_target.target_id,
        )
    elif Path(os.path.abspath(os.fspath(target.root))) != expected_index_root:
        raise ServingPackBuildError(
            "index target root differs from the explicit index root"
        )
    if target.target_id != f"index:{expected_release_id}":
        raise ServingPackBuildError("index target id differs")
    embedding_model_id = bundle.index_result.policy_snapshot.embedding_model

    if pack_schema_version == pack_loader.PACK_SCHEMA_VERSION_V2:
        if not has_lookup_index_points(target.root / "lookup.sqlite3"):
            raise ServingPackBuildError(
                "v2 seal requires a converted index root (index_point store); "
                "run the v1→v2 index migration first"
            )
        if (target.root / "milvus.db").exists():
            raise ServingPackBuildError(
                "v2 seal requires an index root without milvus.db"
            )

    snapshot = open_manifest_verified_index_snapshot(
        target,
        expected_embedding_model_id=embedding_model_id,
        point_store=point_store,
    )
    isolated_read._require_snapshot_matches_bundle(snapshot, bundle)
    mark("index_snapshot_verify")

    destination = _prepare_pack_dir(pack_dir)

    file_sizes: dict[str, int] = {}
    index_sources = tuple(
        (target.root / name, name) for name in index_filenames
    ) + (
        (
            target.root / pack_loader.PACK_MARKER_FILENAME,
            pack_loader.PACK_MARKER_FILENAME,
        ),
    )
    file_hashes: dict[str, str] = {}
    for source, name in index_sources:
        if not source.is_file() or source.is_symlink():
            raise ServingPackBuildError(f"index artifact is missing: {source.name}")
        content = source.read_bytes()
        file_hashes[name] = _sha256_bytes(content)
        target_path = destination / name
        if link:
            os.link(source, target_path)
        else:
            shutil.copyfile(source, target_path)
        file_sizes[name] = len(content)
    mark("index_artifacts_copied")

    relationship_request_dump = bundle.relationship_projection_request.model_dump(
        mode="json"
    )
    relationship_request_sha256 = _canonical_sha256(relationship_request_dump)
    index_request_dump = index_request.model_dump(mode="json")
    index_request_sha256 = _canonical_sha256(index_request_dump)
    candidate_request = index_request.candidate_projection_request
    relationships_document = {
        "schema_version": pack_loader.PACK_RELATIONSHIPS_SCHEMA_VERSION,
        "release_id": release_id,
        "relationship_projection_request": relationship_request_dump,
        "relationship_projection_result": (
            bundle.relationship_projection_result.model_dump(mode="json")
        ),
        "candidate_projection_result": index_request_dump[
            "candidate_projection_result"
        ],
        "internal_reference_projection_result": index_request_dump[
            "candidate_projection_request"
        ]["internal_reference_projection_result"],
        "candidate_projection_request_scalars": {
            "release_id": candidate_request.release_id,
            "build_run_id": candidate_request.build_run_id,
            "as_of": index_request_dump["candidate_projection_request"]["as_of"],
            "projection_schema_version": (candidate_request.projection_schema_version),
        },
        "public_path_eligibility_requests": index_request_dump[
            "public_path_eligibility_requests"
        ],
        "public_path_eligibility_results": index_request_dump[
            "public_path_eligibility_results"
        ],
        "index_projection_scalars": {
            "index_projection_version": index_request.index_projection_version,
            "vector_schema_version": index_request.vector_schema_version,
            "embedding_model": index_request.embedding_model,
            "internal_auxiliary_policy_version": (
                index_request.internal_auxiliary_policy_version
            ),
            "build_mode": index_request.build_mode,
            "prior_accepted_snapshot": index_request_dump["prior_accepted_snapshot"],
        },
    }
    # Contract port C2.1p: pass the multi-value enrichment field through only
    # when the envelope carries it, so both envelope generations seal cleanly.
    if "supplementary_field_values" in index_request_dump:
        relationships_document["index_projection_scalars"][
            "supplementary_field_values"
        ] = index_request_dump["supplementary_field_values"]
    file_sizes[pack_loader.PACK_RELATIONSHIPS_FILENAME] = _write_json(
        destination / pack_loader.PACK_RELATIONSHIPS_FILENAME,
        relationships_document,
    )
    catalog_document = {
        "schema_version": pack_loader.PACK_INSTITUTION_CATALOG_SCHEMA_VERSION,
        "release_id": release_id,
        "institution_catalog": institution_catalog.model_dump(mode="json"),
    }
    file_sizes[pack_loader.PACK_INSTITUTION_CATALOG_FILENAME] = _write_json(
        destination / pack_loader.PACK_INSTITUTION_CATALOG_FILENAME,
        catalog_document,
    )
    mark("authority_documents_written")

    for name in (
        pack_loader.PACK_RELATIONSHIPS_FILENAME,
        pack_loader.PACK_INSTITUTION_CATALOG_FILENAME,
    ):
        file_hashes[name] = _sha256_bytes((destination / name).read_bytes())

    manifest = {
        "schema_version": pack_schema_version,
        "pack_id": f"serving-pack:{release_id}",
        "release_id": release_id,
        "index_root": str(target.root),
        "index_target_id": target.target_id,
        "index_marker_sha256": target.marker_sha256,
        "index_forbidden_milvus_paths": [
            str(path) for path in target.forbidden_milvus_paths
        ],
        "embedding_model_id": embedding_model_id,
        "generator_run_id": generator_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build_manifest": bundle.manifest.model_dump(mode="json"),
        "index_policy_snapshot": bundle.index_result.policy_snapshot.model_dump(
            mode="json"
        ),
        "index_rebuild_decisions": [
            decision.model_dump(mode="json")
            for decision in bundle.index_result.rebuild_decisions
        ],
        "index_result_content_sha256": bundle.index_result.content_sha256,
        "release_verification": release_verification.model_dump(mode="json"),
        "relationship_request_sha256": relationship_request_sha256,
        "relationship_result_content_sha256": (
            bundle.relationship_projection_result.content_sha256
        ),
        "index_projection_request_sha256": index_request_sha256,
        "candidate_projection_result_content_sha256": (
            index_request.candidate_projection_result.content_sha256
        ),
        "internal_reference_projection_result_content_sha256": (
            candidate_request.internal_reference_projection_result.content_sha256
        ),
        "institution_catalog_content_sha256": institution_catalog.content_sha256,
        "files": file_hashes,
    }
    file_sizes[pack_loader.PACK_MANIFEST_FILENAME] = _write_json(
        destination / pack_loader.PACK_MANIFEST_FILENAME,
        manifest,
    )
    mark("manifest_written")

    forbidden = target.forbidden_milvus_paths
    if len(forbidden) != 1:
        raise ServingPackBuildError(
            "serving pack expects exactly one forbidden Milvus path"
        )
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=destination,
        expected_release_id=expected_release_id,
        expected_index_marker_sha256=target.marker_sha256,
        expected_forbidden_milvus_path=forbidden[0],
        embedding_adapter=_ManifestEmbeddingStub(model_id=embedding_model_id),
    )
    rebuilt = authority.release_bundle
    if (
        authority.manifest.schema_version != pack_schema_version
        or rebuilt.index_result != bundle.index_result
        or rebuilt.relationship_projection_result
        != bundle.relationship_projection_result
        or authority.index_projection_request.candidate_projection_result
        != index_request.candidate_projection_result
        or authority.institution_catalog != institution_catalog
        or authority.release_verification != release_verification
    ):
        raise ServingPackBuildError(
            "reloaded serving pack authority differs from the envelope"
        )
    mark("dogfood_open")
    print(
        "serving_pack_summary="
        + repr(
            {
                "pack_dir": str(destination),
                "release_id": release_id,
                "file_sizes": file_sizes,
                "phase_seconds": phases,
            }
        ),
        flush=True,
    )
    return ServingPackSummary(
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
        build_serving_pack(
            envelope_path=namespace.envelope,
            index_root=namespace.index_root,
            pack_dir=namespace.pack_dir,
            expected_release_id=namespace.expected_release_id,
            generator_run_id=namespace.generator_run_id,
            pack_schema_version=namespace.pack_schema_version,
            link=namespace.link,
        )
    except ServingPackBuildError as exc:
        print(f"serving pack build failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"serving pack build failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
