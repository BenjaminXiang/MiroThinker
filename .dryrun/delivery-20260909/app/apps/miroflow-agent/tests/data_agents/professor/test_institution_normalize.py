import pytest

from src.data_agents.professor.institution_names import normalize_institution


@pytest.mark.parametrize(
    "raw, expected",
    [
        # South
        ("南方科技大学", "南方科技大学"),
        ("南科大", "南方科技大学"),
        ("SUSTech", "南方科技大学"),
        ("Southern University of Science and Technology", "南方科技大学"),
        # CUHKSZ — the Jianwei Huang case
        ("CUHKSZ", "香港中文大学（深圳）"),
        ("港中深", "香港中文大学（深圳）"),
        ("港中大深圳", "香港中文大学（深圳）"),
        ("CUHK-Shenzhen", "香港中文大学（深圳）"),
        ("The Chinese University of Hong Kong, Shenzhen", "香港中文大学（深圳）"),
        ("香港中文大学(深圳)", "香港中文大学（深圳）"),
        # Tsinghua SIGS
        ("清华大学深圳国际研究生院", "清华大学深圳国际研究生院"),
        ("SIGS", "清华大学深圳国际研究生院"),
        ("THU-SIGS", "清华大学深圳国际研究生院"),
        # Tsinghua older campus — distinct from SIGS
        ("清华大学深圳研究生院", "清华大学深圳研究生院"),
        ("清华深研院", "清华大学深圳研究生院"),
        # HITSZ
        ("HITSZ", "哈尔滨工业大学（深圳）"),
        ("哈深", "哈尔滨工业大学（深圳）"),
        ("哈工大深圳", "哈尔滨工业大学（深圳）"),
        # SYSU-SZ — 陈伟津 case
        ("中大深圳", "中山大学（深圳）"),
        ("中山大学深圳校区", "中山大学（深圳）"),
        ("SYSU Shenzhen", "中山大学（深圳）"),
        # SZTU
        ("深技大", "深圳技术大学"),
        # SZIT / 深理工
        ("深理工", "深圳理工大学"),
        # SZU
        ("深大", "深圳大学"),
        ("SZU", "深圳大学"),
        # PKUSZ
        ("北大深研", "北京大学深圳研究生院"),
        ("PKUSZ", "北京大学深圳研究生院"),
        # SIAT
        ("深先院", "中国科学院深圳先进技术研究院"),
        ("SIAT", "中国科学院深圳先进技术研究院"),
        # Substring match for "<canonical> + extra context"
        ("深圳理工大学生命健康学院", "深圳理工大学"),
        ("南方科技大学计算机科学与工程系", "南方科技大学"),
    ],
)
def test_normalize_institution_recognizes_known_variants(raw: str, expected: str):
    assert normalize_institution(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "UNKNOWN_INSTITUTION"])
def test_normalize_institution_returns_none_for_empty_or_placeholder(raw):
    assert normalize_institution(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "MIT",
        "Stanford",
        "北京大学",  # non-Shenzhen parent institution — no match expected
        "清华大学",  # parent Tsinghua, not the SZ campus
        "Harvard University",
        "Some Random Company",
    ],
)
def test_normalize_institution_returns_none_for_non_shenzhen(raw):
    """Non-Shenzhen institutions correctly return None. The caller keeps
    the original string in is_primary=false affiliations; we only
    canonicalize the Shenzhen primary set."""
    assert normalize_institution(raw) is None
