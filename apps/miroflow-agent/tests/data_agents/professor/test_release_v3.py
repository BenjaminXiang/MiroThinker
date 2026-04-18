# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for V3 release changes: evaluation_summary removal."""
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


class TestEvaluationSummaryRemoval:
    """Verify evaluation_summary is optional in ProfessorRecord and release pipeline."""

    def test_professor_record_without_evaluation_summary(self):
        """ProfessorRecord should accept empty evaluation_summary (default)."""
        record = ProfessorRecord(
            id="PROF-test123",
            name="李志",
            institution="南方科技大学",
            department="计算机科学与工程系",
            title="教授",
            email="lizhi@sustech.edu.cn",
            research_directions=["机器学习"],
            profile_summary="这是一段足够长的个人简介" * 20,
            # No evaluation_summary — should default to ""
            evidence=_EVIDENCE,
            last_updated=TIMESTAMP,
        )
        assert record.evaluation_summary == ""

    def test_released_object_omits_empty_evaluation_summary(self):
        """to_released_object should not include evaluation_summary when empty."""
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
        # evaluation_summary should not appear in summary_fields when empty
        assert "evaluation_summary" not in released.summary_fields

    def test_release_pipeline_with_profile_only_summarizer(self):
        """Release pipeline should work with summarizer that returns empty evaluation_summary."""
        profile = _merged_record()
        release_result = build_professor_release(
            profiles=[profile],
            summarizer=lambda p: ProfessorSummaries(
                profile_summary=f"好的个人简介关于{p.name}",
                evaluation_summary="",  # Explicitly empty
            ),
            official_domain_suffixes=("sustech.edu.cn",),
            now=TIMESTAMP,
        )
        # Should not skip the record due to empty evaluation_summary
        assert len(release_result.professor_records) == 1
        assert release_result.professor_records[0].evaluation_summary == ""

    def test_release_pipeline_rule_based_no_evaluation_summary(self):
        """Rule-based summarizer should not produce evaluation_summary."""
        profile = _merged_record()
        release_result = build_professor_release(
            profiles=[profile],
            official_domain_suffixes=("sustech.edu.cn",),
            now=TIMESTAMP,
        )
        assert len(release_result.professor_records) == 1
        professor = release_result.professor_records[0]
        # evaluation_summary should be empty — rule-based no longer generates it
        assert professor.evaluation_summary == ""
