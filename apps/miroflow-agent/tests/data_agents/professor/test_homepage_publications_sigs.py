from __future__ import annotations

from src.data_agents.professor.homepage_publications import (
    HomepagePublication,
    _is_suspicious_rule_publication,
    _split_title_authors_venue,
    build_llm_publication_extraction_messages,
    extract_publications_from_html_with_llm_fallback,
    extract_publications_from_html,
)


AHMED_FIRST_PUBLICATION = (
    "1- M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab*. "
    "Robust attention transfer neural networks for diagnosis of Alzheimer's "
    "disease from structural magnetic resonance images, Engineering "
    "Applications of Artificial Intelligence, 164, 113260, 2026 (IF= 8.0, Q1)."
)

AHMED_AUTHOR_CONTINUATION_PUBLICATIONS = [
    (
        "3- X. Yu#, A. Elazab#, R. Ge, J. Zhu, L. Zhang, G. Jia, Q. Wu, "
        "X. Wan, L. Li, and C. Wang. ICH-PRNet: A cross-modal intracerebral "
        "haemorrhage prognostic prediction method using joint-attention "
        "interaction mechanism, Neural Networks, 184, 107096, 2025 (IF= 6.0, Q1).",
        "ICH-PRNet: A cross-modal intracerebral haemorrhage prognostic prediction "
        "method using joint-attention interaction mechanism",
        ("X. Wan", "C. Wang"),
        "Neural Networks",
    ),
    (
        "6- A. Elazab, C. Wang, S. J. S. Gardezi, H. Bai, Q. Hu, T. Wang, "
        "C. Chang*, B. Lei*. GP-GAN: Brain Tumor Growth Prediction Using "
        "Stacked 3D Generative Adversarial Networks. Neural Networks, vol. 132, "
        "pp. 321-332, 2020 (IF= 5.535, Q1).",
        "GP-GAN: Brain Tumor Growth Prediction Using Stacked 3D Generative "
        "Adversarial Networks",
        ("Q. Hu", "B. Lei"),
        "Neural Networks",
    ),
    (
        "7- C. Fan#, A. Elazab#, S. Zhang, Y. Wang, Q. Liang, D. Li, Y. Zhang, "
        "Y. Xiang, B. Liu, C. Wang*. Clinical Prior Guided Cross-Modal "
        "Hierarchical Fusion for Histological Subtyping of Lung Cancer in CT "
        "Scans. International Conference on Medical Image Computing and "
        "Computer-Assisted Intervention, pp. 75-84. Springer, 2025.",
        "Clinical Prior Guided Cross-Modal Hierarchical Fusion for Histological "
        "Subtyping of Lung Cancer in CT Scans",
        ("Y. Xiang", "C. Wang"),
        "International Conference on Medical Image Computing",
    ),
    (
        "8- J. Yu, R. Ge, Z. Wang, C. Yang, C. Lin, X. Fu, J. Liu, A. Elazab*, "
        "C. Wang*. “Small Lesions-aware Bidirectional Multimodal Multiscale "
        "Fusion Network for Lung Disease Classification. International "
        "Conference on Medical Image Computing and Computer-Assisted "
        "Intervention, pp. 589-598. Springer, 2025.",
        "Small Lesions-aware Bidirectional Multimodal Multiscale Fusion Network "
        "for Lung Disease Classification",
        ("J. Liu", "C. Wang"),
        "International Conference on Medical Image Computing",
    ),
    (
        "9- X. Yu#, A. Elazab#, R. Ge, H. Jin, X. Jiang, G. Jia, Q. Wu, Q. Shi, "
        "C. Wang ICH-SCNet: Intracerebral Hemorrhage Segmentation and Prognosis "
        "Classification Network Using CLIP-guided SAM mechanism. 2024 IEEE "
        "International Conference on Bioinformatics and Biomedicine (BIBM), "
        "Lisbon, Portugal, 2024, pp. 2795 - 2800.",
        "ICH-SCNet: Intracerebral Hemorrhage Segmentation and Prognosis "
        "Classification Network Using CLIP-guided SAM mechanism",
        ("Q. Shi", "C. Wang"),
        "2024 IEEE International Conference on Bioinformatics and Biomedicine",
    ),
]


def test_sigs_author_prefixed_numbered_citation_extracts_title_authors_venue_year():
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <div>
        <p>{AHMED_FIRST_PUBLICATION}</p>
      </div>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
    )

    assert len(publications) == 1
    publication = publications[0]
    assert publication.clean_title == (
        "Robust attention transfer neural networks for diagnosis of Alzheimer's "
        "disease from structural magnetic resonance images"
    )
    assert publication.authors_text is not None
    assert "M. Abdelaziz" in publication.authors_text
    assert "A. Elazab" in publication.authors_text
    assert publication.venue_text is not None
    assert "Engineering Applications of Artificial Intelligence" in (
        publication.venue_text
    )
    assert publication.year == 2026


def test_sigs_author_prefixed_splitter_does_not_treat_authors_as_title():
    title, authors, venue = _split_title_authors_venue(AHMED_FIRST_PUBLICATION)

    assert title == (
        "Robust attention transfer neural networks for diagnosis of Alzheimer's "
        "disease from structural magnetic resonance images"
    )
    assert authors is not None
    assert "A. Elazab" in authors
    assert venue is not None
    assert "Engineering Applications of Artificial Intelligence" in venue


def test_sigs_ahmed_author_continuations_extract_full_titles():
    html = "\n".join(
        [
            "<main><h2>代表性论文</h2>",
            *(
                f"<p>{raw_publication}</p>"
                for raw_publication, _title, _authors, _venue in (
                    AHMED_AUTHOR_CONTINUATION_PUBLICATIONS
                )
            ),
            "</main>",
        ]
    )

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
    )

    assert len(publications) == len(AHMED_AUTHOR_CONTINUATION_PUBLICATIONS)
    for publication, (_raw, expected_title, expected_authors, expected_venue) in zip(
        publications,
        AHMED_AUTHOR_CONTINUATION_PUBLICATIONS,
        strict=True,
    ):
        assert publication.clean_title == expected_title
        assert publication.authors_text is not None
        for expected_author in expected_authors:
            assert expected_author in publication.authors_text
        assert publication.venue_text is not None
        assert expected_venue in publication.venue_text


