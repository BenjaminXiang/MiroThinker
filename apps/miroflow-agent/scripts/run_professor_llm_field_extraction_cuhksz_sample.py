#!/usr/bin/env python
"""Bounded CUHK-SZ L2 professor field extraction apply + measurement."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.canonical_writer import _upsert_fact  # noqa: E402
from src.data_agents.professor.llm_field_extractor import (  # noqa: E402
    LLMExtractedProfileFact,
    ProfessorFieldExtractionInput,
    build_gemma4_llm_client,
    extract_llm_profile_fields,
    normalize_profile_text,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)


DEFAULT_INSTITUTION = "香港中文大学（深圳）"
DEFAULT_LIMIT = 12
FIELD_TO_FACT_TYPE = {
    "research_directions": "research_topic",
    "education": "education",
    "academic_position": "academic_position",
    "work_experience": "work_experience",
    "award": "award",
    "contact": "contact",
}
FACT_TYPE_TO_FIELD = {
    fact_type: field for field, fact_type in FIELD_TO_FACT_TYPE.items()
}
MEASURED_FIELDS = (
    "research_directions",
    "education",
    "academic_position",
    "work_experience",
    "award",
    "contact",
    "profile_summary",
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = (
        args.database_url
        or os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_DSN")
    )
    if not dsn:
        sys.stderr.write("DATABASE_URL, POSTGRES_DSN, or --database-url is required.\n")
        return 2
    if args.write and "miroflow_real" in dsn and not args.confirm_real_db:
        sys.stderr.write(
            "--confirm-real-db is required when writing to miroflow_real.\n"
        )
        return 2

    with psycopg.connect(resolve_dsn(dsn), row_factory=dict_row) as conn:
        payload = run(
            conn=conn,
            institution=args.institution,
            limit=args.limit,
            write=args.write,
            input_cost_per_1m=args.input_cost_per_1m,
            output_cost_per_1m=args.output_cost_per_1m,
        )
        if args.write:
            conn.commit()

    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    )
    return 0


def run(
    *,
    conn: psycopg.Connection,
    institution: str,
    limit: int,
    write: bool,
    input_cost_per_1m: float,
    output_cost_per_1m: float,
) -> dict[str, Any]:
    rows = _load_sample_rows(conn, institution=institution, limit=limit)
    client, model, extra_body, settings = build_gemma4_llm_client()

    run_id = None
    if write:
        run_id = open_pipeline_run(
            conn,
            run_kind="backfill_real",
            run_scope={
                "slice": "professor-profile-field-completion-pipeline:L2",
                "source": "llm_extraction",
                "institution": institution,
                "limit": limit,
                "sample_professors": [str(row["professor_id"]) for row in rows],
            },
            triggered_by=Path(__file__).name,
        )

    row_reports: list[dict[str, Any]] = []
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    llm_calls = 0
    inserted_total = 0
    failed_total = 0

    try:
        for row in rows:
            report = _process_row(
                conn,
                row=row,
                run_id=run_id or "00000000-0000-0000-0000-000000000000",
                llm_client=client,
                llm_model=model,
                extra_body=extra_body,
                write=write,
            )
            row_reports.append(report)
            if report["llm_called"]:
                llm_calls += 1
            usage = report["usage"]
            for key in usage_totals:
                usage_totals[key] += int(usage.get(key) or 0)
            inserted_total += int(report["inserted_count"])
            failed_total += int(report["failed"])

        if write and run_id is not None:
            status = "partial" if failed_total else "succeeded"
            close_pipeline_run(
                conn,
                run_id,
                status=status,
                items_processed=len(row_reports),
                items_failed=failed_total,
                error_summary={"failed": failed_total} if failed_total else None,
            )
    except Exception as exc:
        if write and run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                items_processed=len(row_reports),
                items_failed=max(1, failed_total),
                error_summary={"error": str(exc)},
            )
        raise

    aggregate = _aggregate_reports(row_reports)
    cost = _cost_summary(
        usage_totals,
        llm_calls=llm_calls,
        input_cost_per_1m=input_cost_per_1m,
        output_cost_per_1m=output_cost_per_1m,
    )
    return {
        "dry_run": not write,
        "run_id": str(run_id) if run_id is not None else None,
        "llm_endpoint": {
            "profile": settings.get("llm_profile"),
            "base_url": settings.get("local_llm_base_url"),
            "model": model,
        },
        "institution": institution,
        "sample_size": len(rows),
        "llm_calls": llm_calls,
        "inserted_professor_fact_rows": inserted_total,
        "field_yield": aggregate,
        "translation_samples": _translation_samples(row_reports, limit=10),
        "cost": cost,
        "rows": row_reports,
    }


def _process_row(
    conn: psycopg.Connection,
    *,
    row: dict[str, Any],
    run_id: Any,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any],
    write: bool,
) -> dict[str, Any]:
    professor_id = str(row["professor_id"])
    source_page_id = row["primary_official_profile_page_id"]
    page_text = _row_page_text(row)
    existing_fields = _existing_fields(row)
    report: dict[str, Any] = {
        "professor_id": professor_id,
        "canonical_name": row["canonical_name"],
        "source_url": row.get("source_url"),
        "text_chars": len(page_text),
        "existing_fields": sorted(existing_fields),
        "extracted_fields": [],
        "ready_fields": [],
        "needs_review_fields": [],
        "newly_added_fields": [],
        "skipped_existing_fields": [],
        "skipped_low_confidence_fields": [],
        "inserted_count": 0,
        "failed": 0,
        "error": None,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "llm_called": False,
        "facts": [],
    }
    if not page_text:
        report["error"] = "missing_stored_profile_text"
        report["failed"] = 1
        return report

    result = extract_llm_profile_fields(
        ProfessorFieldExtractionInput(
            professor_id=professor_id,
            canonical_name=str(row["canonical_name"]),
            canonical_name_en=_optional_str(row.get("canonical_name_en")),
            institution=str(row["institution"]),
            source_url=_optional_str(row.get("source_url")),
            page_text=page_text,
            run_id=run_id,
        ),
        llm_client=llm_client,
        llm_model=llm_model,
        extra_body=extra_body,
    )
    report["llm_called"] = True
    report["usage"] = {
        "prompt_tokens": result.usage.prompt_tokens or 0,
        "completion_tokens": result.usage.completion_tokens or 0,
        "total_tokens": result.usage.total_tokens or 0,
    }
    if result.error:
        report["error"] = result.error
        report["failed"] = 1
        return report

    for fact in result.facts:
        field = FACT_TYPE_TO_FIELD.get(fact.fact_type, fact.fact_type)
        report["extracted_fields"].append(field)
        if fact.quality_status == "needs_review":
            report["needs_review_fields"].append(field)
        else:
            report["ready_fields"].append(field)
        report["facts"].append(_fact_report(fact))

        if fact.fact_type not in FACT_TYPE_TO_FIELD:
            continue
        if field in existing_fields:
            report["skipped_existing_fields"].append(field)
            continue
        if fact.quality_status != "ready":
            report["skipped_low_confidence_fields"].append(field)
            continue
        if not write:
            report["newly_added_fields"].append(field)
            continue

        result_status = _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type=fact.fact_type,
            value_raw=fact.value_raw,
            value_normalized=fact.value_normalized,
            source_page_id=source_page_id,
            evidence_span=fact.evidence_span,
            confidence=fact.confidence_decimal,
            run_id=run_id,
        )
        if result_status == "inserted":
            report["inserted_count"] += 1
        report["newly_added_fields"].append(field)

    for key in (
        "extracted_fields",
        "ready_fields",
        "needs_review_fields",
        "newly_added_fields",
        "skipped_existing_fields",
        "skipped_low_confidence_fields",
    ):
        report[key] = sorted(set(report[key]))
    return report


def _load_sample_rows(
    conn: psycopg.Connection,
    *,
    institution: str,
    limit: int,
) -> list[dict[str, Any]]:
    return list(
        conn.execute(
            """
            WITH primary_affiliation AS (
                SELECT DISTINCT ON (pa.professor_id)
                       pa.professor_id,
                       pa.institution
                  FROM professor_affiliation pa
                 WHERE pa.institution = %s
                 ORDER BY pa.professor_id,
                          pa.is_primary DESC,
                          pa.is_current DESC,
                          pa.updated_at DESC NULLS LAST,
                          pa.created_at DESC NULLS LAST
            ),
            active_fact AS (
                SELECT professor_id,
                       bool_or(fact_type = 'research_topic') AS has_research_directions,
                       bool_or(fact_type = 'education') AS has_education,
                       bool_or(fact_type = 'academic_position') AS has_academic_position,
                       bool_or(fact_type = 'work_experience') AS has_work_experience,
                       bool_or(fact_type = 'award') AS has_award,
                       bool_or(fact_type = 'contact') AS has_contact
                  FROM professor_fact
                 WHERE status = 'active'
                   AND trim(value_raw) <> ''
                   AND fact_type = ANY(%s)
                 GROUP BY professor_id
            )
            SELECT p.professor_id,
                   p.canonical_name,
                   p.canonical_name_en,
                   primary_affiliation.institution,
                   p.profile_raw_text,
                   p.profile_summary,
                   p.primary_official_profile_page_id,
                   sp.clean_text_path,
                   sp.url AS source_url,
                   COALESCE(active_fact.has_research_directions, false) AS has_research_directions,
                   COALESCE(active_fact.has_education, false) AS has_education,
                   COALESCE(active_fact.has_academic_position, false) AS has_academic_position,
                   COALESCE(active_fact.has_work_experience, false) AS has_work_experience,
                   COALESCE(active_fact.has_award, false) AS has_award,
                   COALESCE(active_fact.has_contact, false) AS has_contact
              FROM professor p
              JOIN primary_affiliation
                ON primary_affiliation.professor_id = p.professor_id
              JOIN source_page sp
                ON sp.page_id = p.primary_official_profile_page_id
              LEFT JOIN active_fact
                ON active_fact.professor_id = p.professor_id
             WHERE p.identity_status <> 'merged_into'
               AND COALESCE(p.lifecycle_state, 'active') = 'active'
               AND p.primary_official_profile_page_id IS NOT NULL
               AND (
                    p.profile_raw_text IS NOT NULL
                    OR sp.clean_text_path IS NOT NULL
               )
             ORDER BY
                (
                    (NOT COALESCE(active_fact.has_education, false))::int
                  + (NOT COALESCE(active_fact.has_academic_position, false))::int
                  + (NOT COALESCE(active_fact.has_research_directions, false))::int
                  + (NOT COALESCE(active_fact.has_work_experience, false))::int
                  + (NOT COALESCE(active_fact.has_contact, false))::int
                ) DESC,
                length(COALESCE(p.profile_raw_text, '')) DESC,
                p.professor_id
             LIMIT %s
            """,
            (institution, list(FIELD_TO_FACT_TYPE.values()), limit),
        ).fetchall()
    )


def _row_page_text(row: dict[str, Any]) -> str:
    raw_text = normalize_profile_text(_optional_str(row.get("profile_raw_text")))
    if raw_text:
        return raw_text
    clean_text_path = _optional_str(row.get("clean_text_path"))
    if not clean_text_path:
        return ""
    path = Path(clean_text_path)
    if not path.is_absolute():
        path = _APP_ROOT / clean_text_path
    try:
        return normalize_profile_text(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _existing_fields(row: dict[str, Any]) -> set[str]:
    fields = {field for field in FIELD_TO_FACT_TYPE if bool(row.get(f"has_{field}"))}
    if _optional_str(row.get("profile_summary")):
        fields.add("profile_summary")
    return fields


def _aggregate_reports(rows: list[dict[str, Any]]) -> dict[str, Any]:
    extracted_counts = [len(row["extracted_fields"]) for row in rows]
    ready_counts = [len(row["ready_fields"]) for row in rows]
    newly_added_counts = [len(row["newly_added_fields"]) for row in rows]
    by_field: dict[str, dict[str, int]] = {
        field: {"extracted": 0, "ready": 0, "needs_review": 0, "newly_added": 0}
        for field in MEASURED_FIELDS
    }
    for row in rows:
        for field in row["extracted_fields"]:
            by_field.setdefault(
                field, {"extracted": 0, "ready": 0, "needs_review": 0, "newly_added": 0}
            )
            by_field[field]["extracted"] += 1
        for field in row["ready_fields"]:
            by_field.setdefault(
                field, {"extracted": 0, "ready": 0, "needs_review": 0, "newly_added": 0}
            )
            by_field[field]["ready"] += 1
        for field in row["needs_review_fields"]:
            by_field.setdefault(
                field, {"extracted": 0, "ready": 0, "needs_review": 0, "newly_added": 0}
            )
            by_field[field]["needs_review"] += 1
        for field in row["newly_added_fields"]:
            by_field.setdefault(
                field, {"extracted": 0, "ready": 0, "needs_review": 0, "newly_added": 0}
            )
            by_field[field]["newly_added"] += 1
    return {
        "per_professor_extracted_mean": _mean(extracted_counts),
        "per_professor_extracted_median": _median(extracted_counts),
        "per_professor_ready_mean": _mean(ready_counts),
        "per_professor_ready_median": _median(ready_counts),
        "per_professor_newly_added_mean": _mean(newly_added_counts),
        "per_professor_newly_added_median": _median(newly_added_counts),
        "by_field": by_field,
    }


def _translation_samples(
    rows: list[dict[str, Any]], *, limit: int
) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for row in rows:
        for fact in row["facts"]:
            original = fact.get("value_original")
            bilingual = fact.get("value_raw")
            if not original or not bilingual or original == bilingual:
                continue
            samples.append(
                {
                    "professor_id": row["professor_id"],
                    "field": fact["field"],
                    "before": original,
                    "after": bilingual,
                }
            )
            if len(samples) >= limit:
                return samples
    return samples


def _cost_summary(
    usage: dict[str, int],
    *,
    llm_calls: int,
    input_cost_per_1m: float,
    output_cost_per_1m: float,
) -> dict[str, Any]:
    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    estimated_cost = (
        prompt_tokens / 1_000_000 * input_cost_per_1m
        + completion_tokens / 1_000_000 * output_cost_per_1m
    )
    per_prof_total_tokens = usage["total_tokens"] / llm_calls if llm_calls else 0.0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": usage["total_tokens"],
        "llm_calls": llm_calls,
        "per_prof_total_tokens": per_prof_total_tokens,
        "estimated_cost_usd": estimated_cost
        if input_cost_per_1m or output_cost_per_1m
        else None,
        "input_cost_per_1m_usd": input_cost_per_1m,
        "output_cost_per_1m_usd": output_cost_per_1m,
        "extrapolated_3387_total_tokens": per_prof_total_tokens * 3387,
        "extrapolated_3387_cost_usd": (
            estimated_cost / llm_calls * 3387
            if llm_calls and (input_cost_per_1m or output_cost_per_1m)
            else None
        ),
    }


def _fact_report(fact: LLMExtractedProfileFact) -> dict[str, Any]:
    return {
        "field": FACT_TYPE_TO_FIELD.get(fact.fact_type, fact.fact_type),
        "fact_type": fact.fact_type,
        "value_original": fact.value_original,
        "value_raw": fact.value_raw,
        "evidence_span": fact.evidence_span,
        "confidence": fact.confidence,
        "quality_status": fact.quality_status,
        "source": fact.source,
        "run_id": str(fact.run_id),
    }


def _mean(values: list[int]) -> float:
    return statistics.mean(values) if values else 0.0


def _median(values: list[int]) -> float:
    return statistics.median(values) if values else 0.0


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded CUHK-SZ LLM profile field extraction apply + measurement."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL or POSTGRES_DSN.",
    )
    parser.add_argument("--institution", default=DEFAULT_INSTITUTION)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--write", action="store_true", help="Persist ready missing facts."
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required with --write against miroflow_real.",
    )
    parser.add_argument(
        "--input-cost-per-1m",
        type=float,
        default=float(os.environ.get("LLM_FIELD_INPUT_COST_PER_1M", "0") or 0),
        help="Optional input-token price for cost estimate.",
    )
    parser.add_argument(
        "--output-cost-per-1m",
        type=float,
        default=float(os.environ.get("LLM_FIELD_OUTPUT_COST_PER_1M", "0") or 0),
        help="Optional output-token price for cost estimate.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
