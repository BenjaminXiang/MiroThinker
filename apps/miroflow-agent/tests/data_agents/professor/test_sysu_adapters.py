from pathlib import Path

import pytest

from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.profile import extract_professor_profile
from src.data_agents.professor.roster import (
    _SCHOOL_ROSTER_ADAPTERS,
    extract_roster_entries,
    extract_roster_page_links,
)
from src.data_agents.professor.school_adapters import find_matching_school_adapter


FIXTURES = Path(__file__).parent / "fixtures" / "sysu"


def _matching_adapter_name(source_url: str) -> str:
    adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    assert adapter is not None
    return adapter.name


@pytest.mark.parametrize(
    ("seed_id", "source_url", "expected_adapter"),
    [
        (36, "http://sece.sysu.edu.cn/szll/index.htm", "sysu-sece-faculty"),
        (37, "http://ise.sysu.edu.cn/teachers", "sysu-ise-teachers"),
        (38, "https://sic.sysu.edu.cn/members/index.htm", "sysu-sic-members"),
        (39, "https://am.sysu.edu.cn/szdw/index.htm", "sysu-am-teacher"),
        (40, "https://scst.sysu.edu.cn/faculty", "sysu-scst-teacher"),
        (41, "https://science.sysu.edu.cn/faculty", "sysu-science-teacher"),
        (
            42,
            "http://sofe.sysu.edu.cn/zh-hans/teachers/full-time",
            "sysu-sofe-teacher",
        ),
    ],
)
def test_sysu_seed_36_42_stored_urls_resolve_to_school_specific_adapters(
    seed_id: int,
    source_url: str,
    expected_adapter: str,
):
    seed = ProfessorRosterSeed(
        institution="中山大学（深圳）",
        department=None,
        roster_url=source_url,
    )

    assert resolve_seed_adapter_name(seed) == expected_adapter, seed_id
    assert expected_adapter != "sysu-faculty-staff"


def test_sysu_sece_roster_adapter_is_specific():
    assert (
        _matching_adapter_name("https://sece.sysu.edu.cn/szll/js/zngz/1401951.htm")
        == "sysu-sece-faculty"
    )
    assert _matching_adapter_name("https://sece.sysu.edu.cn/szll/js") == "sysu-sece-faculty"


def test_sysu_ise_roster_adapter_is_specific():
    assert _matching_adapter_name("http://ise.sysu.edu.cn/teachers") == "sysu-ise-teachers"
    assert (
        _matching_adapter_name("http://ise.sysu.edu.cn/teacher/ChenJunzhou")
        == "sysu-ise-teachers"
    )


def test_sysu_scst_science_sofe_roster_adapters_are_specific():
    assert (
        _matching_adapter_name("https://scst.sysu.edu.cn/teacher/DaiXianhua")
        == "sysu-scst-teacher"
    )
    assert (
        _matching_adapter_name("https://science.sysu.edu.cn/teacher/536")
        == "sysu-science-teacher"
    )
    assert (
        _matching_adapter_name("http://sofe.sysu.edu.cn/zh-hans/teacher/81")
        == "sysu-sofe-teacher"
    )


def test_sysu_science_roster_keeps_latin_name_not_footer_heading():
    html = """
    <html><body>
      <div class="col-md-6 list-images-1-1 inside-r filter alphaall alphal">
        <div class="facultybg">
          <div class="list-left t-c"><a href="/teacher/Lo%C3%AFc%20MARSOT"></a></div>
          <div class="list-content">
            <h4 class="list-title one-line"><a href="/teacher/Lo%C3%AFc%20MARSOT">Loïc MARSOT</a> 助理教授</h4>
            <p>Email：marsot3@mail.sysu.edu.cn</p>
          </div>
        </div>
      </div>
      <footer><h4>友情链接</h4><a href="/teacher/links.htm">友情链接</a></footer>
    </body></html>
    """

    entries = extract_roster_entries(
        html,
        institution="中山大学（深圳）",
        department="理学院",
        source_url="https://science.sysu.edu.cn/faculty",
    )

    assert [entry.name for entry in entries] == ["Loïc MARSOT"]
    assert entries[0].profile_url == "https://science.sysu.edu.cn/teacher/Lo%C3%AFc%20MARSOT"


