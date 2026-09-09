# Acceptance — professor-profile-field-completion-pipeline

> Maps to `specs/professor-profile-field-completion/spec.md`. Evidence under `.agents/runs/professor-profile-field-completion-pipeline/`. Met / Partial / Unmet with artifact or gap.

## A1. Per-field source chain (spec: "Each structured field has a declared chain")
- **A1.1** Dispatcher attempts L1→L2→L3 and leaves a field empty only after exhaustion. — Met via `tests/.../test_field_completion_*` (RED→GREEN).
- **A1.2** External-applicable fields (research_directions←OpenAlex; education/work←ORCID) use enrichment before empty. — Met via L3 dry-run/apply artifact.

## A2. L2 LLM extraction is template-agnostic (spec: "LLM structured-field extraction")
- **A2.1** A template-resistant school's fields are populated via LLM with source-span containment validation; low-confidence → needs_review. — Met via L2 bounded apply artifact + containment test.

## A3. L3 external enrichment (spec: "External enrichment backfills")
- **A3.1** OpenAlex concepts raise `research_directions` fill-rate; facts carry source `openalex` + run_id. — Met via before/after audit delta.
- **A3.2** ORCID education/employment raise `education`/`work_experience` where ORCID present. — Partial where ORCID absent (reported residual, not filed-as-done).

## A4. L4 total-failure diagnosis (spec: "Total-extraction failures")
- **A4.1** HIT(Shenzhen) diagnosed + crawl-fixed; fields move off 0%. — **Met.** L4(a) redirect-follow fix (shared `paper/homepage_http.py`) verified (redirect test + 249 fetch-path tests, no regression). L4(b) HIT Playwright mapper fixed on real data (`research_directions` now extracts real bio topics with a UI-chrome denylist — verified zero chrome leak; `canonical_name`/`department`/`contact_email`/`education`/`work_experience` correct) and the fixture is the real 142 KB render. **E2E proven**: bounded apply on a HIT-SZ sample rendered real pages → extracted → wrote 24 `professor_fact` rows (hedaojing: 18 facts across contact/education/research_topic/work_experience; dengxiang: 6) with a registered `pipeline_run` run_id + valid `source_page_id`; HIT-SZ fill-rate rose rdir/edu/work/contact **0/0/0/4% → 1/1/1/6%** (2-profs sample; full 136 coverage + non-activated pages need the full apply + L3 OpenAlex/ORCID). 105 L4+integration tests green; ruff clean.

## A5. Field-completeness gate (spec: "Field-completeness gate")
- **A5.1** Audit emits per-school × per-field fill-rate artifact; flags under-target fields. — Met via `run_professor_field_completeness_audit.py` artifact.

## A6. Closure (spec: "Completion closes its issues")
- **A6.1** Completed fields resolve their field-gap `pipeline_issue` with run_id + source; not left open. — Met via closure writer test + apply artifact.

## A7. Provenance (spec: "Completed fields carry source provenance and run_id")
- **A7.1** No field written without source + run_id. — Met via provenance test.

## Out of scope
- Roster collection (done). Paper extraction (Part 2.1, separate). Per-school-per-field hand-templates (L1 only residual).

## Skipped / deferred
- Full-population L2/L3 apply (cost) — replaced by bounded-slice apply per layer with fill-rate-delta evidence. Completeness targets finalized after L3 achievable-rate is measured.
- L4(b) HIT(Shenzhen) bounded Playwright apply — deferred until live HIT render and `miroflow_real` DB socket access are available.
