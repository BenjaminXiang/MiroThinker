from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import PatentRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .linkage import link_company_ids, link_professor_ids
from .models import PatentImportRecord


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
    professor_name_to_id: dict[str, str] | None = None,
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
        applicants = list(record.applicants)
        inventors: list[str] = []
        patent = PatentRecord(
            id=build_stable_id(
                "pat",
                record.patent_number or f"{title}|{'|'.join(applicants)}",
            ),
            title=title,
            title_en=record.title_en,
            patent_number=record.patent_number,
            applicants=applicants,
            inventors=inventors,
            patent_type=record.patent_type or "未知类型",
            filing_date=_date_to_iso(record.filing_date),
            publication_date=_date_to_iso(record.publication_date),
            grant_date=None,
            abstract=record.abstract,
            technology_effect=_technology_effect(record),
            ipc_codes=[],
            company_ids=link_company_ids(applicants, company_name_to_id),
            professor_ids=link_professor_ids(inventors, professor_index),
            summary_text=build_summary_text(record),
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


def build_summary_text(record: PatentImportRecord) -> str:
    parts = [f"该专利围绕“{record.title}”展开。"]
    if record.abstract:
        parts.append(record.abstract)
    effect = _technology_effect(record)
    if effect:
        parts.append(f"技术效果重点是{effect}。")
    if record.patent_type:
        parts.append(f"当前记录的专利类型为{record.patent_type}。")
    return _join_and_trim(parts, limit=280)


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


def _join_and_trim(parts: list[str], *, limit: int) -> str:
    text = "".join(part for part in parts if part)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("，。；; ") + "。"
