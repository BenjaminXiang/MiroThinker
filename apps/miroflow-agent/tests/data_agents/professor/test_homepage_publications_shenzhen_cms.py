from __future__ import annotations

from pathlib import Path

from src.data_agents.professor import homepage_publications as publication_parser
from src.data_agents.professor.homepage_publications import (
    extract_publications_from_html,
    extract_publications_with_diagnostics_from_html,
)


_RUN_FIXTURE_DIR = (
    Path(__file__).resolve().parents[5]
    / "logs"
    / "data_agents"
    / "paper"
    / "homepage_ingest_runs"
    / "2026-05-09"
)


def _paper_paragraphs() -> str:
    return """
    <p>1. Adaptive action chunking at inference time for vision language action
    models. IEEE Conference on Computer Vision and Pattern Recognition, 2026.</p>
    <p>2. Reliable vector guided softmax loss for robust face recognition
    systems. IEEE Transactions on Image Processing, 2024.</p>
    <p>3. Teacher guided neural architecture search for face recognition
    models. AAAI Conference on Artificial Intelligence, 2021.</p>
    <p>4. Exclusivity consistency regularized knowledge distillation for face
    recognition. European Conference on Computer Vision, 2020.</p>
    <p>5. Loss function search for face recognition with noisy web labels.
    International Conference on Machine Learning, 2020.</p>
    """


def _br_separated_papers() -> str:
    return """
    1. Adaptive action chunking at inference time for vision language action
    models. IEEE Conference on Computer Vision and Pattern Recognition, 2026.<br/>
    2. Reliable vector guided softmax loss for robust face recognition
    systems. IEEE Transactions on Image Processing, 2024.<br/>
    3. Teacher guided neural architecture search for face recognition
    models. AAAI Conference on Artificial Intelligence, 2021.<br/>
    4. Exclusivity consistency regularized knowledge distillation for face
    recognition. European Conference on Computer Vision, 2020.<br/>
    5. Loss function search for face recognition with noisy web labels.
    International Conference on Machine Learning, 2020.
    """


V1_ACADEMIC_RESULTS_HTML = f"""
<html><body>
  <div class="item">
    <h3 class="tit">学术成果</h3>
    <div class="desc">
      <p>近年发表的主要学术论文 (Selected Journal Papers)：</p>
      {_paper_paragraphs()}
    </div>
  </div>
</body></html>
"""


V2_STRONG_PARAGRAPH_HTML = f"""
<html><body>
  <div class="WordSection1">
    <p><strong><span>代表性论文：</span></strong></p>
    <p>{_br_separated_papers()}</p>
  </div>
</body></html>
"""


V3_CMS_TITLE_HTML = f"""
<html><body>
  <div class="body">
    <div class="tit">代表性文章</div>
    <div class="text">
      {_paper_paragraphs()}
    </div>
  </div>
</body></html>
"""


V4_STANDALONE_HEADING_HTML = f"""
<html><body>
  <div class="szdw_bd">
    <p>代表文章：</p>
    {_paper_paragraphs()}
  </div>
</body></html>
"""


def _extract(html: str):
    return extract_publications_from_html(html, page_url="https://example.edu/prof")


def test_sztu_creative_design_fragment_extracts_typical_paper_semicolon_entries():
    html = """
    <html><body>
      <ul class="news-list">
        <li class="news-item">
          <div class="team-item">
            <h3>魏芊蕙</h3>
            <div class="news-item__intro">
              <p>Associate Professor, School of Creative Design.</p>
              <p>Typical paper: Color Harmony Evaluation in Interactive
              Products. Design Studies, 2024; A Data-Driven Method for Cultural
              Heritage Pattern Generation. Advanced Engineering Informatics,
              2023; Emotional Design Cues for Smart Home Interfaces. Journal
              of Design Research, 2022.</p>
            </div>
          </div>
        </li>
      </ul>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://creative.sztu.edu.cn/team#prof-魏芊蕙",
    )

    assert [publication.clean_title for publication in publications] == [
        "Color Harmony Evaluation in Interactive Products",
        "A Data-Driven Method for Cultural Heritage Pattern Generation",
        "Emotional Design Cues for Smart Home Interfaces",
    ]


def test_sztu_creative_design_fragment_does_not_extract_count_only_paper_text():
    html = """
    <html><body>
      <ul class="news-list">
        <li class="news-item">
          <div class="team-item">
            <h3>某教师</h3>
            <div class="news-item__intro">
              <p>主持设计类项目多项，发表论文 10 篇。</p>
            </div>
          </div>
        </li>
      </ul>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://creative.sztu.edu.cn/team#prof-某教师",
    )

    assert publications == []


def test_sztu_creative_design_fragment_preserves_title_ending_with_design():
    html = """
    <html><body>
      <p>Typical paper: Participatory Design. Design Studies, 2024; Human-centered
      Interaction. Design Issues, 2023.</p>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://creative.sztu.edu.cn/team#prof-design",
    )

    assert [publication.clean_title for publication in publications] == [
        "Participatory Design",
        "Human-centered Interaction",
    ]
    assert publications[0].venue_text == "Design Studies, 2024"


def test_sztu_creative_design_fragment_still_rejects_person_name_before_venue():
    html = """
    <html><body>
      <p>Typical paper: John Smith. Nature, 2024; Participatory Design.
      Design Studies, 2024.</p>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://creative.sztu.edu.cn/team#prof-design",
    )

    assert [publication.clean_title for publication in publications] == [
        "Participatory Design",
    ]


def test_v1_academic_results_heading_uses_new_vocab_word():
    publications = _extract(V1_ACADEMIC_RESULTS_HTML)

    assert len(publications) >= 5


def test_v2_strong_paragraph_heading_accepts_trailing_punctuation():
    publications = _extract(V2_STRONG_PARAGRAPH_HTML)

    assert len(publications) >= 5


def test_v3_cms_title_class_heading_is_detected():
    publications = _extract(V3_CMS_TITLE_HTML)

    assert len(publications) >= 5


def test_v4_short_standalone_exact_vocab_heading_is_detected():
    publications = _extract(V4_STANDALONE_HEADING_HTML)

    assert len(publications) >= 5


def test_szu_math_research_outputs_heading_is_detected():
    html = f"""
    <html><body>
      <div class="szdw_bd">
        <h3>科研成果</h3>
        {_paper_paragraphs()}
      </div>
    </body></html>
    """

    publications = _extract(html)

    assert len(publications) >= 5


