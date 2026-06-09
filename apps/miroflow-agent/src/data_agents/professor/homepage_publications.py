from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

from src.data_agents.paper.title_cleaner import clean_paper_title
from src.data_agents.professor.homepage_publication_headings import (
    _PUBLICATIONS_HEADING_KEYWORDS,
    _PUBLICATIONS_HEADING_RE,
)

logger = logging.getLogger(__name__)

LLMPublicationExtractor = Callable[[str, str], Iterable[Mapping[str, Any]]]
_LLM_PUBLICATION_CHUNK_CHARS = 18_000

_ITEM_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[\[【]\s*\d+(?:\s+\d+)*\s*[\]】]\s*(?:[.)、．。])?"
    r"|\(\s*\d+\s*\)\s*(?:[.)、．。])?"
    r"|\d+\s*(?:[.)、．。）]|[-‐‑‒–—])"
    r"|[•‣▪◦]"
    r")\s*"
)
_NUMBERED_ITEM_START_RE = re.compile(
    r"(?:^|\s)(?:"
    r"[\[【]\s*\d+(?:\s+\d+)*\s*[\]】]\s*(?:[.)、．。])?"
    r"|\(\s*\d+\s*\)\s*(?:[.)、．。])?"
    r"|\d+\s*(?:[.)、．。]|[-‐‑‒–—])"
    r")\s*(?=[A-Za-z\u4e00-\u9fff])"
)
_ITEM_SUFFIX_RE = re.compile(r"\s*\[(?:J|C|J/OL)\]\s*\.?\s*$", re.IGNORECASE)
_LEADING_TITLE_LABEL_RE = re.compile(r"^\s*title\s*[:：]\s*", re.IGNORECASE)
_LEADING_PUBLICATION_TAG_RE = re.compile(
    r"^\s*(?:\[\s*[A-Za-z][A-Za-z0-9&/+ .-]{0,30}\s*\]\s*)+"
)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_PAGE_RANGE_RE = re.compile(
    r"\b(?:pp?|pages?)\.?\s*\d{3,5}\s*[-‐‑‒–—]\s*\d{3,5}\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_QUOTED_TITLE_RE = re.compile(r'["“](.{10,300}?)["”]|《(.{5,300}?)》')
_VENUE_KEYWORD_RE = re.compile(
    r"\b(?:transactions?|journal|proceedings?|conference|conf|symposium|workshop|letters|"
    r"neurips|icml|iclr|cvpr|eccv|aaai|acl|emnlp|naacl|kdd|www|sosp|osdi|nsdi|atc|eurosys|"
    r"sc|spaa|isca|socc|hpdc|rss|icra|corl|iros|t-?ro|prx|nature|science|optica|ofc|cleo)\b",
    re.IGNORECASE,
)
_JOURNAL_TAIL_HINT_RE = re.compile(
    r"\b(?:journal|transactions?|letters|proceedings?|international|advances|advanced|"
    r"trans|adv|materials|ceramics|chemistry|physics|optics|mechanics|engineering|"
    r"science|nature|cell|ieee|acm|springer|elsevier|clin|transl|med|mater|funct|"
    r"robot|biosci|bioelectronics|imaging|fluid|dynamics|research|computational|"
    r"commun|communications|spectrom|geophysical|systems|technology)\b",
    re.IGNORECASE,
)
_ABBREVIATED_JOURNAL_RE = re.compile(
    r"^(?:[A-Z][A-Za-z]{0,8}\.\s*){2,}[A-Z][A-Za-z]{1,16}\.?$"
)
_INLINE_VENUE_START_RE = re.compile(
    r"\s+(?=(?:(?:american|asian|british|canadian|chinese|european|international)"
    r"\s+)?(?:journal|proceedings|ieee|acm|acs|nature|science|elsevier|springer)\b)",
    re.IGNORECASE,
)
_INLINE_PERIOD_VENUE_RE = re.compile(
    r"\.\s*(?=(?:(?:\d+(?:st|nd|rd|th)\s+)?(?:international|national)\s+"
    r"(?:conference|journal)|IFAC-PapersOnLine|journal|proceedings|ieee|acm|"
    r"acs|nature|science|elsevier|springer)\b)",
    re.IGNORECASE,
)
_IN_PROC_TAIL_RE = re.compile(r",\s*\[in\]\s*proc\.?\s+", re.IGNORECASE)
_PROC_TAIL_RE = re.compile(r",\s*proc\.?\s+", re.IGNORECASE)
_VENUE_RANK_TAIL_PATTERN = (
    r"(?:\s*[,，]?\s*(?:"
    r"[\(（]\s*CCF\s+[ABC]\s*[\)）]"
    r"|CCF\s+[ABC]"
    r"|[\(（]?\s*清华\s*CS\s*[,，]?\s*[ABC]\s*[\)）]?"
    r"))*"
)
_COMPACT_VENUE_YEAR_PATTERN = (
    r"(?:"
    r"[A-Z][A-Z0-9/&.-]{1,12}(?:\s+[A-Z][A-Z0-9/&.-]{1,12}){0,2}"
    r"|NeurIPS"
    r")\s*(?:19|20)\d{2}"
    rf"{_VENUE_RANK_TAIL_PATTERN}"
)
_COMPACT_VENUE_YEAR_RE = re.compile(
    rf"^{_COMPACT_VENUE_YEAR_PATTERN}$"
)
_SHORT_COMPACT_VENUE_YEAR_RE = re.compile(
    r"^(?:[A-Z][A-Z0-9/&.-]{1,12}|NeurIPS)[- ]\d{2}$"
)
_TRAILING_COMPACT_VENUE_YEAR_RE = re.compile(
    r"^(?P<title>.+?)\s+"
    rf"(?P<venue>{_COMPACT_VENUE_YEAR_PATTERN})$"
)
_CITATION_TYPE_VENUE_TAIL_RE = re.compile(
    r"^(?P<title>.+?)\s*\[\s*(?:C|J|J/OL)\s*\]\s*"
    r"(?://|/|\.)?\s*(?P<venue>.+)$",
    re.IGNORECASE,
)
_RESIDUAL_CITATION_MARKER_RE = re.compile(
    r"\[\s*(?:C|J|J/OL)\s*\]\s*(?://|/|\.|$)|\bCCF\s+[ABC]\b",
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
_TRAILING_PUNCTUATION_RE = re.compile(
    r"^[,;:\-.\"'“”‘’\s，；：。]+|[,;:\-.\"'“”‘’\s，；：。]+$"
)
_AUTHOR_MARKER_RE = re.compile(r"[*#†‡]+")
_LEADING_MARKER_SEPARATOR_RE = re.compile(r"^\s*[*#†‡]+\s*[,，;；]")
_LEADING_INITIAL_SEPARATOR_FRAGMENT_RE = re.compile(
    r"^\s*(?:[A-Z]\.?\s*){1,4}[*#†‡]*\s*[,，;；]"
)
_LEADING_SPACED_SURNAME_INITIAL_FRAGMENT_RE = re.compile(
    r"^\s*[A-Z][a-z]{0,3}\s+[a-z]{2,}\s*,\s*(?:[A-Z]\.?\s*){1,4}\s*(?:[,，;；]|$)"
)
_LEADING_WOS_AUTHOR_ALIAS_FRAGMENT_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’-]+\s+[A-Z]{1,4}\s*\([^)]+\)\s*,\s*"
    r"(?:[A-Z][A-Za-z'’-]+\s+[A-Z]{1,4}\s*\([^)]+\)\s*,\s*)+"
)
_LEADING_FULL_NAME_MARKER_COMMA_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’.-]+(?:-[A-Z][A-Za-z'’.-]+)?"
    r"(?:\s+[A-Z][A-Za-z'’.-]+(?:-[A-Z][A-Za-z'’.-]+)?){1,3}"
    r"\s*[*#†‡]+\s*[,，]"
)
_SURNAME_INITIAL_AUTHOR_SEGMENT_PATTERN = (
    r"(?:[a-z][a-z'’.-]+(?:\s+[a-z][a-z'’.-]+){0,2}\s+)?"
    r"[A-Z][A-Za-z'’.-]*\s*,\s*(?:[A-Z]\.?\s*){1,4}[*#†‡]*"
)
_LEADING_AUTHOR_CHAIN_COLON_RE = re.compile(
    rf"^\s*{_SURNAME_INITIAL_AUTHOR_SEGMENT_PATTERN}"
    rf"(?:\s*[,，]\s*(?:and\s+)?{_SURNAME_INITIAL_AUTHOR_SEGMENT_PATTERN})+"
    r"\s*[:：]"
)
_CONTRIBUTION_NOTE_RE = re.compile(
    r"\b(?:equally\s+contributed|co-?first\s+author|corresponding\s+author)\b",
    re.IGNORECASE,
)
_CHINESE_AUTHOR_MARKER_NOTE_RE = re.compile(r"(?:共同第一作者|通讯作者|通信作者)")
_AUTHOR_YEAR_MARKER_RE = re.compile(r"\(?\b(?:19|20)\d{2}\b\)?")
_AUTHOR_YEAR_TITLE_PREFIX_RE = re.compile(
    r"^\s*(?:[A-Z]\.\s*){1,4}\s*[*#†‡]*\s*"
    r"\(?\b(?:19|20)\d{2}\b\)?(?:\s*[.)]\s+|\s*$)"
)
_AUTHOR_NOTE_RE = re.compile(
    r"\s*[（(]\s*(?:通讯作者|通信作者|共同通讯作者|第一作者|共同第一作者|"
    r"corresponding\s+authors?|co-?first\s+authors?|equal\s+contribution)\s*[）)]",
    re.IGNORECASE,
)
_AUTHOR_NOTE_ONLY_RE = re.compile(
    r"^[（(][^）)]*(?:第一|共同|通讯|通信|作者|corresponding|contribution)[^）)]*[）)]$",
    re.IGNORECASE,
)
_ET_AL_SUFFIX_RE = re.compile(
    r"\s+et\s+a(?:l\.?|[;/]+)\s*/?$", re.IGNORECASE
)
_ET_AL_PREFIX_RE = re.compile(
    r"^(?P<prefix>.+?)\s*,?\s*et\s+a(?:l\.?|[;/]+)\s*"
    r"(?:[/.\-–—,，]\s*|\s+)"
    r"(?P<suffix>.+)$",
    re.IGNORECASE,
)
_INITIAL_CLUSTER_PATTERN = r"(?:[A-Z]\.?(?:-[A-Z]\.?)?\s*){1,4}"
_CONNECTIVE_AUTHOR_PATTERN = (
    rf"[A-Z][A-Za-z'’-]+(?:\s+and\s+"
    rf"(?:(?:{_INITIAL_CLUSTER_PATTERN})?[A-Z][A-Za-z'’-]+|{_INITIAL_CLUSTER_PATTERN}))+"
)
_CONNECTIVE_AUTHOR_YEAR_PREFIX_RE = re.compile(
    rf"^\s*{_CONNECTIVE_AUTHOR_PATTERN}\s*"
    r"\(?\b(?:19|20)\d{2}\b\)?\s*[,.)]",
)
_CONNECTIVE_AUTHOR_ONLY_RE = re.compile(rf"^\s*{_CONNECTIVE_AUTHOR_PATTERN}\s*$")
_SURNAME_INITIAL_COMMA_RE = re.compile(
    rf"^[A-Z][A-Za-z'’-]+,\s*{_INITIAL_CLUSTER_PATTERN}$"
)
_SURNAME_GIVEN_AUTHOR_RE = re.compile(
    r"^([^\W\d_][\w'’.-]*),\s*"
    rf"((?:[^\W\d_][\w'’.-]*|{_INITIAL_CLUSTER_PATTERN})"
    rf"(?:\s+(?:[^\W\d_][\w'’.-]*|{_INITIAL_CLUSTER_PATTERN})){{0,3}})$"
)
_SURNAME_INITIAL_AUTHOR_RE = re.compile(
    rf"\b([^\W\d_][\w'’.-]*),\s*({_INITIAL_CLUSTER_PATTERN})"
    r"(?=\s*(?:,|;|and\b|&|$))"
)
_NAME_TOKEN_PATTERN = r"[^\W\d_][\w'’.-]*"
_INITIAL_PREFIXED_AUTHOR_RE = re.compile(
    rf"^(?:[A-Z]\.\s*[-‐‑‒–—]\s*)?(?:[A-Z]\.\s*){{1,4}}"
    rf"{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,3}}$",
    re.UNICODE,
)
_AUTHOR_CORRESPONDENCE_TAIL_RE = re.compile(
    r"\s+Author\s+for\s+correspondence\s*:?\s*(?P<venue>.+)$",
    re.IGNORECASE,
)
_PUBLICATION_STATUS_TAIL_RE = re.compile(
    r"^(?:in\s+press|accepted|to\s+appear)$",
    re.IGNORECASE,
)
_IF_CITATIONS_METADATA_RE = re.compile(
    r"\bIF\s*/\s*citations?\s*:",
    re.IGNORECASE,
)
_LEADING_YEAR_MARKER_RE = re.compile(
    r"^\s*[\(（]?\s*(?:19|20)\d{2}\s*[\)）]?\s*[,，.]?\s*"
)
_URL_ONLY_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_EXTERNAL_POINTER_RE = re.compile(
    r"(?:^|[\s,，;；:：。])(?:请见|详见|参见|具体发表(?:情况)?详见|"
    r"see\b|refer(?:\s+to)?\b|for\s+details\b)",
    re.IGNORECASE,
)
_INDEX_ONLY_RE = re.compile(
    r"^(?:"
    r"wos|web\s+of\s+science|ei(?:\s+accession\s+number)?|scopus|"
    r"pubmed|pmid|doi"
    r")\s*[:：]?\s*[\w./:-]+$",
    re.IGNORECASE,
)
_INDEX_METADATA_IN_TEXT_RE = re.compile(
    r"\b(?:wos|web\s+of\s+science|ei\s+accession\s+number|scopus|pubmed|pmid)"
    r"\s*[:：]",
    re.IGNORECASE,
)
_MOJIBAKE_RE = re.compile(r"(?:�|Ã.|Â.|â[€€™“”])")
_URL_IN_TEXT_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_SPLIT_INTERNAL_DIACRITIC_LETTER_RE = re.compile(
    r"(?<=[A-Za-z])\s+([^\W\d_A-Za-z])\s+(?=[a-z])",
    re.UNICODE,
)
_SPLIT_TRAILING_DIACRITIC_LETTER_RE = re.compile(
    r"(?<=[A-Za-z])\s+([^\W\d_A-Za-z])(?=\s+(?:[A-Z][A-Za-z]|[,;，；.]|$))",
    re.UNICODE,
)
_LEADING_SURNAME_INITIAL_FRAGMENT_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]\.\s*){1,4}"
    r"(?:and\s+[A-Z][A-Za-z'’.-]+)?(?:,|$|\s+and\b)"
    r"|[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]{1,3}\s*,\s*){1,}"
    r")"
)
_LEADING_SURNAME_INITIAL_MARKER_COMMA_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’.-]+,\s*(?:[A-Z]\.?\s*){1,4}"
    r"[*#†‡]+\s*[,，]"
)
_LEADING_INITIAL_COMMA_FRAGMENT_RE = re.compile(r"^(?:[A-Z]\.?\s*){1,4},\s+")
_LEADING_AUTHOR_DOT_TITLE_RE = re.compile(
    r"^[A-Z][A-Za-z'’.-]+\s+(?:[A-Z]\.?\s*){0,3}[A-Z][A-Za-z'’.-]*\.\s+"
)
_NON_PUBLICATION_PROSE_RE = re.compile(
    r"(?:发表\s*(?:sci|ei)?\s*(?:收录)?\s*论文|论文\s*\d+\s*多?篇|"
    r"授权\s*专利|申请\s*专利|被引|影响因子|"
    r"\b(?:selected\s+publications?|selected\s+publication|"
    r"published\s+more\s+than\s+\d+\s+papers?|"
    r"papers?\s+have\s+been\s+cited|h\s+index|google\s+scholar)\b)",
    re.IGNORECASE,
)
_TRAILING_ABBREVIATED_VENUE_TOKEN_RE = re.compile(
    r"\s+(?:Adv|ACS\s+Appl|Chem|Mater|Funct|Today|Catal)\.?\s*$",
    re.IGNORECASE,
)
_COMMON_ROMANIZED_CHINESE_SURNAMES = frozenset(
    {
        "bai",
        "cao",
        "chen",
        "cheng",
        "cui",
        "dai",
        "deng",
        "ding",
        "du",
        "duan",
        "fan",
        "fang",
        "feng",
        "fu",
        "gao",
        "gu",
        "guan",
        "guo",
        "han",
        "hao",
        "he",
        "hong",
        "hou",
        "hu",
        "huang",
        "jia",
        "jiang",
        "kang",
        "lai",
        "lau",
        "lei",
        "li",
        "liang",
        "liao",
        "lin",
        "liu",
        "lu",
        "luo",
        "lyu",
        "ma",
        "mi",
        "ouyang",
        "pan",
        "peng",
        "qian",
        "qiao",
        "qin",
        "qiu",
        "ren",
        "shen",
        "song",
        "su",
        "sui",
        "sun",
        "tan",
        "tang",
        "tian",
        "wan",
        "wang",
        "wei",
        "wen",
        "wu",
        "xia",
        "xie",
        "xin",
        "xu",
        "xue",
        "yan",
        "yang",
        "ye",
        "yin",
        "yu",
        "yuan",
        "zeng",
        "zhang",
        "zhao",
        "zheng",
        "zhong",
        "zhou",
        "zhu",
        "zong",
    }
)
_COMMON_SPACED_AUTHOR_TOKEN_REPAIRS = frozenset(
    {
        "bowen",
        "chen",
        "jia",
        "li",
        "mi",
        "paek",
        "shu",
        "tao",
        "xi",
        "xiaojun",
        "yang",
        "xingwei",
    }
)
_COMMON_SPLIT_TITLE_WORD_REPAIRS = frozenset(
    {
        "bottles",
        "old",
        "wine",
    }
)
_CHINESE_AUTHOR_SEGMENT_RE = re.compile(
    r"^[\u4e00-\u9fff](?:\s*[\u4e00-\u9fff]){1,3}\s*[*#†‡]?$"
)
_CHINESE_VENUE_HINT_RE = re.compile(
    r"(?:学报|期刊|杂志|会议|评论|报|刊|给水排水)"
)
_CONCATENATED_AUTHOR_NAME_RE = re.compile(r"^[A-Z][a-z]{1,24}[A-Z][a-z]{1,24}$")
_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_NON_HEADING_SECTION_TAG_NAMES = ("p", "div")
_GENERAL_PUBLICATIONS_HEADING_TEXTS = frozenset({"学术成果"})
_LANDMARK_TAGS = ("header", "footer", "nav", "aside")
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
    pdf_url: str | None = None


