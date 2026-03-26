from __future__ import annotations

from pathlib import Path

from company_data_agent.config import ArtifactLayout
from company_data_agent.importer import SkeletonImportActionType, SkeletonImporter
from company_data_agent.identity import generate_company_id
from company_data_agent.ingest import MasterListParseError, MasterListParseResult, ParsedMasterListRow
from company_data_agent.models.company_record import CompanySource, PartialCompanyRecord


def build_layout() -> ArtifactLayout:
    return ArtifactLayout.model_validate({"root_dir": "artifacts/company-data-agent"})


def build_row(
    row_number: int,
    *,
    name: str,
    credit_code: str,
    registered_address: str | None = None,
    industry: str | None = None,
    source_path: str = "data/shenzhen_company_list.xlsx",
) -> ParsedMasterListRow:
    return ParsedMasterListRow(
        row_number=row_number,
        source_path=source_path,
        raw_columns={
            "企业名称": name,
            "统一社会信用代码": credit_code,
            "注册地址": registered_address,
            "行业分类": industry,
        },
        name=name,
        credit_code=credit_code,
        registered_address=registered_address,
        industry=industry,
    )


def build_parse_result(
    rows: list[ParsedMasterListRow],
    *,
    errors: list[MasterListParseError] | None = None,
    source_path: str = "data/shenzhen_company_list.xlsx",
) -> MasterListParseResult:
    return MasterListParseResult(
        rows=rows,
        errors=errors or [],
        source_path=source_path,
    )


def test_skeleton_import_creates_deduplicated_records_and_report() -> None:
    parse_result = build_parse_result(
        [
            build_row(
                2,
                name="深圳未来机器人有限公司",
                credit_code="91440300MA5FUTURE1",
                registered_address="深圳市南山区",
            ),
            build_row(
                3,
                name="深圳未来机器人有限公司",
                credit_code="91440300MA5FUTURE1",
                industry="机器人",
            ),
            build_row(
                4,
                name="深圳智算科技有限公司",
                credit_code="91440300MA5INTELAI",
                registered_address="深圳市福田区",
                industry="人工智能",
            ),
        ]
    )

    result = SkeletonImporter().import_rows(parse_result, build_layout())

    assert [record.credit_code for record in result.records] == [
        "91440300MA5FUTURE1",
        "91440300MA5INTELAI",
    ]
    assert result.records[0].id == generate_company_id("91440300MA5FUTURE1")
    assert result.records[0].registered_address == "深圳市南山区"
    assert result.records[0].industry == "机器人"
    assert result.report.created_count == 2
    assert result.report.updated_count == 0
    assert result.report.skipped_count == 0
    assert result.report.failed_count == 0
    assert result.report.actions[0].row_numbers == [2, 3]
    assert result.report.actions[0].action is SkeletonImportActionType.CREATED


def test_skeleton_import_updates_existing_record_and_preserves_existing_fields() -> None:
    existing = PartialCompanyRecord.model_validate(
        {
            "id": generate_company_id("91440300MA5FUTURE1"),
            "name": "深圳未来机器人旧名称有限公司",
            "credit_code": "91440300MA5FUTURE1",
            "website": "https://future-robotics.example",
            "sources": [CompanySource.WEBSITE],
            "raw_data_path": "raw/previous.json",
        }
    )

    parse_result = build_parse_result(
        [
            build_row(
                2,
                name="深圳未来机器人有限公司",
                credit_code="91440300MA5FUTURE1",
                registered_address="深圳市南山区",
                industry="机器人",
            )
        ]
    )

    result = SkeletonImporter().import_rows(parse_result, build_layout(), existing_records=[existing])

    record = result.records[0]
    assert record.name == "深圳未来机器人有限公司"
    assert record.website == "https://future-robotics.example"
    assert record.sources == [CompanySource.MASTER_LIST, CompanySource.WEBSITE]
    assert result.report.updated_count == 1
    assert result.report.actions[0].action is SkeletonImportActionType.UPDATED


def test_skeleton_import_skips_unchanged_existing_record_and_counts_failures() -> None:
    existing = PartialCompanyRecord.model_validate(
        {
            "id": generate_company_id("91440300MA5FUTURE1"),
            "name": "深圳未来机器人有限公司",
            "credit_code": "91440300MA5FUTURE1",
            "registered_address": "深圳市南山区",
            "industry": "机器人",
            "sources": [CompanySource.MASTER_LIST],
            "raw_data_path": "artifacts/company-data-agent/raw/companies/91440300MA5FUTURE1/master_list/shenzhen_company_list-row-000002.json",
        }
    )
    parse_result = build_parse_result(
        [
            build_row(
                2,
                name="深圳未来机器人有限公司",
                credit_code="91440300MA5FUTURE1",
                registered_address="深圳市南山区",
                industry="机器人",
            )
        ],
        errors=[
            MasterListParseError(
                row_number=3,
                source_path="data/shenzhen_company_list.xlsx",
                message="missing required columns: name",
                raw_columns={"统一社会信用代码": "91440300MA5BROKEN01"},
            )
        ],
    )

    result = SkeletonImporter().import_rows(parse_result, build_layout(), existing_records=[existing])

    assert result.report.created_count == 0
    assert result.report.updated_count == 0
    assert result.report.skipped_count == 1
    assert result.report.failed_count == 1
    assert result.report.actions[0].action is SkeletonImportActionType.SKIPPED
    assert result.report.failures[0].row_number == 3


def test_skeleton_import_is_deterministic_on_rerun() -> None:
    parse_result = build_parse_result(
        [
            build_row(
                2,
                name="深圳未来机器人有限公司",
                credit_code="91440300MA5FUTURE1",
                registered_address="深圳市南山区",
                industry="机器人",
            )
        ]
    )

    importer = SkeletonImporter()
    first = importer.import_rows(parse_result, build_layout())
    second = importer.import_rows(parse_result, build_layout())

    assert [record.model_dump(mode="python") for record in first.records] == [
        record.model_dump(mode="python") for record in second.records
    ]
    assert first.report.model_dump(mode="python") == second.report.model_dump(mode="python")


def test_invalid_credit_code_from_parsed_row_becomes_failure() -> None:
    parse_result = build_parse_result(
        [
            build_row(
                2,
                name="深圳未来机器人有限公司",
                credit_code="bad-code",
                registered_address="深圳市南山区",
            )
        ]
    )

    result = SkeletonImporter().import_rows(parse_result, build_layout())

    assert not result.records
    assert result.report.failed_count == 1
    assert "credit_code" in result.report.failures[0].message
