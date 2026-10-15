"""Alias foothold: a pack-known name holds a local-scope foothold.

RED before this slice: ``_has_local_scope_foothold`` had no data-driven
name-shape path, so ``国先中心（深圳）的详细信息`` executed Web-only
(round-47 live evidence). The fixtures reuse the read side's own name forms
and linker, so the unit chain speaks the production language instead of a
hand-built vocabulary.
"""

from __future__ import annotations

import pytest

from src.data_agents.canonical_v2 import knowledge_read_isolated as iso
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    _has_local_scope_foothold,
)

FULL_NAME = "深圳国际先进技术应用推进中心"
ALIAS = "深圳国先中心"
ROUND47_ASK = "国先中心（深圳）的详细信息"
ROUND47_FULL_ASK = "介绍一下 国际先进技术应用推进中心（深圳）"
ENV = "CANONICAL_V2_ALIAS_FOOTHOLD"


def _pack_name_linker():
    forms = iso._entity_name_forms("company", frozenset({FULL_NAME, ALIAS}))
    index = iso._EntityNameIndex(
        targets={form: (0,) for form in forms},
        forms_longest_first=tuple(
            sorted(forms, key=lambda form: (-len(form), form))
        ),
    )

    def linker(query: str) -> bool:
        return bool(iso._entity_link_entry_indexes(index, query))

    return linker, forms


def test_alias_forms_cover_the_round47_asks() -> None:
    linker, forms = _pack_name_linker()
    # The city-prefix strip is what makes the bracket-reordered short form
    # match: 深圳国先中心 -> 国先中心, and FULL_NAME -> without 深圳.
    assert "国先中心" in forms
    assert "国际先进技术应用推进中心" in forms
    assert linker(ROUND47_ASK) is True
    assert linker(ROUND47_FULL_ASK) is True


@pytest.mark.parametrize(
    "query",
    (
        "世界上最美丽的女人是谁",
        "JEPA有哪些变体",
        "介绍一下",
        "深圳有哪些做机器人的公司",
    ),
)
def test_name_linker_negative_controls(query: str) -> None:
    linker, _ = _pack_name_linker()
    assert linker(query) is False


def test_foothold_uses_the_linker_when_lexical_checks_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linker, _ = _pack_name_linker()
    monkeypatch.delenv(ENV, raising=False)
    # Baseline: without a linker the old lexical decision still says no.
    assert _has_local_scope_foothold(ROUND47_ASK) is False
    assert _has_local_scope_foothold(ROUND47_FULL_ASK) is False
    # With the data-driven linker both hold.
    assert _has_local_scope_foothold(ROUND47_ASK, name_linker=linker) is True
    assert (
        _has_local_scope_foothold(ROUND47_FULL_ASK, name_linker=linker) is True
    )


def test_foothold_kill_switch_restores_old_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linker, _ = _pack_name_linker()
    monkeypatch.setenv(ENV, "0")
    assert _has_local_scope_foothold(ROUND47_ASK, name_linker=linker) is False
    # Lexical positives are untouched by the switch.
    assert _has_local_scope_foothold("优必选有哪些专利") is True


def test_foothold_negative_control_keeps_web_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linker, _ = _pack_name_linker()
    monkeypatch.delenv(ENV, raising=False)
    assert (
        _has_local_scope_foothold("世界上最美丽的女人是谁", name_linker=linker)
        is False
    )


def test_foothold_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    linker, _ = _pack_name_linker()
    monkeypatch.delenv(ENV, raising=False)
    assert all(
        _has_local_scope_foothold(ROUND47_ASK, name_linker=linker)
        for _ in range(3)
    )
