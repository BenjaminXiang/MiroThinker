"""Persist append-only Canonical V2 knowledge-gap operations.

Revision ID: C2_0011
Revises: C2_0010
Create Date: 2026-07-20
"""

from __future__ import annotations

from typing import Final, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0011"
down_revision: Union[str, None] = "C2_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHA256_CHECK: Final = "VALUE ~ '^[0-9a-f]{64}$'"
GAP_CLASSES: Final = (
    "knowledge_coverage",
    "identity",
    "source_conflict_freshness",
    "relationship",
    "path_reach",
    "retrieval_precision",
    "context",
    "synthesis",
    "index_parity",
    "provider_availability",
)
GAP_STATUSES: Final = ("open", "in_review", "planned", "resolved", "dismissed")
REVIEW_STATES: Final = ("unreviewed", "in_review", "accepted", "rejected")
SEVERITIES: Final = ("low", "medium", "high", "critical")


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _sha256_check(column: str) -> str:
    return SHA256_CHECK.replace("VALUE", column)


def _append_only(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON ops.{table} "
        "FOR EACH ROW EXECUTE FUNCTION knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON ops.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION knowledge.reject_append_only_mutation()"
    )


def upgrade() -> None:
    op.create_table(
        "knowledge_gap",
        sa.Column("gap_id", sa.Text(), nullable=False),
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("gap_class", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("review_state", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("affected_domains", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("affected_paths", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("demand_count", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gap_payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("gap_id", name="pk_ops_knowledge_gap"),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_ops_knowledge_gap_release",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("gap_class", GAP_CLASSES), name="ck_ops_gap_class"
        ),
        sa.CheckConstraint(
            _enum_check("status", GAP_STATUSES), name="ck_ops_gap_status"
        ),
        sa.CheckConstraint(
            _enum_check("review_state", REVIEW_STATES),
            name="ck_ops_gap_review_state",
        ),
        sa.CheckConstraint(
            _enum_check("severity", SEVERITIES), name="ck_ops_gap_severity"
        ),
        sa.CheckConstraint("demand_count >= 0", name="ck_ops_gap_demand_count"),
        sa.CheckConstraint(
            "cardinality(affected_domains) > 0",
            name="ck_ops_gap_affected_domains_nonempty",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(gap_payload) = 'object'",
            name="ck_ops_gap_payload_object",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"), name="ck_ops_gap_content_sha256"
        ),
        schema="ops",
    )
    op.create_index(
        "ix_ops_gap_admin_order",
        "knowledge_gap",
        ["severity", "demand_count", "updated_at", "gap_id"],
        schema="ops",
    )
    op.create_index(
        "ix_ops_gap_domains", "knowledge_gap", ["affected_domains"], schema="ops"
    )
    op.create_index(
        "ix_ops_gap_paths", "knowledge_gap", ["affected_paths"], schema="ops"
    )

    op.create_table(
        "gap_remediation_transition",
        sa.Column("transition_id", sa.Text(), nullable=False),
        sa.Column("gap_id", sa.Text(), nullable=False),
        sa.Column("source_release_id", sa.Text(), nullable=False),
        sa.Column("candidate_release_id", sa.Text(), nullable=False),
        sa.Column("transition_state", sa.Text(), nullable=False),
        sa.Column("remediation_input_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "transition_id", name="pk_ops_gap_remediation_transition"
        ),
        sa.UniqueConstraint(
            "gap_id",
            "remediation_input_sha256",
            name="uq_ops_gap_transition_input",
        ),
        sa.ForeignKeyConstraint(
            ["gap_id"],
            ["ops.knowledge_gap.gap_id"],
            name="fk_ops_gap_transition_gap",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_release_id"],
            ["knowledge.release.release_id"],
            name="fk_ops_gap_transition_source_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_release_id"],
            ["knowledge.release.release_id"],
            name="fk_ops_gap_transition_candidate_release",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "transition_state IN ('linked', 'resolved')",
            name="ck_ops_gap_transition_state",
        ),
        sa.CheckConstraint(
            _sha256_check("remediation_input_sha256"),
            name="ck_ops_gap_transition_input_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("result_content_sha256"),
            name="ck_ops_gap_transition_result_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(request_payload) = 'object' AND "
            "jsonb_typeof(result_payload) = 'object'",
            name="ck_ops_gap_transition_payload_objects",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_ops_gap_transition_history",
        "gap_remediation_transition",
        ["gap_id", "transitioned_at", "transition_id"],
        schema="ops",
    )
    _append_only("knowledge_gap")
    _append_only("gap_remediation_transition")

    op.execute(
        """
        CREATE VIEW ops.current_knowledge_gap AS
        SELECT base.gap_id,
               base.release_id AS source_release_id,
               COALESCE(latest.result_payload -> 'gap', base.gap_payload)
                   AS gap_payload,
               latest.transition_id,
               latest.transition_state,
               latest.candidate_release_id,
               COALESCE(latest.transitioned_at, base.updated_at) AS current_updated_at
        FROM ops.knowledge_gap AS base
        LEFT JOIN LATERAL (
            SELECT transition_id, transition_state, candidate_release_id,
                   transitioned_at, result_payload
            FROM ops.gap_remediation_transition AS transition
            WHERE transition.gap_id = base.gap_id
            ORDER BY transitioned_at DESC, transition_id DESC
            LIMIT 1
        ) AS latest ON TRUE
        """
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE ops.knowledge_gap, ops.gap_remediation_transition "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ops.knowledge_gap)
               OR EXISTS (SELECT 1 FROM ops.gap_remediation_transition)
            THEN
                RAISE EXCEPTION
                    'C2_0011 downgrade refuses nonempty operational history'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    op.execute("DROP VIEW ops.current_knowledge_gap")
    op.drop_table("gap_remediation_transition", schema="ops")
    op.drop_index("ix_ops_gap_paths", table_name="knowledge_gap", schema="ops")
    op.drop_index("ix_ops_gap_domains", table_name="knowledge_gap", schema="ops")
    op.drop_index("ix_ops_gap_admin_order", table_name="knowledge_gap", schema="ops")
    op.drop_table("knowledge_gap", schema="ops")
