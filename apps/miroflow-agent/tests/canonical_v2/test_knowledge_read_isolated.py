"""Unit tests for the lexical-lane category-recall fallback (F1,
close-workbook-gaps B1) in knowledge_read_isolated.

The fallback fires only when the whole-phrase lexical pass returns empty on
an enumeration-marker query; these tests pin the term-extraction matrix, the
precision guardrails, and the field-tier weighting directly against
`_category_query_terms` / `_category_recall_entries` with fabricated lookup
entries. The adapter-level wiring is covered in test_serving_pack_loader.py
(both lane adapters, lockstep) and the sealed-pack GT evidence lives in
.agents/runs/close-workbook-gaps/d0-probe/f1-verify.md.
"""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from typing import Any


RELEASE_ID = "candidate-f1-tests"


def _module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read_isolated")


def _index_module() -> Any:
    return import_module("src.data_agents.canonical_v2.index_projection")


def _read_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read")


def _document(
    index_module: Any,
    *,
    canonical_id: str,
    domain: str = "company",
) -> Any:
    content = json.dumps({"name": canonical_id}, ensure_ascii=False)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return index_module.LookupProjectionDocument(
        document_id=f"doc:{canonical_id}",
        canonical_object_id=canonical_id,
        release_id=RELEASE_ID,
        projection_id=f"projection:{canonical_id}",
        projection_scope=index_module.ProjectionScope.public_domain,
        domain=domain,
        reference_type=None,
        projection_view=index_module.ProjectionView.default,
        eligibility_policy_version="test-eligibility-v1",
        eligibility_decision_id=f"decision:{canonical_id}",
        eligibility_outcome="admitted",
        source_projection_content_sha256=digest,
        lookup_content=content,
        lookup_content_sha256=digest,
        source_evidence_ids=(f"evidence:{canonical_id}",),
    )


def _entry(
    module: Any,
    index_module: Any,
    *,
    canonical_id: str,
    display_name: str,
    content_terms: tuple[str, ...],
    industry_terms: tuple[str, ...] = (),
    tag_terms: tuple[str, ...] = (),
    product_terms: tuple[str, ...] = (),
    domain: str = "company",
) -> Any:
    return module._PublicLookupEntry(
        document=_document(index_module, canonical_id=canonical_id, domain=domain),
        display_name=display_name,
        display_terms=frozenset({display_name}),
        identifier_terms=frozenset(),
        content_terms=frozenset(content_terms),
        industry_label_terms=frozenset(industry_terms),
        tag_category_terms=frozenset(tag_terms),
        product_category_terms=frozenset(product_terms),
    )


def _request(
    read_module: Any,
    query: str,
    *,
    max_candidates: int = 48,
    displayed_ids: tuple[str, ...] = (),
    excluded_terms: tuple[str, ...] = (),
    domains: tuple[str, ...] = ("company",),
) -> Any:
    return read_module.LaneRequest(
        lane="lexical",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        query_text=query,
        domains=domains,
        protected_slots=(),
        structured_constraints=read_module.StructuredConstraints(
            displayed_entity_ids=displayed_ids,
            excluded_terms=excluded_terms,
        ),
        max_candidates=max_candidates,
    )


def test_category_query_terms_extraction_matrix() -> None:
    module = _module()
    # run14 verbatim category queries (turn-trace 2026-09-10): stopword
    # phrases and geography strip away; >= 4-char CJK runs decompose into
    # overlapping bigrams; short CJK runs and latin/digit runs stay whole.
    assert module._category_query_terms("中国有哪些成熟的酒店送餐机器人供应商") == (
        ("器人", 1),
        ("店送", 1),
        ("机器", 1),
        ("送餐", 1),
        ("酒店", 1),
        ("餐机", 1),
    )
    assert module._category_query_terms("我想找PCB打板， 有哪些推荐") == (
        ("pcb", 2),
        ("我想找", 2),
        ("打板", 2),
    )
    assert module._category_query_terms("深圳有哪些做具身智能的公司") == (
        ("具身", 1),
        ("智能", 1),
        ("身智", 1),
    )


def test_category_query_terms_rejects_non_enumeration_queries() -> None:
    module = _module()
    # No enumeration marker -> no terms, no fallback, no behavior change for
    # single-entity or free-text questions.
    assert module._category_query_terms("深南电路怎么样") == ()
    assert (
        module._category_query_terms("介绍一下国际先进技术应用推进中心（深圳）") == ()
    )


