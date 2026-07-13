"""Persist typed release-scoped Professor, Company, Paper, and Patent projections.

Revision ID: C2_0009
Revises: C2_0008
Create Date: 2026-07-12
"""

from __future__ import annotations

import hashlib
from typing import Any, Final, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0009"
down_revision: Union[str, None] = "C2_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHA256_CHECK: Final = "VALUE ~ '^[0-9a-f]{64}$'"
DOMAIN_PROJECTION_MANIFEST_TABLE = ("knowledge", "domain_projection_manifest")
DOMAIN_INCLUSION_DECISION_TABLE = ("knowledge", "domain_inclusion_decision")
DOMAIN_INCLUSION_ASSERTION_TABLE = (
    "knowledge",
    "domain_inclusion_decision_assertion",
)
DOMAIN_PROJECTION_LINEAGE_TABLE = ("knowledge", "domain_projection_lineage")

DOMAIN_ROOT_TABLES = {
    "company": ("company", "current_projection"),
    "paper": ("paper", "current_projection"),
    "patent": ("patent", "current_projection"),
    "professor": ("professor", "current_projection"),
}

DOMAIN_SUBOBJECT_TABLES = {
    "company": {
        "business_scenario": ("company", "business_scenario"),
        "capability": ("company", "capability"),
        "financing_event": ("company", "financing_event"),
        "key_personnel": ("company", "key_personnel"),
        "personnel_education": ("company", "personnel_education"),
        "personnel_work_experience": (
            "company",
            "personnel_work_experience",
        ),
        "product": ("company", "product"),
        "public_update": ("company", "public_update"),
    },
    "paper": {
        "author": ("paper", "author"),
        "enrichment_provenance": ("paper", "enrichment_provenance"),
        "full_text": ("paper", "full_text"),
        "funding": ("paper", "funding"),
        "identifier": ("paper", "identifier"),
        "publication": ("paper", "publication"),
        "reference": ("paper", "reference"),
        "summary": ("paper", "summary"),
    },
    "patent": {
        "applicant": ("patent", "applicant"),
        "inventor": ("patent", "inventor"),
        "ipc_classification": ("patent", "ipc_classification"),
        "patent_milestone": ("patent", "patent_milestone"),
        "technical_summary": ("patent", "technical_summary"),
    },
    "professor": {
        "affiliation_history": ("professor", "affiliation_history"),
        "award": ("professor", "award"),
        "contact": ("professor", "contact"),
        "education_history": ("professor", "education_history"),
        "metric_snapshot": ("professor", "metric_snapshot"),
        "research_project": ("professor", "research_project"),
        "work_history": ("professor", "work_history"),
    },
}

# (value shape, nullable). Conditional PRD fields stay nullable; absence is not
# replaced with a placeholder. Complex lists hold stable typed-child IDs.
DOMAIN_FIELD_SPECS: dict[str, dict[str, tuple[str, bool]]] = {
    "company": {
        "aliases": ("text_list", True),
        "credit_code": ("text", True),
        "evidence": ("evidence_reference_list", False),
        "founded_at": ("date", True),
        "geography": ("named_reference", True),
        "id": ("text", False),
        "industry": ("named_reference", True),
        "industry_tags": ("named_reference_list", True),
        "key_personnel": ("text_list", True),
        "last_updated": ("aware_datetime", False),
        "latest_public_updates": ("text_list", True),
        "legal_representative": ("named_reference", True),
        "name": ("text", False),
        "normalized_name": ("text", False),
        "patent_count": ("integer", True),
        "product_description": ("text", True),
        "profile_summary": ("text", False),
        "quality_status": ("text", False),
        "registered_address": ("text", True),
        "registered_capital": ("money", True),
        "run_id": ("text", False),
        "team_description": ("text", True),
        "tech_tags": ("named_reference_list", True),
        "technology_route_summary": ("text", False),
        "website": ("text", True),
    },
    "paper": {
        "abstract": ("text", True),
        "arxiv_id": ("text", True),
        "authors": ("text_list", False),
        "citation_count": ("integer", True),
        "doi": ("text", True),
        "enrichment_sources": ("text_list", True),
        "evidence": ("evidence_reference_list", False),
        "fields_of_study": ("named_reference_list", True),
        "funders": ("text_list", True),
        "id": ("text", False),
        "keywords": ("text_list", True),
        "last_updated": ("aware_datetime", False),
        "license": ("text", True),
        "oa_status": ("text", True),
        "pdf_path": ("text", True),
        "professor_ids": ("text_list", True),
        "publication_date": ("date", True),
        "quality_status": ("text", False),
        "reference_count": ("integer", True),
        "run_id": ("text", False),
        "summary_text": ("text", True),
        "summary_zh": ("text", True),
        "title": ("text", False),
        "title_zh": ("text", True),
        "tldr": ("text", True),
        "venue": ("named_reference", False),
        "year": ("year", False),
    },
    "patent": {
        "abstract": ("text", True),
        "applicants": ("text_list", False),
        "company_ids": ("text_list", True),
        "evidence": ("evidence_reference_list", False),
        "filing_date": ("date", True),
        "grant_date": ("date", True),
        "id": ("text", False),
        "inventors": ("text_list", True),
        "ipc_codes": ("text_list", True),
        "last_updated": ("aware_datetime", False),
        "patent_number": ("text", True),
        "patent_type": ("text", True),
        "professor_ids": ("text_list", True),
        "publication_date": ("date", True),
        "quality_status": ("text", False),
        "run_id": ("text", False),
        "summary_text": ("text", False),
        "technology_effect": ("text", True),
        "title": ("text", False),
        "title_en": ("text", True),
    },
    "professor": {
        "aliases": ("text_list", True),
        "awards": ("text_list", True),
        "canonical_name_en": ("text", True),
        "canonical_name_zh": ("text", False),
        "citation_count": ("integer", True),
        "company_roles": ("relationship_reference_list", False),
        "department": ("named_reference", False),
        "email": ("text", False),
        "evidence": ("evidence_reference_list", False),
        "h_index": ("integer", True),
        "homepage": ("text", False),
        "id": ("text", False),
        "institution": ("text", False),
        "last_updated": ("aware_datetime", False),
        "lifecycle_state": ("text", True),
        "manual_override": ("object", True),
        "name": ("text", False),
        "office": ("text", True),
        "paper_count": ("integer", True),
        "paper_summary": ("text", False),
        "patent_ids": ("text_list", False),
        "patent_summary": ("text", False),
        "phone": ("text", True),
        "profile_summary": ("text", False),
        "projects": ("text_list", True),
        "quality_status": ("text", False),
        "research_directions": ("named_reference_list", False),
        "run_id": ("text", False),
        "title": ("text", False),
    },
}

