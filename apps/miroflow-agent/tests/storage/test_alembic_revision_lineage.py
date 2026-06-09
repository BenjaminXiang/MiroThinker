from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = APP_ROOT / "alembic" / "versions"

EXPECTED_RECENT_CHAIN = {
    "V024": ("V023", "V024_extend_professor_paper_link_tier_evidence.py"),
    "V025": ("V024", "V025_add_professor_admin_action.py"),
    "V026": ("V025", "V026_allow_page_only_patent_number.py"),
    "V027": ("V026", "V027_repair_professor_paper_link_tier_constraint.py"),
    "V028": ("V027", "V028_extend_paper_canonical_source_page_flow.py"),
    "V029": ("V028", "V029_add_professor_output_summary_fields.py"),
    "V030": ("V029", "V030_add_professor_lifecycle_state.py"),
    "V031": ("V030", "V031_add_paper_full_text_raw_pdf_provenance.py"),
    "V032": ("V031", "V032_add_professor_patent_link_evidence_url.py"),
    "V033": ("V032", "V033_add_company_enrichment_product_tables.py"),
    "V034": ("V033", "V034_add_company_structured_business_fields.py"),
    "V035": ("V034", "V035_add_company_enrichment_batch_ops.py"),
    "V036": ("V035", "V036_add_company_team_member_structured_fields.py"),
    "V037": ("V036", "V037_add_company_evidence_source_tier.py"),
    "V038": ("V037", "V038_allow_company_signal_event_needs_review.py"),
    "V039": ("V038", "V039_add_company_upload_hardening_fields.py"),
    "V040": ("V039", "V040_allow_dblp_paper_canonical_source.py"),
}


def _load_revision(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_recent_alembic_revisions_are_linear_and_unique() -> None:
    seen: dict[str, Path] = {}

    for path in VERSIONS_DIR.glob("V*.py"):
        migration = _load_revision(path)
        revision = migration.revision
        assert revision not in seen, (
            f"Duplicate Alembic revision {revision}: {seen[revision]} and {path}"
        )
        seen[revision] = path

    for revision, (down_revision, filename) in EXPECTED_RECENT_CHAIN.items():
        path = VERSIONS_DIR / filename
        assert path.exists(), f"Missing migration file for {revision}: {filename}"
        migration = _load_revision(path)
        assert migration.revision == revision
        assert migration.down_revision == down_revision
