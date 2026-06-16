## Context

Professor structured fields are largely missing (2026-06-16 field-completeness audit): `education`/`academic_position` are **0% in 6 of 10 schools** (only SIGS extracts them); `research_directions` 40–99% (HIT-SZ 0%); `work_experience`/`award` ~13% globally. Root cause: completion is single-source (homepage section extraction), and the section extractor (`homepage_crawler.py` + `profile_sections.py`) only recognizes SIGS-like templates. HIT-Shenzhen is a total page-crawl/parse failure (0% across all fields incl. contact). The user requires a **systematic** (not per-school-per-field) completion.

Existing assets to reuse: `professor-fact-extraction` (fact extractor) + archived `prof-fact-extraction-expansion` (LLM fact extraction); `professor/openalex_metrics.py` (already calls OpenAlex authors for h-index — extend to `concepts`/`x_concepts`); ORCID backfill scripts (used elsewhere for papers — extend to education/employment); `professor-profile-field-extraction-integrity` spec (extraction-correctness contract — sibling). The W0b change established the evidence + reversibility + closure discipline this change reuses.

Constraints (CLAUDE.md §7): evidence + `run_id` traceability; no unattributed writes; no weakening of the `professor-profile-field-extraction-integrity` contract; preserve V001–V042 history (reuse `professor_fact`/`professor_profile_section`, no migration).

## Goals / Non-Goals

**Goals:**
- Fill missing structured fields via a template-agnostic, multi-source pipeline so one change improves all 10 schools (not 37×8 hand-fixes).
- Make L2 (LLM extraction) + L3 (OpenAlex/ORCID enrichment) carry the bulk; reserve L1 (per-school section) for residual high-value cases.
- Add a measurable field-completeness gate + a real closure loop (write + resolve issue).

**Non-Goals:**
- Roster collection (done). Paper extraction (Part 2.1, separate). Hand-writing per-school-per-field templates. Lowering targets to pass the gate.

## Decisions

1. **Template-agnostic layers (L2/L3) carry the bulk.** *Why:* education/position are 0% in 6/10 schools because only SIGS's template is recognized; an LLM extractor + external enrichment are template-independent and cover all schools in one pass. *Alternative rejected:* per-school section extractors for every field — ~296 hand-fixes, non-systematic.
2. **Per-field source chain is normative, ordered L1→L2→L3.** *Why:* each field has different best sources (research_directions ← OpenAlex; education ← ORCID; title/award ← homepage/LLM only). A declared chain makes completion deterministic and auditable. Fields with no external source stop at L2.
3. **L4 (crawl-fix) gates L1–L3.** *Why:* HIT-SZ has 0% across all fields because the page isn't parsed; no field layer helps. Total-failure detection routes to crawl diagnosis first.
4. **Closure is part of completion (write + resolve issue).** *Why:* A1 root cause — without closure, field gaps are filed-not-fixed and re-pile. Each completion resolves its `pipeline_issue`.
5. **Reuse, don't rebuild:** L2 reuses the fact extractor; L3 extends `openalex_metrics.py` + existing ORCID backfill; the audit mirrors `run_professor_field_completeness_audit.py` style. *Why:* minimize new surface; these are already evidence-graded and run_id-aware.

## Risks / Trade-offs

- **[LLM extraction accuracy / hallucination]** → L2 outputs are facts, not free text; validate against homepage text (source-span containment, like the paper LLM extractor); low-confidence facts flagged `needs_review`, not auto-written. L3 (OpenAlex/ORCID) is authoritative for its fields.
- **[ORCID coverage is low]** → L3 ORCID only fires when an ORCID iD is present; many professors lack ORCID → education stays residual (reported, not silently filed). OpenAlex concepts have broader coverage for research_directions.
- **[OpenAlex rate-limits (B1)]** → L3 enrichment respects the existing circuit + the B1 provider-hardening change; failures are retriable, not silent.
- **[Field-source conflict]** → chain is ordered; a higher-priority source's value wins; later sources only fill empties (no overwrite of an existing attributed value).
- **[Completeness targets too aggressive]** → targets are declared per field; unmet targets are residual-risk issues, not gate-lowered. (Closure ≠ 100% fill.)

## Migration Plan

1. Ship the field-completeness **audit** first (read-only baseline artifact per-school × per-field).
2. **L4**: diagnose + fix total-failure schools (HIT-SZ first); re-audit.
3. **L3**: OpenAlex-concepts research_directions backfill + ORCID education/work backfill (bounded slice); verify fill-rate rise + provenance.
4. **L2**: LLM fact extraction for template-failed pages (bounded slice); verify.
5. **L1**: targeted per-school section fixes for residual high-value fields (Chinese research overview).
6. Closure loop live at each layer.

**Rollback:** each layer writes attributed facts with `run_id`; revert by `run_id`; no schema change. LLM/ORCID-sourced facts can be downgraded to `needs_review` without data loss.

## Open Questions

- **Completeness targets per field** (e.g., research_directions ≥70%, education ≥40% given ORCID limits) — set after the L3 slice shows achievable rates.
- **L2 model/prompt**: reuse the existing fact-extraction LLM profile or a dedicated field-extraction prompt — decide at slice time.
- **Decomposition**: this is cross-cutting (L2/L3/L4 are independent subsystems) — it may decompose into child changes (one per layer) at execution time, per CLAUDE.md §8 Epic guidance. The parent change locks the architecture + per-field chain; children implement layers.
- **Whether to MODIFY `professor-profile-field-extraction-integrity` vs keep `professor-profile-field-completion` separate** — kept separate here; revisit at archive.
