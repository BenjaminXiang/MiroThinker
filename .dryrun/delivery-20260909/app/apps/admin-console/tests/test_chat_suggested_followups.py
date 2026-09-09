from __future__ import annotations

from backend.api import chat as chat_module


def test_professor_profile_response_suggests_contextual_followups(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")

    response = chat_module._build_chat_response(
        conn=object(),
        query="介绍清华的丁文伯",
        query_type="A_prof_profile",
        answer_text="丁文伯是清华大学深圳国际研究生院教授。",
        citations=[
            chat_module.ChatCitation(
                type="professor",
                id="PROF-001",
                label="丁文伯",
                url="/browse#professor/PROF-001",
            )
        ],
        structured_payload={
            "professor_id": "PROF-001",
            "canonical_name": "丁文伯",
        },
    )

    assert response.suggested_followups == [
        "看看他的论文",
        "他的专利有哪些",
        "他参与创立了哪些企业",
    ]


def test_company_profile_response_suggests_contextual_followups(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")

    response = chat_module._build_chat_response(
        conn=object(),
        query="介绍无界智航",
        query_type="A_company_profile",
        answer_text="无界智航是一家低空智能企业。",
        citations=[
            chat_module.ChatCitation(
                type="company",
                id="COMP-001",
                label="无界智航",
                url="/browse#company/COMP-001",
            )
        ],
        structured_payload={
            "company_id": "COMP-001",
            "canonical_name": "无界智航",
        },
    )

    assert response.suggested_followups == [
        "这家公司有哪些专利",
        "这家公司相关论文有哪些",
        "找相似企业",
    ]


def test_topic_search_response_suggests_narrowing_and_domain_switches(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")

    response = chat_module._build_chat_response(
        conn=object(),
        query="深圳哪些公司做激光雷达",
        query_type="B_company_topic_search",
        answer_text="共找到 6 个企业。",
        citations=[
            chat_module.ChatCitation(
                type="company",
                id="COMP-001",
                label="不止技术",
                url="/browse#company/COMP-001",
            )
        ],
        structured_payload={
            "classifier_topic": "激光雷达",
            "classifier_target_domain": "company",
            "matched_objects": [{"company_id": "COMP-001"}],
        },
    )

    assert response.suggested_followups == [
        "上述哪些在深圳",
        "换成同方向论文",
        "换成同方向专利",
    ]


def test_cross_domain_response_without_results_has_no_result_followups(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")

    response = chat_module._build_chat_response(
        conn=object(),
        query="他参与创立了哪些企业",
        query_type="C_cross_domain_related",
        answer_text="暂未收录丁文伯关联的企业数据。",
        citations=[],
        structured_payload={
            "source_domain": "professor",
            "source_id": "PROF-001",
            "source_label": "丁文伯",
            "target_domain": "company",
            "retrieval_evidence": [],
        },
    )

    assert response.suggested_followups == []
