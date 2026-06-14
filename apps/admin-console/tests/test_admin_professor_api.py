from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from backend.deps import get_pg_conn
from backend.main import app
from .conftest import _load_postgres_dependencies

NOW = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
SCHEMA_PROFESSOR_ID = "PROF-ADMIN-SCHEMA"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _AdminProfessorConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.quality_status = "low_confidence"
        self.persisted_research_overview: str | None = None

    def execute(self, query: str, params: Any = None) -> _Result:
        sql = " ".join(query.split())
        sql_lower = sql.lower()
        self.calls.append((sql, params))

        if "with issue_summary" in sql_lower and "from professor p" in sql_lower:
            return _Result(
                [
                    {
                        "professor_id": "PROF-ADMIN-1",
                        "display_name": "Ada Lovelace",
                        "institution": "Test University",
                        "department": "Computer Science",
                        "quality_status": "needs_review",
                        "lifecycle_state": "active",
                        "open_issue_count": 2,
                        "latest_admin_action": "send_to_review",
                        "has_official_source": True,
                        "reason_rule_ids": ["missing_research_topic"],
                        "total_count": 1,
                    }
                ]
            )
        if "select p.professor_id" in sql_lower and "from professor p" in sql_lower:
            return _Result(
                [
                    {
                        "professor_id": "PROF-ADMIN-1",
                        "canonical_name": "Ada Lovelace",
                        "canonical_name_en": "Ada Lovelace",
                        "institution": "Test University",
                        "department": "Computer Science",
                        "title": "Professor",
                        "email": "ada@example.edu",
                        "profile_raw_text": (
                            "个人简介 教学 研究领域 研究成果 奖励荣誉 概况 "
                            "教育经历 Ada University, Computing, PhD. "
                            "工作经历 Test University, Professor. 研究领域 "
                            "My research focuses on developing trustworthy artificial intelligence "
                            "for medical image analysis. 主要项目 Project A."
                        ),
                        "profile_summary": "Works on analytical engines.",
                        "paper_summary": "Published computing papers.",
                        "patent_summary": "Inventive computing devices.",
                        "quality_status": self.quality_status,
                        "identity_status": "resolved",
                        "lifecycle_state": "active",
                        "lifecycle_merged_into_id": None,
                        "updated_at": NOW,
                    }
                ]
            )
        if "from professor_profile_section" in sql_lower:
            if self.persisted_research_overview is None:
                return _Result([])
            return _Result(
                [
                    {
                        "content": self.persisted_research_overview,
                        "source_page_url": "https://example.edu/ada",
                        "generation_method": "llm_translation",
                        "source_language": "en",
                    }
                ]
            )
        if "from professor_affiliation" in sql_lower:
            return _Result(
                [
                    {
                        "institution": "Test University",
                        "department": "Computer Science",
                        "title": "Professor",
                        "is_primary": True,
                        "is_current": True,
                        "source_page_url": "https://example.edu/ada",
                    }
                ]
            )
        if "from professor_fact" in sql_lower:
            return _Result(
                [
                    {
                        "fact_type": "research_topic",
                        "value_raw": "Computing",
                        "confidence": "0.9",
                        "source_page_url": "https://example.edu/ada",
                    }
                ]
            )
        if "from professor_paper_link" in sql_lower:
            row = {"paper_id": "PAPER-1", "title_clean": "Notes", "year": 2026}
            if "quality_status" in sql_lower and "canonical_source" in sql_lower:
                row.update(
                    {
                        "quality_status": "ready",
                        "canonical_source": "crossref",
                        "doi": "10.1000/notes",
                        "arxiv_id": "2409.05701",
                        "pdf_url": "https://arxiv.org/pdf/2409.05701",
                        "external_url": "https://doi.org/10.1000/notes",
                        "source_page_url": "https://example.edu/ada",
                    }
                )
            return _Result([row])
        if "from professor_patent_link" in sql_lower:
            return _Result([{"patent_id": "PAT-1", "title_clean": "Engine", "patent_number": None}])
        if "from source_page" in sql_lower:
            return _Result(
                [
                    {
                        "url": "https://example.edu/ada",
                        "page_role": "official_profile",
                        "is_official_source": True,
                        "fetched_at": NOW,
                    }
                ]
            )
        if "from pipeline_issue" in sql_lower and "select issue_id" in sql_lower:
            return _Result(
                [
                    {
                        "issue_id": "ISSUE-1",
                        "stage": "research_directions",
                        "severity": "medium",
                        "description": "professor quality gate: missing_research_topic",
                        "evidence_snapshot": {"rule_id": "missing_research_topic"},
                        "reported_by": "professor_quality_gate",
                        "reported_at": NOW,
                    }
                ]
            )
        if "from professor_admin_action" in sql_lower and "select action" in sql_lower:
            return _Result(
                [
                    {
                        "action": "send_to_review",
                        "actor": "admin-console",
                        "note": "Needs review",
                        "observed_data_updated_at": NOW,
                        "created_at": NOW,
                    }
                ]
            )
        if "select greatest" in sql_lower:
            return _Result([{"observed_data_updated_at": NOW}])
        if sql_lower.startswith("update professor"):
            self.quality_status = params["quality_status"]
            return _Result([])
        if sql_lower.startswith("insert into professor_admin_action"):
            return _Result([])
        if sql_lower.startswith("insert into pipeline_issue"):
            return _Result([])
        raise AssertionError(f"Unhandled SQL: {sql}")

    def commit(self) -> None:
        self.calls.append(("COMMIT", None))

    def rollback(self) -> None:
        self.calls.append(("ROLLBACK", None))


