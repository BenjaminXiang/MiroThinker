"""Bind human review decisions to immutable evidence and reviewer provenance.

Revision ID: C2_0007
Revises: C2_0006
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0007"
down_revision: Union[str, None] = "C2_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DECISION_REVIEW_FAMILIES = (
    ("canonical_decision", "field"),
    ("relationship_decision", "relationship"),
    ("identity_decision", "identity"),
)

DECISION_SUPERSESSION_UNIQUES = (
    (
        "canonical_decision",
        "uq_knowledge_canonical_decision_supersedes_once",
    ),
    (
        "relationship_decision",
        "uq_knowledge_relationship_decision_supersedes_once",
    ),
)

DECISION_ROOT_UNIQUES = (
    (
        "canonical_decision",
        "uq_knowledge_canonical_decision_one_root",
        ("canonical_identity_id", "field_path"),
    ),
    (
        "relationship_decision",
        "uq_knowledge_relationship_decision_one_root",
        ("canonical_relationship_id",),
    ),
)

# Preserve C2_0006's parent-first identity lock order before touching the three
# reviewed decision tables.  Its deferred validators read identity_decision while
# writers may still hold earlier identity-resolution rows; taking identity_decision
# first would deadlock a chained C2_0007 -> C2_0005 downgrade.
REVIEW_BOUNDARY_LOCK_ORDER = (
    "release",
    "identity_resolution_run",
    "identity_candidate_verdict",
    "canonical_decision",
    "relationship_decision",
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


def _lock_review_boundary() -> None:
    table_list = ", ".join(f"knowledge.{table}" for table in REVIEW_BOUNDARY_LOCK_ORDER)
    op.execute(f"LOCK TABLE {table_list} IN ACCESS EXCLUSIVE MODE")


def _reject_and_prevent_supersession_forks() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                WITH RECURSIVE ancestry(
                    origin_release_id,
                    release_id,
                    previous_release_id
                ) AS (
                    SELECT release_id, release_id, previous_release_id
                    FROM knowledge.release
                    UNION
                    SELECT ancestry.origin_release_id,
                           parent.release_id,
                           parent.previous_release_id
                    FROM ancestry
                    JOIN knowledge.release AS parent
                      ON parent.release_id = ancestry.previous_release_id
                )
                SELECT 1
                FROM ancestry
                WHERE previous_release_id = origin_release_id
            ) THEN
                RAISE EXCEPTION
                    'C2_0007 cannot freeze cyclic release history'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                WITH RECURSIVE release_ancestry(
                    descendant_release_id,
                    ancestor_release_id,
                    previous_release_id
                ) AS (
                    SELECT child.release_id,
                           parent.release_id,
                           parent.previous_release_id
                    FROM knowledge.release AS child
                    JOIN knowledge.release AS parent
                      ON parent.release_id = child.previous_release_id
                    UNION
                    SELECT release_ancestry.descendant_release_id,
                           parent.release_id,
                           parent.previous_release_id
                    FROM release_ancestry
                    JOIN knowledge.release AS parent
                      ON parent.release_id = release_ancestry.previous_release_id
                )
                SELECT 1
                FROM knowledge.canonical_decision AS child
                JOIN knowledge.canonical_decision AS predecessor
                  ON predecessor.decision_id = child.supersedes_decision_id
                WHERE child.supersedes_decision_id IS NOT NULL
                  AND (
                        child.canonical_identity_id IS DISTINCT FROM
                            predecessor.canonical_identity_id
                        OR child.field_path IS DISTINCT FROM predecessor.field_path
                        OR NOT EXISTS (
                            SELECT 1
                            FROM release_ancestry
                            WHERE descendant_release_id = child.release_id
                              AND ancestor_release_id = predecessor.release_id
                        )
                  )
                UNION ALL
                SELECT 1
                FROM knowledge.relationship_decision AS child
                JOIN knowledge.relationship_decision AS predecessor
                  ON predecessor.decision_id = child.supersedes_decision_id
                WHERE child.supersedes_decision_id IS NOT NULL
                  AND (
                        child.canonical_relationship_id IS DISTINCT FROM
                            predecessor.canonical_relationship_id
                        OR child.relationship_type_id IS DISTINCT FROM
                            predecessor.relationship_type_id
                        OR child.relationship_type_version IS DISTINCT FROM
                            predecessor.relationship_type_version
                        OR child.source_canonical_identity_id IS DISTINCT FROM
                            predecessor.source_canonical_identity_id
                        OR child.target_canonical_identity_id IS DISTINCT FROM
                            predecessor.target_canonical_identity_id
                        OR NOT EXISTS (
                            SELECT 1
                            FROM release_ancestry
                            WHERE descendant_release_id = child.release_id
                              AND ancestor_release_id = predecessor.release_id
                        )
                  )
            ) THEN
                RAISE EXCEPTION
                    'C2_0007 cannot preserve cross-wired or non-ancestral decision lineage'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    cycle_predicates = " OR ".join(
        "EXISTS (WITH RECURSIVE chain(origin_decision_id, decision_id, "
        "supersedes_decision_id) AS (SELECT decision_id, decision_id, "
        f"supersedes_decision_id FROM knowledge.{table} WHERE "
        "supersedes_decision_id IS NOT NULL UNION SELECT chain.origin_decision_id, "
        "predecessor.decision_id, predecessor.supersedes_decision_id FROM chain "
        f"JOIN knowledge.{table} AS predecessor ON predecessor.decision_id = "
        "chain.supersedes_decision_id) SELECT 1 FROM chain WHERE "
        "supersedes_decision_id = origin_decision_id)"
        for table, _ in DECISION_SUPERSESSION_UNIQUES
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {cycle_predicates} THEN
                RAISE EXCEPTION
                    'C2_0007 cannot preserve cyclic decision lineage'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    fork_predicates = tuple(
        "EXISTS (SELECT 1 FROM knowledge."
        f"{table} WHERE supersedes_decision_id IS NOT NULL "
        "GROUP BY supersedes_decision_id HAVING count(*) > 1)"
        for table, _ in DECISION_SUPERSESSION_UNIQUES
    )
    root_predicates = tuple(
        "EXISTS (SELECT 1 FROM knowledge."
        f"{table} WHERE supersedes_decision_id IS NULL GROUP BY "
        f"{', '.join(columns)} HAVING count(*) > 1)"
        for table, _, columns in DECISION_ROOT_UNIQUES
    )
    predicates = " OR ".join((*fork_predicates, *root_predicates))
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0007 cannot preserve decision history with an existing supersession fork'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    for table, constraint in DECISION_SUPERSESSION_UNIQUES:
        op.create_unique_constraint(
            constraint,
            table,
            ["supersedes_decision_id"],
            schema="knowledge",
        )
    for table, index, columns in DECISION_ROOT_UNIQUES:
        op.create_index(
            index,
            table,
            list(columns),
            schema="knowledge",
            unique=True,
            postgresql_where=sa.text("supersedes_decision_id IS NULL"),
        )


def _allow_supersession_forks_for_c2_0006_compatibility() -> None:
    for _, index, _ in reversed(DECISION_ROOT_UNIQUES):
        op.drop_index(index, schema="knowledge")
    for table, constraint in reversed(DECISION_SUPERSESSION_UNIQUES):
        op.drop_constraint(
            constraint,
            table,
            schema="knowledge",
            type_="unique",
        )


def _create_decision_lineage_validators() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_field_decision_lineage_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            predecessor record;
        BEGIN
            IF NEW.supersedes_decision_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT decision.*
            INTO predecessor
            FROM knowledge.canonical_decision AS decision
            WHERE decision.decision_id = NEW.supersedes_decision_id;
            IF NOT FOUND
               OR predecessor.canonical_identity_id IS DISTINCT FROM
                    NEW.canonical_identity_id
               OR predecessor.field_path IS DISTINCT FROM NEW.field_path
            THEN
                RAISE EXCEPTION
                    'field supersession predecessor is missing or cross-wired'
                    USING ERRCODE = '23514';
            END IF;
            IF predecessor.release_id = NEW.release_id
               OR NOT EXISTS (
                    WITH RECURSIVE ancestry(release_id, previous_release_id) AS (
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS child
                        JOIN knowledge.release AS parent
                          ON parent.release_id = child.previous_release_id
                        WHERE child.release_id = NEW.release_id
                        UNION
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS parent
                        JOIN ancestry
                          ON parent.release_id = ancestry.previous_release_id
                    )
                    SELECT 1 FROM ancestry
                    WHERE release_id = predecessor.release_id
               )
            THEN
                RAISE EXCEPTION
                    'field supersession must target a strict release ancestor'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_relationship_decision_lineage_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            predecessor record;
        BEGIN
            IF NEW.supersedes_decision_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT decision.*
            INTO predecessor
            FROM knowledge.relationship_decision AS decision
            WHERE decision.decision_id = NEW.supersedes_decision_id;
            IF NOT FOUND
               OR predecessor.canonical_relationship_id IS DISTINCT FROM
                    NEW.canonical_relationship_id
               OR predecessor.relationship_type_id IS DISTINCT FROM
                    NEW.relationship_type_id
               OR predecessor.relationship_type_version IS DISTINCT FROM
                    NEW.relationship_type_version
               OR predecessor.source_canonical_identity_id IS DISTINCT FROM
                    NEW.source_canonical_identity_id
               OR predecessor.target_canonical_identity_id IS DISTINCT FROM
                    NEW.target_canonical_identity_id
            THEN
                RAISE EXCEPTION
                    'relationship supersession predecessor is missing or cross-wired'
                    USING ERRCODE = '23514';
            END IF;
            IF predecessor.release_id = NEW.release_id
               OR NOT EXISTS (
                    WITH RECURSIVE ancestry(release_id, previous_release_id) AS (
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS child
                        JOIN knowledge.release AS parent
                          ON parent.release_id = child.previous_release_id
                        WHERE child.release_id = NEW.release_id
                        UNION
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS parent
                        JOIN ancestry
                          ON parent.release_id = ancestry.previous_release_id
                    )
                    SELECT 1 FROM ancestry
                    WHERE release_id = predecessor.release_id
               )
            THEN
                RAISE EXCEPTION
                    'relationship supersession must target a strict release ancestor'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_validate_field_decision_lineage_insert "
        "BEFORE INSERT ON knowledge.canonical_decision FOR EACH ROW "
        "EXECUTE FUNCTION knowledge.validate_field_decision_lineage_insert()"
    )
    op.execute(
        "CREATE TRIGGER trg_validate_relationship_decision_lineage_insert "
        "BEFORE INSERT ON knowledge.relationship_decision FOR EACH ROW "
        "EXECUTE FUNCTION knowledge.validate_relationship_decision_lineage_insert()"
    )


def _drop_decision_lineage_validators() -> None:
    op.execute(
        "DROP TRIGGER trg_validate_relationship_decision_lineage_insert "
        "ON knowledge.relationship_decision"
    )
    op.execute(
        "DROP TRIGGER trg_validate_field_decision_lineage_insert "
        "ON knowledge.canonical_decision"
    )
    op.execute(
        "DROP FUNCTION knowledge.validate_relationship_decision_lineage_insert()"
    )
    op.execute("DROP FUNCTION knowledge.validate_field_decision_lineage_insert()")


def _create_review_json_helpers() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.canonical_jsonb_text(value jsonb)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        SET extra_float_digits = 3
        AS $$
        DECLARE
            kind text;
            result text;
            scalar_text text;
        BEGIN
            kind := jsonb_typeof(value);
            IF kind = 'object' THEN
                SELECT '{' || COALESCE(
                    string_agg(
                        to_jsonb(entry.key)::text || ':' ||
                            knowledge.canonical_jsonb_text(entry.value),
                        ',' ORDER BY convert_to(entry.key, 'UTF8')
                    ),
                    ''
                ) || '}'
                INTO result
                FROM jsonb_each(value) AS entry(key, value);
            ELSIF kind = 'array' THEN
                SELECT '[' || COALESCE(
                    string_agg(
                        knowledge.canonical_jsonb_text(item.value),
                        ',' ORDER BY item.ordinality
                    ),
                    ''
                ) || ']'
                INTO result
                FROM jsonb_array_elements(value) WITH ORDINALITY
                    AS item(value, ordinality);
            ELSIF kind = 'number' THEN
                scalar_text := value::text;
                result := (scalar_text::double precision)::text;
                IF result !~ '[.eE]' AND scalar_text ~ '[.eE]' THEN
                    result := result || '.0';
                END IF;
            ELSE
                result := value::text;
            END IF;
            RETURN result;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_valid_human_review_identity_verdict(value jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            field_name text;
            resolution jsonb;
            source_group jsonb;
            normalized_groups jsonb;
        BEGIN
            IF knowledge.jsonb_has_exact_keys(value, ARRAY[
                    'verdict_id', 'component_id', 'component_input_sha256',
                    'verdict', 'proposed_outcome', 'source_identity_ids',
                    'source_identity_groups', 'supporting_assertion_ids',
                    'reason_codes', 'method', 'confidence', 'rationale',
                    'uncertainty', 'llm_trace', 'human_review_resolution'
                ]) IS DISTINCT FROM TRUE
            THEN
                RETURN FALSE;
            END IF;

            FOREACH field_name IN ARRAY ARRAY[
                'verdict_id', 'component_id', 'component_input_sha256',
                'verdict', 'method', 'rationale', 'uncertainty'
            ] LOOP
                IF jsonb_typeof(value->field_name) <> 'string'
                   OR knowledge.is_canonical_non_empty_string(
                        value->>field_name
                      ) IS DISTINCT FROM TRUE
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;

            IF value->>'component_input_sha256' !~ '^[0-9a-f]{64}$'
               OR value->>'verdict' NOT IN ('same_entity', 'different_entities')
               OR value->>'method' <> 'human_review'
               OR jsonb_typeof(value->'proposed_outcome') <> 'null'
               OR jsonb_typeof(value->'llm_trace') <> 'null'
               OR jsonb_typeof(value->'confidence') <> 'number'
               OR (value->'confidence')::text !~ '[.eE]'
               OR (value->>'confidence')::double precision
                    NOT BETWEEN 0.0 AND 1.0
               OR knowledge.is_canonical_json_string_array(
                    value->'source_identity_ids'
                  ) IS DISTINCT FROM TRUE
               OR jsonb_array_length(value->'source_identity_ids') < 2
               OR knowledge.is_canonical_json_string_array(
                    value->'supporting_assertion_ids'
                  ) IS DISTINCT FROM TRUE
               OR jsonb_array_length(value->'supporting_assertion_ids') < 1
               OR knowledge.is_canonical_json_string_array(value->'reason_codes')
                    IS DISTINCT FROM TRUE
               OR jsonb_array_length(value->'reason_codes') < 1
               OR jsonb_typeof(value->'source_identity_groups') <> 'array'
               OR jsonb_array_length(value->'source_identity_groups') < 1
               OR jsonb_typeof(value->'human_review_resolution') <> 'object'
            THEN
                RETURN FALSE;
            END IF;

            FOR source_group IN
                SELECT item.value
                FROM jsonb_array_elements(value->'source_identity_groups')
                    AS item(value)
            LOOP
                IF knowledge.is_canonical_json_string_array(source_group)
                        IS DISTINCT FROM TRUE
                   OR jsonb_array_length(source_group) = 0
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            SELECT COALESCE(
                jsonb_agg(
                    item.value
                    ORDER BY knowledge.canonical_json_string_array_sort_key(
                        item.value
                    )
                ),
                '[]'::jsonb
            )
            INTO normalized_groups
            FROM jsonb_array_elements(value->'source_identity_groups') AS item(value);
            IF normalized_groups <> value->'source_identity_groups'
               OR (
                    SELECT count(*) <> count(DISTINCT convert_to(source.value, 'UTF8'))
                    FROM jsonb_array_elements(value->'source_identity_groups')
                        AS source_group(value)
                    CROSS JOIN LATERAL jsonb_array_elements_text(source_group.value)
                        AS source(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(value->'source_identity_ids')
                        AS item(value)
                    EXCEPT
                    SELECT source.value
                    FROM jsonb_array_elements(value->'source_identity_groups')
                        AS source_group(value)
                    CROSS JOIN LATERAL jsonb_array_elements_text(source_group.value)
                        AS source(value)
               )
               OR EXISTS (
                    SELECT source.value
                    FROM jsonb_array_elements(value->'source_identity_groups')
                        AS source_group(value)
                    CROSS JOIN LATERAL jsonb_array_elements_text(source_group.value)
                        AS source(value)
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(value->'source_identity_ids')
                        AS item(value)
               )
            THEN
                RETURN FALSE;
            END IF;

            resolution := value->'human_review_resolution';
            RETURN knowledge.is_valid_human_review_resolution(resolution) IS TRUE
               AND resolution->'review_case'->>'family' = 'identity'
               AND resolution->>'outcome' = value->>'verdict'
               AND (resolution->>'confidence')::double precision =
                    (value->>'confidence')::double precision
               AND resolution->>'rationale' = value->>'rationale'
               AND resolution->'review_case'->>'uncertainty' =
                    value->>'uncertainty'
               AND value->'reason_codes' = '["human_review_resolution"]'::jsonb
               AND resolution->'source_identity_groups' =
                    value->'source_identity_groups'
               AND resolution->'review_case'->'source_identity_ids' =
                    value->'source_identity_ids'
               AND resolution->'review_case'->'candidate_evidence_ids' =
                    value->'supporting_assertion_ids';
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.canonical_jsonb_sha256(value jsonb)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT encode(
                sha256(convert_to(knowledge.canonical_jsonb_text(value), 'UTF8')),
                'hex'
            )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.jsonb_has_exact_keys(
            candidate jsonb,
            expected text[]
        )
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT jsonb_typeof(candidate) = 'object'
               AND NOT EXISTS (
                   SELECT key FROM jsonb_object_keys(candidate) AS actual(key)
                   EXCEPT
                   SELECT key FROM unnest(expected) AS required(key)
               )
               AND NOT EXISTS (
                   SELECT key FROM unnest(expected) AS required(key)
                   EXCEPT
                   SELECT key FROM jsonb_object_keys(candidate) AS actual(key)
               )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_canonical_non_empty_string(value text)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT length(value) > 0
               AND value = btrim(
                    value,
                    chr(9) || chr(10) || chr(11) || chr(12) || chr(13) ||
                    chr(32) || chr(133) || chr(160) || chr(5760) ||
                    chr(8192) || chr(8193) || chr(8194) || chr(8195) ||
                    chr(8196) || chr(8197) || chr(8198) || chr(8199) ||
                    chr(8200) || chr(8201) || chr(8202) || chr(8232) ||
                    chr(8233) || chr(8239) || chr(8287) || chr(12288)
               )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.canonical_json_string_array_sort_key(
            candidate jsonb
        )
        RETURNS bytea[]
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT COALESCE(
                array_agg(
                    convert_to(item.value, 'UTF8') ORDER BY item.ordinality
                ),
                ARRAY[]::bytea[]
            )
            FROM jsonb_array_elements_text(candidate) WITH ORDINALITY
                AS item(value, ordinality)
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_canonical_json_string_array(candidate jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            normalized jsonb;
        BEGIN
            IF knowledge.is_json_string_array(candidate) IS DISTINCT FROM TRUE
               OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(candidate) AS item(value)
                    WHERE knowledge.is_canonical_non_empty_string(
                        item.value #>> '{}'
                    ) IS DISTINCT FROM TRUE
               )
            THEN
                RETURN FALSE;
            END IF;
            SELECT COALESCE(
                jsonb_agg(item.value ORDER BY convert_to(item.value #>> '{}', 'UTF8')),
                '[]'::jsonb
            )
            INTO normalized
            FROM jsonb_array_elements(candidate) AS item(value);
            RETURN candidate = normalized;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_canonical_utc_datetime(value jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            raw_value text;
            parsed_value timestamptz;
            utc_value timestamp without time zone;
            microseconds text;
            canonical_value text;
        BEGIN
            IF jsonb_typeof(value) <> 'string' THEN
                RETURN FALSE;
            END IF;
            raw_value := value #>> '{}';
            parsed_value := raw_value::timestamptz;
            utc_value := parsed_value AT TIME ZONE 'UTC';
            microseconds := to_char(utc_value, 'US');
            canonical_value := to_char(
                utc_value,
                'YYYY-MM-DD"T"HH24:MI:SS'
            );
            IF microseconds <> '000000' THEN
                canonical_value := canonical_value || '.' || microseconds;
            END IF;
            canonical_value := canonical_value || 'Z';
            RETURN raw_value = canonical_value;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )


def _create_review_validator() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.is_valid_human_review_resolution(value jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            review_case jsonb;
            policy jsonb;
            case_hash text;
            resolution_hash text;
            field_name text;
            source_group jsonb;
            normalized_groups jsonb;
            family text;
            outcome text;
            method text;
        BEGIN
            IF knowledge.jsonb_has_exact_keys(value, ARRAY[
                    'resolution_id', 'content_sha256', 'review_case', 'outcome',
                    'selected_evidence_ids', 'role_bindings', 'source_identity_groups',
                    'reviewer_id', 'review_policy_id', 'review_policy_version',
                    'review_policy_content_sha256', 'reviewed_at', 'rationale',
                    'confidence'
                ]) IS DISTINCT FROM TRUE
            THEN
                RETURN FALSE;
            END IF;
            review_case := value->'review_case';
            IF knowledge.jsonb_has_exact_keys(review_case, ARRAY[
                    'review_case_id', 'content_sha256', 'family', 'release_id',
                    'decision_run_id', 'subject_id', 'path', 'originating_record_id',
                    'candidate_evidence_ids', 'conflicting_evidence_ids',
                    'source_identity_ids', 'policy', 'method', 'method_version',
                    'confidence', 'rationale', 'uncertainty', 'reason_codes',
                    'trace_content_sha256', 'input_content_sha256', 'created_at'
                ]) IS DISTINCT FROM TRUE
            THEN
                RETURN FALSE;
            END IF;
            policy := review_case->'policy';
            IF knowledge.jsonb_has_exact_keys(policy, ARRAY[
                    'policy_id', 'policy_version', 'policy_kind',
                    'content_sha256', 'effective_at'
                ]) IS DISTINCT FROM TRUE
            THEN
                RETURN FALSE;
            END IF;

            FOREACH field_name IN ARRAY ARRAY[
                'resolution_id', 'content_sha256', 'outcome', 'reviewer_id',
                'review_policy_id', 'review_policy_version',
                'review_policy_content_sha256', 'reviewed_at', 'rationale'
            ] LOOP
                IF jsonb_typeof(value->field_name) <> 'string'
                   OR knowledge.is_canonical_non_empty_string(
                        value->>field_name
                      ) IS DISTINCT FROM TRUE
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            FOREACH field_name IN ARRAY ARRAY[
                'review_case_id', 'content_sha256', 'family', 'release_id',
                'decision_run_id', 'subject_id', 'path', 'originating_record_id',
                'method', 'method_version', 'rationale', 'input_content_sha256',
                'created_at'
            ] LOOP
                IF jsonb_typeof(review_case->field_name) <> 'string'
                   OR knowledge.is_canonical_non_empty_string(
                        review_case->>field_name
                      ) IS DISTINCT FROM TRUE
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            FOREACH field_name IN ARRAY ARRAY[
                'policy_id', 'policy_version', 'policy_kind',
                'content_sha256', 'effective_at'
            ] LOOP
                IF jsonb_typeof(policy->field_name) <> 'string'
                   OR knowledge.is_canonical_non_empty_string(
                        policy->>field_name
                      ) IS DISTINCT FROM TRUE
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;

            IF value->>'resolution_id'
                    !~ '^human-review-resolution:sha256:[0-9a-f]{64}$'
               OR value->>'content_sha256' !~ '^[0-9a-f]{64}$'
               OR review_case->>'review_case_id'
                    !~ '^review-case:sha256:[0-9a-f]{64}$'
               OR review_case->>'content_sha256' !~ '^[0-9a-f]{64}$'
               OR value->>'review_policy_content_sha256' !~ '^[0-9a-f]{64}$'
               OR review_case->>'input_content_sha256' !~ '^[0-9a-f]{64}$'
               OR policy->>'content_sha256' !~ '^[0-9a-f]{64}$'
               OR jsonb_typeof(value->'confidence') <> 'number'
               OR (value->'confidence')::text !~ '[.eE]'
               OR (value->>'confidence')::double precision NOT BETWEEN 0.0 AND 1.0
               OR jsonb_typeof(review_case->'confidence') <> 'number'
               OR (review_case->'confidence')::text !~ '[.eE]'
               OR (review_case->>'confidence')::double precision
                    NOT BETWEEN 0.0 AND 1.0
            THEN
                RETURN FALSE;
            END IF;

            IF knowledge.is_canonical_json_string_array(
                    value->'selected_evidence_ids'
                ) IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_json_string_array(
                    review_case->'candidate_evidence_ids'
                ) IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_json_string_array(
                    review_case->'conflicting_evidence_ids'
                ) IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_json_string_array(
                    review_case->'source_identity_ids'
                ) IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_json_string_array(
                    review_case->'reason_codes'
                ) IS DISTINCT FROM TRUE
               OR jsonb_array_length(review_case->'candidate_evidence_ids') = 0
               OR jsonb_array_length(review_case->'conflicting_evidence_ids') < 2
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'conflicting_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        value->'selected_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
            THEN
                RETURN FALSE;
            END IF;

            IF jsonb_typeof(value->'role_bindings') <> 'object'
               OR EXISTS (
                    SELECT 1
                    FROM jsonb_each(value->'role_bindings') AS role(key, bound_value)
                    WHERE knowledge.is_canonical_non_empty_string(role.key)
                            IS DISTINCT FROM TRUE
                       OR jsonb_typeof(role.bound_value) <> 'string'
                       OR knowledge.is_canonical_non_empty_string(
                            role.bound_value #>> '{}'
                          ) IS DISTINCT FROM TRUE
               )
               OR jsonb_typeof(value->'source_identity_groups') <> 'array'
            THEN
                RETURN FALSE;
            END IF;
            FOR source_group IN
                SELECT item.value
                FROM jsonb_array_elements(value->'source_identity_groups')
                    AS item(value)
            LOOP
                IF knowledge.is_canonical_json_string_array(source_group)
                        IS DISTINCT FROM TRUE
                   OR jsonb_array_length(source_group) = 0
                THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            SELECT COALESCE(
                jsonb_agg(
                    item.value
                    ORDER BY knowledge.canonical_json_string_array_sort_key(
                        item.value
                    )
                ),
                '[]'::jsonb
            )
            INTO normalized_groups
            FROM jsonb_array_elements(value->'source_identity_groups') AS item(value);
            IF normalized_groups <> value->'source_identity_groups'
               OR (
                    SELECT count(*) <> count(DISTINCT convert_to(source.value, 'UTF8'))
                    FROM jsonb_array_elements(value->'source_identity_groups')
                        AS source_group(value)
                    CROSS JOIN LATERAL jsonb_array_elements_text(source_group.value)
                        AS source(value)
               )
            THEN
                RETURN FALSE;
            END IF;

            family := review_case->>'family';
            outcome := value->>'outcome';
            method := review_case->>'method';
            IF family NOT IN ('field', 'relationship', 'identity')
               OR method NOT IN (
                    'deterministic', 'structured_llm', 'human_review', 'composite'
               )
               OR jsonb_typeof(review_case->'uncertainty')
                    NOT IN ('null', 'string')
               OR (
                    jsonb_typeof(review_case->'uncertainty') = 'string'
                    AND knowledge.is_canonical_non_empty_string(
                        review_case->>'uncertainty'
                    ) IS DISTINCT FROM TRUE
               )
               OR jsonb_typeof(review_case->'trace_content_sha256')
                    NOT IN ('null', 'string')
               OR (
                    jsonb_typeof(review_case->'trace_content_sha256') = 'string'
                    AND review_case->>'trace_content_sha256'
                        !~ '^[0-9a-f]{64}$'
               )
               OR (
                    method = 'structured_llm'
                    AND jsonb_typeof(review_case->'trace_content_sha256') <> 'string'
               )
               OR (
                    method <> 'structured_llm'
                    AND jsonb_typeof(review_case->'trace_content_sha256') <> 'null'
               )
               OR (review_case->>'created_at')::timestamptz
                    > (value->>'reviewed_at')::timestamptz
               OR knowledge.is_canonical_utc_datetime(review_case->'created_at')
                    IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_utc_datetime(policy->'effective_at')
                    IS DISTINCT FROM TRUE
               OR knowledge.is_canonical_utc_datetime(value->'reviewed_at')
                    IS DISTINCT FROM TRUE
            THEN
                RETURN FALSE;
            END IF;

            IF family = 'field' THEN
                IF policy->>'policy_kind' <> 'field_selection'
                   OR jsonb_array_length(review_case->'source_identity_ids') <> 0
                   OR jsonb_array_length(review_case->'reason_codes') <> 0
                   OR outcome NOT IN ('selected', 'rejected')
                   OR jsonb_array_length(value->'source_identity_groups') <> 0
                   OR (
                        SELECT count(*)
                        FROM jsonb_object_keys(value->'role_bindings') AS role(key)
                   ) <> 0
                   OR (
                        outcome = 'selected'
                        AND jsonb_array_length(value->'selected_evidence_ids') = 0
                   )
                   OR (
                        outcome = 'rejected'
                        AND jsonb_array_length(value->'selected_evidence_ids') <> 0
                   )
                THEN
                    RETURN FALSE;
                END IF;
            ELSIF family = 'relationship' THEN
                IF policy->>'policy_kind' <> 'relationship'
                   OR jsonb_array_length(review_case->'source_identity_ids') <> 0
                   OR jsonb_array_length(review_case->'reason_codes') <> 0
                   OR outcome NOT IN ('accepted', 'rejected')
                   OR jsonb_array_length(value->'source_identity_groups') <> 0
                   OR (
                        outcome = 'accepted'
                        AND (
                            jsonb_array_length(value->'selected_evidence_ids') = 0
                            OR (
                                SELECT count(*)
                                FROM jsonb_object_keys(value->'role_bindings')
                                    AS role(key)
                            ) = 0
                        )
                   )
                   OR (
                        outcome = 'rejected'
                        AND (
                            jsonb_array_length(value->'selected_evidence_ids') <> 0
                            OR (
                                SELECT count(*)
                                FROM jsonb_object_keys(value->'role_bindings')
                                    AS role(key)
                            ) <> 0
                        )
                   )
                THEN
                    RETURN FALSE;
                END IF;
            ELSE
                IF policy->>'policy_kind' <> 'identity'
                   OR jsonb_array_length(review_case->'source_identity_ids') < 2
                   OR review_case->'candidate_evidence_ids' <>
                      review_case->'conflicting_evidence_ids'
                   OR outcome NOT IN ('same_entity', 'different_entities')
                   OR jsonb_array_length(value->'selected_evidence_ids') <> 0
                   OR (
                        SELECT count(*)
                        FROM jsonb_object_keys(value->'role_bindings') AS role(key)
                   ) <> 0
                   OR EXISTS (
                        SELECT item.value
                        FROM jsonb_array_elements_text(
                            review_case->'source_identity_ids'
                        ) AS item(value)
                        EXCEPT
                        SELECT source.value
                        FROM jsonb_array_elements(value->'source_identity_groups')
                            AS source_group(value)
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            source_group.value
                        ) AS source(value)
                   )
                   OR EXISTS (
                        SELECT source.value
                        FROM jsonb_array_elements(value->'source_identity_groups')
                            AS source_group(value)
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            source_group.value
                        ) AS source(value)
                        EXCEPT
                        SELECT item.value
                        FROM jsonb_array_elements_text(
                            review_case->'source_identity_ids'
                        ) AS item(value)
                   )
                   OR (
                        outcome = 'same_entity'
                        AND jsonb_array_length(value->'source_identity_groups') <> 1
                   )
                   OR (
                        outcome = 'different_entities'
                        AND jsonb_array_length(value->'source_identity_groups') < 2
                   )
                THEN
                    RETURN FALSE;
                END IF;
            END IF;

            case_hash := knowledge.canonical_jsonb_sha256(
                review_case - 'review_case_id' - 'content_sha256'
            );
            IF review_case->>'content_sha256' <> case_hash
               OR review_case->>'review_case_id' <>
                    'review-case:sha256:' || case_hash
            THEN
                RETURN FALSE;
            END IF;
            resolution_hash := knowledge.canonical_jsonb_sha256(
                value - 'resolution_id' - 'content_sha256'
            );
            RETURN value->>'content_sha256' = resolution_hash
               AND value->>'resolution_id' =
                    'human-review-resolution:sha256:' || resolution_hash;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN FALSE;
        END;
        $$
        """
    )


