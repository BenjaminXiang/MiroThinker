"""Phase 3 — deterministic subject layer hardening (RED-first).

Slice 3.4: news-headline anchor guard. Fixtures are the verbatim G1 headline
and real entity names as negatives; the sanitize hole (web handles never
dropped) is the RED surface.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

service = import_module("backend.services.canonical_v2_chat")
answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")

G1_HEADLINE = "河套深圳园区打造深港科技创新聚集地 - 香港中联办"
REAL_ENTITIES = (
    "深圳市优必选科技股份有限公司",
    "中国建设银行",
    "国际先进技术应用推进中心（深圳）",
    "云迹科技",
)


class TestHeadlineDetector:
    def test_g1_verbatim_headline_detected(self) -> None:
        assert service.is_headline_shaped_name(G1_HEADLINE)

    def test_event_verb_headline_detected(self) -> None:
        assert service.is_headline_shaped_name("优必选发布新一代人形机器人Walker S2")

    def test_real_entity_names_not_flagged(self) -> None:
        for name in REAL_ENTITIES:
            assert not service.is_headline_shaped_name(name), name


def _web_receipt(display_name: str) -> Any:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    handle = read_module.WebEntityHandle(
        handle_id="web-handle:1",
        domain="company",
        display_name=display_name,
        evidence_snapshot_ids=(),
        evidence_ids=("evidence:web:1",),
        resolution_state="accepted",
        candidate_canonical_ids=(),
        originating_query="介绍 国际先进技术应用推进中心（深圳）",
        origin_lane="web",
        origin_attempt=1,
    )
    return answer_module.ContextReceipt(active_anchor=handle)


class TestHeadlineAnchorGuard:
    def test_headline_web_anchor_dropped_on_soft_turn(self) -> None:
        receipt = service._sanitize_soft_turn_anchor(
            _web_receipt(G1_HEADLINE),
            planned_displayed_ids=(),
            soft_context_subject="国际先进技术应用推进中心（深圳）",
        )
        assert receipt is not None
        assert receipt.active_anchor is None

    def test_real_company_web_anchor_survives(self) -> None:
        receipt_input = _web_receipt("深圳市优必选科技股份有限公司")
        receipt = service._sanitize_soft_turn_anchor(
            receipt_input,
            planned_displayed_ids=(),
            soft_context_subject="优必选",
        )
        assert receipt is not None
        assert receipt.active_anchor is receipt_input.active_anchor

    def test_canonical_anchor_path_unchanged(self) -> None:
        # The pre-existing canonical-name-mismatch drop must keep working.
        read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
        canonical = read_module.CanonicalEntityHandle(
            canonical_id="company-c-yunji",
            domain="company",
            display_name="云迹科技",
            evidence_ids=("evidence:1",),
        )
        receipt = service._sanitize_soft_turn_anchor(
            answer_module.ContextReceipt(active_anchor=canonical),
            planned_displayed_ids=(),
            soft_context_subject="毫不相干的其他主体名",
        )
        assert receipt is not None
        assert receipt.active_anchor is None
