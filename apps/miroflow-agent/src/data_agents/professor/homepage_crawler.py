# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Layer 2 — Recursive homepage crawler with LLM structured extraction.

Crawls a professor's personal homepage and up to 5 relevant sub-pages,
then uses LLM to extract structured profile data (education, awards, etc.)
from the concatenated page content.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, ValidationError

from .cross_domain import PaperLink
from .direction_cleaner import clean_directions
from .homepage_publication_headings import _PUBLICATIONS_HEADING_RE
from .models import (
    EducationEntry,
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
    WorkEntry,
)
from .name_utils import (
    derive_english_name_candidates_from_url,
    normalize_english_name,
    sanitize_english_person_name,
    select_best_english_name_candidate,
)
from .translation_spec import LLM_EXTRA_BODY, TRANSLATION_GUIDELINES

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_READER_METADATA_PATTERNS = (
    re.compile(r"\bURL Source:\s*\S+", re.IGNORECASE),
    re.compile(r"\bPublished Time:\s*[^\n]+", re.IGNORECASE),
    re.compile(r"\bMarkdown Content:\s*", re.IGNORECASE),
    re.compile(r"^\s*Title:\s*", re.IGNORECASE | re.MULTILINE),
)
_SUSPICIOUS_TITLE_MARKERS = ("URL Source:", "Published Time:", "Markdown Content:")
_TITLE_TRAILING_CONTACT_RE = re.compile(
    r"\s*(?:电话|联系电话|Phone|Tel)(?:[:：].*)?$",
    re.IGNORECASE,
)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Max sub-pages to crawl per professor
MAX_SUB_PAGES = 5

# Max total chars across all pages sent to LLM
MAX_CONTENT_CHARS = 8000

# Keywords indicating a relevant sub-page
RELEVANT_LINK_KEYWORDS = {
    "publication",
    "paper",
    "research",
    "project",
    "cv",
    "resume",
    "group",
    "lab",
    "award",
    "honor",
    "bio",
    "about",
    "pub",
    "pro",
    "profile",
    "team",
    "member",
    "people",
    "论文",
    "发表",
    "研究",
    "项目",
    "简历",
    "荣誉",
    "获奖",
    "课题组",
    "个人简介",
    "成果",
    "科研",
    "团队",
}
PUBLICATION_LINK_KEYWORDS = {
    "publication",
    "publications",
    "paper",
    "papers",
    "selected publications",
    "selected papers",
    "representative papers",
    "representative publications",
    "journal articles",
    "research output",
    "科研成果",
    "学术成果",
    "代表论文",
    "代表作",
    "论文",
    "发表论文",
    "论著",
    "成果",
}
_PUBLICATION_COUNT_PATTERNS = (
    re.compile(
        r"(?:发表|已发表|累计发表|共发表|在[^。\n]{0,40}?发表)\s*(?:学术|研究|SCI|高水平)?\s*论文\s*([0-9]{1,5})\s*(?:余|多)?\s*篇",
    ),
    re.compile(
        r"(?:发表|已发表|累计发表|共发表)(?:了)?\s*([0-9]{1,5})\s*(?:余|多)?\s*篇\s*(?:学术|研究|SCI|高水平)?\s*论文",
    ),
    re.compile(
        r"(?:published|has published)\s+(?:over|more than|about|approximately)?\s*([0-9]{1,5})\s+(?:research\s+)?(?:papers?|publications?)",
        re.IGNORECASE,
    ),
)
_PUBLICATION_SECTION_MARKERS = tuple(PUBLICATION_LINK_KEYWORDS) + (
    "doi",
    "arxiv",
    "发表于",
    "published in",
)
_PUBLICATION_LINE_BLOCKERS = (
    "教授",
    "副教授",
    "讲席教授",
    "院士",
    "研究员",
    "博士生导师",
    "博士后",
    "硕士",
    "邮箱",
    "邮件",
    "电话",
    "地址",
    "教育经历",
    "工作经历",
    "研究方向",
    "荣誉",
    "获奖",
    "项目",
    "课程",
    "实验室",
    "学院",
    "学校",
    "大学",
    "中心",
    "faculty",
    "research interests",
    "biography",
    "education",
    "employment",
    "award",
    "审稿人",
    "编委",
    "associate editor",
    "guest editor",
    "editorial board",
    "reviewer for",
)
_PUBLICATION_FOOTER_PATTERNS = (
    re.compile(r"\ball rights reserved\b", re.IGNORECASE),
    re.compile(r"\bdesigned by\b", re.IGNORECASE),
    re.compile(
        r"\bcopyright\b.*(?:©|\(c\)|20\d{2}|\ball rights reserved\b)", re.IGNORECASE
    ),
)
_PUBLICATION_SITEWIDE_PATTERNS = (
    re.compile(
        r"(?:学校|学院|学部|我院|本院|全院)[^。\n]{0,40}(?:累计|共)?发表[^。\n]{0,20}(?:论文|SCI|EI|CNS)",
        re.IGNORECASE,
    ),
    re.compile(r"科研人员作为一作|科研人员作为通讯作者|一作或通讯作者", re.IGNORECASE),
)
_OFFICIAL_ANCHOR_TOKEN_STOPWORDS = frozenset(
    {
        "学校",
        "学院",
        "大学",
        "教师",
        "教授",
        "研究",
        "研究方向",
        "科研",
        "学术",
        "博士",
        "硕士",
        "学士",
        "学生",
        "发展",
        "高等教育",
        "影响力",
        "教师发展",
        "管理学",
        "院校",
        "影响",
        "teaching",
        "research",
        "university",
        "college",
        "faculty",
        "department",
        "professor",
        "student",
        "students",
        "education",
    }
)
_SITEWIDE_PUBLICATION_URL_HINTS = (
    "scientific-achievements",
    "research-achievements",
    "colleges/index",
    "科研成果",
    "学院成果",
    "院系总览",
)
_ANCHOR_TOPIC_TOKEN_RE = re.compile(r"[A-Za-z]{4,}|[一-鿿]{3,}")
_OFFICIAL_ANCHOR_BLOCK_HINTS = (
    "introduce",
    "introduce-main",
    "teacher_inner",
    "message-left",
    "message-right",
    "page_content_teacher",
    "content_teacher_box",
    "page_content_detail",
    "v_news_content",
    "main_cont",
    "page_main",
    "site-content",
)
_OFFICIAL_ANCHOR_NAV_BLOCKERS = (
    "本科招生",
    "人才招聘",
    "科研平台",
    "院系设置",
    "学校概览",
    "返回上一级",
    "继续了解",
)
_PUBLICATION_CONTEXT_LINE_PATTERNS = (_PUBLICATIONS_HEADING_RE,)
_RESEARCH_DIRECTION_BLOCKERS = (
    "教育背景",
    "工作经历",
    "学术成果",
    "科研项目",
    "联系方式",
    "个人简介",
    "基本信息",
    "研究成果",
    "招生信息",
    "主讲课程",
    "课程教学",
    "本科课程",
    "荣誉",
    "获奖",
    "教授",
    "副教授",
    "讲师",
    "研究员",
    "院士",
    "博士",
    "硕士",
)
_RESEARCH_DIRECTION_LABELS = (
    "研究方向",
    "研究领域",
    "Research Directions",
    "Research Interests",
)
_NARRATIVE_RESEARCH_PATTERNS = (
    re.compile(r"(?:长期|主要|一直|多年来)\s*从事([^。；;\n]{4,80})"),
    re.compile(r"(?:聚焦于|致力于)\s*([^。；;\n]{4,80})"),
)
_EXTERNAL_ACADEMIC_PROFILE_HOST_HINTS = (
    "researchgate.net",
    "orcid.org",
    "dblp.org",
    "scholar.google",
    "scopus.com",
    "scopus",
    "webofscience.com",
    "semanticscholar.org",
)
_CV_LINK_KEYWORDS = (
    "cv",
    "resume",
    "curriculum vitae",
    "简历",
)
_CV_DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx")
MAX_ANCHORED_FOLLOW_LINKS = 4
MAX_RECURSIVE_SUB_PAGES = 2
_FOLLOW_LINK_HINTS = {
    "homepage",
    "personal homepage",
    "home page",
    "personal website",
    "个人主页",
    "个人网站",
    "主页",
    "课题组",
    "实验室",
    "group",
    "lab",
    "research group",
    "team",
    "publications",
    "publication",
    "papers",
    "selected publications",
    "selected papers",
    "代表论文",
    "论文",
    "科研成果",
}
_BINARY_LINK_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".zip",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
)
_COMPANY_NAME_STOP_KEYWORDS = ()


