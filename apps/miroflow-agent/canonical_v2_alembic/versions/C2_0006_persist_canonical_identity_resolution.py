"""Persist immutable offline canonical identity resolution projections.

Revision ID: C2_0006
Revises: C2_0005
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0006"
down_revision: Union[str, None] = "C2_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = (
    "identity_resolution_run",
    "identity_candidate_verdict",
    "identity_decision_context",
    "identity_decision_assertion",
    "canonical_identity_source_membership",
    "identity_decision_output_source",
    "canonical_identity_lineage",
    "current_source_identity_assignment",
)

EXISTING_IDENTITY_TABLES = (
    "identity_decision",
    "canonical_identity",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_record",
)

IDENTITY_LOCK_ORDER = (
    "identity_resolution_run",
    "identity_candidate_verdict",
    "identity_decision",
    "identity_decision_context",
    "canonical_identity",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_record",
    "identity_decision_assertion",
    "canonical_identity_source_membership",
    "identity_decision_output_source",
    "canonical_identity_lineage",
    "current_source_identity_assignment",
)

ACTION_ALLOCATION_TABLES = (
    "identity_decision",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_output_source",
)

RELEASE_PROJECTION_TABLES = (
    "identity_resolution_run",
    "identity_candidate_verdict",
    "identity_decision",
    "identity_decision_context",
    "canonical_identity",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_record",
    "identity_decision_assertion",
    "canonical_identity_source_membership",
    "identity_decision_output_source",
    "canonical_identity_lineage",
    "current_source_identity_assignment",
)


def _install_append_only(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON "
        f"knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON knowledge.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )


def _drop_append_only(table: str) -> None:
    op.execute(f"DROP TRIGGER trg_reject_truncate ON knowledge.{table}")
    op.execute(f"DROP TRIGGER trg_reject_mutation ON knowledge.{table}")


def _lock_and_preflight_existing_identity_history() -> None:
    tables = ", ".join(f"knowledge.{table}" for table in EXISTING_IDENTITY_TABLES)
    op.execute(f"LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE")
    predicates = " OR ".join(
        f"EXISTS (SELECT 1 FROM knowledge.{table})"
        for table in EXISTING_IDENTITY_TABLES
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0006 requires empty identity history because exact decision-time output allocation and current assignment provenance cannot be inferred safely'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )


def _create_projection_validators() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_canonical_membership_entity_type()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            canonical_type text;
            source_type text;
        BEGIN
            SELECT entity_type INTO canonical_type
            FROM knowledge.canonical_identity
            WHERE release_id = NEW.release_id
              AND canonical_identity_id = NEW.canonical_identity_id;
            SELECT entity_type INTO source_type
            FROM knowledge.source_identity
            WHERE source_identity_id = NEW.source_identity_id;
            IF canonical_type IS NOT NULL
               AND source_type IS NOT NULL
               AND canonical_type IS DISTINCT FROM source_type
            THEN
                RAISE EXCEPTION
                    'canonical/source identity entity types must match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_current_assignment_owner()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            owner_state text;
        BEGIN
            SELECT state INTO owner_state
            FROM knowledge.canonical_identity
            WHERE release_id = NEW.release_id
              AND canonical_identity_id = NEW.canonical_identity_id;
            IF owner_state IS NOT NULL AND owner_state <> 'active' THEN
                RAISE EXCEPTION
                    'current source assignment requires an active canonical owner'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_validate_entity_type BEFORE INSERT ON "
        "knowledge.canonical_identity_source_membership FOR EACH ROW EXECUTE "
        "FUNCTION knowledge.validate_canonical_membership_entity_type()"
    )
    op.execute(
        "CREATE TRIGGER trg_validate_active_owner BEFORE INSERT ON "
        "knowledge.current_source_identity_assignment FOR EACH ROW EXECUTE "
        "FUNCTION knowledge.validate_current_assignment_owner()"
    )


def _create_deferred_action_allocation_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_identity_action_allocation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            decision_action text;
            source_count bigint;
            input_count bigint;
            output_count bigint;
            allocation_count bigint;
            allocated_output_count bigint;
            link_endpoints_match boolean;
        BEGIN
            SELECT
                decision.action,
                (
                    SELECT count(*)
                    FROM knowledge.identity_decision_source_identity AS source
                    WHERE source.release_id = decision.release_id
                      AND source.decision_id = decision.decision_id
                ),
                (
                    SELECT count(*)
                    FROM knowledge.identity_decision_input AS input
                    WHERE input.release_id = decision.release_id
                      AND input.decision_id = decision.decision_id
                ),
                (
                    SELECT count(*)
                    FROM knowledge.identity_decision_output AS output
                    WHERE output.release_id = decision.release_id
                      AND output.decision_id = decision.decision_id
                ),
                (
                    SELECT count(*)
                    FROM knowledge.identity_decision_output_source AS allocation
                    WHERE allocation.release_id = decision.release_id
                      AND allocation.decision_id = decision.decision_id
                ),
                (
                    SELECT count(DISTINCT allocation.canonical_identity_id)
                    FROM knowledge.identity_decision_output_source AS allocation
                    WHERE allocation.release_id = decision.release_id
                      AND allocation.decision_id = decision.decision_id
                ),
                NOT EXISTS (
                    SELECT input.canonical_identity_id
                    FROM knowledge.identity_decision_input AS input
                    WHERE input.release_id = decision.release_id
                      AND input.decision_id = decision.decision_id
                    EXCEPT
                    SELECT output.canonical_identity_id
                    FROM knowledge.identity_decision_output AS output
                    WHERE output.release_id = decision.release_id
                      AND output.decision_id = decision.decision_id
                ) AND NOT EXISTS (
                    SELECT output.canonical_identity_id
                    FROM knowledge.identity_decision_output AS output
                    WHERE output.release_id = decision.release_id
                      AND output.decision_id = decision.decision_id
                    EXCEPT
                    SELECT input.canonical_identity_id
                    FROM knowledge.identity_decision_input AS input
                    WHERE input.release_id = decision.release_id
                      AND input.decision_id = decision.decision_id
                )
            INTO
                decision_action,
                source_count,
                input_count,
                output_count,
                allocation_count,
                allocated_output_count,
                link_endpoints_match
            FROM knowledge.identity_decision AS decision
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;

            IF decision_action IS NULL THEN
                RETURN NEW;
            END IF;

            IF source_count = 0 OR NOT (CASE decision_action
                WHEN 'create' THEN input_count = 0 AND output_count = 1
                WHEN 'link' THEN
                    input_count = 1
                    AND output_count = 1
                    AND link_endpoints_match
                WHEN 'merge' THEN input_count >= 2 AND output_count = 1
                WHEN 'split' THEN input_count = 1 AND output_count >= 2
                WHEN 'reject' THEN output_count = 0
                WHEN 'reverse' THEN input_count >= 1 AND output_count >= 1
                ELSE FALSE
            END) THEN
                RAISE EXCEPTION 'identity decision action shape is invalid'
                    USING ERRCODE = '23514';
            END IF;

            IF decision_action <> 'reject'
               AND (
                   allocation_count <> source_count
                   OR allocated_output_count <> output_count
               )
            THEN
                RAISE EXCEPTION
                    'identity decision output allocation is incomplete'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in ACTION_ALLOCATION_TABLES:
        op.execute(
            "CREATE CONSTRAINT TRIGGER "
            "trg_validate_identity_action_allocation "
            f"AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_identity_action_allocation()"
        )


def _drop_deferred_action_allocation_validator() -> None:
    for table in ACTION_ALLOCATION_TABLES:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_validate_identity_action_allocation "
            f"ON knowledge.{table}"
        )
    op.execute(
        "DROP FUNCTION IF EXISTS knowledge.validate_identity_action_allocation()"
    )


def _create_deferred_release_projection_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.validate_identity_resolution_release()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM knowledge.identity_decision AS decision
                LEFT JOIN knowledge.identity_decision_context AS context
                  ON context.release_id = decision.release_id
                 AND context.decision_id = decision.decision_id
                LEFT JOIN knowledge.identity_resolution_run AS resolution_run
                  ON resolution_run.release_id = context.release_id
                 AND resolution_run.decision_run_id = context.decision_run_id
                WHERE decision.release_id = NEW.release_id
                  AND (
                      context.decision_id IS NULL
                      OR resolution_run.release_id IS NULL
                  )
            ) THEN
                RAISE EXCEPTION
                    'every identity decision requires its exact context and containing run'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM knowledge.canonical_identity AS identity
                WHERE identity.release_id = NEW.release_id
                  AND (
                      (
                          identity.state = 'active'
                          AND NOT EXISTS (
                              SELECT 1
                              FROM knowledge.identity_decision_output AS output
                              WHERE output.release_id = identity.release_id
                                AND output.decision_id =
                                    identity.identity_decision_id
                                AND output.canonical_identity_id =
                                    identity.canonical_identity_id
                          )
                      )
                      OR (
                          identity.state = 'merged'
                          AND NOT EXISTS (
                              SELECT 1
                              FROM knowledge.identity_decision AS transition
                              JOIN knowledge.identity_decision_input AS input
                                ON input.release_id = transition.release_id
                               AND input.decision_id = transition.decision_id
                              WHERE transition.release_id = identity.release_id
                                AND transition.action = 'merge'
                                AND input.canonical_identity_id =
                                    identity.canonical_identity_id
                          )
                      )
                      OR (
                          identity.state = 'split'
                          AND NOT EXISTS (
                              SELECT 1
                              FROM knowledge.identity_decision AS transition
                              JOIN knowledge.identity_decision_input AS input
                                ON input.release_id = transition.release_id
                               AND input.decision_id = transition.decision_id
                              WHERE transition.release_id = identity.release_id
                                AND transition.action IN ('split', 'reverse')
                                AND input.canonical_identity_id =
                                    identity.canonical_identity_id
                          )
                      )
                      OR (
                          identity.state = 'rejected'
                          AND NOT EXISTS (
                              SELECT 1
                              FROM knowledge.identity_decision AS transition
                              WHERE transition.release_id = identity.release_id
                                AND transition.decision_id =
                                    identity.identity_decision_id
                                AND transition.action = 'reject'
                          )
                      )
                  )
            ) THEN
                RAISE EXCEPTION
                    'canonical state must match its current decision topology'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM (
                    (
                        SELECT
                            decision.decision_id,
                            input.canonical_identity_id AS predecessor_identity_id,
                            output.canonical_identity_id AS successor_identity_id,
                            decision.action AS transition
                        FROM knowledge.identity_decision AS decision
                        JOIN knowledge.identity_decision_input AS input
                          ON input.release_id = decision.release_id
                         AND input.decision_id = decision.decision_id
                        JOIN knowledge.identity_decision_output AS output
                          ON output.release_id = decision.release_id
                         AND output.decision_id = decision.decision_id
                        WHERE decision.release_id = NEW.release_id
                          AND decision.action IN ('merge', 'split', 'reverse')
                          AND input.canonical_identity_id <>
                              output.canonical_identity_id
                        EXCEPT
                        SELECT
                            lineage.decision_id,
                            lineage.predecessor_identity_id,
                            lineage.successor_identity_id,
                            lineage.transition
                        FROM knowledge.canonical_identity_lineage AS lineage
                        WHERE lineage.release_id = NEW.release_id
                    )
                    UNION ALL
                    (
                        SELECT
                            lineage.decision_id,
                            lineage.predecessor_identity_id,
                            lineage.successor_identity_id,
                            lineage.transition
                        FROM knowledge.canonical_identity_lineage AS lineage
                        WHERE lineage.release_id = NEW.release_id
                        EXCEPT
                        SELECT
                            decision.decision_id,
                            input.canonical_identity_id AS predecessor_identity_id,
                            output.canonical_identity_id AS successor_identity_id,
                            decision.action AS transition
                        FROM knowledge.identity_decision AS decision
                        JOIN knowledge.identity_decision_input AS input
                          ON input.release_id = decision.release_id
                         AND input.decision_id = decision.decision_id
                        JOIN knowledge.identity_decision_output AS output
                          ON output.release_id = decision.release_id
                         AND output.decision_id = decision.decision_id
                        WHERE decision.release_id = NEW.release_id
                          AND decision.action IN ('merge', 'split', 'reverse')
                          AND input.canonical_identity_id <>
                              output.canonical_identity_id
                    )
                ) AS mismatch
            ) THEN
                RAISE EXCEPTION
                    'canonical lineage must exactly equal lifecycle decision topology'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM knowledge.identity_decision_context AS context
                WHERE context.release_id = NEW.release_id
                  AND (
                      EXISTS (
                          SELECT evidence.value
                          FROM jsonb_array_elements_text(
                              context.supporting_assertion_ids
                          ) AS evidence(value)
                          EXCEPT
                          SELECT edge.assertion_id
                          FROM knowledge.identity_decision_assertion AS edge
                          WHERE edge.release_id = context.release_id
                            AND edge.decision_id = context.decision_id
                      )
                      OR EXISTS (
                          SELECT edge.assertion_id
                          FROM knowledge.identity_decision_assertion AS edge
                          WHERE edge.release_id = context.release_id
                            AND edge.decision_id = context.decision_id
                          EXCEPT
                          SELECT evidence.value
                          FROM jsonb_array_elements_text(
                              context.supporting_assertion_ids
                          ) AS evidence(value)
                      )
                  )
            ) THEN
                RAISE EXCEPTION
                    'identity context evidence must exactly equal its assertion edge set'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM knowledge.identity_decision AS decision
                WHERE decision.release_id = NEW.release_id
                  AND decision.method = 'structured_llm'
                  AND (
                      EXISTS (
                          SELECT evidence.value
                          FROM jsonb_array_elements_text(
                              decision.llm_trace->'input_evidence_ids'
                          ) AS evidence(value)
                          EXCEPT
                          SELECT edge.assertion_id
                          FROM knowledge.identity_decision_assertion AS edge
                          WHERE edge.release_id = decision.release_id
                            AND edge.decision_id = decision.decision_id
                      )
                      OR EXISTS (
                          SELECT edge.assertion_id
                          FROM knowledge.identity_decision_assertion AS edge
                          WHERE edge.release_id = decision.release_id
                            AND edge.decision_id = decision.decision_id
                          EXCEPT
                          SELECT evidence.value
                          FROM jsonb_array_elements_text(
                              decision.llm_trace->'input_evidence_ids'
                          ) AS evidence(value)
                      )
                  )
            ) THEN
                RAISE EXCEPTION
                    'structured LLM evidence must exactly equal its decision edge set'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM (
                    (
                        SELECT
                            membership.canonical_identity_id,
                            membership.source_identity_id
                        FROM knowledge.canonical_identity_source_membership
                            AS membership
                        JOIN knowledge.canonical_identity AS identity
                          ON identity.release_id = membership.release_id
                         AND identity.canonical_identity_id =
                             membership.canonical_identity_id
                        WHERE membership.release_id = NEW.release_id
                          AND identity.state = 'active'
                        EXCEPT
                        SELECT
                            assignment.canonical_identity_id,
                            assignment.source_identity_id
                        FROM knowledge.current_source_identity_assignment
                            AS assignment
                        WHERE assignment.release_id = NEW.release_id
                    )
                    UNION ALL
                    (
                        SELECT
                            assignment.canonical_identity_id,
                            assignment.source_identity_id
                        FROM knowledge.current_source_identity_assignment
                            AS assignment
                        WHERE assignment.release_id = NEW.release_id
                        EXCEPT
                        SELECT
                            membership.canonical_identity_id,
                            membership.source_identity_id
                        FROM knowledge.canonical_identity_source_membership
                            AS membership
                        JOIN knowledge.canonical_identity AS identity
                          ON identity.release_id = membership.release_id
                         AND identity.canonical_identity_id =
                             membership.canonical_identity_id
                        WHERE membership.release_id = NEW.release_id
                          AND identity.state = 'active'
                    )
                ) AS mismatch
            ) THEN
                RAISE EXCEPTION
                    'active membership must exactly equal current assignment'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in RELEASE_PROJECTION_TABLES:
        op.execute(
            "CREATE CONSTRAINT TRIGGER trg_validate_identity_resolution_release "
            f"AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_identity_resolution_release()"
        )


def _drop_deferred_release_projection_validator() -> None:
    for table in RELEASE_PROJECTION_TABLES:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_validate_identity_resolution_release "
            f"ON knowledge.{table}"
        )
    op.execute(
        "DROP FUNCTION IF EXISTS knowledge.validate_identity_resolution_release()"
    )


def upgrade() -> None:
    _lock_and_preflight_existing_identity_history()

    op.create_unique_constraint(
        "uq_knowledge_source_assertion_identity_record",
        "source_assertion",
        ["assertion_id", "source_identity_id", "source_record_id"],
        schema="knowledge",
    )

    op.create_table(
        "identity_resolution_run",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("identity_method_version", sa.Text(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("build_authority", sa.Text(), nullable=False),
        sa.Column(
            "request_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("request_content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "result_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "release_id", name="pk_knowledge_identity_resolution_run"
        ),
        sa.UniqueConstraint(
            "release_id",
            "decision_run_id",
            name="uq_knowledge_identity_resolution_run_identity",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_identity_resolution_run_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["knowledge.policy.policy_id", "knowledge.policy.policy_version"],
            name="fk_knowledge_identity_resolution_run_policy",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "build_authority = 'offline_canonical_build'",
            name="ck_knowledge_identity_resolution_run_authority",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(request_content) = 'object' AND "
            "jsonb_typeof(result_content) = 'object'",
            name="ck_knowledge_identity_resolution_run_content",
        ),
        sa.CheckConstraint(
            "request_content_sha256 ~ '^[0-9a-f]{64}$' AND "
            "result_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_knowledge_identity_resolution_run_sha256",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_candidate_verdict",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("verdict_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "verdict_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "verdict_id",
            name="pk_knowledge_identity_candidate_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_run_id"],
            [
                "knowledge.identity_resolution_run.release_id",
                "knowledge.identity_resolution_run.decision_run_id",
            ],
            name="fk_knowledge_identity_candidate_verdict_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "verdict IN ('same_entity', 'different_entities', 'unresolved')",
            name="ck_knowledge_identity_candidate_verdict_value",
        ),
        sa.CheckConstraint(
            "method IN ('deterministic', 'structured_llm', 'human_review', 'composite')",
            name="ck_knowledge_identity_candidate_verdict_method",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_identity_candidate_verdict_confidence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(verdict_content) = 'object' AND "
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_knowledge_identity_candidate_verdict_content",
        ),
        sa.UniqueConstraint(
            "release_id",
            "decision_run_id",
            "verdict_id",
            name="uq_knowledge_identity_candidate_verdict_run",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_decision_context",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column("candidate_verdict_id", sa.Text(), nullable=True),
        sa.Column(
            "context_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "supporting_assertion_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            name="pk_knowledge_identity_decision_context",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_run_id"],
            [
                "knowledge.identity_resolution_run.release_id",
                "knowledge.identity_resolution_run.decision_run_id",
            ],
            name="fk_knowledge_identity_decision_context_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_run_id", "candidate_verdict_id"],
            [
                "knowledge.identity_candidate_verdict.release_id",
                "knowledge.identity_candidate_verdict.decision_run_id",
                "knowledge.identity_candidate_verdict.verdict_id",
            ],
            name="fk_knowledge_identity_decision_context_verdict",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.identity_decision.release_id",
                "knowledge.identity_decision.decision_id",
            ],
            name="fk_knowledge_identity_decision_context_decision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(context_content) = 'object' AND "
            "content_sha256 ~ '^[0-9a-f]{64}$' AND "
            "context_content->>'content_sha256' = content_sha256",
            name="ck_knowledge_identity_decision_context_sha256",
        ),
        sa.CheckConstraint(
            "knowledge.is_json_string_array(supporting_assertion_ids) AND "
            "jsonb_array_length(supporting_assertion_ids) > 0",
            name="ck_knowledge_identity_decision_context_assertions",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_decision_assertion",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            name="pk_knowledge_identity_decision_assertion",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                "knowledge.identity_decision_context.release_id",
                "knowledge.identity_decision_context.decision_id",
            ],
            name="fk_knowledge_identity_decision_assertion_context",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id", "source_identity_id", "source_record_id"],
            [
                "knowledge.source_assertion.assertion_id",
                "knowledge.source_assertion.source_identity_id",
                "knowledge.source_assertion.source_record_id",
            ],
            name="fk_knowledge_identity_decision_assertion_assertion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "source_identity_id"],
            [
                "knowledge.identity_decision_source_identity.release_id",
                "knowledge.identity_decision_source_identity.decision_id",
                "knowledge.identity_decision_source_identity.source_identity_id",
            ],
            name="fk_knowledge_identity_decision_assertion_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "source_record_id"],
            [
                "knowledge.identity_decision_record.release_id",
                "knowledge.identity_decision_record.decision_id",
                "knowledge.identity_decision_record.record_id",
            ],
            name="fk_knowledge_identity_decision_assertion_record",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    op.create_table(
        "canonical_identity_source_membership",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "canonical_identity_id",
            "source_identity_id",
            name="pk_knowledge_canonical_identity_source_membership",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_membership_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_identity_id"],
            ["knowledge.source_identity.source_identity_id"],
            name="fk_knowledge_canonical_membership_source",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    op.create_table(
        "identity_decision_output_source",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "source_identity_id",
            name="pk_knowledge_identity_decision_output_source",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "canonical_identity_id"],
            [
                "knowledge.identity_decision_output.release_id",
                "knowledge.identity_decision_output.decision_id",
                "knowledge.identity_decision_output.canonical_identity_id",
            ],
            name="fk_knowledge_identity_output_source_output",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "source_identity_id"],
            [
                "knowledge.identity_decision_source_identity.release_id",
                "knowledge.identity_decision_source_identity.decision_id",
                "knowledge.identity_decision_source_identity.source_identity_id",
            ],
            name="fk_knowledge_identity_output_source_decision_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id", "source_identity_id"],
            [
                "knowledge.canonical_identity_source_membership.release_id",
                "knowledge.canonical_identity_source_membership.canonical_identity_id",
                "knowledge.canonical_identity_source_membership.source_identity_id",
            ],
            name="fk_knowledge_identity_output_source_membership",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    op.create_table(
        "canonical_identity_lineage",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("predecessor_identity_id", sa.Text(), nullable=False),
        sa.Column("successor_identity_id", sa.Text(), nullable=False),
        sa.Column("transition", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "predecessor_identity_id",
            "successor_identity_id",
            name="pk_knowledge_canonical_identity_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "predecessor_identity_id"],
            [
                "knowledge.identity_decision_input.release_id",
                "knowledge.identity_decision_input.decision_id",
                "knowledge.identity_decision_input.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_lineage_input",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id", "successor_identity_id"],
            [
                "knowledge.identity_decision_output.release_id",
                "knowledge.identity_decision_output.decision_id",
                "knowledge.identity_decision_output.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_lineage_output",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "predecessor_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_lineage_predecessor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "successor_identity_id"],
            [
                "knowledge.canonical_identity.release_id",
                "knowledge.canonical_identity.canonical_identity_id",
            ],
            name="fk_knowledge_canonical_lineage_successor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "predecessor_identity_id <> successor_identity_id",
            name="ck_knowledge_canonical_identity_lineage_not_self",
        ),
        sa.CheckConstraint(
            "transition IN ('link', 'merge', 'split', 'reverse')",
            name="ck_knowledge_canonical_identity_lineage_transition",
        ),
        schema="knowledge",
    )

    op.create_table(
        "current_source_identity_assignment",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("source_identity_id", sa.Text(), nullable=False),
        sa.Column("canonical_identity_id", sa.Text(), nullable=False),
        sa.Column("identity_decision_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "source_identity_id",
            name="pk_knowledge_current_source_identity_assignment",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "canonical_identity_id", "source_identity_id"],
            [
                "knowledge.canonical_identity_source_membership.release_id",
                "knowledge.canonical_identity_source_membership.canonical_identity_id",
                "knowledge.canonical_identity_source_membership.source_identity_id",
            ],
            name="fk_knowledge_current_assignment_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "identity_decision_id", "source_identity_id"],
            [
                "knowledge.identity_decision_source_identity.release_id",
                "knowledge.identity_decision_source_identity.decision_id",
                "knowledge.identity_decision_source_identity.source_identity_id",
            ],
            name="fk_knowledge_current_assignment_decision_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "identity_decision_id", "canonical_identity_id"],
            [
                "knowledge.identity_decision_output.release_id",
                "knowledge.identity_decision_output.decision_id",
                "knowledge.identity_decision_output.canonical_identity_id",
            ],
            name="fk_knowledge_current_assignment_decision_output",
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    _create_projection_validators()
    _create_deferred_action_allocation_validator()
    _create_deferred_release_projection_validator()
    for table in NEW_TABLES:
        _install_append_only(table)
    _install_append_only("canonical_identity")


def downgrade() -> None:
    lock_tables = ", ".join(f"knowledge.{table}" for table in IDENTITY_LOCK_ORDER)
    op.execute(f"LOCK TABLE {lock_tables} IN ACCESS EXCLUSIVE MODE")
    predicates = " OR ".join(
        f"EXISTS (SELECT 1 FROM knowledge.{table})"
        for table in (*NEW_TABLES, *EXISTING_IDENTITY_TABLES)
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0006 downgrade requires empty canonical identity resolution and identity history; append-only identity state will not be discarded'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )

    _drop_deferred_release_projection_validator()
    _drop_deferred_action_allocation_validator()
    _drop_append_only("canonical_identity")
    for table in reversed(NEW_TABLES):
        _drop_append_only(table)
        op.drop_table(table, schema="knowledge")
    op.execute(
        "ALTER TABLE knowledge.source_assertion DROP CONSTRAINT IF EXISTS "
        "uq_knowledge_source_assertion_identity_record"
    )
    op.execute("DROP FUNCTION IF EXISTS knowledge.validate_current_assignment_owner()")
    op.execute(
        "DROP FUNCTION IF EXISTS knowledge.validate_canonical_membership_entity_type()"
    )
