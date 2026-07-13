"""Persist typed and current Canonical V2 relationship projections.

Revision ID: C2_0010
Revises: C2_0009
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Final, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0010"
down_revision: Union[str, None] = "C2_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHA256_CHECK: Final = "VALUE ~ '^[0-9a-f]{64}$'"
NEW_TABLES = (
    "relationship_projection_run",
    "relationship_projection_shared_assertion",
    "relationship_projection_shared_decision",
    "typed_relationship_assertion",
    "typed_relationship_decision",
    "typed_relationship_decision_assertion",
    "relationship_projection_outcome",
    "current_relationship_projection",
)
RELEASE_SCOPED_TABLES = (
    *NEW_TABLES,
    "relationship_decision",
    "relationship_decision_assertion",
)


def _sha256_check(column: str) -> str:
    return SHA256_CHECK.replace("VALUE", column)


def _json_object_check(column: str) -> str:
    return f"jsonb_typeof({column}) = 'object'"


def _json_array_check(column: str) -> str:
    return f"jsonb_typeof({column}) = 'array'"


def _install_append_only(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE "
        f"ON knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE "
        f"ON knowledge.{table} FOR EACH STATEMENT EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )


def _drop_append_only(table: str) -> None:
    op.execute(f"DROP TRIGGER trg_reject_truncate ON knowledge.{table}")
    op.execute(f"DROP TRIGGER trg_reject_mutation ON knowledge.{table}")


def _create_run_table() -> None:
    op.create_table(
        "relationship_projection_run",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("catalog_schema_version", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("catalog_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "temporal_comparison_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "retained_assertion_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "retained_artifact_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("request_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "release_id",
            "projection_run_id",
            name="pk_knowledge_relationship_projection_run",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_relationship_projection_run_release",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("catalog_content_sha256"),
            name="ck_knowledge_relationship_projection_catalog_hash",
        ),
        sa.CheckConstraint(
            _sha256_check("request_content_sha256"),
            name="ck_knowledge_relationship_projection_request_hash",
        ),
        sa.CheckConstraint(
            _sha256_check("result_content_sha256"),
            name="ck_knowledge_relationship_projection_result_hash",
        ),
        sa.CheckConstraint(
            _json_array_check("retained_assertion_refs")
            + " AND "
            + _json_array_check("retained_artifact_refs")
            + " AND "
            + _json_object_check("result_payload")
            + " AND (temporal_comparison_context IS NULL OR "
            + _json_object_check("temporal_comparison_context")
            + ")",
            name="ck_knowledge_relationship_projection_run_json",
        ),
        schema="knowledge",
    )


def _create_shared_membership_tables() -> None:
    op.create_table(
        "relationship_projection_shared_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "projection_run_id",
            "assertion_id",
            name="pk_knowledge_relationship_projection_shared_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_relationship_projection_shared_assertion_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["knowledge.relationship_assertion.assertion_id"],
            name="fk_knowledge_relationship_projection_shared_assertion_row",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_relationship_projection_shared_assertion_hash",
        ),
        schema="knowledge",
    )
    op.create_table(
        "relationship_projection_shared_decision",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "projection_run_id",
            "decision_id",
            name="pk_knowledge_relationship_projection_shared_decision",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_relationship_projection_shared_decision_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.relationship_decision.release_id",
                "knowledge.relationship_decision.decision_id",
            ],
            name="fk_knowledge_relationship_projection_shared_decision_row",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_relationship_projection_shared_decision_hash",
        ),
        schema="knowledge",
    )


def _create_typed_assertion_table() -> None:
    op.create_table(
        "typed_relationship_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_version", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("source_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("target_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("valid_to_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("assertion_run_id", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "assertion_id",
            name="pk_knowledge_typed_relationship_assertion",
        ),
        sa.UniqueConstraint(
            "release_id",
            "content_sha256",
            name="uq_knowledge_typed_relationship_assertion_content",
        ),
        sa.UniqueConstraint(
            "release_id",
            "projection_run_id",
            "assertion_id",
            name="uq_knowledge_typed_relationship_assertion_run",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_typed_relationship_assertion_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_type_id", "relationship_type_version"],
            [
                "knowledge.relationship_type.relationship_type_id",
                "knowledge.relationship_type.version",
            ],
            name="fk_knowledge_typed_relationship_assertion_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["landing.source_record.record_id"],
            name="fk_knowledge_typed_relationship_assertion_record",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _json_object_check("source_endpoint")
            + " AND "
            + _json_object_check("target_endpoint")
            + " AND "
            + _json_object_check("attributes")
            + " AND "
            + _json_array_check("evidence_bindings"),
            name="ck_knowledge_typed_relationship_assertion_json",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_typed_relationship_assertion_hash",
        ),
        schema="knowledge",
    )


def _create_typed_decision_tables() -> None:
    op.create_table(
        "typed_relationship_decision",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("canonical_relationship_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_version", sa.Text(), nullable=False),
        sa.Column("source_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("target_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("candidate_assertion_ids", postgresql.JSONB(), nullable=False),
        sa.Column("selected_assertion_ids", postgresql.JSONB(), nullable=False),
        sa.Column("conflicting_assertion_ids", postgresql.JSONB(), nullable=False),
        sa.Column("role_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("selected_evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("method_version", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("valid_from_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("valid_to_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_decision_id", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            name="pk_knowledge_typed_relationship_decision",
        ),
        sa.UniqueConstraint(
            "release_id",
            "canonical_relationship_id",
            name="uq_knowledge_typed_relationship_decision_relationship",
        ),
        sa.UniqueConstraint(
            "release_id",
            "projection_run_id",
            "decision_id",
            name="uq_knowledge_typed_relationship_decision_run",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_typed_relationship_decision_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_type_id", "relationship_type_version"],
            [
                "knowledge.relationship_type.relationship_type_id",
                "knowledge.relationship_type.version",
            ],
            name="fk_knowledge_typed_relationship_decision_type",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["knowledge.policy.policy_id", "knowledge.policy.policy_version"],
            name="fk_knowledge_typed_relationship_decision_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "supersedes_decision_id"],
            [
                "knowledge.typed_relationship_decision.release_id",
                "knowledge.typed_relationship_decision.decision_id",
            ],
            name="fk_knowledge_typed_relationship_decision_supersedes",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('accepted', 'unresolved', 'rejected', 'superseded')",
            name="ck_knowledge_typed_relationship_decision_state",
        ),
        sa.CheckConstraint(
            "method IN ('deterministic', 'structured_llm', 'human_review', 'composite')",
            name="ck_knowledge_typed_relationship_decision_method",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_typed_relationship_decision_confidence",
        ),
        sa.CheckConstraint(
            _json_object_check("source_endpoint")
            + " AND "
            + _json_object_check("target_endpoint")
            + " AND "
            + _json_array_check("candidate_assertion_ids")
            + " AND "
            + _json_array_check("selected_assertion_ids")
            + " AND "
            + _json_array_check("conflicting_assertion_ids")
            + " AND "
            + _json_object_check("role_bindings")
            + " AND "
            + _json_array_check("selected_evidence_refs"),
            name="ck_knowledge_typed_relationship_decision_json",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_typed_relationship_decision_hash",
        ),
        schema="knowledge",
    )
    op.create_table(
        "typed_relationship_decision_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("assertion_role", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            "assertion_role",
            name="pk_knowledge_typed_relationship_decision_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id", "decision_id"],
            [
                "knowledge.typed_relationship_decision.release_id",
                "knowledge.typed_relationship_decision.projection_run_id",
                "knowledge.typed_relationship_decision.decision_id",
            ],
            name="fk_knowledge_typed_relationship_decision_assertion_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id", "assertion_id"],
            [
                "knowledge.typed_relationship_assertion.release_id",
                "knowledge.typed_relationship_assertion.projection_run_id",
                "knowledge.typed_relationship_assertion.assertion_id",
            ],
            name="fk_knowledge_typed_relationship_decision_assertion_row",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assertion_role IN ('candidate', 'selected', 'conflicting')",
            name="ck_knowledge_typed_relationship_decision_assertion_role",
        ),
        schema="knowledge",
    )


def _create_outcome_table() -> None:
    op.create_table(
        "relationship_projection_outcome",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("admitted", sa.Boolean(), nullable=False),
        sa.Column("outcome_payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "projection_run_id",
            "candidate_id",
            name="pk_knowledge_relationship_projection_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_relationship_projection_outcome_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _json_object_check("outcome_payload"),
            name="ck_knowledge_relationship_projection_outcome_json",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_relationship_projection_outcome_hash",
        ),
        schema="knowledge",
    )


def _create_current_table() -> None:
    op.create_table(
        "current_relationship_projection",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column("canonical_relationship_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("decision_kind", sa.Text(), nullable=False),
        sa.Column("relationship_type_id", sa.Text(), nullable=False),
        sa.Column("relationship_type_version", sa.Text(), nullable=False),
        sa.Column("source_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("target_endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("role_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("selected_evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("effective_time_semantics", sa.Text(), nullable=False),
        sa.Column("valid_from_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("valid_to_temporal", postgresql.JSONB(), nullable=True),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "canonical_relationship_id",
            name="pk_knowledge_current_relationship_projection",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "projection_run_id"],
            [
                "knowledge.relationship_projection_run.release_id",
                "knowledge.relationship_projection_run.projection_run_id",
            ],
            name="fk_knowledge_current_relationship_projection_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_type_id", "relationship_type_version"],
            [
                "knowledge.relationship_type.relationship_type_id",
                "knowledge.relationship_type.version",
            ],
            name="fk_knowledge_current_relationship_projection_type",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision_kind IN ('shared', 'typed')",
            name="ck_knowledge_current_relationship_projection_decision_kind",
        ),
        sa.CheckConstraint(
            _json_object_check("source_endpoint")
            + " AND "
            + _json_object_check("target_endpoint")
            + " AND "
            + _json_object_check("role_bindings")
            + " AND "
            + _json_array_check("selected_evidence_refs"),
            name="ck_knowledge_current_relationship_projection_json",
        ),
        sa.CheckConstraint(
            _sha256_check("content_sha256"),
            name="ck_knowledge_current_relationship_projection_hash",
        ),
        schema="knowledge",
    )


def _create_candidate_release_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_relationship_projection_candidate_release()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            release_state text;
        BEGIN
            SELECT state INTO release_state
            FROM knowledge.release
            WHERE release_id = NEW.release_id;
            IF release_state IS DISTINCT FROM 'candidate' THEN
                RAISE EXCEPTION
                    'relationship projections require a candidate release'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in RELEASE_SCOPED_TABLES:
        op.execute(
            "CREATE TRIGGER trg_validate_relationship_candidate_release "
            f"BEFORE INSERT ON knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_relationship_projection_candidate_release()"
        )


def _create_endpoint_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.relationship_endpoint_exists(
            checked_release_id text,
            endpoint jsonb
        ) RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            kind text := endpoint->>'reference_kind';
            endpoint_type text := endpoint->>'endpoint_type';
            stable_reference text := endpoint->>'stable_reference';
            parent_reference text := endpoint->>'parent_canonical_identity_ref';
            found boolean;
        BEGIN
            IF kind = 'canonical_identity' THEN
                SELECT EXISTS (
                    SELECT 1 FROM knowledge.canonical_identity AS identity
                    WHERE identity.release_id = checked_release_id
                      AND identity.canonical_identity_id = endpoint->>'canonical_identity_id'
                      AND identity.entity_type = endpoint_type
                      AND stable_reference = 'canonical:' || endpoint_type || ':' ||
                          identity.canonical_identity_id
                ) INTO found;
                RETURN found;
            ELSIF kind = 'typed_subobject' THEN
                CASE endpoint_type
                    WHEN 'business_scenario' THEN
                        SELECT EXISTS (SELECT 1 FROM company.business_scenario AS child
                            WHERE child.release_id = checked_release_id
                              AND child.subobject_id = stable_reference
                              AND parent_reference = 'canonical:company:' ||
                                  child.canonical_identity_id) INTO found;
                    WHEN 'capability' THEN
                        SELECT EXISTS (SELECT 1 FROM company.capability AS child
                            WHERE child.release_id = checked_release_id
                              AND child.subobject_id = stable_reference
                              AND parent_reference = 'canonical:company:' ||
                                  child.canonical_identity_id) INTO found;
                    WHEN 'financing_event' THEN
                        SELECT EXISTS (SELECT 1 FROM company.financing_event AS child
                            WHERE child.release_id = checked_release_id
                              AND child.subobject_id = stable_reference
                              AND parent_reference = 'canonical:company:' ||
                                  child.canonical_identity_id) INTO found;
                    WHEN 'product' THEN
                        SELECT EXISTS (SELECT 1 FROM company.product AS child
                            WHERE child.release_id = checked_release_id
                              AND child.subobject_id = stable_reference
                              AND parent_reference = 'canonical:company:' ||
                                  child.canonical_identity_id) INTO found;
                    WHEN 'public_update' THEN
                        SELECT EXISTS (SELECT 1 FROM company.public_update AS child
                            WHERE child.release_id = checked_release_id
                              AND child.subobject_id = stable_reference
                              AND parent_reference = 'canonical:company:' ||
                                  child.canonical_identity_id) INTO found;
                    ELSE
                        found := false;
                END CASE;
                RETURN found;
            END IF;
            RETURN kind IN ('registry_entity', 'lineage_record');
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_typed_relationship_endpoints()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF knowledge.relationship_endpoint_exists(NEW.release_id, NEW.source_endpoint)
               IS DISTINCT FROM TRUE
               OR knowledge.relationship_endpoint_exists(
                   NEW.release_id, NEW.target_endpoint
               ) IS DISTINCT FROM TRUE
            THEN
                RAISE EXCEPTION 'typed relationship endpoint is not durable'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in (
        "typed_relationship_assertion",
        "typed_relationship_decision",
        "current_relationship_projection",
    ):
        op.execute(
            "CREATE TRIGGER trg_validate_typed_relationship_endpoints "
            f"BEFORE INSERT ON knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_typed_relationship_endpoints()"
        )


def _create_current_decision_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_current_relationship_decision()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            valid_link boolean;
        BEGIN
            IF NEW.decision_kind = 'shared' THEN
                SELECT EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_projection_shared_decision AS member
                    JOIN knowledge.relationship_decision AS decision
                      ON decision.release_id = member.release_id
                     AND decision.decision_id = member.decision_id
                    WHERE member.release_id = NEW.release_id
                      AND member.projection_run_id = NEW.projection_run_id
                      AND member.decision_id = NEW.decision_id
                      AND decision.canonical_relationship_id =
                          NEW.canonical_relationship_id
                      AND decision.state = 'accepted'
                ) INTO valid_link;
            ELSE
                SELECT EXISTS (
                    SELECT 1 FROM knowledge.typed_relationship_decision AS decision
                    WHERE decision.release_id = NEW.release_id
                      AND decision.projection_run_id = NEW.projection_run_id
                      AND decision.decision_id = NEW.decision_id
                      AND decision.canonical_relationship_id =
                          NEW.canonical_relationship_id
                      AND decision.state = 'accepted'
                ) INTO valid_link;
            END IF;
            IF valid_link IS DISTINCT FROM TRUE THEN
                RAISE EXCEPTION 'current relationship requires one accepted durable decision'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_validate_current_relationship_decision "
        "AFTER INSERT ON knowledge.current_relationship_projection "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.validate_current_relationship_decision()"
    )


def upgrade() -> None:
    _create_run_table()
    _create_shared_membership_tables()
    _create_typed_assertion_table()
    _create_typed_decision_tables()
    _create_outcome_table()
    _create_current_table()
    for table in NEW_TABLES:
        _install_append_only(table)
    _create_candidate_release_guard()
    _create_endpoint_validator()
    _create_current_decision_validator()


def downgrade() -> None:
    lock_tables = ", ".join(
        f"knowledge.{table}"
        for table in (
            *NEW_TABLES,
            "relationship_decision",
            "relationship_decision_assertion",
        )
    )
    op.execute(f"LOCK TABLE {lock_tables} IN ACCESS EXCLUSIVE MODE")
    predicates = " OR ".join(
        f"EXISTS (SELECT 1 FROM knowledge.{table})" for table in NEW_TABLES
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0010 downgrade requires empty relationship projection tables'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER trg_validate_current_relationship_decision "
        "ON knowledge.current_relationship_projection"
    )
    op.execute("DROP FUNCTION knowledge.validate_current_relationship_decision()")
    for table in reversed(
        (
            "typed_relationship_assertion",
            "typed_relationship_decision",
            "current_relationship_projection",
        )
    ):
        op.execute(
            "DROP TRIGGER trg_validate_typed_relationship_endpoints "
            f"ON knowledge.{table}"
        )
    op.execute("DROP FUNCTION knowledge.validate_typed_relationship_endpoints()")
    op.execute("DROP FUNCTION knowledge.relationship_endpoint_exists(text, jsonb)")
    for table in reversed(RELEASE_SCOPED_TABLES):
        op.execute(
            "DROP TRIGGER trg_validate_relationship_candidate_release "
            f"ON knowledge.{table}"
        )
    op.execute(
        "DROP FUNCTION knowledge.validate_relationship_projection_candidate_release()"
    )
    for table in reversed(NEW_TABLES):
        _drop_append_only(table)
        op.drop_table(table, schema="knowledge")
