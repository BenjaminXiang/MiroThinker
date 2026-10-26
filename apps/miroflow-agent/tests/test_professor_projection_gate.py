"""Professor projection gate: names, emails, and edge aggregation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_professor_paper_projection.py"
)
_spec = importlib.util.spec_from_file_location(
    "build_professor_paper_projection", _SCRIPT
)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = builder
_spec.loader.exec_module(builder)


def _professor(identifier: str, name: str, **overrides) -> dict:
    record = {
        "canonical_identity_id": identifier,
        "name": name,
        "institution": "测试大学",
        "homepage": "https://example.edu/~x",
        "email": "x@example.edu",
        "research_directions": [{"name": "机器人"}],
        "profile_summary": "研究方向是机器人。",
        "paper_count": None,
    }
    record.update(overrides)
    return record


def _paper(identifier: str, *, citations: int = 0, year: int = 2020) -> dict:
    return {
        "canonical_identity_id": identifier,
        "title": f"paper {identifier}",
        "year": year,
        "citation_count": citations,
        "doi": None,
        "title_zh": None,
    }


def test_page_chrome_and_generic_titles_are_not_names() -> None:
    for name in ("面包屑", "教授", "院士", "首页", "更多", "登录"):
        assert not builder.is_plausible_name(name), name
    assert builder.is_plausible_name("王伟")
    assert builder.is_plausible_name("欧阳娜娜")
    assert builder.is_plausible_name("Ming-Hu Pan")
    assert not builder.is_plausible_name("王")
    assert not builder.is_plausible_name("欧阳娜娜娜")
    assert not builder.is_plausible_name("")


def test_email_check_rejects_page_label_concatenation() -> None:
    assert builder.is_valid_email("jun.zhu@cuhk.edu.cn")
    assert builder.is_valid_email("a@b.io")
    assert not builder.is_valid_email(
        "emailjun.zhu@cuhk.edu.cnofficeaddressphoneteachingareaotherbiography"
    )
    assert not builder.is_valid_email("no-at-sign")
    assert not builder.is_valid_email("a@b")
    assert not builder.is_valid_email("a@b.toolongtld")
    assert not builder.is_valid_email("a b@c.cn")
    assert not builder.is_valid_email(None)


def test_gate_drops_corrupted_email_but_keeps_the_person() -> None:
    verdict = builder.gate_professor(
        _professor("p1", "朱军", email="emailjun.zhu@cuhk.edu.cnofficeaddressphone")
    )

    assert verdict["admitted"] is True
    assert verdict["email"] is None
    assert "email_dropped" in verdict["reasons"]


def test_gate_rejects_implausible_name_and_bad_homepage() -> None:
    assert builder.gate_professor(_professor("p1", "面包屑"))["admitted"] is False
    assert (
        builder.gate_professor(_professor("p1", "王伟", homepage="cuhk.edu.cn"))[
            "admitted"
        ]
        is False
    )


def test_projection_counts_edges_and_orders_top_papers() -> None:
    professors = {"p1": _professor("p1", "王伟")}
    papers = {
        "a": _paper("a", citations=5, year=2019),
        "b": _paper("b", citations=50, year=2021),
        "c": _paper("c", citations=1, year=2022),
    }
    edges = [("p1", "a"), ("p1", "b"), ("p1", "c")]

    projection, report = builder.build_projection(professors, papers, edges)

    row = projection["p1"]
    assert row["paper_count"] == 3
    assert [paper["id"] for paper in row["top_papers"]] == ["b", "a", "c"]
    assert report["population"]["projected_professors"] == 1
    assert report["population"]["professors_gaining_paper_count"] == 1


def test_projection_drops_unknown_papers_and_unknown_professors() -> None:
    professors = {"p1": _professor("p1", "王伟")}
    papers = {"a": _paper("a")}

    projection, report = builder.build_projection(
        professors, papers, [("p1", "a"), ("p1", "missing"), ("p9", "a")]
    )

    assert projection["p1"]["paper_count"] == 1
    assert report["population"]["edges_without_paper"] == 1
    assert report["population"]["rejected_by_reason"] == {"professor_not_in_pack": 1}


def test_junk_professor_is_rejected_not_projected() -> None:
    professors = {
        "p1": _professor("p1", "面包屑"),
        "p2": _professor("p2", "王伟"),
    }
    papers = {"a": _paper("a")}

    projection, report = builder.build_projection(
        professors, papers, [("p1", "a"), ("p2", "a")]
    )

    assert "p1" not in projection
    assert report["population"]["rejected_by_reason"] == {"implausible_name": 1}


def test_duplicate_names_and_high_counts_are_flagged_not_dropped() -> None:
    professors = {
        "p1": _professor("p1", "王伟"),
        "p2": _professor("p2", "王伟"),
    }
    papers = {f"x{i}": _paper(f"x{i}") for i in range(builder.HIGH_PAPER_COUNT + 1)}
    edges = [("p1", identifier) for identifier in papers] + [("p2", "x0")]

    projection, _ = builder.build_projection(professors, papers, edges)

    assert "high_paper_count" in projection["p1"]["flags"]
    assert "duplicate_name" in projection["p1"]["flags"]
    assert "duplicate_name" in projection["p2"]["flags"]
    assert len(projection["p1"]["paper_ids"]) == builder.MAX_PAPER_IDS


def test_template_summary_and_missing_directions_are_flagged() -> None:
    template = (
        "王伟现任测试大学教授。该教授在深圳科创领域有持续贡献，研究成果具有重要学术价值。"
        * 2
    )
    professors = {
        "p1": _professor("p1", "王伟", profile_summary=template, research_directions=[])
    }
    papers = {"a": _paper("a")}

    projection, _ = builder.build_projection(professors, papers, [("p1", "a")])

    assert "template_summary" in projection["p1"]["flags"]
    assert "no_directions" in projection["p1"]["flags"]


def test_low_confidence_edges_are_flagged() -> None:
    professors = {"p1": _professor("p1", "王伟"), "p2": _professor("p2", "李静")}
    papers = {"a": _paper("a")}

    projection, report = builder.build_projection(
        professors,
        papers,
        [("p1", "a", 0.55, "author-name-match"), ("p2", "a", 0.95, "homepage-link")],
    )

    assert "low_confidence_edge" in projection["p1"]["flags"]
    assert "low_confidence_edge" not in projection["p2"]["flags"]
    assert projection["p1"]["confidence"]["min"] == 0.55
    assert report["confidence"]["below_threshold"] == 1


def test_two_tuple_edges_stay_supported() -> None:
    professors = {"p1": _professor("p1", "王伟")}
    papers = {"a": _paper("a")}

    projection, report = builder.build_projection(professors, papers, [("p1", "a")])

    assert projection["p1"]["paper_count"] == 1
    assert projection["p1"]["confidence"]["min"] is None
    assert report["confidence"]["edges_with_score"] == 0
