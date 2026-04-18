from __future__ import annotations

from datetime import datetime, timezone

from src.data_agents.contracts import (
    CompanyRecord,
    PaperRecord,
    ProfessorPaperLinkRecord,
    ProfessorRecord,
)
from src.data_agents.evidence import build_evidence
from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def _professor_record() -> ProfessorRecord:
    return ProfessorRecord(
        id="PROF-1",
        name="靳玉乐",
        institution="深圳大学",
        department="教育学部",
        title="教授",
        research_directions=["课程思政"],
        profile_summary="靳玉乐现任深圳大学教育学部教授，研究方向包括课程思政。",
        evaluation_summary="靳玉乐当前资料完整度为structured，已关联课程思政论文。",
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


def _paper_record() -> PaperRecord:
    return PaperRecord(
        id="PAPER-1",
        title="要认真对待高校课程思政的“泛意识形态化”倾向",
        title_zh="要认真对待高校课程思政的“泛意识形态化”倾向",
        authors=["靳玉乐", "张良"],
        year=2021,
        venue="江苏高教",
        doi="10.16697/J.1674-5485.2021.04.005",
        publication_date="2021-04-15",
        keywords=["课程思政", "课程论"],
        citation_count=2,
        professor_ids=["PROF-1"],
        summary_zh="what：论文讨论课程思政治理。why：为高校教学改革提供参考。how：基于政策和实践分析。result：提出治理路径。",
        summary_text="what：论文讨论课程思政治理。why：为高校教学改革提供参考。how：基于政策和实践分析。result：提出治理路径。",
        evidence=[
            build_evidence(
                source_type="academic_platform",
                source_url="https://www.semanticscholar.org/paper/PAPER-1",
                fetched_at=TIMESTAMP,
                confidence=0.8,
            )
        ],
        last_updated=TIMESTAMP,
    )


def _professor_paper_link_record() -> ProfessorPaperLinkRecord:
    return ProfessorPaperLinkRecord(
        id="PPLINK-1",
        professor_id="PROF-1",
        paper_id="PAPER-1",
        professor_name="靳玉乐",
        paper_title="要认真对待高校课程思政的“泛意识形态化”倾向",
        link_status="verified",
        evidence_source="official_site",
        evidence_url="https://fe.szu.edu.cn/info/1021/1191.htm",
        match_reason="Official profile lists the paper in the teacher's publication section.",
        verified_by="pipeline_v3",
        evidence=[
            build_evidence(
                source_type="official_site",
                source_url="https://fe.szu.edu.cn/info/1021/1191.htm",
                fetched_at=TIMESTAMP,
                confidence=0.9,
            )
        ],
        last_updated=TIMESTAMP,
        quality_status="ready",
    )


def _service(tmp_path) -> DataSearchService:
    sql_store = SqliteReleasedObjectStore(tmp_path / "service.sqlite3")
    vector_store = MilvusVectorStore(
        uri=str(tmp_path / "service_vectors.db"),
        collection_name="service_vectors",
    )
    sql_store.upsert_released_objects(
        [
            _professor_record().to_released_object(),
            _paper_record().to_released_object(),
            _professor_paper_link_record().to_released_object(),
        ]
    )
    vector_store.upsert_released_objects(
        [_professor_record().to_released_object(), _paper_record().to_released_object()]
    )
    return DataSearchService(sql_store=sql_store, vector_store=vector_store)


def test_search_service_routes_single_domain_queries_and_related_objects(tmp_path):
    service = _service(tmp_path)

    professor_results = service.search(
        "介绍深圳大学的靳玉乐教授",
        filters={"institution": "深圳大学"},
        limit=5,
    )
    assert professor_results.query_type == "A"
    assert [item.id for item in professor_results.results] == ["PROF-1"]

    related_papers = service.get_related_objects(
        source_domain="professor",
        source_id="PROF-1",
        target_domain="paper",
        relation_type="professor_papers",
        limit=10,
    )
    assert [item.id for item in related_papers] == ["PAPER-1"]


def test_search_service_routes_cross_domain_professor_and_paper_queries(tmp_path):
    service = _service(tmp_path)

    response = service.search("深圳做课程思政的教授和论文有哪些", limit=5)

    assert response.query_type == "D"
    assert {item.object_type for item in response.results} == {"professor", "paper"}


def test_search_service_prefers_exact_sql_hits_over_semantic_noise_in_hybrid_mode(
    tmp_path,
):
    sql_store = SqliteReleasedObjectStore(tmp_path / "company.sqlite3")
    target = CompanyRecord(
        id="COMP-TARGET",
        name="极智视觉科技（深圳）有限公司",
        normalized_name="极智视觉科技（深圳）",
        industry="VR/AR",
        profile_summary="极智视觉科技聚焦VR/AR。",
        evaluation_summary="已形成企业画像。",
        technology_route_summary="围绕AI影像与VR/AR。",
        evidence=[
            build_evidence(
                source_type="xlsx_import",
                source_file="/home/longxiang/MiroThinker/docs/专辑项目导出1768807339.xlsx",
                fetched_at=TIMESTAMP,
                confidence=1.0,
            )
        ],
        last_updated=TIMESTAMP,
    ).to_released_object()
    noisy = CompanyRecord(
        id="COMP-NOISY",
        name="未来视觉智能科技有限公司",
        normalized_name="未来视觉智能科技",
        industry="机器人",
        profile_summary="未来视觉智能科技聚焦机器人。",
        evaluation_summary="已形成企业画像。",
        technology_route_summary="围绕机器人视觉。",
        evidence=[
            build_evidence(
                source_type="xlsx_import",
                source_file="/home/longxiang/MiroThinker/docs/专辑项目导出1768807339.xlsx",
                fetched_at=TIMESTAMP,
                confidence=1.0,
            )
        ],
        last_updated=TIMESTAMP,
    ).to_released_object()
    sql_store.upsert_released_objects([target, noisy])

    class FakeVectorStore:
        def search_domain(self, domain: str, query: str, limit: int = 10) -> list[str]:
            assert domain == "company"
            assert query == "公司 极智视觉科技（深圳）有限公司"
            assert limit == 10
            return ["COMP-NOISY"]

    service = DataSearchService(sql_store=sql_store, vector_store=FakeVectorStore())

    response = service.search("公司 极智视觉科技（深圳）有限公司", limit=10)

    assert [item.id for item in response.results][:2] == ["COMP-TARGET", "COMP-NOISY"]
