import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from .direction_cleaner import clean_directions
from .models import ExtractedProfessorProfile
from .name_selection import is_obvious_non_person_name

_TITLE_LABELS = ("职位", "职称", "Title")
_EMAIL_LABELS = ("邮箱", "电子邮箱", "Email", "E-mail")
_OFFICE_LABELS = ("办公地点", "办公室", "Office")
_RESEARCH_LABELS = ("研究方向", "研究领域", "Research Directions", "Research Interests")
_NAME_LABELS = ("姓名", "Name")
_HOMEPAGE_LABELS = ("主页", "个人主页", "Homepage", "Home Page", "Profile")
_HOMEPAGE_TEXT_KEYWORDS = ("主页", "homepage", "home page", "profile")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_STRUCTURED_TEXT_TAGS = {"div", "p", "li", "td", "th", "dd", "dt", "section", "article"}
_IGNORED_TEXT_TAGS = {"script", "style", "noscript"}
_INLINE_LABEL_BOUNDARY_RE = re.compile(
    r"\s+(?:姓名|Name|职位|职称|Title|邮箱|电子邮箱|Email|E-mail|"
    r"办公地点|办公室|Office|研究方向|研究领域|Research Directions|"
    r"Research Interests|主页|个人主页|Homepage|Home Page|Profile)\s*[：:]",
    flags=re.IGNORECASE,
)
_NON_NAME_HEADING_KEYWORDS = (
    "概况",
    "导航",
    "组织机构",
    "现任领导",
    "新闻中心",
    "个人简介",
    "基本信息",
    "个人信息",
    "研究方向",
    "研究领域",
    "教育背景",
    "工作经历",
    "学术成果",
    "科研项目",
    "论文发表",
    "联系方式",
    "社会兼职",
    "课程教学",
    "招生信息",
    "学术科研",
    "科研动态",
    "讲座信息",
    "人才招聘",
    "资料下载",
    "汉语言文字学",
    "中国古代文学",
    "中国现当代文学",
    "文艺学",
    "外国哲学",
    "中国哲学",
    "中国史",
    "汉语国际教育系",
)
_STRUCTURED_RESEARCH_BLOCKERS = (
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


class _ProfileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self.full_text_parts: list[str] = []
        self.name_candidates: list[str] = []
        self.generic_heading_name_candidates: list[str] = []
        self.homepage_links: list[tuple[str, str]] = []
        self.page_title_parts: list[str] = []
        self.structured_text_samples: list[str] = []
        self._in_paragraph = False
        self._paragraph_parts: list[str] = []
        self._structured_text_depth = 0
        self._structured_text_parts: list[str] = []
        self._name_heading_depth = 0
        self._name_parts: list[str] = []
        self._generic_heading_depth = 0
        self._generic_heading_parts: list[str] = []
        self._title_depth = 0
        self._active_anchor_href: str | None = None
        self._active_anchor_text_parts: list[str] = []
        self._ignored_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORED_TEXT_TAGS:
            self._ignored_text_depth += 1
            return
        if self._ignored_text_depth > 0:
            return

        attributes = dict(attrs)
        class_attr = attributes.get("class") or ""
        class_tokens = set(class_attr.split())

        if tag == "p":
            self._in_paragraph = True
            self._paragraph_parts = []
        if tag in _STRUCTURED_TEXT_TAGS:
            if self._structured_text_depth == 0:
                self._structured_text_parts = []
            self._structured_text_depth += 1

        if tag in _HEADING_TAGS:
            if "t-name" in class_tokens:
                self._name_heading_depth += 1
                self._name_parts = []
            else:
                self._generic_heading_depth += 1
                self._generic_heading_parts = []
        if tag == "title":
            self._title_depth += 1

        if tag == "a":
            href = attributes.get("href")
            if href:
                self._active_anchor_href = href
                self._active_anchor_text_parts = []

    def handle_data(self, data: str) -> None:
        if not data or self._ignored_text_depth > 0:
            return
        self.full_text_parts.append(data)

        if self._in_paragraph:
            self._paragraph_parts.append(data)
        if self._structured_text_depth > 0:
            self._structured_text_parts.append(data)
        if self._name_heading_depth > 0:
            self._name_parts.append(data)
        if self._generic_heading_depth > 0:
            self._generic_heading_parts.append(data)
        if self._title_depth > 0:
            self.page_title_parts.append(data)
        if self._active_anchor_href is not None:
            self._active_anchor_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORED_TEXT_TAGS and self._ignored_text_depth > 0:
            self._ignored_text_depth -= 1
            return
        if self._ignored_text_depth > 0:
            return

        if tag == "p" and self._in_paragraph:
            paragraph_text = _normalize_text("".join(self._paragraph_parts))
            if paragraph_text:
                self.paragraphs.append(paragraph_text)
            self._in_paragraph = False
            self._paragraph_parts = []
        if tag in _STRUCTURED_TEXT_TAGS and self._structured_text_depth > 0:
            self._structured_text_depth -= 1
            if self._structured_text_depth == 0:
                structured_text = _normalize_text("".join(self._structured_text_parts))
                if structured_text:
                    self.structured_text_samples.append(structured_text)
                self._structured_text_parts = []

        if tag in _HEADING_TAGS and self._name_heading_depth > 0:
            candidate = _normalize_text("".join(self._name_parts))
            if candidate:
                self.name_candidates.append(candidate)
            self._name_heading_depth -= 1
            self._name_parts = []
        elif tag in _HEADING_TAGS and self._generic_heading_depth > 0:
            candidate = _normalize_text("".join(self._generic_heading_parts))
            if _is_generic_name_heading(candidate):
                self.generic_heading_name_candidates.append(candidate)
            self._generic_heading_depth -= 1
            self._generic_heading_parts = []
        if tag == "title" and self._title_depth > 0:
            self._title_depth -= 1

        if tag == "a" and self._active_anchor_href is not None:
            anchor_text = _normalize_text("".join(self._active_anchor_text_parts))
            lowered = anchor_text.lower()
            if anchor_text and any(keyword in lowered for keyword in _HOMEPAGE_TEXT_KEYWORDS):
                self.homepage_links.append((self._active_anchor_href, anchor_text))
            self._active_anchor_href = None
            self._active_anchor_text_parts = []


def extract_professor_profile(
    html: str,
    source_url: str,
    institution: str | None = None,
    department: str | None = None,
) -> ExtractedProfessorProfile:
    parser = _ProfileParser()
    parser.feed(html)
    parser.close()

    full_text = _normalize_text(" ".join(parser.full_text_parts))
    text_samples = [*parser.structured_text_samples, *parser.paragraphs, full_text]

    labeled_name = _extract_first_labeled_value(text_samples, _NAME_LABELS)
    title_name = _extract_name_from_page_title(
        page_title=_normalize_text("".join(parser.page_title_parts)),
        institution=institution,
        department=department,
    )
    name = _first_non_empty(
        parser.name_candidates
        + [labeled_name]
        + [title_name]
        + parser.generic_heading_name_candidates
    )
    title = _extract_first_labeled_value(text_samples, _TITLE_LABELS)
    office = _extract_first_labeled_value(text_samples, _OFFICE_LABELS)
    research_raw = _extract_first_labeled_value(text_samples, _RESEARCH_LABELS)
    research_directions = _extract_research_directions(
        text_samples=text_samples,
        research_raw=research_raw,
    )

    labeled_email = _extract_first_labeled_value(text_samples, _EMAIL_LABELS)
    fallback_email = _extract_email_from_text(full_text)
    email = _normalize_email(labeled_email or fallback_email)

    homepage_url = _extract_homepage_url(
        text_samples=text_samples,
        parser_homepage_links=parser.homepage_links,
        source_url=source_url,
    )

    return ExtractedProfessorProfile(
        name=name,
        institution=_normalize_optional_context(institution),
        department=_normalize_optional_context(department),
        title=title,
        email=email,
        homepage_url=homepage_url,
        profile_url=source_url,
        office=office,
        research_directions=tuple(research_directions),
        source_urls=(source_url,),
    )


def _extract_homepage_url(
    text_samples: list[str],
    parser_homepage_links: list[tuple[str, str]],
    source_url: str,
) -> str:
    homepage_text = _extract_first_labeled_value(text_samples, _HOMEPAGE_LABELS)
    if homepage_text:
        match = re.search(r"https?://[^\s]+", homepage_text)
        if match:
            return match.group(0).rstrip("，。,.;；）)")

    if parser_homepage_links:
        return urljoin(source_url, parser_homepage_links[0][0])

    return source_url


def _extract_first_labeled_value(text_samples: list[str], labels: tuple[str, ...]) -> str | None:
    for sample in text_samples:
        if not sample:
            continue
        for label in labels:
            value = _extract_labeled_value(sample, label)
            if value:
                return value
    return None


def _extract_labeled_value(text: str, label: str) -> str | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None

    if normalized.startswith(label):
        value = _clean_value(normalized[len(label) :])
        if value:
            return value

    escaped = re.escape(label)
    colon_match = re.search(
        rf"(?:^|[\s/|；;，,]){escaped}\s*[：:]\s*([^/|；;，,\n]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if colon_match:
        value = _clean_value(colon_match.group(1))
        if value:
            return value

    return None


def _extract_email_from_text(text: str) -> str | None:
    match = _EMAIL_PATTERN.search(_normalize_email_text(text))
    if not match:
        return None
    return match.group(0)


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    match = _EMAIL_PATTERN.search(_normalize_email_text(value))
    if not match:
        return None
    return match.group(0).lower()


def _normalize_email_text(text: str) -> str:
    normalized = text
    replacements = (
        ("_AT_", "@"),
        ("(at)", "@"),
        ("[at]", "@"),
        ("{at}", "@"),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
        normalized = normalized.replace(old.upper(), new)
    return normalized.replace(" ", "")


def _split_research_directions(value: str) -> list[str]:
    items: list[str] = []
    for part in re.split(r"[、,，;/；]\s*", value):
        cleaned = _clean_value(part)
        if not cleaned:
            continue
        if cleaned not in items:
            items.append(cleaned)
    return items


def _extract_research_directions(
    *,
    text_samples: list[str],
    research_raw: str | None,
) -> list[str]:
    candidates: list[str] = []
    if research_raw:
        candidates.append(research_raw)

    for index, sample in enumerate(text_samples):
        normalized = _normalize_text(sample)
        if not normalized:
            continue
        for label in _RESEARCH_LABELS:
            if normalized == label:
                next_value = _next_non_empty_sample(text_samples, index + 1)
                if _looks_like_research_directions(next_value):
                    candidates.append(next_value)
                continue
            match = re.match(
                rf"^{re.escape(label)}\s*(?:[：:]\s*|\s+)(.+)$",
                normalized,
                flags=re.IGNORECASE,
            )
            if match:
                candidate = _clean_value(match.group(1))
                if _looks_like_research_directions(candidate):
                    candidates.append(candidate)

    return _clean_structured_research_directions(candidates)


def _clean_structured_research_directions(values: list[str]) -> list[str]:
    protected_token = "__COURSE_THOUGHT__"
    protected = [
        value.replace("课程思政", protected_token)
        for value in values
        if value
    ]
    cleaned = clean_directions(protected)
    return [value.replace(protected_token, "课程思政") for value in cleaned]


def _next_non_empty_sample(text_samples: list[str], start_index: int) -> str | None:
    for sample in text_samples[start_index:]:
        normalized = _normalize_text(sample)
        if normalized:
            return normalized
    return None


def _looks_like_research_directions(value: str | None) -> bool:
    normalized = _normalize_text(value or "")
    if not normalized:
        return False
    if len(normalized) > 80:
        return False
    if any(blocker in normalized for blocker in _STRUCTURED_RESEARCH_BLOCKERS):
        return False
    return True


def _is_generic_name_heading(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    if len(normalized) > 20:
        return False
    if is_obvious_non_person_name(normalized):
        return False
    if any(keyword in normalized for keyword in _NON_NAME_HEADING_KEYWORDS):
        return False
    if re.search(r"[0-9@#%$^&*_+=<>{}\[\]\\|/:：]", normalized):
        return False
    if re.fullmatch(
        r"[\u4e00-\u9fff·]{2,4}(?:院士|教授|副教授|讲师|研究员|副研究员|助理教授|老师|博士)?",
        normalized,
    ):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,39}", normalized) and " " in normalized:
        return True
    return False


def _clean_value(value: str) -> str:
    normalized = _normalize_text(value)
    boundary_match = _INLINE_LABEL_BOUNDARY_RE.search(normalized)
    if boundary_match:
        normalized = normalized[: boundary_match.start()]
    return _normalize_text(normalized).strip("：:;,，；/|").strip()


def _normalize_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.replace("\ufeff", "").replace("\u3000", " "),
    ).strip()


def _normalize_optional_context(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    return normalized or None


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _extract_name_from_page_title(
    *,
    page_title: str | None,
    institution: str | None,
    department: str | None,
) -> str | None:
    title = _normalize_text(page_title or "")
    if not title:
        return None

    for separator in ("@", "-", "_", "|", "－", "—"):
        if separator in title:
            prefix = _normalize_text(title.split(separator, 1)[0])
            if _is_generic_name_heading(prefix):
                return prefix
            break

    for context_text in (institution, department):
        normalized_context = _normalize_text(context_text or "")
        if normalized_context and title.endswith(normalized_context):
            prefix = _normalize_text(title[: -len(normalized_context)])
            if _is_generic_name_heading(prefix):
                return prefix

    return title if _is_generic_name_heading(title) else None
