from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from .direction_cleaner import clean_directions
from .models import EducationEntry, WorkEntry

HIT_PROFILE_SOURCE = "hit_homepage"
HIT_PROFILE_HOSTS = frozenset({"homepage.hit.edu.cn", "faculty.hitsz.edu.cn"})
HIT_PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_WHITESPACE_RE = re.compile(r"\s+")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:19|20)\d{2})(?:[/-]\d{1,2})?\s*"
    r"(?:[-–—~～]|至|到)\s*"
    r"(?:(?P<end>(?:19|20)\d{2})(?:[/-]\d{1,2})?|今|至今|present|now)",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"工学博士|理学博士|博士研究生|博士|硕士研究生|硕士|学士|Ph\.?D\.?|M\.?S\.?|B\.?S\.?",
    re.IGNORECASE,
)
_ROLE_TOKENS = (
    "长聘教授",
    "讲席教授",
    "特聘教授",
    "副教授",
    "助理教授",
    "教授",
    "研究员",
    "副研究员",
    "讲师",
    "博士后",
    "副院长",
    "院长",
    "博导",
    "硕导",
)
_ORG_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z（）()·&.\s-]{2,}?"
    r"(?:大学（深圳）[\u4e00-\u9fffA-Za-z（）()·&.\s-]{0,30}学院|"
    r"大学[\u4e00-\u9fffA-Za-z（）()·&.\s-]{0,30}学院|"
    r"大学（深圳）|大学|学院|研究院|实验室|中心|"
    r"University|College|Institute|Laboratory|Center)",
    re.IGNORECASE,
)
_SECTION_LABELS = (
    "个人简介",
    "研究方向",
    "研究领域",
    "教育及工作经历",
    "教育经历",
    "工作经历",
    "联系方式",
    "邮箱",
    "部分项目及论文列表",
    "项目及论文",
    "论文",
    "成果",
    "专利",
    "荣誉",
)
_PAPER_OR_PROJECT_LABEL_RE = re.compile(r"论文|项目")
_BIO_RESEARCH_PATTERNS = (
    re.compile(r"(?:长期|主要|一直|多年来)?从事(?P<body>.{4,120}?)(?:等领域|领域)"),
    re.compile(
        r"(?:长期|主要|一直|多年来)?从事(?P<body>.{4,100}?)(?:研究|相关研究|研究工作)"
    ),
)
_RESEARCH_DIRECTION_DENYLIST = frozenset(
    {
        "更新日期",
        "人气",
        "主页地址",
        "复制地址",
        "二维码",
        "更换皮肤",
        "版式",
        "编辑",
        "提交",
        "校内单位",
        "学科",
        "更多",
        "手机",
        "回到顶部",
        "http",
        "https",
        "homepage.hit.edu.cn",
        "None",
        "空",
    }
)
_RESEARCH_DIRECTION_DENY_SUBSTRINGS = (
    "手机",
    "二维码",
    "复制地址",
    "主页地址",
)
# Reject reference-list / citation fragments that leak in when a verbose professor's
# publication list is mistaken for research directions (e.g. volume:page, "N. Author",
# volume(issue), page ranges, DOIs, (year)). A real research direction is a TERM:
# a CJK char or a 3+ letter run.
_CITATION_FRAGMENT_RE = re.compile(
    r"\d+\s*[:：]\s*\d+"  # 114: 103462  (volume: page)
    r"|^\s*\d+\s*\.\s"  # "10. 宋鹏" (numbered citation author)
    r"|\d+\s*\(\s*\d"  # 150(16) / 141904 (2016) (volume(issue) / id (year))
    r"|\d{3,}\s*[-–—~]\s*\d{2,}"  # 138-145 (page range)
    r"|10\.\d{4,}\s*/"  # 10.xxxx/ (DOI)
)
_RESEARCH_TERM_RE = re.compile(r"[一-鿿]|[A-Za-z]{3,}")


@dataclass(frozen=True, slots=True)
class HitProfileFact:
    professor_id: str
    fact_type: str
    value_raw: str
    evidence_span: str
    source: str
    source_url: str
    run_id: str
    value_normalized: str | None = None
    confidence: float = 0.85


@dataclass(frozen=True, slots=True)
class HitProfileExtraction:
    source_url: str
    canonical_name: str | None = None
    department: str | None = None
    profile_summary: str | None = None
    research_directions: list[str] | None = None
    education: list[EducationEntry] | None = None
    work_experience: list[WorkEntry] | None = None
    academic_positions: list[str] | None = None
    contact_email: str | None = None
    profile_text: str = ""
    facts: tuple[HitProfileFact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "research_directions", self.research_directions or [])
        object.__setattr__(self, "education", self.education or [])
        object.__setattr__(self, "work_experience", self.work_experience or [])
        object.__setattr__(self, "academic_positions", self.academic_positions or [])


