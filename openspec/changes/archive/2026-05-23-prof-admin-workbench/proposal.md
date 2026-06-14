---
change_id: prof-admin-workbench
type: epic (parent) — quality-status rework + admin audit workbench + fact extraction
weight: Epic
behavior_change: true
code_change: design only at this stage; child changes carry implementation
adds_requirements: true (new capabilities across 3 child changes)
created: 2026-05-14
canonical_input:
  - Brainstorming session 2026-05-14 (5 locked decisions, see design.md "Locked decisions")
  - docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md (Professor-domain canonical)
  - Live DB inspection 2026-05-14 (miroflow_real: 495/495 professors stuck needs_review)
children:
  - prof-quality-status-rework
  - prof-fact-extraction-expansion
  - prof-admin-workbench-ui
---

# Proposal: prof-admin-workbench (Epic)

## Why

The admin console at `:5180` is meant to be the surface where an
administrator **accepts or rejects scraped professor data**. Today it
cannot do that job:

- All 495 professors in `miroflow_real` sit at `quality_status =
  needs_review`. `canonical_writer.py` never writes `quality_status`,
  so every row stays at the column default. `needs_review` has become
  the universal default state, which makes human review unrunnable at
  Shenzhen scale (tens of thousands of professors expected).
- `quality_gate.evaluate_quality()` exists but (a) is never called by
  the canonical write path, (b) operates on the in-pipeline
  `EnrichedProfessorProfile` object rather than persisted canonical
  state, and (c) routes merely-incomplete records (missing research
  directions, shallow summary) into `needs_review` — conflating
  "incomplete" with "anomalous".
- The professor detail page is a generic 4-domain record viewer. It
  surfaces `core_facts + profile_summary` only. It does not aggregate
  `professor_fact`, affiliation history, `source_page`, or
  `pipeline_issue`, and has no quality-diagnosis view. An admin cannot
  tell whether a professor was scraped correctly, what is missing,
  where each field came from, or what to do next without querying the
  database directly.
- `education / work_experience / award / academic_position` have no
  structured storage populated, even though `ck_professor_fact_type`
  already allows those `fact_type` values.

## What Changes

This Epic decomposes into three child changes, sequenced quality-first
and then data-first:

1. **`prof-quality-status-rework`** (pure backend) — Extract
   `evaluate_professor_quality(canonical_state)` as a pure function
   over persisted canonical state, correct the 4-state semantics so
   `needs_review` is reserved for true anomalies, wire it into
   `canonical_writer`, add a standalone re-evaluation entry point, and
   re-grade the existing 495 rows. No migration required.

2. **`prof-fact-extraction-expansion`** — Add LLM structured
   extraction for `education / work_experience / award /
   academic_position` into `professor_fact`, backfill those facts plus
   LLM-generated factual `profile_summary` over the eligible no-summary
   professors (those with non-empty `profile_raw_text`; the eligible
   count is established by the fact-extraction child preflight, not assumed), and
   re-run quality evaluation. No migration required.

3. **`prof-admin-workbench-ui`** — Add the `/api/admin/professor/*`
   namespace (rich aggregated audit payload + lightweight marking
   actions), a `professor_admin_action` table for the operation log
   (the Epic's only migration), and rebuild the professor detail page
   as a single-column audit workbench with quality diagnosis pinned at
   the top and inline per-field provenance.

## Non-goals

- In-page field editing and same-name merge — v1 marking actions are
  limited to `confirm_ready` / `send_to_review` / `flag_recrawl`.
- Professor lifecycle modeling — owned by the registered
  `prof-lifecycle-state` change. `quality_status` answers "is the data
  trustworthy", not "is the person still active".
- Paper/patent aggregate summaries — owned by `prof-summary-fields`.
  The fact-extraction child's `generate_summaries` produces the
  `profile_summary` (fact-type contract output), not paper/patent
  aggregates.
- Milvus retrieval index split — owned by `prof-double-milvus-collection`.

## Child change scaffolding

This parent change carries the Epic-level `design.md` only. The three
child changes' `proposal.md / specs/ / design.md / tasks.md /
acceptance.md / source-links.md` are the immediate next step after
this design is reviewed.
