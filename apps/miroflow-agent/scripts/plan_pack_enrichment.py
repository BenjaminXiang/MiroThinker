"""Plan a pack→collection enrichment batch and emit the roster import SQL.

The thin professor profiles (2,856 of 3,958) live only in the serving pack; the
collection database does not know them, so the existing enrichment script cannot
reach them. This tool closes that gap:

1. selects thin professors from the pack (short or padded summaries),
2. emits an **idempotent** SQL script that registers them in the collection DB
   (`source_page` → `professor` → `professor_affiliation`), which is what the
   enrichment pipeline reads,
3. writes a human-readable list for review before anything runs.

No database access, no network: it only reads the pack and writes files.

Usage::

    python scripts/plan_pack_enrichment.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --limit 20 --out .agents/runs/professor-paper-slice/pilot
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import uuid

PADDING_MARKERS = (
    "该教授在深圳科创领域有持续贡献",
    "研究成果具有重要学术价值",
)
THIN_CHARS = 120
INSTITUTION_PRIORITY = (
    "深圳大学",
    "南方科技大学",
    "哈尔滨工业大学（深圳）",
    "清华大学深圳国际研究生院",
    "中山大学（深圳）",
    "香港中文大学（深圳）",
)
UUID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def is_thin(summary: str | None) -> bool:
    text = (summary or "").strip()
    if any(marker in text for marker in PADDING_MARKERS):
        return True
    return len(text) < THIN_CHARS


def sql_text(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def page_uuid(url: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, url))


def rank_key(record: dict) -> tuple:
    institution = str(record.get("institution") or "")
    priority = (
        INSTITUTION_PRIORITY.index(institution)
        if institution in INSTITUTION_PRIORITY
        else len(INSTITUTION_PRIORITY)
    )
    return (0 if record.get("homepage") else 1, priority, str(record.get("name") or ""))


def select_thin(records: list[dict], *, limit: int) -> list[dict]:
    candidates = [
        record for record in records if is_thin(record.get("profile_summary"))
    ]
    candidates.sort(key=rank_key)
    return candidates[:limit]


def render_sql(selected: list[dict]) -> str:
    lines = ["BEGIN;", ""]
    for record in selected:
        name = str(record.get("name") or "").strip()
        institution = str(record.get("institution") or "").strip() or "未知"
        professor_id = str(record.get("canonical_identity_id"))
        homepage = str(record.get("homepage") or "").strip()
        # Never import the padded text: the enrichment UPDATE only replaces a
        # SHORTER summary, so a 226-character template would win against a
        # 223-character real biography and the professor would never be upgraded.
        # A short placeholder also satisfies the selection's "summary is not null".
        summary = "待补全。"

        if homepage:
            page_id = page_uuid(homepage)
            lines.append(
                # url_host is a generated column: never insert it.
                "INSERT INTO source_page (page_id, url, page_role, fetched_at,"
                " is_official_source)"
                f" VALUES ('{page_id}', {sql_text(homepage)},"
                " 'official_profile', now(), true)"
                " ON CONFLICT (url) DO NOTHING;"
            )
            page_ref = (
                f"(SELECT page_id FROM source_page WHERE url = {sql_text(homepage)})"
            )
        else:
            page_ref = "NULL"

        lines.append(
            "INSERT INTO professor (professor_id, canonical_name, canonical_name_zh,"
            " aliases, discipline_family, identity_status, quality_status,"
            " lifecycle_state, profile_summary, primary_official_profile_page_id,"
            " created_at, updated_at)"
            f" VALUES ({sql_text(professor_id)}, {sql_text(name)}, {sql_text(name)},"
            " ARRAY[]::text[], 'other', 'needs_review', 'needs_enrichment', 'active',"
            f" {sql_text(summary)}, {page_ref}, now(), now())"
            " ON CONFLICT (professor_id) DO NOTHING;"
        )
        lines.append(
            "INSERT INTO professor_affiliation (professor_id, institution, is_primary,"
            " is_current, source_page_id)"
            f" SELECT {sql_text(professor_id)}, {sql_text(institution)}, true, true,"
            f" {page_ref}"
            " WHERE NOT EXISTS (SELECT 1 FROM professor_affiliation"
            f" WHERE professor_id = {sql_text(professor_id)} AND is_primary);"
        )
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines)


def load_professors(pack: Path) -> list[dict]:
    database = pack / "lookup.sqlite3"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        cursor = connection.execute(
            "select document_json from lookup_document "
            "where json_extract(document_json,'$.domain')='professor'"
        )
        records: list[dict] = []
        for (raw,) in cursor:
            document = json.loads(raw)
            content = document.get("lookup_content")
            if isinstance(content, str):
                content = json.loads(content)
            records.append(content)
        return records
    finally:
        connection.close()


def render_markdown(selected: list[dict], total_thin: int, total: int) -> str:
    lines = [
        "# 补全试点：前 20 位薄画像",
        "",
        f"pack 教授 {total} 位，其中薄画像 **{total_thin}** 位；本清单取前 {len(selected)} 位"
        "（优先有主页、按机构优先级）。",
        "",
        "| # | 姓名 | 机构 | 主页 | 现有摘要字数 |",
        "|---|---|---|---|---|",
    ]
    for index, record in enumerate(selected, start=1):
        lines.append(
            f"| {index} | {record.get('name')} | {record.get('institution')} | "
            f"{(record.get('homepage') or '—')} | "
            f"{len((record.get('profile_summary') or '').strip())} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    if not (pack / "lookup.sqlite3").is_file():
        print(f"not a serving pack: {pack}", file=sys.stderr)
        return 2

    records = load_professors(pack)
    thin = [record for record in records if is_thin(record.get("profile_summary"))]
    selected = select_thin(records, limit=args.limit)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "pilot.json").write_text(
        json.dumps(
            {
                "pack": str(pack),
                "professors": len(records),
                "thin": len(thin),
                "selected": [
                    {
                        "professor_id": record.get("canonical_identity_id"),
                        "name": record.get("name"),
                        "institution": record.get("institution"),
                        "homepage": record.get("homepage"),
                        "summary_chars": len(
                            (record.get("profile_summary") or "").strip()
                        ),
                        "directions": len(record.get("research_directions") or []),
                    }
                    for record in selected
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    (out / "import.sql").write_text(render_sql(selected))
    markdown = render_markdown(selected, len(thin), len(records))
    (out / "pilot.md").write_text(markdown)

    print(f"professors: {len(records)} | thin: {len(thin)} | selected: {len(selected)}")
    print("\n".join(markdown.splitlines()[:10]))
    print(f"\nwritten: {out}/{{pilot.json,pilot.md,import.sql}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