def test_sysu_sic_partial_representative_outputs_heading_is_detected():
    html = f"""
    <html><body>
      <article>
        <h3>五、部分代表性成果</h3>
        {_paper_paragraphs()}
      </article>
    </body></html>
    """

    publications = _extract(html)

    assert len(publications) >= 5


def test_sysu_sic_strong_partial_outputs_with_nested_paper_label_is_detected():
    html = f"""
    <html><body>
      <article>
        <p><strong>五、部分代表性成果</strong></p>
        <p><strong>1.学术论文</strong></p>
        {_paper_paragraphs()}
        <p><strong>2.科研项目</strong></p>
        <p>国家自然科学基金项目，主持。</p>
      </article>
    </body></html>
    """

    publications = _extract(html)

    assert len(publications) >= 5


def test_suat_synbio_representative_outputs_strip_chinese_grant_tails():
    html = """
    <html><body>
      <article>
        <p><strong>（科研成果）重大科技项目承担情况，代表性文章、成果转化情况：</strong></p>
        <p>1.2024年，Leaf dissection and margin serration are independently
        regulated by two transcription factors converging on the CUC2-auxin
        module in wild strawberry （Current Biology）鉴定了植物叶片型状多样性的调控因子和调控机制。</p>
        <p>2.2022年，Mechanism of fertilization-induced auxin synthesis in the
        endosperm for seed and fruit development（Nature Communication）揭示了花蕊受粉是如何激活MADS-box
        基因AGL62 而启动果实形成的分子机制。</p>
        <p>3.2020年，Molecular framework underlying stolon development in
        strawberry，美国NSF ，课题负责人</p>
      </article>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://synbio.suat-sz.edu.cn/info/1151/2128.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Leaf dissection and margin serration are independently regulated by "
            "two transcription factors converging on the CUC2-auxin module in wild "
            "strawberry"
        ),
        (
            "Mechanism of fertilization-induced auxin synthesis in the endosperm "
            "for seed and fruit development"
        ),
        "Molecular framework underlying stolon development in strawberry",
    ]
    assert publications[0].venue_text == "Current Biology"
    assert publications[1].venue_text == "Nature Communication"
    assert publications[2].year == 2020


def test_shenzhen_bigdata_table_ignores_cms_publish_metadata():
    html = """
    <html><body>
      <article>
        <h2>2019年代表性论文</h2>
        <p>发布时间：2019-12-31 10:34:22 来源：系统管理员 浏览次数：</p>
        <table>
          <tr>
            <th>序号</th><th>论文名称</th><th>期刊</th><th>时间</th><th>作者</th>
          </tr>
          <tr>
            <td>1</td>
            <td>A distributed data management system to support large-scale data analysis</td>
            <td>The Journal of Systems &amp; Software</td>
            <td>2019</td>
            <td>黄哲学</td>
          </tr>
          <tr>
            <td>2</td>
            <td>Differential evolution algorithm with dichotomy-based parameter space compression</td>
            <td>Soft Computing</td>
            <td>2019</td>
            <td>崔来中</td>
          </tr>
        </table>
      </article>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://bigdata.szu.edu.cn/info/1016/1210.htm",
    )

    titles = {publication.clean_title for publication in publications}
    assert "A distributed data management system to support large-scale data analysis" in titles
    assert (
        "Differential evolution algorithm with dichotomy-based parameter space compression"
        in titles
    )
    assert all("发布时间" not in publication.raw_title for publication in publications)
    first = next(
        publication
        for publication in publications
        if publication.clean_title
        == "A distributed data management system to support large-scale data analysis"
    )
    assert first.venue_text == "The Journal of Systems & Software"
    assert first.authors_text == "黄哲学"
    assert first.year == 2019
    assert all("自然科学基金" not in publication.clean_title for publication in publications)


