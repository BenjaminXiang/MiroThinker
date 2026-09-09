import re
from urllib.parse import urlparse

from .models import ProfessorRosterSeed

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
_MARKDOWN_LINK_CAPTURE_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL_PATTERN = re.compile(r"https?://[^\s)>\]]+")
_INLINE_BULLET_PREFIX_PATTERN = re.compile(r"^[-*+\d.、\s]+")
_INLINE_LABEL_KEYWORDS = {
    "faculty",
    "teacher",
    "teachers",
    "roster",
    "directory",
    "备用地址",
    "教师目录",
    "教授目录",
}
_DEPARTMENT_SUFFIXES = ("学院", "系", "中心", "研究所", "实验室", "学部", "书院")
_PERSON_TITLE_SUFFIXES = re.compile(
    r"(?:院士|教授|副教授|助理教授|讲席教授|特聘教授|研究员|副研究员|博士生导师|博导|导师|讲师)+$"
)
_HOST_INSTITUTION_HINTS = {
    "sigs.tsinghua.edu.cn": "清华大学深圳国际研究生院",
    "pkusz.edu.cn": "北京大学深圳研究生院",
    "sustech.edu.cn": "南方科技大学",
    "szu.edu.cn": "深圳大学",
    "suat-sz.edu.cn": "深圳理工大学",
    "sztu.edu.cn": "深圳技术大学",
    "hit.edu.cn": "哈尔滨工业大学（深圳）",
    "cuhk.edu.cn": "香港中文大学（深圳）",
    "sysu.edu.cn": "中山大学（深圳）",
}


def parse_roster_seed_markdown(markdown_text: str) -> list[ProfessorRosterSeed]:
    seeds: list[ProfessorRosterSeed] = []
    current_institution: str | None = None
    current_department: str | None = None
    in_code_block = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not line:
            continue

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = _clean_text(heading_match.group(2))
            if level <= 2:
                current_institution = heading_text
                current_department = None
            else:
                current_department = heading_text
            continue

        line_institution, line_department = _extract_context_from_pipe_row(line)
        if line_institution:
            current_institution = line_institution
            current_department = line_department
        elif line_department is not None:
            current_department = line_department

        urls = _extract_urls_from_line(line)
        inline_prefix = _extract_inline_prefix(line)
        direct_profile_context = None
        if urls and inline_prefix:
            for roster_url in urls:
                if _looks_like_inline_direct_profile_seed_url(roster_url):
                    direct_profile_context = _extract_direct_profile_context_and_label_from_prefix(inline_prefix)
                    if direct_profile_context is not None:
                        break

        if direct_profile_context is not None:
            inline_institution, inline_department, inline_label = direct_profile_context
        else:
            inline_institution, inline_department = _extract_inline_context_from_prefix(inline_prefix)
            inline_label = _extract_inline_label_from_line(line)

        if inline_institution:
            current_institution = inline_institution
            current_department = inline_department
        elif inline_department is not None:
            current_department = inline_department

        for roster_url in urls:
            institution = current_institution or _infer_institution_from_url(roster_url)
            seeds.append(
                ProfessorRosterSeed(
                    institution=institution,
                    department=current_department,
                    roster_url=roster_url,
                    label=inline_label,
                )
            )

    return seeds


