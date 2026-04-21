from __future__ import annotations

import logging
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

from src.data_agents.paper.title_cleaner import clean_paper_title
from src.data_agents.professor.homepage_publication_headings import (
    _PUBLICATIONS_HEADING_KEYWORDS,
    _PUBLICATIONS_HEADING_RE,
)

logger = logging.getLogger(__name__)

_ITEM_PREFIX_RE = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)])\s*")
_ITEM_SUFFIX_RE = re.compile(r"\s*\[(?:J|C|J/OL)\]\s*\.?\s*$", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_WHITESPACE_RE = re.compile(r"\s+")
_QUOTED_TITLE_RE = re.compile(r'["“](.{10,300}?)["”]|《(.{5,300}?)》')
_VENUE_KEYWORD_RE = re.compile(
    r"\b(?:transactions?|journal|proceedings?|conference|conf|symposium|workshop|letters|review|"
    r"neurips|icml|iclr|cvpr|eccv|aaai|acl|emnlp|naacl|kdd|www|sosp|osdi|nsdi|atc|eurosys|"
    r"sc|spaa|isca|socc|hpdc|rss|icra|corl|iros|t-?ro|prx|nature|science|optica|ofc|cleo)\b",
    re.IGNORECASE,
)
_AUTHOR_NAME_RE = re.compile(
    r"(?:"
    r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.?"
    r"|[A-Z]\.\s*[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r")(?:,\s*"
    r"(?:"
    r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.?"
    r"|[A-Z]\.\s*[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"))*"
)
_TRAILING_PUNCTUATION_RE = re.compile(r"^[,;:\-.\s]+|[,;:\-.\s]+$")
_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_LANDMARK_TAGS = ("header", "footer", "nav", "aside")
_MAX_ITEMS_PER_PAGE = 200
_MIN_TITLE_LENGTH = 10


@dataclass(frozen=True, slots=True)
class HomepagePublication:
    raw_title: str
    clean_title: str
    authors_text: str | None
    venue_text: str | None
    year: int | None
    source_url: str
    source_anchor: str | None


def _strip_item_prefix(text: str) -> str:
    return _ITEM_PREFIX_RE.sub("", text).strip()


def _strip_item_suffix(text: str) -> str:
    stripped = _ITEM_SUFFIX_RE.sub("", text)
    return stripped.rstrip(" .,;:")


def _extract_year_from_text(text: str) -> int | None:
    current_year = datetime.now().year
    years = [
        int(match.group(0))
        for match in _YEAR_RE.finditer(text)
        if 1900 <= int(match.group(0)) <= current_year + 1
    ]
    if not years:
        return None
    return max(years)


def _split_title_authors_venue(text: str) -> tuple[str, str | None, str | None]:
    normalized = _normalize_sentence(text)
    if not normalized:
        return "", None, None

    quoted = _extract_quoted_title_segment(normalized)
    if quoted is not None:
        return quoted

    leading_authors, trailing = _split_leading_authors(normalized)
    if leading_authors is not None:
        title, remainder = _split_title_and_remainder(trailing)
        _, venue = _split_remainder_authors_venue(remainder)
        return title or trailing, leading_authors, venue

    title, remainder = _split_title_and_remainder(normalized)
    if not title:
        return normalized, None, None

    authors, venue = _split_remainder_authors_venue(remainder)
    return title, authors, venue


def _normalize_title_for_dedup(text: str) -> str:
    cleaned = clean_paper_title(text).casefold()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def extract_publications_from_html(
    html: str,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None = None,
) -> list[HomepagePublication]:
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    for tag_name in _LANDMARK_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    sections = _find_publications_sections(soup)
    if not sections:
        return []

    collected: list[HomepagePublication] = []
    for section in sections:
        collected.extend(
            _extract_section_publications(
                section,
                page_url=page_url,
                author_filter=author_filter,
            )
        )

    deduped = _dedupe_publications(collected)
    if len(deduped) > _MAX_ITEMS_PER_PAGE:
        logger.warning(
            "Extracted %s publications from %s; truncating to %s",
            len(deduped),
            page_url,
            _MAX_ITEMS_PER_PAGE,
        )
        deduped = deduped[:_MAX_ITEMS_PER_PAGE]

    if sections and len(deduped) < 3:
        logger.warning(
            "Detected publications section on %s but extracted only %s items",
            page_url,
            len(deduped),
        )

    return deduped


