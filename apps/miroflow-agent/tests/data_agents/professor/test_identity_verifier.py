# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for identity verifier — LLM-based same-person verification."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.identity_verifier import (
    IdentityVerification,
    ProfessorContext,
    verify_identity,
)


def _make_context(**kwargs) -> ProfessorContext:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        email="lizhi@sustech.edu.cn",
        research_directions=["机器学习", "计算机视觉"],
    )
    defaults.update(kwargs)
    return ProfessorContext(**defaults)


def _mock_llm_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return mock


@pytest.mark.asyncio
class TestVerifyIdentity:
    """Test identity verification."""

    async def test_same_person_high_confidence(self):
        """Same person, high confidence → is_same_person=True."""
        llm_response = json.dumps({
            "is_same_person": True,
            "confidence": 0.95,
            "matching_signals": ["name_match", "institution_match", "email_match"],
            "conflicting_signals": [],
            "reasoning": "Name, institution, and email all match exactly.",
        })
        llm = _mock_llm_response(f"```json\n{llm_response}\n```")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/lizhi",
            page_content="李志，南方科技大学教授，研究方向：机器学习。邮箱：lizhi@sustech.edu.cn",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is True
        assert result.confidence >= 0.8

    async def test_different_person_same_name(self):
        """Different person with same name → is_same_person=False."""
        llm_response = json.dumps({
            "is_same_person": False,
            "confidence": 0.3,
            "matching_signals": ["name_match"],
            "conflicting_signals": ["different_institution", "different_field"],
            "reasoning": "Same name but different university and research field.",
        })
        llm = _mock_llm_response(f"```json\n{llm_response}\n```")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/lizhi-other",
            page_content="李志，北京大学教授，研究方向：古代文学。",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is False

    async def test_confidence_exactly_0_8_accepted(self):
        """Confidence exactly 0.8 → accepted."""
        llm_response = json.dumps({
            "is_same_person": True,
            "confidence": 0.8,
            "matching_signals": ["name_match", "institution_match"],
            "conflicting_signals": [],
            "reasoning": "Moderately confident.",
        })
        llm = _mock_llm_response(f"```json\n{llm_response}\n```")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/lizhi",
            page_content="李志教授在南方科技大学工作。",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is True
        assert result.confidence == 0.8

    async def test_confidence_0_79_rejected(self):
        """Confidence 0.79 → rejected despite LLM saying is_same_person=True."""
        llm_response = json.dumps({
            "is_same_person": True,
            "confidence": 0.79,
            "matching_signals": ["name_match"],
            "conflicting_signals": ["unclear_institution"],
            "reasoning": "Name matches but institution not confirmed.",
        })
        llm = _mock_llm_response(f"```json\n{llm_response}\n```")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/lizhi",
            page_content="李志教授的一篇论文。",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is False
        assert result.confidence == 0.79

    async def test_empty_page_content(self):
        """Empty page content → is_same_person=False, confidence=0.0."""
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/empty",
            page_content="",
            llm_client=MagicMock(),
            llm_model="test",
        )
        assert result.is_same_person is False
        assert result.confidence == 0.0

    async def test_malformed_json_returns_false(self):
        """LLM returns malformed JSON → is_same_person=False."""
        llm = _mock_llm_response("This is not JSON at all!")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/page",
            page_content="Some page content about a professor.",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is False
        assert result.error is not None

    async def test_llm_exception_returns_false(self):
        """LLM client throws exception → is_same_person=False."""
        llm = MagicMock()
        llm.chat.completions.create.side_effect = RuntimeError("API error")
        ctx = _make_context()

        result = await verify_identity(
            professor_context=ctx,
            page_url="https://example.com/page",
            page_content="Some content.",
            llm_client=llm,
            llm_model="test",
        )
        assert result.is_same_person is False
        assert result.error is not None
