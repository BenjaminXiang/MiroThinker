"""Pronoun × anchor-type guard (fix-pronoun-anchor-type-guard).

G3 replay failure (2026-08-28): T1 anchors an ORGANIZATION
(深圳国际先进技术应用推进中心), T2 「他有哪些论文」 free-retrieved junk
papers (《"做"与"揍"》) instead of clarifying. The session snapshot was
correct — the clarification rule simply trusts any present anchor,
regardless of type, so a personal pronoun bound to a company. Guard: a
personal pronoun (他/她) over a non-person anchor clarifies, unless the
query names an explicit subject or the referent history holds a person.
"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from typing import Any

read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
referents_module = import_module("src.data_agents.canonical_v2.followup_referents")
service = import_module("backend.services.canonical_v2_chat")


def _anchor(domain: str, name: str = "某主体") -> Any:
    return read_module.CanonicalEntityHandle(
        canonical_id=f"{domain}-c-test",
        domain=domain,
        display_name=name,
        evidence_ids=(f"evidence:{domain}-c-test",),
    )


def _committed(anchor: Any, history: tuple = ()) -> Any:
    return SimpleNamespace(
        context_receipt=SimpleNamespace(
            active_anchor=anchor,
            displayed_result_set=None,
        ),
        referent_history=history,
    )


def test_personal_pronoun_over_company_anchor_clarifies() -> None:
    assert service._referent_clarification_needed(
        query="他有哪些论文",
        committed=_committed(_anchor("company", "深圳国际先进技术应用推进中心")),
    )


def test_personal_pronoun_over_paper_anchor_clarifies() -> None:
    # P4 family: a paper-title anchor must not swallow a personal pronoun.
    assert service._referent_clarification_needed(
        query="他有哪些论文",
        committed=_committed(_anchor("paper", "扩散模型综述")),
    )


def test_personal_pronoun_over_patent_anchor_clarifies() -> None:
    assert service._referent_clarification_needed(
        query="她的研究方向是什么",
        committed=_committed(_anchor("patent", "CN117873146A")),
    )


def test_personal_pronoun_over_professor_anchor_binds() -> None:
    assert not service._referent_clarification_needed(
        query="他的代表性论文有哪些",
        committed=_committed(_anchor("professor", "丁文伯")),
    )


def test_org_referent_over_company_anchor_binds() -> None:
    # G4 flow: 该公司 must keep binding to the org anchor.
    assert not service._referent_clarification_needed(
        query="该公司的专利有哪些",
        committed=_committed(_anchor("company", "优必选")),
    )


def test_neuter_referent_over_company_anchor_binds() -> None:
    # G2 flow: 这个中心 must keep binding to the org anchor.
    assert not service._referent_clarification_needed(
        query="这个中心的企业培育情况怎么样",
        committed=_committed(_anchor("company", "深圳国际先进技术应用推进中心")),
    )


def test_explicit_named_subject_never_clarifies() -> None:
    assert not service._referent_clarification_needed(
        query="丁文伯他有哪些论文",
        committed=_committed(_anchor("company", "深圳国际先进技术应用推进中心")),
    )


def test_professor_in_history_supplies_person() -> None:
    history = (
        SimpleNamespace(
            kind="anchor",
            domain="professor",
            canonical_ids=("professor-c-ding",),
            display_names=("丁文伯",),
        ),
    )
    assert not service._referent_clarification_needed(
        query="他有哪些论文",
        committed=_committed(_anchor("company", "某公司"), history=history),
    )


def test_has_personal_pronoun_predicate() -> None:
    assert referents_module.has_personal_pronoun("他有哪些论文")
    assert referents_module.has_personal_pronoun("那她的研究方向是什么")
    assert referents_module.has_personal_pronoun("他是否参与创立")
    assert not referents_module.has_personal_pronoun("这个中心的企业培育情况怎么样")
    assert not referents_module.has_personal_pronoun("该公司的专利有哪些")
    assert not referents_module.has_personal_pronoun("它们的用途是什么")
    assert not referents_module.has_personal_pronoun("他们是谁")
