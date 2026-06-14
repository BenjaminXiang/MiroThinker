from __future__ import annotations

from src.data_agents.professor.homepage_publications import (
    extract_publications_with_diagnostics_from_html,
)


def test_cuhk_myweb_toplist_nav_uses_publications_pane_and_splits_letter_number_items():
    html = """
    <html><body>
      <div class="basic-cell">
        <div class="toplist">Biography</div>
        <div class="toplist">Research</div>
        <div class="toplist">Awards</div>
        <div class="toplist">Publications</div>
        <div class="AcademicPublications">
          <div id="Publications" class="tab-content in">
            <div class="tab-pane teams active">
              <p>
                B1. Graph Signal Processing for Machine Intelligence.
                Springer, 2024.<br/>
                B2. Low Rank Modeling for Robust Machine Learning.
                Foundations and Trends in Signal Processing, 2023.<br/>
                Journal Publications<br/>
                J1. Xiangrong Wang, Lei Zhang. Adaptive graph neural networks
                for image understanding. IEEE Transactions on Pattern Analysis
                and Machine Intelligence, 2024.<br/>
                J2. Xiangrong Wang, Ming Li. Sparse tensor methods for remote
                sensing. IEEE Transactions on Geoscience and Remote Sensing,
                2023.<br/>
                Conference Publications<br/>
                C1. Xiangrong Wang, Jian Chen. Reliable representation learning
                for graph data. IEEE Conference on Computer Vision and Pattern
                Recognition, 2022.
              </p>
            </div>
          </div>
        </div>
      </div>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://myweb.cuhk.edu.cn/wangxiangrong",
    )

    assert result.sections_detected == 1
    assert [publication.clean_title for publication in result.publications] == [
        "Graph Signal Processing for Machine Intelligence",
        "Low Rank Modeling for Robust Machine Learning",
        "Adaptive graph neural networks for image understanding",
        "Sparse tensor methods for remote sensing",
        "Reliable representation learning for graph data",
    ]


def test_cuhk_myweb_repairs_glyph_pollution_and_filters_titleless_fragments():
    html = r"""
    <html><body>
      <div class="AcademicPublications">
        <div id="Publications" class="tab-content in">
          <div class="tab-pane teams active">
            <p>J1. \Highly e_cient _eld-free control of domain wall motion in
              ferrimagnetic films. Nature Materials, 2024.</p>
            <p>Book chapters</p>
            <p>J2. IEEE Transactions on Information Theory, vol. 67, no. 8,
              pp. 5212-5224</p>
            <p>J3. Sparse_matrix factorization for graph signal processing.
              IEEE Transactions on Signal Processing, 2023.</p>
          </div>
        </div>
      </div>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://myweb.cuhk.edu.cn/example",
    )

    assert [publication.clean_title for publication in result.publications] == [
        "Highly efficient field-free control of domain wall motion in ferrimagnetic films",
        "Sparse_matrix factorization for graph signal processing",
    ]
