## Why

The Company domain enrichment pipeline has completed the main collection and scaleout work, but several PRD acceptance gates remain unclosed: mandatory summary completeness, human Top-5 retrieval relevance, duplicate-pair deduplication accuracy, source/evidence contract checks, refresh cadence, and review-state publishing policy.

This change converts those open items into executable acceptance artifacts and small remediation steps, without forcing further data enrichment when the current implementation already satisfies the PRD.

## What Changes

- Backfill or repair the remaining Company records whose `profile_summary` or `technology_route_summary` is missing so the mandatory release-field completeness gate reaches 100%.
- Add a reproducible Company Top-5 retrieval evaluation harness for at least 50 enterprise-class queries, producing an annotation-ready CSV and an acceptance report after human labels are provided.
- Add an evidence/source contract audit for sampled Company detail API and release payloads, covering source URL, source type/tier, update timestamp, and field-level support for products, scenarios, signals, profile, and technology summaries.
- Add a duplicate-pair evaluation harness that generates at least 100 candidate labeled pairs and computes deduplication accuracy from human labels.
- Define and implement the monthly/on-demand refresh acceptance path so operators can run incremental Company refreshes with checkpoint, stale-source selection, and report evidence instead of blindly rerunning all external sources.
- Define and implement the `needs_review` publishing policy so high-confidence XLSX/official/source-judged facts can be shown while low-confidence external facts remain review-gated.
- Record all verification evidence under `.agents/runs/company-prd-acceptance-closure/` and the OpenSpec acceptance artifact.

## Capabilities

### New Capabilities

- `company-prd-acceptance-closure`: Company PRD acceptance closure for mandatory summary completeness, Top-5 retrieval relevance, deduplication labeled-pair evaluation, API/release evidence contract, incremental refresh cadence, and review-state publication policy.

### Modified Capabilities

- `company-enrichment-source-closure`: Clarifies that accepted Company source facts must remain traceable through API/release surfaces and that review-gated source facts must not be treated as fully published without a source-confidence policy.

## Impact

- Affected code: Company narrative/backfill scripts, Company release/detail serializers, Company retrieval evaluation tooling, Company deduplication evaluation tooling, Company enrichment batch refresh selection, Company review-state policy helpers, admin-console detail APIs, and focused tests.
- Affected storage: existing Company tables only unless current tables cannot represent the required audit outputs; preferred output for acceptance artifacts is CSV/JSON under `.agents/runs/company-prd-acceptance-closure/`.
- Affected validation: OpenSpec strict validation, focused Company unit/script tests, DB-backed summary completeness checks, retrieval evaluation CSV generation, duplicate-pair annotation CSV generation, evidence/source audit report, incremental refresh dry-run report, and review-policy sample report.
- Out of scope: unbounded new crawling, anti-bot bypass, full external re-enrichment of all companies, and changing PRD acceptance thresholds without explicit user approval.
