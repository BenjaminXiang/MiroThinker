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


def test_extract_profile_record_uses_szu_csse_roster_card_before_blocked_detail():
    seed = DiscoveredProfessorSeed(
        name="梁中明",
        institution="深圳大学",
        department="计算机与软件学院",
        profile_url="https://csse.szu.edu.cn/pages/user/index?id=1077",
        source_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    roster_markdown = """
Title: 深圳大学计算机与软件学院

URL Source: https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1

Markdown Content:
院士

陈国良

![Image 15](https://csse.szu.edu.cn/attachment/userimg/chen.jpg)

中国科学院院士

![Image 16](https://csse.szu.edu.cn/attachment/userimg/chen.jpg)

[HOMEPAGE](https://csse.szu.edu.cn/pages/user/index?id=617)

梁中明

![Image 17](https://csse.szu.edu.cn/attachment/base64/leung.jpg)

加拿大三院院士

![Image 18](https://csse.szu.edu.cn/attachment/base64/leung.jpg)

[HOMEPAGE](https://csse.szu.edu.cn/pages/user/index?id=1077)

 vleung@szu.edu.cn ![Image 19](https://csse.szu.edu.cn/image/teacher_image/documents@2x.png)
    """
    requested_urls: list[str] = []

    def _fetch_html(url: str, timeout: float) -> str:
        assert timeout == 20.0
        requested_urls.append(url)
        if url == seed.profile_url:
            raise AssertionError("blocked CSSE detail page should not be fetched first")
        if url == seed.source_url:
            return roster_markdown
        if url == "https://bigdata.szu.edu.cn/kytd.htm":
            return "<html><body><div class='gbteam1'><h3>其他教师</h3></div></body></html>"
        raise AssertionError(url)

    extracted, error = extract_profile_record(
        roster_seed=seed,
        timeout=20.0,
        fetch_html=_fetch_html,
    )

    assert error is None
    assert extracted is not None
    assert requested_urls == [
        seed.source_url,
        "https://bigdata.szu.edu.cn/kytd.htm",
    ]
    assert extracted.name == "梁中明"
    assert extracted.title == "加拿大三院院士"
    assert extracted.email == "vleung@szu.edu.cn"
    assert extracted.profile_raw_text is not None
    assert "官方详情页：https://csse.szu.edu.cn/pages/user/index?id=1077" in (
        extracted.profile_raw_text
    )


def test_extract_profile_record_supplements_szu_csse_card_from_bigdata_index():
    seed = DiscoveredProfessorSeed(
        name="崔来中",
        institution="深圳大学",
        department="计算机与软件学院",
        profile_url="https://csse.szu.edu.cn/pages/user/index?id=1205",
        source_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
    )
    roster_markdown = """
Title: 深圳大学计算机与软件学院
Markdown Content:
崔来中

教授

[HOMEPAGE](https://csse.szu.edu.cn/pages/user/index?id=1205)

clz@szu.edu.cn
    """
    bigdata_index = """
    <html><body>
      <div class="gbteam1 fr">
        <h3>崔来中</h3>
        <p><em>研究方向</em>: 下一代互联网、边缘计算、联邦学习</p>
        <a href="info/1008/1184.htm">查看详情</a>
      </div>
    </body></html>
    """
    bigdata_detail = """
    <html><body>
      <div class="abm2">
        <div class="teamm1">崔来中</div>
        <div class="teamm2">
          <h3>个人简介</h3>
          <div class="teamm2_1">
            研究领域包括：下一代互联网体系结构、软件定义网络、边缘计算、大数据分析、机器学习和智能计算。
            已在国内外重要期刊以及国际会议上发表SCI/EI检索论文80余篇。
          </div>
          <h3>研究方向</h3>
          <div class="teamm2_2">下一代互联网、边缘计算、联邦学习</div>
        </div>
      </div>
    </body></html>
    """
    requested_urls: list[str] = []

    def _fetch_html(url: str, timeout: float) -> str:
        assert timeout == 20.0
        requested_urls.append(url)
        if url == seed.source_url:
            return roster_markdown
        if url == "https://bigdata.szu.edu.cn/kytd.htm":
            return bigdata_index
        if url == "https://bigdata.szu.edu.cn/info/1008/1184.htm":
            return bigdata_detail
        raise AssertionError(url)

    extracted, error = extract_profile_record(
        roster_seed=seed,
        timeout=20.0,
        fetch_html=_fetch_html,
    )

    assert error is None
    assert extracted is not None
    assert requested_urls == [
        seed.source_url,
        "https://bigdata.szu.edu.cn/kytd.htm",
        "https://bigdata.szu.edu.cn/info/1008/1184.htm",
    ]
    assert extracted.name == "崔来中"
    assert extracted.email == "clz@szu.edu.cn"
    assert extracted.homepage_url == "https://bigdata.szu.edu.cn/info/1008/1184.htm"
    assert "软件定义网络" in (extracted.profile_raw_text or "")
    assert "https://bigdata.szu.edu.cn/info/1008/1184.htm" in extracted.source_urls
    assert extracted.research_directions == ("下一代互联网", "边缘计算", "联邦学习")


def test_extract_profile_record_caches_szu_csse_shared_supplement_pages():
    seeds = [
        DiscoveredProfessorSeed(
            name="崔来中",
            institution="深圳大学",
            department="计算机与软件学院",
            profile_url="https://csse.szu.edu.cn/pages/user/index?id=1205",
            source_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
        ),
        DiscoveredProfessorSeed(
            name="黄哲学",
            institution="深圳大学",
            department="计算机与软件学院",
            profile_url="https://csse.szu.edu.cn/pages/user/index?id=617",
            source_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
        ),
    ]
    roster_markdown = """
崔来中
教授
[HOMEPAGE](https://csse.szu.edu.cn/pages/user/index?id=1205)
clz@szu.edu.cn

黄哲学
教授
[HOMEPAGE](https://csse.szu.edu.cn/pages/user/index?id=617)
hzx@szu.edu.cn
    """
    bigdata_index = """
    <html><body>
      <div class="gbteam1 fr"><h3>崔来中</h3><a href="info/1008/1184.htm">查看详情</a></div>
      <div class="gbteam1 fr"><h3>黄哲学</h3><a href="info/1008/1185.htm">查看详情</a></div>
    </body></html>
    """
    detail_by_url = {
        "https://bigdata.szu.edu.cn/info/1008/1184.htm": """
        <html><body><div class="abm2"><div class="teamm1">崔来中</div>
        <div class="teamm2"><h3>个人简介</h3><div class="teamm2_1">软件定义网络。</div>
        <h3>研究方向</h3><div class="teamm2_2">边缘计算、联邦学习</div></div></div></body></html>
        """,
        "https://bigdata.szu.edu.cn/info/1008/1185.htm": """
        <html><body><div class="abm2"><div class="teamm1">黄哲学</div>
        <div class="teamm2"><h3>个人简介</h3><div class="teamm2_1">大数据近似计算。</div>
        <h3>研究方向</h3><div class="teamm2_2">大数据近似计算、RSP平台</div></div></div></body></html>
        """,
    }
    fetch_counts: dict[str, int] = {}

    def _fetch_html(url: str, timeout: float) -> str:
        del timeout
        fetch_counts[url] = fetch_counts.get(url, 0) + 1
        if url == seeds[0].source_url:
            return roster_markdown
        if url == "https://bigdata.szu.edu.cn/kytd.htm":
            return bigdata_index
        if url in detail_by_url:
            return detail_by_url[url]
        raise AssertionError(url)

    for seed in seeds:
        extracted, error = extract_profile_record(
            roster_seed=seed,
            timeout=20.0,
            fetch_html=_fetch_html,
        )
        assert error is None
        assert extracted is not None

    assert fetch_counts[seeds[0].source_url] == 1
    assert fetch_counts["https://bigdata.szu.edu.cn/kytd.htm"] == 1
    assert fetch_counts["https://bigdata.szu.edu.cn/info/1008/1184.htm"] == 1
    assert fetch_counts["https://bigdata.szu.edu.cn/info/1008/1185.htm"] == 1


def test_extract_profile_record_carries_sigs_tab_structured_fields():
    seed = DiscoveredProfessorSeed(
        name="Ahmed Elazab",
        institution="清华大学深圳国际研究生院",
        department=None,
        profile_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
        source_url="https://www.sigs.tsinghua.edu.cn/7644/list.htm",
    )
    html = """
    <html><body>
      <div class="teacher_right">
        Ahmed Elazab 助理教授 ， 博士生导师
        邮箱：ahmedelazab@sz.tsinghua.edu.cn
        <div class="sudy-tab">
          <ul class="tab-menu">
            <li><span>个人简历</span></li>
            <li><span>研究领域</span></li>
            <li><span>奖励荣誉</span></li>
          </ul>
          <ul class="tab-list">
            <li>
              <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
                <div class="con"><p>09/2012-01/2017, University of Chinese Academy of Sciences, Pattern Recognition &amp; Intelligent Systems, PhD</p></div>
              </div>
              <div class="post"><h3 class="tit"><span class="title">工作经历</span></h3>
                <div class="con"><p>08/2017 -04/2020, Postdoctoral Fellow, Shenzhen University</p></div>
              </div>
              <div class="post"><h3 class="tit"><span class="title">学术兼职</span></h3>
                <div class="con"><p>PeerJ Computer Science, Academic Editor</p></div>
              </div>
            </li>
            <li><div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
              <div class="con"><p>medical image analysis; explainable AI</p></div>
            </div></li>
            <li><div class="post"><h3 class="tit"><span class="title">荣誉奖项</span></h3>
              <div class="con"><p>Best paper award of the 2023 workshop.</p></div>
            </div></li>
          </ul>
        </div>
      </div>
    </body></html>
    """

    extracted, error = extract_profile_record(
        roster_seed=seed,
        timeout=12.0,
        fetch_html=lambda _url, _timeout: html,
    )

    assert error is None
    assert extracted is not None
    assert extracted.education_structured[0].degree == "PhD"
    assert extracted.work_experience[0].organization == "Shenzhen University"
    assert extracted.work_experience[0].role == "Postdoctoral Fellow"
    assert extracted.awards == ("Best paper award of the 2023 workshop.",)
    assert extracted.academic_positions == ("PeerJ Computer Science, Academic Editor",)

    record = build_profile_record(
        roster_seed=seed,
        extracted=extracted,
        extraction_status="structured",
        skip_reason=None,
    )

    assert record.education_structured == extracted.education_structured
    assert record.work_experience == extracted.work_experience
    assert record.awards == extracted.awards
    assert record.academic_positions == extracted.academic_positions


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
        profile_raw_text="李志现任南方科技大学工学院教授。",
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
    assert record.profile_raw_text == "李志现任南方科技大学工学院教授。"


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