def _create_field_review_binding_validator() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_field_human_review_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            reviewed record;
            origin record;
            resolution jsonb;
            review_case jsonb;
        BEGIN
            IF TG_TABLE_NAME = 'canonical_decision_assertion'
               AND EXISTS (
                    SELECT 1
                    FROM knowledge.canonical_decision AS human_decision
                    WHERE human_decision.method = 'human_review'
                      AND human_decision.human_review_resolution
                            ->'review_case'->>'release_id' = NEW.release_id
                      AND human_decision.human_review_resolution
                            ->'review_case'->>'originating_record_id' =
                            NEW.decision_id
               )
            THEN
                RAISE EXCEPTION
                    'reviewed field origin evidence is immutable'
                    USING ERRCODE = '23514';
            END IF;
            SELECT decision.*
            INTO reviewed
            FROM knowledge.canonical_decision AS decision
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;
            IF NOT FOUND OR reviewed.method <> 'human_review' THEN
                RETURN NEW;
            END IF;
            resolution := reviewed.human_review_resolution;
            review_case := resolution->'review_case';

            IF review_case->>'release_id' = reviewed.release_id
               OR NOT EXISTS (
                    WITH RECURSIVE ancestry(release_id, previous_release_id) AS (
                        SELECT release.release_id, release.previous_release_id
                        FROM knowledge.release AS release
                        WHERE release.release_id = reviewed.release_id
                        UNION
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS parent
                        JOIN ancestry
                          ON parent.release_id = ancestry.previous_release_id
                    )
                    SELECT 1 FROM ancestry
                    WHERE release_id = review_case->>'release_id'
               )
            THEN
                RAISE EXCEPTION
                    'field human review binding requires an immutable ancestor case'
                    USING ERRCODE = '23514';
            END IF;

            SELECT decision.*,
                   policy.policy_kind AS origin_policy_kind,
                   policy.content_sha256 AS origin_policy_sha256,
                   policy.effective_at AS origin_policy_effective_at
            INTO origin
            FROM knowledge.canonical_decision AS decision
            JOIN knowledge.policy AS policy
              ON policy.policy_id = decision.policy_id
             AND policy.policy_version = decision.policy_version
            WHERE decision.release_id = review_case->>'release_id'
              AND decision.decision_run_id = review_case->>'decision_run_id'
              AND decision.decision_id = review_case->>'originating_record_id'
            FOR UPDATE OF decision;
            IF NOT FOUND
               OR origin.state <> 'unresolved'
               OR origin.canonical_identity_id IS DISTINCT FROM
                    review_case->>'subject_id'
               OR origin.field_path IS DISTINCT FROM review_case->>'path'
               OR reviewed.canonical_identity_id IS DISTINCT FROM
                    origin.canonical_identity_id
               OR reviewed.field_path IS DISTINCT FROM origin.field_path
               OR reviewed.supersedes_decision_id IS DISTINCT FROM origin.decision_id
               OR origin.policy_id IS DISTINCT FROM
                    review_case->'policy'->>'policy_id'
               OR origin.policy_version IS DISTINCT FROM
                    review_case->'policy'->>'policy_version'
               OR origin.origin_policy_kind IS DISTINCT FROM
                    review_case->'policy'->>'policy_kind'
               OR origin.origin_policy_sha256 IS DISTINCT FROM
                    review_case->'policy'->>'content_sha256'
               OR origin.origin_policy_effective_at IS DISTINCT FROM
                    (review_case->'policy'->>'effective_at')::timestamptz
               OR origin.method IS DISTINCT FROM review_case->>'method'
               OR origin.method_version IS DISTINCT FROM
                    review_case->>'method_version'
               OR origin.confidence IS DISTINCT FROM
                    (review_case->>'confidence')::double precision
               OR origin.rationale IS DISTINCT FROM review_case->>'rationale'
               OR origin.decided_at IS DISTINCT FROM
                    (review_case->>'created_at')::timestamptz
               OR COALESCE(
                    origin.llm_trace->'validated_output'->>'uncertainty',
                    NULL
                  ) IS DISTINCT FROM review_case->>'uncertainty'
               OR origin.llm_trace->>'output_sha256' IS DISTINCT FROM
                    review_case->>'trace_content_sha256'
               OR origin.decision_id NOT LIKE
                    'field-decision:manifest-sha256:' ||
                    (review_case->>'input_content_sha256') || ':%'
               OR reviewed.decision_id NOT LIKE
                    'field-decision:manifest-sha256:' ||
                    (review_case->>'input_content_sha256') || ':%'
            THEN
                RAISE EXCEPTION
                    'field human review provenance is cross-wired to its origin'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'candidate'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'candidate'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'conflicting_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'conflicting'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'conflicting'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'conflicting_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT 1
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'selected'
               )
            THEN
                RAISE EXCEPTION
                    'field human review case evidence differs from unresolved origin'
                    USING ERRCODE = '23514';
            END IF;

            IF reviewed.policy_id IS DISTINCT FROM
                    review_case->'policy'->>'policy_id'
               OR reviewed.policy_version IS DISTINCT FROM
                    review_case->'policy'->>'policy_version'
               OR reviewed.method_version IS DISTINCT FROM
                    review_case->>'method_version'
               OR reviewed.confidence IS DISTINCT FROM
                    (resolution->>'confidence')::double precision
               OR reviewed.rationale IS DISTINCT FROM resolution->>'rationale'
               OR reviewed.decided_at < (resolution->>'reviewed_at')::timestamptz
               OR reviewed.llm_trace IS NOT NULL
               OR (resolution->>'outcome' = 'selected' AND reviewed.state <> 'selected')
               OR (resolution->>'outcome' = 'rejected' AND reviewed.state <> 'rejected')
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'candidate'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'candidate'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        resolution->'selected_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'selected'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'selected'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        resolution->'selected_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    WHERE NOT (resolution->'selected_evidence_ids') ? item.value
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'conflicting'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.canonical_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'conflicting'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    WHERE NOT (resolution->'selected_evidence_ids') ? item.value
               )
               OR EXISTS (
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
                    WHERE left_edge.release_id = reviewed.release_id
                      AND left_edge.decision_id = reviewed.decision_id
                      AND left_edge.assertion_role = 'selected'
                      AND (
                          left_assertion.value IS DISTINCT FROM right_assertion.value
                          OR left_assertion.valid_from IS DISTINCT FROM
                             right_assertion.valid_from
                          OR left_assertion.valid_to IS DISTINCT FROM
                             right_assertion.valid_to
                      )
               )
            THEN
                RAISE EXCEPTION
                    'field human review binding does not exactly apply its resolution'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table, trigger in (
        ("canonical_decision", "trg_validate_field_human_review_binding"),
        (
            "canonical_decision_assertion",
            "trg_validate_field_human_review_assertion_binding",
        ),
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_field_human_review_binding()"
        )