def test_official_publication_extraction_does_not_truncate_large_sigs_list():
    entries = "\n".join(
        (
            "<li>"
            f"{index}- A. Elazab*. Complete Trustworthy Medical AI Study {index}, "
            f"Journal of Medical Artificial Intelligence, {index}, 2026."
            "</li>"
        )
        for index in range(1, 206)
    )
    html = f"""
    <main>
      <h2>Representative Publications</h2>
      <ol>{entries}</ol>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
    )

    assert len(publications) == 205
    assert publications[0].clean_title == "Complete Trustworthy Medical AI Study 1"
    assert publications[-1].clean_title == "Complete Trustworthy Medical AI Study 205"


def test_sigs_spaced_bracket_prefix_and_url_only_lines_do_not_pollute_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[ 2 ] Tengfei Li, Deli Peng #, Yelingyi Wang, Guangliang Li,
      Dinglin Yang, Kaiwen Tian, Wengen Ouyang, Michael Urbakh, and
      Quanshui Zheng#. Towards Zero Static Friction at the Microscale.
      Physical Review Letters, 2024, 133(23): 236202.</p>
      <p>https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.133.236202</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/pdl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Towards Zero Static Friction at the Microscale"
    )
    assert publications[0].authors_text is not None
    assert "Deli Peng" in publications[0].authors_text
    assert "Quanshui Zheng" in publications[0].authors_text


def test_sigs_bracketed_venue_prefix_with_missing_closing_quote_extracts_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[9] [JSAC] Wenbo Ding, Yang Lu, Fang Yang, Wei Dai, Pan Li,
      Sicong Liu, and Jian Song, “Spectrally Efficient Channel State
      Information Acquisition for Power Line Communications: A Bayesian
      Compressive Sensing Perspective, IEEE Journal of Selected Areas on
      Communications, vol 34, no. 7, pp. 2022-2032, Jul. 2016</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Spectrally Efficient Channel State Information Acquisition for Power "
        "Line Communications: A Bayesian Compressive Sensing Perspective"
    )
    assert publications[0].authors_text is not None
    assert "Wenbo Ding" in publications[0].authors_text
    assert "Jian Song" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "IEEE Journal of Selected Areas on Communications" in (
        publications[0].venue_text
    )
    assert publications[0].year == 2016


def test_sigs_marked_author_continuation_before_title_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[7] Quan Yuan, Lei Deng, Hao Guo, Qishen Lyu, Xin Zhang,
      Jibin Wu, Yu Deng, Hongyang Zhou, Xilin Wang* . Zhidong Jia.
      Discharge Image Reconstruction and Frequency Domain Analysis Based on
      Event Data, High Voltage, 2024, 2024, 9(6): 1195-1201.</p>
      <p>【 4 】 Jiafei Lyu, Le Wan, Xiu Li † s and Zongqing Lu.
      Understanding what affects generalization gap in visual reinforcement
      learning: Theory and empirical evidence[J]. Journal of Artificial
      Intelligence Research, 2024, Volume:80.</p>
      <p>【 1 】 Yukang Lin * , Hokit Fung * , Jianjin Xu, Zeping Ren,
      Adela S.M. Lau, Guosheng Yin † , Xiu Li † . MVPortrait: Text-Guided
      Motion and Emotion Control for Multi-view Vivid Portrait Animation[C].
      In Proceedings of the IEEE/CVF Conference on Computer Vision and
      Pattern Recognition (CVPR-25), 2025.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lx/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Discharge Image Reconstruction and Frequency Domain Analysis Based on "
        "Event Data",
        "Understanding what affects generalization gap in visual reinforcement "
        "learning: Theory and empirical evidence",
        "MVPortrait: Text-Guided Motion and Emotion Control for Multi-view Vivid "
        "Portrait Animation",
    ]
    assert "Zhidong Jia" in (publications[0].authors_text or "")
    assert "Zongqing Lu" in (publications[1].authors_text or "")
    assert "Adela S.M. Lau" in (publications[2].authors_text or "")


def test_sigs_semicolon_surname_initial_authors_split_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>1. Ma, Z.; Fu, Z.; Hou, B.; Zeng, X.; Wang, J.; Tan, Y.;
      Jiang, Y.; Xu, N.; Tan, C. Two-Photon Light-Activatable Fluorophores
      for Organelle Imaging in Living Cells and Tissue-Level Imaging.
      J. Am. Chem. Soc. 2025, jacs.5c14442.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/tcy/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Two-Photon Light-Activatable Fluorophores for Organelle Imaging in "
        "Living Cells and Tissue-Level Imaging"
    )
    assert publications[0].authors_text is not None
    assert "Z. Ma" in publications[0].authors_text
    assert "C. Tan" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "J. Am. Chem. Soc" in publications[0].venue_text


def test_sigs_chinese_author_list_splits_title_and_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>6. 邱家福, 刘佳鑫, 段晓伟, 陈胜利*, 大鹏湾海域海漂垃圾迁移路径研究,
      热带海洋学报, 2026, 45(2), 1-15.</p>
      <p>7. 姜昊, 景路*, 朱艳, 刘蒙, 赵庆喜, 王恩浩, 陈胜利, 李彬彬, 胡振中.
      中长周期波作用下斜坡堤表面压力分布特性的 SPH 数值模拟研究. 海洋工程, 2025.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/csl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "大鹏湾海域海漂垃圾迁移路径研究",
        "中长周期波作用下斜坡堤表面压力分布特性的 SPH 数值模拟研究",
    ]
    assert publications[0].authors_text is not None
    assert "陈胜利" in publications[0].authors_text
    assert publications[1].authors_text is not None
    assert "胡振中" in publications[1].authors_text


def test_sigs_comma_author_list_with_et_al_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1]. Dachuan Shi, Chun Yuan, et al., CrossGET: Cross-Guided
      Ensemble of Tokens for Accelerating Vision-Language Transformers ，
      ICML2024</p>
      <p>[7]. Tianke Zhang, Chun Yuan, et al,Accurate 3D Face Reconstruction
      with Facial Component Tokens, ICCV2023</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "CrossGET: Cross-Guided Ensemble of Tokens for Accelerating "
        "Vision-Language Transformers",
        "Accurate 3D Face Reconstruction with Facial Component Tokens",
    ]
    for publication in publications:
        assert publication.authors_text is not None
        assert "Chun Yuan" in publication.authors_text
        assert "et al" in publication.authors_text
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_et_al_prefix_keeps_comma_inside_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[12]. Zixuan Hu, Chun Yuan, et al., Architecture, Dataset and
      Model-Scale Agnostic Data-free Meta-Learning ， CVPR 2023</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Architecture, Dataset and Model-Scale Agnostic Data-free Meta-Learning"
    )
    assert publications[0].authors_text is not None
    assert "Zixuan Hu" in publications[0].authors_text
    assert "Chun Yuan" in publications[0].authors_text
    assert "et al" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "CVPR 2023" in publications[0].venue_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_semicolon_surname_list_with_comma_tail_author_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[3] Liu, Shaojun; Liao, Qingmin; Xue, Jing-Hao, Zhou, Fei.
      Defocus map estimation from a single image using improved likelihood
      feature and edge-based basis, Pattern Recognition, 107: 107485,
      Nov 2020.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lqm/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Defocus map estimation from a single image using improved likelihood "
        "feature and edge-based basis"
    )
    assert publications[0].authors_text is not None
    assert "Fei Zhou" in publications[0].authors_text


def test_sigs_comma_author_list_with_accented_name_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[3] Xu Feng, Tan Junbo, Wang Xueqian *, Puig Vicenç, Liang Bin*,
      Yuan Bo, Mixed Active/Passive Robust Fault Detection and Isolation Using
      Set-Theoretic Unknown Input Observers[J]. IEEE Transactions on Automation
      Science and Engineering. 2018, 15(2): 863-871.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wxq/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Mixed Active/Passive Robust Fault Detection and Isolation Using "
        "Set-Theoretic Unknown Input Observers"
    )
    assert publications[0].authors_text is not None
    assert "Puig Vicenç" in publications[0].authors_text
    assert "Yuan Bo" in publications[0].authors_text


def test_sigs_comma_author_list_with_accented_surname_given_pair_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[4] Xu Feng, Tan Junbo, Wang Xueqian *, Puig, Vicenç, Liang Bin*,
      Yuan Bo, Liu Houde, Generalized set-theoretic unknown input observer for
      LPV systems with application to state estimation and robust fault
      detection[J]. International Journal of Robust and Nonlinear Control.
      2017, 17(27): 3812-3832.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wxq/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Generalized set-theoretic unknown input observer for LPV systems with "
        "application to state estimation and robust fault detection"
    )
    assert publications[0].authors_text is not None
    assert "Vicenç Puig" in publications[0].authors_text
    assert "Liu Houde" in publications[0].authors_text


def test_sigs_comma_author_list_with_surname_given_pair_and_marked_tail_author():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[6] Xu Feng, Tan Junbo, Wang Ye*, Puig, Vicenç, Wang Xueqian *.
      Combining Set-Theoretic UIO and Invariant Sets for Optimal Guaranteed
      Robust Fault Detection and Isolation[J]. Journal of Process Control,
      2019, 78: 155-169.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wxq/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Combining Set-Theoretic UIO and Invariant Sets for Optimal Guaranteed "
        "Robust Fault Detection and Isolation"
    )
    assert publications[0].authors_text is not None
    assert "Vicenç Puig" in publications[0].authors_text
    assert "Wang Xueqian" in publications[0].authors_text


def test_sigs_comma_author_list_with_surname_initial_period_tail_author():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>20. Li, DX, Feng, PF, Zhang, JF, Wu, ZJ, Yu, DW. Method for
      modifying convective heat transfer coefficients used in the thermal
      simulation of a feed drive system based on the response surface
      methodology. NUMERICAL HEAT TRANSFER PART A-APPLICATIONS. 2015.</p>
      <p>1. Liu, A., Hong, N., Zhu, P., Guan, Y.. Understanding benzene
      series (BTEX) pollutant load characteristics in the urban environment.
      Science of the Total Environment, 2018, 619:938-945.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Method for modifying convective heat transfer coefficients used in the "
        "thermal simulation of a feed drive system based on the response surface "
        "methodology",
        "Understanding benzene series (BTEX) pollutant load characteristics in "
        "the urban environment",
    ]
    assert publications[0].authors_text is not None
    assert "DW Yu" in publications[0].authors_text
    assert publications[1].authors_text is not None
    assert "Y. Guan" in publications[1].authors_text


def test_sigs_et_al_period_prefix_with_compact_venue_year_splits_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[46]. Maomao Li, Chun Yuan, et al. Stochastic Video Generation
      with Disentangled Representations ICME 2019 (CCF B)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Stochastic Video Generation with Disentangled Representations"
    )
    assert publications[0].authors_text is not None
    assert "Maomao Li" in publications[0].authors_text
    assert "Chun Yuan" in publications[0].authors_text
    assert "et al" in publications[0].authors_text
    assert publications[0].venue_text == "ICME 2019 (CCF B)"
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_compact_ccf_venue_tail_is_not_part_of_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1]. Dachuan Shi, Chun Yuan, et al.,
      Cross-modal Representation Learning and Relation Reasoning for
      Bidirectional Adaptive Manipulation，IJCAI2022 CCF A</p>
      <p>[2]. Chun Yuan, et al. TranSlider: Transfer Ensemble Learning from
      Exploitation to Exploration KDD2020(CCF A)</p>
      <p>[3]. Chun Yuan, et al. AF-SVG: Hierarchical Stochastic Video
      Generation with Aligned Features, IJCAI2020, (CCF A)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Cross-modal Representation Learning and Relation Reasoning for "
        "Bidirectional Adaptive Manipulation",
        "TranSlider: Transfer Ensemble Learning from Exploitation to Exploration",
        "AF-SVG: Hierarchical Stochastic Video Generation with Aligned Features",
    ]
    assert [publication.venue_text for publication in publications] == [
        "IJCAI2022 CCF A",
        "KDD2020(CCF A)",
        "IJCAI2020, (CCF A)",
    ]
    assert [publication.year for publication in publications] == [2022, 2020, 2020]
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_citation_type_and_title_label_metadata_are_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[4]. Zixuan Hu, Chun Yuan, et al. Towards Calibrated Model for
      Long-Tailed Visual Recognition from Prior Perspective[C]//NeurIPS2021 CCF A</p>
      <p>[5]. Chun Yuan, et al. Title:HOSE-Net: Higher Order Structure Embedded
      Network for Scene Graph Generation, ACMMM2020 （ CCF A ）</p>
      <p>[6]. Ying Shan “ Feature Augmented Memory with Global Attention
      Network for VideoQA IJCAI2020, (CCF A)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Towards Calibrated Model for Long-Tailed Visual Recognition from "
        "Prior Perspective",
        "HOSE-Net: Higher Order Structure Embedded Network for Scene Graph "
        "Generation",
        "Feature Augmented Memory with Global Attention Network for VideoQA",
    ]
    assert "NeurIPS2021 CCF A" in (publications[0].venue_text or "")
    assert "ACMMM2020" in (publications[1].venue_text or "")
    assert "IJCAI2020" in (publications[2].venue_text or "")
    assert "Ying Shan" in (publications[2].authors_text or "")
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_full_name_author_list_and_in_press_tail_are_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[52]. Zhuobin Zheng, Chun Yuan, Zhihui Lin, Yangyang Cheng,
      Hanghao Wu, Self-Adaptive Double bootstrapped DDPG ， in press,
      IJCAI 2018 (CCF A)</p>
      <p>[42]. Chenxi Yuan , Yang Bai, Chun Yuan Bridge the Gap: High-level
      Semantic Planning for Image Captioning Coling, Coling2020 CCF B</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc2/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Self-Adaptive Double bootstrapped DDPG",
        "Bridge the Gap: High-level Semantic Planning for Image Captioning",
    ]
    assert "Hanghao Wu" in (publications[0].authors_text or "")
    assert "Chun Yuan" in (publications[1].authors_text or "")
    assert "IJCAI 2018 (CCF A)" in (publications[0].venue_text or "")
    assert publications[1].venue_text == "Coling2020 CCF B"
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_if_citations_metadata_tail_is_venue_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1] Servadio J, Munoz-Zanzi C, Convertino M., (2021) Estimating
      case fatality risk of severe Yellow Fever cases: Systematic literature
      review and meta-analysis, BMC Infectious Diseases, IF/citations:
      2.87/-, in press &</p>
      <p>[2] Galbraith E, Convertino M, Li J, Del Rio-Vilas V (2021),
      In.To. COVID-19 Socio-epidemiological Co-causality, (2021) Scientific
      Reports, IF/citations: 4/-, in press *</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/Matteo Convertino/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Estimating case fatality risk of severe Yellow Fever cases: Systematic "
        "literature review and meta-analysis",
        "In.To. COVID-19 Socio-epidemiological Co-causality",
    ]
    assert "BMC Infectious Diseases" in (publications[0].venue_text or "")
    assert "Scientific Reports" in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_no_year_venue_head_before_compact_venue_tail_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[55]. Zhiguan Lin, Chun Yuan, Robust Visual Tracking in Low-Resolution
      Sequence. IEEE International Conference on Image Processing ICIP 2018,
      ( 清华 CS ， B)</p>
      <p>[56]. Dali Yang, Chun Yuan. Hierarchical Context Encoder for Events
      Captioning in Videos, IEEE International Conference on Image Processing,
      ICIP2018, ( 清华 CS ， B)</p>
      <p>[57]. EP-Net: More Efficient Pose Estimation Network with the
      Classification-based Key-points Detection.2nd International Conference
      on Video</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc2/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Robust Visual Tracking in Low-Resolution Sequence",
        "Hierarchical Context Encoder for Events Captioning in Videos",
        "EP-Net: More Efficient Pose Estimation Network with the "
        "Classification-based Key-points Detection",
    ]
    assert "Zhiguan Lin" in (publications[0].authors_text or "")
    assert "Dali Yang" in (publications[1].authors_text or "")
    assert "IEEE International Conference on Image Processing" in (
        publications[0].venue_text or ""
    )
    assert "IEEE International Conference on Image Processing" in (
        publications[1].venue_text or ""
    )
    assert "2nd International Conference on Video" in (
        publications[2].venue_text or ""
    )
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_short_year_status_and_ieee_trans_tail_are_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[69] Hang Guo, Tao Dai, Guanghao Meng, Shu-Tao Xia. Towards robust
      scene text image super-resolution via explicit location enhancement,
      IJCAI-23.</p>
      <p>[51]. Zhou Cheng, Chun Yuan, Jiancheng Li, Haiqin Yuang, TreeNet:
      Learning sentence representations with unconstrained tree structure,
      in press, IJCAI 2018 (CCF A)</p>
      <p>[24] Siqi Wang, Yehu Shen, Wenming Yang *, Touchless Finger Vein and
      Fingerprint Verification via Exploiting Attention-Based Cross-Domain
      Fusion, IEEE Trans. on Circuits Systems & Video Technology(IEEE TCSVT),
      (2024) Early Access.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Towards robust scene text image super-resolution via explicit location "
        "enhancement",
        "TreeNet: Learning sentence representations with unconstrained tree "
        "structure",
        "Touchless Finger Vein and Fingerprint Verification via Exploiting "
        "Attention-Based Cross-Domain Fusion",
    ]
    assert publications[0].venue_text == "IJCAI-23"
    assert "IJCAI 2018 (CCF A)" in (publications[1].venue_text or "")
    assert "IEEE Trans. on Circuits Systems & Video Technology" in (
        publications[2].venue_text or ""
    )


def test_sigs_embedded_colon_author_before_title_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[26] Yiyun Chen, Yunmeng Liu, Mingliang Chen, Zirui Wang，
      Wenming Yang*， Qingmin Liao: Blind JPEG Compression Artifacts Removal
      by Integrating Channel Regulation with Exit Strategy, IEEE Trans. on
      Multimedia(IEEE TMM), 25(11):7274-7286 (2023)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ywm/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Blind JPEG Compression Artifacts Removal by Integrating Channel "
        "Regulation with Exit Strategy"
    )
    assert "Qingmin Liao" in (publications[0].authors_text or "")
    assert "IEEE Trans. on Multimedia" in (publications[0].venue_text or "")


def test_sigs_full_name_author_fragment_is_blocked_or_split():
    title = "Yanfei Zhu, Zhoujie Lao, Mengtian Zhang, Tingzheng Hou, Xiao Xiao"
    assert _is_suspicious_rule_publication(
        HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text=None,
            venue_text=None,
            year=None,
            source_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
            source_anchor=None,
        )
    )

    html = """
    <main>
      <h2>代表性论文</h2>
      <p>42. Jia Liu, David J. Sample, Cameron Bell and Yuntao Guan, Review
      and research needs of bioretention used for the treatment of urban
      stormwater [J]. Water, 2014, 6(4): 1069-1099.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/gyt/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Review and research needs of bioretention used for the treatment of "
        "urban stormwater"
    )
    assert "Yuntao Guan" in (publications[0].authors_text or "")
    assert publications[0].venue_text is not None
    assert "Water" in publications[0].venue_text


