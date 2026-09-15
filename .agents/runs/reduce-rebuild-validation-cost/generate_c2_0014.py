"""Generate migration C2_0014 from the C2_0007 validator bodies.

The three `human review binding` validator bodies are long; re-typing them into
the new migration would risk silent predicate drift. This one-off generator in
the run evidence directory copies the bodies **verbatim** out of
`canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py`, inserts
the release-level guard immediately after each `BEGIN`, and writes the migration
file. Everything else in the generated file is authored here.

Usage:
    uv run python generate_c2_0014.py [--check]

`--check` re-generates in memory and reports whether the on-disk file matches,
so the migration can be reviewed as an ordinary source file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parents[2] / "apps" / "miroflow-agent"
VERSIONS = APP_ROOT / "canonical_v2_alembic" / "versions"
SOURCE = VERSIONS / "C2_0007_bind_human_review_provenance.py"
TARGET = VERSIONS / "C2_0014_guard_review_binding_scans.py"

FUNCTIONS = (
    "knowledge.validate_field_human_review_binding",
    "knowledge.validate_relationship_human_review_binding",
    "knowledge.validate_identity_human_review_binding",
)

FIELD_GUARD = """
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
"""

RELATIONSHIP_GUARD = """
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
"""

IDENTITY_GUARD = """
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
"""

GUARDS = {
    "knowledge.validate_field_human_review_binding": FIELD_GUARD,
    "knowledge.validate_relationship_human_review_binding": RELATIONSHIP_GUARD,
    "knowledge.validate_identity_human_review_binding": IDENTITY_GUARD,
}

INDEXES = (
    # block ① lookup: "is (release, decision) the originating record of a review case?"
    "CREATE INDEX ix_knowledge_canonical_decision_human_review_case\n"
    "    ON knowledge.canonical_decision (\n"
    "        (human_review_resolution->'review_case'->>'release_id'),\n"
    "        (human_review_resolution->'review_case'->>'originating_record_id')\n"
    "    )\n"
    "    WHERE method = 'human_review'",
    "CREATE INDEX ix_knowledge_canonical_decision_human_review_decision\n"
    "    ON knowledge.canonical_decision (release_id, decision_id)\n"
    "    WHERE method = 'human_review'",
    "CREATE INDEX ix_knowledge_relationship_decision_human_review_case\n"
    "    ON knowledge.relationship_decision (\n"
    "        (human_review_resolution->'review_case'->>'release_id'),\n"
    "        (human_review_resolution->'review_case'->>'originating_record_id')\n"
    "    )\n"
    "    WHERE method = 'human_review'",
    "CREATE INDEX ix_knowledge_relationship_decision_human_review_decision\n"
    "    ON knowledge.relationship_decision (release_id, decision_id)\n"
    "    WHERE method = 'human_review'",
    "CREATE INDEX ix_knowledge_identity_decision_human_review\n"
    "    ON knowledge.identity_decision (release_id)\n"
    "    WHERE method = 'human_review'",
    "CREATE INDEX ix_knowledge_identity_candidate_verdict_human_review\n"
    "    ON knowledge.identity_candidate_verdict (release_id)\n"
    "    WHERE method = 'human_review'",
)

INDEX_NAMES = tuple(
    re.match(r"CREATE INDEX (\w+)", statement).group(1)  # type: ignore[union-attr]
    for statement in INDEXES
)

HEADER = '''"""Skip per-row review-binding scans when a release has no reviewed rows.

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

'''


def extract_body(name: str) -> str:
    """Return the `CREATE FUNCTION <name>() ... $$` text from C2_0007."""
    text = SOURCE.read_text()
    start = text.index(f"CREATE FUNCTION {name}()")
    end = text.index("$$\n        \"\"\"", start)
    return text[start : end + 2]


def guarded(body: str, name: str) -> str:
    head, separator, tail = body.partition("BEGIN\n")
    assert separator, f"{name}: BEGIN not found"
    return (
        head.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)
        + separator
        + GUARDS[name]
        + tail
    )


def build() -> str:
    parts = [HEADER, "def upgrade() -> None:\n"]
    for statement in INDEXES:
        parts.append(f'    op.execute(\n        """\n        {statement}\n        """\n    )\n')
    for name in FUNCTIONS:
        parts.append(f'    op.execute(\n        r"""\n        {guarded(extract_body(name), name)}\n        """\n    )\n')
    parts.append("\n\ndef downgrade() -> None:\n")
    for name in FUNCTIONS:
        parts.append(
            "    op.execute(\n"
            "        r\"\"\"\n"
            f"        {extract_body(name).replace('CREATE FUNCTION ', 'CREATE OR REPLACE FUNCTION ', 1)}\n"
            "        \"\"\"\n"
            "    )\n\n"
        )
    parts.append("    for name in (\n")
    for index_name in INDEX_NAMES:
        parts.append(f'        "{index_name}",\n')
    parts.append("    ):\n")
    parts.append('        op.execute(f"DROP INDEX IF EXISTS knowledge.{name}")\n')
    return "".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    if args.check:
        current = TARGET.read_text() if TARGET.exists() else ""
        print("in sync" if current == generated else "OUT OF SYNC")
        raise SystemExit(0 if current == generated else 1)
    TARGET.write_text(generated)
    print(f"wrote {TARGET} ({len(generated)} bytes)")


if __name__ == "__main__":
    main()
