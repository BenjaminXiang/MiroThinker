from src.data_agents.professor.homepage_publications import (
    extract_publications_from_html,
)


def test_sysu_seed36_dense_representative_papers_stop_before_patents():
    html = """
    <html><body>
      <p>
        代表性论著：
        1. Qiang Li, Hui Zhang. Urban runoff pollutant control using green
        infrastructure. Water Research, 2024.
        2. Lei Chen, Qiang Li. Sponge city monitoring with graph neural
        networks. Environmental Science & Technology, 2023.
        主要发明专利：
        1. 一种水处理装置，申请号 CN202410123456.7。
      </p>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://sece.sysu.edu.cn/szll/js/zngz/1401951.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Urban runoff pollutant control using green infrastructure",
        "Sponge city monitoring with graph neural networks",
    ]
    assert all("主要发明专利" not in publication.raw_title for publication in publications)


def test_sysu_seed37_quoted_titles_after_authors_stop_at_patent_section():
    html = """
    <html><body>
      <main>
        <p>
          部分论文：
          1. 刘强、王明，“面向工业物联网的协同边缘智能调度”，计算机学报，2024。
          2. Zhang Q, Li M. "Robust Edge Intelligence for Industrial IoT".
          IEEE Internet of Things Journal, 2023.
          部分专利：
          1. 一种工业控制系统，申请号 CN202310000001.0。
        </p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://ise.sysu.edu.cn/teacher/ChenJunzhou",
    )

    assert [publication.clean_title for publication in publications] == [
        "面向工业物联网的协同边缘智能调度",
        "Robust Edge Intelligence for Industrial IoT",
    ]
    assert all("部分专利" not in publication.raw_title for publication in publications)


def test_sysu_seed38_bracketed_conference_tags_split_and_skip_patents():
    html = """
    <html><body>
      <section>
        <h2>论文成果</h2>
        <p>
          [DAC26] Y. Zhang*, Q. Li#, and M. Chen. Timing-driven placement for
          chiplet designs. Design Automation Conference, 2026.
          [TCAD25] L. Wu, H. Wang. Robust routing with variation awareness.
          IEEE Transactions on Computer-Aided Design, 2025.
          授权专利：CN202410999999.9 一种芯片互连优化方法。
        </p>
      </section>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://sic.sysu.edu.cn/members/t01/1409794.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Timing-driven placement for chiplet designs",
        "Robust routing with variation awareness",
    ]
    assert "Y. Zhang" in (publications[0].authors_text or "")
    assert "Q. Li" in (publications[0].authors_text or "")
    assert "M. Chen" in (publications[0].authors_text or "")
    assert "*" not in (publications[0].authors_text or "")
    assert "#" not in (publications[0].authors_text or "")
    assert "Design Automation Conference" in (publications[0].venue_text or "")
    assert all("专利" not in publication.raw_title for publication in publications)


def test_sysu_seed40_preserves_comma_title_and_ignores_student_author_note():
    html = """
    <html><body>
      <h2>Selected Publications</h2>
      <p>
        Wang J. (Ph.D. student), Li H., and Chen X. Uncovering, Explaining,
        and Mitigating Shortcut Learning in Vision Models. IEEE Transactions
        on Pattern Analysis and Machine Intelligence, 2024.
      </p>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://scst.sysu.edu.cn/teacher/DaiXianhua",
    )

    assert len(publications) == 1
    publication = publications[0]
    assert publication.clean_title == (
        "Uncovering, Explaining, and Mitigating Shortcut Learning in Vision Models"
    )
    assert "Wang J." in (publication.authors_text or "")
    assert "Li H." in (publication.authors_text or "")
    assert "Chen X" in (publication.authors_text or "")
    assert "student" not in (publication.authors_text or "").lower()


def test_sysu_seed41_title_first_math_citations_keep_proc_as_venue():
    html = """
    <html><body>
      <p>
        Representative Papers:
        1. Rigidity of mean curvature flows in hyperbolic space. Proc. Amer.
        Math. Soc., 2024.
        2. Spectral gaps for nonlinear Schrodinger operators. Journal of
        Mathematical Physics, 2023.
      </p>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://science.sysu.edu.cn/teacher/536",
    )

    assert [publication.clean_title for publication in publications] == [
        "Rigidity of mean curvature flows in hyperbolic space",
        "Spectral gaps for nonlinear Schrodinger operators",
    ]
    assert "Proc. Amer. Math. Soc." in (publications[0].venue_text or "")
    assert "Proc. Amer. Math. Soc." not in (publications[0].authors_text or "")


def test_sysu_seed42_sofe_title_first_entries_skip_application_numbers():
    html = """
    <html><body>
      <div class="field-name-field-publications">
        <div class="field-label">Selected Publications</div>
        <div class="field-items">
          <p>Measuring systemic financial risk with high-dimensional networks.
          Journal of Econometrics, 2024.</p>
          <p>Green innovation spillovers and financing constraints. Journal of
          Corporate Finance, 2023.</p>
          <p>Patent application No. CN202411111111.1, dynamic risk warning
          system.</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://sofe.sysu.edu.cn/zh-hans/teacher/81",
    )

    assert [publication.clean_title for publication in publications] == [
        "Measuring systemic financial risk with high-dimensional networks",
        "Green innovation spillovers and financing constraints",
    ]
    assert all("application" not in publication.raw_title.lower() for publication in publications)
