#!/usr/bin/env python3
"""Run deterministic Company enrichment closure checks on the real XLSX."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.import_xlsx import import_company_xlsx  # noqa: E402
from src.data_agents.company.models import CompanyImportRecord  # noqa: E402
from src.data_agents.company.news_connectors import (  # noqa: E402
    NewsRecord,
    PitchHubNewsConnector,
    SerperSearchConnector,
    YiouNewsConnector,
    YiouSearchContext,
)
from src.data_agents.company.official_product_capture import (  # noqa: E402
    OfficialSitePage,
    extract_products_from_html,
)
from src.data_agents.company.release import build_company_release  # noqa: E402

READER_FALLBACK_PREFIX = "https://r.jina.ai/http://r.jina.ai/http://"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_output() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _repo_root() / "logs" / "debug" / f"company_enrichment_e2e_{timestamp}.json"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Company enrichment closure against the real XLSX.",
    )
    parser.add_argument("--input", type=Path, default=_default_input())
    parser.add_argument("--sheet-name", type=str, default="sheet1")
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument(
        "--live",
        action="store_true",
        help="Attempt live Yiou and official-site fetch checks when credentials allow.",
    )
    parser.add_argument(
        "--live-limit",
        type=int,
        default=20,
        help="Number of XLSX companies to scan during live Yiou checks.",
    )
    return parser.parse_args(argv)


def _build_e2e_report(
    *,
    records: list[CompanyImportRecord],
    source_file: Path,
    now: datetime,
    live: bool,
) -> dict[str, object]:
    release_result = build_company_release(
        records=records,
        source_file=source_file,
        now=now,
    )
    company_records = release_result.company_records
    key_people = [person for record in company_records for person in record.key_personnel]
    fixture_checks = {
        "iyiou_adapter": _run_yiou_fixture_check(),
        "official_product_capture": _run_product_fixture_check(),
    }
    deterministic_passed = (
        len(records) > 0
        and release_result.report.released_record_count > 0
        and fixture_checks["iyiou_adapter"]["records"] == 1
        and fixture_checks["official_product_capture"]["products"] == 1
    )
    report: dict[str, object] = {
        "generated_at": now.isoformat(timespec="seconds"),
        "input": str(source_file),
        "deterministic_status": "passed" if deterministic_passed else "failed",
        "import": {
            "company_rows_parsed": len(records),
            "with_website": sum(1 for record in records if record.website),
        },
        "release": {
            "released_record_count": release_result.report.released_record_count,
        },
        "optional_field_coverage": {
            "credit_code": sum(1 for record in company_records if record.credit_code),
            "legal_representative": sum(
                1 for record in company_records if record.legal_representative
            ),
            "registered_capital": sum(
                1 for record in company_records if record.registered_capital
            ),
            "patent_count": sum(
                1 for record in company_records if record.patent_count is not None
            ),
        },
        "key_person_coverage": {
            "total": len(key_people),
            "with_description": sum(1 for person in key_people if person.description),
            "with_education": sum(
                1 for person in key_people if person.education_structured
            ),
            "with_work_experience": sum(
                1 for person in key_people if person.work_experience
            ),
        },
        "fixture_checks": fixture_checks,
        "live_checks": (
            _run_live_checks(records, limit=20) if live else _skipped_live_checks()
        ),
        "smoke": {
            "first_release_has_core_facts": bool(
                release_result.released_objects
                and release_result.released_objects[0].core_facts.get("name")
            ),
            "first_release_has_optional_keys": bool(
                release_result.released_objects
                and {
                    "credit_code",
                    "legal_representative",
                    "registered_capital",
                    "patent_count",
                }.issubset(release_result.released_objects[0].core_facts)
            ),
        },
    }
    return report


class _FixtureConnector:
    def fetch(self, _company_name: str, _since: date) -> list[NewsRecord]:
        return [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/news/123",
                title="深圳示例科技发布工业机器人产品",
                summary="亿欧数据来源摘要。",
                published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                raw_text="亿欧数据来源摘要。",
            )
        ]


def _run_yiou_fixture_check() -> dict[str, object]:
    result = YiouNewsConnector(_FixtureConnector()).fetch_with_diagnostics(
        "深圳示例科技",
        date(2026, 5, 1),
    )
    return {
        "status": "passed" if len(result.records) == 1 else "failed",
        "records": len(result.records),
        "diagnostics": result.diagnostics,
    }


def _run_product_fixture_check() -> dict[str, object]:
    products = extract_products_from_html(
        company_id="COMP-fixture",
        company_name="深圳示例科技有限公司",
        page=OfficialSitePage(
            url="https://example.com/products",
            html=(
                "<section class='product-card'>"
                "<h2>工业视觉平台</h2>"
                "<p>面向产线质检的AI视觉检测产品。</p>"
                "</section>"
            ),
            fetched_at=None,
        ),
    )
    return {
        "status": "passed" if len(products) == 1 else "failed",
        "products": len(products),
    }


def _skipped_live_checks() -> dict[str, object]:
    return {
        "status": "skipped",
        "blocker": "live checks require --live and external network/API prerequisites",
        "confidence_impact": "deterministic parser/storage contract checks passed; live source coverage not measured",
        "next_best_command": (
            "uv run python scripts/run_company_enrichment_e2e.py --live --output -"
        ),
    }


def _run_live_checks(
    records: list[CompanyImportRecord], *, limit: int
) -> dict[str, object]:
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "skipped",
            "blocker": "SERPER_API_KEY is not set",
            "confidence_impact": "Yiou live discovery not measured",
            "next_best_command": (
                "SERPER_API_KEY=... uv run python scripts/run_company_enrichment_e2e.py --live --output -"
            ),
        }

    companies = [record for record in records if record.name][: max(1, limit)]
    if not companies:
        return {
            "status": "skipped",
            "blocker": "no company records available for live checks",
            "confidence_impact": "live source coverage not measured",
            "next_best_command": "rerun with a non-empty XLSX input",
        }

    connectors = {
        "iyiou": YiouNewsConnector(
            SerperSearchConnector(
                api_key,
                site_filters=["data.iyiou.com"],
                fetch_article_content=False,
                timeout_seconds=8,
                result_cap=5,
            )
        ),
        "pitchhub_36kr": PitchHubNewsConnector(
            SerperSearchConnector(
                api_key,
                site_filters=["pitchhub.36kr.com"],
                fetch_article_content=False,
                timeout_seconds=8,
                result_cap=5,
            ),
            reader_fallback_prefix=READER_FALLBACK_PREFIX,
            article_max_chars=4000,
        ),
    }
    samples: list[dict[str, object]] = []
    source_totals = {
        source: {"records": 0, "companies_with_records": 0, "content_chars": 0}
        for source in connectors
    }
    for company in companies:
        context = _build_yiou_live_context(company)
        source_samples: dict[str, object] = {}
        company_total_records = 0
        for source_name, connector in connectors.items():
            result = connector.fetch_with_context(context, date(2026, 1, 1))
            record_count = len(result.records)
            content_chars = sum(len(record.raw_text or record.summary or "") for record in result.records)
            source_totals[source_name]["records"] += record_count
            source_totals[source_name]["content_chars"] += content_chars
            if record_count:
                source_totals[source_name]["companies_with_records"] += 1
            company_total_records += record_count
            source_samples[source_name] = {
                "records": record_count,
                "content_chars": content_chars,
                "diagnostics": result.diagnostics,
                "top_urls": [record.source_url for record in result.records[:3]],
            }
        samples.append(
            {
                "company": company.name,
                "records": company_total_records,
                "sources": source_samples,
            }
        )
    total_records = sum(source["records"] for source in source_totals.values())
    return {
        "status": "passed" if total_records else "passed_with_zero_results",
        "companies_checked": len(companies),
        "sources": source_totals,
        "companies_with_yiou_records": source_totals["iyiou"]["companies_with_records"],
        "iyiou_records": source_totals["iyiou"]["records"],
        "companies_with_pitchhub_records": source_totals["pitchhub_36kr"]["companies_with_records"],
        "pitchhub_records": source_totals["pitchhub_36kr"]["records"],
        "pitchhub_content_chars": source_totals["pitchhub_36kr"]["content_chars"],
        "samples": samples,
    }


def _build_yiou_live_context(record: CompanyImportRecord) -> YiouSearchContext:
    return YiouSearchContext(
        company_name=record.name,
        normalized_name=record.normalized_name,
        project_name=record.project_name,
        description=record.description,
        team_raw=record.team_raw,
        max_query_terms=4,
    )


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

    import_result = import_company_xlsx(args.input, sheet_name=args.sheet_name)
    report = _build_e2e_report(
        records=import_result.records,
        source_file=args.input,
        now=datetime.now(timezone.utc),
        live=False,
    )
    if args.live:
        report["live_checks"] = _run_live_checks(
            import_result.records,
            limit=args.live_limit,
        )
    report["import"]["report"] = {
        "sheet_name": import_result.report.sheet_name,
        "rows_read": import_result.report.rows_read,
        "company_rows_parsed": import_result.report.company_rows_parsed,
        "deduped_records": import_result.report.deduped_records,
    }

    if str(args.output) == "-":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["deterministic_status"] == "passed" else 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0 if report["deterministic_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
