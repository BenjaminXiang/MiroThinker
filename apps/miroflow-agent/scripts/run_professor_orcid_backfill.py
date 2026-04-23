"""M1 follow-up — populate professor_orcid table from OpenAlex.

Queries OpenAlex `/authors` for each professor by name + institution.
When a high-confidence match has a non-null ORCID, writes via
upsert_professor_orcid. Idempotent; supports --dry-run / --resume / --limit.

Per-prof errors (OpenAlex 429 / network / malformed response) are caught
and logged; the run continues. Rate gate: 0.1s between OpenAlex calls
(matches paper/title_resolver.py convention — 10 req/s OpenAlex limit).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.storage.postgres.professor_orcid import (  # noqa: E402
    upsert_professor_orcid,
)

logger = logging.getLogger("run_professor_orcid_backfill")

_OPENALEX_AUTHORS_ENDPOINT = "https://api.openalex.org/authors"
_OPENALEX_RATE_INTERVAL = 0.1  # seconds between calls
_DEFAULT_TIMEOUT = 30.0
_ORCID_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?orcid\.org/(?P<orcid>\d{4}-\d{4}-\d{4}-\d{3}[\dX])/?$",
    re.IGNORECASE,
)


class _RateLimitGate:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last_called_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_called_at is not None:
                elapsed = now - self._last_called_at
                if elapsed < self._min_interval:
                    time.sleep(self._min_interval - elapsed)
            self._last_called_at = time.monotonic()


_OPENALEX_GATE = _RateLimitGate(_OPENALEX_RATE_INTERVAL)


def _strip_orcid_url(raw: str | None) -> str | None:
    """Turn 'https://orcid.org/0000-0001-2345-6789' → '0000-0001-2345-6789'."""
    if not raw:
        return None
    stripped = raw.strip()
    match = _ORCID_URL_RE.match(stripped)
    if match:
        return match.group("orcid").upper()
    # Already bare form?
    if re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", stripped):
        return stripped.upper()
    return None


def _fetch_openalex_author(
    name: str,
    institution: str,
    *,
    http_client: httpx.Client | None = None,
) -> dict | None:
    """Return the best-matching OpenAlex author record, or None.

    Match criteria (in order):
      1. display_name exactly matches `name`, AND any affiliation's
         institution.display_name contains `institution`
      2. display_name matches `name` (any affiliation)
      3. None — caller treats as no match
    """
    _OPENALEX_GATE.wait()
    params = {
        "search": name,
        "per-page": 25,
        "select": "id,display_name,orcid,affiliations,works_count,cited_by_count",
    }
    owned_client = http_client is None
    client = http_client or httpx.Client(
        trust_env=False, timeout=_DEFAULT_TIMEOUT, follow_redirects=True
    )
    try:
        response = client.get(_OPENALEX_AUTHORS_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAlex fetch failed for %r: %s", name, exc)
        if owned_client:
            client.close()
        return None

    if owned_client:
        client.close()

    authors = payload.get("results") or []
    exact_matches = [
        a for a in authors if (a.get("display_name") or "").strip() == name
    ]
    name_pool = exact_matches or authors

    # Prefer author whose any affiliation matches institution.
    inst_lower = institution.lower().strip() if institution else ""
    if inst_lower:
        for author in name_pool:
            for aff in author.get("affiliations") or []:
                inst_obj = aff.get("institution") or {}
                disp = (inst_obj.get("display_name") or "").lower()
                if disp and inst_lower in disp:
                    return author
    # Fall back to first name-matched candidate (no institution verification).
    if name_pool:
        return name_pool[0]
    return None


def _score_author_match(author: dict, prof: dict) -> float:
    """Confidence score for the match quality.

    0.9 if institution verified, 0.7 if only name matches.
    """
    target_inst = (prof.get("institution") or "").lower().strip()
    if not target_inst:
        return 0.7
    for aff in author.get("affiliations") or []:
        inst_obj = aff.get("institution") or {}
        disp = (inst_obj.get("display_name") or "").lower()
        if disp and target_inst in disp:
            return 0.9
    return 0.7


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _build_select_sql(
    *, limit: int | None, institution: str | None, prof_id: str | None
) -> tuple[str, tuple]:
    clauses = ["homepage_url IS NOT NULL OR canonical_name IS NOT NULL"]
    params: list = []
    if institution:
        clauses.append("institution ILIKE %s")
        params.append(f"%{institution}%")
    if prof_id:
        clauses.append("professor_id = %s")
        params.append(prof_id)
    sql = (
        "SELECT professor_id, canonical_name, institution "
        "  FROM professor "
        f" WHERE {' AND '.join(clauses)} "
        " ORDER BY professor_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping corrupted resume line: %s", line[:80])
                continue
            if isinstance(row, dict) and isinstance(row.get("prof_id"), str):
                ids.add(row["prof_id"])
    return ids


def _append_checkpoint(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill professor_orcid from OpenAlex /authors."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--institution", type=str, default=None)
    parser.add_argument("--prof-id", type=str, default=None)
    parser.add_argument("--resume", nargs="?", const="", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print(
            "ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...",
            file=sys.stderr,
        )
        sys.exit(1)

    run_id = str(uuid.uuid4())
    conn = _open_database_connection(dsn)

    checkpoint_base = (
        _REPO_ROOT / "logs" / "data_agents" / "professor" / "orcid_backfill_runs"
    )
    if args.resume is not None:
        resume_path = (
            Path(args.resume) if args.resume else checkpoint_base / f"{run_id}.jsonl"
        )
    else:
        resume_path = None
    resume_ids = _load_resume_ids(resume_path) if resume_path else set()
    new_checkpoint_path = checkpoint_base / f"{run_id}.jsonl"

    sql, params = _build_select_sql(
        limit=args.limit,
        institution=args.institution,
        prof_id=args.prof_id,
    )
    prof_rows = conn.execute(sql, params).fetchall()

    report = {
        "run_id": run_id,
        "profs_total": len(prof_rows),
        "profs_processed": 0,
        "profs_skipped_resume": 0,
        "orcids_written": 0,
        "orcids_not_found": 0,
        "profs_with_errors": 0,
        "dry_run": args.dry_run,
    }

    started = time.monotonic()
    for prof in prof_rows:
        prof_id = str(prof["professor_id"])
        if prof_id in resume_ids:
            report["profs_skipped_resume"] += 1
            continue
        report["profs_processed"] += 1

        try:
            author = _fetch_openalex_author(
                str(prof.get("canonical_name") or ""),
                str(prof.get("institution") or ""),
            )
        except Exception as exc:  # defensive — the helper already catches
            logger.warning("Prof %s fetch crashed: %s", prof_id, exc)
            report["profs_with_errors"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {"prof_id": prof_id, "status": "error", "error": str(exc)},
            )
            continue

        if author is None:
            report["orcids_not_found"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {"prof_id": prof_id, "status": "no_author_match"},
            )
            continue

        bare_orcid = _strip_orcid_url(author.get("orcid"))
        if not bare_orcid:
            report["orcids_not_found"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {"prof_id": prof_id, "status": "author_has_no_orcid"},
            )
            continue

        confidence = _score_author_match(author, prof)
        if not args.dry_run:
            try:
                upsert_professor_orcid(
                    conn,
                    professor_id=prof_id,
                    orcid=bare_orcid,
                    source="openalex",
                    confidence=confidence,
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Persist failed for prof %s: %s", prof_id, exc)
                report["profs_with_errors"] += 1
                _append_checkpoint(
                    new_checkpoint_path,
                    {
                        "prof_id": prof_id,
                        "status": "persist_error",
                        "error": str(exc),
                        "orcid": bare_orcid,
                    },
                )
                continue

        report["orcids_written"] += 1
        _append_checkpoint(
            new_checkpoint_path,
            {
                "prof_id": prof_id,
                "status": "written" if not args.dry_run else "dry_run_success",
                "orcid": bare_orcid,
                "confidence": confidence,
            },
        )

    report["duration_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