def test_sigs_semicolon_author_list_splits_on_semicolon_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[35]. Lu, Yuwu; Wang, Wenjing; Yuan, Chun; Li, Xuelong;
      Lai, Zhihui; Manifold Transfer Learning Via Discriminant Regression
      Analysis, IEEE Transaction on Multimedia ， 2020 (清华 CS ， A)</p>
      <p>3. Ling Qiu; Jeffery Z Liu; Shery L Y Chang; Yanzhe Wu; Dan Li*;
      Biomimetic superelastic graphene-based cellular monoliths,
      Nature Communications, 2012, 3: 1241</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Manifold Transfer Learning Via Discriminant Regression Analysis",
        "Biomimetic superelastic graphene-based cellular monoliths",
    ]
    assert "Chun Yuan" in (publications[0].authors_text or "")
    assert "Dan Li" in (publications[1].authors_text or "")
    assert publications[0].venue_text is not None
    assert "IEEE Transaction on Multimedia" in publications[0].venue_text
    assert publications[1].venue_text is not None
    assert "Nature Communications" in publications[1].venue_text
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_semicolon_surname_list_with_plus_markers_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>(8) Zhang, C.+; Tan, J. Y.+; Pan, Y. K.; Cai, X. K.; Zou, X. L.;
      Cheng, H. M.*; Liu, B. L.*, Mass Production of Two-Dimensional
      Materials by Intermediate-Assisted Grinding Exfoliation. National
      Science Review, 2020, 7, 324-332.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lbl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Mass Production of Two-Dimensional Materials by Intermediate-Assisted "
        "Grinding Exfoliation"
    )
    assert publications[0].authors_text is not None
    assert "C. Zhang" in publications[0].authors_text
    assert "B. L. Liu" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "National Science Review" in publications[0].venue_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_author_year_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Zheng, X. Y. (2013) Random Wave Forces on Monopile Wind Turbine
      Foundations: A Comparison of Wave Models. OMAE2013-10713,
      Proceedings of 32nd International Conference on Offshore Mechanics and
      Arctic Engineering, June 9-14, 2013, Nantes, France.</p>
      <p>Moan, T., X. Y. Zheng and S. T. Quek (2007) Frequency-domain
      Analysis of Nonlinear Wave Effects on Offshore Platform Responses.
      International Journal of Non-Linear Mechanics, 42(3), p 555-565.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zxy/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Random Wave Forces on Monopile Wind Turbine Foundations: A Comparison "
        "of Wave Models",
        "Frequency-domain Analysis of Nonlinear Wave Effects on Offshore "
        "Platform Responses",
    ]
    assert "X. Y Zheng" in (publications[0].authors_text or "")
    assert "S. T. Quek" in (publications[1].authors_text or "")
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_concatenated_camelcase_author_before_title_splits():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[19] Ruibo Yan, Xi Xiao, Guangwu Hu, Sancheng Peng,YongJiang.
      New Deep Learning Method to Detect Code Injection Attacks on Hybrid
      Applications, Journal of Systems and Software, 2018, 3(137): 67-77.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xx_443/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "New Deep Learning Method to Detect Code Injection Attacks on Hybrid "
        "Applications"
    )
    assert publications[0].authors_text is not None
    assert "Yong Jiang" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "Journal of Systems and Software" in publications[0].venue_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_author_period_splits_title_and_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[15] 郭昱君、关翎、 邱亨嘉 *、杨燕绥。临床路径对医疗资源使用的效益-
      以腹腔镜胆囊切除手术患者为例。中国卫生政策研究，2018, 11(8)，50-55。</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/qhj/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "临床路径对医疗资源使用的效益- 以腹腔镜胆囊切除手术患者为例"
    )
    assert publications[0].authors_text is not None
    assert "邱亨嘉" in publications[0].authors_text
    assert publications[0].venue_text is not None
    assert "中国卫生政策研究" in publications[0].venue_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_in_proc_tail_is_venue_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>1. Shun Lei*, Yixuan Zhou*, Boshi Tang*, Max W. Y. Lam,
      Feng Liu, Hangyu Liu, Jingcheng Wu, Shiyin Kang, Zhiyong Wu#,
      Helen Meng, SongCreator: Lyrics-based Universal Song Generation,
      [in] Proc. Annual Conference on Neural Information Processing Systems
      (NeurIPS), pp. 1-34. Vancouver, Canada. December 10-15, 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zywu/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "SongCreator: Lyrics-based Universal Song Generation"
    )
    assert publications[0].venue_text is not None
    assert "Annual Conference on Neural Information Processing Systems" in (
        publications[0].venue_text
    )


def test_sigs_proc_tail_is_venue_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[10] Yuzhao Chen, Yatao Bian, Xi Xiao*, Yu Rong, Tingyang Xu,
      Junzhou Huang. On Self-Distilling Graph Neural Network, Proc. 30th
      International Joint Conference on Artificial Intelligence (IJCAI-21),
      Montreal, Canada, 2021.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xx_443/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "On Self-Distilling Graph Neural Network"
    assert publications[0].venue_text is not None
    assert "International Joint Conference on Artificial Intelligence" in (
        publications[0].venue_text
    )


def test_sigs_chinese_spaced_author_before_journal_marker_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1]. 李向明* ，孙春柳，董 宇涵. 研究生教育中外合作办学选择动因研究——
      推拉理论的拓展与延伸 [J] .清华大学教育研究, 2017, 38(3):108-112.
      CSSCI</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lxm/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "研究生教育中外合作办学选择动因研究—— 推拉理论的拓展与延伸"
    )
    assert "董宇涵" in (publications[0].authors_text or "")
    assert "清华大学教育研究" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_surname_given_year_quoted_title_extracts_title_not_author_fragment():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[3] Lu, Shuai, Wang, Chunxiao, Fan, Yue & Lin, Borong 2021,
      ‘Robustness of building energy optimization with uncertainties using
      deterministic and stochastic methods: Analysis of two forms’, Building
      and Environment, vol. 205, pp. 108185</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ls/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Robustness of building energy optimization with uncertainties using "
        "deterministic and stochastic methods: Analysis of two forms"
    )
    assert "Shuai Lu" in (publications[0].authors_text or "")
    assert "Borong Lin" in (publications[0].authors_text or "")
    assert "Building and Environment" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_semicolon_initial_author_list_extracts_title_not_author_prefix():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[15] Mao, R.; Gao, S.; Qin, Z.; Wu, S. J.; Li, Z. Q. Arnold, F. H.
      Biocatalytic, Enantioenriched Primary Amination of Tertiary C–H Bonds.
      Nat. Catal. 2024, 7, 585.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/mrz/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Biocatalytic, Enantioenriched Primary Amination of Tertiary C–H Bonds"
    )
    assert "R. Mao" in (publications[0].authors_text or "")
    assert "F. H. Arnold" in (publications[0].authors_text or "")
    assert "Nat. Catal" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_residual_journal_marker_fragments_are_washed_out():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>forms[J]. Frontiers of Architectural Research, 2022, 11: 653-669.</p>
      <p>建设介绍[J]. 建筑技艺, 2022, 28(07): 82-85.</p>
      <p>[1] Wenbo Ding, Yang Lu, Fang Yang, Wei Dai, Pan Li, Sicong Liu,
      and Jian Song. Spectrally Efficient Channel State Information Acquisition
      for Power Line Communications: A Bayesian Compressive Sensing Perspective.
      IEEE Journal of Selected Areas on Communications, 2016.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xwg/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Spectrally Efficient Channel State Information Acquisition for Power "
        "Line Communications: A Bayesian Compressive Sensing Perspective"
    ]


def test_sigs_author_dot_title_without_space_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1]. Yuexin Kang, Rong Wang, Zhizhen Qin, Peng Yang* , Yimo
      Yan.Warehouses with heterogeneous robots collaboration: operational
      policies and performance analysis.International Journal of Production
      Research,2025,DOI: 10.1080/00207543.2025.2513576.</p>
      <p>[14]. Rong Wang, Peng Yang* , Yeming Gong, Cheng Chen.Operational
      Policies and Performance Analysis for Overhead Robotic Compact
      Warehousing Systems with Bin Reshuffling. International Journal of
      Production Research,2024(62),14:5236-5251.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yp/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Warehouses with heterogeneous robots collaboration: operational "
            "policies and performance analysis"
        ),
        (
            "Operational Policies and Performance Analysis for Overhead Robotic "
            "Compact Warehousing Systems with Bin Reshuffling"
        ),
    ]
    assert "Yimo Yan" in (publications[0].authors_text or "")
    assert "Cheng Chen" in (publications[1].authors_text or "")
    assert "International Journal of Production Research" in (
        publications[0].venue_text or ""
    )


def test_sigs_final_full_name_author_period_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Guochao Wang*, Xinghui Li* , Shuhua Yan, Lilong Tan. Wenliang Guan.
      Real-time absolute distance measurement by multi-wavelength
      interferometry synchronously multi-channel phase-locked to frequency comb
      and analysis for the potential non-ambiguity range[J]. Acta Physica
      Sinica , 2021, 70(4): 20201225.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lxh/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title.startswith("Real-time absolute distance")
    assert "Wenliang Guan" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_multi_initial_final_author_is_not_title_prefix():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[10]. Zhizhen Qin, Peng Yang* , Yeming Gong, René B. M. de Koster.
      Performance Analysis of Multi-Tote Storage and Retrieval Autonomous Mobile
      Robot Systems. Transportation Science,2024, DOI: 10.1287/trsc.2023.0397.
      </p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yp/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Performance Analysis of Multi-Tote Storage and Retrieval Autonomous "
        "Mobile Robot Systems"
    )
    assert "René B. M. de Koster" in (publications[0].authors_text or "")
    assert "Transportation Science" in (publications[0].venue_text or "")


def test_sigs_compact_journal_year_tail_without_space_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[7]. Xiaolong Zhou,Binjia Li, Peng Yang* . Ergonomic Workload
      Assessment of Order Picking Operations Based on Machine Learning with
      sEMG Signals.IFAC-PapersOnLine.2025 (59),10:422-427.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yp/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Ergonomic Workload Assessment of Order Picking Operations Based on "
        "Machine Learning with sEMG Signals"
    )
    assert "IFAC-PapersOnLine" in (publications[0].venue_text or "")


def test_sigs_spaced_given_name_and_marked_middle_author_do_not_become_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[17]. Xin gwei Chen, Peng Yang* and Zixin Shao. Simulation-based
      time-efficient and energy-efficient performance analysis of an overhead
      robotic compact storage and retrieval system. Simulation Modelling
      Practice and Theory,2022.DOI: 10.1016/j.simpat.2022.102560.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yp/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Simulation-based time-efficient and energy-efficient performance "
        "analysis of an overhead robotic compact storage and retrieval system"
    )
    assert "Xingwei Chen" in (publications[0].authors_text or "")
    assert "Zixin Shao" in (publications[0].authors_text or "")
    assert "Simulation Modelling Practice and Theory" in (
        publications[0].venue_text or ""
    )