def test_category_query_terms_drops_empty_and_single_char_residue() -> None:
    module = _module()
    assert module._category_query_terms("有哪些公司") == ()
    assert module._category_query_terms("深圳有哪些做灯的公司") == ()


def test_category_recall_rejects_non_enumeration_query() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    entry = _entry(
        module,
        index_module,
        canonical_id="company-c-one",
        display_name="阿尔法机器人",
        content_terms=("阿尔法机器人是一家机器人企业",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "阿尔法机器人怎么样"),
        entries=(entry,),
    )
    assert result == []


def test_category_recall_requires_two_documents_per_bigram() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # 仓储/储搬/搬运 each hit exactly one document: a document matching only
    # such singleton bigrams is entity-fragment noise and stays out even
    # though three of them would clear the score floor together.
    noisy = _entry(
        module,
        index_module,
        canonical_id="company-c-noise",
        display_name="仓储搬运服务商",
        content_terms=("仓储搬运方案提供商",),
    )
    on_topic = _entry(
        module,
        index_module,
        canonical_id="company-c-topic-a",
        display_name="配送机器人甲",
        content_terms=("室内外配送机器人研发商",),
    )
    also_on_topic = _entry(
        module,
        index_module,
        canonical_id="company-c-topic-b",
        display_name="配送机器人乙",
        content_terms=("酒店配送机器人方案",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些做仓储搬运配送机器人的公司"),
        entries=(noisy, on_topic, also_on_topic),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-topic-a",
        "company-c-topic-b",
    ]


def test_category_recall_keeps_singleton_word_term() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # A weight-2 self-delimiting word (latin run or short CJK run) is a real
    # category signal even with a single hit — the exact lane owns entity
    # names, not vocabulary words like FPC.
    entry = _entry(
        module,
        index_module,
        canonical_id="company-c-fpc",
        display_name="柔性电路公司",
        content_terms=("fpc组件产品研发商",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些做FPC的公司"),
        entries=(entry,),
    )
    assert [entry.document.canonical_object_id for entry in result] == ["company-c-fpc"]


def test_category_recall_min_score_excludes_single_bigram() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # 机器视觉 mentions 机器 only: one stray bigram (score 1) never recalls,
    # while true 机器人 hits score 机器+器人 = 2.
    off_topic = _entry(
        module,
        index_module,
        canonical_id="company-c-vision",
        display_name="机器视觉公司",
        content_terms=("工业机器视觉检测服务商",),
    )
    on_topic_a = _entry(
        module,
        index_module,
        canonical_id="company-c-robot-a",
        display_name="机器人甲",
        content_terms=("配送机器人研发商",),
    )
    on_topic_b = _entry(
        module,
        index_module,
        canonical_id="company-c-robot-b",
        display_name="机器人乙",
        content_terms=("清洁机器人制造商",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些做配送机器人的公司"),
        entries=(off_topic, on_topic_a, on_topic_b),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-robot-a",
        "company-c-robot-b",
    ]


def test_category_recall_boosts_category_field_hits() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # Same flat hit count; the entry carrying the term in its curated
    # category tags (industry_tags/tech_tags) outranks a long-summary-only
    # mention.
    summary_only = _entry(
        module,
        index_module,
        canonical_id="company-c-summary",
        display_name="甲企业",
        content_terms=("甲企业是一家多元化集团，历史沿革提及机器人业务",),
    )
    tag_hit = _entry(
        module,
        index_module,
        canonical_id="company-c-tag",
        display_name="乙企业",
        content_terms=("乙企业简介", "机器人"),
        tag_terms=("机器人",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司"),
        entries=(summary_only, tag_hit),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-tag",
        "company-c-summary",
    ]


def test_category_recall_respects_domain_displayed_and_exclusions() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    company_a = _entry(
        module,
        index_module,
        canonical_id="company-c-a",
        display_name="机器人甲",
        content_terms=("配送机器人研发商",),
    )
    company_b = _entry(
        module,
        index_module,
        canonical_id="company-c-b",
        display_name="机器人乙",
        content_terms=("清洁机器人制造商",),
    )
    paper = _entry(
        module,
        index_module,
        canonical_id="paper-c-one",
        display_name="机器人论文",
        content_terms=("机器人控制论文",),
        domain="paper",
    )
    entries = (company_a, company_b, paper)
    # Domain filter: the paper entry never joins a company-domain request.
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司"),
        entries=entries,
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-a",
        "company-c-b",
    ]
    # Displayed-set restriction mirrors _matches_lexical_request semantics.
    result = module._category_recall_entries(
        request=_request(
            read_module, "深圳有哪些机器人公司", displayed_ids=("company-c-b",)
        ),
        entries=entries,
    )
    assert [entry.document.canonical_object_id for entry in result] == ["company-c-b"]
    # Excluded terms drop matching documents.
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司", excluded_terms=("配送",)),
        entries=entries,
    )
    assert [entry.document.canonical_object_id for entry in result] == ["company-c-b"]


def test_category_recall_truncates_at_window_with_deterministic_order() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    entries = tuple(
        _entry(
            module,
            index_module,
            canonical_id=f"company-c-{index:02d}",
            display_name=f"机器人公司{index:02d}",
            content_terms=(f"机器人公司{index:02d}是机器人研发商",),
        )
        for index in range(5)
    )
    request = _request(read_module, "深圳有哪些机器人公司", max_candidates=3)
    first = module._category_recall_entries(request=request, entries=entries)
    second = module._category_recall_entries(request=request, entries=entries)
    assert [entry.document.canonical_object_id for entry in first] == [
        "company-c-00",
        "company-c-01",
        "company-c-02",
    ]
    assert [entry.document.canonical_object_id for entry in second] == [
        entry.document.canonical_object_id for entry in first
    ]


def test_category_recall_field_tiers_order_industry_tags_product_summary() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # One weight-2 term ("机器人"); the same hit scores 2*8 in the closed
    # industry label, 2*4 in the curated tags, 2*2 in the short identity /
    # product-line fields, and 2*1 in the long summaries. Canonical ids are
    # assigned so plain id order would reverse the expected ranking — only
    # the field tiers produce it.
    industry_hit = _entry(
        module,
        index_module,
        canonical_id="company-c-3-industry",
        display_name="甲企业",
        content_terms=("甲企业机器人研发",),
        industry_terms=("机器人",),
    )
    tag_hit = _entry(
        module,
        index_module,
        canonical_id="company-c-2-tags",
        display_name="乙企业",
        content_terms=("乙企业机器人制造",),
        tag_terms=("机器人",),
    )
    product_hit = _entry(
        module,
        index_module,
        canonical_id="company-c-1-product",
        display_name="丙企业",
        content_terms=("丙企业机器人集成",),
        product_terms=("机器人产品线",),
    )
    summary_hit = _entry(
        module,
        index_module,
        canonical_id="company-c-0-summary",
        display_name="丁企业",
        content_terms=("丁企业多元化集团，历史沿革提及机器人业务",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司"),
        entries=(summary_hit, product_hit, tag_hit, industry_hit),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-3-industry",
        "company-c-2-tags",
        "company-c-1-product",
        "company-c-0-summary",
    ]


def test_category_recall_industry_label_outranks_multi_term_summary_tie() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # The run14 g2 failure shape: a true category member whose only signal is
    # industry=机器人 must outrank tie-mass companies whose long summaries
    # happen to mention most of the query's scenario words. 餐机 hits only
    # one document and dies on the bigram-coverage guardrail.
    tie_mass_a = _entry(
        module,
        index_module,
        canonical_id="company-c-a",
        display_name="甲企业",
        content_terms=("豪华酒店送餐机器人一体化解决方案",),
    )
    tie_mass_b = _entry(
        module,
        index_module,
        canonical_id="company-c-b",
        display_name="乙企业",
        content_terms=("连锁酒店送餐服务商",),
    )
    category_member = _entry(
        module,
        index_module,
        canonical_id="company-c-c",
        display_name="丙企业",
        content_terms=("丙配送机器人",),
        industry_terms=("机器人",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "中国有哪些成熟的酒店送餐机器人供应商"),
        entries=(tie_mass_a, tie_mass_b, category_member),
    )
    # 16 (机器+器人 at x8) beats 5 (five summary bigrams) and 3.
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-c",
        "company-c-a",
        "company-c-b",
    ]


def test_category_recall_field_tier_counts_highest_tier_once() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    # A term hitting several tiers counts once at the highest tier, never
    # stacked: both entries score 2*8=16, so the tie falls back to canonical
    # id order (company-c-a first); stacking (8+2=10, score 20) would put
    # company-c-b first.
    industry_only = _entry(
        module,
        index_module,
        canonical_id="company-c-a",
        display_name="甲企业",
        content_terms=("甲机器人",),
        industry_terms=("机器人",),
    )
    industry_and_product = _entry(
        module,
        index_module,
        canonical_id="company-c-b",
        display_name="乙企业",
        content_terms=("乙机器人",),
        industry_terms=("机器人",),
        product_terms=("机器人",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司"),
        entries=(industry_and_product, industry_only),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-a",
        "company-c-b",
    ]


def _declaration_module() -> Any:
    return import_module("src.data_agents.canonical_v2.anchoring_declaration")


def test_anchoring_declaration_unknown_schema_fails_closed() -> None:
    declaration_module = _declaration_module()
    valid_bytes = json.dumps(
        {
            "schema_version": declaration_module.DECLARATION_SCHEMA_VERSION,
            "generated_from": {
                "pack_id": "serving-pack:test",
                "pack_sha256": "0" * 64,
                "sources": ["test"],
            },
            "f1_category_scoring": {
                "field_tier_multipliers": {
                    "industry_label": 8,
                    "tag": 4,
                    "product": 2,
                },
                "min_bigram_coverage": 2,
                "min_score": 2,
            },
            "terms": [],
        }
    ).encode("utf-8")
    parsed = declaration_module.parse_anchoring_declaration(valid_bytes)
    assert parsed.f1_category_scoring.field_tier_multipliers.industry_label == 8

    tampered = json.loads(valid_bytes)
    tampered["schema_version"] = "canonical-v2-anchoring-declaration-v999"
    try:
        declaration_module.parse_anchoring_declaration(
            json.dumps(tampered).encode("utf-8")
        )
    except RuntimeError as exc:
        assert "schema version" in str(exc)
    else:  # pragma: no cover - the raise is the contract
        raise AssertionError("unknown schema must fail closed")
    try:
        declaration_module.parse_anchoring_declaration(b"[]")
    except RuntimeError as exc:
        assert "JSON object" in str(exc)
    else:  # pragma: no cover - the raise is the contract
        raise AssertionError("non-object declaration must fail closed")
    try:
        declaration_module.parse_anchoring_declaration(
            b'{"schema_version": 1, "schema_version": 2}'
        )
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - the raise is the contract
        raise AssertionError("duplicate keys must fail closed")


def test_f1_scoring_consumes_anchoring_declaration_equivalently() -> None:
    module = _module()
    read_module = _read_module()
    index_module = _index_module()
    declaration_module = _declaration_module()
    scoring = declaration_module.PACKAGED_ANCHORING_DECLARATION.f1_category_scoring
    # Equivalence pin: the packaged declaration carries exactly the constants
    # measured on the sealed run14 pack (design.md §C1-5: behavior-preserving).
    assert (
        scoring.field_tier_multipliers.industry_label,
        scoring.field_tier_multipliers.tag,
        scoring.field_tier_multipliers.product,
        scoring.min_bigram_coverage,
        scoring.min_score,
    ) == (8, 4, 2, 2, 2)
    assert module._F1_CATEGORY_SCORING is scoring

    # Behavioral equivalence: a weight-2 term scores 2*8=16 on the industry
    # label, 2*4=8 on curated tags, 2*1=2 in a long summary — the exact
    # ranking the hardcoded constants produced.
    label_member = _entry(
        module,
        index_module,
        canonical_id="company-c-label",
        display_name="甲企业",
        content_terms=("甲机器人研发商",),
        industry_terms=("机器人",),
    )
    tag_member = _entry(
        module,
        index_module,
        canonical_id="company-c-tag",
        display_name="乙企业",
        content_terms=("乙机器人研发商",),
        tag_terms=("机器人",),
    )
    summary_only = _entry(
        module,
        index_module,
        canonical_id="company-c-summary",
        display_name="丙企业",
        content_terms=("丙企业长期从事机器人集成业务",),
    )
    result = module._category_recall_entries(
        request=_request(read_module, "深圳有哪些机器人公司"),
        entries=(summary_only, tag_member, label_member),
    )
    assert [entry.document.canonical_object_id for entry in result] == [
        "company-c-label",
        "company-c-tag",
        "company-c-summary",
    ]
