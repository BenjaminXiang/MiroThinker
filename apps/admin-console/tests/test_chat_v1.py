from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi import Response

from backend.api import chat as chat_module


class _FakeResult:
    def __init__(self, *, rows=None, row=None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self) -> None:
        self.pipeline_issues: list[dict[str, object]] = []

    def execute(self, sql: str, params=None):
        if "INSERT INTO pipeline_issue" not in sql:
            raise AssertionError(f"Unexpected SQL in chat unit test: {sql}")
        professor_id, institution, stage, severity, description, reported_by = params
        self.pipeline_issues.append(
            {
                "professor_id": professor_id,
                "institution": institution,
                "stage": stage,
                "severity": severity,
                "description": description,
                "reported_by": reported_by,
            }
        )
        return _FakeResult()


def test_chat_v1_profile_uses_llm_synthesis_and_returns_citation_map(
    monkeypatch,
) -> None:
    fake_conn = _FakeConn()

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setenv("http_proxy", "http://100.64.0.15:7893")
    monkeypatch.setenv("https_proxy", "http://100.64.0.15:7893")
    monkeypatch.setenv("all_proxy", "http://100.64.0.15:7893")

    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda conn, *, name, institutions: [
            {
                "professor_id": "PROF-001",
                "canonical_name": "丁文伯",
                "canonical_name_en": "Wenbo Ding",
                "institution": "清华大学深圳国际研究生院",
                "title": "教授",
                "discipline_family": "控制科学与工程",
            }
        ],
    )
    monkeypatch.setattr(
        chat_module,
        "_prof_research_topics",
        lambda conn, professor_id: ["机器人", "力控"],
    )
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda conn, professor_id: 12)
    monkeypatch.setattr(
        chat_module,
        "resolve_professor_llm_settings",
        lambda profile_name: {
            "local_llm_base_url": "http://127.0.0.1:8000/v1",
            "local_llm_api_key": "deepseek-secret",
            "local_llm_model": "deepseek-v4-pro",
        },
    )

    class _FakeOpenAI:
        init_calls: list[dict[str, object]] = []
        create_calls: list[dict[str, object]] = []

        def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
            self.__class__.init_calls.append(
                {
                    "base_url": base_url,
                    "api_key": api_key,
                    "timeout": timeout,
                }
            )
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs):
            self.__class__.create_calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="丁文伯任职于清华大学深圳国际研究生院[1]，目前职称为教授[2]。"
                        )
                    )
                ]
            )

    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍清华的丁文伯"),
        response=Response(),
        conn=fake_conn,
    )

    assert response.answer_style == "llm_synthesized"
    assert response.answer_text.endswith("[2]。")
    assert response.citation_map == {
        "1": "PROF-001",
        "2": "PROF-001",
        "3": "PROF-001",
        "4": "PROF-001",
        "5": "PROF-001",
        "6": "PROF-001",
    }
    assert fake_conn.pipeline_issues == []
    assert _FakeOpenAI.init_calls == [
        {
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "deepseek-secret",
            "timeout": 3.0,
        }
    ]
    assert _FakeOpenAI.create_calls[0]["model"] == "deepseek-v4-pro"
    assert _FakeOpenAI.create_calls[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "用户问题: 介绍清华的丁文伯" in _FakeOpenAI.create_calls[0]["messages"][1]["content"]
    assert "http_proxy" not in os.environ
    assert "https_proxy" not in os.environ
    assert "all_proxy" not in os.environ


def test_chat_profile_accepts_introduce_once_professor_variant(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda conn, *, name, institutions: [
            {
                "professor_id": "PROF-LIXUAN",
                "canonical_name": "李轩",
                "canonical_name_en": None,
                "institution": "电子科技大学（深圳）高等研究院",
                "title": "研究员",
                "discipline_family": "electrical_engineering",
            }
        ]
        if name == "李轩"
        else [],
    )
    monkeypatch.setattr(
        chat_module,
        "_prof_research_topics",
        lambda conn, professor_id: ["宽禁带碳化硅基功率器件", "封装及应用研究"],
    )
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda conn, professor_id: 12)

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍一下李轩教授"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert response.structured_payload["professor_id"] == "PROF-LIXUAN"
    assert response.structured_payload["verified_paper_count"] == 12
    assert "宽禁带碳化硅基功率器件" in response.answer_text


