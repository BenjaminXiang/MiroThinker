"""E — the console pages stay honest when the console database is missing.

Fixture source: the shipped static pages, served over the real route graph with a
scratch session. The gate itself runs in the browser, so these lock the shape the
page contract needs — the marked entries, the one-shot signal read, the fail-open
guards, the hidden commit control and the inline failure detail. The rendered
behaviour is confirmed in a browser (see .agents/runs/connect-collection-line/).
"""

from __future__ import annotations

from tests.conftest import authorized_client


def _text(path: str) -> str:
    response = authorized_client(raise_server_exceptions=False).get(path)

    assert response.status_code == 200, path
    return response.text


def test_main_marks_the_entries_that_need_the_console_database() -> None:
    page = _text("/main")

    assert '<a href="/upload" data-requires-postgres>上传导入</a>' in page
    assert '<a href="/seeds" data-requires-postgres>Seed 管理</a>' in page
    assert 'href="/jobs">任务运维</a>' in page  # the unmarked entries keep their shape


def test_main_loads_the_shared_nav_that_runs_the_gate() -> None:
    """The marked entries only hide if the script that reads them is on the page."""

    page = _text("/main")

    assert '<script src="/static/nav_auth.js"' in page


def test_nav_script_gates_on_the_single_availability_signal() -> None:
    script = _text("/static/nav_auth.js")

    assert "[data-requires-postgres]" in script
    assert "/api/canonical-v2/admin/jobs" in script
    assert "available !== false" in script
    assert "entry.hidden = true" in script


def test_nav_script_leaves_the_entries_when_the_signal_is_unreadable() -> None:
    """Fail-open: offline, signed out (302/401), or a payload without the flag."""

    script = _text("/static/nav_auth.js")

    assert "!response.ok || response.redirected" in script
    assert "response.json().catch" in script
    assert "!postgres ||" in script


def test_nav_script_does_not_hijack_the_entry_page() -> None:
    """`/main` shows the login form: its own 401 must not bounce the browser."""

    script = _text("/static/nav_auth.js")

    assert "if (!entryPage) load();" in script
    assert "if (button && !entryPage)" in script


def test_upload_page_hides_the_commit_control_in_the_degraded_branch() -> None:
    page = _text("/upload")

    assert 'document.getElementById("submit").hidden = !available;' in page
    assert 'id="dryRunSubmit"' in page
    assert 'document.getElementById("dryRunSubmit").hidden = available;' in page


def test_upload_page_copy_matches_the_hidden_control() -> None:
    page = _text("/upload")

    assert "提交导入不可用（上传按钮已隐藏）" in page


def test_seeds_page_renders_the_failure_reason_inline() -> None:
    page = _text("/seeds")

    assert "failureReason(run)" in page
    assert "exit_code" in page
    assert "stderr_excerpt" in page
    assert "escapeHtml" in page
    assert "clip(run.stderr_excerpt, 160)" in page


def test_seeds_page_explains_the_unconfigured_database_code() -> None:
    page = _text("/seeds")

    assert "console_database_not_configured" in page
    assert "DATABASE_URL" in page


def test_seeds_page_maps_the_interrupted_status() -> None:
    page = _text("/seeds")

    assert "已中断" in page
    assert "interrupted" in page
