from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module
from backend.services.chat_context import (
    ChipPredicate,
    detect_chip_predicate,
    evaluate_chip_predicate,
)


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "narrowing-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


@pytest.fixture(autouse=True)
def _disable_web(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_AUGMENT_WEB", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")


def _seed_result_set(
    store: _FakeSessionStore,
    domain: str,
    ids: list[str],
    *,
    session_id: str = "narrowing-session",
) -> None:
    session = chat_module.SessionContext(session_id=session_id)
    session.push_result_set(domain, ids)
    store.sessions[session_id] = session


@pytest.mark.parametrize(
    ("query", "domain", "expected_kind", "expected_param"),
    [
        ("上述哪些在深圳", "professor", "region", {"city": "深圳"}),
        ("上述哪些总部在广州", "company", "region", {"city": "广州"}),
        ("上述哪些是近两年的", "paper", "recency", {"mode": "recent_years", "years": 2}),
        ("上述哪些是2024年的", "patent", "recency", {"mode": "year", "year": 2024}),
        ("上述哪些已授权", "patent", "grant_status", {"status": "granted"}),
        ("上述哪些申请人是企业", "patent", "applicant_type", {"type": "企业"}),
    ],
)
def test_detect_chip_predicate_closed_table(
    query: str,
    domain: str,
    expected_kind: str,
    expected_param: dict[str, Any],
) -> None:
    predicate = detect_chip_predicate(query, domain)

    assert predicate is not None
    assert predicate.domain == domain
    assert predicate.kind == expected_kind
    assert predicate.param == expected_param


@pytest.mark.parametrize(
    ("query", "domain"),
    [
        ("上述哪些在深圳", "paper"),
        ("上述哪些在深圳", "patent"),
        ("上述哪些是近两年的", "company"),
        ("上述哪些已授权", "paper"),
        ("上述哪些申请人是企业", "company"),
        ("其中做大模型的", "professor"),
    ],
)
def test_detect_chip_predicate_returns_none_for_non_applicable_domains(
    query: str,
    domain: str,
) -> None:
    assert detect_chip_predicate(query, domain) is None


@pytest.mark.parametrize(
    ("domain", "row", "predicate", "expected_verdict", "basis_text"),
    [
        (
            "professor",
            {"professor_id": "PROF-1", "canonical_name": "李明", "institution": "清华大学深圳国际研究生院"},
            ChipPredicate(kind="region", domain="professor", param={"city": "深圳"}),
            True,
            "清华大学深圳国际研究生院 -> 在深圳",
        ),
        (
            "professor",
            {"professor_id": "PROF-2", "canonical_name": "王强", "institution": "北京大学"},
            ChipPredicate(kind="region", domain="professor", param={"city": "深圳"}),
            False,
            "北京大学 -> 不在深圳",
        ),
        (
            "professor",
            {"professor_id": "PROF-3", "canonical_name": "赵空", "institution": ""},
            ChipPredicate(kind="region", domain="professor", param={"city": "深圳"}),
            None,
            "机构信息缺失",
        ),
        (
            "company",
            {"company_id": "COMP-1", "canonical_name": "未来机器人", "hq_city": "深圳", "is_shenzhen": True},
            ChipPredicate(kind="region", domain="company", param={"city": "深圳"}),
            True,
            "hq_city=深圳 -> 在深圳",
        ),
        (
            "company",
            {"company_id": "COMP-2", "canonical_name": "深圳市前缀科技"},
            ChipPredicate(kind="region", domain="company", param={"city": "深圳"}),
            True,
            "名称前缀=深圳市前缀科技 -> 在深圳",
        ),
        (
            "company",
            {"company_id": "COMP-3", "canonical_name": "北京未来科技", "hq_city": "北京"},
            ChipPredicate(kind="region", domain="company", param={"city": "深圳"}),
            False,
            "hq_city=北京 -> 不在深圳",
        ),
        (
            "company",
            {"company_id": "COMP-4", "canonical_name": "未来科技"},
            ChipPredicate(kind="region", domain="company", param={"city": "深圳"}),
            None,
            "地区信息缺失",
        ),
        (
            "paper",
            {"paper_id": "PAPER-1", "title_clean": "近年论文", "year": 2024},
            ChipPredicate(kind="recency", domain="paper", param={"mode": "year", "year": 2024}),
            True,
            "year=2024 -> 2024年",
        ),
        (
            "paper",
            {"paper_id": "PAPER-2", "title_clean": "旧论文", "year": 2022},
            ChipPredicate(kind="recency", domain="paper", param={"mode": "year", "year": 2024}),
            False,
            "year=2022 -> 不满足2024年",
        ),
        (
            "paper",
            {"paper_id": "PAPER-3", "title_clean": "缺年论文", "year": None},
            ChipPredicate(kind="recency", domain="paper", param={"mode": "year", "year": 2024}),
            None,
            "年份信息缺失",
        ),
        (
            "patent",
            {"patent_id": "PAT-1", "patent_number": "CN1", "grant_date": "2025-01-01", "filing_date": "2023-01-01"},
            ChipPredicate(kind="grant_status", domain="patent", param={"status": "granted"}),
            True,
            "grant_date=2025-01-01 -> 已授权",
        ),
        (
            "patent",
            {"patent_id": "PAT-2", "patent_number": "CN2", "grant_date": None, "filing_date": "2023-01-01"},
            ChipPredicate(kind="grant_status", domain="patent", param={"status": "granted"}),
            False,
            "filing_date=2023-01-01 -> 未见授权日",
        ),
        (
            "patent",
            {"patent_id": "PAT-3", "patent_number": "CN3", "grant_date": None, "filing_date": None},
            ChipPredicate(kind="grant_status", domain="patent", param={"status": "granted"}),
            None,
            "授权/申请日期信息缺失",
        ),
        (
            "patent",
            {"patent_id": "PAT-4", "patent_number": "CN4", "applicants_raw": "深圳市未来机器人有限公司"},
            ChipPredicate(kind="applicant_type", domain="patent", param={"type": "企业"}),
            True,
            "applicants_raw=深圳市未来机器人有限公司 -> 企业申请人",
        ),
        (
            "patent",
            {"patent_id": "PAT-5", "patent_number": "CN5", "applicants_raw": "张三; 清华大学"},
            ChipPredicate(kind="applicant_type", domain="patent", param={"type": "企业"}),
            False,
            "applicants_raw=张三; 清华大学 -> 非企业申请人",
        ),
        (
            "patent",
            {"patent_id": "PAT-6", "patent_number": "CN6", "applicants_raw": ""},
            ChipPredicate(kind="applicant_type", domain="patent", param={"type": "企业"}),
            None,
            "申请人信息缺失",
        ),
    ],
)
def test_evaluate_chip_predicate_boundaries(
    domain: str,
    row: dict[str, Any],
    predicate: ChipPredicate,
    expected_verdict: bool | None,
    basis_text: str,
) -> None:
    verdict, basis = evaluate_chip_predicate(domain, row, predicate)

    assert verdict is expected_verdict
    assert basis_text in basis


