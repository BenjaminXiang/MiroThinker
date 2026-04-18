from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypeVar

from .import_xlsx import import_patent_xlsx
from .release import PatentReleaseReport, PatentReleaseResult, build_patent_release


T = TypeVar("T")


def build_patent_release_from_sources(
    *,
    workbook_paths: list[Path],
    company_name_to_id: dict[str, str],
    professor_name_to_id: dict[str, str] | None = None,
    now: datetime | None = None,
) -> PatentReleaseResult:
    results: list[PatentReleaseResult] = []
    total_input = 0
    for workbook_path in workbook_paths:
        import_result = import_patent_xlsx(workbook_path)
        total_input += len(import_result.records)
        results.append(
            build_patent_release(
                records=import_result.records,
                source_file=workbook_path,
                company_name_to_id=company_name_to_id,
                professor_name_to_id=professor_name_to_id,
                now=now,
            )
        )

    patent_records = _merge_models_by_id(
        [record for result in results for record in result.patent_records]
    )
    released_objects = _merge_models_by_id(
        [obj for result in results for obj in result.released_objects]
    )
    return PatentReleaseResult(
        patent_records=patent_records,
        released_objects=released_objects,
        report=PatentReleaseReport(
            input_record_count=total_input,
            released_record_count=len(patent_records),
        ),
    )


def _merge_models_by_id(items: list[T]) -> list[T]:
    merged: dict[str, T] = {}
    for item in items:
        item_id = getattr(item, "id")
        merged[item_id] = item
    return list(merged.values())
