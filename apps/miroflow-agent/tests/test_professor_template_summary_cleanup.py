"""Template summaries: stop generating them and keep them out of claims."""

from __future__ import annotations

from src.data_agents.canonical_v2.knowledge_read import EvidenceItem
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    _drop_filler_sentences,
    _semantic_text,
)
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.pipeline_v2 import _build_fallback_summary

FILLER = "该教授在深圳科创领域有持续贡献。"


def test_fallback_summary_no_longer_pads() -> None:
    profile = EnrichedProfessorProfile(
        name="王伟",
        institution="清华大学深圳国际研究生院",
        title="教授",
        profile_url="https://example.edu/~wang",
        roster_source="manual",
        extraction_status="ok",
    )

    summary = _build_fallback_summary(profile)

    assert FILLER not in summary
    assert summary.startswith("王伟现任清华大学深圳国际研究生院")
    assert len(summary) < 200


def test_fallback_summary_keeps_facts() -> None:
    profile = EnrichedProfessorProfile(
        name="王伟",
        institution="清华大学深圳国际研究生院",
        profile_url="https://example.edu/~wang",
        roster_source="manual",
        extraction_status="ok",
        research_directions=["机器人控制"],
        h_index=12,
    )

    summary = _build_fallback_summary(profile)

    assert "机器人控制" in summary
    assert "h-index为12" in summary


def test_filler_sentences_are_dropped() -> None:
    text = f"白冠华研究相分离。{FILLER}研究成果具有重要学术价值。他还在南科大任教。"

    cleaned = _drop_filler_sentences(text)

    assert cleaned == "白冠华研究相分离。他还在南科大任教。"


def test_filler_filter_keeps_unrelated_text() -> None:
    assert _drop_filler_sentences("她研究机器人控制。") == "她研究机器人控制。"
    assert _drop_filler_sentences("") == ""


def test_claim_rendering_drops_template_summary() -> None:
    item = EvidenceItem(
        evidence_id="e",
        object_id="p1",
        domain="professor",
        lane="exact",
        source_nature="local",
        source_locator="lookup",
        snippet=(
            '{"name": "王伟", "profile_summary": "'
            + FILLER * 3
            + '王伟研究机器人控制。"}'
        ),
        score=1.0,
    )

    text = _semantic_text(item, "王伟")

    assert "持续贡献" not in text
    assert "机器人控制" in text