LLM_PUBLICATION_EXTRACTION_SYSTEM_PROMPT = (
    "You extract publication citations from official professor profile pages. "
    "Use only the provided publication-section text. Return strict JSON only. "
    "Do not invent papers, abstracts, authors, venues, years, DOIs, or URLs."
)


def _strip_item_prefix(text: str) -> str:
    return _ITEM_PREFIX_RE.sub("", text).strip()


def _strip_leading_publication_tags(text: str) -> str:
    stripped = text.strip()
    while True:
        match = _LEADING_PUBLICATION_TAG_RE.match(stripped)
        if match is None:
            return stripped
        suffix = stripped[match.end() :].lstrip()
        if not _starts_with_authorish_segment(suffix):
            return stripped
        stripped = suffix


def _starts_with_authorish_segment(text: str) -> bool:
    first_segment = _clean_segment(re.split(r"[,，;；.。]", text, maxsplit=1)[0])
    return bool(
        first_segment
        and (
            _looks_like_author_segment(first_segment)
            or _looks_like_author_list(first_segment)
        )
    )


def _strip_item_suffix(text: str) -> str:
    stripped = _ITEM_SUFFIX_RE.sub("", text)
    return stripped.rstrip(" .,;:")


def _strip_leading_title_label(text: str) -> str:
    return _LEADING_TITLE_LABEL_RE.sub("", text).strip()


def _extract_year_from_text(text: str) -> int | None:
    current_year = datetime.now().year
    text = _PAGE_RANGE_RE.sub(" ", text)
    years = [
        int(match.group(0))
        for match in _YEAR_RE.finditer(text)
        if 1900 <= int(match.group(0)) <= current_year + 1
    ]
    if not years:
        return None
    return max(years)


def _split_title_authors_venue(text: str) -> tuple[str, str | None, str | None]:
    normalized = _strip_leading_title_label(
        _normalize_sentence(
            _strip_leading_publication_tags(_strip_item_prefix(text))
        )
    )
    if not normalized:
        return "", None, None

    surname_given_year_quoted = _split_surname_given_year_quoted_title_prefix(
        normalized
    )
    if surname_given_year_quoted is not None:
        return surname_given_year_quoted

    and_surname_given_authors = _split_and_surname_given_author_prefix(normalized)
    if and_surname_given_authors is not None:
        return and_surname_given_authors

    chinese_author_prefix = _split_chinese_author_prefixed_citation(normalized)
    if chinese_author_prefix is not None:
        return chinese_author_prefix

    chinese_comma_title = _split_chinese_comma_title_venue(normalized)
    if chinese_comma_title is not None:
        return chinese_comma_title

    quoted = _extract_quoted_title_segment(normalized)
    if quoted is not None:
        return quoted

    unclosed_quote_author_prefix = _split_unclosed_quote_author_prefix(normalized)
    if unclosed_quote_author_prefix is not None:
        return unclosed_quote_author_prefix

    if _IF_CITATIONS_METADATA_RE.search(normalized):
        comma_delimited = _split_comma_delimited_citation(normalized)
        if (
            comma_delimited is not None
            and not _title_result_needs_author_prefix_fallback(comma_delimited[0])
            and not _is_non_publication_title_noise(comma_delimited[0])
        ):
            return comma_delimited

    author_year_prefix = _split_author_year_prefix(normalized)
    if author_year_prefix is not None:
        return author_year_prefix

    et_al_prefix = _split_et_al_author_prefix(normalized)
    if et_al_prefix is not None:
        return et_al_prefix

    marked_author = _split_marked_author_prefix(normalized)
    if marked_author is not None:
        if (
            _title_has_author_prefix_contamination(marked_author[0])
            or _is_dense_initial_author_fragment_title(marked_author[0])
            or _is_non_publication_title_noise(marked_author[0])
        ):
            comma_delimited = _split_comma_delimited_citation(normalized)
            if comma_delimited is not None and not _title_has_author_prefix_contamination(
                comma_delimited[0]
            ):
                return comma_delimited
        return marked_author

    semicolon_surname_authors = _split_semicolon_surname_author_prefix(normalized)
    if semicolon_surname_authors is not None:
        return semicolon_surname_authors

    semicolon_period_authors = _split_semicolon_surname_author_period_prefix(
        normalized
    )
    if semicolon_period_authors is not None:
        return semicolon_period_authors

    semicolon_author_title = _split_semicolon_author_title_prefix(normalized)
    if semicolon_author_title is not None:
        return semicolon_author_title

    semicolon_plain_authors = _split_semicolon_plain_author_prefix(normalized)
    if semicolon_plain_authors is not None:
        return semicolon_plain_authors

    comma_surname_authors = _split_comma_surname_author_prefix(normalized)
    if comma_surname_authors is not None:
        return comma_surname_authors

    comma_surname_given_pair_authors = (
        _split_comma_author_prefix_with_surname_given_pairs(normalized)
    )
    if comma_surname_given_pair_authors is not None:
        return comma_surname_given_pair_authors

    author_prefix_before_acronym = _split_author_prefix_before_acronym_title(
        normalized
    )
    if author_prefix_before_acronym is not None:
        return author_prefix_before_acronym

    connective_author_prefix = _split_connective_author_comma_prefix(normalized)
    if connective_author_prefix is not None:
        return connective_author_prefix

    comma_delimited = _split_comma_delimited_citation(normalized)
    if comma_delimited is not None:
        if _title_result_needs_author_prefix_fallback(
            comma_delimited[0]
        ) or _is_standalone_person_name_title(comma_delimited[0]):
            author_prefixed = _split_author_prefixed_citation(normalized)
            if (
                author_prefixed is not None
                and not _title_result_needs_author_prefix_fallback(
                    author_prefixed[0]
                )
            ):
                return author_prefixed
            repaired = _repair_contaminated_title_result(comma_delimited)
            if repaired is not None:
                return repaired
        return comma_delimited

    leading_authors, trailing = _split_leading_authors(normalized)
    if leading_authors is not None:
        title, remainder = _split_title_and_remainder(trailing)
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return title or trailing, leading_authors, venue

    author_prefixed = _split_author_prefixed_citation(normalized)
    if author_prefixed is not None:
        return author_prefixed

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

    if sections and len(deduped) < 3:
        logger.warning(
            "Detected publications section on %s but extracted only %s items",
            page_url,
            len(deduped),
        )

    return deduped


def extract_publications_from_html_with_llm_fallback(
    html: str,
    *,
    page_url: str,
    llm_extractor: LLMPublicationExtractor | None,
    author_filter: Callable[[str | None], bool] | None = None,
    force_llm: bool = False,
    min_confidence: float = 0.75,
    llm_chunk_chars: int = _LLM_PUBLICATION_CHUNK_CHARS,
) -> list[HomepagePublication]:
    """Extract official publications with optional source-grounded LLM fallback.

    Rules remain the fast path and section locator. The LLM is only allowed to
    structure text from the detected publication section; every accepted field
    must be grounded in the returned source span.
    """
    rule_publications = extract_publications_from_html(
        html,
        page_url=page_url,
        author_filter=author_filter,
    )
    if llm_extractor is None:
        return rule_publications

    section_text = _extract_publication_sections_text(html)
    if not section_text:
        return rule_publications

    should_use_fallback = force_llm or _should_use_llm_publication_fallback(
        publications=rule_publications,
        section_text=section_text,
    )
    if not should_use_fallback:
        return rule_publications

    try:
        raw_items = [
            item
            for chunk in _chunk_publication_section_text(
                section_text,
                max_chars=llm_chunk_chars,
            )
            for item in llm_extractor(chunk, page_url)
        ]
    except Exception as exc:  # noqa: BLE001 - extraction fallback must not crash ingest
        logger.warning("LLM publication extraction failed for %s: %s", page_url, exc)
        if should_use_fallback:
            return _filter_suspicious_rule_publications(rule_publications)
        return rule_publications

    llm_publications = [
        publication
        for item in raw_items
        if (
            publication := _publication_from_llm_item(
                item,
                section_text=section_text,
                page_url=page_url,
                author_filter=author_filter,
                min_confidence=min_confidence,
            )
        )
        is not None
    ]
    if llm_publications:
        return _dedupe_publications(
            [
                *_filter_suspicious_rule_publications(rule_publications),
                *llm_publications,
            ]
        )

    if should_use_fallback:
        return _filter_suspicious_rule_publications(rule_publications)
    return rule_publications


