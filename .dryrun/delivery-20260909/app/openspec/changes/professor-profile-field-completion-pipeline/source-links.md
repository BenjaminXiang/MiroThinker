# Source Links — professor-profile-field-completion-pipeline

> Per CLAUDE.md §14.3. Legacy docs/code consulted and what was extracted into the new `professor-profile-field-completion` capability.

## Evidence base (2026-06-16 field-completeness audit)
- **Per-school × per-field fill-rate query** (run against `miroflow_real`): `education`/`academic_position` 0% in 6/10 schools (only SIGS 87/73%); `research_directions` 40–99% (HIT-SZ 0%); `work_experience`/`award` ~13% globally; HIT(Shenzhen) 0% across ALL fields. → motivates the multi-source, template-agnostic pipeline.
- `docs/plans/2026-06-16-professor-paper-cleanup-gap-analysis.md` — Part 1.2 profile-quality gaps (short profile_summary 441, missing research_overview_zh 2510); this change generalizes to all structured fields.
- `docs/plans/2026-06-16-professor-paper-cleanup-seed-checklist.md` — per-seed paper-extraction checklist (separate concern; referenced for non-overlap).

## Code extracted into the design
- `professor/homepage_crawler.py` + `professor/profile_sections.py` — the homepage section extractor (L1); only recognizes SIGS-like templates (root cause of broad field gaps).
- `professor/openalex_metrics.py:39` — already calls OpenLex authors for h_index; L3 extends it to `concepts`/`x_concepts`.
- ORCID backfill (existing paper-side infra) — L3 extends to education/employment.
- `professor-fact-extraction` capability + archived `prof-fact-extraction-expansion` — L2 LLM fact extractor reused.
- `openspec/specs/professor-profile-field-extraction-integrity/spec.md` — sibling extraction-correctness contract (not modified; this adds completion).

## What was NOT migrated
- Roster/adapter layer (`professor-seed-management`, `roster.py`) — done, out of scope.
- Paper extraction (`paper-homepage-enrichment-completion`, the per-seed checklist) — separate.
