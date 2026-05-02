"""Postgres-backed cache for E-route web search results."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

_SQLALCHEMY_PREFIX = "postgresql+psycopg://"
_PG_PREFIX = "postgresql://"
_DEFAULT_TTL_SECONDS = 24 * 3600
_MAX_QUERY_CHARS = 1000


def _normalize_dsn(dsn: str) -> str:
    if dsn.startswith(_SQLALCHEMY_PREFIX):
        return _PG_PREFIX + dsn[len(_SQLALCHEMY_PREFIX) :]
    return dsn


def _query_key(query: str) -> tuple[str, str]:
    text = query.strip()[:_MAX_QUERY_CHARS]
    return text, hashlib.sha1(text.encode("utf-8")).hexdigest()


class WebSearchCache:
    def __init__(self, dsn: str | None, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self.dsn = _normalize_dsn(dsn) if dsn else None
        self.ttl_seconds = ttl_seconds

    def get(self, query: str, provider: str = "serper") -> list[dict] | None:
        if not self.dsn:
            return None
        query_text, query_sha1 = _query_key(query)
        if not query_text:
            return None
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                row = conn.execute(
                    """
                    SELECT results
                      FROM web_search_cache
                     WHERE query_sha1 = %s
                       AND provider = %s
                       AND cached_at > now() - (%s * interval '1 second')
                    """,
                    (query_sha1, provider, self.ttl_seconds),
                ).fetchone()
        except Exception as exc:
            logger.warning("Web search cache read failed: %s", exc)
            return None
        if row is None:
            return None
        results = row.get("results")
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except json.JSONDecodeError:
                return None
        return results if isinstance(results, list) else None

    def set(self, query: str, results: list[dict], *, provider: str = "serper") -> None:
        if not self.dsn:
            return
        query_text, query_sha1 = _query_key(query)
        if not query_text:
            return
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                conn.execute(
                    """
                    INSERT INTO web_search_cache (
                        query_sha1,
                        query_text,
                        results,
                        provider,
                        cached_at
                    )
                    VALUES (%s, %s, %s::jsonb, %s, now())
                    ON CONFLICT (query_sha1) DO UPDATE
                       SET query_text = EXCLUDED.query_text,
                           results = EXCLUDED.results,
                           provider = EXCLUDED.provider,
                           cached_at = EXCLUDED.cached_at
                    """,
                    (
                        query_sha1,
                        query_text,
                        json.dumps(results, ensure_ascii=False),
                        provider,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("Web search cache write failed: %s", exc)

    def clear_expired(self, provider: str = "serper") -> int:
        if not self.dsn:
            return 0
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                result = conn.execute(
                    """
                    DELETE FROM web_search_cache
                     WHERE provider = %s
                       AND cached_at <= now() - (%s * interval '1 second')
                    """,
                    (provider, self.ttl_seconds),
                )
                conn.commit()
                return int(result.rowcount or 0)
        except Exception as exc:
            logger.warning("Web search cache GC failed: %s", exc)
            return 0


def normalize_serper_results(payload: dict, *, top_n: int = 5) -> list[dict]:
    organics = payload.get("organic") or []
    if not isinstance(organics, list):
        return []
    results: list[dict] = []
    for item in organics:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if link or title:
            results.append({"title": title or link, "link": link, "snippet": snippet})
    return results[:top_n]


def web_evidence_from_results(results: list[dict]) -> list[dict]:
    evidence: list[dict] = []
    for idx, result in enumerate(results[:5], start=1):
        link = str(result.get("link") or "").strip()
        title = str(result.get("title") or link or f"网页结果 {idx}")
        evidence.append(
            {
                "type": "web",
                "source_type": "web",
                "id": link or f"web:{idx}",
                "title": title,
                "snippet": str(result.get("snippet") or "")[:500],
                "url": link or None,
                "score": 1.0 - (idx - 1) * 0.05,
            }
        )
    return evidence


def answer_knowledge_qa_with_web_search(
    query: str,
    *,
    cache: WebSearchCache,
    provider_factory: Callable[[], object | None],
    synthesize: Callable[[str, list[dict]], str],
    fallback: Callable[[str], tuple[str, str | None]],
    logger: logging.Logger,
) -> tuple[str, str | None, list[dict]]:
    cached = cache.get(query, provider="serper")
    err: str | None = None
    if cached is None:
        provider = provider_factory()
        if provider is None:
            results = []
            err = "SERPER_API_KEY 未配置"
        else:
            try:
                results = normalize_serper_results(provider.search(query), top_n=5)
            except Exception as exc:
                logger.warning("Serper search failed for knowledge QA %r: %s", query, exc)
                results = []
                err = str(exc)
            else:
                if results:
                    cache.set(query, results, provider="serper")
    else:
        results = cached[:5]

    evidence = web_evidence_from_results(results)
    if not evidence:
        fallback_answer, fallback_err = fallback(query)
        return (
            f"未引用网络搜索；以下为纯 LLM 回答：{fallback_answer}",
            err or fallback_err,
            [],
        )
    try:
        return synthesize(query, evidence), err, evidence
    except Exception as exc:
        logger.warning("Web evidence synthesis failed for %r: %s", query, exc)
        lines = ["以下是网络搜索到的相关资料："]
        for idx, item in enumerate(evidence, start=1):
            lines.append(f"[web][{idx}] {item['title']}：{item.get('snippet') or ''}")
        return "\n".join(lines), str(exc), evidence
