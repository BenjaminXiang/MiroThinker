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
_LLM_PUBLICATION_FALLBACK_MAX_RULE_PUBLICATIONS = 80
_SHORT_SINGLE_WORD_JOURNAL_TITLES = frozenset({"joule"})

_ITEM_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[\[【]\s*\d+(?:\s+\d+)*\s*[\]】]\s*(?:[.)、．。])?"
    r"|\(\s*\d+\s*\)\s*(?:[.)、．。])?"
    r"|\d+\s*(?:[.)、．。）]|[-‐‑‒–—])"
    r"|[•‣▪◦◆·]"
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
_LEADING_AUTHOR_ROLE_PREFIX_RE = re.compile(
    r"^\s*[\(（]\s*"
    r"(?:corresponding|co[-\s]*first|first|equal|共同|通讯|第一).{0,40}?"
    r"author[s]?"
    r"\s*[\)）]\s*[,，;；]?\s*",
    re.IGNORECASE,
)
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
    r"\b(?:transactions?|journal|proceedings?|conference|conf|congress|symposium|workshop|letters|"
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
_PARENTHESIZED_AUTHOR_MARKER_RE = re.compile(
    r"\(\s*[*#†‡+]*\s*(?:同等贡献作者|同等贡献|共同第一作者|共同通讯作者|"
    r"通讯作者|通信作者|第一作者|co-?first\s+authors?|equal\s+contribution|"
    r"corresponding\s+authors?)?\s*\)",
    re.IGNORECASE,
)
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
    r"学生|corresponding\s+authors?|co-?first\s+authors?|equal\s+contribution)\s*[）)]",
    re.IGNORECASE,
)
_TRAILING_WITH_AUTHORS_NOTE_RE = re.compile(
    r"\s*[\(（]\s*with\s+[^()（）]{3,160}[\)）]\s*$",
    re.IGNORECASE,
)
_LEADING_CHINESE_AUTHOR_NOTE_FRAGMENT_RE = re.compile(
    r"^\s*(?:[*#†‡+&,\s，,;；、]*(?:[（(]\s*)?"
    r"(?:同等贡献作者|同等贡献|共同第一作者|共同通讯作者|通讯作者|通信作者|第一作者)"
    r"\s*[）)]\s*[,，;；、]*)+"
)
_AUTHOR_NOTE_ONLY_RE = re.compile(
    r"^[（(][^）)]*(?:第一|共同|通讯|通信|作者|corresponding|contribution)[^）)]*[）)]$",
    re.IGNORECASE,
)
_ET_AL_SUFFIX_RE = re.compile(
    r"\s+et\s+a(?:l\.?|[;/]+)\s*/?$", re.IGNORECASE
)
_ETC_AUTHOR_SUFFIX_RE = re.compile(r"\s+etc\.?\s*$", re.IGNORECASE)
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
_PUBLICATION_STATUS_VENUE_TAIL_RE = re.compile(
    r"^(?:in\s+press\b|accepted\s+(?:to|by|for)\b|to\s+appear\b)",
    re.IGNORECASE,
)
_IF_CITATIONS_METADATA_RE = re.compile(
    r"\bIF\s*/\s*citations?\s*:",
    re.IGNORECASE,
)
_PUBLICATION_METRIC_METADATA_RE = re.compile(
    r"(?:"
    r"\bIF\s*[=:：]?\s*\d"
    r"|\bJCR\b\s*(?:Q\s*[1-4]|\d\s*区)?"
    r"|中科院\s*\d+\s*区"
    r")",
    re.IGNORECASE,
)
_DOI_ONLY_METADATA_TITLE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*)?"
    r"(?:DOI\s*[:：]\s*)?10\.\d{4,9}/\S+"
    r"(?:\s*[.。]?\s*[\(（][^()（）]*(?:IF|JCR|中科院)[^()（）]*[\)）])?\s*$",
    re.IGNORECASE,
)
_VOLUME_PAGE_DOI_FRAGMENT_RE = re.compile(
    r"^\d{1,5}\s*[,，]\s*\d{1,6}\s*\.?\s*\[?\s*doi\s*\]?$",
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
_PUBLICATION_LIST_POINTER_RE = re.compile(
    r"\b(?:complete\s+publication\s+list|publication\s+list|please\s+refer\s+to)\b",
    re.IGNORECASE,
)
_INDEX_ONLY_RE = re.compile(
    r"^(?:"
    r"wos|web\s+of\s+science|ei(?:\s+accession\s+number)?|scopus|"
    r"pubmed|pmid|doi|orcid"
    r")\s*[:：]?\s*[\w./:-]+$",
    re.IGNORECASE,
)
_INDEX_METADATA_IN_TEXT_RE = re.compile(
    r"\b(?:wos|web\s+of\s+science|ei\s+accession\s+number|scopus|pubmed|pmid|orcid)"
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
    r"(?:发表\s*(?:专业)?\s*(?:sci|ei)?\s*(?:收录)?\s*论文|"
    r"论文\s*\d+\s*[多余]?\s*篇|引用\s*\d+\s*[万千]?\s*余?次|"
    r"授权\s*专利|专利\s*授权|申请\s*专利|成果转化|"
    r"荣誉|被引|影响因子|"
    r"(?:老师|教授)?长期从事|主要从事|研究工作|应用领域包括|着重研究|"
    r"年薪|住房补贴|孔雀计划|五险一金|餐补|过节费|免费体检|"
    r"应聘|申请材料|个人简历|推荐人|联系方式|"
    r"独立申请课题|证明个人水平和能力|招聘要求|岗位要求|"
    r"博士学位|高度责任心|英语写作|报告能力|博士后待遇|福利待遇|"
    r"\b(?:selected\s+publications?|selected\s+publication|"
    r"published\s+more\s+than\s+\d+\s+papers?|"
    r"papers?\s+have\s+been\s+cited|h\s+index|google\s+scholar)\b)",
    re.IGNORECASE,
)
_NON_PUBLICATION_REPORTING_FRAGMENT_RE = re.compile(
    r"^(?:[a-z]\s+)?research\s+highlight\b|^reported\s+by\b",
    re.IGNORECASE,
)
_AWARD_HONOR_TITLE_RE = re.compile(
    r"(?:"
    r"\b(?:award|fellowship|postdoc|poster|oral\s+presentation|"
    r"young\s+investigator|travel\s+award|presidential\s+award)\b|"
    r"奖学金|优秀毕业|优秀研究生|十佳毕业生|院长奖|优秀奖|三等奖|二等奖|一等奖|"
    r"论坛|博士后基金|自然科学基金|国自然|科创委|青年学生基础研究项目|"
    r"候选人|优秀博士生"
    r")",
    re.IGNORECASE,
)
_CITATION_METRIC_ONLY_RE = re.compile(
    r"^(?:他引次数|引用次数|被引次数|总引用|h\s*index)\b",
    re.IGNORECASE,
)
_CONTRIBUTION_LEGEND_ONLY_RE = re.compile(
    r"^(?:[*#†‡+&,\s]*(?:corresponding\s+author|"
    r"student\s+under\s+my\s+supervision|"
    r"first/co-?first\s+authors?|co-?first\s+authors?|"
    r"corresponding/co-?corresponding\s+authors?|"
    r"co-?corresponding\s+authors?|corresponding\s+authors?|"
    r"equal\s+contributions?)"
    r"[\s,;，；]*)+$",
    re.IGNORECASE,
)
_CHINESE_CONTRIBUTION_LEGEND_ONLY_RE = re.compile(
    r"^(?:[*#†‡+&,\s，,;；、]*(?:本人指导的)?"
    r"(?:研究生|本科生|博士生|硕士生|学生|共同第一作者|"
    r"共同通讯作者|通讯作者|通信作者|第一作者|同等贡献)"
    r"[\s，,;；、]*)+$"
)
_LOWERCASE_CONTINUATION_TITLE_RE = re.compile(
    r"^(?:from|for|with|under|based)\b"
)
_MONTH_NAME_RE = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)$",
    re.IGNORECASE,
)
_LEADING_YEAR_MONTH_TITLE_PREFIX_RE = re.compile(
    r"^\s*(?:19|20)\d{2}\s*[,，]\s*"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+",
    re.IGNORECASE,
)
_LEADING_MONTH_TITLE_PREFIX_RE = re.compile(
    r"^\s*[,，]?\s*"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+",
    re.IGNORECASE,
)
_LEADING_CITATION_YEAR_TITLE_PREFIX_RE = re.compile(
    r"^\s*(?:19|20)\d{2}\s*[,，.]\s+"
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
_SINGLE_AUTHOR_TOKEN_EXCLUSIONS = frozenset(
    {
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
        "under",
        "with",
    }
)
_COMMON_SPLIT_TITLE_WORD_REPAIRS = frozenset(
    {
        "analysis",
        "batteries",
        "basis",
        "binary",
        "bottles",
        "bound",
        "codoped",
        "codes",
        "constant",
        "constructions",
        "dimensional",
        "distribution",
        "doped",
        "drinking",
        "error",
        "flow",
        "geometry",
        "graphene",
        "guarantee",
        "iron",
        "life",
        "lightweight",
        "lower",
        "matrices",
        "mechanism",
        "measurement",
        "meeting",
        "metal",
        "nitrogen",
        "old",
        "oxidation",
        "pipe",
        "probability",
        "pursuit",
        "release",
        "sponge",
        "surfaces",
        "sulphides",
        "sulphur",
        "surface",
        "systems",
        "the",
        "three",
        "three-dimensional",
        "undetected",
        "velocity",
        "water",
        "weight",
        "wine",
    }
)
_CHINESE_AUTHOR_SEGMENT_RE = re.compile(
    r"^[\u4e00-\u9fff](?:\s*[\u4e00-\u9fff]){1,3}\s*[*#†‡]?$"
)
_CHINESE_ET_AL_SUFFIX_RE = re.compile(r"\s*等\s*$")
_COMMON_CHINESE_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平"
    "黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋庞熊纪舒屈项祝董"
    "梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田胡凌"
    "霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚"
    "程邢裴陆荣翁荀羊於惠甄曲家封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗"
    "山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶"
    "幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双"
    "闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀浦尚农"
    "温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满"
    "弘匡国文寇广禄阙东殴沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶"
    "空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
_COMMON_TWO_CHAR_CHINESE_SURNAMES = frozenset(
    {
        "欧阳",
        "司马",
        "诸葛",
        "上官",
        "东方",
        "夏侯",
        "司徒",
        "司空",
        "尉迟",
        "公孙",
        "慕容",
        "南宫",
        "闻人",
        "皇甫",
        "令狐",
        "宇文",
        "长孙",
    }
)
_CHINESE_VENUE_HINT_RE = re.compile(
    r"(?:学报|期刊|杂志|会议|评论|报|刊|给水排水|系统自动化)"
)
_CONCATENATED_AUTHOR_NAME_RE = re.compile(r"^[A-Z][a-z]{1,24}[A-Z][a-z]{1,24}$")
_HEADING_TAG_NAMES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_NON_HEADING_SECTION_TAG_NAMES = ("p", "div")
_GENERAL_PUBLICATIONS_HEADING_TEXTS = frozenset({"学术成果"})
_RESEARCH_PUBLICATION_HEADING_TEXTS = frozenset({"research"})
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


@dataclass(frozen=True, slots=True)
class _ParagraphPublicationText:
    text: str
    source_anchor: str | None
    pdf_url: str | None


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
    first_segment = _clean_segment(re.split(r"[,，;；.。．]", text, maxsplit=1)[0])
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


def _strip_leading_author_role_prefix(text: str) -> str:
    return _LEADING_AUTHOR_ROLE_PREFIX_RE.sub("", text).strip()


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
            _strip_leading_author_role_prefix(
                _strip_leading_publication_tags(_strip_item_prefix(text))
            )
        )
    )
    if not normalized:
        return "", None, None
    normalized = _strip_parenthesized_author_markers(normalized)

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

    if _QUOTED_TITLE_RE.search(normalized):
        quoted_author_prefix = _split_marked_author_prefix(normalized)
        if quoted_author_prefix is not None:
            title, authors, venue = quoted_author_prefix
            title, venue = _split_question_title_venue_tail(title, venue)
            if (
                not _title_result_needs_author_prefix_fallback(title)
                and not _is_non_publication_title_noise(title)
            ):
                return title, authors, venue

    quoted = _extract_quoted_title_segment(normalized)
    if quoted is not None:
        return quoted

    unclosed_quote_author_prefix = _split_unclosed_quote_author_prefix(normalized)
    if unclosed_quote_author_prefix is not None:
        return unclosed_quote_author_prefix

    connective_period_prefix = _split_connective_full_name_period_title_prefix(
        normalized
    )
    if connective_period_prefix is not None:
        return connective_period_prefix

    comma_delimited = _split_comma_delimited_citation(normalized)
    if comma_delimited is not None:
        if (
            not _title_result_needs_author_prefix_fallback(comma_delimited[0])
            and not _is_non_publication_title_noise(comma_delimited[0])
        ):
            return comma_delimited
        repaired = _repair_contaminated_title_result(comma_delimited)
        if (
            repaired is not None
            and not _is_non_publication_title_noise(repaired[0])
            and not _title_result_needs_author_prefix_fallback(repaired[0])
        ):
            return repaired

    if _IF_CITATIONS_METADATA_RE.search(normalized):
        comma_delimited = _split_comma_delimited_citation(normalized)
        if comma_delimited is not None:
            if (
                not _title_result_needs_author_prefix_fallback(comma_delimited[0])
                and not _is_non_publication_title_noise(comma_delimited[0])
            ):
                return comma_delimited
            repaired = _repair_contaminated_title_result(comma_delimited)
            if (
                repaired is not None
                and not _is_non_publication_title_noise(repaired[0])
                and not _title_result_needs_author_prefix_fallback(repaired[0])
            ):
                return repaired

    author_year_prefix = _split_author_year_prefix(normalized)
    if author_year_prefix is not None:
        return author_year_prefix

    surname_given_year_prefix = _split_surname_given_year_prefix(normalized)
    if surname_given_year_prefix is not None:
        return surname_given_year_prefix

    et_al_prefix = _split_et_al_author_prefix(normalized)
    if et_al_prefix is not None:
        return et_al_prefix

    single_marked_semicolon = _split_single_marked_author_semicolon_prefix(normalized)
    if single_marked_semicolon is not None:
        return single_marked_semicolon

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
        mixed = _prefer_mixed_author_prefix_result(normalized, marked_author)
        if mixed is not marked_author:
            return mixed
        return marked_author

    semicolon_period_authors = _split_semicolon_surname_author_period_prefix(
        normalized
    )
    if semicolon_period_authors is not None:
        if _standard_semicolon_period_title_is_clean(semicolon_period_authors[0]):
            return semicolon_period_authors
        repaired = _repair_contaminated_title_result(semicolon_period_authors)
        if repaired is not None:
            return repaired

    semicolon_surname_authors = _split_semicolon_surname_author_prefix(normalized)
    if semicolon_surname_authors is not None:
        repaired = _repair_contaminated_title_result(semicolon_surname_authors)
        if repaired is not None:
            return repaired
        if _result_title_needs_mixed_author_fallback(semicolon_surname_authors):
            loose_semicolon_authors = _split_loose_semicolon_author_chain_prefix(
                normalized
            )
            if loose_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(loose_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    loose_semicolon_authors
                ):
                    return loose_semicolon_authors
            mixed_semicolon_authors = _split_mixed_semicolon_author_prefix(normalized)
            if mixed_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(mixed_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    mixed_semicolon_authors
                ):
                    return mixed_semicolon_authors
        preferred = _prefer_mixed_semicolon_author_prefix_result(
            normalized,
            semicolon_surname_authors,
        )
        if preferred is not semicolon_surname_authors:
            return preferred
        return semicolon_surname_authors

    loose_semicolon_authors = _split_loose_semicolon_author_chain_prefix(normalized)
    if loose_semicolon_authors is not None:
        repaired = _repair_contaminated_title_result(loose_semicolon_authors)
        if repaired is not None:
            return repaired
        return loose_semicolon_authors

    semicolon_author_title = _split_semicolon_author_title_prefix(normalized)
    if semicolon_author_title is not None:
        repaired = _repair_contaminated_title_result(semicolon_author_title)
        if repaired is not None:
            return repaired
        if _result_title_needs_mixed_author_fallback(semicolon_author_title):
            loose_semicolon_authors = _split_loose_semicolon_author_chain_prefix(
                normalized
            )
            if loose_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(loose_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    loose_semicolon_authors
                ):
                    return loose_semicolon_authors
            mixed_semicolon_authors = _split_mixed_semicolon_author_prefix(normalized)
            if mixed_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(mixed_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    mixed_semicolon_authors
                ):
                    return mixed_semicolon_authors
        preferred = _prefer_mixed_semicolon_author_prefix_result(
            normalized,
            semicolon_author_title,
        )
        if preferred is not semicolon_author_title and not (
            _result_title_needs_mixed_author_fallback(preferred)
        ):
            return preferred
        if not _result_title_needs_mixed_author_fallback(semicolon_author_title):
            return semicolon_author_title

    semicolon_plain_authors = _split_semicolon_plain_author_prefix(normalized)
    if semicolon_plain_authors is not None:
        repaired = _repair_contaminated_title_result(semicolon_plain_authors)
        if repaired is not None:
            return repaired
        if _result_title_needs_mixed_author_fallback(semicolon_plain_authors):
            loose_semicolon_authors = _split_loose_semicolon_author_chain_prefix(
                normalized
            )
            if loose_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(loose_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    loose_semicolon_authors
                ):
                    return loose_semicolon_authors
            mixed_semicolon_authors = _split_mixed_semicolon_author_prefix(normalized)
            if mixed_semicolon_authors is not None:
                repaired = _repair_contaminated_title_result(mixed_semicolon_authors)
                if repaired is not None:
                    return repaired
                if not _result_title_needs_mixed_author_fallback(
                    mixed_semicolon_authors
                ):
                    return mixed_semicolon_authors
        preferred = _prefer_mixed_semicolon_author_prefix_result(
            normalized,
            semicolon_plain_authors,
        )
        if preferred is not semicolon_plain_authors:
            return preferred
        return semicolon_plain_authors

    mixed_semicolon_authors = _split_mixed_semicolon_author_prefix(normalized)
    if mixed_semicolon_authors is not None:
        repaired = _repair_contaminated_title_result(mixed_semicolon_authors)
        if repaired is not None:
            return repaired
        return mixed_semicolon_authors

    dense_comma_author_year = _split_dense_comma_author_year_prefix(normalized)
    if dense_comma_author_year is not None:
        return dense_comma_author_year

    comma_surname_authors = _split_comma_surname_author_prefix(normalized)
    if comma_surname_authors is not None:
        repaired = _repair_contaminated_title_result(comma_surname_authors)
        if repaired is not None:
            return repaired
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

    period_author_prefix = _split_pubmed_author_period_prefix(normalized)
    if period_author_prefix is not None:
        authors, title, venue = period_author_prefix
        return title, authors, venue

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
            preferred = _prefer_mixed_author_prefix_result(
                normalized,
                comma_delimited,
            )
            if preferred is not comma_delimited:
                return preferred
            repaired = _repair_contaminated_title_result(comma_delimited)
            if repaired is not None:
                return repaired
        preferred = _prefer_mixed_author_prefix_result(normalized, comma_delimited)
        if preferred is not comma_delimited:
            return preferred
        return comma_delimited

    leading_authors, trailing = _split_leading_authors(normalized)
    if leading_authors is not None:
        title, remainder = _split_title_and_remainder(trailing)
        if (
            _looks_like_publication_status_venue_tail(remainder)
            or _looks_like_venue(remainder)
            or _looks_like_journal_tail(remainder)
        ):
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

    if _looks_like_publication_status_venue_tail(remainder):
        return title, None, remainder

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
    if (
        not force_llm
        and len(rule_publications) > _LLM_PUBLICATION_FALLBACK_MAX_RULE_PUBLICATIONS
    ):
        return _filter_suspicious_rule_publications(rule_publications)

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
            r"(?:Adv|ACS\s+Appl|Anal|Angew|Chem|Commum|Commun|Mater|Funct|Today|Catal|Nat|Sci)\.?",
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
    if _PUBLICATION_LIST_POINTER_RE.search(normalized):
        return True
    if _INDEX_ONLY_RE.fullmatch(normalized):
        return True
    if _INDEX_METADATA_IN_TEXT_RE.search(normalized):
        return True
    if _DOI_ONLY_METADATA_TITLE_RE.fullmatch(normalized):
        return True
    if _VOLUME_PAGE_DOI_FRAGMENT_RE.fullmatch(normalized):
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
    if _looks_like_chinese_intro_english_venue_fragment(normalized):
        return True
    if _looks_like_publisher_date_fragment(normalized):
        return True
    if _looks_like_numeric_month_fragment(normalized):
        return True
    if _looks_like_venue_volume_page_only_title(normalized):
        return True
    if re.search(r"^\s*(?:et\s+a[;/l]?|et\s+al\.?)\b", normalized, re.IGNORECASE):
        return True
    if _looks_like_author_tail_venue_only_title(normalized):
        return True
    if _looks_like_lone_venue_title(normalized):
        return True
    if _IF_CITATIONS_METADATA_RE.search(normalized):
        return True
    if _RESIDUAL_CITATION_MARKER_RE.search(normalized):
        return True
    if _looks_like_author_venue_year_only_title(normalized):
        return True
    if _NON_PUBLICATION_PROSE_RE.search(normalized):
        return True
    if _NON_PUBLICATION_REPORTING_FRAGMENT_RE.search(normalized):
        return True
    if _AWARD_HONOR_TITLE_RE.search(normalized):
        return True
    if _CITATION_METRIC_ONLY_RE.search(normalized):
        return True
    if _CONTRIBUTION_LEGEND_ONLY_RE.search(normalized):
        return True
    if _CHINESE_CONTRIBUTION_LEGEND_ONLY_RE.fullmatch(normalized):
        return True
    if _LOWERCASE_CONTINUATION_TITLE_RE.search(normalized):
        return True
    if _looks_like_etc_author_only_title(normalized):
        return True
    if _looks_like_connective_romanized_chinese_author_title(normalized):
        return True
    if _looks_like_author_fragment_title(normalized):
        return True
    return _is_standalone_person_name_title(normalized)


