"""Regression tests for paper-retrievability fixes (2026-07-10).

Guards two behavior-affecting fixes that close paper-retrievability-baseline gaps
(`.agents/runs/paper-retrievability-baseline/`):

- Type4 (topic->paper): `_classify_query_by_rules` SHALL route paper-topic-search queries
  to B/paper, not over-fire the exact-paper rule to A/unknown.
  (`openspec/changes/fix-paper-topic-query-classification/`)
- Type2 (professor->paper): `_prof_paper_list_intent` SHALL detect paper-list intent so
  `_professor_profile_or_papers_response` lists the professor's verified papers
  (`A_prof_papers`) instead of the count-only profile.

Pure-function tests (no DB / Milvus / backend). The full DB path is exercised by
`eval_recall_chat.py` (paper-domain recall 7/20 -> 14/20 after both fixes).
"""
from __future__ import annotations

import pytest

from backend.api.chat import _classify_query_by_rules, _prof_paper_list_intent


# --- Type4: paper-topic classification (fix-paper-topic-query-classification) ---


def test_paper_topic_search_with_english_term_routes_to_b_paper() -> None:
    # qid109 baseline case: was over-fired to A/unknown by the exact-paper rule.
    r = _classify_query_by_rules("关于perovskite钙钛矿材料的论文有哪些")
    assert r is not None
    assert r["type"] == "B"
    assert r["target_domain"] == "paper"


def test_paper_topic_latest_papers_routes_to_b_paper() -> None:
    # qid110 baseline case.
    r = _classify_query_by_rules("关于联邦学习federated learning的最新论文")
    assert r is not None
    assert r["type"] == "B"
    assert r["target_domain"] == "paper"


def test_paper_topic_ending_in_paper_stays_b_paper() -> None:
    r = _classify_query_by_rules("钙钛矿太阳能电池方向的论文")
    assert r is not None
    assert r["type"] == "B"
    assert r["target_domain"] == "paper"


def test_bare_english_paper_title_stays_a_paper() -> None:
    # Guard: a bare EN title must NOT be re-routed to B by the broadened topic rule.
    r = _classify_query_by_rules(
        "ShuffleNet V2: Practical Guidelines for Efficient CNN Architecture Design"
    )
    assert r is not None
    assert r["type"] == "A"
    assert r["target_domain"] == "paper"


def test_entity_anchored_paper_query_not_rerouted_to_b_paper() -> None:
    # "X教授的论文" must route via professor (A), not be caught by the paper-topic rule.
    r = _classify_query_by_rules("常瑞华教授发表了哪些论文")
    assert r is not None
    assert r["type"] == "A"
    assert r["target_domain"] == "professor"


def test_paper_author_lookup_not_rerouted_to_b_topic() -> None:
    # "论文 X 的作者有哪些" is a paper-author lookup (A/cross-domain), NOT a topic search.
    # Regression guard for the Type4 broadening over-firing (benchmark Q050 A->B).
    r = _classify_query_by_rules("论文 Segment Anything 的深圳作者有哪些")
    assert r is not None
    assert r["type"] != "B"


# --- Type2: professor paper-list intent (professor->paper traversal) ---


@pytest.mark.parametrize(
    "query",
    [
        "常瑞华教授发表了哪些论文",
        "刘江的论文",
        "陈勇勇教授的代表作",
        "他发表过什么论文",
        "张三的著作有哪些",
    ],
)
def test_prof_paper_list_intent_true(query: str) -> None:
    assert _prof_paper_list_intent(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "介绍清华的丁文伯",
        "常瑞华的研究方向",
        "王学谦的评价如何",
        "张三是谁",
    ],
)
def test_prof_paper_list_intent_false(query: str) -> None:
    assert _prof_paper_list_intent(query) is False


# --- Professor-ambiguity (fix-professor-ambiguity-intro-rule): "X教授是谁" -> A, not G ---


@pytest.mark.parametrize(
    "query",
    [
        "南方科技大学张巍教授是谁",
        "港中大深圳吴佳教授是谁",
    ],
)
def test_professor_with_title_is_not_ambiguous(query: str) -> None:
    # A name with an academic title (教授/研究员) is a definite person -> A, not G ambiguous.
    r = _classify_query_by_rules(query)
    assert r is not None
    assert r["type"] == "A"
    assert r["target_domain"] == "professor"


def test_untitled_name_is_still_ambiguous() -> None:
    # No title -> still ambiguous (G), unchanged.
    r = _classify_query_by_rules("张三是谁")
    assert r is not None
    assert r["type"] == "G"
