from __future__ import annotations

from typing import Literal
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from src.data_agents.contracts import PatentRecord
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

from .release import record_to_patent_dict


CompanyPatentLinkRole = Literal["applicant", "assignee"]
CompanyPatentEvidenceSourceType = Literal[
    "patent_xlsx_applicant_exact_match",
    "patent_xlsx_applicant_normalized_match",
    "gov_registry",
    "company_official_site",
]
RelationLinkStatus = Literal["candidate", "verified", "rejected"]
RelationVerifiedBy = Literal[
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
]

_VALID_COMPANY_PATENT_LINK_ROLES = {"applicant", "assignee"}
_VALID_COMPANY_PATENT_EVIDENCE_SOURCE_TYPES = {
    "patent_xlsx_applicant_exact_match",
    "patent_xlsx_applicant_normalized_match",
    "gov_registry",
    "company_official_site",
}
_VALID_RELATION_LINK_STATUSES = {"candidate", "verified", "rejected"}
_VALID_RELATION_VERIFIED_BY = {
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
}
_VALID_SUMMARY_TEXT_METHODS = {"llm", "fallback_template"}


def upsert_patent(
    conn: Connection,
    *,
    record: PatentRecord,
    run_id: UUID | str,
) -> str:
    run_id = require_real_run_id(run_id, writer_name="upsert_patent")
    values = record_to_patent_dict(record)
    _validate_patent_values(values)

    row = conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            title_raw,
            title_en,
            applicants_raw,
            applicants_parsed,
            inventors_raw,
            inventors_parsed,
            filing_date,
            publication_date,
            grant_date,
            patent_type,
            status,
            abstract_clean,
            technology_effect,
            ipc_codes,
            summary_text,
            summary_text_method,
            identity_status,
            quality_status,
            run_id,
            first_seen_at,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (patent_id) DO UPDATE
           SET patent_number       = EXCLUDED.patent_number,
               title_clean         = EXCLUDED.title_clean,
               title_raw           = EXCLUDED.title_raw,
               title_en            = COALESCE(EXCLUDED.title_en, patent.title_en),
               applicants_raw      = EXCLUDED.applicants_raw,
               applicants_parsed   = EXCLUDED.applicants_parsed,
               inventors_raw       = EXCLUDED.inventors_raw,
               inventors_parsed    = EXCLUDED.inventors_parsed,
               filing_date         = COALESCE(EXCLUDED.filing_date, patent.filing_date),
               publication_date    = COALESCE(EXCLUDED.publication_date, patent.publication_date),
               grant_date          = COALESCE(EXCLUDED.grant_date, patent.grant_date),
               patent_type         = EXCLUDED.patent_type,
               status              = COALESCE(EXCLUDED.status, patent.status),
               abstract_clean      = COALESCE(EXCLUDED.abstract_clean, patent.abstract_clean),
               technology_effect   = COALESCE(EXCLUDED.technology_effect, patent.technology_effect),
               ipc_codes           = EXCLUDED.ipc_codes,
               summary_text        = EXCLUDED.summary_text,
               summary_text_method = EXCLUDED.summary_text_method,
               identity_status     = EXCLUDED.identity_status,
               quality_status      = EXCLUDED.quality_status,
               run_id              = EXCLUDED.run_id,
               updated_at          = EXCLUDED.updated_at
        RETURNING patent_id
        """,
        (
            values["patent_id"],
            values["patent_number"],
            values["title_clean"],
            values["title_raw"],
            values["title_en"],
            values["applicants_raw"],
            Jsonb(values["applicants_parsed"]),
            values["inventors_raw"],
            Jsonb(values["inventors_parsed"]),
            values["filing_date"],
            values["publication_date"],
            values["grant_date"],
            values["patent_type"],
            values["status"],
            values["abstract_clean"],
            values["technology_effect"],
            values["ipc_codes"],
            values["summary_text"],
            values["summary_text_method"],
            values["identity_status"],
            values["quality_status"],
            run_id,
            values["first_seen_at"],
            values["updated_at"],
        ),
    ).fetchone()
    return str(_row_value(row, "patent_id", 0))


def upsert_company_patent_link(
    conn: Connection,
    *,
    patent_id: str,
    company_id: str,
    evidence_source_type: CompanyPatentEvidenceSourceType,
    match_reason: str,
    link_role: CompanyPatentLinkRole = "applicant",
    link_status: RelationLinkStatus = "candidate",
    verified_by: RelationVerifiedBy | None = None,
) -> str:
    link_role = _require_value(
        "link_role",
        link_role,
        _VALID_COMPANY_PATENT_LINK_ROLES,
    )
    evidence_source_type = _require_value(
        "evidence_source_type",
        evidence_source_type,
        _VALID_COMPANY_PATENT_EVIDENCE_SOURCE_TYPES,
    )
    link_status = _require_value(
        "link_status",
        link_status,
        _VALID_RELATION_LINK_STATUSES,
    )
    if verified_by is not None:
        verified_by = _require_value(
            "verified_by",
            verified_by,
            _VALID_RELATION_VERIFIED_BY,
        )
    match_reason = match_reason.strip()
    if not match_reason:
        raise ValueError("match_reason must be non-empty")

    row = conn.execute(
        """
        INSERT INTO company_patent_link (
            company_id,
            patent_id,
            link_role,
            link_status,
            evidence_source_type,
            match_reason,
            verified_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, patent_id, link_role) DO UPDATE
           SET link_status          = EXCLUDED.link_status,
               evidence_source_type = EXCLUDED.evidence_source_type,
               match_reason         = EXCLUDED.match_reason,
               verified_by          = COALESCE(EXCLUDED.verified_by, company_patent_link.verified_by),
               updated_at           = now()
        RETURNING link_id
        """,
        (
            company_id,
            patent_id,
            link_role,
            link_status,
            evidence_source_type,
            match_reason,
            verified_by,
        ),
    ).fetchone()
    return str(_row_value(row, "link_id", 0))


def _validate_patent_values(values: dict[str, object]) -> None:
    if not str(values["patent_id"]).strip():
        raise ValueError("patent_id must be non-empty")
    if not str(values["title_clean"]).strip():
        raise ValueError("title_clean must be non-empty")
    summary_method = values["summary_text_method"]
    if summary_method not in _VALID_SUMMARY_TEXT_METHODS:
        raise ValueError(f"summary_text_method must be one of {_VALID_SUMMARY_TEXT_METHODS}")


def _require_value(name: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")
    return value


def _row_value(row: object, key: str, index: int) -> object:
    if row is None:
        raise RuntimeError(f"INSERT did not return {key}")
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]
