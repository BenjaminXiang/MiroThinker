import requests
import sys
import threading
import types
import pytest
import json
from urllib.parse import quote

from src.data_agents.professor.discovery import (
    DiscoveryLimits,
    discover_professor_seeds,
    fetch_html_with_fallback,
)
from src.data_agents.professor.models import DiscoveredProfessorSeed, ProfessorRosterSeed
from src.data_agents.professor.parser import parse_roster_seed_markdown
from src.data_agents.professor.roster import extract_roster_entries, extract_roster_page_links
from src.data_agents.professor.validator import (
    SeedDocumentValidationError,
    validate_roster_discovery_document,
    validate_roster_seed_document,
)


@pytest.fixture(autouse=True)
def reset_discovery_runtime_state(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_learned_browser_first_hosts", set())
    monkeypatch.setattr(discovery_module, "_learned_reader_first_hosts", set())
    monkeypatch.setattr(discovery_module, "_THREAD_LOCAL_PLAYWRIGHT", threading.local())
    monkeypatch.setattr(discovery_module, "_PLAYWRIGHT_RUNTIME_REGISTRY", [])
    monkeypatch.setattr(discovery_module, "_SHARED_BROWSER_LOCK", threading.Lock())
    monkeypatch.setattr(discovery_module, "_last_direct_request_started_at_by_host", {})
    monkeypatch.setattr(discovery_module, "_last_reader_request_started_at", 0.0)


def test_parse_roster_seed_markdown_supports_links_and_plain_urls():
    markdown_text = """
## 深圳大学
### 计算机与软件学院
- [教师目录](https://cs.szu.edu.cn/szdw/jsml.htm)
- 备用地址: https://cs.szu.edu.cn/faculty/list.htm

## 南方科技大学
- [Faculty](https://cs.sustech.edu.cn/faculty/)
"""

    seeds = parse_roster_seed_markdown(markdown_text)

    assert [seed.roster_url for seed in seeds] == [
        "https://cs.szu.edu.cn/szdw/jsml.htm",
        "https://cs.szu.edu.cn/faculty/list.htm",
        "https://cs.sustech.edu.cn/faculty/",
    ]
    assert seeds[0].institution == "深圳大学"
    assert seeds[0].department == "计算机与软件学院"
    assert seeds[2].institution == "南方科技大学"
    assert seeds[2].department is None


def test_parse_roster_seed_markdown_supports_inline_seed_format_with_optional_department():
    markdown_text = """
清华大学深圳国际研究生院 https://www.sigs.tsinghua.edu.cn/7644/list.htm
深圳理工大学 计算机科学与人工智能学院 https://csce.suat-sz.edu.cn/szdw.htm
香港中文大学（深圳）人工智能学院 https://sai.cuhk.edu.cn/teacher-search
"""

    seeds = parse_roster_seed_markdown(markdown_text)

    assert [(seed.institution, seed.department, seed.roster_url) for seed in seeds] == [
        (
            "清华大学深圳国际研究生院",
            None,
            "https://www.sigs.tsinghua.edu.cn/7644/list.htm",
        ),
        (
            "深圳理工大学",
            "计算机科学与人工智能学院",
            "https://csce.suat-sz.edu.cn/szdw.htm",
        ),
        (
            "香港中文大学（深圳）",
            "人工智能学院",
            "https://sai.cuhk.edu.cn/teacher-search",
        ),
    ]


def test_parse_roster_seed_markdown_preserves_inline_person_label_for_direct_profile_urls():
    markdown_text = """
李立浧 https://www.sigs.tsinghua.edu.cn/llyys/main.htm
[王伟](https://www.sigs.tsinghua.edu.cn/wangwei/main.htm)
"""

    seeds = parse_roster_seed_markdown(markdown_text)

    assert [(seed.label, seed.roster_url) for seed in seeds] == [
        ("李立浧", "https://www.sigs.tsinghua.edu.cn/llyys/main.htm"),
        ("王伟", "https://www.sigs.tsinghua.edu.cn/wangwei/main.htm"),
    ]


def test_parse_roster_seed_markdown_splits_institution_and_person_label_for_direct_profile_urls():
    markdown_text = """
清华大学深圳国际研究生院 丁文伯 http://www.sigs.tsinghua.edu.cn/dwb/main.htm
"""

    seeds = parse_roster_seed_markdown(markdown_text)

    assert [(seed.institution, seed.department, seed.label, seed.roster_url) for seed in seeds] == [
        (
            "清华大学深圳国际研究生院",
            None,
            "丁文伯",
            "http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
        ),
    ]


def test_parse_roster_seed_markdown_infers_institution_from_direct_profile_url_without_context():
    markdown_text = """
李立浧 https://www.sigs.tsinghua.edu.cn/llyys/main.htm
崔曙光 https://sse.cuhk.edu.cn/teacher/42
"""

    seeds = parse_roster_seed_markdown(markdown_text)

    assert [(seed.label, seed.institution, seed.roster_url) for seed in seeds] == [
        (
            "李立浧",
            "清华大学深圳国际研究生院",
            "https://www.sigs.tsinghua.edu.cn/llyys/main.htm",
        ),
        (
            "崔曙光",
            "香港中文大学（深圳）",
            "https://sse.cuhk.edu.cn/teacher/42",
        ),
    ]


def test_extract_roster_entries_uses_school_adapter_dispatch_before_generic_paths(monkeypatch):
    from src.data_agents.professor import roster as roster_module
    from src.data_agents.professor.school_adapters import SchoolRosterAdapter

    adapter = SchoolRosterAdapter(
        name="cuhk-teacher-search",
        matcher=lambda url: "teacher-search" in url,
        extractor=lambda html, institution, department, source_url: [
            DiscoveredProfessorSeed(
                name="崔曙光",
                institution=institution,
                department=department,
                profile_url="https://sse.cuhk.edu.cn/teacher/1",
                source_url=source_url,
            )
        ],
    )

    monkeypatch.setattr(roster_module, "_SCHOOL_ROSTER_ADAPTERS", (adapter,))
    monkeypatch.setattr(
        roster_module,
        "_extract_inline_record_profile_links",
        lambda html: (_ for _ in ()).throw(AssertionError("generic path should be skipped")),
    )

    entries = roster_module.extract_roster_entries(
        html="<html></html>",
        institution="香港中文大学（深圳）",
        department="理工学院",
        source_url="https://sse.cuhk.edu.cn/teacher-search",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("崔曙光", "https://sse.cuhk.edu.cn/teacher/1")
    ]


def test_extract_roster_entries_uses_sustech_adapter_before_site_specific_path(monkeypatch):
    from src.data_agents.professor import roster as roster_module

    monkeypatch.setattr(
        roster_module,
        "_extract_site_specific_markdown_profile_links",
        lambda markdown, source_url: (_ for _ in ()).throw(
            AssertionError("site-specific fallback should be skipped")
        ),
    )

    entries = roster_module.extract_roster_entries(
        html="[唐博](https://www.sustech.edu.cn/zh/faculties/tangbo-2.html)",
        institution="南方科技大学",
        department=None,
        source_url="https://www.sustech.edu.cn/zh/letter/",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("唐博", "https://www.sustech.edu.cn/zh/faculties/tangbo-2.html")
    ]


def test_extract_roster_entries_uses_szu_adapter_before_site_specific_path(monkeypatch):
    from src.data_agents.professor import roster as roster_module

    monkeypatch.setattr(
        roster_module,
        "_extract_site_specific_html_profile_links",
        lambda soup, source_url: (_ for _ in ()).throw(
            AssertionError("site-specific fallback should be skipped")
        ),
    )

    entries = roster_module.extract_roster_entries(
        html='<html><body><a href="/info/1234/5678.htm">李华</a></body></html>',
        institution="深圳大学",
        department="计算机与软件学院",
        source_url="https://cs.szu.edu.cn/szdw/jsjj.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("李华", "https://cs.szu.edu.cn/info/1234/5678.htm")
    ]


def test_extract_roster_entries_uses_suat_adapter_before_site_specific_path(monkeypatch):
    from src.data_agents.professor import roster as roster_module

    monkeypatch.setattr(
        roster_module,
        "_extract_site_specific_markdown_profile_links",
        lambda markdown, source_url: (_ for _ in ()).throw(
            AssertionError("site-specific fallback should be skipped")
        ),
    )

    entries = roster_module.extract_roster_entries(
        html="[张三](https://csce.suat-sz.edu.cn/info/1001/2001.htm)",
        institution="深圳理工大学",
        department="计算机科学与人工智能学院",
        source_url="https://csce.suat-sz.edu.cn/szdw.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("张三", "https://csce.suat-sz.edu.cn/info/1001/2001.htm")
    ]


def test_extract_roster_entries_deduplicates_by_professor_identity():
    html = """
<html><body>
  <ul>
    <li><a href="/faculty/lihua">李华</a></li>
    <li><a href="/teacher/lihua_profile">李华</a></li>
    <li><a href="/faculty/wangwu">王五</a></li>
    <li><a href="/faculty/index">教师列表</a></li>
  </ul>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="计算机与软件学院",
        source_url="https://cs.szu.edu.cn/faculty/index.htm",
    )

    assert [entry.name for entry in entries] == ["李华", "王五"]
    assert entries[0].profile_url == "https://cs.szu.edu.cn/faculty/lihua"
    assert entries[1].profile_url == "https://cs.szu.edu.cn/faculty/wangwu"


def test_extract_roster_entries_prefers_teacherlist_faculty_cards_over_generic_anchors():
    html = """
<html><body>
  <nav>
    <a href="/faculty/history">发展历程</a>
    <a href="/faculty/staff">教辅人员</a>
    <a href="/faculty/news">新闻动态</a>
  </nav>
  <div class="teacherlist">
    <a href="/faculty/liyi">
      <dl class="faculty_item">
        <dt><img src="/images/liyi.jpg" /></dt>
        <dd>
          <h3 class="t-name">李一</h3>
        </dd>
      </dl>
    </a>
    <a href="/faculty/erwang">
      <dl class="faculty_item">
        <dd>
          <h3 class="t-name">王二</h3>
        </dd>
      </dl>
    </a>
    <a href="/faculty/liyi-v2">
      <dl class="faculty_item">
        <dd>
          <h3 class="t-name">李一</h3>
        </dd>
      </dl>
    </a>
  </div>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="南方科技大学",
        department="计算机科学与工程系",
        source_url="https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    )

    assert [entry.name for entry in entries] == ["李一", "王二"]
    assert [entry.profile_url for entry in entries] == [
        "https://cse.sustech.edu.cn/faculty/liyi",
        "https://cse.sustech.edu.cn/faculty/erwang",
    ]


def test_extract_roster_entries_fallback_generic_anchor_filters_nav_keywords():
    html = """
<html><body>
  <ul>
    <li><a href="/faculty/history">发展历程</a></li>
    <li><a href="/faculty/staff">教辅人员</a></li>
    <li><a href="/faculty/news">新闻动态</a></li>
    <li><a href="/faculty/lihua">李华</a></li>
    <li><a href="/faculty/wangwu">王五</a></li>
  </ul>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="南方科技大学",
        department="计算机科学与工程系",
        source_url="https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    )

    assert [entry.name for entry in entries] == ["李华", "王五"]
    assert [entry.profile_url for entry in entries] == [
        "https://cse.sustech.edu.cn/faculty/lihua",
        "https://cse.sustech.edu.cn/faculty/wangwu",
    ]


def test_extract_roster_entries_supports_markdown_reader_links():
    markdown = """
* [吴亚北 研究助理教授（副研究员） 材料科学与工程系](https://www.sustech.edu.cn/zh/faculties/wuyabei.html)
* [Alejandro Palomo Gonzalez 环境科学与工程学院](https://www.sustech.edu.cn/zh/faculties/alejandropalomogonzalez.html)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="南方科技大学",
        department=None,
        source_url="https://www.sustech.edu.cn/zh/letter/",
    )

    assert [entry.name for entry in entries] == ["吴亚北", "Alejandro Palomo Gonzalez"]
    assert [entry.profile_url for entry in entries] == [
        "https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        "https://www.sustech.edu.cn/zh/faculties/alejandropalomogonzalez.html",
    ]


def test_extract_roster_entries_supports_markdown_reader_links_with_image_prefix():
    markdown = """
* [![Image 1](https://www.sigs.tsinghua.edu.cn/example.jpg) 陈道毅 0755-26036290 教授，博士生导师](http://www.sigs.tsinghua.edu.cn/cdy/main.htm)
* [![Image 2](https://www.sigs.tsinghua.edu.cn/example2.jpg) Avik Kumar DAS (Structures and Materials) Civil Engineering 助理教授](http://www.sigs.tsinghua.edu.cn/Avik%20Kumar/main.htm)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="清华大学深圳国际研究生院",
        department=None,
        source_url="https://www.sigs.tsinghua.edu.cn/7644/list.htm",
    )

    assert [entry.name for entry in entries] == ["陈道毅", "Avik Kumar DAS"]
    assert [entry.profile_url for entry in entries] == [
        "http://www.sigs.tsinghua.edu.cn/cdy/main.htm",
        "http://www.sigs.tsinghua.edu.cn/Avik%20Kumar/main.htm",
    ]


def test_extract_roster_entries_supports_markdown_links_with_optional_titles():
    markdown = """
* [![Image 4](https://csce.suat-sz.edu.cn/example.jpg) 潘毅 讲席教授、院长](https://csce.suat-sz.edu.cn/info/1008/1029.htm "潘毅")
* [![Image 19](https://csce.suat-sz.edu.cn/example2.jpg) 唐继军 教授、副院长](https://csce.suat-sz.edu.cn/info/1010/1021.htm "唐继军")
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="深圳理工大学",
        department="计算机科学与人工智能学院",
        source_url="https://csce.suat-sz.edu.cn/szdw.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("潘毅", "https://csce.suat-sz.edu.cn/info/1008/1029.htm"),
        ("唐继军", "https://csce.suat-sz.edu.cn/info/1010/1021.htm"),
    ]


def test_extract_roster_entries_rejects_generic_markdown_navigation_pages():
    markdown = """
* [学校简介](https://www.szu.edu.cn/xxgk/xxjj.htm)
* [深大标识](https://www.szu.edu.cn/xxgk/sdbs.htm)
* [人才招聘](https://www.pkusz.edu.cn/zp/js.htm)
* [帮助中心](https://homepage.hit.edu.cn/help_center.html)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="深圳大学",
        department=None,
        source_url="https://www.szu.edu.cn/szdw/jsjj.htm",
    )

    assert entries == []


def test_extract_roster_entries_teacherlist_with_nested_divs_still_uses_card_names():
    html = """
<html><body>
  <div class="teacherlist">
    <a href="/faculty/lihua">
      <dl class="faculty_item">
        <dt>
          <div class="imgsize img4_3">
            <img src="/images/lihua.jpg" />
          </div>
        </dt>
        <dd>
          <h3 class="t-name">李华</h3>
          <span>查看详情</span>
        </dd>
      </dl>
    </a>
    <a href="/faculty/wangwu">
      <dl class="faculty_item">
        <dt>
          <div class="imgsize img4_3">
            <img src="/images/wangwu.jpg" />
          </div>
        </dt>
        <dd>
          <h3 class="t-name">王五</h3>
          <span>查看详情</span>
        </dd>
      </dl>
    </a>
  </div>
  <nav>
    <a href="/faculty/history">发展历程</a>
    <a href="/faculty/staff">教辅人员</a>
    <a href="/faculty/news">新闻动态</a>
  </nav>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="南方科技大学",
        department="计算机科学与工程系",
        source_url="https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    )

    assert [entry.name for entry in entries] == ["李华", "王五"]
    assert [entry.profile_url for entry in entries] == [
        "https://cse.sustech.edu.cn/faculty/lihua",
        "https://cse.sustech.edu.cn/faculty/wangwu",
    ]


@pytest.mark.parametrize(
    ("html", "source_url", "expected"),
    [
        (
            """
            <html><body>
              <div class="list2">
                <a href="/zh/faculties/wuyabei.html">
                  <div class="name">吴亚北</div>
                  <div class="dep">材料科学与工程系</div>
                </a>
                <a href="/zh/faculties/riwu.html">
                  <div class="name">吴日</div>
                  <div class="dep">先进光源科学中心</div>
                </a>
              </div>
            </body></html>
            """,
            "https://www.sustech.edu.cn/zh/letter/",
            [
                ("吴亚北", "https://www.sustech.edu.cn/zh/faculties/wuyabei.html"),
                ("吴日", "https://www.sustech.edu.cn/zh/faculties/riwu.html"),
            ],
        ),
        (
            """
            <html><body>
              <div class="item">
                <a href="info/1008/1029.htm" class="con" title="潘毅">
                  <span class="name">潘毅</span>
                  <span class="lab">讲席教授、院长</span>
                </a>
              </div>
              <div class="item">
                <a href="info/1008/1028.htm" class="con" title="唐金陵">
                  <span class="name">唐金陵</span>
                  <span class="lab">讲席教授、系主任</span>
                </a>
              </div>
            </body></html>
            """,
            "https://csce.suat-sz.edu.cn/szdw.htm",
            [
                ("潘毅", "https://csce.suat-sz.edu.cn/info/1008/1029.htm"),
                ("唐金陵", "https://csce.suat-sz.edu.cn/info/1008/1028.htm"),
            ],
        ),
    ],
)
def test_extract_roster_entries_supports_modern_name_card_layouts(
    html: str,
    source_url: str,
    expected: list[tuple[str, str]],
):
    entries = extract_roster_entries(
        html=html,
        institution="测试大学",
        department=None,
        source_url=source_url,
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == expected


def test_extract_roster_entries_name_normalization_keeps_spaces_for_latin_names():
    html = """
<html><body>
  <ul>
    <li><a href="/faculty/georgios">  Georgios   Theodoropoulos  </a></li>
    <li><a href="/faculty/hisao">Hisao    Ishibuchi</a></li>
    <li><a href="/faculty/pietro">Pietro  Simone   Oliveto</a></li>
    <li><a href="/faculty/lihua">  李  华  </a></li>
  </ul>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="南方科技大学",
        department="计算机科学与工程系",
        source_url="https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    )

    assert [entry.name for entry in entries] == [
        "Georgios Theodoropoulos",
        "Hisao Ishibuchi",
        "Pietro Simone Oliveto",
        "李华",
    ]


def test_validate_roster_seed_document_fails_on_empty_document():
    with pytest.raises(SeedDocumentValidationError, match="contains no roster URLs"):
        validate_roster_seed_document("", document_name="docs/教授 URL.md")


def test_validate_roster_seed_document_reports_duplicate_urls():
    markdown_text = """
## 深圳大学
- https://cs.szu.edu.cn/szdw/jsml.htm
- [教师目录](https://cs.szu.edu.cn/szdw/jsml.htm)
"""

    report = validate_roster_seed_document(markdown_text, document_name="docs/教授 URL.md")

    assert report.seed_source_count == 2
    assert report.unique_seed_source_count == 1
    assert report.duplicate_seed_urls == ["https://cs.szu.edu.cn/szdw/jsml.htm"]


def test_extract_roster_page_links_ignores_fragment_only_markdown_links():
    markdown = """
* [专任教师](#row-z1)
* [讲席教授](#row-z2)
* [教师目录](https://example.edu/faculty/list.htm)
"""

    links = extract_roster_page_links(markdown, "https://example.edu/szdw.htm")

    assert links == [("https://example.edu/faculty/list.htm", "教师目录")]


def test_extract_roster_entries_skips_sustech_hub_pages_and_keeps_department_links():
    markdown = """
* [学校概况](https://www.sustech.edu.cn/zh/about.html)
* [理学院](https://science.sustech.edu.cn/)
* [数学系](https://math.sustech.edu.cn/?lang=zh)
* [院系师资](https://www.sustech.edu.cn/zh/faculty_members.html)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="南方科技大学",
        department=None,
        source_url="https://www.sustech.edu.cn/zh/letter/",
    )
    links = extract_roster_page_links(markdown, "https://www.sustech.edu.cn/zh/letter/")

    assert entries == []
    assert links == [
        ("https://science.sustech.edu.cn/", "理学院"),
        ("https://math.sustech.edu.cn/?lang=zh", "数学系"),
    ]


def test_extract_roster_entries_keeps_sustech_faculty_links_without_nav_false_positives():
    markdown = """
* [学生](https://www.sustech.edu.cn/zh/students.html)
* [教职工](https://www.sustech.edu.cn/zh/faculty-staff.html)
* [吴亚北 研究助理教授（副研究员） 材料科学与工程系](https://www.sustech.edu.cn/zh/faculties/wuyabei.html)
* [Alejandro Palomo Gonzalez 环境科学与工程学院](https://www.sustech.edu.cn/zh/faculties/alejandropalomogonzalez.html)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="南方科技大学",
        department=None,
        source_url="https://www.sustech.edu.cn/zh/letter/",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("吴亚北", "https://www.sustech.edu.cn/zh/faculties/wuyabei.html"),
        (
            "Alejandro Palomo Gonzalez",
            "https://www.sustech.edu.cn/zh/faculties/alejandropalomogonzalez.html",
        ),
    ]


def test_extract_roster_entries_prefers_szu_info_detail_cards_over_navigation_links():
    html = """
<html><body>
  <nav>
    <a class="sub-link" href="../xbgk/xrld.htm">现任领导</a>
    <a class="sub-link" href="../dqgz/zzsz.htm">组织设置</a>
    <a class="sub-link" href="js1.htm">教授</a>
  </nav>
  <div class="news_box clearfix">
    <div class="news_imgs"><a href="../info/1022/1124.htm"><img src="p1.jpg" /></a></div>
    <div class="news_con">
      <div class="news_title"><a href="../info/1022/1124.htm">:孔祥渊</a></div>
    </div>
  </div>
  <div class="news_box clearfix">
    <div class="news_imgs"><a href="../info/1022/1122.htm"><img src="p2.jpg" /></a></div>
    <div class="news_con">
      <div class="news_title"><a href="../info/1022/1122.htm">:王晓芳</a></div>
    </div>
  </div>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="教育学部",
        source_url="http://fe.szu.edu.cn/szdw/fjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("孔祥渊", "http://fe.szu.edu.cn/info/1022/1124.htm"),
        ("王晓芳", "http://fe.szu.edu.cn/info/1022/1122.htm"),
    ]


def test_extract_roster_entries_prefers_szu_art_info_cards_over_navigation_links():
    html = """
<html><body>
  <nav>
    <a href="../xbgk/xbbz.htm">学部班子</a>
    <a href="../xkjs_zs/bkjy.htm">本科教育</a>
  </nav>
  <ul class="list11 flex">
    <li><a class="a" href="../info/1009/3471.htm">陈向兵 教授、硕导</a></li>
    <li><a class="a" href="../info/1009/2149.htm">陈振旺 教授、博导</a></li>
  </ul>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="艺术学部",
        source_url="https://art.szu.edu.cn/sztd/zgjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("陈向兵", "https://art.szu.edu.cn/info/1009/3471.htm"),
        ("陈振旺", "https://art.szu.edu.cn/info/1009/2149.htm"),
    ]


def test_extract_roster_page_links_prefers_szu_subcollege_teacher_pages():
    markdown = """
* [学部学院](https://www.szu.edu.cn/yxjg/xbxy.htm)
* [教授委员会](https://www.szu.edu.cn/yxjg/jswyh.htm)
* [教育学部](http://fe.szu.edu.cn/szdw/js1.htm)
* [医学部](https://med.szu.edu.cn/szdw)
* [马克思主义学院](https://my.szu.edu.cn/jsfc/js.htm)
"""

    links = extract_roster_page_links(markdown, "https://www.szu.edu.cn/szdw/jsjj.htm")

    assert links == [
        ("http://fe.szu.edu.cn/szdw/js1.htm", "教育学部"),
        ("https://med.szu.edu.cn/szdw", "医学部"),
        ("https://my.szu.edu.cn/jsfc/js.htm", "马克思主义学院"),
    ]


def test_extract_roster_entries_prefers_pkusz_ece_teacher_cards_over_navigation_links():
    html = """
<html><body>
  <nav>
    <a href="../xygk/xrld.htm">现任领导</a>
    <a href="../xwzx.htm">新闻中心</a>
    <a href="../kxyj/fmzl.htm">发明专利</a>
  </nav>
  <ul class="list_box_shizi">
    <li><a href="../info/1046/2141.htm">白志强 职 称： 教授 电 话： 0755-26035598 办公室： Email： baizq@pkusz.edu.cn</a></li>
    <li><a href="../info/1045/2137.htm">蔡泽宇 职 称： 特聘研究员 电 话： 0755-26032014 办公室： A302 Email： zcai@pku.edu.cn</a></li>
  </ul>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="北京大学深圳研究生院",
        department="信息工程学院",
        source_url="https://www.ece.pku.edu.cn/szdw/js1.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("白志强", "https://www.ece.pku.edu.cn/info/1046/2141.htm"),
        ("蔡泽宇", "https://www.ece.pku.edu.cn/info/1045/2137.htm"),
    ]


def test_extract_roster_entries_supports_szu_nested_jsml_profile_links():
    html = """
<html><head><title>教师名录-深圳大学材料学院欢迎您</title></head><body>
  <nav>
    <a href="../xygk/lsyg.htm">历史沿革</a>
    <a href="jcrc.htm">杰出人才</a>
  </nav>
  <div class="faculty-list">
    <a href="jsml/clkxygcx/fzr/lyy.htm">李亚运</a>
    <a href="jsml/clkxygcx/j_s/zdl.htm">朱德亮</a>
  </div>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="材料学院",
        source_url="https://cmse.szu.edu.cn/szdw1/jsml.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("李亚运", "https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/fzr/lyy.htm"),
        ("朱德亮", "https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/j_s/zdl.htm"),
    ]


def test_extract_roster_entries_skips_szu_template_teacher_pages_without_real_profiles():
    html = """
<html><head><title>师资队伍-深圳大学物理与光电工程学院</title></head><body>
  <a href="xygk/xrld.htm">现任领导</a>
  <a href="szdw.jsp?urltype=tree.TreeTempUrl&wbtreeid=1111&rankid=1779727392649842690">教授</a>
  <a href="{{:url}}">{{:showName}} {{:rank}}</a>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="物理与光电工程学院",
        source_url="https://cpoe.szu.edu.cn/szdw.jsp?urltype=tree.TreeTempUrl&wbtreeid=1111",
    )

    assert entries == []


def test_extract_roster_entries_supports_szu_relative_info_profile_links():
    html = """
<html><head><title>师资队伍-深圳大学微众银行金融科技学院</title></head><body>
  <a href="szdw/jsfc.htm">查看更多</a>
  <a href="info/1026/1562.htm">陈海强</a>
  <a href="info/1026/1563.htm">葛锐</a>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="微众金融科技学院",
        source_url="https://swift.szu.edu.cn/szdw.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("陈海强", "https://swift.szu.edu.cn/info/1026/1562.htm"),
        ("葛锐", "https://swift.szu.edu.cn/info/1026/1563.htm"),
    ]


def test_extract_roster_entries_supports_szu_content_profile_links():
    html = """
<html><head><title>师资队伍-深圳大学医学部</title></head><body>
  <a href="http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_8681">陈玮琳</a>
  <a href="http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_4551">姜保国</a>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="医学部",
        source_url="https://med.szu.edu.cn/szdw",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("陈玮琳", "http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_8681"),
        ("姜保国", "http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_4551"),
    ]


def test_extract_roster_entries_supports_szu_markdown_content_profile_links():
    markdown = """
* [陈玮琳](http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_8681)
* [姜保国](http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_4551)
* [教授](https://med.szu.edu.cn/szdw/jss)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="深圳大学",
        department="医学部",
        source_url="https://med.szu.edu.cn/szdw",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("陈玮琳", "http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_8681"),
        ("姜保国", "http://med.szu.edu.cn/szdw/jszgml/jcyxy2/content_4551"),
    ]


def test_extract_roster_page_links_prefers_pkusz_teacher_queue_links():
    markdown = """
* [### 学院导航](https://www.pkusz.edu.cn/xydh.htm "学院导航")[信息工程学院](https://www.ece.pku.edu.cn/ "信息工程学院")[汇丰商学院](https://www.phbs.pku.edu.cn/ "汇丰商学院")

教师队伍

*   [信息工程学院](https://www.ece.pku.edu.cn/szdw.htm)
*   [化学生物学与生物技术学院](https://scbb.pkusz.edu.cn/szdw.htm)
*   [汇丰商学院](https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/)
*   [国际法学院](https://stl.pku.edu.cn/Faculty_Research/Resident_Faculty.htm)
"""

    links = extract_roster_page_links(markdown, "https://www.pkusz.edu.cn/szdw.htm")

    assert links == [
        ("https://www.ece.pku.edu.cn/szdw.htm", "信息工程学院"),
        ("https://scbb.pkusz.edu.cn/szdw.htm", "化学生物学与生物技术学院"),
        ("https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/", "汇丰商学院"),
        ("https://stl.pku.edu.cn/Faculty_Research/Resident_Faculty.htm", "国际法学院"),
    ]


def test_extract_roster_entries_skips_pkusz_hub_navigation_page():
    markdown = """
*   [### 本院概况](https://www.pkusz.edu.cn/bygk/byjs.htm "本院概况")[本院介绍](https://www.pkusz.edu.cn/bygk/byjs.htm "本院介绍")[北大传承](https://www.pkusz.edu.cn/bygk/bdcc.htm "北大传承")

教师队伍

*   [信息工程学院](https://www.ece.pku.edu.cn/szdw.htm)
*   [汇丰商学院](https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="北京大学深圳研究生院",
        department=None,
        source_url="https://www.pkusz.edu.cn/szdw.htm",
    )
    links = extract_roster_page_links(markdown, "https://www.pkusz.edu.cn/szdw.htm")

    assert entries == []
    assert links == [
        ("https://www.ece.pku.edu.cn/szdw.htm", "信息工程学院"),
        ("https://www.phbs.pku.edu.cn/teacher/teachers/fulltime/", "汇丰商学院"),
    ]


def test_extract_roster_entries_skips_pkusz_root_info_links_before_recursive_discovery():
    html = """
    <html><body>
      <a href="/info/1012/2741.htm">学术交流</a>
      <a href="https://www.ece.pku.edu.cn/szdw.htm">信息工程学院</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="北京大学深圳研究生院",
        department=None,
        source_url="https://www.pkusz.edu.cn/szdw.htm",
    )

    assert entries == []


def test_extract_roster_entries_skips_pkusz_ece_hub_page_without_direct_profile_cards():
    html = """
    <html><body>
      <a href="/xwzx.htm">新闻中心</a>
      <a href="/kxyj.htm">科学研究</a>
      <a href="/szdw/js1.htm">教师</a>
      <a href="/szdw/jzjs.htm">兼职教师</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="北京大学深圳研究生院",
        department="信息工程学院",
        source_url="https://www.ece.pku.edu.cn/szdw.htm",
    )

    assert entries == []


def test_extract_roster_entries_skips_sztu_teacher_hub_without_direct_people():
    html = """
    <html><body>
      <a href="/szdw/szgk.htm">师资概况</a>
      <a href="/szdw/jyxl.htm">教研序列</a>
      <a href="/szdw/yjxl.htm">研究序列</a>
      <a href="/szdw/jfxl.htm">教辅序列</a>
      <a href="/szdw/xzxl.htm">行政序列</a>
      <a href="/rcpy.htm">人才培养</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="健康与环境工程学院",
        source_url="https://hsee.sztu.edu.cn/szdw.htm",
    )

    assert entries == []


def test_extract_roster_entries_supports_sztu_heading_profiles_without_detail_links():
    html = """
    <html><body>
      <section class="faculty">
        <h3>杜鹤民</h3>
        <p>副院长、教授、博士研究生导师</p>
        <p>duhemin@sztu.edu.cn</p>
        <h3>荣誉教授</h3>
        <p>Honorary Professor</p>
        <h3>李立全</h3>
        <p>副院长、正高级工程师、副教授</p>
      </section>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="创意设计学院",
        source_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "杜鹤民",
            f"https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-{quote('杜鹤民')}",
        ),
        (
            "李立全",
            f"https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-{quote('李立全')}",
        ),
    ]


def test_extract_roster_entries_supports_sztu_heading_profiles_with_latin_names():
    html = """
    <html><body>
      <article>
        <h4>Franz Raps</h4>
        <p>院长、讲席教授</p>
        <p>德国国家工程院院士</p>
        <h4>International Exchange Cooperation</h4>
        <p>合作交流</p>
      </article>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="城市交通与物流学院",
        source_url="https://utl.sztu.edu.cn/szdw1/qbjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "Franz Raps",
            "https://utl.sztu.edu.cn/szdw1/qbjs.htm#prof-Franz%20Raps",
        )
    ]


def test_extract_roster_entries_prefers_sztu_inline_js_detail_pages_over_heading_fragments():
    html = """
    <html><body>
      <article>
        <h4>Franz Raps</h4>
        <p>院长、讲席教授</p>
      </article>
      <script>
        let teacherData = [
          {
            showTitle: 'Franz Raps',
            bq: '车辆工程#教授#教授序列',
            zc: '院长顾问、兼职教授',
            picUrl: '/__local/example.jpg',
            aHref:"../info/1286/1968.htm"
          }
        ];
      </script>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="城市交通与物流学院",
        source_url="https://utl.sztu.edu.cn/szdw1/qbjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "Franz Raps",
            "https://utl.sztu.edu.cn/info/1286/1968.htm",
        )
    ]


def test_extract_roster_entries_prefers_sztu_ahref_over_main_url_fields():
    html = """
    <html><body>
      <article>
        <h4>Franz Raps</h4>
        <p>院长、讲席教授</p>
      </article>
      <script>
        let teacherData = [
          {
            showTitle: 'Franz Raps',
            mainUrl: '/banner.jpg',
            aHref:"../info/1286/1968.htm"
          }
        ];
      </script>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="城市交通与物流学院",
        source_url="https://utl.sztu.edu.cn/szdw1/qbjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "Franz Raps",
            "https://utl.sztu.edu.cn/info/1286/1968.htm",
        )
    ]



def test_extract_roster_entries_does_not_block_topology_context_for_heading_profiles():
    html = """
    <html><body>
      <article>
        <h4>Alice Zhang</h4>
        <p>副教授</p>
        <p>Research topics: algebraic topology and transport networks</p>
      </article>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="城市交通与物流学院",
        source_url="https://utl.sztu.edu.cn/szdw1/qbjs.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "Alice Zhang",
            "https://utl.sztu.edu.cn/szdw1/qbjs.htm#prof-Alice%20Zhang",
        )
    ]


def test_extract_roster_entries_prefers_sztu_heading_profiles_over_navigation_links():
    html = """
    <html><body>
      <nav>
        <a href="../xygk/jgsz.htm">机构设置</a>
        <a href="../../jyjx/xkjs/bks.htm">本科生</a>
        <a href="kzjs.htm">客座教授</a>
      </nav>
      <section>
        <h3>杜鹤民</h3>
        <div>副院长、教授、博士研究生导师</div>
      </section>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="创意设计学院",
        source_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        (
            "杜鹤民",
            f"https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-{quote('杜鹤民')}",
        )
    ]


def test_extract_roster_entries_uses_sztu_detail_pages_wrapping_profile_cards():
    html = """
    <html><body>
      <div class="right n_shizi">
        <ul>
          <li><a href="../info/1025/1331.htm">
            <div class="box">
              <div class="con">
                <h4>傅强</h4>
                <h6>特聘教授，执业药师</h6>
                <p>药物分析学教授（二级），博士生导师。</p>
                <p>查看更多</p>
              </div>
            </div>
          </a></li>
          <li><a href="../info/1025/2713.htm">
            <div class="box">
              <div class="con">
                <h4>\u200b隋文</h4>
                <h6>助理教授</h6>
                <p>药物递送与制剂工程。</p>
                <p>查看更多</p>
              </div>
            </div>
          </a></li>
        </ul>
      </div>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳技术大学",
        department="药学院",
        source_url="https://cop.sztu.edu.cn/szdw/jxky.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("傅强", "https://cop.sztu.edu.cn/info/1025/1331.htm"),
        ("隋文", "https://cop.sztu.edu.cn/info/1025/2713.htm"),
    ]


def test_extract_roster_entries_filters_institution_and_role_titles_as_names():
    html = """
    <html><body>
      <a href="/teacher/sysu.htm">中山大学</a>
      <a href="/teacher/postdoc.htm">博士后</a>
      <a href="/teacher/hutianjiang.htm">胡天江</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="示例大学",
        department="示例学院",
        source_url="https://example.edu/faculty",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("胡天江", "https://example.edu/teacher/hutianjiang.htm")
    ]


def test_extract_roster_entries_skips_ise_overview_page_without_direct_teacher_cards():
    html = """
    <html><body>
      <a href="/teacher">教师名录</a>
      <a href="/Faculty/Post-doctor">博士后</a>
      <a href="/faculty/Retired-Teacher">荣休人员</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="智能工程学院",
        source_url="http://ise.sysu.edu.cn/teachers",
    )
    links = extract_roster_page_links(html, "http://ise.sysu.edu.cn/teachers")

    assert entries == []
    assert links == [
        ("http://ise.sysu.edu.cn/teacher", "教师名录"),
        ("http://ise.sysu.edu.cn/Faculty/Post-doctor", "博士后"),
    ]


def test_extract_roster_entries_skips_pkusz_ece_alpha_directory_pages_without_teacher_cards():
    html = """
    <html><body>
      <a href="../../xwzx.htm">新闻中心</a>
      <a href="../../kxyj/fmzl.htm">发明专利</a>
      <a href="../../xsgz1/xsfw.htm">学生服务</a>
      <a href="../js1.htm">教师</a>
      <a href="ALL.htm">ALL</a>
      <a href="A.htm">A</a>
      <a href="B.htm">B</a>
      <ul class="list_box_shizi"></ul>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="北京大学深圳研究生院",
        department="信息工程学院",
        source_url="https://www.ece.pku.edu.cn/szdw/ALL/A.htm",
    )

    assert entries == []


def test_extract_roster_entries_supports_hit_directory_markdown_summaries():
    markdown = """
*   访问量：506770[![Image 7](https://homepage.hit.edu.cn/file/showHP.do?d=232&&w=84&&h=84) ### 高会军 航天学院 国家级高层次人才](https://homepage.hit.edu.cn/school-dept?id=1&browseName=%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT)
*   访问量：223827[![Image 8](https://homepage.hit.edu.cn/file/showHP.do?d=264&&w=84&&h=84) ### 吴立刚 航天学院 国家杰青](https://homepage.hit.edu.cn/school-dept?id=1&browseName=%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="哈尔滨工业大学（深圳）",
        department=None,
        source_url=(
            "https://homepage.hit.edu.cn/school-dept?id=1&browseName="
            "%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT"
        ),
    )

    assert [(entry.name, entry.department, entry.profile_url) for entry in entries] == [
        (
            "高会军",
            "航天学院",
            "https://homepage.hit.edu.cn/school-dept?id=1&browseName=%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT#prof-%E9%AB%98%E4%BC%9A%E5%86%9B",
        ),
        (
            "吴立刚",
            "航天学院",
            "https://homepage.hit.edu.cn/school-dept?id=1&browseName=%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT#prof-%E5%90%B4%E7%AB%8B%E5%88%9A",
        ),
    ]


def test_get_shared_playwright_state_stops_runtime_when_browser_launch_fails(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    discovery_module._shutdown_shared_playwright_browser()

    stopped = []

    class FakeChromium:
        def launch(self, *, headless: bool = True):
            del headless
            raise RuntimeError("launch failed")

    class FakePlaywrightRuntime:
        def __init__(self):
            self.chromium = FakeChromium()

        def stop(self) -> None:
            stopped.append("stopped")

    fake_sync_api = types.SimpleNamespace(
        sync_playwright=lambda: types.SimpleNamespace(start=lambda: FakePlaywrightRuntime())
    )
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', fake_sync_api)
    monkeypatch.setitem(sys.modules, 'playwright', types.SimpleNamespace(sync_api=fake_sync_api))

    with pytest.raises(RuntimeError, match="launch failed"):
        discovery_module._get_shared_playwright_state()

    assert stopped == ["stopped"]


def test_shared_playwright_browser_is_thread_scoped(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    discovery_module._shutdown_shared_playwright_browser()

    browser_owner_threads: list[int] = []
    stopped_threads: list[int] = []

    class FakeBrowser:
        def __init__(self, owner_thread: int):
            self.owner_thread = owner_thread

        def close(self) -> None:
            stopped_threads.append(self.owner_thread)

    class FakeChromium:
        def launch(self, *, headless: bool = True):
            del headless
            owner_thread = threading.get_ident()
            browser_owner_threads.append(owner_thread)
            return FakeBrowser(owner_thread)

    class FakePlaywrightRuntime:
        def __init__(self):
            self.chromium = FakeChromium()

        def stop(self) -> None:
            stopped_threads.append(threading.get_ident())

    fake_sync_api = types.SimpleNamespace(
        sync_playwright=lambda: types.SimpleNamespace(start=lambda: FakePlaywrightRuntime())
    )
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', fake_sync_api)
    monkeypatch.setitem(sys.modules, 'playwright', types.SimpleNamespace(sync_api=fake_sync_api))

    results: list[object] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            results.append(discovery_module._get_shared_playwright_browser())
            barrier.wait(timeout=2)
        except Exception as exc:  # pragma: no cover - defensive collection for assertion below
            errors.append(exc)

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    second.start()
    first.join()
    second.join()

    assert not errors
    assert len(results) == 2
    assert results[0] is not results[1]
    assert len(set(browser_owner_threads)) == 2

    discovery_module._shutdown_shared_playwright_browser()
    assert len(stopped_threads) >= 2


def test_render_html_with_playwright_retries_after_stale_browser_state(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    class FakePlaywrightError(Exception):
        pass

    class FakePage:
        def __init__(self):
            self.mouse = types.SimpleNamespace(wheel=lambda _x, _y: None)

        def goto(self, _url: str, *, wait_until: str, timeout: int) -> None:
            assert wait_until == "domcontentloaded"
            assert timeout > 0

        def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
            assert timeout > 0

        def wait_for_timeout(self, _timeout: int) -> None:
            return None

        def content(self) -> str:
            return "<html><body>browser response</body></html>"

    class FakeContext:
        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            return None

    class StaleBrowser:
        def new_context(self, **_kwargs):
            raise FakePlaywrightError("Target page, context or browser has been closed")

    class HealthyBrowser:
        def new_context(self, **_kwargs):
            return FakeContext()

    browsers = [StaleBrowser(), HealthyBrowser()]
    shutdown_calls: list[int | None] = []

    monkeypatch.setattr(
        discovery_module,
        "_get_shared_playwright_state",
        lambda: types.SimpleNamespace(browser=browsers.pop(0), render_lock=threading.Lock()),
    )
    monkeypatch.setattr(
        discovery_module,
        "_shutdown_shared_playwright_browser",
        lambda thread_id=None: shutdown_calls.append(thread_id),
    )

    fake_sync_api = types.SimpleNamespace(Error=FakePlaywrightError)
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', fake_sync_api)
    monkeypatch.setitem(sys.modules, 'playwright', types.SimpleNamespace(sync_api=fake_sync_api))

    html = discovery_module._render_html_with_playwright(
        "https://example.edu/teacher/1",
        timeout=5.0,
    )

    assert html == "<html><body>browser response</body></html>"
    assert shutdown_calls == [threading.get_ident()]
    assert not browsers



def test_fetch_html_with_fallback_reports_browser_runtime_failures_explicitly():
    class FakeResponse:
        status_code = 403
        encoding = "ISO-8859-1"
        apparent_encoding = "utf-8"
        text = "access denied"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("403 Client Error")

    result = fetch_html_with_fallback(
        "https://blocked.example.edu/roster",
        request_get=lambda url, timeout: FakeResponse(),
        browser_fetch=lambda url, timeout: (_ for _ in ()).throw(
            RuntimeError("playwright browser runtime unavailable")
        ),
        reader_fetch=lambda url, timeout: (_ for _ in ()).throw(
            RuntimeError("reader transport unavailable")
        ),
    )

    assert result.html is None
    assert result.used_browser is False
    assert result.blocked_by_anti_scraping is True
    assert result.request_error == "403 Client Error"
    assert result.browser_error == (
        "playwright browser runtime unavailable | reader transport unavailable"
    )


def test_fetch_html_with_fallback_uses_browser_when_request_get_raises_tls_error():
    result = fetch_html_with_fallback(
        "https://sai.cuhk.edu.cn/teacher-search",
        request_get=lambda url, timeout: (_ for _ in ()).throw(
            requests.exceptions.SSLError("tls handshake failure")
        ),
        browser_fetch=lambda url, timeout: (
            '<html><body><a href="/teacher/102">李海洲</a></body></html>'
        ),
    )

    assert "李海洲" in (result.html or "")
    assert result.used_browser is True
    assert result.blocked_by_anti_scraping is True
    assert result.request_error is None
    assert result.browser_error is None
    assert result.fetch_policy == "browser_first"
    assert result.fetch_method == "browser"


def test_fetch_html_with_fallback_falls_back_on_non_blocked_http_error():
    calls: list[str] = []

    class FakeResponse:
        status_code = 500
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "<html><body>internal server error</body></html>"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("500 Server Error")

    result = fetch_html_with_fallback(
        "https://www.sustech.edu.cn/zh/letter/",
        request_get=lambda _url, _timeout: (calls.append("request"), FakeResponse())[1],
        browser_fetch=lambda _url, _timeout: (
            calls.append("browser"),
            "<html><body>browser response</body></html>",
        )[1],
    )

    assert calls == ["request", "browser"]
    assert result.html == "<html><body>browser response</body></html>"
    assert result.used_browser is True
    assert result.fetch_policy == "direct_first"
    assert result.fetch_method == "browser"
    assert result.request_error == "500 Server Error"


def test_fetch_html_with_fallback_prefers_browser_first_for_known_anti_scraping_pages():
    calls: list[str] = []

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "<html><body>direct response</body></html>"

        def raise_for_status(self) -> None:
            return None

    result = fetch_html_with_fallback(
        "https://sai.cuhk.edu.cn/teacher-search",
        request_get=lambda _url, _timeout: (
            calls.append("request"),
            FakeResponse(),
        )[1],
        browser_fetch=lambda _url, _timeout: (
            calls.append("browser"),
            "<html><body>browser response</body></html>",
        )[1],
    )

    assert calls == ["browser"]
    assert result.html == "<html><body>browser response</body></html>"
    assert result.used_browser is True
    assert result.fetch_policy == "browser_first"
    assert result.fetch_method == "browser"


def test_fetch_html_with_fallback_keeps_direct_first_for_normal_pages():
    calls: list[str] = []

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "<html><body>direct response</body></html>"

        def raise_for_status(self) -> None:
            return None

    result = fetch_html_with_fallback(
        "https://www.sustech.edu.cn/zh/letter/",
        request_get=lambda _url, _timeout: (
            calls.append("request"),
            FakeResponse(),
        )[1],
        browser_fetch=lambda _url, _timeout: (
            calls.append("browser"),
            "<html><body>browser response</body></html>",
        )[1],
    )

    assert calls == ["request"]
    assert result.html == "<html><body>direct response</body></html>"
    assert result.used_browser is False
    assert result.fetch_policy == "direct_first"
    assert result.fetch_method == "direct"


def test_fetch_html_with_fallback_uses_browser_when_direct_response_body_is_empty():
    calls: list[str] = []

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "   "

        def raise_for_status(self) -> None:
            return None

    result = fetch_html_with_fallback(
        "https://www.sustech.edu.cn/zh/letter/",
        request_get=lambda _url, _timeout: (calls.append("request"), FakeResponse())[1],
        browser_fetch=lambda _url, _timeout: (
            calls.append("browser"),
            "<html><body>browser response</body></html>",
        )[1],
    )

    assert calls == ["request", "browser"]
    assert result.html == "<html><body>browser response</body></html>"
    assert result.fetch_method == "browser"


def test_discover_professor_seeds_resets_learned_fetch_policy_state_before_each_run(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    observed_policies: list[str] = []
    discovery_module._learned_browser_first_hosts.add("www.sustech.edu.cn")

    def fake_default_fetch(url: str) -> str:
        observed_policies.append(discovery_module._resolve_fetch_policy(url))
        return "* [李华](https://www.sustech.edu.cn/zh/faculties/lihua.html)"

    monkeypatch.setattr(discovery_module, "_default_fetch_html", fake_default_fetch)

    result = discovery_module.discover_professor_seeds(
        seeds=[
            ProfessorRosterSeed(
                institution="南方科技大学",
                department=None,
                roster_url="https://www.sustech.edu.cn/zh/letter/",
            )
        ]
    )

    assert observed_policies == ["direct_first"]
    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李华", "https://www.sustech.edu.cn/zh/faculties/lihua.html")
    ]


def test_fetch_html_with_fallback_learns_reader_first_after_browser_path_proves_unusable(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_learned_browser_first_hosts", set())
    monkeypatch.setattr(discovery_module, "_learned_reader_first_hosts", set())

    browser_calls: list[str] = []
    reader_calls: list[str] = []

    def request_get(_url: str, _timeout: float):
        raise requests.exceptions.SSLError("tls handshake failure")

    def browser_fetch(url: str, _timeout: float) -> str:
        browser_calls.append(url)
        raise RuntimeError(
            "playwright browser runtime unavailable: Page.goto: net::ERR_CONNECTION_CLOSED"
        )

    def reader_fetch(url: str, _timeout: float) -> str:
        reader_calls.append(url)
        return f"reader content for {url}"

    first = fetch_html_with_fallback(
        "https://sai.cuhk.edu.cn/teacher/102",
        request_get=request_get,
        browser_fetch=browser_fetch,
        reader_fetch=reader_fetch,
    )
    second = fetch_html_with_fallback(
        "https://sai.cuhk.edu.cn/teacher/108",
        request_get=request_get,
        browser_fetch=browser_fetch,
        reader_fetch=reader_fetch,
    )

    assert first.fetch_policy == "browser_first"
    assert first.fetch_method == "reader"
    assert second.fetch_policy == "reader_first"
    assert second.fetch_method == "reader"
    assert browser_calls == ["https://sai.cuhk.edu.cn/teacher/102"]
    assert reader_calls == [
        "https://sai.cuhk.edu.cn/teacher/102",
        "https://sai.cuhk.edu.cn/teacher/108",
    ]


def test_fetch_html_with_fallback_reader_first_does_not_retry_reader_after_browser_failure(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    url = "https://sai.cuhk.edu.cn/teacher/102"
    monkeypatch.setattr(discovery_module, "_learned_reader_first_hosts", {"sai.cuhk.edu.cn"})

    browser_calls: list[str] = []
    reader_calls: list[str] = []

    def request_get(_url: str, _timeout: float):
        raise requests.exceptions.SSLError("tls handshake failure")

    def browser_fetch(_url: str, _timeout: float) -> str:
        browser_calls.append(_url)
        raise RuntimeError("playwright browser runtime unavailable")

    def reader_fetch(_url: str, _timeout: float) -> str:
        reader_calls.append(_url)
        raise RuntimeError("reader transport unavailable")

    result = fetch_html_with_fallback(
        url,
        request_get=request_get,
        browser_fetch=browser_fetch,
        reader_fetch=reader_fetch,
    )

    assert result.html is None
    assert result.fetch_policy == "reader_first"
    assert result.fetch_method is None
    assert result.request_error == "tls handshake failure"
    assert result.browser_error == "reader transport unavailable | playwright browser runtime unavailable"
    assert reader_calls == [url]
    assert browser_calls == [url]


def test_fetch_html_with_fallback_uses_reader_when_request_and_browser_fail():
    result = fetch_html_with_fallback(
        "https://www.sustech.edu.cn/zh/letter/",
        request_get=lambda url, timeout: (_ for _ in ()).throw(
            requests.exceptions.SSLError("tls handshake failure")
        ),
        browser_fetch=lambda url, timeout: (_ for _ in ()).throw(
            RuntimeError("playwright browser runtime unavailable")
        ),
        reader_fetch=lambda url, timeout: (
            "[吴亚北 研究助理教授 材料科学与工程系](https://www.sustech.edu.cn/zh/faculties/wuyabei.html)"
        ),
    )

    assert "吴亚北" in (result.html or "")
    assert result.used_browser is False
    assert result.blocked_by_anti_scraping is True
    assert result.request_error == "tls handshake failure"
    assert result.browser_error == "playwright browser runtime unavailable"


def test_fetch_html_with_fallback_treats_412_as_anti_scraping_and_uses_reader_fallback():
    request_response = requests.Response()
    request_response.status_code = 412
    request_response._content = "precondition failed".encode("utf-8")
    request_response.url = "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1"

    result = fetch_html_with_fallback(
        "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
        request_get=lambda _url, _timeout: request_response,
        browser_fetch=lambda _url, _timeout: "",
        reader_fetch=lambda _url, _timeout: "* [张三](https://csse.szu.edu.cn/info/1001/1001.htm)",
    )

    assert result.html == "* [张三](https://csse.szu.edu.cn/info/1001/1001.htm)"
    assert result.blocked_by_anti_scraping


def test_fetch_html_with_fallback_reports_blocked_200_request_error():
    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "<html><body>Just a moment...</body></html>"

        def raise_for_status(self) -> None:
            return None

    result = fetch_html_with_fallback(
        "https://example.edu/teacher-search",
        request_get=lambda _url, _timeout: FakeResponse(),
        browser_fetch=lambda _url, _timeout: (_ for _ in ()).throw(
            RuntimeError("playwright browser runtime unavailable")
        ),
        reader_fetch=lambda _url, _timeout: (_ for _ in ()).throw(
            RuntimeError("reader transport unavailable")
        ),
    )

    assert result.html is None
    assert result.request_error == "200 blocked (anti-scraping detected)"
    assert result.browser_error == (
        "playwright browser runtime unavailable | reader transport unavailable"
    )


def test_fetch_html_with_fallback_ignores_cache_when_fetchers_are_injected(tmp_path, monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_cache_dir", lambda: tmp_path)
    cache_file = discovery_module._cache_path("https://sai.cuhk.edu.cn/teacher-search")
    cache_file.write_text(
        json.dumps({"url": "https://sai.cuhk.edu.cn/teacher-search", "content": "stale"}),
        encoding="utf-8",
    )

    result = fetch_html_with_fallback(
        "https://sai.cuhk.edu.cn/teacher-search",
        request_get=lambda url, timeout: (_ for _ in ()).throw(
            requests.exceptions.SSLError("tls handshake failure")
        ),
        browser_fetch=lambda url, timeout: (
            '<html><body><a href="/teacher/102">李海洲</a></body></html>'
        ),
    )

    assert "李海洲" in (result.html or "")
    assert cache_file.read_text(encoding="utf-8") == json.dumps(
        {"url": "https://sai.cuhk.edu.cn/teacher-search", "content": "stale"}
    )


def test_fetch_html_with_fallback_refreshes_stale_teacher_search_reader_cache(tmp_path, monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_cache_dir", lambda: tmp_path)
    cache_file = discovery_module._cache_path("https://sse.cuhk.edu.cn/teacher-search")
    cache_file.write_text(
        json.dumps(
            {
                "url": "https://sse.cuhk.edu.cn/teacher-search",
                "content": "Title: Teacher Search | 香港中文大学（深圳）理工学院\nMarkdown Content:\n[学院概况](https://sse.cuhk.edu.cn/node/411)",
            }
        ),
        encoding="utf-8",
    )

    fresh_html = """
    <html><body>
      <div class="list-title"><a href="https://jianwei.cuhk.edu.cn/">黄建伟</a></div>
    </body></html>
    """

    result = fetch_html_with_fallback(
        "https://sse.cuhk.edu.cn/teacher-search",
        request_get=lambda _url, _timeout: type(
            "Resp",
            (),
            {
                "status_code": 200,
                "encoding": "utf-8",
                "apparent_encoding": "utf-8",
                "text": fresh_html,
                "raise_for_status": lambda self: None,
            },
        )(),
    )

    assert "黄建伟" in (result.html or "")


def test_fetch_html_with_fallback_propagates_non_request_exceptions(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    monkeypatch.setattr(discovery_module, "_learned_browser_first_hosts", set())
    monkeypatch.setattr(discovery_module, "_learned_reader_first_hosts", set())

    with pytest.raises(RuntimeError, match="boom"):
        fetch_html_with_fallback(
            "https://www.sustech.edu.cn/zh/letter/",
            request_get=lambda url, timeout: (_ for _ in ()).throw(RuntimeError("boom")),
            browser_fetch=lambda url, timeout: (
                '<html><body><a href="/teacher/102">李海洲</a></body></html>'
            ),
        )


def test_discover_professor_seeds_recurses_into_hub_pages_with_department_context():
    seeds = [
        ProfessorRosterSeed(
            institution="深圳大学",
            department=None,
            roster_url="https://www.szu.edu.cn/szdw/jsjj.htm",
        )
    ]
    pages = {
        "https://www.szu.edu.cn/szdw/jsjj.htm": """
        <html><body>
          <ul class="l18-q">
            <li><h4><a href="https://cs.szu.edu.cn/szdw/jsjj.htm">计算机与软件学院</a></h4></li>
            <li><h4><a href="https://law.szu.edu.cn/szdw/jsjj.htm">法学院</a></h4></li>
          </ul>
        </body></html>
        """,
        "https://cs.szu.edu.cn/szdw/jsjj.htm": """
        <html><body>
          <ul>
            <li><a href="/teacher/lihua.htm">李华</a></li>
            <li><a href="/teacher/wangwu.htm">王五</a></li>
          </ul>
        </body></html>
        """,
        "https://law.szu.edu.cn/szdw/jsjj.htm": """
        <html><body>
          <ul>
            <li><a href="/teacher/zhaoliu.htm">赵六</a></li>
          </ul>
        </body></html>
        """,
    }

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=lambda url: pages[url],
        limits=DiscoveryLimits(max_depth=2, max_candidate_links_per_page=8, max_pages_per_seed=8),
    )

    assert [(item.name, item.department, item.profile_url) for item in result.professors] == [
        ("李华", "计算机与软件学院", "https://cs.szu.edu.cn/teacher/lihua.htm"),
        ("王五", "计算机与软件学院", "https://cs.szu.edu.cn/teacher/wangwu.htm"),
        ("赵六", "法学院", "https://law.szu.edu.cn/teacher/zhaoliu.htm"),
    ]
    assert result.source_statuses[0].status == "resolved"
    assert result.source_statuses[0].visited_urls == [
        "https://www.szu.edu.cn/szdw/jsjj.htm",
        "https://cs.szu.edu.cn/szdw/jsjj.htm",
        "https://law.szu.edu.cn/szdw/jsjj.htm",
    ]


def test_discover_professor_seeds_uses_sigs_api_without_html_fetch():
    seeds = [
        ProfessorRosterSeed(
            institution="清华大学深圳国际研究生院",
            department=None,
            roster_url="https://www.sigs.tsinghua.edu.cn/7644/list.htm",
        )
    ]

    def fail_fetch_html(_: str) -> str:
        raise AssertionError("html fetch should not be used for SIGS api discovery")

    def fake_fetch_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        assert url == (
            "https://www.sigs.tsinghua.edu.cn/_wp3services/generalQuery?queryObj=teacherHome"
        )
        assert payload["rows"] == 999
        return {
            "total": 2,
            "data": [
                {
                    "title": "李立浧院士",
                    "cnUrl": "http://www.sigs.tsinghua.edu.cn/llyys/main.htm",
                },
                {
                    "title": "王伟",
                    "cnUrl": "/wangwei/main.htm",
                },
            ],
            "lastPageNum": 1,
            "pageCount": 1,
            "endExeTime": "1ms",
        }

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fail_fetch_html,
        fetch_json=fake_fetch_json,
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李立浧院士", "http://www.sigs.tsinghua.edu.cn/llyys/main.htm"),
        ("王伟", "https://www.sigs.tsinghua.edu.cn/wangwei/main.htm"),
    ]
    assert result.source_statuses[0].status == "resolved"
    assert result.source_statuses[0].reason == "sigs_teacher_api"


def test_discover_professor_seeds_uses_hit_api_endpoint():
    seeds = [
        ProfessorRosterSeed(
            institution="哈尔滨工业大学（深圳）",
            department=None,
            roster_url=(
                "https://homepage.hit.edu.cn/school-dept?id=1&browseName="
                "%E6%A0%A1%E5%86%85%E5%8D%95%E4%BD%8D&browseEnName=DEPARTMENT"
            ),
        )
    ]

    def fail_fetch_html(_: str) -> str:
        raise AssertionError("html fetch should not be used for HIT api discovery")

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_fetch_json(url: str, payload: dict[str, object]) -> object:
        calls.append((url, payload))
        if url.endswith("executeBrowseAllOfSchoolDepartSz.do"):
            return [
                {
                    "id": "999903600000",
                    "deptname": "计算机科学与技术学院（深圳）",
                    "parentid": "999903600015",
                    "value": 107,
                }
            ]
        if url.endswith("getUserInfoByDeptId.do"):
            assert payload["deptId"] == "999903600000"
            return [
                {
                    "userName": "王轩",
                    "englishName": "Xuan Wang",
                    "department": "计算机科学与技术学院（深圳）",
                    "url": "wangxuan",
                    "shortDescription": "决策智能、CAAI会士",
                }
            ]
        raise AssertionError(f"unexpected url: {url}")

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fail_fetch_html,
        fetch_json=fake_fetch_json,
    )

    assert len(calls) == 2
    assert [(item.name, item.department, item.profile_url) for item in result.professors] == [
        (
            "王轩",
            "计算机科学与技术学院（深圳）",
            "https://homepage.hit.edu.cn/wangxuan?lang=zh",
        )
    ]
    assert result.source_statuses[0].status == "resolved"
    assert result.source_statuses[0].reason == "hit_teacher_api"


def test_validate_roster_discovery_document_aggregates_duplicates_and_fetch_failures():
    markdown_text = """
## 深圳大学
### 计算机与软件学院
- https://example.edu/roster/a
- https://example.edu/roster/b
- https://example.edu/roster/fail
"""

    pages = {
        "https://example.edu/roster/a": """
        <ul>
          <li><a href="/faculty/lihua">李华</a></li>
          <li><a href="/faculty/wangwu">王五</a></li>
        </ul>
        """,
        "https://example.edu/roster/b": """
        <ul>
          <li><a href="/people/lihua">李华</a></li>
          <li><a href="/faculty/zhaoliu">赵六</a></li>
        </ul>
        """,
    }

    def fake_fetch(url: str) -> str:
        if url == "https://example.edu/roster/fail":
            raise RuntimeError("network timeout")
        return pages[url]

    report = validate_roster_discovery_document(
        markdown_text,
        document_name="docs/教授 URL.md",
        fetch_html=fake_fetch,
    )

    assert report.seed_source_count == 3
    assert report.unique_seed_source_count == 3
    assert report.discovered_professor_count == 4
    assert report.unique_professor_identity_count == 3
    assert report.duplicate_professor_identities == ["李华|深圳大学|计算机与软件学院"]
    assert report.failed_fetch_urls == ["https://example.edu/roster/fail"]


def test_discover_professor_seeds_falls_back_to_recursive_html_when_sigs_api_fails():
    seeds = [
        ProfessorRosterSeed(
            institution="清华大学深圳国际研究生院",
            department=None,
            roster_url="https://www.sigs.tsinghua.edu.cn/7644/list.htm",
        )
    ]

    markdown = """
* [李立浧 讲席教授 智能制造学院](https://www.sigs.tsinghua.edu.cn/llyys/main.htm)
"""

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=lambda url: markdown,
        fetch_json=lambda url, payload: (_ for _ in ()).throw(RuntimeError("api down")),
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李立浧", "https://www.sigs.tsinghua.edu.cn/llyys/main.htm")
    ]
    assert result.source_statuses[0].status == "resolved"


def test_discover_professor_seeds_prefers_inline_seed_label_over_profile_page_noise(monkeypatch):
    seeds = [
        ProfessorRosterSeed(
            institution="清华大学深圳国际研究生院",
            department="智能制造学院",
            roster_url="https://www.sigs.tsinghua.edu.cn/llyys/main.htm",
            label="李立浧",
        )
    ]

    calls = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return "<html><head><title>李立浧 - 智能制造学院</title></head><body></body></html>"

    def fake_extract_roster_entries(*args, **kwargs):
        return [
            DiscoveredProfessorSeed(
                name="智能制造学院",
                institution="清华大学深圳国际研究生院",
                department="智能制造学院",
                profile_url="https://www.sigs.tsinghua.edu.cn/llyys/main.htm",
                source_url="https://www.sigs.tsinghua.edu.cn/llyys/main.htm",
            )
        ]

    monkeypatch.setattr(
        "src.data_agents.professor.discovery.extract_roster_entries",
        fake_extract_roster_entries,
    )

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李立浧", "https://www.sigs.tsinghua.edu.cn/llyys/main.htm")
    ]
    assert result.source_statuses[0].reason == "direct_profile_seed_fetched"
    assert result.source_statuses[0].visited_urls == [
        "https://www.sigs.tsinghua.edu.cn/llyys/main.htm"
    ]
    assert calls == ["https://www.sigs.tsinghua.edu.cn/llyys/main.htm"]


def test_discover_professor_seeds_treats_root_homepage_with_person_seed_label_as_direct_profile(monkeypatch):
    seeds = [
        ProfessorRosterSeed(
            institution="香港中文大学（深圳）",
            department="理工学院",
            roster_url="https://jianwei.cuhk.edu.cn/",
            label="黄建伟",
        )
    ]

    calls = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return "<html><head><title>黄建伟 @ CUHK</title></head><body></body></html>"

    monkeypatch.setattr(
        "src.data_agents.professor.discovery.extract_roster_entries",
        lambda *args, **kwargs: [],
    )

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("黄建伟", "https://jianwei.cuhk.edu.cn/")
    ]
    assert result.source_statuses[0].reason == "direct_profile_seed_fetched"
    assert calls == ["https://jianwei.cuhk.edu.cn/"]


def test_discover_professor_seeds_does_not_treat_institutional_root_homepage_with_person_label_as_direct_profile():
    seeds = [
        ProfessorRosterSeed(
            institution="南方科技大学",
            department=None,
            roster_url="https://www.sustech.edu.cn/",
            label="李华",
        )
    ]

    def fake_fetch_html(url: str) -> str:
        raise RuntimeError("expected fallback discovery path")

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert result.professors == []
    assert result.source_statuses[0].reason == "fetch_failed"


def test_cuhk_page_url_preserves_existing_query_for_first_page():
    from src.data_agents.professor import discovery as discovery_module

    assert (
        discovery_module._cuhk_page_url(
            "https://example.cuhk.edu.cn/teacher-search?dept=cs",
            0,
        )
        == "https://example.cuhk.edu.cn/teacher-search?dept=cs"
    )


def test_discover_cuhk_seed_respects_max_pages_limit():
    from src.data_agents.professor import discovery as discovery_module

    seed = ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        roster_url="https://sai.cuhk.edu.cn/teacher-search",
    )

    visited = []
    names = ["李海洲", "崔曙光", "段成国"]

    def fetch_html(url: str) -> str:
        visited.append(url)
        page_no = len(visited)
        return f'<html><body><div class="list-title"><a href="https://sai.cuhk.edu.cn/teacher/{page_no}">{names[page_no - 1]}</a></div></body></html>'

    result = discovery_module._discover_cuhk_seed(
        seed,
        fetch_html=fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=3),
    )

    assert len(result.professors) == 3
    assert visited == [
        "https://sai.cuhk.edu.cn/teacher-search",
        "https://sai.cuhk.edu.cn/teacher-search?page=1",
        "https://sai.cuhk.edu.cn/teacher-search?page=2",
    ]


def test_discover_cuhk_seed_stops_after_repeated_profile_pages():
    from src.data_agents.professor import discovery as discovery_module

    seed = ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        roster_url="https://sai.cuhk.edu.cn/teacher-search",
    )

    repeated_html = """
    <html><body>
      <div class="list-title"><a href="https://sai.cuhk.edu.cn/teacher/102">李海洲</a></div>
    </body></html>
    """

    pages = {
        "https://sai.cuhk.edu.cn/teacher-search": repeated_html,
        "https://sai.cuhk.edu.cn/teacher-search?page=1": repeated_html,
    }

    result = discovery_module._discover_cuhk_seed(
        seed,
        fetch_html=lambda url: pages[url],
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李海洲", "https://sai.cuhk.edu.cn/teacher/102")
    ]
    assert result.status.visited_urls == [
        "https://sai.cuhk.edu.cn/teacher-search",
        "https://sai.cuhk.edu.cn/teacher-search?page=1",
    ]


def test_discover_cuhk_seed_filters_non_person_names():
    from src.data_agents.professor import discovery as discovery_module

    seed = ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="理工学院",
        roster_url="https://sse.cuhk.edu.cn/teacher-search",
    )

    html = """
    <html><body>
      <div class="list-title"><a href="https://sse.cuhk.edu.cn/teacher/1">信息工程学院</a></div>
      <div class="list-title"><a href="https://sse.cuhk.edu.cn/teacher/2">崔曙光</a></div>
    </body></html>
    """

    result = discovery_module._discover_cuhk_seed(seed, fetch_html=lambda _url: html)

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("崔曙光", "https://sse.cuhk.edu.cn/teacher/2")
    ]


def test_discover_professor_seeds_treats_root_homepage_with_comma_formatted_english_name_as_direct_profile(monkeypatch):
    seeds = [
        ProfessorRosterSeed(
            institution="香港中文大学（深圳）",
            department="医学院",
            roster_url="https://miha.cuhk.edu.cn/",
            label="BRESAR, Miha",
        )
    ]

    calls = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return "<html><head><title>BRESAR, Miha @ CUHK</title></head><body></body></html>"

    monkeypatch.setattr(
        "src.data_agents.professor.discovery.extract_roster_entries",
        lambda *args, **kwargs: [],
    )

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("BRESAR, Miha", "https://miha.cuhk.edu.cn/")
    ]
    assert result.source_statuses[0].reason == "direct_profile_seed_fetched"
    assert calls == ["https://miha.cuhk.edu.cn/"]


def test_discover_professor_seeds_treats_detail_profile_url_without_person_label_as_direct_profile():
    seeds = [
        ProfessorRosterSeed(
            institution="中山大学（深圳）",
            department="材料学院",
            roster_url="http://materials.sysu.edu.cn/teacher/162",
            label=None,
        )
    ]

    calls = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return "<html><head><title>陈少川 - 材料学院</title></head><body></body></html>"

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("陈少川", "http://materials.sysu.edu.cn/teacher/162")
    ]
    assert result.source_statuses[0].reason == "direct_profile_seed_fetched"
    assert calls == ["http://materials.sysu.edu.cn/teacher/162"]


def test_looks_like_direct_profile_url_rejects_generic_roster_leaf_pages():
    from src.data_agents.professor import discovery as discovery_module

    assert not discovery_module._looks_like_direct_profile_url(
        "https://example.edu/szll.htm"
    )
    assert not discovery_module._looks_like_direct_profile_url(
        "https://example.edu/jsml.htm"
    )


def test_looks_like_direct_profile_url_rejects_generic_info_pages():
    from src.data_agents.professor import discovery as discovery_module

    assert not discovery_module._looks_like_direct_profile_url(
        "https://example.edu/info/news/1234.htm"
    )
    assert not discovery_module._looks_like_direct_profile_url(
        "https://example.edu/info/contact.htm"
    )
    assert not discovery_module._looks_like_direct_profile_url(
        "http://materials.sysu.edu.cn/faculty/staff"
    )
    assert discovery_module._looks_like_direct_profile_url(
        "https://example.edu/teacher/1234.htm"
    )


def test_looks_like_direct_profile_url_rejects_teacher_category_pages():
    from src.data_agents.professor import discovery as discovery_module

    assert not discovery_module._looks_like_direct_profile_url(
        "https://szmed.sysu.edu.cn/zh-hans/teachers/professor"
    )
    assert not discovery_module._looks_like_direct_profile_url(
        "https://szmed.sysu.edu.cn/zh-hans/teachers/associate-professor"
    )


def test_discover_professor_seeds_treats_info_detail_page_with_matching_seed_label_as_direct_profile(monkeypatch):
    seeds = [
        ProfessorRosterSeed(
            institution="深圳技术大学",
            department="人工智能学院",
            roster_url="https://ai.sztu.edu.cn/info/1332/6055.htm",
            label="梁永生",
        )
    ]

    calls = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return """
        <html>
          <head><title>梁永生-人工智能学院</title></head>
          <body>
            <div class="page_content_teacher">
              <div class="content_teacher_box">
                <h2>梁永生</h2>
                <div class="v_news_content">
                  <p>梁永生，现任深圳技术大学副校长、哈尔滨工业大学（深圳）电子与信息工程学院二级教授、博士生导师。</p>
                </div>
              </div>
            </div>
          </body>
        </html>
        """

    def fail_extract_roster_entries(*args, **kwargs):
        raise AssertionError("direct profile detail page should short-circuit before roster extraction")

    monkeypatch.setattr(
        "src.data_agents.professor.discovery.extract_roster_entries",
        fail_extract_roster_entries,
    )

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch_html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("梁永生", "https://ai.sztu.edu.cn/info/1332/6055.htm")
    ]
    assert result.source_statuses[0].reason == "direct_profile_seed_fetched"
    assert result.source_statuses[0].visited_urls == [
        "https://ai.sztu.edu.cn/info/1332/6055.htm"
    ]
    assert calls == ["https://ai.sztu.edu.cn/info/1332/6055.htm"]


def test_discover_professor_seeds_treats_root_homepage_with_personal_title_as_direct_profile():
    seeds = [
        ProfessorRosterSeed(
            institution="香港中文大学（深圳）",
            department=None,
            roster_url="https://jianwei.cuhk.edu.cn/",
            label=None,
        )
    ]

    html = """
    <html>
      <head><title>Jianwei Huang @ CUHK</title></head>
      <body>
        <a href="teaching.html">Teaching</a>
        <a href="presentations.html">Presentation</a>
        <a href="services.html">Service</a>
        <a href="Files/CV.pdf">CV</a>
      </body>
    </html>
    """

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=lambda url: html,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=4),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("Jianwei Huang", "https://jianwei.cuhk.edu.cn/")
    ]
    assert result.source_statuses[0].reason == "direct_profile_homepage"


def test_discover_professor_seeds_tries_seed_fallback_url_when_primary_seed_fails():
    seeds = [
        ProfessorRosterSeed(
            institution="南方科技大学",
            department=None,
            roster_url="https://www.sustech.edu.cn/zh/letter/",
        )
    ]
    pages = {
        "https://www.sustech.edu.cn/zh/faculty_members.html": """
        * [计算机科学与工程系](https://cse.sustech.edu.cn/faculty/full-time-faculty/)
        """,
        "https://cse.sustech.edu.cn/faculty/full-time-faculty/": """
        <html><body>
          <ul>
            <li><a href="/faculty/lihua">李华</a></li>
          </ul>
        </body></html>
        """,
    }

    def fake_fetch(url: str) -> str:
        if url == "https://www.sustech.edu.cn/zh/letter/":
            raise RuntimeError("tls failure")
        return pages[url]

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch,
        limits=DiscoveryLimits(max_depth=2, max_candidate_links_per_page=8, max_pages_per_seed=8),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李华", "https://cse.sustech.edu.cn/faculty/lihua")
    ]
    assert result.source_statuses[0].status == "resolved"
    assert result.source_statuses[0].visited_urls == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://www.sustech.edu.cn/zh/faculty_members.html",
        "https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    ]


def test_discover_professor_seeds_skips_seed_fallback_pages_when_primary_page_already_has_candidates():
    seeds = [
        ProfessorRosterSeed(
            institution="南方科技大学",
            department=None,
            roster_url="https://www.sustech.edu.cn/zh/letter/",
        )
    ]
    pages = {
        "https://www.sustech.edu.cn/zh/letter/": """
        * [计算机科学与工程系](https://cse.sustech.edu.cn/faculty/full-time-faculty/)
        """,
        "https://cse.sustech.edu.cn/faculty/full-time-faculty/": """
        <html><body>
          <ul>
            <li><a href="/faculty/lihua">李华</a></li>
          </ul>
        </body></html>
        """,
    }

    def fake_fetch(url: str) -> str:
        if url == "https://www.sustech.edu.cn/zh/faculty_members.html":
            raise AssertionError("fallback page should not be fetched when primary page already yields candidates")
        return pages[url]

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch,
        limits=DiscoveryLimits(max_depth=2, max_candidate_links_per_page=8, max_pages_per_seed=8),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("李华", "https://cse.sustech.edu.cn/faculty/lihua")
    ]
    assert result.source_statuses[0].visited_urls == [
        "https://www.sustech.edu.cn/zh/letter/",
        "https://cse.sustech.edu.cn/faculty/full-time-faculty/",
    ]


def test_discover_professor_seeds_prioritizes_configured_seed_fallback_when_primary_page_is_homepage_redirect(monkeypatch):
    from src.data_agents.professor import discovery as discovery_module

    seed_url = "http://sa.sysu.edu.cn/zh-hans/teacher/faculty"
    fallback_url = "https://ab.sysu.edu.cn/zh-hans/teacher/faculty"
    seeds = [
        ProfessorRosterSeed(
            institution="中山大学（深圳）",
            department="农业与生物技术学院",
            roster_url=seed_url,
        )
    ]
    pages = {
        seed_url: """
        <html>
          <head>
            <title>首页 | 中山大学农业与生物技术学院</title>
            <link rel="canonical" href="https://ab.sysu.edu.cn/zh-hans" />
          </head>
          <body>
            <a href="/zh-hans/article/1338">学术交流</a>
            <a href="/zh-hans/taxonomy/term/66">兼职教授</a>
          </body>
        </html>
        """,
        fallback_url: """
        <html><body>
          <div class="views-row">
            <a href="/teacher/123">详情</a>
            <div class="list-title"><strong>张三</strong></div>
          </div>
        </body></html>
        """,
    }

    def fake_fetch(url: str) -> str:
        return pages[url]

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch,
        limits=DiscoveryLimits(max_depth=1, max_candidate_links_per_page=8, max_pages_per_seed=2),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("张三", "https://ab.sysu.edu.cn/teacher/123")
    ]
    assert result.source_statuses[0].visited_urls == [
        seed_url,
        fallback_url,
    ]


def test_discover_professor_seeds_tries_pkusz_fallback_urls_when_seed_path_is_stale():
    seeds = [
        ProfessorRosterSeed(
            institution="北京大学深圳研究生院",
            department="人文社会科学学院",
            roster_url="https://rw.pkusz.edu.cn/szll.htm",
        )
    ]
    pages = {
        "https://shss.pkusz.edu.cn/szdw/jsml.htm": """
        <html><body>
          <ul>
            <li><a href="/info/1001/1002.htm">陈一</a></li>
          </ul>
        </body></html>
        """,
    }

    def fake_fetch(url: str) -> str:
        if url == "https://rw.pkusz.edu.cn/szll.htm":
            raise RuntimeError("404 stale seed")
        return pages[url]

    result = discover_professor_seeds(
        seeds=seeds,
        fetch_html=fake_fetch,
        limits=DiscoveryLimits(
            max_depth=1,
            max_candidate_links_per_page=8,
            max_pages_per_seed=8,
        ),
    )

    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("陈一", "https://shss.pkusz.edu.cn/info/1001/1002.htm")
    ]
    assert result.source_statuses[0].status == "resolved"


def test_extract_roster_page_links_filters_sustech_navigation_noise():
    markdown = """
### [院系设置](https://www.sustech.edu.cn/zh/letter/#)
1. [理学院](https://science.sustech.edu.cn/)
2. [数学系](https://math.sustech.edu.cn/?lang=zh)
3. [科研机构](https://www.sustech.edu.cn/zh/research-institutions.html)
4. [常用系统](https://www.sustech.edu.cn/zh/common-systems.html)
5. [联系我们](https://www.sustech.edu.cn/zh/contact_us.html)

### [教育教学](https://www.sustech.edu.cn/zh/letter/#)
1. [本科教学](http://tao.sustech.edu.cn/)
"""

    links = extract_roster_page_links(markdown, "https://www.sustech.edu.cn/zh/letter/")

    assert links == [
        ("https://science.sustech.edu.cn/", "理学院"),
        ("https://math.sustech.edu.cn/?lang=zh", "数学系"),
    ]


def test_validate_roster_discovery_document_reports_unresolved_sources():
    markdown_text = """
香港中文大学（深圳）人工智能学院 https://sai.cuhk.edu.cn/teacher-search
"""

    report = validate_roster_discovery_document(
        markdown_text,
        document_name="docs/教授 URL.md",
        fetch_html=lambda _: "<html><body><div id='app'></div></body></html>",
    )

    assert report.discovered_professor_count == 0
    assert report.unresolved_seed_source_count == 1
    assert report.unresolved_seed_sources == [
        "https://sai.cuhk.edu.cn/teacher-search|香港中文大学（深圳）|人工智能学院|cuhk_teacher_search_empty"
    ]


def test_validate_roster_discovery_document_fails_on_empty_document():
    with pytest.raises(SeedDocumentValidationError, match="contains no roster URLs"):
        validate_roster_discovery_document(
            "",
            document_name="docs/教授 URL.md",
            fetch_html=lambda _: "<html></html>",
        )


def test_extract_roster_entries_skips_szu_profile_detail_pages_to_avoid_nav_pollution():
    html = """
    <html>
      <head><title>靳玉乐-深圳大学-教育学部</title></head>
      <body>
        <a href="/xbgk/xrld.htm">现任领导</a>
        <a href="/dqgz/zzsz.htm">组织机构</a>
        <a href="/szdw/js1.htm">教授</a>
      </body>
    </html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="教育学部",
        source_url="http://fe.szu.edu.cn/info/1021/1191.htm",
    )

    assert entries == []


def test_extract_roster_entries_skips_pkusz_profile_detail_pages_to_avoid_nav_pollution():
    html = """
    <html>
      <head><title>白志强-北京大学信息工程学院</title></head>
      <body>
        <a href="/xygk/xrld.htm">现任领导</a>
        <a href="/xwzx.htm">新闻中心</a>
        <a href="/kxyj/kyxm.htm">科研项目</a>
      </body>
    </html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="北京大学深圳研究生院",
        department="信息工程学院",
        source_url="https://www.ece.pku.edu.cn/info/1046/2141.htm",
    )

    assert entries == []


def test_extract_roster_entries_normalizes_bom_prefixed_szu_names():
    html = """
    <html><body>
      <div class="news_con">
        <a href="/info/1046/2800.htm">\ufeff陈冠亨</a>
      </div>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="高等研究院",
        source_url="https://ias.szu.edu.cn/szdw/yjyry.htm",
    )

    assert [entry.name for entry in entries] == ["陈冠亨"]


def test_extract_roster_entries_prefers_cuhk_teacher_markdown_links_over_navigation():
    markdown = """
Title: 教师搜索 | 人工智能学院

Markdown Content:
* [返回主站](https://www.cuhk.edu.cn/)
* [院长致辞](https://sai.cuhk.edu.cn/page/42)
* [精彩活动](https://sai.cuhk.edu.cn/taxonomy/term/194)
* [李海洲](https://sai.cuhk.edu.cn/teacher/102)
* [荆炳义](https://sai.cuhk.edu.cn/teacher/162)
"""

    entries = extract_roster_entries(
        html=markdown,
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        source_url="https://sai.cuhk.edu.cn/teacher-search",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("李海洲", "https://sai.cuhk.edu.cn/teacher/102"),
        ("荆炳义", "https://sai.cuhk.edu.cn/teacher/162"),
    ]


def test_extract_roster_entries_supports_sysu_drupal_teacher_cards():
    html = """
    <html><body>
      <div class="list-images-1-1 inside-tb">
        <div class="list-left">
          <a href="/zh-hans/teacher/616"><img alt="" /></a>
        </div>
        <div class="list-content">
          <h4 class="list-title one-line">
            <strong>陈维清</strong>
            <span class="text-light">教授</span>
          </h4>
          <div class="list-more">
            <a target="_blank" href="/zh-hans/teacher/616">了解更多</a>
          </div>
        </div>
      </div>
      <div class="list-images-1-1 inside-tb">
        <div class="list-left">
          <a href="/zh-hans/teacher/177"><img alt="" /></a>
        </div>
        <div class="list-content">
          <h4 class="list-title one-line">
            <strong>李立明</strong>
            <span class="text-light">教授</span>
          </h4>
          <div class="list-more">
            <a target="_blank" href="/zh-hans/teacher/177">了解更多</a>
          </div>
        </div>
      </div>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="公共卫生学院（深圳）",
        source_url="https://phs.sysu.edu.cn/zh-hans/faculty",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("陈维清", "https://phs.sysu.edu.cn/zh-hans/teacher/616"),
        ("李立明", "https://phs.sysu.edu.cn/zh-hans/teacher/177"),
    ]


def test_extract_roster_entries_supports_sysu_business_school_teacher_cards():
    html = """
    <html><body>
      <div class="col-lg-6 teacher">
        <div class="row">
          <div class="col-sm-4 teacherpicture">
            <a href="1395853.htm"><img class="imgcontain" /></a>
          </div>
          <div class="col-sm-8 teacherinfo">
            <h3>李广众 <span>教授</span></h3>
            <a href="1395853.htm" class="btn btn-primary btn-sm">了解更多</a>
          </div>
        </div>
      </div>
      <div class="col-lg-6 teacher">
        <div class="row">
          <div class="col-sm-4 teacherpicture">
            <a href="1401906.htm"><img class="imgcontain" /></a>
          </div>
          <div class="col-sm-8 teacherinfo">
            <h3>刘冰 <span>教授</span></h3>
            <a href="1401906.htm" class="btn btn-primary btn-sm">了解更多</a>
          </div>
        </div>
      </div>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="管理学院(创业学院)",
        source_url="https://bschool.sysu.edu.cn/teacher/index.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("李广众", "https://bschool.sysu.edu.cn/teacher/1395853.htm"),
        ("刘冰", "https://bschool.sysu.edu.cn/teacher/1401906.htm"),
    ]


def test_extract_roster_entries_supports_sysu_faculty_item_cards():
    html = """
    <html><body>
      <div class="faculty-list-wrap">
        <a href="/zh-hans/teacher/169" target="_blank" class="faculty-item">
          <div class="faculty-item-info">
            <h4>黄维</h4>
            <p>中国科学院院士</p>
          </div>
        </a>
      </div>
      <div class="faculty-list-wrap">
        <a href="/zh-hans/teacher/81" target="_blank" class="faculty-item">
          <div class="faculty-item-info">
            <h4>秦天石</h4>
            <p>国家海外高层次人才引进计划青年项目入选者</p>
          </div>
        </a>
      </div>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="柔性电子学院",
        source_url="https://sofe.sysu.edu.cn/zh-hans/teachers/full-time",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("黄维", "https://sofe.sysu.edu.cn/zh-hans/teacher/169"),
        ("秦天石", "https://sofe.sysu.edu.cn/zh-hans/teacher/81"),
    ]


def test_extract_roster_entries_supports_sysu_markdown_teacher_links_before_heading_fallback():
    html = """
    # 正高级职称人员

    [程瑜](https://szmed.sysu.edu.cn/zh-hans/teacher/1656)
    [陈元](https://szmed.sysu.edu.cn/zh-hans/teacher/1159)
    [师资力量](https://szmed.sysu.edu.cn/zh-hans/teachers/professor)
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="医学院",
        source_url="https://szmed.sysu.edu.cn/zh-hans/teachers/professor",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("程瑜", "https://szmed.sysu.edu.cn/zh-hans/teacher/1656"),
        ("陈元", "https://szmed.sysu.edu.cn/zh-hans/teacher/1159"),
    ]


def test_extract_roster_entries_supports_inline_suat_records_without_anchor_tags():
    html = """
    <script>
    var teacherData = [
      {"showTitle":"叶克强","fields":{"gw":"讲席教授","name":"Keqiang Ye"},"url":"info/1022/1086.htm"},
      {"showTitle":"Helmut Kettenmann","fields":{"gw":"讲席教授"},"url":"info/1055/1058.htm"},
      {"showTitle":"师资概况","url":"xygk/szgk.htm"}
    ];
    </script>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳理工大学",
        department="生命健康学院",
        source_url="https://lhs.suat-sz.edu.cn/szdw.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("叶克强", "https://lhs.suat-sz.edu.cn/info/1022/1086.htm"),
        ("Helmut Kettenmann", "https://lhs.suat-sz.edu.cn/info/1055/1058.htm"),
    ]


def test_extract_roster_entries_keeps_latin_names_containing_en_substrings():
    html = """
    <html><body>
      <a href="/teacher/1001">Helmut Kettenmann</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="深圳理工大学",
        department="生命健康学院",
        source_url="https://lhs.suat-sz.edu.cn/faculty/index.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("Helmut Kettenmann", "https://lhs.suat-sz.edu.cn/teacher/1001")
    ]


def test_extract_roster_entries_strips_trailing_title_suffixes_from_chinese_names():
    html = """
    <html><body>
      <a href="/teacher/2001">罗锴教授</a>
      <a href="/teacher/2002">王涛副教授</a>
    </body></html>
    """

    entries = extract_roster_entries(
        html=html,
        institution="中山大学（深圳）",
        department="电子与通信工程学院",
        source_url="https://sece.sysu.edu.cn/szll/js/zngz/index.htm",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("罗锴", "https://sece.sysu.edu.cn/teacher/2001"),
        ("王涛", "https://sece.sysu.edu.cn/teacher/2002"),
    ]


def test_extract_roster_page_links_supports_inline_javascript_redirects():
    html = """
    <html><body>
      <script>
        window.location.replace("teacher01/index.htm");
      </script>
    </body></html>
    """

    links = extract_roster_page_links(html, "https://bme.sysu.edu.cn/teacher/index.htm")

    assert links == [("https://bme.sysu.edu.cn/teacher/teacher01/index.htm", "redirect")]
