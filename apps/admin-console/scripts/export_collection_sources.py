"""P4 S0: export collection data as a build source bundle (released-object JSONL).

Design note (measured 2026-10-28): the collection database does NOT hold every
field the original build sources carried — the professor source had
`research_directions` (37%), `education_structured` (19%), `work_experience`
(20%), `awards` (13%), `academic_positions` (17%), `top_papers` (17%) and more,
none of which the database stores. Exporting database rows alone would make the
rebuild thinner than the current pack.

So the export merges two authorities:

* the current pack (full field coverage, it is the last build's output), and
* the collection database (authoritative for fields the database now owns:
  enriched summaries, corrections, counts).

Output is deterministic: rows sorted by id, canonical JSON, content-addressed
file names. ``--dry-run`` prints the plan without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import psycopg

# Fields the build's professor source rows carried (measured from staging-v4).
PROFESSOR_SOURCE_FIELDS = (
    "professor_id",
    "name",
    "name_en",
    "institution",
    "department",
    "title",
    "email",
    "homepage",
    "profile_url",
    "profile_summary",
    "research_directions",
    "education_structured",
    "work_experience",
    "academic_positions",
    "awards",
    "projects",
    "paper_count",
    "citation_count",
    "h_index",
    "top_papers",
    "official_top_papers",
    "company_roles",
    "patent_ids",
    "office",
    "cv_urls",
    "roster_source",
    "enrichment_source",
    "evaluation_summary",
    "evidence_urls",
    "extraction_status",
)

# Fields the collection database owns once it has been written to.
DB_OVERRIDES = (
    "profile_summary",
    "department",
    "title",
    "email",
    "paper_count",
    "citation_count",
    "h_index",
)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    text = str(value).strip()
    return text or None


def load_pack_professors(pack: Path) -> dict[str, dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')='professor'"
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


_PROF_ID = re.compile(r"PROF-[0-9A-F]{12}")


def source_key(pack_doc: dict) -> str | None:
    """The original source id lives in the pack document's evidence assertions."""

    text = json.dumps(pack_doc, ensure_ascii=False)
    match = _PROF_ID.search(text)
    return match.group(0) if match else None


def load_source_rows(source_paths: list[Path]) -> dict[str, dict]:
    """Original build source rows (full field coverage) keyed by professor id."""

    rows: dict[str, dict] = {}
    for path in source_paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                identifier = str(row.get("professor_id") or "")
                if identifier:
                    rows[identifier] = row
    return rows


def load_db_professors(dsn: str) -> dict[str, dict]:
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.professor_id, p.profile_summary, pa.department, pa.title,"
                " p.paper_count, p.citation_count, p.h_index,"
                " (SELECT f.value_raw FROM professor_fact f WHERE f.professor_id=p.professor_id"
                "   AND f.fact_type='contact' AND f.status='active' LIMIT 1)"
                " FROM professor p"
                " LEFT JOIN professor_affiliation pa ON pa.professor_id=p.professor_id"
                "   AND pa.is_primary"
            )
            result: dict[str, dict] = {}
            for row in cursor.fetchall():
                result[str(row[0])] = {
                    "profile_summary": row[1],
                    "department": row[2],
                    "title": row[3],
                    "paper_count": row[4],
                    "citation_count": row[5],
                    "h_index": row[6],
                    "email": row[7],
                }
            return result
    finally:
        connection.close()


def to_source_row(pack_doc: dict, db_row: dict, source_row: dict | None = None) -> dict:
    """Project a pack document into the build's source-row shape.

    Precedence per field: collection database > original source row > pack
    document. The original source row carries fields the pack dropped
    (education, awards, top papers), so it fills what the pack cannot.
    """

    row = {
        "professor_id": pack_doc.get("canonical_identity_id"),
        "name": _text(pack_doc.get("name")) or _text(pack_doc.get("canonical_name_zh")),
        "name_en": _text(pack_doc.get("canonical_name_en")),
        "institution": _text(pack_doc.get("institution")),
        "department": _text(pack_doc.get("department")),
        "title": _text(pack_doc.get("title")),
        "email": _text(pack_doc.get("email")),
        "homepage": _text(pack_doc.get("homepage")),
        "profile_url": _text(pack_doc.get("homepage")),
        "profile_summary": _text(pack_doc.get("profile_summary")),
        "research_directions": pack_doc.get("research_directions") or [],
        "education_structured": pack_doc.get("education_history") or [],
        "work_experience": pack_doc.get("work_history") or [],
        "academic_positions": pack_doc.get("affiliation_history") or [],
        "awards": pack_doc.get("awards") or [],
        "projects": pack_doc.get("projects") or [],
        "paper_count": pack_doc.get("paper_count"),
        "citation_count": pack_doc.get("citation_count"),
        "h_index": pack_doc.get("h_index"),
        "top_papers": [],
        "official_top_papers": [],
        "company_roles": pack_doc.get("company_roles") or [],
        "patent_ids": pack_doc.get("patent_ids") or [],
        "office": _text(pack_doc.get("office")),
        "cv_urls": [],
        "roster_source": None,
        "enrichment_source": "collection-db-export",
        "evaluation_summary": None,
        "evidence_urls": [],
        "extraction_status": "exported",
    }
    if source_row:
        for key, value in source_row.items():
            if key in row and row[key] in (None, "", [], {}) and value not in (None, "", [], {}):
                row[key] = value
    # Database values win where the database has written something.
    for field in DB_OVERRIDES:
        value = db_row.get(field)
        if value not in (None, "", [], {}):
            row[field] = value
    return {key: row[key] for key in PROFESSOR_SOURCE_FIELDS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--domain", default="professor", choices=("professor",))
    parser.add_argument("--source", action="append", default=[], help="original .source file(s) to merge")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pack = load_pack_professors(Path(args.pack))
    database = load_db_professors(args.dsn)
    source_rows = load_source_rows([Path(path) for path in args.source])
    identifiers = sorted(set(pack) | set(database))
    if args.limit:
        identifiers = identifiers[: args.limit]

    rows = []
    missing_in_db = 0
    for identifier in identifiers:
        pack_doc = pack.get(identifier)
        db_row = database.get(identifier) or {}
        if pack_doc is None:
            missing_in_db += 1
            continue
        key = identifier if identifier in source_rows else source_key(pack_doc)
        rows.append(to_source_row(pack_doc, db_row, source_rows.get(key or "")))

    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    summary = {
        "domain": args.domain,
        "rows": len(rows),
        "pack": len(pack),
        "database": len(database),
        "database_only": missing_in_db,
        "source_rows": len(source_rows),
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
