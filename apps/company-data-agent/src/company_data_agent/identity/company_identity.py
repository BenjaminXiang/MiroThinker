"""Canonical credit-code normalization and deterministic company ID generation."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field

_CREDIT_CODE_PATTERN = re.compile(r"^[0-9A-Z]{18}$")
_COMPANY_ID_PATTERN = re.compile(r"^COMP-[0-9A-F]{20}$")


def normalize_credit_code(raw_credit_code: str) -> str:
    """Normalize a raw credit code by removing presentation noise and validating it."""

    stripped = "".join(
        char for char in raw_credit_code.strip().upper() if not char.isspace() and char != "-"
    )
    if not _CREDIT_CODE_PATTERN.fullmatch(stripped):
        raise ValueError("credit_code must normalize to an 18-character uppercase alphanumeric string")
    return stripped


def generate_company_id(raw_credit_code: str) -> str:
    """Generate a deterministic company ID from a normalized credit code."""

    normalized_credit_code = normalize_credit_code(raw_credit_code)
    digest = hashlib.sha256(normalized_credit_code.encode("utf-8")).hexdigest().upper()[:20]
    return f"COMP-{digest}"


def validate_company_id(company_id: str) -> str:
    """Validate the canonical company ID format."""

    normalized = company_id.strip().upper()
    if not _COMPANY_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "company id must match the canonical format COMP-{20 uppercase hex chars}"
        )
    return normalized


class CompanyIdentity(BaseModel):
    """Canonical normalized company identity used before deduplication and enrichment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    credit_code: str = Field(min_length=18, max_length=18)
    company_id: str = Field(min_length=25, max_length=25)

    @classmethod
    def from_raw_credit_code(cls, raw_credit_code: str) -> "CompanyIdentity":
        normalized_credit_code = normalize_credit_code(raw_credit_code)
        return cls(
            credit_code=normalized_credit_code,
            company_id=generate_company_id(normalized_credit_code),
        )
