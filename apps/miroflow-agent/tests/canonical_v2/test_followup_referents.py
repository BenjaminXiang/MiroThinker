"""Invariant matrix for shared Chinese follow-up referent detection.

The adapter and the serving planner MUST agree on which turns refer to the
active anchor or the displayed set; referent words MUST be strippable from
retrieval query text. Expansion requests ("还有哪些", "其他的呢") intentionally
match neither family until a real expansion operation exists.
"""

from __future__ import annotations

import pytest

from src.data_agents.canonical_v2.followup_referents import (
    has_explicit_named_subject,
    has_set_referent,
    has_singular_referent,
    referent_domain_hint,
    referent_subject_domain,
    strip_leading_pronoun,
)


@pytest.mark.parametrize(
    "query",
    (
        "他有哪些代表性研究成果",
        "他的论文有哪些",
        "她是否创办过公司",
        "她还有哪些科研成果",
        "那它还支持哪些能力",
        "该学者的工作有哪些",
        "这位老师的研究方向是什么",
        "这名教授的论文有哪些",
        "这个人的公司叫什么",
        "此人的代表作是什么",
        "该公司的专利有哪些",
        "这篇文章的链接是什么",
    ),
)
def test_singular_referent_positive(query: str) -> None:
    assert has_singular_referent(query)
    assert not has_set_referent(query)


@pytest.mark.parametrize(
    "query",
    (
        "其他公司有哪些",
        "其它专利有哪些",
        "其他的呢",
        "其他是否有补贴",
        "吉他品牌有哪些",
        "他们有哪些专利",
        "它们分别是什么",
        "还有哪些企业",
        "专利 CN117873146A 的详细信息是什么",
        "中国有哪些成熟的酒店送餐机器人供应商",
    ),
)
def test_singular_referent_negative(query: str) -> None:
    assert not has_singular_referent(query)


@pytest.mark.parametrize(
    "query",
    (
        "上述企业里总部在深圳的有哪些",
        "这些论文的区别是什么",
        "已展示的专利有哪些",
        "其中哪些在深圳",
        "上面的公司有哪些",
        "以上企业有哪些",
        "它们分别是什么",
        "他们有哪些专利",
        "她们分别来自哪些学校",
        "这几家企业哪家更强",
        "这两篇论文的区别",
        "这两位教授谁更适合",
    ),
)
def test_set_referent_positive(query: str) -> None:
    assert has_set_referent(query)


@pytest.mark.parametrize(
    "query",
    (
        "还有哪些企业",
        "其他的呢",
        "他的论文有哪些",
        "专利 CN117873146A 的详细信息是什么",
        "介绍清华的丁文伯",
    ),
)
def test_set_referent_negative(query: str) -> None:
    assert not has_set_referent(query)


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("他有哪些代表性研究成果", "有哪些代表性研究成果"),
        ("他的公司简介", "公司简介"),
        ("他还有哪些专利", "有哪些专利"),
        ("她还是谁", "是谁"),
        ("他们的总部在哪", "总部在哪"),
        ("它们的应用场景", "应用场景"),
        ("其他公司有哪些", "其他公司有哪些"),
        ("介绍清华的丁文伯", "介绍清华的丁文伯"),
    ),
)
def test_strip_leading_pronoun(query: str, expected: str) -> None:
    assert strip_leading_pronoun(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("他有哪些代表性研究成果", False),
        ("这论文的链接是什么", False),
        ("该公司的专利有哪些", False),
        (
            "pFedGPA: Diffusion-based Generative Parameter Aggregation for "
            "Personalized Federated Learning 这篇论文的详细信息",
            True,
        ),
        ("《pFedGPA》这篇论文的链接是什么", True),
        ("介绍清华的丁文伯，他的论文有哪些", True),
        ("华力创这家公司相关信息，他的产量特点是什么", True),
        ("专利 CN117873146A 的详细信息是什么，它的申请公司", True),
        ("丁文伯教授的论文有哪些", True),
        ("深圳市普渡科技有限公司的产品有哪些", True),
        ("优必选这家公司相关信息", True),
        ("上述企业有哪些是深圳的", False),
        ("这位老师的研究方向是什么", False),
        ("这个人创办过哪些公司", False),
        ("这些公司的总部在哪", False),
        ("这家公司的营收是多少", False),
    ),
)
def test_explicit_named_subject(query: str, expected: bool) -> None:
    assert has_explicit_named_subject(query) is expected


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("这些公司的总部在哪", "company"),
        ("该企业的营收是多少", "company"),
        ("这些供应商都在深圳吗", "company"),
        ("他的代表性论文有哪些", "paper"),
        ("上述论文的区别是什么", "paper"),
        ("这些专利的申请年份是什么", "patent"),
        ("这位教授的研究方向是什么", "professor"),
        ("她主持过哪些项目", "professor"),
        ("还有哪些", None),
        ("今天天气怎么样", None),
    ),
)
def test_referent_domain_hint(query: str, expected: str | None) -> None:
    assert referent_domain_hint(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        # The referent is a person even though the asked-about object is papers.
        ("他的代表性论文有哪些", "professor"),
        ("她主持过哪些项目", "professor"),
        ("这位教授的研究方向是什么", "professor"),
        ("此人有哪些专利", "professor"),
        ("该公司的论文有哪些", "company"),
        ("这家企业有哪些专利", "company"),
        ("这些公司的总部在哪", "company"),
        ("上述论文的区别是什么", "paper"),
        ("该论文的链接是什么", "paper"),
        ("这项专利的申请年份", "patent"),
        # Bare 它/它们 discloses no referent type: no constraint, never a mismatch.
        ("它的总部在哪", None),
        ("它们分别是什么", None),
        ("还有哪些", None),
        ("今天天气怎么样", None),
    ),
)
def test_referent_subject_domain(query: str, expected: str | None) -> None:
    assert referent_subject_domain(query) == expected
