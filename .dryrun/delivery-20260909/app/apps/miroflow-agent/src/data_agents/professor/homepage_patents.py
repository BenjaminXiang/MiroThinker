"""Conservative patents-section extractor for professor Tier 2 / Tier 3
homepages.

Per OpenSpec change `prof-paper-patent-from-page-flow` spec
Requirement "Patents-section extraction from prof Tier 2/3 pages": only
sections whose heading matches one of `专利 / Patents /
Patent Applications / 发明专利 / 实用新型 / 外观` are processed. Sibling
modules (paper/homepage_ingest.py + professor/homepage_publications.py)
own the Publications path; this module is intentionally narrower because
patent-section layout is far more uniform than Publications and most
prof pages do not list patents at all (design.md §3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)

_PATENTS_HEADING_KEYWORDS: tuple[str, ...] = (
    "patent applications",
    "patents",
    "patent",
    "授权专利",
    "发明专利",
    "实用新型",
    "外观设计",
    "外观",
    "专利成果",
    "专利申请",
    "专利",
)

_PATENTS_HEADING_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(keyword) for keyword in _PATENTS_HEADING_KEYWORDS)
    + r")[:：]?$",
    re.IGNORECASE,
)

_LANDMARK_TAGS = ("header", "footer", "nav", "aside")
_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_NON_HEADING_SECTION_TAG_NAMES = ("p", "div")

_ITEM_PREFIX_RE = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+\s*[.)、．。])\s*")
_WHITESPACE_RE = re.compile(r"\s+")

# Conservative patent-id patterns. Patterns are matched in declared order; the
# first that succeeds wins. Each pattern targets a distinct registry family:
#   - CN / ZL ........... Chinese patent numbers (with optional checksum dot)
#   - US ................ US patent / publication numbers
#   - EP / JP / KR / WO . European, Japanese, Korean, PCT-international
# We intentionally keep matching conservative: noisy free-text strings like
# "专利号待批" should NOT match. Two-letter prefixes followed by digits are
# the canonical wire format on prof pages.
_PATENT_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    # CN/ZL patent numbers carry an optional check character that may be
    # either a digit (e.g. ".6") or the letter X (used as a stand-in for
    # checksum value 10).
    re.compile(r"\b(?:ZL|CN)\s*\d{8,13}(?:\.[0-9X])?\b", re.IGNORECASE),
    re.compile(r"\bUS\s*\d{7,11}(?:[A-Z]\d?)?\b", re.IGNORECASE),
    re.compile(r"\bEP\s*\d{7,10}(?:[A-Z]\d?)?\b", re.IGNORECASE),
    re.compile(r"\b(?:JP|KR)\s*\d{4}-?\d{6,7}\b", re.IGNORECASE),
    re.compile(r"\bWO\s*\d{4}/?\d{6}\b", re.IGNORECASE),
)

# Granted vs filed date hints. When a date appears alongside one of these
# keywords we tag it accordingly; otherwise the date is treated as an
# application date by convention (most prof pages list filings, not grants).
_GRANT_KEYWORDS = (
    "授权",
    "授权日",
    "授予",
    "授权公告日",
    "颁证",
    "grant date",
    "granted",
    "issued",
)
_APPLICATION_KEYWORDS = (
    "申请",
    "申请日",
    "filed",
    "filing date",
    "application date",
)

_DATE_ISO_RE = re.compile(r"\b(?P<year>\d{4})[-./](?P<month>\d{1,2})(?:[-./](?P<day>\d{1,2}))?\b")
_DATE_CN_RE = re.compile(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月(?:\s*(?P<day>\d{1,2})\s*日)?")
_DATE_YEAR_ONLY_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b")

_INVENTOR_PREFIX_RE = re.compile(
    r"(?:发明人|inventors?|inventor[s]?:)\s*[:：]?\s*",
    re.IGNORECASE,
)
_INVENTOR_SPLIT_RE = re.compile(r"[,，;；、/\s]+")

_MIN_TITLE_LENGTH = 6
_MAX_ITEMS_PER_PAGE = 100


@dataclass(frozen=True, slots=True)
class PatentEntry:
    """A patent candidate extracted from a single prof homepage section.

    `title` is the only required field. All other fields are best-effort:
    most prof pages list patents as "title (registration-number, year)"
    or "title — application no. XXX". The downstream ingest module
    (`patent/homepage_ingest.py`) decides whether the candidate has
    enough fields to satisfy the V004 schema's NOT NULL constraints, or
    whether to file a `pipeline_issue` with stage="data_quality_flag".
    """

    title: str
    patent_id: str | None = None
    application_date: date | None = None
    grant_date: date | None = None
    inventors: tuple[str, ...] = field(default_factory=tuple)
    source_url: str = ""
    source_anchor: str | None = None


def extract_patents_from_html(html: str, *, page_url: str) -> list[PatentEntry]:
    """Extract patent candidates from a prof homepage HTML string.

    Returns an empty list when no patents-section heading is found (this
    is the normal case — most prof pages have no patents section).
    """
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    for tag_name in _LANDMARK_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    sections = _find_patents_sections(soup)
    if not sections:
        return []

    collected: list[PatentEntry] = []
    for section in sections:
        collected.extend(_extract_section_patents(section, page_url=page_url))

    deduped = _dedupe_entries(collected)
    if len(deduped) > _MAX_ITEMS_PER_PAGE:
        logger.warning(
            "Extracted %s patents from %s; truncating to %s",
            len(deduped),
            page_url,
            _MAX_ITEMS_PER_PAGE,
        )
        deduped = deduped[:_MAX_ITEMS_PER_PAGE]

    return deduped


def _find_patents_sections(soup: BeautifulSoup) -> list[Tag]:
    sections: list[Tag] = []
    seen: set[int] = set()

    for tag in soup.find_all(_HEADING_TAG_NAMES):
        if _is_patents_heading_text(tag.get_text(" ", strip=True)):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    for tag in soup.find_all(True):
        values = [*tag.get("class", []), tag.get("id")]
        attributes = " ".join(str(value) for value in values if value).casefold()
        if not attributes:
            continue
        if any(keyword in attributes for keyword in _PATENTS_HEADING_KEYWORDS):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    for tag in soup.find_all(_NON_HEADING_SECTION_TAG_NAMES):
        if _is_non_heading_patents_heading(tag):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    return sections


def _is_patents_heading_text(text: str) -> bool:
    normalized = _normalize_sentence(text).strip(" ：:-•*#\t")
    if not normalized:
        return False
    if _PATENTS_HEADING_RE.fullmatch(normalized):
        return True
    lowered = normalized.casefold()
    if len(lowered) > 60:
        return False
    return any(keyword in lowered for keyword in _PATENTS_HEADING_KEYWORDS)


def _is_non_heading_patents_heading(tag: Tag) -> bool:
    if tag.name in _HEADING_TAG_NAMES or tag.name not in _NON_HEADING_SECTION_TAG_NAMES:
        return False
    text = tag.get_text(" ", strip=True)
    normalized = _normalize_sentence(text).strip().rstrip(":：").strip()
    if not normalized or len(normalized) > 40:
        return False
    if not _is_patents_heading_text(normalized):
        return False
    # Require a visible-heading marker so we don't misread free-flowing
    # body copy that happens to contain the word "patent".
    has_marker = (
        tag.name in {"strong", "b"}
        or tag.find(["strong", "b"]) is not None
        or _has_title_class(tag)
    )
    return has_marker or _PATENTS_HEADING_RE.fullmatch(normalized) is not None


def _has_title_class(tag: Tag) -> bool:
    class_values = tag.get("class", [])
    if isinstance(class_values, str):
        class_values = [class_values]
    return any(
        "tit" in str(value).casefold() or "title" in str(value).casefold()
        for value in class_values
    )


def _extract_section_patents(section: Tag, *, page_url: str) -> list[PatentEntry]:
    items: list[PatentEntry] = []

    blocks = _section_root_blocks(section)
    if not blocks:
        return items

    # Strategy order mirrors homepage_publications but is narrower: list →
    # paragraphs → table. First strategy that yields rows wins.
    for strategy in (_extract_from_list, _extract_from_paragraphs, _extract_from_table):
        items = strategy(blocks, page_url=page_url)
        if items:
            return items
    return items


def _extract_from_list(blocks: list[Tag], *, page_url: str) -> list[PatentEntry]:
    items: list[PatentEntry] = []
    for block in blocks:
        list_tags = [block] if block.name in {"ol", "ul"} else []
        list_tags.extend(block.find_all(["ol", "ul"]))
        for list_tag in list_tags:
            for li in list_tag.find_all("li", recursive=False):
                entry = _entry_from_tag(li, page_url=page_url)
                if entry is not None:
                    items.append(entry)
    return items


def _extract_from_paragraphs(blocks: list[Tag], *, page_url: str) -> list[PatentEntry]:
    items: list[PatentEntry] = []
    for block in blocks:
        paragraphs = [block] if block.name == "p" else []
        paragraphs.extend(block.find_all("p"))
        for paragraph in paragraphs:
            for text in _paragraph_texts(paragraph):
                entry = _entry_from_text(
                    text,
                    source_url=page_url,
                    source_anchor=_extract_source_anchor(paragraph, page_url),
                )
                if entry is not None:
                    items.append(entry)
    return items


def _extract_from_table(blocks: list[Tag], *, page_url: str) -> list[PatentEntry]:
    items: list[PatentEntry] = []
    for block in blocks:
        tables = [block] if block.name == "table" else []
        tables.extend(block.find_all("table"))
        for table in tables:
            headers = _table_header_texts(table)
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"], recursive=False)
                if not cells or all(cell.name == "th" for cell in cells):
                    continue
                texts = [
                    _normalize_sentence(cell.get_text(" ", strip=True))
                    for cell in cells
                ]
                # Prepend column-header context (e.g. "授权日 2024-05-01")
                # so date classification picks up grant vs filing intent
                # that the bare cell value would otherwise drop.
                annotated = [
                    _annotate_cell_with_header(text, headers[idx] if idx < len(headers) else "")
                    for idx, text in enumerate(texts)
                ]
                joined = " | ".join(part for part in annotated if part)
                if not joined:
                    continue
                entry = _entry_from_text(
                    joined,
                    source_url=page_url,
                    source_anchor=_extract_source_anchor(row, page_url),
                )
                if entry is not None:
                    items.append(entry)
    return items


def _table_header_texts(table: Tag) -> list[str]:
    header_row = table.find("tr")
    if header_row is None:
        return []
    cells = header_row.find_all(["th", "td"], recursive=False)
    if not cells or not all(cell.name == "th" for cell in cells):
        return []
    return [
        _normalize_sentence(cell.get_text(" ", strip=True))
        for cell in cells
    ]


def _annotate_cell_with_header(text: str, header: str) -> str:
    if not text:
        return ""
    if not header:
        return text
    return f"{header} {text}"


def _section_root_blocks(section: Tag) -> list[Tag]:
    if section.name in _HEADING_TAG_NAMES:
        current_level = int(section.name[1])
        blocks = _following_blocks_until_heading(section, current_level=current_level)
        return blocks
    if section.name in _NON_HEADING_SECTION_TAG_NAMES and _is_non_heading_patents_heading(
        section
    ):
        blocks = _following_blocks_until_non_heading_boundary(section)
        return blocks
    return [section]


def _following_blocks_until_heading(section: Tag, *, current_level: int) -> list[Tag]:
    blocks: list[Tag] = []
    for sibling in section.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if (
            sibling.name in _HEADING_TAG_NAMES
            and int(sibling.name[1]) <= current_level
        ):
            break
        blocks.append(sibling)
    return blocks


def _following_blocks_until_non_heading_boundary(section: Tag) -> list[Tag]:
    blocks: list[Tag] = []
    for sibling in section.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name in _HEADING_TAG_NAMES:
            break
        if (
            sibling.name in _NON_HEADING_SECTION_TAG_NAMES
            and _has_title_class(sibling)
        ):
            break
        blocks.append(sibling)
    return blocks


def _entry_from_tag(tag: Tag, *, page_url: str) -> PatentEntry | None:
    raw_text = _normalize_sentence(tag.get_text(" ", strip=True))
    if not raw_text:
        return None
    return _entry_from_text(
        raw_text,
        source_url=page_url,
        source_anchor=_extract_source_anchor(tag, page_url),
    )


def _entry_from_text(
    raw_text: str,
    *,
    source_url: str,
    source_anchor: str | None,
) -> PatentEntry | None:
    text = _strip_item_prefix(_normalize_sentence(raw_text))
    if not text:
        return None

    patent_id = _extract_patent_id(text)
    application_date, grant_date = _extract_dates(text)
    inventors = _extract_inventors(text)
    title = _extract_title(text, patent_id=patent_id, inventors=inventors)
    if title is None or len(title) < _MIN_TITLE_LENGTH:
        return None

    return PatentEntry(
        title=title,
        patent_id=patent_id,
        application_date=application_date,
        grant_date=grant_date,
        inventors=inventors,
        source_url=source_url,
        source_anchor=source_anchor,
    )


def _extract_patent_id(text: str) -> str | None:
    for pattern in _PATENT_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(0)
            return _WHITESPACE_RE.sub("", value).upper()
    return None


def _extract_dates(text: str) -> tuple[date | None, date | None]:
    """Find at most one application date + one grant date in `text`.

    Each match is classified by the nearest preceding keyword window:
    "授权" → grant_date; "申请" → application_date. Unlabeled dates
    default to application_date (most prof pages list filings).
    """
    application: date | None = None
    grant: date | None = None
    for date_value, classification in _iter_classified_dates(text):
        if classification == "grant" and grant is None:
            grant = date_value
        elif classification == "application" and application is None:
            application = date_value
        elif application is None:
            application = date_value
        if application is not None and grant is not None:
            break
    return application, grant


def _iter_classified_dates(text: str):
    seen_spans: list[tuple[int, int]] = []
    for pattern in (_DATE_ISO_RE, _DATE_CN_RE):
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            if any(not (e <= start or end <= s) for s, e in seen_spans for start, end in [span]):
                continue
            year = int(match.group("year"))
            month = int(match.group("month"))
            day_token = match.groupdict().get("day")
            day = int(day_token) if day_token else 1
            current_year = datetime.now().year
            if not (1900 <= year <= current_year + 1):
                continue
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                continue
            try:
                parsed = date(year, month, day)
            except ValueError:
                continue
            seen_spans.append(span)
            classification = _classify_date_window(text, match.start())
            yield parsed, classification

    # Year-only matches are too ambiguous to record as a full date. A bare
    # year on a prof page (e.g. "授权于 2024") could mean either filing
    # or grant; we leave the date None and let downstream ingest treat the
    # candidate as missing dates. This keeps the contract honest.


def _classify_date_window(text: str, match_start: int) -> str:
    window_start = max(0, match_start - 30)
    window = text[window_start:match_start].casefold()
    if any(keyword in window for keyword in _GRANT_KEYWORDS):
        return "grant"
    if any(keyword in window for keyword in _APPLICATION_KEYWORDS):
        return "application"
    return "unknown"


def _extract_inventors(text: str) -> tuple[str, ...]:
    match = _INVENTOR_PREFIX_RE.search(text)
    if not match:
        return ()
    tail = text[match.end() :]
    end_of_segment_idx = _find_inventor_segment_end(tail)
    segment = tail[:end_of_segment_idx]
    tokens = [
        token.strip()
        for token in _INVENTOR_SPLIT_RE.split(segment)
        if token.strip()
    ]
    inventors: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        if not _looks_like_person_name(token):
            continue
        seen.add(token)
        inventors.append(token)
    return tuple(inventors)


def _find_inventor_segment_end(text: str) -> int:
    """End the inventor list at the first sentence boundary or keyword."""
    for stop_re in (
        re.compile(r"[。.](?:\s|$)"),
        re.compile(r"\s*[（(](?:专利|授权|申请|公告|公开|patent)", re.IGNORECASE),
    ):
        match = stop_re.search(text)
        if match:
            return match.start()
    return min(len(text), 80)


def _looks_like_person_name(token: str) -> bool:
    if not token or len(token) > 20:
        return False
    if re.search(r"\d", token):
        return False
    if re.fullmatch(r"[一-鿿]{2,4}", token):
        return True
    if re.fullmatch(r"[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*", token):
        return True
    if re.fullmatch(r"[A-Z]\.\s?[A-Z][a-z]+", token):
        return True
    return False


def _extract_title(
    text: str,
    *,
    patent_id: str | None,
    inventors: tuple[str, ...],
) -> str | None:
    candidate = text
    quoted = re.search(r"[《「『]([^》」』]{4,200})[》」』]", candidate)
    if quoted:
        title = quoted.group(1).strip()
        return _clean_title(title)

    if patent_id:
        for pattern in _PATENT_ID_PATTERNS:
            candidate = pattern.sub("", candidate)

    candidate = _INVENTOR_PREFIX_RE.split(candidate, maxsplit=1)[0]
    for stop_pattern in (
        r"\s*[（(]\s*(?:专利号|申请号|公告号|公开号|授权日|申请日)[^）)]*[)）]\s*",
        r"\s*[（(][^)）]{0,80}(?:授权|申请|公告)[^)）]{0,80}[)）]\s*",
    ):
        candidate = re.sub(stop_pattern, " ", candidate, flags=re.IGNORECASE)

    # Drop trailing date / publication-number tokens.
    candidate = _DATE_ISO_RE.sub(" ", candidate)
    candidate = _DATE_CN_RE.sub(" ", candidate)
    candidate = _DATE_YEAR_ONLY_RE.sub(" ", candidate)

    # Split on common delimiters; keep the longest chunk that doesn't
    # look like metadata.
    parts = [
        _clean_title(part)
        for part in re.split(r"[,，;；|]+", candidate)
        if _clean_title(part)
    ]
    parts = [
        part
        for part in parts
        if not _looks_like_metadata_only(part, inventors=inventors)
    ]
    if not parts:
        return None
    return max(parts, key=len)


def _clean_title(text: str) -> str:
    normalized = _normalize_sentence(text).strip(" ,，;；:：.。、-—_·*")
    return normalized


def _looks_like_metadata_only(text: str, *, inventors: tuple[str, ...]) -> bool:
    if not text:
        return True
    if len(text) < _MIN_TITLE_LENGTH:
        return True
    inventor_set = set(inventors)
    if text in inventor_set:
        return True
    # Pure inventor lists.
    tokens = [
        token.strip()
        for token in _INVENTOR_SPLIT_RE.split(text)
        if token.strip()
    ]
    if tokens and all(_looks_like_person_name(token) for token in tokens):
        return True
    return False


def _paragraph_texts(paragraph: Tag) -> list[str]:
    """Split a `<p>` on `<br>` boundaries; otherwise return one chunk."""
    if paragraph.find("br") is None:
        text = _normalize_sentence(paragraph.get_text(" ", strip=True))
        return [text] if text else []

    pieces: list[str] = []
    # Replace <br> with a sentinel, then split — this avoids the descendant
    # / NavigableString traversal pitfalls (NavigableString has .name=None
    # which is easy to filter incorrectly).
    sentinel = "\x1f__BR__\x1f"
    clone = BeautifulSoup(str(paragraph), "lxml")
    for br in clone.find_all("br"):
        br.replace_with(sentinel)
    raw = clone.get_text("")
    for piece in raw.split(sentinel):
        normalized = _normalize_sentence(piece)
        if normalized:
            pieces.append(normalized)
    return pieces


def _extract_source_anchor(tag: Tag, page_url: str) -> str | None:
    for anchor in tag.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#"):
            continue
        return urljoin(page_url, href)
    return None


def _strip_item_prefix(text: str) -> str:
    return _ITEM_PREFIX_RE.sub("", text).strip()


def _normalize_sentence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip(" \t\r\n")


def _dedupe_entries(entries: list[PatentEntry]) -> list[PatentEntry]:
    seen: set[tuple[str, str | None]] = set()
    deduped: list[PatentEntry] = []
    for entry in entries:
        key = (_normalize_title_for_dedup(entry.title), entry.patent_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _normalize_title_for_dedup(title: str) -> str:
    text = title.casefold()
    text = re.sub(r"[^\w一-鿿]+", " ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()
