"""Harden canonical decision evidence and append-only constraint outcomes.

Revision ID: C2_0005
Revises: C2_0004
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0005"
down_revision: Union[str, None] = "C2_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DECISION_TABLES = (
    "identity_decision",
    "canonical_decision",
    "relationship_decision",
)

DECISION_ASSERTION_TABLES = (
    "canonical_decision_assertion",
    "relationship_decision_assertion",
)

OUTCOME_TABLES = (
    "canonical_decision_constraint_outcome",
    "relationship_decision_constraint_outcome",
)

CONTEXT_SNAPSHOT_TABLES = (
    "canonical_decision_identity_context",
    "relationship_decision_identity_context",
)


def _legacy_llm_trace_check() -> str:
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


def _create_trace_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.is_valid_structured_llm_trace(trace jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            edge_whitespace CONSTANT text :=
                ' ' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13);
            raw_base64 text;
            raw_bytes bytea;
            parsed_output jsonb;
        BEGIN
            IF jsonb_typeof(trace) <> 'object'
               OR NOT (trace ?& ARRAY[
                   'provider',
                   'model',
                   'prompt_version',
                   'schema_version',
                   'input_evidence_ids',
                   'raw_output_base64',
                   'output_sha256',
                   'validated_output'
               ])
               OR jsonb_typeof(trace->'provider') <> 'string'
               OR length(btrim(trace->>'provider', edge_whitespace)) = 0
               OR trace->>'provider' IS DISTINCT FROM
                  btrim(trace->>'provider', edge_whitespace)
               OR jsonb_typeof(trace->'model') <> 'string'
               OR length(btrim(trace->>'model', edge_whitespace)) = 0
               OR trace->>'model' IS DISTINCT FROM
                  btrim(trace->>'model', edge_whitespace)
               OR jsonb_typeof(trace->'prompt_version') <> 'string'
               OR length(btrim(trace->>'prompt_version', edge_whitespace)) = 0
               OR trace->>'prompt_version' IS DISTINCT FROM
                  btrim(trace->>'prompt_version', edge_whitespace)
               OR jsonb_typeof(trace->'schema_version') <> 'string'
               OR length(btrim(trace->>'schema_version', edge_whitespace)) = 0
               OR trace->>'schema_version' IS DISTINCT FROM
                  btrim(trace->>'schema_version', edge_whitespace)
               OR jsonb_typeof(trace->'input_evidence_ids') <> 'array'
               OR jsonb_array_length(trace->'input_evidence_ids') = 0
               OR jsonb_typeof(trace->'raw_output_base64') <> 'string'
               OR jsonb_typeof(trace->'output_sha256') <> 'string'
               OR (trace->>'output_sha256') !~ '^[0-9a-f]{64}$'
               OR jsonb_typeof(trace->'validated_output') <> 'object'
            THEN
                RETURN FALSE;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM jsonb_array_elements(trace->'input_evidence_ids') AS item(value)
                WHERE jsonb_typeof(item.value) <> 'string'
                   OR length(btrim(item.value #>> '{}', edge_whitespace)) = 0
                   OR item.value #>> '{}' IS DISTINCT FROM
                      btrim(item.value #>> '{}', edge_whitespace)
            ) THEN
                RETURN FALSE;
            END IF;

            IF (
                SELECT count(*) <>
                       count(DISTINCT convert_to(
                           btrim(item.value #>> '{}', edge_whitespace),
                           'UTF8'
                       ))
                FROM jsonb_array_elements(trace->'input_evidence_ids') AS item(value)
            ) THEN
                RETURN FALSE;
            END IF;

            raw_base64 := trace->>'raw_output_base64';
            IF raw_base64 !~
               '^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$'
            THEN
                RETURN FALSE;
            END IF;

            raw_bytes := decode(raw_base64, 'base64');
            IF replace(encode(raw_bytes, 'base64'), E'\n', '') <> raw_base64
               OR encode(sha256(raw_bytes), 'hex') <> trace->>'output_sha256'
            THEN
                RETURN FALSE;
            END IF;

            parsed_output := convert_from(raw_bytes, 'UTF8')::jsonb;
            RETURN jsonb_typeof(parsed_output) = 'object'
               AND parsed_output = trace->'validated_output';
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )


def _create_json_string_array_validator() -> None:
    op.execute(
        """
        CREATE FUNCTION knowledge.is_json_string_array(candidate jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            edge_whitespace CONSTANT text :=
                ' ' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13);
            item jsonb;
            raw_token text;
            canonical_token text;
            canonical_bytes bytea;
            seen_tokens bytea[] := ARRAY[]::bytea[];
        BEGIN
            IF jsonb_typeof(candidate) <> 'array' THEN
                RETURN FALSE;
            END IF;

            FOR item IN
                SELECT element.value
                FROM jsonb_array_elements(candidate) AS element(value)
            LOOP
                IF jsonb_typeof(item) <> 'string' THEN
                    RETURN FALSE;
                END IF;
                raw_token := item #>> '{}';
                canonical_token := btrim(raw_token, edge_whitespace);
                canonical_bytes := convert_to(canonical_token, 'UTF8');
                IF length(canonical_token) = 0
                   OR raw_token IS DISTINCT FROM canonical_token
                   OR canonical_bytes = ANY(seen_tokens)
                THEN
                    RETURN FALSE;
                END IF;
                seen_tokens := array_append(seen_tokens, canonical_bytes);
            END LOOP;
            RETURN TRUE;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )


