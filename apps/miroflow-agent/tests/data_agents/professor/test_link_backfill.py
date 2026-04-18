from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.professor.link_backfill import apply_professor_company_role_backfill


def _professor_object() -> ReleasedObject:
    return ReleasedObject(
        id="PROF-1",
        object_type="professor",
        display_name="丁文伯",
        core_facts={
            "name": "丁文伯",
            "institution": "清华大学深圳国际研究生院",
            "company_roles": [],
            "top_papers": [],
            "patent_ids": [],
        },
        summary_fields={"profile_summary": "教授画像"},
        evidence=[
            Evidence(
                source_type="official_site",
                source_url="https://www.sigs.tsinghua.edu.cn/example",
                fetched_at=datetime(2026, 4, 16, tzinfo=timezone.utc),
            )
        ],
        last_updated=datetime(2026, 4, 16, tzinfo=timezone.utc),
        quality_status="ready",
    )


def test_apply_professor_company_role_backfill_adds_role_and_public_evidence(tmp_path: Path):
    backfill = tmp_path / "professor_company_roles.jsonl"
    backfill.write_text(
        json.dumps(
            {
                "professor_name": "丁文伯",
                "company_name": "深圳无界智航科技有限公司",
                "role": "发起人",
                "source_url": "https://example.com/article",
                "snippet": "丁文伯｜清华大学 长聘副教授、Xspark AI发起人",
                "confidence": 0.72,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    enriched = apply_professor_company_role_backfill([_professor_object()], paths=[backfill])

    assert len(enriched) == 1
    obj = enriched[0]
    assert obj.core_facts["company_roles"] == [
        {"company_name": "深圳无界智航科技有限公司", "role": "发起人"}
    ]
    assert any(item.source_type == "public_web" for item in obj.evidence)
    assert any(item.source_url == "https://example.com/article" for item in obj.evidence)


def test_apply_professor_company_role_backfill_dedupes_role_but_keeps_multiple_evidence(tmp_path: Path):
    backfill = tmp_path / "professor_company_roles.jsonl"
    rows = [
        {
            "professor_name": "丁文伯",
            "company_name": "深圳无界智航科技有限公司",
            "role": "发起人",
            "source_url": "https://example.com/article-1",
            "snippet": "证据 1",
            "confidence": 0.72,
        },
        {
            "professor_name": "丁文伯",
            "company_name": "深圳无界智航科技有限公司",
            "role": "发起人",
            "source_url": "https://example.com/article-2",
            "snippet": "证据 2",
            "confidence": 0.78,
        },
    ]
    backfill.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    enriched = apply_professor_company_role_backfill([_professor_object()], paths=[backfill])

    obj = enriched[0]
    assert obj.core_facts["company_roles"] == [
        {"company_name": "深圳无界智航科技有限公司", "role": "发起人"}
    ]
    public_urls = [item.source_url for item in obj.evidence if item.source_type == "public_web"]
    assert public_urls == ["https://example.com/article-1", "https://example.com/article-2"]
