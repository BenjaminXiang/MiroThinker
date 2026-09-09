from __future__ import annotations

import pytest

from src.data_agents.professor.homepage_publications import (
    HomepagePublication,
    _is_suspicious_rule_publication,
    _split_compact_initial_connective_author_segment,
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
      <p>[1] On Universal Features for High-Dimensional Learning and Inference.
      accepted to Foundations and Trends in Communications and Information
      Theory: Now Publishers. (ArXiv)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc2/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Self-Adaptive Double bootstrapped DDPG",
        "Bridge the Gap: High-level Semantic Planning for Image Captioning",
        "On Universal Features for High-Dimensional Learning and Inference",
    ]
    assert "Hanghao Wu" in (publications[0].authors_text or "")
    assert "Chun Yuan" in (publications[1].authors_text or "")
    assert "IJCAI 2018 (CCF A)" in (publications[0].venue_text or "")
    assert publications[1].venue_text == "Coling2020 CCF B"
    assert "Foundations and Trends in Communications and Information Theory" in (
        publications[2].venue_text or ""
    )
    assert "ArXiv" in (publications[2].venue_text or "")
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


def test_sigs_chinese_single_author_et_al_period_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>汪劲松等. 双组元液压自由活塞发动机的研究背景与可行性分析.
      中国机械工程，2008。</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xbz/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "双组元液压自由活塞发动机的研究背景与可行性分析"
    assert publications[0].authors_text == "汪劲松"
    assert publications[0].venue_text is not None
    assert "中国机械工程" in publications[0].venue_text
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_chinese_single_author_compact_period_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>蔡中华.基于矩阵模型进行抗荧光干扰的蓝藻原位检测方法.湖泊科学</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/czh/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "基于矩阵模型进行抗荧光干扰的蓝藻原位检测方法"
    assert publications[0].authors_text == "蔡中华"
    assert publications[0].venue_text == "湖泊科学"
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


def test_initial_connective_author_comma_prefix_reaches_real_title():
    raw = (
        "[2].T.W. Wu and Y.L. Ma, Doubly heavy tetraquark multiplets as heavy "
        "antiquark-diquark symmetry partners of heavy baryons, Phys.Rev.D 107 "
        "(2023) 7, L071501."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Doubly heavy tetraquark multiplets as heavy antiquark-diquark symmetry "
        "partners of heavy baryons"
    )
    assert authors == "T.W. Wu, Y.L. Ma"
    assert venue == "Phys.Rev.D 107 (2023) 7, L071501"


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
      <p>G. M. Zhou, S. F. Pei, L. Li, D. W. Wang, S. G. Wang, K. Huang,
      L. C. Yin, F. Li, H.-M. Cheng, A Graphene-Pure Sulphur Sandwich
      Structure for Ultrafast, Long-Life Lithium–Sulphur Batteries, Adv. Mater,
      2014, 26, 625–631.</p>
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
        ),
        (
            "A Graphene-Pure Sulphur Sandwich Structure for Ultrafast, "
            "Long-Life Lithium–Sulphur Batteries"
        ),
    ]
    assert "Baohua Li" in (publications[0].authors_text or "")
    assert "Chemical Reviews" in (publications[0].venue_text or "")
    assert "Adv Mater" in (publications[1].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])
    assert not _is_suspicious_rule_publication(publications[1])


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

    assert publications == []


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
        "ORCID: 0000-0002-9903-3798",
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


def test_sigs_orcid_identifier_line_is_not_publication():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>ORCID: 0000-0002-9903-3798</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert publications == []


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


def test_sigs_repairs_scientific_title_words_split_by_html_spacing():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Long- l ife Li/polysulphide b atteries with high sul ph ur loading
      enabled by l ightweight t hree- d imensional n itrogen/sulphur
      c o d oped g raphene s ponge</p>
      <p>Catalytic o xidation of Li 2 S on the s urface of m etal s ulphides
      for Li-S b atteries</p>
      <p>Effect m echanism of f low v elocity on i ron r elease from p ipe
      s urfaces in d rinking w ater d istribution s ystems. T he 37 th IAHR
      World Congress</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Long-life Li/polysulphide batteries with high sulphur loading "
            "enabled by lightweight three-dimensional nitrogen/sulphur codoped "
            "graphene sponge"
        ),
        (
            "Catalytic oxidation of Li 2 S on the surface of metal sulphides "
            "for Li-S batteries"
        ),
        (
            "Effect mechanism of flow velocity on iron release from pipe surfaces "
            "in drinking water distribution systems"
        ),
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
      <p>杨诚老师长期从事面向电化学能源以及传感、封装方面应用的关键材料的研究工作。
      着重研究金属微纳结构的形态演变规律和控制方法，提出了一系列以热力学非平衡态
      条件为主要特征的实验手段。应用领域包括金属电化学电极、元器件封装、传感器等方面。</p>
      <p>目前已发表专业论文170余篇、引用1万余次，获得中美国发明专利授权50余项、
      成果转化6项。获得了日内瓦国际发明奖金奖、中国发明创新奖等荣誉。</p>
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
      <p>[8] Wang R, Chan J. F-W, Wang S, Li H, Zhao J, Ip K-Y, Zuo Z,
      Yuen K-K, Yuan S*, Sun H*, Chem. Sci., 2022, 13, 2238-2248
      [Back cover]</p>
      <p>[9] Nairan A.; Yang C.* et al. Advanced Functional Materials
      2019, 29, 1903747 (featured as back cover)</p>
      <p>[10] Zhao S.; Yang C.* et al. InfoMat, 2024, e12552</p>
      <p>[11] Zhang Z.; Yang C.* et al. Small, 2023,19, 2300747</p>
      <p>[12] Zhu H.; Yang C.* et al. Angewandte Chemie International Edition.
      2022,62, e202212439</p>
      <p>[13] Liang C.; Yang C.* et al. Small, 2022, 18, 2203663</p>
      <p>[14] Yang C.* et al. Nature Communications 2015, 9150
      (Highlighted by C&EN)</p>
      <p>[15] Yang C.: “Applying Nanotechnology to Composite Materials ---
      Multifunctionality & Mechanical Properties” VDM publishing house,
      Saarbrücken, 2009, 199 pages. ISBN: 978-3-639-10882-8 （学术专著）</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Spectrally Efficient Channel State Information Acquisition for Power "
        "Line Communications: A Bayesian Compressive Sensing Perspective",
        "Applying Nanotechnology to Composite Materials --- Multifunctionality "
        "& Mechanical Properties",
    ]


