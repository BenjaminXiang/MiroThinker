"""P0 reconciliation: how would the pack backfill into the collection database?

Read-only. For professors and papers it reports, per domain:

- pack documents vs collection rows;
- matches by id, then by natural key (professor name; paper DOI, else title);
- what would be inserted, what would collide, and what is missing a required
  field;
- rows that exist in the collection database but not in the pack.

Nothing is written to the database; the only output is a JSON report.

Usage::

    python scripts/reconcile_pack_to_collection.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        --domain professor --out /tmp/reconcile-professor.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

import psycopg

REQUIRED = {
    "professor": ("name",),
    "paper": ("title",),
}


def load_pack(pack: Path, domain: str) -> list[dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select json_extract(document_json,'$.lookup_content') from lookup_document"
            " where json_extract(document_json,'$.domain')=?",
            (domain,),
        )
        documents = []
        for (raw,) in rows:
            content = json.loads(raw) if isinstance(raw, str) else raw
            documents.append(content)
        return documents
    finally:
        connection.close()


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def professor_indexes(dsn: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (id -> name, name -> id) from the collection database."""

    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT professor_id, canonical_name FROM professor")
            by_id: dict[str, str] = {}
            by_name: dict[str, str] = {}
            for professor_id, name in cursor.fetchall():
                by_id[str(professor_id)] = str(name or "")
                key = _norm(name)
                if key:
                    by_name.setdefault(key, str(professor_id))
            return by_id, by_name
    finally:
        connection.close()


def paper_indexes(dsn: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT paper_id, doi, title_clean FROM paper")
            by_id: dict[str, str] = {}
            by_doi: dict[str, str] = {}
            by_title: dict[str, str] = {}
            for paper_id, doi, title in cursor.fetchall():
                by_id[str(paper_id)] = str(title or "")
                if doi:
                    by_doi.setdefault(_norm(doi), str(paper_id))
                if title:
                    by_title.setdefault(_norm(title), str(paper_id))
            return by_id, by_doi, by_title
    finally:
        connection.close()


def reconcile_professor(pack: Path, dsn: str) -> dict:
    docs = load_pack(pack, "professor")
    by_id, by_name = professor_indexes(dsn)
    report = {
        "domain": "professor",
        "pack": len(docs),
        "collection": len(by_id),
        "matched_by_id": 0,
        "matched_by_name": 0,
        "new_rows": 0,
        "missing_required": 0,
        "name_collisions": 0,
        "collection_only": len(set(by_id) - {str(d.get("canonical_identity_id")) for d in docs}),
        "samples": {"new": [], "collision": []},
    }
    for document in docs:
        pack_id = str(document.get("canonical_identity_id") or "")
        name = _norm(document.get("name") or document.get("canonical_name_zh"))
        if pack_id in by_id:
            report["matched_by_id"] += 1
            continue
        if name and name in by_name:
            # Same person, different id: inserting naively would duplicate them.
            report["matched_by_name"] += 1
            report["name_collisions"] += 1
            if len(report["samples"]["collision"]) < 5:
                report["samples"]["collision"].append(
                    {"pack_id": pack_id, "name": document.get("name"), "collection_id": by_name[name]}
                )
            continue
        missing = [field for field in REQUIRED["professor"] if not document.get(field)]
        if missing:
            report["missing_required"] += 1
            continue
        report["new_rows"] += 1
        if len(report["samples"]["new"]) < 5:
            report["samples"]["new"].append(
                {"pack_id": pack_id, "name": document.get("name"), "institution": document.get("institution")}
            )
    return report


def reconcile_paper(pack: Path, dsn: str) -> dict:
    docs = load_pack(pack, "paper")
    by_id, by_doi, by_title = paper_indexes(dsn)
    report = {
        "domain": "paper",
        "pack": len(docs),
        "collection": len(by_id),
        "matched_by_id": 0,
        "matched_by_doi": 0,
        "matched_by_title": 0,
        "new_rows": 0,
        "missing_required": 0,
        "collection_only": len(set(by_id) - {str(d.get("canonical_identity_id")) for d in docs}),
        "samples": {"new": []},
    }
    for document in docs:
        pack_id = str(document.get("canonical_identity_id") or "")
        if pack_id in by_id:
            report["matched_by_id"] += 1
            continue
        doi = _norm(document.get("doi"))
        if doi and doi in by_doi:
            report["matched_by_doi"] += 1
            continue
        title = _norm(document.get("title") or document.get("title_zh"))
        if title and title in by_title:
            report["matched_by_title"] += 1
            continue
        if not title:
            report["missing_required"] += 1
            continue
        report["new_rows"] += 1
        if len(report["samples"]["new"]) < 5:
            report["samples"]["new"].append(
                {"pack_id": pack_id, "title": (document.get("title") or "")[:60], "year": document.get("year")}
            )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--domain", required=True, choices=("professor", "paper"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    if not (pack / "lookup.sqlite3").is_file():
        raise SystemExit(f"not a serving pack: {pack}")

    if args.domain == "professor":
        report = reconcile_professor(pack, args.dsn)
    else:
        report = reconcile_paper(pack, args.dsn)

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