def _looks_like_author_fragment_title(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized:
        return True
    if _looks_like_concatenated_author_name(normalized):
        return True
    if _looks_like_pubmed_author_segment(normalized):
        return True
    if re.fullmatch(
        rf"{_NAME_TOKEN_PATTERN}[*#†‡]?\s*[\(（](?:19|20)\d{{2}}[\)）]",
        normalized,
        flags=re.UNICODE,
    ):
        return True
    if re.fullmatch(
        rf"and{_NAME_TOKEN_PATTERN}(?:\s+[A-Z]\.?){{0,2}}"
        rf"(?:\s+{_NAME_TOKEN_PATTERN})?[*#†‡]*",
        normalized,
        flags=re.UNICODE,
    ):
        return True
    if _looks_like_mixed_case_author_fragment_title(normalized):
        return True
    return False


def _looks_like_mixed_case_author_fragment_title(title: str) -> bool:
    normalized = _AUTHOR_MARKER_RE.sub("", _clean_segment(title))
    if not re.search(r"[,，;；]|\band\b|&", normalized, flags=re.IGNORECASE):
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"\s*(?:[,，;；]|\band\b|&)\s*", normalized)
        if _clean_segment(part)
    ]
    if not 3 <= len(parts) <= 8:
        return False
    has_mixed_case_fragment = any(
        _looks_like_mixed_case_author_fragment_part(part) for part in parts
    )
    if not has_mixed_case_fragment:
        return False
    return all(
        _looks_like_mixed_case_author_fragment_part(part)
        or _looks_like_author_segment(part)
        for part in parts
    )


