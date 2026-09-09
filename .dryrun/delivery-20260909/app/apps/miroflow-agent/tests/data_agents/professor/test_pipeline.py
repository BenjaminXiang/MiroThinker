from __future__ import annotations

from pathlib import Path

from src.data_agents.professor.discovery import (
    DiscoverySourceStatus,
    ProfessorSeedDiscoveryResult,
)
from src.data_agents.professor.models import (
    DiscoveredProfessorSeed,
    ExtractedProfessorProfile,
    ProfessorRosterSeed,
)
from src.data_agents.professor.pipeline import run_professor_pipeline


def test_run_professor_pipeline_builds_records_and_counts(tmp_path: Path):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "\n".join(
            [
                "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
                "深圳大学 https://www.szu.edu.cn/szdw/jsjj.htm",
            ]
        ),
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="李志",
                institution="南方科技大学",
                department="工学院",
                profile_url="https://cse.sustech.edu.cn/faculty/lizhi/",
                source_url="https://www.sustech.edu.cn/zh/letter/",
            ),
            DiscoveredProfessorSeed(
                name="李志",
                institution="南方科技大学",
                department="工学院",
                profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
                source_url="https://www.sustech.edu.cn/zh/letter/",
            ),
            DiscoveredProfessorSeed(
                name="王五",
                institution="深圳大学",
                department="计算机与软件学院",
                profile_url="https://scholar.google.com/citations?user=demo",
                source_url="https://www.szu.edu.cn/szdw/jsjj.htm",
            ),
        ],
        source_statuses=[
            DiscoverySourceStatus(
                seed_url="https://www.sustech.edu.cn/zh/letter/",
                institution="南方科技大学",
                department=None,
                status="ok",
                reason="ok",
                visited_urls=["https://www.sustech.edu.cn/zh/letter/"],
                discovered_professor_count=2,
            ),
            DiscoverySourceStatus(
                seed_url="https://www.szu.edu.cn/szdw/jsjj.htm",
                institution="深圳大学",
                department=None,
                status="ok",
                reason="ok",
                visited_urls=["https://www.szu.edu.cn/szdw/jsjj.htm"],
                discovered_professor_count=1,
            ),
        ],
        failed_fetch_urls=["https://broken.example.edu/list"],
    )
    fetched_profile_urls: list[str] = []

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        assert timeout == 15.0
        assert len(seeds) == 2
        return discovery

    def fake_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        assert timeout == 15.0
        fetched_profile_urls.append(roster_seed.profile_url)
        return (
            ExtractedProfessorProfile(
                name=roster_seed.name,
                institution=roster_seed.institution,
                department=roster_seed.department,
                title="教授",
                email="lizhi@sustech.edu.cn",
                homepage_url=roster_seed.profile_url,
                profile_url=roster_seed.profile_url,
                office="工学院南楼",
                research_directions=["机器学习"],
                source_urls=[roster_seed.profile_url],
            ),
            None,
        )

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=15.0,
        official_domain_suffixes=("sustech.edu.cn", "szu.edu.cn"),
        include_external_profiles=False,
        discover_professors=fake_discover,
        extract_profile=fake_extract,
        max_workers=1,
    )

    assert fetched_profile_urls == ["https://cse.sustech.edu.cn/faculty/lizhi/"]
    assert [profile.extraction_status for profile in result.profiles] == [
        "structured",
        "skipped",
    ]
    assert result.profiles[1].skip_reason == "external_profile_domain_not_allowed_by_default"
    assert result.report.seed_url_count == 2
    assert result.report.discovered_professor_count == 3
    assert result.report.unique_professor_count == 2
    assert result.report.duplicate_professor_count == 1
    assert result.report.failed_roster_fetch_count == 1
    assert result.report.official_profile_candidate_count == 1
    assert result.report.profile_fetch_success_count == 1
    assert result.report.profile_fetch_failed_count == 0
    assert result.report.skipped_external_profile_count == 1
    assert result.report.structured_profile_count == 1
    assert result.report.partial_profile_count == 0


def test_run_professor_pipeline_marks_failed_profile_fetch(tmp_path: Path):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "清华大学深圳国际研究生院 https://www.sigs.tsinghua.edu.cn/7644/list.htm",
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="李立浧",
                institution="清华大学深圳国际研究生院",
                department="自动化与智能制造学院",
                profile_url="https://www.sigs.tsinghua.edu.cn/llyys/main.htm",
                source_url="https://www.sigs.tsinghua.edu.cn/7644/list.htm",
            )
        ],
        source_statuses=[],
        failed_fetch_urls=[],
    )

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        del seeds, timeout
        return discovery

    def fake_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        del roster_seed, timeout
        return None, "RuntimeError: timeout"

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=20.0,
        official_domain_suffixes=("sigs.tsinghua.edu.cn",),
        include_external_profiles=True,
        discover_professors=fake_discover,
        extract_profile=fake_extract,
        max_workers=1,
    )

    assert len(result.profiles) == 1
    assert result.profiles[0].extraction_status == "failed"
    assert result.profiles[0].error == "RuntimeError: timeout"
    assert result.report.profile_fetch_success_count == 0
    assert result.report.profile_fetch_failed_count == 1


