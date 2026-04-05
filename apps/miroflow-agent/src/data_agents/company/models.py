from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FinancingEvent:
    round: str | None = None
    time: str | None = None
    amount: str | None = None
    amount_cny_wan: str | None = None
    ratio: str | None = None
    investor: str | None = None

    def is_empty(self) -> bool:
        return not any(
            (
                self.round,
                self.time,
                self.amount,
                self.amount_cny_wan,
                self.ratio,
                self.investor,
            )
        )


@dataclass(frozen=True, slots=True)
class CompanyImportRecord:
    name: str
    normalized_name: str
    sequence_no: str | None = None
    project_name: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    business: str | None = None
    region: str | None = None
    website: str | None = None
    legal_representative: str | None = None
    registered_capital: str | None = None
    description: str | None = None
    team_raw: str | None = None
    registered_address: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    country: str | None = None
    established_date: str | None = None
    is_high_tech: bool | None = None
    patent_count: int | None = None
    financing_events: tuple[FinancingEvent, ...] = ()
    investors: tuple[str, ...] = ()
    source_row_numbers: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "financing_events", tuple(self.financing_events))
        object.__setattr__(self, "investors", tuple(self.investors))
        object.__setattr__(self, "source_row_numbers", tuple(self.source_row_numbers))

    def completeness_score(self) -> int:
        scalar_values = (
            self.name,
            self.industry,
            self.sub_industry,
            self.business,
            self.region,
            self.website,
            self.legal_representative,
            self.registered_capital,
            self.description,
            self.team_raw,
            self.registered_address,
            self.contact_phone,
            self.contact_email,
            self.country,
            self.established_date,
            self.sequence_no,
            self.project_name,
        )
        score = sum(1 for value in scalar_values if value)
        if self.is_high_tech is not None:
            score += 1
        if self.patent_count is not None:
            score += 1
        score += len(self.financing_events)
        score += len(self.investors)
        return score


@dataclass(frozen=True, slots=True)
class CompanyImportReport:
    source_file: str
    sheet_name: str
    header_row_index: int
    rows_read: int
    rows_empty_skipped: int
    rows_missing_company_name: int
    continuation_rows_merged: int
    orphan_continuation_rows: int
    company_rows_parsed: int
    deduped_records: int
    duplicate_groups: int
    duplicate_records_discarded: int


@dataclass(frozen=True, slots=True)
class CompanyImportResult:
    records: list[CompanyImportRecord]
    report: CompanyImportReport
