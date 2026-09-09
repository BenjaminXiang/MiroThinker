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

from ..paper.homepage_http import (
    _HIT_TEACHER_BODY_HEADERS,
    _decode_json_wrapped_html,
    _hit_teacher_body_payload,
    _hit_teacher_body_url,
)
from .cross_domain import PaperLink
from .direction_cleaner import clean_directions
from .homepage_publication_headings import _PUBLICATIONS_HEADING_RE
from .homepage_publications import extract_publications_from_html
from . import hit_playwright_profile as hit_profile
from .models import (
    EducationEntry,
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
    WorkEntry,
)
from .multi_source_crawler import follow_supplementary_links
from .name_utils import (
    derive_english_name_candidates_from_url,
    normalize_english_name,
    sanitize_english_person_name,
    select_best_english_name_candidate,
)
from .publish_helpers import build_professor_id, is_official_url
from .discovery import _decode_response_text, _request_with_env_fallback
from .profile import (
    _find_sztu_fragment_profile_node,
    _extract_sigs_research_topics_from_sections,
    _extract_sigs_tab_sections,
    _extract_uestc_yjsjy_secondary_academic_urls,
    _scope_html_to_fragment_profile,
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
PROFILE_RAW_TEXT_CHARS = 30_000

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
_PUBLICATION_FALLBACK_STOP_HEADINGS = (
    "代表性著作",
    "学术兼职",
    "社会兼职",
    "研究领域",
    "主要项目",
    "科研项目",
    "荣誉奖项",
    "教育背景",
    "工作经历",
    "研究方向",
    "招生信息",
    "联系方式",
    "academic service",
    "professional service",
    "honors",
    "awards",
    "research",
    "projects",
    "teaching",
)
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
_EXTERNAL_PERSONAL_SITE_HOST_HINTS = (
    "github.io",
    "gitlab.io",
    "sites.google.com",
    "pages.dev",
    "netlify.app",
    "vercel.app",
)
_CV_LINK_KEYWORDS = (
    "cv",
    "resume",
    "curriculum vitae",
    "简历",
)
_CV_DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx")
_MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
)
MAX_ANCHORED_FOLLOW_LINKS = 4
MAX_RECURSIVE_SUB_PAGES = 2
MAX_RECURSIVE_PUBLICATION_SUB_PAGES = 2
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
_RECURSIVE_PROFILE_LINK_KEYWORDS = {
    "about",
    "bio",
    "profile",
    "research",
    "project",
    "projects",
    "cv",
    "team",
    "lab",
    "group",
    "people",
    "member",
    "personal",
    "个人简介",
    "简介",
    "研究",
    "项目",
    "简历",
    "团队",
    "课题组",
    "实验室",
}
SOURCE_PAGE_ROLE_PROVENANCE_PREFIX = "source_page_role:"
_FOLLOW_CATEGORY_SOURCE_PAGE_ROLES = {
    "personal_homepage": "personal_homepage",
    "lab_or_group": "lab_homepage",
}
_PERSONAL_HOMEPAGE_LINK_KEYWORDS = (
    "个人主页",
    "个人网站",
    "主页",
    "homepage",
    "home page",
    "personal website",
    "personal page",
)
_OWNED_SOURCE_PAGE_ROLES = frozenset(
    {"official_publication_page", "personal_homepage", "lab_homepage"}
)
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
    email: str | None = None
    profile_summary: str | None = None
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
class _RecursiveFollowLink:
    link: _LinkInfo
    category: str


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


def _is_external_personal_site_host(hostname: str | None) -> bool:
    lowered = (hostname or "").lower()
    return any(
        lowered == hint or lowered.endswith(f".{hint}")
        for hint in _EXTERNAL_PERSONAL_SITE_HOST_HINTS
    )


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
        if _should_ignore_follow_link(item.link):
            continue
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
        parser.links = []

    seen: set[str] = set()
    result: list[_LinkInfo] = []
    base_normalized = base_url.rstrip("/")
    base_domain = (urlparse(base_url).hostname or "").lower()

    for item in [*parser.links, *_extract_markdown_link_infos(html)]:
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
        is_external_personal_site = _is_external_personal_site_host(hostname)

        if same_domain:
            if is_binary and not is_cv:
                continue
            if not hinted and not is_cv:
                continue
        else:
            if not (
                hinted or is_cv or is_academic_profile or is_external_personal_site
            ):
                continue

        seen.add(normalized)
        result.append(_LinkInfo(url=absolute, text=item.text, title=item.title))
    return result


def _extract_markdown_link_infos(markdown: str) -> list[_LinkInfo]:
    return [
        _LinkInfo(url=href.strip(), text=label.strip(), title=None)
        for label, href in _MARKDOWN_LINK_RE.findall(markdown)
        if label.strip() and href.strip()
    ]


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

    if _should_ignore_follow_link(link):
        return None
    if _is_external_academic_profile_host(hostname):
        return "academic_profile"
    if _is_external_personal_site_host(hostname):
        return "personal_homepage"
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
    if _looks_like_lab_or_group_url(link.url) or any(
        keyword in combined_text for keyword in ("课题组", "实验室", "lab", "group")
    ):
        return "lab_or_group"
    if any(keyword in combined_text for keyword in _PERSONAL_HOMEPAGE_LINK_KEYWORDS):
        return "personal_homepage"
    return None


def _has_explicit_personal_homepage_label(link: _LinkInfo) -> bool:
    label = " ".join(part for part in (link.text, link.title or "") if part)
    lowered = label.casefold()
    return any(
        keyword.casefold() in lowered for keyword in _PERSONAL_HOMEPAGE_LINK_KEYWORDS
    )


def _is_szu_navigation_homepage_link(link: _LinkInfo) -> bool:
    parsed = urlparse(link.url)
    hostname = (parsed.hostname or "").lower()
    if not (hostname == "szu.edu.cn" or hostname.endswith(".szu.edu.cn")):
        return False
    if not _is_generic_homepage_url(link.url):
        return False
    label = " ".join(part for part in (link.text, link.title or "") if part)
    if any(token in label for token in ("个人", "课题组", "实验室", "团队")):
        return False
    if any(token in label.casefold() for token in ("personal", "lab", "group")):
        return False
    return any(
        token in label for token in ("学校主页", "学院主页", "首页", "官网", "网站首页")
    )


