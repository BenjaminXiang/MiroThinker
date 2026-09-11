#!/usr/bin/env python3
"""G1 field-contract probe (read-only, stdlib only).

Measures, per domain (company/paper/patent/professor) over the sealed lookup pack:
  1. per-field coverage + null/empty/placeholder breakdown + value samples
  2. placeholder census (distinct placeholder strings per field)
  3. distributions (quality_status per domain, company industry)
  4. category-word -> field-bucket hit matrix (incl. summary-only blind spots)

Usage:
  python3 g1_probe_fields.py [DB_PATH] [SECTION] [ROW_LIMIT]
    SECTION in {all, coverage, words}   (default all)
    ROW_LIMIT optional per-domain row cap for smoke runs (default: no limit)

Rerun examples:
  python3 .agents/runs/close-workbook-gaps/g-series/g1_probe_fields.py
  python3 .agents/runs/close-workbook-gaps/g-series/g1_probe_fields.py \
      /var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3 coverage
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict

DB = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
)
SECTION = sys.argv[2] if len(sys.argv) > 2 else "all"
ROW_LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else None

DOMAINS = ("company", "paper", "patent", "professor")

# --- coverage field lists (projection payload fields, envelope/lineage excluded) ---
FIELDS: dict[str, tuple[str, ...]] = {
    "company": (
        "name", "normalized_name", "aliases", "credit_code", "founded_at",
        "geography", "industry", "industry_tags", "key_personnel",
        "latest_public_updates", "legal_representative", "patent_count",
        "product_description", "profile_summary", "registered_address",
        "registered_capital", "team_description", "tech_tags",
        "technology_route_summary", "website", "business_scenarios",
        "capabilities", "financing_events", "personnel_education",
        "personnel_work_experience", "products", "quality_status",
    ),
    "paper": (
        "title", "title_zh", "abstract", "arxiv_id", "authors", "citation_count",
        "doi", "enrichment_sources", "fields_of_study", "funders", "keywords",
        "license", "oa_status", "pdf_path", "professor_ids", "publication_date",
        "reference_count", "summary_text", "summary_zh", "tldr", "venue", "year",
        "full_texts", "identifiers", "publications", "references", "summaries",
        "quality_status",
    ),
    "patent": (
        "title", "title_en", "abstract", "applicants", "company_ids",
        "filing_date", "grant_date", "inventors", "ipc_codes", "patent_number",
        "patent_type", "professor_ids", "publication_date", "summary_text",
        "technology_effect", "milestones", "technical_summaries", "quality_status",
    ),
    "professor": (
        "name", "canonical_name_zh", "canonical_name_en", "aliases", "awards",
        "citation_count", "company_roles", "department", "email", "h_index",
        "homepage", "institution", "lifecycle_state", "manual_override", "office",
        "paper_count", "paper_summary", "patent_ids", "patent_summary", "phone",
        "profile_summary", "projects", "research_directions", "title",
        "affiliation_history", "contacts", "education_history",
        "metric_snapshots", "work_history", "quality_status",
    ),
}

# --- word -> field-bucket accessors for the anchoring matrix ---
BUCKETS: dict[str, dict[str, tuple[str, ...]]] = {
    "company": {
        "name": ("name", "normalized_name", "aliases"),
        "industry": ("industry",),
        "industry_tags": ("industry_tags",),
        "tech_tags": ("tech_tags",),
        "profile_summary": ("profile_summary",),
        "technology_route_summary": ("technology_route_summary",),
        "product_description": ("product_description",),
        "team_description": ("team_description",),
        "business_scenarios": ("business_scenarios",),
        "capabilities": ("capabilities",),
        "products": ("products",),
        "key_personnel": ("key_personnel",),
        "latest_public_updates": ("latest_public_updates",),
    },
    "paper": {
        "title": ("title", "title_zh"),
        "abstract": ("abstract",),
        "summary_text": ("summary_text",),
        "summary_zh": ("summary_zh",),
        "tldr": ("tldr",),
        "keywords": ("keywords",),
        "fields_of_study": ("fields_of_study",),
    },
    "patent": {
        "title": ("title", "title_en"),
        "abstract": ("abstract",),
        "summary_text": ("summary_text",),
        "technology_effect": ("technology_effect",),
        "ipc_codes": ("ipc_codes",),
        "technical_summaries": ("technical_summaries",),
    },
    "professor": {
        "research_directions": ("research_directions",),
        "profile_summary": ("profile_summary",),
        "paper_summary": ("paper_summary",),
        "patent_summary": ("patent_summary",),
    },
}

# buckets that count as "structured/anchored" vs "descriptive/summary" for blind-spot math
STRUCTURED = {
    "company": {"name", "industry", "industry_tags", "tech_tags"},
    "paper": {"title", "keywords", "fields_of_study"},
    "patent": {"title", "ipc_codes"},
    "professor": {"research_directions"},
}

WORDS = (
    "机器人", "具身智能", "PCB", "人工智能", "储能", "半导体", "芯片",
    "新能源", "无人机", "激光雷达", "大模型", "自动驾驶", "生物医药", "低空经济",
)

# --- placeholder detection (full-value, capped length so long generated prose is not misread) ---
PH_PATTERNS = (
    re.compile(r"^not supplied\b.*$", re.IGNORECASE),
    re.compile(r"^no dedicated summary\b.*$", re.IGNORECASE),
    re.compile(r"^no data\b.*$", re.IGNORECASE),
    re.compile(r"^not available\b.*$", re.IGNORECASE),
    re.compile(r"^none$", re.IGNORECASE),
    re.compile(r"^n/?a$", re.IGNORECASE),
    re.compile(r"^-+$"),
    re.compile(r"^未找到.*$"),
    re.compile(r"^暂无.*$"),
    re.compile(r"^未知.*$"),
    re.compile(r"^无$"),
    re.compile(r"^待补充.*$"),
)
PH_MAX_LEN = 140


def is_placeholder_text(value: str) -> bool:
    text = value.strip()
    if not text or len(text) > PH_MAX_LEN:
        return False
    return any(pattern.match(text) for pattern in PH_PATTERNS)


def first_text(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in (
            "name", "title", "headline", "canonical_name_zh", "summary_text",
            "content", "description", "role", "code", "label", "value", "provider",
        ):
            if key in value:
                found = first_text(value[key])
                if found:
                    return found
        for nested in value.values():
            found = first_text(nested)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = first_text(nested)
            if found:
                return found
    return None


def classify(value: object) -> tuple[str, str | None]:
    """Return (class, sample) where class in {null, empty, placeholder, filled}."""
    if value is None:
        return "null", None
    if isinstance(value, bool):
        return "filled", str(value)
    if isinstance(value, (int, float)):
        return "filled", str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "empty", None
        if is_placeholder_text(text):
            return "placeholder", text[:80]
        return "filled", text[:80]
    if isinstance(value, dict):
        if "amount" in value:
            amount = value.get("amount")
            if amount is None:
                return "null", None
            return "filled", f"amount={amount}"
        if not value:
            return "null", None
        sample = first_text(value)
        if sample is None:
            return "empty", None
        if is_placeholder_text(sample):
            return "placeholder", sample[:80]
        return "filled", sample[:80]
    if isinstance(value, list):
        if not value:
            return "empty", None
        samples = [s for item in value if (s := first_text(item)) is not None]
        if not samples:
            return "placeholder", None
        if all(is_placeholder_text(s) for s in samples):
            return "placeholder", samples[0][:80]
        return "filled", samples[0][:80]
    return "filled", repr(value)[:80]


def flatten_texts(value: object) -> list[str]:
    out: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return out


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()

    coverage: dict[str, dict[str, Counter]] = {
        domain: defaultdict(Counter) for domain in DOMAINS
    }
    samples: dict[str, dict[str, list[str]]] = {
        domain: defaultdict(list) for domain in DOMAINS
    }
    placeholder_census: Counter[tuple[str, str, str]] = Counter()
    quality_dist: dict[str, Counter] = {domain: Counter() for domain in DOMAINS}
    industry_dist: Counter[str] = Counter()
    word_counts: dict[str, dict[str, dict[str, int]]] = {
        domain: {word: Counter() for word in WORDS} for domain in DOMAINS
    }
    totals: Counter[str] = Counter()

    for domain in DOMAINS:
        query = (
            "SELECT document_json FROM lookup_document "
            "WHERE projection_id = ? ORDER BY canonical_object_id"
        )
        params: tuple[object, ...] = (f"lookup:exact-lookup:{domain}",)
        if ROW_LIMIT:
            query += " LIMIT ?"
            params = params + (ROW_LIMIT,)
        for (document_json,) in cur.execute(query, params):
            doc_json = json.loads(document_json)
            content = doc_json.get("lookup_content")
            if isinstance(content, str):
                content = json.loads(content)
            if not isinstance(content, dict):
                continue
            totals[domain] += 1

            for field in FIELDS[domain]:
                state, sample = classify(content.get(field))
                coverage[domain][field][state] += 1
                if state == "placeholder" and sample:
                    placeholder_census[(domain, field, sample)] += 1
                if state == "filled" and sample and sample not in samples[domain][field]:
                    if len(samples[domain][field]) < 2:
                        samples[domain][field].append(sample)

            quality_dist[domain][str(content.get("quality_status"))] += 1

            if domain == "company":
                industry = content.get("industry")
                if isinstance(industry, dict) and industry.get("name"):
                    industry_dist[industry["name"]] += 1
                elif industry is None:
                    industry_dist["(null)"] += 1
                else:
                    industry_dist[f"(other:{type(industry).__name__})"] += 1

            for word in WORDS:
                hit_any = False
                hit_structured = False
                for bucket, field_names in BUCKETS[domain].items():
                    texts: list[str] = []
                    for field_name in field_names:
                        texts.extend(flatten_texts(content.get(field_name)))
                    haystack = "\n".join(texts).lower()
                    if word.lower() in haystack:
                        word_counts[domain][word][bucket] += 1
                        hit_any = True
                        if bucket in STRUCTURED[domain]:
                            hit_structured = True
                if hit_any:
                    word_counts[domain][word]["ANY"] += 1
                if hit_structured:
                    word_counts[domain][word]["STRUCTURED"] += 1

    con.close()

    if SECTION in ("all", "coverage"):
        for domain in DOMAINS:
            total = totals[domain]
            print(f"== [{domain}] coverage N={total} ==")
            for field in FIELDS[domain]:
                counts = coverage[domain][field]
                null, empty, placeholder, filled = (
                    counts["null"], counts["empty"], counts["placeholder"], counts["filled"],
                )
                pct = (100.0 * filled / total) if total else 0.0
                ex = " | ".join(samples[domain][field])[:110]
                print(
                    f"{field:28s} filled={filled:6d}/{total} ({pct:5.1f}%) "
                    f"null={null} empty={empty} ph={placeholder}  ex={ex}"
                )
            print()

        print("== placeholder census (domain.field | value | count) ==")
        for (domain, field, value), count in placeholder_census.most_common(60):
            print(f"{domain}.{field} | {value!r} | {count}")
        print()

        print("== quality_status ==")
        for domain in DOMAINS:
            print(f"{domain}: {dict(quality_dist[domain].most_common())}")
        print()

        print("== company industry distribution (top 60 + null) ==")
        for name, count in industry_dist.most_common(60):
            print(f"{name} : {count}")
        for probe in ("机器人", "具身智能", "储能", "医疗器械", "新能源", "PCB"):
            exact = industry_dist.get(probe, 0)
            substring = sum(
                count for name, count in industry_dist.items() if probe in name
            )
            print(f"[probe] {probe} exact={exact} substring={substring}")
        print()

    if SECTION in ("all", "words"):
        for domain in DOMAINS:
            print(f"== [{domain}] word -> bucket hits (N={totals[domain]}) ==")
            for word in WORDS:
                counts = word_counts[domain][word]
                if counts["ANY"] == 0 and counts["STRUCTURED"] == 0:
                    print(f"{word:8s} ANY=0")
                    continue
                detail = " ".join(
                    f"{bucket}={counts[bucket]}"
                    for bucket in BUCKETS[domain]
                    if counts[bucket]
                )
                summary_only = counts["ANY"] - counts["STRUCTURED"]
                print(
                    f"{word:8s} ANY={counts['ANY']} STRUCTURED={counts['STRUCTURED']} "
                    f"summary_only={summary_only} | {detail}"
                )
            print()


if __name__ == "__main__":
    main()
