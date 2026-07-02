"""Merge exact-title paper duplicates that share one author list."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_APP_ROOT / ".env")
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.paper.dedup_merge import merge_paper_into_canonical  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "paper_exact_title_dedup"
_REAL_DB_NAME = "miroflow_real"
_FALSE_MERGE_THRESHOLD = 0.99
_IDENTIFIER_FIELDS = ("doi", "arxiv_id", "openalex_id", "semantic_scholar_id")
_RICHNESS_FIELDS = ("abstract_clean", "summary_zh", "venue", "year")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Tier-2 paper dedup: merge exact case-insensitive title duplicates "
            "that share one author list."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="mode",
        action="store_const",
        const="dry-run",
        default="dry-run",
        help="Preview candidate groups without writes (default).",
    )
    mode.add_argument(
        "--apply",
        dest="mode",
        action="store_const",
        const="apply",
        help="Apply merges. Requires --confirm-real-db when targeting miroflow_real.",
    )
    parser.add_argument("--confirm-real-db", action="store_true")
    parser.add_argument(
        "--limit", type=int, default=None, help="Max groups to process."
    )
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    args.dry_run = args.mode == "dry-run"
    return args


def _open_database_connection(url: str | None):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _build_candidate_sql(limit: int | None) -> tuple[str, tuple[Any, ...]]:
    sql = """
WITH g AS (
  SELECT lower(nullif(trim(title_clean::text),'')) t
  FROM paper
  WHERE nullif(trim(title_clean::text),'') IS NOT NULL
    AND coalesce(identity_status,'unverified') NOT IN ('rejected','merged')
  GROUP BY t HAVING count(*) > 1)
SELECT g.t, array_agg(p.paper_id ORDER BY p.paper_id) pids
FROM g JOIN paper p ON lower(trim(p.title_clean)) = g.t
WHERE coalesce(p.identity_status,'unverified') NOT IN ('rejected','merged')
GROUP BY g.t
HAVING count(DISTINCT lower(coalesce(p.authors_display,''))) = 1
  -- 2+ publisher DOIs usually means distinct publications (conf/journal
  -- extension), so route to Tier-3 review; preprint DOIs stay Tier-2.
  AND count(DISTINCT nullif(p.doi,''))
    - count(DISTINCT CASE WHEN p.doi LIKE '10.48550/arxiv.%%'
                           OR p.doi LIKE '10.2139/ssrn.%%'
                           OR p.doi LIKE '10.5194/egusphere-%%'
                          THEN nullif(p.doi,'') END) <= 1
ORDER BY g.t
"""
    params: list[Any] = []
    if limit is not None:
        sql += "LIMIT %s\n"
        params.append(int(limit))
    return sql, tuple(params)


def _fetch_candidate_groups(conn: Any, *, limit: int | None) -> list[dict[str, Any]]:
    sql, params = _build_candidate_sql(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _fetch_group_members(conn: Any, paper_ids: list[str]) -> list[dict[str, Any]]:
    if not paper_ids:
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT p.paper_id,
                   p.title_clean,
                   p.title_raw,
                   p.authors_display,
                   p.doi,
                   p.arxiv_id,
                   p.openalex_id,
                   p.semantic_scholar_id,
                   p.abstract_clean,
                   p.summary_zh,
                   p.venue,
                   p.year,
                   p.identity_status,
                   p.quality_status,
                   p.canonical_source,
                   COALESCE(active_links.active_link_count, 0) AS active_link_count
              FROM paper p
              LEFT JOIN (
                   SELECT paper_id, count(*)::int AS active_link_count
                     FROM professor_paper_link
                    WHERE link_status != 'rejected'
                    GROUP BY paper_id
              ) active_links ON active_links.paper_id = p.paper_id
             WHERE p.paper_id = ANY(%s)
             ORDER BY p.paper_id
            """,
            (paper_ids,),
        ).fetchall()
    ]


def _pick_canonical_member(members: list[dict[str, Any]]) -> dict[str, Any]:
    if not members:
        raise ValueError("members is required")
    return min(
        members,
        key=lambda row: (
            -int(_has_identifier(row)),
            -_richness(row),
            _required_str(row.get("paper_id"), "paper_id"),
        ),
    )


def _process_candidate_groups(
    conn: Any,
    groups: list[dict[str, Any]],
    *,
    dry_run: bool,
    run_id: UUID | str,
) -> dict[str, Any]:
    report = _empty_report(
        run_id=run_id,
        mode="dry-run" if dry_run else "apply",
        groups_total=len(groups),
        rows_total=sum(len(_paper_ids_from_group(group)) for group in groups),
    )
    for group in groups:
        paper_ids = _paper_ids_from_group(group)
        members = _fetch_group_members(conn, paper_ids)
        if len(members) < 2:
            continue
        canonical = _pick_canonical_member(members)
        canonical_paper_id = _required_str(canonical.get("paper_id"), "paper_id")
        group_report = {
            "title_key": group.get("t"),
            "canonical_paper_id": canonical_paper_id,
            "member_paper_ids": [
                _required_str(member.get("paper_id"), "paper_id") for member in members
            ],
        }
        report["groups"].append(group_report)
        report["groups_processed"] += 1
        for member in members:
            old_paper_id = _required_str(member.get("paper_id"), "paper_id")
            if old_paper_id == canonical_paper_id:
                continue
            _record_false_merge_risk(
                report,
                group=group,
                member=member,
                canonical=canonical,
            )
            if dry_run:
                report["members_merged"] += 1
                report["links_migrated"] += _optional_int(
                    member.get("active_link_count")
                )
                continue
            counts = merge_paper_into_canonical(
                conn,
                old_paper_id=old_paper_id,
                canonical_paper_id=canonical_paper_id,
                run_id=run_id,
            )
            report["members_merged"] += counts["papers_marked_merged"]
            report["links_migrated"] += counts["links_migrated"]
            report["merge_aliases_written"] += counts["merge_aliases_written"]
            report["old_links_rejected"] += counts["old_links_rejected"]
            report["ready_degraded"] += counts["ready_degraded"]
        report["false_merge_count"] = len(report["false_merge_risk"])
        if not dry_run:
            conn.commit()
    report["false_merge_count"] = len(report["false_merge_risk"])
    return report


