from __future__ import annotations

from dataclasses import dataclass
import re

_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)
_NESTED_DOI_RE = re.compile(r"/10\.\d{4,9}/", re.IGNORECASE)
_NATURE_STUB_RE = re.compile(r"^10\.1038/s\d{3,6}$", re.IGNORECASE)
_ACS_JOURNAL_STUB_RE = re.compile(r"^10\.1021/acs\.[a-z][a-z0-9.-]*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DoiQuality:
    raw: str | None
    normalized: str | None
    is_usable: bool
    reason: str | None


def assess_doi_quality(value: object) -> DoiQuality:
    if not isinstance(value, str):
        return DoiQuality(raw=None, normalized=None, is_usable=False, reason="missing")
    raw = value.strip()
    if not raw:
        return DoiQuality(raw=raw, normalized=None, is_usable=False, reason="missing")

    normalized = _strip_doi_prefix(raw).lower()
    if any(separator in normalized for separator in ("|", ",")):
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="contains_separator",
        )
    if any(char.isspace() for char in normalized):
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="contains_whitespace",
        )
    if "://" in normalized or "www." in normalized:
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="contains_url_tail",
        )
    if _NESTED_DOI_RE.search(normalized):
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="nested_doi_prefix",
        )
    if _NATURE_STUB_RE.match(normalized) or _ACS_JOURNAL_STUB_RE.match(normalized):
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="publisher_stub",
        )
    if not _DOI_RE.match(normalized):
        return DoiQuality(
            raw=raw,
            normalized=normalized,
            is_usable=False,
            reason="invalid_format",
        )
    return DoiQuality(raw=raw, normalized=normalized, is_usable=True, reason=None)


def normalize_usable_doi(value: object) -> str | None:
    quality = assess_doi_quality(value)
    return quality.normalized if quality.is_usable else None


def _strip_doi_prefix(value: str) -> str:
    item = value.strip()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "doi:",
        "DOI:",
    ):
        if item.startswith(prefix):
            return item[len(prefix) :].strip()
    return item
