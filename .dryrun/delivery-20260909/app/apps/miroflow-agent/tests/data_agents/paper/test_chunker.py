"""RED-phase tests for M3 Unit 2 — paper chunker (pure function)."""

from __future__ import annotations

import pytest

from src.data_agents.paper.chunker import PaperChunk, chunk_paper


def test_paper_chunk_dataclass_smoke():
    c = PaperChunk(
        chunk_id="p1:title:0",
        paper_id="p1",
        chunk_type="title",
        segment_index=0,
        year=2023,
        venue="NeurIPS",
        content_text="Some title",
    )
    assert c.chunk_id == "p1:title:0"
    assert c.paper_id == "p1"


def test_paper_chunk_is_frozen():
    c = PaperChunk(
        chunk_id="p1:title:0",
        paper_id="p1",
        chunk_type="title",
        segment_index=0,
        year=None,
        venue=None,
        content_text="Some title",
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        c.content_text = "mutated"


# --- chunk_paper happy paths ---


def test_chunk_paper_title_only():
    chunks = chunk_paper(
        paper_id="p1",
        title="Deep Learning for Images",
        year=2023,
        venue="NeurIPS",
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "title"
    assert chunks[0].chunk_id == "p1:title:0"
    assert chunks[0].content_text == "Deep Learning for Images"
    assert chunks[0].year == 2023
    assert chunks[0].venue == "NeurIPS"


def test_chunk_paper_with_short_abstract():
    short_abstract = "We propose a new method. It works well."
    chunks = chunk_paper(
        paper_id="p1",
        title="Deep Learning for Images",
        year=2023,
        venue="NeurIPS",
        abstract=short_abstract,
    )
    assert len(chunks) == 2
    assert chunks[0].chunk_type == "title"
    assert chunks[1].chunk_type == "abstract"
    assert chunks[1].chunk_id == "p1:abstract:0"
    assert chunks[1].content_text == short_abstract


def test_chunk_paper_with_long_abstract_splits_into_segments():
    # Long abstract with paragraph breaks → multiple segments.
    long_abstract = (
        "We propose a novel method for image classification.\n\n"
        + "X" * 500
        + ".\n\n"
        + "The approach achieves state-of-the-art results on ImageNet.\n\n"
        + "Y" * 500
        + "."
    )
    chunks = chunk_paper(
        paper_id="p1",
        title="Title",
        year=2023,
        venue="NeurIPS",
        abstract=long_abstract,
    )
    abstract_chunks = [c for c in chunks if c.chunk_type == "abstract"]
    assert 1 < len(abstract_chunks) <= 3
    # Each abstract chunk ≤ 500 chars
    assert all(len(c.content_text) <= 500 for c in abstract_chunks)
    # segment_index is 0, 1, 2, ... consecutive
    assert [c.segment_index for c in abstract_chunks] == list(range(len(abstract_chunks)))


def test_chunk_paper_with_long_intro_splits_up_to_four_segments():
    long_intro = "\n\n".join(["Segment " + str(i) + "." + ("X" * 450) for i in range(6)])
    chunks = chunk_paper(
        paper_id="p1",
        title="Title",
        year=2023,
        venue="NeurIPS",
        abstract=None,
        intro=long_intro,
    )
    intro_chunks = [c for c in chunks if c.chunk_type.startswith("intro")]
    # Capped at 4
    assert 0 < len(intro_chunks) <= 4
    assert all(len(c.content_text) <= 500 for c in intro_chunks)


def test_chunk_paper_all_fields_yields_up_to_8_chunks():
    chunks = chunk_paper(
        paper_id="p1",
        title="Title",
        year=2023,
        venue="NeurIPS",
        abstract="A" * 1400,  # 3 segments
        intro="B" * 1800,  # 4 segments
    )
    assert len(chunks) <= 8
    types = {c.chunk_type for c in chunks}
    assert "title" in types
    assert "abstract" in types
    assert any(t.startswith("intro") for t in types)


# --- chunk_paper edge cases ---


def test_chunk_paper_no_title_returns_empty_list():
    """Paper with no title has nothing to embed → 0 chunks."""
    chunks = chunk_paper(
        paper_id="p1",
        title="",
        year=2023,
        venue=None,
    )
    assert chunks == []


def test_chunk_paper_none_abstract_and_intro_yields_only_title():
    chunks = chunk_paper(
        paper_id="p1",
        title="T",
        year=2023,
        venue=None,
        abstract=None,
        intro=None,
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "title"


def test_chunk_paper_intro_without_abstract():
    chunks = chunk_paper(
        paper_id="p1",
        title="Title",
        year=2023,
        venue=None,
        abstract=None,
        intro="Some intro paragraph.",
    )
    types = [c.chunk_type for c in chunks]
    assert "title" in types
    assert any(t.startswith("intro") for t in types)
    assert "abstract" not in types


def test_chunk_paper_abstract_without_intro():
    chunks = chunk_paper(
        paper_id="p1",
        title="Title",
        year=2023,
        venue=None,
        abstract="An abstract.",
        intro=None,
    )
    types = [c.chunk_type for c in chunks]
    assert "title" in types
    assert "abstract" in types
    assert not any(t.startswith("intro") for t in types)


def test_chunk_id_is_deterministic_across_calls():
    c1 = chunk_paper(paper_id="p1", title="Same title", year=2023, venue=None)
    c2 = chunk_paper(paper_id="p1", title="Same title", year=2023, venue=None)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]


def test_chunk_id_disjoint_across_different_paper_ids():
    c1 = chunk_paper(paper_id="p1", title="T", year=2023, venue=None)
    c2 = chunk_paper(paper_id="p2", title="T", year=2023, venue=None)
    ids1 = {c.chunk_id for c in c1}
    ids2 = {c.chunk_id for c in c2}
    assert ids1.isdisjoint(ids2)