def test_szu_bigdata_meta_description_publications_are_extracted():
    html = """
    <html>
      <head>
        <meta name="description" content="科研成果：代表性论文：1. Hybrid
        interaction mining for large-scale visual analytics. IEEE Transactions on
        Visualization and Computer Graphics, 2024; 2. Efficient graph learning
        for urban computing. ACM Transactions on Knowledge Discovery from Data,
        2023" />
      </head>
      <body>
        <article>
          <p>发表近30篇论文，CCF A类论文19篇。</p>
        </article>
      </body>
    </html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://bigdata.szu.edu.cn/info/1008/1321.htm",
    )

    titles = {publication.clean_title for publication in publications}
    assert "Hybrid interaction mining for large-scale visual analytics" in titles
    assert "Efficient graph learning for urban computing" in titles
    assert all("发表近30篇" not in publication.clean_title for publication in publications)


def test_sysu_sofe_ordinal_partial_papers_heading_is_detected():
    html = f"""
    <html><body>
      <article>
        <p><strong>五、部分论文（Selected Publications）</strong></p>
        {_paper_paragraphs()}
        <p><strong>六、科研项目</strong></p>
        <p>深圳市基础研究项目。</p>
      </article>
    </body></html>
    """

    publications = _extract(html)

    assert len(publications) >= 5
    assert all("深圳市基础研究项目" not in publication.clean_title for publication in publications)


def test_sustech_plain_text_academic_outputs_label_extracts_literature_items():
    text = """
    学术成果（发表论著或者论文或者专利）：
    Book (chapter):
    1. Yi Liu & Zhenzhong Zeng* ; Wind energy. In The Palgrave Handbook of
    Global Sustainability. (Cham: Springer International Publishing, 2022).
    L iteratures:
    1. Lili Liang; Shijing Liang & Zhenzhong Zeng *; Extreme climate sparks
    record boreal wildfires and carbon surge in 2023; The Innovation ; 2024.
    2. Zurui Ao; Xiaomei Hu; Shengli Tao*; Zhenzhong Zeng; Hydrological shifts
    threaten water security; Nature Water ; 2024.
    """

    publications = _extract(text)

    assert len(publications) >= 2
    assert any(
        publication.clean_title
        == "Extreme climate sparks record boreal wildfires and carbon surge in 2023"
        for publication in publications
    )


def test_sustech_plain_text_academic_outputs_label_extracts_journal_articles():
    text = """
    学术成果（发表论著或者论文） ：
    期刊文章（一作/通讯）
    1. Shen, H.Z., Shen, G.F.*, Chen, Y.L., Russell, A.G., Hu, Y.T., Duan, X.L.,
    Meng, W.J., Xu, Y., Yun, X., Lyu, B.L., Zhao, S.L., Hakami, A., Tao, S.,
    Smith, K.R., 2021. Increased air pollution exposure among the Chinese
    population during the national quarantine in 2020. Nature Human Behaviour,
    DOI: 10.1038/s41562-020-01018-z.
    2. Shen, H.Z., Hou, W.Y., Zhu, Y.Q., Zheng, S.X., Ainiwaer, S., Shen, G.F.,
    Chen, Y.L., Cheng, H.F., Hu, J.Y., Tao, S.*, 2021. Temporal and spatial
    variation of PM2.5 in indoor air monitored by low-cost sensors. Science of
    The Total Environment, 770: 145304.
    """

    publications = _extract(text)

    assert [publication.clean_title for publication in publications] == [
        "Increased air pollution exposure among the Chinese population during "
        "the national quarantine in 2020",
        "Temporal and spatial variation of PM2.5 in indoor air monitored by "
        "low-cost sensors",
    ]


def test_sustech_plain_text_profile_raw_text_publication_labels_extract_items():
    text = """
    研究领域 机器人视觉感知与控制、燃料电池系统控制与健康管理。
    发表文章
    1. J. Chen, Q. Ouyang, and Z. Wang, Equalization Control for Lithium-Ion
    Batteries, Singapore, Springer, 2023.
    2. P. Jiang, J. Chen*, L. Jin, and L. Kumar, “Adaptive Condition Monitoring
    for Fuel Cells Based on Fast EIS and Two-Frequency Impedance Measurements,”
    IEEE Transactions on Industrial Electronics, vol. 70, no. 8, pp. 8517-8525,
    August 2023.
    主要科研项目：
    国家自然科学基金项目。
    """

    publications = extract_publications_from_html(
        text,
        page_url="https://www.sustech.edu.cn/zh/faculties/jianchen.html",
    )

    assert [
        publication.clean_title for publication in publications
    ] == [
        "Equalization Control for Lithium-Ion Batteries",
        (
            "Adaptive Condition Monitoring for Fuel Cells Based on Fast EIS and "
            "Two-Frequency Impedance Measurements"
        ),
    ]


def test_sustech_plain_text_profile_raw_text_representative_articles_extract_items():
    text = """
    代表文章：
    加入南科大之后
    1. Hongji Pan, Tiantian Wang, Yanxin Jiang, Jingjing Ouyang, Lu Chen,
    Zeyi Wang, Yiju Li*, Revisiting Fluorobenzene as Diluents in Ether-Based
    Electrolytes for Lithium Metal Batteries, Nature Communications, 2025, 16, 9813.
    2. Xudong Peng, Yang Zhang, Qiyu Wang, Lu Chen, Yiju Li*, A scalable and
    long-cycle-life 600 Wh kg-1 solid-state lithium metal pouch cell, Nature
    Communications, 2025, https://doi.org/10.1038/s41467-025-66866-7.
    所获荣誉：
    全球高被引科学家。
    """

    publications = extract_publications_from_html(
        text,
        page_url="https://www.sustech.edu.cn/zh/faculties/llyiju.html",
    )

    assert [
        publication.clean_title for publication in publications
    ] == [
        "Revisiting Fluorobenzene as Diluents in Ether-Based Electrolytes for Lithium Metal Batteries",
        "A scalable and long-cycle-life 600 Wh kg-1 solid-state lithium metal pouch cell",
    ]


def test_sustech_plain_text_profile_raw_text_skips_publication_section_summary():
    text = """
    论文及专利 Publications
    A-1. Journal articles (All articles were peer-reviewed) Summary: A total of
    >120 peer-reviewed articles, including two papers in PNAS and one in Science.
    Total citations >4410, H index = 37 (Google Scholar as of February 26, 2016).
    2016 Special issue in Science China-Earth Sciences
    Ge H., Zhang* C. L. 2016. Advances in GDGT research in Chinese marginal seas:
    A review. Science China-Earth Sciences. doi: 10.1007/s11430-015-5242-z.
    """

    publications = extract_publications_from_html(
        text,
        page_url="https://www.sustech.edu.cn/zh/faculties/zhangchuanlun.html",
    )

    titles = [publication.clean_title for publication in publications]
    assert all("peer-reviewed articles" not in title for title in titles)
    assert "Advances in GDGT research in Chinese marginal seas: A review" in titles


def test_embedded_vocab_in_body_copy_is_not_a_heading():
    html = """
    <html><body>
      <div>
        <p>本团队近年发表论文50余篇，主持多个科研项目，研究成果服务产业。</p>
        <p>联系方式：teacher@example.edu</p>
      </div>
    </body></html>
    """

    assert _extract(html) == []


def test_specific_paper_subheading_overrides_general_academic_results_noise():
    html = """
    <html><body>
      <div class="item">
        <h3 class="tit">学术成果</h3>
        <div class="desc">
          <p>国际影响力：国际期刊《Knowledge-Based Systems》副主编。</p>
          <p>所获荣誉：获辽宁省自然科学三等奖，青岛市政府科学技术进步一等奖。</p>
          <p>近年发表的主要学术论文 (Selected Journal Papers)：</p>
          <p>1.Xiang Lv, Mingwen Shao*, SUV: Suppressing Undesired Video
          Content via Semantic Modulation Based on Text Embeddings, ICCV
          2025, accepted.</p>
          <p>2.Qiao Zhang, Mingwen Shao*, Wave-MambaAD: Wavelet-driven State
          Space Model for Multi-class Unsupervised Anomaly Detection, ICCV
          2025, accepted.</p>
        </div>
      </div>
    </body></html>
    """

    publications = _extract(html)

    assert [pub.clean_title for pub in publications] == [
        "SUV: Suppressing Undesired Video Content via Semantic Modulation "
        "Based on Text Embeddings",
        "Wave-MambaAD: Wavelet-driven State Space Model for Multi-class "
        "Unsupervised Anomaly Detection",
    ]


def test_swyxgcxy_prefetched_sample_still_extracts_papers():
    html = (_RUN_FIXTURE_DIR / "PROF-2E2F7D86A756.html").read_text(encoding="utf-8")

    publications = extract_publications_from_html(
        html,
        page_url="file://PROF-2E2F7D86A756.html",
    )

    assert len(publications) >= 5


def test_glued_page_range_and_next_numbered_item_are_split():
    html = """
    <html><body>
      <main>
        <h2>Publications</h2>
        <p>1. Emily M Teichman, Jianping Hu, Ming-Hu Han. Design and validation
        of novel brain-penetrant HCN channel inhibitors to ameliorate social
        stress-induced susceptible phenotype, Molecular Psychiatry, Apr 8;
        1-142. Laurel S Morris, Sara Costi, Ming-Hu Han. Effects of KCNQ
        potassium channel modulation on ventral tegmental area activity and
        connectivity in individuals with depression and anhedonia, Molecular
        Psychiatry, 2025 Mar 25; 1-93. Min Cai, Yingbo Zhu, Ming-Hu Han. HCN
        channel inhibitor induces ketamine-like rapid and sustained
        antidepressant effects in chronic social defeat stress model,
        Neurobiology of Stress, 2023 Sep 1; 26, 100565</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://minghuHanLab.lhs.suat-sz.edu.cn/hmh/col98/list",
    )

    assert [publication.clean_title for publication in publications] == [
        "Design and validation of novel brain-penetrant HCN channel inhibitors "
        "to ameliorate social stress-induced susceptible phenotype",
        "Effects of KCNQ potassium channel modulation on ventral tegmental area "
        "activity and connectivity in individuals with depression and anhedonia",
        "HCN channel inhibitor induces ketamine-like rapid and sustained "
        "antidepressant effects in chronic social defeat stress model",
    ]