def _is_suat_navigation_homepage_link(link: _LinkInfo) -> bool:
    parsed = urlparse(link.url)
    hostname = (parsed.hostname or "").lower()
    if not hostname.endswith("suat-sz.edu.cn"):
        return False
    if not _is_generic_homepage_url(link.url):
        return False
    label = " ".join(part for part in (link.text, link.title or "") if part)
    if any(token in label for token in ("个人", "课题组", "实验室", "团队")):
        return False
    if any(token in label.casefold() for token in ("personal", "lab", "group")):
        return False
    return any(
        token in label
        for token in (
            "学校主页",
            "学院主页",
            "首页",
            "官网",
            "网站首页",
            "深圳理工大学",
        )
    )


def _is_navigation_homepage_link(link: _LinkInfo) -> bool:
    return _is_szu_navigation_homepage_link(link) or _is_suat_navigation_homepage_link(
        link
    )


def _is_suat_recruitment_follow_link(link: _LinkInfo) -> bool:
    if _is_suat_recruitment_url(link.url):
        return True
    label = " ".join(part for part in (link.text, link.title or "") if part)
    return "招聘" in label and any(
        token in label for token in ("课题组", "人才", "学院", "教辅", "行政")
    )


def _is_suat_recruitment_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname.endswith("suat-sz.edu.cn"):
        return False
    path_lower = parsed.path.lower()
    return any(token in path_lower for token in ("/rczp", "/zpxx"))


def _should_ignore_follow_link(link: _LinkInfo) -> bool:
    return _is_navigation_homepage_link(link) or _is_suat_recruitment_follow_link(link)


def _without_ignored_supplementary_fetches(fetch_html_fn: Callable) -> Callable:
    def filtered_fetch_html(url: str, timeout: float = 20.0):
        if _is_suat_recruitment_url(url):
            return None
        return fetch_html_fn(url, timeout)

    return filtered_fetch_html


def _looks_like_lab_or_group_url(url: str) -> bool:
    parsed = urlparse(url)
    haystack = " ".join(
        part
        for part in (
            parsed.hostname or "",
            parsed.path or "",
        )
        if part
    ).casefold()
    return any(
        token in haystack for token in ("lab", "group", "team", "课题组", "实验室")
    )


def _same_institutional_domain(left_url: str, right_url: str) -> bool:
    left_host = (urlparse(left_url).hostname or "").casefold()
    right_host = (urlparse(right_url).hostname or "").casefold()
    if not left_host or not right_host:
        return False
    if left_host == right_host:
        return True
    return _institutional_domain_suffix(left_host) == _institutional_domain_suffix(
        right_host
    )


def _institutional_domain_suffix(hostname: str) -> str:
    labels = [label for label in hostname.split(".") if label]
    if len(labels) >= 3 and labels[-2:] == ["edu", "cn"]:
        return ".".join(labels[-3:])
    if len(labels) >= 2:
        return ".".join(labels[-2:])
    return hostname


def _source_page_role_for_follow_link(
    *,
    category: str,
    url: str,
) -> str | None:
    role = _FOLLOW_CATEGORY_SOURCE_PAGE_ROLES.get(category)
    if role is not None:
        return role
    if category != "publication_page":
        return None
    if is_official_url(url):
        return "official_publication_page"
    if _looks_like_lab_or_group_url(url):
        return "lab_homepage"
    return "personal_homepage"


def _source_page_role_provenance(
    source_page_roles: dict[str, str],
) -> dict[str, str]:
    return {
        f"{SOURCE_PAGE_ROLE_PROVENANCE_PREFIX}{url}": role
        for url, role in source_page_roles.items()
        if role in _OWNED_SOURCE_PAGE_ROLES
    }


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
        "lab_or_group": 4,
        "personal_homepage": 5,
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
        if category == "personal_homepage":
            trusted_external_personal_site = _is_external_personal_site_host(
                candidate_hostname
            )
            if (
                not trusted_external_personal_site
                and not _same_institutional_domain(base_url, candidate.url)
                and not _has_explicit_personal_homepage_label(candidate)
            ):
                continue
        if category == "lab_or_group" and not _same_institutional_domain(
            base_url, candidate.url
        ):
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
) -> list[_RecursiveFollowLink]:
    recursive: list[_RecursiveFollowLink] = []
    for page in fetched_pages[1:]:
        if page.publication_candidate:
            continue
        link_infos = extract_same_domain_link_infos(page.html, page.url)
        profile_links = _select_recursive_profile_link_infos(
            link_infos, base_url=page.url, max_links=per_page_limit
        )
        for link in profile_links:
            key = link.url.rstrip("/")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            recursive.append(
                _RecursiveFollowLink(link=link, category="profile_content")
            )

        publication_links = _select_publication_link_infos(
            link_infos,
            base_url=page.url,
            max_links=MAX_RECURSIVE_PUBLICATION_SUB_PAGES,
        )
        for link in publication_links:
            key = link.url.rstrip("/")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            recursive.append(
                _RecursiveFollowLink(link=link, category="publication_page")
            )
    return recursive


def _select_recursive_profile_link_infos(
    links: list[_LinkInfo],
    *,
    base_url: str,
    max_links: int,
) -> list[_LinkInfo]:
    ranked: list[tuple[tuple[int, int], _LinkInfo]] = []
    for link in links:
        if _classify_recursive_link(link) != "profile_content":
            continue
        score, affinity = _score_recursive_profile_link(link, base_url)
        ranked.append(((score, affinity), link))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:max_links]]


def _classify_recursive_link(link: _LinkInfo) -> str | None:
    haystack = " ".join(
        part for part in (link.text, link.title or "", urlparse(link.url).path) if part
    ).casefold()
    if any(keyword in haystack for keyword in PUBLICATION_LINK_KEYWORDS):
        return "publication_page"
    if any(keyword in haystack for keyword in _RECURSIVE_PROFILE_LINK_KEYWORDS):
        return "profile_content"
    return None


def _score_recursive_profile_link(link: _LinkInfo, base_url: str) -> tuple[int, int]:
    text_score = _keyword_score(
        " ".join(filter(None, (link.text, link.title or ""))),
        _RECURSIVE_PROFILE_LINK_KEYWORDS,
    )
    path_score = _keyword_score(
        urlparse(link.url).path.lower(), _RECURSIVE_PROFILE_LINK_KEYWORDS
    )
    affinity = _shared_path_prefix_depth(base_url, link.url)
    score = text_score * 4 + path_score + min(affinity, 2)
    return score, affinity


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


