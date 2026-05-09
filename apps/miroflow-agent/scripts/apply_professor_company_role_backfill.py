#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.link_backfill import (  # noqa: E402
    _infer_role_type,
    safe_upsert_professor_company_role,
)


@dataclass(frozen=True, slots=True)
class BackfillItem:
    professor_name: str
    company_name: str
    role: str
    source_url: str
    snippet: str | None
    confidence: float | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply professor-company role JSONL backfills to Postgres."
    )
    parser.add_argument(
        "--backfill",
        type=Path,
        default=REPO_ROOT / "docs/source_backfills/professor_company_roles.jsonl",
        help="JSONL backfill file. Defaults to docs/source_backfills/professor_company_roles.jsonl.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST"),
        help="Postgres DSN. Defaults to DATABASE_URL or DATABASE_URL_TEST.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write rows. Without this flag the script only resolves and reports.",
    )
    parser.add_argument(
        "--link-status",
        choices=("candidate", "verified"),
        default="candidate",
        help=(
            "Status to write when --apply is set. Candidate links are visible "
            "to current retrieval and need an explicit override."
        ),
    )
    parser.add_argument(
        "--allow-candidate-serving-link",
        action="store_true",
        help=(
            "Allow --apply with --link-status candidate. Use only when the "
            "team accepts that current retrieval may surface this relation."
        ),
    )
    return parser.parse_args()


def _load_backfills(path: Path) -> list[BackfillItem]:
    items: list[BackfillItem] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        try:
            items.append(
                BackfillItem(
                    professor_name=str(payload["professor_name"]).strip(),
                    company_name=str(payload["company_name"]).strip(),
                    role=str(payload["role"]).strip(),
                    source_url=str(payload["source_url"]).strip(),
                    snippet=payload.get("snippet"),
                    confidence=payload.get("confidence"),
                )
            )
        except KeyError as exc:
            raise ValueError(f"{path}:{line_number} missing required key {exc}") from exc
    return items


def _compact_name(value: str) -> str:
    return "".join(value.casefold().split())


def _one_match(rows: list[dict[str, Any]], *, label: str, name: str) -> dict[str, Any] | None:
    if not rows:
        print(f"{label}_resolve=MISS name={name}")
        return None
    best_score = rows[0]["match_score"]
    tied = [row for row in rows if row["match_score"] == best_score]
    if len(tied) > 1:
        ids = ",".join(str(row.get("id")) for row in tied)
        print(f"{label}_resolve=AMBIGUOUS name={name} ids={ids}")
        return None
    return rows[0]


def _resolve_professor(conn: psycopg.Connection, name: str) -> dict[str, Any] | None:
    compact = _compact_name(name)
    rows = conn.execute(
        """
        SELECT professor_id AS id,
               canonical_name AS name,
               canonical_name_zh,
               CASE
                 WHEN canonical_name = %(name)s THEN 0
                 WHEN canonical_name_zh = %(name)s THEN 0
                 WHEN %(name)s = ANY(aliases) THEN 1
                 WHEN regexp_replace(lower(canonical_name), '\\s+', '', 'g') = %(compact)s THEN 2
                 WHEN regexp_replace(lower(coalesce(canonical_name_zh, '')), '\\s+', '', 'g') = %(compact)s THEN 2
                 ELSE 9
               END AS match_score
          FROM professor
         WHERE identity_status = 'resolved'
           AND (
             canonical_name = %(name)s
             OR canonical_name_zh = %(name)s
             OR %(name)s = ANY(aliases)
             OR regexp_replace(lower(canonical_name), '\\s+', '', 'g') = %(compact)s
             OR regexp_replace(lower(coalesce(canonical_name_zh, '')), '\\s+', '', 'g') = %(compact)s
           )
         ORDER BY match_score ASC, professor_id ASC
         LIMIT 5
        """,
        {"name": name, "compact": compact},
    ).fetchall()
    return _one_match(list(rows), label="professor", name=name)


