from __future__ import annotations

import pytest

from company_data_agent.identity import (
    CompanyIdentity,
    generate_company_id,
    normalize_credit_code,
    validate_company_id,
)


@pytest.mark.parametrize(
    ("raw_credit_code", "expected"),
    [
        ("91440300MA5FUTURE1", "91440300MA5FUTURE1"),
        (" 91440300ma5future1 ", "91440300MA5FUTURE1"),
        ("9144 0300-MA5FUTURE1", "91440300MA5FUTURE1"),
    ],
)
def test_normalize_credit_code_removes_presentation_noise(
    raw_credit_code: str,
    expected: str,
) -> None:
    assert normalize_credit_code(raw_credit_code) == expected


@pytest.mark.parametrize(
    "raw_credit_code",
    [
        "",
        "91440300MA5FUTURE",
        "91440300MA5FUTURE12",
        "91440300MA5FUTURE!",
        "91中文0300MA5FUTURE1",
    ],
)
def test_invalid_credit_codes_are_rejected(raw_credit_code: str) -> None:
    with pytest.raises(ValueError, match="credit_code"):
        normalize_credit_code(raw_credit_code)


def test_generate_company_id_is_deterministic_snapshot() -> None:
    assert generate_company_id("91440300MA5FUTURE1") == "COMP-9A0B2B5AB656D527B267"
    assert generate_company_id(" 91440300ma5future1 ") == "COMP-9A0B2B5AB656D527B267"


def test_validate_company_id_accepts_canonical_format() -> None:
    assert validate_company_id("COMP-9A0B2B5AB656D527B267") == "COMP-9A0B2B5AB656D527B267"


def test_validate_company_id_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="canonical format"):
        validate_company_id("COMP-91440300MA5FUTURE1")


def test_company_identity_from_raw_credit_code() -> None:
    identity = CompanyIdentity.from_raw_credit_code(" 91440300ma5future1 ")

    assert identity.credit_code == "91440300MA5FUTURE1"
    assert identity.company_id == "COMP-9A0B2B5AB656D527B267"