def _looks_like_mixed_case_author_fragment_part(text: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
    if not 2 <= len(tokens) <= 4:
        return False
    if not tokens[0][:1].isupper():
        return False
    lower_tail = sum(1 for token in tokens[1:] if token[:1].islower())
    return lower_tail >= 1 and all(1 <= len(token) <= 30 for token in tokens)


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


def _looks_like_publisher_date_fragment(title: str) -> bool:
    normalized = _clean_segment(title)
    return bool(
        re.fullmatch(
            r"(?:Elsevier|Springer|Wiley|IEEE|ACM|Taylor\s*&\s*Francis)"
            r"\s*,?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
            r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
            r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)\d{2}",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_numeric_month_fragment(title: str) -> bool:
    normalized = _clean_segment(title)
    return bool(
        re.fullmatch(
            r"\d{1,4}\s*,\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
            r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
            r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+(?:19|20)\d{2}",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_venue_volume_page_only_title(title: str) -> bool:
    normalized = _clean_segment(title)
    numeric_tail_pattern = (
        r"(?:"
        r"(?:19|20)\d{2}\s*,\s*"
        r")?"
        r"(?:\d{1,4}(?:\(\d{1,4}\))?\s*,\s*){1,3}"
        r"[\dA-Za-z][\dA-Za-z\-‐‑‒–—]*"
        r"(?:\s*[-‐‑‒–—]\s*[\dA-Za-z]+)?"
        r"(?:\s*\.?\s*(?:"
        r"\[[^\]]*(?:cover|frontispiece|highlighted|featured)[^\]]*\]"
        r"|\([^)]*(?:cover|frontispiece|highlighted|featured)[^)]*\)"
        r"))?"
    )
    if re.fullmatch(numeric_tail_pattern, normalized, flags=re.IGNORECASE):
        return True

    match = re.fullmatch(
        rf"(?P<venue>.+?)[,\s]+(?P<tail>{numeric_tail_pattern})",
        normalized,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.fullmatch(
            r"(?P<venue>.+?)(?P<tail>(?:19|20)\d{2}\s*,\s*"
            r"(?:\d{1,4}(?:\(\d{1,4}\))?\s*,\s*){1,3}"
            r"[\dA-Za-z][\dA-Za-z\-‐‑‒–—]*"
            r"(?:\s*[-‐‑‒–—]\s*[\dA-Za-z]+)?)",
            normalized,
            flags=re.IGNORECASE,
        )
    if match is None:
        return False
    venue_head = _clean_segment(match.group("venue"))
    return bool(
        _looks_like_venue(venue_head)
        or _looks_like_journal_tail(venue_head)
        or _looks_like_bibliographic_venue_name(venue_head)
        or _looks_like_abbreviated_venue_fragment(venue_head)
        or _ABBREVIATED_JOURNAL_RE.fullmatch(venue_head)
    )


def _looks_like_author_tail_venue_only_title(title: str) -> bool:
    normalized = _clean_segment(title)
    match = re.fullmatch(r"et\s+al\.?\s+(?P<venue>.+)", normalized, flags=re.IGNORECASE)
    if match is None:
        return False
    venue = _clean_segment(match.group("venue"))
    return bool(
        _looks_like_venue(venue)
        or _looks_like_journal_tail(venue)
        or _looks_like_bibliographic_venue_name(venue)
        or _looks_like_abbreviated_venue_fragment(venue)
    )


def _looks_like_lone_venue_title(title: str) -> bool:
    normalized = _clean_segment(title)
    if _YEAR_RE.search(normalized) is not None:
        return False
    if ":" in normalized or "?" in normalized:
        return False
    word_count = len(normalized.split())
    if not 2 <= word_count <= 6:
        return False
    return bool(
        _looks_like_venue(normalized)
        or _looks_like_journal_tail(normalized)
        or _looks_like_bibliographic_venue_name(normalized)
    )


def _looks_like_bibliographic_venue_name(text: str) -> bool:
    normalized = _clean_segment(text)
    return bool(
        re.search(
            r"\b(?:reviews?|energy|nano|storage|materials?|communications?|synfacts)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


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
        and not re.search(r"[.。．?？]", normalized)
    )


def _looks_like_chinese_intro_english_venue_fragment(title: str) -> bool:
    normalized = _clean_segment(title)
    if _YEAR_RE.search(normalized):
        return False
    match = re.match(
        r"^(?:[\u4e00-\u9fff]{2,4}(?:教授|老师|博士)?\s*)?在\s+(?P<tail>.+)$",
        normalized,
    )
    if match is None:
        return False

    tail = _clean_segment(match.group("tail"))
    if not tail or re.search(r"[\u4e00-\u9fff]", tail):
        return False
    if re.search(r"[.。．?？:：]", tail):
        return False
    if not re.search(
        r"\b(?:science|nature|materials|cell|journal|communications?|"
        r"letters|proceedings?)\b",
        tail,
        flags=re.IGNORECASE,
    ):
        return False
    return len(re.findall(r"[A-Za-z]+", tail)) <= 8


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


def _looks_like_etc_author_only_title(title: str) -> bool:
    normalized = _normalize_author_text(title)
    if not _ETC_AUTHOR_SUFFIX_RE.search(normalized):
        return False
    base = _clean_segment(_ETC_AUTHOR_SUFFIX_RE.sub("", normalized))
    return _looks_like_romanized_chinese_full_name_author_any_order(base)


def _looks_like_connective_romanized_chinese_author_title(title: str) -> bool:
    normalized = _normalize_author_text(title)
    if len(normalized) > 80:
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"\s+(?:and|&)\s+", normalized, flags=re.IGNORECASE)
        if _clean_segment(part)
    ]
    if len(parts) != 2:
        return False
    return all(_looks_like_romanized_chinese_full_name_author_any_order(part) for part in parts)


def _looks_like_romanized_chinese_full_name_author_any_order(text: str) -> bool:
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
    if not all(
        re.fullmatch(_NAME_TOKEN_PATTERN, token, flags=re.UNICODE)
        for token in tokens
    ):
        return False
    if not any(token[:1].isupper() for token in tokens):
        return False

    first = re.sub(r"[^A-Za-z'’-]", "", tokens[0]).casefold()
    last = re.sub(r"[^A-Za-z'’-]", "", tokens[-1]).casefold()
    return first in _COMMON_ROMANIZED_CHINESE_SURNAMES or last in _COMMON_ROMANIZED_CHINESE_SURNAMES


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
        or re.match(r"^(?:and\b|&|…|\.\.\.)", normalized, flags=re.IGNORECASE)
        or re.match(
            rf"^{_NAME_TOKEN_PATTERN}\s*[*#†‡+]*\s*[;；]\s*",
            normalized,
            flags=re.UNICODE,
        )
        or re.fullmatch(
            rf"{_NAME_TOKEN_PATTERN}\s*,\s*(?:[A-Z]\.?\s*){{1,4}}",
            normalized,
            flags=re.UNICODE,
        )
        or (
            (";" in normalized or "；" in normalized)
            and _looks_like_short_author_fragment_title(normalized)
        )
        or _starts_with_short_author_comma_prefix_title(normalized)
        or _split_full_name_period_title_prefix(normalized) is not None
        or _split_author_continuation_before_title(normalized) is not None
        or _split_embedded_colon_author_prefix(normalized) is not None
        or _split_embedded_full_name_author_prefix(normalized) is not None
        or _split_mixed_semicolon_author_prefix(normalized) is not None
    )


def _repair_contaminated_title_result(
    result: tuple[str, str | None, str | None],
) -> tuple[str, str | None, str | None] | None:
    title, authors, venue = result
    if venue:
        title_venue_head = _move_trailing_venue_head_from_title(title, venue)
        if title_venue_head is not None:
            clean_title, title_venue = title_venue_head
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, authors, title_venue

        connective_initial = (
            _split_connective_initial_surname_authors_before_title_segment(
                title,
                [venue],
            )
        )
        if connective_initial is not None:
            extra_authors, clean_title, title_venue = connective_initial
            combined_authors = _append_author_text(authors, ", ".join(extra_authors))
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        title_with_venue = f"{title}. {venue}"
        marker_surname_author = (
            _split_marker_semicolon_surname_given_period_author_suffix(title_with_venue)
        )
        if marker_surname_author is not None:
            extra_author, clean_title, title_venue = marker_surname_author
            combined_authors = _append_author_text(authors, extra_author)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        leading_author_title = _split_leading_author_comma_title_prefix(
            title_with_venue
        )
        if leading_author_title is not None:
            extra_authors, clean_title, title_venue = leading_author_title
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        author_prefixed = _split_author_prefixed_citation(title_with_venue)
        if author_prefixed is not None:
            clean_title, extra_authors, title_venue = author_prefixed
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        period_author_title = _split_period_author_fragments_before_title(
            title_with_venue
        )
        if period_author_title is not None:
            extra_authors, clean_title, title_venue = period_author_title
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        mixed_period = _split_mixed_author_period_prefix(title_with_venue)
        if mixed_period is not None:
            clean_title, extra_authors, title_venue = mixed_period
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

        mixed_year = _split_mixed_author_year_prefix(title_with_venue)
        if mixed_year is not None:
            clean_title, extra_authors, title_venue = mixed_year
            combined_authors = _append_author_text(authors, extra_authors)
            if not _title_result_needs_author_prefix_fallback(clean_title):
                return clean_title, combined_authors, title_venue

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

    stripped_year_title = _strip_leading_citation_year_title_prefix(title)
    if stripped_year_title and stripped_year_title != _clean_segment(title):
        clean_title, remainder = _split_title_and_remainder_after_author_prefix(
            stripped_year_title
        )
        candidate_title = clean_title or stripped_year_title
        if not _title_result_needs_author_prefix_fallback(candidate_title):
            combined_venue = venue or remainder or None
            return candidate_title, authors, combined_venue
    return None


def _split_marker_semicolon_surname_given_period_author_suffix(
    text: str,
) -> tuple[str, str, str | None] | None:
    normalized = _clean_segment(text)
    stripped = _clean_segment(
        re.sub(r"^[*#†‡ǂ]+\s*[;；]\s*", "", normalized)
    )
    if stripped == normalized:
        return None
    return _split_surname_given_period_author_suffix(stripped)


def _split_period_author_fragments_before_title(
    text: str,
) -> tuple[str, str, str | None] | None:
    normalized = _clean_segment(text)
    if ". " not in normalized:
        return None

    segments = [
        _clean_segment(segment)
        for segment in re.split(r"\.\s+", normalized)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return None

    for title_index in range(1, min(len(segments) - 1, 4)):
        author_text = ". ".join(segments[:title_index])
        author_text_as_list = re.sub(r"\.\s+", ", ", author_text)
        title = segments[title_index]
        venue = ". ".join(segments[title_index + 1 :]) or None
        if not _looks_like_period_author_fragment_chain(author_text_as_list):
            continue
        if not _looks_like_llm_author_prefix_stripped_title(title):
            continue
        return author_text_as_list, title, venue
    return None


def _split_pubmed_author_period_prefix(
    text: str,
) -> tuple[str, str, str | None] | None:
    normalized = _clean_segment(text)
    if ". " not in normalized:
        return None

    segments = [
        _clean_segment(segment)
        for segment in re.split(r"\.\s+", normalized)
        if _clean_segment(segment)
    ]
    if len(segments) < 3:
        return None

    for title_index in range(1, min(len(segments) - 1, 5)):
        author_segments = segments[:title_index]
        if not all(_looks_like_pubmed_author_group(segment) for segment in author_segments):
            continue
        title = segments[title_index]
        if _looks_like_pubmed_author_group(title):
            continue
        if not _looks_like_llm_author_prefix_stripped_title(title):
            continue
        venue = ". ".join(segments[title_index + 1 :]) or None
        authors = ", ".join(author_segments)
        return authors, title, venue
    return None


def _looks_like_pubmed_author_group(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if "," in normalized or "，" in normalized:
        return _looks_like_pubmed_author_list(normalized)
    return _looks_like_pubmed_author_segment(normalized)


def _looks_like_period_author_fragment_chain(text: str) -> bool:
    if (
        _looks_like_author_list(text)
        or _looks_like_comma_surname_author_list(text)
        or _looks_like_pubmed_author_list(text)
    ):
        return True
    normalized = _normalize_author_text(text)
    if "…" not in normalized and "..." not in normalized:
        return False
    repaired = re.sub(
        rf"\b(?:[A-Z]\.?\s*)?{_NAME_TOKEN_PATTERN}\s*(?:…|\.{{3}})+\.?\s*",
        "",
        normalized,
        count=1,
        flags=re.UNICODE,
    )
    return _looks_like_comma_surname_author_list(repaired)


def _split_question_title_venue_tail(
    title: str,
    venue: str | None,
) -> tuple[str, str | None]:
    normalized_title = _clean_segment(title)
    match = re.match(
        r"^(?P<title>.+\?)\s+(?P<venue>[A-Z][A-Za-z&.-]+"
        r"(?:\s+[A-Z][A-Za-z&.-]+){0,3})$",
        normalized_title,
    )
    if match is None:
        return normalized_title, venue
    venue_head = _clean_segment(match.group("venue"))
    existing_venue = _clean_segment(venue or "")
    combined_venue = (
        f"{venue_head}. {existing_venue}" if existing_venue else venue_head
    )
    if not existing_venue and not _looks_like_venue(combined_venue):
        return normalized_title, venue
    return _clean_segment(match.group("title")), combined_venue


def _prefer_mixed_author_prefix_result(
    text: str,
    result: tuple[str, str | None, str | None],
) -> tuple[str, str | None, str | None]:
    candidates = (
        _split_mixed_author_period_prefix(text),
        _split_mixed_author_year_prefix(text),
    )
    for candidate in candidates:
        if candidate is None:
            continue
        if _title_result_needs_author_prefix_fallback(candidate[0]):
            continue
        if _result_title_needs_mixed_author_fallback(result):
            return candidate
        if _same_title_but_better_venue(candidate, result):
            return candidate
    return result


def _prefer_mixed_semicolon_author_prefix_result(
    text: str,
    result: tuple[str, str | None, str | None],
) -> tuple[str, str | None, str | None]:
    candidate = _split_mixed_semicolon_author_prefix(text)
    if candidate is None:
        return result
    if _title_result_needs_author_prefix_fallback(candidate[0]):
        return result
    if _result_title_needs_mixed_author_fallback(result):
        return candidate
    if _same_title_but_better_venue(candidate, result):
        return candidate
    if _same_title_with_venue_head_split(candidate, result):
        return candidate
    return result


def _result_title_needs_mixed_author_fallback(
    result: tuple[str, str | None, str | None],
) -> bool:
    title = _clean_segment(result[0])
    return bool(
        _title_result_needs_author_prefix_fallback(title)
        or _LEADING_CITATION_YEAR_TITLE_PREFIX_RE.search(title)
        or _is_standalone_person_name_title(title)
        or _looks_like_short_author_fragment_title(title)
    )


def _standard_semicolon_period_title_is_clean(title: str) -> bool:
    normalized = _clean_segment(title)
    if re.search(r"[;；]", normalized):
        return False
    if re.match(r"^(?:[A-Z]\.?\s*)?[*#†‡ǂ]+\s*[,，;；]", normalized):
        return False
    if re.match(r"^[A-Z]\.\s*[*#†‡ǂ]*\s*[,，]", normalized):
        return False
    return bool(
        _looks_like_publication_title_after_author_prefix(normalized)
        and not _is_non_publication_title_noise(normalized)
        and not _looks_like_author_list(normalized)
        and not _looks_like_short_author_fragment_title(normalized)
        and not _is_standalone_person_name_title(normalized)
        and not re.match(r"^(?:and\b|&|…|\.\.\.)", normalized, flags=re.IGNORECASE)
    )


def _same_title_but_better_venue(
    candidate: tuple[str, str | None, str | None],
    current: tuple[str, str | None, str | None],
) -> bool:
    if _clean_segment(candidate[0]) != _clean_segment(current[0]):
        return False
    candidate_venue = _clean_segment(candidate[2] or "")
    current_venue = _clean_segment(current[2] or "")
    return bool(candidate_venue and len(candidate_venue) > len(current_venue))


def _same_title_with_venue_head_split(
    candidate: tuple[str, str | None, str | None],
    current: tuple[str, str | None, str | None],
) -> bool:
    candidate_title = _clean_segment(candidate[0])
    current_title = _clean_segment(current[0])
    candidate_venue = _clean_segment(candidate[2] or "")
    if not candidate_title or not candidate_venue:
        return False
    if current_title.startswith(f"{candidate_title}, "):
        swallowed_venue_head = _clean_segment(current_title[len(candidate_title) + 1 :])
    elif f"; {candidate_title}, " in current_title:
        swallowed_venue_head = _clean_segment(
            current_title.rsplit(f"; {candidate_title}, ", maxsplit=1)[1]
        )
    else:
        return False
    if not swallowed_venue_head or len(swallowed_venue_head.split()) > 4:
        return False
    venue_head = _clean_segment(
        re.split(r"[:：,，]", candidate_venue, maxsplit=1)[0]
    )
    return swallowed_venue_head == venue_head


def _looks_like_short_author_fragment_title(title: str) -> bool:
    normalized = _clean_segment(title)
    if not normalized or len(normalized) > 80:
        return False
    if not _has_explicit_author_syntax(normalized):
        return False
    if re.search(r"[:：?？]", normalized):
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"\s*(?:[,，;；]|\band\b|&)\s*", normalized)
        if _clean_segment(part)
    ]
    if not 1 <= len(parts) <= 4:
        return False
    authorish = 0
    for part in parts:
        if _looks_like_short_author_fragment_part(part):
            authorish += 1
    return authorish == len(parts)


def _looks_like_short_author_fragment_part(text: str) -> bool:
    markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", text))
    if not markerless:
        return False
    if _is_single_author_name_token(markerless):
        return True
    if re.fullmatch(r"(?:[A-Z]\.?\s*){1,4}", markerless):
        return True
    if re.fullmatch(r"[A-Z](?:-[a-z])?", markerless):
        return True
    words = [word for word in markerless.split() if word]
    if len(words) > 2 and not re.search(r"\b[A-Z]\.", markerless):
        return False
    return _looks_like_author_segment(markerless)


def _split_full_name_period_title_prefix(
    text: str,
) -> tuple[str, str, str | None] | None:
    for match in re.finditer(r"\.\s+", text):
        author_candidate = _clean_segment(text[: match.start()])
        suffix = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", text[match.end() :]))
        if not author_candidate or not suffix:
            continue
        if not _is_standalone_person_name_title(author_candidate):
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return author_candidate, candidate_title, venue or remainder or None
    return None


def _split_connective_full_name_period_title_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"\.\s+", text):
        prefix = _repair_missing_connective_author_spacing(
            _clean_segment(text[: match.start()])
        )
        suffix = _clean_segment(text[match.end() :])
        if not prefix or not suffix:
            continue
        if _looks_like_incomplete_initial_author_before_surname(prefix, suffix):
            continue
        if not _looks_like_connective_author_name_pair(prefix):
            continue
        suffix = re.sub(r"\.(?=In:)", ". ", suffix)
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        return candidate_title, _normalize_author_list(prefix), venue or remainder
    return None


def _repair_missing_connective_author_spacing(text: str) -> str:
    repaired = re.sub(r"(?<=[a-z])and\s+(?=[A-Z])", " and ", text)
    return _clean_segment(repaired)


def _split_leading_author_comma_title_prefix(
    text: str,
) -> tuple[str, str, str | None] | None:
    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", text, maxsplit=2)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return None

    author: str | None = None
    suffix: str | None = None
    if len(parts) >= 3:
        surname_given = f"{parts[0]}, {parts[1]}"
        if (
            not re.search(r"[-‐‑‒–—]", parts[0])
            and _parse_surname_given_author_segment(surname_given) is not None
        ):
            author = _normalize_surname_given_author_segment(surname_given)
            suffix = parts[2]
    if author is None and _looks_like_author_list(parts[0]):
        author = _normalize_author_list(parts[0])
        suffix = ", ".join(parts[1:])
    if not author or not suffix:
        return None

    title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
    candidate_title = title or suffix
    if _suffix_starts_with_author_continuation(candidate_title):
        return None
    if not _looks_like_publication_title_after_author_prefix(candidate_title):
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
        venue = remainder
    else:
        _, venue = _split_remainder_authors_venue(remainder)
        venue = venue or remainder or None
    return author, candidate_title, venue


def _starts_with_short_author_comma_prefix_title(text: str) -> bool:
    normalized = _clean_segment(text)
    if "," not in normalized and "，" not in normalized:
        return False

    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", normalized, maxsplit=2)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False

    if len(parts) >= 3 and _looks_like_strict_surname_given_pair(parts[0], parts[1]):
        title_candidate = _clean_segment(parts[2])
        return bool(
            title_candidate
            and not _suffix_starts_with_author_continuation(title_candidate)
            and _looks_like_publication_title_after_author_prefix(title_candidate)
        )

    first_words = parts[0].split()
    if not (1 <= len(first_words) <= 2 and _looks_like_author_segment(parts[0])):
        return False
    title_candidate = _clean_segment(", ".join(parts[1:]))
    return bool(
        title_candidate
        and not _suffix_starts_with_author_continuation(title_candidate)
        and _looks_like_publication_title_after_author_prefix(title_candidate)
    )


def _looks_like_strict_surname_given_pair(surname: str, given: str) -> bool:
    clean_surname = _clean_segment(_AUTHOR_MARKER_RE.sub("", surname))
    clean_given = _clean_segment(_AUTHOR_MARKER_RE.sub("", given))
    if not clean_surname or not clean_given:
        return False
    if not re.fullmatch(
        r"[A-Z][a-z'’.-]+(?:-[A-Z][a-z'’.-]+)?",
        clean_surname,
    ):
        return False
    return bool(
        re.fullmatch(r"(?:[A-Z]\.?\s*){1,4}", clean_given)
        or re.fullmatch(
            r"[A-Z][a-z'’.-]+(?:-[A-Z][a-z'’.-]+)?"
            r"(?:\s+[A-Z][a-z'’.-]+(?:-[A-Z][a-z'’.-]+)?){0,2}",
            clean_given,
        )
    )


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
            r"^[\u4e00-\u9fff]{2,6}\s*[*#†‡]+\s*[.。．]\s*"
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
    for match in re.finditer(r"[.。．]\s*", title):
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
    normalized = _WHITESPACE_RE.sub(" ", text).strip(" \t\r\n")
    normalized = re.sub(r"\ba\s+nd\b", "and", normalized, flags=re.IGNORECASE)

    def replace_spaced_hyphen_initials(match: re.Match[str]) -> str:
        return (
            f"{match.group('surname')}, "
            f"{match.group('first').upper()}.-{match.group('second').upper()}."
        )

    return re.sub(
        r"\b(?P<surname>[A-Z][A-Za-z'’-]+),\s*"
        r"(?P<first>[A-Za-z])\.\s*[-‐‑‒–—]\s*"
        r"(?P<second>[A-Za-z])\.",
        replace_spaced_hyphen_initials,
        normalized,
    )


def _clean_segment(text: str) -> str:
    cleaned = _TRAILING_PUNCTUATION_RE.sub("", clean_paper_title(text))
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)


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
    clean_title = _strip_leading_chinese_author_note_fragment(clean_title)
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
    clean_title = _repair_split_title_words(clean_title)
    clean_title = _TRAILING_WITH_AUTHORS_NOTE_RE.sub("", clean_title).strip()
    title_without_tail, remainder = _split_title_and_remainder(clean_title)
    if (
        remainder
        and title_without_tail != clean_title
        and len(title_without_tail) >= _MIN_TITLE_LENGTH
    ):
        return title_without_tail
    return clean_title


def _strip_leading_chinese_author_note_fragment(title_text: str) -> str:
    title = _clean_segment(title_text)
    match = _LEADING_CHINESE_AUTHOR_NOTE_FRAGMENT_RE.match(title)
    if match is None:
        return title
    suffix = _clean_segment(title[match.end() :])
    return suffix or title


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
    repaired = text
    for word in sorted(_COMMON_SPLIT_TITLE_WORD_REPAIRS, key=len, reverse=True):
        pattern = re.compile(
            r"\b" + r"\s*".join(re.escape(char) for char in word) + r"\b",
            re.IGNORECASE,
        )

        def replace(match: re.Match[str], *, expected: str = word) -> str:
            value = match.group(0)
            if not re.search(r"\s", value):
                return value
            compact = re.sub(r"\s+", "", value)
            if compact.isupper():
                return expected.upper()
            if compact[:1].isupper():
                return expected[:1].upper() + expected[1:]
            return expected

        repaired = pattern.sub(replace, repaired)
    repaired = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "-", repaired)
    return re.sub(r"\b(\d+)\s+(st|nd|rd|th)\b", r"\1\2", repaired)


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
        suffix = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", text[match.end() :]))
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


