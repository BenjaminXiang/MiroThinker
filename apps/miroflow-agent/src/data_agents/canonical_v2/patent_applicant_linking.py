"""Patent applicant name → release company linking for Canonical V2 builds.

Most released patents carry applicant names but no resolved
``core_facts.company_ids`` (the s12e relationship audit: 1855 of 1931
patents).  This module recovers the missing ``patent_has_applicant`` seeds by
matching applicant name strings against the released companies' names:

- exact lane: punctuation/case-insensitive display-name equality, mirroring
  ``knowledge_build_isolated._source_name_key`` semantics;
- normalized lane: city prefixes (深圳市/上海/北京/广州 and the symmetric
  市-suffixed forms) and company suffixes
  (有限责任公司/股份有限公司/有限公司) are stripped on BOTH sides before
  comparison;
- uniqueness guard: a match that resolves to more than one distinct canonical
  company is abstained — a wrong link is worse than no link.

The module is deliberately pure and side-effect free so the build path can
reuse it inside ``_typed_relationship_seeds`` without import cycles.
Integration contract for the build (owner of ``knowledge_build_isolated.py``):
when a patent row has an empty ``core_facts.company_ids`` list, resolve
``core_facts.applicants`` through ``resolve_patent_applicant_links`` against a
``CompanyNameIndex`` built from the released company rows
(``core_facts.name``/``core_facts.normalized_name`` plus their canonical
assignments), and route every ``accepted`` resolution through the existing
typed-seed path with ``role_id="applicant"``, ``role_owner="target"``,
``evidence_kind="patent_applicant_assertion"``,
``requested_paths=("company_to_patent", "patent_to_company")``,
``catalog_scenario_id="catalog_scenario.patent_has_applicant"``, and
``evidence_metadata={"source_field": f"core_facts.applicants[{i}]",
"match_kind": ..., "matched_company_name": ...}``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

__all__ = [
    "ApplicantCompanyResolution",
    "CompanyNameEntry",
    "CompanyNameIndex",
    "MatchKind",
    "ResolutionStatus",
    "build_company_name_index",
    "company_name_key",
    "normalized_company_name_key",
    "resolve_applicant_company",
    "resolve_patent_applicant_links",
]

MatchKind: TypeAlias = Literal["exact", "normalized"]
ResolutionStatus: TypeAlias = Literal[
    "accepted",
    "abstained_ambiguous",
    "abstained_no_match",
]

# City prefixes stripped from BOTH applicant and company names before the
# normalized comparison.  Longest-first so 深圳市 wins over 深圳; only a
# leading prefix is stripped, never a parenthesized infix such as (深圳).
_CITY_PREFIXES: tuple[str, ...] = (
    "深圳市",
    "上海市",
    "北京市",
    "广州市",
    "深圳",
    "上海",
    "北京",
    "广州",
)
_COMPANY_SUFFIXES: tuple[str, ...] = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
)
# A normalized core shorter than this is meaningless (e.g. a bare city name
# reduces to nothing) and must never be used as a match key.
_MIN_NORMALIZED_KEY_LENGTH = 2


def company_name_key(value: object) -> str | None:
    """Exact-match key: casefold and keep alphanumeric characters only.

    Mirrors ``knowledge_build_isolated._source_name_key`` so CJK punctuation
    and parenthesis style (（深圳） vs (深圳)) cannot break exact matches.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    return normalized or None


def normalized_company_name_key(value: object) -> str | None:
    """Normalized-match key with city prefix and company suffix stripped."""

    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    for prefix in _CITY_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break
    for suffix in _COMPANY_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    key = company_name_key(stripped)
    if key is None or len(key) < _MIN_NORMALIZED_KEY_LENGTH:
        return None
    return key


@dataclass(frozen=True, slots=True)
class CompanyNameEntry:
    """One released company eligible as a patent-applicant link target."""

    object_id: str
    canonical_identity_id: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanyNameIndex:
    """Name-keyed lookup over released companies for applicant resolution."""

    exact_object_ids: Mapping[str, frozenset[str]]
    normalized_object_ids: Mapping[str, frozenset[str]]
    canonical_by_object: Mapping[str, str]
    display_name_by_object: Mapping[str, str]


