"""Serving Pack loader: seconds-level boot for the isolated Candidate server.

Today ``--serve --serve-existing`` parses the ~426MB build envelope and then
re-derives the complete candidate/index/relationship graph several times over
(once per composition factory) before the first request can be served. The
Serving Pack replaces that envelope-side input with a prebuilt directory:

.. code-block:: text

    serving-pack/
      manifest.json            # pack identity, small authority models, file hashes
      relationships.json       # relationship/candidate/internal/eligibility authority
      institution_catalog.json # the release institution catalog
      lookup.sqlite3           # copied index artifacts (byte copies of the
      milvus.db                # accepted isolated index, bound by per-file hash)
      .canonical-v2-isolated-index-target.json   # index marker copy

With ``manifest.json: schema_version = canonical-v2-serving-pack-v2`` the pack
registers ``lookup.sqlite3`` + marker + relationships + catalog and carries no
``milvus.db`` at all: the index points are read from the release lookup store's
``index_point`` table, and the boot path never imports ``pymilvus``. v1 packs
keep the exact v1 code path (see
``openspec/changes/drop-milvus-from-serving-pack/design.md``).

The on-disk index marker binds the absolute index root, so the pack is bound
to the index root it was generated from (recorded in ``manifest.json``); the
loader refuses any other root. This keeps every query-time trace (target
marker hash, evidence IDs, plan bindings) byte-identical to the envelope path.

The loader verifies the manifest and per-file hashes, opens the index through
:func:`open_manifest_verified_index_snapshot` (the same manifest-verified fast
open as ``CANONICAL_V2_FAST_BOOT=1``), reconstructs the release authority from
the pack files, and composes the same planner/knowledge-read object graph that
:func:`create_isolated_release_query_planner` and
:func:`create_isolated_release_knowledge_read` produce — minus the redundant
deterministic replays, which the pack generator already proved exact.

Graph fields that serving only ever *serializes* (for content-hash binding in
evidence traces) are carried as raw JSON subtrees and mounted into the
reconstructed models with ``model_construct``; fields that serving *reads* are
fully parsed. Every reconstructed giant model is re-hashed at boot against the
generator-recorded canonical SHA-256, so any drift refuses the boot.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import logging
import math
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import Any, Literal, cast

import numpy as np
import pydantic
from pydantic import Field

from . import knowledge_read_isolated as iso
from . import manual_recall_points
from . import serving_timing
from .candidate_projection import (
    CandidateProjectionRequest,
    CandidateProjectionResult,
)
from .contracts import (
    BuildManifest,
    ContractModel,
    PolicyReference,
    PublishedRelease,
    RelationshipAssertion,
    ReleaseState,
    ReleaseVerification,
    SourceAssertion,
)
from .domain_projection import DomainProjectionRequest
from .domain_projection_models import CompanyProjection, ProfessorProjection
from .index_projection import (
    IndexProjectionPolicySnapshot,
    IndexProjectionRebuildDecision,
    IndexProjectionRequest,
    IndexProjectionResult,
)
from .index_projection_isolated import (
    EmbeddingAdapter,
    IndexPointStore,
    IsolatedIndexSnapshot,
    IsolatedIndexTarget,
    POINT_STORE_LOOKUP,
    POINT_STORE_MILVUS,
    open_manifest_verified_index_snapshot,
)
from .internal_reference_projection import (
    InternalReferenceProjectionRequest,
    InternalReferenceProjectionResult,
)
from .knowledge_read import (
    AcceptedIdentityLookupRequest,
    AmbiguityPolicy,
    IdentityFusionRequest,
    InstitutionCatalog,
    KnowledgeRead,
    LaneRequest,
    PlanningReleaseBinding,
    QueryPlanningPolicy,
    QueryPlanningRequest,
    RerankRequest,
    RetrievalLaneResult,
    SufficiencyDecisionRequest,
    SupplementalRequest,
    WebHandleResolutionRequest,
    WebSearchPolicy,
    WebSnapshotPolicy,
    create_ephemeral_knowledge_read,
    create_ephemeral_query_planner,
)
from .path_eligibility import PathEligibilityRequest, PathEligibilityResult
from .relationship_projection import (
    RelationshipCatalogIdentity,
    RelationshipDecisionInput,
    RelationshipProjectionCandidate,
    RelationshipProjectionRequest,
    RelationshipProjectionResult,
    RetainedAssertionReference,
    SourceCanonicalAssignment,
    TypedRelationshipAssertionInput,
)
from .release_publication_isolated import IsolatedReleaseBundle

_LOGGER = logging.getLogger(__name__)

PACK_SCHEMA_VERSION = "canonical-v2-serving-pack-v1"
PACK_SCHEMA_VERSION_V2 = "canonical-v2-serving-pack-v2"
PACK_RELATIONSHIPS_SCHEMA_VERSION = "canonical-v2-serving-pack-relationships-v1"
PACK_INSTITUTION_CATALOG_SCHEMA_VERSION = (
    "canonical-v2-serving-pack-institution-catalog-v1"
)
PACK_MANIFEST_FILENAME = "manifest.json"
PACK_RELATIONSHIPS_FILENAME = "relationships.json"
PACK_INSTITUTION_CATALOG_FILENAME = "institution_catalog.json"
PACK_INDEX_FILENAMES = ("lookup.sqlite3", "milvus.db")
PACK_INDEX_FILENAMES_V2 = ("lookup.sqlite3",)
PACK_MARKER_FILENAME = ".canonical-v2-isolated-index-target.json"

_HASH_CHUNK_BYTES = 8 * 1024 * 1024
_PACKAGE_DIR = Path(__file__).resolve().parent


def pack_index_filenames(schema_version: str) -> tuple[str, ...]:
    """The index files one pack schema registers in its manifest.

    v1 packs carry the Milvus copy; v2 packs carry only the lookup store, whose
    ``index_point`` table is the v2 point authority.
    """

    if schema_version == PACK_SCHEMA_VERSION_V2:
        return PACK_INDEX_FILENAMES_V2
    if schema_version == PACK_SCHEMA_VERSION:
        return PACK_INDEX_FILENAMES
    raise ServingPackIntegrityError("serving pack schema version differs")


def pack_point_store(schema_version: str) -> IndexPointStore:
    """Where the points of one pack schema are read from."""

    if schema_version == PACK_SCHEMA_VERSION_V2:
        return POINT_STORE_LOOKUP
    if schema_version == PACK_SCHEMA_VERSION:
        return POINT_STORE_MILVUS
    raise ServingPackIntegrityError("serving pack schema version differs")


class ServingPackIntegrityError(ValueError):
    """The serving pack is missing, tampered, or bound to another release."""


class ServingPackManifest(ContractModel):
    """Pack identity plus the small serving-authority models."""

    schema_version: Literal[
        "canonical-v2-serving-pack-v1", "canonical-v2-serving-pack-v2"
    ]
    pack_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    index_root: str = Field(min_length=1)
    index_target_id: str = Field(min_length=1)
    index_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_forbidden_milvus_paths: tuple[str, ...]
    embedding_model_id: str = Field(min_length=1)
    generator_run_id: str = Field(min_length=1)
    generated_at: datetime
    build_manifest: dict[str, Any]
    index_policy_snapshot: dict[str, Any]
    index_rebuild_decisions: tuple[dict[str, Any], ...]
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_verification: dict[str, Any]
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_projection_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_projection_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    internal_reference_projection_result_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    institution_catalog_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Identity of the reader that sealed this pack (serving_pack_loader
    # .reader_contract_digest). Optional: every pack sealed before this field
    # existed lacks it, and a missing value means "unknown reader" — the boot
    # then re-derives the two request hashes instead of trusting the seal.
    reader_contract_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    files: dict[str, str]


@dataclass(frozen=True, slots=True)
class ServingPackAuthority:
    """The verified release authority one serving pack boots from."""

    pack_dir: Path
    manifest: ServingPackManifest
    release_bundle: IsolatedReleaseBundle
    index_projection_request: IndexProjectionRequest
    institution_catalog: InstitutionCatalog
    release_verification: ReleaseVerification
    index_snapshot: IsolatedIndexSnapshot


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def reader_contract_digest() -> str:
    """Identity of the code that reconstructs a pack's object graph.

    ``open_serving_pack_authority`` reconstructs the relationship and index
    requests from ``relationships.json`` and, historically, re-derived their
    canonical hashes to prove the reconstruction reproduces what the seal
    recorded (≈137 s of a 440 s boot, measured). That proof only has content when
    the reading code may differ from the sealing code, and it is exactly this
    digest that decides that: a pack records the digest of the reader that sealed
    it, so an equal digest means the reconstruction is a replay and the dumped
    comparison proves nothing new. A different digest — any edit to this package,
    to pydantic, or to the interpreter — falls back to running it.

    The scope is deliberately the whole ``canonical_v2`` package plus the two
    things outside it that can change what a dump looks like. A narrower scope
    would need someone to remember to widen it.
    """

    digest = hashlib.sha256()
    digest.update(f"python={sys.version_info[:3]}\n".encode())
    digest.update(f"pydantic={pydantic.VERSION}\n".encode())
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _reader_contract_matches(
    manifest: ServingPackManifest,
    *,
    verify_reconstruction: bool,
    receipt_used: bool,
) -> bool:
    """May this boot trust the seal's reconstruction instead of replaying it?

    Three conditions, all necessary:

    * ``receipt_used`` — the mount receipt binds this exact manifest file, so the
      fields below are the sealed ones. Without it the manifest is unverified and
      nothing written in it may excuse a check (this is the case a tampered
      manifest hits, and then the reconstruction runs and refuses).
    * the pack names a reader (``None`` on every pack sealed before the field
      existed, which answers no), and
    * that reader is this code — same package, same pydantic, same interpreter.

    ``verify_reconstruction`` answers no unconditionally, which is how the seal
    keeps proving the reconstruction it is about to record a digest for.
    """

    if verify_reconstruction or not receipt_used:
        return False
    recorded = manifest.reader_contract_sha256
    return bool(recorded) and recorded == reader_contract_digest()


def _require_regular_file(pack_dir: Path, name: str) -> Path:
    path = pack_dir / name
    if not path.is_file() or path.is_symlink():
        raise ServingPackIntegrityError(
            f"serving pack file is missing or unsafe: {name}"
        )
    return path


def _read_verified_json(pack_dir: Path, name: str, expected_sha256: str) -> Any:
    return _read_pack_json(pack_dir, name, expected_sha256, verify_sha256=True)


def _read_pack_json(
    pack_dir: Path,
    name: str,
    expected_sha256: str,
    *,
    verify_sha256: bool,
) -> Any:
    """Read one pack JSON document; ``verify_sha256=False`` is the receipt path.

    Skipping the byte hash is only allowed for a file whose identity a
    verified mount receipt already pins (size + first/last-block fingerprint).
    The two JSON documents additionally bind their content one way or the
    other, and never neither: the institution catalog through the authority's
    own checks, relationships.json either through this hash or through the
    reconstructed authority hashes — this hash is what runs instead when the
    pack records the reader digest and the reconstruction is therefore skipped.
    """

    path = _require_regular_file(pack_dir, name)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ServingPackIntegrityError(
            f"serving pack file is unreadable: {name}"
        ) from exc
    if verify_sha256 and hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ServingPackIntegrityError(f"serving pack file hash differs: {name}")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServingPackIntegrityError(
            f"serving pack file is invalid JSON: {name}"
        ) from exc


_MOUNT_RECEIPT_SCHEMA_VERSION = "canonical-v2-serving-mount-receipt-v1"
_MOUNT_BLOCK_BYTES = 64 * 1024


def _mount_receipt_path(pack_dir: Path) -> Path:
    override = os.environ.get("CANONICAL_V2_SERVING_RECEIPT_PATH", "").strip()
    if override:
        return Path(override)
    return pack_dir.parent / f"{pack_dir.name}.mount-receipt.json"


def _file_identity_fingerprint(path: Path) -> dict[str, Any]:
    """Size plus first/last-block hashes: cheap proof a file is the same shape.

    A truncated, appended, or header/footer-swapped copy changes at least one
    of these; the middle of a file is covered by the authority reconstruction
    the loader performs afterwards.
    """

    size = path.stat().st_size
    with path.open("rb") as stream:
        first = hashlib.sha256(stream.read(_MOUNT_BLOCK_BYTES)).hexdigest()
        if size > _MOUNT_BLOCK_BYTES:
            stream.seek(max(size - _MOUNT_BLOCK_BYTES, _MOUNT_BLOCK_BYTES))
            last = hashlib.sha256(stream.read(_MOUNT_BLOCK_BYTES)).hexdigest()
        else:
            last = first
    return {"size": size, "first_block_sha256": first, "last_block_sha256": last}


def _read_mount_receipt(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("schema_version") != _MOUNT_RECEIPT_SCHEMA_VERSION:
        return None
    return cast(dict[str, Any], value)


def _write_mount_receipt(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        # A receipt we cannot persist only costs the next boot the full
        # verification; it must never fail a verified mount.
        _LOGGER.warning("serving pack mount receipt could not be written: %s", path)


def _receipt_binds_mount(
    receipt: dict[str, Any],
    *,
    pack_dir: Path,
    manifest_sha256: str,
    marker_sha256: str,
    identities: dict[str, dict[str, Any]],
) -> bool:
    return (
        receipt.get("pack_dir") == str(pack_dir)
        and receipt.get("pack_manifest_sha256") == manifest_sha256
        and receipt.get("index_marker_sha256") == marker_sha256
        and receipt.get("files") == identities
    )


def _require_mapping(value: object, *, owner: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ServingPackIntegrityError(f"serving pack {owner} must be an object")
    return cast(dict[str, Any], value)


def _require_list(value: object, *, owner: str) -> list[Any]:
    if not isinstance(value, list):
        raise ServingPackIntegrityError(f"serving pack {owner} must be a list")
    return cast(list[Any], value)


def _require_str(value: object, *, owner: str) -> str:
    if not isinstance(value, str) or not value:
        raise ServingPackIntegrityError(f"serving pack {owner} must be a string")
    return value


def _parse_datetime(value: object, *, owner: str) -> datetime:
    text = _require_str(value, owner=owner)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ServingPackIntegrityError(
            f"serving pack {owner} must be an ISO datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ServingPackIntegrityError(f"serving pack {owner} must be timezone-aware")
    return parsed


def _validated_published_release(
    value: PublishedRelease,
    *,
    release_id: str,
) -> PublishedRelease:
    if not isinstance(value, PublishedRelease):
        raise TypeError("published_release must be a PublishedRelease")
    validated = PublishedRelease.model_validate(value.model_dump(mode="json"))
    if validated.state not in {ReleaseState.active, ReleaseState.rolled_back}:
        raise ServingPackIntegrityError("published release is not serviceable")
    if validated.release_id != release_id:
        raise ServingPackIntegrityError(
            "published release differs from the serving pack release"
        )
    return validated


# The pack's projection graph is parsed with its recorded per-object hashes left
# unbound, because by the time this loader returns it has vouched for those bytes
# one way or the other: either it hashed relationships.json, or the reconstruction
# replay below reproduced the request hashes that cover the whole graph — a
# mismatch in either raises, so the optimism here is always confirmed before a
# caller sees the authority. Re-deriving the ~180k sub-object and projection
# hashes this covers costs tens of seconds to re-prove what the seal proved
# (measured 2026-09-20). The other ~221k such validations come from the isolated
# read re-validating projections out of the lookup store
# (knowledge_read_isolated._validated_public_projection, ~:8399); vouching for
# that file is a separate decision and is not claimed here.
_PACK_VALIDATION_CONTEXT = {"allow_unbound_projection_hash": True}


def _parse_models(
    model_type: type[Any],
    values: object,
    *,
    owner: str,
) -> tuple[Any, ...]:
    items = _require_list(values, owner=owner)
    parsed: list[Any] = []
    for index, item in enumerate(items):
        try:
            parsed.append(
                model_type.model_validate(item, context=_PACK_VALIDATION_CONTEXT)
            )
        except ValueError as exc:
            raise ServingPackIntegrityError(
                f"serving pack {owner}[{index}] failed typed validation"
            ) from exc
    return tuple(parsed)


def _parse_model(model_type: type[Any], value: object, *, owner: str) -> Any:
    try:
        return model_type.model_validate(value, context=_PACK_VALIDATION_CONTEXT)
    except ValueError as exc:
        raise ServingPackIntegrityError(
            f"serving pack {owner} failed typed validation"
        ) from exc


def _build_internal_reference_request(raw: dict[str, Any]) -> Any:
    """Rebuild the internal request: parsed where serving reads, raw elsewhere.

    Only ``public_domain_projection_request.source_assertions`` is read at
    query time (relationship evidence building); every other subtree is only
    serialized for content-hash binding, so it stays raw JSON. The boot-time
    canonical-hash check on the enclosing requests proves the mix exact.
    """

    public_raw = _require_mapping(
        raw.get("public_domain_projection_request"),
        owner="internal_reference_projection_request.public_domain_projection_request",
    )
    public_request = DomainProjectionRequest.model_construct(
        release_id=_require_str(
            public_raw.get("release_id"), owner="public request release_id"
        ),
        build_run_id=_require_str(
            public_raw.get("build_run_id"), owner="public request build_run_id"
        ),
        as_of=_parse_datetime(public_raw.get("as_of"), owner="public request as_of"),
        projection_version=_require_str(
            public_raw.get("projection_version"),
            owner="public request projection_version",
        ),
        catalog_schema_version=_require_str(
            public_raw.get("catalog_schema_version"),
            owner="public request catalog_schema_version",
        ),
        catalog_version=_require_str(
            public_raw.get("catalog_version"), owner="public request catalog_version"
        ),
        catalog_content_sha256=_require_str(
            public_raw.get("catalog_content_sha256"),
            owner="public request catalog_content_sha256",
        ),
        canonical_identities=_require_list(
            public_raw.get("canonical_identities"),
            owner="public request canonical_identities",
        ),
        source_identity_assignments=_require_list(
            public_raw.get("source_identity_assignments"),
            owner="public request source_identity_assignments",
        ),
        source_assertions=_parse_models(
            SourceAssertion,
            public_raw.get("source_assertions"),
            owner="public request source_assertions",
        ),
        canonical_decisions=_require_list(
            public_raw.get("canonical_decisions"),
            owner="public request canonical_decisions",
        ),
        current_fields=_require_list(
            public_raw.get("current_fields"), owner="public request current_fields"
        ),
        inclusion_result=public_raw.get("inclusion_result"),
    )
    return InternalReferenceProjectionRequest.model_construct(
        release_id=_require_str(
            raw.get("release_id"), owner="internal request release_id"
        ),
        build_run_id=_require_str(
            raw.get("build_run_id"), owner="internal request build_run_id"
        ),
        as_of=_parse_datetime(raw.get("as_of"), owner="internal request as_of"),
        projection_version=_require_str(
            raw.get("projection_version"), owner="internal request projection_version"
        ),
        reference_catalog_identity=raw.get("reference_catalog_identity"),
        public_domain_projection_request=public_request,
        public_domain_projection_result=raw.get("public_domain_projection_result"),
        person_identity_resolution_request=raw.get(
            "person_identity_resolution_request"
        ),
        person_identity_resolution_result=raw.get("person_identity_resolution_result"),
        person_evidence_locators=_require_list(
            raw.get("person_evidence_locators"),
            owner="internal request person_evidence_locators",
        ),
        technology_identity_resolution_request=raw.get(
            "technology_identity_resolution_request"
        ),
        technology_identity_resolution_result=raw.get(
            "technology_identity_resolution_result"
        ),
        technology_evidence_locators=_require_list(
            raw.get("technology_evidence_locators"),
            owner="internal request technology_evidence_locators",
        ),
    )


def _build_relationship_request(
    raw: dict[str, Any],
    *,
    internal_request: Any,
    internal_result: InternalReferenceProjectionResult,
) -> RelationshipProjectionRequest:
    """Rebuild the relationship request with only its query-read fields parsed."""

    request = RelationshipProjectionRequest.model_construct(
        catalog=_parse_model(
            RelationshipCatalogIdentity,
            raw.get("catalog"),
            owner="relationship request catalog",
        ),
        relationship_registry_version=_require_str(
            raw.get("relationship_registry_version"),
            owner="relationship request registry version",
        ),
        relationship_registry_content_sha256=_require_str(
            raw.get("relationship_registry_content_sha256"),
            owner="relationship request registry hash",
        ),
        release_id=_require_str(
            raw.get("release_id"), owner="relationship request release_id"
        ),
        projection_run_id=_require_str(
            raw.get("projection_run_id"), owner="relationship request run id"
        ),
        as_of=_parse_datetime(raw.get("as_of"), owner="relationship request as_of"),
        temporal_comparison_context=raw.get("temporal_comparison_context"),
        decision_policy=_parse_model(
            PolicyReference,
            raw.get("decision_policy"),
            owner="relationship request decision policy",
        ),
        domain_projections=_require_list(
            raw.get("domain_projections"),
            owner="relationship request domain_projections",
        ),
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
        candidates=_parse_models(
            RelationshipProjectionCandidate,
            raw.get("candidates"),
            owner="relationship request candidates",
        ),
        relationship_assertions=_parse_models(
            RelationshipAssertion,
            raw.get("relationship_assertions"),
            owner="relationship request relationship_assertions",
        ),
        typed_relationship_assertions=_parse_models(
            TypedRelationshipAssertionInput,
            raw.get("typed_relationship_assertions"),
            owner="relationship request typed_relationship_assertions",
        ),
        source_canonical_assignments=_parse_models(
            SourceCanonicalAssignment,
            raw.get("source_canonical_assignments"),
            owner="relationship request source_canonical_assignments",
        ),
        decision_inputs=_parse_models(
            RelationshipDecisionInput,
            raw.get("decision_inputs"),
            owner="relationship request decision_inputs",
        ),
        direction_probes=_require_list(
            raw.get("direction_probes"),
            owner="relationship request direction_probes",
        ),
        layer_probes=_require_list(
            raw.get("layer_probes"), owner="relationship request layer_probes"
        ),
        retained_assertions=_parse_models(
            RetainedAssertionReference,
            raw.get("retained_assertions"),
            owner="relationship request retained_assertions",
        ),
        retained_artifacts=_require_list(
            raw.get("retained_artifacts"),
            owner="relationship request retained_artifacts",
        ),
    )
    return request


def open_serving_pack_authority(
    *,
    pack_dir: Path,
    expected_release_id: str,
    expected_index_marker_sha256: str,
    expected_forbidden_milvus_path: Path,
    embedding_adapter: EmbeddingAdapter | None = None,
    verify_reconstruction: bool = False,
) -> ServingPackAuthority:
    """Verify one serving pack and rebuild its release authority, fail closed.

    Every mismatch — identity, file hash, model hash, snapshot inventory —
    raises :class:`ServingPackIntegrityError` (or the underlying integrity
    error from the index open); there is no fallback to the envelope path.
    When ``embedding_adapter`` is supplied its model identity is bound here;
    otherwise the adapter binds later in
    :func:`create_serving_pack_knowledge_read` (the serving bundle loads it).

    ``verify_reconstruction`` forces the two request-hash reconstructions even
    when the pack records this reader's digest. The seal passes it: the seal is
    the earliest layer, so it is the seal that has to prove the reconstruction
    reproduces what it recorded, and every consumer after it may verify the
    receipt instead of replaying the proof (R8 rule ②).
    """

    # R16: the serving process adopts the operator's managed configuration here —
    # once, at startup, never on a request path. A managed file that is absent or
    # unreadable is a no-op, so this cannot fail a boot.
    from .managed_runtime import apply_managed_runtime_config

    apply_managed_runtime_config()

    if not pack_dir.is_absolute():
        raise ServingPackIntegrityError("serving pack directory must be absolute")
    if not pack_dir.is_dir() or pack_dir.is_symlink():
        raise ServingPackIntegrityError("serving pack directory is missing or unsafe")

    manifest_path = _require_regular_file(pack_dir, PACK_MANIFEST_FILENAME)
    try:
        manifest = ServingPackManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ServingPackIntegrityError(
            "serving pack manifest is unreadable or invalid"
        ) from exc
    if manifest.release_id != expected_release_id:
        raise ServingPackIntegrityError("serving pack release differs")
    if manifest.index_target_id != f"index:{expected_release_id}":
        raise ServingPackIntegrityError("serving pack index target differs")
    if manifest.index_marker_sha256 != expected_index_marker_sha256:
        raise ServingPackIntegrityError("serving pack index marker differs")
    if embedding_adapter is not None and (
        getattr(embedding_adapter, "model_id", None) != manifest.embedding_model_id
    ):
        raise ServingPackIntegrityError("serving pack embedding model differs")
    forbidden_paths = tuple(
        Path(value) for value in manifest.index_forbidden_milvus_paths
    )
    if any(not path.is_absolute() for path in forbidden_paths):
        raise ServingPackIntegrityError("serving pack forbidden paths must be absolute")
    expected_forbidden = expected_forbidden_milvus_path.resolve(strict=False)
    if tuple(path.resolve(strict=False) for path in forbidden_paths) != (
        expected_forbidden,
    ):
        raise ServingPackIntegrityError("serving pack forbidden Milvus paths differ")
    index_root = Path(manifest.index_root)
    if not index_root.is_absolute():
        raise ServingPackIntegrityError("serving pack index root must be absolute")
    index_root = index_root.resolve(strict=False)

    expected_files = {
        PACK_RELATIONSHIPS_FILENAME,
        PACK_INSTITUTION_CATALOG_FILENAME,
        PACK_MARKER_FILENAME,
        *pack_index_filenames(manifest.schema_version),
    }
    if set(manifest.files) != expected_files or any(
        not isinstance(value, str) or len(value) != 64
        for value in manifest.files.values()
    ):
        raise ServingPackIntegrityError("serving pack file hash registry differs")

    # Mount identity (serving-index-process-scope T4): the first verified mount
    # of a pack writes a receipt; later mounts prove the same identity from
    # that receipt (marker hash, file sizes, first/last-block fingerprints)
    # instead of re-hashing 1.7GB of artifacts on the user's path. Full hashing
    # stays available (fresh receipt, changed identity, or
    # CANONICAL_V2_SERVING_FULL_VERIFY=1) and everything the loader
    # reconstructs below is still bound to the recorded content hashes.
    mount_started = monotonic()
    full_verify = os.environ.get("CANONICAL_V2_SERVING_FULL_VERIFY", "").strip() == "1"
    receipt_path = _mount_receipt_path(pack_dir)
    manifest_file_sha256 = _sha256_file(manifest_path)
    index_filenames = pack_index_filenames(manifest.schema_version)
    with serving_timing.timed_step("pack.mount_identity"):
        identities = {
            name: _file_identity_fingerprint(_require_regular_file(pack_dir, name))
            for name in (*index_filenames, PACK_MARKER_FILENAME)
        }
    receipt = None if full_verify else _read_mount_receipt(receipt_path)
    receipt_used = receipt is not None and _receipt_binds_mount(
        receipt,
        pack_dir=pack_dir,
        manifest_sha256=manifest_file_sha256,
        marker_sha256=manifest.index_marker_sha256,
        identities=identities,
    )
    serving_timing.bump_counter(
        "pack.mount", receipt_used=receipt_used, full_verify=full_verify
    )
    skip_reconstruction = _reader_contract_matches(
        manifest,
        verify_reconstruction=verify_reconstruction,
        receipt_used=receipt_used,
    )
    if not receipt_used:
        with serving_timing.timed_step("pack.file_hash"):
            for name in (*index_filenames, PACK_MARKER_FILENAME):
                if _sha256_file(pack_dir / name) != manifest.files[name]:
                    raise ServingPackIntegrityError(
                        f"serving pack file hash differs: {name}"
                    )
        for name in (
            PACK_RELATIONSHIPS_FILENAME,
            PACK_INSTITUTION_CATALOG_FILENAME,
        ):
            if _sha256_file(_require_regular_file(pack_dir, name)) != manifest.files[name]:
                raise ServingPackIntegrityError(
                    f"serving pack file hash differs: {name}"
                )

    with serving_timing.timed_step("pack.relationships_read"):
        # The hash runs whenever the receipt did not already check the files,
        # and additionally whenever it is what lets the reconstruction below be
        # skipped: the bytes of this one file then carry the proof that the
        # reconstruction used to carry (~14 s against the ~137 s it displaces),
        # and without it the receipt path would verify this file contents by
        # nothing at all.
        relationships_raw = _read_pack_json(
            pack_dir,
            PACK_RELATIONSHIPS_FILENAME,
            manifest.files[PACK_RELATIONSHIPS_FILENAME],
            verify_sha256=(not receipt_used) or skip_reconstruction,
        )
    relationships = _require_mapping(
        relationships_raw, owner=PACK_RELATIONSHIPS_FILENAME
    )
    if relationships.get("schema_version") != PACK_RELATIONSHIPS_SCHEMA_VERSION:
        raise ServingPackIntegrityError("serving pack relationships schema differs")
    if relationships.get("release_id") != expected_release_id:
        raise ServingPackIntegrityError("serving pack relationships release differs")

    catalog_raw = _read_pack_json(
        pack_dir,
        PACK_INSTITUTION_CATALOG_FILENAME,
        manifest.files[PACK_INSTITUTION_CATALOG_FILENAME],
        verify_sha256=not receipt_used,
    )
    catalog_envelope = _require_mapping(
        catalog_raw, owner=PACK_INSTITUTION_CATALOG_FILENAME
    )
    if catalog_envelope.get("schema_version") != (
        PACK_INSTITUTION_CATALOG_SCHEMA_VERSION
    ):
        raise ServingPackIntegrityError(
            "serving pack institution catalog schema differs"
        )
    if catalog_envelope.get("release_id") != expected_release_id:
        raise ServingPackIntegrityError(
            "serving pack institution catalog release differs"
        )
    institution_catalog = _parse_model(
        InstitutionCatalog,
        catalog_envelope.get("institution_catalog"),
        owner="institution_catalog",
    )
    if institution_catalog.release_id != expected_release_id:
        raise ServingPackIntegrityError(
            "serving pack institution catalog release differs"
        )
    if (
        institution_catalog.content_sha256
        != manifest.institution_catalog_content_sha256
    ):
        raise ServingPackIntegrityError("serving pack institution catalog hash differs")

    build_manifest = _parse_model(
        BuildManifest,
        manifest.build_manifest,
        owner="manifest.build_manifest",
    )
    if build_manifest.release_id != expected_release_id:
        raise ServingPackIntegrityError("serving pack build manifest release differs")
    manifest_hash_payload = build_manifest.model_dump(
        mode="json",
        exclude={"manifest_sha256"},
    )
    if build_manifest.manifest_sha256 != _canonical_sha256(manifest_hash_payload):
        raise ServingPackIntegrityError(
            "serving pack build manifest stored hash does not bind it"
        )

    release_verification = _parse_model(
        ReleaseVerification,
        manifest.release_verification,
        owner="manifest.release_verification",
    )
    if (
        release_verification.candidate_release_id != expected_release_id
        or release_verification.manifest_sha256 != build_manifest.manifest_sha256
    ):
        raise ServingPackIntegrityError("serving pack release verification differs")

    index_target = IsolatedIndexTarget(
        root=index_root,
        target_id=manifest.index_target_id,
        release_id=manifest.release_id,
        forbidden_milvus_paths=forbidden_paths,
        marker_sha256=manifest.index_marker_sha256,
    )
    with serving_timing.timed_step("snapshot.open"):
        snapshot = open_manifest_verified_index_snapshot(
            index_target,
            expected_embedding_model_id=manifest.embedding_model_id,
            point_store=pack_point_store(manifest.schema_version),
        )

    index_result = IndexProjectionResult.model_construct(
        release_id=manifest.release_id,
        points=snapshot.points,
        lookup_documents=snapshot.lookup_documents,
        expected_index_projections=snapshot.receipt.index_projections,
        actual_index_projections=snapshot.receipt.index_projections,
        expected_lookup_projections=snapshot.receipt.lookup_projections,
        actual_lookup_projections=snapshot.receipt.lookup_projections,
        rebuild_decisions=_parse_models(
            IndexProjectionRebuildDecision,
            list(manifest.index_rebuild_decisions),
            owner="manifest.index_rebuild_decisions",
        ),
        policy_snapshot=_parse_model(
            IndexProjectionPolicySnapshot,
            manifest.index_policy_snapshot,
            owner="manifest.index_policy_snapshot",
        ),
        content_sha256=manifest.index_result_content_sha256,
    )
    index_result_payload = index_result.model_dump(
        mode="json",
        exclude={"content_sha256"},
    )
    if (
        index_result.content_sha256 != _canonical_sha256(index_result_payload)
        or index_result.policy_snapshot.embedding_model != manifest.embedding_model_id
    ):
        raise ServingPackIntegrityError(
            "serving pack index result does not reproduce its recorded hash"
        )

    internal_result = _parse_model(
        InternalReferenceProjectionResult,
        relationships.get("internal_reference_projection_result"),
        owner="relationships.internal_reference_projection_result",
    )
    if (
        internal_result.content_sha256
        != manifest.internal_reference_projection_result_content_sha256
    ):
        raise ServingPackIntegrityError(
            "serving pack internal reference result hash differs"
        )
    relationship_result = _parse_model(
        RelationshipProjectionResult,
        relationships.get("relationship_projection_result"),
        owner="relationships.relationship_projection_result",
    )
    if (
        relationship_result.content_sha256
        != manifest.relationship_result_content_sha256
        or relationship_result.release_id != expected_release_id
    ):
        raise ServingPackIntegrityError("serving pack relationship result hash differs")
    candidate_result = _parse_model(
        CandidateProjectionResult,
        relationships.get("candidate_projection_result"),
        owner="relationships.candidate_projection_result",
    )
    if (
        candidate_result.content_sha256
        != manifest.candidate_projection_result_content_sha256
        or candidate_result.release_id != expected_release_id
    ):
        raise ServingPackIntegrityError(
            "serving pack candidate projection result hash differs"
        )
    eligibility_results = _parse_models(
        PathEligibilityResult,
        relationships.get("public_path_eligibility_results"),
        owner="relationships.public_path_eligibility_results",
    )

    relationship_request_raw = _require_mapping(
        relationships.get("relationship_projection_request"),
        owner="relationships.relationship_projection_request",
    )
    internal_request = _build_internal_reference_request(
        _require_mapping(
            relationship_request_raw.get("internal_reference_projection_request"),
            owner="relationship request.internal_reference_projection_request",
        )
    )
    relationship_request = _build_relationship_request(
        relationship_request_raw,
        internal_request=internal_request,
        internal_result=internal_result,
    )
    if not skip_reconstruction:
        observed_request_sha256 = _canonical_sha256(
            relationship_request.model_dump(mode="json")
        )
        if observed_request_sha256 != manifest.relationship_request_sha256:
            raise ServingPackIntegrityError(
                "serving pack relationship request does not reproduce its recorded hash"
            )

    candidate_request_scalars = _require_mapping(
        relationships.get("candidate_projection_request_scalars"),
        owner="relationships.candidate_projection_request_scalars",
    )
    candidate_request = CandidateProjectionRequest.model_construct(
        release_id=_require_str(
            candidate_request_scalars.get("release_id"),
            owner="candidate request release_id",
        ),
        build_run_id=_require_str(
            candidate_request_scalars.get("build_run_id"),
            owner="candidate request build_run_id",
        ),
        as_of=_parse_datetime(
            candidate_request_scalars.get("as_of"),
            owner="candidate request as_of",
        ),
        projection_schema_version=_require_str(
            candidate_request_scalars.get("projection_schema_version"),
            owner="candidate request projection_schema_version",
        ),
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
    )
    index_scalars = _require_mapping(
        relationships.get("index_projection_scalars"),
        owner="relationships.index_projection_scalars",
    )
    index_request = IndexProjectionRequest.model_construct(
        candidate_projection_request=candidate_request,
        candidate_projection_result=candidate_result,
        # These are read, not just serialized: the professor-paper lane replays
        # every request through PathEligibilityEngine.evaluate at query time,
        # which refuses a bare mapping.  Mounting raw JSON dicts here also made
        # every dump of the reconstructed request (the boot hash check and the
        # release-bound read) emit one pydantic serializer warning per request —
        # 47k log lines per boot on the production pack.
        public_path_eligibility_requests=_parse_models(
            PathEligibilityRequest,
            relationships.get("public_path_eligibility_requests"),
            owner="relationships.public_path_eligibility_requests",
        ),
        public_path_eligibility_results=eligibility_results,
        index_projection_version=_require_str(
            index_scalars.get("index_projection_version"),
            owner="index projection version",
        ),
        vector_schema_version=_require_str(
            index_scalars.get("vector_schema_version"),
            owner="index vector schema version",
        ),
        embedding_model=_require_str(
            index_scalars.get("embedding_model"), owner="index embedding model"
        ),
        internal_auxiliary_policy_version=_require_str(
            index_scalars.get("internal_auxiliary_policy_version"),
            owner="index internal auxiliary policy version",
        ),
        build_mode=_require_str(
            index_scalars.get("build_mode"), owner="index build mode"
        ),
        prior_accepted_snapshot=index_scalars.get("prior_accepted_snapshot"),
        **(
            {
                "supplementary_field_values": index_scalars[
                    "supplementary_field_values"
                ]
            }
            if "supplementary_field_values" in index_scalars
            else {}
        ),
    )
    # exclude_unset is the rollback-compat lock: packs sealed before the
    # C2.1p contract port carry no such scalar, so the field stays unset and
    # the dump is byte-identical to the pre-port canonical form; packs sealed
    # from a multi-value envelope carry it and reproduce the envelope hash.
    # Every other field above is passed explicitly, so exclude_unset changes
    # nothing else.
    if not skip_reconstruction:
        observed_index_request_sha256 = _canonical_sha256(
            index_request.model_dump(mode="json", exclude_unset=True)
        )
        if observed_index_request_sha256 != manifest.index_projection_request_sha256:
            raise ServingPackIntegrityError(
                "serving pack index projection request does not reproduce its recorded hash"
            )
    if (
        candidate_request.release_id != expected_release_id
        or candidate_result.release_id != expected_release_id
        or candidate_request.build_run_id != candidate_result.build_run_id
        or candidate_result.internal_reference_projection_result_content_sha256
        != internal_result.content_sha256
        or candidate_result.public_domain_projection_result_content_sha256
        != internal_result.public_domain_projection_result_content_sha256
        or relationship_request.release_id != expected_release_id
        or relationship_result.projection_run_id
        != relationship_request.projection_run_id
        or relationship_result.catalog != relationship_request.catalog
    ):
        raise ServingPackIntegrityError(
            "serving pack authority graph is not bound to one release"
        )
    manifest_projections = {
        projection.projection_id: projection
        for projection in build_manifest.published_projections
    }
    candidate_projections = {
        projection.projection_id: projection
        for projection in candidate_result.published_projections
    }
    if (
        len(manifest_projections) != len(build_manifest.published_projections)
        or len(candidate_projections) != len(candidate_result.published_projections)
        or manifest_projections != candidate_projections
    ):
        raise ServingPackIntegrityError(
            "serving pack published projection graph differs from its release manifest"
        )

    release_bundle = IsolatedReleaseBundle.model_construct(
        manifest=build_manifest,
        index_result=index_result,
        index_target=index_target,
        relationship_projection_request=relationship_request,
        relationship_projection_result=relationship_result,
    )
    _write_mount_receipt(
        receipt_path,
        {
            "schema_version": _MOUNT_RECEIPT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pack_dir": str(pack_dir),
            "release_id": manifest.release_id,
            "index_root": str(index_root),
            "index_target_id": manifest.index_target_id,
            "index_marker_sha256": manifest.index_marker_sha256,
            "pack_manifest_sha256": manifest_file_sha256,
            "verification": "receipt" if receipt_used else "full",
            "files": identities,
            "file_sha256": {
                name: manifest.files[name]
                for name in (
                    *index_filenames,
                    PACK_MARKER_FILENAME,
                    PACK_RELATIONSHIPS_FILENAME,
                    PACK_INSTITUTION_CATALOG_FILENAME,
                )
            },
            "mount_seconds": round(monotonic() - mount_started, 3),
        },
    )
    return ServingPackAuthority(
        pack_dir=pack_dir,
        manifest=manifest,
        release_bundle=release_bundle,
        index_projection_request=index_request,
        institution_catalog=institution_catalog,
        release_verification=release_verification,
        index_snapshot=snapshot,
    )


# ---------------------------------------------------------------------------
# Lane adapters.
#
# These factories mirror the composition glue of
# ``knowledge_read_isolated.create_isolated_*`` one-for-one and reuse its
# helpers for every behavioral decision; the only difference is that the
# pack-verified authority is already exact, so the expensive re-validation and
# deterministic replays are not repeated. The hermetic pack tests assert the
# resulting lanes answer fixture queries with evidence identical to the
# upstream factories.
# ---------------------------------------------------------------------------


def _create_pack_exact_lookup_adapter(
    *,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    lookup_view: iso._AuditedLookupView,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    view_provider = iso._lookup_view_provider(bundle=bundle, supplied=lookup_view)

    def exact_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = iso._validated_lane_request(
            request,
            lane="exact",
            bundle=bundle,
        )
        documents = iso._read_bound_documents(bundle)
        view = view_provider()
        entries = iso._lookup_entries_for_documents(
            documents=documents,
            lookup_view=view,
        )
        linked_positions = iso._entity_link_indexes_for_view(
            view=view,
            entries=entries,
            query_text=validated_request.query_text,
        )
        candidates: list[Any] = []
        for position, entry in enumerate(entries):
            document = entry.document
            if not iso._matches_exact_request(
                request=validated_request,
                document=document,
                display_terms=entry.display_terms,
                identifier_terms=entry.identifier_terms,
                content_terms=entry.content_terms,
                name_linked=position in linked_positions,
            ):
                continue
            candidates.append(
                iso._candidate_from_document(
                    request=validated_request,
                    bundle=bundle,
                    publication=publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="exact",
                    adapter_version=iso._EXACT_ADAPTER_VERSION,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return exact_lookup


def _create_pack_structured_lookup_adapter(
    *,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    lookup_view: iso._AuditedLookupView,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    view_provider = iso._lookup_view_provider(bundle=bundle, supplied=lookup_view)

    def structured_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = iso._validated_lane_request(
            request,
            lane="structured",
            bundle=bundle,
        )
        displayed_ids = validated_request.structured_constraints.displayed_entity_ids
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated_request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if any(values != displayed_ids for values in protected_sets):
            raise ValueError(
                "protected displayed set differs from structured constraints"
            )
        if not displayed_ids:
            return RetrievalLaneResult()
        documents = iso._read_bound_documents(bundle)
        entries = iso._lookup_entries_for_documents(
            documents=documents,
            lookup_view=view_provider(),
        )
        candidates: list[Any] = []
        for entry in entries:
            document = entry.document
            if not iso._matches_structured_request(
                request=validated_request,
                document=document,
                content_terms=entry.content_terms,
            ):
                continue
            candidates.append(
                iso._candidate_from_document(
                    request=validated_request,
                    bundle=bundle,
                    publication=publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="structured",
                    adapter_version=iso._STRUCTURED_ADAPTER_VERSION,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return structured_lookup


def _warm_indexed_lexical_lane(bundle: IsolatedReleaseBundle) -> None:
    """Open the derived lexical index off the request path, best-effort.

    The open costs ~5.7s on the run14 pack (jieba domain dictionary + FTS5
    connect) and would otherwise be paid by the first user turn; the open is
    process-cached and only successful opens are cached, so a rebuilt
    artifact is picked up without a restart.
    """

    def warm() -> None:
        try:
            with serving_timing.timed_step("lexical.warm_open"):
                iso._indexed_lexical_open(bundle)
        except Exception:  # noqa: BLE001 - warm-up must never fail the boot
            _LOGGER.warning("lexical index warm-up failed", exc_info=True)

    Thread(target=warm, name="canonical-v2-lexical-index-warm", daemon=True).start()


def _create_pack_lexical_lookup_adapter(
    *,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    lookup_view: iso._AuditedLookupView,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    view_provider = iso._lookup_view_provider(bundle=bundle, supplied=lookup_view)

    def lexical_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = iso._validated_lane_request(
            request,
            lane="lexical",
            bundle=bundle,
        )
        query_phrase = iso._lexical_query_phrase(validated_request.query_text)
        if not query_phrase:
            return RetrievalLaneResult()
        # retrieval-v2 Step 1: the indexed lexical lane (shared with the
        # isolated adapter); None keeps the substring lane below, category
        # fallback included.
        indexed_result = iso._indexed_lexical_lane_result(
            query_phrase=query_phrase,
            request=validated_request,
            bundle=bundle,
            publication=publication,
            lookup_view=view_provider(),
        )
        if indexed_result is not None:
            return indexed_result
        documents = iso._read_bound_documents(bundle)
        entries = iso._lookup_entries_for_documents(
            documents=documents,
            lookup_view=view_provider(),
        )
        candidates: list[Any] = []
        for entry in entries:
            document = entry.document
            if not iso._matches_lexical_request(
                request=validated_request,
                document=document,
                query_phrase=query_phrase,
                display_terms=entry.display_terms,
                content_terms=entry.content_terms,
            ):
                continue
            candidates.append(
                iso._candidate_from_document(
                    request=validated_request,
                    bundle=bundle,
                    publication=publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="lexical",
                    adapter_version=iso._LEXICAL_ADAPTER_VERSION,
                )
            )
        if not candidates:
            # F1 (close-workbook-gaps B1): same category-recall fallback as
            # the isolated adapter — the pack parity test keeps the two
            # lexical paths in lockstep.
            return RetrievalLaneResult(
                candidates=tuple(
                    iso._candidate_from_document(
                        request=validated_request,
                        bundle=bundle,
                        publication=publication,
                        document=entry.document,
                        display_name=entry.display_name,
                        identifier_terms=entry.identifier_terms,
                        lane="lexical",
                        adapter_version=iso._LEXICAL_ADAPTER_VERSION,
                    )
                    for entry in iso._category_recall_entries(
                        request=validated_request,
                        entries=entries,
                    )
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return lexical_lookup


_VECTOR_INDEX_CACHE: dict[tuple[str, str, str], "_ServingVectorIndex"] = {}
_VECTOR_INDEX_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class _ServingVectorIndex:
    """Process-scoped derived state for one mounted index (serving-index-process-scope T2).

    ``points`` is the snapshot inventory; ``terms_by_point_id`` is the parsed
    ``embedded_content`` term set each point already paid for on the previous
    design's every query; ``professor_names`` is the professor display-name
    authority derived from the lookup documents. Everything is keyed by
    ``(index_root, marker_sha256, release_id)``, so a re-mounted pack (different
    marker) or another release never reuses stale rows.
    """

    key: tuple[str, str, str]
    points: tuple[Any, ...]
    terms_by_point_id: dict[str, frozenset[str]]
    professor_names: dict[str, str]


def _vector_index_key(bundle: IsolatedReleaseBundle) -> tuple[str, str, str]:
    return (
        str(bundle.index_target.root),
        bundle.index_target.marker_sha256,
        bundle.release_id,
    )


def load_serving_vector_index(
    *,
    bundle: IsolatedReleaseBundle,
    snapshot: IsolatedIndexSnapshot,
) -> _ServingVectorIndex:
    """Build (once per process per mounted index) the derived vector state.

    The first build pays the JSON parse of every point's ``embedded_content``
    and the professor display-name authority; every later query and every
    later session of this process reads the cached rows. A build for another
    key (other root/marker/release) is independent, and the whole function is
    fail-closed: an unparseable point raises exactly like the per-query
    matcher did.
    """

    key = _vector_index_key(bundle)
    with _VECTOR_INDEX_LOCK:
        cached = _VECTOR_INDEX_CACHE.get(key)
        if cached is not None and cached.points is snapshot.points:
            serving_timing.bump_counter("vector.index.hit")
            return cached
    with serving_timing.timed_step("vector.index_build") as step:
        step.annotate(points=len(snapshot.points))
        terms_by_point_id: dict[str, frozenset[str]] = {}
        for point in snapshot.points:
            try:
                content = json.loads(point.embedded_content)
            except (TypeError, ValueError) as exc:
                raise iso.IsolatedKnowledgeReadIntegrityError(
                    "vector point embedded content is not valid JSON"
                ) from exc
            terms_by_point_id[point.point_id] = iso._normalized_scalar_values(content)
        professor_names = iso._professor_vector_display_names(
            points=snapshot.points,
            lookup_documents=snapshot.lookup_documents,
            bundle=bundle,
        )
        index = _ServingVectorIndex(
            key=key,
            points=snapshot.points,
            terms_by_point_id=terms_by_point_id,
            professor_names=professor_names,
        )
    with _VECTOR_INDEX_LOCK:
        _VECTOR_INDEX_CACHE[key] = index
    return index


def _vector_candidate_rank_key(
    *,
    point: Any,
    score: float,
    target_id: str,
) -> tuple[float, str, str, str, str]:
    """The lane-result ordering key, computed straight from a vector point.

    Mirrors the ``RecallCandidate`` sort tuple used below: ``raw_score`` is the
    similarity score, and every vector candidate carries a ``LocalVectorTrace``
    whose view is the point's projection view and whose locator is the local
    projection locator (``canonical-v2-isolated:{target}:{point_id}``). Keys are
    total (``point_id`` is unique), so ranking before binding keeps the exact
    order the full list would have produced.
    """
    return (
        -score,
        point.domain or "",
        point.canonical_object_id or "",
        point.projection_view.value,
        f"canonical-v2-isolated:{target_id}:{point.point_id}",
    )


def _create_pack_vector_recall_adapter(
    *,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    embedding_adapter: EmbeddingAdapter,
    vectorized_scoring: bool,
    preopened_snapshot: IsolatedIndexSnapshot | None,
    point_store: IndexPointStore = POINT_STORE_MILVUS,
    manual_recall_provider: Any | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    expected_model_id = bundle.index_result.policy_snapshot.embedding_model
    if any(
        point.embedding_model != expected_model_id
        for point in bundle.index_result.points
    ):
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "vector point embedding model differs from the release policy"
        )
    validating_adapter = iso._ValidatingEmbeddingAdapter(
        embedding_adapter,
        expected_model_id=expected_model_id,
    )
    if not isinstance(vectorized_scoring, bool):
        raise TypeError("vectorized_scoring must be a Boolean")
    cached_snapshot: Any = None
    snapshot_lock = Lock()
    vectorized_index: tuple[dict[str, int], Any, Any] | None = None
    vectorized_index_lock = Lock()

    def validated_snapshot() -> Any:
        nonlocal cached_snapshot
        if cached_snapshot is not None:
            serving_timing.bump_counter("vector.snapshot.hit")
            return cached_snapshot
        with snapshot_lock:
            if cached_snapshot is None:
                with serving_timing.timed_step("vector.snapshot.open") as step:
                    step.annotate(preopened=preopened_snapshot is not None)
                    snapshot = iso._validated_vector_snapshot(
                        preopened_snapshot
                        if preopened_snapshot is not None
                        else open_manifest_verified_index_snapshot(
                            bundle.index_target,
                            expected_embedding_model_id=expected_model_id,
                            point_store=point_store,
                        )
                    )
                    iso._require_snapshot_matches_bundle(snapshot, bundle)
                    cached_snapshot = snapshot
        return cached_snapshot

    def _load_persisted_index() -> tuple[dict[str, int], Any, Any] | None:
        if not vectorized_scoring:
            return None
        snapshot = validated_snapshot()
        path = bundle.index_target.root / "vector_matrix.npz"
        try:
            with serving_timing.timed_step("vector.npz_load") as step:
                result = iso.load_persisted_vector_matrix(
                    path,
                    points=snapshot.points,
                    expected_embedding_model_id=expected_model_id,
                    dimension=validating_adapter.dimension,
                )
                step.annotate(points=len(snapshot.points))
                return result
        except iso.IndexProjectionIntegrityError as exc:
            raise iso.IsolatedKnowledgeReadIntegrityError(
                "persisted vector matrix failed integrity validation"
            ) from exc

    def vectorized_scores(
        snapshot: Any,
        query_vector: tuple[float, ...],
    ) -> tuple[dict[str, int], Any]:
        nonlocal vectorized_index
        if vectorized_index is None:
            with vectorized_index_lock:
                if vectorized_index is None:
                    persisted = _load_persisted_index()
                    if persisted is not None:
                        vectorized_index = persisted
                    else:
                        point_vectors = validating_adapter.embed_batch(
                            tuple(
                                point.embedded_content
                                for point in snapshot.points
                            )
                        )
                        matrix = np.asarray(point_vectors, dtype=np.float64)
                        norms = np.linalg.norm(matrix, axis=1)
                        if not np.all(np.isfinite(norms)) or np.any(norms == 0.0):
                            raise iso.IsolatedKnowledgeReadIntegrityError(
                                "vectorized point matrix has an invalid norm"
                            )
                        vectorized_index = (
                            {
                                point.point_id: index
                                for index, point in enumerate(snapshot.points)
                            },
                            matrix,
                            norms,
                        )
        positions, matrix, norms = vectorized_index
        query = np.asarray(query_vector, dtype=np.float64)
        query_norm = float(np.linalg.norm(query))
        if not math.isfinite(query_norm) or query_norm == 0.0:
            raise iso.IsolatedKnowledgeReadIntegrityError(
                "vectorized query has an invalid norm"
            )
        with serving_timing.timed_step("vector.score"):
            scores = np.clip((matrix @ query) / (norms * query_norm), -1.0, 1.0)
            if not np.all(np.isfinite(scores)):
                raise iso.IsolatedKnowledgeReadIntegrityError(
                    "vectorized recall produced a non-finite score"
                )
        return positions, scores

    def vector_recall(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = iso._validated_lane_request(
            request,
            lane="vector",
            bundle=bundle,
        )
        if (
            "professor" in validated_request.domains
            and validated_request.professor_vector_view is None
        ):
            raise iso.IsolatedKnowledgeReadIntegrityError(
                "Professor vector recall requires an explicit typed projection view"
            )
        query_topic = iso._vector_query_topic(validated_request.query_text)
        if not query_topic or validated_request.max_candidates == 0:
            return RetrievalLaneResult()

        snapshot = validated_snapshot()
        index = load_serving_vector_index(bundle=bundle, snapshot=snapshot)
        with serving_timing.timed_step("vector.points_filter") as step:
            points = tuple(
                point
                for point in index.points
                if iso._matches_vector_request(
                    request=validated_request,
                    point=point,
                    content_terms=index.terms_by_point_id[point.point_id],
                )
            )
            step.annotate(matched=len(points), total=len(index.points))
        manual_points = manual_recall_points.manual_points_for_request(
            provider=manual_recall_provider,
            request=validated_request,
        )
        if not points and not manual_points:
            return RetrievalLaneResult()

        if vectorized_scoring:
            with serving_timing.timed_step("vector.embed_query"):
                query_vector = validating_adapter.embed_batch((query_topic,))[0]
            positions, scores = vectorized_scores(snapshot, query_vector)
            similarity_scores = tuple(
                float(scores[positions[point.point_id]]) for point in points
            )
        else:
            vectors = validating_adapter.embed_batch(
                (query_topic, *(point.embedded_content for point in points))
            )
            query_vector = vectors[0]
            similarity_scores = tuple(
                iso._cosine_similarity(query_vector, point_vector)
                for point_vector in vectors[1:]
            )
        query_embedding_sha256 = _canonical_sha256(query_vector)
        # Rank first, bind second: the retained lane result is capped at
        # ``max_candidates`` and the final ordering is total over the rank key
        # below, so building a full RecallCandidate (evidence item, trace,
        # claim binding) for every matched point — up to the whole 51k-point
        # inventory — only to drop all but the cap is pure waste
        # (serving-index-process-scope T2: 11s/query on the run15 pack).
        with serving_timing.timed_step("vector.rank") as step:
            step.annotate(matched=len(points))
            ranked = sorted(
                zip(points, similarity_scores, strict=True),
                key=lambda entry: _vector_candidate_rank_key(
                    point=entry[0],
                    score=entry[1],
                    target_id=bundle.index_target.target_id,
                ),
            )[: validated_request.max_candidates]
        with serving_timing.timed_step("vector.candidate_bind") as step:
            step.annotate(candidates=len(ranked))
            candidates = [
                iso._candidate_from_point(
                    request=validated_request,
                    bundle=bundle,
                    publication=publication,
                    point=point,
                    display_name=iso._vector_display_name(
                        point,
                        professor_display_names=index.professor_names,
                    ),
                    query_embedding_sha256=query_embedding_sha256,
                    similarity_score=score,
                )
                for point, score in ranked
            ]
        manual_recall_points.append_manual_candidates(
            provider=manual_recall_provider,
            request=validated_request,
            query_vector=query_vector,
            query_embedding_sha256=query_embedding_sha256,
            embedding_model=expected_model_id,
            candidates=candidates,
        )
        with serving_timing.timed_step("vector.sort") as step:
            step.annotate(candidates=len(candidates))
            candidates.sort(
                key=lambda candidate: (
                    -candidate.raw_score,
                    candidate.domain,
                    candidate.canonical_id or "",
                    candidate.evidence[0].local_projection_trace.projection_view
                    if isinstance(
                        candidate.evidence[0].local_projection_trace,
                        iso.LocalVectorTrace,
                    )
                    else "",
                    candidate.evidence[0].source_locator,
                )
            )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    validated_snapshot()
    # Fast boot: load the persisted scoring matrix now so the first vector
    # request skips the ~77s full re-embed.  Missing file falls back to the
    # lazy in-request build; a corrupt file fails closed at boot.
    if vectorized_scoring:
        with vectorized_index_lock:
            if vectorized_index is None:
                vectorized_index = _load_persisted_index()
    # serving-index-process-scope T3: pay the derived-state build now, at boot,
    # so no user turn (and no later session) ever pays it.
    if cached_snapshot is not None:
        load_serving_vector_index(bundle=bundle, snapshot=cached_snapshot)
    return vector_recall


def _create_pack_internal_reference_lookup_adapter(
    *,
    authority: Any,
    lookup_view: iso._AuditedLookupView,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    view_provider = iso._lookup_view_provider(
        bundle=authority.bundle,
        supplied=lookup_view,
    )

    def internal_reference_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = iso._validate_internal_reference_request(
            request,
            authority,
        )
        if validated_request.max_candidates == 0:
            return RetrievalLaneResult()
        view_provider()
        documents = iso._read_bound_documents(authority.bundle)
        return iso._build_internal_reference_result(
            request=validated_request,
            authority=authority,
            documents=documents,
        )

    return internal_reference_lookup


def _create_pack_relationship_lookup_adapter(
    *,
    authority: Any,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    def relationship_lookup(request: LaneRequest) -> RetrievalLaneResult:
        return iso._build_relationship_result(request=request, authority=authority)

    return relationship_lookup


def create_serving_pack_query_planner(
    *,
    authority: ServingPackAuthority,
    published_release: PublishedRelease,
    planning_policy: QueryPlanningPolicy,
    proposal_provider: Callable[[QueryPlanningRequest], Any],
    ambiguity_policy: AmbiguityPolicy | None = None,
) -> Any:
    """Compose the release-bound planner, mirroring the isolated factory."""

    bundle = authority.release_bundle
    validated_publication = _validated_published_release(
        published_release,
        release_id=bundle.release_id,
    )
    validated_policy = iso._validated_exact_model(
        planning_policy,
        QueryPlanningPolicy,
        "query planning policy",
    )
    validated_ambiguity_policy = (
        iso._validated_exact_model(
            ambiguity_policy,
            AmbiguityPolicy,
            "ambiguity policy",
        )
        if ambiguity_policy is not None
        else None
    )
    iso._validate_manifest_hash(bundle)
    iso._validate_planning_policy(validated_policy)
    institution_catalog = authority.institution_catalog
    if institution_catalog.release_id != bundle.release_id:
        raise iso.IsolatedQueryPlanningIntegrityError(
            "institution catalog release differs from the isolated bundle"
        )
    index_request = authority.index_projection_request
    candidate_request = index_request.candidate_projection_request
    candidate_result = index_request.candidate_projection_result
    internal_result = candidate_request.internal_reference_projection_result
    if (
        candidate_request.release_id != bundle.release_id
        or candidate_result.release_id != bundle.release_id
        or candidate_request.build_run_id != candidate_result.build_run_id
        or candidate_result.internal_reference_projection_result_content_sha256
        != internal_result.content_sha256
        or candidate_result.public_domain_projection_result_content_sha256
        != internal_result.public_domain_projection_result_content_sha256
    ):
        raise iso.IsolatedQueryPlanningIntegrityError(
            "candidate projection graph differs from the release manifest"
        )
    manifest_projections = {
        projection.projection_id: projection
        for projection in bundle.manifest.published_projections
    }
    candidate_projections = {
        projection.projection_id: projection
        for projection in candidate_result.published_projections
    }
    if (
        len(manifest_projections) != len(bundle.manifest.published_projections)
        or len(candidate_projections) != len(candidate_result.published_projections)
        or manifest_projections != candidate_projections
    ):
        raise iso.IsolatedQueryPlanningIntegrityError(
            "published projection graph differs from the release manifest"
        )
    iso._validate_institution_catalog(institution_catalog, candidate_result)
    person_references = iso._derive_person_reference_records(
        candidate_result=candidate_result,
        internal_result=internal_result,
        institution_catalog=institution_catalog,
    )
    technology_routes = iso._derive_technology_route_records(candidate_result)
    if validated_publication.state is ReleaseState.active:
        publication_state: Literal["active", "rolled_back"] = "active"
    elif validated_publication.state is ReleaseState.rolled_back:
        publication_state = "rolled_back"
    else:
        raise iso.IsolatedQueryPlanningIntegrityError(
            "published release is not serviceable for query planning"
        )
    release_binding = PlanningReleaseBinding(
        release_id=bundle.release_id,
        publication_state=publication_state,
        published_release_sha256=_canonical_sha256(
            validated_publication.model_dump(mode="json")
        ),
        publication_verification_evidence_ids=tuple(
            sorted(validated_publication.verification_evidence_ids)
        ),
        manifest_sha256=bundle.manifest.manifest_sha256,
        # The receipt, not a recomputation: open_serving_pack_authority already
        # proved the reconstructed index request reproduces this exact value
        # from relationships.json, and the dump that proved it is byte-identical
        # to the one this line used to re-derive (measured, 2026-09-20).
        index_projection_request_sha256=authority.manifest.index_projection_request_sha256,
        index_projection_result_sha256=bundle.index_result.content_sha256,
        candidate_projection_result_sha256=candidate_result.content_sha256,
        internal_reference_projection_result_sha256=internal_result.content_sha256,
        institution_catalog_sha256=institution_catalog.content_sha256,
        planning_policy_sha256=validated_policy.content_sha256,
    )
    delegate = create_ephemeral_query_planner(
        planning_policy=validated_policy,
        institution_catalog=institution_catalog,
        proposal_provider=proposal_provider,
        person_references=person_references,
        technology_routes=technology_routes,
    )
    # The injected ambiguity policy gates only requests that actually carry
    # ambiguity candidates; every other request plans on the policy-free
    # delegate so an absent candidate set can never block ordinary queries.
    ambiguity_delegate = (
        create_ephemeral_query_planner(
            planning_policy=validated_policy,
            institution_catalog=institution_catalog,
            proposal_provider=proposal_provider,
            ambiguity_policy=validated_ambiguity_policy,
            person_references=person_references,
            technology_routes=technology_routes,
        )
        if validated_ambiguity_policy is not None
        else None
    )
    return iso._ReleaseBoundQueryPlanner(
        release_id=bundle.release_id,
        release_binding=release_binding,
        delegate=delegate,
        ambiguity_delegate=ambiguity_delegate,
        named_professor_projections=tuple(
            projection
            for projection in candidate_result.public_domain_projections
            if isinstance(projection, ProfessorProjection)
        ),
        named_company_projections=tuple(
            projection
            for projection in candidate_result.public_domain_projections
            if isinstance(projection, CompanyProjection)
        ),
        institution_catalog=institution_catalog,
    )


def create_serving_pack_knowledge_read(
    *,
    authority: ServingPackAuthority,
    published_release: PublishedRelease,
    universal_web_policy: WebSearchPolicy,
    web_search: Callable[[LaneRequest], object],
    web_snapshot_policy: WebSnapshotPolicy,
    embedding_adapter: EmbeddingAdapter | None = None,
    vectorized_recall: bool = True,
    identity_fuser: Callable[[IdentityFusionRequest], object] | None = None,
    reranker: Callable[[RerankRequest], object] | None = None,
    sufficiency_decider: Callable[[SufficiencyDecisionRequest], object] | None = None,
    supplemental_search: Callable[[SupplementalRequest], object] | None = None,
    web_handle_resolver: Callable[[WebHandleResolutionRequest], object] | None = None,
    accepted_identity_lookup: Callable[[AcceptedIdentityLookupRequest], object]
    | None = None,
    manual_recall_provider: Any | None = None,
    web_handle_ttl: timedelta = timedelta(hours=1),
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> KnowledgeRead:
    """Compose the release-bound KnowledgeRead over the pack authority."""

    bundle = authority.release_bundle
    validated_publication = _validated_published_release(
        published_release,
        release_id=bundle.release_id,
    )
    iso._validate_manifest_hash(bundle)
    try:
        validated_web_policy = iso._validated_exact_model(
            universal_web_policy,
            WebSearchPolicy,
            "Universal Web policy",
        )
        validated_snapshot_policy = iso._validated_exact_model(
            web_snapshot_policy,
            WebSnapshotPolicy,
            "Web snapshot policy",
        )
    except (TypeError, iso.IsolatedQueryPlanningIntegrityError) as exc:
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "Web policy failed exact typed validation"
        ) from exc
    if (
        validated_web_policy.mode != "universal"
        or validated_web_policy.max_provider_calls <= 0
        or validated_web_policy.timeout_ms <= 0
        or validated_web_policy.max_results <= 0
        or validated_web_policy.allowed_domains
    ):
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "release-bound Universal Web policy must be positive and unscoped"
        )
    if not callable(web_search):
        raise TypeError("web_search must be callable")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not isinstance(vectorized_recall, bool):
        raise TypeError("vectorized_recall must be a Boolean")
    if embedding_adapter is not None and (
        getattr(embedding_adapter, "model_id", None)
        != bundle.index_result.policy_snapshot.embedding_model
    ):
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "serving pack embedding adapter differs from the release policy"
        )

    institution_catalog = authority.institution_catalog
    index_request = authority.index_projection_request
    candidate_request = index_request.candidate_projection_request
    candidate_result = index_request.candidate_projection_result
    internal_result = candidate_request.internal_reference_projection_result
    person_records = iso._derive_person_reference_records(
        candidate_result=candidate_result,
        internal_result=internal_result,
        institution_catalog=institution_catalog,
    )
    technology_records = iso._derive_technology_route_records(candidate_result)
    internal_reference_authority = iso._InternalReferenceAuthority(
        bundle=bundle,
        publication=validated_publication,
        index_request=index_request,
        institution_catalog=institution_catalog,
        internal_result=internal_result,
        person_records=person_records,
        technology_records=technology_records,
    )
    relationship_request = bundle.relationship_projection_request
    relationship_result = bundle.relationship_projection_result
    if relationship_request is None or relationship_result is None:
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "serving pack release bundle lacks relationship publication authority"
        )
    relationship_authority = iso._RelationshipAuthority(
        internal_authority=internal_reference_authority,
        relationship_request=relationship_request,
        relationship_result=relationship_result,
        candidate_result=candidate_result,
        # Receipt, not a recomputation: this is the same value
        # open_serving_pack_authority proved when it reconstructed the
        # relationship request, and the measured dump is byte-identical.
        relationship_request_content_sha256=(
            authority.manifest.relationship_request_sha256
        ),
    )

    lookup_view = iso._create_audited_lookup_view(bundle)
    lane_adapters: dict[str, Callable[[LaneRequest], RetrievalLaneResult]] = {
        "exact": _create_pack_exact_lookup_adapter(
            bundle=bundle,
            publication=validated_publication,
            lookup_view=lookup_view,
        ),
        "structured": _create_pack_structured_lookup_adapter(
            bundle=bundle,
            publication=validated_publication,
            lookup_view=lookup_view,
        ),
        "lexical": _create_pack_lexical_lookup_adapter(
            bundle=bundle,
            publication=validated_publication,
            lookup_view=lookup_view,
        ),
    }
    supported_lanes = {"exact", "structured", "lexical", "web"}
    if embedding_adapter is not None:
        lane_adapters["vector"] = _create_pack_vector_recall_adapter(
            bundle=bundle,
            publication=validated_publication,
            embedding_adapter=embedding_adapter,
            vectorized_scoring=vectorized_recall,
            preopened_snapshot=authority.index_snapshot,
            point_store=pack_point_store(authority.manifest.schema_version),
            manual_recall_provider=manual_recall_provider,
        )
        supported_lanes.add("vector")
    lane_adapters["internal_reference"] = (
        _create_pack_internal_reference_lookup_adapter(
            authority=internal_reference_authority,
            lookup_view=lookup_view,
        )
    )
    supported_lanes.add("internal_reference")
    lane_adapters["relationship"] = _create_pack_relationship_lookup_adapter(
        authority=relationship_authority,
    )
    supported_lanes.add("relationship")

    # retrieval-v2 Step 1: the derived lexical index pays a one-time open
    # (jieba domain dictionary + FTS5 connect, measured 5.7s on the run14
    # pack). Warm it off the request path here, where the release bundle is
    # the one the lexical lane binds to; the open is process-cached.
    _warm_indexed_lexical_lane(bundle)

    delegate = create_ephemeral_knowledge_read(
        universal_web_policy=validated_web_policy,
        lane_adapters=lane_adapters,
        web_search=web_search,
        identity_fuser=identity_fuser,
        reranker=reranker,
        sufficiency_decider=sufficiency_decider,
        supplemental_search=supplemental_search,
        web_handle_resolver=web_handle_resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        clock=clock,
        web_handle_ttl=web_handle_ttl,
        web_snapshot_policy=validated_snapshot_policy,
    )
    return iso._ReleaseBoundKnowledgeRead(
        release_bundle=bundle,
        published_release=validated_publication,
        delegate=delegate,
        supported_lanes=frozenset(supported_lanes),
        embedding_adapter=embedding_adapter,
        internal_reference_authority=internal_reference_authority,
        relationship_authority=relationship_authority,
    )


__all__ = [
    "PACK_INDEX_FILENAMES",
    "PACK_INDEX_FILENAMES_V2",
    "PACK_INSTITUTION_CATALOG_FILENAME",
    "PACK_INSTITUTION_CATALOG_SCHEMA_VERSION",
    "PACK_MANIFEST_FILENAME",
    "PACK_MARKER_FILENAME",
    "PACK_RELATIONSHIPS_FILENAME",
    "PACK_RELATIONSHIPS_SCHEMA_VERSION",
    "PACK_SCHEMA_VERSION",
    "PACK_SCHEMA_VERSION_V2",
    "ServingPackAuthority",
    "ServingPackIntegrityError",
    "ServingPackManifest",
    "create_serving_pack_knowledge_read",
    "create_serving_pack_query_planner",
    "open_serving_pack_authority",
    "pack_index_filenames",
    "pack_point_store",
]
