"""P3: daily guard — is every serving-pack record present in the collection DB?

Writes a small JSON report (default ``var/pack-collection-gap.json``) with, per
domain, how many pack records have no matching collection row. The admin status
reads that file; the check itself never touches the pack's data.

Usage::

    python scripts/check_pack_collection_gap.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        --out /root/deploy/fullstack-v2/var/pack-collection-gap.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import psycopg

# Id families differ between the pack and the collection database for companies
# and patents (company-c-… vs company-c-…, patent-c-… vs PAT-…), so each domain
# compares on the identifier that both sides actually share.
TABLE_BY_DOMAIN = {
    "company": ("company", "canonical_name", ("name",)),
    "paper": ("paper", "paper_id", ("canonical_identity_id",)),
    "professor": ("professor", "professor_id", ("canonical_identity_id",)),
    "patent": ("patent", "patent_number", ("patent_number",)),
}


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def pack_keys(pack: dict[str, set[str]], field: str) -> set[str]:
    return {_norm(value) for value in pack[field] if _norm(value)}


def pack_keys_by_domain(pack: Path) -> dict[str, set[str]]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        result: dict[str, set[str]] = {}
        for domain, (_table, _column, fields) in TABLE_BY_DOMAIN.items():
            rows = connection.execute(
                "select json_extract(document_json,'$.lookup_content') from lookup_document"
                " where json_extract(document_json,'$.domain')=?",
                (domain,),
            )
            values: set[str] = set()
            for (raw,) in rows:
                content = json.loads(raw) if isinstance(raw, str) else raw
                for field in fields:
                    key = _norm(content.get(field))
                    if key:
                        values.add(key)
            result[domain] = values
        return result
    finally:
        connection.close()


def database_keys(dsn: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            for domain, (table, column, _fields) in TABLE_BY_DOMAIN.items():
                cursor.execute(f"SELECT {column} FROM {table}")
                result[domain] = {_norm(value) for (value,) in cursor.fetchall() if _norm(value)}
    return result


def build_report(
    pack: dict[str, set[str]],
    database: dict[str, set[str]],
    baseline: dict[str, int] | None = None,
) -> dict:
    domains: dict[str, dict] = {}
    for domain in TABLE_BY_DOMAIN:
        pack_set = pack.get(domain, set())
        db_set = database.get(domain, set())
        missing = sorted(pack_set - db_set)
        expected = (baseline or {}).get(domain, 0)
        domains[domain] = {
            "pack_documents": len(pack_set),
            "collection_rows": len(db_set),
            "pack_missing_from_collection": len(missing),
            "expected_missing": expected,
            "regressed": len(missing) > expected,
            "collection_only": len(db_set - pack_set),
            "missing_samples": missing[:5],
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domains": domains,
        "ok": not any(entry["regressed"] for entry in domains.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--baseline",
        default=None,
        help="JSON file with the accepted per-domain gap, e.g. {\"professor\": 2}",
    )
    args = parser.parse_args(argv)

    baseline: dict[str, int] | None = None
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except (OSError, ValueError):
            baseline = None
    report = build_report(
        pack_keys_by_domain(Path(args.pack)), database_keys(args.dsn), baseline
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "missing_samples"} for k, v in report["domains"].items()}, ensure_ascii=False))
    print(f"ok={report['ok']} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