def test_sigs_titlecase_title_after_comma_author_list_is_not_author_tail():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1] Zhendong Yang, Zhe Li, Mingqi Shao, Dachuan Shi, Zehuan Yuan,
      Chun Yuan, Masked Generative Distillation, ECCV 2022</p>
      <p>[2] J. Xu, S.-L. Huang, Byzantine-Resilient Decentralized
      Collaborative Learning, IEEE International Conference on Acoustics,
      Speech, and Signal Processing (ICASSP), May, 2022</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc2/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Masked Generative Distillation",
        "Byzantine-Resilient Decentralized Collaborative Learning",
    ]
    assert "Chun Yuan" in (publications[0].authors_text or "")
    assert "S.-L. Huang" in (publications[1].authors_text or "")
    assert publications[0].venue_text == "ECCV 2022"


def test_sigs_dense_initial_author_chain_splits_before_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[10] X. M. Yuan, C.R. Fan, J. Xu, W.J. Cao*, W.C. Zhou,
      E.L. Jiang, Y. Ma, C. Xu, P.F. Feng, F. Feng* , Dominating influence
      of cutting-edge lead angles on arc-trajectory machining of Nomex®
      honeycomb composites by using a straight blade cutter, Engineering
      Science and Technology, an International Journal, 49 (2024) 101601.</p>
      <p>[12] X.M. Yuan, B. Li, F. Feng* , J. Xu, G. Song, Y.Y. Liang,
      Y. Ma, C. Xu, F.J. Wang, P.F. Feng, False Boss Connection for Precision
      Machining of Composites with Soft and Brittle Characteristics, Journal
      of Composites Science, 8 (2024) 292.</p>
      <p>[15] J. Xu, Q.Z. Yue, H.T. Zha*, X.M. Yuan, X.K. Cai, C. Xu,
      Y. Ma, P.F. Feng, F. Feng* , Wear reduction by toughness enhancement
      of disc tool in Nomex honeycomb composites machining, Tribology
      International, 185 (2023) 108475.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ff/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Dominating influence of cutting-edge lead angles on arc-trajectory "
            "machining of Nomex® honeycomb composites by using a straight blade "
            "cutter"
        ),
        (
            "False Boss Connection for Precision Machining of Composites with "
            "Soft and Brittle Characteristics"
        ),
        (
            "Wear reduction by toughness enhancement of disc tool in Nomex "
            "honeycomb composites machining"
        ),
    ]
    assert "F. Feng" in (publications[0].authors_text or "")
    assert "P.F. Feng" in (publications[1].authors_text or "")
    assert "H.T. Zha" in (publications[2].authors_text or "")
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_marked_final_author_comma_title_splits_before_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[26] F. Feng , H.F. Hong, X. Gao*, T. Ren, Y. Ma, P.F. Feng*,
      Effectiveness of Oxygen during Sintering of Silver Thin Films Derived by
      Nanoparticle Ink, Nanomaterials, 12 (2022) 1908.</p>
      <p>[27] F. Feng , M. Yuan, Y.S. Xia, H.M. Xu, P.F. Feng*, X.H. Li*,
      Roughness Scaling Extraction Accelerated by Dichotomy-Binary Strategy
      and Its Application to Milling Vibration Signal, Mathematics, 10 (2022)
      1105.</p>
      <p>[31] G. Zhou, X.H. Wang, F. Feng* , P.F. Feng, M. Zhang*,
      Calculation of fractal dimension based on artificial neural network and
      its application for machined surfaces. Fractals-Complex Geometry
      Patterns and Scaling in Nature and Society, 29 (2021) 2150129.</p>
      <p>[32] Z.R. Yang, T.M. Qu, F. Feng* , L.L. Wang, P.F. Feng, Wrinkling
      surface of mono-layered thin film derived by using trifluoroacetate
      solution, Journal of Sol-Gel Science and Technology, 99 (2021) 13-24.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ff/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Effectiveness of Oxygen during Sintering of Silver Thin Films "
            "Derived by Nanoparticle Ink"
        ),
        (
            "Roughness Scaling Extraction Accelerated by Dichotomy-Binary "
            "Strategy and Its Application to Milling Vibration Signal"
        ),
        (
            "Calculation of fractal dimension based on artificial neural "
            "network and its application for machined surfaces"
        ),
        (
            "Wrinkling surface of mono-layered thin film derived by using "
            "trifluoroacetate solution"
        ),
    ]
    assert "P.F. Feng" in (publications[0].authors_text or "")
    assert "X.H. Li" in (publications[1].authors_text or "")
    assert "M. Zhang" in (publications[2].authors_text or "")
    assert "L.L. Wang" in (publications[3].authors_text or "")
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_long_marked_author_chain_continues_until_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>18. Dongqing Liu, Zulipiya Shadike, Ruoqian Lin, Kun Qian, Hai Li,
      Kaikai Li, Shuwei Wang, Qipeng Yu, Ming Liu, Swapna Ganapathy,
      Xianying Qin, QuanHong Yang, Marnix Wagemaker * , Feiyu Kang,
      Xiao ‐ Qing Yang * , Baohua Li * , Review of recent development of
      in situ/operando characterization techniques for lithium battery
      research . Advanced Materials , 2019, 31,1806620.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lbh/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Review of recent development of in situ/operando characterization "
            "techniques for lithium battery research"
        )
    ]
    assert "Xiao-Qing Yang" in (publications[0].authors_text or "")
    assert "Baohua Li" in (publications[0].authors_text or "")
    assert "Advanced Materials" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_marked_author_period_splits_before_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>26.魏鹏骥， 姜玥璐 * .重金属Cd 2+ 、Cu 2+ 与Zn 2+ 对威氏海链藻
      Conticribra weissflogii 生长生理和油脂的影响, 中国海洋大学学报
      (自然科学版)，2018，接收。</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/jyl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "重金属Cd 2+ 、Cu 2+ 与Zn 2+ 对威氏海链藻 Conticribra "
            "weissflogii 生长生理和油脂的影响"
        )
    ]
    assert publications[0].authors_text == "魏鹏骥, 姜玥璐"
    assert "中国海洋大学学报" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_period_journal_tail_after_title_is_not_kept_in_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1] W. M. Zhou, P.F. Feng, W. Ji, Z.Y. Wang, Y. Ma, E.L.
      Jiang, H.T. Zha, Z.P. Cai, F. Feng*, Multiscale analysis on the
      wear process of cemented carbide tools during titanium alloy
      machining. Friction, 13 (2025) 9440921.</p>
      <p>2. Lv, X., Huang, B., Zhu, X., Jiang, Y., Chen, B., Tao, Y.,
      Zhou, J., Cai, Z., 2017. Mechanisms underlying the acute toxicity
      of fullerene to Daphnia magna: Energy acquisition restriction and
      oxidative stress. Water Research 123(Supplement C), 696-703.</p>
      <p>5. Yuelu Jiang*, Katherine Starks Laverty, Jola Brown, Marcella
      Nunez, Lou Brown, Antonietta Quigg. 2014. Effects of fluctuating
      temperature and silicate supply on the growth, biochemical
      composition and lipid accumulation of Nitzschia sp.. Bioresource
      Technology. 154: 336-344.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Multiscale analysis on the wear process of cemented carbide tools "
            "during titanium alloy machining"
        ),
        (
            "Mechanisms underlying the acute toxicity of fullerene to Daphnia "
            "magna: Energy acquisition restriction and oxidative stress"
        ),
        (
            "Effects of fluctuating temperature and silicate supply on the "
            "growth, biochemical composition and lipid accumulation of "
            "Nitzschia sp"
        ),
    ]
    assert "Friction" in (publications[0].venue_text or "")
    assert "Water Research" in (publications[1].venue_text or "")
    assert "Bioresource Technology" in (publications[2].venue_text or "")
    for publication in publications:
        assert not _is_suspicious_rule_publication(publication)


