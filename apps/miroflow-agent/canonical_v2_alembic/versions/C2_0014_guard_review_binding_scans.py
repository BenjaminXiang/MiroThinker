"""Skip per-row review-binding scans when a release has no reviewed rows.

Revision ID: C2_0014
Revises: C2_0013
Create Date: 2026-09-15

The `human review binding` constraint triggers re-derived a whole-table fact for
every inserted row: `validate_field_human_review_binding` scanned all 417k
`knowledge.canonical_decision` rows for each of the 834k inserted
`canonical_decision_assertion` rows because the `EXISTS` in its first branch had
no usable index (run15 measured **12h40m** inside a single deferred `COMMIT`,
with 0 rows actually rejected). The same shape sits in the relationship and
identity binding validators.

This migration keeps every predicate and every `RAISE EXCEPTION ... ERRCODE
23514` byte-identical and only changes when work happens:

1. six partial indexes make the `method = 'human_review'` probes index lookups
   (empty index in a rebuild => the probe is free);
2. each binding validator returns immediately when the inserted row's release
   has no reviewed decision and no reviewed case, which is a necessary condition
   for every rejection branch in that function.

No trigger, predicate, error message, or deferral mode changes.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "C2_0014"
down_revision: Union[str, None] = "C2_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_knowledge_canonical_decision_human_review_case
    ON knowledge.canonical_decision (
        (human_review_resolution->'review_case'->>'release_id'),
        (human_review_resolution->'review_case'->>'originating_record_id')
    )
    WHERE method = 'human_review'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_canonical_decision_human_review_decision
    ON knowledge.canonical_decision (release_id, decision_id)
    WHERE method = 'human_review'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_relationship_decision_human_review_case
    ON knowledge.relationship_decision (
        (human_review_resolution->'review_case'->>'release_id'),
        (human_review_resolution->'review_case'->>'originating_record_id')
    )
    WHERE method = 'human_review'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_relationship_decision_human_review_decision
    ON knowledge.relationship_decision (release_id, decision_id)
    WHERE method = 'human_review'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_identity_decision_human_review
    ON knowledge.identity_decision (release_id)
    WHERE method = 'human_review'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_identity_candidate_verdict_human_review
    ON knowledge.identity_candidate_verdict (release_id)
    WHERE method = 'human_review'
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_field_human_review_binding()
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

            IF NOT EXISTS (
                    SELECT 1
                    FROM knowledge.canonical_decision AS reviewed_decision
                    WHERE reviewed_decision.method = 'human_review'
                      AND reviewed_decision.human_review_resolution
                            ->'review_case'->>'release_id' = NEW.release_id
               )
               AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge.canonical_decision AS reviewed_decision
                    WHERE reviewed_decision.release_id = NEW.release_id
                      AND reviewed_decision.decision_id = NEW.decision_id
                      AND reviewed_decision.method = 'human_review'
               )
            THEN
                RETURN NEW;
            END IF;
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
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_relationship_human_review_binding()
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

            IF NOT EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_decision AS reviewed_decision
                    WHERE reviewed_decision.method = 'human_review'
                      AND reviewed_decision.human_review_resolution
                            ->'review_case'->>'release_id' = NEW.release_id
               )
               AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge.relationship_decision AS reviewed_decision
                    WHERE reviewed_decision.release_id = NEW.release_id
                      AND reviewed_decision.decision_id = NEW.decision_id
                      AND reviewed_decision.method = 'human_review'
               )
            THEN
                RETURN NEW;
            END IF;
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
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_identity_human_review_binding()
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

            IF NOT EXISTS (
                    SELECT 1
                    FROM knowledge.identity_decision AS reviewed_decision
                    WHERE reviewed_decision.release_id = NEW.release_id
                      AND reviewed_decision.method = 'human_review'
               )
               AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge.identity_candidate_verdict
                        AS reviewed_verdict
                    WHERE reviewed_verdict.release_id = NEW.release_id
                      AND reviewed_verdict.method = 'human_review'
               )
            THEN
                RETURN NEW;
            END IF;
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


def downgrade() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_field_human_review_binding()
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

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_relationship_human_review_binding()
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

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION knowledge.validate_identity_human_review_binding()
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

    for name in (
        "ix_knowledge_canonical_decision_human_review_case",
        "ix_knowledge_canonical_decision_human_review_decision",
        "ix_knowledge_relationship_decision_human_review_case",
        "ix_knowledge_relationship_decision_human_review_decision",
        "ix_knowledge_identity_decision_human_review",
        "ix_knowledge_identity_candidate_verdict_human_review",
    ):
        op.execute(f"DROP INDEX IF EXISTS knowledge.{name}")

