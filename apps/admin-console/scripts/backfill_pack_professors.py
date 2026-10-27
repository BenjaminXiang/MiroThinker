"""P1: backfill serving-pack professors into the collection database.

Why: the pack holds 3,958 professors and the collection database 220 — the pack
is built from external source bundles, so most professors cannot be browsed,
enriched or corrected through the database, and anything written there would be
lost on the next rebuild.

Behaviour (decisions taken 2026-10-28):

- ids are kept from the pack (`professor-c-…`) so the two systems stay traceable;
- a pack professor whose name matches an existing collection professor under a
  different id is **merged**: no new row is created, the mapping is reported, and
  only empty columns of the existing row are filled;
- `research_directions` has no column in the collection schema: it is dropped and
  counted per professor (the count is reported, not silently discarded);
- inserts are idempotent (`ON CONFLICT DO NOTHING`), single transaction, and the
  whole run is dry-runnable.

Usage::

    python scripts/backfill_pack_professors.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        [--dry-run] [--out /tmp/backfill-professors.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import uuid

import psycopg

# run_id is a uuid column: use a deterministic uuid for this backfill so a rerun
# is traceable and idempotent.
RUN_ID_LABEL = "pack-backfill-20261028"
RUN_ID = str(uuid.uuid5(uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff"), RUN_ID_LABEL))
PAGE_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
DISCIPLINE_FAMILY = "other"
IDENTITY_STATUS = "needs_review"
LIFECYCLE_STATE = "active"


def load_pack_professors(pack: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')='professor'"
        )
        documents = []
        for (raw,) in rows:
            content = json.loads(raw) if isinstance(raw, str) else raw
            documents.append(content)
        return documents
    finally:
        connection.close()


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    text = str(value).strip()
    return text or None


def _alias_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    aliases: list[str] = []
    for entry in value:
        text = _text(entry)
        if text:
            aliases.append(text)
    return aliases


MAX_NAME_CHARS = 200


def _safe_name(value: str | None) -> str | None:
    """Two pack records carry a whole paragraph in `name` (3762/5905 bytes) and
    blow the btree index limit; keep a readable prefix and report the truncation.
    """
    if not value:
        return value
    return value if len(value) <= MAX_NAME_CHARS else value[:MAX_NAME_CHARS]


def _normalized_name(value: object) -> str:
    return str(value or "").strip().lower()


def _page_url(record: dict) -> str:
    homepage = _text(record.get("homepage"))
    if homepage:
        return homepage
    return f"pack://{record.get('canonical_identity_id')}"


def plan(records: list[dict], existing: dict[str, str], name_index: dict[str, str]) -> dict:
    """Classify each pack professor: insert / merge / already present."""

    to_insert: list[dict] = []
    merges: list[dict] = []
    present = 0
    dropped_directions = 0
    for record in records:
        pack_id = str(record.get("canonical_identity_id") or "")
        name = _text(record.get("name")) or _text(record.get("canonical_name_zh"))
        if not pack_id or not name:
            continue
        if pack_id in existing:
            present += 1
            continue
        normalized = _normalized_name(name)
        if normalized in name_index:
            merges.append(
                {
                    "pack_id": pack_id,
                    "collection_id": name_index[normalized],
                    "name": name,
                    "record": record,
                }
            )
            continue
        directions = record.get("research_directions") or []
        if directions:
            dropped_directions += len(directions)
        to_insert.append(record)
    return {
        "pack": len(records),
        "already_present": present,
        "to_insert": len(to_insert),
        "to_merge": len(merges),
        "dropped_research_directions": dropped_directions,
        "merges": merges,
        "inserts": to_insert,
    }


def apply(dsn: str, inserts: list[dict], merges: list[dict]) -> dict:
    written = 0
    merged_filled = 0
    truncated = 0
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            # professor.run_id is a FK to pipeline_run: register the backfill run
            # (deterministic id, so reruns reuse it).
            cursor.execute(
                "INSERT INTO pipeline_run (run_id, run_kind, run_scope, started_at,"
                " status, triggered_by, created_at)"
                " VALUES (%s,'backfill_real',%s,now(),'succeeded','backfill',now())"
                " ON CONFLICT (run_id) DO NOTHING",
                (
                    RUN_ID,
                    psycopg.types.json.Jsonb(
                        {
                            "purpose": "pack professor backfill",
                            "source": "serving-pack",
                            "label": RUN_ID_LABEL,
                        }
                    ),
                ),
            )
            for record in inserts:
                pack_id = str(record["canonical_identity_id"])
                name = _safe_name(
                    _text(record.get("name")) or _text(record.get("canonical_name_zh"))
                )
                url = _page_url(record)
                page_id = str(uuid.uuid5(PAGE_NAMESPACE, url))
                cursor.execute(
                    "INSERT INTO source_page (page_id, url, page_role, fetched_at,"
                    " is_official_source) VALUES (%s,%s,'official_profile',now(),true)"
                    " ON CONFLICT (url) DO NOTHING",
                    (page_id, url),
                )
                department = _text(record.get("department"))
                title = _text(record.get("title"))
                cursor.execute(
                    "INSERT INTO professor (professor_id, canonical_name, canonical_name_zh,"
                    " canonical_name_en, aliases, discipline_family, identity_status,"
                    " quality_status, lifecycle_state, profile_summary, paper_count,"
                    " h_index, citation_count, primary_official_profile_page_id, run_id,"
                    " created_at, updated_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    " (SELECT page_id FROM source_page WHERE url=%s),"
                    " %s,now(),now())"
                    " ON CONFLICT (professor_id) DO NOTHING",
                    (
                        pack_id,
                        name,
                        name,
                        _text(record.get("canonical_name_en")),
                        _alias_list(record.get("aliases")),
                        DISCIPLINE_FAMILY,
                        IDENTITY_STATUS,
                        _text(record.get("quality_status")) or "needs_review",
                        LIFECYCLE_STATE,
                        _text(record.get("profile_summary")),
                        record.get("paper_count"),
                        record.get("h_index"),
                        record.get("citation_count"),
                        url,
                        RUN_ID,
                    ),
                )
                cursor.execute(
                    "INSERT INTO professor_affiliation (professor_id, institution, department,"
                    " title, is_primary, is_current, source_page_id)"
                    " SELECT %s,%s,%s,%s,true,true,(SELECT page_id FROM source_page WHERE url=%s)"
                    " WHERE NOT EXISTS (SELECT 1 FROM professor_affiliation"
                    " WHERE professor_id=%s AND is_primary)",
                    (pack_id, _text(record.get("institution")) or "未知", department, title, url, pack_id),
                )
                if name and len(name) >= MAX_NAME_CHARS:
                    truncated += 1
                written += 1

            for merge in merges:
                record = merge.get("record") or {}
                # Same person under two ids: keep the existing row and fill its
                # empty fields from the pack record instead of duplicating them.
                cursor.execute(
                    "UPDATE professor SET profile_summary = COALESCE(profile_summary, %s),"
                    " citation_count = COALESCE(citation_count, %s),"
                    " h_index = COALESCE(h_index, %s), paper_count = COALESCE(paper_count, %s),"
                    " updated_at = now() WHERE professor_id = %s",
                    (
                        _text(record.get("profile_summary")),
                        record.get("citation_count"),
                        record.get("h_index"),
                        record.get("paper_count"),
                        merge["collection_id"],
                    ),
                )
                merged_filled += cursor.rowcount
        connection.commit()
    return {"written": written, "merged_filled": merged_filled, "truncated_names": truncated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    records = load_pack_professors(Path(args.pack))
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT professor_id, canonical_name FROM professor")
            existing = {str(row[0]): str(row[1] or "") for row in cursor.fetchall()}
    name_index = {
        _normalized_name(name): professor_id
        for professor_id, name in existing.items()
        if _normalized_name(name)
    }

    outcome = plan(records, existing, name_index)
    summary = {
        "pack": outcome["pack"],
        "already_present": outcome["already_present"],
        "to_insert": outcome["to_insert"],
        "to_merge": outcome["to_merge"],
        "dropped_research_directions": outcome["dropped_research_directions"],
        "merges": [
            {"pack_id": item["pack_id"], "collection_id": item["collection_id"], "name": item["name"]}
            for item in outcome["merges"]
        ],
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "merges"}, ensure_ascii=False))

    if args.dry_run:
        if args.out:
            Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    applied = apply(args.dsn, outcome["inserts"], outcome["merges"])
    summary["applied"] = applied
    print(json.dumps(applied, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