def test_sigs_title_internal_comma_before_period_journal_is_not_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>2. Yao Wang, Xu Yang, Yuefeng Meng, Zuxin Wen, Ran Han, Xia Hu,
      Bing Sun, Feiyu Kang, Baohua Li*, Dong Zhou*, Chunsheng Wang*, and
      Guoxiu Wang*, Fluorine Chemistry in Rechargeable Batteries:
      Challenges, Progress and Perspectives. Chemical Reviews, 2024,
      124 (6), 3494-3589.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lbh/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Fluorine Chemistry in Rechargeable Batteries: Challenges, "
            "Progress and Perspectives"
        )
    ]
    assert "Baohua Li" in (publications[0].authors_text or "")
    assert "Chemical Reviews" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_title_suffix_author_chain_is_suspicious_and_filters_noise():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>I have published more than 60 papers in peer-refereed journals,
      including 2 Nature Materials and 4 Advanced Materials.</p>
      <p>Selected Publication :</p>
      <p>1.Intrinsic Half-Metallicity in 2D Ternary Chalcogenides with High
      Critical Temperature and Controllable Magnetization Direction Shuqing
      Zhang, Runzhang Xu, Wenhui Duan, Xiaolong Zou* Adv. Funct. Mater.
      DOI: https://doi.org/10.1002/adfm.201808380 (2019)</p>
      <p>2.Morphology and surface chemistry engineering toward pH-universal
      catalysts for hydrogen evolution at high current density Yuting Luo,
      Lei Tang, Usman Khan, Qiangmin Yu, Hui-Ming Cheng, Xiaolong Zou*,
      Bilu Liu* Nature Communications, 10, 269 (2019)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zxl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Intrinsic Half-Metallicity in 2D Ternary Chalcogenides with High "
            "Critical Temperature and Controllable Magnetization Direction "
            "Shuqing Zhang, Runzhang Xu, Wenhui Duan, Xiaolong Zou* Adv"
        ),
        (
            "Morphology and surface chemistry engineering toward pH-universal "
            "catalysts for hydrogen evolution at high current density Yuting "
            "Luo, Lei Tang, Usman Khan, Qiangmin Yu, Hui-Ming Cheng, Xiaolong "
            "Zou*, Bilu Liu*"
        ),
    ]
    assert all(_is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_llm_fallback_fixes_title_suffix_author_chain():
    source_span = (
        "1.Intrinsic Half-Metallicity in 2D Ternary Chalcogenides with High "
        "Critical Temperature and Controllable Magnetization Direction Shuqing "
        "Zhang, Runzhang Xu, Wenhui Duan, Xiaolong Zou* Adv. Funct. Mater. "
        "DOI: https://doi.org/10.1002/adfm.201808380 (2019)"
    )
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <p>{source_span}</p>
    </main>
    """

    def clean_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Intrinsic Half-Metallicity in 2D Ternary Chalcogenides "
                    "with High Critical Temperature and Controllable "
                    "Magnetization Direction"
                ),
                "authors_text": "Shuqing Zhang, Runzhang Xu, Wenhui Duan, Xiaolong Zou",
                "venue_text": "Adv. Funct. Mater.",
                "year": 2019,
                "source_span": source_span,
                "confidence": 0.95,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zxl/main.htm",
        llm_extractor=clean_llm,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Intrinsic Half-Metallicity in 2D Ternary Chalcogenides with High "
            "Critical Temperature and Controllable Magnetization Direction"
        )
    ]
    assert publications[0].authors_text is not None
    assert "Xiaolong Zou" in publications[0].authors_text
    assert publications[0].venue_text == "Adv. Funct. Mater"
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_dense_initial_author_fragment_title_is_suspicious():
    for title in (
        "Jiang, Y. Ma, C. Xu, P.F",
        "Liang, Y. Ma, C. Xu, F.J",
        "Cai, C. Xu, Y. Ma, P.F",
        "Feng, X.H. Li*",
        "Feng*, Effectiveness of Oxygen during Sintering of Silver Thin Films",
        "Li*, Roughness Scaling Extraction Accelerated by Dichotomy-Binary Strategy",
        "Xiao ‐ Qing Yang *, Baohua Li *",
        "姜玥璐 *.重金属Cd 2+ 、Cu 2+ 与Zn 2+ 对威氏海链藻",
    ):
        assert _is_suspicious_rule_publication(
            HomepagePublication(
                raw_title=title,
                clean_title=title,
                authors_text=None,
                venue_text=None,
                year=None,
                source_url="http://www.sigs.tsinghua.edu.cn/ff/main.htm",
                source_anchor=None,
            )
        )


def test_sigs_semicolon_author_list_stops_before_title_and_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Ling Qiu; Bing Huang; Zijun He; Yuanyuan Wang; Zhiming Tian;
      Jefferson Zhe Liu; Kun Wang; Jingchao Song; Thomas R Gengenbach;
      Dan Li; Extremely Low Density and Super-Compressible Graphene Cellular
      Materials, Advanced Materials, 2017, 29(36): 0-1701553</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ql/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Extremely Low Density and Super-Compressible Graphene Cellular "
        "Materials"
    )
    assert "Ling Qiu" in (publications[0].authors_text or "")
    assert "Dan Li" in (publications[0].authors_text or "")
    assert "Advanced Materials" in (publications[0].venue_text or "")


def test_sigs_chinese_author_title_and_chinese_journal_tail_are_split():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>刘广灵, 探寻职业化之路, 清华管理评论, 3 卷 1 期（2013 年 2 月）, 68-76</p>
      <p>机电产品拆卸研究综述, 机械工程学报, 2004(7)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lgl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "探寻职业化之路",
        "机电产品拆卸研究综述",
    ]
    assert publications[0].authors_text == "刘广灵"
    assert "清华管理评论" in (publications[0].venue_text or "")
    assert "机械工程学报" in (publications[1].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])
    assert not _is_suspicious_rule_publication(publications[1])


def test_sigs_chinese_probable_journal_tail_after_author_is_split():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>刘广灵, 合伙制理论研究最新进展, 经济学动态, 2009 年 12 期, 114-118</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lgl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "合伙制理论研究最新进展"
    assert publications[0].authors_text == "刘广灵"
    assert "经济学动态" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_author_year_parentheses_prefix_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>姜文宇, 王飞 * 等（ 2023 ）， 基于元胞自动机的以火灭火动态建模方法,
      清华大学学报 (自然科学版), vol. 63, no. 06, pp. 926-933</p>
      <p>姜文宇, 王飞 * 等（ 2022 ）, 面向森林火灾的应急管理信息化关键技术,
      中国安全科学学报, vol. 32, no. 09, pp. 182-191</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wf/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "基于元胞自动机的以火灭火动态建模方法",
        "面向森林火灾的应急管理信息化关键技术",
    ]
    assert [publication.authors_text for publication in publications] == [
        "姜文宇, 王飞",
        "姜文宇, 王飞",
    ]
    assert "清华大学学报" in (publications[0].venue_text or "")
    assert "中国安全科学学报" in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_chinese_semicolon_author_list_before_title_is_split():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>黄龙; 曾文; 徐冰; 张灿阳; 马少华; 张翀; 王怡 *; 邢新会 *,
      口服多糖靶向药物递送体系在结肠疾病治疗中的应用研究进展, 药学学报,
      2021, 1073. (IF 11.413). Q1</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zcy/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "口服多糖靶向药物递送体系在结肠疾病治疗中的应用研究进展"
    )
    assert "张灿阳" in (publications[0].authors_text or "")
    assert "邢新会" in (publications[0].authors_text or "")
    assert "药学学报" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_title_and_journal_without_year_still_splits_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>液压自由活塞发动机的发展历程及研究现状, 机械工程学报</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xbz/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "液压自由活塞发动机的发展历程及研究现状"
    assert publications[0].authors_text is None
    assert publications[0].venue_text == "机械工程学报"
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_author_period_title_journal_year_splits_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>杨华勇,夏必忠,傅新. 液压自由活塞发动机的发展历程及研究现状,
      机械工程学报 ,2001,37(2):1-7. (EI)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xbz/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "液压自由活塞发动机的发展历程及研究现状"
    assert publications[0].authors_text == "杨华勇, 夏必忠, 傅新"
    assert "机械工程学报" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_surname_given_and_author_list_splits_before_year_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Wang, Ziteng and Hu, Chun and Zheng, Dezhi* and Chen, Xinlei*
      (2021) Ultralow-Power Sensing Framework for Internet of Things: A Smart
      Gas Meter as a Case. IEEE Internet of Things Journal, 9(10), 7533-7544</p>
      <p>Yan, Tao and Zhou, Tiankuang and Guo, Yanchen& and Zhao, Yun& and
      Shao Guocheng& and Wu, Jiamin and Huang, Ruqi* and Dai Qionghai* and
      Fang, Lu*, Nanowatt all-optical 3D perception for mobile robotics,
      Science Advances, 2024</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/hrq/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Ultralow-Power Sensing Framework for Internet of Things: A Smart "
            "Gas Meter as a Case"
        ),
        "Nanowatt all-optical 3D perception for mobile robotics",
    ]
    assert "Ziteng Wang" in (publications[0].authors_text or "")
    assert "Xinlei Chen" in (publications[0].authors_text or "")
    assert "Ruqi Huang" in (publications[1].authors_text or "")
    assert "Science Advances" in (publications[1].venue_text or "")


def test_sigs_comma_full_name_and_author_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[21]. Cairong Wang, Yiming Zhu, and Chun Yuan, Diverse Image
      Inpainting with Normalizing Flow, ECCV 2022</p>
      <p>Andong Wang, Zhengzhuo Xu, and Chun Yuan, Semantic-Sparse
      Colorization Network for Deep Exemplar-based Colorization, ACM
      Multimedia 2020</p>
      <p>Peng Zhang, Chun Yuan, and Zhi Wang, Texture and Shape biased
      Two-Stream Networks for Clothing Classification and Attribute
      Recognition, IEEE CVPR 2021</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc2/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Diverse Image Inpainting with Normalizing Flow",
        "Semantic-Sparse Colorization Network for Deep Exemplar-based Colorization",
        (
            "Texture and Shape biased Two-Stream Networks for Clothing "
            "Classification and Attribute Recognition"
        ),
    ]
    assert publications[0].authors_text == "Cairong Wang, Yiming Zhu, Chun Yuan"
    assert publications[1].authors_text == "Andong Wang, Zhengzhuo Xu, Chun Yuan"
    assert publications[2].authors_text == "Peng Zhang, Chun Yuan, Zhi Wang"
    assert "ECCV 2022" in (publications[0].venue_text or "")
    assert "ACM Multimedia 2020" in (publications[1].venue_text or "")
    assert "IEEE CVPR 2021" in (publications[2].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_comma_full_name_marked_tail_author_without_comma_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Zhang C anrong, Zhang Dandan, and Wu T ao * Data-driven Branching
      and Selection for Lot-sizing and Scheduling Problems with
      Sequence-dependent Setups and Setup Carryover</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zcr/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Data-driven Branching and Selection for Lot-sizing and Scheduling "
        "Problems with Sequence-dependent Setups and Setup Carryover"
    )
    assert publications[0].authors_text is not None
    assert "Zhang Canrong" in publications[0].authors_text
    assert "Zhang Dandan" in publications[0].authors_text
    assert "Wu Tao" in publications[0].authors_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_semicolon_author_final_author_period_title_splits_cleanly():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[4] Pan Yi; Zhang Sheng; Wang Xiao; Liu Manhao;Luo Yiran. A fine
      acquisition algorithm based on fast three-time FRFT for dynamic and weak
      GNSS signals. Journal of Systems Engineering and Electronics. April 2023.
      Vol. 34, No. 2, April 2023, pp.259-269.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zs_458/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "A fine acquisition algorithm based on fast three-time FRFT for dynamic "
        "and weak GNSS signals"
    )
    assert "Luo Yiran" in (publications[0].authors_text or "")


def test_sigs_chinese_title_journal_year_without_author_splits_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>独具特色的地质学研究学派, 科学学研究, 1996（1）</p>
      <p>STS三次浪潮中的实在论立场, 自然辩证法研究, 2020 (2)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wps/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "独具特色的地质学研究学派",
        "STS三次浪潮中的实在论立场",
    ]
    assert "科学学研究" in (publications[0].venue_text or "")
    assert "自然辩证法研究" in (publications[1].venue_text or "")


def test_sigs_comma_inside_valid_title_is_not_author_fragment():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>S.-L. Huang, L. Zheng, G. Wornell, Gaussian Universal Features,
      Canonical Correlations, and Common Information, IEEE Information Theory
      Workshop, Nov., 2018</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/hsl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Gaussian Universal Features, Canonical Correlations, and Common "
        "Information"
    )
    assert "S.-L. Huang" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_and_surname_initial_author_tail_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>C. Hong, J. A. Burney, J. Pongratz, J. Nabel, N. D Mueller,
      R. B. Jackson and Davis, S. J.*, Global and regional drivers of
      land-use emissions 1961-2017 Nature, 589, 554-561, 2021</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/hcp/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Global and regional drivers of land-use emissions 1961-2017"
    )
    assert "R. B. Jackson" in (publications[0].authors_text or "")
    assert "S. J. Davis" in (publications[0].authors_text or "")
    assert "Nature, 589" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_surname_and_initial_author_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Goodenough and G. Yu*, A chemistry and material perspective on
      lithium redox flow batteries towards high-density electrical energy
      storage, Chem, 2017.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "A chemistry and material perspective on lithium redox flow batteries "
        "towards high-density electrical energy storage"
    )
    assert "Goodenough" in (publications[0].authors_text or "")
    assert "G. Yu" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_fullwidth_numbered_comma_author_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>5） Wang Yu, Wu Qian-Yuan, Lee Min-Yong, Nong Yu-Jia,
      Wang Wen-Long *, Drewes Jörg E. Efficient Electrocatalytic
      Hydrodechlorination and Detoxification of Chlorophenols by
      Palladium–Palladium Oxide Heterostructure. Water Research, 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/wwl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Efficient Electrocatalytic Hydrodechlorination and Detoxification of "
        "Chlorophenols by Palladium–Palladium Oxide Heterostructure"
    )
    assert "Wang Wen-Long" in (publications[0].authors_text or "")
    assert "Drewes Jörg E" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_missing_comma_surname_initial_author_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Gong, J. Zhou, N. Zhang*, Y.Su*, Smart and solvent-switchable
      graphene-based membrane for graded molecular sieving. Journal of
      Membrane Science, 2023.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sy/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Smart and solvent-switchable graphene-based membrane for graded "
        "molecular sieving"
    )
    assert "Gong" in (publications[0].authors_text or "")
    assert "Y. Su" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_semicolon_surname_given_author_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Sia, Wan Rong; Mak, Jeffrey Y.W.; Fairlie, David P.; Wang, Lin-Fa;
      Sandberg, Johan K.; Lobie, Peter E.; Ma, Shaohua*; Leeansyah, Edwin*;
      MAIT cell activation and recruitment in inflammation and tissue damage
      in acute appendicitis. Clinical & Translational Immunology, 2020.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "MAIT cell activation and recruitment in inflammation and tissue "
        "damage in acute appendicitis"
    )
    assert "Wan Rong Sia" in (publications[0].authors_text or "")
    assert "Edwin Leeansyah" in (publications[0].authors_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_url_and_author_fragment_titles_are_suspicious_at_bridge_boundary():
    for title in (
        "ResearcherID: http://www.researcherid.com/rid/I-9088-2012",
        "Chen, M. and Li",
        "A., EDTA functionalized magnetic nanoparticle sorbents",
        "Zhang Y. Serine/Arginine-rich Splicing Factor 2 Modulates Herpes",
        "Chem. Engineer. J",
        "Offshore wind resources. Energy. WOS:000445985300047, total cites 6",
        "Rui hua Luo, Keyi Zhong, Daoyi Chen, Guozhong Wu, Li Wang, "
        "Mucong Zi*, Microscopic influence mechanisms of pre-adsorbed "
        "polysaccharide on the nucleation and growth of methane hydrate on "
        "metal surface",
    ):
        publication = HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text=None,
            venue_text=None,
            year=None,
            source_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
            source_anchor=None,
        )

        assert _is_suspicious_rule_publication(publication), title


def test_sigs_marker_and_contribution_author_fragments_are_suspicious_with_authors():
    for title in (
        "*; Electrotunable liquid sulphur microdroplets",
        "M.; # (# Equally Contributed) Yin, L. C.; Ren W. C.; Li, F.; "
        "Cheng, H.-M. *",
        "M.; # (# Equally Contributed), Liu, Z.; Ma, X.; Chen, J.; "
        "Scalable Clean Exfoliation of High-Quality Few-Layer Black Phosphorus "
        "for a Flexible Lithium Ion Battery",
        "#; (# Equally Contributed), Yan, K.; Xie, J.; Li, Y.; "
        "Air-stable and freestanding lithium alloy/graphene foil as an "
        "alternative to lithium metal anodes",
        "(# Equally Contributed)",
        "*, Bidirectional catalysts for liquid-solid redox conversion in "
        "lithium-sulfur batteries",
        "*; Wang, J.; Li",
        "Zh ang, C.; Kang",
        "M. *; Cheng, H.-M. *, Intercalation-Induced Conversion Reactions Give "
        "High-Capacity Potassium Storage",
        "*; Xiao, J. #; Zhong",
        "Zhou YK (Zhou, Yikang), Li G (Li, Gang), Dong JK (Dong, Junkai), "
        "Xing XH (Xing, Xin-hui), Dai JBA (Dai, Junbiao), Zhang C "
        "(Zhang, Chong)*, MiYA, an efficient machine-learning workflow in "
        "conjunction with the YeastFab assembly strategy for combinatorial "
        "optimization of heterologous metabolic pathways in Saccharomyces "
        "cerevisiae",
        "Xin-Hui Xing *, Prokaryotic Communities in Multidimensional "
        "Bottom-Pit-Mud from Old and Young Pits Used for the Production of "
        "Chinese Strong-Flavor Baijiu",
        "Hatton, T.A.*, Electrochemically mediated direct CO2 capture by a "
        "stackable bipolar cell",
        "van der Velde, I. R., Chuvieco, E., Chen, Y., Zhang, Q., He, K., "
        "and Zheng, B.*: Enhanced CH 4 emissions from global wildfires likely "
        "due to undetected small fires",
        "van der A, R., Lin, J., Guan, D., Lei, Y., He, K., and Zhang, Q.*: "
        "Satellite-based estimates of decline and rebound in China'sCO2 "
        "emissions during COVID-19 pandemic",
        "Zhai * and F. Kang.*",
        "Li * and F. Kang",
        "Curtiss * and K. Amine",
        "Das and H.-H. Sun, K. Amine",
        "K. Amine* and L. A. Curtiss.*",
        "… Xiao Liu *",
        "…, Xiao Liu * and Xiu Qiu*",
        "… Christian Datz* and Xiao Liu *",
        "jiajun Huang*, Shengli Mi*",
        "Shengli Mi * and Wei Sun* The multifaceted nature of catechol "
        "chemistry: bioinspired pH-initiated hyaluronic acid hydrogels with "
        "tunable cohesive and adhesive properties",
        "junwen zhong, Min Zhang *, Xiaohao Wang, Liwei Lin",
    ):
        publication = HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text="G. M. Zhou, Y. Cui",
            venue_text="Nature Nanotechnology, 2020",
            year=2020,
            source_url="http://www.sigs.tsinghua.edu.cn/zgm/main.htm",
            source_anchor=None,
        )

        assert _is_suspicious_rule_publication(publication), title


def test_sigs_chinese_author_marker_note_is_not_publication():
    for title in ("# 共同第一作者， * 通讯作者", "共同第一作者 / 通讯作者"):
        publication = HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text=None,
            venue_text=None,
            year=None,
            source_url="http://www.sigs.tsinghua.edu.cn/lx2/main.htm",
            source_anchor=None,
        )

        assert _is_suspicious_rule_publication(publication), title


def test_sigs_llm_fallback_rejects_author_only_titles_without_real_title():
    source_span = (
        "W. Yu, K. C. Lau, Y. Lei, R. Liu, L. Qin, W. Yang, B. Li, "
        "L. A. Curtiss, D. Zhai * and F. Kang.* ACS Applied Materials & "
        "Interfaces 2017, 31871."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "Zhai * and F. Kang.*",
                "authors_text": (
                    "W. Yu, K. C. Lau, Y. Lei, R. Liu, L. Qin, W. Yang, "
                    "B. Li, L. A. Curtiss"
                ),
                "venue_text": "ACS Applied Materials & Interfaces 2017, 31871",
                "year": 2017,
                "source_span": source_span,
                "confidence": 0.95,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zdy/main.htm",
        llm_extractor=bad_llm,
        force_llm=True,
    )

    assert publications == []


def test_sigs_llm_fallback_extracts_title_from_ellipsis_author_fragments():
    source_span = (
        "Zhiming Li#, Jingjing Xia#, … Xiao Liu *, Jiucun Wang*. "
        "Characterization of the human skin resistome and identification of two "
        "microbiota cutotypes. Microbiome. 2021. (IF 11.6, JCR Q1)"
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Characterization of the human skin resistome and "
                    "identification of two microbiota cutotypes"
                ),
                "authors_text": (
                    "Zhiming Li, Jingjing Xia, Xiao Liu, Jiucun Wang"
                ),
                "venue_text": "Microbiome",
                "year": 2021,
                "source_span": source_span,
                "confidence": 0.95,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lx2/main.htm",
        llm_extractor=good_llm,
        force_llm=False,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Characterization of the human skin resistome and identification "
            "of two microbiota cutotypes"
        )
    ]
    assert "Xiao Liu" in (publications[0].authors_text or "")


def test_sigs_llm_fallback_repairs_split_pinyin_author_prefix_before_title():
    source_span = (
        "Shengli M i *, Xiaohui Zhang, Zhidong Liu. Study on patterned "
        "photodynamic cross-linking for keratoconus. Bioactive Materials, 2023."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def contaminated_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Shengli M i * Study on patterned photodynamic "
                    "cross-linking for keratoconus"
                ),
                "authors_text": "Shengli M i *, Xiaohui Zhang, Zhidong Liu",
                "venue_text": "Bioactive Materials",
                "year": 2023,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/msl/main.htm",
        llm_extractor=contaminated_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Study on patterned photodynamic cross-linking for keratoconus"
    ]


def test_sigs_llm_fallback_repairs_marked_author_pair_prefix_before_title():
    source_span = (
        "Shengli Mi * and Wei Sun* The multifaceted nature of catechol "
        "chemistry: bioinspired pH-initiated hyaluronic acid hydrogels with "
        "tunable cohesive and adhesive properties. Chemical Society Reviews, 2020."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def contaminated_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Shengli Mi * and Wei Sun* The multifaceted nature of "
                    "catechol chemistry: bioinspired pH-initiated hyaluronic "
                    "acid hydrogels with tunable cohesive and adhesive properties"
                ),
                "authors_text": "Shengli Mi * and Wei Sun*",
                "venue_text": "Chemical Society Reviews",
                "year": 2020,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/msl/main.htm",
        llm_extractor=contaminated_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "The multifaceted nature of catechol chemistry: bioinspired "
            "pH-initiated hyaluronic acid hydrogels with tunable cohesive and "
            "adhesive properties"
        )
    ]


def test_sigs_llm_fallback_repairs_marked_surname_initial_prefix_without_authors_text():
    source_span = (
        "Tsuboi T *. Mitochondrial protein heterogeneity stems from the "
        "stochastic nature of co-translational protein targeting in cell "
        "senescence. Nature Communications, 2025."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def contaminated_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Tsuboi T *. Mitochondrial protein heterogeneity stems from "
                    "the stochastic nature of co-translational protein targeting "
                    "in cell senescence"
                ),
                "authors_text": None,
                "venue_text": "Nature Communications",
                "year": 2025,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/test/main.htm",
        llm_extractor=contaminated_llm,
        author_filter=lambda authors: authors is None,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Mitochondrial protein heterogeneity stems from the stochastic "
            "nature of co-translational protein targeting in cell senescence"
        )
    ]


def test_sigs_split_diacritic_author_semicolon_chain_before_title():
    source_span = (
        "Micha ł Tu ł odziecki; Sandeep Unnikrishnan; Marnix Wagemaker; "
        "Tandem Interface and Bulk Li-Ion Transport in a Hybrid Solid "
        "Electrolyte with Microsized Active Filler. ACS Energy Letters, 2024."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/test/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Tandem Interface and Bulk Li-Ion Transport in a Hybrid Solid "
            "Electrolyte with Microsized Active Filler"
        )
    ]
    assert "Michał Tułodziecki" in (publications[0].authors_text or "")
    assert "Sandeep Unnikrishnan" in (publications[0].authors_text or "")


def test_sigs_author_venue_year_only_fragment_is_not_publication_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>F Kang.* Advanced Materials 2024, 2409062</p>
      <p>F. Kang.* Advanced Materials 2024, 2409062</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/test/main.htm",
    )

    assert publications == []


def test_sigs_bullet_prefix_is_removed_from_publication_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>• On the Multi-User Multi-Cell Massive Spatial Modulation Uplink:
      How Many Antennas for Each User? IEEE Transactions on Wireless
      Communications, 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/test/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "On the Multi-User Multi-Cell Massive Spatial Modulation Uplink: "
            "How Many Antennas for Each User?"
        )
    ]


def test_sigs_llm_fallback_repairs_connective_author_comma_prefix_without_authors_text():
    source_span = (
        "Goodenough and G. Yu*, A chemistry and material perspective on lithium "
        "redox flow batteries towards high-density electrical energy storage, "
        "Chem, 2024."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def contaminated_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Goodenough and G. Yu*, A chemistry and material perspective "
                    "on lithium redox flow batteries towards high-density "
                    "electrical energy storage, Chem"
                ),
                "authors_text": None,
                "venue_text": "Chem",
                "year": 2024,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/test/main.htm",
        llm_extractor=contaminated_llm,
        author_filter=lambda authors: authors is None,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "A chemistry and material perspective on lithium redox flow "
            "batteries towards high-density electrical energy storage"
        )
    ]


def test_sigs_llm_fallback_repairs_split_title_words_from_line_breaks():
    source_span = (
        "X Zhao, Z Zhang*, 2025, Heterogeneous Peroxymonosulfate-based "
        "Advanced Oxidation Mechanisms: New W ine in O ld B ottles? "
        "Environmental Science & Technology, 59, 12, 5913-5924"
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def split_word_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Heterogeneous Peroxymonosulfate-based Advanced Oxidation "
                    "Mechanisms: New W ine in O ld B ottles?"
                ),
                "authors_text": "X Zhao, Z Zhang",
                "venue_text": "Environmental Science & Technology",
                "year": 2025,
                "source_span": source_span,
                "confidence": 0.95,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zzh/main.htm",
        llm_extractor=split_word_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Heterogeneous Peroxymonosulfate-based Advanced Oxidation "
            "Mechanisms: New Wine in Old Bottles?"
        )
    ]


def test_sigs_research_topic_heading_is_not_publication():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>机器学习 / 计算机视觉 / 大模型与 AI 安全</p>
      <p>[1] Yujun Huang, Bin Chen, Naiqi Li, Baoyi An, Shu-Tao Xia,
      Yaowei Wang. MB-RACS: measurement-bounds-based rate-adaptive image
      compressed sensing network, IEEE Transactions on Pattern Analysis and
      Machine Intelligence (TPAMI), accepted, Mar. 2025</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xst/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "MB-RACS: measurement-bounds-based rate-adaptive image compressed sensing network"
    ]


def test_sigs_split_pinyin_author_names_do_not_become_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[2] Yiming L i, Linghui Zhu, X iaojun J ia, Yang Bai, Yong Jiang,
      Shu-Tao Xia, Xiaochun Cao. MOVE: Effective and harmless ownership
      verification via embedded external features. IEEE Transactions on
      Pattern Analysis and Machine Intelligence (TPAMI), accepted, Feb. 2025,
      early access, DOI: 10.1109/TPAMI.2025.3546223</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xst/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "MOVE: Effective and harmless ownership verification via embedded "
        "external features"
    )
    assert "Yiming Li" in (publications[0].authors_text or "")
    assert "Xiaojun Jia" in (publications[0].authors_text or "")
    assert "Xiaochun Cao" in (publications[0].authors_text or "")
    assert "IEEE Transactions on Pattern Analysis and Machine Intelligence" in (
        publications[0].venue_text or ""
    )


def test_sigs_comma_author_tail_before_period_title_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[10] Xinhao Zhong, Bin Chen, Hao Fang, Xulin Gu, Shu-Tao Xia,
      En-Hui Yang. Going beyond feature similarity: effective dataset
      distillation based on class-aware conditional mutual information.
      ICLR 2025</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xst/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Going beyond feature similarity: effective dataset distillation "
        "based on class-aware conditional mutual information"
    )
    assert "Shu-Tao Xia" in (publications[0].authors_text or "")
    assert "En-Hui Yang" in (publications[0].authors_text or "")
    assert publications[0].venue_text == "ICLR 2025"


def test_sigs_split_pinyin_author_chain_and_full_name_dot_title_are_repaired():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[85] Bo wen Zhao, C hen Chen, X i Xiao, S hu- T ao Xia.
      Towards a category-extended object detector with limited data,
      Pattern Recognition 132(2022) 108943.</p>
      <p>[119] Dongxian Wu, Yisen Wang, Shu-Tao Xia. Adversarial Weight
      Perturbation Improves Adversarial Training, Proc. Neural Information
      Processing Systems (NIPS-20), Virtual Conference, Dec. 2020.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xst/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Towards a category-extended object detector with limited data",
        "Adversarial Weight Perturbation Improves Adversarial Training",
    ]
    assert "Bowen Zhao" in (publications[0].authors_text or "")
    assert "Chen Chen" in (publications[0].authors_text or "")
    assert "Xi Xiao" in (publications[0].authors_text or "")
    assert "Shu-Tao Xia" in (publications[0].authors_text or "")
    assert "Shu-Tao Xia" in (publications[1].authors_text or "")
    assert "Neural Information Processing Systems" in (
        publications[1].venue_text or ""
    )


def test_sigs_leading_author_marker_is_removed_from_title_after_author_chain():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[7]. Cheng Zheng*, Yaowu Chen, Xiangcheng Xu, Qiaowei Lin,
      Hongyu Wang, Qiao Xue, Bangquan Jian, Zhu Guo, Wei Lv,* Diglyme-based
      electrolytes boosting high-rate and stable sodium-ion storage for
      three-dimensional VS4/Reduced graphene oxide hybrid anodes, Journal
      of Power Sources, 2022, 526, 231098.</p>
      <p>[26]. Ziyang Lu, Qinghua Liang; Bo Wang, Ying Tao, Yufeng Zhao,
      Wei Lv,* Donghai Liu, Chen Zhang, Zhe Weng, Jiachen Liang, Huan Li,
      Quan-Hong Yang,* Graphitic Carbon Nitride Induced Micro-Electric Field
      for Dendrite-Free Lithium Metal Anodes, Advanced Energy Materials,
      2019, 9(7), 1803186.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lw/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Diglyme-based electrolytes boosting high-rate and stable sodium-ion "
            "storage for three-dimensional VS4/Reduced graphene oxide hybrid anodes"
        ),
        (
            "Graphitic Carbon Nitride Induced Micro-Electric Field for "
            "Dendrite-Free Lithium Metal Anodes"
        ),
    ]
    assert "Wei Lv" in (publications[0].authors_text or "")
    assert "Quan-Hong Yang" in (publications[1].authors_text or "")
    assert all(not pub.clean_title.startswith("*") for pub in publications)
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_publication_heading_and_bio_prose_are_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>代表性论文（ *表示通讯）</p>
      <p>康飞宇教授主要从事新型碳材料以及能源与环境材料研究，是国家纳米研究
      重大计划首席科学家，已在国内外学术期刊上发表SCI收录论文493篇。</p>
      <p>此外，康飞宇教授还带领学科团队在天然石墨深加工、锌离子电池方面
      业绩突出，产生了显著的经济效益和社会效益。</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/kfy/main.htm",
    )

    assert publications == []


def test_sigs_person_names_external_pointers_and_mojibake_are_washed_out():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1] Wenbo Ding, Yang Lu, Fang Yang, Wei Dai, Pan Li, Sicong Liu,
      and Jian Song. Spectrally Efficient Channel State Information Acquisition
      for Power Line Communications: A Bayesian Compressive Sensing Perspective.
      IEEE Journal of Selected Areas on Communications, 2016.</p>
      <p>[2] Zhidong Jia</p>
      <p>[3] 请见 https://www.sigs.tsinghua.edu.cn/sample/main.htm</p>
      <p>[4] WOS:000123456789</p>
      <p>[5] EI Accession number: 202612345678</p>
      <p>[6] Ã©Ã¨â€™ malformed title</p>
      <p>[7] 具体发表情况详见： https://scholar.google.com/citations?user=9-7kE_QAAAAJ</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Spectrally Efficient Channel State Information Acquisition for Power "
        "Line Communications: A Bayesian Compressive Sensing Perspective"
    ]


def test_sigs_non_publication_title_noise_is_suspicious_at_bridge_boundary():
    for title in (
        "Zhidong Jia",
        "发表 SCI 论文 200 多篇，其中 Nature 论文 3 篇",
        "请见 https://www.sigs.tsinghua.edu.cn/sample/main.htm",
        "具体发表详见 https://scholar.google.com/citations?hl=en&user=Nm3ZGrQAAAAJ",
        "具体发表情况详见： https://scholar.google.com/citations?user=9-7kE_QAAAAJ",
        "WOS:000123456789",
        "EI Accession number: 202612345678",
        "Ã©Ã¨â€™ malformed title",
        "As Corresponding Author",
        "Scientific Reports, IF/citations: 4/-, in press *",
        "杨 兵, * 高福平, 吴应湘",
    ):
        publication = HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text=None,
            venue_text=None,
            year=None,
            source_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
            source_anchor=None,
        )

        assert _is_suspicious_rule_publication(publication), title


def test_sigs_short_titlecase_titles_are_not_treated_as_person_names():
    for title in ("Deep Learning", "Federated Learning"):
        publication = HomepagePublication(
            raw_title=title,
            clean_title=title,
            authors_text=None,
            venue_text=None,
            year=None,
            source_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
            source_anchor=None,
        )

        assert not _is_suspicious_rule_publication(publication), title


def test_sigs_llm_fallback_extracts_variable_citations_from_source_spans():
    source_spans = [
        (
            "Ping Su, Junrong Wang, Chao Cai, et al. Large field-of-view "
            "lensless holographic dynamic projection system with uniform "
            "illumination and U-net acceleration. Optics and Lasers in "
            "Engineering, 2022"
        ),
        (
            "Pandey, V., Wang, B., Mohan, C. D., Raquib, A. R., Rangappa, S., "
            "Srinivasa, V., Fuchs, J. E., Girish, K. S., Zhu, T., Bender, A., "
            "Ma, L., Yin, Z., Basappa, Rangappa, K. S. and Lobie, P. E., "
            "Discovery of a small-molecule inhibitor of specific serine residue BAD "
            "phosphorylation. Proc Natl Acad Sci U S A, 2018. 115(44): "
            "p. E10505-e10514."
        ),
        (
            "Zhao, Q.-R.; Wang, K.; Gao, X.; Tan, C. Two-Dimensional "
            "Porphyrin-Based Covalent Organic Frameworks for Visible-Light-Driven "
            "Oxidative Coupling of Benzylamines. Chem. Commun. 2025, 61 (67), "
            "12502-12505."
        ),
        (
            "Guo, D.; Selby, T. A.; Kahmann, S.; Gorgon, S.; Dai, L.; "
            "Dubajic, M.; Yang, T. C.-J.; Fairclough, S. M.; Marsh, T.; "
            "Jacobs, I. E.; Wu, B.; Guo, R.; Nagane, S.; Doherty, T. A. S.; "
            "Ji, K.; Liu, C.; Lu, Y.; Kang, T.; Mamak, C.; Mao, J.; "
            "Muller-Buschbaum, P.; Sirringhaus, H.; Midgley, P. A.; "
            "Stranks, S. D. Picosecond quantum transients in halide perovskite "
            "nanodomain superlattices. Nature Nanotechnology 2025, 20, "
            "1771-1778."
        ),
    ]
    html = "<main><h2>代表性论文</h2>" + "".join(
        f"<p>[{index}] {span}</p>" for index, span in enumerate(source_spans, 1)
    ) + "</main>"

    def fake_llm(section_text: str, page_url: str):
        assert "代表性论文" in section_text
        assert page_url == "https://www.sigs.tsinghua.edu.cn/sample/main.htm"
        return [
            {
                "title": (
                    "Large field-of-view lensless holographic dynamic projection "
                    "system with uniform illumination and U-net acceleration"
                ),
                "authors_text": "Ping Su, Junrong Wang, Chao Cai, et al.",
                "venue_text": "Optics and Lasers in Engineering",
                "year": 2022,
                "source_span": source_spans[0],
                "confidence": 0.94,
            },
            {
                "title": (
                    "Discovery of a small-molecule inhibitor of specific serine "
                    "residue BAD phosphorylation"
                ),
                "authors_text": (
                    "Pandey, V., Wang, B., Mohan, C. D., Raquib, A. R., "
                    "Rangappa, S., Srinivasa, V., Fuchs, J. E., Girish, K. S., "
                    "Zhu, T., Bender, A., Ma, L., Yin, Z., Basappa, Rangappa, "
                    "K. S. and Lobie, P. E."
                ),
                "venue_text": "Proc Natl Acad Sci U S A",
                "year": 2018,
                "source_span": source_spans[1],
                "confidence": 0.92,
            },
            {
                "title": (
                    "Two-Dimensional Porphyrin-Based Covalent Organic Frameworks "
                    "for Visible-Light-Driven Oxidative Coupling of Benzylamines"
                ),
                "authors_text": "Zhao, Q.-R.; Wang, K.; Gao, X.; Tan, C.",
                "venue_text": "Chem. Commun.",
                "year": 2025,
                "source_span": source_spans[2],
                "confidence": 0.93,
            },
            {
                "title": (
                    "Picosecond quantum transients in halide perovskite "
                    "nanodomain superlattices"
                ),
                "authors_text": (
                    "Guo, D.; Selby, T. A.; Kahmann, S.; Gorgon, S.; Dai, L.; "
                    "Dubajic, M.; Yang, T. C.-J.; Fairclough, S. M.; Marsh, T.; "
                    "Jacobs, I. E.; Wu, B.; Guo, R.; Nagane, S.; Doherty, T. A. S.; "
                    "Ji, K.; Liu, C.; Lu, Y.; Kang, T.; Mamak, C.; Mao, J.; "
                    "Muller-Buschbaum, P.; Sirringhaus, H.; Midgley, P. A.; "
                    "Stranks, S. D."
                ),
                "venue_text": "Nature Nanotechnology",
                "year": 2025,
                "source_span": source_spans[3],
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/sample/main.htm",
        llm_extractor=fake_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Large field-of-view lensless holographic dynamic projection system with "
        "uniform illumination and U-net acceleration",
        "Discovery of a small-molecule inhibitor of specific serine residue BAD "
        "phosphorylation",
        "Two-Dimensional Porphyrin-Based Covalent Organic Frameworks for "
        "Visible-Light-Driven Oxidative Coupling of Benzylamines",
        "Picosecond quantum transients in halide perovskite nanodomain superlattices",
    ]
    assert publications[0].authors_text is not None
    assert "Ping Su" in publications[0].authors_text
    assert publications[1].authors_text is not None
    assert "V. Pandey" in publications[1].authors_text
    assert publications[2].venue_text is not None
    assert "Chem. Commun" in publications[2].venue_text
    assert publications[3].year == 2025


def test_llm_publication_prompt_prioritizes_titles_over_author_variants():
    messages = build_llm_publication_extraction_messages(
        section_text=(
            "Liu, Xinjuan#; Zhang, Xi; Zhou, Yong. High-performance polymer "
            "membranes for selective ion transport. Advanced Materials, 2025."
        ),
        page_url="https://example.edu/faculty",
    )

    prompt = "\n".join(message["content"] for message in messages)

    assert "title is the primary lookup key" in prompt
    assert "never return an author list as `title`" in prompt
    assert "Authors may appear in many formats" in prompt
    assert '"confidence": 0.95' in prompt
    assert "Use confidence >= 0.9" in prompt


def test_sigs_llm_fallback_rejects_hallucinated_items_and_filters_bad_rules():
    bad_rule_span = (
        "Ping Su, Junrong Wang, Chao Cai, et al. Large field-of-view lensless "
        "holographic dynamic projection system with uniform illumination and "
        "U-net acceleration. Optics and Lasers in Engineering, 2022"
    )
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <div><span>[1] {bad_rule_span}</span></div>
    </main>
    """

    def hallucinating_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "Invented paper title that is not on the page",
                "authors_text": "Invented Author",
                "venue_text": "Invented Venue",
                "year": 2026,
                "source_span": bad_rule_span,
                "confidence": 0.99,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/sp_548/main.htm",
        llm_extractor=hallucinating_llm,
        force_llm=True,
    )

    assert publications == []


