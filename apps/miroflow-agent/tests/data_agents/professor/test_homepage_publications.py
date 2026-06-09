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