def test_chip_narrowing_renders_coverage_verdicts_source_ids_and_skips_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_result_set(store, "company", ["COMP-SZ", "COMP-BJ", "COMP-UNK"])
    calls: list[str] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(
        chat_module,
        "_lookup_company_by_id",
        lambda _conn, *, company_id: {
            "COMP-SZ": {
                "type": "company",
                "id": "COMP-SZ",
                "company_id": "COMP-SZ",
                "canonical_name": "深圳未来机器人",
                "hq_city": "深圳",
                "is_shenzhen": True,
            },
            "COMP-BJ": {
                "type": "company",
                "id": "COMP-BJ",
                "company_id": "COMP-BJ",
                "canonical_name": "北京未来科技",
                "hq_city": "北京",
            },
            "COMP-UNK": {
                "type": "company",
                "id": "COMP-UNK",
                "company_id": "COMP-UNK",
                "canonical_name": "未来科技",
            },
        }[company_id],
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_narrowed_results",
        lambda *_args, **_kwargs: pytest.fail("chip predicates must not use topic retrieval"),
    )

    def fail_synthesis(*_args: Any, **_kwargs: Any) -> str:
        calls.append("llm")
        raise AssertionError("chip narrowing must skip synthesis")

    monkeypatch.setattr(chat_module, "_call_gemma_synthesis", fail_synthesis)

    response = chat_module.chat(
        chat_module.ChatRequest(query="上述哪些在深圳"),
        response=Response(),
        miroflow_chat_session="narrowing-session",
        conn=object(),
    )

    assert calls == []
    assert response.query_type == "D_narrowing"
    assert "上轮 3 个企业中，1 个在深圳，1 个不满足，1 个信息缺失。" in response.answer_text
    assert response.answer_text.index("深圳未来机器人") < response.answer_text.index("北京未来科技")
    assert response.answer_text.index("北京未来科技") < response.answer_text.index("未来科技")
    assert [citation.id for citation in response.citations] == ["COMP-SZ"]
    assert response.structured_payload["source_ids"] == ["COMP-SZ", "COMP-BJ", "COMP-UNK"]
    assert response.structured_payload["predicate"]["kind"] == "region"
    assert response.structured_payload["verdicts"] == [
        {
            "member_id": "COMP-SZ",
            "label": "深圳未来机器人",
            "verdict": True,
            "basis": "深圳未来机器人 - hq_city=深圳 -> 在深圳",
        },
        {
            "member_id": "COMP-BJ",
            "label": "北京未来科技",
            "verdict": False,
            "basis": "北京未来科技 - hq_city=北京 -> 不在深圳",
        },
        {
            "member_id": "COMP-UNK",
            "label": "未来科技",
            "verdict": None,
            "basis": "未来科技 - 地区信息缺失 -> 信息缺失",
        },
    ]
    assert [row["company_id"] for row in response.structured_payload["retrieval_evidence"]] == [
        "COMP-SZ"
    ]
    assert store.sessions["narrowing-session"].last_result_set["company"] == ["COMP-SZ"]