@dataclass(frozen=True)
class _LinkInfo:
    url: str
    text: str
    title: str | None = None


@dataclass(frozen=True)
class _FetchedPage:
    url: str
    html: str
    publication_candidate: bool = False


@dataclass(frozen=True)
class _OfficialPublicationSignals:
    paper_count: int | None
    top_papers: list[PaperLink]
    evidence_urls: list[str]


class HomepageExtractOutput(BaseModel):
    """Schema for LLM structured extraction from homepage content."""

    name_en: str | None = None
    title: str | None = None
    department: str | None = None
    research_directions: list[str] = []
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    awards: list[str] = []
    academic_positions: list[str] = []


class _AnchoredFollowLinkDecision(BaseModel):
    url: str
    category: str
    priority: int = 3
    should_follow: bool = False
    reason: str = ""


class _AnchoredFollowLinkPlan(BaseModel):
    links: list[_AnchoredFollowLinkDecision] = []


@dataclass(frozen=True)
class _SelectedFollowLink:
    link: _LinkInfo
    category: str
    priority: int


@dataclass(frozen=True)
class HomepageCrawlResult:
    """Result of homepage crawling."""

    profile: EnrichedProfessorProfile
    success: bool
    pages_fetched: int
    error: str | None = None


class _LinkExtractor(HTMLParser):
    """Extract href values from <a> tags, preserving visible anchor text."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[_LinkInfo] = []
        self._current_href: str | None = None
        self._current_title: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = None
            title = None
            for attr_name, attr_value in attrs:
                if attr_name == "href" and attr_value:
                    href = attr_value
                elif attr_name == "title" and attr_value:
                    title = attr_value
            self._current_href = href
            self._current_title = title
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current_href:
            return
        text = re.sub(r"\s+", " ", "".join(self._chunks)).strip()
        self.links.append(
            _LinkInfo(
                url=self._current_href,
                text=text,
                title=self._current_title.strip() if self._current_title else None,
            )
        )
        self._current_href = None
        self._current_title = None
        self._chunks = []


def extract_same_domain_link_infos(html: str, base_url: str) -> list[_LinkInfo]:
    """Extract same-domain links with anchor text and title metadata."""
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []

    base_parsed = urlparse(base_url)
    base_domain = base_parsed.hostname or ""
    base_normalized = base_url.rstrip("/")

    seen: set[str] = set()
    result: list[_LinkInfo] = []

    for item in parser.links:
        href = item.url
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        link_domain = parsed.hostname or ""

        if link_domain != base_domain:
            continue

        normalized = absolute.rstrip("/")
        if normalized == base_normalized:
            continue

        if parsed.scheme not in ("http", "https"):
            continue

        path_lower = parsed.path.lower()
        if any(
            path_lower.endswith(ext)
            for ext in (
                ".pdf",
                ".doc",
                ".docx",
                ".ppt",
                ".pptx",
                ".zip",
                ".jpg",
                ".png",
                ".gif",
            )
        ):
            continue

        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(
            _LinkInfo(
                url=absolute,
                text=item.text,
                title=item.title,
            )
        )

    return result


def extract_same_domain_links(html: str, base_url: str) -> list[str]:
    """Extract links from HTML that belong to the same domain as base_url."""
    return [item.url for item in extract_same_domain_link_infos(html, base_url)]


def filter_relevant_links(
    links: list[str], max_links: int = MAX_SUB_PAGES
) -> list[str]:
    """Filter links by relevance keywords in the URL path."""
    relevant: list[str] = []

    for link in links:
        path = urlparse(link).path.lower()
        # Check if any keyword appears in the path
        if any(keyword in path for keyword in RELEVANT_LINK_KEYWORDS):
            relevant.append(link)
            if len(relevant) >= max_links:
                break

    # If not enough keyword matches, return what we have
    return relevant


def _shared_path_prefix_depth(base_url: str, link_url: str) -> int:
    base_parts = [part for part in urlparse(base_url).path.split("/") if part]
    link_parts = [part for part in urlparse(link_url).path.split("/") if part]
    depth = 0
    for base_part, link_part in zip(base_parts, link_parts, strict=False):
        if base_part != link_part:
            break
        depth += 1
    return depth


def _path_depth(url: str) -> int:
    return len([part for part in urlparse(url).path.split("/") if part])


def _is_generic_homepage_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    return path in {"", "/index.htm", "/index.html", "/home", "/home/index.html"}


def _is_external_academic_profile_host(hostname: str | None) -> bool:
    lowered = (hostname or "").lower()
    return any(hint in lowered for hint in _EXTERNAL_ACADEMIC_PROFILE_HOST_HINTS)


def _select_primary_profile_url(profile: EnrichedProfessorProfile) -> str | None:
    homepage = (profile.homepage or "").strip()
    profile_url = (profile.profile_url or "").strip()
    if profile_url:
        # The roster-discovered official detail page is the authoritative crawl seed.
        # Personal homepages are follow-up targets, not the primary anchor.
        return profile_url
    return homepage or None


def _english_name_tokens(value: str | None) -> tuple[str, ...]:
    normalized = sanitize_english_person_name(value) or normalize_english_name(value)
    if not normalized:
        return ()
    return tuple(token.casefold() for token in normalized.split())


def _is_name_consistent_with_anchor_candidates(
    candidate: str | None,
    anchor_candidates: list[str],
) -> bool:
    candidate_tokens = set(_english_name_tokens(candidate))
    if len(candidate_tokens) < 2:
        return False
    for anchor in anchor_candidates:
        anchor_tokens = set(_english_name_tokens(anchor))
        if len(candidate_tokens & anchor_tokens) >= 2:
            return True
    return False


def _is_teacher_scoped_publication_link(
    link: _LinkInfo,
    *,
    profile: EnrichedProfessorProfile,
    base_url: str,
) -> bool:
    candidate_host = (urlparse(link.url).hostname or "").lower()
    base_host = (urlparse(base_url).hostname or "").lower()
    if candidate_host != base_host:
        return True
    if _shared_path_prefix_depth(base_url, link.url) > 1:
        return True

    combined = " ".join(
        part for part in (link.text, link.title or "", link.url) if part
    )
    if profile.name and profile.name in combined:
        return True
    for anchor_name in derive_english_name_candidates_from_url(base_url):
        tokens = _english_name_tokens(anchor_name)
        lowered = combined.casefold()
        if len(tokens) >= 2 and sum(1 for token in tokens if token in lowered) >= 2:
            return True
    path_lower = urlparse(link.url).path.lower()
    if any(hint in path_lower for hint in _SITEWIDE_PUBLICATION_URL_HINTS):
        return False
    return False


def _filter_selected_follow_link_infos(
    selected: list[_SelectedFollowLink],
    *,
    profile: EnrichedProfessorProfile,
    base_url: str,
) -> list[_SelectedFollowLink]:
    filtered: list[_SelectedFollowLink] = []
    for item in selected:
        if (
            item.category == "publication_page"
            and not _is_teacher_scoped_publication_link(
                item.link,
                profile=profile,
                base_url=base_url,
            )
        ):
            continue
        filtered.append(item)
    return filtered


def _extract_anchor_topic_tokens(text: str, research_topics: list[str]) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for topic in research_topics:
        normalized = re.sub(r"\s+", " ", (topic or "").strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            tokens.append(normalized)
    for match in _ANCHOR_TOPIC_TOKEN_RE.finditer(text or ""):
        token = match.group(0).strip()
        if not token:
            continue
        if any(ord(ch) > 127 for ch in token):
            if len(token) < 3 or token in _OFFICIAL_ANCHOR_TOKEN_STOPWORDS:
                continue
        else:
            if token.casefold() in _OFFICIAL_ANCHOR_TOKEN_STOPWORDS:
                continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _extract_anchor_lines(text: str, patterns: tuple[str, ...]) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern in stripped for pattern in patterns):
            lines.append(stripped)
    return lines[:10]


def _extract_official_anchor_text_from_html(
    *,
    html: str,
    profile: EnrichedProfessorProfile,
) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return _sanitize_page_content(html)

    name = (profile.name or "").strip()
    email = (profile.email or "").strip().lower()
    candidates: list[tuple[int, int, str]] = []

    for node in soup.find_all(("main", "article", "section", "div")):
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) < 20:
            continue
        attrs = " ".join(
            filter(None, [str(node.get("id") or ""), " ".join(node.get("class") or [])])
        ).lower()
        score = 0
        if name and name in text:
            score += 8
        if email and email in text.lower():
            score += 4
        score += sum(3 for hint in _OFFICIAL_ANCHOR_BLOCK_HINTS if hint in attrs)
        score += sum(
            1
            for hint in (
                "研究方向",
                "研究领域",
                "博士",
                "硕士",
                "学士",
                "教授",
                "副教授",
                "研究助理教授",
                "博士生导师",
            )
            if hint in text
        )
        score -= sum(1 for blocker in _OFFICIAL_ANCHOR_NAV_BLOCKERS if blocker in text)
        if len(text) > 2500:
            score -= 3
        if len(text) > 5000:
            score -= 5
        if score <= 0:
            continue
        candidates.append((score, -abs(len(text) - 600), text))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = re.split(r"(?:上一篇|下一篇)[:：]?", candidates[0][2], maxsplit=1)[
            0
        ].strip()
        return selected or candidates[0][2]

    return _sanitize_page_content(html)


def _build_official_anchor_profile(
    *,
    profile: EnrichedProfessorProfile,
    source_url: str,
    main_page_text: str,
    extracted_title: str | None,
    research_topics: list[str],
    english_name_candidates: list[str],
) -> OfficialAnchorProfile:
    topic_tokens = _extract_anchor_topic_tokens(main_page_text, research_topics)
    return OfficialAnchorProfile(
        source_url=source_url,
        title=extracted_title or profile.title,
        email=profile.email,
        bio_text=main_page_text,
        research_topics=research_topics,
        education_lines=_extract_anchor_lines(
            main_page_text, ("博士", "硕士", "学士", "PhD", "MPhil", "BSc", "MSc")
        ),
        award_lines=_extract_anchor_lines(
            main_page_text, ("奖", "荣誉", "Fellow", "会士", "award")
        ),
        work_role_lines=_extract_anchor_lines(
            main_page_text,
            ("教授", "研究员", "院长", "主任", "校长", "chair", "director"),
        ),
        english_name_candidates=english_name_candidates,
        topic_tokens=topic_tokens,
        sparse_anchor=len(topic_tokens) < 3,
    )


def _keyword_score(text: str, keywords: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _score_link_relevance(link: _LinkInfo, base_url: str) -> tuple[int, int]:
    text_score = _keyword_score(
        " ".join(filter(None, (link.text, link.title or ""))), RELEVANT_LINK_KEYWORDS
    )
    path_score = _keyword_score(urlparse(link.url).path.lower(), RELEVANT_LINK_KEYWORDS)
    affinity = _shared_path_prefix_depth(base_url, link.url)
    score = text_score * 3 + path_score + min(affinity, 2)
    return score, affinity


def _score_publication_link(link: _LinkInfo, base_url: str) -> tuple[int, int]:
    text_score = _keyword_score(
        " ".join(filter(None, (link.text, link.title or ""))), PUBLICATION_LINK_KEYWORDS
    )
    path_score = _keyword_score(
        urlparse(link.url).path.lower(), PUBLICATION_LINK_KEYWORDS
    )
    affinity = _shared_path_prefix_depth(base_url, link.url)
    score = text_score * 4 + path_score + min(affinity, 2)
    return score, affinity


def _select_relevant_link_infos(
    links: list[_LinkInfo],
    *,
    base_url: str,
    max_links: int = MAX_SUB_PAGES,
) -> list[_LinkInfo]:
    ranked: list[tuple[tuple[int, int], _LinkInfo]] = []
    for link in links:
        score, affinity = _score_link_relevance(link, base_url)
        if score <= 0:
            continue
        if affinity <= 0 and score < 4:
            continue
        ranked.append(((score, affinity), link))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:max_links]]


def _select_publication_link_infos(
    links: list[_LinkInfo],
    *,
    base_url: str,
    max_links: int = 3,
) -> list[_LinkInfo]:
    ranked: list[tuple[tuple[int, int], _LinkInfo]] = []
    for link in links:
        score, affinity = _score_publication_link(link, base_url)
        if score <= 0:
            continue
        ranked.append(((score, affinity), link))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:max_links]]


def _extract_follow_candidate_link_infos(html: str, base_url: str) -> list[_LinkInfo]:
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []

    seen: set[str] = set()
    result: list[_LinkInfo] = []
    base_normalized = base_url.rstrip("/")
    base_domain = (urlparse(base_url).hostname or "").lower()

    for item in parser.links:
        href = item.url
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = urljoin(base_url, href).strip()
        if not absolute.startswith(("http://", "https://")):
            continue
        normalized = absolute.rstrip("/")
        if normalized == base_normalized or normalized in seen:
            continue
        parsed = urlparse(absolute)
        hostname = (parsed.hostname or "").lower()
        path_lower = parsed.path.lower()
        combined_text = " ".join(
            part for part in (item.text, item.title or "", absolute) if part
        ).lower()
        same_domain = hostname == base_domain
        hinted = any(
            hint in combined_text or hint in path_lower for hint in _FOLLOW_LINK_HINTS
        )
        is_binary = any(path_lower.endswith(ext) for ext in _BINARY_LINK_EXTENSIONS)
        is_cv = is_binary and any(
            keyword in combined_text or keyword in absolute.lower()
            for keyword in _CV_LINK_KEYWORDS
        )
        is_academic_profile = _is_external_academic_profile_host(hostname)

        if same_domain:
            if is_binary and not is_cv:
                continue
            if not hinted and not is_cv:
                continue
        else:
            if not (hinted or is_cv or is_academic_profile):
                continue

        seen.add(normalized)
        result.append(_LinkInfo(url=absolute, text=item.text, title=item.title))
    return result


def _build_follow_link_prompt(
    profile: EnrichedProfessorProfile, candidates: list[_LinkInfo]
) -> str:
    schema = json.dumps(
        _AnchoredFollowLinkPlan.model_json_schema(), ensure_ascii=False, indent=2
    )
    candidate_lines = []
    for index, item in enumerate(candidates, start=1):
        candidate_lines.append(
            f"{index}. url={item.url} | text={item.text or '无'} | title={item.title or '无'}"
        )
    candidate_block = "\n".join(candidate_lines)
    return f"""## 任务目标
