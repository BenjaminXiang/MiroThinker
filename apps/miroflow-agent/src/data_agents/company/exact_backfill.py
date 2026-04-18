from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypeVar

from .import_xlsx import import_company_xlsx
from .models import CompanyImportResult
from .release import CompanyReleaseReport, CompanyReleaseResult, build_company_release


T = TypeVar("T")


def load_company_import_results(
    *,
    workbook_paths: list[Path],
    sheet_name: str = "sheet1",
) -> list[tuple[Path, CompanyImportResult]]:
    return [
        (workbook_path, import_company_xlsx(workbook_path, sheet_name=sheet_name))
        for workbook_path in workbook_paths
    ]


def build_company_release_from_import_results(
    *,
    import_results: list[tuple[Path, CompanyImportResult]],
    now: datetime | None = None,
) -> CompanyReleaseResult:
    results: list[CompanyReleaseResult] = []
    total_input = 0
    for workbook_path, import_result in import_results:
        total_input += len(import_result.records)
        results.append(
            build_company_release(
                records=import_result.records,
                source_file=workbook_path,
                now=now,
            )
        )

    company_records = _merge_models_by_id(
        [record for result in results for record in result.company_records]
    )
    released_objects = _merge_models_by_id(
        [obj for result in results for obj in result.released_objects]
    )
    return CompanyReleaseResult(
        company_records=company_records,
        released_objects=released_objects,
        report=CompanyReleaseReport(
            input_record_count=total_input,
            released_record_count=len(company_records),
        ),
    )


def build_company_release_from_sources(
    *,
    workbook_paths: list[Path],
    sheet_name: str = "sheet1",
    now: datetime | None = None,
) -> CompanyReleaseResult:
    return build_company_release_from_import_results(
        import_results=load_company_import_results(
            workbook_paths=workbook_paths,
            sheet_name=sheet_name,
        ),
        now=now,
    )


def _merge_models_by_id(items: list[T]) -> list[T]:
    merged: dict[str, T] = {}
    for item in items:
        item_id = getattr(item, "id")
        merged[item_id] = item
    return list(merged.values())