def test_sigs_ercan_author_chain_extracts_real_title_and_filters_page_fragments():
    html = """
    <main>
      <h2>Publications</h2>
      <p>203. Elsevier, May 2016.</p>
      <p>53-A, pp. 79-83, December 2014.</p>
      <p>53. E. E. Kuruoglu, W. J. Fitzgerald and P. J. W. Rayner,
      Near Optimal Detection of Signals in Impulsive Noise Modelled with a
      Symmetric alpha-Stable Distribution, IEEE Communications Letters,
      Vol. 2, No. 10, pp. 282-284, October 1998.</p>
      <p>54. E. E. Kuruoglu, P. J. W. Rayner and W. J. Fitzgerald,
      Least lp-norm Impulsive Noise Cancellation with Polynomial Filters,
      Signal Processing, Vol. 69, No. 1, pp. 1-14, 1998.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/Ercan/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Near Optimal Detection of Signals in Impulsive Noise Modelled "
            "with a Symmetric alpha-Stable Distribution"
        ),
        "Least lp-norm Impulsive Noise Cancellation with Polynomial Filters",
    ]
    assert "E. E. Kuruoglu" in (publications[0].authors_text or "")
    assert "P. J. W. Rayner" in (publications[0].authors_text or "")
    assert "IEEE Communications Letters" in (publications[0].venue_text or "")
    assert "Signal Processing" in (publications[1].venue_text or "")


def test_sigs_numbered_publication_split_across_paragraphs_is_merged():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[1] Li Y, Xu W. A deep learning-based framework for intelligent
      modeling: From architectural</p>
      <p>sketch to 3D model[J]. Frontiers of Architectural Research,
      2025 (In press).</p>
      <p>[2] 黄舒弈, 徐卫国. 基于 3D 打印混凝土技术的建筑学交叉学科研究新路径探索[J].
      建筑学报, 2024,</p>
      <p>30(S2): 176-182.</p>
      <p>[3] Huang S, Xu W, Anton A, Dillenburger B. Self-supporting
      lamellae: Shape variation methods</p>
      <p>for the 3D concrete printing of large overhang structures[J].
      Additive Manufacturing, 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xwg/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "A deep learning-based framework for intelligent modeling: From "
        "architectural sketch to 3D model",
        "基于 3D 打印混凝土技术的建筑学交叉学科研究新路径探索",
        (
            "Self-supporting lamellae: Shape variation methods for the 3D "
            "concrete printing of large overhang structures"
        ),
    ]
    assert "30(S2)" in (publications[1].venue_text or "")
    assert "sketch to 3D model" not in {
        publication.clean_title for publication in publications[1:]
    }


def test_sigs_numbered_publications_in_same_paragraph_are_split():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[14] 徐卫国. 数字建筑设计与建造的发展前景[J]. 当代建筑,
      2020, No.2(02): 20-22. [15] 徐卫国. 世界最大的混凝土
      3D 打印步行桥[J]. 建筑技艺, 2019, 281(02): 6-9.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xwg/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "数字建筑设计与建造的发展前景",
        "世界最大的混凝土 3D 打印步行桥",
    ]
    assert "当代建筑" in (publications[0].venue_text or "")
    assert "建筑技艺" in (publications[1].venue_text or "")


def test_sigs_english_numbered_publications_in_same_paragraph_are_split():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[4].T.W. Wu, M.Z. Liu and L.S. Geng，Excited K meson,
      Kc(4180), with hidden charm as a DDbarK bound state,
      Phys.Rev.D 103 (2021) 3, L031501 [5].T.W. Wu, M.Z. Liu,
      L.S. Geng et al. DK,DDK, and DDDK molecules- understanding
      the nature of the Ds0(2317), Phys.Rev.D 100 (2019) 3, 034029.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://science.sysu.edu.cn/teacher/WuTianwei",
    )

    assert [publication.clean_title for publication in publications] == [
        "Kc(4180), with hidden charm as a DDbarK bound state",
        "DK, DDK, and DDDK molecules-understanding the nature of the Ds0(2317)",
    ]
    assert "Phys.Rev.D 103" in (publications[0].venue_text or "")
    assert "[5]" not in (publications[0].venue_text or "")
    assert "Phys.Rev.D 100" in (publications[1].venue_text or "")


def test_sigs_non_publication_title_noise_is_suspicious_at_bridge_boundary():
    for title in (
        "Zhidong Jia",
        "Yong Tian etc",
        "Mingwang Wang etc",
        "Zhihui Xu and Weiwei Zheng",
        "Sun Wei and Xu Zhihui",
        "在 Science, Nature Materials",
        "发表 SCI 论文 200 多篇，其中 Nature 论文 3 篇",
        "请见 https://www.sigs.tsinghua.edu.cn/sample/main.htm",
        "具体发表详见 https://scholar.google.com/citations?hl=en&user=Nm3ZGrQAAAAJ",
        "具体发表情况详见： https://scholar.google.com/citations?user=9-7kE_QAAAAJ",
        "For the complete publication list, please refer to",
        "WOS:000123456789",
        "EI Accession number: 202612345678",
        "Ã©Ã¨â€™ malformed title",
        "l Research Highlight 1#",
        "Research Highlight 2#: Alberto Moscatelli (Chief Editor of Nature "
        "Nanotechnology), A 2D material-based liquid crystal for "
        "deep-ultraviolet light modulation (Research Briefing)",
        "Reported by EurekAlert! (AAAS), etc",
        "Reported by the EurekAlert! (AAAS), Nanowerk, Physorg, "
        "Tsinghua News, etc",
        "As Corresponding Author",
        "Scientific Reports, IF/citations: 4/-, in press *",
        "杨 兵, * 高福平, 吴应湘",
        "杨诚老师长期从事面向电化学能源以及传感、封装方面应用的关键材料的研究工作。"
        "应用领域包括金属电化学电极、元器件封装、传感器等方面",
        "目前已发表专业论文 170余篇、引用1万余次，获得中美国发明专利授权50余项、"
        "成果转化6项。获得了日内瓦国际发明奖金奖、中国发明创新奖等荣誉",
        "2022, 13, 2238-2248 [Back cover]",
        "Advanced Functional Materials 2019, 29, 1903747 (featured as back cover)",
        "35, 2207787. (Front Cover Article)",
        "Advanced Functional Materials 2010, 20, 2580 (featured as frontispiece)",
        "Commum., 2018, 9, 439",
        "Nat. Commun., 2018, 9, 439",
        "ACS Nano 2015, 9, 5636",
        "Advanced Functional Materials2021, 31, 2105736",
        "Chemical Reviews 2021, 121, 10, 5986-6056",
        "Electrochemical Energy Reviews",
        "Electrochemical Energy Reviews 2021, 4, 601-631",
        "Nano Energy 2018, 51, 349",
        "Nature Communications 2018, 9, 464",
        "Nature Communications 2015, 9150 (Highlighted by C&EN)",
        "et al. InfoMat",
        "et al. Small",
        "et al. Angewandte Chemie International Edition",
        "Advanced Science",
        "Advanced Energy Materials",
        "Advanced Functional Materials",
        "Advanced Materials",
        "Chemical Reviews",
        "Energy & Environmental Science",
        "Energy & Environ. Sci",
        "Energy Storage Materials",
        "Journal of the American Chemical Society",
        "Nano Energy",
        "Nature Communications",
        "Elsevier, May 2016",
        "83, December 2014",
        "Fitzgerald and P. J. W. Rayner",
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


def test_sigs_llm_fallback_rejects_venue_only_yang_items_but_keeps_book_title():
    source_span = (
        "Yang C.* et al. Nature Communications 2015, 9150 "
        "(Highlighted by C&EN)"
    )
    book_span = (
        "Yang C.: “Applying Nanotechnology to Composite Materials --- "
        "Multifunctionality & Mechanical Properties” VDM publishing house, "
        "Saarbrücken, 2009, 199 pages. ISBN: 978-3-639-10882-8 （学术专著）"
    )
    html = f"""
    <main>
      <h2>代表性论文</h2>
      <p>{source_span}</p>
      <p>{book_span}</p>
    </main>
    """

    def yang_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "Nature Communications 2015, 9150 (Highlighted by C&EN)",
                "authors_text": "Yang C. et al",
                "venue_text": None,
                "year": 2015,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Applying Nanotechnology to Composite Materials --- "
                    "Multifunctionality & Mechanical Properties"
                ),
                "authors_text": "Yang C",
                "venue_text": (
                    "VDM publishing house, Saarbrücken, 2009, 199 pages. "
                    "ISBN: 978-3-639-10882-8 （学术专著）"
                ),
                "year": 2009,
                "source_span": book_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/yc/main.htm",
        llm_extractor=yang_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Applying Nanotechnology to Composite Materials --- Multifunctionality "
        "& Mechanical Properties"
    ]


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


def test_sigs_llm_fallback_rejects_chinese_intro_venue_fragment_title():
    source_span = (
        "干林教授在 Science, Nature Materials 等期刊发表多篇论文。"
        "Atomic imaging of subsurface hydrogen and insight into the surface "
        "reactivity of palladium hydrides. Nature Materials, 2024."
    )
    html = f"<main><h2>代表性论文</h2><p>{source_span}</p></main>"

    def bad_then_good_llm(_section_text: str, _page_url: str):
        return [
            {
                "title": "在 Science, Nature Materials",
                "authors_text": None,
                "venue_text": "Science, Nature Materials",
                "year": None,
                "source_span": source_span,
                "confidence": 0.95,
            },
            {
                "title": (
                    "Atomic imaging of subsurface hydrogen and insight into the "
                    "surface reactivity of palladium hydrides"
                ),
                "authors_text": None,
                "venue_text": "Nature Materials",
                "year": 2024,
                "source_span": source_span,
                "confidence": 0.95,
            },
        ]

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/gl1/main.htm",
        llm_extractor=bad_then_good_llm,
        force_llm=True,
    )

    assert [publication.clean_title for publication in publications] == [
        "Atomic imaging of subsurface hydrogen and insight into the surface "
        "reactivity of palladium hydrides"
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


def test_llm_fallback_skips_large_rule_publication_lists(monkeypatch):
    items = [
        (
            f"<p>{index}. A. Author, B. Scientist. Reliable SUSTech "
            f"Publication Title {index} for Batch Ingest. Journal of Testing, "
            "2024.</p>"
        )
        for index in range(1, 82)
    ]
    html = "<main><h2>Publications</h2>" + "".join(items) + "</main>"
    calls: list[str] = []

    monkeypatch.setattr(
        "src.data_agents.professor.homepage_publications."
        "_should_use_llm_publication_fallback",
        lambda **_kwargs: True,
    )

    def _llm_extractor(_section_text: str, page_url: str):
        calls.append(page_url)
        raise AssertionError("large rule-extracted lists should not call the LLM")

    publications = extract_publications_from_html_with_llm_fallback(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/xiao-guozhi.html",
        llm_extractor=_llm_extractor,
    )

    assert calls == []
    assert len(publications) == 81
    assert publications[0].clean_title == (
        "Reliable SUSTech Publication Title 1 for Batch Ingest"
    )


def test_sigs_jcr_if_tail_after_comma_author_prefix_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[6] Xi Cheng, Pingfa Feng, Long Zeng* , Approaching optimum sampling
      by sectional error equivalence, M easurement (JCR Q1, IF5.2), 2024.</p>
      <p>[17] Fei Liu, XiaoMing Zhu, PingFa Feng, Long Zeng* , Anomaly
      Detection via Progressive Reconstruction and Hierarchical Feature Fusion,
      Sensors (JCR Q2, IF3.9), MDPI, 2023.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/cl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Approaching optimum sampling by sectional error equivalence",
        "Anomaly Detection via Progressive Reconstruction and Hierarchical Feature Fusion",
    ]
    assert all("JCR" not in publication.clean_title for publication in publications)
    assert all("IF" not in publication.clean_title for publication in publications)
    assert "Long Zeng" in (publications[0].authors_text or "")
    assert "Measurement" in (publications[0].venue_text or "").replace(" ", "")
    assert "Sensors" in (publications[1].venue_text or "")


def test_sigs_doi_only_metric_rows_are_suspicious_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>40. DOI: 10.37188/lam.2025.040.(IF=10.6, JCR Q1)</p>
      <p>116147. DOI: 10.1016/j.measurement.2024.116147.(IF=5.6,
      JCR Q1, 中科院 2区)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lxh/main.htm",
    )

    assert publications == []


def test_sigs_chinese_ampersand_author_year_prefix_splits_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>80. 杨朋 , & 缪立新 . (2012). 多载具自动化存取系统性能评价研究 .
      工业工程 , 15(4), 21-27.</p>
      <p>39. 李彬彬，欧进萍， Truss Spar平台垂荡响应频域分析，海洋工程，2009</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/mlx/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "多载具自动化存取系统性能评价研究",
        "Truss Spar平台垂荡响应频域分析",
    ]
    assert publications[0].authors_text == "杨朋, 缪立新"
    assert publications[1].authors_text == "李彬彬, 欧进萍"
    assert "工业工程" in (publications[0].venue_text or "")
    assert "海洋工程" in (publications[1].venue_text or "")


def test_sigs_split_connective_author_fragment_before_title_is_repaired():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[56] Wang Chong # , Liu Kaiyuan # , Zhang Canrong *, a nd Miao
      Lixin. Distributionally Robust Chance-Constrained Optimization for the
      Integrated Berth Allocation and Quay Crane Assignment Problem.
      Transportation Research Part B: Methodological, April 2024, 182:
      102923.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/zcr/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Distributionally Robust Chance-Constrained Optimization for the "
        "Integrated Berth Allocation and Quay Crane Assignment Problem"
    )
    assert "Zhang Canrong" in (publications[0].authors_text or "")
    assert "Miao Lixin" in (publications[0].authors_text or "")
    assert "Transportation Research Part B" in (publications[0].venue_text or "")


def test_sigs_student_marked_initial_author_chain_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[25] F. Yang （学生） , k. Wu, S. Y. Zhang, G. N. Jiang, Y. Liu,
      F. Zheng, W. Zhang, C. J. Wang and L. Zeng , Class-Aware Contrastive
      Semi-Supervised Learning, 2022 IEEE Computer Vision and Pattern
      Recognition (CVPR2022, CCF-A).</p>
      <p>[36] Y. F. Xu （学生） , T. Fan, M. Xu, L. Zeng . SpiderCNN: Deep
      Learning on Point Sets with Parameterized Convolutional Filters, ECCV
      2018 ( 全球计算机视觉三大会议之一 ，谷歌学术引用数 > 800 次 ).</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/cl/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Class-Aware Contrastive Semi-Supervised Learning",
        "SpiderCNN: Deep Learning on Point Sets with Parameterized Convolutional Filters",
    ]
    assert "F. Yang" in (publications[0].authors_text or "")
    assert "L. Zeng" in (publications[0].authors_text or "")
    assert "Y. F. Xu" in (publications[1].authors_text or "")
    assert "L. Zeng" in (publications[1].authors_text or "")
    assert "CVPR2022" in (publications[0].venue_text or "")
    assert "ECCV 2018" in (publications[1].venue_text or "")


def test_sigs_metric_journal_tail_after_period_is_not_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>26. Yuchun Yang, Jie Pan, Zhichao Zhou, Jiapeng Wu, Yang Liu,
      Jih-Gaw Lin, Yiguo Hong, Xiao-yan Li , Meng Li, Ji-Dong Gu. 2020.
      Complex microbial nitrogen-cycling networks in three distinct
      anammox-inoculated wastewater treatment systems. Water research
      (IF: 11.236), 168, 115142.</p>
      <p>35. Guang-Jie Zhou, Xiao-yan Li , Kenneth Mei Yee Leung. 2019.
      Retinoids and oestrogenic endocrine disrupting chemicals in saline
      sewage treatment plants: Removal efficiencies and ecological risks to
      marine organisms. Environment international (IF: 9.621), 127, 103-113.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lxy/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Complex microbial nitrogen-cycling networks in three distinct "
            "anammox-inoculated wastewater treatment systems"
        ),
        (
            "Retinoids and oestrogenic endocrine disrupting chemicals in saline "
            "sewage treatment plants: Removal efficiencies and ecological risks "
            "to marine organisms"
        ),
    ]
    assert "Water research" in (publications[0].venue_text or "")
    assert "Environment international" in (publications[1].venue_text or "")
    assert all("IF" not in publication.clean_title for publication in publications)


def test_sigs_chinese_and_english_author_prefix_splits_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>11. 毛献忠，祝倩， Wei Yong, 浙江沿海潜在区域地震海啸风险分析 ,
      海洋学报， 2015 ， 37 （ 3 ）： 37-45 。</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/mxz/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "浙江沿海潜在区域地震海啸风险分析"
    assert publications[0].authors_text == "毛献忠, 祝倩, Wei Yong"
    assert "海洋学报" in (publications[0].venue_text or "")


def test_sigs_repairs_split_information_theory_title_words():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[8] Jie Hao, Jun Zhang, Shu-Tao Xia, Fang-Wei Fu, Yixian Yang.
      C onstructions and weight distributions of optimal locally repairable
      codes, IEEE Transactions on Communications (TCOM), vol. 70, no. 5,
      pp. 2895-2908, May 2022.</p>
      <p>[24] S.-T. Xia, F.-W. Fu, and S. Ling, A l ower b ound on the
      p robability of u ndetected e rror for b inary c onstant w eight c odes.
      IEEE Transactions on Information Theory, vol. 52, no. 9, 2006.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/xst/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "Constructions and weight distributions of optimal locally repairable codes",
        (
            "A lower bound on the probability of undetected error for binary "
            "constant weight codes"
        ),
    ]
    assert "Shu-Tao Xia" in (publications[0].authors_text or "")
    assert "IEEE Transactions on Communications" in (publications[0].venue_text or "")


def test_sigs_chinese_author_ampersand_year_prefix_splits_all_authors():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>19. 沈欣炜, 郭庆来, 许银亮 & 孙宏斌 (2019), 考虑多能负荷不确定性的
      区域综合能源系统鲁棒规划, 电力系统自动化, Vol. 43 No. 07, pp.
      34-41.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sxw/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "考虑多能负荷不确定性的区域综合能源系统鲁棒规划"
    assert publications[0].authors_text == "沈欣炜, 郭庆来, 许银亮, 孙宏斌"
    assert "电力系统自动化" in (publications[0].venue_text or "")


def test_sigs_chinese_author_quote_prefix_splits_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>8) 杨舰、刘丹鹤“曼哈顿工程与科学家的社会责任”，《哈尔滨工业大学学报
      （社会科学版）》 2005 年 4 期。 pp.1-7 。</p>
      <p>44) 闫新芳，杨舰“洋务留学生伍光建与卡尔·皮尔逊的交往”，
      《自然科学史研究》， 41 卷，第 2 期（ 2022 ）： 234-249.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/Yang Jian/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        "曼哈顿工程与科学家的社会责任",
        "洋务留学生伍光建与卡尔·皮尔逊的交往",
    ]
    assert publications[0].authors_text == "杨舰, 刘丹鹤"
    assert publications[1].authors_text == "闫新芳, 杨舰"
    assert "哈尔滨工业大学学报" in (publications[0].venue_text or "")
    assert "自然科学史研究" in (publications[1].venue_text or "")


def test_sigs_metric_and_lowercase_continuation_fragments_are_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>他引次数 14399 +</p>
      <p>with Roger Zhan and Max Shen</p>
      <p>from polytitanium-coagulated sludge as an adsorbent or photocatalyst
      for pollutant removals</p>
      <p>for Visible Light Driven High-Rate Photodegradation of Carbamazepine</p>
      <p>based Nanosystem for Cancer Therapy and Antimicrobial Treatment:
      A Review</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/lxy/main.htm",
    )

    assert publications == []


def test_sigs_final_author_dot_prefixes_are_not_kept_in_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[ 5 ] B . Sun, G . Haunschild, C. Polanco, J. Ju, L. Lindsay,
      G. Koblmüller, Y.K. Koh. Dislocation-induced thermal transport
      anisotropy in single-crystal group-III nitride films. Nature Materials
      2019, 18(2): 136-140.</p>
      <p>[10] S.-X. Cao , A. Main, K.G. Wang. Robin-Neumann transmission
      conditions for fluid-structure coupling: Embedded boundary implementation
      and parameter analysis. International Journal for Numerical Methods in
      Engineering. 2018;115(5):578-603.</p>
      <p>[11] H. Chung, S.-X. Cao , M. Philen, P.S. Beran, K.G. Wang.
      CFD-CSD coupled analysis of underwater propulsion using a biomimetic
      fin-and-joint system. Computers & Fluids. 2018; 172(8): 54-66.</p>
      <p>[13] Yong Wang* , Wenli Li, Brett Baker, Yingli Zhou, Lisheng He,
      Antoine Danchin, Qingmei Li, Zhaoming. Carbon metabolism and adaptation
      of hyperalkaliphilic microbes in serpentinizing spring of Manleluag,
      the Philippines. Environ. Microbiol. Rep. 2022,14: 308-319</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Dislocation-induced thermal transport anisotropy in single-crystal "
            "group-III nitride films"
        ),
        (
            "Robin-Neumann transmission conditions for fluid-structure coupling: "
            "Embedded boundary implementation and parameter analysis"
        ),
        (
            "CFD-CSD coupled analysis of underwater propulsion using a biomimetic "
            "fin-and-joint system"
        ),
        (
            "Carbon metabolism and adaptation of hyperalkaliphilic microbes in "
            "serpentinizing spring of Manleluag, the Philippines"
        ),
    ]
    assert "Y.K. Koh" in (publications[0].authors_text or "")
    assert "K.G. Wang" in (publications[1].authors_text or "")
    assert "K.G. Wang" in (publications[2].authors_text or "")
    assert "Zhaoming" in (publications[3].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_month_marker_between_authors_and_title_is_removed():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Chen, X., Purohit, A., Dominguez, C.R., Carpin, S. and Zhang, P.,
      2015, November. Drunkwalk: Collaborative and adaptive planning for
      navigation of micro-aerial sensor swarms. In Proceedings of the 13th
      ACM Conference on Embedded Networked Sensor Systems (pp. 295-308).</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/cxl/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Drunkwalk: Collaborative and adaptive planning for navigation of "
        "micro-aerial sensor swarms"
    )
    assert "P. Zhang" in (publications[0].authors_text or "")
    assert "ACM Conference on Embedded Networked Sensor Systems" in (
        publications[0].venue_text or ""
    )
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_marked_author_continuation_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>[2] Sun, Mingze& and Guo, Chen& and Jiang, Puhua& and Mao, Shiwei&,
      Chen, Yurun& and Huang, Ruqi*, SRIF: Semantic Shape Registration
      Empowered by Image Morphing and Flow Estimation, Siggraph Asia, 2024</p>
      <p>[1] Chao Yu *, Akash Velu*, Eugene Vinitsky, Jiaxuan Gao, Yu Wang + ,
      Alexandre Bayen + , Yi Wu + . The Surprising Effectiveness of PPO in
      Cooperative Multi-agent Games. in Advances in Neural Information
      Processing Systems (NeurIPS) , 2022.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/sample/main.htm",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "SRIF: Semantic Shape Registration Empowered by Image Morphing and "
            "Flow Estimation"
        ),
        "The Surprising Effectiveness of PPO in Cooperative Multi-agent Games",
    ]
    assert "Yurun Chen" in (publications[0].authors_text or "")
    assert "Ruqi Huang" in (publications[0].authors_text or "")
    assert "Alexandre Bayen" in (publications[1].authors_text or "")
    assert "Yi Wu" in (publications[1].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sigs_contribution_legend_is_not_publication():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>* Corresponding Author, & Student under my supervision.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/hrq/main.htm",
    )

    assert publications == []


def test_sustech_chinese_supervision_legend_is_not_publication():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>* 本人指导的研究生</p>
      <p>** 本人指导的本科生</p>
      <p># 共同第一作者</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/sample.html",
    )

    assert publications == []


def test_sustech_long_semicolon_author_chain_with_pinyin_tokens_reaches_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>6. Jiaqi Hu#; Gina Jinna Chen#*; Chenlong Xue; Pei Liang;
      Yanqun Xiang; Chuanlun Zhang; XiaokengChi; Guoying Liu; Yanfang Ye;
      DongyuCui; DeZhang; Xiaojunyu; Hong Dang; Wen Zhang; Junfan Chen;
      Quan Tang; Penglai Guo; Ho-Pui Ho; Yuchao Li; Longqing Cong;
      Perry Ping Shum*; RSPSSL A novel high-fidelity Raman spectral
      preprocessing scheme to enhance biomedical applications and chemical
      resolution visualization, Light: Science & Applications, 2024,
      13(52): 1-21.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/jinnachen.html",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "RSPSSL A novel high-fidelity Raman spectral preprocessing scheme to "
        "enhance biomedical applications and chemical resolution visualization"
    )
    assert "Xiaokeng Chi" in (publications[0].authors_text or "")
    assert "Xiaojunyu" in (publications[0].authors_text or "")
    assert "Perry Ping Shum" in (publications[0].authors_text or "")
    assert "Light: Science & Applications" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sigs_long_ellipsis_author_chain_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>8) Lei, Y. # , Pakhira, S. # , Fujisawa, K., Wang, X.,
      Iyiola, O. O., Perea López, N. s., Laura Elías, A.,
      Pulickal Rajukumar, L., Zhou, C.; Kabius, B., … & Terrones, M.
      Low-temperature Synthesis of Heterostructures of Transition Metal
      Dichalcogenide Alloys (WxMo1-xS2) and Graphene with Superior Catalytic
      Performance for Hydrogen Evolution. ACS nano 2017, 11 (5), 5103-5112.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="http://www.sigs.tsinghua.edu.cn/ly2_4216/main.htm",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Low-temperature Synthesis of Heterostructures of Transition Metal "
        "Dichalcogenide Alloys (WxMo1-xS2) and Graphene with Superior Catalytic "
        "Performance for Hydrogen Evolution"
    )
    assert "Terrones" in (publications[0].authors_text or "")
    assert "ACS nano" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sustech_diamond_bullet_author_period_prefix_splits_titles():
    html = """
    <main>
      <h2>代表文章</h2>
      <p>◆ Wang C, Chen X , Knierim JJ. Egocentric and allocentric
      representations of space in the rodent brain. Curr Opin Neurobiol.
      2019(60):12-20</p>
      <p>◆Wang C*, Chen X *, Lee H, Deshmukh SS, Yoganarasimha D,
      Savelli F, Knierim JJ. Egocentric Coding of External Items in the
      Lateral Entorhinal Cortex；Science；362(6417):945-949；
      (*Co-first author)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/chenxiaojing.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Egocentric and allocentric representations of space in the rodent brain",
        "Egocentric Coding of External Items in the Lateral Entorhinal Cortex",
    ]
    assert "Wang C" in (publications[0].authors_text or "")
    assert "Chen X" in (publications[1].authors_text or "")
    assert "Science" in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_semicolon_author_chain_reaches_real_title():
    html = """
    <main>
      <h2>代表论文</h2>
      <p>(1) Xu, Binbin; Chen, Dafa; Ruan, Kaidong; Luo, Ming; Cai,
      Yuanting; Qiu, Jia; Zhou, Wenhao; Cao, Bula; Lin, Zhenyang,
      Sessler, L. Jonathan; Xia, Haiping*; Metal-centred planar
      [15]annulenes, Nature, 2025, 641, 106.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/chendafa.html",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == "Metal-centred planar [15]annulenes"
    assert "Dafa Chen" in (publications[0].authors_text or "")
    assert "Haiping Xia" in (publications[0].authors_text or "")
    assert "Nature" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sustech_single_marked_author_semicolon_prefix_splits_title():
    html = """
    <main>
      <h2>Selected Publications</h2>
      <p>Xu*; Conjugated linker-boosted SAM molecule for inverted perovskite
      solar cells; Joule, 2024.</p>
      <p>Xu*; Overcoming Two Key Challenges in Monolithic Perovskite-Silicon
      Tandem Solar Cell Development: Wide Bandgap and Textured Substrate-A
      Comprehensive Review. Advanced Energy Materials, 2023.</p>
      <p>Xu*; Bimetallic Phthalocyanine Catalyst for Ammonia Electrosynthesis
      from Nitrate Reduction across All pH Ranges; Applied Catalysis B:
      Environment and Energy, 2025.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/example.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Conjugated linker-boosted SAM molecule for inverted perovskite solar cells",
        (
            "Overcoming Two Key Challenges in Monolithic Perovskite-Silicon Tandem "
            "Solar Cell Development: Wide Bandgap and Textured Substrate-A "
            "Comprehensive Review"
        ),
        (
            "Bimetallic Phthalocyanine Catalyst for Ammonia Electrosynthesis "
            "from Nitrate Reduction across All pH Ranges"
        ),
    ]
    assert [publication.authors_text for publication in publications] == [
        "Xu",
        "Xu",
        "Xu",
    ]
    assert "Joule" in (publications[0].venue_text or "")
    assert "Advanced Energy Materials" in (publications[1].venue_text or "")
    assert "Applied Catalysis B" in (publications[2].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_wos_author_period_continuation_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>3) An J, Zhao X, Wang Y, Noriega J, Gewirtz AT*, Zou J*.
      Western-style diet impedes colonization and clearance of Citrobacter
      rodentium. PLoS Pathog. 2021 Apr</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/anjunqing.html",
    )

    assert len(publications) == 1
    assert publications[0].clean_title == (
        "Western-style diet impedes colonization and clearance of Citrobacter "
        "rodentium"
    )
    assert "Gewirtz AT" in (publications[0].authors_text or "")
    assert "Zou J" in (publications[0].authors_text or "")
    assert "PLoS Pathog" in (publications[0].venue_text or "")
    assert not _is_suspicious_rule_publication(publications[0])


