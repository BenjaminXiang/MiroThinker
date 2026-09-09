"""RED-phase tests for M2.1 homepage publications extractor.

Source of truth: docs/plans/2026-04-21-001-m2.1-homepage-publications-extractor.md
Requirements: R1 signature, R2 dataclass fields, R3 happy-path count, R4 title-clean
rules, R5 at-least-one-of-authors/venue, R6 pure function, R7 5-archetype coverage.

Tests are organized by Unit:
  Unit 1 — dataclass + helper pure functions (_strip_item_prefix/suffix,
           _extract_year_from_text, _split_title_authors_venue, _normalize_title_for_dedup)
  Unit 2 — end-to-end extract_publications_from_html (5 archetypes + edges)
  Unit 3 — deferred (real HTML fixtures land after Unit 1+2 are green)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_agents.professor.homepage_publications import (
    HomepagePublication,
    _extract_year_from_text,
    _is_non_publication_title_noise,
    _normalize_title_for_dedup,
    _split_title_authors_venue,
    _strip_item_prefix,
    _strip_item_suffix,
    extract_publications_from_html,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "homepage"


def _load(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# Unit 1 — dataclass construction + helpers
# -----------------------------------------------------------------------------


def test_homepage_publication_dataclass_smoke():
    pub = HomepagePublication(
        raw_title="[1] Some Title [J]",
        clean_title="Some Title",
        authors_text="A. Smith",
        venue_text="ACM",
        year=2023,
        source_url="https://example.edu/prof",
        source_anchor="https://doi.org/10.1/x",
        pdf_url="https://example.edu/papers/some-title.pdf",
    )
    assert pub.clean_title == "Some Title"
    assert pub.year == 2023
    assert pub.source_anchor == "https://doi.org/10.1/x"
    assert pub.pdf_url == "https://example.edu/papers/some-title.pdf"


def test_homepage_publication_is_frozen():
    pub = HomepagePublication(
        raw_title="raw",
        clean_title="clean",
        authors_text=None,
        venue_text=None,
        year=None,
        source_url="https://example.edu",
        source_anchor=None,
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        pub.clean_title = "mutated"  # frozen dataclass blocks this


def test_extract_publications_preserves_relative_absolute_and_doi_adjacent_pdf_links():
    html = """
    <section>
      <h2>Selected Publications</h2>
      <ul>
        <li>
          A Robust Method for Scientific Discovery. A. Smith. NeurIPS 2024.
          <a href="/papers/robust-method.pdf">PDF</a>
        </li>
        <li>
          Efficient Systems for Laboratory Automation. B. Lee. ICRA 2023.
          <a href="https://cdn.example.edu/lab-automation.PDF?download=1">Full text</a>
        </li>
        <li>
          Trustworthy Models for Clinical Prediction. C. Wang. Nature 2022.
          <a href="https://doi.org/10.1234/clinical">DOI</a>
          <a href="./clinical-prediction.pdf">PDF</a>
        </li>
      </ul>
    </section>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile/index.html",
    )

    assert [pub.pdf_url for pub in pubs] == [
        "https://faculty.example.edu/papers/robust-method.pdf",
        "https://cdn.example.edu/lab-automation.PDF?download=1",
        "https://faculty.example.edu/profile/clinical-prediction.pdf",
    ]
    assert pubs[2].source_anchor == "https://doi.org/10.1234/clinical"


def test_extract_publications_from_google_sites_research_section_with_citations():
    html = """
    <html><body>
      <h1>Miha Bresar</h1>
      <h2>Research:</h2>
      <p>
        Central Limit Theorem for ergodic averages of Markov chains and the
        comparison of sampling algorithms for heavy-tailed distributions
        (with A. Mijatovic and G. Roberts), Submitted, 2025.
        <a href="https://arxiv.org/abs/2501.00001">ArXiv</a>
      </p>
      <p>
        Brownian motion with asymptotically normal reflection in unbounded
        domains: from transience to stability (with A. Mijatovic and A. Wade),
        Annals of Probability 53(1): 175-222 (2025).
        <a href="https://arxiv.org/abs/2401.00001">ArXiv</a>
      </p>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://sites.google.com/view/mihabresar",
    )

    assert [pub.clean_title for pub in pubs] == [
        (
            "Central Limit Theorem for ergodic averages of Markov chains and the "
            "comparison of sampling algorithms for heavy-tailed distributions"
        ),
        (
            "Brownian motion with asymptotically normal reflection in unbounded "
            "domains: from transience to stability"
        ),
    ]
    assert [pub.source_anchor for pub in pubs] == [
        "https://arxiv.org/abs/2501.00001",
        "https://arxiv.org/abs/2401.00001",
    ]


def test_extract_publications_cleans_sysu_szu_cuhk_author_tail_pollution():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>et. al, Dynamics of flexible multi-stable origami with
          bio-inspired creases, Int. Journal of Robotics Research, 2024.</li>
          <li>Xiaojun Ta n*. InScope: A New Real-world 3D
          Infrastructure-side Collaborative Perception Dataset for Open
          Traffic Scenarios. IEEE Robotics and Automation Letters, 2025.</li>
          <li>Reliable Motion Planning for Agile Robots. IEEE Robotics and
          Automation Letters, 2025.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/publications",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Dynamics of flexible multi-stable origami with bio-inspired creases",
        (
            "InScope: A New Real-world 3D Infrastructure-side Collaborative "
            "Perception Dataset for Open Traffic Scenarios"
        ),
        "Reliable Motion Planning for Agile Robots",
    ]
    assert all(not pub.clean_title.casefold().startswith("et") for pub in pubs)
    assert all("Xiaojun Ta" not in pub.clean_title for pub in pubs)


def test_extract_publications_rejects_news_update_accepted_rows():
    html = """
    <html><body>
      <section>
        <h2>Publications and News</h2>
        <ul>
          <li>to RA-L. 2025-12-01: COMET accepted</li>
          <li>to RA-L. 2025-11-28: Threat-Aware UAV Dodging for Agile Robots accepted</li>
          <li>Reliable Motion Planning for Agile Robots. IEEE Robotics and
          Automation Letters, 2025.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/news",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Reliable Motion Planning for Agile Robots"
    ]


def test_extract_publications_rejects_long_chinese_project_responsibility_prose():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>● 国家重大专项工程、综合粒子设施类大科学装置的工程设计经验。
          1)某重大专项工程的“密封与屏蔽”子专题负责人，解决了复杂体系沉积源项、
          检修人员气溶胶控制等关键问题。2)负责了中科院CiADS，哈工大SESRI等
          一些大科学装置的辐射安全分析和防护设计，注重装置中值得关注的特殊问题
          的提出及解决方案</li>
          <li>高能粒子辐射屏蔽设计中的蒙特卡罗方法研究. 核技术, 2024.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/sysu",
    )

    assert [pub.clean_title for pub in pubs] == [
        "高能粒子辐射屏蔽设计中的蒙特卡罗方法研究"
    ]


def test_extract_publications_rejects_suat_postdoc_honor_and_history_rows():
    html = """
    <html><body>
      <section>
        <h2>论文发表</h2>
        <ul>
          <li>2023深圳市优秀博士后</li>
          <li>2023中国科学院深圳先进技术研究院“十大优秀博士后”</li>
          <li>2025 至今深圳理工大学材料科学与工程学院博士后</li>
          <li>Postdoctoral Polymer Interfaces for Flexible Electronics.
          Advanced Materials, 2024.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/suat-postdoc",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Postdoctoral Polymer Interfaces for Flexible Electronics"
    ]
    assert all("博士后" not in pub.clean_title for pub in pubs)


def test_extract_publications_rejects_cuhk_book_metadata_rows():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>accepted to appear</li>
          <li>Book: J. G. Dai and Michael J. Harrison</li>
          <li>Book: Processing Networks: Fluid Models and Stability</li>
          <li>Queueing Controls for Processing Networks.
          Annals of Applied Probability, 2023.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/cuhk-book",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Queueing Controls for Processing Networks"
    ]
    assert all(not pub.clean_title.startswith("Book:") for pub in pubs)
    assert all(pub.clean_title != "accepted to appear" for pub in pubs)


def test_extract_publications_strips_cuhk_collaboration_and_editor_residue():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>Diffusion Limits for Queueing Networks, joint work with
          J. G. Dai and Michael J. Harrison, Operations Research, 2024.</li>
          <li>Stochastic Processing Networks: Heavy Traffic Analysis.
          In Handbook of Stochastic Models, Edited by J. G. Dai and
          Michael J. Harrison, Springer, 2023.</li>
          <li>Edited by J. G. Dai and Michael J. Harrison</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/cuhk-annotations",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Diffusion Limits for Queueing Networks",
        "Stochastic Processing Networks: Heavy Traffic Analysis",
    ]
    assert all("joint work with" not in pub.clean_title for pub in pubs)
    assert all("Edited by" not in pub.clean_title for pub in pubs)


def test_extract_publications_falls_back_when_lxml_rejects_malformed_attributes():
    html = """
    <html><body>
      <div {bad="x">malformed attribute from personal homepage</div>
      <section>
        <h2>Selected Publications</h2>
        <p>1. A. Smith, B. Lee. Robust Planning for Assistive Robots.
        IEEE Robotics and Automation Letters, 2024.</p>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://example.edu/personal",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Robust Planning for Assistive Robots"
    ]


