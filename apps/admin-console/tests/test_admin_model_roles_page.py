"""I6 — the 模型与连接 card: role invariants the payload cannot carry.

Fixture source: the shipped static files read from disk (no network, no service,
no state directory) plus the backend modules that own the request shapes, so the
page's previews cannot drift from what the server actually calls. Behavioural
evidence for the same card (pickers, timeouts, per-role saves) lives in
`.agents/runs/connect-collection-line/model-roles-harness/render_check.cjs`,
which has no browser and does not run in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.services.canonical_v2_connection_tests import (
    _CHAT_PATH,
    _EMBEDDING_PATH,
    _RERANK_PATH,
    CONNECTIONS,
    SPEC_BY_KEY,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = REPO_ROOT / "apps" / "admin-console" / "backend" / "static"
_PAGE = (_STATIC / "admin.html").read_text(encoding="utf-8")
_SCRIPT = (_STATIC / "admin.js").read_text(encoding="utf-8")

ROLE_IDS = ("chat", "collection", "embedding", "rerank", "web")
# The role blocks that render an editable/runtime value need the effective rows.
_VALUE_ROLES = ("chat", "collection", "embedding", "rerank")
MODEL_ERROR_CODES = (
    "unauthorized",
    "unreachable",
    "timeout",
    "not_supported",
    "bad_response",
)


def _literal(name: str, *, closing: str = "\n};") -> str:
    start = _SCRIPT.index(name)
    end = _SCRIPT.index(closing, start)
    return _SCRIPT[start:end]


def _test_paths() -> dict[str, str]:
    block = _literal("const TEST_PATH_BY_KIND = {")
    return dict(re.findall(r'(\w+):\s*"([^"]+)"', block))


def test_every_value_role_renders_its_runtime_effective_rows() -> None:
    """A role that cannot say what is in effect is the defect this card removes."""

    for role_id in _VALUE_ROLES:
        assert f'id="{role_id}Effective"' in _PAGE, role_id
        assert f'renderRoleEffectiveRows("{role_id}"' in _SCRIPT, role_id
    assert 'id="role-web-body"' not in _PAGE  # the web role renders per provider


def test_every_backend_connection_belongs_to_exactly_one_role() -> None:
    """The connections the server can test must all be reachable from some role."""

    roles_block = _literal("const ROLES = {")
    for spec in CONNECTIONS:
        if spec.kind == "web_search":
            assert 'connection.kind === "web_search"' in _SCRIPT, spec.key
            continue
        assert f'"{spec.key}"' in roles_block, spec.key
    # The role→connection map is the page's only connection knowledge: it must not
    # grow a connection the server does not know.
    mapped = set(re.findall(r'connection:\s*"(\w+)"', roles_block))
    assert mapped <= set(SPEC_BY_KEY), mapped - set(SPEC_BY_KEY)


def test_the_preview_paths_are_the_ones_the_server_posts_to() -> None:
    """Preview URL ≡ request URL: same paths as the probe builder, per kind."""

    paths = _test_paths()

    assert paths["llm"] == _CHAT_PATH
    assert paths["rerank"] == _RERANK_PATH
    assert paths["embedding"] == _EMBEDDING_PATH
    assert 'const MODEL_PATH = "/v1/models"' in _SCRIPT


def test_the_model_list_is_probed_with_the_unsaved_values() -> None:
    """拉取模型列表 must send the form values, key included, and store nothing."""

    fetch_body = _SCRIPT[
        _SCRIPT.index("async function fetchModels(") : _SCRIPT.index(
            "function describeModelOutcome("
        )
    ]

    assert "modelLists.delete(roleId)" in fetch_body
    assert "request.base_url = base" in fetch_body
    assert "request.api_key = typed" in fetch_body
    assert "state.keys.get(role.connection)" in fetch_body
    # No endpoint ⇒ no outbound call: the honest answer is local.
    assert "还没有可用端点" in fetch_body
    assert fetch_body.index("还没有可用端点") < fetch_body.index("await fetch(")


def test_the_picker_switches_shape_at_two_hundred_models() -> None:
    assert "const MODEL_PICKER_LIMIT = 200" in _SCRIPT
    picker = _SCRIPT[
        _SCRIPT.index("function renderModelPicker(") : _SCRIPT.index(
            "function roleActions("
        )
    ]

    assert "ids.length <= MODEL_PICKER_LIMIT" in picker
    assert 'document.createElement("select")' in picker
    assert 'document.createElement("datalist")' in picker
    assert 'filter.setAttribute("list", datalistId)' in picker
    # 手填模型 ID is a first-class option in both shapes.
    assert picker.count("手填模型 ID") >= 2
    assert "手填模型 ID（保留上面输入框里的值）" in picker
    assert "也可以直接手填" in picker


def test_every_failure_the_endpoint_can_report_has_chinese_copy() -> None:
    block = _literal("const MODEL_ERROR_TEXT = {")
    codes = re.findall(r"(\w+):", block)

    assert tuple(codes) == MODEL_ERROR_CODES
    assert "密钥被拒绝（401/403）" in block
    assert "连不上该地址" in block
    assert "3 秒内没有响应" in block
    assert "该端点没有 /v1/models，请直接手填模型 ID" in block
    assert "返回内容无法解析" in block
    # request_url and elapsed_ms are always surfaced, success or failure.
    assert "payload.request_url" in _SCRIPT
    assert "payload.elapsed_ms" in _SCRIPT


def test_the_client_guard_is_three_seconds_and_aborts_the_call() -> None:
    assert "const MODELS_TIMEOUT_MS = 3000" in _SCRIPT
    fetch_body = _SCRIPT[
        _SCRIPT.index("async function fetchModels(") : _SCRIPT.index(
            "function describeModelOutcome("
        )
    ]

    assert "new AbortController()" in fetch_body
    assert "setTimeout(() => controller.abort(), MODELS_TIMEOUT_MS)" in fetch_body
    assert 'error.name === "AbortError"' in fetch_body


def test_keys_are_never_written_as_text() -> None:
    """A typed key may only exist in a password input and in a request body."""

    for line in _SCRIPT.splitlines():
        if "state.keys" in line:
            assert ".textContent" not in line, line
            assert "innerHTML" not in line, line
    assert 'input.type = "password"' in _SCRIPT


def test_the_embedding_role_reads_the_frozen_value_and_honours_readonly() -> None:
    assert "embedding_frozen" in _SCRIPT
    assert "readonly_reason" in _SCRIPT
    assert "服务线索引由发布包冻结：改它需要重建全部向量" in _PAGE
    assert "高级：采集侧覆盖" in _SCRIPT
    assert "只影响后续采集/构建，不改服务线索引" in _SCRIPT


def test_saving_and_testing_are_separate_and_say_so() -> None:
    assert "保存 ≠ 测试" in _SCRIPT
    assert "测试不改配置，保存才写文件" in _SCRIPT
    assert "保存 ≠ 测试" in _PAGE


# -- Round 10: card 2's duplicate probe removed, 「全部测试」 added --------------
# The card header keeps one aggregate control (script-built, like every other probe);
# it walks the roles sequentially because the server rate-limits per connection and
# per client (6/min, ≥1 s between two calls), so a parallel burst would 429 itself.

ALL_TEST_PROBES = (
    ("llm", "对话模型"),
    ("llm", "采集模型"),
    ("embedding", "嵌入模型"),
    ("rerank", "重排模型"),
    ("bocha", "Web 搜索（Bocha）"),
    ("serper", "Web 搜索（Serper）"),
)


def _block(start: str, end: str) -> str:
    return _SCRIPT[_SCRIPT.index(start) : _SCRIPT.index(end)]


def test_the_aggregate_probe_covers_every_connection_the_server_can_test() -> None:
    roles = _literal("const ALL_TEST_ROLES = [", closing="\n];")
    probes = tuple(re.findall(r'connection:\s*"(\w+)",\s*label:\s*"([^"]+)"', roles))

    assert probes == ALL_TEST_PROBES
    # Every testable connection is probed, and no connection is invented: web has two
    # providers, llm backs two roles.
    assert {connection for connection, _ in probes} == set(SPEC_BY_KEY)


def test_the_aggregate_run_is_sequential_and_spaced_for_the_rate_limits() -> None:
    gap = int(re.search(r"const ALL_TEST_GAP_MS = (\d+);", _SCRIPT).group(1))
    body = _block("async function runAllConnectionTests(", "// 「保存本卡」")

    assert gap >= 1000  # the server's min_interval_seconds for one connection
    assert "Promise.all" not in body
    assert body.index("await delay(ALL_TEST_GAP_MS)") < body.index("await probeRoleConnection(")
    assert "测试中 ${index + 1}/${ALL_TEST_ROLES.length}…" in body
    # never stuck disabled, even when a probe throws
    assert "finally" in body
    assert "button.disabled = false" in body[body.index("} finally {") :]


def test_the_aggregate_control_is_script_built_in_the_card_header() -> None:
    assert 'id="allTestsControls"' in _PAGE
    assert 'id="allTestsPanel"' in _PAGE
    assert ">全部测试<" not in _PAGE  # the shell holds no probe control
    assert 'button.textContent = "全部测试"' in _SCRIPT
    assert 'button.id = "test-all-roles"' in _SCRIPT


def test_a_role_without_an_endpoint_is_skipped_not_reported_as_a_failure() -> None:
    body = _block("async function probeRoleConnection(", "async function runAllConnectionTests(")

    assert "未配置端点，已跳过" in body
    assert body.index("allTestEndpoint(entry)") < body.index("await probeConnection(")
    assert body.index("未配置端点，已跳过") < body.index("await probeConnection(")
    # one row per role, rendered with the card's own row renderer
    assert "row(entry.label, result.text)" in _SCRIPT


def test_the_aggregate_lines_reuse_the_single_probe_wording() -> None:
    single = _block("async function testConnection(", "// 「保存本卡」")
    aggregate = _block("async function probeRoleConnection(", "async function runAllConnectionTests(")

    assert _SCRIPT.count("function describeConnectionTest(") == 1
    assert "describeConnectionTest(response, payload).text" in single
    assert "outcome = describeConnectionTest(response, payload);" in aggregate
    assert _SCRIPT.count("await probeConnection(") == 2
    # compact per-role shapes; the failure keeps the server's own reason and the URL
    assert "`可用（${outcome.latency_ms} ms）`" in aggregate
    assert "`不可用：${outcome.detail}（请求 ${url || \"—\"}）`" in aggregate
    assert "`未测：${outcome.text}`" in aggregate


def test_card_two_no_longer_carries_a_second_rerank_probe() -> None:
    serving = _PAGE[_PAGE.index('id="card-serving"') : _PAGE.index('id="card-paths"')]

    assert 'id="testRerank"' not in _PAGE
    assert "测试 Rerank 连通性" not in serving
    assert "Rerank 连通性测试已移到「模型与连接 › 重排模型」" in serving
    assert "el(\"testRerank\")" not in _SCRIPT
    assert "rerankTestResult" not in _SCRIPT
    # the connectivity test itself moved, it was not dropped: the role block still probes
    assert "testButton.id = `role-${roleId}-test`" in _SCRIPT
    rerank_actions = _block('roleActions("rerank"', "function renderWebRole(")
    assert "test: true" in rerank_actions
