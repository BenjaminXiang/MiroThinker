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

import collections
import hashlib
import json
import re
from dataclasses import dataclass, field
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
CITY_ONLY_RE = re.compile(r"^[\u4e00-\u9fff]{2,6}市$")
PROVINCE_LEVEL_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}(?:省|市|自治区|特别行政区)$")
PROVINCE_DASH_SEGMENT_RE = re.compile(r"^(?P<province>[^\-]+)-(?P<city>[^\-]+)$")

# Provincial-level names, used to recover the province of a city-only
# geography label from the company's registered address ("苏州市" + address
# containing 江苏 -> "江苏省-苏州市").  Deliberately small and declarative.
PROVINCE_LABELS = (
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
    "河北省",
    "山西省",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "海南省",
    "四川省",
    "贵州省",
    "云南省",
    "陕西省",
    "甘肃省",
    "青海省",
    "台湾省",
    "内蒙古自治区",
    "广西壮族自治区",
    "西藏自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "香港特别行政区",
    "澳门特别行政区",
)

# Prefecture cities whose "市" suffix is dropped by the source ("广东省-珠海").
# Only these may be suffixed; a district-like tail ("南沙") must stay as-is.
PREFECTURE_CITIES = (
    "北京",
    "上海",
    "天津",
    "重庆",
    "广州",
    "深圳",
    "珠海",
    "汕头",
    "佛山",
    "韶关",
    "湛江",
    "肇庆",
    "江门",
    "茂名",
    "惠州",
    "梅州",
    "汕尾",
    "河源",
    "阳江",
    "清远",
    "东莞",
    "中山",
    "潮州",
    "揭阳",
    "云浮",
    "杭州",
    "宁波",
    "温州",
    "苏州",
    "南京",
    "无锡",
    "常州",
    "南通",
    "扬州",
    "合肥",
    "福州",
    "厦门",
    "泉州",
    "济南",
    "青岛",
    "郑州",
    "武汉",
    "长沙",
    "成都",
    "西安",
    "昆明",
    "贵阳",
    "南昌",
    "太原",
    "石家庄",
    "兰州",
    "大连",
    "沈阳",
    "长春",
    "哈尔滨",
    "南宁",
    "海口",
    "银川",
    "西宁",
    "拉萨",
    "乌鲁木齐",
    "呼和浩特",
)

# Venue label normalisation (D0-b item 1).  Labels for one venue differ by
# punctuation, case, a trailing year or a parenthetical qualifier; the grouping
# key removes all of them plus the "Proceedings of the ..." prefix family, and
# the published label is the most frequent variant inside its group (ties break
# on the lexicographically smallest label, so the mapping is deterministic).
VENUE_PARENTHETICAL_RE = re.compile(r"[（(][^）)]*[）)]")
VENUE_TRAILING_YEAR_RE = re.compile(r"[\s,，\-]*[（(]?(?:19|20)\d{2}[）)]?\.?$")
VENUE_KEY_STOPWORDS = frozenset(
    {"proceedings", "proc", "the", "of", "on", "in", "for", "and"}
)

# Declared-but-never-filled fields (D0-b item 5) are *measured* on every build
# and decided in the change's design.md table: retiring a declaration means
# revising the content-hash-pinned domain catalog and the typed projection
# contract together, which is a deliberate release-identity change, not a
# cleaning rule.  Until that revision lands, every build reports the list of
# fields that are declared on every document of a domain and empty on all of
# them, so the "declared but unobtainable" surface stays visible and bounded.
#
#
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

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "domain": self.domain,
            "canonical_identity_id": self.canonical_identity_id,
            "field_path": self.field_path,
            "rule": self.rule,
            "value": self.value,
            "reference_id": self.reference_id,
        }


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