def test_sigs_llm_fallback_rejects_author_prefix_contaminated_titles():
    source_span = (
        "Guo, D.; Selby, T. A.; Kahmann, S.; Gorgon, S.; Dai, L.; "
        "Dubajic, M.; Yang, T. C.-J.; Fairclough, S. M.; Marsh, T.; "
        "Jacobs, I. E.; Wu, B.; Guo, R.; Nagane, S.; Doherty, T. A. S.; "
        "Ji, K.; Liu, C.; Lu, Y.; Kang, T.; Mamak, C.; Mao, J.; "
        "Muller-Buschbaum, P.; Sirringhaus, H.; Midgley, P. A.; "
        "Stranks, S. D. Picosecond quantum transients in halide perovskite "
        "nanodomain superlattices. Nature Nanotechnology 2025, 20, "
        "1771-1778."
    )
    contaminated_title = (
        "S.; Ji, K.; Liu, C.; Lu, Y.; Kang, T.; Mamak, C.; Mao, J.; "
        "Muller-Buschbaum, P.; Sirringhaus, H.; Midgley, P. A.; "
        "Stranks, S. D. Picosecond quantum transients in halide perovskite "
        "nanodomain superlattices"
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": contaminated_title,
                "authors_text": "Guo, D.; Selby, T. A.; Kahmann, S.",
                "venue_text": "Nature Nanotechnology",
                "year": 2025,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Picosecond quantum transients in halide perovskite "
                    "nanodomain superlattices"
                ),
                "authors_text": (
                    "Guo, D.; Selby, T. A.; Kahmann, S.; Gorgon, S.; Dai, L.; "
                    "Dubajic, M.; Yang, T. C.-J.; Fairclough, S. M.; Marsh, T.; "
                    "Jacobs, I. E.; Wu, B.; Guo, R.; Nagane, S.; "
                    "Doherty, T. A. S.; Ji, K.; Liu, C.; Lu, Y.; Kang, T.; "
                    "Mamak, C.; Mao, J.; Muller-Buschbaum, P.; Sirringhaus, H.; "
                    "Midgley, P. A.; Stranks, S. D."
                ),
                "venue_text": "Nature Nanotechnology",
                "year": 2025,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/Guo%20Dengyang/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Picosecond quantum transients in halide perovskite nanodomain "
        "superlattices"
    ]