def _create_relationship_review_binding_validator() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_relationship_human_review_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            reviewed record;
            origin record;
            resolution jsonb;
            review_case jsonb;
            selected_valid_from timestamptz;
            selected_valid_to timestamptz;
        BEGIN
            IF TG_TABLE_NAME = 'relationship_decision_assertion'
               AND EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_decision AS human_decision
                    WHERE human_decision.method = 'human_review'
                      AND human_decision.human_review_resolution
                            ->'review_case'->>'release_id' = NEW.release_id
                      AND human_decision.human_review_resolution
                            ->'review_case'->>'originating_record_id' =
                            NEW.decision_id
               )
            THEN
                RAISE EXCEPTION
                    'reviewed relationship origin evidence is immutable'
                    USING ERRCODE = '23514';
            END IF;
            SELECT decision.*
            INTO reviewed
            FROM knowledge.relationship_decision AS decision
            WHERE decision.release_id = NEW.release_id
              AND decision.decision_id = NEW.decision_id;
            IF NOT FOUND OR reviewed.method <> 'human_review' THEN
                RETURN NEW;
            END IF;
            resolution := reviewed.human_review_resolution;
            review_case := resolution->'review_case';

            IF review_case->>'release_id' = reviewed.release_id
               OR NOT EXISTS (
                    WITH RECURSIVE ancestry(release_id, previous_release_id) AS (
                        SELECT release.release_id, release.previous_release_id
                        FROM knowledge.release AS release
                        WHERE release.release_id = reviewed.release_id
                        UNION
                        SELECT parent.release_id, parent.previous_release_id
                        FROM knowledge.release AS parent
                        JOIN ancestry
                          ON parent.release_id = ancestry.previous_release_id
                    )
                    SELECT 1 FROM ancestry
                    WHERE release_id = review_case->>'release_id'
               )
            THEN
                RAISE EXCEPTION
                    'relationship human review binding requires an immutable ancestor case'
                    USING ERRCODE = '23514';
            END IF;

            SELECT decision.*,
                   policy.policy_kind AS origin_policy_kind,
                   policy.content_sha256 AS origin_policy_sha256,
                   policy.effective_at AS origin_policy_effective_at
            INTO origin
            FROM knowledge.relationship_decision AS decision
            JOIN knowledge.policy AS policy
              ON policy.policy_id = decision.policy_id
             AND policy.policy_version = decision.policy_version
            WHERE decision.release_id = review_case->>'release_id'
              AND decision.decision_run_id = review_case->>'decision_run_id'
              AND decision.decision_id = review_case->>'originating_record_id'
            FOR UPDATE OF decision;
            IF NOT FOUND
               OR origin.state <> 'unresolved'
               OR origin.canonical_relationship_id IS DISTINCT FROM
                    review_case->>'subject_id'
               OR origin.relationship_type_id IS DISTINCT FROM review_case->>'path'
               OR reviewed.canonical_relationship_id IS DISTINCT FROM
                    origin.canonical_relationship_id
               OR reviewed.relationship_type_id IS DISTINCT FROM
                    origin.relationship_type_id
               OR reviewed.relationship_type_version IS DISTINCT FROM
                    origin.relationship_type_version
               OR reviewed.source_canonical_identity_id IS DISTINCT FROM
                    origin.source_canonical_identity_id
               OR reviewed.target_canonical_identity_id IS DISTINCT FROM
                    origin.target_canonical_identity_id
               OR reviewed.supersedes_decision_id IS DISTINCT FROM origin.decision_id
               OR origin.policy_id IS DISTINCT FROM
                    review_case->'policy'->>'policy_id'
               OR origin.policy_version IS DISTINCT FROM
                    review_case->'policy'->>'policy_version'
               OR origin.origin_policy_kind IS DISTINCT FROM
                    review_case->'policy'->>'policy_kind'
               OR origin.origin_policy_sha256 IS DISTINCT FROM
                    review_case->'policy'->>'content_sha256'
               OR origin.origin_policy_effective_at IS DISTINCT FROM
                    (review_case->'policy'->>'effective_at')::timestamptz
               OR origin.method IS DISTINCT FROM review_case->>'method'
               OR origin.method_version IS DISTINCT FROM
                    review_case->>'method_version'
               OR origin.confidence IS DISTINCT FROM
                    (review_case->>'confidence')::double precision
               OR origin.rationale IS DISTINCT FROM review_case->>'rationale'
               OR origin.decided_at IS DISTINCT FROM
                    (review_case->>'created_at')::timestamptz
               OR COALESCE(
                    origin.llm_trace->'validated_output'->>'uncertainty',
                    NULL
                  ) IS DISTINCT FROM review_case->>'uncertainty'
               OR origin.llm_trace->>'output_sha256' IS DISTINCT FROM
                    review_case->>'trace_content_sha256'
               OR origin.role_bindings <> '{}'::jsonb
               OR origin.valid_from IS NOT NULL
               OR origin.valid_to IS NOT NULL
               OR origin.decision_id NOT LIKE
                    'relationship-decision:manifest-sha256:' ||
                    (review_case->>'input_content_sha256') || ':%'
               OR reviewed.decision_id NOT LIKE
                    'relationship-decision:manifest-sha256:' ||
                    (review_case->>'input_content_sha256') || ':%'
            THEN
                RAISE EXCEPTION
                    'relationship human review provenance is cross-wired to its origin'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'candidate'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'candidate'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'conflicting_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'conflicting'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'conflicting'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'conflicting_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = origin.release_id
                      AND edge.decision_id = origin.decision_id
                      AND edge.assertion_role = 'selected'
               )
            THEN
                RAISE EXCEPTION
                    'relationship review case evidence differs from unresolved origin'
                    USING ERRCODE = '23514';
            END IF;

            SELECT assertion.valid_from, assertion.valid_to
            INTO selected_valid_from, selected_valid_to
            FROM knowledge.relationship_decision_assertion AS edge
            JOIN knowledge.relationship_assertion AS assertion
              ON assertion.assertion_id = edge.assertion_id
            WHERE edge.release_id = reviewed.release_id
              AND edge.decision_id = reviewed.decision_id
              AND edge.assertion_role = 'selected'
            ORDER BY edge.assertion_id
            LIMIT 1;
            IF reviewed.policy_id IS DISTINCT FROM
                    review_case->'policy'->>'policy_id'
               OR reviewed.policy_version IS DISTINCT FROM
                    review_case->'policy'->>'policy_version'
               OR reviewed.method_version IS DISTINCT FROM
                    review_case->>'method_version'
               OR reviewed.confidence IS DISTINCT FROM
                    (resolution->>'confidence')::double precision
               OR reviewed.rationale IS DISTINCT FROM resolution->>'rationale'
               OR reviewed.decided_at < (resolution->>'reviewed_at')::timestamptz
               OR reviewed.llm_trace IS NOT NULL
               OR reviewed.role_bindings IS DISTINCT FROM
                    resolution->'role_bindings'
               OR (resolution->>'outcome' = 'accepted' AND reviewed.state <> 'accepted')
               OR (resolution->>'outcome' = 'rejected' AND reviewed.state <> 'rejected')
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'candidate'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'candidate'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        resolution->'selected_evidence_ids'
                    ) AS item(value)
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'selected'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'selected'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        resolution->'selected_evidence_ids'
                    ) AS item(value)
               )
               OR EXISTS (
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    WHERE NOT (resolution->'selected_evidence_ids') ? item.value
                    EXCEPT
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'conflicting'
               )
               OR EXISTS (
                    SELECT edge.assertion_id
                    FROM knowledge.relationship_decision_assertion AS edge
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'conflicting'
                    EXCEPT
                    SELECT item.value
                    FROM jsonb_array_elements_text(
                        review_case->'candidate_evidence_ids'
                    ) AS item(value)
                    WHERE NOT (resolution->'selected_evidence_ids') ? item.value
               )
               OR EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_decision_assertion AS edge
                    JOIN knowledge.relationship_assertion AS assertion
                      ON assertion.assertion_id = edge.assertion_id
                    WHERE edge.release_id = reviewed.release_id
                      AND edge.decision_id = reviewed.decision_id
                      AND edge.assertion_role = 'selected'
                      AND (
                          assertion.valid_from IS DISTINCT FROM selected_valid_from
                          OR assertion.valid_to IS DISTINCT FROM selected_valid_to
                      )
               )
               OR reviewed.valid_from IS DISTINCT FROM selected_valid_from
               OR reviewed.valid_to IS DISTINCT FROM selected_valid_to
            THEN
                RAISE EXCEPTION
                    'relationship human review binding does not exactly apply its resolution'
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
            "trg_validate_relationship_human_review_binding",
        ),
        (
            "relationship_decision_assertion",
            "trg_validate_relationship_human_review_assertion_binding",
        ),
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_relationship_human_review_binding()"
        )


