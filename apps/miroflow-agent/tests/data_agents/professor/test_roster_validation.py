import requests
import pytest
import json

from src.data_agents.professor.discovery import (
    DiscoveryLimits,
    discover_professor_seeds,
    fetch_html_with_fallback,
)
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.professor.parser import parse_roster_seed_markdown
from src.data_agents.professor.roster import extract_roster_entries, extract_roster_page_links
from src.data_agents.professor.validator import (
    SeedDocumentValidationError,
    validate_roster_discovery_document,
    validate_roster_seed_document,
)


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
    assert result.request_error == "tls handshake failure"
    assert result.browser_error is None


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


def test_fetch_html_with_fallback_propagates_non_request_exceptions():
    with pytest.raises(RuntimeError, match="boom"):
        fetch_html_with_fallback(
            "https://sai.cuhk.edu.cn/teacher-search",
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
        "https://sai.cuhk.edu.cn/teacher-search|香港中文大学（深圳）|人工智能学院|no_professor_entries_found"
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