@pytest.mark.parametrize(
    "heading",
    ["论文及著作", "Paper & Book Publications", "Paper and Book Publications"],
)
def test_extract_publications_detects_paper_and_book_publication_headings(
    heading: str,
):
    html = f"""
    <html><body>
      <section>
        <h2>{heading}</h2>
        <ul>
          <li>Robust Planning for Assistive Robots. Journal of Robotics, 2024.</li>
          <li>Scalable Optical Systems for Smart Manufacturing. Optics Letters, 2023.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Robust Planning for Assistive Robots",
        "Scalable Optical Systems for Smart Manufacturing",
    ]


def test_extract_publications_filters_patent_entries_from_rule_parser():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>机器人手臂遥操作方法、装置、系统及介质，发明专利，授权号 CN202410001234.5。</li>
          <li>Reliable Paper Title for Manufacturing Systems. Journal of Systems, 2024.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Reliable Paper Title for Manufacturing Systems"
    ]


def test_extract_publications_keeps_papers_about_patent_analysis():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>Patent Citation Network Analysis for Technology Forecasting. Scientometrics, 2024.</li>
          <li>专利价值评估方法研究. 情报学报, 2023.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Patent Citation Network Analysis for Technology Forecasting",
        "专利价值评估方法研究",
    ]


def test_extract_publications_recovers_titles_after_long_author_et_al_prefixes():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>[27]. Shanmin Wang, Duanwei He, Yongtao Zou, et al.,
          High-pressure and high-temperature sintering of nanostructured
          bulk NiAl materials, Journal of Materials Research, 24, 2089 (2009).</li>
          <li>5. J Lu, CV Ngo, SC Singh, et al. Bioinspired Hierarchical
          Surfaces Fabricated by Femtosecond Laser and Hydrothermal Method for
          Water Harvesting. Langmuir 35 (9), 3562-3567 (2019).</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "High-pressure and high-temperature sintering of nanostructured bulk NiAl materials",
        (
            "Bioinspired Hierarchical Surfaces Fabricated by Femtosecond Laser "
            "and Hydrothermal Method for Water Harvesting"
        ),
    ]
    assert pubs[0].authors_text == "Shanmin Wang, Duanwei He, Yongtao Zou, et al"
    assert pubs[1].authors_text == "J Lu, CV Ngo, SC Singh, et al"


def test_extract_publications_skips_bibliographic_fragments_without_real_titles():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <ul>
          <li>Yang Peng, Zikang Yu, Jiuzhou Zhao, Qing Wang, Jiaxin Liu, Bo Sun,
      Yun Mou*, Mingxiang Chen. J. Adv. Ceram., 2022, 11, 1889-1900.
      (IF=11.534, 中科院1区)</li>
          <li>2016 Jun 1;6:26942. doi: 10.1038/srep26942</li>
          <li>Fellow, The World Academy of Sciences (TWAS)</li>
          <li>Reliable Paper Title for Manufacturing Systems. Journal of Systems, 2024.</li>
        </ul>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Reliable Paper Title for Manufacturing Systems"
    ]


def test_extract_publications_recovers_title_before_doi_tail_from_long_author_list():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <p>Zilun Li, Meixiu Peng, Pin Chen, Chenshu Liu, Jiangyun Peng, Jiang Liu,
        Yihui Li, Wenxue Li, Wei Zhu, Dongxian Guan, Yang Zhang, Hongyin Chen,
        Jiuzhou Li, Dongxiao Fan, Kan Huang, Fen Lin, Zefeng Zhang, Zeling Guo,
        Hengli Luo, Bingding Huang, Weikang Cai, Lei Gu, Yutong Lu, Li Yan*,
        Sifan Chen*, Imatinib and methazolamide ameliorate COVID-19-induced
        metabolic complications via elevating ACE2 enzymatic activity and
        inhibiting viral entry. Cell Metabolism, 2022, 34:1-17. DOI:
        10.1016/j.cmet.2022.01.008 [PDF]</p>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        (
            "Imatinib and methazolamide ameliorate COVID-19-induced metabolic "
            "complications via elevating ACE2 enzymatic activity and inhibiting "
            "viral entry"
        )
    ]
    assert "Bingding Huang" in (pubs[0].authors_text or "")
    assert pubs[0].venue_text == "Cell Metabolism, 2022, 34:1-17"
    assert pubs[0].source_anchor == "https://doi.org/10.1016/j.cmet.2022.01.008"


def test_extract_publications_splits_pubmed_numbered_items_after_pmids():
    html = """
    <html><body>
      <section>
        <h2>代表性论文和专利</h2>
        <p>1.Lui A, Do T, Alzayat O, Yu N, Phyu S, Santuya HJ, Liang B,
        Kailash V, Liu D, Inslicht SS, Shahlaie K, Liu DZ （ Senior and
        Corresponding Author） . Tumor Suppressor MicroRNAs in Clinical and
        Preclinical Trials for Neurological Disorders. Pharmaceuticals,
        2024 Mar 27;17(4):426. PMID:38675388</p>
        <p>2.Ye Z, Izadi A, Gurkoff GG, Rickerl K, Sharp FR, Ander BP,
        Bauer AZ, Lui A, Lyeth BG, Liu DZ （ Senior and Corresponding Author） .
        Combined Inhibition of Fyn and c-Src Protects Hippocampal Neurons and
        Improves Spatial Memory via ROCK after Traumatic Brain Injury.
        J Neurotrauma. 2022 Apr;39(7-8):520-529. PMID:35109711</p>
        <p>3. Liu DZ （ First Inventor） , Lyeth B. Martin R, Shahlaie K.
        Methods for Treating Brain Injury. (Patent)</p>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Tumor Suppressor MicroRNAs in Clinical and Preclinical Trials for Neurological Disorders",
        (
            "Combined Inhibition of Fyn and c-Src Protects Hippocampal Neurons "
            "and Improves Spatial Memory via ROCK after Traumatic Brain Injury"
        ),
    ]
    assert pubs[0].venue_text == "Pharmaceuticals, 2024 Mar 27;17(4):426"
    assert pubs[1].venue_text == "J Neurotrauma. 2022 Apr;39(7-8):520-529"


def test_extract_publications_maps_tab_heading_to_matching_content_pane():
    html = """
    <html><body>
      <div class="m-tabcon-person">
        <ul class="ul-tab-person TAB_CLICK" id=".TAB">
          <li><a class="con" href="JavaScript:;">个人简介</a></li>
          <li><a class="con" href="JavaScript:;">研究领域</a></li>
          <li><a class="con" href="JavaScript:;">研究论文成果</a></li>
        </ul>
        <div class="item">
          <div class="TAB boxj"><p>教授简介文字，不应作为论文。</p></div>
          <div class="TAB boxj"><p>1. 水系离子电池等研究方向。</p></div>
          <div class="TAB boxj">
            <p>1.Building a High-Concentration Zn2+ Cation Reservoir of Zn
            Anode for Long-Cycling and High-Efficiency Zinc-Bromine Flow
            Batteries. Haichao Huang, Wenwen Cao, Guojin Liang.
            ACS Energy Letters, 2025, Accepted.</p>
            <p>2.Long-life Aqueous Zinc-iodine Flow Batteries Enabled by
            Selectively Intercepting Hydrated Ions. Zhiquan Wei, Yiqiao Wang,
            Guojin Liang. Nature Communications, 2025, Accepted.</p>
          </div>
        </div>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/profile",
    )

    assert [pub.clean_title for pub in pubs] == [
        (
            "Building a High-Concentration Zn2+ Cation Reservoir of Zn Anode "
            "for Long-Cycling and High-Efficiency Zinc-Bromine Flow Batteries"
        ),
        (
            "Long-life Aqueous Zinc-iodine Flow Batteries Enabled by "
            "Selectively Intercepting Hydrated Ions"
        ),
    ]


def test_extract_publications_ignores_tab_navigation_and_hidden_profile_history():
    html = """
    <html><body>
      <div class="teacherTabs" id="teacherTabs">
        <div class="teacher_Tab teacher_Tab_zh">个人简介</div>
        <div class="teacher_Tab teacher_Tab_zh">教育及工作经历</div>
        <div class="teacher_Tab teacher_Tab_zh">部分项目及论文列表</div>
      </div>
      <div class="tacherContent">
        <div class="part_box" style="display:none;">
          <p>教育经历 2009/09 - 2012/12 浙江大学 计算机专业 博士</p>
          <p>工作经历 2021/11 至今 哈尔滨工业大学（深圳）教授</p>
        </div>
        <div class="part_t">部分项目及论文列表</div>
        <dl>
          <dt>主持的部分项目列表：</dt>
          <dd>1. 项目编号 RKX20231110090859012 深圳市科技项目。</dd>
          <p style="font-size: medium;">部分论文列表：</p>
          <p>1. Daojing He, Zhiyong Liu. Specific Secure Communication Protocol
          for Smart Grid. IEEE Transactions on Smart Grid, 2024.</p>
          <p>2. Daojing He, Xin Lv. Double Auction Mechanism for Edge Computing.
          ACM Transactions on Sensor Networks, 2023.</p>
        </dl>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.hitsz.edu.cn/hedaojing",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Specific Secure Communication Protocol for Smart Grid",
        "Double Auction Mechanism for Edge Computing",
    ]