def test_sigs_llm_fallback_rejects_author_year_prefix_titles():
    source_span = (
        "Qiu, H.; Lee, C.* (2019). Frailty is Associated with an Increased "
        "Risk of Major Adverse Outcomes in Elderly Patients Following Surgical "
        "Treatment of Hip Fracture. Journal of Orthopaedic Surgery, 2019."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "C.* (2019). Frailty is Associated with an Increased Risk "
                    "of Major Adverse Outcomes in Elderly Patients Following "
                    "Surgical Treatment of Hip Fracture"
                ),
                "authors_text": "Qiu, H.; Lee, C.",
                "venue_text": "Journal of Orthopaedic Surgery",
                "year": 2019,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Frailty is Associated with an Increased Risk of Major "
                    "Adverse Outcomes in Elderly Patients Following Surgical "
                    "Treatment of Hip Fracture"
                ),
                "authors_text": "Qiu, H.; Lee, C.",
                "venue_text": "Journal of Orthopaedic Surgery",
                "year": 2019,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/qhj/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Frailty is Associated with an Increased Risk of Major Adverse Outcomes "
        "in Elderly Patients Following Surgical Treatment of Hip Fracture"
    ]


def test_sigs_llm_fallback_rejects_connective_author_year_prefix_titles():
    source_span = (
        "Jirka and D. Chen (1995), Large scale planar laser induced fluorescence "
        "in turbulent density stratified flows. Journal of Fluid Mechanics, 1995."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "Jirka and D. Chen (1995), Large scale planar laser induced "
                    "fluorescence in turbulent density stratified flows"
                ),
                "authors_text": "Jirka and D. Chen",
                "venue_text": "Journal of Fluid Mechanics",
                "year": 1995,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": "Chen and D. Chen",
                "authors_text": "Chen and D. Chen",
                "venue_text": "Journal of Fluid Mechanics",
                "year": 1995,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Large scale planar laser induced fluorescence in turbulent "
                    "density stratified flows"
                ),
                "authors_text": "Jirka and D. Chen",
                "venue_text": "Journal of Fluid Mechanics",
                "year": 1995,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/cdy/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Large scale planar laser induced fluorescence in turbulent density "
        "stratified flows"
    ]


