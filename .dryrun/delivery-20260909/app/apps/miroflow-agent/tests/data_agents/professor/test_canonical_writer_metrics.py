from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.data_agents.canonical.professor import Professor
from src.data_agents.professor.canonical_writer import (
    _classify_homepage_source_page_role,
    _iter_owned_homepage_source_pages,
    _is_generic_contact_email,
    _retire_conflicting_contact_email_facts,
    _upsert_professor_row,
    upsert_professor_metrics,
)
from src.data_agents.professor.models import EnrichedProfessorProfile

_RUN_ID = "00000000-0000-0000-0000-000000000001"


def _conn_with_paper_count(count: int) -> MagicMock:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"n": count}
    conn.execute.return_value = cursor
    return conn


def _sql_at(conn: MagicMock, index: int) -> str:
    return " ".join(conn.execute.call_args_list[index].args[0].split())


def _params_at(conn: MagicMock, index: int) -> tuple[object, ...]:
    return conn.execute.call_args_list[index].args[1]


def test_generic_contact_email_detector_catches_footer_and_department_mailboxes() -> None:
    assert _is_generic_contact_email("yzb@uestc.edu.cn")
    assert _is_generic_contact_email("design@sztu.edu.cnfollowussztuwechatadmissionscopyright")
    assert not _is_generic_contact_email("xuanli@uestc.edu.cn")


def test_retire_conflicting_contact_email_facts_soft_inactivates_other_emails() -> None:
    conn = MagicMock()

    _retire_conflicting_contact_email_facts(
        conn,
        professor_id="PROF-LI-XUAN",
        source_page_id="PAGE-1",
        accepted_email="xuanli@uestc.edu.cn",
        run_id=_RUN_ID,
    )

    sql = _sql_at(conn, 0)
    assert "UPDATE professor_fact" in sql
    assert "status = 'superseded'" in sql
    params = _params_at(conn, 0)
    assert params[0] == _RUN_ID
    assert params[1] == "PROF-LI-XUAN"
    assert params[2] == "PAGE-1"
    assert params[3] == "xuanli@uestc.edu.cn"


def test_upsert_professor_metrics_writes_openalex_metrics() -> None:
    conn = _conn_with_paper_count(2)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-1",
        h_index=37,
        citation_count=5_000_000_000,
        metrics_source="openalex",
        run_id="00000000-0000-0000-0000-000000000001",
    )

    assert conn.execute.call_count == 2
    assert _params_at(conn, 1) == (
        37,
        5_000_000_000,
        2,
        "openalex",
        "00000000-0000-0000-0000-000000000001",
        "PROF-1",
    )


def test_upsert_professor_metrics_writes_verified_link_only_zero_count() -> None:
    conn = _conn_with_paper_count(0)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-2",
        h_index=None,
        citation_count=None,
        metrics_source="verified_link_only",
        run_id=_RUN_ID,
    )

    assert _params_at(conn, 1) == (
        None,
        None,
        0,
        "verified_link_only",
        _RUN_ID,
        "PROF-2",
    )


def test_upsert_professor_metrics_refreshes_verified_link_count_without_metrics_source() -> None:
    conn = _conn_with_paper_count(3)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-LINKED",
        h_index=None,
        citation_count=None,
        metrics_source=None,
        run_id=_RUN_ID,
    )

    assert conn.execute.call_count == 2
    assert _params_at(conn, 1) == (
        None,
        None,
        3,
        "verified_link_only",
        _RUN_ID,
        "PROF-LINKED",
    )


def test_upsert_professor_metrics_allows_mixed_source() -> None:
    conn = _conn_with_paper_count(4)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-3",
        h_index=12,
        citation_count=None,
        metrics_source="mixed",
        run_id="run-1",
    )

    assert _params_at(conn, 1) == (12, None, 4, "mixed", "run-1", "PROF-3")


def test_upsert_professor_metrics_without_verified_links_writes_zero_not_count_only_prose() -> None:
    conn = _conn_with_paper_count(0)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-4",
        h_index=None,
        citation_count=None,
        metrics_source=None,
        run_id="run-1",
    )

    assert conn.execute.call_count == 2
    assert _params_at(conn, 1) == (
        None,
        None,
        0,
        "verified_link_only",
        "run-1",
        "PROF-4",
    )


def test_upsert_professor_metrics_rejects_unknown_source() -> None:
    conn = MagicMock()

    with pytest.raises(ValueError, match="invalid metrics_source"):
        upsert_professor_metrics(
            conn,
            professor_id="PROF-5",
        h_index=None,
        citation_count=None,
        metrics_source="google_scholar",
        run_id=_RUN_ID,
        )

    conn.execute.assert_not_called()


def test_upsert_professor_metrics_requires_source_for_openalex_values() -> None:
    conn = MagicMock()

    with pytest.raises(ValueError, match="metrics_source is required"):
        upsert_professor_metrics(
            conn,
            professor_id="PROF-6",
        h_index=1,
        citation_count=None,
        metrics_source=None,
        run_id=_RUN_ID,
        )

    conn.execute.assert_not_called()


def test_upsert_professor_metrics_uses_verified_link_count_sql() -> None:
    conn = _conn_with_paper_count(9)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-7",
        h_index=1,
        citation_count=2,
        metrics_source="openalex",
        run_id=_RUN_ID,
    )

    assert _sql_at(conn, 0) == (
        "SELECT count(*)::int AS n FROM professor_paper_link "
        "WHERE professor_id = %s AND link_status = 'verified'"
    )
    assert _params_at(conn, 0) == ("PROF-7",)


