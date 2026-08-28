"""Lexical identifier-token fallback (fix-lexical-identifier-token, G5).

「我想找PCB打板」 never matched 深南电路 lexically: the full phrase
"PCB打板" is not a substring of any content term, though the company's
industry/profile literally carries "PCB". Fallback: Latin identifier
tokens from the query itself (no alias invention — the industry-alias
attempt was rolled back for over-matching).
"""

from __future__ import annotations

from importlib import import_module

read_isolated = import_module(
    "src.data_agents.canonical_v2.knowledge_read_isolated"
)


def test_pcb_token_matches_pcb_content() -> None:
    assert read_isolated._matches_query_identifier_token(
        "pcb打板", frozenset({"pcb", "印制电路板 封装基板"})
    )


def test_led_token_matches() -> None:
    assert read_isolated._matches_query_identifier_token(
        "led显示屏", frozenset({"led 显示", "光电"})
    )


def test_pure_cjk_query_never_matches_via_token() -> None:
    # 纯中文短语没有拉丁 token，不触发回退（避免 CJK 短词过度匹配）
    assert not read_isolated._matches_query_identifier_token(
        "做锂电池的公司", frozenset({"锂电池", "电池"})
    )


def test_short_tokens_ignored() -> None:
    # 两位以下（如 "ai" 单词边界外）不作为回退 token——保持窄面
    assert not read_isolated._matches_query_identifier_token(
        "ai公司", frozenset({"人工智能"})
    )


def test_unrelated_token_no_match() -> None:
    assert not read_isolated._matches_query_identifier_token(
        "pcb打板", frozenset({"服装", "纺织"})
    )
