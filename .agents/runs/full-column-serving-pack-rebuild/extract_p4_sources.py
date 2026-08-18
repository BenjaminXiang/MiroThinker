#!/usr/bin/env python3
"""Extract the six P4 full-column source batches from the surviving sources.

Read-only inputs:
  - restore workspace  /var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z/workspace
  - recovery lab DB    docker container pgtest-recovery-lab-01 (salvage schema)
  - PROF-id -> name map rebuilt from released_objects snapshots + paper_staging

Outputs (append-only new files, s12f admission pattern):
  <restore>/workspace/docs/source_backfills/p4-company-full-v1.jsonl
  .../p4-patent-full-v1.jsonl
  .../p4-paper-salvage-v1.jsonl
  .../p4-professor-full-v1.jsonl
  .../p4-professor-paper-links-v1.jsonl
  .../p4-applicant-binding-full-v1.jsonl
  plus a local batch-inventory.json (byte sizes + sha256) for the manifest.

Deterministic: sorted iteration everywhere; no clock in payloads.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RESTORE = Path(
    "/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z/workspace"
)
OUT_DIR = RESTORE / "docs" / "source_backfills"
INVENTORY_OUT = Path(__file__).resolve().parent / "batch-inventory.json"
SALVAGE_CONTAINER = "pgtest-recovery-lab-01"
SALVAGE_DB = "miroflow_recovery_candidate"

_WS = re.compile(r"\s+")
_COMPANY_SUFFIXES = (
    "公司",
    "集团",
    "企业",
    "厂",
    "有限公司",
    "有限责任公司",
    "股份有限公司",
)
_INSTITUTION_MARKERS = (
    "大学",
    "学院",
    "研究院",
    "研究所",
    "医院",
    "研究中心",
    "实验室",
    "科学院",
    "协会",
    "基金会",
    "中学",
    "学校",
)

# Same conservative extraction-pollution labels the s12e professor audit froze.
_POLLUTION_NAMES = {
    "师资列表",
    "师资介绍",
    "教育经历",
    "相关教师",
    "教师名录",
    "科研成果",
    "研究兴趣",
    "个人简介",
    "Lab Introduction",
    "Highlighted News",
    "Faculty",
    "People",
    "Deep Bit lab",
}


def _norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _WS.sub("", text)
    return text.strip().lower()


def _clean(value) -> str | None:
    if value is None:
        return None
    text = _WS.sub(" ", str(value).replace("\u3000", " ")).strip()
    return text or None


def _psql(query: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            SALVAGE_CONTAINER,
            "psql",
            "-U",
            "miroflow",
            "-d",
            SALVAGE_DB,
            "-AtF",
            "\x1f",
            "-c",
            query,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _psql_csv(query: str) -> list[list[str | None]]:
    """CSV-safe export: values may contain pipes, quotes, and newlines."""
    proc = subprocess.run(
        [
            "docker",
            "exec",
            SALVAGE_CONTAINER,
            "psql",
            "-U",
            "miroflow",
            "-d",
            SALVAGE_DB,
            "-Atc",
            "\\copy (" + query + ") to stdout with (format csv, header false)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import csv
    import io

    return [
        [None if field == "" else field for field in row]
        for row in csv.reader(io.StringIO(proc.stdout))
    ]


def _write_batch(name: str, records: list[dict]) -> dict:
    path = OUT_DIR / name
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing payload {path}")
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8")
    data = path.read_bytes()
    return {
        "filename": name,
        "records": len(records),
        "byte_size": len(data),
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }


def build_prof_map() -> dict[str, str]:
    """Union PROF-id -> display-name over every recovered artifact family."""
    prof: dict[str, str] = {}
    for db_path in sorted(
        glob.glob(
            str(RESTORE / "logs/data_agents/**/released_objects*.db"), recursive=True
        )
    ):
        try:
            import sqlite3

            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            tables = {
                row[0]
                for row in db.execute(
                    "select name from sqlite_master where type='table'"
                )
            }
            if "released_objects" not in tables:
                db.close()
                continue
            try:
                for pid, name in db.execute(
                    "select id, display_name from released_objects "
                    "where object_type='professor'"
                ):
                    prof.setdefault(str(pid), str(name))
            except Exception:
                pass
            db.close()
        except Exception:
            continue
    for staging in sorted(
        glob.glob(
            str(RESTORE / "logs/data_agents/**/paper_staging.jsonl"), recursive=True
        )
    ):
        try:
            with open(staging, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue
                    pid = record.get("anchoring_professor_id")
                    name = record.get("anchoring_professor_name")
                    if isinstance(pid, str) and isinstance(name, str) and pid and name:
                        prof.setdefault(pid, name)
        except Exception:
            continue
    return prof


def extract_company() -> list[dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(RESTORE / "docs/企业总表.xlsx", read_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell).strip() if cell is not None else "" for cell in next(rows)]
    index = {name: position for position, name in enumerate(header)}
    records: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row is None or all(cell is None for cell in row):
            continue
        values = {
            key: _clean(row[index[key]] if index.get(key) is not None else None)
            for key in header
        }
        name = values.get("公司名称")
        if not name:
            continue
        key = _norm_name(name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "company_name": name,
                "project_name": values.get("项目名称"),
                "industry": values.get("行业"),
                "geography": values.get("省份地区"),
                "business": values.get("业务"),
                "founded_date": values.get("成立时间"),
                "legal_representative": values.get("法定代表人"),
                "team": values.get("团队"),
                "company_type": values.get("企业类型"),
                "registered_address": values.get("注册地址"),
                "website": values.get("网址"),
                "email": values.get("邮箱"),
                "phone": values.get("企业联系电话"),
                "product_summary": values.get("产品简介"),
                "product_features": values.get("产品特点"),
                "application_scenarios": values.get("应用场景"),
            }
        )
    records.sort(key=lambda record: _norm_name(record["company_name"]))
    return records


def extract_patent() -> list[dict]:
    release_dir = (
        RESTORE
        / "data/admin_uploads/patent/0dab0a5f9fdff2d7/"
        "63a4dc74-dc2c-43bd-8373-36923bf69e87/11月专利完整版-patent-release"
    )
    type_by_id: dict[str, str] = {}
    type_path = Path(
        "/home/longxiang/MiroThinker/.worktrees/data-rebuild/"
        ".agents/runs/infer-patent-type-from-patent-number/"
        "backfill-apply-2026-06-26.jsonl"
    )
    with open(type_path, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            type_by_id[record["patent_id"]] = record["inferred_type"]
    records: list[dict] = []
    with open(release_dir / "released_objects.jsonl", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            core = row["core_facts"]
            summary = row["summary_fields"]
            patent_id = row["id"]
            applicants_raw = core.get("applicants") or []
            applicants = [
                _clean(applicant)
                for applicant in (
                    applicants_raw
                    if isinstance(applicants_raw, list)
                    else [applicants_raw]
                )
                if _clean(applicant)
            ]
            records.append(
                {
                    "patent_id": patent_id,
                    "title": _clean(core.get("title")),
                    "title_en": _clean(core.get("title_en")),
                    "abstract": _clean(core.get("abstract")),
                    "applicants": applicants,
                    "patent_number": _clean(core.get("patent_number")),
                    "publication_date": _clean(core.get("publication_date")),
                    "filing_date": _clean(core.get("filing_date")),
                    "grant_date": _clean(core.get("grant_date")),
                    "ipc_codes": [
                        _clean(code)
                        for code in (core.get("ipc_codes") or [])
                        if _clean(code)
                    ],
                    "inventors": [
                        _clean(inventor)
                        for inventor in (core.get("inventors") or [])
                        if _clean(inventor)
                    ],
                    "technology_effect": _clean(core.get("technology_effect")),
                    "patent_type": type_by_id.get(patent_id) or "未知类型",
                    "summary_text": _clean(summary.get("summary_text")),
                }
            )
    records.sort(key=lambda record: record["patent_id"])
    return records


def extract_papers() -> list[dict]:
    query = (
        "select paper_id, title_clean, doi, arxiv_id, openalex_id, year, venue, "
        "abstract_clean, authors_display, citation_count, summary_zh "
        "from salvage.paper where quality_status='ready' order by paper_id"
    )
    records: list[dict] = []
    for fields in _psql_csv(query):
        if not fields or not fields[0]:
            continue
        (
            paper_id,
            title,
            doi,
            arxiv_id,
            openalex_id,
            year,
            venue,
            abstract,
            authors_display,
            citation_count,
            summary_zh,
        ) = fields
        authors = []
        for author in re.split(r"[,;，；]", authors_display or ""):
            name = _clean(author)
            if name:
                authors.append({"name": name})
        record = {
            "paper_id": paper_id,
            "title": _clean(title),
            "doi": _clean(doi),
            "arxiv_id": _clean(arxiv_id),
            "openalex_id": _clean(openalex_id),
            "year": int(year) if year and year.isdigit() else None,
            "venue": _clean(venue),
            "abstract": _clean(abstract),
            "authors": authors,
            "citation_count": (
                int(citation_count) if citation_count and citation_count.isdigit() else None
            ),
            "summary_zh": _clean(summary_zh),
        }
        records.append(record)
    return records


def extract_professors(prof_map: dict[str, str]) -> list[dict]:
    sources = [
        RESTORE / "logs/legacy_v2/enriched_v2_2026-04-05.jsonl",
        RESTORE / "logs/data_agents/professor/enriched_v3_merged.jsonl",
    ]
    merged: dict[tuple[str, str], dict] = {}
    name_to_ids: dict[str, list[str]] = {}
    for source in sources:
        with open(source, encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                name = _clean(record.get("name"))
                if not name or name in _POLLUTION_NAMES or name.startswith("("):
                    continue
                institution = _clean(record.get("institution")) or ""
                key = (name, _norm_name(institution))
                merged[key] = record  # v3 (later file) overrides v2
    for (name, _institution), record in sorted(merged.items()):
        institution = _clean(record.get("institution")) or ""
        existing_ids = [
            pid
            for pid, mapped in prof_map.items()
            if _clean(mapped) == name and pid.startswith("PROF-")
        ]
        if existing_ids:
            professor_id = sorted(existing_ids)[0]
        else:
            digest = hashlib.sha256(
                f"{name}|{_norm_name(institution)}".encode("utf-8")
            ).hexdigest()[:12].upper()
            professor_id = f"PROF-{digest}"
        name_to_ids.setdefault(name, []).append(professor_id)
        record["professor_id"] = professor_id
        record["institution"] = institution or None
    return [
        merged[key] for key in sorted(merged.keys(), key=lambda item: item[0])
    ]


def extract_links(prof_map: dict[str, str]) -> list[dict]:
    ids = sorted(prof_map)
    array = "array['" + "','".join(ids) + "']"
    query = (
        "select l.professor_id, l.paper_id, l.evidence_source_type, "
        "coalesce(l.match_reason,'') from salvage.professor_paper_link l "
        f"where l.link_status='verified' and l.professor_id = any({array}) "
        "order by l.professor_id, l.paper_id"
    )
    records: list[dict] = []
    for fields in _psql_csv(query):
        if not fields or not fields[0]:
            continue
        professor_id, paper_id, source_type, match_reason = fields
        records.append(
            {
                "professor_id": professor_id,
                "professor_name": prof_map[professor_id],
                "paper_id": paper_id,
                "link_status": "verified",
                "evidence_source_type": source_type,
                "match_reason": match_reason,
            }
        )
    return records


def extract_applicant_binding(
    patents: list[dict], companies: list[dict]
) -> list[dict]:
    s12f_path = RESTORE / "docs/source_backfills/applicant_name_resolution.jsonl"
    s12f: dict[str, dict] = {}
    with open(s12f_path, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            s12f[record["applicant_name"]] = record

    company_index: dict[str, str] = {}
    alias_index: dict[str, str] = {}
    for record in companies:
        name = record["company_name"]
        key = _norm_name(name)
        company_index.setdefault(key, name)
    # s12f resolved aliases broaden the exact-match index.
    for applicant, record in s12f.items():
        resolved = record.get("resolved_company")
        if record.get("status") == "resolved" and resolved:
            alias_index.setdefault(_norm_name(applicant), resolved)
            for alias in record.get("aliases") or []:
                alias_index.setdefault(_norm_name(alias), resolved)
    # Also index the s12a released company names and s12f backfill companies.
    import sqlite3

    db = sqlite3.connect(
        "file:"
        + str(RESTORE / "logs/data_agents/released_objects.db")
        + "?mode=ro",
        uri=True,
    )
    for (payload,) in db.execute(
        "select payload_json from released_objects where object_type='company'"
    ):
        core = json.loads(payload).get("core_facts", {})
        name = core.get("name")
        if name:
            company_index.setdefault(_norm_name(name), name)
    db.close()
    backfill_path = RESTORE / "docs/source_backfills/company_backfill.jsonl"
    with open(backfill_path, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            name = record.get("company_name")
            if name:
                company_index.setdefault(_norm_name(name), name)
            for alias in record.get("aliases") or []:
                company_index.setdefault(_norm_name(alias), name)

    pool: dict[str, int] = {}
    for patent in patents:
        for applicant in patent["applicants"]:
            pool[applicant] = pool.get(applicant, 0) + 1

    records: list[dict] = []
    for applicant in sorted(pool, key=lambda name: (-pool[name], name)):
        count = pool[applicant]
        prior = s12f.get(applicant)
        key = _norm_name(applicant)
        if prior and prior.get("status") in {"resolved", "already_matched"}:
            resolved = prior.get("resolved_company") or company_index.get(key)
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": "resolved" if resolved else "unresolved",
                    "resolved_company": resolved or "",
                    "aliases": prior.get("aliases") or [],
                    "evidence_urls": prior.get("evidence_urls") or [],
                    "confidence": prior.get("confidence") or "high",
                    "note": "s12f audited resolution reused for the full pool",
                    "search_queries": [],
                }
            )
            continue
        if prior and prior.get("status") in {"institution", "individual"}:
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": prior["status"],
                    "resolved_company": "",
                    "aliases": [],
                    "evidence_urls": [],
                    "confidence": "",
                    "note": prior.get("note") or "",
                    "search_queries": [],
                }
            )
            continue
        if key in company_index:
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": "resolved",
                    "resolved_company": company_index[key],
                    "aliases": [],
                    "evidence_urls": [],
                    "confidence": "high",
                    "note": "full-column name normalization exact match",
                    "search_queries": [],
                }
            )
            continue
        if key in alias_index:
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": "resolved",
                    "resolved_company": alias_index[key],
                    "aliases": [],
                    "evidence_urls": [],
                    "confidence": "high",
                    "note": "s12f audited alias normalization match",
                    "search_queries": [],
                }
            )
            continue
        if any(marker in applicant for marker in _INSTITUTION_MARKERS):
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": "institution",
                    "resolved_company": "",
                    "aliases": [],
                    "evidence_urls": [],
                    "confidence": "",
                    "note": "机构（大学/研究院/医院等，不做公司解析）",
                    "search_queries": [],
                }
            )
            continue
        if not any(suffix in applicant for suffix in _COMPANY_SUFFIXES):
            records.append(
                {
                    "applicant_name": applicant,
                    "patent_count": count,
                    "status": "individual",
                    "resolved_company": "",
                    "aliases": [],
                    "evidence_urls": [],
                    "confidence": "",
                    "note": "自然人申请人（无企业后缀，不做公司解析）",
                    "search_queries": [],
                }
            )
            continue
        records.append(
            {
                "applicant_name": applicant,
                "patent_count": count,
                "status": "unresolved",
                "resolved_company": "",
                "aliases": [],
                "evidence_urls": [],
                "confidence": "",
                "note": "企业申请人未在收录企业名录中（typed gap）",
                "search_queries": [],
            }
        )
    return records


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prof_map = build_prof_map()
    print(f"prof map: {len(prof_map)} ids", flush=True)

    companies = extract_company()
    patents = extract_patent()
    papers = extract_papers()
    professors = extract_professors(prof_map)
    links = extract_links(prof_map)
    applicants = extract_applicant_binding(patents, companies)
    print(
        f"companies={len(companies)} patents={len(patents)} papers={len(papers)} "
        f"professors={len(professors)} links={len(links)} "
        f"applicant_records={len(applicants)}",
        flush=True,
    )

    inventory = {
        "company_full": _write_batch("p4-company-full-v1.jsonl", companies),
        "patent_full": _write_batch("p4-patent-full-v1.jsonl", patents),
        "paper_salvage": _write_batch("p4-paper-salvage-v1.jsonl", papers),
        "professor_full": _write_batch("p4-professor-full-v1.jsonl", professors),
        "professor_paper_links": _write_batch(
            "p4-professor-paper-links-v1.jsonl", links
        ),
        "applicant_binding_full": _write_batch(
            "p4-applicant-binding-full-v1.jsonl", applicants
        ),
    }
    INVENTORY_OUT.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name, meta in inventory.items():
        print(
            f"{name}: records={meta['records']} bytes={meta['byte_size']} "
            f"sha256={meta['content_sha256']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
