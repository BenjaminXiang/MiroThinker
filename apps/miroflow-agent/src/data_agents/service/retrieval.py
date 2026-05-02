from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager, nullcontext
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Protocol

from ..storage.milvus_collections import (
    COMPANY_PROFILES_COLLECTION,
    PAPER_CHUNKS_COLLECTION,
    PATENT_PROFILES_COLLECTION,
)

logger = logging.getLogger(__name__)

_VALID_DOMAINS = {"professor", "paper", "company", "patent"}
_Domain = Literal["professor", "paper", "company", "patent"]
_MAX_RELATED_LIMIT = 200
_PROFESSOR_COLLECTION = "professor_profiles"
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


@dataclass(frozen=True, slots=True)
class Evidence:
    object_type: str
    object_id: str
    score: float
    snippet: str
    source_url: str | None
    metadata: dict


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


class RetrievalService:
    def __init__(
        self,
        *,
        pg_conn_factory,
        milvus_client,
        embedding_client,
        reranker,
        cache: RetrievalCache | None = None,
    ) -> None:
        self._pg_conn_factory = pg_conn_factory
        self._milvus_client = milvus_client
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._cache = cache

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
        candidate_limit: int = 30,
        final_top_k: int = 10,
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

        filters_key = self._compute_filters_key(filters)
        if self._cache is not None:
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

        if filters:
            candidates = self._apply_filters(candidates, filters)

        if not candidates:
            return []

        try:
            reranked = self._reranker.rerank(
                query,
                [candidate.snippet for candidate in candidates],
                top_n=final_top_k,
            )
        except Exception as exc:
            logger.warning("Rerank failed for retrieval query %r: %s", query, exc)
            results = sorted(
                candidates,
                key=lambda candidate: candidate.metadata.get("ann_score", candidate.score),
                reverse=True,
            )[:final_top_k]
        else:
            results = []
            for item in reranked:
                if item.index < 0 or item.index >= len(candidates):
                    logger.warning("Reranker returned out-of-range index %s", item.index)
                    continue
                candidate = candidates[item.index]
                results.append(
                    Evidence(
                        object_type=candidate.object_type,
                        object_id=candidate.object_id,
                        score=item.score,
                        snippet=candidate.snippet,
                        source_url=candidate.source_url,
                        metadata=candidate.metadata,
                    )
                )

        if self._cache is not None and results:
            self._cache.set(query, domains, filters_key, results)

        return results

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
        vectors: list[list[float]],
        candidate_limit: int,
    ) -> list[dict]:
        collection_name, output_fields = self._domain_search_config(domain)
        try:
            response = self._milvus_client.search(
                collection_name=collection_name,
                data=vectors,
                limit=candidate_limit,
                output_fields=output_fields,
            )
        except Exception as exc:
            logger.warning("Milvus search failed for domain %s: %s", domain, exc)
            return []

        if not response:
            return []
        first_query_rows = response[0]
        if not isinstance(first_query_rows, list):
            return []
        return first_query_rows

    def _row_to_evidence(self, domain: str, row: dict) -> Evidence | None:
        entity = dict(row.get("entity") or {})
        raw_score = float(row.get("distance", 0.0))

        if domain == "professor":
            object_id = str(entity.get("id") or row.get("id") or "")
            profile_summary = str(entity.get("profile_summary") or "")
            name = str(entity.get("name") or "")
            metadata = dict(entity)
            return Evidence(
                object_type="professor",
                object_id=object_id,
                score=raw_score,
                snippet=profile_summary[:500] or name,
                source_url=entity.get("homepage_url"),
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
            )[:500]
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

    def _domain_search_config(self, domain: str) -> tuple[str, list[str]]:
        if domain == "professor":
            return _PROFESSOR_COLLECTION, _PROFESSOR_OUTPUT_FIELDS
        if domain == "paper":
            return PAPER_CHUNKS_COLLECTION, _PAPER_OUTPUT_FIELDS
        if domain == "company":
            return COMPANY_PROFILES_COLLECTION, _COMPANY_OUTPUT_FIELDS
        return PATENT_PROFILES_COLLECTION, _PATENT_OUTPUT_FIELDS

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