def test_sustech_author_year_and_comma_pair_prefixes_do_not_become_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>35. Li Z*, Chen B, Wei CJ. 2017, Is the Paleoproterozoic
      Jiao-Liao-Ji Belt (North China Craton) a rift? International Journal
      of Earth Sciences, 106: 355-375.</p>
      <p>67. Chen B.*, He J.B., Chen .CJ. and Muhetaer Z., 2013.
      Nd-Sr-Os isotopic data of the Baishiquan mafic-ultramafic complex
      from East Tianshan, and implications for petrogenesis. Acta
      Petrologica Sinica, 29( 1) : 294-302.</p>
      <p>114. Chen B.*, Jahn, B-m., Zhai, M.G., 2003, Sr-Nd isotopic
      characteristics of the Mesozoic magmatism in the Taihang-Yanshan
      orogen, north China craton, and implications for Archean lithosphere
      thinning. J. Geol. Soc., London, 160: 963-970.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/chenbin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Is the Paleoproterozoic Jiao-Liao-Ji Belt (North China Craton) a rift?",
        (
            "Nd-Sr-Os isotopic data of the Baishiquan mafic-ultramafic complex "
            "from East Tianshan, and implications for petrogenesis"
        ),
        (
            "Sr-Nd isotopic characteristics of the Mesozoic magmatism in the "
            "Taihang-Yanshan orogen, north China craton, and implications for "
            "Archean lithosphere thinning"
        ),
    ]
    assert all(
        not publication.clean_title.startswith(("2017", "CJ", "Jahn"))
        for publication in publications
    )
    assert "Wei CJ" in (publications[0].authors_text or "")
    assert "Muhetaer Z" in (publications[1].authors_text or "")
    assert "M.G. Zhai" in (publications[2].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_dense_author_year_prefixes_reach_real_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>63. Chen B*, Niu XL, Wang ZQ, Gao L., Wang C, 2013，
      Geochronology, petrology, and geochemistry of the Yaojiazhuang
      ultramafic-syenitic complex from the North China Craton. Science
      China: Earth Sciences, 56(8): 1294-1307.</p>
      <p>106. Chen B.*, Liu S.W., Geng Y.S., et al., 2006, Zircon U-Pb
      ages, Hf isotopes and significance of the late Archean -
      Paleoproterozoic granitoids from the Wutai-Luliang terrain, North
      China. Acta Petrologica Sinica, 22: 296-304.</p>
      <p>112. Chen, B.*, Jahn, B-m., 2004, Genesis of post-collisional
      granitoids and basement nature of the Junggar Terrane, NW China:
      Nd-Sr isotope and trace element evidence. J. Asian Earth Sciences,
      23: 691-703.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/chenbin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Geochronology, petrology, and geochemistry of the Yaojiazhuang "
            "ultramafic-syenitic complex from the North China Craton"
        ),
        (
            "Zircon U-Pb ages, Hf isotopes and significance of the late Archean - "
            "Paleoproterozoic granitoids from the Wutai-Luliang terrain, North China"
        ),
        (
            "Genesis of post-collisional granitoids and basement nature of the "
            "Junggar Terrane, NW China: Nd-Sr isotope and trace element evidence"
        ),
    ]
    assert "Chen B" in (publications[0].authors_text or "")
    assert "Wang C" in (publications[0].authors_text or "")
    assert "Geng Y.S" in (publications[1].authors_text or "")
    assert "B-m Jahn" in (publications[2].authors_text or "")
    assert "Science China: Earth Sciences" in (publications[0].venue_text or "")
    assert "Acta Petrologica Sinica" in (publications[1].venue_text or "")
    assert "J. Asian Earth Sciences" in (publications[2].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_recruitment_tail_is_not_publication():
    html = """
    <main>
      <h2>代表论文</h2>
      <p>Chengchao Gu, Shuxiang Guo *, Chunying Li. A Novel Versatile
      Mechanical Integrated Leg-Based Underwater Grasping Function for a
      Bionic Amphibious Spherical Robot. Robotics and Autonomous Systems,
      2026.</p>
      <p>年薪36万起，海外博士后符合相关人才政策条件可以深圳市申请孔雀计划160-200万住房补贴</p>
      <p>享受五险一金、餐补、过节费、免费体检等福利待遇</p>
      <p>可申请硕士研究生导师，可独立申请课题。 应聘申请材料</p>
      <p>详细的个人简历（附2名推荐人姓名及联系方式），含学习、工作和科研的经历</p>
      <p>其他可以证明个人水平和能力的材料。 应聘方式</p>
      <p>仿生水下多机器人集群作业控制招聘要求</p>
      <p>具有相关专业的博士学位</p>
      <p>具有高度责任心</p>
      <p>良好的专业英语写作和报告能力博士后待遇</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/shuxiangguo.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "A Novel Versatile Mechanical Integrated Leg-Based Underwater Grasping "
            "Function for a Bionic Amphibious Spherical Robot"
        )
    ]
    assert "Shuxiang Guo" in (publications[0].authors_text or "")
    assert "Robotics and Autonomous Systems" in (publications[0].venue_text or "")


def test_sustech_semicolon_surname_given_chain_reaches_real_title():
    html = """
    <main>
      <h2>代表论文</h2>
      <p>Hanle Liu; Sarah; Brusseau, Mark L.; The influence of NAPL
      distribution on the transport of PFOS in Co-contaminated media.
      Journal of Hazardous Materials, 2024, 462, 132794.</p>
      <p>Kewei Chen; Xingyuan Chen; James C. Stegen; Jorge A. Villa;
      Bohrer, Gil; Song, Xuehang; Chang, Kuang-Yu; Kaufman, Matthew;
      Liang, Xiuyu; Guo, Zhiling; Roden, Eric E.*; Zheng, Chunmiao*;
      Vertical hydrologic exchange flows control methane emissions from
      riverbed sediments. Environmental Science & Technology, 2023.</p>
      <p>Rui Ma; Kewei Chen; Charles B. Andrews; Steven P. Loheide;
      Audrey H. Sawyer; Xue Jiang; … & Guo, Zhilin; Zheng, Chunmiao*;
      Methods for Quantifying Interactions Between Groundwater and
      Surface Water. Annual Review of Environment and Resources, 2024.</p>
      <p>Kuang, XingXing; Liu, Junguo*; Scanlon, Briget R.; Jiao,
      Jiu Jimmy; ... & Guo, Zhilin; …& Zheng, Chunmiao*; The changing
      nature of groundwater in the global water cycle. Science, 2024,
      383(6686), eadf0630.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/guozhilin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "The influence of NAPL distribution on the transport of PFOS in "
            "Co-contaminated media"
        ),
        (
            "Vertical hydrologic exchange flows control methane emissions from "
            "riverbed sediments"
        ),
        (
            "Methods for Quantifying Interactions Between Groundwater and "
            "Surface Water"
        ),
        "The changing nature of groundwater in the global water cycle",
    ]
    assert "Hanle Liu" in (publications[0].authors_text or "")
    assert "Mark L. Brusseau" in (publications[0].authors_text or "")
    assert "Bohrer" in (publications[1].authors_text or "")
    assert "Gil" in (publications[1].authors_text or "")
    assert "Roden" in (publications[1].authors_text or "")
    assert "Eric E" in (publications[1].authors_text or "")
    assert "Zhilin Guo" in (publications[2].authors_text or "")
    assert "Zhilin Guo" in (publications[3].authors_text or "")
    assert "Chunmiao Zheng" in (publications[3].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_chinese_contribution_note_prefix_does_not_become_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>2. G. G. Liu#, Z. Gao#(#同等贡献作者), Q. Wang, X. Xi, Y. H. Hu,
      M. R. Wang, C. Q. Liu, X. Lin, L. J. Deng, S. A. Yang, P. H. Zhou*,
      Y. Yang*, Y. D. Chong*, B. Zhang*, Topological Chern vectors in
      three-dimensional photonic crystals, Nature 609, 925-930 (2022).</p>
      <p>15. F. Gao#, Z. Gao#(#同等贡献作者), X. Shi, Z. Yang, X. Lin, H. Xu,
      J. D. Joannopoulos, M. Soljacic, H. Chen, L. Lu, Y. Chong, and B. Zhang,
      Probing topological protection using a designer surface plasmon structure,
      Nature Communications 7, 11619 (2016).</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/gaozhen.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Topological Chern vectors in three-dimensional photonic crystals",
        "Probing topological protection using a designer surface plasmon structure",
    ]
    assert all("同等贡献作者" not in publication.clean_title for publication in publications)
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_pubmed_author_particle_initial_fragment_reaches_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>25. Edd JF, Mishra A, Dubash TD, Herrera S, Mohammad R, Williams EK,
      Hong X, Mutlu BR, Walsh JR, Machado de Carvalho F. Aldikacti B, Nieman LT,
      Stott SL, Kapur R, Maheswaran S, Haber DA, Toner M. Microfluidic
      concentration and separation of circulating tumor cell clusters from large
      blood volumes. Lab Chip. 2020 Feb 7;20(3):558-567.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/hongxin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Microfluidic concentration and separation of circulating tumor cell "
            "clusters from large blood volumes"
        )
    ]
    assert "Machado de Carvalho F" in (publications[0].authors_text or "")
    assert "Toner M" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_english_contribution_legend_is_not_publication():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>* first/co-first authors; # corresponding/co-corresponding authors</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/hongxin.html",
    )

    assert publications == []


