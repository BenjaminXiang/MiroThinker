"""Unit tests for `scripts/import_professor_seeds.py`.

The plan/report logic runs against an in-memory stub registry; the CLI tests patch the
connection factory, so no test touches a database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.storage.seeds import SeedCreate
from scripts import import_professor_seeds as importer
from scripts.import_professor_seeds import (
    SeedImportError,
    load_roster_seeds,
    main,
    render_report,
    run_import,
)

DSN = "postgresql://miroflow:secret@127.0.0.1:55458/miroflow_collection_v1"

ROSTER = """\
南方科技大学 https://www.sustech.edu.cn/zh/letter/
深圳技术大学 人工智能学院 https://ai.sztu.edu.cn/szdw/jytd/js.htm
深圳技术大学 新材料与新能源学院 https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004
"""

OVERLAP = """\
南方科技大学 https://www.sustech.edu.cn/zh/letter/
北京大学深圳研究生院 https://www.pkusz.edu.cn/szdw.htm
"""


class StubRegistry:
    """In-memory stand-in for the two `backend.storage.seeds` calls the importer makes."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = set(existing or ())
        self.created: list[SeedCreate] = []

    def get_by_url(self, seed_url: str) -> object | None:
        return object() if seed_url in self._existing else None

    def create(self, payload: SeedCreate) -> object:
        self.created.append(payload)
        self._existing.add(str(payload.seed_url))
        return payload


class StubConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def seeds_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "e2e_seeds"
    directory.mkdir()
    (directory / "stem.md").write_text(ROSTER, encoding="utf-8")
    (directory / "overlap.md").write_text(OVERLAP, encoding="utf-8")
    return directory


def _statuses(report: importer.ImportReport) -> dict[str, str]:
    return {str(row.payload.seed_url): row.status for row in report.rows}


def test_load_roster_seeds_deduplicates_urls_across_files(seeds_dir: Path) -> None:
    seeds, duplicates = load_roster_seeds(seeds_dir)

    assert [seed.roster_url for seed in seeds] == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://www.pkusz.edu.cn/szdw.htm",
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
    ]
    assert duplicates == 1


def test_plan_classifies_every_distinct_url_and_reads_school_department(
    seeds_dir: Path,
) -> None:
    report = run_import(
        seeds_dir=seeds_dir,
        registry=StubRegistry({"https://www.sustech.edu.cn/zh/letter/"}),
        apply=False,
        include_unresolved=False,
    )

    assert report.parsed_seed_count == 5
    assert report.duplicate_seed_count == 1
    assert _statuses(report) == {
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm": "would_create",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004": (
            "would_create"
        ),
        "https://www.pkusz.edu.cn/szdw.htm": "would_create",
        "https://www.sustech.edu.cn/zh/letter/": "skipped_existing",
    }
    rows = {str(row.payload.seed_url): row for row in report.rows}
    sztu_row = rows["https://ai.sztu.edu.cn/szdw/jytd/js.htm"]
    assert (sztu_row.payload.school, sztu_row.payload.department) == (
        "深圳技术大学",
        "人工智能学院",
    )
    assert sztu_row.adapter_name == "sztu-teacher-family"
    assert rows["https://www.pkusz.edu.cn/szdw.htm"].adapter_name == "pkusz-szdw-hub"
    assert (
        rows[
            "https://nmne.sztu.edu.cn/picturers.jsp?"
            "urltype=tree.TreeTempUrl&wbtreeid=1004"
        ].adapter_name
        == "sztu-nmne-picturers-roster"
    )


def test_dry_run_never_writes_even_with_include_unresolved(seeds_dir: Path) -> None:
    registry = StubRegistry()

    report = run_import(
        seeds_dir=seeds_dir,
        registry=registry,
        apply=False,
        include_unresolved=True,
    )

    assert registry.created == []
    assert set(_statuses(report).values()) == {"would_create"}
    assert report.apply is False


def test_apply_creates_only_missing_rows_and_is_idempotent(seeds_dir: Path) -> None:
    registry = StubRegistry({"https://www.pkusz.edu.cn/szdw.htm"})

    first = run_import(
        seeds_dir=seeds_dir,
        registry=registry,
        apply=True,
        include_unresolved=False,
    )
    second = run_import(
        seeds_dir=seeds_dir,
        registry=registry,
        apply=True,
        include_unresolved=False,
    )

    assert [str(payload.seed_url) for payload in registry.created] == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
    ]
    assert _statuses(first)["https://www.pkusz.edu.cn/szdw.htm"] == "skipped_existing"
    assert set(_statuses(second).values()) == {"skipped_existing"}


