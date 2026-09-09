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
from .link_backfill import safe_upsert_professor_company_role

logger = logging.getLogger(__name__)

_ROLE_TYPES = {"founder", "cofounder", "chief_scientist", "advisor", "board_member"}
_EVIDENCE_SOURCE_TYPES = {
    "company_official_site",
    "professor_official_profile",
    "trusted_media",
    "xlsx_team_with_explicit_role",
    "gov_registry",
}


def _normalize_company_lookup_name(name: str) -> str:
    normalized = (name or "").strip().replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\([^)]*\)", "", normalized).strip()
    normalized = normalized.replace(" ", "")
    for prefix in (
        "深圳市",
        "深圳",
        "上海市",
        "上海",
        "北京市",
        "北京",
        "广州市",
        "广州",
        "杭州市",
        "杭州",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    for suffix in (
        "股份有限公司",
        "有限责任公司",
        "集团有限公司",
        "有限公司",
        "股份公司",
        "集团",
        "公司",
    ):
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
            if candidate_normalized.startswith(
                query_normalized
            ) or query_normalized.startswith(candidate_normalized):
                return obj
    return None


def build_company_role_link_records(
    profile: Any,
    *,
    source_ref: str,
) -> list[dict[str, Any]]:
    """Build V005b professor_company_role dictionaries from an enriched profile."""
    professor_id = _professor_id_for_profile(profile, source_ref=source_ref)
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for company_link in _iter_company_links(profile):
        company_id = _clean_text(_get_attr(company_link, "company_id"))
        evidence_url = _clean_text(_get_attr(company_link, "evidence_url"))
        if not company_id or not evidence_url:
            continue

        role_text = _clean_text(_get_attr(company_link, "role"))
        company_name = _clean_text(_get_attr(company_link, "company_name"))
        role_type = _infer_role_type(
            role_text, company_name=company_name, profile=profile
        )
        if role_type not in _ROLE_TYPES:
            continue

        evidence_source_type = _infer_evidence_source_type(
            company_link,
            profile=profile,
            evidence_url=evidence_url,
            company_name=company_name,
        )
        if evidence_source_type not in _EVIDENCE_SOURCE_TYPES:
            continue

        match_reason = _build_match_reason(
            role_type=role_type,
            evidence_source_type=evidence_source_type,
            role_text=role_text,
            company_name=company_name,
            profile=profile,
        )
        if not match_reason:
            continue

        key = (company_id, role_type)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "professor_id": professor_id,
                "company_id": company_id,
                "role_type": role_type,
                "link_status": "candidate",
                "evidence_source_type": evidence_source_type,
                "evidence_url": evidence_url,
                "match_reason": match_reason,
                "source_ref": source_ref,
            }
        )
    return records


def write_bidirectional_link(
    store: SqliteReleasedObjectStore,
    professor_id: str,
    company_link: CompanyLink,
    *,
    pg_conn: Any | None = None,
    source_ref: str | None = None,
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
            r.get("company_name", "") if isinstance(r, dict) else "" for r in roles
        }
        if company_link.company_name not in existing_names:
            roles.append(company_link.model_dump(mode="json"))
            updated_facts = {**prof_obj.core_facts, "company_roles": roles}
            updated = prof_obj.model_copy(update={"core_facts": updated_facts})
            store.update_object(updated)
            logger.info(
                "Added company link %s -> %s (%s)",
                professor_id,
                company_link.company_name,
                company_link.role,
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
                    company_link.company_id,
                    professor_id,
                )

    if pg_conn is not None:
        record = _build_record_from_company_link(
            professor_id=professor_id,
            company_link=company_link,
            source_ref=source_ref or professor_id,
        )
        if record is not None:
            safe_upsert_professor_company_role(pg_conn, **record)


def _build_record_from_company_link(
    *,
    professor_id: str,
    company_link: CompanyLink,
    source_ref: str,
) -> dict[str, Any] | None:
    company_id = _clean_text(company_link.company_id)
    evidence_url = _clean_text(company_link.evidence_url)
    if not company_id or not evidence_url:
        return None

    role_type = _infer_role_type(company_link.role)
    if role_type not in _ROLE_TYPES:
        logger.warning(
            "Skipping professor-company PG link with unsupported role %r for %s -> %s",
            company_link.role,
            professor_id,
            company_id,
        )
        return None

    evidence_source_type = _infer_evidence_source_type(
        company_link,
        profile=None,
        evidence_url=evidence_url,
        company_name=company_link.company_name,
    )
    match_reason = _build_match_reason(
        role_type=role_type,
        evidence_source_type=evidence_source_type,
        role_text=company_link.role,
        company_name=company_link.company_name,
        profile=None,
    )
    return {
        "professor_id": professor_id,
        "company_id": company_id,
        "role_type": role_type,
        "link_status": "candidate",
        "evidence_source_type": evidence_source_type,
        "evidence_url": evidence_url,
        "match_reason": match_reason,
        "source_ref": source_ref,
    }


