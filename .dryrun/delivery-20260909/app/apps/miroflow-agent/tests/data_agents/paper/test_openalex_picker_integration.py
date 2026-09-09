"""Integration: when `author_picker` is supplied, it takes precedence over
the rule-based disambiguator even if the LLM picks the rule's non-winner."""

from __future__ import annotations

from dataclasses import dataclass

from src.data_agents.paper.openalex import (
    discover_professor_paper_candidates_from_openalex,
)


@dataclass
class _FakePickerDecision:
    accepted_author_id: str | None
    confidence: float = 0.9
    reasoning: str = ""
    considered_author_ids: list[str] | None = None
    error: str | None = None


def test_llm_picker_selects_correct_author_when_rule_would_pick_wrong_one():
    """Two same-name candidates: rule picks high-h-index one, but that's a
    different person. LLM picker flags the lower-h-index CUHK Shenzhen author.
    """

    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A-WRONG",
                        "display_name": "Jianwei Huang",
                        "works_count": 500,
                        "cited_by_count": 50000,
                        "summary_stats": {"h_index": 80},
                        "last_known_institutions": [
                            {"display_name": "Shanghai Jiao Tong University"}
                        ],
                        "x_concepts": [{"display_name": "Medicine"}],
                    },
                    {
                        "id": "https://openalex.org/A-RIGHT",
                        "display_name": "Jianwei Huang",
                        "works_count": 200,
                        "cited_by_count": 30000,
                        "summary_stats": {"h_index": 60},
                        "last_known_institutions": [
                            {
                                "display_name": "The Chinese University of Hong Kong, Shenzhen"
                            }
                        ],
                        "x_concepts": [
                            {"display_name": "Wireless Networks"},
                            {"display_name": "Game Theory"},
                        ],
                    },
                ]
            }
        if url.endswith("/works"):
            # Must be querying the LLM-selected author, not the rule winner.
            assert params["filter"] == (
                "authorships.author.id:https://openalex.org/A-RIGHT"
            )
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Pricing Mobile Data Plans — A Game-Theoretic Study",
                        "publication_year": 2022,
                        "publication_date": "2022-05-01",
                        "cited_by_count": 40,
                        "primary_location": {},
                        "authorships": [
                            {"author": {"display_name": "Jianwei Huang"}},
                            {"author": {"display_name": "Coauthor A"}},
                        ],
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    captured_candidates: list[list] = []

    def picker(*, target_name, target_institution, target_directions, candidates):
        # Snapshot what the picker saw for assertion.
        captured_candidates.append(list(candidates))
        by_id = {c.author_id: c for c in candidates}
        return _FakePickerDecision(
            accepted_author_id="https://openalex.org/A-RIGHT",
            considered_author_ids=list(by_id.keys()),
        )

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-TEST",
        professor_name="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_id=None,
        request_json=fake_request_json,
        max_papers=5,
        author_picker=picker,
        target_research_directions=["无线通信", "博弈论"],
    )

    assert result.author_id == "https://openalex.org/A-RIGHT"
    assert result.papers and "Game-Theoretic" in result.papers[0].title
    # Picker was called once and saw both candidates.
    assert len(captured_candidates) == 1
    assert {c.author_id for c in captured_candidates[0]} == {
        "https://openalex.org/A-WRONG",
        "https://openalex.org/A-RIGHT",
    }


def test_llm_picker_none_decision_drops_author_rather_than_falling_back():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A-A",
                        "display_name": "Jianwei Huang",
                        "works_count": 500,
                        "cited_by_count": 50000,
                        "summary_stats": {"h_index": 80},
                        "last_known_institutions": [
                            {"display_name": "Shanghai Jiao Tong University"}
                        ],
                    },
                    {
                        "id": "https://openalex.org/A-B",
                        "display_name": "Jianwei Huang",
                        "works_count": 200,
                        "cited_by_count": 30000,
                        "summary_stats": {"h_index": 60},
                        "last_known_institutions": [
                            {"display_name": "Peking University"}
                        ],
                    },
                ]
            }
        raise AssertionError("/works should not be called when no author picked")

    def picker(*, target_name, target_institution, target_directions, candidates):
        return _FakePickerDecision(accepted_author_id=None)

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-TEST",
        professor_name="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_id=None,
        request_json=fake_request_json,
        max_papers=5,
        author_picker=picker,
    )

    assert result.author_id is None
    assert result.papers == []


def test_llm_picker_skipped_when_only_one_candidate_matches():
    """Single unambiguous candidate → old rule path handles it; picker not invoked."""

    picker_calls: list[int] = []

    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A-ONLY",
                        "display_name": "Jianwei Huang",
                        "works_count": 200,
                        "cited_by_count": 30000,
                        "summary_stats": {"h_index": 60},
                    }
                ]
            }
        return {"results": []}

    def picker(*, target_name, target_institution, target_directions, candidates):
        picker_calls.append(1)
        return _FakePickerDecision(accepted_author_id="SHOULD_NOT_BE_USED")

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-TEST",
        professor_name="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_id=None,
        request_json=fake_request_json,
        max_papers=5,
        author_picker=picker,
    )

    assert picker_calls == []
    assert result.author_id == "https://openalex.org/A-ONLY"
