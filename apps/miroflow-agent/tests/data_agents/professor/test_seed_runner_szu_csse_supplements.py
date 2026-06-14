from __future__ import annotations

from typing import Any
from uuid import UUID

import requests

from src.data_agents.professor import seed_runner as seed_runner_module
from src.data_agents.professor.models import MergedProfessorProfileRecord, ProfessorRosterSeed
from src.data_agents.professor.publish_helpers import build_professor_id


def _profile(**overrides) -> MergedProfessorProfileRecord:
    defaults = {
        "name": "崔来中",
        "institution": "深圳大学",
        "department": "计算机与软件学院",
        "title": "教授",
        "email": None,
        "office": None,
        "homepage": "https://csse.szu.edu.cn/pages/user/index?id=1205",
        "profile_url": "https://csse.szu.edu.cn/pages/user/index?id=1205",
        "source_urls": (
            "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
            "https://csse.szu.edu.cn/pages/user/index?id=1205",
        ),
        "evidence": (
            "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
            "https://csse.szu.edu.cn/pages/user/index?id=1205",
        ),
        "research_directions": (),
        "extraction_status": "structured",
        "skip_reason": None,
        "error": None,
        "roster_source": "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
    }
    defaults.update(overrides)
    return MergedProfessorProfileRecord(**defaults)


def test_attach_szu_csse_supplements_matches_known_official_pages_by_name():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
    )
    profile = _profile()
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": "崔来中 科研成果 论文发表",
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": "张良杰 王璐 Rukhsana Ruby",
        "https://csse.szu.edu.cn/se/team-Staff": "明仲 潘微科",
    }

    updated = seed_runner_module._attach_szu_csse_official_supplement_sources(
        seed,
        [profile],
        timeout=3.0,
        fetch_source_page=lambda url, timeout: pages.get(url, ""),
    )

    assert updated[0].profile_url == profile.profile_url
    assert updated[0].roster_source == profile.roster_source
    assert "https://bigdata.szu.edu.cn/kytd.htm" in updated[0].source_urls
    assert "https://bigdata.szu.edu.cn/kytd.htm" in updated[0].evidence
    assert "https://aisc.szu.edu.cn/AISC/Faculty.htm" not in updated[0].source_urls

    enriched = seed_runner_module._merged_to_enriched(updated[0])
    assert enriched.publication_evidence_urls == ["https://bigdata.szu.edu.cn/kytd.htm"]
    assert (
        enriched.field_provenance["source_page_role:https://bigdata.szu.edu.cn/kytd.htm"]
        == "official_publication_page"
    )


