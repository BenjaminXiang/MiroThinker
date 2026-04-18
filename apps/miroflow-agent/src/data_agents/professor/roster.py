from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import DiscoveredProfessorSeed
from .school_adapters import SchoolRosterAdapter, find_matching_school_adapter

_NON_PERSON_KEYWORDS = {
    "教师",
    "老师",
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
    "新闻动态",
    "通知公告",
    "联系我们",
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
    "讲座信息",
    "学部概况",
    "学院概况",
    "学术科研",
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
    "活动照片",
    "历年毕业照",
    "重要新闻",
    "科研进展",
    "综合新闻",
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
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_roster_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
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
        if adapter_entries:
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
        candidate_links = _extract_inline_record_profile_links(html)
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
        if not href:
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
        return _extract_links_from_selectors(soup, ("ul.l18-q h4 a",))
    if hostname.endswith("pkusz.edu.cn"):
        return _extract_links_from_selectors(soup, ("div.szdw_jsdw .szdw_bd a",))
    if hostname == "ise.sysu.edu.cn" and parsed.path.rstrip("/").lower() == "/teachers":
        return _extract_links_from_selectors(
            soup,
            (
                'a[href="/teacher"]',
                'a[href*="/Faculty/"]',
            ),
        )
    return []


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
    text = value.replace("\u3000", " ").strip()
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
        if keyword in lowered:
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


def _matches_suat_teacher_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("suat-sz.edu.cn") and any(
        token in path for token in ("/szdw", "/szll", "/teacher", "/faculty")
    )


def _matches_cuhk_teacher_search(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("cuhk.edu.cn") and "teacher-search" in parsed.path.lower()


def _matches_sysu_faculty_staff_family(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname.endswith("sysu.edu.cn") and any(
        token in path for token in ("/faculty", "/staff", "/teacher", "/teachers")
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


def _extract_suat_teacher_adapter_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[DiscoveredProfessorSeed]:
    candidate_links = _extract_suat_profile_links(html)
    if not candidate_links:
        soup = BeautifulSoup(html, "html.parser")
        candidate_links = _extract_heading_profile_links(soup, source_url)
    return _build_discovered_professor_seeds(
        candidate_links,
        institution=institution,
        department=department,
        source_url=source_url,
    )


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


_SCHOOL_ROSTER_ADAPTERS: tuple[SchoolRosterAdapter, ...] = (
    SchoolRosterAdapter(
        name="sustech-roster",
        matcher=_matches_sustech_roster_family,
        extractor=_extract_sustech_roster_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="szu-teacher-family",
        matcher=_matches_szu_teacher_family,
        extractor=_extract_szu_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="suat-teacher-family",
        matcher=_matches_suat_teacher_family,
        extractor=_extract_suat_teacher_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="cuhk-teacher-search",
        matcher=_matches_cuhk_teacher_search,
        extractor=_extract_cuhk_teacher_search_adapter_entries,
    ),
    SchoolRosterAdapter(
        name="sysu-faculty-staff",
        matcher=_matches_sysu_faculty_staff_family,
        extractor=_extract_sysu_faculty_staff_adapter_entries,
    ),
)


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
            if any(token in cleaned_label for token in ("学院", "学部", "中心")):
                links.append((href, cleaned_label))
                continue
            if any(token in path for token in ("szdw", "js", "teacher", "faculty")):
                links.append((href, cleaned_label))
                continue
    return links


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


def extract_cuhk_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for title_anchor in soup.select("div.list-title a"):
        href = str(title_anchor.get("href", "")).strip()
        name = _extract_candidate_person_name(title_anchor.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        if href:
            links.append((href, name))
    return links


def extract_cuhk_markdown_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        parsed = urlparse(href)
        hostname = (parsed.hostname or "").lower()
        if not hostname.endswith("cuhk.edu.cn"):
            continue
        if "/teacher/" not in parsed.path:
            continue
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links


def _extract_sysu_drupal_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    selectors = (
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


def _extract_inline_record_profile_links(html: str) -> list[tuple[str, str]]:
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
        if not _looks_like_profile_href(raw_url) and not _looks_like_generic_html_profile_href(raw_url):
            continue
        links.append((raw_url, name))
    deduped: dict[str, str] = {}
    for href, name in links:
        deduped.setdefault(href, name)
    return [(href, name) for href, name in deduped.items()]


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