def _create_identity_review_binding_validator() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.validate_identity_human_review_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            reviewed record;
            origin record;
            resolution jsonb;
            review_case jsonb;
            materialization_count bigint;
            materialized_groups jsonb;
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM knowledge.identity_decision AS decision
                LEFT JOIN knowledge.identity_decision_context AS context
                  ON context.release_id = decision.release_id
                 AND context.decision_id = decision.decision_id
                LEFT JOIN knowledge.identity_candidate_verdict AS verdict
                  ON verdict.release_id = context.release_id
                 AND verdict.decision_run_id = context.decision_run_id
                 AND verdict.verdict_id = context.candidate_verdict_id
                WHERE decision.release_id = NEW.release_id
                  AND decision.method = 'human_review'
                  AND (
                      verdict.verdict_id IS NULL
                      OR verdict.method <> 'human_review'
                      OR verdict.verdict_content->'human_review_resolution'
                         IS DISTINCT FROM decision.human_review_resolution
                  )
            ) THEN
                RAISE EXCEPTION
                    'identity human review decision is not bound to one reviewed verdict'
                    USING ERRCODE = '23514';
            END IF;

            FOR reviewed IN
                SELECT verdict.*,
                       resolution_run.identity_method_version,
                       resolution_run.as_of AS run_as_of,
                       resolution_run.policy_id AS run_policy_id,
                       resolution_run.policy_version AS run_policy_version,
                       policy.policy_kind AS run_policy_kind,
                       policy.content_sha256 AS run_policy_sha256,
                       policy.effective_at AS run_policy_effective_at
                FROM knowledge.identity_candidate_verdict AS verdict
                JOIN knowledge.identity_resolution_run AS resolution_run
                  ON resolution_run.release_id = verdict.release_id
                 AND resolution_run.decision_run_id = verdict.decision_run_id
                JOIN knowledge.policy AS policy
                  ON policy.policy_id = resolution_run.policy_id
                 AND policy.policy_version = resolution_run.policy_version
                WHERE verdict.release_id = NEW.release_id
                  AND verdict.method = 'human_review'
            LOOP
                resolution := reviewed.verdict_content->'human_review_resolution';
                review_case := resolution->'review_case';
                IF review_case->>'release_id' = reviewed.release_id
                   OR NOT EXISTS (
                        WITH RECURSIVE ancestry(release_id, previous_release_id) AS (
                            SELECT release.release_id, release.previous_release_id
                            FROM knowledge.release AS release
                            WHERE release.release_id = reviewed.release_id
                            UNION
                            SELECT parent.release_id, parent.previous_release_id
                            FROM knowledge.release AS parent
                            JOIN ancestry
                              ON parent.release_id = ancestry.previous_release_id
                        )
                        SELECT 1 FROM ancestry
                        WHERE release_id = review_case->>'release_id'
                   )
                THEN
                    RAISE EXCEPTION
                        'identity human review requires an immutable ancestor case'
                        USING ERRCODE = '23514';
                END IF;

                SELECT verdict.*,
                       resolution_run.identity_method_version,
                       resolution_run.as_of AS run_as_of,
                       resolution_run.policy_id AS run_policy_id,
                       resolution_run.policy_version AS run_policy_version,
                       policy.policy_kind AS run_policy_kind,
                       policy.content_sha256 AS run_policy_sha256,
                       policy.effective_at AS run_policy_effective_at
                INTO origin
                FROM knowledge.identity_candidate_verdict AS verdict
                JOIN knowledge.identity_resolution_run AS resolution_run
                  ON resolution_run.release_id = verdict.release_id
                 AND resolution_run.decision_run_id = verdict.decision_run_id
                JOIN knowledge.policy AS policy
                  ON policy.policy_id = resolution_run.policy_id
                 AND policy.policy_version = resolution_run.policy_version
                WHERE verdict.release_id = review_case->>'release_id'
                  AND verdict.decision_run_id = review_case->>'decision_run_id'
                  AND verdict.verdict_id = review_case->>'originating_record_id';
                IF NOT FOUND
                   OR origin.verdict <> 'unresolved'
                   OR origin.content_sha256 IS DISTINCT FROM
                        knowledge.canonical_jsonb_sha256(origin.verdict_content)
                   OR origin.verdict_content->>'component_id' IS DISTINCT FROM
                        review_case->>'subject_id'
                   OR review_case->>'path' <> 'canonical_identity'
                   OR origin.verdict_content->'source_identity_ids' IS DISTINCT FROM
                        review_case->'source_identity_ids'
                   OR origin.verdict_content->'supporting_assertion_ids'
                        IS DISTINCT FROM review_case->'candidate_evidence_ids'
                   OR origin.method IS DISTINCT FROM review_case->>'method'
                   OR origin.identity_method_version IS DISTINCT FROM
                        review_case->>'method_version'
                   OR origin.confidence IS DISTINCT FROM
                        (review_case->>'confidence')::double precision
                   OR origin.verdict_content->>'rationale' IS DISTINCT FROM
                        review_case->>'rationale'
                   OR origin.verdict_content->>'uncertainty' IS DISTINCT FROM
                        review_case->>'uncertainty'
                   OR origin.verdict_content->'reason_codes' IS DISTINCT FROM
                        review_case->'reason_codes'
                   OR origin.verdict_content->'llm_trace'->>'output_sha256'
                        IS DISTINCT FROM review_case->>'trace_content_sha256'
                   OR origin.verdict_content->>'component_input_sha256'
                        IS DISTINCT FROM review_case->>'input_content_sha256'
                   OR origin.run_as_of IS DISTINCT FROM
                        (review_case->>'created_at')::timestamptz
                   OR origin.run_policy_id IS DISTINCT FROM
                        review_case->'policy'->>'policy_id'
                   OR origin.run_policy_version IS DISTINCT FROM
                        review_case->'policy'->>'policy_version'
                   OR origin.run_policy_kind IS DISTINCT FROM
                        review_case->'policy'->>'policy_kind'
                   OR origin.run_policy_sha256 IS DISTINCT FROM
                        review_case->'policy'->>'content_sha256'
                   OR origin.run_policy_effective_at IS DISTINCT FROM
                        (review_case->'policy'->>'effective_at')::timestamptz
                THEN
                    RAISE EXCEPTION
                        'identity human review provenance is cross-wired to its unresolved verdict'
                        USING ERRCODE = '23514';
                END IF;

                IF reviewed.content_sha256 IS DISTINCT FROM
                        knowledge.canonical_jsonb_sha256(reviewed.verdict_content)
                   OR reviewed.verdict_id IS DISTINCT FROM
                        reviewed.verdict_content->>'verdict_id'
                   OR reviewed.verdict IS DISTINCT FROM
                        reviewed.verdict_content->>'verdict'
                   OR reviewed.method IS DISTINCT FROM
                        reviewed.verdict_content->>'method'
                   OR reviewed.confidence IS DISTINCT FROM
                        (reviewed.verdict_content->>'confidence')::double precision
                   OR reviewed.run_policy_id IS DISTINCT FROM
                        review_case->'policy'->>'policy_id'
                   OR reviewed.run_policy_version IS DISTINCT FROM
                        review_case->'policy'->>'policy_version'
                   OR reviewed.run_as_of < (resolution->>'reviewed_at')::timestamptz
                   OR reviewed.verdict_content->'source_identity_ids'
                        IS DISTINCT FROM review_case->'source_identity_ids'
                   OR reviewed.verdict_content->'supporting_assertion_ids'
                        IS DISTINCT FROM review_case->'candidate_evidence_ids'
                   OR reviewed.verdict_content->'source_identity_groups'
                        IS DISTINCT FROM resolution->'source_identity_groups'
                   OR (
                        resolution->>'outcome' = 'same_entity'
                        AND reviewed.verdict <> 'same_entity'
                   )
                   OR (
                        resolution->>'outcome' = 'different_entities'
                        AND reviewed.verdict <> 'different_entities'
                   )
                   OR (
                        SELECT count(*)
                        FROM knowledge.identity_candidate_verdict AS sibling
                        WHERE sibling.release_id = reviewed.release_id
                          AND sibling.decision_run_id = reviewed.decision_run_id
                          AND sibling.method = 'human_review'
                          AND sibling.verdict_content->'human_review_resolution'
                              ->>'resolution_id' = resolution->>'resolution_id'
                   ) <> 1
                THEN
                    RAISE EXCEPTION
                        'identity human review verdict does not exactly apply its resolution'
                        USING ERRCODE = '23514';
                END IF;

                SELECT count(DISTINCT context.decision_id)
                INTO materialization_count
                FROM knowledge.identity_decision_context AS context
                WHERE context.release_id = reviewed.release_id
                  AND context.decision_run_id = reviewed.decision_run_id
                  AND context.candidate_verdict_id = reviewed.verdict_id;
                IF materialization_count > 0 THEN
                    IF EXISTS (
                            SELECT 1
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision AS decision
                              ON decision.release_id = context.release_id
                             AND decision.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                              AND (
                                  decision.method <> 'human_review'
                                  OR decision.human_review_resolution
                                     IS DISTINCT FROM resolution
                                  OR decision.policy_id IS DISTINCT FROM
                                     review_case->'policy'->>'policy_id'
                                  OR decision.policy_version IS DISTINCT FROM
                                     review_case->'policy'->>'policy_version'
                                  OR decision.method_version IS DISTINCT FROM
                                     reviewed.identity_method_version
                                  OR decision.confidence IS DISTINCT FROM
                                     (resolution->>'confidence')::double precision
                                  OR decision.rationale IS DISTINCT FROM
                                     resolution->>'rationale'
                                  OR decision.decided_at <
                                     (resolution->>'reviewed_at')::timestamptz
                                  OR decision.llm_trace IS NOT NULL
                                  OR (
                                      resolution->>'outcome' = 'same_entity'
                                      AND decision.action NOT IN (
                                          'create', 'link', 'merge'
                                      )
                                  )
                                  OR (
                                      resolution->>'outcome' = 'different_entities'
                                      AND decision.action NOT IN (
                                          'create', 'split', 'reverse'
                                      )
                                  )
                              )
                       )
                       OR EXISTS (
                            SELECT item.value
                            FROM jsonb_array_elements_text(
                                review_case->'source_identity_ids'
                            ) AS item(value)
                            EXCEPT
                            SELECT edge.source_identity_id
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_source_identity AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                       )
                       OR EXISTS (
                            SELECT edge.source_identity_id
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_source_identity AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                            EXCEPT
                            SELECT item.value
                            FROM jsonb_array_elements_text(
                                review_case->'source_identity_ids'
                            ) AS item(value)
                       )
                       OR (
                            SELECT count(*) <> count(DISTINCT edge.source_identity_id)
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_source_identity AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                       )
                       OR EXISTS (
                            SELECT item.value
                            FROM jsonb_array_elements_text(
                                review_case->'candidate_evidence_ids'
                            ) AS item(value)
                            EXCEPT
                            SELECT edge.assertion_id
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_assertion AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                       )
                       OR EXISTS (
                            SELECT edge.assertion_id
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_assertion AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                            EXCEPT
                            SELECT item.value
                            FROM jsonb_array_elements_text(
                                review_case->'candidate_evidence_ids'
                            ) AS item(value)
                       )
                       OR (
                            SELECT count(*) <> count(DISTINCT edge.assertion_id)
                            FROM knowledge.identity_decision_context AS context
                            JOIN knowledge.identity_decision_assertion AS edge
                              ON edge.release_id = context.release_id
                             AND edge.decision_id = context.decision_id
                            WHERE context.release_id = reviewed.release_id
                              AND context.decision_run_id = reviewed.decision_run_id
                              AND context.candidate_verdict_id = reviewed.verdict_id
                       )
                    THEN
                        RAISE EXCEPTION
                            'identity human review materialization is cross-wired'
                            USING ERRCODE = '23514';
                    END IF;

                    SELECT COALESCE(
                        jsonb_agg(
                            grouped.source_ids
                            ORDER BY knowledge.canonical_json_string_array_sort_key(
                                grouped.source_ids
                            )
                        ),
                        '[]'::jsonb
                    )
                    INTO materialized_groups
                    FROM (
                        SELECT allocation.canonical_identity_id,
                               jsonb_agg(
                                   allocation.source_identity_id
                                   ORDER BY convert_to(
                                       allocation.source_identity_id, 'UTF8'
                                   )
                               ) AS source_ids
                        FROM knowledge.identity_decision_context AS context
                        JOIN knowledge.identity_decision_output_source AS allocation
                          ON allocation.release_id = context.release_id
                         AND allocation.decision_id = context.decision_id
                        WHERE context.release_id = reviewed.release_id
                          AND context.decision_run_id = reviewed.decision_run_id
                          AND context.candidate_verdict_id = reviewed.verdict_id
                        GROUP BY allocation.canonical_identity_id
                    ) AS grouped;
                ELSE
                    SELECT COALESCE(
                        jsonb_agg(
                            grouped.source_ids
                            ORDER BY knowledge.canonical_json_string_array_sort_key(
                                grouped.source_ids
                            )
                        ),
                        '[]'::jsonb
                    )
                    INTO materialized_groups
                    FROM (
                        SELECT assignment.canonical_identity_id,
                               jsonb_agg(
                                   assignment.source_identity_id
                                   ORDER BY convert_to(
                                       assignment.source_identity_id, 'UTF8'
                                   )
                               ) AS source_ids
                        FROM knowledge.current_source_identity_assignment AS assignment
                        WHERE assignment.release_id = reviewed.release_id
                          AND (review_case->'source_identity_ids')
                              ? assignment.source_identity_id
                        GROUP BY assignment.canonical_identity_id
                    ) AS grouped;
                END IF;
                IF materialized_groups IS DISTINCT FROM
                        resolution->'source_identity_groups'
                THEN
                    RAISE EXCEPTION
                        'identity review output partition differs from its resolution'
                        USING ERRCODE = '23514';
                END IF;
            END LOOP;
            RETURN NEW;
        END;
        $$
        """
    )
    trigger_tables = (
        (
            "identity_candidate_verdict",
            "trg_validate_identity_human_review_verdict_binding",
        ),
        ("identity_decision", "trg_validate_identity_human_review_binding"),
        (
            "identity_decision_context",
            "trg_validate_identity_human_review_context_binding",
        ),
        (
            "identity_decision_source_identity",
            "trg_validate_identity_human_review_source_binding",
        ),
        (
            "identity_decision_output",
            "trg_validate_identity_human_review_output_binding",
        ),
        (
            "identity_decision_output_source",
            "trg_validate_identity_human_review_allocation_binding",
        ),
        (
            "identity_decision_assertion",
            "trg_validate_identity_human_review_assertion_binding",
        ),
        (
            "current_source_identity_assignment",
            "trg_validate_identity_human_review_assignment_binding",
        ),
        (
            "canonical_identity_source_membership",
            "trg_validate_identity_human_review_membership_binding",
        ),
    )
    for table, trigger in trigger_tables:
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON knowledge.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.validate_identity_human_review_binding()"
        )


def _drop_identity_review_binding_validator() -> None:
    for table, trigger in reversed(
        (
            (
                "identity_candidate_verdict",
                "trg_validate_identity_human_review_verdict_binding",
            ),
            ("identity_decision", "trg_validate_identity_human_review_binding"),
            (
                "identity_decision_context",
                "trg_validate_identity_human_review_context_binding",
            ),
            (
                "identity_decision_source_identity",
                "trg_validate_identity_human_review_source_binding",
            ),
            (
                "identity_decision_output",
                "trg_validate_identity_human_review_output_binding",
            ),
            (
                "identity_decision_output_source",
                "trg_validate_identity_human_review_allocation_binding",
            ),
            (
                "identity_decision_assertion",
                "trg_validate_identity_human_review_assertion_binding",
            ),
            (
                "current_source_identity_assignment",
                "trg_validate_identity_human_review_assignment_binding",
            ),
            (
                "canonical_identity_source_membership",
                "trg_validate_identity_human_review_membership_binding",
            ),
        )
    ):
        op.execute(f"DROP TRIGGER {trigger} ON knowledge.{table}")
    op.execute("DROP FUNCTION knowledge.validate_identity_human_review_binding()")


def _drop_decision_review_binding_validators() -> None:
    for table, trigger in (
        (
            "relationship_decision_assertion",
            "trg_validate_relationship_human_review_assertion_binding",
        ),
        (
            "relationship_decision",
            "trg_validate_relationship_human_review_binding",
        ),
        (
            "canonical_decision_assertion",
            "trg_validate_field_human_review_assertion_binding",
        ),
        ("canonical_decision", "trg_validate_field_human_review_binding"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON knowledge.{table}")
    op.execute("DROP FUNCTION knowledge.validate_relationship_human_review_binding()")
    op.execute("DROP FUNCTION knowledge.validate_field_human_review_binding()")


def _protect_release_history() -> None:
    op.execute(
        r"""
        CREATE FUNCTION knowledge.reject_release_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'release history is immutable; knowledge.release rejects %',
                TG_OP
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_reject_release_history_update "
        "BEFORE UPDATE ON knowledge.release FOR EACH ROW WHEN ("
        "OLD.release_id IS DISTINCT FROM NEW.release_id OR "
        "OLD.build_run_id IS DISTINCT FROM NEW.build_run_id OR "
        "OLD.manifest_sha256 IS DISTINCT FROM NEW.manifest_sha256 OR "
        "OLD.previous_release_id IS DISTINCT FROM NEW.previous_release_id OR "
        "OLD.created_at IS DISTINCT FROM NEW.created_at) "
        "EXECUTE FUNCTION knowledge.reject_release_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_reject_release_history_delete "
        "BEFORE DELETE ON knowledge.release FOR EACH ROW "
        "EXECUTE FUNCTION knowledge.reject_release_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_reject_release_history_truncate "
        "BEFORE TRUNCATE ON knowledge.release FOR EACH STATEMENT "
        "EXECUTE FUNCTION knowledge.reject_release_history_mutation()"
    )


