from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.roster import (
    _SCHOOL_ROSTER_ADAPTERS,
    extract_roster_entries,
    extract_roster_page_links,
)
from src.data_agents.professor.school_adapters import find_matching_school_adapter

PKUSZ_HUB_URL = "https://www.pkusz.edu.cn/szdw.htm"


def _seed(source_url: str) -> ProfessorRosterSeed:
    return ProfessorRosterSeed(
        institution="北京大学深圳研究生院",
        department=None,
        roster_url=source_url,
    )


def _matching_adapter_name(source_url: str) -> str:
    adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    assert adapter is not None
    return adapter.name


def test_pkusz_school_roster_url_resolves_to_the_szdw_hub_adapter() -> None:
    assert resolve_seed_adapter_name(_seed(PKUSZ_HUB_URL)) == "pkusz-szdw-hub"
    assert _matching_adapter_name(PKUSZ_HUB_URL) == "pkusz-szdw-hub"


def test_unrelated_pkusz_urls_do_not_match_the_hub_adapter() -> None:
    for url in (
        "https://www.pkusz.edu.cn/",
        "https://www.pkusz.edu.cn/xydh.htm",
        "https://www.pkusz.edu.cn/bygk/byjs.htm",
        "https://scbb.pkusz.edu.cn/szdw.htm",
        "https://www.ece.pku.edu.cn/szdw.htm",
    ):
        assert resolve_seed_adapter_name(_seed(url)) is None, url
        assert find_matching_school_adapter(url, _SCHOOL_ROSTER_ADAPTERS) is None, url


def test_pkusz_hub_adapter_neither_invents_entries_nor_swallows_hub_links() -> None:
    markdown = """
*   [### 学院导航](https://www.pkusz.edu.cn/xydh.htm "学院导航")[信息工程学院](https://www.ece.pku.edu.cn/ "信息工程学院")

教师队伍

*   [信息工程学院](https://www.ece.pku.edu.cn/szdw.htm)
*   [化学生物学与生物技术学院](https://scbb.pkusz.edu.cn/szdw.htm)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="北京大学深圳研究生院",
        department=None,
        source_url=PKUSZ_HUB_URL,
    )
    links = extract_roster_page_links(markdown, PKUSZ_HUB_URL)

    assert entries == []
    assert links == [
        ("https://www.ece.pku.edu.cn/szdw.htm", "信息工程学院"),
        ("https://scbb.pkusz.edu.cn/szdw.htm", "化学生物学与生物技术学院"),
    ]


def test_corrected_sztu_roster_urls_resolve_to_sztu_teacher_family() -> None:
    for url in (
        "https://ai.sztu.edu.cn/szdw/jytd/js.htm",
        "https://sgim.sztu.edu.cn/szdw2022/jytd/jxsjzzjqzdh.htm",
        "https://nmne.sztu.edu.cn/szdw.htm",
    ):
        seed = ProfessorRosterSeed(
            institution="深圳技术大学",
            department=None,
            roster_url=url,
        )

        assert resolve_seed_adapter_name(seed) == "sztu-teacher-family", url


def test_legacy_sztu_picturers_url_resolves_to_its_own_narrow_adapter() -> None:
    """The legacy CMS listing lives behind `picturers.jsp`, not behind the `/szdw` matcher.

    Design §6 first assumed a `/szdw…` list URL existed for this college; the live page
    disproved it (every `/szdw…` path answers 404) and the roster is served from the CMS
    column id — so the URL gets its own host-pinned adapter
    (`test_sztu_nmne_picturers_adapter.py` holds the accept/reject matrix).
    """
    seed = ProfessorRosterSeed(
        institution="深圳技术大学",
        department="新材料与新能源学院",
        roster_url=(
            "https://nmne.sztu.edu.cn/picturers.jsp?"
            "urltype=tree.TreeTempUrl&wbtreeid=1004"
        ),
    )

    assert resolve_seed_adapter_name(seed) == "sztu-nmne-picturers-roster"
