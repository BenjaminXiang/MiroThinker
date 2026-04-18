import pytest

from src.data_agents.professor.topic_quality import is_plausible_research_topic


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
