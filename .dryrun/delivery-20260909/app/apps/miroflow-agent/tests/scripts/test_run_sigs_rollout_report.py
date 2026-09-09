from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_sigs_rollout_report.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location("run_sigs_rollout_report", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _SequencedConn:
    def __init__(self, result_sets: list[list[dict[str, Any]]]):
        self._result_sets = list(result_sets)
        self.calls: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> _FakeResult:
        self.calls.append((" ".join(query.split()), params))
        if not self._result_sets:
            raise AssertionError("Unexpected execute call")
        return _FakeResult(self._result_sets.pop(0))


def test_build_report_returns_sigs_rollout_shape() -> None:
    cli = _import_cli()
    conn = _SequencedConn(
        [
            [{"version_num": "V040"}],
            [
                {
                    "id": 8,
                    "school": "清华大学深圳国际研究生院",
                    "department": None,
                    "seed_url": "https://www.sigs.tsinghua.edu.cn/7644/list.htm",
                    "last_run_status": "success",
                }
            ],
            [{"total": 254, "ready": 174, "with_primary_page": 254}],
            [{"pages": 255, "pages_with_clean_text": 0, "official_pages": 255}],
            [
                {
                    "links": 4768,
                    "verified": 4768,
                    "officially_listed": 4768,
                }
            ],
            [
                {
                    "linked_papers": 4669,
                    "with_abstract": 2148,
                    "with_summary_zh": 4,
                    "ready": 3,
                    "page_only": 1369,
                    "dblp": 0,
                }
            ],
            [
                {"canonical_source": "openalex", "row_count": 3000},
                {"canonical_source": "prof_page_only", "row_count": 1369},
            ],
            [
                {"title_match_source": "openalex", "row_count": 2100},
                {"title_match_source": "crossref", "row_count": 12},
            ],
            [{"stage": "paper_attribution", "severity": "medium", "n": 3}],
            [
                {
                    "paper_id": "PAPER-1",
                    "title_clean": "A paper",
                    "canonical_source": "openalex",
                    "quality_status": "needs_enrichment",
                    "abstract_len": 1200,
                    "professor_count": 1,
                }
            ],
        ]
    )

    payload = cli.build_report(conn, institution="清华大学深圳国际研究生院")

    assert payload["institution"] == "清华大学深圳国际研究生院"
    assert payload["alembic_version"] == "V040"
    assert payload["readiness"]["v040_applied"] is True
    assert payload["professors"]["total"] == 254
    assert payload["paper_links"]["verified"] == 4768
    assert payload["papers"]["summary_zh_gap"] == 2144
    assert payload["papers_by_canonical_source"]["prof_page_only"] == 1369
    assert payload["title_resolution_sources"]["crossref"] == 12
    assert payload["pipeline_issue_counts"][0]["stage"] == "paper_attribution"
    assert payload["missing_summary_samples"][0]["paper_id"] == "PAPER-1"

    called_sql = " ".join(call[0] for call in conn.calls)
    assert "professor_affiliation" in called_sql
    assert "paper_title_resolution_cache" in called_sql
    assert "resolved_paper_id" not in called_sql
    assert "digest(" in called_sql


def test_main_requires_database_url(monkeypatch, capsys) -> None:
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli.main([])

    assert exc.value.code == 1
    assert "DATABASE_URL is required" in capsys.readouterr().err


def test_main_prints_json_report(monkeypatch, capsys) -> None:
    cli = _import_cli()

    class _Conn:
        def __enter__(self):
            return "CONN"

        def __exit__(self, *_exc):
            return None

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(cli, "_open_conn", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "build_report",
        lambda conn, *, institution, sample_limit: {
            "conn": conn,
            "institution": institution,
            "sample_limit": sample_limit,
        },
    )

    exit_code = cli.main(["--institution", "Test University", "--sample-limit", "3"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "conn": "CONN",
        "institution": "Test University",
        "sample_limit": 3,
    }
