from __future__ import annotations

from urllib.parse import unquote, urlparse

_EXTERNAL_ACADEMIC_PROFILE_URL_HINTS = (
    "researchgate.net",
    "scholar.google.",
    "scholar.google/",
    "google scholar",
    "orcid.org",
    "dblp.org",
    "semanticscholar.org",
    "scopus.com",
    "webofscience.com",
)
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
    lowered_url = url.casefold()
    decoded_path = unquote(parsed.path or "").casefold()
    if any(hint.casefold() in decoded_path for hint in _NON_PUBLICATION_URL_PATH_HINTS):
        return False
    return not any(
        hint in lowered_url or hint in hostname
        for hint in _EXTERNAL_ACADEMIC_PROFILE_URL_HINTS
    )
