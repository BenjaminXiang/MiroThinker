from __future__ import annotations

from importlib import util
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient


HERE = Path(__file__).resolve().parent
TARGET = HERE / "build_real_data_preview.py"


def _module() -> Any:
    spec = util.spec_from_file_location("canonical_v2_preview_p1_builder", TARGET)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "COMP-3B95F48EB687",
            "object_type": "company",
            "display_name": "深圳森合创新科技有限公司",
            "payload_json_sha256": "1" * 64,
            "last_updated": "2026-07-11T00:00:00Z",
            "quality_status": "ready",
            "core_facts": {
                "name": "深圳森合创新科技有限公司",
                "normalized_name": "深圳森合创新科技",
                "industry": "先进制造",
                "website": "https://oasalife.com",
            },
            "summary_fields": {
                "profile_summary": "一家聚焦家庭机器人的先进制造企业。",
                "technology_route_summary": "技术路线聚焦家用机器人。",
            },
            "evidence": (),
        },
        {
            "id": "PAT-009605B1E383",
            "object_type": "patent",
            "display_name": "底刀调节结构及割草机器人",
            "payload_json_sha256": "2" * 64,
            "last_updated": "2026-07-11T00:00:00Z",
            "quality_status": "ready",
            "core_facts": {
                "title": "底刀调节结构及割草机器人",
                "applicants": ["深圳森合创新科技有限公司"],
                "company_ids": ["COMP-3B95F48EB687"],
                "patent_number": "CN221010838U",
                "patent_type": "实用新型",
                "filing_date": "2023-09-27",
                "publication_date": "2024-05-28",
                "abstract": "通过偏心件调节底刀刀片。",
            },
            "summary_fields": {"summary_text": "该专利涉及割草机器人底刀调节。"},
            "evidence": (),
        },
        {
            "id": "PROF-8000C9F994C3",
            "object_type": "professor",
            "display_name": "丁文伯",
            "payload_json_sha256": "3" * 64,
            "last_updated": "2026-07-11T00:00:00Z",
            "quality_status": "ready",
            "core_facts": {
                "name": "丁文伯",
                "institution": "清华大学深圳国际研究生院",
                "department": "数据与信息研究院",
                "title": "副教授、博士生导师",
                "homepage": "https://www.sigs.tsinghua.edu.cn/dwb/main.htm",
                "research_directions": ["摩擦纳米发电机", "机器人触觉感知"],
                "paper_count": 112,
                "h_index": 36,
                "citation_count": 7910,
            },
            "summary_fields": {"profile_summary": "研究聚焦摩擦纳米发电机与触觉感知。"},
            "evidence": (),
        },
        {
            "id": "PAPER-1258119BC264",
            "object_type": "paper",
            "display_name": "Keystroke dynamics enabled authentication and identification using triboelectric nanogenerator array",
            "payload_json_sha256": "4" * 64,
            "last_updated": "2026-07-11T00:00:00Z",
            "quality_status": "ready",
            "core_facts": {
                "title": "Keystroke dynamics enabled authentication and identification using triboelectric nanogenerator array",
                "authors": ["Changsheng Wu", "Wenbo Ding"],
                "professor_ids": ["PROF-8000C9F994C3"],
                "venue": "Materials Today",
                "year": 2018,
                "doi": "10.1016/j.mattod.2018.01.006",
                "citation_count": 220,
            },
            "summary_fields": {
                "summary_text": (
                    "论文研究击键动力学身份认证；内部来源 PROF-8000C9F994C3。"
                )
            },
            "evidence": (),
        },
        {
            "id": "PROF-PAPER-LINK-00A7B60465F2",
            "object_type": "professor_paper_link",
            "display_name": "丁文伯 -> Keystroke dynamics enabled authentication and identification using triboelectric nanogenerator array",
            "payload_json_sha256": "5" * 64,
            "last_updated": "2026-07-11T00:00:00Z",
            "quality_status": "ready",
            "core_facts": {
                "professor_id": "PROF-8000C9F994C3",
                "paper_id": "PAPER-1258119BC264",
                "link_status": "verified",
            },
            "summary_fields": {},
            "evidence": (),
        },
    )


class _RecordedWeb:
    api_key = "configured"

    def search(self, query: str) -> dict[str, Any]:
        return {
            "organic": [
                {
                    "title": "公开网页结果",
                    "link": "https://example.org/result",
                    "snippet": f"与 {query} 相关的当前网页摘要。",
                }
            ]
        }


