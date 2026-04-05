from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import CompanyRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .enrichment import build_rule_based_summaries, extract_key_personnel
from .models import CompanyImportRecord


@dataclass(frozen=True, slots=True)
class CompanyReleaseReport:
    input_record_count: int
    released_record_count: int


@dataclass(frozen=True, slots=True)
class CompanyReleaseResult:
    company_records: list[CompanyRecord]
    released_objects: list[ReleasedObject]
    report: CompanyReleaseReport


def build_company_release(
    *,
    records: list[CompanyImportRecord],
    source_file: Path,
    now: datetime | None = None,
) -> CompanyReleaseResult:
    generated_at = now or datetime.now(timezone.utc)
    company_records: list[CompanyRecord] = []
    released_objects: list[ReleasedObject] = []

    for record in records:
        industry = (record.industry or "").strip()
        if not industry:
            continue
        summaries = build_rule_based_summaries(record)
        company = CompanyRecord(
            id=build_stable_id("comp", record.normalized_name),
            name=record.name,
            normalized_name=record.normalized_name,
            industry=industry,
            website=record.website,
            key_personnel=extract_key_personnel(record),
            profile_summary=summaries.profile_summary,
            evaluation_summary=summaries.evaluation_summary,
            technology_route_summary=summaries.technology_route_summary,
            evidence=[
                build_evidence(
                    source_type="xlsx_import",
                    source_file=str(source_file),
                    fetched_at=generated_at,
                    snippet=f"rows={','.join(str(row) for row in record.source_row_numbers)}",
                    confidence=1.0,
                )
            ],
            last_updated=generated_at,
        )
        company_records.append(company)
        released_objects.append(company.to_released_object())

    return CompanyReleaseResult(
        company_records=company_records,
        released_objects=released_objects,
        report=CompanyReleaseReport(
            input_record_count=len(records),
            released_record_count=len(company_records),
        ),
    )


def publish_company_release(
    release_result: CompanyReleaseResult,
    *,
    company_records_path: Path,
    released_objects_path: Path,
) -> None:
    publish_jsonl(company_records_path, release_result.company_records)
    publish_jsonl(released_objects_path, release_result.released_objects)
