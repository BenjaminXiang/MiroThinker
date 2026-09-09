"""Phase 3 slices 3.1 + 3.2 — bare-name soft subject + typed clarification.

RED fixtures: P3 verbatim form (bare institution name opening must establish
the soft subject; the anti-echo rule must not reject entity-shaped queries)
and G3 form (personal referent over an organization session must produce a
typed clarification, not an org-anchored answer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

service = import_module("backend.services.canonical_v2_chat")

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


class TestBareNameSoftSubject:
    def test_bare_entity_name_query_yields_soft_subject(self) -> None:
        # P3 root: the anti-echo rule (candidate == query → reject) starved
        # bare-name openings of a soft subject, so the follow-up clarified.
        name = service._soft_subject_name(query="国际先进技术应用推进中心（深圳）")
        assert name == "国际先进技术应用推进中心（深圳）"

    def test_bare_company_name_yields_soft_subject(self) -> None:
        assert (
            service._soft_subject_name(query="深圳市优必选科技股份有限公司")
            == "深圳市优必选科技股份有限公司"
        )

    def test_question_query_still_rejected(self) -> None:
        assert service._soft_subject_name(query="深圳有哪些做机器人的公司？") is None

    def test_referent_query_still_rejected(self) -> None:
        assert service._soft_subject_name(query="他有哪些论文") is None


class TestTypedClarification:
    def test_person_referent_over_org_session_clarifies(self) -> None:
        # G3 form after the headline anchor is dropped: org soft subject +
        # person referent must clarify (typed), never answer org content.
        committed = service._CommittedSession(
            answer=None,
            turn_count=1,
            context_receipt=None,
            active_offer=None,
            displayed_ids=(),
            checkpoint=None,
            prior_web_items=(),
            referent_history=(),
            soft_subject_name="国际先进技术应用推进中心（深圳）",
        )
        assert service._referent_clarification_needed(
            query="他有哪些论文", committed=committed
        )

    def test_person_typed_clarification_prompt_names_person_domain(self) -> None:
        response = service._referent_clarification_response("他有哪些论文")
        text = response.answer_text
        assert "教授" in text or "人物" in text or "姓名" in text
