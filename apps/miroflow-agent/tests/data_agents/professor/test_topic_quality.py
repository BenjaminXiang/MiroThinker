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
