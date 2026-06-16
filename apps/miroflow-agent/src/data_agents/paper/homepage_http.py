from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from urllib.parse import ParseResult, parse_qsl, urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_HOST_FETCH_GATE_SECONDS: float = 0.5
_DEFAULT_HOMEPAGE_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=12.0,
    write=5.0,
    pool=5.0,
)
_HOST_LAST_FETCH: dict[str, float] = {}
_HOST_GATE_LOCK = threading.Lock()
_CURL_CONNECT_TIMEOUT_SECONDS = 5
_CURL_MAX_TIME_SECONDS = 20
_CURL_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PROXY_ENV_KEYS = {
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
}
_ANTI_SCRAPING_STATUS_CODES = frozenset({403, 412})
_KNOWN_UNPRODUCTIVE_ANTI_SCRAPING_PAGES = (
    ("csse.szu.edu.cn", "/pages/user/index"),
)
_HIT_TEACHER_BODY_ID_RE = re.compile(
    r"\bdata-tid\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_HIT_TEACHER_BODY_VERSION_ID_RE = re.compile(
    r"(?:\bdata-version(?:-id)?\s*=\s*[\"']|"
    r"\bversionId\s*[:=]\s*[\"'])([^\"']+)[\"']",
    re.IGNORECASE,
)
_HIT_TEACHER_BODY_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}
_HIT_TEACHER_BODY_HTML_KEYS = ("html", "body", "content", "data", "result")
_SUSTECH_FACULTY_HOST = "faculty.sustech.edu.cn"
_SUSTECH_JS_REDIRECT_STUB_MAX_CHARS = 4096
_SUSTECH_JS_REDIRECT_MAX_HOPS = 1
_SUSTECH_URL_VAR_RE = re.compile(
    r"\b(?:var|let|const)?\s*url\s*=\s*"
    r"(?P<quote>[\"'])(?P<query>[^\"']+)(?P=quote)\s*;",
    re.IGNORECASE,
)
_SUSTECH_WINDOW_LOCATION_RE = re.compile(
    r"\bwindow\.location\.href\s*=\s*"
    r"(?P<quote>[\"'])(?P<prefix>/\?)(?P=quote)\s*\+\s*url\s*;?",
    re.IGNORECASE,
)


def _reset_host_gate_for_test() -> None:
    with _HOST_GATE_LOCK:
        _HOST_LAST_FETCH.clear()


