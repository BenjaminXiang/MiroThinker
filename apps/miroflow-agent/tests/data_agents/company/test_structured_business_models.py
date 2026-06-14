from __future__ import annotations

from decimal import Decimal

from src.data_agents.canonical.company import (
    CompanyApplicationScenario,
    CompanyApplicationScenarioEvidence,
    CompanyProduct,
    CompanyTeamMember,
)


def test_company_product_accepts_structured_business_fields() -> None:
    product = CompanyProduct(
        product_id="PROD-1",
        company_id="COMP-1",
        canonical_name="Semacare",
        short_description="AI cardiac screening service.",
        product_category="medical_ai_ecg",
        target_customers=["hospital", "clinic"],
        application_scenarios=["remote_ecg_diagnosis"],
        technical_tags=["explainable_ai", "ecg"],
        confidence=Decimal("0.75"),
    )

    assert product.product_category == "medical_ai_ecg"
    assert product.target_customers == ["hospital", "clinic"]
    assert product.application_scenarios == ["remote_ecg_diagnosis"]
    assert product.technical_tags == ["explainable_ai", "ecg"]


def test_company_application_scenario_models_preserve_evidence_contract() -> None:
    scenario = CompanyApplicationScenario(
        scenario_id="SCEN-1",
        company_id="COMP-1",
        related_product_id="PROD-1",
        scenario_name="remote_ecg_diagnosis",
        scenario_category="clinical_diagnosis",
        description="Remote ECG diagnosis and monitoring in clinical workflows.",
        target_customer="hospital",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
        quality_status="needs_review",
        confidence=Decimal("0.65"),
    )
    evidence = CompanyApplicationScenarioEvidence(
        scenario_id=scenario.scenario_id,
        field_name="scenario_name",
        source_url=scenario.source_url,
        evidence_span="supports clinical and remote ECG diagnosis and monitoring",
        confidence=Decimal("0.65"),
        extractor_version="source_product_extractor.v1",
    )

    assert scenario.scenario_name == "remote_ecg_diagnosis"
    assert evidence.scenario_id == scenario.scenario_id
    assert evidence.field_name == "scenario_name"


def test_company_team_member_accepts_structured_llm_fields() -> None:
    member = CompanyTeamMember(
        company_id="COMP-1",
        snapshot_id="11111111-1111-1111-1111-111111111111",
        member_order=1,
        raw_name="王博洋",
        raw_role="CEO&联合创始人",
        raw_intro="王博洋，旭宏医疗CEO&联合创始人。",
        normalized_name="王博洋",
        structured_background="连续创业者，长期参与医疗产品商业化。",
        structured_experience_highlights=["医疗产品商业化", "公司经营管理"],
        structured_relevance="负责旭宏医疗整体经营和心电产品商业化。",
        structured_confidence=Decimal("0.86"),
        structured_evidence_span="王博洋，旭宏医疗CEO&联合创始人。",
        structured_raw_text="王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。",
    )

    assert member.structured_background == "连续创业者，长期参与医疗产品商业化。"
    assert member.structured_experience_highlights == [
        "医疗产品商业化",
        "公司经营管理",
    ]
    assert member.structured_confidence == Decimal("0.86")
