#!/usr/bin/env python3
"""Backfill ``paper.abstract_clean`` for embodied-AI papers whose abstract is NULL.

Reuses the existing paper providers
(``enrich_paper_metadata_from_crossref`` / ``enrich_paper_with_openalex`` /
``enrich_paper_with_openalex_id`` / ``enrich_paper_metadata_from_arxiv``)
for id-based fetch, injecting fresh-fetch callables that bypass the on-disk
provider cache (so the backfill always hits the network). For
``prof_page_only`` shells that have no DOI / arxiv_id / openalex_id, falls back
to title-based realtime resolution against OpenAlex (``/works?search=``) then
arXiv (``ti:`` query) — the ``recover-paper-shells-via-realtime-resolution``
pattern.

Only ``abstract_clean`` is written. ``quality_status`` and Milvus are NOT
touched (summary_zh + promote + embed are separate steps).

Usage::

    cd apps/miroflow-agent
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
    export DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real
    uv run python scripts/backfill_embodied_abstracts.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET

import psycopg
import requests
from psycopg.rows import dict_row

# Make ``src.*`` importable when run from apps/miroflow-agent.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

# OpenAlex polite pool works without an api key as long as we send mailto.
# The provider default skips requests when no key is set; opt out so the
# backfill actually hits the API.
os.environ.setdefault("OPENALEX_SKIP_WITHOUT_API_KEY", "0")

from src.data_agents.paper.arxiv import enrich_paper_metadata_from_arxiv  # noqa: E402
from src.data_agents.paper.crossref import enrich_paper_metadata_from_crossref  # noqa: E402
from src.data_agents.paper.enrichment import enrich_paper_with_openalex_id  # noqa: E402
from src.data_agents.paper.openalex import (  # noqa: E402
    _decode_abstract,
    enrich_paper_with_openalex,
)
from src.data_agents.providers.crossref import (  # noqa: E402
    crossref_request_headers,
    crossref_request_params,
)
from src.data_agents.providers.openalex import (  # noqa: E402
    OPENALEX_RATE_LIMIT_CIRCUIT,
    openalex_rate_limit_cooldown_seconds,
    openalex_request_params,
)

MAILTO = "mirothinker-data-agent@example.com"
TIMEOUT = (5, 20)
SLEEP_BETWEEN_FETCHES = 0.5
COMMIT_BATCH = 5
MAX_CONSECUTIVE_FAILURES = 5

OPENALEX_WORKS = "https://api.openalex.org/works"
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TITLE_TOKEN_RE = re.compile(r"[0-9a-z一-鿿]+")
_TITLE_MATCH_THRESHOLD = 0.6  # Jaccard token overlap; Crossref query.title is
# fuzzy and returns different papers that share common words (e.g. a "Survey on
# Fine-Grained MLLMs" matched "AffordBot" at 0.43). 0.6 cleanly separates exact
# matches (>=0.82) from those wrong-paper false positives (<=0.43).


# --- fresh-fetch callables (bypass provider on-disk cache) -----------------


def _empty_openalex_payload(url: str) -> dict:
    tail = url.rstrip("/")
    if tail.endswith("/works") or "/works?" in tail:
        return {"results": []}
    return {}


def fresh_crossref_fetch(url: str, params: dict) -> dict:
    req_params = crossref_request_params(params)
    resp = requests.get(
        url,
        params=req_params,
        timeout=TIMEOUT,
        headers=crossref_request_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def fresh_openalex_fetch(url: str, params: dict) -> dict:
    req_params = openalex_request_params(params)
    if req_params is None:
        return _empty_openalex_payload(url)
    if not OPENALEX_RATE_LIMIT_CIRCUIT.can_call():
        return _empty_openalex_payload(url)
    req_params = dict(req_params)
    req_params.setdefault("mailto", MAILTO)
    resp = requests.get(url, params=req_params, timeout=TIMEOUT)
    if resp.status_code == 429:
        OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(
            openalex_rate_limit_cooldown_seconds(getattr(resp, "headers", {}) or {})
        )
    if resp.status_code >= 400:
        return _empty_openalex_payload(url)
    OPENALEX_RATE_LIMIT_CIRCUIT.record_success()
    return resp.json()


def fresh_openalex_fetch_by_url(url: str) -> dict:
    return fresh_openalex_fetch(url, {})


def fresh_arxiv_fetch(url: str, params: dict) -> str:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


# --- title-based realtime resolution (shells with no ids) ------------------


def _clean_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    item = _WS_RE.sub(" ", value).strip()
    return item or None


def _clean_abstract(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return _clean_text(_HTML_TAG_RE.sub(" ", text))


def _title_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    folded = unicodedata.normalize("NFKD", value.casefold())
    return set(_TITLE_TOKEN_RE.findall(folded))


def _title_match(query: str, candidate: str) -> float:
    q = _title_tokens(query)
    c = _title_tokens(candidate)
    if not q or not c:
        return 0.0
    return len(q & c) / len(q | c)


def fetch_abstract_openalex_title(title: str) -> tuple[str | None, str | None]:
    """Search OpenAlex by title; return (abstract, matched_title)."""
    params = {"search": title, "per-page": 1}
    req_params = openalex_request_params(params)
    if req_params is None or not OPENALEX_RATE_LIMIT_CIRCUIT.can_call():
        return None, None
    req_params = dict(req_params)
    req_params.setdefault("mailto", MAILTO)
    try:
        resp = requests.get(OPENALEX_WORKS, params=req_params, timeout=TIMEOUT)
    except requests.RequestException:
        return None, None
    if resp.status_code == 429:
        OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(
            openalex_rate_limit_cooldown_seconds(getattr(resp, "headers", {}) or {})
        )
    if resp.status_code >= 400:
        return None, None
    OPENALEX_RATE_LIMIT_CIRCUIT.record_success()
    results = (resp.json() or {}).get("results") or []
    if not results:
        return None, None
    top = results[0]
    matched_title = (top.get("display_name") or "").strip() or None
    if matched_title and _title_match(title, matched_title) < _TITLE_MATCH_THRESHOLD:
        return None, matched_title  # wrong paper
    return _decode_abstract(top.get("abstract_inverted_index")), matched_title


def fetch_abstract_arxiv_title(title: str) -> tuple[str | None, str | None]:
    """Search arXiv by title; return (abstract, matched_title)."""
    params = {"search_query": f"ti:{title}", "max_results": 1}
    try:
        resp = requests.get(
            ARXIV_ENDPOINT,
            params=params,
            timeout=(3, 8),
            headers={"User-Agent": "MiroThinkerDataAgent/0.1"},
        )
    except requests.RequestException:
        return None, None
    if resp.status_code >= 400:
        return None, None
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None, None
    entry = root.find("atom:entry", ARXIV_NS)
    if entry is None:
        return None, None
    matched_title = _clean_text(entry.findtext("atom:title", default="", namespaces=ARXIV_NS))
    if matched_title and _title_match(title, matched_title) < _TITLE_MATCH_THRESHOLD:
        return None, matched_title
    summary = entry.findtext("atom:summary", default="", namespaces=ARXIV_NS)
    return _clean_text(summary), matched_title


def fetch_abstract_crossref_title(title: str) -> tuple[str | None, str | None]:
    """Search Crossref by title; return (abstract, matched_title).

    Crossref carries JATS-tagged abstracts for some works and is reachable even
    when OpenAlex / arXiv are throttling this environment, so it serves as the
    working realtime-resolution backstop for prof_page_only shells.
    """
    for attempt in range(2):
        try:
            resp = requests.get(
                "https://api.crossref.org/works",
                params={"query.title": title, "rows": 3},
                timeout=TIMEOUT,
                headers=crossref_request_headers(),
            )
        except requests.RequestException as exc:
            if attempt == 0:
                time.sleep(15)
                continue
            raise RuntimeError(
                f"crossref_title:network:{type(exc).__name__}"
            ) from exc
        if resp.status_code == 429 and attempt == 0:
            time.sleep(20)  # transient rate-limit; back off once
            continue
        break
    if resp.status_code >= 400:
        raise RuntimeError(f"crossref_title:http:{resp.status_code}")
    resp.raise_for_status()
    items = (resp.json().get("message") or {}).get("items") or []
    for item in items:
        candidate = (item.get("title") or [""])[0]
        if not candidate:
            continue
        if _title_match(title, candidate) < _TITLE_MATCH_THRESHOLD:
            continue
        abstract = _clean_abstract(item.get("abstract"))
        if abstract:
            return abstract, candidate
    return None, None


# --- per-paper fetch orchestration ------------------------------------------


def _try(provider: str, fn, *args, **kwargs):
    """Run a provider call, return (abstract, source) or (None, reason)."""
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — backfill must not abort
        return None, f"{provider}:exception:{type(exc).__name__}:{exc}"
    abstract = None
    if isinstance(result, str):
        abstract = _clean_text(result)
    else:
        abstract = getattr(result, "abstract", None) if result else None
        if abstract is not None:
            abstract = _clean_text(abstract)
    if not abstract:
        return None, f"{provider}:no-abstract"
    return abstract, provider


def fetch_abstract_for(row: dict) -> tuple[str | None, str, str]:
    """Return (abstract, source, reason). abstract is None on failure."""
    doi = (row.get("doi") or "").strip() or None
    arxiv_id = (row.get("arxiv_id") or "").strip() or None
    openalex_id = (row.get("openalex_id") or "").strip() or None
    title = (row.get("title_clean") or row.get("title_raw") or "").strip() or None

    # Priority: openalex_id -> arxiv_id -> crossref(doi) -> openalex(doi)
    #           -> openalex(title) -> arxiv(title)
    if openalex_id:
        ab, src = _try(
            "openalex_id",
            enrich_paper_with_openalex_id,
            openalex_id,
            request_json=fresh_openalex_fetch_by_url,
        )
        if ab:
            return ab, src, ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

    if arxiv_id:
        ab, src = _try(
            "arxiv_id",
            enrich_paper_metadata_from_arxiv,
            arxiv_id,
            request_text=fresh_arxiv_fetch,
        )
        if ab:
            return ab, src, ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

    if doi:
        ab, src = _try(
            "crossref_doi",
            enrich_paper_metadata_from_crossref,
            doi,
            request_json=fresh_crossref_fetch,
        )
        if ab:
            return ab, src, ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

        ab, src = _try(
            "openalex_doi",
            enrich_paper_with_openalex,
            doi,
            request_json=fresh_openalex_fetch,
        )
        if ab:
            return ab, src, ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

    if title:
        ab, matched = fetch_abstract_openalex_title(title)
        ab = _clean_text(ab)
        if ab:
            return ab, "openalex_title", ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

        ab, matched = fetch_abstract_arxiv_title(title)
        ab = _clean_text(ab)
        if ab:
            return ab, "arxiv_title", ""
        time.sleep(SLEEP_BETWEEN_FETCHES)

        try:
            ab, matched = fetch_abstract_crossref_title(title)
        except Exception as exc:  # noqa: BLE001
            return (
                None,
                "crossref_title",
                f"crossref_title:exception:{type(exc).__name__}:{exc}",
            )
        ab = _clean_text(ab)
        if ab:
            return ab, "crossref_title", ""
        time.sleep(SLEEP_BETWEEN_FETCHES)
        return (
            None,
            "title-search-fail",
            "no id + openalex/arxiv/crossref title-search miss (openalex/arxiv throttled)",
        )
    return None, "no-id-no-title", "no identifiers and no title to search"


# --- DB + main --------------------------------------------------------------


QUERY = """
SELECT p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, p.openalex_id,
       p.semantic_scholar_id, p.canonical_source
