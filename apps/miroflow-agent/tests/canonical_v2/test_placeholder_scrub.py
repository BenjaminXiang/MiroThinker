"""Unit tests for placeholder_scrub (C1 batch 0, close-workbook-gaps).

RED pinned inside the GREEN: every fixture asserts the raw projection payload
still carries the placeholder (pre-fix it flowed straight into
``content_terms`` / the F1 field-tier buckets), and the scrubbed terms drop
it. The matcher families and the 140-char cap are locked by design.md §C1-3;
the census semantics replicate g1_probe_fields.py so the packaging gate's
counts stay comparable to the run14 read-only census.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any


def _scrub() -> Any:
    return import_module("src.data_agents.canonical_v2.placeholder_scrub")


def _read_isolated() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read_isolated")


def _projection_models() -> Any:
    return import_module("src.data_agents.canonical_v2.domain_projection_models")


def test_english_sentence_prefix_family() -> None:
    scrub = _scrub()
    assert scrub.is_placeholder_value("Not supplied by the source system")
    assert scrub.is_placeholder_value("no dedicated summary available")
    assert scrub.is_placeholder_value("No data")
    assert scrub.is_placeholder_value("NOT AVAILABLE")
    assert scrub.scrub_placeholder_value("Not supplied by the source system") == ""
    # prefix family requires the sentence start — embedded mentions survive
    assert not scrub.is_placeholder_value("The field was not supplied last year")


def test_chinese_whole_value_family_including_single_wu() -> None:
    scrub = _scrub()
    for value in ("未找到", "未找到相关信息", "暂无", "暂无相关数据", "未知", "待补充", "无"):
        assert scrub.is_placeholder_value(value), value
        assert scrub.scrub_placeholder_value(value) == ""
    # single 无 only — longer values starting with 无 stay
    assert not scrub.is_placeholder_value("无数据字段")


def test_structural_family() -> None:
    scrub = _scrub()
    for value in ("-", "---", "none", "None", "N/A", "n/a"):
        assert scrub.is_placeholder_value(value), value
        assert scrub.scrub_placeholder_value(value) == ""
    assert not scrub.is_placeholder_value("none of the above applies here")


def test_glued_weizhaodao_run_erasure_keeps_real_terms() -> None:
    scrub = _scrub()
    # run14 verbatim sample (scoping §2): erasure must keep the real terms —
    # whole-value dropping would lose them (0 of the 189 runs erase empty).
    glued = "VE1未找到未找到B,VE3未找到AS等系列GPS/北斗定位器"
    assert not scrub.is_placeholder_value(glued)
    assert scrub.scrub_placeholder_value(glued) == "VE1B,VE3AS等系列GPS/北斗定位器"
    assert scrub.scrub_placeholder_value("型号未找到A") == "型号A"
    # values without the glued token pass through untouched
    assert scrub.scrub_placeholder_value("室内外配送机器人研发商") == "室内外配送机器人研发商"


def test_long_unknown_prose_survives_via_length_cap() -> None:
    scrub = _scrub()
    # The only ^未知 hit in run14 is legitimate long prose (paper summary on
    # 未知词识别); the 140-char cap is what protects it — dropping the cap or
    # widening to substring would false-kill it.
    prose = "未知词识别是自然语言处理中的关键问题，" + "本文讨论了开放词汇场景下的识别方法。" * 20
    assert len(prose) > 140
    assert not scrub.is_placeholder_value(prose)
    assert scrub.scrub_placeholder_value(prose) == prose


def test_short_legit_values_survive() -> None:
    scrub = _scrub()
    for value in ("机器人", "深圳市普渡科技有限公司", "PCB 打板", "智能仓储"):
        assert not scrub.is_placeholder_value(value), value
        assert scrub.scrub_placeholder_value(value) == value


def test_payload_scrub_skips_record_identity_fields() -> None:
    scrub = _scrub()
    payload = {
        "name": "无",  # record identity: record-level R1/R2 concern, not value scrub
        "title": "未找到",
        "patent_number": "-",
        "industry": {"name": "未找到"},
        "industry_tags": [{"name": "无"}, {"name": "机器人"}],
        "profile_summary": "主营配送机器人。未找到未找到更多资料",
        "nested": {"deep": ["暂无"]},
        "patent_count": 3,
    }
    scrubbed = scrub.scrub_projection_payload(payload)
    assert scrubbed["name"] == "无"
    assert scrubbed["title"] == "未找到"
    assert scrubbed["patent_number"] == "-"
    assert scrubbed["industry"]["name"] == ""
    assert scrubbed["industry_tags"][0]["name"] == ""
    assert scrubbed["industry_tags"][1]["name"] == "机器人"
    assert scrubbed["profile_summary"] == "主营配送机器人。更多资料"
    assert scrubbed["nested"]["deep"] == [""]
    assert scrubbed["patent_count"] == 3
    # the input payload is not mutated
    assert payload["industry"]["name"] == "未找到"


def _company_projection(**overrides: Any) -> Any:
    models = _projection_models()
    values = {
        "name": "深圳市示例科技有限公司",
        "normalized_name": "深圳市示例科技有限公司",
        "id": "company-c-example",
        "industry": None,
        "industry_tags": (),
        "tech_tags": (),
        "product_description": None,
        "profile_summary": "示例正文",
    }
    values.update(overrides)
    return models.CompanyProjection.model_construct(**values)


def test_projection_terms_scrub_placeholder_content() -> None:
    module = _read_isolated()
    scrub = _scrub()
    models = _projection_models()
    projection = _company_projection(
        industry=models.NamedReference.model_construct(
            reference_id="industry:placeholder", name="未找到"
        ),
        industry_tags=(
            models.NamedReference.model_construct(reference_id="tag:1", name="无"),
            models.NamedReference.model_construct(reference_id="tag:2", name="机器人"),
        ),
        product_description="VE1未找到未找到B系列产品",
        profile_summary="暂无",
    )
    raw_terms = module._normalized_scalar_values(projection.model_dump(mode="json"))
    # RED pin: the unscrubbed payload does carry the placeholders.
    assert "未找到" in raw_terms
    assert "暂无" in raw_terms

    _display_name, _display_terms, _identifier_terms, content_terms = (
        module._projection_terms(projection)
    )
    assert "未找到" not in content_terms
    assert "暂无" not in content_terms
    assert "无" not in content_terms
    assert "机器人" in content_terms
    # glued run erased token-wise, the real terms survive
    assert "ve1b系列产品" in content_terms
    # record identity is not value-scrubbed
    assert "深圳市示例科技有限公司" in content_terms
    assert scrub.PLACEHOLDER_IDENTITY_FIELDS == frozenset({"name", "title", "patent_number"})


def test_projection_category_term_buckets_scrub_placeholder_fields() -> None:
    module = _read_isolated()
    models = _projection_models()
    projection = _company_projection(
        industry=models.NamedReference.model_construct(
            reference_id="industry:placeholder", name="未找到"
        ),
        industry_tags=(
            models.NamedReference.model_construct(reference_id="tag:1", name="无"),
            models.NamedReference.model_construct(reference_id="tag:2", name="机器人"),
        ),
        tech_tags=(
            models.NamedReference.model_construct(reference_id="tag:3", name="-"),
        ),
        product_description="VE1未找到未找到B系列产品",
    )
    raw_buckets_terms = module._normalized_values(
        ("未找到", "无", "-", "VE1未找到未找到B系列产品")
    )
    # RED pin: pre-scrub the bucket values carried the placeholders verbatim.
    assert "未找到" in raw_buckets_terms

    industry, tags, product = module._projection_category_term_buckets(projection)
    assert industry == frozenset()
    assert tags == frozenset({"机器人"})
    assert "深圳市示例科技有限公司" in product
    assert "ve1b系列产品" in product
    assert not any("未找到" in term for term in product)


def test_scan_lookup_index_counts_and_is_read_only(tmp_path: Path) -> None:
    scrub = _scrub()
    db_path = tmp_path / "lookup.sqlite3"
    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "CREATE TABLE lookup_document ("
            "document_id TEXT PRIMARY KEY, release_id TEXT NOT NULL, "
            "projection_id TEXT NOT NULL, canonical_object_id TEXT NOT NULL, "
            "document_json TEXT NOT NULL) STRICT"
        )
        documents = (
            (
                "doc:1",
                "lookup:exact-lookup:company",
                "company-c-1",
                {
                    "name": "公司甲",
                    "profile_summary": "未找到",
                    "tech_tags": [{"name": "无"}],
                    "product_description": "VE1未找到未找到B系列产品",
                },
            ),
            (
                "doc:2",
                "lookup:exact-lookup:company",
                "company-c-2",
                {
                    "name": "公司乙",
                    "industry": {"name": "-"},
                    "profile_summary": "正规正文",
                },
            ),
            (
                "doc:3",
                "lookup:exact-lookup:professor",
                "professor-p-1",
                {"name": "教授丙", "paper_summary": "no data available"},
            ),
        )
        for document_id, projection_id, canonical_id, content in documents:
            connection.execute(
                "INSERT INTO lookup_document VALUES (?, 'r1', ?, ?, ?)",
                (
                    document_id,
                    projection_id,
                    canonical_id,
                    json.dumps(
                        {"lookup_content": json.dumps(content, ensure_ascii=False)},
                        ensure_ascii=False,
                    ),
                ),
            )
    connection.close()
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    report = scrub.scan_lookup_index(db_path)

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    assert report["schema_version"] == "canonical-v2-placeholder-scan-report-v1"
    assert report["documents"] == {
        "company": 2,
        "paper": 0,
        "patent": 0,
        "professor": 1,
    }
    # field-level (g1 classify semantics): company profile_summary + tech_tags
    # + industry; professor paper_summary
    assert report["field_placeholder_hits"] == {
        "company": 3,
        "paper": 0,
        "patent": 0,
        "professor": 1,
    }
    assert report["by_field"]["company.profile_summary"] == 1
    assert report["by_field"]["company.tech_tags"] == 1
    assert report["by_field"]["company.industry"] == 1
    # value-level: one exact whole-value 未找到, one glued run
    assert report["whole_value_weizhaodao_exact"] == 1
    assert report["glued_runs"] == 1
    assert report["samples"]["company.product_description#glued"] == [
        "VE1未找到未找到B系列产品"
    ]
