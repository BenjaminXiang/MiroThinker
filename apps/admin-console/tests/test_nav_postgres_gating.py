"""E — the console pages stay honest when the console database is missing.

Fixture source: the shipped static pages, served over the real route graph with a
scratch session. The gate itself runs in the browser, so these lock the shape the
page contract needs — the marked entries, the one-shot signal read, the fail-open
guards, the hidden commit control and the inline failure detail. The rendered
behaviour is confirmed in a browser (see .agents/runs/connect-collection-line/).
"""

from __future__ import annotations

import re

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


def test_seeds_page_offers_the_two_outcome_actions() -> None:
    """Row 1: the trigger pair speaks outcomes, not our preview/sample vocabulary."""

    page = _text("/seeds")

    assert 'data-action="check"' in page
    assert "检查名册</button>" in page
    assert "只访问名册页确认能不能解析，不写入任何数据（约 1 分钟）" in page
    assert 'data-action="collect"' in page
    assert "开始抓取</button>" in page
    assert "抓取该名册下的教授主页并写入数据（会真实访问学校网站）" in page


def _scope_select(page: str) -> str:
    match = re.search(r'<select id="scopeSelect"[^>]*>(.*?)</select>', page, re.S)

    assert match, "the 抓取范围 selector is missing"
    return match.group(1)


def test_seeds_page_scope_selector_carries_the_legal_combinations_only() -> None:
    """The four options are the page's whole vocabulary of trigger parameters."""

    page = _text("/seeds")
    select = _scope_select(page)

    assert re.findall(
        r'<option value="([^"]+)"(?: selected)?>([^<]+)</option>', select
    ) == [
        ("sample:20", "前 20 条"),
        ("sample:50", "前 50 条"),
        ("sample:100", "前 100 条"),
        ("full", "全部"),
    ]
    assert '<option value="sample:20" selected>' in select  # default
    assert re.search(r"抓取范围\s*<select id=\"scopeSelect\"", page)


def test_seeds_page_scope_options_map_to_the_documented_request_bodies() -> None:
    page = _text("/seeds")

    assert '{ mode: "sample", limit: 20 }' in page
    assert '{ mode: "sample", limit: 50 }' in page
    assert '{ mode: "sample", limit: 100 }' in page
    assert '{ mode: "full" }' in page
    assert '{ mode: "preview" }' in page  # 检查名册
    # no fifth combination: a limit outside 20/50/100, or a limit on 全部
    assert re.findall(r"limit: (\d+)", page) == ["20", "50", "100"]


def test_seeds_page_never_writes_without_the_confirm() -> None:
    page = _text("/seeds")

    assert '"确认抓取「"' in page
    assert '"教授主页？会真实访问学校网站。"' in page
    assert "全部抓取可能耗时较长（上千条时可能超过任务上限）。" in page
    assert "if (!window.confirm(message)) return;" in page
    # the gate sits between the click and the POST the write happens through
    assert page.index("if (!window.confirm(message)) return;") < page.index(
        "await trigger(id, scope.body, scope.banner);"
    )
    assert "检查名册" in page and '"已开始："' in page


def test_seeds_page_drops_the_internal_mode_vocabulary() -> None:
    page = _text("/seeds")

    for gone in (
        "预览抓取",
        "抽样抓取",
        "触发抓取走闸门",
        "预览 = 只跑发现阶段",
        "抽样 = 抓取上限 20 条画像",
        'data-action="preview"',
        'data-action="sample"',
    ):
        assert gone not in page


def test_seeds_page_maps_the_interrupted_status() -> None:
    page = _text("/seeds")

    assert "已中断" in page
    assert "interrupted" in page


def test_seed_run_history_speaks_the_operator_language() -> None:
    page = _text("/seeds")

    assert "检查名册" in page
    assert "全部抓取" in page
    assert "抓取 前 " in page  # 「抓取 前 20 条」按上限拼出来
    assert "MODE_LABEL" not in page
