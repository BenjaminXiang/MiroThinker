#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from src.data_agents.storage.postgres.connection import connect

FIELD_NAMES = (
    "profile_summary_ge200",
    "research_overview",
    "research_directions",
    "education",
    "academic_position",
    "work_experience",
    "award",
    "contact",
)
FACT_FIELD_TYPES = {
    "research_directions": "research_topic",
    "education": "education",
    "academic_position": "academic_position",
    "work_experience": "work_experience",
    "award": "award",
    "contact": "contact",
}


def main() -> int:
    args = _parse_args()
    rows = run_audit(dsn=args.dsn, institution=args.institution)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db": _db_label(args.dsn),
        "institution_filter": args.institution,
        "per_school": rows,
    }
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_audit(
    *, dsn: str | None, institution: str | None = None
) -> list[dict[str, Any]]:
    with connect(dsn) as conn:
        conn.row_factory = dict_row
        professor_rows = conn.execute(
            """
            WITH primary_affiliation AS (
                SELECT DISTINCT ON (pa.professor_id)
                       pa.professor_id,
                       pa.institution
                  FROM professor_affiliation pa
                 WHERE pa.institution IS NOT NULL
                   AND trim(pa.institution) <> ''
                 ORDER BY pa.professor_id,
                          pa.is_primary DESC,
                          pa.is_current DESC,
                          pa.updated_at DESC NULLS LAST,
                          pa.created_at DESC NULLS LAST
            )
            SELECT p.professor_id,
                   primary_affiliation.institution,
                   p.profile_summary
              FROM professor p
              JOIN primary_affiliation
                ON primary_affiliation.professor_id = p.professor_id
             WHERE p.identity_status <> 'merged_into'
               AND COALESCE(p.lifecycle_state, 'active') = 'active'
               AND (%s IS NULL OR primary_affiliation.institution = %s)
             ORDER BY primary_affiliation.institution, p.professor_id
            """,
            (institution, institution),
        ).fetchall()
        professor_ids = [str(row["professor_id"]) for row in professor_rows]
        fact_presence = _load_fact_presence(conn, professor_ids)
        overview_presence = _load_research_overview_presence(conn, professor_ids)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in professor_rows:
        grouped.setdefault(str(row["institution"]), []).append(row)

    results: list[dict[str, Any]] = []
    for school, rows in grouped.items():
        total = len(rows)
        counts = {field: 0 for field in FIELD_NAMES}
        for row in rows:
            professor_id = str(row["professor_id"])
            if _has_summary(row.get("profile_summary")):
                counts["profile_summary_ge200"] += 1
            if professor_id in overview_presence:
                counts["research_overview"] += 1
            for field, fact_type in FACT_FIELD_TYPES.items():
                if fact_type in fact_presence.get(professor_id, set()):
                    counts[field] += 1

        record: dict[str, Any] = {"institution": school, "profs": total}
        for field in FIELD_NAMES:
            record[field] = _percent(counts[field], total)
        record["field_counts"] = {
            field: {
                "filled": counts[field],
                "total": total,
                "fill_rate": _rate(counts[field], total),
            }
            for field in FIELD_NAMES
        }
        results.append(record)
    return results


def _load_fact_presence(conn: Any, professor_ids: list[str]) -> dict[str, set[str]]:
    if not professor_ids:
        return {}
    rows = conn.execute(
        """
        SELECT professor_id, fact_type
          FROM professor_fact
         WHERE professor_id = ANY(%s)
           AND status = 'active'
           AND trim(value_raw) <> ''
           AND fact_type = ANY(%s)
         GROUP BY professor_id, fact_type
        """,
        (professor_ids, list(FACT_FIELD_TYPES.values())),
    ).fetchall()
    presence: dict[str, set[str]] = {}
    for row in rows:
        presence.setdefault(str(row["professor_id"]), set()).add(str(row["fact_type"]))
    return presence


def _load_research_overview_presence(conn: Any, professor_ids: list[str]) -> set[str]:
    if not professor_ids:
        return set()
    rows = conn.execute(
        """
        SELECT professor_id
          FROM professor_profile_section
         WHERE professor_id = ANY(%s)
           AND section_type = 'research_overview'
           AND trim(content) <> ''
         GROUP BY professor_id
        """,
        (professor_ids,),
    ).fetchall()
    return {str(row["professor_id"]) for row in rows}


def _has_summary(value: Any) -> bool:
    return len(str(value or "").strip()) >= 200


def _percent(filled: int, total: int) -> int:
    return int(round(100 * _rate(filled, total)))


def _rate(filled: int, total: int) -> float:
    return filled / total if total else 0.0


def _db_label(dsn: str | None) -> str:
    value = (
        dsn or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN") or ""
    )
    return value.rsplit("/", 1)[-1] if value else "default"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only per-school professor field-completeness audit."
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN"),
        help="Postgres DSN. Defaults to DATABASE_URL or POSTGRES_DSN.",
    )
    parser.add_argument(
        "--institution",
        help="Optional exact institution filter, e.g. 哈尔滨工业大学（深圳）.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON artifact path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
