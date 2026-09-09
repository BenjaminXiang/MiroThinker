from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import json
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb

from .canonical_import import _evaluate_xlsx_baseline_readiness
from .news_connectors import YiouSearchHints

ReviewAction = Literal["accept", "reject", "needs_review"]
ReviewTargetType = Literal["product", "scenario"]
BASELINE_READINESS_STAGE = "baseline_readiness"

_ACTION_STATUS: dict[ReviewAction, str] = {
    "accept": "ready",
    "reject": "rejected",
    "needs_review": "needs_review",
}


@dataclass(frozen=True, slots=True)
class EnrichmentBatchCreateResult:
    batch_id: UUID
    companies_total: int
    companies_selected: int


@dataclass(frozen=True, slots=True)
class RepresentativeCompanySample:
    company_ids: list[str]
    candidates_total: int
    selected_count: int
    selection_criteria: dict[str, Any]
    bucket_summary: list[dict[str, Any]]

    def to_report_dict(self, *, sample_size_requested: int | None) -> dict[str, Any]:
        return {
            "sample_size_requested": sample_size_requested,
            "candidates_total": self.candidates_total,
            "selected_count": self.selected_count,
            "selection_criteria": dict(self.selection_criteria),
            "bucket_summary": list(self.bucket_summary),
        }


def select_representative_company_sample(
    candidates: list[dict[str, Any]],
    *,
    sample_size: int,
) -> RepresentativeCompanySample:
    requested = max(0, int(sample_size))
    unique_rows: dict[str, dict[str, Any]] = {}
    for row in candidates:
        company_id = str(row.get("company_id") or "").strip()
        if not company_id or company_id in unique_rows:
            continue
        unique_rows[company_id] = dict(row)
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in unique_rows.values():
        bucket = _representative_sample_bucket(row)
        buckets.setdefault(bucket, []).append(row)
    for rows in buckets.values():
        rows.sort(key=lambda item: str(item.get("company_id") or ""))

    selected: list[str] = []
    selected_counts: Counter[tuple[str, str, str]] = Counter()
    bucket_indexes = {bucket: 0 for bucket in buckets}
    ordered_buckets = sorted(buckets)
    while len(selected) < requested:
        progressed = False
        for bucket in ordered_buckets:
            rows = buckets[bucket]
            index = bucket_indexes[bucket]
            if index >= len(rows):
                continue
            selected.append(str(rows[index]["company_id"]))
            selected_counts[bucket] += 1
            bucket_indexes[bucket] = index + 1
            progressed = True
            if len(selected) >= requested:
                break
        if not progressed:
            break

    bucket_summary = [
        {
            "bucket": {
                "industry": bucket[0],
                "website_availability": bucket[1],
                "source_coverage": bucket[2],
            },
            "candidates": len(buckets[bucket]),
            "selected": int(selected_counts.get(bucket, 0)),
        }
        for bucket in ordered_buckets
    ]
    return RepresentativeCompanySample(
        company_ids=selected,
        candidates_total=len(unique_rows),
        selected_count=len(selected),
        selection_criteria={
            "strategy": "deterministic_stratified_round_robin",
            "bucket_fields": [
                "industry",
                "website_availability",
                "source_coverage",
            ],
            "stable_sort": "company_id",
        },
        bucket_summary=bucket_summary,
    )