def _extract_sigs_tab_homepage_output(
    html_content: str,
    source_url: str,
) -> HomepageExtractOutput:
    sections = _extract_sigs_tab_sections(html_content, source_url)
    if not sections:
        return HomepageExtractOutput()

    education: list[EducationEntry] = []
    work: list[WorkEntry] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    for section in sections:
        section_key = " ".join([section.tab_label, section.section_title]).casefold()
        if "教育" in section_key or "education" in section_key:
            for line in section.lines:
                for fact_line in _split_sigs_fact_line_entries(line):
                    entry = _parse_sigs_education_line(fact_line)
                    if entry:
                        education.append(entry)
        elif (
            "工作" in section_key
            or "employment" in section_key
            or "experience" in section_key
        ):
            for line in section.lines:
                for fact_line in _split_sigs_fact_line_entries(line):
                    entry = _parse_sigs_work_line(fact_line)
                    if entry:
                        work.append(entry)
        elif (
            "学术兼职" in section_key
            or "社会兼职" in section_key
            or "academic service" in section_key
            or "professional service" in section_key
        ):
            academic_positions.extend(section.lines)
        elif "荣誉" in section_key or "奖励" in section_key or "award" in section_key:
            awards.extend(section.lines)

    return HomepageExtractOutput(
        research_directions=_extract_sigs_research_topics_from_sections(sections),
        education_structured=_dedupe_model_entries(education),
        work_experience=_dedupe_model_entries(work),
        awards=_dedupe_preserve_order(awards),
        academic_positions=_dedupe_preserve_order(academic_positions),
    )


_SIGS_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_SIGS_DATE_RANGE_RE = re.compile(
    r"(?:\d{1,2}[/-])?(?P<start>(?:19|20)\d{2})"
    r"(?:\s*年(?:\s*\d{1,2}\s*月?)?|\.\d{1,2}|/\d{1,2}|-\d{1,2})?\s*"
    r"(?:[-–—~～]\s*|至\s*)"
    r"(?:(?:\d{1,2}[/-])?(?P<end>(?:19|20)\d{2})"
    r"(?:\s*年\s*\d{1,2}\s*月?|\.\d{1,2}|/\d{1,2}|-\d{1,2})?|"
    r"now|present|至?今|今)",
    flags=re.IGNORECASE,
)
_SIGS_INSTITUTION_HINT_RE = re.compile(
    r"University|College|Institute|Academy|School|Laboratory|Center|Centre|SIGS|"
    r"大学|学院|研究院|研究所|实验室|中心",
    flags=re.IGNORECASE,
)
_SIGS_DEGREE_RE = re.compile(
    r"\b(?:Ph\.?D\.?|Doctor|M\.?Sc\.?|M\.?Eng\.?|Master|B\.?Sc\.?|B\.?Eng\.?|Bachelor)\b|"
    r"(?:工学|理学|医学|哲学|管理学|法学|文学|经济学|教育学)?(?:博士|硕士|学士)",
    flags=re.IGNORECASE,
)
_SIGS_ROLE_TITLE_RE = re.compile(
    r"教授|副教授|助理教授|讲席教授|研究员|副研究员|助理研究员|讲师|博士后|博士后研究员|"
    r"访问学者|研究科学家|研究助理|兼职教员|Staff Scientist|Professor|Lecturer|Fellow",
    flags=re.IGNORECASE,
)
_SIGS_INSTITUTION_NAME_RE = re.compile(
    r"[A-Za-z][A-Za-z .&()（）-]{1,80}?"
    r"(?:University|College|Institute|Academy|School|Laboratory|Center|Centre|SIGS)"
    r"|[\u4e00-\u9fffA-Za-z（）()·& -]{2,80}"
    r"(?:研究生院|大学|学院|研究院|研究所|实验室|中心)",
    flags=re.IGNORECASE,
)


def _parse_sigs_education_line(line: str) -> EducationEntry | None:
    cleaned, start_year, end_year = _strip_sigs_year_range(line)
    parts = _split_sigs_fact_parts(cleaned)
    if not parts:
        return None
    if len(parts) == 1:
        compact = _parse_sigs_compact_education_line(
            parts[0], start_year=start_year, end_year=end_year
        )
        if compact:
            return compact

    school_part = _first_matching_part(parts, _SIGS_INSTITUTION_HINT_RE) or parts[0]
    school, embedded_field = _split_sigs_school_and_field(school_part)
    degree = _first_matching_part(parts, _SIGS_DEGREE_RE)
    field_candidates = [part for part in parts if part not in {school_part, degree}]
    field = embedded_field or (field_candidates[0] if field_candidates else None)
    return EducationEntry(
        school=school,
        degree=degree,
        field=field,
        start_year=start_year,
        end_year=end_year,
    )


def _parse_sigs_work_line(line: str) -> WorkEntry | None:
    cleaned, start_year, end_year = _strip_sigs_year_range(line)
    parts = _split_sigs_fact_parts(cleaned)
    if not parts:
        return None
    if len(parts) == 1:
        compact = _parse_sigs_compact_work_line(
            parts[0], start_year=start_year, end_year=end_year
        )
        if compact:
            return compact

    organization = _select_sigs_work_organization(parts)
    if organization:
        role_candidates = [part for part in parts if part != organization]
        role = _first_matching_part(role_candidates, _SIGS_ROLE_TITLE_RE) or (
            role_candidates[-1] if role_candidates else None
        )
    else:
        organization = parts[-1] if len(parts) > 1 else parts[0]
        role = parts[0] if len(parts) > 1 else None
    return WorkEntry(
        organization=organization,
        role=role,
        start_year=start_year,
        end_year=end_year,
    )


def _strip_sigs_year_range(line: str) -> tuple[str, int | None, int | None]:
    normalized = re.sub(r"\s+", " ", line or "").strip()
    range_match = _SIGS_DATE_RANGE_RE.search(normalized)
    if range_match:
        start_year = int(range_match.group("start"))
        end_value = range_match.group("end")
        end_year = int(end_value) if end_value else None
        cleaned = _normalize_sigs_fact_line(
            f"{normalized[: range_match.start()]} {normalized[range_match.end() :]}"
        )
        return cleaned, start_year, end_year

    years = [int(match.group(0)) for match in _SIGS_YEAR_RE.finditer(normalized)]
    start_year = years[0] if years else None
    end_year = None
    if len(years) >= 2 and not re.search(
        r"\b(?:now|present|至今)\b", normalized, re.IGNORECASE
    ):
        end_year = years[1]
    cleaned = _normalize_sigs_fact_line(normalized)
    return cleaned, start_year, end_year