def _split_mixed_author_period_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in reversed(list(re.finditer(r"\.\s+(?=[(（]?(?:19|20)\d{2}\b|[A-Z])", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _strip_leading_citation_year_title_prefix(text[match.end() :])
        authors = _parse_mixed_author_prefix(prefix)
        if not authors or not suffix:
            continue
        title, remainder = _split_title_and_remainder(suffix)
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


def _split_mixed_author_year_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"\(?\b(?:19|20)\d{2}\b\)?[.),，]?\s+", text):
        prefix = _clean_segment(text[: match.start()]).rstrip(" ,，.;；(（")
        suffix = _strip_leading_citation_year_title_prefix(text[match.start() :])
        authors = _parse_mixed_author_prefix(prefix)
        if not authors or not suffix:
            continue
        title, remainder = _split_title_and_remainder(suffix)
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


def _split_mixed_semicolon_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    for match in reversed(list(re.finditer(r"[;；]\s*", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _strip_leading_citation_year_title_prefix(text[match.end() :])
        authors = _parse_mixed_author_prefix(prefix)
        if not authors or not suffix:
            continue
        if _suffix_starts_with_author_continuation(suffix):
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


def _split_loose_semicolon_author_chain_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    for match in reversed(list(re.finditer(r"[;；]\s*", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _strip_leading_citation_year_title_prefix(text[match.end() :])
        if not prefix or not suffix:
            continue
        segments = _loose_semicolon_author_segments(prefix)
        if not _looks_like_loose_semicolon_author_chain(segments):
            continue
        if _suffix_starts_with_author_continuation(suffix):
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not (
            _looks_like_publication_title_after_author_prefix(candidate_title)
            or _looks_like_title_segment(candidate_title)
            or _looks_like_loose_semicolon_title_candidate(candidate_title)
        ):
            continue
        if _title_has_author_prefix_contamination(candidate_title) or re.match(
            r"^(?:&|…|\.\.\.)\s*",
            candidate_title,
        ):
            continue
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        authors = _normalize_loose_semicolon_author_chain(segments)
        if len(authors) < 2:
            continue
        return candidate_title, ", ".join(authors), venue
    return None


def _looks_like_loose_semicolon_title_candidate(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    if _is_non_publication_title_noise(normalized):
        return False
    if _looks_like_journal_tail(normalized):
        return False
    if re.match(r"^(?:&|…|\.\.\.)\s*", normalized):
        return False
    if _has_explicit_author_syntax(normalized) and _looks_like_author_list(normalized):
        return False
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", normalized):
        return False
    words = [word for word in normalized.split() if word]
    return len(words) >= 4 or _looks_like_chinese_title_segment(normalized)


def _loose_semicolon_author_segments(text: str) -> list[str]:
    return [
        _clean_segment(part)
        for part in re.split(r"[;；]", text)
        if _clean_segment(part)
    ]


def _looks_like_loose_semicolon_author_chain(segments: list[str]) -> bool:
    if len(segments) < 3:
        return False
    named_authors = 0
    for segment in segments:
        authors = _normalize_loose_semicolon_author_segment(segment)
        if authors:
            named_authors += len(authors)
            continue
        if _is_ellipsis_author_placeholder(segment):
            continue
        return False
    return named_authors >= 2


def _normalize_loose_semicolon_author_chain(segments: list[str]) -> list[str]:
    authors: list[str] = []
    for segment in segments:
        authors.extend(_normalize_loose_semicolon_author_segment(segment))
    return authors


def _normalize_loose_semicolon_author_segment(segment: str) -> list[str]:
    normalized = _clean_loose_semicolon_author_segment(segment)
    if not normalized:
        return []

    parsed = _parse_mixed_semicolon_author_unit(normalized)
    if parsed:
        return parsed

    loose_surname_given = _normalize_loose_surname_given_author_segment(normalized)
    if loose_surname_given is not None:
        return [loose_surname_given]

    if _looks_like_author_segment(normalized) or _looks_like_author_list(normalized):
        return [_normalize_author_list(normalized)]
    return []


def _clean_loose_semicolon_author_segment(segment: str) -> str:
    normalized = _clean_mixed_author_prefix_text(segment)
    normalized = re.sub(
        r"^(?:…|\.{3})\s*(?:&|and)?\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = _clean_segment(_AUTHOR_MARKER_RE.sub("", normalized))
    return normalized.strip(" .。．;；,，")


def _is_ellipsis_author_placeholder(segment: str) -> bool:
    normalized = _clean_segment(segment)
    return bool(re.fullmatch(r"(?:…|\.{3})\s*(?:&|and)?", normalized, re.IGNORECASE))


def _normalize_loose_surname_given_author_segment(segment: str) -> str | None:
    normalized = _clean_segment(segment)
    match = re.fullmatch(
        rf"(?P<surname>{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,3}})"
        r"\s*[,，]\s*(?P<given>[^;；]{1,80})",
        normalized,
        flags=re.UNICODE,
    )
    if match is None:
        return None
    surname = _clean_segment(match.group("surname"))
    given = _clean_segment(re.sub(r"[,，]", " ", match.group("given")))
    given = _normalize_given_name_tokens(given)
    if not surname or not given:
        return None
    return f"{given} {surname}".strip()


def _parse_mixed_author_prefix(text: str) -> list[str]:
    normalized = _clean_mixed_author_prefix_text(text)
    if not normalized:
        return []

    if ";" in normalized or "；" in normalized:
        authors: list[str] = []
        for part in re.split(r"\s*[;；]\s*", normalized):
            part_authors = _parse_mixed_semicolon_author_unit(part)
            if not part_authors:
                return []
            authors.extend(part_authors)
        return authors if len(authors) >= 2 else []

    return _parse_mixed_author_unit(normalized)


def _parse_mixed_semicolon_author_unit(text: str) -> list[str]:
    normalized = _clean_mixed_author_prefix_text(text)
    if not normalized:
        return []

    ellipsis_match = re.match(
        r"^…\s*(?:&|and)?\s*(?P<author>.+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if ellipsis_match is not None:
        normalized = _clean_mixed_author_prefix_text(ellipsis_match.group("author"))

    markerless = _clean_segment(_AUTHOR_MARKER_RE.sub("", normalized))
    parsed = _parse_mixed_author_unit(markerless)
    if parsed:
        return parsed
    if _is_single_author_name_token(markerless):
        return [_normalize_author_text(markerless)]
    return []


def _parse_mixed_author_unit(text: str) -> list[str]:
    normalized = _clean_mixed_author_prefix_text(text)
    if not normalized:
        return []

    if re.search(r"\s+(?:and|&)\s+", normalized, flags=re.IGNORECASE):
        authors: list[str] = []
        for part in re.split(r"\s+(?:and|&)\s+", normalized, flags=re.IGNORECASE):
            part_authors = _parse_mixed_author_unit(part)
            if not part_authors:
                return []
            authors.extend(part_authors)
        return authors

    single_surname_given_author = _normalize_flexible_surname_given_author_segment(
        normalized
    )
    if single_surname_given_author is not None:
        return [single_surname_given_author]

    surname_given_authors = _parse_flexible_surname_given_author_sequence(normalized)
    if surname_given_authors:
        return surname_given_authors

    comma_author_segments = _parse_comma_author_segment_sequence(normalized)
    if comma_author_segments:
        return comma_author_segments

    if _looks_like_concatenated_author_name(normalized):
        return [_normalize_concatenated_author_name(normalized)]

    single_token_romanized = _normalize_single_token_romanized_chinese_author(
        normalized
    )
    if single_token_romanized is not None:
        return [single_token_romanized]

    if _looks_like_author_list(normalized):
        return [_normalize_author_list(normalized)]
    if _looks_like_author_segment(normalized):
        return [_normalize_author_text(normalized)]
    return []


def _parse_flexible_surname_given_author_sequence(text: str) -> list[str]:
    segments = [
        _clean_mixed_author_prefix_text(segment)
        for segment in re.split(r"\s*[,，]\s*", text)
        if _clean_mixed_author_prefix_text(segment)
    ]
    if len(segments) < 2:
        return []

    authors: list[str] = []
    consumed_surname_given = False
    index = 0
    while index < len(segments):
        if index + 1 < len(segments):
            author = _normalize_flexible_surname_given_author_segment(
                f"{segments[index]}, {segments[index + 1]}"
            )
            if author is not None:
                authors.append(author)
                consumed_surname_given = True
                index += 2
                continue

        if _looks_like_author_segment(segments[index]) or _looks_like_author_list(
            segments[index]
        ):
            authors.append(_normalize_author_list(segments[index]))
            index += 1
            continue
        return []

    return authors if consumed_surname_given and len(authors) >= 2 else []


def _parse_comma_author_segment_sequence(text: str) -> list[str]:
    if "," not in text and "，" not in text:
        return []
    segments = [
        _clean_mixed_author_prefix_text(segment)
        for segment in re.split(r"\s*[,，]\s*", text)
        if _clean_mixed_author_prefix_text(segment)
    ]
    if len(segments) < 2:
        return []
    authors: list[str] = []
    for segment in segments:
        if not (
            _looks_like_author_segment(segment) or _looks_like_author_list(segment)
        ):
            return []
        authors.append(_normalize_author_list(segment))
    return authors


def _normalize_flexible_surname_given_author_segment(text: str) -> str | None:
    normalized = _clean_mixed_author_prefix_text(text)
    match = _SURNAME_GIVEN_AUTHOR_RE.fullmatch(_normalize_author_text(normalized))
    if match is None:
        return None
    surname = match.group(1)
    given = _normalize_given_name_tokens(match.group(2))
    return f"{given} {surname}".strip()


def _clean_mixed_author_prefix_text(text: str) -> str:
    cleaned = _clean_segment(text)
    cleaned = re.sub(r"\b([A-Z][A-Za-z'’-]+)\.(?=[A-Z]{1,4}\b)", r"\1 ", cleaned)
    cleaned = re.sub(r"\b([A-Z][A-Za-z'’-]+)\s+\.(?=[A-Z])", r"\1 ", cleaned)
    cleaned = re.sub(r"\s*[.。]\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,，;；")


def _strip_leading_citation_year_title_prefix(text: str) -> str:
    cleaned = _strip_leading_year_month_title_prefix(text)
    return _clean_segment(_LEADING_CITATION_YEAR_TITLE_PREFIX_RE.sub("", cleaned))


def _split_and_surname_given_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if " and " not in text:
        return None

    for match in re.finditer(r"\(?\b(?:19|20)\d{2}\b\)?[.),，]?\s+", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _strip_leading_year_month_title_prefix(text[match.end() :])
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
        suffix = _strip_leading_year_month_title_prefix(text[match.end() :])
        authors = _parse_and_surname_given_author_list(prefix)
        if not authors or not suffix:
            continue
        continuation = _split_and_surname_given_author_continuation(suffix)
        if continuation is not None:
            extra_authors, title, venue = continuation
            return title, ", ".join([*authors, *extra_authors]), venue
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


def _split_and_surname_given_author_continuation(
    text: str,
) -> tuple[list[str], str, str | None] | None:
    if " and " not in text:
        return None

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
        return authors, candidate_title, venue
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
    normalized = _strip_parenthesized_author_markers(normalized)
    normalized = re.sub(r"(?<=[A-Za-z])\s*-\s*(?=[A-Za-z])", "-", normalized)
    normalized = re.sub(r"\b([A-Z])\.(?=[A-Z][a-z])", r"\1. ", normalized)
    normalized = _repair_split_diacritic_author_letters(normalized)
    normalized = _repair_spaced_author_name_tokens(normalized)
    normalized = _repair_split_pinyin_given_name_tokens(normalized)
    normalized = re.sub(r"(?<=[A-Za-z])\s*&+\s+(?=and\b)", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*&+\s*(?=[,;，；.]|$)", "", normalized)
    normalized = re.sub(r"\s*\+\s*(?=[,;，；.]|$)", "", normalized)
    normalized = _AUTHOR_NOTE_RE.sub("", normalized)
    normalized = _AUTHOR_YEAR_MARKER_RE.sub("", normalized)
    normalized = _AUTHOR_MARKER_RE.sub("", normalized)
    normalized = re.sub(r"(?<=\.)\+(?=\s*(?:[,;，；.]|$))", "", normalized)
    normalized = re.sub(r"(?<=[A-Z])\+(?=\s*(?:[,;，；.]|$))", "", normalized)
    normalized = re.sub(r"^\s*(?:and|&)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip(" ,;")


def _strip_parenthesized_author_markers(text: str) -> str:
    return _PARENTHESIZED_AUTHOR_MARKER_RE.sub("", text)


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


def _strip_leading_year_month_title_prefix(text: str) -> str:
    cleaned = _clean_segment(text)
    cleaned = _LEADING_YEAR_MONTH_TITLE_PREFIX_RE.sub("", cleaned)
    return _LEADING_MONTH_TITLE_PREFIX_RE.sub("", cleaned)


def _looks_like_single_author_token_before_title(text: str) -> bool:
    normalized = _normalize_author_text(text)
    return bool(
        _is_single_author_name_token(normalized)
        and _MONTH_NAME_RE.fullmatch(normalized) is None
        and normalized.casefold() not in _SINGLE_AUTHOR_TOKEN_EXCLUSIONS
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
        match = re.fullmatch(
            rf"(?P<surname>"
            r"(?:da|de|del|della|der|di|dos|du|la|le|van|von)"
            rf"\s+{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,2}}"
            rf"),\s*(?P<given>(?:{_NAME_TOKEN_PATTERN}|{_INITIAL_CLUSTER_PATTERN})"
            rf"(?:\s+(?:{_NAME_TOKEN_PATTERN}|{_INITIAL_CLUSTER_PATTERN})){{0,3}})",
            normalized,
            flags=re.IGNORECASE | re.UNICODE,
        )
        if match is None:
            return None
        surname = match.group("surname")
        given = match.group("given")
    else:
        surname = match.group(1)
        given = match.group(2)
    given = _WHITESPACE_RE.sub(" ", given).strip()
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
            next_surname = connective_match.group("next_surname")
            next_given = segments[index + 2]
            if next_given.casefold() in _COMMON_ROMANIZED_CHINESE_SURNAMES:
                second_pair = f"{next_given}, {next_surname}"
            else:
                second_pair = f"{next_surname}, {next_given}"
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
        _strip_leading_author_contribution_marker(_clean_segment(part))
        for part in re.split(r"[;；]", text)
        if _strip_leading_author_contribution_marker(_clean_segment(part))
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


def _strip_leading_author_contribution_marker(text: str) -> str:
    return _clean_segment(re.sub(r"^\s*[+＋]\s*", "", text))


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


def _normalize_single_token_romanized_chinese_author(text: str) -> str | None:
    markerless = _AUTHOR_MARKER_RE.sub("", _clean_segment(text)).strip()
    if not re.fullmatch(r"[A-Z][a-z]{4,24}", markerless):
        return None
    lowered = markerless.casefold()
    for surname in sorted(_COMMON_ROMANIZED_CHINESE_SURNAMES, key=len, reverse=True):
        if len(surname) < 3:
            continue
        if lowered.startswith(surname) and len(lowered) >= len(surname) + 2:
            return markerless
    return None


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
    if _looks_like_pubmed_author_list(normalized):
        return True
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:[;；,，])\s*", normalized)
        if part.strip()
    ]
    if not parts:
        return False
    return all(_looks_like_author_segment(part) for part in parts)


def _looks_like_pubmed_author_list(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if "," not in normalized and "，" not in normalized:
        return False
    parts = [
        _clean_segment(part)
        for part in re.split(r"\s*[,，]\s*", normalized)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return False
    return all(_looks_like_pubmed_author_segment(part) for part in parts)


def _looks_like_pubmed_author_segment(text: str) -> bool:
    normalized = _AUTHOR_MARKER_RE.sub("", _normalize_author_text(text)).strip()
    if (
        not normalized
        or re.search(r"[,，;；:：()（）\d]", normalized)
    ):
        return False
    tokens = normalized.split()
    if not 2 <= len(tokens) <= 5:
        return False
    if not re.fullmatch(r"(?:[A-Z]{1,5}|(?:[A-Z]\.?\s*){1,5})", tokens[-1]):
        return False
    if not re.fullmatch(r"[A-Z][A-Za-z'’-]{1,40}", tokens[0]):
        return False
    allowed_particles = {"da", "de", "del", "der", "di", "dos", "du", "la", "le", "van", "von"}
    if len(tokens) > 2 and not any(
        token.casefold() in allowed_particles for token in tokens[1:-1]
    ):
        return False
    for token in tokens[1:-1]:
        if token.casefold() in allowed_particles:
            continue
        if not re.fullmatch(r"[A-Z][A-Za-z'’-]{1,40}", token):
            return False
    return True


def _looks_like_author_segment(text: str) -> bool:
    normalized = _normalize_author_text(text)
    if not normalized or len(normalized) > 80:
        return False
    if _looks_like_venue(normalized):
        return False
    if re.fullmatch(
        rf"(?:[A-Z]\.?\s*)?{_NAME_TOKEN_PATTERN}\s*(?:…|\.{3})+\.?"
        rf"\s*{_NAME_TOKEN_PATTERN}",
        normalized,
        flags=re.UNICODE,
    ):
        return True
    if re.fullmatch(
        rf"{_NAME_TOKEN_PATTERN}\s+"
        r"(?:da|de|del|della|der|di|dos|du|la|le|van|von)\s+"
        rf"{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,2}}\s+"
        r"(?:[A-Z]\.?|[A-Z]{2,4})",
        normalized,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        return True
    if re.fullmatch(
        r"(?:da|de|del|della|der|di|dos|du|la|le|van|von)\s+"
        rf"{_NAME_TOKEN_PATTERN}(?:\s+{_NAME_TOKEN_PATTERN}){{0,2}}\s+"
        r"(?:[A-Z]\.?|[A-Z]{2,4})",
        normalized,
        flags=re.IGNORECASE | re.UNICODE,
    ):
        return True
    if _looks_like_split_latin_author_segment(normalized):
        return True
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
        return not any(
            token.casefold() in title_connectors
            and not (token.isupper() and 1 < len(token) <= 4)
            for token in tokens
        )
    return bool(_AUTHOR_NAME_RE.fullmatch(normalized))


def _looks_like_split_latin_author_segment(text: str) -> bool:
    tokens = text.split()
    if len(tokens) != 3:
        return False
    first, middle, tail = tokens
    if first.casefold() in {"a", "an", "the"}:
        return False
    return bool(
        re.fullmatch(r"[A-Z][A-Za-z'’-]{2,}", first)
        and re.fullmatch(r"[A-Z][A-Za-z'’-]{2,}", middle)
        and re.fullmatch(r"[a-z][a-z'’-]{1,}", tail)
    )


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
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", normalized):
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
    stripped_first = _strip_leading_lowercase_author_note_marker(
        segments[0],
        following_segment=segments[1],
    )
    if stripped_first != segments[0]:
        segments[0] = stripped_first

    authors: list[str] = []
    skip_next_author_segment = False
    for index, segment in enumerate(segments):
        if skip_next_author_segment:
            skip_next_author_segment = False
            continue

        if authors and index + 1 < len(segments):
            surname_given = f"{segment}, {segments[index + 1]}"
            next_connective_initial_title = (
                _split_connective_initial_surname_authors_before_title_segment(
                    segments[index + 1],
                    segments[index + 2 :],
                )
            )
            if (
                next_connective_initial_title is None
                and _parse_surname_given_author_segment(surname_given) is not None
            ):
                authors.append(_normalize_surname_given_author_segment(surname_given))
                skip_next_author_segment = True
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
                if not _is_single_author_name_token(title):
                    return title, ", ".join(authors), venue

        if authors and (
            connective_initial_title := (
                _split_connective_initial_surname_authors_before_title_segment(
                    segment,
                    segments[index + 1 :],
                )
            )
        ) is not None:
            extra_authors, title, venue = connective_initial_title
            authors.extend(extra_authors)
            return title, ", ".join(authors), venue

        if authors and (
            initial_author_title := _split_initial_surname_author_before_title_segment(
                segment,
                segments[index + 1 :],
            )
        ) is not None:
            author, title, venue = initial_author_title
            authors.append(author)
            return title, ", ".join(authors), venue

        if authors and (
            compact_connective_authors
            := _split_compact_initial_connective_author_segment(segment)
        ) is not None:
            authors.extend(compact_connective_authors)
            continue

        if (
            authors
            and _has_explicit_author_syntax(segment)
            and _looks_like_author_list(segment)
        ):
            authors.append(_normalize_author_list(segment))
            continue

        if authors and (
            continuation := _split_author_continuation_before_title(segment)
        ) is not None:
            extra_authors, title, remainder = continuation
            if extra_authors:
                authors.append(extra_authors)
            continuation_title = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", title))
            following_segments = segments[index + 1 :]
            if (
                following_segments
                and not _starts_with_numeric_citation_tail([following_segments[0]])
                and _PUBLICATION_STATUS_TAIL_RE.fullmatch(following_segments[0]) is None
            ) and (
                continued_title := _split_comma_title_segments_with_following_venue(
                    [continuation_title, *following_segments],
                    0,
                )
            ) is not None:
                title, venue = continued_title
                return title, ", ".join(authors), venue
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

        if (
            authors
            and _looks_like_author_list(segment)
            and _looks_like_explicit_author_chain_segment(segment)
        ):
            authors.append(_normalize_author_list(segment))
            continue
        if authors and _looks_like_concatenated_author_name(segment):
            authors.append(_normalize_concatenated_author_name(segment))
            continue

        if authors and index + 1 < len(segments):
            connective_author_title = (
                _split_connective_full_name_author_title_after_segment(
                    segment,
                    segments[index + 1],
                    segments[index + 2 :],
                )
            )
            if connective_author_title is not None:
                extra_authors, title, venue = connective_author_title
                authors.extend(extra_authors)
                return title, ", ".join(authors), venue

        if authors and (
            embedded_author := _split_embedded_full_name_author_prefix(segment)
        ) is not None:
            embedded_authors, suffix = embedded_author
            authors.append(embedded_authors)
            title, remainder = _split_title_and_remainder(suffix)
            venue_parts = [part for part in (remainder, *segments[index + 1 :]) if part]
            venue = ", ".join(venue_parts).strip(" ,;") or None
            title, venue = _strip_duplicate_bare_venue_tail(
                title or suffix,
                venue or "",
            )
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

            title_with_venue = _split_comma_title_segment_with_following_venue(
                segment,
                segments[index + 1 :],
            )
            if title_with_venue is not None:
                title, venue = title_with_venue
                return title, ", ".join(authors), venue

            multi_segment_title = _split_comma_title_segments_with_following_venue(
                segments,
                index,
            )
            if multi_segment_title is not None:
                title, venue = multi_segment_title
                return title, ", ".join(authors), venue

        if _looks_like_author_list(segment):
            authors.append(_normalize_author_list(segment))
            continue
        if _looks_like_concatenated_author_name(segment):
            authors.append(_normalize_concatenated_author_name(segment))
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
                if end_index < len(segments) and _looks_like_comma_title_continuation_segment(
                    segments[end_index]
                ):
                    continue
                venue = ", ".join(segments[end_index:]).strip(" ,;") or None
                return candidate_title, ", ".join(authors), venue
        if not authors or not _looks_like_title_segment(segment):
            return None
        venue = ", ".join(segments[index + 1 :]).strip(" ,;") or None
        return segment, ", ".join(authors), venue

    return None


def _split_connective_initial_surname_authors_before_title_segment(
    segment: str,
    following_segments: list[str],
) -> tuple[list[str], str, str | None] | None:
    normalized = _clean_segment(segment)
    match = re.match(
        r"^(?P<left>(?:[A-Z]\.\s*){1,4}[A-Z][A-Za-z'’-]{1,40})\s+"
        r"(?:&|and)\s+"
        r"(?P<right>(?:[A-Z]\.\s*){1,4}[A-Z][A-Za-z'’-]{1,40})\s+"
        r"(?P<body>.+)$",
        normalized,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return None
    left = _clean_segment(match.group("left"))
    right = _clean_segment(match.group("right"))
    if not _looks_like_author_segment(left) or not _looks_like_author_segment(right):
        return None

    body = _clean_segment(match.group("body"))
    title_venue = _split_title_year_venue_tail(body, following_segments)
    if title_venue is None and following_segments:
        title_venue = _split_title_year_venue_tail(
            ", ".join([body, *following_segments]),
            [],
        )
    if title_venue is None:
        title, remainder = _split_title_and_remainder(body)
        candidate_title = title or body
        if not _looks_like_title_segment(candidate_title):
            return None
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        title_venue = candidate_title, venue

    title, venue = title_venue
    return [_normalize_author_text(left), _normalize_author_text(right)], title, venue


def _split_initial_surname_author_before_title_segment(
    segment: str,
    following_segments: list[str],
) -> tuple[str, str, str | None] | None:
    normalized = _clean_segment(segment)
    match = re.match(
        r"^(?P<author>(?:[A-Z]\.\s*){1,4}[A-Z][A-Za-z'’-]{1,40})\s+"
        r"(?P<body>.+)$",
        normalized,
        flags=re.UNICODE,
    )
    if match is None:
        return None
    author = _clean_segment(match.group("author"))
    if not _looks_like_author_segment(author):
        return None

    body = _clean_segment(match.group("body"))
    title_venue = _split_title_year_venue_tail(body, following_segments)
    if title_venue is None:
        title, remainder = _split_title_and_remainder(body)
        candidate_title = title or body
        if not _looks_like_title_segment(candidate_title):
            return None
        venue = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else _split_remainder_authors_venue(remainder)[1]
        )
        return _normalize_author_text(author), candidate_title, venue

    title, venue = title_venue
    return _normalize_author_text(author), title, venue


def _split_title_year_venue_tail(
    text: str,
    following_segments: list[str],
) -> tuple[str, str | None] | None:
    normalized = _clean_segment(text)
    inline_match = re.match(
        r"^(?P<title>.+?)\s+(?P<year>(?:19|20)\d{2})\s+(?P<venue>.+)$",
        normalized,
    )
    if inline_match is not None:
        title = _clean_segment(inline_match.group("title"))
        venue = _clean_segment(
            f"{inline_match.group('year')} {inline_match.group('venue')}"
        )
        if _looks_like_title_segment(title) and (
            _looks_like_venue(venue) or _looks_like_journal_tail(venue)
        ):
            if following_segments:
                venue = _clean_segment(
                    ", ".join([venue, *following_segments]).strip(" ,;")
                )
            return title, venue

    trailing_year_match = re.match(
        r"^(?P<title>.+?)\s+(?P<year>(?:19|20)\d{2})$",
        normalized,
    )
    if trailing_year_match is None or not following_segments:
        return None
    title = _clean_segment(trailing_year_match.group("title"))
    venue_tail = ", ".join(following_segments).strip(" ,;")
    if not venue_tail:
        return None
    venue = _clean_segment(f"{trailing_year_match.group('year')}, {venue_tail}")
    if _looks_like_title_segment(title) and (
        _looks_like_venue(venue_tail) or _looks_like_journal_tail(venue_tail)
    ):
        return title, venue
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


def _split_compact_initial_connective_author_segment(segment: str) -> list[str] | None:
    normalized = _clean_segment(segment)
    parts = [
        _clean_segment(part)
        for part in re.split(
            r"\s*(?:and|&)\s*",
            normalized,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if _clean_segment(part)
    ]
    if len(parts) != 2:
        return None

    first = _normalize_compact_initial_author_text(parts[0])
    second = _normalize_compact_initial_author_text(
        _AUTHOR_MARKER_RE.sub("", parts[1])
    )
    if not (_looks_like_author_segment(first) and _looks_like_author_segment(second)):
        return None
    return [first, second]


def _normalize_compact_initial_author_text(text: str) -> str:
    normalized = _normalize_author_text(text)
    match = re.match(
        rf"^(?P<initial>[A-Z])\s+(?P<surname>{_NAME_TOKEN_PATTERN})$",
        normalized,
        flags=re.UNICODE,
    )
    if match is None:
        match = re.match(
            rf"^(?P<surname>{_NAME_TOKEN_PATTERN})\.?\s*"
            rf"(?P<initials>{_INITIAL_CLUSTER_PATTERN})\.?$",
            normalized,
            flags=re.UNICODE,
        )
        if match is None:
            return normalized
        return _clean_segment(
            f"{match.group('surname')} "
            f"{_normalize_initial_cluster(match.group('initials'))}"
        )
    return f"{match.group('initial')}. {match.group('surname')}"


def _split_full_name_author_chain_before_title(
    segments: list[str],
    start_index: int,
) -> tuple[list[str], str, str | None] | None:
    extra_authors: list[str] = []
    max_end = min(len(segments) - 1, start_index + 8)
    index = start_index
    while index < max_end:
        if index + 1 < len(segments):
            surname_given = f"{segments[index]}, {segments[index + 1]}"
            if _parse_surname_given_author_segment(surname_given) is not None:
                extra_authors.append(
                    _normalize_surname_given_author_segment(surname_given)
                )
                index += 2
                continue

        connective_author_title = _split_connective_full_name_author_title_segment(
            segments[index],
            segments[index + 1 :],
        )
        if connective_author_title is not None:
            if not extra_authors:
                return None
            author, title, venue = connective_author_title
            return [*extra_authors, author], title, venue

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

        compact_connective_authors = _split_compact_initial_connective_author_segment(
            segments[index]
        )
        if compact_connective_authors is not None:
            if not extra_authors:
                return None
            extra_authors.extend(compact_connective_authors)
            index += 1
            continue

        marked_author = _split_marked_author_prefix(segments[index])
        if marked_author is not None:
            if not extra_authors:
                return None
            title, marked_authors, venue = marked_author
            venue_parts = [part for part in (venue, *segments[index + 1 :]) if part]
            return (
                [*extra_authors, *(marked_authors or "").split(", ")],
                title,
                ", ".join(venue_parts).strip(" ,;") or None,
            )

        continuation = _split_author_continuation_before_title(segments[index])
        if continuation is not None:
            if not extra_authors:
                return None
            continuation_authors, title, venue = continuation
            following_segments = segments[index + 1 :]
            continuation_title = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", title))
            if (
                following_segments
                and not _starts_with_numeric_citation_tail([following_segments[0]])
                and _PUBLICATION_STATUS_TAIL_RE.fullmatch(following_segments[0]) is None
            ) and (
                continued_title := _split_comma_title_segments_with_following_venue(
                    [continuation_title, *following_segments],
                    0,
                )
            ) is not None:
                title, venue = continued_title
                following_segments = []
            venue_parts = [part for part in (venue, *following_segments) if part]
            return (
                [*extra_authors, *(continuation_authors or "").split(", ")],
                title,
                ", ".join(venue_parts).strip(" ,;") or None,
            )

        if not _looks_like_author_continuation_segment(segments[index]):
            if not extra_authors:
                return None
            connective_initial_title = (
                _split_connective_initial_surname_authors_before_title_segment(
                    segments[index],
                    segments[index + 1 :],
                )
            )
            if connective_initial_title is not None:
                connective_authors, title, venue = connective_initial_title
                return [*extra_authors, *connective_authors], title, venue
            title_venue = _split_title_from_comma_segments_after_author_chain(
                segments,
                index,
            )
            if title_venue is None:
                return None
            title, venue = title_venue
            return extra_authors, title, venue
        extra_authors.append(_normalize_author_text(segments[index]))
        index += 1
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


def _strip_leading_lowercase_author_note_marker(
    segment: str,
    *,
    following_segment: str,
) -> str:
    normalized = _clean_segment(segment)
    match = re.match(r"^[a-z]\s+(?P<author>.+)$", normalized)
    if match is None:
        return normalized
    author = _clean_segment(match.group("author"))
    if not _looks_like_author_segment(author):
        return normalized
    if not (
        _looks_like_author_list(following_segment)
        or _looks_like_author_segment(following_segment)
        or _looks_like_explicit_author_chain_segment(following_segment)
    ):
        return normalized
    return author


def _looks_like_explicit_author_chain_segment(segment: str) -> bool:
    normalized = _clean_segment(segment)
    return bool(
        _has_explicit_author_syntax(normalized)
        or re.search(r"\s+(?:and|&)\s+", normalized, flags=re.IGNORECASE)
    )


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


def _split_connective_full_name_author_title_after_segment(
    segment: str,
    following_segment: str,
    remaining_segments: list[str],
) -> tuple[list[str], str, str | None] | None:
    first_author = _clean_segment(segment)
    if not _looks_like_author_segment(first_author):
        return None

    connective = _split_connective_full_name_author_title_segment(
        following_segment,
        remaining_segments,
    )
    if connective is None:
        return None
    second_author, title, venue = connective
    return [_normalize_author_text(first_author), second_author], title, venue


def _split_connective_full_name_author_title_segment(
    segment: str,
    remaining_segments: list[str],
) -> tuple[str, str, str | None] | None:
    match = re.match(
        r"^(?:and|&)\s+(?P<body>.+)$",
        _clean_segment(segment),
        flags=re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return None

    body = _clean_segment(match.group("body"))
    for period in re.finditer(r"\.\s*", body):
        author_candidate = _AUTHOR_MARKER_RE.sub(
            "",
            _clean_segment(body[: period.start()]),
        )
        suffix = _clean_segment(body[period.end() :])
        if not author_candidate or not suffix:
            continue
        if _looks_like_incomplete_initial_author_before_surname(
            author_candidate,
            suffix,
        ):
            continue
        if not _looks_like_author_segment(author_candidate):
            continue

        suffix = re.sub(r"\.(?=In:)", ". ", suffix)
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_title_after_connective_author_period(candidate_title):
            title_venue = _split_comma_title_segments_with_following_venue(
                [candidate_title, *remaining_segments],
                0,
            )
            if title_venue is None:
                continue
            title, venue = title_venue
            return _normalize_author_text(author_candidate), title, venue

        _, parsed_venue = _split_remainder_authors_venue(remainder)
        venue_head = (
            remainder
            if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
            else parsed_venue or remainder
        )
        venue_parts = [
            part for part in (venue_head, *remaining_segments) if _clean_segment(part)
        ]
        venue = ", ".join(venue_parts).strip(" ,;") or None
        return _normalize_author_text(author_candidate), candidate_title, venue

    return None


def _looks_like_title_after_connective_author_period(text: str) -> bool:
    if _looks_like_publication_title_after_author_prefix(text):
        return True
    normalized = _clean_segment(text)
    words = [word for word in normalized.split() if word]
    if (
        len(normalized) >= 10
        and len(words) >= 2
        and _has_camelcase_title_token(normalized)
        and not _looks_like_venue(normalized)
        and not _looks_like_journal_tail(normalized)
        and not _is_non_publication_title_noise(normalized)
    ):
        return True
    return bool(
        len(normalized) >= 10
        and len(words) >= 2
        and not _looks_like_author_segment(normalized)
        and not _looks_like_venue(normalized)
        and not _looks_like_journal_tail(normalized)
        and not _is_non_publication_title_noise(normalized)
    )


def _looks_like_incomplete_initial_author_before_surname(
    author_candidate: str,
    suffix: str,
) -> bool:
    normalized_author = _clean_segment(author_candidate)
    normalized_suffix = _clean_segment(suffix)
    return bool(
        re.search(r"\b[A-Z]$", normalized_author)
        and re.match(
            r"^[A-Z][A-Za-z'’.-]*\.\s+",
            normalized_suffix,
            flags=re.UNICODE,
        )
    )


def _has_camelcase_title_token(text: str) -> bool:
    return any(
        re.search(r"[a-z][A-Z]", token)
        for token in re.split(r"\s+", _clean_segment(text))
    )


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
        r"IEEE\b|ACM\b|International\s+Journal\b|Journal\s+of\b|J\.\s+of\b|"
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
    segments = [*segments]
    segments[start_index] = _clean_segment(
        _LEADING_YEAR_MARKER_RE.sub("", segments[start_index])
    )
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
        if not _comma_title_candidate_has_continuation_signal(candidate_segments):
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


def _looks_like_comma_title_continuation_segment(segment: str) -> bool:
    normalized = _clean_segment(segment)
    if not normalized:
        return False
    if _starts_with_numeric_citation_tail([normalized]):
        return False
    if _PUBLICATION_STATUS_TAIL_RE.fullmatch(normalized):
        return False
    if re.match(r"^(?:and|&)\s+", normalized, flags=re.IGNORECASE):
        return True
    if _looks_like_venue(normalized) or _looks_like_journal_tail(normalized):
        return False
    return bool(re.match(r"^[a-z][A-Za-z0-9-]*(?:\b|\d)", normalized))


def _comma_title_candidate_has_continuation_signal(segments: list[str]) -> bool:
    continuation_segments = segments[1:]
    if not continuation_segments:
        return False
    if all(
        _looks_like_comma_title_continuation_segment(segment)
        for segment in continuation_segments
    ):
        return True
    return any(
        re.match(r"^(?:and|&)\s+", _clean_segment(segment), flags=re.IGNORECASE)
        is not None
        for segment in continuation_segments
    )


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
        candidate = ", ".join(candidate_segments).strip(" ,;")
        title, venue_head = _split_title_and_remainder(candidate)
        if not venue_head or title == candidate:
            continue
        if not _looks_like_publication_title_after_author_prefix(title):
            continue
        if not (_looks_like_venue(venue_head) or _looks_like_journal_tail(venue_head)):
            continue
        if not following_segments:
            return _strip_duplicate_bare_venue_tail(title, venue_head)
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
    for match in re.finditer(r"\(?\b(?:19|20)\d{2}\b\)?[.),，]?\s+", text):
        prefix = _clean_segment(text[: match.start()]).rstrip(" ,，.;；(（")
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

        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, authors, venue
    return None


def _split_surname_given_year_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"[\(（]?\b(?:19|20)\d{2}\b[\)）]?", text):
        prefix = _clean_segment(text[: match.start()]).rstrip(" .。．,(（")
        suffix = _clean_segment(text[match.end() :]).lstrip(" .。．")
        suffix = re.sub(r"^\[[^\]]{1,30}\]\s*[.。．]?\s*", "", suffix)
        if not prefix or not suffix:
            continue
        authors = _parse_surname_given_author_prefix(prefix)
        if not authors:
            continue
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
            venue = venue or remainder or None
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            words = [word for word in candidate_title.split() if word]
            if not (
                venue
                and len(words) >= 2
                and not _is_non_publication_title_noise(candidate_title)
            ):
                continue
        return candidate_title, ", ".join(authors), venue
    return None


def _split_dense_comma_author_year_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    segments = [
        _clean_segment(segment)
        for segment in re.split(r"[,，]", text)
        if _clean_segment(segment)
    ]
    if len(segments) < 4:
        return None

    for year_index, segment in enumerate(segments):
        if re.fullmatch(r"(?:19|20)\d{2}\.?", segment) is None:
            continue
        if year_index < 2 or year_index + 1 >= len(segments):
            continue

        authors = _parse_dense_comma_author_prefix(segments[:year_index])
        if len(authors) < 2:
            continue

        suffix = _strip_leading_year_month_title_prefix(
            ", ".join(segments[year_index + 1 :])
        )
        title, remainder = _split_title_and_remainder(suffix)
        candidate_title = title or suffix
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        if _title_result_needs_author_prefix_fallback(candidate_title):
            continue

        if (
            _looks_like_publication_status_venue_tail(remainder)
            or _looks_like_venue(remainder)
            or _looks_like_journal_tail(remainder)
        ):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
            venue = venue or remainder or None
        return candidate_title, ", ".join(authors), venue
    return None


def _parse_dense_comma_author_prefix(segments: list[str]) -> list[str]:
    authors: list[str] = []
    index = 0
    while index < len(segments):
        segment = segments[index]

        if re.fullmatch(r"et\s+a(?:l\.?|[;/]+)", segment, flags=re.IGNORECASE):
            if not authors or index != len(segments) - 1:
                return []
            authors.append(_normalize_author_text(segment))
            index += 1
            continue

        if index + 1 < len(segments):
            surname_given = f"{segment}, {segments[index + 1]}"
            if _parse_surname_given_author_segment(surname_given) is not None:
                authors.append(_normalize_surname_given_author_segment(surname_given))
                index += 2
                continue

        if _looks_like_author_segment(segment) or _looks_like_author_list(segment):
            authors.append(_normalize_author_list(segment))
            index += 1
            continue

        return []
    return authors


def _split_comma_surname_author_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if "," not in text and "，" not in text:
        return None

    for match in reversed(list(re.finditer(r"[,，]\s+", text))):
        prefix = _clean_segment(text[: match.start()])
        suffix = _strip_leading_year_month_title_prefix(text[match.end() :])
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
            if _should_skip_initial_only_suffix_continuation(
                prefix,
                extra_authors,
            ):
                continue
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


def _should_skip_initial_only_suffix_continuation(
    prefix: str,
    extra_authors: str,
) -> bool:
    first_extra_author = _clean_segment(
        re.split(r"[,，]", extra_authors, maxsplit=1)[0]
    )
    if re.fullmatch(_INITIAL_CLUSTER_PATTERN, first_extra_author) is None:
        return False

    prefix_parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", prefix)
        if _clean_segment(part)
    ]
    if not prefix_parts:
        return False
    return _is_single_author_name_token(prefix_parts[-1])


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
    suffix = _strip_leading_year_month_title_prefix(suffix)
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
        suffix = _strip_leading_year_month_title_prefix(text[match.end() :])
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
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        suffix_is_title_with_venue = bool(
            _looks_like_publication_title_after_author_prefix(candidate_title)
            and not _title_has_author_prefix_contamination(candidate_title)
            and (
                _looks_like_venue(remainder)
                or _looks_like_journal_tail(remainder)
            )
        )
        if _suffix_starts_with_author_continuation(
            suffix
        ) or _starts_with_author_continuation(suffix):
            if suffix_is_title_with_venue:
                venue = remainder
                return (
                    candidate_title,
                    _normalize_semicolon_surname_author_list(prefix),
                    venue,
                )
            continue
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
    text = _strip_leading_year_month_title_prefix(text)
    title, remainder = _split_title_and_remainder(text)
    period_venue_head = _move_trailing_period_venue_head_from_title(title, remainder)
    if period_venue_head is not None:
        return period_venue_head
    title_venue_head = _move_trailing_venue_head_from_title(title, remainder)
    if title_venue_head is not None:
        return title_venue_head
    question_split = _split_title_venue_on_question_tail(text)
    if question_split is not None:
        return question_split
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


def _move_trailing_period_venue_head_from_title(
    title: str,
    remainder: str,
) -> tuple[str, str] | None:
    clean_title = _clean_segment(title)
    clean_remainder = _clean_segment(remainder)
    if not clean_title or not clean_remainder or ". " not in clean_title:
        return None
    parts = [_clean_segment(part) for part in clean_title.split(". ")]
    for venue_part_count in range(min(2, len(parts) - 1), 0, -1):
        title_head = _clean_segment(". ".join(parts[:-venue_part_count]))
        venue_head = _clean_segment(". ".join(parts[-venue_part_count:]))
        if not title_head or not venue_head:
            continue
        if not (
            _looks_like_venue(venue_head)
            or _looks_like_journal_tail(venue_head)
            or _looks_like_bibliographic_venue_name(venue_head)
            or _looks_like_abbreviated_venue_fragment(venue_head)
            or _looks_like_abbreviated_venue_head(venue_head)
            or _ABBREVIATED_JOURNAL_RE.fullmatch(venue_head)
        ):
            continue
        if not _looks_like_publication_title_after_author_prefix(title_head):
            continue
        separator = " " if venue_head.endswith(".") else ". "
        return title_head, f"{venue_head}{separator}{clean_remainder}"
    return None


def _looks_like_abbreviated_venue_head(text: str) -> bool:
    parts = [
        _clean_segment(part)
        for part in re.split(r"\.\s*", text)
        if _clean_segment(part)
    ]
    return bool(parts and all(_looks_like_abbreviated_venue_fragment(part) for part in parts))


def _move_trailing_venue_head_from_title(
    title: str,
    remainder: str,
) -> tuple[str, str] | None:
    clean_title = _clean_segment(title)
    clean_remainder = _clean_segment(remainder)
    if not clean_title or not clean_remainder:
        return None
    parts = [
        _clean_segment(part)
        for part in re.split(r"[,，]", clean_title)
        if _clean_segment(part)
    ]
    if len(parts) < 2:
        return None
    venue_head = parts[-1]
    if len(venue_head.split()) > 3:
        return None
    venue_head_is_venue = bool(
        _looks_like_venue(venue_head)
        or _looks_like_journal_tail(venue_head)
        or _looks_like_bibliographic_venue_name(venue_head)
        or _looks_like_abbreviated_venue_fragment(venue_head)
        or _ABBREVIATED_JOURNAL_RE.fullmatch(venue_head)
    )
    if not venue_head_is_venue:
        return None
    combined_venue = _clean_segment(f"{venue_head}. {clean_remainder}")
    if not (
        _looks_like_venue(combined_venue)
        or _looks_like_journal_tail(combined_venue)
        or _looks_like_bibliographic_venue_name(combined_venue)
    ):
        return None
    corrected_title = _clean_segment(", ".join(parts[:-1]))
    if not _looks_like_publication_title_after_author_prefix(corrected_title):
        return None
    return corrected_title, combined_venue


def _comma_remainder_starts_title_continuation(
    *,
    comma_title: str,
    comma_remainder: str,
    period_title: str,
) -> bool:
    continuation = _clean_segment(
        re.split(r"[.。．]", comma_remainder, maxsplit=1)[0]
    )
    if not continuation:
        return False
    expected_title = _clean_segment(f"{comma_title}, {continuation}")
    if expected_title != _clean_segment(period_title):
        return False
    continuation_is_titleish = bool(
        _looks_like_publication_title_after_author_prefix(expected_title)
        and re.search(r"[-/]", f"{comma_title} {continuation}")
    )
    if (
        not continuation_is_titleish
        and (
            _looks_like_venue(continuation)
            or _looks_like_journal_tail(continuation)
            or _looks_like_authors(continuation)
        )
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


def _split_single_marked_author_semicolon_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    if ";" not in text and "；" not in text:
        return None

    match = re.match(r"^(?P<author>[^;；]{1,80}[*#†‡])\s*[;；]\s*(?P<suffix>.+)$", text)
    if match is None:
        return None
    author_candidate = _clean_segment(match.group("author"))
    if _AUTHOR_MARKER_RE.search(author_candidate) is None:
        return None
    normalized_author = _normalize_author_text(author_candidate)
    if not (
        _looks_like_single_author_token_before_title(normalized_author)
        or _looks_like_author_segment(normalized_author)
    ):
        return None

    suffix = _clean_segment(match.group("suffix"))
    semicolon_venue = _split_title_venue_on_semicolon_tail(suffix)
    if semicolon_venue is not None:
        candidate_title, remainder = semicolon_venue
    else:
        title, remainder = _split_title_and_remainder_after_author_prefix(suffix)
        candidate_title = title or suffix
        semicolon_venue = _split_title_venue_on_semicolon_tail(candidate_title)
        if semicolon_venue is not None:
            candidate_title, venue_head = semicolon_venue
            remainder = " ".join(part for part in (venue_head, remainder) if part)
    if not _looks_like_publication_title_after_author_prefix(candidate_title):
        return None
    if _title_has_author_prefix_contamination(candidate_title):
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
        venue = remainder
    else:
        _, venue = _split_remainder_authors_venue(remainder)
    return candidate_title, normalized_author, venue


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

    quote_prefix = _split_chinese_author_quote_prefix(text)
    if quote_prefix is not None:
        return quote_prefix

    period_split = _split_chinese_author_prefix_on_period(text)
    if period_split is not None:
        return period_split

    parts = _split_chinese_author_parts(text)
    if len(parts) < 4:
        return None

    for index in range(2, min(len(parts) - 1, 12)):
        author_parts = parts[:index]
        title = parts[index]
        if not _looks_like_chinese_authorish_prefix_parts(author_parts):
            continue
        if not (
            _looks_like_title_segment(title) or _looks_like_chinese_title_segment(title)
        ):
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

    author_parts = _split_chinese_author_parts(match.group("authors"))
    if not _looks_like_chinese_author_prefix_parts(author_parts):
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


def _split_chinese_author_quote_prefix(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    match = re.match(
        r"^(?P<authors>.+?)[\"“](?P<suffix>.+)$",
        text,
    )
    if match is None:
        return None

    author_parts = _split_chinese_author_parts(match.group("authors"))
    if not _looks_like_chinese_author_prefix_parts(author_parts):
        return None

    suffix = _clean_segment(match.group("suffix"))
    title_match = re.match(
        r"^(?P<title>.+)[\"”]\s*[,，]\s*(?P<venue>.+)$",
        suffix,
    )
    if title_match is not None:
        title = _clean_segment(title_match.group("title"))
        venue = _clean_segment(title_match.group("venue"))
    else:
        title = _clean_segment(suffix.strip("\"”"))
        venue = None

    if not _looks_like_chinese_title_segment(title):
        return None
    return title, _normalize_chinese_author_list(author_parts), venue


def _split_chinese_author_prefix_on_period(
    text: str,
) -> tuple[str, str | None, str | None] | None:
    for match in re.finditer(r"[.。．]\s*", text):
        prefix = _clean_segment(text[: match.start()])
        suffix = _clean_segment(_LEADING_YEAR_MARKER_RE.sub("", text[match.end() :]))
        author_parts = _split_chinese_author_parts(prefix)
        if not _looks_like_chinese_author_prefix_parts(author_parts):
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
        if remainder and re.search(r"[\u4e00-\u9fff]", remainder):
            venue = remainder
        elif _looks_like_compact_chinese_venue_tail(remainder):
            venue = remainder
        else:
            _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_chinese_author_list(author_parts), venue
    return None


def _split_chinese_title_period_tail(text: str) -> tuple[str, str] | None:
    for match in re.finditer(r"[.。．]\s*", text):
        title = _clean_segment(text[: match.start()])
        remainder = _clean_segment(text[match.end() :])
        if title and remainder and _looks_like_title_segment(title):
            return title, remainder
    return None


def _looks_like_chinese_author_list(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    return all(_CHINESE_AUTHOR_SEGMENT_RE.fullmatch(part) for part in parts)


def _split_chinese_author_parts(text: str) -> list[str]:
    return [
        _clean_chinese_author_part(part)
        for part in re.split(r"\s*[,，、&＆]\s*", text)
        if _clean_chinese_author_part(part)
    ]


def _looks_like_chinese_authorish_prefix_parts(parts: list[str]) -> bool:
    if _looks_like_chinese_author_list(parts):
        return True
    if len(parts) < 2:
        return False
    if not any(_CHINESE_AUTHOR_SEGMENT_RE.fullmatch(part) for part in parts):
        return False
    return all(
        _CHINESE_AUTHOR_SEGMENT_RE.fullmatch(part) or _looks_like_author_segment(part)
        for part in parts
    )


def _clean_chinese_author_part(text: str) -> str:
    return _clean_segment(re.sub(r"^\s*[&＆]\s*", "", text))


def _looks_like_chinese_author_prefix_parts(parts: list[str]) -> bool:
    if _looks_like_chinese_author_list(parts):
        return True
    if len(parts) != 1:
        return False
    if _looks_like_compact_marked_chinese_author_chain(parts[0]):
        return True
    stripped = _strip_chinese_et_al_suffix(parts[0])
    if stripped != _clean_segment(parts[0]):
        return bool(_CHINESE_AUTHOR_SEGMENT_RE.fullmatch(stripped))
    return _looks_like_single_chinese_author_name(stripped)


def _normalize_chinese_author_list(parts: list[str]) -> str:
    cleaned: list[str] = []
    for part in parts:
        markerless = _AUTHOR_MARKER_RE.sub("", _clean_chinese_author_part(part))
        if re.search(r"[\u4e00-\u9fff]", markerless):
            cleaned.append(_strip_chinese_et_al_suffix(markerless))
        else:
            cleaned.append(_normalize_author_text(markerless))
    return ", ".join(part for part in cleaned if part)


def _strip_chinese_et_al_suffix(text: str) -> str:
    stripped = re.sub(r"\s+", "", _AUTHOR_MARKER_RE.sub("", _clean_segment(text)))
    return _CHINESE_ET_AL_SUFFIX_RE.sub("", stripped).strip()


def _looks_like_compact_marked_chinese_author_chain(text: str) -> bool:
    normalized = re.sub(r"\s+", "", _clean_segment(text))
    if not re.fullmatch(r"[\u4e00-\u9fff]{4,30}[*#†‡]+", normalized):
        return False
    markerless = _AUTHOR_MARKER_RE.sub("", normalized)
    return bool(markerless and markerless[0] in _COMMON_CHINESE_SURNAMES)


def _looks_like_single_chinese_author_name(text: str) -> bool:
    normalized = _clean_segment(text)
    if not _CHINESE_AUTHOR_SEGMENT_RE.fullmatch(normalized):
        return False
    compact = _AUTHOR_MARKER_RE.sub("", normalized).replace(" ", "")
    if len(compact) < 2:
        return False
    if compact[:2] in _COMMON_TWO_CHAR_CHINESE_SURNAMES:
        return len(compact) >= 3
    return compact[0] in _COMMON_CHINESE_SURNAMES


def _looks_like_compact_chinese_venue_tail(text: str) -> bool:
    normalized = _clean_segment(text)
    if not re.search(r"[\u4e00-\u9fff]", normalized):
        return False
    if not 2 <= len(normalized) <= 16:
        return False
    if re.search(r"[。.!?？]", normalized):
        return False
    return not _looks_like_single_chinese_author_name(normalized)


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
        candidate_title = title or suffix
        if not (
            _looks_like_title_segment(candidate_title)
            or _looks_like_colon_title_after_marked_author_prefix(candidate_title)
        ):
            continue
        _, venue = _split_remainder_authors_venue(remainder)
        return candidate_title, _normalize_marked_author_prefix(prefix), venue
    return None


def _looks_like_colon_title_after_marked_author_prefix(text: str) -> bool:
    normalized = _clean_segment(text)
    if len(normalized) < _MIN_TITLE_LENGTH:
        return False
    if ":" not in normalized and "：" not in normalized:
        return False
    left, right = [
        _clean_segment(part)
        for part in re.split(r"[:：]", normalized, maxsplit=1)
    ]
    if len(left) < 3 or len(right) < _MIN_TITLE_LENGTH:
        return False
    words = [word for word in normalized.split() if word]
    if len(words) < 5:
        return False
    if _has_explicit_author_syntax(normalized) and _looks_like_author_list(normalized):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", normalized))


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
    if _starts_with_ellipsis_author_fragment(text):
        return True

    first_segment = _clean_segment(re.split(r"[,，;；]", text, maxsplit=1)[0])
    if (
        _looks_like_author_segment(first_segment)
        or _looks_like_author_list(first_segment)
        or _looks_like_concatenated_author_name(first_segment)
        or _looks_like_pubmed_author_segment(first_segment)
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
    ellipsis_continuation = _split_ellipsis_author_continuation_before_title(text)
    if ellipsis_continuation is not None:
        return ellipsis_continuation

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
                venue = _clean_segment(remainder) if remainder else None
                extra_authors = _normalize_author_list(leading_with_period)
                nested = _split_author_continuation_before_title(candidate_title)
                if nested is not None:
                    nested_authors, nested_title, nested_venue = nested
                    extra_authors = _merge_nested_author_continuation(
                        extra_authors,
                        nested_authors,
                    )
                    return extra_authors, nested_title, nested_venue or venue
                return extra_authors, candidate_title, venue
            continue
        leading = _clean_segment(text[: match.start()])
        leading = re.sub(r"^\s*s\s+and\s+", "", leading, flags=re.IGNORECASE)
        trailing = text[match.end() :].strip()
        if _starts_with_author_continuation(trailing):
            continue
        title, remainder = _split_title_and_remainder(trailing)
        candidate_title = title or trailing
        leading_is_concatenated_author = _looks_like_concatenated_author_name(leading)
        leading_is_single_author = _looks_like_single_author_token_before_title(
            leading
        )
        if not (
            _looks_like_author_segment(leading)
            or _looks_like_author_list(leading)
            or leading_is_concatenated_author
            or leading_is_single_author
        ):
            continue
        if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
            continue
        venue = _clean_segment(remainder) if remainder else None
        extra_authors = (
            _normalize_concatenated_author_name(leading)
            if leading_is_concatenated_author
            else _normalize_author_list(leading)
        )
        nested = _split_author_continuation_before_title(candidate_title)
        if nested is not None:
            nested_authors, nested_title, nested_venue = nested
            extra_authors = _merge_nested_author_continuation(
                extra_authors,
                nested_authors,
            )
            return extra_authors, nested_title, nested_venue or venue
        return extra_authors, candidate_title, venue
    return None


def _merge_nested_author_continuation(prefix_author: str, nested_authors: str) -> str:
    nested_parts = [part for part in nested_authors.split(", ") if part]
    if nested_parts and _looks_like_incomplete_initial_author_before_surname(
        prefix_author,
        nested_parts[0],
    ):
        separator = "" if prefix_author.endswith(".") else "."
        merged_first = _clean_segment(f"{prefix_author}{separator} {nested_parts[0]}")
        return ", ".join([merged_first, *nested_parts[1:]])
    return f"{prefix_author}, {nested_authors}"


def _split_ellipsis_author_continuation_before_title(
    text: str,
) -> tuple[str, str, str | None] | None:
    match = re.match(
        rf"^(?P<prefix>.+?)\s*,?\s*…\s*&\s*"
        rf"(?P<author>{_NAME_TOKEN_PATTERN},\s*{_INITIAL_CLUSTER_PATTERN})"
        r"\.\s+(?P<trailing>.+)$",
        _clean_segment(text),
        flags=re.UNICODE,
    )
    if match is None:
        return None

    prefix = _clean_segment(match.group("prefix"))
    author = _clean_segment(match.group("author"))
    trailing = _clean_segment(match.group("trailing"))
    if not prefix or not author or not trailing:
        return None

    normalized_author = _normalize_surname_given_author_segment(author)
    title, remainder = _split_title_and_remainder(trailing)
    candidate_title = title or trailing
    if not _looks_like_llm_author_prefix_stripped_title(candidate_title):
        return None
    _, venue = _split_remainder_authors_venue(remainder)
    prefix_authors = _normalize_author_list(prefix)
    authors = ", ".join(part for part in (prefix_authors, normalized_author) if part)
    return authors, candidate_title, venue


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

    no_space_author_suffix = _split_no_space_author_suffix_after_title(text)
    if no_space_author_suffix is not None:
        return _move_author_correspondence_tail(*no_space_author_suffix)

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
            _looks_like_publication_status_venue_tail(remainder)
            or
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


def _split_no_space_author_suffix_after_title(text: str) -> tuple[str, str] | None:
    for match in re.finditer(
        rf"\.\s*(?={_NAME_TOKEN_PATTERN}\s*[,，]\s*(?:[A-Z]\.?\s*){{1,4}})",
        text,
        flags=re.UNICODE,
    ):
        candidate_title = _clean_segment(text[: match.start()])
        remainder = _clean_segment(text[match.end() :])
        if len(candidate_title) < _MIN_TITLE_LENGTH or not remainder:
            continue
        if _has_explicit_author_syntax(candidate_title) and _looks_like_authors(
            candidate_title
        ):
            continue
        if not _looks_like_publication_title_after_author_prefix(candidate_title):
            continue
        if _starts_with_author_continuation(remainder) or _looks_like_authors(
            remainder
        ):
            return candidate_title, remainder
    return None


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
        metric_index = next(
            (
                index
                for index in range(start_index + 1, len(segments))
                if _PUBLICATION_METRIC_METADATA_RE.search(segments[index])
            ),
            None,
        )
        if metric_index is not None and metric_index - start_index <= 2:
            metadata_index = metric_index
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
    for status_index in range(1, len(parts)):
        if not _looks_like_publication_status_venue_tail(parts[status_index]):
            continue
        title = ", ".join(parts[:status_index]).strip(" ,;")
        remainder = ", ".join(parts[status_index:]).strip(" ,;")
        if not _looks_like_title_segment(title):
            continue
        return title, remainder
    return None


def _looks_like_publication_status_venue_tail(text: str) -> bool:
    tail = _clean_segment(text)
    return (
        _PUBLICATION_STATUS_TAIL_RE.fullmatch(tail) is not None
        or _PUBLICATION_STATUS_VENUE_TAIL_RE.match(tail) is not None
    )


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

    for index in range(1, len(parts)):
        title = "; ".join(parts[:index]).strip(" ;")
        remainder = "; ".join(parts[index:]).strip(" ;")
        venue_head = parts[index]
        if len(title) < _MIN_TITLE_LENGTH:
            continue
        if _looks_like_semicolon_venue_tail(venue_head):
            return title, remainder

    title = "; ".join(parts[:-1]).strip(" ;")
    remainder = parts[-1].strip(" ;")
    if len(title) < _MIN_TITLE_LENGTH:
        return None
    if len(remainder) <= 60 and _looks_like_semicolon_venue_tail(remainder):
        return title, remainder
    return None


def _looks_like_semicolon_venue_tail(text: str) -> bool:
    normalized = _clean_segment(text)
    if not normalized:
        return False
    return bool(
        _looks_like_venue(normalized)
        or _looks_like_journal_tail(normalized)
        or _looks_like_bibliographic_venue_name(normalized)
        or normalized.casefold() in _SHORT_SINGLE_WORD_JOURNAL_TITLES
    )


def _split_title_venue_on_question_tail(text: str) -> tuple[str, str] | None:
    match = re.match(r"^(?P<title>.+?\?)\s+(?P<remainder>.+)$", _clean_segment(text))
    if match is None:
        return None
    title = _clean_segment(match.group("title"))
    remainder = _clean_segment(match.group("remainder"))
    if len(title) < _MIN_TITLE_LENGTH or not remainder:
        return None
    if _looks_like_venue(remainder) or _looks_like_journal_tail(remainder):
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
    if re.match(
        rf"^(?:[A-Z]\.\s*){{1,4}}{_NAME_TOKEN_PATTERN}\.\s+[A-Z]",
        stripped,
        flags=re.UNICODE,
    ):
        return True
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


def _looks_like_title_or_title_with_venue_after_author_prefix(text: str) -> bool:
    normalized = _clean_segment(text)
    if not normalized:
        return False
    title, remainder = _split_title_and_remainder_after_author_prefix(normalized)
    candidate_title = title or normalized
    if not _looks_like_publication_title_after_author_prefix(candidate_title):
        return False
    if _title_has_author_prefix_contamination(candidate_title):
        return False
    if remainder and (
        _looks_like_venue(remainder) or _looks_like_journal_tail(remainder)
    ):
        return True
    return bool(
        re.search(r"[-:：?？]", candidate_title)
        or re.search(r"[,，]", candidate_title)
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
    if _looks_like_concatenated_author_name(text):
        return True
    if _looks_like_pubmed_author_segment(text):
        return True
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
    allowed_lower = {
        "and",
        "geochemistry",
        "health",
        "in",
        "international",
        "of",
        "on",
        "research",
        "technology",
        "the",
        "with",
    }
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
        if _is_publications_heading_text(
            tag.get_text(" ", strip=True)
        ) or _is_research_heading_with_publication_citations(tag):
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
        _extract_from_paragraphs,
        _extract_from_list,
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

    raw_entries: list[_ParagraphPublicationText] = []
    for paragraph in _iter_section_descendants(section, {"p"}):
        source_anchor = _extract_source_anchor(paragraph, page_url)
        pdf_url = _extract_pdf_url(paragraph, page_url)
        for raw_text in _publication_texts_from_paragraph(paragraph):
            raw_entries.append(
                _ParagraphPublicationText(
                    text=raw_text,
                    source_anchor=source_anchor,
                    pdf_url=pdf_url,
                )
            )

    items: list[HomepagePublication] = []
    for raw_entry in _merge_numbered_paragraph_publication_texts(raw_entries):
        publication = _publication_from_text(
            raw_text=raw_entry.text,
            source_url=page_url,
            source_anchor=raw_entry.source_anchor,
            pdf_url=raw_entry.pdf_url,
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
    if not raw_text:
        return [raw_text] if raw_text else []

    item_starts = _numbered_publication_item_starts(raw_text)
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


def _numbered_publication_item_starts(raw_text: str) -> list[re.Match[str]]:
    starts: list[re.Match[str]] = []
    for match in _NUMBERED_ITEM_START_RE.finditer(raw_text):
        token = match.group(0).strip()
        if _YEAR_RE.search(token):
            continue
        prefix = raw_text[: match.start()].rstrip()
        if prefix and prefix[-1].isalnum():
            continue
        starts.append(match)
    return starts


def _merge_numbered_paragraph_publication_texts(
    entries: list[_ParagraphPublicationText],
) -> list[_ParagraphPublicationText]:
    if not any(_starts_with_publication_item_prefix(entry.text) for entry in entries):
        return entries

    merged: list[_ParagraphPublicationText] = []
    for entry in entries:
        text = _normalize_sentence(entry.text)
        if not text:
            continue
        if not merged or _starts_with_publication_item_prefix(text):
            merged.append(
                _ParagraphPublicationText(
                    text=text,
                    source_anchor=entry.source_anchor,
                    pdf_url=entry.pdf_url,
                )
            )
            continue
        previous = merged[-1]
        if _should_merge_publication_paragraph_continuation(previous.text, text):
            merged[-1] = _ParagraphPublicationText(
                text=_normalize_sentence(f"{previous.text} {text}"),
                source_anchor=previous.source_anchor or entry.source_anchor,
                pdf_url=previous.pdf_url or entry.pdf_url,
            )
            continue
        merged.append(
            _ParagraphPublicationText(
                text=text,
                source_anchor=entry.source_anchor,
                pdf_url=entry.pdf_url,
            )
        )
    return merged


def _starts_with_publication_item_prefix(text: str) -> bool:
    return _ITEM_PREFIX_RE.match(_normalize_sentence(text)) is not None


def _should_merge_publication_paragraph_continuation(
    previous_text: str,
    current_text: str,
) -> bool:
    previous = _normalize_sentence(previous_text)
    current = _normalize_sentence(current_text)
    if not previous or not current:
        return False
    if _starts_with_publication_item_prefix(current):
        return False
    if _is_publications_heading_text(current) or _looks_like_biography_prose(current):
        return False
    if _URL_ONLY_RE.fullmatch(current):
        return False
    if not _starts_with_publication_item_prefix(previous):
        return False
    if _looks_like_standalone_publication_citation(current):
        return False
    return True


def _looks_like_standalone_publication_citation(text: str) -> bool:
    title_text, authors_text, venue_text = _split_title_authors_venue(text)
    if not authors_text:
        return False

    clean_title = _clean_publication_title_segment(
        title_text,
        authors_text=authors_text,
    )
    if not _looks_like_publication_title_after_author_prefix(clean_title):
        return False
    if _is_non_publication_title_noise(clean_title):
        return False
    return bool(venue_text or _extract_year_from_text(text))


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
    authors_value = _clean_author_display_segment(authors_value) if authors_value else None
    venue_value = (
        _clean_segment(_strip_item_suffix(venue_value)) if venue_value else None
    )
    if author_filter is not None and not author_filter(authors_value):
        return None

    publication = HomepagePublication(
        raw_title=normalized,
        clean_title=clean_title,
        authors_text=authors_value,
        venue_text=venue_value,
        year=year_value,
        source_url=source_url,
        source_anchor=source_anchor,
        pdf_url=pdf_url,
    )
    return publication


def _clean_author_display_segment(text: str) -> str:
    cleaned = _clean_segment(text)
    cleaned = _AUTHOR_NOTE_RE.sub("", cleaned)
    cleaned = re.sub(r"[(（]\s*$", "", cleaned)
    return cleaned.strip(" ,;，；")


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
        "老师长期从事",
        "长期从事",
        "主要从事",
        "研究工作",
        "应用领域包括",
        "着重研究",
        "此外",
        "业绩突出",
        "产生了显著",
        "发表SCI收录论文",
        "已发表专业论文",
        "专利授权",
        "成果转化",
        "荣誉",
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
    return tag.name in _HEADING_TAG_NAMES and (
        _is_publications_heading_text(tag.get_text(" ", strip=True))
        or _is_research_heading_with_publication_citations(tag)
    )


def _is_research_heading_with_publication_citations(tag: Tag) -> bool:
    if tag.name not in _HEADING_TAG_NAMES:
        return False
    normalized = _strip_heading_trailing_punctuation(tag.get_text(" ", strip=True))
    if normalized.casefold() not in _RESEARCH_PUBLICATION_HEADING_TEXTS:
        return False

    current_level = int(tag.name[1])
    citation_count = 0
    for block in _following_section_blocks(tag, current_level=current_level):
        if not isinstance(block, Tag):
            continue
        paragraphs = (
            [block]
            if block.name in {"p", "li"}
            else list(block.find_all(["p", "li"]))
        )
        for paragraph in paragraphs:
            text = paragraph.get_text(" ", strip=True)
            if _looks_like_research_publication_paragraph(text):
                citation_count += 1
                if citation_count >= 2:
                    return True
    return False


def _looks_like_research_publication_paragraph(text: str) -> bool:
    normalized = _normalize_sentence(text)
    if len(normalized) < 40:
        return False
    if _looks_like_biography_prose(normalized):
        return False
    if not (
        _extract_year_from_text(normalized) is not None
        or re.search(r"\b(?:submitted|to appear|accepted)\b", normalized, re.IGNORECASE)
        or re.search(r"\b(?:arxiv|doi)\b", normalized, re.IGNORECASE)
    ):
        return False

    title_text, authors_text, venue_text = _split_title_authors_venue(normalized)
    clean_title = _clean_publication_title_segment(
        title_text,
        authors_text=authors_text,
    )
    if len(clean_title) < _MIN_TITLE_LENGTH:
        return False
    if _is_non_publication_title_noise(clean_title):
        return False
    return bool(venue_text or _extract_year_from_text(normalized) is not None)


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
