"""Small-scale verification: the persistence schema accepts every optional field.

Three consecutive run16 attempts (5/6/7) died because D0-a relaxed the typed
projection models but the PostgreSQL layer was not updated: a NOT NULL column
(C2_0015) and then two NULL-rejecting named-reference CHECKs (C2_0016) only
surfaced when a build reached persistence, hours into the run.

This test closes the class statically, in seconds, against a migrated database:

1. every model field that is not required must map to a nullable column (when a
   same-named column exists in the domain's current_projection table);
2. no CHECK constraint on those tables may reject NULL for such a column — the
   signature is `COALESCE(...)` without an `IS NULL` guard (`btrim(x) <> ''` is
   NULL-tolerant because a CHECK accepts an UNKNOWN result).

PG-gated, same env contract as test_domain_projection_postgres.py.
"""

from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
import psycopg
import pytest
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import set_alembic_database_url

APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
MODELS_MODULE = "src.data_agents.canonical_v2.domain_projection_models"
MODELS = {
    "company": "CompanyProjection",
    "paper": "PaperProjection",
    "patent": "PatentProjection",
    "professor": "ProfessorProjection",
}


def _models():
    return import_module(MODELS_MODULE)


def _explicit_environment() -> tuple[str, str, str, str]:
    names = (
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not all(values):
        pytest.skip(
            "projection schema nullability check requires all four "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _connect(database_url: str) -> psycopg.Connection[Any]:
    dsn = (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    return psycopg.connect(dsn, autocommit=True, row_factory=psycopg.rows.dict_row)


def test_projection_schema_accepts_every_optional_field() -> None:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert target_kind == "disposable"
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, database_url)
    config.set_main_option("miroflow.expected_database", expected_database)
    config.set_main_option("miroflow.target_kind", target_kind)
    config.set_main_option("miroflow.backup_gate_root", backup_gate_root)
    command.upgrade(config, "head")

    models = _models()
    with _connect(database_url) as connection:
        for domain, class_name in sorted(MODELS.items()):
            model = getattr(models, class_name)
            columns = {
                row["column_name"]: row["is_nullable"]
                for row in connection.execute(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = 'current_projection'",
                    (domain,),
                ).fetchall()
            }
            assert columns, f"{domain}.current_projection is missing"

            # Fields that default to None are the ones that can reach the
            # database as NULL; defaults like `entity_type: Literal[...] = "x"`
            # or `tuple[...] = ()` are always populated.
            optional_fields = {
                name
                for name, field in model.model_fields.items()
                if not field.is_required() and field.default is None
            }
            mismatched = sorted(
                name
                for name in optional_fields & set(columns)
                if columns[name] != "YES"
            )
            assert not mismatched, (
                f"{domain}: optional model fields backed by NOT NULL columns "
                f"(needs a DROP NOT NULL migration): {mismatched}"
            )

            constraints = connection.execute(
                """
                SELECT conname, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint
                WHERE conrelid = %s::regclass AND contype = 'c'
                """,
                (f"{domain}.current_projection",),
            ).fetchall()
            offenders = sorted(
                row["conname"]
                for row in constraints
                if "COALESCE(" in row["definition"]
                and "IS NULL" not in row["definition"]
                and any(
                    name in row["definition"] for name in optional_fields & set(columns)
                )
            )
            assert not offenders, (
                f"{domain}: NULL-rejecting CHECK constraints on optional columns "
                f"(needs a shape-relaxation migration): {offenders}"
            )
