"""Placeholder value scrub for the Canonical V2 read path (C1 batch 0).

The lookup corpus carries placeholder strings ("未找到…", "not supplied…")
that today flow into the derived term sets (`content_terms` and the F1
category field-tier buckets) and pollute category recall with cross-entity
fake vocabulary. This module owns the single matcher shared by:

- the read-side scrub (`knowledge_read_isolated._projection_terms` /
  `_projection_category_term_buckets`, applied AFTER
  `_validated_public_projection` so the lineage assertions keep binding the
  stored bytes), and
- the packaging-side scan gate (`s12c/build_serving_pack.py`), whose census
  semantics replicate the read-only probe
  (`.agents/runs/close-workbook-gaps/g-series/g1_probe_fields.py`) so the
  dry-run counts stay comparable to the run14 census (professor 12,872 /
  company 3,099 / glued 189 / whole-value 未找到 1,817).

Matcher (locked in `openspec/changes/close-workbook-gaps/design.md` §C1-3,
seed = g1_probe_fields.py:131-153), four families:
  (a) English sentence prefixes: ^(not supplied|no dedicated summary|no
      data|not available)\\b (case-insensitive);
  (b) Chinese whole-value/prefix {未找到, 暂无, 未知, 待补充} plus single `无`;
  (c) token-level erasure of glued `未找到` runs inside longer values (189
      such values in run14, every one retains real content after erasure, so
      whole-value dropping is forbidden for them);
  (d) structural values `^-+$` / `^(none|n/?a)$`.

The 140-character cap on the whole-value families is load-bearing: the only
`^未知` hit in run14 is legitimate long prose (a paper summary on 未知词识别);
widening to substring or dropping the cap false-kills it. Value-level hits
scrub to empty; hits on record-identity fields (`name` / `title` /
`patent_number`) are NOT value-scrubbed — record-level rejection is the
build side's R1/R2 concern, not the read-side scrubber's.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

PLACEHOLDER_MAX_LEN = 140

# Family (a): English sentence prefixes.
_ENGLISH_PREFIX_PATTERNS = (
    re.compile(r"^not supplied\b.*$", re.IGNORECASE),
    re.compile(r"^no dedicated summary\b.*$", re.IGNORECASE),
    re.compile(r"^no data\b.*$", re.IGNORECASE),
    re.compile(r"^not available\b.*$", re.IGNORECASE),
)
# Family (d): structural values.
_STRUCTURAL_PATTERNS = (
    re.compile(r"^none$", re.IGNORECASE),
    re.compile(r"^n/?a$", re.IGNORECASE),
    re.compile(r"^-+$"),
)
# Family (b): Chinese whole-value/prefix patterns plus single 无.
_CHINESE_PATTERNS = (
    re.compile(r"^未找到.*$"),
    re.compile(r"^暂无.*$"),
    re.compile(r"^未知.*$"),
    re.compile(r"^无$"),
    re.compile(r"^待补充.*$"),
)
_WHOLE_VALUE_PATTERNS = (
    *_ENGLISH_PREFIX_PATTERNS,
    *_STRUCTURAL_PATTERNS,
    *_CHINESE_PATTERNS,
)

# Family (c): glued 未找到 runs inside a longer value.
_GLUED_RUN = re.compile(r"(?:未找到)+")

# Record-identity fields route placeholder hits to build-side record-level
# rejection (R1/R2); the read-side scrubber never value-cleans them.
PLACEHOLDER_IDENTITY_FIELDS = frozenset({"name", "title", "patent_number"})


def is_placeholder_value(value: str) -> bool:
    """Whole-value placeholder check (families a/b/d, 140-char cap)."""
    text = value.strip()
    if not text or len(text) > PLACEHOLDER_MAX_LEN:
        return False
    return any(pattern.match(text) for pattern in _WHOLE_VALUE_PATTERNS)


def scrub_placeholder_value(value: str) -> str:
    """Scrub one string: whole-value hit -> "", else erase glued runs."""
    if is_placeholder_value(value):
        return ""
    return _GLUED_RUN.sub("", value)


def scrub_projection_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Scrub every string in a validated projection dump (post-validation).

    Record-identity top-level fields (`name` / `title` / `patent_number`)
    pass through untouched; every other string (including nested tag/industry
    ``name`` members, which are F1's top weight bucket) is value-scrubbed.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return scrub_placeholder_value(node)
        if isinstance(node, dict):
            return {key: walk(nested) for key, nested in node.items()}
        if isinstance(node, list):
            return [walk(nested) for nested in node]
        return node

    return {
        key: (value if key in PLACEHOLDER_IDENTITY_FIELDS else walk(value))
        for key, value in payload.items()
    }


# --- Packaging-side census gate (warn-only in batch 0) ---------------------
#
# The field lists and classify() semantics replicate the read-only census
# probe (g1_probe_fields.py) so the gate's counts stay comparable to the
# run14 baseline; the matcher families above stay the single source for what
# counts as a placeholder.

SCAN_FIELD_LISTS: dict[str, tuple[str, ...]] = {
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

_SCAN_DOMAINS = ("company", "paper", "patent", "professor")
_SCAN_SAMPLE_LIMIT = 3
_WHOLE_VALUE_WEIZHAODAO_EXACT = re.compile(r"^未找到$")


def _first_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in (
            "name", "title", "headline", "canonical_name_zh", "summary_text",
            "content", "description", "role", "code", "label", "value", "provider",
        ):
            if key in value:
                found = _first_text(value[key])
                if found:
                    return found
        for nested in value.values():
            found = _first_text(nested)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _first_text(nested)
            if found:
                return found
    return None


def classify_field_value(value: Any) -> tuple[str, str | None]:
    """(class, sample) with class in null/empty/placeholder/filled (g1 semantics)."""
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
        if is_placeholder_value(text):
            return "placeholder", text[:80]
        return "filled", text[:80]
    if isinstance(value, dict):
        if "amount" in value:
            if value.get("amount") is None:
                return "null", None
            return "filled", f"amount={value.get('amount')}"
        if not value:
            return "null", None
        sample = _first_text(value)
        if sample is None:
            return "empty", None
        if is_placeholder_value(sample):
            return "placeholder", sample[:80]
        return "filled", sample[:80]
    if isinstance(value, list):
        if not value:
            return "empty", None
        samples = [s for item in value if (s := _first_text(item)) is not None]
        if not samples:
            return "placeholder", None
        if all(is_placeholder_value(s) for s in samples):
            return "placeholder", samples[0][:80]
        return "filled", samples[0][:80]
    return "filled", repr(value)[:80]


def _flatten_texts(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for nested in value.values():
            _flatten_texts(nested, out)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _flatten_texts(nested, out)


def scan_lookup_index(db_path: Path | str) -> dict[str, Any]:
    """Read-only placeholder census of one lookup index.

    Opens ``db_path`` with ``mode=ro&immutable=1`` and never writes. The
    report carries per-domain field-hit totals (g1 classify semantics),
    value-level whole-value / glued-run breakdowns, and bounded samples.
    """
    path = Path(db_path)
    report: dict[str, Any] = {
        "schema_version": "canonical-v2-placeholder-scan-report-v1",
        "source_index": str(path),
        "matcher": {
            "families": [
                "english-sentence-prefix",
                "chinese-whole-value-prefix",
                "glued-weizhaodao-run-erasure",
                "structural-dash-none-na",
            ],
            "max_value_length": PLACEHOLDER_MAX_LEN,
            "seed": "g-series/g1_probe_fields.py:131-153",
        },
        "documents": {},
        "field_placeholder_hits": {},
        "whole_value_weizhaodao_exact": 0,
        "whole_value_weizhaodao_prefix": 0,
        "glued_runs": 0,
        "by_field": {},
        "samples": {},
        "previous_pack_report": None,
    }
    connection = sqlite3.connect(
        f"file:{path}?mode=ro&immutable=1", uri=True
    )
    try:
        for domain in _SCAN_DOMAINS:
            rows = connection.execute(
                "SELECT document_json FROM lookup_document "
                "WHERE projection_id = ? ORDER BY canonical_object_id",
                (f"lookup:exact-lookup:{domain}",),
            )
            field_hits: dict[str, int] = {}
            documents = 0
            for (document_json,) in rows:
                document = json.loads(document_json)
                content = document.get("lookup_content")
                if isinstance(content, str):
                    content = json.loads(content)
                if not isinstance(content, dict):
                    continue
                documents += 1
                for field_name in SCAN_FIELD_LISTS[domain]:
                    state, sample = classify_field_value(content.get(field_name))
                    if state == "placeholder":
                        key = f"{domain}.{field_name}"
                        field_hits[key] = field_hits.get(key, 0) + 1
                        if sample:
                            samples = report["samples"].setdefault(key, [])
                            if len(samples) < _SCAN_SAMPLE_LIMIT and sample not in samples:
                                samples.append(sample)
                    texts: list[str] = []
                    _flatten_texts(content.get(field_name), texts)
                    for text in texts:
                        stripped = text.strip()
                        if not stripped:
                            continue
                        if _WHOLE_VALUE_WEIZHAODAO_EXACT.match(stripped):
                            report["whole_value_weizhaodao_exact"] += 1
                        elif (
                            len(stripped) <= PLACEHOLDER_MAX_LEN
                            and stripped.startswith("未找到")
                        ):
                            report["whole_value_weizhaodao_prefix"] += 1
                        elif "未找到" in stripped:
                            report["glued_runs"] += 1
                            glued_key = f"{domain}.{field_name}"
                            glued_samples = report["samples"].setdefault(
                                f"{glued_key}#glued", []
                            )
                            snippet = stripped[:80]
                            if (
                                len(glued_samples) < _SCAN_SAMPLE_LIMIT
                                and snippet not in glued_samples
                            ):
                                glued_samples.append(snippet)
            report["documents"][domain] = documents
            report["field_placeholder_hits"][domain] = sum(field_hits.values())
            report["by_field"].update(
                {key: count for key, count in sorted(field_hits.items())}
            )
    finally:
        connection.close()
    return report