def test_sustech_quoted_phrase_inside_pubmed_title_keeps_full_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>10. Jiang Z*, He J*, Zhang B*, Wang L, Long C, Zhao B, Yang Y, Du L,
      Luo W#, Hu J#, Hong X#. A Potential "Anti-Warburg Effect" in Circulating
      Tumor Cell-mediated Metastatic Progression? Aging Dis. 2024 Jan 11.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/hongxin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            'A Potential "Anti-Warburg Effect" in Circulating Tumor '
            "Cell-mediated Metastatic Progression?"
        )
    ]
    assert publications[0].venue_text == "Aging Dis. 2024 Jan 11"
    assert "Hong X" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_ellipsis_joined_author_fragment_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>7. Zhu, Q., Zhao, X., Zhang, Y….Hu, Y., Chen, A., Xu, X., Li, G.,
      Hou, Y., Liu, L., Liu, S., Fang, L., Chen, W.*, Wu, L.*. Single cell
      multi-omics reveal intra-cell-line heterogeneity across human cancer
      cell lines. Nature Communications,14(1), 8170 (2023).
      https://doi.org/10.1038/s41467-023-43991-9</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/huyuhui.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Single cell multi-omics reveal intra-cell-line heterogeneity across "
            "human cancer cell lines"
        )
    ]
    assert "Y….Hu" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_lowercase_particle_author_fragment_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>35. Chen W, Ullmann R, Langnick C, Menzel C, Wotschofsky Z, Hu H,
      Döring A, Hu Y, Kang H, Tzschach A, Hoeltzenbein M, Neitzel H, Markus S,
      Wiedersberg E, Kistner G, van Ravenswaaij-Arts CM, Kleefstra T,
      Kalscheuer VM, Ropers HH. Breakpoint analysis of balanced chromosome
      rearrangements by next-generation paired-end sequencing. Eur J Hum Genet.
      (2010) May;18(5):539-43.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/huyuhui.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Breakpoint analysis of balanced chromosome rearrangements by "
            "next-generation paired-end sequencing"
        )
    ]
    assert "van Ravenswaaij-Arts CM" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_split_latin_author_fragment_reaches_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>20. Tao Chen, Bin Zhang, Thomas Ziegenhals, Archana B. Prusty,
      Sebastian Fro hler, Clemens Grimm, Yuhui Hu, Bernhard Schaefke,
      Liang Fang, Min Zhang, Nadine Kraemer, Angela M. Kaindl*, Utz Fischer*,
      and Wei Chen*. A missense mutation in SNRPElinked to non-syndromal
      microcephaly interferes with U snRNP assembly and pre-mRNA splicing.
      PLOS Genetics (2019) 15(10): e1008460.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/huyuhui.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "A missense mutation in SNRPElinked to non-syndromal microcephaly "
            "interferes with U snRNP assembly and pre-mRNA splicing"
        )
    ]
    assert "Sebastian Fro hler" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_oxford_comma_title_after_author_prefix_is_preserved():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>32. Mehmet Somel, Song Guo, Ning Fu, Zheng Yan, Hai Yang Hu, Ying Xu,
      Yuan Yuan, Zhibin Ning, Yuhui Hu, Corinna Menzel, Hao Hu, Michael Lachmann,
      Rong Zeng, Wei Chen, and Philipp Khaitovich. MicroRNA, mRNA, and protein
      expression link development and aging in human and macaque brain.
      Genome Research (2010); 20:1207-1218.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/huyuhui.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "MicroRNA, mRNA, and protein expression link development and aging "
            "in human and macaque brain"
        )
    ]
    assert publications[0].venue_text == "Genome Research (2010); 20:1207-1218"
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_synfacts_highlight_fragments_are_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>9357. Highlighted by “Synfacts 2016, 1020”. Highlighted by “Chin. J.
      Org. Chem. 2016, 36, 2247”.</p>
      <p>36. Taotao Li, Junhui Li, Wei Lin, and Xinyuan Liu*. Dual-Catalyzed
      Enantioselective Remote C-H Functionalization Triggered by Radical
      Trifluoromethylation of Alkenes: Highly Selective Formation of C-CF3 and
      C-C Bonds. J. Fluorine Chem. 2017, 203, 210. Highlighted by Synfacts
      2017, 13(10), 1042.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuxinyuan.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Dual-Catalyzed Enantioselective Remote C-H Functionalization "
            "Triggered by Radical Trifluoromethylation of Alkenes: Highly "
            "Selective Formation of C-CF3 and C-C Bonds"
        )
    ]
    assert all("Synfacts" not in publication.clean_title for publication in publications)
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_surname_given_ampersand_year_prefix_reaches_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Bodomo, Adams & Yuxiu, Hu (2013). Ubiquitous Conversations.
      Ubiquitous Learning: An International Journal. 5(1), 1-14</p>
      <p>Hu, Yuxiu & Adams, Bodomo. (2007). Harbinglish: L1 Influence on the
      Learning of English Among High School Students in China’s Harbin. Paper
      presented at The Second Pearl River Delta English Studies Graduate
      Student Conference at Shenzhen University. June 15-18, 2007.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/huyuxiu.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Ubiquitous Conversations",
        (
            "Harbinglish: L1 Influence on the Learning of English Among High "
            "School Students in China’s Harbin"
        ),
    ]
    assert "Adams Bodomo" in (publications[0].authors_text or "")
    assert "Yuxiu Hu" in (publications[0].authors_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_long_semicolon_author_chain_reaches_title_after_final_semicolon():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>1. Qin, Siying#; Yin, Hang#; Yang, Celi; Dou, Yunfeng; Liu, Zhongmin;
      Zhang, Peng; Yu, He; Huang, Yulong; Feng, Jing; Hao, Junfeng; Hao, Jia;
      Deng, Lizong; Yan, Xiyun; Dong, Xiaoli; Zhao, Zhongxian; Jiang, Taijiao;
      Wang, Hong-Wei; Luo, Shu-Jin; Xie, Can*; A magnetic protein biocompass,
      Nature Materials, 2016, 15(2): 217. (研究性论文)</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuzhongmin.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "A magnetic protein biocompass"
    ]
    assert "Siying Qin" in (publications[0].authors_text or "")
    assert "Can Xie" in (publications[0].authors_text or "")
    assert publications[0].venue_text is not None
    assert "Nature Materials" in publications[0].venue_text
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_title_internal_commas_are_preserved_before_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>17. Chen T.; Hao, R.; Peng H.; Dai L., High-Performance, Stretchable,
      Wire-Shaped Supercapacitors, Angew. Chem. Int. Ed., 2015, 54, 618-622.</p>
      <p>18. Hao, R.; Zhang, B, Nanopipette-based, Electroplated Nanoelectrodes.
      Anal. Chem., 2016, 88, 414-430.</p>
      <p>27. Fan, Y.ǂ; Hao, R. ǂ; Zhang, B. Counting Single Redox Molecules
      in a Nanoscale Electrochemical Cell. Anal.Chem. 2018, 90, 13837-13841.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/haorui.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "High-Performance, Stretchable, Wire-Shaped Supercapacitors",
        "Nanopipette-based, Electroplated Nanoelectrodes",
        "Counting Single Redox Molecules in a Nanoscale Electrochemical Cell",
    ]
    assert "R. Hao" in (publications[0].authors_text or "")
    assert "R. Hao" in (publications[1].authors_text or "")
    assert "R. Hao" in (publications[2].authors_text or "")
    assert "B. Zhang" in (publications[2].authors_text or "")
    assert "Angew. Chem. Int. Ed." in (publications[0].venue_text or "")
    assert "Anal. Chem." in (publications[1].venue_text or "")
    assert "Anal.Chem. 2018" in (publications[2].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_middle_dot_bullet_author_prefix_splits_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>· B. Zhang#*, D. Ge#, Y. Liu*, K. Cai, M. Ba, X. Li, H. Chen, X. Ji,
      X. Huang, G. Li, D. Zhou, High-resolution DNA size enrichment using a
      magnetic nano-platform and application in noninvasive prenatal testing,
      Analyst 2020, 145, 5733-5741.</p>
      <p>· G. Li, W. Zheng, Y. Liu, D. Zhou, Novel encoding methods for
      DNA-templated chemical libraries, Curr. Opin. Chem. Biol. 2015, 26,
      25-33.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuying-2.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "High-resolution DNA size enrichment using a magnetic nano-platform "
            "and application in noninvasive prenatal testing"
        ),
        "Novel encoding methods for DNA-templated chemical libraries",
    ]
    assert "B. Zhang" in (publications[0].authors_text or "")
    assert "G. Li" in (publications[0].authors_text or "")
    assert "G. Li" in (publications[1].authors_text or "")
    assert "Analyst 2020" in (publications[0].venue_text or "")
    assert "Curr. Opin. Chem. Biol." in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_parenthetical_author_role_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>(Corresponding 1st author), F. Zhang#, X. Guo, W. Zeng, H. Zhang,
      L. Zeng, J. Qu, B. Wu, X. Wan, C. R. Cantor, D. Ge*, High-resolution
      DNA size enrichment using a magnetic nano-platform and application in
      noninvasive prenatal testing, Analyst 2020, 145, 5733-5741.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuying-2.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "High-resolution DNA size enrichment using a magnetic nano-platform "
            "and application in noninvasive prenatal testing"
        )
    ]
    assert "F. Zhang" in (publications[0].authors_text or "")
    assert "D. Ge" in (publications[0].authors_text or "")
    assert "Analyst 2020" in (publications[0].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_lowercase_author_note_marker_prefix_splits_before_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>a Quan Gong, Jialin Wen* and Xumu Zhang*, Nickel-Catalyzed
      Desymmetric Hydrogenation of Cyclohexadienones: An Eﬃcient Approach to
      All-Carbon Quaternary Stereocenters, Angew. Chem. Int. Ed. 2019.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/sample.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Nickel-Catalyzed Desymmetric Hydrogenation of Cyclohexadienones: "
            "An Eﬃcient Approach to All-Carbon Quaternary Stereocenters"
        )
    ]
    assert "Quan Gong" in (publications[0].authors_text or "")
    assert "Xumu Zhang" in (publications[0].authors_text or "")
    assert "Angew. Chem. Int. Ed. 2019" in (publications[0].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_volume_page_doi_fragments_are_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>38, 1821. [doi]</p>
      <p>144, 10162. [doi]</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/sample.html",
    )

    assert publications == []


