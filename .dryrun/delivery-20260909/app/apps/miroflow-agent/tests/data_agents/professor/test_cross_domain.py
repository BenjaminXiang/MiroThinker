# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.cross_domain import (
    CompanyLink,
    PaperLink,
    PaperStagingRecord,
    PatentLink,
)


def test_paper_link_with_all_fields():
    link = PaperLink(
        paper_id="PAPER-abc123",
        title="Attention Is All You Need",
        year=2017,
        venue="NeurIPS",
        citation_count=95000,
        doi="10.5555/3295222.3295349",
        source="semantic_scholar",
    )
    assert link.paper_id == "PAPER-abc123"
    assert link.title == "Attention Is All You Need"
    assert link.year == 2017
    assert link.citation_count == 95000


def test_paper_link_pre_backfill_state():
    link = PaperLink(
        paper_id=None,
        title="Some Paper",
        source="dblp",
    )
    assert link.paper_id is None
    assert link.year is None
    assert link.doi is None


def test_company_link_validates():
    link = CompanyLink(
        company_name="深圳量子科技",
        role="联合创始人",
        evidence_url="https://tianyancha.com/xxx",
        source="web_scrape",
    )
    assert link.company_id is None
    assert link.role == "联合创始人"


def test_patent_link_defaults():
    link = PatentLink(
        patent_title="一种基于深度学习的蛋白质结构预测方法",
        patent_number="CN202110001234.5",
        source="web_search",
    )
    assert link.role == "发明人"
    assert link.patent_id is None


def test_paper_staging_record_serialization_roundtrip():
    record = PaperStagingRecord(
        title="Protein Structure Prediction",
        authors=["张三", "李四"],
        year=2024,
        venue="Nature",
        abstract="We propose a novel method...",
        doi="10.1038/s41586-024-00001",
        citation_count=150,
        keywords=["protein", "deep learning"],
        source_url="https://semanticscholar.org/paper/xxx",
        source="semantic_scholar",
        anchoring_professor_id="PROF-abc123",
        anchoring_professor_name="张三",
        anchoring_institution="南方科技大学",
    )
    json_str = record.model_dump_json()
    restored = PaperStagingRecord.model_validate_json(json_str)
    assert restored.title == record.title
    assert restored.authors == record.authors
    assert restored.year == record.year
    assert restored.keywords == record.keywords
    assert restored.anchoring_professor_id == record.anchoring_professor_id


def test_paper_staging_record_minimal():
    record = PaperStagingRecord(
        title="Minimal Paper",
        authors=["Author"],
        source_url="https://arxiv.org/abs/2401.00001",
        source="arxiv",
        anchoring_professor_id="PROF-001",
        anchoring_professor_name="Test",
        anchoring_institution="南方科技大学",
    )
    assert record.year is None
    assert record.keywords == []
    assert record.abstract is None
