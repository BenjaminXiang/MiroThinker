from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "backend" / "static"


def test_review_presentation_translates_contracts_and_blind_labels_for_humans() -> None:
    presentation_path = STATIC / "review_presentation.js"
    contract_payload = {
        "query": "我关注的是深圳智航无界科技",
        "family": "multi_turn",
        "as_of": "2026-07-13T17:44:15Z",
        "structured_requirements": {
            "required_claims": [
                {
                    "claim_id": "claim:req-lawful-safety-guidance",
                    "evidence_obligation": "accepted_policy_snapshot",
                    "materiality": "material",
                    "object_constraint": {"kind": "boolean", "value": True},
                    "predicate": "provides_lawful_safety_guidance",
                    "source_snapshot_ids": ["snapshot:openspec:safety-guidance"],
                    "subject": {
                        "entity_id": "case-subject:wb-r009",
                        "entity_type": "user_request",
                    },
                    "temporal_scope": "timeless",
                }
            ],
            "required_entities": [
                {
                    "canonical_name": "深圳智航无界科技",
                    "entity_type": "company",
                    "match_policy": "case_scoped_identity",
                }
            ],
            "forbidden_entities": [
                {
                    "canonical_name": "深圳智航无人机有限公司",
                    "entity_type": "company",
                    "match_policy": "case_scoped_identity",
                }
            ],
            "enumeration_policy": {
                "applicable": False,
                "reason": "non_enumeration_turn",
            },
            "stage_oracles": [
                {
                    "stage": "query_understanding",
                    "expectations": [
                        {
                            "hard": True,
                            "observable_kind": "query_interaction",
                            "operator": "equals",
                            "value": "information_retrieval",
                        },
                        {
                            "hard": True,
                            "observable_kind": "protected_slot",
                            "operator": "contains",
                            "value": {"kind": "name", "value": "深圳智航无界科技"},
                        },
                    ],
                }
            ],
        },
    }
    calibration_payload = {
        "sample_id": "cal-v2-ce-001",
        "as_of": "2026-07-15T00:00:00Z",
        "requirement": {
            "predicate": "founded_by",
            "subject_id": "company:example-robotics",
            "value": "professor:founder-1",
        },
        "candidate_observation": {
            "text": "Example Robotics was founded by Professor One.",
            "predicate": "founded_by",
            "subject_id": "company:example-robotics",
            "value": "professor:founder-1",
        },
        "evidence_snapshots": [
            {
                "snippet": "Example Robotics was founded by Professor One.",
                "predicate": "founded_by",
                "subject_id": "company:example-robotics",
                "value": "professor:founder-1",
            }
        ],
        "critical_probe": True,
        "stratum": "claim_evidence",
    }
    harness = f"""
const presentation = require({json.dumps(str(presentation_path))});
console.log(JSON.stringify({{
  contract: presentation.presentContract({json.dumps(contract_payload, ensure_ascii=False)}),
  calibration: presentation.presentCalibration({json.dumps(calibration_payload, ensure_ascii=False)}),
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
    rendered = json.loads(completed.stdout)
    contract_text = json.dumps(rendered["contract"], ensure_ascii=False)
    calibration_text = json.dumps(rendered["calibration"], ensure_ascii=False)

    assert "本项在评什么" in contract_text
    assert "不是判断当前系统答案" in contract_text
    assert "系统需要提供合法、安全指引" in contract_text
    assert "期望值：是" in contract_text
    assert "已接受的政策快照" in contract_text
    assert "必须出现：公司“深圳智航无界科技”" in contract_text
    assert "禁止出现：公司“深圳智航无人机有限公司”" in contract_text
    assert "本案例不是枚举型问题" in contract_text
    assert "系统应将问题识别为信息检索" in contract_text
    assert "通过的前提是以上所有硬性要求都准确" in contract_text
    assert "provides_lawful_safety_guidance" not in contract_text

    assert "本项在评什么" in calibration_text
    assert "候选观察是否被冻结证据支持" in calibration_text
    assert "Example Robotics was founded by Professor One." in calibration_text
    assert "有证据支持：冻结快照直接支持候选观察" in calibration_text
    assert "critical_probe" not in calibration_text
    assert "stratum" not in calibration_text


def test_review_presentation_covers_every_frozen_contract_without_raw_fallback() -> (
    None
):
    presentation_path = STATIC / "review_presentation.js"
    workload_path = (
        ROOT.parents[1]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review"
        / "human-review-workload-v2.json"
    )
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    harness = f"""
const presentation = require({json.dumps(str(presentation_path))});
const contracts = {json.dumps(workload["contract_reviews"], ensure_ascii=False)};
const rendered = contracts.map((contract) => ({{
  caseId: contract.case_id,
  view: presentation.presentContract(contract),
}}));
console.log(JSON.stringify(rendered));
"""

    completed = subprocess.run(
        ["node", "-"],
        input=harness,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    assert len(rendered) == 29
    assert [item["caseId"] for item in rendered if item["view"]["blocksApproval"]] == []
    rendered_text = json.dumps(rendered, ensure_ascii=False)
    assert "[object Object]" not in rendered_text
    assert "页面无法完整翻译" not in rendered_text
    assert "系统不得识别或推测违法场所、商家或类别" in rendered_text
    assert "可接受的安全回应" in rendered_text


def test_review_html_is_semantic_external_and_contains_the_approved_flow() -> None:
    html = (STATIC / "review.html").read_text(encoding="utf-8")

    assert '<main id="review-workbench"' in html
    assert '<aside id="review-queue"' in html
    assert '<section id="review-content"' in html
    assert '<aside id="review-decision"' in html
    assert '<link rel="stylesheet" href="/static/review.css">' in html
    assert (
        '<script src="/static/review_mutation_coordinator.js" defer></script>' in html
    )
    assert '<script src="/static/review_presentation.js" defer></script>' in html
    assert '<script src="/static/review.js" defer></script>' in html
    assert "评审人登记" in html
    assert "合同审核" in html
    assert "排除审核" in html
    assert "盲标校准" in html
    assert "汇总与导出" in html
    assert "仅供评审参考，不是规范性证据" in html
    assert "packet-hash" in html
    assert "judge-status" in html
    assert "autosave-status" in html
    assert "task-mutability-status" in html
    assert "decision-conflict" in html
    assert "server-final-decision" in html
    assert "unsubmitted-draft" in html
    assert "confirm-draft-supersede" in html
    assert "review-summary" in html
    assert "export-dialog" in html

    scripts = re.findall(
        r"<script\b([^>]*)>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert len(scripts) == 3
    assert [
        re.search(r'src="([^"]+)"', attributes).group(1)  # type: ignore[union-attr]
        for attributes, _body in scripts
    ] == [
        "/static/review_mutation_coordinator.js",
        "/static/review_presentation.js",
        "/static/review.js",
    ]
    assert all("defer" in attributes for attributes, _body in scripts)
    assert all(not body.strip() for _attributes, body in scripts)
    assert not re.search(r"<style(?:\s|>)", html)
    assert not re.search(r"\son[a-z]+\s*=", html, flags=re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", html, flags=re.IGNORECASE)


def test_review_javascript_uses_safe_dom_and_server_authoritative_commands() -> None:
    javascript = (STATIC / "review.js").read_text(encoding="utf-8")

    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "eval(",
        "new Function",
        "backend.api.review",
        "DATABASE_URL",
        "Milvus",
    ):
        assert forbidden not in javascript
    for required in (
        "textContent",
        "createElement",
        "replaceChildren",
        'credentials: "same-origin"',
        '"/api/review/sessions"',
        '"/api/review/workspace"',
        '"/api/review/decisions"',
        '"/api/review/calibration/seal"',
        '"/api/review/exports"',
        "crypto.randomUUID",
        "idempotencyKeys",
        "getIdempotencyKey",
        "idempotency_key: key",
        "export:${state.workspace.round_id}:${mode}",
        "beforeunload",
        "setTimeout",
        "response.status === 409",
        "current_revision",
        "judge_configured",
        "artifact_identity",
        "review_context",
        "ReviewPresentation",
        "stage_oracles",
        "再次点击将启动新的评审模型运行",
        "ReviewMutationCoordinator",
        "gate_summary",
        "task.mutable",
        "blocking_task_ids",
        "blocking_reasons",
        "family_coverage",
        "stratum_coverage",
        "authorization_sha256",
        "human_snapshot_sha256",
        "reconcileDecisionPresentation",
        "confirmedDraftTaskId",
        "preserveActionMessage",
        "确认按草稿改判",
    ):
        assert required in javascript
    assert "task.draft?.decision || task.current_decision?.decision" not in javascript
    assert "payload.stratum" not in javascript
    assert "payload.critical_probe" not in javascript
    stale_reload = javascript[javascript.index("const staleError = error") :]
    assert "captured.payload.decision" in stale_reload
    assert "captured.payload.rationale" in stale_reload
    assert "`/api/review/drafts/${encodeURIComponent(captured.taskId)}`" in stale_reload
    autosave_apply = re.search(
        r"\(workspace\) => \{(?P<body>.*?)\n\s*\},\n\s*\);",
        javascript[javascript.index("async function saveDraft") :],
        flags=re.DOTALL,
    )
    assert autosave_apply is not None
    assert "renderDecisionForm(workspace.task)" in autosave_apply.group("body")

    checked = subprocess.run(
        ["node", "--check", str(STATIC / "review.js")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr

    coordinator_checked = subprocess.run(
        ["node", "--check", str(STATIC / "review_mutation_coordinator.js")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert coordinator_checked.returncode == 0, (
        coordinator_checked.stdout + coordinator_checked.stderr
    )

    behavior = subprocess.run(
        [
            "node",
            str(ROOT / "tests" / "js" / "review_mutation_coordinator_test.cjs"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert behavior.returncode == 0, behavior.stdout + behavior.stderr


def test_review_css_has_three_panes_responsive_stack_and_visible_focus() -> None:
    css = (STATIC / "review.css").read_text(encoding="utf-8")

    assert "180px minmax(0, 1fr) 280px" in css
    assert "@media (max-width: 900px)" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "--" in css
    assert "gradient(" not in css
    assert "min-width: 0" in css
    assert "max-width: 100%" in css
    assert "white-space: pre-wrap" in css
    assert "overflow-wrap: anywhere" in css
    assert re.search(
        r"\.review-card li\s*\{[^}]*overflow-wrap:\s*anywhere",
        css,
        flags=re.DOTALL,
    )


def test_workbench_design_matches_active_seal_then_judge_timing() -> None:
    design = (
        ROOT.parents[1]
        / "docs/superpowers/specs/2026-07-24-canonical-v2-human-review-workbench-design.md"
    ).read_text(encoding="utf-8")

    assert (
        "All 60 model decisions are recorded and frozen server-side before the human "
        "calibration phase opens."
    ) not in design
    assert (
        "All 60 model decisions are produced and frozen server-side only when the human "
        "labels are sealed."
    ) in design