def test_open_predicate_lane_uses_mocked_llm_and_beats_topic_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_result_set(store, "company", ["COMP-A", "COMP-B"])
    calls: list[dict[str, Any]] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(
        chat_module,
        "_lookup_company_by_id",
        lambda _conn, *, company_id: {
            "COMP-A": {
                "type": "company",
                "id": "COMP-A",
                "company_id": "COMP-A",
                "canonical_name": "电梯机器人",
                "products": [{"name": "自主按电梯机械臂", "description": "可识别楼层按钮并自主按电梯"}],
            },
            "COMP-B": {
                "type": "company",
                "id": "COMP-B",
                "company_id": "COMP-B",
                "canonical_name": "通用视觉",
                "products": [{"name": "工业相机", "description": "用于质检"}],
            },
        }[company_id],
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_narrowed_results",
        lambda *_args, **_kwargs: pytest.fail("open predicate should beat topic retrieval when synthesis is on"),
    )

    def mocked_llm(query: str, evidence_text: str, **kwargs: Any) -> str:
        calls.append({"query": query, "evidence_text": evidence_text, **kwargs})
        return json.dumps(
            [
                {
                    "member_id": "COMP-A",
                    "verdict": True,
                    "evidence_field": "products",
                    "quote": "可识别楼层按钮并自主按电梯",
                },
                {
                    "member_id": "COMP-B",
                    "verdict": False,
                    "evidence_field": "products",
                    "quote": "用于质检",
                },
            ],
            ensure_ascii=False,
        )

    monkeypatch.setattr(chat_module, "_call_gemma_synthesis", mocked_llm)

    response = chat_module.chat(
        chat_module.ChatRequest(query="上述企业的产品有哪些可以实现机械臂自主按电梯"),
        response=Response(),
        miroflow_chat_session="narrowing-session",
        conn=object(),
    )

    assert len(calls) == 1
    assert "COMP-A" in calls[0]["evidence_text"]
    assert response.query_type == "D_narrowing"
    assert "上轮 2 个企业中，1 个满足，1 个不满足，0 个信息缺失。" in response.answer_text
    assert "电梯机器人 - products: 可识别楼层按钮并自主按电梯 -> 满足" in response.answer_text
    assert "通用视觉 - products: 用于质检 -> 不满足" in response.answer_text
    assert [citation.id for citation in response.citations] == ["COMP-A"]
    assert response.structured_payload["open_predicate_verdicts"][0] == {
        "member_id": "COMP-A",
        "verdict": True,
        "evidence_field": "products",
        "quote": "可识别楼层按钮并自主按电梯",
    }
    assert [row["company_id"] for row in response.structured_payload["retrieval_evidence"]] == [
        "COMP-A"
    ]


def test_open_predicate_degrades_to_labeled_topic_narrowing_when_synthesis_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_result_set(store, "professor", ["PROF-1", "PROF-2"])
    retrieval_calls: list[str] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def narrow(
        _conn: Any,
        *,
        domain: str,
        allowed_ids: list[str],
        topic: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        retrieval_calls.append(topic)
        assert domain == "professor"
        assert allowed_ids == ["PROF-1", "PROF-2"]
        return [
            {
                "type": "professor",
                "id": "PROF-2",
                "professor_id": "PROF-2",
                "canonical_name": "张敏",
                "institution": "南方科技大学",
            }
        ]

    monkeypatch.setattr(chat_module, "_lookup_narrowed_results", narrow)
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda *_args, **_kwargs: pytest.fail("synthesis-off degradation must not call LLM"),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="其中偏硬件落地能力强的"),
        response=Response(),
        miroflow_chat_session="narrowing-session",
        conn=object(),
    )

    assert retrieval_calls == ["偏硬件落地能力强"]
    assert response.query_type == "D_narrowing"
    assert response.answer_text.startswith("按语义相关性筛选：")
    assert "张敏" in response.answer_text
    assert response.structured_payload["narrowing_mechanism"] == "topic"
    assert response.structured_payload["degraded_from_open_predicate"] is True
