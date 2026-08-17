from __future__ import annotations

from src.data_agents.professor.models import (
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from src.data_agents.professor.seed_runner import (
    _attach_szu_csse_official_supplement_sources,
    _collect_szu_csse_official_supplement_profiles,
    _fetch_szu_csse_official_supplement_pages,
    _fetch_szu_csse_supplement_source_page_no_env,
    _merged_to_enriched,
    _profile_matches_seed_scope,
)


def _seed() -> ProfessorRosterSeed:
    return ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )


def _profile(
    *,
    name: str,
    profile_url: str = "https://csse.szu.edu.cn/pages/user/index?id=611",
    source_urls: tuple[str, ...] | None = None,
    evidence: tuple[str, ...] | None = None,
    roster_source: str = "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
) -> MergedProfessorProfileRecord:
    source_urls = source_urls or (profile_url,)
    evidence = evidence or (profile_url,)
    return MergedProfessorProfileRecord(
        name=name,
        institution="深圳大学",
        department="计算机与软件学院",
        title="教授",
        email=None,
        office=None,
        homepage=profile_url,
        profile_url=profile_url,
        source_urls=source_urls,
        evidence=evidence,
        research_directions=(),
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source=roster_source,
    )


def test_collects_szu_csse_official_supplement_profiles_without_nav_pollution():
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": """
        <html><body>
          <div class="gbteam1 fr">
            <a href="info/1008/1185.htm">查看详情</a>
            <h3>黄哲学</h3>
            <p><em>研究方向</em>: 大数据近似计算</p>
          </div>
          <div class="gbteam1 fr">
            <a href="info/1008/1184.htm"><img alt="崔来中" /></a>
            <h3>崔来中</h3>
            <p><em>研究方向</em>：边缘计算、物联网</p>
          </div>
          <div class="gbteam1 fr"><h3>文化建设</h3><a href="whjs.htm">更多</a></div>
        </body></html>
        """,
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": """
        <html><body>
          <nav><a href="/AISC/Faculty.htm">Faculty</a></nav>
          <main>
            <a href="../info/1060/1268.htm">Liangjie Zhang</a>
            <a href="../info/1060/1299.htm">Lu Wang</a>
            <a href="../culture.htm">文化建设</a>
          </main>
        </body></html>
        """,
        "https://csse.szu.edu.cn/se/team-Staff": """
        <html><body>
          <section class="staff-list">
            <article>
              <h3>明仲</h3>
              <p>研究方向：软件工程、智能软件</p>
              <a href="/se/member/mingzhong">个人主页</a>
            </article>
            <article><h3>科研团队</h3><a href="/se/team">详情</a></article>
          </section>
        </body></html>
        """,
    }

    profiles = _collect_szu_csse_official_supplement_profiles(
        _seed(),
        timeout=45.0,
        fetch_source_page=lambda url, timeout: pages[url],
    )

    by_name = {profile.name: profile for profile in profiles}
    assert set(by_name) == {"黄哲学", "崔来中", "Liangjie Zhang", "Lu Wang", "明仲"}
    assert (
        by_name["黄哲学"].profile_url
        == "https://bigdata.szu.edu.cn/info/1008/1185.htm"
    )
    assert by_name["崔来中"].research_directions == ("边缘计算、物联网",)
    assert (
        by_name["崔来中"].profile_url
        == "https://bigdata.szu.edu.cn/info/1008/1184.htm"
    )
    assert (
        by_name["Liangjie Zhang"].profile_url
        == "https://aisc.szu.edu.cn/info/1060/1268.htm"
    )
    assert by_name["明仲"].profile_url == "https://csse.szu.edu.cn/se/member/mingzhong"


def test_attach_szu_csse_supplement_sources_marks_publication_entry_pages():
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": """
        <html><body>
          <h3>崔来中</h3>
          <a href="kycg/lwfb.htm">论文发表</a>
        </body></html>
        """,
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": "",
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }
    profile = _profile(name="崔来中")

    [updated] = _attach_szu_csse_official_supplement_sources(
        _seed(),
        [profile],
        timeout=45.0,
        fetch_source_page=lambda url, timeout: pages[url],
    )
    enriched = _merged_to_enriched(updated)

    assert updated.source_urls == (
        "https://csse.szu.edu.cn/pages/user/index?id=611",
        "https://bigdata.szu.edu.cn/kytd.htm",
        "https://bigdata.szu.edu.cn/kycg/lwfb.htm",
    )
    assert enriched.publication_evidence_urls == [
        "https://bigdata.szu.edu.cn/kytd.htm",
        "https://bigdata.szu.edu.cn/kycg/lwfb.htm",
    ]
    assert enriched.field_provenance[
        "source_page_role:https://bigdata.szu.edu.cn/kytd.htm"
    ] == "official_publication_page"


def test_attach_szu_aisc_supplement_sources_marks_publication_entry_pages():
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": "",
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": """
        <html><body>
          <nav><a href="Faculty.htm">Faculty</a></nav>
          <a href="../kycg.htm">科研成果</a>
          <a href="../kycg/a2025.htm">2025</a>
          <a href="../whjs1/xwzx.htm">文化建设</a>
          <article>
            <a href="../info/1060/1268.htm"><p>Liangjie Zhang</p></a>
          </article>
        </body></html>
        """,
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }
    profile = _profile(
        name="Liangjie Zhang",
        profile_url="https://aisc.szu.edu.cn/info/1060/1268.htm",
        source_urls=("https://aisc.szu.edu.cn/info/1060/1268.htm",),
        evidence=("https://aisc.szu.edu.cn/info/1060/1268.htm",),
        roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
    )

    [updated] = _attach_szu_csse_official_supplement_sources(
        _seed(),
        [profile],
        timeout=45.0,
        fetch_source_page=lambda url, timeout: pages[url],
    )
    enriched = _merged_to_enriched(updated)

    assert enriched.publication_evidence_urls == [
        "https://aisc.szu.edu.cn/kycg.htm",
        "https://aisc.szu.edu.cn/kycg/a2025.htm",
    ]
    assert all("whjs" not in url for url in updated.evidence)


def test_attach_szu_csse_supplement_sources_keeps_unmatched_profiles_unchanged():
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": "<html><body><h3>崔来中</h3></body></html>",
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": "",
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }
    profile = _profile(name="谢科")

    [updated] = _attach_szu_csse_official_supplement_sources(
        _seed(),
        [profile],
        timeout=45.0,
        fetch_source_page=lambda url, timeout: pages[url],
    )

    assert updated == profile


def test_profile_matches_seed_scope_rejects_szu_csse_navigation_labels():
    assert _profile_matches_seed_scope(
        _seed(),
        _profile(
            name="Liangjie Zhang",
            profile_url="https://aisc.szu.edu.cn/info/1060/1268.htm",
            roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
        ),
    )
    assert not _profile_matches_seed_scope(
        _seed(),
        _profile(
            name="Faculty",
            profile_url="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
        ),
    )


def test_fetch_szu_csse_supplement_source_page_strips_proxy_env(monkeypatch):
    calls: list[tuple[bool, str, float]] = []

    class FakeResponse:
        content = "崔来中".encode()
        encoding = None
        apparent_encoding = "utf-8"

        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        trust_env = True

        def get(self, url: str, *, timeout: float, headers: dict[str, str]):
            calls.append((self.trust_env, url, timeout))
            assert "Mozilla" in headers["User-Agent"]
            return FakeResponse()

    monkeypatch.setattr(
        "src.data_agents.professor.seed_runner.requests.Session",
        FakeSession,
    )

    html = _fetch_szu_csse_supplement_source_page_no_env(
        "https://bigdata.szu.edu.cn/kytd.htm",
        timeout=45.0,
    )

    assert html == "崔来中"
    assert calls == [(False, "https://bigdata.szu.edu.cn/kytd.htm", 45.0)]


def test_fetch_szu_csse_official_supplement_pages_caps_per_source_timeout():
    calls: list[tuple[str, float]] = []

    pages = _fetch_szu_csse_official_supplement_pages(
        timeout=45.0,
        fetch_source_page=lambda url, timeout: calls.append((url, timeout)) or "",
    )

    assert pages == {
        "https://bigdata.szu.edu.cn/kytd.htm": "",
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": "",
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }
    assert len(calls) == 3
    assert all(timeout <= 5.0 for _, timeout in calls)