def _split_sigs_fact_line_entries(line: str) -> list[str]:
    normalized = _normalize_sigs_fact_line(line)
    if not normalized:
        return []
    matches = list(_SIGS_DATE_RANGE_RE.finditer(normalized))
    if len(matches) < 2:
        return [normalized]
    entries = [
        normalized_part.strip(" ;；")
        for index, match in enumerate(matches)
        if (
            normalized_part := _normalize_sigs_fact_line(
                normalized[
                    match.start() : (
                        matches[index + 1].start()
                        if index + 1 < len(matches)
                        else len(normalized)
                    )
                ]
            )
        )
    ]
    return entries or [normalized]


def _normalize_sigs_fact_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line or "").strip(" ,，;；")
    cleaned = re.sub(r"^[lL]\s+", "", cleaned)
    return cleaned.strip(" ,，;；")


def _split_sigs_fact_parts(line: str) -> list[str]:
    parts = [
        re.sub(r"\s+", " ", part).strip(" ,，;；")
        for part in re.split(r"\s*,\s*|，", line or "")
    ]
    return [part for part in parts if part]


def _first_matching_part(parts: list[str], pattern: re.Pattern[str]) -> str | None:
    for part in parts:
        if pattern.search(part):
            return part
    return None


def _parse_sigs_compact_education_line(
    line: str,
    *,
    start_year: int | None,
    end_year: int | None,
) -> EducationEntry | None:
    school = _longest_institution_name(line)
    if not school:
        return None
    degree_match = _last_degree_match(line)
    degree = degree_match.group(0) if degree_match else None
    remainder = line.replace(school, " ", 1)
    if degree_match:
        remainder = remainder.replace(degree or "", " ", 1)
    field = re.sub(r"\s+", " ", remainder).strip(" ,，;；")
    return EducationEntry(
        school=school,
        degree=degree,
        field=field or None,
        start_year=start_year,
        end_year=end_year,
    )


def _split_sigs_school_and_field(value: str) -> tuple[str, str | None]:
    normalized = re.sub(r"\s+", " ", value or "").strip(" ,，;；")
    if not normalized:
        return normalized, None
    match = re.match(
        r"^(?P<school>.+?大学)\s*"
        r"(?P<field>[\u4e00-\u9fffA-Za-z&（）() -]{2,40}(?:专业|方向|学科|工程|科学))$",
        normalized,
    )
    if match:
        return (
            match.group("school").strip(" ,，;；"),
            match.group("field").strip(" ,，;；"),
        )
    return normalized, None


def _parse_sigs_compact_work_line(
    line: str,
    *,
    start_year: int | None,
    end_year: int | None,
) -> WorkEntry | None:
    organization = _longest_institution_name(line)
    if not organization:
        return None
    role = line.replace(organization, " ", 1)
    role = re.sub(r"\s+", " ", role).strip(" ,，;；")
    return WorkEntry(
        organization=organization,
        role=role or None,
        start_year=start_year,
        end_year=end_year,
    )


def _select_sigs_work_organization(parts: list[str]) -> str | None:
    organization_parts = [
        part
        for part in parts
        if _SIGS_INSTITUTION_HINT_RE.search(part)
        and not _SIGS_ROLE_TITLE_RE.fullmatch(part)
    ]
    if not organization_parts:
        return None
    first = organization_parts[0]
    if (
        len(organization_parts) >= 2
        and first.endswith("大学")
        and any(marker in organization_parts[1] for marker in ("研究生院", "学院"))
    ):
        return f"{first}{organization_parts[1]}"
    return first


def _longest_institution_name(line: str) -> str | None:
    matches = [
        re.sub(r"\s+", " ", match.group(0)).strip(" ,，;；")
        for match in _SIGS_INSTITUTION_NAME_RE.finditer(line or "")
    ]
    return max(matches, key=len, default=None)


def _last_degree_match(line: str) -> re.Match[str] | None:
    matches = list(_SIGS_DEGREE_RE.finditer(line or ""))
    return matches[-1] if matches else None


def _dedupe_model_entries[T: BaseModel](items: list[T]) -> list[T]:
    seen: set[str] = set()
    result: list[T] = []
    for item in items:
        key = item.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _merge_homepage_extract_outputs(
    primary: HomepageExtractOutput,
    fallback: HomepageExtractOutput,
) -> HomepageExtractOutput:
    if not _has_homepage_extract_output(fallback):
        return primary
    return primary.model_copy(
        update={
            "name_en": primary.name_en or fallback.name_en,
            "title": primary.title or fallback.title,
            "department": primary.department or fallback.department,
            "email": primary.email or fallback.email,
            "profile_summary": primary.profile_summary or fallback.profile_summary,
            "research_directions": _dedupe_preserve_order(
                [*primary.research_directions, *fallback.research_directions]
            ),
            "education_structured": _dedupe_model_entries(
                [*primary.education_structured, *fallback.education_structured]
            ),
            "work_experience": _dedupe_model_entries(
                [*primary.work_experience, *fallback.work_experience]
            ),
            "awards": _dedupe_preserve_order([*primary.awards, *fallback.awards]),
            "academic_positions": _dedupe_preserve_order(
                [*primary.academic_positions, *fallback.academic_positions]
            ),
        }
    )


def _has_homepage_extract_output(output: HomepageExtractOutput) -> bool:
    return bool(
        output.name_en
        or output.title
        or output.department
        or output.email
        or output.profile_summary
        or output.research_directions
        or output.education_structured
        or output.work_experience
        or output.awards
        or output.academic_positions
    )


