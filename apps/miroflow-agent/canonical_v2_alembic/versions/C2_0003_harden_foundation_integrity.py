"""Harden shared lineage, decision history, and append-only integrity.

Revision ID: C2_0003
Revises: C2_0002
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0003"
down_revision: Union[str, None] = "C2_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPEND_ONLY_TABLES = (
    ("landing", "evidence_artifact"),
    ("landing", "source_record"),
    ("landing", "source_error"),
    ("knowledge", "policy"),
    ("knowledge", "source_identity_record"),
    ("knowledge", "source_assertion"),
    ("knowledge", "identity_decision"),
    ("knowledge", "identity_decision_source_identity"),
    ("knowledge", "identity_decision_input"),
    ("knowledge", "identity_decision_output"),
    ("knowledge", "identity_decision_record"),
    ("knowledge", "canonical_decision"),
    ("knowledge", "canonical_decision_assertion"),
    ("knowledge", "relationship_type"),
    ("knowledge", "relationship_assertion"),
    ("knowledge", "relationship_decision"),
    ("knowledge", "relationship_decision_assertion"),
    ("publish", "build_manifest"),
    ("publish", "manifest_section"),
)

MUTABLE_HISTORY_TABLES = (
    (
        "landing",
        "parser_run",
        (
            "parse_run_id",
            "artifact_id",
            "parser_name",
            "parser_version",
            "schema_version",
            "started_at",
        ),
    ),
    (
        "knowledge",
        "source_identity",
        (
            "source_identity_id",
            "source_system",
            "source_key",
            "entity_type",
            "normalized_keys",
            "first_observed_at",
        ),
    ),
)

DECISION_LINEAGE = (
    (
        "identity_decision",
        "reversal_of_decision_id",
        "fk_knowledge_identity_decision_reversal",
        "uq_knowledge_identity_decision_id",
        "ck_knowledge_identity_decision_reversal_not_self",
        (),
        None,
    ),
    (
        "canonical_decision",
        "supersedes_decision_id",
        "fk_knowledge_canonical_decision_supersedes",
        "uq_knowledge_canonical_decision_id",
        "ck_knowledge_canonical_decision_supersedes_not_self",
        ("canonical_identity_id", "field_path"),
        "uq_knowledge_canonical_decision_lineage_subject",
    ),
    (
        "relationship_decision",
        "supersedes_decision_id",
        "fk_knowledge_relationship_decision_supersedes",
        "uq_knowledge_relationship_decision_id",
        "ck_knowledge_relationship_decision_supersedes_not_self",
        ("canonical_relationship_id",),
        "uq_knowledge_relationship_decision_lineage_subject",
    ),
)


def _llm_trace_check() -> str:
    required_keys = (
        "provider",
        "model",
        "prompt_version",
        "schema_version",
        "input_evidence_ids",
        "output_sha256",
    )
    keys = ", ".join(f"'{key}'" for key in required_keys)
    string_fields = (
        "provider",
        "model",
        "prompt_version",
        "schema_version",
    )
    string_checks = " AND ".join(
        f"jsonb_typeof(llm_trace->'{field}') = 'string' "
        f"AND length(llm_trace->>'{field}') > 0"
        for field in string_fields
    )
    return (
        "method <> 'structured_llm' OR ("
        "llm_trace IS NOT NULL AND jsonb_typeof(llm_trace) = 'object' AND "
        f"llm_trace ?& ARRAY[{keys}] AND {string_checks} AND "
        "jsonb_typeof(llm_trace->'input_evidence_ids') = 'array' AND "
        "jsonb_array_length(llm_trace->'input_evidence_ids') > 0 AND "
        "(llm_trace->>'output_sha256') ~ '^[0-9a-f]{64}$')"
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_landing_evidence_artifact_identity_hash",
        "evidence_artifact",
        ["artifact_id", "content_sha256"],
        schema="landing",
    )
    op.drop_constraint(
        "fk_landing_evidence_artifact_parent",
        "evidence_artifact",
        schema="landing",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_landing_evidence_artifact_parent",
        "evidence_artifact",
        "evidence_artifact",
        ["parent_artifact_id", "parent_content_sha256"],
        ["artifact_id", "content_sha256"],
        source_schema="landing",
        referent_schema="landing",
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_knowledge_source_assertion_record_identity",
        "source_assertion",
        "source_identity_record",
        ["source_identity_id", "source_record_id"],
        ["source_identity_id", "record_id"],
        source_schema="knowledge",
        referent_schema="knowledge",
        ondelete="RESTRICT",
    )
    for endpoint in ("source", "target"):
        op.create_foreign_key(
            f"fk_knowledge_relationship_assertion_{endpoint}_record_identity",
            "relationship_assertion",
            "source_identity_record",
            [f"{endpoint}_identity_id", "source_record_id"],
            ["source_identity_id", "record_id"],
            source_schema="knowledge",
            referent_schema="knowledge",
            ondelete="RESTRICT",
        )

    for (
        table,
        reference_column,
        foreign_key,
        unique_constraint,
        check_constraint,
        subject_columns,
        subject_unique_constraint,
    ) in DECISION_LINEAGE:
        op.create_unique_constraint(
            unique_constraint,
            table,
            ["decision_id"],
            schema="knowledge",
        )
        if subject_unique_constraint is not None:
            op.create_unique_constraint(
                subject_unique_constraint,
                table,
                ["decision_id", *subject_columns],
                schema="knowledge",
            )
        op.drop_constraint(
            foreign_key,
            table,
            schema="knowledge",
            type_="foreignkey",
        )
        op.create_foreign_key(
            foreign_key,
            table,
            table,
            [reference_column, *subject_columns],
            ["decision_id", *subject_columns],
            source_schema="knowledge",
            referent_schema="knowledge",
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            check_constraint,
            table,
            f"{reference_column} IS NULL OR {reference_column} <> decision_id",
            schema="knowledge",
        )

    trace_check = _llm_trace_check()
    for table in (
        "identity_decision",
        "canonical_decision",
        "relationship_decision",
    ):
        op.add_column(
            table,
            sa.Column(
                "llm_trace",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            schema="knowledge",
        )
        op.create_check_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            trace_check,
            schema="knowledge",
        )

    for schema, table in APPEND_ONLY_TABLES:
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON {schema}.{table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION "
                "knowledge.reject_append_only_mutation()"
            )
        )
    for schema, table, immutable_columns in MUTABLE_HISTORY_TABLES:
        changed = " OR ".join(
            f"OLD.{column} IS DISTINCT FROM NEW.{column}"
            for column in immutable_columns
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_reject_immutable_update BEFORE UPDATE ON "
                f"{schema}.{table} FOR EACH ROW WHEN ({changed}) EXECUTE FUNCTION "
                "knowledge.reject_append_only_mutation()"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_reject_delete BEFORE DELETE ON {schema}.{table} "
                "FOR EACH ROW EXECUTE FUNCTION knowledge.reject_append_only_mutation()"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON {schema}.{table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION "
                "knowledge.reject_append_only_mutation()"
            )
        )


def downgrade() -> None:
    for schema, table, _ in MUTABLE_HISTORY_TABLES:
        for trigger in (
            "trg_reject_truncate",
            "trg_reject_delete",
            "trg_reject_immutable_update",
        ):
            op.execute(sa.text(f"DROP TRIGGER {trigger} ON {schema}.{table}"))
    for schema, table in APPEND_ONLY_TABLES:
        op.execute(sa.text(f"DROP TRIGGER trg_reject_truncate ON {schema}.{table}"))

    for table in (
        "relationship_decision",
        "canonical_decision",
        "identity_decision",
    ):
        op.drop_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            schema="knowledge",
            type_="check",
        )
        op.drop_column(table, "llm_trace", schema="knowledge")

    for (
        table,
        reference_column,
        foreign_key,
        unique_constraint,
        check_constraint,
        subject_columns,
        subject_unique_constraint,
    ) in reversed(DECISION_LINEAGE):
        op.drop_constraint(
            check_constraint,
            table,
            schema="knowledge",
            type_="check",
        )
        op.drop_constraint(
            foreign_key,
            table,
            schema="knowledge",
            type_="foreignkey",
        )
        op.create_foreign_key(
            foreign_key,
            table,
            table,
            ["release_id", reference_column],
            ["release_id", "decision_id"],
            source_schema="knowledge",
            referent_schema="knowledge",
            ondelete="RESTRICT",
        )
        if subject_unique_constraint is not None:
            op.drop_constraint(
                subject_unique_constraint,
                table,
                schema="knowledge",
                type_="unique",
            )
        op.drop_constraint(
            unique_constraint,
            table,
            schema="knowledge",
            type_="unique",
        )

    for endpoint in reversed(("source", "target")):
        op.drop_constraint(
            f"fk_knowledge_relationship_assertion_{endpoint}_record_identity",
            "relationship_assertion",
            schema="knowledge",
            type_="foreignkey",
        )
    op.drop_constraint(
        "fk_knowledge_source_assertion_record_identity",
        "source_assertion",
        schema="knowledge",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_landing_evidence_artifact_parent",
        "evidence_artifact",
        schema="landing",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_landing_evidence_artifact_parent",
        "evidence_artifact",
        "evidence_artifact",
        ["parent_artifact_id"],
        ["artifact_id"],
        source_schema="landing",
        referent_schema="landing",
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_landing_evidence_artifact_identity_hash",
        "evidence_artifact",
        schema="landing",
        type_="unique",
    )