def _client(conn: _AdminProfessorConn) -> TestClient:
    app.dependency_overrides[get_pg_conn] = lambda: conn
    return TestClient(app)


def test_admin_professor_list_filters_by_quality_and_reason_rule() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.get(
        "/api/admin/professor",
        params={
            "quality_status": "needs_review",
            "reason_rule_id": "missing_research_topic",
            "sort_by": "open_issue_count",
            "sort_order": "desc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["professor_id"] == "PROF-ADMIN-1"
    assert payload["items"][0]["reason_rule_ids"] == ["missing_research_topic"]
    assert payload["items"][0]["open_issue_count"] == 2
    assert conn.calls[0][1]["quality_status"] == "needs_review"
    assert conn.calls[0][1]["reason_rule_id"] == "missing_research_topic"
    assert "ORDER BY open_issue_count DESC" in conn.calls[0][0]


def test_admin_professor_detail_returns_seven_sections() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.get("/api/admin/professor/PROF-ADMIN-1")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["sections"]) == {
        "identity",
        "contact",
        "research_output",
        "experience",
        "cleaned_summary",
        "sources_evidence",
        "quality_diagnosis",
    }
    assert payload["sections"]["quality_diagnosis"]["status"] == "low_confidence"
    assert payload["sections"]["quality_diagnosis"]["reasons"][0]["rule_id"] == (
        "missing_research_topic"
    )


def test_admin_professor_detail_extracts_research_overview_from_raw_profile() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.get("/api/admin/professor/PROF-ADMIN-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"]["research_output"]["research_overview"] == (
        "My research focuses on developing trustworthy artificial intelligence "
        "for medical image analysis."
    )


def test_admin_professor_detail_prefers_persisted_chinese_research_overview() -> None:
    conn = _AdminProfessorConn()
    conn.persisted_research_overview = (
        "我的研究聚焦可信人工智能在医学影像分析中的应用，尤其关注脑疾病诊断与预后。"
    )
    client = _client(conn)

    response = client.get("/api/admin/professor/PROF-ADMIN-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"]["research_output"]["research_overview"] == (
        "我的研究聚焦可信人工智能在医学影像分析中的应用，尤其关注脑疾病诊断与预后。"
    )


def test_admin_professor_detail_returns_canonical_paper_link_fields() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.get("/api/admin/professor/PROF-ADMIN-1")

    assert response.status_code == 200
    paper = response.json()["sections"]["research_output"]["papers"][0]
    assert paper == {
        "paper_id": "PAPER-1",
        "title_clean": "Notes",
        "year": 2026,
        "quality_status": "ready",
        "canonical_source": "crossref",
        "doi": "10.1000/notes",
        "arxiv_id": "2409.05701",
        "pdf_url": "https://arxiv.org/pdf/2409.05701",
        "external_url": "https://doi.org/10.1000/notes",
        "source_page_url": "https://example.edu/ada",
    }
    paper_sql = next(
        sql for sql, _ in conn.calls if "FROM professor_paper_link" in sql
    )
    assert "paper_merge_alias" in paper_sql
    assert "canonical_source" in paper_sql


def test_admin_professor_mark_confirm_ready_updates_status_and_audits() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.post(
        "/api/admin/professor/PROF-ADMIN-1/mark",
        json={
            "action": "confirm_ready",
            "actor": "ops",
            "note": "Reviewed source evidence.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "ready"
    assert any(sql.startswith("UPDATE professor") for sql, _ in conn.calls)
    assert any(sql.startswith("INSERT INTO professor_admin_action") for sql, _ in conn.calls)
    assert any(
        "reported_by IS DISTINCT FROM 'professor_quality_gate'" in sql
        for sql, _ in conn.calls
    )


def test_admin_professor_mark_send_to_review_updates_status_and_audits() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.post(
        "/api/admin/professor/PROF-ADMIN-1/mark",
        json={"action": "send_to_review", "actor": "ops"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "needs_review"
    assert any(sql.startswith("UPDATE professor") for sql, _ in conn.calls)
    assert any(sql.startswith("INSERT INTO professor_admin_action") for sql, _ in conn.calls)


def test_admin_professor_mark_flag_recrawl_keeps_status_and_files_issue() -> None:
    conn = _AdminProfessorConn()
    client = _client(conn)

    response = client.post(
        "/api/admin/professor/PROF-ADMIN-1/mark",
        json={"action": "flag_recrawl", "actor": "ops"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "low_confidence"
    assert not any(sql.startswith("UPDATE professor") for sql, _ in conn.calls)
    assert any(sql.startswith("INSERT INTO professor_admin_action") for sql, _ in conn.calls)
    assert any(sql.startswith("INSERT INTO pipeline_issue") for sql, _ in conn.calls)


def _seed_admin_professor_schema_fixture(pg_dsn: str) -> None:
    psycopg, Jsonb, _, _ = _load_postgres_dependencies()
    page_id = "33333333-3333-3333-3333-333333333333"
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            "DELETE FROM professor_admin_action WHERE professor_id = %s",
            (SCHEMA_PROFESSOR_ID,),
        )
        conn.execute(
            "DELETE FROM pipeline_issue WHERE professor_id = %s",
            (SCHEMA_PROFESSOR_ID,),
        )
        conn.execute(
            "DELETE FROM professor_fact WHERE professor_id = %s",
            (SCHEMA_PROFESSOR_ID,),
        )
        conn.execute(
            "DELETE FROM professor_affiliation WHERE professor_id = %s",
            (SCHEMA_PROFESSOR_ID,),
        )
        conn.execute(
            "DELETE FROM professor WHERE professor_id = %s",
            (SCHEMA_PROFESSOR_ID,),
        )
        conn.execute("DELETE FROM source_page WHERE page_id = %s", (page_id,))
        conn.execute(
            """
            INSERT INTO source_page (
                page_id,
                url,
                page_role,
                owner_scope_kind,
                owner_scope_ref,
                fetched_at,
                http_status,
                title,
                is_official_source
            )
            VALUES (%s, %s, 'official_profile', 'professor', %s, %s, 200, %s, true)
            """,
            (
                page_id,
                "https://example.edu/admin-workbench-schema",
                SCHEMA_PROFESSOR_ID,
                NOW,
                "Admin Workbench Schema Fixture",
            ),
        )
        conn.execute(
            """
            INSERT INTO professor (
                professor_id,
                canonical_name,
                canonical_name_en,
                aliases,
                discipline_family,
                primary_official_profile_page_id,
                identity_status,
                first_seen_at,
                last_refreshed_at,
                profile_summary,
                paper_summary,
                patent_summary,
                quality_status,
                lifecycle_state
            )
            VALUES (%s, %s, %s, %s, 'computer_science', %s, 'needs_review',
                    %s, %s, %s, %s, %s, 'low_confidence', 'active')
            """,
            (
                SCHEMA_PROFESSOR_ID,
                "Schema Ada",
                "Schema Ada",
                [],
                page_id,
                NOW,
                NOW,
                "Schema-backed professor profile.",
                "Schema-backed papers.",
                "Schema-backed patents.",
            ),
        )
        conn.execute(
            """
            INSERT INTO professor_affiliation (
                professor_id,
                institution,
                department,
                title,
                is_primary,
                is_current,
                source_page_id
            )
            VALUES (%s, 'Schema University', 'Computer Science', 'Professor',
                    true, true, %s)
            """,
            (SCHEMA_PROFESSOR_ID, page_id),
        )
        conn.execute(
            """
            INSERT INTO professor_fact (
                professor_id,
                fact_type,
                value_raw,
                value_normalized,
                source_page_id,
                evidence_span,
                confidence,
                status
            )
            VALUES
                (%s, 'contact', 'schema-ada@example.edu', 'schema-ada@example.edu',
                 %s, 'schema-ada@example.edu', 0.9, 'active'),
                (%s, 'research_topic', 'Schema-safe retrieval', 'Schema-safe retrieval',
                 %s, 'Schema-safe retrieval', 0.9, 'active')
            """,
            (SCHEMA_PROFESSOR_ID, page_id, SCHEMA_PROFESSOR_ID, page_id),
        )
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by,
                reported_at,
                resolved
            )
            VALUES (%s, 'research_directions', 'medium', %s, %s,
                    'professor_quality_gate', %s, false)
            """,
            (
                SCHEMA_PROFESSOR_ID,
                "professor quality gate: missing_research_topic",
                Jsonb({"rule_id": "missing_research_topic"}),
                NOW,
            ),
        )
        conn.commit()


def test_admin_professor_detail_and_mark_use_migrated_schema(
    postgres_client: TestClient,
    postgres_data_ready: str,
) -> None:
    _seed_admin_professor_schema_fixture(postgres_data_ready)

    detail_response = postgres_client.get(
        f"/api/admin/professor/{SCHEMA_PROFESSOR_ID}"
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["sections"]["identity"]["canonical_name"] == "Schema Ada"
    assert detail_payload["sections"]["contact"]["email"] == "schema-ada@example.edu"

    mark_response = postgres_client.post(
        f"/api/admin/professor/{SCHEMA_PROFESSOR_ID}/mark",
        json={
            "action": "confirm_ready",
            "actor": "browser-e2e",
            "note": "Schema-backed mark.",
        },
    )

    assert mark_response.status_code == 200
    assert mark_response.json()["quality_status"] == "ready"

    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(postgres_data_ready) as conn:
        action_row = conn.execute(
            """
            SELECT action, actor, note
              FROM professor_admin_action
             WHERE professor_id = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (SCHEMA_PROFESSOR_ID,),
        ).fetchone()
    assert action_row is not None
    assert action_row[0] == "confirm_ready"
    assert action_row[1] == "browser-e2e"

    generic_response = postgres_client.patch(
        f"/api/professor/{SCHEMA_PROFESSOR_ID}",
        json={"quality_status": "needs_review"},
    )
    assert generic_response.status_code == 409
    assert generic_response.json()["detail"]["error"] == (
        "professor_quality_requires_mark_endpoint"
    )