def _infer_institution_from_url(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return None
    for suffix, institution in _HOST_INSTITUTION_HINTS.items():
        if suffix in hostname:
            return institution
    return None


def _extract_urls_from_line(line: str) -> list[str]:
    urls: list[str] = []
    for url in _MARKDOWN_LINK_PATTERN.findall(line):
        urls.append(_normalize_url(url))

    line_without_links = _MARKDOWN_LINK_PATTERN.sub("", line)
    for match in _URL_PATTERN.findall(line_without_links):
        urls.append(_normalize_url(match))
    return urls


def _extract_context_from_pipe_row(line: str) -> tuple[str | None, str | None]:
    if "|" not in line:
        return None, None

    cells = [_clean_text(cell) for cell in line.strip("|").split("|")]
    if len(cells) < 2:
        return None, None

    institution = None if _looks_like_url(cells[0]) else cells[0] or None
    department = None if _looks_like_url(cells[1]) else cells[1] or None
    return institution, department


def _extract_inline_prefix(line: str) -> str:
    urls = _extract_urls_from_line(line)
    if not urls:
        return ""

    prefix = _MARKDOWN_LINK_PATTERN.sub("", line)
    for url in urls:
        prefix = prefix.replace(url, "")
    prefix = _INLINE_BULLET_PREFIX_PATTERN.sub("", prefix)
    return _clean_text(prefix).strip("：:,- ")


def _extract_inline_context_from_line(line: str) -> tuple[str | None, str | None]:
    return _extract_inline_context_from_prefix(_extract_inline_prefix(line))


def _extract_inline_context_from_prefix(prefix: str) -> tuple[str | None, str | None]:
    if not prefix:
        return None, None

    lowered = prefix.lower()
    if lowered in _INLINE_LABEL_KEYWORDS:
        return None, None

    parts = prefix.split()
    if len(parts) >= 2 and _looks_like_institution_text(parts[0]):
        department_candidate = " ".join(parts[1:])
        if _looks_like_department_text(department_candidate):
            return parts[0], department_candidate

    compact_institution, compact_department = _split_compact_inline_context(prefix)
    if compact_institution:
        return compact_institution, compact_department

    if _looks_like_institution_text(prefix):
        return prefix, None
    return None, None


def _looks_like_inline_direct_profile_seed_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    if not path:
        return False
    if any(
        token in path
        for token in (
            "list",
            "index",
            "search",
            "letter",
            "directory",
            "roster",
            "faculty_members",
            "jsjj",
            "szdw",
            "szll",
            "jsml",
            "jxjs",
            "qbjs",
            "news",
            "notice",
            "notices",
            "event",
            "events",
            "article",
            "articles",
        )
    ):
        return False
    if any(token in path for token in ("teacher/", "teachers/", "faculty/", "faculties/", "profile/", "people/")):
        return True
    leaf = path.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0]
    return stem in {"main", "home", "homepage", "profile"} and path.count("/") >= 2


def _extract_direct_profile_context_and_label_from_prefix(prefix: str) -> tuple[str | None, str | None, str] | None:
    if not prefix:
        return None
    parts = prefix.split()
    if len(parts) < 2:
        return None

    max_suffix = min(4, len(parts) - 1)
    for suffix_len in range(1, max_suffix + 1):
        label_candidate = _normalize_inline_person_label(" ".join(parts[-suffix_len:]))
        if not label_candidate:
            continue
        context_prefix = " ".join(parts[:-suffix_len]).strip()
        if not context_prefix:
            continue
        institution, department = _extract_inline_context_from_prefix(context_prefix)
        if institution:
            return institution, department, label_candidate
    return None


def _extract_inline_label_from_line(line: str) -> str | None:
    for raw_label, _ in _MARKDOWN_LINK_CAPTURE_PATTERN.findall(line):
        label = _normalize_inline_person_label(raw_label)
        if label:
            return label

    prefix = _extract_inline_prefix(line)
    if not prefix:
        return None
    return _normalize_inline_person_label(prefix)


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _looks_like_institution_text(value: str) -> bool:
    return "大学" in value or "研究生院" in value or "学院" in value


def _looks_like_department_text(value: str) -> bool:
    if "研究生院" in value:
        return False
    return any(suffix in value for suffix in _DEPARTMENT_SUFFIXES)


def _normalize_inline_person_label(value: str) -> str | None:
    normalized = _clean_text(value)
    normalized = re.sub(r"[（(].*?[）)]", "", normalized)
    normalized = normalized.replace("\u3000", " ").strip("：:;；,，")
    if not normalized:
        return None
    if _looks_like_institution_text(normalized) or _looks_like_department_text(normalized):
        return None
    if any(keyword in normalized.lower() for keyword in _INLINE_LABEL_KEYWORDS):
        return None

    candidate = _PERSON_TITLE_SUFFIXES.sub("", normalized).strip()
    if not candidate:
        return None

    if re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF]", candidate):
        candidate = candidate.replace(" ", "")
        if len(candidate) < 2 or len(candidate) > 32:
            return None
        if candidate.endswith(("大学", "学院", "学部", "研究院", "实验室", "中心", "博士后")):
            return None
        return candidate

    tokens = candidate.split()
    if len(tokens) < 2:
        return None
    if all(
        re.fullmatch(r"(?:[A-Z][A-Za-z'.-]*|[A-Z]{2,}|[A-Z]\.)", token)
        for token in tokens
    ):
        return candidate
    return None


def _split_compact_inline_context(value: str) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    if "研究生院" in value:
        return value, None
    match = re.match(r"^(.+?大学(?:（[^）]+）)?)(.+)$", value)
    if not match:
        return None, None
    institution = match.group(1).strip()
    department = match.group(2).strip()
    if not _looks_like_department_text(department):
        return None, None
    return institution, department


def _normalize_url(url: str) -> str:
    return url.rstrip(".,;:)")


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", value)
    return value.strip()
