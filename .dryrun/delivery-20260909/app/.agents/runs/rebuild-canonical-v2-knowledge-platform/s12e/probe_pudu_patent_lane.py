"""In-process probe: does the s12e relationship lane enumerate Pudu's patents?

Builds the exact serving-pack relationship authority (same recipe as
create_serving_pack_knowledge_read) and runs _build_relationship_result for a
company_to_patent LaneRequest on 深圳市普渡科技有限公司, printing candidate
count, ids, display names, snippet sizes, and wall time. No server, no LLM.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_read_isolated as iso  # noqa: E402
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2.contracts import PublishedRelease  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    EnumerationPolicy,
    LaneRequest,
    ProtectedSlot,
    RelationshipPathProposal,
    StructuredConstraints,
    WebSearchPolicy,
)

RELEASE_ID = "candidate-s12e-20260801-v1"
PUDU_ID = "company-c-5fac6a22c980262f125f995d"
NOW = datetime.now(UTC)

t0 = time.monotonic()
authority_pack = pack_loader.open_serving_pack_authority(
    pack_dir=Path("/var/tmp/mirothinker-canonical-v2-s12e/serving-pack"),
    expected_release_id=RELEASE_ID,
    expected_index_marker_sha256=(
        "1fafb12bf8870244b34862801ccef6e6ea58434a95592c29355eee11c3ce04b1"
    ),
    expected_forbidden_milvus_path=Path(
        "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
    ),
)
print(f"pack authority open: {time.monotonic() - t0:.1f}s")

bundle = authority_pack.release_bundle
index_request = authority_pack.index_projection_request
institution_catalog = authority_pack.institution_catalog
candidate_request = index_request.candidate_projection_request
candidate_result = index_request.candidate_projection_result
internal_result = candidate_request.internal_reference_projection_result

published = PublishedRelease(
    release_id=RELEASE_ID,
    previous_release_id=None,
    canonical_release_id=RELEASE_ID,
    published_projection_release_id=RELEASE_ID,
    index_release_id=RELEASE_ID,
    state="active",
    changed_at=datetime(2026, 7, 22, tzinfo=UTC),
    verification_evidence_ids=tuple(authority_pack.release_verification.evidence_ids),
)
person_records = iso._derive_person_reference_records(
    candidate_result=candidate_result,
    internal_result=internal_result,
    institution_catalog=institution_catalog,
)
technology_records = iso._derive_technology_route_records(candidate_result)
internal_reference_authority = iso._InternalReferenceAuthority(
    bundle=bundle,
    publication=published,
    index_request=index_request,
    institution_catalog=institution_catalog,
    internal_result=internal_result,
    person_records=person_records,
    technology_records=technology_records,
)
relationship_request = bundle.relationship_projection_request
relationship_result = bundle.relationship_projection_result
t0 = time.monotonic()
relationship_authority = iso._RelationshipAuthority(
    internal_authority=internal_reference_authority,
    relationship_request=relationship_request,
    relationship_result=relationship_result,
    candidate_result=candidate_result,
    relationship_request_content_sha256=iso._canonical_sha256(
        relationship_request.model_dump(mode="json")
    ),
)
print(f"authority hash precompute: {time.monotonic() - t0:.1f}s")

protected_slot = ProtectedSlot(
    kind="displayed_entity_set",
    value="displayed_entity_set",
    entity_ids=(PUDU_ID,),
)
lane_request = LaneRequest(
    lane="relationship",
    release_id=RELEASE_ID,
    query_view="view:original",
    original_query="深圳市普渡科技有限公司有哪些专利",
    behavior_class="D",
    interaction_mode="information_retrieval",
    web_policy=WebSearchPolicy(
        mode="universal",
        max_provider_calls=1,
        timeout_ms=1_000,
        max_results=5,
    ),
    query_text="深圳市普渡科技有限公司有哪些专利",
    domains=("patent",),
    protected_slots=(protected_slot,),
    structured_constraints=StructuredConstraints(displayed_entity_ids=(PUDU_ID,)),
    max_candidates=24,
    relationship_paths=(
        RelationshipPathProposal(
            relationship_type_id="company_has_patent",
            direction="company_to_patent",
            source_type="company",
            target_type="patent",
        ),
    ),
    relationship_enumeration_policy=EnumerationPolicy(
        mode="representative",
        scope="深圳市普渡科技有限公司有哪些专利",
        as_of=NOW,
    ),
)

t0 = time.monotonic()
result = iso._build_relationship_result(
    request=lane_request,
    authority=relationship_authority,
)
elapsed = time.monotonic() - t0
print(f"lane execute: {elapsed:.2f}s, candidates: {len(result.candidates)}")
for candidate in result.candidates:
    evidence = candidate.evidence[0]
    print(
        "-",
        candidate.canonical_id,
        repr(candidate.display_name)[:80],
        f"snippet_bytes={len(evidence.snippet.encode('utf-8'))}",
        f"claim={evidence.claim_binding.predicate if evidence.claim_binding else None}",
    )

t0 = time.monotonic()
result2 = iso._build_relationship_result(
    request=lane_request,
    authority=relationship_authority,
)
print(f"lane re-execute (validation twin): {time.monotonic() - t0:.2f}s")
