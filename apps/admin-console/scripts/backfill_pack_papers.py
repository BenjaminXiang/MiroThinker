"""P2: backfill serving-pack papers into the collection database.

Companion to ``backfill_pack_professors.py``. Same guarantees: pack ids kept,
single transaction, idempotent, dry-runnable, provenance recorded via
``canonical_source='pack_backfill'`` (V043) and a deterministic ``run_id``.

Deduping: a pack paper that already exists by id, DOI or normalized title is not
inserted again (the DOI/title matches are reported). Rows that exist only in the
collection database are never touched.

Usage::

    python scripts/backfill_pack_papers.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        [--dry-run] [--out /tmp/backfill-papers.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import uuid

import psycopg
from psycopg.types.json import Jsonb

RUN_ID_LABEL = "pack-backfill-20261028"
RUN_ID = str(uuid.uuid5(uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff"), RUN_ID_LABEL))
CANONICAL_SOURCE = "pack_backfill"
IDENTITY_STATUS = "unverified"


def load_pack_papers(pack: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')='paper'"
        )
        return [json.loads(raw) if isinstance(raw, str) else raw for (raw,) in rows]
    finally:
        connection.close()


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    text = str(value).strip()
    return text or None


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _author_names(authors: object) -> list[str]:
    if not isinstance(authors, (list, tuple)):
        return []
    names: list[str] = []
    for author in authors:
        if isinstance(author, dict):
            name = _text(author.get("name"))
            if name:
                names.append(name)
    return names


def plan(documents: list[dict], by_id: set[str], by_doi: dict[str, str], by_title: dict[str, str]) -> dict:
    to_insert: list[dict] = []
    matched_doi = 0
    matched_title = 0
    present = 0
    missing_title = 0
    for document in documents:
        pack_id = str(document.get("canonical_identity_id") or "")
        if pack_id in by_id:
            present += 1
            continue
        doi = _norm(document.get("doi"))
        if doi and doi in by_doi:
            matched_doi += 1
            continue
        title = _text(document.get("title")) or _text(document.get("title_zh"))
        if title and _norm(title) in by_title:
            matched_title += 1
            continue
        if not title:
            missing_title += 1
            continue
        to_insert.append(document)
    return {
        "pack": len(documents),
        "already_present": present,
        "matched_by_doi": matched_doi,
        "matched_by_title": matched_title,
        "to_insert": len(to_insert),
        "missing_title": missing_title,
        "inserts": to_insert,
    }


def apply(dsn: str, inserts: list[dict]) -> dict:
    written = 0
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO pipeline_run (run_id, run_kind, run_scope, started_at,"
                " status, triggered_by, created_at)"
                " VALUES (%s,'backfill_real',%s,now(),'succeeded','backfill',now())"
                " ON CONFLICT (run_id) DO NOTHING",
                (
                    RUN_ID,
                    Jsonb({"purpose": "pack paper backfill", "source": "serving-pack", "label": RUN_ID_LABEL}),
                ),
            )
            for document in inserts:
                title = _text(document.get("title")) or _text(document.get("title_zh"))
                authors = _author_names(document.get("authors"))
                cursor.execute(
                    "INSERT INTO paper (paper_id, canonical_source, title_clean, title_raw,"
                    " abstract_clean, authors_display, authors_raw, doi, arxiv_id, venue,"
                    " year, citation_count, summary_zh, quality_status,"
                    " identity_status, run_id, first_seen_at, updated_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())"
                    " ON CONFLICT (paper_id) DO NOTHING",
                    (
                        str(document.get("canonical_identity_id")),
                        CANONICAL_SOURCE,
                        title,
                        _text(document.get("title_zh")) or title,
                        _text(document.get("abstract")),
                        ", ".join(authors) or None,
                        Jsonb(document.get("authors") or []),
                        _text(document.get("doi")),
                        _text(document.get("arxiv_id")),
                        _text(document.get("venue")),
                        document.get("year"),
                        document.get("citation_count"),
                        _text(document.get("summary_zh")),
                        _text(document.get("quality_status")) or "needs_review",
                        IDENTITY_STATUS,
                        RUN_ID,
                    ),
                )
                written += 1
        connection.commit()
    return {"written": written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    documents = load_pack_papers(Path(args.pack))
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT paper_id, doi, title_clean FROM paper")
            rows = cursor.fetchall()
    by_id = {str(row[0]) for row in rows}
    by_doi = {_norm(row[1]): str(row[0]) for row in rows if row[1]}
    by_title = {_norm(row[2]): str(row[0]) for row in rows if row[2]}

    outcome = plan(documents, by_id, by_doi, by_title)
    summary = {key: value for key, value in outcome.items() if key != "inserts"}
    print(json.dumps(summary, ensure_ascii=False))

    if args.dry_run:
        if args.out:
            Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    applied = apply(args.dsn, outcome["inserts"])
    summary["applied"] = applied
    print(json.dumps(applied, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
