"""thin-decision-persist (Stage 2, R15-推论一): the persist path proves
storage consistency with raw column tuples instead of an in-transaction
object-graph rebuild. These tests lock the thin behaviors:

- idempotent replay returns without the full `_load_result` rebuild
- a tampered durable row makes replay fail closed (replay conflict)
- the post-commit rebuild check honors CANONICAL_V2_DECISION_REBUILD_CHECK

PG-backed, gated by the same CANONICAL_V2_TEST_* env as the decision
postgres suite.
"""

from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from typing import Any, Iterator

import psycopg
import pytest
from alembic import command
from psycopg import sql

test_helpers = import_module(
    "test_canonical_decision_postgres"
)


@pytest.fixture
def target(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[Any]:
    # replica of the sibling suite's target fixture (pytest forbids
    # calling fixtures across modules directly)
    database_url, expected_database, target_kind, backup_gate_root = (
        test_helpers._explicit_environment()
    )
    assert target_kind == "disposable"
    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    base_marker = (
        f"miroflow:destructive-target:v1:{target_kind}:{expected_database}"
    )
    sibling_name = (
        f"{expected_database[:42]}_thin_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    sibling_marker = (
        f"miroflow:destructive-target:v1:disposable:{sibling_name}"
    )
    with psycopg.connect(
        test_helpers._psycopg_dsn(database_url), autocommit=True
    ) as admin:
        assert admin.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone() == (expected_database, base_marker)
        test_helpers._drop_owned_sibling(
            admin,
            database_name=sibling_name,
            expected_marker=sibling_marker,
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(sibling_name))
        )
        admin.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(sibling_name),
                sql.Literal(sibling_marker),
            )
        )
    try:
        provisional = test_helpers._Target(
            database_url=test_helpers._sibling_database_url(
                database_url, sibling_name
            ),
            expected_database=sibling_name,
            target_kind="disposable",
            backup_gate_root=Path(backup_gate_root),
            config=test_helpers.Config(),
        )
        configured = test_helpers._Target(
            database_url=provisional.database_url,
            expected_database=provisional.expected_database,
            target_kind=provisional.target_kind,
            backup_gate_root=provisional.backup_gate_root,
            config=test_helpers._migration_config(provisional),
        )
        command.upgrade(configured.config, test_helpers.EXPECTED_REVISION)
        test_helpers._verify_target(configured)
        yield configured
    finally:
        with psycopg.connect(
            test_helpers._psycopg_dsn(database_url), autocommit=True
        ) as admin:
            test_helpers._drop_owned_sibling(
                admin,
                database_name=sibling_name,
                expected_marker=sibling_marker,
            )


def test_replay_returns_without_full_rebuild(target, monkeypatch) -> None:
    store = test_helpers._store(target)
    result = test_helpers._decision_result()
    test_helpers._insert_prerequisites(target)

    assert store.persist(result) == result

    loads = {"count": 0}
    original_load = store._load_result.__func__

    def counting_load(cls, connection, **kwargs):
        loads["count"] += 1
        return original_load(cls, connection, **kwargs)

    monkeypatch.setattr(
        type(store), "_load_result", classmethod(counting_load)
    )
    replayed = store.persist(result)
    assert replayed == result
    assert loads["count"] == 0, "replay must not rebuild the object graph"


def test_tampered_durable_row_fails_replay_closed(target, monkeypatch) -> None:
    module = test_helpers._postgres_module()
    store = test_helpers._store(target)
    assert module  # noqa: B018 — kept for the raises() type below
    result = test_helpers._decision_result()
    test_helpers._insert_prerequisites(target)
    assert store.persist(result) == result

    # physical corruption is blocked upstream (append-only triggers + FK +
    # terminal-role uniqueness), so the durable-vs-input conflict vector is
    # changed content under the same release/run — the thin replay path must
    # detect it WITHOUT the object-graph rebuild (the property this slice
    # adds over the legacy path).
    loads = {"count": 0}
    original_load = store._load_result.__func__

    def counting_load(cls, connection, **kwargs):
        loads["count"] += 1
        return original_load(cls, connection, **kwargs)

    monkeypatch.setattr(type(store), "_load_result", classmethod(counting_load))
    changed = test_helpers._decision_result(changed=True)
    with pytest.raises(
        module.CanonicalDecisionPersistenceError, match="replay conflict"
    ):
        store.persist(changed)
    assert loads["count"] == 0, "conflict detection must not rebuild the graph"


def test_post_commit_rebuild_check_env_gate(target, monkeypatch) -> None:
    store = test_helpers._store(target)
    loads = {"count": 0}
    original_load = store._load_result.__func__

    def counting_load(cls, connection, **kwargs):
        loads["count"] += 1
        return original_load(cls, connection, **kwargs)

    monkeypatch.setattr(
        type(store), "_load_result", classmethod(counting_load)
    )
    initial = test_helpers._decision_result(field_unresolved=True)
    reviewed = test_helpers._reviewed_field_result(initial)
    test_helpers._insert_prerequisites(target)
    test_helpers._insert_reviewed_release_prerequisites(target)

    with monkeypatch.context() as off_ctx:
        off_ctx.setenv("CANONICAL_V2_DECISION_REBUILD_CHECK", "off")
        store_off = test_helpers._store(target)
        store_off.persist(initial)
    assert loads["count"] == 0

    with monkeypatch.context() as on_ctx:
        on_ctx.setenv("CANONICAL_V2_DECISION_REBUILD_CHECK", "always")
        store_on = test_helpers._store(target)
        store_on.persist(reviewed)
    assert loads["count"] == 1
