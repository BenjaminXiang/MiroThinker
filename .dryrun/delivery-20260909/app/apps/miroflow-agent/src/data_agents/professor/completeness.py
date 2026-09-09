# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Completeness evaluation for enriched professor profiles.

Determines whether Stage 2c (agent enrichment) should be triggered
based on weighted gap analysis of fields not covered by regex pre-extract
and paper collection.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import EnrichedProfessorProfile

AGENT_TARGET_FIELDS: dict[str, float] = {
    "education_structured": 0.6,
    "work_experience": 0.6,
    "awards": 0.5,
    "academic_positions": 0.4,
    "projects": 0.4,
    "company_roles": 0.8,
    "patent_ids": 0.5,
    "department": 0.8,
    "title": 0.8,
}

AGENT_TRIGGER_THRESHOLD: float = 0.5


@dataclass(frozen=True)
class CompletenessAssessment:
    missing_fields: list[str]
    gap_weighted_sum: float
    should_trigger_agent: bool
    priority_fields: list[str]


def _is_field_missing(profile: EnrichedProfessorProfile, field_name: str) -> bool:
    value = getattr(profile, field_name, None)
    if value is None:
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def assess_completeness(
    profile: EnrichedProfessorProfile,
) -> CompletenessAssessment:
    missing_fields: list[str] = []
    gap_weighted_sum = 0.0

    for field_name, weight in AGENT_TARGET_FIELDS.items():
        if _is_field_missing(profile, field_name):
            missing_fields.append(field_name)
            gap_weighted_sum += weight

    priority_fields = sorted(
        missing_fields,
        key=lambda f: AGENT_TARGET_FIELDS.get(f, 0.0),
        reverse=True,
    )

    return CompletenessAssessment(
        missing_fields=missing_fields,
        gap_weighted_sum=round(gap_weighted_sum, 2),
        should_trigger_agent=gap_weighted_sum >= AGENT_TRIGGER_THRESHOLD,
        priority_fields=priority_fields,
    )