def _normalize_sentence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip(" \t\r\n")


def _clean_segment(text: str) -> str:
    return _TRAILING_PUNCTUATION_RE.sub("", clean_paper_title(text))


def _looks_like_authors(text: str) -> bool:
    normalized = _clean_segment(text)
    if not normalized:
        return False
    if " and " in normalized.lower() or "," in normalized:
        return bool(_AUTHOR_NAME_RE.search(normalized))
    return bool(_AUTHOR_NAME_RE.fullmatch(normalized))


def _looks_like_venue(text: str) -> bool:
    normalized = _clean_segment(text)
    if not normalized:
        return False
    return bool(
        _VENUE_KEYWORD_RE.search(normalized) or _extract_year_from_text(normalized)
    )


def _extract_quoted_title_segment(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    match = _QUOTED_TITLE_RE.search(text)
    if not match:
        return None

    title = _clean_segment(match.group(1) or match.group(2) or "")
    if not title:
        return None

    prefix = _clean_segment(text[: match.start()])
    suffix = _clean_segment(text[match.end() :])
    authors = prefix if _looks_like_authors(prefix) else None
    venue = suffix if suffix else None
    return title, authors, venue


def _split_title_and_remainder(text: str) -> tuple[str, str]:
    for match in re.finditer(r"\.\s+", text):
        candidate_title = _clean_segment(text[: match.start()])
        remainder = text[match.end() :].strip()
        if len(candidate_title) < _MIN_TITLE_LENGTH:
            continue
        if _looks_like_authors(candidate_title):
            continue
        if not remainder:
            return candidate_title, ""
        if _looks_like_authors(remainder) or _looks_like_venue(remainder):
            return candidate_title, remainder

    cleaned = _clean_segment(text)
    return cleaned, ""


def _split_remainder_authors_venue(text: str) -> tuple[str | None, str | None]:
    remainder = _normalize_sentence(text)
    if not remainder:
        return None, None

    split_points = list(re.finditer(r"\.\s+", remainder))
    for match in reversed(split_points):
        authors_candidate = _clean_segment(remainder[: match.start()])
        venue_candidate = _clean_segment(remainder[match.end() :])
        if authors_candidate and venue_candidate and _looks_like_venue(venue_candidate):
            if _looks_like_authors(authors_candidate):
                return authors_candidate, venue_candidate

    cleaned = _clean_segment(remainder)
    if _looks_like_authors(cleaned):
        return cleaned, None
    if _looks_like_venue(cleaned):
        return None, cleaned
    return None, None


def _split_leading_authors(text: str) -> tuple[str | None, str]:
    match = re.search(r"\.\s+", text)
    if not match:
        return None, text
    leading = _clean_segment(text[: match.start()])
    if not _looks_like_authors(leading):
        return None, text
    return leading, text[match.end() :].strip()


def _find_publications_sections(soup: BeautifulSoup) -> list[Tag]:
    sections: list[Tag] = []
    seen: set[int] = set()

    for tag in soup.find_all(_HEADING_TAG_NAMES):
        if _is_publications_heading_text(tag.get_text(" ", strip=True)):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    if sections:
        return sections

    for tag in soup.find_all(True):
        values = [*tag.get("class", []), tag.get("id")]
        attributes = " ".join(str(value) for value in values if value).casefold()
        if not attributes:
            continue
        if any(keyword in attributes for keyword in _PUBLICATIONS_HEADING_KEYWORDS):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    return sections


def _extract_section_publications(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    strategies = (
        _extract_from_list,
        _extract_from_paragraphs,
        _extract_from_table,
        _extract_from_year_groups,
        _extract_from_definition_list,
    )
    for strategy in strategies:
        items = strategy(section, page_url=page_url, author_filter=author_filter)
        if items:
            return items
    return []


def _extract_from_list(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    items: list[HomepagePublication] = []
    for list_tag in _iter_section_descendants(section, {"ol", "ul"}):
        for item_tag in list_tag.find_all("li", recursive=False):
            publication = _publication_from_tag(
                item_tag,
                page_url=page_url,
                author_filter=author_filter,
            )
            if publication is not None:
                items.append(publication)
    return items


def _extract_from_paragraphs(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    if _has_year_group_structure(section):
        return []

    items: list[HomepagePublication] = []
    for paragraph in _iter_section_descendants(section, {"p"}):
        publication = _publication_from_tag(
            paragraph,
            page_url=page_url,
            author_filter=author_filter,
        )
        if publication is not None:
            items.append(publication)
    return items


def _extract_from_table(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    items: list[HomepagePublication] = []
    for table in _iter_section_descendants(section, {"table"}):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells or all(cell.name == "th" for cell in cells):
                continue
            texts = [
                _normalize_sentence(cell.get_text(" ", strip=True)) for cell in cells
            ]
            year = next(
                (
                    value
                    for text in texts
                    if (value := _extract_year_from_text(text)) is not None
                ),
                None,
            )
            content_cells = [
                text
                for text in texts
                if text and (_extract_year_from_text(text) != year or len(text) > 6)
            ]
            if not content_cells:
                continue
            title = max(content_cells, key=len)
            venue_candidates = [text for text in content_cells if text != title]
            venue = venue_candidates[0] if venue_candidates else None
            publication = _publication_from_text(
                raw_text=title,
                source_url=page_url,
                source_anchor=_extract_source_anchor(row, page_url),
                author_filter=author_filter,
                year_override=year,
                authors_override=None,
                venue_override=venue,
            )
            if publication is not None:
                items.append(publication)
    return items


def _extract_from_year_groups(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    items: list[HomepagePublication] = []
    current_year: int | None = None

    for element in _iter_section_content(section):
        if isinstance(element, Tag) and element.name in _HEADING_TAG_NAMES:
            year_candidate = _extract_year_from_text(element.get_text(" ", strip=True))
            if year_candidate is not None:
                current_year = year_candidate
                continue
        if not isinstance(element, Tag) or current_year is None:
            continue
        if element.name not in {"p", "li", "dd", "dt"}:
            continue
        publication = _publication_from_tag(
            element,
            page_url=page_url,
            author_filter=author_filter,
            year_override=current_year,
        )
        if publication is not None:
            items.append(publication)
    return items


def _extract_from_definition_list(
    section: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
) -> list[HomepagePublication]:
    items: list[HomepagePublication] = []
    for dl_tag in _iter_section_descendants(section, {"dl"}):
        current_dt: Tag | None = None
        for child in dl_tag.find_all(["dt", "dd"], recursive=False):
            if child.name == "dt":
                current_dt = child
                continue
            if current_dt is None:
                continue
            combined_text = " ".join(
                part
                for part in (
                    current_dt.get_text(" ", strip=True),
                    child.get_text(" ", strip=True),
                )
                if part
            )
            publication = _publication_from_text(
                raw_text=combined_text,
                source_url=page_url,
                source_anchor=(
                    _extract_source_anchor(child, page_url)
                    or _extract_source_anchor(current_dt, page_url)
                ),
                author_filter=author_filter,
            )
            if publication is not None:
                items.append(publication)
    return items


def _publication_from_tag(
    tag: Tag,
    *,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
    year_override: int | None = None,
) -> HomepagePublication | None:
    raw_text = _normalize_sentence(tag.get_text(" ", strip=True))
    if not raw_text:
        return None
    return _publication_from_text(
        raw_text=raw_text,
        source_url=page_url,
        source_anchor=_extract_source_anchor(tag, page_url),
        author_filter=author_filter,
        year_override=year_override,
    )


def _publication_from_text(
    *,
    raw_text: str,
    source_url: str,
    source_anchor: str | None,
    author_filter: Callable[[str | None], bool] | None,
    year_override: int | None = None,
    authors_override: str | None = None,
    venue_override: str | None = None,
) -> HomepagePublication | None:
    normalized = _normalize_sentence(raw_text)
    if not normalized:
        return None

    item_text = _strip_item_suffix(_strip_item_prefix(normalized))
    title_text, authors_text, venue_text = _split_title_authors_venue(item_text)
    clean_title = _clean_segment(_strip_item_suffix(_strip_item_prefix(title_text)))
    if len(clean_title) < _MIN_TITLE_LENGTH:
        return None

    authors_value = authors_override if authors_override is not None else authors_text
    venue_value = venue_override if venue_override is not None else venue_text
    authors_value = _clean_segment(authors_value) if authors_value else None
    venue_value = (
        _clean_segment(_strip_item_suffix(venue_value)) if venue_value else None
    )
    year_value = _validate_year(
        year_override
        if year_override is not None
        else _extract_year_from_text(item_text)
    )

    if author_filter is not None and not author_filter(authors_value):
        return None

    return HomepagePublication(
        raw_title=normalized,
        clean_title=clean_title,
        authors_text=authors_value,
        venue_text=venue_value,
        year=year_value,
        source_url=source_url,
        source_anchor=source_anchor,
    )


def _extract_source_anchor(tag: Tag, page_url: str) -> str | None:
    for anchor in tag.find_all("a", href=True):
        href = anchor["href"].strip()
        if "doi.org" in href or "arxiv.org" in href:
            return urljoin(page_url, href)
    return None


def _iter_section_descendants(section: Tag, names: set[str]) -> list[Tag]:
    descendants: list[Tag] = []
    for block in _section_root_blocks(section):
        if block.name in names:
            descendants.append(block)
        descendants.extend(block.find_all(names))
    return descendants


def _iter_section_content(section: Tag) -> list[PageElement]:
    content: list[PageElement] = []
    for block in _section_root_blocks(section):
        content.append(block)
        if isinstance(block, Tag):
            content.extend(
                child
                for child in block.descendants
                if not isinstance(child, NavigableString)
            )
    return content


def _section_root_blocks(section: Tag) -> list[Tag]:
    if _is_heading_tag(section):
        blocks: list[Tag] = []
        current_level = int(section.name[1])
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
    return [section]


def _has_year_group_structure(section: Tag) -> bool:
    for block in _section_root_blocks(section):
        heading_tags = [block, *block.find_all(_HEADING_TAG_NAMES)]
        for tag in heading_tags:
            if (
                tag.name in _HEADING_TAG_NAMES
                and _extract_year_from_text(tag.get_text(" ", strip=True)) is not None
            ):
                return True
    return False


def _is_heading_tag(tag: Tag) -> bool:
    return tag.name in _HEADING_TAG_NAMES and _is_publications_heading_text(
        tag.get_text(" ", strip=True)
    )


def _is_publications_heading_text(text: str) -> bool:
    normalized = _normalize_sentence(text).strip(" ：:-•*#\t")
    if not normalized:
        return False
    if _PUBLICATIONS_HEADING_RE.fullmatch(normalized):
        return True
    lowered = normalized.casefold()
    return len(lowered) <= 60 and any(
        keyword in lowered for keyword in _PUBLICATIONS_HEADING_KEYWORDS
    )


def _validate_year(year: int | None) -> int | None:
    if year is None:
        return None
    current_year = datetime.now().year
    if 1900 <= year <= current_year + 1:
        return year
    return None


def _dedupe_publications(
    publications: list[HomepagePublication],
) -> list[HomepagePublication]:
    seen: set[tuple[str, int | None]] = set()
    deduped: list[HomepagePublication] = []
    for publication in publications:
        key = (_normalize_title_for_dedup(publication.clean_title), publication.year)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(publication)
    return deduped
