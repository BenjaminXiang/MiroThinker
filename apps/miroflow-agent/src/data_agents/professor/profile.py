import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .direction_cleaner import clean_directions
from .models import ExtractedProfessorProfile
from .name_selection import is_obvious_non_person_name

_TITLE_LABELS = ("职称职务", "职位", "职称", "岗位", "Position", "Title")
_EMAIL_LABELS = ("邮箱", "电子邮箱", "Email", "E-mail")
_OFFICE_LABELS = ("办公地点", "办公室", "Office")
_RESEARCH_LABELS = ("研究方向", "研究领域", "Research Directions", "Research Interests")
_NAME_LABELS = ("姓名", "Name")
_HOMEPAGE_LABELS = (
    "主页",
    "个人主页",
    "个人网站",
    "Homepage",
    "Home Page",
    "Profile",
    "ResearchGate",
)
_HOMEPAGE_TEXT_KEYWORDS = (
    "主页",
    "个人网站",
    "homepage",
    "home page",
    "profile",
    "researchgate",
)
_YJSJY_HOMEPAGE_KEYWORDS = ("主页", "个人主页", "个人网站", "homepage")
_YJSJY_SECONDARY_ACADEMIC_CONTEXT_KEYWORDS = (
    "google scholar",
    "scholar",
    "dblp",
    "doi",
    "主页",
    "个人主页",
    "个人网站",
    "教师主页",
    "学院主页",
    "课题组",
    "实验室",
    "团队",
    "更多",
    "more",
    "more results",
    "homepage",
    "home page",
    "personal website",
    "personal site",
)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BARE_SECONDARY_ACADEMIC_URL_RE = re.compile(
    r"(?:(?:https?://)|(?:www\.)|(?:doi\.org/)|(?:dx\.doi\.org/))[^\s<>'\"，。；;、]+",
    flags=re.IGNORECASE,
)
_HTTP_URL_TEXT_RE = re.compile(
    r"https?://(?:(?!\d+[.．][\u3400-\u9fff])"
    r"[^\s|；;，,<>\"'（）()【】\[\]{}\u3400-\u9fff])+",
    flags=re.IGNORECASE,
)
_REPEATED_HTTP_SCHEME_RE = re.compile(
    r"^https?://(?:www\.)?https?://",
    flags=re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
)
_ACADEMIC_TITLE_PHRASE = (
    r"(?:校长学勤讲座教授|校长永平讲座教授|校长讲座教授|特聘杰出教授|"
    r"讲席教授|特聘副教授|特聘助理教授|特聘教授|杰出教授|客座副教授|"
    r"客座助理教授|客座教授|教研助理教授|教研副教授|教研教授|"
    r"教学助理教授|教学副教授|教学教授|教学正教授|助理教授|"
    r"副教授|教授|讲师|研究员|"
    r"副研究员|院士|博士生导师|博士研究生导师|博导)"
    r"(?:[、/，, ]*(?:博士生导师|博士研究生导师|博导|课题组长))*"
)
_ACADEMIC_TITLE_PATTERN = re.compile(rf"^{_ACADEMIC_TITLE_PHRASE}$")
_ACADEMIC_TITLE_SEARCH_PATTERN = re.compile(_ACADEMIC_TITLE_PHRASE)
_ENGLISH_ACADEMIC_TITLE_HINT_RE = re.compile(
    r"\b(?:Professor|Lecturer|Researcher|Research Fellow|Chair|Scholar|Dean|"
    r"Director|Instructor|Faculty|Scientist)\b",
    flags=re.IGNORECASE,
)
_DEPARTMENT_SUFFIX_PATTERN = r"(?:研究院|实验室|学院|学部|中心|系)"
_SUSTECH_DEPARTMENT_CONTEXT_PATTERN = re.compile(
    r"南方科技大学(?P<context>[^，。；;\n]{2,80})"
)
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_STRUCTURED_TEXT_TAGS = {"div", "p", "li", "td", "th", "dd", "dt", "section", "article"}
_IGNORED_TEXT_TAGS = {"script", "style", "noscript"}
_INLINE_LABEL_BOUNDARY_RE = re.compile(
    r"\s+(?:姓名|Name|职位|职称|Position|Title|邮箱|电子邮箱|Email|E-mail|"
    r"办公地点|办公室|Office|研究方向|研究领域|Research Directions|"
    r"Research Interests|主页|个人主页|Homepage|Home Page|Profile)\s*[：:]",
    flags=re.IGNORECASE,
)
_INLINE_CONTACT_BOUNDARY_RE = re.compile(
    r"\s+(?:https?:\S*|(?:电话|办公电话|办公室电话|联系电话|个人课题组|课题组|"
    r"主页|个人主页|Homepage|Home Page|Profile|ResearchGate)(?:\s*[：:]|$))",
    flags=re.IGNORECASE,
)
_NON_NAME_HEADING_KEYWORDS = (
    "概况",
    "导航",
    "组织机构",
    "现任领导",
    "新闻中心",
    "个人简历",
    "个人简介",
    "基本信息",
    "个人信息",
    "研究方向",
    "研究领域",
    "教育经历",
    "教育背景",
    "工作经历",
    "研究成果",
    "学术成果",
    "科研项目",
    "论文发表",
    "代表性文章",
    "代表性论文",
    "代表性著作",
    "奖励荣誉",
    "荣誉奖项",
    "主要荣誉",
    "学术兼职",
    "联系方式",
    "发明专利",
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
    "招生类别",
    "专业名称",
    "研究领域/方向",
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
_TITLE_CONTAMINATION_MARKERS = (
    "URL Source",
    "Published Time",
    "Markdown Content",
    "搜索",
    "面包屑",
    "教育背景",
    "教育经历",
    "学术领域",
    "研究领域",
    "研究方向",
    "个人简介",
    "学术著作",
    "学术成果",
    "科研项目",
    "联系方式",
    "人才招聘",
    "Patent",
    "patent",
    "Inventor",
    "inventor",
    "Applicant",
    "applicant",
)
_SZTU_SUAT_ADMIN_SUPPORT_ROLE_HINTS = (
    "校企合作专员",
    "教务员",
    "教学秘书",
    "行政人员",
    "行政",
    "教辅",
    "办公室",
    "秘书",
    "辅导员",
    "党务",
    "人事",
    "综合",
    "书记",
    "副书记",
    "院长",
    "副院长",
)
_MARKDOWN_NAV_HEADING_MARKERS = (
    "搜索",
    "返回主站",
    "学院概况",
    "师资力量",
    "教职人员",
    "荣休教授",
    "兼职人员",
    "学生发展",
    "新闻与公示",
)
_LEADING_PROFILE_TITLE_NOISE = frozenset(
    {
        "面包屑",
        "友情链接",
        "未开通",
        "导航",
        *_MARKDOWN_NAV_HEADING_MARKERS,
    }
)
_PROFILE_FRAGMENT_CONTAINER_RE = re.compile(
    r"(?:prof|profile|teacher|faculty|member|card|item|team|person)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SigsTabSection:
    tab_label: str
    section_title: str
    text: str
    lines: tuple[str, ...]


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
    extraction_html = _scope_html_to_fragment_profile(html, source_url) or html
    uestc_yjsjy_profile = _extract_uestc_yjsjy_detail_profile(
        html=extraction_html,
        source_url=source_url,
        institution=institution,
        department=department,
    )
    if uestc_yjsjy_profile is not None:
        return uestc_yjsjy_profile

    parser = _ProfileParser()
    parser.feed(extraction_html)
    parser.close()

    full_text = _normalize_text(" ".join(parser.full_text_parts))
    sustech_fields = _extract_sustech_message_left_fields(extraction_html, source_url)
    sigs_fields = _extract_sigs_teacher_fields(extraction_html, source_url)
    sigs_tab_sections = _extract_sigs_tab_sections(extraction_html, source_url)
    sztu_suat_fields = _extract_sztu_suat_detail_fields(extraction_html, source_url)
    szu_bigdata_fields = _extract_szu_bigdata_detail_fields(extraction_html, source_url)
    szu_cpoe_fields = _extract_szu_cpoe_detail_fields(extraction_html, source_url)
    profile_raw_text = (
        szu_cpoe_fields.get("profile_raw_text")
        or szu_bigdata_fields.get("profile_raw_text")
        or sztu_suat_fields.get("profile_raw_text")
        or _extract_cuhk_myweb_profile_raw_text(extraction_html, source_url)
        or _extract_profile_raw_text(extraction_html, source_url)
    )
    if _is_sztu_suat_fragment_profile_url(source_url) and profile_raw_text:
        text_samples = [profile_raw_text]
    else:
        text_samples = [
            sample
            for sample in [
                *parser.structured_text_samples,
                *parser.paragraphs,
                profile_raw_text,
                full_text,
            ]
            if sample
        ]

    labeled_name = _extract_first_labeled_value(text_samples, _NAME_LABELS)
    title_name = _extract_name_from_page_title(
        page_title=_normalize_text("".join(parser.page_title_parts)),
        institution=institution,
        department=department,
    )
    body_name = _extract_name_from_profile_text(profile_raw_text or full_text)
    sysu_detail_name = _extract_sysu_detail_latin_name(
        html=extraction_html,
        source_url=source_url,
        profile_text=profile_raw_text or full_text,
    )
    trusted_structured_name = szu_bigdata_fields.get("name")
    if _is_sztu_suat_profile_url(source_url):
        name_candidates = [
            title_name,
            sztu_suat_fields.get("name"),
            body_name,
            labeled_name,
            sysu_detail_name,
            *parser.name_candidates,
            *parser.generic_heading_name_candidates,
        ]
    else:
        name_candidates = (
            parser.name_candidates
            + [
                sztu_suat_fields.get("name"),
                sigs_fields.get("name"),
                sustech_fields.get("name"),
                labeled_name,
            ]
            + [title_name]
            + [sysu_detail_name]
            + parser.generic_heading_name_candidates
            + [body_name]
        )
    name = (
        szu_cpoe_fields.get("name")
        or trusted_structured_name
        or _first_person_name(name_candidates)
    )
    title = _first_non_empty(
        [
            _normalize_title_candidate(szu_cpoe_fields.get("title")),
            _normalize_title_candidate(szu_bigdata_fields.get("title")),
            _normalize_title_candidate(sztu_suat_fields.get("title")),
            _extract_first_title_value(text_samples),
            _normalize_title_candidate(sigs_fields.get("title")),
            _normalize_title_candidate(sustech_fields.get("title")),
            _extract_sysu_title_from_profile_text(
                profile_raw_text or full_text,
                source_url,
            ),
            _extract_title_near_profile_name(profile_raw_text or full_text, name),
            _extract_markdown_heading_title(text_samples),
        ]
    )
    office = _extract_first_labeled_value(text_samples, _OFFICE_LABELS)
    research_raw = (
        szu_cpoe_fields.get("research_directions")
        or szu_bigdata_fields.get("research_directions")
        or sztu_suat_fields.get("research_directions")
        or _extract_first_labeled_value(text_samples, _RESEARCH_LABELS)
    )
    research_directions = _extract_research_directions(
        text_samples=text_samples,
        research_raw=research_raw,
    )
    sztu_suat_research_directions = (
        _extract_sztu_suat_research_directions_from_profile_text(
            profile_raw_text,
            source_url,
        )
    )
    if sztu_suat_research_directions and (
        not research_directions
        or len(sztu_suat_research_directions) > len(research_directions)
        or _sztu_suat_research_directions_need_cleanup(research_directions)
    ):
        research_directions = sztu_suat_research_directions
    sigs_research_directions = _extract_sigs_research_topics_from_sections(
        sigs_tab_sections
    )
    if sigs_research_directions:
        research_directions = sigs_research_directions
    if not research_directions and _should_scope_sysu_col_md_9_profile(source_url):
        research_directions = _extract_sysu_narrative_research_directions(
            profile_raw_text or full_text
        )
    sysu_research_directions = _extract_sysu_research_directions_from_samples(
        text_samples=text_samples,
        source_url=source_url,
    )
    if sysu_research_directions and (
        not research_directions
        or len(sysu_research_directions) > len(research_directions)
        or _research_directions_need_sysu_cleanup(research_directions)
    ):
        research_directions = sysu_research_directions

    email_text_samples = _email_text_samples(
        text_samples=text_samples,
        profile_raw_text=profile_raw_text,
        source_url=source_url,
    )
    labeled_email = _extract_first_labeled_value(email_text_samples, _EMAIL_LABELS)
    fallback_email_source = (
        profile_raw_text
        if _should_scope_contact_text_to_profile_raw(source_url, profile_raw_text)
        else full_text
    )
    fallback_email = _extract_email_from_text(fallback_email_source)
    email = _normalize_email(
        szu_cpoe_fields.get("email")
        or sztu_suat_fields.get("email")
        or labeled_email
        or sustech_fields.get("email")
        or fallback_email
    )

    homepage_url = _extract_homepage_url(
        text_samples=text_samples,
        parser_homepage_links=parser.homepage_links,
        source_url=source_url,
    )
    inferred_department = _first_non_empty(
        [
            _normalize_optional_context(department),
            _extract_department_from_profile_text(profile_raw_text or full_text, institution),
        ]
    )

    return ExtractedProfessorProfile(
        name=name,
        institution=_normalize_optional_context(institution),
        department=inferred_department,
        title=title,
        email=email,
        homepage_url=homepage_url,
        profile_url=source_url,
        office=office,
        research_directions=tuple(research_directions),
        source_urls=(source_url,),
        profile_raw_text=profile_raw_text,
    )


def _scope_html_to_fragment_profile(html: str, source_url: str) -> str | None:
    node = _find_fragment_profile_scope_node(BeautifulSoup(html, "html.parser"), source_url)
    if node is None:
        return None
    return str(node)


def _find_fragment_profile_scope_node(
    soup: BeautifulSoup,
    source_url: str,
) -> Tag | None:
    fragment = _normalize_text(unquote(urlparse(source_url).fragment or ""))
    if not fragment:
        return None

    target = soup.find(id=fragment)
    if target is None:
        target = soup.find(attrs={"name": fragment})
    if not isinstance(target, Tag):
        return None

    if _fragment_node_looks_like_profile_container(target):
        return target

    for ancestor in target.parents:
        if not isinstance(ancestor, Tag) or ancestor.name in {"body", "html", "[document]"}:
            continue
        if _fragment_node_looks_like_profile_container(ancestor):
            return ancestor

    for ancestor in target.parents:
        if not isinstance(ancestor, Tag) or ancestor.name in {"body", "html", "[document]"}:
            continue
        if ancestor.name in {"section", "article", "li", "tr", "td", "div"}:
            text = _normalize_text(ancestor.get_text(" ", strip=True))
            if len(text) >= 20:
                return ancestor
    return target


def _fragment_node_looks_like_profile_container(node: Tag) -> bool:
    text = _normalize_text(node.get_text(" ", strip=True))
    if len(text) < 20:
        return False
    class_text = " ".join(node.get("class", ()))
    identifier_text = " ".join(
        value for value in (node.get("id"), node.get("name"), class_text) if value
    )
    if _PROFILE_FRAGMENT_CONTAINER_RE.search(identifier_text):
        return True
    return node.name in {"section", "article", "li", "tr"}


def _extract_sustech_message_left_fields(html: str, source_url: str) -> dict[str, str]:
    if "sustech.edu.cn" not in source_url:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    message_left = soup.select_one(".message-left")
    if message_left is None:
        return {}

    font_texts = [
        text
        for node in message_left.select(".font")
        if (text := _normalize_text(node.get_text(" ", strip=True)))
    ]
    fields: dict[str, str] = {}
    for text in font_texts:
        email = _normalize_email(text)
        if email:
            fields.setdefault("email", email)
            continue
        if _looks_like_academic_title(text):
            fields.setdefault("title", text)
            continue
        if not fields.get("name") and _looks_like_person_name(text):
            fields["name"] = text

    if "email" not in fields:
        email = _extract_email_from_text(message_left.get_text(" ", strip=True))
        if email:
            fields["email"] = email
    return fields


def _extract_sigs_teacher_fields(html: str, source_url: str) -> dict[str, str]:
    if "sigs.tsinghua.edu.cn" not in source_url:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    profile_node = soup.select_one(".teacher_right, .col_news_con")
    if profile_node is None:
        return {}
    profile_text = _normalize_text(profile_node.get_text(" ", strip=True))
    if not profile_text:
        return {}

    fields: dict[str, str] = {}
    title_match = re.match(
        r"^(?P<name>.{2,80}?)\s+"
        r"(?P<title>(?:院士|讲席教授|教授|副教授|助理教授|讲师|研究员|副研究员)"
        r"(?:\s*[，,、]\s*(?:博士生导师|博导))*)"
        r"(?:\s|电话|邮箱|地址|$)",
        profile_text,
    )
    if title_match:
        name = _normalize_sigs_teacher_name(title_match.group("name"))
        if _looks_like_person_name(name):
            fields["name"] = name
        title = _normalize_text(title_match.group("title")).replace(" ,", ",")
        fields["title"] = re.sub(r"\s*([，,、])\s*", r"\1", title)
    return fields


def _extract_szu_bigdata_detail_fields(html: str, source_url: str) -> dict[str, str]:
    if not _is_szu_bigdata_profile_url(source_url):
        return {}

    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    name = _normalize_text(_text_from_selector(soup, ".teamm1") or "")
    if name and _looks_like_szu_bigdata_person_name(name):
        fields["name"] = name
    title = _szu_bigdata_title_from_url(source_url)
    if title:
        fields["title"] = title
    raw_text = _extract_szu_bigdata_profile_raw_text(soup, name)
    if raw_text:
        fields["profile_raw_text"] = raw_text
    research_directions = _extract_szu_bigdata_research_directions(soup)
    if research_directions:
        fields["research_directions"] = research_directions
    return fields


def _extract_szu_cpoe_detail_fields(html: str, source_url: str) -> dict[str, str]:
    if not _is_szu_cpoe_detail_url(source_url):
        return {}

    soup = BeautifulSoup(html, "html.parser")
    detail = soup.select_one(".teac-det")
    if detail is None:
        return {}

    fields: dict[str, str] = {}
    name = _normalize_text(_text_from_selector(detail, ".name") or "")
    if name and _looks_like_person_name(name):
        fields["name"] = name

    title = _normalize_text(
        _text_from_selector(detail, ".position")
        or _text_from_selector(detail, ".zw")
        or ""
    )
    if title:
        fields["title"] = title

    email = _extract_szu_cpoe_email(detail)
    if email:
        fields["email"] = email

    raw_node = detail.select_one(".txtBox") or detail.select_one(".v_news_content")
    if raw_node is not None:
        raw_text = _extract_clean_profile_node_text(raw_node)
        if raw_text and len(raw_text) >= 20:
            fields["profile_raw_text"] = raw_text

    research = _extract_szu_cpoe_research_directions(detail)
    if research:
        fields["research_directions"] = research
    return fields


def _is_szu_cpoe_detail_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    return hostname == "cpoe.szu.edu.cn" and parsed.path.rstrip("/").lower().endswith(
        "/szxq.jsp"
    )


def _extract_szu_cpoe_email(detail: Tag) -> str | None:
    for node in detail.select("li, p, span"):
        text = _normalize_text(node.get_text(" ", strip=True))
        if "@" not in text:
            continue
        email = _normalize_email(text)
        if email:
            return email
    return _extract_email_from_text(detail.get_text(" ", strip=True))


def _extract_szu_cpoe_research_directions(detail: Tag) -> str | None:
    for heading in detail.find_all(("h2", "h3", "strong")):
        label = _normalize_text(heading.get_text(" ", strip=True))
        if "研究方向" not in label and "研究领域" not in label:
            continue
        container = heading.find_parent(class_="item") or heading.parent
        if not isinstance(container, Tag):
            continue
        info = container.select_one(".info") or container
        text = _normalize_text(info.get_text(" ", strip=True))
        text = re.sub(r"^研究方向\s*[:：]?\s*", "", text)
        if text and len(text) >= 4:
            return re.sub(r"\s*[,，]\s*", "、", text)
    return None


def _is_szu_bigdata_profile_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    return (parsed.hostname or "").lower() == "bigdata.szu.edu.cn" and "/info/" in (
        parsed.path or ""
    )


def _szu_bigdata_title_from_url(source_url: str) -> str | None:
    match = re.search(r"/info/(?P<category>\d+)/", urlparse(source_url).path)
    if not match:
        return None
    return {
        "1008": "教授",
        "1009": "副教授",
        "1010": "助理教授",
        "1011": "讲师",
        "1012": "专职研究员",
        "1013": "博士后",
    }.get(match.group("category"))


def _extract_szu_bigdata_profile_raw_text(
    soup: BeautifulSoup,
    name: str | None,
) -> str | None:
    body = soup.select_one(".abm2 .teamm2, .teamm2")
    if body is None:
        return None
    text = _extract_clean_profile_node_text(body)
    if not text or len(text) < 20:
        return None
    if name and not text.startswith(name):
        text = f"{name} {text}"
    return text


def _extract_szu_bigdata_research_directions(soup: BeautifulSoup) -> str | None:
    for heading in soup.select(".teamm2 h3"):
        label = _normalize_text(heading.get_text(" ", strip=True))
        if "研究方向" not in label and "Research" not in label:
            continue
        for sibling in heading.find_next_siblings():
            text = _clean_szu_bigdata_research_text(sibling.get_text("\n", strip=True))
            if text:
                return re.sub(r"\s*[,，]\s*", "、", text)
    return None


def _looks_like_szu_bigdata_person_name(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized or _EMAIL_PATTERN.search(normalized):
        return False
    if re.fullmatch(r"[\u3400-\u9fff·]{2,8}", normalized):
        return True
    return _looks_like_person_name(normalized)


def _clean_szu_bigdata_research_text(value: str) -> str | None:
    lines = [
        _clean_value(line)
        for line in value.splitlines()
        if _clean_value(line)
    ]
    if len(lines) >= 2:
        return "、".join(lines)
    return _clean_value(value)


def _extract_sztu_suat_detail_fields(html: str, source_url: str) -> dict[str, str]:
    if not _is_sztu_suat_profile_url(source_url):
        return {}

    soup = BeautifulSoup(html, "html.parser")
    scoped_node = _find_sztu_fragment_profile_node(soup, source_url)
    field_soup = BeautifulSoup(str(scoped_node), "html.parser") if scoped_node else soup
    fields: dict[str, str] = {}
    name = _extract_sztu_suat_name(field_soup)
    if name:
        fields["name"] = name
    title = _extract_sztu_suat_title(field_soup)
    if title:
        fields["title"] = title
    email = _extract_email_from_text(
        " ".join(_iter_texts_from_selectors(field_soup, _SZTU_SUAT_FIELD_SELECTORS))
    )
    if email:
        fields["email"] = email
    research_directions = _extract_sztu_suat_table_research_directions(field_soup)
    if research_directions:
        fields["research_directions"] = research_directions
    raw_text = _extract_sztu_suat_profile_raw_text(soup, source_url)
    if raw_text:
        fields["profile_raw_text"] = raw_text
    if "title" not in fields and raw_text:
        title = _extract_sztu_suat_title_from_profile_text(raw_text, name)
        if title:
            fields["title"] = title
    return fields


def _is_sztu_suat_profile_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    host = parsed.hostname or ""
    return (
        (host.endswith("sztu.edu.cn") or host.endswith("suat-sz.edu.cn"))
        and ("/info/" in parsed.path or _is_sztu_suat_fragment_profile_url(source_url))
    )


def _is_sztu_suat_fragment_profile_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    host = parsed.hostname or ""
    return (
        (host.endswith("sztu.edu.cn") or host.endswith("suat-sz.edu.cn"))
        and parsed.fragment.startswith("prof-")
    )


_SZTU_SUAT_NAME_SELECTORS = (
    ".ldxm",
    ".team-item__name",
    ".szdw_txt .title",
    ".m-details2 .name",
    ".teacher-details .name",
    ".m-person-introduce1 .name",
    ".ej_nry_dsjs .bt",
    ".con_xx .bt",
    ".v_news_content h1",
)
_SZTU_SUAT_TITLE_SELECTORS = (
    ".ldzw",
    ".team-item__title",
    ".szdw_txt .title",
    ".m-details2 .i-t",
    ".m-details2 .t-c",
    ".teacher-details .text-con .text",
    ".m-person-introduce1 .info .span",
    ".ej_nry_dsjs .p1",
    ".con_xx .p1",
)
_SZTU_SUAT_FIELD_SELECTORS = (
    *_SZTU_SUAT_NAME_SELECTORS,
    *_SZTU_SUAT_TITLE_SELECTORS,
    ".teacher-details .des",
    ".m-details2 .info",
    ".m-person-introduce1 .info",
    ".ej_nry_dsjs .con_xx",
)
_SZTU_SUAT_PROFILE_SELECTORS = (
    ".teacher-details",
    ".m-details2",
    ".m-person-introduce1",
    ".ej_nry_dsjs",
    ".content-body",
    ".szdw_bd",
    "[id^='vsb_content']",
    ".v_news_content",
)


def _extract_sztu_suat_name(soup: BeautifulSoup) -> str | None:
    profile_context = _normalize_text(soup.get_text(" ", strip=True))
    for text in _iter_texts_from_selectors(soup, _SZTU_SUAT_NAME_SELECTORS):
        candidate = (
            _extract_name_from_profile_text(text)
            or _extract_sztu_suat_name_with_role_suffix(text, profile_context)
            or _normalize_text(text)
        )
        if _sztu_suat_text_looks_like_section_heading(candidate):
            continue
        if candidate == _normalize_text(text) and _sztu_suat_text_has_admin_support_role(
            text
        ):
            continue
        if _looks_like_person_name(candidate):
            return candidate
    return None


def _extract_sztu_suat_title(soup: BeautifulSoup) -> str | None:
    for text in _iter_texts_from_selectors(soup, _SZTU_SUAT_TITLE_SELECTORS):
        title = _extract_sztu_suat_title_from_text(text)
        if title:
            return title
    return None


def _iter_texts_from_selectors(soup: BeautifulSoup, selectors: tuple[str, ...]):
    for selector in selectors:
        for node in soup.select(selector):
            text = _normalize_text(node.get_text(" ", strip=True))
            if text:
                yield text


def _extract_sztu_suat_title_from_text(text: str) -> str | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    for label in ("职称职务", "职称", "岗位"):
        value = _extract_labeled_value(normalized, label)
        title = _extract_sztu_suat_academic_title(value or "")
        if title:
            return title
    return _extract_sztu_suat_academic_title(normalized)


def _extract_sztu_suat_name_with_role_suffix(
    text: str,
    profile_context: str,
) -> str | None:
    normalized = _normalize_text(text)
    if not _sztu_suat_text_has_admin_support_role(normalized):
        return None
    match = re.match(r"^(?P<name>[\u3400-\u9fff·]{2,8})\s+.+$", normalized)
    if not match:
        return None
    name = _normalize_text(match.group("name"))
    if not _sztu_suat_context_has_academic_role_for_name(profile_context, name):
        return None
    return name if _looks_like_person_name(name) else None


def _sztu_suat_text_has_admin_support_role(text: str | None) -> bool:
    normalized = _normalize_text(text or "")
    return any(marker in normalized for marker in _SZTU_SUAT_ADMIN_SUPPORT_ROLE_HINTS)


def _sztu_suat_text_looks_like_section_heading(text: str | None) -> bool:
    normalized = _normalize_text(text or "")
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _NON_NAME_HEADING_KEYWORDS)


def _sztu_suat_context_has_academic_role_for_name(
    profile_context: str,
    name: str,
) -> bool:
    normalized_context = _normalize_text(profile_context)
    normalized_name = _normalize_text(name)
    if not normalized_context or not normalized_name:
        return False
    return bool(
        re.search(
            rf"{re.escape(normalized_name)}\s*[，,、]?\s*[^。；;\n]{{0,80}}"
            rf"{_ACADEMIC_TITLE_PHRASE}",
            normalized_context,
            flags=re.IGNORECASE,
        )
    )


def _extract_sztu_suat_academic_title(text: str) -> str | None:
    cleaned = _clean_value(text).strip(".。")
    if not cleaned:
        return None
    if _looks_like_academic_title(cleaned):
        return cleaned
    return _extract_bounded_academic_title(cleaned)


def _extract_sztu_suat_title_from_profile_text(
    profile_text: str,
    name: str | None,
) -> str | None:
    normalized = _normalize_text(profile_text)
    if not normalized:
        return None

    candidates: list[str] = []
    if name:
        name_pattern = re.escape(name)
        for match in re.finditer(
            rf"{name_pattern}\s*[，,、]?\s*(?P<context>[^。；;\n]{{0,100}})",
            normalized,
        ):
            context = _normalize_text(match.group("context"))
            if context:
                candidates.append(context)
    candidates.append(normalized[:360])

    for candidate in candidates:
        title = _extract_sztu_suat_academic_title(candidate)
        if title:
            return title
    return None


def _extract_sztu_suat_table_research_directions(soup: BeautifulSoup) -> str | None:
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        label = _normalize_text(cells[0].get_text(" ", strip=True))
        if not any(research_label in label for research_label in _RESEARCH_LABELS[:2]):
            continue
        value = _clean_value(cells[1].get_text(" ", strip=True))
        if value:
            return re.sub(r"\s*[,，]\s*", "、", value)
    return None


def _extract_sztu_suat_profile_raw_text(
    soup: BeautifulSoup,
    source_url: str,
) -> str | None:
    fragment_text = _extract_sztu_fragment_profile_raw_text(soup, source_url)
    if fragment_text:
        return fragment_text
    for selector in _SZTU_SUAT_PROFILE_SELECTORS:
        for node in soup.select(selector):
            if _node_looks_like_roster_list(node):
                continue
            text = _extract_clean_profile_node_text(node)
            if _looks_like_publication_only_profile_block(text):
                continue
            if text and len(text) >= 20:
                return text
    return None


def _extract_sztu_suat_research_directions_from_profile_text(
    profile_text: str | None,
    source_url: str,
) -> list[str]:
    if not profile_text or not _is_sztu_suat_profile_url(source_url):
        return []
    normalized = _normalize_text(profile_text)
    if not normalized:
        return []
    numbered_topics = _extract_sztu_suat_numbered_research_topics(normalized)
    if numbered_topics:
        return numbered_topics
    labels = ("主要研究方向", "研究方向", "研究领域")
    for label in labels:
        pattern = rf"{re.escape(label)}\s*(?:为|是|包括|集中于|[：:])?\s*(?P<body>.+)"
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            body = _trim_sztu_suat_research_body(match.group("body"))
            parts = _split_sztu_suat_research_topics(body)
            if parts:
                return parts
    return []


def _trim_sztu_suat_research_body(value: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    stop_match = re.search(
        r"(?:教育及工作经历|教育经历|工作经历|代表性文章|代表性论文|部分发表|"
        r"科研项目|学术成果|电子邮箱|邮箱|联系方式|个人简介|发表和出版|主持)",
        normalized,
    )
    if stop_match is not None:
        normalized = normalized[: stop_match.start()]
    normalized = re.split(r"[。.!！?？]", normalized, maxsplit=1)[0]
    return _normalize_text(normalized).strip("：:;,，；、")


def _extract_sztu_suat_numbered_research_topics(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []
    label_match = re.search(r"(?:主要研究方向|研究方向|研究领域)\s*[：:]?", normalized)
    if label_match is not None:
        normalized = normalized[label_match.end() :]
    stop_match = re.search(
        r"(?:代表性成果|代表性文章|代表性论文|学术服务|科研项目|招生与招聘|"
        r"English Biography|Chinese Biography|Open positions)",
        normalized,
        flags=re.IGNORECASE,
    )
    if stop_match is not None:
        normalized = normalized[: stop_match.start()]

    topics: list[str] = []
    for match in re.finditer(
        r"(?:^|\s)\d+[.、]\s*(?P<topic>[^：:。；;\n]{2,80})[：:]",
        normalized,
    ):
        topic = _clean_value(match.group("topic"))
        topic = topic.strip(" .。；;，,、")
        if not topic or len(topic) > 80:
            continue
        if any(blocker in topic for blocker in _STRUCTURED_RESEARCH_BLOCKERS):
            continue
        if topic not in topics:
            topics.append(topic)
    return _clean_structured_research_directions(topics)


def _split_sztu_suat_research_topics(value: str) -> list[str]:
    topics: list[str] = []
    for part in re.split(r"[、,，;/；]\s*", value):
        topic = _clean_value(part)
        topic = re.sub(r"^(?:为|是)\s*", "", topic)
        topic = re.sub(r"^(?:主要)?(?:从事|围绕|开展|致力于)\s*", "", topic)
        topic = re.sub(r"^(?:包括|涉及|及)\s*", "", topic)
        topic = re.sub(r"(?:等)?(?:相关)?(?:研究|方向|领域|工作|方面)$", "", topic)
        topic = re.sub(r"等$", "", topic)
        topic = topic.strip(" .。；;，,、")
        if not topic or len(topic) > 80:
            continue
        if any(blocker in topic for blocker in _STRUCTURED_RESEARCH_BLOCKERS):
            continue
        if topic not in topics:
            topics.append(topic)
    return _clean_structured_research_directions(topics)


def _sztu_suat_research_directions_need_cleanup(values: list[str]) -> bool:
    noisy_markers = (
        "教育及工作经历",
        "教育经历",
        "工作经历",
        "代表性文章",
        "代表性论文",
        "电子邮箱",
        "联系方式",
    )
    return any(any(marker in value for marker in noisy_markers) for value in values)


def _extract_sztu_fragment_profile_raw_text(
    soup: BeautifulSoup,
    source_url: str,
) -> str | None:
    node = _find_sztu_fragment_profile_node(soup, source_url)
    if node is None:
        return None
    text = _extract_clean_profile_node_text(node)
    if text and len(text) >= 20:
        return text
    return None


def _find_sztu_fragment_profile_node(
    soup: BeautifulSoup,
    source_url: str,
) -> Tag | None:
    parsed = urlparse(source_url)
    if not parsed.fragment.startswith("prof-"):
        return None
    name = _normalize_text(unquote(parsed.fragment.removeprefix("prof-")))
    if not name:
        return None
    for node in soup.select(".team-item"):
        if not isinstance(node, Tag):
            continue
        node_name = _extract_sztu_suat_name(BeautifulSoup(str(node), "html.parser"))
        if node_name == name:
            return node
        node_text = _normalize_text(node.get_text(" ", strip=True))
        if not node_text:
            continue
        first_window = node_text[:80]
        if first_window.startswith(name) or re.search(
            rf"(^|\s){re.escape(name)}(?:\s|$)",
            first_window,
        ):
            return node
    return None


def _normalize_sigs_teacher_name(value: str | None) -> str | None:
    normalized = _normalize_text(value or "")
    if not normalized:
        return None
    normalized = re.sub(
        r"^(?:姓名|Name)\s*[：:]\s*", "", normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(r"[（(][^()（）]*[）)]", "", normalized)
    normalized = _normalize_text(normalized).strip("：:;；,，")
    return normalized or None


def _extract_sigs_tab_sections(
    html: str,
    source_url: str | None = None,
) -> tuple[SigsTabSection, ...]:
    if source_url and "sigs.tsinghua.edu.cn" not in source_url:
        return ()

    soup = BeautifulSoup(html, "html.parser")
    sections: list[SigsTabSection] = []
    for tab in soup.select(".sudy-tab"):
        menu_labels = [
            _normalize_text(item.get_text(" ", strip=True))
            for item in tab.select(".tab-menu > li")
        ]
        tab_items = tab.select(".tab-list > li")
        for index, tab_item in enumerate(tab_items):
            tab_label = menu_labels[index] if index < len(menu_labels) else ""
            posts = tab_item.select(":scope > .post")
            if not posts:
                posts = tab_item.select(".post")
            if not posts:
                posts = [tab_item]
            for post in posts:
                section_title = _extract_sigs_section_title(post, tab_label)
                content_node = post.select_one(".con") or post
                lines = _extract_sigs_section_lines(content_node, section_title)
                if not lines:
                    continue
                text = _normalize_text(" ".join(lines))
                if not text:
                    continue
                sections.append(
                    SigsTabSection(
                        tab_label=tab_label,
                        section_title=section_title,
                        text=text,
                        lines=tuple(lines),
                    )
                )
    return tuple(sections)


def _extract_sigs_section_title(node, fallback: str) -> str:
    for selector in (".tit .title", ".tt .title", "h1", "h2", "h3", "h4"):
        title_node = node.select_one(selector)
        if title_node is None:
            continue
        title = _normalize_text(title_node.get_text(" ", strip=True))
        if title:
            return title
    return _normalize_text(fallback)


def _extract_sigs_section_lines(node, section_title: str) -> list[str]:
    lines: list[str] = []
    line_nodes = node.find_all(["p", "li"], recursive=True)
    if not line_nodes:
        line_nodes = [node]
    for line_node in line_nodes:
        line = _normalize_text(line_node.get_text(" ", strip=True))
        if not line or line == section_title:
            continue
        if section_title and line.startswith(section_title):
            line = _normalize_text(line[len(section_title) :])
        if line and line not in lines:
            lines.append(line)
    return lines


def _extract_sigs_research_topics_from_sections(
    sections: tuple[SigsTabSection, ...],
) -> list[str]:
    topics: list[str] = []
    for section in sections:
        if not _is_sigs_research_section(section):
            continue
        for line in section.lines or (section.text,):
            for topic in _derive_sigs_research_topics(line):
                _append_unique_topic(topics, topic)
    return topics


def _is_sigs_research_section(section: SigsTabSection) -> bool:
    markers = (
        "研究领域",
        "研究方向",
        "research interests",
        "research directions",
        "research area",
    )
    section_title = section.section_title.casefold()
    tab_label = section.tab_label.casefold()
    if section_title and section_title != tab_label:
        return any(marker in section_title for marker in markers)
    return any(marker in section_title or marker in tab_label for marker in markers)


_SIGS_RESEARCH_LABEL_RE = re.compile(
    r"^(?:研究(?:方向|领域)|research\s*(?:area|interests?|directions?))\s*[：:]\s*",
    flags=re.IGNORECASE,
)
_SIGS_RESEARCH_PHRASE_HINTS = (
    "trustworthy artificial intelligence",
    "medical image analysis",
    "brain disease diagnosis and prognosis",
    "multi-modal neuroimaging data fusion",
    "pattern recognition",
    "neural informatics",
    "explainable AI",
)
_SIGS_RESEARCH_TOPIC_BLOCKERS = (
    "revise",
    "presented",
    "presented at",
    "coauthor",
    "conference",
    "journal",
    "meeting",
    "university of",
    "sole-authored",
    "co-authored",
    "review of",
    "项目",
    "基金",
    "负责人",
    "子课题",
    "计划",
    "医院",
    "规划",
    "进行",
    "正在",
    "利用",
    "相比",
    "同时",
    "具有",
    "过程中",
    "准确性",
    "稳定性",
    "首次实现",
    "发表",
    "论文",
    "成果",
    "会议",
)


def _derive_sigs_research_topics(value: str) -> list[str]:
    normalized = _normalize_text(_SIGS_RESEARCH_LABEL_RE.sub("", value or ""))
    if not normalized:
        return []

    topics: list[str] = []
    for topic in _extract_sigs_chinese_research_topics(normalized):
        _append_unique_topic(topics, topic)

    if _contains_cjk(normalized):
        if topics:
            return topics
        if any(
            blocker in normalized.casefold() or blocker in normalized
            for blocker in _SIGS_RESEARCH_TOPIC_BLOCKERS
        ):
            return []
        if _looks_like_sigs_narrative(normalized):
            return []
        for part in re.split(r"[、；;]\s*", normalized):
            candidate = _clean_sigs_research_topic(part)
            if _looks_like_sigs_research_topic(candidate):
                _append_unique_topic(topics, candidate or "")
        return topics

    if _looks_like_sigs_publication_or_service_line(normalized):
        return topics

    for topic in _extract_sigs_english_research_topics(normalized):
        _append_unique_topic(topics, topic)
    if topics:
        return topics

    if _looks_like_sigs_research_topic(normalized) and not _looks_like_sigs_narrative(
        normalized
    ):
        _append_unique_topic(topics, normalized)

    for part in re.split(r"[、；;]\s*|\s+(?:and|or)\s+", normalized):
        candidate = _clean_sigs_research_topic(part)
        if _looks_like_sigs_research_topic(candidate):
            _append_unique_topic(topics, candidate or "")

    for part in re.split(r"[,，]\s*", normalized):
        candidate = _clean_sigs_research_topic(part)
        if _looks_like_sigs_research_topic(candidate):
            _append_unique_topic(topics, candidate or "")

    lowered = normalized.casefold()
    for phrase in _SIGS_RESEARCH_PHRASE_HINTS:
        if phrase.casefold() in lowered:
            _append_unique_topic(topics, phrase)

    for pattern in (
        r"focus(?:es)? on developing (?P<topic>.+?) for (?P<context>.+?)(?:,\s+with|\.|$)",
        r"emphasis on (?P<topic>.+?)(?:\.|,|;|$)",
        r"with (?P<topic>multi-modal .+?) to build",
        r"applying (?P<topic>.+?) to uncover",
        r"prioritizing (?P<topic>.+?) to ensure",
    ):
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            for group_name in ("topic", "context"):
                candidate = _clean_sigs_research_topic(match.groupdict().get(group_name))
                if _looks_like_sigs_research_topic(candidate):
                    _append_unique_topic(topics, candidate or "")
            topic = match.groupdict().get("topic")
            if topic and " and " in topic.casefold():
                for part in re.split(r"\s+and\s+", topic, flags=re.IGNORECASE):
                    candidate = _clean_sigs_research_topic(part)
                    if _looks_like_sigs_research_topic(candidate):
                        _append_unique_topic(topics, candidate or "")

    return topics


def _extract_sigs_english_research_topics(value: str) -> list[str]:
    normalized = _normalize_text(value)
    lowered = normalized.casefold()
    topics: list[str] = []
    applications_match = re.match(
        r"(?P<head>.+?)\s+and\s+their\s+applications\s+for\s+.+?,\s*including\s+(?P<tail>.+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if applications_match:
        _append_unique_topic(topics, applications_match.group("head"))
        for part in re.split(r"[,;]\s*|\s+and\s+", applications_match.group("tail")):
            _append_unique_topic(topics, part)
        return topics

    if "including " in lowered:
        head, tail = re.split(r"\bincluding\b", normalized, maxsplit=1, flags=re.IGNORECASE)
        if _looks_like_sigs_research_topic(head):
            _append_unique_topic(topics, head)
        for part in re.split(r"[,;]\s*|\s+and\s+", tail):
            _append_unique_topic(topics, part)
    return topics


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def _looks_like_sigs_publication_or_service_line(value: str) -> bool:
    lowered = value.casefold()
    if any(blocker in lowered for blocker in _SIGS_RESEARCH_TOPIC_BLOCKERS):
        return True
    if re.search(r"\((?:19|20)\d{2}\)", value):
        return True
    if re.search(r"\bwith\s+[A-Z][A-Za-z. -]{2,}", value):
        return True
    if any(marker in value for marker in ("“", "”", '"')) and any(
        marker in lowered for marker in ("authored", "revise", "presented", "with ")
    ):
        return True
    return False


def _extract_sigs_chinese_research_topics(value: str) -> list[str]:
    topics: list[str] = []
    keyword_match = re.search(
        r"关键词为[“\"](?P<body>[^”\"]{2,40})[”\"]",
        value,
    )
    if keyword_match:
        candidate = _clean_sigs_research_topic(keyword_match.group("body"))
        if _looks_like_sigs_research_topic(candidate):
            _append_unique_topic(topics, candidate or "")
        return topics

    direction_match = re.search(
        r"(?:研究方向\s*包括|主要研究方向(?:\s*包括)?|主要研究领域(?:\s*包括)?|研究领域(?:\s*包括)?|研究方向\s*[：:])(?P<body>.+)",
        value,
    )
    if direction_match:
        body = re.split(
            r"(?:，|,|。)?(?:近年来|主持|并发表|台湾执行计划|以下|组织|IEEE|在国内外|通过|作为|累计|申请|授权|等)",
            direction_match.group("body"),
            maxsplit=1,
        )[0]
        for topic in re.split(r"[、,，；;]\s*", body):
            candidate = _clean_sigs_research_topic(topic)
            if _looks_like_sigs_research_topic(candidate):
                _append_unique_topic(topics, candidate or "")

    numbered_match = re.match(r"^\s*\d+[.、]\s*(?P<body>.+)", value)
    if numbered_match:
        body = re.split(r"[，,。；;]\s*(?:主要|用于|主持|承担)", numbered_match.group("body"), maxsplit=1)[0]
        segments = [body]
        if " " in body:
            head, tail = body.split(" ", 1)
            segments = [head, *re.split(r"[、,，；;]\s*", tail)]
        for topic in segments:
            candidate = _clean_sigs_research_topic(topic)
            if _looks_like_sigs_research_topic(candidate):
                _append_unique_topic(topics, candidate or "")

    return topics


def _clean_sigs_research_topic(value: str | None) -> str | None:
    cleaned = _clean_value(value or "")
    cleaned = re.sub(r"^\s*\d+[.、]\s*", "", cleaned)
    cleaned = re.sub(
        r"^(?:研究方向\s*包括|主要研究方向(?:\s*包括)?|主要研究领域(?:\s*包括)?|研究领域(?:\s*包括)?|研究方向)\s*[：:]?",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^包括", "", cleaned)
    cleaned = re.sub(r"等$", "", cleaned).strip()
    cleaned = re.sub(
        r"^(?:developing|advanced|machine and deep learning techniques with)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:techniques|systems|work|research)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:including)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:等领域|等方法|等)$", "", cleaned)
    return cleaned.strip(" .，,。；;") or None


def _looks_like_sigs_research_topic(value: str | None) -> bool:
    normalized = _clean_sigs_research_topic(value)
    if not normalized or len(normalized) > 80:
        return False
    lowered = normalized.casefold()
    if any(blocker in normalized for blocker in _STRUCTURED_RESEARCH_BLOCKERS):
        return False
    if any(blocker in lowered or blocker in normalized for blocker in _SIGS_RESEARCH_TOPIC_BLOCKERS):
        return False
    if any(marker in normalized for marker in ("“", "”", '"')):
        return False
    if "。" in normalized or "，" in normalized:
        return False
    if any(marker in normalized for marker in ("个人简历", "教学", "研究成果", "奖励荣誉")):
        return False
    if re.search(r"\((?:19|20)\d{2}\)", normalized):
        return False
    if re.match(r"^[oO]\s+", normalized):
        return False
    if "." in normalized:
        return False
    if len(normalized.split()) > 10:
        return False
    return True


def _looks_like_sigs_narrative(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "长期从事",
            "主持",
            "近年来",
            "承担",
            "主要包括",
            "工作",
            "研究工作",
        )
    )


def _append_unique_topic(items: list[str], value: str) -> None:
    normalized = _clean_sigs_research_topic(value)
    if not normalized:
        return
    key = normalized.casefold()
    if key in {item.casefold() for item in items}:
        return
    items.append(normalized)


def _extract_profile_raw_text(html: str, source_url: str | None = None) -> str | None:
    markdown_text = _extract_reader_markdown_profile_raw_text(html)
    if markdown_text:
        return markdown_text

    soup = BeautifulSoup(html, "html.parser")
    for selector in _profile_raw_text_selectors(source_url):
        node = soup.select_one(selector)
        if node is None:
            continue
        if _node_looks_like_roster_list(node):
            continue
        text = _extract_clean_profile_node_text(node)
        if _looks_like_publication_only_profile_block(text):
            continue
        if text and len(text) >= 20:
            return text
    if urlparse(source_url or "").fragment:
        text = _extract_clean_profile_node_text(soup)
        if text and len(text) >= 20 and not _looks_like_publication_only_profile_block(text):
            return text
    return None


def _profile_raw_text_selectors(source_url: str | None) -> tuple[str, ...]:
    selectors = (
        ".message-right",
        ".teacher_right",
        ".col_news_con",
        ".sudy-tab",
        ".detail-message",
        ".teacher-detail .col-md-9",
        ".teacher-message",
        ".teacherDetail",
        ".arc-con",
        ".field-name-body",
        ".region-content",
        ".wp_articlecontent",
        ".articlecontent",
        ".article_content",
        ".news_content",
        ".v_news_content",
        "[id^='vsb_content']",
        ".main_cont",
        ".mainright .cont",
        ".content .detail",
        ".detail .content",
        ".content",
        ".detail",
        "article",
        "main",
    )
    if _should_scope_sysu_col_md_9_profile(source_url):
        return (".col-md-9",) + selectors
    return selectors


def _should_scope_sysu_col_md_9_profile(source_url: str | None) -> bool:
    parsed = urlparse(source_url or "")
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    leaf = path.rsplit("/", 1)[-1]
    if hostname == "sic.sysu.edu.cn":
        return path.startswith("/members/") and not leaf.startswith("index.")
    if hostname == "am.sysu.edu.cn":
        return path.startswith("/teacher/") or path.startswith("/szdw/")
    return False


def _extract_cuhk_myweb_profile_raw_text(html: str, source_url: str) -> str | None:
    parsed = urlparse(source_url)
    if (parsed.hostname or "").lower() != "myweb.cuhk.edu.cn":
        return None

    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        "article.profile",
        ".profile-content",
        ".personal-profile",
        ".entry-content",
        ".post-content",
        "main article",
        "main",
        "article",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        text = _extract_clean_profile_node_text(node)
        if _looks_like_cuhk_myweb_profile_text(text):
            return text
    return None


def _looks_like_cuhk_myweb_profile_text(text: str | None) -> bool:
    normalized = _normalize_text(text or "")
    if len(normalized) < 20:
        return False
    if _looks_like_publication_only_profile_block(normalized):
        return False
    lowered = normalized.casefold()
    return any(
        marker.casefold() in lowered
        for marker in (
            "Position",
            "Email",
            "Research Interests",
            "Research Directions",
            "教授",
            "研究方向",
            "研究领域",
        )
    )


def _extract_clean_profile_node_text(node) -> str:
    soup = BeautifulSoup(str(node), "html.parser")
    for noisy_node in soup.select(
        "nav, footer, aside, "
        ".nav, .navbar, .header-nav, .breadcrumb, .footer, .copyright, "
        ".sidebar, .side, .menu, .loca, .position"
    ):
        noisy_node.decompose()
    return _strip_leading_non_person_profile_titles(
        _normalize_text(soup.get_text(" ", strip=True))
    )


def _strip_leading_non_person_profile_titles(text: str) -> str:
    cleaned = _normalize_text(text)
    for _ in range(4):
        head, separator, tail = cleaned.partition(" ")
        if not separator or not tail:
            break
        if head.strip("：:;；,，") not in _LEADING_PROFILE_TITLE_NOISE:
            break
        cleaned = _normalize_text(tail)
    return cleaned


def _extract_reader_markdown_profile_raw_text(html: str) -> str | None:
    if "Markdown Content:" not in html and "##" not in html:
        return None
    markdown = re.split(r"Markdown Content\s*:\s*", html, maxsplit=1, flags=re.IGNORECASE)[-1]
    lines = [line.strip() for line in markdown.splitlines()]
    start_index: int | None = None
    for index, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        heading = _strip_markdown_heading(line)
        if any(marker in heading for marker in _MARKDOWN_NAV_HEADING_MARKERS):
            continue
        if _extract_bounded_academic_title(heading) or _reader_heading_has_next_line_title(
            heading,
            lines[index + 1 :],
        ):
            start_index = index
            break
    if start_index is None:
        return None

    scoped_lines: list[str] = []
    for line in lines[start_index:]:
        if not line:
            continue
        stripped_heading = _strip_markdown_heading(line) if line.startswith("#") else line
        if scoped_lines and _looks_like_reader_markdown_footer(stripped_heading):
            break
        scoped_lines.append(stripped_heading)

    text = _normalize_text(" ".join(scoped_lines))
    return text if len(text) >= 20 else None


def _reader_heading_has_next_line_title(heading: str, following_lines: list[str]) -> bool:
    if not _looks_like_person_name(heading):
        return False
    for line in following_lines[:4]:
        candidate = _strip_markdown_heading(line) if line.startswith("#") else line
        if not candidate:
            continue
        if any(marker in candidate for marker in _MARKDOWN_NAV_HEADING_MARKERS):
            return False
        return _extract_bounded_academic_title(candidate) is not None
    return False


def _strip_markdown_heading(line: str) -> str:
    return line.lstrip("#").strip()


def _looks_like_reader_markdown_footer(line: str) -> bool:
    lowered = line.casefold()
    return any(
        marker in lowered or marker in line
        for marker in ("footer", "copyright", "版权所有")
    )


def _node_looks_like_roster_list(node) -> bool:
    if node.select_one(".listteacher, ul.listteacher"):
        text = _normalize_text(node.get_text(" ", strip=True))
        return not any(
            marker in text
            for marker in (
                "邮箱",
                "Email",
                "研究领域",
                "研究方向",
                "个人简介",
                "教育背景",
                "科研成果",
            )
        )
    return False


def _looks_like_publication_only_profile_block(text: str | None) -> bool:
    normalized = _normalize_text(text or "")
    if not normalized:
        return False
    has_publication_marker = any(
        marker in normalized
        for marker in ("代表性论文", "论文发表", "Publications", "Publication")
    )
    has_profile_marker = any(
        marker in normalized
        for marker in (
            "个人简介",
            "教育背景",
            "工作经历",
            "研究方向",
            "研究领域",
            "职称",
            "邮箱",
            "电子邮箱",
            "Email",
        )
    )
    return has_publication_marker and not has_profile_marker


def _extract_department_from_profile_text(
    text: str | None,
    institution: str | None,
) -> str | None:
    if not text or "南方科技大学" not in (institution or ""):
        return None
    for match in _SUSTECH_DEPARTMENT_CONTEXT_PATTERN.finditer(text):
        department = _clean_department(match.group("context"))
        if department:
            return department
    return None


def _clean_department(value: str | None) -> str | None:
    cleaned = _clean_value(value or "")
    if not cleaned:
        return None
    cleaned = re.sub(r"(?:双聘)?(?:助理教授|副教授|教授|讲师|研究员|博士生导师|博导).*$", "", cleaned)
    cleaned = cleaned.strip(" ，,、")
    suffix_matches = list(re.finditer(_DEPARTMENT_SUFFIX_PATTERN, cleaned))
    if suffix_matches:
        cleaned = cleaned[: suffix_matches[-1].end()].strip(" ，,、")
    if not cleaned or len(cleaned) > 50:
        return None
    if "博士" in cleaned:
        return None
    if not re.search(_DEPARTMENT_SUFFIX_PATTERN, cleaned):
        return None
    return cleaned


def _looks_like_academic_title(value: str | None) -> bool:
    normalized = _normalize_text(value or "")
    return bool(normalized and _ACADEMIC_TITLE_PATTERN.fullmatch(normalized))


def _extract_first_title_value(text_samples: list[str]) -> str | None:
    for sample in text_samples:
        if not sample:
            continue
        for label in _TITLE_LABELS:
            if _looks_like_non_profile_title_label_context(sample, label):
                continue
            value = _extract_labeled_value(sample, label)
            if label.casefold() == "title" and not _title_label_value_allowed(value):
                continue
            title = _normalize_title_candidate(value)
            if title:
                return title
        if _looks_like_academic_title(sample):
            return _normalize_text(sample)
    return None


def _looks_like_non_profile_title_label_context(sample: str, label: str) -> bool:
    if label.casefold() != "title":
        return False
    lowered = _normalize_text(sample).casefold()
    return any(
        marker in lowered
        for marker in (
            "patent",
            "inventor",
            "applicant",
            "专利",
            "发明人",
            "申请人",
            "publication",
            "publications",
            "journal papers",
        )
    )


def _title_label_value_allowed(value: str | None) -> bool:
    cleaned = _clean_value(value or "")
    if not cleaned:
        return False
    return _looks_like_academic_title(cleaned) or bool(
        _ENGLISH_ACADEMIC_TITLE_HINT_RE.search(cleaned)
    )


def _extract_markdown_heading_title(text_samples: list[str]) -> str | None:
    for sample in text_samples:
        for heading in _iter_markdown_heading_segments(sample):
            if any(marker in heading for marker in _MARKDOWN_NAV_HEADING_MARKERS):
                continue
            title = _extract_bounded_academic_title(heading)
            if title:
                return title
    return None


def _iter_markdown_heading_segments(text: str):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            yield stripped.lstrip("#").strip()
    for match in re.finditer(r"(?:^|\s)#{1,6}\s+([^#]+?)(?=(?:\s+#{1,6}\s+)|$)", text):
        yield _normalize_text(match.group(1))


def _normalize_title_candidate(value: str | None) -> str | None:
    cleaned = _clean_value(value or "")
    if not cleaned:
        return None
    if _looks_like_academic_title(cleaned):
        return cleaned
    if _is_contaminated_title_candidate(cleaned):
        return None
    return cleaned


def _is_contaminated_title_candidate(value: str) -> bool:
    normalized = _normalize_text(value)
    return len(normalized) > 80 or any(
        marker in normalized for marker in _TITLE_CONTAMINATION_MARKERS
    )


def _extract_bounded_academic_title(value: str) -> str | None:
    normalized = _normalize_text(value)
    for match in _ACADEMIC_TITLE_SEARCH_PATTERN.finditer(normalized):
        title = _normalize_text(match.group(0))
        if _looks_like_academic_title(title):
            return title
    return None


def _looks_like_person_name(value: str | None) -> bool:
    normalized = _normalize_text(value or "")
    if not normalized or len(normalized) > 32:
        return False
    if _EMAIL_PATTERN.search(normalized) or _looks_like_academic_title(normalized):
        return False
    if _extract_bounded_academic_title(normalized):
        return False
    if is_obvious_non_person_name(normalized):
        return False
    return True


def _extract_uestc_yjsjy_detail_profile(
    *,
    html: str,
    source_url: str,
    institution: str | None,
    department: str | None,
) -> ExtractedProfessorProfile | None:
    if "yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/" not in source_url:
        return None

    soup = BeautifulSoup(html, "html.parser")
    profile_table = soup.select_one("#mcontent .news_list table.box")
    if profile_table is None:
        return None

    name = _clean_value(_text_from_selector(profile_table, "span#Labeldsxm") or "")
    title = _normalize_title_candidate(
        _text_from_selector(profile_table, "span#Labelzc")
    )
    if title is None:
        title_candidate = _text_from_selector(profile_table, "span#Labeltc")
        if _looks_like_academic_title(title_candidate):
            title = _normalize_title_candidate(title_candidate)

    email = _extract_uestc_yjsjy_email(profile_table)
    raw_text = _extract_uestc_yjsjy_profile_raw_text(profile_table, source_url)
    research_directions = _extract_uestc_yjsjy_research_directions(
        profile_table,
        raw_text=raw_text,
    )
    secondary_academic_urls = _extract_uestc_yjsjy_secondary_academic_urls(
        str(profile_table),
        source_url,
    )

    return ExtractedProfessorProfile(
        name=name or None,
        institution=_normalize_optional_context(institution),
        department=_normalize_optional_context(department),
        title=title,
        email=email,
        homepage_url=_extract_uestc_yjsjy_homepage_url(profile_table, source_url),
        profile_url=source_url,
        office=None,
        research_directions=tuple(research_directions),
        source_urls=(source_url, *secondary_academic_urls),
        profile_raw_text=raw_text or None,
    )


def _text_from_selector(node, selector: str) -> str | None:
    selected = node.select_one(selector)
    if selected is None:
        return None
    text = _normalize_text(selected.get_text(" ", strip=True))
    return text or None


def _extract_uestc_yjsjy_email(profile_table) -> str | None:
    email_node = profile_table.select_one("span#Labelemail")
    if email_node is None:
        return None
    email = _normalize_email(email_node.get_text(" ", strip=True))
    if email:
        return email
    parent_cell = email_node.find_parent(["td", "th"])
    if parent_cell is None:
        return None
    return _normalize_email(parent_cell.get_text(" ", strip=True))


def _extract_uestc_yjsjy_research_directions(
    profile_table,
    *,
    raw_text: str | None = None,
) -> list[str]:
    directions: list[str] = []
    narrative_candidates: list[str] = []
    for row in profile_table.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2 or _is_uestc_yjsjy_container_row(cells):
            continue
        label = _normalize_text(cells[0].get_text(" ", strip=True))
        value = _extract_uestc_yjsjy_row_value(cells)
        if "专业研究方向" in label:
            if value and value not in directions:
                directions.append(value)
            continue
        if value:
            narrative_candidates.extend(
                _extract_uestc_yjsjy_narrative_research_directions(value)
            )
    if directions:
        return directions
    if raw_text:
        narrative_candidates.extend(
            _extract_uestc_yjsjy_narrative_research_directions(raw_text)
        )
    return _clean_structured_research_directions(narrative_candidates)


def _extract_uestc_yjsjy_profile_raw_text(profile_table, source_url: str) -> str:
    row_texts: list[str] = []
    for row in profile_table.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells or _is_uestc_yjsjy_container_row(cells):
            continue
        label = _normalize_text(cells[0].get_text(" ", strip=True))
        value_cell = _extract_uestc_yjsjy_value_cell(cells)
        value = _normalize_text(value_cell.get_text(" ", strip=True)) if value_cell else ""
        link_cell = value_cell or cells[0]
        hrefs = [
            urljoin(source_url, href)
            for anchor in link_cell.find_all("a", href=True)
            if (href := str(anchor.get("href", "")).strip())
            and not href.lower().startswith(("mailto:", "javascript:", "tel:", "#"))
        ]
        parts = [part for part in (label, value, " ".join(hrefs)) if part]
        if parts:
            row_texts.append(" ".join(parts))
    return _normalize_text(" ".join(row_texts))


def _is_uestc_yjsjy_container_row(cells) -> bool:
    return len(cells) == 1 and cells[0].find("table") is not None


def _extract_uestc_yjsjy_row_value(cells) -> str:
    value_cell = _extract_uestc_yjsjy_value_cell(cells)
    if value_cell is None:
        return ""
    return _clean_value(value_cell.get_text(" ", strip=True))


def _extract_uestc_yjsjy_value_cell(cells):
    for cell in cells[1:]:
        if _normalize_text(cell.get_text(" ", strip=True)):
            return cell
    return None


def _extract_uestc_yjsjy_homepage_url(profile_table, source_url: str) -> str | None:
    for row in profile_table.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            continue
        label = _normalize_text(cells[0].get_text(" ", strip=True))
        value_cell = cells[1]
        value_text = _normalize_text(value_cell.get_text(" ", strip=True))
        if not _looks_like_uestc_yjsjy_homepage_label(label):
            for anchor in value_cell.find_all("a", href=True):
                anchor_text = _normalize_text(anchor.get_text(" ", strip=True))
                if _looks_like_uestc_yjsjy_homepage_label(anchor_text):
                    return urljoin(source_url, anchor["href"].strip())
            continue
        for anchor in value_cell.find_all("a", href=True):
            href = anchor["href"].strip()
            if href:
                return urljoin(source_url, href)
        url = _extract_url_from_text(value_text)
        if url:
            return urljoin(source_url, url)
    return None


def _extract_uestc_yjsjy_secondary_academic_urls(
    html: str,
    source_url: str,
) -> tuple[str, ...]:
    if not _is_uestc_yjsjy_detail_url(source_url):
        return ()

    soup = BeautifulSoup(html, "html.parser")
    profile_node = soup.select_one("#mcontent .news_list table.box") or soup
    urls: list[str] = []
    for row in profile_node.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        scoped_nodes = cells if cells else [row]
        context = _normalize_text(" ".join(node.get_text(" ", strip=True) for node in scoped_nodes))
        for anchor in row.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            candidate = _normalize_secondary_academic_url(urljoin(source_url, href))
            anchor_context = _normalize_text(
                " ".join(
                    part
                    for part in (context, anchor.get_text(" ", strip=True), anchor.get("title"))
                    if part
                )
            )
            if _is_uestc_yjsjy_secondary_academic_url(
                candidate,
                context=anchor_context,
                source_url=source_url,
            ):
                urls.append(candidate)
        for candidate in _extract_secondary_academic_bare_urls(context, source_url):
            if _is_uestc_yjsjy_secondary_academic_url(
                candidate,
                context=context,
                source_url=source_url,
            ):
                urls.append(candidate)
    return tuple(_dedupe_urls(urls))


def _is_uestc_yjsjy_detail_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    return (parsed.hostname or "").casefold() == "yjsjy.uestc.edu.cn" and (
        "/gmis/jcsjgl/dsfc/dsgrjj/" in parsed.path.casefold()
    )


def _extract_secondary_academic_bare_urls(text: str, source_url: str) -> list[str]:
    return [
        candidate
        for match in _BARE_SECONDARY_ACADEMIC_URL_RE.finditer(text or "")
        if (candidate := _normalize_secondary_academic_url(match.group(0), source_url))
    ]


def _normalize_secondary_academic_url(
    value: str | None,
    source_url: str | None = None,
) -> str | None:
    candidate = (value or "").strip()
    if not candidate or candidate.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    candidate = candidate.rstrip("，。,.;；、）)]}>")
    lowered = candidate.casefold()
    if lowered.startswith("www."):
        candidate = f"https://{candidate}"
    elif lowered.startswith(("doi.org/", "dx.doi.org/")):
        candidate = f"https://{candidate}"
    if source_url:
        candidate = urljoin(source_url, candidate)
    if not candidate.startswith(("http://", "https://")):
        return None
    return candidate


def _is_uestc_yjsjy_secondary_academic_url(
    url: str | None,
    *,
    context: str,
    source_url: str,
) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    source = urlparse(source_url)
    hostname = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if not hostname:
        return False
    if hostname == (source.hostname or "").casefold() and path == source.path.casefold():
        return False
    context_lower = _normalize_text(context).casefold()
    has_context_hint = any(
        keyword.casefold() in context_lower
        for keyword in _YJSJY_SECONDARY_ACADEMIC_CONTEXT_KEYWORDS
    )
    if "scholar.google" in hostname or hostname == "dblp.org" or hostname.endswith(".dblp.org"):
        return True
    if hostname in {"doi.org", "dx.doi.org"} and path.startswith("/10."):
        return True
    if hostname in {"faculty.uestc.edu.cn", "staff.uestc.edu.cn"}:
        return True
    if hostname.endswith(".uestc.edu.cn") and hostname != "yjsjy.uestc.edu.cn":
        return True
    return has_context_hint


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        key = url.rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(url.rstrip("/"))
    return deduped


def _looks_like_uestc_yjsjy_homepage_label(value: str | None) -> bool:
    normalized = _normalize_text(value or "").casefold()
    if not normalized:
        return False
    return any(keyword.casefold() in normalized for keyword in _YJSJY_HOMEPAGE_KEYWORDS)


def _extract_url_from_text(value: str | None) -> str | None:
    match = _HTTP_URL_TEXT_RE.search(value or "")
    if not match:
        return None
    return _normalize_extracted_http_url(match.group(0))


def _extract_uestc_yjsjy_narrative_research_directions(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []
    patterns = (
        r"(?:主要)?研究方向(?:为|是|包括|集中于|：|:)\s*(?P<body>[^。；;\n]+)",
        r"(?:主要)?研究领域(?:为|是|包括|集中于|：|:)\s*(?P<body>[^。；;\n]+)",
        r"(?:主要|长期)?从事(?P<body>[^。；;\n]{2,80}?)(?:方向)?研究",
    )
    directions: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            body = _normalize_text(match.group("body"))
            body = re.sub(r"^(?:主要|长期)?从事", "", body).strip()
            body = re.split(
                r"(?:，|,)?(?:曾|并|同时|目前|主持|承担|发表|获得)",
                body,
                maxsplit=1,
            )[0]
            for direction in _split_research_directions(body.replace("和", "、")):
                _append_uestc_yjsjy_research_direction(directions, direction)
    return directions


def _append_uestc_yjsjy_research_direction(
    directions: list[str], direction: str | None
) -> None:
    if not direction:
        return
    for index, existing in enumerate(directions):
        if existing == direction:
            return
        if existing == f"{direction}研究":
            return
        if direction == f"{existing}研究":
            directions[index] = direction
            return
    directions.append(direction)


def _extract_sysu_narrative_research_directions(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []
    candidates: list[str] = []
    patterns = (
        r"(?:主要)?研究方向(?:为|是|包括|集中于|：|:)\s*(?P<body>[^。；;\n]+)",
        r"研究内容包括\s*(?P<body>[^。；;\n]+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            body = _normalize_text(match.group("body"))
            body = re.split(
                r"(?:，|,)?(?:曾|并|同时|目前|长期|主持|承担|发表|获得)",
                body,
                maxsplit=1,
            )[0]
            candidates.extend(_split_research_directions(body.replace("和", "、")))
    return _clean_structured_research_directions(candidates)


_SYSU_RESEARCH_LABEL_PATTERN = (
    r"(?:研究(?:方向|领域|兴趣)|research\s*(?:areas?|interests?|directions?|fields?))"
)
_SYSU_RESEARCH_LABEL_ONLY_RE = re.compile(
    rf"^{_SYSU_RESEARCH_LABEL_PATTERN}\s*[:：]?$",
    flags=re.IGNORECASE,
)
_SYSU_RESEARCH_LABELED_BODY_RE = re.compile(
    rf"{_SYSU_RESEARCH_LABEL_PATTERN}\s*"
    rf"(?:[:：]|\s+(?:include|includes|including)\s*[:：]?|\s+)"
    rf"(?P<body>[^。.\n]+)",
    flags=re.IGNORECASE,
)
_SYSU_RESEARCH_NARRATIVE_BODY_RE = re.compile(
    r"(?:主要|长期)?(?:从事|围绕|致力于)\s*(?P<body>[^。；;\n]+?)"
    r"(?:等)?(?:研究|方向|领域|工作)?(?:。|；|;|$)"
    r"|(?:主要)?研究(?:方向|领域)(?:为|是|包括|集中于|涉及)?\s*[:：]?\s*"
    r"(?P<label_body>[^。；;\n]+)",
    flags=re.IGNORECASE,
)
_SYSU_RESEARCH_INLINE_STOP_RE = re.compile(
    r"\s+(?:"
    r"姓名|职称|职位|邮箱|电子邮箱|Email|E-mail|联系方式|办公地点|个人简介|"
    r"教育经历|教育背景|工作经历|科研项目|研究成果|学术成果|代表性论文|"
    r"论文|专利|招生信息|主讲课程|课程教学"
    r")\s*[:：]",
    flags=re.IGNORECASE,
)
_SYSU_RESEARCH_TOPIC_BLOCKERS = (
    "教授",
    "副教授",
    "讲师",
    "博士",
    "硕士",
    "招生",
    "课程",
    "论文",
    "专利",
    "项目",
    "邮箱",
    "email",
    "etc",
    "科研与人才培养",
    "理论功底",
    "工程实践",
    "组织能力",
)


def _extract_sysu_research_directions_from_samples(
    *,
    text_samples: list[str],
    source_url: str,
) -> list[str]:
    if not _is_sysu_profile_source(source_url):
        return []

    topics: list[str] = []
    for index, sample in enumerate(text_samples):
        normalized = _normalize_text(sample)
        if not normalized:
            continue
        if _SYSU_RESEARCH_LABEL_ONLY_RE.fullmatch(normalized):
            next_value = _next_non_empty_sample(text_samples, index + 1)
            for topic in _derive_sysu_research_topics(next_value or ""):
                _append_unique_sysu_topic(topics, topic)
            continue
        for topic in _derive_sysu_research_topics(normalized):
            _append_unique_sysu_topic(topics, topic)
    return topics


def _is_sysu_profile_source(source_url: str) -> bool:
    hostname = (urlparse(source_url).hostname or "").lower()
    return hostname.endswith("sysu.edu.cn")


def _derive_sysu_research_topics(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []

    bodies: list[str] = []
    for match in _SYSU_RESEARCH_LABELED_BODY_RE.finditer(normalized):
        bodies.append(match.group("body"))
    for match in _SYSU_RESEARCH_NARRATIVE_BODY_RE.finditer(normalized):
        body = match.groupdict().get("body") or match.groupdict().get("label_body")
        if body:
            bodies.append(body)

    topics: list[str] = []
    for body in bodies:
        for topic in _split_sysu_research_topics(body):
            _append_unique_sysu_topic(topics, topic)
    return topics


def _split_sysu_research_topics(body: str) -> list[str]:
    trimmed = _trim_sysu_research_body(body)
    if not trimmed:
        return []
    topics: list[str] = []
    for part in re.split(r"[、,，；;]\s*", trimmed):
        topic = _clean_sysu_research_topic(part)
        if topic:
            topics.append(topic)
    return topics


def _trim_sysu_research_body(body: str) -> str:
    trimmed = _normalize_text(body)
    stop_match = _SYSU_RESEARCH_INLINE_STOP_RE.search(trimmed)
    if stop_match is not None:
        trimmed = trimmed[: stop_match.start()]
    trimmed = re.split(
        r"(?:，|,)?(?:曾|并|同时|目前|长期|主持|承担|发表|获得|入选|申请|授权|"
        r"理论功底|工程实践|具有|作为|Representative\s+Publications?|"
        r"Publications?|教育背景|工作经历)",
        trimmed,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _normalize_text(trimmed)


def _clean_sysu_research_topic(value: str) -> str | None:
    topic = _clean_value(value)
    topic = re.sub(
        rf"^{_SYSU_RESEARCH_LABEL_PATTERN}\s*[:：]?\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(
        r"^(?:include|includes|including)\s*[:：]?\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"^(?:and|or)\s+", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^research\s*fields?\s*[:：]?\s*", "", topic, flags=re.IGNORECASE)
    topic = re.sub(
        r"^(?:主要|长期)?(?:从事|围绕|开展|致力于)\s*",
        "",
        topic,
    )
    topic = re.sub(r"^(?:具体)?(?:包括|涉及)\s*", "", topic)
    topic = re.sub(r"等(?:领域|方面).*$", "", topic)
    topic = re.sub(r"(?:等)?(?:相关)?(?:研究|方向|领域|工作|方面)$", "", topic)
    topic = re.sub(r"\s*等[）)]?$", "", topic)
    topic = re.sub(r"[）)]$", "", topic)
    topic = topic.strip(" .。；;，,、")
    if not topic:
        return None
    if len(topic) > 80:
        return None
    lowered = topic.casefold()
    if any(blocker in lowered or blocker in topic for blocker in _SYSU_RESEARCH_TOPIC_BLOCKERS):
        return None
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", topic):
        return None
    return topic


def _append_unique_sysu_topic(items: list[str], value: str) -> None:
    key = value.casefold()
    if key in {item.casefold() for item in items}:
        return
    items.append(value)


def _extract_sysu_title_from_profile_text(text: str | None, source_url: str) -> str | None:
    if not text or not _is_sysu_profile_source(source_url):
        return None
    normalized = _normalize_text(text)
    if not normalized:
        return None
    lead = re.split(
        r"(?:研究方向|研究领域|Research|Email|E-mail|邮箱|电子邮箱|联系邮箱|个人简介|"
        r"主要从事|长期从事|长期围绕)",
        normalized,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    lead = lead[:240]
    if not lead:
        return None
    return _extract_bounded_academic_title(lead)


def _research_directions_need_sysu_cleanup(values: list[str]) -> bool:
    return any(
        value.startswith(("主要从事", "长期从事", "围绕", "致力于"))
        or value.endswith(("研究", "研究。", "等"))
        for value in values
    )


def _extract_homepage_url(
    text_samples: list[str],
    parser_homepage_links: list[tuple[str, str]],
    source_url: str,
) -> str | None:
    for sample in text_samples:
        url = _extract_labeled_url(sample, _HOMEPAGE_LABELS)
        if url and not _looks_like_generic_institution_homepage_url(url, source_url):
            return url

    for sample in text_samples:
        markdown_url = _extract_markdown_homepage_url(sample)
        if markdown_url:
            candidate = _normalize_extracted_http_url(urljoin(source_url, markdown_url))
            if candidate and not _looks_like_generic_institution_homepage_url(
                candidate, source_url
            ):
                return candidate

    homepage_text = _extract_first_labeled_value(text_samples, _HOMEPAGE_LABELS)
    if homepage_text:
        match = _HTTP_URL_TEXT_RE.search(homepage_text)
        if match:
            candidate = _normalize_extracted_http_url(match.group(0))
            if candidate and not _looks_like_generic_institution_homepage_url(
                candidate, source_url
            ):
                return candidate

    if parser_homepage_links:
        for href, _label in parser_homepage_links:
            candidate = _normalize_extracted_http_url(urljoin(source_url, href))
            if candidate and not _looks_like_generic_institution_homepage_url(
                candidate, source_url
            ):
                return candidate

    if _should_suppress_missing_homepage_fallback(source_url):
        return None
    return source_url


def _should_suppress_missing_homepage_fallback(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if hostname.endswith("sztu.edu.cn"):
        return True
    if hostname.endswith("suat-sz.edu.cn"):
        return True
    if hostname.endswith("suit-sz.edu.cn"):
        return True
    return hostname == "yjsjy.uestc.edu.cn" and "/gmis/jcsjgl/dsfc/dsgrjj/" in path


def _extract_labeled_url(text: str | None, labels: tuple[str, ...]) -> str | None:
    normalized = _normalize_text(text or "")
    if not normalized:
        return None
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:{label_pattern})\s*[：:]\s*({_HTTP_URL_TEXT_RE.pattern})",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return _normalize_extracted_http_url(match.group(1))


def _normalize_extracted_http_url(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    candidate = candidate.rstrip("，。,.;；、")
    candidate = _REPEATED_HTTP_SCHEME_RE.sub("https://", candidate)
    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not hostname:
        return None
    if hostname in {"https", "www.https"} or hostname.endswith(".https"):
        return None
    return candidate


def _extract_markdown_homepage_url(text: str | None) -> str | None:
    for label, href in _MARKDOWN_LINK_RE.findall(text or ""):
        lowered = _normalize_text(label).casefold()
        if any(keyword in lowered for keyword in _HOMEPAGE_TEXT_KEYWORDS):
            return href.strip()
    return None


def _looks_like_generic_institution_homepage_url(candidate: str, source_url: str) -> bool:
    parsed_candidate = urlparse(candidate)
    parsed_source = urlparse(source_url)
    candidate_host = parsed_candidate.netloc.casefold()
    source_host = parsed_source.netloc.casefold()
    candidate_path = parsed_candidate.path.rstrip("/").casefold()
    if not candidate_host or not source_host:
        return False
    if candidate_host == source_host:
        return False
    generic_root_hosts = {
        "www.szu.edu.cn",
        "szu.edu.cn",
        "www.sztu.edu.cn",
        "sztu.edu.cn",
        "www.sysu.edu.cn",
        "sysu.edu.cn",
        "www.suat-sz.edu.cn",
        "suat-sz.edu.cn",
        "www.sustech.edu.cn",
        "sustech.edu.cn",
        "www.cuhk.edu.cn",
        "cuhk.edu.cn",
    }
    if candidate_host in generic_root_hosts and candidate_path in {
        "",
        "/index.htm",
        "/index.html",
    }:
        return True
    return False


def _extract_first_labeled_value(text_samples: list[str], labels: tuple[str, ...]) -> str | None:
    for sample in text_samples:
        if not sample:
            continue
        for label in labels:
            value = _extract_labeled_value(sample, label)
            if value:
                return value
    return None


def _email_text_samples(
    *,
    text_samples: list[str],
    profile_raw_text: str | None,
    source_url: str,
) -> list[str]:
    if _should_scope_contact_text_to_profile_raw(source_url, profile_raw_text):
        return [profile_raw_text or ""]
    return text_samples


def _should_scope_contact_text_to_profile_raw(
    source_url: str,
    profile_raw_text: str | None,
) -> bool:
    if not profile_raw_text:
        return False
    return _should_scope_sysu_contact_text(
        source_url,
        profile_raw_text,
    ) or _is_sztu_suat_fragment_profile_url(source_url)


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
    match = _EMAIL_PATTERN.search(_normalize_email_text(_trim_email_context(text)))
    if not match:
        return None
    return match.group(0)


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    match = _EMAIL_PATTERN.search(_normalize_email_text(_trim_email_context(value)))
    if not match:
        return None
    return match.group(0).lower()


def _trim_email_context(value: str) -> str:
    normalized = _normalize_text(value)
    boundary_match = re.search(
        r"\s+(?:https?:\S*|(?:个人课题组|课题组|主页|个人主页|Homepage|Home Page|Profile|ResearchGate)"
        r"(?:\s*[：:]|$)|(?:English Biography|招生与招聘|Open positions)"
        r"(?:\s*[：:]|\s|$))",
        normalized,
        flags=re.IGNORECASE,
    )
    if boundary_match:
        normalized = normalized[: boundary_match.start()]
    return normalized


def _should_scope_sysu_contact_text(source_url: str, profile_raw_text: str | None) -> bool:
    if not profile_raw_text:
        return False
    hostname = (urlparse(source_url).hostname or "").lower()
    return hostname in {"sic.sysu.edu.cn", "am.sysu.edu.cn"}


_SYSU_LATIN_NAME_TOKEN = r"[^\W\d_\u3400-\u9fff][^\W\d_\u3400-\u9fff.'’.-]*"
_SYSU_LATIN_NAME_RE = re.compile(
    rf"^{_SYSU_LATIN_NAME_TOKEN}(?:\s+{_SYSU_LATIN_NAME_TOKEN}){{1,3}}$",
    flags=re.IGNORECASE,
)
_SYSU_LATIN_NAME_BEFORE_TITLE_RE = re.compile(
    rf"(?P<name>{_SYSU_LATIN_NAME_TOKEN}(?:\s+{_SYSU_LATIN_NAME_TOKEN}){{1,3}})"
    rf"\s+(?:{_ACADEMIC_TITLE_PHRASE}|邮箱|电子邮箱|Email|E-mail|研究领域|Research)",
    flags=re.IGNORECASE,
)


def _extract_sysu_detail_latin_name(
    *,
    html: str,
    source_url: str,
    profile_text: str | None,
) -> str | None:
    if not _is_sysu_detail_profile_url(source_url):
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    if soup.title and soup.title.string:
        candidates.extend(_split_sysu_detail_name_context(soup.title.string))
    for node in soup.select(".breadcrumb, .breadcrumbs, .path, .position"):
        candidates.extend(_split_sysu_detail_name_context(node.get_text(" ", strip=True)))
    if profile_text:
        for match in _SYSU_LATIN_NAME_BEFORE_TITLE_RE.finditer(profile_text):
            candidates.append(match.group("name"))

    for candidate in candidates:
        normalized = _clean_sysu_latin_name_candidate(candidate)
        if normalized:
            return normalized
    return None


def _is_sysu_detail_profile_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("sysu.edu.cn") and (
        "/teacher/" in path or "/members/" in path
    )


def _split_sysu_detail_name_context(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    return [
        part.strip()
        for part in re.split(r"\ue817|›|»|>|/|\||-|_", normalized)
        if part.strip()
    ]


def _clean_sysu_latin_name_candidate(value: str) -> str | None:
    candidate = _ACADEMIC_TITLE_SEARCH_PATTERN.sub(" ", _normalize_text(value))
    candidate = candidate.strip("：:;,，；/|-_>›»")
    candidate = _normalize_text(candidate)
    candidate = re.sub(
        r"\s+(?:his|her|their)$",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    if not _SYSU_LATIN_NAME_RE.fullmatch(candidate):
        return None
    if not _looks_like_person_name(candidate):
        return None
    return candidate


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
    return [
        value.replace(protected_token, "课程思政")
        for value in cleaned
        if not _is_structured_research_blocked(value.replace(protected_token, "课程思政"))
    ]


def _is_structured_research_blocked(value: str) -> bool:
    normalized = _normalize_text(value)
    return any(blocker in normalized for blocker in _STRUCTURED_RESEARCH_BLOCKERS)


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
    contact_boundary_match = _INLINE_CONTACT_BOUNDARY_RE.search(normalized)
    if contact_boundary_match:
        normalized = normalized[: contact_boundary_match.start()]
    return _normalize_text(normalized).strip("：:;,，；/|").strip()


def _normalize_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.replace("\x00", "")
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u3000", " "),
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


def _first_person_name(values: list[str | None]) -> str | None:
    for value in values:
        candidate = _normalize_text(value or "")
        if candidate and _looks_like_person_name(candidate):
            return candidate
    return None


def _extract_name_from_profile_text(text: str | None) -> str | None:
    normalized = _normalize_text(text or "")
    if not normalized:
        return None

    cjk_match = re.match(
        rf"^\s*(?P<name>[\u3400-\u9fff·]{{2,8}})"
        rf"(?:\s*[（(][^）)]{{0,80}}[）)])?"
        rf"\s*[，,、]?\s*(?:{_ACADEMIC_TITLE_PHRASE}|邮箱|电子邮箱|Email|E-mail|教育背景|研究领域|研究方向|个人简介|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if cjk_match:
        candidate = _normalize_text(cjk_match.group("name"))
        if _looks_like_person_name(candidate):
            return candidate

    name_token = r"[^\W\d_\u3400-\u9fff][^\W\d_\u3400-\u9fff.'’.-]*"
    latin_comma_match = re.match(
        rf"^\s*(?P<name>{name_token}(?:\s+{name_token}){{0,2}},\s*{name_token}(?:\s+{name_token}){{0,2}})"
        rf"\s+(?:{_ACADEMIC_TITLE_PHRASE}|邮箱|电子邮箱|Email|E-mail|Research|Biography|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if latin_comma_match:
        candidate = _normalize_text(latin_comma_match.group("name"))
        if _looks_like_person_name(candidate):
            return candidate

    latin_match = re.match(
        rf"^\s*(?P<name>{name_token}(?:\s+{name_token}){{1,3}})"
        rf"\s+(?:{_ACADEMIC_TITLE_PHRASE}|邮箱|电子邮箱|Email|E-mail|Research|Biography|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if latin_match:
        candidate = _normalize_text(latin_match.group("name"))
        if _looks_like_person_name(candidate):
            return candidate
    return None


def _extract_title_near_profile_name(text: str | None, name: str | None) -> str | None:
    normalized = _normalize_text(text or "")
    normalized_name = _normalize_text(name or "")
    if not normalized or not normalized_name:
        return None

    candidate_contexts: list[str] = []
    name_pattern = re.escape(normalized_name)
    for match in re.finditer(
        rf"{name_pattern}"
        rf"(?:\s*[（(][^）)]{{0,120}}[）)])?"
        rf"\s*(?P<context>[^。；;\n]{{0,160}})",
        normalized,
        flags=re.IGNORECASE,
    ):
        context = _normalize_text(match.group("context"))
        if context:
            candidate_contexts.append(context)

    for context in candidate_contexts:
        title = _extract_bounded_academic_title(context)
        if title:
            return title
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
