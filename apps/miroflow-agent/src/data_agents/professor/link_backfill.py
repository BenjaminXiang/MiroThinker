from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import UUID

from psycopg import Connection, errors

from src.data_agents.contracts import Evidence, ReleasedObject

logger = logging.getLogger(__name__)

RELATION_LINK_STATUSES = ["verified", "candidate", "rejected"]
RELATION_VERIFIED_BY = [
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
]
PROFESSOR_COMPANY_ROLE_TYPES = [
    "founder",
    "cofounder",
    "chief_scientist",
    "advisor",
    "board_member",
]
PROFESSOR_COMPANY_EVIDENCE_SOURCE_TYPES = [
    "company_official_site",
    "professor_official_profile",
    "trusted_media",
    "xlsx_team_with_explicit_role",
    "gov_registry",
]


@dataclass(frozen=True, slots=True)
class ProfessorCompanyRoleBackfill:
    professor_name: str
    company_name: str
    role: str
    source_url: str
    snippet: str | None = None
    confidence: float | None = None


def upsert_professor_company_role(
    conn: Connection,
    *,
    professor_id: str,
    company_id: str,
    role_type: str,
    evidence_source_type: str,
    evidence_url: str,
    match_reason: str,
    link_status: str = "candidate",
    evidence_page_id: UUID | str | None = None,
    source_ref: str | None = None,
    verified_by: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    is_current: bool | None = None,
) -> str:
    """Upsert by (professor_id, company_id, role_type); returns role_id."""
    evidence_url = _required_text(evidence_url, "evidence_url")
    match_reason = _required_text(match_reason, "match_reason")
    _validate_enum("role_type", role_type, PROFESSOR_COMPANY_ROLE_TYPES)
    _validate_enum(
        "evidence_source_type",
        evidence_source_type,
        PROFESSOR_COMPANY_EVIDENCE_SOURCE_TYPES,
    )
    _validate_enum("link_status", link_status, RELATION_LINK_STATUSES)
    if verified_by is not None:
        _validate_enum("verified_by", verified_by, RELATION_VERIFIED_BY)
    if link_status == "verified" and verified_by is None:
        raise ValueError("verified_by is required when link_status='verified'")

    row = conn.execute(
        """
        INSERT INTO professor_company_role (
            professor_id,
            company_id,
            role_type,
            link_status,
            evidence_source_type,
            evidence_url,
            evidence_page_id,
            match_reason,
            source_ref,
            verified_by,
            start_year,
            end_year,
            is_current,
            verified_at
        )
        VALUES (
            %(professor_id)s,
            %(company_id)s,
            %(role_type)s,
            %(link_status)s,
            %(evidence_source_type)s,
            %(evidence_url)s,
            %(evidence_page_id)s,
            %(match_reason)s,
            %(source_ref)s,
            %(verified_by)s,
            %(start_year)s,
            %(end_year)s,
            %(is_current)s,
            CASE WHEN %(link_status)s = 'verified' THEN now() ELSE NULL END
        )
        ON CONFLICT (professor_id, company_id, role_type) DO UPDATE
           SET link_status = EXCLUDED.link_status,
               evidence_source_type = EXCLUDED.evidence_source_type,
               evidence_url = EXCLUDED.evidence_url,
               evidence_page_id = EXCLUDED.evidence_page_id,
               match_reason = EXCLUDED.match_reason,
               source_ref = EXCLUDED.source_ref,
               verified_by = EXCLUDED.verified_by,
               start_year = EXCLUDED.start_year,
               end_year = EXCLUDED.end_year,
               is_current = EXCLUDED.is_current,
               verified_at = CASE
                   WHEN EXCLUDED.link_status = 'verified' THEN now()
                   ELSE NULL
               END,
               updated_at = now()
        RETURNING role_id
        """,
        {
            "professor_id": professor_id,
            "company_id": company_id,
            "role_type": role_type,
            "link_status": link_status,
            "evidence_source_type": evidence_source_type,
            "evidence_url": evidence_url,
            "evidence_page_id": evidence_page_id,
            "match_reason": match_reason,
            "source_ref": source_ref,
            "verified_by": verified_by,
            "start_year": start_year,
            "end_year": end_year,
            "is_current": is_current,
        },
    ).fetchone()
    if row is None:
        raise RuntimeError("professor_company_role upsert did not return role_id")
    return str(row["role_id"] if isinstance(row, dict) else row[0])


def safe_upsert_professor_company_role(
    conn: Connection,
    *,
    professor_id: str,
    company_id: str,
    role_type: str,
    evidence_source_type: str,
    evidence_url: str,
    match_reason: str,
    link_status: str = "candidate",
    evidence_page_id: UUID | str | None = None,
    source_ref: str | None = None,
    verified_by: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    is_current: bool | None = None,
    issue_details: dict[str, Any] | None = None,
) -> str | None:
    """Try the PG relation write; file pipeline_issue and continue on PG failure."""
    try:
        with conn.transaction():
            return upsert_professor_company_role(
                conn,
                professor_id=professor_id,
                company_id=company_id,
                role_type=role_type,
                link_status=link_status,
                evidence_source_type=evidence_source_type,
                evidence_url=evidence_url,
                evidence_page_id=evidence_page_id,
                match_reason=match_reason,
                source_ref=source_ref,
                verified_by=verified_by,
                start_year=start_year,
                end_year=end_year,
                is_current=is_current,
            )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Postgres professor_company_role write failed for %s -> %s: %s",
            professor_id,
            company_id,
            exc,
        )
        _file_pg_link_write_failed_issue(
            conn,
            professor_id=professor_id,
            company_id=company_id,
            role_type=role_type,
            error=exc,
            details=issue_details,
        )
        return None


