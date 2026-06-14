from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_SUB_TAG_RE = re.compile(r"<sub\b[^>]*>(.*?)</sub>", re.IGNORECASE | re.DOTALL)
_SUP_TAG_RE = re.compile(r"<sup\b[^>]*>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_MATH_BLOCK_RE = re.compile(
    r"<(?P<tag>(?:[A-Za-z0-9_]+:)?math)\b.*?</(?P=tag)>", re.IGNORECASE | re.DOTALL
)
_CONTROL_RE = re.compile(r"[\u200b-\u200f\ufeff]")
_FORMULA_SEQUENCE_RE = re.compile(
    r"\b(?:[A-Za-z\u0370-\u03FF]{1,4}|\d{1,3})(?:\s+(?:[A-Za-z\u0370-\u03FF]{1,4}|\d{1,3})){2,5}\b"
)
_FORMULA_DIGIT_SUFFIX_RE = re.compile(
    r"\b([A-Za-z\u0370-\u03FF0-9-]*\d[A-Za-z\u0370-\u03FF0-9-]*)\s+(\d{1,3})\b"
)
_LEADING_LATEX_ESCAPE_RE = re.compile(r"^\\(?=[A-Z])")
_COMMON_GLYPH_LOSS_WORDS = {
    "_eld": "field",
    "_elds": "fields",
    "arti_cial": "artificial",
    "classi_cation": "classification",
    "e_ciency": "efficiency",
    "e_cient": "efficient",
    "identi_cation": "identification",
    "signi_cant": "significant",
    "speci_c": "specific",
    "veri_cation": "verification",
}
_COMMON_GLYPH_LOSS_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(token) for token in _COMMON_GLYPH_LOSS_WORDS)
    + r")\b"
)
_WESTERN_NAME_WORD = r"[A-Z][A-Za-z.'’:-]+(?:-[A-Z][A-Za-z.'’:-]+)?"
_WESTERN_AUTHOR_NAME = rf"{_WESTERN_NAME_WORD}\s+{_WESTERN_NAME_WORD}\s*#?"
_TRAILING_AUTHOR_CODE_RE = re.compile(
    rf"^(?P<title>.{{20,}}?)\s+"
    rf"(?P<authors>{_WESTERN_AUTHOR_NAME}(?:\s*,\s*{_WESTERN_AUTHOR_NAME})+"
    r"\s*&\s*Code)$"
)
_LEADING_AUTHOR_QUOTED_TITLE_RE = re.compile(
    rf"^(?P<authors>{_WESTERN_AUTHOR_NAME}(?:\s*,\s*{_WESTERN_AUTHOR_NAME}){{1,8}})"
    r"\s*,\s*[\"“](?P<title>.{20,}?)[\"”]\s*(?:,\s*.{2,120})?$",
    re.IGNORECASE,
)
_TRAILING_AUTHOR_METADATA_TAIL_RE = re.compile(
    rf"^(?P<title>.{{30,}}),\s*"
    rf"(?P<authors>{_WESTERN_AUTHOR_NAME}(?:\s*,\s*{_WESTERN_AUTHOR_NAME}){{1,8}})"
    r"\s*,\s*(?:Proc\.\s+VLDB\s+Endow\.?|VLDB)\s*\.?\s*$",
    re.IGNORECASE,
)
_TRAILING_GENERIC_METADATA_TAIL_RE = re.compile(
    r"^(?P<title>.{20,}?)(?:"
    r"[.。]\s*Proc\.\s+VLDB\s+Endow\.?"
    r"|[,，]\s*VLDB\.?"
    r"|[,，]\s*no\.?\s*\d+\s*,\s*pp\.?(?:\s*[\d–—-]+)?"
    r"|[,，]\s*vol\.?\s*\d+(?:\s*[,，]\s*no\.?\s*\d+)?"
    r"(?:\s*[,，]\s*pp\.?\s*[\d–—-]+)?"
    r"|\s*[\(（]\s*IF\s*[:=]\s*\d+(?:\.\d+)?\s*[\)）]"
    r")$",
    re.IGNORECASE,
)
_KNOWN_TRAILING_VENUES = (
    "Applied Catalysis B: Environmental",
    "Computers and Fluids",
    "RSC Adv",
)
_KNOWN_PERIOD_TRAILING_VENUES = {
    "annals of applied statistics",
    "actuators",
    "bmc biology",
    "cities",
    "weather and forecasting",
}
_KNOWN_COMMA_TRAILING_VENUES = {
    "communications in computational physics",
    "geografiska annaler: series b, human geography",
}
_KNOWN_SHORT_TRAILING_VENUE_SUFFIXES = (
    "Light, Sci",
    "Commun",
    "PNAS",
    "Nat",
    "Sci",
)
_KNOWN_ACRONYM_YEAR_VENUES = (
    "NAACL-HLT",
    "EMNLP-IJCNLP",
)
_LEADING_ETC_PREFIX_RE = re.compile(r"^etc(?:\.|\s+)\s*(?=[A-Z])", re.IGNORECASE)
_LEADING_CJK_AUTHOR_ROLE_RE = re.compile(
    r"^(?:第[一二三四五六七八九十]+作者|共同第[一二三四五六七八九十]+作者|"
    r"(?:通讯|通信)作者|共同(?:通讯|通信)作者|同等贡献)"
    r"\s*[，,、:：]\s*"
)
_LEADING_SINGLE_AUTHOR_ARTICLE_TITLE_RE = re.compile(
    r"^(?P<author>[A-Z][a-zA-Z'’.-]{2,24})\s+"
    r"(?P<title>(?:A|An|The)\s+\S.{20,})$"
)
_LEADING_SINGLE_AUTHOR_HYPHEN_TITLE_RE = re.compile(
    r"^(?P<author>[A-Z][A-Za-z'’.]{2,24})\s+"
    r"(?P<title>[A-Z][A-Za-z0-9]+[-‐‑‒–—][A-Za-z0-9]+(?:\s+\S+){4,})$"
)
_LEADING_AUTHOR_AND_INITIAL_AUTHOR_TITLE_RE = re.compile(
    r"^(?P<authors>[A-Z][A-Za-z'’.]{2,24}\s+and\s+"
    r"(?:[A-Z]\.\s*){1,3}[A-Z][A-Za-z'’.-]{2,24})\s+"
    r"(?P<title>\S.{20,})$"
)
_LEADING_WITH_AUTHOR_NOTE_RE = re.compile(
    r"^\(with\s+[^)]{3,120}\)\s*(?P<title>.{20,})$",
    re.IGNORECASE,
)
_TRAILING_IN_VENUE_DOWNLOAD_RE = re.compile(
    r"^(?P<title>.{20,}?)"
    r"(?:[.。]\s+|[,，]\s*)In\s+(?:the\s+)?"
    r"(?P<venue>.{8,180}?(?:Conference|Meeting|Workshop|Symposium|"
    r"Transportation\s+Research\s+Board).*)"
    r"(?:\.\s*\[[^\]]+\])?\s*$",
    re.IGNORECASE,
)
_TRAILING_CONFERENCE_COAUTHOR_RE = re.compile(
    r"^(?P<title>.{20,}?)\s+"
    r"\d+(?:st|nd|rd|th)\s+"
    r"(?P<venue>(?:"
    r"(?:Conference|Meeting|Workshop|Symposium)\b"
    r"[A-Za-z0-9&/ .,'’():-]*"
    r"|[A-Z][A-Za-z0-9&/ .,'’():-]{3,180}?"
    r"(?:Conference|Meeting|Workshop|Symposium)"
    r"[A-Za-z0-9&/ .,'’():-]*"
    r"))\s+"
    r"(?i:Coauthors?)\s*:\s*.+$",
)
_TRAILING_DOI_METADATA_RE = re.compile(
    r"^(?P<title>.{20,}?)\.\s+"
    r"(?P<venue>[A-Z][A-Z0-9 &/().:-]{2,80})\.\s+"
    r"DOI\s*:?\s*10\.\S+$",
    re.IGNORECASE,
)
_TRAILING_PROCEEDINGS_VENUE_RE = re.compile(
    r"^(?P<title>.{20,}?)"
    r"(?:[.。]\s+|[,，]\s*|\s+In\s+)"
    r"(?:Proceedings\s+of\s+(?:the\s+)?)?"
    r"(?:19|20)\d{2}\s+Conference\s+(?:of|on)\s+.{10,}$",
    re.IGNORECASE,
)
_TRAILING_ACRONYM_YEAR_VENUE_RE = re.compile(
    rf"^(?P<title>.{{20,}}?)\s+"
    rf"(?:{'|'.join(re.escape(venue) for venue in _KNOWN_ACRONYM_YEAR_VENUES)})"
    r"\s+(?:19|20)\d{2}$"
)
_TRAILING_JOURNAL_VOLUME_TAIL_RE = re.compile(
    r"^(?P<title>.{20,}?)[\"'“”’]?\s*,\s*"
    r"(?P<venue>[A-Z][A-Za-z&().:'’ -]{2,120})\s*,\s*Vol\.?$",
    re.IGNORECASE,
)
_TRAILING_KNOWN_JOURNAL_CITATION_TAIL_RE = re.compile(
    r"^(?P<title>.{20,}?)(?:[.。]\s+|[,，]\s*)"
    r"(?P<venue>BMC\s+bioinformatics|J\.\s+d[’']Analyse\s+Math|Comm)"
    r"(?:\s*,\s*\d+\s*,\s*[\d–—-]+)?$",
    re.IGNORECASE,
)
_TRAILING_C_OL_CITATION_RE = re.compile(
    r"^(?P<title>.{20,}?)\s*\[C/OL\]//.{8,}$",
    re.IGNORECASE,
)
_TRAILING_DASH_VENUE_LINKS_RE = re.compile(
    r"^(?P<title>.{20,}?)\s*[—–-]\s*"
    r"(?:Bioinformatics)\s*,\s*(?:19|20)\d{2}"
    r"(?:\s*\[[^\]]+\])+\s*$",
    re.IGNORECASE,
)
_TRAILING_WITH_AUTHORS_RE = re.compile(
    r"^(?P<title>.{20,}?)[\"'“”’]?\s*,\s*with\s+"
    r"[A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){0,4}"
    r"(?:\s+and\s+[A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){0,4})?\s*$",
    re.IGNORECASE,
)
_TRAILING_QUOTE_ABBREV_VENUE_RE = re.compile(
    r"^(?P<title>.{20,}?)[\"'“”’]\s+J\.\s+Am\.?$",
    re.IGNORECASE,
)
_TRAILING_ORPHAN_ARTICLE_RE = re.compile(
    r"^(?P<title>.{20,}?)\s+(?:The|A|An)$"
)
_CAPITALIZED_NAME_TOKEN = r"[A-Z][A-Za-z'’.-]{1,30}"
_TRAILING_AUTHOR_NAME_TAIL_RE = re.compile(
    rf"^(?P<title>.{{30,}}?)\s+"
    rf"(?P<authors>{_CAPITALIZED_NAME_TOKEN}\s+{_CAPITALIZED_NAME_TOKEN}"
    rf"(?:\s*[,，]\s*[*#†‡§]*\s*"
    rf"{_CAPITALIZED_NAME_TOKEN}\s+{_CAPITALIZED_NAME_TOKEN})*"
    r"\s*[*#†‡§]*)$"
)
_COMMON_ROMANIZED_NAME_TOKENS = {
    "bai",
    "cao",
    "chen",
    "cheng",
    "ding",
    "guo",
    "he",
    "hong",
    "huang",
    "jun",
    "kai",
    "li",
    "lin",
    "liu",
    "lu",
    "luo",
    "ma",
    "ming",
    "mo",
    "qian",
    "qin",
    "shi",
    "su",
    "sun",
    "wang",
    "wei",
    "wen",
    "wu",
    "xiao",
    "xie",
    "xu",
    "yang",
    "yao",
    "yong",
    "zhang",
    "zhao",
    "zheng",
    "zhou",
    "zhu",
}
_TECHNICAL_LEADING_WORDS = {
    "sparse",
}


