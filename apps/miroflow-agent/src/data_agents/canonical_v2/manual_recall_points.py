"""Manual recall sidecar points for the vector lane.

Manual knowledge (operator-uploaded document chunks, manually added records)
is not part of the audited release index. It lives in a writable sidecar
store and is unioned into the vector lane's candidate pool at recall time,
before sort/truncate. Points are embedded at write time with the serving
embedding model, so recall scoring is pure in-process cosine and adds no new
query-time external calls.

Manual traces intentionally carry ``target_id == MANUAL_RECALL_TARGET_ID``:
their provenance is operator attestation (recorded on the trace lineage
fields), not the release hash chain, and the release-bound vector validator
exempts them on that marker.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from .knowledge_read import (
    MANUAL_RECALL_SOURCE_AUTHORITY,
    MANUAL_RECALL_TARGET_ID,
    EvidenceClaimBinding,
    EvidenceItem,
    LaneRequest,
    LocalVectorTrace,
    RecallCandidate,
    _local_projection_locator,
)

MANUAL_RECALL_PROJECTION_ID = "manual-recall-projection-v1"
MANUAL_RECALL_SCHEMA_VERSION = "canonical-v2-manual-recall-v1"
MANUAL_RECALL_ADAPTER_VERSION = "manual-recall-v1"

_FIXED_LINEAGE_SHA256 = hashlib.sha256(b"canonical-v2-manual-recall-v1").hexdigest()

_PUBLIC_DOMAINS = frozenset({"company", "paper", "patent", "professor"})


class ManualRecallPoint(Protocol):
    """Structural view of one sidecar point consumed by the vector lane."""

    point_id: str
    domain: str
    display_name: str
    canonical_ref: str
    embedded_content: str
    vector: tuple[float, ...]


class ManualRecallProvider(Protocol):
    """Read-only provider of the currently active manual points."""

    def active_points(self) -> tuple[Any, ...]: ...


def is_manual_vector_trace(trace: object) -> bool:
    """True when one local projection trace belongs to the manual sidecar."""

    return (
        isinstance(trace, LocalVectorTrace)
        and trace.target_id == MANUAL_RECALL_TARGET_ID
    )


def manual_points_for_request(
    *,
    provider: ManualRecallProvider | None,
    request: LaneRequest,
) -> tuple[Any, ...]:
    """Active sidecar points eligible for one validated vector lane request.

    Mirrors the release point filter semantics (domain membership, displayed
    entity constraint, excluded-term constraint). Corrupt points are skipped
    rather than poisoning the lane: sidecar content is operator-writable.
    """

    if provider is None:
        return ()
    from . import knowledge_read_isolated as iso  # lazy: avoids an import cycle

    constraints = request.structured_constraints
    matched: list[Any] = []
    for point in provider.active_points():
        if point.domain not in request.domains:
            continue
        if (
            constraints.displayed_entity_ids
            and point.canonical_ref not in constraints.displayed_entity_ids
        ):
            continue
        try:
            content = json.loads(point.embedded_content)
        except (TypeError, ValueError):
            continue
        if iso._has_excluded_term(
            constraints.excluded_terms,
            iso._normalized_scalar_values(content),
        ):
            continue
        matched.append(point)
    return tuple(matched)


def manual_candidate_from_point(
    *,
    point: Any,
    request: LaneRequest,
    query_embedding_sha256: str,
    similarity_score: float,
    embedding_model: str,
) -> RecallCandidate:
    """Build one release-shaped vector candidate from a sidecar point.

    The candidate/evidence pair satisfies the lane output contract
    (``_invoke_lane`` cross-wiring checks): lane ``vector``, candidate
    ``release_id`` bound to the serving request, trace-derived ids, and
    claim/score consistency. Only ``target_id`` marks it as manual.
    """

    from . import knowledge_read_isolated as iso  # lazy: avoids an import cycle

    if point.domain not in _PUBLIC_DOMAINS:
        raise iso.IsolatedKnowledgeReadIntegrityError(
            "manual recall point domain is not a public domain"
        )
    embedded_sha256 = hashlib.sha256(
        point.embedded_content.encode("utf-8")
    ).hexdigest()
    source_evidence_id = f"manual-recall-evidence:{point.point_id}"
    trace = LocalVectorTrace(
        target_id=MANUAL_RECALL_TARGET_ID,
        target_marker_sha256=_FIXED_LINEAGE_SHA256,
        manifest_sha256=_FIXED_LINEAGE_SHA256,
        index_result_content_sha256=_FIXED_LINEAGE_SHA256,
        point_id=point.point_id,
        canonical_object_id=point.canonical_ref,
        release_id=request.release_id,
        domain=point.domain,
        projection_id=MANUAL_RECALL_PROJECTION_ID,
        projection_view="default",
        projection_version=MANUAL_RECALL_TARGET_ID,
        schema_version=MANUAL_RECALL_SCHEMA_VERSION,
        embedding_model=embedding_model,
        eligibility_policy_version=MANUAL_RECALL_TARGET_ID,
        eligibility_decision_id=f"manual-recall-decision:{point.point_id}",
        eligibility_outcome="admitted",
        eligibility_limitations=(),
        source_projection_content_sha256=embedded_sha256,
        embedded_content_sha256=embedded_sha256,
        source_evidence_ids=(source_evidence_id,),
        publication_verification_evidence_ids=(
            f"manual-recall-attestation:{point.point_id}",
        ),
        lane_query_text_sha256=hashlib.sha256(
            request.query_text.encode("utf-8")
        ).hexdigest(),
        query_embedding_sha256=query_embedding_sha256,
        similarity_score=similarity_score,
    )
    evidence = EvidenceItem(
        evidence_id=trace.evidence_id,
        object_id=point.canonical_ref,
        domain=point.domain,
        lane="vector",
        source_nature="local",
        source_locator=_local_projection_locator(trace),
        snippet=point.embedded_content,
        score=similarity_score,
        source_authority=MANUAL_RECALL_SOURCE_AUTHORITY,
        claim_binding=EvidenceClaimBinding(
            subject_id=point.canonical_ref,
            predicate="semantic_recall",
            value=embedded_sha256,
            status="admitted",
        ),
        local_projection_trace=trace,
    )
    return RecallCandidate(
        raw_candidate_id=trace.raw_candidate_id,
        display_name=point.display_name,
        domain=point.domain,
        identity_kind="canonical",
        canonical_id=point.canonical_ref,
        resolution_state="resolved",
        origin_public_evidence_ids=(source_evidence_id,),
        query_view=request.query_view,
        lane="vector",
        attempt=1,
        release_id=request.release_id,
        adapter_version=MANUAL_RECALL_ADAPTER_VERSION,
        raw_score=similarity_score,
        quality_flags=(),
        evidence=(evidence,),
    )


def append_manual_candidates(
    *,
    provider: ManualRecallProvider | None,
    request: LaneRequest,
    query_vector: tuple[float, ...],
    query_embedding_sha256: str,
    embedding_model: str,
    candidates: list[RecallCandidate],
) -> int:
    """Score the eligible sidecar points against the request's query vector
    and append their candidates before the lane's sort/truncate step."""

    if provider is None:
        return 0
    from . import knowledge_read_isolated as iso  # lazy: avoids an import cycle

    appended = 0
    for point in manual_points_for_request(provider=provider, request=request):
        score = iso._cosine_similarity(query_vector, tuple(point.vector))
        candidates.append(
            manual_candidate_from_point(
                point=point,
                request=request,
                query_embedding_sha256=query_embedding_sha256,
                similarity_score=score,
                embedding_model=embedding_model,
            )
        )
        appended += 1
    return appended


__all__ = [
    "MANUAL_RECALL_ADAPTER_VERSION",
    "MANUAL_RECALL_SCHEMA_VERSION",
    "MANUAL_RECALL_SOURCE_AUTHORITY",
    "MANUAL_RECALL_TARGET_ID",
    "ManualRecallPoint",
    "ManualRecallProvider",
    "append_manual_candidates",
    "is_manual_vector_trace",
    "manual_candidate_from_point",
    "manual_points_for_request",
]
