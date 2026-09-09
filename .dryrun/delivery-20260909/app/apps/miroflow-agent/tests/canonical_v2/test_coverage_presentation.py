"""Presentation-layer tests for enumeration coverage disclosure.

Contract: openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/
grounded-progressive-answer/spec.md, requirement "List answers expose
enumeration coverage". Both render paths must surface the enumeration
accounting: the LLM prose call receives an ``enumeration_coverage`` payload
section plus a disclosure instruction, and the deterministic/fallback answer
text carries a factual coverage sentence. A representative list must never
read as exhaustive.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace
from typing import Any

from src.data_agents.canonical_v2 import knowledge_answer as answer_module
from src.data_agents.canonical_v2 import knowledge_read as read_module
from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module

NOW = datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
RELEASE_ID = "candidate-coverage-presentation"
QUERY = "丁文伯有哪些论文"
CLAIM_TEXT = "丁文伯的论文包括 pFedGPA。"


def _item() -> Any:
    return read_module.EvidenceItem(
        evidence_id="evidence:coverage:paper-pfedgpa",
        object_id="paper-c-pfedgpa",
        domain="paper",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:paper-c-pfedgpa",
        snippet="pFedGPA 是丁文伯的论文之一。",
        score=1.0,
        source_authority="canonical_release",
        observed_at=NOW,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id="paper-c-pfedgpa",
            predicate="representative_work",
            value="pFedGPA",
            status="supported",
        ),
    )


def _coverage(
    *,
    mode: str,
    retrieved_count: int,
    displayed_count: int,
    exhaustive: bool,
    unknown_scope: bool,
) -> Any:
    return read_module.EnumerationCoverage(
        mode=mode,
        scope=QUERY,
        as_of=NOW,
        checked_ids=(),
        eligible_ids=(),
        retrieved_ids=(),
        displayed_ids=(),
        omitted_ids=(),
        unknown_ids=(),
        unknown_scope=unknown_scope,
        checked_count=retrieved_count,
        eligible_count=retrieved_count,
        retrieved_count=retrieved_count,
        displayed_count=displayed_count,
        omitted_count=0,
        unknown_count=(None if unknown_scope else 0),
        exhaustive=exhaustive,
        accounting_complete=True,
        required_member_outcomes=(),
        continuation_state=("open_world" if unknown_scope else "complete"),
        continuation_required=unknown_scope,
    )


def _evidence_set(coverage: Any | None) -> Any:
    return read_module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=QUERY,
        protected_slots=(),
        items=(_item(),),
        traces=(),
        limitations=(),
        enumeration_coverage=coverage,
    )


def _request(evidence_set: Any, *, turn_id: str) -> Any:
    return answer_module.TurnRequest(
        session_id=f"session:coverage-presentation:{turn_id}",
        turn_id=turn_id,
        query=evidence_set.original_query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
    )


def _selector(request: Any) -> Any:
    item = request.evidence_set.items[0]
    binding = item.claim_binding
    assert binding is not None
    return answer_module.AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:{request.turn_id}",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text="NON_AUTHORITATIVE_RAW_DRAFT",
        claims=(
            answer_module.MaterialClaimProposal(
                claim_id="claim:coverage:pfedgpa",
                text=CLAIM_TEXT,
                subject_id=binding.subject_id,
                predicate=binding.predicate,
                value=binding.value,
                subject_handle_ids=(binding.subject_id,),
                evidence_ids=(item.evidence_id,),
                status=binding.status,
            ),
        ),
    )


class _Completions:
    """Hermetic chat-completions fake that captures each request payload."""

    def __init__(self, calls: list[dict[str, Any]], answer_text: str) -> None:
        self._calls = calls
        self._answer_text = answer_text

    def create(self, **kwargs: object) -> object:
        self._calls.append(kwargs)
        return SimpleNamespace(
            choices=(
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "<|canonical_v2_selection_v1|>\n"
                            + json.dumps(
                                {
                                    "selected_claim_indexes": [1],
                                    "selected_entity_indexes": [],
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            + "\n<|canonical_v2_answer_v1|>\n"
                            + self._answer_text
                        )
                    )
                ),
            )
        )


def _capturing_renderer(calls: list[dict[str, Any]], *, answer_text: str) -> Any:
    return serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions(calls, answer_text))
        ),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )


def _timeout_renderer(_: Any) -> str:
    raise TimeoutError("test-owned prose renderer is unavailable")


def _user_payload(calls: list[dict[str, Any]]) -> Any:
    assert len(calls) == 1
    messages = calls[0]["messages"]
    assert isinstance(messages, list)
    return json.loads(messages[1]["content"])


def test_representative_list_answer_prose_payload_carries_coverage_accounting() -> (
    None
):
    calls: list[dict[str, Any]] = []
    coverage = _coverage(
        mode="representative",
        retrieved_count=21,
        displayed_count=13,
        exhaustive=False,
        unknown_scope=True,
    )

    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=_selector,
        prose_renderer=_capturing_renderer(calls, answer_text=CLAIM_TEXT),
    ).answer(_request(_evidence_set(coverage), turn_id="turn:prose-representative"))

    assert result.render_mode == "prose_renderer"
    assert result.answer_text == CLAIM_TEXT
    messages = calls[0]["messages"]
    system_content = messages[0]["content"]
    assert "representative" in system_content
    assert "有代表性的 M 个" in system_content
    assert "严禁暗示已穷尽" in system_content
    payload = _user_payload(calls)
    coverage_payload = payload["enumeration_coverage"]
    assert coverage_payload["mode"] == "representative"
    assert coverage_payload["scope"] == QUERY
    assert coverage_payload["as_of"] == NOW.isoformat()
    assert coverage_payload["checked_count"] == 21
    assert coverage_payload["eligible_count"] == 21
    assert coverage_payload["retrieved_count"] == 21
    assert coverage_payload["displayed_count"] == 13
    assert coverage_payload["omitted_count"] == 0
    assert coverage_payload["unknown_scope"] is True
    assert coverage_payload["exhaustive"] is False
    assert "unknown_count" not in coverage_payload
    assert coverage_payload["omitted_members"] == []
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "paper-c-pfedgpa" not in serialized
    assert "evidence:coverage" not in serialized


def test_deterministic_fallback_discloses_representative_coverage_counts() -> None:
    coverage = _coverage(
        mode="representative",
        retrieved_count=21,
        displayed_count=13,
        exhaustive=False,
        unknown_scope=True,
    )

    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=_selector,
        prose_renderer=_timeout_renderer,
    ).answer(
        _request(_evidence_set(coverage), turn_id="turn:deterministic-representative")
    )

    assert result.render_mode == "deterministic_fallback"
    sentence = "共检索到 21 个相关结果，本次展示其中 13 个，为代表性结果而非穷尽列表。"
    assert sentence in result.answer_text
    assert result.answer_text.count(sentence) == 1
    assert f"- {CLAIM_TEXT}" in result.answer_text


def test_exhaustive_bounded_coverage_gets_no_representative_disclosure() -> None:
    coverage = _coverage(
        mode="exhaustive_bounded",
        retrieved_count=5,
        displayed_count=5,
        exhaustive=True,
        unknown_scope=False,
    )

    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=_selector,
        prose_renderer=None,
    ).answer(
        _request(_evidence_set(coverage), turn_id="turn:deterministic-exhaustive")
    )

    assert result.render_mode == "deterministic_grounded"
    assert result.enumeration_coverage is not None
    assert result.enumeration_coverage.mode == "exhaustive_bounded"
    assert result.answer_text == f"- {CLAIM_TEXT}"
    assert "代表性" not in result.answer_text
    assert "穷尽" not in result.answer_text


def test_missing_coverage_leaves_both_render_paths_unchanged() -> None:
    calls: list[dict[str, Any]] = []
    prose_result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=_selector,
        prose_renderer=_capturing_renderer(calls, answer_text=CLAIM_TEXT),
    ).answer(_request(_evidence_set(None), turn_id="turn:prose-no-coverage"))

    assert prose_result.render_mode == "prose_renderer"
    assert prose_result.answer_text == CLAIM_TEXT
    assert _user_payload(calls)["enumeration_coverage"] is None

    deterministic_result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=_selector,
        prose_renderer=None,
    ).answer(_request(_evidence_set(None), turn_id="turn:deterministic-no-coverage"))

    assert deterministic_result.render_mode == "deterministic_grounded"
    assert deterministic_result.answer_text == f"- {CLAIM_TEXT}"
    assert "穷尽" not in deterministic_result.answer_text
