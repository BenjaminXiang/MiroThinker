"""Chunk oversized run snapshots instead of one jsonb value.

Revision ID: C2_0013
Revises: C2_0012
Create Date: 2026-08-19

PostgreSQL caps a single jsonb value at 268435455 bytes. The full-column
rebuild (full-column-serving-pack-rebuild) persists identity-resolution and
relationship-projection snapshots whose serialized size exceeds that cap, so
the run rows now store their request/result payloads as base64 chunks in
companion tables and leave the inline jsonb columns NULL. Readers reassemble
the chunks (verifying every chunk hash and the run row's aggregate hash) and
keep validating the typed models exactly as before; small runs may still use
the inline columns, and both readers treat them with priority.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "C2_0013"
down_revision: Union[str, None] = "C2_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ALTER COLUMN request_content DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ALTER COLUMN result_content DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "DROP CONSTRAINT ck_knowledge_identity_resolution_run_content"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ADD CONSTRAINT ck_knowledge_identity_resolution_run_content "
        "CHECK ((request_content IS NULL OR "
        "jsonb_typeof(request_content) = 'object') AND "
        "(result_content IS NULL OR jsonb_typeof(result_content) = 'object'))"
    )
    op.create_table(
        "identity_resolution_run_content_chunk",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("decision_run_id", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_b64", sa.Text(), nullable=False),
        sa.Column("chunk_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "decision_run_id",
            "role",
            "chunk_index",
            name="pk_knowledge_identity_resolution_run_content_chunk",
        ),
        schema="knowledge",
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "ALTER COLUMN result_payload DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "DROP CONSTRAINT ck_knowledge_relationship_projection_run_json"
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "ADD CONSTRAINT ck_knowledge_relationship_projection_run_json "
        "CHECK (jsonb_typeof(retained_assertion_refs) = 'array' AND "
        "jsonb_typeof(retained_artifact_refs) = 'array' AND "
        "(result_payload IS NULL OR jsonb_typeof(result_payload) = 'object') "
        "AND (temporal_comparison_context IS NULL OR "
        "jsonb_typeof(temporal_comparison_context) = 'object'))"
    )
    op.create_table(
        "relationship_projection_run_content_chunk",
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("projection_run_id", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_b64", sa.Text(), nullable=False),
        sa.Column("chunk_sha256", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "release_id",
            "projection_run_id",
            "role",
            "chunk_index",
            name="pk_knowledge_relationship_projection_run_content_chunk",
        ),
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_table(
        "relationship_projection_run_content_chunk",
        schema="knowledge",
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "DROP CONSTRAINT ck_knowledge_relationship_projection_run_json"
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "ADD CONSTRAINT ck_knowledge_relationship_projection_run_json "
        "CHECK (jsonb_typeof(retained_assertion_refs) = 'array' AND "
        "jsonb_typeof(retained_artifact_refs) = 'array' AND "
        "jsonb_typeof(result_payload) = 'object' AND "
        "(temporal_comparison_context IS NULL OR "
        "jsonb_typeof(temporal_comparison_context) = 'object'))"
    )
    op.execute(
        "ALTER TABLE knowledge.relationship_projection_run "
        "ALTER COLUMN result_payload SET NOT NULL"
    )
    op.drop_table(
        "identity_resolution_run_content_chunk",
        schema="knowledge",
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "DROP CONSTRAINT ck_knowledge_identity_resolution_run_content"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ADD CONSTRAINT ck_knowledge_identity_resolution_run_content "
        "CHECK (jsonb_typeof(request_content) = 'object' AND "
        "jsonb_typeof(result_content) = 'object')"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ALTER COLUMN result_content SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE knowledge.identity_resolution_run "
        "ALTER COLUMN request_content SET NOT NULL"
    )
