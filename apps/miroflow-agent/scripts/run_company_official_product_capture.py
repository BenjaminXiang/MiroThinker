#!/usr/bin/env python3
"""Capture product-oriented records from company official websites."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable
from urllib.parse import urljoin, urlparse

import psycopg
from psycopg.rows import dict_row
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.import_xlsx import import_company_xlsx  # noqa: E402
from src.data_agents.company.models import CompanyImportRecord  # noqa: E402
from src.data_agents.company.official_product_capture import (  # noqa: E402
    CompanyProductCandidate,
    OfficialSitePage,
    classify_official_capture_failure,
    common_official_material_urls,
    extract_official_source_materials,
    extract_products_from_html,
    needs_javascript_rendering,
    product_to_json,
    select_candidate_material_urls,
    select_candidate_urls,
    select_sitemap_material_urls,
    upsert_company_product,
)
from src.data_agents.company.source_material import CompanySourceMaterial  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402

_DEFAULT_USER_AGENT = "MiroThinker-Company-Product/1.0 (+https://github.com)"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_report_output() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _repo_root() / "logs" / "debug" / f"company_product_capture_{timestamp}.json"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch bounded official company pages and extract product records.",
    )
    parser.add_argument("--input", type=Path, default=_default_input())
    parser.add_argument("--sheet-name", type=str, default="sheet1")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument(
        "--enable-js-render",
        action="store_true",
        help="Use dependency-optional JavaScript rendering when static pages are SPA shells.",
    )
    parser.add_argument(
        "--disable-sitemap-discovery",
        action="store_true",
        help="Do not try /sitemap.xml when homepage navigation has no material links.",
    )
    parser.add_argument(
        "--disable-common-path-discovery",
        action="store_true",
        help="Do not probe common official business paths such as /products.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=_default_report_output())
    parser.add_argument(
        "--company-id",
        action="append",
        default=[],
        help="Only process this canonical company_id from Postgres. Repeat for multiple IDs.",
    )
    parser.add_argument(
        "--enrichment-batch-id",
        default=None,
        help="Optional company_enrichment_batch id for reports/checkpoints.",
    )
    return parser.parse_args(argv)


class CompanyRecordForCapture:
    def __init__(self, *, company_id: str, record: CompanyImportRecord) -> None:
        self.company_id = company_id
        self.record = record


class OfficialFetchResult:
    def __init__(
        self,
        *,
        html: str | None,
        http_status: int | None = None,
        content_type: str | None = None,
        error: str | None = None,
        robots_disallowed: bool = False,
    ) -> None:
        self.html = html
        self.http_status = http_status
        self.content_type = content_type
        self.error = error
        self.robots_disallowed = robots_disallowed


class OfficialCaptureDiagnosticsResult:
    def __init__(
        self,
        *,
        pages: list[OfficialSitePage],
        materials: list[CompanySourceMaterial],
        attempts: list[dict[str, object]],
        failure_reason: str | None,
    ) -> None:
        self.pages = pages
        self.materials = materials
        self.attempts = attempts
        self.failure_reason = failure_reason


FetchHtmlResult = str | OfficialFetchResult | None


def _fetch_html(url: str, *, timeout_seconds: float) -> FetchHtmlResult:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            timeout=timeout_seconds,
        )
    except requests.Timeout as exc:
        return OfficialFetchResult(html=None, error=f"timeout: {exc}")
    except requests.ConnectionError as exc:
        return OfficialFetchResult(html=None, error=f"dns or connection error: {exc}")
    except Exception as exc:
        return OfficialFetchResult(html=None, error=str(exc))

    content_type = response.headers.get("content-type", "")
    if content_type and "html" not in content_type.lower():
        return OfficialFetchResult(
            html=None,
            http_status=response.status_code,
            content_type=content_type,
            error="non_html_content_type",
        )
    if response.encoding is None or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return OfficialFetchResult(
        html=response.text,
        http_status=response.status_code,
        content_type=content_type,
    )


def _render_html(url: str, *, timeout_seconds: float) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=int(timeout_seconds * 1000))
                return page.content()
            finally:
                browser.close()
    except Exception:
        return None


def _coerce_fetch_result(value: FetchHtmlResult) -> OfficialFetchResult:
    if isinstance(value, OfficialFetchResult):
        return value
    return OfficialFetchResult(html=value)


def _capture_products_for_record(
    record: CompanyImportRecord,
    *,
    fetch_html: Callable[[str], FetchHtmlResult],
    max_pages: int,
) -> list[CompanyProductCandidate]:
    products: list[CompanyProductCandidate] = []
    for page in _capture_official_pages_for_record(
        record,
        fetch_html=fetch_html,
        max_pages=max_pages,
    ):
        products.extend(
            extract_products_from_html(
                company_id=f"COMP-{record.normalized_name}",
                company_name=record.name,
                page=page,
            )
        )
    return products


def _capture_official_pages_for_record(
    record: CompanyImportRecord,
    *,
    fetch_html: Callable[[str], FetchHtmlResult],
    max_pages: int,
) -> list[OfficialSitePage]:
    if not record.website or max_pages <= 0:
        return []

    homepage_fetch = _coerce_fetch_result(fetch_html(record.website))
    homepage_html = homepage_fetch.html
    if not homepage_html:
        return []

    material_urls = select_candidate_material_urls(
        base_url=record.website,
        html=homepage_html,
        max_urls=max(0, max_pages - 1),
    )
    if not material_urls:
        material_urls = select_candidate_urls(
            base_url=record.website,
            html=homepage_html,
            max_urls=max(0, max_pages - 1),
        )
    page_urls = [record.website, *material_urls]
    seen: set[str] = set()
    pages: list[OfficialSitePage] = []
    fetched_at = datetime.now(timezone.utc)
    for url in page_urls:
        if url in seen:
            continue
        seen.add(url)
        fetch_result = (
            homepage_fetch
            if url == record.website
            else _coerce_fetch_result(fetch_html(url))
        )
        html = fetch_result.html
        if not html:
            continue
        pages.append(
            OfficialSitePage(
                url=url,
                html=html,
                fetched_at=fetched_at,
                acquisition_method="static" if url == record.website else "static_discovered",
            )
        )
        if len(pages) >= max_pages:
            break
    return pages


def _capture_official_pages_with_diagnostics_for_record(
    record: CompanyImportRecord,
    *,
    fetch_html: Callable[[str], FetchHtmlResult],
    max_pages: int,
    render_html: Callable[[str], str | None] | None = None,
    use_sitemap_discovery: bool = True,
    use_common_path_discovery: bool = True,
) -> tuple[list[OfficialSitePage], list[dict[str, object]], str | None]:
    if not record.website or max_pages <= 0:
        return [], [], classify_official_capture_failure(website=record.website)

    attempts: list[dict[str, object]] = []
    homepage_fetch = _coerce_fetch_result(fetch_html(record.website))
    homepage_html = homepage_fetch.html
    homepage_acquisition_method = "static"
    homepage_failure = classify_official_capture_failure(
        website=record.website,
        html=homepage_html,
        http_status=homepage_fetch.http_status,
        error=homepage_fetch.error,
        robots_disallowed=homepage_fetch.robots_disallowed,
    )
    recoverable_homepage_failure = homepage_failure in {"text_too_short"} and bool(
        homepage_html
    )
    if homepage_failure:
        attempts.append(
            _official_capture_attempt(
                url=record.website,
                acquisition_method="static",
                fetch_result=homepage_fetch,
                status="rejected",
                failure_reason=homepage_failure,
            )
        )
        if homepage_failure == "js_required" and render_html is not None:
            rendered_html = render_html(record.website)
            render_failure = classify_official_capture_failure(
                website=record.website,
                html=rendered_html,
                render_failed=rendered_html is None,
            )
            attempts.append(
                _official_capture_attempt(
                    url=record.website,
                    acquisition_method="js_render",
                    fetch_result=OfficialFetchResult(html=rendered_html),
                    status="accepted" if render_failure is None else "rejected",
                    failure_reason=render_failure,
                )
            )
            if render_failure is not None:
                return [], attempts, render_failure
            homepage_html = rendered_html
            homepage_fetch = OfficialFetchResult(html=rendered_html)
            homepage_acquisition_method = "js_render"
        elif recoverable_homepage_failure:
            pass
        else:
            return [], attempts, homepage_failure
    else:
        attempts.append(
            _official_capture_attempt(
                url=record.website,
                acquisition_method="static",
                fetch_result=homepage_fetch,
                status="accepted",
                failure_reason=None,
            )
        )

    if not homepage_html:
        return [], attempts, "fetch_failed"

    material_urls = select_candidate_material_urls(
        base_url=record.website,
        html=homepage_html,
        max_urls=max(0, max_pages - 1),
    )
    if not material_urls:
        material_urls = select_candidate_urls(
            base_url=record.website,
            html=homepage_html,
            max_urls=max(0, max_pages - 1),
        )
    if not material_urls and use_sitemap_discovery:
        sitemap_url = _default_sitemap_url(record.website)
        sitemap_fetch = _coerce_fetch_result(fetch_html(sitemap_url))
        sitemap_failure = classify_official_capture_failure(
            website=sitemap_url,
            html=sitemap_fetch.html,
            http_status=sitemap_fetch.http_status,
            error=sitemap_fetch.error,
            robots_disallowed=sitemap_fetch.robots_disallowed,
        )
        attempts.append(
            _official_capture_attempt(
                url=sitemap_url,
                acquisition_method="sitemap",
                fetch_result=sitemap_fetch,
                status="accepted" if sitemap_failure is None else "rejected",
                failure_reason=sitemap_failure,
            )
        )
        if sitemap_fetch.html:
            material_urls = select_sitemap_material_urls(
                base_url=record.website,
                sitemap_xml=sitemap_fetch.html,
                max_urls=max(0, max_pages - 1),
            )
    if use_common_path_discovery:
        for common_url in common_official_material_urls(
            base_url=record.website,
            max_urls=max(0, max_pages - 1),
        ):
            if len(material_urls) >= max(0, max_pages - 1):
                break
            if common_url not in material_urls:
                material_urls.append(common_url)

    page_urls = [record.website, *material_urls]
    seen: set[str] = set()
    pages: list[OfficialSitePage] = []
    fetched_at = datetime.now(timezone.utc)
    for url in page_urls:
        if url in seen:
            continue
        seen.add(url)
        fetch_result = (
            homepage_fetch
            if url == record.website
            else _coerce_fetch_result(fetch_html(url))
        )
        html = fetch_result.html
        method = "static" if url == record.website else "static_discovered"
        if url == record.website:
            method = homepage_acquisition_method
        accepted_method = method
        failure = classify_official_capture_failure(
            website=url,
            html=html,
            http_status=fetch_result.http_status,
            error=fetch_result.error,
            robots_disallowed=fetch_result.robots_disallowed,
        )
        if failure == "js_required" and render_html is not None:
            attempts.append(
                _official_capture_attempt(
                    url=url,
                    acquisition_method=method,
                    fetch_result=fetch_result,
                    status="rejected",
                    failure_reason=failure,
                )
            )
            rendered_html = render_html(url)
            failure = classify_official_capture_failure(
                website=url,
                html=rendered_html,
                render_failed=rendered_html is None,
            )
            attempts.append(
                _official_capture_attempt(
                    url=url,
                    acquisition_method="js_render",
                    fetch_result=OfficialFetchResult(html=rendered_html),
                    status="accepted" if failure is None else "rejected",
                    failure_reason=failure,
                )
            )
            html = rendered_html
            if failure is None:
                accepted_method = "js_render"
        elif url != record.website:
            attempts.append(
                _official_capture_attempt(
                    url=url,
                    acquisition_method=method,
                    fetch_result=fetch_result,
                    status="accepted" if failure is None else "rejected",
                    failure_reason=failure,
                )
            )
        if failure is not None or not html:
            continue
        pages.append(
            OfficialSitePage(
                url=url,
                html=html,
                fetched_at=fetched_at,
                acquisition_method=accepted_method,
            )
        )
        if len(pages) >= max_pages:
            break

    if pages:
        return pages, attempts, None
    last_failure = next(
        (
            str(attempt.get("failure_reason"))
            for attempt in reversed(attempts)
            if attempt.get("failure_reason")
        ),
        None,
    )
    return [], attempts, last_failure or "no_relevant_pages"


def _capture_official_materials_for_record(
    record: CompanyImportRecord,
    *,
    company_id: str,
    fetch_html: Callable[[str], FetchHtmlResult],
    max_pages: int,
) -> list[CompanySourceMaterial]:
    result = _capture_official_materials_with_diagnostics_for_record(
        record,
        company_id=company_id,
        fetch_html=fetch_html,
        max_pages=max_pages,
    )
    return result.materials


def _capture_official_materials_with_diagnostics_for_record(
    record: CompanyImportRecord,
    *,
    company_id: str,
    fetch_html: Callable[[str], FetchHtmlResult],
    max_pages: int,
    render_html: Callable[[str], str | None] | None = None,
    use_sitemap_discovery: bool = True,
    use_common_path_discovery: bool = True,
) -> OfficialCaptureDiagnosticsResult:
    pages, attempts, page_failure_reason = (
        _capture_official_pages_with_diagnostics_for_record(
            record,
            fetch_html=fetch_html,
            max_pages=max_pages,
            render_html=render_html,
            use_sitemap_discovery=use_sitemap_discovery,
            use_common_path_discovery=use_common_path_discovery,
        )
    )
    materials = extract_official_source_materials(
        company_id=company_id,
        company_name=record.name,
        pages=pages,
    )
    failure_reason = None if materials else page_failure_reason or "no_relevant_pages"
    return OfficialCaptureDiagnosticsResult(
        pages=pages,
        materials=materials,
        attempts=attempts,
        failure_reason=failure_reason,
    )


def _official_capture_attempt(
    *,
    url: str,
    acquisition_method: str,
    fetch_result: OfficialFetchResult,
    status: str,
    failure_reason: str | None,
) -> dict[str, object]:
    text = ""
    html = fetch_result.html
    if html is not None:
        text = _page_text(html)
    return {
        "url": url,
        "acquisition_method": acquisition_method,
        "status": status,
        "failure_reason": failure_reason,
        "http_status": fetch_result.http_status,
        "content_type": fetch_result.content_type,
        "error": fetch_result.error,
        "robots_disallowed": fetch_result.robots_disallowed,
        "content_length": len(html or ""),
        "text_length": len(text),
        "page_category": _page_category(url),
        "js_required": bool(html and needs_javascript_rendering(html)),
    }


def _default_sitemap_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return urljoin(base_url, "/sitemap.xml")
    return f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"


def _page_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    return " ".join(soup.get_text(" ", strip=True).split())


def _page_category(url: str) -> str:
    lowered = url.lower()
    if "product" in lowered or "产品" in lowered:
        return "product"
    if "solution" in lowered or "方案" in lowered:
        return "solution"
    if (
        "case" in lowered
        or "customer" in lowered
        or "案例" in lowered
        or "客户" in lowered
    ):
        return "case"
    if "news" in lowered or "article" in lowered or "新闻" in lowered or "资讯" in lowered:
        return "news"
    if "about" in lowered or "company" in lowered or "关于" in lowered or "简介" in lowered:
        return "about"
    return "homepage"


def _source_material_to_json(material: CompanySourceMaterial) -> dict[str, object]:
    return {
        "source_id": material.source_id,
        "source_tier": material.source_tier,
        "url": material.url,
        "title": material.title,
        "captured_text": material.captured_text,
        "captured_at": (
            material.captured_at.isoformat(timespec="seconds")
            if material.captured_at
            else None
        ),
        "trust_reason": material.trust_reason,
        "source_judgment_status": material.source_judgment_status,
        "source_judgment_confidence": (
            str(material.source_judgment_confidence)
            if material.source_judgment_confidence is not None
            else None
        ),
        "source_judgment_evidence_span": material.source_judgment_evidence_span,
        "acquisition_method": material.acquisition_method,
        "evidence_span": material.evidence_span,
        "failure_reason": material.failure_reason,
    }


def _rewrite_products_with_company_id(
    products: list[CompanyProductCandidate], company_id: str
) -> list[CompanyProductCandidate]:
    return [
        CompanyProductCandidate(
            company_id=company_id,
            product_name=product.product_name,
            short_description=product.short_description,
            official_product_url=product.official_product_url,
            evidence_span=product.evidence_span,
            confidence=product.confidence,
            quality_status=product.quality_status,
            product_category=product.product_category,
            target_customers=product.target_customers,
            application_scenarios=product.application_scenarios,
            technical_tags=product.technical_tags,
        )
        for product in products
    ]


def _load_company_records_from_database(
    conn,
    *,
    company_ids: tuple[str, ...] = (),
    limit: int | None = None,
) -> list[CompanyRecordForCapture]:
    filters = ["COALESCE(latest_snapshot.website_xlsx, c.website) IS NOT NULL"]
    params: list[object] = []
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        filters.append(f"c.company_id IN ({placeholders})")
        params.extend(company_ids)
    sql = (
        "SELECT c.company_id, c.canonical_name, "
        "       COALESCE(NULLIF(latest_snapshot.project_name, ''), c.canonical_name) AS normalized_name, "
        "       latest_snapshot.industry, "
        "       COALESCE(latest_snapshot.website_xlsx, c.website) AS website "
        "  FROM company c "
        "  LEFT JOIN LATERAL ("
        "      SELECT cs.project_name, cs.industry, cs.website_xlsx "
        "        FROM company_snapshot cs "
        "       WHERE cs.company_id = c.company_id "
        "       ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "       LIMIT 1"
        "  ) latest_snapshot ON true "
        f" WHERE {' AND '.join(filters)} "
        " ORDER BY c.company_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    rows = conn.execute(sql, tuple(params)).fetchall()
    records: list[CompanyRecordForCapture] = []
    for row in rows:
        data = dict(row)
        records.append(
            CompanyRecordForCapture(
                company_id=str(data["company_id"]),
                record=CompanyImportRecord(
                    name=str(data.get("canonical_name") or data["company_id"]),
                    normalized_name=str(data.get("normalized_name") or data.get("canonical_name") or ""),
                    industry=data.get("industry"),
                    website=data.get("website"),
                ),
            )
        )
    return records


def _resolve_company_id_for_record(conn, record: CompanyImportRecord) -> str | None:
    row = conn.execute(
        """
        SELECT company_id
          FROM company
         WHERE canonical_name = %s
            OR registered_name = %s
            OR %s = ANY(aliases)
         ORDER BY last_refreshed_at DESC NULLS LAST, company_id
         LIMIT 1
        """,
        (record.name, record.name, record.normalized_name),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return str(row.get("company_id") or "") or None
    return str(row[0]) if row[0] else None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.input.exists():
        print(
            json.dumps(
                {"input": str(args.input), "error": "input xlsx not found"},
                ensure_ascii=False,
            )
        )
        return 1

    conn = None
    db_records: list[CompanyRecordForCapture] | None = None
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if args.company_id:
        if not dsn:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            return 1
        conn = psycopg.connect(resolve_dsn(dsn), row_factory=dict_row)
        db_records = _load_company_records_from_database(
            conn,
            company_ids=tuple(args.company_id),
            limit=args.limit,
        )
        records = [item.record for item in db_records]
    else:
        import_result = import_company_xlsx(args.input, sheet_name=args.sheet_name)
        records = [record for record in import_result.records if record.website]
        if args.limit is not None:
            records = records[: args.limit]

    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(args.input),
        "enrichment_batch_id": args.enrichment_batch_id,
        "companies_considered": len(records),
        "companies_with_products": 0,
        "official_pages_captured": 0,
        "products_extracted": 0,
        "products_inserted": 0,
        "dry_run": args.dry_run,
        "items": [],
        "source_materials": [],
        "official_capture_attempts": [],
        "official_capture_failures": [],
    }

    if not args.dry_run:
        if not dsn:
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            return 1
        if conn is None:
            conn = psycopg.connect(resolve_dsn(dsn), row_factory=dict_row)

    try:
        render_html = (
            (lambda url: _render_html(url, timeout_seconds=args.timeout_seconds))
            if args.enable_js_render
            else None
        )
        for index, record in enumerate(records):
            resolved_company_id = None
            if conn is not None:
                resolved_company_id = (
                    db_records[index].company_id
                    if db_records is not None
                    else _resolve_company_id_for_record(conn, record)
                )
            material_company_id = resolved_company_id or f"COMP-{record.normalized_name}"
            material_result = _capture_official_materials_with_diagnostics_for_record(
                record,
                company_id=material_company_id,
                fetch_html=lambda url: _fetch_html(
                    url, timeout_seconds=args.timeout_seconds
                ),
                max_pages=args.max_pages,
                render_html=render_html,
                use_sitemap_discovery=not args.disable_sitemap_discovery,
                use_common_path_discovery=not args.disable_common_path_discovery,
            )
            materials = material_result.materials
            report["official_pages_captured"] = int(report["official_pages_captured"]) + len(
                materials
            )
            source_material_items = report["source_materials"]
            assert isinstance(source_material_items, list)
            source_material_items.extend(_source_material_to_json(item) for item in materials)
            capture_attempt_items = report["official_capture_attempts"]
            assert isinstance(capture_attempt_items, list)
            for attempt in material_result.attempts:
                capture_attempt_items.append(
                    {
                        "company_id": material_company_id,
                        "company_name": record.name,
                        **attempt,
                    }
                )
            if material_result.failure_reason:
                capture_failure_items = report["official_capture_failures"]
                assert isinstance(capture_failure_items, list)
                capture_failure_items.append(
                    {
                        "company_id": material_company_id,
                        "company_name": record.name,
                        "website": record.website,
                        "failure_reason": material_result.failure_reason,
                    }
                )

            products = []
            for page in material_result.pages:
                products.extend(
                    extract_products_from_html(
                        company_id=material_company_id,
                        company_name=record.name,
                        page=page,
                    )
                )
            if products:
                report["companies_with_products"] = (
                    int(report["companies_with_products"]) + 1
                )
            report["products_extracted"] = int(report["products_extracted"]) + len(
                products
            )
            if conn is not None and not args.dry_run:
                if resolved_company_id:
                    products = _rewrite_products_with_company_id(
                        products,
                        resolved_company_id,
                    )
                for product in products:
                    upsert_company_product(conn, product)
                    report["products_inserted"] = int(report["products_inserted"]) + 1
                conn.commit()
            report_items = report["items"]
            assert isinstance(report_items, list)
            report_items.extend(product_to_json(product) for product in products)
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
    finally:
        if conn is not None:
            conn.close()

    if str(args.output) == "-":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
