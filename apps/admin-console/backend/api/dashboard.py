from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api")


class DomainStats(BaseModel):
    name: str
    count: int
    quality: dict[str, int]
    last_updated: str | None


class DashboardResponse(BaseModel):
    domains: list[DomainStats]


# Round 9 — read from Postgres canonical tables, not the legacy
# `released_objects.db` snapshot. The SQLite store was frozen several
# rounds ago and showed stale counts (19 profs / 1037 companies / 208
# papers / 1931 patents) even though Postgres has the current truth
# (783 resolved profs / 1024 companies / 7297 papers / 0 patents).


def _professor_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*) FILTER (WHERE identity_status = 'resolved')::int AS ready,
               count(*) FILTER (WHERE identity_status = 'needs_review')::int AS needs_review,
               count(*) FILTER (WHERE identity_status = 'inactive')::int AS inactive,
               count(*) FILTER (WHERE identity_status = 'merged_into')::int AS merged,
               max(updated_at) AS last_updated
          FROM professor
        """
    ).fetchone()
    count = (row["ready"] or 0)
    quality = {
        "ready": row["ready"] or 0,
        "needs_review": row["needs_review"] or 0,
    }
    if row["inactive"]:
        quality["inactive"] = row["inactive"]
    if row["merged"]:
        quality["merged"] = row["merged"]
    return DomainStats(
        name="professor",
        count=count,
        quality=quality,
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _company_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total,
               count(*) FILTER (WHERE is_shenzhen = true)::int AS shenzhen,
               max(updated_at) AS last_updated
          FROM company
        """
    ).fetchone()
    return DomainStats(
        name="company",
        count=row["total"] or 0,
        quality={
            "ready": row["total"] or 0,
            "shenzhen": row["shenzhen"] or 0,
        },
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _paper_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total,
               count(*) FILTER (WHERE title_clean IS NOT NULL)::int AS with_title,
               count(*) FILTER (WHERE title_clean IS NULL)::int AS missing_title,
               max(updated_at) AS last_updated
          FROM paper
        """
    ).fetchone()
    quality = {"ready": row["with_title"] or 0}
    if row["missing_title"]:
        quality["missing_title"] = row["missing_title"]
    return DomainStats(
        name="paper",
        count=row["total"] or 0,
        quality=quality,
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _patent_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total, max(updated_at) AS last_updated
          FROM patent
        """
    ).fetchone()
    return DomainStats(
        name="patent",
        count=row["total"] or 0,
        quality={"ready": row["total"] or 0},
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(conn: Any = Depends(get_pg_conn)) -> DashboardResponse:
    return DashboardResponse(
        domains=[
            _professor_stats(conn),
            _company_stats(conn),
            _paper_stats(conn),
            _patent_stats(conn),
        ]
    )