DOMAIN_SUBOBJECT_MEMBER_SPECS: dict[str, dict[str, dict[str, tuple[str, bool]]]] = {
    "company": {
        "business_scenario": {
            "name": ("text", False),
            "description": ("text", False),
        },
        "capability": {
            "name": ("text", False),
            "description": ("text", False),
        },
        "financing_event": {
            "round": ("text", False),
            "amount": ("money", True),
            "investors": ("named_reference_list", True),
            "event_date": ("date", True),
        },
        "key_personnel": {
            "name": ("text", False),
            "role": ("text", False),
            "description": ("text", True),
        },
        "personnel_education": {
            "person": ("named_reference", False),
            "institution": ("named_reference", False),
            "degree": ("text", True),
            "field": ("text", True),
            "year": ("year", True),
        },
        "personnel_work_experience": {
            "person": ("named_reference", False),
            "organization": ("named_reference", False),
            "role": ("text", False),
            "start": ("date", True),
            "end": ("date", True),
        },
        "product": {
            "name": ("text", False),
            "description": ("text", True),
            "technology_tags": ("named_reference_list", True),
        },
        "public_update": {
            "headline": ("text", False),
            "source_url": ("text", False),
            "event_date": ("date", True),
            "summary": ("text", True),
        },
    },
    "paper": {
        "author": {
            "name": ("text", False),
            "author_order": ("integer", False),
            "orcid": ("text", True),
            "affiliations": ("named_reference_list", True),
        },
        "enrichment_provenance": {
            "provider": ("text", False),
            "fetched_at": ("aware_datetime", False),
            "source_record_id": ("text", False),
        },
        "full_text": {
            "content_sha256": ("sha256", False),
            "storage_reference": ("text", False),
            "source_url": ("text", True),
            "parser_version": ("text", False),
        },
        "funding": {
            "funder": ("named_reference", False),
            "grant_number": ("text", True),
        },
        "identifier": {
            "scheme": ("text", False),
            "value": ("text", False),
        },
        "publication": {
            "venue": ("named_reference", True),
            "publication_date": ("date", True),
            "year": ("year", False),
        },
        "reference": {
            "target_paper_id": ("text", True),
            "raw_citation": ("text", True),
        },
        "summary": {
            "language": ("text", False),
            "summary_kind": ("text", False),
            "content": ("text", False),
            "content_hash": ("sha256", False),
        },
    },
    "patent": {
        "applicant": {
            "name": ("text", False),
            "applicant_order": ("integer", False),
            "canonical_company_id": ("text", True),
        },
        "inventor": {
            "name": ("text", False),
            "inventor_order": ("integer", False),
            "affiliation": ("named_reference", True),
            "canonical_professor_id": ("text", True),
        },
        "ipc_classification": {
            "code": ("text", False),
            "version": ("text", False),
            "label": ("text", True),
        },
        "patent_milestone": {
            "kind": ("text", False),
            "date": ("date", False),
        },
        "technical_summary": {
            "summary_text": ("text", False),
            "technology_effect": ("text", True),
            "content_hash": ("sha256", False),
            "model_version": ("text", False),
        },
    },
    "professor": {
        "affiliation_history": {
            "institution": ("named_reference", False),
            "department": ("named_reference", True),
            "title": ("text", True),
        },
        "award": {
            "name": ("text", False),
            "issuer": ("named_reference", True),
            "date": ("date", True),
        },
        "contact": {
            "kind": ("text", False),
            "value": ("text", False),
            "public_source": ("evidence_reference", False),
        },
        "education_history": {
            "institution": ("named_reference", False),
            "degree": ("text", True),
            "field": ("text", True),
            "start": ("date", True),
            "end": ("date", True),
        },
        "metric_snapshot": {
            "provider": ("text", False),
            "h_index": ("integer", True),
            "citation_count": ("integer", True),
            "paper_count": ("integer", True),
        },
        "research_project": {
            "name": ("text", False),
            "funder": ("named_reference", True),
            "role": ("text", True),
        },
        "work_history": {
            "organization": ("named_reference", False),
            "role": ("text", False),
        },
    },
}

# The full-text artifact hash and the immutable projection-row hash are distinct.
SUBOBJECT_MEMBER_COLUMN_OVERRIDES = {
    ("paper", "full_text", "content_sha256"): "source_content_sha256",
}

APPEND_ONLY_TABLES = (
    DOMAIN_PROJECTION_MANIFEST_TABLE,
    DOMAIN_INCLUSION_DECISION_TABLE,
    DOMAIN_INCLUSION_ASSERTION_TABLE,
    *DOMAIN_ROOT_TABLES.values(),
    *(
        table
        for domain_tables in DOMAIN_SUBOBJECT_TABLES.values()
        for table in domain_tables.values()
    ),
    DOMAIN_PROJECTION_LINEAGE_TABLE,
)

DOMAIN_PROJECTION_LOCK_ORDER = tuple(sorted(APPEND_ONLY_TABLES))


def _constraint_name(prefix: str, schema: str, table: str, suffix: str) -> str:
    candidate = f"{prefix}_{schema}_{table}_{suffix}"
    if len(candidate) <= 63:
        return candidate
    digest = hashlib.sha256(candidate.encode()).hexdigest()[:10]
    return f"{candidate[:52]}_{digest}"


def _sha256_check(column: str) -> str:
    return SHA256_CHECK.replace("VALUE", _sql_identifier(column))


def _sql_identifier(value: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"unsafe static SQL identifier: {value!r}")
    return f'"{value}"'


def _column_type(shape: str) -> sa.types.TypeEngine[Any]:
    if shape == "text_list":
        return postgresql.ARRAY(sa.Text())
    if shape in {
        "evidence_reference",
        "evidence_reference_list",
        "money",
        "named_reference",
        "named_reference_list",
        "relationship_reference_list",
    }:
        return postgresql.JSONB(astext_type=sa.Text())
    if shape == "integer" or shape == "year":
        return sa.Integer()
    if shape == "date":
        return sa.Date()
    if shape == "aware_datetime":
        return sa.DateTime(timezone=True)
    if shape == "object":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.Text()


def _typed_column(name: str, shape: str, nullable: bool) -> sa.Column[Any]:
    return sa.Column(name, _column_type(shape), nullable=nullable)


