from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PatentImportRecord:
    source_row: int
    sequence_number: str | None
    title: str
    title_en: str | None
    abstract: str | None
    abstract_en: str | None
    applicants: tuple[str, ...]
    patent_number: str | None
    publication_date: date | None
    filing_date: date | None
    patent_type: str | None
    technology_effect_sentence: str | None
    technology_effect_phrases: tuple[str, ...]
    expected_expiry_date: date | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "applicants", tuple(self.applicants))
        object.__setattr__(
            self,
            "technology_effect_phrases",
            tuple(self.technology_effect_phrases),
        )


@dataclass(frozen=True, slots=True)
class PatentImportReport:
    workbook_path: str
    worksheet_title: str
    header_row_index: int
    rows_read: int
    records_parsed: int
    skipped_rows: int
    skip_reasons: dict[str, int]
    read_only_max_row: int
    read_only_max_column: int


@dataclass(frozen=True, slots=True)
class PatentImportResult:
    records: list[PatentImportRecord]
    report: PatentImportReport
