from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.data_agents.contracts import Evidence, ReleasedObject


@dataclass(frozen=True, slots=True)
class ProfessorCompanyRoleBackfill:
    professor_name: str
    company_name: str
    role: str
    source_url: str
    snippet: str | None = None
    confidence: float | None = None


def apply_professor_company_role_backfill(
    objects: list[ReleasedObject],
    *,
    paths: Iterable[Path],
    now: datetime | None = None,
) -> list[ReleasedObject]:
    backfills = _load_backfills(paths)
    if not backfills:
        return list(objects)

    current_time = now or datetime.now(timezone.utc)
    by_professor: dict[str, list[ProfessorCompanyRoleBackfill]] = {}
    for item in backfills:
        by_professor.setdefault(_normalize_name(item.professor_name), []).append(item)

    enriched: list[ReleasedObject] = []
    for obj in objects:
        if obj.object_type != "professor":
            enriched.append(obj)
            continue
        professor_name = _normalize_name(str(obj.core_facts.get("name") or obj.display_name))
        items = by_professor.get(professor_name)
        if not items:
            enriched.append(obj)
            continue

        core_facts = dict(obj.core_facts)
        company_roles = [dict(role) for role in core_facts.get("company_roles", [])]
        existing_pairs = {
            (_normalize_name(str(role.get("company_name", ""))), _normalize_name(str(role.get("role", ""))))
            for role in company_roles
        }
        evidence = list(obj.evidence)
        existing_urls = {item.source_url for item in evidence if item.source_url}

        for item in items:
            pair = (_normalize_name(item.company_name), _normalize_name(item.role))
            if pair not in existing_pairs:
                company_roles.append({"company_name": item.company_name, "role": item.role})
                existing_pairs.add(pair)
            if item.source_url not in existing_urls:
                evidence.append(
                    Evidence(
                        source_type="public_web",
                        source_url=item.source_url,
                        fetched_at=current_time,
                        snippet=item.snippet,
                        confidence=item.confidence,
                    )
                )
                existing_urls.add(item.source_url)

        core_facts["company_roles"] = company_roles
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


def _load_backfills(paths: Iterable[Path]) -> list[ProfessorCompanyRoleBackfill]:
    backfills: list[ProfessorCompanyRoleBackfill] = []
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            backfills.append(
                ProfessorCompanyRoleBackfill(
                    professor_name=str(payload["professor_name"]),
                    company_name=str(payload["company_name"]),
                    role=str(payload["role"]),
                    source_url=str(payload["source_url"]),
                    snippet=payload.get("snippet"),
                    confidence=payload.get("confidence"),
                )
            )
    return backfills


def _normalize_name(value: str) -> str:
    return value.casefold().strip()
