from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.school_adapters import (
    SchoolRosterAdapter,
    find_matching_school_adapter,
    school_adapter_bypass_enabled,
)


def test_find_matching_school_adapter_returns_first_match():
    first = SchoolRosterAdapter(
        name="first",
        matcher=lambda url: "teacher-search" in url,
        extractor=lambda html, institution, department, source_url: [],
    )
    second = SchoolRosterAdapter(
        name="second",
        matcher=lambda url: True,
        extractor=lambda html, institution, department, source_url: [],
    )

    adapter = find_matching_school_adapter(
        "https://sse.cuhk.edu.cn/teacher-search",
        (first, second),
        bypass=False,
    )

    assert adapter is first


def test_find_matching_school_adapter_returns_none_when_bypassed(monkeypatch):
    adapter = SchoolRosterAdapter(
        name="cuhk",
        matcher=lambda url: True,
        extractor=lambda html, institution, department, source_url: [],
    )
    monkeypatch.setenv("PROFESSOR_SCHOOL_ADAPTER_BYPASS", "1")

    assert school_adapter_bypass_enabled() is True
    assert find_matching_school_adapter(
        "https://sse.cuhk.edu.cn/teacher-search",
        (adapter,),
    ) is None


def test_find_matching_school_adapter_returns_none_without_match():
    adapter = SchoolRosterAdapter(
        name="sysu",
        matcher=lambda url: "sysu.edu.cn" in url,
        extractor=lambda html, institution, department, source_url: [],
    )

    assert find_matching_school_adapter(
        "https://sse.cuhk.edu.cn/teacher-search",
        (adapter,),
        bypass=False,
    ) is None


def test_resolve_seed_adapter_supports_sysu_seed_url_families():
    urls = [
        "http://sece.sysu.edu.cn/szll/index.htm",
        "https://sic.sysu.edu.cn/members/index.htm",
        "https://am.sysu.edu.cn/szdw/index.htm",
    ]

    for url in urls:
        seed = ProfessorRosterSeed(
            institution="中山大学（深圳）",
            department="SYSU fixture",
            roster_url=url,
        )

        assert resolve_seed_adapter_name(seed) == "sysu-faculty-staff"
