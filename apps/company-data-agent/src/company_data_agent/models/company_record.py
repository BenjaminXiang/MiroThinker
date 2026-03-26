"""Canonical company record models used across the pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator

from company_data_agent.identity import normalize_credit_code, validate_company_id


class CompanySource(StrEnum):
    """Known upstream sources for company data provenance."""

    MASTER_LIST = "master_list"
    QIMINGPIAN = "qimingpian"
    WEBSITE = "website"
    PR_NEWS = "pr_news"
    WEB_SEARCH = "web_search"
    MANUAL = "manual"


class EducationRecord(BaseModel):
    """Structured education record for a key person."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    institution: str = Field(min_length=1)
    degree: str | None = None
    year: int | None = None
    field: str | None = None


class KeyPersonnelRecord(BaseModel):
    """Structured representation of a key person mentioned by the company."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    education: list[EducationRecord] = Field(default_factory=list)


class CompanyRecordBase(BaseModel):
    """Shared fields for partial and final company records."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    id: str | None = None
    name: str = Field(min_length=1)
    credit_code: str = Field(min_length=18, max_length=18)
    legal_representative: str | None = None
    registered_capital: str | None = None
    establishment_date: str | None = None
    registered_address: str | None = None
    industry: str | None = None
    business_scope: str | None = None
    product_description: str | None = None
    tech_tags: list[str] = Field(default_factory=list)
    industry_tags: list[str] = Field(default_factory=list)
    financing_round: str | None = None
    financing_amount: str | None = None
    investors: list[str] = Field(default_factory=list)
    patent_count: int | None = None
    team_description: str | None = None
    key_personnel: list[KeyPersonnelRecord] = Field(default_factory=list)
    website: str | None = None
    profile_summary: str | None = None
    profile_embedding: list[float] | None = None
    sources: list[CompanySource] = Field(default_factory=list, min_length=1)
    completeness_score: int | None = None
    last_updated: datetime | None = None
    raw_data_path: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_company_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_company_id(value)

    @field_validator("credit_code")
    @classmethod
    def validate_credit_code(cls, value: str) -> str:
        return normalize_credit_code(value)

    @field_validator("sources")
    @classmethod
    def deduplicate_sources(cls, value: list[CompanySource]) -> list[CompanySource]:
        deduped = list(dict.fromkeys(value))
        if not deduped:
            raise ValueError("sources must contain at least one source")
        return deduped

    @field_validator("tech_tags", "industry_tags", "investors")
    @classmethod
    def deduplicate_string_lists(cls, value: list[str]) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = item.strip()
            if not normalized:
                continue
            if normalized not in seen:
                seen.add(normalized)
                items.append(normalized)
        return items

    @field_validator("profile_embedding")
    @classmethod
    def validate_profile_embedding(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("profile_embedding must not be empty")
        for component in value:
            if not isfinite(component):
                raise ValueError("profile_embedding must contain finite floats only")
        return value

    @field_validator("completeness_score")
    @classmethod
    def validate_completeness_score(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 0 or value > 100:
            raise ValueError("completeness_score must be between 0 and 100")
        return value

    @field_validator("last_updated")
    @classmethod
    def validate_last_updated(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("last_updated must be timezone-aware")
        return value


class PartialCompanyRecord(CompanyRecordBase):
    """Intermediate company record used before final retrieval fields exist."""


class FinalCompanyRecord(CompanyRecordBase):
    """Final record shape required before persistence and downstream handoff."""

    id: str
    profile_summary: str = Field(min_length=1)
    profile_embedding: list[float] = Field(min_length=1)
    completeness_score: int
    last_updated: datetime
