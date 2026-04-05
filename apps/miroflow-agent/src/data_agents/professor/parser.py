import re

from .models import ProfessorRosterSeed

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
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

        inline_institution, inline_department = _extract_inline_context_from_line(line)
        if inline_institution:
            current_institution = inline_institution
            current_department = inline_department
        elif inline_department is not None:
            current_department = inline_department

        urls = _extract_urls_from_line(line)
        for roster_url in urls:
            seeds.append(
                ProfessorRosterSeed(
                    institution=current_institution,
                    department=current_department,
                    roster_url=roster_url,
                )
            )

    return seeds


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


def _extract_inline_context_from_line(line: str) -> tuple[str | None, str | None]:
    urls = _extract_urls_from_line(line)
    if not urls:
        return None, None

    prefix = _MARKDOWN_LINK_PATTERN.sub("", line)
    for url in urls:
        prefix = prefix.replace(url, "")
    prefix = _INLINE_BULLET_PREFIX_PATTERN.sub("", prefix)
    prefix = _clean_text(prefix).strip("：:,- ")
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


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _looks_like_institution_text(value: str) -> bool:
    return "大学" in value or "研究生院" in value or "学院" in value


def _looks_like_department_text(value: str) -> bool:
    if "研究生院" in value:
        return False
    return any(suffix in value for suffix in _DEPARTMENT_SUFFIXES)


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