def venue_group_key(label: str) -> str:
    """Grouping key for venue label variants (case/punctuation/prefix agnostic)."""
    text = VENUE_PARENTHETICAL_RE.sub(" ", label.casefold())
    text = VENUE_TRAILING_YEAR_RE.sub(" ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    tokens = [token for token in text.split() if token not in VENUE_KEY_STOPWORDS]
    return " ".join(tokens)


def canonicalize_venue_label(label: str) -> str:
    """Strip source artifacts (parenthetical qualifiers, trailing year)."""
    text = VENUE_PARENTHETICAL_RE.sub(" ", label)
    text = VENUE_TRAILING_YEAR_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def venue_canonical_map(labels: Iterable[str]) -> dict[str, str]:
    """Map every variant spelling to its group's published label.

    The published label is the most frequent canonicalised variant of its group;
    ties break on the lexicographically smallest label so the mapping is
    deterministic and independent of iteration order.  Singleton groups map to
    their canonicalised spelling, and the raw spelling maps to the same value,
    so a label is only rewritten into a form its own group justifies.
    """
    counts: dict[str, collections.Counter[str]] = {}
    canonical_by_raw: dict[str, str] = {}
    for label in labels:
        if not isinstance(label, str) or not label.strip():
            continue
        raw = label.strip()
        canonical = canonicalize_venue_label(raw) or raw
        canonical_by_raw[raw] = canonical
        counts.setdefault(venue_group_key(raw), collections.Counter())[canonical] += 1
    mapping: dict[str, str] = {}
    for counter in counts.values():
        winner = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]
        for canonical in counter:
            mapping[canonical] = winner
    return {
        raw: mapping.get(canonical, canonical)
        for raw, canonical in canonical_by_raw.items()
    }


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
    """Normalise or complete a company geography label.

    Four rules, all local to the label plus the company's own address:

    1. a province-only label gains the city named by the address
       (``广东省`` + ``深圳市南山区…`` -> ``广东省-深圳市``);
    2. a city-only label gains the province named by the address
       (``苏州市`` + ``中国（江苏）…`` -> ``江苏省-苏州市``);
    3. a ``省-城市`` label whose city lost its ``市`` gains it when the city is
       a known prefecture city (``广东省-珠海`` -> ``广东省-珠海市``);
    4. a stray leading/trailing separator is stripped (``-开曼群岛`` ->
       ``开曼群岛``).

    Anything else - an unknown tail, an address naming no province, a value
    already in final form, an absent value - is returned untouched, so the rule
    can never invent a location.
    """
    label = (
        _named_reference_label(geography) if isinstance(geography, dict) else geography
    )
    if not isinstance(label, str) or not label.strip():
        return CleaningOutcome(geography)
    text = label.strip()
    address = registered_address if isinstance(registered_address, str) else ""

    cleaned = text.strip("-–— ").strip()
    if not cleaned:
        return CleaningOutcome(geography)
    if cleaned != text:
        return _geography_outcome(geography, cleaned, "geography_separator")

    match = PROVINCE_DASH_SEGMENT_RE.match(cleaned)
    if match is not None:
        city = match.group("city").strip()
        if city and not PROVINCE_LEVEL_RE.match(city):
            suffixed = f"{city}市"
            if not city.endswith("市") and city in PREFECTURE_CITIES:
                return _geography_outcome(
                    geography,
                    f"{match.group('province').strip()}-{suffixed}",
                    "geography_city_suffix",
                )
        return CleaningOutcome(geography)

    if CITY_ONLY_RE.match(cleaned):
        province = next(
            (
                candidate
                for candidate in PROVINCE_LABELS
                if candidate.rstrip("省市自治区特别行政区") in address
                or candidate in address
            ),
            None,
        )
        if province is not None and province != cleaned:
            return _geography_outcome(
                geography, f"{province}-{cleaned}", "geography_province"
            )
        return CleaningOutcome(geography, "geography_unparsed")

    return _derive_province_only_geography(geography, cleaned, address)


def _geography_outcome(
    geography: JsonValue, derived: str, disposition: str
) -> CleaningOutcome:
    if isinstance(geography, dict):
        return CleaningOutcome(
            {
                **geography,
                "reference_id": source_reference_id(derived),
                "name": derived,
            },
            disposition,
        )
    return CleaningOutcome(derived, disposition)


