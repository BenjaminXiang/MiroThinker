from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHAT_PATH = _REPO_ROOT / "apps/admin-console/backend/static/chat.html"
_BROWSE_PATH = _REPO_ROOT / "apps/admin-console/backend/static/browse.html"


@pytest.fixture(scope="module")
def chat_html() -> str:
    return _CHAT_PATH.read_text(encoding="utf-8")


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
    assert "/api/canonical-v2/admin/domains/" in chat_script

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
    assert "renderCurrentWebEvidence(view.bubble, data.evidence || [])" not in chat_script
    assert 'create("details", "evidence-disclosure")' in chat_script
    assert 'create("summary", "evidence-summary", "查看依据")' in chat_script
    assert "evidenceDetails.open = false" in chat_script


def test_chat_evidence_is_collapsed_and_internal_trace_is_not_rendered(
    chat_script: str,
) -> None:
    assistant_renderer = _section(
        chat_script,
        "function renderAssistant(data, originalQuery)",
        "async function sendQuery",
    )

    assert 'create("details", "evidence-disclosure")' in chat_script
    assert 'create("summary", "evidence-summary", "查看依据")' in chat_script
    assert ".open = false" in chat_script
    assert "renderCitations(evidenceDetails, data.citations || [])" in assistant_renderer
    assert "renderTrace(" not in assistant_renderer
    assert "renderCurrentWebEvidence(" not in assistant_renderer
    assert "response-meta" not in assistant_renderer

    assert "element.textContent = String(text)" in chat_script
    assert re.search(r"(?:inner|outer)\s*HTML", chat_script, re.IGNORECASE) is None
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
        "a" * 64,
        "COMP-3B95F48EB687",
        "professor:internal-preview-id",
        "source_nature=current_web",
        "evidence:sha256:" + "b" * 64,
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
    snippet: "COMP-3B95F48EB687",
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

    load_status = _section(browse_script, "async function loadStatus()", "function buildTabs")
    assert "releasePill.textContent = status.release_id" not in load_status
    assert 'releasePill.textContent = "真实数据预览 · 版本已绑定"' in load_status

    item_card = _section(browse_script, "function itemCard(", "function inspectorPrompt")
    render_detail = _section(browse_script, "function renderDetail(", "function createEvidenceSummary")
    evidence_summary = _section(
        browse_script,
        "function createEvidenceSummary",
        "async function loadDetail",
    )
    load_related = _section(browse_script, "async function loadRelated", "function gapCard")
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
