from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from company_data_agent.models.company_record import (
    CompanySource,
    FinalCompanyRecord,
    PartialCompanyRecord,
)


def build_partial(**overrides: object) -> PartialCompanyRecord:
    payload = {
        "name": "深圳未来机器人有限公司",
        "credit_code": "91440300MA5FUTURE1",
        "sources": [CompanySource.MASTER_LIST],
        "raw_data_path": "raw/company/91440300MA5FUTURE1/master.json",
    }
    payload.update(overrides)
    return PartialCompanyRecord.model_validate(payload)


def build_final(**overrides: object) -> FinalCompanyRecord:
    payload = {
        "id": "COMP-91440300MA5FUTURE1",
        "name": "深圳未来机器人有限公司",
        "credit_code": "91440300MA5FUTURE1",
        "profile_summary": "一家聚焦手术机器人与智能控制系统的深圳科技企业，面向医院与科研机构提供核心机器人平台能力。",
        "profile_embedding": [0.1, 0.2, 0.3],
        "sources": [CompanySource.MASTER_LIST, CompanySource.WEBSITE],
        "completeness_score": 78,
        "last_updated": datetime(2026, 3, 21, 16, 0, tzinfo=UTC),
        "raw_data_path": "raw/company/91440300MA5FUTURE1/final.json",
    }
    payload.update(overrides)
    return FinalCompanyRecord.model_validate(payload)


def test_partial_record_accepts_minimal_valid_payload() -> None:
    record = build_partial()

    assert record.id is None
    assert record.credit_code == "91440300MA5FUTURE1"
    assert record.sources == [CompanySource.MASTER_LIST]


def test_final_record_requires_final_invariants() -> None:
    record = build_final(sources=[CompanySource.MASTER_LIST, CompanySource.WEBSITE, CompanySource.MASTER_LIST])

    assert record.id == "COMP-91440300MA5FUTURE1"
    assert record.sources == [CompanySource.MASTER_LIST, CompanySource.WEBSITE]
    assert record.profile_embedding == [0.1, 0.2, 0.3]


def test_invalid_credit_code_is_rejected() -> None:
    with pytest.raises(ValidationError, match="credit_code"):
        build_partial(credit_code="bad-code")


def test_invalid_company_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="company id"):
        build_final(id="BAD-91440300MA5FUTURE1")


def test_completeness_score_must_stay_in_range() -> None:
    with pytest.raises(ValidationError, match="completeness_score"):
        build_final(completeness_score=101)


def test_last_updated_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        build_final(last_updated=datetime(2026, 3, 21, 16, 0))


def test_embedding_must_contain_finite_numbers() -> None:
    with pytest.raises(ValidationError, match="finite"):
        build_final(profile_embedding=[0.1, float("nan")])


def test_nested_key_personnel_payload_is_validated() -> None:
    record = build_partial(
        key_personnel=[
            {
                "name": "张三",
                "role": "CTO",
                "education": [
                    {
                        "institution": "南方科技大学",
                        "degree": "PhD",
                        "year": 2020,
                        "field": "机器人学",
                    }
                ],
            }
        ]
    )

    assert record.key_personnel[0].education[0].institution == "南方科技大学"


def test_sources_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="sources"):
        build_partial(sources=[])
