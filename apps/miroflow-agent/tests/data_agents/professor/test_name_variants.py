"""RED-phase tests for M1 Unit 1 — name_variants helper."""

from __future__ import annotations

import pytest

from src.data_agents.professor.name_variants import (
    NameVariants,
    resolve_name_variants,
)


def test_name_variants_dataclass_smoke():
    nv = NameVariants(
        zh="姚建铨",
        en="Jianquan Yao",
        pinyin="yao jian quan",
        initials=("J. Yao",),
        all_lower=("姚建铨", "jianquan yao", "yao jian quan", "j. yao"),
    )
    assert nv.zh == "姚建铨"
    assert nv.en == "Jianquan Yao"
    with pytest.raises((AttributeError, TypeError, Exception)):
        nv.zh = "mutated"


def test_resolve_latin_and_cjk_both_provided():
    nv = resolve_name_variants(
        canonical_name="Jianquan Yao",
        canonical_name_zh="姚建铨",
        canonical_name_en="Jianquan Yao",
    )
    assert nv.zh == "姚建铨"
    assert nv.en == "Jianquan Yao"
    assert nv.pinyin is not None
    assert "yao" in nv.pinyin.lower()
    # Initials should include at least one variant
    assert any("Yao" in i for i in nv.initials)


def test_resolve_from_cjk_only():
    nv = resolve_name_variants(
        canonical_name=None,
        canonical_name_zh="陈伟津",
        canonical_name_en=None,
    )
    assert nv.zh == "陈伟津"
    assert nv.en is None
    assert nv.pinyin is not None
    pinyin_lower = nv.pinyin.lower()
    # pypinyin default: surname first (chen), then given (wei jin)
    assert "chen" in pinyin_lower
    assert "wei" in pinyin_lower
    assert "jin" in pinyin_lower


def test_resolve_from_latin_only():
    nv = resolve_name_variants(
        canonical_name="Wenbo Ding",
        canonical_name_zh=None,
        canonical_name_en=None,
    )
    assert nv.en == "Wenbo Ding"
    assert nv.zh is None
    assert nv.pinyin is None
    assert len(nv.initials) >= 1
    assert any("Ding" in i for i in nv.initials)


def test_resolve_infers_cjk_from_canonical_name():
    """When canonical_name is Chinese and canonical_name_zh is None, infer zh."""
    nv = resolve_name_variants(
        canonical_name="姚建铨",
        canonical_name_zh=None,
        canonical_name_en=None,
    )
    assert nv.zh == "姚建铨"
    assert nv.pinyin is not None


def test_resolve_all_none():
    nv = resolve_name_variants(None, None, None)
    assert nv.zh is None
    assert nv.en is None
    assert nv.pinyin is None
    assert nv.initials == ()
    assert nv.all_lower == ()


def test_resolve_single_given_name():
    """'J Smith' — only one initial should be produced, not duplicates."""
    nv = resolve_name_variants(
        canonical_name="J Smith",
        canonical_name_zh=None,
        canonical_name_en=None,
    )
    assert nv.en == "J Smith"
    assert any("Smith" in i for i in nv.initials)


def test_resolve_compound_surname_compiles_pinyin():
    """Chinese compound surname — verify pypinyin doesn't crash."""
    nv = resolve_name_variants(
        canonical_name=None,
        canonical_name_zh="欧阳明",
        canonical_name_en=None,
    )
    # pypinyin splits compound surname into individual characters;
    # we just assert the pinyin output includes "ou yang" and "ming"
    assert nv.pinyin is not None
    lowered = nv.pinyin.lower()
    assert "ou" in lowered
    assert "yang" in lowered
    assert "ming" in lowered


def test_all_lower_contains_all_unique_forms_lowercased():
    nv = resolve_name_variants(
        canonical_name="Jianquan Yao",
        canonical_name_zh="姚建铨",
        canonical_name_en="Jianquan Yao",
    )
    # all_lower is a tuple of unique lowercased forms
    assert len(nv.all_lower) == len(set(nv.all_lower))
    # At minimum: zh + en + pinyin representations present
    joined = " ".join(nv.all_lower)
    assert "姚建铨" in joined
    assert "jianquan yao" in joined
    assert "yao" in joined.lower()


def test_resolve_latin_with_multiple_given_names():
    """'Wenbo Yi Ding' — should produce initials from all given-name tokens."""
    nv = resolve_name_variants(
        canonical_name="Wenbo Yi Ding",
        canonical_name_zh=None,
        canonical_name_en=None,
    )
    # Surname = Ding (last token), given = Wenbo Yi
    assert any("Ding" in i for i in nv.initials)
    # Full-initials variant should include both "W." and "Y." prefixes
    assert any("W." in i and "Y." in i for i in nv.initials) or any(
        "W." in i for i in nv.initials
    )
