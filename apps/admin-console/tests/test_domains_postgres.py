from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from fastapi import HTTPException

from backend.api.data import _list_professors
from backend.api.domains import (
    DomainEnum,
    UpdateRecordRequest,
    delete_domain_object,
    get_domain_object,
    get_filter_options,
    get_related_objects,
    list_domain,
    update_domain_object,
)

NOW = datetime(2026, 4, 30, tzinfo=timezone.utc)
RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
RELEASED_KEYS = {
    "id",
    "object_type",
    "display_name",
    "core_facts",
    "summary_fields",
    "evidence",
    "last_updated",
    "quality_status",
}


def _base_records() -> dict[str, dict[str, Any]]:
    return {
        "professor": {
            "professor_id": "PROF-TEST",
            "canonical_name": "Ada Lovelace",
            "canonical_name_en": "Ada Lovelace",
            "canonical_name_zh": None,
            "aliases": [],
            "discipline_family": "computer_science",
            "identity_status": "resolved",
            "merged_into_id": None,
            "profile_summary": "Analytical engine researcher.",
            "h_index": 12,
            "citation_count": 1200,
            "paper_count": 8,
            "metrics_computed_at": NOW,
            "metrics_source": "openalex",
            "last_refreshed_at": NOW,
            "updated_at": NOW,
            "run_id": RUN_ID,
            "primary_affiliation_institution": "Test University",
            "primary_affiliation_department": "Computing",
            "primary_affiliation_title": "Professor",
            "institution": "Test University",
            "title": "Professor",
            "research_topic_count": 3,
            "primary_profile_url": "https://example.test/prof",
            "primary_profile_fetched_at": NOW,
            "total_count": 1,
        },
        "company": {
            "company_id": "COMP-TEST",
            "unified_credit_code": "91440300TEST",
            "canonical_name": "Analytical Engines Ltd",
            "registered_name": "Analytical Engines Ltd",
            "aliases": [],
            "website": "https://example.test/company",
            "hq_province": "Guangdong",
            "hq_city": "Shenzhen",
            "hq_district": "Nanshan",
            "is_shenzhen": True,
            "country": "China",
            "identity_status": "resolved",
            "merged_into_id": None,
            "last_refreshed_at": NOW,
            "created_at": NOW,
            "updated_at": NOW,
            "project_name": "Analytical Engine",
            "industry": "AI",
            "sub_industry": "Systems",
            "business": "Computing platforms",
            "region": "Shenzhen",
            "description": "Builds computing platforms.",
            "logo_url": None,
            "star_rating": 5,
            "status_raw": None,
            "remarks": "Reviewed.",
            "is_high_tech": True,
            "company_name_xlsx": "Analytical Engines Ltd",
            "established_date": None,
            "years_established": 4,
            "website_xlsx": None,
            "registered_address": "Shenzhen",
            "registered_capital": None,
            "reported_patent_count": 2,
            "reported_news_count": 1,
            "reported_funding_round_count": 1,
            "reported_total_funding_raw": None,
            "reported_valuation_raw": None,
            "latest_funding_round": "Seed",
            "latest_funding_time": None,
            "latest_funding_amount_raw": None,
            "latest_funding_cny_wan": None,
            "latest_investors_raw": None,
            "team_raw": None,
            "snapshot_created_at": NOW,
            "total_count": 1,
        },
        "paper": {
            "paper_id": "PAPER-TEST",
            "title_clean": "Notes on the Analytical Engine",
            "title_raw": "Notes on the Analytical Engine",
            "doi": "10.0000/test",
            "arxiv_id": None,
            "openalex_id": None,
            "semantic_scholar_id": None,
            "year": 2026,
            "venue": "TestConf",
            "abstract_clean": "A test paper.",
            "authors_display": "Ada Lovelace",
            "authors_raw": None,
            "citation_count": 10,
            "canonical_source": "manual",
            "first_seen_at": NOW,
            "updated_at": NOW,
            "run_id": RUN_ID,
            "admin_action": None,
            "linked_professor_count": 1,
            "verified_professor_count": 1,
            "total_count": 1,
        },
        "patent": {
            "patent_id": "PAT-TEST",
            "patent_number": "CNTEST",
            "title_clean": "Analytical engine patent",
            "title_raw": "Analytical engine patent",
            "title_en": "Analytical engine patent",
            "applicants_raw": "Analytical Engines Ltd",
            "applicants_parsed": None,
            "inventors_raw": "Ada Lovelace",
            "inventors_parsed": None,
            "filing_date": None,
            "publication_date": None,
            "grant_date": None,
            "patent_type": "invention",
            "status": None,
            "abstract_clean": "A test patent.",
            "technology_effect": "Faster computing.",
            "ipc_codes": ["G06F"],
            "first_seen_at": NOW,
            "updated_at": NOW,
            "run_id": RUN_ID,
            "total_count": 1,
        },
    }


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakePostgresConn:
    def __init__(self) -> None:
        self.records = _base_records()
        self.calls: list[tuple[str, Any]] = []
        self.run_scopes: list[dict[str, Any]] = []

    def execute(
        self,
        query: str,
        params: dict[str, Any] | tuple[Any, ...] | None = None,
    ) -> _FakeResult:
        sql = " ".join(query.split())
        sql_lower = sql.lower()
        self.calls.append((sql, params))

        if sql_lower.startswith("insert into pipeline_run"):
            scope = json.loads(params[1]) if isinstance(params, tuple) else {}
            self.run_scopes.append(scope)
            return _FakeResult([{"run_id": RUN_ID}])
        if sql_lower.startswith("update pipeline_run"):
            return _FakeResult([])
        if sql_lower.startswith("update professor_affiliation"):
            self._update_professor_affiliation(params)
            return _FakeResult([])
        if sql_lower.startswith("update professor"):
            self._update_professor(sql_lower, params)
            return _FakeResult([])
        if sql_lower.startswith("update company_snapshot"):
            self._update_company_snapshot(params)
            return _FakeResult([])
        if sql_lower.startswith("update company"):
            self._update_company(sql_lower, params)
            return _FakeResult([])
        if sql_lower.startswith("update paper"):
            self._update_paper(params)
            return _FakeResult([])
        if sql_lower.startswith("update patent"):
            self._update_patent(sql_lower, params)
            return _FakeResult([])
        if "select distinct" in sql_lower and " as value" in sql_lower:
            return _FakeResult([{"value": self._filter_option_value(sql_lower)}])

        domain = self._domain_from_sql(sql_lower)
        if domain is None:
            raise AssertionError(f"Unexpected SQL in fake connection: {sql}")
        return _FakeResult(self._select_domain_rows(domain, sql_lower, params))

    def _domain_from_sql(self, sql_lower: str) -> str | None:
        if " from professor p" in sql_lower:
            return "professor"
        if " from company c" in sql_lower:
            return "company"
        if " from paper p" in sql_lower:
            return "paper"
        if " from patent" in sql_lower:
            return "patent"
        return None

    def _select_domain_rows(
        self,
        domain: str,
        sql_lower: str,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> list[dict[str, Any]]:
        record = copy.deepcopy(self.records[domain])
        params = params or {}
        is_relation_query = any(
            marker in sql_lower
            for marker in (
                "join professor_paper_link ppl on ppl.paper_id = p.paper_id",
                "join professor_paper_link ppl on ppl.professor_id = p.professor_id",
                "join professor_patent_link ppl on ppl.patent_id = patent.patent_id",
                "join professor_patent_link ppl on ppl.professor_id = p.professor_id",
                "join company_patent_link cpl on cpl.patent_id = patent.patent_id",
                "join company_patent_link cpl on cpl.company_id = c.company_id",
                "join professor_company_role pcr on pcr.company_id = c.company_id",
            )
        )
        object_id = params.get("object_id") if isinstance(params, dict) else None
        if object_id and not is_relation_query and object_id != record[f"{domain}_id"]:
            return []
        if not is_relation_query and not self._is_active(domain):
            return []
        record["total_count"] = 1
        return [record]

    def _is_active(self, domain: str) -> bool:
        if domain in {"professor", "company"}:
            return self.records[domain]["identity_status"] == "resolved"
        if domain == "paper":
            return self.records[domain].get("admin_action") != "delete"
        if domain == "patent":
            return self.records[domain].get("status") != "inactive"
        return True

    def _filter_option_value(self, sql_lower: str) -> str:
        if "institution" in sql_lower:
            return "Test University"
        if "industry" in sql_lower:
            return "AI"
        if "year" in sql_lower:
            return "2026"
        if "patent_type" in sql_lower:
            return "invention"
        return "ready"

    def _update_professor(
        self,
        sql_lower: str,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        assert isinstance(params, dict)
        row = self.records["professor"]
        if "identity_status = 'inactive'" in sql_lower:
            row["identity_status"] = "inactive"
        if "identity_status" in params:
            row["identity_status"] = params["identity_status"]
        if "core_name" in params:
            row["canonical_name"] = params["core_name"]
        row["run_id"] = params.get("run_id", row["run_id"])

    def _update_professor_affiliation(
        self,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        assert isinstance(params, dict)
        row = self.records["professor"]
        if "aff_institution" in params:
            row["primary_affiliation_institution"] = params["aff_institution"]
            row["institution"] = params["aff_institution"]
        if "aff_department" in params:
            row["primary_affiliation_department"] = params["aff_department"]
        if "aff_title" in params:
            row["primary_affiliation_title"] = params["aff_title"]
            row["title"] = params["aff_title"]

    def _update_company(
        self,
        sql_lower: str,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        assert isinstance(params, dict)
        row = self.records["company"]
        if "identity_status = 'inactive'" in sql_lower:
            row["identity_status"] = "inactive"
        if "identity_status" in params:
            row["identity_status"] = params["identity_status"]
        if "core_name" in params:
            row["canonical_name"] = params["core_name"]

    def _update_company_snapshot(
        self,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        assert isinstance(params, dict)
        row = self.records["company"]
        if "snap_industry" in params:
            row["industry"] = params["snap_industry"]
        if "summary_profile_summary" in params:
            row["description"] = params["summary_profile_summary"]

    def _update_paper(self, params: dict[str, Any] | tuple[Any, ...] | None) -> None:
        assert isinstance(params, dict)
        row = self.records["paper"]
        if self.run_scopes and self.run_scopes[-1]["action"] == "delete":
            row["admin_action"] = "delete"
        if "core_title" in params:
            row["title_clean"] = params["core_title"]
        row["run_id"] = params.get("run_id", row["run_id"])

    def _update_patent(
        self,
        sql_lower: str,
        params: dict[str, Any] | tuple[Any, ...] | None,
    ) -> None:
        assert isinstance(params, dict)
        row = self.records["patent"]
        if "status = 'inactive'" in sql_lower:
            row["status"] = "inactive"
        if "status" in params:
            row["status"] = params["status"]
        if "core_title" in params:
            row["title_clean"] = params["core_title"]
        row["run_id"] = params.get("run_id", row["run_id"])


@pytest.fixture()
def fake_pg_conn() -> _FakePostgresConn:
    return _FakePostgresConn()


@pytest.mark.parametrize(
    ("domain", "object_id"),
    [
        ("professor", "PROF-TEST"),
        ("company", "COMP-TEST"),
        ("paper", "PAPER-TEST"),
        ("patent", "PAT-TEST"),
    ],
)
def test_list_domain_returns_released_object_shape(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    object_id: str,
) -> None:
    response = list_domain(
        DomainEnum(domain),
        page=1,
        page_size=1,
        sort_by="display_name",
        sort_order="asc",
        conn=fake_pg_conn,
    )
    payload = response.model_dump(mode="json")
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == object_id
    assert set(payload["items"][0]) == RELEASED_KEYS


@pytest.mark.parametrize(
    ("domain", "object_id"),
    [
        ("professor", "PROF-TEST"),
        ("company", "COMP-TEST"),
        ("paper", "PAPER-TEST"),
        ("patent", "PAT-TEST"),
    ],
)
def test_get_domain_object_returns_released_object_shape(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    object_id: str,
) -> None:
    payload = get_domain_object(DomainEnum(domain), object_id, conn=fake_pg_conn)
    assert payload["id"] == object_id
    assert payload["object_type"] == domain
    assert set(payload) == RELEASED_KEYS


@pytest.mark.parametrize(
    ("domain", "field", "expected"),
    [
        ("professor", "institution", "Test University"),
        ("company", "industry", "AI"),
        ("paper", "year", "2026"),
        ("patent", "patent_type", "invention"),
    ],
)
def test_get_filter_options_uses_distinct_with_limit(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    field: str,
    expected: str,
) -> None:
    response = get_filter_options(DomainEnum(domain), field, conn=fake_pg_conn)
    assert response.model_dump(mode="json") == {"options": [expected]}
    assert "LIMIT 1000" in fake_pg_conn.calls[-1][0]


@pytest.mark.parametrize(
    ("domain", "object_id", "bucket", "expected_type"),
    [
        ("professor", "PROF-TEST", "papers", "paper"),
        ("company", "COMP-TEST", "patents", "patent"),
        ("paper", "PAPER-TEST", "papers", "professor"),
        ("patent", "PAT-TEST", "companies", "company"),
    ],
)
def test_get_related_objects_joins_canonical_relations(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    object_id: str,
    bucket: str,
    expected_type: str,
) -> None:
    response = get_related_objects(DomainEnum(domain), object_id, conn=fake_pg_conn)
    payload = response.model_dump(mode="json")
    assert payload[bucket]
    assert payload[bucket][0]["object_type"] == expected_type
    assert set(payload[bucket][0]) == RELEASED_KEYS


def test_professor_domains_total_matches_data_api_for_same_institution(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    filters = json.dumps({"institution": "Test University"})
    domain_response = list_domain(
        DomainEnum.professor,
        page=1,
        page_size=1,
        sort_by="display_name",
        sort_order="asc",
        filters=filters,
        conn=fake_pg_conn,
    )
    data_response = _list_professors(
        fake_pg_conn,
        q=None,
        institution="Test University",
        discipline_family=None,
        has_verified_papers=None,
        metrics_source=None,
        page=1,
        page_size=1,
    )

    assert domain_response.total == data_response.total


@pytest.mark.parametrize(
    ("domain", "object_id", "payload", "expected_display"),
    [
        ("professor", "PROF-TEST", {"core_facts": {"name": "Grace Hopper"}}, "Grace Hopper"),
        ("company", "COMP-TEST", {"core_facts": {"name": "Compiler Corp"}}, "Compiler Corp"),
        ("paper", "PAPER-TEST", {"core_facts": {"title": "Updated Paper"}}, "Updated Paper"),
        ("patent", "PAT-TEST", {"core_facts": {"title": "Updated Patent"}}, "Updated Patent"),
    ],
)
def test_patch_domain_object_updates_postgres_and_records_run(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    object_id: str,
    payload: dict[str, Any],
    expected_display: str,
) -> None:
    response = update_domain_object(
        DomainEnum(domain),
        object_id,
        conn=fake_pg_conn,
        body=UpdateRecordRequest.model_validate(payload),
    )
    assert response["display_name"] == expected_display
    assert fake_pg_conn.run_scopes[-1]["action"] == "patch"
    assert fake_pg_conn.run_scopes[-1]["domain"] == domain


@pytest.mark.parametrize(
    ("domain", "object_id"),
    [
        ("professor", "PROF-TEST"),
        ("company", "COMP-TEST"),
        ("paper", "PAPER-TEST"),
        ("patent", "PAT-TEST"),
    ],
)
def test_delete_domain_object_soft_deletes_and_records_run(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    object_id: str,
) -> None:
    response = delete_domain_object(DomainEnum(domain), object_id, conn=fake_pg_conn)
    assert response is None
    assert fake_pg_conn.run_scopes[-1]["action"] == "delete"
    assert fake_pg_conn.run_scopes[-1]["domain"] == domain

    with pytest.raises(HTTPException) as exc:
        get_domain_object(DomainEnum(domain), object_id, conn=fake_pg_conn)
    assert exc.value.status_code == 404
