"""P4 S2: export papers as a build source bundle (released-object JSONL).

Same three-way merge as the professor exporter: collection database > original
source rows > pack documents, matched by DOI then normalized title (the source
uses UUID paper ids, the pack uses `paper-c-…`, so ids cannot be compared).

Output: deterministic JSONL, content-addressed file name, dry-runnable.

Usage::

    python scripts/export_papers_source.py \
        --pack <dir> --dsn <url> --source <paper .source file> \
        --out <dir> [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

import psycopg

PAPER_SOURCE_FIELDS = (
    "paper_id",
    "title",
    "title_zh",
    "abstract",
    "summary_text",
    "summary_zh",
    "doi",
    "arxiv_id",
    "openalex_id",
    "year",
    "publication_date",
    "venue",
    "authors",
    "citation_count",
    "reference_count",
    "fields_of_study",
    "source_url",
    "enrichment_sources",
    "license",
    "oa_status",
    "pdf_path",
)

DB_OVERRIDES = ("summary_zh", "abstract", "venue", "year", "citation_count")


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    text = str(value).strip()
    return text or None


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def load_pack(pack: Path) -> dict[str, dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')='paper'"
        )
        result: dict[str, dict] = {}
        for (raw,) in rows:
            content = json.loads(raw) if isinstance(raw, str) else raw
            identifier = str(content.get("canonical_identity_id") or "")
            if identifier:
                result[identifier] = content
        return result
    finally:
        connection.close()


def load_database(dsn: str) -> dict[str, dict]:
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT paper_id, title_clean, abstract_clean, summary_zh, doi,"
                " arxiv_id, venue, year, citation_count, authors_display"
                " FROM paper"
            )
            result: dict[str, dict] = {}
            for row in cursor.fetchall():
                result[str(row[0])] = {
                    "title": row[1],
                    "abstract_clean": row[2],
                    "summary_zh": row[3],
                    "doi": row[4],
                    "arxiv_id": row[5],
                    "venue": row[6],
                    "year": row[7],
                    "citation_count": row[8],
                    "authors_display": row[9],
                }
            return result
    finally:
        connection.close()


def load_source(source_paths: list[Path]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in source_paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                identifier = str(row.get("paper_id") or "")
                if not identifier:
                    continue
                rows[identifier] = row
                doi = _norm(row.get("doi"))
                if doi:
                    rows.setdefault(f"doi:{doi}", row)
                title = _norm(row.get("title"))
                if title:
                    rows.setdefault(f"title:{title}", row)
    return rows


def to_source_row(pack_doc: dict, db_row: dict, source_row: dict | None) -> dict:
    row = {field: None for field in PAPER_SOURCE_FIELDS}
    row.update(
        {
            "paper_id": pack_doc.get("canonical_identity_id"),
            "title": _text(pack_doc.get("title")) or _text(pack_doc.get("title_zh")),
            "title_zh": _text(pack_doc.get("title_zh")),
            "abstract": _text(pack_doc.get("abstract")),
            "summary_text": _text(pack_doc.get("summary_text")),
            "summary_zh": _text(pack_doc.get("summary_zh")),
            "doi": _text(pack_doc.get("doi")),
            "arxiv_id": _text(pack_doc.get("arxiv_id")),
            "openalex_id": _text(pack_doc.get("openalex_id")),
            "year": pack_doc.get("year"),
            "publication_date": _text(pack_doc.get("publication_date")),
            "venue": _text(pack_doc.get("venue")),
            "authors": pack_doc.get("authors") or [],
            "citation_count": pack_doc.get("citation_count"),
            "reference_count": pack_doc.get("reference_count"),
            "fields_of_study": pack_doc.get("fields_of_study") or [],
            "source_url": None,
            "enrichment_sources": pack_doc.get("enrichment_sources") or [],
            "license": pack_doc.get("license"),
            "oa_status": pack_doc.get("oa_status"),
            "pdf_path": pack_doc.get("pdf_path"),
        }
    )
    if source_row:
        for key in PAPER_SOURCE_FIELDS:
            value = source_row.get(key)
            if row[key] in (None, "", [], {}) and value not in (None, "", [], {}):
                row[key] = value
    for field in DB_OVERRIDES:
        candidate = db_row.get(field) or db_row.get(f"{field}_clean")
        if candidate not in (None, "", [], {}):
            row[field] = candidate
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pack = load_pack(Path(args.pack))
    database = load_database(args.dsn)
    source = load_source([Path(path) for path in args.source])

    rows: list[dict] = []
    used_source: set[str] = set()
    dropped = 0
    db_only = 0
    for identifier, pack_doc in pack.items():
        doi = _norm(pack_doc.get("doi"))
        title = _norm(pack_doc.get("title") or pack_doc.get("title_zh"))
        source_row = source.get(f"doi:{doi}") if doi else None
        if source_row is None and title:
            source_row = source.get(f"title:{title}")
        if source_row is not None:
            used_source.add(str(source_row.get("paper_id")))
        db_row = database.get(identifier) or {}
        row = to_source_row(pack_doc, db_row, source_row)
        if not row.get("title"):
            dropped += 1
            continue
        rows.append(row)

    # Database-only papers (in the collection, never in the pack) are real data.
    pack_keys = set(pack)
    for identifier, db_row in database.items():
        if identifier in pack_keys:
            continue
        title = _text(db_row.get("title"))
        if not title:
            dropped += 1
            continue
        db_only += 1
        rows.append(
            {
                **{field: None for field in PAPER_SOURCE_FIELDS},
                "paper_id": identifier,
                "title": title,
                "abstract": _text(db_row.get("abstract_clean")),
                "summary_zh": _text(db_row.get("summary_zh")),
                "doi": _text(db_row.get("doi")),
                "arxiv_id": _text(db_row.get("arxiv_id")),
                "year": db_row.get("year"),
                "venue": _text(db_row.get("venue")),
                "citation_count": db_row.get("citation_count"),
                "authors": [],
                "enrichment_sources": ["collection-db-export"],
            }
        )

    rows.sort(key=lambda row: str(row.get("paper_id")))
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    summary = {
        "domain": "paper",
        "rows": len(rows),
        "pack": len(pack),
        "database": len(database),
        "source_rows": len([key for key in source if not key.startswith(("doi:", "title:"))]),
        "database_only_added": db_only,
        "dropped_without_title": dropped,
        "sha256": digest,
        "bytes": len(payload.encode("utf-8")),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if args.dry_run:
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{digest}.source").write_text(payload + "\n", encoding="utf-8")
    (out / "export-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
