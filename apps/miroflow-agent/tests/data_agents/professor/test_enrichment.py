import pytest

from src.data_agents.professor.enrichment import (
    build_profile_record,
    extract_profile_record,
    is_structured_profile,
)
from src.data_agents.professor.models import (
    DiscoveredProfessorSeed,
    ExtractedProfessorProfile,
    MergedProfessorProfileRecord,
)


def _roster_seed() -> DiscoveredProfessorSeed:
    return DiscoveredProfessorSeed(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        source_url="https://www.sustech.edu.cn/zh/faculties.html",
    )


def test_is_structured_profile_returns_true_when_homepage_differs_from_profile():
    profile = ExtractedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title=None,
        email=None,
        homepage_url="https://example.com/lizhi",
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        office=None,
        research_directions=[],
        source_urls=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
    )

    assert is_structured_profile(profile) is True


def test_is_structured_profile_returns_false_for_sparse_profile():
    profile = ExtractedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title=None,
        email=None,
        homepage_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        office=None,
        research_directions=[],
        source_urls=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
    )

    assert is_structured_profile(profile) is False


def test_extract_profile_record_returns_extracted_profile_on_success():
    seed = _roster_seed()
    expected = ExtractedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title="教授",
        email="lizhi@sustech.edu.cn",
        homepage_url=seed.profile_url,
        profile_url=seed.profile_url,
        office=None,
        research_directions=[],
        source_urls=[seed.profile_url],
    )

    def _fake_fetch_html(url: str, timeout: float) -> str:
        assert url == seed.profile_url
        assert timeout == 12.0
        return "<html><body>ignored</body></html>"

    def _fake_extract_professor_profile(
        html: str,
        source_url: str,
        institution: str | None,
        department: str | None,
    ) -> ExtractedProfessorProfile:
        assert html == "<html><body>ignored</body></html>"
        assert source_url == seed.profile_url
        assert institution == "南方科技大学"
        assert department == "工学院"
        return expected

    extracted, error = extract_profile_record(
        roster_seed=seed,
        timeout=12.0,
        fetch_html=_fake_fetch_html,
        profile_extractor=_fake_extract_professor_profile,
    )

    assert extracted == expected
    assert error is None


def test_extract_profile_record_returns_error_string_when_fetch_fails():
    seed = _roster_seed()

    def _boom_fetch_html(url: str, timeout: float) -> str:
        del url, timeout
        raise ValueError("network timeout")

    extracted, error = extract_profile_record(
        roster_seed=seed,
        timeout=20.0,
        fetch_html=_boom_fetch_html,
    )

    assert extracted is None
    assert error == "ValueError: network timeout"


def test_build_profile_record_detaches_from_extracted_sequences():
    seed = _roster_seed()
    extracted_research_directions = ["机器学习"]
    extracted_source_urls = [seed.profile_url]
    extracted = ExtractedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title="教授",
        email="lizhi@sustech.edu.cn",
        homepage_url=seed.profile_url,
        profile_url=seed.profile_url,
        office=None,
        research_directions=extracted_research_directions,
        source_urls=extracted_source_urls,
    )

    record = build_profile_record(
        roster_seed=seed,
        extracted=extracted,
        extraction_status="structured",
        skip_reason=None,
    )
    extracted_research_directions.append("具身智能")
    extracted_source_urls.append("https://external.example.com/profile")

    assert record.research_directions == ("机器学习",)
    assert record.source_urls == (
        seed.profile_url,
        seed.source_url,
    )
    assert record.evidence == (
        seed.profile_url,
        seed.source_url,
    )


def test_exposed_profile_sequences_are_not_in_place_mutable():
    extracted = ExtractedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title=None,
        email=None,
        homepage_url=None,
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        office=None,
        research_directions=["机器学习"],
        source_urls=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
    )
    merged = MergedProfessorProfileRecord(
        name="李志",
        institution="南方科技大学",
        department="工学院",
        title=None,
        email=None,
        office=None,
        homepage=None,
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        source_urls=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
        evidence=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
        research_directions=["机器学习"],
        extraction_status="partial",
        skip_reason=None,
        error=None,
        roster_source="https://www.sustech.edu.cn/zh/faculties.html",
    )

    assert isinstance(extracted.research_directions, tuple)
    assert isinstance(extracted.source_urls, tuple)
    assert isinstance(merged.source_urls, tuple)
    assert isinstance(merged.evidence, tuple)
    assert isinstance(merged.research_directions, tuple)

    with pytest.raises(AttributeError):
        extracted.research_directions.append("具身智能")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        extracted.source_urls.append("https://other.example.com")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        merged.evidence.append("https://other.example.com")  # type: ignore[attr-defined]
