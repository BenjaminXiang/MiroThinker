"""RED-phase tests for M2.4 Unit 7 — CLI entrypoint.

Thin argparse shell over run_homepage_paper_ingest. Tests cover flag parsing,
dispatch to orchestrator, and DATABASE_URL env handling.
"""

from __future__ import annotations

from types import SimpleNamespace
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Import the script as a module — scripts/ needs to be importable.
_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_homepage_paper_ingest.py"
)


def _import_cli_module():
    """Load scripts/run_homepage_paper_ingest.py as a module for testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_homepage_paper_ingest", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(capsys):
    """--help emits usage and exits 0."""
    with patch.object(sys, "argv", ["run_homepage_paper_ingest.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli_module()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--limit" in captured.out


def test_cli_dispatches_dry_run_flag(monkeypatch, tmp_path):
    """--dry-run parses and dispatches with dry_run=True."""
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--limit",
            "5",
        ],
    )
    cli.main()
    assert called_kwargs.get("dry_run") is True
    assert called_kwargs.get("limit") == 5
    assert called_kwargs.get("include_owned_homepage_pages") is True


def test_cli_can_dispatch_official_profile_pages_only(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--official-profile-pages-only",
        ],
    )

    cli.main()

    assert called_kwargs.get("include_owned_homepage_pages") is False


def test_cli_dispatches_include_owned_homepage_pages_flag(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--include-owned-homepage-pages",
        ],
    )

    cli.main()

    assert called_kwargs.get("include_owned_homepage_pages") is True


def test_cli_dispatches_external_resolution_budget(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--external-resolution-max-per-professor",
            "3",
        ],
    )

    cli.main()

    assert called_kwargs.get("external_resolution_max_per_professor") == 3


def test_cli_dispatches_llm_publication_extraction(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}
    sentinel_extractor = object()

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    builder_kwargs: dict = {}

    def _fake_build_llm_publication_extractor(profile, **kwargs):
        builder_kwargs.update(kwargs)
        return sentinel_extractor

    monkeypatch.setattr(
        cli,
        "_build_llm_publication_extractor",
        _fake_build_llm_publication_extractor,
        raising=False,
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--llm-publication-extraction",
        ],
    )

    cli.main()

    assert called_kwargs.get("publication_extractor") is sentinel_extractor
    assert builder_kwargs.get("force_llm") is False


def test_cli_dispatches_force_llm_publication_extraction(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}
    builder_kwargs: dict = {}
    sentinel_extractor = object()

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    def _fake_build_llm_publication_extractor(profile, **kwargs):
        builder_kwargs.update(kwargs)
        return sentinel_extractor

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(
        cli,
        "_build_llm_publication_extractor",
        _fake_build_llm_publication_extractor,
        raising=False,
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--force-llm-publication-extraction",
        ],
    )

    cli.main()

    assert called_kwargs.get("publication_extractor") is sentinel_extractor
    assert builder_kwargs.get("force_llm") is True


def test_llm_publication_extractor_uses_model_specific_extra_body(monkeypatch):
    cli = _import_cli_module()
    captured_create_kwargs: dict = {}
    captured_openai_kwargs: dict = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured_create_kwargs.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"items": []}')
                    )
                ]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=lambda **kwargs: captured_openai_kwargs.update(kwargs)
            or fake_client
        ),
    )
    monkeypatch.setattr(
        cli,
        "resolve_professor_llm_settings",
        lambda *_args, **_kwargs: {
            "local_llm_base_url": "https://api.deepseek.com",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-v4-pro",
        },
    )

    extractor = cli._build_llm_publication_extractor(None, force_llm=True)
    extractor(
        (
            "<main><h2>Publications</h2><p>J. Wang, M. Li. Robust neural "
            "interface control for wearable robotics. IEEE Transactions on "
            "Robotics, 2024.</p></main>"
        ),
        page_url="https://example.edu/faculty/wang",
    )

    assert captured_create_kwargs["model"] == "deepseek-v4-pro"
    assert captured_create_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert captured_openai_kwargs["timeout"] == (
        cli._LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS
    )
    assert captured_openai_kwargs["max_retries"] == 0
    assert isinstance(captured_openai_kwargs["http_client"], httpx.Client)
    assert captured_openai_kwargs["http_client"].timeout.read == (
        cli._LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS
    )
    assert captured_openai_kwargs["http_client"].trust_env is False
    captured_openai_kwargs["http_client"].close()


def test_llm_publication_extractor_retries_transient_create_failure(monkeypatch):
    cli = _import_cli_module()
    attempts = 0

    class _FakeCompletions:
        def create(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary upstream disconnect")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"items": []}')
                    )
                ]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **_kwargs: fake_client),
    )
    monkeypatch.setattr(
        cli,
        "resolve_professor_llm_settings",
        lambda *_args, **_kwargs: {
            "local_llm_base_url": "https://api.deepseek.com",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-v4-pro",
        },
    )
    monkeypatch.setattr(
        cli,
        "_LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS",
        (0.0, 0.0),
        raising=False,
    )

    extractor = cli._build_llm_publication_extractor(None, force_llm=True)
    extractor(
        (
            "<main><h2>Publications</h2><p>J. Wang, M. Li. Robust neural "
            "interface control for wearable robotics. IEEE Transactions on "
            "Robotics, 2024.</p></main>"
        ),
        page_url="https://example.edu/faculty/wang",
    )

    assert attempts == 2


def test_llm_publication_extractor_breaks_after_consecutive_failures(monkeypatch):
    cli = _import_cli_module()
    attempts = 0

    class _FakeCompletions:
        def create(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise TimeoutError("upstream timed out")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **_kwargs: fake_client),
    )
    monkeypatch.setattr(
        cli,
        "resolve_professor_llm_settings",
        lambda *_args, **_kwargs: {
            "local_llm_base_url": "https://api.deepseek.com",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-v4-pro",
        },
    )
    monkeypatch.setattr(
        cli,
        "_LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS",
        (),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES",
        1,
        raising=False,
    )
    html = (
        "<main><h2>Publications</h2><p>J. Wang, M. Li. Robust neural "
        "interface control for wearable robotics. IEEE Transactions on "
        "Robotics, 2024.</p></main>"
    )

    extractor = cli._build_llm_publication_extractor(None, force_llm=True)
    first = extractor(html, page_url="https://example.edu/faculty/wang")
    second = extractor(html, page_url="https://example.edu/faculty/li")

    assert attempts == 1
    assert [publication.clean_title for publication in first] == [
        "Robust neural interface control for wearable robotics"
    ]
    assert [publication.clean_title for publication in second] == [
        "Robust neural interface control for wearable robotics"
    ]


def test_cli_commits_successful_ingest(monkeypatch, capsys):
    cli = _import_cli_module()
    conn = MagicMock()

    def _fake_run(conn_arg, **_kwargs):
        assert conn_arg is conn
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=1,
            profs_processed=1,
            profs_skipped=0,
            papers_linked_total=1,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.1,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--limit", "1"])

    assert cli.main() == 0
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()


def test_cli_rolls_back_failed_ingest(monkeypatch):
    cli = _import_cli_module()
    conn = MagicMock()

    def _fake_run(_conn, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--limit", "1"])

    assert cli.main() == 1
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_cli_dispatches_institution_filter(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--institution",
            "南方科技大学",
            "--dry-run",
        ],
    )
    cli.main()
    assert called_kwargs.get("institution") == "南方科技大学"


def test_cli_dispatches_department_and_seed_filters(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--institution",
            "南方科技大学",
            "--department",
            "计算机科学与工程系",
            "--seed-id",
            "42",
            "--dry-run",
        ],
    )

    cli.main()

    assert called_kwargs.get("institution") == "南方科技大学"
    assert called_kwargs.get("department") == "计算机科学与工程系"
    assert called_kwargs.get("seed_id") == "42"


def test_cli_dispatches_resume_flag_with_explicit_path(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    explicit = tmp_path / "my_checkpoint.jsonl"
    explicit.write_text("")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--resume",
            str(explicit),
        ],
    )
    cli.main()
    assert called_kwargs.get("resume_checkpoint_path") == explicit


def test_cli_missing_database_url_exits_nonzero(monkeypatch, capsys):
    """No DATABASE_URL env in non-dry-run → exit 1 with clear message."""
    cli = _import_cli_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--limit", "1"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0


def test_cli_prints_ingest_report_as_json(monkeypatch, capsys, tmp_path):
    cli = _import_cli_module()

    def _fake_run(conn, **kwargs):
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=10,
            profs_processed=8,
            profs_skipped=2,
            papers_linked_total=42,
            full_text_fetched_total=30,
            pipeline_issues_filed=1,
            run_duration_seconds=99.5,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--dry-run"])
    cli.main()
    captured = capsys.readouterr()
    import json

    # Script output must include a JSON blob with the report fields.
    found_json = False
    for line in captured.out.splitlines():
        try:
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("papers_linked_total") == 42:
                found_json = True
                assert payload["profs_processed"] == 8
                assert payload["pipeline_issues_filed"] == 1
                break
        except (json.JSONDecodeError, TypeError):
            continue
    assert found_json, f"expected JSON report in output, got: {captured.out!r}"