你需要从高校官方教师详情页里已经出现的候选链接中，判断哪些链接值得继续递归抓取，以获取该教师本人维护的主页、课题组主页、publication 子页等。

## 教授信息
姓名: {profile.name}
学校: {profile.institution}
院系: {profile.department or "未知"}

## 分类要求
category 只能是以下之一：
- personal_homepage
- lab_or_group
- publication_page
- academic_profile
- cv
- ignore

## 规则
1. 只能基于候选链接本身做判断，不要编造新链接
2. should_follow=true 只用于该教授本人维护主页、课题组主页、publication/论文页，或教师本人官方详情页给出的学术档案/CV
3. academic_profile 用于 ORCID / Google Scholar / DBLP / ResearchGate / Semantic Scholar 等教师个人学术档案
4. cv 用于教师本人简历 PDF / DOC 文档
5. 优先级 1 最高，数字越大优先级越低

## 候选链接
{candidate_block}

## 输出格式
严格输出 JSON：
{schema}
"""


def _parse_follow_link_output(text: str) -> _AnchoredFollowLinkPlan:
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()
    data = _load_first_json_object(content)
    return _AnchoredFollowLinkPlan.model_validate(data)


def _select_llm_follow_link_infos(
    candidates: list[_LinkInfo],
    plan: _AnchoredFollowLinkPlan,
    *,
    max_links: int = MAX_ANCHORED_FOLLOW_LINKS,
) -> list[_SelectedFollowLink]:
    allowed = {
        "personal_homepage",
        "lab_or_group",
        "publication_page",
        "academic_profile",
        "cv",
    }
    by_url = {item.url.rstrip("/"): item for item in candidates}
    selected: list[_SelectedFollowLink] = []
    seen: set[str] = set()
    ordered = sorted(
        (
            decision
            for decision in plan.links
            if decision.should_follow and decision.category in allowed
        ),
        key=lambda decision: (decision.priority, decision.url),
    )
    for decision in ordered:
        key = decision.url.rstrip("/")
        link = by_url.get(key)
        if link is None or key in seen:
            continue
        seen.add(key)
        selected.append(
            _SelectedFollowLink(
                link=link, category=decision.category, priority=decision.priority
            )
        )
        if len(selected) >= max_links:
            break
    return selected


def _classify_follow_link_by_rules(link: _LinkInfo) -> str | None:
    combined_text = " ".join(
        part for part in (link.text, link.title or "", link.url) if part
    ).lower()
    path_lower = urlparse(link.url).path.lower()
    hostname = (urlparse(link.url).hostname or "").lower()

    if _is_external_academic_profile_host(hostname):
        return "academic_profile"
    if any(path_lower.endswith(ext) for ext in _CV_DOCUMENT_EXTENSIONS) and any(
        keyword in combined_text or keyword in link.url.lower()
        for keyword in _CV_LINK_KEYWORDS
    ):
        return "cv"
    if any(
        keyword in combined_text or keyword in path_lower
        for keyword in PUBLICATION_LINK_KEYWORDS
    ):
        return "publication_page"
    return None


def _select_rule_based_follow_link_infos(
    candidates: list[_LinkInfo],
    *,
    base_url: str,
    max_links: int = MAX_ANCHORED_FOLLOW_LINKS,
) -> list[_SelectedFollowLink]:
    priority_map = {
        "academic_profile": 1,
        "cv": 2,
        "publication_page": 3,
    }
    base_hostname = (urlparse(base_url).hostname or "").lower()
    selected: list[_SelectedFollowLink] = []
    seen: set[str] = set()
    for candidate in candidates:
        category = _classify_follow_link_by_rules(candidate)
        if category is None:
            continue
        candidate_hostname = (urlparse(candidate.url).hostname or "").lower()
        if category == "publication_page" and candidate_hostname == base_hostname:
            if _shared_path_prefix_depth(base_url, candidate.url) <= 0:
                continue
        key = candidate.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            _SelectedFollowLink(
                link=candidate,
                category=category,
                priority=priority_map[category],
            )
        )
    selected.sort(key=lambda item: (item.priority, item.link.url))
    return selected[:max_links]


def _collect_recursive_link_infos(
    fetched_pages: list[_FetchedPage],
    *,
    seen_urls: set[str],
    per_page_limit: int = MAX_RECURSIVE_SUB_PAGES,
) -> list[_LinkInfo]:
    recursive: list[_LinkInfo] = []
    for page in fetched_pages[1:]:
        if page.publication_candidate:
            continue
        link_infos = extract_same_domain_link_infos(page.html, page.url)
        publication_links = _select_publication_link_infos(
            link_infos, base_url=page.url, max_links=per_page_limit
        )
        for link in publication_links:
            key = link.url.rstrip("/")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            recursive.append(link)
    return recursive


def _build_extraction_prompt(
    profile: EnrichedProfessorProfile,
    page_content: str,
) -> str:
    """Build LLM prompt for structured extraction from homepage content."""
    schema = json.dumps(
        HomepageExtractOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    return f"""## 任务目标
