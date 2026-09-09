from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.data_agents.company.canonical_import import _evaluate_xlsx_baseline_readiness
from src.data_agents.paper.quality_promotion import (
    PaperEnrichmentSignals,
    PromotionDecision,
    evaluate_paper_promotion,
)
from src.data_agents.patent.quality_promotion import (
    PatentEnrichmentSignals,
    evaluate_patent_promotion,
)
from src.data_agents.professor.quality_gate import (
    ProfessorAffiliationState,
    ProfessorCanonicalState,
    ProfessorFactState,
    SourcePageState,
    evaluate_professor_quality,
)
from src.data_agents.quality.promotion_rules import (
    evaluate_company,
    evaluate_paper,
    evaluate_patent,
    evaluate_professor,
)


def _text(length: int) -> str:
    return "x" * length


def _zh_summary() -> str:
    return (
        "该教师长期从事人工智能与医学影像分析研究，聚焦脑疾病诊断、预后评估和多模态数据融合。"
        "其工作结合深度学习、可信人工智能和临床应用场景，形成了较稳定的研究方向。"
        "相关成果服务于智能医疗系统建设，并在人才培养和科研合作中持续积累影响。"
        "近年的研究强调算法可靠性、模型解释性和真实临床数据验证，能够为深圳高校的交叉学科布局提供支撑。"
        "团队也关注医学数据治理和跨院校协作，推动算法从实验室验证走向可审计的真实应用，并形成稳定成果。"
    )


def _professor_row() -> dict[str, object]:
    return {
        "professor_id": "prof-1",
        "canonical_name": "张三",
        "identity_status": "resolved",
        "institution": "南方科技大学",
        "department": "计算机科学与工程系",
        "title": "教授",
        "research_topic": "人工智能",
        "profile_summary": _zh_summary(),
        "official_source_url": "https://faculty.sustech.edu.cn/zhangsan",
    }


def _professor_state(row: Mapping[str, object]) -> ProfessorCanonicalState:
    return ProfessorCanonicalState(
        professor_id=str(row["professor_id"]),
        canonical_name=str(row["canonical_name"]),
        identity_status=str(row["identity_status"]),
        profile_summary=str(row["profile_summary"]),
        primary_official_profile_page_id="page-1",
        source_pages=(
            SourcePageState(
                page_id="page-1",
                url=str(row["official_source_url"]),
                is_official_source=True,
            ),
        ),
        affiliations=(
            ProfessorAffiliationState(
                institution=str(row["institution"]),
                department=str(row["department"]),
                title=str(row["title"]),
                is_primary=True,
            ),
        ),
        facts=(
            ProfessorFactState(
                fact_type="research_topic",
                value_raw=str(row["research_topic"]),
            ),
        ),
    )


def _paper_row() -> dict[str, object]:
    return {
        "paper_id": "paper-1",
        "quality_status": "needs_enrichment",
        "title_clean": "Unified Quality Gates",
        "year": 2026,
        "venue": "Journal of Data Quality",
        "authors_display": "Ada Zhang",
        "abstract_clean": "A study of quality gates.",
        "summary_zh": _text(150),
    }


def _paper_signals(row: Mapping[str, object]) -> PaperEnrichmentSignals:
    return PaperEnrichmentSignals(
        has_title=bool(str(row.get("title_clean") or "").strip()),
        has_year=row.get("year") is not None,
        has_venue=bool(str(row.get("venue") or "").strip()),
        has_authors=bool(str(row.get("authors_display") or "").strip()),
        has_abstract=bool(str(row.get("abstract_clean") or "").strip()),
        has_summary_zh=bool(str(row.get("summary_zh") or "").strip()),
    )


def _company_row() -> dict[str, object]:
    return {
        "company_id": "company-1",
        "company_name_xlsx": "Shenzhen Example Technology Co Ltd",
        "identity_status": "resolved",
        "industry": "medical AI",
        "description": "company profile",
    }


def _patent_row() -> dict[str, object]:
    return {
        "patent_id": "patent-1",
        "quality_status": "needs_enrichment",
        "patent_number": "CN123456789A",
        "title_clean": "Example patent",
        "patent_type": "invention",
        "filing_date": "2026-01-02",
        "grant_date": None,
        "publication_date": None,
        "applicants_parsed": ["Example Company"],
        "inventors_parsed": [],
        "xlsx_merged": True,
    }


def _patent_signals(row: Mapping[str, object]) -> PatentEnrichmentSignals:
    return PatentEnrichmentSignals(
        has_patent_number=bool(str(row.get("patent_number") or "").strip()),
        has_title=bool(str(row.get("title_clean") or "").strip()),
        has_patent_type=bool(str(row.get("patent_type") or "").strip()),
        has_any_date=bool(
            row.get("filing_date") or row.get("grant_date") or row.get("publication_date")
        ),
        has_applicants_or_inventors=bool(
            row.get("applicants_parsed") or row.get("inventors_parsed")
        ),
        xlsx_merged=bool(row.get("xlsx_merged")),
    )


@pytest.mark.parametrize(
    ("domain", "batch_status", "write_status"),
    [
        (
            "professor",
            evaluate_professor(_professor_row())[0],
            evaluate_professor_quality(_professor_state(_professor_row())).quality_status,
        ),
        (
            "company",
            evaluate_company(_company_row())[0],
            _evaluate_xlsx_baseline_readiness(_company_row()).quality_status,
        ),
        (
            "paper",
            evaluate_paper(_paper_row())[0],
            evaluate_paper_promotion(
                current_status=str(_paper_row()["quality_status"]),
                signals=_paper_signals(_paper_row()),
            ).next_status,
        ),
        (
            "patent",
            evaluate_patent(_patent_row())[0],
            evaluate_patent_promotion(
                current_status=str(_patent_row()["quality_status"]),
                signals=_patent_signals(_patent_row()),
            ).next_status,
        ),
    ],
)
def test_batch_promotion_rules_match_write_path_status(
    domain: str,
    batch_status: str,
    write_status: str,
) -> None:
    assert batch_status == write_status, domain


def test_evaluate_patent_delegates_to_patent_state_machine(monkeypatch) -> None:
    calls: list[tuple[str, PatentEnrichmentSignals]] = []

    def fake_evaluate_patent_promotion(
        *,
        current_status: str,
        signals: PatentEnrichmentSignals,
    ) -> PromotionDecision:
        calls.append((current_status, signals))
        return PromotionDecision("ready", "delegated")

    monkeypatch.setattr(
        "src.data_agents.quality.promotion_rules.evaluate_patent_promotion",
        fake_evaluate_patent_promotion,
    )

    assert evaluate_patent(_patent_row()) == ("ready", None)
    assert calls == [("needs_enrichment", _patent_signals(_patent_row()))]
