from __future__ import annotations

import csv
import io
import json
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.domains import (
    _get_released_object,
    _query_domain_rows,
    _row_to_released_object,
)
from backend.deps import get_pg_conn

router = APIRouter(prefix="/api/export")


class ExportFormat(str, Enum):
    csv = "csv"
    xlsx = "xlsx"


_DOMAIN_HEADERS: dict[str, list[tuple[str, str]]] = {
    "professor": [
        ("id", "ID"),
        ("display_name", "姓名"),
        ("institution", "院校"),
        ("department", "院系"),
        ("title", "职称"),
        ("email", "邮箱"),
        ("research_directions", "研究方向"),
        ("quality_status", "质量状态"),
    ],
    "company": [
        ("id", "ID"),
        ("display_name", "企业名称"),
        ("industry", "行业"),
        ("website", "官网"),
        ("quality_status", "质量状态"),
    ],
    "paper": [
        ("id", "ID"),
        ("display_name", "标题"),
        ("authors", "作者"),
        ("year", "年份"),
        ("venue", "期刊/会议"),
        ("doi", "DOI"),
        ("summary_zh", "中文摘要"),
        ("quality_status", "质量状态"),
    ],
    "patent": [
        ("id", "ID"),
        ("display_name", "标题"),
        ("patent_number", "专利号"),
        ("patent_type", "专利类型"),
        ("applicants", "申请人"),
        ("filing_date", "申请日"),
        ("publication_date", "公开日"),
        ("summary_text", "摘要"),
        ("quality_status", "质量状态"),
    ],
}


def _extract_field(obj: dict[str, Any], field: str) -> str:
    if field == "id":
        return obj["id"]
    if field == "display_name":
        return obj["display_name"]
    if field == "quality_status":
        return obj["quality_status"]

    val = obj["core_facts"].get(field)
    if val is None:
        val = obj["summary_fields"].get(field)
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


@router.get("/{domain}")
def export_domain(
    domain: str,
    format: ExportFormat = ExportFormat.csv,
    ids: str = Query(default=""),
    conn: Any = Depends(get_pg_conn),
) -> StreamingResponse:
    if domain not in _DOMAIN_HEADERS:
        raise HTTPException(status_code=422, detail="Invalid domain")

    objects = _load_export_objects(conn, domain, ids=ids)

    headers_def = _DOMAIN_HEADERS[domain]
    field_keys = [h[0] for h in headers_def]
    header_labels = [h[1] for h in headers_def]

    if format == ExportFormat.csv:
        return _export_csv(objects, field_keys, header_labels, domain)
    else:
        return _export_xlsx(objects, field_keys, header_labels, domain)


def _export_csv(
    objects: list[dict[str, Any]],
    field_keys: list[str],
    header_labels: list[str],
    domain: str,
) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header_labels)
    for obj in objects:
        writer.writerow([_extract_field(obj, key) for key in field_keys])

    content = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{domain}_export.csv"'
        },
    )


def _export_xlsx(
    objects: list[dict[str, Any]],
    field_keys: list[str],
    header_labels: list[str],
    domain: str,
) -> StreamingResponse:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = domain

    ws.append(header_labels)
    for obj in objects:
        ws.append([_extract_field(obj, key) for key in field_keys])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{domain}_export.xlsx"'
        },
    )


def _load_export_objects(
    conn: Any,
    domain: str,
    *,
    ids: str = "",
) -> list[dict[str, Any]]:
    if ids:
        id_list = [item.strip() for item in ids.split(",") if item.strip()]
        objects = [
            _get_released_object(conn, domain, obj_id, include_evidence=True)
            for obj_id in id_list
        ]
        return [obj for obj in objects if obj is not None]

    rows, _ = _query_domain_rows(
        conn,
        domain=domain,
        page=1,
        page_size=1_000_000,
        sort_by="display_name",
        sort_order="asc",
    )
    return [
        _row_to_released_object(domain, row, include_evidence=True)
        for row in rows
    ]
