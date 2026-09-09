"""RED-phase tests for M1 follow-up — professor ORCID backfill CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_professor_orcid_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_professor_orcid_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _patch_argv:
    def __init__(self, argv):
        self.argv = argv
        self._saved = None

    def __enter__(self):
        self._saved = sys.argv
        sys.argv = self.argv

    def __exit__(self, *exc):
        sys.argv = self._saved


def test_cli_help(capsys):
    with _patch_argv(["run_professor_orcid_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--dry-run" in captured.out


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_professor_orcid_backfill.py", "--limit", "1"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code != 0


def test_cli_dry_run_no_upsert(monkeypatch):
    cli = _import_cli()

    # Mock conn returning one prof with no existing ORCID.
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "canonical_name": "王教授",
            "institution": "南方科技大学",
        }
    ]
    conn.execute.return_value = cursor
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    # Mock OpenAlex returning a match with ORCID.
    monkeypatch.setattr(
        cli,
        "_fetch_openalex_author",
        lambda name, institution, http_client=None: {
            "orcid": "https://orcid.org/0000-0001-2345-6789",
            "display_name": "Wang Jiao",
            "affiliations": [{"institution": {"display_name": "南方科技大学"}}],
        },
    )
    # Mock upsert writer — should NOT be called in dry-run.
    monkeypatch.setattr(cli, "upsert_professor_orcid", MagicMock())

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(["run_professor_orcid_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    cli.upsert_professor_orcid.assert_not_called()


def test_cli_persists_bare_orcid_on_match(monkeypatch):
    cli = _import_cli()

    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "canonical_name": "李教授",
            "institution": "清华大学深圳国际研究生院",
        }
    ]
    conn.execute.return_value = cursor
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    monkeypatch.setattr(
        cli,
        "_fetch_openalex_author",
        lambda name, institution, http_client=None: {
            "orcid": "https://orcid.org/0000-0002-1111-2222",
            "display_name": "Li Wei",
            "affiliations": [
                {"institution": {"display_name": "清华大学深圳国际研究生院"}}
            ],
        },
    )
    upsert_mock = MagicMock()
    monkeypatch.setattr(cli, "upsert_professor_orcid", upsert_mock)

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(["run_professor_orcid_backfill.py", "--limit", "1"]):
        cli.main()

    upsert_mock.assert_called_once()
    kwargs = upsert_mock.call_args.kwargs
    assert kwargs["orcid"] == "0000-0002-1111-2222"  # URL prefix stripped
    assert kwargs["source"] == "openalex"
    assert 0.0 <= kwargs["confidence"] <= 1.0
    assert kwargs["professor_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_cli_no_openalex_match_no_upsert(monkeypatch):
    cli = _import_cli()

    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "canonical_name": "无匹配",
            "institution": "无机构",
        }
    ]
    conn.execute.return_value = cursor
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    # OpenAlex returns None (no match).
    monkeypatch.setattr(cli, "_fetch_openalex_author", lambda *a, **kw: None)
    upsert_mock = MagicMock()
    monkeypatch.setattr(cli, "upsert_professor_orcid", upsert_mock)

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(["run_professor_orcid_backfill.py", "--limit", "1"]):
        cli.main()

    upsert_mock.assert_not_called()


def test_cli_openalex_exception_isolates_prof(monkeypatch):
    """One prof's OpenAlex failure must not abort the run."""
    cli = _import_cli()

    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "canonical_name": "出错",
            "institution": "X",
        },
        {
            "professor_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "canonical_name": "张教授",
            "institution": "Y",
        },
    ]
    conn.execute.return_value = cursor
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    call_count = [0]

    def _fake_fetch(name, institution, http_client=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("openalex 429")
        return {
            "orcid": "https://orcid.org/0000-0003-4444-5555",
            "display_name": "Zhang",
            "affiliations": [{"institution": {"display_name": "Y"}}],
        }

    monkeypatch.setattr(cli, "_fetch_openalex_author", _fake_fetch)
    upsert_mock = MagicMock()
    monkeypatch.setattr(cli, "upsert_professor_orcid", upsert_mock)

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(["run_professor_orcid_backfill.py", "--limit", "2"]):
        cli.main()

    # Prof 2 should have been written even though prof 1 errored.
    assert upsert_mock.call_count == 1
    assert upsert_mock.call_args.kwargs["orcid"] == "0000-0003-4444-5555"


def test_cli_ignores_openalex_record_with_null_orcid(monkeypatch):
    cli = _import_cli()

    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "canonical_name": "Prof",
            "institution": "X",
        }
    ]
    conn.execute.return_value = cursor
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    # Author found but no ORCID — must not upsert.
    monkeypatch.setattr(
        cli,
        "_fetch_openalex_author",
        lambda *a, **kw: {
            "orcid": None,
            "display_name": "Prof",
            "affiliations": [{"institution": {"display_name": "X"}}],
        },
    )
    upsert_mock = MagicMock()
    monkeypatch.setattr(cli, "upsert_professor_orcid", upsert_mock)

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(["run_professor_orcid_backfill.py", "--limit", "1"]):
        cli.main()

    upsert_mock.assert_not_called()
