from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.normalization import normalize_company_name


_LIST_FIELDS = (
    "capability_facets",
    "data_route_types",
    "real_data_methods",
    "synthetic_data_methods",
    "modality_tags",
    "application_scenarios",
    "movement_data_needs",
    "operation_data_needs",
)
_OPTIONAL_TEXT_FIELDS = (
    "founder_background",
    "data_route_summary",
)


@dataclass(frozen=True, slots=True)
class CompanyKnowledgeBackfill:
    company_name: str
    capability_facets: tuple[str, ...] = ()
    data_route_types: tuple[str, ...] = ()
    real_data_methods: tuple[str, ...] = ()
    synthetic_data_methods: tuple[str, ...] = ()
    modality_tags: tuple[str, ...] = ()
    application_scenarios: tuple[str, ...] = ()
    movement_data_needs: tuple[str, ...] = ()
    operation_data_needs: tuple[str, ...] = ()
    founder_background: str | None = None
    data_route_summary: str | None = None
    source_url: str | None = None
    snippet: str | None = None
    confidence: float | None = None
    source_file: str | None = None


def apply_company_knowledge_backfill(
    objects: list[ReleasedObject],
    *,
    paths: Iterable[Path],
    now: datetime | None = None,
) -> list[ReleasedObject]:
    backfills = _load_backfills(paths)
    if not backfills:
        return list(objects)

    current_time = now or datetime.now(timezone.utc)
    by_company: dict[str, list[CompanyKnowledgeBackfill]] = {}
    for item in backfills:
        by_company.setdefault(_normalize_company(item.company_name), []).append(item)

    enriched: list[ReleasedObject] = []
    for obj in objects:
        if obj.object_type != "company":
            enriched.append(obj)
            continue
        company_name = str(obj.core_facts.get("name") or obj.display_name)
        items = by_company.get(_normalize_company(company_name))
        if items is None:
            enriched.append(obj)
            continue

        core_facts = dict(obj.core_facts)
        for field in _LIST_FIELDS:
            existing = [str(value) for value in core_facts.get(field, []) if value]
            for item in items:
                existing = _merge_unique(existing, list(getattr(item, field)))
            if existing:
                core_facts[field] = existing
        for field in _OPTIONAL_TEXT_FIELDS:
            for item in items:
                value = getattr(item, field)
                if value:
                    core_facts[field] = value

        evidence = list(obj.evidence)
        seen_keys = {(item.source_type, item.source_url, item.source_file) for item in evidence}
        for item in items:
            evidence_item = _build_evidence(item=item, source_file_hint=item.source_file, fetched_at=current_time)
            key = (evidence_item.source_type, evidence_item.source_url, evidence_item.source_file)
            if key in seen_keys:
                continue
            evidence.append(evidence_item)
            seen_keys.add(key)
        enriched.append(
            obj.model_copy(
                update={
                    "core_facts": core_facts,
                    "evidence": evidence,
                    "last_updated": current_time,
                }
            )
        )
    return enriched


def _build_evidence(
    *,
    item: CompanyKnowledgeBackfill,
    source_file_hint: str | None,
    fetched_at: datetime,
) -> Evidence:
    if item.source_url:
        return Evidence(
            source_type="public_web",
            source_url=item.source_url,
            fetched_at=fetched_at,
            snippet=item.snippet,
            confidence=item.confidence,
        )
    return Evidence(
        source_type="manual_review",
        source_file=source_file_hint or "docs/source_backfills/company_knowledge_fields.jsonl",
        fetched_at=fetched_at,
        snippet=item.snippet,
        confidence=item.confidence,
    )


def _load_backfills(paths: Iterable[Path]) -> list[CompanyKnowledgeBackfill]:
    backfills: list[CompanyKnowledgeBackfill] = []
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            backfills.append(
                CompanyKnowledgeBackfill(
                    company_name=str(payload["company_name"]),
                    capability_facets=tuple(str(item) for item in payload.get("capability_facets", [])),
                    data_route_types=tuple(str(item) for item in payload.get("data_route_types", [])),
                    real_data_methods=tuple(str(item) for item in payload.get("real_data_methods", [])),
                    synthetic_data_methods=tuple(str(item) for item in payload.get("synthetic_data_methods", [])),
                    modality_tags=tuple(str(item) for item in payload.get("modality_tags", [])),
                    application_scenarios=tuple(str(item) for item in payload.get("application_scenarios", [])),
                    movement_data_needs=tuple(str(item) for item in payload.get("movement_data_needs", [])),
                    operation_data_needs=tuple(str(item) for item in payload.get("operation_data_needs", [])),
                    founder_background=payload.get("founder_background"),
                    data_route_summary=payload.get("data_route_summary"),
                    source_url=payload.get("source_url"),
                    snippet=payload.get("snippet"),
                    confidence=payload.get("confidence"),
                    source_file=str(path),
                )
            )
    return backfills


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    seen = {item.casefold().strip() for item in existing}
    merged = list(existing)
    for item in incoming:
        key = item.casefold().strip()
        if not key or key in seen:
            continue
        merged.append(item)
        seen.add(key)
    return merged


def _normalize_company(value: str) -> str:
    return normalize_company_name(value)
