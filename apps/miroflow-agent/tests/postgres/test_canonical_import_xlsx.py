from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
import psycopg
from psycopg.types.json import Jsonb
import pytest

from src.data_agents.company.canonical_import import import_company_xlsx_to_postgres


TEST_SEED_ID = "qimingpian-shenzhen-test"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _real_xlsx_path() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _scalar(
    conn: psycopg.Connection, query: str, params: tuple[object, ...] = ()
) -> object:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _truncate_canonical_tables(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        TRUNCATE TABLE
            company_signal_event,
            company_news_item,
            company_fact,
            company_team_member,
            company_snapshot,
            company,
            source_row_lineage,
            import_batch,
            pipeline_run,
            seed_registry
        RESTART IDENTITY CASCADE
        """
    )


def _insert_seed_registry(
    conn: psycopg.Connection, seed_id: str = TEST_SEED_ID
) -> None:
    conn.execute(
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            priority,
            refresh_policy,
            status,
            config
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            seed_id,
            "company_xlsx",
            "test",
            f"file://{_real_xlsx_path()}",
            100,
            "manual",
            "active",
            Jsonb({"source": "pytest"}),
        ),
    )


@pytest.fixture()
def canonical_test_dsn(pg_migrated, pg_dsn: str) -> str:
    del pg_migrated
    conn = psycopg.connect(pg_dsn)
    try:
        _truncate_canonical_tables(conn)
        _insert_seed_registry(conn)
        conn.commit()
        yield pg_dsn
    finally:
        _truncate_canonical_tables(conn)
        conn.commit()
        conn.close()


def test_import_real_xlsx_1025_companies(canonical_test_dsn: str):
    report = import_company_xlsx_to_postgres(
        _real_xlsx_path(),
        dsn=canonical_test_dsn,
        seed_id=TEST_SEED_ID,
    )

    assert 1020 <= report.records_new_company <= 1030
    assert report.records_failed == 0

    with psycopg.connect(canonical_test_dsn) as conn:
        assert 1020 <= _scalar(conn, "SELECT count(*) FROM company") <= 1030
        assert 1020 <= _scalar(conn, "SELECT count(*) FROM company_snapshot") <= 1030
        assert 1000 <= _scalar(conn, "SELECT count(*) FROM company_team_member") <= 5000
        assert (
            400
            <= _scalar(
                conn,
                """
                SELECT count(*)
                FROM company_signal_event
                WHERE event_type = 'funding'
                """,
            )
            <= 900
        )

        snapshot_row = conn.execute(
            """
            SELECT industry, years_established
            FROM company_snapshot
            WHERE company_name_xlsx = %s
            ORDER BY snapshot_created_at DESC
            LIMIT 1
            """,
            ("极智视觉科技（深圳）有限公司",),
        ).fetchone()
        assert snapshot_row == ("VR/AR", 6)

        team_rows = conn.execute(
            """
            SELECT raw_name
            FROM company_team_member tm
            JOIN company_snapshot cs ON cs.snapshot_id = tm.snapshot_id
            WHERE cs.company_name_xlsx = %s
            ORDER BY tm.member_order
            """,
            ("深圳旭宏医疗科技有限公司",),
        ).fetchall()
        assert [row[0] for row in team_rows] == ["王博洋", "杨馥诚", "罗杰"]

        funding_row = conn.execute(
            """
            SELECT event_subject_normalized->>'round'
            FROM company_signal_event cse
            JOIN company_snapshot cs ON cs.company_id = cse.company_id
            WHERE cs.company_name_xlsx = %s
              AND cse.event_type = 'funding'
            ORDER BY cse.event_date DESC
            LIMIT 1
            """,
            ("深圳旭宏医疗科技有限公司",),
        ).fetchone()
        assert funding_row is not None
        assert funding_row[0] == "A轮"


def test_import_is_idempotent_by_content_hash(canonical_test_dsn: str):
    xlsx_path = _real_xlsx_path()

    import_company_xlsx_to_postgres(
        xlsx_path,
        dsn=canonical_test_dsn,
        seed_id=TEST_SEED_ID,
    )

    with psycopg.connect(canonical_test_dsn) as conn:
        before_counts = {
            "company": _scalar(conn, "SELECT count(*) FROM company"),
            "company_snapshot": _scalar(conn, "SELECT count(*) FROM company_snapshot"),
            "company_team_member": _scalar(
                conn, "SELECT count(*) FROM company_team_member"
            ),
            "company_signal_event": _scalar(
                conn, "SELECT count(*) FROM company_signal_event"
            ),
            "source_row_lineage": _scalar(
                conn, "SELECT count(*) FROM source_row_lineage"
            ),
            "import_batch": _scalar(conn, "SELECT count(*) FROM import_batch"),
            "pipeline_run": _scalar(conn, "SELECT count(*) FROM pipeline_run"),
        }

    with pytest.raises(LookupError):
        import_company_xlsx_to_postgres(
            xlsx_path,
            dsn=canonical_test_dsn,
            seed_id=TEST_SEED_ID,
        )

    with psycopg.connect(canonical_test_dsn) as conn:
        after_counts = {
            "company": _scalar(conn, "SELECT count(*) FROM company"),
            "company_snapshot": _scalar(conn, "SELECT count(*) FROM company_snapshot"),
            "company_team_member": _scalar(
                conn, "SELECT count(*) FROM company_team_member"
            ),
            "company_signal_event": _scalar(
                conn, "SELECT count(*) FROM company_signal_event"
            ),
            "source_row_lineage": _scalar(
                conn, "SELECT count(*) FROM source_row_lineage"
            ),
            "import_batch": _scalar(conn, "SELECT count(*) FROM import_batch"),
            "pipeline_run": _scalar(conn, "SELECT count(*) FROM pipeline_run"),
        }

    assert after_counts == before_counts


def test_row_level_failure_does_not_abort_batch(
    canonical_test_dsn: str,
    tmp_path: Path,
):
    workbook_path = tmp_path / "partial_failure.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "sheet1"
    sheet.append(["专辑项目导出"])
    sheet.append(
        ["序号", "行业领域", "公司名称", "网址", "团队", "投资轮次", "投资时间"]
    )
    sheet.append(
        [
            "1",
            "先进制造",
            "深圳市甲公司有限公司",
            "https://a.example.com",
            "-",
            "-",
            "-",
        ]
    )
    sheet.append(["2", "先进制造", None, "https://bad.example.com", "-", "-", "-"])
    sheet.append(
        [
            "3",
            "医疗健康",
            "深圳市乙公司有限公司",
            "https://b.example.com",
            "-",
            "A轮",
            "2020.7.7",
        ]
    )
    sheet.append(
        ["4", "VR/AR", "深圳市丙公司有限公司", "https://c.example.com", "-", "-", "-"]
    )
    workbook.save(workbook_path)

    report = import_company_xlsx_to_postgres(
        workbook_path,
        dsn=canonical_test_dsn,
        seed_id=TEST_SEED_ID,
    )

    assert report.records_failed == 1
    assert report.records_new_company == 3

    with psycopg.connect(canonical_test_dsn) as conn:
        assert _scalar(conn, "SELECT count(*) FROM company") == 3
        assert _scalar(conn, "SELECT count(*) FROM company_snapshot") == 3
        run_status = conn.execute(
            """
            SELECT run_status
            FROM import_batch
            WHERE batch_id = %s
            """,
            (report.batch_id,),
        ).fetchone()
        assert run_status is not None
        assert run_status[0] == "partial"
