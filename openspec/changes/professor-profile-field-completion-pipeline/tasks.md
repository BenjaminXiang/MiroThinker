# Tasks — professor-profile-field-completion-pipeline

> Cross-cutting (Epic-shaped): L2/L3/L4 are independent subsystems and may split into child changes at execution time. Order below is the recommended sequence; each layer is independently verifiable. RED = contract/unit tests for the deterministic audit + closure + source-chain logic; L2 LLM + L3/L4 real-runs are acceptance evidence.

## 1. Verification contract & baseline

- [ ] 1.1 Create `.agents/runs/professor-profile-field-completion-pipeline/verification-contract.md`: classify as behavior-affecting; RED = unit/contract tests for the per-field source-chain dispatcher, the closure writer, and the audit; L2/L3/L4 real-runs are acceptance (not RED). State allowed Superpowers mode.
- [ ] 1.2 Build `scripts/run_professor_field_completeness_audit.py` (read-only): per-school × per-field fill-rate (`research_directions`, `research_overview`, `education`, `academic_position`, `work_experience`, `award`, `contact`); save baseline artifact `field-completeness-baseline-YYYYMMDD.json`. Confirm the 6/10-school education/position 0% + HIT-SZ total-failure readings.

## 2. Layer 4 — total-failure crawl diagnosis (gates L1–L3)

- [ ] 2.1 Diagnose HIT(Shenzhen): fetch a sample of professor homepage URLs; determine cause (HTTP 403/anti-scrape, JS-rendered, URL structure, selector). Record findings + a fix (retry/header/Playwright/selector) in the run dir.
- [ ] 2.2 Apply the L4 crawl fix; re-run the field audit for HIT-SZ; confirm fields move off 0%.

## 3. Layer 3 — external enrichment backfill (template-agnostic)

- [ ] 3.1 Extend `professor/openalex_metrics.py` (or a sibling) to fetch author `concepts`/`x_concepts`; map top concepts → `research_topic` facts with source `openalex` + `run_id`. Respect the OpenAlex circuit + B1 failure taxonomy.
- [ ] 3.2 ORCID education/employment backfill: where a professor has an ORCID iD, fetch education/employment → `education`/`work_experience` facts, source `orcid` + `run_id`. (Reuse existing ORCID fetch infra.)
- [ ] 3.3 Bounded dry-run + apply on a sample; verify `research_directions`/`education` fill-rate rise + provenance; resolve matching field-gap `pipeline_issue` rows.

## 4. Layer 2 — LLM structured-field extraction (template-agnostic)

- [ ] 4.1 LLM field extractor: given homepage text, extract `research_topic`/`education`/`academic_position`/`work_experience`/`award`/`contact` facts. Reuse the fact-extraction LLM profile/prompt; add source-span containment validation (mirror the paper LLM extractor); low-confidence → `needs_review`.
- [ ] 4.2 Wire L2 to run when L1 section extraction returns nothing for a field; write facts with source `llm_extraction` + `run_id`.
- [ ] 4.3 Bounded dry-run + apply on a template-failed school (e.g., a SZU/SUSTech subset); verify fill-rate rise + containment-validated facts.

## 5. Layer 1 — per-school homepage section extraction (residual, targeted)

- [ ] 5.1 After L2/L3, identify residual high-value fields per school (e.g., Chinese `research_overview` for schools with structured tables); add targeted section extractors mirroring the SIGS precedent (`prof-sigs-tab-template-extraction`).
- [ ] 5.2 Verify targeted fill-rate rise without regressing `is_plausible`-style quality guards.

## 6. Source-chain dispatcher + closure + audit (deterministic)

- [ ] 6.1 Source-chain dispatcher: for a professor × field, attempt L1→L2→L3 in declared order; first non-empty attributed value wins; later sources only fill empties.
- [ ] 6.2 Closure writer: on field completion, resolve the matching field-gap `pipeline_issue` (reporter/stage for field gaps) with `run_id` + source. Idempotent.
- [ ] 6.3 Field-completeness gate: audit compares per-school × per-field fill-rate to declared targets; under-target → residual-risk issue (not silently filed, not gate-lowered).

## 7. Tests (RED → GREEN)

- [ ] 7.1 RED: source-chain dispatcher attempts L1→L2→L3 and leaves empty only after exhaustion; higher-priority source wins; later sources don't overwrite.
- [ ] 7.2 RED: closure writer resolves the field-gap issue on completion; idempotent.
- [ ] 7.3 RED: audit computes per-school × per-field fill-rates correctly; flags under-target fields.
- [ ] 7.4 RED: provenance — no field written without a source + `run_id`.
- [ ] 7.5 GREEN: implement to pass; run `uv run pytest` for the new test files (`-n0`).

## 8. Real evidence, acceptance, ledger

- [ ] 8.1 Re-run the field-completeness audit after L4/L3/L2 slices; save before/after artifacts; report per-school fill-rate deltas.
- [ ] 8.2 Fill `acceptance.md` against each spec scenario (evidence artifact or gap).
- [ ] 8.3 `openspec validate professor-profile-field-completion-pipeline --strict` exits 0.
- [ ] 8.4 Register in `openspec/change-ledger.md`; note Epic/child-split decision (§design Open Questions).
