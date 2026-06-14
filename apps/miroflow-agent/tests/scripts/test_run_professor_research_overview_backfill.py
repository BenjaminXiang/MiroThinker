from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_professor_research_overview_backfill.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_research_overview_backfill",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Cursor:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "SELECT" in sql:
            return _Cursor(rows=self.rows)
        return _Cursor(row={"section_id": "SECTION-1"})


def test_dry_run_translates_ahmed_override_without_writing() -> None:
    cli = _import_cli()
    conn = _Conn(
        [
            {
                "professor_id": "PROF-823D4761D493",
                "canonical_name": "Ahmed Elazab",
                "profile_raw_text": (
                    "Research Overview: My research focuses on developing "
                    "trustworthy artificial intelligence for medical image "
                    "analysis, with a special emphasis on brain disease "
                    "diagnosis and prognosis. Publications: ..."
                ),
                "primary_official_profile_page_id": "PAGE-1",
                "run_id": "11111111-1111-1111-1111-111111111111",
            }
        ]
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn=conn,
        professor_ids=["PROF-823D4761D493"],
        translation_overrides={
            "PROF-823D4761D493": "我的研究聚焦于医学影像分析中的可信人工智能，重点关注脑疾病诊断与预后。"
        },
        write=False,
        output=output,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["dry_run"] is True
    assert payload["processed"] == 1
    assert payload["section_ready"] == 1
    assert payload["translated"] == 1
    assert payload["written"] == 0
    assert payload["rows"][0]["professor_id"] == "PROF-823D4761D493"
    assert payload["rows"][0]["status"] == "section_ready"
    assert payload["rows"][0]["generation_method"] == "llm_translation"
    assert payload["rows"][0]["source_text_hash"]
    assert len(conn.calls) == 1


def test_write_mode_persists_ready_section() -> None:
    cli = _import_cli()
    conn = _Conn(
        [
            {
                "professor_id": "PROF-ZH",
                "canonical_name": "中文教授",
                "profile_raw_text": "研究方向：可信人工智能医学影像分析。教育经历：博士。",
                "primary_official_profile_page_id": None,
                "run_id": None,
            }
        ]
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn=conn,
        professor_ids=["PROF-ZH"],
        translation_overrides={},
        write=True,
        output=output,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["dry_run"] is False
    assert payload["written"] == 1
    assert payload["rows"][0]["section_id"] == "SECTION-1"
    assert len(conn.calls) == 2
