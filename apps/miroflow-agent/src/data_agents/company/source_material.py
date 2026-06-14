from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CompanySourceMaterial:
    source_id: str
    source_tier: str
    url: str
    title: str | None
    captured_text: str
    captured_at: datetime | None = None
    trust_reason: str | None = None
    source_judgment_status: str | None = None
    source_judgment_confidence: Decimal | None = None
    source_judgment_evidence_span: str | None = None
    acquisition_method: str | None = None
    evidence_span: str | None = None
    failure_reason: str | None = None