def test_sustech_fullwidth_dot_chinese_author_prefix_splits_title_and_venue():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>秦建强*．微纳米拓扑结构材料对移植细胞行为功能的影响．中国临床解剖学杂志，2013。</p>
      <p>杨俊罗勇邱小忠武雷余磊陆云涛朴英杰秦建强*．FK506促进异体神经匀浆激活的巨噬细胞凋亡的实验研究．第一军医大学学报，2005,25(1)66-70</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/qinjianqiang.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "微纳米拓扑结构材料对移植细胞行为功能的影响",
        "FK506促进异体神经匀浆激活的巨噬细胞凋亡的实验研究",
    ]
    assert publications[0].authors_text == "秦建强"
    assert publications[1].authors_text == "杨俊罗勇邱小忠武雷余磊陆云涛朴英杰秦建强"
    assert "中国临床解剖学杂志" in (publications[0].venue_text or "")
    assert "第一军医大学学报" in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_parenthesized_author_markers_split_before_real_titles():
    cases = [
        (
            "Yang Su (#), Yifan Luo(#), Peitao Zhang, Hong Lin, Weijie Pu, "
            "Hongyun Zhang, Huifang Wang, Yi Hao, Yihang Xiao, Xiaozhe Zhang, "
            "Xiayun Wei, Siyue Nie, Keren Zhang, Qiuyu Fu, Hao Chen, Niu Huang, "
            "Yan Ren, Mingxuan Wu, Billy Kwok Chong Chow, Xing Chen, Wenfei Jin, "
            "Fengchao Wang*, Li Zhao*, Feng Rao*, Glucose-induced CRL4COP1-p53 "
            "axis amplifies glycometabolism to drive tumorigenesis, Molecular "
            "Cell, 2023 Jun 6;83(13):2316-2331.",
            "Glucose-induced CRL4COP1-p53 axis amplifies glycometabolism to drive tumorigenesis",
            "Molecular Cell",
        ),
        (
            "Su Y , Yang Y, Huang Y(*), Loss of ppr3, ppr4, ppr6 or ppr10 "
            "perturbs iron homeostasis and leads to apoptotic cell death in "
            "Schizosaccharomyces pombe, FEBS J, 2017, 284(2): 324-337.",
            (
                "Loss of ppr3, ppr4, ppr6 or ppr10 perturbs iron homeostasis "
                "and leads to apoptotic cell death in Schizosaccharomyces pombe"
            ),
            "FEBS J",
        ),
        (
            "Rao F(*), Lin H, Su Y , Cullin-RING Ligase Regulation by the COP9 "
            "Signalosome: Structural Mechanisms and NewPhysiologic Players, "
            "Adv Exp Med Biol, 2020;1217:47-60.",
            (
                "Cullin-RING Ligase Regulation by the COP9 Signalosome: "
                "Structural Mechanisms and NewPhysiologic Players"
            ),
            "Adv Exp Med Biol",
        ),
        (
            "Hong Lin(#), Yuan Yan(#), Yifan Luo(#), Wing Yan So(#), Xiayun Wei, "
            "Xiaozhe Zhang, Xiaoli Yang, Jun Zhang, Yang Su , Xiuyan Yang, "
            "Bobo Zhang, Kangjun Zhang, Nan Jiang, Billy Kwok Chong Chow, "
            "Weiping Han, Fengchao Wang & Feng Rao*, IP6 -assisted CSN-COP1 "
            "competition regulates a CRL4-ETV5 proteolytic checkpoint to "
            "safeguard glucose-induced insulin secretion against hyperinsulinemia, "
            "Nature Communications, 2021 Apr 28;12(1):2461.",
            (
                "IP6 -assisted CSN-COP1 competition regulates a CRL4-ETV5 "
                "proteolytic checkpoint to safeguard glucose-induced insulin "
                "secretion against hyperinsulinemia"
            ),
            "Nature Communications",
        ),
    ]

    for raw, expected_title, expected_venue in cases:
        title, authors, venue = _split_title_authors_venue(raw)

        assert title == expected_title
        assert authors is not None
        assert "Yang Su" in authors or "Su Y" in authors or "Rao F" in authors
        assert expected_venue in (venue or "")


