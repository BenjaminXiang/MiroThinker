"""Infer missing patent_type values from patent_number.

Dry-run is the default and performs no writes. Use --apply only after reviewing
the dry-run JSONL output and summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.patent.release import _calculate_quality_status  # noqa: E402
from src.data_agents.patent.type_inference import infer_patent_type  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "run_patent_type_inference_backfill"


@dataclass(frozen=True, slots=True)
class PatentTypeBackfillDecision:
    patent_id: str
    patent_number: str | None
    old_type: str | None
    inferred_type: str
    old_quality_status: str | None
    new_quality_status: str

    @property
    def is_promoted_to_ready(self) -> bool:
        return self.old_quality_status != "ready" and self.new_quality_status == "ready"

    @property
    def is_ready_degraded(self) -> bool:
        return self.old_quality_status == "ready" and self.new_quality_status != "ready"

    def to_json_event(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PatentTypeBackfillSummary:
    examined: int
    candidates: int
    promoted_to_ready: int
    unchanged: int
    ready_degraded: int
    dry_run: bool
    json_output: str | None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing patent_type from CN patent_number kind codes.",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        help="Read and emit JSONL without writing. This is the default.",
    )
    mode.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Write inferred patent_type and recomputed quality_status.",
    )
    parser.set_defaults(apply=False)
    parser.add_argument(
        "--json-output",
        type=Path,
        required=True,
        help="JSONL output path for examined rows.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows to examine.")
    return parser.parse_args(argv)


def _connect(dsn: str):
    return psycopg.connect(resolve_dsn(dsn), row_factory=dict_row)


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        return _coerce_text_list(decoded)
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def build_backfill_decision(
    row: Mapping[str, Any],
) -> PatentTypeBackfillDecision | None:
    old_type = _coerce_optional_text(row.get("patent_type"))
    patent_number = _coerce_optional_text(row.get("patent_number"))
    inferred_type = infer_patent_type(patent_number, current_type=old_type)
    if inferred_type is None or inferred_type == old_type:
        return None

    new_quality_status = _calculate_quality_status(
        title_clean=_coerce_optional_text(row.get("title_clean")),
        patent_number=patent_number,
        patent_type=inferred_type,
        applicants_parsed=_coerce_text_list(row.get("applicants_parsed")),
        inventors_parsed=_coerce_text_list(row.get("inventors_parsed")),
        filing_date=row.get("filing_date"),
        grant_date=row.get("grant_date"),
        publication_date=row.get("publication_date"),
    )
    return PatentTypeBackfillDecision(
        patent_id=str(row["patent_id"]),
        patent_number=patent_number,
        old_type=old_type,
        inferred_type=inferred_type,
        old_quality_status=_coerce_optional_text(row.get("quality_status")),
        new_quality_status=new_quality_status,
    )


def _build_select_sql(limit: int | None) -> tuple[str, tuple[Any, ...]]:
    sql = """
        SELECT
            patent_id,
            patent_number,
            patent_type,
            quality_status,
            title_clean,
            applicants_parsed,
            inventors_parsed,
            filing_date,
            grant_date,
            publication_date
          FROM patent
         ORDER BY patent_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _load_patent_rows(conn: Any, *, limit: int | None) -> list[Mapping[str, Any]]:
    sql, params = _build_select_sql(limit)
    return list(conn.execute(sql, params).fetchall())


def _json_event_for_row(
    row: Mapping[str, Any],
    decision: PatentTypeBackfillDecision | None,
) -> dict[str, Any]:
    if decision is not None:
        return decision.to_json_event()

    old_type = _coerce_optional_text(row.get("patent_type"))
    return {
        "patent_id": str(row["patent_id"]),
        "patent_number": _coerce_optional_text(row.get("patent_number")),
        "old_type": old_type,
        "inferred_type": infer_patent_type(
            _coerce_optional_text(row.get("patent_number")),
            current_type=old_type,
        ),
        "old_quality_status": _coerce_optional_text(row.get("quality_status")),
        "new_quality_status": _coerce_optional_text(row.get("quality_status")),
    }


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, default=str))
            handle.write("\n")


def _apply_decision(
    conn: Any,
    *,
    decision: PatentTypeBackfillDecision,
    run_id: UUID | str,
) -> None:
    real_run_id = require_real_run_id(
        run_id,
        writer_name="run_patent_type_inference_backfill",
    )
    cursor = conn.execute(
        """
        UPDATE patent
           SET patent_type = %s,
               quality_status = %s,
               updated_at = now(),
               run_id = %s
         WHERE patent_id = %s
           AND (patent_type IS NULL OR btrim(patent_type) = '')
        """,
        (
            decision.inferred_type,
            decision.new_quality_status,
            real_run_id,
            decision.patent_id,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(
            "patent update skipped unexpectedly; patent_type may have changed "
            f"for patent_id={decision.patent_id}"
        )


def run_backfill(
    conn: Any,
    *,
    apply: bool,
    limit: int | None = None,
    json_output: Path | None = None,
    run_id: UUID | str | None = None,
) -> PatentTypeBackfillSummary:
    rows = _load_patent_rows(conn, limit=limit)
    decisions: list[PatentTypeBackfillDecision] = []
    events: list[dict[str, Any]] = []
    for row in rows:
        decision = build_backfill_decision(row)
        if decision is not None:
            decisions.append(decision)
        events.append(_json_event_for_row(row, decision))

    ready_degraded = sum(1 for decision in decisions if decision.is_ready_degraded)
    if apply and ready_degraded:
        raise RuntimeError(f"refusing to apply: ready_degraded={ready_degraded}")

    if apply:
        if run_id is None:
            raise ValueError("run_id is required for --apply")
        for decision in decisions:
            _apply_decision(conn, decision=decision, run_id=run_id)

    if json_output is not None:
        _write_jsonl(json_output, events)

    candidates = len(decisions)
    return PatentTypeBackfillSummary(
        examined=len(rows),
        candidates=candidates,
        promoted_to_ready=sum(
            1 for decision in decisions if decision.is_promoted_to_ready
        ),
        unchanged=len(rows) - candidates,
        ready_degraded=ready_degraded,
        dry_run=not apply,
        json_output=str(json_output) if json_output is not None else None,
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if not args.dsn:
        raise SystemExit("--dsn or DATABASE_URL is required")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")

    conn = _connect(args.dsn)
    run_id: UUID | str | None = None
    try:
        if args.apply:
            run_id = require_real_run_id(
                open_pipeline_run(
                    conn,
                    run_kind=_RUN_KIND,
                    run_scope={
                        "task": "patent_type_inference_backfill",
                        "limit": args.limit,
                        "json_output": str(args.json_output),
                    },
                    triggered_by=_TRIGGERED_BY,
                ),
                writer_name="run_patent_type_inference_backfill",
            )
            conn.commit()

        summary = run_backfill(
            conn,
            apply=args.apply,
            limit=args.limit,
            json_output=args.json_output,
            run_id=run_id,
        )

        if args.apply and run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="succeeded",
                items_processed=summary.examined,
                items_failed=0,
            )
            conn.commit()

        print(json.dumps(asdict(summary), ensure_ascii=False))
    except Exception as exc:
        if run_id is not None:
            conn.rollback()
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