def test_run_professor_pipeline_can_skip_profile_fetch(tmp_path: Path):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="李志",
                institution="南方科技大学",
                department="工学院",
                profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
                source_url="https://www.sustech.edu.cn/zh/letter/",
            )
        ],
        source_statuses=[],
        failed_fetch_urls=[],
    )

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        del seeds, timeout
        return discovery

    def fail_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        raise AssertionError(f"profile fetch should be skipped for {roster_seed.profile_url} / {timeout}")

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=20.0,
        official_domain_suffixes=("sustech.edu.cn",),
        include_external_profiles=True,
        skip_profile_fetch=True,
        discover_professors=fake_discover,
        extract_profile=fail_extract,
        max_workers=1,
    )

    assert len(result.profiles) == 1
    assert result.profiles[0].extraction_status == "skipped"
    assert result.profiles[0].skip_reason == "profile_fetch_disabled"
    assert result.report.profile_fetch_success_count == 0
    assert result.report.profile_fetch_failed_count == 0
    assert result.report.skipped_external_profile_count == 1


def test_run_professor_pipeline_treats_pku_subdomains_as_official_for_pkusz(tmp_path: Path):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "北京大学深圳研究生院 https://www.pkusz.edu.cn/szdw.htm",
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="李华",
                institution="北京大学深圳研究生院",
                department="信息工程学院",
                profile_url="https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/lihua",
                source_url="https://www.pkusz.edu.cn/szdw.htm",
            )
        ],
        source_statuses=[],
        failed_fetch_urls=[],
    )
    fetched_profile_urls: list[str] = []

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        del seeds, timeout
        return discovery

    def fake_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        del timeout
        fetched_profile_urls.append(roster_seed.profile_url)
        return (
            ExtractedProfessorProfile(
                name=roster_seed.name,
                institution=roster_seed.institution,
                department=roster_seed.department,
                title="教授",
                email="lihua@pku.edu.cn",
                homepage_url=roster_seed.profile_url,
                profile_url=roster_seed.profile_url,
                office="A101",
                research_directions=["金融科技"],
                source_urls=[roster_seed.profile_url],
            ),
            None,
        )

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=20.0,
        official_domain_suffixes=(),
        include_external_profiles=False,
        discover_professors=fake_discover,
        extract_profile=fake_extract,
        max_workers=1,
    )

    assert fetched_profile_urls == ["https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/lihua"]
    assert result.report.official_profile_candidate_count == 1
    assert result.report.skipped_external_profile_count == 0


def test_run_professor_pipeline_surfaces_extractor_exception(tmp_path: Path):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "深圳技术大学 https://www.sut.edu.cn/faculty",
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="徐英",
                institution="深圳技术大学",
                department="工程学院",
                profile_url="https://www.sut.edu.cn/faculty/ying",
                source_url="https://www.sut.edu.cn/faculty",
            )
        ],
        source_statuses=[],
        failed_fetch_urls=[],
    )

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        del seeds, timeout
        return discovery

    def fake_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        del roster_seed, timeout
        raise RuntimeError("boom")

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=10.0,
        official_domain_suffixes=("sut.edu.cn",),
        include_external_profiles=True,
        discover_professors=fake_discover,
        extract_profile=fake_extract,
        max_workers=1,
    )

    assert len(result.profiles) == 1
    failure_record = result.profiles[0]
    assert failure_record.extraction_status == "failed"
    assert failure_record.error == "RuntimeError: boom"
    assert result.report.profile_fetch_success_count == 0
    assert result.report.profile_fetch_failed_count == 1


def test_run_professor_pipeline_prefers_official_profile_for_duplicate_identity(
    tmp_path: Path,
):
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(
        "南方科技大学 https://www.sustech.edu.cn/zh/letter/",
        encoding="utf-8",
    )
    discovery = ProfessorSeedDiscoveryResult(
        professors=[
            DiscoveredProfessorSeed(
                name="李志",
                institution="南方科技大学",
                department="工学院",
                profile_url="https://scholar.google.com/citations?user=demo",
                source_url="https://www.sustech.edu.cn/zh/letter/",
            ),
            DiscoveredProfessorSeed(
                name="李志",
                institution="南方科技大学",
                department="工学院",
                profile_url="https://cse.sustech.edu.cn/faculty/lizhi/",
                source_url="https://www.sustech.edu.cn/zh/letter/",
            ),
        ],
        source_statuses=[],
        failed_fetch_urls=[],
    )
    fetched_profile_urls: list[str] = []

    def fake_discover(
        seeds: list[ProfessorRosterSeed],
        timeout: float,
    ) -> ProfessorSeedDiscoveryResult:
        del seeds, timeout
        return discovery

    def fake_extract(
        roster_seed: DiscoveredProfessorSeed,
        timeout: float,
    ) -> tuple[ExtractedProfessorProfile | None, str | None]:
        del timeout
        fetched_profile_urls.append(roster_seed.profile_url)
        return (
            ExtractedProfessorProfile(
                name=roster_seed.name,
                institution=roster_seed.institution,
                department=roster_seed.department,
                title="教授",
                email="lizhi@sustech.edu.cn",
                homepage_url=roster_seed.profile_url,
                profile_url=roster_seed.profile_url,
                office="工学院南楼",
                research_directions=["机器学习"],
                source_urls=[roster_seed.profile_url],
            ),
            None,
        )

    result = run_professor_pipeline(
        seed_doc=seed_doc,
        timeout=20.0,
        official_domain_suffixes=("sustech.edu.cn",),
        include_external_profiles=False,
        discover_professors=fake_discover,
        extract_profile=fake_extract,
        max_workers=1,
    )

    assert fetched_profile_urls == ["https://cse.sustech.edu.cn/faculty/lizhi/"]
    assert len(result.profiles) == 1
    assert result.profiles[0].profile_url == "https://cse.sustech.edu.cn/faculty/lizhi/"
    assert result.profiles[0].extraction_status == "structured"
