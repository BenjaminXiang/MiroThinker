"""Phase 2 — never-refuse wording contracts (RED-first).

Deterministic guards are pure functions over (answer_text, evidence signals);
the RED cases come from verbatim user transcripts (P2 G2 refusal family,
P5 G4 deflection) and the lane-outage wording rule (2.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

service = import_module("backend.services.canonical_v2_chat")

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


class TestNeverRefuseFallback:
    def test_fallback_names_subject_and_gap_not_refusal(self) -> None:
        text = service._soft_fallback_answer_text("云迹科技", domain="company")
        assert "云迹科技" in text.split("。")[0]
        assert "换个角度" not in text
        assert "暂未能确认您问的具体内容" not in text
        # contract form: names what is confirmed AND names the coverage gap
        assert "已确认" in text or "确认" in text
        assert "暂未" in text or "未覆盖" in text

    def test_fallback_without_anchor_still_actionable(self) -> None:
        text = service._soft_fallback_answer_text(None, domain=None)
        assert "换个角度" not in text
        assert "暂未能确认您问的具体内容" not in text
        assert len(text) > 20

    def test_fallback_web_ran_mentions_both_channels(self) -> None:
        text = service._soft_fallback_answer_text(
            "深圳市优必选科技股份有限公司",
            domain="patent",
            web_state="ran",
        )
        # User feedback 2026-08-18: the system has web search; the fallback
        # must never present itself as local-only when the web lane ran.
        assert "网络检索" in text
        assert "本地知识库" in text
        assert "不代表该信息不存在" in text

    def test_fallback_web_unavailable_names_outage(self) -> None:
        text = service._soft_fallback_answer_text(
            "深圳市优必选科技股份有限公司",
            domain="patent",
            web_state="unavailable",
        )
        assert "网络检索暂不可用" in text
        assert "恢复后" in text


class TestDeflectionGuard:
    def _evidence(self, patent_count: int) -> Any:
        read_module = import_module(
            "src.data_agents.canonical_v2.knowledge_read"
        )
        return read_module.EvidenceSet(
            release_id="r",
            original_query="q",
            protected_slots=(),
            items=(),
            traces=(
                read_module.RetrievalTrace(
                    query_view="v",
                    lane="relationship",
                    attempt=1,
                    release_id="r",
                    candidate_count=patent_count,
                ),
            ),
            limitations=(),
            entity_handles=(),
        )

    def test_patent_deflection_rewritten_with_anchor(self) -> None:
        verbatim = (
            "未找到深圳市优必选科技股份有限公司的专利信息，"
            "建议访问国家知识产权局或 PatSnap 查询完整专利。"
        )
        rewritten = service._rewrite_deflection_answer_text(
            verbatim,
            patent_evidence_count=0,
            anchor_name="深圳市优必选科技股份有限公司",
        )
        assert "国家知识产权局" not in rewritten
        assert "PatSnap" not in rewritten
        assert "优必选" in rewritten
        assert "专利" in rewritten  # the gap is named, not dodged

    def test_no_rewrite_when_patent_evidence_exists(self) -> None:
        verbatim = "该公司拥有 12 项专利；更多细节建议访问国家知识产权局核对。"
        rewritten = service._rewrite_deflection_answer_text(
            verbatim,
            patent_evidence_count=12,
            anchor_name="深圳市优必选科技股份有限公司",
        )
        assert rewritten == verbatim  # grounded recommendation stays


class TestLaneFailureSemantics:
    def test_world_negative_claim_rewritten_on_outage(self) -> None:
        claim = "未找到该机构的相关信息。"
        rewritten = service._rewrite_lane_outage_answer_text(
            claim, anchor_name="国际先进技术应用推进中心（深圳）"
        )
        assert "网络检索暂不可用" in rewritten
        assert "未找到" not in rewritten
        assert "国际先进技术应用推进中心" in rewritten

    def test_normal_answer_untouched(self) -> None:
        answer = "云迹科技是一家酒店服务机器人公司，总部位于北京。"
        assert (
            service._rewrite_lane_outage_answer_text(answer, anchor_name="云迹科技")
            == answer
        )

    def test_web_lane_unavailable_detected_from_traces(self) -> None:
        read_module = import_module(
            "src.data_agents.canonical_v2.knowledge_read"
        )
        failed_web = read_module.RetrievalTrace(
            query_view="v", lane="web", attempt=1, release_id="r",
            candidate_count=0, status="failed", failure_kind="provider_error",
        )
        assert service._web_lane_unavailable_from_traces((failed_web,))
        healthy = read_module.RetrievalTrace(
            query_view="v", lane="web", attempt=1, release_id="r",
            candidate_count=5,
        )
        assert not service._web_lane_unavailable_from_traces((healthy,))
        assert not service._web_lane_unavailable_from_traces(())
