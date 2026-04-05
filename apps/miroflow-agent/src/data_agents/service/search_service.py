from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.data_agents.contracts import ReleasedObject
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


@dataclass(frozen=True, slots=True)
class SearchResponse:
    query: str
    query_type: str
    domains: tuple[str, ...]
    results: list[ReleasedObject]


class DataSearchService:
    def __init__(
        self,
        *,
        sql_store: SqliteReleasedObjectStore,
        vector_store: MilvusVectorStore,
    ) -> None:
        self.sql_store = sql_store
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        mode: str = "hybrid",
        limit: int = 10,
    ) -> SearchResponse:
        domains = _infer_domains(query)
        if not domains:
            return SearchResponse(
                query=query,
                query_type="F",
                domains=(),
                results=[],
            )
        query_type = "D" if len(domains) > 1 else "A"

        results: list[ReleasedObject] = []
        seen_ids: set[str] = set()
        for domain in domains:
            for item in self._search_domain(
                domain,
                query,
                filters=filters,
                mode=mode,
                limit=limit,
            ):
                if item.id in seen_ids:
                    continue
                seen_ids.add(item.id)
                results.append(item)
        return SearchResponse(
            query=query,
            query_type=query_type,
            domains=domains,
            results=results[:limit] if query_type == "A" else results,
        )

    def get_object(self, domain: str, object_id: str) -> ReleasedObject | None:
        return self.sql_store.get_object(domain, object_id)

    def get_related_objects(
        self,
        *,
        source_domain: str,
        source_id: str,
        target_domain: str,
        relation_type: str,
        limit: int = 20,
    ) -> list[ReleasedObject]:
        return self.sql_store.get_related_objects(
            source_domain=source_domain,
            source_id=source_id,
            target_domain=target_domain,
            relation_type=relation_type,
            limit=limit,
        )

    def _search_domain(
        self,
        domain: str,
        query: str,
        *,
        filters: dict[str, Any] | None,
        mode: str,
        limit: int,
    ) -> list[ReleasedObject]:
        if mode == "exact":
            return self.sql_store.search_domain(
                domain,
                query,
                filters=filters,
                mode=mode,
                limit=limit,
            )

        semantic_results = _load_semantic_results(
            sql_store=self.sql_store,
            vector_store=self.vector_store,
            domain=domain,
            query=query,
            filters=filters,
            limit=limit,
        )
        if mode == "semantic":
            return semantic_results

        exact_results = self.sql_store.search_domain(
            domain,
            query,
            filters=filters,
            mode="exact",
            limit=limit,
        )
        merged_results: list[ReleasedObject] = []
        seen_ids: set[str] = set()
        for item in [*exact_results, *semantic_results]:
            if item.id in seen_ids:
                continue
            seen_ids.add(item.id)
            merged_results.append(item)
            if len(merged_results) >= limit:
                break
        return merged_results


def _infer_domains(query: str) -> tuple[str, ...]:
    domains: list[str] = []
    if any(token in query for token in ("教授", "老师", "导师", "院系", "研究方向")):
        domains.append("professor")
    if any(token in query for token in ("企业", "公司", "厂商", "融资", "法人", "业务")):
        domains.append("company")
    if any(token in query for token in ("论文", "paper", "doi", "arxiv")):
        domains.append("paper")
    if any(token in query for token in ("专利", "发明人", "申请人", "专利号")):
        domains.append("patent")
    return tuple(dict.fromkeys(domains))


def _load_semantic_results(
    *,
    sql_store: SqliteReleasedObjectStore,
    vector_store: MilvusVectorStore,
    domain: str,
    query: str,
    filters: dict[str, Any] | None,
    limit: int,
) -> list[ReleasedObject]:
    semantic_ids = vector_store.search_domain(domain, query, limit=limit)
    results = [
        item
        for object_id in semantic_ids
        if (item := sql_store.get_object(domain, object_id)) is not None
    ]
    if not filters:
        return results
    return [
        item
        for item in results
        if all(item.core_facts.get(key) == value for key, value in filters.items())
    ]
