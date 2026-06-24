from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_topic_split_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_topic_split_backfill", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fetch_candidate_facts_selects_source_run_id():
    cli = _import_cli()
    conn = _FakeConn([])

    cli._fetch_candidate_facts(conn, limit=1)

    sql, _params = conn.calls[0]
    assert "f.run_id" in sql


def test_insert_atomic_copies_source_run_id_via_writer():
    """_insert_atomic now routes through the dedup-aware writer, which issues a
    SELECT (to find existing active twins) then an INSERT. Locate the INSERT
    and confirm the source run_id is carried through."""
    cli = _import_cli()
    conn = _FakeConn([])

    cli._insert_atomic(
        conn,
        source={
            "professor_id": "PROF-1",
            "source_page_id": "PAGE-1",
            "evidence_span": "raw evidence",
            "confidence": "0.85",
            "run_id": "11111111-1111-1111-1111-111111111111",
        },
        value_raw="机器学习",
    )

    insert_call = next(
        (c for c in conn.calls if "INSERT INTO professor_fact" in c[0]), None
    )
    assert insert_call is not None, "expected an INSERT into professor_fact"
    sql, params = insert_call
    assert "run_id" in sql
    assert params[0] == "PROF-1"  # professor_id
    assert params[1] == "research_topic"  # fact_type
    assert params[2] == "机器学习"  # value_raw
    assert params[4] == "PAGE-1"  # source_page_id
    assert params[-1] == "11111111-1111-1111-1111-111111111111"  # run_id preserved


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _FakeCursor(self.rows)
