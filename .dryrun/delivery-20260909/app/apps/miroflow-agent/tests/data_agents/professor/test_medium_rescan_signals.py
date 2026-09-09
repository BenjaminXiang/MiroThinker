import pytest

from src.data_agents.professor.medium_rescan_signals import (
    ProfessorCorpusProfile,
    compute_signals,
)


def _profile(
    *,
    coauthor_tokens: list[str] = None,
    venues: list[str] = None,
    year_min: int | None = 2015,
    year_max: int | None = 2024,
) -> ProfessorCorpusProfile:
    return ProfessorCorpusProfile(
        professor_id="PROF-TEST",
        coauthor_tokens=frozenset(coauthor_tokens or []),
        venues=frozenset(venues or []),
        year_min=year_min,
        year_max=year_max,
    )


def test_strong_coauthor_keeps_regardless_of_venue_year():
    """coauthor >= 0.4 is strong enough → keep even if venue/year are zero."""
    sigs = compute_signals(
        paper_authors_display="Alice Smith, Bob Jones",
        paper_venue="Random Venue",
        paper_year=1990,  # way out of range
        profile=_profile(
            coauthor_tokens=["alice", "alice smith", "bob", "bob jones"],
            venues=["Nature Communications"],
            year_min=2015,
            year_max=2024,
        ),
        prof_name_tokens=frozenset({"target", "prof"}),
    )
    assert sigs.coauthor_overlap >= 0.4
    assert sigs.venue_alignment == 0.0
    assert sigs.year_plausibility == 0.0
    assert sigs.verdict == "keep"


def test_all_zero_signals_demote():
    """No coauthor overlap, unknown venue, year out of range → demote."""
    sigs = compute_signals(
        paper_authors_display="Unknown Author, Stranger Person",
        paper_venue="Random Journal",
        paper_year=1995,
        profile=_profile(
            coauthor_tokens=["alice smith", "bob jones"],
            venues=["Nature Communications"],
        ),
        prof_name_tokens=frozenset({"target", "prof"}),
    )
    assert sigs.coauthor_overlap == 0.0
    assert sigs.venue_alignment == 0.0
    assert sigs.year_plausibility == 0.0
    assert sigs.verdict == "demote"


def test_any_positive_signal_goes_to_llm():
    """Even one non-zero signal short of coauthor>=0.4 → LLM re-verify."""
    # Venue match only
    sigs = compute_signals(
        paper_authors_display="Unknown A",
        paper_venue="Nature Communications",
        paper_year=1990,
        profile=_profile(
            coauthor_tokens=["alice"], venues=["Nature Communications"]
        ),
        prof_name_tokens=frozenset({"target"}),
    )
    assert sigs.verdict == "llm_needed"
    # Year match only
    sigs = compute_signals(
        paper_authors_display="Unknown A",
        paper_venue="Unknown Venue",
        paper_year=2020,
        profile=_profile(
            coauthor_tokens=["alice"], venues=["Nature Communications"],
            year_min=2015, year_max=2024,
        ),
        prof_name_tokens=frozenset({"target"}),
    )
    assert sigs.verdict == "llm_needed"


def test_coauthor_overlap_uses_name_sub_tokens():
    """'Shu-Tao Xia' should hit corpus token 'xia' via sub-token split."""
    sigs = compute_signals(
        paper_authors_display="Alice Wang, Shu-Tao Xia",
        paper_venue=None,
        paper_year=None,
        profile=_profile(coauthor_tokens=["xia", "alice wang"]),
        prof_name_tokens=frozenset({"target", "prof"}),
    )
    # paper tokens include 'xia' (sub-token), 'alice wang' (full), 'alice', 'wang', 'shu-tao'
    # corpus hits: xia, alice wang → some overlap
    assert sigs.coauthor_overlap > 0.0


def test_prof_own_name_stripped_from_overlap():
    """A paper where only the target prof's name matches must NOT score coauthor_overlap."""
    sigs = compute_signals(
        paper_authors_display="张三",
        paper_venue=None,
        paper_year=None,
        profile=_profile(coauthor_tokens=["张三", "lisa wong"]),
        prof_name_tokens=frozenset({"张三"}),
    )
    # paper tokens after strip = empty
    assert sigs.coauthor_overlap == 0.0


def test_year_plausibility_within_tolerance():
    sigs = compute_signals(
        paper_authors_display="",
        paper_venue=None,
        paper_year=2010,  # profile range 2015-2024, tolerance ±5 → [2010, 2029]
        profile=_profile(year_min=2015, year_max=2024),
        prof_name_tokens=frozenset(),
    )
    assert sigs.year_plausibility == 1.0


def test_year_plausibility_outside_tolerance():
    sigs = compute_signals(
        paper_authors_display="",
        paper_venue=None,
        paper_year=2000,  # 15 years before profile range start → out
        profile=_profile(year_min=2015, year_max=2024),
        prof_name_tokens=frozenset(),
    )
    assert sigs.year_plausibility == 0.0


def test_missing_year_scores_zero():
    sigs = compute_signals(
        paper_authors_display="",
        paper_venue=None,
        paper_year=None,
        profile=_profile(year_min=2015, year_max=2024),
        prof_name_tokens=frozenset(),
    )
    assert sigs.year_plausibility == 0.0


def test_empty_author_string_does_not_crash():
    sigs = compute_signals(
        paper_authors_display=None,
        paper_venue=None,
        paper_year=None,
        profile=_profile(),
        prof_name_tokens=frozenset(),
    )
    assert sigs.composite == 0.0
    assert sigs.verdict == "demote"
