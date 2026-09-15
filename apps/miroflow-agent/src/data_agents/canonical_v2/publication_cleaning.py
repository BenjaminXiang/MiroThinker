"""Publication-time cleaning rules for the canonical-v2 serving pack.

D0-a data-cleaning batch 1 (2026-09-15, R21): placeholders, glue damage,
company geography city fill and research-direction junk are cleaned where
selected source values become typed domain projections, so nothing dirty
reaches the published lookup/vector documents.  Source assertions stay
verbatim: cleaning happens on the *published projection*, never on the
evidence record.

Vocabulary (mirrors the read-only census in
``.agents/runs/data-quality-assessment/scripts/dqlib.py``):

* **placeholder family** - a value that is a placeholder rather than data.
  Published as absent (``None``), never as a different fake value.
* **glue damage** - a placeholder token that replaced characters *inside* a
  token (e.g. ``DM-7未找到未找到C``), so the original characters cannot be
  recovered.  The value is withheld and listed for review; nothing is guessed.
* **legitimate prose** - the token used as an ordinary word in a sentence
  (``未找到最终目标节点``); kept as-is and counted.

Every rule is a pure function so the same code drives the build projection,
the publication gate and the offline replay counter.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import JsonValue

# Token used by the historical source/backfill pipeline where real characters
# were missing.  It is Chinese text *inside* the value, not a field marker.
GLUE_TOKEN = "未找到"

# Values that carry no information at all; published as absent.
EXACT_PLACEHOLDER_VALUES = frozenset(
    {
        "-",
        "–",
        "—",
        "/",
        "n/a",
        "na",
        "none",
        "null",
        "nil",
        "无",
        "暂无",
        "未知",
        "未找到",
        "无数据",
        "暂无数据",
        "待补充",
        "未提供",
        "未公开",
        "不详",
        "待定",
        "待完善",
        "undefined",
        "not available",
        "not applicable",
        "no data",
        "no info",
        "unknown",
        "tbd",
        "to be determined",
    }
)

# Sentence-shaped placeholders ("Not supplied by the historical source.",
# "No dedicated summary was supplied by the backfill source.", ...).  These
# literals are also produced by the build gate itself
# (``knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK`` and friends);
# ``test_publication_cleaning.py`` pins that they stay covered.
PLACEHOLDER_PREFIX_VALUES = (
    "未找到",
    "暂无",
    "待补充",
    "未提供",
    "未公开",
    "不详",
    "not supplied",
    "no dedicated summary was supplied",
    "not provided",
    "no summary",
    "not available",
    "none supplied",
)

# A whole value that only states that the information does not exist.  Shape
# guarded (single short sentence, nothing else) so informative prose that
# happens to contain the token is never dropped.
NO_INFORMATION_SENTENCE_RE = re.compile(r"^根据现有信息[，,]\s*未找到[^。]{0,40}。$")

# Glue token adjacent to Latin/digit/version characters: the token replaced
# characters inside an identifier or a version string.
GLUE_DAMAGE_RE = re.compile(r"[0-9A-Za-z.]未找到|未找到[0-9A-Za-z.]")

# Reference ids for location labels are deterministic in the build
# (``knowledge_build_isolated``: ``source-reference:{sha256(casefold(name))}``)
# so a derived geography keeps the same reference scheme.
SOURCE_REFERENCE_PREFIX = "source-reference:"

PROVINCE_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}省$")
CITY_RE = re.compile(r"[\u4e00-\u9fff]{2,6}市")
LEADING_PROVINCE_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}(?:省|自治区)")

# Research directions are short noun phrases.  Everything below marks a value
# that is a layout block, a sentence fragment, a truncated tail, a noise token
# or a paragraph dump instead.
RESEARCH_DIRECTION_LAYOUT_MARKERS = (
    "主讲本科课程",
    "主讲研究生课程",
    "教育背景",
    "工作履历",
    "主持项目",
    "代表期刊论文",
    "代表会议论文",
    "代表专利",
    "代表著作",
    "获得荣誉",
    "主要学术兼职",
    "上一篇",
    "下一篇",
    "微信公众号",
    "学习经历",
    "工作经历",
    "开设课程",
    "招生信息",
    "教学情况",
    "学术任职",
)
RESEARCH_DIRECTION_SENTENCE_MARKS = ("。", "，", "；")
RESEARCH_DIRECTION_TRUNCATION_SUFFIXES = ("等", "等）", "等)")
RESEARCH_DIRECTION_MIN_LENGTH = 3
# A research direction never carries a calendar year; a dated value is a
# CV/publication dump ("2016年《哲学研究》论文（关于沼泽人疑难）").
RESEARCH_DIRECTION_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# Disposition codes (also the keys of the published quality report).
DISPOSITION_CLEAN = "clean"
DISPOSITION_PLACEHOLDER = "placeholder"
DISPOSITION_NO_INFORMATION = "no_information_sentence"
DISPOSITION_GLUE_WITHHELD = "glue_damage"
DISPOSITION_GLUE_KEPT = "glue_legit_prose"


@dataclass(frozen=True)
class CleaningOutcome:
    """One cleaned field value plus the rule that decided it."""

    value: JsonValue
    disposition: str = DISPOSITION_CLEAN

    @property
    def dropped(self) -> bool:
        return self.value is None and self.disposition != DISPOSITION_CLEAN


@dataclass(frozen=True)
class QuarantineRecord:
    """A value withheld from publication, kept verbatim for review (D1/LLM)."""

    canonical_identity_id: str
    domain: str
    field_path: str
    rule: str
    value: str
    reference_id: str | None = None


def placeholder_family(value: str) -> str | None:
    """Return ``exact``/``prefix`` when the value is a placeholder, else None."""
    text = value.strip()
    if not text:
        return "exact"
    if text in EXACT_PLACEHOLDER_VALUES or text.lower() in EXACT_PLACEHOLDER_VALUES:
        return "exact"
    lowered = text.lower()
    for prefix in PLACEHOLDER_PREFIX_VALUES:
        if lowered.startswith(prefix):
            return "prefix"
    if NO_INFORMATION_SENTENCE_RE.match(text):
        return "no_information"
    return None


def glue_damaged(value: str) -> bool:
    return GLUE_DAMAGE_RE.search(value) is not None


def clean_text(value: str) -> CleaningOutcome:
    """Clean one published text value (placeholder, glue, no-information)."""
    family = placeholder_family(value)
    if family is not None:
        return CleaningOutcome(
            None,
            (
                DISPOSITION_NO_INFORMATION
                if family == "no_information"
                else DISPOSITION_PLACEHOLDER
            ),
        )
    if GLUE_TOKEN in value:
        if glue_damaged(value):
            return CleaningOutcome(None, DISPOSITION_GLUE_WITHHELD)
        return CleaningOutcome(value, DISPOSITION_GLUE_KEPT)
    return CleaningOutcome(value)


def _named_reference_label(value: Mapping[str, object]) -> str | None:
    for key in ("name", "label"):
        label = value.get(key)
        if isinstance(label, str) and label.strip():
            return label
    return None


def clean_field_value(value: JsonValue, *, field_path: str) -> CleaningOutcome:
    """Clean one projected field value of any shape.

    Scalars and ``{reference_id, name}`` references become ``None`` when they
    are placeholders; list members are cleaned individually so one junk entry
    cannot poison the field.  Non-text shapes are left untouched.
    """
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        kept: list[JsonValue] = []
        disposition = DISPOSITION_CLEAN
        for item in value:
            outcome = clean_field_value(item, field_path=field_path)
            if outcome.dropped:
                disposition = outcome.disposition
                continue
            kept.append(outcome.value)
        return CleaningOutcome(kept, disposition)
    if isinstance(value, dict):
        label = _named_reference_label(value)
        if label is None:
            return CleaningOutcome(value)
        outcome = clean_text(label)
        if outcome.dropped:
            # A reference whose label is a placeholder points at nothing.
            return outcome
        if outcome.value == label:
            return CleaningOutcome(value, outcome.disposition)
        return CleaningOutcome({**value, "name": outcome.value}, outcome.disposition)
    return CleaningOutcome(value)


def clean_research_directions(
    value: JsonValue,
) -> tuple[CleaningOutcome, tuple[tuple[str, str | None], ...]]:
    """Drop research-direction junk; return the survivors and the dropped ones."""
    if not isinstance(value, list):
        return clean_field_value(value, field_path="research_directions"), ()
    kept: list[JsonValue] = []
    quarantined: list[tuple[str, str | None]] = []
    for item in value:
        label = (
            _named_reference_label(item)
            if isinstance(item, dict)
            else item
            if isinstance(item, str)
            else None
        )
        rule = research_direction_rule(label) if isinstance(label, str) else None
        if rule is None:
            kept.append(item)
            continue
        reference_id = item.get("reference_id") if isinstance(item, dict) else None
        quarantined.append(
            (label, reference_id if isinstance(reference_id, str) else None)
        )
    disposition = DISPOSITION_CLEAN if not quarantined else "research_direction_junk"
    return CleaningOutcome(kept, disposition), tuple(quarantined)


def research_direction_rule(value: str) -> str | None:
    """Return the junk rule that quarantines a research direction, else None."""
    text = value.strip()
    if any(marker in text for marker in RESEARCH_DIRECTION_LAYOUT_MARKERS):
        return "layout_block"
    if len(text) < RESEARCH_DIRECTION_MIN_LENGTH:
        return "too_short"
    if RESEARCH_DIRECTION_YEAR_RE.search(text):
        return "dated_dump"
    if any(mark in text for mark in RESEARCH_DIRECTION_SENTENCE_MARKS):
        return "sentence_fragment"
    if text.endswith(RESEARCH_DIRECTION_TRUNCATION_SUFFIXES):
        return "truncated_tail"
    return None


def source_reference_id(name: str) -> str:
    """Deterministic reference id for a label (same scheme as the build)."""
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
    return f"{SOURCE_REFERENCE_PREFIX}{digest}"


def city_label(address: str) -> str | None:
    """Extract the prefecture city ("深圳市") from a registered address.

    A leading province ("广东省深圳市...", "新疆维吾尔自治区乌鲁木齐市...")
    is removed first so the city match cannot swallow the province.
    """
    residual = LEADING_PROVINCE_RE.sub("", address, count=1)
    for match in CITY_RE.findall(residual):
        return match
    return None


def derive_company_geography(
    geography: JsonValue, registered_address: JsonValue
) -> CleaningOutcome:
    """Fill the missing city of a province-only geography from the address.

    Only province-level values are derived; anything else (already city-level,
    absent, or unparseable) is returned untouched so the rule cannot invent a
    location for a company whose address carries none.
    """
    label = (
        _named_reference_label(geography) if isinstance(geography, dict) else geography
    )
    if not isinstance(label, str) or not PROVINCE_RE.match(label.strip()):
        return CleaningOutcome(geography)
    address = registered_address if isinstance(registered_address, str) else ""
    city = city_label(address.strip())
    if city is None:
        return CleaningOutcome(geography, "geography_unparsed")
    derived = f"{label.strip()}-{city}"
    if isinstance(geography, dict):
        return CleaningOutcome(
            {
                **geography,
                "reference_id": source_reference_id(derived),
                "name": derived,
            },
            "geography_derived",
        )
    return CleaningOutcome(derived, "geography_derived")


CLEANED_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "company": (
        "profile_summary",
        "technology_route_summary",
        "product_description",
        "team_description",
    ),
    "professor": (
        "title",
        "email",
        "homepage",
        "profile_summary",
        "paper_summary",
        "patent_summary",
    ),
    "paper": ("title_zh", "abstract", "summary_text", "summary_zh", "tldr"),
    "patent": ("abstract", "summary_text", "technology_effect"),
}

# Reference/alias shaped fields: a placeholder label means "no such value".
CLEANED_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "company": (
        "aliases",
        "industry",
        "industry_tags",
        "legal_representative",
        "tech_tags",
        "website",
        "geography",
        "key_personnel",
        "products",
        "capabilities",
        "business_scenarios",
    ),
    "professor": ("aliases", "department", "office", "canonical_name_en"),
    "paper": ("keywords", "fields_of_study", "authors", "venue"),
    "patent": ("applicants", "inventors", "ipc_codes", "patent_type"),
}


def clean_projected_values(
    domain: str,
    values: Mapping[str, JsonValue],
    *,
    canonical_identity_id: str = "",
) -> tuple[dict[str, JsonValue], list[QuarantineRecord]]:
    """Clean one entity's projected field values before typed validation.

    Returns the cleaned mapping (placeholders absent rather than rewritten)
    plus the quarantine records for values withheld from publication.
    """
    outcome_values = dict(values)
    quarantined: list[QuarantineRecord] = []

    if domain == "company":
        geography_outcome = derive_company_geography(
            outcome_values.get("geography"),
            outcome_values.get("registered_address"),
        )
        if geography_outcome.disposition != DISPOSITION_CLEAN:
            outcome_values["geography"] = geography_outcome.value

    for field_path in CLEANED_TEXT_FIELDS.get(domain, ()):
        if field_path not in outcome_values:
            continue
        original = outcome_values[field_path]
        if field_path == "research_directions":
            continue
        outcome = clean_field_value(original, field_path=field_path)
        if outcome.disposition in (DISPOSITION_GLUE_WITHHELD,):
            quarantined.append(
                QuarantineRecord(
                    canonical_identity_id=canonical_identity_id,
                    domain=domain,
                    field_path=field_path,
                    rule=outcome.disposition,
                    value=original
                    if isinstance(original, str)
                    else json.dumps(original, ensure_ascii=False),
                )
            )
        if outcome.disposition != DISPOSITION_CLEAN:
            outcome_values[field_path] = outcome.value

    for field_path in CLEANED_REFERENCE_FIELDS.get(domain, ()):
        if field_path not in outcome_values:
            continue
        outcome = clean_field_value(outcome_values[field_path], field_path=field_path)
        if outcome.disposition != DISPOSITION_CLEAN:
            outcome_values[field_path] = outcome.value

    if domain == "professor" and "research_directions" in outcome_values:
        outcome, dropped = clean_research_directions(
            outcome_values["research_directions"]
        )
        if outcome.disposition != DISPOSITION_CLEAN:
            outcome_values["research_directions"] = outcome.value
        quarantined.extend(
            QuarantineRecord(
                canonical_identity_id=canonical_identity_id,
                domain=domain,
                field_path="research_directions",
                rule=research_direction_rule(label) or "research_direction_junk",
                value=label,
                reference_id=reference_id,
            )
            for label, reference_id in dropped
        )
    return outcome_values, quarantined


@dataclass(frozen=True)
class PublicationQualityReport:
    """Counts produced by auditing published lookup documents."""

    documents: int
    placeholder_hits: int
    glue_damaged_values: int
    glue_legit_values: int
    geography_total: int
    geography_city_level: int
    research_direction_entries: int
    research_direction_junk: int

    @property
    def city_level_ratio(self) -> float:
        if not self.geography_total:
            return 1.0
        return self.geography_city_level / self.geography_total

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "documents": self.documents,
            "placeholder_hits": self.placeholder_hits,
            "glue_damaged_values": self.glue_damaged_values,
            "glue_legit_values": self.glue_legit_values,
            "geography_total": self.geography_total,
            "geography_city_level": self.geography_city_level,
            "city_level_ratio": round(self.city_level_ratio, 4),
            "research_direction_entries": self.research_direction_entries,
            "research_direction_junk": self.research_direction_junk,
        }


def _iter_document_strings(value: JsonValue) -> Iterable[tuple[str, str]]:
    """Yield ``(field_path, text)`` for every string in a projection payload."""
    if isinstance(value, str):
        yield "", value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_document_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            for path, text in _iter_document_strings(item):
                yield (f"{key}.{path}" if path else key), text


def audit_projection_payload(
    domain: str, payload: Mapping[str, JsonValue]
) -> dict[str, int]:
    """Count cleaning-relevant findings in one published projection payload."""
    findings = {
        "placeholder_hits": 0,
        "glue_damaged_values": 0,
        "glue_legit_values": 0,
        "research_direction_entries": 0,
        "research_direction_junk": 0,
    }
    for field_path, text in _iter_document_strings(dict(payload)):
        if placeholder_family(text) is not None:
            findings["placeholder_hits"] += 1
        elif GLUE_TOKEN in text:
            if glue_damaged(text):
                findings["glue_damaged_values"] += 1
            else:
                findings["glue_legit_values"] += 1
    if domain == "professor":
        directions = payload.get("research_directions")
        if isinstance(directions, list):
            for item in directions:
                label = (
                    _named_reference_label(item)
                    if isinstance(item, dict)
                    else item
                    if isinstance(item, str)
                    else None
                )
                if not isinstance(label, str):
                    continue
                findings["research_direction_entries"] += 1
                if research_direction_rule(label) is not None:
                    findings["research_direction_junk"] += 1
    return findings


def audit_lookup_documents(documents: Iterable[object]) -> PublicationQualityReport:
    """Audit published lookup documents (any object exposing the doc fields)."""
    documents_count = 0
    totals = {
        "placeholder_hits": 0,
        "glue_damaged_values": 0,
        "glue_legit_values": 0,
        "research_direction_entries": 0,
        "research_direction_junk": 0,
    }
    geography_total = 0
    geography_city_level = 0
    for document in documents:
        domain = getattr(document, "domain", None)
        if domain is None:
            continue
        content = getattr(document, "lookup_content", None)
        if not isinstance(content, str):
            continue
        payload = json.loads(content)
        documents_count += 1
        findings = audit_projection_payload(domain, payload)
        for key, value in findings.items():
            totals[key] += value
        if domain == "company":
            label = payload.get("geography")
            label = _named_reference_label(label) if isinstance(label, dict) else label
            if isinstance(label, str) and label.strip():
                geography_total += 1
                if "-" in label:
                    geography_city_level += 1
    return PublicationQualityReport(
        documents=documents_count,
        geography_total=geography_total,
        geography_city_level=geography_city_level,
        **totals,
    )


# Publication gates (design.md): a build may not publish placeholder text, glue
# damage or research-direction junk, and company geography must reach city level.
MIN_CITY_LEVEL_GEOGRAPHY_RATIO = 0.90


class PublicationQualityError(ValueError):
    """The built pack would publish uncleaned data; fail the build."""


def assert_publication_quality(
    report: PublicationQualityReport,
    *,
    min_city_level_ratio: float = MIN_CITY_LEVEL_GEOGRAPHY_RATIO,
) -> None:
    failures: list[str] = []
    if report.placeholder_hits:
        failures.append(f"placeholder values published: {report.placeholder_hits}")
    if report.glue_damaged_values:
        failures.append(f"glue-damaged values published: {report.glue_damaged_values}")
    if report.research_direction_junk:
        failures.append(
            f"research-direction junk published: {report.research_direction_junk}"
        )
    if report.geography_total and report.city_level_ratio < min_city_level_ratio:
        failures.append(
            "company geography city-level ratio "
            f"{report.city_level_ratio:.4f} < {min_city_level_ratio:.2f}"
        )
    if failures:
        raise PublicationQualityError("; ".join(failures))
