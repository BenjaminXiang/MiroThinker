import pytest

from src.data_agents.professor.enrichment import build_profile_record
from src.data_agents.professor.models import DiscoveredProfessorSeed, ExtractedProfessorProfile


def _roster_seed(name: str) -> DiscoveredProfessorSeed:
    return DiscoveredProfessorSeed(
        name=name,
        institution="南方科技大学",
        department="工学院",
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        source_url="https://www.sustech.edu.cn/zh/faculties.html",
    )


def _extracted_profile(name: str) -> ExtractedProfessorProfile:
    return ExtractedProfessorProfile(
        name=name,
        institution="南方科技大学",
        department="工学院",
        title="教授",
        email=None,
        homepage_url=None,
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        office=None,
        research_directions=[],
        source_urls=["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
    )


@pytest.mark.parametrize("junk_name", ["师资", "师资队伍", "首页", "南燕新闻"])
def test_build_profile_record_prefers_roster_name_when_extracted_name_is_navigation_junk(
    junk_name: str,
):
    record = build_profile_record(
        roster_seed=_roster_seed("吴亚北"),
        extracted=_extracted_profile(junk_name),
        extraction_status="partial",
        skip_reason=None,
    )

    assert record.name == "吴亚北"


def test_build_profile_record_keeps_richer_extracted_name_for_same_person():
    record = build_profile_record(
        roster_seed=_roster_seed("李志"),
        extracted=_extracted_profile("李志教授"),
        extraction_status="structured",
        skip_reason=None,
    )

    assert record.name == "李志教授"


def test_build_profile_record_keeps_richer_roster_name_for_same_person():
    record = build_profile_record(
        roster_seed=_roster_seed("李志教授"),
        extracted=_extracted_profile("李志"),
        extraction_status="structured",
        skip_reason=None,
    )

    assert record.name == "李志教授"
