# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for company linker — verify and write professor-company associations."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.company_linker import (
    CompanyLinkResult,
    verify_company_link,
)
from src.data_agents.professor.web_search_enrichment import CompanyMention
from src.data_agents.professor.models import EnrichedProfessorProfile


def _make_profile(**kwargs) -> EnrichedProfessorProfile:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        profile_url="https://www.sustech.edu.cn/zh/lizhi",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
        research_directions=["机器学习"],
    )
    defaults.update(kwargs)
    return EnrichedProfessorProfile(**defaults)


def _make_mention(**kwargs) -> CompanyMention:
    defaults = dict(
        company_name="深圳点联传感科技有限公司",
        role="首席科学家",
        evidence_url="https://news.example.com/lizhi-company",
    )
    defaults.update(kwargs)
    return CompanyMention(**defaults)


@pytest.mark.asyncio
class TestVerifyCompanyLink:
    """Test company link verification."""

    async def test_verified_link_returned(self):
        """Company link verified → CompanyLinkResult returned."""
        llm_response = json.dumps({
            "is_associated": True,
            "confidence": 0.9,
            "role": "首席科学家",
            "reasoning": "News article confirms professor is chief scientist.",
        })
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile()
        mention = _make_mention()
        result = await verify_company_link(
            professor=profile,
            company_mention=mention,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result is not None
        assert result.company_link.company_name == "深圳点联传感科技有限公司"
        assert result.company_link.role == "首席科学家"
        assert result.company_link.source == "web_search"
        assert result.verification_confidence >= 0.8

    async def test_low_confidence_returns_none(self):
        """Confidence < 0.8 → returns None."""
        llm_response = json.dumps({
            "is_associated": True,
            "confidence": 0.5,
            "role": "未知",
            "reasoning": "Unsure about the association.",
        })
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile()
        mention = _make_mention()
        result = await verify_company_link(
            professor=profile,
            company_mention=mention,
            llm_client=mock_llm,
            llm_model="test",
        )
        assert result is None

    async def test_not_associated_returns_none(self):
        """LLM says not associated → returns None."""
        llm_response = json.dumps({
            "is_associated": False,
            "confidence": 0.85,
            "role": "",
            "reasoning": "Different person with same name.",
        })
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile()
        mention = _make_mention()
        result = await verify_company_link(
            professor=profile,
            company_mention=mention,
            llm_client=mock_llm,
            llm_model="test",
        )
        assert result is None

    async def test_llm_failure_returns_none(self):
        """LLM failure → returns None."""
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = RuntimeError("API error")

        profile = _make_profile()
        mention = _make_mention()
        result = await verify_company_link(
            professor=profile,
            company_mention=mention,
            llm_client=mock_llm,
            llm_model="test",
        )
        assert result is None