def _derive_province_only_geography(
    geography: JsonValue, label: str, address: str
) -> CleaningOutcome:
    """Province-only labels gain the city named by the address."""
    if not PROVINCE_RE.match(label):
        return CleaningOutcome(geography)
    city = city_label(address.strip())
    if city is None:
        return CleaningOutcome(geography, "geography_unparsed")
    return _geography_outcome(geography, f"{label}-{city}", "geography_derived")


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
    ),
    "professor": ("aliases", "department", "office", "canonical_name_en"),
    "paper": ("keywords", "fields_of_study", "authors", "venue"),
    "patent": ("applicants", "inventors", "ipc_codes", "patent_type"),
}


def canonicalize_venue_reference(
    venue: JsonValue, venue_map: Mapping[str, str]
) -> CleaningOutcome:
    """Publish the group's canonical label for a venue reference."""
    label = _named_reference_label(venue) if isinstance(venue, dict) else venue
    if not isinstance(label, str):
        return CleaningOutcome(venue)
    published = venue_map.get(label.strip())
    if not published or published == label:
        return CleaningOutcome(venue)
    if isinstance(venue, dict):
        return CleaningOutcome(
            {
                **venue,
                "reference_id": source_reference_id(published),
                "name": published,
            },
            "venue_merged",
        )
    return CleaningOutcome(published, "venue_merged")


