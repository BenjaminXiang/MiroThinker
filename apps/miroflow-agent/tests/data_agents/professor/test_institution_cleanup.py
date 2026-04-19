import pytest

from src.data_agents.professor.institution_cleanup import (
    strip_trailing_person_name,
)


@pytest.mark.parametrize(
    "institution, expected",
    [
        # Real samples from miroflow_real — only known-SZ institution prefix gets stripped
        ("中山大学（深圳） 陈伟津", "中山大学（深圳）"),
        ("香港中文大学（深圳） Jianwei Huang", "香港中文大学（深圳）"),
        ("深圳技术大学 张三", "深圳技术大学"),
        ("南方科技大学 Connie Chang-Hasnain", "南方科技大学"),
        # No change when prefix is NOT a known SZ primary institution
        # (these are legit historical affiliations)
        ("中山大学 生态学院", "中山大学 生态学院"),
        ("北京大学 工学院", "北京大学 工学院"),
        ("加州大学伯克利分校 & 戴维斯分校", "加州大学伯克利分校 & 戴维斯分校"),
        ("新加坡国立大学电气与计算机工程系Social Robotics Lab",
         "新加坡国立大学电气与计算机工程系Social Robotics Lab"),
        # No change when suffix is a department word (even after known prefix)
        ("清华大学深圳国际研究生院 信息学部", "清华大学深圳国际研究生院 信息学部"),
        ("深圳技术大学 工程物理学院", "深圳技术大学 工程物理学院"),
        # No change when CN suffix ends with 院/系/所/室/组/校 (dept, not person)
        ("清华大学深圳国际研究生院 数信院", "清华大学深圳国际研究生院 数信院"),
        ("深圳技术大学 物理系", "深圳技术大学 物理系"),
        ("南方科技大学 生物所", "南方科技大学 生物所"),
        # No change when no trailing space
        ("中山大学（深圳）", "中山大学（深圳）"),
        ("清华大学深圳国际研究生院", "清华大学深圳国际研究生院"),
        ("深圳技术大学工程物理学院", "深圳技术大学工程物理学院"),
        ("UNKNOWN_INSTITUTION", "UNKNOWN_INSTITUTION"),
        ("MIT", "MIT"),
        ("南科大", "南科大"),
    ],
)
def test_strip_trailing_person_name(institution: str, expected: str):
    assert strip_trailing_person_name(institution) == expected


def test_strip_trailing_person_name_passthrough_for_none_and_empty():
    assert strip_trailing_person_name(None) is None
    assert strip_trailing_person_name("") == ""
    assert strip_trailing_person_name("   ") == "   "


def test_strip_trailing_person_name_handles_single_english_word_not_stripped():
    """A single English word alone is not a name pattern — keep it."""
    assert strip_trailing_person_name("清华大学 Nature") == "清华大学 Nature"