def test_include_unresolved_decides_whether_unrouted_rows_are_written(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "e2e_seeds"
    directory.mkdir()
    (directory / "unknown.md").write_text(
        "示例大学 师资队伍 https://example.com/teacher/list.htm\n", encoding="utf-8"
    )

    planned = run_import(
        seeds_dir=directory,
        registry=StubRegistry(),
        apply=False,
        include_unresolved=False,
    )
    planned_text = render_report(planned, seeds_dir=directory, registry_configured=True)

    assert _statuses(planned) == {
        "https://example.com/teacher/list.htm": "skipped_unresolved"
    }
    assert "unresolved urls (no registered adapter):" in planned_text
    assert "  - https://example.com/teacher/list.htm" in planned_text
    assert "pass --include-unresolved to register them anyway" in planned_text

    registry = StubRegistry()
    applied = run_import(
        seeds_dir=directory,
        registry=registry,
        apply=True,
        include_unresolved=True,
    )

    assert [str(payload.seed_url) for payload in registry.created] == [
        "https://example.com/teacher/list.htm"
    ]
    assert _statuses(applied) == {"https://example.com/teacher/list.htm": "created"}


def test_render_report_counts_states_for_the_routed_corpus(seeds_dir: Path) -> None:
    report = run_import(
        seeds_dir=seeds_dir,
        registry=StubRegistry({"https://www.sustech.edu.cn/zh/letter/"}),
        apply=False,
        include_unresolved=False,
    )

    text = render_report(report, seeds_dir=seeds_dir, registry_configured=True)

    assert "parsed entries: 5 (1 duplicate URL(s) folded)" in text
    assert "distinct urls: 4" in text
    assert (
        "created: 0 | would_create: 3 | skipped_existing: 1 | skipped_unresolved: 0"
        in text
    )
    assert "sztu-nmne-picturers-roster" in text
    assert "unresolved urls (no registered adapter):" not in text
    assert "dry-run: nothing written" in text


def test_entry_without_institution_is_reported_as_a_real_error(tmp_path: Path) -> None:
    directory = tmp_path / "e2e_seeds"
    directory.mkdir()
    (directory / "unknown.md").write_text(
        "https://example.com/teacher/1\n", encoding="utf-8"
    )

    with pytest.raises(SeedImportError):
        run_import(
            seeds_dir=directory,
            registry=None,
            apply=False,
            include_unresolved=False,
        )


def test_cli_writes_only_with_apply_and_never_echoes_the_dsn(
    monkeypatch: pytest.MonkeyPatch,
    seeds_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = StubRegistry()
    connection = StubConnection()
    monkeypatch.setattr(importer.psycopg, "connect", lambda dsn: connection)
    monkeypatch.setattr(importer, "PostgresSeedRegistry", lambda conn: registry)

    assert main(["--seeds-dir", str(seeds_dir), "--dsn", DSN]) == 0
    assert registry.created == []
    dry_run_output = capsys.readouterr()
    assert "dry-run: nothing written" in dry_run_output.out
    assert "secret" not in dry_run_output.out
    assert "sztu-nmne-picturers-roster" in dry_run_output.out
    assert connection.closed is True

    assert main(["--seeds-dir", str(seeds_dir), "--dsn", DSN, "--apply"]) == 0
    assert [str(payload.seed_url) for payload in registry.created] == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://www.pkusz.edu.cn/szdw.htm",
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
    ]

    assert main(["--seeds-dir", str(seeds_dir), "--dsn", DSN, "--apply"]) == 0
    assert [str(payload.seed_url) for payload in registry.created] == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://www.pkusz.edu.cn/szdw.htm",
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
    ]


def test_cli_refuses_apply_without_a_dsn(
    monkeypatch: pytest.MonkeyPatch,
    seeds_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["--seeds-dir", str(seeds_dir), "--apply"]) == 2
    assert "--apply needs a database" in capsys.readouterr().err


def test_cli_reports_a_missing_seeds_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nope"

    assert main(["--seeds-dir", str(missing)]) == 2
    assert f"seeds directory not found: {missing}" in capsys.readouterr().err
