# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Cross-domain bidirectional linker — writes professor-company associations to store.

Reads current records, appends links avoiding duplicates, writes back.
"""
from __future__ import annotations

import re
import logging
from typing import Any

from src.data_agents.contracts import ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

from .cross_domain import CompanyLink

logger = logging.getLogger(__name__)


def _normalize_company_lookup_name(name: str) -> str:
    normalized = (name or "").strip().replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\([^)]*\)", "", normalized).strip()
    normalized = normalized.replace(" ", "")
    for prefix in ("深圳市", "深圳", "上海市", "上海", "北京市", "北京", "广州市", "广州", "杭州市", "杭州"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    for suffix in ("股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "股份公司", "集团", "公司"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.casefold()


def find_company_by_name(
    store: SqliteReleasedObjectStore,
    company_name: str,
) -> ReleasedObject | None:
    """Find a company in the store using the shared normalized-name semantics."""
    query_normalized = _normalize_company_lookup_name(company_name)
    if not query_normalized:
        return None

    objects = store.export_domain_objects("company")
    for obj in objects:
        candidates = [
            obj.display_name,
            str(obj.core_facts.get("name", "") or ""),
            str(obj.core_facts.get("normalized_name", "") or ""),
        ]
        for candidate in candidates:
            candidate_normalized = _normalize_company_lookup_name(candidate)
            if not candidate_normalized:
                continue
            if candidate_normalized == query_normalized:
                return obj
            if candidate_normalized.startswith(query_normalized) or query_normalized.startswith(candidate_normalized):
                return obj
    return None


def write_bidirectional_link(
    store: SqliteReleasedObjectStore,
    professor_id: str,
    company_link: CompanyLink,
) -> None:
    """Write professor-company link to both sides of the store.

    Professor side: append to core_facts.company_roles
    Company side: append professor_id to core_facts.professor_ids
    """
    # --- Professor side ---
    prof_obj = store.get_object("professor", professor_id)
    if prof_obj is not None:
        roles = list(prof_obj.core_facts.get("company_roles", []))
        # Check for duplicate by company_name
        existing_names = {
            r.get("company_name", "") if isinstance(r, dict) else ""
            for r in roles
        }
        if company_link.company_name not in existing_names:
            roles.append(company_link.model_dump(mode="json"))
            updated_facts = {**prof_obj.core_facts, "company_roles": roles}
            updated = prof_obj.model_copy(update={"core_facts": updated_facts})
            store.update_object(updated)
            logger.info(
                "Added company link %s -> %s (%s)",
                professor_id, company_link.company_name, company_link.role,
            )

    # --- Company side ---
    if company_link.company_id:
        company_obj = store.get_object("company", company_link.company_id)
        if company_obj is not None:
            prof_ids = list(company_obj.core_facts.get("professor_ids", []))
            if professor_id not in prof_ids:
                prof_ids.append(professor_id)
                updated_facts = {**company_obj.core_facts, "professor_ids": prof_ids}
                updated = company_obj.model_copy(update={"core_facts": updated_facts})
                store.update_object(updated)
                logger.info(
                    "Added professor link %s -> %s",
                    company_link.company_id, professor_id,
                )