def _preflight_existing_rows() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM knowledge.canonical_decision
            ) OR EXISTS (
                SELECT 1 FROM knowledge.relationship_decision
            ) THEN
                RAISE EXCEPTION
                    'C2_0005 requires empty field and relationship decision history because decision-time identity contexts cannot be inferred safely'
                    USING ERRCODE = '55000';
            END IF;

            IF EXISTS (
                SELECT 1 FROM knowledge.identity_decision
                WHERE method = 'structured_llm'
                  AND knowledge.is_valid_structured_llm_trace(llm_trace)
                      IS DISTINCT FROM TRUE
            ) OR EXISTS (
                SELECT 1 FROM knowledge.canonical_decision
                WHERE method = 'structured_llm'
                  AND knowledge.is_valid_structured_llm_trace(llm_trace)
                      IS DISTINCT FROM TRUE
            ) OR EXISTS (
                SELECT 1 FROM knowledge.relationship_decision
                WHERE method = 'structured_llm'
                  AND knowledge.is_valid_structured_llm_trace(llm_trace)
                      IS DISTINCT FROM TRUE
            ) THEN
                RAISE EXCEPTION
                    'C2_0005 requires every existing structured LLM decision trace to be content-bound; migration will not invent raw output bytes'
                    USING ERRCODE = '55000';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM knowledge.canonical_decision_assertion
                WHERE assertion_role IN ('selected', 'conflicting')
                GROUP BY release_id, decision_id, assertion_id
                HAVING count(*) > 1
            ) OR EXISTS (
                SELECT 1
                FROM knowledge.relationship_decision_assertion
                WHERE assertion_role IN ('selected', 'conflicting')
                GROUP BY release_id, decision_id, assertion_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'C2_0005 found assertions with both selected and conflicting roles; migration will not rewrite decision history'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )


def _create_outcome_table(*, relationship: bool) -> None:
    table = (
        "relationship_decision_constraint_outcome"
        if relationship
        else "canonical_decision_constraint_outcome"
    )
    decision_table = "relationship_decision" if relationship else "canonical_decision"
    assertion_table = "relationship_assertion" if relationship else "source_assertion"
    prefix = "relationship" if relationship else "canonical"
    op.create_table(
        table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("assertion_id", sa.Text(), nullable=False),
        sa.Column("admitted", sa.Boolean(), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            "assertion_id",
            name=f"pk_knowledge_{table}",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                f"knowledge.{decision_table}.release_id",
                f"knowledge.{decision_table}.decision_id",
            ],
            name=f"fk_knowledge_{prefix}_decision_outcome_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            [f"knowledge.{assertion_table}.assertion_id"],
            name=f"fk_knowledge_{prefix}_decision_outcome_assertion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "knowledge.is_json_string_array(reason_codes)",
            name=f"ck_knowledge_{prefix}_decision_outcome_reason_codes",
        ),
        sa.CheckConstraint(
            "(admitted AND jsonb_array_length(reason_codes) = 0) OR "
            "(NOT admitted AND jsonb_array_length(reason_codes) > 0)",
            name=f"ck_knowledge_{prefix}_decision_outcome_admission",
        ),
        schema="knowledge",
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON "
        f"knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON knowledge.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION knowledge.reject_append_only_mutation()"
    )


