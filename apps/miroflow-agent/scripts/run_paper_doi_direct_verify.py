#!/usr/bin/env python
"""DOI-DIRECT identity verification for unverified papers that already carry a DOI.

`run_paper_doi_verify.py` resolves by TITLE (cached/OpenAlex/arXiv) and yields
nothing for DOI-bearing chemistry / Chinese-titled papers that aren't on arXiv.
This script does the complementary, higher-precision lookup: resolve each paper's
EXISTING DOI directly on Crossref (the DOI authority) and OpenAlex, fetch the
authoritative title, and confirm `identity_status` only when the resolved title
matches the DB title (>= threshold). A DOI that doesn't resolve, or resolves to a
mismatching title, is left unverified (it may be mis-extracted from a prof page).

Safe by default: --dry-run prints the plan; --apply writes. Every confirmation
is logged to JSONL (reversible).
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
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_CROSSREF = "https://api.crossref.org/works"
_OPENALEX = "https://api.openalex.org/works"
_MAILTO = "mirothinker-dev@sustech.edu.cn"  # polite pool


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def _title_ratio(a: str, b: str) -> float:
    na, nb = _normalize_title(clean_paper_title(a)), _normalize_title(clean_paper_title(b))
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _fetch_crossref_title(client: httpx.Client, doi: str) -> str | None:
    try:
        r = client.get(f"{_CROSSREF}/{doi}", params={"mailto": _MAILTO})
        if r.status_code != 200:
            return None
        msg = (r.json() or {}).get("message") or {}
        titles = msg.get("title") or []
        return titles[0] if titles else None
    except Exception:  # noqa: BLE001
        return None


def _fetch_openalex_title(client: httpx.Client, doi: str) -> str | None:
    try:
        r = client.get(f"{_OPENALEX}/doi:{doi}")
        if r.status_code != 200:
            return None
        return (r.json() or {}).get("title")
    except Exception:  # noqa: BLE001
        return None


def _resolve_doi_title(client: httpx.Client, doi: str) -> tuple[str | None, str]:
    t = _fetch_crossref_title(client, doi)
    if t:
        return t, "crossref"
    t = _fetch_openalex_title(client, doi)
    return (t, "openalex") if t else (None, "")


def main() -> int:
    p = argparse.ArgumentParser(description="DOI-direct identity verification.")
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
            "SELECT paper_id, doi, title_clean FROM paper "
            "WHERE quality_status='ready' AND identity_status='unverified' "
            "AND doi IS NOT NULL AND doi <> ''"
        )
        rows = cur.fetchall()

    targets = [(pid, doi, (ttl or "")) for pid, doi, ttl in rows if _DOI_RE.match(doi or "")]
    mode = "APPLY" if args.apply else "DRY-RUN"
    archive_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "..", ".agents", "runs", "paper-doi-direct-verify",
        f"{'apply' if args.apply else 'dryrun'}-2026-06-24.jsonl",
    )
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_run(run_id,run_kind,run_scope,started_at,status,created_at,triggered_by,finished_at)"
            " VALUES(%s,'backfill_real',%s,now(),'succeeded',now(),'paper_doi_direct_verify',now())",
            (run_id, Json({"purpose": "paper_doi_direct_verify"})),
        )
        conn.commit()
    print(f"{mode} | {len(targets)} DOI-bearing unverified papers | archive={archive_path}")

    confirmed = mismatch = unresolved = 0
    client_headers = {"User-Agent": f"MiroThinker/1.0 (mailto:{_MAILTO})"}
    with open(archive_path, "w", encoding="utf-8") as archive, httpx.Client(
        timeout=30.0, trust_env=True, follow_redirects=True, headers=client_headers,
    ) as client:
        for pid, doi, db_title in targets:
            resolved_title, source = _resolve_doi_title(client, doi)
            if not resolved_title:
                unresolved += 1
                archive.write(json.dumps({"paper_id": pid, "doi": doi, "outcome": "unresolved"}, ensure_ascii=False) + "\n")
                time.sleep(args.sleep)
                continue
            ratio = _title_ratio(db_title, resolved_title)
            outcome = "confirmed" if ratio >= _TITLE_MATCH_THRESHOLD else "title_mismatch"
            archive.write(json.dumps({
                "paper_id": pid, "doi": doi, "source": source,
                "db_title": db_title[:120], "resolved_title": resolved_title[:120],
                "title_ratio": round(ratio, 3), "outcome": outcome,
            }, ensure_ascii=False) + "\n")
            if outcome == "confirmed":
                confirmed += 1
                if args.apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE paper SET identity_status='confirmed', run_id=%s, updated_at=now() "
                            "WHERE paper_id=%s AND identity_status='unverified'",
                            (run_id, pid),
                        )
                    conn.commit()
                print(f"  CONFIRM [{source}] {doi[:40]} ratio={ratio:.2f}")
            else:
                mismatch += 1
                print(f"  MISMATCH [{source}] {doi[:40]} ratio={ratio:.2f}: {resolved_title[:50]}")
            time.sleep(args.sleep)

    print(f"\n{mode} done. confirmed={confirmed} mismatch={mismatch} unresolved={unresolved}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