def test_upsert_professor_metrics_skips_merged_professors() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-8",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=_RUN_ID,
    )

    update_sql = _sql_at(conn, 1)
    assert "identity_status <> 'merged_into'" in update_sql


def test_upsert_professor_metrics_computed_at_not_newer_than_refresh() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-9",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=_RUN_ID,
    )

    update_sql = _sql_at(conn, 1)
    assert "metrics_computed_at = LEAST(now(), COALESCE(last_refreshed_at, now()))" in update_sql


def test_upsert_professor_metrics_does_not_commit() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-10",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=_RUN_ID,
    )

    conn.commit.assert_not_called()


def test_upsert_professor_row_persists_paper_summary_from_profile_write_path() -> None:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"exists": 1}
    profile = EnrichedProfessorProfile(
        name="A Test",
        institution="南方科技大学",
        paper_summary="Verified official links cover graph learning and robotics.",
        profile_url="https://www.sustech.edu.cn/faculty/a.html",
        roster_source="https://www.sustech.edu.cn/faculty/",
        extraction_status="structured",
    )

    _upsert_professor_row(
        conn,
        professor_id="PROF-SUMMARY",
        enriched=profile,
        primary_page_id="11111111-1111-1111-1111-111111111111",
        run_id=_RUN_ID,
    )

    upsert_sql = _sql_at(conn, 1)
    assert "paper_summary" in upsert_sql
    assert "paper_summary = COALESCE(EXCLUDED.paper_summary, professor.paper_summary)" in upsert_sql
    assert "Verified official links cover graph learning and robotics." in _params_at(conn, 1)


def test_iter_owned_homepage_source_pages_uses_provenance_before_fallbacks() -> None:
    official_publication_url = "https://www.sustech.edu.cn/faculty/a/publications.html"
    lab_publication_url = "https://research.example.org/a/publications"
    profile = EnrichedProfessorProfile(
        name="A Test",
        institution="南方科技大学",
        publication_evidence_urls=[official_publication_url, lab_publication_url],
        field_provenance={
            f"source_page_role:{lab_publication_url}": "lab_homepage",
        },
        profile_url="https://www.sustech.edu.cn/faculty/a.html",
        roster_source="https://www.sustech.edu.cn/faculty/",
        extraction_status="structured",
    )

    assert _iter_owned_homepage_source_pages(profile) == [
        (lab_publication_url, "lab_homepage"),
        (official_publication_url, "official_publication_page"),
    ]


def test_iter_owned_homepage_source_pages_skips_external_academic_profiles() -> None:
    official_publication_url = "https://www.sustech.edu.cn/faculty/a/publications.html"
    profile = EnrichedProfessorProfile(
        name="A Test",
        institution="南方科技大学",
        publication_evidence_urls=[
            official_publication_url,
            "https://scholar.google.com/citations?user=test",
            "https://www.researchgate.net/profile/Test-Prof",
        ],
        field_provenance={
            "source_page_role:https://scholar.google.com/citations?user=test": (
                "personal_homepage"
            ),
            "source_page_role:https://www.researchgate.net/profile/Test-Prof": (
                "personal_homepage"
            ),
        },
        profile_url="https://www.sustech.edu.cn/faculty/a.html",
        roster_source="https://www.sustech.edu.cn/faculty/",
        extraction_status="structured",
    )

    assert _iter_owned_homepage_source_pages(profile) == [
        (official_publication_url, "official_publication_page")
    ]


@pytest.mark.parametrize(
    ("url", "expected_role"),
    [
        ("https://sds.cuhk.edu.cn/teacher/2238", "official_profile"),
        ("http://materials.sysu.edu.cn/teacher/162", "official_profile"),
        ("https://sites.google.com/view/mihabresar", "personal_homepage"),
        ("https://deepbitlab.example.org/people/alice", "lab_homepage"),
        ("https://scholar.google.com/citations?user=abc", "official_external_profile"),
        ("https://www.researchgate.net/profile/Beichen-Ding", "official_external_profile"),
        ("https://orcid.org/0000-0001-2345-6789", "official_external_profile"),
        ("https://dblp.org/pid/12/3456.html", "official_external_profile"),
        ("https://inspirehep.net/authors/1234567", "official_external_profile"),
        ("ResearchGate https://www.researchgate.net/profile/Beichen-Ding", None),
        ("https://scholar.google.com/citations?user=abc Google Scholar", None),
    ],
)
def test_classify_homepage_source_page_role_separates_official_personal_and_academic_profiles(
    url: str,
    expected_role: str | None,
) -> None:
    assert _classify_homepage_source_page_role(url) == expected_role


def test_professor_model_accepts_metrics_and_rejects_unknown_source() -> None:
    prof = Professor(
        professor_id="PROF-11",
        canonical_name="张三",
        discipline_family="computer_science",
        h_index=0,
        citation_count=0,
        paper_count=0,
        metrics_source="openalex",
    )

    assert prof.h_index == 0
    assert prof.citation_count == 0
    assert prof.paper_count == 0

    with pytest.raises(ValidationError):
        Professor(
            professor_id="PROF-12",
            canonical_name="李四",
            discipline_family="computer_science",
            metrics_source="google_scholar",
        )
