from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.data_agents.professor.summary_reinforcement import (
    PaperContext,
    generate_reinforced_profile_summary,
)


_SCRIPT_DIR = Path(__file__).parent.parent.parent / "scripts"


def _import_script(name: str):
    path = _SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unified_crawl_prompt_uses_canonical_chinese_summary_contract() -> None:
    unified = _import_script("run_unified_professor_crawl")

    prompt = unified._PROMPT_FIELDS

    assert "300-500" not in prompt
    assert "comprehensive bilingual bio" not in prompt
    assert "profile_summary" in prompt
    assert "200-300" in prompt
    assert "中文" in prompt


def test_web_enrich_prompt_uses_canonical_chinese_summary_contract() -> None:
    web_enrich = _import_script("run_professor_web_enrich")

    system_prompt = web_enrich._SYS_SYNTH

    assert "300-500" not in system_prompt
    assert "bilingual" not in system_prompt.lower()
    assert "English paragraph" not in system_prompt
    assert "200-300" in system_prompt
    assert "中文" in system_prompt


def test_unified_crawl_skips_invalid_profile_summary_write() -> None:
    unified = _import_script("run_unified_professor_crawl")
    invalid_summary = (
        "Ahmed Elazab is an Assistant Professor (助理教授) and Doctoral Supervisor "
        "(博士生导师) at Tsinghua SIGS. His research focuses on developing trustworthy "
        "artificial intelligence for medical image analysis, brain disease diagnosis "
        "and prognosis. He has published papers in international venues and works on "
        "multimodal neuroimaging, segmentation, registration, and clinical AI systems."
    )
    conn = _FakeConnection()

    facts_written, papers_written = unified._write_results(
        conn,
        "PROF-1",
        "PAGE-1",
        "11111111-1111-1111-1111-111111111111",
        {"fields": {"profile_summary": invalid_summary}, "papers": []},
    )

    assert facts_written == 0
    assert papers_written == 0
    assert not any(
        "UPDATE professor SET profile_summary" in sql for sql, _ in conn.statements
    )
    assert not any(
        params[1] == "homepage"
        for sql, params in conn.statements
        if "INSERT INTO professor_fact" in sql
    )


def test_llm_field_extract_profile_summary_uses_canonical_contract() -> None:
    llm_extract = _import_script("run_professor_llm_field_extract")

    prompt = llm_extract._PROMPT

    assert "bilingual bio" not in prompt
    assert "200-300" in prompt
    assert "中文" in prompt


def test_llm_field_extract_skips_invalid_profile_summary_fact() -> None:
    llm_extract = _import_script("run_professor_llm_field_extract")
    invalid_summary = (
        "Ahmed Elazab is an Assistant Professor (助理教授) and Doctoral Supervisor "
        "(博士生导师) at Tsinghua SIGS. His research focuses on trustworthy "
        "artificial intelligence for medical image analysis, brain disease "
        "diagnosis and prognosis, with emphasis on multimodal neuroimaging "
        "and clinical AI systems."
    )

    facts = llm_extract._facts_from({"profile_summary": invalid_summary})

    assert facts == []


def test_summary_reinforcement_prompt_uses_canonical_contract() -> None:
    from src.data_agents.professor import summary_reinforcement

    assert "200-500" not in summary_reinforcement._SYSTEM_PROMPT
    assert "200-300" in summary_reinforcement._SYSTEM_PROMPT
    assert "中文" in summary_reinforcement._SYSTEM_PROMPT


def test_summary_reinforcement_rejects_english_dominant_output() -> None:
    invalid_summary = (
        "Ahmed Elazab is an Assistant Professor (助理教授) and Doctoral Supervisor "
        "(博士生导师) at Tsinghua SIGS. His research focuses on trustworthy "
        "artificial intelligence for medical image analysis, brain disease "
        "diagnosis and prognosis, with emphasis on multimodal neuroimaging "
        "and clinical AI systems."
    )
    llm = _FakeLLM(invalid_summary)

    result = generate_reinforced_profile_summary(
        prof_name="Ahmed Elazab",
        institution="清华大学深圳国际研究生院",
        research_directions=["medical image analysis"],
        bio="",
        paper_contexts=[
            PaperContext(
                title="Medical Image Analysis",
                abstract="AI for medical image analysis.",
                intro=None,
                year=2024,
                venue="MICCAI",
            )
        ],
        llm_client=llm,
        llm_model="test",
    )

    assert result.summary == ""
    assert result.error is not None
    assert "profile_summary_english_dominant" in result.error


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self._cursor = _FakeCursor(self)
        self.commits = 0

    def cursor(self) -> "_FakeCursor":
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn
        self.rowcount = 0

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.conn.statements.append((sql, params))
        self.rowcount = 1


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )
            )
        )
