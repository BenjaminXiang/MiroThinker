"""Acceptance tests for the light-lane query API.

Locks the three product scenarios promised for Phase 4 plus the P8
reconciliation shape. Runs against the live service on 127.0.0.1:18201.
"""

from __future__ import annotations

import os

from pathlib import Path

import json

import pytest
import httpx

BASE = os.environ.get("LIGHT_LANE_TEST_BASE", "http://127.0.0.1:18201")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=60) as client:
        health = client.get("/healthz")
        assert health.status_code == 200, "light-lane API must be up"
        yield client


def test_health_and_inventory(client):
    inventory = client.get("/api/inventory").json()
    counts = inventory["counts"]
    assert counts["company"] == 6514
    assert counts["patent"] == 11408
    assert counts["paper"] == 24101
    assert counts["professor"] == 3652
    assert counts["prof_paper_link"] == 18655
    assert inventory["applicant_binding"]["resolved"] == 957
    assert inventory["applicant_binding"]["unresolved"] == 1239


def test_scenario_company_patents_ubtech(client):
    """场景1：优必选的专利有哪些 —— 448 条可查，含别名与出处。"""
    detail = client.get(
        "/api/company/深圳市优必选科技股份有限公司"
    ).json()
    assert detail["patent_count"] >= 400
    assert "UBTECH" in detail["aliases"]
    assert detail["sources"], "binding evidence urls must survive"
    assert any("机器人" in p["title"] or "控制" in p["title"] for p in detail["patents"])


def test_scenario_embodied_ai_company_list(client):
    """场景2：深圳做机器人的公司 —— 语义+行业混合检索清单。"""
    results = client.get(
        "/api/search", params={"q": "深圳做机器人的公司", "type": "company", "limit": 8}
    ).json()["results"]
    assert len(results) >= 5
    assert any("机器人" in r["label"] for r in results)


def test_scenario_company_detail_fields(client):
    """场景3：公司详情全字段 —— 成立/法人/行业等在位。"""
    detail = client.get(
        "/api/company/深圳市优必选科技股份有限公司"
    ).json()
    fields = detail["fields"]
    assert fields.get("industry")
    assert fields.get("founded_date")
    assert fields.get("legal_representative")


def test_semantic_search_professor(client):
    results = client.get(
        "/api/search", params={"q": "做电池研究的教授", "type": "professor", "mode": "semantic", "limit": 5}
    ).json()["results"]
    assert results, "semantic professor search must return hits"
    assert all(r["entity_type"] == "professor" for r in results)


def test_keyword_search_patent(client):
    results = client.get(
        "/api/search", params={"q": "机器人", "type": "patent", "mode": "keyword", "limit": 5}
    ).json()["results"]
    assert len(results) == 5
    # 申请人名含"机器人"而标题不含的命中是合法的（匹配可来自申请人）
    assert sum("机器人" in r["label"] for r in results) >= 3


def test_professor_detail_with_public_links(client):
    """教授详情：论文列表带可复原公开出处（DOI）。"""
    detail = client.get(
        "/api/professor/PROF-00248146798C"
    ).json()
    assert detail["paper_count"] >= 1
    assert any(p["public_link"] for p in detail["papers"])


def test_paper_detail_public_link(client):
    inventory_paper = client.get(
        "/api/search", params={"q": "battery", "type": "paper", "limit": 1}
    ).json()["results"]
    assert inventory_paper
    detail = client.get(f"/api/paper/{inventory_paper[0]['entity_id']}").json()
    assert detail["authors"]


def test_patent_detail_applicant_resolution(client):
    detail = client.get("/api/patent/PAT-002313250DD5").json()
    assert detail["fields"]["title"]
    applicants = detail["applicants"]
    assert applicants, "patent detail must list applicants"


def test_missing_entity_returns_404(client):
    response = client.get("/api/professor/PROF-DOES-NOT-EXIST")
    assert response.status_code == 404