def test_cmce_teacher_bottom_tc_cont_label_keeps_publication_entries():
    html = """
    <html><body>
      <div class="teacher-bottom pos16">
        <p class="tc-title">代表期刊论文 ：</p>
        <p class="tc-cont">第一或通信作者：<br/>
        2023<br/>
        [1]Wang C, Liu J, Hong Y, and Pan J. Design of a Fuzzy-based Adaptive
        Gain Filter for PMSM Servo Systems with Maneuverability[J]. IEEE
        Transactions on Industrial Informatics, 2023, 19(9): 9394-9403.<br/>
        [2]Wang, C; Liu, FF; Xu, JC; Pan, JF. A SMC-based Accurate and Robust
        Load Speed Control Method for Elastic Servo System[J]. IEEE
        Transactions on Industrial Electronics, 2023, 71(3), 2300-2308, 2024.
        </p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmce.szu.edu.cn/info/1427/3775.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Design of a Fuzzy-based Adaptive Gain Filter for PMSM Servo Systems "
        "with Maneuverability",
        "A SMC-based Accurate and Robust Load Speed Control Method for Elastic "
        "Servo System",
    ]
    assert "Wang C" in (publications[0].authors_text or "")
    assert "IEEE Transactions on Industrial Informatics" in (
        publications[0].venue_text or ""
    )
    assert publications[0].year == 2023


def test_cmce_fullwidth_parenthesized_numbered_entries_are_split():
    html = """
    <html><body>
      <div class="teacher-bottom pos16">
        <p class="tc-title">代表期刊论文 ：</p>
        <p class="tc-cont">
        （1）Yujian Li, Yan Liu, Yangguang Zhan, Yu Zhang, Zhenxuan Zhang*,
        Xiong Liang*, Jiang Ma*, Peracetic acid-induced nanoengineering of
        Fe-based metallic glass ribbon in application of efficient drinking
        water treatment. Applied Catalysis B: Environment and Energy, 2024,
        355: 124161.
        （2）Libo Zhang, Lianxiang Qiu, Qingyao Zhu, Xiong Liang, Jiang Ma*,
        Jun Shen, Insight into efficient degradation of 3,5-dichlorosalicylic
        acid by Fe-Si-B amorphous ribbon under neutral condition. Applied
        Catalysis B: Environmental, 2021, 294: 120258.
        </p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmce.szu.edu.cn/info/1611/4384.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Peracetic acid-induced nanoengineering of Fe-based metallic glass "
        "ribbon in application of efficient drinking water treatment",
        "Insight into efficient degradation of 3, 5-dichlorosalicylic acid by "
        "Fe-Si-B amorphous ribbon under neutral condition",
    ]
    assert "Applied Catalysis B" in (publications[0].venue_text or "")
    assert publications[0].year == 2024


def test_cmce_bracketed_entries_split_after_chinese_author_role_suffix():
    html = """
    <html><body>
      <div class="teacher-bottom pos16">
        <p class="tc-title">代表期刊论文 ：</p>
        <p class="tc-cont">
        [1]Structural Health Monitoring of Large Scale Geomembrane Floating
        Covers Using Solar Energy， IEEE Sensors Journal（IF 4.325，JCR一区，
        中科院二区top），第一作者
        [2]Quasi-active Thermal Imaging of Large Floating Covers Using Ambient
        Solar Energy， Remote Sensing (IF 5.349， JCR一区，中科院二区top），第一作者
        </p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmce.szu.edu.cn/info/1431/4790.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Structural Health Monitoring of Large Scale Geomembrane Floating "
        "Covers Using Solar Energy",
        "Quasi-active Thermal Imaging of Large Floating Covers Using Ambient "
        "Solar Energy",
    ]
    assert "IEEE Sensors Journal" in (publications[0].venue_text or "")


def test_szu_tab_navigation_representative_outputs_is_not_publication_section():
    html = """
    <html><body>
      <div class="qieh">
        <div class="sy-tzgg-title">
          基本信息 研究方向 代表论著 科研项目 荣誉获奖
        </div>
        <div class="sy-tzgg-con">
          <p>庄华鹭，主要从事热电材料研究。累计发表SCI论文40余篇。</p>
          <p>学习&工作简历</p>
          <p>2022.09-2024.12，清华大学，材料学院，博士后（导师：李敬锋 教授）</p>
          <p>2017.09-2022.06，清华大学，材料学院，博士（导师：李敬锋 教授）</p>
          <p>联系方式</p>
          <p>地址：广东省深圳市南山区学苑大道1066号深圳大学材料学院B2-307</p>
          <p>电话：0755-89837297</p>
          <p>邮箱：hualu@szu.edu.cn</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/j_s_zljs/zhl.htm",
    )

    assert publications == []