def build_llm_publication_extraction_messages(
    *,
    section_text: str,
    page_url: str,
) -> list[dict[str, str]]:
    schema = {
        "items": [
            {
                "title": "paper title exactly as written in the citation",
                "authors_text": "authors exactly as written, or null",
                "venue_text": "journal/conference/book venue exactly as written, or null",
                "year": 2025,
                "doi": "doi string from the citation, or null",
                "source_span": "the full citation text copied from the input",
                "confidence": 0.95,
            }
        ]
    }
    user_prompt = "\n".join(
        [
            f"Page URL: {page_url}",
            "",
            "Extract every publication citation from the official publication-section text.",
            "Rules:",
            "- Output strict JSON with top-level key `items`.",
            "- The title is the primary lookup key for later paper search.",
            "- Authors may appear in many formats; use them as `authors_text`, "
            "never return an author list as `title`.",
            "- For author-first references, extract the paper title after the "
            "author block and before the venue/year metadata.",
            "- `source_span` must be copied from the input and contain the citation.",
            "- `title`, `authors_text`, `venue_text`, `year`, and `doi` must come from `source_span`.",
            "- Use confidence >= 0.9 for exact source-grounded citation extraction; "
            "use confidence < 0.75 only when the citation fields are uncertain.",
            "- Do not output biographies, section headings, project descriptions, patents, awards, or URLs alone.",
            "- Do not translate titles or authors.",
            "- If no publication citations are present, return {\"items\": []}.",
            "",
            "Expected JSON shape:",
            json.dumps(schema, ensure_ascii=False),
            "",
            "Publication-section text:",
            section_text,
        ]
    )
    return [
        {"role": "system", "content": LLM_PUBLICATION_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def parse_llm_publication_extraction_response(raw_text: str) -> list[Mapping[str, Any]]:
    payload = _extract_llm_json_payload(raw_text)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _extract_publication_sections_text(html: str) -> str:
    if not html.strip():
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag_name in _LANDMARK_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    sections = _find_publications_sections(soup)
    texts: list[str] = []
    seen_texts: set[str] = set()
    for section in sections:
        section_heading_text = _normalize_sentence(section.get_text(" ", strip=True))
        if section_heading_text and section_heading_text not in seen_texts:
            texts.append(section_heading_text)
            seen_texts.add(section_heading_text)

        for block in _section_root_blocks(section):
            block_text = _normalize_sentence(block.get_text(" ", strip=True))
            if block_text and block_text not in seen_texts:
                texts.append(block_text)
                seen_texts.add(block_text)
    return "\n".join(texts)


def _chunk_publication_section_text(
    section_text: str,
    *,
    max_chars: int,
) -> list[str]:
    """Chunk long publication sections without imposing an item count cap."""
    normalized = section_text.strip()
    if not normalized:
        return []
    if max_chars <= 0 or len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if line_len > max_chars:
            chunks.append(line)
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def _publication_from_llm_item(
    item: Mapping[str, Any],
    *,
    section_text: str,
    page_url: str,
    author_filter: Callable[[str | None], bool] | None,
    min_confidence: float,
) -> HomepagePublication | None:
    confidence = _coerce_float(item.get("confidence"))
    if confidence is not None and confidence < min_confidence:
        return None

    authors_text = _optional_llm_text(item.get("authors_text"))
    source_span = _normalize_sentence(str(item.get("source_span") or ""))
    raw_title = _clean_segment(str(item.get("title") or ""))
    title = _clean_publication_title_segment(raw_title, authors_text=authors_text)
    venue_text = _optional_llm_text(item.get("venue_text"))
    doi = _optional_llm_text(item.get("doi"))
    year = _validate_year(_coerce_int(item.get("year")))

    if len(title) < _MIN_TITLE_LENGTH or not source_span:
        return None
    if not _normalized_contains(section_text, source_span):
        return None
    if not (
        _normalized_contains(source_span, raw_title)
        or _normalized_contains(source_span, title)
    ):
        return None
    if authors_text and not _normalized_contains_author_text(
        source_span,
        authors_text,
    ):
        return None
    if venue_text and not _normalized_contains(source_span, venue_text):
        return None
    if year is not None and str(year) not in source_span:
        return None
    if doi and not _normalized_contains(source_span, doi):
        return None
    if author_filter is not None and not author_filter(authors_text):
        return None

    publication = HomepagePublication(
        raw_title=source_span,
        clean_title=title,
        authors_text=authors_text,
        venue_text=venue_text,
        year=year,
        source_url=page_url,
        source_anchor=f"https://doi.org/{doi}" if doi else None,
        pdf_url=None,
    )
    if _is_suspicious_rule_publication(publication):
        return None
    return publication


def _extract_llm_json_payload(raw_text: str) -> Any:
    cleaned = _strip_markdown_fences(raw_text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _strip_markdown_fences(text: str) -> str:
    return re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", text, flags=re.MULTILINE).strip()


def _optional_llm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _clean_segment(str(value))
    if not text or text.lower() == "null":
        return None
    return text


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_contains(haystack: str, needle: str) -> bool:
    normalized_haystack = _normalize_for_grounding(haystack)
    normalized_needle = _normalize_for_grounding(needle)
    return bool(normalized_needle and normalized_needle in normalized_haystack)


def _normalized_contains_author_text(haystack: str, needle: str) -> bool:
    if _normalized_contains(haystack, needle):
        return True
    normalized_haystack = _normalize_for_author_grounding(haystack)
    normalized_needle = _normalize_for_author_grounding(needle)
    return bool(normalized_needle and normalized_needle in normalized_haystack)


def _normalize_for_grounding(text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", str(text)).strip().casefold()
    normalized = re.sub(r"\s+([,.;:，；：。])", r"\1", normalized)
    normalized = re.sub(r"([,.;:，；：。])\s+", r"\1 ", normalized)
    return normalized


def _normalize_for_author_grounding(text: str) -> str:
    normalized = str(text).replace("…", " ")
    normalized = _AUTHOR_MARKER_RE.sub(" ", normalized)
    normalized = re.sub(r"\bet\s+al\.?", " ", normalized, flags=re.IGNORECASE)
    normalized = _normalize_for_grounding(normalized)
    return re.sub(r"\s+", " ", normalized).strip(" ,;，；")


def _should_use_llm_publication_fallback(
    *,
    publications: list[HomepagePublication],
    section_text: str,
) -> bool:
    if any(_is_suspicious_rule_publication(publication) for publication in publications):
        return True
    if len(publications) >= 3:
        return False
    return _publication_section_has_citation_signal(section_text)


def _publication_section_has_citation_signal(section_text: str) -> bool:
    if len(section_text.strip()) < 80:
        return False
    year_count = len(_YEAR_RE.findall(section_text))
    if year_count >= 2:
        return True
    return bool(
        re.search(
            r"\b(?:doi|journal|proceedings|conference|ieee|acm|springer|elsevier|"
            r"nature|science|optics|materials|letters|commun|transactions?)\b",
            section_text,
            flags=re.IGNORECASE,
        )
    )


def _filter_suspicious_rule_publications(
    publications: list[HomepagePublication],
) -> list[HomepagePublication]:
    return [
        publication
        for publication in publications
        if not _is_suspicious_rule_publication(publication)
    ]


def _is_suspicious_rule_publication(publication: HomepagePublication) -> bool:
    title = str(publication.clean_title or "").strip()
    if not title:
        return True
    if _is_non_publication_title_noise(title):
        return True
    if _title_has_author_prefix_contamination(title):
        return True
    if (
        publication.authors_text is None
        and _title_has_author_suffix_contamination(title)
    ):
        return True
    if re.search(r"^\s*(?:et\s+a[;/l]?|and\b|&\b)", title, re.IGNORECASE):
        return True
    if re.search(r"\bet\s+a[;/l]?\b", title, re.IGNORECASE):
        return True
    if _has_explicit_author_syntax(title) and _looks_like_author_list(title):
        return publication.authors_text is None or _has_strong_author_fragment_evidence(
            title
        )
    if (
        publication.authors_text is None
        and _has_explicit_author_syntax(title)
        and (
            re.search(r"^[A-Z][A-Za-z'’-]+,\s*(?:[A-Z]\.?\s*){1,4}", title)
            or ";" in title
            or "；" in title
        )
    ):
        return True
    return False


def _title_has_author_suffix_contamination(title: str) -> bool:
    has_author_marker = _AUTHOR_MARKER_RE.search(title) is not None
    normalized = _normalize_author_text(title)
    if not normalized or ("," not in normalized and "，" not in normalized):
        return False

    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", normalized)
        if _clean_segment(part)
    ]
    if len(parts) < 3:
        return False

    authorish_tail_count = 0
    skipped_venue_tail = False
    for part in reversed(parts):
        candidate = _strip_trailing_abbreviated_venue_token(part)
        if _looks_like_author_segment(candidate) or _looks_like_author_list(candidate):
            authorish_tail_count += 1
            continue
        if not skipped_venue_tail and _looks_like_abbreviated_venue_fragment(part):
            skipped_venue_tail = True
            continue
        break
    return authorish_tail_count >= (2 if has_author_marker else 3)


def _strip_trailing_abbreviated_venue_token(text: str) -> str:
    markerless = _AUTHOR_MARKER_RE.sub("", _clean_segment(text))
    return _clean_segment(_TRAILING_ABBREVIATED_VENUE_TOKEN_RE.sub("", markerless))


def _looks_like_abbreviated_venue_fragment(text: str) -> bool:
    normalized = _clean_segment(text)
    if not normalized:
        return False
    return bool(
        re.fullmatch(
            r"(?:Adv|ACS\s+Appl|Chem|Mater|Funct|Today|Catal)\.?",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _is_non_publication_title_noise(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized:
        return True
    if _URL_ONLY_RE.fullmatch(normalized):
        return True
    if _URL_IN_TEXT_RE.search(normalized):
        return True
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", normalized):
        return True
    if _EXTERNAL_POINTER_RE.search(normalized) and re.search(
        r"https?://|www\.", normalized, re.IGNORECASE
    ):
        return True
    if _INDEX_ONLY_RE.fullmatch(normalized):
        return True
    if _INDEX_METADATA_IN_TEXT_RE.search(normalized):
        return True
    if _MOJIBAKE_RE.search(normalized):
        return True
    if _CONTRIBUTION_NOTE_RE.search(normalized):
        return True
    if _CHINESE_AUTHOR_MARKER_NOTE_RE.search(normalized):
        return True
    if _looks_like_chinese_author_list_only(normalized):
        return True
    if _looks_like_research_topic_heading(normalized):
        return True
    if _IF_CITATIONS_METADATA_RE.search(normalized):
        return True
    if _RESIDUAL_CITATION_MARKER_RE.search(normalized):
        return True
    if _looks_like_author_venue_year_only_title(normalized):
        return True
    if _NON_PUBLICATION_PROSE_RE.search(normalized):
        return True
    return _is_standalone_person_name_title(normalized)


def _looks_like_author_venue_year_only_title(title: str) -> bool:
    normalized = _clean_segment(title)
    if _YEAR_RE.search(normalized) is None:
        return False
    match = re.match(
        r"^(?P<author>(?:[A-Z]\.?\s*)?[A-Z][A-Za-z'’.-]+)"
        r"\s*[*#†‡.]*\s+(?P<tail>.+)$",
        normalized,
    )
    if match is None:
        return False
    author_candidate = _clean_segment(match.group("author"))
    tail = _clean_segment(match.group("tail"))
    if not _looks_like_author_segment(author_candidate):
        return False
    return _looks_like_venue(tail) or _looks_like_journal_tail(tail)


def _looks_like_chinese_author_list_only(title: str) -> bool:
    normalized = _clean_segment(title)
    if "," not in normalized and "，" not in normalized:
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", normalized)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False
    return all(_looks_like_chinese_author_name_part(part) for part in parts)


def _looks_like_research_topic_heading(title: str) -> bool:
    normalized = _clean_segment(title)
    return bool(
        "/" in normalized
        and _YEAR_RE.search(normalized) is None
        and re.search(r"[\u4e00-\u9fff]", normalized)
        and not re.search(r"[.。?？]", normalized)
    )


def _looks_like_chinese_author_name_part(text: str) -> bool:
    markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", text))
    if not markerless:
        return False
    return bool(
        re.fullmatch(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]{1,3}", markerless)
        or re.fullmatch(r"[\u4e00-\u9fff]{2,4}", markerless)
    )


def _is_standalone_person_name_title(title: str) -> bool:
    normalized = _normalize_author_text(title)
    if not normalized or len(normalized) > 60:
        return False
    if _looks_like_venue(normalized) or _looks_like_journal_tail(normalized):
        return False
    if not _looks_like_author_segment(normalized):
        return False
    if re.search(r"[:?？]", normalized):
        return False

    words = [
        word.strip("()[]{}")
        for word in re.split(r"\s+", normalized)
        if word.strip("()[]{}")
    ]
    if not 2 <= len(words) <= 4:
        return False

    last_word = re.sub(r"[^A-Za-z'-]", "", words[-1]).casefold()
    if last_word in _COMMON_ROMANIZED_CHINESE_SURNAMES:
        return True
    return bool(re.search(r"\b[A-Z]\.", normalized))


def _title_has_author_prefix_contamination(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized:
        return False
    if _LEADING_MARKER_SEPARATOR_RE.search(normalized):
        return True
    if _LEADING_INITIAL_SEPARATOR_FRAGMENT_RE.search(normalized):
        return True
    if _LEADING_SPACED_SURNAME_INITIAL_FRAGMENT_RE.search(normalized):
        return True
    if _LEADING_WOS_AUTHOR_ALIAS_FRAGMENT_RE.search(normalized):
        return True
    if _LEADING_FULL_NAME_MARKER_COMMA_RE.search(normalized):
        return True
    if _LEADING_AUTHOR_CHAIN_COLON_RE.search(normalized):
        return True
    if _starts_with_ellipsis_author_fragment(normalized):
        return True
    if _AUTHOR_YEAR_TITLE_PREFIX_RE.search(normalized):
        return True
    if _LEADING_SURNAME_INITIAL_MARKER_COMMA_RE.search(normalized):
        return True
    if _LEADING_SURNAME_INITIAL_FRAGMENT_RE.search(normalized):
        return True
    if _LEADING_INITIAL_COMMA_FRAGMENT_RE.search(normalized):
        return True
    if _LEADING_AUTHOR_DOT_TITLE_RE.search(normalized):
        return True
    if _starts_with_chinese_marked_author_title_fragment(normalized):
        return True
    if _starts_with_single_surname_comma_title_fragment(normalized):
        return True
    return (
        _split_et_al_author_prefix(normalized) is not None
        or _split_comma_surname_author_prefix(normalized) is not None
        or _split_semicolon_surname_author_prefix(normalized) is not None
        or _split_semicolon_plain_author_prefix(normalized) is not None
        or _split_chinese_author_prefixed_citation(normalized) is not None
        or _split_marked_author_prefix(normalized) is not None
        or _starts_with_marked_full_name_author_chain(normalized)
        or _starts_with_marked_connective_full_name_author_prefix(normalized)
        or _starts_with_full_name_author_list_fragment(normalized)
        or _is_dense_initial_author_fragment_title(normalized)
        or _is_author_fragment_title(normalized)
        or _is_author_only_connective_fragment_title(normalized)
        or _is_connective_author_fragment_title(normalized)
        or _starts_with_chinese_author_fragment(normalized)
        or _starts_with_semicolon_author_fragment(normalized)
    )


def _title_result_needs_author_prefix_fallback(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized:
        return True
    return bool(
        _title_has_author_prefix_contamination(normalized)
        or re.match(r"^(?:and|&)\b", normalized, flags=re.IGNORECASE)
        or _split_full_name_period_title_prefix(normalized) is not None
        or _split_author_continuation_before_title(normalized) is not None
        or _split_embedded_colon_author_prefix(normalized) is not None
        or _split_embedded_full_name_author_prefix(normalized) is not None
    )


def _repair_contaminated_title_result(
    result: tuple[str, str | None, str | None],
) -> tuple[str, str | None, str | None] | None:
    title, authors, venue = result
    if venue:
        title_with_venue = f"{title}. {venue}"
        full_name_period = _split_full_name_period_title_prefix(title_with_venue)
        if full_name_period is not None:
            extra_authors, clean_title, title_venue = full_name_period
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        continuation = _split_author_continuation_before_title(title_with_venue)
        if continuation is not None:
            extra_authors, clean_title, title_venue = continuation
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        leading_authors, trailing = _split_leading_authors(title_with_venue)
        if leading_authors is not None:
            clean_title, remainder = _split_title_and_remainder(trailing)
            candidate_title = clean_title or trailing
            if not _title_result_needs_author_prefix_fallback(candidate_title):
                _, title_venue = _split_remainder_authors_venue(remainder)
                return (
                    candidate_title,
                    _append_author_text(authors, leading_authors),
                    title_venue or remainder or None,
                )

    continuation = _split_author_continuation_before_title(title)
    if continuation is not None:
        extra_authors, clean_title, title_venue = continuation
        combined_authors = _append_author_text(authors, extra_authors)
        combined_venue = venue or title_venue
        if not _title_result_needs_author_prefix_fallback(clean_title):
            return clean_title, combined_authors, combined_venue

    colon_author = _split_embedded_colon_author_prefix(title)
    if colon_author is not None:
        extra_authors, clean_title = colon_author
        combined_authors = _append_author_text(authors, extra_authors)
        if not _title_result_needs_author_prefix_fallback(clean_title):
            return clean_title, combined_authors, venue

    embedded_author = _split_embedded_full_name_author_prefix(title)
    if embedded_author is not None:
        extra_authors, suffix = embedded_author
        clean_title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = clean_title or suffix
        combined_authors = _append_author_text(authors, extra_authors)
        combined_venue = venue or remainder or None
        if not _title_result_needs_author_prefix_fallback(candidate_title):
            return candidate_title, combined_authors, combined_venue
    return None


def _split_full_name_period_title_prefix(
    text: str,
) -> tuple[str, str, str | None] | None:
    for match in re.finditer(r"\.\s+", text):
        author_candidate = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not author_candidate or not suffix:
            continue
        if not _is_standalone_person_name_title(author_candidate):
            continue
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return author_candidate, candidate_title, venue or remainder or None
    return None


def _append_author_text(existing: str | None, extra: str | None) -> str | None:
    if not extra:
        return existing
    if not existing:
        return extra
    return f"{existing}, {extra}"


def _starts_with_full_name_author_list_fragment(title: str) -> bool:
    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", title)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return False
    authorish_count = 0
    for segment in segments[:4]:
        if re.match(r"^(?:and|&)\s+", segment, flags=re.IGNORECASE):
            if authorish_count >= 3 and (
                _looks_like_author_list(segment) or _looks_like_author_segment(segment)
            ):
                return True
            return False
        if _looks_like_author_list(segment) or _looks_like_author_segment(segment):
            authorish_count += 1
            continue
        break
    return authorish_count >= 3


def _starts_with_marked_full_name_author_chain(title: str) -> bool:
    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", title)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return False

    author_count = 0
    for index, segment in enumerate(segments[:-1]):
        has_marker = _AUTHOR_MARKER_RE.search(segment) is not None
        markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", segment))
        markerless = _clean_segment(_AUTHOR_YEAR_MARKER_RE.sub("", markerless))
        if not _looks_like_loose_full_name_author(markerless):
            return False
        author_count += 1
        if has_marker:
            remainder = ", ".join(segments[index + 1 :]).strip(" ,;")
            return author_count >= 2 and _looks_like_title_segment(remainder)
    return False


def _starts_with_marked_connective_full_name_author_prefix(title: str) -> bool:
    normalized = _clean_segment(title)
    match = re.match(
        rf"^(?P<prefix>{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{1,3}}"
        rf"\s*[*#†‡]*\s+(?:and|&)\s+"
        rf"{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{1,3}}"
        rf"\s*[*#†‡]*)\s+(?P<suffix>.+)$",
        normalized,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return False
    prefix = _clean_segment(match.group("prefix"))
    if _AUTHOR_MARKER_RE.search(prefix) is None:
        return False
    markerless_prefix = _clean_segment(_AUTHOR_MARKER_RE.sub("", prefix))
    suffix = _clean_segment(match.group("suffix"))
    return bool(
        _looks_like_author_list(markerless_prefix)
        and _looks_like_llm_author_prefix_stripped_title(suffix)
    )


def _looks_like_loose_full_name_author(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized or re.search(r"\d|[:：]", normalized):
        return False
    words = [
        word.strip("()[]{}")
        for word in re.split(r"\s+", normalized)
        if word.strip("()[]{}")
    ]
    if not 2 <= len(words) <= 5:
        return False
    first = re.sub(r"[^A-Za-z'’-]", "", words[0])
    last = re.sub(r"[^A-Za-z'’-]", "", words[-1])
    return bool(
        first
        and last
        and first[:1].isupper()
        and last[:1].isupper()
        and all(re.search(r"[A-Za-z]", word) for word in words)
    )


def _starts_with_single_surname_comma_title_fragment(title: str) -> bool:
    match = re.match(
        r"^(?P<surname>[A-Z][A-Za-z'’.-]+)\*?\s*[,，]\s+(?P<suffix>.+)$",
        _clean_segment(title),
    )
    if match is None:
        return False
    surname = re.sub(
        r"[^A-Za-z'-]",
        "",
        match.group("surname"),
    ).casefold()
    if surname not in _COMMON_ROMANIZED_CHINESE_SURNAMES:
        return False
    suffix = _clean_segment(match.group("suffix"))
    return bool(
        _starts_with_author_continuation(suffix)
        or _split_author_continuation_before_title(suffix) is not None
        or _looks_like_title_segment(suffix)
    )


def _starts_with_chinese_marked_author_title_fragment(title: str) -> bool:
    return bool(
        re.match(
            r"^[\u4e00-\u9fff]{2,6}\s*[*#†‡]+\s*[.。]\s*"
            r"(?=[A-Za-z\u4e00-\u9fff])",
            _clean_segment(title),
        )
    )


def _starts_with_ellipsis_author_fragment(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized.startswith("…"):
        return False
    if _AUTHOR_MARKER_RE.search(normalized):
        return True
    markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", normalized.lstrip("… ,，")))
    return bool(markerless and _looks_like_author_list(markerless))


def _is_connective_author_fragment_title(title: str) -> bool:
    normalized = _clean_segment(title)
    return bool(
        _CONNECTIVE_AUTHOR_YEAR_PREFIX_RE.search(normalized)
        or _CONNECTIVE_AUTHOR_ONLY_RE.fullmatch(normalized)
    )


def _is_author_only_connective_fragment_title(title: str) -> bool:
    normalized = _normalize_author_text(title)
    if not re.search(r"\s+(?:and|&)\s+", normalized, flags=re.IGNORECASE):
        return False
    if not _has_strong_author_fragment_evidence(title):
        return False

    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", normalized)
        if _clean_segment(part)
    ]
    if not parts:
        return False
    return all(
        _looks_like_connective_author_name_pair(part)
        or _looks_like_author_segment(part)
        or _looks_like_author_list(part)
        for part in parts
    )


def _starts_with_semicolon_author_fragment(title: str) -> bool:
    if ";" not in title and "；" not in title:
        return False
    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[;；]", title)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return False

    authorish_count = 0
    for segment in segments[:-1]:
        if not _looks_like_author_fragment_segment(segment):
            break
        authorish_count += 1
    return authorish_count >= 3


def _starts_with_chinese_author_fragment(title: str) -> bool:
    if "、" not in title and "，" not in title and "," not in title:
        return False
    for match in re.finditer(r"[.。]\s*", title):
        prefix = _clean_segment(title[: match.start()])
        suffix = _clean_segment(title[match.end() :])
        if not prefix or not suffix:
            continue
        author_parts = [
            _clean_segment(part)
            for part in re.split(r"\s*[、,，]\s*", prefix)
            if _clean_segment(part)
        ]
        if _looks_like_chinese_author_list(author_parts) and _looks_like_title_segment(
            suffix
        ):
            return True
    return False


def _is_author_fragment_title(title: str) -> bool:
    if not _has_strong_author_fragment_evidence(title):
        return False
    normalized = _AUTHOR_MARKER_RE.sub("", title)
    normalized = re.sub(r"\s*&+\s*(?=[,;，；.]|$)", "", normalized)
    parts = [
        _clean_segment(part)
        for part in re.split(r"(?:\.\s+|[,，;；]\s*)", normalized)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False
    return all(_looks_like_author_fragment_segment(part) for part in parts)


def _is_dense_initial_author_fragment_title(title: str) -> bool:
    normalized = _normalize_author_text(title)
    if not normalized or "," not in normalized:
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", normalized)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False

    has_initial_evidence = False
    for part in parts:
        markerless = _AUTHOR_MARKER_RE.sub("", part).strip()
        if "." in markerless:
            has_initial_evidence = True
        if (
            _looks_like_author_fragment_segment(part)
            or _is_single_author_name_token(markerless)
            or re.fullmatch(_INITIAL_CLUSTER_PATTERN, markerless)
        ):
            continue
        return False
    return has_initial_evidence


def _has_strong_author_fragment_evidence(title: str) -> bool:
    return bool(
        _LEADING_SURNAME_INITIAL_FRAGMENT_RE.search(title)
        or _LEADING_INITIAL_COMMA_FRAGMENT_RE.search(title)
        or re.search(r"\b[A-Z]\.", title)
        or _AUTHOR_MARKER_RE.search(title)
        or ";" in title
        or "；" in title
    )


def _looks_like_author_fragment_segment(text: str) -> bool:
    raw = str(text).strip()
    if re.fullmatch(r"(?:[A-Z]\.\s*){1,4}", raw):
        return True
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    if re.fullmatch(r"(?:[A-Z]\.?\s*){1,4}", normalized):
        return True
    return (
        _parse_surname_given_author_segment(normalized) is not None
        or _looks_like_author_segment(normalized)
        or _looks_like_romanized_chinese_full_name_author(
            normalized,
            require_uppercase=False,
        )
    )


def _normalize_sentence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip(" \t\r\n")


def _clean_segment(text: str) -> str:
    return _TRAILING_PUNCTUATION_RE.sub("", clean_paper_title(text))


def _clean_publication_title_segment(
    title_text: str,
    *,
    authors_text: str | None,
) -> str:
    clean_title = _clean_segment(_strip_item_suffix(_strip_item_prefix(title_text)))
    clean_title = _repair_spaced_author_name_tokens(clean_title)
    if authors_text:
        clean_title = re.sub(r"^\s*[*#†‡]+\s*", "", clean_title).strip()
        clean_title = _strip_llm_author_prefix_from_title(
            clean_title,
            authors_text=authors_text,
        )
    continuation = _split_author_continuation_before_title(clean_title)
    if continuation is not None:
        extra_authors, candidate_title, _ = continuation
        if (
            _AUTHOR_MARKER_RE.search(clean_title) is not None
            or "," in extra_authors
            or ";" in extra_authors
            or " " in extra_authors
        ):
            clean_title = candidate_title
    clean_title = _strip_parseable_author_prefix_from_title(clean_title)
    return _repair_split_title_words(clean_title)


def _strip_parseable_author_prefix_from_title(title_text: str) -> str:
    title = _clean_segment(title_text)
    if not _has_strong_author_fragment_evidence(title):
        return title
    reparsed_title, reparsed_authors, _ = _split_title_authors_venue(title)
    if not reparsed_authors:
        return title
    candidate_title = _strip_trailing_abbreviated_venue_token(reparsed_title)
    if (
        candidate_title
        and candidate_title != title
        and _looks_like_llm_author_prefix_stripped_title(candidate_title)
    ):
        return candidate_title
    return title


def _strip_llm_author_prefix_from_title(
    title_text: str,
    *,
    authors_text: str,
) -> str:
    title = _clean_segment(title_text)
    markerless_title = _clean_segment(_AUTHOR_MARKER_RE.sub("", title))
    title_variants = [title]
    if markerless_title and markerless_title != title:
        title_variants.append(markerless_title)
    for author_prefix in _llm_author_prefix_candidates(authors_text):
        for candidate_title_text in title_variants:
            match = re.match(
                rf"^{re.escape(author_prefix)}\s*[*#†‡&]*\s*"
                r"(?:[.,;:：。]\s*)?(?P<suffix>.+)$",
                candidate_title_text,
                flags=re.IGNORECASE | re.UNICODE,
            )
            if match is None:
                continue
            suffix = _clean_segment(match.group("suffix"))
            if not suffix:
                continue
            continuation = _split_author_continuation_before_title(suffix)
            candidate_title = continuation[1] if continuation is not None else suffix
            if _looks_like_llm_author_prefix_stripped_title(candidate_title):
                return candidate_title
    return title


def _looks_like_llm_author_prefix_stripped_title(text: str) -> bool:
    if _looks_like_publication_title_after_author_prefix(text):
        return True
    normalized = _clean_segment(text)
    words = [word for word in normalized.split() if word]
    return bool(
        len(normalized) >= 20
        and len(words) >= 5
        and not _looks_like_author_segment(normalized)
        and not _looks_like_journal_tail(normalized)
        and not _is_non_publication_title_noise(normalized)
    )


def _llm_author_prefix_candidates(authors_text: str) -> list[str]:
    normalized = _repair_spaced_author_name_tokens(_clean_segment(authors_text))
    if not normalized:
        return []

    raw_parts = [
        _clean_segment(part)
        for part in re.split(r"\s*[,，;；]\s*", normalized)
        if _clean_segment(part)
    ]
    candidates: set[str] = set()
    if raw_parts:
        for end in range(1, min(len(raw_parts), 3) + 1):
            candidates.add(", ".join(raw_parts[:end]))
    candidates.add(normalized)

    accepted: set[str] = set()
    for candidate in candidates:
        markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", candidate))
        markerless = _clean_segment(_AUTHOR_YEAR_MARKER_RE.sub("", markerless))
        normalized_author = _normalize_author_text(candidate)
        for value in (markerless, normalized_author):
            if not value:
                continue
            if _looks_like_author_segment(value) or _looks_like_author_list(value):
                accepted.add(value)
    return sorted(accepted, key=len, reverse=True)


def _repair_split_title_words(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        joined = f"{match.group(1)}{match.group(2)}"
        if joined.casefold() not in _COMMON_SPLIT_TITLE_WORD_REPAIRS:
            return match.group(0)
        return joined

    return re.sub(r"\b([A-Z])\s+([a-z]{2,20})\b", replace, text)


def _looks_like_authors(text: str) -> bool:
    return _looks_like_author_list(text)


def _has_explicit_author_syntax(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    if re.search(r"&\s*(?:[,，;；.]|$)", text):
        return True
    if _ET_AL_SUFFIX_RE.search(normalized):
        return True
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
        _VENUE_KEYWORD_RE.search(normalized)
        or _COMPACT_VENUE_YEAR_RE.fullmatch(normalized)
        or _SHORT_COMPACT_VENUE_YEAR_RE.fullmatch(normalized)
        or _extract_year_from_text(normalized)
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


def _split_surname_given_year_quoted_title_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(
        r"\b(?:19|20)\d{2}\b\s*,?\s*[‘'](?P<title>.{10,300}?)[’']",
        text,
    ):
        prefix = _clean_segment(text[: match.start()])
        title = _clean_segment(match.group("title"))
        suffix = _clean_segment(text[match.end() :])
        authors = _parse_surname_given_author_prefix(prefix)
        if not authors:
            continue
        if not _looks_like_title_segment(title):
            continue
        return title, ", ".join(authors), suffix or None
    return None


def _split_unclosed_quote_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    match = re.match(r"^(?P<authors>.+?)\s+[\"“]\s*(?P<suffix>.+)$", text)
    if match is None:
        return None

    authors = _clean_segment(match.group("authors"))
    suffix = _strip_leading_title_label(_clean_segment(match.group("suffix")))
    if not authors or not suffix:
        return None
    if not (
        _looks_like_author_list(authors) or _looks_like_author_segment(authors)
    ):
        return None

    title, remainder = _split_title_and_remainder(suffix)
    candidate_title = title or suffix
    if not _looks_like_title_segment(candidate_title):
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
        venue = remainder
    else:
        _, venue = _split_remainder_authors_venue(remainder)
    return candidate_title, _normalize_author_list(authors), venue


def _split_and_surname_given_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if " and " not in text:
        return None

    for match in re.finditer(r"\(?\b(?:19|20)\d{2}\b\)?[.)]?\s+", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        authors = _parse_and_surname_given_author_list(prefix)
        if not authors or not suffix:
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        return candidate_title, ", ".join(authors), venue

    for match in reversed(list(re.finditer(r"[,，]\s+", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        authors = _parse_and_surname_given_author_list(prefix)
        if not authors or not suffix:
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        return candidate_title, ", ".join(authors), venue

    return None


def _parse_and_surname_given_author_list(text: str) -> list[str]:
    normalized = _clean_segment(text)
    if " and " not in normalized:
        return []
    parts = [
        _clean_segment(part)
        for part in re.split(r"\s+and\s+", normalized, flags=re.IGNORECASE)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return []

    authors: list[str] = []
    consumed_surname_given = False
    for part in parts:
        part = re.sub(r"\s*&+\s*$", "", part).strip()
        parsed = _parse_surname_given_author_segment(part)
        if parsed is not None:
            authors.append(_normalize_surname_given_author_segment(part))
            consumed_surname_given = True
            continue
        if _looks_like_author_segment(part) or _looks_like_author_list(part):
            authors.append(_normalize_author_list(part))
            continue
        return []

    if len(authors) < 2 or not consumed_surname_given:
        return []
    return authors


def _split_chinese_comma_title_venue(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if not re.search(r"[\u4e00-\u9fff]", text):
        return None
    if "," not in text and "，" not in text:
        return None

    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", text)
        if _clean_segment(part)
    ]
    if len(parts) < 3:
        if (
            len(parts) == 2
            and _looks_like_chinese_title_segment(parts[0])
            and _looks_like_chinese_venue_segment(parts[1])
        ):
            return parts[0], None, parts[1]
        return None

    leading_semicolon_authors = _split_chinese_semicolon_author_parts(parts[0])
    if (
        _looks_like_chinese_author_list(leading_semicolon_authors)
        and _looks_like_chinese_title_segment(parts[1])
        and (
            _looks_like_chinese_venue_segment(parts[2])
            or _looks_like_probable_chinese_venue_segment(parts[2], parts[3:])
        )
    ):
        venue = ", ".join(parts[2:]).strip(" ,;") or None
        return (
            parts[1],
            _normalize_chinese_author_list(leading_semicolon_authors),
            venue,
        )

    if (
        _CHINESE_AUTHOR_SEGMENT_RE.fullmatch(parts[0])
        and _looks_like_chinese_title_segment(parts[1])
        and (
            _looks_like_chinese_venue_segment(parts[2])
            or _looks_like_probable_chinese_venue_segment(parts[2], parts[3:])
        )
    ):
        venue = ", ".join(parts[2:]).strip(" ,;") or None
        return parts[1], _normalize_chinese_author_list([parts[0]]), venue

    if (
        _looks_like_chinese_title_segment(parts[0])
        and (
            _looks_like_chinese_venue_segment(parts[1])
            or _looks_like_probable_chinese_venue_segment(parts[1], parts[2:])
        )
        and (
            _extract_year_from_text(", ".join(parts[2:])) is not None
            or len(parts) >= 3
        )
    ):
        venue = ", ".join(parts[1:]).strip(" ,;") or None
        return parts[0], None, venue

    return None


def _split_chinese_semicolon_author_parts(text: str) -> list[str]:
    if ";" not in text and "；" not in text:
        return []
    return [
        _clean_segment(part)
        for part in re.split(r"\s*[;；]\s*", text)
        if _clean_segment(part)
    ]


def _looks_like_chinese_title_segment(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < 4:
        return False
    if not re.search(r"[\u4e00-\u9fff]", normalized):
        return False
    if _CHINESE_AUTHOR_SEGMENT_RE.fullmatch(normalized):
        return False
    if _looks_like_chinese_venue_segment(normalized):
        return False
    return True


def _looks_like_chinese_venue_segment(text: str) -> bool:
    normalized = _clean_segment(text)
    return bool(
        re.search(r"[\u4e00-\u9fff]", normalized)
        and _CHINESE_VENUE_HINT_RE.search(normalized)
    )


def _looks_like_probable_chinese_venue_segment(
    text: str,
    following_parts: list[str],
) -> bool:
    normalized = _clean_segment(text)
    if not re.search(r"[\u4e00-\u9fff]", normalized):
        return False
    if not 2 <= len(normalized) <= 16:
        return False
    if re.search(r"\d", normalized):
        return False
    return _extract_year_from_text(", ".join(following_parts)) is not None


def _normalize_author_text(text: str) -> str:
    normalized = _clean_segment(text)
    normalized = normalized.replace("’", "'")
    normalized = re.sub(r"[‐‑‒–—]", "-", normalized)
    normalized = re.sub(r"(?<=[A-Za-z])\s*-\s*(?=[A-Za-z])", "-", normalized)
    normalized = re.sub(r"\b([A-Z])\.(?=[A-Z][a-z])", r"\1. ", normalized)
    normalized = _repair_split_diacritic_author_letters(normalized)
    normalized = _repair_spaced_author_name_tokens(normalized)
    normalized = _repair_split_pinyin_given_name_tokens(normalized)
    normalized = re.sub(r"\s*&+\s*(?=[,;，；.]|$)", "", normalized)
    normalized = _AUTHOR_NOTE_RE.sub("", normalized)
    normalized = _AUTHOR_YEAR_MARKER_RE.sub("", normalized)
    normalized = _AUTHOR_MARKER_RE.sub("", normalized)
    normalized = re.sub(r"(?<=\.)\+(?=\s*(?:[,;，；.]|$))", "", normalized)
    normalized = re.sub(r"(?<=[A-Z])\+(?=\s*(?:[,;，；.]|$))", "", normalized)
    normalized = re.sub(r"^\s*(?:and|&)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip(" ,;")


def _repair_spaced_author_name_tokens(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        joined = f"{match.group(1)}{match.group(2)}"
        if joined.casefold() not in _COMMON_SPACED_AUTHOR_TOKEN_REPAIRS:
            return match.group(0)
        return joined

    return re.sub(r"\b([A-Z][a-z]{0,4})\s+([a-z]{1,12})\b", replace, text)


def _repair_split_diacritic_author_letters(text: str) -> str:
    repaired = _SPLIT_INTERNAL_DIACRITIC_LETTER_RE.sub(r"\1", text)
    return _SPLIT_TRAILING_DIACRITIC_LETTER_RE.sub(r"\1", repaired)


def _repair_split_pinyin_given_name_tokens(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        surname = match.group("surname")
        initial = match.group("initial")
        suffix = match.group("suffix")
        return f"{surname} {initial}{suffix}"

    return re.sub(
        rf"\b(?P<surname>{_NAME_TOKEN_PATTERN})\s+"
        r"(?P<initial>[A-Z])\s+(?P<suffix>[a-z]{2,16})\b",
        replace,
        text,
        flags=re.UNICODE,
    )


def _normalize_surname_initial_author_order(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        surname = match.group(1)
        initials = _WHITESPACE_RE.sub(" ", match.group(2)).strip()
        return f"{initials} {surname} "

    return _SURNAME_INITIAL_AUTHOR_RE.sub(replace, text)


def _parse_surname_given_author_segment(text: str) -> tuple[str, str] | None:
    normalized = _normalize_author_text(text)
    match = _SURNAME_GIVEN_AUTHOR_RE.fullmatch(normalized)
    if match is None:
        return None
    surname = match.group(1)
    given = _WHITESPACE_RE.sub(" ", match.group(2)).strip()
    given_tokens = given.split()
    if any(
        re.fullmatch(_INITIAL_CLUSTER_PATTERN, token)
        for token in given_tokens[:-1]
    ) and any(
        not re.fullmatch(_INITIAL_CLUSTER_PATTERN, token)
        for token in given_tokens[1:]
    ):
        return None
    return surname, given


def _normalize_surname_given_author_segment(text: str) -> str:
    parsed = _parse_surname_given_author_segment(text)
    if parsed is None:
        return _normalize_author_text(text)
    surname, given = parsed
    given = _normalize_given_name_tokens(given)
    return f"{given} {surname}".strip()


def _parse_surname_given_author_prefix(text: str) -> list[str]:
    normalized = _normalize_author_text(text)
    if not normalized:
        return []
    segments = [
        _clean_segment(segment)
        for segment in re.split(r"\s*[,，]\s*", normalized)
        if _clean_segment(segment)
    ]
    if len(segments) < 2:
        return []

    authors: list[str] = []
    index = 0
    while index + 1 < len(segments):
        surname = segments[index]
        given = segments[index + 1]
        connective_match = re.match(
            r"^(?P<given>.+?)\s+(?:&|and)\s+(?P<next_surname>[^\s].+)$",
            given,
            flags=re.IGNORECASE,
        )
        if connective_match is not None and index + 2 < len(segments):
            first_pair = f"{surname}, {connective_match.group('given')}"
            second_pair = (
                f"{connective_match.group('next_surname')}, {segments[index + 2]}"
            )
            if (
                _parse_surname_given_author_segment(first_pair) is None
                or _parse_surname_given_author_segment(second_pair) is None
            ):
                return []
            authors.append(_normalize_surname_given_author_segment(first_pair))
            authors.append(_normalize_surname_given_author_segment(second_pair))
            index += 3
            continue

        pair = f"{surname}, {given}"
        if _parse_surname_given_author_segment(pair) is None:
            return []
        authors.append(_normalize_surname_given_author_segment(pair))
        index += 2

    if index != len(segments) or len(authors) < 2:
        return []
    return authors


def _normalize_given_name_tokens(text: str) -> str:
    normalized = _normalize_initial_cluster(text)
    return re.sub(r"(?<![A-Za-z])([A-Z])(?=\s|$)", r"\1.", normalized)


def _normalize_initial_cluster(text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    if not re.fullmatch(
        r"(?:[A-Z]\.?(?:-[A-Z]\.?)?)(?:\s+[A-Z]\.?(?:-[A-Z]\.?)?)*",
        normalized,
    ):
        return normalized
    normalized = re.sub(r"\b([A-Z])\.?(?=(?:-|$|\s))", r"\1.", normalized)
    normalized = re.sub(r"-([A-Z])\.?", r"-\1.", normalized)
    return normalized


def _looks_like_semicolon_surname_author_list(text: str) -> bool:
    parts = _parse_semicolon_surname_author_parts(text)
    return parts is not None and len(parts) >= 2


def _normalize_semicolon_surname_author_list(text: str) -> str:
    parts = _parse_semicolon_surname_author_parts(text)
    if parts is None:
        return ""
    return ", ".join(parts).strip(" ,;")


def _parse_semicolon_surname_author_parts(text: str) -> list[str] | None:
    text = _repair_missing_semicolon_between_surname_initial_authors(text)
    parts = [
        _clean_segment(part)
        for part in re.split(r"[;；]", text)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return None
    authors: list[str] = []
    for part in parts:
        parsed = _parse_surname_given_author_segment(part)
        if parsed is not None:
            authors.append(_normalize_surname_given_author_segment(part))
            continue

        comma_parts = [
            _clean_segment(item)
            for item in re.split(r"[,，]", part)
            if _clean_segment(item)
        ]
        if len(comma_parts) < 2 or len(comma_parts) % 2:
            return None
        for index in range(0, len(comma_parts), 2):
            candidate = f"{comma_parts[index]}, {comma_parts[index + 1]}"
            if _parse_surname_given_author_segment(candidate) is None:
                return None
            authors.append(_normalize_surname_given_author_segment(candidate))
    if len(authors) < 2:
        return None
    return authors


def _repair_missing_semicolon_between_surname_initial_authors(text: str) -> str:
    return re.sub(
        rf"(?P<initials>{_INITIAL_CLUSTER_PATTERN})\s+"
        rf"(?P<next>[A-Z][A-Za-z'’-]+,\s*{_INITIAL_CLUSTER_PATTERN})",
        r"\g<initials>; \g<next>",
        text,
    )


def _normalize_author_list(text: str) -> str:
    normalized = _normalize_author_text(text)
    normalized = _normalize_surname_initial_author_order(normalized)
    normalized = re.sub(r"\s*[;；]\s*", ", ", normalized)
    normalized = re.sub(r",\s*(?:and|&)\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+(?:and|&)\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r"(?:,\s*){2,}", ", ", normalized)
    return normalized.strip(" ,;")


def _looks_like_concatenated_author_name(text: str) -> bool:
    normalized = _AUTHOR_MARKER_RE.sub("", _clean_segment(text)).strip()
    if not _CONCATENATED_AUTHOR_NAME_RE.fullmatch(normalized):
        return False
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    return _looks_like_author_segment(split)


def _normalize_concatenated_author_name(text: str) -> str:
    normalized = _AUTHOR_MARKER_RE.sub("", _clean_segment(text)).strip()
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)


def _looks_like_author_list(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    if _SURNAME_INITIAL_COMMA_RE.fullmatch(normalized):
        return True
    if _parse_surname_given_author_segment(normalized) is not None:
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
    if _looks_like_romanized_chinese_full_name_author(normalized):
        return True
    if _INITIAL_PREFIXED_AUTHOR_RE.fullmatch(normalized):
        return True
    if _ET_AL_SUFFIX_RE.search(normalized):
        base = _ET_AL_SUFFIX_RE.sub("", normalized).strip(" ,;")
        return bool(base and base != normalized and _looks_like_author_segment(base))
    if re.fullmatch(
        r"[A-Z][A-Za-z-]+\s+\([A-Z][A-Za-z.-]+\)\s+[A-Z][A-Za-z-]+",
        normalized,
    ):
        return True
    if re.fullmatch(r"(?:[A-Z]\.\s*){1,3}[A-Z][a-z]+(?:-[A-Z][a-z]+)?", normalized):
        return True
    if re.fullmatch(
        rf"[A-Z]\s+{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,2}}",
        normalized,
        flags=re.UNICODE,
    ):
        return True
    tokens = normalized.split()
    if (
        2 <= len(tokens) <= 7
        and all(
            re.fullmatch(
                rf"(?:[A-Z]\.|(?:[A-Z]\.){{2,}}|{_NAME_TOKEN_PATTERN})",
                token,
                flags=re.UNICODE,
            )
            for token in tokens
        )
        and len(tokens[0]) > 1
        and any(char.isupper() for char in tokens[0])
        and tokens[1][:1].isupper()
        and all(_is_author_name_token(token) for token in tokens)
    ):
        title_connectors = {
            "after",
            "against",
            "as",
            "at",
            "based",
            "before",
            "between",
            "by",
            "for",
            "from",
            "in",
            "into",
            "of",
            "on",
            "over",
            "through",
            "to",
            "toward",
            "towards",
            "under",
            "using",
            "via",
            "with",
            "within",
            "without",
        }
        return not any(token.casefold() in title_connectors for token in tokens)
    return bool(_AUTHOR_NAME_RE.fullmatch(normalized))


def _is_author_name_token(token: str) -> bool:
    normalized = token.strip("()[]{}")
    if not normalized:
        return False
    if re.fullmatch(r"(?:[A-Z]\.){1,4}", normalized):
        return True
    if re.fullmatch(_NAME_TOKEN_PATTERN, normalized, flags=re.UNICODE):
        if normalized[:1].isupper():
            return True
        return normalized.casefold() in {
            "da",
            "de",
            "del",
            "der",
            "dos",
            "du",
            "la",
            "le",
            "van",
            "von",
        }
    return False


def _looks_like_title_segment(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    if _looks_like_author_segment(normalized) or _looks_like_venue(normalized):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", normalized))


def _looks_like_publication_title_after_author_prefix(text: str) -> bool:
    return (
        _looks_like_title_segment(text)
        or _looks_like_short_title_after_author_prefix(text)
        or _looks_like_chinese_title_segment(text)
    )


def _looks_like_short_title_after_author_prefix(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < 5:
        return False
    if _looks_like_venue(normalized) or _looks_like_journal_tail(normalized):
        return False
    if _has_explicit_author_syntax(normalized) and _looks_like_author_list(normalized):
        return False
    if ":" in normalized:
        return True
    words = [word for word in normalized.split() if word]
    if len(words) >= 3:
        return True
    return bool(len(words) >= 2 and re.search(r"[-/]", normalized))


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
    skip_next_author_segment = False
    for index, segment in enumerate(segments):
        if skip_next_author_segment:
            skip_next_author_segment = False
            continue

        if (
            not authors
            and index + 2 < len(segments)
            and _is_single_author_name_token(segment)
            and (
                _looks_like_author_segment(segments[index + 1])
                or _looks_like_author_list(segments[index + 1])
            )
        ):
            authors.append(_normalize_author_text(segment))
            continue

        if authors:
            if_citations_tail = _split_if_citations_tail_from_segments(
                segments,
                index,
                allow_short_title=True,
            )
            if if_citations_tail is not None:
                title, venue = if_citations_tail
                return title, ", ".join(authors), venue

        if authors and (
            continuation := _split_author_continuation_before_title(segment)
        ) is not None:
            extra_authors, title, remainder = continuation
            if extra_authors:
                authors.append(extra_authors)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title, ", ".join(authors), venue

        if authors and (
            colon_author := _split_embedded_colon_author_prefix(segment)
        ) is not None:
            embedded_authors, suffix = colon_author
            authors.append(embedded_authors)
            title, remainder = _split_title_and_remainder(suffix)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title or suffix, ", ".join(authors), venue

        if authors and (
            marked_author := _split_marked_author_prefix(segment)
        ) is not None:
            title, marked_authors, remainder = marked_author
            if marked_authors:
                authors.append(marked_authors)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title, ", ".join(authors), venue

        if authors and (
            embedded_author := _split_embedded_full_name_author_prefix(segment)
        ) is not None:
            embedded_authors, suffix = embedded_author
            authors.append(embedded_authors)
            title, remainder = _split_title_and_remainder(suffix)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            title, venue = _strip_duplicate_bare_venue_tail(title or suffix, venue or "")
            return title, ", ".join(authors), venue

        if authors:
            full_name_author_chain = _split_full_name_author_chain_before_title(
                segments,
                index,
            )
            if full_name_author_chain is not None:
                extra_authors, title, venue = full_name_author_chain
                authors.extend(extra_authors)
                return title, ", ".join(authors), venue

        if authors and index + 1 < len(segments):
            connective_authors = _split_connective_author_with_following_initials(
                segment,
                segments[index + 1],
            )
            if connective_authors is not None:
                authors.extend(connective_authors)
                skip_next_author_segment = True
                continue
            connective_full_name_authors = (
                _split_connective_author_with_following_full_name(
                    segment,
                    segments[index + 1],
                )
            )
            if connective_full_name_authors is not None:
                authors.extend(connective_full_name_authors)
                skip_next_author_segment = True
                continue

        if authors:
            bare_venue_tail = _split_bare_venue_tail_before_numeric_segments(
                segment,
                segments[index + 1 :],
            )
            if bare_venue_tail is not None:
                title, venue = bare_venue_tail
                return title, ", ".join(authors), venue

            multi_segment_title = _split_comma_title_segments_with_following_venue(
                segments,
                index,
            )
            if multi_segment_title is not None:
                title, venue = multi_segment_title
                return title, ", ".join(authors), venue

            title_with_venue = _split_comma_title_segment_with_following_venue(
                segment,
                segments[index + 1 :],
            )
            if title_with_venue is not None:
                title, venue = title_with_venue
                return title, ", ".join(authors), venue

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
        title, remainder = _split_title_and_remainder(segment)
        if authors and title != segment and _looks_like_title_segment(title):
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return title, ", ".join(authors), venue
        if (
            authors
            and _looks_like_title_segment(segment)
            and index + 2 <= len(segments)
            and _PUBLICATION_STATUS_TAIL_RE.fullmatch(segments[index + 1])
        ):
            venue_parts = [part for part in segments[index + 1 :] if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            return segment, ", ".join(authors), venue
        if authors and _looks_like_title_segment(segment) and index + 1 < len(
            segments
        ):
            next_segment = segments[index + 1]
            venue_tail = ", ".join(segments[index + 1 :]).strip(" ,;")
            if (
                _looks_like_venue(next_segment)
                or _looks_like_journal_tail(next_segment)
                or _looks_like_journal_tail(venue_tail)
            ):
                return segment, ", ".join(authors), venue_tail or None
        if authors:
            for end_index in range(index + 2, min(len(segments), index + 4) + 1):
                candidate_title = ", ".join(segments[index:end_index]).strip(" ,;")
                if not _looks_like_title_segment(candidate_title):
                    continue
                venue = ", ".join(segments[end_index:]).strip(" ,;") or None
                return candidate_title, ", ".join(authors), venue
        if not authors or not _looks_like_title_segment(segment):
            return None
        venue = ", ".join(segments[index + 1 :]).strip(" ,;") or None
        return segment, ", ".join(authors), venue

    return None


def _split_connective_author_with_following_initials(
    segment: str,
    following_segment: str,
) -> list[str] | None:
    match = re.match(
        rf"^(?P<first>.+?)\s+(?:and|&)\s+(?P<surname>{_NAME_TOKEN_PATTERN})$",
        _clean_segment(segment),
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return None

    first_author = _clean_segment(match.group("first"))
    surname = _clean_segment(match.group("surname"))
    initials = _AUTHOR_MARKER_RE.sub("", _clean_segment(following_segment))
    if not first_author or not surname or not initials:
        return None
    if not _looks_like_author_segment(first_author):
        return None
    if not re.fullmatch(_INITIAL_CLUSTER_PATTERN, initials):
        return None

    return [
        _normalize_author_text(first_author),
        f"{_normalize_initial_cluster(initials)} {surname}".strip(),
    ]


def _split_full_name_author_chain_before_title(
    segments: list[str],
    start_index: int,
) -> tuple[list[str], str, str | None] | None:
    extra_authors: list[str] = []
    max_end = min(len(segments) - 1, start_index + 8)
    for index in range(start_index, max_end):
        connective_author = _parse_connective_full_name_author_segment(
            segments[index]
        )
        if connective_author is not None:
            if not extra_authors:
                return None
            title_venue = _split_title_from_comma_segments_after_author_chain(
                segments,
                index + 1,
            )
            if title_venue is None:
                return None
            title, venue = title_venue
            return [*extra_authors, connective_author], title, venue

        if not _looks_like_author_continuation_segment(segments[index]):
            if not extra_authors:
                return None
            title_venue = _split_title_from_comma_segments_after_author_chain(
                segments,
                index,
            )
            if title_venue is None:
                return None
            title, venue = title_venue
            return extra_authors, title, venue
        extra_authors.append(_normalize_author_text(segments[index]))
    return None


def _parse_connective_full_name_author_segment(segment: str) -> str | None:
    match = re.match(
        rf"^(?:and|&)\s+(?P<author>{_NAME_TOKEN_PATTERN}"
        rf"(?:\s+{_NAME_TOKEN_PATTERN}){{1,3}})[*#†‡&]*$",
        _clean_segment(segment),
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return None
    author = _AUTHOR_MARKER_RE.sub("", _clean_segment(match.group("author")))
    if not _looks_like_author_segment(author):
        return None
    return _normalize_author_text(author)


def _split_title_from_comma_segments_after_author_chain(
    segments: list[str],
    start_index: int,
) -> tuple[str, str | None] | None:
    if start_index >= len(segments):
        return None

    title_with_venue = _split_comma_title_segment_with_following_venue(
        segments[start_index],
        segments[start_index + 1 :],
    )
    if title_with_venue is not None:
        return title_with_venue

    multi_segment_title = _split_comma_title_segments_with_following_venue(
        segments,
        start_index,
    )
    if multi_segment_title is not None:
        return multi_segment_title

    if start_index == len(segments) - 1:
        candidate_title = segments[start_index]
        if _looks_like_publication_title_after_author_prefix(candidate_title):
            return candidate_title, None
    return None


def _split_connective_author_with_following_full_name(
    segment: str,
    following_segment: str,
) -> list[str] | None:
    first_author = _clean_segment(segment)
    if not _looks_like_author_segment(first_author):
        return None
    match = re.match(
        rf"^(?:and|&)\s+(?P<author>{_NAME_TOKEN_PATTERN}"
        rf"(?:\s+{_NAME_TOKEN_PATTERN}){{1,3}})[*#†‡&]*$",
        _clean_segment(following_segment),
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return None
    second_author = _AUTHOR_MARKER_RE.sub("", _clean_segment(match.group("author")))
    if not _looks_like_author_segment(second_author):
        return None
    return [
        _normalize_author_text(first_author),
        _normalize_author_text(second_author),
    ]


def _split_bare_venue_tail_before_numeric_segments(
    segment: str,
    following_segments: list[str],
) -> tuple[str, str] | None:
    if not following_segments or not _starts_with_numeric_citation_tail(
        following_segments
    ):
        return None

    period_split = _split_period_venue_tail_before_numeric_segments(
        segment,
        following_segments,
    )
    if period_split is not None:
        return period_split
    if ". " in segment:
        return None

    return _split_inline_venue_tail_before_numeric_segments(
        segment,
        following_segments,
    )


def _split_period_venue_tail_before_numeric_segments(
    segment: str,
    following_segments: list[str],
) -> tuple[str, str] | None:
    for match in re.finditer(r"\.\s+", segment):
        if _is_abbreviated_venue_period(segment, match.start(), match.end()):
            continue
        title = _clean_residual_title_marker(segment[: match.start()])
        venue_head = _clean_segment(segment[match.end() :])
        if not title or not venue_head:
            continue
        if not (
            _looks_like_journal_tail(venue_head) or _VENUE_KEYWORD_RE.search(venue_head)
            or _looks_like_journal_tail(
                ", ".join([venue_head, *following_segments]).strip(" ,;")
            )
        ):
            continue
        if not _looks_like_title_text_allowing_year_range(title):
            continue
        venue = ", ".join([venue_head, *following_segments]).strip(" ,;")
        return title, venue
    return None


def _split_inline_venue_tail_before_numeric_segments(
    segment: str,
    following_segments: list[str],
) -> tuple[str, str] | None:
    venue_start_re = re.compile(
        r"\s+(?=(?:"
        r"IEEE\b|ACM\b|Journal\s+of\b|J\.\s+of\b|"
        r"Nature\b|Science\b|Cell\b|PNAS\b|"
        r"Proceedings?\b|Conference\b"
        r"))",
        re.IGNORECASE,
    )
    for match in venue_start_re.finditer(segment):
        title = _clean_residual_title_marker(segment[: match.start()])
        venue_head = _clean_segment(segment[match.end() :])
        if not title or not venue_head:
            continue
        if not (
            _looks_like_journal_tail(venue_head) or _VENUE_KEYWORD_RE.search(venue_head)
        ):
            continue
        if not _looks_like_title_text_allowing_year_range(title):
            continue
        venue = ", ".join([venue_head, *following_segments]).strip(" ,;")
        return title, venue
    return None


def _is_abbreviated_venue_period(text: str, start: int, end: int) -> bool:
    token = re.split(r"\s+", text[:start].strip())[-1]
    suffix = text[end:].lstrip()
    return bool(re.fullmatch(r"[A-Z]", token) and suffix[:1].islower())


def _clean_residual_title_marker(text: str) -> str:
    return _clean_segment(_RESIDUAL_CITATION_MARKER_RE.sub("", text))


def _starts_with_numeric_citation_tail(segments: list[str]) -> bool:
    if not segments:
        return False
    return bool(re.match(r"^(?:\d|vol\b|pp?\b|pages?\b)", segments[0], re.IGNORECASE))


def _looks_like_title_text_allowing_year_range(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", normalized):
        return False
    if _looks_like_author_segment(normalized) or _looks_like_author_list(normalized):
        return False
    return len(normalized.split()) >= 4 or re.search(r"[\u4e00-\u9fff]", normalized)


def _split_comma_title_segments_with_following_venue(
    segments: list[str],
    start_index: int,
) -> tuple[str, str | None] | None:
    first_segment = segments[start_index]
    if _has_explicit_author_syntax(first_segment) and _looks_like_author_list(
        first_segment
    ):
        return None
    period_venue_title = _split_comma_title_continuation_with_period_venue(
        segments,
        start_index,
    )
    if period_venue_title is not None:
        return period_venue_title
    for end_index in range(start_index + 2, min(len(segments), start_index + 4) + 1):
        candidate_segments = segments[start_index:end_index]
        following_segments = segments[end_index:]
        if not following_segments:
            continue
        if (
            _looks_like_author_list(first_segment)
            and (
                re.search(r"\s+(?:and|&)\s+", first_segment, flags=re.IGNORECASE)
                or _AUTHOR_MARKER_RE.search(first_segment) is not None
            )
            and _segments_start_with_title_and_venue(segments[start_index + 1 :])
        ):
            return None
        title = ", ".join(candidate_segments).strip(" ,;")
        if not any(
            re.match(r"^(?:and|&)\s+", candidate, flags=re.IGNORECASE)
            for candidate in candidate_segments[1:]
        ):
            continue
        if any(
            _has_explicit_author_syntax(candidate)
            and _looks_like_author_list(candidate)
            for candidate in candidate_segments[:-1]
        ):
            continue
        if not _looks_like_publication_title_after_author_prefix(title):
            continue
        venue = _venue_from_following_comma_segments(following_segments)
        if venue is None:
            continue
        return _strip_duplicate_bare_venue_tail(title, venue)
    return None


def _split_comma_title_continuation_with_period_venue(
    segments: list[str],
    start_index: int,
) -> tuple[str, str | None] | None:
    first_segment = segments[start_index]
    if _looks_like_author_list(first_segment) or _looks_like_author_segment(
        first_segment
    ):
        return None
    for end_index in range(start_index + 2, min(len(segments), start_index + 4) + 1):
        candidate_segments = segments[start_index:end_index]
        following_segments = segments[end_index:]
        if not following_segments:
            continue
        candidate = ", ".join(candidate_segments).strip(" ,;")
        title, venue_head = _split_title_and_remainder(candidate)
        if not venue_head or title == candidate:
            continue
        if not _looks_like_publication_title_after_author_prefix(title):
            continue
        if not (_looks_like_venue(venue_head) or _looks_like_journal_tail(venue_head)):
            continue
        venue_tail = _venue_from_following_comma_segments(following_segments)
        if venue_tail is None and not _starts_with_numeric_citation_tail(
            following_segments
        ):
            continue
        venue_parts = [venue_head, venue_tail] if venue_tail else [
            venue_head,
            *following_segments,
        ]
        venue = ", ".join(part for part in venue_parts if part).strip(" ,;")
        return _strip_duplicate_bare_venue_tail(title, venue)
    return None


def _venue_from_following_comma_segments(segments: list[str]) -> str | None:
    if not segments:
        return None
    first = segments[0]
    if _looks_like_venue(first) or _looks_like_journal_tail(first):
        return ", ".join(part for part in segments if part).strip(" ,;") or None
    if (
        _PUBLICATION_STATUS_TAIL_RE.fullmatch(first) is not None
        and len(segments) >= 2
        and (_looks_like_venue(segments[1]) or _looks_like_journal_tail(segments[1]))
    ):
        return ", ".join(part for part in segments if part).strip(" ,;") or None
    return None


def _split_comma_title_segment_with_following_venue(
    segment: str,
    following_segments: list[str],
) -> tuple[str, str | None] | None:
    if not following_segments:
        return None
    bare_venue_tail = _split_bare_venue_tail_before_numeric_segments(
        segment,
        following_segments,
    )
    if bare_venue_tail is not None:
        return bare_venue_tail
    if (
        _looks_like_author_list(segment)
        and (
            re.search(r"\s+(?:and|&)\s+", segment, flags=re.IGNORECASE)
            or _AUTHOR_MARKER_RE.search(segment) is not None
        )
        and _segments_start_with_title_and_venue(following_segments)
    ):
        return None

    venue_tail = ", ".join(part for part in following_segments if part).strip(" ,;")
    if not venue_tail:
        return None

    if _venue_from_following_comma_segments(following_segments) is None:
        return None

    title, remainder = _split_title_and_remainder_after_author_prefix(segment)
    candidate_title = title or segment
    if not _looks_like_publication_title_after_author_prefix(candidate_title):
        return None
    venue = ", ".join(part for part in (remainder, *following_segments) if part).strip(
        " ,;"
    )
    return _strip_duplicate_bare_venue_tail(candidate_title, venue)


def _segment_contains_title_and_venue(text: str) -> bool:
    title, remainder = _split_title_and_remainder_after_author_prefix(text)
    candidate_title = title or text
    return bool(
        remainder
        and _looks_like_publication_title_after_author_prefix(candidate_title)
        and (_looks_like_venue(remainder) or _looks_like_journal_tail(remainder))
    )


def _segments_start_with_title_and_venue(segments: list[str]) -> bool:
    for end_index in range(1, min(len(segments), 3) + 1):
        if _segment_contains_title_and_venue(
            ", ".join(segments[:end_index]).strip(" ,;")
        ):
            return True
    return False


def _split_embedded_colon_author_prefix(text: str) -> tuple[str, str] | None:
    match = re.match(r"^(?P<author>[^:：]{2,80})\s*[:：]\s*(?P<title>.+)$", text)
    if match is None:
        return None
    author_candidate = _clean_segment(match.group("author"))
    title_candidate = _clean_segment(match.group("title"))
    if not author_candidate or not title_candidate:
        return None
    if not _looks_like_embedded_full_name_author(author_candidate):
        return None
    if not _looks_like_title_segment(title_candidate):
        return None
    return _normalize_author_text(author_candidate), title_candidate


def _split_embedded_full_name_author_prefix(text: str) -> tuple[str, str] | None:
    normalized = _clean_segment(text)
    words = normalized.split()
    if len(words) < 5:
        return None

    max_author_words = min(4, len(words) - 3)
    for word_count in range(2, max_author_words + 1):
        author_candidate = " ".join(words[:word_count])
        title_candidate = " ".join(words[word_count:])
        if not _looks_like_author_segment(author_candidate):
            continue
        if not _looks_like_embedded_full_name_author(author_candidate):
            continue
        if not _looks_like_title_segment(title_candidate):
            continue
        if ":" not in title_candidate and len(title_candidate.split()) < 4:
            continue
        return _normalize_author_text(author_candidate), title_candidate
    return None


def _looks_like_embedded_full_name_author(text: str) -> bool:
    normalized = _normalize_author_text(text)
    words = [word.strip("()[]{}") for word in normalized.split() if word.strip()]
    if len(words) < 2:
        return False
    if any(re.search(r"\b[A-Z]\.", word) for word in words):
        return True
    surname = re.sub(r"[^A-Za-z'-]", "", words[-1]).casefold()
    return surname in _COMMON_ROMANIZED_CHINESE_SURNAMES


def _split_et_al_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    match = _ET_AL_PREFIX_RE.match(text)
    if match is None:
        return None

    prefix = _clean_segment(match.group("prefix"))
    suffix = _clean_segment(match.group("suffix"))
    if not prefix or not suffix:
        return None
    if not _looks_like_author_list(prefix):
        return None

    title, remainder = _split_title_and_remainder(suffix)
    candidate_title = title or suffix
    if not _looks_like_title_segment(candidate_title):
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
        venue = remainder
    else:
        _, venue = _split_remainder_authors_venue(remainder)
    authors = _normalize_author_list(prefix)
    et_al_authors = f"{authors}, et al" if "," in authors else f"{authors} et al"
    return candidate_title, et_al_authors, venue


def _split_author_year_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"\(?\b(?:19|20)\d{2}\b\)?[.)]?\s+", text):
        prefix = _clean_segment(text[: match.start()]).rstrip(" ,，.;；")
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if ";" in prefix or "；" in prefix:
            if _looks_like_semicolon_surname_author_list(prefix):
                authors = _normalize_semicolon_surname_author_list(prefix)
            elif _looks_like_semicolon_plain_author_list(prefix):
                authors = _normalize_author_list(prefix)
            else:
                continue
        elif _looks_like_author_list(prefix):
            authors = _normalize_author_list(prefix)
        else:
            continue

        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, authors, venue
    return None


def _split_comma_surname_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    for match in reversed(list(re.finditer(r"[,，]\s+", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_comma_surname_author_list(prefix):
            continue
        period_author_suffix = _split_surname_given_period_author_suffix(suffix)
        if period_author_suffix is not None:
            author, title, venue = period_author_suffix
            return title, f"{_normalize_author_list(prefix)}, {author}", venue
        continuation = _split_author_continuation_before_title(suffix)
        if continuation is not None:
            extra_authors, title, venue = continuation
            return title, f"{_normalize_author_list(prefix)}, {extra_authors}", venue
        if _starts_with_author_continuation(suffix):
            continue
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _looks_like_comma_surname_author_list(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized:
        return False
    surname_initial_matches = list(
        re.finditer(
            rf"\b[A-Z][A-Za-z'’-]+,\s*{_INITIAL_CLUSTER_PATTERN}"
            r"(?=\s*(?:[,;]|and\b|&|$))",
            normalized,
        )
    )
    if len(surname_initial_matches) < 2:
        return False
    normalized_order = _normalize_surname_initial_author_order(normalized)
    normalized_order = re.sub(
        r"\s+(?:and|&)\s+", ", ", normalized_order, flags=re.IGNORECASE
    )
    parts = [
        part.strip()
        for part in re.split(r"\s*[,，]\s*", normalized_order)
        if part.strip()
    ]
    if len(parts) < 2:
        return False
    return all(
        _looks_like_author_segment(part) or _is_single_author_name_token(part)
        for part in parts
    )


def _split_comma_author_prefix_with_surname_given_pairs(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", text)
        if _clean_segment(segment)
    ]
    if len(segments) < 5:
        return None

    authors: list[str] = []
    consumed_surname_given_pair = False
    index = 0
    while index < len(segments):
        segment = segments[index]
        if index + 1 < len(segments):
            pair = f"{segment}, {segments[index + 1]}"
            if _parse_surname_given_author_segment(pair) is not None:
                authors.append(_normalize_surname_given_author_segment(pair))
                consumed_surname_given_pair = True
                index += 2
                continue

        if _looks_like_author_segment(segment) or _looks_like_author_list(segment):
            authors.append(_normalize_author_list(segment))
            index += 1
            continue

        suffix = ", ".join(segments[index:]).strip(" ,;")
        marked_author = _split_marked_author_prefix(suffix)
        if marked_author is not None:
            title, marked_authors, venue = marked_author
            if marked_authors:
                authors.append(marked_authors)
            return title, ", ".join(authors), venue
        break

    if not consumed_surname_given_pair or len(authors) < 2 or index >= len(segments):
        return None

    suffix = ", ".join(segments[index:]).strip(" ,;")
    title, remainder = _split_title_and_remainder(suffix)
    candidate_title = title or suffix
    if not _looks_like_title_segment(candidate_title):
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
        venue = remainder
    else:
        _, venue = _split_remainder_authors_venue(remainder)
    return candidate_title, ", ".join(authors), venue


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
        continuation = _split_author_continuation_before_title(suffix)
        if continuation is not None:
            extra_authors, title, venue = continuation
            authors = _normalize_author_list(prefix)
            if extra_authors:
                authors = f"{authors}, {extra_authors}"
            return title, authors, venue
        if _suffix_starts_with_author_continuation(
            suffix
        ) or _starts_with_author_continuation(suffix):
            continue

        initial_suffix = _split_initial_only_author_suffix(suffix)
        if initial_suffix is not None:
            initial_author, title, remainder = initial_suffix
            authors = _normalize_author_list(f"{prefix}, {initial_author}")
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
                venue = remainder
            else:
                _, venue = _split_remainder_authors_venue(remainder)
            return title, authors, venue

        marked_author = _split_marked_author_prefix(suffix)
        if marked_author is not None:
            title, marked_authors, venue = marked_author
            authors = _normalize_author_list(prefix)
            if marked_authors:
                authors = f"{authors}, {marked_authors}"
            return title, authors, venue

        period_author_suffix = _split_surname_given_period_author_suffix(suffix)
        if period_author_suffix is not None:
            author, title, venue = period_author_suffix
            return title, f"{_normalize_author_list(prefix)}, {author}", venue

        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _split_initial_only_author_suffix(
    text: str,
) -> tuple[str, str, str] | None:
    match = re.match(r"^((?:[A-Z]\.\s*){1,3})\s+(.+)$", text)
    if match is None:
        return None
    body = match.group(2).strip()
    title, remainder = _split_title_and_remainder(body)
    candidate_title = title or body
    if not _looks_like_title_segment(candidate_title):
        return None
    return match.group(1).strip(), candidate_title, remainder


def _split_semicolon_surname_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    last_semicolon = _split_semicolon_surname_author_prefix_on_last_semicolon(text)
    if last_semicolon is not None:
        return last_semicolon

    for match in reversed(list(re.finditer(r",\s+", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_semicolon_surname_author_list(prefix):
            continue

        period_author_suffix = _split_surname_given_period_author_suffix(suffix)
        if period_author_suffix is not None:
            author, title, venue = period_author_suffix
            return (
                title,
                f"{_normalize_semicolon_surname_author_list(prefix)}, {author}",
                venue,
            )

        comma_author_suffix = _split_surname_given_comma_author_suffix(suffix)
        if comma_author_suffix is not None:
            author, title, venue = comma_author_suffix
            return (
                title,
                f"{_normalize_semicolon_surname_author_list(prefix)}, {author}",
                venue,
            )

        marked_author = _split_marked_author_prefix(suffix)
        if marked_author is not None:
            title, marked_authors, venue = marked_author
            authors = _normalize_semicolon_surname_author_list(prefix)
            if marked_authors:
                authors = f"{authors}, {marked_authors}"
            return title, authors, venue

        if _suffix_starts_with_author_continuation(
            suffix
        ) or _starts_with_author_continuation(suffix):
            continue

        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        if title and _looks_like_title_segment(title):
            venue = remainder or None
        else:
            comma_split = _split_title_venue_on_comma(suffix)
            if comma_split is not None:
                title, venue = comma_split
            else:
                _, venue = _split_remainder_authors_venue(remainder)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        if (
            _LEADING_SURNAME_INITIAL_FRAGMENT_RE.search(candidate_title)
            or _LEADING_INITIAL_COMMA_FRAGMENT_RE.search(candidate_title)
        ):
            continue
        return (
            candidate_title,
            _normalize_semicolon_surname_author_list(prefix),
            venue,
        )
    return None


def _split_semicolon_surname_author_prefix_on_last_semicolon(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in reversed(list(re.finditer(r"[;；]\s*", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_semicolon_surname_author_list(prefix):
            continue
        if _suffix_starts_with_author_continuation(
            suffix
        ) or _starts_with_author_continuation(suffix):
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return (
            candidate_title,
            _normalize_semicolon_surname_author_list(prefix),
            venue,
        )
    return None


def _split_surname_given_period_author_suffix(
    text: str,
) -> tuple[str, str, str | None] | None:
    for match in re.finditer(r"\.\s+", text):
        author_candidate = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if _parse_surname_given_author_segment(author_candidate) is None:
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        return (
            _normalize_surname_given_author_segment(author_candidate),
            candidate_title,
            remainder or None,
        )
    return None


def _split_surname_given_comma_author_suffix(
    text: str,
) -> tuple[str, str, str | None] | None:
    match = re.match(r"^(?P<author>[^,，]+[,，]\s*[^,，]{1,60})[,，]\s*(?P<suffix>.+)$", text)
    if match is None:
        return None
    author_candidate = _clean_segment(match.group("author"))
    suffix = _clean_segment(match.group("suffix"))
    if _parse_surname_given_author_segment(author_candidate) is None:
        return None
    title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
    candidate_title = title or suffix
    if not _looks_like_title_segment(candidate_title):
        return None
    return (
        _normalize_surname_given_author_segment(author_candidate),
        candidate_title,
        remainder or None,
    )


def _split_title_and_remainder_after_author_prefix(text: str) -> tuple[str, str]:
    title, remainder = _split_title_and_remainder(text)
    comma_split = _split_title_venue_on_comma(text)
    if comma_split is None:
        return title, remainder
    comma_title, comma_remainder = comma_split
    if not _looks_like_title_segment(comma_title):
        return title, remainder
    if not title or not _looks_like_title_segment(title):
        return comma_title, comma_remainder
    if title.startswith(f"{comma_title},") and len(comma_title) < len(title):
        if _comma_remainder_starts_title_continuation(
            comma_title=comma_title,
            comma_remainder=comma_remainder,
            period_title=title,
        ):
            return title, remainder
        return comma_title, comma_remainder
    return title, remainder


def _comma_remainder_starts_title_continuation(
    *,
    comma_title: str,
    comma_remainder: str,
    period_title: str,
) -> bool:
    continuation = _clean_segment(
        re.split(r"[.。]", comma_remainder, maxsplit=1)[0]
    )
    if not continuation:
        return False
    expected_title = _clean_segment(f"{comma_title}, {continuation}")
    if expected_title != _clean_segment(period_title):
        return False
    if (
        _looks_like_venue(continuation)
        or _looks_like_journal_tail(continuation)
        or _looks_like_authors(continuation)
    ):
        return False
    return _looks_like_title_segment(expected_title) and len(continuation.split()) >= 2


def _split_semicolon_author_title_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    for match in reversed(list(re.finditer(r"[;；]\s*", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if _looks_like_semicolon_surname_author_list(prefix):
            authors = _normalize_semicolon_surname_author_list(prefix)
        elif _looks_like_semicolon_plain_author_list(prefix):
            authors = _normalize_author_list(prefix)
        else:
            continue

        continuation = _split_author_continuation_before_title(suffix)
        if continuation is not None:
            extra_authors, title, venue = continuation
            if extra_authors:
                authors = f"{authors}, {extra_authors}"
            return title, authors, venue

        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if (
            (";" in suffix or "；" in suffix)
            and _suffix_starts_with_author_continuation(suffix)
        ):
            continue
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, authors, venue
    return None


def _split_semicolon_plain_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    for match in reversed(list(re.finditer(r",\s+", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if _looks_like_semicolon_surname_author_list(prefix):
            continue
        if not _looks_like_semicolon_plain_author_list(prefix):
            continue
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _looks_like_semicolon_plain_author_list(text: str) -> bool:
    parts = [
        _clean_segment(part)
        for part in re.split(r"[;；]", text)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False
    return all(
        _looks_like_author_segment(part) or _looks_like_author_list(part)
        for part in parts
    )


def _split_semicolon_surname_author_period_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    candidate: tuple[str, str | None, str | None] | None = None
    for match in re.finditer(r"\.\s+", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if _suffix_starts_with_author_continuation(suffix):
            continue
        if not _looks_like_semicolon_surname_author_list(prefix):
            continue
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        candidate = (
            candidate_title,
            _normalize_semicolon_surname_author_list(prefix),
            venue,
        )
    return candidate


def _split_chinese_author_prefixed_citation(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if not re.search(r"[\u4e00-\u9fff]", text):
        return None

    year_prefix = _split_chinese_author_year_prefix(text)
    if year_prefix is not None:
        return year_prefix

    period_split = _split_chinese_author_prefix_on_period(text)
    if period_split is not None:
        return period_split

    parts = [
        _clean_segment(part)
        for part in re.split(r"\s*[,，、]\s*", text)
        if _clean_segment(part)
    ]
    if len(parts) < 4:
        return None

    for index in range(2, min(len(parts) - 1, 12)):
        author_parts = parts[:index]
        title = parts[index]
        if not _looks_like_chinese_author_list(author_parts):
            continue
        if not _looks_like_title_segment(title):
            continue
        venue = ", ".join(parts[index + 1 :]).strip(" ,;") or None
        return title, _normalize_chinese_author_list(author_parts), venue
    return None


def _split_chinese_author_year_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    match = re.match(
        r"^(?P<authors>.+?)(?:\s*等)?\s*[（(]\s*(?P<year>(?:19|20)\d{2})"
        r"\s*[）)]\s*[,，]\s*(?P<suffix>.+)$",
        text,
    )
    if match is None:
        return None

    author_parts = [
        _clean_segment(part)
        for part in re.split(r"\s*[,，、]\s*", match.group("authors"))
        if _clean_segment(part)
    ]
    if not _looks_like_chinese_author_list(author_parts):
        return None

    suffix = _clean_segment(match.group("suffix"))
    chinese_comma_tail = _split_chinese_comma_title_venue(suffix)
    if chinese_comma_tail is not None:
        title, _, venue = chinese_comma_tail
    else:
        title, remainder = _split_title_and_remainder(suffix)
        venue = remainder or None
    if not _looks_like_title_segment(title):
        return None
    return title, _normalize_chinese_author_list(author_parts), venue


def _split_chinese_author_prefix_on_period(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"[.。]\s*", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        author_parts = [
            _clean_segment(part)
            for part in re.split(r"\s*[,，、]\s*", prefix)
            if _clean_segment(part)
        ]
        if not _looks_like_chinese_author_list(author_parts):
            continue
        chinese_comma_tail = _split_chinese_comma_title_venue(suffix)
        if chinese_comma_tail is not None:
            title, _, venue = chinese_comma_tail
            return title, _normalize_chinese_author_list(author_parts), venue
        chinese_period_tail = _split_chinese_title_period_tail(suffix)
        if chinese_period_tail is not None:
            title, remainder = chinese_period_tail
        else:
            title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_chinese_author_list(author_parts), venue
    return None


def _split_chinese_title_period_tail(text: str) -> tuple[str, str] | None:
    for match in re.finditer(r"。", text):
        title = _clean_segment(text[: match.start()])
        remainder = _clean_segment(text[match.end() :])
        if title and remainder and _looks_like_title_segment(title):
            return title, remainder
    return None


def _looks_like_chinese_author_list(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    return all(_CHINESE_AUTHOR_SEGMENT_RE.fullmatch(part) for part in parts)


def _normalize_chinese_author_list(parts: list[str]) -> str:
    cleaned = [
        re.sub(r"\s+", "", _AUTHOR_MARKER_RE.sub("", part)).strip()
        for part in parts
    ]
    return ", ".join(part for part in cleaned if part)


def _split_author_prefix_before_acronym_title(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"\s+(?=[A-Z][A-Za-z0-9-]{2,}:)", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.start() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_author_list(prefix):
            continue
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_segment(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _split_connective_author_comma_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    for match in re.finditer(r"[,，]\s+", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if not _looks_like_connective_author_name_pair(prefix):
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_author_list(prefix), venue
    return None


def _split_marked_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for marker_match in reversed(list(_AUTHOR_MARKER_RE.finditer(text))):
        raw_prefix = text[: marker_match.start()].rstrip()
        if raw_prefix.endswith((",", ";", "，", "；")):
            continue
        prefix = _clean_segment(text[: marker_match.start()])
        raw_suffix = text[marker_match.end() :].lstrip()
        if raw_suffix.startswith(".") and re.search(r"(?:^|[,，]\s*)[A-Z]$", prefix):
            continue
        if raw_suffix.startswith(("&", ";", "；")):
            continue
        if not prefix:
            continue
        if not _looks_like_author_list(prefix):
            continue

        if raw_suffix.startswith((",", "，")):
            comma_continuation = _split_comma_author_continuation_after_marker(
                raw_suffix
            )
            if comma_continuation is None:
                continue
            extra_authors, title, venue = comma_continuation
            authors = _normalize_marked_author_prefix(prefix)
            if extra_authors:
                authors = f"{authors}, {extra_authors}"
            return title, authors, venue

        suffix = _clean_segment(raw_suffix)
        if not suffix:
            continue

        continuation = _split_author_continuation_before_title(suffix)
        if continuation is not None:
            extra_authors, title, venue = continuation
            authors = _normalize_marked_author_prefix(prefix)
            if extra_authors:
                authors = f"{authors}, {extra_authors}"
            return title, authors, venue

        title, remainder = _split_title_and_remainder(suffix)
        if not _looks_like_title_segment(title or suffix):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return title or suffix, _normalize_marked_author_prefix(prefix), venue
    return None


def _normalize_marked_author_prefix(text: str) -> str:
    if _parse_surname_given_author_segment(text) is not None:
        return _normalize_surname_given_author_segment(text)
    return _normalize_author_list(text)


def _split_comma_author_continuation_after_marker(
    text: str,
) -> tuple[str, str, str | None] | None:
    suffix = _clean_segment(text.lstrip(",， "))
    if not suffix:
        return None
    continuation = _split_author_continuation_before_title(suffix)
    if continuation is None:
        return None
    extra_authors, title, venue = continuation
    first_extra_author = _clean_segment(
        re.split(r"[,，]", extra_authors, maxsplit=1)[0]
    )
    if not _looks_like_author_segment(first_extra_author):
        return None
    return extra_authors, title, venue


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


def _split_author_continuation_before_title(
    text: str,
) -> tuple[str, str, str | None] | None:
    for match in re.finditer(r"\.(?:\s+|(?=[A-Z\u4e00-\u9fff]))", text):
        author_initial_period = _is_author_initial_period(text, match.start())
        if author_initial_period:
            leading_with_period = _clean_segment(text[: match.start() + 1])
            trailing_after_initial = text[match.end() :].strip()
            combined_author_candidate = _clean_segment(
                f"{leading_with_period} {trailing_after_initial}"
            )
            if (
                _looks_like_author_segment(combined_author_candidate)
                or _looks_like_author_list(combined_author_candidate)
                or _starts_with_author_continuation(trailing_after_initial)
            ):
                continue
            title, remainder = _split_title_and_remainder(trailing_after_initial)
            candidate_title = title or trailing_after_initial
            if _looks_like_author_segment(
                leading_with_period
            ) and _looks_like_llm_author_prefix_stripped_title(candidate_title):
                _, venue = _split_remainder_authors_venue(remainder)
                extra_authors = _normalize_author_list(leading_with_period)
                nested = _split_author_continuation_before_title(candidate_title)
                if nested is not None:
                    nested_authors, nested_title, nested_venue = nested
                    extra_authors = f"{extra_authors}, {nested_authors}"
                    return extra_authors, nested_title, nested_venue or venue
                return extra_authors, candidate_title, venue
            continue
        leading = _clean_segment(text[: match.start()])
        leading = re.sub(r"^\s*s\s+and\s+", "", leading, flags=re.IGNORECASE)
        trailing = text[match.end() :].strip()
        title, remainder = _split_title_and_remainder(trailing)
        candidate_title = title or trailing
        if not (
            _looks_like_author_segment(leading)
            or _looks_like_author_list(leading)
            or _looks_like_concatenated_author_name(leading)
        ):
            continue
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        extra_authors = (
            _normalize_concatenated_author_name(leading)
            if _looks_like_concatenated_author_name(leading)
            else _normalize_author_list(leading)
        )
        nested = _split_author_continuation_before_title(candidate_title)
        if nested is not None:
            nested_authors, nested_title, nested_venue = nested
            extra_authors = f"{extra_authors}, {nested_authors}"
            return extra_authors, nested_title, nested_venue or venue
        return extra_authors, candidate_title, venue
    return None


def _split_title_and_remainder(text: str) -> tuple[str, str]:
    text = _strip_leading_title_label(_normalize_sentence(text))
    if not text:
        return "", ""

    if_citations_tail = _split_if_citations_tail(text)
    if if_citations_tail is not None:
        return _move_author_correspondence_tail(*if_citations_tail)

    in_proc_match = _IN_PROC_TAIL_RE.search(text)
    if in_proc_match is not None:
        candidate_title = _clean_segment(text[: in_proc_match.start()])
        remainder = _clean_segment(text[in_proc_match.end() :])
        if len(candidate_title) >= _MIN_TITLE_LENGTH and remainder:
            return _move_author_correspondence_tail(candidate_title, remainder)

    proc_match = _PROC_TAIL_RE.search(text)
    if proc_match is not None:
        candidate_title = _clean_segment(text[: proc_match.start()])
        remainder = _clean_segment(text[proc_match.end() :])
        if len(candidate_title) >= _MIN_TITLE_LENGTH and remainder:
            return _move_author_correspondence_tail(candidate_title, remainder)

    citation_type_match = _CITATION_TYPE_VENUE_TAIL_RE.match(text)
    if citation_type_match is not None:
        candidate_title = _clean_segment(citation_type_match.group("title"))
        remainder = _clean_segment(citation_type_match.group("venue"))
        if len(candidate_title) >= _MIN_TITLE_LENGTH and remainder:
            return _move_author_correspondence_tail(candidate_title, remainder)

    compact_venue_match = _TRAILING_COMPACT_VENUE_YEAR_RE.match(
        text
    )
    if compact_venue_match is not None:
        candidate_title = _clean_segment(compact_venue_match.group("title"))
        remainder = _clean_segment(compact_venue_match.group("venue"))
        if len(candidate_title) >= _MIN_TITLE_LENGTH and _looks_like_venue(remainder):
            candidate_split = _split_title_venue_on_comma(
                candidate_title
            ) or _split_title_venue_on_semicolon_tail(candidate_title)
            if candidate_split is None:
                candidate_split = _split_title_inline_period_venue_tail(
                    candidate_title
                ) or _split_title_inline_venue_tail(candidate_title)
            if candidate_split is None:
                candidate_split = _split_title_status_tail(candidate_title)
            if candidate_split is not None:
                title, venue_head = candidate_split
                venue = ", ".join(part for part in (venue_head, remainder) if part)
                return _move_author_correspondence_tail(title, venue)
            return _move_author_correspondence_tail(candidate_title, remainder)

    for match in re.finditer(r"\.\s+", text):
        if _is_author_initial_period(text, match.start()):
            continue
        candidate_title = _clean_segment(text[: match.start()])
        remainder = text[match.end() :].strip()
        if len(candidate_title) < _MIN_TITLE_LENGTH:
            if (
                len(candidate_title) >= 5
                and remainder
                and _looks_like_authors(remainder)
            ):
                return _move_author_correspondence_tail(candidate_title, remainder)
            continue
        if _has_explicit_author_syntax(candidate_title) and _looks_like_authors(
            candidate_title
        ):
            continue
        if not remainder:
            return _move_author_correspondence_tail(candidate_title, "")
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
                return _move_author_correspondence_tail(title, venue)
            return _move_author_correspondence_tail(candidate_title, remainder)

    period_venue_split = _split_title_inline_period_venue_tail(text)
    if period_venue_split is not None:
        return _move_author_correspondence_tail(*period_venue_split)

    inline_venue_split = _split_title_inline_venue_tail(text)
    if inline_venue_split is not None:
        return _move_author_correspondence_tail(*inline_venue_split)

    comma_split = _split_title_venue_on_comma(text)
    if comma_split is not None:
        return _move_author_correspondence_tail(*comma_split)

    semicolon_split = _split_title_venue_on_semicolon_tail(text)
    if semicolon_split is not None:
        return _move_author_correspondence_tail(*semicolon_split)

    cleaned = _clean_segment(text)
    return _move_author_correspondence_tail(cleaned, "")


def _split_if_citations_tail(text: str) -> tuple[str, str] | None:
    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", text)
        if _clean_segment(segment)
    ]
    return _split_if_citations_tail_from_segments(
        segments,
        0,
        allow_short_title=False,
    )


def _split_if_citations_tail_from_segments(
    segments: list[str],
    start_index: int,
    *,
    allow_short_title: bool,
) -> tuple[str, str] | None:
    if start_index >= len(segments):
        return None

    metadata_index = next(
        (
            index
            for index in range(start_index + 1, len(segments))
            if _IF_CITATIONS_METADATA_RE.search(segments[index])
        ),
        None,
    )
    if metadata_index is None:
        return None

    venue_start = metadata_index - 1 if metadata_index - start_index >= 2 else metadata_index
    title = _clean_segment(", ".join(segments[start_index:venue_start]))
    title = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", title))
    venue = _clean_segment(", ".join(segments[venue_start:]))
    if not title or not venue:
        return None
    if not allow_short_title and len(title.split()) < 4 and ":" not in title:
        return None
    if not _looks_like_title_segment(title) and not _looks_like_if_citations_title_segment(
        title
    ):
        return None
    return title, venue


def _looks_like_if_citations_title_segment(title: str) -> bool:
    normalized = _clean_segment(title)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    has_comma = bool(re.search(r"[,，]", normalized))
    first_part = _clean_segment(re.split(r"[,，]", normalized, maxsplit=1)[0])
    first_part = _clean_segment(_AUTHOR_YEAR_MARKER_RE.sub("", first_part))
    if has_comma and (
        _looks_like_author_segment(first_part) or _looks_like_author_list(first_part)
    ):
        return False
    if _looks_like_venue(normalized) or _looks_like_journal_tail(normalized):
        return False
    words = [word for word in normalized.split() if word]
    return len(words) >= 3 and bool(re.search(r"[A-Za-z\u4e00-\u9fff]", normalized))


def _is_author_initial_period(text: str, period_index: int) -> bool:
    left = text[: period_index + 1]
    token = re.split(r"[\s,，;；]+", left)[-1]
    token = _AUTHOR_MARKER_RE.sub("", token)
    return bool(re.fullmatch(r"(?:[A-Z]\.\s*[-‐‑‒–—]\s*)?[A-Z]\.", token))


def _move_author_correspondence_tail(title: str, remainder: str) -> tuple[str, str]:
    match = _AUTHOR_CORRESPONDENCE_TAIL_RE.search(title)
    if match is None:
        return _strip_duplicate_bare_venue_tail(title, remainder)
    clean_title = _clean_segment(title[: match.start()])
    venue_head = _clean_segment(match.group("venue"))
    clean_remainder = " ".join(part for part in (venue_head, remainder) if part).strip()
    return _strip_duplicate_bare_venue_tail(clean_title, clean_remainder)


def _strip_duplicate_bare_venue_tail(title: str, remainder: str) -> tuple[str, str]:
    clean_title = _clean_segment(title)
    clean_remainder = _clean_segment(remainder)
    if not clean_title or not clean_remainder:
        return clean_title, clean_remainder

    match = re.match(
        r"(?P<head>[A-Za-z][A-Za-z/&.-]{2,20})(?:\s*(?:19|20)\d{2}|\b)",
        clean_remainder,
    )
    if match is None:
        return clean_title, clean_remainder

    venue_head = match.group("head")
    title_without_tail = re.sub(
        rf"\s+{re.escape(venue_head)}$",
        "",
        clean_title,
        flags=re.IGNORECASE,
    )
    if title_without_tail == clean_title:
        return clean_title, clean_remainder
    return _clean_segment(title_without_tail), clean_remainder


def _split_title_status_tail(text: str) -> tuple[str, str] | None:
    parts = [_clean_segment(part) for part in re.split(r"[,，]", text)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None
    if not _PUBLICATION_STATUS_TAIL_RE.fullmatch(parts[-1]):
        return None
    title = ", ".join(parts[:-1]).strip(" ,;")
    if not _looks_like_title_segment(title):
        return None
    return title, parts[-1]


def _split_title_inline_venue_tail(text: str) -> tuple[str, str] | None:
    cleaned = _clean_segment(text)
    if not cleaned:
        return None
    for match in _INLINE_VENUE_START_RE.finditer(cleaned):
        title = _clean_segment(cleaned[: match.start()])
        remainder = _clean_segment(cleaned[match.start() :])
        if len(title) < _MIN_TITLE_LENGTH or len(title.split()) < 4:
            continue
        if not _extract_year_from_text(remainder):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            title = re.sub(r"\s*[,，;；:]\s*in$", "", title, flags=re.IGNORECASE)
            title = _clean_segment(title)
            return title, remainder
    return None


def _split_title_inline_period_venue_tail(text: str) -> tuple[str, str] | None:
    cleaned = _clean_segment(text)
    if not cleaned:
        return None
    for match in _INLINE_PERIOD_VENUE_RE.finditer(cleaned):
        title = _clean_segment(cleaned[: match.start()])
        remainder = _clean_segment(cleaned[match.start() + 1 :])
        if len(title) < _MIN_TITLE_LENGTH:
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            return title, remainder
    return None


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
        if len(title.split()) < 2 and index < len(parts) - 1:
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
            if _looks_like_journal_tail(authors_candidate):
                continue
            if _looks_like_authors(authors_candidate) and not _looks_like_journal_tail(
                authors_candidate
            ):
                return authors_candidate, venue_candidate

    cleaned = _clean_segment(remainder)
    journal_tail = _looks_like_journal_tail(cleaned)
    if journal_tail:
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
            if _starts_with_author_continuation(trailing):
                continue
            return _normalize_author_list(leading), trailing
    return None, text


def _starts_with_author_continuation(text: str) -> bool:
    stripped = text.lstrip(" ,，;；")
    if re.match(rf"^{_NAME_TOKEN_PATTERN}\s*\(\d{{4}}\)\s*,", stripped, re.UNICODE):
        return True
    if re.match(
        rf"^(?:and|&)\s+(?:[A-Z]\.\s*){{1,3}}{_NAME_TOKEN_PATTERN}\b",
        stripped,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        return True
    if re.match(
        rf"^(?:and|&)\s+{_NAME_TOKEN_PATTERN},\s*"
        rf"(?:[A-Z]\.?\s*){{1,4}}\.?\s+",
        stripped,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        return True
    if re.match(
        rf"^(?:and|&)\s+{_NAME_TOKEN_PATTERN}"
        rf"(?:\s+{_NAME_TOKEN_PATTERN}){{0,3}}[*#†‡]*\.\s+",
        stripped,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        return True
    if re.match(
        rf"^{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,3}}"
        rf"\s*[*#†‡]+\s+[A-Z]",
        stripped,
        flags=re.UNICODE,
    ):
        return True
    if re.match(
        rf"^{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,3}}"
        rf"\s*[*#†‡]+\.\s+[\"'“”‘’]?[A-Z]",
        stripped,
        flags=re.UNICODE,
    ):
        return True
    if re.match(
        rf"^{_NAME_TOKEN_PATTERN}\s*,\s*(?:[A-Z]\.\s*){{1,3}}"
        rf"{_NAME_TOKEN_PATTERN}[*#†‡&]*\.\s+",
        stripped,
        flags=re.UNICODE,
    ):
        return True
    if re.match(
        rf"^{_NAME_TOKEN_PATTERN}[*#†‡&]*\s*,",
        stripped,
        flags=re.UNICODE,
    ):
        return True
    if re.match(
        rf"^{_NAME_TOKEN_PATTERN}[*#†‡&]*\.\s+[\"'“”‘’]?[A-Z]",
        stripped,
        flags=re.UNICODE,
    ):
        return True
    if re.match(r"^(?:[A-Z]\.\s*){1,3}\s*[,，]", stripped):
        return True
    if re.match(r"^(?:[A-Z]\.\s*){1,3}[*#†‡+]*\s*[;；,，]", stripped):
        return True
    if re.match(r"^(?:[A-Z]\.\s*){1,3}(?:&|and\b)", stripped, flags=re.IGNORECASE):
        return True
    if re.match(r"^[A-Z][A-Za-z-]+,\s*(?:[A-Z]\.\s*){1,3}\s*&", stripped):
        return True
    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，;；]", stripped)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False
    first, second = parts[0], parts[1]
    if _looks_like_connective_author_name_pair(first) and (
        _looks_like_author_continuation_segment(second)
        or _looks_like_author_segment(second)
    ):
        return True
    third_is_author = len(parts) >= 3 and _looks_like_author_continuation_segment(
        parts[2]
    )
    second_is_author = _looks_like_author_continuation_segment(second) or (
        third_is_author and _looks_like_author_segment(second)
    )
    first_is_author_token = _is_single_author_name_token(first) or (
        _AUTHOR_MARKER_RE.search(first) is not None
        and _is_single_author_name_token(_AUTHOR_MARKER_RE.sub("", first).strip())
    )
    if first_is_author_token and second_is_author:
        return bool(
            _AUTHOR_MARKER_RE.search(first)
            or _AUTHOR_MARKER_RE.search(second)
            or third_is_author
            or len(parts) >= 3
        )
    if first_is_author_token and second.lower().startswith(("and ", "& ")):
        return True
    return (
        _looks_like_author_continuation_segment(first)
        and second_is_author
    )


def _looks_like_connective_author_name_pair(text: str) -> bool:
    normalized = _normalize_author_text(text)
    match = re.fullmatch(
        r"(?P<left>.+?)\s+(?:and|&)\s+(?P<right>.+)",
        normalized,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return False
    left = _clean_segment(match.group("left"))
    right = _clean_segment(match.group("right"))
    left_is_author = _looks_like_author_segment(left) or _is_single_author_name_token(
        left
    )
    right_is_author = _looks_like_author_segment(right) or _looks_like_author_list(
        right
    )
    return left_is_author and right_is_author


def _looks_like_author_continuation_segment(text: str) -> bool:
    if not (_looks_like_author_segment(text) or _looks_like_author_list(text)):
        return False
    normalized = _normalize_author_text(text)
    tokens = normalized.split()
    if len(tokens) > 4:
        return False
    title_connectors = {
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "to",
        "with",
    }
    return not any(token.casefold() in title_connectors for token in tokens)


def _is_single_author_name_token(text: str) -> bool:
    normalized = _normalize_author_text(text)
    return bool(
        normalized[:1].isupper()
        and re.fullmatch(_NAME_TOKEN_PATTERN, normalized, flags=re.UNICODE)
    )
    return False


def _looks_like_romanized_chinese_full_name_author(
    text: str,
    *,
    require_uppercase: bool = True,
) -> bool:
    normalized = _normalize_author_text(text)
    if (
        not normalized
        or re.search(r"\d|[:：]", normalized)
        or re.search(r"[,，;；]", normalized)
    ):
        return False

    tokens = [
        token.strip("()[]{}")
        for token in re.split(r"\s+", normalized)
        if token.strip("()[]{}")
    ]
    if not 2 <= len(tokens) <= 4:
        return False

    title_connectors = {
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "to",
        "with",
    }
    if any(token.casefold() in title_connectors for token in tokens):
        return False
    if not all(
        re.fullmatch(_NAME_TOKEN_PATTERN, token, flags=re.UNICODE)
        for token in tokens
    ):
        return False

    surname = re.sub(r"[^A-Za-z'’-]", "", tokens[-1]).casefold()
    return bool(
        surname in _COMMON_ROMANIZED_CHINESE_SURNAMES
        and (not require_uppercase or any(token[:1].isupper() for token in tokens))
    )


def _looks_like_journal_tail(text: str) -> bool:
    cleaned = _clean_segment(text)
    if not cleaned:
        return False
    if _ABBREVIATED_JOURNAL_RE.fullmatch(cleaned):
        return True
    head = _clean_segment(re.split(r"[,，]", cleaned, maxsplit=1)[0])
    has_citation_tail = bool(
        re.search(r"[,，]\s*(?:V\.?\s*)?\d", cleaned, re.IGNORECASE)
        or re.search(r"\b\d+\s*\([^)]*\)\s*[,，:]", cleaned)
        or re.search(r"\.\s*\d+\s*:", cleaned)
        or re.search(r"\b\d+\s*\([A-Za-z0-9]+\)", cleaned)
    )
    if not _JOURNAL_TAIL_HINT_RE.search(head) and not has_citation_tail:
        return False
    if (
        has_citation_tail
        and re.fullmatch(r"[A-Z][A-Za-z&/-]{2,40}", head)
        and not _looks_like_author_segment(head)
    ):
        return True
    head = re.sub(r"\s+\d+\S*$", "", head)
    head = re.sub(r"\s+\d+\s*\([^)]*\)\s*$", "", head)
    head = re.sub(r"\.\s*\d+\s*:.*$", "", head)
    head = re.sub(r"\([^)]*\)", "", head)
    words = head.split()
    if not 1 <= len(words) <= 10:
        return False
    allowed_lower = {"and", "in", "of", "on", "for", "the", "with"}
    titleish_count = 0
    for word in words:
        token = word.strip("().:-")
        if not token:
            continue
        if token == "&":
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
                pdf_url=_extract_pdf_url(paragraph, page_url),
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
                pdf_url=_extract_pdf_url(row, page_url),
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
                pdf_url=(
                    _extract_pdf_url(child, page_url)
                    or _extract_pdf_url(current_dt, page_url)
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
        pdf_url=_extract_pdf_url(tag, page_url),
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
    pdf_url: str | None,
    author_filter: Callable[[str | None], bool] | None,
    year_override: int | None = None,
    authors_override: str | None = None,
    venue_override: str | None = None,
) -> HomepagePublication | None:
    normalized = _normalize_sentence(raw_text)
    if not normalized:
        return None
    if _URL_ONLY_RE.fullmatch(normalized):
        return None
    if _looks_like_biography_prose(normalized):
        return None

    item_text = _strip_item_suffix(_strip_item_prefix(normalized))
    title_text, authors_text, venue_text = _split_title_authors_venue(item_text)
    clean_title = _clean_publication_title_segment(
        title_text,
        authors_text=authors_override if authors_override is not None else authors_text,
    )
    year_value = _validate_year(
        year_override
        if year_override is not None
        else _extract_year_from_text(item_text)
    )
    if len(clean_title) < _MIN_TITLE_LENGTH and not _is_short_title_with_context(
        clean_title,
        authors_text=authors_override if authors_override is not None else authors_text,
        venue_text=venue_override if venue_override is not None else venue_text,
        year_value=year_value,
    ):
        return None
    if _is_publications_heading_text(clean_title) or clean_title.startswith("代表性论文"):
        return None
    if _AUTHOR_NOTE_ONLY_RE.fullmatch(clean_title):
        return None
    if _looks_like_semicolon_surname_author_list(clean_title):
        return None
    if _ABBREVIATED_JOURNAL_RE.fullmatch(clean_title):
        return None
    if _is_non_publication_title_noise(clean_title):
        return None
    if (
        _LEADING_SURNAME_INITIAL_FRAGMENT_RE.search(clean_title)
        or _LEADING_INITIAL_COMMA_FRAGMENT_RE.search(clean_title)
    ):
        return None

    authors_value = authors_override if authors_override is not None else authors_text
    venue_value = venue_override if venue_override is not None else venue_text
    authors_value = _clean_segment(authors_value) if authors_value else None
    venue_value = (
        _clean_segment(_strip_item_suffix(venue_value)) if venue_value else None
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
        pdf_url=pdf_url,
    )


def _is_short_title_with_context(
    clean_title: str,
    *,
    authors_text: str | None,
    venue_text: str | None,
    year_value: int | None,
) -> bool:
    if len(clean_title) < 4:
        return False
    if _is_non_publication_title_noise(clean_title):
        return False
    has_context = bool(authors_text or venue_text or year_value)
    if not has_context:
        return False
    return (
        _looks_like_short_title_after_author_prefix(clean_title)
        or _looks_like_chinese_title_segment(clean_title)
    )


def _looks_like_biography_prose(text: str) -> bool:
    if not re.search(r"[\u4e00-\u9fff]", text):
        return False
    prose_markers = (
        "教授主要从事",
        "主要从事",
        "此外",
        "业绩突出",
        "产生了显著",
        "发表SCI收录论文",
    )
    return any(marker in text for marker in prose_markers)


def _extract_source_anchor(tag: Tag, page_url: str) -> str | None:
    for anchor in tag.find_all("a", href=True):
        href = anchor["href"].strip()
        if "doi.org" in href or "arxiv.org" in href:
            return urljoin(page_url, href)
    return None


def _extract_pdf_url(tag: Tag, page_url: str) -> str | None:
    for anchor in tag.find_all("a", href=True):
        href = anchor["href"].strip()
        if _looks_like_pdf_href(href):
            return urljoin(page_url, href)
    return None


def _looks_like_pdf_href(href: str) -> bool:
    if not href:
        return False
    path = urlparse(href).path.casefold()
    return path.endswith(".pdf")


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
    if not normalized:
        return False

    is_exact_heading = _PUBLICATIONS_HEADING_RE.fullmatch(normalized) is not None
    is_descriptive_heading = _is_descriptive_publications_heading_text(text)
    if not is_exact_heading and not is_descriptive_heading:
        return False

    return (
        _has_strong_or_b_marker(tag)
        or _has_title_class(tag)
        or is_descriptive_heading
        or len(normalized) <= 30
    )


def _is_descriptive_publications_heading_text(text: str) -> bool:
    normalized = _strip_heading_trailing_punctuation(text)
    if not normalized or len(normalized) > 80:
        return False
    if not _is_publications_heading_text(normalized):
        return False
    if re.search(r"(?:发表论文|论文)\s*\d+\s*余|主持|服务产业", normalized):
        return False
    return bool(
        re.search(
            r"\bselected\s+(?:journal\s+)?papers\b",
            normalized,
            re.IGNORECASE,
        )
        or re.search(r"(?:主要|代表性|代表|精选).{0,20}(?:论文|文章|论著)", normalized)
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