def test_placeholder_contact_fields_not_shown(client):
    """P10：占位符不当真值 —— 详情字段过滤掉 '-'/'空'。"""
    detail = client.get(
        "/api/company/深圳市优必选科技股份有限公司"
    ).json()
    for value in detail["fields"].values():
        assert value != "-"


# ---------------------------------------------------------------------------
# Grounded QA (/api/ask) — loose assertions: LLM wording varies, structure
# and grounding must not.
# ---------------------------------------------------------------------------


def test_qa_company_patents(client):
    payload = client.get(
        "/api/ask", params={"q": "优必选有哪些专利"}
    ).json()
    assert payload["grounded"] is True
    answer = payload["answer"]
    assert "448" in answer, "must cite the exact patent count"
    assert "优必选" in answer
    assert any("CN" in s["url"] or s["url"].startswith("http") for s in payload["sources"])


def test_qa_company_list(client):
    payload = client.get(
        "/api/ask", params={"q": "深圳做机器人的公司有哪些"}
    ).json()
    assert payload["grounded"] is True
    answer = payload["answer"]
    assert "机器人" in answer
    assert sum("深圳" in line or "有限" in line for line in answer.splitlines()) >= 3


def test_qa_contact_info(client):
    payload = client.get(
        "/api/ask", params={"q": "优必选的联系方式"}
    ).json()
    assert payload["grounded"] is True
    answer = payload["answer"]
    assert ("@" in answer or "公开渠道" in answer), (
        "either real contact info or the P10 no-contact phrasing"
    )
    import re
    assert not re.search(r"[:：]\s*[-—]\s*$", answer, re.MULTILINE), (
        "placeholder-only field values must never surface"
    )


def test_qa_professor_papers(client):
    """G2/G4 形：教授论文问答（简称生效、计数与样例齐全）。"""
    payload = client.get(
        "/api/ask", params={"q": "杨贤有哪些论文"}
    ).json()
    assert payload["grounded"] is True
    answer = payload["answer"]
    assert "33" in answer
    assert "论文" in answer


# ---------------------------------------------------------------------------
# Admin config interface (/api/admin/*)
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def _restore_config(original: str | None):
    if original is None:
        CONFIG_PATH.unlink(missing_ok=True)
    else:
        CONFIG_PATH.write_text(original)


def test_admin_config_masks_secrets(client):
    payload = client.get("/api/admin/config").json()
    for key in ("embed_key", "chat_key"):
        value = payload[key]
        assert value == "" or value.startswith("***")


def test_admin_config_update_persists_and_applies(client):
    original = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else None
    try:
        response = client.put(
            "/api/admin/config", json={"embed_model": "probe-model-x"}
        ).json()
        assert response["saved"] == ["embed_model"]
        stored = json.loads(CONFIG_PATH.read_text())
        assert stored["embed_model"] == "probe-model-x"
        assert client.get("/api/admin/config").json()["embed_model"] == "probe-model-x"
        client.put("/api/admin/config", json={"embed_model": ""} if False else {"embed_model": "Qwen/Qwen3-Embedding-8B"})
    finally:
        _restore_config(original)


def test_admin_config_rejects_unknown_fields(client):
    response = client.put("/api/admin/config", json={"evil_field": "x"})
    assert response.status_code == 400


def test_admin_probe_reports_both_components(client):
    payload = client.post("/api/admin/config/test").json()
    assert set(payload) == {"embed", "chat"}
    assert isinstance(payload["embed"]["ok"], bool)
    assert isinstance(payload["chat"]["ok"], bool)
    assert "dimension" in payload["embed"]
    assert "latency_ms" in payload["chat"]


def test_admin_token_enforced_when_set(client):
    original = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else None
    try:
        client.put("/api/admin/config", json={"admin_token": "secret-tok"})
        wrong = client.get(
            "/api/admin/config", headers={"X-Admin-Token": "nope"}
        )
        assert wrong.status_code == 403
        right = client.get(
            "/api/admin/config", headers={"X-Admin-Token": "secret-tok"}
        )
        assert right.status_code == 200
    finally:
        client.put("/api/admin/config", json={"admin_token": ""})
        _restore_config(original)
