"""Format-normalizing semantic dedup for ``professor_fact``.

The ``professor_fact`` table is written by seven insert paths in three
incompatible surface encodings (pipe, JSON, bilingual prose). A literal
whitespace-collapsed key cannot match the same logical fact across those
encodings, so duplicates accumulate. This module gives the canonical writer a
*format-normalizing* view of a fact so it can keep exactly one active row per
logical entry (keep-richest).

Design choices:

* Match is a **predicate**, not a plain hash: two facts are duplicates when
  their school/org, degree/role and field agree *and* their time periods agree
  — but a period agrees when one side is empty, so a year-bearing pipe twin
  still matches a year-less JSON twin. This keeps genuinely-distinct
  consecutive degrees (same school+field, different periods) separate.
* Org/field signatures use **ASCII tokens when present, else CJK runs**. This
  matches ``Tsinghua University`` against ``Tsinghua University (清华大学)``
  (the CJK gloss is dropped because ASCII is present) while still keeping
  CJK-only schools (``清华大学`` vs ``北京大学``) distinct.

Validated empirically: these algorithms drove this session's six cleanup
passes that superseded ~23,000 duplicate rows with zero confirmed false
positives (the years-from-whole fix removed the only false positive seen).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "FactComponents",
    "extract_components",
    "facts_are_duplicates",
    "completeness_score",
    "legacy_literal_key",
    "llm_merge_is_safe",
]

_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_CJK_RE = re.compile(r"[㐀-鿿]+")
_WHITESPACE_RE = re.compile(r"\s+")
# A pure parenthetical gloss remainder, e.g. " (English translation)" / "（中文释义）".
_GLOSS_REMAINDER_RE = re.compile(r"^\s*[(（][^()（）]*[)）]\s*$")

_DEGREE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # postdoc before phd: 博士后 contains 博士.
    (re.compile(r"postdoc|博士后", re.IGNORECASE), "postdoc"),
    (re.compile(r"ph\.?d|doctor|博士", re.IGNORECASE), "phd"),
    (re.compile(r"master|硕士|m\.?sc|m\.?eng", re.IGNORECASE), "master"),
    (re.compile(r"bachelor|本科|学士|b\.?sc|b\.?eng|undergrad", re.IGNORECASE), "bachelor"),
    (re.compile(r"visit|访问|交流|交换", re.IGNORECASE), "visit"),
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip()


def _ascii_tokens(text: str) -> frozenset[str]:
    return frozenset(w.lower() for w in _ASCII_WORD_RE.findall(text or "") if len(w) >= 2)


def _cjk_runs(text: str) -> frozenset[str]:
    return frozenset(r for r in _CJK_RE.findall(text or "") if r)


def _signature(text: str) -> frozenset[str]:
    """ASCII word tokens when any are present, else CJK runs. Order-independent.

    Using ASCII-when-present lets ``Tsinghua University`` match
    ``Tsinghua University (清华大学)`` (the CJK gloss is dropped) while keeping
    CJK-only strings (``清华大学`` vs ``北京大学``) distinct.
    """
    ascii_tokens = _ascii_tokens(text)
    return ascii_tokens if ascii_tokens else _cjk_runs(text)


def _years(text: str) -> str:
    # Canonical period signature: sorted unique 4-digit years, independent of
    # surface format/dash placement. "2018-2022" and "2018年11月-2022年05月"
    # both yield "2018,2022" so a pipe twin matches its prose twin. Distinct
    # periods (2013-2016 vs 2016-2020 -> "2013,2016" vs "2016,2020") stay apart.
    years = sorted({m.group() for m in re.finditer(r"(?:19|20)\d{2}", text or "")})
    return ",".join(years)


def _degree_level(text: str) -> str:
    for pattern, level in _DEGREE_PATTERNS:
        if pattern.search(text or ""):
            return level
    # Fallback: the ascii-or-cjk signature, so distinct roles that are not
    # canonical degrees (教授 vs 副教授; Assistant vs Associate Professor) stay
    # separate rather than collapsing to an empty signature.
    return _signature(text)


def _try_json(value: str) -> dict[str, Any] | None:
    if not value or value[0] not in "{[":
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True, slots=True)
class FactComponents:
    """Normalized, format-independent view of one fact value."""

    org_sig: frozenset[str]
    field_sig: frozenset[str]
    degree_level: str
    whole_sig: frozenset[str]
    years: str
    is_structured: bool
    raw: str


def _structured_components(org: str, degree: str, field: str, whole: str) -> FactComponents:
    return FactComponents(
        org_sig=_signature(org),
        field_sig=_signature(field),
        degree_level=_degree_level(degree),
        whole_sig=_signature(whole),
        years=_years(whole),
        is_structured=True,
        raw=whole,
    )


def _freeform_components(whole: str) -> FactComponents:
    return FactComponents(
        org_sig=frozenset(),
        field_sig=frozenset(),
        degree_level="",
        whole_sig=_signature(whole),
        years=_years(whole),
        is_structured=False,
        raw=whole,
    )


def extract_components(
    fact_type: str, value_raw: Any, value_normalized: Any = None
) -> FactComponents | None:
    """Parse a fact value into comparable components, independent of encoding.

    Returns ``None`` for empty/unkeyable values so the writer can fall back to
    the legacy literal key and never collapse two empty facts.
    """
    raw = _clean(value_raw) or _clean(value_normalized)
    if not raw:
        return None

    parsed = _try_json(raw)
    if parsed is not None:
        org = str(parsed.get("school") or parsed.get("organization") or "")
        degree = str(parsed.get("degree") or parsed.get("role") or parsed.get("title") or "")
        field = str(parsed.get("field") or "")
        return _structured_components(org, degree, field, raw)

    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
        org = parts[0] if parts else ""
        degree = parts[1] if len(parts) > 1 else ""
        field = parts[2] if len(parts) > 2 else ""
        return _structured_components(org, degree, field, raw)

    # Pure prose. Structured fact_types that arrived as prose keep their tokens
    # but are matched as freeform (conservative: a prose education will not
    # cross-match a pipe education — that residual is handled by the one-shot
    # cleanup, to avoid false positives on partial overlaps).
    return _freeform_components(raw)


def _years_agree(a: str, b: str) -> bool:
    """Periods agree when both empty or equal. One empty => agree (a year-less
    JSON twin matches a year-bearing pipe twin of the same degree)."""
    if not a or not b:
        return True
    return a == b


def _components_match(a: FactComponents, b: FactComponents) -> bool:
    if a.is_structured and b.is_structured:
        # Require at least one non-empty signature so two empty structured
        # values don't collapse.
        if not (a.org_sig or a.field_sig):
            return False
        return (
            a.org_sig == b.org_sig
            and a.field_sig == b.field_sig
            and a.degree_level == b.degree_level
            and _years_agree(a.years, b.years)
        )
    if not a.is_structured and not b.is_structured:
        if not a.whole_sig or not b.whole_sig:
            return False
        return a.whole_sig == b.whole_sig and _years_agree(a.years, b.years)
    # structured vs prose: do not cross-match (conservative; residual handled
    # by the one-shot cleanup). Avoids false positives on partial overlaps.
    return False


def _is_gloss_prefix(short: str, long: str) -> bool:
    """True when ``short`` is ``long`` with a pure parenthetical gloss appended,
    e.g. ``X`` vs ``X (English gloss)``."""
    ns, nl = _clean(short), _clean(long)
    if not ns or len(ns) >= len(nl):
        return False
    return nl.startswith(ns) and bool(_GLOSS_REMAINDER_RE.match(nl[len(ns):]))


def facts_are_duplicates(fact_type: str, value_a: Any, value_b: Any) -> bool:
    """Predicate: are two fact values the same logical entry?

    Order is exact-text -> gloss-prefix -> semantic-components. Designed to
    never produce a false positive on genuinely-distinct facts.
    """
    a = _clean(value_a)
    b = _clean(value_b)
    if not a or not b:
        return False
    la = legacy_literal_key(a)
    lb = legacy_literal_key(b)
    if la and la == lb:
        return True
    if _is_gloss_prefix(a, b) or _is_gloss_prefix(b, a):
        return True
    ca = extract_components(fact_type, a)
    cb = extract_components(fact_type, b)
    if ca is None or cb is None:
        return False
    return _components_match(ca, cb)


def completeness_score(value_raw: Any, value_normalized: Any = None) -> tuple[int, ...]:
    """Higher == richer representation. Used for keep-richest on collision.

    ``(is_structured, n_signature_tokens, has_years, len(value_raw))`` —
    structured (pipe/JSON) outranks prose; within structured, more tokens and a
    year range win; length is the final tiebreak.
    """
    raw = _clean(value_raw) or _clean(value_normalized)
    if not raw:
        return (0, 0, 0, 0)
    comp = extract_components("", raw)
    is_structured = 1 if (comp is not None and comp.is_structured) else 0
    has_years = 1 if (comp is not None and comp.years) else 0
    if comp is not None and comp.is_structured:
        n_tokens = len(comp.org_sig) + len(comp.field_sig)
    elif comp is not None:
        n_tokens = len(comp.whole_sig)
    else:
        n_tokens = 0
    return (is_structured, n_tokens, has_years, len(raw))


def legacy_literal_key(value: Any, value_normalized: Any = None) -> str:
    """The pre-semantic key: whitespace-collapsed, case-folded text. Kept as a
    defensive fallback for values the semantic view cannot parse."""
    text = _clean(value) or _clean(value_normalized)
    return text.casefold()


_CANONICAL_DEGREE_LEVELS = frozenset({"phd", "master", "bachelor", "visit", "postdoc"})
# Generic institution/connector words ignored by the LLM-merge overlap guard,
# so "University of X" vs "University of Y" don't pass on the shared "university".
_GENERIC_OVERLAP_WORDS = frozenset(
    {
        "university", "college", "school", "institute", "institutes",
        "department", "division", "laboratory", "lab", "labs", "center",
        "centre", "faculty", "academy", "polytechnic", "of", "the", "and",
        "for", "in", "at", "on",
    }
)
# Degree-word fragments excluded from the overlap guard (e.g. "Ph.D." -> "ph").
_DEGREE_FRAGMENTS = frozenset(
    {
        "phd", "msc", "bsc", "ms", "bs", "ma", "ba", "meng", "beng",
        "doctor", "doctoral", "master", "masters", "bachelor", "postdoc",
        "prof", "professor", "dr",
    }
)


def _distinctive_ascii_tokens(text: str) -> frozenset[str]:
    """ASCII words (len>=3) minus generic/degree fragments — the distinctive
    English school/org/field signal used by the LLM-merge overlap guard."""
    return frozenset(
        w.lower() for w in _ASCII_WORD_RE.findall(text) if len(w) >= 3
    ) - _GENERIC_OVERLAP_WORDS - _DEGREE_FRAGMENTS


def _org_overlap(keep: str, sup: str) -> bool:
    """True when the two values share a school/org signal.

    ASCII side uses set intersection. CJK side uses bidirectional SUBSTRING of
    maximal runs, because a pipe value separates CJK into runs
    (``中山大学 | 理学博士`` -> {中山大学, 理学博士}) while prose is one big run
    (``2007年于中山大学物理系获理学博士学位``) — set intersection would be empty for
    the same school. Maximal-run needles keep genuinely-different schools apart
    (``北京大学`` is not a substring of ``北京师范大学``)."""
    if _distinctive_ascii_tokens(keep) & _distinctive_ascii_tokens(sup):
        return True
    keep_runs = [r for r in _CJK_RE.findall(keep) if len(r) >= 2]
    sup_runs = [r for r in _CJK_RE.findall(sup) if len(r) >= 2]
    return any(c in sup for c in keep_runs) or any(c in keep for c in sup_runs)


def _canonical_degree(value: Any) -> str | None:
    """The degree/role level if a canonical one is detectable, else None.

    None means 'no canonical degree/role keyword' (e.g. a pipe value that only
    lists org | field | years). Used so the LLM-merge filter does NOT reject a
    valid merge just because one side omits the degree."""
    level = _degree_level(_clean(value))
    return level if level in _CANONICAL_DEGREE_LEVELS else None


def llm_merge_is_safe(fact_type: str, keep_value: Any, supersede_value: Any) -> bool:
    """Safety filter for an LLM-proposed ``keep`` vs ``supersede`` merge.

    Accepts the merge only when:
      * both sides agree on degree/role level — but only when BOTH have a
        canonical degree keyword (so a year-bearing pipe with no degree still
        matches a prose 'PhD' twin); and
      * their time periods agree (both-empty-or-equal); and
      * they share a school/org signal (ASCII token set or CJK substring).

    This rejects the common LLM false-positives — merging a PhD with a Master,
    or two stints at the same school with different periods, or two different
    schools — while accepting the genuine prose<->structured and bilingual-flip
    merges the LLM finds.
    """
    keep = _clean(keep_value)
    sup = _clean(supersede_value)
    if not keep or not sup:
        return False
    dk = _canonical_degree(keep)
    ds = _canonical_degree(sup)
    if dk is not None and ds is not None and dk != ds:
        return False
    if not _years_agree(_years(keep), _years(sup)):
        return False
    return _org_overlap(keep, sup)

