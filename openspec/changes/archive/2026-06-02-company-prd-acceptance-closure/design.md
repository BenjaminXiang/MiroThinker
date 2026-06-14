## Context

The Company domain already has the main XLSX import, enrichment, product/scenario synthesis, source judgment, vector refresh, and admin detail surfaces. Recent full-company work produced broad product/scenario coverage and refreshed the Company vector index, but the PRD still has open acceptance gates that require explicit evidence rather than more crawling:

- Mandatory release fields `profile_summary` and `technology_route_summary` must be complete for all released companies.
- Company Top-5 retrieval relevance must be manually evaluated on at least 50 enterprise-class queries.
- Deduplication accuracy must be evaluated against at least 100 human-labeled duplicate pairs.
- Company detail API and release payloads must expose traceable evidence/source data.
- Monthly or on-demand refresh must be an operator workflow with checkpoint and report evidence.
- `needs_review` must become a publication policy instead of a blanket block on all Company facts.

The current worktree is intentionally dirty from prior Company/Professor/Paper changes. This change avoids broad rewrites and adds focused scripts, reports, and small policy helpers around the existing Company pipeline.

## Goals / Non-Goals

**Goals:**

- Close the remaining Company PRD acceptance gates with reproducible reports and narrow code changes.
- Fix the remaining mandatory summary gaps without forcing new external enrichment.
- Produce annotation-ready CSVs for retrieval relevance and duplicate-pair validation.
- Make evidence/source presence testable at API/release boundaries.
- Define refresh and review publication policy in code or runbook form so operators can execute it consistently.
- Keep accepted high-confidence XLSX and official-source facts visible while preserving review gates for low-confidence external facts.

**Non-Goals:**

- No unbounded live crawling.
- No anti-bot, CAPTCHA, login, paywall, or robots bypass.
- No change to the PRD thresholds unless the user explicitly changes them.
- No requirement that every product or scenario reaches 100% coverage.
- No manual review of all Company rows.

## Decisions

1. **Use acceptance harnesses instead of more enrichment as the default closure path.**
   - Rationale: The PRD gaps are mostly validation and publication-contract gaps, not evidence that more source crawling is required.
   - Alternative considered: rerun all external enrichment before validation. Rejected because it increases runtime and noise without proving relevance, deduplication, or release traceability.

2. **Keep human labels as the final truth for Top-5 relevance and deduplication.**
   - Rationale: The PRD explicitly requires manual relevance and duplicate-pair judgment. LLM pre-labeling may speed review, but it cannot be the final acceptance source.
   - Alternative considered: use an LLM-only evaluator. Rejected because it would not satisfy the stated PRD gate.

3. **Generate annotation-ready artifacts before requiring user participation.**
   - Rationale: The user should review compact, evidence-rich CSVs instead of searching through raw DB rows or UI pages.
   - Artifacts include company names, IDs, summaries, product/scenario snippets, evidence URLs, scores, and suggested labels where available.

4. **Represent `needs_review` as a publication decision, not a Company-base blocker.**
   - Rationale: XLSX and official-source facts can be trusted enough for display when identity and attribution gates pass. Low-confidence generic web facts remain review-gated.
   - Alternative considered: hide all `needs_review` rows. Rejected because it blocks useful high-confidence facts and conflicts with the user's operating requirement.

5. **Prefer incremental refresh selection over scheduled full external reruns.**
   - Rationale: The PRD asks for sustainable monthly or on-demand updates, not exhaustive live web refresh every run.
   - Refresh selection will use uploaded/touched company IDs, stale source timestamps, missing mandatory fields, and explicit operator requests.

## Risks / Trade-offs

- **Human labeling can delay final acceptance** -> Generate compact CSVs with enough context and optional suggested labels so the user can label quickly.
- **Top-5 relevance can pass while ranking quality is weak** -> Report auxiliary Top-1 and Precision@5 metrics, but keep the PRD gate as Top-5 hit rate.
- **Duplicate-pair generation can be biased** -> Include likely duplicates, likely non-duplicates, and hard pairs; compute metrics only on labeled non-uncertain rows.
- **Evidence exists in storage but not API/release** -> Add boundary tests and audit reports that check the user-facing payload, not only raw tables.
- **Review policy may overpublish low-confidence web facts** -> Gate publication by source tier, identity confirmation, attribution evidence, and quality status; keep generic weak facts out of default RAG/display.

## Migration Plan

1. Add focused acceptance scripts and tests without changing existing table layout unless a missing field is proven.
2. Run summary completeness audit and backfill missing summaries from XLSX/synthesized source material.
3. Generate retrieval and deduplication annotation CSVs.
4. Run API/release evidence audit on a representative sample.
5. Add or verify refresh and review policy helpers.
6. Record reports under `.agents/runs/company-prd-acceptance-closure/`.
7. Run focused tests and `openspec validate company-prd-acceptance-closure --strict`.

Rollback is limited to reverting code changes and, for DB writes, restoring the pre-run report generated before the summary backfill. Evaluation CSVs and reports are append-only evidence artifacts.
