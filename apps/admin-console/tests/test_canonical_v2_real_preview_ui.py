from __future__ import annotations

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import pytest

from backend.main import _create_route_shell


_REPO_ROOT = Path(__file__).resolve().parents[3]
_BROWSER_ACCEPTANCE_PATH = (
    _REPO_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py"
)
_CHAT_PATH = _REPO_ROOT / "apps/admin-console/backend/static/chat.html"
_BROWSE_PATH = _REPO_ROOT / "apps/admin-console/backend/static/browse.html"
_GUOXIAN_LOGO_PATH = (
    _REPO_ROOT / "apps/admin-console/backend/static/assets/guoxian-logo.jpg"
)
_S12G_VIEWPORT_MATRIX_ORACLE = (
    (320, 568),
    (360, 640),
    (360, 800),
    (412, 915),
    (375, 667),
    (390, 844),
    (430, 932),
    (667, 375),
    (844, 390),
    (768, 1024),
    (1024, 768),
    (1280, 720),
    (1440, 900),
)


@pytest.fixture(scope="module")
def chat_html() -> str:
    return _CHAT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def chat_css(chat_html: str) -> str:
    styles = re.findall(r"<style>(.*?)</style>", chat_html, flags=re.DOTALL)
    assert len(styles) == 1
    return styles[0]


