# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for cross-domain linker — bidirectional professor-company writes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data_agents.contracts import (
    CompanyRecord,
    Evidence,
    ProfessorRecord,
    ReleasedObject,
)
from src.data_agents.professor.cross_domain import CompanyLink
from src.data_agents.professor.cross_domain_linker import (
    find_company_by_name,
    write_bidirectional_link,
)
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)
_EVIDENCE = [
    Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn/zh/lizhi",
        fetched_at=TIMESTAMP,
        confidence=0.9,
    )
]


def _professor_released_object() -> ReleasedObject:
    return ReleasedObject(
        id="PROF-test123",
        object_type="professor",
        display_name="李志",
        core_facts={
            "name": "李志",
            "institution": "南方科技大学",
            "department": "计算机科学与工程系",
            "company_roles": [],
        },
        summary_fields={"profile_summary": "李志教授的个人简介" * 20},
        evidence=_EVIDENCE,
        last_updated=TIMESTAMP,
    )


def _company_released_object() -> ReleasedObject:
    return ReleasedObject(
        id="COMP-abc456",
        object_type="company",
        display_name="深圳点联传感科技有限公司",
        core_facts={
            "name": "深圳点联传感科技有限公司",
            "normalized_name": "深圳点联传感科技有限公司",
            "industry": "传感器",
            "professor_ids": [],
        },
        summary_fields={
            "profile_summary": "深圳点联传感科技有限公司简介" * 10,
            "evaluation_summary": "评估" * 20,
            "technology_route_summary": "技术路线" * 10,
        },
        evidence=[Evidence(
            source_type="xlsx_import",
            source_file="companies.xlsx",
            fetched_at=TIMESTAMP,
            confidence=0.9,
        )],
        last_updated=TIMESTAMP,
    )


class TestFindCompanyByName:
    """Test finding company by name in store."""

    def test_finds_matching_company(self, tmp_path: Path):
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        company = _company_released_object()
        store.upsert_released_objects([company])

        found = find_company_by_name(store, "深圳点联传感科技有限公司")
        assert found is not None
        assert found.id == "COMP-abc456"

    def test_matches_company_name_variants_via_normalized_name(self, tmp_path: Path):
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        company = _company_released_object()
        store.upsert_released_objects([company])

        found = find_company_by_name(store, "点联传感科技")
        assert found is not None
        assert found.id == "COMP-abc456"

    def test_matches_company_name_with_city_and_suffix_variants(self, tmp_path: Path):
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        company = _company_released_object()
        store.upsert_released_objects([company])

        found = find_company_by_name(store, "深圳市点联传感科技股份有限公司")
        assert found is not None
        assert found.id == "COMP-abc456"

    def test_matches_company_name_with_parenthetical_alias(self, tmp_path: Path):
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        company = _company_released_object()
        store.upsert_released_objects([company])

        found = find_company_by_name(store, "点联传感科技（Pointsense）")
        assert found is not None
        assert found.id == "COMP-abc456"

    def test_returns_none_for_unknown_company(self, tmp_path: Path):
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        found = find_company_by_name(store, "不存在的公司")
        assert found is None


class TestWriteBidirectionalLink:
    """Test bidirectional write of professor-company links."""

    def test_writes_both_sides(self, tmp_path: Path):
        """Both professor.company_roles and company.professor_ids updated."""
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        prof = _professor_released_object()
        company = _company_released_object()
        store.upsert_released_objects([prof])
        store.upsert_released_objects([company])

        link = CompanyLink(
            company_id="COMP-abc456",
            company_name="深圳点联传感科技有限公司",
            role="首席科学家",
            evidence_url="https://news.example.com",
            source="web_search",
        )
        write_bidirectional_link(store, "PROF-test123", link)

        # Check professor side
        updated_prof = store.get_object("professor", "PROF-test123")
        assert updated_prof is not None
        roles = updated_prof.core_facts.get("company_roles", [])
        assert len(roles) == 1
        assert roles[0]["company_name"] == "深圳点联传感科技有限公司"

        # Check company side
        updated_company = store.get_object("company", "COMP-abc456")
        assert updated_company is not None
        prof_ids = updated_company.core_facts.get("professor_ids", [])
        assert "PROF-test123" in prof_ids

    def test_no_duplicate_company_link(self, tmp_path: Path):
        """Writing same link twice does not create duplicate."""
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        prof = _professor_released_object()
        company = _company_released_object()
        store.upsert_released_objects([prof])
        store.upsert_released_objects([company])

        link = CompanyLink(
            company_id="COMP-abc456",
            company_name="深圳点联传感科技有限公司",
            role="首席科学家",
            evidence_url="https://news.example.com",
            source="web_search",
        )
        write_bidirectional_link(store, "PROF-test123", link)
        write_bidirectional_link(store, "PROF-test123", link)

        updated_prof = store.get_object("professor", "PROF-test123")
        roles = updated_prof.core_facts.get("company_roles", [])
        assert len(roles) == 1

        updated_company = store.get_object("company", "COMP-abc456")
        prof_ids = updated_company.core_facts.get("professor_ids", [])
        assert prof_ids.count("PROF-test123") == 1

    def test_company_not_in_db_writes_professor_only(self, tmp_path: Path):
        """Company not in database → professor side still written, company_id=None."""
        store = SqliteReleasedObjectStore(tmp_path / "test.db")
        prof = _professor_released_object()
        store.upsert_released_objects([prof])

        link = CompanyLink(
            company_id=None,
            company_name="未知公司",
            role="顾问",
            evidence_url="https://example.com",
            source="web_search",
        )
        write_bidirectional_link(store, "PROF-test123", link)

        updated_prof = store.get_object("professor", "PROF-test123")
        roles = updated_prof.core_facts.get("company_roles", [])
        assert len(roles) == 1
        assert roles[0]["company_name"] == "未知公司"