def test_real_rows_feed_four_domains_two_relationships_and_no_fixture_names() -> None:
    module = _module()
    app = module.create_preview_app(
        rows=_rows(),
        release_id="preview-p1-real-data",
        web_provider=_RecordedWeb(),
    )
    client = TestClient(app)

    expected = {
        "company": "深圳森合创新科技有限公司",
        "paper": "Keystroke dynamics enabled authentication",
        "patent": "底刀调节结构及割草机器人",
        "professor": "丁文伯",
    }
    for domain, name in expected.items():
        payload = client.get(f"/api/canonical-v2/admin/domains/{domain}").json()
        assert payload["total"] == 1
        assert name in str(payload["items"][0])
        assert "Robotics Co" not in str(payload)
        assert "陈艾达" not in str(payload)

    company = client.get("/api/canonical-v2/admin/domains/company").json()["items"][0]
    related = client.get(
        f"/api/canonical-v2/admin/domains/company/{company['canonical_identity_id']}/related",
        params={"relation_type": "company_has_patent"},
    ).json()
    assert related["items"][0]["title"] == "底刀调节结构及割草机器人"

    professor = client.get("/api/canonical-v2/admin/domains/professor").json()["items"][
        0
    ]
    related = client.get(
        f"/api/canonical-v2/admin/domains/professor/{professor['canonical_identity_id']}/related",
        params={"relation_type": "professor_authored_paper"},
    ).json()
    assert related["items"][0]["title"].startswith("Keystroke dynamics")


def test_chat_executes_local_and_live_web_and_exposes_safe_web_evidence() -> None:
    module = _module()
    app = module.create_preview_app(
        rows=_rows(),
        release_id="preview-p1-real-data",
        web_provider=_RecordedWeb(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={"query": "介绍深圳森合创新科技有限公司并列出其专利"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "深圳森合创新科技有限公司" in payload["answer_text"]
    assert "本轮 Web Search 返回" not in payload["answer_text"]
    assert "网页摘要未自动写入本地事实" not in payload["answer_text"]
    trace = payload["structured_payload"]["canonical_v2"]
    assert trace["lanes"] == ["relationship", "web"]
    assert {item["source_nature"] for item in payload["evidence"]} == {
        "local",
        "current_web",
    }
    web = [
        item for item in payload["evidence"] if item["source_nature"] == "current_web"
    ]
    assert web[0]["source_locator"] == "https://example.org/result"
    assert "configured" not in str(payload)
    assert "Robotics Co" not in str(payload)


def test_web_failure_keeps_local_answer_and_records_limitation() -> None:
    module = _module()

    class FailedWeb:
        api_key = "configured"

        def search(self, query: str) -> dict[str, Any]:
            del query
            raise RuntimeError("provider unavailable")

    client = TestClient(
        module.create_preview_app(
            rows=_rows(),
            release_id="preview-p1-real-data",
            web_provider=FailedWeb(),
        )
    )
    payload = client.post("/api/chat", json={"query": "介绍丁文伯"}).json()
    assert "丁文伯" in payload["answer_text"]
    assert "当前 Web Search 暂未取得" not in payload["answer_text"]
    assert "以上回答仍仅来自本地已验证选择数据" not in payload["answer_text"]
    trace = payload["structured_payload"]["canonical_v2"]
    assert trace["lanes"] == ["exact", "web"]
    assert any(
        item["code"] == "web_provider_unavailable" for item in trace["limitations"]
    )


def test_public_copy_never_exposes_source_ids_hashes_or_raw_enum() -> None:
    module = _module()
    client = TestClient(
        module.create_preview_app(
            rows=_rows(),
            release_id="preview-p1-real-data",
            web_provider=_RecordedWeb(),
        )
    )
    payload = client.post("/api/chat", json={"query": "介绍丁文伯及其论文"}).json()
    public = payload["answer_text"] + str(payload.get("suggested_followups", []))
    assert "PROF-" not in public
    assert "PAPER-" not in public
    assert "professor_attributed_to_paper" not in public
    assert not module.SHA256_PATTERN.search(public)

    for domain in ("company", "paper", "patent", "professor"):
        page = client.get(f"/api/canonical-v2/admin/domains/{domain}").json()
        item = page["items"][0]
        detail = client.get(
            f"/api/canonical-v2/admin/domains/{domain}/{item['canonical_identity_id']}"
        ).json()
        for response_payload in (page, detail):
            serialized = str(response_payload)
            assert "COMP-" not in serialized
            assert "PROF-" not in serialized
            assert "PAPER-" not in serialized
            assert "PAT-" not in serialized
            assert "professor_attributed_to_paper" not in serialized
            assert not module.SHA256_PATTERN.search(serialized)
