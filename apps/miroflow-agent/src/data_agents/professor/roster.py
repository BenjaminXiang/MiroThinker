from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from .models import DiscoveredProfessorSeed, ExtractedProfessorProfile
from .school_adapters import SchoolRosterAdapter, find_matching_school_adapter

_NON_PERSON_KEYWORDS = {
    "教师",
    "老师",
    "面包屑",
    "Markdown Content",
    "URL Source",
    "Title",
    "师资",
    "简介",
    "详情",
    "列表",
    "目录",
    "首页",
    "更多",
    "实验室",
    "团队",
    "学院",
    "系",
    "department",
    "faculty",
    "development",
    "english",
    "teaching",
    "presentation",
    "presentations",
    "service",
    "发展历程",
    "访问量排序",
    "教辅人员",
    "研究助理",
    "新闻动态",
    "通知公告",
    "联系我们",
    "廉洁之窗",
    "奖学助贷",
    "校友",
    "基本介绍",
    "友情链接",
    "游戏机",
    "标识",
    "招聘",
    "概况",
    "学校",
    "校园",
    "帮助",
    "招生",
    "本科招生",
    "研究生招生",
    "组织机构",
    "现任领导",
    "中心介绍",
    "交流合作",
    "发展沿革",
    "历史沿革",
    "讲座信息",
    "学部概况",
    "学院概况",
    "学术科研",
    "科学研究",
    "科研项目",
    "科研动态",
    "平台基地",
    "学院文化",
    "党建工作",
    "资料下载",
    "财务人事",
    "后勤安全",
    "汉语言文字学",
    "中国古代文学",
    "中国现当代文学",
    "文艺学",
    "外国哲学",
    "中国哲学",
    "中国史",
    "汉语国际教育系",
    "教学名师",
    "师资力量",
    "返回主站",
    "院长致辞",
    "院长专区",
    "院长寄语",
    "院长讲话",
    "院长采访",
    "院长视频",
    "专业设置",
    "本科专业",
    "研究人员",
    "博士生",
    "学生活动",
    "学生风采",
    "创新创意",
    "学院资讯",
    "学院新闻",
    "最新公告",
    "活动预告",
    "国际交流",
    "关于我们",
    "国际顾问",
    "院系介绍",
    "师资概况",
    "教育教学",
    "本科教学",
    "研究生教学",
    "实验课程",
    "导师介绍",
    "行政教辅",
    "学术委员会",
    "科教融汇",
    "产教融合",
    "产业联盟",
    "投资基金",
    "校园风景",
    "文化建设",
    "活动照片",
    "历年毕业照",
    "重要新闻",
    "科研进展",
    "综合新闻",
    "讲座报告",
    "讲座通知",
    "学生工作",
    "学术交流",
    "行政服务",
    "人才培养",
    "荣誉教授",
    "荣休人员",
    "客座教授",
    "机构设置",
    "团学风采",
    "本科生",
    "研究生",
    "考生",
    "访客",
    "why med",
}
_CARD_HINT_CLASS_TOKENS = {
    "teacherlist",
    "faculty_item",
    "item",
    "con",
    "list2",
    "cols_box",
}
_NAME_CLASS_TOKENS = {"t-name", "name"}
_PROFILE_PATH_HINTS = ("teacher", "teachers", "faculty", "faculties", "profile", "people", "info/")
_PROFILE_PATH_BLOCKLIST = (
    "index",
    "list",
    "letter",
    "search",
    "teacher-search",
    "szdw",
    "jsjj",
    "xyjj",
    "xzfw",
    "rcpy",
    "ryjs",
    "szgk",
    "jyxl",
    "yjxl",
    "jfxl",
    "xzxl",
)
_ROSTER_LINK_TEXT_HINTS = ("师资", "教师", "导师", "教授", "faculty", "teacher", "people", "roster")
_ROSTER_LINK_PATH_HINTS = ("szdw", "jsjj", "faculty", "teacher", "teachers", "people")
_SYSU_TEACHER_CATEGORY_LABELS = {
    "教师名录",
    "专任教师",
    "博士后",
    "实验技术人员",
    "专职科研人员",
}
_SYSU_TEACHER_CATEGORY_PATHS = {
    "/teacher",
    "/faculty/post-doctor",
    "/faculty/engineer",
    "/faculty/researcher",
    "/faculty/technician",
}
_SZU_HUB_NAVIGATION_LABELS = {
    "学院概况",
    "研究所/中心",
    "视觉智能研究中心",
    "教学系",
}
_SZU_FILTER_ONLY_LABELS = {
    "职称",
    "教授",
    "副教授",
    "基础物理部",
    "创新部",
}
_SZU_CSSE_TEACHER_CATEGORY_LABELS = {
    "讲席教授",
    "特聘教授",
    "教授",
    "副教授",
    "助理教授",
    "研究员",
    "讲师",
    "副研究员",
    "研究/辅助管理",
    "博士后",
}
_SZU_CPOE_TEACHERFEATURE_NAME_KEYS = {
    "name",
    "teachername",
    "teacher_name",
    "xm",
    "showtitle",
    "title",
}
_SZU_CPOE_TEACHERFEATURE_URL_KEYS = {
    "url",
    "href",
    "link",
    "teacherurl",
    "teacher_url",
    "showurl",
    "show_url",
}
_SZTU_TEACHER_CATEGORY_LABELS = {
    "特聘教授",
    "讲席教授",
    "教授",
    "兼职教授",
    "副教授",
    "助理教授",
    "研究员",
    "博士后",
    "产业导师",
    "专任教师",
    "教学教师",
    "研究教师",
}
_SZTU_SCOPED_TEACHER_CATEGORY_PATHS: dict[str, set[str]] = {
    "ai.sztu.edu.cn": {
        "/szdw/jytd/jxjs.htm",
        "/szdw/jytd/tpjs.htm",
        "/szdw/jytd/js.htm",
        "/szdw/jytd/fjs.htm",
        "/szdw/jytd/zljs.htm",
    },
    "icoc.sztu.edu.cn": {
        "/szdw/jytd/jxjs.htm",
        "/szdw/jytd/tpjs.htm",
        "/szdw/jytd/js.htm",
        "/szdw/jytd/fjs.htm",
        "/szdw/jytd/zljs.htm",
        "/szdw/jytd/yjy.htm",
        "/szdw/jytd/bsh.htm",
    },
}
_SUAT_TEACHER_CATEGORY_LABELS = {
    "讲席教授",
    "杰出教授",
    "教授",
    "副教授",
    "助理教授",
    "青年教师",
    "特聘教授",
    "全职教师",
}
_MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\)"
)
_MARKDOWN_IMAGE_PREFIX_RE = re.compile(r"^(?:!\[[^\]]*\]\([^)]+\)\s*)+")
_INLINE_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_LATIN_ROLE_STOPWORDS = {
    "Architecture",
    "Biological",
    "Biomedical",
    "Chemical",
    "Civil",
    "Computer",
    "Control",
    "Data",
    "Energy",
    "Engineering",
    "Environmental",
    "Information",
    "Logistics",
    "Management",
    "Materials",
    "Mathematics",
    "Mechanical",
    "Medical",
    "Ocean",
    "Physics",
    "Science",
    "Student",
    "Technology",
    "Training",
    "Urban",
    "Water",
}
_DEPARTMENT_LABEL_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFFA-Za-z（）()·]+(?:学院|学部|系|中心|书院|研究院|实验室)")
_TITLE_SUFFIX_RE = re.compile(
    r"(?:校长学勤讲座教授|校长永平讲座教授|校长讲座教授|特聘杰出教授|讲席教授|特聘教授|杰出教授|教研助理教授|教研副教授|教研教授|教学正教授|教学副教授|教学教授|助理教授|副教授|教授|副研究员|研究员|博士生导师|博导)+$"
)
_HEADING_PROFILE_ROLE_HINTS = (
    "教授",
    "副教授",
    "助理教授",
    "讲席教授",
    "特聘教授",
    "研究员",
    "副研究员",
    "工程师",
    "实验师",
    "导师",
    "院长",
    "副院长",
    "个人简介",
)
_HEADING_PROFILE_BLOCK_HINTS = ("友情链接", "联系我们", "copyright")
_HEADING_PROFILE_BLOCK_PATTERNS = (
    re.compile(r"\bback to top\b", re.IGNORECASE),
    re.compile(r"\btop of page\b", re.IGNORECASE),
    re.compile(r"回到顶部"),
)
_SUAT_CARD_PROFILE_HINTS = (
    "院士",
    "教授",
    "研究员",
    "导师",
    "所长",
    "副所长",
    "主任",
    "博士",
)
_SZTU_INLINE_RECORD_PROFILE_CONTEXT_HINTS = (
    '"gw"',
    "'gw'",
    "gw",
    "职称",
    "岗位",
    "职务",
    "职级",
)
_SZTU_ACADEMIC_PROFILE_ROLE_HINTS = (
    "院士",
    "讲席教授",
    "特聘教授",
    "助理教授",
    "副教授",
    "教授",
    "副研究员",
    "研究员",
    "讲师",
    "博士后",
    "产业导师",
    "导师",
)
_SZTU_ADMIN_SUPPORT_ROLE_HINTS = (
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
_SZTU_NON_PERSON_LINK_LABELS = {
    "党的建设",
    "团建工作",
    "就业指导",
    "科研方向",
}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_roster_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    if _should_skip_profile_detail_entry_extraction(source_url):
        return []
    if _is_hit_directory_page(source_url):
        hit_entries = _extract_hit_directory_entries(
            markdown=html,
            institution=institution,
            department=department,
            source_url=source_url,
        )
        if hit_entries:
            return hit_entries
    school_adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    if school_adapter is not None:
        adapter_entries = school_adapter.extract(html, institution, department, source_url)
        if adapter_entries or school_adapter.name in _STRICT_EMPTY_ROSTER_ADAPTERS:
            return adapter_entries
    site_specific_profile_links = _extract_site_specific_markdown_profile_links(
        markdown=html,
        source_url=source_url,
    )
    if site_specific_profile_links or _should_force_site_specific_profile_extraction(source_url):
        candidate_links = site_specific_profile_links
    else:
        candidate_links: list[tuple[str, str]] = []
    if not candidate_links:
        candidate_links = _extract_inline_record_profile_links(html, source_url=source_url)
    if not candidate_links:
        candidate_links = _extract_markdown_heading_profile_links(html, source_url)
    if not candidate_links:
        soup = BeautifulSoup(html, "html.parser")
        candidate_links = _extract_site_specific_html_profile_links(soup, source_url)
        if not candidate_links:
            candidate_links = _extract_heading_profile_links(soup, source_url)
        if not candidate_links:
            candidate_links = _extract_info_profile_links(soup)
        if not candidate_links and _should_skip_direct_entry_extraction(source_url, html):
            return []
        if not candidate_links:
            candidate_links = _extract_card_links(soup)
        if not candidate_links:
            candidate_links = _extract_generic_profile_links(soup)
        if not candidate_links:
            candidate_links = _extract_markdown_profile_links(html)

    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _build_discovered_professor_seeds(
    candidate_links: list[tuple[str, str]],
    *,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    deduped: dict[tuple[str, str, str], DiscoveredProfessorSeed] = {}
    for href, raw_name in candidate_links:
        name = _normalize_person_name(raw_name)
        if not _is_likely_professor_name(name):
            continue
        profile_url = _normalize_profile_url(source_url, href)
        identity_key = (name, institution.strip(), (department or "").strip())
        if identity_key in deduped:
            continue
        deduped[identity_key] = DiscoveredProfessorSeed(
            name=name,
            institution=institution,
            department=department,
            profile_url=profile_url,
            source_url=source_url,
        )
    return list(deduped.values())


def extract_roster_page_links(html: str, source_url: str) -> list[tuple[str, str]]:
    if _should_skip_roster_page_link_extraction(source_url, html):
        return []
    cpoe_pagination_links = _extract_szu_cpoe_teacherfeature_pagination_links(
        html,
        source_url,
    )
    if cpoe_pagination_links:
        return cpoe_pagination_links
    site_specific_markdown_links = _extract_site_specific_markdown_roster_links(
        markdown=html,
        source_url=source_url,
    )
    if site_specific_markdown_links:
        links = site_specific_markdown_links
    else:
        soup = BeautifulSoup(html, "html.parser")
        links = _extract_site_specific_hub_links(soup, source_url)
        if not links:
            links = _extract_generic_roster_links(soup, source_url)
        if not links:
            links = _extract_markdown_roster_links(html)
        if not links:
            links = _extract_inline_redirect_links(html)
    deduped: dict[str, str] = {}
    for href, label in links:
        absolute_url = _normalize_profile_url(source_url, href)
        if absolute_url == source_url:
            continue
        deduped.setdefault(absolute_url, _normalize_link_label(label))
    return [(url, label) for url, label in deduped.items()]


def _extract_card_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        name_node = _find_name_node(anchor)
        if name_node is None:
            continue
        if not _anchor_looks_like_card(anchor):
            continue
        name_text = name_node.get_text(" ", strip=True)
        if not name_text:
            continue
        href = str(anchor.get("href", "")).strip()
        if not _is_navigable_href(href):
            continue
        links.append((href, name_text))
    return links


def _extract_info_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.select('a[href*="info/"]'):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        text = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()
        if not text:
            title_node = _find_nearby_title_node(anchor)
            if title_node is not None:
                text = title_node.get_text(" ", strip=True)
        candidate_name = _extract_candidate_person_name(text)
        if not candidate_name or not _is_likely_professor_name(candidate_name):
            continue
        links.append((href, candidate_name))
    return links


def _extract_generic_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        if _anchor_is_inside_noisy_link_block(anchor):
            continue
        href = str(anchor.get("href", "")).strip()
        text = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()
        if not text:
            continue
        candidate_name = _extract_candidate_person_name(text)
        if not candidate_name or not _is_likely_professor_name(candidate_name):
            continue
        if not _looks_like_profile_href(href):
            if not (
                _looks_like_generic_html_profile_href(href)
            ):
                continue
        links.append((href, text))
    return links


def _anchor_is_inside_noisy_link_block(anchor: Tag) -> bool:
    node: Tag | None = anchor
    while node is not None:
        if node.name in {"nav", "footer", "aside"}:
            return True
        class_tokens = {str(token).lower() for token in node.get("class") or []}
        node_id = str(node.get("id", "")).lower()
        if any("friend" in token for token in class_tokens) or "friend" in node_id:
            return True
        node = node.parent if isinstance(node.parent, Tag) else None
    return False


def _extract_markdown_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for raw_text, href in _iter_markdown_links(markdown):
        name = _extract_candidate_person_name(raw_text)
        if not name or not _is_likely_professor_name(name):
            continue
        if not _looks_like_profile_href(href) and not _looks_like_generic_html_profile_href(href):
            continue
        links.append((href, name))
    return links


def _extract_site_specific_hub_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()

    if hostname.endswith("szu.edu.cn"):
        cpoe_links = _extract_szu_cpoe_teacherfeature_endpoint_links(soup, source_url)
        if cpoe_links:
            return cpoe_links
        csse_links = _extract_szu_csse_teacher_category_links(soup, source_url)
        if csse_links:
            return csse_links
        ceie_links = _extract_szu_ceie_teacher_category_links(soup, source_url)
        if ceie_links:
            return ceie_links
        return _extract_links_from_selectors(soup, ("ul.l18-q h4 a",))
    if hostname.endswith("sztu.edu.cn"):
        return _extract_sztu_teacher_category_links(soup, source_url)
    if hostname.endswith("suat-sz.edu.cn"):
        return _extract_suat_teacher_category_links(soup, source_url)
    if hostname.endswith("suit-sz.edu.cn"):
        return _extract_suit_sziit_pagination_links(soup, source_url)
    if hostname.endswith("pkusz.edu.cn"):
        return _extract_links_from_selectors(soup, ("div.szdw_jsdw .szdw_bd a",))
    if hostname.endswith("sysu.edu.cn"):
        return _extract_sysu_teacher_category_links(soup, source_url)
    return []


def _extract_sysu_teacher_category_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    if not _should_extract_sysu_teacher_category_links(source_url):
        return []
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if not href or label not in _SYSU_TEACHER_CATEGORY_LABELS:
            continue
        path = urlparse(href).path.rstrip("/").lower()
        if path not in _SYSU_TEACHER_CATEGORY_PATHS and "/teachers/" not in path:
            continue
        links.append((href, label))
    return links


def _should_extract_sysu_teacher_category_links(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if not hostname.endswith("sysu.edu.cn"):
        return False
    if re.search(r"/teacher/[^/]+$", path):
        return False
    return any(
        token in path
        for token in ("/teachers", "/teacher", "/faculty", "/members", "/staff", "/szdw", "/szll")
    )


def _extract_szu_ceie_teacher_category_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname != "ceie.szu.edu.cn" or path != "/szdw/ysfc.htm":
        return []
    wanted_labels = {"院士风采", "杰出人才", "教授", "副教授", "讲师/助理教授"}
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        if label not in wanted_labels:
            continue
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        links.append((href, label))
    return links


def _extract_szu_cpoe_teacherfeature_endpoint_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    if not _is_szu_cpoe_roster_shell_url(source_url):
        return []
    links = [
        (href, "teacherfeature")
        for href in _iter_szu_cpoe_teacherfeature_url_candidates(str(soup))
    ]
    return _dedupe_candidate_links(links)


def _iter_szu_cpoe_teacherfeature_url_candidates(text: str):
    pattern = re.compile(
        r"""(?P<url>[^"'()\s]*teacherfeature\.jsp(?:\?[^"'()\s<>]*)?)""",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        candidate = match.group("url").strip()
        if candidate:
            yield candidate
    yield from _iter_szu_cpoe_queryteacher_urls(text)


def _iter_szu_cpoe_queryteacher_urls(text: str):
    pattern = re.compile(
        r"tsites_load_data_options\s*=\s*(?P<options>\{.*?\})\s*;",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(text):
        try:
            options = json.loads(match.group("options"))
        except json.JSONDecodeError:
            continue
        if not isinstance(options, dict):
            continue
        params: dict[str, object] = {}
        for key in (
            "viewUniqueId",
            "viewId",
            "siteOwner",
            "columnId",
            "pageNumber",
            "viewMode",
            "publicType",
        ):
            value = options.get(key)
            if value is not None:
                params[key] = value
        if not {"viewUniqueId", "siteOwner", "columnId"} <= params.keys():
            continue
        page_size = params.get("pageNumber") or 10
        params.setdefault("viewId", params["viewUniqueId"])
        params["pageindex"] = 1
        params["pagesize"] = page_size
        yield (
            "/system/resource/teacherfeature/search/queryteacher.jsp?"
            f"{urlencode(params)}"
        )


def _is_szu_cpoe_roster_shell_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    return hostname == "cpoe.szu.edu.cn" and path.endswith("/szdw.jsp")


def _is_szu_cpoe_teacherfeature_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "cpoe.szu.edu.cn" and (
        "teacherfeature.jsp" in path
        or "/teacherfeature/search/queryteacher.jsp" in path
    )


def _extract_szu_cpoe_teacherfeature_pagination_links(
    html: str,
    source_url: str,
) -> list[tuple[str, str]]:
    if not _is_szu_cpoe_teacherfeature_url(source_url):
        return []
    payload = _parse_szu_cpoe_teacherfeature_payload(html)
    if not isinstance(payload, dict):
        return []
    current_page = _coerce_positive_int(
        payload.get("pageindex")
        or payload.get("pageIndex")
        or payload.get("page")
        or payload.get("currentPage")
    )
    total_pages = _coerce_positive_int(
        payload.get("totalpage")
        or payload.get("totalPage")
        or payload.get("pages")
        or payload.get("pageCount")
    )
    if current_page is None or total_pages is None or current_page >= total_pages:
        return []

    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not params:
        return []
    if "pagesize" not in params and "pageNumber" in params:
        params["pagesize"] = params["pageNumber"]

    links: list[tuple[str, str]] = []
    for page_index in range(current_page + 1, total_pages + 1):
        params["pageindex"] = str(page_index)
        next_url = urlunparse(parsed._replace(query=urlencode(params)))
        links.append((next_url, f"page-{page_index}"))
    return links


def _coerce_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _extract_szu_csse_teacher_category_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    parsed_source = urlparse(source_url)
    source_host = (parsed_source.hostname or "").lower()
    source_path = parsed_source.path.rstrip("/").lower()
    if source_host != "csse.szu.edu.cn" or source_path != "/pages/teacherteam/index":
        return []

    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if label not in _SZU_CSSE_TEACHER_CATEGORY_LABELS:
            continue
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        parsed_href = urlparse(absolute_url)
        if (parsed_href.hostname or "").lower() != source_host:
            continue
        if parsed_href.path.rstrip("/").lower() != "/pages/teacherteam/index":
            continue
        if "zc=" not in parsed_href.query.lower():
            continue
        links.append((href, label))
    return links


def _extract_szu_csse_markdown_teacher_category_links(
    markdown: str,
    source_url: str,
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        normalized_label = _normalize_link_label(label)
        if normalized_label not in _SZU_CSSE_TEACHER_CATEGORY_LABELS:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        if not _is_szu_csse_teacher_team_url(absolute_url):
            continue
        if "zc=" not in urlparse(absolute_url).query.lower():
            continue
        links.append((href, normalized_label))
    return links


def _extract_szu_csse_markdown_profile_links(
    markdown: str,
    source_url: str,
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    lines = markdown.splitlines()
    for line_index, line in enumerate(lines):
        for match in _MARKDOWN_LINK_RE.finditer(line):
            label = match.group(1)
            href = match.group(2)
            if not _looks_like_szu_csse_user_profile_href(source_url, href):
                continue
            name = _extract_szu_csse_reader_profile_name(lines, line_index, label)
            if not name:
                continue
            links.append((href, name))
    return links


def _extract_szu_csse_reader_profile_name(
    lines: list[str],
    link_line_index: int,
    label: str,
) -> str | None:
    name = _extract_szu_csse_neighbor_name(label)
    if name:
        return name

    name = _extract_szu_csse_name_before_first_image_in_block(lines, link_line_index)
    if name:
        return name

    for offset in range(1, 9):
        candidate_index = link_line_index - offset
        if candidate_index < 0:
            break
        name = _extract_szu_csse_neighbor_name(lines[candidate_index])
        if name:
            return name

    return None


def _extract_szu_csse_name_before_first_image_in_block(
    lines: list[str],
    link_line_index: int,
) -> str | None:
    block_start = 0
    for index in range(link_line_index - 1, -1, -1):
        if _MARKDOWN_LINK_RE.search(lines[index]):
            block_start = index + 1
            break

    first_image_index: int | None = None
    for index in range(block_start, link_line_index):
        line = lines[index]
        if line.strip().startswith("!["):
            first_image_index = index
            break
    if first_image_index is None:
        return None

    for index in range(first_image_index - 1, block_start - 1, -1):
        name = _extract_szu_csse_neighbor_name(lines[index])
        if name:
            return name
    return None


def _extract_szu_csse_neighbor_name(value: str) -> str | None:
    normalized = _normalize_link_label(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered in {"homepage", "home page", "personal homepage", "profile"}:
        return None
    if "@" in normalized or normalized.startswith("![") or "image" in lowered:
        return None
    if _INLINE_MARKDOWN_IMAGE_RE.search(normalized):
        return None
    name = _extract_candidate_person_name(normalized)
    if not name or not _is_likely_professor_name(name):
        return None
    if any(
        token in normalized
        for token in (
            "院士",
            "教授",
            "研究员",
            "主任",
            "院长",
            "所长",
            "博士",
            "实验室",
            "研究所",
            "研究中心",
            "学院",
            "学科",
        )
    ) and not (normalized.startswith(name) and normalized != name):
        return None
    return name


def _is_szu_csse_teacher_team_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    return hostname == "csse.szu.edu.cn" and path == "/pages/teacherteam/index"


def _is_szu_csse_school_context(institution: str, department: str | None) -> bool:
    return institution.strip() == "深圳大学" and "计算机与软件学院" in (department or "")


def _looks_like_szu_csse_user_profile_href(source_url: str, href: str) -> bool:
    absolute_url = _normalize_profile_url(source_url, href)
    parsed = urlparse(absolute_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname != "csse.szu.edu.cn" or path != "/pages/user/index":
        return False
    return any(
        key.lower() == "id" and value.isdigit()
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _extract_sztu_teacher_category_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    scoped_paths = _SZTU_SCOPED_TEACHER_CATEGORY_PATHS.get(hostname)
    if scoped_paths is not None:
        if path not in scoped_paths:
            return []
        return _extract_sztu_scoped_teacher_category_links(
            soup=soup,
            source_url=source_url,
            allowed_paths=scoped_paths,
        )
    if not any(token in path for token in ("/szdw/", "/szdw2022/", "/xygk/szdw/")):
        return []
    return _extract_same_host_label_category_links(
        soup=soup,
        source_url=source_url,
        wanted_labels=_SZTU_TEACHER_CATEGORY_LABELS,
    )


def _extract_sztu_scoped_teacher_category_links(
    *,
    soup: BeautifulSoup,
    source_url: str,
    allowed_paths: set[str],
) -> list[tuple[str, str]]:
    current_host = (urlparse(source_url).hostname or "").lower()
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if not href or label not in _SZTU_TEACHER_CATEGORY_LABELS:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        parsed = urlparse(absolute_url)
        if (parsed.hostname or "").lower() != current_host:
            continue
        if parsed.path.rstrip("/").lower() not in allowed_paths:
            continue
        links.append((href, label))
    return links


def _extract_suat_teacher_category_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    path = parsed.path.lower()
    if not any(token in path for token in ("/szll", "/szdw", "/faculty")):
        return []
    category_links = _extract_same_host_label_category_links(
        soup=soup,
        source_url=source_url,
        wanted_labels=_SUAT_TEACHER_CATEGORY_LABELS,
    )
    pagination_links = _extract_suat_roster_pagination_links(soup, source_url)
    return _dedupe_candidate_links([*category_links, *pagination_links])


def _extract_suat_roster_pagination_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed_source = urlparse(source_url)
    source_host = (parsed_source.hostname or "").lower()
    source_path = parsed_source.path.rstrip("/").lower()
    if not source_host.endswith("suat-sz.edu.cn"):
        return []
    if not any(token in source_path for token in ("/szll", "/szdw", "/faculty")):
        return []

    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        if not href or not _is_navigable_href(href):
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        parsed = urlparse(absolute_url)
        if (parsed.hostname or "").lower() != source_host:
            continue
        path = parsed.path.rstrip("/").lower()
        if path == source_path or "info/" in path or _looks_like_profile_href(path):
            continue
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if not _looks_like_suat_roster_pagination_path(source_path, path):
            continue
        if label and not _looks_like_suat_pagination_label(label):
            continue
        links.append((href, label or "pagination"))
    return _dedupe_candidate_links(links)


def _looks_like_suat_roster_pagination_path(source_path: str, candidate_path: str) -> bool:
    source_parts = [part for part in source_path.split("/") if part]
    candidate_parts = [part for part in candidate_path.split("/") if part]
    if not source_parts or not candidate_parts:
        return False

    source_leaf = source_parts[-1]
    source_stem = re.sub(r"\.html?$", "", source_leaf)
    if source_stem.isdigit() and len(source_parts) >= 2:
        expected_prefix = source_parts[:-1]
        return candidate_parts[:-1] == expected_prefix and re.fullmatch(
            r"\d+\.html?", candidate_parts[-1]
        ) is not None

    expected_prefix = [*source_parts[:-1], source_stem]
    if candidate_parts[:-1] == expected_prefix and re.fullmatch(
        r"\d+\.html?", candidate_parts[-1]
    ):
        return True
    if candidate_parts[:-1] != source_parts[:-1]:
        return False
    return re.fullmatch(rf"{re.escape(source_stem)}[-_]?\d+\.html?", candidate_parts[-1]) is not None


def _looks_like_suat_pagination_label(label: str) -> bool:
    normalized = label.strip().lower()
    if not normalized:
        return True
    if normalized.isdigit():
        return True
    return normalized in {">", ">>", "next", "next page", "下一页", "下页", "尾页", "末页"}


def _extract_same_host_label_category_links(
    *,
    soup: BeautifulSoup,
    source_url: str,
    wanted_labels: set[str],
) -> list[tuple[str, str]]:
    current_host = (urlparse(source_url).hostname or "").lower()
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if not href or label not in wanted_labels:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        parsed = urlparse(absolute_url)
        if (parsed.hostname or "").lower() != current_host:
            continue
        if _looks_like_profile_href(parsed.path) or "info/" in parsed.path.lower():
            continue
        links.append((href, label))
    return links


def _extract_suit_sziit_pagination_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed_source = urlparse(source_url)
    source_host = (parsed_source.hostname or "").lower()
    source_path = parsed_source.path.rstrip("/").lower()
    if "/jyjx/jsfc" not in source_path:
        return []
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        label = _normalize_link_label(anchor.get_text(" ", strip=True))
        if not href:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        parsed = urlparse(absolute_url)
        if (parsed.hostname or "").lower() != source_host:
            continue
        path = parsed.path.rstrip("/").lower()
        if re.fullmatch(r".*/jyjx/jsfc/\d+\.htm", path):
            links.append((href, label or "pagination"))
    return links


def _extract_links_from_selectors(
    soup: BeautifulSoup, selectors: tuple[str, ...]
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for selector in selectors:
        for anchor in soup.select(selector):
            href = str(anchor.get("href", "")).strip()
            label = anchor.get_text(" ", strip=True)
            if href and label:
                links.append((href, label))
    return links


def _extract_generic_roster_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    current_host = (urlparse(source_url).hostname or "").lower()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        if _anchor_is_inside_noisy_link_block(anchor):
            continue
        href = str(anchor.get("href", "")).strip()
        label = anchor.get_text(" ", strip=True)
        if not href or not label:
            continue
        absolute_url = _normalize_profile_url(source_url, href)
        if (urlparse(absolute_url).hostname or "").lower() != current_host:
            continue
        if _looks_like_roster_link(href, label):
            links.append((href, label))
    return links


def _extract_markdown_roster_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        if not _is_navigable_href(href):
            continue
        cleaned_label = _normalize_link_label(label)
        lowered_label = cleaned_label.lower()
        lowered_href = href.lower()
        if cleaned_label in _NON_PERSON_KEYWORDS:
            continue
        if any(keyword in lowered_href for keyword in _ROSTER_LINK_PATH_HINTS):
            links.append((href, cleaned_label))
            continue
        if any(keyword in lowered_label for keyword in _ROSTER_LINK_TEXT_HINTS):
            links.append((href, cleaned_label))
            continue
        if any(token in cleaned_label for token in ("学院", "系", "中心", "书院")):
            links.append((href, cleaned_label))
    return links


def _find_name_node(anchor: Tag) -> Tag | None:
    for descendant in anchor.find_all(True):
        class_tokens = set(descendant.get("class") or [])
        if class_tokens & _NAME_CLASS_TOKENS:
            return descendant
    return None


def _anchor_looks_like_card(anchor: Tag) -> bool:
    href = str(anchor.get("href", "")).strip().lower()
    if _looks_like_profile_href(href):
        return True

    node: Tag | None = anchor
    while node is not None:
        class_tokens = set(node.get("class") or [])
        if class_tokens & _CARD_HINT_CLASS_TOKENS:
            return True
        node = node.parent if isinstance(node.parent, Tag) else None
    return False


def _looks_like_roster_link(href: str, text: str) -> bool:
    lowered_text = text.lower()
    lowered_href = href.lower()
    if any(keyword in lowered_text for keyword in _NON_PERSON_KEYWORDS):
        return False
    return any(keyword in lowered_text for keyword in _ROSTER_LINK_TEXT_HINTS) or any(
        keyword in lowered_href for keyword in _ROSTER_LINK_PATH_HINTS
    )


def _looks_like_profile_href(href: str) -> bool:
    lowered = href.lower().strip()
    if not _is_navigable_href(lowered):
        return False
    path = urlparse(lowered).path
    if any(token in path for token in _PROFILE_PATH_BLOCKLIST):
        return False
    if any(token in path for token in _PROFILE_PATH_HINTS):
        return True
    leaf = path.rsplit("/", 1)[-1]
    return leaf in {"main.htm", "main.html"}


def _looks_like_generic_html_profile_href(href: str) -> bool:
    lowered = href.lower().strip()
    if not _is_navigable_href(lowered):
        return False
    path = urlparse(lowered).path
    if any(token in path for token in _PROFILE_PATH_BLOCKLIST):
        return False
    leaf = path.rsplit("/", 1)[-1]
    return leaf.endswith((".htm", ".html")) and len(leaf) > 4


def _should_skip_roster_page_link_extraction(source_url: str, html: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname == "cpoe.szu.edu.cn" and path.endswith("/szdw.jsp"):
        labels = {
            _normalize_link_label(anchor.get_text(" ", strip=True))
            for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True)
        }
        return bool(labels) and labels <= _SZU_FILTER_ONLY_LABELS
    return False


def _normalize_profile_url(source_url: str, href: str) -> str:
    return urljoin(source_url, href.strip())


def _normalize_person_name(value: str) -> str:
    value = value.replace("\ufeff", "").replace("\u200b", "").replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[（(].*?[）)]", "", value)
    value = _TITLE_SUFFIX_RE.sub("", value).strip()
    if re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF]", value):
        value = value.replace(" ", "")
    return value.strip("：:;；,，")


def _extract_candidate_person_name(value: str) -> str:
    text = value.replace("\ufeff", "").replace("\u200b", "").replace("\u3000", " ").strip()
    text = _MARKDOWN_IMAGE_PREFIX_RE.sub("", text)
    text = re.sub(r"[（(].*?[）)]", "", text)
    chinese_match = re.match(r"^\s*([\u3400-\u4DBF\u4E00-\u9FFF·]{2,8})", text)
    if chinese_match:
        return _normalize_person_name(chinese_match.group(1))
    latin_tokens: list[str] = []
    for token in re.split(r"\s+", text):
        if len(latin_tokens) >= 2 and token in _LATIN_ROLE_STOPWORDS:
            break
        if re.fullmatch(r"(?:[A-Z][A-Za-z'.-]*|[A-Z]{2,}|[A-Z]\.)", token):
            latin_tokens.append(token)
            if len(latin_tokens) >= 3:
                break
            continue
        break
    if len(latin_tokens) >= 2:
        return " ".join(latin_tokens)
    return _normalize_person_name(text)


def _normalize_link_label(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.replace("\ufeff", "").replace("\u3000", " "),
    ).strip()


def _is_likely_professor_name(name: str) -> bool:
    if len(name) < 2 or len(name) > 32:
        return False
    if any(char.isdigit() for char in name):
        return False
    lowered = name.lower()
    for keyword in _NON_PERSON_KEYWORDS:
        if keyword.lower() in lowered:
            return False
    if re.fullmatch(r"[\u3400-\u4DBF\u4E00-\u9FFF·]+", name):
        if name.endswith(("大学", "学院", "学部", "研究院", "实验室", "中心", "博士后")):
            return False
        if "·" in name:
            return 2 <= len(name) <= 8
        return len(name) <= 4
    return True


def _is_navigable_href(href: str) -> bool:
    lowered = href.lower().strip()
    return bool(lowered) and not lowered.startswith("javascript:") and not lowered.startswith("#")


def _should_skip_direct_entry_extraction(source_url: str, html: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname == "www.sustech.edu.cn" and path in {"/zh/letter", "/zh/faculty_members.html"}:
        lowered_html = html.lower()
        if any(marker in lowered_html for marker in ('class="list2"', 'class="name"', "/zh/faculties/")):
            return False
        if "markdown content:" in lowered_html and "/zh/faculties/" in lowered_html:
            return False
        return True
    if hostname == "www.szu.edu.cn" and path in {"/szdw/jsjj.htm", "/yxjg/xbxy.htm"}:
        return True
    if hostname.endswith("sztu.edu.cn") and path.endswith("/szdw.htm"):
        lowered_html = html.lower()
        if all(
            marker in lowered_html
            for marker in ("教研序列", "研究序列", "教辅序列", "行政序列")
        ):
            return True
    if hostname == "ise.sysu.edu.cn" and path == "/teachers":
        return True
    if hostname.endswith("szu.edu.cn") and _is_szu_profile_detail_page(source_url):
        return True
    if hostname.endswith("szu.edu.cn") and _is_szu_teacher_page(source_url, html):
        return True
    if hostname == "www.pkusz.edu.cn" and path == "/szdw.htm":
        return True
    if hostname == "www.ece.pku.edu.cn" and path == "/szdw.htm":
        return True
    if (
        hostname == "www.ece.pku.edu.cn"
        and path.startswith("/szdw/all/")
        and not _extract_pkusz_ece_profile_links(BeautifulSoup(html, "html.parser"))
    ):
        return True
    if (
        hostname.endswith("pkusz.edu.cn") or hostname.endswith("pku.edu.cn")
    ) and not _is_pkusz_teacher_page(source_url):
        return True
    return False


def _should_force_site_specific_profile_extraction(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname == "www.sustech.edu.cn" and path in {"/zh/letter", "/zh/faculty_members.html"}:
        return True
    if hostname == "csce.suat-sz.edu.cn" and path == "/szdw.htm":
        return True
    return False


def _extract_site_specific_markdown_roster_links(
    markdown: str,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname == "www.sustech.edu.cn" and path in {"/zh/letter", "/zh/faculty_members.html"}:
        return _extract_sustech_hub_links(markdown)
    if _is_szu_csse_teacher_team_url(source_url):
        return _extract_szu_csse_markdown_teacher_category_links(markdown, source_url)
    if _is_szu_cpoe_roster_shell_url(source_url):
        return [
            (href, "teacherfeature")
            for href in _iter_szu_cpoe_teacherfeature_url_candidates(markdown)
        ]
    if hostname == "www.szu.edu.cn" and path in {"/szdw/jsjj.htm", "/yxjg/xbxy.htm"}:
        return _extract_szu_hub_links(markdown)
    if hostname == "www.pkusz.edu.cn" and path == "/szdw.htm":
        return _extract_pkusz_hub_links(markdown)
    return []


def _extract_site_specific_markdown_profile_links(
    markdown: str,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname == "www.sustech.edu.cn" and path == "/zh/letter":
        return _extract_sustech_profile_links(markdown)
    if _is_szu_csse_teacher_team_url(source_url):
        return _extract_szu_csse_markdown_profile_links(markdown, source_url)
    if hostname.endswith("szu.edu.cn"):
        return _extract_szu_markdown_profile_links(markdown)
    if hostname == "csce.suat-sz.edu.cn" and path == "/szdw.htm":
        return _extract_suat_profile_links(markdown)
    if hostname.endswith("cuhk.edu.cn") and "teacher-search" in path:
        return extract_cuhk_markdown_profile_links(markdown)
    return []


def _extract_site_specific_html_profile_links(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname.endswith("cuhk.edu.cn") and "teacher-search" in path:
        return extract_cuhk_profile_links(soup)
    if hostname.endswith("sysu.edu.cn"):
        return _extract_sysu_drupal_profile_links(soup)
    if hostname.endswith("szu.edu.cn"):
        return _extract_szu_profile_links(soup)
    if hostname == "www.ece.pku.edu.cn" and path.startswith("/szdw"):
        return _extract_pkusz_ece_profile_links(soup)
    if _is_pkusz_teacher_page(source_url):
        return _extract_pkusz_profile_links(soup)
    return []


def _matches_sustech_roster_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    return hostname == "www.sustech.edu.cn" and path in {"/zh/letter", "/zh/faculty_members.html"}


def _matches_szu_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("szu.edu.cn") and not _is_szu_profile_detail_page(source_url) and any(
        token in path for token in ("/szdw", "/jsjj", "/jsml", "/jsfc", "/teacher", "/faculty")
    )


def _matches_szu_csse_teacher_team(source_url: str) -> bool:
    return _is_szu_csse_teacher_team_url(source_url)


def _matches_szu_cpoe_teacherfeature(source_url: str) -> bool:
    return _is_szu_cpoe_teacherfeature_url(source_url)


def _matches_hitsz_college_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return (
        hostname.endswith("hitsz.edu.cn")
        and hostname != "homepage.hit.edu.cn"
        and "/szll" in path
    )


def _matches_suat_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("suat-sz.edu.cn") and any(
        token in path for token in ("/szdw", "/szll", "/teacher", "/faculty")
    )


def _matches_suit_sziit_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("suit-sz.edu.cn") and "/jyjx/jsfc" in path


def _matches_sztu_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("sztu.edu.cn") and any(
        token in path for token in ("/szdw", "/szdw2022", "/xygk/szdw")
    )


def _matches_uestc_yjsjy_mentor_roster(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    return hostname == "yjsjy.uestc.edu.cn" and path == "/gmis/jcsjgl/dsfc"


def _matches_cuhk_teacher_search(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("cuhk.edu.cn") and "teacher-search" in parsed.path.lower()


def _matches_sysu_sic_members(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "sic.sysu.edu.cn" and path.startswith("/members")


def _matches_sysu_am_teacher(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "am.sysu.edu.cn" and (
        path.startswith("/teacher") or path.startswith("/szdw")
    )


def _matches_sysu_sece_faculty(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "sece.sysu.edu.cn" and path.startswith("/szll")


def _matches_sysu_ise_teachers(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "ise.sysu.edu.cn" and (
        path.startswith("/teacher") or path.startswith("/teachers")
    )


def _matches_sysu_scst_teacher(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "scst.sysu.edu.cn" and (
        path.startswith("/teacher") or path.startswith("/faculty")
    )


def _matches_sysu_science_teacher(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "science.sysu.edu.cn" and (
        path.startswith("/teacher") or path.startswith("/faculty")
    )


def _matches_sysu_sofe_teacher(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "sofe.sysu.edu.cn" and (
        path.startswith("/teacher") or path.startswith("/zh-hans/teacher")
    )


def _matches_sysu_faculty_staff_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("sysu.edu.cn") and any(
        token in path
        for token in (
            "/faculty",
            "/members",
            "/staff",
            "/szdw",
            "/szll",
            "/teacher",
            "/teachers",
        )
    )


def _extract_sustech_roster_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    candidate_links = _extract_sustech_profile_links(html)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_szu_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_szu_chemistry_profile_links(soup, source_url)
    if not candidate_links:
        candidate_links = _extract_szu_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_szu_markdown_profile_links(html)
    if not candidate_links:
        candidate_links = _extract_heading_profile_links(soup, source_url)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_szu_csse_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    if not _is_szu_csse_school_context(institution, department):
        return []
    candidate_links = _extract_szu_csse_markdown_profile_links(html, source_url)
    if candidate_links:
        return _build_discovered_professor_seeds(
            candidate_links,
            institution=institution,
            department=department,
            source_url=source_url,
        )

    soup = BeautifulSoup(html, "html.parser")
    candidate_links = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        if not href or not _looks_like_szu_csse_user_profile_href(source_url, href):
            continue
        name = _extract_candidate_person_name(anchor.get_text(" ", strip=True))
        if not name and isinstance(anchor.parent, Tag):
            name = _extract_candidate_person_name(anchor.parent.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        candidate_links.append((href, name))
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_szu_cpoe_teacherfeature_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    candidate_links = _extract_szu_cpoe_teacherfeature_profile_links(
        html,
        source_url=source_url,
    )
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_szu_cpoe_teacherfeature_profile_links(
    html: str,
    *,
    source_url: str | None = None,
) -> list[tuple[str, str]]:
    payload = _parse_szu_cpoe_teacherfeature_payload(html)
    if payload is None:
        return []
    links: list[tuple[str, str]] = []
    for record in _iter_szu_cpoe_teacherfeature_records(payload):
        name = _extract_szu_cpoe_record_name(record)
        href = _extract_szu_cpoe_record_profile_href(record, source_url=source_url)
        if name and href:
            links.append((href, name))
    return _dedupe_candidate_links(links)


def _parse_szu_cpoe_teacherfeature_payload(html: str):
    text = html.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if match is None:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _iter_szu_cpoe_teacherfeature_records(payload):
    if isinstance(payload, dict):
        if _extract_szu_cpoe_record_name(payload) and _extract_szu_cpoe_record_profile_href(payload):
            yield payload
        for value in payload.values():
            yield from _iter_szu_cpoe_teacherfeature_records(value)
        return
    if isinstance(payload, list):
        for value in payload:
            yield from _iter_szu_cpoe_teacherfeature_records(value)


def _extract_szu_cpoe_record_name(record: dict[object, object]) -> str | None:
    for key, value in record.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.replace("-", "_").lower() not in _SZU_CPOE_TEACHERFEATURE_NAME_KEYS:
            continue
        name = _extract_candidate_person_name(value)
        if name and _is_likely_professor_name(name):
            return name
    return None


def _extract_szu_cpoe_record_profile_href(
    record: dict[object, object],
    *,
    source_url: str | None = None,
) -> str | None:
    for key, value in record.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.replace("-", "_").lower() not in _SZU_CPOE_TEACHERFEATURE_URL_KEYS:
            continue
        href = _normalize_szu_cpoe_profile_href(value, source_url=source_url)
        if href:
            return href
    return None


def _normalize_szu_cpoe_profile_href(
    value: str,
    *,
    source_url: str | None = None,
) -> str | None:
    href = value.strip()
    if not href:
        return None
    parsed = urlparse(href)
    path = parsed.path.lower()
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_params = {key.lower(): value for key, value in query_pairs}
    if query_params.get("urltype", "").lower() != "tp.tpteacherdetail":
        return None
    has_teacher_id = bool(query_params.get("teacherid") or query_params.get("id"))
    if not has_teacher_id:
        return None
    source_wbtreeid = _szu_cpoe_wbtreeid_from_source_url(source_url)
    if path.endswith("szxq.jsp"):
        if source_wbtreeid and not query_params.get("wbtreeid"):
            href = _szu_cpoe_detail_url_from_query_pairs(
                query_pairs,
                wbtreeid=source_wbtreeid,
            )
        if href.startswith(("http://", "https://", "/")):
            return href
        return f"/{href}"
    hostname = (parsed.hostname or "").lower()
    if hostname == "cpoe.szu.edu.cn" and path in {"", "/"}:
        return _szu_cpoe_detail_url_from_query_pairs(
            query_pairs,
            wbtreeid=source_wbtreeid,
        )
    return None


def _szu_cpoe_wbtreeid_from_source_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    parsed = urlparse(source_url)
    params = {
        key.lower(): value
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    }
    return params.get("wbtreeid") or params.get("columnid") or None


def _szu_cpoe_detail_url_from_query_pairs(
    query_pairs: list[tuple[str, str]],
    *,
    wbtreeid: str | None,
) -> str:
    normalized_pairs: list[tuple[str, str]] = []
    saw_wbtreeid = False
    for key, value in query_pairs:
        if key.lower() == "wbtreeid":
            saw_wbtreeid = True
            normalized_pairs.append((key, value or wbtreeid or ""))
        else:
            normalized_pairs.append((key, value))
    if not saw_wbtreeid and wbtreeid:
        normalized_pairs.insert(1, ("wbtreeid", wbtreeid))
    return "https://cpoe.szu.edu.cn/szxq.jsp?" + urlencode(normalized_pairs)


def extract_szu_csse_roster_card_profile(
    html: str,
    roster_seed: DiscoveredProfessorSeed,
) -> ExtractedProfessorProfile | None:
    """Build a sparse official profile from a CSSE roster card.

    CSSE detail pages are often hidden behind a tokenized 412 challenge, while
    the official teacher-team page exposes enough card text for a conservative
    fallback. The returned record keeps the profile URL as the canonical detail
    URL and uses the roster page as additional evidence.
    """

    if not _looks_like_szu_csse_user_profile_href(
        roster_seed.source_url,
        roster_seed.profile_url,
    ):
        return None

    normalized_profile_url = _normalize_profile_url(
        roster_seed.source_url,
        roster_seed.profile_url,
    )
    lines = [_normalize_link_label(line) for line in html.splitlines()]
    lines = [line for line in lines if line]
    homepage_index = _find_szu_csse_homepage_line(lines, normalized_profile_url)
    if homepage_index is None:
        return None

    name_index = _find_szu_csse_card_name_line(
        lines,
        homepage_index,
        roster_seed.name,
    )
    if name_index is None:
        return None

    name = _extract_candidate_person_name(lines[name_index])
    if not name or not _is_likely_professor_name(name):
        return None

    raw_card_lines = _szu_csse_card_detail_lines(lines[name_index + 1 : homepage_index])
    email = _find_szu_csse_card_email(lines, homepage_index)
    title = _first_szu_csse_card_title(raw_card_lines) or _szu_csse_title_from_source_url(
        roster_seed.source_url
    )
    research_directions = _szu_csse_card_research_directions(raw_card_lines)

    profile_raw_parts = [
        name,
        *(raw_card_lines if raw_card_lines else []),
        *([f"邮箱：{email}"] if email else []),
        f"官方详情页：{normalized_profile_url}",
        f"官方师资列表：{roster_seed.source_url}",
    ]
    profile_raw_text = "\n".join(profile_raw_parts)

    return ExtractedProfessorProfile(
        name=name,
        institution=roster_seed.institution,
        department=roster_seed.department,
        title=title,
        email=email,
        homepage_url=normalized_profile_url,
        profile_url=normalized_profile_url,
        office=None,
        research_directions=tuple(research_directions),
        source_urls=(normalized_profile_url, roster_seed.source_url),
        profile_raw_text=profile_raw_text,
        academic_positions=tuple(raw_card_lines),
    )


def _find_szu_csse_homepage_line(lines: list[str], profile_url: str) -> int | None:
    for index, line in enumerate(lines):
        if profile_url in line:
            return index
    return None


def _find_szu_csse_card_name_line(
    lines: list[str],
    homepage_index: int,
    roster_name: str,
) -> int | None:
    normalized_roster_name = _extract_candidate_person_name(roster_name)
    search_start = max(0, homepage_index - 12)
    for index in range(homepage_index - 1, search_start - 1, -1):
        candidate = _extract_candidate_person_name(lines[index])
        if not candidate or not _is_likely_professor_name(candidate):
            continue
        if normalized_roster_name and candidate == normalized_roster_name:
            return index
    for index in range(homepage_index - 1, search_start - 1, -1):
        candidate = _extract_candidate_person_name(lines[index])
        if candidate and _is_likely_professor_name(candidate):
            return index
    return None


def _szu_csse_card_detail_lines(lines: list[str]) -> list[str]:
    details: list[str] = []
    for line in lines:
        if not line or _szu_csse_card_line_is_noise(line):
            continue
        if line not in details:
            details.append(line)
    return details


def _szu_csse_card_line_is_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("![") or stripped.startswith("[HOMEPAGE]"):
        return True
    if stripped.startswith("*") or stripped.startswith("#"):
        return True
    if "Image " in stripped and "http" in stripped:
        return True
    if _EMAIL_RE.search(stripped):
        return True
    return False


def _find_szu_csse_card_email(lines: list[str], homepage_index: int) -> str | None:
    stop_index = min(len(lines), homepage_index + 8)
    for line in lines[homepage_index + 1 : stop_index]:
        if "[HOMEPAGE]" in line:
            break
        match = _EMAIL_RE.search(line)
        if match:
            return match.group(0)
    return None


def _first_szu_csse_card_title(lines: list[str]) -> str | None:
    for line in lines:
        if any(
            marker in line
            for marker in (
                "院士",
                "教授",
                "研究员",
                "讲师",
                "博士后",
                "主任",
                "博导",
            )
        ):
            return line
    return None


def _szu_csse_title_from_source_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    if (parsed.hostname or "").lower() != "csse.szu.edu.cn":
        return None
    if parsed.path.rstrip("/").lower() != "/pages/teacherteam/index":
        return None
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return {
        "12": "讲席教授",
        "13": "特聘教授",
        "2": "教授",
        "3": "副教授",
        "5": "助理教授",
        "4": "讲师",
        "10": "副研究员",
        "7": "博士后",
    }.get(params.get("zc", ""))


def _szu_csse_card_research_directions(lines: list[str]) -> list[str]:
    directions: list[str] = []
    for line in lines:
        if _first_szu_csse_card_title([line]) == line:
            continue
        if line.endswith(("研究所", "研究中心", "教学系")):
            continue
        if any(separator in line for separator in ("、", ",", "，", ";", "；")):
            directions.append(line)
    return directions


def _extract_sztu_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_inline_record_profile_links(html, source_url=source_url)
    if not candidate_links:
        candidate_links = _extract_sztu_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_sztu_design_team_cards(soup, source_url)
    if not candidate_links:
        candidate_links = _extract_heading_profile_links(soup, source_url)
    if not candidate_links:
        candidate_links = _extract_markdown_heading_profile_links(html, source_url)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_sztu_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    selectors = (
        "div.content-list div.item > a[href*='/info/']",
        ".list_teacher .list_pic_box .item > a[href*='/info/']",
        ".main_bd .szdw.fr li > a[href*='/info/']",
        ".s_team_main li > a[href*='/info/']",
        ".right.n_shizi a[href*='/info/']",
        ".n_shizi a[href*='/info/']",
    )
    for selector in selectors:
        for anchor in soup.select(selector):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor.get("href", "")).strip()
            label = _extract_sztu_anchor_label(anchor)
            if not _sztu_roster_label_supports_academic_profile(label):
                continue
            name = _extract_candidate_person_name(label)
            if href and name and _is_likely_professor_name(name):
                links.append((href, name))
    return _dedupe_candidate_links(links)


def _sztu_roster_label_supports_academic_profile(label: str) -> bool:
    normalized = _normalize_link_label(label)
    if not normalized:
        return False
    if normalized in _SZTU_NON_PERSON_LINK_LABELS:
        return False
    if not any(marker in normalized for marker in _SZTU_ADMIN_SUPPORT_ROLE_HINTS):
        return True
    return _sztu_roster_text_has_academic_role(normalized)


def _sztu_roster_text_has_academic_role(text: str) -> bool:
    normalized = _normalize_link_label(text)
    return bool(_TITLE_SUFFIX_RE.search(normalized)) or any(
        marker in normalized for marker in _SZTU_ACADEMIC_PROFILE_ROLE_HINTS
    )


def _extract_sztu_anchor_label(anchor: Tag) -> str:
    for selector in ("h3.team-item__name", "h4", ".name", "h3", ".bt", ".title"):
        node = anchor.select_one(selector)
        if isinstance(node, Tag):
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()


def _extract_sztu_design_team_cards(
    soup: BeautifulSoup,
    source_url: str,
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for card in soup.select("div.team-part .team-item"):
        if not isinstance(card, Tag):
            continue
        name_node = card.select_one("h3.team-item__name")
        if not isinstance(name_node, Tag):
            continue
        name = _extract_candidate_person_name(name_node.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        if not _sztu_design_card_supports_profile(card):
            continue
        links.append((f"{source_url}#prof-{quote(name)}", name))
    return _dedupe_candidate_links(links)


def _sztu_design_card_supports_profile(card: Tag) -> bool:
    title_node = card.select_one(".team-item__title")
    title_text = (
        _normalize_link_label(title_node.get_text(" ", strip=True))
        if isinstance(title_node, Tag)
        else ""
    )
    if title_text and _TITLE_SUFFIX_RE.search(title_text):
        return True
    return _context_supports_heading_profile(card.get_text(" ", strip=True))


def _extract_hitsz_college_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    candidate_links = _extract_hitsz_college_profile_links(BeautifulSoup(html, "html.parser"))
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_suat_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_suat_profile_links(html)
    if not candidate_links:
        candidate_links = _extract_inline_record_profile_links(html, source_url=source_url)
    if not candidate_links:
        candidate_links = _extract_suat_html_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_suat_generic_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_heading_profile_links(soup, source_url)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_suit_sziit_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_suit_sziit_profile_links(soup)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_suit_sziit_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    selectors = (
        "ul.teacher-list h3.name a[href]",
        ".teacher-list .name a[href]",
        "a.l-news-tit[href]",
    )
    for selector in selectors:
        for anchor in soup.select(selector):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor.get("href", "")).strip()
            label = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()
            if href and label:
                links.append((href, label))
    if not links:
        for anchor in soup.select('a[href*="/info/"][title]'):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor.get("href", "")).strip()
            label = str(anchor.get("title", "")).strip()
            if href and label:
                links.append((href, label))
    return _dedupe_candidate_links(links)


def _extract_suat_html_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.select("a[href][title]"):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        raw_title = str(anchor.get("title", "")).strip()
        name = _extract_candidate_person_name(raw_title)
        if not href or not name or not _is_likely_professor_name(name):
            continue
        if not _is_navigable_href(href):
            continue
        if not _looks_like_suat_profile_href(href) and not (
            _is_inside_suat_teacher_card(anchor)
            and _looks_like_suat_external_profile_href(href)
        ):
            continue
        links.append((href, name))
    return _dedupe_candidate_links(links)


def _extract_suat_generic_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        if not _looks_like_profile_href(href):
            continue
        text = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()
        name = _extract_candidate_person_name(text)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return _dedupe_candidate_links(links)


def _looks_like_suat_profile_href(href: str) -> bool:
    if not _is_navigable_href(href):
        return False
    path = urlparse(href).path.lower()
    return "info/" in path


def _looks_like_suat_external_profile_href(href: str) -> bool:
    if not _is_navigable_href(href):
        return False
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host.endswith("suat-sz.edu.cn"):
        return False
    return host == "www.siat.ac.cn" or host.endswith(".siat.ac.cn")


def _is_inside_suat_teacher_card(anchor: Tag) -> bool:
    current: Tag | None = anchor
    for _ in range(5):
        if current is None:
            return False
        class_tokens = set(current.get("class") or [])
        if current is anchor and class_tokens & {"con", "flex"}:
            return True
        if current is not anchor and class_tokens & {"item", "list2"}:
            text = current.get_text(" ", strip=True)
            return any(hint in text for hint in _SUAT_CARD_PROFILE_HINTS)
        current = current.parent if isinstance(current.parent, Tag) else None
    return False


def _extract_uestc_yjsjy_mentor_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_uestc_yjsjy_mentor_links(soup)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_uestc_yjsjy_mentor_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.select('a[href*="/gmis/jcsjgl/dsfc/dsgrjj/"]'):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        label = anchor.get_text(" ", strip=True) or str(anchor.get("title", "")).strip()
        label = re.sub(r"^\s*\d+\s*", "", label).strip()
        name = _extract_candidate_person_name(label)
        if href and name:
            links.append((href, name))
    return _dedupe_candidate_links(links)


def _dedupe_candidate_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: dict[tuple[str, str], tuple[str, str]] = {}
    for href, label in links:
        deduped.setdefault((href, label), (href, label))
    return list(deduped.values())


def _extract_cuhk_teacher_search_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    candidate_links = extract_cuhk_markdown_profile_links(html)
    if not candidate_links:
        candidate_links = extract_cuhk_profile_links(BeautifulSoup(html, "html.parser"))
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_sysu_faculty_staff_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_sysu_drupal_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_heading_profile_links(soup, source_url)
    if not candidate_links:
        candidate_links = _extract_markdown_profile_links(html)
    if not candidate_links:
        candidate_links = _extract_markdown_heading_profile_links(html, source_url)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_sysu_sic_member_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_sysu_sic_member_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_sysu_drupal_profile_links(soup)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


def _extract_sysu_am_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_links = _extract_sysu_am_memberblock_profile_links(soup)
    if not candidate_links:
        candidate_links = _extract_sysu_drupal_profile_links(soup)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


_SCHOOL_ROSTER_ADAPTERS: tuple[SchoolRosterAdapter, ...] = (
    SchoolRosterAdapter(
        name="sustech-roster",
        matcher=_matches_sustech_roster_family,
        extractor=_extract_sustech_roster_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="szu-csse-teacher-team",
        matcher=_matches_szu_csse_teacher_team,
        extractor=_extract_szu_csse_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="szu-cpoe-teacherfeature",
        matcher=_matches_szu_cpoe_teacherfeature,
        extractor=_extract_szu_cpoe_teacherfeature_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="szu-teacher-family",
        matcher=_matches_szu_teacher_family,
        extractor=_extract_szu_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="hitsz-college-teacher-family",
        matcher=_matches_hitsz_college_teacher_family,
        extractor=_extract_hitsz_college_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="suat-teacher-family",
        matcher=_matches_suat_teacher_family,
        extractor=_extract_suat_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="suit-sziit-teacher-family",
        matcher=_matches_suit_sziit_teacher_family,
        extractor=_extract_suit_sziit_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sztu-teacher-family",
        matcher=_matches_sztu_teacher_family,
        extractor=_extract_sztu_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="uestc-yjsjy-mentor-roster",
        matcher=_matches_uestc_yjsjy_mentor_roster,
        extractor=_extract_uestc_yjsjy_mentor_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="cuhk-teacher-search",
        matcher=_matches_cuhk_teacher_search,
        extractor=_extract_cuhk_teacher_search_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-sic-members",
        matcher=_matches_sysu_sic_members,
        extractor=_extract_sysu_sic_member_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-am-teacher",
        matcher=_matches_sysu_am_teacher,
        extractor=_extract_sysu_am_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-sece-faculty",
        matcher=_matches_sysu_sece_faculty,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-ise-teachers",
        matcher=_matches_sysu_ise_teachers,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-scst-teacher",
        matcher=_matches_sysu_scst_teacher,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-science-teacher",
        matcher=_matches_sysu_science_teacher,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-sofe-teacher",
        matcher=_matches_sysu_sofe_teacher,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-faculty-staff",
        matcher=_matches_sysu_faculty_staff_family,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
)
_STRICT_EMPTY_ROSTER_ADAPTERS = {
    "suat-teacher-family",
    "szu-csse-teacher-team",
    "szu-cpoe-teacherfeature",
}


def _iter_markdown_links(markdown: str) -> list[tuple[str, str]]:
    sanitized_markdown = _INLINE_MARKDOWN_IMAGE_RE.sub("", markdown)
    return [(label, href.strip()) for label, href in _MARKDOWN_LINK_RE.findall(sanitized_markdown)]


def _extract_sustech_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        if "/zh/faculties/" not in href.lower():
            continue
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_sustech_hub_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    section = _extract_sustech_unit_section(markdown)
    for label, href in _iter_markdown_links(section):
        if not _is_navigable_href(href):
            continue
        absolute_host = (urlparse(href).hostname or "").lower()
        if absolute_host and not absolute_host.endswith("sustech.edu.cn"):
            continue
        cleaned_label = _normalize_link_label(label)
        if cleaned_label in {"院系师资", "院系概况"}:
            continue
        if _DEPARTMENT_LABEL_RE.fullmatch(cleaned_label) is None:
            continue
        links.append((href, cleaned_label))
    return links


def _extract_sustech_unit_section(markdown: str) -> str:
    start = markdown.find("### [院系设置]")
    if start < 0:
        start = markdown.find("## 院系师资")
    if start < 0:
        return markdown
    end_candidates = [
        markdown.find(marker, start + 1)
        for marker in ("### [师资队伍]", "### [教育教学]", "## 公共平台", "## 师资队伍")
    ]
    end_positions = [position for position in end_candidates if position > start]
    end = min(end_positions) if end_positions else len(markdown)
    return markdown[start:end]


def _extract_szu_hub_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        if not _is_navigable_href(href):
            continue
        parsed_href = urlparse(href)
        hostname = (parsed_href.hostname or "").lower()
        if hostname and not hostname.endswith("szu.edu.cn"):
            continue
        cleaned_label = _normalize_link_label(label)
        path = parsed_href.path.lower()
        if hostname and hostname != "www.szu.edu.cn":
            if _looks_like_szu_hub_roster_link(path, cleaned_label):
                links.append((href, cleaned_label))
                continue
    return links


def _looks_like_szu_hub_roster_link(path: str, label: str) -> bool:
    if label in _SZU_HUB_NAVIGATION_LABELS:
        return False
    return any(token in path for token in ("szdw", "js", "teacher", "faculty", "teacherteam"))


def _extract_szu_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or not _looks_like_szu_profile_href(href):
            continue
        parent_classes = set(anchor.parent.get("class") or []) if isinstance(anchor.parent, Tag) else set()
        grandparent = anchor.parent.parent if isinstance(anchor.parent, Tag) and isinstance(anchor.parent.parent, Tag) else None
        grandparent_classes = set(grandparent.get("class") or []) if isinstance(grandparent, Tag) else set()
        if not (
            parent_classes & {"news_title", "news_imgs"}
            or grandparent_classes & {"news_con", "news_box", "list11"}
            or "a" in (anchor.get("class") or [])
            or "list_box_shizi" in grandparent_classes
            or _looks_like_szu_name_href(href)
        ):
            continue
        text = anchor.get_text(" ", strip=True)
        name = _extract_candidate_person_name(text)
        if not name and isinstance(anchor.parent, Tag):
            name = _extract_candidate_person_name(anchor.parent.get_text(" ", strip=True))
        if not name and isinstance(grandparent, Tag):
            name = _extract_candidate_person_name(grandparent.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_szu_chemistry_profile_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if hostname != "chem.szu.edu.cn" or not path.startswith("/szdw/zyjs/"):
        return []
    source_stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if not source_stem:
        return []
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        href_path = urlparse(href).path.lower()
        if not href_path.endswith((".htm", ".html")):
            continue
        if not (
            href_path.startswith(f"{source_stem}/")
            or f"/szdw/zyjs/{source_stem}/" in href_path
        ):
            continue
        text = anchor.get_text(" ", strip=True)
        name = _extract_candidate_person_name(text)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_hitsz_college_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        parsed = urlparse(href)
        hostname = (parsed.hostname or "").lower()
        if hostname not in {"faculty.hitsz.edu.cn", "homepage.hit.edu.cn"}:
            continue
        if hostname == "homepage.hit.edu.cn" and parsed.path.rstrip("/") in {
            "/noFound.html",
            "/noFound",
        }:
            continue
        text = anchor.get_text(" ", strip=True)
        name = _extract_candidate_person_name(text)
        if not name or not _is_likely_professor_name(name):
            continue
        if parsed.scheme == "http":
            href = parsed._replace(scheme="https").geturl()
        links.append((href, name))
    return links


def extract_cuhk_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for title_anchor in soup.select("div.list-title a"):
        href = str(title_anchor.get("href", "")).strip()
        label = title_anchor.get_text(" ", strip=True)
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        if href and _looks_like_cuhk_profile_link(label=label, href=href, name=name):
            links.append((href, name))
    return links


def extract_cuhk_markdown_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        if not _looks_like_cuhk_markdown_profile_link(label=label, href=href, name=name):
            continue
        links.append((href, name))
    return links


def _looks_like_cuhk_markdown_profile_link(*, label: str, href: str, name: str) -> bool:
    return _looks_like_cuhk_profile_link(label=label, href=href, name=name)


def _looks_like_cuhk_profile_link(*, label: str, href: str, name: str) -> bool:
    parsed = urlparse(href)
    hostname = (parsed.hostname or "").lower()
    if hostname and not hostname.endswith("cuhk.edu.cn"):
        return False
    path = parsed.path.lower()
    if "/teacher/" in parsed.path:
        return True
    normalized_label = _normalize_link_label(label)
    if not normalized_label.startswith(name):
        return False
    lowered_label = normalized_label.lower()
    if any(
        token in lowered_label or token in path
        for token in ("lab", "news", "introduction", "homepage")
    ):
        return False
    if hostname == "myweb.cuhk.edu.cn":
        return True
    if not hostname:
        return False
    if hostname in {
        "www.cuhk.edu.cn",
        "cuhk.edu.cn",
        "sai.cuhk.edu.cn",
        "sds.cuhk.edu.cn",
        "sse.cuhk.edu.cn",
        "med.cuhk.edu.cn",
    }:
        return False
    return path in {"", "/"}


def _extract_sysu_drupal_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    selectors = (
        "div.memberblock",
        "div.list-images-1-1",
        "div.list-images-2-1",
        "div.views-row",
        "div.col-sm-12",
    )
    for selector in selectors:
        for card in soup.select(selector):
            teacher_anchor = card.select_one('a[href*="/teacher/"]')
            if not isinstance(teacher_anchor, Tag):
                continue
            href = str(teacher_anchor.get("href", "")).strip()
            if not href:
                continue
            title_node = card.select_one(
                "h4.list-title strong, h4.list-title, h3.list-title strong, h3.list-title, .list-title strong, .list-title"
            )
            if title_node is None:
                title_node = _find_nearby_title_node(teacher_anchor)
            if title_node is None:
                continue
            name = _extract_candidate_person_name(title_node.get_text(" ", strip=True))
            if not name or not _is_likely_professor_name(name):
                continue
            links.append((href, name))
    for card in soup.select("div.teacher"):
        title_node = card.select_one("div.teacherinfo h3, h3")
        profile_anchor = card.select_one(
            'div.teacherpicture a[href], div.teacherinfo a.btn[href], div.teacherinfo a[href$=".htm"]'
        )
        if title_node is None or not isinstance(profile_anchor, Tag):
            continue
        href = str(profile_anchor.get("href", "")).strip()
        if not href:
            continue
        name = _extract_candidate_person_name(title_node.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    for card in soup.select("div.faculty-list-wrap, a.faculty-item"):
        if isinstance(card, Tag) and card.name == "a":
            profile_anchor = card
            title_node = card.select_one("h4")
        else:
            profile_anchor = card.select_one('a.faculty-item[href*="/teacher/"], a[href*="/teacher/"]')
            title_node = card.select_one("h4")
        if title_node is None or not isinstance(profile_anchor, Tag):
            continue
        href = str(profile_anchor.get("href", "")).strip()
        if not href:
            continue
        name = _extract_candidate_person_name(title_node.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(href, name)
    return [(href, name) for href, name in deduped.items()]


def _extract_sysu_sic_member_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for card in soup.select(".member-item, .member-list li, .views-row, .memberblock"):
        if not isinstance(card, Tag):
            continue
        profile_anchor = _find_first_anchor(card, _looks_like_sysu_sic_member_href)
        if profile_anchor is None:
            continue
        name_node = card.select_one(
            ".member-name, .name, h1, h2, h3, h4, .title, .member-title"
        )
        if name_node is None:
            continue
        href = str(profile_anchor.get("href", "")).strip()
        name = _extract_candidate_person_name(name_node.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return _dedupe_links_by_href(links)


def _extract_sysu_am_memberblock_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for card in soup.select("div.memberblock"):
        if not isinstance(card, Tag):
            continue
        profile_anchor = _find_first_anchor(
            card, lambda href: "/teacher/" in urlparse(href.lower()).path
        )
        if profile_anchor is None:
            continue
        name_node = card.select_one(
            ".member-name, .name, h1, h2, h3, h4, .list-title, .member-title"
        )
        if name_node is None:
            name_node = _find_nearby_title_node(profile_anchor)
        if name_node is None:
            continue
        href = str(profile_anchor.get("href", "")).strip()
        name = _extract_candidate_person_name(name_node.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return _dedupe_links_by_href(links)


def _find_first_anchor(card: Tag, predicate: Callable[[str], bool]) -> Tag | None:
    for anchor in card.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        if href and predicate(href):
            return anchor
    return None


def _looks_like_sysu_sic_member_href(href: str) -> bool:
    path = urlparse(href.lower()).path
    if "/members/" not in path:
        return False
    leaf = path.rsplit("/", 1)[-1]
    return leaf.endswith((".htm", ".html")) and not leaf.startswith("index.")


def _dedupe_links_by_href(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(href, name)
    return [(href, name) for href, name in deduped.items()]


def _extract_szu_markdown_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        if not _looks_like_szu_profile_href(href):
            continue
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _looks_like_szu_profile_href(href: str) -> bool:
    lowered = href.lower().strip()
    if not _is_navigable_href(lowered):
        return False
    path = urlparse(lowered).path
    if "info/" in path:
        return True
    if "jsml/" in path and path.count("/") >= 2:
        return True
    if "jsfc/" in path and path.count("/") >= 2:
        return True
    if "content_" in path and "/szdw/" in path:
        return True
    if "/teacher/" in path or "/faculty/" in path:
        return True
    return False


def _looks_like_szu_name_href(href: str) -> bool:
    lowered = href.lower().strip()
    path = urlparse(lowered).path
    return any(
        token in path
        for token in ("jsml/", "jsfc/", "info/", "content_", "/teacher/", "/faculty/")
    )


def _is_szu_teacher_page(source_url: str, html: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname.endswith("szu.edu.cn"):
        return False
    path = parsed.path.lower()
    lowered_html = html.lower()
    if "{{:showname}}" in lowered_html:
        return True
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = _normalize_link_label(title_match.group(1)) if title_match else ""
    teacher_markers = ("师资", "教师", "教授", "在职教师", "专职教师", "教师名录", "教师风采")
    return any(marker in title for marker in teacher_markers) or any(
        token in path for token in ("/szdw", "/jsfc", "/jsml", "/teacher")
    )


def _is_szu_profile_detail_page(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("szu.edu.cn") and (
        "/info/" in path or "content_" in path or "/jsml/" in path
    )


def _extract_pkusz_hub_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    teacher_section = _extract_pkusz_teacher_queue_section(markdown)
    for label, href in _iter_markdown_links(teacher_section):
        if not _is_navigable_href(href):
            continue
        hostname = (urlparse(href).hostname or "").lower()
        if hostname and not (hostname.endswith("pkusz.edu.cn") or hostname.endswith("pku.edu.cn")):
            continue
        cleaned_label = _normalize_link_label(label)
        lowered_href = href.lower()
        if any(token in lowered_href for token in ("szdw", "teacher", "faculty", "resident_faculty")):
            links.append((href, cleaned_label))
            continue
        if any(token in cleaned_label for token in ("学院", "中心", "研究院", "实验室", "系")):
            links.append((href, cleaned_label))
    return links


def _extract_pkusz_ece_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.select('ul.list_box_shizi a[href*="/info/"]'):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        name = _extract_candidate_person_name(anchor.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_pkusz_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in soup.select('a[href*="/info/"]'):
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        name = _extract_candidate_person_name(anchor.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _is_pkusz_teacher_page(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if not (hostname.endswith("pkusz.edu.cn") or hostname.endswith("pku.edu.cn")):
        return False
    if hostname == "www.pkusz.edu.cn" and path == "/szdw.htm":
        return False
    if "/info/" in path:
        return False
    return path.startswith("/szdw") or "faculty" in path


def _extract_pkusz_teacher_queue_section(markdown: str) -> str:
    start = markdown.find("教师队伍")
    if start < 0:
        return markdown
    end = markdown.find("博士后", start)
    if end < 0:
        end = len(markdown)
    return markdown[start:end]


def _extract_suat_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        if "/info/" not in href.lower():
            continue
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_inline_record_profile_links(
    html: str, source_url: str | None = None
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    pattern = re.compile(
        r"(?:[\"']showTitle[\"']|showTitle)\s*:\s*[\"'](?P<title>[^\"']+)[\"']"
        r"(?:(?!(?:[\"']showTitle[\"']|showTitle)).)*?"
        r"(?:[\"'](?:url|aHref)[\"']|(?<![A-Za-z0-9_])(?:url|aHref)(?![A-Za-z0-9_]))\s*:\s*[\"'](?P<url>[^\"']+)[\"']",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(html):
        raw_title = _decode_inline_json_string(match.group("title"))
        raw_url = _decode_inline_json_string(match.group("url"))
        if not raw_title or not raw_url:
            continue
        name = _extract_candidate_person_name(raw_title)
        if not name or not _is_likely_professor_name(name):
            continue
        if not _inline_record_href_is_allowed(
            href=raw_url,
            record_text=match.group(0),
            source_url=source_url,
        ):
            continue
        links.append((raw_url, name))
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(href, name)
    return [(href, name) for href, name in deduped.items()]


def _inline_record_href_is_allowed(
    *,
    href: str,
    record_text: str,
    source_url: str | None,
) -> bool:
    if _looks_like_profile_href(href):
        return True
    if not _looks_like_generic_html_profile_href(href):
        return False
    if not _is_sztu_source_url(source_url):
        return True
    return _sztu_inline_record_has_profile_context(record_text)


def _is_sztu_source_url(source_url: str | None) -> bool:
    if not source_url:
        return False
    return (urlparse(source_url).hostname or "").lower().endswith("sztu.edu.cn")


def _sztu_inline_record_has_profile_context(record_text: str) -> bool:
    return any(hint in record_text for hint in _SZTU_INLINE_RECORD_PROFILE_CONTEXT_HINTS)


def _extract_markdown_heading_profile_links(
    markdown: str, source_url: str
) -> list[tuple[str, str]]:
    if not _should_try_heading_profile_extraction(source_url):
        return []
    lines = markdown.splitlines()
    links: list[tuple[str, str]] = []
    for index, raw_line in enumerate(lines):
        match = re.match(r"^\s*#{3,4}\s+(.+?)\s*$", raw_line)
        if not match:
            continue
        name = _extract_candidate_person_name(match.group(1))
        if not name or not _is_likely_professor_name(name):
            continue
        context = " ".join(lines[index + 1 : index + 5])
        if _context_looks_non_person(context):
            continue
        if not _context_supports_heading_profile(context):
            continue
        links.append((f"{source_url}#prof-{quote(name)}", name))
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(name, href)
    return [(href, name) for name, href in deduped.items()]


def _extract_heading_profile_links(
    soup: BeautifulSoup, source_url: str
) -> list[tuple[str, str]]:
    if not _should_try_heading_profile_extraction(source_url):
        return []
    links: list[tuple[str, str]] = []
    for heading in soup.find_all(["h3", "h4", "h5"]):
        if not isinstance(heading, Tag):
            continue
        name = _extract_candidate_person_name(heading.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        context = _collect_heading_context(heading)
        if _context_looks_non_person(context):
            continue
        if not _context_supports_heading_profile(context):
            continue
        href = _find_heading_profile_href(heading) or f"{source_url}#prof-{quote(name)}"
        links.append((href, name))
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(name, href)
    return [(href, name) for name, href in deduped.items()]


def _extract_inline_redirect_links(html: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    patterns = (
        r'window\.location\.replace\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'location\.replace\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'window\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'location\.href\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\']+)["\']',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.IGNORECASE):
            href = match.group(1).strip()
            if not _is_navigable_href(href):
                continue
            links.append((href, "redirect"))
    return links


def _decode_inline_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\/", "/")


def _find_nearby_title_node(anchor: Tag) -> Tag | None:
    current: Tag | None = anchor
    for _ in range(5):
        if current is None:
            break
        title_node = current.select_one(
            "h4.list-title strong, h4.list-title, h3.list-title strong, h3.list-title, p.bt, .bt, .name, .title"
        )
        if isinstance(title_node, Tag):
            return title_node
        current = current.parent if isinstance(current.parent, Tag) else None
    return None


def _should_try_heading_profile_extraction(source_url: str) -> bool:
    hostname = (urlparse(source_url).hostname or "").lower()
    return hostname.endswith("sztu.edu.cn") or hostname.endswith("sysu.edu.cn")


def _should_skip_profile_detail_entry_extraction(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    return (
        (hostname.endswith("sztu.edu.cn") or hostname.endswith("suat-sz.edu.cn"))
        and "/info/" in parsed.path.lower()
    )


def _collect_heading_context(heading: Tag) -> str:
    parts: list[str] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag):
            if sibling.name in {"h2", "h3", "h4", "h5"}:
                break
            text = sibling.get_text(" ", strip=True)
        else:
            text = str(sibling).strip()
        if text:
            parts.append(text)
        if len(parts) >= 4 or sum(len(part) for part in parts) >= 400:
            break
    if not parts and isinstance(heading.parent, Tag):
        parent_text = heading.parent.get_text(" ", strip=True)
        heading_text = heading.get_text(" ", strip=True)
        if parent_text and parent_text != heading_text:
            parts.append(parent_text.removeprefix(heading_text).strip())
    return " ".join(parts)


def _find_heading_profile_href(heading: Tag) -> str | None:
    candidate_anchors: list[Tag] = []
    current: Tag | None = heading
    for _ in range(4):
        if current is None:
            break
        if current.name == "a" and current.get("href"):
            candidate_anchors.append(current)
            break
        current = current.parent if isinstance(current.parent, Tag) else None
    if isinstance(heading.parent, Tag):
        candidate_anchors.extend(heading.parent.find_all("a", href=True))
    for sibling in list(heading.previous_siblings)[:2] + list(heading.next_siblings)[:2]:
        if isinstance(sibling, Tag):
            candidate_anchors.extend(sibling.find_all("a", href=True))
            if sibling.name == "a" and sibling.get("href"):
                candidate_anchors.append(sibling)
    for anchor in candidate_anchors:
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        if _looks_like_profile_href(href) or _looks_like_generic_html_profile_href(href):
            return href
    return None


def _context_supports_heading_profile(context: str) -> bool:
    if not context:
        return False
    if _EMAIL_RE.search(context):
        return True
    return any(marker in context for marker in _HEADING_PROFILE_ROLE_HINTS)


def _context_looks_non_person(context: str) -> bool:
    lowered = context.lower()
    if any(marker in lowered for marker in _HEADING_PROFILE_BLOCK_HINTS):
        return True
    return any(pattern.search(lowered) for pattern in _HEADING_PROFILE_BLOCK_PATTERNS)


def _is_hit_directory_page(source_url: str) -> bool:
    parsed = urlparse(source_url)
    return (parsed.hostname or "").lower() == "homepage.hit.edu.cn" and parsed.path == "/school-dept"


def _extract_hit_directory_entries(
    *,
    markdown: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    entries: dict[tuple[str, str, str], DiscoveredProfessorSeed] = {}
    for raw_text, href in _iter_markdown_links(markdown):
        if "###" not in raw_text:
            continue
        label = raw_text.split("###", 1)[1].strip()
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        label_remainder = label.removeprefix(name).strip()
        dept_match = _DEPARTMENT_LABEL_RE.search(label_remainder)
        inferred_department = dept_match.group(0) if dept_match else department
        profile_href = href.strip()
        if profile_href == source_url:
            profile_href = f"{source_url}#prof-{quote(name)}"
        identity_key = (name, institution.strip(), (inferred_department or "").strip())
        entries.setdefault(
            identity_key,
            DiscoveredProfessorSeed(
                name=name,
                institution=institution,
                department=inferred_department,
                profile_url=profile_href,
                source_url=source_url,
            ),
        )
    return list(entries.values())
