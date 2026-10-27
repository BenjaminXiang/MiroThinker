"""Enrichment planning: thin detection, ranking, SQL shape."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plan_pack_enrichment.py"
_spec = importlib.util.spec_from_file_location("plan_pack_enrichment", _SCRIPT)
assert _spec and _spec.loader
planner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = planner
_spec.loader.exec_module(planner)

PAD = "该教授在深圳科创领域有持续贡献。"


def _record(
    name: str, *, institution: str = "深圳大学", summary: str = "", homepage: str = ""
) -> dict:
    return {
        "canonical_identity_id": f"professor-c-{name}",
        "name": name,
        "institution": institution,
        "profile_summary": summary,
        "homepage": homepage,
    }


def test_thin_detection() -> None:
    assert planner.is_thin("")
    assert planner.is_thin("短简介。")
    assert planner.is_thin(f"某教授。{PAD}" * 3)
    assert not planner.is_thin("认真写的简介。" * 20)


def test_ranking_prefers_homepage_then_institution() -> None:
    records = [
        _record("乙", institution="其他大学", homepage=""),
        _record("甲", institution="深圳大学", homepage="https://a.edu"),
        _record("丙", institution="深圳大学", homepage=""),
    ]

    selected = planner.select_thin(records, limit=3)

    assert [record["name"] for record in selected] == ["甲", "丙", "乙"]


def test_sql_text_escapes_quotes() -> None:
    assert planner.sql_text("O'Brien") == "'O''Brien'"
    assert planner.sql_text(None) == "NULL"


def test_render_sql_is_idempotent_and_complete() -> None:
    record = _record("王伟", summary="", homepage="https://example.edu/~wang")

    sql = planner.render_sql([record])

    assert "ON CONFLICT (url) DO NOTHING" in sql
    assert "url_host" not in sql  # generated column
    assert "ON CONFLICT (professor_id) DO NOTHING" in sql
    assert "professor_affiliation" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert planner.page_uuid("https://example.edu/~wang") in sql


def test_record_without_homepage_uses_null_page() -> None:
    sql = planner.render_sql([_record("李静")])

    assert "INSERT INTO source_page" not in sql
    assert ", NULL, now(), now())" in sql
