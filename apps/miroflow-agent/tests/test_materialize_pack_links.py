"""Pack link materialisation: maps, field rules, and top-paper selection."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_pack_links.py"
_spec = importlib.util.spec_from_file_location("materialize_pack_links", _SCRIPT)
assert _spec and _spec.loader
links = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = links
_spec.loader.exec_module(links)


def _paper(identifier: str, *, citations: int = 0, year: int = 2020) -> dict:
    return {
        "canonical_identity_id": identifier,
        "title": f"paper {identifier}",
        "year": year,
        "citation_count": citations,
    }


def test_build_maps_drops_unknown_endpoints() -> None:
    by_paper, by_professor, dropped = links.build_maps(
        [("p1", "a"), ("p1", "b"), ("p2", "missing"), ("ghost", "a")],
        professor_ids={"p1", "p2"},
        paper_ids={"a", "b"},
    )

    assert by_paper == {"a": ["p1"], "b": ["p1"]}
    assert by_professor == {"p1": ["a", "b"]}
    assert dropped == 2


def test_apply_links_sets_both_sides() -> None:
    professors = {"p1": {"canonical_identity_id": "p1"}}
    papers = {
        "a": _paper("a", citations=1, year=2020),
        "b": _paper("b", citations=50, year=2019),
        "c": _paper("c", citations=10, year=2021),
    }

    updated_papers, updated_professors, stats = links.apply_links(
        professors=professors,
        papers=papers,
        by_paper={"a": ["p1"], "b": ["p1"], "c": ["p1"]},
        by_professor={"p1": ["a", "b", "c"]},
    )

    assert sorted(updated_papers) == ["a", "b", "c"]
    assert updated_papers["a"]["professor_ids"] == ["p1"]
    professor = updated_professors["p1"]
    assert professor["paper_count"] == 3
    assert professor["paper_ids"] == ["a", "b", "c"]
    assert professor["top_papers"] == ["b", "c", "a"]  # by citations
    assert stats["professors_updated"] == 1


def test_existing_values_are_never_overwritten() -> None:
    professors = {"p1": {"canonical_identity_id": "p1", "paper_count": 2, "paper_ids": ["x"]}}
    papers = {"a": {"canonical_identity_id": "a", "professor_ids": ["other"]}}

    updated_papers, updated_professors, stats = links.apply_links(
        professors=professors,
        papers=papers,
        by_paper={"a": ["p1"]},
        by_professor={"p1": ["a"]},
    )

    # The paper keeps its source list; the professor keeps count and ids and only
    # gains the missing top_papers.
    assert updated_papers == {}
    assert updated_professors["p1"]["paper_count"] == 2
    assert updated_professors["p1"]["paper_ids"] == ["x"]
    assert updated_professors["p1"]["top_papers"] == ["a"]
    assert stats["papers_already_set"] == 1


def test_paper_ids_are_capped_but_count_is_true() -> None:
    professors = {"p1": {"canonical_identity_id": "p1"}}
    papers = {key: _paper(key) for key in "abcdef"}

    _, updated_professors, _ = links.apply_links(
        professors=professors,
        papers=papers,
        by_paper={key: ["p1"] for key in papers},
        by_professor={"p1": list(papers)},
        max_paper_ids=3,
    )

    assert len(updated_professors["p1"]["paper_ids"]) == 3
    assert updated_professors["p1"]["paper_count"] == 6


def test_hash_format_matches_the_builder() -> None:
    assert links.sha256_text("x") == (
        "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    )


def test_pack_count_is_preserved_while_links_are_filled() -> None:
    professors = {"p1": {"canonical_identity_id": "p1", "paper_count": 57}}
    papers = {"a": _paper("a", citations=3)}

    _, updated_professors, _ = links.apply_links(
        professors=professors,
        papers=papers,
        by_paper={"a": ["p1"]},
        by_professor={"p1": ["a"]},
    )

    professor = updated_professors["p1"]
    assert professor["paper_count"] == 57          # source value kept
    assert professor["paper_ids"] == ["a"]          # link filled
    assert professor["top_papers"] == ["a"]


def test_main_writes_links_and_recomputes_hashes(tmp_path: Path) -> None:
    import json
    import sqlite3

    database = tmp_path / "lookup.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "create table lookup_document (document_id text, canonical_object_id text, document_json text)"
    )

    def _insert(domain: str, canonical_id: str, content: dict) -> None:
        document = {
            "document_id": f"doc-{canonical_id}",
            "canonical_object_id": canonical_id,
            "domain": domain,
            "lookup_content": json.dumps(content),
            "lookup_content_sha256": "stale",
        }
        connection.execute(
            "insert into lookup_document values (?,?,?)",
            (f"doc-{canonical_id}", canonical_id, json.dumps(document)),
        )

    _insert("professor", "p1", {"canonical_identity_id": "p1", "name": "王伟"})
    _insert("paper", "a", {"canonical_identity_id": "a", "title": "A", "citation_count": 5})
    connection.commit()
    connection.close()

    edges = tmp_path / "edges.jsonl"
    edges.write_text('["p1", "a"]\n')

    assert links.main(["--pack", str(tmp_path), "--edges", str(edges)]) == 0

    connection = sqlite3.connect(database)
    rows = dict(
        (row[0], row[1])
        for row in connection.execute(
            "select canonical_object_id, document_json from lookup_document"
        )
    )
    connection.close()

    paper = json.loads(rows["a"])
    assert json.loads(paper["lookup_content"])["professor_ids"] == ["p1"]
    assert paper["lookup_content_sha256"] == links.sha256_text(paper["lookup_content"])

    professor = json.loads(json.loads(rows["p1"])["lookup_content"])
    assert professor["paper_ids"] == ["a"]
    assert professor["paper_count"] == 1
