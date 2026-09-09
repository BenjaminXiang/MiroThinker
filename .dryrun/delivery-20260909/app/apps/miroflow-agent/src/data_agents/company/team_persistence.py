from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from ..normalization import normalize_person_name
from .team_parser import StructuredTeamMember


def persist_structured_team_members(
    conn: Any,
    *,
    company_id: str,
    snapshot_id: UUID,
    members: list[StructuredTeamMember],
) -> int:
    inserted_or_updated = 0
    for member_order, member in enumerate(members, start=1):
        conn.execute(
            """
            WITH updated AS (
                UPDATE company_team_member
                   SET raw_name = %(raw_name)s,
                       raw_role = %(raw_role)s,
                       raw_intro = %(raw_intro)s,
                       normalized_name = %(normalized_name)s,
                       structured_background = %(structured_background)s,
                       structured_experience_highlights = %(structured_experience_highlights)s,
                       structured_relevance = %(structured_relevance)s,
                       structured_confidence = %(structured_confidence)s,
                       structured_evidence_span = %(structured_evidence_span)s,
                       structured_raw_text = %(structured_raw_text)s
                 WHERE company_id = %(company_id)s
                   AND snapshot_id = %(snapshot_id)s
                   AND member_order = %(member_order)s
                RETURNING member_id
            )
            INSERT INTO company_team_member (
                company_id,
                snapshot_id,
                member_order,
                raw_name,
                raw_role,
                raw_intro,
                normalized_name,
                structured_background,
                structured_experience_highlights,
                structured_relevance,
                structured_confidence,
                structured_evidence_span,
                structured_raw_text
            )
            SELECT
                %(company_id)s,
                %(snapshot_id)s,
                %(member_order)s,
                %(raw_name)s,
                %(raw_role)s,
                %(raw_intro)s,
                %(normalized_name)s,
                %(structured_background)s,
                %(structured_experience_highlights)s,
                %(structured_relevance)s,
                %(structured_confidence)s,
                %(structured_evidence_span)s,
                %(structured_raw_text)s
            WHERE NOT EXISTS (SELECT 1 FROM updated)
            """,
            {
                "company_id": company_id,
                "snapshot_id": snapshot_id,
                "member_order": member_order,
                "raw_name": member.name,
                "raw_role": member.role,
                "raw_intro": member.background,
                "normalized_name": normalize_person_name(member.name),
                "structured_background": member.background,
                "structured_experience_highlights": Jsonb(
                    list(member.experience_highlights)
                ),
                "structured_relevance": member.relevance,
                "structured_confidence": _confidence_decimal(member.confidence),
                "structured_evidence_span": member.evidence_span,
                "structured_raw_text": member.raw_text,
            },
        )
        inserted_or_updated += 1
    return inserted_or_updated


def _confidence_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
