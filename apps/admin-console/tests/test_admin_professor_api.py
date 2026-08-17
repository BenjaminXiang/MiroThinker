from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app

from .conftest import (
    _alembic_config,
    _clear_pg_pool_cache,
    _load_alembic,
    _load_postgres_dependencies,
    _psycopg_dsn,
    _raw_database_url,
)


@dataclass(frozen=True)
class ProfessorApiFixture:
    ready_id: str
    review_id: str
    enrichment_id: str


@pytest.fixture(scope="session")
def schema_ready() -> Iterator[str]:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    pg_dsn = _psycopg_dsn(_raw_database_url())
    alembic_command.upgrade(config, "head")
    try:
        yield pg_dsn
    finally:
        _clear_pg_pool_cache()
        alembic_command.downgrade(config, "base")


@pytest.fixture()
def admin_client(schema_ready: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL_TEST", schema_ready)
    _clear_pg_pool_cache()
    with TestClient(app) as client:
        yield client
    _clear_pg_pool_cache()


@pytest.fixture()
def professor_api_fixture(schema_ready: str) -> Iterator[ProfessorApiFixture]:
    psycopg, Jsonb, _, _ = _load_postgres_dependencies()
    marker = uuid.uuid4().hex[:8]
    ready_id = f"PROF-ADMIN-READY-{marker}"
    review_id = f"PROF-ADMIN-REVIEW-{marker}"
    enrichment_id = f"PROF-ADMIN-ENRICH-{marker}"
    page_ids: list[str] = []
    with psycopg.connect(schema_ready) as conn:
        for professor_id in (ready_id, review_id, enrichment_id):
            page_id = conn.execute(
                """
                INSERT INTO source_page (
                    url,
                    page_role,
                    owner_scope_kind,
                    owner_scope_ref,
                    fetched_at,
                    is_official_source,
                    title
                )
                VALUES (%s, 'official_profile', 'professor', %s, now(), true, %s)
                RETURNING page_id
                """,
                (
                    f"https://example.test/{professor_id}",
                    professor_id,
                    f"{professor_id} profile",
                ),
            ).fetchone()[0]
            page_ids.append(str(page_id))

        rows = [
            (
                ready_id,
                "Ready Professor",
                "ready",
                page_ids[0],
                "Ready profile summary",
            ),
            (
                review_id,
                "Review Professor",
                "needs_review",
                page_ids[1],
                "Review profile summary",
            ),
            (
                enrichment_id,
                "Enrichment Professor",
                "needs_enrichment",
                None,
                None,
            ),
        ]
        for professor_id, name, status, page_id, summary in rows:
            conn.execute(
                """
                INSERT INTO professor (
                    professor_id,
                    canonical_name,
                    canonical_name_en,
                    canonical_name_zh,
                    aliases,
                    discipline_family,
                    primary_official_profile_page_id,
                    identity_status,
                    quality_status,
                    profile_summary,
                    h_index,
                    citation_count,
                    paper_count
                )
                VALUES (%s, %s, %s, %s, %s, 'computer_science',
                        %s, 'resolved', %s, %s, 7, 120, 4)
                """,
                (
                    professor_id,
                    name,
                    name,
                    name,
                    [],
                    page_id,
                    status,
                    summary,
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
                VALUES (%s, '南方科技大学', '计算机科学与工程系',
                        '教授', true, true, %s)
                """,
                (professor_id, page_ids[0]),
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
                confidence
            )
            VALUES
                (%s, 'research_topic', '机器学习', 'machine learning',
                 %s, '研究机器学习', 0.95),
                (%s, 'education', 'PhD, Example University',
                 'phd example university', %s, 'PhD, Example University', 0.92),
                (%s, 'contact', 'ready@example.test', 'ready@example.test',
                 %s, 'ready@example.test', 0.99)
            """,
            (ready_id, page_ids[0], ready_id, page_ids[0], ready_id, page_ids[0]),
        )
        for stage, description, reporter, rule_id in (
            (
                "identity_gate",
                "[professor_quality_gate:identity_unresolved] identity is not resolved",
                "professor_quality_gate",
                "identity_unresolved",
            ),
            (
                "coverage",
                "[adapter:official_profile_fetch_failed] official profile fetch failed",
                "adapter",
                "official_profile_fetch_failed",
            ),
        ):
            conn.execute(
                """
                INSERT INTO pipeline_issue (
                    professor_id,
                    stage,
                    severity,
                    description,
                    evidence_snapshot,
                    reported_by
                )
                VALUES (%s, %s, 'high', %s, %s, %s)
                """,
                (
                    review_id,
                    stage,
                    description,
                    Jsonb({"rule_id": rule_id}),
                    reporter,
                ),
            )
        conn.execute(
            """
            INSERT INTO professor_admin_action (
                professor_id,
                action,
                actor,
                observed_data_updated_at
            )
            VALUES (%s, 'flag_recrawl', 'fixture', now())
            """,
            (enrichment_id,),
        )
        conn.commit()

    try:
        yield ProfessorApiFixture(
            ready_id=ready_id,
            review_id=review_id,
            enrichment_id=enrichment_id,
        )
    finally:
        with psycopg.connect(schema_ready) as conn:
            professor_ids = [ready_id, review_id, enrichment_id]
            professor_placeholders = ", ".join(["%s"] * len(professor_ids))
            conn.execute(
                "DELETE FROM pipeline_issue WHERE professor_id IN "
                f"({professor_placeholders})",
                tuple(professor_ids),
            )
            conn.execute(
                "DELETE FROM professor_admin_action WHERE professor_id IN "
                f"({professor_placeholders})",
                tuple(professor_ids),
            )
            for table, column, values in (
                ("professor", "professor_id", professor_ids),
                ("source_page", "page_id", page_ids),
            ):
                if values:
                    placeholders = ", ".join(["%s"] * len(values))
                    conn.execute(
                        f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
                        tuple(values),
                    )
            conn.commit()


def test_admin_professor_list_filters_and_sorts(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.get(
        "/api/admin/professor",
        params={"quality_status": "needs_review"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert {item["quality_status"] for item in payload["items"]} == {"needs_review"}
    review_item = next(
        item
        for item in payload["items"]
        if item["professor_id"] == professor_api_fixture.review_id
    )
    assert review_item["open_issue_count"] == 2
    assert "identity_unresolved" in review_item["reason_rule_ids"]

    reason_response = admin_client.get(
        "/api/admin/professor",
        params={"reason_rule_id": "identity_unresolved"},
    )
    assert reason_response.status_code == 200
    assert reason_response.json()["items"][0]["professor_id"] == (
        professor_api_fixture.review_id
    )

    sorted_response = admin_client.get(
        "/api/admin/professor",
        params={"sort_by": "open_issue_count", "sort_order": "desc"},
    )
    assert sorted_response.status_code == 200
    assert sorted_response.json()["items"][0]["professor_id"] == (
        professor_api_fixture.review_id
    )


def test_admin_professor_detail_returns_seven_sections(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.get(
        f"/api/admin/professor/{professor_api_fixture.ready_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "identity",
        "contact",
        "research_and_output",
        "experience",
        "cleaned_summary",
        "sources_and_evidence",
        "quality_diagnosis",
    }
    assert payload["identity"]["professor_id"] == professor_api_fixture.ready_id
    assert payload["experience"]["status"] == "populated"
    assert payload["experience"]["facts"]["education"][0]["value_raw"].startswith("PhD")
    assert payload["quality_diagnosis"]["status"] == "ready"
    assert payload["sources_and_evidence"]["provenance"]


def test_admin_professor_detail_returns_not_extracted_experience(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.get(
        f"/api/admin/professor/{professor_api_fixture.enrichment_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["experience"]["status"] == "not_extracted"
    assert payload["experience"]["facts"] == {}


def test_admin_professor_mark_confirm_ready(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.post(
        f"/api/admin/professor/{professor_api_fixture.enrichment_id}/mark",
        headers={"X-Admin-Actor": "alice@example.test"},
        json={"action": "confirm_ready", "note": "Looks complete enough"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "ready"
    assert payload["admin_action"]["action"] == "confirm_ready"
    assert payload["admin_action"]["actor"] == "alice@example.test"
    assert payload["admin_action"]["observed_data_updated_at"]


def test_admin_professor_mark_send_to_review(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.post(
        f"/api/admin/professor/{professor_api_fixture.ready_id}/mark",
        json={"action": "send_to_review"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "needs_review"
    assert payload["admin_action"]["actor"] == "admin-console"


def test_admin_professor_mark_flag_recrawl_keeps_status(
    admin_client: TestClient,
    professor_api_fixture: ProfessorApiFixture,
) -> None:
    response = admin_client.post(
        f"/api/admin/professor/{professor_api_fixture.enrichment_id}/mark",
        json={"action": "flag_recrawl", "note": "Fetch again"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "needs_enrichment"
    assert payload["pipeline_issue"]["stage"] == "data_quality_flag"
    assert payload["pipeline_issue"]["reported_by"] == "admin:flag_recrawl"