def test_sigs_llm_fallback_rejects_chinese_author_prefix_titles():
    source_span = (
        "郭昱君、关翎、邱亨嘉*、杨燕绥。临床路径对医疗资源使用的效益-以腹腔镜"
        "胆囊切除手术患者为例。中国卫生政策研究，2020。"
    )
    contaminated_title = (
        "郭昱君、关翎、邱亨嘉*、杨燕绥。临床路径对医疗资源使用的效益-以腹腔镜"
        "胆囊切除手术患者为例"
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": contaminated_title,
                "authors_text": "郭昱君、关翎、邱亨嘉*、杨燕绥",
                "venue_text": "中国卫生政策研究",
                "year": 2020,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": "临床路径对医疗资源使用的效益-以腹腔镜胆囊切除手术患者为例",
                "authors_text": "郭昱君、关翎、邱亨嘉*、杨燕绥",
                "venue_text": "中国卫生政策研究",
                "year": 2020,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/qhj/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "临床路径对医疗资源使用的效益-以腹腔镜胆囊切除手术患者为例"
    ]


def test_sigs_llm_fallback_rejects_ampersand_author_only_titles():
    source_span = (
        "Ping Su, Wenbo Cao&. Jianshe Ma*, Bingchao Cheng, Xianting Liang. "
        "Fast computer-generated hologram generation method for "
        "three-dimensional point cloud model. Optics Express, 2023."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "Wenbo Cao&",
                "authors_text": "Ping Su",
                "venue_text": "Optics Express",
                "year": 2023,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Fast computer-generated hologram generation method for "
                    "three-dimensional point cloud model"
                ),
                "authors_text": (
                    "Ping Su, Wenbo Cao&. Jianshe Ma*, Bingchao Cheng, "
                    "Xianting Liang"
                ),
                "venue_text": "Optics Express",
                "year": 2023,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/sp_548/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Fast computer-generated hologram generation method for "
        "three-dimensional point cloud model"
    ]


def test_sigs_llm_fallback_rejects_ampersand_author_list_titles():
    source_span = (
        "Zhenpeng Luo &, Jianshe Ma, Ping Su*, and Liangcai Cao*. "
        "Digital holographic phase imaging based on phase iteratively enhanced "
        "compressive sensing. Optics Letters, 2021."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "Zhenpeng Luo &, Jianshe Ma, Ping Su*, and Liangcai Cao*",
                "authors_text": None,
                "venue_text": "Optics Letters",
                "year": 2021,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Digital holographic phase imaging based on phase iteratively "
                    "enhanced compressive sensing"
                ),
                "authors_text": (
                    "Zhenpeng Luo &, Jianshe Ma, Ping Su*, and Liangcai Cao*"
                ),
                "venue_text": "Optics Letters",
                "year": 2021,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sigs.tsinghua.edu.cn/sp_548/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Digital holographic phase imaging based on phase iteratively enhanced "
        "compressive sensing"
    ]


def test_llm_fallback_auto_triggers_for_non_sigs_suspicious_rule_title():
    source_span = (
        "Liu, Xinjuan#; Zhang, Xi; Zhou, Yong. High-performance polymer "
        "membranes for selective ion transport. Advanced Materials, 2025."
    )
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <p>{source_span}</p>
    </main>
    """

    def fake_llm(section_text: str, page_url: str):
        assert "Advanced Materials" in section_text
        assert page_url == "https://cmce.szu.edu.cn/info/1609/4360.htm"
        return [
            {
                "title": (
                    "High-performance polymer membranes for selective ion "
                    "transport"
                ),
                "authors_text": "Liu, Xinjuan#; Zhang, Xi; Zhou, Yong",
                "venue_text": "Advanced Materials",
                "year": 2025,
                "source_span": source_span,
                "confidence": 0.92,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://cmce.szu.edu.cn/info/1609/4360.htm",
        llm_extractor=fake_llm,
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "High-performance polymer membranes for selective ion transport"
    )
    assert publications[0].authors_text is not None
    assert "Xi Zhang" in publications[0].authors_text


def test_llm_fallback_auto_triggers_for_non_sigs_low_rule_recall():
    source_span = (
        "J. Wang, M. Li. Robust neural interface control for wearable robotics. "
        "IEEE Transactions on Robotics, 2024."
    )
    html = f"""
    <main>
      <h2>Publications</h2>
      <div><span>{source_span}</span></div>
    </main>
    """

    def fake_llm(section_text: str, _page_url: str):
        assert "IEEE Transactions on Robotics" in section_text
        return [
            {
                "title": (
                    "Robust neural interface control for wearable robotics"
                ),
                "authors_text": "J. Wang, M. Li",
                "venue_text": "IEEE Transactions on Robotics",
                "year": 2024,
                "source_span": source_span,
                "confidence": 0.91,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://example.edu/faculty/wang",
        llm_extractor=fake_llm,
    )

    assert [publication.clean_title for publication in publications] == [
        "Robust neural interface control for wearable robotics"
    ]


def test_llm_fallback_preserves_safe_rule_results_while_fixing_suspicious_items():
    safe_span = (
        "Zhang Q, Li M. Novel Optical Sensor Based on Photonic Crystal "
        "Structures. Optics Express, 2024, 32(5): 123-134."
    )
    suspicious_span = (
        "Liu, Xinjuan#; Zhang, Xi; Zhou, Yong. High-performance polymer "
        "membranes for selective ion transport. Advanced Materials, 2025."
    )
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <p>{safe_span}</p>
      <p>{suspicious_span}</p>
    </main>
    """

    def fake_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": (
                    "High-performance polymer membranes for selective ion "
                    "transport"
                ),
                "authors_text": "Liu, Xinjuan#; Zhang, Xi; Zhou, Yong",
                "venue_text": "Advanced Materials",
                "year": 2025,
                "source_span": suspicious_span,
                "confidence": 0.92,
            }
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://cmce.szu.edu.cn/info/1609/4360.htm",
        llm_extractor=fake_llm,
    )

    assert [publication.clean_title for publication in publications] == [
        "Novel Optical Sensor Based on Photonic Crystal Structures",
        "High-performance polymer membranes for selective ion transport",
    ]
