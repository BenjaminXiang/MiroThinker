from __future__ import annotations

import pytest

from src.data_agents.patent.release import _normalize_patent_type_for_canonical
from src.data_agents.patent.type_inference import infer_patent_type


@pytest.mark.parametrize(
    ("patent_number", "expected"),
    [
        ("CN115709471A", "发明"),
        ("CN115709471B", "发明"),
        ("CN223200311U", "实用新型"),
        ("CN223200311Y", "实用新型"),
        ("CN330000000S", "外观设计"),
        ("CN330000000D", "外观设计"),
    ],
)
def test_kindcode_matrix(patent_number: str, expected: str) -> None:
    assert infer_patent_type(patent_number) == expected


@pytest.mark.parametrize(
    ("patent_number", "expected"),
    [
        ("CN123456789", "发明"),
        ("CN223456789", "实用新型"),
        ("CN323456789", "外观设计"),
        ("CN823456789", "发明"),
        ("CN923456789", "实用新型"),
    ],
)
def test_leading_digit_fallback(patent_number: str, expected: str) -> None:
    assert infer_patent_type(patent_number) == expected


def test_non_overwriting() -> None:
    assert infer_patent_type("CN223200311U", current_type="发明") == "发明"


@pytest.mark.parametrize("patent_number", ["", "CN", "CNX23456789", "not-a-patent"])
def test_unrecognizable_returns_none(patent_number: str) -> None:
    assert infer_patent_type(patent_number) is None


@pytest.mark.parametrize(
    "patent_number",
    [
        "CN115709471A",
        "CN115709471B",
        "CN223200311U",
        "CN223200311Y",
        "CN330000000S",
        "CN330000000D",
        "CN123456789",
        "CN223456789",
        "CN323456789",
        "CN823456789",
        "CN923456789",
    ],
)
def test_roundtrip_with_normalizer(patent_number: str) -> None:
    inferred_type = infer_patent_type(patent_number)

    assert inferred_type is not None
    assert _normalize_patent_type_for_canonical(inferred_type)