def test_sysu_science_profile_extracts_latin_name_from_detail_page():
    html = (FIXTURES / "science_loic_profile.html").read_text()

    profile = extract_professor_profile(
        html,
        source_url="https://science.sysu.edu.cn/teacher/Lo%C3%AFc%20MARSOT",
        institution="中山大学（深圳）",
        department="理学院",
    )

    assert profile.name == "Loïc MARSOT"
    assert profile.title == "助理教授"
    assert profile.email == "marsot3@mail.sysu.edu.cn"
    assert profile.homepage_url == "https://science.sysu.edu.cn/teacher/Lo%C3%AFc%20MARSOT"
    assert profile.profile_raw_text is not None
    assert "友情链接" not in profile.profile_raw_text[:80]


def test_sysu_sic_members_roster_extracts_member_cards():
    html = (FIXTURES / "sic_member_category.html").read_text()

    entries = extract_roster_entries(
        html,
        institution="中山大学（深圳）",
        department="集成电路学院",
        source_url="https://sic.sysu.edu.cn/members/t01/index.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("王美琪", "https://sic.sysu.edu.cn/members/t01/1409794.htm"),
        ("李一鸣", "https://sic.sysu.edu.cn/members/t02/1409801.htm"),
    ]


def test_sysu_am_teacher_roster_extracts_memberblocks():
    html = (FIXTURES / "am_live_memberblock.html").read_text()

    entries = extract_roster_entries(
        html,
        institution="中山大学（深圳）",
        department="先进制造学院",
        source_url="https://am.sysu.edu.cn/teacher",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("黄含", "https://am.sysu.edu.cn/teacher/HuangHan"),
        ("丁北辰", "https://am.sysu.edu.cn/teacher/DingBeichen"),
    ]


def test_sysu_friend_links_do_not_emit_professors_or_roster_pages():
    html = (FIXTURES / "science_friend_links.html").read_text()
    source_url = "https://science.sysu.edu.cn/faculty"

    assert (
        extract_roster_entries(
            html,
            institution="中山大学（深圳）",
            department="理学院",
            source_url=source_url,
        )
        == []
    )
    assert extract_roster_page_links(html, source_url) == []


def test_sysu_sic_profile_scopes_col_md_9_content():
    html = (FIXTURES / "sic_profile_col_md_9.html").read_text()

    profile = extract_professor_profile(
        html,
        source_url="https://sic.sysu.edu.cn/members/t01/1409794.htm",
        institution="中山大学（深圳）",
        department="集成电路学院",
    )

    assert profile.name == "王美琪"
    assert profile.title == "助理教授"
    assert profile.email is None
    assert profile.research_directions == (
        "面向人工智能的集成电路与智能系统设计",
        "软硬件协同设计",
        "VLSI 优化",
        "存算一体",
        "数字孪生系统",
    )
    assert profile.profile_raw_text is not None
    assert "国家高层次人才" not in profile.profile_raw_text
    assert "jcdlxy@mail.sysu.edu.cn" not in profile.profile_raw_text


def test_sysu_am_profile_scopes_col_md_9_content_and_normalizes_email():
    html = (FIXTURES / "am_profile_col_md_9.html").read_text()

    profile = extract_professor_profile(
        html,
        source_url="https://am.sysu.edu.cn/teacher/DingBeichen",
        institution="中山大学（深圳）",
        department="先进制造学院",
    )

    assert profile.name == "丁北辰"
    assert profile.title == "副教授"
    assert profile.email == "dingbch@mail.sysu.edu.cn"
    assert profile.homepage_url == "https://www.researchgate.net/profile/Beichen-Ding"
    assert profile.research_directions == (
        "电液伺服控制系统",
        "机器人精密驱动及运动控制技术",
        "智能装备设计集成",
    )
    assert profile.profile_raw_text is not None
    assert "wangrq55@mail.sysu.edu.cn" not in profile.profile_raw_text
