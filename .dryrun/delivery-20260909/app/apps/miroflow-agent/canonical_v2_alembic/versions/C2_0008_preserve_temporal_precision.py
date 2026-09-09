"""Preserve date-only versus instant validity precision.

Revision ID: C2_0008
Revises: C2_0007
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0008"
down_revision: Union[str, None] = "C2_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TEMPORAL_TABLES = (
    "source_assertion",
    "relationship_assertion",
    "relationship_decision",
)


def _canonical_datetime_sql(column: str) -> str:
    return f"knowledge.canonical_utc_datetime_text({column})"


def _temporal_check(table: str, bound: str) -> tuple[str, str]:
    temporal = f"{bound}_temporal"
    return (
        f"ck_knowledge_{table}_{bound}_temporal",
        f"({temporal} IS NULL AND {bound} IS NULL) OR ("
        f"knowledge.is_valid_temporal_value({temporal}) IS TRUE AND (("
        f"{temporal}->>'precision' = 'date' AND {bound} IS NULL) OR ("
        f"{temporal}->>'precision' = 'instant' AND {bound} IS NOT NULL AND "
        f"{bound} = ({temporal}->>'value')::timestamptz)))",
    )


def _source_assertion_payload(*, temporal: bool) -> str:
    valid_from = (
        "valid_from_temporal" if temporal else _canonical_datetime_sql("valid_from")
    )
    valid_to = "valid_to_temporal" if temporal else _canonical_datetime_sql("valid_to")
    return f"""
        jsonb_build_object(
            'assertion_id', assertion_id,
            'source_record_id', source_record_id,
            'source_identity_id', source_identity_id,
            'subject_entity_type', subject_entity_type,
            'field_path', field_path,
            'value', value,
            'observed_at', {_canonical_datetime_sql("observed_at")},
            'source_event_time', {_canonical_datetime_sql("source_event_time")},
            'valid_from', {valid_from},
            'valid_to', {valid_to},
            'assertion_run_id', assertion_run_id
        )
    """


def _relationship_assertion_payload(*, temporal: bool) -> str:
    valid_from = (
        "assertion.valid_from_temporal"
        if temporal
        else _canonical_datetime_sql("assertion.valid_from")
    )
    valid_to = (
        "assertion.valid_to_temporal"
        if temporal
        else _canonical_datetime_sql("assertion.valid_to")
    )
    return f"""
        jsonb_build_object(
            'assertion_id', assertion.assertion_id,
            'relationship_type_id', assertion.relationship_type_id,
            'relationship_type_version', assertion.relationship_type_version,
            'source_record_id', assertion.source_record_id,
            'source_endpoint', jsonb_build_object(
                'identity_id', assertion.source_identity_id,
                'identity_space', 'source',
                'entity_type', source_identity.entity_type
            ),
            'target_endpoint', jsonb_build_object(
                'identity_id', assertion.target_identity_id,
                'identity_space', 'source',
                'entity_type', target_identity.entity_type
            ),
            'attributes', assertion.attributes,
            'observed_at',
                {_canonical_datetime_sql("assertion.observed_at")},
            'source_event_time',
                {_canonical_datetime_sql("assertion.source_event_time")},
            'valid_from', {valid_from},
            'valid_to', {valid_to},
            'assertion_run_id', assertion.assertion_run_id
        )
    """


def _set_assertion_fingerprints(*, temporal: bool) -> None:
    for table in ("source_assertion", "relationship_assertion"):
        op.execute(f"ALTER TABLE knowledge.{table} DISABLE TRIGGER trg_reject_mutation")
    op.execute(
        "UPDATE knowledge.source_assertion SET assertion_fingerprint_sha256 = "
        f"knowledge.canonical_jsonb_sha256({_source_assertion_payload(temporal=temporal)})"
    )
    op.execute(
        f"""
        UPDATE knowledge.relationship_assertion AS assertion
        SET assertion_fingerprint_sha256 = knowledge.canonical_jsonb_sha256(
            {_relationship_assertion_payload(temporal=temporal)}
        )
        FROM knowledge.source_identity AS source_identity,
             knowledge.source_identity AS target_identity
        WHERE source_identity.source_identity_id = assertion.source_identity_id
          AND target_identity.source_identity_id = assertion.target_identity_id
        """
    )
    for table in ("source_assertion", "relationship_assertion"):
        op.execute(f"ALTER TABLE knowledge.{table} ENABLE TRIGGER trg_reject_mutation")


def _create_temporal_functions() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.canonical_utc_datetime_text(value timestamptz)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            utc_value timestamp;
            microseconds text;
            result text;
        BEGIN
            utc_value := value AT TIME ZONE 'UTC';
            microseconds := to_char(utc_value, 'US');
            result := to_char(utc_value, 'YYYY-MM-DD"T"HH24:MI:SS');
            IF microseconds <> '000000' THEN
                result := result || '.' || microseconds;
            END IF;
            RETURN result || 'Z';
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.temporal_instant_value(value timestamptz)
        RETURNS jsonb
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_build_object(
                'precision', 'instant',
                'value', knowledge.canonical_utc_datetime_text(value)
            )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_valid_temporal_value(value jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            raw_value text;
        BEGIN
            IF jsonb_typeof(value) <> 'object'
               OR NOT knowledge.jsonb_has_exact_keys(
                    value, ARRAY['precision', 'value']
               )
               OR jsonb_typeof(value->'precision') <> 'string'
               OR jsonb_typeof(value->'value') <> 'string'
            THEN
                RETURN FALSE;
            END IF;
            raw_value := value->>'value';
            IF value->>'precision' = 'date' THEN
                RETURN raw_value ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                   AND to_char(raw_value::date, 'YYYY-MM-DD') = raw_value;
            END IF;
            IF value->>'precision' = 'instant' THEN
                RETURN knowledge.is_canonical_utc_datetime(value->'value');
            END IF;
            RETURN FALSE;
        EXCEPTION
            WHEN datetime_field_overflow OR invalid_datetime_format THEN
                RETURN FALSE;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_valid_temporal_comparison_context(value jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(value) = 'object'
               AND knowledge.jsonb_has_exact_keys(
                    value, ARRAY['policy_version', 'calendar', 'timezone']
               )
               AND value->>'policy_version' = 'explicit-calendar-v1'
               AND value->>'calendar' = 'gregorian'
               AND knowledge.is_canonical_non_empty_string(value->>'timezone')
        $$
        """
    )


