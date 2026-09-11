#!/usr/bin/env python3
"""G1 derived-metric probe (read-only, stdlib only).

Companion to g1_probe_fields.py: computes union coverage and worst-case combos
that calibrate the gate-at-import draft.

  - placeholder pollution: share of docs whose content_terms contain >=1
    placeholder string (lexical lane haystack pollution)
  - union coverage of retrieval-critical field groups
  - worst-case combos (no usable anchor at all)

Usage:
  python3 g1_probe_derived.py [DB_PATH]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys

DB = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
)
DOMAINS = ("company", "paper", "patent", "professor")

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

FIELDS = {
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

GROUPS = {
    "company": {
        "category_anchor": ("industry", "industry_tags", "tech_tags"),
        "description": (
            "profile_summary", "technology_route_summary",
            "product_description", "team_description",
        ),
        "identity": ("credit_code",),
    },
    "paper": {
        "semantic_text": ("abstract", "summary_text", "summary_zh"),
        "identifier": ("doi", "arxiv_id", "identifiers"),
        "people": ("authors", "professor_ids"),
    },
    "patent": {
        "abstract_or_effect": ("abstract", "technology_effect"),
        "ipc_inventors": ("ipc_codes", "inventors"),
        "dates": ("filing_date", "grant_date"),
    },
    "professor": {
        "direction_signal": ("research_directions", "profile_summary"),
        "contact": ("email", "homepage"),
        "title_or_dept": ("title", "department"),
    },
}


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


def is_placeholder_text(value: str) -> bool:
    text = value.strip()
    if not text or len(text) > PH_MAX_LEN:
        return False
    return any(pattern.match(text) for pattern in PH_PATTERNS)


def classify(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "filled"
    if isinstance(value, (int, float)):
        return "filled"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "empty"
        return "placeholder" if is_placeholder_text(text) else "filled"
    if isinstance(value, dict):
        if "amount" in value:
            return "null" if value.get("amount") is None else "filled"
        if not value:
            return "null"
        sample = first_text(value)
        if sample is None:
            return "empty"
        return "placeholder" if is_placeholder_text(sample) else "filled"
    if isinstance(value, list):
        if not value:
            return "empty"
        samples = [s for item in value if (s := first_text(item)) is not None]
        if not samples:
            return "placeholder"
        return "placeholder" if all(is_placeholder_text(s) for s in samples) else "filled"
    return "filled"


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()

    for domain in DOMAINS:
        total = 0
        polluted = 0
        group_both = {name: 0 for name in GROUPS[domain]}
        for (document_json,) in cur.execute(
            "SELECT document_json FROM lookup_document WHERE projection_id = ?",
            (f"lookup:exact-lookup:{domain}",),
        ):
            doc_json = json.loads(document_json)
            content = doc_json.get("lookup_content")
            if isinstance(content, str):
                content = json.loads(content)
            if not isinstance(content, dict):
                continue
            total += 1

            states = {field: classify(content.get(field)) for field in FIELDS[domain]}
            if any(state == "placeholder" for state in states.values()):
                polluted += 1
            for group, fields in GROUPS[domain].items():
                if all(states[field] != "filled" for field in fields):
                    group_both[group] += 1

        print(f"== [{domain}] N={total} ==")
        print(
            f"placeholder_pollution: {polluted}/{total} "
            f"({100.0 * polluted / total:.1f}%) docs carry >=1 placeholder string"
        )
        for group, fields in GROUPS[domain].items():
            none_count = group_both[group]
            print(
                f"group '{group}' {'+'.join(fields)}: "
                f"all-unusable={none_count}/{total} "
                f"({100.0 * none_count / total:.1f}%)"
            )
        print()

    con.close()


if __name__ == "__main__":
    main()
