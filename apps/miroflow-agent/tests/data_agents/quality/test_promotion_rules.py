from __future__ import annotations

from src.data_agents.quality.promotion_rules import (
    evaluate_company,
    evaluate_paper,
    evaluate_professor,
)


def _text(length: int) -> str:
    return "x" * length


def _zh_summary() -> str:
    return (
        "该教师长期从事人工智能与医学影像分析研究，聚焦脑疾病诊断、预后评估和多模态数据融合。"
        "其工作结合深度学习、可信人工智能和临床应用场景，形成了较稳定的研究方向。"
        "相关成果服务于智能医疗系统建设，并在人才培养和科研合作中持续积累影响。"
        "近年的研究强调算法可靠性、模型解释性和真实临床数据验证，能够为深圳高校的交叉学科布局提供支撑。"
        "团队也关注医学数据治理和跨院校协作，推动算法从实验室验证走向可审计的真实应用，并形成稳定成果。"
    )


def test_evaluate_professor_high_ready() -> None:
    assert evaluate_professor(
        {"identity_status": "confirmed", "profile_summary": _zh_summary()}
    ) == ("ready", None)


def test_evaluate_professor_resolved_matches_confirmed_schema_semantics() -> None:
    assert evaluate_professor(
        {"identity_status": "resolved", "profile_summary": _zh_summary()}
    ) == ("ready", None)


def test_evaluate_professor_medium_summary_too_short() -> None:
    assert evaluate_professor(
        {"identity_status": "confirmed", "profile_summary": "摘要过短。"}
    ) == ("needs_review", "professor_summary_too_short")


def test_evaluate_professor_rejects_no_chinese_summary() -> None:
    assert evaluate_professor(
        {
            "identity_status": "resolved",
            "profile_summary": (
                "Ahmed Elazab is an Assistant Professor at Tsinghua SIGS. "
                "His research focuses on trustworthy artificial intelligence "
                "for medical image analysis, brain disease diagnosis, and "
                "multi-modal neuroimaging data."
            ),
        }
    ) == ("needs_review", "professor_summary_not_chinese")


def test_evaluate_professor_rejects_english_dominant_summary() -> None:
    assert evaluate_professor(
        {
            "identity_status": "resolved",
            "profile_summary": (
                "Ahmed Elazab is an Assistant Professor (助理教授) and Doctoral "
                "Supervisor (博士生导师) at Tsinghua SIGS. His research focuses "
                "on developing trustworthy artificial intelligence (可信人工智能) "
                "for medical image analysis, brain disease diagnosis and prognosis."
            ),
        }
    ) == ("needs_review", "professor_summary_english_dominant")


def test_evaluate_professor_rejects_too_long_summary() -> None:
    assert evaluate_professor(
        {
            "identity_status": "resolved",
            "profile_summary": _zh_summary() * 3,
        }
    ) == ("needs_review", "professor_summary_too_long")


def test_evaluate_professor_low_unconfirmed_no_issue() -> None:
    assert evaluate_professor(
        {"identity_status": "unverified", "profile_summary": _text(200)}
    ) == ("needs_review", None)


def test_evaluate_company_high_ready() -> None:
    assert evaluate_company(
        {
            "profile_summary": _text(100),
            "technology_route_summary": "route summary",
        }
    ) == ("ready", None)


def test_evaluate_company_medium_partial_narrative() -> None:
    assert evaluate_company(
        {"profile_summary": _text(100), "technology_route_summary": None}
    ) == ("needs_review", "company_partial_narrative")


def test_evaluate_company_low_no_narrative() -> None:
    assert evaluate_company(
        {"profile_summary": None, "technology_route_summary": ""}
    ) == ("needs_review", "company_no_narrative")


def test_evaluate_paper_high_ready() -> None:
    assert evaluate_paper(
        {
            "summary_zh": _text(150),
            "abstract_clean": "abstract",
            "identity_status": "confirmed",
        }
    ) == ("ready", None)


def test_evaluate_paper_medium_partial_metadata() -> None:
    assert evaluate_paper(
        {
            "summary_zh": None,
            "abstract_clean": "abstract",
            "identity_status": "unverified",
        }
    ) == ("needs_review", "paper_partial_metadata")


def test_evaluate_paper_low_no_abstract_no_issue() -> None:
    assert evaluate_paper(
        {
            "summary_zh": None,
            "abstract_clean": None,
            "identity_status": "unverified",
        }
    ) == ("needs_review", None)
