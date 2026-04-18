from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.company.knowledge_backfill import apply_company_knowledge_backfill
from src.data_agents.contracts import Evidence, ReleasedObject


def _company_object() -> ReleasedObject:
    return ReleasedObject(
        id="COMP-1",
        object_type="company",
        display_name="深圳无界智航科技有限公司",
        core_facts={
            "name": "深圳无界智航科技有限公司",
            "normalized_name": "无界智航科技",
            "industry": "机器人",
            "key_personnel": [],
        },
        summary_fields={
            "profile_summary": "公司画像",
            "evaluation_summary": "评价",
            "technology_route_summary": "技术路线",
        },
        evidence=[
            Evidence(
                source_type="xlsx_import",
                source_file="docs/source.xlsx",
                fetched_at=datetime(2026, 4, 16, tzinfo=timezone.utc),
            )
        ],
        last_updated=datetime(2026, 4, 16, tzinfo=timezone.utc),
        quality_status="ready",
    )


def test_apply_company_knowledge_backfill_merges_structured_fields_and_evidence(tmp_path: Path):
    backfill = tmp_path / "company_knowledge_fields.jsonl"
    backfill.write_text(
        json.dumps(
            {
                "company_name": "深圳无界智航科技有限公司",
                "data_route_types": ["real_data", "synthetic_data"],
                "real_data_methods": ["wearable_capture"],
                "synthetic_data_methods": ["physics_simulation"],
                "capability_facets": ["cross_embodiment_learning"],
                "movement_data_needs": ["proprioception"],
                "operation_data_needs": ["tactile_interaction"],
                "source_url": "https://example.com/knowledge",
                "snippet": "X-H1 与 X-Sim 构成真实+合成双引擎",
                "confidence": 0.7,
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    enriched = apply_company_knowledge_backfill([_company_object()], paths=[backfill])

    obj = enriched[0]
    assert obj.core_facts["data_route_types"] == ["real_data", "synthetic_data"]
    assert obj.core_facts["real_data_methods"] == ["wearable_capture"]
    assert obj.core_facts["synthetic_data_methods"] == ["physics_simulation"]
    assert obj.core_facts["capability_facets"] == ["cross_embodiment_learning"]
    assert any(item.source_url == "https://example.com/knowledge" for item in obj.evidence)


def test_apply_company_knowledge_backfill_merges_duplicate_entries(tmp_path: Path):
    backfill = tmp_path / "company_knowledge_fields.jsonl"
    rows = [
        {
            "company_name": "深圳无界智航科技有限公司",
            "data_route_types": ["real_data"],
            "real_data_methods": ["wearable_capture"],
            "source_url": "https://example.com/1",
        },
        {
            "company_name": "深圳无界智航科技有限公司",
            "data_route_types": ["synthetic_data"],
            "synthetic_data_methods": ["physics_simulation"],
            "source_url": "https://example.com/2",
        },
    ]
    backfill.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    enriched = apply_company_knowledge_backfill([_company_object()], paths=[backfill])

    obj = enriched[0]
    assert obj.core_facts["data_route_types"] == ["real_data", "synthetic_data"]
    assert obj.core_facts["real_data_methods"] == ["wearable_capture"]
    assert obj.core_facts["synthetic_data_methods"] == ["physics_simulation"]
    public_urls = [item.source_url for item in obj.evidence if item.source_type == "public_web"]
    assert public_urls == ["https://example.com/1", "https://example.com/2"]