def _merge_research_directions_preserving_official_terms(
    existing: list[str],
    official_terms: list[str],
) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in merged}
    for term in official_terms:
        normalized = re.sub(r"\s+", " ", term or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return merged


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
    if output.email and not profile.email:
        updates["email"] = output.email
    if output.profile_summary and not profile.profile_summary:
        updates["profile_summary"] = output.profile_summary
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


def _scope_html_to_professor_fragment(html_content: str, source_url: str) -> str:
    scoped = _scope_html_to_fragment_profile(html_content, source_url)
    if scoped:
        return scoped
    try:
        node = _find_sztu_fragment_profile_node(
            BeautifulSoup(html_content, "html.parser"),
            source_url,
        )
    except Exception:
        return html_content
    return str(node) if node is not None else html_content


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
    if _looks_like_publication_service_line(line):
        return None
    if "《" in line and "》" in line:
        match = re.search(r"《([^》]{5,200})》", line)
        if match:
            return match.group(1).strip()
    if _looks_like_publication_pointer_line(line):
        return None
    author_prefixed = _extract_title_from_author_prefixed_publication_line(line)
    if author_prefixed:
        return author_prefixed
    cleaned = re.sub(r"^\s*(?:\[\s*\d+\s*\]|\d+\s*[-.)、]|[•*-])\s*", "", line).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*(?:doi|arxiv)\s*[:：].*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" ,;:.")
    cleaned = _strip_publication_author_residue(cleaned)
    return cleaned or None


def _looks_like_publication_service_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line or "").strip()
    lowered = normalized.casefold()
    service_markers = (
        "审稿人",
        "期刊审稿",
        "reviewer for",
        "reviewer of",
        "reviewer",
        "editorial board",
        "associate editor",
        "guest editor",
        "编委",
    )
    if not any(marker in lowered for marker in service_markers):
        return False
    venue_separators = (
        normalized.count("、") + normalized.count(";") + normalized.count("；")
    )
    latin_abbrev_count = len(re.findall(r"\b[A-Z][A-Za-z]{0,8}\.", normalized))
    return venue_separators >= 1 or latin_abbrev_count >= 2


def _looks_like_publication_title(line: str) -> bool:
    normalized = line.strip()
    if len(normalized) < 20 or len(normalized) > 240:
        return False
    lowered = normalized.lower()
    if _looks_like_publication_pointer_line(normalized):
        return False
    if _looks_like_author_credit_publication_title(normalized):
        return False
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


def _looks_like_publication_pointer_line(line: str) -> bool:
    lowered = (line or "").strip().casefold()
    return lowered.startswith(
        (
            "all publications",
            "all papers",
            "selected publications:",
            "google scholar",
        )
    ) or lowered.startswith(("http://", "https://"))


def _looks_like_author_credit_publication_title(line: str) -> bool:
    normalized = re.sub(
        r"^\s*(?:\[\s*\d+\s*\]|\d+\s*[-.)、]|[•*-])\s*", "", line
    ).strip()
    if len(re.findall(r"\b[A-Z]\.", normalized)) >= 2 and re.search(
        r"[*#]", normalized
    ):
        return True
    if normalized.count(",") >= 3 and re.match(r"^[A-Z][A-Za-z.' -]+,", normalized):
        return True
    return False


