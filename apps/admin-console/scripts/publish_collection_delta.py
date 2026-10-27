"""Publish collection-DB records that the serving pack does not contain.

XLSX imports write canonical rows into the collection database, but the serving
line reads a frozen pack: imported companies/papers never become searchable until
a rebuild. This script closes that gap for the small deltas that matter — records
present in the collection database but missing from the pack — by publishing them
into the manual-recall store, which the service does read.

Matching is by display name (company) or title (paper), because the pack and the
collection database use different identifier families.

Safety:
- ``--dry-run`` lists what would be published and writes nothing;
- record ids are deterministic (``delta-<domain>-<pk>``), so re-runs replace;
- back up ``var/manual-recall-v1`` before a real run (the runbook requires it).

Usage::

    python scripts/publish_collection_delta.py \
        --domain company \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --store-dir /root/deploy/fullstack-v2/var/manual-recall-v1 \
        [--dry-run] [--limit 500]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

import psycopg


def pack_names(pack: Path, domain: str) -> set[str]:
    database = pack / "lookup.sqlite3"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        field = {"company": "name", "paper": "title", "patent": "title"}[domain]
        names: set[str] = set()
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')=?",
            (domain,),
        )
        for (raw,) in rows:
            content = json.loads(raw) if isinstance(raw, str) else raw
            value = content.get(field) or content.get("title_zh")
            if value:
                names.add(str(value).strip())
        return names
    finally:
        connection.close()


def collection_rows(dsn: str, domain: str, limit: int) -> list[dict]:
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            if domain == "company":
                cursor.execute(
                    "SELECT company_id, canonical_name, profile_summary,"
                    " technology_route_summary, website, hq_city"
                    " FROM company WHERE canonical_name IS NOT NULL"
                    " ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                return [
                    {
                        "pk": row[0],
                        "name": row[1],
                        "payload": {
                            "name": row[1],
                            "profile_summary": row[2],
                            "technology_route_summary": row[3],
                            "website": row[4],
                            "hq_city": row[5],
                        },
                    }
                    for row in cursor.fetchall()
                ]
            # The collection schema stores title_clean/title_raw + abstract_clean
            # (no `title` column), so read those names.
            if domain == "patent":
                cursor.execute(
                    "SELECT patent_id, title_clean, abstract_clean, technology_effect,"
                    " title_en, ipc_codes, summary_text"
                    " FROM patent WHERE title_clean IS NOT NULL"
                    " ORDER BY updated_at DESC LIMIT %s",
                    (limit,),
                )
                rows = []
                for row in cursor.fetchall():
                    title = (row[1] or "").strip()
                    rows.append(
                        {
                            "pk": row[0],
                            "name": title,
                            "payload": {
                                "title": title,
                                "abstract": row[2],
                                "technology_effect": row[3],
                                "title_en": row[4],
                                "ipc_codes": row[5],
                                "summary_text": row[6],
                            },
                        }
                    )
                return rows
            cursor.execute(
                "SELECT paper_id, title_clean, title_raw, abstract_clean, summary_zh"
                " FROM paper WHERE title_clean IS NOT NULL OR title_raw IS NOT NULL"
                " ORDER BY updated_at DESC LIMIT %s",
                (limit,),
            )
            rows = []
            for row in cursor.fetchall():
                title = (row[1] or row[2] or "").strip()
                rows.append(
                    {
                        "pk": row[0],
                        "name": title,
                        "payload": {
                            "title": title,
                            "abstract": row[3],
                            "summary_zh": row[4],
                        },
                    }
                )
            return rows
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=("company", "paper", "patent"))
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--store-dir", required=True)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    known = pack_names(Path(args.pack), args.domain)
    rows = collection_rows(args.dsn, args.domain, args.limit)
    missing = [row for row in rows if row["name"] not in known]
    print(f"{args.domain}: collection={len(rows)} pack={len(known)} missing={len(missing)}")

    if args.dry_run:
        for row in missing[:20]:
            print(f"  + {row['name']}")
        return 0
    if not missing:
        print("nothing to publish")
        return 0

    from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config

    apply_managed_runtime_config()

    from backend.services.canonical_v2_manual_recall import ManualRecallStore
    from publish_professor_pilot import HttpEmbeddingAdapter, embedding_settings

    adapter = HttpEmbeddingAdapter(**embedding_settings())
    store = ManualRecallStore(Path(args.store_dir), adapter)
    print(f"store points before: {len(store.active_points())}")
    batch: list[dict] = []
    written = 0
    for row in missing:
        batch.append(
            {
                "record_id": f"delta-{args.domain}-{row['pk']}",
                "domain": args.domain,
                "manual_object_id": str(row["pk"]),
                "payload": {key: value for key, value in row["payload"].items() if value},
                "operator": "delta-sync",
                "reason": "collection-db row absent from the serving pack",
            }
        )
        if len(batch) >= 200:
            store.add_manual_records(batch)
            written += len(batch)
            print(f"  published {written}/{len(missing)}")
            batch = []
    if batch:
        store.add_manual_records(batch)
        written += len(batch)
    print(f"written: {written}; store points after: {len(store.active_points())}")
    if written and not sys.stdout.isatty():
        print("restart the service to load the new points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