def is_hit_profile_url(url: str | None) -> bool:
    parsed = urlparse(url or "")
    return (parsed.hostname or "").lower() in HIT_PROFILE_HOSTS


def canonicalize_hit_profile_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname != "faculty.hitsz.edu.cn":
        return url
    return urlunparse(
        (
            parsed.scheme or "https",
            "homepage.hit.edu.cn",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


async def render_hit_profile_html_async(
    url: str,
    *,
    timeout: float = 20.0,
    wait_after_ms: int = 4000,
) -> str:
    """Render a HIT teacher profile page with Playwright and return the DOM HTML."""
    from playwright.async_api import async_playwright

    timeout_ms = max(1_000, int(timeout * 1000))
    target_url = canonicalize_hit_profile_url(url)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=HIT_PLAYWRIGHT_USER_AGENT)
            await page.goto(target_url, wait_until="networkidle", timeout=timeout_ms)
            await page.wait_for_timeout(wait_after_ms)
            return await page.content()
        finally:
            await browser.close()


def render_hit_profile_html(
    url: str,
    *,
    timeout: float = 20.0,
    wait_after_ms: int = 4000,
) -> str:
    """Synchronous wrapper for scripts; async crawler code uses the async API."""
    return asyncio.run(
        render_hit_profile_html_async(
            url,
            timeout=timeout,
            wait_after_ms=wait_after_ms,
        )
    )


def extract_hit_profile_fields(
    html: str,
    *,
    source_url: str,
    professor_id: str,
    run_id: str,
) -> HitProfileExtraction:
    normalized_run_id = _require_run_id(run_id)
    normalized_source_url = canonicalize_hit_profile_url(source_url)
    extraction = parse_hit_rendered_profile(html, source_url=normalized_source_url)
    facts = tuple(
        _iter_hit_profile_facts(
            extraction,
            professor_id=professor_id,
            run_id=normalized_run_id,
        )
    )
    return replace(extraction, facts=facts)


def parse_hit_rendered_profile(html: str, *, source_url: str) -> HitProfileExtraction:
    soup = BeautifulSoup(html or "", "html.parser")
    _remove_non_content_nodes(soup)
    text = _body_text(soup)
    sections = _extract_hit_sections(soup, text)
    header_lines = _header_lines(text)

    # Use only the (guarded) structured 研究方向 section; do NOT fall back to
    # _inline_labeled_text, which can mis-attribute a verbose publication/reference
    # list to research directions (real directions come from the bio pattern below).
    research_text = sections.get("research") or ""
    summary = sections.get("summary")
    education_work_text = sections.get("education_work") or ""
    contact_text = "\n".join(part for part in (sections.get("contact"), text) if part)
    research_directions = _dedupe(
        [
            *_extract_research_directions(research_text),
            *_extract_bio_research_directions(summary),
        ]
    )

    return HitProfileExtraction(
        source_url=canonicalize_hit_profile_url(source_url),
        canonical_name=_extract_canonical_name(soup, text),
        department=_extract_department(header_lines),
        profile_summary=_strip_section_label(summary, "个人简介"),
        research_directions=research_directions,
        education=_extract_education_entries(education_work_text),
        work_experience=_extract_work_entries(education_work_text),
        academic_positions=_extract_academic_positions(header_lines),
        contact_email=_extract_email(contact_text),
        profile_text=_profile_text_without_papers(sections, header_lines),
    )


def _require_run_id(run_id: str | None) -> str:
    normalized = str(run_id or "").strip()
    if not normalized:
        raise ValueError("run_id is required for HIT profile facts")
    return normalized


def _remove_non_content_nodes(soup: BeautifulSoup) -> None:
    for node in soup(["script", "style", "noscript"]):
        node.decompose()


def _body_text(soup: BeautifulSoup) -> str:
    node = soup.body or soup
    lines = [_clean_text(line) for line in node.get_text("\n", strip=True).splitlines()]
    return "\n".join(line for line in lines if line)


def _clean_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip(" \t\r\n:：;；")


def _clean_multiline_text(value: Any) -> str:
    lines = [_clean_text(line) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_canonical_name(soup: BeautifulSoup, text: str) -> str | None:
    # HIT renders the teacher name in <h3 class="tit chineseName">…</h3>; the page
    # <title> is "Name - 哈尔滨工业大学教师个人主页". Prefer those explicit markers
    # before any <h1>/line-scan fallback (the nav label "首页" otherwise wins).
    chinese_name = soup.select_one("h3.chineseName") or soup.select_one(".chineseName")
    if chinese_name is not None:
        value = _clean_text(chinese_name.get_text(" ", strip=True))
        if value:
            return value
    title = soup.find("title")
    if title is not None:
        title_text = _clean_text(title.get_text(" ", strip=True))
        if " - " in title_text:
            value = _clean_text(title_text.split(" - ", 1)[0])
            if value:
                return value
    heading = soup.find("h1")
    if heading is not None:
        value = _clean_text(heading.get_text(" ", strip=True))
        if value:
            return value
    for line in text.splitlines():
        value = _clean_text(line)
        if 2 <= len(value) <= 12 and not any(
            label in value for label in _SECTION_LABELS
        ):
            return value
    return None


def _extract_hit_sections(soup: BeautifulSoup, text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    skip_text_fallback_keys: set[str] = set()
    has_structured_research, structured_research = _extract_structured_research_text(
        soup
    )
    if has_structured_research:
        skip_text_fallback_keys.add("research")
        if structured_research:
            sections.setdefault("research", structured_research)

    labels = [
        _clean_text(node.get_text(" ", strip=True))
        for node in soup.select(".teacher_Tab, .tab-menu span, .ul-tab-person a.con")
    ]
    panes = soup.select(".part_box, .TAB.boxj")
    for label, pane in zip(labels, panes, strict=False):
        key = _section_key(label)
        if key is None:
            continue
        pane_text = _clean_multiline_text(pane.get_text("\n", strip=True))
        pane_text = _strip_section_label(pane_text, label)
        if pane_text:
            sections.setdefault(key, pane_text)

    for key, value in _extract_sections_from_text(text).items():
        if key in skip_text_fallback_keys:
            continue
        sections.setdefault(key, value)
    return sections


def _extract_structured_research_text(soup: BeautifulSoup) -> tuple[bool, str | None]:
    nodes = soup.select(".user-label, .change-list-label")
    if not nodes:
        return False, None
    values: list[str] = []
    for node in nodes:
        text = _clean_multiline_text(node.get_text("\n", strip=True))
        title = _clean_text(node.get("title", ""))
        if text:
            values.append(text)
        if title:
            values.append(title)
    return True, _clean_multiline_text("\n".join(values))


def _section_key(label: str | None) -> str | None:
    normalized = _clean_text(label)
    if not normalized:
        return None
    if _PAPER_OR_PROJECT_LABEL_RE.search(normalized):
        return None
    if "个人简介" in normalized:
        return "summary"
    if "研究方向" in normalized or "研究领域" in normalized:
        return "research"
    if "教育" in normalized or "工作经历" in normalized:
        return "education_work"
    if "邮箱" in normalized or "联系方式" in normalized:
        return "contact"
    return None


def _extract_sections_from_text(text: str) -> dict[str, str]:
    lines = [_clean_text(line) for line in text.splitlines()]
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_key is None:
            return
        content = "\n".join(line for line in current_lines if line)
        content = _strip_section_label(content, current_key)
        if content:
            sections.setdefault(current_key, content)

    for line in lines:
        key = _section_key(line)
        if key is not None and line in _SECTION_LABELS:
            flush()
            current_key = key
            current_lines = []
            continue
        if key is not None and _starts_with_section_label(line):
            flush()
            current_key = key
            current_lines = [_remove_leading_known_label(line)]
            continue
        if line and current_key is not None:
            current_lines.append(line)
    flush()
    return sections


def _starts_with_section_label(line: str) -> bool:
    return any(line.startswith(label) for label in _SECTION_LABELS)


def _remove_leading_known_label(line: str) -> str:
    for label in _SECTION_LABELS:
        if line.startswith(label):
            return line[len(label) :].strip(" :：-")
    return line


def _strip_section_label(text: str | None, label: str) -> str | None:
    cleaned = _clean_multiline_text(text)
    if not cleaned:
        return None
    aliases = [label, *_SECTION_LABELS]
    for alias in aliases:
        alias_clean = _clean_text(alias)
        lines = cleaned.splitlines()
        if lines and lines[0] == alias_clean:
            cleaned = "\n".join(lines[1:]).strip()
            break
        if cleaned == alias_clean:
            return None
        if cleaned.startswith(alias_clean):
            cleaned = cleaned[len(alias_clean) :].strip(" :：-")
            break
    return cleaned or None


def _inline_labeled_text(text: str, label: str) -> str | None:
    pattern = re.compile(rf"{re.escape(label)}\s*[：:]\s*(?P<body>[^\n]+)")
    match = pattern.search(text)
    return _clean_text(match.group("body")) if match else None


def _header_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if any(
            label == line or line.startswith(f"{label}：") for label in _SECTION_LABELS
        ):
            break
        if _clean_text(line):
            lines.append(_clean_text(line))
    return lines


def _extract_department(lines: list[str]) -> str | None:
    for line in lines:
        if (
            any(marker in line for marker in ("学部", "学院", "研究院"))
            and "@" not in line
        ):
            return line
    return None


def _extract_academic_positions(lines: list[str]) -> list[str]:
    positions: list[str] = []
    for line in lines:
        if "@" in line or len(line) > 80:
            continue
        if any(token in line for token in _ROLE_TOKENS):
            positions.append(line)
    return _dedupe(positions)


def _extract_research_directions(text: str | None) -> list[str]:
    if not text:
        return []
    raw_items: list[str] = []
    for line in str(text).splitlines():
        cleaned = _remove_leading_known_label(line)
        raw_items.extend(re.split(r"[,，/、；;]", cleaned))
    return _clean_research_directions(raw_items)


def _extract_bio_research_directions(text: str | None) -> list[str]:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return []
    raw_items: list[str] = []
    matched_spans: list[tuple[int, int]] = []
    for pattern in _BIO_RESEARCH_PATTERNS:
        for match in pattern.finditer(compact):
            if any(
                match.start() < end and start < match.end()
                for start, end in matched_spans
            ):
                continue
            matched_spans.append(match.span())
            raw_items.extend(_split_research_topic_phrase(match.group("body")))
    return _clean_research_directions(raw_items)


def _split_research_topic_phrase(value: str | None) -> list[str]:
    cleaned = re.sub(r"(?:等)?(?:领域|方向|方面)$", "", str(value or ""))
    cleaned = re.sub(r"(?:的)?(?:创新)?(?:相关)?研究(?:工作)?$", "", cleaned)
    return re.split(r"[,，/、；;和及]", cleaned)


def _clean_research_directions(raw_items: list[str]) -> list[str]:
    return [
        direction
        for direction in clean_directions(raw_items)
        if not _is_denied_research_direction(direction)
    ]


def _is_denied_research_direction(value: str) -> bool:
    normalized = _clean_text(value)
    if not normalized or len(normalized) < 2:
        return True
    if normalized in _RESEARCH_DIRECTION_DENYLIST:
        return True
    if any(token in normalized for token in _RESEARCH_DIRECTION_DENY_SUBSTRINGS):
        return True
    if _CITATION_FRAGMENT_RE.search(normalized):
        return True
    if not _RESEARCH_TERM_RE.search(normalized):
        # Digits/punctuation only (no CJK char and no 3+ letter run) \u2014 not a real term.
        return True
    return False


def _extract_education_entries(text: str) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    for line in _fact_lines(text):
        if not _DEGREE_RE.search(line) or "博士后" in line:
            continue
        school = _extract_institution(line)
        if not school:
            continue
        degree_match = _DEGREE_RE.search(line)
        degree = _clean_text(degree_match.group(0)) if degree_match else None
        entries.append(
            EducationEntry(
                school=school,
                degree=degree,
                field=_extract_field(line, school, degree),
                start_year=_start_year(line),
                end_year=_end_year(line),
            )
        )
    return _dedupe_model_entries(entries)


def _extract_work_entries(text: str) -> list[WorkEntry]:
    entries: list[WorkEntry] = []
    for line in _fact_lines(text):
        if _DEGREE_RE.search(line) and "博士后" not in line:
            continue
        role = _extract_role(line)
        organization = _extract_institution(line)
        if not organization or not role:
            continue
        entries.append(
            WorkEntry(
                organization=organization,
                role=role,
                start_year=_start_year(line),
                end_year=_end_year(line),
            )
        )
    return _dedupe_model_entries(entries)


def _fact_lines(text: str) -> list[str]:
    candidates: list[str] = []
    for line in str(text or "").splitlines():
        cleaned = _remove_leading_known_label(line)
        candidates.extend(re.split(r"[；;]\s*", cleaned))
    return [_clean_text(line) for line in candidates if _clean_text(line)]


def _extract_institution(line: str) -> str | None:
    candidates = [
        _clean_org_candidate(match.group(0)) for match in _ORG_RE.finditer(line)
    ]
    candidates = [
        candidate for candidate in candidates if not _looks_like_date(candidate)
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _clean_org_candidate(value: str) -> str:
    candidate = _clean_text(value)
    candidate = re.sub(
        r"^(?:\d{4}(?:[/.-]\d{1,2})?\s*)?"
        r"(?:[-–—~～到至]\s*)?"
        r"(?:今|至今|present|now)?\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    return _clean_text(candidate)


def _extract_role(line: str) -> str | None:
    for token in _ROLE_TOKENS:
        if token in line:
            return token
    return None


def _extract_field(line: str, school: str, degree: str | None) -> str | None:
    try:
        start = line.index(school) + len(school)
    except ValueError:
        return None
    end = line.find(degree, start) if degree else -1
    if end < 0:
        return None
    field = _clean_text(line[start:end])
    field = re.sub(r"^[,，、\s]+", "", field)
    return field or None


def _start_year(line: str) -> int | None:
    match = _DATE_RANGE_RE.search(line)
    if match:
        return int(match.group("start"))
    match = _YEAR_RE.search(line)
    return int(match.group(0)) if match else None


def _end_year(line: str) -> int | None:
    match = _DATE_RANGE_RE.search(line)
    if match and match.group("end"):
        return int(match.group("end"))
    return None


def _looks_like_date(value: str) -> bool:
    return bool(re.fullmatch(r"[\d/\-–—~～ 至今presentnow]+", value, re.IGNORECASE))


def _extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text or "")
    return match.group(0) if match else None


def _profile_text_without_papers(
    sections: dict[str, str],
    header_lines: list[str],
) -> str:
    chunks = [*header_lines]
    for key in ("summary", "research", "education_work", "contact"):
        value = sections.get(key)
        if value:
            chunks.append(value)
    return "\n".join(_dedupe([_clean_text(chunk) for chunk in chunks if chunk]))


def _iter_hit_profile_facts(
    extraction: HitProfileExtraction,
    *,
    professor_id: str,
    run_id: str,
) -> list[HitProfileFact]:
    facts: list[HitProfileFact] = []
    for direction in extraction.research_directions or []:
        facts.append(
            _fact(
                professor_id=professor_id,
                fact_type="research_topic",
                value_raw=direction,
                evidence_span=direction,
                source_url=extraction.source_url,
                run_id=run_id,
            )
        )
    for entry in extraction.education or []:
        value = _format_education_entry(entry)
        if value:
            facts.append(
                _fact(
                    professor_id=professor_id,
                    fact_type="education",
                    value_raw=value,
                    evidence_span=value,
                    source_url=extraction.source_url,
                    run_id=run_id,
                )
            )
    for entry in extraction.work_experience or []:
        value = _format_work_entry(entry)
        if value:
            facts.append(
                _fact(
                    professor_id=professor_id,
                    fact_type="work_experience",
                    value_raw=value,
                    evidence_span=value,
                    source_url=extraction.source_url,
                    run_id=run_id,
                )
            )
    for position in extraction.academic_positions or []:
        facts.append(
            _fact(
                professor_id=professor_id,
                fact_type="academic_position",
                value_raw=position,
                value_normalized=position,
                evidence_span=position,
                source_url=extraction.source_url,
                run_id=run_id,
            )
        )
    if extraction.contact_email:
        facts.append(
            _fact(
                professor_id=professor_id,
                fact_type="contact",
                value_raw=extraction.contact_email,
                evidence_span=extraction.contact_email,
                source_url=extraction.source_url,
                run_id=run_id,
            )
        )
    return facts


def _fact(
    *,
    professor_id: str,
    fact_type: str,
    value_raw: str,
    evidence_span: str,
    source_url: str,
    run_id: str,
    value_normalized: str | None = None,
) -> HitProfileFact:
    return HitProfileFact(
        professor_id=professor_id,
        fact_type=fact_type,
        value_raw=_clean_text(value_raw),
        value_normalized=_clean_text(value_normalized) if value_normalized else None,
        evidence_span=_clean_text(evidence_span),
        source=HIT_PROFILE_SOURCE,
        source_url=source_url,
        run_id=run_id,
    )


def _format_education_entry(entry: EducationEntry) -> str:
    parts = [
        _year_range(entry.start_year, entry.end_year),
        entry.school,
        entry.field,
        entry.degree,
    ]
    return _clean_text(" ".join(part for part in parts if part))


def _format_work_entry(entry: WorkEntry) -> str:
    parts = [
        _year_range(entry.start_year, entry.end_year),
        entry.organization,
        entry.role,
    ]
    return _clean_text(" ".join(part for part in parts if part))


def _year_range(start_year: int | None, end_year: int | None) -> str | None:
    if start_year and end_year:
        return f"{start_year}-{end_year}"
    if start_year:
        return f"{start_year}-至今"
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_model_entries[T](items: list[T]) -> list[T]:
    seen: set[str] = set()
    result: list[T] = []
    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