def test_szu_body_publication_heading_after_tabs_still_extracts_publications():
    html = """
    <html><body>
      <div class="qieh">
        <div class="sy-tzgg-title">
          基本信息 研究方向 代表论著 科研项目 荣誉获奖
        </div>
        <div class="sy-tzgg-con">
          <p>研究方向：半导体材料。</p>
        </div>
      </div>
      <div id="vsb_content">
        <p><strong><span>发表论文</span></strong></p>
        <p>(1) Yongyong Che; Keyuan Ding*; Low-damage dry etching process
        for ultrawide bandgap semiconductors, Applied Physics Letters, 2025,
        126: 182102.</p>
        <p>(2) Hao Liu; Keyuan Ding; Electronic excitation-induced ultrafast
        defect recovery in gallium oxide, Chemistry of Materials, 2023, 35:
        6396-6404.</p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/j_s/dky.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Low-damage dry etching process for ultrawide bandgap semiconductors",
        "Electronic excitation-induced ultrafast defect recovery in gallium oxide",
    ]


def test_szu_tab_container_extracts_bracketed_representative_publications():
    html = """
    <html><body>
      <div class="qieh">
        <div class="sy-tzgg-title">
          基本信息 研究方向 代表论著 科研项目 荣誉获奖
        </div>
        <div class="sy-tzgg-con">
          <p>林菁菁，深圳大学助理教授。以独立第一作者身份在
          Nano Energy、Chem. Eng. J.、Small 等国际权威期刊发表论文
          10余篇，主持国家自然科学基金青年项目。</p>
          <p>学习经历：2017.11-2022.03 德国亚琛工业大学博士。</p>
          <p>工作经历：2022.09-2026.01 深圳大学材料学院博士后。</p>
          <p>高温质子交换膜燃料电池关键与新型材料研发。</p>
          <p>[1] J. Lin, J. Huang, L. Wang* and X. Peng.
          Synergistic Proton and Oxygen Transport Optimization via Binder
          Engineering for High-Efficiency ORR in High-Temperature Fuel Cell.
          Nano Energy, 142, Part A (2025) 111205.</p>
          <p>[2] J. Lin, P. Wang, X. Peng. An imidazole-philic dispersible
          ionic liquid provides ample proton transport channels for high
          temperature proton exchange membranes. Chemical Engineering Journal,
          475 (2023): 146146.</p>
          <p>国家自然科学基金青年科学基金项目，30万元。</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/gfzclygc/j_s2/ljj.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Synergistic Proton and Oxygen Transport Optimization via Binder "
            "Engineering for High-Efficiency ORR in High-Temperature Fuel Cell"
        ),
        (
            "An imidazole-philic dispersible ionic liquid provides ample proton "
            "transport channels for high temperature proton exchange membranes"
        ),
    ]
    assert all("发表论文 10余篇" not in publication.raw_title for publication in publications)
    assert all("国家自然科学基金" not in publication.raw_title for publication in publications)


def test_szu_chem_non_heading_publication_section_includes_labeled_year_blocks():
    html = """
    <html><body>
      <div class="sy-tzgg-con">
        <div class="ny_about">
          <p><span>专利：</span></p>
          <p>1. 一种锌空电池的负极及其制备方法和应用，中国发明专利。</p>
        </div>
        <div class="ny_about">
        </div>
        <div class="ny_about">
          <p><span>学术论文：</span></p>
        <p>第一作者及通讯作者</p>
        <p>2026 年</p>
        <p>1. Xiongwei Zhong, Jie Li, and Ming Chen. Visible-light-driven
        catalytic conversion over defect-rich oxide nanosheets. Applied
        Catalysis B: Environmental, 2026, 351: 124321.</p>
        <p>2. Xiongwei Zhong, Rui Wang. Interfacial charge transfer in
        two-dimensional photocatalysts. Chemical Engineering Journal, 2026,
        498: 155432.</p>
        <p>2025 年以前</p>
        <p>研究项目：</p>
        <p>国家自然科学基金面上项目，主持。</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/zljs/zxw.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Visible-light-driven catalytic conversion over defect-rich oxide nanosheets",
        "Interfacial charge transfer in two-dimensional photocatalysts",
    ]
    assert all("2026 年" not in publication.clean_title for publication in publications)
    assert all("2025 年以前" not in publication.clean_title for publication in publications)
    assert all("研究项目" not in publication.raw_title for publication in publications)


def test_szu_material_quoted_title_keeps_title_before_venue_metadata():
    html = """
    <html><body>
      <div class="qieh">
        <div class="sy-tzgg-title">基本信息 代表论著 科研项目</div>
        <div class="sy-tzgg-con">
          <p>[8] J. Lin, P. Wang and X. Peng. "PBI-type membranes with
          fluorinated side chains for high temperature fuel cells." Fuel cells
          20.4 (2020): 461-468.</p>
          <p>国家自然科学基金青年科学基金项目，30万元。</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/gfzclygc/j_s2/ljj.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "PBI-type membranes with fluorinated side chains for high temperature fuel cells"
    ]
    assert "Fuel cells 20.4" in (publications[0].venue_text or "")


def test_szu_material_metric_tail_fragments_are_not_publication_titles():
    html = """
    <html><body>
      <div class="qieh">
        <div class="sy-tzgg-title">基本信息 代表论著 科研项目</div>
        <div class="sy-tzgg-con">
          <p>[1] Lipeng Hu, Ming Fang. Stable high-entropy alloy catalysts for
          oxygen evolution. Advanced Functional Materials, 2024, 34: 2403136.
          中科院大类 1 区， IF = 15.7.</p>
          <p>[3] Shan Li, # Xingce Fang, # Tu Lyu, Jiahui Cheng, Weiqin Ao,
          Chaohua Zhang, Fusheng Liu, Junqin Li, and Lipeng Hu, * Antisite
          defect manipulation enables the high thermoelectric performance of
          p-type Bi2-xSbxTe3 alloys for solid-state refrigeration, Materials
          Today Physics, 2022, 27, 100764. (IF = 11.021)</p>
          <p>[2] Lipeng Hu, Yongping Zheng. Interface engineering in layered
          cathodes. Energy Storage Materials, 2023, 61: 102945.</p>
          <p>3136. 中科院大类 1 区， IF = 15.7</p>
          <p>2503918. 中科院大类 1 区， IF = 26.8 （ NI 杂志） 2024 年：</p>
          <p>66(2), 696-706. 中科院大类 2 区， IF = 6.8</p>
        </div>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/fjs/hlp.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Stable high-entropy alloy catalysts for oxygen evolution",
        (
            "Antisite defect manipulation enables the high thermoelectric "
            "performance of p-type Bi2-xSbxTe3 alloys for solid-state "
            "refrigeration"
        ),
        "Interface engineering in layered cathodes",
    ]
    assert all("中科院大类" not in publication.clean_title for publication in publications)
    assert all("IF =" not in publication.clean_title for publication in publications)


def test_szu_comma_author_chain_without_period_reaches_real_title():
    html = """
    <html><body>
      <main>
        <h2>代表性论文</h2>
        <p>2. Xin Guan and To Ngai*, pH-Sensitive W/O Pickering High Internal
        Phase Emulsions and W/O/W High Internal Water-Phase Double Emulsions
        with Tailored Microstructures Co-Stabilized by Lecithin and Silica
        Inorganic Particles, Langmuir, 2021, 37, 2843-2854. (Cover)</p>
        <p>2. Dong Liu, Dan tao, Jiangpeng Ni, Xiongzhi Xiang, Lei wang*,
        Jingyu Xi, Synthesis and properties of highly branched sulfonated
        poly(arylene ether)s with flexible alkylsulfonated side chains as
        proton exchange membranes, Journal of Materials Chemistry C, 2016,
        6(4): 1326-1335. IF: 6.641 (JCR1)</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/zljs/gx.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "pH-Sensitive W/O Pickering High Internal Phase Emulsions and W/O/W "
            "High Internal Water-Phase Double Emulsions with Tailored "
            "Microstructures Co-Stabilized by Lecithin and Silica Inorganic "
            "Particles"
        ),
        (
            "Synthesis and properties of highly branched sulfonated "
            "poly(arylene ether)s with flexible alkylsulfonated side chains as "
            "proton exchange membranes"
        ),
    ]
    assert publications[0].authors_text == "Xin Guan, To Ngai"
    assert "Lei wang" in (publications[1].authors_text or "")
    assert "Journal of Materials Chemistry C" in (publications[1].venue_text or "")