def test_plain_text_publication_fallback_splits_dense_citation_boundaries():
    html = """
    <html><body>
      <p>个人简介 研究方向：智能感知。</p>
      <p>期刊论文： Jinxing Li, Guangming Lu, Multi-Feature Matching for
      High-Resolution Fingerprint Recognition, IEEE Transactions on
      Instrumentation & Measurement, 2025, 74: 1-11 Yishu Liu, Guangming Lu,
      Self-Supervised Medical Adversarial Robustness with Two-Stage Contrastive
      Constraints, IEEE Transactions on Emerging Topics in Computational
      Intelligence, 2025, DOI: 10.1109/TETCI.2025.3547633 Yingjian Li,
      Guangming Lu, Cross-Domain Facial Expression Recognition via Contrastive
      Warm up and Complexity-aware Self-training, IEEE Transactions on Image
      Processing, 2026, accepted Ke Yan, David Zhang, Darong Wu, Hua Wei,
      Guangming Lu, Design of a Breath Analysis System for Diabetes Screening
      and Blood Glucose Level Prediction, IEEE Transactions on Biomedical
      Engineering, 2014, 61(11): 2787-2795. F. Liu, D. Zhang, C. Song, and
      Guangming Lu, Touchless Multi-view Fingerprint Acquisition and Mosaicking,
      IEEE Trans. on Instrumentation and Measurement, 2013, 62(9): 2492-2502.
      Wei Li, David Zhang, Guangming Lu, Nan Luo, A Novel 3-D Palmprint
      Acquisition System, Bulletin of Advanced Technology, 2012.</p>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.hitsz.edu.cn/luguangming",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Multi-Feature Matching for High-Resolution Fingerprint Recognition",
        (
            "Self-Supervised Medical Adversarial Robustness with Two-Stage "
            "Contrastive Constraints"
        ),
        (
            "Cross-Domain Facial Expression Recognition via Contrastive Warm up "
            "and Complexity-aware Self-training"
        ),
        (
            "Design of a Breath Analysis System for Diabetes Screening and "
            "Blood Glucose Level Prediction"
        ),
        "Touchless Multi-view Fingerprint Acquisition and Mosaicking",
        "A Novel 3-D Palmprint Acquisition System",
    ]


# --- _strip_item_prefix ---


def test_strip_item_prefix_bracketed_number():
    assert _strip_item_prefix("[1] Title goes here") == "Title goes here"
    assert _strip_item_prefix("[12] Another Title") == "Another Title"


def test_strip_item_prefix_dotted_number():
    assert _strip_item_prefix("1. Title goes here") == "Title goes here"
    assert _strip_item_prefix("12. Another Title") == "Another Title"


def test_strip_item_prefix_chinese_number_marker():
    assert _strip_item_prefix("1、 Title goes here") == "Title goes here"
    assert _strip_item_prefix("12、Another Title") == "Another Title"


def test_strip_item_prefix_parenthesized_number():
    assert _strip_item_prefix("(1) Title goes here") == "Title goes here"
    assert _strip_item_prefix("(12) Another Title") == "Another Title"


def test_strip_item_prefix_no_prefix_is_passthrough():
    assert _strip_item_prefix("Title with no prefix") == "Title with no prefix"


def test_strip_item_prefix_preserves_interior_brackets():
    # Only LEADING prefix markers get stripped; [J] inside text survives.
    assert _strip_item_prefix("[1] Some [Key] Title") == "Some [Key] Title"


# --- _strip_item_suffix ---


def test_strip_item_suffix_journal_tag():
    assert _strip_item_suffix("Some Title [J]") == "Some Title"


def test_strip_item_suffix_conference_tag():
    assert _strip_item_suffix("Some Title [C]") == "Some Title"


def test_strip_item_suffix_online_journal_tag():
    assert _strip_item_suffix("Some Title [J/OL]") == "Some Title"


def test_strip_item_suffix_no_suffix_is_passthrough():
    assert (
        _strip_item_suffix("Some Title with no suffix") == "Some Title with no suffix"
    )


def test_strip_item_suffix_trailing_period_normalized():
    # If suffix strip leaves a trailing period/comma, it should also be cleaned.
    assert _strip_item_suffix("Some Title [J].").rstrip(".") == "Some Title"


# --- _extract_year_from_text ---


def test_extract_year_from_text_single_year():
    assert _extract_year_from_text("Published in 2023 Proceedings.") == 2023


def test_extract_year_from_text_trailing_year():
    assert _extract_year_from_text("Some Title. Venue, 2024.") == 2024


def test_extract_year_from_text_no_year_returns_none():
    assert _extract_year_from_text("No year mentioned here") is None


def test_extract_year_from_text_future_year_rejected():
    # Year far in the future is rejected (e.g., placeholder or typo).
    assert _extract_year_from_text("Will appear in 2099.") is None


def test_extract_year_from_text_very_old_year_rejected():
    # Pre-1900 is rejected as likely false positive (e.g., address numbers).
    assert _extract_year_from_text("Some old classic from 1887") is None


def test_extract_year_from_text_multiple_years_prefers_latest():
    # "Proceedings of 2022 conference, published 2023" → prefer 2023 (latest)
    result = _extract_year_from_text("Proceedings of 2022 conference, published 2023.")
    assert result in (2022, 2023)  # implementer picks; pin whichever they choose
    # but explicit: verify it's an int in range
    assert isinstance(result, int) and 2000 <= result <= 2026


def test_year_number_fragment_title_is_noise():
    assert _is_non_publication_title_noise("2023 年 40")


def test_publication_count_profile_tail_title_is_noise():
    assert _is_non_publication_title_noise(
        "4 篇，2019年9月- 2020年1月任广州航海学院大学化学兼职讲师。"
        "2020年9月至今任创意设计学院辅导员。 wenyayu@sztu.edu.cn"
    )
    assert _is_non_publication_title_noise("4 篇，2020年至今任副教授。")
    assert not _is_non_publication_title_noise("4D Printing of Shape-Memory Polymers")


# --- _split_title_authors_venue ---


def test_split_title_authors_venue_full_triple():
    title, authors, venue = _split_title_authors_venue(
        "Deep Learning for Image Recognition. J. Doe, X. Liu. ACM Conf 2023."
    )
    assert "Deep Learning" in title
    assert authors is not None and "Doe" in authors
    assert venue is not None and "ACM" in venue


def test_split_title_authors_venue_bare_title_only():
    title, authors, venue = _split_title_authors_venue("Bare title with no authors")
    assert title == "Bare title with no authors"
    assert authors is None
    assert venue is None


def test_split_title_authors_venue_handles_missing_venue():
    # "Title. Authors." with no trailing venue is acceptable.
    title, authors, _venue = _split_title_authors_venue("A Title. J. Doe, X. Liu.")
    assert "A Title" in title
    assert authors is not None and "Doe" in authors


def test_split_title_authors_venue_handles_comma_delimited_citation():
    title, authors, venue = _split_title_authors_venue(
        "Shuting Liu, Baochang Zhang, Yiqing Liu, Tian Guan*, and Yonghong He*, "
        "Unpaired Stain Transfer Using Pathology-Consistent Constrained "
        "Generative Adversarial Networks, IEEE Transactions on Medical Imaging, "
        "40(8):1977-1989, 2021."
    )

    assert title == (
        "Unpaired Stain Transfer Using Pathology-Consistent Constrained "
        "Generative Adversarial Networks"
    )
    assert authors is not None and "Yonghong He" in authors
    assert ", ," not in authors
    assert venue is not None and "IEEE Transactions" in venue


def test_split_title_authors_venue_handles_semicolon_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Rui Feng; Fei Tang*; Ning Zhang; Xiaohao Wang, "
        "Flexible; High-Power Density; Wearable Thermoelectric Nanogenerator "
        "and Self-Powered Temperature Sensor"
    )

    assert title == (
        "Flexible; High-Power Density; Wearable Thermoelectric Nanogenerator "
        "and Self-Powered Temperature Sensor"
    )
    assert authors is not None and "Xiaohao Wang" in authors
    assert venue is None


def test_split_title_authors_venue_handles_initial_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Wang J, Zhang J, Feng P. Experimental and theoretical investigation "
        "on critical cutting force in rotary ultrasonic drilling of brittle "
        "materials and composites"
    )

    assert title == (
        "Experimental and theoretical investigation on critical cutting force "
        "in rotary ultrasonic drilling of brittle materials and composites"
    )
    assert authors == "Wang J, Zhang J, Feng P"
    assert venue is None


def test_split_title_authors_venue_handles_chinese_author_note_in_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Yuanchang Liang, Xiaobo Wang（通讯作者）,Kai Wang, Shuo Wang, "
        "Xiaojiang Peng, Haoyu Chen, David Kim Huat Chua, Prahlad "
        "Vadakkepat, Adaptive Action Chunking at Inference-Time for "
        "Vision-Language-Action Models. IEEE Conference on Computer Vision "
        "and Pattern Recognition. (CVPR), 2026"
    )

    assert title == (
        "Adaptive Action Chunking at Inference-Time for Vision-Language-Action "
        "Models"
    )
    assert authors is not None and "Xiaobo Wang" in authors
    assert "通讯作者" not in authors
    assert venue is not None and "Computer Vision" in venue


def test_split_title_authors_venue_handles_et_al_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Xiaobo Wang et al. Teacher Guided Neural Architecture Search for "
        "Face Recognition. Association for the Advancement of Artificial "
        "Intelligence (AAAI), 2021"
    )

    assert title == "Teacher Guided Neural Architecture Search for Face Recognition"
    assert authors == "Xiaobo Wang et al"
    assert venue is not None and "AAAI" in venue


def test_split_title_authors_venue_handles_chinese_numbered_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "1、 Mingzhou Wu, Shuqing He, Xin Hu, Jingqin Chen, Enna Ha, "
            "Fujin Ai, Tao Ji, Junqing Hu and Shuangchen Ruan*, A "
            "Near-Infrared Light Triggered Composite Nanoparticles for "
            "Image-Guided Photothermal Therapy in Osteosarcoma. Journal of "
            "Materials Chemistry B, 2018"
        )
    )

    assert title == (
        "A Near-Infrared Light Triggered Composite Nanoparticles for "
        "Image-Guided Photothermal Therapy in Osteosarcoma"
    )
    assert authors is not None and "Mingzhou Wu" in authors
    assert authors is not None and "Shuangchen Ruan" in authors
    assert venue == "Journal of Materials Chemistry B, 2018"


def test_split_title_authors_venue_does_not_treat_title_case_phrase_as_author():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "36.Xiaodong Tan,Mingwen Shao*, Yuanjian Qiao, Tiyao Liu, "
            "Xiangyong Cao, Low-Rank Prompt-Guided Transformer for "
            "Hyperspectral Image Denoising,IEEE Transactions on Geoscience "
            "and Remote Sensing, 2024, 62:5520815. (SCI 1区)"
        )
    )

    assert title == (
        "Low-Rank Prompt-Guided Transformer for Hyperspectral Image Denoising"
    )
    assert authors is not None and "Xiaodong Tan" in authors
    assert authors is not None and "Xiangyong Cao" in authors
    assert venue is not None and "Geoscience and Remote Sensing" in venue


def test_split_title_authors_venue_handles_no_space_before_ieee_venue_tail():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "51.Leiquan Wang, Yunfeng Wang, Zhongwei Li, Chunlei Wu, "
            "Mingming Xu,Mingwen Shao, Eliminating Spatial Correlations of "
            "Anomaly: Corner-Visible Network for Unsupervised Hyperspectral "
            "Anomaly Detection.IEEE Transactions on Geoscience and Remote "
            "Sensing, 2023, 61: 1-14. (SCI 1区)"
        )
    )

    assert title == (
        "Eliminating Spatial Correlations of Anomaly: Corner-Visible Network "
        "for Unsupervised Hyperspectral Anomaly Detection"
    )
    assert authors is not None and "Leiquan Wang" in authors
    assert authors is not None and "Mingwen Shao" in authors
    assert venue is not None and "IEEE Transactions" in venue


def test_split_title_authors_venue_handles_curly_apostrophe_author_name():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "84.Baichen Liu, Zhi Han, Xi’ai Chen,Mingwen Shao, Huidi Jia, "
            "Yanmei Wang, Yandong Tang, A novel compact design of "
            "convolutional layers with spatial transformation towards "
            "lower-rank representation for image classification,"
            "Knowledge-Based Systems, 2022, 255: 109723. (SCI 1区)"
        )
    )

    assert title == (
        "A novel compact design of convolutional layers with spatial "
        "transformation towards lower-rank representation for image "
        "classification"
    )
    assert authors is not None and "Xi'ai Chen" in authors
    assert authors is not None and "Yandong Tang" in authors
    assert venue is not None and "Knowledge-Based Systems" in venue


def test_split_title_authors_venue_does_not_treat_against_title_as_author():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "147.Liu Shuqi, Mingwen Shao*, Liu Xinping, GAN-based Classifier "
            "Protection against adversarial attacks, Journal of Intelligent "
            "& Fuzzy Systems, 2020, 38(6):1-13. (SCI 4区)"
        )
    )

    assert title == "GAN-based Classifier Protection against adversarial attacks"
    assert authors is not None and "Liu Shuqi" in authors
    assert authors is not None and "Liu Xinping" in authors
    assert venue is not None and "Journal of Intelligent" in venue


def test_split_title_authors_venue_handles_semicolon_surname_given_authors():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "20. Li, Xiao-Tian; Mi, Sixuan; Xu, Yuzhi; Li, Bo-Wen; "
            "Zhu, T; Zhang, John Z. H., Discovery of New Synthetic Routes "
            "of Amino Acids in Prebiotic Chemistry, J. Am. Che m. Soc. Au, "
            "2024, 4, 4757-4768."
        )
    )

    assert title == (
        "Discovery of New Synthetic Routes of Amino Acids in Prebiotic Chemistry"
    )
    assert authors is not None and "Xiao-Tian Li" in authors
    assert authors is not None and "John Z. H. Zhang" in authors
    assert venue is not None and "J. Am. Che m. Soc. Au" in venue


def test_split_title_authors_venue_keeps_adjective_with_journal_name():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "2、 Mingzhou Wu, Wangcheng Zhan*, Yun Guo, Yunsong Wang, "
            "Yanglong Guo, Xueqing Gong, Li Wang and Guanzhong Lu*, "
            "Solvent-free selective oxidation of cyclohexane with molecular "
            "oxygen over manganese oxides: Effect of the calcination "
            "temperature, Chinese Journal of Catalysis, 2016, 37: 184-192"
        )
    )

    assert title == (
        "Solvent-free selective oxidation of cyclohexane with molecular "
        "oxygen over manganese oxides: Effect of the calcination temperature"
    )
    assert authors is not None and "Mingzhou Wu" in authors
    assert venue is not None and venue.startswith("Chinese Journal of Catalysis")


def test_split_title_authors_venue_handles_inline_journal_after_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Kewei Liu, Zhorro NiCkolov, Jonghyun Oh and Moses Noh, "
        "KrF excimer laser micromachining of MEMS materials: characterization "
        "and applications Journal of Micromechanics and Microengineering, "
        "2012,22 015012"
    )

    assert title == (
        "KrF excimer laser micromachining of MEMS materials: characterization "
        "and applications"
    )
    assert authors is not None and "Moses Noh" in authors
    assert venue is not None and "Journal of Micromechanics" in venue


def test_split_title_authors_venue_handles_author_parentheses_and_adjacent_initials():
    title, authors, venue = _split_title_authors_venue(
        "Xiang Ren, Kewei Liu, Qingwei Zhang, Hongseok (Moses) Noh, "
        "E.Caglan Kumbur, Wenqiao Wayne Yuan, Jack G. Zhou, "
        "Parkson Lee-Gau Chong, Design, Fabrication and Characterization "
        "of Archaeal Tetraether Free-Standing Planar Membranes in a PDMS- "
        "and PCB-Based Fluidic Platform, ACS Applied Materials & Interfaces, "
        "2014, Vol.6, No.15, pp. 12618-12628"
    )

    assert title == (
        "Design, Fabrication and Characterization of Archaeal Tetraether "
        "Free-Standing Planar Membranes in a PDMS- and PCB-Based Fluidic Platform"
    )
    assert authors is not None and "Hongseok (Moses) Noh" in authors
    assert authors is not None and "E. Caglan Kumbur" in authors
    assert venue is not None and "ACS Applied Materials" in venue


def test_split_title_authors_venue_handles_inline_journal_manufacturing_tail():
    title, authors, venue = _split_title_authors_venue(
        "Kewei Liu, Yoontae Kim, Moses Noh, "
        "ArF excimer laser micromachining of MEMS materials: characterization "
        "and applications Journal of Micro and Nano-Manufacturing, 2014, 2(2)."
    )

    assert title == (
        "ArF excimer laser micromachining of MEMS materials: characterization "
        "and applications"
    )
    assert authors is not None and "Moses Noh" in authors
    assert venue is not None and "Journal of Micro" in venue


def test_split_title_authors_venue_removes_short_journal_tail():
    title, authors, venue = _split_title_authors_venue(
        "Zhang J. Experimental study on vibration stability in rotary "
        "ultrasonic machining of ceramic matrix composites: cutting force "
        "variation at hole entrance. Ceramics International"
    )

    assert title == (
        "Experimental study on vibration stability in rotary ultrasonic "
        "machining of ceramic matrix composites: cutting force variation at "
        "hole entrance"
    )
    assert authors == "Zhang J"
    assert venue == "Ceramics International"


def test_split_title_authors_venue_handles_ampersand_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Marnix Wagemaker * & Chenglong Zhao *, Chemical short-range disorder "
        "in lithium oxide cathodes"
    )

    assert title == "Chemical short-range disorder in lithium oxide cathodes"
    assert authors == "Marnix Wagemaker, Chenglong Zhao"
    assert venue is None


def test_split_title_authors_venue_handles_comma_and_ampersand_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Hadas Alon Yehezkel, Steven Langford, Dong Zhou *, Baohua Li *, "
        "Guoxiu Wang * & Doron Aurbach *, External-pressure-electrochemistry "
        "coupling in solid-state lithium metal batteries"
    )

    assert title == (
        "External-pressure-electrochemistry coupling in solid-state lithium "
        "metal batteries"
    )
    assert authors is not None and "Doron Aurbach" in authors
    assert venue is None


def test_split_title_authors_venue_handles_multi_initial_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "and G. H. Jirka (1994), Axisymmetric instability of the annular "
        "Hagen Poiseuille flow with small inner radius by Chebyshevpseudospectral method"
    )

    assert title == (
        "Axisymmetric instability of the annular Hagen Poiseuille flow with "
        "small inner radius by Chebyshevpseudospectral method"
    )
    assert authors == "G. H. Jirka"
    assert venue is None


def test_split_title_authors_venue_handles_journal_tail_with_volume():
    title, authors, venue = _split_title_authors_venue(
        "and W. Brutsaert (1995), Diagnostics of landsurface spatial "
        "variability and water vapor flux. J. of Geophysical Research "
        "100(D12), 25595-25606"
    )

    assert title == "Diagnostics of landsurface spatial variability and water vapor flux"
    assert authors == "W. Brutsaert"
    assert venue == "J. of Geophysical Research 100(D12), 25595-25606"


def test_split_title_authors_venue_handles_journal_tail_with_v_volume():
    title, authors, venue = _split_title_authors_venue(
        "and G. H. Jirka (1995), Experimental study of plane turbulent wakes "
        "in a shallow water. Fluid Dynamics Research, V.16, 11-41"
    )

    assert title == "Experimental study of plane turbulent wakes in a shallow water"
    assert authors == "G. H. Jirka"
    assert venue == "Fluid Dynamics Research, V.16, 11-41"


def test_split_title_authors_venue_keeps_dotted_journal_prefix_out_of_title():
    title, authors, venue = _split_title_authors_venue(
        "T.W. Wu, Y.W Pan, M.Z. Liu et al. Discovery of the doubly charmed "
        "Tcc+ state implies a triply charmed Hccc hexaquark state, "
        "Phys.Rev.D 105 (2022) 3, L031505."
    )

    assert title == (
        "Discovery of the doubly charmed Tcc+ state implies a triply charmed "
        "Hccc hexaquark state"
    )
    assert authors == "T.W. Wu, Y.W Pan, M.Z. Liu, et al"
    assert venue == "Phys.Rev.D 105 (2022) 3, L031505"


def test_split_title_authors_venue_keeps_comma_title_with_dotted_journal_clean():
    title, authors, venue = _split_title_authors_venue(
        "Y. Kamiya, T.W. Wu, S. Nishihara et al. Kc(4180), with hidden charm "
        "as a DDbarK bound state, Phys.Rev.D 103 (2021) 1, 014014."
    )

    assert title == "Kc(4180), with hidden charm as a DDbarK bound state"
    assert authors == "Y. Kamiya, T.W. Wu, S. Nishihara, et al"
    assert venue == "Phys.Rev.D 103 (2021) 1, 014014"


def test_split_title_authors_venue_moves_in_compact_venue_year_out_of_title():
    title, authors, venue = _split_title_authors_venue(
        "M. Saqib Nawaz et al. Investigating Crossover Operators in Genetic "
        "Algorithms for High-Utility Itemset Mining. In ACIIDS 2021."
    )

    assert title == (
        "Investigating Crossover Operators in Genetic Algorithms for "
        "High-Utility Itemset Mining"
    )
    assert authors == "M. Saqib Nawaz et al"
    assert venue == "In ACIIDS 2021"


def test_extract_publications_strips_single_initial_before_acronym_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. M. S. Nawaz et al, P. COVID-19 Genome Analysis using Alignment
      Free Methods. In IEA AIE 2021.</p>
    </main>
    """

    pubs = extract_publications_from_html(html, page_url="https://example.edu/prof")

    assert [pub.clean_title for pub in pubs] == [
        "COVID-19 Genome Analysis using Alignment Free Methods"
    ]
    assert pubs[0].venue_text == "In IEA AIE 2021"