FROM paper p
JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id
JOIN professor pr ON pr.professor_id = ppl.professor_id
WHERE p.title_clean ~* '具身智能|灵巧手|embodied|dexterous|humanoid|具身|灵巧'
  AND pr.identity_status = 'resolved' AND pr.lifecycle_state = 'active'
  AND p.identity_status != 'rejected'
  AND p.quality_status IN ('needs_enrichment', 'partial')
  AND p.abstract_clean IS NULL
GROUP BY p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, p.openalex_id,
         p.semantic_scholar_id, p.canonical_source
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="fetch but do not write")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    written = 0
    still_null: list[tuple[str, str, str]] = []  # (paper_id, source/reason, detail)
    provider_hits: dict[str, int] = {}
    consecutive_failures = 0
    sample: tuple[str, str, str] | None = None
    pending_updates: list[tuple[str, str]] = []

    conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
    try:
        rows = conn.execute(QUERY).fetchall()
        print(f"rows-to-process: {len(rows)}")

        def flush(cur):
            for pid, ab in pending_updates:
                cur.execute(
                    "UPDATE paper SET abstract_clean = %s WHERE paper_id = %s",
                    (ab, pid),
                )
            conn.commit()
            pending_updates.clear()

        for i, row in enumerate(rows, 1):
            pid = row["paper_id"]
            title = (row.get("title_clean") or row.get("title_raw") or "")[:70]
            abstract, source, reason = fetch_abstract_for(row)
            if abstract:
                provider_hits[source] = provider_hits.get(source, 0) + 1
                consecutive_failures = 0
                if not args.dry_run:
                    pending_updates.append((pid, abstract))
                    if len(pending_updates) >= COMMIT_BATCH:
                        with conn.cursor() as cur:
                            flush(cur)
                written += 1
                if sample is None:
                    sample = (title, source, abstract[:150])
                print(f"[{i}/{len(rows)}] OK  {pid[:12]} src={source} :: {title}")
            else:
                still_null.append((pid, source, reason))
                print(
                    f"[{i}/{len(rows)}] MISS {pid[:12]} src={source} :: {reason} :: {title}"
                )
                # Guard detects real access breakage (exceptions / 5xx from the
                # working source), not legitimate no-matches or known-throttled
                # OpenAlex/arXiv title-search. ":exception:" is emitted by _try
                # and the crossref_title wrapper on real failures.
                if ":exception:" in reason:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0
                if consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"STOP: {MAX_CONSECUTIVE_FAILURES} consecutive access "
                        "exceptions — external access broken.",
                        file=sys.stderr,
                    )
                    break

        if pending_updates and not args.dry_run:
            with conn.cursor() as cur:
                flush(cur)
    finally:
        conn.close()

    print("\n=== REPORT ===")
    print(f"status: {'DRY-RUN' if args.dry_run else 'DONE'}")
    print(f"total: {len(rows)} | written: {written} | still-null: {len(still_null)}")
    print("provider-hits:", provider_hits)
    if sample:
        print(
            f"sample: title={sample[0]!r} src={sample[1]} abstract={sample[2]!r}"
        )
    if still_null:
        print("still-null by reason:")
        by_reason: dict[str, int] = {}
        for _pid, src, _reason in still_null:
            by_reason[src] = by_reason.get(src, 0) + 1
        for reason, count in sorted(by_reason.items()):
            print(f"  {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