def _create_context_table() -> None:
    op.create_table(
        "decision_batch_temporal_context",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column(
            "comparison_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_run_id",
            name="pk_knowledge_decision_batch_temporal_context",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["knowledge.release.release_id"],
            name="fk_knowledge_decision_batch_temporal_context_release",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "knowledge.is_valid_temporal_comparison_context(comparison_context) "
            "IS TRUE",
            name="ck_knowledge_decision_batch_temporal_context_shape",
        ),
        sa.CheckConstraint(
            "content_sha256 = knowledge.canonical_jsonb_sha256(comparison_context)",
            name="ck_knowledge_decision_batch_temporal_context_hash",
        ),
        schema="knowledge",
    )
    op.execute(
        "CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON "
        "knowledge.decision_batch_temporal_context FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON "
        "knowledge.decision_batch_temporal_context FOR EACH STATEMENT EXECUTE "
        "FUNCTION knowledge.reject_append_only_mutation()"
    )


def _create_temporal_binding_validators() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_field_temporal_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            decision_state text;
        BEGIN
            SELECT decision.state INTO decision_state
            FROM knowledge.canonical_decision AS decision
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;
            IF NOT FOUND OR decision_state <> 'selected' THEN
                RETURN NEW;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM knowledge.canonical_decision_assertion AS left_edge
                JOIN knowledge.canonical_decision_assertion AS right_edge
                  ON right_edge.release_id = left_edge.release_id
                 AND right_edge.decision_id = left_edge.decision_id
                 AND right_edge.assertion_role = 'selected'
                JOIN knowledge.source_assertion AS left_assertion
                  ON left_assertion.assertion_id = left_edge.assertion_id
                JOIN knowledge.source_assertion AS right_assertion
                  ON right_assertion.assertion_id = right_edge.assertion_id
                WHERE left_edge.release_id = NEW.release_id
                  AND left_edge.decision_id = NEW.decision_id
                  AND left_edge.assertion_role = 'selected'
                  AND (
                      left_assertion.valid_from_temporal IS DISTINCT FROM
                          right_assertion.valid_from_temporal
                      OR left_assertion.valid_to_temporal IS DISTINCT FROM
                          right_assertion.valid_to_temporal
                  )
            ) THEN
                RAISE EXCEPTION
                    'field selected evidence has inconsistent temporal precision or value'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table, trigger in (
        ("canonical_decision", "trg_validate_field_temporal_binding"),
        (
            "canonical_decision_assertion",
            "trg_validate_field_assertion_temporal_binding",
        ),
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_field_temporal_binding()"
        )

    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_relationship_temporal_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            reviewed record;
            selected_valid_from jsonb;
            selected_valid_to jsonb;
        BEGIN
            SELECT decision.* INTO reviewed
            FROM knowledge.relationship_decision AS decision
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;
            IF NOT FOUND THEN
                RETURN NEW;
            END IF;
            IF reviewed.state <> 'accepted' THEN
                IF reviewed.valid_from_temporal IS NOT NULL
                   OR reviewed.valid_to_temporal IS NOT NULL
                THEN
                    RAISE EXCEPTION
                        'non-accepted relationship decision cannot carry temporal validity'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            SELECT assertion.valid_from_temporal, assertion.valid_to_temporal
            INTO selected_valid_from, selected_valid_to
            FROM knowledge.relationship_decision_assertion AS edge
            JOIN knowledge.relationship_assertion AS assertion
              ON assertion.assertion_id = edge.assertion_id
            WHERE edge.release_id = reviewed.release_id
              AND edge.decision_id = reviewed.decision_id
              AND edge.assertion_role = 'selected'
            ORDER BY edge.assertion_id
            LIMIT 1;
            IF NOT FOUND THEN
                RETURN NEW;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM knowledge.relationship_decision_assertion AS edge
                JOIN knowledge.relationship_assertion AS assertion
                  ON assertion.assertion_id = edge.assertion_id
                WHERE edge.release_id = reviewed.release_id
                  AND edge.decision_id = reviewed.decision_id
                  AND edge.assertion_role = 'selected'
                  AND (
                      assertion.valid_from_temporal IS DISTINCT FROM
                          selected_valid_from
                      OR assertion.valid_to_temporal IS DISTINCT FROM
                          selected_valid_to
                  )
            )
               OR reviewed.valid_from_temporal IS DISTINCT FROM selected_valid_from
               OR reviewed.valid_to_temporal IS DISTINCT FROM selected_valid_to
            THEN
                RAISE EXCEPTION
                    'relationship decision temporal validity does not exactly match selected evidence'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table, trigger in (
        (
            "relationship_decision",
            "trg_validate_relationship_temporal_binding",
        ),
        (
            "relationship_decision_assertion",
            "trg_validate_relationship_assertion_temporal_binding",
        ),
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_relationship_temporal_binding()"
        )


