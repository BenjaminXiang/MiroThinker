from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_source_product_quality_audit.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_source_product_quality_audit", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**overrides):
    row = {
        "product_id": "PROD-1",
        "company_id": "COMP-1",
        "company_name": "深圳旭宏医疗科技有限公司",
        "registered_name": "深圳旭宏医疗科技有限公司",
        "company_aliases": ["旭宏医疗"],
        "project_name": "旭宏医疗",
        "description": "企业简称旭宏医疗，专注创新心电系统开发。",
        "team_raw": "",
        "product_name": "Semacare",
        "short_description": "Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床。",
        "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
        "quality_status": "needs_review",
        "evidence_span": "旭宏医疗的 Semacare 专注创新心电系统开发。",
        "news_id": "11111111-1111-1111-1111-111111111111",
        "source_adapter": "pitchhub_36kr",
        "title": "旭宏医疗 | 项目信息-36氪",
        "source_body": "旭宏医疗是一家医疗AI公司。产品服务：Semacare 专注创新心电系统开发，支持临床心电诊断。",
    }
    row.update(overrides)
    return row


def test_audit_product_row_marks_ready_candidate_when_identity_and_product_evidence_pass():
    cli = _import_cli()

    result = cli._audit_product_row(_row())

    assert result["decision"] == "ready_candidate"
    assert result["recommended_status"] == "needs_review"
    assert result["risk_level"] == "low"
    assert result["reasons"] == []


def test_audit_product_row_rejects_company_identity_failure():
    cli = _import_cli()

    result = cli._audit_product_row(
        _row(
            title="智象机器人 | 项目信息-36氪",
            source_body="智象机器人是一家停车机器人研发商。产品服务：停车机器人系统。",
            evidence_span="智象机器人提供停车机器人系统。",
            product_name="停车机器人系统",
            short_description="停车机器人系统。",
        )
    )

    assert result["decision"] == "reject"
    assert result["recommended_status"] == "rejected"
    assert "company_identity_failed" in result["reasons"]


def test_llm_verifier_payload_uses_xlsx_baseline_and_source_evidence():
    cli = _import_cli()
    rule_result = cli._audit_product_row(_row())

    payload = cli._build_llm_verifier_payload(_row(), rule_result)

    baseline = payload["trusted_xlsx_baseline"]
    assert baseline["company_name"] == "深圳旭宏医疗科技有限公司"
    assert baseline["project_name"] == "旭宏医疗"
    assert "专注创新心电系统开发" in baseline["description"]
    assert baseline["company_aliases"] == ["旭宏医疗"]
    assert payload["candidate_product"]["product_name"] == "Semacare"
    assert payload["candidate_product"]["evidence_span"] == "旭宏医疗的 Semacare 专注创新心电系统开发。"
    assert payload["external_source"]["source_adapter"] == "pitchhub_36kr"
    assert "产品服务：Semacare" in payload["external_source"]["source_body"]


