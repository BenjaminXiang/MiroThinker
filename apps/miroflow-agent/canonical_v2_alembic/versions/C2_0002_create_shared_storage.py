"""Create shared evidence, decision, and release storage.

Revision ID: C2_0002
Revises: C2_0001
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0002"
down_revision: Union[str, None] = "C2_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHA256_CHECK = "VALUE ~ '^[0-9a-f]{64}$'"


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({allowed})"


def _sha256_check(column: str) -> str:
    return SHA256_CHECK.replace("VALUE", column)


def _install_append_only_trigger(schema: str, table: str) -> None:
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE "
            f"ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.reject_append_only_mutation()"
        )
    )


def upgrade() -> None:
    op.create_table(
        "release",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("previous_release_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("release_id", name="pk_knowledge_release"),
        sa.UniqueConstraint(
            "manifest_sha256", name="uq_knowledge_release_manifest_sha256"
        ),
        sa.UniqueConstraint(
            "release_id",
            "manifest_sha256",
            name="uq_knowledge_release_manifest_identity",
        ),
        sa.ForeignKeyConstraint(
            ["previous_release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_release_previous",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check(
                "state",
                (
                    "candidate",
                    "verified",
                    "accepted",
                    "rejected",
                    "active",
                    "rolled_back",
                    "retired",
                ),
            ),
            name="ck_knowledge_release_state",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_sha256"),
            name="ck_knowledge_release_manifest_sha256",
        ),
        sa.CheckConstraint(
            "previous_release_id IS NULL OR previous_release_id <> release_id",
            name="ck_knowledge_release_previous_not_self",
        ),
        schema="knowledge",
    )

    op.create_table(
        "policy",
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("policy_kind", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "policy_id", "policy_version", name="pk_knowledge_policy"
        ),
        sa.CheckConstraint(
            _enum_check(
                "policy_kind",
                (
                    "inclusion",
                    "path_eligibility",
                    "identity",
                    "field_selection",
                    "relationship",
                    "publication",
                    "gap",
                ),
            ),
            name="ck_knowledge_policy_kind",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_policy_content_sha256",
        ),
        schema="knowledge",
    )

    op.create_table(
        "evidence_artifact",
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("parent_artifact_id", sa.Text(), nullable=True),
        sa.Column("parent_content_sha256", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("artifact_id", name="pk_landing_evidence_artifact"),
        sa.UniqueConstraint(
            "source_kind",
            "source_locator",
            "content_sha256",
            name="uq_landing_evidence_artifact_source_content",
        ),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"],
            ["landing.evidence_artifact.artifact_id"],
            name="fk_landing_evidence_artifact_parent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_landing_evidence_artifact_content_sha256",
        ),
        sa.CheckConstraint(
            "parent_content_sha256 IS NULL OR "
            + _sha256_check("parent_content_sha256"),
            name="ck_landing_evidence_artifact_parent_sha256",
        ),
        sa.CheckConstraint(
            "byte_size >= 0", name="ck_landing_evidence_artifact_byte_size"
        ),
        sa.CheckConstraint(
            "(parent_artifact_id IS NULL) = (parent_content_sha256 IS NULL)",
            name="ck_landing_evidence_artifact_parent_pair",
        ),
        sa.CheckConstraint(
            "parent_artifact_id IS NULL OR parent_artifact_id <> artifact_id",
            name="ck_landing_evidence_artifact_parent_not_self",
        ),
        schema="landing",
    )

    op.create_table(
        "parser_run",
        sa.Column("parse_run_id", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("parser_name", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("run_status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("parse_run_id", name="pk_landing_parser_run"),
        sa.UniqueConstraint(
            "parse_run_id",
            "artifact_id",
            name="uq_landing_parser_run_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["landing.evidence_artifact.artifact_id"],
            name="fk_landing_parser_run_artifact",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("run_status", ("running", "succeeded", "partial", "failed")),
            name="ck_landing_parser_run_status",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_landing_parser_run_time",
        ),
        schema="landing",
    )

    op.create_table(
        "source_record",
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("source_batch_id", sa.Text(), nullable=False),
        sa.Column("record_locator", sa.Text(), nullable=False),
        sa.Column("parse_run_id", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("record_id", name="pk_landing_source_record"),
        sa.UniqueConstraint(
            "parse_run_id",
            "record_locator",
            name="uq_landing_source_record_replay",
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id", "artifact_id"],
            ["landing.parser_run.parse_run_id", "landing.parser_run.artifact_id"],
            name="fk_landing_source_record_parser_artifact",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check(
                "parse_status",
                ("parsed", "partial", "quarantined", "unsupported", "corrupt"),
            ),
            name="ck_landing_source_record_parse_status",
        ),
        schema="landing",
    )

    op.create_table(
        "source_error",
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.Column("error_ordinal", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=False),
        sa.Column("error_kind", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=True),
        sa.Column("recoverable", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(
            "record_id", "error_ordinal", name="pk_landing_source_error"
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["landing.source_record.record_id"],
            name="fk_landing_source_error_record",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "error_ordinal >= 0", name="ck_landing_source_error_ordinal"
        ),
        sa.CheckConstraint(
            _enum_check(
                "error_kind",
                (
                    "unsupported_format",
                    "corrupt_content",
                    "missing_external_content",
                    "parse_error",
                    "schema_mismatch",
                ),
            ),
            name="ck_landing_source_error_kind",
        ),
        schema="landing",
    )

    op.create_table(
        "source_identity",
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column(
            "normalized_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "source_identity_id", name="pk_knowledge_source_identity"
        ),
        sa.UniqueConstraint(
            "source_system",
            "source_key",
            "entity_type",
            name="uq_knowledge_source_identity_source_key",
        ),
        sa.CheckConstraint(
            _enum_check("state", ("active", "superseded", "rejected")),
            name="ck_knowledge_source_identity_state",
        ),
        sa.CheckConstraint(
            "last_observed_at >= first_observed_at",
            name="ck_knowledge_source_identity_time",
        ),
        schema="knowledge",
    )

    op.create_table(
        "source_identity_record",
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "source_identity_id",
            "record_id",
            name="pk_knowledge_source_identity_record",
        ),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_source_identity_record_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["landing.source_record.record_id"],
            name="fk_knowledge_source_identity_record_record",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    op.create_table(
        "source_assertion",
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("subject_entity_type", sa.Text(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assertion_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assertion_run_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("assertion_id", name="pk_knowledge_source_assertion"),
        sa.UniqueConstraint(
            "assertion_fingerprint_sha256",
            name="uq_knowledge_source_assertion_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["landing.source_record.record_id"],
            name="fk_knowledge_source_assertion_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_source_assertion_identity",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("assertion_fingerprint_sha256"),
            name="ck_knowledge_source_assertion_fingerprint",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="ck_knowledge_source_assertion_validity",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_decision",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("method_version", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversal_of_decision_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "release_id", "decision_id", name="pk_knowledge_identity_decision"
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_identity_decision_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["knowledge.policy.policy_id", "knowledge.policy.policy_version"],
            name="fk_knowledge_identity_decision_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "reversal_of_decision_id"],
            [
                "knowledge.identity_decision.release_id",
                "knowledge.identity_decision.decision_id",
            ],
            name="fk_knowledge_identity_decision_reversal",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check(
                "action", ("create", "link", "merge", "split", "reject", "reverse")
            ),
            name="ck_knowledge_identity_decision_action",
        ),
        sa.CheckConstraint(
            _enum_check(
                "method",
                ("deterministic", "structured_llm", "human_review", "composite"),
            ),
            name="ck_knowledge_identity_decision_method",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_identity_decision_confidence",
        ),
        sa.CheckConstraint(
            "(action = 'reverse' AND reversal_of_decision_id IS NOT NULL) OR "
            "(action <> 'reverse' AND reversal_of_decision_id IS NULL)",
            name="ck_knowledge_identity_decision_reversal_shape",
        ),
        schema="knowledge",
    )

    op.create_table(
        "canonical_identity",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("identity_decision_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "canonical_identity_id",
            name="pk_knowledge_canonical_identity",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_canonical_identity_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "identity_decision_id"],
            [
                "knowledge.identity_decision.release_id",
                "knowledge.identity_decision.decision_id",
            ],
            name="fk_knowledge_canonical_identity_decision",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            _enum_check("state", ("active", "merged", "split", "rejected")),
            name="ck_knowledge_canonical_identity_state",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_decision_source_identity",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "source_identity_id",
            name="pk_knowledge_identity_decision_source_identity",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.identity_decision.release_id",
                "knowledge.identity_decision.decision_id",
            ],
            name="fk_knowledge_identity_decision_source_identity_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_identity_decision_source_identity_identity",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    for table_name, constraint_suffix in (
        ("identity_decision_input", "input"),
        ("identity_decision_output", "output"),
    ):
        op.create_table(
            table_name,
            sa.Column("release_id", sa.Text(), nullable=False),
            sa.Column("decision_id", sa.Text(), nullable=False),
            sa.Column("canonical_identity_id", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint(
                "release_id",
                "decision_id",
                "canonical_identity_id",
                name=f"pk_knowledge_{table_name}",
            ),
            sa.ForeignKeyConstraint(
                ["release_id", "decision_id"],
                [
                    "knowledge.identity_decision.release_id",
                    "knowledge.identity_decision.decision_id",
                ],
                name=f"fk_knowledge_identity_decision_{constraint_suffix}_decision",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["release_id", "canonical_identity_id"],
                [
                    "knowledge.canonical_identity.release_id",
                    "knowledge.canonical_identity.canonical_identity_id",
                ],
                name=f"fk_knowledge_identity_decision_{constraint_suffix}_identity",
                ondelete="RESTRICT",
                deferrable=True,
                initially="DEFERRED",
            ),
            schema="knowledge",
        )

    op.create_table(
        "identity_decision_record",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "record_id",
            name="pk_knowledge_identity_decision_record",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.identity_decision.release_id",
                "knowledge.identity_decision.decision_id",
            ],
            name="fk_knowledge_identity_decision_record_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["landing.source_record.record_id"],
            name="fk_knowledge_identity_decision_record_record",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    op.create_table(
        "canonical_decision",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("method_version", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_decision_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "release_id", "decision_id", name="pk_knowledge_canonical_decision"
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_decision_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["knowledge.policy.policy_id", "knowledge.policy.policy_version"],
            name="fk_knowledge_canonical_decision_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "supersedes_decision_id"],
            [
                "knowledge.canonical_decision.release_id",
                "knowledge.canonical_decision.decision_id",
            ],
            name="fk_knowledge_canonical_decision_supersedes",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("state", ("selected", "unresolved", "rejected", "superseded")),
            name="ck_knowledge_canonical_decision_state",
        ),
        sa.CheckConstraint(
            _enum_check(
                "method",
                ("deterministic", "structured_llm", "human_review", "composite"),
            ),
            name="ck_knowledge_canonical_decision_method",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_canonical_decision_confidence",
        ),
        schema="knowledge",
    )

    op.create_table(
        "canonical_decision_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("assertion_role", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            "assertion_role",
            name="pk_knowledge_canonical_decision_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.canonical_decision.release_id",
                "knowledge.canonical_decision.decision_id",
            ],
            name="fk_knowledge_canonical_decision_assertion_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["knowledge.source_assertion.assertion_id"],
            name="fk_knowledge_canonical_decision_assertion_assertion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("assertion_role", ("candidate", "selected", "conflicting")),
            name="ck_knowledge_canonical_decision_assertion_role",
        ),
        schema="knowledge",
    )

    op.create_table(
        "relationship_type",
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column(
            "source_entity_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "target_entity_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "required_evidence_kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("time_semantics", sa.Text(), nullable=False),
        sa.Column(
            "allowed_states", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "eligible_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "relationship_type_id", "version", name="pk_knowledge_relationship_type"
        ),
        sa.CheckConstraint(
            _enum_check("layer", ("canonical", "derived", "session")),
            name="ck_knowledge_relationship_type_layer",
        ),
        sa.CheckConstraint(
            _enum_check("direction", ("directed", "undirected")),
            name="ck_knowledge_relationship_type_direction",
        ),
        sa.CheckConstraint(
            _enum_check(
                "time_semantics",
                (
                    "none",
                    "observed_at",
                    "event_time",
                    "validity_interval",
                    "computed_at",
                    "session_lifetime",
                ),
            ),
            name="ck_knowledge_relationship_type_time_semantics",
        ),
        sa.CheckConstraint(
            "CASE WHEN jsonb_typeof(required_evidence_kinds) = 'array' THEN "
            "(layer = 'canonical' AND jsonb_array_length(required_evidence_kinds) > 0) OR "
            "(layer IN ('derived', 'session') AND "
            "jsonb_array_length(required_evidence_kinds) = 0) ELSE FALSE END",
            name="ck_knowledge_relationship_type_evidence_layer",
        ),
        schema="knowledge",
    )

    op.create_table(
        "relationship_assertion",
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_version", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("target_identity_id", sa.Text(), nullable=False),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("assertion_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assertion_run_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "assertion_id", name="pk_knowledge_relationship_assertion"
        ),
        sa.UniqueConstraint(
            "assertion_fingerprint_sha256",
            name="uq_knowledge_relationship_assertion_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_type_id", "relationship_type_version"],
            [
                "knowledge.relationship_type.relationship_type_id",
                "knowledge.relationship_type.version",
            ],
            name="fk_knowledge_relationship_assertion_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["landing.source_record.record_id"],
            name="fk_knowledge_relationship_assertion_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_relationship_assertion_source_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_relationship_assertion_target_identity",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("assertion_fingerprint_sha256"),
            name="ck_knowledge_relationship_assertion_fingerprint",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="ck_knowledge_relationship_assertion_validity",
        ),
        schema="knowledge",
    )

    op.create_table(
        "relationship_decision",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("canonical_relationship_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_version", sa.Text(), nullable=False),
        sa.Column("source_canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("target_canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "role_bindings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("method_version", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_decision_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "release_id", "decision_id", name="pk_knowledge_relationship_decision"
        ),
        sa.UniqueConstraint(
            "release_id",
            "canonical_relationship_id",
            name="uq_knowledge_relationship_decision_canonical_relation",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_relationship_decision_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_type_id", "relationship_type_version"],
            [
                "knowledge.relationship_type.relationship_type_id",
                "knowledge.relationship_type.version",
            ],
            name="fk_knowledge_relationship_decision_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "source_canonical_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_relationship_decision_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "target_canonical_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_relationship_decision_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["knowledge.policy.policy_id", "knowledge.policy.policy_version"],
            name="fk_knowledge_relationship_decision_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "supersedes_decision_id"],
            [
                "knowledge.relationship_decision.release_id",
                "knowledge.relationship_decision.decision_id",
            ],
            name="fk_knowledge_relationship_decision_supersedes",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("state", ("accepted", "unresolved", "rejected", "superseded")),
            name="ck_knowledge_relationship_decision_state",
        ),
        sa.CheckConstraint(
            _enum_check(
                "method",
                ("deterministic", "structured_llm", "human_review", "composite"),
            ),
            name="ck_knowledge_relationship_decision_method",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_relationship_decision_confidence",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="ck_knowledge_relationship_decision_validity",
        ),
        schema="knowledge",
    )

    op.create_table(
        "relationship_decision_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("assertion_role", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            "assertion_role",
            name="pk_knowledge_relationship_decision_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.relationship_decision.release_id",
                "knowledge.relationship_decision.decision_id",
            ],
            name="fk_knowledge_relationship_decision_assertion_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["knowledge.relationship_assertion.assertion_id"],
            name="fk_knowledge_relationship_decision_assertion_assertion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _enum_check("assertion_role", ("candidate", "selected", "conflicting")),
            name="ck_knowledge_relationship_decision_assertion_role",
        ),
        schema="knowledge",
    )

    op.create_table(
        "build_manifest",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("build_run_id", sa.Text(), nullable=False),
        sa.Column(
            "source_batch_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("source_batches_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "parser_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "policy_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "model_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("release_id", name="pk_publish_build_manifest"),
        sa.UniqueConstraint("manifest_sha256", name="uq_publish_build_manifest_sha256"),
        sa.ForeignKeyConstraint(
            ["release_id", "manifest_sha256"],
            ["knowledge.release.release_id", "knowledge.release.manifest_sha256"],
            name="fk_publish_build_manifest_release_identity",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("source_batches_sha256"),
            name="ck_publish_build_manifest_source_batches_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_sha256"),
            name="ck_publish_build_manifest_sha256",
        ),
        schema="publish",
    )

    op.create_table(
        "manifest_section",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=False),
        sa.Column("section_kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id", "section_id", name="pk_publish_manifest_section"
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["publish.build_manifest.release_id"],
            name="fk_publish_manifest_section_manifest",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "record_count >= 0", name="ck_publish_manifest_section_record_count"
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_publish_manifest_section_content_sha256",
        ),
        schema="publish",
    )

    op.create_table(
        "active_release",
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("canonical_release_id", sa.Text(), nullable=False),
        sa.Column("published_projection_release_id", sa.Text(), nullable=False),
        sa.Column("index_release_id", sa.Text(), nullable=False),
        sa.Column("previous_release_id", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("singleton", name="pk_publish_active_release"),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["publish.build_manifest.release_id"],
            name="fk_publish_active_release_manifest",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_release_id"],
            ["knowledge.release.release_id"],
            name="fk_publish_active_release_canonical",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["published_projection_release_id"],
            ["knowledge.release.release_id"],
            name="fk_publish_active_release_projection",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["index_release_id"],
            ["knowledge.release.release_id"],
            name="fk_publish_active_release_index",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_release_id"],
            ["knowledge.release.release_id"],
            name="fk_publish_active_release_previous",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("singleton", name="ck_publish_active_release_singleton"),
        sa.CheckConstraint(
            "release_id = canonical_release_id AND "
            "release_id = published_projection_release_id AND "
            "release_id = index_release_id",
            name="ck_publish_active_release_one_release",
        ),
        sa.CheckConstraint(
            "previous_release_id IS NULL OR previous_release_id <> release_id",
            name="ck_publish_active_release_previous_not_self",
        ),
        schema="publish",
    )

    op.execute(
        """
        CREATE FUNCTION knowledge.reject_append_only_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'append-only relation %.% rejects %',
                TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    for schema, table in (
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
    ):
        _install_append_only_trigger(schema, table)


def downgrade() -> None:
    for schema, table in (
        ("publish", "active_release"),
        ("publish", "manifest_section"),
        ("publish", "build_manifest"),
        ("knowledge", "relationship_decision_assertion"),
        ("knowledge", "relationship_decision"),
        ("knowledge", "relationship_assertion"),
        ("knowledge", "relationship_type"),
        ("knowledge", "canonical_decision_assertion"),
        ("knowledge", "canonical_decision"),
        ("knowledge", "identity_decision_record"),
        ("knowledge", "identity_decision_output"),
        ("knowledge", "identity_decision_input"),
        ("knowledge", "identity_decision_source_identity"),
        ("knowledge", "canonical_identity"),
        ("knowledge", "identity_decision"),
        ("knowledge", "source_assertion"),
        ("knowledge", "source_identity_record"),
        ("knowledge", "source_identity"),
        ("landing", "source_error"),
        ("landing", "source_record"),
        ("landing", "parser_run"),
        ("landing", "evidence_artifact"),
        ("knowledge", "policy"),
        ("knowledge", "release"),
    ):
        op.drop_table(table, schema=schema)
    op.execute("DROP FUNCTION knowledge.reject_append_only_mutation()")