def apply_professor_company_role_backfill(
    objects: list[ReleasedObject],
    *,
    paths: Iterable[Path],
    now: datetime | None = None,
    pg_conn: Connection | None = None,
    company_id_lookup: Mapping[str, str] | Callable[[str], str | None] | None = None,
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
        professor_name = _normalize_name(
            str(obj.core_facts.get("name") or obj.display_name)
        )
        items = by_professor.get(professor_name)
        if not items:
            enriched.append(obj)
            continue

        core_facts = dict(obj.core_facts)
        company_roles = [dict(role) for role in core_facts.get("company_roles", [])]
        existing_pairs = {
            (
                _normalize_name(str(role.get("company_name", ""))),
                _normalize_name(str(role.get("role", ""))),
            )
            for role in company_roles
        }
        evidence = list(obj.evidence)
        existing_urls = {item.source_url for item in evidence if item.source_url}

        for item in items:
            pair = (_normalize_name(item.company_name), _normalize_name(item.role))
            if pair not in existing_pairs:
                company_roles.append(
                    {"company_name": item.company_name, "role": item.role}
                )
                existing_pairs.add(pair)
            if pg_conn is not None:
                _safe_write_backfill_pg_link(
                    pg_conn,
                    professor_id=obj.id,
                    item=item,
                    company_id_lookup=company_id_lookup,
                )
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


def _safe_write_backfill_pg_link(
    conn: Connection,
    *,
    professor_id: str,
    item: ProfessorCompanyRoleBackfill,
    company_id_lookup: Mapping[str, str] | Callable[[str], str | None] | None,
) -> None:
    company_id = _resolve_company_id(item.company_name, company_id_lookup)
    role_type = _infer_role_type(item.role)
    if not company_id or role_type is None:
        return

    safe_upsert_professor_company_role(
        conn,
        professor_id=professor_id,
        company_id=company_id,
        role_type=role_type,
        link_status="candidate",
        evidence_source_type="trusted_media",
        evidence_url=item.source_url,
        match_reason=(
            f"backfill source mentions {item.company_name} role '{item.role}' "
            f"mapped to {role_type}"
        )[:200],
        source_ref=professor_id,
        issue_details={
            "company_name": item.company_name,
            "role": item.role,
            "source_url": item.source_url,
        },
    )


def _resolve_company_id(
    company_name: str,
    company_id_lookup: Mapping[str, str] | Callable[[str], str | None] | None,
) -> str | None:
    if company_id_lookup is None:
        return None
    if callable(company_id_lookup):
        return company_id_lookup(company_name)
    return company_id_lookup.get(company_name) or company_id_lookup.get(
        _normalize_name(company_name)
    )


def _infer_role_type(role: str) -> str | None:
    role = role.casefold().strip()
    if any(
        token in role
        for token in ("联合创始人", "co-founder", "cofounder", "co founder")
    ):
        return "cofounder"
    if any(
        token in role
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
        token in role
        for token in ("首席科学家", "chief scientist", "科学顾问首席", " cso")
    ):
        return "chief_scientist"
    if any(token in role for token in ("独立董事", "董事", "board member", "director")):
        return "board_member"
    if any(
        token in role
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


def _required_text(value: str, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _validate_enum(field_name: str, value: str, allowed: list[str]) -> None:
    if value not in allowed:
        allowed_text = ", ".join(allowed)
        raise ValueError(f"{field_name} must be one of: {allowed_text}")


def _file_pg_link_write_failed_issue(
    conn: Connection,
    *,
    professor_id: str,
    company_id: str,
    role_type: str,
    error: Exception,
    details: dict[str, Any] | None = None,
) -> None:
    evidence_snapshot = json.dumps(
        {
            "code": "pg_link_write_failed",
            "requested_stage": "cross_domain_link",
            "professor_id": professor_id,
            "company_id": company_id,
            "role_type": role_type,
            "error": str(error),
            "details": details or {},
        },
        ensure_ascii=False,
        default=str,
    )
    description = (
        "[pg_link_write_failed] "
        f"professor_company_role write failed for {professor_id} -> {company_id}"
    )

    try:
        _insert_pipeline_issue(
            conn,
            stage="cross_domain_link",
            description=description,
            evidence_snapshot=evidence_snapshot,
        )
    except errors.CheckViolation:
        _insert_pipeline_issue(
            conn,
            stage="data_quality_flag",
            description=description,
            evidence_snapshot=evidence_snapshot,
        )
    except Exception as issue_error:  # noqa: BLE001
        logger.warning(
            "Failed to file pg_link_write_failed pipeline_issue for %s -> %s: %s",
            professor_id,
            company_id,
            issue_error,
        )


def _insert_pipeline_issue(
    conn: Connection,
    *,
    stage: str,
    description: str,
    evidence_snapshot: str,
) -> None:
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                institution,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by
            )
            VALUES (%s, %s, %s, 'medium', %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                None,
                "cross_domain_link",
                stage,
                description,
                evidence_snapshot,
                "professor_company_role_writer",
            ),
        )
