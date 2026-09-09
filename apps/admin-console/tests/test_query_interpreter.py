"""Phase 6 — contextual query interpreter tests (RED-first).

Unit tests for the interpreter module: validation checklist with the
G1-T3 fixture, hallucination fixture, and the isolation properties.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

interp = import_module(
    "backend.services.canonical_v2_query_interpreter"
)
chat = import_module("backend.services.canonical_v2_chat")

G1_SUBJECT = "国际先进技术应用推进中心（深圳）"
HALLUCINATED = "张三丰"
HEADLINE = "河套深圳园区打造深港科技创新聚集地 - 香港中联办"


def _make(subject_name: str, *, confidence: float = 0.8, intent: str = "deepen") -> Any:
    return interp.Interpretation(
        subject_ref=(
            interp.SubjectRef(name=subject_name, source="anchor", evidence_quote="query context")
            if subject_name
            else None
        ),
        intent=intent,
        self_contained_query="self-contained version",
        confidence=confidence,
        referent_kind="singular",
    )


class TestValidation:
    def test_g1_t3_fixture_passes(self) -> None:
        result = interp.validate_interpretation(
            _make(G1_SUBJECT),
            query="它有哪些布局和进展",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=False,
        )
        assert result is not None
        assert result.subject_ref is not None
        assert result.subject_ref.name == G1_SUBJECT

    def test_hallucinated_subject_rejected(self) -> None:
        result = interp.validate_interpretation(
            _make(HALLUCINATED),
            query="他有哪些论文",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=False,
        )
        assert result is None

    def test_headline_rejected(self) -> None:
        assert chat.is_headline_shaped_name(HEADLINE)
        result = interp.validate_interpretation(
            _make(HEADLINE),
            query="它是什么",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=False,
        )
        assert result is None

    def test_low_confidence_rejected(self) -> None:
        result = interp.validate_interpretation(
            _make(G1_SUBJECT, confidence=0.5),
            query="它有哪些布局和进展",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=False,
        )
        assert result is None

    def test_enumeration_never_single_subject(self) -> None:
        result = interp.validate_interpretation(
            _make(G1_SUBJECT, intent="deepen"),
            query="深圳有哪些做具身智能的公司",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=True,
        )
        assert result is None

    def test_enumeration_intent_ok(self) -> None:
        result = interp.validate_interpretation(
            interp.Interpretation(
                subject_ref=None,
                intent="enumerate",
                self_contained_query="深圳有哪些做具身智能的公司",
                confidence=0.9,
                referent_kind="none",
            ),
            query="深圳有哪些做具身智能的公司",
            session_manifest_names=(),
            query_is_enumeration=True,
        )
        assert result is not None

    def test_explicit_named_subject_veto(self) -> None:
        """Query names 云迹科技 explicitly; interpretation resolves to anchor
        (different subject) → veto."""
        result = interp.validate_interpretation(
            _make(G1_SUBJECT),
            query="介绍一下云迹科技",
            session_manifest_names=(G1_SUBJECT, "云迹科技"),
            query_is_enumeration=False,
        )
        assert result is None

    def test_named_in_query_ok(self) -> None:
        """Subject explicitly named in query is valid even if not in manifest."""
        result = interp.validate_interpretation(
            interp.Interpretation(
                subject_ref=interp.SubjectRef(
                    name="新成立的公司XYZ", source="query_named"
                ),
                intent="profile",
                self_contained_query="介绍一下新成立的公司XYZ",
                confidence=0.85,
                referent_kind="none",
            ),
            query="介绍一下新成立的公司XYZ",
            session_manifest_names=(G1_SUBJECT,),
            query_is_enumeration=False,
        )
        assert result is not None


class TestInterpreterIsolation:
    def test_disabled_returns_none(self, monkeypatch) -> None:
        monkeypatch.delenv("CHAT_CONTEXTUAL_INTERPRETATION", raising=False)
        interpreter = interp.ContextualQueryInterpreter()
        assert (
            interpreter.interpret(
                query="它有哪些布局和进展",
                manifest_names=(G1_SUBJECT,),
            )
            is None
        )

    def test_timeout_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("CHAT_CONTEXTUAL_INTERPRETATION", "on")
        import time

        class _SlowClient:
            def __init__(self):
                self.chat = type("C", (), {})()

            class _Completions:
                def create(self, **_: Any) -> Any:
                    time.sleep(3.0)
                    return None

        interpreter = interp.ContextualQueryInterpreter(timeout_seconds=0.1)
        # Don't actually call the LLM; just verify timeout via a mock
        interpreter._llm_call = lambda *a, **kw: (_ for _ in ()).throw(
            TimeoutError("simulated")
        )
        assert (
            interpreter.interpret(
                query="它有哪些布局和进展",
                manifest_names=(G1_SUBJECT,),
            )
            is None
        )
