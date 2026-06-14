from __future__ import annotations

from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed


def test_resolves_suit_sziit_seed_url_to_named_adapter() -> None:
    seed = ProfessorRosterSeed(
        institution="深圳信息职业技术大学",
        department="中德机器人学院",
        roster_url="https://zd.suit-sz.edu.cn/jyjx/jsfc.htm",
    )

    assert resolve_seed_adapter_name(seed) == "suit-sziit-teacher-family"


def test_resolves_suit_sziit_paged_roster_url_to_named_adapter() -> None:
    seed = ProfessorRosterSeed(
        institution="深圳信息职业技术大学",
        department="中德机器人学院",
        roster_url="https://suit-sz.edu.cn/jyjx/jsfc/1.htm",
    )

    assert resolve_seed_adapter_name(seed) == "suit-sziit-teacher-family"


def test_resolves_uestc_yjsjy_mentor_roster_url_to_named_adapter() -> None:
    seed = ProfessorRosterSeed(
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        roster_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404",
    )

    assert resolve_seed_adapter_name(seed) == "uestc-yjsjy-mentor-roster"


def test_resolves_uestc_sias_seed_url_to_yjsjy_named_adapter() -> None:
    seed = ProfessorRosterSeed(
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        roster_url="https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm",
    )

    assert resolve_seed_adapter_name(seed) == "uestc-yjsjy-mentor-roster"


def test_resolves_sztu_seed_urls_to_named_adapter() -> None:
    urls = [
        "https://sgim.sztu.edu.cn/szdw2022/jytd/jxsjzzjqzdh.htm",
        "https://ai.sztu.edu.cn/szdw/jytd/jxjs.htm",
        "https://cep.sztu.edu.cn/szdw/szdw.htm",
        "https://icoc.sztu.edu.cn/szdw/jytd/jxjs.htm",
        "https://design.sztu.edu.cn/xygk/szdw/jytd.htm",
    ]

    for url in urls:
        seed = ProfessorRosterSeed(
            institution="深圳技术大学",
            department=None,
            roster_url=url,
        )

        assert resolve_seed_adapter_name(seed) == "sztu-teacher-family"


def test_resolves_szu_cpoe_seed_url_to_teacherfeature_adapter() -> None:
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="物理与光电工程学院",
        roster_url=(
            "https://cpoe.szu.edu.cn/szdw.jsp?"
            "urltype=tree.TreeTempUrl&wbtreeid=1111"
        ),
    )

    assert resolve_seed_adapter_name(seed) == "szu-cpoe-teacherfeature"


def test_resolves_sysu_custom_roster_urls_to_named_adapter() -> None:
    expected = {
        "http://sece.sysu.edu.cn/szll/index.htm": "sysu-sece-faculty",
        "https://sic.sysu.edu.cn/members/index.htm": "sysu-sic-members",
        "https://am.sysu.edu.cn/szdw/index.htm": "sysu-am-teacher",
        "https://scst.sysu.edu.cn/faculty": "sysu-scst-teacher",
    }

    for url, adapter_name in expected.items():
        seed = ProfessorRosterSeed(
            institution="中山大学（深圳）",
            department=None,
            roster_url=url,
        )

        assert resolve_seed_adapter_name(seed) == adapter_name