def test_szu_comma_author_chain_with_affiliation_letters_keeps_title_commas():
    html = """
    <html><body>
      <main>
        <h2>Representative publications</h2>
        <p>Jianfeng Ban,a Luona Mu,a Jinghao Yang,a Shaojun Chen *a and Haitao
        Zhuo*, New stimulus-responsive shape-memory polyurethanes capable of UV
        light-triggered deformation, hydrogen bond-mediated fixation,and
        thermal-induced recovery, J. Mater. Chem. A, 2017, 5, 14514-14518.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/gfzclygc/j_s/csj.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "New stimulus-responsive shape-memory polyurethanes capable of UV "
            "light-triggered deformation, hydrogen bond-mediated fixation, and "
            "thermal-induced recovery"
        )
    ]
    assert publications[0].authors_text == (
        "Jianfeng Ban, Luona Mu, Jinghao Yang, Shaojun Chen, Haitao Zhuo"
    )
    assert "J. Mater. Chem. A" in (publications[0].venue_text or "")


def test_szu_glued_numbered_entries_split_after_citation_tail():
    html = """
    <html><body>
      <main>
        <h2>代表性论文</h2>
        <p>4. Decai Zhao, Nailiang Yang, Yan Wei Quan Jin, Yanlei Wang,
        Hongyan He, Yang Yang, Bing Han, Suojiang Zhang*, Dan Wang* ；
        Sequential drug release via chemical diffusion and physical barriers
        enabled by hollow multishelled structures; Nature Communications,
        2020, 11, 4450. 5 Yanze Wei, Jiawei Wan, Nailiang Yang, Yu Yang,
        Yanwen Ma, Songcan Wang, Jiangyan Wang, Ranbo Yu, Lin Gu, Lianhui
        Wang, Lianzhou Wang, Wei Huang*, Dan Wang* ； Efficient sequential
        harvesting of solar light by heterogeneous hollow shells with
        hierarchical pores. National Science Review, 2020, 7, 1638.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/tpjs/wd.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Sequential drug release via chemical diffusion and physical "
            "barriers enabled by hollow multishelled structures"
        ),
        (
            "Efficient sequential harvesting of solar light by heterogeneous "
            "hollow shells with hierarchical pores"
        ),
    ]
    assert publications[0].venue_text == "Nature Communications, 2020, 11, 4450"
    assert publications[1].venue_text == "National Science Review, 2020, 7, 1638"


def test_szu_numbered_entry_without_period_starts_new_paragraph():
    html = """
    <html><body>
      <main>
        <h2>代表性论文</h2>
        <p>4. Decai Zhao, Nailiang Yang, Yan Wei Quan Jin, Yanlei Wang,
        Hongyan He, Yang Yang, Bing Han, Suojiang Zhang*, Dan Wang* ；
        Sequential drug release via chemical diffusion and physical barriers
        enabled by hollow multishelled structures; Nature Communications,
        2020, 11, 4450.</p>
        <p>5 Yanze Wei, Jiawei Wan, Nailiang Yang, Yu Yang, Yanwen Ma,
        Songcan Wang, Jiangyan Wang, Ranbo Yu, Lin Gu, Lianhui Wang,
        Lianzhou Wang, Wei Huang*, Dan Wang* ； Efficient sequential
        harvesting of solar light by heterogeneous hollow shells with
        hierarchical pores. National Science Review, 2020, 7, 1638.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/tpjs/wd.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Sequential drug release via chemical diffusion and physical "
            "barriers enabled by hollow multishelled structures"
        ),
        (
            "Efficient sequential harvesting of solar light by heterogeneous "
            "hollow shells with hierarchical pores"
        ),
    ]
    assert publications[0].venue_text == "Nature Communications, 2020, 11, 4450"
    assert publications[1].venue_text == "National Science Review, 2020, 7, 1638"


def test_szu_connective_author_pair_fragment_repairs_title_from_venue_tail():
    html = """
    <html><body>
      <main>
        <h2>代表性论文</h2>
        <p>7. Xin Guan , Jingjing Wei*, Yufei Xia and To Ngai*.
        Raspberry-shaped Microgels with Tunable Morphology and
        Thermoresponsive Properties. ACS Macro Lett., 2022, 11, 123-130.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/js/gx.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Raspberry-shaped Microgels with Tunable Morphology and "
            "Thermoresponsive Properties"
        )
    ]
    assert publications[0].authors_text == "Xin Guan, Jingjing Wei, Yufei Xia, To Ngai"
    assert publications[0].venue_text == "ACS Macro Lett., 2022, 11, 123-130"


