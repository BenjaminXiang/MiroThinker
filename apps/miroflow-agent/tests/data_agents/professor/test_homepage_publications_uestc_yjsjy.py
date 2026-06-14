from __future__ import annotations

from src.data_agents.professor.homepage_publications import (
    extract_publications_from_html,
)


def test_uestc_yjsjy_long_title_first_doi_list_splits_and_keeps_doi_anchors():
    html = """
    <html><body>
      <table><tbody>
        <tr><td><b>研究成果：</b></td></tr>
        <tr><td>
          1. Trustworthy multimodal perception for autonomous industrial robots.
          DOI: <a href="https://doi.org/10.1109/TNNLS.2024.1234567">
          10.1109/TNNLS.2024.1234567</a>
          2 Lightweight visual localization for Shenzhen campus service robots.
          DOI: <a href="https://doi.org/10.1016/j.robot.2023.104634">
          10.1016/j.robot.2023.104634</a>
          3 Cross-domain secure sensing for industrial Internet of Things.
          DOI: 10.1145/2022.3600001
        </td></tr>
        <tr><td><b>专业研究方向：</b></td></tr>
        <tr><td>085400电子信息 08软件工程 硕士专业学位</td></tr>
      </tbody></table>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20492?yxsh=28",
    )

    assert [publication.clean_title for publication in publications] == [
        "Trustworthy multimodal perception for autonomous industrial robots",
        "Lightweight visual localization for Shenzhen campus service robots",
        "Cross-domain secure sensing for industrial Internet of Things",
    ]
    assert [publication.source_anchor for publication in publications] == [
        "https://doi.org/10.1109/TNNLS.2024.1234567",
        "https://doi.org/10.1016/j.robot.2023.104634",
        "https://doi.org/10.1145/2022.3600001",
    ]
    assert all("10." in publication.raw_title for publication in publications)


def test_uestc_yjsjy_seed26_mixed_comma_author_list_keeps_title_clean():
    html = """
    <html><body>
      <table><tbody>
        <tr><td><b>研究成果：</b></td></tr>
        <tr><td>
          <span id="lblFbwz">
            【7】 Yawen Ling, Jianpeng Chen, Yazhou Ren*, Xiaorong Pu, Jie Xu,
            Xiaofeng Zhu, Lifang He. Dual Label-Guided Graph Refinement for
            Multi-View Graph Clustering, [C]//Proceedings of the AAAI Conference
            on Artificial Intelligence. 2023, 37(7): 8791-8798. (CCF A 类会议)
            【8】 Xiaorong Pu, Yi Peng（共一）, Chen Kecheng*, Qima Zhao,
            Di Zhao, Yazhou Ren*, EEGDnet: Fusing Non-Local and Local
            Self-Similarity for 1-D EEG Signal Denoising with 2-D Transformer.
            Computers in Biology and Medicine CBM (SCI 2区)，151, 2022, 106248
            【9】 Zongmo Huang; Xiaorong Pu(共一); Gongshun Tang*; Ming Ping;
            Guo Jiang; Mengjie Wang; Xiaoyu Wei; Yazhou Ren*, BS-80K: The First
            Large Open-access Dataset of Bone Scan Images with Manifold
            Annotations，Computers in Biology and Medicine CBM (SCI 2区)，151,
            2022, 106221.
          </span>
        </td></tr>
        <tr><td><b>专业研究方向：</b></td></tr>
      </tbody></table>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10368?yxsh=28",
    )

    publication = next(
        publication
        for publication in publications
        if "EEGDnet" in publication.raw_title
    )
    assert publication.clean_title == (
        "EEGDnet: Fusing Non-Local and Local Self-Similarity for 1-D EEG Signal "
        "Denoising with 2-D Transformer"
    )
    assert publication.authors_text == (
        "Xiaorong Pu, Yi Peng, Chen Kecheng, Qima Zhao, Di Zhao, Yazhou Ren"
    )
    assert publication.venue_text == (
        "Computers in Biology and Medicine CBM (SCI 2区)，151, 2022, 106248"
    )


def test_uestc_yjsjy_star_bulleted_representative_papers_split_without_profile_prose():
    html = """
    <html><body>
      <table><tbody>
        <tr><td><b>研究成果：</b></td></tr>
        <tr><td>
          <span id="lblFbwz">
            代表性论文：
            ★ 张明，李华，王强*，面向智能制造的多源数据融合方法，
            计算机集成制造系统，2024，30(2)：101-112。
            ★ Liu Wei, Chen Kai, Zhang Ming*, Robust Scheduling for
            Industrial Digital Twin Systems, IEEE Transactions on
            Industrial Informatics, 2023, 19(8): 8123-8134.
            发表论文十余篇。
          </span>
        </td></tr>
        <tr><td><b>专业研究方向：</b></td></tr>
      </tbody></table>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10001?yxsh=28",
    )

    assert [publication.clean_title for publication in publications] == [
        "面向智能制造的多源数据融合方法",
        "Robust Scheduling for Industrial Digital Twin Systems",
    ]
    assert all("发表论文十余篇" not in publication.raw_title for publication in publications)


def test_uestc_yjsjy_aggregate_publication_count_only_does_not_fabricate_publication():
    html = """
    <html><body>
      <table><tbody>
        <tr><td><b>研究成果：</b></td></tr>
        <tr><td><span id="lblFbwz">发表论文十余篇。</span></td></tr>
        <tr><td><b>专业研究方向：</b></td></tr>
      </tbody></table>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10002?yxsh=28",
    )

    assert publications == []


def test_sztu_typical_paper_semicolon_quoted_entries_split_without_thesis_prose():
    html = """
    <html><body>
      <div class="teacher-info">
        <p>Typical paper:
        发表论文《Affective Product Design for Aging Communities》发表于
        《Design Studies》2024；
        《Collaborative Service Design in Urban Renewal》发表于
        《Packaging Engineering》2023；
        硕士论文《服务设计教学改革研究》。</p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://design.sztu.edu.cn/info/seed47",
    )

    assert [publication.clean_title for publication in publications] == [
        "Affective Product Design for Aging Communities",
        "Collaborative Service Design in Urban Renewal",
    ]
    assert all("硕士论文" not in publication.raw_title for publication in publications)
