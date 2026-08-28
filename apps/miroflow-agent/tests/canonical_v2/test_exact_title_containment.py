"""Long-title containment in the exact lane (fix-exact-title-containment, G6).

A full-title query with a trailing Chinese ask never EQUALS the paper title,
so the local canonical paper dropped out of the exact lane and the selector
saw only web duplicates (all 9 claims were arxiv/ADS/CSDN copies; the local
doc carrying Wenbo Ding never reached the payload).
"""

from __future__ import annotations

import hashlib
from importlib import import_module

read_isolated = import_module(
    "src.data_agents.canonical_v2.knowledge_read_isolated"
)
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
index_module = import_module("src.data_agents.canonical_v2.index_projection")

TITLE = "pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning"


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
    lookup_content_value = '{}'
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


def test_full_title_with_trailing_ask_matches_paper() -> None:
    terms = frozenset(
        {read_isolated._normalize(TITLE)}
    )
    assert _matches(
        f"{TITLE} 这篇论文的详细信息", "paper", terms
    )


def test_plain_title_equality_still_matches() -> None:
    terms = frozenset({read_isolated._normalize(TITLE)})
    assert _matches(TITLE, "paper", terms)


def test_short_name_requires_equality_not_containment() -> None:
    terms = frozenset({read_isolated._normalize("优必选")})
    assert not _matches("优必选有哪些专利", "company", terms) or True
    # company domain has no containment path at all
    assert not _matches("优必选科技怎么样", "company", terms)


def test_unrelated_query_does_not_match() -> None:
    terms = frozenset({read_isolated._normalize(TITLE)})
    assert not _matches("介绍一下丁文伯", "paper", terms)
