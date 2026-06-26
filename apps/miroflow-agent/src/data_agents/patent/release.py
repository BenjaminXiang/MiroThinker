from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.data_agents.contracts import PatentRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .import_xlsx import _split_tokens
from .linkage import link_company_ids, link_professor_ids
from .models import PatentImportRecord
from .quality_promotion import (
    NEEDS_ENRICHMENT,
    PatentEnrichmentSignals,
    evaluate_patent_promotion,
)
from .summary_llm import (
    PatentSummaryMethod,
    generate_patent_summary_text,
)
from .type_inference import infer_patent_type


@dataclass(frozen=True, slots=True)
class PatentReleaseReport:
    input_record_count: int
    released_record_count: int


@dataclass(frozen=True, slots=True)
class PatentReleaseResult:
    patent_records: list[PatentRecord]
    released_objects: list[ReleasedObject]
    report: PatentReleaseReport


def build_patent_release(
    *,
    records: list[PatentImportRecord],
    source_file: Path,
    company_name_to_id: dict[str, str],
    company_aliases_map: dict[str, str] | None = None,
    professor_name_to_id: dict[str, str] | None = None,
    llm_client: Any | None = None,
    now: datetime | None = None,
) -> PatentReleaseResult:
    generated_at = now or datetime.now(timezone.utc)
    patent_records: list[PatentRecord] = []
    released_objects: list[ReleasedObject] = []
    professor_index = professor_name_to_id or {}

    for record in records:
        title = record.title.strip()
        if not title:
            continue
        applicants = _split_applicant_tokens(record.applicants)
        inventors: list[str] = []
        summary_text, summary_text_method = build_summary_text(
            record,
            llm_client=llm_client,
        )
        company_link_candidates = link_company_ids(
            applicants,
            company_name_to_id,
            company_aliases_map=company_aliases_map,
        )
        patent_type = infer_patent_type(
            record.patent_number,
            current_type=record.patent_type,
        )
        patent = PatentRecord(
            id=build_stable_id(
                "pat",
                record.patent_number or f"{title}|{'|'.join(applicants)}",
            ),
            title=title,
            title_en=record.title_en,
            patent_number=record.patent_number,
            identity_status=_identity_status_for_patent_number(record.patent_number),
            applicants=applicants,
            inventors=inventors,
            patent_type=patent_type or "未知类型",
            filing_date=_date_to_iso(record.filing_date),
            publication_date=_date_to_iso(record.publication_date),
            grant_date=None,
            abstract=record.abstract,
            technology_effect=_technology_effect(record),
            ipc_codes=[],
            company_ids=[candidate[0] for candidate in company_link_candidates],
            professor_ids=link_professor_ids(inventors, professor_index),
            summary_text=summary_text,
            summary_text_method=summary_text_method,
            evidence=[
                build_evidence(
                    source_type="xlsx_import",
                    source_file=str(source_file),
                    fetched_at=generated_at,
                    snippet=f"row={record.source_row}",
                    confidence=1.0,
                )
            ],
            last_updated=generated_at,
            quality_status=_calculate_quality_status(
                title_clean=title,
                patent_number=record.patent_number,
                patent_type=patent_type,
                applicants_parsed=applicants,
                inventors_parsed=inventors,
                filing_date=record.filing_date,
                grant_date=None,
                publication_date=record.publication_date,
            ),
        )
        patent_records.append(patent)
        released_objects.append(patent.to_released_object())

    return PatentReleaseResult(
        patent_records=patent_records,
        released_objects=released_objects,
        report=PatentReleaseReport(
            input_record_count=len(records),
            released_record_count=len(patent_records),
        ),
    )


def build_summary_text(
    record: PatentImportRecord,
    *,
    llm_client: Any | None = None,
) -> tuple[str, PatentSummaryMethod]:
    return generate_patent_summary_text(record, llm_client=llm_client)


_PATENT_TYPE_CANONICAL = {"发明", "实用新型", "外观", "PCT", "其他"}


