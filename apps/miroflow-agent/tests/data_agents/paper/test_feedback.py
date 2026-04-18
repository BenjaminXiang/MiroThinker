from __future__ import annotations

from datetime import datetime, timezone

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.evidence import build_evidence
from src.data_agents.paper.feedback import apply_paper_feedback_to_professors
from src.data_agents.paper.models import AuthorPaperMetrics, DiscoveredPaper


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def _professor_record() -> ProfessorRecord:
    return ProfessorRecord(
        id="PROF-1",
        name="靳玉乐",
        institution="深圳大学",
        department="教育学部",
        title="教授",
        research_directions=["课程论"],
        profile_summary="靳玉乐现任深圳大学教育学部教授，研究方向包括课程论。",
        evaluation_summary="靳玉乐当前资料完整度为structured，已按官网资料完成基础核验。",
        evidence=[
            build_evidence(
                source_type="official_site",
                source_url="https://fe.szu.edu.cn/info/1021/1191.htm",
                fetched_at=TIMESTAMP,
                confidence=0.9,
            )
        ],
        last_updated=TIMESTAMP,
    )


def test_apply_paper_feedback_to_professors_updates_metrics_and_summary():
    updated = apply_paper_feedback_to_professors(
        professors=[_professor_record()],
        papers=[
            DiscoveredPaper(
                paper_id="paper-a",
                title="要认真对待高校课程思政的“泛意识形态化”倾向",
                year=2021,
                publication_date="2021-04-15",
                venue="江苏高教",
                doi="10.16697/J.1674-5485.2021.04.005",
                arxiv_id=None,
                abstract="讨论高校课程思政泛意识形态化倾向的表现与治理路径。",
                authors=("靳玉乐", "张良"),
                professor_ids=("PROF-1",),
                citation_count=5,
                source_url="https://www.semanticscholar.org/paper/paper-a",
            )
        ],
        author_metrics={
            "PROF-1": AuthorPaperMetrics(
                professor_id="PROF-1",
                author_id="136691277",
                h_index=3,
                citation_count=9,
            )
        },
        now=TIMESTAMP,
    )

    assert len(updated) == 1
    professor = updated[0]
    assert professor.h_index == 3
    assert professor.citation_count == 9
    assert "课程思政" in professor.research_directions
    assert "近期论文" in professor.profile_summary
    assert "h-index=3" in professor.evaluation_summary