def test_llm_verifier_can_accept_true_alias_when_rule_identity_fails():
    cli = _import_cli()
    row = _row(
        company_name="深圳问止中医健康科技有限公司",
        registered_name="深圳问止中医健康科技有限公司",
        company_aliases=[],
        project_name="问止中医",
        description="XLSX 显示项目简称为问止中医，提供中医人工智能辅助诊疗服务。",
        title="问止中医 | 项目信息-36氪",
        source_body="问止中医推出中医大脑，面向基层中医诊疗提供辅助决策。",
        evidence_span="问止中医推出中医大脑，面向基层中医诊疗提供辅助决策。",
        product_name="中医大脑",
        short_description="中医大脑提供中医辅助诊疗服务。",
    )
    rule_result = cli._audit_product_row(row) | {
        "decision": "reject",
        "recommended_status": "rejected",
        "risk_level": "high",
        "reasons": ["company_identity_failed"],
    }
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "company_identity_match": "yes",
                            "matched_company_name_or_alias": "问止中医",
                            "source_section_type": "target_company_profile",
                            "fact_belongs_to_company": "yes",
                            "is_actual_product_or_service": "yes",
                            "evidence_quote": "问止中医推出中医大脑",
                            "decision": "ready_candidate",
                            "confidence": 0.88,
                            "reason": "XLSX project name confirms the alias and the source states the product.",
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )

    result = cli._audit_product_with_llm(
        row,
        rule_result,
        llm_client=llm,
        llm_model="gemma-test",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert result["decision"] == "ready_candidate"
    assert result["recommended_status"] == "ready"
    assert result["risk_level"] == "low"
    assert result["llm_verifier"]["status"] == "verified"
    assert result["llm_verifier"]["matched_company_name_or_alias"] == "问止中医"
    assert result["reasons"] == []
    kwargs = llm.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gemma-test"
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "XLSX baseline is trusted" in kwargs["messages"][0]["content"]


def test_llm_verifier_rejects_same_industry_wrong_company_source():
    cli = _import_cli()
    row = _row(
        title="智象机器人 | 项目信息-36氪",
        source_body="智象机器人是一家停车机器人研发商。产品服务：停车机器人系统。",
        evidence_span="智象机器人提供停车机器人系统。",
        product_name="停车机器人系统",
        short_description="停车机器人系统。",
    )
    rule_result = cli._audit_product_row(row)
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "company_identity_match": "no",
                            "matched_company_name_or_alias": "智象机器人",
                            "source_section_type": "other_company_profile",
                            "fact_belongs_to_company": "no",
                            "is_actual_product_or_service": "yes",
                            "evidence_quote": "智象机器人是一家停车机器人研发商",
                            "decision": "reject",
                            "confidence": 0.93,
                            "reason": "The source is about another company.",
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )

    result = cli._audit_product_with_llm(
        row,
        rule_result,
        llm_client=llm,
        llm_model="gemma-test",
        extra_body={},
    )

    assert result["decision"] == "reject"
    assert result["recommended_status"] == "rejected"
    assert result["llm_verifier"]["source_section_type"] == "other_company_profile"
    assert "llm_company_identity_no" in result["reasons"]


def test_llm_verifier_accepts_textual_high_confidence():
    cli = _import_cli()
    rule_result = cli._audit_product_row(_row())
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "company_identity_match": "yes",
                            "matched_company_name_or_alias": "旭宏医疗",
                            "source_section_type": "target_company_profile",
                            "fact_belongs_to_company": "yes",
                            "is_actual_product_or_service": "yes",
                            "evidence_quote": "旭宏医疗的 Semacare",
                            "decision": "ready_candidate",
                            "confidence": "high",
                            "reason": "Source matches the trusted baseline.",
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )

    result = cli._audit_product_with_llm(
        _row(),
        rule_result,
        llm_client=llm,
        llm_model="gemma-test",
        extra_body={},
    )

    assert result["decision"] == "ready_candidate"
    assert result["llm_verifier"]["confidence"] == 0.85


def test_llm_verifier_failure_does_not_turn_identity_uncertainty_into_rejection():
    cli = _import_cli()
    row = _row(
        title="问止中医 | 项目信息-36氪",
        source_body="问止中医推出中医大脑，面向基层中医诊疗提供辅助决策。",
        evidence_span="问止中医推出中医大脑。",
        product_name="中医大脑",
        short_description="中医大脑提供中医辅助诊疗服务。",
    )
    rule_result = cli._audit_product_row(row)
    assert "company_identity_failed" in rule_result["reasons"]
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("LLM unavailable")

    result = cli._audit_product_with_llm(
        row,
        rule_result,
        llm_client=llm,
        llm_model="gemma-test",
        extra_body={},
    )

    assert result["decision"] == "needs_review"
    assert result["recommended_status"] == "needs_review"
    assert result["risk_level"] == "medium"
    assert result["reasons"] == []
    assert "llm_verification_failed" in result["warnings"]
    assert result["llm_verifier"]["status"] == "failed"


def test_audit_product_row_rejects_generic_product_name():
    cli = _import_cli()

    result = cli._audit_product_row(
        _row(
            product_name="产品服务",
            short_description="产品服务覆盖医疗AI平台。",
            evidence_span="旭宏医疗产品服务覆盖医疗AI平台。",
        )
    )

    assert result["decision"] == "reject"
    assert result["recommended_status"] == "rejected"
    assert "invalid_product_name" in result["reasons"]