def clean_paper_title(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _MATH_BLOCK_RE.sub(_replace_math_block, text)
    text = _SUB_TAG_RE.sub(lambda match: _clean_inline_fragment(match.group(1)), text)
    text = _SUP_TAG_RE.sub(lambda match: _clean_inline_fragment(match.group(1)), text)
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = _CONTROL_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([(/])\s+", r"\1", text)
    text = re.sub(r"\s+([)])", r"\1", text)
    text = _compact_formula_spacing(text)
    text = _repair_common_glyph_loss_words(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def clean_reference_like_paper_title(value: str | None) -> str:
    """Clean titles extracted from publication/reference-like homepage text."""
    text = clean_paper_title(value)
    text = _extract_quoted_title_from_author_record(text)
    text = _strip_leading_reference_prefix(text)
    text = _strip_leading_with_author_note(text)
    text = _strip_trailing_author_code_links(text)
    text = _strip_trailing_author_metadata_tail(text)
    text = _strip_known_trailing_venue(text)
    text = _strip_trailing_author_name_tail(text)
    text = _strip_trailing_venue_download_tail(text)
    text = _strip_trailing_doi_metadata_tail(text)
    text = _strip_trailing_proceedings_venue(text)
    text = _strip_trailing_acronym_year_venue(text)
    text = _strip_trailing_journal_volume_tail(text)
    text = _strip_trailing_known_journal_citation_tail(text)
    text = _strip_trailing_c_ol_citation_tail(text)
    text = _strip_trailing_dash_venue_links(text)
    text = _strip_trailing_with_authors(text)
    text = _strip_trailing_quote_abbrev_venue(text)
    text = _strip_short_trailing_venue_suffix(text)
    text = _strip_trailing_author_name_tail(text)
    text = _strip_known_period_trailing_venue(text)
    text = _strip_known_comma_trailing_venue(text)
    text = _strip_trailing_conference_coauthor_tail(text)
    text = _strip_trailing_orphan_article(text)
    text = _strip_generic_metadata_tail(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _clean_inline_fragment(fragment: str) -> str:
    text = html.unescape(fragment or "")
    text = _TAG_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return _WHITESPACE_RE.sub("", text)


def _repair_common_glyph_loss_words(text: str) -> str:
    text = _LEADING_LATEX_ESCAPE_RE.sub("", text)
    return _COMMON_GLYPH_LOSS_RE.sub(
        lambda match: _COMMON_GLYPH_LOSS_WORDS[match.group(0)],
        text,
    )


def _strip_trailing_author_code_links(text: str) -> str:
    match = _TRAILING_AUTHOR_CODE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,;.")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _extract_quoted_title_from_author_record(text: str) -> str:
    match = _LEADING_AUTHOR_QUOTED_TITLE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_author_metadata_tail(text: str) -> str:
    match = _TRAILING_AUTHOR_METADATA_TAIL_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_leading_reference_prefix(text: str) -> str:
    text = _LEADING_ETC_PREFIX_RE.sub("", text).strip()
    text = _LEADING_CJK_AUTHOR_ROLE_RE.sub("", text).strip()
    match = _LEADING_AUTHOR_AND_INITIAL_AUTHOR_TITLE_RE.match(text)
    if match:
        candidate = match.group("title").strip()
        if _has_title_candidate_shape(candidate):
            return candidate
    match = _LEADING_SINGLE_AUTHOR_ARTICLE_TITLE_RE.match(text)
    if match:
        candidate = match.group("title").strip()
        if _has_title_candidate_shape(candidate) and _looks_like_leading_author_token(
            match.group("author")
        ):
            return candidate
    match = _LEADING_SINGLE_AUTHOR_HYPHEN_TITLE_RE.match(text)
    if match:
        candidate = match.group("title").strip()
        if _has_title_candidate_shape(candidate) and _looks_like_leading_author_token(
            match.group("author")
        ):
            return candidate
    return text


def _looks_like_leading_author_token(text: str) -> bool:
    return text.casefold() not in _TECHNICAL_LEADING_WORDS


def _strip_leading_with_author_note(text: str) -> str:
    match = _LEADING_WITH_AUTHOR_NOTE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_known_trailing_venue(text: str) -> str:
    for venue in _KNOWN_TRAILING_VENUES:
        suffix = f" {venue}"
        if not text.casefold().endswith(suffix.casefold()):
            continue
        candidate = text[: -len(suffix)].strip(" ,;.")
        if _has_title_candidate_shape(candidate):
            return candidate
    return text


def _strip_trailing_author_name_tail(text: str) -> str:
    match = _TRAILING_AUTHOR_NAME_TAIL_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    authors = match.group("authors")
    if not _has_title_candidate_shape(candidate):
        return text
    if not _looks_like_romanized_author_tail(authors):
        return text
    return candidate


def _looks_like_romanized_author_tail(text: str) -> bool:
    cleaned = re.sub(r"[*#†‡§,，]", " ", text)
    tokens = [token.casefold() for token in cleaned.split() if token.strip()]
    if len(tokens) < 2 or len(tokens) % 2 != 0 or len(tokens) > 8:
        return False
    return all(token in _COMMON_ROMANIZED_NAME_TOKENS for token in tokens)


def _strip_trailing_orphan_article(text: str) -> str:
    match = _TRAILING_ORPHAN_ARTICLE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_venue_download_tail(text: str) -> str:
    match = _TRAILING_IN_VENUE_DOWNLOAD_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_conference_coauthor_tail(text: str) -> str:
    match = _TRAILING_CONFERENCE_COAUTHOR_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_doi_metadata_tail(text: str) -> str:
    match = _TRAILING_DOI_METADATA_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_proceedings_venue(text: str) -> str:
    match = _TRAILING_PROCEEDINGS_VENUE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_acronym_year_venue(text: str) -> str:
    match = _TRAILING_ACRONYM_YEAR_VENUE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_journal_volume_tail(text: str) -> str:
    match = _TRAILING_JOURNAL_VOLUME_TAIL_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_known_journal_citation_tail(text: str) -> str:
    match = _TRAILING_KNOWN_JOURNAL_CITATION_TAIL_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_c_ol_citation_tail(text: str) -> str:
    match = _TRAILING_C_OL_CITATION_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_dash_venue_links(text: str) -> str:
    match = _TRAILING_DASH_VENUE_LINKS_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_with_authors(text: str) -> str:
    match = _TRAILING_WITH_AUTHORS_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_trailing_quote_abbrev_venue(text: str) -> str:
    match = _TRAILING_QUOTE_ABBREV_VENUE_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_short_trailing_venue_suffix(text: str) -> str:
    stripped = text.rstrip()
    lowered = stripped.casefold()
    for suffix in _KNOWN_SHORT_TRAILING_VENUE_SUFFIXES:
        for marker in (f" {suffix}", f", {suffix}", f". {suffix}"):
            if not lowered.endswith(marker.casefold()):
                continue
            candidate = stripped[: -len(marker)].strip(" ,.;。\"'“”’")
            if _has_title_candidate_shape(candidate):
                return candidate
    return text


def _strip_known_period_trailing_venue(text: str) -> str:
    if ". " not in text:
        return text
    candidate, suffix = text.rsplit(". ", 1)
    if suffix.strip().casefold() not in _KNOWN_PERIOD_TRAILING_VENUES:
        return text
    candidate = candidate.strip(" ,.;。")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _strip_known_comma_trailing_venue(text: str) -> str:
    for venue in _KNOWN_COMMA_TRAILING_VENUES:
        suffix = f", {venue}"
        if not text.casefold().endswith(suffix):
            continue
        candidate = text[: -len(suffix)].strip(" ,.;。")
        if _has_title_candidate_shape(candidate):
            return candidate
    return text


def _strip_generic_metadata_tail(text: str) -> str:
    match = _TRAILING_GENERIC_METADATA_TAIL_RE.match(text)
    if not match:
        return text
    candidate = match.group("title").strip(" ,.;。\"'“”’")
    if not _has_title_candidate_shape(candidate):
        return text
    return candidate


def _has_title_candidate_shape(text: str) -> bool:
    return len(text) >= 20 and " " in text


def _replace_math_block(match: re.Match[str]) -> str:
    fragment = match.group(0)
    rendered = _render_mathml_fragment(fragment)
    if rendered:
        return rendered
    fallback = _TAG_RE.sub(" ", fragment)
    fallback = html.unescape(fallback)
    return _WHITESPACE_RE.sub(" ", fallback).strip()


def _render_mathml_fragment(fragment: str) -> str:
    try:
        root = ET.fromstring(fragment)
    except ET.ParseError:
        return ""
    rendered = _render_mathml_node(root)
    rendered = html.unescape(rendered)
    rendered = _CONTROL_RE.sub("", rendered)
    rendered = _WHITESPACE_RE.sub(" ", rendered).strip()
    rendered = re.sub(r"\s*/\s*", "/", rendered)
    return rendered


def _render_mathml_node(node: ET.Element) -> str:
    tag = _local_name(node.tag)
    children = list(node)

    if tag == "mfrac":
        numerator = _render_mathml_node(children[0]) if len(children) > 0 else ""
        denominator = _render_mathml_node(children[1]) if len(children) > 1 else ""
        return f"{numerator}/{denominator}".strip("/")

    if tag in {"msub", "msup", "msubsup", "msqrt", "mroot"}:
        rendered_children = "".join(_render_mathml_node(child) for child in children)
        return f"{(node.text or '')}{rendered_children}"

    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in children:
        parts.append(_render_mathml_node(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1].casefold()
    if ":" in tag:
        return tag.rsplit(":", 1)[-1].casefold()
    return tag.casefold()


def _compact_formula_spacing(text: str) -> str:
    previous = None
    while text != previous:
        previous = text
        text = _FORMULA_SEQUENCE_RE.sub(_replace_formula_sequence, text)
        text = _FORMULA_DIGIT_SUFFIX_RE.sub(r"\1\2", text)
    return text


def _replace_formula_sequence(match: re.Match[str]) -> str:
    tokens = match.group(0).split()
    if not _looks_like_formula_sequence(tokens):
        return match.group(0)
    return "".join(tokens)


def _looks_like_formula_sequence(tokens: list[str]) -> bool:
    if len(tokens) < 3 or not any(token.isdigit() for token in tokens):
        return False
    for token in tokens:
        if token.isdigit():
            continue
        if len(token) > 4 or not re.fullmatch(r"[A-Za-z\u0370-\u03FF]+", token):
            return False
        if token.islower() and len(token) > 1:
            return False
    return True