def build_company_name_index(
    entries: Iterable[CompanyNameEntry],
) -> CompanyNameIndex:
    exact: defaultdict[str, set[str]] = defaultdict(set)
    normalized: defaultdict[str, set[str]] = defaultdict(set)
    canonical_by_object: dict[str, str] = {}
    display_name_by_object: dict[str, str] = {}
    for entry in entries:
        canonical_by_object[entry.object_id] = entry.canonical_identity_id
        if entry.names:
            display_name_by_object[entry.object_id] = entry.names[0]
        for name in entry.names:
            if (exact_key := company_name_key(name)) is not None:
                exact[exact_key].add(entry.object_id)
            if (normalized_key := normalized_company_name_key(name)) is not None:
                normalized[normalized_key].add(entry.object_id)
    return CompanyNameIndex(
        exact_object_ids={
            key: frozenset(value) for key, value in sorted(exact.items())
        },
        normalized_object_ids={
            key: frozenset(value) for key, value in sorted(normalized.items())
        },
        canonical_by_object=canonical_by_object,
        display_name_by_object=display_name_by_object,
    )


@dataclass(frozen=True, slots=True)
class ApplicantCompanyResolution:
    """Outcome of resolving one applicant name against released companies."""

    applicant_name: str
    status: ResolutionStatus
    match_kind: MatchKind | None = None
    company_object_id: str | None = None
    company_canonical_identity_id: str | None = None
    matched_company_name: str | None = None
    candidate_canonical_identity_ids: tuple[str, ...] = ()


def _no_match(applicant_name: str) -> ApplicantCompanyResolution:
    return ApplicantCompanyResolution(
        applicant_name=applicant_name,
        status="abstained_no_match",
    )


def _resolve_candidates(
    *,
    applicant_name: str,
    match_kind: MatchKind,
    object_ids: frozenset[str],
    index: CompanyNameIndex,
) -> ApplicantCompanyResolution:
    canonical_ids = sorted(
        {index.canonical_by_object[object_id] for object_id in object_ids}
    )
    if len(canonical_ids) != 1:
        return ApplicantCompanyResolution(
            applicant_name=applicant_name,
            status="abstained_ambiguous",
            candidate_canonical_identity_ids=tuple(canonical_ids),
        )
    # Several source objects may merge into one canonical company; pick a
    # deterministic object id for the seed endpoint.
    object_id = min(object_ids)
    return ApplicantCompanyResolution(
        applicant_name=applicant_name,
        status="accepted",
        match_kind=match_kind,
        company_object_id=object_id,
        company_canonical_identity_id=canonical_ids[0],
        matched_company_name=index.display_name_by_object.get(object_id),
    )


def resolve_applicant_company(
    *,
    applicant_name: object,
    index: CompanyNameIndex,
) -> ApplicantCompanyResolution:
    """Resolve one applicant name to at most one canonical company."""

    if not isinstance(applicant_name, str) or not applicant_name.strip():
        return _no_match("")
    name = applicant_name.strip()
    exact_ids = index.exact_object_ids.get(company_name_key(name) or "", frozenset())
    if exact_ids:
        return _resolve_candidates(
            applicant_name=name,
            match_kind="exact",
            object_ids=exact_ids,
            index=index,
        )
    normalized_key = normalized_company_name_key(name)
    if normalized_key is None:
        return _no_match(name)
    normalized_ids = index.normalized_object_ids.get(normalized_key, frozenset())
    if not normalized_ids:
        return _no_match(name)
    return _resolve_candidates(
        applicant_name=name,
        match_kind="normalized",
        object_ids=normalized_ids,
        index=index,
    )


def resolve_patent_applicant_links(
    *,
    applicant_names: Iterable[object],
    index: CompanyNameIndex,
) -> tuple[ApplicantCompanyResolution, ...]:
    """Resolve every applicant of one patent, preserving applicant order."""

    return tuple(
        resolve_applicant_company(applicant_name=name, index=index)
        for name in applicant_names
    )
