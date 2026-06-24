"""Contract tests for the semantic, keep-richest _upsert_fact writer."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

from src.data_agents.professor.canonical_writer import _upsert_fact

_RUN_ID = "00000000-0000-0000-0000-0000000000aa"
_PAGE_ID = UUID("11111111-1111-1111-1111-111111111111")


class _FakeConn:
    """Minimal in-memory professor_fact store for the three SQL shapes the
    writer uses (SELECT active / INSERT / UPDATE superseded)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._n = 0

    def _active(self, professor_id: str, fact_type: str) -> list[dict]:
        return [
            {
                "fact_id": r["fact_id"],
                "value_raw": r["value_raw"],
                "value_normalized": r["value_normalized"],
            }
            for r in self.rows
            if r["professor_id"] == professor_id
            and r["fact_type"] == fact_type
            and r["status"] == "active"
        ]

    def execute(self, sql: str, params: tuple | None = None):
        s = sql.strip().upper()
        if s.startswith("SELECT"):
            return MagicMock(fetchall=MagicMock(return_value=self._active(params[0], params[1])))
        if "INSERT INTO PROFESSOR_FACT" in s:
            self._n += 1
            (
                professor_id,
                fact_type,
                value_raw,
                value_normalized,
                _source_page_id,
                _evidence_span,
                _confidence,
                _run_id,
            ) = params
            self.rows.append(
                {
                    "fact_id": f"fid-{self._n}",
                    "professor_id": professor_id,
                    "fact_type": fact_type,
                    "value_raw": value_raw,
                    "value_normalized": value_normalized,
                    "status": "active",
                }
            )
            return MagicMock()
        if "UPDATE PROFESSOR_FACT" in s and "SUPERSEDED" in s:
            fact_id = params[1]  # (run_id, fact_id)
            for r in self.rows:
                if r["fact_id"] == fact_id:
                    r["status"] = "superseded"
            return MagicMock()
        return MagicMock()

    def active(self, professor_id: str, fact_type: str) -> list[dict]:
        return [r for r in self.rows if r["professor_id"] == professor_id and r["fact_type"] == fact_type and r["status"] == "active"]


def _write(conn, value_raw, value_normalized=None, fact_type="education"):
    return _upsert_fact(
        conn,
        professor_id="PROF-X",
        fact_type=fact_type,
        value_raw=value_raw,
        value_normalized=value_normalized,
        source_page_id=_PAGE_ID,
        evidence_span="span",
        confidence=Decimal("0.85"),
        run_id=_RUN_ID,
    )


def test_three_structured_formats_yield_one_active_row():
    conn = _FakeConn()
    _write(conn, "Tsinghua University | Ph.D. | Computer Science | 2010-2015")
    assert _write(conn, '{"school": "Tsinghua University", "degree": "Ph.D.", "field": "Computer Science"}') == "updated"
    assert (
        _write(
            conn,
            '{"school": "Tsinghua University (清华大学)", "degree": "Ph.D. (博士)", "field": "Computer Science"}',
        )
        == "updated"
    )
    active = conn.active("PROF-X", "education")
    assert len(active) == 1
    # keep-richest: the pipe row carrying the year range survives
    assert active[0]["value_raw"] == "Tsinghua University | Ph.D. | Computer Science | 2010-2015"


def test_keep_richest_upgrades_yearless_json_to_pipe_with_years():
    conn = _FakeConn()
    assert _write(conn, '{"organization": "Tsinghua", "role": "Postdoc"}', fact_type="work_experience") == "inserted"
    assert _write(conn, "Tsinghua | Postdoc | 2017-2020", fact_type="work_experience") == "inserted"
    active = conn.active("PROF-X", "work_experience")
    assert len(active) == 1
    assert active[0]["value_raw"] == "Tsinghua | Postdoc | 2017-2020"


def test_distinct_periods_stay_two_active_rows():
    conn = _FakeConn()
    _write(conn, "Peking University | Master | Chemistry | 2013-2016")
    _write(conn, "Peking University | Ph.D. | Chemistry | 2016-2020")
    assert len(conn.active("PROF-X", "education")) == 2


def test_distinct_fields_stay_two_active_rows():
    conn = _FakeConn()
    _write(conn, "Tsinghua University | Bachelor | Economics | 2008-2012")
    _write(conn, "Tsinghua University | Bachelor | Environmental Engineering | 2008-2012")
    assert len(conn.active("PROF-X", "education")) == 2


def test_idempotent_rerun_is_noop():
    conn = _FakeConn()
    _write(conn, "Tsinghua University | Ph.D. | CS | 2010-2015")
    before = list(conn.rows)
    assert _write(conn, "Tsinghua University | Ph.D. | CS | 2010-2015") == "updated"
    assert len(conn.active("PROF-X", "education")) == 1
    # no new row, no status churn
    assert conn.rows == before
