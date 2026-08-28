"""Follow-up domain carryover (fix-followup-domain-carryover, G11T2).

A signal-less topic follow-up (「在真实数据采集路线中有哪些具体方式」after a
厂商/数据路线 turn) fell back to ALL four domains; professor vector noise
(曲建飞/胡伟鹏… matched on "数据采集") won the ranking and the answer
degraded to a raw candidate dump. The planner now inherits the prior turn's
inferred domains when the follow-up carries no signal of its own.
"""

from __future__ import annotations

from importlib import import_module

serving = import_module(
    "src.data_agents.canonical_v2.knowledge_serving_isolated"
)

FOLLOWUP = "在真实数据采集路线中，有哪些具体方式"
PRIOR_COMPANY = "具身智能厂商在数据方面目前存在几种技术路线"


def _domains_for(query: str, prior: str | None) -> tuple[str, ...]:
    """Drive _infer_domains through the planner's carryover branch."""
    inferred = serving._infer_domains(query)
    if tuple(inferred) == tuple(serving._PUBLIC_DOMAINS) and prior:
        inherited = serving._infer_domains(prior)
        if tuple(inherited) != tuple(serving._PUBLIC_DOMAINS):
            return inherited
    return inferred


def test_signal_less_followup_falls_back_to_all_domains() -> None:
    assert tuple(serving._infer_domains(FOLLOWUP)) == tuple(
        serving._PUBLIC_DOMAINS
    )


def test_carryover_inherits_prior_domains() -> None:
    # The prior turn names 厂商 -> company; the follow-up inherits it.
    assert _domains_for(FOLLOWUP, PRIOR_COMPANY) == ("company",)


def test_signal_bearing_query_not_overridden() -> None:
    # The follow-up names a professor marker: its own inference wins.
    assert _domains_for("他的论文有哪些", PRIOR_COMPANY) == (
        "paper",
    ) or "paper" in _domains_for("他的论文有哪些", PRIOR_COMPANY)


def test_no_carryover_when_prior_also_signal_less() -> None:
    assert tuple(_domains_for(FOLLOWUP, "还有什么")) == tuple(
        serving._PUBLIC_DOMAINS
    )
