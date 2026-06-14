import pytest

from src.data_agents.paper.title_cleaner import (
    clean_paper_title,
    clean_reference_like_paper_title,
)


def test_clean_paper_title_strips_mathml_and_preserves_formula_tokens():
    raw = """Manipulation of valley pseudospin in <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:msub><mml:mi>WSe</mml:mi><mml:mn>2</mml:mn></mml:msub><mml:mo>/</mml:mo><mml:msub><mml:mi>CrI</mml:mi><mml:mn>3</mml:mn></mml:msub></mml:math> heterostructures by the magnetic proximity effect"""

    assert clean_paper_title(raw) == "Manipulation of valley pseudospin in WSe2/CrI3 heterostructures by the magnetic proximity effect"


def test_clean_paper_title_decodes_entities_and_sub_sup_tags():
    raw = "First-principles study of Ga-vacancy induced magnetism in β-Ga<sub>2</sub>O<sub>3</sub> &amp; related systems"

    assert clean_paper_title(raw) == "First-principles study of Ga-vacancy induced magnetism in β-Ga2O3 & related systems"


def test_clean_paper_title_compacts_formula_tokens_from_mathml_runs():
    raw = """Quasiparticle electronic structure of honeycomb <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:mi>C</mml:mi><mml:mn>3</mml:mn><mml:mi>N</mml:mi></mml:math>: from monolayer to bulk"""

    assert clean_paper_title(raw) == "Quasiparticle electronic structure of honeycomb C3N: from monolayer to bulk"