你是一个教授信息采集助手。请从以下教授的个人主页内容中提取结构化信息。

## 教授基本信息
姓名: {profile.name}
学校: {profile.institution}
院系: {profile.department or "未知"}
职称: {profile.title or "未知"}

## 个人主页内容
{page_content[:MAX_CONTENT_CHARS]}

## 提取要求
1. 从页面内容中提取以下信息：英文名（若页面明确出现）、职称、院系、研究方向、教育经历、工作经历、获奖、学术职务
2. 不能编造信息。页面中没有提到的字段留空（空数组或null）
3. 教育经历请包含学校、学位、专业、起止年份
4. 工作经历请包含机构、职位、起止年份
5. 研究方向只提取学术研究主题，不要包含课程名称或教育背景
6. 英文名仅在页面、页面标题或双语链接中明确出现时填写

{TRANSLATION_GUIDELINES}

## 输出格式
严格按以下 JSON Schema 输出，不要包含任何其他文字:
{schema}"""


def _parse_extraction_output(text: str) -> HomepageExtractOutput:
    """Parse LLM response to HomepageExtractOutput."""
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()

    data = _load_first_json_object(content)
    data["education_structured"] = _filter_education_entries(
        data.get("education_structured", [])
    )
    data["work_experience"] = _filter_work_entries(data.get("work_experience", []))
    return HomepageExtractOutput.model_validate(data)


def _load_first_json_object(text: str) -> dict[str, Any]:
    """Return the first valid JSON object embedded in model output."""
    stripped = text.strip()
    if not stripped:
        raise json.JSONDecodeError("empty JSON payload", text, 0)

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as first_error:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", stripped):
            candidate = stripped[match.start() :]
            try:
                parsed, _ = decoder.raw_decode(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise first_error

    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("top-level JSON value is not an object", stripped, 0)
    return parsed


def _filter_education_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        school = item.get("school") or item.get("institution")
        if not school:
            continue
        normalized = dict(item)
        normalized["school"] = school
        filtered.append(normalized)
    return filtered


def _filter_work_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        organization = item.get("organization") or item.get("institution")
        if not organization:
            continue
        normalized = dict(item)
        normalized["organization"] = organization
        filtered.append(normalized)
    return filtered


def _merge_homepage_output(
    profile: EnrichedProfessorProfile,
    output: HomepageExtractOutput,
) -> EnrichedProfessorProfile:
    """Merge homepage extraction into profile, not overwriting existing non-empty fields."""
    updates: dict[str, Any] = {}

    if output.name_en and not profile.name_en:
        normalized_name_en = sanitize_english_person_name(output.name_en)
        if normalized_name_en:
            updates["name_en"] = normalized_name_en
    if output.title and not profile.title:
        sanitized_title = _sanitize_title(output.title)
        if sanitized_title:
            updates["title"] = sanitized_title
    if output.department and not profile.department:
        updates["department"] = output.department
    if output.research_directions and not profile.research_directions:
        updates["research_directions"] = _clean_structured_research_directions(
            output.research_directions
        )
    elif output.research_directions and profile.research_directions:
        # Merge: keep existing + add new cleaned ones
        existing = set(d.lower() for d in profile.research_directions)
        cleaned_new = _clean_structured_research_directions(output.research_directions)
        merged = list(profile.research_directions)
        for d in cleaned_new:
            if d.lower() not in existing:
                existing.add(d.lower())
                merged.append(d)
        updates["research_directions"] = merged
    if output.education_structured and not profile.education_structured:
        updates["education_structured"] = output.education_structured
    if output.work_experience and not profile.work_experience:
        updates["work_experience"] = output.work_experience
    if output.awards and not profile.awards:
        updates["awards"] = output.awards
    if output.academic_positions and not profile.academic_positions:
        updates["academic_positions"] = output.academic_positions

    if updates:
        return profile.model_copy(update=updates)
    return profile


def _extract_official_research_directions(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    candidates: list[str] = []

    for index, line in enumerate(lines):
        if not line:
            continue
        for label in _RESEARCH_DIRECTION_LABELS:
            normalized = line.strip()
            if normalized == label:
                next_value = _next_non_empty_line(lines, index + 1)
                if _looks_like_research_directions(next_value):
                    candidates.append(next_value or "")
                break
            match = re.match(
                rf"^{re.escape(label)}\s*(?:[：:]\s*|\s+)(.+)$",
                normalized,
                flags=re.IGNORECASE,
            )
            if match:
                value = match.group(1).strip()
                if _looks_like_research_directions(value):
                    candidates.append(value)
                break

    for pattern in _NARRATIVE_RESEARCH_PATTERNS:
        for match in pattern.finditer(text):
            candidate = _normalize_narrative_research_direction(match.group(1))
            if _looks_like_research_directions(candidate):
                candidates.append(candidate or "")

    return _clean_structured_research_directions(candidates)


def _normalize_narrative_research_direction(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(
        r"(?:方面)?(?:的)?(?:研究|相关研究|研究工作|工作)$", "", normalized
    )
    normalized = normalized.strip(" ，,;；。")
    if normalized.endswith(("教学", "管理", "人才培养")):
        return None
    return normalized or None


def _sanitize_page_content(content: str) -> str:
    cleaned = content or ""
    cleaned = _HTML_COMMENT_RE.sub("\n", cleaned)
    cleaned = _SCRIPT_STYLE_RE.sub("\n", cleaned)
    cleaned = _HTML_TAG_RE.sub("\n", cleaned)
    cleaned = html.unescape(cleaned)
    for pattern in _READER_METADATA_PATTERNS:
        cleaned = pattern.sub("\n", cleaned)
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _sanitize_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return None
    if any(marker in cleaned for marker in _SUSPICIOUS_TITLE_MARKERS):
        return None
    cleaned = _TITLE_TRAILING_CONTACT_RE.sub("", cleaned).strip(" ,;:/")
    if not cleaned:
        return None
    return cleaned


def _next_non_empty_line(lines: list[str], start_index: int) -> str | None:
    for line in lines[start_index:]:
        normalized = line.strip()
        if normalized:
            return normalized
    return None


def _looks_like_research_directions(value: str | None) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    if len(normalized) > 80:
        return False
    if any(blocker in normalized for blocker in _RESEARCH_DIRECTION_BLOCKERS):
        return False
    return True


def _clean_structured_research_directions(values: list[str]) -> list[str]:
    protected_token = "__COURSE_THOUGHT__"
    protected = [
        value.replace("课程思政", protected_token) for value in values if value
    ]
    cleaned = clean_directions(protected)
    return [value.replace(protected_token, "课程思政") for value in cleaned]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _extract_publication_count(text: str) -> int | None:
    counts: list[int] = []
    for pattern in _PUBLICATION_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                counts.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return max(counts, default=None)


def _normalize_publication_title(line: str) -> str | None:
    if "《" in line and "》" in line:
        match = re.search(r"《([^》]{5,200})》", line)
        if match:
            return match.group(1).strip()
    cleaned = re.sub(r"^\s*(?:\[\d+\]|\d+[.)]|[•*-])\s*", "", line).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*(?:doi|arxiv)\s*[:：].*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" ,;:.")
    return cleaned or None


def _looks_like_publication_title(line: str) -> bool:
    normalized = line.strip()
    if len(normalized) < 20 or len(normalized) > 240:
        return False
    lowered = normalized.lower()
    if any(blocker.lower() in lowered for blocker in _PUBLICATION_LINE_BLOCKERS):
        return False
    if any(pattern.search(normalized) for pattern in _PUBLICATION_FOOTER_PATTERNS):
        return False
    if re.match(r"^\d{4}\s*-\s*(?:\d{4}|present|至今)", lowered):
        return False
    if any(
        marker in lowered
        for marker in (
            "research area",
            "associate professor",
            "assistant professor",
            "ph.d",
            "b. eng",
            "m. eng",
            "postdoc",
            "postdoctoral",
        )
    ):
        return False
    if "@" in normalized or "http://" in lowered or "https://" in lowered:
        return False
    if any(
        marker in lowered
        for marker in ("doi", "arxiv", "proceedings", "journal", "letters")
    ):
        return True
    if "《" in normalized and "》" in normalized:
        return True
    return len(re.findall(r"[A-Za-z]+", normalized)) >= 5


def _extract_publication_titles(text: str, *, limit: int = 5) -> list[PaperLink]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        normalized = _normalize_publication_title(raw_line)
        if not normalized or not _looks_like_publication_title(normalized):
            continue
        candidates.append(normalized)
    return [
        PaperLink(title=title, source="official_site")
        for title in _dedupe_preserve_order(candidates)[:limit]
    ]


def _has_inline_publication_context(text: str) -> bool:
    if _extract_publication_count(text) is not None:
        return True
    for raw_line in text.splitlines():
        normalized = re.sub(r"\s+", " ", raw_line).strip(" ：:-•*#\t")
        if not normalized or len(normalized) > 40:
            continue
        if any(
            pattern.fullmatch(normalized)
            for pattern in _PUBLICATION_CONTEXT_LINE_PATTERNS
        ):
            return True
    return False


def _looks_like_sitewide_publication_page(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PUBLICATION_SITEWIDE_PATTERNS)


def _extract_official_publication_signals(
    pages: list[_FetchedPage],
) -> _OfficialPublicationSignals:
    best_count: int | None = None
    titles: list[PaperLink] = []
    evidence_urls: list[str] = []

    for index, page in enumerate(pages):
        sanitized = _sanitize_page_content(page.html)
        count_allowed = index == 0 or page.publication_candidate
        page_is_sitewide = _looks_like_sitewide_publication_page(sanitized)
        page_count = (
            _extract_publication_count(sanitized)
            if count_allowed and not page_is_sitewide
            else None
        )
        if page_count is not None:
            if best_count is None or page_count > best_count:
                best_count = page_count
            evidence_urls.append(page.url)
        titles_allowed = page.publication_candidate or (
            index == 0 and _has_inline_publication_context(sanitized)
        )
        if titles_allowed and not page_is_sitewide:
            extracted_titles = _extract_publication_titles(sanitized)
            if extracted_titles:
                titles.extend(extracted_titles)
                evidence_urls.append(page.url)

    deduped_titles: list[PaperLink] = []
    seen_titles: set[str] = set()
    for paper in titles:
        key = paper.title.casefold()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped_titles.append(paper)

    return _OfficialPublicationSignals(
        paper_count=best_count,
        top_papers=deduped_titles[:5],
        evidence_urls=_dedupe_preserve_order(evidence_urls),
    )


def _extract_official_link_targets(
    pages: list[_FetchedPage],
) -> tuple[list[str], list[str]]:
    scholarly_profile_urls: list[str] = []
    cv_urls: list[str] = []

    for page in pages:
        if page.publication_candidate:
            continue
        parser = _LinkExtractor()
        try:
            parser.feed(page.html)
        except Exception:
            continue
        for item in parser.links:
            href = item.url
            if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
                continue
            absolute = urljoin(page.url, href).strip()
            if not absolute.startswith(("http://", "https://")):
                continue
            combined_text = " ".join(
                part for part in (item.text, item.title or "") if part
            ).lower()
            path_lower = urlparse(absolute).path.lower()
            hostname = (urlparse(absolute).hostname or "").lower()

            if _is_external_academic_profile_host(hostname):
                scholarly_profile_urls.append(absolute)
            if any(path_lower.endswith(ext) for ext in _CV_DOCUMENT_EXTENSIONS) and any(
                keyword in combined_text or keyword in absolute.lower()
                for keyword in _CV_LINK_KEYWORDS
            ):
                cv_urls.append(absolute)

    return _dedupe_preserve_order(scholarly_profile_urls), _dedupe_preserve_order(
        cv_urls
    )


async def crawl_homepage(
    *,
    profile: EnrichedProfessorProfile,
    fetch_html_fn: Callable,
    llm_client: Any,
    llm_model: str,
    timeout: float = 20.0,
) -> HomepageCrawlResult:
    """Crawl professor's homepage and extract structured data.

    Args:
        profile: The professor profile to enrich.
        fetch_html_fn: Function(url, timeout) -> HtmlFetchResult.
        llm_client: OpenAI-compatible LLM client.
        llm_model: Model name for LLM calls.
        timeout: Timeout for each page fetch.

    Returns:
        HomepageCrawlResult with enriched profile.
    """
    homepage_url = _select_primary_profile_url(profile)
    if not homepage_url:
        return HomepageCrawlResult(
            profile=profile, success=False, pages_fetched=0, error="no_homepage_url"
        )

    # Step 1: Fetch main homepage
    try:
        main_result = fetch_html_fn(homepage_url, timeout)
        main_html = main_result.html if hasattr(main_result, "html") else main_result
    except Exception as e:
        logger.warning("Failed to fetch homepage for %s: %s", profile.name, e)
        return HomepageCrawlResult(
            profile=profile, success=False, pages_fetched=0, error=str(e)
        )

    if not main_html:
        return HomepageCrawlResult(
            profile=profile, success=False, pages_fetched=0, error="empty_html"
        )

    pages_fetched = 1
    fetched_pages: list[_FetchedPage] = [
        _FetchedPage(url=homepage_url, html=main_html, publication_candidate=False)
    ]
    all_content = main_html

    # Step 2-4: From the official detail page, let the LLM decide which anchored targets
    # are worth following. Only LLM-selected anchored pages are recursively fetched.
    selected_follow_links: list[_SelectedFollowLink] = []
    candidate_follow_links = _extract_follow_candidate_link_infos(
        main_html, homepage_url
    )
    fallback_follow_links = _select_rule_based_follow_link_infos(
        candidate_follow_links, base_url=homepage_url
    )
    if candidate_follow_links:
        try:
            follow_prompt = _build_follow_link_prompt(profile, candidate_follow_links)
            follow_response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个教师主页递归抓取助手。请严格按JSON格式输出。",
                    },
                    {"role": "user", "content": follow_prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
                extra_body=LLM_EXTRA_BODY,
            )
            follow_plan = _parse_follow_link_output(
                follow_response.choices[0].message.content
            )
            selected_follow_links = _select_llm_follow_link_infos(
                candidate_follow_links, follow_plan
            )
        except (ValidationError, json.JSONDecodeError, Exception) as e:
            logger.debug(
                "Homepage anchored-link planning failed for %s: %s", profile.name, e
            )

    selected_follow_links = _filter_selected_follow_link_infos(
        selected_follow_links,
        profile=profile,
        base_url=homepage_url,
    )

    if not selected_follow_links:
        selected_follow_links = fallback_follow_links
    else:
        existing_keys = {item.link.url.rstrip("/") for item in selected_follow_links}
        for fallback in fallback_follow_links:
            key = fallback.link.url.rstrip("/")
            if key in existing_keys:
                continue
            if fallback.category in {"academic_profile", "cv"}:
                existing_keys.add(key)
                selected_follow_links.append(fallback)
        selected_follow_links.sort(key=lambda item: (item.priority, item.link.url))

    selected_follow_links = _filter_selected_follow_link_infos(
        selected_follow_links,
        profile=profile,
        base_url=homepage_url,
    )

    seen_urls: set[str] = {homepage_url.rstrip("/")}
    selected_html_links: list[_LinkInfo] = []
    selected_publication_urls: set[str] = set()
    selected_scholarly_profile_urls: list[str] = []
    selected_cv_urls: list[str] = []
    for selected in selected_follow_links:
        key = selected.link.url.rstrip("/")
        if selected.category in {
            "personal_homepage",
            "lab_or_group",
            "publication_page",
        }:
            if key in seen_urls:
                continue
            seen_urls.add(key)
            selected_html_links.append(selected.link)
            if selected.category == "publication_page":
                selected_publication_urls.add(key)
        elif selected.category == "academic_profile":
            selected_scholarly_profile_urls.append(selected.link.url)
        elif selected.category == "cv":
            selected_cv_urls.append(selected.link.url)

    for link in selected_html_links:
        try:
            sub_result = fetch_html_fn(link.url, timeout)
            sub_html = sub_result.html if hasattr(sub_result, "html") else sub_result
            if sub_html:
                all_content += f"\n\n--- {link.url} ---\n{sub_html}"
                fetched_pages.append(
                    _FetchedPage(
                        url=link.url,
                        html=sub_html,
                        publication_candidate=link.url.rstrip("/")
                        in selected_publication_urls,
                    )
                )
                pages_fetched += 1
        except Exception as e:
            logger.debug("Failed to fetch anchored sub-page %s: %s", link.url, e)

    recursive_links = _collect_recursive_link_infos(fetched_pages, seen_urls=seen_urls)
    for link in recursive_links:
        try:
            sub_result = fetch_html_fn(link.url, timeout)
            sub_html = sub_result.html if hasattr(sub_result, "html") else sub_result
            if sub_html:
                all_content += f"\n\n--- {link.url} ---\n{sub_html}"
                fetched_pages.append(
                    _FetchedPage(
                        url=link.url,
                        html=sub_html,
                        publication_candidate=True,
                    )
                )
                pages_fetched += 1
        except Exception as e:
            logger.debug(
                "Failed to fetch recursive publication sub-page %s: %s", link.url, e
            )

    official_publication_signals = _extract_official_publication_signals(fetched_pages)
    anchored_scholarly_profile_urls, anchored_cv_urls = _extract_official_link_targets(
        fetched_pages[1:]
    )
    scholarly_profile_urls = _dedupe_preserve_order(
        selected_scholarly_profile_urls + anchored_scholarly_profile_urls
    )
    cv_urls = _dedupe_preserve_order(selected_cv_urls + anchored_cv_urls)

    # Step 5-6: LLM structured extraction
    sanitized_content = _sanitize_page_content(all_content)
    prompt = _build_extraction_prompt(profile, sanitized_content)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个教授信息采集助手。请严格按JSON格式输出。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        output = _parse_extraction_output(text)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("Homepage LLM extraction failed for %s: %s", profile.name, e)
        return HomepageCrawlResult(
            profile=profile, success=False, pages_fetched=pages_fetched, error=str(e)
        )

    main_anchor_text = _extract_official_anchor_text_from_html(
        html=main_html, profile=profile
    )
    main_sanitized_content = _sanitize_page_content(main_anchor_text)
    official_research_directions = _extract_official_research_directions(
        main_sanitized_content
    )
    if official_research_directions:
        merged_research_directions = _clean_structured_research_directions(
            [*output.research_directions, *official_research_directions]
        )
        if merged_research_directions != output.research_directions:
            output = output.model_copy(
                update={"research_directions": merged_research_directions}
            )

    best_candidate = select_best_english_name_candidate(
        main_sanitized_content,
        url=homepage_url,
    )
    candidate_names = derive_english_name_candidates_from_url(homepage_url)
    if (
        best_candidate
        and candidate_names
        and not _is_name_consistent_with_anchor_candidates(
            best_candidate, candidate_names
        )
    ):
        best_candidate = None
    anchor_name_candidates = _dedupe_preserve_order(
        ([best_candidate] if best_candidate else []) + candidate_names
    )

    if not output.name_en:
        if best_candidate:
            output = output.model_copy(update={"name_en": best_candidate})
        elif candidate_names:
            output = output.model_copy(update={"name_en": candidate_names[0]})
    elif output.name_en:
        normalized_name_en = sanitize_english_person_name(output.name_en)
        if (
            normalized_name_en
            and anchor_name_candidates
            and not _is_name_consistent_with_anchor_candidates(
                normalized_name_en, anchor_name_candidates
            )
        ):
            normalized_name_en = None
        if normalized_name_en:
            output = output.model_copy(update={"name_en": normalized_name_en})
        elif best_candidate:
            output = output.model_copy(update={"name_en": best_candidate})
        elif candidate_names:
            output = output.model_copy(update={"name_en": candidate_names[0]})

    # Step 7-8: Merge into profile
    official_anchor_profile = _build_official_anchor_profile(
        profile=profile,
        source_url=homepage_url,
        main_page_text=main_sanitized_content,
        extracted_title=output.title,
        research_topics=official_research_directions or output.research_directions,
        english_name_candidates=anchor_name_candidates,
    )

    enriched = _merge_homepage_output(profile, output).model_copy(
        update={
            "official_anchor_profile": official_anchor_profile,
        }
    )
    if (
        official_publication_signals.paper_count is not None
        or official_publication_signals.top_papers
        or official_publication_signals.evidence_urls
        or scholarly_profile_urls
        or cv_urls
    ):
        merged_evidence_urls = _dedupe_preserve_order(
            list(enriched.evidence_urls)
            + [page.url for page in fetched_pages]
            + official_publication_signals.evidence_urls
            + scholarly_profile_urls
            + cv_urls
        )
        merged_publication_evidence_urls = _dedupe_preserve_order(
            list(enriched.publication_evidence_urls)
            + official_publication_signals.evidence_urls
        )
        merged_scholarly_profile_urls = _dedupe_preserve_order(
            list(enriched.scholarly_profile_urls) + scholarly_profile_urls
        )
        merged_cv_urls = _dedupe_preserve_order(list(enriched.cv_urls) + cv_urls)
        enriched = enriched.model_copy(
            update={
                "official_paper_count": (
                    official_publication_signals.paper_count
                    if official_publication_signals.paper_count is not None
                    else enriched.official_paper_count
                ),
                "official_top_papers": (
                    official_publication_signals.top_papers
                    if official_publication_signals.top_papers
                    else enriched.official_top_papers
                ),
                "publication_evidence_urls": merged_publication_evidence_urls,
                "scholarly_profile_urls": merged_scholarly_profile_urls,
                "cv_urls": merged_cv_urls,
                "evidence_urls": merged_evidence_urls,
            }
        )

    return HomepageCrawlResult(
        profile=enriched,
        success=True,
        pages_fetched=pages_fetched,
    )