def test_szu_bracketed_full_name_author_alias_is_not_title_prefix():
    html = """
    <html><body>
      <main>
        <h2>Representative publications</h2>
        <p>[ 15 ] B. J. Huang #, K. Wang #, J. C. Zhang, H. W. Yan, H.
        Zhao, L. Han* 【Baojian Huang #, Kang Wang #, Jinchuan Zhang, Hewei
        Yan, Hui Zhao, Lei Han*, Ting Han*, and Ben Zhong Tang*】, Targeted
        and long-term fluorescence imaging of plant cytomembranes using
        main-chain charged polyelectrolytes with aggregation-induced emission,
        ACS Appl. Mater. Interfaces, 2024, 16 (16), 20011-20022.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/gfzclygc/fzr/ht.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Targeted and long-term fluorescence imaging of plant cytomembranes "
            "using main-chain charged polyelectrolytes with aggregation-induced "
            "emission"
        )
    ]
    assert publications[0].authors_text == (
        "B. J. Huang, K. Wang, J. C. Zhang, H. W. Yan, H. Zhao, L. Han"
    )
    assert "ACS Appl. Mater. Interfaces" in (publications[0].venue_text or "")


def test_szu_venue_only_citation_without_title_is_rejected():
    html = """
    <html><body>
      <main>
        <h2>代表性论文</h2>
        <p>6. C. Wang #, Q. Qiao#, W. Chi, J. Chen, W. Liu, D. Tan,
        S. McKechnie, D. Lyu, X.-F. Jiang, W. Zhou, N. Xu, Q. Zhang,
        Z. Xu*, X. Liu*, Angew. Chem. Int. Ed., 2020, 59, 10160-10172
        (ESI Highly Cited Paper)</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/gfzclygc/j_s2/wc.htm",
    )

    assert publications == []


def test_szu_aggregate_publication_prose_does_not_count_as_section():
    html = """
    <html><body>
      <main>
        <h2>论文</h2>
        <p>发表科研论文20余篇，SCI论文10余篇，总引用超过2600次，
        授权发明专利5项。</p>
      </main>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/zljs/zt.htm",
    )

    assert result.publications == []
    assert result.sections_detected == 0
    assert result.heading_texts == ()


def test_szu_empty_publication_heading_does_not_count_as_section():
    html = """
    <html><body>
      <main>
        <h2>论文</h2>
        <p>论文：</p>
      </main>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/zljs/zt.htm",
    )

    assert result.publications == []
    assert result.sections_detected == 0
    assert result.heading_texts == ()


def test_szu_inline_research_outputs_sentence_is_not_publication_heading():
    html = """
    <html><body>
      <main>
        <p>近三年，课题组主要研究成果均发表在Nature Communications、
        Advanced Materials等期刊上。</p>
      </main>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/fjs/lyz.htm",
    )

    assert result.publications == []
    assert result.sections_detected == 0
    assert result.heading_texts == ()


def test_szu_titleless_venue_line_is_rejected():
    html = """
    <html><body>
      <main>
        <h2>部分代表性论文</h2>
        <p>W-M Kwok, Chem. Sci., 2015, 6, 4623-4635.</p>
      </main>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/js/mcs.htm",
    )

    assert publications == []


def test_szu_titleless_venue_section_does_not_count_as_actionable_section():
    html = """
    <html><body>
      <main>
        <h2>部分代表性论文</h2>
        <p>· C. Ma *, J. C.-L. Chow, A. K.-W. Wong, Q. Xiong,
        J. Chomchoei, W.-M. Kwok*, J. Phys. Chem. Lett. 2023,
        14, 5085-5094.</p>
        <p>· R. Chan, C. Chan, C. Ma* , K. Gu, H. Xie, A. Wong,
        Q. Xiong, M. Wang, W.-M. Kwok*, Phys. Chem. Chem. Phys.
        2021, 23, 6472-6480.</p>
      </main>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/js/mcs.htm",
    )

    assert result.publications == []
    assert result.sections_detected == 0
    assert result.heading_texts == ()


def test_szu_prose_only_publication_count_does_not_create_papers():
    html = """
    <html><body>
      <div id="vsb_content">
        <p>目前主要从事高分子材料研究，发表论文70余篇，授权发明专利10项。</p>
        <p>Google Scholar: https://scholar.google.com/citations?user=example</p>
      </div>
    </body></html>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/fjs/zyp.htm",
    )

    assert publications == []


def test_szu_navigation_academic_outputs_menu_does_not_create_publication():
    raw_text = (
        "学院新闻 通知公告 学院介绍 学术科研 学术活动 学术成果 "
        "科研动态 科研平台 实验室安全 本科生培养 招生信息 师资队伍 "
        "专业教师 化学系 环境工程系 荣休教师 吴玥 职称：特聘教授 "
        "办公电话：0755-86937276 EMAIL：wuyue@szu.edu.cn 基本信息 "
        "吴玥，男，特聘教授、博士生导师，国家青年科学基金B类获得者"
        "（2025年），《中国科学·材料科学》新锐科学家（2025年），"
        "深圳市高层次人才（2019年）， Science China - Chemistry 、 "
        "Smart Molecules 期刊青年编委。 Yue Wu, Distinguished Professor, "
        "NSFC Excellent Young Scholar (2025), Science China-Materials "
        "Emerging Investigator (2025), Shenzhen High-Level Talent (2019), "
        "Youth Editorial Board Member for Science China-Chemistry and "
        "Smart Molecules (Wiley)."
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/tpjs/wy.htm",
    )

    assert publications == []


def test_szu_publication_count_hindex_profile_tail_is_not_publication():
    raw_text = (
        "发表学术论文 40 篇。 H-index 24 。 教育背景： 2015.09 – "
        "2021-08 厦门大学，物理化学，理学博士 导师：谢兆雄教授 "
        "2019.09 – 2021.08 美国 Cornell University，国家公派联合培养 "
        "导师： Héctor D. Abruña 院士 2011.09 – 2015.06 黑龙江大学，"
        "材料化学，工学学士 工作背景： 2025.01 – 至今 深圳大学，助理教授 "
        "2021.09 – 2024.08 美国 Cornell University，博士后研究员 合作导师： "
        "Héctor D. Abruña 院士"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/zljs/lhq.htm",
    )

    assert publications == []