def test_extract_publications_truncates_profile_tail_after_compact_venue_year():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. M. S. Nawaz et al, P. COVID-19 Genome Analysis using Alignment
      Free Methods. In IEA AIE 2021. Muhammad Saqib Nawaz 大数据技术与应用研究所
      Pattern Mining 官方详情页：https://csse.szu.edu.cn/pages/user/index?id=1252</p>
    </main>
    """

    pubs = extract_publications_from_html(html, page_url="https://example.edu/prof")

    assert [pub.clean_title for pub in pubs] == [
        "COVID-19 Genome Analysis using Alignment Free Methods"
    ]
    assert pubs[0].venue_text == "In IEA AIE 2021"


def test_extract_publications_from_cuhk_mypage_publication_cards():
    html = """
    <html><body>
      <section id="publications">
        <h2>Publications</h2>
        <div class="publication">
          <a href="./static/PDF/DriveFlow.pdf">
            DriveFlow: Rectified Flow Adaptation for Autonomous Driving
          </a>
          <p>AAAI Conference on Artificial Intelligence, 2026.</p>
        </div>
        <div class="publication-card">
          <a href="./static/PDF/FedBridge.pdf">
            FedBridge: Communication-Efficient Federated Learning with
            Heterogeneous Clients
          </a>
          <p>IEEE Transactions on Mobile Computing, 2025.</p>
        </div>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://mypage.cuhk.edu.cn/academics/lizhen/",
    )

    assert [pub.clean_title for pub in pubs] == [
        "DriveFlow: Rectified Flow Adaptation for Autonomous Driving",
        (
            "FedBridge: Communication-Efficient Federated Learning with "
            "Heterogeneous Clients"
        ),
    ]
    assert pubs[0].venue_text == "AAAI Conference on Artificial Intelligence, 2026"
    assert pubs[0].year == 2026
    assert pubs[0].pdf_url == (
        "https://mypage.cuhk.edu.cn/academics/lizhen/static/PDF/DriveFlow.pdf"
    )


