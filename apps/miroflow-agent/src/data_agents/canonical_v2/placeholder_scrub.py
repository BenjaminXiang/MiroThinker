"""Placeholder value scrub for the Canonical V2 read path (C1 batch 0).

The lookup corpus carries placeholder strings ("未找到…", "not supplied…")
that today flow into the derived term sets (`content_terms` and the F1
category field-tier buckets) and pollute category recall with cross-entity
fake vocabulary. This module owns the single matcher shared by the read-side
scrub (`knowledge_read_isolated._projection_terms` /
`_projection_category_term_buckets`, applied AFTER
`_validated_public_projection` so the lineage assertions keep binding the
stored bytes).

The packaging-side census that used to live here (`scan_lookup_index`, the
warn-only `placeholder-scan-report.json` side-car of the serving-pack build)
was deleted in `drop-milvus-from-serving-pack`: nothing consumed the report,
and placeholder density belongs to the data-quality line, not to packaging
(design.md §5). The matcher below is the part with a real reader.

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

import re
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
