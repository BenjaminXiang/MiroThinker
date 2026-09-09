#!/usr/bin/env python
"""Acquire a DOI for no-DOI papers by title search against OpenAlex, then confirm.

Targets ready+unverified papers with no DOI. For each, searches OpenAlex by
title, matches the top results against the DB title (>= threshold), and on a
match writes the resolved DOI + flips identity_status to 'confirmed'. Papers not
found (or mismatched) are left unverified (genuine source gap).

Safe by default: --dry-run; --apply writes. Every acquisition is JSONL-archived.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from difflib import SequenceMatcher

import httpx
import psycopg
from psycopg.types.json import Json

from src.data_agents.paper.title_cleaner import clean_paper_title

_TITLE_MATCH_THRESHOLD = 0.85
_OPENALEX = "https://api.openalex.org/works"
_MAILTO = "mirothinker-dev@sustech.edu.cn"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def _ratio(a: str, b: str) -> float:
    na, nb = _norm(clean_paper_title(a)), _norm(clean_paper_title(b))
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _search_openalex(client: httpx.Client, title: str) -> list[dict]:
    try:
        r = client.get(_OPENALEX, params={"search": title, "per-page": 5, "mailto": _MAILTO})
        if r.status_code != 200:
            return []
        return (r.json() or {}).get("results") or []
    except Exception:  # noqa: BLE001
        return []


def _strip_doi(doi_url: str | None) -> str | None:
    if not doi_url:
        return None
    return doi_url[16:] if doi_url.lower().startswith("https://doi.org/") else doi_url


def main() -> int:
    p = argparse.ArgumentParser(description="Acquire DOI via OpenAlex title search.")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--apply", action="store_true", help="write (default: dry-run).")
    p.add_argument("--sleep", type=float, default=1.0)
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL or --dsn required")
    if "+psycopg" in args.dsn:
        args.dsn = args.dsn.replace("postgresql+psycopg://", "postgresql://")

    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT paper_id, title_clean FROM paper "
            "WHERE quality_status='ready' AND identity_status='unverified' "
            "AND (doi IS NULL OR doi = '')"
        )
        targets = cur.fetchall()

    mode = "APPLY" if args.apply else "DRY-RUN"
    archive_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "..", ".agents", "runs", "paper-title-to-doi",
        f"{'apply' if args.apply else 'dryrun'}-2026-06-24.jsonl",
    )
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_run(run_id,run_kind,run_scope,started_at,status,created_at,triggered_by,finished_at)"
            " VALUES(%s,'backfill_real',%s,now(),'succeeded',now(),'paper_title_to_doi',now())",
            (run_id, Json({"purpose": "paper_title_to_doi"})),
        )
        conn.commit()
    print(f"{mode} | {len(targets)} no-DOI papers | archive={archive_path}")

    acquired = merged = nomatch = notfound = 0
    client_headers = {"User-Agent": f"MiroThinker/1.0 (mailto:{_MAILTO})"}
    with open(archive_path, "w", encoding="utf-8") as archive, httpx.Client(
        timeout=30.0, trust_env=True, follow_redirects=True, headers=client_headers,
    ) as client:
        for pid, db_title in targets:
            results = _search_openalex(client, clean_paper_title(db_title) or db_title)
            if not results:
                notfound += 1
                archive.write(json.dumps({"paper_id": pid, "db_title": (db_title or "")[:120], "outcome": "not_found"}, ensure_ascii=False) + "\n")
                time.sleep(args.sleep)
                continue
            best = max(results, key=lambda w: _ratio(db_title, w.get("title") or ""))
            ratio = _ratio(db_title, best.get("title") or "")
            doi = _strip_doi(best.get("doi"))
            if ratio >= _TITLE_MATCH_THRESHOLD and doi:
                # If the DOI already exists on ANOTHER paper, this no-DOI row is a
                # duplicate -> mark it 'merged' (excluded from indexing) rather
                # than violating uq_paper_doi.
                with conn.cursor() as cur:
                    cur.execute("SELECT paper_id FROM paper WHERE doi=%s AND paper_id<>%s", (doi, pid))
                    survivor = cur.fetchone()
                if survivor:
                    merged += 1
                    archive.write(json.dumps({"paper_id": pid, "db_title": (db_title or "")[:120], "doi": doi, "survivor": survivor[0], "ratio": round(ratio, 3), "outcome": "merged_duplicate"}, ensure_ascii=False) + "\n")
                    if args.apply:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE paper SET identity_status='merged', run_id=%s, updated_at=now() "
                                "WHERE paper_id=%s AND identity_status='unverified'",
                                (run_id, pid),
                            )
                        conn.commit()
                    print(f"  MERGE (dup of {survivor[0]}) doi={doi[:32]} ratio={ratio:.2f}  {str(db_title)[:36]}")
                else:
                    acquired += 1
                    archive.write(json.dumps({"paper_id": pid, "db_title": (db_title or "")[:120], "matched_title": (best.get("title") or "")[:120], "doi": doi, "ratio": round(ratio, 3), "outcome": "acquired"}, ensure_ascii=False) + "\n")
                    if args.apply:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE paper SET doi=%s, identity_status='confirmed', run_id=%s, updated_at=now() "
                                "WHERE paper_id=%s AND identity_status='unverified'",
                                (doi, run_id, pid),
                            )
                        conn.commit()
                    print(f"  ACQUIRE doi={doi[:38]} ratio={ratio:.2f}  {str(db_title)[:42]}")
            else:
                nomatch += 1
                archive.write(json.dumps({"paper_id": pid, "db_title": (db_title or "")[:120], "best_title": (best.get("title") or "")[:120], "ratio": round(ratio, 3), "outcome": "no_match"}, ensure_ascii=False) + "\n")
            time.sleep(args.sleep)

    print(f"\n{mode} done. acquired={acquired} merged={merged} no_match={nomatch} not_found={notfound}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