def test_sustech_semicolon_period_author_chain_keeps_title_after_final_author():
    cases = [
        (
            "Ruan, K.; Lu, Z.; Rao, R.; Liu, j. -j.; Chen, D.; Xia, H. "
            "Craig-Hückel Hybrid Aromatic Metalla-dehydro[11]annulenes "
            "Constructed by a Formal [10+1] Cycloaddition Reaction. "
            "Angew. Chem. Int. Ed. 2024, 63, e202316885.",
            (
                "Craig-Hückel Hybrid Aromatic Metalla-dehydro[11]annulenes "
                "Constructed by a Formal [10+1] Cycloaddition Reaction"
            ),
            "Angew. Chem. Int. Ed. 2024",
        ),
        (
            "Li, Q.; Hua, Y.; Tang, C.; Chen, D.; Luo, M.; Xia, H. "
            "Isolation, Reactivity, and Tunable Properties of a Strained "
            "Antiaromatic Osmacycle. J. Am. Chem. Soc. 2023, 145, 7580-7591.",
            (
                "Isolation, Reactivity, and Tunable Properties of a Strained "
                "Antiaromatic Osmacycle"
            ),
            "J. Am. Chem. Soc. 2023",
        ),
    ]

    for raw, expected_title, expected_venue in cases:
        title, authors, venue = _split_title_authors_venue(raw)

        assert title == expected_title
        assert authors is not None
        assert "H. Xia" in authors
        assert expected_venue in (venue or "")


def test_sustech_xiahaiping_semicolon_period_references_extract_clean_titles():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>4. Ruan, K.; Lu, Z.; Rao, R.; Liu, j. -j.; Chen, D.; Xia, H.
      Craig-Hückel Hybrid Aromatic Metalla-dehydro[11]annulenes Constructed
      by a Formal [10+1] Cycloaddition Reaction. Angew. Chem. Int. Ed. 2024,
      63, e202316885.</p>
      <p>8. Li, Q.; Hua, Y.; Tang, C.; Chen, D.; Luo, M.; Xia, H. Isolation,
      Reactivity, and Tunable Properties of a Strained Antiaromatic Osmacycle.
      J. Am. Chem. Soc. 2023, 145, 7580-7591.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/xiahaiping.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Craig-Hückel Hybrid Aromatic Metalla-dehydro[11]annulenes "
            "Constructed by a Formal [10+1] Cycloaddition Reaction"
        ),
        (
            "Isolation, Reactivity, and Tunable Properties of a Strained "
            "Antiaromatic Osmacycle"
        ),
    ]
    assert all("H. Xia" in (publication.authors_text or "") for publication in publications)
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_no_space_author_suffix_after_title_splits_remainder():
    raw = (
        "Transannular [6+4] and Ambimodal Cycloaddition in the Biosynthesis "
        "of Heronamide A .Yu, P.; Patel, A.; Houk, K. N.*J. Am. Chem. Soc. "
        "2015, 137, 13518."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Transannular [6+4] and Ambimodal Cycloaddition in the Biosynthesis "
        "of Heronamide A"
    )
    assert authors is not None
    assert "Yu, P." in authors
    assert "Patel, A." in authors
    assert "Houk, K. N." in authors
    assert "Am. Chem. Soc. 2015" in (venue or "")


def test_sustech_marked_tail_author_before_colon_title_is_stripped():
    raw = (
        "[1]. Caichao Ye , Tao Feng, Weishu Liu*, Wenqing Zhang*. "
        "Functional Unit: A New Perspective on Materials Science Research "
        "Paradigms. Acc. Mater. Res. , 2025 , 6(8), 914-920."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Functional Unit: A New Perspective on Materials Science Research "
        "Paradigms"
    )
    assert authors == "Caichao Ye, Tao Feng, Weishu Liu, Wenqing Zhang"
    assert "Acc. Mater. Res" in (venue or "")


def test_sustech_plus_marked_semicolon_author_chain_reaches_title():
    raw = (
        "14. Zhang, J.;+ Zhao, X.;+ Yang, J.-D.; Cheng, J.-P. "
        "Diazaphospholene-catalyzed hydrodefluorination of polyfluoroarenes "
        "with phenylsilane via concerted nucleophilic aromatic substitution. "
        "J. Org. Chem. 2022, 87, 1, 294-300. "
        "(+ Both authors contributed equally)"
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Diazaphospholene-catalyzed hydrodefluorination of polyfluoroarenes "
        "with phenylsilane via concerted nucleophilic aromatic substitution"
    )
    assert authors is not None
    assert "J. Zhang" in authors
    assert "X. Zhao" in authors
    assert "J.-D. Yang" in authors
    assert "J.-P. Cheng" in authors
    assert "J. Org. Chem. 2022" in (venue or "")


