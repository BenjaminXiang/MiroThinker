# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.data_agents.professor.model_quality_gate import evaluate_model_quality_gate
from src.data_agents.professor.quality_gate import (
    ProfessorAffiliationState,
    ProfessorCanonicalState,
    ProfessorFactState,
    SourcePageState,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 21, hour, tzinfo=timezone.utc)


def _state(**overrides: object) -> ProfessorCanonicalState:
    summary = (
        "吴亚北现任南方科技大学物理系教授，长期从事二维材料、电子结构与低维量子体系研究。"
        "其工作围绕材料表界面调控、能带结构分析和器件物理机制展开，结合实验表征与理论建模，"
        "为新型功能材料和电子器件设计提供可验证依据。相关成果体现出稳定的研究方向和清晰的学术产出。"
        "公开主页能够支撑其身份、研究主题和代表性论文之间的关联，适合作为教师核心资料的完整样例。"
        "其研究脉络、任职信息与论文摘要相互印证，具备进入发布库所需的基础可读性和可追溯性。"
    )
    defaults = {
        "professor_id": "PROF-READY",
        "canonical_name": "吴亚北",
        "identity_status": "resolved",
        "profile_summary": summary,
        "paper_summary": "代表论文围绕二维材料电子结构、低维量子体系与器件物理展开。",
        "profile_raw_text": "吴亚北，南方科技大学物理系教授。研究方向：二维材料、电子结构。",
        "updated_at": _dt(9),
        "source_pages": (
            SourcePageState(
                page_id="PAGE-1",
                url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
                is_official_source=True,
            ),
        ),
        "affiliations": (
            ProfessorAffiliationState(
                institution="南方科技大学",
                department="物理系",
                title="教授",
                is_primary=True,
                is_current=True,
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
        ),
        "facts": (
            ProfessorFactState(
                fact_type="research_topic",
                value_raw="二维材料",
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
        ),
        "has_paper_candidates": True,
        "has_verified_paper_signal": True,
    }
    defaults.update(overrides)
    return ProfessorCanonicalState(**defaults)


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self.content)),
            ],
            usage=SimpleNamespace(
                prompt_tokens=123,
                completion_tokens=45,
                total_tokens=168,
            ),
        )


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


def test_model_quality_gate_promotes_ready_candidate_when_model_passes() -> None:
    llm = _FakeLLM(
        '{"publishable": true, "confidence": 0.91, '
        '"reason_codes": [], "rationale": "身份、摘要和研究方向均有官方资料支撑。"}'
    )

    result = evaluate_model_quality_gate(
        _state(),
        llm_client=llm,
        llm_model="fake-model",
    )

    assert result.model_called is True
    assert result.base_quality_status == "ready"
    assert result.final_quality_status == "ready"
    assert result.decision is not None
    assert result.decision.usage["total_tokens"] == 168
    assert llm.completions.calls[0]["model"] == "fake-model"


def test_model_quality_gate_skips_when_deterministic_gate_is_not_ready() -> None:
    llm = _FakeLLM(
        '{"publishable": true, "confidence": 0.99, '
        '"reason_codes": [], "rationale": "should not be called"}'
    )

    result = evaluate_model_quality_gate(
        _state(facts=()),
        llm_client=llm,
        llm_model="fake-model",
    )

    assert result.model_called is False
    assert result.final_quality_status == "needs_enrichment"
    assert result.skip_reason == "base_gate_needs_enrichment"
    assert llm.completions.calls == []


def test_model_quality_gate_keeps_low_confidence_decision_in_review() -> None:
    llm = _FakeLLM(
        '{"publishable": true, "confidence": 0.42, '
        '"reason_codes": ["weak_evidence"], "rationale": "官方资料支撑不足。"}'
    )

    result = evaluate_model_quality_gate(
        _state(),
        llm_client=llm,
        llm_model="fake-model",
    )

    assert result.model_called is True
    assert result.final_quality_status == "needs_review"
    assert result.decision is not None
    assert result.decision.reason_codes == ("weak_evidence",)


def test_model_quality_gate_keeps_malformed_response_in_review() -> None:
    llm = _FakeLLM("not json")

    result = evaluate_model_quality_gate(
        _state(),
        llm_client=llm,
        llm_model="fake-model",
    )

    assert result.model_called is True
    assert result.final_quality_status == "needs_review"
    assert result.decision is not None
    assert result.decision.reason_codes == ("malformed_model_response",)
