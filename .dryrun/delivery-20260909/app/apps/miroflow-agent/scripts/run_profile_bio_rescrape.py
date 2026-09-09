# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.19c + 7.20b — re-scrape prof homepages, extract bio + link CV PDFs.

Solves TWO Round 7 residuals in one pass:
  1. professor.profile_raw_text is 0/783 populated because the original
     crawl didn't persist clean text. Re-fetch primary_official_profile_page
     URL, extract the bio paragraph, store it.
  2. source_page cv_pdf rows have owner_scope_ref=NULL, so we can't
     attribute the CV PDFs to a specific professor. Re-fetching the
     prof's homepage lets us discover CV PDF links IN CONTEXT (on this
     prof's own page), which gives unambiguous attribution.

User requirement: NO PROXY for crawl. We explicitly unset proxy env at
process start and pass trust_env=False to httpx so no environment
variable sneaks in.

Bio extraction heuristic (rule-based, no LLM):
  1. Parse HTML via selectolax (already a repo dep)
  2. Prefer <div class="..."> or <section> whose text contains keywords:
     简介 / 个人简介 / 教育 / Biography / Profile / About
  3. Otherwise pick the longest <p>/<div> prose block (≥ 150 chars,
     whitespace-collapsed)
  4. Cap at 5000 chars; fallback to first 2000 chars of page text

CV link discovery: all <a href="...pdf"> on the page with hostname matching
the prof's homepage host. Upsert each into source_page with
page_role='cv_pdf', owner_scope_kind='professor', owner_scope_ref=prof_id.

--dry-run default, --apply --confirm-real-db for writes.
--limit N for smoke tests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
import psycopg
from bs4 import BeautifulSoup
from psycopg.rows import dict_row

from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_19c_bio_rescrape"
_FETCH_TIMEOUT_S = 20.0
_MIN_BIO_CHARS = 150
_MAX_BIO_CHARS = 5000
_RATE_LIMIT_SLEEP = 0.5  # seconds between requests (gentle on servers)

_BIO_KEYWORDS_CN = ("简介", "个人简介", "个人介绍", "教育背景", "工作经历", "研究兴趣", "研究方向")
_BIO_KEYWORDS_EN = ("biography", "profile", "about", "background", "cv")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


@dataclass
class Stats:
    examined: int = 0
    fetched_ok: int = 0
    fetch_failed: int = 0
    bio_extracted: int = 0
    bio_stored: int = 0
    cv_pdfs_found: int = 0
    cv_pdfs_attributed: int = 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--database-url")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-real-db", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--skip-if-populated",
        action="store_true",
        default=True,
        help="Skip profs whose profile_raw_text is already non-null (default on).",
    )
    return p.parse_args()


def _clear_proxy_env() -> None:
    for key in (
        "all_proxy", "ALL_PROXY",
        "http_proxy", "HTTP_PROXY",
        "https_proxy", "HTTPS_PROXY",
        "no_proxy", "NO_PROXY",
    ):
        os.environ.pop(key, None)


def _fetch_candidates(conn, *, limit: int | None, skip_populated: bool) -> list[dict]:
    sql = """
        SELECT p.professor_id,
               p.canonical_name,
               sp.url AS profile_url,
               sp.page_id::text AS page_id,
               p.profile_raw_text IS NOT NULL AND length(p.profile_raw_text) > 0
                 AS already_populated
          FROM professor p
          JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.identity_status = 'resolved'
           AND sp.url LIKE 'http%%'
    """
    if skip_populated:
        sql += "\n AND (p.profile_raw_text IS NULL OR length(p.profile_raw_text) = 0)"
    sql += "\n ORDER BY p.canonical_name"
    if limit is not None:
        sql += f"\n LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _fetch_page(client: httpx.Client, url: str) -> str | None:
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            return None
        # Try charset detection
        text = resp.text
        if not text or len(text) < 100:
            return None
        return text
    except (httpx.RequestError, httpx.HTTPError):
        return None


_NAV_TOKENS_RE = re.compile(r"(?:^|\s)[A-Z](?:\s+[A-Z]){2,}")  # "A B C D E ..."
_CN_NAV_WORDS = ("师资队伍", "首页", "学院领导", "客座教授", "全部")


def _looks_like_navigation(text: str) -> bool:
    """Filter out navigation-heavy blocks (alphabet lists, faculty indices)."""
    # Long run of single-letter uppercase tokens
    if _NAV_TOKENS_RE.search(text):
        return True
    # Too many navigation words
    nav_hits = sum(1 for w in _CN_NAV_WORDS if w in text)
    if nav_hits >= 3:
        return True
    # Low prose density: <20% of chars are Chinese, <30% are letters→digits
    cn_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_alpha = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cn_chars < 30 and ascii_alpha < 100:
        return True
    # Sentence-ending marks
    sentence_marks = sum(text.count(m) for m in ("。", ". ", "！", "!", "；"))
    if sentence_marks < 2:
        return True
    return False


