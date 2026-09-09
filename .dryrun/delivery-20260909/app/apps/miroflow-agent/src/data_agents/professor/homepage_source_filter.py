from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

_EXTERNAL_ACADEMIC_PROFILE_URL_HINTS = (
    "researchgate.net",
    "scholar.google.",
    "scholar.google/",
    "google scholar",
    "orcid.org",
    "dblp.org",
    "inspirehep.net",
    "semanticscholar.org",
    "scopus.com",
    "webofscience.com",
)
_INSTITUTION_ROOT_HOSTS = {
    "cuhk.edu.cn",
    "hit.edu.cn",
    "sigs.tsinghua.edu.cn",
    "suat-sz.edu.cn",
    "sustech.edu.cn",
    "sysu.edu.cn",
    "sziit.edu.cn",
    "szu.edu.cn",
    "sztu.edu.cn",
    "tsinghua.edu.cn",
    "uestc.edu.cn",
}
_NON_PUBLICATION_URL_PATH_HINTS = (
    "联系邮箱",
    "联系我们",
    "联系",
    "邮箱",
    "email",
    "e-mail",
    "contact",
    "contacts",
    "contact-us",
    "contact_us",
)
_SUSTECH_FACULTY_HOST = "faculty.sustech.edu.cn"
_SUSTECH_FACULTY_NOISE_PATHS = {
    "cn",
    "en",
    "faculty",
    "faculties",
    "list",
    "lists",
    "people",
    "search",
    "team",
    "teams",
    "teacher",
    "teachers",
    "zh",
}


def is_homepage_publication_ingest_url(value: object) -> bool:
    """Return whether a professor-owned source page is worth homepage-paper ingest.

    Google Scholar, ResearchGate, ORCID, DBLP, and similar academic profile pages
    are metadata/profile sources. They are not stable publication homepages and
    should not be fetched by the official-page publication parser.
    """
    if not isinstance(value, str):
        return False
    url = value.strip()
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").casefold()
    if not hostname:
        return False
    if hostname in {"https", "www.https"} or hostname.endswith(".https"):
        return False
    if hostname == _SUSTECH_FACULTY_HOST and not _is_sustech_faculty_professor_page(
        parsed.path,
        parsed.query,
    ):
        return False
    if _is_roster_fragment_profile(parsed.fragment):
        return False
    if _is_institution_root_homepage(hostname, parsed.path, parsed.query):
        return False
    lowered_url = url.casefold()
    decoded_path = unquote(parsed.path or "").casefold()
    if any(hint.casefold() in decoded_path for hint in _NON_PUBLICATION_URL_PATH_HINTS):
        return False
    return not any(
        hint in lowered_url or hint in hostname
        for hint in _EXTERNAL_ACADEMIC_PROFILE_URL_HINTS
    )


def _is_roster_fragment_profile(fragment: str) -> bool:
    return unquote(fragment or "").casefold().startswith("prof-")


def _is_sustech_faculty_professor_page(path: str, query: str) -> bool:
    normalized_path = unquote(path or "").strip("/")
    if not normalized_path:
        return _is_sustech_faculty_tag_page(query)
    if query:
        return False
    path_parts = [part for part in normalized_path.split("/") if part]
    if len(path_parts) != 1:
        return False
    slug = path_parts[0].casefold()
    if slug in _SUSTECH_FACULTY_NOISE_PATHS:
        return False
    return any(char.isalnum() for char in slug)


def _is_sustech_faculty_tag_page(query: str) -> bool:
    params = parse_qs(query, keep_blank_values=False)
    if set(params) != {"tagid", "iscss", "snapid"}:
        return False
    return (
        len(params["tagid"]) == 1
        and bool(params["tagid"][0].strip())
        and params["iscss"] == ["1"]
        and params["snapid"] == ["1"]
    )


def _is_institution_root_homepage(hostname: str, path: str, query: str) -> bool:
    if query:
        return False
    normalized_path = (path or "").strip()
    if normalized_path not in {"", "/"}:
        return False
    bare_hostname = hostname.removeprefix("www.")
    return bare_hostname in _INSTITUTION_ROOT_HOSTS