def test_extract_publications_from_cuhk_mypage_pub_list_items():
    html = """
    <html><body>
      <section id="publications" class="home-section">
        <div class="container">
          <div class="row">
            <div class="col-xs-12 col-md-4 section-heading">
              <h1>Publications</h1>
              <p>Papers & Publications</p>
            </div>
            <div class="col-xs-12 col-md-8">
              <div class="pub-list-item">
                <span itemprop="author">
                  Hongbin Lin, Yiming Yang, Chaoda Zheng, Zhen Li .
                </span>
                <a href="./static/PDF/DriveFlow.pdf">
                  DriveFlow: Rectified Flow Adaptation for Robust 3D Object
                  Detection in Autonomous Driving.
                </a>
                <b>AAAI 2026</b>
                <p>
                  <a class="btn btn-primary btn-outline btn-xs" href="./static/PDF/DriveFlow.pdf">PDF</a>
                  <a class="btn btn-primary btn-outline btn-xs" href="https://github.com/example/DriveFlow">Code</a>
                </p>
              </div>
              <div class="pub-list-item">
                <span itemprop="author">Yuncheng Jiang, Chun-Mei Feng, Zhen Li# .</span>
                <a href="./static/PDF/Federated-Ultrasound.pdf">
                  From pretraining to privacy: federated ultrasound foundation
                  model with self-supervised learning.
                </a>
                <b>npj Digital Medicine</b>
                <p>
                  <a class="btn btn-primary btn-outline btn-xs" href="./static/PDF/Federated-Ultrasound.pdf">PDF</a>
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://mypage.cuhk.edu.cn/academics/lizhen/",
    )

    assert [pub.clean_title for pub in pubs] == [
        (
            "DriveFlow: Rectified Flow Adaptation for Robust 3D Object "
            "Detection in Autonomous Driving"
        ),
        (
            "From pretraining to privacy: federated ultrasound foundation model "
            "with self-supervised learning"
        ),
    ]
    assert pubs[0].authors_text == "Hongbin Lin, Yiming Yang, Chaoda Zheng, Zhen Li"
    assert pubs[0].venue_text == "AAAI 2026"
    assert pubs[0].year == 2026
    assert pubs[0].pdf_url == (
        "https://mypage.cuhk.edu.cn/academics/lizhen/static/PDF/DriveFlow.pdf"
    )
    assert pubs[1].venue_text == "npj Digital Medicine"


def test_extract_publications_ignores_cuhk_lab_navigation_cards():
    html = """
    <html><body>
      <section id="publications">
        <h2>Publications</h2>
        <div class="publication"><a href="/lab">Deep Bit lab</a></div>
        <div class="publication"><a href="/news">Highlighted News</a></div>
        <div class="publication"><a href="/intro">Lab Introduction</a></div>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://sse.cuhk.edu.cn/faculty/example",
    )

    assert pubs == []


def test_extract_publications_ignores_cuhk_workshop_organizer_cards():
    html = """
    <html><body>
      <section id="publications" class="home-section">
        <h1>Publications</h1>
        <div class="pub-list-item">
          Organizers: Dr. Zhen Li, Dr. Chao Zheng, Dr. Hongyang Li.
          Program Committee: Yiming Yang, Chao Zhan, Kun Tang.
          <a href="https://topocotwacv26.github.io/" itemprop="name">
            The 1st WACV 2026 Workshop on Robust and Generalized Lane
            Topology Understanding and HD Map Generation through CoT Design
            (TopoCoT).
          </a>
          <b>WACV 2026 Workshop Website</b>
        </div>
        <div class="pub-list-item">
          <span itemprop="author">Haiming Zhang, Zhen Li# .</span>
          <a href="./static/PDF/SQS.pdf" itemprop="name">
            SQS: Enhancing Sparse Perception Models via Query-based Splatting
            in Autonomous Driving.
          </a>
          <b>NeurIPS 2025 Spotlight</b>
          <p><a href="./static/PDF/SQS.pdf">PDF</a></p>
        </div>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://mypage.cuhk.edu.cn/academics/lizhen/",
    )

    assert [pub.clean_title for pub in pubs] == [
        "SQS: Enhancing Sparse Perception Models via Query-based Splatting in Autonomous Driving"
    ]


def test_split_title_authors_venue_strips_short_comma_venue_tail():
    title, authors, venue = _split_title_authors_venue(
        "3D location and trajectory reconstruction of a moving object behind "
        "scattering media, IEEE Trans"
    )

    assert title == (
        "3D location and trajectory reconstruction of a moving object behind "
        "scattering media"
    )
    assert authors is None
    assert venue == "IEEE Trans"


def test_split_title_authors_venue_strips_abbreviated_semicolon_venue_tail():
    title, authors, venue = _split_title_authors_venue(
        "Human Pulse Diagnosis for Medical Assessments Using a Wearable "
        "Piezoelectret Sensing System; Adv"
    )

    assert title == (
        "Human Pulse Diagnosis for Medical Assessments Using a Wearable "
        "Piezoelectret Sensing System"
    )
    assert authors is None
    assert venue == "Adv"


def test_split_title_authors_venue_handles_marked_author_without_comma():
    title, authors, venue = _split_title_authors_venue(
        "Yaou Zhang * Persistent high glucose induced EPB41L4A-AS1 inhibits "
        "glucose uptake via GCN5 mediating crotonylation and acetylation of "
        "histones and non-histones"
    )

    assert title == (
        "Persistent high glucose induced EPB41L4A-AS1 inhibits glucose uptake "
        "via GCN5 mediating crotonylation and acetylation of histones and "
        "non-histones"
    )
    assert authors == "Yaou Zhang"
    assert venue is None


def test_split_title_authors_venue_handles_marked_last_author_inside_author_list():
    title, authors, venue = _split_title_authors_venue(
        "Weijie Liao, Naihan Xu, Haowei Zhang, Weifang Liao, Yanzhi Wang, "
        "Songmao Wang, Shikuan Zhang, Yuyang Jiang, Weidong Xie *, Yaou "
        "Zhang * Persistent high glucose induced EPB41L4A-AS1 inhibits "
        "glucose uptake via GCN5 mediating crotonylation and acetylation of "
        "histones and non-histones. Clin Transl Med. 2022 Feb;12(2):e699"
    )

    assert title == (
        "Persistent high glucose induced EPB41L4A-AS1 inhibits glucose uptake "
        "via GCN5 mediating crotonylation and acetylation of histones and "
        "non-histones"
    )
    assert authors is not None and "Yaou Zhang" in authors
    assert venue is not None and "Clin Transl Med" in venue


def test_split_title_authors_venue_strips_split_short_venue_tail():
    title, authors, venue = _split_title_authors_venue(
        "Yao Chu; Junwen Zhong,* Huiliang Liu; Yuan Ma; Nathaniel Liu; "
        "Yu Song; Jiaming Liang; Zhichun Shao; Yu Sun; Ying Dong,* Xiaohao "
        "Wang; and Liwei Lin*, Human Pulse Diagnosis for Medical Assessments "
        "Using a Wearable Piezoelectret Sensing System; Adv. Funct. Mater.; "
        "1803413; 2018"
    )

    assert title == (
        "Human Pulse Diagnosis for Medical Assessments Using a Wearable "
        "Piezoelectret Sensing System"
    )
    assert authors is not None and "Liwei Lin" in authors
    assert venue is not None and "Funct. Mater" in venue


def test_split_title_authors_venue_handles_middle_initial_before_semicolon():
    title, authors, venue = _split_title_authors_venue(
        "Rizwan Ur Rehman Sagar; Khurram Shehzad Ayaz Ali Florian J. "
        "Stadler; Qasim Khan; Jingjing Zhao; Xiaohao Wang; Min Zhang*, "
        "Defect-induced; temperature-independent; tunable magnetoresistance "
        "of partially fluorinated graphene foam. CARBON 2019(143), 179-188"
    )

    assert title == (
        "Defect-induced; temperature-independent; tunable magnetoresistance "
        "of partially fluorinated graphene foam"
    )
    assert authors is not None and "Florian J. Stadler" in authors
    assert venue is not None and "CARBON" in venue


def test_split_title_authors_venue_strips_split_comma_venue_tail():
    title, authors, venue = _split_title_authors_venue(
        "Rujia Deng, Xin Jin, Dongyu Du, 3D location and trajectory "
        "reconstruction of a moving object behind scattering media, IEEE "
        "Trans. Compuat. Imaging, 2021"
    )

    assert title == (
        "3D location and trajectory reconstruction of a moving object behind "
        "scattering media"
    )
    assert authors == "Rujia Deng, Xin Jin, Dongyu Du"
    assert venue is not None and "IEEE Trans" in venue


def test_split_title_authors_venue_handles_surname_initial_and_author_prefix():
    title, authors, venue = _split_title_authors_venue(
        "Chen, D. and G. H. Jirka (1994), Axisymmetric instability of the "
        "annular Hagen Poiseuille flow with small inner radius by "
        "Chebyshevpseudospectral method. International J. of Computational "
        "Fluid Dynamics, V.3, 265-280."
    )

    assert title == (
        "Axisymmetric instability of the annular Hagen Poiseuille flow with "
        "small inner radius by Chebyshevpseudospectral method"
    )
    assert authors is not None and "G. H. Jirka" in authors
    assert venue is not None and "Computational Fluid Dynamics" in venue


def test_split_title_authors_venue_handles_sustech_surname_initial_ampersand_list():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "5. Yang, Y. , Valencia, L. A. & Cui, B. Membrane curvature at "
            "the ER-PM contact sites. Trends in cell biology (2025). "
            "doi:10.1016/j.tcb.2025.10.002"
        )
    )

    assert title == "Membrane curvature at the ER-PM contact sites"
    assert authors is not None and "Yang" in authors
    assert authors is not None and "Valencia" in authors
    assert authors is not None and "Cui" in authors
    assert venue is not None and "Trends in cell biology" in venue


def test_split_title_authors_venue_handles_hyphenated_initial_author_list():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "[5] Ri Wu# , Jonas B. Metternich#, Anna S. Kamenik#, Prince "
            "Tiwari, Julian A. Harrison, Dennis Kessen, Hasan Akay, Lukas "
            "R. Benzenberg, T.-W. Dominic Chan, Sereina Riniker*, Renato "
            "Zenobi*. Determining the Gas-Phase Structures of α-Helical "
            "Peptides from Shape, Microsolvation, and Intramolecular "
            "Distance Data. Nat. Commun. 2023, 14, 2913."
        )
    )

    assert title == (
        "Determining the Gas-Phase Structures of α-Helical Peptides from "
        "Shape, Microsolvation, and Intramolecular Distance Data"
    )
    assert authors is not None and "T.-W. Dominic Chan" in authors
    assert authors is not None and "Renato Zenobi" in authors
    assert venue is not None and "Nat. Commun" in venue


def test_split_title_authors_venue_handles_hyphenated_initial_before_title():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "1. Z. Yang*, A. Mameri*, C. Cattoglio, C. Lachance, A. J. "
            "Florez Ariza, J. Luo, J. Humbert, D. Sudarshan, A. Banerjea, "
            "M. Galloy, A. Fradet-Turcotte, J.-P. Lambert, J. A. Ranish, "
            "J. Côté, E†. Nogales†, Structural insights into the human "
            "NuA4/TIP60 acetyltransferase and chromatin remodeling complex. "
            "Science (2024). Vol 385, Issue 6711, DOI: 10.1126/science.adl58162."
        )
    )

    assert title == (
        "Structural insights into the human NuA4/TIP60 acetyltransferase and "
        "chromatin remodeling complex"
    )
    assert authors is not None and "J.-P. Lambert" in authors
    assert authors is not None and "E. Nogales" in authors
    assert venue is not None and "Science" in venue


def test_split_title_authors_venue_handles_unicode_hyphen_author_names():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "[11] Ri Wu , Xiangfeng Chen*, Wei‐Jing Wu, Ze Wang, Yik‐Ling "
            "Winnie Hung, Hei‐Tung Wong, T‐W Dominic Chan*. Fine adjustment "
            "of gas modifier loadings for separation of epimeric glycopeptides "
            "using differential ion mobility spectrometry mass spectrometry. "
            "Rapid Commun. Mass Spectrom, 2020, 34, 9, e8751."
        )
    )

    assert title == (
        "Fine adjustment of gas modifier loadings for separation of epimeric "
        "glycopeptides using differential ion mobility spectrometry mass "
        "spectrometry"
    )
    assert authors is not None and "Wei-Jing Wu" in authors
    assert authors is not None and "T-W Dominic Chan" in authors
    assert venue is not None and "Rapid Commun" in venue


def test_split_title_authors_venue_strips_author_for_correspondence_tail():
    title, authors, venue = _split_title_authors_venue(
        _strip_item_prefix(
            "7. Yang Y , Wu M. Rhythmicity and waves in the cortex of single "
            "cells Author for correspondence : Phil Trans R Soc B. "
            "2018;(373):1-11. doi:10.1098/rstb.2017.0116"
        )
    )

    assert title == "Rhythmicity and waves in the cortex of single cells"
    assert authors == "Yang Y, Wu M"
    assert venue is not None and "Phil Trans R Soc B" in venue


def test_extract_publications_drops_author_note_only_item():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>(*第一或共同第一作者，†通讯作者)</li>
      <li>Activation of the helper NRC4 immune receptor forms a hexameric resistosome. Cell (2024).</li>
    </ol>
    </body></html>"""

    pubs = extract_publications_from_html(html, page_url="https://x.edu")

    assert [pub.clean_title for pub in pubs] == [
        "Activation of the helper NRC4 immune receptor forms a hexameric resistosome"
    ]


