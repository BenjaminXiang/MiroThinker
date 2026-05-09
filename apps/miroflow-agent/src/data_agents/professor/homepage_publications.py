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
_NUMBERED_ITEM_START_RE = re.compile(
    r"(?:^|\s)(?:\[\d+\]|\(\d+\)|\d+[.)])\s*(?=[A-Za-z\u4e00-\u9fff])"
)
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
_JOURNAL_TAIL_HINT_RE = re.compile(
    r"\b(?:journal|transactions?|letters|proceedings?|international|advances|advanced|"
    r"trans|adv|materials|ceramics|chemistry|physics|optics|mechanics|engineering|"
    r"science|nature|cell|ieee|acm|springer|elsevier|clin|transl|med|mater|funct|"
    r"robot|biosci|bioelectronics|imaging|fluid|dynamics|research|computational|"
    r"geophysical)\b",
    re.IGNORECASE,
)
_AUTHOR_NAME_RE = re.compile(
    r"(?:"
    r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.?"
    r"|[A-Z]\.\s*[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r")(?:,\s*"
    r"(?:"
    r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.?"
    r"|[A-Z]\.\s*[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\.\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"|[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
    r"))*"
)
_TRAILING_PUNCTUATION_RE = re.compile(r"^[,;:\-.\s，；：。]+|[,;:\-.\s，；：。]+$")
_AUTHOR_MARKER_RE = re.compile(r"[*#†‡]+")
_AUTHOR_YEAR_MARKER_RE = re.compile(r"\(?\b(?:19|20)\d{2}\b\)?")
_SURNAME_INITIAL_COMMA_RE = re.compile(
    r"^[A-Z][A-Za-z-]+,\s*(?:[A-Z]\.?\s*){1,3}$"
)
_SURNAME_INITIAL_AUTHOR_RE = re.compile(
    r"\b([A-Z][A-Za-z-]+),\s*((?:[A-Z]\.\s*){1,3}|[A-Z]\.?)(?=\s*(?:,|and\b|&|$))"
)
_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_NON_HEADING_SECTION_TAG_NAMES = ("p", "div")
_GENERAL_PUBLICATIONS_HEADING_TEXTS = frozenset({"学术成果"})
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

    marked_author = _split_marked_author_prefix(normalized)
    if marked_author is not None:
        return marked_author

    author_prefixed = _split_author_prefixed_citation(normalized)
    if author_prefixed is not None:
        return author_prefixed

    leading_authors, trailing = _split_leading_authors(normalized)
    if leading_authors is not None:
        title, remainder = _split_title_and_remainder(trailing)
        _, venue = _split_remainder_authors_venue(remainder)
        return title or trailing, leading_authors, venue

    comma_delimited = _split_comma_delimited_citation(normalized)
    if comma_delimited is not None:
        return comma_delimited

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
    return _looks_like_author_list(text)


def _has_explicit_author_syntax(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    if _AUTHOR_MARKER_RE.search(text):
        return True
    if re.search(r"[,，;；]", normalized):
        return True
    if re.search(r"\b[A-Z]\.", normalized):
        return True
    if re.search(
        r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]\b",
        normalized,
    ):
        return True
    return bool(_SURNAME_INITIAL_COMMA_RE.fullmatch(normalized))


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


def _normalize_author_text(text: str) -> str:
    normalized = _clean_segment(text)
    normalized = _AUTHOR_YEAR_MARKER_RE.sub("", normalized)
    normalized = _AUTHOR_MARKER_RE.sub("", normalized)
    normalized = re.sub(r"^\s*(?:and|&)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip(" ,;")


def _normalize_surname_initial_author_order(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        surname = match.group(1)
        initials = _WHITESPACE_RE.sub(" ", match.group(2)).strip()
        return f"{initials} {surname} "

    return _SURNAME_INITIAL_AUTHOR_RE.sub(replace, text)


def _normalize_author_list(text: str) -> str:
    normalized = _normalize_author_text(text)
    normalized = _normalize_surname_initial_author_order(normalized)
    normalized = re.sub(r"\s*[;；]\s*", ", ", normalized)
    normalized = re.sub(r",\s*(?:and|&)\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+(?:and|&)\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r"(?:,\s*){2,}", ", ", normalized)
    return normalized.strip(" ,;")


def _looks_like_author_list(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    if _SURNAME_INITIAL_COMMA_RE.fullmatch(normalized):
        return True

    normalized = _normalize_surname_initial_author_order(normalized)
    normalized = re.sub(r"\s+(?:and|&)\s+", ", ", normalized, flags=re.IGNORECASE)
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:[;；,，])\s*", normalized)
        if part.strip()
    ]
    if not parts:
        return False
    return all(_looks_like_author_segment(part) for part in parts)


def _looks_like_author_segment(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized or len(normalized) > 80:
        return False
    if _looks_like_venue(normalized):
        return False
    if re.fullmatch(r"(?:[A-Z]\.\s*){1,3}[A-Z][a-z]+(?:-[A-Z][a-z]+)?", normalized):
        return True
    tokens = normalized.split()
    if (
        2 <= len(tokens) <= 7
        and all(re.fullmatch(r"(?:[A-Z]\.|[A-Za-z-]+)", token) for token in tokens)
        and len(tokens[0]) > 1
        and any(char.isupper() for char in tokens[0])
        and tokens[1][:1].isupper()
    ):
        return True
    return bool(_AUTHOR_NAME_RE.fullmatch(normalized))


def _looks_like_title_segment(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    if _looks_like_author_segment(normalized) or _looks_like_venue(normalized):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", normalized))


def _split_comma_delimited_citation(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", text)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return None

    authors: list[str] = []
    for index, segment in enumerate(segments):
        if _looks_like_author_list(segment):
            authors.append(_normalize_author_list(segment))
            continue
        if _looks_like_author_segment(segment):
            authors.append(_normalize_author_text(segment))
            continue
        leading_author, trailing = _split_leading_authors(segment)
        if leading_author is not None and authors and _looks_like_title_segment(
            trailing
        ):
            authors.append(leading_author)
            title, remainder = _split_title_and_remainder(trailing)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title or trailing, ", ".join(authors), venue
        marked_author = _split_marked_author_prefix(segment)
        if marked_author is not None and authors:
            title, marked_authors, remainder = marked_author
            if marked_authors:
                authors.append(marked_authors)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title, ", ".join(authors), venue
        if not authors or not _looks_like_title_segment(segment):
            return None
        venue = ", ".join(segments[index + 1 :]).strip(" ,;") or None
        return segment, ", ".join(authors), venue

    return None


def _split_author_prefixed_citation(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"[,，]", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_author_list(prefix):
            continue
        if _suffix_starts_with_author_continuation(suffix):
            continue

        marked_author = _split_marked_author_prefix(suffix)
        if marked_author is not None:
            title, marked_authors, venue = marked_author
            authors = _normalize_author_list(prefix)
            if marked_authors:
                authors = f"{authors}, {marked_authors}"
            return title, authors, venue

        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _split_marked_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    marker_match = _AUTHOR_MARKER_RE.search(text)
    if marker_match is None:
        return None

    raw_prefix = text[: marker_match.start()].rstrip()
    if raw_prefix.endswith((",", ";", "，", "；")):
        return None
    prefix = _clean_segment(text[: marker_match.start()])
    raw_suffix = text[marker_match.end() :].lstrip()
    if raw_suffix.startswith(("&", ",", ";", "，", "；")) or raw_suffix.casefold().startswith(
        "and "
    ):
        return None
    suffix = _clean_segment(raw_suffix)
    if not prefix or not suffix:
        return None
    if not _looks_like_author_list(prefix):
        return None

    title, remainder = _split_title_and_remainder(suffix)
    if not _looks_like_title_segment(title or suffix):
        return None
    _, venue = _split_remainder_authors_venue(remainder)
    return title or suffix, _normalize_author_list(prefix), venue


def _suffix_starts_with_author_continuation(text: str) -> bool:
    first_segment = _clean_segment(re.split(r"[,，;；]", text, maxsplit=1)[0])
    if _looks_like_author_segment(first_segment) or _looks_like_author_list(
        first_segment
    ):
        return True

    for match in re.finditer(r"\.\s+", text):
        leading = _clean_segment(text[: match.start()])
        trailing = text[match.end() :].strip()
        title, _ = _split_title_and_remainder(trailing)
        if _looks_like_author_segment(leading) and _looks_like_title_segment(
            title or trailing
        ):
            return True
        break

    leading_author, trailing = _split_leading_authors(text)
    return leading_author is not None and bool(trailing)


def _split_title_and_remainder(text: str) -> tuple[str, str]:
    for match in re.finditer(r"\.\s+", text):
        candidate_title = _clean_segment(text[: match.start()])
        remainder = text[match.end() :].strip()
        if len(candidate_title) < _MIN_TITLE_LENGTH:
            if (
                len(candidate_title) >= 5
                and remainder
                and _looks_like_authors(remainder)
            ):
                return candidate_title, remainder
            continue
        if _has_explicit_author_syntax(candidate_title) and _looks_like_authors(
            candidate_title
        ):
            continue
        if not remainder:
            return candidate_title, ""
        if (
            _looks_like_authors(remainder)
            or _looks_like_venue(remainder)
            or _looks_like_journal_tail(remainder)
        ):
            candidate_split = _split_title_venue_on_comma(
                candidate_title
            ) or _split_title_venue_on_semicolon_tail(candidate_title)
            if candidate_split is not None:
                title, venue_head = candidate_split
                venue = " ".join(part for part in (venue_head, remainder) if part)
                return title, venue
            return candidate_title, remainder

    comma_split = _split_title_venue_on_comma(text)
    if comma_split is not None:
        return comma_split

    semicolon_split = _split_title_venue_on_semicolon_tail(text)
    if semicolon_split is not None:
        return semicolon_split

    cleaned = _clean_segment(text)
    return cleaned, ""


def _split_title_venue_on_comma(text: str) -> tuple[str, str] | None:
    parts = [_clean_segment(part) for part in re.split(r"[,，]", text)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None
    for index in range(1, len(parts)):
        title = ", ".join(parts[:index]).strip(" ,;")
        remainder = ", ".join(parts[index:]).strip(" ,;")
        if len(title) < _MIN_TITLE_LENGTH:
            continue
        normalized_remainder = re.sub(
            r"^\s*in\s+", "", remainder, flags=re.IGNORECASE
        )
        if _looks_like_venue(normalized_remainder):
            return title, remainder
        if _looks_like_journal_tail(normalized_remainder):
            return title, remainder
    return None


def _split_title_venue_on_semicolon_tail(text: str) -> tuple[str, str] | None:
    parts = [_clean_segment(part) for part in re.split(r"[;；]", text)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None

    title = "; ".join(parts[:-1]).strip(" ;")
    remainder = parts[-1].strip(" ;")
    if len(title) < _MIN_TITLE_LENGTH:
        return None
    if len(remainder) <= 25 and (
        _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
    ):
        return title, remainder
    return None


def _split_remainder_authors_venue(text: str) -> tuple[str | None, str | None]:
    remainder = _normalize_sentence(text)
    if not remainder:
        return None, None

    split_points = list(re.finditer(r"\.\s+", remainder))
    for match in reversed(split_points):
        authors_candidate = _clean_segment(remainder[: match.start()])
        venue_candidate = _clean_segment(remainder[match.end() :])
        if authors_candidate and venue_candidate and (
            _looks_like_venue(venue_candidate)
            or _looks_like_journal_tail(venue_candidate)
        ):
            if _looks_like_authors(authors_candidate) and not _looks_like_journal_tail(
                authors_candidate
            ):
                return authors_candidate, venue_candidate

    cleaned = _clean_segment(remainder)
    journal_tail = _looks_like_journal_tail(cleaned)
    if journal_tail and not re.search(r"\b[A-Z]\.|[,;，；]", cleaned):
        return None, cleaned
    if _looks_like_authors(cleaned):
        return cleaned, None
    if _looks_like_venue(cleaned) or journal_tail:
        return None, cleaned
    return None, None


def _split_leading_authors(text: str) -> tuple[str | None, str]:
    for match in re.finditer(r"\.\s+", text):
        leading = _clean_segment(text[: match.start()])
        trailing = text[match.end() :].strip()
        if (
            re.search(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z]$", leading)
            and re.match(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s*[,;]", trailing)
        ):
            continue
        if _has_explicit_author_syntax(leading) and _looks_like_author_list(leading):
            return _normalize_author_list(leading), trailing
    return None, text


def _looks_like_journal_tail(text: str) -> bool:
    cleaned = _clean_segment(text)
    if not cleaned:
        return False
    head = _clean_segment(re.split(r"[,，]", cleaned, maxsplit=1)[0])
    has_citation_tail = bool(
        re.search(r"[,，]\s*(?:V\.?\s*)?\d", cleaned, re.IGNORECASE)
        or re.search(r"\b\d+\s*\([A-Za-z0-9]+\)", cleaned)
    )
    if not _JOURNAL_TAIL_HINT_RE.search(head) and not has_citation_tail:
        return False
    head = re.sub(r"\s+\d+\S*$", "", head)
    words = head.split()
    if not 1 <= len(words) <= 10:
        return False
    allowed_lower = {"and", "in", "of", "on", "for", "the", "with"}
    titleish_count = 0
    for word in words:
        token = word.strip("().:-")
        if not token:
            continue
        lowered = token.casefold()
        if lowered in allowed_lower:
            continue
        if re.fullmatch(r"[A-Z][A-Za-z&/-]*", token):
            titleish_count += 1
            continue
        return False
    return titleish_count >= 1


def _find_publications_sections(soup: BeautifulSoup) -> list[Tag]:
    sections: list[Tag] = []
    seen: set[int] = set()

    for tag in soup.find_all(_HEADING_TAG_NAMES):
        if _is_publications_heading_text(tag.get_text(" ", strip=True)):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

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

    for tag in soup.find_all(_NON_HEADING_SECTION_TAG_NAMES):
        if _is_non_heading_publications_heading(tag):
            key = id(tag)
            if key not in seen:
                seen.add(key)
                sections.append(tag)

    return _filter_publications_section_candidates(sections)


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
        for raw_text in _publication_texts_from_paragraph(paragraph):
            publication = _publication_from_text(
                raw_text=raw_text,
                source_url=page_url,
                source_anchor=_extract_source_anchor(paragraph, page_url),
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


def _publication_texts_from_paragraph(paragraph: Tag) -> list[str]:
    raw_text = _normalize_sentence(paragraph.get_text(" ", strip=True))
    if not raw_text or paragraph.find("br") is None:
        return [raw_text] if raw_text else []

    item_starts = list(_NUMBERED_ITEM_START_RE.finditer(raw_text))
    if len(item_starts) < 2:
        return [raw_text]

    items: list[str] = []
    for index, match in enumerate(item_starts):
        end = (
            item_starts[index + 1].start()
            if index + 1 < len(item_starts)
            else len(raw_text)
        )
        item_text = raw_text[match.start() : end].strip()
        if item_text:
            items.append(item_text)
    return items


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
        current_level = int(section.name[1])
        blocks = _following_section_blocks(section, current_level=current_level)
        if blocks:
            return blocks
        for parent in section.parents:
            if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
                break
            blocks = _following_section_blocks(parent, current_level=current_level)
            if blocks:
                return blocks
        return []
    if _is_non_heading_publications_heading(section):
        blocks = _following_non_heading_section_blocks(section)
        if blocks:
            return blocks
        for parent in section.parents:
            if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
                break
            if not _is_non_heading_publications_heading(parent):
                continue
            blocks = _following_non_heading_section_blocks(parent)
            if blocks:
                return blocks
        return []
    return [section]


def _following_section_blocks(section: Tag, *, current_level: int) -> list[Tag]:
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


def _following_non_heading_section_blocks(section: Tag) -> list[Tag]:
    blocks: list[Tag] = []
    for sibling in section.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if _is_non_heading_section_boundary(sibling):
            break
        blocks.append(sibling)
    return blocks


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


def _filter_publications_section_candidates(candidates: list[Tag]) -> list[Tag]:
    has_specific_candidate = any(
        _normalized_heading_candidate_text(candidate)
        not in _GENERAL_PUBLICATIONS_HEADING_TEXTS
        for candidate in candidates
    )
    if not has_specific_candidate:
        return candidates
    return [
        candidate
        for candidate in candidates
        if _normalized_heading_candidate_text(candidate)
        not in _GENERAL_PUBLICATIONS_HEADING_TEXTS
    ]


def _normalized_heading_candidate_text(tag: Tag) -> str:
    return _strip_heading_trailing_punctuation(tag.get_text(" ", strip=True))


def _is_non_heading_publications_heading(tag: Tag) -> bool:
    if tag.name in _HEADING_TAG_NAMES or tag.name not in _NON_HEADING_SECTION_TAG_NAMES:
        return False

    text = tag.get_text(" ", strip=True)
    normalized = _strip_heading_trailing_punctuation(text)
    if not normalized or not _PUBLICATIONS_HEADING_RE.fullmatch(normalized):
        return False

    return (
        _has_strong_or_b_marker(tag)
        or _has_title_class(tag)
        or len(normalized) <= 30
    )


def _is_non_heading_section_boundary(tag: Tag) -> bool:
    if tag.name in _HEADING_TAG_NAMES:
        return True
    if tag.name not in _NON_HEADING_SECTION_TAG_NAMES:
        return False

    text = tag.get_text(" ", strip=True)
    if _has_short_chinese_label_prefix(text):
        return True

    normalized = _strip_heading_trailing_punctuation(text)
    if not normalized or len(normalized) > 30 or _ITEM_PREFIX_RE.match(normalized):
        return False
    return _has_title_class(tag) or _has_strong_or_b_marker(tag)


def _has_strong_or_b_marker(tag: Tag) -> bool:
    return tag.name in {"strong", "b"} or tag.find(["strong", "b"]) is not None


def _has_title_class(tag: Tag) -> bool:
    class_values = tag.get("class", [])
    if isinstance(class_values, str):
        class_values = [class_values]
    return any(
        "tit" in str(class_value).casefold()
        or "title" in str(class_value).casefold()
        for class_value in class_values
    )


def _strip_heading_trailing_punctuation(text: str) -> str:
    return _normalize_sentence(text).strip().rstrip(":：").strip()


def _has_short_chinese_label_prefix(text: str) -> bool:
    normalized = _normalize_sentence(text).strip()
    if _ITEM_PREFIX_RE.match(normalized):
        return False
    match = re.match(r"^([^:：]{2,12})[:：]", normalized)
    if match is None:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", match.group(1)))


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
