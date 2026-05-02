# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for V3 profile-only release behavior."""
from __future__ import annotations

from datetime import datetime, timezone

from src.data_agents.contracts import ProfessorRecord, Evidence
from src.data_agents.professor.models import MergedProfessorProfileRecord
from src.data_agents.professor.release import (
    ProfessorSummaries,
    build_professor_release,
)


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)
_EVIDENCE = [
    Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn/zh/lizhi",
        fetched_at=TIMESTAMP,
        confidence=0.9,
    )
]


def _merged_record(**kwargs) -> MergedProfessorProfileRecord:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        title="教授",
        email="lizhi@sustech.edu.cn",
        office="工学院南楼",
        homepage=None,
        profile_url="https://scholar.example.com/lizhi",
        source_urls=("https://scholar.example.com/lizhi",),
        evidence=("https://scholar.example.com/lizhi",),
        research_directions=("机器学习", "具身智能"),
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source="https://www.sustech.edu.cn/zh/letter/",
    )
    defaults.update(kwargs)
    return MergedProfessorProfileRecord(**defaults)


class TestProfileOnlyRelease:
    """Verify professor release works with profile summaries only."""

    def test_professor_record_uses_profile_summary_only(self):
        record = ProfessorRecord(
            id="PROF-test123",
            name="李志",
            institution="南方科技大学",
            department="计算机科学与工程系",
            title="教授",
            email="lizhi@sustech.edu.cn",
            research_directions=["机器学习"],
            profile_summary="这是一段足够长的个人简介" * 20,
            evidence=_EVIDENCE,
            last_updated=TIMESTAMP,
        )
        assert record.profile_summary

    def test_released_object_has_profile_summary_only(self):
        record = ProfessorRecord(
            id="PROF-test123",
            name="李志",
            institution="南方科技大学",
            department="计算机科学与工程系",
            title="教授",
            email="lizhi@sustech.edu.cn",
            research_directions=["机器学习"],
            profile_summary="这是一段足够长的个人简介" * 20,
            evidence=_EVIDENCE,
            last_updated=TIMESTAMP,
        )
        released = record.to_released_object()
        assert released.summary_fields == {"profile_summary": record.profile_summary}

    def test_release_pipeline_with_profile_only_summarizer(self):
        profile = _merged_record()
        release_result = build_professor_release(
            profiles=[profile],
            summarizer=lambda p: ProfessorSummaries(
                profile_summary=f"好的个人简介关于{p.name}",
            ),
            official_domain_suffixes=("sustech.edu.cn",),
            now=TIMESTAMP,
        )
        assert len(release_result.professor_records) == 1

    def test_release_pipeline_rule_based_summary(self):
        profile = _merged_record()
        release_result = build_professor_release(
            profiles=[profile],
            official_domain_suffixes=("sustech.edu.cn",),
            now=TIMESTAMP,
        )
        assert len(release_result.professor_records) == 1
        professor = release_result.professor_records[0]
        assert professor.profile_summary