def test_chat_profile_accepts_name_institution_research_and_papers_query(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda conn, *, name, institutions: [
            {
                "professor_id": "PROF-LIXUAN",
                "canonical_name": "李轩",
                "canonical_name_en": None,
                "institution": "电子科技大学（深圳）高等研究院",
                "title": "研究员",
                "discipline_family": "electrical_engineering",
            }
        ]
        if name == "李轩"
        else [],
    )
    monkeypatch.setattr(
        chat_module,
        "_prof_research_topics",
        lambda conn, professor_id: ["宽禁带碳化硅基功率器件", "封装及应用研究"],
    )
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda conn, professor_id: 12)

    response = chat_module.chat(
        chat_module.ChatRequest(query="李轩 电子科技大学深圳高等研究院 的研究方向和论文情况是什么？"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert response.structured_payload["professor_id"] == "PROF-LIXUAN"
    assert response.structured_payload["verified_paper_count"] == 12
    assert "封装及应用研究" in response.answer_text


def test_chat_profile_accepts_institution_prefixed_research_direction_query(
    monkeypatch,
) -> None:
    lookup_calls: list[tuple[str, tuple[str, ...] | None]] = []

    def lookup_professor(conn, *, name, institutions):
        lookup_calls.append((name, institutions))
        if name == "夏树涛" and institutions == ("清华大学深圳国际研究生院", "清华大学深圳研究生院"):
            return [
                {
                    "professor_id": "PROF-XIASHUTAO",
                    "canonical_name": "夏树涛",
                    "canonical_name_en": None,
                    "institution": "清华大学深圳国际研究生院",
                    "title": "教授",
                    "discipline_family": "information_theory",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(
        chat_module,
        "_prof_research_topics",
        lambda conn, professor_id: ["信息论", "编码"],
    )
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda conn, professor_id: 211)

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍清华大学深圳国际研究生院夏树涛的研究方向"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert response.structured_payload["professor_id"] == "PROF-XIASHUTAO"
    assert response.structured_payload["research_topics"] == ["信息论", "编码"]
    assert "夏树涛" in response.answer_text
    assert lookup_calls[0] == (
        "夏树涛",
        ("清华大学深圳国际研究生院", "清华大学深圳研究生院"),
    )


def test_chat_v1_patent_falls_back_to_template_and_files_pipeline_issue(
    monkeypatch,
) -> None:
    fake_conn = _FakeConn()

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(
        chat_module,
        "_lookup_patents_by_applicant",
        lambda conn, *, company_name: [
            {
                "patent_id": "PAT-001",
                "patent_number": "CN202400001",
                "title_clean": "机器人控制系统",
                "applicants_raw": "优必选",
                "filing_date": "2024-01-10",
                "grant_date": None,
                "patent_type": "发明专利",
                "total_count": 1,
            }
        ],
    )
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda query, evidence_text, timeout=3.0: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="优必选有哪些专利"),
        response=Response(),
        conn=fake_conn,
    )

    assert response.answer_style == "template"
    assert response.query_type == "A_patent_by_applicant"
    assert "CN202400001" in response.answer_text
    assert len(fake_conn.pipeline_issues) == 1
    assert fake_conn.pipeline_issues[0] == {
        "professor_id": None,
        "institution": "UNKNOWN_INSTITUTION",
        "stage": "chat_synthesis",
        "severity": "low",
        "description": "LLM synthesis failed for A_patent_by_applicant: boom",
        "reported_by": "round_9_p1_v1_chat_synthesis",
    }


def test_chat_v1_dangling_marker_falls_back_for_ambiguous_professors(
    monkeypatch,
) -> None:
    fake_conn = _FakeConn()

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda conn, *, name, institutions: [
            {
                "professor_id": "PROF-A",
                "canonical_name": "王伟",
                "institution": "南方科技大学",
                "title": "教授",
            },
            {
                "professor_id": "PROF-B",
                "canonical_name": "王伟",
                "institution": "清华大学深圳国际研究生院",
                "title": "副教授",
            },
        ],
    )
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda query, evidence_text, timeout=3.0: "候选教授包括王伟[99]。",
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="介绍王伟"),
        response=Response(),
        conn=fake_conn,
    )

    assert response.answer_style == "template"
    assert response.query_type == "A_prof_profile_ambiguous"
    assert "请加上学校再问一次" in response.answer_text
    assert len(fake_conn.pipeline_issues) == 1
    # M4's citation validator strips out-of-range [99] upstream, so the downstream
    # check now reports "no citation markers found" instead of "dangling".
    assert (
        "no citation markers found"
        in fake_conn.pipeline_issues[0]["description"]
    )


def test_chat_v1_env_off_keeps_v0_prof_list_behavior_and_skips_llm(
    monkeypatch,
) -> None:
    fake_conn = _FakeConn()

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(
        chat_module,
        "_lookup_professors_by_topic",
        lambda conn, *, institutions, topic, limit=None: [
            {
                "professor_id": "PROF-101",
                "canonical_name": "李明",
                "institution": "南方科技大学",
                "matched_topics": ["力控", "机器人"],
                "total_count": 2,
            },
            {
                "professor_id": "PROF-102",
                "canonical_name": "张敏",
                "institution": "南方科技大学",
                "matched_topics": ["力控"],
                "total_count": 2,
            },
        ],
    )
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LLM should not run when CHAT_LLM_SYNTHESIS=off")
        ),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="南科大做力控的教授"),
        response=Response(),
        conn=fake_conn,
    )

    assert response.answer_style == "template"
    assert response.query_type == "A_prof_list_by_topic"
    assert response.citation_map == {}
    assert "共找到 2 位教授" in response.answer_text
    assert "李明" in response.answer_text
    assert fake_conn.pipeline_issues == []
