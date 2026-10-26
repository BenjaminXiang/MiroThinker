"""Professor projection overlay: merge rules, flags, and claim rendering."""

from __future__ import annotations

import json
from pathlib import Path

from src.data_agents.canonical_v2 import professor_projection_overlay as overlay_module
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    _collapse_repetition,
    _semantic_text,
)
from src.data_agents.canonical_v2.knowledge_read import EvidenceItem


def _record(**overrides) -> dict:
    record = {
        "name": "王向荣",
        "institution": "香港中文大学（深圳）",
        "paper_count": 90,
        "coherence_top3": 0.41,
        "flags": [],
        "top_papers": [
            {"title": "Topological Magnonics", "year": 2021, "title_zh": None},
            {"title": "Domain Wall Propagation", "year": 2019, "title_zh": None},
            {"title": "Spin Wave Emission", "year": 2018, "title_zh": None},
            {"title": "Fourth Paper", "year": 2017, "title_zh": None},
        ],
    }
    record.update(overrides)
    return record


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def test_apply_merges_missing_fields() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay({"p1": _record()})

    merged = overlay.apply("p1", {"name": "王向荣"})

    assert merged["paper_count"] == 90
    assert len(merged["top_papers"]) == 4
    # The source payload is not mutated.
    assert "paper_count" not in {"name": "王向荣"}


def test_apply_never_overwrites_pack_values() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay({"p1": _record()})

    merged = overlay.apply("p1", {"paper_count": 3, "top_papers": [{"title": "x"}]})

    assert merged["paper_count"] == 3
    assert merged["top_papers"] == [{"title": "x"}]


def test_duplicate_name_records_are_ignored() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay(
        {"p1": _record(flags=["duplicate_name"])}
    )

    assert len(overlay) == 0
    assert "paper_count" not in overlay.apply("p1", {})


def test_unknown_professor_is_a_no_op() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay({"p1": _record()})

    assert overlay.apply("other", {"name": "某人"}) == {"name": "某人"}


def test_top_papers_text_prefers_chinese_title_and_limits_to_three() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay({})

    text = overlay.top_papers_text(
        {
            "top_papers": [
                {"title": "A", "title_zh": "甲", "year": 2021},
                {"title": "B", "year": 2020},
                {"title": "C", "year": 2019},
                {"title": "D", "year": 2018},
                {"title": "E"},
            ]
        }
    )

    assert text == "《甲》2021；《B》2020；《C》2019"


def test_top_papers_text_is_none_without_papers() -> None:
    overlay = overlay_module.ProfessorProjectionOverlay({})

    assert overlay.top_papers_text({}) is None
    assert overlay.top_papers_text({"top_papers": [{}]}) is None


def test_load_overlay_is_disabled_for_missing_or_invalid_files(tmp_path: Path) -> None:
    assert overlay_module.load_overlay(None) is None
    assert overlay_module.load_overlay(tmp_path / "missing.json") is None

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert overlay_module.load_overlay(broken) is None

    wrong_shape = tmp_path / "list.json"
    wrong_shape.write_text("[]")
    assert overlay_module.load_overlay(wrong_shape) is None


def test_active_overlay_reads_env_once(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path, {"p1": _record()})
    monkeypatch.setenv(overlay_module.ENV_VAR, str(path))
    overlay_module.reset_overlay_cache()

    first = overlay_module.active_overlay()
    second = overlay_module.active_overlay()

    assert first is not None and first is second
    monkeypatch.delenv(overlay_module.ENV_VAR)
    overlay_module.reset_overlay_cache()
    assert overlay_module.active_overlay() is None


def _evidence(snippet: dict, *, object_id: str = "p1") -> EvidenceItem:
    return EvidenceItem(
        evidence_id="evidence-1",
        object_id=object_id,
        domain="professor",
        lane="exact",
        source_nature="local",
        source_locator="lookup:professor",
        snippet=json.dumps(snippet, ensure_ascii=False),
        score=1.0,
    )


def test_semantic_text_adds_count_and_representative_papers(
    tmp_path: Path, monkeypatch
) -> None:
    path = _write(tmp_path, {"p1": _record()})
    monkeypatch.setenv(overlay_module.ENV_VAR, str(path))
    overlay_module.reset_overlay_cache()

    text = _semantic_text(
        _evidence(
            {
                "name": "王向荣",
                "institution": "香港中文大学（深圳）",
                "research_directions": [{"name": "凝聚态理论"}],
            }
        ),
        "王向荣",
    )

    assert "本地收录论文：90 篇" in text
    assert "代表作：《Topological Magnonics》2021" in text
    assert "研究方向：凝聚态理论" in text


def test_semantic_text_is_unchanged_without_overlay(monkeypatch) -> None:
    monkeypatch.delenv(overlay_module.ENV_VAR, raising=False)
    overlay_module.reset_overlay_cache()

    text = _semantic_text(_evidence({"name": "王向荣"}), "王向荣")

    assert "本地收录论文" not in text
    assert "代表作" not in text


def test_collapse_repetition_keeps_each_sentence_once() -> None:
    template = "该教授在深圳科创领域有持续贡献，研究成果具有重要学术价值。"

    collapsed = _collapse_repetition(f"{template}{template}{template}", limit=400)

    assert collapsed == template


def test_collapse_repetition_keeps_normal_text() -> None:
    text = "她研究机器人控制。近年转向人机交互。"

    assert _collapse_repetition(text, limit=400) == text


def test_collapse_repetition_truncates_after_dedupe() -> None:
    text = "第一句。" * 5 + "第二句。"

    collapsed = _collapse_repetition(text, limit=10)

    assert collapsed == "第一句。第二句。"[:10]


def test_semantic_text_dedupes_template_summary() -> None:
    template = "该教授在深圳科创领域有持续贡献，研究成果具有重要学术价值。"
    item = _evidence(
        {
            "name": "王伟",
            "profile_summary": template * 3 + "研究方向是机器人。",
        }
    )

    text = _semantic_text(item, "王伟")

    # The known padding sentence is dropped outright (template-cleanup slice),
    # so it never reaches the claim even once.
    assert text.count("该教授在深圳科创领域有持续贡献") == 0
    assert "研究方向是机器人" in text


def test_active_overlay_reloads_when_the_file_changes(tmp_path: Path, monkeypatch) -> None:
    import os as _os

    path = _write(tmp_path, {"p1": _record(paper_count=90)})
    monkeypatch.setenv(overlay_module.ENV_VAR, str(path))
    overlay_module.reset_overlay_cache()
    first = overlay_module.active_overlay()

    path.write_text(json.dumps({"p1": _record(paper_count=7)}, ensure_ascii=False))
    stat = path.stat()
    _os.utime(path, (stat.st_atime, stat.st_mtime + 5))

    second = overlay_module.active_overlay()

    assert second is not None and second is not first
    assert second.apply("p1", {})["paper_count"] == 7


def test_active_overlay_keeps_the_instance_while_the_file_is_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    path = _write(tmp_path, {"p1": _record()})
    monkeypatch.setenv(overlay_module.ENV_VAR, str(path))
    overlay_module.reset_overlay_cache()

    assert overlay_module.active_overlay() is overlay_module.active_overlay()
