import pytest

from src.data_agents.paper.title_quality import is_plausible_paper_title


@pytest.mark.parametrize(
    "title",
    [
        "Attention Is All You Need",
        "Deep Residual Learning for Image Recognition",
        "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "Neural Machine Translation by Jointly Learning to Align and Translate",
        "Graph Attention Networks",
        "A Survey on Large Language Models for Education",
        "基于深度学习的图像识别方法研究",
        "面向智慧医疗的多模态数据融合模型",
        "面向自动驾驶的三维目标检测方法",
        "融合知识图谱与大语言模型的问答系统研究",
        "基于Transformer的中文长文本分类研究",
        "面向工业质检的 Vision Transformer 缺陷检测方法",
    ],
)
def test_accepts_real_paper_titles(title: str):
    assert is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Heng Tan, Hao Wang, Qingyuan Zhu, Rui Xu, Fengyi Wu, Jinsong Liu",
        "(3)Hao Liu; Hanlong Zhang; Xiaoxi Nie; Wei He; Dongmei Zhang",
        "L. B. Ju; Taiwu Huang; Ran Li; K. Jiang; Chaoneng Wang",
        "ACM SIGMOD China主席、IEEE Transactions on Knowledge and Data Engineering Associate Editor",
    ],
)
def test_rejects_round_7_12_prime_real_bad_titles(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize("title", [None, "", " ", "Short7!"])
def test_rejects_missing_or_tiny_titles(title):
    assert not is_plausible_paper_title(title)


def test_rejects_titles_longer_than_300_chars():
    title = "Graph representation learning " * 12
    assert len(title) > 300
    assert not is_plausible_paper_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Alice Smith; Bob Chen; Carol Wang; David Li; Eve Zhang",
        "WANG, Hao; LI, Jun; XU, Rui; ZHU, Qingyuan",
    ],
)
def test_rejects_author_lists_with_many_semicolons(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "(12)Alice Smith and Bob Chen",
        "(3)Hao Liu; Hanlong Zhang",
    ],
)
def test_rejects_digit_prefix_author_shapes(title: str):
    assert not is_plausible_paper_title(title), title


def test_rejects_editorial_bio_not_paper_title():
    """'ACM SIGMOD China主席、IEEE TKDE Associate Editor' is an editorial bio."""
    assert not is_plausible_paper_title(
        "ACM SIGMOD China主席、IEEE TKDE Associate Editor"
    )


@pytest.mark.parametrize(
    "title",
    [
        # Real titles from miroflow_real that must NOT be over-rejected:
        "香猪 ADAMTS-1 基因克隆及遗传效应分析",
        "小型汽油发动机电喷系统平台——MSE2．0",
        "一种Sn-Sb/石墨烯纳米复合材料的制备方法",
        "CONCAVE EXTENDED LINEAR MODELING: A THEORETICAL SYNTHESIS",
        "RELATION BETWEEN WATER TEMPERATURE, WATER EXCHANGE AMOUNT, FEED AND PRAWN DISEASE",
        "4,4'—二偶氮苯重氮氨基偶氮苯分光光度法测定水和废水中的痕量汞（II）",
        "基于ICP-MS/MS分析微量金属元素的原油产地溯源",
        "w (Co)/w (Ni)对Ti(C,N)基金属陶瓷高温氧化和耐腐蚀性能的影响",
        "斑节对虾 CFSH 基因的克隆及其多功能性探究",
        "5-氨基酮戊酸光动力疗法对兔耳痤疮模型皮损及组织中IL-17表达水平的影响",
    ],
)
def test_accepts_cjk_titles_with_acronyms_and_all_caps_english(title: str):
    """Chinese titles with embedded Latin acronyms and all-caps western
    titles must pass — the v1 uppercase_ratio rule over-rejected them."""
    assert is_plausible_paper_title(title), title
