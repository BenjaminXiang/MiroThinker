## Why

Professor structured fields are largely **missing** across schools: `education` and `academic_position` are **0% populated in 6 of 10 schools** (only SIGS extracts them well, 87/73%); `research_directions` is 40–99% (HIT-SZ 0%); `work_experience`/`award` ~13% globally. The cause is structural: completion today is **single-source (homepage section extraction)**, and that extractor only recognizes SIGS-like templates — so every other school's homepage fields go unextracted. **HIT(深圳) is 0% across ALL fields** — a total page-crawl/parse failure, not a field problem.

The user requirement: the designed structured fields must be **systematically completed**, not hand-fixed per-school-per-field (which would be ~37 seeds × 8 fields). This change introduces a **multi-source, template-agnostic completion pipeline** so field completion scales across all schools at once.

This change is **behavior-affecting** (changes how/whether professor fields get populated + persisted). The behavior contract is owned by the new capability `professor-profile-field-completion`.

## What Changes

- **NEW capability `professor-profile-field-completion`**: a 4-layer, per-field completion pipeline with a declared **multi-source priority chain** per field.
- **L1 — per-school homepage section extraction**: targeted fixes for high-value fields where LLM/external sources underperform (e.g., Chinese research overview, structured tables). Reserved; scope shrunk by L2/L3.
- **L2 — LLM structured-field extraction (template-agnostic, the systematic lever)**: when the section parser fails, an LLM extracts structured facts (`research_topic`, `education`, `academic_position`, `work_experience`, `award`, `contact`) from the homepage text. Reuses `professor-fact-extraction` (fact extractor) + archived `prof-fact-extraction-expansion`. One change covers all schools.
- **L3 — external enrichment backfill (template-agnostic)**: `research_directions` ← OpenAlex `concepts`/`x_concepts` (extend `openalex_metrics.py` beyond h-index); `education`/`work_experience` ← ORCID education/employment (where ORCID present).
- **L4 — total-failure crawl diagnosis + fix**: schools where the whole page is unextracted (HIT-SZ 0%) must be diagnosed (403/JS/URL structure/selector) and fixed before any field layer can help.
- **NEW field-completeness gate**: a per-school per-field fill-rate audit (`run_professor_field_completeness_audit.py`) with declared targets; completion writes the field AND **resolves** the matching `pipeline_issue` (closure, not file-only — addresses root cause A1).
- **Per-field source chain** is normative (see spec): each field declares its source priority; completion must attempt the chain before leaving a field empty.

## Capabilities

### New Capabilities
- `professor-profile-field-completion`: multi-source completion of professor structured fields (homepage section → LLM extraction → external enrichment), with a per-field source chain, a field-completeness gate, and a closure loop. Baselines the existing homepage-section extraction as L1.

### Modified Capabilities
<!-- none — `professor-profile-field-extraction-integrity` remains the extraction-correctness contract; this change adds the completion pipeline as a sibling capability (see source-links). -->

## Impact

- **Affected code**: `professor/homepage_crawler.py` + profile-section extractors (L1); fact-extraction/LLM field extractor (L2) — reuse `professor/fact_extraction*` / archived `prof-fact-extraction-expansion`; `professor/openalex_metrics.py` extended to author-profile fields + a new ORCID education/employment backfill (L3); a new crawl-diagnosis step for total-failure schools (L4); new `scripts/run_professor_field_completeness_audit.py` + a closure writer.
- **Storage**: `professor_fact` / `professor_profile_section` reused (no migration); new `pipeline_issue` rows at field-completion stages, resolved on write.
- **Evidence/provenance**: each externally-sourced (L3) or LLM-sourced (L2) field value carries its source + `run_id`; homepage-sourced (L1) carries page evidence. No unattributed writes.
- **Dependencies**: benefits from B1 provider hardening (OpenAlex rate-limits) and the W0b identity-gate precedent (evidence + reversibility discipline).
- **No public API change**; serialized formats unchanged; `_VALID_DOMAINS`/A–G untouched.

## Non-goals

- Does **not** change roster collection (Part 1.1 — done: 37 adapters, 100% homepage URL coverage).
- Does **not** fix paper extraction (Part 2.1 — separate per-seed work; see `2026-06-16-professor-paper-cleanup-seed-checklist.md`).
- Does **not** hand-write 37×8 field templates — L2/L3 are template-agnostic and carry the bulk.
- Does **not** lower field-completeness targets to make the gate pass; unfilled fields are reported as residual risk, not silently filed.
