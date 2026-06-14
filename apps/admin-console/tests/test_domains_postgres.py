from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from fastapi import HTTPException

from backend.api import domains as domains_api
from backend.api.domains import (
    DomainEnum,
    UpdateRecordRequest,
    delete_domain_object,
    get_domain_object,
    get_filter_options,
    get_related_objects,
    list_domain,
    review_company_enrichment_item,
    update_domain_object,
)
from backend.services.data_helpers import _list_professors

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
            "lifecycle_state": "active",
            "lifecycle_merged_into_id": None,
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
            "profile_summary": None,
            "technology_route_summary": None,
            "last_refreshed_at": NOW,
            "created_at": NOW,
            "updated_at": NOW,
            "import_batch_id": 7,
            "source_row_number": 4,
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
            "products_json": [
                {
                    "product_id": "PROD-TEST",
                    "name": "旭宏医疗",
                    "description": "AI心电智能筛查服务。",
                    "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                    "quality_status": "needs_review",
                    "product_category": "心电诊断系统",
                    "target_customers": ["医院/临床机构"],
                    "application_scenarios": ["远程心电诊断"],
                    "technical_tags": ["AI自动诊断"],
                    "source_type": "pitchhub_36kr",
                    "source_tier": "pitchhub_36kr",
                    "source_tiers": ["pitchhub_36kr"],
                    "fetched_at": NOW.isoformat(),
                    "evidence": [
                        {
                            "field_name": "short_description",
                            "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                            "source_type": "pitchhub_36kr",
                            "source_tier": "pitchhub_36kr",
                            "evidence_span": "AI心电智能筛查服务",
                            "confidence": 0.8,
                        }
                    ],
                }
            ],
            "application_scenarios_json": [
                {
                    "scenario_id": "SCEN-TEST",
                    "scenario_name": "远程心电诊断",
                    "scenario_category": "医疗诊断",
                    "description": "支持临床远程心电诊断及监护。",
                    "target_customer": "医院/临床机构",
                    "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                    "quality_status": "needs_review",
                    "source_type": "pitchhub_36kr",
                    "source_tier": "pitchhub_36kr",
                    "source_tiers": ["pitchhub_36kr"],
                    "fetched_at": NOW.isoformat(),
                    "evidence": [
                        {
                            "field_name": "description",
                            "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                            "source_type": "pitchhub_36kr",
                            "source_tier": "pitchhub_36kr",
                            "evidence_span": "临床远程心电诊断及监护",
                            "confidence": 0.78,
                        }
                    ],
                }
            ],
            "recent_events_json": [
                {
                    "event_id": "22222222-2222-2222-2222-222222222222",
                    "event_type": "funding",
                    "event_date": "2026-05-01",
                    "summary": "旭宏医疗完成天使轮融资。",
                    "status": "active",
                    "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                    "source_type": "pitchhub_36kr",
                    "source_tier": "pitchhub_36kr",
                    "source_file": None,
                    "fetched_at": NOW.isoformat(),
                    "normalized": {
                        "round": "天使轮",
                        "amount": None,
                        "investors": [],
                        "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                    },
                }
            ],
            "source_records_json": [
                {
                    "source_type": "pitchhub_36kr",
                    "source_tier": "pitchhub_36kr",
                    "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
                    "fetched_at": NOW.isoformat(),
                    "snippet": "项目简介：AI心电智能筛查服务。",
                    "confidence": 0.8,
                }
            ],
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
            "summary_zh": "A test paper.",
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
        "paper_partial": {
            "paper_id": "PAPER-PARTIAL",
            "title_clean": "Partial Paper",
            "title_raw": "Partial Paper",
            "doi": None,
            "arxiv_id": None,
            "openalex_id": None,
            "semantic_scholar_id": None,
            "year": 2026,
            "venue": "DraftConf",
            "abstract_clean": None,
            "summary_zh": None,
            "authors_display": "Ada Lovelace",
            "authors_raw": None,
            "citation_count": 100,
            "canonical_source": "manual",
            "quality_status": "needs_review",
            "pdf_url": None,
            "first_seen_at": NOW,
            "updated_at": NOW,
            "run_id": RUN_ID,
            "admin_action": None,
            "linked_professor_count": 1,
            "verified_professor_count": 1,
            "total_count": 2,
        },
        "paper_ready": {
            "paper_id": "PAPER-READY",
            "title_clean": "Ready Paper With Summary",
            "title_raw": "Ready Paper With Summary",
            "doi": None,
            "arxiv_id": None,
            "openalex_id": None,
            "semantic_scholar_id": None,
            "year": 2025,
            "venue": "ReadyConf",
            "abstract_clean": "A complete abstract.",
            "summary_zh": "一段可展示的中文摘要。",
            "authors_display": "Ada Lovelace",
            "authors_raw": None,
            "citation_count": 1,
            "canonical_source": "manual",
            "quality_status": "ready",
            "pdf_url": None,
            "first_seen_at": NOW,
            "updated_at": NOW,
            "run_id": RUN_ID,
            "admin_action": None,
            "linked_professor_count": 1,
            "verified_professor_count": 1,
            "total_count": 2,
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
            "summary_text": "A readable patent summary.",
            "summary_text_method": "llm",
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
        self.paper_aliases: dict[str, str] = {}

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
        if sql_lower.startswith("insert into professor_admin_action"):
            return _FakeResult([])
        if sql_lower.startswith("insert into company_enrichment_review_action"):
            return _FakeResult([])
        if sql_lower.startswith("update pipeline_run"):
            return _FakeResult([])
        if sql_lower.startswith("select canonical_paper_id") and "from paper_merge_alias" in sql_lower:
            paper_id = params.get("paper_id") if isinstance(params, dict) else None
            canonical_paper_id = self.paper_aliases.get(str(paper_id))
            return _FakeResult(
                [{"canonical_paper_id": canonical_paper_id}]
                if canonical_paper_id
                else []
            )
        if sql_lower.startswith("select quality_status") and "from company_product" in sql_lower:
            return _FakeResult(
                [{"quality_status": "needs_review", "company_id": "COMP-TEST"}]
            )
        if sql_lower.startswith("select quality_status") and "from company_application_scenario" in sql_lower:
            return _FakeResult(
                [{"quality_status": "needs_review", "company_id": "COMP-TEST"}]
            )
        if sql_lower.startswith("update company_product"):
            self.records["company"]["products_json"][0]["quality_status"] = params[
                "new_status"
            ]
            return _FakeResult([])
        if sql_lower.startswith("update company_application_scenario"):
            self.records["company"]["application_scenarios_json"][0][
                "quality_status"
            ] = params["new_status"]
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
        if sql_lower.startswith("select lifecycle_state, lifecycle_merged_into_id"):
            row = self.records["professor"]
            object_id = params[0] if isinstance(params, tuple) else None
            if object_id != row["professor_id"]:
                return _FakeResult([])
            return _FakeResult(
                [
                    {
                        "lifecycle_state": row["lifecycle_state"],
                        "lifecycle_merged_into_id": row["lifecycle_merged_into_id"],
                        "updated_at": row["updated_at"],
                    }
                ]
            )

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
        if domain == "professor" and "active_paper_counts.active_paper_count" in sql_lower:
            record["active_paper_count"] = 2
            record["verified_paper_count"] = 1
            if record.get("paper_count") is None:
                record["paper_count"] = record["active_paper_count"]
        if (
            domain == "paper"
            and "join professor_paper_link ppl on ppl.paper_id = p.paper_id"
            in sql_lower
        ):
            rows = [
                copy.deepcopy(self.records["paper_partial"]),
                copy.deepcopy(self.records["paper_ready"]),
            ]
            if "case when p.quality_status = 'ready'" in sql_lower:
                rows.sort(
                    key=lambda row: (
                        row.get("quality_status") != "ready",
                        not row.get("summary_zh"),
                        not row.get("abstract_clean"),
                        -(row.get("citation_count") or 0),
                    )
                )
            return rows
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
        row = self.records["professor"]
        if isinstance(params, tuple):
            if "lifecycle_state = %s" in sql_lower:
                row["lifecycle_state"] = params[0]
                row["lifecycle_merged_into_id"] = params[1]
                return
            raise AssertionError(f"Unexpected tuple params for professor update: {params!r}")
        assert isinstance(params, dict)
        if "identity_status = 'inactive'" in sql_lower:
            row["identity_status"] = "inactive"
        if "lifecycle_state" in params:
            row["lifecycle_state"] = params["lifecycle_state"]
        if "lifecycle_merged_into_id" in params:
            row["lifecycle_merged_into_id"] = params["lifecycle_merged_into_id"]
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
        if "summary_profile_summary" in params:
            row["profile_summary"] = params["summary_profile_summary"]
        if "summary_technology_route_summary" in params:
            row["technology_route_summary"] = params[
                "summary_technology_route_summary"
            ]

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
        if "summary_text" in params:
            row["abstract_clean"] = params["summary_text"]
        if "summary_zh" in params:
            row["summary_zh"] = params["summary_zh"]
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
        if "summary_text" in params:
            row["summary_text"] = params["summary_text"]
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
    expected_keys = set(RELEASED_KEYS)
    if domain == "professor":
        expected_keys.update({"lifecycle_state", "lifecycle_merged_into_id"})
    assert set(payload["items"][0]) == expected_keys


@pytest.mark.parametrize(
    ("domain", "column"),
    [
        ("professor", "p.quality_status"),
        ("company", "c.quality_status"),
        ("paper", "p.quality_status"),
        ("patent", "patent.quality_status"),
    ],
)
def test_quality_filter_uses_canonical_quality_status_column(
    fake_pg_conn: _FakePostgresConn,
    domain: str,
    column: str,
) -> None:
    list_domain(
        DomainEnum(domain),
        page=1,
        page_size=20,
        sort_by="display_name",
        sort_order="asc",
        filters=json.dumps({"quality_status": "needs_review"}),
        conn=fake_pg_conn,
    )

    sql, params = fake_pg_conn.calls[-1]
    assert f"{column} = %(filter_quality_status)s" in sql
    assert params["filter_quality_status"] == "needs_review"
    assert "identity_status = 'needs_review'" not in sql


def test_list_domain_accepts_top_level_quality_status_query_param(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    list_domain(
        DomainEnum.paper,
        page=1,
        page_size=20,
        sort_by="display_name",
        sort_order="asc",
        quality_status="ready",
        conn=fake_pg_conn,
    )

    sql, params = fake_pg_conn.calls[-1]
    assert "p.quality_status = %(filter_quality_status)s" in sql
    assert params["filter_quality_status"] == "ready"


def test_company_search_uses_jsonb_alias_expansion(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    list_domain(
        DomainEnum.company,
        q="深圳迈塔兰斯科技",
        page=1,
        page_size=20,
        sort_by="display_name",
        sort_order="asc",
        conn=fake_pg_conn,
    )

    sql = fake_pg_conn.calls[-1][0]
    assert "jsonb_array_elements_text" in sql
    assert "unnest(c.aliases)" not in sql


def test_company_search_includes_latest_xlsx_project_name(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    list_domain(
        DomainEnum.company,
        q="Analytical Engine",
        page=1,
        page_size=20,
        sort_by="display_name",
        sort_order="asc",
        conn=fake_pg_conn,
    )

    sql = fake_pg_conn.calls[-1][0]
    assert "latest_snapshot.project_name ILIKE" in sql
    assert "latest_snapshot.company_name_xlsx ILIKE" in sql


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
    expected_keys = set(RELEASED_KEYS)
    if domain == "professor":
        expected_keys.update({"lifecycle_state", "lifecycle_merged_into_id"})
    assert set(payload) == expected_keys


def test_professor_released_object_exposes_lifecycle_separate_from_quality(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    fake_pg_conn.records["professor"]["quality_status"] = "ready"
    fake_pg_conn.records["professor"]["lifecycle_state"] = "archived"

    payload = get_domain_object(DomainEnum.professor, "PROF-TEST", conn=fake_pg_conn)

    assert payload["quality_status"] == "ready"
    assert payload["lifecycle_state"] == "archived"
    assert payload["lifecycle_merged_into_id"] is None


def test_professor_domain_detail_falls_back_to_linked_paper_counts(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    fake_pg_conn.records["professor"]["paper_count"] = None

    payload = get_domain_object(DomainEnum.professor, "PROF-TEST", conn=fake_pg_conn)

    assert payload["core_facts"]["paper_count"] == 2
    assert payload["core_facts"]["verified_paper_count"] == 1
    sql = fake_pg_conn.calls[0][0]
    assert "active_paper_counts.active_paper_count" in sql
    assert "verified_paper_counts.verified_paper_count" in sql


def test_paper_domain_detail_resolves_merge_alias(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    fake_pg_conn.paper_aliases["PAPER-OLD"] = "PAPER-TEST"

    payload = get_domain_object(DomainEnum.paper, "PAPER-OLD", conn=fake_pg_conn)

    assert payload["id"] == "PAPER-TEST"
    assert payload["display_name"] == "Notes on the Analytical Engine"
    assert fake_pg_conn.calls[0][1] == {"paper_id": "PAPER-OLD"}
    assert fake_pg_conn.calls[1][1]["object_id"] == "PAPER-TEST"


def test_company_released_object_exposes_products_events_and_source_evidence(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    payload = get_domain_object(DomainEnum.company, "COMP-TEST", conn=fake_pg_conn)

    assert payload["core_facts"]["products"][0]["name"] == "旭宏医疗"
    assert payload["core_facts"]["products"][0]["product_category"] == "心电诊断系统"
    assert payload["core_facts"]["products"][0]["application_scenarios"] == ["远程心电诊断"]
    assert payload["core_facts"]["products"][0]["source_tier"] == "pitchhub_36kr"
    assert (
        payload["core_facts"]["products"][0]["evidence"][0]["evidence_span"]
        == "AI心电智能筛查服务"
    )
    assert payload["core_facts"]["application_scenarios"][0]["scenario_name"] == "远程心电诊断"
    assert (
        payload["core_facts"]["application_scenarios"][0]["evidence"][0]["source_tier"]
        == "pitchhub_36kr"
    )
    assert payload["core_facts"]["recent_events"][0]["event_type"] == "funding"
    assert payload["core_facts"]["recent_events"][0]["summary"] == "旭宏医疗完成天使轮融资。"
    assert payload["core_facts"]["recent_events"][0]["status"] == "active"
    assert payload["core_facts"]["recent_events"][0]["normalized"]["round"] == "天使轮"
    assert payload["core_facts"]["recent_events"][0]["source_tier"] == "pitchhub_36kr"
    assert payload["evidence"][0]["source_type"] == "xlsx_import"
    assert payload["evidence"][0]["source_tier"] == "xlsx"
    assert "import_batch_id=7" in payload["evidence"][0]["source_file"]
    assert any(
        item["source_type"] == "pitchhub_36kr"
        and item["source_url"] == "https://pitchhub.36kr.com/project/1678475362006017"
        for item in payload["evidence"]
    )
    assert "'status', cse.status" in fake_pg_conn.calls[0][0]


def test_company_release_sql_uses_source_confidence_publication_policy(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    get_domain_object(DomainEnum.company, "COMP-TEST", conn=fake_pg_conn)

    company_sql = fake_pg_conn.calls[0][0]
    assert "FROM company_product cp" in company_sql
    assert "cp.quality_status = 'ready' OR" in company_sql
    assert "cp.quality_status = 'needs_review'" in company_sql
    assert "company_product_evidence publishable_evidence" in company_sql
    assert "'xlsx', 'official', 'official_site', 'iyiou', 'pitchhub_36kr'" in company_sql
    assert "FROM company_application_scenario cas" in company_sql
    assert "cas.quality_status = 'ready' OR" in company_sql
    assert "cas.quality_status = 'needs_review'" in company_sql
    assert "company_application_scenario_evidence publishable_evidence" in company_sql
    assert "'evidence', COALESCE(product_evidence.evidence_json" in company_sql
    assert "'evidence', COALESCE(scenario_evidence.evidence_json" in company_sql


def test_update_professor_lifecycle_records_admin_run_and_audit(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    payload = domains_api.update_professor_lifecycle(
        "PROF-TEST",
        domains_api.ProfessorLifecycleUpdateRequest(
            lifecycle_state="archived",
            actor="ops",
            note="Historical school roster entry.",
        ),
        conn=fake_pg_conn,
    )

    assert payload["id"] == "PROF-TEST"
    assert payload["quality_status"] == "ready"
    assert payload["lifecycle_state"] == "archived"
    assert fake_pg_conn.run_scopes[-1]["action"] == "set_lifecycle_state"
    assert any(
        sql.startswith("INSERT INTO professor_admin_action")
        for sql, _params in fake_pg_conn.calls
    )


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
    expected_keys = set(RELEASED_KEYS)
    if expected_type == "professor":
        expected_keys.update({"lifecycle_state", "lifecycle_merged_into_id"})
    assert set(payload[bucket][0]) == expected_keys


def test_professor_related_papers_prioritize_ready_with_summary_and_abstract(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = get_related_objects(DomainEnum.professor, "PROF-TEST", conn=fake_pg_conn)
    payload = response.model_dump(mode="json")

    assert [paper["id"] for paper in payload["papers"]] == [
        "PAPER-READY",
        "PAPER-PARTIAL",
    ]
    first = payload["papers"][0]
    assert first["quality_status"] == "ready"
    assert first["summary_fields"]["summary_zh"]
    assert first["core_facts"]["abstract"]
    assert "openalex_id" in first["core_facts"]
    sql = fake_pg_conn.calls[-3][0]
    assert "CASE WHEN p.quality_status = 'ready'" in sql
    assert "CASE WHEN NULLIF(p.summary_zh, '') IS NOT NULL" in sql
    assert "CASE WHEN NULLIF(p.abstract_clean, '') IS NOT NULL" in sql


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


def test_patch_paper_summary_zh_updates_summary_zh_not_abstract(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = update_domain_object(
        DomainEnum.paper,
        "PAPER-TEST",
        conn=fake_pg_conn,
        body=UpdateRecordRequest(
            summary_fields={"summary_zh": "更新后的中文摘要"}
        ),
    )

    assert response["summary_fields"]["summary_zh"] == "更新后的中文摘要"
    assert fake_pg_conn.records["paper"]["abstract_clean"] == "A test paper."
    update_sql = next(
        sql for sql, _params in fake_pg_conn.calls if sql.startswith("UPDATE paper SET")
    )
    assert "summary_zh = %(summary_zh)s" in update_sql
    assert "abstract_clean = %(summary_zh)s" not in update_sql


def test_patch_professor_quality_status_requires_admin_mark_endpoint(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        update_domain_object(
            DomainEnum.professor,
            "PROF-TEST",
            conn=fake_pg_conn,
            body=UpdateRecordRequest(quality_status="ready"),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "professor_quality_requires_mark_endpoint"
    assert not any(
        sql.startswith("UPDATE professor SET") for sql, _params in fake_pg_conn.calls
    )


def test_patch_company_quality_status_keeps_generic_contract(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = update_domain_object(
        DomainEnum.company,
        "COMP-TEST",
        conn=fake_pg_conn,
        body=UpdateRecordRequest(quality_status="ready"),
    )

    assert response["quality_status"] == "ready"
    assert any(
        sql.startswith("UPDATE company SET") for sql, _params in fake_pg_conn.calls
    )


def test_patch_company_summary_updates_company_summary_columns_not_xlsx_snapshot(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    original_description = fake_pg_conn.records["company"]["description"]
    original_business = fake_pg_conn.records["company"]["business"]

    response = update_domain_object(
        DomainEnum.company,
        "COMP-TEST",
        conn=fake_pg_conn,
        body=UpdateRecordRequest(
            summary_fields={
                "profile_summary": "这是合成后的长公司简介。",
                "technology_route_summary": "这是合成后的技术路线。",
            }
        ),
    )

    assert response["summary_fields"]["profile_summary"] == "这是合成后的长公司简介。"
    assert response["summary_fields"]["technology_route_summary"] == "这是合成后的技术路线。"
    assert fake_pg_conn.records["company"]["description"] == original_description
    assert fake_pg_conn.records["company"]["business"] == original_business
    update_company_calls = [
        params
        for sql, params in fake_pg_conn.calls
        if sql.startswith("UPDATE company SET")
    ]
    assert update_company_calls
    assert update_company_calls[-1]["summary_profile_summary"] == "这是合成后的长公司简介。"
    assert (
        update_company_calls[-1]["summary_technology_route_summary"]
        == "这是合成后的技术路线。"
    )
    assert not any(
        sql.startswith("UPDATE company_snapshot")
        for sql, _params in fake_pg_conn.calls
    )


def test_review_company_product_accepts_row_and_records_audit(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = review_company_enrichment_item(
        company_id="COMP-TEST",
        target_type="product",
        target_id="PROD-TEST",
        conn=fake_pg_conn,
        body=domains_api.CompanyEnrichmentReviewRequest(
            action="accept",
            actor="ops",
            note="Verified.",
        ),
    )

    assert response["target_type"] == "product"
    assert response["target_id"] == "PROD-TEST"
    assert response["previous_status"] == "needs_review"
    assert response["new_status"] == "ready"
    assert any(
        "INSERT INTO company_enrichment_review_action" in sql
        for sql, _params in fake_pg_conn.calls
    )


def test_review_company_scenario_rejects_row_and_records_audit(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = review_company_enrichment_item(
        company_id="COMP-TEST",
        target_type="scenario",
        target_id="SCEN-TEST",
        conn=fake_pg_conn,
        body=domains_api.CompanyEnrichmentReviewRequest(
            action="reject",
            actor="ops",
            note="Not supported by source.",
        ),
    )

    assert response["target_type"] == "scenario"
    assert response["new_status"] == "rejected"
    assert any(
        "UPDATE company_application_scenario" in sql
        for sql, _params in fake_pg_conn.calls
    )


def test_patch_patent_summary_text_updates_summary_text_not_abstract(
    fake_pg_conn: _FakePostgresConn,
) -> None:
    response = update_domain_object(
        DomainEnum.patent,
        "PAT-TEST",
        conn=fake_pg_conn,
        body=UpdateRecordRequest(
            summary_fields={"summary_text": "更新后的专利通俗解读"}
        ),
    )

    assert response["summary_fields"]["summary_text"] == "更新后的专利通俗解读"
    assert fake_pg_conn.records["patent"]["abstract_clean"] == "A test patent."
    update_sql = next(
        sql for sql, _params in fake_pg_conn.calls if sql.startswith("UPDATE patent SET")
    )
    assert "summary_text = %(summary_text)s" in update_sql
    assert "abstract_clean = %(summary_text)s" not in update_sql


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