def test_clean_paper_title_compacts_plaintext_formula_tokens():
    raw = "Quasiparticle electronic structure of honeycomb C 3 N: from monolayer to bulk"

    assert clean_paper_title(raw) == "Quasiparticle electronic structure of honeycomb C3N: from monolayer to bulk"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Isolation and impartial aggregation: A paradigm of incremental "
            "learning without interference Yabin Wang #, Zhiheng Ma #, Zhiwu "
            "Huang, Yaowei Wang, Zhou Su, Xiaopeng Hong & Code",
            "Isolation and impartial aggregation: A paradigm of incremental "
            "learning without interference",
        ),
        (
            "ComprehendEdit: A Comprehensive Dataset and Evaluation Framework "
            "for Multimodal Knowledge Editing Yaohui Ma, Xiaopeng Hong, "
            "Shizhou Zhang, Huiyun Li, Zhilin Zhu, Wei Luo, Zhiheng Ma & Code",
            "ComprehendEdit: A Comprehensive Dataset and Evaluation Framework "
            "for Multimodal Knowledge Editing",
        ),
        (
            "Sparse parameterization for epitomic dataset distillation Xing Wei, "
            "Anjia Cao, Funing Yang, Zhiheng Ma & Code",
            "Sparse parameterization for epitomic dataset distillation",
        ),
        (
            "FLAME: Frozen Large Language Models Enable Data-Efficient "
            "Language-Image Pre-training Anjia Cao, Xing Wei, Zhiheng Ma & Code",
            "FLAME: Frozen Large Language Models Enable Data-Efficient "
            "Language-Image Pre-training",
        ),
        (
            "Joint Memory Optimization for Continual Learning Zhiheng Ma, "
            "Yaohui Ma, Xiaopeng Hong, Huiyun Li, Shizhou Zhang & Code",
            "Joint Memory Optimization for Continual Learning",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_suat_author_code_tail(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


def test_clean_reference_like_paper_title_preserves_code_words_in_real_titles():
    raw = "Code-switching language modeling with sparse mixture-of-experts"

    assert clean_reference_like_paper_title(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "Etching dynamics of silicon surfaces under plasma treatment",
        "Etch profile control in plasma-assisted semiconductor manufacturing",
    ],
)
def test_clean_reference_like_paper_title_preserves_etch_prefix_words(raw: str):
    assert clean_reference_like_paper_title(raw) == raw


def test_clean_reference_like_paper_title_strips_known_trailing_venue():
    raw = (
        "Structure and phase regulation in MoxC based compounds for enhanced "
        "hydrogen evolution Applied Catalysis B: Environmental"
    )

    assert (
        clean_reference_like_paper_title(raw)
        == "Structure and phase regulation in MoxC based compounds for enhanced hydrogen evolution"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "etc.Energy Recovery Strategy Numerical Simulation for Dual Axle "
            "Drive Pure Electric Vehicle Based on Motor Loss Model and Big "
            "Data Calculation",
            "Energy Recovery Strategy Numerical Simulation for Dual Axle "
            "Drive Pure Electric Vehicle Based on Motor Loss Model and Big "
            "Data Calculation",
        ),
        (
            "第一作者，AGSENet：A Robust Road Ponding Detection Method for "
            "Proactive Traffic Safety",
            "AGSENet：A Robust Road Ponding Detection Method for Proactive "
            "Traffic Safety",
        ),
        (
            "Quantifying privacy vulnerability under linkage attack across "
            "multi-source individual mobility data. In 99th Transportation "
            "Research Board (TRB) Annual Meeting. [download]",
            "Quantifying privacy vulnerability under linkage attack across "
            "multi-source individual mobility data",
        ),
        (
            "Finding the Maximum Area Parallelogram in a Convex Polygon 23rd "
            "Canadian Conference on Computational Geometry (CCCG’11) "
            "Coauthor: Kevin Matulef",
            "Finding the Maximum Area Parallelogram in a Convex Polygon",
        ),
        (
            "Simple k-crashing Plan with a Good Approximation Ratio 23rd "
            "Conference in Autonomous Agents and Multiagent Systems (AAMAS’24) "
            "Coauthors: R. Luo",
            "Simple k-crashing Plan with a Good Approximation Ratio",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_runtime_reference_noise(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Optimal Control Method of Path Tracking for Four-Wheel Steering "
            "Vehicles. ACTUATORS. DOI10.3390/act11020061",
            "Optimal Control Method of Path Tracking for Four-Wheel Steering "
            "Vehicles",
        ),
        (
            "You are where you go: Inferring residents‘ income level through "
            "daily activity and geographic exposure. Cities",
            "You are where you go: Inferring residents‘ income level through "
            "daily activity and geographic exposure",
        ),
        (
            "Examining the Relationship between Social Context and Community "
            "Attachment Through the Daily Social Context Averaging Effect, "
            "Geografiska Annaler: Series B, Human Geography",
            "Examining the Relationship between Social Context and Community "
            "Attachment Through the Daily Social Context Averaging Effect",
        ),
        (
            "Statistical Regression Scheme for Intensity Prediction of "
            "Tropical Cyclones in the Northwestern Pacific. WEATHER AND "
            "FORECASTING",
            "Statistical Regression Scheme for Intensity Prediction of "
            "Tropical Cyclones in the Northwestern Pacific",
        ),
        (
            "Fast dynamic nonparametric distribution tracking in electron "
            "microscopic data. Annals of Applied Statistics",
            "Fast dynamic nonparametric distribution tracking in electron "
            "microscopic data",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_venue_and_doi_suffixes(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "A Survey on Large Language Models for Education. Proceedings of "
            "the 2024 Conference of the North American Chapter of the "
            "Association for Computational Linguistics",
            "A Survey on Large Language Models for Education",
        ),
        (
            "A Survey on Large Language Models for Education, Proceedings of "
            "the 2024 Conference on Empirical Methods in Natural Language "
            "Processing",
            "A Survey on Large Language Models for Education",
        ),
        (
            "A Survey on Large Language Models for Education In Proceedings "
            "of the 2024 Conference on Empirical Methods in Natural Language "
            "Processing",
            "A Survey on Large Language Models for Education",
        ),
        (
            "Graph Neural Networks for Materials Discovery NAACL-HLT 2024",
            "Graph Neural Networks for Materials Discovery",
        ),
        (
            "Graph Neural Networks for Materials Discovery EMNLP-IJCNLP 2019",
            "Graph Neural Networks for Materials Discovery",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_proceedings_and_acronym_venue_suffixes(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


def test_clean_reference_like_paper_title_strips_journal_volume_tail():
    raw = (
        "A Stochastic Successive Minimization Method for Nonsmooth Nonconvex "
        "Optimization with Applications to Transceiver Design in Wireless "
        "Communication Networks”, Mathematical Programming, Vol"
    )

    assert (
        clean_reference_like_paper_title(raw)
        == "A Stochastic Successive Minimization Method for Nonsmooth Nonconvex "
        "Optimization with Applications to Transceiver Design in Wireless "
        "Communication Networks"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Non-Hermitian non-equipartition theory for trapped particles Nat",
            "Non-Hermitian non-equipartition theory for trapped particles",
        ),
        (
            "Solving non-Hermitian physics for optical manipulation on a "
            "quantum computer Light, Sci",
            "Solving non-Hermitian physics for optical manipulation on a "
            "quantum computer",
        ),
        (
            "Diversity-enabled sweet spots in layered architectures and "
            "speed-accuracy trade-offs in sensorimotor control, PNAS",
            "Diversity-enabled sweet spots in layered architectures and "
            "speed-accuracy trade-offs in sensorimotor control",
        ),
        (
            "Evidence for chiral superconductivity on a silicon surface\" Nat",
            "Evidence for chiral superconductivity on a silicon surface",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_short_venue_abbreviation_tail(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


def test_clean_reference_like_paper_title_strips_single_author_before_article_title():
    raw = (
        "Xiu A non-intrusive correction algorithm for classification "
        "problems with corrupted data Commun"
    )

    assert (
        clean_reference_like_paper_title(raw)
        == "A non-intrusive correction algorithm for classification problems with corrupted data"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Kurganov Well-Balanced Positivity Preserving Cell-Vertex "
            "Central-Upwind Scheme for Shallow Water Flows Computers and Fluids",
            "Well-Balanced Positivity Preserving Cell-Vertex Central-Upwind "
            "Scheme for Shallow Water Flows",
        ),
        (
            "Christov and A. Kurganov Central-Upwind Schemes for the "
            "Boussinesq Paradigm Equations The",
            "Central-Upwind Schemes for the Boussinesq Paradigm Equations",
        ),
        (
            "Highly efficient solid-state luminescent gold complexes Yong Chen",
            "Highly efficient solid-state luminescent gold complexes",
        ),
        (
            "Photochemically induced reversible and irreversible "
            "photochromic behavior of diarylethenes Mo Xie,* Wei Lu * RSC Adv",
            "Photochemically induced reversible and irreversible "
            "photochromic behavior of diarylethenes",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_sustech_author_prefixes_and_venue_tails(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Kurganov-type central-upwind schemes for hyperbolic conservation laws",
        "Computers and Fluids benchmark suite for shallow water flows",
        "The Boussinesq Paradigm Equations and Long-Wave Approximation",
        "Photochemical behavior of diarylethenes in RSC advanced materials",
    ],
)
def test_clean_reference_like_paper_title_preserves_sustech_like_valid_titles(
    raw: str,
):
    assert clean_reference_like_paper_title(raw) == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "(with B. Gidas and L. Nirenberg) Symmetry of positive solutions "
            "of nonlinear elliptic equations in Rn",
            "Symmetry of positive solutions of nonlinear elliptic equations in Rn",
        ),
        (
            "(with P. Sacks and J. Tavantzis) On the asymptotic behavior of "
            "solutionsof certain quasilinear parabolic equations",
            "On the asymptotic behavior of solutionsof certain quasilinear "
            "parabolic equations",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_leading_with_author_note(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "l1kdeconv: an R package for deconvolution of bulk DNA "
            "methylation data. BMC bioinformatics, 18, 1-7",
            "l1kdeconv: an R package for deconvolution of bulk DNA "
            "methylation data",
        ),
        (
            "On the existence of global vortex rings, J. d’Analyse Math",
            "On the existence of global vortex rings",
        ),
        (
            "Symmetry and related properties via the maximum principle, Comm",
            "Symmetry and related properties via the maximum principle",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_known_journal_citation_tail(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Class-Incremental Learning for Myoelectric Locomotion Modes "
            "Prediction: Evaluating Replay Strategies Against Catastrophic "
            "Forgetting[C/OL]//2025 IEEE International Conference on Robotics "
            "and Automation (ICRA)",
            "Class-Incremental Learning for Myoelectric Locomotion Modes "
            "Prediction: Evaluating Replay Strategies Against Catastrophic "
            "Forgetting",
        ),
        (
            "A normalisation approach improves the performance of inter-subject "
            "sEMG-based hand gesture recognition with a ConvNet[C/OL]//2020 "
            "42nd Annual International Conference of the IEEE Engineering in "
            "Medicine & Biology Society (EMBC)",
            "A normalisation approach improves the performance of inter-subject "
            "sEMG-based hand gesture recognition with a ConvNet",
        ),
        (
            "FEAST: Feature selection for improved cell clustering — "
            "Bioinformatics, 2020 [ Paper ] [ Software ]",
            "FEAST: Feature selection for improved cell clustering",
        ),
        (
            "DSS: Differential methylation for general experimental design — "
            "Bioinformatics, 2016 [ Paper ] [ Software ]",
            "DSS: Differential methylation for general experimental design",
        ),
        (
            "Volatility Forecasting based on Daily Frequency Prices”, with "
            "Weiyi Liu and Mingjin Wang",
            "Volatility Forecasting based on Daily Frequency Prices",
        ),
        (
            "Copper-Catalyzed Enantioconvergent Radical N-Alkylation of "
            "Indoles with Amino Acid Derivatives\" J. Am",
            "Copper-Catalyzed Enantioconvergent Radical N-Alkylation of "
            "Indoles with Amino Acid Derivatives",
        ),
        (
            "DrugReAlign: a multisource prompt framework for drug repurposing "
            "based on large language models. BMC biology",
            "DrugReAlign: a multisource prompt framework for drug repurposing "
            "based on large language models",
        ),
        (
            "An iterative thresholding method for the minimum compliance "
            "problem, Communications in Computational Physics",
            "An iterative thresholding method for the minimum compliance problem",
        ),
    ],
)
def test_clean_reference_like_paper_title_recovers_seed_audit_citation_tails(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


def test_clean_paper_title_repairs_cuhk_myweb_latex_escaped_glyph_losses():
    raw = (
        r"\Highly e_cient _eld-free control of domain wall motion in "
        r"ferrimagnetic films"
    )

    assert (
        clean_paper_title(raw)
        == "Highly efficient field-free control of domain wall motion in "
        "ferrimagnetic films"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "Sparse_matrix factorization for graph signal processing",
        "Learning with L_2 regularization and H_infinity constraints",
        "Co_n thin films with field-free switching",
    ],
)
def test_clean_paper_title_preserves_real_underscore_and_math_like_tokens(raw: str):
    assert clean_paper_title(raw) == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Reachability Analysis of Hybrid Systems, Automatica, vol",
            "Reachability Analysis of Hybrid Systems",
        ),
        (
            "Adaptive Query Processing over Distributed Tables. Proc. VLDB Endow.",
            "Adaptive Query Processing over Distributed Tables",
        ),
        (
            "Scalable Skyline Computation for Uncertain Data, VLDB",
            "Scalable Skyline Computation for Uncertain Data",
        ),
        (
            "Robust Consensus for Networked Multi-Agent Systems, no. 2, pp",
            "Robust Consensus for Networked Multi-Agent Systems",
        ),
        (
            "Predictive Control for Energy-Efficient Autonomous Driving, "
            "vol. 12, no. 2, pp. 100-110",
            "Predictive Control for Energy-Efficient Autonomous Driving",
        ),
        (
            "Learning-Based Fault Diagnosis for Industrial Systems (IF: 8.5)",
            "Learning-Based Fault Diagnosis for Industrial Systems",
        ),
    ],
)
def test_clean_reference_like_paper_title_strips_generic_metadata_tails(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            'Wei Zhang, Ming Li, "Efficient Graph Neural Networks for '
            'Large-Scale Table Understanding", Proc. VLDB Endow.',
            "Efficient Graph Neural Networks for Large-Scale Table Understanding",
        ),
        (
            "Efficient Graph Neural Networks for Large-Scale Table "
            "Understanding, Wei Zhang, Ming Li, Proc. VLDB Endow.",
            "Efficient Graph Neural Networks for Large-Scale Table Understanding",
        ),
    ],
)
def test_clean_reference_like_paper_title_extracts_title_from_author_metadata_records(
    raw: str,
    expected: str,
):
    assert clean_reference_like_paper_title(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Uncovering, Explaining and Predicting Defects in Software Systems",
        "Proc. Macro Expansion for Reproducible Build Systems",
        "Sparse Matrix-Vector Multiplication: From O(n log n) to O(n)",
    ],
)
def test_clean_reference_like_paper_title_preserves_commas_proc_and_math_tokens(
    raw: str,
):
    assert clean_reference_like_paper_title(raw) == raw
