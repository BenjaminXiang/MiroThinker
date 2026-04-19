import pytest

from src.data_agents.professor.topic_quality import (
    is_plausible_research_topic,
    split_compound_research_topic,
)


@pytest.mark.parametrize(
    "topic",
    [
        "人工智能",
        "机器学习",
        "计算机视觉",
        "红外图像处理",
        "非线性控制",
        "交通流建模与仿真",
        "2D/3D目标检测",
        "储能用碳材料和先进电池",
        "图像退化恢复 (Image Restoration)",
        "光无线通信波束赋形超表面 (Beam-Steering Metasurfaces)",
        "Neural network optimization",
    ],
)
def test_accepts_real_topics(topic: str):
    assert is_plausible_research_topic(topic), topic


@pytest.mark.parametrize(
    "topic",
    [
        "不同取食策略生物的耐热性，仍缺乏系统验证",
        "蛹等）",
        "《国家科学评论》（National Science Re",
        "智能控制与先进制造领域的研究及应用，主要研究方向包括学习控制",
        "半导体制造系统等",
        "以及不同平台机器人的具身智能实现",
        "交通大数据分析等",
        "多模态图像理解等",
    ],
)
def test_rejects_sentence_fragments_and_meta_phrases(topic: str):
    assert not is_plausible_research_topic(topic), topic


@pytest.mark.parametrize(
    "topic",
    [
        None,
        "",
        " ",
        "x",
        "）开头的",
        "逗号结尾，",
        "冒号结尾：",
    ],
)
def test_rejects_degenerate_shapes(topic):
    assert not is_plausible_research_topic(topic)


def test_rejects_overlong_phrases():
    # > 80 chars — too long to be a "topic"
    long_topic = "研究方向描述" * 20
    assert len(long_topic) > 80
    assert not is_plausible_research_topic(long_topic)


def test_rejects_unbalanced_brackets():
    assert not is_plausible_research_topic("研究（未闭合")
    assert not is_plausible_research_topic("《引用未闭合")
    assert not is_plausible_research_topic("(open paren")


# Round 7.9' — catch noise classes found in miroflow_real research_topic column.


@pytest.mark.parametrize(
    "topic",
    [
        # Generic English meta labels
        "Research syntheses",
        "Research interests",
        "Research areas",
        "Research topics",
        # Journal name with year suffix (seen in real data, comma CN or EN)
        "Conservation Biology，2023",
        "Nature Communications，2025",
        "One Earth，2023",
        "Journal of Biogeography，2021",
        "Conservation Biology, 2024",
        # Bare journal name or truncated journal name
        "Nano Letters",
        "JACS",
        "Matter and Radia",
        "Nature",
        # Numbered section fragments
        "（1）3D",
        "1.",
        "(2)",
    ],
)
def test_rejects_round_7_9_prime_noise(topic: str):
    """Noise classes found in miroflow_real that the original guard missed."""
    assert not is_plausible_research_topic(topic), topic


@pytest.mark.parametrize(
    "topic",
    [
        # Legit English tech terms that happen to be short / all-caps
        "PVD",
        "Transfer learning",
        "AI4Science",
        "AR/VR",
        "HDR",
        # Legit topics that mention a journal name but are full phrases
        "发表于 Nature Communications 的机器学习算法",
    ],
)
def test_keeps_legit_english_tech_terms(topic: str):
    """The new rules must not over-reject short English terms that are real topics."""
    assert is_plausible_research_topic(topic), topic


# Round 7.18b — split_compound_research_topic: break multi-topic strings
# like "计算神经科学，机器学习，人工智能，数据科学，生物图像分析" into atomic topics.


def test_split_compound_single_topic_returns_itself():
    assert split_compound_research_topic("多智能体协同控制") == ["多智能体协同控制"]
    assert split_compound_research_topic("量子计算") == ["量子计算"]


def test_split_compound_with_chinese_commas():
    assert split_compound_research_topic("计算神经科学，机器学习，人工智能") == [
        "计算神经科学",
        "机器学习",
        "人工智能",
    ]


def test_split_compound_with_mixed_separators():
    assert split_compound_research_topic("机器学习、人工智能；控制论,深度学习") == [
        "机器学习",
        "人工智能",
        "控制论",
        "深度学习",
    ]


def test_split_compound_five_topics_real_data():
    """Sample from miroflow_real: 周鹏程/深圳理工大学."""
    result = split_compound_research_topic(
        "计算神经科学，机器学习，人工智能，数据科学，生物图像分析"
    )
    assert result == [
        "计算神经科学",
        "机器学习",
        "人工智能",
        "数据科学",
        "生物图像分析",
    ]


def test_split_compound_drops_noise_fragments():
    """Valid pieces keep, garbage pieces drop via is_plausible_research_topic."""
    assert split_compound_research_topic("机器学习, 等") == ["机器学习"]
    assert split_compound_research_topic("计算神经科学，研究兴趣，机器学习") == [
        "计算神经科学",
        "机器学习",
    ]


def test_split_compound_does_not_split_parenthetical_english():
    """(Image Restoration) parenthetical must stay — no comma outside parens."""
    assert split_compound_research_topic("图像退化恢复 (Image Restoration)") == [
        "图像退化恢复 (Image Restoration)"
    ]


def test_split_compound_returns_empty_for_pure_noise():
    assert split_compound_research_topic("等, 其他") == []
    assert split_compound_research_topic("") == []
    assert split_compound_research_topic(None) == []


def test_split_compound_trims_whitespace():
    assert split_compound_research_topic(" 机器学习 ， 人工智能 ") == [
        "机器学习",
        "人工智能",
    ]


@pytest.mark.parametrize(
    "metric",
    [
        "发表学术论文350多篇",
        "出版著作30余部",
        "获得授权发明专利20余项",
        "主持国家自然科学基金5项",
        "发表SCI论文100篇以上",
    ],
)
def test_rejects_publication_metric_pretending_to_be_topic(metric: str):
    """Publication count/metric strings are not research topics."""
    assert not is_plausible_research_topic(metric), metric


def test_split_compound_drops_metric_fragments_from_compound():
    """Real case: "课程与教学论研究，发表学术论文350多篇，出版著作30余部"."""
    result = split_compound_research_topic(
        "课程与教学论研究，发表学术论文350多篇，出版著作30余部"
    )
    assert result == ["课程与教学论研究"]