def _professor_id_for_profile(profile: Any, *, source_ref: str) -> str:
    existing = _clean_text(_get_attr(profile, "professor_id"))
    if existing:
        return existing
    return source_ref


def _iter_company_links(profile: Any) -> list[Any]:
    links = _get_attr(profile, "company_roles") or []
    return list(links) if isinstance(links, list) else []


def _infer_role_type(
    role_text: str,
    *,
    company_name: str = "",
    profile: Any | None = None,
) -> str | None:
    haystack = " ".join(
        part
        for part in [
            role_text,
            _company_bio_context(profile, company_name) if profile is not None else "",
        ]
        if part
    ).casefold()
    if not haystack:
        return None

    if any(
        token in haystack
        for token in ("联合创始人", "co-founder", "cofounder", "co founder")
    ):
        return "cofounder"
    if any(
        token in haystack
        for token in (
            "创始人",
            "发起人",
            "创办",
            "创立",
            "founder",
            "founded",
            "founding",
        )
    ):
        return "founder"
    if any(
        token in haystack
        for token in ("首席科学家", "chief scientist", "科学顾问首席", " cso")
    ):
        return "chief_scientist"
    if any(
        token in haystack for token in ("独立董事", "董事", "board member", "director")
    ):
        return "board_member"
    if any(
        token in haystack
        for token in (
            "技术顾问",
            "学术顾问",
            "顾问",
            "advisor",
            "adviser",
            "consultant",
        )
    ):
        return "advisor"
    return None


def _infer_evidence_source_type(
    company_link: Any,
    *,
    profile: Any | None,
    evidence_url: str,
    company_name: str,
) -> str:
    source = _clean_text(_get_attr(company_link, "source")).casefold()
    if "xlsx" in source or "team_raw" in source:
        return "xlsx_team_with_explicit_role"
    if source in {"company_domain", "company_official_site", "official_company_site"}:
        return "company_official_site"
    if source in {"trusted_media", "media", "news", "web_search"}:
        return "trusted_media"

    anchor = (
        _get_attr(profile, "official_anchor_profile") if profile is not None else None
    )
    anchor_url = _clean_text(_get_attr(anchor, "source_url"))
    profile_url = (
        _clean_text(_get_attr(profile, "profile_url")) if profile is not None else ""
    )
    if evidence_url and evidence_url in {anchor_url, profile_url}:
        return "professor_official_profile"
    if profile is not None and _company_bio_context(profile, company_name):
        return "professor_official_profile"
    return "trusted_media"


def _build_match_reason(
    *,
    role_type: str,
    evidence_source_type: str,
    role_text: str,
    company_name: str,
    profile: Any | None,
) -> str:
    role_fragment = role_text or role_type
    if evidence_source_type == "xlsx_team_with_explicit_role":
        reason = f"xlsx team_raw lists {company_name} role '{role_fragment}' mapped to {role_type}"
    elif evidence_source_type == "professor_official_profile":
        reason = f"professor profile bio mentions {company_name} role '{role_fragment}' mapped to {role_type}"
    elif evidence_source_type == "company_official_site":
        reason = (
            f"company official page lists role '{role_fragment}' mapped to {role_type}"
        )
    else:
        reason = f"{evidence_source_type} evidence lists {company_name} role '{role_fragment}' mapped to {role_type}"
    if profile is not None and evidence_source_type == "professor_official_profile":
        context = _company_bio_context(profile, company_name)
        if context:
            reason = f"{reason}; context='{context[:60]}'"
    return reason[:200].strip()


def _company_bio_context(profile: Any | None, company_name: str) -> str:
    if profile is None:
        return ""
    anchor = _get_attr(profile, "official_anchor_profile")
    parts = [
        _clean_text(_get_attr(anchor, "bio_text")),
        " ".join(str(item) for item in (_get_attr(anchor, "work_role_lines") or [])),
        _clean_text(_get_attr(profile, "profile_summary")),
        " ".join(
            str(item) for item in (_get_attr(profile, "academic_positions") or [])
        ),
    ]
    haystack = " ".join(part for part in parts if part)
    if not company_name:
        return haystack
    normalized_company = _normalize_company_lookup_name(company_name)
    if normalized_company and normalized_company in _normalize_company_lookup_name(
        haystack
    ):
        return haystack
    if company_name and company_name in haystack:
        return haystack
    return ""


def _get_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