def _normalize_patent_type_for_canonical(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "实用新型" in text:
        return "实用新型"
    if "外观" in text:
        return "外观"
    if "发明" in text:
        return "发明"
    if "PCT" in text or "pct" in text.lower():
        return "PCT"
    if text in {"其他", "其它"}:
        return "其他"
    return None


def record_to_patent_dict(record: PatentRecord) -> dict[str, object]:
    applicants_parsed = [
        str(item).strip() for item in record.applicants if str(item).strip()
    ]
    inventors_parsed = [
        str(item).strip() for item in record.inventors if str(item).strip()
    ]
    filing_date = _date_from_iso(record.filing_date)
    patent_type = infer_patent_type(
        record.patent_number,
        current_type=record.patent_type,
    )

    return {
        "patent_id": record.id,
        "patent_number": record.patent_number,
        "title_clean": record.title.strip(),
        "title_raw": record.title.strip(),
        "title_en": record.title_en,
        "applicants_raw": "；".join(applicants_parsed) if applicants_parsed else None,
        "applicants_parsed": applicants_parsed,
        "inventors_raw": "；".join(inventors_parsed) if inventors_parsed else None,
        "inventors_parsed": inventors_parsed,
        "filing_date": filing_date,
        "publication_date": _date_from_iso(record.publication_date),
        "grant_date": _date_from_iso(record.grant_date),
        "patent_type": _normalize_patent_type_for_canonical(patent_type),
        "status": None,
        "abstract_clean": record.abstract,
        "technology_effect": record.technology_effect,
        "ipc_codes": list(record.ipc_codes),
        "summary_text": record.summary_text,
        "summary_text_method": record.summary_text_method,
        "identity_status": _identity_status_for_patent_number(record.patent_number),
        "quality_status": _calculate_quality_status(
            title_clean=record.title,
            patent_number=record.patent_number,
            patent_type=patent_type,
            applicants_parsed=applicants_parsed,
            inventors_parsed=inventors_parsed,
            filing_date=filing_date,
            grant_date=_date_from_iso(record.grant_date),
            publication_date=_date_from_iso(record.publication_date),
        ),
        "first_seen_at": record.last_updated,
        "updated_at": record.last_updated,
    }


def _identity_status_for_patent_number(patent_number: str | None) -> str:
    if patent_number and patent_number.strip():
        return "confirmed"
    return "unverified"


def publish_patent_release(
    release_result: PatentReleaseResult,
    *,
    patent_records_path: Path,
    released_objects_path: Path,
) -> None:
    publish_jsonl(patent_records_path, release_result.patent_records)
    publish_jsonl(released_objects_path, release_result.released_objects)


def _date_to_iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _technology_effect(record: PatentImportRecord) -> str | None:
    if record.technology_effect_sentence:
        return record.technology_effect_sentence
    if record.technology_effect_phrases:
        return "、".join(record.technology_effect_phrases)
    return None


def _split_applicant_tokens(applicants: tuple[str, ...] | list[str]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for applicant in applicants:
        for token in _split_tokens(applicant):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _calculate_quality_status(
    *,
    title_clean: str | None,
    patent_number: str | None,
    patent_type: str | None,
    applicants_parsed: list[str],
    inventors_parsed: list[str],
    filing_date: date | str | None,
    grant_date: date | str | None,
    publication_date: date | str | None,
) -> str:
    decision = evaluate_patent_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=PatentEnrichmentSignals(
            has_patent_number=bool((patent_number or "").strip()),
            has_title=bool((title_clean or "").strip()),
            has_patent_type=bool(_normalize_patent_type_for_canonical(patent_type)),
            has_any_date=bool(filing_date or grant_date or publication_date),
            has_applicants_or_inventors=bool(applicants_parsed or inventors_parsed),
            xlsx_merged=True,
        ),
    )
    return decision.next_status


def _date_from_iso(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
