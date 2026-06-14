from __future__ import annotations

from decimal import Decimal

from src.data_agents.canonical.paper import ProfessorPaperLink
from src.data_agents.quality.threshold_config import PROFESSOR_PAPER_LINK_PROMOTION


def test_professor_paper_link_accepts_homepage_tier_evidence_sources():
    for evidence_source_type in ("prof_homepage_tier2", "prof_homepage_tier3"):
        link = ProfessorPaperLink(
            professor_id="PROF-001",
            paper_id="PAPER-001",
            link_status="verified",
            evidence_source_type=evidence_source_type,
            match_reason="Page-declared paper evidence preserves homepage tier.",
            author_name_match_score=Decimal("1.0"),
            is_officially_listed=True,
        )

        assert link.evidence_source_type == evidence_source_type


def test_homepage_tier_evidence_sources_are_promotion_eligible():
    assert "prof_homepage_tier2" in (
        PROFESSOR_PAPER_LINK_PROMOTION.allowed_evidence_sources
    )
    assert "prof_homepage_tier3" in (
        PROFESSOR_PAPER_LINK_PROMOTION.allowed_evidence_sources
    )