def _empty_report(
    *,
    run_id: UUID | str,
    mode: str,
    groups_total: int,
    rows_total: int,
) -> dict[str, Any]:
    return {
        "groups_total": groups_total,
        "rows_total": rows_total,
        "groups_processed": 0,
        "members_merged": 0,
        "links_migrated": 0,
        "merge_aliases_written": 0,
        "old_links_rejected": 0,
        "ready_degraded": 0,
        "false_merge_count": 0,
        "false_merge_risk": [],
        "run_id": run_id,
        "mode": mode,
        "groups": [],
    }


def _record_false_merge_risk(
    report: dict[str, Any],
    *,
    group: dict[str, Any],
    member: dict[str, Any],
    canonical: dict[str, Any],
) -> None:
    member_title = _display_title(member)
    canonical_title = _display_title(canonical)
    similarity = _title_similarity(member_title, canonical_title)
    if similarity >= _FALSE_MERGE_THRESHOLD:
        return
    report["false_merge_risk"].append(
        {
            "title_key": group.get("t"),
            "member_paper_id": member.get("paper_id"),
            "canonical_paper_id": canonical.get("paper_id"),
            "member_title": member_title,
            "canonical_title": canonical_title,
            "similarity": similarity,
        }
    )


def _title_similarity(left: object, right: object) -> float:
    """Normalized lower/whitespace-folded Levenshtein ratio."""
    left_text = _normalize_title(left)
    right_text = _normalize_title(right)
    if not left_text and not right_text:
        return 1.0
    if not left_text or not right_text:
        return 0.0
    distance = _levenshtein_distance(left_text, right_text)
    return 1.0 - (distance / max(len(left_text), len(right_text)))


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + int(left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _normalize_title(value: object) -> str:
    text = _optional_str(value)
    if text is None:
        return ""
    return " ".join(text.casefold().split())


def _display_title(row: dict[str, Any]) -> str:
    return (
        _optional_str(row.get("title_clean"))
        or _optional_str(row.get("title_raw"))
        or ""
    )


def _paper_ids_from_group(group: dict[str, Any]) -> list[str]:
    raw = group.get("pids") or []
    return [str(item) for item in raw]


def _has_identifier(row: dict[str, Any]) -> bool:
    return any(
        _optional_str(row.get(field)) is not None for field in _IDENTIFIER_FIELDS
    )


def _richness(row: dict[str, Any]) -> int:
    return sum(_optional_str(row.get(field)) is not None for field in _RICHNESS_FIELDS)


def _required_str(value: object, field_name: str) -> str:
    text = _optional_str(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _print_report(report: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, default=str))
        return
    print(f"mode: {report['mode']}")
    print(f"run_id: {report['run_id']}")
    print(f"groups_total: {report['groups_total']}")
    print(f"rows_total: {report['rows_total']}")
    print(f"groups_processed: {report['groups_processed']}")
    print(f"members_merged: {report['members_merged']}")
    print(f"links_migrated: {report['links_migrated']}")
    print(f"merge_aliases_written: {report['merge_aliases_written']}")
    print(f"old_links_rejected: {report['old_links_rejected']}")
    print(f"ready_degraded: {report['ready_degraded']}")
    print(f"false_merge_count: {report['false_merge_count']}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = resolve_dsn(args.database_url)
    if args.mode == "apply" and _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing miroflow_real --apply without --confirm-real-db.", file=sys.stderr
        )
        return 2

    conn = _open_database_connection(args.database_url)
    run_id: UUID | str | None = None
    try:
        if args.dry_run:
            run_id = f"dry-run-{uuid4()}"
        else:
            run_id = open_pipeline_run(
                conn,
                run_kind=_RUN_KIND,
                run_scope={
                    "task": "paper_exact_title_dedup",
                    "limit": args.limit,
                    "mode": args.mode,
                },
                triggered_by=_TRIGGERED_BY,
            )
            run_id = require_real_run_id(
                run_id,
                writer_name="run_paper_exact_title_dedup",
            )
            conn.commit()

        groups = _fetch_candidate_groups(conn, limit=args.limit)
        report = _process_candidate_groups(
            conn,
            groups,
            dry_run=args.dry_run,
            run_id=run_id,
        )
        if not args.dry_run:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if report["false_merge_count"] else "succeeded",
                items_processed=report["groups_processed"],
                items_failed=report["false_merge_count"],
            )
            conn.commit()
        _print_report(report, json_output=args.json_output)
        return 0
    except Exception as exc:
        if run_id is not None and not args.dry_run:
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
        close_conn = getattr(conn, "close", None)
        if callable(close_conn):
            close_conn()


if __name__ == "__main__":
    raise SystemExit(main())
