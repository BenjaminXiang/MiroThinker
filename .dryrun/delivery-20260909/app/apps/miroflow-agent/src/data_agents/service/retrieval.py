from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from contextlib import contextmanager, nullcontext
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Protocol

from ..paper.title_cleaner import clean_paper_title
from ..storage.milvus_collections import (
    COMPANY_PROFILES_COLLECTION,
    PAPER_CHUNKS_COLLECTION,
    PATENT_PROFILES_COLLECTION,
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
    PROFESSOR_RESEARCH_PROFILES_COLLECTION,
)

logger = logging.getLogger(__name__)

_VALID_DOMAINS = {"professor", "paper", "company", "patent"}
_Domain = Literal["professor", "paper", "company", "patent"]
_MAX_RELATED_LIMIT = 200
_PROFESSOR_COLLECTION = "professor_profiles"
_PROFESSOR_IDENTITY_INDEX = "identity"
_PROFESSOR_RESEARCH_INDEX = "research"
_PROFESSOR_OUTPUT_FIELDS = [
    "id",
    "name",
    "institution",
    "department",
    "profile_summary",
    "h_index",
    "citation_count",
    "paper_count",
]
_PROFESSOR_IDENTITY_OUTPUT_FIELDS = [
    "id",
    "name",
    "name_en",
    "institution",
    "department",
    "title",
    "profile_url",
    "identity_text",
    "quality_status",
]
_PROFESSOR_RESEARCH_OUTPUT_FIELDS = [
    "id",
    "research_text",
    "research_directions",
    "profile_summary",
    "paper_summary",
    "patent_summary",
    "quality_status",
    "h_index",
    "citation_count",
    "paper_count",
]
_PAPER_OUTPUT_FIELDS = [
    "chunk_id",
    "paper_id",
    "chunk_type",
    "segment_index",
    "year",
    "venue",
    "content_text",
]
_COMPANY_OUTPUT_FIELDS = [
    "id",
    "name",
    "industry",
    "hq_city",
    "description",
    "profile_summary",
    "technology_route_summary",
]
_PATENT_OUTPUT_FIELDS = [
    "id",
    "patent_number",
    "title",
    "abstract",
    "technology_effect",
    "patent_type",
    "ipc_codes",
]
_QUALITY_STATUS_LOOKUP: dict[str, tuple[str, str]] = {
    "professor": ("professor", "professor_id"),
    "paper": ("paper", "paper_id"),
    "company": ("company", "company_id"),
    "patent": ("patent", "patent_id"),
}
_PROFESSOR_DEFAULT_LIFECYCLE_STATE = "active"
_PROFESSOR_IDENTITY_QUERY_MARKERS = (
    "是谁",
    "什么人",
    "简介",
    "介绍",
    "主页",
    "邮箱",
    "联系方式",
    "任职",
    "职称",
    "在哪",
    "个人信息",
    "profile",
    "homepage",
    "email",
    "affiliation",
)
_PROFESSOR_RESEARCH_QUERY_MARKERS = (
    "研究",
    "方向",
    "领域",
    "课题",
    "专家",
    "找",
    "推荐",
    "做",
    "从事",
    "擅长",
    "论文",
    "专利",
    "技术",
    "算法",
    "模型",
    "智能",
    "机器人",
    "材料",
    "芯片",
    "expert",
    "research",
    "works on",
)
_PAPER_TITLE_EXACT_SCORE = 1.0
_PAPER_TITLE_EXACT_LIMIT = 5
_PAPER_TITLE_KEY_MIN_CHARS = 16
_PAPER_TITLE_KEY_MIN_TOKENS = 3
_PAPER_TITLE_PARTIAL_KEY_MIN_CHARS = 32
_PAPER_TITLE_PARTIAL_KEY_MIN_TOKENS = 5
_PAPER_TITLE_QUERY_SUFFIX_RE = re.compile(
    r"\s*(?:这篇|这份|该)?(?:论文|文章|paper)(?:的)?"
    r"(?:主要|大概|具体)?"
    r"(?:(?:讲|讲了|说|说明|介绍|研究|讨论|解决)"
    r"(?:了)?(?:什么|啥|哪些内容)?|是(?:什么|啥)|什么|介绍一下).*$",
    re.IGNORECASE,
)
_PAPER_TITLE_QUERY_PREFIX_RE = re.compile(
    r"^\s*(?:请问|帮我|查询|查一下)?\s*(?:论文|文章|paper)\s*[:：]?\s+",
    re.IGNORECASE,
)
_PAPER_TITLE_QUERY_ABSTRACT_SUFFIX_RE = re.compile(
    r"\s*(?:(?:这篇|这份|该)?(?:论文|文章|paper)(?:的)?)?"
    r"(?:的)?(?:中文)?(?:摘要|解读|总结)"
    r"(?:是(?:什么|啥))?[？?!.。！]*\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Evidence:
    object_type: str
    object_id: str
    score: float
    snippet: str
    source_url: str | None
    metadata: dict


@dataclass(frozen=True, slots=True)
class _SearchTarget:
    collection_name: str
    output_fields: list[str]
    anns_field: str | None = None
    professor_index: str | None = None


class RetrievalCache(Protocol):
    def get(
        self,
        query: str,
        domains: tuple[str, ...],
        filters_key: str,
    ) -> list[Evidence] | None: ...

    def set(
        self,
        query: str,
        domains: tuple[str, ...],
        filters_key: str,
        evidence: list[Evidence],
    ) -> None: ...


# --- Hybrid retrieval: lexical-coverage RRF fusion (vector-rerank + keywords) ---
# Pure functions so they are unit-testable independent of the live services.
_RRF_K = 60
_HYBRID_LEX_WEIGHT = 1.0  # equal weight to rerank rank and lexical rank by default
# Professor ready-boost: a `ready` professor's rerank-fusion term is multiplied by
# (1 + this). Counteracts loose matches from less-polished needs_review/needs_enrichment
# profiles admitted by the professor-decouple: when relevance is close (adjacent RRF
# ranks), prefer the better-embedded `ready` profile. Professor-only; gentle (tunable
# via the precision oracle). See make-professors-retrievable-beyond-ready design D3.
_PROFESSOR_READY_BOOST = 0.1
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{1,}")


def _cjk_runs(text: str) -> list[str]:
    """Return contiguous CJK runs of length >= 2 from ``text``."""
    runs: list[str] = []
    cur: list[str] = []
    for ch in text or "":
        if "一" <= ch <= "鿿":
            cur.append(ch)
        else:
            if len(cur) >= 2:
                runs.append("".join(cur))
            cur = []
    if len(cur) >= 2:
        runs.append("".join(cur))
    return runs


def _lexical_terms(text: str) -> set[str]:
    """Significant lexical terms: CJK char-bigrams (per run) + latin tokens (>=2 chars)."""
    terms: set[str] = set()
    for run in _cjk_runs(text):
        for i in range(len(run) - 1):
            terms.add(run[i : i + 2])
    for match in _LATIN_TOKEN_RE.findall(text or ""):
        terms.add(match.lower())
    return terms


def _lexical_coverage(query_terms: set[str], text: str) -> float:
    """Fraction of ``query_terms`` present in ``text``'s lexical terms (query coverage)."""
    if not query_terms:
        return 0.0
    text_terms = _lexical_terms(text)
    if not text_terms:
        return 0.0
    return len(query_terms & text_terms) / float(len(query_terms))


def _hybrid_rrf_select(
    query: str,
    candidates: list[Evidence],
    reranked,
    *,
    final_top_k: int,
    lex_weight: float = _HYBRID_LEX_WEIGHT,
) -> list[Evidence]:
    """Reciprocal Rank Fusion of rerank rank and lexical-coverage rank.

    Boosts candidates whose text overlaps the query's keywords, rescuing
    semantically-relevant rows the cross-encoder reranker ranks just outside top-k
    (e.g. broad-profile market leaders). Robust to score scales (uses ranks only).
    """
    n = len(candidates)
    rerank_rank: dict[int, int] = {}
    rerank_score_by_idx: dict[int, float] = {}
    for pos, item in enumerate(reranked):
        if 0 <= item.index < n:
            rerank_rank[item.index] = pos + 1
            rerank_score_by_idx[item.index] = item.score
    query_terms = _lexical_terms(query)
    lex_scored = sorted(
        ((i, _lexical_coverage(query_terms, candidates[i].snippet)) for i in range(n)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    lex_rank = {i: rank + 1 for rank, (i, _cov) in enumerate(lex_scored)}
    fused: list[tuple[float, int]] = []
    for i in range(n):
        rr = rerank_rank.get(i, n)
        lr = lex_rank.get(i, n)
        score = 1.0 / (_RRF_K + rr) + lex_weight / (_RRF_K + lr)
        if (
            candidates[i].object_type == "professor"
            and candidates[i].metadata.get("quality_status") == "ready"
        ):
            # ready-boost: prefer better-embedded ready profiles on near-ties.
            score += _PROFESSOR_READY_BOOST / (_RRF_K + rr)
        fused.append((score, i))
    fused.sort(key=lambda pair: pair[0], reverse=True)
    results: list[Evidence] = []
    for _score, i in fused[:final_top_k]:
        candidate = candidates[i]
        results.append(
            Evidence(
                object_type=candidate.object_type,
                object_id=candidate.object_id,
                score=rerank_score_by_idx.get(i, candidate.score),
                snippet=candidate.snippet,
                source_url=candidate.source_url,
                metadata=candidate.metadata,
            )
        )
    return results


class RetrievalService:
    def __init__(
        self,
        *,
        pg_conn_factory,
        milvus_client,
        embedding_client,
        reranker,
        cache: RetrievalCache | None = None,
        web_search_provider=None,
    ) -> None:
        self._pg_conn_factory = pg_conn_factory
        self._milvus_client = milvus_client
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._cache = cache
        self._web_search_provider = web_search_provider

    @staticmethod
    def _compute_filters_key(filters: dict | None) -> str:
        items = sorted((filters or {}).items(), key=lambda item: item[0])
        payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def retrieve(
        self,
        query: str,
        *,
        domains: tuple[str, ...],
        filters: dict | None = None,
        candidate_limit: int = 64,
        final_top_k: int = 10,
        filter_by_quality_status: bool | None = None,
        augment_with_web: bool = False,
        web_top_n: int = 5,
    ) -> list[Evidence]:
        unsupported_domains = tuple(
            domain for domain in domains if domain not in _VALID_DOMAINS
        )
        if unsupported_domains:
            logger.warning(
                "Unsupported retrieval domains skipped: %s",
                ", ".join(unsupported_domains),
            )
        domains = tuple(domain for domain in domains if domain in _VALID_DOMAINS)

        if filter_by_quality_status is None:
            filter_by_quality_status = (
                os.environ.get("FILTER_BY_QUALITY_STATUS", "1") != "0"
            )
        professor_lifecycle_state = (
            _PROFESSOR_DEFAULT_LIFECYCLE_STATE
            if "professor" in domains and not (filters and "lifecycle_state" in filters)
            else None
        )
        cache_filters = {
            **(filters or {}),
            "__quality_status_filter_enabled": filter_by_quality_status,
        }
        if professor_lifecycle_state is not None:
            cache_filters["__professor_lifecycle_state"] = professor_lifecycle_state
        filters_key = self._compute_filters_key(cache_filters)
        if self._cache is not None and not augment_with_web:
            cached = self._cache.get(query, domains, filters_key)
            if cached is not None:
                return cached

        if not domains:
            return []

        try:
            vectors = self._embedding_client.embed_batch([query])
        except Exception as exc:
            logger.warning("Embedding failed for retrieval query %r: %s", query, exc)
            return []

        with ThreadPoolExecutor(max_workers=len(domains)) as executor:
            futures: list[tuple[str, Future[list[dict]]]] = []
            for domain in domains:
                futures.append(
                    (
                        domain,
                        executor.submit(
                            self._search_domain,
                            domain=domain,
                            query=query,
                            vectors=vectors,
                            candidate_limit=candidate_limit,
                        ),
                    )
                )

            raw_rows_by_domain: list[tuple[str, list[dict]]] = []
            for domain, future in futures:
                try:
                    raw_rows_by_domain.append((domain, future.result()))
                except Exception as exc:
                    logger.warning("Retrieval search failed for domain %s: %s", domain, exc)

        candidates: list[Evidence] = []
        for domain, rows in raw_rows_by_domain:
            for row in rows:
                evidence = self._row_to_evidence(domain, row)
                if evidence is not None:
                    candidates.append(evidence)
        if "paper" in domains:
            candidates.extend(
                self._paper_title_exact_candidates(
                    query,
                    limit=max(_PAPER_TITLE_EXACT_LIMIT, min(candidate_limit, 10)),
                )
            )

        candidates = self._annotate_quality_status(
            candidates,
            filter_ready_only=filter_by_quality_status,
            professor_lifecycle_state=professor_lifecycle_state,
        )

        if filters:
            candidates = self._apply_filters(candidates, filters)

        if not candidates:
            return []

        try:
            reranked = self._reranker.rerank(
                query,
                [candidate.snippet for candidate in candidates],
                top_n=len(candidates),
            )
            results = _hybrid_rrf_select(
                query,
                candidates,
                reranked,
                final_top_k=final_top_k,
            )
        except Exception as exc:
            logger.warning("Rerank failed for retrieval query %r: %s", query, exc)
            results = sorted(
                candidates,
                key=lambda candidate: candidate.metadata.get("ann_score", candidate.score),
                reverse=True,
            )[:final_top_k]

        results = self._promote_exact_paper_title_matches(
            results,
            candidates,
            final_top_k=final_top_k,
        )

        if augment_with_web and self._web_search_provider is not None:
            results = self._augment_with_web(query, results, web_top_n=web_top_n)
        elif self._cache is not None and results:
            self._cache.set(query, domains, filters_key, results)

        return results

    def _augment_with_web(
        self,
        query: str,
        results: list[Evidence],
        *,
        web_top_n: int,
    ) -> list[Evidence]:
        """Append web-search results as object_type='web' Evidence.

        Closes the FM1a coverage gap: surfaces entities/concepts absent from the local
        DB (e.g. well-known market leaders never ingested) so they become citable
        candidates. The chat layer renders object_type='web' as a cited source row.
        Best-effort: on web-search failure, returns local results unchanged.
        """
        if self._web_search_provider is None:
            return results
        try:
            payload = self._web_search_provider.search(query)
        except Exception as exc:  # noqa: BLE001 - web is best-effort augmentation
            logger.warning("Web search augmentation failed for %r: %s", query, exc)
            return results
        organic = payload.get("organic") or payload.get("results") or []
        existing_urls = {evidence.source_url for evidence in results if evidence.source_url}
        web_evidence: list[Evidence] = []
        for index, item in enumerate(organic):
            if len(web_evidence) >= web_top_n:
                break
            url = item.get("link") or item.get("url") or ""
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            if not (title or snippet):
                continue
            if url and url in existing_urls:
                continue
            existing_urls.add(url)
            web_evidence.append(
                Evidence(
                    object_type="web",
                    object_id=f"web-{index}",
                    source_url=url or None,
                    snippet=f"{title} {snippet}".strip(),
                    score=0.0,
                    metadata={"title": title, "source_kind": "web"},
                )
            )
        return results + web_evidence

    def get_object(
        self,
        *,
        domain: _Domain,
        object_id: str,
    ) -> dict | None:
        if not object_id or domain not in _VALID_DOMAINS:
            return None

        sql = self._object_sql(domain)
        with self._pg_connection() as conn:
            row = conn.execute(sql, (object_id,)).fetchone()
        return dict(row) if row else None

    def get_related_objects(
        self,
        *,
        source_domain: _Domain,
        source_id: str,
        target_domain: _Domain,
        limit: int = 50,
    ) -> list[dict]:
        if (
            not source_id
            or source_domain not in _VALID_DOMAINS
            or target_domain not in _VALID_DOMAINS
            or source_domain == target_domain
        ):
            return []

        clamped_limit = self._clamp_related_limit(limit)
        if clamped_limit <= 0:
            return []

        sql = self._related_sql(source_domain, target_domain)
        if sql is None:
            return []

        with self._pg_connection() as conn:
            rows = conn.execute(sql, (source_id, clamped_limit)).fetchall()
        return [dict(row) for row in rows]

    def _pg_connection(self):
        conn = self._pg_conn_factory()
        if hasattr(conn, "__enter__") and hasattr(conn, "__exit__"):
            return conn
        if hasattr(conn, "__next__"):
            return self._generator_connection(conn)
        return nullcontext(conn)

    @staticmethod
    @contextmanager
    def _generator_connection(conn_iter):
        try:
            conn = next(conn_iter)
            yield conn
        finally:
            close = getattr(conn_iter, "close", None)
            if close is not None:
                close()

    @staticmethod
    def _clamp_related_limit(limit: int) -> int:
        return min(max(int(limit), 0), _MAX_RELATED_LIMIT)

    def _object_sql(self, domain: str) -> str:
        if domain == "professor":
            return """
                SELECT *
                  FROM professor
                 WHERE professor_id = %s
                   AND identity_status = 'resolved'
                 LIMIT 1
            """
        if domain == "paper":
            return """
                SELECT *
                  FROM paper
                 WHERE paper_id = %s
                   AND COALESCE(identity_status, 'unverified') != 'rejected'
                   AND COALESCE(quality_status, 'needs_enrichment') != 'rejected'
                 LIMIT 1
            """
        if domain == "company":
            return """
                SELECT *
                  FROM company
                 WHERE company_id = %s
                   AND identity_status = 'resolved'
                 LIMIT 1
            """
        return """
            SELECT *
              FROM patent
             WHERE patent_id = %s
               AND COALESCE(status, '') != 'inactive'
             LIMIT 1
        """

    def _related_sql(self, source_domain: str, target_domain: str) -> str | None:
        query_map = {
            ("professor", "paper"): self._professor_papers_sql,
            ("paper", "professor"): self._paper_professors_sql,
            ("professor", "company"): self._professor_companies_sql,
            ("company", "professor"): self._company_professors_sql,
            ("professor", "patent"): self._professor_patents_sql,
            ("patent", "professor"): self._patent_professors_sql,
            ("company", "patent"): self._company_patents_sql,
            ("patent", "company"): self._patent_companies_sql,
        }
        builder = query_map.get((source_domain, target_domain))
        return builder() if builder else None

    def _professor_papers_sql(self) -> str:
        return """
            SELECT p.*,
                   ppl.link_status,
                   ppl.topic_consistency_score,
                   ppl.match_reason
              FROM professor_paper_link ppl
              JOIN paper p ON p.paper_id = ppl.paper_id
             WHERE ppl.professor_id = %s
               AND ppl.link_status = 'verified'
               AND COALESCE(p.identity_status, 'unverified') != 'rejected'
               AND COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'
             ORDER BY
                   ppl.topic_consistency_score DESC NULLS LAST,
                   p.citation_count DESC NULLS LAST,
                   p.year DESC NULLS LAST,
                   p.title_clean ASC
             LIMIT %s
        """

    def _paper_professors_sql(self) -> str:
        return """
            SELECT prof.*,
                   ppl.link_status,
                   ppl.topic_consistency_score,
                   ppl.match_reason
              FROM professor_paper_link ppl
              JOIN professor prof ON prof.professor_id = ppl.professor_id
             WHERE ppl.paper_id = %s
               AND ppl.link_status = 'verified'
               AND prof.identity_status = 'resolved'
             ORDER BY
                   ppl.topic_consistency_score DESC NULLS LAST,
                   prof.canonical_name ASC
             LIMIT %s
        """

    def _professor_companies_sql(self) -> str:
        return """
            SELECT c.*,
                   pcr.role_type,
                   pcr.link_status,
                   pcr.match_reason
              FROM professor_company_role pcr
              JOIN company c ON c.company_id = pcr.company_id
             WHERE pcr.professor_id = %s
               AND pcr.link_status IN ('verified', 'candidate')
               AND c.identity_status != 'inactive'
             ORDER BY c.canonical_name ASC
             LIMIT %s
        """

    def _company_professors_sql(self) -> str:
        return """
            SELECT prof.*,
                   pcr.role_type,
                   pcr.link_status,
                   pcr.match_reason
              FROM professor_company_role pcr
              JOIN professor prof ON prof.professor_id = pcr.professor_id
             WHERE pcr.company_id = %s
               AND pcr.link_status IN ('verified', 'candidate')
               AND prof.identity_status = 'resolved'
             ORDER BY prof.canonical_name ASC
             LIMIT %s
        """

    def _professor_patents_sql(self) -> str:
        return """
            SELECT patent.*,
                   ppl.link_role,
                   ppl.link_status,
                   ppl.match_reason
              FROM professor_patent_link ppl
              JOIN patent ON patent.patent_id = ppl.patent_id
             WHERE ppl.professor_id = %s
               AND ppl.link_status IN ('verified', 'candidate')
               AND COALESCE(patent.status, '') != 'inactive'
             ORDER BY patent.filing_date DESC NULLS LAST, patent.title_clean ASC
             LIMIT %s
        """

    def _patent_professors_sql(self) -> str:
        return """
            SELECT prof.*,
                   ppl.link_role,
                   ppl.link_status,
                   ppl.match_reason
              FROM professor_patent_link ppl
              JOIN professor prof ON prof.professor_id = ppl.professor_id
             WHERE ppl.patent_id = %s
               AND ppl.link_status IN ('verified', 'candidate')
               AND prof.identity_status = 'resolved'
             ORDER BY prof.canonical_name ASC
             LIMIT %s
        """

    def _company_patents_sql(self) -> str:
        return """
            SELECT patent.*,
                   cpl.link_role,
                   cpl.link_status,
                   cpl.match_reason
              FROM company_patent_link cpl
              JOIN patent ON patent.patent_id = cpl.patent_id
             WHERE cpl.company_id = %s
               AND cpl.link_status IN ('verified', 'candidate')
               AND COALESCE(patent.status, '') != 'inactive'
             ORDER BY patent.filing_date DESC NULLS LAST, patent.title_clean ASC
             LIMIT %s
        """

    def _patent_companies_sql(self) -> str:
        return """
            SELECT c.*,
                   cpl.link_role,
                   cpl.link_status,
                   cpl.match_reason
              FROM company_patent_link cpl
              JOIN company c ON c.company_id = cpl.company_id
             WHERE cpl.patent_id = %s
               AND cpl.link_status IN ('verified', 'candidate')
               AND c.identity_status != 'inactive'
             ORDER BY c.canonical_name ASC
             LIMIT %s
        """

    def _search_domain(
        self,
        *,
        domain: str,
        query: str,
        vectors: list[list[float]],
        candidate_limit: int,
    ) -> list[dict]:
        if domain == "professor":
            rows: list[dict] = []
            for target in self._professor_search_targets(query):
                rows.extend(
                    self._search_collection(
                        domain=domain,
                        target=target,
                        vectors=vectors,
                        candidate_limit=candidate_limit,
                    )
                )
            return rows

        return self._search_collection(
            domain=domain,
            target=self._domain_search_config(domain),
            vectors=vectors,
            candidate_limit=candidate_limit,
        )

    def _search_collection(
        self,
        *,
        domain: str,
        target: _SearchTarget,
        vectors: list[list[float]],
        candidate_limit: int,
    ) -> list[dict]:
        kwargs = {}
        if target.anns_field:
            kwargs["anns_field"] = target.anns_field
        try:
            response = self._milvus_client.search(
                collection_name=target.collection_name,
                data=vectors,
                limit=candidate_limit,
                output_fields=target.output_fields,
                **kwargs,
            )
        except Exception as exc:
            logger.warning(
                "Milvus search failed for domain %s collection %s: %s",
                domain,
                target.collection_name,
                exc,
            )
            return []

        if not response:
            return []
        first_query_rows = response[0]
        if not isinstance(first_query_rows, list):
            return []
        if domain != "professor":
            return first_query_rows

        annotated_rows: list[dict] = []
        for row in first_query_rows:
            if not isinstance(row, dict):
                continue
            annotated = dict(row)
            annotated["__collection_name"] = target.collection_name
            annotated["__professor_retrieval_index"] = target.professor_index
            annotated_rows.append(annotated)
        return annotated_rows

    def _row_to_evidence(self, domain: str, row: dict) -> Evidence | None:
        entity = dict(row.get("entity") or {})
        raw_score = float(row.get("distance", 0.0))

        if domain == "professor":
            object_id = str(entity.get("id") or row.get("id") or "")
            snippet = str(
                entity.get("research_text")
                or entity.get("identity_text")
                or entity.get("profile_summary")
                or entity.get("paper_summary")
                or entity.get("patent_summary")
                or ""
            )
            name = str(entity.get("name") or "")
            metadata = dict(entity)
            metadata["ann_score"] = raw_score
            collection_name = row.get("__collection_name")
            professor_index = row.get("__professor_retrieval_index")
            if collection_name:
                metadata["collection_name"] = collection_name
            if professor_index:
                metadata["professor_retrieval_index"] = professor_index
            return Evidence(
                object_type="professor",
                object_id=object_id,
                score=raw_score,
                snippet=snippet[:500] or name,
                source_url=entity.get("profile_url") or entity.get("homepage_url"),
                metadata=metadata,
            )

        if domain == "paper":
            object_id = str(entity.get("paper_id") or "")
            metadata = {
                "year": entity.get("year"),
                "venue": entity.get("venue"),
                "chunk_type": entity.get("chunk_type"),
                "chunk_id": entity.get("chunk_id") or row.get("id"),
                "ann_score": raw_score,
            }
            return Evidence(
                object_type="paper",
                object_id=object_id,
                score=raw_score,
                snippet=str(entity.get("content_text") or ""),
                source_url=None,
                metadata=metadata,
            )

        if domain == "company":
            object_id = str(entity.get("id") or "")
            name = str(entity.get("name") or "")
            snippet = str(
                entity.get("profile_summary")
                or entity.get("technology_route_summary")
                or entity.get("description")
                or name
            )[:1800]
            return Evidence(
                object_type="company",
                object_id=object_id,
                score=raw_score,
                snippet=snippet,
                source_url=None,
                metadata=dict(entity),
            )

        if domain == "patent":
            object_id = str(entity.get("id") or "")
            snippet = (
                str(entity.get("title") or "")
                + "\n"
                + str(entity.get("abstract") or "")[:500]
            )
            return Evidence(
                object_type="patent",
                object_id=object_id,
                score=raw_score,
                snippet=snippet,
                source_url=None,
                metadata=dict(entity),
            )

        return None

    def _paper_title_exact_candidates(self, query: str, *, limit: int) -> list[Evidence]:
        query_title = self._paper_title_query_text(query)
        title_key = self._paper_title_match_key(query_title)
        if title_key is None:
            return []
        query_tokens = self._paper_title_tokens(query_title)
        like_pattern = self._paper_title_like_pattern(query_title)
        if like_pattern is None:
            return []

        try:
            with self._pg_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT p.paper_id,
                           p.title_clean,
                           title_raw,
                           year,
                           venue,
                           abstract_clean,
                           summary_zh,
                           pft.abstract AS paper_full_text_abstract,
                           doi,
                           identity_status,
                           quality_status,
                           citation_count
                      FROM paper p
                      LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
                     WHERE p.paper_id IS NOT NULL
                       AND COALESCE(identity_status, 'unverified') != 'rejected'
                       AND COALESCE(quality_status, 'needs_enrichment') != 'rejected'
                       AND (
                            regexp_replace(lower(coalesce(title_clean, title_raw, '')), '\\s+', '', 'g') = %s
                            OR coalesce(title_clean, title_raw, '') ILIKE %s
                       )
                     ORDER BY
                           CASE
                             WHEN regexp_replace(lower(coalesce(title_clean, title_raw, '')), '\\s+', '', 'g') = %s
                             THEN 0
                             ELSE 1
                           END,
                           citation_count DESC NULLS LAST,
                           year DESC NULLS LAST,
                           p.paper_id ASC
                     LIMIT %s
                    """,
                    (title_key, like_pattern, title_key, max(1, int(limit))),
                ).fetchall()
        except Exception as exc:
            logger.warning("Paper title exact lookup failed for query %r: %s", query, exc)
            return []

        candidates: list[Evidence] = []
        for row in rows:
            row_dict = dict(row)
            if row_dict.get("identity_status") == "rejected":
                continue
            if row_dict.get("quality_status") == "rejected":
                continue
            title = str(row_dict.get("title_clean") or row_dict.get("title_raw") or "")
            candidate_key = self._paper_title_match_key(title)
            if not self._paper_title_key_matches_query(
                candidate_key,
                title_key,
                query_tokens=query_tokens,
            ):
                continue
            paper_id = str(row_dict.get("paper_id") or "")
            if not paper_id:
                continue
            snippet, snippet_source = self._paper_title_snippet(row_dict, title)
            candidates.append(
                Evidence(
                    object_type="paper",
                    object_id=paper_id,
                    score=_PAPER_TITLE_EXACT_SCORE,
                    snippet=snippet[:1800],
                    source_url=self._doi_url(row_dict.get("doi")),
                    metadata={
                        "year": row_dict.get("year"),
                        "venue": row_dict.get("venue"),
                        "chunk_type": "title",
                        "chunk_id": f"{paper_id}:title:exact",
                        "ann_score": _PAPER_TITLE_EXACT_SCORE,
                        "retrieval_source": "paper_title_exact",
                        "title_clean": title,
                        "snippet_source": snippet_source,
                        "quality_status": row_dict.get("quality_status"),
                        "citation_count": row_dict.get("citation_count"),
                    },
                )
            )
        candidates.sort(key=self._paper_title_candidate_rank, reverse=True)
        return candidates

    @classmethod
    def _promote_exact_paper_title_matches(
        cls,
        results: list[Evidence],
        candidates: list[Evidence],
        *,
        final_top_k: int,
    ) -> list[Evidence]:
        exact_matches = [
            candidate
            for candidate in candidates
            if candidate.object_type == "paper"
            and candidate.metadata.get("retrieval_source") == "paper_title_exact"
        ]
        if not exact_matches:
            return results

        promoted: list[Evidence] = []
        seen: set[tuple[str, str]] = set()
        for candidate in exact_matches + results:
            key = (candidate.object_type, candidate.object_id)
            if key in seen:
                continue
            seen.add(key)
            promoted.append(candidate)
            if len(promoted) >= final_top_k:
                break
        return promoted

    @classmethod
    def _paper_title_match_key(cls, value: str) -> str | None:
        cleaned = clean_paper_title(value)
        tokens = cls._paper_title_tokens(cleaned)
        key = "".join(tokens).casefold()
        if (
            len(key) < _PAPER_TITLE_KEY_MIN_CHARS
            or len(tokens) < _PAPER_TITLE_KEY_MIN_TOKENS
        ):
            return None
        return key

    @staticmethod
    def _paper_title_key_matches_query(
        candidate_key: str | None,
        query_key: str,
        *,
        query_tokens: list[str],
    ) -> bool:
        if candidate_key is None:
            return False
        if candidate_key == query_key:
            return True
        if (
            len(query_key) < _PAPER_TITLE_PARTIAL_KEY_MIN_CHARS
            or len(query_tokens) < _PAPER_TITLE_PARTIAL_KEY_MIN_TOKENS
        ):
            return False
        return len(candidate_key) > len(query_key) and query_key in candidate_key

    @staticmethod
    def _paper_title_query_text(value: str) -> str:
        cleaned = clean_paper_title(value)
        stripped = _PAPER_TITLE_QUERY_PREFIX_RE.sub("", cleaned, count=1).strip()
        stripped = _PAPER_TITLE_QUERY_ABSTRACT_SUFFIX_RE.sub("", stripped).strip()
        stripped = _PAPER_TITLE_QUERY_SUFFIX_RE.sub("", stripped).strip()
        return stripped or cleaned

    @classmethod
    def _paper_title_like_pattern(cls, value: str) -> str | None:
        tokens = cls._paper_title_tokens(clean_paper_title(value))
        if len(tokens) < _PAPER_TITLE_KEY_MIN_TOKENS:
            return None
        return "%" + "%".join(tokens) + "%"

    @staticmethod
    def _paper_title_tokens(value: str) -> list[str]:
        return re.findall(r"[^\W_]+", value, flags=re.UNICODE)

    @staticmethod
    def _paper_title_snippet(row: dict, title: str) -> tuple[str, str]:
        for source in ("summary_zh", "abstract_clean", "paper_full_text_abstract"):
            value = row.get(source)
            if isinstance(value, str) and value.strip():
                return value.strip(), source
        return title, "title"

    @staticmethod
    def _paper_title_candidate_rank(candidate: Evidence) -> tuple[int, int, int, int]:
        snippet_source = candidate.metadata.get("snippet_source")
        source_rank = {
            "summary_zh": 3,
            "abstract_clean": 2,
            "paper_full_text_abstract": 1,
        }.get(snippet_source, 0)
        quality_rank = 1 if candidate.metadata.get("quality_status") == "ready" else 0
        citation_count = candidate.metadata.get("citation_count")
        if not isinstance(citation_count, int):
            citation_count = -1
        year = candidate.metadata.get("year")
        if not isinstance(year, int):
            year = -1
        return (source_rank, quality_rank, citation_count, year)

    @staticmethod
    def _doi_url(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        doi = value.strip()
        if not doi:
            return None
        if doi.startswith("http://") or doi.startswith("https://"):
            return doi
        return f"https://doi.org/{doi}"

    def _domain_search_config(self, domain: str) -> _SearchTarget:
        if domain == "professor":
            return _SearchTarget(
                collection_name=_PROFESSOR_COLLECTION,
                output_fields=_PROFESSOR_OUTPUT_FIELDS,
                anns_field="profile_vector",
            )
        if domain == "paper":
            return _SearchTarget(
                collection_name=PAPER_CHUNKS_COLLECTION,
                output_fields=_PAPER_OUTPUT_FIELDS,
                anns_field="content_vector",
            )
        if domain == "company":
            return _SearchTarget(
                collection_name=COMPANY_PROFILES_COLLECTION,
                output_fields=_COMPANY_OUTPUT_FIELDS,
            )
        return _SearchTarget(
            collection_name=PATENT_PROFILES_COLLECTION,
            output_fields=_PATENT_OUTPUT_FIELDS,
        )

    def _professor_search_targets(self, query: str) -> tuple[_SearchTarget, ...]:
        intent = self._professor_query_intent(query)
        identity_target = _SearchTarget(
            collection_name=PROFESSOR_IDENTITY_PROFILES_COLLECTION,
            output_fields=_PROFESSOR_IDENTITY_OUTPUT_FIELDS,
            anns_field="identity_vector",
            professor_index=_PROFESSOR_IDENTITY_INDEX,
        )
        research_target = _SearchTarget(
            collection_name=PROFESSOR_RESEARCH_PROFILES_COLLECTION,
            output_fields=_PROFESSOR_RESEARCH_OUTPUT_FIELDS,
            anns_field="research_vector",
            professor_index=_PROFESSOR_RESEARCH_INDEX,
        )
        if intent == _PROFESSOR_IDENTITY_INDEX:
            return (identity_target,)
        if intent == _PROFESSOR_RESEARCH_INDEX:
            return (research_target,)
        return (identity_target, research_target)

    @classmethod
    def _professor_query_intent(cls, query: str) -> str:
        normalized = query.strip().lower()
        has_identity_signal = any(
            marker in normalized for marker in _PROFESSOR_IDENTITY_QUERY_MARKERS
        ) or cls._contains_named_professor_reference(query)
        has_research_signal = any(
            marker in normalized for marker in _PROFESSOR_RESEARCH_QUERY_MARKERS
        )

        if has_identity_signal and not has_research_signal:
            return _PROFESSOR_IDENTITY_INDEX
        if has_research_signal and not has_identity_signal:
            return _PROFESSOR_RESEARCH_INDEX
        return "ambiguous"

    @staticmethod
    def _contains_named_professor_reference(query: str) -> bool:
        professor_at = query.find("教授")
        if professor_at <= 0:
            return False

        prefix = query[:professor_at]
        chars: list[str] = []
        for char in reversed(prefix):
            if "\u4e00" <= char <= "\u9fff":
                chars.append(char)
                continue
            break
        candidate = "".join(reversed(chars))
        return 2 <= len(candidate) <= 4

    def _annotate_quality_status(
        self,
        candidates: list[Evidence],
        *,
        filter_ready_only: bool,
        professor_lifecycle_state: str | None,
    ) -> list[Evidence]:
        if not candidates:
            return []

        ids_by_domain: dict[str, set[str]] = {}
        for candidate in candidates:
            if candidate.object_type in _QUALITY_STATUS_LOOKUP and candidate.object_id:
                ids_by_domain.setdefault(candidate.object_type, set()).add(
                    candidate.object_id
                )

        statuses = self._fetch_quality_statuses(ids_by_domain)
        annotated: list[Evidence] = []
        for candidate in candidates:
            status_info = statuses.get((candidate.object_type, candidate.object_id), {})
            status = status_info.get("quality_status")
            if status == "rejected":
                continue
            if filter_ready_only and not self._filter_ready_only(
                candidate,
                status_info,
            ):
                continue
            if status is not None:
                candidate.metadata["quality_status"] = status
            if (
                candidate.object_type == "paper"
                and "paper_has_rich_text" in status_info
            ):
                candidate.metadata["paper_has_rich_text"] = status_info[
                    "paper_has_rich_text"
                ]
            if candidate.object_type == "professor":
                lifecycle_state = status_info.get(
                    "lifecycle_state", _PROFESSOR_DEFAULT_LIFECYCLE_STATE
                )
                if (
                    professor_lifecycle_state is not None
                    and lifecycle_state != professor_lifecycle_state
                ):
                    continue
                candidate.metadata["lifecycle_state"] = lifecycle_state
            annotated.append(candidate)
        return annotated

    def _fetch_quality_statuses(
        self,
        ids_by_domain: dict[str, set[str]],
    ) -> dict[tuple[str, str], dict[str, str | bool]]:
        statuses: dict[tuple[str, str], dict[str, str | bool]] = {}
        if not ids_by_domain:
            return statuses

        try:
            with self._pg_connection() as conn:
                for domain, object_ids in ids_by_domain.items():
                    if not object_ids:
                        continue
                    table_name, id_column = _QUALITY_STATUS_LOOKUP[domain]
                    sorted_ids = sorted(object_ids)
                    placeholders = ", ".join(["%s"] * len(sorted_ids))
                    if domain == "professor":
                        rows = conn.execute(
                            f"SELECT {id_column} AS object_id, "
                            "quality_status, "
                            "COALESCE(lifecycle_state, 'active') AS lifecycle_state "
                            f"FROM {table_name} "
                            f"WHERE {id_column} IN ({placeholders})",
                            tuple(sorted_ids),
                        ).fetchall()
                    elif domain == "paper":
                        rows = conn.execute(
                            "SELECT p.paper_id AS object_id, "
                            "p.quality_status, "
                            "(NULLIF(BTRIM(COALESCE(pft.abstract, '')), '') IS NOT NULL "
                            " OR NULLIF(BTRIM(COALESCE(pft.intro, '')), '') IS NOT NULL) "
                            "AS paper_has_rich_text "
                            "FROM paper p "
                            "LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id "
                            f"WHERE p.paper_id IN ({placeholders})",
                            tuple(sorted_ids),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT {id_column} AS object_id, quality_status "
                            f"FROM {table_name} WHERE {id_column} IN ({placeholders})",
                            tuple(sorted_ids),
                        ).fetchall()
                    for row in rows:
                        row_dict = dict(row)
                        object_id = row_dict.get("object_id")
                        status = row_dict.get("quality_status")
                        if object_id is not None and status is not None:
                            payload = {"quality_status": str(status)}
                            if domain == "paper":
                                payload["paper_has_rich_text"] = (
                                    row_dict.get("paper_has_rich_text") is True
                                )
                            lifecycle_state = row_dict.get("lifecycle_state")
                            if lifecycle_state is not None:
                                payload["lifecycle_state"] = str(lifecycle_state)
                            statuses[(domain, str(object_id))] = payload
        except Exception as exc:
            logger.warning("Failed to fetch retrieval quality_status values: %s", exc)
        return statuses

    @classmethod
    def _filter_ready_only(
        cls,
        candidate: Evidence,
        status_info: dict[str, str | bool],
    ) -> bool:
        status = status_info.get("quality_status")
        if status == "ready":
            return True
        if candidate.object_type == "professor":
            # Decouple professor retrievability from publication-completeness.
            # A professor is retrievable if it is a real identified entity.
            # quality_status (ready > needs_review > needs_enrichment) is a
            # RANKING signal (better profiles embed/rerank higher), not a
            # retrieval gate. Only low_confidence (non-person-name /
            # profile-blob / reader-artifact / missing-official-source) is
            # excluded — it is not a reliable entity. rejected/merged identity
            # are already excluded from the index.
            return status != "low_confidence"
        if cls._allow_non_ready_exact_paper(candidate):
            return True
        return cls._allow_non_ready_vector_paper(candidate, status_info)

    @staticmethod
    def _allow_non_ready_exact_paper(candidate: Evidence) -> bool:
        if candidate.object_type != "paper":
            return False
        if candidate.metadata.get("retrieval_source") != "paper_title_exact":
            return False
        return candidate.metadata.get("snippet_source") in {
            "summary_zh",
            "abstract_clean",
            "paper_full_text_abstract",
        }

    @staticmethod
    def _allow_non_ready_vector_paper(
        candidate: Evidence,
        status_info: dict[str, str | bool],
    ) -> bool:
        if candidate.object_type != "paper":
            return False
        if candidate.metadata.get("retrieval_source") == "paper_title_exact":
            return False
        if status_info.get("quality_status") != "partial":
            return False
        return status_info.get("paper_has_rich_text") is True

    def _apply_filters(
        self,
        candidates: list[Evidence],
        filters: dict,
    ) -> list[Evidence]:
        filtered = candidates
        for key, value in filters.items():
            filtered = [
                candidate
                for candidate in filtered
                if candidate.metadata.get(key) == value
            ]
        return filtered