def test_sustech_lowercase_particle_surname_semicolon_chain_reaches_title():
    raw = (
        "5. Zhang, J.; Kwak, M. K.; van Wesel, L.; Choi, T.-L. "
        "Degradation of postconsumer thermoset rubbers via photo-oxidation. "
        "J. Am. Chem. Soc. 2025, 147 (47), 43973-43980."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Degradation of postconsumer thermoset rubbers via photo-oxidation"
    )
    assert authors is not None
    assert "J. Zhang" in authors
    assert "M. K. Kwak" in authors
    assert "L. van Wesel" in authors
    assert "T.-L. Choi" in authors
    assert "J. Am. Chem. Soc. 2025" in (venue or "")


def test_sustech_full_name_author_chain_before_comma_title_reaches_title():
    raw = (
        "10. Omar I. Awad, Bo Zhou*, Karim Harrath, K. Kadirgama, "
        "Characteristics of NH3/H2 blend as carbon-free fuels: A review, "
        "International Journal of Hydrogen Energy, Volume 48, 38077-38100, 2023"
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "Characteristics of NH3/H2 blend as carbon-free fuels: A review"
    assert authors is not None
    assert "Omar I. Awad" in authors
    assert "Bo Zhou" in authors
    assert "Karim Harrath" in authors
    assert "K. Kadirgama" in authors
    assert "International Journal of Hydrogen Energy" in (venue or "")


def test_sustech_initial_surname_author_before_year_venue_title_reaches_title():
    raw = (
        "5. F. Zhang, L. Zhang, X. Wang, K. Liu, B. Huang, Y. Wang, "
        "J. Li Observing reduced field fluctuation in interfacial engineered "
        "organic-inorganic dielectric nanocomposite for enhanced breakdown "
        "strength 2022 Appl. Phys. Lett. 121 243905 (IF:3.971)"
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Observing reduced field fluctuation in interfacial engineered "
        "organic-inorganic dielectric nanocomposite for enhanced breakdown strength"
    )
    assert authors is not None
    assert "F. Zhang" in authors
    assert "Y. Wang" in authors
    assert "J. Li" in authors
    assert "2022 Appl. Phys. Lett. 121 243905" in (venue or "")


def test_sustech_multi_initial_surname_author_before_title_reaches_title():
    raw = (
        "7. F. Zhang, H. Fan, X. Deng, D. Edwards, J. I. Kilpatrick, "
        "A. Kumar, D. Chen, X. Gao, Z. Fan, B. J. Rodriguez Boosting "
        "polarization switching-induced current injection by mechanical force "
        "in ferroelectric thin films 2021 ACS Appl. Mater. Interfaces, "
        "13(22), 26180-261869 (IF:10.383)"
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Boosting polarization switching-induced current injection by mechanical "
        "force in ferroelectric thin films"
    )
    assert authors is not None
    assert "B. J. Rodriguez" in authors
    assert "2021 ACS Appl. Mater. Interfaces, 13(22)" in (venue or "")


def test_sustech_connective_initial_authors_before_comma_title_reaches_title():
    raw = (
        "10. F. Zhang, Q. Miao, G. Tian, Z. Lu, L. Zhao, H. Fan, "
        "X. Song, Z. Li, M. Zeng, X. Gao & J. Liu Unique nano-domain "
        "structures in self-assembled BiFeO3 and Pb(Zr,Ti)O3 ferroelectric "
        "nanocapacitors 2016 Nanotechnol. 27 015703 (IF:3.551)"
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Unique nano-domain structures in self-assembled BiFeO3 and Pb(Zr, Ti)O3 "
        "ferroelectric nanocapacitors"
    )
    assert authors is not None
    assert "X. Gao" in authors
    assert "J. Liu" in authors
    assert "2016 Nanotechnol. 27 015703" in (venue or "")


def test_sustech_compact_initial_connective_author_segment_splits_pair():
    assert _split_compact_initial_connective_author_segment("X. Gao & J. Liu") == [
        "X. Gao",
        "J. Liu",
    ]


def test_sustech_full_name_and_author_period_prefix_reaches_title():
    raw = (
        "[7] Yu Zhang and Dit-Yan Yeung. A Regularization Approach to "
        "Learning Task Relationships in Multitask Learning. ACM Transactions "
        "on Knowledge Discovery from Data (TKDD), 8(3): article 12, 2014."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "A Regularization Approach to Learning Task Relationships in Multitask Learning"
    assert authors == "Yu Zhang, Dit-Yan Yeung"
    assert "ACM Transactions on Knowledge Discovery from Data" in (venue or "")


def test_sustech_missing_space_before_and_author_period_prefix_reaches_title():
    raw = (
        "[44] Yu Zhangand Dit-Yan Yeung. Multi-Task Boosting by Exploiting "
        "Task Relationships.In:Proceedings of the European Conference on "
        "Machine Learning and Principles andPractice of Knowledge Discovery "
        "in Databases (ECML-PKDD), pp. 697–710, Bristol,UK, 24–28 September 2012."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "Multi-Task Boosting by Exploiting Task Relationships"
    assert authors == "Yu Zhang, Dit-Yan Yeung"
    assert "ECML-PKDD" in (venue or "")


def test_sustech_connective_full_name_author_before_title_reaches_title():
    raw = (
        "[53] Bin Cao, Sinno Jialin Pan, Yu Zhang, Dit-Yan Yeung, "
        "and Qiang Yang. AdaptiveTransfer Learning. In:Proceedings of the "
        "Twenty-Fourth AAAI Conference on ArtificialIntelligence (AAAI), "
        "pp. 407–412, Atlanta, Georgia, USA, 11–15 July 2010."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "AdaptiveTransfer Learning"
    assert authors is not None
    assert "Dit-Yan Yeung" in authors
    assert "Qiang Yang" in authors
    assert "AAAI" in (venue or "")


def test_sustech_connective_full_name_with_middle_initial_before_title_reaches_title():
    raw = (
        "[46] Yu Zhang, Dit-Yan Yeung, and Eric P. Xing. Supervised "
        "Probabilistic Robust Embedding with Sparse Noise. In:Proceedings "
        "of the Twenty-Sixth AAAI Conference onArtificial Intelligence (AAAI), "
        "pp. 1226–1232, Toronto, Ontario, Canada, 22–26 July2012."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "Supervised Probabilistic Robust Embedding with Sparse Noise"
    assert authors is not None
    assert "Eric P. Xing" in authors
    assert "AAAI" in (venue or "")


def test_sustech_number_comma_item_prefix_is_stripped_from_title():
    raw = "1,Tumbling Down the Rabbit Hole: How do Assisting Exploration Strategies Facilitate Grey-box Fuzzing?"

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Tumbling Down the Rabbit Hole: How do Assisting Exploration Strategies "
        "Facilitate Grey-box Fuzzing?"
    )
    assert authors is None
    assert venue is None


def test_sustech_title_author_list_before_in_proceedings_reaches_title():
    raw = (
        "MOAT: Towards Safe BPF Kernel Extension Hongyi Lu, Shuai Wang*, "
        "Yechang Wu, Wanning He, and Fengwei Zhang* In Proceedings of the "
        "USENIX Security Symposium (USENIX Security'24), Philadelphia, PA, "
        "August 2024."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == "MOAT: Towards Safe BPF Kernel Extension"
    assert authors is not None
    assert "Hongyi Lu" in authors
    assert "Fengwei Zhang" in authors
    assert "USENIX Security" in (venue or "")


def test_sustech_parenthesized_year_author_list_before_title_reaches_title():
    raw = (
        "1. Liu Z*, Yang j*, Long Y*, Zhang C*, Wang D, Zhang X, Dong W, Zhao L, "
        "Liu C, Zhai J#, Wang E#. (2023) Single-nucleus transcriptomes reveal "
        "spatiotemporal symbiotic perception and early response in Medicago. "
        "Nature Plants . 10.1038/s41477-023-01524-8."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Single-nucleus transcriptomes reveal spatiotemporal symbiotic perception "
        "and early response in Medicago"
    )
    assert authors is not None
    assert "Liu Z" in authors
    assert "Zhai J" in authors
    assert "Nature Plants" in (venue or "")


def test_sustech_long_author_list_period_title_reaches_title():
    raw = (
        "Fan Pan1, Qifan Zhou*,1, Ming Yan1, Sidi Yang1, Ruiyu Hu, Yongzhi Chen, "
        "Yuanmei Wen, Yang Chao, Cailing Xie, Weixin Ou, Yingjun Li, "
        "Hongmin Zhang*, Deyin Guo*, Xumu Zhang*. Development of pyrimidone "
        "derivatives as nonpeptidic and noncovalent 3-chymotrypsin-like protease "
        "(3CLpro) inhibitors with anti-coronavirus activities. Bioorganic "
        "Chemistry, 2024, 154, 107988."
    )

    title, authors, venue = _split_title_authors_venue(raw)

    assert title == (
        "Development of pyrimidone derivatives as nonpeptidic and noncovalent "
        "3-chymotrypsin-like protease (3CLpro) inhibitors with anti-coronavirus "
        "activities"
    )
    assert authors is not None
    assert "Qifan Zhou" in authors
    assert "Xumu Zhang" in authors
    assert "Bioorganic Chemistry" in (venue or "")


def test_sustech_mixed_awards_list_does_not_override_publication_paragraphs():
    html = """
    <main>
      <h2>From total 250 publications</h2>
      <div>
        <ul>
          <li>Xiaohao Wu, School of Medicine Dean’s Fellowship, Stanford
          University, $35,000, 2024</li>
          <li>Donghao Gan, ASBMR Young Investigator Award, 2023</li>
        </ul>
        <p>1. Walke W, Xiao G, and Goldman D. A dual function
        activity-dependent, muscle-specific enhancer from rat nicotinic
        acetylcholine receptor d-subunit gene. J Biol Chem. 1996.</p>
        <p>2. Xiao G, Cui Y, Ducy P, Karsenty G, and Franceschi RT.
        Ascorbic acid-dependent activation of the osteocalcin promoter in
        MC3T3-E1 preosteoblasts. Mol Endocrinol. 1997.</p>
        <p>Donghao Gan, ASBMR Young Investigator Award, 2023</p>
        <p>钟一鸣，博士研究生国家奖学金, 2023</p>
      </div>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/english-xiao-guozhi.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "A dual function activity-dependent, muscle-specific enhancer from "
            "rat nicotinic acetylcholine receptor d-subunit gene"
        ),
        (
            "Ascorbic acid-dependent activation of the osteocalcin promoter in "
            "MC3T3-E1 preosteoblasts"
        ),
    ]
    assert all("Award" not in publication.clean_title for publication in publications)


def test_sustech_concatenated_middle_author_continues_to_real_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>John Yianni, PtolemaiosSarrigiannis, Jimmy Liu Jiang and Xiong-xiong
      He, A wavelet-based correlation analysis framework to study
      cerebro-muscular activity in essential tremor, Complexity, 2019.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liujiang.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "A wavelet-based correlation analysis framework to study "
            "cerebro-muscular activity in essential tremor"
        )
    ]
    assert "Ptolemaios Sarrigiannis" in (publications[0].authors_text or "")
    assert "Xiong-xiong He" in (publications[0].authors_text or "")
    assert "Complexity" in (publications[0].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_pubmed_author_list_period_prefix_reaches_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Watkins SC, Demetris AJ, Hussey GS, Badylak SF, Turnquist HR. Graft
      IL-33 regulates infiltrating macrophages to protect against chronic
      rejection. J Clin Invest. 2018.</p>
      <p>Matta BM, Reichenbach DK, Zhang X, Mathews L, Koehn BH, Dwyer GK,
      Lott JM, Uhl FM, Pfeifer D, Feser CJ, Rolandi M, Turnquist HR.
      Peri-alloHCT IL-33 administration expands recipient T regulatory cells
      that protect mice against acute GVHD. Blood. 2016.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuquan.html",
    )

    assert [publication.clean_title for publication in publications] == [
        (
            "Graft IL-33 regulates infiltrating macrophages to protect against "
            "chronic rejection"
        ),
        (
            "Peri-alloHCT IL-33 administration expands recipient T regulatory "
            "cells that protect mice against acute GVHD"
        ),
    ]
    assert "Watkins SC" in (publications[0].authors_text or "")
    assert "Reichenbach DK" in (publications[1].authors_text or "")
    assert "J Clin Invest" in (publications[0].venue_text or "")
    assert "Blood" in (publications[1].venue_text or "")
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_author_only_fragments_are_not_publications():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>Chen* (2012)</p>
      <p>andJianan Y. Qu*</p>
      <p>Yang iu, Chao lu, Wiliam Wella lu, * Hongmei liu* and Decheng Wu*</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/liuhongmei.html",
    )

    assert publications == []


def test_sustech_inline_academic_outputs_label_splits_numbered_publications():
    html = """
    <main>
      <p><strong>学术成果/论文发表</strong>1. Li Z, Wang Y. Scalable
      membrane separation for lithium recovery. Journal of Materials
      Chemistry A, 2024. 2. Zhang Q, Chen R. Stable photocatalytic hydrogen
      evolution from polymer heterojunctions. Advanced Science, 2023.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/sustech-audit.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Scalable membrane separation for lithium recovery",
        "Stable photocatalytic hydrogen evolution from polymer heterojunctions",
    ]
    assert "Li Z" in (publications[0].authors_text or "")
    assert "Journal of Materials Chemistry A" in (publications[0].venue_text or "")
    assert publications[0].year == 2024
    assert "Zhang Q" in (publications[1].authors_text or "")
    assert "Advanced Science" in (publications[1].venue_text or "")
    assert publications[1].year == 2023
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_sustech_academic_outputs_parenthetical_heading_collects_following_numbered_paragraphs():
    html = """
    <main>
      <div class="w clearfix introduce-main teacher_inner">
        <div class="message-right fr">
          <p><span><strong>学术成果（发表论著或者论文或者专利）：</strong></span></p>
          <p><br/></p>
          <p>Book (chapter):</p>
          <p>1. Yi Liu &amp; Zhenzhong Zeng*; Wind energy. In The Palgrave
          Handbook of Global Sustainability. (Cham: Springer International
          Publishing, 2022).</p>
          <p>L iteratures:</p>
          <p>1. Lili Liang; Shijing Liang &amp; Zhenzhong Zeng*; Extreme climate
          sparks record boreal wildfires and carbon surge in 2023; The
          Innovation; 2024. https://doi.org/10.1016/j.xinn.2024.100645</p>
          <p>2. Zurui Ao; Zhenzhong Zeng*; A national-scale assessment of land
          surface changes from satellite observations; Remote Sensing of
          Environment; 2023.</p>
        </div>
      </div>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/cengzhenzhong.html",
    )

    assert [publication.clean_title for publication in publications] == [
        "Wind energy",
        "Extreme climate sparks record boreal wildfires and carbon surge in 2023",
        "A national-scale assessment of land surface changes from satellite observations",
    ]
    assert publications[0].year == 2022
    assert "Zhenzhong Zeng" in (publications[0].authors_text or "")
    assert publications[1].year == 2024
    assert publications[1].venue_text == "The Innovation; 2024"
    assert publications[2].year == 2023
    assert publications[2].venue_text == "Remote Sensing of Environment; 2023"
    assert all(not _is_suspicious_rule_publication(pub) for pub in publications)


def test_homepage_publications_moves_single_abbreviated_venue_token_out_of_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. Zhang X, Li Y. Graphene sheets embedded carbon film prepared by
      electron irradiation in electron cyclotron resonance plasma, Appl.
      Physics Letters, 2012.</p>
      <p>2. Zhang X, Li Y. Influence of UV irradiation for low frictional
      performance of CNx coatings, Lubr. Sci., 2012, 24(3):129.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://example.edu/prof/publications",
    )

    assert [publication.clean_title for publication in publications] == [
        "Graphene sheets embedded carbon film prepared by electron irradiation "
        "in electron cyclotron resonance plasma",
        "Influence of UV irradiation for low frictional performance of CNx coatings",
    ]
    assert "Appl. Physics Letters" in (publications[0].venue_text or "")
    assert "Lubr. Sci" in (publications[1].venue_text or "")


def test_homepage_publications_skips_patent_entries_in_mixed_outputs_section():
    html = """
    <main>
      <h2>Publications and Patents</h2>
      <p>1. Patent: Adaptive quantization device for federated learning,
      CN202410123456.7.</p>
      <p>2. A. Zhang, B. Chen. Communication Efficient Federated Learning
      with Adaptive Quantization. ACM Transactions on Intelligent Systems and
      Technology, 2022.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://example.edu/prof/publications",
    )

    assert [publication.clean_title for publication in publications] == [
        "Communication Efficient Federated Learning with Adaptive Quantization"
    ]
    assert "Patent" not in publications[0].raw_title


def test_homepage_publications_skips_preprint_label_as_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. Zhang X, Li Y. In arXiv preprint. arXiv preprint, 2024.</p>
      <p>2. Zhang X, Li Y. Federated Optimization with Adaptive Compression.
      IEEE Transactions on Signal Processing, 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://example.edu/prof/publications",
    )

    assert [publication.clean_title for publication in publications] == [
        "Federated Optimization with Adaptive Compression"
    ]


def test_homepage_publications_skips_proceedings_label_as_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. Zhang X, Li Y. In Proceedings of the AAAI Conference on
      Artificial Intelligence (AAAI), 2025.</p>
      <p>2. Zhang X, Li Y. Federated Optimization with Adaptive Compression.
      In Proceedings of the AAAI Conference on Artificial Intelligence (AAAI),
      2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://example.edu/prof/publications",
    )

    assert [publication.clean_title for publication in publications] == [
        "Federated Optimization with Adaptive Compression"
    ]
    assert "AAAI" in (publications[0].venue_text or "")


def test_homepage_publications_skips_in_venue_label_as_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>1. Zhang X, Li Y. In IEEE Transactions on Circuits and Systems for
      Video Technology (T-CSVT).</p>
      <p>2. Zhang X, Li Y. Efficient Neural Video Compression.
      In IEEE Transactions on Circuits and Systems for Video Technology
      (T-CSVT), 2024.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://example.edu/prof/publications",
    )

    assert [publication.clean_title for publication in publications] == [
        "Efficient Neural Video Compression"
    ]
    assert "T-CSVT" in (publications[0].venue_text or "")


