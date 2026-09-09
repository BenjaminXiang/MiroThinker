"""Create the clean Canonical V2 namespace baseline.

Revision ID: C2_0001
Revises:
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "C2_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("canonical_v2",)
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_COMMENTS = {
    "landing": "Immutable source artifacts, parser runs, and replayable source records",
    "knowledge": "Shared evidence, identity, decision, relationship, policy, and release semantics",
    "professor": "Typed Canonical V2 Professor projections and business sub-objects",
    "company": "Typed Canonical V2 Company projections and business sub-objects",
    "paper": "Typed Canonical V2 Paper projections and business sub-objects",
    "patent": "Typed Canonical V2 Patent projections and business sub-objects",
    "publish": "Release-scoped serving projections and publication manifests",
    "ops": "Knowledge gaps, reviews, decisions, and rebuild operations",
}


def upgrade() -> None:
    for schema, comment in SCHEMA_COMMENTS.items():
        op.execute(sa.schema.CreateSchema(schema))
        op.execute(sa.text(f"COMMENT ON SCHEMA {schema} IS '{comment}'"))


def downgrade() -> None:
    for schema in reversed(SCHEMA_COMMENTS):
        op.execute(sa.schema.DropSchema(schema, cascade=False))