def _drop_temporal_binding_validators() -> None:
    for table, trigger in (
        (
            "relationship_decision_assertion",
            "trg_validate_relationship_assertion_temporal_binding",
        ),
        (
            "relationship_decision",
            "trg_validate_relationship_temporal_binding",
        ),
        (
            "canonical_decision_assertion",
            "trg_validate_field_assertion_temporal_binding",
        ),
        ("canonical_decision", "trg_validate_field_temporal_binding"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON knowledge.{table}")
    op.execute("DROP FUNCTION knowledge.validate_relationship_temporal_binding()")
    op.execute("DROP FUNCTION knowledge.validate_field_temporal_binding()")


def upgrade() -> None:
    op.execute("LOCK TABLE knowledge.release IN ACCESS EXCLUSIVE MODE")
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM knowledge.source_assertion AS assertion
                JOIN knowledge.canonical_decision_assertion AS edge
                  ON edge.assertion_id = assertion.assertion_id
                WHERE assertion.valid_from IS NOT NULL
                   OR assertion.valid_to IS NOT NULL
                UNION ALL
                SELECT 1
                FROM knowledge.relationship_assertion AS assertion
                JOIN knowledge.relationship_decision_assertion AS edge
                  ON edge.assertion_id = assertion.assertion_id
                WHERE assertion.valid_from IS NOT NULL
                   OR assertion.valid_to IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'C2_0008 refuses to rewrite temporal content identity for referenced decision evidence';
            END IF;
        END;
        $$
        """
    )
    _create_temporal_functions()
    for table in TEMPORAL_TABLES:
        op.execute(f"ALTER TABLE knowledge.{table} DISABLE TRIGGER trg_reject_mutation")
    for table in TEMPORAL_TABLES:
        for bound in ("valid_from", "valid_to"):
            op.add_column(
                table,
                sa.Column(
                    f"{bound}_temporal",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=True,
                ),
                schema="knowledge",
            )
            op.execute(
                f"UPDATE knowledge.{table} SET {bound}_temporal = "
                f"knowledge.temporal_instant_value({bound}) "
                f"WHERE {bound} IS NOT NULL"
            )
            constraint_name, expression = _temporal_check(table, bound)
            op.create_check_constraint(
                constraint_name, table, expression, schema="knowledge"
            )
    _set_assertion_fingerprints(temporal=True)
    for table in TEMPORAL_TABLES:
        op.execute(f"ALTER TABLE knowledge.{table} ENABLE TRIGGER trg_reject_mutation")
    _create_context_table()
    _create_temporal_binding_validators()


def downgrade() -> None:
    op.execute("LOCK TABLE knowledge.release IN ACCESS EXCLUSIVE MODE")
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM knowledge.source_assertion
                WHERE valid_from_temporal->>'precision' = 'date'
                   OR valid_to_temporal->>'precision' = 'date'
                UNION ALL
                SELECT 1 FROM knowledge.relationship_assertion
                WHERE valid_from_temporal->>'precision' = 'date'
                   OR valid_to_temporal->>'precision' = 'date'
                UNION ALL
                SELECT 1 FROM knowledge.relationship_decision
                WHERE valid_from_temporal->>'precision' = 'date'
                   OR valid_to_temporal->>'precision' = 'date'
                UNION ALL
                SELECT 1 FROM knowledge.decision_batch_temporal_context
            ) THEN
                RAISE EXCEPTION
                    'C2_0008 downgrade refuses to discard date precision or explicit temporal context';
            END IF;
        END;
        $$
        """
    )
    _drop_temporal_binding_validators()
    _set_assertion_fingerprints(temporal=False)
    op.drop_table("decision_batch_temporal_context", schema="knowledge")
    for table in reversed(TEMPORAL_TABLES):
        for bound in reversed(("valid_from", "valid_to")):
            op.drop_constraint(
                f"ck_knowledge_{table}_{bound}_temporal",
                table,
                schema="knowledge",
                type_="check",
            )
            op.drop_column(table, f"{bound}_temporal", schema="knowledge")
    op.execute("DROP FUNCTION knowledge.is_valid_temporal_comparison_context(jsonb)")
    op.execute("DROP FUNCTION knowledge.is_valid_temporal_value(jsonb)")
    op.execute("DROP FUNCTION knowledge.temporal_instant_value(timestamptz)")
    op.execute("DROP FUNCTION knowledge.canonical_utc_datetime_text(timestamptz)")
