"""Structure-first Excel analysis for operator uploads.

The upload flow must not flatten every workbook into one text blob. This
module detects the header row, maps columns to a domain's canonical fields,
and returns a domain recommendation before anything is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import io
from typing import Any, Iterable

from openpyxl import load_workbook

_ALIASES: dict[str, dict[str, set[str]]] = {
    "company": {
        "company_name": {"公司名称", "企业名称", "公司", "企业", "名称"},
        "credit_code": {"统一社会信用代码", "社会信用代码", "信用代码"},
        "website": {"网址", "官网", "网站", "website", "url"},
        "description": {"简介", "企业简介", "公司简介", "描述"},
        "industry": {"行业", "行业领域", "所属行业"},
        "region": {"地区", "省份", "城市", "注册地址", "地址"},
        "legal_representative": {"法人", "法人代表", "法定代表人"},
        "established_date": {"成立日期", "成立时间"},
        "contact_phone": {"电话", "联系电话", "企业联系电话"},
        "contact_email": {"邮箱", "联系邮箱", "email"},
    },
    "professor": {
        "name": {"姓名", "教授姓名", "教师姓名", "名字", "name"},
        "school": {"学校", "高校", "单位", "所属学校", "院校"},
        "department": {"院系", "学院", "系", "部门", "所在院系"},
        "title": {"职称", "职位", "职务"},
        "email": {"邮箱", "email", "电子邮箱"},
        "homepage": {"主页", "个人主页", "homepage", "网址"},
        "research": {"研究方向", "研究领域", "方向"},
        "summary": {"简介", "个人简介", "介绍"},
        "paper_count": {"论文数", "论文数量", "发表论文"},
        "citation_count": {"引用数", "引用次数", "被引"},
    },
    "patent": {
        "title": {"专利名称", "专利标题", "名称", "title"},
        "patent_number": {"专利号", "申请号", "公开号", "专利编号"},
        "applicants": {"申请人", "申请单位", "专利权人", "申请人名称"},
        "inventors": {"发明人", "发明者"},
        "filing_date": {"申请日", "申请日期"},
        "publication_date": {"公开日", "公开日期", "公告日"},
        "status": {"法律状态", "状态", "专利状态"},
        "abstract": {"摘要", "专利摘要"},
        "patent_type": {"专利类型", "类型"},
    },
    "paper": {
        "title": {"论文标题", "标题", "题目", "论文题目", "title"},
        "doi": {"doi", "数字对象标识"},
        "year": {"年份", "发表年份", "年", "year"},
        "venue": {"期刊", "会议", "发表期刊", "venue", "期刊名称"},
        "authors": {"作者", "作者列表", "authors"},
        "abstract": {"摘要", "abstract"},
        "citation_count": {"引用数", "引用次数", "被引", "citation"},
        "arxiv_id": {"arxiv", "arxiv_id", "arxiv id"},
    },
}

_DOMAIN_LABEL = {
    "company": "企业",
    "professor": "教授",
    "patent": "专利",
    "paper": "论文",
}


def _norm(value: Any) -> str:
    return "".join(
        str(value or "").strip().lower().replace(" ", "").replace("\n", "").split()
    )


def _alias_lookup(domain: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for field_name, aliases in _ALIASES[domain].items():
        for alias in aliases:
            lookup[_norm(alias)] = field_name
    return lookup


_LOOKUPS = {domain: _alias_lookup(domain) for domain in _ALIASES}


@dataclass(frozen=True)
class ColumnMapping:
    source: str
    field: str
    source_index: int = 0


@dataclass(frozen=True)
class SheetAnalysis:
    domain: str
    domain_label: str
    confidence: str
    sheet_name: str
    header_row: int
    headers: tuple[str, ...]
    mapping: tuple[ColumnMapping, ...]
    row_count: int
    sample_rows: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkbookAnalysis:
    best: SheetAnalysis
    alternatives: tuple[SheetAnalysis, ...] = ()
    sheets: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


def _mapping_for_domain(headers: Iterable[Any], domain: str) -> list[ColumnMapping]:
    lookup = _LOOKUPS[domain]
    header_list = list(headers)
    normalized = [_norm(header) for header in header_list]
    mapping: list[ColumnMapping] = []
    for index, header in enumerate(normalized):
        if not header:
            continue
        field = lookup.get(header)
        if field is None:
            # allow a header that contains exactly one known alias
            for alias, candidate in lookup.items():
                if alias and alias in header:
                    field = candidate
                    break
        if field is not None:
            mapping.append(
                ColumnMapping(
                    source=str(header_list[index]) if index < len(header_list) else "",
                    field=field,
                    source_index=index,
                )
            )
    return mapping


def _match_domain(headers: Iterable[Any]) -> tuple[str, list[ColumnMapping]]:
    best_domain = "unknown"
    best_mapping: list[ColumnMapping] = []
    for domain in _LOOKUPS:
        mapping = _mapping_for_domain(headers, domain)
        if len(mapping) > len(best_mapping):
            best_domain = domain
            best_mapping = mapping
    return best_domain, best_mapping


def _confidence(mapping: list[ColumnMapping], header_count: int, second: int) -> str:
    if len(mapping) < 2:
        return "low"
    coverage = len(mapping) / max(1, header_count)
    if coverage >= 0.4 and len(mapping) >= 3 and len(mapping) >= second + 2:
        return "high"
    if coverage >= 0.25:
        return "medium"
    return "low"


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def analyze_workbook(data: bytes) -> WorkbookAnalysis:
    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet_analyses: list[SheetAnalysis] = []
        for sheet in workbook.worksheets:
            headers: list[Any] = []
            header_row = 0
            best_matches = 0
            rows = list(sheet.iter_rows(min_row=1, max_row=12, values_only=True))
            for index, row in enumerate(rows):
                domain, mapping = _match_domain(row)
                if len(mapping) > best_matches:
                    best_matches = len(mapping)
                    headers = list(row)
                    header_row = index + 1
            if header_row == 0:
                continue
            domain, mapping = _match_domain(headers)
            if domain == "unknown":
                continue
            mappings = {name: _mapping_for_domain(headers, name) for name in _LOOKUPS}
            second = max(
                (len(value) for name, value in mappings.items() if name != domain),
                default=0,
            )
            data_rows = max(0, (sheet.max_row or 0) - header_row)
            sample: list[dict[str, Any]] = []
            for row in sheet.iter_rows(
                min_row=header_row + 1,
                max_row=min(header_row + 3, sheet.max_row or 0),
                values_only=True,
            ):
                values = {
                    item.field: _cell(row[item.source_index])
                    for item in mapping
                    if item.source_index < len(row)
                    and row[item.source_index] is not None
                    and str(row[item.source_index]).strip()
                }
                if values:
                    sample.append(values)
            warnings = ()
            required = {
                "company": "company_name",
                "professor": "name",
                "patent": "title",
                "paper": "title",
            }[domain]
            if not any(item.field == required for item in mapping):
                warnings = (f"缺少关键字段 {required}",)
            sheet_analyses.append(
                SheetAnalysis(
                    domain=domain,
                    domain_label=_DOMAIN_LABEL[domain],
                    confidence=_confidence(mapping, len(headers), second),
                    sheet_name=sheet.title,
                    header_row=header_row,
                    headers=tuple(str(value or "") for value in headers),
                    mapping=tuple(mapping),
                    row_count=data_rows,
                    sample_rows=tuple(sample),
                    warnings=warnings,
                )
            )
        if not sheet_analyses:
            raise ValueError(
                "no sheet looks like a company/professor/patent/paper table"
            )
        sheet_analyses.sort(
            key=lambda item: (len(item.mapping), item.row_count), reverse=True
        )
        return WorkbookAnalysis(
            best=sheet_analyses[0],
            alternatives=tuple(sheet_analyses[1:]),
            sheets=tuple(sheet.title for sheet in workbook.worksheets),
        )
    finally:
        workbook.close()


def iter_structured_rows(
    analysis: SheetAnalysis,
    data: bytes,
) -> Iterable[dict[str, Any]]:
    """Yield one canonical-field dict per data row of the analysed sheet."""

    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet = workbook[analysis.sheet_name]
        by_index = {item.source_index: item.field for item in analysis.mapping}
        for row in sheet.iter_rows(
            min_row=analysis.header_row + 1,
            max_row=sheet.max_row or 0,
            values_only=True,
        ):
            values: dict[str, Any] = {}
            for index, field_name in by_index.items():
                if index < len(row):
                    value = _cell(row[index])
                    if value is not None and str(value).strip():
                        values[field_name] = value
            if values:
                yield values
    finally:
        workbook.close()


def stable_upload_id(prefix: str, identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


__all__ = [
    "ColumnMapping",
    "SheetAnalysis",
    "WorkbookAnalysis",
    "analyze_workbook",
    "iter_structured_rows",
    "stable_upload_id",
]