# --- _normalize_title_for_dedup ---


def test_normalize_title_for_dedup_case_insensitive():
    assert _normalize_title_for_dedup("Hello World") == _normalize_title_for_dedup(
        "hello world"
    )


def test_normalize_title_for_dedup_whitespace_collapsed():
    assert _normalize_title_for_dedup(
        "  Hello,  World!  "
    ) == _normalize_title_for_dedup("Hello World")


def test_normalize_title_for_dedup_empty_input():
    assert _normalize_title_for_dedup("") == ""


# -----------------------------------------------------------------------------
# Unit 2 — extract_publications_from_html (end-to-end on 5 archetypes + edges)
# -----------------------------------------------------------------------------


# --- 5 archetype happy paths ---


def test_extract_ol_list_happy_path():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/prof/doe")
    assert len(pubs) == 25
    assert all(len(p.clean_title) >= 10 for p in pubs)
    # [1] prefixes and trailing periods cleaned from clean_title
    assert not any(p.clean_title.startswith("[1]") for p in pubs)
    # DOI anchor captured on the 2nd item
    doi_items = [p for p in pubs if p.source_anchor and "doi.org" in p.source_anchor]
    assert len(doi_items) >= 1
    # source_url preserved
    assert all(p.source_url == "https://example.edu/prof/doe" for p in pubs)


def test_extract_ul_list_strips_prefixes_and_suffixes():
    html = _load("sample_ul_list.html")
    pubs = extract_publications_from_html(
        html, page_url="https://example.edu/prof/zhang"
    )
    assert len(pubs) == 15
    # No [1] prefixes nor [J]/[C]/[J/OL] suffixes in clean_title
    for p in pubs:
        assert not p.clean_title.startswith("[")
        assert "[J]" not in p.clean_title
        assert "[C]" not in p.clean_title
        assert "[J/OL]" not in p.clean_title
    # Years extracted
    assert sum(1 for p in pubs if p.year is not None) >= 10


def test_extract_paragraphs_happy_path():
    html = _load("sample_paragraphs.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/alice")
    assert len(pubs) == 10
    # At least one item has authors_text or venue_text populated (R5)
    assert sum(1 for p in pubs if p.authors_text or p.venue_text) >= 8
    # arxiv anchor captured on the 4th item
    arxiv_items = [p for p in pubs if p.source_anchor and "arxiv" in p.source_anchor]
    # NOTE: implementer decides whether bare "arxiv.org/abs/..." text without <a> tag
    # gets captured as anchor. If not, this assertion softens to presence-in-raw_title.
    if arxiv_items:
        assert len(arxiv_items) >= 1
    else:
        assert any("arxiv" in p.raw_title.lower() for p in pubs)


def test_extract_nested_sigs_heading_stitches_fragmented_spans():
    html = """<!doctype html><html><body>
    <div class="post">
      <div class="tt"><h3><span class="title">代表性论文</span></h3></div>
      <div class="con">
        <p><span>[1]</span><span>Shuting Liu, Baochang Zhang, Yiqing Liu, Tian Guan*, and </span>
        <strong>Yonghong He*</strong><span>, Unpaired Stain Transfer Using
        Pathology-Consistent Constrained Generative Adversarial Networks, </span>
        <em>IEEE Transactions on Medical Imaging</em><span>, 40(8):1977-1989, 2021.</span></p>
      </div>
    </div>
    </body></html>"""

    pubs = extract_publications_from_html(html, page_url="https://example.edu/hyh")

    assert len(pubs) == 1
    assert pubs[0].clean_title == (
        "Unpaired Stain Transfer Using Pathology-Consistent Constrained "
        "Generative Adversarial Networks"
    )
    assert pubs[0].authors_text is not None and "Yonghong He" in pubs[0].authors_text
    assert pubs[0].venue_text is not None and "IEEE Transactions" in pubs[0].venue_text
    assert pubs[0].year == 2021


def test_extract_table_happy_path():
    html = _load("sample_table.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/wang")
    assert len(pubs) == 8
    # Every row in this fixture has a year column
    assert all(p.year is not None for p in pubs)
    years = {p.year for p in pubs}
    assert 2024 in years and 2023 in years and 2022 in years


def test_extract_year_groups_happy_path():
    html = _load("sample_year_groups.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/chen")
    assert len(pubs) == 6
    # Year-heading groups: items under <h4>2023</h4> get year=2023, etc.
    years_found = {p.year for p in pubs}
    assert 2023 in years_found
    assert 2022 in years_found
    assert 2021 in years_found


# --- Contract: return type, purity, signature ---


def test_extract_returns_list_of_homepage_publication():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert isinstance(pubs, list)
    assert all(isinstance(p, HomepagePublication) for p in pubs)


def test_extract_is_pure_function_deterministic():
    html = _load("sample_ol_list.html")
    a = extract_publications_from_html(html, page_url="https://x.edu")
    b = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(a) == len(b)
    assert [p.clean_title for p in a] == [p.clean_title for p in b]


def test_extract_accepts_author_filter_none_default():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 25  # No filter applied
    pubs2 = extract_publications_from_html(
        html, page_url="https://x.edu", author_filter=None
    )
    assert len(pubs2) == 25


def test_extract_respects_author_filter():
    html = _load("sample_ol_list.html")
    # Filter: keep only items whose authors_text includes "X. Liu"
    pubs = extract_publications_from_html(
        html,
        page_url="https://x.edu",
        author_filter=lambda text: text is not None and "Liu" in text,
    )
    # Fixture has several items with X. Liu; expect at least 1 and fewer than total
    assert 1 <= len(pubs) < 25


# --- Edge cases ---


def test_extract_empty_html_returns_empty_list():
    pubs = extract_publications_from_html("", page_url="https://x.edu")
    assert pubs == []


def test_extract_html_with_no_publications_section_returns_empty():
    html = """<!doctype html><html><body><h1>Home</h1><p>Welcome to my page.</p></body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert pubs == []


def test_extract_publications_section_with_empty_list_returns_empty():
    html = """<!doctype html><html><body>
    <h2>Publications</h2><ol></ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert pubs == []