def _wait_for_host(hostname: str | None) -> None:
    if not hostname:
        return

    with _HOST_GATE_LOCK:
        now = time.monotonic()
        last_called_at = _HOST_LAST_FETCH.get(hostname)
        scheduled_at = now
        if last_called_at is not None:
            scheduled_at = max(now, last_called_at + _HOST_FETCH_GATE_SECONDS)
        _HOST_LAST_FETCH[hostname] = scheduled_at

    sleep_seconds = scheduled_at - now
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def fetch_homepage_html(
    url: str,
    *,
    http_client: httpx.Client | None = None,
) -> str:
    hostname = urlparse(url).hostname
    _wait_for_host(hostname)

    if http_client is not None:
        response = http_client.get(url, follow_redirects=True)
        response.raise_for_status()
        homepage_url, html_content = _resolve_sustech_faculty_js_redirects(
            requested_url=url,
            response=response,
            http_client=http_client,
        )
        return _augment_hit_homepage_dynamic_body(
            homepage_url=homepage_url,
            html_content=html_content,
            http_client=http_client,
        )

    client = httpx.Client(
        trust_env=False,
        follow_redirects=True,
        timeout=_DEFAULT_HOMEPAGE_TIMEOUT,
    )
    try:
        try:
            response = client.get(url)
        except httpx.TransportError as exc:
            html_content = _fetch_homepage_html_with_curl(url, fallback_exc=exc)
            return _augment_hit_homepage_dynamic_body(
                homepage_url=url,
                html_content=html_content,
                http_client=client,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in _ANTI_SCRAPING_STATUS_CODES:
                if _should_skip_anti_scraping_fallback(url):
                    raise
                html_content = _fetch_homepage_html_with_professor_fallback(
                    url,
                    fallback_exc=exc,
                )
                return _augment_hit_homepage_dynamic_body(
                    homepage_url=url,
                    html_content=html_content,
                    http_client=client,
                )
            raise
        homepage_url, html_content = _resolve_sustech_faculty_js_redirects(
            requested_url=url,
            response=response,
            http_client=client,
        )
        return _augment_hit_homepage_dynamic_body(
            homepage_url=homepage_url,
            html_content=html_content,
            http_client=client,
        )
    finally:
        client.close()


def _response_url(response: httpx.Response, *, fallback: str) -> str:
    response_url = getattr(response, "url", None)
    return str(response_url) if response_url else fallback


def _resolve_sustech_faculty_js_redirects(
    *,
    requested_url: str,
    response: httpx.Response,
    http_client: httpx.Client,
) -> tuple[str, str]:
    current_url = _response_url(response, fallback=requested_url)
    html_content = response.text
    seen_urls = {requested_url, current_url}

    for _ in range(_SUSTECH_JS_REDIRECT_MAX_HOPS):
        redirect_url = _sustech_faculty_js_redirect_url(current_url, html_content)
        if redirect_url is None or redirect_url in seen_urls:
            break

        seen_urls.add(redirect_url)
        response = http_client.get(redirect_url, follow_redirects=True)
        response.raise_for_status()
        current_url = _response_url(response, fallback=redirect_url)
        html_content = response.text
        seen_urls.add(current_url)

    return current_url, html_content


def _sustech_faculty_js_redirect_url(current_url: str, html_content: str) -> str | None:
    parsed_current = urlparse(current_url)
    current_host = (parsed_current.hostname or "").lower()
    if current_host != _SUSTECH_FACULTY_HOST:
        return None
    if len(html_content) > _SUSTECH_JS_REDIRECT_STUB_MAX_CHARS:
        return None
    if "window.location.href" not in html_content:
        return None

    url_match = _SUSTECH_URL_VAR_RE.search(html_content)
    location_match = _SUSTECH_WINDOW_LOCATION_RE.search(html_content)
    if url_match is None or location_match is None:
        return None

    query = url_match.group("query").strip()
    if not _is_sustech_faculty_redirect_query(query):
        return None

    redirect_url = urljoin(current_url, f"{location_match.group('prefix')}{query}")
    parsed_redirect = urlparse(redirect_url)
    redirect_host = (parsed_redirect.hostname or "").lower()
    if redirect_host != _SUSTECH_FACULTY_HOST:
        return None
    if parsed_redirect.scheme not in {"http", "https"}:
        return None
    if parsed_redirect.path not in {"", "/"}:
        return None
    if redirect_url == current_url:
        return None
    return redirect_url


def _is_sustech_faculty_redirect_query(query: str) -> bool:
    if not query or any(char in query for char in "\r\n\"'<>\\"):
        return False
    if query.startswith(("/", "?", "#")):
        return False

    params = parse_qsl(query, keep_blank_values=True)
    keys = {key for key, _ in params}
    return "tagid" in keys and {"iscss", "snapid"}.issubset(keys)


def _should_skip_anti_scraping_fallback(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path or ""
    return any(
        hostname == known_hostname and path.startswith(known_path)
        for known_hostname, known_path in _KNOWN_UNPRODUCTIVE_ANTI_SCRAPING_PAGES
    )


def _hit_teacher_body_payload(html_content: str) -> dict[str, str] | None:
    tid_match = _HIT_TEACHER_BODY_ID_RE.search(html_content)
    if not tid_match:
        return None

    teacher_id = tid_match.group(1).strip()
    if not teacher_id:
        return None

    payload = {"id": teacher_id}
    version_match = _HIT_TEACHER_BODY_VERSION_ID_RE.search(html_content)
    if version_match:
        version_id = version_match.group(1).strip()
        if version_id:
            payload["versionId"] = version_id
    return payload


def _decode_json_wrapped_html(value: str) -> str:
    stripped = (value or "").strip()
    if not stripped:
        return ""
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(decoded, str):
        return decoded
    return _html_from_json_payload(decoded)


def _html_from_json_payload(value: object) -> str:
    if isinstance(value, str):
        return _decode_json_wrapped_html(value)
    if not isinstance(value, dict):
        return ""
    for key in _HIT_TEACHER_BODY_HTML_KEYS:
        html_value = value.get(key)
        if isinstance(html_value, str):
            return _decode_json_wrapped_html(html_value)
        if isinstance(html_value, dict):
            nested = _html_from_json_payload(html_value)
            if nested:
                return nested
    return ""


def _hit_teacher_body_url(parsed_homepage_url: ParseResult) -> str:
    return f"https://{parsed_homepage_url.netloc}/TeacherHome/teacherBody.do"


def _augment_hit_homepage_dynamic_body(
    *,
    homepage_url: str,
    html_content: str,
    http_client: httpx.Client,
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
        response = http_client.post(
            teacher_body_url,
            data=payload,
            headers=_HIT_TEACHER_BODY_HEADERS,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to fetch HIT dynamic teacher body %s: %s",
            homepage_url,
            exc,
        )
        return html_content

    body_html = _decode_json_wrapped_html(response.text)
    if not body_html:
        return html_content
    return f"{html_content}\n\n--- HIT dynamic teacher body ---\n{body_html}"


def _fetch_homepage_html_with_curl(url: str, *, fallback_exc: Exception) -> str:
    try:
        completed = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--location",
                "--fail",
                "--compressed",
                "--http1.1",
                "--connect-timeout",
                str(_CURL_CONNECT_TIMEOUT_SECONDS),
                "--max-time",
                str(_CURL_MAX_TIME_SECONDS),
                "--user-agent",
                _CURL_USER_AGENT,
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=_proxy_free_env(),
        )
    except OSError:
        raise fallback_exc from None

    if completed.returncode != 0 or not completed.stdout.strip():
        raise fallback_exc
    return completed.stdout


def _fetch_homepage_html_with_professor_fallback(
    url: str,
    *,
    fallback_exc: Exception,
) -> str:
    from ..professor.discovery import fetch_html_with_fallback

    result = fetch_html_with_fallback(url, timeout=_CURL_MAX_TIME_SECONDS)
    if result.html is not None and result.html.strip():
        return result.html
    raise fallback_exc


def _proxy_free_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _PROXY_ENV_KEYS}
