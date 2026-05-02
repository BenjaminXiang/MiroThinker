from __future__ import annotations

import pytest

from src.data_agents.normalization import (
    normalize_company_name,
    normalize_company_name_v2,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("深圳市优必选科技股份有限公司", "优必选科技"),
        ("深圳优必选科技股份有限公司", "优必选科技"),
        ("广东省深圳市大疆创新科技有限公司", "大疆创新"),
        ("广东广和通无线股份有限公司", "广和通"),
        ("上海市云从科技有限公司", "云从"),
        ("北京旷视科技有限公司", "旷视"),
        ("北京市旷视科技有限公司", "旷视"),
        ("极智视觉科技（深圳）有限公司", "极智视觉科技"),
        ("极智视觉科技(深圳)有限公司", "极智视觉科技"),
        ("极智视觉科技（中国）有限公司", "极智视觉科技"),
        ("极智视觉科技(中国)有限公司", "极智视觉科技"),
        ("深圳市广和通无线股份有限公司", "广和通"),
        ("深圳市广和通无线", "广和通"),
        ("广和通无线股份", "广和通"),
        ("云天励飞技术股份有限公司", "云天励飞技术"),
        ("优必选智能股份有限公司", "优必选智能"),
        ("优必选科技", "优必选科技"),
        ("优必选技术", "优必选技术"),
        ("优必选智能", "优必选智能"),
        ("云从科技有限公司", "云从"),
        ("云从科技股份", "云从"),
        ("腾讯科技（深圳）有限公司", "腾讯科技"),
        (" 深圳市  腾讯 科技 股份有限公司 ", "腾讯科技"),
        ("深圳市腾讯-科技股份有限公司", "腾讯科技"),
        ("深圳市腾讯·科技有限公司", "腾讯"),
        ("DJI 科技有限公司", "dji"),
        ("深圳市DJI 科技有限公司", "dji"),
        ("广东省 公司A 有限公司", "公司a"),
        ("广东省深圳公司A集团有限公司", "公司a"),
        ("上海市公司A集团", "公司a"),
        ("北京公司A股份", "公司a"),
        ("公司A有限公司", "公司a"),
        ("公司A有限责任公司", "公司a"),
        ("公司A，有限公司", "公司a"),
    ],
)
def test_normalize_company_name_v2_rule_based_cases(raw: str, expected: str) -> None:
    assert normalize_company_name_v2(raw) == expected


def test_normalize_company_name_v2_does_not_change_legacy_normalizer() -> None:
    assert normalize_company_name("深圳市优必选科技股份有限公司") == "优必选科技"
    assert normalize_company_name_v2("深圳市优必选科技股份有限公司") == "优必选科技"


def test_normalize_company_name_v2_does_not_strip_generic_technical_words_alone() -> (
    None
):
    assert normalize_company_name_v2("深圳市光明科技") == "光明科技"
    assert normalize_company_name_v2("深圳市光明技术") == "光明技术"
    assert normalize_company_name_v2("深圳市光明智能") == "光明智能"