def _create_identity_context_snapshot_table(*, relationship: bool) -> None:
    table = (
        "relationship_decision_identity_context"
        if relationship
        else "canonical_decision_identity_context"
    )
    decision_table = "relationship_decision" if relationship else "canonical_decision"
    prefix = "relationship" if relationship else "canonical"
    op.create_table(
        table,
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column(
            "canonical_identity_contexts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_identity_contexts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_id",
            name=f"pk_knowledge_{table}",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "decision_id"],
            [
                f"knowledge.{decision_table}.release_id",
                f"knowledge.{decision_table}.decision_id",
            ],
            name=f"fk_knowledge_{prefix}_decision_identity_context_decision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_identity_contexts) = 'array' AND "
            "jsonb_array_length(canonical_identity_contexts) > 0",
            name=f"ck_knowledge_{prefix}_decision_canonical_contexts",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_identity_contexts) = 'array' AND "
            "jsonb_array_length(source_identity_contexts) > 0",
            name=f"ck_knowledge_{prefix}_decision_source_contexts",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=f"ck_knowledge_{prefix}_decision_context_sha256",
        ),
        schema="knowledge",
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_mutation BEFORE UPDATE OR DELETE ON "
        f"knowledge.{table} FOR EACH ROW EXECUTE FUNCTION "
        "knowledge.reject_append_only_mutation()"
    )
    op.execute(
        f"CREATE TRIGGER trg_reject_truncate BEFORE TRUNCATE ON knowledge.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION knowledge.reject_append_only_mutation()"
    )


def upgrade() -> None:
    _create_trace_validator()
    _preflight_existing_rows()

    for table in DECISION_TABLES:
        op.drop_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            schema="knowledge",
            type_="check",
        )
        op.create_check_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            "method <> 'structured_llm' OR (llm_trace IS NOT NULL AND "
            "knowledge.is_valid_structured_llm_trace(llm_trace))",
            schema="knowledge",
        )

    for table in DECISION_ASSERTION_TABLES:
        op.create_index(
            f"uq_knowledge_{table}_terminal_role",
            table,
            ["release_id", "decision_id", "assertion_id"],
            unique=True,
            schema="knowledge",
            postgresql_where=sa.text("assertion_role IN ('selected', 'conflicting')"),
        )

    _create_json_string_array_validator()
    _create_outcome_table(relationship=False)
    _create_outcome_table(relationship=True)
    _create_identity_context_snapshot_table(relationship=False)
    _create_identity_context_snapshot_table(relationship=True)


def downgrade() -> None:
    op.execute(
        "LOCK TABLE knowledge.canonical_decision_constraint_outcome, "
        "knowledge.relationship_decision_constraint_outcome, "
        "knowledge.canonical_decision_identity_context, "
        "knowledge.relationship_decision_identity_context "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM knowledge.canonical_decision_constraint_outcome
            ) OR EXISTS (
                SELECT 1 FROM knowledge.relationship_decision_constraint_outcome
            ) OR EXISTS (
                SELECT 1 FROM knowledge.canonical_decision_identity_context
            ) OR EXISTS (
                SELECT 1 FROM knowledge.relationship_decision_identity_context
            ) THEN
                RAISE EXCEPTION
                    'C2_0005 downgrade requires empty outcome and identity-context ledgers; append-only decision history will not be discarded'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )

    for table in reversed(CONTEXT_SNAPSHOT_TABLES):
        op.drop_table(table, schema="knowledge")
    for table in reversed(OUTCOME_TABLES):
        op.drop_table(table, schema="knowledge")
    op.execute("DROP FUNCTION knowledge.is_json_string_array(jsonb)")

    for table in reversed(DECISION_ASSERTION_TABLES):
        op.drop_index(
            f"uq_knowledge_{table}_terminal_role",
            table_name=table,
            schema="knowledge",
        )

    legacy_trace_check = _legacy_llm_trace_check()
    for table in reversed(DECISION_TABLES):
        op.drop_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            schema="knowledge",
            type_="check",
        )
        op.create_check_constraint(
            f"ck_knowledge_{table}_structured_llm_trace",
            table,
            legacy_trace_check,
            schema="knowledge",
        )
    op.execute("DROP FUNCTION knowledge.is_valid_structured_llm_trace(jsonb)")
