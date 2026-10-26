"""Coherence measurement: text selection, cosine, and batching."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "measure_professor_paper_coherence.py"
)
_spec = importlib.util.spec_from_file_location(
    "measure_professor_paper_coherence", _SCRIPT
)
assert _spec and _spec.loader
coherence = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = coherence
_spec.loader.exec_module(coherence)


def test_direction_text_prefers_directions_and_falls_back_to_summary() -> None:
    document = {
        "research_directions": [{"name": "机器人"}, {"name": "运动控制"}],
        "profile_summary": "一段简介",
    }
    assert coherence.direction_text(document) == "机器人；运动控制"
    assert (
        coherence.direction_text({"research_directions": [], "profile_summary": "简介"})
        == "简介"
    )


def test_cosine_bounds() -> None:
    assert coherence.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert coherence.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert coherence.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_measure_uses_mean_of_paper_similarities(monkeypatch) -> None:
    projection = {
        "p1": {
            "professor_id": "p1",
            "name": "王伟",
            "paper_count": 2,
            "top_papers": [{"title": "a"}, {"title": "b"}],
        }
    }
    documents = {
        "p1": {"research_directions": [{"name": "机器人"}], "profile_summary": ""}
    }

    # direction, paper a, paper b
    vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    monkeypatch.setattr(coherence, "embed", lambda texts, **_: vectors[: len(texts)])

    [row] = coherence.measure(
        projection=projection,
        documents=documents,
        names=["王伟"],
        top=5,
        endpoint="http://unused",
        key="k",
    )

    assert row["papers"] == 2
    assert row["coherence"] == 0.5
    assert row["has_directions"] is True


def test_measure_marks_unknown_names(monkeypatch) -> None:
    monkeypatch.setattr(coherence, "embed", lambda texts, **_: [[1.0]])
    [row] = coherence.measure(
        projection={},
        documents={},
        names=["不存在"],
        top=5,
        endpoint="http://unused",
        key="k",
    )
    assert row["error"] == "not in projection"