@pytest.fixture(scope="module")
def chat_script(chat_html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", chat_html, flags=re.DOTALL)
    assert len(scripts) == 1
    return scripts[0]


@pytest.fixture(scope="module")
def browse_html() -> str:
    return _BROWSE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def browse_script(browse_html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", browse_html, flags=re.DOTALL)
    assert len(scripts) == 1
    return scripts[0]


def _section(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    return source[start_index : source.index(end, start_index)]


def _css_rule(source: str, selector_pattern: str) -> str:
    match = re.search(
        rf"(?m)^\s*(?:{selector_pattern})\s*\{{(?P<body>[^{{}}]*)\}}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, selector_pattern
    return match.group("body")


def _css_values(rule: str, property_name: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in re.findall(
            rf"(?:\A|;)\s*{re.escape(property_name)}\s*:\s*([^;]+)",
            rule,
            flags=re.DOTALL,
        )
    )


@pytest.mark.parametrize(
    "fixture_copy",
    (
        "Robotics Co",
        "陈艾达",
        "Evidence-bound robotics",
    ),
)
def test_chat_preview_contains_no_fixture_names_or_questions(
    chat_html: str,
    fixture_copy: str,
) -> None:
    assert fixture_copy not in chat_html


def test_public_chat_has_no_internal_browse_navigation(chat_html: str) -> None:
    assert 'href="/browse"' not in chat_html
    assert "返回数据目录" not in chat_html


def test_public_chat_uses_guoxian_brand_identity(chat_html: str) -> None:
    title = re.search(r"<title>(.*?)</title>", chat_html)
    assert title is not None
    assert title.group(1).strip() == "国先检索助手"

    header = _section(chat_html, '<header class="header">', "</header>")
    assert '<div class="brand-mark" aria-hidden="true">国先</div>' in header
    assert "<h1>国先检索助手</h1>" in header
    assert "科技信息检索 · 支持连续追问 · 补充公开网页信息" in header
    assert "Canonical V2 智能检索" not in header

    welcome = _section(chat_html, '<div class="welcome" id="welcome">', "</div>")
    assert "<strong>欢迎使用国先检索助手</strong>" in welcome
    assert "企业、教授、论文、专利、技术与产业" in welcome

    composer = _section(chat_html, '<footer class="composer">', "</footer>")
    assert "当前知识库与公开网页信息" in composer
    assert "展示的来源" in composer


@pytest.mark.parametrize(
    ("old_copy", "new_copy"),
    (
        ("正在根据当前候选版本准备可核验问题", "正在准备可核验的问题示例"),
        ("当前候选版本暂无可用名称", "暂无可用问题示例"),
        ("根据当前候选数据生成的可核验问题", "你可以试试这些问题"),
        ("正在读取企业、教授与论文候选数据…", "正在准备问题示例…"),
        ("当前候选问题暂不可用", "问题示例暂不可用"),
    ),
)
def test_public_demo_copy_uses_user_facing_language(
    chat_html: str,
    old_copy: str,
    new_copy: str,
) -> None:
    assert old_copy not in chat_html
    assert new_copy in chat_html


def test_public_chat_serves_guoxian_logo_as_jpeg() -> None:
    client = TestClient(_create_route_shell(include_review=False))

    response = client.get("/static/assets/guoxian-logo.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == _GUOXIAN_LOGO_PATH.read_bytes()


def test_public_root_enters_chat_without_advertising_internal_browse() -> None:
    client = TestClient(_create_route_shell(include_review=False))

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/chat"


def test_chat_preview_builds_questions_only_after_current_candidates_and_relations_load(
    chat_html: str,
    chat_script: str,
) -> None:
    demo_grid = re.search(
        r'<div class="demo-grid" id="demo-grid"[^>]*>(.*?)</div>',
        chat_html,
        flags=re.DOTALL,
    )
    assert demo_grid is not None
    assert "demo-chip" not in demo_grid.group(1)

    assert 'Object.freeze(["company", "professor", "paper"])' in chat_script
    assert 'company: "company_has_patent"' in chat_script
    assert 'professor: "professor_authored_paper"' in chat_script
    assert 'const candidateDomainPath = "api/canonical-v2/admin/domains/";' in chat_script

    loader = _section(
        chat_script,
        "async function loadDemoQuestions()",
        "form.addEventListener",
    )
    pages_loaded = loader.index("await loadCandidatePages()")
    relations_loaded = loader.index("await loadVerifiedRelations(candidatePages)")
    questions_built = loader.index(
        "buildSemanticQuestions(candidatePages, verifiedRelations)"
    )
    questions_rendered = loader.index("renderDemoQuestions(questions)")
    assert pages_loaded < relations_loaded < questions_built < questions_rendered

    candidate_name = _section(
        chat_script,
        "function candidateName(item)",
        "function namedCandidates",
    )
    assert "canonical_identity_id" not in candidate_name
    assert ".id" not in candidate_name
    assert "return null" in candidate_name


def test_chat_preview_renders_only_safe_current_web_evidence(
    chat_script: str,
) -> None:
    safe_url = _section(
        chat_script,
        "function safeCurrentWebUrl(value)",
        "function currentWebEvidenceRows",
    )
    assert "new URL(String(value))" in safe_url
    assert 'parsed.protocol !== "https:"' in safe_url
    assert "parsed.username" in safe_url
    assert "parsed.password" in safe_url

    renderer = _section(
        chat_script,
        "function renderCurrentWebEvidence(container, evidence)",
        "function renderCitations",
    )
    assert "currentWebEvidenceRows(evidence)" in renderer
    assert "snippet" in renderer
    assert "hostname" in renderer
    for internal_field in (
        "evidence_id",
        "object_id",
        "subject_id",
        "predicate",
        "value",
        "lane",
        "status",
        "content_sha256",
        "snapshot_id",
    ):
        assert internal_field not in renderer

    evidence_rows = _section(
        chat_script,
        "function currentWebEvidenceRows(evidence)",
        "function renderCurrentWebEvidence",
    )
    assert 'item.source_nature !== "current_web"' in evidence_rows
    assert "safeCurrentWebUrl(item.source_locator)" in evidence_rows
    assert (
        "renderCurrentWebEvidence(view.bubble, data.evidence || [])" not in chat_script
    )
    assert 'create("details", "evidence-disclosure")' in chat_script
    assert 'create("summary", "evidence-summary", "查看依据")' in chat_script
    assert "evidenceDetails.open = false" in chat_script


def test_chat_evidence_is_collapsed_and_internal_trace_is_not_rendered(
    chat_script: str,
) -> None:
    assistant_renderer = _section(
        chat_script,
        "function renderAssistant(",
        "function renderProcess(",
    )

    assert 'create("details", "evidence-disclosure")' in chat_script
    assert 'create("summary", "evidence-summary", "查看依据")' in chat_script
    assert ".open = false" in chat_script
    assert (
        "renderCitations(evidenceDetails, data.citations || [])" in assistant_renderer
    )
    assert "renderTrace(" not in assistant_renderer
    assert "renderCurrentWebEvidence(" not in assistant_renderer
    assert "response-meta" not in assistant_renderer

    assert "element.textContent = String(text)" in chat_script
    unsafe_html_property_access = re.compile(
        r"\.\s*(?:inner|outer)HTML\b"
        r"""|\[\s*(?:"(?:inner|outer)HTML"|'(?:inner|outer)HTML')\s*\]""",
        re.IGNORECASE,
    )
    assert unsafe_html_property_access.search(chat_script) is None
    assert "insertAdjacentHTML" not in chat_script
    assert "document.write" not in chat_script


def test_public_display_sanitizer_rejects_internal_tokens_and_keeps_real_copy(
    chat_script: str,
) -> None:
    sanitizer = _section(
        chat_script,
        "const unsafePublicTextPatterns",
        "async function fetchJson",
    )
    evidence_helpers = _section(
        chat_script,
        "function safeCurrentWebUrl(value)",
        "function renderCurrentWebEvidence",
    )
    values = (
        "深圳森合创新科技有限公司",
        "Keystroke dynamics enabled authentication",
        "公开前文。PROF-8000C9F994C3；公开后文。",
        "source:github",
        "paper:arxiv",
        "query:python",
        "paper-based",
        "https://example.test/company:overview?ref=public",
        "a" * 64,
        "COMP-012345abcdef",
        "professor-c-0123456789abcdef01234567",
        "web-object:sha256:" + "b" * 64,
        "source_nature=current_web",
        "COMP-3B95F48EB687",
    )
    harness = f"""
{sanitizer}
{evidence_helpers}
const values = {json.dumps(values, ensure_ascii=False)};
const evidence = [
  {{
    source_nature: "current_web",
    source_locator: "https://example.test/news",
    snippet: "公开网页介绍了该企业的最新进展。",
  }},
  {{
    source_nature: "current_web",
    source_locator: "https://example.test/leak",
    snippet: "COMP-012345abcdef",
  }},
  {{
    source_nature: "current_web",
    source_locator: "http://example.test/not-https",
    snippet: "不应展示",
  }},
  {{
    source_nature: "local",
    source_locator: "https://example.test/not-web",
    snippet: "不应展示",
  }},
];
console.log(JSON.stringify({{
  sanitized: values.map((item) => safePublicText(item)),
  evidence: currentWebEvidenceRows(evidence),
}}));
"""
    completed = subprocess.run(
        ["node", "-"],
        input=harness,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["sanitized"] == [
        "深圳森合创新科技有限公司",
        "Keystroke dynamics enabled authentication",
        "公开前文。；公开后文。",
        "source:github",
        "paper:arxiv",
        "query:python",
        "paper-based",
        "https://example.test/company:overview?ref=public",
        "a" * 64,
        None,
        None,
        None,
        None,
        None,
    ]
    assert payload["evidence"] == [
        {
            "href": "https://example.test/news",
            "hostname": "example.test",
            "snippet": "公开网页介绍了该企业的最新进展。",
        }
    ]

    for display_source in (
        "safePublicText(data.answer_text)",
        "safePublicText(citation.label)",
        "safePublicText(option?.label)",
        "safePublicText(item[field])",
    ):
        assert display_source in chat_script


def test_s12g_task8_browser_runner_owns_fixed_viewport_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _BROWSER_ACCEPTANCE_PATH.is_file(), _BROWSER_ACCEPTANCE_PATH
    source = _BROWSER_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    module_tree = ast.parse(source, filename=str(_BROWSER_ACCEPTANCE_PATH))
    matrix_owners = [
        node
        for node in module_tree.body
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "VIEWPORT_MATRIX"
                for target in node.targets
            )
        )
        or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "VIEWPORT_MATRIX"
        )
    ]
    assert len(matrix_owners) == 1
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "__main__"
        for node in module_tree.body
    )

    original_import = builtins.__import__

    def reject_top_level_playwright(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        assert name != "playwright" and not name.startswith("playwright."), name
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_top_level_playwright)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.chdir(tmp_path)
    before = tuple(tmp_path.iterdir())
    module_name = "_s12g_browser_acceptance_contract"
    spec = importlib.util.spec_from_file_location(module_name, _BROWSER_ACCEPTANCE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert tuple(tmp_path.iterdir()) == before
    assert module.VIEWPORT_MATRIX == _S12G_VIEWPORT_MATRIX_ORACLE
    assert len(module.VIEWPORT_MATRIX) == len(set(module.VIEWPORT_MATRIX))


def _load_s12g_browser_acceptance_module() -> object:
    module_name = "_s12g_browser_acceptance_helpers"
    spec = importlib.util.spec_from_file_location(module_name, _BROWSER_ACCEPTANCE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _with_s12g_real_chat_page(
    viewport: tuple[int, int],
    assertion: object,
    *,
    stream_body: str | None = None,
    stream_segments: tuple[str, ...] | None = None,
    stream_content_type: str = "text/event-stream; charset=utf-8",
    stream_abort: bool = False,
    delayed_duplicate_ms: int | None = None,
    delayed_duplicate_body: str | None = None,
) -> None:
    from playwright.sync_api import sync_playwright

    if stream_segments is not None:
        assert stream_body is not None
        assert "".join(stream_segments) == stream_body

    candidate_pages = {
        "company": {
            "items": [
                {
                    "canonical_identity_id": "company-c-111111111111111111111111",
                    "name": "公开企业示例",
                }
            ]
        },
        "professor": {
            "items": [
                {
                    "canonical_identity_id": "professor-c-222222222222222222222222",
                    "name": "公开教授示例",
                }
            ]
        },
        "paper": {
            "items": [
                {
                    "canonical_identity_id": "paper-c-333333333333333333333333",
                    "title": "公开论文示例",
                }
            ]
        },
    }

    def fulfill(route: object) -> None:
        request_url = route.request.url
        if request_url == "https://s12g.test/chat":
            route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=_CHAT_PATH.read_text(encoding="utf-8"),
            )
            return
        if request_url == "https://s12g.test/api/chat/stream" and stream_abort:
            route.abort("connectionfailed")
            return
        if (
            request_url == "https://s12g.test/api/chat/stream"
            and stream_body is not None
        ):
            route.fulfill(
                status=200,
                content_type=stream_content_type,
                body=stream_body,
            )
            return
        if "/related?" in request_url:
            route.fulfill(
                status=200, content_type="application/json", body='{"items":[]}'
            )
            return
        for domain, payload in candidate_pages.items():
            if f"/domains/{domain}?" in request_url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )
                return
        route.fulfill(status=404, content_type="application/json", body="{}")

    width, height = viewport
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.route("https://s12g.test/**", fulfill)
        try:
            page.goto("https://s12g.test/chat", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => document.getElementById('demo-grid')?.getAttribute('aria-busy') === 'false'"
            )
            if stream_segments is not None:
                segmented_fetch_installed = page.evaluate(
                    """(streamSegments) => {
                      const nativeFetch = window.fetch.bind(window);
                      const encoder = new TextEncoder();
                      window.fetch = async (...args) => {
                        const response = await nativeFetch(...args);
                        const input = args[0];
                        const requestUrl =
                          typeof input === "string" ? input : input?.url;
                        if (
                          !requestUrl ||
                          new URL(requestUrl, window.location.href).pathname !==
                            "/api/chat/stream"
                        ) {
                          return response;
                        }
                        const chunks = streamSegments.map(
                          (segment) => encoder.encode(segment),
                        );
                        const body = new ReadableStream({
                          start(controller) {
                            let index = 0;
                            const enqueueNext = () => {
                              if (index >= chunks.length) {
                                controller.close();
                                return;
                              }
                              controller.enqueue(chunks[index]);
                              index += 1;
                              window.setTimeout(enqueueNext, 250);
                            };
                            enqueueNext();
                          },
                        });
                        return new Response(body, {
                          status: response.status,
                          statusText: response.statusText,
                          headers: response.headers,
                        });
                      };
                      return true;
                    }""",
                    list(stream_segments),
                )
                assert segmented_fetch_installed is True
            if delayed_duplicate_ms is not None:
                duplicate_fetch_installed = page.evaluate(
                    """({delayMs, duplicateBody}) => {
                      const nativeFetch = window.fetch.bind(window);
                      let scheduled = false;
                      window.fetch = async (...args) => {
                        const response = await nativeFetch(...args);
                        const input = args[0];
                        const requestUrl =
                          typeof input === "string" ? input : input?.url;
                        if (
                          scheduled ||
                          !requestUrl ||
                          new URL(requestUrl, window.location.href).pathname !==
                            "/api/chat/stream"
                        ) {
                          return response;
                        }
                        scheduled = true;
                        const duplicateArgs = duplicateBody === null
                          ? (typeof input === "string"
                            ? [input, {...(args[1] || {})}]
                            : [input.clone()])
                          : [
                            requestUrl,
                            typeof input === "string"
                              ? {...(args[1] || {}), body: duplicateBody}
                              : {
                                method: input.method,
                                headers: input.headers,
                                body: duplicateBody,
                              },
                          ];
                        const submit = document.getElementById("chat-submit");
                        let sawPending = Boolean(submit?.disabled);
                        const observer = new MutationObserver(() => {
                          sawPending ||= Boolean(submit?.disabled);
                          if (!sawPending || submit?.disabled) return;
                          observer.disconnect();
                          window.setTimeout(async () => {
                            try {
                              const duplicate = await nativeFetch(...duplicateArgs);
                              await duplicate.body?.cancel();
                            } catch {
                              // The lifecycle oracle observes request failure separately.
                            }
                          }, delayMs);
                        });
                        observer.observe(submit, {attributes: true, childList: true});
                        return response;
                      };
                      return true;
                    }""",
                    {
                        "delayMs": delayed_duplicate_ms,
                        "duplicateBody": delayed_duplicate_body,
                    },
                )
                assert duplicate_fetch_installed is True
            assert callable(assertion)
            assertion(page)
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize(
    ("width", "height"),
    ((768, 1024), (1024, 768), (1280, 720), (1440, 900)),
)
def test_s12g_task8_real_chat_wide_shell_geometry(width: int, height: int) -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_geometry(page: object) -> None:
        snapshot = module._browser_geometry(page, ())
        report = module._evaluate_geometry_snapshot(snapshot)
        shell = snapshot["shell"]
        visual = snapshot["viewport"]["visual"]
        expected_width = min(980, visual["width"] - 32)

        assert shell["width"] == pytest.approx(expected_width, abs=1.5)
        assert shell["left"] == pytest.approx(
            visual["offset_left"] + (visual["width"] - expected_width) / 2,
            abs=1.5,
        )
        assert shell["right"] <= visual["offset_left"] + visual["width"] + 1.5
        assert report["status"] == "passed", report

    _with_s12g_real_chat_page((width, height), assert_geometry)


@pytest.mark.parametrize("viewport", ((667, 375), (844, 390)))
def test_s12g_task8_real_chat_short_landscape_skips_hidden_demo_controls(
    viewport: tuple[int, int],
) -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_short_layout(page: object) -> None:
        page.set_default_timeout(1_000)
        report = module._exercise_presentation_states(page)

        assert report["status"] == "passed", report
        assert report["defect_codes"] == []
        assert report["short_layout"] is True
        assert report["short_layout_controls"] == {
            "demo_strip_hidden": True,
            "demo_toggle_hidden": True,
        }
        assert report["toggle_was_visible"] is False
        assert [state["state"] for state in report["states"]] == [
            "landing",
            "conversation",
        ]
        expected_actionability = {
            "status": "passed",
            "defect_codes": [],
            "required_controls": ["#chat-input", "#chat-submit"],
            "controls": {
                "#chat-input": {
                    "seen": True,
                    "visible": True,
                    "actionable": True,
                },
                "#chat-submit": {
                    "seen": True,
                    "visible": True,
                    "actionable": True,
                },
            },
        }
        for state in report["states"]:
            assert state["actionable_controls"] == expected_actionability
            input_target = next(
                target
                for target in state["core_geometry"]["targets"]
                if target["selector"] == "#chat-input"
            )
            assert input_target["width"] >= 44
            assert input_target["height"] >= 44

    _with_s12g_real_chat_page(viewport, assert_short_layout)


@pytest.mark.parametrize("viewport", ((320, 568), (667, 375)))
def test_s12g_task8_hidden_demo_keeps_messages_and_composer_in_grid_tracks(
    viewport: tuple[int, int],
) -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_long_content_geometry(page: object) -> None:
        presentation_changed = page.evaluate(
            "() => setPresentationState('conversation')"
        )
        assert presentation_changed is True
        page.evaluate(
            """() => {
              const messages = document.getElementById("messages");
              messages.replaceChildren();
              for (let index = 0; index < 80; index += 1) {
                const article = document.createElement("article");
                article.className = "message user";
                article.textContent = `长内容 ${index} `.repeat(20);
                messages.append(article);
              }
            }"""
        )
        module._settle_geometry(page)
        snapshot = module._browser_geometry(page, ())
        report = module._evaluate_geometry_snapshot(snapshot)
        scroll_state = page.evaluate(
            """() => {
              const shell = document.querySelector(".shell");
              const messages = document.getElementById("messages");
              return {
                demoHidden:
                  getComputedStyle(document.querySelector(".demo-strip")).display === "none",
                messagesOverflow: messages.scrollHeight > messages.clientHeight,
                shellScrollTop: shell.scrollTop,
              };
            }"""
        )

        assert scroll_state["demoHidden"] is True
        assert scroll_state["messagesOverflow"] is True
        assert scroll_state["shellScrollTop"] == 0
        assert report["status"] == "passed", report

    _with_s12g_real_chat_page(viewport, assert_long_content_geometry)


def test_s12g_task8_real_chat_wide_presentation_return_uses_second_toggle_click() -> (
    None
):
    module = _load_s12g_browser_acceptance_module()

    def assert_toggle_round_trip(page: object) -> None:
        page.set_default_timeout(1_000)
        page.evaluate(
            """() => {
              window.__s12gToggleClickCount = 0;
              document.getElementById("demo-toggle").addEventListener("click", () => {
                window.__s12gToggleClickCount += 1;
              });
            }"""
        )

        report = module._exercise_presentation_states(page)

        assert report["status"] == "passed", report
        assert page.evaluate("() => window.__s12gToggleClickCount") == 2
        assert (
            page.evaluate(
                "() => document.querySelector('.shell')?.dataset.presentationState"
            )
            == "conversation"
        )

    _with_s12g_real_chat_page((768, 1024), assert_toggle_round_trip)


@pytest.mark.parametrize("failure_stage", ("navigation", "shell", "demo_grid"))
def test_s12g_task8_first_shared_bootstrap_failure_aborts_viewport_matrix(
    failure_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    attempted: list[tuple[int, int]] = []
    closed: list[tuple[int, int]] = []
    presentation_calls: list[tuple[int, int]] = []
    captures: list[str] = []
    sensitive_message = f"private-{failure_stage}-failure-must-not-persist"
    first_viewport = (320, 568)

    class FakePage:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def goto(self, *_args: object, **_kwargs: object) -> None:
            if self.viewport == first_viewport and failure_stage == "navigation":
                raise RuntimeError(sensitive_message)

        def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
            if self.viewport == first_viewport and failure_stage == "shell":
                raise RuntimeError(sensitive_message)

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            if self.viewport == first_viewport and failure_stage == "demo_grid":
                raise RuntimeError(sensitive_message)

    class FakeContext:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def new_page(self) -> FakePage:
            return FakePage(self.viewport)

        def close(self) -> None:
            closed.append(self.viewport)

    class FakeBrowser:
        def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
            candidate = (viewport["width"], viewport["height"])
            attempted.append(candidate)
            return FakeContext(candidate)

    def exercise(page: FakePage) -> dict[str, object]:
        presentation_calls.append(page.viewport)
        return {"status": "passed", "defect_codes": [], "states": []}

    def capture(_page: FakePage | None, path: Path) -> dict[str, object]:
        captures.append(path.name)
        return {"screenshot_saved": True, "reason": "MASKED_CHAT_ROOTS"}

    monkeypatch.setattr(
        module,
        "VIEWPORT_MATRIX",
        (first_viewport, (360, 640), (390, 844)),
    )
    monkeypatch.setattr(module, "LONG_CONTENT_VIEWPORTS", set())
    monkeypatch.setattr(module, "SSE_VIEWPORT", (999, 999))
    monkeypatch.setattr(module, "_attach_sanitized_console", lambda *_args: None)
    monkeypatch.setattr(module, "_exercise_presentation_states", exercise)
    monkeypatch.setattr(module, "_capture_failure", capture)

    report = module._run_production(
        FakeBrowser(),
        "https://s12g.test/chat",
        "safe query",
        tmp_path,
        [],
    )

    assert attempted == [first_viewport]
    assert closed == attempted
    assert presentation_calls == []
    assert captures == ["viewport-320x568-failure.png"]
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["VIEWPORT_RUNTIME_FAILURE"]
    assert report["real_sse"] is None
    assert len(report["viewports"]) == 1
    assert report["viewports"][0]["status"] == "failed"
    assert report["viewports"][0]["failure"] == {
        "code": "VIEWPORT_RUNTIME_FAILURE",
        "exception_type": "RuntimeError",
    }
    assert sensitive_message not in json.dumps(report)


def test_s12g_task8_production_continues_after_viewport_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    visited: list[tuple[int, int]] = []
    closed: list[tuple[int, int]] = []
    captures: list[str] = []
    sensitive_message = "private-response-payload-must-not-persist"
    screenshot_result = {
        "screenshot_saved": True,
        "reason": "MASKED_CHAT_ROOTS",
    }

    class FakePage:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def goto(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            return None

    class FakeContext:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def new_page(self) -> FakePage:
            return FakePage(self.viewport)

        def close(self) -> None:
            closed.append(self.viewport)

    class FakeBrowser:
        def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
            return FakeContext((viewport["width"], viewport["height"]))

    def exercise(page: FakePage) -> dict[str, object]:
        visited.append(page.viewport)
        if page.viewport == (320, 568):
            raise RuntimeError(sensitive_message)
        return {"status": "passed", "defect_codes": [], "states": []}

    def capture(_page: FakePage | None, path: Path) -> dict[str, object]:
        captures.append(path.name)
        return screenshot_result

    monkeypatch.setattr(module, "VIEWPORT_MATRIX", ((320, 568), (360, 640)))
    monkeypatch.setattr(module, "LONG_CONTENT_VIEWPORTS", set())
    monkeypatch.setattr(module, "SSE_VIEWPORT", (999, 999))
    monkeypatch.setattr(module, "_attach_sanitized_console", lambda *_args: None)
    monkeypatch.setattr(module, "_exercise_presentation_states", exercise)
    monkeypatch.setattr(module, "_capture_failure", capture)

    report = module._run_production(
        FakeBrowser(),
        "https://s12g.test/chat",
        "safe query",
        tmp_path,
        [],
    )

    assert visited == [(320, 568), (360, 640)]
    assert closed == visited
    assert captures == ["viewport-320x568-failure.png"]
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["VIEWPORT_RUNTIME_FAILURE"]
    assert [record["status"] for record in report["viewports"]] == [
        "failed",
        "passed",
    ]
    assert report["viewports"][0]["failure"] == {
        "code": "VIEWPORT_RUNTIME_FAILURE",
        "exception_type": "RuntimeError",
    }
    assert report["viewports"][0]["screenshot"] == screenshot_result
    assert sensitive_message not in json.dumps(report)


@pytest.mark.parametrize(
    "failure_stage",
    (
        "new_context",
        "new_page",
        "attach",
        "run",
        "geometry",
        "sse",
        "close",
        "run_and_close",
    ),
)
def test_s12g_task8_production_isolates_each_viewport_lifecycle_failure(
    failure_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    attempted: list[tuple[int, int]] = []
    visited: list[tuple[int, int]] = []
    closed: list[tuple[int, int]] = []
    captures: list[tuple[tuple[int, int] | None, str]] = []
    sensitive_message = f"sensitive-{failure_stage}-failure"

    class FakePage:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def goto(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            return None

    class FakeContext:
        def __init__(self, viewport: tuple[int, int], index: int) -> None:
            self.viewport = viewport
            self.index = index

        def new_page(self) -> FakePage:
            if self.index == 0 and failure_stage == "new_page":
                raise RuntimeError(sensitive_message)
            return FakePage(self.viewport)

        def close(self) -> None:
            closed.append(self.viewport)
            if self.index == 0 and failure_stage in {"close", "run_and_close"}:
                raise OSError(sensitive_message)

    class FakeBrowser:
        def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
            candidate = (viewport["width"], viewport["height"])
            index = len(attempted)
            attempted.append(candidate)
            if index == 0 and failure_stage == "new_context":
                raise OSError(sensitive_message)
            return FakeContext(candidate, index)

    def attach(page: FakePage, *_args: object) -> None:
        if page.viewport == (320, 568) and failure_stage == "attach":
            raise ValueError(sensitive_message)

    def exercise(page: FakePage) -> dict[str, object]:
        visited.append(page.viewport)
        if page.viewport == (320, 568) and failure_stage in {"run", "run_and_close"}:
            raise RuntimeError(sensitive_message)
        return {"status": "passed", "defect_codes": [], "states": []}

    def exercise_geometry(page: FakePage) -> dict[str, object]:
        if page.viewport == (320, 568) and failure_stage == "geometry":
            raise RuntimeError(sensitive_message)
        return {"status": "passed", "defect_codes": []}

    def run_sse(page: FakePage, _query: str) -> dict[str, object]:
        if page.viewport == (320, 568) and failure_stage == "sse":
            raise RuntimeError(sensitive_message)
        return {"status": "passed", "defect_codes": []}

    def capture(page: FakePage | None, path: Path) -> dict[str, object]:
        captures.append((None if page is None else page.viewport, path.name))
        return {
            "screenshot_saved": page is not None,
            "reason": "MASKED_CHAT_ROOTS" if page is not None else "PAGE_CLOSED",
        }

    monkeypatch.setattr(module, "VIEWPORT_MATRIX", ((320, 568), (360, 640)))
    monkeypatch.setattr(module, "LONG_CONTENT_VIEWPORTS", set())
    monkeypatch.setattr(
        module,
        "SSE_VIEWPORT",
        (320, 568) if failure_stage in {"geometry", "sse"} else (999, 999),
    )
    monkeypatch.setattr(module, "_attach_sanitized_console", attach)
    monkeypatch.setattr(module, "_exercise_presentation_states", exercise)
    monkeypatch.setattr(module, "_exercise_keyboard_and_rotation", exercise_geometry)
    monkeypatch.setattr(module, "_run_real_sse", run_sse)
    monkeypatch.setattr(module, "_capture_failure", capture)

    report = module._run_production(
        FakeBrowser(),
        "https://s12g.test/chat",
        "safe query",
        tmp_path,
        [],
    )

    assert attempted == [(320, 568), (360, 640)]
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["VIEWPORT_RUNTIME_FAILURE"]
    assert [record["status"] for record in report["viewports"]] == [
        "failed",
        "passed",
    ]
    assert len(captures) == 1
    assert captures[0][1] == "viewport-320x568-failure.png"
    first = report["viewports"][0]
    assert first["screenshot"]["screenshot_saved"] is (
        failure_stage != "new_context" and failure_stage != "new_page"
    )
    if failure_stage in {"close", "run_and_close"}:
        assert first["cleanup_failure"] == {
            "code": "VIEWPORT_CLEANUP_FAILURE",
            "exception_type": "OSError",
        }
    if failure_stage == "run_and_close":
        assert first["failure"] == {
            "code": "VIEWPORT_RUNTIME_FAILURE",
            "exception_type": "RuntimeError",
        }
    assert sensitive_message not in json.dumps(report)


def test_s12g_task8_production_healthy_path_visits_complete_viewport_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    attempted: list[tuple[int, int]] = []
    closed: list[tuple[int, int]] = []
    presentation_calls: list[tuple[int, int]] = []
    long_content_calls: list[tuple[int, int]] = []
    geometry_calls: list[tuple[int, int]] = []
    sse_calls: list[tuple[tuple[int, int], str]] = []
    captures: list[str] = []
    sse_report = {"status": "passed", "defect_codes": []}

    class FakePage:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def goto(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            return None

    class FakeContext:
        def __init__(self, viewport: tuple[int, int]) -> None:
            self.viewport = viewport

        def new_page(self) -> FakePage:
            return FakePage(self.viewport)

        def close(self) -> None:
            closed.append(self.viewport)

    class FakeBrowser:
        def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
            candidate = (viewport["width"], viewport["height"])
            attempted.append(candidate)
            return FakeContext(candidate)

    def exercise_presentation(page: FakePage) -> dict[str, object]:
        presentation_calls.append(page.viewport)
        return {"status": "passed", "defect_codes": [], "states": []}

    def exercise_long_content(page: FakePage) -> dict[str, object]:
        long_content_calls.append(page.viewport)
        return {"status": "passed", "defect_codes": []}

    def exercise_geometry(page: FakePage) -> dict[str, object]:
        geometry_calls.append(page.viewport)
        return {"status": "passed", "defect_codes": []}

    def run_sse(page: FakePage, query: str) -> dict[str, object]:
        sse_calls.append((page.viewport, query))
        return sse_report

    def capture(_page: FakePage | None, path: Path) -> dict[str, object]:
        captures.append(path.name)
        return {"screenshot_saved": True, "reason": "MASKED_CHAT_ROOTS"}

    monkeypatch.setattr(module, "_attach_sanitized_console", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "_exercise_presentation_states",
        exercise_presentation,
    )
    monkeypatch.setattr(module, "_inject_and_probe_long_content", exercise_long_content)
    monkeypatch.setattr(module, "_exercise_keyboard_and_rotation", exercise_geometry)
    monkeypatch.setattr(module, "_run_real_sse", run_sse)
    monkeypatch.setattr(module, "_capture_failure", capture)

    report = module._run_production(
        FakeBrowser(),
        "https://s12g.test/chat",
        "safe query",
        tmp_path,
        [],
    )

    expected_viewports = list(_S12G_VIEWPORT_MATRIX_ORACLE)
    assert attempted == expected_viewports
    assert closed == expected_viewports
    assert presentation_calls == expected_viewports
    assert long_content_calls == [(320, 568), (667, 375)]
    assert geometry_calls == [(390, 844)]
    assert sse_calls == [((390, 844), "safe query")]
    assert captures == []
    assert report["status"] == "passed"
    assert report["defect_codes"] == []
    assert report["real_sse"] == sse_report
    assert [
        (record["viewport"]["width"], record["viewport"]["height"])
        for record in report["viewports"]
    ] == expected_viewports
    assert all(record["status"] == "passed" for record in report["viewports"])


def _s12g_valid_chat_response(answer_text: str = "a") -> dict[str, object]:
    citation_id = "official-source-0123456789abcdef"
    return {
        "query": "public query",
        "query_type": "canonical_v2:A:answer",
        "answer_text": answer_text,
        "citations": [
            {
                "type": "paper",
                "id": citation_id,
                "label": "Public source",
                "url": "https://example.edu/source",
            }
        ],
        "evidence": [],
        "clarification": {
            "prompt": "Choose a public option",
            "options": [
                {
                    "id": "option-1",
                    "domain": "paper",
                    "label": "Continue",
                    "hint": "Continue",
                }
            ],
            "default_id": "",
            "omitted": 0,
        },
        "structured_payload": {},
        "answer_style": "template",
        "citation_map": {"1": citation_id},
        "suggested_followups": ["Continue"],
    }


def _s12g_sse_event(name: str, data: dict[str, object]) -> str:
    return (
        f"event: {name}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _s12g_valid_sse_payloads() -> list[tuple[str, dict[str, object]]]:
    return [
        ("stage", {"name": "planning"}),
        (
            "plan_done",
            {
                "lanes": ["exact"],
                "domains": ["paper"],
                "views": ["public query"],
            },
        ),
        ("stage", {"name": "retrieval"}),
        (
            "retrieval_done",
            {"lanes": [{"lane": "exact", "status": "succeeded", "candidates": 1}]},
        ),
        ("stage", {"name": "synthesis"}),
        ("answer_chunk", {"text": "a"}),
        ("answer", _s12g_valid_chat_response()),
        ("done", {}),
    ]


def _s12g_segmented_sse_stream(
    *,
    with_citations: bool = True,
    with_options: bool = True,
) -> tuple[str, tuple[str, ...]]:
    answer_chunks = (
        "## 流式公开回答\n\n"
        "- 第一项公开内容包含中文，并确保首个流式分段超过公开文本安全尾部缓冲长度。\n\n"
        "1. 第二项在后续分段到达前形成可观察的增量内容，并拆分英文 to",
        'ken 后继续增长。\n\n```python\nprint("公开")\n```\n',
    )
    answer = _s12g_valid_chat_response("".join(answer_chunks))
    if not with_citations:
        answer["citations"] = []
        answer["citation_map"] = {}
    if not with_options:
        answer["clarification"] = None
    payloads = _s12g_valid_sse_payloads()
    prefix = payloads[:5]
    segments = (
        "".join(_s12g_sse_event(*event) for event in prefix),
        _s12g_sse_event("answer_chunk", {"text": answer_chunks[0]}),
        _s12g_sse_event("answer_chunk", {"text": answer_chunks[1]}),
        _s12g_sse_event("answer", answer) + _s12g_sse_event("done", {}),
    )
    return "".join(segments), segments


def _s12g_install_dynamic_control_mutation(
    page: object,
    selector: str,
    mutation: str,
) -> None:
    if mutation == "baseline":
        return
    if mutation == "never-created":
        installed = page.evaluate(
            """(blockedSelector) => {
              const nativeAppend = Element.prototype.append;
              Element.prototype.append = function (...nodes) {
                const retained = nodes.filter(
                  (node) =>
                    !(node instanceof Element && node.matches(blockedSelector)),
                );
                return nativeAppend.apply(this, retained);
              };
              return true;
            }""",
            selector,
        )
        assert installed is True
        return
    declaration = {
        "hidden": "display: none !important;",
        "pointer-disabled": "pointer-events: none !important;",
        "43px": (
            "box-sizing: border-box !important; "
            "width: 43px !important; height: 43px !important; "
            "min-width: 0 !important; min-height: 0 !important; "
            "padding: 0 !important;"
        ),
    }[mutation]
    installed = page.evaluate(
        """({selector, declaration}) => {
          const style = document.createElement("style");
          style.dataset.s12gControlMutation = selector;
          style.textContent = `${selector} { ${declaration} }`;
          document.head.append(style);
          return true;
        }""",
        {"selector": selector, "declaration": declaration},
    )
    assert installed is True


@pytest.mark.parametrize(
    ("mutation_name", "expected_event", "expected_event_index"),
    (
        ("snapshot_id", "answer", 6),
        ("release_id", "answer", 6),
        ("source_authority", "answer", 6),
        ("trace.internal_stage", "answer", 6),
        ("row_key", "retrieval_done", 3),
    ),
)
def test_s12g_task8_raw_sse_schema_rejects_internal_or_unknown_fields(
    mutation_name: str,
    expected_event: str,
    expected_event_index: int,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    payloads = _s12g_valid_sse_payloads()

    if mutation_name == "snapshot_id":
        evidence = payloads[6][1]["evidence"]
        assert isinstance(evidence, list)
        evidence.append({"snapshot_id": "snapshot-secret"})
    elif mutation_name == "release_id":
        structured_payload = payloads[6][1]["structured_payload"]
        assert isinstance(structured_payload, dict)
        structured_payload["release_id"] = "release-secret"
    elif mutation_name == "source_authority":
        citations = payloads[6][1]["citations"]
        assert isinstance(citations, list) and isinstance(citations[0], dict)
        citations[0]["source_authority"] = "internal"
    elif mutation_name == "trace.internal_stage":
        structured_payload = payloads[6][1]["structured_payload"]
        assert isinstance(structured_payload, dict)
        structured_payload["trace"] = {"internal_stage": "private"}
    else:
        lanes = payloads[3][1]["lanes"]
        assert isinstance(lanes, list) and isinstance(lanes[0], dict)
        lanes[0]["row_key"] = "private-row"

    raw_body = "".join(_s12g_sse_event(*event) for event in payloads).encode()
    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))
    persisted = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "failed"
    assert report["checks"]["valid_event_shapes"] is False
    assert len(report["schema_violations"]) == 1
    violation = report["schema_violations"][0]
    assert set(violation) == {
        "event_index",
        "event",
        "category",
        "field_path_sha256",
    }
    assert violation["event_index"] == expected_event_index
    assert violation["event"] == expected_event
    assert violation["category"] == "unknown_field"
    assert len(violation["field_path_sha256"]) == 64
    for fragment in mutation_name.split("."):
        assert fragment not in persisted


@pytest.mark.parametrize(
    ("clarification_case", "expected_status", "expects_option"),
    (
        ("nonempty", "passed", True),
        ("null", "passed", False),
        ("empty", "passed", False),
        ("schema-invalid", "failed", False),
        ("duplicate-answer", "failed", False),
    ),
)
def test_s12g_task8_raw_sse_derives_option_only_from_unique_valid_answer(
    clarification_case: str,
    expected_status: str,
    expects_option: bool,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    payloads = _s12g_valid_sse_payloads()
    answer = payloads[6][1]
    clarification = answer["clarification"]
    assert isinstance(clarification, dict)

    if clarification_case == "null":
        answer["clarification"] = None
    elif clarification_case == "empty":
        clarification["options"] = []
    elif clarification_case == "schema-invalid":
        options = clarification["options"]
        assert isinstance(options, list) and isinstance(options[0], dict)
        options[0]["private_field"] = "must-not-persist"
    elif clarification_case == "duplicate-answer":
        payloads.insert(-1, ("answer", _s12g_valid_chat_response()))

    raw_body = "".join(_s12g_sse_event(*event) for event in payloads).encode()
    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))
    terminal_controls = report["control_expectations"]["terminal"]
    persisted = json.dumps(report, ensure_ascii=False)

    assert report["status"] == expected_status
    assert (".option-button" in terminal_controls) is expects_option
    assert "option-1" not in persisted
    assert "public query" not in persisted
    if clarification_case == "schema-invalid":
        assert report["checks"]["valid_event_shapes"] is False
        assert [violation["category"] for violation in report["schema_violations"]] == [
            "unknown_field"
        ]
        assert "private_field" not in persisted
        assert "must-not-persist" not in persisted


def test_s12g_task8_raw_sse_parser_validates_order_and_chunk_reconstruction() -> None:
    module = _load_s12g_browser_acceptance_module()
    answer_data = json.dumps(
        _s12g_valid_chat_response("第一段第二段"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw_body = (
        'event: stage\r\ndata: {"name":"planning"}\r\n\r\n'
        'event: answer_chunk\r\ndata: {"text":\r\ndata: "第一段"}\r\n\r\n'
        'event: answer_chunk\r\ndata: {"text":"第二段"}\r\n\r\n'
        f"event: answer\r\ndata: {answer_data}\r\n\r\n"
        "event: done\r\ndata: {}\r\n\r\n"
    ).encode()

    events = module._parse_sse_body(raw_body)
    report = module._evaluate_sse_events(events)

    assert [event["name"] for event in events] == [
        "stage",
        "answer_chunk",
        "answer_chunk",
        "answer",
        "done",
    ]
    assert report["status"] == "passed"
    assert report["event_count"] == 5
    assert report["event_counts"] == {
        "answer": 1,
        "answer_chunk": 2,
        "done": 1,
        "stage": 1,
    }
    assert report["indexes"] == {
        "answer_chunks": [1, 2],
        "answer": 3,
        "done": 4,
        "errors": [],
    }
    assert all(report["checks"].values())
    assert len(report["event_order_sha256"]) == 64
    assert len(report["chunk_text_sha256"]) == 64
    assert report["chunk_text_sha256"] == report["answer_text_sha256"]
    assert report["event_marker_latches"] == []
    assert "第一段" not in json.dumps(report, ensure_ascii=False)


def test_s12g_task8_raw_sse_allows_harmless_comments_and_wire_metadata() -> None:
    module = _load_s12g_browser_acceptance_module()
    answer_data = json.dumps(
        _s12g_valid_chat_response(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw_body = (
        ": public heartbeat\n\n"
        "event: answer\n"
        ": public rendering metadata\n"
        "id: public-event-1\n"
        "retry: 1000\n"
        "x-correlation: public-heartbeat-42\n"
        f"data: {answer_data}\n\n" + _s12g_sse_event("done", {})
    ).encode()

    events = module._parse_sse_body(raw_body)
    report = module._evaluate_sse_events(events)

    assert [event["name"] for event in events] == ["answer", "done"]
    assert report["status"] == "passed"
    assert report["event_marker_latches"] == []


@pytest.mark.parametrize(
    "discarded_line",
    (
        ": keepalive PROF-8000C9F994C3",
        "id: PROF-8000C9F994C3",
        "x-meta: PROF-8000C9F994C3",
        "x-PROF-8000C9F994C3: public",
    ),
    ids=("comment", "id", "unknown-value", "unknown-name"),
)
def test_s12g_task8_raw_sse_latches_markers_in_discarded_wire_material(
    discarded_line: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"
    answer_data = json.dumps(
        _s12g_valid_chat_response(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw_body = (
        f"event: answer\n{discarded_line}\ndata: {answer_data}\n\n"
        + _s12g_sse_event("done", {})
    ).encode()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))
    persisted = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "failed"
    assert report["checks"]["no_raw_event_markers"] is False
    assert report["event_marker_latches"] == [
        {
            "marker_kind": "professor_internal_id",
            "event_index": 0,
            "sha256": report["event_marker_latches"][0]["sha256"],
        }
    ]
    assert re.fullmatch(r"[0-9a-f]{64}", report["event_marker_latches"][0]["sha256"])
    assert marker not in persisted
    assert marker.lower() not in persisted.lower()


@pytest.mark.parametrize(
    ("discarded_line", "private_fragment"),
    (
        (
            ": answer_text private-comment-wire-value",
            "private-comment-wire-value",
        ),
        (
            "x-meta: snapshot_id private-snapshot-wire-value",
            "private-snapshot-wire-value",
        ),
        (
            "answer_text: private-unknown-wire-value",
            "private-unknown-wire-value",
        ),
    ),
    ids=("comment-schema-key", "unknown-value-internal-key", "unknown-name-schema-key"),
)
def test_s12g_task8_raw_sse_latches_structural_tokens_in_discarded_wire_material(
    discarded_line: str,
    private_fragment: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    answer_data = json.dumps(
        _s12g_valid_chat_response(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw_body = (
        f"event: answer\n{discarded_line}\ndata: {answer_data}\n\n"
        + _s12g_sse_event("done", {})
    ).encode()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))
    persisted = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "failed"
    assert report["checks"]["no_raw_event_markers"] is False
    assert report["event_marker_latches"] == [
        {
            "marker_kind": "sse_structure_field",
            "event_index": 0,
            "sha256": report["event_marker_latches"][0]["sha256"],
        }
    ]
    assert re.fullmatch(r"[0-9a-f]{64}", report["event_marker_latches"][0]["sha256"])
    assert private_fragment not in persisted


@pytest.mark.parametrize(
    ("raw_data", "private_fragments"),
    (
        (
            '{"text":"public","text":"private duplicate value"}',
            ("text", "private duplicate value"),
        ),
        (
            '{"text":"public","nested":{"label":"one","label":"private nested"}}',
            ("label", "private nested"),
        ),
    ),
    ids=("top-level", "nested"),
)
def test_s12g_task8_raw_sse_rejects_duplicate_json_keys_safely(
    raw_data: str,
    private_fragments: tuple[str, ...],
) -> None:
    module = _load_s12g_browser_acceptance_module()

    with pytest.raises(module.AcceptanceRuntimeError) as caught:
        module._parse_sse_body(f"event: answer_chunk\ndata: {raw_data}\n\n".encode())

    assert caught.value.code == "SSE_JSON_DUPLICATE_KEY"
    persisted = f"{caught.value.code} {caught.value.public_message}"
    assert all(fragment not in persisted for fragment in private_fragments)


@pytest.mark.parametrize(
    ("raw_body", "expected_status", "failed_check"),
    (
        (
            _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("done", {}),
            "passed",
            None,
        ),
        (
            _s12g_sse_event("answer", _s12g_valid_chat_response(""))
            + _s12g_sse_event("done", {}),
            "failed",
            "nonempty_answer",
        ),
        (
            _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("done", {}),
            "failed",
            "chunks_before_answer",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response("b"))
            + _s12g_sse_event("done", {}),
            "failed",
            "chunks_reconstruct_answer",
        ),
    ),
)
def test_s12g_task8_raw_sse_answer_chunks_are_optional_but_strict_when_present(
    raw_body: str,
    expected_status: str,
    failed_check: str | None,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body.encode()))

    assert report["status"] == expected_status
    if failed_check is None:
        assert "has_answer_chunk" not in report["checks"]
        assert report["indexes"]["answer_chunks"] == []
        assert report["checks"]["nonempty_answer"] is True
        assert report["checks"]["chunks_before_answer"] is True
        assert report["checks"]["chunks_reconstruct_answer"] is True
    else:
        assert report["checks"].get(failed_check) is False


@pytest.mark.parametrize(
    ("raw_body", "failed_check"),
    (
        (
            _s12g_sse_event("answer", _s12g_valid_chat_response(""))
            + _s12g_sse_event("done", {}),
            "nonempty_answer",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("done", {}),
            "unique_answer",
        ),
        (
            _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("done", {}),
            "chunks_before_answer",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("done", {})
            + _s12g_sse_event("answer", _s12g_valid_chat_response()),
            "answer_before_done",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("done", {})
            + _s12g_sse_event("stage", {"name": "planning"}),
            "done_is_terminal",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response("b"))
            + _s12g_sse_event("done", {}),
            "chunks_reconstruct_answer",
        ),
        (
            _s12g_sse_event("error", {"detail": "safe failure"}),
            "no_error_events",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("error", {"detail": "safe failure"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("done", {}),
            "no_error_events",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("stage", {"name": "planning"})
            + _s12g_sse_event("done", {}),
            "answer_is_penultimate",
        ),
        (
            _s12g_sse_event("answer_chunk", {"text": "a"})
            + _s12g_sse_event("answer", _s12g_valid_chat_response())
            + _s12g_sse_event("done", {})
            + _s12g_sse_event("done", {}),
            "unique_done",
        ),
    ),
)
def test_s12g_task8_raw_sse_mutations_fail_closed(
    raw_body: str,
    failed_check: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body.encode()))

    assert report["status"] == "failed"
    assert report["checks"][failed_check] is False


def test_s12g_task8_raw_sse_latches_markers_without_persisting_payload() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"
    answer_text = f"公开{marker}"
    raw_body = (
        _s12g_sse_event("answer_chunk", {"text": answer_text})
        + _s12g_sse_event("answer", _s12g_valid_chat_response(answer_text))
        + _s12g_sse_event("done", {})
    ).encode()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))

    assert report["status"] == "failed"
    assert report["checks"]["no_raw_event_markers"] is False
    assert [item["marker_kind"] for item in report["event_marker_latches"]] == [
        "professor_internal_id",
        "professor_internal_id",
    ]
    assert [item["event_index"] for item in report["event_marker_latches"]] == [0, 1]
    assert all(len(item["sha256"]) == 64 for item in report["event_marker_latches"])
    assert marker not in json.dumps(report, ensure_ascii=False)


def test_s12g_task8_raw_sse_event_names_are_allowlisted_and_never_persisted() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"
    raw_body = (
        f"event: {marker}\ndata: {{}}\n\n"
        + _s12g_sse_event("answer_chunk", {"text": "a"})
        + _s12g_sse_event("answer", _s12g_valid_chat_response())
        + _s12g_sse_event("done", {})
    ).encode()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))
    persisted = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "failed"
    assert report["checks"]["known_event_names"] is False
    assert report["checks"]["no_raw_event_markers"] is False
    assert report["event_counts"] == {
        "answer": 1,
        "answer_chunk": 1,
        "done": 1,
        "unknown": 1,
    }
    assert report["event_marker_latches"][0]["marker_kind"] == "professor_internal_id"
    assert marker not in persisted
    assert marker.lower() not in persisted.lower()


def test_s12g_task8_raw_sse_latches_unicode_escaped_nested_markers() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"
    answer_payload = _s12g_valid_chat_response()
    citations = answer_payload["citations"]
    assert isinstance(citations, list) and isinstance(citations[0], dict)
    citations[0]["label"] = marker
    answer_data = json.dumps(
        answer_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("PROF-8", "PROF-\\u0038", 1)
    raw_body = (
        _s12g_sse_event("answer_chunk", {"text": "a"})
        + f"event: answer\ndata: {answer_data}\n\n"
        + _s12g_sse_event("done", {})
    ).encode()

    report = module._evaluate_sse_events(module._parse_sse_body(raw_body))

    assert report["status"] == "failed"
    assert report["checks"]["no_raw_event_markers"] is False
    assert report["event_marker_latches"][0]["marker_kind"] == "professor_internal_id"
    assert report["event_marker_latches"][0]["event_index"] == 1
    assert marker not in json.dumps(report, ensure_ascii=False)


def test_s12g_task8_raw_sse_json_failure_uses_safe_error_code() -> None:
    module = _load_s12g_browser_acceptance_module()

    with pytest.raises(module.AcceptanceRuntimeError) as caught:
        module._parse_sse_body(b'event: answer_chunk\ndata: {"text":\n\n')

    assert caught.value.code == "SSE_JSON_DECODE_FAILED"
    assert "text" not in caught.value.public_message


def _s12g_valid_geometry_snapshot() -> dict[str, object]:
    return {
        "viewport": {
            "width": 390,
            "height": 844,
            "visual": {
                "offset_left": 12,
                "offset_top": 20,
                "width": 366,
                "height": 800,
            },
            "css_app_height": 800,
            "visual_viewport_short": False,
        },
        "document": {
            "client_width": 390,
            "scroll_width": 390,
            "client_height": 844,
            "scroll_height": 844,
            "scroll_x": 0,
            "scroll_y": 0,
        },
        "presentation_state": "conversation",
        "shell": {
            "left": 12,
            "top": 20,
            "right": 378,
            "bottom": 820,
            "width": 366,
            "height": 800,
        },
        "header": {
            "left": 12,
            "top": 20,
            "right": 378,
            "bottom": 80,
            "width": 366,
            "height": 60,
        },
        "messages": {
            "left": 12,
            "top": 80,
            "right": 378,
            "bottom": 750,
            "width": 366,
            "height": 670,
        },
        "composer": {
            "left": 12,
            "top": 750,
            "right": 378,
            "bottom": 820,
            "width": 366,
            "height": 70,
        },
        "targets": [],
    }


def test_s12g_task8_geometry_accepts_nonzero_visual_viewport_origin() -> None:
    module = _load_s12g_browser_acceptance_module()

    report = module._evaluate_geometry_snapshot(_s12g_valid_geometry_snapshot())

    assert report["status"] == "passed"
    assert report["defect_codes"] == []
    assert all(report["checks"].values())


def test_s12g_task8_geometry_rejects_visual_viewport_width_underfill() -> None:
    module = _load_s12g_browser_acceptance_module()
    snapshot = _s12g_valid_geometry_snapshot()
    for section_name in ("shell", "header", "messages", "composer"):
        section = snapshot[section_name]
        assert isinstance(section, dict)
        section.update({"left": 20, "right": 370, "width": 350})

    report = module._evaluate_geometry_snapshot(snapshot)

    assert report["status"] == "failed"
    assert report["checks"]["shell_matches_visual_viewport"] is False
    assert report["checks"]["core_within_visual_viewport"] is True
    assert "ROTATION_STALE_GEOMETRY" in report["defect_codes"]


@pytest.mark.parametrize(
    ("path", "value", "failed_check", "defect_code"),
    (
        (("document", "scroll_height"), 845, "document_size_fits", "DOCUMENT_OVERFLOW"),
        (("document", "scroll_x"), 1, "document_not_scrolled", "DOCUMENT_OVERFLOW"),
        (("document", "scroll_y"), 1, "document_not_scrolled", "DOCUMENT_OVERFLOW"),
        (
            ("shell", "left"),
            0,
            "core_within_visual_viewport",
            "ROTATION_STALE_GEOMETRY",
        ),
        (
            ("composer", "bottom"),
            821,
            "core_within_visual_viewport",
            "ROTATION_STALE_GEOMETRY",
        ),
    ),
)
def test_s12g_task8_geometry_mutations_fail_both_axes_and_visual_bounds(
    path: tuple[str, str],
    value: int,
    failed_check: str,
    defect_code: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    snapshot = _s12g_valid_geometry_snapshot()
    section = snapshot[path[0]]
    assert isinstance(section, dict)
    section[path[1]] = value

    report = module._evaluate_geometry_snapshot(snapshot)

    assert report["status"] == "failed"
    assert report["checks"][failed_check] is False
    assert defect_code in report["defect_codes"]


def test_s12g_task8_target_samples_keep_independent_axis_minima() -> None:
    module = _load_s12g_browser_acceptance_module()
    selectors = ("#chat-input", "#chat-submit", ".demo-chip")
    samples = [
        {"selector": "#chat-input", "width": 300, "height": 48},
        {"selector": "#chat-submit", "width": 60, "height": 52},
        {"selector": "#chat-submit", "width": 72, "height": 40},
    ]

    summary = module._summarize_target_samples(samples, selectors)

    assert summary == {
        "#chat-input": {
            "seen": True,
            "sample_count": 1,
            "min_width": 300,
            "min_height": 48,
            "ever_below_44": False,
        },
        "#chat-submit": {
            "seen": True,
            "sample_count": 2,
            "min_width": 60,
            "min_height": 40,
            "ever_below_44": True,
        },
        ".demo-chip": {
            "seen": False,
            "sample_count": 0,
            "min_width": None,
            "min_height": None,
            "ever_below_44": False,
        },
    }
    assert module._sampled_target_defects(summary) == {"TARGET_LT_44"}


def test_s12g_task8_required_dynamic_target_must_be_observed() -> None:
    module = _load_s12g_browser_acceptance_module()
    summary = module._summarize_target_samples(
        [{"selector": ".option-button", "width": 80, "height": 44}],
        (".process-summary summary", ".option-button"),
    )

    assert module._sampled_target_defects(
        summary,
        required_selectors=(".process-summary summary",),
    ) == {"TARGET_LT_44"}
    assert (
        module._sampled_target_defects(
            summary,
            required_selectors=(".option-button",),
        )
        == set()
    )


def test_s12g_task8_declares_required_actionable_controls_by_state() -> None:
    module = _load_s12g_browser_acceptance_module()

    assert module.REQUIRED_ACTIONABLE_CONTROLS == {
        "landing": ("#chat-input", "#chat-submit", ".demo-chip"),
        "conversation": ("#chat-input", "#chat-submit", "#demo-toggle"),
        "demo-expanded": (
            "#chat-input",
            "#chat-submit",
            "#demo-toggle",
            ".demo-chip",
        ),
    }


def test_s12g_task8_required_control_evaluator_fails_hidden_control() -> None:
    module = _load_s12g_browser_acceptance_module()
    observations = {
        "#chat-input": {"seen": True, "visible": True, "actionable": True},
        "#chat-submit": {"seen": True, "visible": True, "actionable": True},
        "#demo-toggle": {"seen": True, "visible": False, "actionable": False},
    }

    report = module._evaluate_actionable_controls("conversation", observations)

    assert report["status"] == "failed"
    assert report["required_controls"] == list(
        module.REQUIRED_ACTIONABLE_CONTROLS["conversation"]
    )
    assert report["controls"]["#demo-toggle"]["actionable"] is False
    assert report["defect_codes"] == ["REQUIRED_CONTROL_NOT_ACTIONABLE"]


def test_s12g_task8_actionability_requires_every_matching_instance() -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakeCandidate:
        def __init__(self, *, click_fails: bool = False) -> None:
            self.click_fails = click_fails
            self.trial_clicks = 0

        def is_visible(self) -> bool:
            return True

        def bounding_box(self) -> dict[str, float]:
            return {"width": 44, "height": 44}

        def click(self, *, trial: bool, timeout: int) -> None:
            assert trial is True
            assert timeout == 1_000
            self.trial_clicks += 1
            if self.click_fails:
                raise RuntimeError("covered")

    class FakeLocator:
        def __init__(self, candidates: list[FakeCandidate]) -> None:
            self.candidates = candidates

        def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> FakeCandidate:
            return self.candidates[index]

    failing_candidate = FakeCandidate(click_fails=True)

    class FakePage:
        def __init__(self) -> None:
            self.controls = {
                "#chat-input": [FakeCandidate()],
                "#chat-submit": [FakeCandidate()],
                ".demo-chip": [FakeCandidate(), failing_candidate],
            }

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self.controls[selector])

    observations = module._actionable_control_observations(FakePage(), "landing")
    report = module._evaluate_actionable_controls("landing", observations)

    assert failing_candidate.trial_clicks == 1
    assert observations[".demo-chip"] == {
        "seen": True,
        "visible": True,
        "actionable": False,
    }
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["REQUIRED_CONTROL_NOT_ACTIONABLE"]


def test_s12g_task8_actionability_rejects_visible_control_below_target_size() -> None:
    module = _load_s12g_browser_acceptance_module()
    selector = ".process-summary summary"

    class FakeCandidate:
        def is_visible(self) -> bool:
            return True

        def bounding_box(self) -> dict[str, float]:
            return {"width": 43.5, "height": 44}

        def click(self, *, trial: bool, timeout: int) -> None:
            assert trial is True
            assert timeout == 1_000

    class FakeLocator:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> FakeCandidate:
            assert index == 0
            return FakeCandidate()

    class FakePage:
        def locator(self, candidate_selector: str) -> FakeLocator:
            assert candidate_selector == selector
            return FakeLocator()

    required = (selector,)
    observations = module._actionable_control_observations(
        FakePage(),
        "conversation",
        required_controls=required,
    )
    report = module._evaluate_actionable_controls(
        "conversation",
        observations,
        required_controls=required,
    )

    assert observations[selector]["visible"] is True
    assert observations[selector]["actionable"] is False
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["REQUIRED_CONTROL_NOT_ACTIONABLE"]


@pytest.mark.parametrize(
    ("summary_style", "expected_status"),
    (
        ("", "passed"),
        ("display: none", "failed"),
        ("pointer-events: none", "failed"),
    ),
)
def test_s12g_task8_real_terminal_summary_is_required_and_actionable(
    summary_style: str,
    expected_status: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_terminal_summary(page: object) -> None:
        page.evaluate(
            """(summaryStyle) => {
              setPresentationState("conversation");
              document.getElementById("s12g-terminal-process")?.remove();
              const process = document.createElement("div");
              process.id = "s12g-terminal-process";
              process.className = "process process-finished";
              const details = document.createElement("details");
              details.className = "process-summary";
              const summary = document.createElement("summary");
              summary.textContent = "查看检索过程";
              summary.style.cssText = summaryStyle;
              details.append(summary);
              process.append(details);
              document.getElementById("messages").append(process);
              notifyContentUpdate();
            }""",
            summary_style,
        )
        report = module._terminal_actionable_controls(page)

        assert report["status"] == expected_status
        assert report["required_controls"] == [
            "#chat-input",
            "#chat-submit",
            "#demo-toggle",
            ".process-summary summary",
        ]
        assert report["controls"][".process-summary summary"]["seen"] is True
        if expected_status == "passed":
            assert report["defect_codes"] == []
        else:
            assert report["defect_codes"] == ["REQUIRED_CONTROL_NOT_ACTIONABLE"]

    _with_s12g_real_chat_page((390, 844), assert_terminal_summary)


def test_s12g_task8_detached_oracle_latches_transient_maximum_drift() -> None:
    module = _load_s12g_browser_acceptance_module()
    baseline = {"scroll_top": 200, "anchor_top": 80}
    samples = [
        {"scroll_top": 224, "anchor_top": 104},
        {"scroll_top": 200, "anchor_top": 80},
    ]

    report = module._evaluate_detached_samples(baseline, samples)

    assert report["status"] == "failed"
    assert report["defect_codes"] == ["DETACHED_SCROLL_DRIFT"]
    assert report["sample_count"] == 2
    assert report["max_scroll_delta"] == 24
    assert report["max_scroll_delta_index"] == 0
    assert report["max_anchor_delta"] == 24
    assert report["max_anchor_delta_index"] == 0
    assert report["terminal_scroll_delta"] == 0
    assert report["terminal_anchor_delta"] == 0


def test_s12g_task8_stream_probe_latches_first_frame_drift_before_recovery() -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_mutation_frames_observed(page: object) -> None:
        page.evaluate("() => setPresentationState('conversation')")
        module._inject_stream_history_and_probe(page, 0)
        module._enable_stream_detachment(page)
        page.evaluate(
            """() => {
              const answer = document.createElement("div");
              answer.className = "answer";
              answer.textContent = "streamed public answer";
              document.getElementById("messages").append(answer);
            }"""
        )
        page.evaluate(
            """() => new Promise((resolve) => {
              requestAnimationFrame(() => requestAnimationFrame(resolve));
            })"""
        )

        probe = module._stream_probe_result(page)
        assert isinstance(probe, dict)
        samples = probe["detached_samples"]
        triggers = [sample["trigger"] for sample in samples]
        expected_triggers = (
            "mutation_immediate",
            "mutation_first_frame",
            "mutation_second_frame",
        )
        trigger_indexes = []
        search_from = 0
        for trigger in expected_triggers:
            matching_indexes = [
                index
                for index in range(search_from, len(triggers))
                if triggers[index] == trigger
            ]
            assert matching_indexes, probe
            trigger_indexes.append(matching_indexes[0])
            search_from = matching_indexes[0] + 1
        sample_indexes = [samples[index]["sample_index"] for index in trigger_indexes]
        assert sample_indexes == sorted(sample_indexes)
        assert all(samples[index]["answer_length"] > 0 for index in trigger_indexes)

    _with_s12g_real_chat_page((390, 844), assert_mutation_frames_observed)

    report = module._evaluate_detached_samples(
        {"scroll_top": 200, "anchor_top": 80},
        [
            {
                "trigger": "mutation_immediate",
                "scroll_top": 200,
                "anchor_top": 80,
            },
            {
                "trigger": "mutation_first_frame",
                "scroll_top": 224,
                "anchor_top": 104,
            },
            {
                "trigger": "mutation_second_frame",
                "scroll_top": 200,
                "anchor_top": 80,
            },
        ],
    )

    assert report["status"] == "failed"
    assert report["max_scroll_delta_index"] == 1
    assert report["terminal_scroll_delta"] == 0


def test_s12g_task8_production_stream_drops_self_proving_length_change_check() -> None:
    module = _load_s12g_browser_acceptance_module()
    run_code = module._run_real_sse_round.__code__

    assert "all_length_changes_recorded" not in run_code.co_varnames
    assert "all_answer_length_changes_recorded" not in run_code.co_consts


def test_s12g_task8_collect_oracle_reuses_one_geometry_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    page = object()
    supplied_snapshot = _s12g_valid_geometry_snapshot()
    collected_snapshot = _s12g_valid_geometry_snapshot()
    browser_geometry_calls = []

    def fake_browser_geometry(page_arg: object, selectors: tuple[str, ...]):
        browser_geometry_calls.append((page_arg, selectors))
        return collected_snapshot

    monkeypatch.setattr(module, "_browser_geometry", fake_browser_geometry)

    supplied_report = module._collect_oracle(
        page,
        geometry_snapshot=supplied_snapshot,
    )
    collected_report = module._collect_oracle(page)

    assert browser_geometry_calls == [(page, ())]
    assert supplied_report["geometry"] is supplied_snapshot
    assert collected_report["geometry"] is collected_snapshot


def test_s12g_task8_collect_oracle_rejects_terminal_only_detached_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    monkeypatch.setattr(
        module,
        "_browser_geometry",
        lambda _page, _selectors: {"targets": []},
    )
    monkeypatch.setattr(
        module,
        "_evaluate_geometry_snapshot",
        lambda _snapshot: {"defect_codes": [], "checks": {}},
    )
    monkeypatch.setattr(
        module,
        "_summarize_target_samples",
        lambda _samples, _selectors: {},
    )
    monkeypatch.setattr(module, "_sampled_target_defects", lambda _summary: set())

    report = module._collect_oracle(
        object(),
        detached_probe={
            "before_scroll_top": 200,
            "before_anchor_top": 80,
            "after_scroll_top": 200,
            "after_anchor_top": 80,
        },
    )

    assert report["defect_codes"] == ["DETACHED_SCROLL_DRIFT"]
    assert report["detached_scroll"]["status"] == "failed"
    assert report["detached_scroll"]["checks"]["valid_sample_shape"] is False
    assert report["detached_scroll"]["sample_count"] == 0


def _s12g_rotation_expected_fingerprint() -> dict[str, object]:
    return {"length": 12, "sha256": "a" * 64}


def _s12g_rotation_phases() -> list[dict[str, object]]:
    phases = []
    for index, (width, height) in enumerate(
        ((390, 844), (390, 500), (390, 844), (844, 390), (390, 844))
    ):
        phases.append(
            {
                "phase_index": index,
                "viewport": {"width": width, "height": height},
                "geometry_status": "passed",
                "presentation_state": "conversation",
                "input_value_fingerprint": _s12g_rotation_expected_fingerprint(),
                "input_focused": True,
                "scroll_intent": "detached",
                "sentinel_present": True,
                "shell": {"width": width, "height": height},
            }
        )
    return phases


def test_s12g_task8_rotation_continuity_accepts_all_preserved_state() -> None:
    module = _load_s12g_browser_acceptance_module()

    report = module._evaluate_rotation_continuity(
        _s12g_rotation_phases(),
        _s12g_rotation_expected_fingerprint(),
    )

    assert report["status"] == "passed"
    assert report["defect_codes"] == []
    assert all(report["checks"].values())


def test_s12g_task8_rotation_accepts_bounded_landscape_shell_from_geometry_oracle() -> (
    None
):
    module = _load_s12g_browser_acceptance_module()
    phases = _s12g_rotation_phases()
    phases[3]["shell"] = {"width": 812, "height": 390}

    report = module._evaluate_rotation_continuity(
        phases,
        _s12g_rotation_expected_fingerprint(),
    )

    assert report["status"] == "passed"
    assert report["checks"]["geometry_valid"] is True


def test_s12g_task8_rotation_rejects_consistent_but_wrong_draft_fingerprint() -> None:
    module = _load_s12g_browser_acceptance_module()
    expected_fingerprint = {"length": 12, "sha256": "b" * 64}

    report = module._evaluate_rotation_continuity(
        _s12g_rotation_phases(),
        expected_fingerprint,
    )

    assert report["status"] == "failed"
    assert report["checks"]["input_value_preserved"] is False
    assert report["defect_codes"] == ["ROTATION_STALE_GEOMETRY"]


@pytest.mark.parametrize(
    ("field", "value", "failed_check"),
    (
        ("presentation_state", "landing", "conversation_state_preserved"),
        (
            "input_value_fingerprint",
            {"length": 7, "sha256": "b" * 64},
            "input_value_preserved",
        ),
        ("input_focused", False, "input_focus_preserved"),
        ("scroll_intent", "following", "detached_intent_preserved"),
        ("sentinel_present", False, "sentinel_preserved"),
    ),
)
def test_s12g_task8_rotation_continuity_mutations_fail_closed(
    field: str,
    value: object,
    failed_check: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    phases = _s12g_rotation_phases()
    phases[2][field] = value

    report = module._evaluate_rotation_continuity(
        phases,
        _s12g_rotation_expected_fingerprint(),
    )

    assert report["status"] == "failed"
    assert report["checks"][failed_check] is False
    assert report["defect_codes"] == ["ROTATION_STALE_GEOMETRY"]


def test_s12g_task8_dom_marker_latches_are_fail_closed_and_sanitized() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"
    latches = [
        {
            "marker_kind": "professor_internal_id",
            "mutation_index": 3,
            "sha256": "c" * 64,
            "raw_text": marker,
        }
    ]

    report = module._evaluate_dom_marker_latches(latches)

    assert report["status"] == "failed"
    assert report["checks"] == {
        "valid_latch_shape": True,
        "no_dom_mutation_markers": False,
    }
    assert report["latches"] == [
        {
            "marker_kind": "professor_internal_id",
            "mutation_index": 3,
            "sha256": "c" * 64,
        }
    ]
    assert marker not in json.dumps(report, ensure_ascii=False)


def test_s12g_task8_dom_marker_probe_scans_initial_and_removed_nodes() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "PROF-8000C9F994C3"

    def assert_removed_marker_latched(page: object) -> None:
        module._install_dom_marker_probe(page)
        marker_absent = page.evaluate(
            """(markerText) => {
              const marker = document.createElement("span");
              marker.textContent = markerText;
              const messages = document.getElementById("messages");
              messages.append(marker);
              marker.remove();
              return !messages.textContent.includes(markerText);
            }""",
            marker,
        )
        assert marker_absent is True

        latches = module._dom_marker_probe_result(page)
        assert isinstance(latches, list)
        professor_latches = [
            latch
            for latch in latches
            if latch.get("marker_kind") == "professor_internal_id"
        ]
        assert professor_latches
        assert all(
            isinstance(latch.get("mutation_index"), int)
            and not isinstance(latch.get("mutation_index"), bool)
            and latch["mutation_index"] >= 0
            and re.fullmatch(r"[0-9a-f]{64}", latch.get("sha256", ""))
            for latch in professor_latches
        )

        report = module._evaluate_dom_marker_latches(latches)
        assert report["status"] == "failed"
        assert report["checks"]["valid_latch_shape"] is True
        assert report["checks"]["no_dom_mutation_markers"] is False
        assert marker not in json.dumps(report, ensure_ascii=False)

    _with_s12g_real_chat_page((390, 844), assert_removed_marker_latched)


@pytest.mark.parametrize(
    ("mutation", "marker", "expected_kind"),
    (
        ("initial-attribute-value", "comp-A1b2C3d4E5f6", "company_internal_id"),
        ("current-attribute-value", "PROF-8000C9F994C3", "professor_internal_id"),
        ("attribute-name", "comp-A1B2C3D4E5F6", "company_internal_id"),
        ("removed-attribute-value", "PROF-8000C9F994C3", "professor_internal_id"),
    ),
)
def test_s12g_task8_dom_marker_probe_scans_all_message_subtree_attributes(
    mutation: str,
    marker: str,
    expected_kind: str,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_attribute_marker_latched(page: object) -> None:
        if mutation == "initial-attribute-value":
            created = page.evaluate(
                """(markerText) => {
                  const node = document.createElement("span");
                  node.setAttribute("data-public-reference", markerText);
                  document.getElementById("messages").append(node);
                  return true;
                }""",
                marker,
            )
            assert created is True

        module._install_dom_marker_probe(page)
        if mutation != "initial-attribute-value":
            mutated = page.evaluate(
                """({mutation, markerText}) => {
                  const node = document.createElement("span");
                  const messages = document.getElementById("messages");
                  messages.append(node);
                  if (mutation === "current-attribute-value") {
                    node.setAttribute("data-public-reference", markerText);
                  } else if (mutation === "attribute-name") {
                    node.setAttribute(`data-${markerText}`, "public");
                  } else if (mutation === "removed-attribute-value") {
                    node.setAttribute("data-public-reference", markerText);
                    node.remove();
                  }
                  return true;
                }""",
                {"mutation": mutation, "markerText": marker},
            )
            assert mutated is True

        latches = module._dom_marker_probe_result(page)
        assert isinstance(latches, list)
        assert expected_kind in {latch.get("marker_kind") for latch in latches}
        report = module._evaluate_dom_marker_latches(latches)
        assert report["status"] == "failed"
        assert report["checks"]["valid_latch_shape"] is True
        assert marker.lower() not in json.dumps(report, ensure_ascii=False).lower()

    _with_s12g_real_chat_page((390, 844), assert_attribute_marker_latched)


def test_s12g_task8_dom_marker_probe_latches_transient_attribute_name() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "comp-A1B2C3D4E5F6"

    def assert_transient_attribute_name_latched(page: object) -> None:
        module._install_dom_marker_probe(page)
        marker_absent = page.evaluate(
            """(markerText) => {
              const node = document.createElement("span");
              const messages = document.getElementById("messages");
              messages.append(node);
              const attributeName = `data-${markerText}`;
              node.setAttribute(attributeName, "public");
              node.removeAttribute(attributeName);
              return !node.hasAttribute(attributeName);
            }""",
            marker,
        )
        assert marker_absent is True

        latches = module._dom_marker_probe_result(page)
        assert isinstance(latches, list)
        assert "company_internal_id" in {latch.get("marker_kind") for latch in latches}
        report = module._evaluate_dom_marker_latches(latches)
        assert report["status"] == "failed"
        assert report["checks"]["valid_latch_shape"] is True
        assert report["checks"]["no_dom_mutation_markers"] is False
        assert marker.lower() not in json.dumps(report, ensure_ascii=False).lower()

    _with_s12g_real_chat_page(
        (390, 844),
        assert_transient_attribute_name_latched,
    )


def test_s12g_task8_dom_marker_probe_allows_safe_data_attributes() -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_safe_attributes_ignored(page: object) -> None:
        module._install_dom_marker_probe(page)
        mutated = page.evaluate(
            """() => {
              const node = document.createElement("span");
              node.setAttribute("data-presentation-state", "conversation");
              node.setAttribute("data-scroll-intent", "detached");
              node.setAttribute("data-s12g-history", "1");
              document.getElementById("messages").append(node);
              return true;
            }"""
        )
        assert mutated is True

        latches = module._dom_marker_probe_result(page)
        assert latches == []
        report = module._evaluate_dom_marker_latches(latches)
        assert report["status"] == "passed"

    _with_s12g_real_chat_page((390, 844), assert_safe_attributes_ignored)


def test_s12g_task8_visible_marker_scan_is_case_insensitive_for_company_ids() -> None:
    module = _load_s12g_browser_acceptance_module()
    marker = "comp-A1B2C3D4E5F6"

    def assert_visible_marker_detected(page: object) -> None:
        page.evaluate(
            """(markerText) => {
              const node = document.createElement("span");
              node.textContent = markerText;
              document.getElementById("messages").append(node);
            }""",
            marker,
        )

        assert module._scan_visible_internal_markers(page) == ["company_internal_id"]

    _with_s12g_real_chat_page((390, 844), assert_visible_marker_detected)


@pytest.mark.parametrize(
    "fixture",
    (
        "valid",
        "document-overflow",
        "small-target",
        "detached-scroll-drift",
        "rotation-stale-geometry",
    ),
)
def test_s12g_task8_self_test_fixtures_use_production_dom_shape(fixture: str) -> None:
    module = _load_s12g_browser_acceptance_module()

    html = module._self_test_html(fixture)

    for token in (
        'class="shell"',
        'class="header"',
        'id="messages"',
        'class="composer"',
        'id="chat-input"',
        'id="chat-submit"',
        'id="demo-toggle"',
        'class="demo-chip"',
        'id="demo-grid"',
        'data-presentation-state="conversation"',
        'data-scroll-intent="detached"',
    ):
        assert token in html


@pytest.mark.parametrize(
    ("width", "height"),
    ((390, 844), (720, 500), (721, 500), (844, 390)),
)
def test_s12g_task8_valid_self_test_fixture_matches_geometry_contract(
    width: int,
    height: int,
) -> None:
    from playwright.sync_api import sync_playwright

    module = _load_s12g_browser_acceptance_module()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        try:
            module._load_self_test_fixture(page, "valid")
            snapshot = module._browser_geometry(page, ())
            report = module._evaluate_geometry_snapshot(snapshot)

            expected_width = width if width <= 720 else min(980, width - 32)
            assert snapshot["shell"]["width"] == pytest.approx(expected_width, abs=1.5)
            assert report["status"] == "passed", report
        finally:
            context.close()
            browser.close()


def test_s12g_task8_self_test_fixture_uses_secure_context_for_sha256() -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakeRoute:
        def __init__(self) -> None:
            self.fulfillment: dict[str, object] | None = None

        def fulfill(self, **kwargs: object) -> None:
            self.fulfillment = kwargs

    class FakePage:
        def __init__(self, crypto_ready: bool) -> None:
            self.crypto_ready = crypto_ready
            self.handler: object | None = None
            self.navigation: tuple[str, str] | None = None
            self.route_result: FakeRoute | None = None
            self.evaluate_script = ""

        def route(self, _url: str, handler: object) -> None:
            self.handler = handler

        def goto(self, url: str, *, wait_until: str) -> None:
            assert callable(self.handler)
            self.navigation = (url, wait_until)
            self.route_result = FakeRoute()
            self.handler(self.route_result)

        def unroute(self, _url: str, handler: object) -> None:
            assert handler is self.handler
            self.handler = None

        def evaluate(self, script: str) -> bool:
            self.evaluate_script = script
            return self.crypto_ready

    page = FakePage(crypto_ready=True)
    module._load_self_test_fixture(page, "valid")

    assert page.navigation is not None
    assert page.navigation[0].startswith("https://")
    assert page.navigation[1] == "load"
    assert page.handler is None
    assert page.route_result is not None
    assert page.route_result.fulfillment == {
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "body": module._self_test_html("valid"),
    }
    assert "isSecureContext" in page.evaluate_script
    assert "crypto.subtle.digest" in page.evaluate_script

    with pytest.raises(module.AcceptanceRuntimeError) as error:
        module._load_self_test_fixture(FakePage(crypto_ready=False), "valid")
    assert error.value.code == "SELF_TEST_WEB_CRYPTO_UNAVAILABLE"


def test_s12g_task8_json_artifacts_use_atomic_same_directory_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    destination = tmp_path / "summary.json"
    replacements: list[tuple[Path, Path]] = []
    real_replace = module.os.replace

    def record_replace(source: str | Path, target: str | Path) -> None:
        source_path = Path(source)
        target_path = Path(target)
        replacements.append((source_path, target_path))
        assert source_path.parent == destination.parent
        assert source_path != destination
        real_replace(source_path, target_path)

    monkeypatch.setattr(module.os, "replace", record_replace)
    module._write_json(destination, {"status": "passed"})

    assert replacements == [(replacements[0][0], destination)]
    assert json.loads(destination.read_text(encoding="utf-8")) == {"status": "passed"}
    assert list(tmp_path.iterdir()) == [destination]


def test_s12g_task8_json_artifact_fsyncs_before_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    destination = tmp_path / "summary.json"
    calls: list[str] = []

    class FakeHandle:
        def __enter__(self) -> FakeHandle:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def write(self, text: str) -> int:
            calls.append("write")
            return len(text)

        def flush(self) -> None:
            calls.append("flush")

        def fileno(self) -> int:
            calls.append("fileno")
            return 37

    def fake_open(path: Path, mode: str, *, encoding: str) -> FakeHandle:
        assert path.parent == destination.parent
        assert mode == "x"
        assert encoding == "utf-8"
        return FakeHandle()

    def record_fsync(file_descriptor: int) -> None:
        assert file_descriptor == 37
        calls.append("fsync")

    def record_replace(source: str | Path, target: str | Path) -> None:
        assert Path(source).parent == destination.parent
        assert Path(target) == destination
        calls.append("replace")

    monkeypatch.setattr(module.Path, "open", fake_open)
    monkeypatch.setattr(module.os, "fsync", record_fsync)
    monkeypatch.setattr(module.os, "replace", record_replace)

    module._write_json(destination, {"status": "passed"})

    assert calls == ["write", "flush", "fileno", "fsync", "replace"]


def test_s12g_task8_json_artifact_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    destination = tmp_path / "summary.json"

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise OSError("controlled replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="controlled replace failure"):
        module._write_json(destination, {"status": "failed"})

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_s12g_task8_summary_is_written_last_as_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    writes: list[str] = []

    def record_write(path: Path, _payload: object) -> None:
        writes.append(path.name)

    monkeypatch.setattr(module, "_write_json", record_write)
    module._commit_artifacts(tmp_path, [{"type": "log"}], {"status": "passed"})
    assert writes == ["console.json", "summary.json"]

    writes.clear()

    def fail_console(path: Path, _payload: object) -> None:
        writes.append(path.name)
        if path.name == "console.json":
            raise OSError("controlled console failure")

    monkeypatch.setattr(module, "_write_json", fail_console)
    with pytest.raises(OSError, match="controlled console failure"):
        module._commit_artifacts(tmp_path, [], {"status": "failed"})
    assert writes == ["console.json"]


def test_s12g_task8_failure_screenshot_masks_sensitive_regions_once(
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakeLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def count(self) -> int:
            return 1

    class FakePage:
        def __init__(self) -> None:
            self.screenshots: list[dict[str, object]] = []

        def is_closed(self) -> bool:
            return False

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

        def screenshot(self, **kwargs: object) -> None:
            self.screenshots.append(kwargs)

    page = FakePage()
    result = module._capture_failure(page, tmp_path / "failure.png")

    assert result == {"screenshot_saved": True, "reason": "MASKED_CHAT_ROOTS"}
    assert len(page.screenshots) == 1
    assert {locator.selector for locator in page.screenshots[0]["mask"]} == {
        ".shell[data-presentation-state]",
        "#messages",
        "#chat-input",
        "#demo-grid",
    }
    assert "_capture_failure" not in module._run_real_sse.__code__.co_names
    assert "_capture_failure" not in module._run_real_sse_round.__code__.co_names


@pytest.mark.parametrize("invalid_count", (0, 2))
def test_s12g_task8_failure_screenshot_skips_when_mask_root_is_not_unique(
    invalid_count: int,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakeLocator:
        def __init__(self, count: int) -> None:
            self.match_count = count

        def count(self) -> int:
            return self.match_count

    class FakePage:
        screenshot_called = False

        def is_closed(self) -> bool:
            return False

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(invalid_count if selector == "#messages" else 1)

        def screenshot(self, **_kwargs: object) -> None:
            self.screenshot_called = True

    page = FakePage()
    result = module._capture_failure(page, tmp_path / "failure.png")

    assert result == {
        "screenshot_saved": False,
        "reason": "MASK_ROOTS_UNAVAILABLE",
    }
    assert page.screenshot_called is False


def test_s12g_task8_failure_screenshot_skips_closed_page(tmp_path: Path) -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakePage:
        locator_called = False

        def is_closed(self) -> bool:
            return True

        def locator(self, _selector: str) -> object:
            self.locator_called = True
            raise AssertionError("closed page must not be inspected")

    page = FakePage()
    result = module._capture_failure(page, tmp_path / "failure.png")

    assert result == {"screenshot_saved": False, "reason": "PAGE_CLOSED"}
    assert page.locator_called is False


def test_s12g_task8_failure_screenshot_sanitizes_capture_failure(
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    sensitive_message = "private-screenshot-error-must-not-persist"

    class FakeLocator:
        def count(self) -> int:
            return 1

    class FakePage:
        def is_closed(self) -> bool:
            return False

        def locator(self, _selector: str) -> FakeLocator:
            return FakeLocator()

        def screenshot(self, **_kwargs: object) -> None:
            raise RuntimeError(sensitive_message)

    result = module._capture_failure(FakePage(), tmp_path / "failure.png")

    assert result == {"screenshot_saved": False, "reason": "CAPTURE_FAILED"}
    assert sensitive_message not in json.dumps(result)


def test_s12g_task8_production_observation_is_not_task9_certified() -> None:
    module = _load_s12g_browser_acceptance_module()

    assert module._production_observation_provenance() == {
        "observation_kind": "browser_observation",
        "task9_provenance_certified": False,
        "evidence_eligible_without_task9_receipt": False,
    }


def test_s12g_task8_failed_production_summary_still_denies_task9_certification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakeArgs:
        pass

    args = FakeArgs()
    args.output_dir = tmp_path
    args.self_test = False
    args.browser = "chromium"
    args.real_sse_query = "acceptance exact query"
    committed: dict[str, object] = {}

    def fail_execute(*_args: object) -> object:
        raise module.AcceptanceRuntimeError(
            "CONTROLLED_PRODUCTION_FAILURE",
            "Controlled production failure.",
        )

    def capture_summary(
        _run_dir: Path,
        _console_events: list[dict[str, object]],
        summary: dict[str, object],
    ) -> None:
        committed.update(summary)

    monkeypatch.setattr(module, "_parse_args", lambda _argv: args)
    monkeypatch.setattr(module, "_create_run_directory", lambda _output_dir: tmp_path)
    monkeypatch.setattr(module, "_execute_browser", fail_execute)
    monkeypatch.setattr(module, "_commit_artifacts", capture_summary)

    assert module.main([]) == 1
    assert committed["status"] == "failed"
    assert committed["failure"] == {"type": "CONTROLLED_PRODUCTION_FAILURE"}
    provenance = module._production_observation_provenance()
    assert {key: committed[key] for key in provenance} == provenance


def test_s12g_task8_stream_request_targeting_and_payload_validation_are_separate() -> (
    None
):
    module = _load_s12g_browser_acceptance_module()
    query = "acceptance exact query"
    endpoint = "http://127.0.0.1:8001/api/chat/stream"

    class FakeRequest:
        def __init__(self, *, url: str, method: str, post_data: str | None) -> None:
            self.url = url
            self.method = method
            self.post_data = post_data

    valid = FakeRequest(
        url=endpoint,
        method="POST",
        post_data=json.dumps({"query": query, "mode": "chat"}),
    )
    different_query = FakeRequest(
        url=endpoint,
        method="POST",
        post_data=json.dumps({"query": query + " altered"}),
    )
    malformed = FakeRequest(url=endpoint, method="POST", post_data="not-json")
    missing_body = FakeRequest(url=endpoint, method="POST", post_data=None)

    assert all(
        module._request_targets_stream_endpoint(request, endpoint) is True
        for request in (valid, different_query, malformed, missing_body)
    )
    endpoint_mutations = (
        FakeRequest(url=endpoint + "/other", method="POST", post_data=valid.post_data),
        FakeRequest(
            url="http://localhost:8001/api/chat/stream",
            method="POST",
            post_data=valid.post_data,
        ),
        FakeRequest(
            url="http://127.0.0.1:8002/api/chat/stream",
            method="POST",
            post_data=valid.post_data,
        ),
        FakeRequest(
            url=endpoint + ";retry=1", method="POST", post_data=valid.post_data
        ),
        FakeRequest(
            url=endpoint + "?retry=1", method="POST", post_data=valid.post_data
        ),
        FakeRequest(url=endpoint + "#retry", method="POST", post_data=valid.post_data),
        FakeRequest(url=endpoint, method="GET", post_data=valid.post_data),
        FakeRequest(
            url="http://127.0.0.1:not-a-port/api/chat/stream",
            method="POST",
            post_data=valid.post_data,
        ),
    )
    assert all(
        module._request_targets_stream_endpoint(request, endpoint) is False
        for request in endpoint_mutations
    )

    assert module._request_payload_matches_query(valid, query) is True
    assert all(
        module._request_payload_matches_query(request, query) is False
        for request in (different_query, malformed, missing_body, object())
    )


@pytest.mark.parametrize(
    ("content_type", "expected"),
    (
        ("text/event-stream", True),
        ("Text/Event-Stream; charset=utf-8", True),
        (" text/event-stream ; charset=UTF-8 ", True),
        ("application/x-text/event-stream-wrong", False),
        ("text/event-stream-wrong", False),
        ("text/event-streaming", False),
        ("", False),
        (None, False),
    ),
)
def test_s12g_task8_stream_response_mime_is_exact(
    content_type: str | None,
    expected: bool,
) -> None:
    module = _load_s12g_browser_acceptance_module()

    assert module._is_event_stream_content_type(content_type) is expected


@pytest.mark.parametrize(
    "mutation",
    ("unknown-field", "chunk-after-answer", "chunk-final-mismatch"),
)
def test_s12g_task8_real_chat_malformed_raw_sse_fails_closed(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    payloads = _s12g_valid_sse_payloads()
    if mutation == "unknown-field":
        payloads[6][1]["private_field"] = "must-not-persist"
    elif mutation == "chunk-after-answer":
        payloads.insert(-1, ("answer_chunk", {"text": "late"}))
    else:
        payloads[5] = ("answer_chunk", {"text": "does-not-match"})
    stream_body = "".join(_s12g_sse_event(*event) for event in payloads)
    monkeypatch.setattr(module, "SSE_TIMEOUT_MS", 1_000)
    monkeypatch.setattr(module, "NAVIGATION_TIMEOUT_MS", 1_000)

    def assert_failed_closed(page: object) -> None:
        report = module._run_real_sse(page, "public query")

        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert report["response"]["matched_request_count"] == 1
        assert report["sse_contract"]["status"] == "failed"
        assert report["checks"]["raw_sse_contract_and_order"] is False
        assert "must-not-persist" not in json.dumps(report, ensure_ascii=False)

    _with_s12g_real_chat_page(
        (390, 844),
        assert_failed_closed,
        stream_body=stream_body,
    )


def test_s12g_task8_real_chat_wrong_stream_mime_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, _segments = _s12g_segmented_sse_stream()
    monkeypatch.setattr(module, "SSE_TIMEOUT_MS", 1_000)
    monkeypatch.setattr(module, "NAVIGATION_TIMEOUT_MS", 1_000)

    def assert_wrong_mime_fails(page: object) -> None:
        report = module._run_real_sse(page, "public query")

        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert report["response"]["matched_request_count"] == 1
        assert report["response"]["content_type_is_event_stream"] is False
        assert report["checks"]["real_sse_response"] is False

    _with_s12g_real_chat_page(
        (390, 844),
        assert_wrong_mime_fails,
        stream_body=stream_body,
        stream_content_type="application/json",
    )


def test_s12g_task8_stream_response_body_failure_is_sanitized() -> None:
    module = _load_s12g_browser_acceptance_module()
    sensitive_message = "private-response-body-must-not-persist"
    method_calls = {"finished": 0}

    class FakeResponse:
        status = 200
        headers = {"content-type": "text/event-stream"}

        def finished(self) -> None:
            method_calls["finished"] += 1

        def body(self) -> bytes:
            raise RuntimeError(sensitive_message)

    response_report, raw_body = module._read_stream_response(FakeResponse())

    assert method_calls["finished"] == 0
    assert raw_body is None
    assert response_report["body_read"] is False
    assert response_report["failures"] == [
        {
            "code": "SSE_RESPONSE_BODY_UNAVAILABLE",
            "exception_type": "RuntimeError",
        }
    ]
    assert sensitive_message not in json.dumps(response_report)


def test_s12g_task8_real_chat_propagates_unreadable_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    calls = 0

    def unreadable(_response: object) -> tuple[dict[str, object], None]:
        nonlocal calls
        calls += 1
        return (
            {
                "status": 200,
                "content_type_is_event_stream": True,
                "finished": True,
                "body_read": False,
                "body_fingerprint": None,
                "failures": [
                    {
                        "code": "SSE_RESPONSE_BODY_UNAVAILABLE",
                        "exception_type": "RuntimeError",
                    }
                ],
            },
            None,
        )

    monkeypatch.setattr(module, "_read_stream_response", unreadable)

    def assert_body_failure(page: object) -> None:
        report = module._run_real_sse(page, "public query")

        assert calls == 1
        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert report["response"]["body_read"] is False
        assert report["checks"]["real_sse_response"] is False
        assert report["checks"]["raw_sse_contract_and_order"] is False

    _with_s12g_real_chat_page(
        (390, 844),
        assert_body_failure,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_real_chat_stream_observes_response_body_and_schema() -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    query = "public query"
    endpoint = "https://s12g.test/api/chat/stream"

    def assert_stream_observation(page: object) -> None:
        exact_posts: list[object] = []

        def observe_request(request: object) -> None:
            if request.url == endpoint and request.method == "POST":
                exact_posts.append(request)

        page.on("request", observe_request)
        try:
            report = module._run_real_sse(page, query)
        finally:
            page.remove_listener("request", observe_request)
        response = report["response"]

        assert report["status"] == "passed", report
        assert report["defect_codes"] == []
        assert len(exact_posts) == 1
        assert response["target_request_count"] == 1
        assert response["duplicate_target_request_count"] == 0
        assert response["request_count_is_one"] is True
        assert response["unique_request_payload_matches_query"] is True
        assert response["matched_request_count"] == 1
        assert response["duplicate_request_count"] == 0
        assert response["primary_request_observed"] is True
        assert response["primary_response_count"] == 1
        assert response["request_finished"] is True
        assert response["request_failed"] is False
        assert response["finished"] is True
        assert response["body_read"] is True
        assert response["body_fingerprint"]["length"] == len(
            stream_body.encode("utf-8")
        )
        assert re.fullmatch(r"[0-9a-f]{64}", response["body_fingerprint"]["sha256"])
        assert report["sse_contract"]["status"] == "passed"
        assert report["sse_contract"]["schema_violations"] == []
        assert "option_followup" not in report
        assert report["control_expectations"] == {
            "streaming": [".process-stop"],
            "terminal": [
                ".process-summary summary",
                ".evidence-summary",
                ".option-button",
            ],
        }
        streaming = report["streaming_actionable_controls"]
        assert streaming == {
            "status": "passed",
            "defect_codes": [],
            "required_controls": [".process-stop"],
            "controls": {
                ".process-stop": {
                    "seen": True,
                    "visible": True,
                    "actionable": True,
                }
            },
        }
        terminal = report["actionable_controls"]
        assert terminal["required_controls"] == [
            "#chat-input",
            "#chat-submit",
            "#demo-toggle",
            ".process-summary summary",
            ".evidence-summary",
            ".option-button",
        ]
        assert terminal["controls"][".evidence-summary"] == {
            "seen": True,
            "visible": True,
            "actionable": True,
        }
        assert terminal["controls"][".option-button"] == {
            "seen": True,
            "visible": True,
            "actionable": True,
        }
        persisted = json.dumps(report, ensure_ascii=False)
        assert query not in persisted
        assert "option-1" not in persisted
        assert "ordinary request without option" not in persisted
        assert ".back-to-latest" not in terminal["required_controls"]
        assert report["checks"]["streaming_controls_actionable"] is True
        assert report["checks"]["terminal_controls_actionable"] is True
        assert report["checks"]["progressive_answer_chunk_observed"] is True
        assert report["checks"]["streaming_frame_observed"] is True
        assert report["checks"]["progressive_answer_growth"] is True
        assert report["checks"]["grew_after_detach"] is True
        assert report["checks"]["detached_scroll_and_anchor_stable"] is True
        assert report["checks"]["back_to_latest_visible_while_detached"] is True
        assert report["checks"]["back_to_latest_restored_following"] is True
        assert report["answer_creation"]["status"] == "passed"
        assert report["markdown_consistency"]["status"] == "passed"
        assert report["incremental_prefixes"]["status"] == "passed"
        assert report["checks"]["incremental_answer_prefixes"] is True
        assert report["checks"]["single_answer_created_for_request"] is True
        assert report["checks"]["rendered_markdown_matches_raw_answer"] is True
        assert report["checks"]["terminal_process_summary"] is True
        assert report["checks"]["answer_nonempty"] is True
        assert report["target_summary"][".process-stop"]["min_width"] >= 44
        assert report["target_summary"][".process-stop"]["min_height"] >= 44

    _with_s12g_real_chat_page(
        (390, 844),
        assert_stream_observation,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_real_sse_uses_single_round_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    original_remaining = module._remaining_timeout_ms
    observed_deadlines: list[float] = []

    def observe_remaining(deadline: float) -> int:
        observed_deadlines.append(deadline)
        return original_remaining(deadline)

    monkeypatch.setattr(module, "_remaining_timeout_ms", observe_remaining)

    def assert_single_deadline(page: object) -> None:
        report = module._run_real_sse(page, "public query")
        assert report["status"] == "passed", report

    _with_s12g_real_chat_page(
        (390, 844),
        assert_single_deadline,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )

    assert len(observed_deadlines) >= 3
    assert all(deadline == observed_deadlines[0] for deadline in observed_deadlines)


def test_s12g_task8_unfinished_request_exhausts_deadline_without_response_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body = "".join(
        _s12g_sse_event(*event) for event in _s12g_valid_sse_payloads()
    )
    method_calls = {"finished": 0, "body": 0}
    observed_deadlines: list[float] = []
    original_remaining = module._remaining_timeout_ms
    monkeypatch.setattr(module, "SSE_TIMEOUT_MS", 400)

    def observe_remaining(deadline: float) -> int:
        observed_deadlines.append(deadline)
        return original_remaining(deadline)

    monkeypatch.setattr(module, "_remaining_timeout_ms", observe_remaining)

    class ResponseProbe:
        def __init__(self, response: object) -> None:
            self.request = response.request
            self.status = response.status
            self.headers = response.headers

        def finished(self) -> None:
            method_calls["finished"] += 1

        def body(self) -> bytes:
            method_calls["body"] += 1
            return stream_body.encode()

    class PageWithoutRequestFinished:
        def __init__(self, page: object) -> None:
            self._page = page
            self._response_wrappers: dict[object, object] = {}
            self.active_listeners: set[tuple[str, object]] = set()

        @property
        def url(self) -> str:
            return self._page.url

        def on(self, event_name: str, listener: object) -> None:
            self.active_listeners.add((event_name, listener))
            if event_name == "requestfinished":
                return
            registered_listener = listener
            if event_name == "response":

                def wrap_response(response: object) -> None:
                    listener(ResponseProbe(response))

                registered_listener = wrap_response
                self._response_wrappers[listener] = registered_listener
            self._page.on(event_name, registered_listener)

        def remove_listener(self, event_name: str, listener: object) -> None:
            self.active_listeners.discard((event_name, listener))
            if event_name == "requestfinished":
                return
            registered_listener = self._response_wrappers.pop(listener, listener)
            self._page.remove_listener(event_name, registered_listener)

        def __getattr__(self, name: str) -> object:
            return getattr(self._page, name)

    def assert_unfinished_request(page: object) -> None:
        wrapped_page = PageWithoutRequestFinished(page)
        error = None
        started = time.monotonic()
        try:
            module._run_real_sse(wrapped_page, "public query")
        except module.AcceptanceRuntimeError as caught:
            error = caught
        elapsed = time.monotonic() - started

        assert elapsed < 1.5
        assert wrapped_page.active_listeners == set()
        assert observed_deadlines
        assert all(deadline == observed_deadlines[0] for deadline in observed_deadlines)
        assert (
            None if error is None else error.code,
            method_calls,
        ) == (
            "SSE_DEADLINE_EXCEEDED",
            {"finished": 0, "body": 0},
        )

    _with_s12g_real_chat_page(
        (390, 844),
        assert_unfinished_request,
        stream_body=stream_body,
    )


def test_s12g_task8_real_sse_cleans_up_partially_attached_network_listeners() -> None:
    module = _load_s12g_browser_acceptance_module()

    class PartialAttachPage:
        url = "https://s12g.test/chat"

        def __init__(self) -> None:
            self.active_listeners: set[tuple[str, object]] = set()

        def on(self, event_name: str, listener: object) -> None:
            if event_name == "requestfinished":
                raise RuntimeError("synthetic listener attach failure")
            self.active_listeners.add((event_name, listener))

        def remove_listener(self, event_name: str, listener: object) -> None:
            self.active_listeners.discard((event_name, listener))

    page = PartialAttachPage()
    with pytest.raises(RuntimeError, match="synthetic listener attach failure"):
        module._run_real_sse(page, "public query")

    assert page.active_listeners == set()


def test_s12g_task8_back_to_latest_click_request_is_counted_in_network_lifecycle() -> (
    None
):
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    query = "public query"
    endpoint = "https://s12g.test/api/chat/stream"

    def assert_click_request_detected(page: object) -> None:
        exact_posts: list[object] = []

        def observe_request(request: object) -> None:
            if request.url == endpoint and request.method == "POST":
                exact_posts.append(request)

        page.on("request", observe_request)
        try:
            installed = page.evaluate(
                """() => {
                  const button = document.getElementById("back-to-latest");
                  if (!button) return false;
                  window.__s12gClickBoundaryFetchDone = false;
                  button.addEventListener("click", async () => {
                    try {
                      const response = await fetch("/api/chat/stream", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({query: "public query"}),
                      });
                      await response.body?.cancel();
                    } finally {
                      window.__s12gClickBoundaryFetchDone = true;
                    }
                  }, {once: true});
                  return true;
                }"""
            )
            assert installed is True
            report = module._run_real_sse(page, query)
            page.wait_for_function("() => window.__s12gClickBoundaryFetchDone === true")
        finally:
            page.remove_listener("request", observe_request)

        response = report["response"]
        assert len(exact_posts) == 2
        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert response["target_request_count"] == 2
        assert response["duplicate_target_request_count"] == 1
        assert response["matched_request_count"] == 2
        assert response["duplicate_request_count"] == 1
        assert response["request_count_is_one"] is False
        assert response["unique_request_payload_matches_query"] is False
        assert response["primary_request_observed"] is True
        assert response["primary_response_count"] == 1
        assert [failure["code"] for failure in response["failures"]] == [
            "SSE_REQUEST_MATCH_COUNT"
        ]
        assert report["checks"]["unique_matching_stream_response"] is False
        persisted = json.dumps(report, ensure_ascii=False)
        assert query not in persisted
        assert '{"query":"public query"}' not in persisted

    _with_s12g_real_chat_page(
        (390, 844),
        assert_click_request_detected,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_terminal_read_request_is_counted_before_network_snapshot() -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    query = "public query"
    duplicate_query = "private terminal duplicate query must not persist"
    duplicate_body = json.dumps({"query": duplicate_query})
    endpoint = "https://s12g.test/api/chat/stream"

    class SubmitLocator:
        def __init__(self, locator: object, trigger_duplicate: object) -> None:
            self._locator = locator
            self._trigger_duplicate = trigger_duplicate

        def is_enabled(self) -> bool:
            assert callable(self._trigger_duplicate)
            self._trigger_duplicate()
            return self._locator.is_enabled()

        def __getattr__(self, name: str) -> object:
            return getattr(self._locator, name)

    class TerminalReadRequestPage:
        def __init__(self, page: object) -> None:
            self._page = page
            self.terminal_read_trigger_count = 0

        def _trigger_duplicate(self) -> None:
            if self.terminal_read_trigger_count:
                return
            self.terminal_read_trigger_count += 1
            dispatched = self._page.evaluate(
                """async ({duplicateBody}) => {
                  const response = await fetch("/api/chat/stream", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: duplicateBody,
                  });
                  await response.body?.cancel();
                  return true;
                }""",
                {"duplicateBody": duplicate_body},
            )
            assert dispatched is True

        def locator(self, selector: str) -> object:
            locator = self._page.locator(selector)
            if selector == "#chat-submit":
                return SubmitLocator(locator, self._trigger_duplicate)
            return locator

        def __getattr__(self, name: str) -> object:
            return getattr(self._page, name)

    def assert_terminal_read_request_detected(page: object) -> None:
        exact_posts: list[object] = []

        def observe_request(request: object) -> None:
            if request.url == endpoint and request.method == "POST":
                exact_posts.append(request)

        wrapped_page = TerminalReadRequestPage(page)
        page.on("request", observe_request)
        try:
            report = module._run_real_sse(wrapped_page, query)
        finally:
            page.remove_listener("request", observe_request)

        response = report["response"]
        assert wrapped_page.terminal_read_trigger_count == 1
        assert len(exact_posts) == 2
        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert response["target_request_count"] == 2
        assert response["duplicate_target_request_count"] == 1
        assert response["matched_request_count"] == 2
        assert response["duplicate_request_count"] == 1
        assert response["request_count_is_one"] is False
        assert response["unique_request_payload_matches_query"] is False
        assert response["primary_request_observed"] is True
        assert response["primary_response_count"] == 1
        assert [failure["code"] for failure in response["failures"]] == [
            "SSE_REQUEST_MATCH_COUNT"
        ]
        assert report["checks"]["unique_matching_stream_response"] is False
        persisted = json.dumps(report, ensure_ascii=False)
        assert query not in persisted
        assert duplicate_query not in persisted
        assert duplicate_body not in persisted

    _with_s12g_real_chat_page(
        (390, 844),
        assert_terminal_read_request_detected,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_requestfailed_returns_sanitized_report_without_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    query = "private request failure query must not persist"
    monkeypatch.setattr(module, "SSE_TIMEOUT_MS", 3_000)
    monkeypatch.setattr(module, "NAVIGATION_TIMEOUT_MS", 3_000)

    def assert_request_failure(page: object) -> None:
        started = time.monotonic()
        report = module._run_real_sse(page, query)
        elapsed = time.monotonic() - started
        response = report["response"]

        assert elapsed < 2.0
        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert response["target_request_count"] == 1
        assert response["duplicate_target_request_count"] == 0
        assert response["request_count_is_one"] is True
        assert response["unique_request_payload_matches_query"] is True
        assert response["matched_request_count"] == 1
        assert response["duplicate_request_count"] == 0
        assert response["primary_request_observed"] is True
        assert response["primary_response_count"] == 0
        assert response["request_finished"] is False
        assert response["request_failed"] is True
        assert set(response["request_failure"]) == {"code", "exception_type"}
        assert response["request_failure"]["code"] == "SSE_REQUEST_FAILED"
        assert isinstance(response["request_failure"]["exception_type"], str)
        persisted = json.dumps(report, ensure_ascii=False)
        assert query not in persisted
        assert "connectionfailed" not in persisted.lower()

    _with_s12g_real_chat_page(
        (390, 844),
        assert_request_failure,
        stream_abort=True,
    )


@pytest.mark.parametrize(
    ("duplicate_body", "private_fragments"),
    (
        (None, ()),
        (
            json.dumps({"query": "private different query must not persist"}),
            ("private different query must not persist",),
        ),
        (
            "private malformed payload must not persist {",
            ("private malformed payload must not persist",),
        ),
    ),
    ids=("same-query", "different-query", "malformed-json"),
)
def test_s12g_task8_delayed_duplicate_request_fails_single_request_contract(
    duplicate_body: str | None,
    private_fragments: tuple[str, ...],
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    query = "private delayed duplicate query must not persist"

    def assert_duplicate_detected(page: object) -> None:
        report = module._run_real_sse(page, query)
        response = report["response"]

        assert report["status"] == "failed", report
        assert report["defect_codes"]
        assert response["target_request_count"] == 2
        assert response["duplicate_target_request_count"] == 1
        assert response["matched_request_count"] == 2
        assert response["duplicate_request_count"] == 1
        assert response["request_count_is_one"] is False
        assert response["unique_request_payload_matches_query"] is False
        assert response["primary_request_observed"] is True
        assert response["primary_response_count"] == 1
        assert response["request_finished"] is True
        assert response["request_failed"] is False
        assert [failure["code"] for failure in response["failures"]] == [
            "SSE_REQUEST_MATCH_COUNT"
        ]
        assert report["checks"]["unique_matching_stream_response"] is False
        persisted = json.dumps(report, ensure_ascii=False)
        assert query not in persisted
        assert all(fragment not in persisted for fragment in private_fragments)

    _with_s12g_real_chat_page(
        (390, 844),
        assert_duplicate_detected,
        stream_body=stream_body,
        stream_segments=stream_segments,
        delayed_duplicate_ms=100,
        delayed_duplicate_body=duplicate_body,
    )


def test_s12g_task8_option_followup_is_exercised_only_by_deterministic_test() -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()
    query = "public query"

    def assert_direct_option_followup(page: object) -> None:
        production_report = module._run_real_sse(page, query)

        assert production_report["status"] == "passed", production_report
        assert "option_followup" not in production_report
        assert production_report["response"]["matched_request_count"] == 1

        option_followup = module._exercise_option_followup(
            page,
            expected_endpoint="https://s12g.test/api/chat/stream",
            original_query=query,
            option_id="option-1",
            option_expected=True,
            controls_ready=True,
            initial_answer_count=production_report["answer_creation"]["after_count"],
        )

        assert option_followup == {
            "status": "passed",
            "option_count": 1,
            "request_count": 2,
            "checks": {
                "option_rendered": True,
                "followup_observed": True,
                "original_query_reused": True,
                "entity_id_hint_matches": True,
                "duplicate_suppressed": True,
                "ordinary_request_observed": True,
                "ordinary_hint_absent": True,
            },
        }
        persisted = json.dumps(option_followup, ensure_ascii=False)
        assert query not in persisted
        assert "option-1" not in persisted
        assert "ordinary request without option" not in persisted

    _with_s12g_real_chat_page(
        (390, 844),
        assert_direct_option_followup,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_control", "expected_defect_codes"),
    (
        (
            "hidden",
            {"seen": True, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "pointer-disabled",
            {"seen": True, "visible": True, "actionable": False},
            ["REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "43px",
            {"seen": True, "visible": True, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "never-created",
            {"seen": False, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
    ),
)
def test_s12g_task8_real_streaming_stop_fails_closed_for_mutation(
    mutation: str,
    expected_control: dict[str, bool],
    expected_defect_codes: list[str],
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()

    def assert_stop_failure(page: object) -> None:
        _s12g_install_dynamic_control_mutation(page, ".process-stop", mutation)
        report = module._run_real_sse(page, "public query")
        streaming = report["streaming_actionable_controls"]

        assert report["status"] == "failed"
        assert report["defect_codes"] == expected_defect_codes
        assert report["control_expectations"]["streaming"] == [".process-stop"]
        assert streaming["status"] == "failed"
        assert streaming["required_controls"] == [".process-stop"]
        assert streaming["controls"][".process-stop"] == expected_control
        assert streaming["defect_codes"] == ["REQUIRED_CONTROL_NOT_ACTIONABLE"]
        assert report["checks"]["streaming_controls_actionable"] is False
        assert "option_followup" not in report
        if mutation == "43px":
            target = report["target_summary"][".process-stop"]
            assert target["min_width"] == pytest.approx(43, abs=0.1)
            assert target["min_height"] == pytest.approx(43, abs=0.1)

    _with_s12g_real_chat_page(
        (390, 844),
        assert_stop_failure,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_control", "expected_defect_codes"),
    (
        (
            "baseline",
            {"seen": True, "visible": True, "actionable": True},
            [],
        ),
        (
            "hidden",
            {"seen": True, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "pointer-disabled",
            {"seen": True, "visible": True, "actionable": False},
            ["REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "43px",
            {"seen": True, "visible": True, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "never-created",
            {"seen": False, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
    ),
)
def test_s12g_task8_real_terminal_evidence_follows_citations(
    mutation: str,
    expected_control: dict[str, bool],
    expected_defect_codes: list[str],
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()

    def assert_evidence_contract(page: object) -> None:
        _s12g_install_dynamic_control_mutation(page, ".evidence-summary", mutation)
        report = module._run_real_sse(page, "public query")
        terminal = report["actionable_controls"]
        expected_status = "passed" if mutation == "baseline" else "failed"

        assert report["status"] == expected_status, report
        assert report["defect_codes"] == expected_defect_codes
        assert report["control_expectations"] == {
            "streaming": [".process-stop"],
            "terminal": [
                ".process-summary summary",
                ".evidence-summary",
                ".option-button",
            ],
        }
        assert terminal["required_controls"] == [
            "#chat-input",
            "#chat-submit",
            "#demo-toggle",
            ".process-summary summary",
            ".evidence-summary",
            ".option-button",
        ]
        assert terminal["controls"][".evidence-summary"] == expected_control
        assert terminal["controls"][".option-button"] == {
            "seen": True,
            "visible": True,
            "actionable": True,
        }
        assert ".back-to-latest" not in terminal["required_controls"]
        assert report["checks"]["terminal_controls_actionable"] is (
            mutation == "baseline"
        )
        assert report["checks"]["streaming_controls_actionable"] is True
        assert "option_followup" not in report
        if mutation == "43px":
            target = report["target_summary"][".evidence-summary"]
            assert target["min_width"] == pytest.approx(43, abs=0.1)
            assert target["min_height"] == pytest.approx(43, abs=0.1)

    _with_s12g_real_chat_page(
        (390, 844),
        assert_evidence_contract,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_control", "expected_defect_codes"),
    (
        (
            "baseline",
            {"seen": True, "visible": True, "actionable": True},
            [],
        ),
        (
            "hidden",
            {"seen": True, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "pointer-disabled",
            {"seen": True, "visible": True, "actionable": False},
            ["REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "43px",
            {"seen": True, "visible": True, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
        (
            "never-created",
            {"seen": False, "visible": False, "actionable": False},
            ["TARGET_LT_44", "REQUIRED_CONTROL_NOT_ACTIONABLE"],
        ),
    ),
)
def test_s12g_task8_real_terminal_option_follows_raw_public_contract(
    mutation: str,
    expected_control: dict[str, bool],
    expected_defect_codes: list[str],
) -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream()

    def assert_option_contract(page: object) -> None:
        _s12g_install_dynamic_control_mutation(page, ".option-button", mutation)
        report = module._run_real_sse(page, "public query")
        terminal = report["actionable_controls"]
        expected_status = "passed" if mutation == "baseline" else "failed"

        assert report["status"] == expected_status, report
        assert report["defect_codes"] == expected_defect_codes
        assert report["control_expectations"]["terminal"] == [
            ".process-summary summary",
            ".evidence-summary",
            ".option-button",
        ]
        assert terminal["required_controls"][-1] == ".option-button"
        assert terminal["controls"][".option-button"] == expected_control
        assert report["checks"]["terminal_controls_actionable"] is (
            mutation == "baseline"
        )
        assert "option_followup" not in report
        if mutation == "43px":
            target = report["target_summary"][".option-button"]
            assert target["min_width"] == pytest.approx(43, abs=0.1)
            assert target["min_height"] == pytest.approx(43, abs=0.1)

    _with_s12g_real_chat_page(
        (390, 844),
        assert_option_contract,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_real_citationless_answer_does_not_require_evidence() -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream(with_citations=False)

    def assert_citationless_contract(page: object) -> None:
        report = module._run_real_sse(page, "public query")
        terminal = report["actionable_controls"]

        assert report["status"] == "passed", report
        assert report["defect_codes"] == []
        assert report["control_expectations"] == {
            "streaming": [".process-stop"],
            "terminal": [".process-summary summary", ".option-button"],
        }
        assert terminal["required_controls"] == [
            "#chat-input",
            "#chat-submit",
            "#demo-toggle",
            ".process-summary summary",
            ".option-button",
        ]
        assert ".evidence-summary" not in terminal["controls"]
        assert terminal["controls"][".option-button"] == {
            "seen": True,
            "visible": True,
            "actionable": True,
        }
        assert page.locator(".evidence-summary").count() == 0
        assert report["target_summary"][".evidence-summary"]["seen"] is False
        assert report["checks"]["streaming_controls_actionable"] is True
        assert report["checks"]["terminal_controls_actionable"] is True
        assert "option_followup" not in report

    _with_s12g_real_chat_page(
        (390, 844),
        assert_citationless_contract,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_real_optionless_answer_does_not_require_option() -> None:
    module = _load_s12g_browser_acceptance_module()
    stream_body, stream_segments = _s12g_segmented_sse_stream(with_options=False)

    def assert_optionless_contract(page: object) -> None:
        report = module._run_real_sse(page, "public query")
        terminal = report["actionable_controls"]

        assert report["status"] == "passed", report
        assert report["defect_codes"] == []
        assert report["control_expectations"] == {
            "streaming": [".process-stop"],
            "terminal": [".process-summary summary", ".evidence-summary"],
        }
        assert ".option-button" not in terminal["required_controls"]
        assert ".option-button" not in terminal["controls"]
        assert page.locator(".option-button").count() == 0
        assert report["target_summary"][".option-button"]["seen"] is False
        assert report["checks"]["streaming_controls_actionable"] is True
        assert report["checks"]["terminal_controls_actionable"] is True
        assert "option_followup" not in report

    _with_s12g_real_chat_page(
        (390, 844),
        assert_optionless_contract,
        stream_body=stream_body,
        stream_segments=stream_segments,
    )


def test_s12g_task8_production_preflight_rejects_atomic_stream_without_chunk_or_frame() -> (
    None
):
    module = _load_s12g_browser_acceptance_module()
    payloads = [
        event for event in _s12g_valid_sse_payloads() if event[0] != "answer_chunk"
    ]
    stream_body = "".join(_s12g_sse_event(*event) for event in payloads)
    raw_report = module._evaluate_sse_events(
        module._parse_sse_body(stream_body.encode())
    )

    assert raw_report["status"] == "passed"
    assert raw_report["event_counts"]["answer"] == 1
    assert raw_report["event_counts"].get("answer_chunk", 0) == 0
    assert raw_report["indexes"]["answer_chunks"] == []
    assert raw_report["checks"]["nonempty_answer"] is True
    assert raw_report["checks"]["chunks_before_answer"] is True
    assert raw_report["checks"]["chunks_reconstruct_answer"] is True

    def assert_atomic_stream_rejected(page: object) -> None:
        report = module._run_real_sse(page, "public query")
        sse_contract = report["sse_contract"]

        assert report["status"] == "failed", report
        assert report["defect_codes"] == ["VIEWPORT_RUNTIME_FAILURE"]
        assert sse_contract["status"] == "passed"
        assert sse_contract["event_counts"]["answer"] == 1
        assert sse_contract["event_counts"].get("answer_chunk", 0) == 0
        assert sse_contract["indexes"]["answer_chunks"] == []
        assert sse_contract["checks"]["nonempty_answer"] is True
        assert sse_contract["checks"]["chunks_before_answer"] is True
        assert sse_contract["checks"]["chunks_reconstruct_answer"] is True
        assert report["checks"]["progressive_answer_chunk_observed"] is False
        assert report["checks"]["streaming_frame_observed"] is False
        assert report["checks"]["progressive_answer_growth"] is False
        assert report["checks"]["grew_after_detach"] is False
        assert report["checks"]["detached_scroll_and_anchor_stable"] is False
        assert report["checks"]["back_to_latest_visible_while_detached"] is False
        assert report["checks"]["back_to_latest_restored_following"] is False
        assert "option_followup" not in report

    _with_s12g_real_chat_page(
        (390, 844),
        assert_atomic_stream_rejected,
        stream_body=stream_body,
    )


def test_s12g_task8_incremental_prefix_oracle_rejects_same_length_replacement() -> None:
    module = _load_s12g_browser_acceptance_module()
    expected = [module._fingerprint(value) for value in ("甲", "甲乙", "甲乙丙")]
    ordered = [
        {"sample_index": index, **fingerprint}
        for index, fingerprint in enumerate(expected)
    ]

    accepted = module._evaluate_incremental_prefixes(expected, ordered)
    replaced = module._evaluate_incremental_prefixes(
        expected,
        [
            ordered[0],
            {"sample_index": 1, **module._fingerprint("甲丙")},
            ordered[-1],
        ],
    )
    atomic = module._evaluate_incremental_prefixes(expected, [ordered[-1]])

    assert accepted["status"] == "passed"
    assert all(accepted["checks"].values())
    assert replaced["status"] == "failed"
    assert replaced["checks"]["all_observed_prefixes_expected"] is False
    assert atomic["status"] == "passed"
    assert all(atomic["checks"].values())


def test_s12g_task8_answer_binding_requires_exactly_one_new_node() -> None:
    module = _load_s12g_browser_acceptance_module()

    accepted = module._evaluate_answer_creation(2, 3)
    duplicated = module._evaluate_answer_creation(2, 4)

    assert accepted == {
        "status": "passed",
        "answer_index": 2,
        "before_count": 2,
        "after_count": 3,
        "created_count": 1,
        "checks": {"single_answer_created_for_request": True},
    }
    assert duplicated["status"] == "failed"
    assert duplicated["answer_index"] is None
    assert duplicated["checks"]["single_answer_created_for_request"] is False

    class FakePage:
        script = ""
        argument: object = None

        def evaluate(self, script: str, argument: object) -> dict[str, object]:
            self.script = script
            self.argument = argument
            return {"status": "passed"}

    page = FakePage()
    module._compare_rendered_markdown(page, "answer", 2)

    assert page.argument == {
        "expected_fingerprint": module._fingerprint("answer"),
        "answer_index": 2,
    }
    assert "answers[answerIndex]" in page.script
    assert "answers.length - 1" not in page.script
    assert "answer_text" not in page.argument


def test_s12g_task8_real_chat_markdown_comparison_detects_dom_drift() -> None:
    module = _load_s12g_browser_acceptance_module()
    answer_text = "# Public answer\n\n- **Alpha**\n- 中文 Beta"

    def assert_markdown_comparison(page: object) -> None:
        page.evaluate(
            """(answerText) => {
              setPresentationState("conversation");
              const answer = document.createElement("div");
              answer.className = "answer";
              document.getElementById("messages").append(answer);
              renderMarkdown(answer, answerText);
            }""",
            answer_text,
        )

        matched = module._compare_rendered_markdown(page, answer_text, 0)
        assert matched["status"] == "passed"
        assert matched["checks"] == {
            "answer_present": True,
            "normalized_text_matches": True,
            "hashes_computed": True,
            "markdown_canary": True,
        }
        assert matched["canary"] == {
            "status": "passed",
            "checks": {
                "ordered_list_items": True,
                "unordered_list_items": True,
                "closed_fence": True,
                "unclosed_fence": True,
                "chinese_text": True,
            },
        }
        assert "html_matches" not in matched["checks"]
        assert "html" not in matched

        page.locator(".answer").nth(0).evaluate(
            "(answer) => answer.append(document.createTextNode(' unexpected drift'))"
        )
        drifted = module._compare_rendered_markdown(page, answer_text, 0)

        assert drifted["status"] == "failed"
        assert drifted["checks"]["answer_present"] is True
        assert drifted["checks"]["normalized_text_matches"] is False
        assert drifted["checks"]["hashes_computed"] is True
        assert drifted["checks"]["markdown_canary"] is True

    _with_s12g_real_chat_page((390, 844), assert_markdown_comparison)


def test_s12g_task8_markdown_oracle_rejects_shared_corrupt_renderer() -> None:
    module = _load_s12g_browser_acceptance_module()
    answer_text = "# Public answer\n\n- Alpha\n- 中文 Beta"

    def assert_shared_renderer_corruption_fails(page: object) -> None:
        page.evaluate(
            """(answerText) => {
              setPresentationState("conversation");
              renderMarkdown = (container) => {
                container.textContent = "shared renderer corruption";
              };
              const answer = document.createElement("div");
              answer.className = "answer";
              document.getElementById("messages").append(answer);
              renderMarkdown(answer, answerText);
            }""",
            answer_text,
        )

        report = module._compare_rendered_markdown(page, answer_text, 0)

        assert report["status"] == "failed"
        assert report["checks"]["normalized_text_matches"] is False
        assert report["checks"]["markdown_canary"] is False
        assert report["canary"]["status"] == "failed"

    _with_s12g_real_chat_page((390, 844), assert_shared_renderer_corruption_fails)


def test_s12g_task8_stream_probe_hashes_same_length_answer_replacement() -> None:
    module = _load_s12g_browser_acceptance_module()

    def assert_replacement_is_hashed(page: object) -> None:
        page.evaluate("() => setPresentationState('conversation')")
        module._inject_stream_history_and_probe(page, 0)
        page.evaluate(
            """() => {
              const answer = document.createElement("div");
              answer.className = "answer";
              answer.textContent = "甲乙";
              document.getElementById("messages").append(answer);
            }"""
        )
        page.evaluate(
            "() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        page.locator(".answer").nth(0).evaluate(
            "(answer) => { answer.textContent = '甲丙'; }"
        )
        page.evaluate(
            "() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )

        probe = module._stream_probe_result(page)
        assert isinstance(probe, dict)
        fingerprints = probe["answer_fingerprints"]
        assert len(fingerprints) >= 2
        assert all(
            set(fingerprint) == {"sample_index", "length", "sha256"}
            for fingerprint in fingerprints
        )
        assert fingerprints[0]["length"] == fingerprints[-1]["length"] == 2
        assert fingerprints[0]["sha256"] == module._fingerprint("甲乙")["sha256"]
        assert fingerprints[-1]["sha256"] == module._fingerprint("甲丙")["sha256"]
        persisted = json.dumps(fingerprints, ensure_ascii=False)
        assert "甲乙" not in persisted
        assert "甲丙" not in persisted

        report = module._evaluate_incremental_prefixes(
            [module._fingerprint("甲乙")], fingerprints
        )
        assert report["status"] == "failed"
        assert report["checks"]["all_observed_prefixes_expected"] is False

    _with_s12g_real_chat_page((390, 844), assert_replacement_is_hashed)


def test_s12g_task8_stream_probe_binds_request_answer_index() -> None:
    module = _load_s12g_browser_acceptance_module()

    class FakePage:
        script = ""
        argument: object = None

        def evaluate(self, script: str, argument: object) -> bool | None:
            if script == module.DOM_MARKER_PROBE_SCRIPT:
                return True
            self.script = script
            self.argument = argument
            return None

    page = FakePage()
    module._inject_stream_history_and_probe(page, 2)

    assert page.argument == {
        "target_selectors": list(module.VISIBLE_TARGET_SELECTORS),
        "answer_index": 2,
    }
    assert "answers[answerIndex]" in page.script
    assert "answers.length - 1" not in page.script


def test_s12g_task8_production_stream_uses_shared_fail_closed_evaluators() -> None:
    module = _load_s12g_browser_acceptance_module()
    wrapper_code = module._run_real_sse.__code__
    wrapper_names = set(wrapper_code.co_names)
    run_code = module._run_real_sse_round.__code__
    run_names = set(run_code.co_names)
    observe_request_code = next(
        value
        for value in run_code.co_consts
        if getattr(value, "co_name", None) == "observe_request"
    )
    response_reader_names = set(module._read_stream_response.__code__.co_names)

    assert {
        "_read_stream_response",
        "_parse_sse_body",
        "_evaluate_sse_events",
        "_evaluate_dom_marker_latches",
        "_evaluate_detached_samples",
        "_summarize_target_samples",
        "_evaluate_answer_creation",
        "_compare_rendered_markdown",
        "_terminal_actionable_controls",
    } <= run_names
    assert "_request_targets_stream_endpoint" in observe_request_code.co_names
    assert "_request_payload_matches_query" not in observe_request_code.co_names
    assert "_request_payload_matches_query" in run_names
    assert {"_is_event_stream_content_type", "body"} <= response_reader_names
    assert "finished" not in response_reader_names
    assert {"_run_real_sse_round", "remove_listener"} <= wrapper_names
    assert {
        "_actionable_control_observations",
        "_evaluate_actionable_controls",
    } <= set(module._terminal_actionable_controls.__code__.co_names)

    marker_probe_script = module.DOM_MARKER_PROBE_SCRIPT
    for token in (
        "MutationObserver",
        "characterDataOldValue",
        "attributeOldValue",
        "crypto.subtle.digest",
    ):
        assert token in marker_probe_script
    assert "_install_dom_marker_probe" in (
        module._inject_stream_history_and_probe.__code__.co_names
    )

    probe_literals = "\n".join(
        value
        for value in module._inject_stream_history_and_probe.__code__.co_consts
        if isinstance(value, str)
    )
    result_literals = "\n".join(
        value
        for value in module._stream_probe_result.__code__.co_consts
        if isinstance(value, str)
    )
    assert "requestAnimationFrame" in probe_literals
    assert "terminal_pre_disconnect" in result_literals
    assert "terminal_post_disconnect" in result_literals


def test_s12g_task8_keyboard_rotation_passes_phases_to_shared_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    phases = [
        {"phase_index": index, "sentinel": f"phase-{index}"}
        for index in range(len(module.ROTATION_PHASE_VIEWPORTS))
    ]
    evaluator_calls: list[tuple[object, object]] = []

    class FakeInput:
        def fill(self, value: str) -> None:
            assert value == "s12g-rotation-continuity"

        def focus(self) -> None:
            return None

    class FakePage:
        def locator(self, selector: str) -> FakeInput:
            assert selector == "#chat-input"
            return FakeInput()

        def evaluate(self, script: str) -> bool | None:
            if script == "() => setPresentationState('conversation')":
                return True
            if 'setScrollIntent("detached")' in script:
                return True
            return None

    def phase_record(
        _page: FakePage,
        index: int,
        width: int,
        height: int,
    ) -> dict[str, object]:
        assert (width, height) == module.ROTATION_PHASE_VIEWPORTS[index]
        return phases[index]

    def evaluate(
        received_phases: object,
        expected_fingerprint: object,
    ) -> dict[str, object]:
        evaluator_calls.append((received_phases, expected_fingerprint))
        return {
            "status": "failed",
            "defect_codes": ["ROTATION_STALE_GEOMETRY"],
            "checks": {"sentinel": False},
            "phases": received_phases,
        }

    monkeypatch.setattr(module, "_rotation_phase_record", phase_record)
    monkeypatch.setattr(module, "_evaluate_rotation_continuity", evaluate)

    report = module._exercise_keyboard_and_rotation(FakePage())

    assert evaluator_calls == [
        (phases, module._fingerprint("s12g-rotation-continuity"))
    ]
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["ROTATION_STALE_GEOMETRY"]
    assert report["simulation_scope"] == (
        "viewport_resize_not_real_ime_or_device_keyboard"
    )


def test_s12g_task8_self_test_aggregates_marker_and_rotation_evaluator_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from playwright.sync_api import sync_playwright

    module = _load_s12g_browser_acceptance_module()
    marker_calls: list[object] = []
    rotation_calls: list[tuple[object, object]] = []

    def fail_marker(latches: object) -> dict[str, object]:
        marker_calls.append(latches)
        return {
            "status": "failed",
            "checks": {
                "valid_latch_shape": False,
                "no_dom_mutation_markers": False,
            },
            "latches": [],
        }

    def fail_rotation(
        phases: object,
        expected_fingerprint: object,
    ) -> dict[str, object]:
        rotation_calls.append((phases, expected_fingerprint))
        return {
            "status": "failed",
            "defect_codes": ["ROTATION_STALE_GEOMETRY"],
            "checks": {"sentinel": False},
            "phases": phases,
        }

    monkeypatch.setattr(module, "_evaluate_dom_marker_latches", fail_marker)
    monkeypatch.setattr(module, "_evaluate_rotation_continuity", fail_rotation)
    monkeypatch.setattr(
        module,
        "_capture_failure",
        lambda *_args: {"screenshot_saved": False, "reason": "CAPTURE_FAILED"},
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            report = module._run_self_test(browser, tmp_path, [])
        finally:
            browser.close()

    assert len(marker_calls) == 1
    assert len(rotation_calls) == 2
    assert report["status"] == "failed"
    assert report["defect_codes"] == [
        "ROTATION_STALE_GEOMETRY",
        "VIEWPORT_RUNTIME_FAILURE",
    ]


def test_s12g_task8_production_aggregates_child_report_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_s12g_browser_acceptance_module()
    viewport = (390, 844)
    child_calls: list[str] = []

    class FakePage:
        def goto(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_selector(self, *_args: object, **_kwargs: object) -> None:
            return None

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            return None

    class FakeContext:
        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
            assert (viewport["width"], viewport["height"]) == (390, 844)
            return FakeContext()

    def presentation(_page: FakePage) -> dict[str, object]:
        child_calls.append("presentation")
        return {
            "status": "failed",
            "defect_codes": ["TARGET_LT_44"],
            "states": [],
        }

    def rotation(_page: FakePage) -> dict[str, object]:
        child_calls.append("rotation")
        return {"status": "passed", "defect_codes": []}

    def real_sse(_page: FakePage, query: str) -> dict[str, object]:
        child_calls.append("real_sse")
        assert query == "safe query"
        return {"status": "passed", "defect_codes": []}

    monkeypatch.setattr(module, "VIEWPORT_MATRIX", (viewport,))
    monkeypatch.setattr(module, "LONG_CONTENT_VIEWPORTS", set())
    monkeypatch.setattr(module, "SSE_VIEWPORT", viewport)
    monkeypatch.setattr(module, "_attach_sanitized_console", lambda *_args: None)
    monkeypatch.setattr(module, "_exercise_presentation_states", presentation)
    monkeypatch.setattr(module, "_exercise_keyboard_and_rotation", rotation)
    monkeypatch.setattr(module, "_run_real_sse", real_sse)
    monkeypatch.setattr(
        module,
        "_capture_failure",
        lambda *_args: {
            "screenshot_saved": False,
            "reason": "MASK_ROOTS_UNAVAILABLE",
        },
    )

    report = module._run_production(
        FakeBrowser(),
        "https://s12g.test/chat",
        "safe query",
        tmp_path,
        [],
    )

    assert child_calls == ["presentation", "rotation", "real_sse"]
    assert report["status"] == "failed"
    assert report["defect_codes"] == ["TARGET_LT_44"]
    assert report["viewports"][0]["status"] == "failed"
    assert report["viewports"][0]["defect_codes"] == ["TARGET_LT_44"]


def test_s12g_task5_locks_root_and_gives_messages_the_only_shell_scroll(
    chat_html: str,
    chat_css: str,
) -> None:
    viewport = re.search(
        r'<meta\s+name="viewport"\s+content="([^"]+)"\s*/?>',
        chat_html,
    )
    assert viewport is not None
    assert tuple(part.strip() for part in viewport.group(1).split(",")) == (
        "width=device-width",
        "initial-scale=1",
        "viewport-fit=cover",
    )

    root_rule = _css_rule(chat_css, r"html\s*,\s*body")
    assert _css_values(root_rule, "width") == ("100%",)
    assert _css_values(root_rule, "height") == ("100%",)
    assert _css_values(root_rule, "overflow") == ("hidden",)
    assert _css_values(_css_rule(chat_css, r"body"), "min-width") == ()

    shell_rule = _css_rule(chat_css, r"\.shell")
    assert _css_values(shell_rule, "height") == (
        "100vh",
        "var(--app-height, 100vh)",
    )
    assert _css_values(shell_rule, "min-width") == ("0",)
    assert _css_values(shell_rule, "min-height") == ("0",)
    assert _css_values(shell_rule, "overflow") == ("hidden",)
    assert _css_values(shell_rule, "grid-template-rows") == (
        "auto auto minmax(0, 1fr) auto",
    )

    dynamic_viewport_support = _section(
        chat_css,
        "@supports (height: 100dvh)",
        "@media (max-width: 720px)",
    )
    dynamic_shell_rule = _css_rule(dynamic_viewport_support, r"\.shell")
    assert _css_values(dynamic_shell_rule, "height") == (
        "100dvh",
        "var(--app-height, 100dvh)",
    )

    messages_rule = _css_rule(chat_css, r"\.messages")
    assert _css_values(messages_rule, "min-width") == ("0",)
    assert _css_values(messages_rule, "min-height") == ("0",)
    assert _css_values(messages_rule, "overflow-y") == ("auto",)
    assert _css_values(messages_rule, "overflow-x") == ("hidden",)


def test_s12g_task5_narrow_phone_demo_is_single_row_local_scroll_track(
    chat_css: str,
) -> None:
    narrow_phone = _section(
        chat_css,
        "@media (max-width: 430px)",
        ":root.visual-viewport-short",
    )
    demo_grid_rule = _css_rule(narrow_phone, r"\.demo-grid")
    assert _css_values(demo_grid_rule, "grid-template-columns") == ("none",)
    assert _css_values(demo_grid_rule, "grid-auto-flow") == ("column",)
    assert _css_values(demo_grid_rule, "grid-auto-columns") == ("minmax(250px, 82vw)",)
    assert _css_values(demo_grid_rule, "max-width") == ("100%",)
    assert _css_values(demo_grid_rule, "overflow-x") == ("auto",)
    assert _css_values(demo_grid_rule, "overflow-y") == ("hidden",)

    demo_chip_rule = _css_rule(narrow_phone, r"\.demo-chip")
    assert _css_values(demo_chip_rule, "width") == ("100%",)
    assert _css_values(demo_chip_rule, "max-width") == ("100%",)


def test_s12g_task5_short_layout_viewport_hides_demo_strip(chat_css: str) -> None:
    short_height_media = _section(
        chat_css,
        "@media (max-height: 500px)",
        "@media (orientation: landscape)",
    )

    demo_strip_rule = _css_rule(short_height_media, r"\.demo-strip")
    assert _css_values(demo_strip_rule, "display") == ("none",)


def test_s12g_task5_short_visual_viewport_marker_compacts_intrinsic_rows(
    chat_css: str,
) -> None:
    short_visual_viewport = _section(
        chat_css,
        ":root.visual-viewport-short",
        "@media (max-height: 500px)",
    )

    demo_strip_rule = _css_rule(
        short_visual_viewport,
        r":root\.visual-viewport-short\s+\.demo-strip",
    )
    assert _css_values(demo_strip_rule, "display") == ("none",)

    header_rule = _css_rule(
        short_visual_viewport,
        r":root\.visual-viewport-short\s+\.header",
    )
    assert _css_values(header_rule, "--header-padding-block") == ("8px",)
    header_subtitle_rule = _css_rule(
        short_visual_viewport,
        r":root\.visual-viewport-short\s+\.header\s+p",
    )
    assert _css_values(header_subtitle_rule, "display") == ("none",)

    composer_rule = _css_rule(
        short_visual_viewport,
        r":root\.visual-viewport-short\s+\.composer",
    )
    assert _css_values(composer_rule, "--composer-padding-top") == ("8px",)
    assert _css_values(composer_rule, "--composer-padding-bottom") == ("8px",)
    composer_note_rule = _css_rule(
        short_visual_viewport,
        r":root\.visual-viewport-short\s+\.composer-note",
    )
    assert _css_values(composer_note_rule, "display") == ("none",)


def test_s12g_task5_safe_area_padding_is_single_owner_and_has_fallback(
    chat_css: str,
) -> None:
    safe_area_counts = {
        edge: len(
            re.findall(
                rf"env\(\s*safe-area-inset-{edge}\s*,\s*0px\s*\)",
                chat_css,
            )
        )
        for edge in ("top", "right", "bottom", "left")
    }
    assert safe_area_counts == {"top": 1, "right": 2, "bottom": 1, "left": 2}

    header_rule = _css_rule(chat_css, r"\.header")
    composer_rule = _css_rule(chat_css, r"\.composer")
    header_padding = _css_values(header_rule, "padding")
    composer_padding = _css_values(composer_rule, "padding")
    assert len(header_padding) == 2
    assert len(composer_padding) == 2
    assert "env(" not in header_padding[0]
    assert "env(" not in composer_padding[0]

    for edge in ("top", "right", "left"):
        token = f"env(safe-area-inset-{edge}, 0px)"
        assert token in header_padding[1]
    assert "safe-area-inset-bottom" not in header_rule

    for edge in ("right", "bottom", "left"):
        token = f"env(safe-area-inset-{edge}, 0px)"
        assert token in composer_padding[1]
    assert "safe-area-inset-top" not in composer_rule
    assert "calc(" in header_padding[1]
    assert "calc(" in composer_padding[1]


def test_s12g_task5_contains_long_answer_content_locally(chat_css: str) -> None:
    for selector in (r"\.message", r"\.bubble"):
        assert _css_values(_css_rule(chat_css, selector), "min-width") == ("0",)

    answer_link = _css_rule(chat_css, r"\.answer\s+a")
    assert _css_values(answer_link, "overflow-wrap") == ("anywhere",)

    answer_pre = _css_rule(chat_css, r"\.answer\s+pre")
    assert _css_values(answer_pre, "max-width") == ("100%",)
    assert _css_values(answer_pre, "overflow-x") == ("auto",)

    answer_table = _css_rule(chat_css, r"\.answer\s+table")
    assert _css_values(answer_table, "display") == ("block",)
    assert _css_values(answer_table, "max-width") == ("100%",)
    assert _css_values(answer_table, "overflow-x") == ("auto",)

    answer_image = _css_rule(chat_css, r"\.answer\s+img")
    assert _css_values(answer_image, "max-width") == ("100%",)
    assert _css_values(answer_image, "height") == ("auto",)


def test_s12g_task5_uses_geometry_media_queries_without_device_sniffing(
    chat_css: str,
    chat_script: str,
) -> None:
    assert re.search(r"@media\s*\(\s*max-width\s*:\s*720px\s*\)", chat_css)
    assert re.search(r"@media\s*\(\s*max-height\s*:\s*500px\s*\)", chat_css)
    assert re.search(
        r"@media\s*\(\s*orientation\s*:\s*landscape\s*\)\s*and\s*"
        r"\(\s*max-height\s*:\s*500px\s*\)",
        chat_css,
    )
    assert (
        re.search(r"navigator\s*\.\s*userAgent\b", chat_script, re.IGNORECASE) is None
    )
    assert (
        re.search(r"navigator\s*\.\s*userAgentData\b", chat_script, re.IGNORECASE)
        is None
    )


def test_s12g_task6_uses_bounded_autogrowing_textarea_markup(
    chat_html: str,
    chat_css: str,
) -> None:
    composer = _section(chat_html, '<footer class="composer">', "</footer>")
    textarea = re.search(
        r'<textarea\b(?=[^>]*\bid="chat-input")[^>]*>',
        composer,
    )
    assert textarea is not None
    for attribute in (
        'rows="1"',
        'maxlength="500"',
        'autocomplete="off"',
        'aria-label="检索问题"',
    ):
        assert attribute in textarea.group(0)
    assert re.search(r'<input\b(?=[^>]*\bid="chat-input")', composer) is None
    assert re.search(r"\.input-row\s+input\b", chat_css) is None

    textarea_rule = _css_rule(chat_css, r"\.input-row\s+textarea")
    assert _css_values(textarea_rule, "min-width") == ("0",)
    assert _css_values(textarea_rule, "flex") == ("1",)
    assert _css_values(textarea_rule, "box-sizing") == ("border-box",)
    assert _css_values(textarea_rule, "resize") == ("none",)
    assert _css_values(textarea_rule, "overflow-y") == ("hidden",)


def test_s12g_task6_has_accessible_demo_presentation_state_toggle(
    chat_html: str,
    chat_css: str,
) -> None:
    shell = re.search(r'<div\s+class="shell"[^>]*>', chat_html)
    assert shell is not None
    assert 'data-presentation-state="landing"' in shell.group(0)

    demo_strip = re.search(
        r'<section\b(?=[^>]*\bclass="demo-strip")(?=[^>]*\bid="demo-strip")[^>]*>',
        chat_html,
    )
    assert demo_strip is not None

    toggle = re.search(
        r'<button\b(?=[^>]*\bid="demo-toggle")[^>]*>(?P<text>.*?)</button>',
        chat_html,
        flags=re.DOTALL,
    )
    assert toggle is not None
    for attribute in (
        'type="button"',
        'aria-controls="demo-strip"',
        'aria-expanded="true"',
    ):
        assert attribute in toggle.group(0)
    assert "示例问题" in toggle.group("text")

    toggle_rule = _css_rule(chat_css, r"\.demo-toggle")
    assert _css_values(toggle_rule, "display") == ("none",)
    toggle_focus_rule = _css_rule(chat_css, r"\.demo-toggle:focus-visible")
    assert _css_values(toggle_focus_rule, "outline")
    assert _css_values(toggle_focus_rule, "outline-offset")

    conversation_strip = _css_rule(
        chat_css,
        r'\.shell\[data-presentation-state="conversation"\]\s+\.demo-strip',
    )
    assert _css_values(conversation_strip, "display") == ("none",)
    visible_toggle = _css_rule(
        chat_css,
        r'\.shell\[data-presentation-state="conversation"\]\s+\.demo-toggle\s*,\s*'
        r'\.shell\[data-presentation-state="demo-expanded"\]\s+\.demo-toggle',
    )
    assert _css_values(visible_toggle, "display") == ("inline-flex",)

    compact_css = _section(
        chat_css,
        "@media (max-width: 720px)",
        ":root.visual-viewport-short",
    )
    compact_header = _css_rule(
        compact_css,
        r'\.shell\[data-presentation-state="conversation"\]\s+\.header\s*,\s*'
        r'\.shell\[data-presentation-state="demo-expanded"\]\s+\.header',
    )
    assert _css_values(compact_header, "--header-padding-block") == ("8px",)
    compact_subtitle = _css_rule(
        compact_css,
        r'\.shell\[data-presentation-state="conversation"\]\s+\.header\s+p\s*,\s*'
        r'\.shell\[data-presentation-state="demo-expanded"\]\s+\.header\s+p',
    )
    assert _css_values(compact_subtitle, "display") == ("none",)


def test_s12g_task7_has_accessible_back_to_latest_control(chat_html: str) -> None:
    messages = re.search(
        r'<main\b(?=[^>]*\bid="messages")[^>]*>',
        chat_html,
    )
    assert messages is not None
    for attribute in (
        'aria-label="对话消息"',
        'aria-live="polite"',
        'tabindex="-1"',
        'data-scroll-intent="following"',
    ):
        assert attribute in messages.group(0)

    composer = _section(chat_html, '<footer class="composer">', "</footer>")
    control = re.search(
        r'<button\b(?=[^>]*\bid="back-to-latest")[^>]*>'
        r"(?P<text>.*?)</button>",
        composer,
        flags=re.DOTALL,
    )
    assert control is not None
    for attribute in ('type="button"', 'aria-controls="messages"'):
        assert attribute in control.group(0)
    assert re.search(r"\shidden(?:\s|>)", control.group(0))
    assert control.group("text").strip() == "回到最新"


@pytest.mark.parametrize(
    "selector_pattern",
    (
        r"\.submit",
        r"\.demo-toggle",
        r"\.demo-chip",
        r"\.process-stop",
        r"\.back-to-latest",
        r"\.evidence-summary",
        r"\.process-summary\s+summary",
        r"\.option-button",
    ),
)
def test_s12g_task7_interactive_targets_are_at_least_44px(
    chat_css: str,
    selector_pattern: str,
) -> None:
    rule = _css_rule(chat_css, selector_pattern)
    for property_name in ("min-width", "min-height"):
        values = _css_values(rule, property_name)
        assert len(values) == 1, (selector_pattern, property_name, values)
        assert values[0].endswith("px"), (selector_pattern, property_name, values)
        assert float(values[0].removesuffix("px")) >= 44


@pytest.mark.parametrize(
    "selector_pattern",
    (r"\.evidence-summary", r"\.process-summary\s+summary"),
)
def test_s12g_task7_disclosure_summaries_use_full_hit_area(
    chat_css: str,
    selector_pattern: str,
) -> None:
    rule = _css_rule(chat_css, selector_pattern)
    assert _css_values(rule, "display") in (("flex",), ("inline-flex",))
    assert _css_values(rule, "align-items") == ("center",)


def test_s12g_task7_back_to_latest_overlays_without_resizing_messages(
    chat_css: str,
) -> None:
    composer_rule = _css_rule(chat_css, r"\.composer")
    assert _css_values(composer_rule, "position") == ("relative",)

    control_rule = _css_rule(chat_css, r"\.back-to-latest")
    assert _css_values(control_rule, "position") == ("absolute",)
    hidden_rule = _css_rule(chat_css, r"\.back-to-latest\[hidden\]")
    assert _css_values(hidden_rule, "display") == ("none",)


def test_s12g_task7_interactive_controls_keep_accessible_names(
    chat_html: str,
    chat_script: str,
) -> None:
    composer = _section(chat_html, '<footer class="composer">', "</footer>")
    for control_id, accessible_name in (
        ("chat-submit", "发送"),
        ("back-to-latest", "回到最新"),
    ):
        control = re.search(
            rf'<button\b(?=[^>]*\bid="{control_id}")[^>]*>'
            rf"(?P<text>.*?)</button>",
            composer,
            flags=re.DOTALL,
        )
        assert control is not None
        assert control.group("text").strip() == accessible_name

    demo_toggle = re.search(
        r'<button\b(?=[^>]*\bid="demo-toggle")[^>]*>(?P<text>.*?)</button>',
        chat_html,
        flags=re.DOTALL,
    )
    assert demo_toggle is not None
    assert "示例问题" in demo_toggle.group("text")
    assert 'process.addAction("停止生成", stopGeneration)' in chat_script
    assert 'create("summary", "evidence-summary", "查看依据")' in chat_script
    assert 'process.finish("查看检索过程")' in chat_script


def test_s12g_task7_contains_long_answer_content_locally(chat_css: str) -> None:
    answer_link = _css_rule(chat_css, r"\.answer\s+a")
    assert _css_values(answer_link, "overflow-wrap") == ("anywhere",)

    inline_code = _css_rule(chat_css, r"\.answer\s+code")
    assert _css_values(inline_code, "overflow-wrap") == ("anywhere",)
    assert _css_values(inline_code, "word-break") == ("break-word",)

    answer_pre = _css_rule(chat_css, r"\.answer\s+pre")
    assert _css_values(answer_pre, "max-width") == ("100%",)
    assert _css_values(answer_pre, "overflow-x") == ("auto",)
    assert _css_values(answer_pre, "overscroll-behavior-inline") == ("contain",)

    pre_code = _css_rule(chat_css, r"\.answer\s+pre\s+code")
    assert _css_values(pre_code, "overflow-wrap") == ("normal",)
    assert _css_values(pre_code, "word-break") == ("normal",)

    answer_table = _css_rule(chat_css, r"\.answer\s+table")
    assert _css_values(answer_table, "display") == ("block",)
    assert _css_values(answer_table, "max-width") == ("100%",)
    assert _css_values(answer_table, "overflow-x") == ("auto",)
    assert _css_values(answer_table, "overscroll-behavior-inline") == ("contain",)

    answer_image = _css_rule(chat_css, r"\.answer\s+img")
    assert _css_values(answer_image, "max-width") == ("100%",)
    assert _css_values(answer_image, "height") == ("auto",)

    nested_details_and_citations = _css_rule(
        chat_css,
        r"\.bubble\s+details\s*,\s*\.citations",
    )
    assert _css_values(nested_details_and_citations, "min-width") == ("0",)
    assert _css_values(nested_details_and_citations, "max-width") == ("100%",)


def test_chat_inline_javascript_parses(chat_script: str) -> None:
    completed = subprocess.run(
        ["node", "--check", "-"],
        input=chat_script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_browse_preview_hides_internal_ids_and_maps_machine_statuses(
    browse_script: str,
) -> None:
    labels = _section(
        browse_script,
        "const qualityLabels",
        "const releasePill",
    )
    helpers = _section(
        browse_script,
        "function qualityText",
        "function formatTime",
    )
    harness = f"""
{labels}
{helpers}
console.log(JSON.stringify({{
  ready: qualityText("ready"),
  verified: qualityText("verified_preview"),
  unknown: qualityText("unexpected_internal_status"),
  previewLimit: limitationText({{code: "preview_selection_only"}}),
  unknownLimit: limitationText({{code: "internal_limit_code"}}),
}}));
"""
    completed = subprocess.run(
        ["node", "-"],
        input=harness,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "ready": "已核验",
        "verified": "已核验",
        "unknown": "状态已记录",
        "previewLimit": "当前仅展示少量只读真实数据",
        "unknownLimit": "存在已记录限制",
    }

    load_status = _section(
        browse_script, "async function loadStatus()", "function buildTabs"
    )
    assert "releasePill.textContent = status.release_id" not in load_status
    assert 'releasePill.textContent = "真实数据预览 · 版本已绑定"' in load_status

    item_card = _section(
        browse_script, "function itemCard(", "function inspectorPrompt"
    )
    render_detail = _section(
        browse_script, "function renderDetail(", "function createEvidenceSummary"
    )
    evidence_summary = _section(
        browse_script,
        "function createEvidenceSummary",
        "async function loadDetail",
    )
    load_related = _section(
        browse_script, "async function loadRelated", "function gapCard"
    )
    for renderer in (item_card, render_detail, evidence_summary, load_related):
        assert 'create("div", "canonical-id"' not in renderer
        assert "tokenList(evidenceIds)" not in renderer
    assert "qualityText(item.quality_status)" in item_card
    assert "qualityText(detail.quality_status)" in render_detail
    assert "limitationsText" in item_card
    assert "limitationsText" in render_detail


def test_browse_inline_javascript_parses(browse_script: str) -> None:
    completed = subprocess.run(
        ["node", "--check", "-"],
        input=browse_script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
