"""Fill missing primary affiliations for professors already in the database.

The original 220 professors were imported before the pack backfill and 199 of
them have no ``professor_affiliation`` row. Without an affiliation the
enrichment pipeline's join skips them, so they cannot be enriched.

This script reads the serving pack, finds database professors whose id exists in
the pack but has no primary affiliation, and inserts one (institution +
department + title) with an official-profile source page. Idempotent.

Usage::

    python scripts/backfill_missing_affiliations.py --pack <dir> --dsn <url> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import uuid

import psycopg

PAGE_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
RUN_ID_LABEL = "pack-affiliation-backfill-20261028"
RUN_ID = str(uuid.uuid5(PAGE_NAMESPACE, RUN_ID_LABEL))


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pack = load_pack_professors(Path(args.pack))
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.professor_id FROM professor p"
                " WHERE NOT EXISTS (SELECT 1 FROM professor_affiliation pa"
                "   WHERE pa.professor_id = p.professor_id AND pa.is_primary)"
            )
            missing = [str(row[0]) for row in cursor.fetchall()]

        candidates = [identifier for identifier in missing if identifier in pack]
        print(f"missing affiliations: {len(missing)}; resolvable from pack: {len(candidates)}")
        if args.dry_run or not candidates:
            return 0

        written = 0
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO pipeline_run (run_id, run_kind, run_scope, started_at,"
                " status, triggered_by, created_at)"
                " VALUES (%s,'backfill_real',%s,now(),'succeeded','backfill',now())"
                " ON CONFLICT (run_id) DO NOTHING",
                (RUN_ID, json.dumps({"purpose": "affiliation backfill", "label": RUN_ID_LABEL})),
            )
            for identifier in candidates:
                record = pack[identifier]
                url = _text(record.get("homepage")) or f"pack://{identifier}"
                cursor.execute(
                    "INSERT INTO source_page (page_id, url, page_role, fetched_at,"
                    " is_official_source) VALUES (%s,%s,'official_profile',now(),true)"
                    " ON CONFLICT (url) DO NOTHING",
                    (str(uuid.uuid5(PAGE_NAMESPACE, url)), url),
                )
                cursor.execute(
                    "INSERT INTO professor_affiliation (professor_id, institution,"
                    " department, title, is_primary, is_current, source_page_id, run_id)"
                    " SELECT %s,%s,%s,%s,true,true,"
                    " (SELECT page_id FROM source_page WHERE url=%s), %s"
                    " WHERE NOT EXISTS (SELECT 1 FROM professor_affiliation"
                    "   WHERE professor_id=%s AND is_primary)",
                    (
                        identifier,
                        _text(record.get("institution")) or "未知",
                        _text(record.get("department")),
                        _text(record.get("title")),
                        url,
                        RUN_ID,
                        identifier,
                    ),
                )
                written += cursor.rowcount
        connection.commit()
        print(f"affiliations written: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