def test_szu_split_publication_count_spans_do_not_count_as_section():
    html = """
    <html><body>
      <main>
        <span>论文</span><span>33</span><span>篇，其中以第一作者或通讯作者在</span>
      </main>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/fjs/fhl.htm",
    )

    assert result.publications == []
    assert result.sections_detected == 0
    assert result.heading_texts == ()


def test_szu_publication_count_footer_tail_is_not_publication():
    raw_text = (
        "发表论文 700 多篇，专利 180 多项，专著 8 部， SCI 引用 3 万多次，"
        "H=87，GoogleScholar 引用 4 万多次，H=104，30 多项全球技术产业化，"
        "在 100 多个国家使用。 E-mail：zhangxueji@szu.edu.cn 联系我们 地址："
        "深圳市南山区学苑大道1066号 深圳大学化学与环境工程学院 邮编：518071 "
        "电话：0755-26536141 关于我们 深圳大学化学与环境工程学院是理工类综合学院，"
        "成立于2006年8月。"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="https://chem.szu.edu.cn/szdw/zyjs/hxx/tpjs/zxj.htm",
    )

    assert publications == []


def test_szu_bigdata_footer_navigation_tail_is_not_publication():
    raw_text = (
        "人才培养对外合作文化建设招贤纳士版权所有© 2013-2020："
        "深圳大学南校区计算机与软件学院粤ICP备12345号分享关注官微"
        "更多大数据内容 0755-26530821 23123122"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="https://bigdata.szu.edu.cn/kycg/lwfb.htm",
    )

    assert publications == []
    assert publication_parser._is_non_publication_title_noise(raw_text)
    assert not publication_parser._is_non_publication_title_noise(
        "人才培养不能一味强调竞争"
    )


def test_szu_bigdata_cms_time_source_fragments_are_not_publications():
    for raw_text in (
        "2415:44:46 来源",
        "0417:00:59 来源",
        "2216:55:18 来源",
        "3110:34:22 来源：系统管理员",
    ):
        publications = extract_publications_from_html(
            raw_text,
            page_url="https://bigdata.szu.edu.cn/info/1016/1312.htm",
        )

        assert publications == []
        assert publication_parser._is_non_publication_title_noise(raw_text)


def test_plain_text_signal_skips_expensive_citation_check_without_profile_tail(
    monkeypatch,
):
    calls = 0

    def fake_standalone_citation(text: str) -> bool:
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(
        publication_parser,
        "_looks_like_standalone_publication_citation",
        fake_standalone_citation,
    )

    assert publication_parser._plain_text_publication_entry_has_signal(
        "Yanze Wei, Dandan Wang, Qiang Zhang. High entropy materials for "
        "efficient catalysis. Advanced Materials, 2024, 36, 2400001."
    )
    assert calls == 0


def test_sztu_seed47_partial_publications_raw_text_splits_and_stops_before_projects():
    raw_text = (
        "深圳技术大学 创意设计学院 教师简介 "
        "部分发表论著 "
        "1.《服务设计概论》，机械工业出版社，2022年。 "
        "2.《工业设计史》，高等教育出版社，2021年。 "
        "3. 用户体验驱动的智能产品设计方法研究，包装工程，2020年。 "
        "4. 面向城市家具的公共服务系统设计研究，装饰，2019年。 "
        "5. The Design Strategy for Community Health Service Touchpoints, "
        "Design Journal, 2018. "
        "部分课题项目 "
        "1. 深圳市哲学社会科学规划课题，主持，2023年。 "
        "2. 广东省教育厅创新团队项目，参与，2022年。"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://SZTU-SEED47-DESIGN",
    )

    assert [publication.clean_title for publication in publications] == [
        "《服务设计概论》",
        "《工业设计史》",
        "用户体验驱动的智能产品设计方法研究",
        "面向城市家具的公共服务系统设计研究",
        "The Design Strategy for Community Health Service Touchpoints",
    ]
    assert all("部分课题项目" not in publication.raw_title for publication in publications)
    assert all("哲学社会科学" not in (publication.venue_text or "") for publication in publications)


def test_sztu_seed47_profile_publication_count_tail_is_not_a_publication():
    raw_text = (
        "文雅玉 辅导员 "
        "中共党员，暨南大学理学硕士学位，作为第一作者曾分别在 "
        "ACS Applied Materials & Interfaces, Nanoscale, Journal of Materials "
        "Chemistry B 和Nanotechnology期刊发表 SCI 收录论文 4 篇，"
        "2019年9月- 2020年1月任广州航海学院大学化学兼职讲师。"
        "2020年9月至今任创意设计学院辅导员。 wenyayu@sztu.edu.cn"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://SZTU-SEED47-DESIGN",
    )

    assert publications == []


def test_sztu_seed47_inline_quoted_journal_paper_is_extracted():
    raw_text = (
        "权梓子 实验教师 "
        "研究方向为美术学，论文“浅析当代艺术语境下的超级写实主义的现状问题”"
        "发表于《金田》2014年第12月刊。"
        "2015年硕士学位论文为《当代艺术语境下“调节性理念”的意义》。"
    )

    publications = extract_publications_from_html(
        raw_text,
        page_url="profile_raw_text://SZTU-SEED47-DESIGN",
    )

    assert [publication.clean_title for publication in publications] == [
        "浅析当代艺术语境下的超级写实主义的现状问题"
    ]
    assert publications[0].venue_text == "金田"
    assert publications[0].year == 2014


def test_sztu_sgim_bracketed_research_paper_heading_extracts_items():
    html = """
    <html><body>
      <div class="v_news_content">
        <p><span>【</span><span>科研论文</span><span>】</span></p>
        <p><span>[1] </span><strong><span>Zhan W.</span></strong><span>,
        Fang Y., Huang P. Numerical solution of dry friction in point contact
        using the unified Reynolds method combined with rarefied gas effect [J].
        Proceedings of the Institution of Mechanical Engineers, Part J: Journal
        of Engineering Tribology, 2024, 238 (2): 211-223.</span></p>
        <p><span>[2] </span><strong><span>占旺龙</span></strong><span>,
        李春波. 材料力学弯曲变形问题集中量处理方法 [J]. 力学与实践,
        2024, 46 (4): 863-867.</span></p>
        <p><span>[3] </span><strong><span>占旺龙</span></strong><span>,
        方燕飞. 点的复合运动中任意相切型问题速度分析的一种特殊解法 [J].
        力学与实践, 2023, 45 (6): 1280-1284.</span></p>
        <p><span>【</span><span>科研项目</span><span>】</span></p>
        <p>主持深圳市项目一项。</p>
      </div>
    </body></html>
    """

    result = extract_publications_with_diagnostics_from_html(
        html,
        page_url="https://sgim.sztu.edu.cn/info/1273/4155.htm",
    )

    titles = [publication.clean_title for publication in result.publications]
    assert result.sections_detected == 1
    assert titles == [
        "Numerical solution of dry friction in point contact using the unified Reynolds method combined with rarefied gas effect",
        "材料力学弯曲变形问题集中量处理方法",
        "点的复合运动中任意相切型问题速度分析的一种特殊解法",
    ]