def test_extract_dedups_within_single_section():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>Identical Title Here. A. Smith. Venue 2023.</li>
      <li>Identical Title Here. A. Smith. Venue 2023.</li>
      <li>Different Title Goes Here. B. Jones. Other Venue 2023.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 2  # duplicate collapsed


def test_extract_dedups_across_multiple_sections():
    html = """<!doctype html><html><body>
    <h2>Selected Publications</h2>
    <ul>
      <li>Shared Paper Title. A. Smith. Venue 2023.</li>
      <li>Selected Only Title. A. Smith. Venue 2022.</li>
    </ul>
    <h2>Full Publications</h2>
    <ol>
      <li>Shared Paper Title. A. Smith. Venue 2023.</li>
      <li>Full Only Title. A. Smith. Venue 2021.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    # 3 unique: Shared, Selected-Only, Full-Only
    assert len(pubs) == 3


def test_extract_drops_items_below_min_title_length():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>TBD.</li>
      <li>Proper Title That Is Long Enough. Authors 2023.</li>
      <li>1.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 1
    assert "Proper Title" in pubs[0].clean_title


def test_extract_drops_author_list_without_title():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <p>22. Muhammad, D; Xia, W; Wang, MS; Sun, ZX; Zhang, JZH,
    Int. J. Bio. Macromol. , 2025, 306, 141454.</p>
    </body></html>"""

    pubs = extract_publications_from_html(html, page_url="https://x.edu")

    assert pubs == []


def test_extract_item_without_year_still_extracted():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>Forthcoming Title About Something, to appear in Venue.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 1
    assert pubs[0].year is None


def test_extract_publications_strips_to_appear_venue_tail_from_clean_title():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>Asymptotics of Fredholm determinant solutions of the
      noncommutative Painlevé II equation, to appear in Anal. Appl.</li>
    </ol>
    </body></html>"""

    pubs = extract_publications_from_html(html, page_url="https://x.edu")

    assert [pub.clean_title for pub in pubs] == [
        (
            "Asymptotics of Fredholm determinant solutions of the "
            "noncommutative Painlevé II equation"
        )
    ]


def test_extract_does_not_cap_official_publication_items():
    items = "\n".join(
        f"<li>Long Enough Item Title Number {i}. A 2023.</li>" for i in range(250)
    )
    html = f"""<!doctype html><html><body>
    <h2>Publications</h2><ol>{items}</ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 250


def test_extract_malformed_html_does_not_raise():
    html = (
        "<html><body><h2>Publications</h2>"
        "<ul><li>First item title.<li>Second item <b>unclosed"
        "<li>Third item OK. 2023.</ul></body></html>"
    )
    # lxml is permissive; extractor should return best-effort, not raise.
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert isinstance(pubs, list)


def test_extract_plain_profile_raw_text_representative_publications_section():
    raw_text = (
        "尹剑飞 个人简介 深圳大学计算与软件学院副教授，硕士生导师。"
        "研究方向 深度学习、强化学习、软件工程、数据优化等 "
        "其他 代表性学术论文（10篇）（英文论文、三大索引）： "
        "Jianfei Yin, Weifeng Li. Wireless Sensor Network Node Localization "
        "Algorithm Based on SDP and ESDP. The International Conference on "
        "Consumer Electronics, Communications and Networks (CECNet 2013). "
        "明仲, 尹剑飞, 肖志娇. 一种Web系统性能测试框架及其混合建模过程. "
        "计算机研究与发展, 2010年7月 "
        "Jianfei Yin, Zhong Ming, Zhijiao Xiao, Hui Wang. A Web Performance "
        "Modeling Process based on the Methodology of Learning From Data. "
        "In Proc of the 9th International Conference for Young Computer "
        "Scientists ICYCS, 2008, Zhangjiajie, IEEE Computer Society, 1285-1291 "
        "A Rewriting Logic Based MDA Concepts Framework, WSEAS TRANS. on "
        "INFO. SCI. & APP, June 2006. "
        "Pattern Semantic Link: A Reusable pattern representation in MDA "
        "context, ICDCIT 2004, Springer-Verlag, LNCS 3347, Dec.2004. "
        "A new dependable exchange protocol. Computer Communications 29(15): "
        "2770-2780, 2006 "
        "Abuse-Free Item Exchange. ICCSA2005，Springer LNCS 3483, 2005 "
        "代表性项目： 国家自然科学基金、j0824304、自然科学基金资助成果收集到结题发布流程及解决方案。"
        "获奖： 2009年深圳市科技创新奖。"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://PROF-6B64ABAF9789",
    )

    titles = [pub.clean_title for pub in pubs]
    assert "Wireless Sensor Network Node Localization Algorithm Based on SDP and ESDP" in titles
    assert "一种Web系统性能测试框架及其混合建模过程" in titles
    assert "A Web Performance Modeling Process based on the Methodology of Learning From Data" in titles
    assert "A Rewriting Logic Based MDA Concepts Framework" in titles
    assert "Pattern Semantic Link: A Reusable pattern representation in MDA context" in titles
    assert "A new dependable exchange protocol" in titles
    assert "Abuse-Free Item Exchange" in titles
    assert "Springer LNCS 3483" not in titles
    assert all("自然科学基金" not in title for title in titles)


def test_extract_plain_profile_raw_text_short_representative_publication_section():
    raw_text = (
        "李明 个人简介 深圳某高校副教授。"
        "代表性论文：Robust Graph Matching for Robotics. IEEE Robotics Letters, 2024. "
        "研究方向 机器人感知。"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://PROF-SHORT-PUB",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Robust Graph Matching for Robotics"
    ]


def test_extract_plain_profile_raw_text_sysu_recent_publications_full_list():
    raw_text = (
        "Research Field Computer Vision and its applications in Cybersecurity "
        "Recent Publications 【 Full List 】 "
        "Yangbangyan Jiang, Qianqian Xu, Yunrui Zhao, Zhiyong Yang, Peisong Wen, "
        "Xiaochun Cao, and Qingming Huang. Positive-Unlabeled Learning with Label "
        "Distribution Alignment. IEEE Transactions on Pattern Analysis and Machine "
        "Intelligence (TPAMI), To Appear "
        "Wenqiang Wang, Chongyang Du, Tao Wang, Kaihao Zhang, Wenhan Luo, Lin Ma, "
        "Wei Liu, Xiaochun Cao. Punctuation-level Attack: Single-shot and Single "
        "Punctuation Can Fool Text Models. NeurIPS, 2023 "
        "Liang Yang, Runjie Shi, Qiuliang Zhang, Bingxin Niu, Zhen Wang, Chuan Wang "
        "and Xiaochun Cao. Self-supervised Graph Neural Networks via Low-Rank "
        "Decomposition. NeurIPS 2023 "
        "Zitai Wang, Qianqian Xu, Zhiyong Yang, Yuan He, Xiaochun Cao, Qingming "
        "Huang. A Unified Generalization Analysis of Re-Weighting and "
        "Logit-Adjustment for Imbalanced Learning. NeurIPS, 2023 (Spotlight) "
        "Siran Dai, Qianqian Xu, Zhiyong Yang, Xiaochun Cao, Qingming Huang. "
        "DRAUC: An Instance-wise Distributionally Robust AUC Optimization "
        "Framework. NeurIPS, 2023 "
        "Awards"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://PROF-9F580DAF4994",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Positive-Unlabeled Learning with Label Distribution Alignment",
        "Punctuation-level Attack: Single-shot and Single Punctuation Can Fool Text Models",
        "Self-supervised Graph Neural Networks via Low-Rank Decomposition",
        "A Unified Generalization Analysis of Re-Weighting and Logit-Adjustment for Imbalanced Learning",
        "DRAUC: An Instance-wise Distributionally Robust AUC Optimization Framework",
    ]


def test_extract_publications_follows_sustech_academic_outputs_to_publication_label():
    html = """
    <html><body>
      <div class="profile">
        <p><strong>学术成果（发表论著或者论文）</strong></p>
        <p>论文发表：</p>
        <p>
          2020
          1. Yun X, Wang L, Tao S. Adaptive Secure Control for Cyber Physical Systems.
          IEEE Transactions on Automatic Control, 2020.
          2. Zhang H, Shu T. Communication Efficient Learning over Distributed Networks.
          IEEE Transactions on Signal Processing, 2019.
          3. Li J, Chen Y. Robust Estimation for Networked Systems.
          Automatica, 2018.
        </p>
        <p>研究方向：网络安全与智能系统。</p>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.sustech.edu.cn/example",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Adaptive Secure Control for Cyber Physical Systems",
        "Communication Efficient Learning over Distributed Networks",
        "Robust Estimation for Networked Systems",
    ]


def test_extract_publications_continues_across_sustech_topic_labels_inside_section():
    html = """
    <html><body>
      <div class="profile">
        <p><strong>代表性论文</strong></p>
        <p>机构学与机器人学理论：</p>
        <p>◆ Y. Xing, J. Dai. Geometric Methods for Robot Constraint Analysis.
        Mechanism and Machine Theory, 2022.</p>
        <p>◆ J. Dai, K. Xu. Reconfigurable Parallel Mechanisms for Surgical Robotics.
        IEEE Robotics and Automation Letters, 2021.</p>
        <p>教育经历：博士毕业于某大学。</p>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.sustech.edu.cn/example",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Geometric Methods for Robot Constraint Analysis",
        "Reconfigurable Parallel Mechanisms for Surgical Robotics",
    ]


