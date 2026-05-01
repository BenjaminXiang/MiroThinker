from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import requests

logger = logging.getLogger(__name__)

_OPENALEX_AUTHORS_ENDPOINT = "https://api.openalex.org/authors"
_MAX_ATTEMPTS = 3
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_ORCID_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?orcid\.org/(?P<orcid>\d{4}-\d{4}-\d{4}-\d{3}[\dX])/?$",
    re.IGNORECASE,
)
_BARE_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


@dataclass(frozen=True, slots=True)
class ProfMetrics:
    h_index: int | None
    citation_count: int | None
    works_count_openalex: int | None
    source: Literal["openalex", "openalex_unmatched"]
    fetched_at: datetime


def fetch_metrics(
    *,
    orcid: str | None = None,
    openalex_author_id: str | None = None,
    http_client: Any = None,
    timeout: float = 10.0,
) -> ProfMetrics:
    """Fetch OpenAlex author summary stats.

    Priority is explicit OpenAlex author ID, then ORCID. Transport and payload
    failures are fail-closed and return an unmatched metrics object.
    """

    fetched_at = datetime.now(timezone.utc)
    request = _build_request(
        orcid=orcid,
        openalex_author_id=openalex_author_id,
    )
    if request is None:
        return _unmatched(fetched_at=fetched_at)

    owned_client = http_client is None
    client = http_client or _new_client()
    try:
        payload = _request_json(
            client,
            url=request[0],
            params=request[1],
            timeout=timeout,
        )
    finally:
        if owned_client:
            client.close()

    author = _select_author_payload(payload)
    if author is None:
        return _unmatched(fetched_at=fetched_at)

    return ProfMetrics(
        h_index=_summary_h_index(author),
        citation_count=_coerce_non_negative_int(author.get("cited_by_count")),
        works_count_openalex=_coerce_non_negative_int(author.get("works_count")),
        source="openalex",
        fetched_at=fetched_at,
    )


def _new_client() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def _build_request(
    *,
    orcid: str | None,
    openalex_author_id: str | None,
) -> tuple[str, dict[str, str | int]] | None:
    author_id = _normalize_openalex_author_id(openalex_author_id)
    select = "id,summary_stats,cited_by_count,works_count"
    if author_id:
        return f"{_OPENALEX_AUTHORS_ENDPOINT}/{author_id}", {
            "select": select,
            "mailto": "mirothinker-data-agent@example.com",
        }

    normalized_orcid = _normalize_orcid(orcid)
    if not normalized_orcid:
        return None
    return _OPENALEX_AUTHORS_ENDPOINT, {
        "filter": f"orcid:{normalized_orcid}",
        "per-page": 1,
        "select": select,
        "mailto": "mirothinker-data-agent@example.com",
    }


def _request_json(
    client: Any,
    *,
    url: str,
    params: dict[str, str | int],
    timeout: float,
) -> dict[str, Any] | None:
    response = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = client.get(url, params=params, timeout=timeout)
        except requests.Timeout as exc:
            if attempt + 1 >= _MAX_ATTEMPTS:
                logger.warning("OpenAlex metrics timeout for %s: %s", url, exc)
                return None
            _sleep_before_retry(attempt)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAlex metrics fetch failed for %s: %s", url, exc)
            return None

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code == 404:
            return None
        if status_code in _RETRY_STATUS_CODES:
            if attempt + 1 >= _MAX_ATTEMPTS:
                logger.warning(
                    "OpenAlex metrics fetch exhausted retries for %s: HTTP %s",
                    url,
                    status_code,
                )
                return None
            _sleep_before_retry(attempt)
            continue
        if status_code >= 400:
            logger.warning(
                "OpenAlex metrics fetch failed for %s: HTTP %s",
                url,
                status_code,
            )
            return None

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("OpenAlex metrics payload parse failed for %s: %s", url, exc)
            return None
        if isinstance(payload, dict):
            return payload
        return None
    return None


def _select_author_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("id"):
        return payload
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return first if isinstance(first, dict) else None


def _summary_h_index(author: dict[str, Any]) -> int | None:
    stats = author.get("summary_stats")
    if not isinstance(stats, dict):
        return None
    return _coerce_non_negative_int(stats.get("h_index"))


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _normalize_openalex_author_id(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("https://openalex.org/"):
        raw = raw.rsplit("/", 1)[-1]
    if raw.startswith("https://api.openalex.org/authors/"):
        raw = raw.rsplit("/", 1)[-1]
    return raw or None


def _normalize_orcid(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    match = _ORCID_RE.fullmatch(raw)
    if match:
        return match.group("orcid").upper()
    if _BARE_ORCID_RE.fullmatch(raw):
        return raw.upper()
    return None


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(min(0.1 * (2**attempt), 1.0))


def _unmatched(*, fetched_at: datetime) -> ProfMetrics:
    return ProfMetrics(
        h_index=None,
        citation_count=None,
        works_count_openalex=None,
        source="openalex_unmatched",
        fetched_at=fetched_at,
    )
