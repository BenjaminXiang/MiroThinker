import pytest

from src.data_agents.paper.title_quality import is_plausible_paper_title


@pytest.mark.parametrize(
    "title",
    [
        "Recent Advances and Design Strategies of Metal-Organic Framework-Based Materials",
        "Prediction of MXene based 2D tunable band gap semiconductors",
        "An incentive mechanism for private information acquisition",
        "深度学习在机器人视觉中的应用研究",
        "基于稀疏表示的图像超分辨率重建方法",
        "Manipulation of valley pseudospin in transition metal dichalcogenide monolayers",
        "Route choice behaviour and lane management strategy considering capacity variability",
    ],
)
def test_accepts_real_paper_titles(title: str):
    assert is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Ph.D. in Physics, Renmin University of China, 2018",
        "Ph.D. in Information Engineering",
        "B.Sc. (with Honours), Electrical Engineering",
        "Fellow, American Institute for Medical and Biological Engineering (AIMBE)",
        "Fellow of Royal Society of New Zealand",
        "Associate Editor, Springer-Nature Annals of Biomedical Engineering (ABME)",
        "Associate Editor, IEEE Transactions on Biomedical Engineering (TBME)",
        "Associate Editor, Journal of Artificial Intelligence and Soft Computing Research, 2024-present",
        "President, Asia Pacific Neural Networks Society, 2019",
        "Teaching Prize RWTH Aachen University, 2013",
        "Co-Chair, Ubicomp/ISWC'21 CPD Workshop",
        "Workshop Co-Chair, IEEE SmartGridComm 2019",
        "Reviewer for over 40 journals and conferences",
        "Research Area：Signal Processing, Robotics, Human-machine interface",
        "Assistant professor: December 2025- continue, Tsinghua SIGS",
        "2011 - 2016, Ph.D. in Electronic Engineering, Tsinghua University, China",
        "2019 - 2022, Assistant Professor, Tsinghua-Berkeley Shenzhen Institute",
        "2022 - Present, Associate Professor, Institute of Data and Information",
    ],
)
def test_rejects_cv_fragment_titles(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize("title", ["", " ", None, "x"])
def test_rejects_empty_or_tiny_titles(title):
    assert not is_plausible_paper_title(title)


def test_rejects_short_english_fragments_with_no_words():
    assert not is_plausible_paper_title("summary")
    assert not is_plausible_paper_title("unpublished")


def test_rejects_single_word_fragments_even_when_long_enough():
    # "Abstract" looks plausible by length but has no space separators.
    assert not is_plausible_paper_title("Abstract paragraph")
    # Two-word fragments often nav-esque — require 3+ words.
    assert is_plausible_paper_title("Learning Deep Representations from Sparse Data")