def test_audit_product_row_rejects_product_not_grounded_in_source():
    cli = _import_cli()

    result = cli._audit_product_row(
        _row(
            product_name="UnmentionedPlatform",
            short_description="官网未提到的产品。",
            evidence_span="旭宏医疗专注创新心电系统开发。",
            source_body="旭宏医疗专注创新心电系统开发，支持临床心电诊断。",
        )
    )

    assert result["decision"] == "reject"
    assert result["recommended_status"] == "rejected"
    assert "product_not_grounded_in_source" in result["reasons"]


def test_audit_product_row_rejects_sentence_fragment_product_names():
    cli = _import_cli()

    result = cli._audit_product_row(
        _row(
            product_name="我们希望通过计算巢构建一个开放的企业服务",
            short_description="我们希望通过计算巢构建一个开放的企业服务。",
            evidence_span="图灵集市希望通过计算巢构建一个开放的企业服务。",
            source_body="图灵集市希望通过计算巢构建一个开放的企业服务。",
        )
    )

    assert result["decision"] == "reject"
    assert result["recommended_status"] == "rejected"
    assert "invalid_product_name" in result["reasons"]


def test_build_product_select_sql_scopes_to_batch_and_source_products():
    cli = _import_cli()

    sql, params = cli._build_source_product_select_sql(
        batch_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        limit=50,
        include_rejected=False,
    )

    assert "company_enrichment_company_state" in sql
    assert "company_enrichment_batch" in sql
    assert "pitchhub.36kr.com" in sql
    assert "data.iyiou.com" in sql
    assert "p.quality_status != 'rejected'" in sql
    assert params["batch_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert params["limit"] == 50


def test_apply_audit_rejections_writes_review_actions(monkeypatch):
    cli = _import_cli()
    conn = MagicMock()
    reviewed: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        cli,
        "review_enrichment_item",
        lambda _conn, **kwargs: reviewed.append(
            (kwargs["target_id"], kwargs["action"], kwargs["note"])
        )
        or {"target_id": kwargs["target_id"]},
    )

    updated = cli._apply_audit_actions(
        conn,
        [
            {
                "product_id": "PROD-1",
                "decision": "reject",
                "recommended_status": "rejected",
                "reasons": ["company_identity_failed"],
            },
            {
                "product_id": "PROD-2",
                "decision": "ready_candidate",
                "recommended_status": "needs_review",
                "reasons": [],
            },
        ],
        actor="quality-audit",
        apply_rejections=True,
        promote_ready=False,
    )

    assert updated == {"rejected": 1, "ready": 0}
    assert reviewed == [
        (
            "PROD-1",
            "reject",
            "source_product_quality_audit: company_identity_failed",
        )
    ]


def test_cli_dry_run_outputs_audit_report(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [_row()]
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    exit_code = cli.main(
        [
            "--batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--dry-run",
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["batch_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert report["dry_run"] is True
    assert report["totals"]["audited"] == 1
    assert report["decision_counts"] == {"ready_candidate": 1}


def test_cli_llm_verify_outputs_verifier_metrics(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [_row()]
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "company_identity_match": "yes",
                            "matched_company_name_or_alias": "旭宏医疗",
                            "source_section_type": "target_company_profile",
                            "fact_belongs_to_company": "yes",
                            "is_actual_product_or_service": "yes",
                            "evidence_quote": "旭宏医疗的 Semacare",
                            "decision": "ready_candidate",
                            "confidence": 0.86,
                            "reason": "Source matches the trusted baseline.",
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )
    monkeypatch.setattr(cli, "_open_llm_client", lambda _profile: (llm, "gemma-test", {}))

    exit_code = cli.main(
        [
            "--batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--dry-run",
            "--limit",
            "1",
            "--llm-verify",
        ]
    )

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["llm_verify"] is True
    assert report["totals"]["llm_verified"] == 1
    assert report["totals"]["llm_failed"] == 0
    assert report["decision_counts"] == {"ready_candidate": 1}
