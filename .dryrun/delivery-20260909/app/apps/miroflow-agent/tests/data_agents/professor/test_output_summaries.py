from __future__ import annotations

from types import SimpleNamespace

from src.data_agents.professor.output_summaries import (
    PaperSummaryInput,
    PatentSummaryInput,
    generate_professor_output_summaries,
    select_eligible_paper_summary_inputs,
)


class FakeLLMClient:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class RecordingConn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> FakeRows:
        self.calls.append((sql, params))
        return FakeRows(self.rows)


def _paper_input(
    paper_id: str = "PAPER-1",
    title: str = "Graph Learning for Medical Robotics",
) -> PaperSummaryInput:
    return PaperSummaryInput(
        paper_id=paper_id,
        title=title,
        year=2025,
        venue="TestConf",
        abstract_clean="A study about graph learning for robot control.",
        summary_zh="Graph learning summary.",
        authors_display="A. Author",
        citation_count=12,
        canonical_source="openalex",
        link_status="verified",
        match_reason="listed on official profile",
    )


def _patent_input(
    patent_id: str = "PAT-1",
    title: str = "Robot Force Control Method",
) -> PatentSummaryInput:
    return PatentSummaryInput(
        patent_id=patent_id,
        patent_number="CN202610000001A",
        title=title,
        patent_type="发明",
        status="published",
        abstract_clean="A patent about force control in collaborative robots.",
        technology_effect="Improves force control stability.",
        ipc_codes=("G06N",),
        summary_text="Force control patent summary.",
        link_status="verified",
        match_reason="listed on official profile",
    )


def test_generate_professor_output_summaries_skips_llm_without_outputs() -> None:
    llm = FakeLLMClient('{"paper_summary":"unused","patent_summary":"unused"}')

    result = generate_professor_output_summaries(
        professor_name="Prof Test",
        paper_inputs=(),
        patent_inputs=(),
        llm_client=llm,
        llm_model="test-model",
    )

    assert result.paper_summary is None
    assert result.patent_summary is None
    assert result.no_summary_reason == "no eligible papers or patents"
    assert llm.calls == []


def test_generate_professor_output_summaries_uses_mocked_llm_for_papers() -> None:
    llm = FakeLLMClient(
        '{"paper_summary":"Papers focus on graph learning for robotics.","patent_summary":null}'
    )

    result = generate_professor_output_summaries(
        professor_name="Prof Test",
        paper_inputs=(_paper_input(),),
        patent_inputs=(),
        llm_client=llm,
        llm_model="test-model",
        extra_body={"provider": "mock"},
    )

    assert result.paper_summary == "Papers focus on graph learning for robotics."
    assert result.patent_summary is None
    assert result.no_summary_reason is None
    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == "test-model"
    assert llm.calls[0]["extra_body"] == {"provider": "mock"}
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "Graph Learning for Medical Robotics" in prompt
    assert "PAPER-1" in prompt


def test_generate_professor_output_summaries_uses_mocked_llm_for_patents() -> None:
    llm = FakeLLMClient(
        '{"paper_summary":null,"patent_summary":"Patents focus on stable robot force control."}'
    )

    result = generate_professor_output_summaries(
        professor_name="Prof Test",
        paper_inputs=(),
        patent_inputs=(_patent_input(),),
        llm_client=llm,
        llm_model="test-model",
    )

    assert result.paper_summary is None
    assert result.patent_summary == "Patents focus on stable robot force control."
    assert len(llm.calls) == 1
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "Robot Force Control Method" in prompt
    assert "CN202610000001A" in prompt


def test_generate_professor_output_summaries_handles_mixed_outputs() -> None:
    llm = FakeLLMClient(
        """
        ```json
        {
          "paper_summary": "Papers cover graph learning.",
          "patent_summary": "Patents cover robot control."
        }
        ```
        """
    )

    result = generate_professor_output_summaries(
        professor_name="Prof Test",
        paper_inputs=(_paper_input(),),
        patent_inputs=(_patent_input(),),
        llm_client=llm,
        llm_model="test-model",
    )

    assert result.paper_summary == "Papers cover graph learning."
    assert result.patent_summary == "Patents cover robot control."
    assert len(llm.calls) == 1
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "Graph Learning for Medical Robotics" in prompt
    assert "Robot Force Control Method" in prompt


def test_select_eligible_paper_summary_inputs_resolves_aliases_and_deduplicates() -> None:
    conn = RecordingConn(
        [
            {
                "paper_id": "PAPER-CANON",
                "title_clean": "Improved Alzheimer's disease diagnosis",
                "year": 2018,
                "venue": "Neurocomputing",
                "abstract_clean": "Canonical abstract.",
                "summary_zh": "中文摘要。",
                "authors_display": "Ahmed Elazab et al.",
                "citation_count": 30,
                "canonical_source": "crossref",
                "link_status": "verified",
                "match_reason": "listed on official profile",
            }
        ]
    )

    inputs = select_eligible_paper_summary_inputs(conn, professor_id="PROF-AHMED")

    assert [item.paper_id for item in inputs] == ["PAPER-CANON"]
    sql = " ".join(conn.calls[0][0].split()).lower()
    assert "paper_merge_alias" in sql
    assert "coalesce(pma.canonical_paper_id, ppl.paper_id)" in sql
    assert "duplicate_rank = 1" in sql


def test_select_eligible_paper_summary_inputs_requires_ready_papers() -> None:
    conn = RecordingConn([])

    select_eligible_paper_summary_inputs(conn, professor_id="PROF-AHMED")

    sql = " ".join(conn.calls[0][0].split()).lower()
    assert "p.quality_status = 'ready'" in sql
