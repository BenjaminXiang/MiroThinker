import pytest

from src.data_agents.professor.name_selection import (
    choose_richer_name,
    is_obvious_non_person_name,
    is_same_person_name_variant,
    normalize_name_key,
    select_canonical_name,
)


@pytest.mark.parametrize("title", ["首页", "师资", "师资队伍", "南燕新闻"])
def test_is_obvious_non_person_name_recognizes_known_navigation_titles(title: str):
    assert is_obvious_non_person_name(title)


def test_is_obvious_non_person_name_does_not_block_legitimate_name_with_news_substring():
    assert not is_obvious_non_person_name("李新闻")


def test_same_person_richer_variant_selection_prefers_more_informative_name():
    assert is_same_person_name_variant("李志", "李志教授")
    assert choose_richer_name("李志教授", "李志") == "李志教授"
    assert select_canonical_name(roster_name="李志", extracted_name="李志教授") == "李志教授"


def test_normalize_name_key_removes_separators_and_spaces():
    assert normalize_name_key(" 李·志 教授 ") == "李志教授"


def test_select_canonical_name_falls_back_to_roster_name_when_extracted_is_nav_noise():
    assert select_canonical_name(roster_name="靳玉乐", extracted_name="导航") == "靳玉乐"
    assert select_canonical_name(roster_name="陈向兵", extracted_name="学部概况") == "陈向兵"
    assert select_canonical_name(roster_name="Huthanance", extracted_name="概况") == "Huthanance"


def test_select_canonical_name_normalizes_bom_prefixed_names():
    assert select_canonical_name(roster_name="\ufeff陈冠亨", extracted_name=None) == "陈冠亨"