def load_representative_company_sample(
    conn: Any,
    *,
    batch_id: UUID | str,
    sample_size: int,
    include_failed: bool = False,
) -> RepresentativeCompanySample:
    statuses = ("queued", "partial") + (("failed",) if include_failed else ())
    rows = conn.execute(
        """
        WITH latest_snapshot AS (
            SELECT DISTINCT ON (cs.company_id)
                   cs.company_id,
                   cs.industry,
                   cs.sub_industry,
                   cs.website_xlsx
              FROM company_snapshot cs
             ORDER BY cs.company_id,
                      cs.snapshot_created_at DESC NULLS LAST,
                      cs.snapshot_id DESC
        ),
        source_counts AS (
            SELECT company_id,
                   count(*) FILTER (
                       WHERE source_adapter IN (
                           'iyiou', 'pitchhub_36kr', 'generic_web'
                       )
                   )::int AS source_count
              FROM company_news_item
             GROUP BY company_id
        )
        SELECT s.company_id,
               COALESCE(NULLIF(latest.industry, ''), 'unknown_industry') AS industry,
               COALESCE(NULLIF(latest.sub_industry, ''), 'unknown_sub_industry')
                   AS sub_industry,
               COALESCE(NULLIF(c.website, ''), NULLIF(latest.website_xlsx, ''))
                   AS website,
               COALESCE(source_counts.source_count, 0)::int AS source_count
          FROM company_enrichment_company_state s
          JOIN company c ON c.company_id = s.company_id
          LEFT JOIN latest_snapshot latest ON latest.company_id = s.company_id
          LEFT JOIN source_counts ON source_counts.company_id = s.company_id
         WHERE s.batch_id = %(batch_id)s
           AND s.status = ANY(%(statuses)s::text[])
         ORDER BY s.company_id
        """,
        {"batch_id": batch_id, "statuses": list(statuses)},
    ).fetchall()
    return select_representative_company_sample(
        [_row_payload(row) for row in rows],
        sample_size=sample_size,
    )


def _representative_sample_bucket(row: dict[str, Any]) -> tuple[str, str, str]:
    industry = _normalize_bucket_text(row.get("industry"), fallback="unknown_industry")
    website_availability = (
        "has_website"
        if _normalize_bucket_text(row.get("website"), fallback="")
        else "no_website"
    )
    source_count = _safe_int(row.get("source_count"))
    source_coverage = (
        "has_external_sources" if source_count > 0 else "no_external_sources"
    )
    return (industry, website_availability, source_coverage)