def _unprotect_release_history() -> None:
    for trigger in (
        "trg_reject_release_history_truncate",
        "trg_reject_release_history_delete",
        "trg_reject_release_history_update",
    ):
        op.execute(f"DROP TRIGGER {trigger} ON knowledge.release")
    op.execute("DROP FUNCTION knowledge.reject_release_history_mutation()")


def upgrade() -> None:
    _lock_review_boundary()
    _reject_and_prevent_supersession_forks()
    _create_decision_lineage_validators()
    _protect_release_history()
    for table, _ in DECISION_REVIEW_FAMILIES:
        op.add_column(
            table,
            sa.Column(
                "human_review_resolution",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            schema="knowledge",
        )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM knowledge.canonical_decision
                WHERE method = 'human_review'
            ) OR EXISTS (
                SELECT 1 FROM knowledge.relationship_decision
                WHERE method = 'human_review'
            ) OR EXISTS (
                SELECT 1 FROM knowledge.identity_decision
                WHERE method = 'human_review'
            ) OR EXISTS (
                SELECT 1 FROM knowledge.identity_candidate_verdict
                WHERE method = 'human_review'
            ) THEN
                RAISE EXCEPTION
                    'C2_0007 cannot invent reviewer/evidence provenance for existing human_review decisions'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    _create_review_json_helpers()
    _create_review_validator()
    for table, family in DECISION_REVIEW_FAMILIES:
        op.create_check_constraint(
            f"ck_knowledge_{table}_human_review_resolution",
            table,
            "CASE WHEN method = 'human_review' THEN "
            "human_review_resolution IS NOT NULL AND COALESCE("
            "knowledge.is_valid_human_review_resolution(human_review_resolution), "
            "FALSE) AND COALESCE("
            f"human_review_resolution->'review_case'->>'family' = '{family}', FALSE) "
            "ELSE human_review_resolution IS NULL END",
            schema="knowledge",
        )
    op.create_check_constraint(
        "ck_knowledge_identity_candidate_verdict_human_review_resolution",
        "identity_candidate_verdict",
        "COALESCE(CASE WHEN method = 'human_review' THEN "
        "knowledge.is_valid_human_review_identity_verdict(verdict_content) IS TRUE "
        "AND verdict_id = verdict_content->>'verdict_id' "
        "AND verdict = verdict_content->>'verdict' "
        "AND method = verdict_content->>'method' "
        "AND confidence = (verdict_content->>'confidence')::double precision "
        "AND content_sha256 = knowledge.canonical_jsonb_sha256(verdict_content) "
        "ELSE NOT (verdict_content ? 'human_review_resolution') OR "
        "jsonb_typeof(verdict_content->'human_review_resolution') = 'null' END, "
        "FALSE)",
        schema="knowledge",
    )
    _create_field_review_binding_validator()
    _create_relationship_review_binding_validator()
    _create_identity_review_binding_validator()