def _extract_bio(html: str) -> str | None:
    """Return the best bio paragraph (≥ 150 chars) or None. Filters out
    navigation-heavy blocks and requires prose sentence structure."""
    if not html:
        return None
    try:
        soup = BeautifulSoup(_SCRIPT_STYLE_RE.sub("", html), "lxml")
    except Exception:
        return None

    candidates: list[tuple[int, str, bool]] = []  # (score, text, has_keyword)
    for node in soup.find_all(["section", "article", "div", "p"]):
        text = node.get_text(" ", strip=True) if node else ""
        text = _WS_RE.sub(" ", text).strip()
        if len(text) < _MIN_BIO_CHARS:
            continue
        if _looks_like_navigation(text):
            continue
        if len(text) > _MAX_BIO_CHARS:
            text = text[:_MAX_BIO_CHARS]
        score = len(text)
        low = text.lower()
        has_keyword = False
        if any(kw in text for kw in _BIO_KEYWORDS_CN):
            score += 800
            has_keyword = True
        if any(kw in low for kw in _BIO_KEYWORDS_EN):
            score += 400
            has_keyword = True
        candidates.append((score, text, has_keyword))

    if not candidates:
        return None
    # Prefer blocks WITH bio keywords over longer-but-no-keyword ones
    with_kw = [c for c in candidates if c[2]]
    pool = with_kw if with_kw else candidates
    pool.sort(reverse=True)
    return pool[0][1]


def _find_cv_pdf_links(html: str, page_url: str) -> list[str]:
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    host = urlparse(page_url).hostname or ""
    pdfs: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        absolute = urljoin(page_url, href)
        if ".pdf" not in absolute.lower():
            continue
        if host and urlparse(absolute).hostname != host:
            continue
        if "openaccess" in absolute.lower() or "arxiv" in absolute.lower():
            continue
        pdfs.add(absolute)
    return sorted(pdfs)


def _update_prof_bio(conn, professor_id: str, text: str) -> int:
    return conn.execute(
        """
        UPDATE professor
           SET profile_raw_text = %s, updated_at = now()
         WHERE professor_id = %s
           AND identity_status = 'resolved'
           AND (profile_raw_text IS NULL OR profile_raw_text = '')
        """,
        (text, professor_id),
    ).rowcount


def _upsert_cv_source_page(conn, *, prof_id: str, url: str) -> int:
    """Insert a source_page row for this CV PDF, or attribute an existing one."""
    # Check if url already exists
    existing = conn.execute(
        "SELECT page_id, owner_scope_ref FROM source_page WHERE url = %s LIMIT 1",
        (url,),
    ).fetchone()
    if existing:
        # Attribute it to this prof if unassigned
        if not existing["owner_scope_ref"]:
            conn.execute(
                """
                UPDATE source_page
                   SET owner_scope_kind='professor', owner_scope_ref=%s,
                       page_role='cv_pdf'
                 WHERE page_id = %s::uuid
                """,
                (prof_id, existing["page_id"]),
            )
            return 1
        return 0
    # Insert new row
    conn.execute(
        """
        INSERT INTO source_page (
            url, page_role, owner_scope_kind, owner_scope_ref, fetched_at, is_official_source
        ) VALUES (%s, 'cv_pdf', 'professor', %s, now(), true)
        """,
        (url, prof_id),
    )
    return 1


def main() -> int:
    _clear_proxy_env()
    args = _parse_args()

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print("Refusing miroflow_real without --confirm-real-db.", file=sys.stderr)
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    stats = Stats()
    # trust_env=False ensures proxies from env don't leak in even if
    # something restored them mid-session (user request: no proxy for crawl)
    client = httpx.Client(
        timeout=_FETCH_TIMEOUT_S,
        follow_redirects=True,
        trust_env=False,
        headers={"User-Agent": "MiroThinker/7.19c bio-rescrape (contact admin)"},
    )

    with psycopg.connect(dsn, row_factory=dict_row) as conn, client:
        candidates = _fetch_candidates(
            conn, limit=args.limit, skip_populated=args.skip_if_populated
        )
        print(f"[rescrape] {len(candidates)} candidates")
        for i, row in enumerate(candidates, 1):
            stats.examined += 1
            url = row["profile_url"]
            html = _fetch_page(client, url)
            if not html:
                stats.fetch_failed += 1
                if i % 20 == 0:
                    print(f"  {i}/{len(candidates)}: fetch_failed={stats.fetch_failed}")
                time.sleep(_RATE_LIMIT_SLEEP)
                continue
            stats.fetched_ok += 1

            bio = _extract_bio(html)
            if bio:
                stats.bio_extracted += 1
                if args.apply:
                    stats.bio_stored += _update_prof_bio(
                        conn, row["professor_id"], bio
                    )

            cv_urls = _find_cv_pdf_links(html, url)
            stats.cv_pdfs_found += len(cv_urls)
            if args.apply:
                for cv_url in cv_urls:
                    stats.cv_pdfs_attributed += _upsert_cv_source_page(
                        conn, prof_id=row["professor_id"], url=cv_url
                    )

            if i % 20 == 0:
                print(
                    f"  {i}/{len(candidates)}: ok={stats.fetched_ok} "
                    f"bio={stats.bio_extracted} cvs={stats.cv_pdfs_found}"
                )
            time.sleep(_RATE_LIMIT_SLEEP)

        if not args.apply:
            conn.rollback()

    print()
    print("=== profile bio rescrape summary ===")
    print(f"  examined         : {stats.examined}")
    print(f"  fetched OK       : {stats.fetched_ok}")
    print(f"  fetch_failed     : {stats.fetch_failed}")
    print(f"  bio extracted    : {stats.bio_extracted}")
    print(f"  CV pdfs found    : {stats.cv_pdfs_found}")
    print(f"  apply            : {args.apply}")
    if args.apply:
        print(f"  bios stored      : {stats.bio_stored}")
        print(f"  CV pdfs attributed: {stats.cv_pdfs_attributed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