def _shape_checks(
    *,
    schema: str,
    table: str,
    column: str,
    shape: str,
    nullable: bool,
) -> list[sa.CheckConstraint]:
    checks: list[sa.CheckConstraint] = []
    identifier = _sql_identifier(column)
    prefix = f"{identifier} IS NULL OR " if nullable else ""
    if shape == "text":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}btrim({identifier}) <> ''",
                name=_constraint_name("ck", schema, table, f"{column}_nonempty"),
            )
        )
    elif shape == "text_list":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}array_position({identifier}, NULL) IS NULL",
                name=_constraint_name("ck", schema, table, f"{column}_no_nulls"),
            )
        )
    elif shape == "integer":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}{identifier} >= 0",
                name=_constraint_name("ck", schema, table, f"{column}_nonnegative"),
            )
        )
    elif shape == "year":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}{identifier} BETWEEN 1000 AND 9999",
                name=_constraint_name("ck", schema, table, f"{column}_year"),
            )
        )
    elif shape == "object":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}jsonb_typeof({identifier}) = 'object'",
                name=_constraint_name("ck", schema, table, f"{column}_object"),
            )
        )
    elif shape == "sha256":
        checks.append(
            sa.CheckConstraint(
                f"{prefix}{_sha256_check(column)}",
                name=_constraint_name("ck", schema, table, f"{column}_sha256"),
            )
        )
    elif shape in {
        "evidence_reference",
        "evidence_reference_list",
        "money",
        "named_reference",
        "named_reference_list",
        "relationship_reference_list",
    }:
        function_by_shape = {
            "evidence_reference": "is_valid_projection_evidence_reference",
            "evidence_reference_list": "is_valid_projection_evidence_reference_list",
            "money": "is_valid_projection_money",
            "named_reference": "is_valid_projection_named_reference",
            "named_reference_list": "is_valid_projection_named_reference_list",
            "relationship_reference_list": (
                "is_valid_projection_relationship_reference_list"
            ),
        }
        function = function_by_shape[shape]
        checks.append(
            sa.CheckConstraint(
                f"{prefix}COALESCE(knowledge.{function}({identifier}), FALSE)",
                name=_constraint_name("ck", schema, table, f"{column}_shape"),
            )
        )
    return checks


