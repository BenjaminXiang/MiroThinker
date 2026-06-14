from __future__ import annotations

from src.data_agents.professor import seed_runner as seed_runner_module
from src.data_agents.professor.models import MergedProfessorProfileRecord, ProfessorRosterSeed


def _seed() -> ProfessorRosterSeed:
    return ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="理工学院",
        roster_url="https://sse.cuhk.edu.cn/teacher-search",
    )


def _profile(**overrides) -> MergedProfessorProfileRecord:
    defaults = {
        "name": "黄乃正",
        "institution": "香港中文大学（深圳）",
        "department": "理工学院",
        "title": None,
        "email": None,
        "office": None,
        "homepage": "https://myweb.cuhk.edu.cn/hncwong",
        "profile_url": "https://myweb.cuhk.edu.cn/hncwong",
        "source_urls": ("https://sse.cuhk.edu.cn/teacher-search",),
        "evidence": ("https://sse.cuhk.edu.cn/teacher-search",),
        "research_directions": (),
        "extraction_status": "structured",
        "skip_reason": None,
        "error": None,
        "roster_source": "https://sse.cuhk.edu.cn/teacher-search",
        "profile_raw_text": None,
    }
    defaults.update(overrides)
    return MergedProfessorProfileRecord(**defaults)


_CUHK_SSE_ROSTER_HTML = """
<html><body>
  <section class="view-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/hncwong" target="_blank">黄乃正</a>
      </div>
      <div class="list-des">校长学勤讲座教授</div>
      <div class="list-des">中国科学院院士、发展中国家科学院院士、香港科学院院士</div>
      <div class="list-area"><span>学术领域: </span>化学，材料学</div>
      <div class="list-email"><span>电子邮件: </span>hncwong@cuhk.edu.cn</div>
      <div class="list-area"><span>研究领域: </span>天然与非天然有机分子合成；合成方法学</div>
      <div class="list-website"><span>个人网站: </span>
        <a href="https://chem.cuhk.edu.hk/people/academic-staff/wnc/">
          https://chem.cuhk.edu.hk/people/academic-staff/wnc/
        </a>
      </div>
    </div>
    <div class="list-text">
      <div class="list-title">
        <a href="https://mypage.cuhk.edu.cn/academics/lizhen/">Deep Bit lab</a>
      </div>
      <div class="list-area"><span>研究领域: </span>实验室新闻</div>
    </div>
  </section>
</body></html>
"""


def test_extract_cuhk_teacher_search_roster_profiles_uses_card_facts_and_rejects_navigation():
    profiles = seed_runner_module._extract_cuhk_teacher_search_roster_profiles(
        _seed(),
        source_url="https://sse.cuhk.edu.cn/teacher-search",
        html=_CUHK_SSE_ROSTER_HTML,
    )

    assert [profile.name for profile in profiles] == ["黄乃正"]
    profile = profiles[0]
    assert profile.title == "校长学勤讲座教授"
    assert profile.email == "hncwong@cuhk.edu.cn"
    assert profile.homepage == "https://chem.cuhk.edu.hk/people/academic-staff/wnc/"
    assert profile.profile_url == "https://myweb.cuhk.edu.cn/hncwong"
    assert profile.research_directions == ("天然与非天然有机分子合成", "合成方法学")
    assert profile.profile_raw_text is not None
    assert "Deep Bit lab" not in profile.profile_raw_text


def test_attach_cuhk_teacher_search_roster_supplements_fills_missing_profile_fields():
    updated = seed_runner_module._attach_cuhk_teacher_search_roster_supplements(
        _seed(),
        [_profile()],
        timeout=3.0,
        fetch_source_page=lambda url, timeout: _CUHK_SSE_ROSTER_HTML,
    )

    assert len(updated) == 1
    assert updated[0].title == "校长学勤讲座教授"
    assert updated[0].email == "hncwong@cuhk.edu.cn"
    assert updated[0].homepage == "https://chem.cuhk.edu.hk/people/academic-staff/wnc/"
    assert updated[0].research_directions == ("天然与非天然有机分子合成", "合成方法学")
    assert updated[0].profile_url == "https://myweb.cuhk.edu.cn/hncwong"
    assert "https://sse.cuhk.edu.cn/teacher-search" in updated[0].source_urls


def test_attach_cuhk_teacher_search_roster_supplements_replaces_polluted_short_title():
    updated = seed_runner_module._attach_cuhk_teacher_search_roster_supplements(
        _seed(),
        [_profile(title="s")],
        timeout=3.0,
        fetch_source_page=lambda url, timeout: _CUHK_SSE_ROSTER_HTML,
    )

    assert updated[0].title == "校长学勤讲座教授"
