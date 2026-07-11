"""Persist complete immutable EvidenceLanding runs.

Revision ID: C2_0004
Revises: C2_0003
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0004"
down_revision: Union[str, None] = "C2_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _parser_run_immutable_trigger(*, include_options: bool) -> str:
    columns = [
        "parse_run_id",
        "artifact_id",
        "parser_name",
        "parser_version",
        "schema_version",
        "started_at",
    ]
    if include_options:
        columns.append("parser_options")
    changed = " OR ".join(
        f"OLD.{column} IS DISTINCT FROM NEW.{column}" for column in columns
    )
    return (
        "CREATE TRIGGER trg_reject_immutable_update BEFORE UPDATE ON "
        f"landing.parser_run FOR EACH ROW WHEN ({changed}) EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM landing.evidence_artifact)
               OR EXISTS (SELECT 1 FROM landing.parser_run)
               OR EXISTS (SELECT 1 FROM landing.source_record)
               OR EXISTS (SELECT 1 FROM landing.source_error)
            THEN
                RAISE EXCEPTION
                    'C2_0004 requires an empty C2_0003 landing; existing rows cannot be assigned invented run identities'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    op.add_column(
        "source_record",
        sa.Column("record_ordinal", sa.Integer(), nullable=False),
        schema="landing",
    )
    op.create_unique_constraint(
        "uq_landing_source_record_ordinal",
        "source_record",
        ["parse_run_id", "record_ordinal"],
        schema="landing",
    )
    op.create_check_constraint(
        "ck_landing_source_record_ordinal",
        "source_record",
        "record_ordinal >= 0",
        schema="landing",
    )
    op.execute("DROP TRIGGER trg_reject_immutable_update ON landing.parser_run")
    op.add_column(
        "parser_run",
        sa.Column(
            "parser_options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="landing",
    )
    op.execute(_parser_run_immutable_trigger(include_options=True))

    op.create_table(
        "ingest_run",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("source_batch_id", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("parse_run_id", sa.Text(), nullable=False),
        sa.Column("request_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("landing_status", sa.Text(), nullable=False),
        sa.Column("bytes_written", sa.BigInteger(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_landing_ingest_run"),
        sa.UniqueConstraint("parse_run_id", name="uq_landing_ingest_run_parse_run"),
        sa.ForeignKeyConstraint(
            ["artifact_id", "content_sha256"],
            [
                "landing.evidence_artifact.artifact_id",
                "landing.evidence_artifact.content_sha256",
            ],
            name="fk_landing_ingest_run_artifact_content",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id", "artifact_id"],
            ["landing.parser_run.parse_run_id", "landing.parser_run.artifact_id"],
            name="fk_landing_ingest_run_parser_artifact",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_landing_ingest_run_content_sha256",
        ),
        sa.CheckConstraint(
            "request_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_landing_ingest_run_request_fingerprint",
        ),
        sa.CheckConstraint(
            "output_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_landing_ingest_run_output_fingerprint",
        ),
        sa.CheckConstraint(
            "landing_status IN ('accepted', 'partial', 'quarantined')",
            name="ck_landing_ingest_run_status",
        ),
        sa.CheckConstraint(
            "bytes_written >= 0", name="ck_landing_ingest_run_bytes_written"
        ),
        sa.CheckConstraint(
            "record_count >= 0", name="ck_landing_ingest_run_record_count"
        ),
        schema="landing",
    )
    for operation in (
        "BEFORE UPDATE OR DELETE ON landing.ingest_run FOR EACH ROW",
        "BEFORE TRUNCATE ON landing.ingest_run FOR EACH STATEMENT",
    ):
        trigger = (
            "trg_reject_mutation" if "UPDATE" in operation else "trg_reject_truncate"
        )
        op.execute(
            f"CREATE TRIGGER {trigger} {operation} EXECUTE FUNCTION "
            "knowledge.reject_append_only_mutation()"
        )


def downgrade() -> None:
    op.drop_table("ingest_run", schema="landing")

    op.execute("DROP TRIGGER trg_reject_immutable_update ON landing.parser_run")
    op.drop_column("parser_run", "parser_options", schema="landing")
    op.execute(_parser_run_immutable_trigger(include_options=False))

    op.drop_constraint(
        "ck_landing_source_record_ordinal",
        "source_record",
        schema="landing",
        type_="check",
    )
    op.drop_constraint(
        "uq_landing_source_record_ordinal",
        "source_record",
        schema="landing",
        type_="unique",
    )
    op.drop_column("source_record", "record_ordinal", schema="landing")