def _resolve_company(conn: psycopg.Connection, name: str) -> dict[str, Any] | None:
    compact = _compact_name(name)
    rows = conn.execute(
        """
        SELECT company_id AS id,
               canonical_name AS name,
               registered_name,
               CASE
                 WHEN canonical_name = %(name)s THEN 0
                 WHEN registered_name = %(name)s THEN 0
                 WHEN %(name)s = ANY(aliases) THEN 1
                 WHEN regexp_replace(lower(canonical_name), '\\s+', '', 'g') = %(compact)s THEN 2
                 WHEN regexp_replace(lower(coalesce(registered_name, '')), '\\s+', '', 'g') = %(compact)s THEN 2
                 WHEN EXISTS (
                   SELECT 1
                     FROM unnest(aliases) AS alias
                    WHERE regexp_replace(lower(alias), '\\s+', '', 'g') = %(compact)s
                 ) THEN 3
                 ELSE 9
               END AS match_score
          FROM company
         WHERE identity_status != 'inactive'
           AND (
             canonical_name = %(name)s
             OR registered_name = %(name)s
             OR %(name)s = ANY(aliases)
             OR regexp_replace(lower(canonical_name), '\\s+', '', 'g') = %(compact)s
             OR regexp_replace(lower(coalesce(registered_name, '')), '\\s+', '', 'g') = %(compact)s
             OR EXISTS (
               SELECT 1
                 FROM unnest(aliases) AS alias
                WHERE regexp_replace(lower(alias), '\\s+', '', 'g') = %(compact)s
             )
           )
         ORDER BY match_score ASC, company_id ASC
         LIMIT 5
        """,
        {"name": name, "compact": compact},
    ).fetchall()
    return _one_match(list(rows), label="company", name=name)


def _count_ding_roles(conn: psycopg.Connection) -> int:
    row = conn.execute(
        """
        SELECT count(*)::int AS count
          FROM professor p
          JOIN professor_company_role pcr ON pcr.professor_id = p.professor_id
          JOIN company c ON c.company_id = pcr.company_id
         WHERE (p.canonical_name = '丁文伯' OR p.canonical_name_zh = '丁文伯')
           AND c.canonical_name ILIKE '%无界智航%'
           AND pcr.link_status IN ('verified', 'candidate')
        """
    ).fetchone()
    return int(row["count"] if row else 0)


def main() -> int:
    args = _parse_args()
    print(f"backfill_file={args.backfill}")
    print(f"mode={'apply' if args.apply else 'dry_run'}")
    if not args.backfill.is_file():
        print("result=FAIL")
        print("reason=backfill_file_missing")
        return 1
    if not args.database_url:
        print("result=FAIL")
        print("reason=database_url_unset")
        return 1
    if (
        args.apply
        and args.link_status == "candidate"
        and not args.allow_candidate_serving_link
    ):
        print("result=FAIL")
        print("reason=candidate_links_are_serving_visible")
        print(
            "hint=rerun as dry-run, use --link-status verified after human review, "
            "or add --allow-candidate-serving-link for an accepted candidate"
        )
        return 1

    items = _load_backfills(args.backfill)
    print(f"loaded_count={len(items)}")
    resolved = 0
    applied = 0
    skipped = 0

    verified_by = "human_reviewed" if args.link_status == "verified" else None
    with psycopg.connect(args.database_url, connect_timeout=5, row_factory=dict_row) as conn:
        for item in items:
            professor = _resolve_professor(conn, item.professor_name)
            company = _resolve_company(conn, item.company_name)
            role_type = _infer_role_type(item.role)
            if professor is None or company is None or role_type is None:
                skipped += 1
                print(
                    "backfill_item=SKIPPED "
                    f"professor={item.professor_name} company={item.company_name} "
                    f"role={item.role} role_type={role_type}"
                )
                continue

            resolved += 1
            print(
                "backfill_item=RESOLVED "
                f"professor_id={professor['id']} company_id={company['id']} "
                f"role_type={role_type} source_url={item.source_url}"
            )
            if not args.apply:
                continue

            role_id = safe_upsert_professor_company_role(
                conn,
                professor_id=str(professor["id"]),
                company_id=str(company["id"]),
                role_type=role_type,
                link_status=args.link_status,
                evidence_source_type="trusted_media",
                evidence_url=item.source_url,
                match_reason=(
                    f"backfill source mentions {item.company_name} role "
                    f"'{item.role}' mapped to {role_type}"
                )[:200],
                source_ref=str(args.backfill.relative_to(REPO_ROOT))
                if args.backfill.is_relative_to(REPO_ROOT)
                else str(args.backfill),
                verified_by=verified_by,
                issue_details={
                    "professor_name": item.professor_name,
                    "company_name": item.company_name,
                    "role": item.role,
                    "source_url": item.source_url,
                    "confidence": item.confidence,
                },
            )
            if role_id is None:
                skipped += 1
                print("backfill_item=WRITE_FAILED")
            else:
                applied += 1
                print(f"backfill_item=APPLIED role_id={role_id}")

        ding_count = _count_ding_roles(conn)
        print(f"ding_company_role_count={ding_count}")

    print(f"resolved_count={resolved}")
    print(f"applied_count={applied}")
    print(f"skipped_count={skipped}")
    if skipped:
        print("result=FAIL")
        return 1
    if args.apply and applied == 0 and items:
        print("result=FAIL")
        print("reason=no_rows_applied")
        return 1
    print("result=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
