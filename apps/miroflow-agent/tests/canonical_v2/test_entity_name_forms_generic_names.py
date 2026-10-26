"""Generic appellations must never become entity-link forms.

Adopted from the 2026-10-26 hot patch: the pack carries four professor records
whose canonical name is a generic appellation (`教授`, `院士`, `讲师`,
`副教授`). The record literally named `教授` matched inside `刘桂良教授`, took
the protected slot, and shadowed the real manual record. The fix is at index
generation (never build a form from a generic appellation), not a query-side
blocklist.
"""

from __future__ import annotations

from src.data_agents.canonical_v2 import knowledge_read_isolated as iso


def test_generic_person_names_are_not_indexed() -> None:
    assert "教授" in iso._ENTITY_LINK_GENERIC_PERSON_NAMES
    forms = iso._entity_name_forms("professor", frozenset({"教授", "刘桂良"}))
    assert forms == frozenset({"刘桂良"})


def test_every_generic_appellation_is_filtered() -> None:
    for generic in ("教授", "副教授", "讲师", "老师", "教师", "博士", "研究员", "院士"):
        forms = iso._entity_name_forms("professor", frozenset({generic}))
        assert forms == frozenset(), generic


def test_real_names_still_survive() -> None:
    forms = iso._entity_name_forms("professor", frozenset({"柯文德", "刘桂良"}))
    assert forms == frozenset({"柯文德", "刘桂良"})


def test_blocklist_only_applies_to_single_term_forms() -> None:
    """A longer name that merely contains a generic word is unaffected."""
    forms = iso._entity_name_forms("professor", frozenset({"教授家园"}))
    assert "教授家园" in forms