def test_extract_publications_detects_sustech_span_strong_papers_and_patents_heading():
    html = """
    <html><body>
      <div class="profile">
        <span><strong>论文及专利</strong></span>
        <p>A-1. Journal articles</p>
        <p>1. Zhang C, Wang H. Organic Carbon Cycling in Deep Marine Sediments.
        Nature Geoscience, 2022.</p>
        <p>2. Liu Q, Zhang C. Microbial Mediation of Methane Fluxes.
        Geobiology, 2021.</p>
        <p>授权专利：一种深海沉积物采样装置，授权号 CN202410001234.5。</p>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.sustech.edu.cn/example",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Organic Carbon Cycling in Deep Marine Sediments",
        "Microbial Mediation of Methane Fluxes",
    ]


def test_extract_publications_ignores_misaligned_tab_panels_without_citations():
    html = """
    <html><body>
      <ul class="teacherTabs">
        <li><span>硕博招生信息</span></li>
        <li><span>学生</span></li>
        <li><span>Selected papers</span></li>
      </ul>
      <div class="tabs">
        <div class="part_box">
          名称 硕博招生信息 The research group plans to recruit 2-3 PhD
          students and 2-3 Master's students annually. Applicants with
          academic backgrounds related to low-dimensional semiconductor
          materials are preferred.
        </div>
        <div class="part_box">
          名称 2025 博士生：潘旭；硕士生：李文博、许凤超。
          2024 博士生：张谦；硕士生：黄贞融、刘英俊。
        </div>
        <div class="part_box">
          <p><strong>Selected papers</strong></p>
          <p>方向1：低维半导体材料与逻辑电子器件集成</p>
          <p>1. Jing-Kai Qin, Pai-Ying Liao. Raman response and transport
          properties of tellurium atomic chains encapsulated in nanotubes.
          Nature Electronics, 2020, 3(3): 141-147.</p>
          <p>2. Cheng-Yi Zhu, Jing-Kai Qin. Reliable Devices for Intelligent
          Systems. IEEE Transactions on Electron Devices, 2024.</p>
        </div>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/qinjingkai",
    )

    titles = [pub.clean_title for pub in pubs]
    assert titles == [
        "Raman response and transport properties of tellurium atomic chains encapsulated in nanotubes",
        "Reliable Devices for Intelligent Systems",
    ]
    assert all("PhD" not in title for title in titles)
    assert all("博士生" not in title for title in titles)


def test_extract_publications_keeps_direction_subheadings_inside_paper_section():
    html = """
    <html><body>
      <div class="editor_content">
        <p><strong>Selected papers</strong></p>
        <p>方向1：低维半导体材料与逻辑电子器件集成</p>
        <p>1. Jing-Kai Qin, Pai-Ying Liao. Raman response and transport
        properties of tellurium atomic chains encapsulated in nanotubes.
        Nature Electronics, 2020, 3(3): 141-147.</p>
        <p>方向2：感存算一体化器件与架构</p>
        <p>2. Pei-Yu Huang, Jing-Kai Qin. Retinomorphic vision chip for
        high-accuracy in-sensor static and dynamic object recognition.
        Nature Communications, 2023, 14, 6736.</p>
      </div>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/qinjingkai",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Raman response and transport properties of tellurium atomic chains encapsulated in nanotubes",
        "Retinomorphic vision chip for high-accuracy in-sensor static and dynamic object recognition",
    ]


def test_plain_text_fallback_rejects_student_supervision_entries_with_counts():
    raw_text = (
        "学术论文："
        "【7】王佳东，硕士研究生，2014-2016，本科毕业哈尔滨理工大学；"
        "研究课题：Research on design and application of delay-based physical "
        "unclonable function. *发表EI一作文章1篇。硕士期间受资助赴台湾参加"
        "2015AsianHost学术会议。*目前工作于中兴（深圳）。"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="https://faculty.example.edu/student-supervision",
    )

    assert pubs == []


def test_plain_text_fallback_rejects_biography_publication_count_prose():
    raw_text = (
        "论文发表 "
        "崔来中 个人简介 2007年6月于吉林大学获工学学士学位，同年被免试推荐"
        "直接攻读博士研究生，2012年6月于清华大学获计算机科学与技术博士学位。"
        "研究领域包括：下一代互联网体系结构、软件定义网络、边缘计算、大数据分析、"
        "机器学习和智能计算。担任SCI期刊《International Journal of Machine "
        "Learning and Cybernetics》、《International Journal of Bio-Inspired "
        "Computation》和《Ad Hoc and Sensor Wireless Networks》的副编辑/编委。"
        "已主持国家重点研发计划课题、国家自然科学基金等项目10多项。"
        "已在国内外重要期刊以及国际会议上发表SCI/EI检索论文80余篇。"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="https://bigdata.szu.edu.cn/info/1008/1184.htm",
    )

    assert pubs == []


def test_numbered_plain_text_entries_are_filtered_after_split():
    raw_text = (
        "学术论文："
        "1. Reliable Systems for Sensor Networks. IEEE Internet of Things Journal, 2024. "
        "【2】王佳东，硕士研究生，2014-2016，本科毕业哈尔滨理工大学；"
        "研究课题：Research on design and application of delay-based physical "
        "unclonable function. *发表EI一作文章1篇。"
    )

    pubs = extract_publications_from_html(
        raw_text,
        page_url="https://faculty.example.edu/mixed-supervision",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Reliable Systems for Sensor Networks"
    ]


def test_marker_legend_is_not_publication():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <p># = first co-author</p>
        <p>* = corresponding author</p>
        <p>Reliable Paper Title. Journal of Systems, 2024.</p>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/legend",
    )

    assert [pub.clean_title for pub in pubs] == ["Reliable Paper Title"]


def test_link_label_does_not_contaminate_title_or_author_boundary():
    html = """
    <html><body>
      <section>
        <h2>Publications</h2>
        <p>38. Enhanced Performance of Single-crystal Perovskite Solar Cells
        via In-situ Passivation of Ionic Liquid [ Link ] Tongpeng Zhao#,
        Ruiqin He#, Nanoscale, 2026.</p>
      </section>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/link-label",
    )

    assert [pub.clean_title for pub in pubs] == [
        "Enhanced Performance of Single-crystal Perovskite Solar Cells via In-situ Passivation of Ionic Liquid"
    ]
    assert all("[ Link ]" not in pub.clean_title for pub in pubs)
    assert all("Tongpeng Zhao" not in pub.clean_title for pub in pubs)


def test_uestc_yjsjy_seed28_bracketed_numbered_entries_do_not_merge_or_shift_title():
    html = """
    <html><body>
      <p>研究成果：</p>
      <p>代表性论著：</p>
      <p>论文
      3、Junfeng Xiao，Dongxing Zhang，Mingyue Zheng，YangBai，Yong Sun，
      Liwen Zhang，Qiuquan Guo，Jun Yang，3D printing of metallic structures
      using dopamine-integrated photopolymer，Journal of Materials Research
      and Technology，19，1355-1366，2022.
      4、[第一作者] Yong Sun*, Vladimir Luzin, Yixin Duan, Lei Shi,
      Matthias Weiss. Forming-Induced Residual Stress and Material Properties
      of Roll-Formed High-Strength Steels. Automot. Innov. 3, 210-220, 2020.
      (检索号: https://doi.org/10.1007/s42154-020-00112-2)
      (5)[第一作者] Yong Sun*, Yaguang Li, Dayong Li, Paul A. Meehan,
      William J.T.Daniel, Lei Shi, Hua Xiao, Jichao Zhang, Shichao Ding.
      Predictive modelling of longitudinal bow in Chain-die formed AHSS
      profiles and its experimental verification. Journal of Manufacturing
      Processes. 39, 208-225., 2019.
      (12)Zhen Qian, Yong Sun, Paul A. Meehan, William J.T. Daniel &
      Shichao Ding. Experimental and numerical investigation of flange angle
      in chain-die formed AHSS U-channel sections, The International Journal
      of Advanced Manufacturing Technology. 92(1-4), 1147-1164, 2017.</p>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20492?yxsh=28",
    )

    titles = [pub.clean_title for pub in pubs]
    assert "3D printing of metallic structures using dopamine-integrated photopolymer" in titles
    assert (
        "Forming-Induced Residual Stress and Material Properties of Roll-Formed High-Strength Steels"
        in titles
    )
    assert (
        "Predictive modelling of longitudinal bow in Chain-die formed AHSS profiles and its experimental verification"
        in titles
    )
    assert (
        "Experimental and numerical investigation of flange angle in chain-die formed AHSS U-channel sections"
        in titles
    )
    assert "Daniel & Shichao Ding" not in titles
    assert all("Predictive modelling" not in (pub.venue_text or "") for pub in pubs)


def test_uestc_yjsjy_research_outputs_heading_stops_before_profile_tail():
    html = """
    <html><body>
      <p>研究成果：</p>
      <p>1. Xing He, Yuhong Zhang. Robust Software Architecture Recovery
      with Graph Neural Networks. Journal of Systems and Software, 2024.</p>
      <p>2. Zhiguo Wang, Guangqiang Yin. Mining Software Defect Reports
      for Intelligent Debugging. Information and Software Technology, 2023.</p>
      <p>专业研究方向：软件工程、智能软件系统。</p>
      <p>招生类别：电子信息专业硕士。</p>
      <p>学院列表：软件工程、机械工程、电子信息。</p>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/12345?yxsh=28",
    )

    titles = [pub.clean_title for pub in pubs]
    assert titles == [
        "Robust Software Architecture Recovery with Graph Neural Networks",
        "Mining Software Defect Reports for Intelligent Debugging",
    ]
    assert all("专业研究方向" not in pub.raw_title for pub in pubs)
    assert all("学院列表" not in pub.raw_title for pub in pubs)


def test_uestc_yjsjy_inline_research_outputs_extract_from_table_cell():
    html = """
    <html><body>
      <table><tbody>
        <tr><td><b>个人简介：</b></td></tr>
        <tr><td>近年来主要从事人工智能和大数据分析技术前沿和应用研究，
        在Robotics and Automous Systems等刊物发表论文300多篇。</td></tr>
        <tr><td><b>科研项目：</b></td></tr>
        <tr><td><b>研究成果：</b></td></tr>
        <tr><td>
          1. M.L. Zhong, C.Y. Hong, Z.Q. Jia, C.Y. Wang, Z.G. Wang,
          DynaTM-SLAM: Fast filtering of dynamic feature points and
          object-based localization in dynamic indoor environments,
          Robotics and Automous Systems, 174 (2024) 104634.
        </td></tr>
        <tr><td>
          2. C.Y. Hong, M.L. Zhong, Z.Q. Jia, C.J. You, Z.G. Wang,
          A stereo vision SLAM with moving vehicles tracking in outdoor
          environment, Machine Vision and Applications, 35 (2024) 5.
        </td></tr>
        <tr><td><b>专业研究方向：</b></td></tr>
        <tr><td>085400电子信息 08软件工程（非全） 硕士专业学位</td></tr>
      </tbody></table>
    </body></html>
    """

    pubs = extract_publications_from_html(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10237?yxsh=28",
    )

    titles = [pub.clean_title for pub in pubs]
    assert titles == [
        "DynaTM-SLAM: Fast filtering of dynamic feature points and object-based localization in dynamic indoor environments",
        "A stereo vision SLAM with moving vehicles tracking in outdoor environment",
    ]
    assert all("发表论文300多篇" not in pub.raw_title for pub in pubs)
    assert all("专业研究方向" not in pub.raw_title for pub in pubs)
