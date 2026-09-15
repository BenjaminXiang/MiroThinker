# Proposal: data-cleaning-batch1 (D0-a rule-based cleaning of the serving pack)

> Stage-one D0 of `docs/plans/2026-09-15-requirements-gap-plan.md` §8 (R21:
> local-first requires measurable, gate-able local data quality).  The
> read-only first assessment (`docs/plans/2026-09-15-data-quality-assessment.md`,
> evidence in `.agents/runs/data-quality-assessment/`) fixed the numbers; this
> change implements the four rule-based cleaning items it ranked D0-1..D0-4 and
> gates them at build time.  Applies to run16: no production data is rewritten
> and no release is rebuilt in this slice.

## Why

1. **Placeholders are published as data.** run15 serves `未找到` in 1,817
   whole values, 2 prefix values and 189 glued runs (company), plus the build
   gate's own English fallbacks across 12,872 professor field hits.  The local
   claim text in `knowledge_serving_isolated` renders company
   `profile_summary` / `technology_route_summary` / `product_description`
   verbatim, so users can be shown `简介：未找到`.
2. **Glue damage is a real corruption, not formatting.** 177 of the 189 glue
   values replaced characters *inside* identifiers or version strings
   (`DM-7未找到未找到C`, `V1.未找到`); the replaced characters are gone and the
   remaining text still carries the token.
3. **Company geography stops at the province.** 4,887 of 5,491 companies carry
   `广东省` only, while 91.8% have a `registered_address` that names the city;
   the serving side routes city questions through `geography`.
4. **Research directions contain parse junk.** 796 of 10,238 entries are page
   layout blocks, sentence fragments, truncated tails, ≤2-character tokens or
   dated CV/publication dumps; they pollute professor recall.
5. **Nothing prevents recurrence.** The pack's placeholder census is warn-only;
   a rebuild today would republish every one of these values.

## What Changes

1. **New build-side rule module** `canonical_v2/publication_cleaning.py` - pure
   functions for placeholder families, glue damage, no-information sentences,
   geography city derivation and research-direction junk, plus a publication
   audit and a fail-closed gate.
2. **Applied once, at the projection choke point**
   (`domain_projection._ProjectionContext.project_identity`): cleaning happens
   where selected source values become typed domain projections, so lookup
   documents, vector content and the Postgres projection all inherit it.  Source
   assertions and evidence stay verbatim (O1 evidence discipline).
3. **Placeholder-only fields publish as absent**, which requires the nine
   historically required fields that carried placeholders to become optional at
   the projection level (company `profile_summary`,
   `technology_route_summary`; professor `department`, `email`, `homepage`,
   `title`, `profile_summary`, `paper_summary`, `patent_summary`).  The domain
   catalog is untouched: its `requiredness` only feeds `quality_status`.
4. **Publication gate**: `IndexProjectionBuilder.build` audits the lookup
   documents it is about to publish and fails the build on any published
   placeholder, glue damage, research-direction junk, or when city-level
   company geography drops below 90%.
5. **Offline replay counter + side reports**
   (`.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py`) reproduce the
   before/after counts on a read-only copy of the run15 pack and emit
   `quarantine.jsonl` (withheld values, verbatim) and `kept-legit-prose.jsonl`
   for the D1 LLM review lane.

## Out of scope (D0-b / D1)

venue merging, relationship-edge dedup, empty-row cleanup, dead-field schema
work, placeholder-aware completeness metrics, writing the quarantine side
report from inside the build, LLM-assisted repair of the withheld values,
the 1,595 companies with no geography at all, and the three dirty geography
labels (`广东省-珠海`, `苏州市`, `-开曼群岛`).
