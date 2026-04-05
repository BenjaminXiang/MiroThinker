from __future__ import annotations

from datetime import datetime, timezone

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.evidence import build_evidence
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
        profile_summary="靳玉乐现任深圳大学教育学部教授，研究方向包括课程思政与课程论。",
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


def test_sqlite_store_upserts_and_queries_released_objects(tmp_path):
    store = SqliteReleasedObjectStore(tmp_path / "released_objects.sqlite3")
    professor = _professor_record().to_released_object()

    store.upsert_released_objects([professor])

    assert store.get_object("professor", "PROF-1").display_name == "靳玉乐"
    results = store.search_domain(
        "professor",
        "靳玉乐",
        filters={"institution": "深圳大学"},
        mode="exact",
        limit=10,
    )
    assert [item.id for item in results] == ["PROF-1"]


def test_milvus_store_upserts_and_semantically_searches_released_objects(tmp_path):
    vector_store = MilvusVectorStore(
        uri=str(tmp_path / "released_vectors.db"),
        collection_name="released_objects",
    )
    professor = _professor_record().to_released_object()

    vector_store.upsert_released_objects([professor])

    ids = vector_store.search_domain(
        "professor",
        "课程思政 教授",
        limit=5,
    )
    assert ids[:1] == ["PROF-1"]
