from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_DISCOVERY_SYMBOLS = (
    "discover_professor_paper_candidates_from_hybrid_sources",
    "discover_professor_paper_candidates_from_crossref",
    "discover_professor_paper_candidates_from_openalex",
    "discover_professor_paper_candidates_from_orcid",
    "discover_professor_paper_candidates_from_google_scholar_profile",
    "discover_professor_paper_candidates_from_cv_pdf",
    "discover_professor_paper_candidates(",
)

ALLOWED_COMPATIBILITY_MODULES = {
    Path("src/data_agents/paper/hybrid.py"),
    Path("src/data_agents/paper/crossref.py"),
    Path("src/data_agents/paper/openalex.py"),
    Path("src/data_agents/paper/orcid.py"),
    Path("src/data_agents/paper/google_scholar_profile.py"),
    Path("src/data_agents/paper/cv_pdf.py"),
    Path("src/data_agents/paper/semantic_scholar.py"),
}

PRODUCTION_ROOTS = (
    Path("src"),
    Path("scripts"),
)


def test_retired_paper_discovery_symbols_are_not_used_by_production_callers() -> None:
    offenders: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in sorted((APP_ROOT / root).rglob("*.py")):
            relative = path.relative_to(APP_ROOT)
            if relative in ALLOWED_COMPATIBILITY_MODULES:
                continue
            text = path.read_text(encoding="utf-8")
            for symbol in FORBIDDEN_DISCOVERY_SYMBOLS:
                if symbol in text:
                    offenders.append(f"{relative}: {symbol}")

    assert offenders == []