def _normalize_bucket_text(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def create_enrichment_batch(
    conn: Any,
    *,
    upload_task_id: UUID | str | None,
    import_batch_id: UUID | str | None,
    company_ids: list[str],
    run_scope: dict[str, Any] | None = None,
    triggered_by: str | None = None,
) -> EnrichmentBatchCreateResult:
    selected = _unique_company_ids(company_ids)
    row = conn.execute(
        """
        INSERT INTO company_enrichment_batch (
            upload_task_id, import_batch_id, status, current_stage,
            companies_total, companies_selected, run_scope, triggered_by,
            miss_reason_buckets, quality_report
        )
        VALUES (
            %(upload_task_id)s, %(import_batch_id)s, 'queued', 'queued',
            %(companies_total)s, %(companies_selected)s, %(run_scope)s, %(triggered_by)s,
            %(miss_reason_buckets)s, %(quality_report)s
        )
        RETURNING batch_id
        """,
        {
            "upload_task_id": upload_task_id,
            "import_batch_id": import_batch_id,
            "companies_total": len(company_ids),
            "companies_selected": len(selected),
            "run_scope": Jsonb(run_scope or {}),
            "triggered_by": triggered_by,
            "miss_reason_buckets": Jsonb({}),
            "quality_report": Jsonb({}),
        },
    ).fetchone()
    if row is None:
        raise RuntimeError("company_enrichment_batch INSERT did not return a row")
    batch_id = row["batch_id"] if isinstance(row, dict) else row[0]
    if selected:
        conn.execute(
            """
            INSERT INTO company_enrichment_company_state (
                batch_id, company_id, status, current_stage
            )
            SELECT %(batch_id)s, unnest(%(company_ids)s::text[]), 'queued', 'queued'
            ON CONFLICT (batch_id, company_id) DO NOTHING
            """,
            {"batch_id": batch_id, "company_ids": selected},
        )
    return EnrichmentBatchCreateResult(
        batch_id=batch_id,
        companies_total=len(company_ids),
        companies_selected=len(selected),
    )


def _unique_company_ids(company_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []
    for company_id in company_ids:
        value = str(company_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        selected.append(value)
    return selected


def mark_batch_started(conn: Any, *, batch_id: UUID | str) -> None:
    conn.execute(
        """
        UPDATE company_enrichment_batch
           SET status = 'running',
               current_stage = 'running',
               last_error = NULL,
               finished_at = NULL,
               started_at = COALESCE(started_at, now()),
               runner_heartbeat_at = now(),
               runner_last_seen_at = now(),
               updated_at = now()
         WHERE batch_id = %s
        """,
        (batch_id,),
    )


def record_batch_runner_started(
    conn: Any,
    *,
    batch_id: UUID | str,
    runner_pid: int | None,
    runner_log_path: str | None,
) -> None:
    conn.execute(
        """
        UPDATE company_enrichment_batch
           SET runner_pid = %(runner_pid)s,
               runner_log_path = %(runner_log_path)s,
               runner_heartbeat_at = now(),
               runner_last_seen_at = now(),
               updated_at = now()
         WHERE batch_id = %(batch_id)s
        """,
        {
            "batch_id": batch_id,
            "runner_pid": runner_pid,
            "runner_log_path": runner_log_path,
        },
    )


def record_batch_heartbeat(
    conn: Any,
    *,
    batch_id: UUID | str,
    current_stage: str | None = None,
    last_completed_company_id: str | None = None,
    quality_report: dict[str, Any] | None = None,
    miss_reason_buckets: dict[str, int] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE company_enrichment_batch
           SET runner_heartbeat_at = now(),
               runner_last_seen_at = now(),
               current_stage = COALESCE(%(current_stage)s, current_stage),
               last_completed_company_id = COALESCE(
                   %(last_completed_company_id)s,
                   last_completed_company_id
               ),
               quality_report = CASE
                   WHEN %(quality_report)s IS NULL THEN quality_report
                   ELSE %(quality_report)s
               END,
               miss_reason_buckets = CASE
                   WHEN %(miss_reason_buckets)s IS NULL THEN miss_reason_buckets
                   ELSE %(miss_reason_buckets)s
               END,
               updated_at = now()
         WHERE batch_id = %(batch_id)s
        """,
        {
            "batch_id": batch_id,
            "current_stage": current_stage,
            "last_completed_company_id": last_completed_company_id,
            "quality_report": (
                Jsonb(quality_report) if quality_report is not None else None
            ),
            "miss_reason_buckets": (
                Jsonb(miss_reason_buckets)
                if miss_reason_buckets is not None
                else None
            ),
        },
    )


def mark_batch_progress(
    conn: Any,
    *,
    batch_id: UUID | str,
    companies_processed: int,
    current_stage: str | None = None,
) -> None:
    conn.execute(
        """
        WITH state_counts AS (
            SELECT
                count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                count(*) FILTER (WHERE status = 'failed')::int AS failed
            FROM company_enrichment_company_state
            WHERE batch_id = %(batch_id)s
        )
        UPDATE company_enrichment_batch b
           SET companies_processed = GREATEST(
                   b.companies_processed,
                   %(companies_processed)s
               ),
               companies_succeeded = state_counts.succeeded,
               companies_failed = state_counts.failed,
               current_stage = COALESCE(%(current_stage)s, b.current_stage),
               runner_heartbeat_at = now(),
               runner_last_seen_at = now(),
               updated_at = now()
          FROM state_counts
         WHERE b.batch_id = %(batch_id)s
        """,
        {
            "batch_id": batch_id,
            "companies_processed": int(companies_processed),
            "current_stage": current_stage,
        },
    )


def mark_batch_finished(
    conn: Any,
    *,
    batch_id: UUID | str,
    status: str,
    last_error: str | None = None,
) -> None:
    conn.execute(
        """
        WITH state_counts AS (
            SELECT
                count(*) FILTER (WHERE status IN ('succeeded', 'partial', 'failed'))::int
                    AS processed,
                count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                count(*) FILTER (WHERE status = 'failed')::int AS failed
            FROM company_enrichment_company_state
            WHERE batch_id = %(batch_id)s
        )
        UPDATE company_enrichment_batch b
           SET status = %(status)s,
               current_stage = %(status)s,
               companies_processed = state_counts.processed,
               companies_succeeded = state_counts.succeeded,
               companies_failed = state_counts.failed,
               last_error = CASE
                   WHEN %(status)s = 'succeeded' THEN NULL
                   ELSE COALESCE(%(last_error)s, b.last_error)
               END,
               finished_at = now(),
               runner_heartbeat_at = now(),
               runner_last_seen_at = now(),
               updated_at = now()
          FROM state_counts
         WHERE b.batch_id = %(batch_id)s
        """,
        {"batch_id": batch_id, "status": status, "last_error": last_error},
    )


def close_stale_running_enrichment_batches(
    conn: Any,
    *,
    stale_after_minutes: int = 120,
) -> int:
    row = conn.execute(
        """
        WITH stale_batches AS (
            SELECT batch_id
             FROM company_enrichment_batch
             WHERE status = 'running'
               AND COALESCE(
                   runner_heartbeat_at,
                   runner_last_seen_at,
                   updated_at
               ) < now() - (%(stale_after_minutes)s || ' minutes')::interval
        ),
        stale_states AS (
            UPDATE company_enrichment_company_state s
               SET status = 'failed',
                   last_error = COALESCE(s.last_error, 'stale_running_timeout'),
                   finished_at = COALESCE(s.finished_at, now()),
                   updated_at = now()
              FROM stale_batches b
             WHERE s.batch_id = b.batch_id
               AND s.status = 'running'
            RETURNING s.batch_id, s.company_id
        ),
        stale_company_states AS (
            UPDATE company_enrichment_company_state s
               SET status = 'failed',
                   last_error = COALESCE(s.last_error, 'stale_running_timeout'),
                   finished_at = COALESCE(s.finished_at, now()),
                   updated_at = now()
             WHERE s.status = 'running'
               AND s.updated_at < now() - (%(stale_after_minutes)s || ' minutes')::interval
            RETURNING s.batch_id, s.company_id
        ),
        updated_batches AS (
            UPDATE company_enrichment_batch b
               SET status = 'failed',
                   current_stage = 'failed',
                   last_error = COALESCE(b.last_error, 'stale_running_timeout'),
                   finished_at = COALESCE(b.finished_at, now()),
                   runner_last_seen_at = now(),
                   updated_at = now()
              FROM stale_batches stale
             WHERE b.batch_id = stale.batch_id
            RETURNING b.batch_id
        )
        SELECT (
            (SELECT count(*) FROM updated_batches)
            + (SELECT count(*) FROM stale_company_states)
        )::int AS updated_count
        """,
        {"stale_after_minutes": int(stale_after_minutes)},
    ).fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get("updated_count") or 0)
    return int(row[0] or 0)


def load_pending_company_ids(
    conn: Any,
    *,
    batch_id: UUID | str,
    limit: int | None = None,
    include_failed: bool = False,
) -> list[str]:
    statuses = ("queued", "partial") + (("failed",) if include_failed else ())
    params: dict[str, Any] = {"batch_id": batch_id, "statuses": list(statuses)}
    sql = (
        "SELECT company_id FROM company_enrichment_company_state "
        "WHERE batch_id = %(batch_id)s AND status = ANY(%(statuses)s::text[]) "
        "ORDER BY company_id"
    )
    if limit is not None:
        sql += " LIMIT %(limit)s"
        params["limit"] = int(limit)
    rows = conn.execute(sql, params).fetchall()
    return [str(row["company_id"] if isinstance(row, dict) else row[0]) for row in rows]


def load_stage_pending_company_ids(
    conn: Any,
    *,
    batch_id: UUID | str,
    stage: str,
    company_ids: list[str],
) -> list[str]:
    selected = _unique_company_ids(company_ids)
    if not selected:
        return []
    rows = conn.execute(
        """
        SELECT company_id
          FROM company_enrichment_company_state
         WHERE batch_id = %(batch_id)s
           AND company_id = ANY(%(company_ids)s::text[])
           AND COALESCE(stage_status->%(stage)s->>'status', '') != 'succeeded'
         ORDER BY company_id
        """,
        {"batch_id": batch_id, "stage": stage, "company_ids": selected},
    ).fetchall()
    return [str(row["company_id"] if isinstance(row, dict) else row[0]) for row in rows]


def mark_company_stage_running(
    conn: Any,
    *,
    batch_id: UUID | str,
    company_id: str,
    stage: str,
) -> None:
    conn.execute(
        """
        UPDATE company_enrichment_company_state
           SET status = 'running',
               current_stage = %(stage)s,
               attempts = attempts + 1,
               started_at = COALESCE(started_at, now()),
               updated_at = now()
         WHERE batch_id = %(batch_id)s
           AND company_id = %(company_id)s
        """,
        {"batch_id": batch_id, "company_id": company_id, "stage": stage},
    )


def mark_company_stage_complete(
    conn: Any,
    *,
    batch_id: UUID | str,
    company_id: str,
    stage: str,
    counters: dict[str, int] | None = None,
    details: dict[str, Any] | None = None,
    miss_reason: str | None = None,
    status: str = "partial",
    last_error: str | None = None,
) -> None:
    counters = counters or {}
    recorded_stage_status = "failed" if status == "failed" else "succeeded"
    stage_payload: dict[str, Any] = {
        "status": recorded_stage_status,
        "counters": counters,
    }
    if details:
        stage_payload.update(details)
    if miss_reason:
        stage_payload["miss_reason"] = miss_reason
    if last_error:
        stage_payload["last_error"] = last_error
    stage_status = {stage: stage_payload}
    conn.execute(
        """
        UPDATE company_enrichment_company_state
           SET status = %(status)s,
               current_stage = %(stage)s,
               stage_status = stage_status || %(stage_status)s,
               query_count = query_count + %(query_count)s,
               source_result_count = source_result_count + %(source_result_count)s,
               accepted_source_count = accepted_source_count + %(accepted_source_count)s,
               rejected_source_count = rejected_source_count + %(rejected_source_count)s,
               event_count = event_count + %(event_count)s,
               product_count = product_count + %(product_count)s,
               scenario_count = scenario_count + %(scenario_count)s,
               official_product_count = official_product_count + %(official_product_count)s,
               milvus_refreshed_at = CASE
                   WHEN %(milvus_refreshed)s THEN now()
                   ELSE milvus_refreshed_at
               END,
               miss_reason = COALESCE(%(miss_reason)s, miss_reason),
               last_error = CASE
                   WHEN %(status)s = 'failed'
                   THEN COALESCE(%(last_error)s, last_error)
                   ELSE NULL
               END,
               finished_at = CASE
                   WHEN %(status)s IN ('succeeded', 'failed') THEN now()
                   ELSE finished_at
               END,
               updated_at = now()
         WHERE batch_id = %(batch_id)s
           AND company_id = %(company_id)s
        """,
        {
            "batch_id": batch_id,
            "company_id": company_id,
            "stage": stage,
            "stage_status": Jsonb(stage_status),
            "status": status,
            "query_count": int(counters.get("query_count", 0)),
            "source_result_count": int(counters.get("source_result_count", 0)),
            "accepted_source_count": int(counters.get("accepted_source_count", 0)),
            "rejected_source_count": int(counters.get("rejected_source_count", 0)),
            "event_count": int(counters.get("event_count", 0)),
            "product_count": int(counters.get("product_count", 0)),
            "scenario_count": int(counters.get("scenario_count", 0)),
            "official_product_count": int(counters.get("official_product_count", 0)),
            "milvus_refreshed": bool(counters.get("milvus_refreshed", 0)),
            "miss_reason": miss_reason,
            "last_error": last_error,
        },
    )


_BASELINE_ROW_FIELDS = (
    "company_name_xlsx",
    "project_name",
    "industry",
    "sub_industry",
    "business",
    "region",
    "description",
    "website_xlsx",
    "latest_funding_round",
    "latest_funding_time_raw",
    "latest_funding_amount_raw",
    "latest_funding_cny_wan",
    "latest_investors_raw",
    "team_raw",
    "reported_patent_count",
    "reported_news_count",
    "reported_funding_round_count",
    "reported_total_funding_raw",
    "reported_valuation_raw",
    "registered_address",
    "registered_capital",
)


def record_baseline_readiness_stage(
    conn: Any,
    *,
    batch_id: UUID | str,
    company_ids: list[str],
) -> dict[str, Any]:
    selected = _unique_company_ids(company_ids)
    if not selected:
        return {
            "companies_checked": 0,
            "baseline_ready": 0,
            "baseline_blocked": 0,
            "blockers": {},
        }

    readiness_by_company = _load_baseline_readiness(conn, company_ids=selected)
    ready_company_ids: list[str] = []
    blocker_counts: Counter[str] = Counter()
    blocked = 0

    for company_id in selected:
        readiness = readiness_by_company.get(company_id)
        if readiness is None:
            readiness = {
                "quality_status": "needs_review",
                "blockers": [
                    "missing_company_record",
                    "missing_latest_snapshot",
                    "missing_company_name",
                    "missing_meaningful_baseline_field",
                ],
                "has_latest_snapshot": False,
            }
        blockers = list(readiness["blockers"])
        if readiness["quality_status"] == "ready":
            ready_company_ids.append(company_id)
        else:
            blocked += 1
            blocker_counts.update(blockers)
        mark_company_stage_complete(
            conn,
            batch_id=batch_id,
            company_id=company_id,
            stage=BASELINE_READINESS_STAGE,
            counters={
                "baseline_ready_count": (
                    1 if readiness["quality_status"] == "ready" else 0
                ),
                "baseline_blocker_count": len(blockers),
            },
            details={
                "quality_status": readiness["quality_status"],
                "blockers": blockers,
                "has_latest_snapshot": bool(readiness["has_latest_snapshot"]),
                "source": "xlsx_baseline",
            },
            miss_reason="baseline_not_ready" if blockers else None,
            status="partial",
        )

    if ready_company_ids:
        conn.execute(
            """
            UPDATE company
               SET quality_status = 'ready',
                   updated_at = now()
             WHERE company_id = ANY(%(company_ids)s::text[])
            """,
            {"company_ids": ready_company_ids},
        )

    return {
        "companies_checked": len(selected),
        "baseline_ready": len(ready_company_ids),
        "baseline_blocked": blocked,
        "blockers": {
            blocker: blocker_counts[blocker] for blocker in sorted(blocker_counts)
        },
    }


def _load_baseline_readiness(
    conn: Any,
    *,
    company_ids: list[str],
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.company_id,
            c.identity_status,
            latest.snapshot_id,
            latest.company_name_xlsx,
            latest.project_name,
            latest.industry,
            latest.sub_industry,
            latest.business,
            latest.region,
            latest.description,
            latest.website_xlsx,
            latest.latest_funding_round,
            latest.latest_funding_time_raw,
            latest.latest_funding_amount_raw,
            latest.latest_funding_cny_wan,
            latest.latest_investors_raw,
            latest.team_raw,
            latest.reported_patent_count,
            latest.reported_news_count,
            latest.reported_funding_round_count,
            latest.reported_total_funding_raw,
            latest.reported_valuation_raw,
            latest.registered_address,
            latest.registered_capital
          FROM company c
          LEFT JOIN LATERAL (
            SELECT
                cs.snapshot_id,
                cs.company_name_xlsx,
                cs.project_name,
                cs.industry,
                cs.sub_industry,
                cs.business,
                cs.region,
                cs.description,
                cs.website_xlsx,
                cs.latest_funding_round,
                cs.latest_funding_time_raw,
                cs.latest_funding_amount_raw,
                cs.latest_funding_cny_wan,
                cs.latest_investors_raw,
                cs.team_raw,
                cs.reported_patent_count,
                cs.reported_news_count,
                cs.reported_funding_round_count,
                cs.reported_total_funding_raw,
                cs.reported_valuation_raw,
                cs.registered_address,
                cs.registered_capital
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
             LIMIT 1
          ) latest ON TRUE
         WHERE c.company_id = ANY(%(company_ids)s::text[])
         ORDER BY c.company_id
        """,
        {"company_ids": company_ids},
    ).fetchall()
    readiness_by_company: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = _row_payload(row)
        values = {
            field: payload.get(field)
            for field in _BASELINE_ROW_FIELDS
        }
        readiness = _evaluate_xlsx_baseline_readiness(
            values,
            identity_status=str(payload.get("identity_status") or ""),
            has_latest_snapshot=payload.get("snapshot_id") is not None,
        )
        readiness_by_company[str(payload["company_id"])] = {
            "quality_status": readiness.quality_status,
            "blockers": list(readiness.blockers),
            "has_latest_snapshot": payload.get("snapshot_id") is not None,
        }
    return readiness_by_company


def _row_payload(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    raise TypeError("Expected mapping row for company baseline readiness")


def record_search_audit(
    conn: Any,
    *,
    batch_id: UUID | str,
    company_id: str,
    source_adapter: str,
    diagnostics: dict[str, Any] | None,
    search_hints: YiouSearchHints | None = None,
    miss_reason: str | None = None,
) -> int:
    diagnostics = diagnostics or {}
    records_by_query = diagnostics.get("records_by_query") or {}
    if not isinstance(records_by_query, dict):
        records_by_query = {}
    if not records_by_query:
        records_by_query = {"<no_query_recorded>": int(diagnostics.get("items_seen") or 0)}
    inserted = 0
    accepted_total = int(diagnostics.get("items_accepted") or 0)
    rejected_offsite = int(diagnostics.get("items_rejected_offsite") or 0)
    rejected_irrelevant_path = int(
        diagnostics.get("items_rejected_irrelevant_path") or 0
    )
    rejected_name_mismatch = int(diagnostics.get("items_rejected_name_mismatch") or 0)
    inferred_miss = miss_reason or _infer_miss_reason(
        records_by_query=records_by_query,
        accepted_total=accepted_total,
        diagnostics=diagnostics,
    )
    diagnostics = dict(diagnostics)
    diagnostics.setdefault("counter_scope", "company_adapter_aggregate_stored_once")
    hints_payload = _search_hints_payload(search_hints)
    query_kind = str(diagnostics.get("query_kind") or "site_search")
    for index, (query_text, result_count) in enumerate(records_by_query.items()):
        is_counter_row = index == 0
        conn.execute(
            """
            INSERT INTO company_enrichment_search_audit (
                batch_id, company_id, source_adapter, query_text, query_kind,
                result_count, accepted_count, rejected_offsite,
                rejected_irrelevant_path, rejected_name_mismatch, miss_reason,
                llm_hints, diagnostics
            )
            VALUES (
                %(batch_id)s, %(company_id)s, %(source_adapter)s, %(query_text)s,
                %(query_kind)s, %(result_count)s, %(accepted_count)s,
                %(rejected_offsite)s, %(rejected_irrelevant_path)s,
                %(rejected_name_mismatch)s, %(miss_reason)s,
                %(llm_hints)s, %(diagnostics)s
            )
            """,
            {
                "batch_id": batch_id,
                "company_id": company_id,
                "source_adapter": source_adapter,
                "query_text": str(query_text),
                "query_kind": query_kind,
                "result_count": int(result_count or 0),
                "accepted_count": accepted_total if is_counter_row else 0,
                "rejected_offsite": rejected_offsite if is_counter_row else 0,
                "rejected_irrelevant_path": (
                    rejected_irrelevant_path if is_counter_row else 0
                ),
                "rejected_name_mismatch": (
                    rejected_name_mismatch if is_counter_row else 0
                ),
                "miss_reason": inferred_miss,
                "llm_hints": Jsonb(hints_payload),
                "diagnostics": Jsonb(diagnostics),
            },
        )
        inserted += 1
    return inserted


def _infer_miss_reason(
    *,
    records_by_query: dict[Any, Any],
    accepted_total: int,
    diagnostics: dict[str, Any],
) -> str | None:
    if accepted_total > 0:
        return None
    if diagnostics.get("persist_failed"):
        return "persist_failed"
    if diagnostics.get("llm_rejected"):
        return "llm_rejected"
    if diagnostics.get("synthesis_no_facts"):
        return "synthesis_no_facts"
    if diagnostics.get("fetch_failed") or diagnostics.get("error"):
        return "fetch_failed"
    total_results = sum(int(value or 0) for value in records_by_query.values())
    if total_results == 0:
        return "no_results"
    return "all_results_rejected"


def build_miss_reason_buckets(
    *,
    miss_reasons: dict[str, Any] | None = None,
    official_failure_reasons: dict[str, Any] | None = None,
    rejected_candidate_reasons: dict[str, Any] | None = None,
) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for reasons in (
        miss_reasons or {},
        official_failure_reasons or {},
        rejected_candidate_reasons or {},
    ):
        for reason, count in reasons.items():
            bucket = normalize_miss_reason_bucket(str(reason or ""))
            buckets[bucket] += _safe_int(count)
    return {bucket: int(buckets[bucket]) for bucket in sorted(buckets)}


def normalize_miss_reason_bucket(reason: str) -> str:
    value = str(reason or "").strip().casefold()
    if not value:
        return "other"
    if value in {"no_results", "no_search_results", "empty_search_results"}:
        return "no_search_results"
    if (
        "identity" in value
        or "name_mismatch" in value
        or "other_company" in value
        or "belongs_to_other_company" in value
    ):
        return "identity_mismatch"
    if (
        value.startswith("http_")
        or "timeout" in value
        or "fetch" in value
        or "dns" in value
        or "captcha" in value
        or "bot_challenge" in value
        or "js_required" in value
        or "js_render" in value
        or "robots" in value
        or "no_website" in value
        or "invalid_url" in value
        or "webpage_unavailable" in value
    ):
        return "webpage_unavailable"
    if "llm" in value or "synthesis_no_facts" in value:
        return "llm_rejected"
    if "registration" in value or "工商" in value or "注册" in value:
        return "registration_only"
    return "other"


def _search_hints_payload(search_hints: YiouSearchHints | None) -> dict[str, Any]:
    if search_hints is None:
        return {}
    return {
        "identity_aliases": list(search_hints.identity_aliases),
        "aliases": list(search_hints.aliases),
        "founder_names": list(search_hints.founder_names),
        "keywords": list(search_hints.keywords),
        "source": search_hints.source,
        "error": search_hints.error,
    }


def review_enrichment_item(
    conn: Any,
    *,
    target_type: ReviewTargetType,
    target_id: str,
    action: ReviewAction,
    actor: str,
    note: str | None = None,
) -> dict[str, Any]:
    new_status = _ACTION_STATUS[action]
    table, id_column = _review_target_table(target_type)
    row = conn.execute(
        f"""
        SELECT quality_status, company_id
          FROM {table}
         WHERE {id_column} = %(target_id)s
        """,
        {"target_id": target_id},
    ).fetchone()
    if row is None:
        raise KeyError(f"{target_type} {target_id} not found")
    previous_status = row["quality_status"] if isinstance(row, dict) else row[0]
    company_id = row["company_id"] if isinstance(row, dict) else row[1]
    conn.execute(
        f"""
        UPDATE {table}
           SET quality_status = %(new_status)s,
               updated_at = now()
         WHERE {id_column} = %(target_id)s
        """,
        {"new_status": new_status, "target_id": target_id},
    )
    conn.execute(
        """
        INSERT INTO company_enrichment_review_action (
            company_id, target_type, target_id, action, actor, note,
            previous_status, new_status
        )
        VALUES (
            %(company_id)s, %(target_type)s, %(target_id)s, %(action)s,
            %(actor)s, %(note)s, %(previous_status)s, %(new_status)s
        )
        """,
        {
            "company_id": company_id,
            "target_type": target_type,
            "target_id": target_id,
            "action": action,
            "actor": actor,
            "note": note,
            "previous_status": previous_status,
            "new_status": new_status,
        },
    )
    return {
        "company_id": company_id,
        "target_type": target_type,
        "target_id": target_id,
        "action": action,
        "previous_status": previous_status,
        "new_status": new_status,
    }


def _review_target_table(target_type: ReviewTargetType) -> tuple[str, str]:
    if target_type == "product":
        return "company_product", "product_id"
    if target_type == "scenario":
        return "company_application_scenario", "scenario_id"
    raise ValueError(f"Unsupported target_type: {target_type}")


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