@pytest.mark.parametrize(
    "raw_text",
    [
        "IJCV * 1, AIJ * 1, TIP * 4, TVCG * 1",
        "Lang S u n",
        "and Bingding Huan g*",
        "2016 Aug 26;10 Suppl 3:71. doi: 10.1186/s12918-016-0315-y",
        "2016 Jun 1;6:26942. doi: 10.1038/srep26942",
        "In publications marked with '**', authors are ordered alphabetically, "
        "as is a convention of theory papers (Wikipedia). In the other "
        "publications, authors are ordered by contribution",
    ],
)
def test_homepage_publications_skips_metric_and_author_fragment_titles(raw_text):
    html = f"""
    <main>
      <h2>Publications</h2>
      <p>{raw_text}</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/person",
    )

    assert publications == []


@pytest.mark.parametrize(
    ("raw_text", "expected_title"),
    [
        ("** Fair Division with Prioritized Agents", "Fair Division with Prioritized Agents"),
        (
            "** Approximability Landscape of Welfare Maximization within Fair Allocations",
            "Approximability Landscape of Welfare Maximization within Fair Allocations",
        ),
    ],
)
def test_homepage_publications_strips_leading_contribution_markers(
    raw_text,
    expected_title,
):
    html = f"""
    <main>
      <h2>Publications</h2>
      <p>{raw_text}</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/person",
    )

    assert [publication.clean_title for publication in publications] == [expected_title]


def test_homepage_publications_strips_etc_author_prefix_before_real_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>etc. Logical Relation Inference and Multiview Information Interaction
      for Domain Adaptation Person Re-Identification</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/person",
    )

    assert [publication.clean_title for publication in publications] == [
        "Logical Relation Inference and Multiview Information Interaction "
        "for Domain Adaptation Person Re-Identification"
    ]


@pytest.mark.parametrize(
    "raw_text",
    [
        "Hasan Y ? lmaz",
        "Wenbo Zhu §",
        "Hasan Y ? lmaz, Wenbo Zhu §",
    ],
)
def test_homepage_publications_skips_mojibake_and_section_marker_author_fragments(
    raw_text,
):
    html = f"""
    <main>
      <h2>Publications</h2>
      <p>{raw_text}</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/person",
    )

    assert publications == []


def test_homepage_publications_strips_section_marker_author_before_real_title():
    html = """
    <main>
      <h2>Publications</h2>
      <p>Wenbo Zhu §. Robust Visual Tracking under Occlusion.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://faculty.example.edu/person",
    )

    assert [publication.clean_title for publication in publications] == [
        "Robust Visual Tracking under Occlusion"
    ]
    assert publications[0].authors_text == "Wenbo Zhu"


def test_sustech_semicolon_authors_title_venue_year_uses_second_segment_as_title():
    html = """
    <main>
      <h2>代表性论文</h2>
      <p>陈达发; 金属中心平面大环化合物; Nature; 2025.</p>
    </main>
    """

    publications = extract_publications_from_html(
        html,
        page_url="https://www.sustech.edu.cn/zh/faculties/sustech-audit.html",
    )

    assert len(publications) == 1
    publication = publications[0]
    assert publication.clean_title == "金属中心平面大环化合物"
    assert publication.authors_text == "陈达发"
    assert publication.venue_text == "Nature; 2025"
    assert publication.year == 2025
    assert not _is_suspicious_rule_publication(publication)
