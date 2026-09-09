from __future__ import annotations

import pytest

from src.data_agents.company.team_parser import parse_team_raw, structure_team_raw_with_llm


def test_parse_single_member_full_format():
    members = parse_team_raw(
        "王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。"
    )

    assert len(members) == 1
    assert members[0].raw_name == "王博洋"
    assert members[0].raw_role == "CEO&联合创始人"
    assert members[0].raw_intro == "王博洋，旭宏医疗CEO&联合创始人。"
    assert members[0].raw_intro.endswith("。")


def test_parse_multiple_members_newline_separated():
    raw = (
        "王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。\n"
        "杨馥诚，职务：董事长，介绍：杨馥诚，旭宏医疗董事长。\n"
        "罗杰，职务：首席运营官，介绍：罗杰，旭宏医疗首席运营官。"
    )

    members = parse_team_raw(raw)

    assert [member.raw_name for member in members] == ["王博洋", "杨馥诚", "罗杰"]
    assert [member.raw_role for member in members] == [
        "CEO&联合创始人",
        "董事长",
        "首席运营官",
    ]


@pytest.mark.parametrize("raw", ["", None, "-", "  \n  ", " -- "])
def test_parse_empty_returns_empty(raw: str | None):
    assert parse_team_raw(raw) == []


def test_parse_missing_role_field():
    members = parse_team_raw("王博洋，介绍：王博洋，旭宏医疗联合创始人。")

    assert len(members) == 1
    assert members[0].raw_name == "王博洋"
    assert members[0].raw_role is None
    assert members[0].raw_intro == "王博洋，旭宏医疗联合创始人。"


def test_parse_missing_intro_field():
    members = parse_team_raw("吴卓谦，职务：首席财务官兼公司秘书")

    assert len(members) == 1
    assert members[0].raw_name == "吴卓谦"
    assert members[0].raw_role == "首席财务官兼公司秘书"
    assert members[0].raw_intro is None


def test_parse_intro_contains_fullwidth_comma():
    members = parse_team_raw(
        "周光，职务：CEO&首席科学家，介绍：德州大学博士，曾任Roadstar.ai 联合创始人、首席机器人专家。"
    )

    assert len(members) == 1
    assert members[0].raw_name == "周光"
    assert members[0].raw_role == "CEO&首席科学家"
    assert members[0].raw_intro == (
        "德州大学博士，曾任Roadstar.ai 联合创始人、首席机器人专家。"
    )


def test_parse_trailing_whitespace():
    raw = (
        "王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。\n"
        "\n"
        "杨馥诚，职务：董事长，介绍：杨馥诚，旭宏医疗董事长。\n"
        "  \n"
    )

    members = parse_team_raw(raw)

    assert [member.raw_name for member in members] == ["王博洋", "杨馥诚"]


def test_parse_never_raises():
    pathological_cases = [
        "，",
        "，，，",
        "介绍：只有介绍",
        "张三，职务：",
        "A\nB\nC",
        "Leah Zhang，介绍：Leah Zhang，DeepRoute Strategy Manager。",
    ]

    for raw in pathological_cases:
        members = parse_team_raw(raw)
        assert isinstance(members, list)
        assert all(member.raw_name.strip() for member in members)


def test_structure_team_raw_with_llm_preserves_raw_and_extracts_evidence_fields():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert "王博洋" in kwargs["messages"][1]["content"]

                    class _Message:
                        content = (
                            '{"members":[{"name":"王博洋","role":"CEO&联合创始人",'
                            '"background":"连续创业者，长期参与医疗产品商业化。",'
                            '"experience_highlights":["医疗产品商业化","公司经营管理"],'
                            '"relevance":"负责旭宏医疗整体经营和心电产品商业化。",'
                            '"confidence":0.86,'
                            '"evidence_span":"王博洋，旭宏医疗CEO&联合创始人。"}]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    raw = "王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。"

    members = structure_team_raw_with_llm(
        raw,
        company_name="深圳旭宏医疗科技有限公司",
        llm_client=_FakeLLM(),
        llm_model="deepseek-v4-flash",
    )

    assert len(members) == 1
    assert members[0].name == "王博洋"
    assert members[0].role == "CEO&联合创始人"
    assert members[0].background == "连续创业者，长期参与医疗产品商业化。"
    assert members[0].experience_highlights == ("医疗产品商业化", "公司经营管理")
    assert members[0].relevance == "负责旭宏医疗整体经营和心电产品商业化。"
    assert members[0].evidence_span == "王博洋，旭宏医疗CEO&联合创始人。"
    assert members[0].raw_text == raw


def test_structure_team_raw_without_llm_returns_source_grounded_fallback():
    raw = "周光，职务：CEO&首席科学家，介绍：德州大学博士，曾任Roadstar.ai 联合创始人、首席机器人专家。"

    members = structure_team_raw_with_llm(
        raw,
        company_name="深圳示例科技有限公司",
        llm_client=None,
        llm_model="deepseek-v4-flash",
    )

    assert len(members) == 1
    assert members[0].name == "周光"
    assert members[0].role == "CEO&首席科学家"
    assert members[0].background == "德州大学博士，曾任Roadstar.ai 联合创始人、首席机器人专家。"
    assert members[0].experience_highlights == (
        "德州大学博士，曾任Roadstar.ai 联合创始人、首席机器人专家。",
    )
    assert members[0].raw_text == raw
