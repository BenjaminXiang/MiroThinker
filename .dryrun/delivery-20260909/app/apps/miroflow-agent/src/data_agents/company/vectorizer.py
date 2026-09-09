# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Embedding vectorizer for company profiles."""

from __future__ import annotations

import logging
import json
import warnings
from collections.abc import Mapping
from typing import Any

import httpx

from ..storage.milvus_collections import (
    COMPANY_PROFILES_COLLECTION,
    ensure_company_profiles_collection,
)

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_URL = "http://100.64.0.27:18005/v1"
_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-8B"
_VECTOR_DIM = 4096


class EmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_EMBEDDING_URL,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def embed_batch(
        self,
        texts: list[str],
        *,
        model: str = _DEFAULT_MODEL,
    ) -> list[list[float]]:
        if not texts:
            return []
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(trust_env=False, timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": model},
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
        results = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in results]


class CompanyVectorizer:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        milvus_uri: str,
        collection_name: str = COMPANY_PROFILES_COLLECTION,
    ) -> None:
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self._milvus_client = _create_milvus_client(milvus_uri)

    def ensure_collection(self) -> None:
        ensure_company_profiles_collection(self._milvus_client)

    def vectorize_and_upsert(self, companies: list[Mapping[str, Any]]) -> int:
        rows: list[Mapping[str, Any]] = []
        texts: list[str] = []
        for company in companies:
            company_id = str(company.get("company_id") or company.get("id") or "")
            name = str(company.get("canonical_name") or company.get("name") or "")
            text = _compose_company_text(company)
            if not company_id.strip() or not name.strip() or not text.strip():
                continue
            rows.append(company)
            texts.append(text[:3800])

        if not rows:
            return 0

        vectors = self.embedding_client.embed_batch(texts)
        payload = [
            _company_row_to_payload(row, vector)
            for row, vector in zip(rows, vectors, strict=False)
        ]
        if not payload:
            return 0

        self._milvus_client.upsert(
            collection_name=self.collection_name,
            data=payload,
        )
        return len(payload)

    def search_by_profile(self, query: str, *, limit: int = 10) -> list[str]:
        query_vector = self.embedding_client.embed_batch([query])[0]
        results = self._milvus_client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="profile_vector",
            limit=limit,
            output_fields=["id"],
        )
        return [str(row.get("id", "")) for row in (results[0] if results else [])]


def _compose_company_text(row: Mapping[str, Any]) -> str:
    name = str(row.get("canonical_name") or row.get("name") or "").strip()
    industry = str(row.get("industry") or "").strip()
    hq_city = str(row.get("hq_city") or "").strip()
    profile = str(row.get("profile_summary") or "").strip()
    tech_route = str(row.get("technology_route_summary") or "").strip()
    description = str(row.get("description") or "").strip()

    parts: list[str] = []
    header = name
    if industry or hq_city:
        chunks = [chunk for chunk in (industry, hq_city) if chunk]
        header = f"{name}，{'，'.join(chunks)}" if name else "，".join(chunks)
    if header:
        parts.append(header)

    narrative_chunks = [chunk for chunk in (profile, tech_route) if chunk]
    if narrative_chunks:
        parts.append(" ".join(narrative_chunks))
    elif description:
        parts.append(description[:1800])
    enrichment_text = _compose_company_enrichment_text(row)
    if enrichment_text:
        parts.append(enrichment_text)

    return "\n".join(parts)


def _company_row_to_payload(
    row: Mapping[str, Any],
    vector: list[float],
) -> dict[str, object]:
    return {
        "id": str(row.get("company_id") or row.get("id") or "")[:64],
        "name": str(row.get("canonical_name") or row.get("name") or "")[:256],
        "industry": str(row.get("industry") or "")[:128],
        "hq_city": str(row.get("hq_city") or "")[:64],
        "description": str(row.get("description") or "")[:2048],
        "profile_summary": _compose_company_profile_summary(row)[:2048],
        "technology_route_summary": str(
            row.get("technology_route_summary") or ""
        )[:2048],
        "profile_vector": vector,
    }


def _compose_company_profile_summary(row: Mapping[str, Any]) -> str:
    profile = str(row.get("profile_summary") or "").strip()
    enrichment = _compose_company_enrichment_text(row)
    return "\n".join(part for part in (profile, enrichment) if part)


def _compose_company_enrichment_text(row: Mapping[str, Any]) -> str:
    lines: list[str] = []
    product_parts: list[str] = []
    for item in _json_list(row.get("products_json"))[:5]:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or item.get("canonical_name") or "").strip()
        description = str(
            item.get("description") or item.get("short_description") or ""
        ).strip()
        if not name and not description:
            continue
        product_parts.append(f"{name} - {description}".strip(" -"))
        structured_parts = [
            str(item.get("product_category") or "").strip(),
            *_string_list(item.get("target_customers")),
            *_string_list(item.get("application_scenarios")),
            *_string_list(item.get("technical_tags")),
        ]
        structured_text = " ".join(part for part in structured_parts if part)
        if structured_text:
            product_parts.append(f"产品结构：{structured_text}")
    if product_parts:
        lines.append("产品/服务：" + "；".join(product_parts))

    scenario_parts: list[str] = []
    for item in _json_list(row.get("application_scenarios_json"))[:8]:
        if not isinstance(item, Mapping):
            continue
        scenario_text = " ".join(
            part
            for part in (
                str(item.get("scenario_name") or "").strip(),
                str(item.get("scenario_category") or "").strip(),
                str(item.get("target_customer") or "").strip(),
                str(item.get("description") or "").strip(),
            )
            if part
        )
        if scenario_text:
            scenario_parts.append(scenario_text)
    if scenario_parts:
        lines.append("应用场景：" + "；".join(scenario_parts))

    team_parts: list[str] = []
    for item in _json_list(row.get("team_members_json") or row.get("structured_team_members"))[:8]:
        if not isinstance(item, Mapping):
            continue
        team_text = " ".join(
            part
            for part in (
                str(item.get("name") or "").strip(),
                str(item.get("role") or "").strip(),
                str(item.get("background") or "").strip(),
                " ".join(_string_list(item.get("experience_highlights"))),
                str(item.get("relevance") or "").strip(),
            )
            if part
        )
        if team_text:
            team_parts.append(team_text)
    if team_parts:
        lines.append("团队：" + "；".join(team_parts))

    event_parts: list[str] = []
    for item in _json_list(row.get("recent_events_json"))[:5]:
        if not isinstance(item, Mapping):
            continue
        event_date = str(item.get("event_date") or "").strip()
        event_type = str(item.get("event_type") or "").strip()
        summary = str(item.get("summary") or item.get("event_summary") or "").strip()
        if not summary:
            continue
        normalized = item.get("normalized")
        normalized_text = _event_normalized_text(normalized)
        event_parts.append(
            " ".join(
                part
                for part in (event_date, event_type, summary, normalized_text)
                if part
            )
        )
    if event_parts:
        lines.append("最近动态：" + "；".join(event_parts))

    return "\n".join(lines)


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _event_normalized_text(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    parts: list[str] = []
    for key in ("round", "amount", "amount_raw", "amount_cny_wan"):
        text = str(value.get(key) or "").strip()
        if text:
            parts.append(text)
    parts.extend(_string_list(value.get("investors")))
    return " ".join(parts)


def _create_milvus_client(uri: str) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

        return MilvusClient(uri=uri)