def downgrade() -> None:
    _lock_review_boundary()
    predicates = " OR ".join(
        "EXISTS (SELECT 1 FROM knowledge."
        f"{table} WHERE human_review_resolution IS NOT NULL)"
        for table, _ in DECISION_REVIEW_FAMILIES
    )
    predicates += (
        " OR EXISTS (SELECT 1 FROM knowledge.identity_candidate_verdict "
        "WHERE method = 'human_review')"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {predicates} THEN
                RAISE EXCEPTION
                    'C2_0007 downgrade refuses to discard retained human review provenance'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )
    _drop_decision_lineage_validators()
    _allow_supersession_forks_for_c2_0006_compatibility()
    _drop_identity_review_binding_validator()
    _drop_decision_review_binding_validators()
    op.drop_constraint(
        "ck_knowledge_identity_candidate_verdict_human_review_resolution",
        "identity_candidate_verdict",
        schema="knowledge",
        type_="check",
    )
    for table, _ in reversed(DECISION_REVIEW_FAMILIES):
        op.drop_constraint(
            f"ck_knowledge_{table}_human_review_resolution",
            table,
            schema="knowledge",
            type_="check",
        )
        op.drop_column(table, "human_review_resolution", schema="knowledge")
    op.execute("DROP FUNCTION knowledge.is_valid_human_review_identity_verdict(jsonb)")
    op.execute("DROP FUNCTION knowledge.is_valid_human_review_resolution(jsonb)")
    op.execute("DROP FUNCTION knowledge.is_canonical_utc_datetime(jsonb)")
    op.execute("DROP FUNCTION knowledge.is_canonical_json_string_array(jsonb)")
    op.execute("DROP FUNCTION knowledge.canonical_json_string_array_sort_key(jsonb)")
    op.execute("DROP FUNCTION knowledge.is_canonical_non_empty_string(text)")
    op.execute("DROP FUNCTION knowledge.jsonb_has_exact_keys(jsonb, text[])")
    op.execute("DROP FUNCTION knowledge.canonical_jsonb_sha256(jsonb)")
    op.execute("DROP FUNCTION knowledge.canonical_jsonb_text(jsonb)")
    _unprotect_release_history()