def _extract_title_from_author_prefixed_publication_line(line: str) -> str | None:
    cleaned = re.sub(
        r"^\s*(?:\[\s*\d+\s*\]|\d+\s*[-.)、]|[•*-])\s*", "", line or ""
    ).strip()
    if not cleaned:
        return None
    marker_inline_match = re.match(
        r"(?P<authors>.+?[*#])\s*\.\s+(?P<tail>[A-Z][A-Za-z0-9].+)$",
        cleaned,
    )
    if marker_inline_match and "," in marker_inline_match.group("authors"):
        return _title_from_publication_tail(marker_inline_match.group("tail"))

    marker_match = re.match(
        r"(?P<authors>(?:[^,]{1,80},\s*){1,24}[^,]{1,80}[*#])\s*[,，]\s*(?P<tail>.+)$",
        cleaned,
    )
    if marker_match is None:
        marker_period_match = re.match(
            r"(?P<authors>(?:[^,.;]{1,80},\s*){1,24}[^.;]{1,80}[*#])\s*\.\s*"
            r"(?:\((?:19|20)\d{2}\)\s*)?(?P<tail>.+)$",
            cleaned,
        )
        if marker_period_match is not None:
            tail = marker_period_match.group("tail")
        else:
            initial_period_match = re.match(
                r"(?P<authors>(?:[A-Z]\.\s*[^,.;]{2,40},\s*){1,20}"
                r"[A-Z]\.\s*[^,.;]{2,40})\.\s+"
                r"(?:\((?:19|20)\d{2}\)\s*)?(?P<tail>.+)$",
                cleaned,
            )
            if initial_period_match is not None:
                return _title_from_publication_tail(initial_period_match.group("tail"))
            period_match = re.match(
                r"(?P<authors>(?:[^,.;]{2,80},\s*){1,24}"
                r"(?:and\s+)?[^.;]{2,80})\.\s+"
                r"(?:\((?:19|20)\d{2}\)\s*)?(?P<tail>.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if period_match is None:
                return None
            tail = period_match.group("tail")
    else:
        tail = marker_match.group("tail")
    return _title_from_publication_tail(tail)


def _title_from_publication_tail(tail: str) -> str | None:
    tail = re.sub(r"\s+", " ", tail or "").strip(" ,;:.")
    tail = re.sub(r"^\((?:19|20)\d{2}\)\s*", "", tail).strip(" ,;:.")
    if not tail:
        return None
    period_index = tail.find(". ")
    comma_index = tail.find(",")
    if comma_index != -1 and (period_index == -1 or comma_index < period_index):
        title = tail[:comma_index].strip(" ,;:.")
    elif period_index != -1:
        title = tail[:period_index].strip(" ,;:.")
    else:
        title = tail.strip(" ,;:.")
    return title if len(title) >= 20 else None


def _strip_publication_author_residue(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title or "").strip(" ,;:.")
    for pattern in (
        r"^(?:and\s+)?[A-Z](?:\.[A-Z])?\.\s*[A-Z][A-Za-z-]{1,30}\.\s+(?P<title>[A-Z][A-Za-z0-9].+)$",
        r"^[A-Z]\.\s+(?P<title>[A-Z][A-Za-z0-9].+)$",
        r"^[A-Z][A-Za-z-]{1,30}\.\s+(?P<title>[A-Z][A-Za-z0-9].+)$",
        r"^[A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){1,2}\.\s+(?P<title>[A-Z][A-Za-z0-9].+)$",
    ):
        match = re.match(pattern, normalized)
        if match:
            candidate = _title_from_publication_tail(
                match.group("title")
            ) or match.group("title").strip(" ,;:.")
            if len(candidate) >= 20 and len(re.findall(r"[A-Za-z]+", candidate)) >= 4:
                return candidate
    return normalized


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


def _publication_fallback_scan_text(text: str) -> str:
    lines = text.splitlines()
    start_index: int | None = None
    for index, raw_line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", raw_line).strip(" ：:-•*#\t")
        if not normalized or len(normalized) > 80:
            continue
        if any(
            pattern.fullmatch(normalized)
            for pattern in _PUBLICATION_CONTEXT_LINE_PATTERNS
        ):
            start_index = index + 1
            break

    if start_index is None:
        return text

    section_lines: list[str] = []
    for raw_line in lines[start_index:]:
        normalized = re.sub(r"\s+", " ", raw_line).strip(" ：:-•*#\t")
        lowered = normalized.casefold()
        if section_lines and (
            lowered in _PUBLICATION_FALLBACK_STOP_HEADINGS
            or normalized in _PUBLICATION_FALLBACK_STOP_HEADINGS
        ):
            break
        section_lines.append(raw_line)
    return "\n".join(section_lines).strip()


def _extract_structured_publication_titles(
    *,
    html_content: str,
    page_url: str,
    limit: int = 5,
) -> list[PaperLink]:
    publications = extract_publications_from_html(html_content, page_url=page_url)
    candidates: list[PaperLink] = []
    for publication in publications:
        if _looks_like_publication_service_line(publication.raw_title):
            continue
        title = _normalize_publication_title(publication.clean_title)
        if not title or not _looks_like_publication_title(title):
            title = _normalize_publication_title(publication.raw_title)
        if not title:
            continue
        title = _strip_embedded_structured_venue_suffix(
            title,
            raw_title=publication.raw_title,
            year=publication.year,
        )
        if len(title) < 10 or len(title) > 240:
            continue
        if _extract_publication_count(title) is not None:
            continue
        if any(
            marker in title
            for marker in ("代表作有", "目前已发表", "累计发表", "发表论文")
        ):
            continue
        if not _looks_like_publication_title(title):
            continue
        lowered = title.lower()
        if any(blocker.lower() in lowered for blocker in _PUBLICATION_LINE_BLOCKERS):
            continue
        if any(pattern.search(title) for pattern in _PUBLICATION_FOOTER_PATTERNS):
            continue
        candidates.append(
            PaperLink(
                title=title,
                year=publication.year,
                venue=publication.venue_text,
                source="official_site",
            )
        )
    return candidates[:limit]


def _strip_embedded_structured_venue_suffix(
    title: str,
    *,
    raw_title: str,
    year: int | None,
) -> str:
    """Strip a venue that parser left at the end of a structured title.

    This handles lines like ``Title. Sustainable Cities and Society, 2023`` where
    the upstream citation parser missed the venue boundary but did find the year.
    """
    if year is None:
        return title
    raw = re.sub(r"\s+", " ", raw_title or "")
    for match in re.finditer(
        rf"\.\s+(?P<venue>[A-Z][A-Za-z&.' -]{{3,100}})[,，]\s*{year}\b",
        raw,
    ):
        venue = re.sub(r"\s+", " ", match.group("venue")).strip(" .")
        if not _looks_like_embedded_venue_suffix(venue):
            continue
        suffix = f". {venue}"
        if title.endswith(suffix):
            return title[: -len(suffix)].strip(" ,;:.")
    return title


def _looks_like_embedded_venue_suffix(value: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z&.'-]*", value or "")
    if not 2 <= len(words) <= 8:
        return False
    return not any(word.casefold() in {"of", "for", "with"} for word in words[:1])


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


def _has_inline_publication_evidence(
    *,
    html_content: str,
    sanitized_text: str,
    page_url: str,
) -> bool:
    if _extract_publication_count(sanitized_text) is not None:
        return True
    if _extract_structured_publication_titles(
        html_content=html_content,
        page_url=page_url,
        limit=1,
    ):
        return True
    fallback_text = _publication_fallback_scan_text(sanitized_text)
    return bool(_extract_publication_titles(fallback_text, limit=1))


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
            extracted_titles = _extract_structured_publication_titles(
                html_content=page.html,
                page_url=page.url,
            )
            fallback_text = _publication_fallback_scan_text(sanitized)
            fallback_titles = _extract_publication_titles(fallback_text)
            if extracted_titles:
                extracted_titles = _dedupe_paper_links(
                    [*extracted_titles, *fallback_titles]
                )[:5]
            else:
                extracted_titles = fallback_titles
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


def _dedupe_paper_links(papers: list[PaperLink]) -> list[PaperLink]:
    deduped: list[PaperLink] = []
    for paper in papers:
        duplicate_index = _find_duplicate_paper_link_index(deduped, paper)
        if duplicate_index is None:
            deduped.append(paper)
            continue
        if _prefer_paper_link_candidate(paper, deduped[duplicate_index]):
            deduped[duplicate_index] = paper
    return deduped


def _find_duplicate_paper_link_index(
    existing: list[PaperLink],
    candidate: PaperLink,
) -> int | None:
    for index, paper in enumerate(existing):
        if _paper_link_titles_duplicate(paper.title, candidate.title):
            return index
    return None


def _paper_link_titles_duplicate(left: str, right: str) -> bool:
    left_key = _paper_link_title_key(left)
    right_key = _paper_link_title_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    shorter, longer = (
        (left_key, right_key)
        if len(left_key) <= len(right_key)
        else (right_key, left_key)
    )
    if len(shorter) < 20 or not longer.startswith(shorter):
        return False
    tail = longer[len(shorter) :].strip(" .,:;，；")
    if not tail:
        return True
    return (
        bool(re.search(r"\b(?:19|20)\d{2}\b", tail))
        or len(re.findall(r"[a-z][a-z&.'-]*", tail)) <= 8
    )


def _paper_link_title_key(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,:;，；").casefold()


def _prefer_paper_link_candidate(candidate: PaperLink, existing: PaperLink) -> bool:
    if candidate.year is not None and existing.year is None:
        return True
    if candidate.venue and not existing.venue:
        return True
    if len(candidate.title) < len(existing.title):
        return True
    return False


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


def _html_from_fetch_result(result: Any) -> str:
    return result.html if hasattr(result, "html") else str(result or "")


def _fetch_hit_teacher_body(
    *,
    teacher_body_url: str,
    payload: dict[str, str],
    fetch_html_fn: Callable,
    timeout: float,
) -> str:
    try:
        result = fetch_html_fn(
            teacher_body_url,
            timeout,
            method="POST",
            data=payload,
            headers=_HIT_TEACHER_BODY_HEADERS,
        )
    except TypeError:
        response = _request_with_env_fallback(
            "post",
            teacher_body_url,
            timeout=timeout,
            data=payload,
            headers=_HIT_TEACHER_BODY_HEADERS,
        )
        response.raise_for_status()
        return _decode_response_text(response)
    return _html_from_fetch_result(result)


def _augment_hit_homepage_dynamic_body(
    *,
    homepage_url: str,
    html_content: str,
    fetch_html_fn: Callable,
    timeout: float,
) -> str:
    parsed = urlparse(homepage_url)
    hostname = (parsed.hostname or "").lower()
    if hostname != "homepage.hit.edu.cn":
        return html_content

    payload = _hit_teacher_body_payload(html_content)
    if not payload:
        return html_content

    teacher_body_url = _hit_teacher_body_url(parsed)
    try:
        body_response = _fetch_hit_teacher_body(
            teacher_body_url=teacher_body_url,
            payload=payload,
            fetch_html_fn=fetch_html_fn,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Failed to fetch HIT dynamic teacher body %s: %s", homepage_url, exc
        )
        return html_content

    body_html = _decode_json_wrapped_html(body_response)
    if not body_html:
        return html_content
    return f"{html_content}\n\n--- HIT dynamic teacher body ---\n{body_html}"


async def _extract_hit_playwright_homepage_output(
    *,
    homepage_url: str,
    profile: EnrichedProfessorProfile,
    run_id: str | None,
    timeout: float,
) -> tuple[HomepageExtractOutput, str]:
    if not hit_profile.is_hit_profile_url(homepage_url):
        return HomepageExtractOutput(), ""
    if not run_id:
        return HomepageExtractOutput(), ""

    try:
        rendered_html = await hit_profile.render_hit_profile_html_async(
            homepage_url,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "HIT Playwright profile render skipped for %s: %s",
            homepage_url,
            exc,
        )
        return HomepageExtractOutput(), ""

    try:
        if run_id:
            extraction = hit_profile.extract_hit_profile_fields(
                rendered_html,
                source_url=homepage_url,
                professor_id=build_professor_id(profile),
                run_id=str(run_id),
            )
        else:
            extraction = hit_profile.parse_hit_rendered_profile(
                rendered_html,
                source_url=homepage_url,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "HIT Playwright profile parse skipped for %s: %s",
            homepage_url,
            exc,
        )
        return HomepageExtractOutput(), ""

    title = extraction.academic_positions[0] if extraction.academic_positions else None
    output = HomepageExtractOutput(
        title=title,
        department=extraction.department,
        email=extraction.contact_email,
        profile_summary=extraction.profile_summary,
        research_directions=list(extraction.research_directions or []),
        education_structured=list(extraction.education or []),
        work_experience=list(extraction.work_experience or []),
        academic_positions=list(extraction.academic_positions or []),
    )
    return output, extraction.profile_text


async def crawl_homepage(
    *,
    profile: EnrichedProfessorProfile,
    fetch_html_fn: Callable,
    llm_client: Any,
    llm_model: str,
    timeout: float = 20.0,
    run_id: str | None = None,
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

    # Cache every fetch's HTML by URL so the follow-loop can REUSE pages the
    # supplementary phase (follow_supplementary_links) already fetched, instead
    # of re-fetching them (cross-phase double-fetch, e.g. a personal homepage
    # fetched once by supplementary and again by the anchored follow-loop).
    # Forwards *args/**kwargs so the HIT POST path (method=/data=/headers=) works.
    fetched_html_cache: dict[str, str] = {}
    _underlying_fetch_html_fn = fetch_html_fn

    def _caching_fetch_html_fn(url, *args, **kwargs):
        result = _underlying_fetch_html_fn(url, *args, **kwargs)
        html = result.html if hasattr(result, "html") else result
        if html:
            fetched_html_cache[str(url).rstrip("/")] = html
        return result

    fetch_html_fn = _caching_fetch_html_fn

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
    main_html = _augment_hit_homepage_dynamic_body(
        homepage_url=homepage_url,
        html_content=main_html,
        fetch_html_fn=fetch_html_fn,
        timeout=timeout,
    )
    main_html = _scope_html_to_professor_fragment(main_html, homepage_url)
    yjsjy_secondary_academic_urls = list(
        _extract_uestc_yjsjy_secondary_academic_urls(main_html, homepage_url)
    )
    sigs_tab_output = _extract_sigs_tab_homepage_output(main_html, homepage_url)
    (
        hit_rendered_output,
        hit_profile_text,
    ) = await _extract_hit_playwright_homepage_output(
        homepage_url=homepage_url,
        profile=profile,
        run_id=run_id,
        timeout=timeout,
    )
    template_output = _merge_homepage_extract_outputs(
        sigs_tab_output,
        hit_rendered_output,
    )

    pages_fetched = 1
    fetched_pages: list[_FetchedPage] = [
        _FetchedPage(url=homepage_url, html=main_html, publication_candidate=False)
    ]
    all_content = main_html
    supplementary_text_segments = follow_supplementary_links(
        main_html,
        homepage_url,
        professor_name=profile.name,
        max_hops=2,
        fetch_html_fn=_without_ignored_supplementary_fetches(fetch_html_fn),
    )
    if supplementary_text_segments:
        all_content += "\n\n" + "\n\n".join(supplementary_text_segments)

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
    selected_profile_content_urls: set[str] = set()
    selected_scholarly_profile_urls: list[str] = []
    selected_cv_urls: list[str] = []
    selected_source_page_roles: dict[str, str] = {}
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
            source_page_role = _source_page_role_for_follow_link(
                category=selected.category,
                url=selected.link.url,
            )
            if source_page_role is not None:
                selected_source_page_roles[selected.link.url] = source_page_role
            if selected.category == "publication_page":
                selected_publication_urls.add(key)
            else:
                selected_profile_content_urls.add(key)
        elif selected.category == "academic_profile":
            selected_scholarly_profile_urls.append(selected.link.url)
        elif selected.category == "cv":
            selected_cv_urls.append(selected.link.url)

    profile_subpage_content_segments: list[str] = []
    for link in selected_html_links:
        try:
            cache_key = link.url.rstrip("/")
            if cache_key in fetched_html_cache:
                # Reuse HTML already fetched by the supplementary phase; avoids
                # a cross-phase re-fetch of the same URL.
                sub_html = fetched_html_cache[cache_key]
            else:
                sub_result = fetch_html_fn(link.url, timeout)
                sub_html = (
                    sub_result.html if hasattr(sub_result, "html") else sub_result
                )
            if sub_html:
                sanitized_sub_html = _sanitize_page_content(sub_html)
                publication_candidate = link.url.rstrip(
                    "/"
                ) in selected_publication_urls or _has_inline_publication_evidence(
                    html_content=sub_html,
                    sanitized_text=sanitized_sub_html,
                    page_url=link.url,
                )
                all_content += f"\n\n--- {link.url} ---\n{sub_html}"
                fetched_pages.append(
                    _FetchedPage(
                        url=link.url,
                        html=sub_html,
                        publication_candidate=publication_candidate,
                    )
                )
                if link.url.rstrip("/") in selected_profile_content_urls:
                    profile_subpage_content_segments.append(sub_html)
                pages_fetched += 1
        except Exception as e:
            logger.debug("Failed to fetch anchored sub-page %s: %s", link.url, e)

    recursive_links = _collect_recursive_link_infos(fetched_pages, seen_urls=seen_urls)
    for recursive_link in recursive_links:
        link = recursive_link.link
        try:
            cache_key = link.url.rstrip("/")
            if cache_key in fetched_html_cache:
                sub_html = fetched_html_cache[cache_key]
            else:
                sub_result = fetch_html_fn(link.url, timeout)
                sub_html = (
                    sub_result.html if hasattr(sub_result, "html") else sub_result
                )
            if sub_html:
                all_content += f"\n\n--- {link.url} ---\n{sub_html}"
                fetched_pages.append(
                    _FetchedPage(
                        url=link.url,
                        html=sub_html,
                        publication_candidate=recursive_link.category
                        == "publication_page",
                    )
                )
                if recursive_link.category == "profile_content":
                    profile_subpage_content_segments.append(sub_html)
                else:
                    source_page_role = _source_page_role_for_follow_link(
                        category="publication_page",
                        url=link.url,
                    )
                    if source_page_role is not None:
                        selected_source_page_roles[link.url] = source_page_role
                pages_fetched += 1
        except Exception as e:
            logger.debug("Failed to fetch recursive sub-page %s: %s", link.url, e)

    official_publication_signals = _extract_official_publication_signals(fetched_pages)
    anchored_scholarly_profile_urls, anchored_cv_urls = _extract_official_link_targets(
        fetched_pages[1:]
    )
    scholarly_profile_urls = _dedupe_preserve_order(
        yjsjy_secondary_academic_urls
        + selected_scholarly_profile_urls
        + anchored_scholarly_profile_urls
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
        if _has_homepage_extract_output(template_output):
            output = template_output
        else:
            logger.warning("Homepage LLM extraction failed for %s: %s", profile.name, e)
            return HomepageCrawlResult(
                profile=profile,
                success=False,
                pages_fetched=pages_fetched,
                error=str(e),
            )
    else:
        output = _merge_homepage_extract_outputs(output, sigs_tab_output)
        output = _merge_homepage_extract_outputs(output, hit_rendered_output)

    main_anchor_text = _extract_official_anchor_text_from_html(
        html=main_html, profile=profile
    )
    main_sanitized_content = _sanitize_page_content(
        "\n\n".join([main_anchor_text, *supplementary_text_segments])[:30000]
    )
    # profile_raw_text is the professor's BIO. Exclude supplementary segments
    # sourced from publication pages — those pages feed official_top_papers, and
    # including them here leaked publication titles into the bio. A segment is
    # attributed "Source: {url}\n..."; drop it when that URL was also fetched as
    # a publication_candidate page.
    publication_fetched_urls = {
        page.url.rstrip("/") for page in fetched_pages if page.publication_candidate
    }

    def _is_publication_supplementary_segment(segment: str) -> bool:
        if not segment.startswith("Source: "):
            return False
        return segment.split("\n", 1)[0][len("Source: ") :].rstrip("/") in publication_fetched_urls

    bio_supplementary_segments = [
        segment
        for segment in supplementary_text_segments
        if not _is_publication_supplementary_segment(segment)
    ]
    profile_raw_text_content = _sanitize_page_content(
        "\n\n".join(
            [
                main_anchor_text,
                *bio_supplementary_segments,
                hit_profile_text,
                *profile_subpage_content_segments,
            ]
        )
    )
    official_research_directions = _extract_official_research_directions(
        main_sanitized_content
    )
    official_research_terms = _dedupe_preserve_order(
        [
            *official_research_directions,
            *sigs_tab_output.research_directions,
            *hit_rendered_output.research_directions,
        ]
    )
    if official_research_terms:
        merged_research_directions = (
            _merge_research_directions_preserving_official_terms(
                _clean_structured_research_directions(output.research_directions),
                official_research_terms,
            )
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
        research_topics=official_research_terms or output.research_directions,
        english_name_candidates=anchor_name_candidates,
    )

    enriched = _merge_homepage_output(profile, output)
    merged_profile_raw_text = _merge_profile_raw_text(
        profile.profile_raw_text,
        profile_raw_text_content,
    )
    if merged_profile_raw_text:
        enriched = enriched.model_copy(
            update={"profile_raw_text": merged_profile_raw_text}
        )
    if sigs_tab_output.research_directions:
        enriched = enriched.model_copy(
            update={
                "research_directions": _merge_research_directions_preserving_official_terms(
                    list(enriched.research_directions),
                    sigs_tab_output.research_directions,
                )
            }
        )
    enriched = enriched.model_copy(
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
        or selected_source_page_roles
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
        merged_field_provenance = {
            **dict(enriched.field_provenance),
            **_source_page_role_provenance(selected_source_page_roles),
        }
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
                "field_provenance": merged_field_provenance,
            }
        )

    return HomepageCrawlResult(
        profile=enriched,
        success=True,
        pages_fetched=pages_fetched,
    )


def _merge_profile_raw_text(existing: str | None, crawled_text: str) -> str | None:
    crawled = _sanitize_page_content(crawled_text)
    current = _sanitize_page_content(existing or "")
    if not crawled:
        return current[:PROFILE_RAW_TEXT_CHARS] if current else None
    if not current:
        return crawled[:PROFILE_RAW_TEXT_CHARS]
    if current in crawled:
        return crawled[:PROFILE_RAW_TEXT_CHARS]
    if crawled in current:
        return current[:PROFILE_RAW_TEXT_CHARS]
    return f"{current}\n\n{crawled}"[:PROFILE_RAW_TEXT_CHARS]
