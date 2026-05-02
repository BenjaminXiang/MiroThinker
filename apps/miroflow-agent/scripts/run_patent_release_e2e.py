#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.import_xlsx import import_company_xlsx
from src.data_agents.company.release import build_company_release
from src.data_agents.patent.canonical_writer import (
    upsert_company_patent_link,
    upsert_patent,
)
from src.data_agents.patent.exact_backfill import build_patent_release_from_sources
from src.data_agents.patent.import_xlsx import import_patent_xlsx
from src.data_agents.patent.linkage import link_company_ids
from src.data_agents.patent.release import publish_patent_release
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_patent_input() -> Path:
    return _repo_root() / "docs" / "2025-12-05 专利.xlsx"


def _default_company_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_supplement_patent_inputs() -> list[Path]:
    path = _repo_root() / "docs" / "source_backfills" / "patent_exact_identifier_supplement.xlsx"
    return [path] if path.exists() else []


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"patent_release_e2e_{timestamp}"
    return (
        output_dir / "patent_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "report.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run patent import + release e2e and emit release artifacts.",
    )
    parser.add_argument("--patent-input", type=Path, default=_default_patent_input())
    parser.add_argument("--company-input", type=Path, default=_default_company_input())
    parser.add_argument("--patent-output", type=Path, default=None)
    parser.add_argument("--released-output", type=Path, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST"),
        help="Optional Postgres DSN. If omitted, the script emits JSONL only.",
    )
    parser.add_argument(
        "--skip-postgres",
        action="store_true",
        help="Emit release artifacts without writing patent/company_patent_link rows.",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Use fallback patent summary templates instead of the LLM summary call.",
    )
    parser.add_argument(
        "--supplement-patent-input",
        type=Path,
        action="append",
        default=None,
        help="Optional extra patent workbook(s) with exact-identifier backfills.",
    )
    args = parser.parse_args(argv)

    patent_output, released_output, report_output = _default_output_paths()
    if args.patent_output is not None:
        patent_output = args.patent_output
    if args.released_output is not None:
        released_output = args.released_output
    if args.report_output is not None:
        report_output = args.report_output

    supplement_patent_inputs = (
        args.supplement_patent_input
        if args.supplement_patent_input is not None
        else _default_supplement_patent_inputs()
    )
    patent_inputs = [args.patent_input, *supplement_patent_inputs]
    patent_import_reports = [asdict(import_patent_xlsx(path).report) for path in patent_inputs]
    company_import_result = import_company_xlsx(args.company_input, sheet_name="sheet1")
    company_release_result = build_company_release(
        records=company_import_result.records,
        source_file=args.company_input,
    )
    company_name_to_id: dict[str, str] = {}
    for record in company_release_result.company_records:
        company_name_to_id.setdefault(record.name, record.id)
        company_name_to_id.setdefault(record.normalized_name, record.id)
    llm_client = None if args.skip_llm else _open_llm_client()
    patent_release_result = build_patent_release_from_sources(
        workbook_paths=patent_inputs,
        company_name_to_id=company_name_to_id,
        llm_client=llm_client,
        now=datetime.now(timezone.utc),
    )
    publish_patent_release(
        patent_release_result,
        patent_records_path=patent_output,
        released_objects_path=released_output,
    )
    postgres_write_summary: dict[str, Any]
    if args.skip_postgres or not args.database_url:
        postgres_write_summary = {
            "status": "skipped",
            "reason": "skip_postgres" if args.skip_postgres else "database_url_missing",
        }
    else:
        conn = _open_database_connection(args.database_url)
        try:
            postgres_write_summary = _write_release_to_postgres(
                conn,
                patent_release_result=patent_release_result,
                company_name_to_id=company_name_to_id,
                patent_inputs=patent_inputs,
                company_input=args.company_input,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "patent_inputs": [str(path) for path in patent_inputs],
        "company_input": str(args.company_input),
        "patent_import_summaries": patent_import_reports,
        "patent_release_summary": asdict(patent_release_result.report),
        "postgres_write_summary": postgres_write_summary,
        "outputs": {
            "patent_records_jsonl": str(patent_output),
            "released_objects_jsonl": str(released_output),
        },
    }

    if str(report_output) == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report_output)
    return 0


def _open_database_connection(url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_llm_client():
    _clear_https_proxy_env()
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    return OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"],
        timeout=90.0,
    )


def _write_release_to_postgres(
    conn,
    *,
    patent_release_result,
    company_name_to_id: dict[str, str],
    patent_inputs: list[Path],
    company_input: Path,
) -> dict[str, Any]:
    run_id = open_pipeline_run(
        conn,
        run_kind="import_xlsx",
        run_scope={
            "domain": "patent",
            "patent_inputs": [str(path) for path in patent_inputs],
            "company_input": str(company_input),
        },
        triggered_by="run_patent_release_e2e",
    )
    patents_written = 0
    link_candidates = 0
    links_written = 0
    link_errors = 0
    try:
        for record in patent_release_result.patent_records:
            upsert_patent(conn, record=record, run_id=run_id)
            patents_written += 1
            for company_id, evidence_source_type, match_reason in link_company_ids(
                record.applicants,
                company_name_to_id,
            ):
                link_candidates += 1
                try:
                    upsert_company_patent_link(
                        conn,
                        patent_id=record.id,
                        company_id=company_id,
                        link_role="applicant",
                        evidence_source_type=evidence_source_type,
                        match_reason=match_reason,
                    )
                except Exception:  # noqa: BLE001 - one unmapped FK must not drop patent rows
                    link_errors += 1
                    continue
                links_written += 1
        close_pipeline_run(
            conn,
            run_id,
            status="partial" if link_errors else "succeeded",
            items_processed=patents_written,
            items_failed=link_errors or None,
        )
    except Exception as exc:
        close_pipeline_run(
            conn,
            run_id,
            status="failed",
            items_processed=patents_written,
            items_failed=link_errors or None,
            error_summary={"message": str(exc)[:500]},
        )
        raise

    return {
        "status": "partial" if link_errors else "succeeded",
        "run_id": str(run_id),
        "patents_written": patents_written,
        "company_patent_link_candidates": link_candidates,
        "company_patent_links_written": links_written,
        "company_patent_link_errors": link_errors,
    }


def _clear_https_proxy_env() -> None:
    for key in ("https_proxy", "HTTPS_PROXY"):
        os.environ.pop(key, None)


if __name__ == "__main__":
    raise SystemExit(main())