def _create_complex_shape_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.is_projection_nonempty_json_string(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'string'
               AND btrim(value #>> '{}') <> ''
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_projection_string_array(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'array'
               AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(value) AS item
                    WHERE NOT knowledge.is_projection_nonempty_json_string(item)
               )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_named_reference(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'object'
               AND value ?& ARRAY['reference_id', 'name']
               AND value - 'reference_id' - 'name' = '{}'::jsonb
               AND knowledge.is_projection_nonempty_json_string(value->'reference_id')
               AND knowledge.is_projection_nonempty_json_string(value->'name')
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_named_reference_list(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'array'
               AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(value) AS item
                    WHERE NOT knowledge.is_valid_projection_named_reference(item)
               )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_money(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'object'
               AND value ? 'amount'
               AND value - 'amount' - 'currency' = '{}'::jsonb
               AND (
                    jsonb_typeof(value->'amount') = 'number'
                    OR (
                        jsonb_typeof(value->'amount') = 'string'
                        AND value->>'amount' ~ '^-?[0-9]+(?:\\.[0-9]+)?$'
                    )
               )
               AND (
                    NOT value ? 'currency'
                    OR jsonb_typeof(value->'currency') = 'null'
                    OR knowledge.is_projection_nonempty_json_string(value->'currency')
               )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_evidence_reference(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'object'
               AND value ?& ARRAY['assertion_id', 'decision_id', 'field_path', 'artifact_ids']
               AND value - 'assertion_id' - 'decision_id' - 'field_path' - 'artifact_ids' = '{}'::jsonb
               AND knowledge.is_projection_nonempty_json_string(value->'assertion_id')
               AND knowledge.is_projection_nonempty_json_string(value->'decision_id')
               AND knowledge.is_projection_nonempty_json_string(value->'field_path')
               AND knowledge.is_projection_string_array(value->'artifact_ids')
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_evidence_reference_list(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'array'
               AND jsonb_array_length(value) > 0
               AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(value) AS item
                    WHERE NOT knowledge.is_valid_projection_evidence_reference(item)
               )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_relationship_reference(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'object'
               AND value ?& ARRAY['relationship_id', 'relationship_type_id', 'target_canonical_identity_id']
               AND value - 'relationship_id' - 'relationship_type_id' - 'target_canonical_identity_id' = '{}'::jsonb
               AND knowledge.is_projection_nonempty_json_string(value->'relationship_id')
               AND knowledge.is_projection_nonempty_json_string(value->'relationship_type_id')
               AND knowledge.is_projection_nonempty_json_string(value->'target_canonical_identity_id')
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_projection_relationship_reference_list(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'array'
               AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(value) AS item
                    WHERE NOT knowledge.is_valid_projection_relationship_reference(item)
               )
        $$
        """
    )


def _drop_complex_shape_functions() -> None:
    for function in (
        "is_valid_projection_relationship_reference_list(jsonb)",
        "is_valid_projection_relationship_reference(jsonb)",
        "is_valid_projection_evidence_reference_list(jsonb)",
        "is_valid_projection_evidence_reference(jsonb)",
        "is_valid_projection_money(jsonb)",
        "is_valid_projection_named_reference_list(jsonb)",
        "is_valid_projection_named_reference(jsonb)",
        "is_projection_string_array(jsonb)",
        "is_projection_nonempty_json_string(jsonb)",
    ):
        op.execute(f"DROP FUNCTION knowledge.{function}")


def _install_append_only(schema: str, table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON "
        f"{schema}.{table} FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON {schema}.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )


def _drop_append_only(schema: str, table: str) -> None:
    op.execute(f"DROP TRIGGER trg_reject_truncate ON {schema}.{table}")
    op.execute(f"DROP TRIGGER trg_reject_mutation ON {schema}.{table}")


def _add_parent_uniqueness() -> None:
    op.create_unique_constraint(
        "uq_knowledge_release_domain_projection_build",
        "release",
        ["release_id", "build_run_id"],
        schema="knowledge",
    )
    op.create_unique_constraint(
        "uq_knowledge_canonical_identity_domain_projection_type",
        "canonical_identity",
        ["release_id", "canonical_identity_id", "entity_type"],
        schema="knowledge",
    )
    op.create_unique_constraint(
        "uq_knowledge_canonical_identity_domain_projection_decision",
        "canonical_identity",
        [
            "release_id",
            "canonical_identity_id",
            "entity_type",
            "identity_decision_id",
        ],
        schema="knowledge",
    )
    op.create_unique_constraint(
        "uq_knowledge_canonical_decision_domain_projection_lineage",
        "canonical_decision",
        ["release_id", "decision_id", "canonical_identity_id", "field_path"],
        schema="knowledge",
    )
    op.create_unique_constraint(
        "uq_knowledge_policy_domain_projection_kind",
        "policy",
        ["policy_id", "policy_version", "policy_kind"],
        schema="knowledge",
    )


def _drop_parent_uniqueness() -> None:
    op.drop_constraint(
        "uq_knowledge_policy_domain_projection_kind",
        "policy",
        schema="knowledge",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_canonical_decision_domain_projection_lineage",
        "canonical_decision",
        schema="knowledge",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_canonical_identity_domain_projection_decision",
        "canonical_identity",
        schema="knowledge",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_canonical_identity_domain_projection_type",
        "canonical_identity",
        schema="knowledge",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_release_domain_projection_build",
        "release",
        schema="knowledge",
        type_="unique",
    )


def _create_manifest_table() -> None:
    schema, table = DOMAIN_PROJECTION_MANIFEST_TABLE
    op.create_table(
        table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("projection_version", sa.Text(), nullable=False),
        sa.Column("catalog_schema_version", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("catalog_content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "inclusion_result_content_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "approved_source_scope_manifest_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("inclusion_decision_run_id", sa.Text(), nullable=False),
        sa.Column(
            "inclusion_evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("manifest_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "root_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "subobject_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "projection_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "rejected_projections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id", name="pk_knowledge_domain_projection_manifest"
        ),
        sa.UniqueConstraint(
            "release_id",
            "manifest_content_sha256",
            name="uq_knowledge_domain_projection_manifest_identity",
        ),
        sa.UniqueConstraint(
            "release_id",
            "inclusion_result_content_sha256",
            name="uq_knowledge_domain_projection_manifest_inclusion_result",
        ),
        sa.UniqueConstraint(
            "release_id",
            "inclusion_result_content_sha256",
            "inclusion_decision_run_id",
            "inclusion_evaluated_at",
            name="uq_knowledge_domain_projection_manifest_inclusion_envelope",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "build_run_id"],
            ["knowledge.release.release_id", "knowledge.release.build_run_id"],
            name="fk_knowledge_domain_projection_manifest_release",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("catalog_content_sha256"),
            name="ck_knowledge_domain_projection_manifest_catalog_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_content_sha256"),
            name="ck_knowledge_domain_projection_manifest_content_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("inclusion_result_content_sha256"),
            name="ck_knowledge_domain_projection_manifest_inclusion_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("approved_source_scope_manifest_sha256"),
            name="ck_knowledge_domain_projection_manifest_source_scope_sha256",
        ),
        sa.CheckConstraint(
            "btrim(projection_version) <> '' AND "
            "btrim(catalog_schema_version) <> '' AND btrim(catalog_version) <> '' AND "
            "btrim(inclusion_decision_run_id) <> ''",
            name="ck_knowledge_domain_projection_manifest_versions",
        ),
        sa.CheckConstraint(
            "inclusion_evaluated_at <= as_of",
            name="ck_knowledge_domain_projection_manifest_inclusion_time",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(root_counts) = 'object' AND "
            "jsonb_typeof(subobject_counts) = 'object' AND "
            "jsonb_typeof(projection_hashes) = 'object' AND "
            "jsonb_typeof(rejected_projections) = 'array'",
            name="ck_knowledge_domain_projection_manifest_objects",
        ),
        schema=schema,
    )


def _create_inclusion_tables() -> None:
    schema, table = DOMAIN_INCLUSION_DECISION_TABLE
    op.create_table(
        table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("policy_kind", sa.Text(), nullable=False),
        sa.Column("inclusion_decision_run_id", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "limitations",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "hard_exclusion_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inclusion_result_content_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("manifest_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            name="pk_knowledge_domain_inclusion_decision",
        ),
        sa.UniqueConstraint(
            "release_id",
            "decision_id",
            "canonical_identity_id",
            "entity_type",
            "outcome",
            name="uq_knowledge_domain_inclusion_projection_binding",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "build_run_id"],
            ["knowledge.release.release_id", "knowledge.release.build_run_id"],
            name="fk_knowledge_domain_inclusion_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id", "entity_type"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
                "knowledge.canonical_identity.entity_type",
            ],
            name="fk_knowledge_domain_inclusion_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version", "policy_kind"],
            [
                "knowledge.policy.policy_id",
                "knowledge.policy.policy_version",
                "knowledge.policy.policy_kind",
            ],
            name="fk_knowledge_domain_inclusion_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "manifest_content_sha256"],
            [
                "knowledge.domain_projection_manifest.release_id",
                "knowledge.domain_projection_manifest.manifest_content_sha256",
            ],
            name="fk_knowledge_domain_inclusion_manifest",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "release_id",
                "inclusion_result_content_sha256",
                "inclusion_decision_run_id",
                "evaluated_at",
            ],
            [
                "knowledge.domain_projection_manifest.release_id",
                "knowledge.domain_projection_manifest.inclusion_result_content_sha256",
                "knowledge.domain_projection_manifest.inclusion_decision_run_id",
                "knowledge.domain_projection_manifest.inclusion_evaluated_at",
            ],
            name="fk_knowledge_domain_inclusion_result",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "entity_type IN ('company', 'paper', 'patent', 'professor')",
            name="ck_knowledge_domain_inclusion_entity_type",
        ),
        sa.CheckConstraint(
            "policy_kind = 'inclusion'",
            name="ck_knowledge_domain_inclusion_policy_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('admitted', 'excluded', 'review')",
            name="ck_knowledge_domain_inclusion_outcome",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0.0 AND score <= 1.0)",
            name="ck_knowledge_domain_inclusion_score",
        ),
        sa.CheckConstraint(
            "array_position(limitations, NULL) IS NULL AND "
            "array_position(hard_exclusion_codes, NULL) IS NULL",
            name="ck_knowledge_domain_inclusion_arrays",
        ),
        sa.CheckConstraint(
            "(outcome = 'excluded' AND cardinality(hard_exclusion_codes) > 0) OR "
            "(outcome <> 'excluded' AND cardinality(hard_exclusion_codes) = 0)",
            name="ck_knowledge_domain_inclusion_exclusion",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_content_sha256"),
            name="ck_knowledge_domain_inclusion_manifest_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("inclusion_result_content_sha256"),
            name="ck_knowledge_domain_inclusion_result_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_domain_inclusion_content_sha256",
        ),
        schema=schema,
    )

    assertion_schema, assertion_table = DOMAIN_INCLUSION_ASSERTION_TABLE
    op.create_table(
        assertion_table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            name="pk_knowledge_domain_inclusion_decision_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.domain_inclusion_decision.release_id",
                "knowledge.domain_inclusion_decision.decision_id",
            ],
            name="fk_knowledge_domain_inclusion_assertion_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["knowledge.source_assertion.assertion_id"],
            name="fk_knowledge_domain_inclusion_assertion_source_assertion",
            ondelete="RESTRICT",
        ),
        schema=assertion_schema,
    )


def _create_inclusion_assertion_owner_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_domain_inclusion_assertion_owner()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            decision_identity_id text;
            decision_entity_type text;
            assertion_source_identity_id text;
            assertion_entity_type text;
        BEGIN
            SELECT decision.canonical_identity_id,
                   decision.entity_type,
                   assertion.source_identity_id,
                   assertion.subject_entity_type
            INTO decision_identity_id,
                 decision_entity_type,
                 assertion_source_identity_id,
                 assertion_entity_type
            FROM knowledge.domain_inclusion_decision AS decision
            JOIN knowledge.source_assertion AS assertion
              ON assertion.assertion_id = NEW.assertion_id
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'domain inclusion assertion has no exact decision/assertion pair'
                    USING ERRCODE = '23503';
            END IF;
            IF assertion_entity_type IS DISTINCT FROM decision_entity_type THEN
                RAISE EXCEPTION
                    'domain inclusion assertion entity type is cross-wired'
                    USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM knowledge.current_source_identity_assignment AS assignment
                WHERE assignment.release_id = NEW.release_id
                  AND assignment.source_identity_id = assertion_source_identity_id
                  AND assignment.canonical_identity_id = decision_identity_id
            ) THEN
                RAISE EXCEPTION
                    'domain inclusion assertion canonical owner is cross-wired'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_validate_domain_inclusion_assertion_owner "
        "BEFORE INSERT ON knowledge.domain_inclusion_decision_assertion "
        "FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.validate_domain_inclusion_assertion_owner()"
    )


def _drop_inclusion_assertion_owner_validator() -> None:
    op.execute(
        "DROP TRIGGER trg_validate_domain_inclusion_assertion_owner "
        "ON knowledge.domain_inclusion_decision_assertion"
    )
    op.execute("DROP FUNCTION knowledge.validate_domain_inclusion_assertion_owner()")


def _create_candidate_release_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_domain_projection_candidate_release()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            release_state text;
            release_build_run_id text;
            row_build_run_id text;
        BEGIN
            IF TG_TABLE_SCHEMA = 'knowledge'
               AND TG_TABLE_NAME = 'domain_inclusion_decision_assertion'
            THEN
                SELECT decision.build_run_id
                INTO row_build_run_id
                FROM knowledge.domain_inclusion_decision AS decision
                WHERE decision.release_id = NEW.release_id
                  AND decision.decision_id = NEW.decision_id;
            ELSE
                row_build_run_id := NEW.build_run_id;
            END IF;
            SELECT state, build_run_id
            INTO release_state, release_build_run_id
            FROM knowledge.release
            WHERE release_id = NEW.release_id;
            IF release_state IS DISTINCT FROM 'candidate'
               OR release_build_run_id IS DISTINCT FROM row_build_run_id
            THEN
                RAISE EXCEPTION
                    'typed domain projections require one exact candidate release/build'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def _install_candidate_release_validators() -> None:
    for schema, table in APPEND_ONLY_TABLES:
        op.execute(
            "CREATE TRIGGER trg_validate_domain_projection_candidate_release "
            f"BEFORE INSERT ON {schema}.{table} FOR EACH ROW "
            "EXECUTE FUNCTION knowledge.validate_domain_projection_candidate_release()"
        )


def _drop_candidate_release_validator() -> None:
    for schema, table in reversed(APPEND_ONLY_TABLES):
        op.execute(
            "DROP TRIGGER trg_validate_domain_projection_candidate_release "
            f"ON {schema}.{table}"
        )
    op.execute("DROP FUNCTION knowledge.validate_domain_projection_candidate_release()")


def _root_common_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("projection_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("identity_decision_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("inclusion_decision_id", sa.Text(), nullable=False),
        sa.Column("inclusion_outcome", sa.Text(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "quality_signals",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("projection_version", sa.Text(), nullable=False),
        sa.Column("catalog_schema_version", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("catalog_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _root_constraints(domain: str, schema: str, table: str) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint(
            "release_id",
            "canonical_identity_id",
            name=_constraint_name("pk", schema, table, "identity"),
        ),
        sa.UniqueConstraint(
            "release_id",
            "projection_id",
            name=_constraint_name("uq", schema, table, "projection"),
        ),
        sa.UniqueConstraint(
            "release_id",
            "projection_id",
            "canonical_identity_id",
            "entity_type",
            name=_constraint_name("uq", schema, table, "projection_identity"),
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "build_run_id"],
            ["knowledge.release.release_id", "knowledge.release.build_run_id"],
            name=_constraint_name("fk", schema, table, "release"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "release_id",
                "canonical_identity_id",
                "entity_type",
                "identity_decision_id",
            ],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
                "knowledge.canonical_identity.entity_type",
                "knowledge.canonical_identity.identity_decision_id",
            ],
            name=_constraint_name("fk", schema, table, "canonical_identity"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "release_id",
                "inclusion_decision_id",
                "canonical_identity_id",
                "entity_type",
                "inclusion_outcome",
            ],
            [
                "knowledge.domain_inclusion_decision.release_id",
                "knowledge.domain_inclusion_decision.decision_id",
                "knowledge.domain_inclusion_decision.canonical_identity_id",
                "knowledge.domain_inclusion_decision.entity_type",
                "knowledge.domain_inclusion_decision.outcome",
            ],
            name=_constraint_name("fk", schema, table, "inclusion_decision"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "manifest_content_sha256"],
            [
                "knowledge.domain_projection_manifest.release_id",
                "knowledge.domain_projection_manifest.manifest_content_sha256",
            ],
            name=_constraint_name("fk", schema, table, "manifest"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"entity_type = '{domain}'",
            name=_constraint_name("ck", schema, table, "entity_type"),
        ),
        sa.CheckConstraint(
            "inclusion_outcome = 'admitted'",
            name=_constraint_name("ck", schema, table, "inclusion_outcome"),
        ),
        sa.CheckConstraint(
            "id = canonical_identity_id",
            name=_constraint_name("ck", schema, table, "catalog_id"),
        ),
        sa.CheckConstraint(
            "run_id = build_run_id",
            name=_constraint_name("ck", schema, table, "catalog_run"),
        ),
        sa.CheckConstraint(
            "last_updated <= as_of",
            name=_constraint_name("ck", schema, table, "observation_time"),
        ),
        sa.CheckConstraint(
            "btrim(projection_id) <> '' AND btrim(display_name) <> '' AND "
            "btrim(projection_version) <> '' AND "
            "btrim(catalog_schema_version) <> '' AND btrim(catalog_version) <> ''",
            name=_constraint_name("ck", schema, table, "envelope_text"),
        ),
        sa.CheckConstraint(
            "array_position(quality_signals, NULL) IS NULL",
            name=_constraint_name("ck", schema, table, "quality_signals"),
        ),
        sa.CheckConstraint(
            _sha256_check("catalog_content_sha256"),
            name=_constraint_name("ck", schema, table, "catalog_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_content_sha256"),
            name=_constraint_name("ck", schema, table, "manifest_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name=_constraint_name("ck", schema, table, "content_sha256"),
        ),
    ]
    for field, (shape, nullable) in DOMAIN_FIELD_SPECS[domain].items():
        constraints.extend(
            _shape_checks(
                schema=schema,
                table=table,
                column=field,
                shape=shape,
                nullable=nullable,
            )
        )
    return constraints


def _create_root_table(domain: str) -> None:
    schema, table = DOMAIN_ROOT_TABLES[domain]
    field_columns = [
        _typed_column(field, shape, nullable)
        for field, (shape, nullable) in DOMAIN_FIELD_SPECS[domain].items()
    ]
    op.create_table(
        table,
        *_root_common_columns(),
        *field_columns,
        *_root_constraints(domain, schema, table),
        schema=schema,
    )


def _subobject_member_column(
    domain: str,
    subobject: str,
    member: str,
    shape: str,
    nullable: bool,
) -> sa.Column[Any]:
    column_name = SUBOBJECT_MEMBER_COLUMN_OVERRIDES.get(
        (domain, subobject, member), member
    )
    return _typed_column(column_name, shape, nullable)


def _subobject_constraints(
    domain: str,
    subobject: str,
    schema: str,
    table: str,
) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint(
            "release_id",
            "subobject_id",
            name=_constraint_name("pk", schema, table, "identity"),
        ),
        sa.UniqueConstraint(
            "release_id",
            "parent_projection_id",
            "subobject_type",
            "ordinal",
            name=_constraint_name("uq", schema, table, "parent_ordinal"),
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "build_run_id"],
            ["knowledge.release.release_id", "knowledge.release.build_run_id"],
            name=_constraint_name("fk", schema, table, "release"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "release_id",
                "parent_projection_id",
                "canonical_identity_id",
                "entity_type",
            ],
            [
                f"{domain}.current_projection.release_id",
                f"{domain}.current_projection.projection_id",
                f"{domain}.current_projection.canonical_identity_id",
                f"{domain}.current_projection.entity_type",
            ],
            name=_constraint_name("fk", schema, table, "parent_projection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "manifest_content_sha256"],
            [
                "knowledge.domain_projection_manifest.release_id",
                "knowledge.domain_projection_manifest.manifest_content_sha256",
            ],
            name=_constraint_name("fk", schema, table, "manifest"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"entity_type = '{domain}'",
            name=_constraint_name("ck", schema, table, "entity_type"),
        ),
        sa.CheckConstraint(
            f"subobject_type = '{subobject}'",
            name=_constraint_name("ck", schema, table, "subobject_type"),
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name=_constraint_name("ck", schema, table, "ordinal"),
        ),
        sa.CheckConstraint(
            "btrim(subobject_id) <> '' AND btrim(parent_projection_id) <> '' AND "
            "btrim(projection_version) <> '' AND "
            "btrim(catalog_schema_version) <> '' AND btrim(catalog_version) <> ''",
            name=_constraint_name("ck", schema, table, "envelope_text"),
        ),
        sa.CheckConstraint(
            "parent_canonical_identity_id = canonical_identity_id",
            name=_constraint_name("ck", schema, table, "parent_identity"),
        ),
        sa.CheckConstraint(
            "cardinality(supporting_assertion_ids) > 0 AND "
            "array_position(supporting_assertion_ids, NULL) IS NULL AND "
            "cardinality(decision_ids) > 0 AND "
            "array_position(decision_ids, NULL) IS NULL",
            name=_constraint_name("ck", schema, table, "lineage_arrays"),
        ),
        sa.CheckConstraint(
            "(validity_kind IS NULL AND valid_from IS NULL AND valid_to IS NULL) OR "
            "(validity_kind = 'date' AND (valid_from IS NOT NULL OR valid_to IS NOT NULL) "
            "AND (valid_from IS NULL OR knowledge.is_valid_temporal_value("
            "jsonb_build_object('precision', 'date', 'value', valid_from))) "
            "AND (valid_to IS NULL OR knowledge.is_valid_temporal_value("
            "jsonb_build_object('precision', 'date', 'value', valid_to)))) OR "
            "(validity_kind = 'instant' AND "
            "(valid_from IS NOT NULL OR valid_to IS NOT NULL) "
            "AND (valid_from IS NULL OR knowledge.is_valid_temporal_value("
            "jsonb_build_object('precision', 'instant', 'value', valid_from))) "
            "AND (valid_to IS NULL OR knowledge.is_valid_temporal_value("
            "jsonb_build_object('precision', 'instant', 'value', valid_to))))",
            name=_constraint_name("ck", schema, table, "validity_shape"),
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
            name=_constraint_name("ck", schema, table, "validity_order"),
        ),
        sa.CheckConstraint(
            _sha256_check("catalog_content_sha256"),
            name=_constraint_name("ck", schema, table, "catalog_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_content_sha256"),
            name=_constraint_name("ck", schema, table, "manifest_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name=_constraint_name("ck", schema, table, "content_sha256"),
        ),
        sa.CheckConstraint(
            _sha256_check("projection_content_sha256")
            + " AND projection_content_sha256 = content_sha256",
            name=_constraint_name("ck", schema, table, "projection_content_sha256"),
        ),
    ]
    for member, (shape, nullable) in DOMAIN_SUBOBJECT_MEMBER_SPECS[domain][
        subobject
    ].items():
        column_name = SUBOBJECT_MEMBER_COLUMN_OVERRIDES.get(
            (domain, subobject, member), member
        )
        constraints.extend(
            _shape_checks(
                schema=schema,
                table=table,
                column=column_name,
                shape=shape,
                nullable=nullable,
            )
        )
    member_names = DOMAIN_SUBOBJECT_MEMBER_SPECS[domain][subobject]
    for start, end in (("start", "end"),):
        if start in member_names and end in member_names:
            start_identifier = _sql_identifier(start)
            end_identifier = _sql_identifier(end)
            constraints.append(
                sa.CheckConstraint(
                    f"{start_identifier} IS NULL OR {end_identifier} IS NULL OR "
                    f"{start_identifier} <= {end_identifier}",
                    name=_constraint_name("ck", schema, table, f"{start}_{end}"),
                )
            )
    return constraints


def _subobject_reference_constraints(
    domain: str,
    subobject: str,
    schema: str,
    table: str,
) -> list[sa.ForeignKeyConstraint]:
    references: list[sa.ForeignKeyConstraint] = []
    if (domain, subobject) == ("paper", "enrichment_provenance"):
        references.append(
            sa.ForeignKeyConstraint(
                ["source_record_id"],
                ["landing.source_record.record_id"],
                name=_constraint_name("fk", schema, table, "source_record"),
                ondelete="RESTRICT",
            )
        )
    for column, suffix in (
        ("target_paper_id", "target_paper"),
        ("canonical_company_id", "canonical_company"),
        ("canonical_professor_id", "canonical_professor"),
    ):
        if column in DOMAIN_SUBOBJECT_MEMBER_SPECS[domain][subobject]:
            references.append(
                sa.ForeignKeyConstraint(
                    ["release_id", column],
                    [
                        "knowledge.canonical_identity.release_id",
                        "knowledge.canonical_identity.canonical_identity_id",
                    ],
                    name=_constraint_name("fk", schema, table, suffix),
                    ondelete="RESTRICT",
                )
            )
    return references


def _create_subobject_table(domain: str, subobject: str) -> None:
    schema, table = DOMAIN_SUBOBJECT_TABLES[domain][subobject]
    common_columns: list[sa.Column[Any]] = [
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("subobject_id", sa.Text(), nullable=False),
        sa.Column("parent_projection_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("parent_canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("subobject_type", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "supporting_assertion_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("decision_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.Text(), nullable=True),
        sa.Column("valid_to", sa.Text(), nullable=True),
        sa.Column("validity_kind", sa.Text(), nullable=True),
        sa.Column("projection_version", sa.Text(), nullable=False),
        sa.Column("catalog_schema_version", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("catalog_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]
    member_columns = [
        _subobject_member_column(
            domain,
            subobject,
            member,
            shape,
            nullable,
        )
        for member, (shape, nullable) in DOMAIN_SUBOBJECT_MEMBER_SPECS[domain][
            subobject
        ].items()
    ]
    op.create_table(
        table,
        *common_columns,
        *member_columns,
        *_subobject_constraints(domain, subobject, schema, table),
        *_subobject_reference_constraints(domain, subobject, schema, table),
        schema=schema,
    )


def _create_lineage_table() -> None:
    schema, table = DOMAIN_PROJECTION_LINEAGE_TABLE
    op.create_table(
        table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("lineage_id", sa.Text(), nullable=False),
        sa.Column("projection_id", sa.Text(), nullable=False),
        sa.Column("subobject_type", sa.Text(), nullable=True),
        sa.Column("subobject_id", sa.Text(), nullable=True),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column(
            "assertion_role",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'selected'"),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manifest_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "lineage_id",
            name="pk_knowledge_domain_projection_lineage",
        ),
        sa.UniqueConstraint(
            "release_id",
            "projection_id",
            "subobject_id",
            "field_path",
            "decision_id",
            "assertion_id",
            name="uq_knowledge_domain_projection_lineage_selection",
            postgresql_nulls_not_distinct=True,
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "build_run_id"],
            ["knowledge.release.release_id", "knowledge.release.build_run_id"],
            name="fk_knowledge_domain_projection_lineage_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id", "entity_type"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
                "knowledge.canonical_identity.entity_type",
            ],
            name="fk_knowledge_domain_projection_lineage_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "canonical_identity_id", "field_path"],
            [
                "knowledge.canonical_decision.release_id",
                "knowledge.canonical_decision.decision_id",
                "knowledge.canonical_decision.canonical_identity_id",
                "knowledge.canonical_decision.field_path",
            ],
            name="fk_knowledge_domain_projection_lineage_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "assertion_id", "assertion_role"],
            [
                "knowledge.canonical_decision_assertion.release_id",
                "knowledge.canonical_decision_assertion.decision_id",
                "knowledge.canonical_decision_assertion.assertion_id",
                "knowledge.canonical_decision_assertion.assertion_role",
            ],
            name="fk_knowledge_domain_projection_lineage_selected_assertion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["knowledge.source_assertion.assertion_id"],
            name="fk_knowledge_domain_projection_lineage_source_assertion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "manifest_content_sha256"],
            [
                "knowledge.domain_projection_manifest.release_id",
                "knowledge.domain_projection_manifest.manifest_content_sha256",
            ],
            name="fk_knowledge_domain_projection_lineage_manifest",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "entity_type IN ('company', 'paper', 'patent', 'professor')",
            name="ck_knowledge_domain_projection_lineage_entity_type",
        ),
        sa.CheckConstraint(
            "assertion_role = 'selected'",
            name="ck_knowledge_domain_projection_lineage_selected_role",
        ),
        sa.CheckConstraint(
            "(subobject_id IS NULL) = (subobject_type IS NULL)",
            name="ck_knowledge_domain_projection_lineage_subobject_pair",
        ),
        sa.CheckConstraint(
            "btrim(lineage_id) <> '' AND btrim(projection_id) <> '' AND "
            "btrim(field_path) <> ''",
            name="ck_knowledge_domain_projection_lineage_text",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_content_sha256"),
            name="ck_knowledge_domain_projection_lineage_manifest_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_domain_projection_lineage_content_sha256",
        ),
        schema=schema,
    )


def _create_projection_lineage_validator() -> None:
    allowed_pairs = " OR ".join(
        f"(NEW.entity_type = '{domain}' AND NEW.subobject_type = '{subobject}')"
        for domain, domain_tables in DOMAIN_SUBOBJECT_TABLES.items()
        for subobject in domain_tables
    )
    op.execute(
        f"""
        CREATE FUNCTION knowledge.validate_domain_projection_lineage_target()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            target_exists boolean;
        BEGIN
            IF NEW.entity_type NOT IN ('company', 'paper', 'patent', 'professor') THEN
                RAISE EXCEPTION 'domain projection lineage has an invalid entity type'
                    USING ERRCODE = '23514';
            END IF;
            EXECUTE format(
                'SELECT EXISTS (SELECT 1 FROM %I.current_projection '
                'WHERE release_id = $1 AND projection_id = $2 '
                'AND canonical_identity_id = $3 AND entity_type = $4)',
                NEW.entity_type
            ) INTO target_exists
            USING NEW.release_id, NEW.projection_id,
                  NEW.canonical_identity_id, NEW.entity_type;
            IF NOT target_exists THEN
                RAISE EXCEPTION 'domain projection lineage has no exact root projection'
                    USING ERRCODE = '23503';
            END IF;

            IF NEW.subobject_id IS NOT NULL THEN
                IF NEW.subobject_type IS NULL
                   OR NOT COALESCE(({allowed_pairs}), FALSE)
                THEN
                    RAISE EXCEPTION 'domain projection lineage has an invalid typed subobject'
                        USING ERRCODE = '23514';
                END IF;
                EXECUTE format(
                    'SELECT EXISTS (SELECT 1 FROM %I.%I '
                    'WHERE release_id = $1 AND subobject_id = $2 '
                    'AND parent_projection_id = $3 '
                    'AND canonical_identity_id = $4)',
                    NEW.entity_type,
                    NEW.subobject_type
                ) INTO target_exists
                USING NEW.release_id, NEW.subobject_id, NEW.projection_id,
                      NEW.canonical_identity_id;
                IF NOT target_exists THEN
                    RAISE EXCEPTION 'domain projection lineage has no exact typed subobject'
                        USING ERRCODE = '23503';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_validate_domain_projection_lineage_target "
        "BEFORE INSERT ON knowledge.domain_projection_lineage FOR EACH ROW "
        "EXECUTE FUNCTION knowledge.validate_domain_projection_lineage_target()"
    )


def _drop_projection_lineage_validator() -> None:
    op.execute(
        "DROP TRIGGER trg_validate_domain_projection_lineage_target "
        "ON knowledge.domain_projection_lineage"
    )
    op.execute("DROP FUNCTION knowledge.validate_domain_projection_lineage_target()")


def _create_identity_reference_validators() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.domain_projection_identity_exists(
            target_release_id text,
            target_identity_id text,
            target_entity_type text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        SET search_path = pg_catalog
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM knowledge.canonical_identity
                WHERE release_id = target_release_id
                  AND canonical_identity_id = target_identity_id
                  AND entity_type = target_entity_type
                  AND state = 'active'
            )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_domain_projection_root_references()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_TABLE_SCHEMA = 'paper' AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(
                    COALESCE(to_jsonb(NEW)->'professor_ids', '[]'::jsonb)
                ) AS value
                WHERE NOT knowledge.domain_projection_identity_exists(
                    NEW.release_id, value, 'professor')
            ) THEN
                RAISE EXCEPTION 'Paper professor_ids must reference active Professor identities'
                    USING ERRCODE = '23503';
            ELSIF TG_TABLE_SCHEMA = 'patent' AND (
                EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(
                        COALESCE(to_jsonb(NEW)->'company_ids', '[]'::jsonb)
                    ) AS value
                    WHERE NOT knowledge.domain_projection_identity_exists(
                        NEW.release_id, value, 'company')
                ) OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(
                        COALESCE(to_jsonb(NEW)->'professor_ids', '[]'::jsonb)
                    ) AS value
                    WHERE NOT knowledge.domain_projection_identity_exists(
                        NEW.release_id, value, 'professor')
                )
            ) THEN
                RAISE EXCEPTION 'Patent identity arrays contain a wrong-domain reference'
                    USING ERRCODE = '23503';
            ELSIF TG_TABLE_SCHEMA = 'professor' AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(
                    COALESCE(to_jsonb(NEW)->'patent_ids', '[]'::jsonb)
                ) AS value
                WHERE NOT knowledge.domain_projection_identity_exists(
                    NEW.release_id, value, 'patent')
            ) THEN
                RAISE EXCEPTION 'Professor patent_ids must reference active Patent identities'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for domain in ("paper", "patent", "professor"):
        op.execute(
            f"CREATE TRIGGER trg_validate_domain_projection_references "
            f"BEFORE INSERT ON {domain}.current_projection FOR EACH ROW "
            "EXECUTE FUNCTION knowledge.validate_domain_projection_root_references()"
        )

    op.execute(
        """
        CREATE FUNCTION knowledge.validate_domain_subobject_reference()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_TABLE_SCHEMA = 'paper' AND TG_TABLE_NAME = 'reference'
               AND to_jsonb(NEW)->>'target_paper_id' IS NOT NULL
               AND NOT knowledge.domain_projection_identity_exists(
                   NEW.release_id, to_jsonb(NEW)->>'target_paper_id', 'paper')
            THEN
                RAISE EXCEPTION 'Paper reference must target an active Paper identity'
                    USING ERRCODE = '23503';
            ELSIF TG_TABLE_SCHEMA = 'patent' AND TG_TABLE_NAME = 'applicant'
               AND to_jsonb(NEW)->>'canonical_company_id' IS NOT NULL
               AND NOT knowledge.domain_projection_identity_exists(
                   NEW.release_id, to_jsonb(NEW)->>'canonical_company_id', 'company')
            THEN
                RAISE EXCEPTION 'Patent applicant must target an active Company identity'
                    USING ERRCODE = '23503';
            ELSIF TG_TABLE_SCHEMA = 'patent' AND TG_TABLE_NAME = 'inventor'
               AND to_jsonb(NEW)->>'canonical_professor_id' IS NOT NULL
               AND NOT knowledge.domain_projection_identity_exists(
                   NEW.release_id, to_jsonb(NEW)->>'canonical_professor_id', 'professor')
            THEN
                RAISE EXCEPTION 'Patent inventor must target an active Professor identity'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for schema, table in (
        ("paper", "reference"),
        ("patent", "applicant"),
        ("patent", "inventor"),
    ):
        op.execute(
            f"CREATE TRIGGER trg_validate_domain_subobject_reference "
            f"BEFORE INSERT ON {schema}.{table} FOR EACH ROW "
            "EXECUTE FUNCTION knowledge.validate_domain_subobject_reference()"
        )


def _drop_identity_reference_validators() -> None:
    for schema, table in reversed(
        (
            ("paper", "reference"),
            ("patent", "applicant"),
            ("patent", "inventor"),
        )
    ):
        op.execute(
            f"DROP TRIGGER trg_validate_domain_subobject_reference ON {schema}.{table}"
        )
    op.execute("DROP FUNCTION knowledge.validate_domain_subobject_reference()")
    for domain in reversed(("paper", "patent", "professor")):
        op.execute(
            f"DROP TRIGGER trg_validate_domain_projection_references "
            f"ON {domain}.current_projection"
        )
    op.execute("DROP FUNCTION knowledge.validate_domain_projection_root_references()")
    op.execute(
        "DROP FUNCTION knowledge.domain_projection_identity_exists(text, text, text)"
    )


def _lock_and_refuse_populated_downgrade() -> None:
    tables = ", ".join(
        f'"{schema}"."{table}"' for schema, table in DOMAIN_PROJECTION_LOCK_ORDER
    )
    op.execute(f"LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE")
    predicates = " OR ".join(
        f'EXISTS (SELECT 1 FROM "{schema}"."{table}")'
        for schema, table in DOMAIN_PROJECTION_LOCK_ORDER
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0009 downgrade refuses to discard populated typed domain projection history'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )


def upgrade() -> None:
    _add_parent_uniqueness()
    _create_complex_shape_functions()
    _create_manifest_table()
    _create_candidate_release_validator()
    _create_inclusion_tables()
    _create_inclusion_assertion_owner_validator()
    for domain in sorted(DOMAIN_ROOT_TABLES):
        _create_root_table(domain)
    for domain in sorted(DOMAIN_SUBOBJECT_TABLES):
        for subobject in sorted(DOMAIN_SUBOBJECT_TABLES[domain]):
            _create_subobject_table(domain, subobject)
    _create_lineage_table()
    _create_projection_lineage_validator()
    _create_identity_reference_validators()
    _install_candidate_release_validators()
    for schema, table in APPEND_ONLY_TABLES:
        _install_append_only(schema, table)


def downgrade() -> None:
    _lock_and_refuse_populated_downgrade()
    for schema, table in reversed(APPEND_ONLY_TABLES):
        _drop_append_only(schema, table)
    _drop_identity_reference_validators()
    _drop_projection_lineage_validator()
    _drop_candidate_release_validator()
    _drop_inclusion_assertion_owner_validator()
    lineage_schema, lineage_table = DOMAIN_PROJECTION_LINEAGE_TABLE
    op.drop_table(lineage_table, schema=lineage_schema)
    for domain in reversed(sorted(DOMAIN_SUBOBJECT_TABLES)):
        for subobject in reversed(sorted(DOMAIN_SUBOBJECT_TABLES[domain])):
            schema, table = DOMAIN_SUBOBJECT_TABLES[domain][subobject]
            op.drop_table(table, schema=schema)
    for domain in reversed(sorted(DOMAIN_ROOT_TABLES)):
        schema, table = DOMAIN_ROOT_TABLES[domain]
        op.drop_table(table, schema=schema)
    assertion_schema, assertion_table = DOMAIN_INCLUSION_ASSERTION_TABLE
    op.drop_table(assertion_table, schema=assertion_schema)
    decision_schema, decision_table = DOMAIN_INCLUSION_DECISION_TABLE
    op.drop_table(decision_table, schema=decision_schema)
    manifest_schema, manifest_table = DOMAIN_PROJECTION_MANIFEST_TABLE
    op.drop_table(manifest_table, schema=manifest_schema)
    _drop_complex_shape_functions()
    _drop_parent_uniqueness()
