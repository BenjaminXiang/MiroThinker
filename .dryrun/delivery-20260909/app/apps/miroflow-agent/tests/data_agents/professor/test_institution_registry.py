from __future__ import annotations

from src.data_agents.professor.institution_registry import (
    get_institution_registry_entry,
    resolve_openalex_institution_id,
)


def test_resolve_openalex_institution_id_supports_canonical_name_and_aliases() -> None:
    assert resolve_openalex_institution_id("南方科技大学") == "I3045169105"
    assert resolve_openalex_institution_id("Southern University of Science and Technology") == "I3045169105"
    assert resolve_openalex_institution_id("SUSTech") == "I3045169105"


def test_resolve_openalex_institution_id_supports_verified_shenzhen_school_mappings() -> None:
    assert resolve_openalex_institution_id("清华大学深圳国际研究生院") == "I4405263052"
    assert resolve_openalex_institution_id("北京大学深圳研究生院") == "I20231570"
    assert resolve_openalex_institution_id("深圳大学") == "I180726961"
    assert resolve_openalex_institution_id("深圳理工大学") == "I4405255904"
    assert resolve_openalex_institution_id("Shenzhen University of Advanced Technology") == "I4405255904"
    assert resolve_openalex_institution_id("哈尔滨工业大学（深圳）") == "I204983213"
    assert resolve_openalex_institution_id("香港中文大学（深圳）") == "I4210116924"
    assert resolve_openalex_institution_id("深圳技术大学") == "I4210152380"


def test_get_institution_registry_entry_keeps_shared_parent_note() -> None:
    entry = get_institution_registry_entry("中山大学（深圳）")

    assert entry is not None
    assert entry.openalex_id
    assert entry.notes is not None
    assert "parent" in entry.notes.lower() or "母校" in entry.notes


def test_resolve_openalex_institution_id_returns_none_for_unknown_school() -> None:
    assert resolve_openalex_institution_id("不存在的大学") is None
