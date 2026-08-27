"""Regression: industry alias expansion routes fuzzy enumeration to local.

The lexical lane matches the WHOLE query phrase as a substring of one
content term, so "深圳做具身智能机器人的公司有哪些" never matches a
company whose industry field says "机器人" (G7/G5 root cause).  The fix
adds an alias map that extracts industry tags from domain vocabulary
in the query and checks them against content terms.
"""

from __future__ import annotations

from src.data_agents.canonical_v2.knowledge_read_isolated import (
    _industry_alias_terms,
)


def test_embodied_ai_expands_to_robotics_and_ai() -> None:
    aliases = _industry_alias_terms("深圳做具身智能机器人的公司有哪些")
    assert "机器人" in aliases
    assert "人工智能" in aliases


def test_humanoid_robot_expands_to_robotics() -> None:
    aliases = _industry_alias_terms("人形机器人厂商")
    assert "机器人" in aliases


def test_lithium_battery_expands_to_battery() -> None:
    aliases = _industry_alias_terms("锂电池方向的论文")
    assert "电池" in aliases
    assert "新能源" in aliases


def test_no_alias_for_unrelated_query() -> None:
    aliases = _industry_alias_terms("优必选有哪些专利")
    assert aliases == ()


def test_semiconductor_expands_to_chip() -> None:
    aliases = _industry_alias_terms("深圳做半导体芯片的公司")
    assert "芯片" in aliases
    assert "集成电路" in aliases


def test_biomedicine_expands() -> None:
    aliases = _industry_alias_terms("生物医药企业")
    assert "生物" in aliases
    assert "医药" in aliases