def _is_empty_published_value(value: JsonValue) -> bool:
    """Empty = absent, empty string, empty list/tuple/dict."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return not value
    return False


def clean_projected_values(
    domain: str,
    values: Mapping[str, JsonValue],
    *,
    canonical_identity_id: str = "",
    venue_map: Mapping[str, str] | None = None,
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

    if domain == "paper" and venue_map is not None:
        venue_outcome = canonicalize_venue_reference(
            outcome_values.get("venue"), venue_map
        )
        if venue_outcome.disposition != DISPOSITION_CLEAN:
            outcome_values["venue"] = venue_outcome.value

    for field_path in CLEANED_TEXT_FIELDS.get(domain, ()):
        if field_path not in outcome_values:
            continue
        original = outcome_values[field_path]
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
class ApplicantAudit:
    """Applicant-row accounting for the published patent documents."""

    rows: int
    bound_rows: int
    unbound_rows: int
    nameless_rows: int
    invalid_binding_rows: int

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "rows": self.rows,
            "bound_rows": self.bound_rows,
            "unbound_rows": self.unbound_rows,
            "nameless_rows": self.nameless_rows,
            "invalid_binding_rows": self.invalid_binding_rows,
        }


def audit_patent_applicants(
    payload: Mapping[str, JsonValue], *, released_company_ids: frozenset[str]
) -> ApplicantAudit:
    """Count bound/unbound/nameless applicant rows in one patent payload.

    Decision (design.md): unbound rows are *kept* - they carry the applicant's
    own name, which is the raw material for company binding (D1) - and the
    unbound state is already machine-readable as ``canonical_company_id: null``,
    which is exactly what ``_direct_patent_applicant_scan`` filters on.  What
    must never happen is a row without any name, or a binding that points at a
    company the release does not contain.
    """
    rows = bound = unbound = nameless = invalid = 0
    for applicant in payload.get("applicants") or ():
        if not isinstance(applicant, dict):
            continue
        rows += 1
        name = applicant.get("name") or applicant.get("company_name")
        company_id = applicant.get("canonical_company_id")
        if not isinstance(name, str) or not name.strip():
            nameless += 1
        if not isinstance(company_id, str) or not company_id.strip():
            unbound += 1
            continue
        bound += 1
        if released_company_ids and company_id not in released_company_ids:
            invalid += 1
    return ApplicantAudit(
        rows=rows,
        bound_rows=bound,
        unbound_rows=unbound,
        nameless_rows=nameless,
        invalid_binding_rows=invalid,
    )


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
    applicant_rows: int = 0
    applicant_bound_rows: int = 0
    applicant_unbound_rows: int = 0
    applicant_nameless_rows: int = 0
    applicant_invalid_binding_rows: int = 0
    declared_never_filled_fields: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    # Diagnostic samples (not part of the released report contract): the gate
    # message names its offenders so a failed multi-hour build is diagnosable
    # without a re-run.
    placeholder_examples: tuple[str, ...] = ()
    glue_examples: tuple[str, ...] = ()
    research_direction_examples: tuple[str, ...] = ()

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
            "applicant": {
                "rows": self.applicant_rows,
                "bound_rows": self.applicant_bound_rows,
                "unbound_rows": self.applicant_unbound_rows,
                "nameless_rows": self.applicant_nameless_rows,
                "invalid_binding_rows": self.applicant_invalid_binding_rows,
            },
            "declared_never_filled_fields": {
                domain: list(fields)
                for domain, fields in sorted(self.declared_never_filled_fields.items())
            },
            "declared_never_filled_field_count": sum(
                len(fields) for fields in self.declared_never_filled_fields.values()
            ),
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
    domain: str,
    payload: Mapping[str, JsonValue],
    *,
    examples: dict[str, list[str]] | None = None,
) -> dict[str, int]:
    """Count cleaning-relevant findings in one published projection payload.

    ``examples`` (optional) collects up to :data:`EXAMPLE_LIMIT` offenders per
    kind as ``"domain.field_path: value"`` strings for gate diagnostics.
    """
    findings = {
        "placeholder_hits": 0,
        "glue_damaged_values": 0,
        "glue_legit_values": 0,
        "research_direction_entries": 0,
        "research_direction_junk": 0,
    }

    def record(kind: str, field_path: str, text: str) -> None:
        if examples is None:
            return
        bucket = examples.setdefault(kind, [])
        if len(bucket) < EXAMPLE_LIMIT:
            bucket.append(f"{domain}.{field_path}: {text[:120]}")

    for field_path, text in _iter_document_strings(dict(payload)):
        if placeholder_family(text) is not None:
            findings["placeholder_hits"] += 1
            record("placeholder", field_path, text)
        elif GLUE_TOKEN in text:
            if glue_damaged(text):
                findings["glue_damaged_values"] += 1
                record("glue", field_path, text)
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
                    record("research_direction", "research_directions", label)
    return findings


def audit_lookup_documents(
    documents: Iterable[object],
    *,
    released_company_ids: frozenset[str] = frozenset(),
) -> PublicationQualityReport:
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
    domain_counts: dict[str, int] = {}
    applicants = ApplicantAudit(0, 0, 0, 0, 0)
    declared_fields: dict[str, dict[str, list[int]]] = {}
    examples: dict[str, list[str]] = {}
    for document in documents:
        domain = getattr(document, "domain", None)
        if domain is None:
            continue
        content = getattr(document, "lookup_content", None)
        if not isinstance(content, str):
            continue
        payload = json.loads(content)
        documents_count += 1
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        findings = audit_projection_payload(domain, payload, examples=examples)
        for key, value in findings.items():
            totals[key] += value
        if domain == "company":
            label = payload.get("geography")
            label = _named_reference_label(label) if isinstance(label, dict) else label
            if isinstance(label, str) and label.strip():
                geography_total += 1
                if "-" in label:
                    geography_city_level += 1
        elif domain == "patent":
            audit = audit_patent_applicants(
                payload, released_company_ids=released_company_ids
            )
            applicants = ApplicantAudit(
                rows=applicants.rows + audit.rows,
                bound_rows=applicants.bound_rows + audit.bound_rows,
                unbound_rows=applicants.unbound_rows + audit.unbound_rows,
                nameless_rows=applicants.nameless_rows + audit.nameless_rows,
                invalid_binding_rows=(
                    applicants.invalid_binding_rows + audit.invalid_binding_rows
                ),
            )
        per_field = declared_fields.setdefault(domain, {})
        for declared_field, field_value in payload.items():
            counters = per_field.setdefault(declared_field, [0, 0])
            counters[0] += 1
            if not _is_empty_published_value(field_value):
                counters[1] += 1
    return PublicationQualityReport(
        documents=documents_count,
        geography_total=geography_total,
        geography_city_level=geography_city_level,
        applicant_rows=applicants.rows,
        applicant_bound_rows=applicants.bound_rows,
        applicant_unbound_rows=applicants.unbound_rows,
        applicant_nameless_rows=applicants.nameless_rows,
        applicant_invalid_binding_rows=applicants.invalid_binding_rows,
        declared_never_filled_fields={
            domain: tuple(
                sorted(
                    declared_field
                    for declared_field, (present, filled) in per_field.items()
                    if present == domain_counts.get(domain, 0) and filled == 0
                )
            )
            for domain, per_field in declared_fields.items()
        },
        placeholder_examples=tuple(examples.get("placeholder", ())),
        glue_examples=tuple(examples.get("glue", ())),
        research_direction_examples=tuple(examples.get("research_direction", ())),
        **totals,
    )


# Publication gates (design.md): a build may not publish placeholder text, glue
# damage or research-direction junk, and company geography must reach city level.
MIN_CITY_LEVEL_GEOGRAPHY_RATIO = 0.90
# How many offenders a gate failure names per kind.
EXAMPLE_LIMIT = 8


class PublicationQualityError(ValueError):
    """The built pack would publish uncleaned data; fail the build."""


def assert_publication_quality(
    report: PublicationQualityReport,
    *,
    min_city_level_ratio: float = MIN_CITY_LEVEL_GEOGRAPHY_RATIO,
) -> None:
    def annotated(count: int, examples: tuple[str, ...]) -> str:
        if not examples:
            return str(count)
        shown = "; ".join(examples[:4])
        more = "" if len(examples) <= 4 else f"; +{len(examples) - 4} more"
        return f"{count} (e.g. {shown}{more})"

    failures: list[str] = []
    if report.placeholder_hits:
        failures.append(
            f"placeholder values published: "
            f"{annotated(report.placeholder_hits, report.placeholder_examples)}"
        )
    if report.glue_damaged_values:
        failures.append(
            f"glue-damaged values published: "
            f"{annotated(report.glue_damaged_values, report.glue_examples)}"
        )
    if report.research_direction_junk:
        failures.append(
            "research-direction junk published: "
            f"{annotated(report.research_direction_junk, report.research_direction_examples)}"
        )
    if report.geography_total and report.city_level_ratio < min_city_level_ratio:
        failures.append(
            "company geography city-level ratio "
            f"{report.city_level_ratio:.4f} < {min_city_level_ratio:.2f}"
        )
    if report.applicant_nameless_rows:
        failures.append(
            f"applicant rows published without any name: "
            f"{report.applicant_nameless_rows}"
        )
    if report.applicant_invalid_binding_rows:
        failures.append(
            "applicant bindings outside the released company set: "
            f"{report.applicant_invalid_binding_rows}"
        )
    if failures:
        raise PublicationQualityError("; ".join(failures))


def quarantine_records_from_selections(
    selections: Iterable[tuple[str, str, str, JsonValue]],
) -> tuple[QuarantineRecord, ...]:
    """Re-derive the quarantine for a build from its own source selections.

    ``selections`` yields ``(domain, canonical_identity_id, field_path, value)``.
    The rules are the same pure functions the projection applies, so the report
    and the published pack cannot disagree; nothing is read back from the pack.
    """
    grouped: dict[tuple[str, str], dict[str, JsonValue]] = {}
    order: list[tuple[str, str]] = []
    for domain, identity_id, field_path, value in selections:
        key = (domain, identity_id)
        if key not in grouped:
            grouped[key] = {}
            order.append(key)
        grouped[key][field_path] = value

    records: list[QuarantineRecord] = []
    for key in order:
        domain, identity_id = key
        _cleaned, quarantined = clean_projected_values(
            domain, grouped[key], canonical_identity_id=identity_id
        )
        records.extend(quarantined)
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.domain,
                item.field_path,
                item.canonical_identity_id,
                item.value,
            ),
        )
    )


PUBLICATION_QUALITY_REPORT_SCHEMA_VERSION = "canonical-v2-publication-quality-report-v1"


def compose_publication_quality_report(
    *,
    release_id: str,
    report: PublicationQualityReport,
    quarantine: Iterable[QuarantineRecord] = (),
) -> dict[str, JsonValue]:
    """Compose the build-time quality report payload (deterministic JSON)."""
    records = tuple(quarantine)
    by_rule: dict[str, int] = {}
    for record in records:
        by_rule[record.rule] = by_rule.get(record.rule, 0) + 1
    return {
        "schema_version": PUBLICATION_QUALITY_REPORT_SCHEMA_VERSION,
        "release_id": release_id,
        "publication_audit": report.as_dict(),
        "quarantine_by_rule": by_rule,
        "quarantine_records": [record.as_dict() for record in records],
    }
