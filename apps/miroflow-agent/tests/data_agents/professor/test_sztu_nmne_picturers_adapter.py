from pathlib import Path

import pytest

from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.discovery import (
    DiscoveryLimits,
    _should_continue_after_roster_entries,
    discover_professor_seeds,
)
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.roster import (
    _SCHOOL_ROSTER_ADAPTERS,
    extract_roster_entries,
    extract_roster_page_links,
)
from src.data_agents.professor.school_adapters import find_matching_school_adapter

ADAPTER_NAME = "sztu-nmne-picturers-roster"
SEED_URL = (
    "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004"
)
PAGINATION_URL = (
    "https://nmne.sztu.edu.cn/picturers.jsp?"
    "a237185t=8&a237185p=2&a237185c=8&urltype=tree.TreeTempUrl&wbtreeid=1004"
)
FIXTURE = Path(__file__).parent / "fixtures" / "sztu" / "nmne_picturers_1004.html"
PAGE_TWO_FIXTURE = (
    Path(__file__).parent / "fixtures" / "sztu" / "nmne_picturers_1004_page2.html"
)

EXPECTED_ENTRIES = [
    ("阮双琛", "https://nmne.sztu.edu.cn/info/1033/1594.htm"),
    ("刘清侠", "https://nmne.sztu.edu.cn/info/1033/3214.htm"),
    ("韩培刚", "https://nmne.sztu.edu.cn/info/1033/1207.htm"),
    ("仇明侠", "https://nmne.sztu.edu.cn/info/1033/1206.htm"),
    ("柴广跃", "https://nmne.sztu.edu.cn/info/1033/1205.htm"),
    ("偰正才", "https://nmne.sztu.edu.cn/info/1033/1204.htm"),
    ("孔令兵", "https://nmne.sztu.edu.cn/info/1033/1203.htm"),
    ("李顺朴", "https://nmne.sztu.edu.cn/info/1033/1265.htm"),
]


def _seed(source_url: str) -> ProfessorRosterSeed:
    return ProfessorRosterSeed(
        institution="深圳技术大学",
        department="新材料与新能源学院",
        roster_url=source_url,
    )


def _matching_adapter_name(source_url: str) -> str:
    adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    assert adapter is not None
    return adapter.name


def test_nmne_picturers_seed_resolves_to_the_registered_adapter() -> None:
    assert resolve_seed_adapter_name(_seed(SEED_URL)) == ADAPTER_NAME
    assert _matching_adapter_name(SEED_URL) == ADAPTER_NAME
    assert [adapter.name for adapter in _SCHOOL_ROSTER_ADAPTERS].count(
        ADAPTER_NAME
    ) == 1


@pytest.mark.parametrize(
    "verified_column_id",
    ["1004", "1033", "1034", "1035", "1036", "1351", "1352"],
)
def test_nmne_picturers_matcher_accepts_the_verified_cms_columns(
    verified_column_id: str,
) -> None:
    url = (
        "https://nmne.sztu.edu.cn/picturers.jsp?"
        f"urltype=tree.TreeTempUrl&wbtreeid={verified_column_id}"
    )

    assert resolve_seed_adapter_name(_seed(url)) == ADAPTER_NAME
    assert _matching_adapter_name(url) == ADAPTER_NAME


def test_nmne_picturers_matcher_accepts_the_cms_pagination_url() -> None:
    assert resolve_seed_adapter_name(_seed(PAGINATION_URL)) == ADAPTER_NAME
    assert _matching_adapter_name(PAGINATION_URL) == ADAPTER_NAME


@pytest.mark.parametrize(
    ("other_url", "expected_adapter"),
    [
        ("https://ai.sztu.edu.cn/szdw/jytd/jxjs.htm", "sztu-teacher-family"),
        ("https://nmne.sztu.edu.cn/xygk.htm", None),
        ("https://nmne.sztu.edu.cn/info/1033/3214.htm", None),
        (
            "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=2001",
            None,
        ),
        ("https://nmne.sztu.edu.cn/picturers.jsp", None),
        ("https://nmne.sztu.edu.cn/picturers.jsp?wbtreeid=", None),
        (
            "https://other.sztu.edu.cn/picturers.jsp?"
            "urltype=tree.TreeTempUrl&wbtreeid=1004",
            None,
        ),
    ],
)
def test_nmne_picturers_matcher_leaves_nearby_sztu_urls_alone(
    other_url: str, expected_adapter: str | None
) -> None:
    assert resolve_seed_adapter_name(_seed(other_url)) == expected_adapter, other_url
    adapter = find_matching_school_adapter(other_url, _SCHOOL_ROSTER_ADAPTERS)
    assert (
        adapter.name if adapter is not None else None
    ) == expected_adapter, other_url