def test_attach_szu_csse_supplements_adds_supplement_publication_entry_pages():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
    )
    profiles = [
        _profile(),
        _profile(
            name="Liangjie Zhang",
            homepage="https://aisc.szu.edu.cn/info/1060/1268.htm",
            profile_url="https://aisc.szu.edu.cn/info/1060/1268.htm",
            roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            source_urls=(
                "https://aisc.szu.edu.cn/AISC/Faculty.htm",
                "https://aisc.szu.edu.cn/info/1060/1268.htm",
            ),
            evidence=(
                "https://aisc.szu.edu.cn/AISC/Faculty.htm",
                "https://aisc.szu.edu.cn/info/1060/1268.htm",
            ),
        ),
    ]
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": """
        <html><body>
          <a href="kycg/lwfb.htm" title="论文发表">论文发表</a>
          <div class="gbteam1 fr">
            <h3>崔来中</h3>
            <a href="info/1008/1184.htm">查看详情</a>
          </div>
        </body></html>
        """,
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": """
        <html><body>
          <a href="../kycg.htm" title="科研成果">科研成果</a>
          <a href="../kycg/a2025.htm" title="2025">2025</a>
          <main><a href="../info/1060/1268.htm">Liangjie Zhang</a></main>
        </body></html>
        """,
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }

    updated = seed_runner_module._attach_szu_csse_official_supplement_sources(
        seed,
        profiles,
        timeout=3.0,
        fetch_source_page=lambda url, timeout: pages.get(url, ""),
    )

    cui_enriched = seed_runner_module._merged_to_enriched(updated[0])
    zhang_enriched = seed_runner_module._merged_to_enriched(updated[1])

    assert "https://bigdata.szu.edu.cn/kycg/lwfb.htm" in cui_enriched.publication_evidence_urls
    assert "https://aisc.szu.edu.cn/kycg.htm" in zhang_enriched.publication_evidence_urls
    assert "https://aisc.szu.edu.cn/kycg/a2025.htm" in zhang_enriched.publication_evidence_urls
    assert (
        zhang_enriched.field_provenance[
            "source_page_role:https://aisc.szu.edu.cn/kycg.htm"
        ]
        == "official_publication_page"
    )


def test_attach_szu_csse_supplements_is_scoped_to_csse_seed():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="数学科学学院",
        roster_url="https://math.szu.edu.cn/szdw/szyl.htm",
    )
    profile = _profile(department="数学科学学院")
    calls: list[str] = []

    updated = seed_runner_module._attach_szu_csse_official_supplement_sources(
        seed,
        [profile],
        timeout=3.0,
        fetch_source_page=lambda url, timeout: calls.append(url) or "",
    )

    assert updated == [profile]
    assert calls == []


def test_collect_szu_csse_supplement_profiles_extracts_people_not_navigation_labels():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": """
        <html><body>
          <nav>
            <a href="index.htm">首页</a>
            <a href="whjs/xwzx1.htm">文化建设</a>
          </nav>
          <div class="gbteam1 fr">
            <h3>崔来中</h3>
            <p><em>研究方向</em>: 边缘计算、物联网</p>
            <a href="info/1008/1184.htm">查看详情</a>
          </div>
          <div class="gbteam1 fr">
            <h3>文化建设</h3>
            <p><em>研究方向</em>: 导航栏目</p>
            <a href="info/1008/9999.htm">查看详情</a>
          </div>
        </body></html>
        """,
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": """
        <html><body>
          <nav>
            <a href="About.htm">About</a>
            <a href="Faculty.htm">Faculty</a>
          </nav>
          <main>
            <a href="../info/1060/1268.htm">Liangjie Zhang</a>
            <a href="../info/1060/1269.htm">Lu Wang</a>
            <a href="../info/1054/1408.htm">文化建设</a>
          </main>
        </body></html>
        """,
        "https://csse.szu.edu.cn/se/team-Staff": "",
    }

    profiles = seed_runner_module._collect_szu_csse_official_supplement_profiles(
        seed,
        timeout=3.0,
        fetch_source_page=lambda url, timeout: pages.get(url, ""),
    )

    assert [(profile.name, profile.profile_url) for profile in profiles] == [
        ("崔来中", "https://bigdata.szu.edu.cn/info/1008/1184.htm"),
        ("Liangjie Zhang", "https://aisc.szu.edu.cn/info/1060/1268.htm"),
        ("Lu Wang", "https://aisc.szu.edu.cn/info/1060/1269.htm"),
    ]
    assert profiles[0].research_directions == ("边缘计算、物联网",)
    assert profiles[0].roster_source == "https://bigdata.szu.edu.cn/kytd.htm"
    assert "https://bigdata.szu.edu.cn/kytd.htm" in profiles[0].source_urls
    assert "https://bigdata.szu.edu.cn/info/1008/1184.htm" in profiles[0].evidence


def test_collect_szu_csse_supplement_profiles_extracts_csse_lab_staff_page():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    pages = {
        "https://bigdata.szu.edu.cn/kytd.htm": "",
        "https://aisc.szu.edu.cn/AISC/Faculty.htm": "",
        "https://csse.szu.edu.cn/se/team-Staff": """
        <html><body>
          <nav>
            <a href="/se/index">团队首页</a>
            <a href="/se/news">新闻动态</a>
          </nav>
          <section class="staff-list">
            <article>
              <h3>明仲</h3>
              <p>研究方向：软件工程、智能软件</p>
              <a href="/se/member/mingzhong">个人主页</a>
            </article>
            <article>
              <h3>潘微科</h3>
              <a href="https://csse.szu.edu.cn/se/member/panweike">Homepage</a>
            </article>
            <article>
              <h3>科研团队</h3>
              <a href="/se/team">查看详情</a>
            </article>
          </section>
        </body></html>
        """,
    }

    profiles = seed_runner_module._collect_szu_csse_official_supplement_profiles(
        seed,
        timeout=3.0,
        fetch_source_page=lambda url, timeout: pages.get(url, ""),
    )

    assert [(profile.name, profile.profile_url) for profile in profiles] == [
        ("明仲", "https://csse.szu.edu.cn/se/member/mingzhong"),
        ("潘微科", "https://csse.szu.edu.cn/se/member/panweike"),
    ]
    assert profiles[0].research_directions == ("软件工程、智能软件",)
    assert profiles[0].roster_source == "https://csse.szu.edu.cn/se/team-Staff"


def test_szu_csse_scope_accepts_only_person_shaped_supplement_profiles():
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )

    assert seed_runner_module._profile_matches_seed_scope(
        seed,
        _profile(
            name="Liangjie Zhang",
            homepage="https://aisc.szu.edu.cn/info/1060/1268.htm",
            profile_url="https://aisc.szu.edu.cn/info/1060/1268.htm",
            roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            source_urls=(
                "https://aisc.szu.edu.cn/AISC/Faculty.htm",
                "https://aisc.szu.edu.cn/info/1060/1268.htm",
            ),
            evidence=(
                "https://aisc.szu.edu.cn/AISC/Faculty.htm",
                "https://aisc.szu.edu.cn/info/1060/1268.htm",
            ),
        ),
    )
    assert not seed_runner_module._profile_matches_seed_scope(
        seed,
        _profile(
            name="Faculty",
            homepage="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            profile_url="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
            source_urls=("https://aisc.szu.edu.cn/AISC/Faculty.htm",),
            evidence=("https://aisc.szu.edu.cn/AISC/Faculty.htm",),
        ),
    )


def test_fetch_szu_csse_supplement_source_page_strips_proxy_env(monkeypatch):
    observed_trust_env: list[bool] = []

    class FakeSession:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, *, timeout, headers):
            del url, timeout, headers
            observed_trust_env.append(self.trust_env)
            response = requests.Response()
            response.status_code = 200
            response._content = "崔来中 科研成果".encode("utf-8")
            response.headers["Content-Type"] = "text/html"
            response.encoding = "ISO-8859-1"
            return response

    monkeypatch.setattr(requests, "Session", FakeSession)

    html = seed_runner_module._fetch_szu_csse_supplement_source_page_no_env(
        "https://bigdata.szu.edu.cn/kytd.htm",
        timeout=5.0,
    )

    assert html == "崔来中 科研成果"
    assert observed_trust_env == [False]


def test_szu_csse_supplement_fetch_caps_each_source_timeout():
    observed_timeouts: list[float] = []

    seed_runner_module._fetch_szu_csse_official_supplement_pages(
        timeout=45.0,
        fetch_source_page=lambda _url, timeout: observed_timeouts.append(timeout) or "",
    )

    assert len(observed_timeouts) == 3
    assert all(timeout <= 5.0 for timeout in observed_timeouts)


def test_default_profile_writer_passes_enrichment_timeout(monkeypatch):
    profile = _profile()
    observed: dict[str, float] = {}

    def fake_enrich(
        merged: MergedProfessorProfileRecord,
        *,
        run_id: str,
        timeout: float | None,
    ):
        del run_id
        observed["timeout"] = timeout or 0.0
        return seed_runner_module._merged_to_enriched(merged), []

    def fake_write_professor_bundle(
        _conn,
        *,
        enriched,
        paper_staging,
        official_profile_page_id,
        run_id,
    ):
        del _conn, enriched, paper_staging, official_profile_page_id, run_id

    monkeypatch.setattr(seed_runner_module, "_enrich_profile_for_seed_write", fake_enrich)
    monkeypatch.setattr(
        seed_runner_module,
        "upsert_source_page_for_url",
        lambda *_args, **_kwargs: UUID("00000000-0000-0000-0000-000000000001"),
    )
    monkeypatch.setattr(
        seed_runner_module,
        "write_professor_bundle",
        fake_write_professor_bundle,
    )

    seed_runner_module._default_profile_writer(
        object(),
        profile=profile,
        run_id="00000000-0000-0000-0000-000000000002",
        enrichment_timeout=3.5,
    )

    assert observed["timeout"] == 3.5


def test_default_profile_writer_persists_owned_homepage_recursion_sources(monkeypatch):
    profile = _profile(
        name="NAKAMURA, Satoshi",
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        homepage="https://sai.cuhk.edu.cn/teacher/104",
        profile_url="https://sai.cuhk.edu.cn/teacher/104",
        roster_source="https://sai.cuhk.edu.cn/teacher/104",
    )
    official_profile = seed_runner_module._merged_to_enriched(profile)
    professor_id = build_professor_id(official_profile)
    personal_url = "https://satoshi.example.com/"
    academic_profile_url = "https://scholar.google.com/citations?user=satoshi"
    enriched = official_profile.model_copy(
        update={
            "field_provenance": {
                f"source_page_role:{personal_url}": "personal_homepage",
                f"source_page_role:{academic_profile_url}": "official_external_profile",
            },
            "publication_evidence_urls": [personal_url],
        }
    )
    upserts: list[dict[str, Any]] = []
    ledger_entries: list[dict[str, Any]] = []

    def fake_enrich(
        _profile: MergedProfessorProfileRecord,
        *,
        run_id: str,
        timeout: float | None,
    ):
        del run_id, timeout
        return enriched, []

    def fake_upsert_source_page_for_url(*_args: Any, **kwargs: Any) -> UUID:
        upserts.append(kwargs)
        return UUID(f"00000000-0000-0000-0000-{len(upserts):012d}")

    def fake_record_homepage_recursion_processed(_conn: Any, **kwargs: Any) -> UUID:
        ledger_entries.append(kwargs)
        return UUID("00000000-0000-0000-0000-000000000099")

    def fake_write_professor_bundle(
        _conn: Any,
        *,
        enriched,
        paper_staging,
        official_profile_page_id,
        run_id,
    ) -> None:
        del _conn, enriched, paper_staging, official_profile_page_id, run_id

    monkeypatch.setattr(seed_runner_module, "_enrich_profile_for_seed_write", fake_enrich)
    monkeypatch.setattr(
        seed_runner_module,
        "upsert_source_page_for_url",
        fake_upsert_source_page_for_url,
    )
    monkeypatch.setattr(
        seed_runner_module,
        "record_homepage_recursion_processed",
        fake_record_homepage_recursion_processed,
        raising=False,
    )
    monkeypatch.setattr(
        seed_runner_module,
        "write_professor_bundle",
        fake_write_professor_bundle,
    )

    seed_runner_module._default_profile_writer(
        object(),
        profile=profile,
        run_id="00000000-0000-0000-0000-000000000123",
        enrichment_timeout=3.5,
    )

    assert [entry["url"] for entry in upserts] == [
        "https://sai.cuhk.edu.cn/teacher/104",
        personal_url,
    ]
    assert upserts[1] == {
        "url": personal_url,
        "page_role": "personal_homepage",
        "owner_scope_kind": "professor",
        "owner_scope_ref": professor_id,
        "fetched_at": upserts[1]["fetched_at"],
        "is_official_source": False,
        "run_id": "00000000-0000-0000-0000-000000000123",
    }
    assert ledger_entries == [
        {
            "run_id": "00000000-0000-0000-0000-000000000123",
            "professor_id": professor_id,
            "url": personal_url,
            "page_role": "personal_homepage",
            "discovery_source": "official_profile_anchor",
            "recursion_depth": 1,
            "parent_source_page_id": UUID("00000000-0000-0000-0000-000000000001"),
            "source_page_id": UUID("00000000-0000-0000-0000-000000000002"),
        }
    ]


def test_seed_llm_client_disables_sdk_retries():
    client, model = seed_runner_module._build_seed_llm_client(
        lambda *_args, **_kwargs: {
            "local_llm_base_url": "http://127.0.0.1:9/v1",
            "local_llm_api_key": "EMPTY",
            "local_llm_model": "test-model",
        },
        timeout_seconds=3.0,
    )

    try:
        assert model == "test-model"
        assert client.max_retries == 0
    finally:
        client.close()


def test_budgeted_seed_enrichment_skips_uninterruptible_llm_by_default(monkeypatch):
    profile = _profile()
    called = False

    async def fake_async_enrich(*_args, **_kwargs):
        nonlocal called
        called = True
        return seed_runner_module._merged_to_enriched(profile), []

    monkeypatch.delenv("PROFESSOR_SEED_ENABLE_BOUNDED_LLM_HOMEPAGE_CRAWL", raising=False)
    monkeypatch.setattr(
        seed_runner_module,
        "_enrich_profile_for_seed_write_async",
        fake_async_enrich,
    )

    enriched, paper_staging = seed_runner_module._enrich_profile_for_seed_write(
        profile,
        run_id="00000000-0000-0000-0000-000000000001",
        timeout=9.0,
    )

    assert called is False
    assert enriched.name == profile.name
    assert paper_staging == []
