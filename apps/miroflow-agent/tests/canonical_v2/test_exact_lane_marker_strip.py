"""Stage0-G2a: the exact lane must strip the planner's `[lane=exact]` marker
before equality matching. RED evidence for
openspec/changes/exact-lane-name-marker-strip.

The planner stamps every lane query as f"{pure_topic} [lane={lane}]"; the
lexical/vector/web lanes strip their own marker before matching — the exact
lane never did, so name equality could never succeed (golden set: exact
lane 0 for all name queries, only patent identifiers via the protected
exact_identifier slot).
"""

from __future__ import annotations

import hashlib
from importlib import import_module

read_isolated = import_module(
    "src.data_agents.canonical_v2.knowledge_read_isolated"
)
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
index_module = import_module("src.data_agents.canonical_v2.index_projection")

COMPANY = "深圳市飞象工业科技有限公司"


def _request(query: str, domains: tuple[str, ...]) -> object:
    return read_module.LaneRequest(
        lane="exact",
        release_id="test-release",
        query_view=query,
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        query_text=query,
        domains=domains,
        protected_slots=(),
        structured_constraints=read_module.StructuredConstraints(),
        max_candidates=8,
    )


def _matches(query: str, domain: str, display_terms: frozenset[str]) -> bool:
    lookup_content_value = "{}"
    document = index_module.LookupProjectionDocument(
        document_id="lookup-document:sha256:" + "a" * 64,
        canonical_object_id=f"{domain}-c-test",
        release_id="test-release",
        projection_id=f"lookup:exact-lookup:{domain}",
        projection_scope=index_module.ProjectionScope.public_domain,
        domain=domain,
        reference_type=None,
        path="exact_lookup",
        projection_view=index_module.ProjectionView.default,
        projection_version="canonical-v2-lookup-projection-v1",
        schema_version="canonical-v2-lookup-schema-v1",
        eligibility_policy_version="v1",
        eligibility_decision_id="decision:test",
        eligibility_outcome="admitted",
        source_projection_content_sha256="c" * 64,
        lookup_content=lookup_content_value,
        lookup_content_sha256=hashlib.sha256(
            lookup_content_value.encode("utf-8")
        ).hexdigest(),
        source_evidence_ids=("evidence:test",),
    )
    return read_isolated._matches_exact_request(
        request=_request(query, (domain,)),
        document=document,
        display_terms=display_terms,
        identifier_terms=frozenset(),
        content_terms=frozenset(),
    )


def test_exact_name_query_with_lane_marker_matches() -> None:
    terms = frozenset({read_isolated._normalize(COMPANY)})
    assert _matches(f"{COMPANY} [lane=exact]", "company", terms)


def test_markerless_exact_name_query_still_matches() -> None:
    terms = frozenset({read_isolated._normalize(COMPANY)})
    assert _matches(COMPANY, "company", terms)


def test_containment_with_marker_keeps_g6_behavior() -> None:
    title = "A Substantial Paper Title Long Enough For Containment Rules"
    terms = frozenset({read_isolated._normalize(title)})
    assert _matches(f"{title} 这篇论文的详细信息 [lane=exact]", "paper", terms)
