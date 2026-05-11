"""Tests for the Patents-section homepage extractor.

Per OpenSpec change `prof-paper-patent-from-page-flow` spec Requirement
"Patents-section extraction from prof Tier 2/3 pages" + tasks.md T4.1 /
T4.2 / T4.4.
"""

from __future__ import annotations

from datetime import date

from src.data_agents.professor.homepage_patents import (
    PatentEntry,
    extract_patents_from_html,
)


# ---------------------------------------------------------------------------
# Scenario 1 (Acceptance §5): page has no Patents section → zero candidates,
# no pipeline_issue from the extractor side (extractor never files issues
# itself; absence is normal).
# ---------------------------------------------------------------------------


def test_no_patents_section_returns_empty_list():
    html = """
    <html><body>
      <h2>Publications</h2>
      <ul>
        <li>Foo Bar paper, J. Smith, Nature 2024.</li>
      </ul>
      <h2>About</h2>
      <p>Prof Smith has many patents in machine learning generally.</p>
    </body></html>
    """
    assert extract_patents_from_html(html, page_url="https://prof.test/page") == []


def test_empty_html_returns_empty_list():
    assert extract_patents_from_html("", page_url="https://prof.test/page") == []
    assert extract_patents_from_html("   ", page_url="https://prof.test/page") == []


# ---------------------------------------------------------------------------
# Scenario 2 (Acceptance §5): page has Patents section with only title →
# candidate produced with patent_id=None (downstream ingest decides whether
# to file a data_quality_flag pipeline_issue).
# ---------------------------------------------------------------------------


def test_title_only_patent_yields_candidate_with_no_patent_id():
    html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li>一种基于深度学习的图像分类方法</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "一种基于深度学习的图像分类方法"
    assert entry.patent_id is None
    assert entry.application_date is None
    assert entry.grant_date is None
    assert entry.inventors == ()


# ---------------------------------------------------------------------------
# Scenario 3 (Acceptance §5): page with full patent_id → candidate carries
# patent_id, dates, inventors. Conservative heading match also covers
# `Patent Applications`, `发明专利`, `实用新型`, `外观`.
# ---------------------------------------------------------------------------


def test_full_patent_id_with_chinese_heading():
    html = """
    <html><body>
      <h2>发明专利</h2>
      <ol>
        <li>一种基于深度学习的图像分类方法 (ZL202310012345.6,
            授权日 2024-06-15) 发明人: 张三, 李四</li>
      </ol>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    assert entries[0] == PatentEntry(
        title="一种基于深度学习的图像分类方法",
        patent_id="ZL202310012345.6",
        application_date=None,
        grant_date=date(2024, 6, 15),
        inventors=("张三", "李四"),
        source_url="https://prof.test/page",
        source_anchor=None,
    )


def test_full_patent_id_with_english_heading():
    html = """
    <html><body>
      <h3>Patent Applications</h3>
      <ul>
        <li>Method for foo bar baz, US20240567890A1</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    assert entries[0].title == "Method for foo bar baz"
    assert entries[0].patent_id == "US20240567890A1"


def test_chinese_date_format_is_parsed():
    html = """
    <html><body>
      <h2>发明专利</h2>
      <ul>
        <li>一种处理X的方法 (CN202410123456, 申请日 2024年3月12日)</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    assert entries[0].application_date == date(2024, 3, 12)
    assert entries[0].grant_date is None


def test_zl_x_checksum_suffix_is_preserved():
    html = """
    <html><body>
      <h2>专利</h2>
      <table>
        <tr><th>名称</th><th>专利号</th><th>授权日</th></tr>
        <tr>
          <td>《一种神经网络的训练方法》</td>
          <td>ZL202310099999.X</td>
          <td>2024-05-01</td>
        </tr>
      </table>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    assert entries[0].patent_id == "ZL202310099999.X"
    assert entries[0].grant_date == date(2024, 5, 1)


def test_paragraph_with_br_yields_each_item():
    html = """
    <html><body>
      <h2>专利</h2>
      <p>一种基于X的图像处理方法, ZL202310011111, 授权日 2024-01-15<br>
         一种处理大规模数据的方法, ZL202310022222, 授权日 2024-02-20</p>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 2
    assert {entry.patent_id for entry in entries} == {
        "ZL202310011111",
        "ZL202310022222",
    }


def test_zero_patents_when_publications_section_mentions_patents_in_body():
    """Conservative heading-only match: 'patent' appearing in body copy of
    an unrelated section must NOT trigger extraction."""
    html = """
    <html><body>
      <h2>Research Interests</h2>
      <p>Prof develops novel patents in computer vision and has filed
         several US patents in the last decade.</p>
    </body></html>
    """
    assert extract_patents_from_html(html, page_url="https://prof.test/page") == []


def test_dedup_identical_title_and_patent_id():
    html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li>一种基于深度学习的图像分类方法 (ZL202310012345.6)</li>
        <li>一种基于深度学习的图像分类方法 (ZL202310012345.6)</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1


def test_inventor_extraction_strips_inventor_prefix_from_title():
    html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li>一种用于X的方法, ZL202310045678.9, 发明人: 王五、赵六</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "一种用于X的方法"
    assert entry.inventors == ("王五", "赵六")


def test_year_only_is_not_recorded_as_partial_date():
    """A bare year on a prof page is ambiguous (filing vs grant); the
    extractor leaves dates None rather than fabricating Jan-1."""
    html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li>一种数据处理的方法 (ZL202210011111), 2022</li>
      </ul>
    </body></html>
    """
    entries = extract_patents_from_html(html, page_url="https://prof.test/page")
    assert len(entries) == 1
    assert entries[0].application_date is None
    assert entries[0].grant_date is None
