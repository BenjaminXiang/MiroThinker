"""V027 professor_paper_link evidence-source constraint repair tests."""

from __future__ import annotations

import uuid

from .conftest import (
    _alembic_config,
    _load_alembic,
    _load_postgres_dependencies,
    _psycopg_dsn,
    _raw_database_url,
)


_CONSTRAINT_NAME = "ck_professor_paper_link_evidence_source_type"
_OLD_EVIDENCE_SOURCES = (
    "official_publication_page",
    "personal_homepage",
    "cv_pdf",
    "official_external_profile",
    "academic_api_with_affiliation_match",
)


def test_v027_repairs_drifted_professor_paper_link_tier_constraint() -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    pg_dsn = _psycopg_dsn(_raw_database_url())
    psycopg, _, _, _ = _load_postgres_dependencies()
    professor_id = f"PROF-V027-{uuid.uuid4().hex[:8]}"
    paper_id = f"PAPER-V027-{uuid.uuid4().hex[:8]}"

    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, "V026")
    _force_old_evidence_constraint(psycopg, pg_dsn)

    try:
        alembic_command.upgrade(config, "head")
        with psycopg.connect(pg_dsn) as conn:
            constraint_def = conn.execute(
                """
                SELECT pg_get_constraintdef(c.oid)
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = 'professor_paper_link'
                   AND c.conname = %s
                """,
                (_CONSTRAINT_NAME,),
            ).fetchone()[0]
            assert "prof_homepage_tier2" in constraint_def
            assert "prof_homepage_tier3" in constraint_def

            conn.execute(
                """
                INSERT INTO professor (
                    professor_id,
                    canonical_name,
                    discipline_family
                )
                VALUES (%s, 'V027 Test Professor', 'computer_science')
                """,
                (professor_id,),
            )
            conn.execute(
                """
                INSERT INTO paper (
                    paper_id,
                    title_clean,
                    canonical_source
                )
                VALUES (%s, 'V027 Test Paper', 'official_page')
                """,
                (paper_id,),
            )
            conn.execute(
                """
                INSERT INTO professor_paper_link (
                    professor_id,
                    paper_id,
                    link_status,
                    evidence_source_type,
                    match_reason,
                    author_name_match_score
                )
                VALUES (
                    %s,
                    %s,
                    'verified',
                    'prof_homepage_tier2',
                    'prof_page_declaration',
                    1.0
                )
                """,
                (professor_id, paper_id),
            )
            assert (
                conn.execute(
                    """
                    SELECT evidence_source_type
                      FROM professor_paper_link
                     WHERE professor_id = %s
                       AND paper_id = %s
                    """,
                    (professor_id, paper_id),
                ).fetchone()[0]
                == "prof_homepage_tier2"
            )
    finally:
        alembic_command.downgrade(config, "base")


def _force_old_evidence_constraint(psycopg, pg_dsn: str) -> None:
    quoted = ",".join(f"'{source}'" for source in _OLD_EVIDENCE_SOURCES)
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            f"""
            ALTER TABLE professor_paper_link
            DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}
            """
        )
        conn.execute(
            f"""
            ALTER TABLE professor_paper_link
            ADD CONSTRAINT {_CONSTRAINT_NAME}
            CHECK (evidence_source_type IN ({quoted}))
            """
        )
        conn.commit()
