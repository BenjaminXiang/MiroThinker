"""Paper-title plausibility guard.

Scraped ``paper_staging`` records occasionally include CV bullet-points
(Ph.D. entries, editorial roles, fellowships, workshop co-chair lines)
harvested from professor homepages. Those leak into ``paper`` rows and
pollute the dashboard. ``is_plausible_paper_title`` is the minimal filter
used at backfill time and for SQL cleanup.
"""

from __future__ import annotations

import re

_NON_PAPER_PREFIXES = (
    "ph.d",
    "ph.d.",
    "phd ",
    "b.sc",
    "b.sc.",
    "b.s.",
    "b.eng",
    "b.eng.",
    "m.sc",
    "m.sc.",
    "m.s.",
    "m.eng",
    "m.eng.",
    "m.phil",
    "d.phil",
    "fellow,",
    "fellow of",
    "member,",
    "member of",
    "senior member,",
    "distinguished fellow",
    "editor,",
    "editor-in-chief",
    "editor in chief",
    "associate editor",
    "co-editor",
    "guest editor",
    "handling editor",
    "managing editor",
    "reviewer",
    "reviewer,",
    "workshop",
    "co-chair",
    "chair,",
    "vice chair",
    "session chair",
    "program chair",
    "general chair",
    "panel ",
    "keynote",
    "invited ",
    "visiting ",
    "assistant professor",
    "associate professor",
    "adjunct",
    "president,",
    "vice president",
    "director,",
    "vice director",
    "dean,",
    "vice dean",
    "teaching prize",
    "teaching award",
    "award,",
    "award:",
    "grant,",
    "grant:",
    "professional ",
    "current position",
    "past position",
    "biography",
    "research area",
    "research interest",
    "research direction",
    "research group",
    "research focus",
    "selected publication",
    "selected public",
    "publications:",
    "books:",
    "book chapter",
    "edited book",
    "edited volume",
    "funded project",
    "teaching:",
    "course:",
    "courses:",
    "service:",
    "education:",
    "appointments:",
    "professional experience",
    "work experience",
    "employment",
    "honors and awards",
    "honors &",
)

_YEAR_RANGE_RE = re.compile(r"^(19|20)\d{2}\s*[-–—]")
_YEAR_DASH_POSITION_RE = re.compile(r"^(19|20)\d{2}\s*[-–—]\s*(present|continue|\d{4})", re.IGNORECASE)


def _normalize(value: str) -> str:
    return " ".join(value.replace("\ufeff", "").split()).strip()


def is_plausible_paper_title(value: str | None) -> bool:
    """Return True if *value* plausibly describes a paper title.

    Conservative: missed junk (false negative) is fine, but blocking a
    real paper (false positive) pollutes recall. Only rejects titles with
    shape indicators that are very unlikely in an academic title.
    """
    if not value:
        return False
    normalized = _normalize(value)
    if not normalized:
        return False
    if len(normalized) < 8:
        return False
    lower = normalized.lower()
    for prefix in _NON_PAPER_PREFIXES:
        if lower.startswith(prefix):
            return False
    if _YEAR_DASH_POSITION_RE.match(normalized):
        return False
    if _YEAR_RANGE_RE.match(normalized) and len(normalized) <= 80:
        # "2011 - 2016, Ph.D..." — year-range plus short descriptor.
        return False
    # Chinese: at least 4 non-ASCII characters to dodge page-nav fragments.
    non_ascii = sum(1 for ch in normalized if ord(ch) > 127)
    if non_ascii == 0:
        # Pure ASCII: require at least 3 space-separated tokens.
        if normalized.count(" ") < 2:
            return False
    return True