def test_nmne_picturers_adapter_extractor_reads_the_roster_cards() -> None:
    adapter = find_matching_school_adapter(SEED_URL, _SCHOOL_ROSTER_ADAPTERS)
    assert adapter is not None

    entries = adapter.extract(
        FIXTURE.read_text(encoding="utf-8"),
        "深圳技术大学",
        "新材料与新能源学院",
        SEED_URL,
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == EXPECTED_ENTRIES
    assert {entry.source_url for entry in entries} == {SEED_URL}
    assert {entry.institution for entry in entries} == {"深圳技术大学"}
    assert {entry.department for entry in entries} == {"新材料与新能源学院"}


def test_nmne_picturers_seed_page_entries_through_the_public_extractor() -> None:
    """The seed page's entries survive the public entry point (adapter path included)."""
    entries = extract_roster_entries(
        html=FIXTURE.read_text(encoding="utf-8"),
        institution="深圳技术大学",
        department="新材料与新能源学院",
        source_url=SEED_URL,
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == EXPECTED_ENTRIES


def _page_url(page_number: int) -> str:
    """The CMS pager target for one page of the 1004 list (shape taken from the live page)."""
    return (
        "https://nmne.sztu.edu.cn/picturers.jsp?"
        f"a237185t=8&a237185p={page_number}&a237185c=8"
        "&urltype=tree.TreeTempUrl&wbtreeid=1004"
    )


def test_nmne_picturers_page_links_offer_every_page_of_the_list() -> None:
    """The seed page offers pages 2-8 — including 6/7, which its own window does not show.

    The live window renders 2/3/4/5/8; the missing middle pages are filled up to the last
    page the pager advertises, reusing an observed pager link as the query template.
    """
    links = extract_roster_page_links(FIXTURE.read_text(encoding="utf-8"), SEED_URL)

    assert links == [
        (_page_url(2), "page-2"),
        (_page_url(3), "page-3"),
        (_page_url(4), "page-4"),
        (_page_url(5), "page-5"),
        (_page_url(6), "page-6"),
        (_page_url(7), "page-7"),
        (_page_url(8), "page-8"),
    ]


def test_nmne_picturers_page_links_never_offer_the_page_they_were_read_from() -> None:
    """Page 2's own pager links 首页/上页/1 backwards — page 2 itself is never offered."""
    links = extract_roster_page_links(
        PAGE_TWO_FIXTURE.read_text(encoding="utf-8"), _page_url(2)
    )
    urls = [url for url, _label in links]

    assert _page_url(2) not in urls
    assert urls == [
        _page_url(1),
        _page_url(3),
        _page_url(4),
        _page_url(5),
        _page_url(6),
        _page_url(7),
        _page_url(8),
    ]


def test_nmne_picturers_page_two_holds_the_next_eight_people() -> None:
    """The pager pages enumerate further people — page 2 shares nobody with page 1."""
    page_one_names = {
        entry.name
        for entry in extract_roster_entries(
            html=FIXTURE.read_text(encoding="utf-8"),
            institution="深圳技术大学",
            department="新材料与新能源学院",
            source_url=SEED_URL,
        )
    }
    page_two_names = {
        entry.name
        for entry in extract_roster_entries(
            html=PAGE_TWO_FIXTURE.read_text(encoding="utf-8"),
            institution="深圳技术大学",
            department="新材料与新能源学院",
            source_url=_page_url(2),
        )
    }

    assert page_two_names == {
        "方晓东",
        "翟剑庞",
        "陈丽琼",
        "朱海鸥",
        "游利兵",
        "安红雨",
        "苏耀荣",
        "何斌",
    }
    assert page_one_names.isdisjoint(page_two_names)


@pytest.mark.parametrize(
    ("seed_url", "current_url", "current_depth"),
    [
        (SEED_URL, SEED_URL, 0),
        (SEED_URL, _page_url(3), 1),
    ],
)
def test_discovery_keeps_walking_the_cms_roster_pages(
    seed_url: str, current_url: str, current_depth: int
) -> None:
    assert _should_continue_after_roster_entries(
        seed_url=seed_url,
        current_url=current_url,
        current_depth=current_depth,
        html=FIXTURE.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    "non_roster_url",
    [
        "https://nmne.sztu.edu.cn/xygk.htm",
        "https://nmne.sztu.edu.cn/szdw.htm",
        "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=2001",
        "https://ai.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
    ],
)
def test_discovery_stops_where_the_nmne_matcher_stops(non_roster_url: str) -> None:
    assert not _should_continue_after_roster_entries(
        seed_url=non_roster_url,
        current_url=non_roster_url,
        current_depth=0,
        html=FIXTURE.read_text(encoding="utf-8"),
    )


def test_discovery_walks_every_page_the_seed_page_links() -> None:
    """End to end through the real loop: the seed page dispatches every page of the list.

    Page 1 and page 2 are served with their real fixtures; pages 3-8 are served with page 1's
    HTML (there is no fixture for them), so the distinct-people count locks the dispatch and
    the fact that page 2 adds new people — not the real content of pages 3-8.
    """
    page_one = FIXTURE.read_text(encoding="utf-8")
    page_two = PAGE_TWO_FIXTURE.read_text(encoding="utf-8")
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return page_two if url == _page_url(2) else page_one

    result = discover_professor_seeds(
        seeds=[_seed(SEED_URL)],
        fetch_html=fetch,
        limits=DiscoveryLimits(),
    )

    status = result.source_statuses[0]
    assert status.status == "resolved"
    assert status.visited_urls[0] == SEED_URL
    assert set(status.visited_urls) == {
        SEED_URL,
        *[
            _page_url(page) for page in range(1, 9)
        ],  # p=1 is page 2's back-link spelling
    }
    assert len(result.professors) == 16
    discovered_names = {professor.name for professor in result.professors}
    assert {"阮双琛", "方晓东"} <= discovered_names
